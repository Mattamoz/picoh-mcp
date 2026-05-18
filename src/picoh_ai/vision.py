"""Vision sensors: MediaPipe face mesh (cheap, fast, always on) and
optionally DeepFace (heavier, real emotion classes).

Two layers:

``FaceState``     a snapshot dataclass with smile/valence/arousal/head pose
                  and the dominant emotion label.

``VisionSensor``  a daemon thread that keeps ``.state`` fresh. Lazy
                  imports — apps that don't need vision pay zero cost.

The valence/arousal estimate is computed from face landmarks alone (smile
curve + brow distance + mouth opening) so it works offline at 30 fps on a
CPU. DeepFace is only consulted at ~1 Hz to pin a categorical emotion,
because that's where the latency hides.
"""

from __future__ import annotations

import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)


def _ensure_face_landmarker_model() -> Path:
    """Download MediaPipe's FaceLandmarker model on first use."""
    cache = Path(os.environ.get("PICOH_MODEL_CACHE", Path.home() / ".cache" / "picoh-ai"))
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / "face_landmarker.task"
    if not target.exists():
        print(f"[vision] downloading FaceLandmarker model → {target}", flush=True)
        urllib.request.urlretrieve(_MODEL_URL, target)
    return target


# Distinct labels we emit for the LLM. Keep small — pick from these even
# if DeepFace returns something else, to keep the prompt clean.
EMOTIONS = ("neutral", "happy", "surprised", "sad", "angry", "confused", "absent")


@dataclass
class FaceState:
    present: bool = False
    timestamp: float = 0.0
    # 0..1 smile score
    smile: float = 0.0
    # valence (-1..1) and arousal (0..1), derived from landmarks
    valence: float = 0.0
    arousal: float = 0.0
    # head pose (yaw, pitch, roll), all -1..1 roughly
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    # mouth open 0..1, eye openness 0..1
    mouth_open: float = 0.0
    eye_open: float = 1.0
    # categorical
    emotion: str = "absent"
    # optional raw size for debugging
    face_box: tuple[int, int, int, int] | None = None


def _categorize(state: FaceState) -> str:
    if not state.present:
        return "absent"
    if state.smile > 0.55:
        return "happy"
    if state.valence < -0.35 and state.arousal > 0.5:
        return "angry"
    if state.valence < -0.25:
        return "sad"
    if state.arousal > 0.7 and state.mouth_open > 0.4:
        return "surprised"
    if abs(state.roll) > 0.35:
        return "confused"
    return "neutral"


