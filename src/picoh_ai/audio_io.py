"""Audio I/O for the OpenAI Realtime API.

The Realtime API speaks 16-bit little-endian mono PCM. Mic + speaker are
both 24 kHz by default (the API resamples our 24 kHz output natively).

We deliberately keep this thin: a producer that hands chunks to a callback,
and a consumer that plays a queue of chunks. Backpressure and "stop playing
when the user interrupts" are handled by the Realtime client, not here.
"""

from __future__ import annotations

import base64
import queue
import threading
from typing import Callable, Optional

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 480  # 20ms at 24 kHz — feels responsive without thrashing
DURATION_MS_PER_BLOCK = 20


def _import_sounddevice():
    import numpy as np
    import sounddevice as sd
    return sd, np


class MicStream:
    """Captures PCM blocks from the default input and ships them to ``on_chunk``.

    on_chunk receives raw int16 little-endian bytes (no header).
    """

    def __init__(self, on_chunk: Callable[[bytes], None]) -> None:
        self.on_chunk = on_chunk
        self._stream = None
        self._stop = threading.Event()

    def start(self) -> "MicStream":
        sd, np = _import_sounddevice()

        def cb(indata, frames, time_info, status):  # noqa: ARG001
            if self._stop.is_set():
                raise sd.CallbackStop
            pcm = indata.tobytes()  # already int16 mono LE
            self.on_chunk(pcm)

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
            callback=cb,
        )
        self._stream.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass


class SpeakerStream:
    """Plays a queue of int16-LE PCM chunks at 24 kHz."""

    def __init__(self) -> None:
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=64)
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> "SpeakerStream":
        sd, np = _import_sounddevice()
        self._stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
        )
        self._stream.start()

        def pump():
            while not self._stop.is_set():
                try:
                    chunk = self._q.get(timeout=0.1)
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                try:
                    arr = np.frombuffer(chunk, dtype="<i2").reshape(-1, 1)
                    self._stream.write(arr)
                except Exception:
                    pass

        self._thread = threading.Thread(target=pump, daemon=True, name="speaker")
        self._thread.start()
        return self

    def play(self, pcm: bytes) -> None:
        try:
            self._q.put_nowait(pcm)
        except queue.Full:
            # drop oldest to keep latency low — better than blocking the WS loop
            try:
                self._q.get_nowait()
                self._q.put_nowait(pcm)
            except Exception:
                pass

    def clear(self) -> None:
        """Drop everything queued — used when the user interrupts."""
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def stop(self) -> None:
        self._stop.set()
        self._q.put_nowait(None)
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass


def pcm_b64(chunk: bytes) -> str:
    return base64.b64encode(chunk).decode("ascii")


def b64_pcm(s: str) -> bytes:
    return base64.b64decode(s)
