# 11. The factory refuses to claim maintainability

* Status: Accepted
* Date: 2026-09-12
* Deciders: operator
* Supersedes: none
* Related: [ADR-0009](0009-no-oracle-no-autonomy.md), [ADR-0008](0008-the-model-is-advisory-only.md), [ADR-0006](0006-the-verifier-cannot-reach-the-executor.md)
* Source: [S24](../sources/s24-harness-engineering-is-not-enough.md)

## Context

[ADR-0009](0009-no-oracle-no-autonomy.md) established that autonomy is bounded by what
an oracle can witness: no oracle, no autonomy. [S24] is the strongest published
objection to that idea being *sufficient*, and it deserves a decision rather than a
rebuttal.

The objection: coding models are trained by RLVR against bounded pass/fail rewards,
that reward shape contains no term for design quality, and the cost of bad architecture
arrives weeks or months after the decision that caused it — so the reward cannot be
assigned to the action. Horthy's prescription is to move human judgment earlier
(Product Review → Architecture → Program Design → Vertical Slices) and his conclusion
is that the human stays the judge. He states plainly that he cannot prove the
underlying degradation claim, because no benchmark measures it.

Two things follow that this project should not paper over. First, SoFact is a harness,
so it **cannot** answer a training-side objection — only bound its own claims. Second,
v0.4 had a real defect: it attached a single per-module autonomy ceiling, so a green
suite about *"this obligation was satisfied"* silently licensed the entirely different
claim *"this can be maintained autonomously."* No oracle in O1–O8 observes change cost.
The second claim was never checkable and was being made by adjacency.

The distinction is not pedantic. The two claims differ in what would falsify them, in
who bears the cost when they are wrong, and in when the cost arrives: obligation
satisfaction is falsified in seconds by re-running the oracle, while a maintenance
claim is falsified months later by a developer who cannot make a one-line change in
one place.

## Decision

We separate the two claims and refuse the second one.

1. **Evolvability debt is a first-class, explicitly-defaulted debt term.** It sits
   beside ground-truth debt (FR-108) and, in v1, its value is **1.0 by construction**
   for every module — because no oracle in O1–O8 observes change cost. A debt of 1.0
   is not a measurement failure; it is the correct value, and it must be reported.
2. **Mode M's ceiling is L1 until a change-cost oracle exists.** Mode M's claim is
   maintenance, so it is exactly the claim that is unverifiable. Mode G's ceiling is
   unaffected, because Mode G's claim is obligation satisfaction — a strictly narrower
   and genuinely checkable claim. The ceilings are not a single number and must not be
   reported as one.
3. **No delivery report may present a green suite as evidence of maintainability.**
   The delivery report must state, in [S24]'s terms, that maintainability was not
   verified.
4. **NFR-024 governs the gap.** A proxy may not be substituted for this term without
   being declared a proxy. The one admissible differential instrument is change
   amplification (FR-159), which measures *change cost*, not design quality, and is
   admissible only as a trend alarm.

## Consequences

* Mode M's ceiling is capped at L1, which under D17 is a capability cost rather than a
  commercial one. It is recorded as R30 rather than hidden.
* The delivery report gains a permanent negative finding. That is the intended
  behaviour: the report's purpose is to make the boundary of what was verified
  legible, and a report that only ever lists successes is the artifact R22 describes.
* FR-159 opens a path out of L1 that requires **no new model capability** — which is
  the point, since [S24]'s thesis is that new model capability is what will not arrive.
  Whether to build it is D18, deliberately left open rather than assumed.
* FR-160 follows from the same reasoning applied to the factory's own economics: if
  review is the binding constraint once implementation is agent-driven, and this
  factory measures its throughput but not its review cost, then it is optimising its
  cheapest step. SoFact measured the producer's budget and not the reviewer's.

## Evidence

The refusal is enforced by the type system rather than by documentation. `verify()` in
`verification.py:183` has the signature:

```python
def verify(contract: Contract, evidence: Iterable[Evidence]) -> VerificationReport:
```

It takes no `CompletionClaim`, so no producer's assertion can reach a verdict — this is
ADR-0009's guarantee, and it is what makes item 3 above checkable rather than aspirational.
The tests asserting it are `test_declaring_completion_changes_no_verdict`
(`tests/ci/test_pipeline.py:77`) and `test_a_success_claim_does_not_survive_a_failing_oracle`
(`tests/ci/test_pipeline.py:39`).

That no oracle observes change cost is verifiable by enumeration: `_RULES` in
`verification.py` covers `EvidenceKind` values that are all outputs of executing a
declared oracle command, and `OracleClass` in `views.py` has no member describing a
change-cost measurement. The absence is therefore structural and can be re-checked
whenever an oracle class is added.

The differential instrument in FR-159 is specified and **unbuilt**. This record
deliberately does not claim it works; D18 is where that is decided, after M0.
