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

from sofact.ledger import Ledger, LedgerCorruptError
from sofact.service import FactoryService
from sofact.state import fold
from sofact.views import (
	ElicitationDimension,
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
	LedgerKind.VERDICT_REUSED: "reports",
	LedgerKind.CLAIM_DECLARED: "claims",
	LedgerKind.ADVISOR_NOTE: "notes",
	LedgerKind.PLAN_COMPILED: "plans",
	LedgerKind.SPECIFICATION_PROPOSED: "specifications",
	LedgerKind.SPECIFICATION_GATED: "specification_gates",
	LedgerKind.DECOMPOSITION_PROPOSED: "decompositions",
	LedgerKind.DECOMPOSITION_GATED: "gates",
	LedgerKind.CAPABILITY_PROBED: "profiles",
	LedgerKind.STEP_DISPATCHED: "dispatches",
	LedgerKind.RESEARCH_RUN: "research",
	LedgerKind.SOURCE_LEDGER_RECORDED: "ledgers",
	LedgerKind.RESEARCH_CLASSIFIED: "classifications",
	LedgerKind.INTEGRITY_CHECKED: "integrity",
	LedgerKind.INTEGRATION_CHECKED: "integrations",
	LedgerKind.REPAIR_ATTEMPTED: "repairs",
	LedgerKind.PHASE_ADVANCED: "phases",
	LedgerKind.CUT_RECORDED: "cuts",
	LedgerKind.DELIVERY_RENDERED: "deliveries",
	LedgerKind.DEPLOY_RECORDED: "deploys",
	LedgerKind.GATE_COST_RECORDED: "gate_costs",
	LedgerKind.ORACLE_AUDITED: "oracle_audits",
	LedgerKind.ADVERSARIAL_AUDITED: "adversarial_audits",
	LedgerKind.ESCAPE_RECORDED: "escapes",
	LedgerKind.ESCAPE_OVERRIDE_RECORDED: "escape_overrides",
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

	assert len(ProjectState.model_fields) == 30, "a new state field must be folded too"
	for name in ProjectState.model_fields:
		value = getattr(state, name)
		assert value == (), f"{name} should be empty, got {value!r}"
		assert isinstance(value, tuple), f"{name} must be immutable, got {type(value)}"
	assert state.cut is None, "an uncut project reads under no rollback"
	assert state.ledger is None, "a project with no research has no source ledger"
	assert state.classification is None, "a project with no research has no verdict"


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

	field_to_kinds: dict[str, list[LedgerKind]] = {}
	for kind, field in KIND_TO_FIELD.items():
		field_to_kinds.setdefault(field, []).append(kind)
	for field, mapped in field_to_kinds.items():
		folded = len(getattr(state, field))
		expected = sum(counts.get(kind, 0) for kind in mapped)
		assert folded == expected, (
			f"{field}: {folded} != {' + '.join(str(counts.get(k, 0)) for k in mapped)}"
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
# rollback: a reading rule, not a deletion
# --------------------------------------------------------------------------- #


async def test_a_cut_hides_the_entries_after_its_target(home: Path, tmp_path: Path) -> None:
	"""The state is what it was at the target, and the hidden work is still in the log."""
	service, plan = await plan_and_service(home, tmp_path, "complete")
	await service.dispatch_plan(plan.id)
	before = service.ledger.entries()
	target = next(entry.index for entry in before if entry.kind is LedgerKind.PLAN_COMPILED)

	record = await service.cut(target, by="operator", reason="the plan was wrong")
	state = fold(service.ledger.entries())

	assert state.cut == record, "the state must name the rollback it was read under"
	assert state.plans == (plan,), "the plan itself is at the target, so it survives"
	assert state.dispatches == (), "every dispatch happened after the target"
	assert state.goals == fold(before[: target + 1]).goals, "the goal is untouched"
	after = service.ledger.entries()
	assert len(after) == len(before) + 1, "nothing was deleted: the log grew by one row"
	assert after[-1].kind is LedgerKind.CUT_RECORDED
	assert service.ledger.verify_chain().ok is True


async def test_the_project_resumes_after_a_cut(home: Path, tmp_path: Path) -> None:
	"""A cut is not a dead end: what is appended next folds normally."""
	service, plan = await plan_and_service(home, tmp_path, "complete")
	await service.dispatch_plan(plan.id)
	target = next(
		entry.index for entry in service.ledger.entries() if entry.kind is LedgerKind.PLAN_COMPILED
	)
	await service.cut(target, by="operator", reason="re-dispatch from a clean line")

	before_resume = fold(service.ledger.entries())
	assert before_resume.dispatches == ()

	service.ledger.append(LedgerKind.ADVISOR_NOTE, {"text": "noted after the cut"})
	resumed = fold(service.ledger.entries())

	assert resumed.plans == (plan,), "the rollback still applies to the hidden range"
	assert resumed.dispatches == ()
	assert resumed.notes == ("noted after the cut",), "work after the cut folds normally"


async def test_a_later_cut_supersedes_an_earlier_one(home: Path, tmp_path: Path) -> None:
	"""Cutting again to a later entry un-does the first, rather than stacking on it."""
	service = FactoryService(home=home, llm=None)
	for index in range(4):
		service.ledger.append(LedgerKind.ADVISOR_NOTE, {"text": f"note {index}"})
	first = await service.cut(1, by="operator", reason="too far")
	second = await service.cut(3, by="operator", reason="not far enough")

	state = fold(service.ledger.entries())

	assert state.cut == second, "the latest cut is the one the state is read under"
	assert state.cuts == (first, second), "both decisions are still in the log"
	assert state.notes == ("note 0", "note 1", "note 2", "note 3")


def test_a_cut_that_targets_itself_or_the_future_is_refused(tmp_path: Path) -> None:
	"""The invariant the fold asserts, tested where the fold is the thing being tested.

	``FactoryService.cut`` refuses both before it writes, so a log this fold can see
	should never hold such a row — but the log is a file, and the fold is what has to
	hold when someone edits it.
	"""
	ledger = Ledger(tmp_path / "log.jsonl")
	for index in range(3):
		ledger.append(LedgerKind.ADVISOR_NOTE, {"text": f"note {index}"})
	ledger.append(
		LedgerKind.CUT_RECORDED,
		{"cut": {"target_index": 9, "at": "2026-10-12T00:00:00Z", "by": "x", "reason": "y"}},
	)

	with pytest.raises(AssertionError, match="not before it"):
		fold(ledger.entries())


# --------------------------------------------------------------------------- #
# what the fold refuses
# --------------------------------------------------------------------------- #


def test_an_unknown_kind_is_refused_rather_than_skipped(tmp_path: Path) -> None:
	"""Stale state that *looks* current is worse than a crash.

	The refusal happens at the *parse*, not inside :func:`fold`. ``LedgerEntry.kind`` is
	typed ``LedgerKind``, so a line naming a kind this build does not know fails
	validation before the fold is ever reached — which is earlier and louder than a
	guard in the match would be, and is why the fold carries no wildcard arm.

	This test used ``model_construct`` to smuggle a string past that validation, which
	tested the fold's guard by bypassing the layer that makes the guard unreachable.
	The refusal is exercised where a real log would hit it: through
	:meth:`Ledger.entries`, on a line actually written to disk.
	"""
	ledger = Ledger(tmp_path / "log.jsonl")
	ledger.append(LedgerKind.ADVISOR_NOTE, {"text": "a real entry first"})
	forged = (
		'{"index":1,"at":"2026-01-01T00:00:00Z","kind":"future.kind",'
		'"payload":{},"prev_hash":"' + "0" * 64 + '","entry_hash":"x"}'
	)
	with ledger.path.open("a", encoding="utf-8") as handle:
		handle.write(forged + "\n")
	ledger.invalidate()

	with pytest.raises(LedgerCorruptError) as caught:
		ledger.entries()

	message = str(caught.value)
	assert "future.kind" in message, "the refusal must name the kind it did not understand"


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
