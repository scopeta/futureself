# FutureSelf Functional Specification

> Status: Active Implementation Spec
> Date: 2026-04-13
> Scope: Architecture and contracts after single-agent refactoring (Phases 1–5 complete)

---

## 1. Overview

**FutureSelf is a single-agent longevity guidance system.**
**The only user-facing component is the Future Self Synthesizer.**
Domain expertise is delivered via six skills loaded on demand — not via parallel sub-agents.

### Core goals
- **Holistic:** Health is not just physical; it's mental, financial, social, and environmental.
- **Personalized:** Advice adapts to the user's specific biology, location, and lifestyle.
- **Long-term:** The interaction model is designed for a lifelong relationship, not transactional queries.
- **Persona-consistent synthesis** as the user's future self.
- **Controlled blueprint updates** owned by orchestrator only.
- **Minimal LLM calls:** 1 reasoning LLM call per turn plus tool calls for skill loading (no extra completions).

---

## 2. Architecture Overview

Single-agent pipeline with MAF SkillsProvider for progressive domain disclosure.

```mermaid
flowchart TD
    User(["User Message + UserBlueprint"]) --> AgentNode

    subgraph AgentBox["ChatAgent (Anthropic direct or Azure AI Foundry)"]
        AgentNode["Agent"]
        System["System: prompts/orchestrator.md"]
        Skills["SkillsProvider injects skill names and descriptions at session start"]
        Reason["LLM reasons and calls load_skill for relevant domains"]
        Skill1["load_skill physical_health returns SKILL.md body"]
        Skill2["load_skill mental_health returns SKILL.md body"]
        Synthesize["Synthesizes Future Self reply in character"]
        AgentNode --> System --> Skills --> Reason
        Reason --> Skill1
        Reason --> Skill2
        Skill1 --> Synthesize
        Skill2 --> Synthesize
    end

    Synthesize --> Reply(["User-Facing Reply"])
    Reply -.-> Facts["extract_facts_simple (regex, no LLM call)"]
    Facts -.-> Blueprint[("Updated Blueprint")]
```

**LLM calls per turn:** 1 completion + N `load_skill` tool calls (N = 0–3 relevant domains). Skill loading consumes no additional completions.

---

## 3. Skills

| # | Skill | Key | File |
|---|-------|-----|------|
| 1 | Physical Health | `physical_health` | `src/futureself/skills/physical_health/SKILL.md` |
| 2 | Mental Health | `mental_health` | `src/futureself/skills/mental_health/SKILL.md` |
| 3 | Financial | `financial` | `src/futureself/skills/financial/SKILL.md` |
| 4 | Social Relations | `social_relations` | `src/futureself/skills/social_relations/SKILL.md` |
| 5 | Geopolitics | `geopolitics` | `src/futureself/skills/geopolitics/SKILL.md` |
| 6 | Time Management | `time_management` | `src/futureself/skills/time_management/SKILL.md` |

### Domain Intent Snapshot

- **Physical Health:** Nutrition, exercise, sleep, biomarkers, and medical-risk-aware longevity advice.
- **Mental Health:** Stress resilience, emotional regulation, crisis signal awareness, and behavioral durability.
- **Financial:** Long-horizon planning, risk control, healthcare affordability, and stress-reducing simplicity.
- **Social Relations:** Loneliness risk reduction, relationship quality, and durable community integration.
- **Geopolitics:** Location risk analysis (air quality, climate, stability, healthcare system access).
- **Time Management:** Translating strategy into executable habits and schedules under real-life constraints.

---

## 4. Runtime Orchestration Flow

Single-turn flow (`run_turn`):

1. **Build** user context from `UserBlueprint` + `user_message` (conversation history, inferred facts, profile).
2. **Run** the MAF ChatAgent with `SkillsProvider` .
   - SkillsProvider injects skill names + descriptions at session start.
   - LLM reads the turn context, decides which skills are relevant, calls `load_skill` for each.
   - SkillsProvider returns the full SKILL.md body — no LLM call consumed.
   - LLM synthesizes the Future Self reply in character.
3. **Extract** new facts from the reply via `_extract_facts_simple` (regex, no LLM call).
4. **Append** turn to conversation history and merge new facts into blueprint (immutable copy).
5. **Return** `OrchestratorResult`.

Notes:
- Fact extraction is synchronous and regex-based — no additional LLM cost.
- `_agent` parameter in `run_turn` allows mock injection for tests without Azure credentials.

---

## 5. Data Contracts

All contracts live in `src/futureself/schemas.py`.

### 5.1 User Blueprint (`UserBlueprint`)

Frozen Pydantic model (`frozen=True`). Immutable for all callers; the orchestrator returns an updated copy via `model_copy`.

