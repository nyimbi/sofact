# 0069 — A goal mode is not a forced entry, and an unmeasured turn is not one

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** FR-135, FR-144, FR-145, FR-153, NFR-024, §20.3 item 6a, §20.4, R25;
  [ADR-0019](0019-a-capability-is-measured-by-a-differential.md),
  [ADR-0043](0043-a-gate-cost-is-asked-for-because-nothing-observes-a-person-reading.md),
  [ADR-0054](0054-the-escape-instrument-is-built-and-its-baseline-is-unmeasured.md),
  [ADR-0062](0062-the-change-cost-instrument-and-its-unmeasured-baseline.md),
  [ADR-0068](0068-a-diff-review-is-asked-for-and-the-diffs-nobody-read-are-part-of-the-number.md)

## Context

**§20.3 M0 item 6a** is the probe the whole delegated-P5 design rests on, and the spec
states what is still open in its own words:

> What remains open is not whether the capability exists but whether entry can be
> **forced** and continuations observed.

The **capability** half is answered. [S21] measured that `dsh`'s `goal` package is present
and loaded, and that in a live unattended run the producer never entered it — zero
goal-typed events, `todo_write` substituted, one turn, `finish_reason: completed`. Goal
mode is *available and model-discretionary*, which is why `GoalEntry` ranks its mechanisms
by forcefulness and why `DispatchRecord.capability_loss` reports a single-shot run rather
than letting a plan appear honoured (FR-144).

**What was missing is the reading.** Two fields carried item 6a's answer per dispatch —
`DispatchRecord.goal_entry_observed` and `DispatchRecord.continuations_observed` — and
**nothing in `src/` read either of them**. They were written by `ConfiguredHarnessAdapter`,
asserted in one test each (`test_harness.py:1110`, `:1162`), and referenced nowhere else
outside their own definitions. This is the defect class this repository keeps finding: a
field is collected and no reader ever fails, so the question has an answer in the log that
no surface can state. `docs/research/roadmap-gap/README.md` listed item 6a among the M0
items with "no instrument at all", which was accurate about the *reading* and understated
the record — the facts were there, the fold was not.

**A second defect, found while building the first.** `parse_continuations` hardcoded the
string `"turn/start"` and opened with `_ = spec`, discarding its `HarnessSpec`. It was the
one reader in `harness.py` that did not take its fact from the table — `parse_completion`,
`parse_usage` and `parse_goal_entry` all read a declared path or event. A literal cannot
report *absent*, so the parser could not distinguish a harness that numbers its turns from
one that does not; it could only distinguish a record that happened to contain the name.

## Decisions

### 1. The mode is a prediction; the entry is the observation

`GoalModeRow` carries `mode` (what the *probe* decided before the session started),
`entry` (how the objective actually reached the session, read from the record afterwards)
and `continuations` (turns, where numbered). They are never merged.

A dispatch can carry a goal `mode` and a `prompt` entry, and that pair *is* item 6a. The
mode alone is the flattering reading — "goal mode ran" — available from a value the probe
wrote before anything ran. `is_contradiction` is the conjunction, and it is the finding the
reading exists to print.

### 2. An unwitnessed dispatch is carried and excluded by the denominator, never filtered

`measure_goal_mode` folds **every** dispatch, including the ones never sent and the ones
whose session left no record. `witnessed` is the filter, and it is a property rather than a
`if` in the comprehension.

Filtering at the fold would make "no goal event was found" and "no record was read"
observationally identical — the two answers §20.3 item 6a must keep apart, and only the
first is evidence. A refusal has a mode and no entry, and dropping it would make an
unusable harness invisible in a report about whether a harness could run a goal at all.

### 3. `None` entry is not a prompt, and `entry_forced` has three states

`entry is None` means *not observed*, which is a different fact from `GoalEntry.PROMPT`. A
session nobody read showed nothing, so it cannot contradict a mode: `is_contradiction`
requires `entry is not None`. Reading `None` as a prompt would report every unwitnessed
dispatch as a capability loss — the same error as reporting an unmeasured turn count as one
turn, in the other direction.

`entry_forced` is `bool | None`: `True` (a session shows a forced entry, so the mechanism
works on this configuration), `False` (sessions were read and none was forced — [S21]
reproduced, not a proof of impossibility), `None` (no session record was read, so the
question was never asked). Collapsing `False` and `None` would report an absent instrument
as a measured negative, which is ADR-0019's defect one subsystem over.

### 4. The turn event is declared in the table, and an absent declaration is a measurement

`HarnessSpec.continuation_event` joins `usage_path`, `completion_reason_path` and
`goal_event_types` as a fact the spec states and the parser reads. `dsh` declares
`turn/start`; `pi`, `claude` and `opencode` declare none, and for them
`parse_continuations` returns `None` **by construction** rather than by finding nothing.

The two are different: a harness with no turn boundary reports `None` because the table
says it numbers no turns, which is true even for a record that happens to contain a
`turn/start`. `None` is never `1` — a fabricated single turn would report the cheapest
possible goal behaviour as the observed one (NFR-024).

### 5. The mean travels with its coverage, and the discharge refuses the vacuous pass

`continuation_coverage` returns `(measured, witnessed)` and is printed beside the mean, for
ADR-0068's reason: a mean over the harnesses that number their turns is a fact about *those
harnesses*, and a reader who takes it for the project's goal behaviour has been misled by a
subset that happens to be the measurable one. `None` when nothing was witnessed, never
`(0, 0)`.

`discharged` returns `()` unless a forced entry was observed. This is the one place the
vacuous pass is the **likely** outcome rather than an edge case: a project whose producers
never entered goal mode has a full dispatch history and no FR-153. A reading that counted
goal *modes* would discharge on exactly the projects that have not demonstrated the
capability — the failure `EscapeReport.discharged` and `ChangeCostReport.discharged` both
refuse, applied where it matters most.

