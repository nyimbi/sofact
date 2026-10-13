# 0054 — The escape rate is the one number no producer authored, and its reduction reports rather than refuses

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-021, FR-022, FR-023, FR-031, FR-107, FR-108, FR-123, FR-157, NFR-024;
  [ADR-0053](0053-the-adversarial-audit-is-a-must-fail-canary-and-the-empty-tree-is-the-input.md),
  [ADR-0050](0050-coverage-is-a-conjunction-and-the-debt-and-the-cap-are-one-measure.md),
  [ADR-0045](0045-a-topology-is-a-type-and-a-refusal-is-not-a-downgrade.md)

## Context

§2.4 asks "Who verifies the verifier?" and answers that the regress "terminates in exactly
one place: **reality, after deployment**". Every ceiling in SoFact before this was derived
from a *declaration* — an oracle rank, a module class, a topology — and a declaration can be
wrong in a direction nobody observes until something is reverted. FR-022 calls the escape
rate "the **primary safety metric** of the product" and says why: "It cannot be gamed by the
producer because it is measured by events the producer does not author." The producer writes
oracles and modules; it does not write deploys or reverts.

The factory could report a delivery whose every oracle passed, at L2, with
`value_not_certified` and `maintainability_not_verified` stated — and had no way to record
that the thing was reverted last week. FR-023's "automatically reduced" had no enforcement
path to hook into: ceilings were computed and printed, and nothing consulted them to block
anything.

ADR-0053 built the oracle-side instrument, which audits oracles *before* deploy. This ADR
builds the other half of §2.4 level 2: the measurement of what got out *after*.

## Decision

**1. A lane is a module class, and the lanes a deployment exercised are read off its
traceability chain.** `lanes_of(report, decomposition)` is the single lane-resolution rule,
used by both `record_escape`'s validation and `measure_escapes`' denominator, so a refusal
and a rate cannot disagree about which lanes a deployment touched. A `DeliveryReport`
carries `chain` — one `TraceLink` per clause, each naming a module by *name* — and no
`decomposition_id`, so the class is resolved through the decomposition the caller holds.

**2. The denominator is distinct deployed report ids; the numerator is distinct defect
values.** The unit of a change is a deployed `DeliveryReport`, keyed by `report_id`, because
a re-render of one report is one change rather than two. The numerator counts distinct
`defect` values, because FR-021 names three kinds of event and one defect can produce two of
them — a revert and then a hot-fix — and counting rows would report one failure as two.
FR-021 wants the *kinds* recorded, which they are; FR-022 wants the *rate*, which is a rate
of defects. `EscapeReport.deployed_reports` is a **field, not a sum of the per-lane rows**,
because one report spanning four lanes is *one* change and appears in four denominators;
summing the rows reported four. A test found that, not a reading.

**3. The denominator includes the change that escaped.** An escape is recorded against a
deployed report, so that report is in the lane's set by construction. The rate is therefore
conservatively high — one escape in one deployment reads as 1.0 — and that is the correct
direction for a safety metric. The report states it, because a reader who assumes escaped
changes are excluded would compute a lower number from the same ledger.

**4. The band is derived, not stored.** FR-021 asks an escape to be recorded against the
change, its lane, "its oracle-strength band, and its autonomy level". `EscapeEvent` carries
the change and the lane; the band is derived at read time as
`contract.weakest_oracle_rank` — the same number `Contract.ceiling` is computed from — so an
escape and a delivery cannot disagree about what band a change was in. Storing it would
freeze the number in force on the day of recording, and FR-023 reads the *current* rate to
decide the *current* ceiling; a stored band would let a re-measured contract keep lowering an
autonomy it no longer carries. A lane whose deployments no contract in the log accounts for
reports `oracle_ranks=()` rather than a guess.

**5. The reduction is one level, non-cumulative, and clamps at L0.** §5.4's own modifier unit
is "−1 level" and the ladder is ordinal; the spec supplies no other quantum. It is a function
of the *current* rate, so it is in force while the rate is over budget and lifts when the
rate returns — which is what "reduced until escape rate returns to budget" says. A ratchet to
L0 would be an invented policy. The reduction composes with the module-class ceiling via
`min`, so a G7 lane may be lowered to L0 and never raised.

