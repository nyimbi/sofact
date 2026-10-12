# 0034 — A rollback is a reading rule, and the log keeps what it hides

- **Status:** Accepted
- **Date:** 2026-10-12
- **Related:** FR-094, FR-003, FR-099, FR-060, FR-061, FR-141; [ADR-0007](0007-the-elicitation-gate-is-deterministic.md),
  [ADR-0015](0015-a-verdict-describes-one-run.md), [ADR-0033](0033-a-worktree-is-per-module-and-a-wave-is-isolated-only-when-every-step-has-one.md)

## Context

The capability map's §5 build order named this as item 5 — "ledger rollback to a chosen
entry", what Paperclip's "rollback" is — and item 4, the per-module worktree, is what
unblocked it: a rollback is only safe once the tree a rolled-back session wrote to is
isolated from the tree the current work is in.

The §2.1 row that recorded the gap stated the design almost completely: "Over an
append-only fold this is cheap: replay to a chosen entry index." The one word it did not
settle is *how*, because the log is not a value the operator holds. Three constraints
decided the shape.

**FR-003 makes the log append-only, and the chain is what makes that load-bearing.** A
rollback that truncated the file would destroy the evidence that the rolled-back work
happened — which is the one thing an operator rolling back most needs to keep, because
the reason to roll back is usually a judgement about work that *was* done. It would also
break every `entry_hash` after the cut, so `require_intact` would refuse the project
outright: a rollback implemented as truncation does not produce an older project, it
produces an unreadable one.

**A cut is a decision, and a decision is a fact about the project.** ADR-0007 settled
this shape already for a re-answered elicitation dimension: the later answer supersedes,
the log keeps both, and the fold reports the current one. A rollback is the same
structure applied to the log's own reading rule rather than to one dimension's value.

**A rolled-back state must not be mistakable for a project that never got that far.**
This is the failure mode the whole record is organised around. Both states have the same
goals, the same contracts, the same reports; the difference is a decision, and a decision
that leaves no trace in the state is a state that lies about how it was reached — to the
gates as much as to a reader.

## Decision

**A rollback is a reading rule over an append-only log. The cut is recorded in the log it
cuts, and the fold applies it.**

1. **`Cut` is a view: `target_index`, `at`, `by`, `reason`.** A row is appended with
   `LedgerKind.CUT_RECORDED`, and the log grows. Nothing is deleted, no hash changes, and
   `verify_chain` is unaffected — measured: after a cut the chain still verifies and the
   log is exactly one row longer.
2. **The fold's rule is "read through the target, skip to the cut row, then fold
   normally."** Entries after `target_index` and before the cut row are skipped;
   everything appended after the cut row folds as usual. Both halves are required. Without
   the skip there is no rollback; without the resume, a cut is a permanent dead end and
   the project can never make progress again — so the second half is what makes a cut
   "the state as of entry N, plus whatever has happened since I decided that".
3. **The latest cut wins, and earlier cuts stay visible.** Cutting again to a later entry
   un-does the first, because a stack of cuts whose effects composed would make the
   current state depend on the *history* of rollback decisions rather than on one
   decision — and "read as of entry M" is not a statement that should stack.
   `ProjectState.cuts` collects every cut row the log holds, and `ProjectState.cut`
   derives the operative one from the last of them, so the two cannot disagree.
4. **A cut row is never hidden, including by a later cut's skip.** The skip exists to
   un-do *work*, and a cut is not work — it is the record of a decision about how to read
   the log. Hiding one would make the log's account of its own reading rules depend on the
   most recent reading rule, so an operator who rolled back furthest would see the least
   of their rollback history, which is backwards: the reason an earlier cut was taken is
   exactly what the operator re-cutting needs. It would also let a skip swallow the
   *reason* for a rollback, leaving the unexplained gap decision 6 exists to prevent.
   This was found by testing it: the first implementation hid the whole range and
   `test_a_later_cut_supersedes_an_earlier_one` failed with the earlier cut gone from
   `state.cuts`. The rule was wrong, not the test.
5. **`ProjectState.cut` is derived, not stored.** The obvious modelling — a `cut` field
   set from the latest row — puts the same fact in two places: the field and the skip the
   fold already applied. Two descriptions of one decision is how a state comes to disagree
   with itself, so the fold collects the rows and the property derives the operative one.
6. **The service refuses three cuts, and the fold asserts one of them again.** A target
   past the end would hide nothing while looking like it hid something, which is the one
   failure a rollback may not have; a target at the present rolls nothing back; an empty
   log has nothing to cut to. `by` and `reason` are assertions, because an unattributed
   cut is unaccountable and an unexplained one reads as a bug. The "strictly behind"
   invariant is re-asserted inside `_hidden_by_latest_cut` rather than trusted from the
   service: the log is a file, and the fold is what has to hold when someone edits it.
7. **`sofact rollback --to N --reason ...` is the operator's verb, and it prints what it
   did not delete.** The output names the number of entries hidden and says "none
   deleted", because the single most likely misreading of a rollback is that the work is
   gone.
8. **`sofact status` says when the project is read under a cut, and it says so first.**
   Every other line `status` prints — the phase, the readiness, the draft — is read under
   the cut, so a status that stayed silent would present a rolled-back project as the
   current one. It is printed before the readiness loop for a smaller reason with the
   same shape: that loop rebinds `state` to each dimension's status, so the cut has to be
   read off the state while it is still the project's.

## Alternatives refused

* **Truncate the log to the target.** Refused in the Context: it destroys the evidence the
  operator needs and breaks every subsequent hash, so the result is an unreadable project
  rather than an older one. This is what FR-003 forbids, and the chain is the reason the
  prohibition is structural rather than stylistic.
