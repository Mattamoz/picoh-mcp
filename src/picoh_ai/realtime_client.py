"""Async OpenAI Realtime API client wired to the embodiment.

This is the single most important file in the project. Reading from top to
bottom you should see one continuous flow:

    mic -> ws.input_audio_buffer.append
    ws.response.audio.delta -> speaker
    ws.response.function_call_arguments.done -> embodiment
    vision sensor change -> ws.conversation.item.create (system note)

Everything else is plumbing.

Event reference (subset we actually use):

    Client -> server
        session.update                  initial config (voice, tools, etc)
        input_audio_buffer.append       streamed mic audio
        conversation.item.create        inject text/system messages
        response.cancel                 interrupt model speech (barge-in)
        response.create                 ask for a manual turn

    Server -> client
        session.created / session.updated
        input_audio_buffer.speech_started   (server VAD: user started talking)
        input_audio_buffer.speech_stopped
        response.created
        response.audio.delta              base64 PCM chunk
        response.audio_transcript.delta   running transcript of what *Picoh* said
        response.function_call_arguments.delta
        response.function_call_arguments.done
        response.done
        error
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from typing import Callable, Optional

from .audio_io import MicStream, SpeakerStream, b64_pcm, pcm_b64
from .embodiment import Embodiment
from .persona import EMPATH_PROMPT
from .tools import dispatch, openai_realtime_tools


DEFAULT_MODEL = os.getenv("PICOH_REALTIME_MODEL", "gpt-realtime")
DEFAULT_VOICE = os.getenv("PICOH_REALTIME_VOICE", "cedar")
REALTIME_URL_TEMPLATE = "wss://api.openai.com/v1/realtime?model={model}"


class RealtimeClient:
    def __init__(
        self,
        embodiment: Embodiment,
        *,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        voice: str = DEFAULT_VOICE,
        instructions: str = EMPATH_PROMPT,
        on_transcript: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.embodiment = embodiment
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.on_transcript = on_transcript

        self.speaker: SpeakerStream | None = None
        self.mic: MicStream | None = None
        self._ws = None
        self._send_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._fn_args: dict[str, str] = defaultdict(str)   # call_id -> json string
        self._fn_name: dict[str, str] = {}                 # call_id -> tool name
        self._user_speaking = False
        self._last_user_emotion: str | None = None

    # ----- public ---------------------------------------------------------#
    async def connect(self) -> None:
        import websockets

        url = REALTIME_URL_TEMPLATE.format(model=self.model)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self._ws = await websockets.connect(
            url, additional_headers=headers, max_size=16 * 1024 * 1024
        )
        self._loop = asyncio.get_running_loop()
        await self._send({
            "type": "session.update",
            "session": {
                "instructions": self.instructions,
                "voice": self.voice,
                "modalities": ["audio", "text"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "gpt-4o-mini-transcribe"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 600,
                    "create_response": True,
                },
                "tools": openai_realtime_tools(),
                "tool_choice": "auto",
            },
        })

    async def run(self) -> None:
        """Open mic + speaker, then pump events until the WS closes."""
        self.speaker = SpeakerStream().start()
        self.mic = MicStream(self._on_mic_chunk).start()
        try:
            await self._event_loop()
        finally:
            if self.mic:
                self.mic.stop()
            if self.speaker:
                self.speaker.stop()
            if self._ws:
                await self._ws.close()

    async def push_user_emotion(self, emotion: str) -> None:
        """Slip a system note into the conversation about user emotion."""
        if emotion == self._last_user_emotion:
            return
        self._last_user_emotion = emotion
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"[user_emotion={emotion}] Adjust tone and visual mood "
                            f"to match. Do not call this out aloud."
                        ),
                    }
                ],
            },
        })

    async def say(self, text: str) -> None:
        """Inject a *spoken* message from the model — useful as a wake-up line."""
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        })
        await self._send({"type": "response.create"})

    # ----- mic ----------------------------------------------------------- #
    def _on_mic_chunk(self, pcm: bytes) -> None:
        # called from sounddevice's audio thread — hop to the asyncio loop
        if not self._ws or not self._loop:
            return
        asyncio.run_coroutine_threadsafe(
            self._send({"type": "input_audio_buffer.append", "audio": pcm_b64(pcm)}),
            self._loop,
        )

    # ----- WS pumps ------------------------------------------------------ #
    async def _send(self, payload: dict) -> None:
        if not self._ws:
            return
        async with self._send_lock:
            await self._ws.send(json.dumps(payload))

    async def _event_loop(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            await self._handle(ev)

    async def _handle(self, ev: dict) -> None:
        t = ev.get("type", "")
        # ---- audio out ---------------------------------------------------#
        if t == "response.audio.delta":
            if self.speaker:
                self.speaker.play(b64_pcm(ev["delta"]))
            return

        # ---- transcript --------------------------------------------------#
        if t == "response.audio_transcript.delta":
            if self.on_transcript:
                try:
                    self.on_transcript(ev.get("delta", ""))
                except Exception:
                    pass
            return

        # ---- VAD / barge-in ---------------------------------------------#
        if t == "input_audio_buffer.speech_started":
            self._user_speaking = True
            # interrupt anything Picoh is mid-saying
            if self.speaker:
                self.speaker.clear()
            await self._send({"type": "response.cancel"})
            return

        if t == "input_audio_buffer.speech_stopped":
            self._user_speaking = False
            return

        # ---- function calls ---------------------------------------------#
        if t == "response.output_item.added":
            item = ev.get("item", {})
            if item.get("type") == "function_call":
                cid = item.get("call_id") or item.get("id")
                if cid:
                    self._fn_name[cid] = item.get("name", "")
                    self._fn_args[cid] = ""
            return

        if t == "response.function_call_arguments.delta":
            cid = ev.get("call_id")
            if cid:
                self._fn_args[cid] += ev.get("delta", "")
            return

        if t == "response.function_call_arguments.done":
            cid = ev.get("call_id")
            name = self._fn_name.get(cid) or ev.get("name") or ""
            raw_args = self._fn_args.pop(cid, ev.get("arguments", "") or "{}")
            self._fn_name.pop(cid, None)
            try:
                args = json.loads(raw_args or "{}")
            except Exception:
                args = {}
            # Tool dispatch runs in the worker thread pool so motor moves
            # don't stall the event loop.
            result = await asyncio.to_thread(dispatch, self.embodiment, name, args)
            await self._send({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": cid,
                    "output": json.dumps(result),
                },
            })
            await self._send({"type": "response.create"})
            return

        if t == "error":
            err = ev.get("error", {})
            print(f"[realtime] error: {err.get('type')}: {err.get('message')}", flush=True)
            return

        # silently ignore the dozen other event types we don't care about