Top-level fields:
- `bio: BioData`
- `psych: PsychData`
- `context: ContextData`
- `conversation_history: list[ConversationTurn]` — *current persistence: Postgres, owned by FutureSelf. **On Foundry Hosted Agents migration this field becomes a transient view of Foundry-managed thread memory** (see Section 11); the Blueprint domain object stays in Postgres.*
- `inferred_facts: list[str]`

Class method:
- `from_dict(data: dict) -> UserBlueprint` — used by scenario test loader.

#### `BioData`

- `age: int | None`
- `sex: str | None`
- `height_cm: float | None`
- `weight_kg: float | None`
- `conditions: list[str]`
- `medications: list[str]`
- `supplements: list[Supplement]`
- `biomarker_history: list[BiomarkerEntry]`
- `exam_records: list[ExamRecord]`

Supporting types:
- **`Supplement`:** `name`, `dose`, `started`, `stopped`, `reason`
- **`BiomarkerEntry`:** `marker`, `value`, `unit`, `date`, `source`
- **`ExamRecord`:** `exam_type`, `date`, `provider`, `key_findings`, `raw_text`

#### `PsychData`

- `goals: list[str]`
- `fears: list[str]`
- `stress_level: str | None`
- `mental_health_flags: list[str]`

#### `ContextData`

- `location_city: str | None`
- `location_country: str | None`
- `occupation: str | None`
- `income_usd_annual: float | None`
- `family_situation: str | None`
- `lifestyle_notes: list[str]`

#### `ConversationTurn`

- `role: Literal["user", "assistant"]`
- `content: str`

### 5.2 LLM Call Trace (`LLMCallTrace`)

- `task: str` — e.g. `"orchestrator.run_turn"`
- `model_requested: str`
- `model_actual: str | None` — populated if provider reports actual model used
- `prompt_tokens: int`
- `completion_tokens: int`
- `latency_ms: float`

### 5.3 Turn Result (`OrchestratorResult`)

- `user_facing_reply: str`
- `updated_blueprint: UserBlueprint`
- `llm_traces: list[LLMCallTrace]`

---

## 6. MAF Skills and Agent Client

### SkillsProvider (Microsoft Agent Framework)

`SkillsProvider(skill_paths=Path("src/futureself/skills"))` discovers all `SKILL.md` files and:
1. Injects a `load_skill` tool definition into the agent's tool list.
2. At session start, appends a short skills manifest to the system prompt (~100 tokens/skill): name + description only.
3. Handles `load_skill("<name>")` tool calls by returning the full SKILL.md body.

LLM reads the manifest and autonomously decides which skills to load based on the user message.

### Agent construction (`src/futureself/orchestrator.py`)

Two client backends, selected by environment variable:

**Anthropic direct** (`ANTHROPIC_API_KEY` set, no `AZURE_FOUNDRY_ENDPOINT`):
```python
from agent_framework import Agent, SkillsProvider
from agent_framework_anthropic import AnthropicClient

client = AnthropicClient(api_key=api_key, model=model)
agent = Agent(client, instructions=prompt, name="FutureSelf", context_providers=[skills_provider])
```

**Azure AI Foundry** (`AZURE_FOUNDRY_ENDPOINT` set) — model-agnostic (GPT, Claude, Grok, etc.):
```python
from agent_framework import Agent, SkillsProvider
from agent_framework_foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

client = FoundryChatClient(project_endpoint=endpoint, model=model, credential=DefaultAzureCredential())
agent = Agent(client, instructions=prompt, name="FutureSelf", context_providers=[skills_provider])
```

Session and run (in `run_turn`):
```python
session = agent.create_session()           # sync — not async
result = await agent.run(user_ctx, session=session)
reply = result.text or ""                  # AgentResponse.text, not .value
```

`FUTURESELF_MODEL` env var controls the model name in both cases (required, no default).

### Observability

MAF's built-in OpenTelemetry instrumentation is activated at startup via:
```python
from azure.monitor.opentelemetry import configure_azure_monitor
configure_azure_monitor(connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))
```
Set `APPLICATIONINSIGHTS_CONNECTION_STRING` as a Container App env var. Traces appear in Azure Portal → Application Insights → Transaction search. No custom span code needed.

---

## 7. Skill File Conventions

Each skill lives at `src/futureself/skills/<domain>/SKILL.md`:

```markdown
---
name: physical_health
description: >
  Analyze physical health, fitness, biomarkers, medications, and longevity protocols.
  Use when the user asks about exercise, sleep, nutrition, supplements, lab results,
  aging biomarkers, or any body-related longevity topic.
---

# Physical Health — "The Biological Guardian"
...domain system prompt content...
```

Skill prompt body structure: **Role → Domain Expertise → Prioritization Framework → Guidelines → Output Format**

`prompts/orchestrator.md` is not a skill — it is the agent's system prompt and is NOT processed by `SkillsProvider`.