* **Snapshot the state and restore it as a new value.** Refused: it makes the state a
  stored artefact rather than a derived one, which is the property the whole module exists
  to keep (`state.py`'s own docstring: "if state could be assembled by anything other than
  the log, the log would not be the record of what happened"). It also creates a second
  thing to keep in sync with the log, and a snapshot that drifts from its log is a state
  nobody can date.
* **Write the cut as a rewritten `ProjectState`.** Refused for the same reason plus
  FR-003's: a state is derived, and a rewrite of one is an edit to the log's meaning that
  the chain cannot witness.
* **Compose successive cuts.** Refused in decision 3. Composition makes the current state
  a function of a decision history, which is strictly harder to reason about than a
  function of one decision, and the operator's mental model ("read as of entry N") is
  already single-valued.
* **Hide the superseded cut rows too.** Refused in decision 4, and it was the first
  implementation. A skip that hides reading rules makes the log's self-description depend
  on its last line.
* **Refuse a cut to a later entry than an existing cut.** Refused: that is precisely how
  an operator un-does a rollback they regret, and requiring a second verb for it would
  make the common case the awkward one.
* **Gate the verb on `--concurrent` or on the tree being isolated.** Refused: FR-141's
  worktree is per module and per wave, and a cut is a log operation that touches no tree
  at all. Item 4 unblocked item 5 in the sense that a rollback is *useful* once the tree
  is isolated — the work a cut hides is not sitting in the current tree — not in the sense
  that the log verb needs a tree.

## Consequences

* **A rolled-back project is legible as one.** `ProjectState.cut` is the property that
  says so, and the capability map's §2.1 row moves from "Covered, partly — there is no
  operator rollback verb" to "Covered, stronger".
* **The log grows monotonically, including across rollbacks.** A project that rolls back
  ten times has ten more rows than one that did not, and every one of them is a decision
  the next reader can see. This is the intended cost: the alternative is a log that
  cannot say what was decided about it.
* **`fold` reads the log twice, in effect.** `_cut_rows` walks the entries to find the cut
  rows, and the main loop walks them again. Both are O(n) over a tuple already in memory,
  and the fold is called once per append-invalidated state, so the second walk is not a
  cost worth a cache — and a cache of "where the cuts are" is a second copy of a fact the
  log holds.
* **`ProjectState` gains a field and a property, and `test_state.py`'s census enforces
  the field.** The `KIND_TO_FIELD` mapping is total in both directions, so a new
  `LedgerKind` without a state field fails a test rather than disappearing quietly;
  `CUT_RECORDED: "cuts"` is what keeps that true. The property is not in the census and
  does not need to be: it is derived from the field, so it cannot go stale against it.
* **A cut to an index that a later append made ambiguous is still well-defined.** The
  target names a position in an append-only log, so it never shifts: the entry that was
  index 40 when the cut was taken is index 40 forever. This is a property of the
  append-only design and not of the cut, and it is worth stating because it is what makes
  the recorded `target_index` durable across later writes.

## Evidence

* `src/sofact/views.py` — `Cut`, `LedgerKind.CUT_RECORDED`, `ProjectState.cuts`, the
  `ProjectState.cut` property.
* `src/sofact/state.py` — `_cut_rows`, `_hidden_by_latest_cut`, the skip at the head of
  `fold`'s loop, the `CUT_RECORDED` arm.
* `src/sofact/service.py` — `FactoryService.cut` and its three refusals.
* `src/sofact/cli.py` — the `rollback` verb, and the `status` line that reports a cut in
  force.
* `tests/ci/test_state.py` — 4 tests: a cut hides the entries after its target and leaves
  the log longer; the project resumes after a cut; a later cut supersedes an earlier one;
  a cut that targets its own row or the future is refused by the fold's assertion.
* `tests/ci/test_service.py::TestRollback` — 5 tests: a cut hides work and keeps the log;
  a cut to the present is refused; a cut past the end is refused; a cut on an empty log is
  refused; a cut needs an operator and a reason.
* `tests/ci/test_cli.py::TestTheRollbackVerb` — 5 tests: the verb hides the work and says
  "none deleted"; the log keeps what the rollback hid and the chain still verifies; a
  target in the future is refused with exit 1 and no traceback; `--reason` is required;
  `status` reports the cut it is reading under.
* **Canaries**, each with the target string asserted present before the patch and the file
  restored from a backup rather than from git:
  * `FactoryService.cut`'s bounds check replaced with `if False:` — both
    `test_a_cut_past_the_end_is_refused` and the CLI's
    `test_a_target_in_the_future_is_refused` failed, at both layers.
  * `_hidden_by_latest_cut`'s assertion replaced with `assert True or ...` —
    `test_a_cut_that_targets_itself_or_the_future_is_refused` failed.
  * `_status`'s `cut = state.cut` replaced with `cut = None` —
    `test_status_says_the_project_is_read_under_a_cut` failed.
* Measured: after a cut, `verify_chain().ok is True` and the log holds exactly one more
  row than before it.
* `tests/ci` at this commit: **753 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

* FR-003 (append-only, hash-chained log), FR-094 (a decomposition is revisable), FR-099 (a
  re-dispatch finds what the last one left), FR-060 and FR-061 (the phase machine and its
  gates).
* [ADR-0007](0007-the-elicitation-gate-is-deterministic.md) — the supersede-don't-
  append shape this record applies to the log's reading rule.
* [ADR-0015](0015-a-verdict-describes-one-run.md) — the same question asked of verdicts.
* [ADR-0033](0033-a-worktree-is-per-module-and-a-wave-is-isolated-only-when-every-step-has-one.md)
  — item 4, which made item 5 useful.
* `docs/research/orchestrator-capabilities/README.md` §2.1 — the row this closes.
