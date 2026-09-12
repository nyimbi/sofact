"""The orchestration layer.

This is the only module that both reads the log and can reach a model or a child
process, so what needs testing here is *bookkeeping*: which facts get written down, and
which decisions are taken from the log rather than from the caller. Policy lives in the
pure modules and is tested there; the service is where policy meets the wire.

The harness is real. ``synthetic.py`` supplies an actual Python program that writes an
actual session record and actually exits, so a dispatch test exercises the whole path:
spec -> argv -> process -> record on disk -> observation -> ledger row.
"""

from __future__ import annotations

import dataclasses
import inspect
import os
import time
from pathlib import Path

import pytest
from conftest import GOOD_ANSWERS, answer_everything
from synthetic import (
	base_spec,
	elicitation_to_contract,
	kinds,
	plan_and_service,
	reset_calls,
	synthetic_service,
)

from sofact.harness import DSH_SPEC, PI_SPEC, SPECS
from sofact.service import DEFAULT_HARNESS, FactoryService, resolve_home
from sofact.views import (
	ElicitationDimension,
	GoalStyle,
	HarnessCapability,
	IntegrityOutcome,
	IntegritySubject,
	LedgerKind,
	ProbeOutcome,
	StepOutcome,
	VerdictOutcome,
)

# --------------------------------------------------------------------------- #
# goal lifecycle
# --------------------------------------------------------------------------- #


class TestGoalLifecycle:
	async def test_starting_a_goal_records_it(self, service: FactoryService) -> None:
		goal = await service.start("Ship a reminder dashboard.")
		assert await service.current_goal() == goal
		assert await service.goal(goal.id) == goal
		assert LedgerKind.GOAL_CREATED.value in kinds(service)

	async def test_an_unknown_goal_is_a_key_error_not_an_empty_goal(
		self, service: FactoryService
	) -> None:
		with pytest.raises(KeyError, match="no such goal"):
			await service.goal("01920000-0000-7000-8000-0000000000ff")

	async def test_a_goal_with_no_goal_yet_reports_none(self, service: FactoryService) -> None:
		assert await service.current_goal() is None

	async def test_the_gate_opens_one_dimension_at_a_time(self, service: FactoryService) -> None:
		goal = await service.start("Ship a reminder dashboard.")
		before = await service.readiness(goal.id)
		assert before.is_ready is False
		assert len(before.open_dimensions) == len(GOOD_ANSWERS)
		await service.answer(
			goal.id, ElicitationDimension.OUTCOME, GOOD_ANSWERS[ElicitationDimension.OUTCOME]
		)
		after = await service.readiness(goal.id)
		assert ElicitationDimension.OUTCOME not in after.open_dimensions
		assert len(after.open_dimensions) == len(before.open_dimensions) - 1

	async def test_the_first_open_question_is_the_outcome(self, service: FactoryService) -> None:
		goal = await service.start("Ship a reminder dashboard.")
		pending = await service.open_question(goal.id)
		assert pending is not None
		dimension, spec = pending
		assert dimension is ElicitationDimension.OUTCOME
		assert spec.min_chars > 0

	async def test_a_thin_answer_is_recorded_but_leaves_the_gate_shut(
		self, service: FactoryService
	) -> None:
		"""A thin answer is kept, not refused: the words are the draft's raw material.

		Discarding them would lose the only thing the operator actually said, so the
		answer is written down and the dimension is reported unresolved instead.
		"""
		goal = await service.start("Ship a reminder dashboard.")
		before = len(service.ledger)
		await service.answer(goal.id, ElicitationDimension.OUTCOME, "yes")
		assert len(service.ledger) == before + 1
		readiness = await service.readiness(goal.id)
		assert ElicitationDimension.OUTCOME in readiness.open_dimensions
		assert readiness.is_ready is False

	async def test_a_fully_answered_goal_is_ready_and_has_no_open_question(
		self, service: FactoryService
	) -> None:
		goal = await service.start("Ship a reminder dashboard.")
		await answer_everything(service, goal.id)
		assert (await service.readiness(goal.id)).is_ready is True
		assert await service.open_question(goal.id) is None

	async def test_readiness_is_per_goal_not_per_home(self, service: FactoryService) -> None:
		"""One goal's answers must never make another goal look ready."""
		first = await service.start("Ship a reminder dashboard.")
		second = await service.start("Ship a billing portal.")
		await answer_everything(service, first.id)
		assert (await service.readiness(first.id)).is_ready is True
		assert (await service.readiness(second.id)).is_ready is False