---

## 8. Reliability and Fallback Rules

**No single malformed LLM response may crash a turn.**

| Failure | Fallback |
|---------|----------|
| Empty agent reply | Return `OrchestratorResult` with `user_facing_reply=""` |
| Fact extraction error | Return original blueprint unchanged |
| Missing `AZURE_FOUNDRY_ENDPOINT` | `_build_agent` raises at call time, not at import |

`agent_framework` imports are lazy (inside `_build_agent`) so the module loads in local dev without the cloud SDK installed.

---

## 9. Testing Requirements

### 9.1 Unit/Integration (mocked MAF agent)

Must cover:
- `run_turn` returns `OrchestratorResult` with correct fields.
- Blueprint immutability across turn.
- Conversation history appended with correct `ConversationTurn` objects.
- LLM trace recorded with correct task, model, and non-negative latency.
- `_extract_facts_simple`: age extraction, deduplication, empty reply.
- `_build_user_context`: includes user message, includes inferred facts.
- Empty model reply handled gracefully.

Mock pattern:
```python
def _mock_agent(reply: str) -> MagicMock:
    result = MagicMock()
    result.text = reply                                        # AgentResponse.text
    agent = MagicMock()
    agent.create_session = MagicMock(return_value=MagicMock())  # sync, not AsyncMock
    agent.run = AsyncMock(return_value=result)
    return agent
```

### 9.2 Live Scenario Tests

- Marker-gated (`live`) and excluded by default (`addopts = "-m 'not live'"`).
- Scenario files in `scenarios/*.yaml`.
- Each scenario defines: `name`, `user_blueprint`, and `turns` with `user_message`.
- Multi-turn scenarios carry `updated_blueprint` forward between turns.
- Hard assertions: non-empty reply.

---

## 10. Implementation Roadmap

> **Decision Rule:** Build the intelligence before the interface.

**Phase 1: Agent Laboratory** — *Complete*

**Phase 2: The Orchestrator** — *Complete*

**Phase 3: The Initial Interface** — *Complete*

**Phase 4: Model Router and Cloud** — *Complete*

**Phase 5: Observability** — *Complete*

**Architecture Refactoring** — *Complete*
- Replaced 6-stage supervisor-worker pipeline (7–11 LLM calls/turn) with a single reasoning LLM model.
- MAF `SkillsProvider` delivers progressive domain disclosure via `SKILL.md` files.
- `OrchestratorResult` simplified: removed `agents_consulted`, `initial_responses`, `refined_responses`, `conflict_detected`, `conflict_summary`, `AgentResponse`, `CritiqueContext`.
- Observability: MAF built-in OTel → Application Insights via `azure-monitor-opentelemetry` (configured at startup, no custom span code).
- Deployment: Azure Container Apps (Southeast Asia), FastAPI on port 8000, Docker image on `futureselfacr.azurecr.io`.
- LLM calls: 7–11 → 1 per turn.

**Phase 6: The Data** — *Active*
- User persistence (saving blueprint state across sessions).
- Supplement tracking and biomarker measurement history.
- Blueprint data quality verification and context drift flagging.
- Conversation history population.

**Phase 6.5: Identity & Onboarding (Entra ID)** — *Planned*

Prerequisite slice for productionizing Phase 6: every Blueprint row must be owned by an authenticated user, and no user may read or mutate another user's data.

- **Identity provider:** Microsoft Entra ID (workforce tenant initially; multi-tenant External ID configuration deferred to Phase 7 if WhatsApp B2C onboarding requires it).
- **Auth flow:** OIDC Authorization Code + PKCE from the React UI via MSAL.js. Backend validates Entra-issued JWTs (`iss`, `aud`, signature against tenant JWKS) on every protected request.
- **User identifier:** the Entra `oid` claim (immutable, tenant-scoped) is the canonical user key. A `users` table in Postgres maps `oid → internal user_id (UUID)`; everything else (Blueprint, threads, supplement history) FKs to `user_id`.
- **Onboarding:** first-login flow detects no Blueprint exists for the `oid`, walks the user through a minimum viable Blueprint capture (age, sex, location, top goals, top fears), persists, and routes to the chat surface.
- **Authorization invariant (non-negotiable):** every database query that touches user data is filtered by the `user_id` derived from the validated token — never from a request body, query parameter, or client-supplied header. The orchestrator receives the resolved `user_id` from the auth middleware; it cannot be overridden by the caller.
- **Foundry thread binding:** when Phase 11 (Hosted Agents) lands, the per-user Foundry thread ID stored on the `users` row inherits the same authorization rule.
- **Tests:** add a cross-tenant access denial test (User A's token must not return User B's Blueprint) to the unit tier.

