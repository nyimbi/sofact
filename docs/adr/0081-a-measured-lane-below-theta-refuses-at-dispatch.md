# 0081 — A measured lane below θ_lo refuses at dispatch, and an unmeasured one does not

- **Status:** Accepted
- **Date:** 2026-10-19
- **Related:** FR-105, FR-009, FR-010, NFR-024, ADR-0061, ADR-0076, ADR-0079

## Context

FR-105 reads:

> Oracle manufacturing must produce a **measured** strength for every module before P5
> begins. A module whose manufactured oracle is below θ_lo must be reported as
> unbuildable-at-autonomy and escalated, not built anyway.

ADR-0061 built the measurement — `measure_strength` over a named, closed operator set,
with `StrengthRefusal` naming the five ways the number is withheld. ADR-0076 built the
comparison inside `routing.py`, where `oracle_strength_ceiling` turns a strength into a
lane's *ceiling* and `THETA_GATE_BUILT` moved to `True`.

Neither put the number where an act reads it. The routing report is a reading of the log;
`dispatch_step` never consulted it. So a lane whose oracle kills one mutant in ten was
measured, capped in a report, and then **built anyway** — which is the sentence FR-105
forbids. The defect is the one ADR-0074 recorded one layer down and ADR-0076 recorded in
`THETA_GATE_BUILT`: a fact computed and never consulted by the path that acts.

Two further facts shaped the fix, and both were found by reading rather than assumed:

1. **The instrument scores clauses; the requirement refuses modules.** `_measured_strengths`
   returns `dict[clause_id, float]`. FR-105 says "a module whose … oracle is below θ_lo".
   Something has to join them, and the join is a decision rather than a formatting step.
2. **`_measured_strengths` derives module ownership from `state.dispatches_for(plan.id)`**
   — sealed dispatches, which exist only after a dispatch. FR-105's literal "before P5
   begins" is therefore unreachable for a first build: there is nothing to mutate until a
   session has written files. This is a structural limit of the instrument, not of the
   interlock, and the record states it rather than pretending the requirement's literal
   reading is met.

## Decision

**The number becomes a ledger row, and the one path every dispatch goes through reads it.**

`OracleStrengthMeasured` carries the contract, the contract hash, the measurement time, the
per-lane strengths, and **the thresholds in force at the measurement**. `measure_oracle_strength`
commits it as `oracle.strength_measured`, reachable as `sofact audit --strength`. The row is
appended, never re-keyed, for `OracleAuditReport`'s reason: a measurement is about the exact
tree and oracle set it ran against.

`dispatch_step` calls `_require_lane_above_theta` immediately after resolving the step's
module and before the adapter, the branch, or the worktree exists. It refuses with
`RoutingRefusal` naming the module, the measured strength, the θ_lo it fell below, and the
remedy.

The seam is `dispatch_step` rather than `dispatch_plan` because `dispatch_step` is the one
path all three dispatch surfaces pass through — the driver's `build`, a scheduled wave, and
a direct caller. A check in `dispatch_plan` would be a check on one of the three, and the
driver is what an operator actually runs.

### The join takes the minimum

A lane's strength is its **weakest** measured clause, not the mean. A module is only as
verifiable as its least-verifiable promise: a mean lets one well-tested clause carry a lane
whose other clause nothing checks, which is exactly the composition FR-105 exists to refuse.
ADR-0076 made the same choice inside `routing.py` (`RouteDecision`'s strength is its weakest
clause's), and two different folds for one word would be the drift this record is about.

### Three absences dispatch unchanged

- **No recorded measurement.** The project has not run the instrument. NFR-024 read one
  level up: a lane nobody scored is not a lane that scored zero.
- **No module.** A bootstrap step or one spanning two modules belongs to no lane. FR-105
  refuses *a module*, and such a step has none to refuse.
- **The lane is absent from the mapping.** The instrument declined it — too few mutants, an
  oracle naming no command, ownership that is not exactly one module. That is a refusal to
  score, not a low score.

Refusing any of these would make FR-105's escalation fire on the absence of evidence, which
is the failure mode NFR-024 exists to name.

### Strictly below

The comparison is `strength < θ_lo`. The spec's own word is "below", and θ_lo is the
threshold that *admits* L3 — counting the tie as a violation would refuse the boundary case
FR-009's table admits, and ties are the common case for a small suite.

### The thresholds travel with the number

`OracleStrengthMeasured.thresholds` is the pair in force when the measurement ran, and the
interlock compares against it rather than against `DEFAULT_THETA`. A number measured under
assumed thresholds and judged under calibrated ones would be a verdict by a rule it never
met — the shape ADR-0075 records for a refusal that names the wrong cause.

## Consequences

- **The limit is named, not papered over.** Because ownership comes from sealed dispatches,
  the row is producible only after a prior dispatch. The interlock's honest reach is
  re-dispatch, repair and evolve. A first build of a fresh project cannot be refused by
  this mechanism, and the roadmap row says so in those words.
- **`sofact audit --strength` exits non-zero when it finds a refused lane.** A measurement
  that did its job is not a failed run, but a green line over a lane that will refuse at P5
  is worse than a red one; the output prints the refused lanes, the threshold, and the lanes
  that were *not* scored, because the difference between "scored zero" and "not scored" is
  invisible in a table of the ones that were.
- **A refused dispatch leaves no row.** The check sits before the adapter and the branch, so
  there is nothing to clean up and no half-created session. A refusal after the session
  started would be a failed step wearing a refusal's clothes, and
  `test_the_refused_lane_leaves_no_dispatch_row` asserts the difference.
- **`ProjectState` gained a field and the census gate caught the omission.** `test_state.py`
  transcribes every `LedgerKind` into the field its fold arm fills, and adding
  `oracle.strength_measured` without its `oracle_strengths` row failed both that gate and
  the field-count assertion. The gate worked as designed; this is the note that it fired.
- **`RoutingRefusal` is reused rather than a new exception class.** It already means "a
  calibration or a floor that cannot be read, or that would raise a level", which is this
  refusal's family. A `StrengthRefusal`-named exception would have collided with the
  `StrEnum` of that name in `mutation.py`.

## Evidence

**Ten tests in `test_strength.py`, and five canaries, all caught.**

The canaries, each reverted from a `cp` backup verified to hold this version, with
`__pycache__` cleared:

1. The `_require_lane_above_theta` call removed from `dispatch_step` — 1 failed,
   `test_a_measured_lane_below_theta_is_not_dispatched`.
2. `strength < θ_lo` changed to `<=` — 1 failed,
   `test_a_lane_exactly_at_theta_lo_dispatches`. This is the "below" canary.
3. An absent lane treated as `0.0` — 1 failed,
   `test_a_row_that_does_not_name_the_lane_does_not_refuse_it`. This is the NFR-024 canary,
   and it failed with a `KeyError` rather than a wrong assertion, which is the tell that the
   mutation changed the control flow rather than the arithmetic.
4. The fold changed from `min` to `max` — 1 failed, `test_a_lane_takes_its_weakest_clause`.
5. `latest_strength` no longer keyed by contract — 1 failed,
   `test_a_measurement_of_another_contract_does_not_refuse_this_one`.

**One real defect was found by the existing suite, not by a canary.** `test_state.py`'s
census asserts `set(KIND_TO_FIELD) == set(LedgerKind)`, and the new kind was not in the
transcription. That is the gate doing its job on a field added without its fold arm being
registered — the same class of omission the test was written to catch.
