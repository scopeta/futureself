# FutureSelf — Agent Instructions (Single Source of Truth)

## Project Overview
FutureSelf is a Supervisor-Worker multi-agent system for longevity guidance.

## Source of Truth Precedence

When rebuilding or refactoring, resolve conflicts in this order:

1. **`AGENTS.md`** for governance, constraints, and coding standards.
2. **`futureself-spec.md`** for runtime architecture, data contracts, and rebuild checklist.
3. **`prompts/*.md`** for role behavior, tone, and domain reasoning.

## Non-Negotiable Architecture Rules
- The **Future Self Synthesizer** is the only user-facing agent.
- Sub-agents never communicate peer-to-peer; all traffic goes through orchestrator.
- Keep orchestration **LLM-agnostic** via provider abstraction interfaces.
- Use two memory tiers:
  - short-term conversation context
  - long-term vector retrieval for User Blueprint
- Implement the solution minimizing architecture and codebase complexity, even if it means performing deep refactoring.

## Agent Set (7)
1. Future Self Synthesizer (orchestrator) → `prompts/orchestrator.md`
2. Physical Health Agent → `prompts/physical_health.md`
3. Mental Health Agent → `prompts/mental_health.md`
4. Financial Agent → `prompts/financial.md`
5. Social Relations Agent → `prompts/social_relations.md`
6. Geopolitics Agent → `prompts/geopolitics.md`
7. Time Management Agent → `prompts/time_management.md`

## Coding Standards
- Use Python modules per agent.
- Load each system prompt from `prompts/`.
- Public functions require type hints and docstrings.
- Shared User Blueprint mutations must be controlled (orchestrator only).
- All LLM traffic must go through `LLMProvider`.
- Agent responses must include the **base contract** (see `futureself-spec.md` Section 5.1 for full details):
  - `confidence: float` (0.0–1.0)
  - `domain: str`
  - `advice: str`
  - `urgency: str` ("low" | "medium" | "high" | "critical")
- Domain-specific extensions are allowed alongside the base fields.
- Invalid or malformed model JSON must never crash a turn. Parsing must degrade gracefully to safe defaults.
- Tests go in `tests/` mirroring `src/`.
- Enable OpenTelemetry.
- Run on the Cloud. Design agnostic of provider through abstraction interfaces. Initally focused on Microsoft stack.


## Prompt File Conventions
- Each prompt file in `prompts/` is plain Markdown, loadable directly as a system prompt.
- Worker prompts follow a consistent structure:
  **Role → Domain Expertise → Prioritization Framework → Guidelines → Output Format**
- The orchestrator prompt has its own structure (Identity, Tone, Responsibilities, Conflict Resolution, Response Format).
- All worker prompts must include an explicit coordination line naming which other agents to coordinate with through the orchestrator.

## Current Phase
Phase 4 (Model router and cloud): Initially focused on Microsoft stack, like Foundry and its model router. Designed agnostic of provider through abstraction interfaces.  

## Explicit Do-Not-Do
- No sub-agent direct user addressing.
- No orchestrator bypass.

## Key Files
- `futureself-spec.md` — runtime architecture, contracts, rebuild checklist
- `prompts/` — agent system prompts
- `tests/` — test suite mirroring `src/`
- `scenarios/` — live test YAML scenarios

## CI/CD
- **`ci.yml`** — runs on every push/PR to `main`: installs deps, runs `pytest tests/ -v`.
- **`live.yml`** — manual dispatch only: requires `OPENAI_API_KEY` secret, runs live scenario tests.
- `main` is the default branch. CI must pass before merging.
- Secret `OPENAI_API_KEY` is only needed for live scenario tests.
