# 0055 — Attempt telemetry is a join, and the count of what it could not measure is part of the number

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** FR-102, FR-118, FR-138, FR-140, NFR-024; FR-101, FR-143;
  [ADR-0043](0043-a-gate-cost-is-asked-for-because-nothing-observes-a-person-reading.md),
  [ADR-0053](0053-the-adversarial-audit-is-a-must-fail-canary-and-the-empty-tree-is-the-input.md),
  [ADR-0054](0054-the-escape-rate-is-the-one-number-no-producer-authored.md)

## Context

FR-102 is one sentence with three nouns: "Build must report **attempt telemetry**
(attempts, tokens, wall clock)." The roadmap recorded it **Partly**, and the note on the
verdict is the whole problem: "per-dispatch telemetry exists; the requirement is about
attempts, which are not aggregated anywhere."

Both halves were already in the log, in two places nothing joined.
`RepairAttempt` carries the clause, the ordinal, the diagnosis and the outcome — the
attempt. `DispatchRecord` carries `wall_clock_seconds`, `tokens_observed` and
`continuations_observed` — the session. The attempt row holds the `dispatch_id` that
names the session, and no reader had ever followed it. So the factory could say what one
*step* cost and could say what one *clause's repair history* was, and could not answer the
question FR-101's bound exists to make askable: what did this plan's repair loop cost, in
attempts and in tokens and in wall clock?

The joining field is also the one that makes the answer honest or dishonest.
`DispatchRecord.tokens_observed` is `int | None`, and `None` means the harness reported
no usage — `parse_usage` states the rule at the source and NFR-024 states it as policy:
an unmeasured quantity is not a zero. A total that added `None` as `0` would report a
cheap build where the truth is a build whose cost nobody observed. That is FR-118's
missing qualification in arithmetic form: a number that has lost the fact that it is
incomplete.

## Decision

**1. Attempt telemetry is a pure fold, in its own module.** `measure_attempts`
(`telemetry.py`) takes the repair rows, the dispatch records and a plan id, and returns an
`AttemptTelemetryReport`. It opens no file, runs no session and consults no clock — the
same contract `escape.py` and `audit.py` keep, and for the same reason: a number
reproducible from the log is evidence, a number computed from live state is a summary.
`FactoryService.attempt_telemetry` is the thin reader that supplies the records.

**2. The filter is the plan, and it is applied inside the fold.** A run-wide total would
let one plan's spend hide inside another's, so the caller names the plan it is asking
about. The filter lives in `measure_attempts` rather than in its caller so that passing
the whole ledger cannot accidentally report a peer's spend. `RepairAttempt.plan_id` is the
**origin** — the plan `repair_plan` was entered with — and `revision_id` exists for looking
the step up, not for deciding whether the attempt belongs.

**3. The unmeasured count is part of the number, not a footnote to it.**
`AttemptTelemetryReport` sums what reported and carries `unmeasured_tokens` beside the
total, with `tokens_complete` saying whether the sum is exact. A report whose tokens are a
floor says so in the type, so no caller can print the total and drop the qualification by
forgetting a line.

**4. Three absence cases, three different rows — none of them zero.**
An attempt with no `dispatch_id` never ran: it contributes one attempt, no wall clock and
no tokens, and it is *not* unmeasured, because there is nothing hidden. An attempt whose
`dispatch_id` resolves to no record is a **torn read** on an append-only log — the row is
written when the session ends — so it is unmeasured, the same treatment a silent harness
gets. A harness that reported no usage is unmeasured with the session's wall clock intact.
Collapsing these into "zero" would make the producer never starting, a partial read, and a
silent harness all look like a free build.

**5. `AttemptTelemetry` refuses spend with no session.** A row with `dispatch_id=None` and
a non-zero wall clock or token count raises: a cost with no session attached is a
measurement of nothing. The type also refuses a zero attempt ordinal, because the ordinal
is 1-based (FR-101 counts attempts, and an attempt numbered from zero is off by one
against the bound it is checked against).

**6. A run that made no attempt claims nothing.** `discharged` returns `()` when
`attempts` is empty — `EscapeReport`'s and `OracleAuditReport`'s rule, applied here: the
absence of a measurement is not a measurement, and three zeros over an empty run are the
shape a clean result takes when there was no run at all. `sofact attempts` exits non-zero
on that state and says why in words.

**7. The CLI asks for the origin plan, and this is not a detail.** The verb's first
implementation called `latest_plan(contract_id)`. A repair authors a **new plan revision**
per attempt, so the latest plan is the tail of the revision chain, and its id appears on no
repair row — the fold therefore returned an empty report and the verb printed "no repair
attempt was made against this plan". The failure is worth recording because it was
*plausible*: `latest_plan` is the right accessor for every other question about a contract's
plan, and it is the wrong one for exactly the question FR-102 asks. `ProjectState.origin_plan`
and `FactoryService.origin_plan` return the first plan compiled from a contract, and
`TestTheAttemptsAreFiledUnderTheOriginPlan` asserts the two ids **differ** rather than that
some number is non-zero — a test that only checked for a non-empty total would have passed
against a fixture that happened to make one revision.

**8. Telemetry is derived, never stored.** No new ledger kind, no new field on
`RepairAttempt` or `DispatchRecord`. Every input was already written down; the requirement
was a reader, and adding rows for a computation the log already determines would be a
second source of truth for the same number.

## Consequences

The repair loop's cost is now answerable from the log alone, per plan and per clause
(`by_clause`), which is what FR-101's bound needs to be legible rather than merely
enforced. `sofact attempts` reports it and refuses to report a run that measured nothing.

The cost is that the report is only as complete as the harness's reporting. A harness that
never emits usage yields a floor for every attempt in the run, and the report will say so
on every line. That is the honest reading and not a defect to fix in this module: the
alternative — inferring tokens from wall clock or from argv — would be inventing a
measurement, which is precisely what NFR-024 forbids.

One limit is stated rather than papered over: `continuations_observed` is on the dispatch
record but not in the attempt report. FR-102 names three quantities and continuations are
not among them; adding a fourth would be scope the requirement does not ask for, and the
field is one join away when a requirement does.

This closes the aggregation half of FR-102. It does not build FR-091 (minimise interface
surface — the count is reported, nothing minimises it) or FR-155 (a third-party plugin
deletion test), which remain the roadmap's open unblocked rows.
