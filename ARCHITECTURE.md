# FutureSelf — Architecture & Functionality Guide

> An explanatory, diagram-first overview of how FutureSelf is built and how a
> request flows through it. For **normative contracts, data schemas, and the
> rebuild checklist** see [`futureself-spec.md`](./futureself-spec.md); for
> **governance and coding rules** see [`AGENTS.md`](./AGENTS.md). This document
> is the friendly map; those two are the law.

---

## 1. What FutureSelf is

FutureSelf is a **single-agent longevity guidance system**. The user talks to
one persona — their "Future Self" — which reasons holistically across health
domains (physical, mental, financial, social, geopolitical, time) and gives
personalized, long-horizon advice.

The defining design choices:

- **One user-facing agent.** No sub-agent fan-out, no debate/critique rounds.
- **One LLM completion per turn** (plus zero-cost tool calls to load skills).
- **Domain expertise lives in skills**, not in the orchestrator prompt — loaded
  on demand via the Microsoft Agent Framework (MAF) `SkillsProvider`.
- **The orchestrator is the only writer of the user's Blueprint**, and it
  mutates it immutably (`model_copy`, never in place).

---

## 2. High-level architecture

```mermaid
flowchart TD
    subgraph Browser
        UI["React + Vite SPA<br/>chat + blueprint pages"]
    end

    subgraph Backend["FastAPI BFF — web/app.py"]
        Routes["routes/api.py<br/>/api/* endpoints"]
        SessionMod["session.py<br/>Bearer token to user"]
        Client["web/agent_client.py<br/>synthesize + apply_turn"]
    end

    subgraph FoundryAgent["Foundry Hosted Agent — main.py"]
        Host["Responses host<br/>Azure AI, stateless per caller"]
        Builder["orchestrator.build_agent<br/>single agent builder"]
        Agent["MAF Agent + SkillsProvider"]
        Skills["skills/*/SKILL.md<br/>6 domains, load on demand"]
    end

    Claude["Claude — AnthropicClient<br/>1 turn = 1-2 completions"]
    DB[("PostgreSQL<br/>users / blueprints / sessions")]

    UI -->|"Bearer token + JSON"| Routes
    Routes --> SessionMod
    SessionMod <-->|"load / save Blueprint"| DB
    Routes --> Client
    Client -->|"HTTPS Responses<br/>Entra auth, full context"| Host
    Host --> Builder --> Agent
    Agent -->|"load_skill"| Skills
    Agent -->|"chat completion"| Claude
    Claude -->|"reply"| Agent --> Host
    Host -->|"reply"| Client --> Routes --> UI
```

**One agent, called over HTTP.** The agent runs in exactly one place — the
Foundry Hosted Agent (`main.py`), built by the single `orchestrator.build_agent`.
The BFF no longer runs it in-process: `web/agent_client.py` sends the full
per-turn context to the agent's **stateless** Responses endpoint (Microsoft
Entra auth) and keeps Postgres as the system of record for the Blueprint —
including conversation history. See
[`futureself-spec.md` §11](./futureself-spec.md).

---

## 3. The turn lifecycle

What happens on a single `POST /api/chat/send`:

```mermaid
sequenceDiagram
    actor U as User SPA
    participant API as routes/api.py
    participant S as session.py
    participant DB as PostgreSQL
    participant CL as agent_client
    participant H as Hosted Agent (main.py)
    participant C as Claude

    U->>API: POST /api/chat/send (Bearer token, message)
    API->>S: resolve token to user_id + Blueprint
    S->>DB: SELECT blueprint by session token
    DB-->>S: UserBlueprint (JSON)
    S-->>API: UserBlueprint
    API->>CL: synthesize(blueprint, message)
    CL->>CL: build per-turn context (profile + facts + history + message)
    CL->>H: POST /responses (Entra auth, store=false)
    H->>C: agent.run → load_skill(s) + single synthesis completion
    C-->>H: Future Self reply
    H-->>CL: response.output_text
    CL-->>API: reply
    API->>API: apply_turn → extract facts (regex) + model_copy Blueprint
    API->>S: save updated Blueprint
    S->>DB: UPDATE blueprints.data
    API-->>U: reply JSON
```

Key invariants enforced here:

- **One agent, one synthesis pass per turn.** `load_skill` is a tool call, so the
  model resumes after the tool result: a turn that loads skills costs **~2
  completions** (one to request the skill(s), one to synthesize), one that loads
  none costs 1. Still a single agent — no fan-out, no critique rounds. (Verified
  in prod via App Insights: `chat` spans ≈ 2× `invoke_agent` spans.)
- **Immutability.** `apply_turn` returns a *new* Blueprint via `model_copy`; it
  never mutates the input.
- **Graceful degradation.** An empty model reply yields an empty `reply` rather
  than crashing; a hosted-agent failure returns a retryable **503**, never a raw 500.
- **Stateless agent, durable Postgres.** The agent endpoint stores nothing per
  caller (`store=false`); the BFF sends the full context each turn and owns the
  conversation history.

---

## 4. Skills: progressive domain disclosure

