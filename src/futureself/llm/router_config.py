"""Pydantic models for the routing configuration YAML.

The routing config lets each pipeline task (agent domain, orchestrator stage)
use a different LLM provider + model combination.  When no config file is
present the system falls back to the legacy single-provider env-var behaviour.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ProviderEntry(BaseModel):
    """A named LLM provider instance in the routing config."""

    type: str
    """Provider type: ``openai``, ``anthropic``, ``google``, ``azure_foundry``."""

    model: str
    """Model identifier, e.g. ``gpt-5-nano``, ``model-router``."""

    settings: dict[str, str] = Field(default_factory=dict)
    """Optional provider-specific settings (base_url, max_concurrent, rpm …)."""


class TaskRoute(BaseModel):
    """Per-task override pointing at a named provider."""

    provider: str
    """Key into the top-level ``providers`` dict."""


class RouterConfig(BaseModel):
    """Top-level routing configuration loaded from YAML."""

    default_provider: str
    """Key into ``providers`` used when a task has no explicit override."""

    providers: dict[str, ProviderEntry]
    """Named provider instances available for routing."""

    tasks: dict[str, TaskRoute] = Field(default_factory=dict)
    """Optional per-task overrides mapping task keys to provider names."""

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RouterConfig":
        """Load a ``RouterConfig`` from a YAML file.

        Args:
            path: Filesystem path to the routing YAML.

        Returns:
            Validated ``RouterConfig`` instance.
        """
        text = Path(path).read_text(encoding="utf-8")
        data: Any = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(f"Routing config must be a YAML mapping, got {type(data).__name__}")
        return cls.model_validate(data)
