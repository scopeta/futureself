---
name: implement-futureself-specialized-agent
description: Scaffolds and wires a new FutureSelf worker agent module with the required response schema, prompt loading, tests, and orchestrator registration. Use when asked to "add a new agent", "create a domain agent", "implement a worker agent", "wire an agent into the orchestrator", "modify the AgentResponse contract", or "add critique-round support to an agent".
---

# Implement a FutureSelf Specialized Agent

## Instructions

### Step 1: Implement the agent module

Create `src/agents/<domain_name>.py`.

1. Load the prompt from `prompts/<domain_name>.md` at init (never inline).
1. Expose one public entrypoint — `run()`. See `references/schemas.md` for the
   full function signature and dataclass definitions.
1. All model calls go through `src/llm/provider.py` (LLM-agnostic).
1. Treat `user_blueprint` as **read-only**. New facts go into
   `key_facts_extracted`; the orchestrator merges them.
1. Never import or call other agent modules. Agents are isolated workers.

### Step 2: Handle critique rounds

The orchestrator may re-invoke `run()` with a `CritiqueContext` when it detects
conflicting advice across domains.

When `critique_context` is present:
- Set `is_refined = True` in the response.
- Substantively address `orchestrator_question` — adjust advice or defend with
  reasoning.
- May adjust `confidence`.

See `references/schemas.md` for `CritiqueContext` fields and
`references/orchestrator-flow.md` for how critique rounds fit into the pipeline.

### Step 3: Register with the orchestrator

In `src/orchestrator.py`, add the agent to `AGENT_REGISTRY`:

```python
from src.agents.<domain_name> import run as <domain_name>_run

AGENT_REGISTRY["<domain_name>"] = <domain_name>_run
```

### Step 4: Write tests

Create `tests/agents/test_<domain_name>.py`. Mock all model calls — zero real
API calls.

Required test cases:
- Schema validity (confidence in 0–1, domain matches, advice non-empty)
- Blueprint immutability (deep-copy before, assert equal after)
- Critique round sets `is_refined = True`
- Tradeoff flags use plain language (no "agent" references)

See `references/schemas.md` for the full test template.

## Examples

### Example 1: Add a new nutrition-supplements agent

User says: "Add a new agent for nutrition supplements."

Actions:
1. Create `prompts/supplements.md` with domain scope and constraints.
1. Implement `src/agents/supplements.py` with `run()`.
1. Verify output matches `AgentResponse` contract.
1. Register in `AGENT_REGISTRY`.
1. Add tests in `tests/agents/test_supplements.py`.

Result: New agent is callable by the orchestrator and produces
contract-compliant output with all schema fields populated.

### Example 2: Add critique-round support to an existing agent

User says: "The financial agent doesn't handle critique rounds yet."

Actions:
1. Update `run()` signature to accept `critique_context: CritiqueContext | None`.
1. When present, respond to `orchestrator_question` and set `is_refined = True`.
1. Add `test_critique_round_sets_is_refined` test.

Result: Agent participates in orchestrator conflict-resolution rounds.

## Troubleshooting

Error: Agent addresses the user directly in `advice`.
Cause: The agent prompt uses second-person ("you should…").
Solution: Rewrite the prompt and `advice` output as an internal memo to the
orchestrator. Only the orchestrator speaks to the user.

Error: Blueprint mutation detected in tests.
Cause: Agent appends to `user_blueprint` fields directly.
Solution: Move changes into `key_facts_extracted` for orchestrator-controlled
merging.

Error: Tradeoff flags reference other agents by name.
Cause: Agent has knowledge of peer agents.
Solution: Use plain-language concern areas ("cost", "time commitment") instead.
Agents have zero knowledge of other agents.

## Checklist

- [ ] System prompt in `prompts/`, not inlined
- [ ] `AgentResponse` fully populated (confidence, domain, key_facts, advice, tradeoff_flags, is_refined)
- [ ] `advice` is an internal memo, not user-addressed
- [ ] `tradeoff_flags` use plain language — no agent names
- [ ] `UserBlueprint` never mutated
- [ ] No imports or calls to other agent modules
- [ ] LLM calls go through provider abstraction
- [ ] Type hints and docstrings on all public functions
- [ ] `run()` accepts `critique_context: CritiqueContext | None`
- [ ] `is_refined = True` when critique context present
- [ ] Tests at `tests/agents/test_<domain_name>.py`, mocked, passing
- [ ] Agent registered in `AGENT_REGISTRY`