Domain knowledge is **not** baked into the system prompt. Each domain is a
folder with a `SKILL.md` (YAML frontmatter `name` + `description`, then the
domain reasoning body).

```mermaid
flowchart LR
    SP["SkillsProvider.from_paths skills/"] --> M["Inject manifest into system prompt<br/>name + description only, ~100 tokens each"]
    M --> D{"LLM decides<br/>which domains are relevant"}
    D -->|"load physical-health"| B1["return full SKILL.md body"]
    D -->|"load financial"| B2["return full SKILL.md body"]
    B1 --> Synth["Synthesize Future Self reply"]
    B2 --> Synth
```

The six skills (each `src/futureself/skills/<name>/SKILL.md`):

| Skill | `name` (key) | Focus |
|-------|--------------|-------|
| Physical Health | `physical-health` | Nutrition, exercise, sleep, biomarkers, medical-risk-aware longevity |
| Mental Health | `mental-health` | Stress, emotional regulation, resilience, crisis signals |
| Financial | `financial` | Long-horizon planning, risk control, healthcare affordability |
| Social Relations | `social-relations` | Loneliness reduction, relationship quality, community |
| Geopolitics | `geopolitics` | Location risk (air quality, climate, stability, healthcare access) |
| Time Management | `time-management` | Turning strategy into executable habits and schedules |

> **MAF naming constraint:** a skill's frontmatter `name` must **match its
> directory name** and use only lowercase letters, numbers, and hyphens
> (no underscores). MAF silently skips any `SKILL.md` that violates this,
> which disables that domain.

---

## 5. Data model

### 5.1 Persistence (PostgreSQL)

```mermaid
erDiagram
    users ||--|| blueprints : has
    users ||--o{ sessions : has

    users {
        uuid id PK
        datetime created_at
    }
    blueprints {
        uuid id PK
        uuid user_id FK
        json data "full UserBlueprint, JSONB"
        datetime updated_at
    }
    sessions {
        string token PK
        uuid user_id FK
        string thread_id "reserved for Foundry Agent Service"
        datetime created_at
    }
```

A session **Bearer token** maps to a user; each user has one `blueprints` row
whose `data` column stores the entire `UserBlueprint` serialized as JSON(B).
Schema is managed by Alembic (`alembic/versions/`).

### 5.2 Domain object (`UserBlueprint`, in `schemas.py`)

The Blueprint is a frozen Pydantic model — the user's evolving profile:

- **`bio`** — age, sex, height/weight, conditions, medications, supplements,
  biomarker history, exam records.
- **`psych`** — goals, fears, stress level, mental-health flags.
- **`context`** — location, occupation, income, family, lifestyle notes.
- **`conversation_history`** — list of `{role, content}` turns.
- **`inferred_facts`** — facts extracted from replies (regex, no LLM).

Other contracts: `OrchestratorResult` (reply + updated Blueprint + traces) and
`LLMCallTrace` (per-turn task/model/latency). Full field-level detail is in
[`futureself-spec.md` §5](./futureself-spec.md).

---

## 6. Provider selection & deployment topology

The same agent builder supports two backends, chosen by environment variable:

```mermaid
flowchart TD
    Start["build_agent model"] --> Q{"AZURE_FOUNDRY_ENDPOINT set?"}
    Q -->|"yes"| F["FoundryChatClient<br/>Entra ID auth, model-agnostic"]
    Q -->|"no"| Akey{"ANTHROPIC_API_KEY set?"}
    Akey -->|"yes"| AC["AnthropicClient<br/>Claude direct — ACTIVE"]
    Akey -->|"no"| Err["raise ValueError"]
```

- **Active deployment:** Anthropic direct, `FUTURESELF_MODEL=claude-opus-4-8`.
- **Optional:** Azure AI Foundry (any Foundry-deployed model) via the
  Responses host in `main.py`.
- **Cloud target (per CI):** container pushed to ACR and deployed to Azure
  Container Apps; infra in `infra/azure/main.bicep`. Observability is MAF's
  built-in OpenTelemetry → Application Insights (enabled only when
  `APPLICATIONINSIGHTS_CONNECTION_STRING` is set).

---

## 7. Repository map

| Path | Responsibility |
|------|----------------|
| `frontend/` | React + Vite + Tailwind SPA. `lib/api.ts` calls the BFF; chat + Blueprint pages. |
| `src/futureself/web/app.py` | FastAPI factory: CORS, router mount, OTel, serves built SPA. |
| `src/futureself/web/routes/api.py` | JSON REST endpoints (session, chat, blueprint, quality). |
| `src/futureself/web/session.py` | Bearer-token sessions backed by Postgres. |
| `src/futureself/orchestrator.py` | `build_agent` — the single agent builder (run by the hosted agent). |
| `src/futureself/web/agent_client.py` | BFF→hosted-agent client: `synthesize`, context build, fact extraction, `apply_turn`. |
| `src/futureself/schemas.py` | Pydantic data contracts (`UserBlueprint`, results, traces). |
| `src/futureself/skills/<name>/SKILL.md` | The six domain skills. |
| `src/futureself/blueprint_quality.py` | Rule-based Blueprint data-quality report (no LLM). |
| `src/futureself/eval.py` | Deterministic scenario assertions (`expect` blocks; no LLM). |
| `src/futureself/judge.py` | LLM-as-judge rubric scorer (offline quality gate). |
| `src/futureself/db/` | SQLAlchemy models + async engine. |
| `alembic/` | Database migrations. |
| `main.py` | Foundry Hosted-Agent Responses host — the single agent runtime. |
| `simulate.py` | CLI harness to run `scenarios/*.yaml` through the hosted agent. |
| `scenarios/` | Multi-turn test scenarios. |
| `prompts/orchestrator.md` | The Future Self system prompt. |
| `infra/azure/`, `.github/workflows/`, `Dockerfile` | Deployment & CI/CD. |
| `tests/` | Unit/integration tests (live tests gated by the `live` marker). |

