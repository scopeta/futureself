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
- **One agent, one synthesis pass per turn** — no sub-agent fan-out, no critique rounds, no multi-pass refinement. (Skill loading is a tool call: the model resumes after the tool result, so a turn that loads skills costs ~2 LLM completions — one to request the skill(s), one to synthesize — and a turn that loads none costs 1. Still a single agent and a single synthesis pass, never a multi-agent pipeline.)
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
- `ARCHITECTURE.md` — diagram-first architecture & functionality overview (onboarding/explanatory).
- `futureself-spec.md` — runtime architecture, contracts, deployment, rebuild checklist.
- `prompts/orchestrator.md` — agent system prompt.
- `src/futureself/skills/<domain>/SKILL.md` — domain skill files.
- `src/futureself/orchestrator.py` — `build_agent`, the single agent builder (run by the hosted agent in `main.py`).
- `src/futureself/web/agent_client.py` — BFF→hosted-agent client (`synthesize` + bounded `build_user_context`); the BFF no longer runs the agent in-process.
- `src/futureself/web/` — `session.py` (accounts/sessions/transcript), `passwords.py` (email auth), `facts.py` (user-confirmed fact distillation), `curator.py` (rule-based context-quality nudges — a policy module, NOT a second agent), `whatsapp.py` + `routes/whatsapp.py` (Twilio channel).
- `main.py` — Foundry Hosted Agent entrypoint (`ResponsesAgentServerHost` on :8088).
- `agent.yaml` — `azd ai agent` hosted-agent manifest (flat schema: `protocol: responses`, `environment_variables`, Anthropic-direct).
- `Dockerfile.agent` — dedicated image for the hosted agent (runs `python main.py`, not the BFF).
- `azure.yaml` — azd project (agent service → `Dockerfile.agent`); `infra/` holds the generated bicep (reuses the existing Foundry project).
- `tests/` — unit and integration tests (live tests gated by the `live` marker).
- `scenarios/` — live scenario YAML files.
- `infra/azure/main.bicep` — Azure deployment template.

## Hosting SDK
- `azure-ai-agentserver-responses>=1.0.0b5` — Responses protocol host (replaces the abandoned
  `azure-ai-agentserver-agentframework` v1 adapter, frozen upstream March 2026).
- `uv lock --prerelease=allow` / `uv sync --prerelease=allow` required because the hosting SDK
  is still in beta.

## CI/CD
- **`ci.yml`** — runs on every push/PR to `main`: installs deps, runs `pytest tests/ -v`.
  Live tests are excluded by default (`-m 'not live'`).
- **`live.yml`** — manual dispatch only; requires Azure credentials; runs live scenario tests.
- **`deploy.yml`** — continuous deployment gated on green CI: a successful `ci.yml`
  run on `main` triggers it via `workflow_run` (manual dispatch also supported).
  Builds the container, pushes to ACR, and rolls it out to Azure Container Apps
  (Southeast Asia) as a **zero-downtime update** (`az containerapp update --image`;
  stable URL, old revision serves until the new one is healthy; creates the app on
  first run). It also enables the BFF's **system-assigned managed identity** and
  grants it the Foundry "Azure AI User" role (GUID `53ca6127-…`) on
  `FOUNDRY_RESOURCE_ID` so the BFF can call the hosted agent. New required
  secrets: `FOUNDRY_AGENT_ENDPOINT` (agent Responses base URL) and
  `FOUNDRY_RESOURCE_ID` (Foundry account ARM id, the role scope). If the CI
  principal lacks Owner/UAA on that scope, the grant warns instead of failing —
  run `infra/grant-bff-foundry-role.sh` once with elevated creds.
- `main` is the default branch. CI must pass before merging.
