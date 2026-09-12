# 0008 — The model is advisory only

- **Status:** Accepted (records D17)
- **Date:** 2026-09-12

## Context

SoFact uses a language model for one narrow job: reading an operator's answer to an
interrogation question and saying whether it looks thin. Everything else — whether a
dimension is resolved, whether a contract may be built, whether a clause holds — is
mechanical.

The temptation is to let the model do more. It writes fluent rationales, it can
propose clause stems, and an "AI-native" product is expected to defer to its model.
Two considerations pushed the other way:

1. **A model is an oracle of unmeasured strength.** Spec F7 records the one place a
   model legitimately becomes a *second* oracle class, and it comes with the
   requirement that it be explicit and bounded. An unexplained model judgement is
   indistinguishable from a guess.
2. **The commercialisation question was settled separately (D17).** With no market
   to serve, there is no external signal that could validate a model-driven
   decision — and no product strategy that would justify optimising for one.

There is also a plain operational reason: the configured default model is routed
through a cloud service (ADR-0002) and may simply be unreachable. A design where the
model's absence is fatal cannot run offline, which contradicts the deployment promise.

## Decision

**The model may advise; it may never decide.**

- Advice is recorded as an `ADVISOR_NOTE` event. It is never an input to a gate, a
  verdict, or a budget change.
- The `Advice` type models *failure explicitly* rather than returning `None`, so "the
  advisor had nothing to add" and "the advisor was unreachable" cannot be silently
  collapsed into each other.
- SoFact runs with **no model at all**. `FactoryService(home=..., llm=None)` is a
  supported configuration, and it is the one the test suite uses: the deterministic
  path is the product, and the model is a convenience layered on it.
- A missing or unreachable advisor degrades to the plain questionnaire. It never
  blocks, never retries into a wall, and never fails a goal.
- **Commercialisation is not a goal.** The objective is capability: imagine a product
  and create it efficiently. §19 of the specification is optional context and may not
  justify any requirement.

## Evidence

- The CLI announces the advisor's state at startup and continues on "unreachable —
  continuing with the plain questionnaire".
- The `_no_network` autouse fixture points every test at a closed port, so the whole
  suite runs with the advisor unreachable and still passes. This is the strongest form
  of the claim: the model's absence is the default test condition.
- Spec F12 (`elicit` = 0 across the surveyed ecosystem) means the model's advice runs
  on the *one* phase where SoFact has no competitors to imitate and no benchmark to
  borrow. Advice there is a genuine convenience, not a crutch for a crowded feature.

## Consequences

- SoFact's correctness claims are checkable without a model, which is the only way
  they can be checked reproducibly.
- The model's contribution is unmeasurable by construction. This is a real loss:
  there is no metric showing the advice improved outcomes, and none is claimed.
- Under D17, verification carries *more* load rather than less. With no market as an
  oracle, verification is the only oracle SoFact has — which is why the verifier half
  is the part that was built first, and why FR-155's deletion test (adopt a third-party
  plugin only if SoFact reaches the same verdict without it) is a consequence of this
  decision rather than a separate policy.