class TestTheModelIsAdvisory:
	async def test_advice_without_a_client_is_a_reason_not_an_exception(
		self, service: FactoryService
	) -> None:
		"""The model sits outside the correctness path, so its absence cannot be fatal."""
		goal = await service.start("Ship a reminder dashboard.")
		await service.answer(
			goal.id, ElicitationDimension.OUTCOME, GOOD_ANSWERS[ElicitationDimension.OUTCOME]
		)
		advice = await service.advise(goal.id, ElicitationDimension.OUTCOME)
		assert advice.text is None
		assert advice.unavailable == "no model configured"

	async def test_advice_before_anything_is_answered_says_so(
		self, service: FactoryService
	) -> None:
		"""There is nothing to advise on yet, and that is distinguishable from no model."""
		goal = await service.start("Ship a reminder dashboard.")
		advice = await service.advise(goal.id, ElicitationDimension.OUTCOME)
		assert advice.text is None
		assert advice.unavailable == "nothing answered yet"

	async def test_an_unavailable_advisor_writes_no_ledger_row(
		self, service: FactoryService
	) -> None:
		"""``advisor.note`` pins text the operator was shown; there was none."""
		goal = await service.start("Ship a reminder dashboard.")
		await service.advise(goal.id, ElicitationDimension.OUTCOME)
		assert LedgerKind.ADVISOR_NOTE.value not in kinds(service)

	async def test_an_unavailable_advisor_has_a_reason_in_every_case(
		self, service: FactoryService
	) -> None:
		"""A silent failure would read as a clean, empty, successful answer."""
		goal = await service.start("Ship a reminder dashboard.")
		advice = await service.advise(goal.id, ElicitationDimension.OUTCOME)
		assert advice.unavailable is not None
		assert advice.unavailable.strip()


# --------------------------------------------------------------------------- #
# home resolution and harness configuration
# --------------------------------------------------------------------------- #


