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
from collections import Counter
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

from sofact.contract import executable_clauses
from sofact.harness import (
	CLAUDE_SPEC,
	DEFAULT_TOOLS,
	DSH_SPEC,
	PI_SPEC,
	SPECS,
	ConfiguredHarnessAdapter,
)
from sofact.service import DEFAULT_HARNESS, FactoryService, resolve_home, resolve_tools
from sofact.views import (
	ElicitationDimension,
	GoalPlan,
	GoalStep,
	GoalStyle,
	HarnessCapability,
	IntegrityOutcome,
	IntegritySubject,
	LedgerKind,
	PlanStepKind,
	ProbeOutcome,
	RepairOutcome,
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
		assert set(service.harness_table()) == {
			PI_SPEC.name,
			DSH_SPEC.name,
			CLAUDE_SPEC.name,
			"pi-research",
		}

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


class TestTheToolSet:
	"""Which tools a producer gets is the operator's decision, not a default in src/.

	The tool set is the whole of what an agent may do, so it is the one knob that most
	deserves a surface. Making it reachable is FR-156's rule applied to a *capability*
	rather than a harness: the value must be settable without a source edit.
	"""

	def test_the_default_is_the_read_write_edit_bash_set(self) -> None:
		assert resolve_tools(None) == DEFAULT_TOOLS
		assert resolve_tools(None) == "read,write,edit,bash"

	def test_an_explicit_set_is_used_verbatim(self) -> None:
		assert resolve_tools("read,grep") == "read,grep"

	def test_the_environment_is_the_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("SOFACT_TOOLS", "read")
		assert resolve_tools(None) == "read"

	def test_an_explicit_set_beats_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("SOFACT_TOOLS", "read")
		assert resolve_tools("read,edit") == "read,edit"

	def test_an_empty_set_is_refused_rather_than_forwarded(self) -> None:
		"""``--tools ""`` is an empty allowlist: a producer with no way to write.

		Forwarding it would produce a run that cannot edit anything and a failure with
		no cause attached, so it is refused where the operator can still see why.
		"""
		with pytest.raises(ValueError, match="the tool set is empty"):
			resolve_tools("")
		with pytest.raises(ValueError, match="the tool set is empty"):
			resolve_tools("   ")

	def test_an_empty_environment_value_is_refused_too(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Unset and set-to-empty are different answers, and the empty one is a mistake."""
		monkeypatch.setenv("SOFACT_TOOLS", "")
		with pytest.raises(ValueError, match="the tool set is empty"):
			resolve_tools(None)

	async def test_the_adapter_carries_it(self, home: Path, tmp_path: Path) -> None:
		registered = synthetic_service(home, tmp_path, "complete")
		assert registered.adapter(None).tools == DEFAULT_TOOLS
		assert registered.adapter(None, tools="read").tools == "read"

	def test_it_reaches_the_argv_slot_the_spec_declares(self, tmp_path: Path) -> None:
		"""Resolution is only real if the value lands where the harness reads it."""
		adapter = ConfiguredHarnessAdapter(
			PI_SPEC,
			workspace=tmp_path,
			session_dir=tmp_path,
			model="some-model",
			tools="read,grep",
		)
		argv = adapter.build_argv(
			"a goal long enough to clear the contamination floor",
			"01920000-0000-7000-8000-000000000001",
		)
		assert "{tools}" not in argv, "the placeholder must be filled, not passed through"
		assert argv[argv.index("--tools") + 1] == "read,grep"


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

	async def test_the_extra_rows_are_measured_rather_than_defaulted(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A skipped attempt and an attempt that found nothing are different facts.

		These four rows need more than one child, and an earlier probe recorded them as
		unmeasured. "Nobody looked" is still not "it is not there" -- an empty profile
		holds that line in ``TestProbe.test_an_unprobed_capability_reads_inconclusive_not_
		absent`` -- but these rows are now looked at, so the reason has to say what was
		attempted rather than that nothing was.
		"""
		registered = synthetic_service(home, tmp_path, "complete")
		profile = await registered.probe_harness(None)
		for capability in (
			HarnessCapability.SANDBOXABLE,
			HarnessCapability.CONCURRENT,
			HarnessCapability.BUDGET_CONTROL,
			HarnessCapability.GOAL_SURVIVES_COMPACTION,
		):
			finding = profile.finding(capability)
			assert finding is not None
			assert "no attempt was made" not in finding.attempted
			assert finding.observed != ""

	async def test_a_quick_probe_skips_the_rows_that_need_a_second_child(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The service forwards the flag, so a caller can trade coverage for time."""
		registered = synthetic_service(home, tmp_path, "complete")
		profile = await registered.probe_harness(None, deep=False)
		assert profile.observation(HarnessCapability.CONCURRENT) is ProbeOutcome.INCONCLUSIVE
		assert profile.observation(HarnessCapability.SANDBOXABLE) is ProbeOutcome.INCONCLUSIVE
		finding = profile.finding(HarnessCapability.SANDBOXABLE)
		assert finding is not None
		assert "not requested" in finding.observed

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


class TestModelResolutionThroughTheService:
	"""The preflight an operator actually meets: a refused model, attributed.

	The probe is what measures it (FR-148: capability is attempted, never read off a help
	page), and the dispatch is what refuses on it. Neither half is useful alone -- a
	measurement nothing acts on is a note, and a refusal with no measurement is a guess.
	"""

	async def test_the_probe_records_the_refusal(self, home: Path, tmp_path: Path) -> None:
		registered = synthetic_service(home, tmp_path, "badmodel-once")
		profile = await registered.probe_harness(None)
		assert profile.model_resolved is ProbeOutcome.ABSENT
		assert profile.model, "the profile names the model it was measured with"
		assert LedgerKind.CAPABILITY_PROBED.value in kinds(registered)

	async def test_the_dispatch_refuses_rather_than_blaming_the_producer(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A refused model and a failed producer were the same observation before this."""
		registered = synthetic_service(home, tmp_path, "badmodel-once")
		profile = await registered.probe_harness(None)
		assert profile.model_resolved is ProbeOutcome.ABSENT
		_, contract_id = await elicitation_to_contract(registered)
		plan = await registered.compile_plan(contract_id)
		record = await registered.dispatch_step(plan.id, plan.steps[0].id)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert record.exit_code is None
		assert record.session_path is None
		assert record.declared_complete is False
		assert "model-resolution failure and not a producer failure" in (record.note or "")
		assert record.note is not None and profile.model in record.note

	async def test_the_refusal_is_in_the_log_not_only_in_the_return_value(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A refusal a later reader cannot find is not auditable."""
		registered = synthetic_service(home, tmp_path, "badmodel-once")
		await registered.probe_harness(None)
		_, contract_id = await elicitation_to_contract(registered)
		plan = await registered.compile_plan(contract_id)
		await registered.dispatch_step(plan.id, plan.steps[0].id)
		state = await registered.state()
		dispatches = state.dispatches_for(plan.id)
		assert len(dispatches) == 1
		assert dispatches[0].note is not None
		assert "model-resolution" in dispatches[0].note

	async def test_the_gate_does_not_fire_when_the_model_was_never_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The instrument must not be a blanket refusal: a good model still dispatches."""
		registered = synthetic_service(home, tmp_path, "complete")
		assert (await registered.probe_harness(None)).model_resolved is ProbeOutcome.CONFIRMED
		_, contract_id = await elicitation_to_contract(registered)
		plan = await registered.compile_plan(contract_id)
		record = await registered.dispatch_step(plan.id, plan.steps[0].id)
		assert record.outcome is StepOutcome.COMPLETED


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

	async def test_a_dispatched_step_records_the_branch_it_ran_on(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-100 is a fact in the log, not a claim in the goal text.

		The branch is established before the session starts and carried on the dispatch
		record, so "build never occurs in place" can be checked after the run rather
		than believed from a prompt. The workspace is a real repository afterwards,
		which is the half a log entry alone would not prove.

		The seal is the other half, and it is asserted here because a branch name alone
		proves nothing: a branch with no commit is not a ref, so the *next* step branches
		from an unborn HEAD and both steps share one uncommitted working tree. This test
		fails against the pre-seal code with ``sealed_commit is None``.
		"""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "writes-work-complete")
		record = await service.dispatch_step(plan_id, step_id)

		assert record.checkout is not None, "a dispatched step must name its branch"
		assert record.checkout.branch.startswith("sofact/")
		assert record.checkout.branch != "main", "building on main is building in place"
		assert (Path(record.workspace) / ".git").is_dir()
		assert record.checkout.sealed_commit is not None, (
			"the step's work was never committed, so the branch is not a boundary"
		)
		assert record.checkout.sealed_paths >= 1, "the producer wrote a file and nothing sealed it"

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

	async def test_a_refuted_step_ends_the_run(self, home: Path, tmp_path: Path) -> None:
		"""FR-142 stops a dependency on an *unverified* step, not merely a failed one.

		Every session here completes: the producers all declare success. What stops the
		run is the verdict — the first wave carrying clauses comes back ``VIOLATED``, so
		the steps after it never start. Without this the plan would happily build its
		repair wave on top of a refuted operation wave.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 1")
		records = await service.dispatch_plan(plan.id)
		dispatched = [plan.step_by_id(record.step_id) for record in records]
		assert all(record.outcome is StepOutcome.COMPLETED for record in records)
		assert len(records) < len(plan.steps), "a refuted wave must stop the build"
		assert any(step is not None and step.clause_ids for step in dispatched)
		assert not any(
			step is not None and step.kind is PlanStepKind.REPAIR for step in dispatched
		), "repair must not run on a refuted dependency"
		report = await service.latest_report(plan.contract_id)
		assert report is not None
		assert report.outcome is VerdictOutcome.VIOLATED

	async def test_an_agreeing_oracle_runs_the_whole_plan(self, home: Path, tmp_path: Path) -> None:
		"""The gate must not stop a build that is actually passing."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		records = await service.dispatch_plan(plan.id)
		assert len(records) == len(plan.steps)
		report = await service.latest_report(plan.contract_id)
		assert report is not None
		assert report.outcome is VerdictOutcome.SATISFIED


# --------------------------------------------------------------------------- #
# the repair loop (FR-101's bound on a loop that otherwise does not exist)
# --------------------------------------------------------------------------- #

REPAIR_ORACLE = "test -f repair-marker.txt"
"""An oracle that is refuted until a repair session writes the marker.

The refutation is real: the command runs, exits non-zero, and the verifier reports
VIOLATED from its own observation. The repair is real too — the marker appears only
because a session whose goal text names it wrote it, and only a repair goal names it.
Nothing here is mocked; the state transition is a file on disk.
"""


class TestTheRepairLoop:
	async def test_a_refuted_clause_is_handed_back_and_the_loop_converges(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The whole point: a refuted build becomes a repaired one, unattended.

		Before this loop existed, ``dispatch_plan`` halted at the first refuted wave and
		the operator dispatched again by hand. Here the refutation is turned into a
		session, the session writes the file the oracle was missing, and the contract
		comes back clean — with every step of that recorded.
		"""
		service, plan = await plan_and_service(
			home, tmp_path, "complete-repair", commands=REPAIR_ORACLE
		)
		first = await service.dispatch_plan(plan.id)
		refuted = await service.latest_report(plan.contract_id)
		assert refuted is not None and refuted.outcome is VerdictOutcome.VIOLATED
		assert len(first) < len(plan.steps), "the plan stopped at the refuted wave"

		attempts = await service.repair_plan(plan.id)

		assert attempts, "a refuted clause must produce at least one repair attempt"
		assert all(a.outcome is RepairOutcome.REPAIRED for a in attempts), [
			a.outcome for a in attempts
		]
		after = await service.latest_report(plan.contract_id)
		assert after is not None
		assert after.outcome is VerdictOutcome.SATISFIED, (
			"the loop exists to make the contract clean, not merely to try"
		)

	async def test_the_repair_goal_carries_the_verifiers_diagnosis(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The producer is handed the refutation, never its own summary of it.

		An exit code and a clause statement are the two facts a repair session needs, and
		both come from the verifier. A goal authored from the producer's account of its
		own failure aims at the failure the producer can describe.
		"""
		service, plan = await plan_and_service(
			home, tmp_path, "complete-repair", commands=REPAIR_ORACLE
		)
		await service.dispatch_plan(plan.id)
		attempts = await service.repair_plan(plan.id)

		assert attempts
		diagnosis = attempts[0].diagnosis
		assert "exit code" in diagnosis, f"the oracle's observation must survive: {diagnosis}"
		assert attempts[0].goal_hash, "a repair goal is pinned like any other"

	async def test_the_repair_goal_forbids_editing_the_oracle(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The constraint that makes a loop safe: the check is out of the producer's reach.

		Without this a repair loop is a producer editing its own completion criteria,
		which is R22 — the reason ``DEFAULT_STEP_ATTEMPTS`` was 1. The constraint is in
		the rendered goal text, and FR-139's hash check is what enforces it.
		"""
		service, plan = await plan_and_service(
			home, tmp_path, "complete-repair", commands=REPAIR_ORACLE
		)
		await service.dispatch_plan(plan.id)
		attempts = await service.repair_plan(plan.id)
		revised = await service.latest_plan(plan.contract_id)

		assert revised is not None
		step = revised.step_by_id(attempts[0].step_id)
		assert step is not None
		text = step.goal.render(revised.goal_style)
		assert "pinned by hash" in text
		assert "Do not weaken, skip, delete or rewrite" in text

	async def test_a_repair_that_does_not_work_is_recorded_as_still_refuted(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A session that completes is not a repair that worked.

		``repair-never`` runs and leaves the tree alone, so the clause is refuted again
		by the next check. Reporting that as REPAIRED would be reading an exit code as a
		verdict, which is the FR-138 defect one level down.
		"""
		service, plan = await plan_and_service(
			home, tmp_path, "complete-repair-never", commands=REPAIR_ORACLE
		)
		await service.dispatch_plan(plan.id)
		attempts = await service.repair_plan(plan.id)

		assert attempts
		assert RepairOutcome.STILL_REFUTED in {a.outcome for a in attempts}
		after = await service.latest_report(plan.contract_id)
		assert after is not None and after.outcome is VerdictOutcome.VIOLATED

	async def test_the_loop_is_bounded_and_says_so_when_it_gives_up(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-101: the bound must be visible, not silent.

		``max_attempts=1`` on a clause that never converges produces one attempt and then
		an EXHAUSTED row. A loop that stopped without saying why would make "out of
		attempts" indistinguishable from "nothing to repair" — the same defect as an
		unrun oracle reading as a satisfied one.
		"""
		service, plan = await plan_and_service(
			home, tmp_path, "complete-repair-never", commands=REPAIR_ORACLE
		)
		await service.dispatch_plan(plan.id)
		attempts = await service.repair_plan(plan.id, max_attempts=1)

		assert attempts, "giving up is still an event"
		assert RepairOutcome.EXHAUSTED in {a.outcome for a in attempts}, [
			a.outcome for a in attempts
		]
		assert any(a.attempt == 1 for a in attempts)

	async def test_a_clean_contract_needs_no_repair(self, home: Path, tmp_path: Path) -> None:
		"""The loop must be a no-op on a contract that already holds."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		await service.dispatch_plan(plan.id)
		assert await service.repair_plan(plan.id) == ()

	async def test_nothing_verified_means_nothing_to_repair(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A repair goal authored from an absent verdict would be an invented refutation."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		assert await service.repair_plan(plan.id) == ()

	async def test_every_attempt_is_in_the_log(self, home: Path, tmp_path: Path) -> None:
		"""The loop's history is derivable from the log, like everything else."""
		service, plan = await plan_and_service(
			home, tmp_path, "complete-repair", commands=REPAIR_ORACLE
		)
		await service.dispatch_plan(plan.id)
		attempts = await service.repair_plan(plan.id)

		state = await service.state()
		assert len(state.repairs_for_plan(plan.id)) >= len(attempts)
		assert LedgerKind.REPAIR_ATTEMPTED.value in kinds(service)

	async def test_a_repair_revision_keeps_the_original_steps(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A revision grows the tail; it never rewrites the plan FR-139 pinned."""
		service, plan = await plan_and_service(
			home, tmp_path, "complete-repair", commands=REPAIR_ORACLE
		)
		await service.dispatch_plan(plan.id)
		await service.repair_plan(plan.id)
		revised = await service.latest_plan(plan.contract_id)

		assert revised is not None
		assert revised.id != plan.id, "a revision is a new plan, not an edited one"
		assert revised.contract_hash == plan.contract_hash
		assert revised.oracle_set_hash == plan.oracle_set_hash
		originals = revised.steps[: len(plan.steps)]
		assert [(s.id, s.ordinal, s.goal_hash) for s in originals] == [
			(s.id, s.ordinal, s.goal_hash) for s in plan.steps
		]
		assert revised.steps[-1].kind is PlanStepKind.REPAIR
		# The repair chains onto everything before it — including earlier repairs, since
		# a second pass at the same clause must run after the first one's session.
		assert revised.steps[-1].depends_on == tuple(s.id for s in revised.steps[:-1])

	async def test_a_repair_step_covers_only_the_refuted_clauses(
		self, home: Path, tmp_path: Path
	) -> None:
		"""One session per owning step, so a repair is the size of what failed."""
		service, plan = await plan_and_service(
			home, tmp_path, "complete-repair", commands=REPAIR_ORACLE
		)
		await service.dispatch_plan(plan.id)
		attempts = await service.repair_plan(plan.id)
		revised = await service.latest_plan(plan.contract_id)

		assert revised is not None
		contract = await service.contract_by_id(plan.contract_id)
		by_id = {clause.id: clause for clause in contract.clauses}
		for attempt in attempts:
			assert attempt.clause_ids, "an attempt that covers nothing repairs nothing"
			assert all(clause_id in by_id for clause_id in attempt.clause_ids)
			step = revised.step_by_id(attempt.step_id)
			assert step is not None
			assert set(step.clause_ids) == set(attempt.clause_ids)


# --------------------------------------------------------------------------- #
# a declaration triggers P6 (FR-138)
# --------------------------------------------------------------------------- #


def first_clause_bearing(plan: GoalPlan) -> GoalStep:
	"""The earliest step that carries clauses.

	A verdict can only corroborate a step that has something to corroborate, so the
	trigger tests aim at one of these rather than at the bootstrap step, whose "success"
	no oracle can confirm.
	"""
	for wave in plan.waves():
		for step in wave:
			if step.clause_ids:
				return step
	raise AssertionError("the plan carries no clause-bearing step")


class TestWhatTriggersVerification:
	async def test_a_declaration_runs_the_oracles_and_renders_a_verdict(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-138's missing half: the claim is a *trigger* to run P6, not a substitute."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		contract = await service.contract_by_id(plan.contract_id)
		executable = executable_clauses(contract)
		assert len(executable) == len(contract.clauses), "every clause got the command"

		record = await service.dispatch_step(plan.id, first_clause_bearing(plan).id)
		assert record.declared_complete
		counts = Counter(kinds(service))
		assert counts["claim.declared"] == 1
		assert counts["evidence.recorded"] == len(executable)
		assert counts["verdict.rendered"] == 1

		report = await service.latest_report(plan.contract_id)
		assert report is not None
		assert report.outcome is VerdictOutcome.SATISFIED
		assert len(report.verdicts) == len(contract.clauses)

	async def test_the_claim_is_written_down_before_the_verdict(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Both signals, separately, in that order — so their disagreement stays legible."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 1")
		await service.dispatch_step(plan.id, first_clause_bearing(plan).id)
		written = service.ledger.entries()
		claim = next(entry.index for entry in written if entry.kind is LedgerKind.CLAIM_DECLARED)
		verdict = next(
			entry.index for entry in written if entry.kind is LedgerKind.VERDICT_RENDERED
		)
		assert claim < verdict

	async def test_a_lying_producer_is_measured_not_believed(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The clause has teeth, so it is corroborated, and the producer is refuted."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 1")
		step = first_clause_bearing(plan)
		record = await service.dispatch_step(plan.id, step.id)
		assert record.outcome is StepOutcome.COMPLETED, "the producer was happy"
		assert record.declared_complete, "and said so"

		report = await service.latest_report(plan.contract_id)
		assert report is not None
		assert report.outcome is VerdictOutcome.VIOLATED
		assert all(verdict.outcome is VerdictOutcome.VIOLATED for verdict in report.verdicts)
		precision = await service.declaration_precision()
		assert precision.declarations == 1
		assert precision.corroborated == 0, "a refuted claim must not be counted as corroborated"
		assert precision.precision == 0.0

	async def test_a_completed_dispatch_is_checked_without_a_declaration(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The trigger is a *completed session*, not a producer's word (FR-163).

		``pi`` has no completion event at all, so a trigger gated on a declaration never
		fires for the default harness: measured live, five real ``pi`` sessions built a
		working module while the run recorded zero evidence rows and still exited 0.
		"""
		service, plan = await plan_and_service(home, tmp_path, "plain", commands="exit 0")
		record = await service.dispatch_step(plan.id, first_clause_bearing(plan).id)
		assert not record.declared_complete, "this harness cannot declare completion at all"
		assert record.outcome is StepOutcome.COMPLETED
		counts = Counter(kinds(service))
		assert counts["claim.declared"] == 0, "nothing was declared, so nothing is claimed"
		assert counts["evidence.recorded"] > 0
		assert counts["verdict.rendered"] == 1
		report = await service.latest_report(plan.contract_id)
		assert report is not None
		assert report.outcome is VerdictOutcome.SATISFIED

	async def test_a_failed_session_is_not_checked(self, home: Path, tmp_path: Path) -> None:
		"""The other half of the rule, unchanged: an incomplete session asserts nothing.

		A verdict there would be about an artefact the producer was still changing, and
		inventing one is the manufactured signal ADR-0015 refuses.
		"""
		service, plan = await plan_and_service(home, tmp_path, "fail", commands="exit 0")
		record = await service.dispatch_step(plan.id, first_clause_bearing(plan).id)
		assert record.outcome is StepOutcome.FAILED
		assert await service.check_dispatch(plan.id, record.id) is None
		counts = Counter(kinds(service))
		assert counts["evidence.recorded"] == 0
		assert counts["verdict.rendered"] == 0

	async def test_an_unknown_dispatch_is_refused(self, home: Path, tmp_path: Path) -> None:
		service, plan = await plan_and_service(home, tmp_path, "complete")
		with pytest.raises(KeyError, match="has no dispatch"):
			await service.check_dispatch(plan.id, "01920000-0000-7000-8000-0000000000ff")

	async def test_precision_now_measures_instead_of_reporting_zero(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Before the trigger existed this instrument had nothing to divide by.

		It still refuses to credit a step that carries no clause: the bootstrap step is
		the gap between the two counts, because "no oracle objects" is not corroboration.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		records = await service.dispatch_plan(plan.id)
		precision = await service.declaration_precision()
		steps = [plan.step_by_id(record.step_id) for record in records]
		assert all(step is not None for step in steps), "every record names a real step"
		bearing = [step for step in steps if step is not None and step.clause_ids]
		assert precision.declarations == len(records)
		assert precision.corroborated == len(bearing)
		assert 0 < precision.corroborated < precision.declarations


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
		"""Every fact SoFact knows must be in the log, or it is not auditable.

		Two trees are excluded, and each for a stated reason rather than to make this
		pass. ``sessions`` is the harness's own session records, which SoFact reads and
		does not author. ``.git`` is git's metadata inside the workspace SoFact created
		(FR-100): it is the repository, not a record of what happened. Everything SoFact
		*writes as its own account of the run* must still be the ledger alone, so a
		second bookkeeping file appearing anywhere is still a failure.
		"""
		service, plan_id, step_id = await dispatched_service(home, tmp_path, "complete")
		await service.dispatch_step(plan_id, step_id)
		await service.check_integrity(plan_id)
		written = {
			path.relative_to(home)
			for path in home.rglob("*")
			if path.is_file() and "sessions" not in path.parts and ".git" not in path.parts
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


# --------------------------------------------------------------------------- #
# the verdict cache (FR-006's second half)
# --------------------------------------------------------------------------- #


class TestTheVerdictCache:
	"""A verdict is keyed by what it was decided from, and reused only then.

	FR-006's ordering half says an older result must not decide a newer state; the
	keyed half says a verdict whose inputs are all still present holds without
	re-running. The tests hold the two apart: reuse happens because the tree and the
	contract are bit-for-bit unchanged, and any change — or any demand for a fresh
	run — re-measures.
	"""

	async def test_an_unchanged_workspace_reuses_the_verdict(
		self, home: Path, tmp_path: Path
	) -> None:
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		record = await service.dispatch_step(plan.id, first_clause_bearing(plan).id)
		first = await service.latest_report(plan.contract_id)
		assert first is not None
		assert first.cache_key != "", "the check keyed its inputs"

		again = await service.check_dispatch(plan.id, record.id)
		assert again is not None
		assert again.verdicts == first.verdicts, "the same inputs decide the same verdict"
		assert again.reused_from == first.at
		assert again.cache_key == first.cache_key
		assert again.at >= first.at, "the reuse is a new row, not a replay of the old one"

		counts = Counter(kinds(service))
		assert counts["verdict.rendered"] == 1
		assert counts["verdict.reused"] == 1
		assert counts["evidence.recorded"] == len(
			executable_clauses(await service.contract_by_id(plan.contract_id))
		), "a reuse runs no oracle, so it records no new evidence"

	async def test_the_reuse_is_in_the_log_as_its_own_row(self, home: Path, tmp_path: Path) -> None:
		"""A reuse that looked like a second measurement would be a fabricated one."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		record = await service.dispatch_step(plan.id, first_clause_bearing(plan).id)
		await service.check_dispatch(plan.id, record.id)

		written = kinds(service)
		assert written.count("verdict.reused") == 1
		assert written.index("verdict.rendered") < written.index("verdict.reused")

		latest = await service.latest_report(plan.contract_id)
		assert latest is not None
		assert latest.reused_from is not None, "the fold treats a reuse as the latest verdict"

	async def test_a_changed_artefact_is_measured_again(self, home: Path, tmp_path: Path) -> None:
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		record = await service.dispatch_step(plan.id, first_clause_bearing(plan).id)
		(service.home / "workspace" / "changed.txt").write_text("a new file", encoding="utf-8")

		again = await service.check_dispatch(plan.id, record.id)
		assert again is not None
		assert again.reused_from is None, "the inputs moved, so the verdict had to be re-decided"

		counts = Counter(kinds(service))
		assert counts["verdict.rendered"] == 2
		assert "verdict.reused" not in counts

	async def test_fresh_remeasures_an_unchanged_workspace(
		self, home: Path, tmp_path: Path
	) -> None:
		"""--fresh exists because the cache is an optimisation, not an obligation."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		record = await service.dispatch_step(plan.id, first_clause_bearing(plan).id)

		again = await service.check_dispatch(plan.id, record.id, reuse=False)
		assert again is not None
		assert again.reused_from is None
		assert again.cache_key != "", "measured fresh, but still keyed for the next reuse"

		counts = Counter(kinds(service))
		assert counts["verdict.rendered"] == 2
		assert counts["evidence.recorded"] == 2 * len(
			executable_clauses(await service.contract_by_id(plan.contract_id))
		)

	async def test_a_refuted_verdict_is_reused_like_a_satisfied_one(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The cache is not a pass cache: a violated verdict is equally reproducible."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 1")
		record = await service.dispatch_step(plan.id, first_clause_bearing(plan).id)
		first = await service.latest_report(plan.contract_id)
		assert first is not None
		assert first.outcome is VerdictOutcome.VIOLATED

		again = await service.check_dispatch(plan.id, record.id)
		assert again is not None
		assert again.outcome is VerdictOutcome.VIOLATED
		assert again.reused_from == first.at

	async def test_dispatch_plan_threads_the_fresh_bypass(self, home: Path, tmp_path: Path) -> None:
		"""Every step's check is fresh, not merely the one the caller named."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		await service.dispatch_plan(plan.id, fresh=True)

		counts = Counter(kinds(service))
		# One verdict per completed step, none reused: every check re-ran the oracles.
		assert counts["verdict.rendered"] == counts["step.dispatched"]
		assert "verdict.reused" not in counts


# --------------------------------------------------------------------------- #
# P1: research is dispatched, not performed (FR-167)
# --------------------------------------------------------------------------- #


class TestTheResearchRun:
	"""SoFact authors the research goal and measures the artefacts; the model researches.

	The protocol the goal imposes is two files in the workspace: ``research-report.md``
	and ``research-meta.json``. What SoFact records is exactly what those hold — sizes,
	the loop's own search count, cited URLs — and nothing it did not measure. A report
	with no sources is the recorded shape of a truncated loop, never of a conclusion.
	"""

	async def _service_with_goal(self, home: Path, tmp_path: Path, mode: str) -> FactoryService:
		spec = dataclasses.replace(
			base_spec(tmp_path, mode, name="pi-research"),
			research_tools=("deep_research",),
		)
		registered = FactoryService(home=home, llm=None, specs={"pi-research": spec})
		await registered.start("a platform that builds software from a conversation")
		return registered

	async def test_a_completed_loop_records_the_report_and_its_sources(
		self, home: Path, tmp_path: Path
	) -> None:
		registered = await self._service_with_goal(home, tmp_path, "research")
		record = await registered.research()

		assert record.outcome is StepOutcome.COMPLETED
		assert record.exit_code == 0
		assert record.report_path is not None
		assert record.report_chars > 0
		assert record.searches_observed == 5, "the loop's own meta carries its count"
		# Two from the report text (the trailing period stripped), one more from the
		# meta's sources array, deduplicated in order of first appearance.
		assert record.source_urls == (
			"https://example.com/one",
			"https://example.com/two",
			"https://example.com/three",
		)
		assert record.tokens_observed == 120, "the session record's usage is read"
		assert any("deep_research" in part for part in record.argv), (
			"the spec's research tools must reach the producer's allowlist, or the loop "
			"cannot be called at all (measured 2026-09-12)"
		)

		assert Counter(kinds(registered))["research.run"] == 1
		state = await registered.state()
		assert state.research[-1] == record, "the fold replays the run"

	async def test_a_truncated_loop_is_a_fact_not_a_failure_to_report(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The measured truncation case: session exit 0, report exists, sources absent."""
		registered = await self._service_with_goal(home, tmp_path, "research-stub")
		record = await registered.research()

		assert record.outcome is StepOutcome.COMPLETED, "the session itself finished"
		assert record.searches_observed == 2
		assert record.source_urls == (), "none recorded, which is not none exist (NFR-024)"
		assert record.report_path is not None
		assert record.report_chars > 0

	async def test_a_failed_session_records_what_did_not_happen(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The session failed, and whatever it left before failing is still recorded."""
		registered = await self._service_with_goal(home, tmp_path, "fail")
		record = await registered.research()

		assert record.outcome is StepOutcome.FAILED
		assert record.exit_code == 7
		assert record.note is not None and "exited 7" in record.note
		# The child wrote its artefact before exiting non-zero; the record reports the
		# artefact and the exit code as separate facts, because they are separate facts.
		assert record.report_path is not None
		assert record.report_chars > 0

	async def test_the_query_defaults_to_the_goal_and_an_explicit_one_wins(
		self, home: Path, tmp_path: Path
	) -> None:
		registered = await self._service_with_goal(home, tmp_path, "research")
		defaulted = await registered.research()
		assert defaulted.query == "a platform that builds software from a conversation"

		named = await registered.research("open-source agent harnesses, 2026")
		assert named.query == "open-source agent harnesses, 2026"

	async def test_a_table_without_a_research_harness_is_named(
		self, home: Path, tmp_path: Path
	) -> None:
		registered = synthetic_service(home, tmp_path, "research", name="synthetic")
		await registered.start("a statement about factories")
		with pytest.raises(KeyError, match="no research harness"):
			await registered.research()

	async def test_research_without_a_goal_is_refused(self, home: Path, tmp_path: Path) -> None:
		registered = synthetic_service(home, tmp_path, "research", name="pi-research")
		with pytest.raises(KeyError, match="no goal yet"):
			await registered.research()