### 6. FR-135 is deliberately not in the requirement set

`GOAL_MODE_REQUIREMENTS` is `("FR-144", "FR-153")`. The capability matrix is the *probe's*
discharge, on a `HarnessProfile` this fold does not read; a dispatch is evidence about what
one session did, not about the matrix. Naming FR-135 here would let a project's dispatch
history stand in for a probe it never ran.

### 7. The verb's exit code carries the finding

`sofact goalmode` exits `1` on both bad branches: an empty history (item 6a unmeasured) and
a history with no forced entry (FR-144's degradation, unreported by any other surface).
§20.3 calls this probe blocking for the entire Mode G design, so a verb that printed the bad
news and exited `0` would let a pipeline treat an unforced goal mode as answered.

## Alternatives refused

- **Discharge FR-153 on a goal *mode*.** Refused: it is the probe's pre-session prediction,
  and it is true on exactly the projects that have not exercised the capability. This is
  canary 5.
- **Filter unwitnessed dispatches at the fold.** Refused: it makes "no goal event found" and
  "no record read" the same observation. This is canary 3.
- **Report `entry is None` as `PROMPT`.** Refused: a session nobody read showed nothing, and
  the contradiction is a claim about what the record showed.
- **Keep the `turn/start` literal and add a spec field beside it.** Refused: two sources for
  one fact, and the literal is the one that cannot report absence.
- **Return `0` or `1` for an unmeasured continuation count.** Refused: NFR-024 — zero is the
  claim that every session ran one turn, which a harness writing no boundary has not made.
- **Make the check report-and-never-gate, as FR-160's and item 3's do.** Refused for the
  *verb*, though the same argument was weighed: those instruments measure the operator's own
  spend, where a failure would block a deploy for a number nobody was asked for yet. This one
  measures whether the design's load-bearing assumption holds, and §20.3 makes it blocking.
  The `GoalModeReport` itself gates nothing — `discharged` is a property, and the exit code
  is the verb's, so a library caller reads the finding without a refusal.
- **Fold it into the delivery report.** Refused: item 6a is a fact about the *harness
  configuration*, not about one delivery, and a per-delivery section would re-state one
  project-wide answer under every report. `sofact attempts` (FR-102) is the precedent — a
  CLI verb over the dispatch history, no document section.

## Consequences

- §20.3 M0 item 6a is no longer one of M0's "no instrument at all" items. The **probe
  remains open**: this reads what dispatched sessions recorded, and it cannot *force* entry
  on a harness that offers no mechanism — that needs a live run against a harness whose
  argv enters goal mode by construction, which no configured spec does today. The roadmap's
  M0 narrative moves the item out of that list without claiming the blocking probe is
  answered.
- `HarnessSpec.continuation_event` is a new field, so `synthetic.base_spec` declares it and
  the field-class lists in `harness.py` carry it. A spec that emits turns and does not name
  them now reports `None`, which is the honest reading of a table that makes no claim.
- Two fields that were written and never read now have a reader, which is the fix for the
  defect class rather than for the instance: `goal_entry_observed` and
  `continuations_observed` were the whole of item 6a's record and nothing consumed either.
- The reading is a **negative over one configuration**, and the caveat says so on every
  report. `GOAL_ENTRY_NOT_FORCED` names [S21] and states that a zero is "not observed to be
  forcible" rather than "cannot be forced" — the mechanism may exist on a harness this
  project never dispatched.

## Evidence

Six canaries, each watched before it was believed, reverted from a `cp f /tmp/f.bak` backup
with `__pycache__` cleared and `md5 -q` compared against the backup:

- `is_contradiction` losing its `entry is not None` guard: 1 failed
  (`test_a_dispatch_with_no_record_is_unwitnessed_rather_than_a_prompt`). This one was
  **caught by the suite before any canary was run** — the test failed against the first
  implementation, and the fix went into `views.py` rather than into the test.
- `parse_continuations` back to the `"turn/start"` literal: **MISSED** on the first run —
  all 18 tests passed. The mutation changed the code without changing the observation,
  because the synthetic spec declares `turn/start` and no test named a *different* or an
  *absent* declaration. The miss was a gap in the tests, not a false alarm about the gate:
  two cases were added to `test_harness.py`
  (`test_the_turn_event_is_read_from_the_spec_not_hardcoded`,
  `test_a_spec_that_numbers_no_turns_reports_None_even_where_they_are_present`) and the
  same mutation then failed, with `assert 2 is None`.
- `measure_goal_mode` filtering unwitnessed rows: **MISSED** on the first run — 18 passed,
  because nothing asserted the rows were *carried*. The test that makes the fold's own
  docstring checkable was added
  (`test_an_unwitnessed_dispatch_is_carried_rather_than_dropped`) and the mutation then
  failed.
- `entry_forced` collapsing `None` into `False`: 2 failed
  (`test_entry_forced_is_three_states_not_two`, `test_an_empty_history_claims_nothing`).
- `discharged` keyed on `goal_dispatches` instead of `forced_entries`: 1 failed
  (`test_no_forced_entry_discharges_nothing`), the vacuous pass the whole reading refuses.
- The verb's unforced branch exiting `0`: 1 failed
  (`test_an_unforced_goal_mode_exits_non_zero`), `exit_code` `0` against the expected `1`.

Two of the six missed on the first attempt and both misses are recorded because the miss is
the finding: a canary whose mutation the tests cannot observe is a statement about the
tests, and in both cases the fix was to widen the tests rather than to accept the mutation
as equivalent.
