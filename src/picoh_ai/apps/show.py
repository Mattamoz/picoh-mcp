"""show — a self-contained Picoh show for kids.

Zero API keys, zero LLMs. Five acts of motion, colour, expressions,
face-tracking, narration and a dance finale. ~90 seconds.

    picoh-show
    picoh-show --no-tracking         # skip the face-tracking acts (no camera)
    picoh-show --act finale          # jump to a single act
    picoh-show --silent              # no speech (useful if system voice is slow)

Design notes:

* The show NEVER blacks out the eyes — they stay lit so a slow TTS call
  can't make Picoh look frozen.
* Every speech call has a 10-second watchdog. If macOS ``say`` hangs, the
  show prints a warning and moves on.
* Every act begins by resetting Picoh to a known pose (eyes open + bright,
  head centred, neutral shape) so a buggy preceding act can't snowball.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import threading
import time

from dotenv import load_dotenv

from ..embodiment import Embodiment
from ..gestures import perform
from ..idle import IdleLoop


# --------------------------------------------------------------------------- #
# Defensive helpers
# --------------------------------------------------------------------------- #

SILENT = False


def _reset_pose(emb: Embodiment) -> None:
    """Bring Picoh to a known-good visible state."""
    emb.move("LIDBLINK", 10, 10)           # eyelids open (10=open, 0=closed)
    emb.eye_brightness(10)                  # eyes lit
    # Re-centre pupils so eye shapes draw the *main* sub-frame, not a line.
    emb.look_center(speed=10)
    emb.set_eyes("Eyeball")
    emb.head_pose(nod=5, turn=5, tilt=5, speed=8)


def _say(emb: Embodiment, line: str, pause_after: float = 0.4) -> None:
    """Speak ``line`` with a 10-second watchdog so a hung TTS call can't
    freeze the show. Lip-sync runs in picoh's own thread; we just wait."""
    print(f"  [picoh] {line}", flush=True)
    if SILENT:
        # Approximate lip-flap by just opening the mouth a little
        emb.move("BOTTOMLIP", 7, 6)
        time.sleep(0.25 * max(1, len(line.split())))
        emb.move("BOTTOMLIP", 5, 6)
        return

    done = threading.Event()

    def _speak():
        try:
            emb.say(line, until_done=True, lip_sync=True)
        finally:
            done.set()

    threading.Thread(target=_speak, daemon=True).start()
    # Estimate: ~0.35s/word + a fixed setup cost. Watchdog at 10s hard cap.
    est = 0.35 * max(1, len(line.split())) + 0.6
    if not done.wait(timeout=min(10.0, est * 1.8 + 1.5)):
        print("    (speech watchdog: TTS taking too long, moving on)", flush=True)
    time.sleep(pause_after)


def _pulse_base(emb: Embodiment, palette: list[tuple[int, int, int]], dwell: float = 0.25) -> None:
    for r, g, b in palette:
        emb.base_colour(r, g, b)
        time.sleep(dwell)


# --------------------------------------------------------------------------- #
# Act 1 — Wake up
# --------------------------------------------------------------------------- #

def act_wakeup(emb: Embodiment) -> None:
    print("\n=== ACT 1: Wake up ===", flush=True)
    _reset_pose(emb)

    # Head dips and looks up — like coming alive
    emb.head_pose(nod=3, turn=5, tilt=5, speed=3)
    emb.base_colour(0, 0, 4)
    time.sleep(0.6)
    emb.head_pose(nod=6, speed=3)

    # Eye saccade — look around the room
    emb.look(2, 5, speed=10); time.sleep(0.3)
    emb.look(8, 5, speed=10); time.sleep(0.3)
    emb.look(5, 5, speed=10); time.sleep(0.2)

    # Rainbow flash to celebrate being awake
    _pulse_base(emb, [
        (10, 0, 0), (10, 5, 0), (10, 10, 0),
        (0, 10, 0), (0, 0, 10), (10, 0, 10),
    ], dwell=0.18)
    emb.base_colour(3, 3, 8)

    emb.set_eyes("Large")
    perform(emb, "nod_yes")
    _say(emb, "Hello! I am Picoh. Want to see some tricks?")


# --------------------------------------------------------------------------- #
# Act 2 — Emotion carousel
# --------------------------------------------------------------------------- #

EMOTIONS = [
    # (eyes, base_rgb, gesture, line)
    ("Heart",     (10, 1, 5),   "love",        "Happy."),
    ("Sad",       (0, 2, 6),    "sigh",        "Sad."),
    ("Large",     (10, 5, 0),   "double_take", "Surprised!"),
    ("Angry",     (10, 0, 0),   "shake_no",    "Grumpy."),
    ("SunGlasses",(2, 6, 8),    None,          "Cool."),
    ("Glasses",   (4, 4, 0),    "think",       "Thinking."),
    ("Crying",    (0, 0, 8),    None,          "Sad eyes."),
]


