# FutureSelf — Agent Instructions (Single Source of Truth)

## Project Overview
FutureSelf is a single-agent longevity guidance system .
The orchestrator reasons across all health domains internally using domain skills loaded on demand via the Microsoft Agent Framework (MAF) SkillsProvider.

## Source of Truth Precedence

When rebuilding or refactoring, resolve conflicts in this order:

1. **`AGENTS.md`** for governance, constraints, and coding standards.
2. **`futureself-spec.md`** for runtime architecture, data contracts, and rebuild checklist.
3. **`prompts/orchestrator.md`** and **`src/futureself/skills/*/SKILL.md`** for role behavior, tone, and domain reasoning.

## Non-Negotiable Architecture Rules
- The **Future Self Synthesizer** is the only user-facing agent.
- All reasoning is performed by a single Claude Opus 4.6 call per turn — no sub-agent fan-out.
- Domain expertise is provided via MAF skills (`SKILL.md` files) loaded on demand via the `load_skill` tool.
- Shared User Blueprint mutations must be controlled (orchestrator only).
- Implement the solution minimizing architecture and codebase complexity, even if it means performing deep refactoring.

## Agent and Skills

**One agent:**
- Future Self Synthesizer (orchestrator) → `prompts/orchestrator.md`

**Six domain skills** (loaded on demand by the agent via `load_skill`):
1. Physical Health → `src/futureself/skills/physical_health/SKILL.md`
2. Mental Health → `src/futureself/skills/mental_health/SKILL.md`
3. Financial → `src/futureself/skills/financial/SKILL.md`
4. Social Relations → `src/futureself/skills/social_relations/SKILL.md`
5. Geopolitics → `src/futureself/skills/geopolitics/SKILL.md`
6. Time Management → `src/futureself/skills/time_management/SKILL.md`

The `SkillsProvider` injects skill names and descriptions into the agent's system prompt at session start. The agent calls `load_skill("<name>")` to retrieve the full SKILL.md content for any domain it determines is relevant. No LLM call is consumed by skill loading — it is a tool call response.

## Coding Standards
- Public functions require type hints and docstrings.
- Shared User Blueprint mutations must be controlled (orchestrator only).
- Invalid or malformed model output must never crash a turn. Parsing must degrade gracefully to safe defaults.
- Tests go in `tests/` mirroring `src/`.
- Observability: MAF built-in OTel exports to Azure Application Insights via `azure-monitor-opentelemetry`. Configured at startup in `web/app.py` via `APPLICATIONINSIGHTS_CONNECTION_STRING`. No custom span instrumentation code.
- Run on the Cloud. Deploy to Azure Container Apps (Southeast Asia) via `deploy.yml`. Dockerfile runs `uvicorn futureself.web.app:app` on port 8000.

## Skill File Conventions
- Each skill file is `src/futureself/skills/<domain>/SKILL.md`.
- SKILL.md files have YAML frontmatter with `name` and `description` fields, followed by the full domain system prompt in Markdown.
- The `description` field (1–3 sentences) is what the agent reads upfront when deciding whether to load a skill.
- Skill prompt body follows the structure: **Role → Domain Expertise → Prioritization Framework → Guidelines → Output Format**
- `prompts/orchestrator.md` is NOT a skill — it is the agent's system prompt.

## Current Phase
Phase 6 (The Data): User persistence, supplement tracking, biomarker history, blueprint data quality, conversation history population.

Architecture refactoring is complete: single Claude Opus 4.6 agent with MAF SkillsProvider replaces the 6-stage supervisor-worker pipeline. LLM calls reduced from 7–11 to 1 per turn.

Phase 5 (Observability) is complete: `LLMCallTrace` for every LLM call (model, tokens, latency), deterministic evaluation framework (`eval.py`), `simulate.py --eval/--traces/--eval-json` flags. Application Insights wired via `azure-monitor-opentelemetry`.

Phase 4 (Model router and cloud) is complete: dual LLM provider support (Anthropic direct + Azure AI Foundry), containerized deployment on Azure Container Apps (Southeast Asia).

## Explicit Do-Not-Do
- No sub-agent direct user addressing.
- No orchestrator bypass.
- No multi-agent fan-out or critique rounds.
- No custom OpenTelemetry instrumentation code.

## Key Files
- `futureself-spec.md` — runtime architecture, contracts, rebuild checklist
- `prompts/orchestrator.md` — agent system prompt (identity, tone, responsibilities)
- `src/futureself/skills/` — domain SKILL.md files
- `tests/` — test suite mirroring `src/`
- `scenarios/` — live test YAML scenarios
- `main.py` — Foundry Hosted Agent Service entrypoint
- `infra/azure/main.bicep` — Azure deployment template

## CI/CD
- **`ci.yml`** — runs on every push/PR to `main`: installs deps, runs `pytest tests/ -v`.
- **`live.yml`** — manual dispatch only: requires Azure credentials, runs live scenario tests.
- **`deploy.yml`** — manual dispatch: builds container, pushes to ACR, deploys to Foundry Hosted Agent Service.
- `main` is the default branch. CI must pass before merging.
