"""Shared pytest fixtures. All tests run against the MockPicoh — no
hardware, no network, no LLM keys required."""

from __future__ import annotations

import os

import pytest

# Force mock for the entire test session.
os.environ["PICOH_MOCK"] = "1"

from picoh_ai.embodiment import Embodiment, MockPicoh  # noqa: E402


@pytest.fixture
def mock_backend() -> MockPicoh:
    return MockPicoh(verbose=False)


@pytest.fixture
def emb(mock_backend: MockPicoh) -> Embodiment:
    return Embodiment(mock_backend, mocked=True)
