from __future__ import annotations

import json

import pytest

from picoh_ai.embodiment import Embodiment, MockPicoh
from picoh_ai.tools import CATALOG, CATALOG_BY_NAME, dispatch, openai_realtime_tools


@pytest.fixture
def emb_pair(monkeypatch):
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    b = MockPicoh(verbose=False)
    return Embodiment(b, mocked=True), b


def test_catalog_is_unique_and_named():
    names = [t.name for t in CATALOG]
    assert len(names) == len(set(names)), "duplicate tool name"
    assert "set_eyes" in CATALOG_BY_NAME
    assert "gesture" in CATALOG_BY_NAME


def test_openai_shape_is_valid():
    tools = openai_realtime_tools()
    for t in tools:
        assert t["type"] == "function"
        assert t["name"]
        assert "parameters" in t and isinstance(t["parameters"], dict)
        # Realtime API expects JSON schema-ish parameters with `type: object`
        assert t["parameters"]["type"] == "object"


def test_schemas_serialize_as_json():
    # If a tool schema can't go through json, the Realtime session.update
    # call would fail at runtime.
    json.dumps(openai_realtime_tools())


def test_dispatch_set_eyes(emb_pair):
    emb, b = emb_pair
    out = dispatch(emb, "set_eyes", {"left": "Heart", "right": "Heart"})
    assert out == {"ok": True}
    assert b.state.eyes == ("Heart", "Heart")


def test_dispatch_base_colour(emb_pair):
    emb, b = emb_pair
    dispatch(emb, "base_colour", {"r": 10, "g": 0, "b": 5})
    assert b.state.base == (10.0, 0.0, 5.0)


def test_dispatch_gesture(emb_pair):
    emb, b = emb_pair
    dispatch(emb, "gesture", {"name": "nod_yes"})
    assert any(op[0] == "move" for op in b.log)


def test_dispatch_unknown_tool_returns_error(emb_pair):
    emb, _ = emb_pair
    out = dispatch(emb, "make_coffee", {})
    assert out.get("ok") is False
    assert "make_coffee" in out["error"]


def test_dispatch_read_sensor(emb_pair):
    emb, _ = emb_pair
    out = dispatch(emb, "read_sensor", {"pin": 0})
    assert "value" in out
