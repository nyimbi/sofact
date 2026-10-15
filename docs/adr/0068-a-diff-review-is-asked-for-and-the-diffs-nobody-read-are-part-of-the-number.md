# 0068 — A diff review is asked for, and the diffs nobody read are part of the number

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** FR-160, NFR-024, §1.4, §20.2, §20.3 item 3, §21 R13;
  [ADR-0039](0039-the-envelope-refuses-a-ceiling-and-reports-a-floor.md),
  [ADR-0043](0043-a-gate-cost-is-asked-for-because-nothing-observes-a-person-reading.md),
  [ADR-0054](0054-a-rate-needs-a-deployment-so-an-undeployed-project-reports-unmeasured.md),
  [ADR-0062](0062-a-scope-with-fewer-than-two-measured-units-reports-unmeasured.md)

## Context

**§20.3 M0 item 3** asks for one number in two places:

> **Human review time** — logged per gate *and* per diff, so §1.4's claim can be compared
> directly against the v0.1 alternative.

The **per-gate half exists** (FR-160, ADR-0043): `GateCost` carries a declared
`human_minutes` and `rework_fraction`, `LedgerKind.GATE_COST_RECORDED` is appended rather
than keyed, `ProjectState.total_human_minutes` returns `None` rather than `0` when nothing
was measured, and `delivery.py` carries a `gate_cost_reported` check that reports and never
gates. The **per-diff half did not exist**, and `docs/research/roadmap-gap/README.md`
listed item 3 among the M0 items with "no instrument at all".

**Why the second half is the load-bearing one.** §1.4 claims human attention is spent *per
platform, not per module* — gates are per-platform, work is per-module, so a 25-module
platform costs roughly what an 8-module one does. The **v0.1 alternative** is a review per
diff at "roughly four units an hour", about fifteen minutes a diff. §21 **R13** makes the
comparison explicit — "M0 item 3 compares gate-minutes to diff-minutes directly" — and
names the failure it would refute as **fatal to the business case**: integration risk
growing as `n²` while human attention stays flat. A gate-minutes total alone cannot make
that comparison; only a per-diff number can, and it does not exist unless it is asked for,
for exactly `GateCost`'s reason: nothing in SoFact observes a person reading.

**The trap this instrument is designed around.** §1.4's claim wants per-module attention to
be *small*. If forty diffs sealed and three were reviewed, a mean over the three makes
attention per diff look tiny — the flattering direction, arrived at by measuring only what
was convenient. So coverage is a first-class number beside the mean, not a footnote.

## Decisions

### 1. The diff is identified by its dispatch, and the commit is pinned beside it

`DiffReview` keys on **`dispatch_id`** and carries **`sealed_commit`** and **`step_id`**.

The step is the wrong key. A step can be dispatched more than once — a repair, a
re-dispatch after a stall — and each dispatch seals its own commit. Keying a review by step
would collapse two reviewable diffs into one and **understate** review time, which is the
one direction a measurement of the binding constraint must not be able to move.

`sealed_commit` is recorded rather than resolved at read time, for `ChangeUnit`'s reason: a
number attached to "whatever the branch tip is now" would move under the review that
produced it. A review whose figure could later be read against a different diff is not a
measurement of a diff.

### 2. A review attaches to a dispatch that sealed a commit

`record_diff_review` refuses a dispatch whose `checkout.sealed_commit is None`. This is
ADR-0043 decision 2 one requirement along: that ADR refuses a cost for a gate nobody sat
at, and this refuses a review of a diff that does not exist. A session that changed nothing
produced nothing a human could have read, and allowing it would let the per-diff total be
assembled from diffs that never happened. `seal_branch` already records the fact — it
returns the checkout with `sealed_commit=None` and only `head_commit` set when there was
nothing to commit.

**An accepted limit, named rather than left to be discovered.** `sealed_commit is None`
covers two facts that `head_commit` distinguishes: a session that changed nothing, and a
session whose producer committed its own work. For *this* question they are one fact —
SoFact sealed no diff, so there is nothing to review — and the consequence is that such a
diff is unreviewable through `sofact review`. The alternative would be letting an operator
hand-type a commit sha, which is decision 1's failure.

### 3. Rows are appended and never keyed; the reader takes the latest per dispatch

Same rule as `GATE_COST_RECORDED` and for the same reason: a second sitting on one diff is
a **second measurement**, not an edit, so the log keeps both.
`ProjectState.latest_reviews` returns one row per dispatch, so `reviewed_minutes` cannot
double-count a diff reviewed twice while the history stays intact.

### 4. Coverage travels with the mean, and `None` is not `(0, N)`

`review_coverage` returns `(reviewed, sealed)`, and the report prints `N of M sealed
diff(s)` beside the mean. The pair is not a footnote: a mean over the reviewed subset is a
fact about that subset, and a reader who takes it for the project's whole per-diff cost has
been misled in §1.4's favour — which is the failure this instrument exists to prevent.

`None` when no dispatch sealed a commit, never `(0, 0)`. `(0, N)` is a real measurement —
N diffs, none read. `(0, 0)` would read as a project that reviewed nothing when it is a
project that produced nothing to review. That is ADR-0054's and ADR-0062's rule: a number
that can only be read one way is a number nobody checked.

### 5. Both comparisons are stated, and neither is a verdict

Two comparisons live in this number and both are printed:

- **§20.3 item 3** — diff-minutes against v0.1's ~15 minutes a diff.
- **§21 R13** — gate-minutes against diff-minutes, the comparison whose failure is fatal
  to the business case.

