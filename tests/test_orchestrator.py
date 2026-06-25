"""Tests for the orchestrator — agent construction (the single agent builder).

Per-turn execution moved out of the BFF in the Foundry cutover (spec §11); the
turn-assembly helpers now live in ``futureself.web.agent_client`` and are tested
in ``tests/web/test_agent_client.py``. What remains here is model resolution.
"""
from __future__ import annotations

import pytest

from futureself.orchestrator import _resolve_model


def test_resolve_model_requires_env(monkeypatch):
    monkeypatch.delenv("FUTURESELF_MODEL", raising=False)
    with pytest.raises(ValueError):
        _resolve_model()


def test_resolve_model_returns_value(monkeypatch):
    monkeypatch.setenv("FUTURESELF_MODEL", "claude-opus-4-8")
    assert _resolve_model() == "claude-opus-4-8"
