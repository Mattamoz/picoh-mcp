"""Mirror — Picoh mirrors your face in real time. No LLM. No cloud.

This is the demo that makes people gasp. We take MediaPipe FaceMesh,
extract three quantities (yaw, pitch, mouth-open, blink), smooth each
with an EMA filter, and rewrite Picoh's motors at the camera frame rate.

A continuous valence/arousal estimate also rewrites the base RGB so the
emotional colour follows you live.

Usage:

    picoh-mirror              # mirror with valence colour
    picoh-mirror --no-colour  # mirror motion only
    PICOH_MOCK=1 picoh-mirror # without hardware (prints motor updates)
"""

from __future__ import annotations

import argparse
import os
import signal
import time

from dotenv import load_dotenv

from ..embodiment import Embodiment
from ..vision import VisionSensor


def _palette_from_valence_arousal(v: float, a: float) -> tuple[int, int, int]:
    """Cool/warm RGB driven by valence (x) + arousal (saturation)."""
    # v in [-1,1], a in [0,1]
    warmth = max(0.0, (v + 1.0) / 2.0)        # 0..1
    coolness = 1.0 - warmth
    intensity = 4 + int(a * 6)                # 4..10
    r = int(warmth * intensity)
    b = int(coolness * intensity)
    g = int(min(intensity, 2 + 4 * (1 - abs(v))))  # green peaks at neutral
    return r, g, b


class _EMA:
    def __init__(self, alpha: float = 0.25, initial: float | None = None) -> None:
        self.a = alpha
        self.v = initial
    def __call__(self, x: float) -> float:
        self.v = x if self.v is None else self.a * x + (1 - self.a) * self.v
        return self.v


def _amain(args) -> int:
    emb = Embodiment.connect(port=args.port, mock=args.mock)
    print(f"[mirror] embodiment ready (mock={emb.mocked})", flush=True)
    vs = VisionSensor(camera_index=args.camera, use_deepface=False).start()
    print("[mirror] vision started. Stand in front of the camera.", flush=True)

    yaw_f, pitch_f, mouth_f, eye_f = _EMA(0.30), _EMA(0.30), _EMA(0.55), _EMA(0.60)
    val_f, arou_f = _EMA(0.10), _EMA(0.10)
    last_colour_t = 0.0

    stop = False
    def _on_sigint(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    try:
        while not stop:
            s = vs.state
            if not s.present:
                emb.set_eyes("Eyeball")
                time.sleep(0.1)
                continue

            # Map (-1,1) head pose ranges to picoh's (0,10) world.
            yaw = yaw_f(5 + 5 * (-s.yaw))      # mirror: user turn left → picoh turn right
            pitch = pitch_f(5 + 5 * (-s.pitch))
            mouth = mouth_f(10 * min(1.0, s.mouth_open))
            # LIDBLINK: 10=open, 0=closed → mirror user's eye_open directly.
            eye   = eye_f(10 * s.eye_open)

            emb.move("HEADTURN",  yaw,  10)
            emb.move("HEADNOD",   pitch, 8)
            emb.move("BOTTOMLIP", mouth, 10)
            emb.move("LIDBLINK",  eye,   10)

            # roll-into-tilt (slight)
            emb.move("EYETILT", 5 + 3 * s.roll, 6)

            if not args.no_colour and time.time() - last_colour_t > 0.12:
                last_colour_t = time.time()
                r, g, b = _palette_from_valence_arousal(val_f(s.valence), arou_f(s.arousal))
                emb.base_colour(r, g, b)

            time.sleep(0.03)
    finally:
        vs.stop()
        emb.reset()
        emb.close()
    return 0


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Real-time face mirror for Picoh.")
    p.add_argument("--port", default=None)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--camera", type=int, default=int(os.getenv("PICOH_CAMERA_INDEX", "0")))
    p.add_argument("--no-colour", action="store_true", help="Disable valence→RGB mapping")
    args = p.parse_args()
    if args.mock:
        os.environ["PICOH_MOCK"] = "1"
    return _amain(args)


if __name__ == "__main__":
    raise SystemExit(main())
