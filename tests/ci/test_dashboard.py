"""The dashboard's facts, held to the pipeline that produces them.

``sofact.dashboard`` exists so the screen's content can be asserted without a terminal.
That makes these tests the only place the TUI's *claims* are checked: the app in
``sofact.tui`` is a renderer, and a renderer tested against itself proves nothing.

The properties that matter are the ones an operator acts on:

* the next move the screen names is a command the product accepts, in the state the
  screen is showing — asserted against ``cli.app``'s registry rather than a copy of the
  verb, because a verb that reads right and parses wrong is the defect ADR-0070 records;
* a gate whose machine half failed never names ``gate --approve``, which could only
  refuse — the dead end that ADR fixed by naming the phase's producer verb instead;
* the checks shown are the **recomputed** ones, so a repaired artefact reads as repaired;
* a snapshot holds no callable, so there is no path from reading the log to mutating it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import answer_everything

from sofact._uuid7 import uuid7str
from sofact.cli import app as the_app
from sofact.dashboard import read_snapshot
from sofact.service import FactoryService
from sofact.views import (
	GATE_APPROVE_VERB,
	PHASE_GATE,
	PHASE_SEQUENCE,
	DriverRun,
	DriverTerminal,
	GateCheck,
	Phase,
	PhaseStatus,
	now,
)

_VERB = "sofact "


def _registered() -> set[str]:
	"""The commands the CLI registers, read off the object ``--help`` is built from."""
	return {
		command.name or (command.callback.__name__ if command.callback is not None else "")
		for command in the_app.registered_commands
	}


def _named_verb(move: str) -> str:
	"""The ``sofact <verb>`` a next-move sentence opens with, or ``""`` for bare ``sofact``.

	The sentences carry a parenthetical — ``(then `sofact gate --approve P2 --by <you>`)``
	— so taking the first two words would read ``sofact`` and stop. This reads the
	opening clause up to the first two-space separator, which is how every branch of
	:attr:`Snapshot.next_move` is written.
	"""
	opening = move.split("  (", 1)[0].strip()
	if opening == "sofact":
		return "sofact"
	if opening.startswith(_VERB):
		return opening.split()[1]
	return ""


async def _stopped_at_a_gate(service: FactoryService, *, passed: bool) -> Phase:
	"""Bring the pipeline to P2's gate with a check that passed or failed."""
	await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
	await service.advance_phase(
		Phase.SPECIFY,
		PhaseStatus.AWAITING_GATE,
		checks=(
			GateCheck(
				name="criteria_are_machine_checkable",
				passed=passed,
				detail="6 of 6" if passed else "0 of 6: no criterion names a command",
			),
		),
	)
	return Phase.SPECIFY


# --------------------------------------------------------------------------- #
# an empty log
# --------------------------------------------------------------------------- #


async def test_a_fresh_project_reads_as_p0_with_nothing_to_approve(
	service: FactoryService, home: Path
) -> None:
	snapshot = await read_snapshot(service)
	assert snapshot.goal is None
	assert snapshot.phase is Phase.ELICIT
	assert snapshot.gate is None
	assert not snapshot.stopped_at_gate
	assert snapshot.ledger_length == 0
	assert snapshot.chain.ok
	assert all(row.status is PhaseStatus.PENDING for row in snapshot.phases)


async def test_the_phase_rows_are_the_whole_pipeline_in_order(service: FactoryService) -> None:
	snapshot = await read_snapshot(service)
	assert tuple(row.phase for row in snapshot.phases) == PHASE_SEQUENCE
	gated = {row.phase for row in snapshot.phases if row.gate is not None}
	assert gated == set(PHASE_GATE), "a gated phase with no gate column would read as ungated"


async def test_a_fresh_project_is_told_to_start_an_interrogation(
	service: FactoryService,
) -> None:
	snapshot = await read_snapshot(service)
	assert snapshot.next_move == "sofact build --resume", (
		"with no goal there is nothing to answer; the driver's own fallback is the honest "
		"instruction and it refuses rather than inventing work"
	)