class VisionSensor:
    """Run MediaPipe in a background thread. Optionally cross-check with DeepFace.

    Usage:
        with VisionSensor(use_deepface=False).start() as vs:
            print(vs.state.emotion)
    """

    def __init__(
        self,
        camera_index: int = 0,
        use_deepface: bool = False,
        deepface_interval_s: float = 1.5,
    ) -> None:
        self.camera_index = camera_index
        self.use_deepface = use_deepface
        self.deepface_interval_s = deepface_interval_s
        self.state = FaceState()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_deepface = 0.0
        self._listeners: list = []

    # ----- subscriptions ------------------------------------------------- #
    def on_emotion_change(self, callback) -> None:
        """Register a callback ``cb(new_emotion: str, state: FaceState)``."""
        self._listeners.append(callback)

    # ----- lifecycle ----------------------------------------------------- #
    def start(self) -> "VisionSensor":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="vision")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "VisionSensor":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # ----- worker -------------------------------------------------------- #
    def _run(self) -> None:
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mptp
            from mediapipe.tasks.python import vision as mpv
        except Exception as e:
            print(f"[vision] disabled — missing deps: {e}", flush=True)
            return

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print(f"[vision] could not open camera index {self.camera_index}", flush=True)
            return

        model_path = _ensure_face_landmarker_model()
        landmarker = mpv.FaceLandmarker.create_from_options(
            mpv.FaceLandmarkerOptions(
                base_options=mptp.BaseOptions(model_asset_path=str(model_path)),
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_face_blendshapes=True,  # gives us smile/frown/jawOpen etc.
                running_mode=mpv.RunningMode.VIDEO,
            )
        )
        last_emotion = self.state.emotion
        t0 = time.time()

        frame_n = 0
        face_n = 0
        last_diag = time.time()
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                frame_n += 1
                # Periodic diagnostic: are frames flowing? are faces detected?
                if time.time() - last_diag > 3.0:
                    print(
                        f"[vision diag] {frame_n} frames, {face_n} with face, "
                        f"present={self.state.present} emotion={self.state.emotion}",
                        flush=True,
                    )
                    last_diag = time.time()
                try:
                    h, w = frame.shape[:2]
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    ts_ms = int((time.time() - t0) * 1000)
                    res = landmarker.detect_for_video(mp_image, ts_ms)
                except Exception as e:
                    if frame_n < 10 or frame_n % 50 == 0:
                        print(f"[vision] detect_for_video err frame {frame_n}: {e}", flush=True)
                    time.sleep(0.05)
                    continue

                if not res.face_landmarks:
                    self.state = FaceState(present=False, timestamp=time.time(), emotion="absent")
                else:
                    face_n += 1
                    blends = res.face_blendshapes[0] if res.face_blendshapes else None
                    self.state = self._landmarks_to_state(
                        res.face_landmarks[0], w, h, blendshapes=blends
                    )

                # ~1 Hz: ask DeepFace for a categorical opinion (heavy)
                if (
                    self.use_deepface
                    and self.state.present
                    and time.time() - self._last_deepface > self.deepface_interval_s
                ):
                    self._last_deepface = time.time()
                    threading.Thread(target=self._deepface_query, args=(rgb,), daemon=True).start()

                # categorical fallback derived from landmarks
                cat = _categorize(self.state)
                if not self.state.emotion or self.state.emotion == "absent":
                    self.state.emotion = cat

                if self.state.emotion != last_emotion:
                    last_emotion = self.state.emotion
                    for cb in list(self._listeners):
                        try:
                            cb(self.state.emotion, self.state)
                        except Exception:
                            pass
                time.sleep(0.03)  # ~30 fps cap
        finally:
            cap.release()

    # ----- helpers ------------------------------------------------------- #
    @staticmethod
    def _landmarks_to_state(lm, w: int, h: int, *, blendshapes=None) -> FaceState:
        # Indices follow MediaPipe FaceMesh canonical model.
        # Pairs picked for robust low-noise signal.
        def p(i):
            return (lm[i].x, lm[i].y)

        def dist(a, b):
            return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

        nose_tip, chin = p(1), p(152)
        left_eye_outer, right_eye_outer = p(33), p(263)
        left_mouth, right_mouth = p(61), p(291)
        upper_lip, lower_lip = p(13), p(14)
        right_eyelid_top, right_eyelid_bot = p(159), p(145)
        left_brow, right_brow = p(70), p(300)

        face_w = dist(left_eye_outer, right_eye_outer) + 1e-6
        face_h = dist(nose_tip, chin) + 1e-6

        # Smile: how much the mouth corners are *raised* relative to lip line
        mouth_line_y = (upper_lip[1] + lower_lip[1]) / 2
        corner_raise = ((mouth_line_y - left_mouth[1]) + (mouth_line_y - right_mouth[1])) / 2
        smile = max(0.0, min(1.0, corner_raise / (face_h * 0.10)))

        mouth_open = max(0.0, min(1.0, dist(upper_lip, lower_lip) / (face_h * 0.30)))
        eye_open = max(0.0, min(1.0, dist(right_eyelid_top, right_eyelid_bot) / (face_h * 0.10)))
        brow_dist = dist(left_brow, right_brow) / face_w  # ~0.5..0.8 typically

        # Yaw: nose x relative to face center; pitch: nose y relative to mid; roll: eyes line tilt
        center_x = (left_eye_outer[0] + right_eye_outer[0]) / 2
        center_y = (left_eye_outer[1] + right_eye_outer[1]) / 2
        yaw = (nose_tip[0] - center_x) / (face_w / 2)
        pitch = (nose_tip[1] - center_y) / (face_h / 2)
        roll = (right_eye_outer[1] - left_eye_outer[1]) / (face_w + 1e-6)

        valence = smile - max(0.0, 0.65 - brow_dist) * 1.5
        valence = max(-1.0, min(1.0, valence))
        arousal = max(0.0, min(1.0, mouth_open * 0.7 + (1 - eye_open) * 0.3 + abs(yaw) * 0.2))

        # If MediaPipe gave us blendshapes, use them for the emotion-shaped
        # signals — far more reliable than landmark-derived heuristics.
        # Blendshape names: see the FaceLandmarker model card. Values 0..1.
        emotion = "neutral"
        if blendshapes is not None:
            bs = {c.category_name: c.score for c in blendshapes}
            smile_bs = (bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2
            frown_bs = (bs.get("mouthFrownLeft", 0) + bs.get("mouthFrownRight", 0)) / 2
            jaw_open = bs.get("jawOpen", 0)
            brow_down = (bs.get("browDownLeft", 0) + bs.get("browDownRight", 0)) / 2
            brow_up = bs.get("browInnerUp", 0)
            mouth_pucker = bs.get("mouthPucker", 0)
            eye_open_bs = 1 - max(bs.get("eyeBlinkLeft", 0), bs.get("eyeBlinkRight", 0))

            # Replace landmark heuristics with blendshape values
            smile = smile_bs
            valence = smile_bs - frown_bs - 0.5 * brow_down
            valence = max(-1.0, min(1.0, valence))
            arousal = max(0.0, min(1.0, jaw_open * 0.8 + brow_up * 0.4 + brow_down * 0.4))
            mouth_open = jaw_open
            eye_open = eye_open_bs

            # Categorical pick directly from blendshapes — much more robust
            if smile_bs > 0.35:
                emotion = "happy"
            elif jaw_open > 0.40 and brow_up > 0.20:
                emotion = "surprised"
            elif frown_bs > 0.15 or (valence < -0.20 and brow_down < 0.15):
                emotion = "sad"
            elif brow_down > 0.35 and smile_bs < 0.1:
                emotion = "angry"
            elif mouth_pucker > 0.45:
                emotion = "confused"
            else:
                emotion = "neutral"

        return FaceState(
            present=True,
            timestamp=time.time(),
            smile=smile,
            valence=valence,
            arousal=arousal,
            yaw=max(-1.0, min(1.0, yaw)),
            pitch=max(-1.0, min(1.0, pitch)),
            roll=max(-1.0, min(1.0, roll)),
            mouth_open=mouth_open,
            eye_open=eye_open,
            emotion=emotion,
        )

    def _deepface_query(self, rgb_frame) -> None:
        try:
            from deepface import DeepFace
        except Exception:
            self.use_deepface = False
            return
        try:
            r = DeepFace.analyze(
                rgb_frame, actions=["emotion"], enforce_detection=False, silent=True
            )
            label = (r[0] if isinstance(r, list) else r)["dominant_emotion"]
            mapped = {
                "happy": "happy",
                "sad": "sad",
                "angry": "angry",
                "surprise": "surprised",
                "fear": "surprised",
                "disgust": "angry",
                "neutral": "neutral",
            }.get(label, "neutral")
            self.state.emotion = mapped
        except Exception:
            pass