**6. Unset is not zero.** FR-023 reduces a lane over its *declared* budget, so the budget is a
deployment's declaration (`load_escape_budget`, wired through `SOFACT_ESCAPE_BUDGET`), not a
constant in the product. §20.3 item 4 records that no escape baseline exists until there has
been a deployment, and NFR-024 forbids reporting a target the product has not measured — so
there is no default. A lane absent from the mapping is **unbudgeted**, reported as such, with
`over_budget=None` (not `False`), because "no threshold declared" and "measured under
threshold" are different statements.

**7. The override is a ledger row, not a render parameter.** This is where FR-023 differs from
FR-031: FR-031's override is threaded into one render, but FR-023's reduction *persists*, so
the override that lifts it must persist too. `state.latest_escape_override(lane)` reads the
latest per lane — `gate_cost`'s rule — so a re-record supersedes rather than stacks, and an
override is a `str | None` **name**, because an unnamed one is the silent downgrade ADR-0045
refused.

**8. The over-budget check reports; it does not fail.** The plan called for FR-031's exact
shape (`passed = not over_budget or override is recorded`). Implemented that way, it
deadlocked: the rate is escapes over deployments, so the only way it returns to budget is by
deploying changes that hold — and a failing check refuses exactly that deploy. The recovery
FR-023 promises would be unreachable without an override, which would make recording an
override the routine first step of every recovery. That is how a gate teaches its operators
to bypass it (ADR-0040's argument, applied here). The check is therefore
`escape_ceiling_applied` with `passed=True`, matching `topology_ceiling_applied`'s shape. The
reduction is still real — it reaches `module_autonomy` through `lane_ceilings`, and FR-119
makes the deploy a human decision over the reduced number. A second reporting check,
`escape_budget_declared`, names every unbudgeted lane so an unconfigured deployment says
"FR-023 is not in force here" rather than reading as clean.

**9. The delivery and its escape table share one timestamp.** `measure_escapes` takes
`rendered_at`, and `delivery.report` pins it, because the escape table is a statement *about*
the delivery and a table stamped with the moment it was folded would date a delivery's own
evidence to a different second.

**10. An empty measurement claims nothing.** `discharged`/`not_implemented` return `()` when
no change was deployed — `IntegrationCheck`'s and `OracleAuditReport`'s vacuous-pass refusal.
A rate over zero deployments is not a clearance.

## Consequences

The honest limit, which is **not** FR-022's claim: a producer cannot inflate this number, but
an operator who does not record an escape lowers it, and no code can prevent that. FR-021's
recording discipline is a human obligation, and pretending otherwise would be the factory
grading its own homework one level up. The report names the limit rather than letting "cannot
be gamed by the producer" be read as "cannot be gamed".

A report describes the log at the moment it is rendered, so an escape recorded *after* a
delivery is not in that delivery's report; the reduction appears in the next render. That is
not a gap in the metric — the rate is a fold over the whole ledger — but it is a fact a
reader of a stored report needs, and FR-117's reports are versioned precisely so an approver's
copy stays as it was.

FR-157's dependency now exists: its requirement is "L2–L3 with escape-rate tracking
(FR-107)", and the roadmap recorded it as unbuilt because the rate was absent.

## Evidence

- `tests/ci/test_escape.py` — 42 tests: the two refusals (an escape against an undeployed
  report; a lane the report does not exercise), the vacuous pass, the denominator rule (a
  re-render carrying the same `report_id` is not a second change; `deployed_changes` is 1 for
  a double-deploy of one report), the numerator rule (revert+hotfix of one defect is one
  escape), the reduction (over budget lowers one level; back under lifts it; a G7 lane lowers
  to L0 and no further), the override (attributed by name, refused without one), the
  derived-band rule (the band moves when a different contract is supplied; a missing contract
  yields `()` rather than a guess), and the shared `rendered_at`.
- `tests/ci/test_delivery.py` — 14 tests: the escape ceiling reaching `module_autonomy`,
  the two reporting checks, and the six `## Escapes` states in the rendered document.
- `tests/ci/test_state.py` — two new ledger kinds, `ProjectState` 27 → 29 fields.
- `tests/ci/test_cli.py` — 14 tests: `sofact escape`, `sofact escapes` (per lane and per
  granted ceiling), and the attributed-or-refused override, including a real `budget.json`
  through `SOFACT_ESCAPE_BUDGET`.
- Five canaries, each asserting its target string was present and unique before mutating and
  each reverted from a file backup. Two fired only after replanting: one had mutated a count
  inside a string no test reads, and one had mutated a per-lane set that collapses duplicate
  report ids on its own — the second exposed a real gap, closed by asserting
  `report.deployed_changes == 1`.
