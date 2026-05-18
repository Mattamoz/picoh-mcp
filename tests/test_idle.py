from __future__ import annotations

import time

from picoh_ai.embodiment import Embodiment, MockPicoh
from picoh_ai.idle import IdleLoop, IdlePersona


def test_idle_persona_scales_with_energy():
    p = IdlePersona()
    low, high = p.scale(0), p.scale(10)
    # Higher energy → shorter intervals between blinks
    assert high.blink_min_s < low.blink_min_s
    assert high.breath_amp >= low.breath_amp


def test_idle_loop_emits_moves_within_a_second():
    backend = MockPicoh(verbose=False)
    emb = Embodiment(backend, mocked=True)
    loop = IdleLoop(emb).start()
    try:
        time.sleep(1.2)
    finally:
        loop.stop()
    move_ops = [op for op in backend.log if op[0] == "move"]
    assert move_ops, "expected at least one motor move from idle loop"


def test_inhibit_blocks_moves_for_window():
    backend = MockPicoh(verbose=False)
    emb = Embodiment(backend, mocked=True)
    loop = IdleLoop(emb).start()
    loop.inhibit(0.5)
    time.sleep(0.2)
    before = len(backend.log)
    time.sleep(0.2)  # still inhibited (total < 0.5s)
    after_inhibit = len(backend.log)
    # During the inhibit window, the loop should not have added new ops
    assert after_inhibit - before == 0
    time.sleep(0.7)  # past the inhibit window — should fire again
    loop.stop()
    assert len(backend.log) > after_inhibit
