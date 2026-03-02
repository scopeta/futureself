# Agent Response Schemas

All dataclasses below live in `src/schemas.py` (or equivalent shared module).

## AgentResponse

```python
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TradeoffFlag:
    """Side effect of this agent's own advice that falls outside its domain.
    Uses plain language — never references other agents by name."""

    concern_area: str               # e.g. "cost", "time commitment", "emotional stress"
    description: str                # brief explanation of the side effect
    severity: Literal["low", "medium", "high"]


@dataclass
class AgentResponse:
    confidence: float               # 0.0–1.0; reflect genuine uncertainty
    domain: str                     # snake_case domain name, e.g. "physical_health"
    key_facts_extracted: list[str]  # new facts to merge into User Blueprint
    advice: str                     # internal memo to orchestrator, NOT user-addressed
    tradeoff_flags: list[TradeoffFlag] = field(default_factory=list)
    is_refined: bool = False        # True when produced during a critique round
```

### Field rules

- **`advice`** — Internal memo. Never use second-person "you" addressing the
  user. The orchestrator synthesizes all advice into a single Future Self persona
  response.
- **`tradeoff_flags`** — Plain-language concern areas only. Agents have zero
  knowledge of other agents. Flag side effects of your *own* advice (e.g.,
  "this supplement regimen costs ~$200/month").
- **`is_refined`** — Must be `True` when the response was produced during a
  critique round (i.e., `critique_context` was provided).

## CritiqueContext

Injected by the orchestrator when it detects conflicting advice across domains.

```python
@dataclass
class CritiqueContext:
    conflicting_advice: str         # the other domain's advice text
    concern_area: str               # what the orchestrator identified as the tension
    orchestrator_question: str      # the specific compromise question to address
    round_number: int               # 1-based; capped at MAX_CRITIQUE_ROUNDS
```

## run() function signature

```python
async def run(
    user_blueprint: UserBlueprint,
    user_message: str,
    critique_context: CritiqueContext | None = None,
) -> AgentResponse:
    """
    Run the agent against the user's current message.

    Args:
        user_blueprint: The shared read-only user state.
        user_message: The raw message delegated by the orchestrator.
        critique_context: Optional. Present only during orchestrator-initiated
            critique rounds. Contains conflicting advice from another domain
            and a pointed question from the orchestrator seeking compromise.
            When present, the agent must refine or defend its position.

    Returns:
        A structured AgentResponse.
    """
```

## Prompt loading pattern

```python
from pathlib import Path
from src.llm.provider import LLMProvider

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "<domain_name>.md"

def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")

async def run(
    user_blueprint: UserBlueprint,
    user_message: str,
    critique_context: CritiqueContext | None = None,
) -> AgentResponse:
    provider = LLMProvider.get_default()
    raw = await provider.complete(
        system=_load_prompt(),
        user=_build_context(user_blueprint, user_message, critique_context),
    )
    return _parse_response(raw)
```

## Test template

```python
import pytest
from src.agents.<domain_name> import run
from tests.fixtures import make_blueprint, make_message, make_critique_context

@pytest.mark.asyncio
async def test_returns_valid_schema():
    response = await run(make_blueprint(), make_message())
    assert 0.0 <= response.confidence <= 1.0
    assert response.domain == "<domain_name>"
    assert isinstance(response.key_facts_extracted, list)
    assert isinstance(response.advice, str) and len(response.advice) > 0
    assert isinstance(response.is_refined, bool)

@pytest.mark.asyncio
async def test_does_not_mutate_blueprint():
    blueprint = make_blueprint()
    snapshot = blueprint.model_dump()
    await run(blueprint, make_message())
    assert blueprint.model_dump() == snapshot

@pytest.mark.asyncio
async def test_critique_round_sets_is_refined():
    ctx = make_critique_context(concern_area="cost")
    response = await run(make_blueprint(), make_message(), critique_context=ctx)
    assert response.is_refined is True

@pytest.mark.asyncio
async def test_tradeoff_flags_use_plain_language():
    response = await run(make_blueprint(), make_message())
    for flag in response.tradeoff_flags:
        assert "agent" not in flag.concern_area.lower()
        assert "agent" not in flag.description.lower()
```

## Blueprint immutability

```python
# CORRECT — signal new facts via response
response.key_facts_extracted = ["user reports chronic knee pain since 2025"]

# WRONG — never mutate inside an agent
user_blueprint.bio_data["conditions"].append("knee pain")
```
