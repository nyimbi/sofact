# 0043 — A gate cost is asked for, because nothing observes a person reading

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-160, FR-157, FR-061, FR-118, FR-119, NFR-025, §1.3, §20.2;
  [ADR-0039](0039-the-envelope-refuses-a-ceiling-and-reports-a-floor.md),
  [ADR-0040](0040-a-delivery-report-states-five-things-and-its-gate-is-human.md)

## Context

**FR-160** is the last requirement in §20 with nothing behind it:

> §1.3's 180-600 human-minute envelope is a **budget**; every human gate must record its
> actual **human-minutes** and its **rework fraction** (the share of the slice returned
> to the producer), and both must appear in the delivery report (§20.2). If review is
> the binding constraint once implementation is agent-driven [S24], then a factory that
> measures the producer's budget but not the reviewer's is optimising its cheapest step.
> Same discipline as FR-157: if it decides the ceiling, it is measured.

§20.2 states the claim the measurement exists to test: human attention per delivered
platform is *sub-linear in module count*, because gates are per-platform while work is
per-module. That is a claim about the reviewer's cost, and the factory held no reviewer
cost at all. `EnvelopeDimension.HUMAN_MINUTES` was one of ADR-0039's unmeasured
dimensions, with a reason that named what would have to exist — and nothing existed.

## Decisions

### 1. The number is *declared*, and that is the whole argument

Every other derivation in the envelope is a count of declarations the log already holds.
This one cannot be: nothing in SoFact observes a person reading a specification. A
derived human-minute figure would be an invention wearing a measurement's clothes — the
failure ADR-0039 named when it refused to report an unmeasured dimension as within
bounds.

So the operator supplies it, and `GateCost.recorded_by` records who did. The declared
number is admissible precisely because it is *not* a restatement: a value the log could
have computed would be a second source of truth, and the two would drift.

### 2. A cost attaches to a gate that was passed

`record_gate_cost` refuses a cost for a gate whose phase is not `COMPLETE`. A cost for a
gate nobody sat at is a measurement of nothing — and it would let §1.3's actual be
assembled from gates that never happened, which is the failure mode of every
self-reported metric. The gate's own approval is the evidence that a human was there, so
the approval must come first. The refusal names that ordering rather than merely
rejecting the input.

### 3. `rework_fraction` is a share of the slice, and is averaged rather than summed

Human-minutes are a quantity and add up. Rework is a *fraction of each gated slice*, so
two gates at a quarter each are a quarter on average, not a half. `DeliveryReport`
therefore carries `gate_costs` and derives `rework_fraction` as a mean. Summing shares
would report more rework the more gates a project has — an arithmetic that fails in the
flattering direction on a one-gate project and in the alarming direction on a
four-gate one.

The two numbers travel together in one type rather than as two parallel fields, because
they are two readings of one act and a report carrying one without the other would be
unable to say what the gate cost in total.

### 4. Empty means unmeasured, and the sum is per gate rather than per row

`GateCost` rows are appended and never keyed, for the reason deploys are: two
recordings of one gate are two measurements rather than an edit, and a re-measure after
a second sitting is a new fact. `ProjectState.gate_cost(gate)` reads the latest per
gate, so `total_human_minutes` cannot double-count a gate measured twice, while the log
keeps both.

`total_human_minutes` returns `None` when no gate has recorded anything. The three-state
shape is ADR-0039's, applied to a new dimension: `None` means the caller did not ask, or
nothing was measured, and the report says so rather than printing a zero. A factory that
reported `0` here would be reporting that its gates were free.

### 5. The check reports and does not gate

`gate_cost_reported` is `passed=True` always, and its detail carries the per-gate pair,
the total and the mean. A check that *failed* on an unmeasured project would block a
deploy for a measurement the operator has not been asked for yet — FR-160 asks for the
number to appear, not for the deploy to depend on it. This is FR-057's distinction
applied one requirement along: the envelope's ceiling is a refusal and its floor is a
reading, and here the whole dimension is a reading.

