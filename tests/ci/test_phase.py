"""The phase machine: explicit transitions, and a gate no machine can pass (FR-060/061).

FR-060 asks for transitions that are "explicit ... persisted durably, auditable, and
resumable after SIGKILL". The tests below hold the *explicit* half by driving real
transitions through a real service and reading them back out of a fold — not by
inspecting the enum — and hold the *resumable* half by folding the log a second time
from disk and requiring the phase to come back the same.

FR-061's hard stop is held structurally rather than by a runtime check: the tests
assert that the *constructor* refuses the shapes that would claim a gate was passed,
because a refusal at construction cannot be routed around by a caller that forgets to
check.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sofact.service import FactoryService
from sofact.state import fold
from sofact.views import (
	PHASE_GATE,
	PHASE_SEQUENCE,
	GateCheck,
	LedgerKind,
	Phase,
	PhaseAdvance,
	PhaseStatus,
	now,
)

# --------------------------------------------------------------------------- #
# the vocabulary itself
# --------------------------------------------------------------------------- #


def test_the_sequence_is_the_enum_and_cannot_drift_from_it() -> None:
	"""``PHASE_SEQUENCE`` is ``tuple(Phase)``, so this pins that it stays that way."""
	assert tuple(Phase) == PHASE_SEQUENCE
	assert [p.value for p in PHASE_SEQUENCE] == [
		"P0",
		"P1",
		"P2",
		"P3",
		"P4",
		"P5",
		"P6",
		"P7",
		"P8",
		"P9",
	]


def test_there_are_exactly_four_gates() -> None:
	"""§3.3's argument is for four. A fifth is a decision, not a refactor."""
	assert len(PHASE_GATE) == 4
	assert set(PHASE_GATE) == {Phase.SPECIFY, Phase.DECOMPOSE, Phase.CONTRACT, Phase.DELIVER}


def test_p7_is_a_phase_even_though_the_summary_table_omits_it() -> None:
	"""The diagram and FR-111..116 require P7; §3.2's table is the thing that is wrong."""
	assert Phase.INTEGRATE in PHASE_SEQUENCE
	assert PHASE_SEQUENCE.index(Phase.INTEGRATE) == PHASE_SEQUENCE.index(Phase.VERIFY) + 1
	assert Phase.INTEGRATE not in PHASE_GATE


# --------------------------------------------------------------------------- #
# FR-061 is a type boundary, not a runtime check
# --------------------------------------------------------------------------- #


def test_a_gate_phase_cannot_be_complete_without_an_approver() -> None:
	"""The one shape that would claim a gate was passed by nobody."""
	with pytest.raises(ValidationError, match="cannot be complete without an approval"):
		PhaseAdvance(
			phase=Phase.SPECIFY,
			status=PhaseStatus.COMPLETE,
			at=now(),
			by="factory",
		)


def test_an_ungated_phase_cannot_carry_an_approval() -> None:
	"""An approval on P5 would name a decision the pipeline never asks for."""
	with pytest.raises(ValidationError, match="has no gate, so an approval"):
		PhaseAdvance(
			phase=Phase.BUILD,
			status=PhaseStatus.COMPLETE,
			at=now(),
			by="operator",
			approved_by="operator",
			approved_at=now(),
		)


def test_an_ungated_phase_cannot_await_a_gate() -> None:
	with pytest.raises(ValidationError, match="has no gate to await"):
		PhaseAdvance(phase=Phase.BUILD, status=PhaseStatus.AWAITING_GATE, at=now(), by="factory")


def test_a_half_approval_is_refused() -> None:
	"""Both halves or neither: a name with no time is not an audit trail."""
	with pytest.raises(ValidationError, match="names both who approved it and when"):
		PhaseAdvance(
			phase=Phase.SPECIFY,
			status=PhaseStatus.AWAITING_GATE,
			at=now(),
			by="factory",
			approved_by="operator",
		)


def test_a_gate_phase_may_be_complete_with_an_approver() -> None:
	"""The positive case, so the refusals above are not passing for the wrong reason."""
	advance = PhaseAdvance(
		phase=Phase.SPECIFY,
		status=PhaseStatus.COMPLETE,
		at=now(),
		by="operator",
		approved_by="operator",
		approved_at=now(),
	)
	assert advance.gate is PHASE_GATE[Phase.SPECIFY]
	assert not advance.is_blocking


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