UI deliverables (React frontend):
- **Login screen** — unauthenticated landing surface with a single "Sign in with Microsoft" CTA wired to MSAL.js. No anonymous chat access.
- **Auth-guarded routes** — chat and blueprint pages redirect to the login screen when no valid session/token is present. `api.ts` attaches the MSAL access token as `Authorization: Bearer <jwt>` on every request; 401 responses trigger a silent token refresh, then a forced re-login if refresh fails.
- **Onboarding wizard** — first-login flow when the backend reports no Blueprint exists for the user's `oid`. Multi-step form capturing the minimum viable Blueprint (age, sex, location, top goals, top fears), persisted via the same `/api/blueprint` contract used by the existing settings UI. Wizard cannot be skipped; on completion the user is routed to chat.
- **Session affordance** — header shows the signed-in user (display name from the Entra `name` claim) and a sign-out action that clears the MSAL cache and returns to the login screen.
- **Multi-channel hint** — when the WhatsApp channel exists (Phase 7), the settings page shows the user's bound channel(s); identity remains anchored to the Entra `oid`.

Schema impact (Section 5.1): `UserBlueprint` is conceptually per-user; the persisted row carries `user_id` as an opaque key. The Pydantic model itself does not need to expose `user_id` — it remains an envelope concern owned by the persistence layer and the auth middleware.

**Phase 7: The Advanced Interface**
- WhatsApp integration as primary conversational interface.
- Web UI includes blueprint management, data quality flags, and lab test/exam uploads.

**Phase 8: Enhance Skills** *(Continuous)*
- Specialized tools to expand skill capabilities.
- Advice evaluation and quality feedback loops.

**Phase 9: Proactive Advice** *(Optional)*
- Proactive analysis and recommendations.
- Daily check-in capture.
- **Agent Harness** (Foundry preview): autonomous execution loop for off-turn work — daily check-in synthesis, biomarker drift detection, scheduled nudges. Pairs with Hosted Agents (Section 11); the harness invokes the same Future Self agent without a user-initiated turn. Blueprint mutations from harness runs follow the same orchestrator-only rule as user-initiated turns.

---

## 11. Foundry Hosted Agents Migration (planned)

When `azure-ai-agentserver-agentframework` is compatible with `agent-framework-core>=1.0.1`, the agent moves from in-process Container App execution to managed Foundry Hosted Agents. Two persistence boundaries shift:

### 11.1 Conversation history → Foundry-managed thread memory
- **Today (in-process):** `conversation_history` is a first-class field on `UserBlueprint`, persisted in Postgres alongside `bio`/`psych`/`context`/`inferred_facts`.
- **After migration:** Foundry Agent Service maintains thread memory automatically per session. `conversation_history` on the Blueprint becomes a **read-through projection** of the active Foundry thread (or empty if no thread is bound) — not the system of record. The orchestrator no longer appends turns to it manually; Foundry does.
- **What stays in Postgres:** `bio`, `psych`, `context`, `inferred_facts`. These are domain state, not transcript memory, and remain sovereign to FutureSelf so they survive Foundry session boundaries and channel switches (web ↔ WhatsApp).
- **`inferred_facts` extraction unchanged:** still runs synchronously per turn via `_extract_facts_simple`, still merged into the Postgres-backed Blueprint via `model_copy`.
- **Channel binding:** each user gets one Foundry thread per active channel; thread IDs are stored on the user record in Postgres. Switching channels (web → WhatsApp) starts a fresh thread but keeps the same Blueprint.

### 11.2 Test impact
- Mock pattern in Section 9.1 unchanged for unit tests (Foundry thread is opaque behind `agent.run`).
- Multi-turn scenario tests need to either bind a real Foundry thread (live tier) or stub the thread interface (unit tier).

### 11.3 What does *not* change
- Single-agent rule (Section 2).
- One LLM call per turn (Section 4).
- SkillsProvider and `load_skill` flow (Section 6).
- Blueprint immutability rule (Section 5.1).

---

## 12. Rebuild Checklist

A rebuild from scratch is valid only if all are true:

1. **`run_turn` implements the flow in Section 4.**
2. **All domain expertise is delivered via SKILL.md files following Section 7 conventions.**
3. **`_agent` parameter supports mock injection for tests.**
4. **Blueprint immutability is enforced: orchestrator uses `model_copy`, never mutates.**
5. **LLM call trace is recorded for every `run_turn` call.**
6. **Empty model replies do not crash a turn.**
7. **Tests from Section 9 are present and passing.**
8. **Persistence boundaries follow Section 11.1: Blueprint domain fields in Postgres, `conversation_history` deferred to Foundry-managed thread memory once Hosted Agents migration is active.**
9. **Per-user authorization invariant (Phase 6.5): every user-data query is filtered by a `user_id` resolved from a validated Entra ID token, never from client-supplied input. Cross-tenant access denial test is present and passing.**
