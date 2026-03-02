"""Orchestrator — the Future Self Synthesizer.

Implements the reactive pipeline:
  User message
    → select agents (LLM call)
    → fan-out to workers concurrently
    → detect conflicts (LLM call)
    → optional critique rounds
    → synthesise user-facing reply (LLM call)
    → extract facts into blueprint (LLM call)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from futureself.agents import AGENT_REGISTRY, MAX_CRITIQUE_ROUNDS
from futureself.llm.provider import LLMProvider
from futureself.schemas import (
    AgentResponse,
    CritiqueContext,
    OrchestratorResult,
    UserBlueprint,
)

_ORCHESTRATOR_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "orchestrator.md"


def _load_orchestrator_prompt() -> str:
    return _ORCHESTRATOR_PROMPT_PATH.read_text(encoding="utf-8")


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Best-effort JSON object parser for model output."""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# 1. Agent selection
# ---------------------------------------------------------------------------


def _build_selection_system() -> str:
    agent_keys = ", ".join(sorted(AGENT_REGISTRY.keys()))
    return f"""\
You are a routing component inside a multi-agent longevity advisor.
Given a user's message and their profile, decide which 2-3 specialist
agents should be consulted.

Available agents (use exactly these keys):
  {agent_keys}

Return ONLY a JSON object:
{{
  "selected_agents": ["agent_key", ...]
}}
"""


async def _select_agents(
    blueprint: UserBlueprint,
    user_message: str,
    provider: LLMProvider,
) -> list[str]:
    """Ask the LLM to select relevant agents for the user message."""
    user_content = (
        f"USER BLUEPRINT:\n{blueprint.model_dump_json(indent=2)}\n\n"
        f"USER MESSAGE:\n{user_message}"
    )
    raw = await provider.complete(
        system=_build_selection_system(),
        user=user_content,
        response_format={"type": "json_object"},
    )
    data = _parse_json_object(raw)
    selected = data.get("selected_agents", [])
    if not isinstance(selected, list):
        selected = []

    # Filter to known agents only
    return [a for a in selected if a in AGENT_REGISTRY]


# ---------------------------------------------------------------------------
# 2. Parallel fan-out
# ---------------------------------------------------------------------------


async def _fan_out(
    agent_keys: list[str],
    blueprint: UserBlueprint,
    user_message: str,
    provider: LLMProvider,
) -> dict[str, AgentResponse]:
    """Run selected agents in parallel and collect their responses."""

    async def _call(key: str) -> tuple[str, AgentResponse]:
        run_fn = AGENT_REGISTRY[key]
        response = await run_fn(blueprint, user_message, provider=provider)
        return key, response

    results = await asyncio.gather(*[_call(k) for k in agent_keys])
    return dict(results)


# ---------------------------------------------------------------------------
# 3. Conflict detection
# ---------------------------------------------------------------------------

_CONFLICT_SYSTEM = """\
You are a conflict detection component inside a multi-agent longevity advisor.
You will receive a set of agent responses. Your PRIMARY job is to compare the
actual advice each agent gave and determine whether following all of them
together creates genuine tensions or trade-offs.

A conflict exists when:
- One agent's core recommendation directly CONTRADICTS or works AGAINST
  another agent's core recommendation (e.g., "rest more" vs "work extra
  hours to pay debt").
- Following one agent's advice would require SACRIFICING a key benefit
  from another agent's advice (e.g., "buy the motorcycle for joy" vs
  "avoid the motorcycle for safety").
- The advice from different agents competes for the same limited
  resource (time, money, energy) in ways the user cannot satisfy
  simultaneously.

A conflict does NOT exist when:
- Agents give advice on different topics that can be followed together
  without tension.
- One agent simply adds caveats or conditions to another's advice
  without fundamentally opposing it.

Compare the substance of each agent's recommendation against every
other agent's recommendation.

Err on the side of flagging — it is better to surface a tension for
review than to let a genuine conflict pass through unexamined.

Return ONLY a JSON object:
{
  "conflict_detected": true/false,
  "conflict_summary": "plain-language description of the tension, or empty string if none",
  "implicated_agents": ["agent_key", ...]
}
"""


