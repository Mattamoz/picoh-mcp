"""Smoke test — verify Picoh wiring without spinning up any LLM.

Walks through every embodiment channel: moves each motor, cycles eye
shapes, runs every named gesture, sweeps the base colour, says a line,
prints sensor readings.

    picoh-smoke              # against real hardware
    PICOH_MOCK=1 picoh-smoke # against MockPicoh — sanity test on any machine
"""

from __future__ import annotations

import argparse
import os
import time

from dotenv import load_dotenv

from ..embodiment import EYE_SHAPES, Embodiment
from ..gestures import GESTURE_NAMES, perform
from ..idle import IdleLoop


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="End-to-end smoke test for picoh-ai.")
    p.add_argument("--port", default=None)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--fast", action="store_true", help="Run quickly, skip dwell times")
    args = p.parse_args()
    if args.mock:
        os.environ["PICOH_MOCK"] = "1"

    pause = (lambda s: None) if args.fast else time.sleep
    emb = Embodiment.connect(port=args.port)
    print(f"== Smoke test (mock={emb.mocked}) ==", flush=True)

    with IdleLoop(emb) as idle:
        idle.inhibit(60)  # we'll drive everything explicitly

        print("[1/6] motor sweep")
        for motor in ("HEADNOD", "HEADTURN", "EYETURN", "EYETILT"):
            for pos in (3, 7, 5):
                emb.move(motor, pos, 6)
                pause(0.4)
        # LIDBLINK: 10=open, 0=closed
        emb.move("LIDBLINK", 0, 10)   # blink shut
        pause(0.15)
        emb.move("LIDBLINK", 10, 10)  # open again
        pause(0.2)

        print("[2/6] eye shapes")
        for shape in EYE_SHAPES:
            emb.set_eyes(shape)
            pause(0.35)
        emb.set_eyes("Eyeball")

        print("[3/6] base colour sweep")
        palette = (
            (10, 0, 0), (0, 10, 0), (0, 0, 10),
            (10, 10, 0), (10, 0, 10), (0, 10, 10),
            (10, 10, 10), (0, 0, 0),
        )
        for r, g, b in palette:
            emb.base_colour(r, g, b)
            pause(0.4)

        print("[4/6] gestures")
        for name in GESTURE_NAMES:
            if name == "sleep":
                continue  # save sleep for the very end
            print(f"    > {name}")
            perform(emb, name)
            pause(0.4)

        print("[5/6] speech")
        emb.say("Hello, world. I am Picoh, and all systems are nominal.", until_done=True, lip_sync=True)

        print("[6/6] sensors")
        for pin in range(7):
            try:
                v = emb.read_sensor(pin)
                print(f"    pin {pin}: {v:.2f}")
            except Exception as e:
                print(f"    pin {pin}: error {e}")

        perform(emb, "sleep")
    emb.reset()
    emb.close()
    print("== Smoke OK ==", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