---

## 8. REST API surface (BFF)

All under `/api`; chat and blueprint routes require `Authorization: Bearer <token>`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/session/create` | Create a blank session, return a session token. |
| `POST` | `/chat/send` | Run one turn; return the Future Self reply. |
| `GET` | `/blueprint` | Read the current Blueprint. |
| `PATCH` | `/blueprint/bio` \| `/context` \| `/psych` | Update a Blueprint section. |
| `POST` | `/blueprint/biomarkers` | Append a biomarker entry. |
| `POST` | `/blueprint/supplements` | Add/replace a supplement (by name). |
| `DELETE` | `/blueprint/supplements/{name}` | Remove a supplement. |
| `GET` | `/blueprint/quality` | Rule-based data-quality report. |

---

## 9. Running it locally

The agent and the BFF are two processes (spec §11). Copy `.env.example` → `.env`
first; it documents which vars belong to which process.

1. **Agent:** set `ANTHROPIC_API_KEY` + `FUTURESELF_MODEL`, then run the hosted
   agent locally: `python main.py` (Responses host on `:8088`).
2. **BFF:** point `FOUNDRY_AGENT_ENDPOINT` at the agent (local `:8088` or the
   deployed endpoint), set `DATABASE_URL` (Postgres), and ensure Azure auth
   (`az login`) when targeting the deployed agent.
3. Install deps with `uv sync --prerelease=allow` (the Foundry hosting SDK is
   beta — see `AGENTS.md` → Hosting SDK).
4. Apply migrations (`alembic upgrade head`) against your Postgres.
5. Backend: `uvicorn futureself.web.app:app --reload`.
6. Frontend: `cd frontend && bun install && bun run dev` (set `VITE_API_URL` to
   the backend origin).

**Fast paths that need no DB or browser:**

- Scenario harness: `python simulate.py --scenario <name>` (drives the hosted
  agent via `agent_client.synthesize`; needs `FOUNDRY_AGENT_ENDPOINT` + Azure auth).
- Tests: `pytest` (live LLM tests are excluded by default).

---

## 10. Evaluation (the reviewer for a solo project)

With no human PR reviewer, an automated **evaluator** is the quality gate before
changes land on `main`. It runs in two tiers:

```mermaid
flowchart LR
    subgraph Blocking["Per-push CI — ci.yml, no LLM"]
        U["pytest tests/<br/>incl. evaluator-logic unit tests"]
    end
    subgraph LiveGate["Live Eval Gate — live.yml, real Claude"]
        D["Deterministic assertions<br/>scenario expect blocks — HARD"]
        J["LLM-as-judge rubric<br/>judge.py — advisory floor"]
    end
    U --> D --> J
```

- **Deterministic assertions** (`eval.py` + each scenario's `expect:` block):
  length bounds, required topical keywords (`must_include_any`), and `forbidden`
  phrases (e.g. tool-narration leaks). Objective and repeatable → **hard
  pass/fail**. The *logic* is unit-tested in `ci.yml` (no LLM, blocks every
  push); the *checks against real replies* run in the live tier.
- **LLM-as-judge** (`judge.py`): a Claude judge scores each reply 1–5 against
  `DEFAULT_RUBRIC` plus any scenario-specific `rubric:` criteria. Non-deterministic
  and costs tokens, so it's **advisory** — a score below `JUDGE_FLOOR` (default 3)
  fails to catch egregious regressions. It is offline eval tooling, *not* part of
  the runtime agent (the one-agent / one-completion rules govern the hosted agent only).

Run it locally before merging:

```bash
python simulate.py --scenario motorcycle_purchase --eval --judge
pytest tests/scenarios/ -m live -v            # all scenarios, both tiers
```

Or trigger the **Live Eval Gate** workflow on GitHub (`live.yml`,
`workflow_dispatch`; needs the `ANTHROPIC_API_KEY` secret).

## 11. Where to go deeper

- **Contracts, persistence boundaries, rebuild checklist:** [`futureself-spec.md`](./futureself-spec.md)
- **Governance, coding standards, do-not-do list:** [`AGENTS.md`](./AGENTS.md)
- **Agent behavior & tone:** [`prompts/orchestrator.md`](./prompts/orchestrator.md)
- **Domain reasoning:** `src/futureself/skills/<name>/SKILL.md`
```
