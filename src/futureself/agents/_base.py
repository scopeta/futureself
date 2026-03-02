"""Shared agent logic — every worker agent delegates to this module.

Each domain agent is a thin wrapper that calls ``make_run(domain)`` where
``domain`` is the snake_case domain key, which is also the prompt filename
(without extension) under ``prompts/``.

Everything else — context building, JSON parsing, the ``run()`` coroutine —
lives here exactly once.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from futureself.llm.provider import LLMProvider
from futureself.schemas import AgentResponse, CritiqueContext, UserBlueprint

_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"
_ALLOWED_URGENCY = {"low", "medium", "high", "critical"}


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Best-effort JSON object parser for model output."""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_confidence(value: Any) -> float:
    """Coerce confidence to float and clamp to [0.0, 1.0]."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, numeric))


def _normalize_label(value: Any, allowed: set[str], default: str) -> str:
    """Return normalized lower-case label constrained to an allowed set."""
    normalized = str(value).strip().lower()
    return normalized if normalized in allowed else default


def build_user_context(
    blueprint: UserBlueprint,
    user_message: str,
    critique_context: CritiqueContext | None,
) -> str:
    """Assemble the user turn sent to the LLM."""
    parts = [
        f"USER BLUEPRINT:\n{blueprint.model_dump_json(indent=2)}",
        f"\nUSER MESSAGE:\n{user_message}",
    ]
    if critique_context:
        parts.append(
            f"\nCRITIQUE CONTEXT (round {critique_context.round_number}):\n"
            f"Conflicting advice: {critique_context.conflicting_advice}\n"
            f"Concern area: {critique_context.concern_area}\n"
            f"Orchestrator question: {critique_context.orchestrator_question}"
        )
    return "\n".join(parts)


def parse_response(raw: str, domain: str, is_refined: bool) -> AgentResponse:
    """Parse LLM JSON output into AgentResponse."""
    data = _parse_json_object(raw)

    base_keys = {"confidence", "domain", "advice", "urgency"}
    extensions = {k: v for k, v in data.items() if k not in base_keys}

    return AgentResponse(
        confidence=_normalize_confidence(data.get("confidence", 0.5)),
        domain=domain,
        advice=str(data.get("advice", "")),
        urgency=_normalize_label(data.get("urgency", "low"), _ALLOWED_URGENCY, "low"),
        is_refined=is_refined,
        extensions=extensions,
    )


def make_run(
    domain: str,
) -> Callable[..., Coroutine[Any, Any, AgentResponse]]:
    """Factory that creates a ``run()`` coroutine for a given domain.

    The prompt file is resolved automatically as ``prompts/{domain}.md``
    relative to the project root.
    """
    prompt_path = _PROMPTS_DIR / f"{domain}.md"

    def _load_prompt() -> str:
        return prompt_path.read_text(encoding="utf-8")

    async def run(
        user_blueprint: UserBlueprint,
        user_message: str,
        critique_context: CritiqueContext | None = None,
        *,
        provider: LLMProvider | None = None,
    ) -> AgentResponse:
        if provider is None:
            provider = LLMProvider.get_default()

        raw = await provider.complete(
            system=_load_prompt(),
            user=build_user_context(user_blueprint, user_message, critique_context),
            response_format={"type": "json_object"},
        )
        return parse_response(raw, domain, is_refined=critique_context is not None)

    run.__doc__ = f"Run the {domain} agent."
    return run