The check states both totals and divides neither. A ratio of two *declared* numbers is a
derived claim, and "gate-minutes beat diff-minutes by 3.2×" is exactly the derived figure
ADR-0043 refused as an invention wearing a measurement's clothes. `THETA_GATE_BUILT` stays
`False`, `MODE_M_CEILING` stays L1, `EVOLVABILITY_DEBT` stays 1.0: nothing here may raise a
ceiling on an unmeasured number.

### 6. `rework_fraction` is a share of the diff and is never pooled with the gate's

For a gate the fraction is of the *slice*; for a diff it is of *what was sealed* — the
`sealed_files` denominator an operator can see. The denominators differ, so
`DeliveryReport.diff_rework_fraction` is a separate mean from `DeliveryReport.rework_fraction`
and the two are never averaged together. One mean over both would be a mean over two
populations.

### 7. The check reports and does not gate

`diff_review_reported` is `passed=True` on every branch, including the unmeasured one, for
ADR-0043 decision 5's reason: the requirement asks for the number to *appear*, not for the
deploy to depend on it. A check that failed on an unmeasured project would block a deploy
for a measurement the operator has not been asked for yet.

## Alternatives refused

- **Key the review by step.** Refused: a step dispatched twice is two diffs, and collapsing
  them understates review time — the direction that flatters §1.4's claim.
- **Key the review by `sealed_commit` alone.** Refused: the dispatch is what an operator
  addresses and what carries `step_id`, `checkout.module` and `sealed_paths`, which is what
  they need to decide *which* diff to read. The commit is pinned as an attribute instead.
- **Let the operator hand-type a commit sha.** Refused: a review would then be attachable
  to a diff nobody sealed, and the number could be read against bytes that moved.
- **Compute a ratio, or fail the check when diffs exceed v0.1's rate.** Refused: §1.3 calls
  its numbers "a hypothesis under test", and the precedent is uniform — `THETA_GATE_BUILT`
  is `False` and `MODE_M_CEILING` is L1 because a measured actual may not move a bound.
  The first over-run would teach an operator to stop recording.
- **Make it a ninth `EnvelopeDimension`.** Refused: `EnvelopeDimension` is asserted to be
  §1.3's eight rows, and `HUMAN_MINUTES` is the *per-platform* budget FR-160 unblocked for
  gate costs. A diff is per module; pooling diff-minutes into it would corrupt the one
  dimension the per-gate instrument exists to fill.
- **Report the per-diff mean without coverage.** Refused: it is the flattering direction,
  and it is the whole reason the field exists.
- **Report an unreviewed project as `0` minutes.** Refused: zero is the claim that the
  project's diffs were free to read, which is a different and false statement (NFR-024).

## Consequences

- §20.3 M0 item 3 is no longer one of M0's "no instrument at all" items. The **baseline is
  still unmeasured** — a rate needs a project somebody actually reviewed — so the roadmap's
  M0 narrative moves the item out of that list without claiming the comparison has been
  made.
- §1.4's claim is now *readable* per project and still not *settled* by one: sub-linearity
  is an observation about a population, not about a log. ADR-0043's closing consequence
  applies unchanged.
- `LedgerKind.DIFF_REVIEWED` joined the fold, which is exhaustive — adding the member
  produced a pyright error until `state.fold` handled it, and `test_state.py`'s
  `KIND_TO_FIELD` totality guard failed until the field existed. That is the mechanism
  working.
- `ProjectState.sealed_dispatches` is the single definition of the coverage denominator.
  Before it, `review_coverage` and `render_delivery` each held their own comprehension —
  two answers to one question that agree only until one is edited.
- One quantity is now stated by one function. `views.diff_review_detail` renders the
  per-diff reading for the report check, the markdown document and the CLI, and
  `V01_REVIEW_MINUTES_PER_DIFF` holds v0.1's rate so the sentence and the number cannot
  drift.

## Evidence

Six canaries, each watched before it was believed, reverted from a `cp f /tmp/f.bak`
backup with `__pycache__` cleared:

- `if diff_reviews` → `if True` in the report check: 1 failed
  (`test_an_unreviewed_project_says_so_in_the_report`), `ZeroDivisionError` at
  `delivery.py:851`.
- The sealed-diff refusal → `if False:` in `record_diff_review`: 1 failed
  (`test_a_review_of_a_dispatch_that_sealed_nothing_is_refused`), a `ValidationError` on
  `sealed_commit=None`.
- `latest_reviews` → `self.reviews` in `reviewed_minutes`: 1 failed
  (`test_a_diff_reviewed_twice_is_counted_once`), `55.0` against `15.0`.
- The coverage pair replaced by the reviewed count alone, at each of three sites — the
  module helper, `DeliveryReport.review_coverage` and `ProjectState.review_coverage`:
  1 failed at each (`test_the_report_states_the_coverage_beside_the_mean`,
  `test_the_coverage_pair_counts_reviewed_against_sealed`).
- `sealed_dispatches` unfiltered: 1 failed
  (`test_nothing_sealed_reports_no_coverage_rather_than_a_zero_pair`).
- The dedupe key replaced by `str(len(seen))`: 1 failed
  (`test_a_diff_reviewed_twice_is_counted_once`).

One canary **missed** and is recorded because the miss is the finding. The first attempt at
the `sealed_dispatches` canary was `X and tuple(self.dispatches)`, where `X` is the
comprehension — and an empty `X` short-circuits to the empty tuple, so on the
nothing-sealed case the mutation was a no-op and all 25 tests passed. The mutation changed
the code without changing the observation. Redone as an unconditional
`return tuple(self.dispatches)`, it failed at once.
