from __future__ import annotations

import pytest

from picoh_ai.embodiment import EYE_SHAPES, Embodiment


def test_connect_falls_back_to_mock_when_forced(monkeypatch):
    monkeypatch.setenv("PICOH_MOCK", "1")
    e = Embodiment.connect()
    assert e.mocked is True
    e.close()


def test_move_clamps_positions(emb, mock_backend):
    emb.move("HEADNOD", 99, 99)
    emb.move("HEADNOD", -10, -10)
    # State stays inside 0..10
    assert 0.0 <= mock_backend.state.motors["HEADNOD"] <= 10.0
    # log shows clamped values
    args = [op for op in mock_backend.log if op[0] == "move"]
    assert all(0 <= a[1][1] <= 10 and 0 <= a[1][2] <= 10 for a in args)


def test_unknown_motor_raises(emb):
    with pytest.raises(ValueError):
        emb.move("EARWIGGLE", 5)


def test_unknown_eye_shape_raises(emb):
    with pytest.raises(ValueError):
        emb.set_eyes("Banana")


def test_eye_shape_accepts_all_known(emb, mock_backend):
    for shape in EYE_SHAPES:
        emb.set_eyes(shape)
    assert mock_backend.state.eyes == (EYE_SHAPES[-1], EYE_SHAPES[-1])


def test_base_colour_clamps(emb, mock_backend):
    emb.base_colour(99, -1, 5.5)
    r, g, b = mock_backend.state.base
    assert (r, g, b) == (10.0, 0.0, 5.5)


def test_head_pose_partial_args_only_set_provided(emb, mock_backend):
    before = dict(mock_backend.state.motors)
    emb.head_pose(turn=8)
    assert mock_backend.state.motors["HEADTURN"] == 8.0
    assert mock_backend.state.motors["HEADNOD"] == before["HEADNOD"]


def test_look_writes_eye_motors(emb, mock_backend):
    emb.look(2, 8, speed=10)
    assert mock_backend.state.motors["EYETURN"] == 2.0
    # EYETILT is clamped to [3.5, 6.5] because outside that range the pupil
    # "looks off the edge" of the multi-frame eye-shape hex and the matrix
    # renders as a horizontal line.
    assert mock_backend.state.motors["EYETILT"] == 6.5


def test_look_clamps_tilt_low(emb, mock_backend):
    emb.look(5, 0, speed=10)
    assert mock_backend.state.motors["EYETILT"] == 3.5


def test_set_eyes_recenters_pupil_by_default(emb, mock_backend):
    # First push pupil off-centre…
    emb.look(1, 8, speed=10)
    assert mock_backend.state.motors["EYETURN"] == 1.0
    # …then setting an eye shape should snap pupil back to centre so the
    # main sub-frame of the multi-frame hex is what's drawn.
    emb.set_eyes("Heart")
    assert mock_backend.state.motors["EYETURN"] == 5.0
    assert mock_backend.state.motors["EYETILT"] == 5.0


def test_set_eyes_recenter_false_preserves_pupil(emb, mock_backend):
    emb.look(2, 6, speed=10)
    emb.set_eyes("Heart", recenter=False)
    assert mock_backend.state.motors["EYETURN"] == 2.0


def test_context_manager_resets_and_closes(mock_backend):
    e = Embodiment(mock_backend, mocked=True)
    e.move("HEADNOD", 9)
    with e:
        e.move("HEADTURN", 1)
    ops = [op[0] for op in mock_backend.log]
    assert "reset" in ops
    assert "close" in ops