async def walk_to(service: FactoryService, phase: Phase) -> None:
	"""Bring the pipeline to ``phase`` by completing everything before it, gates and all.

	Written as a loop over :data:`PHASE_SEQUENCE` rather than a fixed script so that a
	phase inserted into the pipeline cannot leave these tests asserting against a
	sequence the product no longer has.
	"""
	for earlier in PHASE_SEQUENCE:
		if earlier is phase:
			return
		if earlier in PHASE_GATE:
			await service.advance_phase(earlier, PhaseStatus.AWAITING_GATE)
			await service.approve_gate(earlier, by="operator")
		else:
			await service.advance_phase(earlier, PhaseStatus.COMPLETE)
	raise AssertionError(f"{phase.value} is not in the pipeline")


# --------------------------------------------------------------------------- #
# an empty log
# --------------------------------------------------------------------------- #


async def test_a_fresh_log_is_in_p0_with_nothing_pending_but_p0(
	service: FactoryService,
) -> None:
	state = await service.state()
	assert state.current_phase is Phase.ELICIT
	assert state.open_gate is None
	assert state.phase_status(Phase.ELICIT) is PhaseStatus.PENDING
	assert all(state.phase_status(p) is PhaseStatus.PENDING for p in PHASE_SEQUENCE), (
		"a log with no transitions has every phase pending, including P0"
	)


# --------------------------------------------------------------------------- #
# machine work, end to end
# --------------------------------------------------------------------------- #


async def test_advancing_an_ungated_phase_is_recorded_and_moves_the_current_phase(
	service: FactoryService,
) -> None:
	await service.advance_phase(Phase.ELICIT, PhaseStatus.ACTIVE)
	assert await service.current_phase() is Phase.ELICIT

	await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
	assert await service.current_phase() is Phase.RESEARCH
	assert await service.phase_status(Phase.ELICIT) is PhaseStatus.COMPLETE


async def test_a_gated_phase_stops_the_pipeline_until_a_human_says_otherwise(
	service: FactoryService,
) -> None:
	"""FR-061: the machine half can present a gate; it cannot pass one."""
	await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
	presented = await service.advance_phase(
		Phase.SPECIFY,
		PhaseStatus.AWAITING_GATE,
		checks=(GateCheck(name="criteria_are_machine_checkable", passed=True, detail="6 of 6"),),
	)

	assert presented.is_blocking
	gate = await service.open_gate()
	assert gate is not None
	assert gate.phase is Phase.SPECIFY
	# The current phase does not skip past an open gate.
	assert await service.current_phase() is Phase.SPECIFY

	approved = await service.approve_gate(Phase.SPECIFY, by="operator")
	assert approved.approved_by == "operator"
	assert await service.open_gate() is None
	assert await service.current_phase() is Phase.DECOMPOSE


async def test_advance_cannot_complete_a_gate_phase_and_names_the_verb_that_can(
	service: FactoryService,
) -> None:
	await walk_to(service, Phase.SPECIFY)
	await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE)
	with pytest.raises(ValueError, match="use approve_gate"):
		await service.advance_phase(Phase.SPECIFY, PhaseStatus.COMPLETE)


async def test_machine_work_is_refused_while_a_gate_is_open(
	service: FactoryService,
) -> None:
	"""FR-061's "no machine work downstream of an unapproved gate", as a refusal.

	The refusal is the same one that enforces ordering — an unapproved gate leaves its
	phase incomplete, and an incomplete phase blocks everything after it — which is why
	one check in the service covers both properties.
	"""
	await walk_to(service, Phase.SPECIFY)
	await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE)
	with pytest.raises(ValueError, match="cannot start while P2 is not complete"):
		await service.advance_phase(Phase.DECOMPOSE, PhaseStatus.ACTIVE)


async def test_a_gate_with_a_failed_check_cannot_be_approved(
	service: FactoryService,
) -> None:
	"""Approval cannot make an unsound artefact sound — the DecompositionGate rule."""
	await walk_to(service, Phase.SPECIFY)
	await service.advance_phase(
		Phase.SPECIFY,
		PhaseStatus.AWAITING_GATE,
		checks=(
			GateCheck(
				name="internal_consistency",
				passed=False,
				detail="clause 3 contradicts 7",
			),
		),
	)
	with pytest.raises(ValueError, match="failed machine checks"):
		await service.approve_gate(Phase.SPECIFY, by="operator")


async def test_a_gate_nobody_has_been_shown_cannot_be_approved(
	service: FactoryService,
) -> None:
	"""P3 is gated, but nothing has presented it — so there is nothing to approve."""
	with pytest.raises(ValueError, match="is not awaiting"):
		await service.approve_gate(Phase.DECOMPOSE, by="operator")


async def test_an_ungated_phase_has_no_gate_to_approve(service: FactoryService) -> None:
	with pytest.raises(ValueError, match="has no gate to approve"):
		await service.approve_gate(Phase.BUILD, by="operator")


