"""Empath — the flagship realtime voice companion.

Runs:

* the OpenAI Realtime API in your ears (sub-second voice round-trip),
* the vision sensor watching your face,
* the embodiment driven by the model's tool calls,
* the idle micro-behaviour loop so Picoh never goes statue-still.

Usage:

    OPENAI_API_KEY=... picoh-empath

    # without hardware:
    PICOH_MOCK=1 OPENAI_API_KEY=... picoh-empath
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys

from dotenv import load_dotenv

from ..embodiment import Embodiment
from ..idle import IdleLoop
from ..realtime_client import RealtimeClient
from ..vision import VisionSensor


def _print_transcript(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


async def _amain(args) -> int:
    emb = Embodiment.connect(port=args.port, mock=args.mock)
    print(f"[empath] embodiment ready (mock={emb.mocked})", flush=True)

    # Idle loop runs from the start so Picoh "wakes up"
    idle = IdleLoop(emb).start()
    idle.set_energy(7)

    # Vision sensor (optional)
    vision: VisionSensor | None = None
    if not args.no_vision:
        try:
            vision = VisionSensor(
                camera_index=int(os.getenv("PICOH_CAMERA_INDEX", "0")),
                use_deepface=not args.no_deepface,
            ).start()
        except Exception as e:
            print(f"[empath] vision disabled: {e}", flush=True)
            vision = None

    client = RealtimeClient(
        emb,
        voice=args.voice,
        on_transcript=_print_transcript if args.transcript else None,
    )
    await client.connect()
    print("[empath] connected to Realtime API. Speak whenever you're ready.", flush=True)

    stop = asyncio.Event()

    def _on_signal(*_):
        stop.set()

    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _on_signal)
        loop.add_signal_handler(signal.SIGTERM, _on_signal)
    except NotImplementedError:  # Windows
        pass

    # Push initial "wake up" so the model commits to a body pose on turn one
    await client.say(
        "Wake up. Say a one-sentence greeting and set your eyes, base colour and head pose."
    )

    async def vision_pump():
        if not vision:
            return
        while not stop.is_set():
            await asyncio.sleep(1.0)
            if vision.state.emotion:
                # Inhibit idle so Picoh holds while the model reacts visually
                idle.inhibit(0.4)
                await client.push_user_emotion(vision.state.emotion)

    run_task = asyncio.create_task(client.run())
    vision_task = asyncio.create_task(vision_pump())

    await stop.wait()
    print("\n[empath] shutting down...", flush=True)
    for t in (run_task, vision_task):
        t.cancel()
    if vision:
        vision.stop()
    idle.stop()
    emb.reset()
    emb.close()
    return 0


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Realtime voice + vision companion for Picoh.")
    p.add_argument("--port", default=None, help="Picoh serial port; default autodetect")
    p.add_argument("--mock", action="store_true", help="Force MockPicoh (no hardware)")
    p.add_argument("--voice", default=os.getenv("PICOH_REALTIME_VOICE", "cedar"))
    p.add_argument("--no-vision", action="store_true", help="Disable camera/emotion sensing")
    p.add_argument("--no-deepface", action="store_true", help="Skip DeepFace, MP only")
    p.add_argument("--transcript", action="store_true", help="Print model transcript to stdout")
    args = p.parse_args()
    if args.mock:
        os.environ["PICOH_MOCK"] = "1"
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