def act_emotions(emb: Embodiment) -> None:
    print("\n=== ACT 2: Emotions ===", flush=True)
    _reset_pose(emb)
    _say(emb, "Watch my face change.")
    for shape, rgb, gesture, line in EMOTIONS:
        # Re-centre BEFORE setting the shape so the eye draws cleanly,
        # and re-assert the shape AFTER any gesture (some gestures
        # internally set_eyes to a different pattern).
        emb.look_center(speed=10)
        emb.set_eyes(shape)
        emb.base_colour(*rgb)
        if gesture:
            try:
                perform(emb, gesture)
            except Exception:
                pass
            # Re-assert shape + pupil position after the gesture.
            emb.look_center(speed=10)
            emb.set_eyes(shape)
        _say(emb, line, pause_after=0.15)
    _reset_pose(emb)
    emb.base_colour(3, 3, 8)


# --------------------------------------------------------------------------- #
# Act 3 — Face tracking
# --------------------------------------------------------------------------- #

def act_face_track(emb: Embodiment, duration: float = 15.0, vs=None) -> None:
    print("\n=== ACT 3: Picoh sees you ===", flush=True)
    if vs is None:
        print("  (skipping — no shared VisionSensor passed in)", flush=True)
        return

    _reset_pose(emb)
    emb.base_colour(2, 6, 8)
    _say(emb, "Come here. I can see you!")
    # Brief settle, then go — the act itself patiently waits for the kid to
    # appear and reacts the moment they do.
    time.sleep(0.5)

    start = time.time()
    saw_anyone = False
    last_emotion = None
    sm_yaw = sm_pitch = 0.0
    alpha = 0.30
    last_motor = 0.0

    while time.time() - start < duration:
        s = vs.state
        now = time.time()
        if s.present:
            saw_anyone = True
            sm_yaw = alpha * s.yaw + (1 - alpha) * sm_yaw
            sm_pitch = alpha * s.pitch + (1 - alpha) * sm_pitch

            if now - last_motor > 0.18:
                eye_x = max(1.0, min(9.0, 5 + 4 * (-sm_yaw)))
                eye_y = max(4.0, min(6.0, 5 + 1.5 * sm_pitch))
                emb.look(eye_x, eye_y, speed=10)
                emb.head_pose(turn=5 + 2 * (-sm_yaw),
                              nod=5 + 1.5 * sm_pitch,
                              speed=4)
                last_motor = now

            if s.emotion != last_emotion:
                last_emotion = s.emotion
                if s.emotion == "happy":
                    emb.set_eyes("Heart"); emb.base_colour(10, 2, 5)
                elif s.emotion == "sad":
                    emb.set_eyes("Sad");   emb.base_colour(0, 2, 8)
                elif s.emotion == "surprised":
                    emb.set_eyes("Large"); emb.base_colour(10, 6, 0)
                elif s.emotion == "angry":
                    emb.set_eyes("Angry"); emb.base_colour(10, 0, 0)
                else:
                    emb.set_eyes("Eyeball"); emb.base_colour(2, 6, 8)
        else:
            if now - last_motor > 0.30:
                emb.head_pose(turn=5, nod=5, speed=3)
                emb.look(5, 5, speed=6)
                last_motor = now
        time.sleep(0.05)

    if saw_anyone:
        _say(emb, "I see you!")
    else:
        _say(emb, "Where did you go?")


# --------------------------------------------------------------------------- #
# Act 4 — Copycat
# --------------------------------------------------------------------------- #

def act_copycat(emb: Embodiment, rounds: int = 3, vs=None) -> None:
    print("\n=== ACT 4: Copycat ===", flush=True)
    if vs is None:
        print("  (skipping — no shared VisionSensor passed in)", flush=True)
        return

    challenges = [
        ("happy",     "Heart", (10, 5, 1), "Now you smile big like me!"),
        ("surprised", "Large", (10, 7, 0), "Show me surprised — open your mouth wide!"),
        ("sad",       "Sad",   (0, 2, 8),  "Pull a sad face."),
    ]

    _reset_pose(emb)
    _say(emb, "Copy my face when I show you. Ready?")

    score = 0
    if True:  # keep indentation consistent
        for target, shape, rgb, prompt in challenges[:rounds]:
            emb.set_eyes(shape)
            emb.base_colour(*rgb)
            emb.head_pose(nod=6, tilt=4, speed=4)
            _say(emb, prompt)

            t0 = time.time()
            match = False
            best_seen = "absent"
            while time.time() - t0 < 4.5:
                if vs.state.present:
                    best_seen = vs.state.emotion
                    if vs.state.emotion == target:
                        match = True
                        break
                time.sleep(0.1)

            if match:
                score += 1
                emb.set_eyes("Heart")
                emb.base_colour(0, 10, 0)
                perform(emb, "nod_yes")
                _say(emb, "Yes! That is it!", pause_after=0.2)
            else:
                emb.set_eyes("Crying")
                emb.base_colour(8, 0, 0)
                perform(emb, "shake_no")
                _say(emb, f"Close! I thought I saw {best_seen}.", pause_after=0.2)

    _reset_pose(emb)
    emb.set_eyes("SunGlasses")
    emb.base_colour(6, 0, 8)
    _say(emb, f"You got {score} out of {rounds}!")