async def test_a_phase_is_not_re_entered_by_advancing_it_again(
	service: FactoryService,
) -> None:
	await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
	with pytest.raises(ValueError, match="already complete"):
		await service.advance_phase(Phase.ELICIT, PhaseStatus.ACTIVE)


async def test_a_later_phase_cannot_be_worked_before_an_earlier_one(
	service: FactoryService,
) -> None:
	"""Out-of-order transitions would make the resume point ambiguous (NFR-028).

	Reaching P3 first is not the shape to test — that is refused outright by the forward
	check, and is covered above. The out-of-order case is a *re-run*: a phase that is
	already complete cannot be worked again, because the log would then hold two
	answers to "where is the pipeline" with no rule for which wins.
	"""
	await walk_to(service, Phase.DECOMPOSE)
	with pytest.raises(ValueError, match="already complete"):
		await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)


async def test_no_phase_can_be_reached_without_passing_the_gates_before_it(
	service: FactoryService,
) -> None:
	"""FR-061's real teeth: the forward check, not only the out-of-order one.

	Refusing *out-of-order* work alone would still permit P0 then P5 directly, skipping
	both P2 and P3 — which is proceeding past an unapproved gate, and FR-061 says there
	must be no configuration under which that happens.
	"""
	with pytest.raises(ValueError, match="cannot start while P0 is not complete"):
		await service.advance_phase(Phase.BUILD, PhaseStatus.ACTIVE)

	# And it is not merely P0 in the way: a pipeline walked up to P2 and left waiting at
	# the gate still cannot reach P5, because P2 and P3 are not complete.
	await walk_to(service, Phase.SPECIFY)
	await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE)
	with pytest.raises(ValueError, match="cannot start while"):
		await service.advance_phase(Phase.BUILD, PhaseStatus.ACTIVE)


async def test_a_gate_must_be_approved_before_the_next_phase_can_complete(
	service: FactoryService,
) -> None:
	"""The happy path through both gates, so the refusals above are not vacuous."""
	await walk_to(service, Phase.BUILD)
	assert await service.current_phase() is Phase.BUILD
	await service.advance_phase(Phase.BUILD, PhaseStatus.COMPLETE)
	assert await service.current_phase() is Phase.VERIFY


# --------------------------------------------------------------------------- #
# FR-060's "persisted durably ... resumable"
# --------------------------------------------------------------------------- #


async def test_the_phase_survives_a_restart_because_it_is_in_the_log(
	service: FactoryService, home: Path
) -> None:
	"""The load-bearing test for NFR-028: a new process reads the phase off disk.

	A fresh :class:`FactoryService` over the same home shares no memory with the first,
	so the phase it reports can only have come from the ledger.
	"""
	await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE)

	restarted = FactoryService(home)
	assert await restarted.current_phase() is Phase.SPECIFY
	gate = await restarted.open_gate()
	assert gate is not None
	assert gate.phase is Phase.SPECIFY


async def test_a_transition_is_one_ledger_row_and_the_fold_reports_it(
	service: FactoryService,
) -> None:
	before = len(service.ledger)
	await service.advance_phase(Phase.ELICIT, PhaseStatus.ACTIVE, by="factory", note="started")
	assert len(service.ledger) == before + 1

	entries = service.ledger.entries()
	assert entries[-1].kind is LedgerKind.PHASE_ADVANCED
	folded = fold(entries)
	assert len(folded.phases) == 1
	assert folded.phases[0].note == "started"
	assert folded.phases[0].by == "factory"


async def test_an_approval_replaces_the_pending_row_and_keeps_the_checks(
	service: FactoryService,
) -> None:
	"""The approval carries forward what the machine checked, so the audit reads whole."""
	await walk_to(service, Phase.SPECIFY)
	await service.advance_phase(
		Phase.SPECIFY,
		PhaseStatus.AWAITING_GATE,
		checks=(
			GateCheck(
				name="testability",
				passed=True,
				detail="every requirement has a criterion",
			),
		),
	)
	await service.approve_gate(Phase.SPECIFY, by="operator")

	state = await service.state()
	settled = state.phase_advance(Phase.SPECIFY)
	assert settled is not None
	assert settled.status is PhaseStatus.COMPLETE
	assert settled.approved_by == "operator"
	assert [c.name for c in settled.checks] == ["testability"]
	# The pending row stays in the log: the fold reports the settled value, the history
	# keeps both, exactly as a re-answered elicitation dimension does (ADR-0007). Two
	# rows for P2 -- the presentation and the approval -- plus one per earlier phase.
	kinds = [e.kind for e in service.ledger.entries()]
	walked = PHASE_SEQUENCE.index(Phase.SPECIFY)
	assert kinds.count(LedgerKind.PHASE_ADVANCED) == walked + 2
