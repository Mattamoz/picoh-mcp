"""Companion — autonomous desk pet that runs all day.

Three concurrent loops:

* **Reflex** (handled by ``IdleLoop``): blinks, breathing, micro-saccades.
  Always on.
* **Perception** (1 Hz): samples vision + audio levels + sensors, files
  ``Event`` records when something interesting happens.
* **Cognition** (every 60–120 s, or sooner if perception spikes): asks
  Claude Haiku for a small JSON behaviour script using the last 20 events
  + persistent facts + current mood/energy.

The cognition output is a list of *actions* that get pushed onto a
priority queue. A fourth worker drains the queue and executes them.

Memory persists to ``companion_memory.json`` so personality survives across
restarts.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import random
import signal
import threading
import time
from collections import deque
from typing import Any

from dotenv import load_dotenv

from ..embodiment import Embodiment
from ..gestures import GESTURE_NAMES, perform
from ..idle import IdleLoop
from ..memory_store import MemoryStore
from ..persona import COMPANION_PERSONA
from ..vision import VisionSensor


# --------------------------------------------------------------------------- #
# Perception
# --------------------------------------------------------------------------- #

class Perception(threading.Thread):
    def __init__(
        self,
        memory: MemoryStore,
        vision: VisionSensor | None,
        emb: Embodiment,
        on_spike,
    ) -> None:
        super().__init__(daemon=True, name="perception")
        self.memory = memory
        self.vision = vision
        self.emb = emb
        self.on_spike = on_spike
        self._stop = threading.Event()
        self._recent_emotions: deque[str] = deque(maxlen=12)
        self._last_face_seen = 0.0

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                print(f"[perception] error: {e}", flush=True)
            time.sleep(1.0)

    def _tick(self) -> None:
        now = time.time()

        if self.vision and self.vision.state.present:
            if now - self._last_face_seen > 30:
                self.memory.add_event("face", "User appeared in front of me.")
                self.on_spike()
            self._last_face_seen = now
            e = self.vision.state.emotion
            self._recent_emotions.append(e)
            if e in ("happy", "sad", "angry", "surprised"):
                # only log strong emotions, once per change
                if len(self._recent_emotions) >= 2 and self._recent_emotions[-2] != e:
                    self.memory.add_event("user_emotion", f"User looked {e}.", emotion=e)

        # touch sensor on pin 0 (typical wiring) — spike on high reading
        try:
            v = self.emb.read_sensor(0)
            if v > 7.5:
                self.memory.add_event("touch", "Something touched my sensor.", pin=0, value=v)
                self.on_spike()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Cognition
# --------------------------------------------------------------------------- #

class Cognition(threading.Thread):
    def __init__(
        self,
        memory: MemoryStore,
        action_q: "queue.PriorityQueue",
        spike_evt: threading.Event,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        super().__init__(daemon=True, name="cognition")
        self.memory = memory
        self.q = action_q
        self.spike = spike_evt
        self.model = model
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            from anthropic import Anthropic
            client = Anthropic()
        except Exception as e:
            print(f"[cognition] disabled — anthropic not installed ({e})", flush=True)
            return

        while not self._stop.is_set():
            # Wait either for spike or for the regular slow cadence
            self.spike.wait(timeout=random.uniform(60, 120))
            self.spike.clear()
            if self._stop.is_set():
                break

            payload = {
                "mood": self.memory.mood,
                "energy": int(self.memory.energy),
                "recent": self.memory.recent(20),
                "facts": self.memory.facts(),
                "time": time.strftime("%H:%M"),
                "spoken_recently": True,
            }
            try:
                msg = client.messages.create(
                    model=self.model,
                    max_tokens=400,
                    system=COMPANION_PERSONA,
                    messages=[{"role": "user", "content": json.dumps(payload)}],
                )
                text = "".join(
                    getattr(b, "text", "") for b in msg.content
                ).strip()
                plan = json.loads(_strip_codefence(text))
            except Exception as e:
                print(f"[cognition] LLM/parse error: {e}", flush=True)
                continue

            self.memory.mood = plan.get("mood", self.memory.mood)
            new_energy = float(plan.get("energy", self.memory.energy - 0.5))
            self.memory.energy = max(0.0, min(10.0, new_energy))

            say_line = plan.get("say") or ""
            if say_line and not self.memory.saw_line(say_line):
                self.q.put((0, {"tool": "say", "args": {"text": say_line}}))
                self.memory.remember_line(say_line)

            for a in plan.get("actions", []):
                self.q.put((int(a.get("priority", 5)), a))

            thought = plan.get("thought", "")
            if thought:
                self.memory.add_event("thought", thought)


def _strip_codefence(t: str) -> str:
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t


# --------------------------------------------------------------------------- #
# Action worker
# --------------------------------------------------------------------------- #

class ActionWorker(threading.Thread):
    def __init__(
        self, emb: Embodiment, idle: IdleLoop, q: "queue.PriorityQueue"
    ) -> None:
        super().__init__(daemon=True, name="actions")
        self.emb = emb
        self.idle = idle
        self.q = q
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                _, action = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._execute(action)
            except Exception as e:
                print(f"[actions] error: {e}", flush=True)

    def _execute(self, a: dict[str, Any]) -> None:
        tool = a.get("tool", "")
        args = a.get("args", {}) or {}
        self.idle.inhibit(2.0)
        if tool == "set_eyes":
            self.emb.set_eyes(args["left"], args["right"])
        elif tool == "base_colour":
            self.emb.base_colour(args["r"], args["g"], args["b"])
        elif tool == "head_pose":
            self.emb.head_pose(
                nod=args.get("nod"), turn=args.get("turn"),
                tilt=args.get("tilt"), speed=args.get("speed", 5),
            )
        elif tool == "gesture":
            if args.get("name") in GESTURE_NAMES:
                perform(self.emb, args["name"])
        elif tool == "say":
            self.emb.say(args["text"])
        elif tool == "play_sound":
            self.emb.play_sound(args["name"])


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #

def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Picoh autonomous desk companion.")
    p.add_argument("--port", default=None)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--memory-path", default="companion_memory.json")
    p.add_argument("--no-vision", action="store_true")
    p.add_argument("--model", default=os.getenv("PICOH_COMPANION_MODEL",
                                                "claude-haiku-4-5-20251001"))
    args = p.parse_args()
    if args.mock:
        os.environ["PICOH_MOCK"] = "1"

    emb = Embodiment.connect(port=args.port)
    idle = IdleLoop(emb).start()
    memory = MemoryStore(args.memory_path)
    vision = None if args.no_vision else VisionSensor(use_deepface=False).start()

    action_q: "queue.PriorityQueue" = queue.PriorityQueue()
    spike_evt = threading.Event()

    perception = Perception(memory, vision, emb, lambda: spike_evt.set())
    cognition = Cognition(memory, action_q, spike_evt, model=args.model)
    actions = ActionWorker(emb, idle, action_q)

    for t in (perception, cognition, actions):
        t.start()

    idle.set_energy(memory.energy)
    print(
        f"[companion] running. mood={memory.mood} energy={memory.energy:.1f}. Ctrl-C to stop.",
        flush=True,
    )

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    try:
        # Tick: keep idle energy synced with memory.energy
        while not stop.is_set():
            idle.set_energy(memory.energy)
            time.sleep(2.0)
    finally:
        for t in (perception, cognition, actions):
            t.stop()
        if vision:
            vision.stop()
        idle.stop()
        emb.reset()
        emb.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