# --------------------------------------------------------------------------- #
# P0 — the questionnaire
# --------------------------------------------------------------------------- #


async def test_an_open_dimension_is_what_the_screen_asks(service: FactoryService) -> None:
	goal = await service.start("a service that reports uptime")
	snapshot = await read_snapshot(service)
	assert snapshot.goal is not None and snapshot.goal.id == goal.id
	assert snapshot.question is not None
	dimension, question, rationale = snapshot.question
	assert question.strip(), "the modal shows a question and this one is empty"
	assert rationale.strip(), "the rationale is what makes the question answerable"
	assert dimension is snapshot.readiness[0].dimension
	assert snapshot.next_move.startswith("sofact"), "the questionnaire is the next move"


async def test_a_resolved_interrogation_stops_asking(service: FactoryService) -> None:
	goal = await service.start("a service that reports uptime")
	await answer_everything(service, goal.id)
	snapshot = await read_snapshot(service)
	assert snapshot.question is None
	assert snapshot.is_ready
	done, total = snapshot.readiness_progress
	assert done == total


# --------------------------------------------------------------------------- #
# a gate — the machine half and the human half
# --------------------------------------------------------------------------- #


async def test_an_open_gate_is_reported_with_its_checks(service: FactoryService) -> None:
	await _stopped_at_a_gate(service, passed=True)
	snapshot = await read_snapshot(service)
	assert snapshot.stopped_at_gate
	assert snapshot.gate is not None
	assert snapshot.gate.phase is Phase.SPECIFY
	assert snapshot.gate.gate is PHASE_GATE[Phase.SPECIFY]
	assert snapshot.gate.can_approve
	assert snapshot.next_move.startswith(f"{GATE_APPROVE_VERB} P2")
	row = next(r for r in snapshot.phases if r.phase is Phase.SPECIFY)
	assert row.is_stopped, "the row the gate is open on must read as stopped"


async def test_a_failed_gate_names_the_producer_and_never_the_approval(
	service: FactoryService,
) -> None:
	"""ADR-0070's dead end: ``gate --approve`` refuses a failed check, so naming it
	sends the operator to a command that can only refuse them."""
	await _stopped_at_a_gate(service, passed=False)
	snapshot = await read_snapshot(service)
	assert snapshot.gate is not None
	assert snapshot.gate.failed
	assert not snapshot.gate.can_approve
	assert GATE_APPROVE_VERB not in snapshot.next_move.split("(", 1)[0], (
		"the opening instruction must not be the verb that refuses"
	)
	assert _named_verb(snapshot.next_move) == "specify"
	# The parenthetical is what separates the two "present the artefact" branches: a
	# failed gate has already been presented, so its repair ends in an approval, while
	# a gate with no checks has nothing to approve yet. Asserting only the verb let a
	# canary that killed this branch pass — both arms name `specify`.
	assert GATE_APPROVE_VERB in snapshot.next_move, (
		"a failed gate is repaired and then approved; the sentence must say so"
	)


async def test_a_gate_with_no_checks_is_not_approvable(service: FactoryService) -> None:
	"""FR-080: a gate nobody has been shown anything at is not a gate awaiting approval."""
	await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE, checks=())
	snapshot = await read_snapshot(service)
	assert snapshot.gate is not None
	assert snapshot.gate.checks == ()
	assert not snapshot.gate.can_approve
	assert _named_verb(snapshot.next_move) == "specify"
	assert GATE_APPROVE_VERB not in snapshot.next_move, (
		"nothing has been presented, so there is no approval to name — the operator's "
		"move is to produce the artefact, not to approve one that was never shown"
	)


async def test_approving_the_gate_clears_the_stop(service: FactoryService) -> None:
	await _stopped_at_a_gate(service, passed=True)
	await service.approve_gate(Phase.SPECIFY, by="operator")
	snapshot = await read_snapshot(service)
	assert not snapshot.stopped_at_gate
	assert snapshot.gate is None
	assert snapshot.next_move != ""


