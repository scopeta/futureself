# FutureSelf — Agent Instructions (Single Source of Truth)

## Project Overview
FutureSelf is a Supervisor-Worker multi-agent system for longevity guidance.

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
- Shared User Blueprint mutations must be controlled.
- Agent responses must include the **base contract**:
  - `confidence: float` (0.0–1.0)
  - `domain: str`
  - `advice: str`
  - `urgency: str` ("low" | "medium" | "high" | "critical")
- Domain-specific extensions (e.g., `crisis_flag`, `contraindications`,
  `proposed_schedule_change`) are allowed alongside the base fields.
- Agents must flag tradeoff concerns in plain language when their advice
  has side effects outside their domain.
- Tests go in `tests/` mirroring `src/`.

## Prompt File Conventions
- Each prompt file in `prompts/` is plain Markdown, loadable directly as a
  system prompt.
- Worker prompts follow a consistent structure:
  **Role → Domain Expertise → Prioritization Framework → Guidelines → Output Format**
- The orchestrator prompt has its own structure (Identity, Tone, Responsibilities,
  Conflict Resolution, Response Format).
- All worker prompts must include an explicit coordination line naming which
  other agents to coordinate with through the orchestrator.

## Current Phase
Phase 2: The Orchestrator.

## Explicit Do-Not-Do
- No frontend work before Phase 3.
- No hard dependency on a specific vector DB/cloud provider.
- No sub-agent direct user addressing.
- No orchestrator bypass.

## Key Files
- `futureself-spec.md`
- `prompts/`
- `tests/`

## CI/CD
- **`ci.yml`** — runs on every push/PR to `main`: installs deps, runs `pytest tests/ -v`.
- **`live.yml`** — manual dispatch only: requires `OPENAI_API_KEY` secret, runs live scenario tests.
- `main` is the default branch. CI must pass before merging.
- Secret `OPENAI_API_KEY` is only needed for live scenario tests.
