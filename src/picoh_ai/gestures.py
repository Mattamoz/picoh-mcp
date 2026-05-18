"""Composite named gestures.

These are short, opinionated motion phrases that read clearly on the Picoh.
They are intentionally synchronous — call them from a background thread if
you want them to overlap with speech.

Adding a gesture? Keep it under ~1.5 s, use ``speed >= 6`` for "snappy"
phrases, and end at a neutral pose unless the gesture *is* a held pose
(``sleep``, ``lean_in``).
"""

from __future__ import annotations

import random
import time
from typing import Callable

from .embodiment import Embodiment


def _seq(emb: Embodiment, *steps: tuple[str, float, float, float]) -> None:
    """Run a list of (motor, pos, speed, dwell_seconds) tuples."""
    for motor, pos, speed, dwell in steps:
        emb.move(motor, pos, speed)
        if dwell:
            time.sleep(dwell)


def nod_yes(emb: Embodiment) -> None:
    _seq(
        emb,
        ("HEADNOD", 3, 8, 0.18),
        ("HEADNOD", 7, 8, 0.18),
        ("HEADNOD", 3, 8, 0.18),
        ("HEADNOD", 5, 6, 0.15),
    )


def shake_no(emb: Embodiment) -> None:
    _seq(
        emb,
        ("HEADTURN", 3, 8, 0.16),
        ("HEADTURN", 7, 8, 0.16),
        ("HEADTURN", 3, 8, 0.16),
        ("HEADTURN", 5, 6, 0.15),
    )


def double_take(emb: Embodiment) -> None:
    """Look forward, snap left, snap right, recenter — the comedy beat."""
    _seq(
        emb,
        ("HEADTURN", 5, 10, 0.10),
        ("HEADTURN", 8, 10, 0.12),
        ("HEADTURN", 2, 10, 0.12),
        ("HEADTURN", 5, 8, 0.10),
    )
    emb.set_eyes("Large")
    time.sleep(0.4)
    emb.set_eyes("Eyeball")


def sigh(emb: Embodiment) -> None:
    """Slow downward head sweep + slight mouth open — a beat of resignation."""
    emb.head_pose(nod=3, speed=2)
    time.sleep(0.45)
    emb.move("BOTTOMLIP", 8, 5)
    time.sleep(0.35)
    emb.move("BOTTOMLIP", 5, 4)
    emb.head_pose(nod=5, speed=2)


def lean_in(emb: Embodiment) -> None:
    """Held forward + slight squint — attentive listening pose."""
    emb.head_pose(nod=6, turn=5, speed=3)
    emb.move("LIDBLINK", 7, 4)  # half-lid squint (10=open, 0=closed)
    emb.set_eyes("Eyeball")


def sleep(emb: Embodiment) -> None:
    """Slow droop to a held resting pose."""
    emb.head_pose(nod=2, speed=2)
    time.sleep(0.6)
    emb.move("LIDBLINK", 0, 3)  # eyes closed (0=closed)
    emb.eye_brightness(2)
    emb.base_colour(0, 0, 2)


def wake_up(emb: Embodiment) -> None:
    emb.eye_brightness(10)
    emb.move("LIDBLINK", 10, 8)  # eyes open (10=open)
    emb.head_pose(nod=5, turn=5, tilt=5, speed=4)
    emb.set_eyes("Eyeball")
    emb.base_colour(3, 3, 6)


def dance(emb: Embodiment, bars: int = 4, bpm: float = 110.0) -> None:
    """Simple 4/4 body bob synced to BPM. Call sparingly — it's loud on servos."""
    beat = 60.0 / bpm
    for _ in range(bars):
        emb.head_pose(nod=7, turn=3, speed=10)
        time.sleep(beat / 2)
        emb.head_pose(nod=4, turn=7, speed=10)
        time.sleep(beat / 2)
        emb.head_pose(nod=7, turn=7, speed=10)
        time.sleep(beat / 2)
        emb.head_pose(nod=4, turn=3, speed=10)
        time.sleep(beat / 2)
    emb.head_pose(nod=5, turn=5, speed=4)


def excited(emb: Embodiment) -> None:
    emb.base_colour(10, 6, 0)
    emb.set_eyes("Large")
    _seq(emb,
         ("HEADNOD", 8, 10, 0.10),
         ("HEADNOD", 3, 10, 0.10),
         ("HEADNOD", 8, 10, 0.10),
         ("HEADNOD", 5, 6, 0))


def think(emb: Embodiment) -> None:
    """Look up-and-away, hold, like the model is computing."""
    emb.set_eyes("Glasses")
    # Keep tilt within the safe pupil range so Glasses stays recognisable.
    emb.head_pose(nod=7, turn=3, tilt=6, speed=4)


def love(emb: Embodiment) -> None:
    emb.set_eyes("Heart")
    emb.base_colour(10, 0, 5)
    nod_yes(emb)


def confused(emb: Embodiment) -> None:
    emb.set_eyes("BoxLeft", "BoxRight")
    emb.head_pose(tilt=6, speed=5)  # stay inside the safe pupil tilt range
    emb.base_colour(5, 5, 0)


def neutral(emb: Embodiment) -> None:
    emb.set_eyes("Eyeball")
    emb.head_pose(nod=5, turn=5, tilt=5, speed=4)
    emb.base_colour(2, 2, 4)


# A registry tool calls and apps can index into.
GESTURES: dict[str, Callable[[Embodiment], None]] = {
    "nod_yes": nod_yes,
    "shake_no": shake_no,
    "double_take": double_take,
    "sigh": sigh,
    "lean_in": lean_in,
    "sleep": sleep,
    "wake_up": wake_up,
    "excited": excited,
    "think": think,
    "love": love,
    "confused": confused,
    "neutral": neutral,
}


GESTURE_NAMES: tuple[str, ...] = tuple(GESTURES.keys())


def perform(emb: Embodiment, name: str) -> None:
    """Run a gesture by name. ``ValueError`` if unknown."""
    if name not in GESTURES:
        raise ValueError(f"Unknown gesture {name!r}; valid: {GESTURE_NAMES}")
    GESTURES[name](emb)


def random_idle_gesture(emb: Embodiment) -> None:
    """Pick a quiet gesture suitable for idle periods (never ``dance``/``sleep``)."""
    quiet = [n for n in GESTURE_NAMES if n not in {"sleep", "dance", "excited"}]
    perform(emb, random.choice(quiet))
