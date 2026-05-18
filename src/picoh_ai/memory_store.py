"""Persistent rolling memory for the Companion daemon.

JSON-on-disk so we have zero deps and can inspect by hand. Memory is a
bounded list — we keep the most recent ``maxlen`` events and a tiny set of
sticky facts (e.g. "the user's name is Chris", "they prefer it quiet
mornings").

Not a vector store and not trying to be. The Companion's cognition prompt
is small; we just need the last ~100 events and a few facts.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Event:
    ts: float
    kind: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Doc:
    facts: dict[str, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    mood: str = "curious"
    energy: float = 6.0
    last_lines: list[str] = field(default_factory=list)


class MemoryStore:
    def __init__(self, path: str | os.PathLike = "companion_memory.json", maxlen: int = 200) -> None:
        self.path = Path(path)
        self.maxlen = maxlen
        self._lock = threading.RLock()
        self._doc = self._load()

    def _load(self) -> _Doc:
        if not self.path.exists():
            return _Doc()
        try:
            raw = json.loads(self.path.read_text())
            doc = _Doc(
                facts=raw.get("facts", {}),
                events=raw.get("events", []),
                mood=raw.get("mood", "curious"),
                energy=float(raw.get("energy", 6.0)),
                last_lines=raw.get("last_lines", []),
            )
        except Exception:
            doc = _Doc()
        return doc

    def _flush(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self._doc), indent=2))
        tmp.replace(self.path)

    # ----- public API ---------------------------------------------------- #
    def add_event(self, kind: str, summary: str, **data: Any) -> None:
        with self._lock:
            self._doc.events.append(asdict(Event(time.time(), kind, summary, data)))
            self._doc.events = self._doc.events[-self.maxlen:]
            self._flush()

    def remember_fact(self, key: str, value: str) -> None:
        with self._lock:
            self._doc.facts[key] = value
            self._flush()

    def recent(self, n: int = 20) -> list[dict]:
        with self._lock:
            return list(self._doc.events[-n:])

    def facts(self) -> dict[str, str]:
        with self._lock:
            return dict(self._doc.facts)

    @property
    def mood(self) -> str:
        return self._doc.mood

    @mood.setter
    def mood(self, m: str) -> None:
        with self._lock:
            self._doc.mood = m
            self._flush()

    @property
    def energy(self) -> float:
        return self._doc.energy

    @energy.setter
    def energy(self, e: float) -> None:
        with self._lock:
            self._doc.energy = float(e)
            self._flush()

    def saw_line(self, line: str) -> bool:
        """Return True if we've said exactly this in the last 20 lines."""
        with self._lock:
            return line in self._doc.last_lines

    def remember_line(self, line: str) -> None:
        with self._lock:
            if not line:
                return
            self._doc.last_lines.append(line)
            self._doc.last_lines = self._doc.last_lines[-20:]
            self._flush()
