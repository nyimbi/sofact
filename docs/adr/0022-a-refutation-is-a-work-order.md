# 0022. A refutation is a work order, and the loop it starts is bounded

## Status

Accepted.

## Context

SoFact was verification-first to the point of being unable to finish. `dispatch_plan` ran
the plan wave by wave and **halted at the first refuted wave** — correct, because a
dependent must not build on an unverified dependency (FR-142) — and then did nothing with
the refutation. The operator read the verdict and dispatched again by hand. The factory
could refuse; it could not complete.

The rule behind that halt was never written down, but it had a shape, and the shape was a
misreading of FR-101. FR-101 says:

> Failed builds must **escalate with diagnosis**, not retry indefinitely. An unbounded
> retry loop is the most expensive failure mode available to an unattended factory,
> because it consumes wall clock — the binding resource.

Read as "do not retry", that forbids the only mechanism by which an unattended factory
converges on a system that works. Read as written — *not retry **indefinitely*** — it
forbids a loop with no bound, and says nothing against a loop with one. The constant that
carried the misreading was `DEFAULT_STEP_ATTEMPTS = 1`, whose own docstring justified
itself by FR-101 and concluded "retrying is therefore an operator decision". One attempt
is not a bound; it is the absence of a loop wearing a bound's clothes.

The cost was structural, not cosmetic. Verification-first is compatible with
spec-in/system-out: an oracle that decides whether a clause holds is exactly what a repair
session needs to aim at. What the halt destroyed was the *feedback edge*, and without it
"provide a specification and get a built system" reduces to "provide a specification and
get a verdict". The verdict was always honest. It was just terminal.

## Decision

**A refuted verdict is turned into another session, and the loop that produces it is
bounded twice over, with the verifier's own words as the goal.**

1. **The diagnosis comes from the verifier, never from the producer.** `refutation_diagnosis`
   renders the verdicts as `'<clause statement>' — <reason>`, where the reason is the
   oracle's observation (its exit code, its missing stdout). A goal authored from the
   producer's account of its own failure aims at the failure the producer can *describe*,
   which is the one it already failed to notice.
2. **The repair goal forbids editing the oracle and is pinned by hash.** The rendered goal
   carries "Do not weaken, skip, delete or rewrite" and names the oracle as pinned by
   hash; FR-139's integrity check is what enforces it. Without this a repair loop is a
   producer editing its own completion criteria — R22, and the actual reason
   `DEFAULT_STEP_ATTEMPTS` was 1. The constraint is the *reason* the bound can be relaxed.
3. **Each round authors a new plan revision, never an edit.** `revised_plan` keeps every
   prior step's id, ordinal and goal hash and chains the new repair step onto all of them.
   The plan is what FR-139 pins hashes against; an edited plan would make the integrity
   check compare the plan with itself.
4. **The bound is per clause, and running out is recorded.** `DEFAULT_REPAIR_ATTEMPTS = 2`.
   An attempt that spends its budget is written as `EXHAUSTED`, not omitted, because
   "ran out of attempts" and "nothing to repair" must not look alike in the log — the
   second is a clean contract and the first is a producer that cannot do the work.
   The clause set being finite bounds the whole run.
5. **The loop re-reads the verdict; it never infers success from an exit code.** An attempt
   whose session completed is `REPAIRED` *as a session*; `_settle_repairs` re-labels it
   `STILL_REFUTED` when the check that session triggered still refutes a clause it covered.
   A completed session is not a repaired clause, which is FR-138 applied to the loop itself.
6. **Every attempt is a ledger row.** `RepairAttempt` carries the plan id, the revision id,
   the step, the covered clauses, the attempt ordinal, the diagnosis, the goal hash, the
   outcome and the dispatch. FR-102's attempt telemetry is satisfied by the row plus the
   dispatch it names, not by a counter that outlives its evidence.

## Alternatives refused

* **Retry the step in place, without a new plan revision.** Refused: FR-139 pins the plan
  by hash, so the "before" and "after" would be the same object and the integrity check
  would compare the plan with itself. It would also destroy the record of what the plan
  originally asked for.
* **Let the producer author its own repair goal from its own failure.** Refused: the
  producer's account of its failure is the account that missed the clause. The verifier is
  independent by construction (ADR-0006) and its observation is the one thing the producer
  does not have.
