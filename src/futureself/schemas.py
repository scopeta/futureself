"""Data contracts for the FutureSelf multi-agent system.

All agent modules and the orchestrator import from this module.
The schemas here are the single source of truth for inter-component
data exchange.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# TradeoffFlag — emitted by worker agents when advice has side effects
# ---------------------------------------------------------------------------


@dataclass
class TradeoffFlag:
    """A plain-language warning that advice in this domain affects another domain."""

    concern_area: str
    """The domain or life area affected (e.g. 'cost', 'time commitment', 'sleep')."""

    description: str
    """A brief, plain-language explanation. Must not name other agents or use jargon."""

    severity: Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# AgentResponse — base contract returned by every worker agent
# ---------------------------------------------------------------------------


@dataclass
class AgentResponse:
    """Structured response from a worker agent. This is an internal memo to the
    orchestrator — never shown directly to the user."""

    confidence: float
    """Confidence in the advice, from 0.0 (very uncertain) to 1.0 (highly confident)."""

    domain: str
    """Snake-case domain identifier, e.g. 'physical_health'."""

    advice: str
    """Internal memo to the orchestrator. Must NOT address the user directly."""

    tradeoff_flags: list[TradeoffFlag]
    """Side effects of this advice that touch other life domains."""

    urgency: Literal["low", "medium", "high", "critical"]
    """How urgently the orchestrator should weight this advice."""

    is_refined: bool = False
    """True when this response came from a critique round."""

    extensions: dict[str, Any] = field(default_factory=dict)
    """Domain-specific extra fields (e.g. crisis_flag, contraindications,
    proposed_schedule_change). Captured from the prompt output without
    modifying the base contract."""


# ---------------------------------------------------------------------------
# CritiqueContext — passed to agents during conflict-resolution rounds
# ---------------------------------------------------------------------------


@dataclass
class CritiqueContext:
    """Context the orchestrator provides when asking an agent to refine its advice
    in light of a conflict with another domain."""

    conflicting_advice: str
    """The other domain's advice that conflicts with this agent's recommendation."""

    concern_area: str
    """The specific area of tension identified by the orchestrator."""

    orchestrator_question: str
    """The specific compromise or clarification the orchestrator is asking for."""

    round_number: int
    """1-based critique round counter. Capped at MAX_CRITIQUE_ROUNDS."""


# ---------------------------------------------------------------------------
# UserBlueprint — the user's persistent profile (read-only for agents)
# ---------------------------------------------------------------------------


class BioData(BaseModel):
    """Biological and medical information."""

    age: int | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    conditions: list[str] = []
    medications: list[str] = []
    biomarkers: dict[str, float] = {}


class PsychData(BaseModel):
    """Psychological profile and goals."""

    goals: list[str] = []
    fears: list[str] = []
    stress_level: Literal["low", "medium", "high"] | None = None
    mental_health_flags: list[str] = []


class ContextData(BaseModel):
    """Life context: location, occupation, family."""

    location_city: str | None = None
    location_country: str | None = None
    occupation: str | None = None
    income_usd_annual: float | None = None
    family_situation: str | None = None
    lifestyle_notes: list[str] = []


class ConversationTurn(BaseModel):
    """A single turn in the conversation history."""

    role: Literal["user", "assistant"]
    content: str


class UserBlueprint(BaseModel):
    """The user's persistent, read-only profile passed to every agent.

    Agents must treat this as immutable.
    The orchestrator is responsible for extracting facts and creating an
    updated blueprint after each turn.
    """

    model_config = ConfigDict(frozen=True)

    bio: BioData = BioData()
    psych: PsychData = PsychData()
    context: ContextData = ContextData()
    conversation_history: list[ConversationTurn] = []
    inferred_facts: list[str] = []
    """Accumulated facts extracted across all previous turns."""

    @classmethod
    def from_dict(cls, data: dict) -> "UserBlueprint":
        """Construct from a raw dict (e.g. loaded from a YAML scenario file)."""
        bio_data = data.get("bio", {})
        psych_data = data.get("psych", {})
        context_data = data.get("context", {})
        return cls(
            bio=BioData(**bio_data) if bio_data else BioData(),
            psych=PsychData(**psych_data) if psych_data else PsychData(),
            context=ContextData(**context_data) if context_data else ContextData(),
        )


# ---------------------------------------------------------------------------
# OrchestratorResult — the full result of one orchestration turn
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorResult:
    """Everything produced in one turn of the orchestrator pipeline."""

    agents_consulted: list[str]
    """Domain keys of agents that ran in this turn."""

    initial_responses: dict[str, AgentResponse]
    """Responses from the initial fan-out, keyed by domain."""

    refined_responses: dict[str, AgentResponse]
    """Responses after critique rounds, if any. Empty if no conflict was detected."""

    conflict_detected: bool
    """Whether the orchestrator identified cross-domain conflicts."""

    conflict_summary: str
    """Plain-language description of the conflict. Empty string if none."""

    user_facing_reply: str
    """The synthesized reply in the Future Self persona, ready to show to the user."""

    updated_blueprint: UserBlueprint
    """A new UserBlueprint with newly extracted facts merged into inferred_facts."""