### 6. The delivery report carries the rows

FR-160 says both numbers "must appear in the delivery report", and the report is the last
artefact a human reads before the deploy gate — a cost recorded but not carried there is
a measurement nobody acts on. `DeliveryReport.gate_costs` is that field, printed under
its own heading at `sofact deliver`, and it reaches §1.3's actual through
`envelope.measure(human_minutes=...)`.

## Alternatives refused

- **Derive human-minutes from dispatch wall-clock.** Refused: wall clock measures a
  machine waiting on a child process, and a human reading a specification is not that.
  The two are not the same quantity and no conversion exists. FR-140 records per-step
  wall clock for its own purpose; conflating them would make the reviewer's cost look
  free on every gate an agent did not block.
- **Make `rework_fraction` a share of the *time* rather than of the slice.** Refused:
  "a quarter of the ninety minutes was rework" is not a measurement anyone can make
  without stopwatch discipline per artefact, and it is not what §20.2's claim is about.
  The share of the slice is observable from the artefact — how much of it came back.
- **Record the cost when the gate is presented rather than approved.** Refused: the
  presentation is the machine's act. A cost recorded there would be recorded against a
  gate that may still fail, and §1.3's actual would then include sittings that ended in
  a refusal to approve — which are real cost, but not cost *of a passed gate*, and
  FR-160 attaches the number to a gate.
- **A per-phase half as well as a per-gate one.** Deferred rather than refused: FR-122's
  per-phase autonomy half is likewise unbuilt, and a per-phase cost would want the same
  treatment. Neither is required to close FR-160, which names gates.
- **Enforce the 180-600 envelope on the measured actual.** Refused: §1.3 calls its
  numbers "targets, not measurements" and "a hypothesis under test". A gate that failed
  because the humans took longer than the hypothesis would be measuring the hypothesis
  against itself, and the first over-run would teach an operator to stop recording.
  ADR-0039 already made this argument for the floor; the budget is reported, not
  enforced.

## Consequences

- §1.3's `HUMAN_MINUTES` is no longer one of ADR-0039's three unmeasured dimensions. It
  is measured when a gate recorded a cost and unmeasured otherwise, and the unmeasured
  reason names `sofact gate --cost` rather than describing an absence.
- A project can now report §20.2's claim rather than assert it, once gates are recorded.
  The factory still cannot *test* sub-linearity on one project: that needs several, and
  it is an observation about a population rather than about a log.
- `LedgerKind.GATE_COST_RECORDED` joined the fold, which is exhaustive — adding the
  member produced a pyright error until `state.fold` handled it. That is the mechanism
  working: a new event kind cannot be silently dropped.
- The cost is the only envelope dimension an operator must *supply*. Every other
  unmeasured dimension names something that would have to exist; this one names a verb.

## Evidence

Three canaries, each watched failing before it was believed:

- `if gate_costs` → `if False` in `delivery.report`'s detail: 1 failed
  (`test_a_recorded_cost_reaches_the_report_the_deploy_gate_presents`).
- `gate_costs=state.gate_costs,` removed from `FactoryService.render_delivery`'s call:
  1 failed, same test — the wiring, not the check.
- `total_human_minutes`' per-gate latest lookup replaced by `list(self.gate_costs)`:
  1 failed (`test_the_total_is_the_latest_measurement_of_each_gate`) — the sum would
  double-count a re-measured gate.

`tests/ci` at 1003 passed, pyright 0 errors, ruff clean. The gate-cost tests are
`TestTheGateCostIsMeasured` (test_phase), `TestTheGateCostIsReported` (test_delivery)
and `TestTheGateCostVerb` (test_cli).

## References

- FR-160, §1.3, §20.2 in `docs/spec/product-spec.md`
- ADR-0039 — the refusal/measurement distinction this extends to a new dimension
- ADR-0040 — the delivery report and its human deploy gate
- [S24] in the specification's source list: the review-bottleneck observation FR-160
  cites for its premise
