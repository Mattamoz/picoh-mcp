"""Embodiment layer: a single point of contact for everything that *moves* Picoh.

Everywhere else in the codebase imports ``Embodiment`` from here. No other module
calls ``picoh`` directly. That gives us:

* A ``MockPicoh`` backend that lets every app run without hardware.
* A central clamp/sanity layer (positions are always 0–10 floats).
* A registry of valid eye shapes so tool calls fail loudly with bad input.
* Thread-safety on the serial line (Picoh's USB transport doesn't love
  concurrent writes from our reflex/cognition loops).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Protocol

# Eye shapes shipped with the default picohData/Ohbot.obe file.
# (Confirmed against the picoh-python README + EyeShape Designer Tool defaults.)
EYE_SHAPES: tuple[str, ...] = (
    "Angry",
    "BoxLeft",
    "BoxRight",
    "Crying",
    "Eyeball",
    "Full",
    "Glasses",
    "Heart",
    "Large",
    "Sad",
    "SmallBall",
    "Square",
    "SunGlasses",
    "VerySad",
)

MOTORS: tuple[str, ...] = (
    "HEADNOD",
    "HEADTURN",
    "EYETURN",
    "LIDBLINK",
    "BOTTOMLIP",
    "EYETILT",
    # TOPLIP exists in some library builds; we treat it as optional.
    "TOPLIP",
)


def _clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, float(x)))


class PicohBackend(Protocol):
    """The minimum interface the embodiment layer needs."""

    def move(self, motor: str, pos: float, speed: float = 5) -> None: ...
    def set_eye_shape(self, right: str, left: str) -> None: ...
    def set_eye_brightness(self, val: float) -> None: ...
    def set_base_colour(self, r: float, g: float, b: float) -> None: ...
    def say(self, text: str, until_done: bool = True, lip_sync: bool = True) -> None: ...
    def play_sound(self, name: str, until_done: bool = True) -> None: ...
    def read_sensor(self, pin: int) -> float: ...
    def wait(self, seconds: float) -> None: ...
    def reset(self) -> None: ...
    def close(self) -> None: ...


# --------------------------------------------------------------------------- #
# Real hardware backend
# --------------------------------------------------------------------------- #

class HardwarePicoh:
    """Wraps the actual ``picoh`` library, isolating us from name drift.

    The picoh library exposes motor names as module-level constants
    (``picoh.HEADNOD``, etc.) and supports ``setBaseColour`` and ``baseColour``
    in different shipped versions — we feel for both.
    """

    def __init__(self, port: str | None = None) -> None:
        # picoh-python's importable module is ``from picoh import picoh``.
        # The module auto-connects on import (prints "Picoh found on port:..."),
        # so calling init() afterwards actually *closes* the working connection
        # and re-opens it — which often fails. Only call init() if the auto-
        # connect didn't take.
        from picoh import picoh as _p

        self._picoh = _p
        connected = bool(getattr(_p, "connected", False))
        if not connected and hasattr(_p, "init"):
            ok = _p.init(port) if port else _p.init("")
            if ok is False:
                raise RuntimeError(
                    "picoh.init returned False — couldn't find the Picoh serial port. "
                    "Set PICOH_PORT in your .env or pass --port."
                )
        if not hasattr(_p, "HEADNOD"):
            raise RuntimeError("picoh module missing motor constants; install may be broken.")

    # ----- motors ---------------------------------------------------------- #
    def move(self, motor: str, pos: float, speed: float = 5) -> None:
        m = getattr(self._picoh, motor, None)
        if m is None:
            return  # silently ignore optional motors not present in this build
        self._picoh.move(m, _clamp(pos), _clamp(speed))

    # ----- LED matrix eyes ------------------------------------------------- #
    def set_eye_shape(self, right: str, left: str) -> None:
        self._picoh.setEyeShape(right, left)

    def set_eye_brightness(self, val: float) -> None:
        self._picoh.setEyeBrightness(_clamp(val))

    # ----- base RGB -------------------------------------------------------- #
    def set_base_colour(self, r: float, g: float, b: float) -> None:
        r, g, b = _clamp(r), _clamp(g), _clamp(b)
        if hasattr(self._picoh, "setBaseColour"):
            self._picoh.setBaseColour(r, g, b)
        else:  # older builds
            self._picoh.baseColour(r, g, b)

    # ----- audio ---------------------------------------------------------- #
    def say(self, text: str, until_done: bool = True, lip_sync: bool = True) -> None:
        self._picoh.say(text, untilDone=until_done, lipSync=lip_sync)

    def play_sound(self, name: str, until_done: bool = True) -> None:
        self._picoh.playSound(name, untilDone=until_done)

    # ----- sensors -------------------------------------------------------- #
    def read_sensor(self, pin: int) -> float:
        return float(self._picoh.readSensor(int(pin)))

    # ----- lifecycle ------------------------------------------------------ #
    def wait(self, seconds: float) -> None:
        self._picoh.wait(seconds)

    def reset(self) -> None:
        self._picoh.reset()

    def close(self) -> None:
        self._picoh.close()


# --------------------------------------------------------------------------- #
# Mock backend — lets every app run without hardware
# --------------------------------------------------------------------------- #

@dataclass
class _State:
    motors: dict[str, float] = field(default_factory=lambda: {m: 5.0 for m in MOTORS})
    eyes: tuple[str, str] = ("Eyeball", "Eyeball")
    brightness: float = 10.0
    base: tuple[float, float, float] = (0.0, 0.0, 0.0)


class MockPicoh:
    """In-process mock. Prints actions and tracks state for inspection in tests."""

    def __init__(self, verbose: bool = True) -> None:
        self.state = _State()
        self.verbose = verbose
        self.log: list[tuple[str, tuple]] = []

    def _record(self, op: str, *args) -> None:
        self.log.append((op, args))
        if self.verbose:
            print(f"[picoh.mock] {op}{args}", flush=True)

    def move(self, motor: str, pos: float, speed: float = 5) -> None:
        if motor in self.state.motors:
            self.state.motors[motor] = _clamp(pos)
        self._record("move", motor, _clamp(pos), _clamp(speed))

    def set_eye_shape(self, right: str, left: str) -> None:
        self.state.eyes = (right, left)
        self._record("eyes", right, left)

    def set_eye_brightness(self, val: float) -> None:
        self.state.brightness = _clamp(val)
        self._record("brightness", _clamp(val))

    def set_base_colour(self, r: float, g: float, b: float) -> None:
        c = (_clamp(r), _clamp(g), _clamp(b))
        self.state.base = c
        self._record("base", *c)

    def say(self, text: str, until_done: bool = True, lip_sync: bool = True) -> None:
        self._record("say", text)
        # simulate roughly realistic TTS duration
        if until_done:
            time.sleep(min(4.0, max(0.4, 0.06 * len(text.split()))))

    def play_sound(self, name: str, until_done: bool = True) -> None:
        self._record("play_sound", name)

    def read_sensor(self, pin: int) -> float:
        return 5.0

    def wait(self, seconds: float) -> None:
        time.sleep(max(0.0, float(seconds)))

    def reset(self) -> None:
        self.state = _State()
        self._record("reset")

    def close(self) -> None:
        self._record("close")


# --------------------------------------------------------------------------- #
# High-level Embodiment facade
# --------------------------------------------------------------------------- #

class Embodiment:
    """Thread-safe, validated facade other modules use.

    Construction:
        emb = Embodiment.connect()              # autodetect hardware or mock
        emb = Embodiment.connect(mock=True)     # force mock
        emb = Embodiment.connect(port="...")    # explicit port

    All motor positions are clamped to 0–10. Unknown eye shapes raise
    ``ValueError`` so a misbehaving LLM fails fast instead of silently doing
    nothing. The serial transport is wrapped in a lock so reflex/cognition
    loops can call methods from different threads without garbling bytes.
    """

    def __init__(self, backend: PicohBackend, *, mocked: bool) -> None:
        self.backend = backend
        self.mocked = mocked
        self._lock = threading.RLock()

    # ----- construction --------------------------------------------------- #
    @classmethod
    def connect(cls, *, port: str | None = None, mock: bool | None = None) -> "Embodiment":
        if mock is None:
            mock = os.getenv("PICOH_MOCK", "0") == "1"
        if not mock:
            try:
                return cls(HardwarePicoh(port or os.getenv("PICOH_PORT") or None), mocked=False)
            except Exception as e:
                print(f"[embodiment] falling back to MockPicoh: {e}", flush=True)
                mock = True
        return cls(MockPicoh(), mocked=True)

    # ----- motion --------------------------------------------------------- #
    def move(self, motor: str, pos: float, speed: float = 5) -> None:
        if motor not in MOTORS:
            raise ValueError(f"Unknown motor {motor!r}; valid: {MOTORS}")
        with self._lock:
            self.backend.move(motor, _clamp(pos), _clamp(speed))

    def head_pose(
        self,
        nod: float | None = None,
        turn: float | None = None,
        tilt: float | None = None,
        speed: float = 5,
    ) -> None:
        with self._lock:
            if nod is not None:
                self.backend.move("HEADNOD", _clamp(nod), _clamp(speed))
            if turn is not None:
                self.backend.move("HEADTURN", _clamp(turn), _clamp(speed))
            if tilt is not None:
                self.backend.move("EYETILT", _clamp(tilt), _clamp(speed))

    def look(self, x: float, y: float, speed: float = 8) -> None:
        """Saccade: only eyes move, not the head.

        EYETILT/EYETURN don't move the physical eye housings — they pick
        which *sub-frame* of the multi-frame eye-shape hex is rendered.
        Most stored shapes only have ~5-6 pupil positions vertically, so
        we clamp ``y`` tighter than ``x`` to keep the pattern recognisable.
        Outside this range you start to see "line" or empty frames.
        """
        with self._lock:
            self.backend.move("EYETURN", _clamp(x), _clamp(speed))
            self.backend.move("EYETILT", _clamp(y, 3.5, 6.5), _clamp(speed))

    def look_center(self, speed: float = 8) -> None:
        """Snap eyes to centre so the next set_eyes shows the full frame."""
        with self._lock:
            self.backend.move("EYETURN", 5.0, _clamp(speed))
            self.backend.move("EYETILT", 5.0, _clamp(speed))

    # ----- LED eyes ------------------------------------------------------- #
    def set_eyes(self, left: str, right: str | None = None, *, recenter: bool = True) -> None:
        """Set the LED eye shapes. By default we first re-centre the pupil
        (EYETILT/EYETURN → 5) so the *main* frame of the multi-frame hex is
        what gets drawn. Without this, leftover pupil offset from a
        previous look() can leave the shape showing as a partial line."""
        right = right or left
        if left not in EYE_SHAPES:
            raise ValueError(f"Unknown eye shape {left!r}; valid: {EYE_SHAPES}")
        if right not in EYE_SHAPES:
            raise ValueError(f"Unknown eye shape {right!r}; valid: {EYE_SHAPES}")
        with self._lock:
            if recenter:
                self.backend.move("EYETURN", 5.0, 10)
                self.backend.move("EYETILT", 5.0, 10)
            self.backend.set_eye_shape(right, left)

    def eye_brightness(self, val: float) -> None:
        with self._lock:
            self.backend.set_eye_brightness(_clamp(val))

    # ----- base RGB ------------------------------------------------------- #
    def base_colour(self, r: float, g: float, b: float) -> None:
        with self._lock:
            self.backend.set_base_colour(_clamp(r), _clamp(g), _clamp(b))

    def base_palette(self, palette: Iterable[float]) -> None:
        r, g, b = list(palette)[:3]
        self.base_colour(r, g, b)

    # ----- audio --------------------------------------------------------- #
    def say(self, text: str, *, until_done: bool = True, lip_sync: bool = True) -> None:
        with self._lock:
            self.backend.say(text, until_done=until_done, lip_sync=lip_sync)

    def play_sound(self, name: str, *, until_done: bool = True) -> None:
        with self._lock:
            self.backend.play_sound(name, until_done=until_done)

    # ----- sensors ------------------------------------------------------- #
    def read_sensor(self, pin: int) -> float:
        with self._lock:
            return self.backend.read_sensor(pin)

    # ----- lifecycle ----------------------------------------------------- #
    def wait(self, seconds: float) -> None:
        self.backend.wait(seconds)

    def reset(self) -> None:
        with self._lock:
            self.backend.reset()

    def close(self) -> None:
        with self._lock:
            self.backend.close()

    # ----- context manager ----------------------------------------------- #
    def __enter__(self) -> "Embodiment":
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.reset()
        finally:
            self.close()
