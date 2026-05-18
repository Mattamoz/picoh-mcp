from __future__ import annotations

from picoh_ai.vision import FaceState, _categorize


def test_categorize_absent():
    s = FaceState(present=False)
    assert _categorize(s) == "absent"


def test_categorize_happy_on_smile():
    s = FaceState(present=True, smile=0.9, valence=0.7, arousal=0.4)
    assert _categorize(s) == "happy"


def test_categorize_sad_on_negative_valence():
    s = FaceState(present=True, smile=0.0, valence=-0.4, arousal=0.2)
    assert _categorize(s) == "sad"


def test_categorize_angry_combines_low_v_high_a():
    s = FaceState(present=True, smile=0.0, valence=-0.6, arousal=0.8)
    assert _categorize(s) == "angry"


def test_categorize_surprised_on_open_mouth_high_arousal():
    s = FaceState(present=True, smile=0.1, valence=0.1, arousal=0.9, mouth_open=0.6)
    assert _categorize(s) == "surprised"


def test_categorize_neutral_default():
    s = FaceState(present=True, smile=0.2, valence=0.1, arousal=0.3)
    assert _categorize(s) == "neutral"
