"""Replay: the log is the only source of derived state.

``fold`` is pure, total over the kinds it knows, and deliberately unforgiving about
the kinds it does not. Those three properties are what make replay meaningful: if
state could be assembled by anything other than the log, the log would not be the
record of what happened, and the hash chain upstream would be guarding a fiction.

The centerpiece drives a real service through the whole pipeline — interrogation,
contract, plan, probe, dispatch, integrity — and folds the log it produced. Every
payload in it is one the product actually wrote, so the test checks the wire shapes
the modules really emit rather than a hand-built approximation of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from synthetic import plan_and_service

from sofact.ledger import Ledger
from sofact.service import FactoryService
from sofact.state import fold
from sofact.views import (
	ElicitationDimension,
	LedgerEntry,
	LedgerKind,
	ProjectState,
)

KIND_TO_FIELD: dict[LedgerKind, str] = {
	LedgerKind.GOAL_CREATED: "goals",
	LedgerKind.ANSWER_RECORDED: "answers",
	LedgerKind.DRAFT_CREATED: "drafts",
	LedgerKind.CONTRACT_CREATED: "contracts",
	LedgerKind.EVIDENCE_RECORDED: "evidence",
	LedgerKind.VERDICT_RENDERED: "reports",
	LedgerKind.CLAIM_DECLARED: "claims",
	LedgerKind.ADVISOR_NOTE: "notes",
	LedgerKind.PLAN_COMPILED: "plans",
	LedgerKind.CAPABILITY_PROBED: "profiles",
	LedgerKind.STEP_DISPATCHED: "dispatches",
	LedgerKind.INTEGRITY_CHECKED: "integrity",
}
"""Which event kind lands in which state field. Transcribed from ``fold``'s arms so
that adding a kind without a field (or a field without a kind) fails a test."""


def census(service: FactoryService) -> dict[LedgerKind, int]:
	"""How many entries of each kind the log holds."""
	counts: dict[LedgerKind, int] = {}
	for entry in service.ledger.entries():
		counts[entry.kind] = counts.get(entry.kind, 0) + 1
	return counts


async def exercised(tmp_path: Path, home: Path) -> FactoryService:
	"""A service that has produced at least one entry of most kinds."""
	service, plan = await plan_and_service(home, tmp_path, "complete")
	await service.dispatch_plan(plan.id)
	await service.check_integrity(plan.id)
	return service


# --------------------------------------------------------------------------- #
# the mapping is total, in both directions
# --------------------------------------------------------------------------- #


def test_every_event_kind_lands_in_a_field_and_every_field_has_a_kind() -> None:
	"""Total in both directions: no kind is silently dropped, no field is unreachable."""
	assert set(KIND_TO_FIELD) == set(LedgerKind)
	assert set(KIND_TO_FIELD.values()) == set(ProjectState.model_fields)


def test_an_empty_log_folds_to_a_state_with_every_field_empty() -> None:
	state = fold(())

	assert len(ProjectState.model_fields) == 12
	for name in ProjectState.model_fields:
		value = getattr(state, name)
		assert value == (), f"{name} should be empty, got {value!r}"
		assert isinstance(value, tuple), f"{name} must be immutable, got {type(value)}"


# --------------------------------------------------------------------------- #
# purity and replay
# --------------------------------------------------------------------------- #


def test_fold_is_pure(home: Path, tmp_path: Path) -> None:
	"""Same entries in, same state out — computed twice, with no I/O in between."""
	ledger = Ledger(tmp_path / "log.jsonl")
	for index in range(3):
		ledger.append(
			LedgerKind.ADVISOR_NOTE,
			{"text": f"note {index}"},
		)
	entries = ledger.entries()

	assert fold(entries) == fold(entries)
	assert fold(entries).notes == ("note 0", "note 1", "note 2")


def test_a_log_read_from_disk_folds_the_same_as_one_in_memory(tmp_path: Path) -> None:
	"""Replay is replay: the cache must not be what makes the fold work."""
	written = Ledger(tmp_path / "log.jsonl")
	written.append(LedgerKind.ADVISOR_NOTE, {"text": "written once"})

	reread = Ledger(tmp_path / "log.jsonl")
	assert fold(reread.entries()) == fold(written.entries())


# --------------------------------------------------------------------------- #
# a real run
# --------------------------------------------------------------------------- #


async def test_a_real_run_folds_into_exactly_the_state_it_committed(
	home: Path, tmp_path: Path
) -> None:
	"""The load-bearing test: real payloads, and a per-kind count that must match."""
	service = await exercised(tmp_path, home)
	state = fold(service.ledger.entries())
	counts = census(service)

	for kind, field in KIND_TO_FIELD.items():
		folded = len(getattr(state, field))
		assert folded == counts.get(kind, 0), (
			f"{kind.value} -> {field}: {folded} != {counts.get(kind, 0)}"
		)

	# Nothing was written that the fold cannot account for.
	assert sum(counts.values()) == sum(
		len(getattr(state, name)) for name in ProjectState.model_fields
	)


async def test_the_folded_objects_equal_the_ones_the_service_committed(
	home: Path, tmp_path: Path
) -> None:
	"""A round trip through the log, not merely a count: the payloads deserialize back
	to equal models, so no field is quietly lost in serialization."""
	service, plan = await plan_and_service(home, tmp_path, "complete")
	await service.dispatch_plan(plan.id)
	state = fold(service.ledger.entries())

	assert state.goals[0] == await service.current_goal()
	assert state.plans[0] == plan
	assert state.plans[0].goal_id == state.goals[0].id
	assert state.contracts[0].id == plan.contract_id
	assert state.drafts[0].goal_id == plan.goal_id
	assert state.profiles[0].name == "synthetic"
	assert state.dispatches[0].step_id == plan.steps[0].id


async def test_order_within_a_field_follows_the_log(home: Path, tmp_path: Path) -> None:
	"""Two orderings that carry meaning: the questions were asked in declaration order,
	and the steps ran in wave order."""
	service, plan = await plan_and_service(home, tmp_path, "complete")
	await service.dispatch_plan(plan.id)
	state = fold(service.ledger.entries())

	assert tuple(status.dimension for status in state.answers) == tuple(ElicitationDimension)
	assert tuple(record.step_id for record in state.dispatches) == tuple(
		step.id for wave in plan.waves() for step in wave
	)


async def test_the_answers_field_holds_only_answers_for_the_goal(
	home: Path, tmp_path: Path
) -> None:
	service = await exercised(tmp_path, home)
	state = fold(service.ledger.entries())
	goal = await service.current_goal()

	assert goal is not None, "the run must have left a current goal"
	assert {answer.goal_id for answer in state.answers} == {goal.id}


# --------------------------------------------------------------------------- #
# what the fold refuses
# --------------------------------------------------------------------------- #


def test_an_unknown_kind_is_refused_rather_than_skipped() -> None:
	"""Stale state that *looks* current is worse than a crash.

	The ledger's own validation normally catches an unreadable kind first; this guard
	is what stops a widened enum from being absorbed as a silent no-op.
	"""
	entry = LedgerEntry.model_construct(index=7, kind="future.kind", payload={})

	with pytest.raises(ValueError) as caught:
		fold((entry,))

	message = str(caught.value)
	assert "unknown kind" in message
	assert "7" in message
	assert "newer SoFact" in message


def test_a_payload_missing_its_key_is_not_coerced(tmp_path: Path) -> None:
	"""An empty payload is not an empty goal. The fold names what it wanted."""
	ledger = Ledger(tmp_path / "log.jsonl")
	ledger.append(LedgerKind.GOAL_CREATED, {})

	with pytest.raises(KeyError):
		fold(ledger.entries())


def test_a_payload_with_an_unusable_value_is_not_coerced(tmp_path: Path) -> None:
	ledger = Ledger(tmp_path / "log.jsonl")
	ledger.append(
		LedgerKind.GOAL_CREATED,
		{"goal": {"id": "not-a-uuid", "statement": "x", "created_at": "not-a-time"}},
	)

	with pytest.raises(ValidationError):
		fold(ledger.entries())


def test_folding_does_not_verify_the_chain_that_is_the_ledgers_job(tmp_path: Path) -> None:
	"""A separation worth pinning: ``fold`` is a replayer, not a guard.

	Tampering is detected by ``require_intact``/``verify_chain``; if the fold were the
	thing that noticed, every caller of a pure function would pay for a hash walk.
	"""
	ledger = Ledger(tmp_path / "log.jsonl")
	ledger.append(LedgerKind.ADVISOR_NOTE, {"text": "Alpha requirement"})
	path = tmp_path / "log.jsonl"
	path.write_text(path.read_text(encoding="utf-8").replace("Alpha", "Beta"), encoding="utf-8")

	tampered = Ledger(path)
	assert fold(tampered.entries()).notes == ("Beta requirement",)
	assert tampered.verify_chain().ok is False
