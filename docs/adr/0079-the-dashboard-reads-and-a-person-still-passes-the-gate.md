# 0079 — The dashboard reads, and a person still passes the gate

- **Status:** Accepted
- **Date:** 2026-10-19
- **Related:** FR-061, FR-064, FR-120, FR-172, FR-173, §3.3;
  [ADR-0070](0070-the-front-door-stops-at-every-gate-and-a-model-answer-is-not-an-answer.md),
  [ADR-0076](0076-a-gate-that-can-be-decided-is-not-a-gate-that-has-been-passed.md)

## Context

`sofact status`, `sofact phase` and `sofact ledger` each answer one question well, and an
operator asking "what do I do next" has to read three outputs and hold the gate table in
their head. The product is a pipeline whose whole discipline is that nothing proceeds past
a gate a person has not passed, so the state an operator most needs to see — *which gate,
which checks, what now* — was spread across three commands and a driver sentence printed
only when `build` happened to run.

## Decision

**`sofact tui` is a renderer over a snapshot, and the snapshot is a separate module.**

`sofact.dashboard` folds `ProjectState` plus three service reads (`readiness`,
`current_gate_checks`, `unanswered_proposals`) into a `Snapshot` — a frozen dataclass of
plain values. It imports no terminal library. `sofact.tui` renders that snapshot and does
nothing else. The split is the design, not tidiness: it makes "what is the operator's next
move" testable with the `service` fixture the rest of the suite uses, in a test that never
starts a terminal. An app that folded the log itself would put that logic where nothing
reaches it without a headless terminal.

**The next move is derived from the same facts the driver reads, and defers where they
could drift.** `Snapshot.next_move` asks `PhaseAdvance.failed` rather than re-deriving
"the machine half failed", and its branches follow `DriverRun.next_human_verb`'s order. A
gate whose machine half failed names the phase's **producer** verb and not
`gate --approve`, which could only refuse — the dead end ADR-0070 records. A gate with
**no** checks is a third case: nothing has been presented, so the sentence names the
producer and says nothing about approving. The first version of the test asserted only the
verb, and a canary that killed the failed-gate branch passed — both arms name `specify`.
The distinction is the parenthetical, and it is now asserted.

**It can do two things, and they are the two §3.3 keeps human.** Answering an elicitation
question, and approving a gate. The approve action asks for the operator's name rather than
defaulting to `"operator"`, because an approval is attributed and an unattributed one is a
row nobody is accountable for. The service still decides: `approve_gate` recomputes the
machine half from the current artefact and refuses a failed check whatever was typed, so
the TUI cannot pass a gate the CLI would not. That is asserted by calling `approve_gate`
directly in `test_the_service_refuses_a_failed_gate_even_if_the_ui_is_bypassed` — a guard
that exists only in the renderer is a guard a second front end would not have.

**It cannot drive past a gate.** `b` runs `sofact.driver.run_goal`, which stops at every
gate by construction; there is no call to `approve_gate` anywhere in `driver.py`.

**The checks shown are the recomputed ones.** `read_snapshot` calls
`current_gate_checks` and falls back to the presented row only when there is no artefact
to recompute from — `approve_gate`'s own rule. A screen showing the frozen row would tell
an operator whose repair had made every check pass that the gate still failed.

## Consequences

- `textual>=8.0` is a runtime dependency, imported inside the `tui` command rather than at
  `cli.py` module scope, so a machine surface that imports the CLI pays nothing for a
  terminal library it will never open.
- `Snapshot` holds no callable, asserted structurally in `test_a_snapshot_holds_no_callable`:
  "the app chooses not to mutate" is a promise, and a frozen dataclass of plain values is a
  property.
- The verb is in `llms.txt` and the README, and `test_llms.py`'s forward direction is what
  required it — the gate fired on the first run after the command was registered, which is
  the behaviour it exists for.
- Four canaries were planted and **one missed**: disabling the `gate.failed` branch changed
  nothing observable, because the two branches differ only in their parenthetical. The test
  was widened rather than the mutation accepted.
