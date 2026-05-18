"""Theatre — Picoh performs an audience-aware story.

Two-model split:

* **Director** (Claude Opus/Sonnet) — slow, narrative-aware. Every 1–3
  beats it produces the next beats given history + audience reaction.
* **Performer** (Picoh + OpenAI TTS) — renders one beat at a time.
  Voice / palette / eyes / pose / gesture all change per character.

Audience reaction is captured continuously by ``VisionSensor`` — we
summarise the last beat's smile/engagement and feed it back to the
director.

Usage:

    picoh-theatre --premise "A nervous robot interviews a dragon for a job"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from ..embodiment import Embodiment
from ..gestures import GESTURE_NAMES, perform
from ..idle import IdleLoop
from ..persona import THEATRE_DIRECTOR_PROMPT
from ..vision import VisionSensor


# --------------------------------------------------------------------------- #
# Director
# --------------------------------------------------------------------------- #

class Director:
    def __init__(self, premise: str, model: str = "claude-sonnet-4-6") -> None:
        from anthropic import Anthropic
        self.client = Anthropic()
        self.model = model
        self.premise = premise
        self.history: list[dict] = []

    def next(self, audience_state: dict) -> dict:
        payload = {
            "premise": self.premise,
            "history": self.history[-12:],
            "audience_state": audience_state,
        }
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=900,
            system=THEATRE_DIRECTOR_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
        try:
            data = json.loads(_strip_codefence(text))
        except Exception as e:
            print(f"[theatre] director returned non-JSON ({e}); raw: {text[:200]}", flush=True)
            data = {"beats": [], "next": "end"}
        self.history.extend(data.get("beats", []))
        return data


def _strip_codefence(t: str) -> str:
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t


# --------------------------------------------------------------------------- #
# Performer
# --------------------------------------------------------------------------- #

class Performer:
    """Speaks a beat. By default uses OpenAI TTS for character voice variety;
    falls back to picoh.say (system voice) if openai isn't installed."""

    def __init__(self, emb: Embodiment) -> None:
        self.emb = emb
        try:
            from openai import OpenAI
            self._oai = OpenAI()
        except Exception:
            self._oai = None

    def speak(self, line: str, voice: str = "alloy") -> None:
        if self._oai is None:
            self.emb.say(line)
            return
        try:
            with self._oai.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=voice,
                input=line,
                response_format="wav",
            ) as resp:
                data = b"".join(resp.iter_bytes())
            # Write to tmp WAV and play via Picoh's WAV playback to get
            # built-in lip-sync. Drops the file in picohData/Sounds/.
            tmpdir = Path("picohData/Sounds")
            tmpdir.mkdir(parents=True, exist_ok=True)
            name = f"_theatre_tmp_{int(time.time()*1000)}.wav"
            (tmpdir / name).write_bytes(data)
            self.emb.play_sound(name[:-4])  # picoh.playSound takes name without ext
        except Exception as e:
            print(f"[theatre] TTS failed ({e}); falling back to picoh.say", flush=True)
            self.emb.say(line)

    def perform_beat(self, beat: dict) -> None:
        # palette
        pal = beat.get("palette") or [3, 3, 5]
        self.emb.base_colour(*pal)
        # eyes
        eyes = beat.get("eyes") or ["Eyeball", "Eyeball"]
        try:
            self.emb.set_eyes(eyes[0], eyes[1])
        except ValueError:
            self.emb.set_eyes("Eyeball")
        # pose
        pose = beat.get("pose") or {}
        self.emb.head_pose(
            nod=pose.get("nod"),
            turn=pose.get("turn"),
            tilt=pose.get("tilt"),
            speed=4,
        )
        # gesture (optional)
        g = beat.get("gesture") or ""
        if g and g in GESTURE_NAMES:
            perform(self.emb, g)
        # line
        line = (beat.get("line") or "").strip()
        if line:
            print(f"  [{beat.get('character','?')}] {line}", flush=True)
            self.speak(line, voice=beat.get("voice", "alloy"))
            time.sleep(0.3)


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #

def _audience_snapshot(vs: VisionSensor | None) -> dict:
    if not vs or not vs.state.present:
        return {"engaged": 0.5, "smile": 0.0, "scared": 0.0, "left": vs is not None and not vs.state.present}
    s = vs.state
    engaged = max(0.0, min(1.0, 0.5 + s.arousal * 0.5))
    return {
        "engaged": engaged,
        "smile": s.smile,
        "scared": max(0.0, -s.valence) * (1 - s.smile),
        "left": False,
    }


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Picoh one-robot theatre.")
    p.add_argument("--premise", default="A small robot meets a very serious cat for the first time.")
    p.add_argument("--port", default=None)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--no-vision", action="store_true")
    p.add_argument("--max-rounds", type=int, default=6)
    p.add_argument("--model", default=os.getenv("PICOH_DIRECTOR_MODEL", "claude-sonnet-4-6"))
    args = p.parse_args()
    if args.mock:
        os.environ["PICOH_MOCK"] = "1"

    emb = Embodiment.connect(port=args.port)
    idle = IdleLoop(emb).start()
    vs = None if args.no_vision else VisionSensor(use_deepface=False).start()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set; cannot run theatre director.", file=sys.stderr)
        return 2

    director = Director(args.premise, model=args.model)
    performer = Performer(emb)

    print(f"\n=== THEATRE: {args.premise} ===\n", flush=True)
    try:
        for round_ix in range(args.max_rounds):
            audience = _audience_snapshot(vs)
            print(f"[round {round_ix + 1}] audience: {audience}", flush=True)
            plan = director.next(audience)
            beats = plan.get("beats", [])
            if not beats:
                break
            idle.inhibit(60)  # we'll drive motion ourselves during the show
            for beat in beats:
                performer.perform_beat(beat)
            if audience.get("left"):
                break
        print("\n=== curtain ===\n", flush=True)
    finally:
        if vs:
            vs.stop()
        idle.stop()
        emb.reset()
        emb.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
