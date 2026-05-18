"""Idle micro-behaviour loop.

What separates a "robot that's powered on" from a "robot that's alive" is
sub-second jitter: small head drifts, occasional blinks, gaze saccades,
"breathing" via HEADNOD. This module emits those whenever no app code is
explicitly driving the motors.

Design choices:

* **Single background thread.** Cheap. Daemonised so the app exits cleanly.
* **Inhibit window.** Apps call ``loop.inhibit(0.6)`` before an explicit
  motion so the idle layer stops fighting them; expires automatically.
* **Energy.** ``loop.energy`` (0–10) modulates frequency + amplitude:
  energy=0 → barely moves; energy=10 → very alert.
* **Pluggable.** ``loop.set_persona(...)`` lets the companion daemon swap
  in different idle profiles without restarting.
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass

from .embodiment import Embodiment


@dataclass
class IdlePersona:
    blink_min_s: float = 1.8
    blink_max_s: float = 5.5
    saccade_min_s: float = 2.5
    saccade_max_s: float = 7.0
    breath_hz: float = 0.25      # ~one breath every 4 s
    breath_amp: float = 0.6      # +- 0.6 around HEADNOD=5
    drift_min_s: float = 4.0
    drift_max_s: float = 10.0

    def scale(self, energy: float) -> "IdlePersona":
        """Higher energy → faster blinks / saccades, deeper breath."""
        k = max(0.1, min(2.0, 0.5 + energy / 10.0))
        return IdlePersona(
            blink_min_s=self.blink_min_s / k,
            blink_max_s=self.blink_max_s / k,
            saccade_min_s=self.saccade_min_s / k,
            saccade_max_s=self.saccade_max_s / k,
            breath_hz=self.breath_hz * k,
            breath_amp=self.breath_amp * (0.5 + energy / 20.0),
            drift_min_s=self.drift_min_s / k,
            drift_max_s=self.drift_max_s / k,
        )


@dataclass
class _Schedule:
    next_blink: float = 0.0
    next_saccade: float = 0.0
    next_drift: float = 0.0


class IdleLoop:
    def __init__(self, emb: Embodiment, persona: IdlePersona | None = None) -> None:
        self.emb = emb
        self._persona = persona or IdlePersona()
        self.energy = 6.0
        self._inhibit_until = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._schedule = _Schedule()
        # current "neutral" gaze target — saccades pick small offsets from this
        self._center = (5.0, 5.0, 5.0)  # nod, turn, tilt (HEADNOD/HEADTURN/EYETILT)

    # ----- public API ---------------------------------------------------- #
    def set_persona(self, persona: IdlePersona) -> None:
        self._persona = persona

    def set_energy(self, energy: float) -> None:
        self.energy = max(0.0, min(10.0, energy))

    def set_center(self, nod: float = 5.0, turn: float = 5.0, tilt: float = 5.0) -> None:
        self._center = (nod, turn, tilt)

    def inhibit(self, seconds: float = 0.6) -> None:
        """Suppress idle motions for ``seconds`` while an app is moving Picoh."""
        self._inhibit_until = max(self._inhibit_until, time.time() + seconds)

    def start(self) -> "IdleLoop":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="idle-loop")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    # ----- internal ------------------------------------------------------ #
    def _run(self) -> None:
        t0 = time.time()
        while not self._stop.is_set():
            now = time.time()
            if now < self._inhibit_until:
                time.sleep(0.05)
                continue

            persona = self._persona.scale(self.energy)

            # 1) Slow breathing on HEADNOD
            phase = (now - t0) * 2 * math.pi * persona.breath_hz
            nod = self._center[0] + persona.breath_amp * math.sin(phase)
            try:
                self.emb.move("HEADNOD", nod, 2)
            except Exception:
                pass

            # 2) Random blink (LIDBLINK: 10=open, 0=closed)
            if now >= self._schedule.next_blink:
                try:
                    self.emb.move("LIDBLINK", 0, 10)   # close
                    time.sleep(0.07)
                    self.emb.move("LIDBLINK", 10, 10)  # open
                except Exception:
                    pass
                self._schedule.next_blink = now + random.uniform(
                    persona.blink_min_s, persona.blink_max_s
                )
                if random.random() < 0.08:  # occasional double-blink
                    time.sleep(0.12)
                    try:
                        self.emb.move("LIDBLINK", 0, 10)
                        time.sleep(0.07)
                        self.emb.move("LIDBLINK", 10, 10)
                    except Exception:
                        pass

            # 3) Random saccade (eyes only, small)
            if now >= self._schedule.next_saccade:
                ex = self._center[1] + random.uniform(-1.5, 1.5)
                ey = self._center[2] + random.uniform(-1.0, 1.0)
                try:
                    self.emb.look(ex, ey, speed=10)
                except Exception:
                    pass
                self._schedule.next_saccade = now + random.uniform(
                    persona.saccade_min_s, persona.saccade_max_s
                )

            # 4) Occasional head drift to a new center
            if now >= self._schedule.next_drift:
                self._center = (
                    5.0 + random.uniform(-1.2, 1.2),
                    5.0 + random.uniform(-1.5, 1.5),
                    5.0 + random.uniform(-1.0, 1.0),
                )
                try:
                    self.emb.head_pose(
                        nod=self._center[0],
                        turn=self._center[1],
                        tilt=self._center[2],
                        speed=2,
                    )
                except Exception:
                    pass
                self._schedule.next_drift = now + random.uniform(
                    persona.drift_min_s, persona.drift_max_s
                )

            time.sleep(0.08)

    # context manager helpers
    def __enter__(self) -> "IdleLoop":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
