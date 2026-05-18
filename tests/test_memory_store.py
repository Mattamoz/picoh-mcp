from __future__ import annotations

from pathlib import Path

from picoh_ai.memory_store import MemoryStore


def test_roundtrip(tmp_path: Path):
    p = tmp_path / "m.json"
    m = MemoryStore(p)
    m.add_event("face", "Saw a face")
    m.remember_fact("name", "Chris")
    m.mood = "playful"
    m.energy = 7.5
    m.remember_line("Hello there!")

    # Reload from disk
    m2 = MemoryStore(p)
    assert m2.recent(5)[-1]["summary"] == "Saw a face"
    assert m2.facts() == {"name": "Chris"}
    assert m2.mood == "playful"
    assert abs(m2.energy - 7.5) < 1e-6
    assert m2.saw_line("Hello there!") is True
    assert m2.saw_line("Never said") is False


def test_event_log_bounded(tmp_path: Path):
    m = MemoryStore(tmp_path / "m.json", maxlen=10)
    for i in range(50):
        m.add_event("tick", f"event {i}")
    events = m.recent(100)
    assert len(events) == 10
    assert events[0]["summary"] == "event 40"
    assert events[-1]["summary"] == "event 49"
