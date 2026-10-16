# 0070 — The front door stops at every gate, and a model's answer is not an answer

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** FR-061, FR-168, FR-172, FR-173, FR-174, NFR-024, ADR-0007, ADR-0021;
  [ADR-0064](0064-the-authoring-surfaces-cannot-reach-a-model.md)

## Context

The operator asked for a system that could take a description of what they want and carry it
to a built, verified platform — and, separately, that it "must include web search and deep
research to find answers and competitive information". Three of the seven capabilities that
implies did not exist in this tree in any form: transcription, notification, and any single
verb that drives the pipeline. A full run today is eleven hand-typed invocations.

The design is constrained on two sides, and both constraints are load-bearing rather than
inconvenient.

**FR-061 makes a gate a hard stop.** `advance_phase` can never pass a gate and
`approve_gate(phase, *, by)` is the only human half. An unattended run therefore *cannot*
reach a delivery without a person, and the honest design is to stop rather than to invent a
way past — a pre-authorization covering a specification, a decomposition and a contract
sample that do not exist yet is exactly what the gate design exists to prevent.

**ADR-0064 keeps model-reaching modules out of the authoring surfaces.** The transitive
import closure of `sofact.elicitation`, `sofact.contract`, `sofact.views` and
`sofact.manufacture` must reach no module in `MODEL_REACHING_MODULES`. Anything that opens a
socket lives outside, and `sofact authorship` is the gate that says so.

## Decision

**A transcriber, a notifier and a search provider are declared external tools.** Each is an
argv template in a JSON table, resolved by name, launched as a child process, judged by the
exit code and the file it wrote — `HarnessSpec`'s shape, for its reason. **No built-in entry
ships for any of the three**, and that is a decision rather than an omission: no
speech-to-text tool, no notification destination and no search index is a dependency of this
product, so there is no ambient one to fall back to. A machine with none configured gets a
refusal naming the variable to set.

This is what makes the operator's "must include web search and deep research" a capability
of the product rather than a request forwarded to someone else. SoFact **authors the
queries** from the goal's own words before any provider runs and writes them into the log,
so what was asked is answerable from the ledger alone. A provider asked what to search for
chooses its own subject list, and the check that the right things were searched would then
be measuring the provider against itself — the same failure `research_goal` prevents by
writing the clause ids into the prompt.

**A search hit is a lead, not a source.** Every hit is recorded at
`VerificationStatus.REPORTED`, the weakest rung, and `SearchHit` refuses to be constructed
at `CONTENT_VERIFIED` at all. A provider returns a title, a url and a snippet it chose and
possibly generated; promoting that to evidence would let a machine-written excerpt be cited
as a page a human read, which is the substitution that enum's own docstring exists to
prevent. A hit with no url is refused outright — a result nobody can look up is not a lead.
A query that failed is recorded as failed rather than as a domain with no results, because
those two call for opposite responses and a hit count alone cannot tell them apart.

**A model-proposed elicitation answer does not resolve a dimension.** `answered_by` is
`NonEmptyStr` and nothing distinguished `"operator"` from `"model:qwen"`, so a model asked to
draft the six answers could clear the deterministic floor — `MIN_STEM_CHARS`, ORACLE's
`required_markers` — with plausible prose that nobody said. That answer would then pass P0
and become a requirement in a specification the operator "approved", and nothing downstream
would fail. It is the "written and never read" defect with a human's signature on it.

`MODEL_ANSWER_PREFIX` and `ElicitationAnswer.is_model_proposed` make the distinction
representable; `ElicitationAttestation` records the human half and refuses an attestation
whose `attested_by` is itself model-prefixed; and `assess(..., attested=...)` reports a
model-proposed unattested answer as **open**, naming the proposal's id. The floor stays
deterministic. What changes is that a paragraph a model wrote can no longer clear it on the
operator's behalf. **Attestation records that a human read an answer, not that it is
correct** — the same distinction `elicitation.py` already draws about the floor.

**The driver stops at every gate and says which.** `sofact build` is a loop over the ledger
rather than a held process, so `--resume` is the same code path as a cold start and a driver
killed mid-run resumes correctly. It has no code path that advances a gate: at each gate it
records a halt, notifies, and returns. Running it twice is a no-op the second time, asserted
on ledger length rather than on the outcome.

**A notification that was not sent is not a notification.** The row is appended whether or
not a process launched, and `delivered` is *derived* from the exit code rather than declared.
A record written only on success would make "we told them" and "we meant to tell them" print
the same line. The subject is composed from the run's terminal state and nothing else, so a
run stopped at a gate cannot produce a message reading "built" — `claims_built` is true for
`DELIVERED` alone.

## Consequences

`sofact authorship` must still report both authoring surfaces clean. It does: the closures
are unchanged at four and five modules, so `search.py`, `notify.py` and `transcribe.py` are
properly outside them, and the dependency arrow points one way.

The operator cannot get a single pre-authorization, and four gates mean four stops for a full
run. That is the cost of FR-061 and it is stated rather than worked around.

**Three defects the driver walk found, all of them the same shape.** Driving a goal to
`DELIVERED` for the first time exercised paths nothing had run, and each failure was a
correct-looking guard reading a fact that was true but not the fact in question.

*The gate was unpassable after its defect was fixed.* `approve_gate` decided on the frozen
presented row. That row is a record of what was *shown*, and the artefact can have been
revised since — which is the ordinary course of a gate the machine half failed, because the
operator's fix is to supply what was missing and propose again. So an operator could supply
the missing halves, watch every check pass, and still be told the gate had failed, with no
exit but a hand-edited ledger. A gate that cannot be passed once the defect is fixed is not a
hard stop, it is a dead end. The checks are now recomputed from the artefact as it is
(`current_gate_checks`), which is the rule `approve_specification` and
`approve_decomposition` already state one level down.

*The driver named a verb that could only refuse.* A gate whose machine half failed is not
passed with `gate --approve`, and that verb correctly refuses it. Reporting the stop without
saying so sent the operator to a command that could not help. `DriverRun.gate_failures` now
carries the failed check names and `next_human_verb` names the phase's producer verb
(`PHASE_PRODUCER_VERB`) instead — and reads the same recomputation, so a repaired gate is
reported as passing rather than sending the operator to re-produce an artefact `gate --approve`
would have accepted.

*The build was re-dispatched until the iteration bound.* The guard read
`state.sealed_dispatches`, which filters on `checkout.sealed_commit is not None` — `None` for
a producer that commits its own work. That filter is about *reviewability*, an accepted limit
of the coverage denominator, and the wrong fact here: the set stayed empty, `build` was
selected on every iteration, and a run that had completed every step re-dispatched the whole
plan 64 times and reported `exhausted`. Idempotency is about the work, not about whether a
diff was reviewable; the guard now reads the plan's dispatch rows.

The common lesson is the one this tree keeps relearning: a predicate that is *nearly* the
right question fails silently, and it fails toward a plausible answer — a refusal that looks
like a rule, a verb that looks like an instruction, an `exhausted` that looks like a slow
build. Each of the three passed every test in the suite before it was found, because no test
had driven the pipeline end to end.

**A fourth defect, in the gate itself.** `GOVERNANCE_ABSENT_REASON` — FR-055's finding, whose
docstring calls it "a checkable statement about this tree" — transcribed the ledger's
vocabulary by hand and had drifted to naming twenty-eight acts against an enum of
thirty-three, having lost `diff`, `oracle`, `adversarial` and `authorship` without a single
test failing. A sentence whose whole claim is that it is checkable cannot be the one thing
nothing checks, so the list is now read off `LedgerKind` and a test pins it in both
directions.