* **Unbounded repair until clean.** Refused on FR-101's own terms: wall clock is the
  binding resource, and a loop with no bound is the failure mode the requirement names.
* **No repair at all, keeping the halt as the whole design.** Refused: it makes the factory
  a referee rather than a factory. A refutation that cannot be acted on is a stop sign, and
  a stop sign is not a system that builds systems.
* **Silently ending the loop when attempts run out.** Refused: it makes the exhausted case
  byte-identical to the converged case in the log. `EXHAUSTED` exists so the difference is
  a row rather than an inference.
* **A single global attempt counter instead of per-clause.** Refused: a plan with one
  stubborn clause would consume the budget for every other clause, so the second failure
  would be reported as the first one's cost. Attempts are counted at the clause because
  that is the unit the verdict is phrased in.
* **Raising `DEFAULT_STEP_ATTEMPTS` instead of adding a loop.** Refused: the step budget
  caps a *scheduler's* retries inside one wave, which cannot see a verdict — the check runs
  after the wave. Repair is authored against a refutation, and a refutation does not exist
  until a wave has ended.

## Consequences

* The factory can now converge: `dispatch` stalls, `repair` hands the refutation back, the
  oracles re-run, and the contract comes back clean with every step recorded. Measured
  end to end through the CLI against a real child process.
* `DEFAULT_STEP_ATTEMPTS` stays 1, and now for a reason that is stated rather than
  inherited: the scheduler does not retry a step, because retrying a step that failed for a
  reason nobody has read is the unbounded loop in miniature. Retrying happens against a
  diagnosis.
* The loop is safe against R22 by construction, not by policy: the oracle text is pinned
  by hash and the goal forbids touching it, so a producer that "repairs" by weakening the
  check is caught by FR-139 as an integrity failure rather than reported as a pass.
* A repair costs a session per refuted clause per round. That is real wall clock and it is
  the intended trade: the alternative is an operator doing the same thing by hand, with
  less information in the log.
* The loop does not decide *whether* a refutation is repairable. A clause refuted because
  the oracle is wrong will spend its attempts and be recorded `EXHAUSTED`; distinguishing
  a bad oracle from a bad artefact is the adversarial oracle audit's job (FR-107), not the
  loop's.

## Evidence

* `src/sofact/views.py` — `RepairAttempt`, `RepairOutcome`, `LedgerKind.REPAIR_ATTEMPTED`;
  `ProjectState.repairs_for_plan` / `attempts_at_clause`.
* `src/sofact/state.py` — the `REPAIR_ATTEMPTED` arm, keyed by id with last-write-wins
  because an attempt is settled after it is written (the ADR-0007 idiom).
* `src/sofact/planner.py` — `DEFAULT_REPAIR_ATTEMPTS`, `refutation_diagnosis`,
  `repair_goal`, `revised_plan`.
* `src/sofact/service.py` — `repair_plan`, `_group_refutations`, `_record_repair`,
  `_settle_repairs`.
* `src/sofact/cli.py` — `sofact repair`, which re-applies the probe and model gates
  `dispatch` applies, so the repair path is not a way around FR-148.
* `tests/ci/test_service.py::TestTheRepairLoop` — 10 tests: convergence, the diagnosis
  reaching the goal, the oracle-edit prohibition, `STILL_REFUTED`, `EXHAUSTED`, the clean
  no-op, nothing-verified, every attempt in the log, the revision keeping the original
  steps, and the repair step covering only refuted clauses.
* `tests/ci/test_cli.py::TestTheRepairVerb` — 5 tests, including a refuted pipeline whose
  exit code is asserted to be *that* refutation rather than an unprobed harness.

## References

* FR-098 — diagnostic repair as one of the adapter's three modes; the requirement this
  record implements.
* FR-101 — escalate with diagnosis, not retry indefinitely; the bound, read as written.
* FR-102 — attempt telemetry.
* FR-107 — the adversarial audit that tells a bad oracle from a bad artefact.
* FR-138, FR-139, FR-142, FR-163.
* R22 — goal-hacking; the risk the hash pin and the oracle prohibition hold off.
* ADR-0006 — the verifier cannot reach the executor, which is why the diagnosis is
  trustworthy.
* ADR-0015, ADR-0017 — what triggers a check and what a verdict describes, which the loop
  consumes rather than changes.
