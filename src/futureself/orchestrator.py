"""Orchestrator — the Future Self Synthesizer.

Single-agent pipeline using Microsoft Agent Framework (MAF):
  User message + UserBlueprint
    → ChatAgent (Claude Opus 4.6 via Azure AI Foundry)
      with SkillsProvider (6 domain SKILL.md files)
    → Claude loads relevant skills on demand via load_skill tool
    → Synthesizes Future Self reply
    → Facts extracted from reply (regex, no extra LLM call)
    → Updated UserBlueprint returned
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
            "FUTURESELF_MODEL is required. Set it to the model deployment name "
            "for your Foundry project (e.g. 'claude-opus-4-6', 'gpt-4o')."
        )
    return model


def _load_orchestrator_prompt() -> str:
    return _ORCHESTRATOR_PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_context(blueprint: UserBlueprint, user_message: str) -> str:
    """Render the user context passed to the agent each turn."""
    history_lines = []
    for turn in blueprint.conversation_history[-10:]:  # last 10 turns
        history_lines.append(f"{turn.role.upper()}: {turn.content}")

    facts_section = ""
    if blueprint.inferred_facts:
        facts_section = "\n\nKNOWN FACTS ABOUT USER:\n" + "\n".join(
            f"- {f}" for f in blueprint.inferred_facts
        )

    history_section = ""
    if history_lines:
        history_section = "\n\nCONVERSATION HISTORY:\n" + "\n".join(history_lines)

    return (
        f"USER PROFILE:\n{blueprint.model_dump_json(indent=2)}"
        f"{facts_section}"
        f"{history_section}"
        f"\n\nUSER MESSAGE:\n{user_message}"
    )


def _extract_facts_simple(reply: str, blueprint: UserBlueprint) -> list[str]:
    """Extract new facts from the reply without an LLM call.

    Looks for common patterns: age mentions, location, conditions, goals.
    Returns only facts not already in the blueprint.
    """
    existing = set(blueprint.inferred_facts)
    candidates: list[str] = []

    # Age pattern: "I'm 35" / "I am 42 years old"
    for m in re.finditer(r"\bI(?:'m| am) (\d{2,3})(?: years? old)?\b", reply, re.I):
        candidates.append(f"User is {m.group(1)} years old")

    # Location pattern: "I live in X" / "based in X"
    for m in re.finditer(r"\b(?:I live|based|living) in ([A-Z][a-zA-Z\s,]+?)(?:\.|,|\n|$)", reply):
        candidates.append(f"User lives in {m.group(1).strip()}")

    return [f for f in candidates if f not in existing]


def _build_agent(project_endpoint: str, model: str) -> object:
    """Build and return the MAF ChatAgent with SkillsProvider.

    Args:
        project_endpoint: Azure AI Foundry project endpoint URL.
        model: Model deployment name in the Foundry project.
    """
    from agent_framework import SkillsProvider  # lazy import — not installed in local dev
    from agent_framework.azure import AzureAIAgentClient
    from azure.identity.aio import DefaultAzureCredential

    skills_provider = SkillsProvider(skill_paths=_SKILLS_DIR)

    return AzureAIAgentClient(
        project_endpoint=project_endpoint,
        model_deployment_name=model,
        credential=DefaultAzureCredential(),
    ).as_agent(
        name="FutureSelf",
        instructions=_load_orchestrator_prompt(),
        context_providers=[skills_provider],
    )


async def run_turn(
    user_blueprint: UserBlueprint,
    user_message: str,
    *,
    project_endpoint: str | None = None,
    _agent: object | None = None,
    _model: str | None = None,
) -> OrchestratorResult:
    """Run one turn of the Future Self agent via MAF on Azure AI Foundry.

    Args:
        user_blueprint: Read-only user profile.
        user_message: The user's raw message.
        project_endpoint: Azure AI Foundry project endpoint URL.
            Falls back to the ``AZURE_FOUNDRY_ENDPOINT`` environment variable.
        _agent: Injectable MAF agent instance (testing — skips building a real agent).
        _model: Injectable model name (testing — skips ``FUTURESELF_MODEL`` lookup).

    Returns:
        OrchestratorResult with user_facing_reply, updated_blueprint, llm_traces.
    """
    model = _model if _model is not None else _resolve_model()
    endpoint = project_endpoint or os.getenv("AZURE_FOUNDRY_ENDPOINT", "")
    agent = _agent if _agent is not None else _build_agent(endpoint, model)

    user_ctx = _build_user_context(user_blueprint, user_message)

    t0 = time.monotonic()
    session = await agent.create_session()
    result = await agent.run(user_ctx, session=session)
    latency_ms = (time.monotonic() - t0) * 1000

    user_reply: str = result.value or ""

    new_facts = _extract_facts_simple(user_reply, user_blueprint)
    existing = set(user_blueprint.inferred_facts)
    unique_new = [f for f in new_facts if f not in existing]

    updated_blueprint = user_blueprint.model_copy(
        update={
            "inferred_facts": list(user_blueprint.inferred_facts) + unique_new,
            "conversation_history": list(user_blueprint.conversation_history) + [
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
