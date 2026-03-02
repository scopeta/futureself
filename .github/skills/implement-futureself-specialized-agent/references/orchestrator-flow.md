# Orchestrator Flow: Reactive Pipeline

This document describes how agent responses flow through the orchestrator.
Agent developers do not implement this — it exists so they understand the
lifecycle their output enters.

## Reactive flow (user-initiated)

```
User message
  → Orchestrator
      ├─ Phase 1: Parallel fan-out
      │   → Agent A.run()  → AgentResponse
      │   → Agent B.run()  → AgentResponse
      │   → Agent C.run()  → AgentResponse
      │
      ├─ Conflict detection (orchestrator's own LLM call)
      │   Compares the substance of all agent advice across domains.
      │   Identifies tensions:
      │     "A's advice costs $200/mo; B's budget analysis says $50 max."
      │
      ├─ Phase 2: Critique rounds (only if conflicts detected)
      │   → Agent A.run(critique_context=CritiqueContext{
      │         conflicting_advice="...",
      │         concern_area="cost",
      │         orchestrator_question="Can you achieve similar outcomes
      │           within a $50/month budget?",
      │         round_number=1,
      │       })  → refined AgentResponse (is_refined=True)
      │   → Agent B.run(critique_context=...)  → refined AgentResponse
      │   → Repeat up to MAX_CRITIQUE_ROUNDS (default: 2)
      │
      └─ Synthesize → User-facing reply in Future Self persona
```

## Key rules for agent developers

1. **Agents never see each other's output directly.** The orchestrator controls
   what information flows into `CritiqueContext`.

2. **Conflict detection is the orchestrator's job.** Agents optimize within
   their domain. The orchestrator spots tensions by comparing the substance
   of each agent's advice.

3. **Critique rounds are optional.** Most responses go through Phase 1 only.
   Phase 2 triggers only when the orchestrator detects genuine tension.

4. **The orchestrator owns the user-facing persona.** Agent `advice` is an
   internal memo consumed by the synthesizer. Only the orchestrator speaks to
   the user as "Future Self."

## LLM evals (future — Phase 2+)

When the orchestrator is integrated and real LLM calls run end-to-end, add
eval files at `evals/agents/eval_<domain_name>.py` covering:

- Domain fidelity (agent stays in its lane)
- Advice quality (evidence-based, actionable)
- Tone compliance (internal memo, never user-addressed)
- Critique responsiveness (meaningful refinement, not capitulation)
- Hallucination detection (claims grounded in blueprint data)

Use an LLM-as-judge pattern for non-deterministic quality assessment.
These run separately from CI.