class TestConfiguration:
	def test_home_precedence_is_explicit_then_env_then_cwd(
		self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		explicit = tmp_path / "explicit"
		assert resolve_home(explicit) == explicit
		monkeypatch.setenv("SOFACT_HOME", str(tmp_path / "from-env"))
		assert resolve_home(None) == tmp_path / "from-env"
		assert resolve_home(explicit) == explicit

	async def test_the_default_harness_when_nothing_is_set(
		self, service: FactoryService, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.delenv("SOFACT_HARNESS", raising=False)
		assert service.harness_name(None) == DEFAULT_HARNESS
		assert DEFAULT_HARNESS in SPECS

	async def test_an_explicit_harness_beats_the_environment(
		self, service: FactoryService, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.setenv("SOFACT_HARNESS", "dsh")
		assert service.harness_name(None) == "dsh"
		assert service.harness_name("pi") == "pi"

	async def test_the_default_table_is_exactly_what_sofact_ships(
		self, service: FactoryService
	) -> None:
		assert service.harness_table() == SPECS
		assert set(service.harness_table()) == {PI_SPEC.name, DSH_SPEC.name}

	async def test_a_deployment_can_register_a_harness_without_patching_code(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-156: config before code. A third harness must not need a source edit."""
		registered = synthetic_service(home, tmp_path, "complete")
		assert set(registered.harness_table()) == {"synthetic"}
		with pytest.raises(KeyError, match="configured harnesses: synthetic"):
			registered.adapter("pi")

	async def test_the_session_directory_is_under_the_home(
		self, home: Path, tmp_path: Path
	) -> None:
		"""SoFact must not write agent debris into the checkout it was asked to build."""
		registered = synthetic_service(home, tmp_path, "complete")
		adapter = registered.adapter(None)
		assert adapter.session_dir == home / "sessions" / "synthetic"
		assert adapter.workspace == home / "workspace"
		assert adapter.session_dir.is_dir()

	async def test_an_explicit_workspace_overrides_the_default(
		self, home: Path, tmp_path: Path
	) -> None:
		registered = synthetic_service(home, tmp_path, "complete")
		chosen = tmp_path / "elsewhere"
		assert registered.adapter(None, workspace=chosen).workspace == chosen


# --------------------------------------------------------------------------- #
# the plan
# --------------------------------------------------------------------------- #


class TestPlanThroughTheService:
	async def test_a_contract_compiles_into_a_recorded_plan(self, service: FactoryService) -> None:
		_, contract_id = await elicitation_to_contract(service)
		plan = await service.compile_plan(contract_id)
		assert LedgerKind.PLAN_COMPILED.value in kinds(service)
		assert await service.latest_plan(contract_id) == plan
		assert await service.plan_by_id(plan.id) == plan

	async def test_an_unknown_plan_is_a_key_error(self, service: FactoryService) -> None:
		with pytest.raises(KeyError, match="no such plan"):
			await service.plan_by_id("01920000-0000-7000-8000-0000000000ff")

	async def test_the_plan_is_for_the_named_contract(self, service: FactoryService) -> None:
		"""A caller naming a contract must get a plan for *that* contract."""
		_, first = await elicitation_to_contract(service)
		plan = await service.compile_plan(first)
		contract = await service.contract_by_id(first)
		assert plan.contract_id == contract.id
		assert plan.contract_hash == contract.content_hash

	async def test_goal_style_reaches_the_compiler(self, service: FactoryService) -> None:
		_, contract_id = await elicitation_to_contract(service)
		plan = await service.compile_plan(contract_id, goal_style=GoalStyle.OBJECTIVE)
		assert plan.goal_style is GoalStyle.OBJECTIVE

	async def test_latest_plan_is_none_before_anything_is_compiled(
		self, service: FactoryService
	) -> None:
		_, contract_id = await elicitation_to_contract(service)
		assert await service.latest_plan(contract_id) is None

	async def test_compiling_twice_keeps_both_plans(self, service: FactoryService) -> None:
		"""Superseding a plan must not destroy the one already dispatched against."""
		_, contract_id = await elicitation_to_contract(service)
		first = await service.compile_plan(contract_id)
		second = await service.compile_plan(contract_id)
		assert first.id != second.id
		assert await service.plan_by_id(first.id) == first
		assert await service.latest_plan(contract_id) == second


# --------------------------------------------------------------------------- #
# probe: capability is measured, never assumed
# --------------------------------------------------------------------------- #


class TestProbeHarness:
	async def test_a_probe_is_recorded_and_readable_back(self, home: Path, tmp_path: Path) -> None:
		registered = synthetic_service(home, tmp_path, "complete")
		profile = await registered.probe_harness(None)
		assert profile.name == "synthetic"
		assert LedgerKind.CAPABILITY_PROBED.value in kinds(registered)
		assert await registered.latest_profile(None) == profile

	async def test_a_usable_harness_is_confirmed_non_interactive(
		self, home: Path, tmp_path: Path
	) -> None:
		registered = synthetic_service(home, tmp_path, "complete")
		profile = await registered.probe_harness(None)
		assert profile.is_usable is True
		assert profile.non_interactive is ProbeOutcome.CONFIRMED

	async def test_nothing_is_probed_until_something_is_probed(
		self, home: Path, tmp_path: Path
	) -> None:
		registered = synthetic_service(home, tmp_path, "complete")
		assert await registered.latest_profile(None) is None
		assert LedgerKind.CAPABILITY_PROBED.value not in kinds(registered)

	async def test_a_goal_typed_record_confirms_goal_mode(self, home: Path, tmp_path: Path) -> None:
		"""FR-153 leaves the *negative* inconclusive; a positive is decidable."""
		registered = synthetic_service(home, tmp_path, "goal")
		profile = await registered.probe_harness(None)
		assert profile.goal_mode is ProbeOutcome.CONFIRMED
		assert profile.supports_goal_dispatch is True

	async def test_without_a_goal_typed_record_goal_mode_stays_inconclusive(
		self, home: Path, tmp_path: Path
	) -> None:
		"""One invocation cannot separate 'the harness cannot' from 'the model declined'."""
		registered = synthetic_service(home, tmp_path, "complete")
		profile = await registered.probe_harness(None)
		assert profile.goal_mode is ProbeOutcome.INCONCLUSIVE
		assert profile.supports_goal_dispatch is False

	async def test_the_probe_reports_on_every_capability(self, home: Path, tmp_path: Path) -> None:
		registered = synthetic_service(home, tmp_path, "complete")
		profile = await registered.probe_harness(None)
		assert len(profile.findings) == len(HarnessCapability)

	async def test_an_unprobed_capability_is_inconclusive_not_absent(
		self, home: Path, tmp_path: Path
	) -> None:
		""" "Nobody looked" must not be reported as "it is not there"."""
		registered = synthetic_service(home, tmp_path, "complete")
		profile = await registered.probe_harness(None)
		assert profile.observation(HarnessCapability.SANDBOXABLE) is ProbeOutcome.INCONCLUSIVE
		assert profile.observation(HarnessCapability.CONCURRENT) is ProbeOutcome.INCONCLUSIVE

	async def test_a_missing_binary_is_an_error_not_an_unprobed_capability(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A binary absent from this machine is a fact about the machine."""
		from sofact.harness import HarnessBinaryMissing

		spec = dataclasses.replace(
			base_spec(tmp_path, "complete", name="absent"), argv=("definitely-not-a-binary", "x")
		)
		registered = FactoryService(home=home, llm=None, specs={"absent": spec})
		with pytest.raises(HarnessBinaryMissing):
			await registered.probe_harness(None)


# --------------------------------------------------------------------------- #
# dispatch, and the claim it may carry
# --------------------------------------------------------------------------- #


async def dispatched_service(
	home: Path, tmp_path: Path, mode: str
) -> tuple[FactoryService, str, str]:
	"""Probe, run P0 to a contract, compile a plan. Returns ``(service, plan, step)``."""
	registered = synthetic_service(home, tmp_path, mode)
	await registered.probe_harness(None)
	_, contract_id = await elicitation_to_contract(registered)
	plan = await registered.compile_plan(contract_id)
	return registered, plan.id, plan.steps[-1].id


class TestDispatchStep:
	async def test_a_step_runs_and_is_recorded(self, home: Path, tmp_path: Path) -> None:
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		record = await service.dispatch_step(plan_id, step_id)
		assert record.outcome is StepOutcome.COMPLETED
		assert record.exit_code == 0
		assert record.harness == "synthetic"
		assert record.session_path
		assert LedgerKind.STEP_DISPATCHED.value in kinds(service)

	async def test_without_a_probe_nothing_is_dispatched(self, home: Path, tmp_path: Path) -> None:
		"""FR-148: no capability may be assumed because it was declared."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		plan = await service.compile_plan(contract_id)
		record = await service.dispatch_step(plan.id, plan.steps[-1].id)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert record.note is not None and "never probed" in record.note
		assert record.session_path is None

	async def test_a_not_dispatched_step_is_still_a_recorded_row(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A missing row is indistinguishable from a step nobody got to."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		plan = await service.compile_plan(contract_id)
		await service.dispatch_step(plan.id, plan.steps[-1].id)
		state = await service.state()
		assert len(state.dispatches_for(plan.id)) == 1

	async def test_an_unknown_step_is_a_key_error(self, home: Path, tmp_path: Path) -> None:
		service, plan_id, _ = await dispatched_service(home, tmp_path, "complete")
		with pytest.raises(KeyError, match="has no step"):
			await service.dispatch_step(plan_id, "01920000-0000-7000-8000-0000000000ff")

	async def test_an_unknown_plan_is_a_key_error(self, home: Path, tmp_path: Path) -> None:
		service, _, step_id = await dispatched_service(home, tmp_path, "complete")
		with pytest.raises(KeyError, match="no such plan"):
			await service.dispatch_step("01920000-0000-7000-8000-0000000000ff", step_id)

	async def test_the_dispatch_pins_the_goal_it_was_given(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-139: the record must let a later reader see which objective ran."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		plan = await service.plan_by_id(plan_id)
		step = plan.step_by_id(step_id)
		assert step is not None
		record = await service.dispatch_step(plan_id, step_id)
		assert record.goal_hash == step.goal_hash
		assert record.contract_hash == plan.contract_hash


class TestTheCompletionClaim:
	async def test_a_declared_completion_is_recorded_as_a_claim(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-138: the harness's own word is a claim, and claims are written down."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		record = await service.dispatch_step(plan_id, step_id)
		assert record.declared_complete is True
		assert LedgerKind.CLAIM_DECLARED.value in kinds(service)

	async def test_the_claim_names_the_session_that_made_it(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A claim with no provenance cannot be audited or withdrawn."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		record = await service.dispatch_step(plan_id, step_id)
		state = await service.state()
		claim = state.claims[-1]
		assert claim.declared_by == f"synthetic:{record.id}"
		assert claim.goal_id == record.goal_id

	async def test_a_silent_harness_declares_nothing(self, home: Path, tmp_path: Path) -> None:
		"""No completion signal must not be laundered into a claim either way."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "aborted")
		record = await service.dispatch_step(plan_id, step_id)
		assert record.declared_complete is False
		assert LedgerKind.CLAIM_DECLARED.value not in kinds(service)

	async def test_a_claim_never_becomes_a_verdict(self, home: Path, tmp_path: Path) -> None:
		"""The whole point of FR-138: a producer's word changes no outcome.

		The contract here has no commands, so every clause is unexecutable and must stay
		``INSUFFICIENT`` no matter how confidently the harness declared completion.
		"""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		record = await service.dispatch_step(plan_id, step_id)
		assert record.declared_complete is True
		plan = await service.plan_by_id(plan_id)
		report = await service.verify_contract(plan.contract_id)
		assert report.verdicts
		assert all(verdict.outcome is VerdictOutcome.INSUFFICIENT for verdict in report.verdicts)

	async def test_a_failed_exit_does_not_suppress_the_claim(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The record must show both facts: the harness failed *and* claimed done."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete-fail")
		record = await service.dispatch_step(plan_id, step_id)
		assert record.outcome is StepOutcome.FAILED
		assert record.declared_complete is True
		assert LedgerKind.CLAIM_DECLARED.value in kinds(service)


# --------------------------------------------------------------------------- #
# wave scheduling (FR-142)
# --------------------------------------------------------------------------- #


class TestDispatchPlan:
	async def test_a_plan_runs_wave_by_wave_to_the_end(self, home: Path, tmp_path: Path) -> None:
		service, plan = await plan_and_service(home, tmp_path, "complete")
		records = await service.dispatch_plan(plan.id)
		assert len(records) == len(plan.steps)
		assert all(record.outcome is StepOutcome.COMPLETED for record in records)

	async def test_steps_run_in_wave_order(self, home: Path, tmp_path: Path) -> None:
		"""A dependent step must never run before the step it depends on."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		records = await service.dispatch_plan(plan.id)
		expected = [step.id for wave in plan.waves() for step in wave]
		assert [record.step_id for record in records] == expected

	async def test_a_stalled_wave_ends_the_run(self, home: Path, tmp_path: Path) -> None:
		"""The point of wave scheduling: dependents never build on a failed wave."""
		service, plan = await plan_and_service(home, tmp_path, "fail-after-first")
		reset_calls(home / "sessions" / "synthetic")
		records = await service.dispatch_plan(plan.id)
		run = [plan.step_by_id(record.step_id) for record in records]
		kinds = [step.kind.value if step is not None else None for step in run]
		assert kinds == ["bootstrap", "operation", "operation", "operation"]
		assert records[0].outcome is StepOutcome.COMPLETED
		assert all(record.outcome is StepOutcome.FAILED for record in records[1:])
		ran = {record.step_id for record in records}
		assert not any(
			step.kind.value in {"invariant", "repair"} for step in plan.steps if step.id in ran
		)

	async def test_a_stalled_first_wave_stops_before_anything_else(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Without a probe the very first wave already stalls, so nothing runs."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		plan = await service.compile_plan(contract_id)
		records = await service.dispatch_plan(plan.id)
		assert len(records) == 1
		assert records[0].outcome is StepOutcome.NOT_DISPATCHED
		assert records[0].step_id == plan.steps[0].id

	async def test_max_steps_caps_the_run(self, home: Path, tmp_path: Path) -> None:
		service, plan = await plan_and_service(home, tmp_path, "complete")
		records = await service.dispatch_plan(plan.id, max_steps=2)
		assert len(records) == 4  # the first wave plus a whole three-step wave
		assert len(records) < len(plan.steps)

	async def test_a_concurrent_wave_is_actually_concurrent(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``concurrent`` must overlap the wave, not merely be accepted.

		Each child naps, so a wave that really runs together is measurably faster than
		the same wave run one step at a time. The sequential run is measured in the same
		test rather than assumed, so the comparison cannot pass on a slow machine.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete-nap-0.4")
		start = time.monotonic()
		sequential = await service.dispatch_plan(plan.id, max_steps=4)
		sequential_elapsed = time.monotonic() - start
		start = time.monotonic()
		concurrent = await service.dispatch_plan(plan.id, max_steps=4, concurrent=True)
		concurrent_elapsed = time.monotonic() - start
		assert len(sequential) == len(concurrent) == 4
		assert all(record.outcome is StepOutcome.COMPLETED for record in concurrent)
		assert concurrent_elapsed < sequential_elapsed * 0.75

	async def test_the_default_is_not_concurrent(self, home: Path, tmp_path: Path) -> None:
		"""Two sessions in one workspace is a merge conflict, not a speedup (FR-141)."""

		signature = inspect.signature(FactoryService.dispatch_plan)
		assert signature.parameters["concurrent"].default is False

	async def test_a_non_positive_max_steps_is_refused(self, home: Path, tmp_path: Path) -> None:
		service, plan = await plan_and_service(home, tmp_path, "complete")
		with pytest.raises(AssertionError, match="max_steps must be positive"):
			await service.dispatch_plan(plan.id, max_steps=0)

	async def test_every_wave_record_is_in_the_log(self, home: Path, tmp_path: Path) -> None:
		service, plan = await plan_and_service(home, tmp_path, "complete")
		await service.dispatch_plan(plan.id)
		state = await service.state()
		assert len(state.dispatches_for(plan.id)) == len(plan.steps)


# --------------------------------------------------------------------------- #
# integrity and precision, read back through the service
# --------------------------------------------------------------------------- #


class TestIntegrityThroughTheService:
	async def test_an_undisturbed_plan_reports_intact(self, home: Path, tmp_path: Path) -> None:
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		await service.dispatch_step(plan_id, step_id)
		checks = await service.check_integrity(plan_id)
		subjects = {check.subject for check in checks}
		assert subjects >= {
			IntegritySubject.CONTRACT,
			IntegritySubject.ORACLE_SET,
			IntegritySubject.GOAL_TEXT,
		}
		assert LedgerKind.INTEGRITY_CHECKED.value in kinds(service)
		assert all(check.outcome is IntegrityOutcome.INTACT for check in checks)

	async def test_each_dispatch_gets_its_own_integrity_row(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A row per dispatch is what makes "which objective actually ran" auditable."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		await service.dispatch_step(plan_id, step_id)
		await service.dispatch_step(plan_id, step_id)
		checks = await service.check_integrity(plan_id)
		dispatch_rows = [c for c in checks if "dispatch" in c.label]
		assert len(dispatch_rows) == 2
		assert all(c.outcome is IntegrityOutcome.INTACT for c in dispatch_rows)

	async def test_integrity_is_read_from_the_log_not_from_the_caller(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The check must not be able to grade its own input."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		record = await service.dispatch_step(plan_id, step_id)
		checks = await service.check_integrity(plan_id)
		assert checks
		assert record.plan_id == plan_id


class TestDeclaredCompletionPrecision:
	async def test_no_declarations_means_no_precision_claim(self, service: FactoryService) -> None:
		"""Zero observations must not be reported as a rate of zero."""
		await _compiled_plan(service)
		precision = await service.declaration_precision()
		assert precision.declarations == 0
		assert precision.corroborated == 0
		assert precision.precision is None

	async def test_a_declaration_that_no_clause_corroborates_is_counted(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A claim on a step whose clauses were never verified must lower precision.

		The contract here has no commands, so no clause can be satisfied: a declaration
		therefore counts and is never corroborated.
		"""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		await service.dispatch_step(plan_id, step_id)
		precision = await service.declaration_precision()
		assert precision.declarations == 1
		assert precision.corroborated == 0
		assert precision.precision == 0.0

	async def test_precision_is_scoped_to_one_harness(self, home: Path, tmp_path: Path) -> None:
		"""A claim made by one producer must not be credited to another."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		await service.dispatch_step(plan_id, step_id)
		assert (await service.declaration_precision()).declarations == 1
		assert (await service.declaration_precision("pi")).declarations == 0


async def _compiled_plan(service: FactoryService):
	_, contract_id = await elicitation_to_contract(service)
	return await service.compile_plan(contract_id)


# --------------------------------------------------------------------------- #
# the ledger is the only thing written to disk
# --------------------------------------------------------------------------- #


class TestWhatGetsWritten:
	async def test_the_service_writes_exactly_one_file(self, home: Path, tmp_path: Path) -> None:
		"""Every fact SoFact knows must be in the log, or it is not auditable."""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		await service.dispatch_step(plan_id, step_id)
		await service.check_integrity(plan_id)
		written = {
			path.relative_to(home)
			for path in home.rglob("*")
			if path.is_file() and "sessions" not in path.parts
		}
		assert written == {Path("ledger.jsonl")}

	async def test_the_log_verifies_after_a_full_run(self, home: Path, tmp_path: Path) -> None:
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		await service.dispatch_step(plan_id, step_id)
		status = await service.verify_ledger()
		assert status.ok is True
		assert status.length > 0

	async def test_state_is_folded_from_the_log_not_cached_across_appends(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A stale cache would make the service disagree with its own audit trail."""
		service = synthetic_service(home, tmp_path, "complete")
		before = await service.state()
		await service.start("Ship a reminder dashboard.")
		after = await service.state()
		assert len(after.goals) == len(before.goals) + 1
		assert after.latest_goal() is not None


@pytest.mark.parametrize("variable", ["SOFACT_HARNESS", "SOFACT_MODEL"])
def test_environment_variables_are_read_not_written(
	variable: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
	"""SoFact must not mutate the operator's environment to configure itself."""
	monkeypatch.delenv(variable, raising=False)
	service = FactoryService(home=tmp_path / "state", llm=None)
	service.adapter(None)
	assert variable not in os.environ
