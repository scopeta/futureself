"""Orchestrator — builds the Future Self Synthesizer agent.

This module is the **single source of truth for agent construction**. The agent
is run in exactly one place: the Foundry Hosted Agent (``main.py``, an Azure AI
Responses host) built via :func:`build_agent`. The browser-facing BFF no longer
runs the agent in-process — it calls the deployed hosted agent over HTTP (see
``web/agent_client``) and owns the Postgres-backed Blueprint. Keeping one
builder prevents drift in client selection, skills wiring, or prompt.

Two client backends, selected from environment variables:

1. **Anthropic direct** — ``ANTHROPIC_API_KEY`` set (and no Foundry endpoint).
   Uses ``agent_framework_anthropic.AnthropicClient``.

2. **Azure AI Foundry** — ``AZURE_FOUNDRY_ENDPOINT`` set.
   Uses ``agent_framework_foundry.FoundryChatClient`` — model-agnostic.
   Supports any model deployed to Foundry (GPT, Claude, Grok, etc.).

Model is configured via ``FUTURESELF_MODEL`` (required; no default).
Skills are lazy-loaded via MAF's ``SkillsProvider``.
"""
from __future__ import annotations

import os
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent / "skills"
_ORCHESTRATOR_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "orchestrator.md"


def _resolve_model() -> str:
    """Return the model name from the ``FUTURESELF_MODEL`` environment variable.

    Raises:
        ValueError: If the variable is not set.
    """
    model = os.getenv("FUTURESELF_MODEL", "")
    if not model:
        raise ValueError(
            "FUTURESELF_MODEL is required. Set it to the model name for your "
            "chosen provider (e.g. 'claude-opus-4-8', 'claude-sonnet-4-6', 'gpt-4o')."
        )
    return model


def _load_orchestrator_prompt() -> str:
    return _ORCHESTRATOR_PROMPT_PATH.read_text(encoding="utf-8")


def build_agent(model: str | None = None) -> object:
    """Build and return the MAF Agent with SkillsProvider.

    Client selection:
    - ``AZURE_FOUNDRY_ENDPOINT`` set → ``FoundryChatClient`` (model-agnostic,
      supports any Foundry-deployed model, Entra ID auth).
    - ``ANTHROPIC_API_KEY`` set → ``AnthropicClient`` (Anthropic direct API).

    Both are MAF-native ``BaseChatClient`` implementations — the same
    ``Agent`` + ``SkillsProvider`` pipeline applies in both cases.

    Args:
        model: Model deployment name. Defaults to ``FUTURESELF_MODEL`` via
            :func:`_resolve_model` when not supplied.

    Raises:
        ValueError: If neither provider env var is configured, or if the model
            cannot be resolved.
        ImportError: If required MAF client packages are not installed.
    """
    if model is None:
        model = _resolve_model()
    # Lazy imports — SDK packages may not be installed in all environments
    from agent_framework import Agent, SkillsProvider  # noqa: PLC0415

    skills_provider = SkillsProvider.from_paths(_SKILLS_DIR)

    endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "")
    if endpoint:
        from agent_framework_foundry import FoundryChatClient  # noqa: PLC0415
        from azure.identity import DefaultAzureCredential  # noqa: PLC0415

        client = FoundryChatClient(
            project_endpoint=endpoint,
            model=model,
            credential=DefaultAzureCredential(),
        )
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "No LLM provider configured. Set AZURE_FOUNDRY_ENDPOINT (Foundry) "
                "or ANTHROPIC_API_KEY (Anthropic direct)."
            )
        from agent_framework_anthropic import AnthropicClient  # noqa: PLC0415

        client = AnthropicClient(api_key=api_key, model=model)

    return Agent(
        client,
        instructions=_load_orchestrator_prompt(),
        name="FutureSelf",
        context_providers=[skills_provider],
    )
