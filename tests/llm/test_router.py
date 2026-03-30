"""Tests for the ModelRouter and routing configuration."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from futureself.llm.provider import LLMProvider
from futureself.llm.router import ModelRouter, get_router, reset_router
from futureself.llm.router_config import RouterConfig


# ---------------------------------------------------------------------------
# RouterConfig
# ---------------------------------------------------------------------------


def test_router_config_from_yaml(tmp_path: Path):
    cfg = tmp_path / "routing.yaml"
    cfg.write_text(textwrap.dedent("""\
        default_provider: openai_main
        providers:
          openai_main:
            type: openai
            model: gpt-5-nano
          claude:
            type: anthropic
            model: claude-haiku-4-5-20251001
        tasks:
          orchestrator.synthesise:
            provider: claude
    """))
    config = RouterConfig.from_yaml(cfg)
    assert config.default_provider == "openai_main"
    assert "openai_main" in config.providers
    assert "claude" in config.providers
    assert config.tasks["orchestrator.synthesise"].provider == "claude"


def test_router_config_rejects_non_mapping(tmp_path: Path):
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("- item1\n- item2\n")
    with pytest.raises(ValueError, match="YAML mapping"):
        RouterConfig.from_yaml(cfg)


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------


def test_from_single_provider():
    mock = AsyncMock(spec=LLMProvider)
    router = ModelRouter.from_single_provider(mock)
    assert router.get_provider("agent.physical_health") is mock
    assert router.get_provider("orchestrator.synthesise") is mock
    assert router.get_provider("unknown.task") is mock


def test_get_provider_returns_task_override():
    p_default = AsyncMock(spec=LLMProvider)
    p_special = AsyncMock(spec=LLMProvider)
    router = ModelRouter(
        providers={"default": p_default, "special": p_special},
        tasks={"orchestrator.synthesise": "special"},
        default_key="default",
    )
    assert router.get_provider("orchestrator.synthesise") is p_special
    assert router.get_provider("orchestrator.select_agents") is p_default


def test_get_provider_falls_back_to_default():
    p_default = AsyncMock(spec=LLMProvider)
    router = ModelRouter(
        providers={"default": p_default},
        tasks={},
        default_key="default",
    )
    assert router.get_provider("anything") is p_default


def test_from_config_validates_default_exists():
    config = RouterConfig(
        default_provider="missing",
        providers={"present": {"type": "openai", "model": "gpt-5-nano"}},
    )
    with pytest.raises(ValueError, match="missing"):
        ModelRouter.from_config(config)


def test_from_config_validates_task_references():
    config = RouterConfig(
        default_provider="main",
        providers={"main": {"type": "openai", "model": "gpt-5-nano"}},
        tasks={"orchestrator.synthesise": {"provider": "nonexistent"}},
    )
    with pytest.raises(ValueError, match="nonexistent"):
        ModelRouter.from_config(config)


# ---------------------------------------------------------------------------
# get_router singleton
# ---------------------------------------------------------------------------


def test_get_router_no_config_falls_back(monkeypatch, tmp_path: Path):
    """When no routing config exists, get_router wraps LLMProvider.get_default()."""
    reset_router()
    # Point at a non-existent config file
    monkeypatch.setenv("FUTURESELF_ROUTING_CONFIG", str(tmp_path / "nonexistent.yaml"))
    # Patch LLMProvider.get_default to return a mock
    mock = AsyncMock(spec=LLMProvider)
    monkeypatch.setattr("futureself.llm.router.LLMProvider.get_default", staticmethod(lambda: mock))

    router = get_router()
    assert router.get_provider("any.task") is mock
    reset_router()


def test_get_router_loads_yaml(monkeypatch, tmp_path: Path):
    """get_router loads from YAML when config file exists."""
    reset_router()
    cfg = tmp_path / "routing.yaml"
    cfg.write_text(textwrap.dedent("""\
        default_provider: main
        providers:
          main:
            type: openai
            model: gpt-5-nano
        tasks: {}
    """))
    monkeypatch.setenv("FUTURESELF_ROUTING_CONFIG", str(cfg))

    router = get_router()
    # Should get an OpenAIProvider instance
    provider = router.get_provider("any.task")
    assert provider.model == "gpt-5-nano"
    reset_router()