# --------------------------------------------------------------------------- #
# the next move is a command the product accepts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
	"state",
	["fresh", "asking", "gated_pass", "gated_fail", "approved"],
)
async def test_every_next_move_names_a_registered_verb(service: FactoryService, state: str) -> None:
	"""The one check that catches a sentence which reads right and parses wrong.

	``GATE_APPROVE_VERB``'s own docstring records the defect this guards: the driver and
	the view told operators to type ``sofact gate approve P2``, which the ``gate``
	command does not accept, and every test passed because each compared the string to a
	copy of itself. The comparison here is against the registry the parser is built from.
	"""
	if state == "asking":
		await service.start("a service that reports uptime")
	elif state in ("gated_pass", "gated_fail"):
		await _stopped_at_a_gate(service, passed=state == "gated_pass")
	elif state == "approved":
		await _stopped_at_a_gate(service, passed=True)
		await service.approve_gate(Phase.SPECIFY, by="operator")

	move = (await read_snapshot(service)).next_move
	verb = _named_verb(move)
	assert verb, f"{state}: no verb read off {move!r}"
	if verb == "sofact":
		return  # the bare questionnaire, which is the product's front door
	assert verb in _registered(), f"{state}: {move!r} names {verb!r}, which is not a command"


async def test_the_approval_sentence_names_a_gate_that_exists(
	service: FactoryService,
) -> None:
	await _stopped_at_a_gate(service, passed=True)
	move = (await read_snapshot(service)).next_move
	assert f"{GATE_APPROVE_VERB} P2" in move
	assert Phase.SPECIFY.value in move


# --------------------------------------------------------------------------- #
# the ledger
# --------------------------------------------------------------------------- #


async def test_the_ledger_section_carries_every_entry_oldest_first(
	service: FactoryService,
) -> None:
	await service.start("a service that reports uptime")
	snapshot = await read_snapshot(service)
	assert snapshot.entries, "starting a goal appends an entry"
	assert [e.index for e in snapshot.entries] == sorted(e.index for e in snapshot.entries)
	assert snapshot.ledger_length == len(snapshot.entries)
	assert snapshot.chain.ok


# --------------------------------------------------------------------------- #
# read-only, in the type
# --------------------------------------------------------------------------- #


async def test_a_snapshot_holds_no_callable(service: FactoryService) -> None:
	"""No code path from a snapshot to a mutation, asserted structurally.

	A service handle or a callback on the snapshot would be a reference the app could
	call, and "the app chooses not to" is a promise rather than a property. A frozen
	dataclass of plain values cannot.
	"""
	await _stopped_at_a_gate(service, passed=True)
	snapshot = await read_snapshot(service)
	for name, value in vars(snapshot).items():
		assert not callable(value), f"Snapshot.{name} is callable, so the screen can act through it"


async def test_the_driver_run_is_read_when_one_exists(service: FactoryService) -> None:
	"""The runs tab reads the latest run, and its terminal names the stop.

	Recorded through ``record_driver_run`` rather than by invoking ``run_goal``: a real
	run dispatches harnesses and would make this a test of the driver, which has its own.
	What is asserted here is only that the snapshot surfaces the row.
	"""
	goal = await service.start("a service that reports uptime")
	started = now()
	run = DriverRun(
		id=uuid7str(),
		goal_id=goal.id,
		started_at=started,
		ended_at=started,
		terminal=DriverTerminal.GATE_OPEN,
		terminal_detail="stopped at the specification gate",
		open_gate=Phase.SPECIFY,
		gate_failures=("criteria_are_machine_checkable",),
	)
	await service.record_driver_run(run)

	snapshot = await read_snapshot(service)
	assert snapshot.run is not None
	assert snapshot.run.id == run.id
	assert snapshot.run.next_human_verb is not None
	assert "specify" in snapshot.run.next_human_verb, (
		"a run that stopped on a failed machine half must name the producer verb"
	)
