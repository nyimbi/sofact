# 15. A verdict describes one run, and a declaration triggers the check

* Status: Accepted; **in part superseded by [ADR-0017](0017-a-completed-session-is-checked.md)**
  — the trigger is now the session's outcome rather than a declaration. Everything here
  about run scoping still stands.
* Date: 2026-09-12
* Deciders: operator
* Supersedes: none (it supersedes a rule that lived only in code and never had a record)
* Related: [ADR-0003](0003-the-ledger-is-append-only-and-hash-chained.md),
  [ADR-0006](0006-the-verifier-cannot-reach-the-executor.md),
  [ADR-0009](0009-no-oracle-no-autonomy.md)

## Context

FR-138 states that termination is not verification: a harness completion declaration
"must trigger P6 and must never satisfy it", and both signals must be recorded separately
so that disagreement is reported. The **first half was never implemented**. A real run
(`/tmp/sf-e2e`, 41 ledger rows) recorded nine `claim.declared` rows and **zero**
`evidence.recorded` and **zero** `verdict.rendered` rows. `dispatch_step` wrote the claim
down and returned; nothing ever ran the contract's oracles afterwards. The verifier was
correct and unreachable, which is indistinguishable from absent.

Two consequences were measured, not assumed.

**1. The verdict was monotone in the log, so nothing could ever be repaired.** `_decide`
(`verification.py:169`) makes the worst observation dominate a clause, and `verify` was
fed `state.evidence` — *all* history. A clause observed failing once therefore stayed
`VIOLATED` forever. Probe `/tmp/repair_probe.py`, on a contract whose oracle is
`test -f marker.txt`:

```text
attempt 1 (no marker):   ['violated']
attempt 2 (marker made): ['violated']
is_clean after the repair: False
```

The plan's `repair` tier exists precisely to take a clause from refuted to satisfied
(FR-103's oracle ladder). Under this rule its success is unobservable, and the log
answers *"has this clause ever failed?"* while wearing the name of a status question.

This also inverted a measurement into a slander. `declaration_precision` needs
`state.latest_report(contract_id)`; with no trigger that is always `None`, so
`corroborated` was always 0 and the live run printed **`0/9 = 0%`**. FR-147's remedy for
a lying harness is replacement. The number that would justify replacing a harness was
being produced by a missing function call.

**And the all-history rule contradicted a retained requirement.** FR-006
(`docs/spec/product-spec-old.md:190`) reads: *"Oracle results older than the change under
test are invalid. Caching must be keyed by content hash of both the change and the oracle
definition."* §9.1 carries FR-001–FR-006 forward unchanged. Worst-case dominance over the
whole history lets an **older** result decide a **newer** artefact. The words
"worst-case dominance" appear nowhere in the spec — the rule existed only in code, which
is why nothing caught the contradiction.

**2. A claim could stand in for a verdict one more time, at the write.** `service.contract`
built each oracle with `model_copy(update={"command_hint": commands})`.
`model_copy` **does not validate** in Pydantic v2. Given a list instead of the declared
`str | None`, it wrote a ledger row that could not be read back — probe
`/tmp/poison_probe.py`:

```text
PydanticSerializationUnexpectedValue(Expected 'str' - serialized value may not be as
expected [field_name='command_hint', input_value=['test -f marker.txt'], input_type=list])
fold FAILED: ValidationError 5 validation errors for Contract
clauses.0.oracle.command_hint
```

The factory's only artifact is its log. An unfoldable log is an unrecoverable project
state, and it was reachable by an untyped caller.

## Decision

**One defect family — a claim standing in for a verdict — closed in four places, plus the
write that made it permanent.**

1. **A verdict describes one run.** `Evidence` carries `run_id: UUID7 | None`
   (`views.py:470`, set through `Evidence.record`), and `verify` takes
   `run_id: str | None` (`verification.py:200`), filtering observations before bucketing
   by clause. Worst-case dominance survives **within** a run: a single counterexample
   still cannot be outvoted inside the attempt it belongs to. `run_id=None` means
   "undifferentiated" — the degenerate case of the same rule, and the answer to the
   provenance question.
2. **A declaration triggers P6.** `check_declaration(plan_id, dispatch_id)`
   (`service.py:437`) runs the contract's oracles **in the dispatch's workspace**, with a
   fresh `run_id`, commits `EVIDENCE_RECORDED` per observation, then renders and commits
   `VERDICT_RENDERED`. `dispatch_step` calls it immediately after committing
   `CLAIM_DECLARED` (`service.py:698`), so the claim row precedes the verdict row as a
   separate fact.
3. **The wave gate uses the verdict, not the declaration** (FR-142). `refuted_steps`
   (`service.py:111`) yields the steps whose covered clauses are `VIOLATED` in the latest
   report, and `dispatch_plan` breaks on them (`service.py:757`). `INSUFFICIENT` is
   deliberately *not* a refutation: FR-109 grants it no autonomy, but halting on a gap
   would make Mode G — which legitimately runs ahead of its oracles — unbuildable. A step
   covering no clause is never refuted, or a bootstrap step would block the build forever.
4. **The trigger runs the whole contract, not the step's clauses.** Under latest-run
   semantics a partial report would mark every unrun clause `INSUFFICIENT` and so destroy
   the corroboration of steps verified a moment earlier. `run_all` is clause-complete, and
   it *skips* non-executable clauses rather than raising — which is what makes this safe
   to call from the dispatch path at all, since `cli.py` catches only `ValueError`,
   `KeyError` and `HarnessBinaryMissing`.
5. **No claim can be an input.** `verify`'s signature has nowhere to put one (FR-138 as a
   type), and `test_verify_takes_no_completion_claim` now asserts the property rather than
   a spelling: nothing is accepted positionally beyond the evidence, and no parameter is
   annotated with anything claim-shaped.