# --------------------------------------------------------------------------- #
# Act 5 — Disco finale
# --------------------------------------------------------------------------- #

def act_finale(emb: Embodiment, duration: float = 16.0) -> None:
    print("\n=== ACT 5: Finale ===", flush=True)
    _reset_pose(emb)
    _say(emb, "And now — disco!")

    rainbow = [
        (10, 0, 0), (10, 5, 0), (10, 10, 0),
        (0, 10, 0), (0, 10, 10), (0, 0, 10),
        (10, 0, 10),
    ]
    eye_cycle = ["Large", "Heart", "SunGlasses", "Eyeball", "Glasses", "SmallBall"]
    bpm = 128.0
    beat = 60.0 / bpm

    t0 = time.time()
    bx = 0
    last_blink = time.time()
    last_eye = time.time()
    last_pose = time.time()

    last_sacc = time.time()
    while time.time() - t0 < duration:
        now = time.time()
        phase = (now - t0) / beat

        # Body bob — head nod alternates
        if now - last_pose > beat / 4:
            nod = 5 + 3 * math.sin(phase * math.pi)
            turn = 5 + 2 * math.sin(phase * math.pi * 0.5)
            emb.head_pose(nod=nod, turn=turn, speed=10)
            last_pose = now

        # Saccades — eye TURN only, keep tilt centred so shapes stay clean
        if now - last_sacc > beat:
            emb.move("EYETURN", random.uniform(3, 7), 10)
            last_sacc = now

        # Eye shape every 2 beats — re-centre pupil first so shape draws cleanly
        if now - last_eye > beat * 2:
            try:
                emb.look_center(speed=10)
                emb.set_eyes(eye_cycle[int(phase / 2) % len(eye_cycle)])
            except ValueError:
                pass
            last_eye = now

        # Colour every beat
        bx = (bx + 1) % len(rainbow)
        emb.base_colour(*rainbow[bx])

        # Occasional blink (10=open, 0=closed)
        if now - last_blink > 1.4 and random.random() < 0.25:
            emb.move("LIDBLINK", 0, 10)   # close
            time.sleep(0.05)
            emb.move("LIDBLINK", 10, 10)  # open
            last_blink = now

        time.sleep(beat / 2)

    # Big finish
    _reset_pose(emb)
    emb.set_eyes("Heart")
    emb.base_colour(10, 0, 5)
    perform(emb, "excited")
    _say(emb, "Ta-da! Thanks for watching!")
    perform(emb, "nod_yes")
    emb.set_eyes("SunGlasses")
    emb.base_colour(0, 0, 3)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

ACTS = {
    "wakeup":   act_wakeup,
    "emotions": act_emotions,
    "track":    act_face_track,
    "copycat":  act_copycat,
    "finale":   act_finale,
}


def main() -> int:
    global SILENT
    load_dotenv()
    p = argparse.ArgumentParser(description="Picoh show — a kid-friendly performance.")
    p.add_argument("--port", default=None)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--no-tracking", action="store_true",
                   help="Skip face-tracking & copycat acts (camera required)")
    p.add_argument("--silent", action="store_true",
                   help="No speech — useful if system TTS is sluggish")
    p.add_argument("--act", choices=list(ACTS.keys()),
                   help="Run a single act only")
    args = p.parse_args()

    SILENT = args.silent
    if args.mock:
        os.environ["PICOH_MOCK"] = "1"
    os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

    emb = Embodiment.connect(port=args.port)
    idle = IdleLoop(emb).start()
    idle.inhibit(600)  # We drive every motion during the show

    # Open camera ONCE at show start and share across acts. macOS
    # AVFoundation is flaky about handing the camera back if we close
    # and re-open between acts within a few hundred ms.
    vs = None
    if not args.no_tracking and not args.mock:
        try:
            from ..vision import VisionSensor
            vs = VisionSensor(
                camera_index=int(os.getenv("PICOH_CAMERA_INDEX", "0")),
                use_deepface=False,
            ).start()
            # Hold for ~2.5s so the AVFoundation pipeline is warm before Act 1
            time.sleep(2.5)
            print(f"  [vision] warm-up complete; face_present={vs.state.present}", flush=True)
        except Exception as e:
            print(f"  [vision] failed to start camera: {e}", flush=True)
            vs = None

    print(f"\n*** Picoh Show — mock={emb.mocked} silent={SILENT} vision={vs is not None} ***\n", flush=True)
    try:
        if args.act:
            fn = ACTS[args.act]
            if args.act in {"track", "copycat"}:
                fn(emb, vs=vs)
            else:
                fn(emb)
        else:
            for name, fn in ACTS.items():
                if args.no_tracking and name in {"track", "copycat"}:
                    continue
                if name in {"track", "copycat"}:
                    fn(emb, vs=vs)
                else:
                    fn(emb)
                time.sleep(0.3)
    finally:
        if vs:
            vs.stop()
        idle.stop()
        time.sleep(0.3)
        emb.reset()
        emb.close()
    print("\n*** Curtain ***\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
