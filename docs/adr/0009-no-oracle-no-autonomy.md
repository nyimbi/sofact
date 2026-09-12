# 0009 — No oracle, no autonomy; termination is not verification

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

Two failures define everything SoFact does, and they are both about a boundary being
crossed by omission rather than by intent:

1. **A clause that cannot be checked gets treated as a clause.** It flows through the
   pipeline, appears in a contract, and the contract is called verified — when the
   clause was never anything but a sentence. This is how "verified" becomes
   decorative: not through a lie, but through a missing check that nobody noticed.
2. **A producer's assertion of completion is treated as completion.** A harness
   finishes, reports success, and the pipeline advances. The report is a fact about
   the producer's state, not about the artefact.

The second has direct evidence. `dsh`'s `ralph` tool documents that "completion and
blockers are worker reports, not independent evaluation" [S21], and a decompressed
session log contained **zero goal-typed events** across 63 records [S21]. The report
arrives; the evidence does not.

These two are the same failure at different points: something that is *not* a check
is accepted in the position where a check belongs.

## Decision

Both rules are enforced **by type and by signature**, so that violating them is a
type error rather than a judgement call.

**FR-001 — no oracle, no autonomy.**

- `Clause.oracle` is a required, non-nullable `OracleDeclaration`.
- `Contract.from_draft` refuses a draft with any stem lacking an oracle, and the error
  **names the missing stems** — "unverifiable" is only actionable when it is specific.
- `OracleRunner.run` raises `OracleNotExecutableError` when asked to run an oracle
  with no `command_hint`. An intention is not an observation.
- An oracle with no command is not a weaker oracle. It is reported as
  `INSUFFICIENT`, and its share of the contract is reported as **ground-truth debt** —
  0.0 is the only good value.

**FR-138 — termination is not verification.**

- `CompletionClaim` is a **distinct type**. It is recorded, and it is inert.
- `verify(contract, evidence)` has **no parameter for a claim**. The signature has
  nowhere to put one.
- `VerdictOutcome.INSUFFICIENT` is a first-class outcome, not an error condition. A
  clause whose oracle could not be run is not satisfied, and collapsing it into either
  "satisfied" or "violated" would be the most expensive mistake the system could make.
- Aggregation is **worst-case dominant**: `VIOLATED > INSUFFICIENT > SATISFIED`. One
  counterexample outweighs any amount of corroboration.
- `VerificationReport.is_clean` is true only when *every* clause is satisfied. Partial
  verification is not verification, and this is the single predicate any gate consults.

## Evidence

`tests/ci/test_pipeline.py::test_a_success_claim_does_not_survive_a_failing_oracle` is
the centrepiece and runs end to end through the real service and a real log:

1. a goal is taken through the full interrogation to a contract;
2. a producer declares completion — `declare_completion(by="probe-harness", note="all green")`;
3. the oracle runs and exits **1**;
4. the verdict is **`VIOLATED`**, for every clause.

Supporting assertions, all passing:

- `test_declaring_completion_changes_no_verdict` — the verdict before and after a claim
  is identical, clause by clause.
- `test_a_claim_without_evidence_leaves_the_clause_insufficient` — claiming success
  with nothing run yields `INSUFFICIENT`, not a pass.
- `test_a_contract_with_no_commands_is_total_ground_truth_debt` — debt is 1.0 and the
  verdict is `INSUFFICIENT`.
- `test_zero_tests_collected_is_insufficient` — a green suite that ran nothing is the
  classic false oracle, and is not a pass.
- `test_timeout_is_insufficient_not_violated` — a hung instrument falsifies nothing.
- `test_malformed_payload_is_never_coerced` — `{"exit_code": "0"}` and
  `{"exit_code": True}` are not exit codes.
- `inspect.signature(verify).parameters == ["contract", "evidence"]`.

## Consequences

- A contract's autonomy ceiling is set by its **weakest** clause
  (`ceiling_for_rank`, L5 never granted), because a contract is only as verifiable as
  its least verifiable part.
- Ground-truth debt becomes the honest headline number: it says how much of a
  "verified" contract was actually verified. Under D17 — no market as an oracle —
  this number is one of the few external-facing claims SoFact can make.
- Producers get no partial credit for announcing success early, and no advantage from
  hanging: `INSUFFICIENT` grants no autonomy either.
- The system can refuse to proceed and still be correct. That is the intended failure
  mode, and it is why refusing a bad oracle is treated as a feature throughout — the
  development of SoFact itself included.
