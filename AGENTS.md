# FutureSelf — Agent Instructions (Governance & Standards)

This file is the **governance layer** for FutureSelf: non-negotiable rules, coding standards,
and pointers to the runtime spec. Architecture, data contracts, deployment topology, and phase
status live in `futureself-spec.md` — do not duplicate them here.

## Project Overview
FutureSelf is a single-agent longevity guidance system. The orchestrator reasons across all
health domains via a single LLM call per turn, using domain skills loaded on demand through
the Microsoft Agent Framework (MAF) `SkillsProvider`.

## Source of Truth Precedence
When rebuilding or refactoring, resolve conflicts in this order:

1. **`AGENTS.md`** — governance, constraints, coding standards (this file).
2. **`futureself-spec.md`** — runtime architecture, data contracts, deployment, phases, rebuild checklist.
3. **`prompts/orchestrator.md`** and **`src/futureself/skills/*/SKILL.md`** — role behavior, tone, domain reasoning.

## Non-Negotiable Architecture Rules
- The **Future Self Synthesizer** is the only user-facing agent.
- **One LLM completion per turn** — no sub-agent fan-out, no critique rounds, no multi-pass refinement.
- Domain expertise is delivered exclusively via MAF skills (`SKILL.md` files) loaded on demand
  through the `load_skill` tool. No hardcoded domain prompts in the orchestrator.
- **Blueprint mutations are orchestrator-only** and must use `model_copy` (never in-place mutation).
- Prefer deep refactoring over accumulating complexity. When in doubt, simplify.

## Coding Standards
- Public functions require type hints and docstrings.
- Invalid or malformed model output must never crash a turn — parsing degrades to safe defaults.
- Tests live in `tests/`, mirroring the `src/` layout.
- Observability uses MAF's built-in OpenTelemetry → Application Insights via
  `azure-monitor-opentelemetry`, configured once at startup in `web/app.py`.
  **No custom span code.**
- Lazy-import cloud SDKs (`agent_framework_*`) inside builder functions so local dev works
  without the cloud stack installed.

## Explicit Do-Not-Do
- No sub-agent directly addressing the user.
- No bypassing the orchestrator for blueprint writes.
- No multi-agent fan-out, debate, or critique rounds.
- No custom OpenTelemetry instrumentation code.
- No duplicating spec content (architecture, deployment, phases) into this file.

## Key Files
- `futureself-spec.md` — runtime architecture, contracts, deployment, rebuild checklist.
- `prompts/orchestrator.md` — agent system prompt.
- `src/futureself/skills/<domain>/SKILL.md` — domain skill files.
- `src/futureself/orchestrator.py` — `run_turn` implementation.
- `tests/` — unit and integration tests (live tests gated by the `live` marker).
- `scenarios/` — live scenario YAML files.
- `infra/azure/main.bicep` — Azure deployment template.

## CI/CD
- **`ci.yml`** — runs on every push/PR to `main`: installs deps, runs `pytest tests/ -v`.
  Live tests are excluded by default (`-m 'not live'`).
- **`live.yml`** — manual dispatch only; requires Azure credentials; runs live scenario tests.
- **`deploy.yml`** — manual dispatch; builds container, pushes to ACR
  (`futureselfacr.azurecr.io`), deploys to Azure Container Apps (Southeast Asia).
- `main` is the default branch. CI must pass before merging.
