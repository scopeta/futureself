"""Orchestrator — the Future Self Synthesizer.

Uses Microsoft Agent Framework (MAF) for all execution paths, providing
SkillsProvider (lazy skill loading), OpenTelemetry tracing, and session
management throughout.

Two client backends, selected from environment variables:

1. **Anthropic direct** — ``ANTHROPIC_API_KEY`` set (and no Foundry endpoint).
   Uses ``agent_framework_anthropic.AnthropicClient``.
   Runs via MAF Agent Services for cloud deployment.

2. **Azure AI Foundry** — ``AZURE_FOUNDRY_ENDPOINT`` set.
   Uses ``agent_framework_foundry.FoundryChatClient`` — model-agnostic.
   Supports any model deployed to Foundry (GPT, Claude, Grok, etc.).
   Enables MAF + Foundry Agent Service integration and Application Insights.

Model is configured via ``FUTURESELF_MODEL`` (required; no default).
Skills are lazy-loaded via MAF's ``SkillsProvider``.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from futureself.schemas import ConversationTurn, LLMCallTrace, OrchestratorResult, UserBlueprint

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
            "chosen provider (e.g. 'claude-opus-4-6', 'claude-sonnet-4-5', 'gpt-4o')."
        )
    return model


def _load_orchestrator_prompt() -> str:
    return _ORCHESTRATOR_PROMPT_PATH.read_text(encoding="utf-8")


def _build_agent(model: str) -> object:
    """Build and return the MAF Agent with SkillsProvider.

    Client selection:
    - ``AZURE_FOUNDRY_ENDPOINT`` set → ``FoundryChatClient`` (model-agnostic,
      supports any Foundry-deployed model, Entra ID auth).
    - ``ANTHROPIC_API_KEY`` set → ``AnthropicClient`` (Anthropic direct API).

    Both are MAF-native ``BaseChatClient`` implementations — the same
    ``Agent`` + ``SkillsProvider`` pipeline applies in both cases.

    Args:
        model: Model deployment name (from ``FUTURESELF_MODEL``).

    Raises:
        ValueError: If neither provider env var is configured.
        ImportError: If required MAF client packages are not installed.
    """
    # Lazy imports — SDK packages may not be installed in all environments
    from agent_framework import Agent, SkillsProvider  # noqa: PLC0415

    skills_provider = SkillsProvider(skill_paths=_SKILLS_DIR)

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

        client = AnthropicClient(api_key=api_key, model_id=model)

    return Agent(
        client,
        instructions=_load_orchestrator_prompt(),
        name="FutureSelf",
        context_providers=[skills_provider],
    )


def _build_user_context(blueprint: UserBlueprint, user_message: str) -> str:
    """Render the per-turn user context block."""
    history_lines = [
        f"{turn.role.upper()}: {turn.content}"
        for turn in blueprint.conversation_history[-10:]
    ]

    facts_section = (
        "\n\nKNOWN FACTS ABOUT USER:\n" + "\n".join(f"- {f}" for f in blueprint.inferred_facts)
        if blueprint.inferred_facts
        else ""
    )
    history_section = (
        "\n\nCONVERSATION HISTORY:\n" + "\n".join(history_lines)
        if history_lines
        else ""
    )

    return (
        f"USER PROFILE:\n{blueprint.model_dump_json(indent=2)}"
        f"{facts_section}"
        f"{history_section}"
        f"\n\nUSER MESSAGE:\n{user_message}"
    )


def _extract_facts_simple(reply: str, blueprint: UserBlueprint) -> list[str]:
    """Extract new facts from the reply without an LLM call.

    Looks for common patterns: age mentions, location. Returns only facts not
    already present in the blueprint.
    """
    existing = set(blueprint.inferred_facts)
    candidates: list[str] = []

    for m in re.finditer(r"\bI(?:'m| am) (\d{2,3})(?: years? old)?\b", reply, re.I):
        candidates.append(f"User is {m.group(1)} years old")

    for m in re.finditer(r"\b(?:I live|based|living) in ([A-Z][a-zA-Z\s,]+?)(?:\.|,|\n|$)", reply):
        candidates.append(f"User lives in {m.group(1).strip()}")

    return [f for f in candidates if f not in existing]


async def run_turn(
    user_blueprint: UserBlueprint,
    user_message: str,
    *,
    _agent: object | None = None,
    _model: str | None = None,
) -> OrchestratorResult:
    """Run one turn of the Future Self agent via MAF.

    Args:
        user_blueprint: Current user profile (treated as immutable input).
        user_message: The user's raw message.
        _agent: Injected MAF Agent instance (testing — skips env-var lookup).
        _model: Injected model name (testing — skips ``FUTURESELF_MODEL`` lookup).

    Returns:
        OrchestratorResult with user_facing_reply, updated_blueprint, llm_traces.
    """
    model = _model if _model is not None else _resolve_model()
    agent = _agent if _agent is not None else _build_agent(model)

    user_ctx = _build_user_context(user_blueprint, user_message)

    t0 = time.monotonic()
    session = agent.create_session()  # sync
    result = await agent.run(user_ctx, session=session)
    latency_ms = (time.monotonic() - t0) * 1000

    user_reply: str = result.text or ""

    new_facts = _extract_facts_simple(user_reply, user_blueprint)
    existing = set(user_blueprint.inferred_facts)

    updated_blueprint = user_blueprint.model_copy(
        update={
            "inferred_facts": list(user_blueprint.inferred_facts)
            + [f for f in new_facts if f not in existing],
            "conversation_history": list(user_blueprint.conversation_history)
            + [
                ConversationTurn(role="user", content=user_message),
                ConversationTurn(role="assistant", content=user_reply),
            ],
        }
    )

    trace = LLMCallTrace(
        task="orchestrator.run_turn",
        model_requested=model,
        latency_ms=latency_ms,
    )

    return OrchestratorResult(
        user_facing_reply=user_reply,
        updated_blueprint=updated_blueprint,
        llm_traces=[trace],
    )