async def _detect_conflicts(
    responses: dict[str, AgentResponse],
    provider: LLMProvider,
) -> tuple[bool, str, list[str]]:
    """Check whether agent responses contain cross-domain conflicts."""
    summaries = []
    for domain, resp in responses.items():
        summaries.append(
            f"--- {domain} (confidence={resp.confidence}, urgency={resp.urgency}) ---\n"
            f"Advice: {resp.advice}"
        )

    raw = await provider.complete(
        system=_CONFLICT_SYSTEM,
        user="\n\n".join(summaries),
        response_format={"type": "json_object"},
    )
    data = _parse_json_object(raw)
    implicated = data.get("implicated_agents", [])
    if not isinstance(implicated, list):
        implicated = []
    return (
        bool(data.get("conflict_detected", False)),
        str(data.get("conflict_summary", "")),
        [a for a in implicated if isinstance(a, str)],
    )


# ---------------------------------------------------------------------------
# 4. Critique rounds
# ---------------------------------------------------------------------------


async def _run_critique_round(
    responses: dict[str, AgentResponse],
    implicated_agents: list[str],
    conflict_summary: str,
    blueprint: UserBlueprint,
    user_message: str,
    provider: LLMProvider,
    round_number: int,
) -> dict[str, AgentResponse]:
    """Re-invoke implicated agents with CritiqueContext for conflict resolution."""

    async def _critique(agent_key: str) -> tuple[str, AgentResponse]:
        # Build a summary of the OTHER agents' advice as the conflicting context
        other_advice = "\n".join(
            f"[{k}] {r.advice}" for k, r in responses.items() if k != agent_key
        )
        ctx = CritiqueContext(
            conflicting_advice=other_advice,
            concern_area=conflict_summary,
            orchestrator_question=(
                f"Given the tension identified ({conflict_summary}), "
                f"can you refine your advice to address this concern while "
                f"maintaining your core recommendation?"
            ),
            round_number=round_number,
        )
        run_fn = AGENT_REGISTRY[agent_key]
        refined = await run_fn(blueprint, user_message, critique_context=ctx, provider=provider)
        return agent_key, refined

    valid_agents = [a for a in implicated_agents if a in responses]
    results = await asyncio.gather(*[_critique(a) for a in valid_agents])
    return dict(results)


# ---------------------------------------------------------------------------
# 5. Synthesis
# ---------------------------------------------------------------------------


_SYNTHESIS_TEMPLATE = """\
You are the Future Self Synthesizer. You speak as the user's future self,
looking back from 100+ years ahead with warmth, wisdom, and gentle urgency.

Below are internal advisor memos about the user's message. Synthesise them
into a single, conversational response in the Future Self persona.

RULES:
- Speak in 1st person plural: "I remember when we...", "Back when we were your age..."
- Be warm, wise, sometimes humorous. Nudge, never lecture.
- If conflict was detected and resolved, weave the resolution naturally into
  your wisdom — don't enumerate the agents or expose the system architecture.
- Never say "as an AI" or reference agents/memos/systems.
- Medium length: meaningful but not exhausting.
- End with a question or gentle prompt to continue the conversation.

USER MESSAGE:
{user_message}

ADVISOR MEMOS:
{advisor_memos}

CONFLICT INFO:
{conflict_info}
"""


async def _synthesise(
    user_message: str,
    responses: dict[str, AgentResponse],
    conflict_summary: str,
    provider: LLMProvider,
) -> str:
    """Produce the final user-facing reply in the Future Self persona."""
    memos = []
    for domain, resp in responses.items():
        memos.append(
            f"[{domain}] (confidence={resp.confidence}, urgency={resp.urgency})\n"
            f"{resp.advice}"
        )

    conflict_info = conflict_summary if conflict_summary else "No conflicts detected."

    prompt = _SYNTHESIS_TEMPLATE.format(
        user_message=user_message,
        advisor_memos="\n\n".join(memos),
        conflict_info=conflict_info,
    )

    orchestrator_prompt = _load_orchestrator_prompt()
    return await provider.complete(system=orchestrator_prompt, user=prompt)


