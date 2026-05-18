from __future__ import annotations

import pytest

from picoh_ai.embodiment import Embodiment, MockPicoh
from picoh_ai.gestures import GESTURE_NAMES, perform


@pytest.fixture
def fast_emb(monkeypatch):
    """Use a mock backend with no time.sleep waiting inside ``.wait()``.
    Gesture impls call time.sleep directly, so we monkeypatch that too."""
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    backend = MockPicoh(verbose=False)
    return Embodiment(backend, mocked=True), backend


@pytest.mark.parametrize("name", list(GESTURE_NAMES))
def test_every_gesture_runs_without_error(fast_emb, name):
    emb, backend = fast_emb
    perform(emb, name)
    # Each gesture should have done *something* — moved a motor,
    # changed eye shape, or set a base colour.
    kinds = {op[0] for op in backend.log}
    assert kinds & {"move", "eyes", "base", "brightness"}


def test_unknown_gesture_raises(fast_emb):
    emb, _ = fast_emb
    with pytest.raises(ValueError):
        perform(emb, "moonwalk")


def test_random_idle_avoids_sleep_dance_excited(fast_emb, monkeypatch):
    """random_idle_gesture should only pick from quiet gestures."""
    from picoh_ai.gestures import random_idle_gesture, GESTURE_NAMES
    emb, backend = fast_emb
    quiet = {n for n in GESTURE_NAMES if n not in {"sleep", "dance", "excited"}}

    chosen: list[str] = []
    import random as _r
    def fake_choice(seq):
        chosen.append(seq[0])
        return seq[0]
    monkeypatch.setattr(_r, "choice", fake_choice)
    random_idle_gesture(emb)
    assert chosen[0] in quiet
