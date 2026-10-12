# 30. Phases are a state machine, and a gate is a type boundary

Date 2026-10-12. Status: Accepted. Amends nothing; implements FR-060, FR-061, FR-062
and NFR-028.

## Context

FR-060 asks for "explicit state machine transitions, persisted durably, auditable, and
resumable after SIGKILL at any point". Before this record none of that existed. There
was no phase vocabulary anywhere in `src/` — `grep -rn "Phase"` returned nothing — and
"which phase are we in" could only be answered by inferring it from whichever ledger
rows happened to be present. The root command's own help text promised a resume
("run `sofact` to resume") that resumed the *interrogation*, not a phase.

FR-061 is the requirement that makes this more than bookkeeping: "There must be no
configuration under which the factory proceeds past an unapproved gate." That is a
statement about reachability, and it is not satisfiable by a check that a caller is
trusted to run.

The precedent for the shape is [`DecompositionGate`](../src/sofact/views.py), which
splits a gate into a machine half (`checks`) and a human half (`approved_by`), and whose
`is_satisfied` requires both.

## Decision

**1. The phase vocabulary is a closed enum with the sequence derived from it.**
`Phase` has ten members, P0 to P9, and `PHASE_SEQUENCE` is `tuple(Phase)` rather than a
written-out list, so the sequence cannot drift from the enum by being spelled twice.

**P7 is a member even though §3.2's summary table omits it.** The pipeline diagram
places `P7 Integrate` between P6 and the deploy gate, and FR-111 to FR-116 give it
requirements and two implemented checks. The table is the thing that is wrong. A phase
machine built from the table would have nowhere to record an integration pass, which is
the artefact FR-114's minimum violating set is read from.

**2. A transition is its own ledger row, not a value recomputed from others.**
`PhaseAdvance` carries the phase, its new status, when, who, the machine checks, and the
approval. FR-060 asks for transitions that are "explicit ... persisted durably,
auditable", and a value derived from other rows is none of those — it is a guess that
happens to agree with the log today. The fold reports the latest transition per phase,
last-write-wins, exactly as a re-answered elicitation dimension does (ADR-0007): the
history keeps both rows, the fold reports the settled one.

**3. FR-061 is enforced by the constructor, not by a runtime check.**
`PhaseAdvance` refuses to be built in two shapes: a gate phase marked `COMPLETE` with no
`approved_by`, and an ungated phase carrying an approval at all. A refusal at
construction is stronger than a check, because there is no code path that can write the
lie in the first place — including a code path that forgets to check.

**4. `advance_phase` cannot pass a gate, and `approve_gate` is the only way through.**
The machine half can move an ungated phase and can present a gated one
(`AWAITING_GATE`), and it raises with the name of the verb that can complete it. The
human half is a separate method that names who approved. The hard stop is the type
boundary between the two, not a rule either one follows.

**5. One check does the work of two: every earlier phase must be complete.**
`advance_phase` refuses when any earlier phase is not `COMPLETE`. This is what makes
FR-061 structural — the only route to P5 runs through P2 and P3, so there is no
configuration in which machine work happens past an unapproved gate. It also subsumes
ordering: a later phase cannot have been worked while an earlier one is incomplete,
because reaching the later one required the earlier one first.

An explicit "is a later phase already done" guard was written here first and then
**removed as unreachable**. It could not fire, and a guard that cannot fire is a claim
about behaviour that nothing tests. This is the same rule the fold's docstring already
states about its missing `case _`.

**6. An open gate is reported as the current phase, not skipped past.** `current_phase`
returns a phase left `AWAITING_GATE` rather than the next one, and `open_gate` is a
property so a caller asks the question directly instead of re-deriving the gate table.
`sofact phase` exits 1 while a gate is open, which is FR-061 available to a script.

## Consequences

- **A phase cannot be entered without passing the gates before it, and this is now a
  refusal rather than a convention.** The cost is that a pipeline which legitimately
  begins mid-way — a Mode M maintenance lane starting at P4, say — cannot be expressed
  yet. FR-124's per-deployment topology is where that belongs, and it is unbuilt; until
  then, refusing is the honest answer and a bypass flag would be exactly the
  configuration FR-061 says must not exist.
- **`ProjectState` gains an eighteenth field**, and `test_state.py` pins that count, so a
  new field cannot be added without the test noticing. That test fired on this change,
  which is the behaviour it exists for.
- **The gate's machine half is currently presented with no checks** by `sofact gate
  --present`, because the checks belong to the phase's own command and no phase command
  computes them yet. The CLI says so rather than offering an approval button over
  nothing, which is FR-080's "presents the specification in the operator's language"
  pointing at work still to do. When P2's artefact exists (FR-076), that command is
  where the checks are computed and passed in.
- **`AWAITING_GATE` is the state an operator most needs to see and the easiest to
  collapse.** Making it distinct from `ACTIVE` is what stops "the factory is working"
  and "the factory is stopped waiting for you" from looking the same.

## Alternatives refused

- **A phase field on the goal, updated in place.** Refused: the ledger is append-only,
  so "updated in place" is a row that supersedes an earlier one, which is what
  `PhaseAdvance` already is. A separate mutable field would be a second source of truth
  for the same fact.
- **Derive the current phase from which artefacts exist.** Refused, and it is the state
  this record replaces. It cannot distinguish a phase that has not started from one that
  is waiting at a gate, and it silently reorders when an artefact is produced out of
  order.
- **Let `advance_phase` take `approved_by` so one verb does both.** Refused: that is a
  single call in which a machine can pass a gate, which is the configuration FR-061
  forbids. The two verbs are the requirement.
- **Gate on the decomposition alone, since that is the only gate with an artefact.**
  Refused: §3.3 places four gates and argues for exactly four. Building one and calling
  the phase machine done would repeat the mistake ADR-0024 §1 records — treating two
  separate requirements as one.
- **Report an open gate but still allow the next phase to start.** Refused: that is
  FR-061 violated with a warning attached.

## Evidence

- `tests/ci/test_phase.py` — 23 tests: the enum and sequence, the four-gate count, the
  constructor refusals, the whole machine path, the two gate paths, out-of-order
  refusal, the forward check, and a restart over the same home proving the phase comes
  back from disk.
- `tests/ci/test_cli.py::TestThePhaseVerb` — 9 tests over `sofact phase` and
  `sofact gate`, including that an open gate exits 1 and that an approval with no
  presentation is refused.
- **Canaried**: deleting the forward check from `advance_phase` makes
  `test_no_phase_can_be_reached_without_passing_the_gates_before_it` and
  `test_machine_work_is_refused_while_a_gate_is_open` fail, and nothing else. The check
  was watched failing before it was believed.