# ---------------------------------------------------------------------------
# 6. Fact extraction (orchestrator-owned)
# ---------------------------------------------------------------------------

_FACTS_SYSTEM = """\
You are a fact-extraction component inside a multi-agent longevity advisor.
You will receive the user's message and the advisor memos produced for it.
Extract any NEW factual information about the user that should be remembered
for future interactions.

Rules:
- Only extract facts explicitly stated or strongly implied by the user.
- Do NOT repeat information already present in the User Blueprint.
- Return short, self-contained sentences (e.g. "User has knee pain").
- If nothing new was revealed, return an empty list.

Return ONLY a JSON object: {"new_facts": ["fact1", "fact2", ...]}
"""


async def _extract_facts(
    blueprint: UserBlueprint,
    user_message: str,
    responses: dict[str, AgentResponse],
    provider: LLMProvider,
) -> UserBlueprint:
    """Extract new facts from the conversation via a single LLM call.

    Never mutates the original blueprint.
    """
    memos = "\n".join(f"[{k}] {r.advice}" for k, r in responses.items())
    user_content = (
        f"USER BLUEPRINT:\n{blueprint.model_dump_json(indent=2)}\n\n"
        f"USER MESSAGE:\n{user_message}\n\n"
        f"ADVISOR MEMOS:\n{memos}"
    )
    raw = await provider.complete(
        system=_FACTS_SYSTEM,
        user=user_content,
        response_format={"type": "json_object"},
    )
    data = _parse_json_object(raw)
    new_facts: list[str] = data.get("new_facts", [])
    if not isinstance(new_facts, list):
        new_facts = []

    if not new_facts:
        return blueprint

    existing = set(blueprint.inferred_facts)
    unique_new = [f for f in new_facts if f not in existing]
    return blueprint.model_copy(
        update={"inferred_facts": list(blueprint.inferred_facts) + unique_new}
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def run_turn(
    user_blueprint: UserBlueprint,
    user_message: str,
    *,
    provider: LLMProvider | None = None,
) -> OrchestratorResult:
    """Run one full turn of the orchestrator pipeline.

    Args:
        user_blueprint: Read-only user profile.
        user_message: The user's raw message.
        provider: Optional LLMProvider override (for testing).

    Returns:
        OrchestratorResult containing all intermediate and final outputs.
    """
    if provider is None:
        provider = LLMProvider.get_default()

    # 1. Select agents
    agent_keys = await _select_agents(user_blueprint, user_message, provider)

    if not agent_keys:
        # Fallback: at least consult mental_health for anything
        agent_keys = ["mental_health"]

    # 2. Fan-out
    initial_responses = await _fan_out(agent_keys, user_blueprint, user_message, provider)

    # 3. Conflict detection
    conflict_detected, conflict_summary, implicated_agents = await _detect_conflicts(
        initial_responses, provider
    )

    refined_responses: dict[str, AgentResponse] = {}

    # 4. Critique rounds (only if conflict detected)
    if conflict_detected and implicated_agents:
        current_responses = dict(initial_responses)
        for round_num in range(1, MAX_CRITIQUE_ROUNDS + 1):
            round_refined = await _run_critique_round(
                current_responses,
                implicated_agents,
                conflict_summary,
                user_blueprint,
                user_message,
                provider,
                round_num,
            )
            refined_responses.update(round_refined)
            current_responses.update(round_refined)

    # 5. Synthesise — use refined responses where available, initial otherwise
    final_responses = dict(initial_responses)
    final_responses.update(refined_responses)

    # 6. Extract facts concurrently with synthesis to keep user path responsive.
    facts_task = asyncio.create_task(
        _extract_facts(user_blueprint, user_message, final_responses, provider)
    )
    user_facing_reply = await _synthesise(
        user_message, final_responses, conflict_summary, provider
    )
    updated_blueprint = await facts_task

    return OrchestratorResult(
        agents_consulted=agent_keys,
        initial_responses=initial_responses,
        refined_responses=refined_responses,
        conflict_detected=conflict_detected,
        conflict_summary=conflict_summary,
        user_facing_reply=user_facing_reply,
        updated_blueprint=updated_blueprint,
    )