6. **`model_copy` is not a validated write, so it is not used for one.** `service.py:353`
   constructs through
   `OracleDeclaration.model_validate({**suggested.model_dump(mode="python"), "command_hint": commands})`
   and asserts the parameter matches its declared type, so the refusal names the argument
   instead of surfacing at the next read of the log.
7. **A payload's truthy stand-in is not agreement.** `_as_bool`
   (`verification.py:58`) narrows `timed_out` to a real `bool`; `1`, `"true"` and `[1]`
   are `INSUFFICIENT`, never a pass. Reading them as falsy would skip the timeout branch
   and let a stale `exit_code` beside it satisfy the clause — a malformed payload turned
   into a green light, the one direction this must never fail in.

**`run_id` is an ordering token, not a content hash, and that limit is stated here rather
than implied.** It implements FR-006's *ordering* half — a result older than the change
under test must not decide it — and it does not claim the other half. Nothing hashes the
artefact, so nothing is cached; each check re-runs the oracles. FR-006's cache key (`hash
of the change **and** the oracle definition`) remains unimplemented and is recorded as
open.

## Consequences

* **A repair can now succeed.** The same contract, unchanged, yields `VIOLATED` and then
  `SATISFIED` once the artefact satisfies it — so the repair tier can observe its own
  success, and the log no longer answers a provenance question under the name of a status
  one.
* **`declaration_precision` measures.** Live, on a nine-step plan: `8/9` when the oracle
  agrees. The gap is the bootstrap step, which covers no clause — a step that no oracle
  *can* object to must not collect the best score. Before this decision the instrument
  reported `0/9`, which was a measurement of nothing.
* **The cost is redundancy.** Each declaration runs the whole contract, so a nine-step
  plan renders nine full reports — 45 clause verdicts for five clauses. Per-wave checking
  would be cheaper and would leave the remaining claims unchecked; checking every claim is
  what FR-138 asks for, so the redundancy is the price and is not optimised away.
* **`sofact dispatch` now exits non-zero when the contract is not clean, including
  `INSUFFICIENT`.** This is the same correction one layer up: `sofact verify` already
  exited 1 on `not report.is_clean`, and a build whose artefact is unverified must not
  hand a script a green light. It changes a documented exit code, and it means dispatching
  against a contract with no executable oracle now fails honestly instead of succeeding
  vacuously.
* **A failed or silent session still triggers nothing** (`check_declaration` returns
  `None`, writing no rows). A `FAILED` or `BUDGET_EXHAUSTED` dispatch asserts nothing about
  the artefact; inventing a verdict for it would manufacture a signal the producer never
  gave.

## Evidence

* **The monotone verdict, before and after.** `/tmp/repair_probe.py` printed
  `['violated']`, `['violated']`, `is_clean after the repair: False`; it now prints
  `['violated']`, `['satisfied']`, `is_clean after the repair: True`, with 21 ledger rows
  and `tampered.verify_chain().ok` still `True` — the history is appended to, never
  rewritten. Pinned by `test_a_repaired_clause_can_turn_green` (`test_pipeline.py:167`),
  which also asserts the chain still verifies.
* **Run scoping, at the unit level.** `test_a_verdict_can_be_scoped_to_one_run`
  (`test_verification.py:110`) asserts the unscoped read is `VIOLATED` while run two is
  `SATISFIED` and run one is still `VIOLATED` — the same observations, three questions.
  `test_scoping_to_a_run_that_observed_nothing_is_insufficient` pins that an unrun oracle
  inherits nothing.
* **The trigger, at the service level.** With `commands="exit 0"`: nine steps dispatched,
  `claim.declared=9`, `evidence.recorded=45`, `verdict.rendered=9`, latest report
  `satisfied`, precision `8/9`. With `commands="exit 1"`: **4 of 9 steps** dispatched, last
  step kind `operation`, `claim.declared=4`, `evidence.recorded=20`, latest report
  `violated`, precision `0/4` — the producers all completed and all declared, and the run
  stopped anyway. Pinned by `test_a_refuted_step_ends_the_run` (`test_service.py:558`),
  `test_a_lying_producer_is_measured_not_believed`, and
  `test_precision_now_measures_instead_of_reporting_zero` (`test_service.py:682`).
* **The claim is written before the verdict**, by ledger index, in
  `test_the_claim_is_written_down_before_the_verdict` (`test_service.py:633`);
  `test_a_dispatch_that_declares_nothing_triggers_nothing` asserts the silent session
  writes neither an evidence row nor a verdict row.
* **A truthy stand-in is refused**, over `1`, `"true"`, `"yes"` and `[1]`, in
  `test_a_truthy_stand_in_for_timed_out_is_not_a_pass` (`test_verification.py:252`).
* **The unfoldable log is closed at the boundary.** The `model_validate` construction
  (`service.py:353`) refuses a list where `str | None` is declared, so the row is never
  written; `grep -rn "model_copy" src/` leaves only `views.py`'s `entry_hash`, which is
  chain bookkeeping rather than a value that must satisfy an annotation.
* **Shell-level, from the real binary** (`/tmp/sf-verify`, a contract with five clauses and
  the oracle `test -f marker.txt`): `sofact dispatch --all` dispatched four steps, printed
  `declared complete` for each, then `contract violated: 0 of 5 clauses hold (FR-138: a
  declaration triggers verification, it does not replace it).` and exited **1**. After
  `touch marker.txt`, `sofact run` then `sofact verify` exited **0** with five of five
  clauses satisfied, and `sofact precision` reported `3/4 = 75%`. The ledger holds **50**
  rows: five `verdict.rendered` — four `violated` from the trigger, one `satisfied` after
  the repair — with a **single unchanged** `contract_hash` (`84f0662492b9`) across all
  five, which is the point: the artefact changed, not the contract. Chain intact, 46 tests
  over the affected modules, suite **424 passed**.
* The ADR set's own index records this as decision 15; the code sites above are the
  authoritative ones and were re-read, not recalled, before being cited.

## References

* `src/sofact/views.py` — `Evidence.run_id` (470), `Evidence.record` (480)
* `src/sofact/verification.py` — `_as_bool` (58), `_decide` (169), `verify` (200)
* `src/sofact/execution.py` — `OracleRunner.__init__(…, run_id=…)`, `run_all` skipping
  non-executable clauses
* `src/sofact/service.py` — `latest_run_id` (96), `refuted_steps` (111),
  `contract`'s validated construction (353), `run` (380), `verify_contract` (409),
  `check_declaration` (437), `dispatch_step` (649, trigger at 698), `dispatch_plan` (757)
* `src/sofact/cli.py` — the dispatch verdict line (612) and its exit code (617)
* `docs/spec/product-spec.md` — §8.3, §8.5 (FR-138, FR-139, FR-142), §9.1 (FR-001–FR-006
  carried forward)
* `docs/spec/product-spec-old.md` — FR-005 (188), FR-006 (190)
