"""Model router — routes each pipeline task to its configured LLM provider.

The ``ModelRouter`` loads a routing YAML (see ``router_config.py``) and
instantiates one ``LLMProvider`` per named entry.  Callers ask for a provider
by *task key* (e.g. ``"agent.physical_health"``, ``"orchestrator.synthesise"``);
tasks without an explicit override receive the default provider.

When no routing config exists the router wraps a single provider created via
``LLMProvider.get_default()``, preserving the legacy env-var-only behaviour.
"""
from __future__ import annotations

import os
from pathlib import Path

from futureself.llm.provider import LLMProvider
from futureself.llm.router_config import RouterConfig

# Project-root-relative default config path.
_DEFAULT_CONFIG = Path(__file__).parent.parent.parent.parent / "config" / "routing.yaml"

_singleton: ModelRouter | None = None


def _build_provider(provider_type: str, model: str, settings: dict[str, str]) -> LLMProvider:
    """Instantiate a concrete ``LLMProvider`` from config values."""
    if provider_type == "openai":
        from futureself.llm.openai_provider import OpenAIProvider  # noqa: PLC0415

        return OpenAIProvider(
            model=model,
            base_url=settings.get("base_url"),
            max_concurrent=int(settings["max_concurrent"]) if "max_concurrent" in settings else None,
        )

    if provider_type in ("anthropic", "claude"):
        from futureself.llm.anthropic_provider import AnthropicProvider  # noqa: PLC0415

        return AnthropicProvider(model=model)

    if provider_type in ("google", "gemini"):
        from futureself.llm.google_provider import GoogleProvider  # noqa: PLC0415

        return GoogleProvider(model=model)

    if provider_type in ("azure_foundry", "azure"):
        from futureself.llm.azure_foundry_provider import AzureFoundryProvider  # noqa: PLC0415

        return AzureFoundryProvider(
            model=model,
            endpoint=settings.get("endpoint"),
            api_key=settings.get("api_key"),
            max_concurrent=int(settings["max_concurrent"]) if "max_concurrent" in settings else None,
        )

    raise ValueError(
        f"Unknown provider type in routing config: {provider_type!r}. "
        "Supported: openai, anthropic, google, azure_foundry."
    )


class ModelRouter:
    """Registry that maps pipeline task keys to ``LLMProvider`` instances."""

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        tasks: dict[str, str],
        default_key: str,
    ) -> None:
        self._providers = providers
        self._tasks = tasks  # task_key -> provider_name
        self._default_key = default_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_provider(self, task: str) -> LLMProvider:
        """Return the ``LLMProvider`` for *task*, falling back to the default.

        Args:
            task: Pipeline task key, e.g. ``"agent.financial"`` or
                ``"orchestrator.detect_conflicts"``.
        """
        provider_key = self._tasks.get(task, self._default_key)
        return self._providers[provider_key]

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: RouterConfig) -> "ModelRouter":
        """Build a router from a validated ``RouterConfig``."""
        if config.default_provider not in config.providers:
            raise ValueError(
                f"default_provider {config.default_provider!r} "
                f"not found in providers: {list(config.providers)}"
            )

        providers: dict[str, LLMProvider] = {}
        for name, entry in config.providers.items():
            providers[name] = _build_provider(entry.type, entry.model, entry.settings)

        tasks: dict[str, str] = {}
        for task_key, route in config.tasks.items():
            if route.provider not in providers:
                raise ValueError(
                    f"Task {task_key!r} references unknown provider {route.provider!r}. "
                    f"Available: {list(providers)}"
                )
            tasks[task_key] = route.provider

        return cls(providers=providers, tasks=tasks, default_key=config.default_provider)

    @classmethod
    def from_single_provider(cls, provider: LLMProvider) -> "ModelRouter":
        """Wrap a single ``LLMProvider`` so it serves all tasks.

        Used for backward compatibility (tests that pass ``provider=...``
        directly) and as the no-config fallback.
        """
        return cls(
            providers={"_default": provider},
            tasks={},
            default_key="_default",
        )


def get_router() -> ModelRouter:
    """Return the module-level ``ModelRouter`` singleton.

    On first call the router is built from the routing YAML pointed to by
    ``FUTURESELF_ROUTING_CONFIG`` (env var) or the project default
    ``config/routing.yaml``.  If no config file is found, falls back to
    ``LLMProvider.get_default()`` wrapped in a single-provider router.
    """
    global _singleton  # noqa: PLW0603
    if _singleton is not None:
        return _singleton

    config_path = os.getenv("FUTURESELF_ROUTING_CONFIG") or str(_DEFAULT_CONFIG)

    path = Path(config_path)
    if path.is_file():
        config = RouterConfig.from_yaml(path)
        _singleton = ModelRouter.from_config(config)
    else:
        _singleton = ModelRouter.from_single_provider(LLMProvider.get_default())

    return _singleton


def reset_router() -> None:
    """Clear the cached singleton (useful in tests)."""
    global _singleton  # noqa: PLW0603
    _singleton = None
