"""The FR-058 adapter, driven against real subprocesses.

No mocks. The harness here is a real Python program that really runs, really writes a
session record, and really exits (or is really killed). The only synthetic thing is the
*wire format*, and that is deliberate: a spec is a declarative claim about a wire format,
so the mapping from bytes on disk back to observations is exactly what needs testing.

The real `pi` and `dsh` are pinned by shape assertions on :data:`PI_SPEC` and
:data:`DSH_SPEC` instead of being run, because running them would make this suite depend
on a cloud model's uptime. What those assertions encode is what [S19] and [S21] measured.
"""

from __future__ import annotations

import dataclasses
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from synthetic import base_spec

from sofact.harness import (
	DSH_SPEC,
	PI_SPEC,
	SPECS,
	ConfiguredHarnessAdapter,
	HarnessBinaryMissing,
	HarnessSessionUnreadable,
	HarnessSpec,
	parse_completion,
	parse_continuations,
	parse_goal_entry,
	parse_usage,
	spec_for,
)
from sofact.planner import compile_plan
from sofact.views import (
	Contract,
	GoalEntry,
	GoalPlan,
	GoalStep,
	HarnessCapability,
	HarnessProfile,
	OracleClass,
	OracleDeclaration,
	ProbeOutcome,
	StepOutcome,
	now,
)

# --------------------------------------------------------------------------- #
# a real, tiny harness
# --------------------------------------------------------------------------- #


def make_adapter(
	tmp_path: Path,
	spec: HarnessSpec,
	*,
	probe_timeout: float = 10.0,
) -> ConfiguredHarnessAdapter:
	"""Bind a spec to a real workspace and session directory under ``tmp_path``."""
	workspace = tmp_path / "workspace"
	workspace.mkdir(parents=True, exist_ok=True)
	return ConfiguredHarnessAdapter(
		spec,
		workspace=workspace,
		session_dir=tmp_path,
		model="synthetic-model",
		probe_timeout=probe_timeout,
	)


def adapter_for(
	tmp_path: Path,
	mode: str,
	*,
	name: str = "synthetic",
	zstd: bool = False,
	zstd_ext: str = "zstd",
	probe_timeout: float = 10.0,
) -> ConfiguredHarnessAdapter:
	"""The common case: the script above, in a given mode."""
	spec = base_spec(tmp_path, mode, name=name, zstd=zstd, zstd_ext=zstd_ext)
	return make_adapter(tmp_path, spec, probe_timeout=probe_timeout)


def _records(*rows: dict[str, object]) -> tuple[dict[str, object], ...]:
	return tuple(rows)


# --------------------------------------------------------------------------- #
# spec shape: what was measured, pinned so it cannot drift silently
# --------------------------------------------------------------------------- #


class TestMeasuredSpecs:
	def test_both_harnesses_have_a_spec(self) -> None:
		assert set(SPECS) == {"pi", "dsh"}
		assert spec_for("pi") is PI_SPEC
		assert spec_for("dsh") is DSH_SPEC

	def test_unknown_harness_names_the_configured_set(self) -> None:
		with pytest.raises(KeyError, match="configured harnesses: dsh, pi"):
			spec_for("omp")

	def test_pi_argv_matches_the_S19_measurement(self) -> None:
		assert PI_SPEC.argv[:2] == ("pi", "--mode")
		assert "--offline" in PI_SPEC.argv
		assert "--no-context-files" in PI_SPEC.argv
		assert PI_SPEC.session_is_zstd is False
		assert PI_SPEC.usage_path == ()

	def test_pi_has_no_completion_signal_so_precision_stays_unmeasured(self) -> None:
		"""The asymmetry with dsh is a measured fact, not an oversight."""
		assert PI_SPEC.completion_event is None
		assert DSH_SPEC.completion_event == "turn/end"

	def test_dsh_requires_explicit_home_and_writes_zstd(self) -> None:
		assert DSH_SPEC.env == (("DSH_HOME", "{session_dir}"),)
		assert DSH_SPEC.session_is_zstd is True
		assert DSH_SPEC.completion_reason_path == ("reason", "kind")
		assert DSH_SPEC.completion_reason_value == "completed"

	def test_dsh_notes_record_the_headless_blocker_and_the_egress(self) -> None:
		"""An UNVERIFIED argv and an unmitigated egress route must stay visible."""
		low = DSH_SPEC.notes.lower()
		assert "unverified" in low
		assert "telemetry" in low

	def test_dsh_cannot_disable_context_files_but_pi_can(self) -> None:
		assert PI_SPEC.supports_context_file_flag is True
		assert DSH_SPEC.supports_context_file_flag is False

	def test_a_spec_naming_no_argv_is_refused(self) -> None:
		with pytest.raises(ValueError, match="declares no argv"):
			HarnessSpec(name="empty", argv=())

	def test_a_completion_event_without_a_path_to_read_it_is_refused(self) -> None:
		with pytest.raises(AssertionError, match="no path to read from it"):
			HarnessSpec(name="x", argv=("true",), completion_event="turn/end")

	def test_an_unknown_usage_reducer_is_refused(self) -> None:
		with pytest.raises(AssertionError, match="bad usage_reduce"):
			HarnessSpec(name="x", argv=("true",), usage_reduce="mean")

	def test_the_spec_env_is_slot_substituted(self) -> None:
		spec = HarnessSpec(name="x", argv=("true",), env=(("HOME_{session_id}", "{session_dir}"),))
		assert spec.formatted_env({"session_id": "s1", "session_dir": "/tmp/s"}) == {
			"HOME_s1": "/tmp/s"
		}


# --------------------------------------------------------------------------- #
# argv construction
# --------------------------------------------------------------------------- #


class TestBuildArgv:
	def test_goal_is_appended_raw_and_last(self, tmp_path: Path) -> None:
		adapter = adapter_for(tmp_path, "complete")
		goal = "Do the thing {with} braces and a {nested: format} spec"
		argv = adapter.build_argv(goal, "s1")
		assert argv[-1] == goal
		assert "{with}" in argv[-1]

	def test_slots_are_substituted_in_the_template(self, tmp_path: Path) -> None:
		adapter = adapter_for(tmp_path, "complete")
		argv = adapter.build_argv("g", "session-42")
		assert str(adapter.session_dir) in argv
		assert "session-42" in argv
		assert "{session_id}" not in " ".join(argv)

	def test_a_goal_baked_into_the_template_is_refused_not_formatted(self, tmp_path: Path) -> None:
		"""A hard-coded objective in the template is the failure this guard catches."""
		goal = "prove the duplicate-delivery clause by replaying the outbox"
		spec = dataclasses.replace(base_spec(tmp_path, "complete"), argv=("echo", goal))
		with pytest.raises(AssertionError, match="formatted argv template"):
			make_adapter(tmp_path, spec).build_argv(goal, "s1")

	def test_a_short_goal_is_not_mistaken_for_template_contamination(self, tmp_path: Path) -> None:
		"""A one-character goal occurs in most absolute paths; that proves nothing."""
		adapter = adapter_for(tmp_path, "complete")
		assert adapter.build_argv("g", "s1")[-1] == "g"

	def test_a_long_goal_resembling_a_slot_is_still_accepted(self, tmp_path: Path) -> None:
		"""The guard fires on the goal itself, not on the word 'session'."""
		adapter = adapter_for(tmp_path, "complete")
		goal = "make the session directory carry the session id in its name"
		assert adapter.build_argv(goal, "s1")[-1] == goal

	def test_an_empty_goal_is_refused(self, tmp_path: Path) -> None:
		adapter = adapter_for(tmp_path, "complete")
		with pytest.raises(AssertionError, match="needs a goal"):
			adapter.build_argv("   ", "s1")

	def test_an_empty_model_is_refused_at_construction(self, tmp_path: Path) -> None:
		with pytest.raises(AssertionError, match="needs a model"):
			ConfiguredHarnessAdapter(PI_SPEC, workspace=tmp_path, session_dir=tmp_path, model=" ")

	def test_a_non_positive_probe_timeout_is_refused(self, tmp_path: Path) -> None:
		with pytest.raises(AssertionError, match="probe timeout must be positive"):
			ConfiguredHarnessAdapter(
				PI_SPEC, workspace=tmp_path, session_dir=tmp_path, model="m", probe_timeout=0.0
			)


# --------------------------------------------------------------------------- #
# record parsing: the wire format read back
# --------------------------------------------------------------------------- #


class TestParseCompletion:
	def test_a_completed_turn_is_a_structured_declaration(self) -> None:
		rows = _records({"type": "turn/end", "data": {"reason": {"kind": "completed"}}})
		assert parse_completion(rows, DSH_SPEC) is True

	def test_a_different_reason_is_not_a_declaration(self) -> None:
		rows = _records({"type": "turn/end", "data": {"reason": {"kind": "aborted"}}})
		assert parse_completion(rows, DSH_SPEC) is False

	def test_a_harness_with_no_completion_signal_never_declares(self) -> None:
		"""Absence of a declaration is not a declaration of failure."""
		rows = _records({"type": "turn/end", "data": {"reason": {"kind": "completed"}}})
		assert parse_completion(rows, PI_SPEC) is False

	def test_a_record_without_a_data_block_is_skipped(self) -> None:
		assert parse_completion(_records({"type": "turn/end"}), DSH_SPEC) is False


class TestParseUsage:
	def test_usage_is_summed_across_records(self) -> None:
		rows = _records(
			{"type": "a", "data": {"usage": {"outputTokens": 10}}},
			{"type": "b", "data": {"usage": {"outputTokens": 32}}},
		)
		assert parse_usage(rows, DSH_SPEC) == 42

	def test_no_usage_block_is_None_and_not_zero(self) -> None:
		"""A harness that reports nothing is unmeasured; zero would be a fabrication."""
		assert parse_usage(_records({"type": "a", "data": {}}), DSH_SPEC) is None

	def test_pi_reports_no_usage_at_all(self) -> None:
		rows = _records({"type": "a", "data": {"usage": {"outputTokens": 10}}})
		assert parse_usage(rows, PI_SPEC) is None

	def test_a_boolean_is_not_a_token_count(self) -> None:
		rows = _records({"type": "a", "data": {"usage": {"outputTokens": True}}})
		assert parse_usage(rows, DSH_SPEC) is None

	def test_max_reduction_takes_the_largest_single_record(self) -> None:
		spec = HarnessSpec(
			name="m", argv=("true",), usage_path=("usage", "outputTokens"), usage_reduce="max"
		)
		rows = _records(
			{"data": {"usage": {"outputTokens": 10}}},
			{"data": {"usage": {"outputTokens": 99}}},
		)
		assert parse_usage(rows, spec) == 99


class TestParseGoalEntryAndTurns:
	def test_prompt_delivery_is_the_default_and_is_not_forced(self) -> None:
		entry = parse_goal_entry(_records({"type": "user/message"}), DSH_SPEC)
		assert entry is GoalEntry.PROMPT
		assert entry.is_forced is False

	def test_a_goal_typed_event_means_the_session_carried_the_goal(self) -> None:
		spec = HarnessSpec(name="g", argv=("true",), goal_event_types=("goal/created",))
		entry = parse_goal_entry(_records({"type": "goal/created"}), spec)
		assert entry is GoalEntry.GOAL_BEARING_SESSION
		assert entry.is_forced is True

	def test_a_harness_that_emits_no_goal_events_can_only_ever_report_a_prompt(self) -> None:
		"""Absence of a goal event type is a measured limit, not a parsing failure."""
		rows = _records({"type": "goal/created"})
		assert parse_goal_entry(rows, DSH_SPEC) is GoalEntry.PROMPT

	def test_turns_are_counted_and_absence_is_None_not_one(self) -> None:
		rows = _records({"type": "turn/start"}, {"type": "turn/start"})
		assert parse_continuations(rows, DSH_SPEC) == 2
		assert parse_continuations(_records({"type": "message"}), DSH_SPEC) is None


# --------------------------------------------------------------------------- #
# the probe: capability measured, or explicitly not measured
# --------------------------------------------------------------------------- #


class TestProbe:
	async def test_probe_reports_every_capability_exactly_once(self, tmp_path: Path) -> None:
		"""Coverage completeness: adding a capability without a probe row fails here."""
		profile = await adapter_for(tmp_path, "complete").probe()
		assert len(profile.findings) == len(HarnessCapability)
		assert {f.capability for f in profile.findings} == set(HarnessCapability)

	def test_an_unprobed_capability_reads_inconclusive_not_absent(self) -> None:
		profile = HarnessProfile(name="none", command=("true",), probed_at=now(), findings=())
		assert profile.observation(HarnessCapability.CONCURRENT) is ProbeOutcome.INCONCLUSIVE
		assert profile.finding(HarnessCapability.CONCURRENT) is None

	async def test_a_process_that_exits_is_non_interactive(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.non_interactive is ProbeOutcome.CONFIRMED
		assert profile.is_usable is True
		assert profile.reduced_mode_available is True

	async def test_usage_in_the_record_confirms_telemetry(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.observation(HarnessCapability.TELEMETRY) is ProbeOutcome.CONFIRMED

	async def test_goal_mode_is_inconclusive_from_one_invocation(self, tmp_path: Path) -> None:
		"""One session cannot separate 'the harness cannot' from 'the model declined'."""
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.goal_mode is ProbeOutcome.INCONCLUSIVE
		assert profile.supports_goal_dispatch is False

	async def test_an_accepted_context_flag_is_confirmed(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert (
			profile.observation(HarnessCapability.CONTEXT_FILES_DISABLED) is ProbeOutcome.CONFIRMED
		)

	async def test_a_failing_invocation_means_the_flag_was_not_accepted(
		self, tmp_path: Path
	) -> None:
		profile = await adapter_for(tmp_path, "fail").probe()
		assert profile.observation(HarnessCapability.CONTEXT_FILES_DISABLED) is ProbeOutcome.ABSENT

	async def test_a_harness_without_the_flag_is_inconclusive_not_absent(
		self, tmp_path: Path
	) -> None:
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"), supports_context_file_flag=False
		)
		profile = await make_adapter(tmp_path, spec).probe()
		assert profile.observation(HarnessCapability.CONTEXT_FILES_DISABLED) is (
			ProbeOutcome.INCONCLUSIVE
		)

	async def test_a_process_that_never_exits_is_unusable(self, tmp_path: Path) -> None:
		"""A real kill after a real timeout: the FR-145 row, measured."""
		profile = await adapter_for(tmp_path, "slow", probe_timeout=0.5).probe()
		assert profile.non_interactive is ProbeOutcome.ABSENT
		assert profile.is_usable is False
		assert profile.supports_goal_dispatch is False
		assert profile.reduced_mode_available is False

	async def test_the_version_comes_from_a_real_invocation(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.version == "synthetic 1.2.3"

	async def test_the_session_record_path_is_kept(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.manifest_path is not None
		assert profile.manifest_path.endswith(".jsonl")

	async def test_an_absent_binary_is_a_local_fact_not_a_harness_finding(
		self, tmp_path: Path
	) -> None:
		"""A missing executable says nothing about the harness, so it is not a profile."""
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"), argv=("definitely-not-a-binary",)
		)
		with pytest.raises(HarnessBinaryMissing, match="on PATH and it is absent"):
			await make_adapter(tmp_path, spec).probe()

	async def test_a_zstd_spec_without_zstd_on_path_is_refused(
		self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		def without_zstd(name: str, *rest: object, **kwargs: object) -> str | None:
			return None if name == "zstd" else "/usr/bin/true"

		adapter = adapter_for(tmp_path, "complete", zstd=True)
		monkeypatch.setattr(shutil, "which", without_zstd)
		with pytest.raises(HarnessBinaryMissing, match="writes zstd session records"):
			await adapter.probe()

	async def test_a_zstd_session_record_is_decompressed_by_the_real_zstd_cli(
		self, tmp_path: Path
	) -> None:
		"""Python 3.13 ships no zstd binding, so this shells out; prove it works."""
		profile = await adapter_for(tmp_path, "complete", zstd=True).probe()
		assert profile.manifest_path is not None
		assert profile.manifest_path.endswith(".jsonl.zstd")
		assert profile.observation(HarnessCapability.TELEMETRY) is ProbeOutcome.CONFIRMED

	async def test_a_producer_that_names_its_file_zst_is_read_too(self, tmp_path: Path) -> None:
		"""zstd >= 1.5 defaults to '.zst', and decompression ignores the extension.

		The glob has to follow the producer's filename, which is why this is a spec
		field rather than a hard-coded '.zstd'.
		"""
		profile = await adapter_for(tmp_path, "complete", zstd=True, zstd_ext="zst").probe()
		assert profile.manifest_path is not None
		assert profile.manifest_path.endswith(".jsonl.zst")
		assert profile.observation(HarnessCapability.TELEMETRY) is ProbeOutcome.CONFIRMED

	async def test_a_record_that_is_not_json_is_reported_not_swallowed(
		self, tmp_path: Path
	) -> None:
		with pytest.raises(HarnessSessionUnreadable, match="is not JSON"):
			await adapter_for(tmp_path, "malformed").probe()

	async def test_a_json_line_that_is_not_an_object_is_reported(self, tmp_path: Path) -> None:
		with pytest.raises(HarnessSessionUnreadable, match="is not a JSON object"):
			await adapter_for(tmp_path, "notobject").probe()

	async def test_a_failing_process_still_produces_a_full_profile(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "fail").probe()
		assert profile.is_usable is True
		assert profile.observation(HarnessCapability.TELEMETRY) is ProbeOutcome.CONFIRMED


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #


@pytest.fixture
def plan(
	make_contract: Callable[..., Contract], make_oracle: Callable[..., OracleDeclaration]
) -> GoalPlan:
	"""A real plan, compiled from a real contract, through the real compiler."""
	contract = make_contract(
		(
			"An HTTP GET of /reminders returns the reminder within five seconds.",
			make_oracle("pytest -k reminders"),
		),
		(
			"A reminder is never delivered twice.",
			make_oracle("pytest -k idempotent", oracle_class=OracleClass.PROPERTY),
		),
	)
	return compile_plan(contract)


def _step(plan: GoalPlan, ordinal: int) -> GoalStep:
	step = next((s for s in plan.steps if s.ordinal == ordinal), None)
	assert step is not None, f"plan {plan.id} has no step {ordinal}"
	return step


def _covering(plan: GoalPlan, clauses: int = 1) -> GoalStep:
	"""The first step covering at least ``clauses`` clauses, whatever its ordinal."""
	step = next((s for s in plan.steps if len(s.clause_ids) >= clauses), None)
	assert step is not None, f"no step in plan {plan.id} covers {clauses} clause(s)"
	return step


class TestDispatch:
	async def test_no_profile_means_not_dispatched_never_a_silent_fallback(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""FR-148: 'never probed' cannot be quietly treated as reduced mode."""
		record = await adapter_for(tmp_path, "complete").dispatch(
			_step(plan, 0), plan, profile=None
		)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert "never probed" in (record.note or "")
		assert record.exit_code is None
		assert record.session_path is None

	async def test_a_profile_for_another_harness_is_a_hard_error(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete", name="synthetic")
		other = await adapter_for(tmp_path, "complete", name="elsewhere").probe()
		with pytest.raises(ValueError, match="not a recoverable error"):
			await adapter.dispatch(_step(plan, 0), plan, profile=other)

	async def test_a_step_absent_from_the_plan_is_refused(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		stranger = _step(plan, 0).model_copy(update={"id": "01920000-0000-7000-8000-0000000000ff"})
		with pytest.raises(ValueError, match="is not in plan"):
			await adapter.dispatch(stranger, plan, profile=profile)

	async def test_an_unusable_profile_dispatches_nothing(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "slow", probe_timeout=0.5)
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert "cannot run unattended" in (record.note or "")

	async def test_a_clean_exit_with_a_declaration_records_both_signals_separately(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""The process outcome and the producer's claim are two signals (FR-138)."""
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		record = await adapter.dispatch(_covering(plan), plan, profile=profile)
		assert record.outcome is StepOutcome.COMPLETED
		assert record.exit_code == 0
		assert record.declared_complete is True
		assert "claim, not a finding" in (record.declaration_note or "")
		assert record.tokens_observed == 120
		assert record.continuations_observed == 1

	async def test_a_nonzero_exit_fails_even_with_a_declaration(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete-fail")
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is StepOutcome.FAILED
		assert record.exit_code == 7

	async def test_a_session_with_no_completion_event_declares_nothing(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "plain")
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.declared_complete is False
		assert record.outcome is StepOutcome.COMPLETED
		assert "did not report completion" in (record.declaration_note or "")

	async def test_a_missing_session_record_is_reported_rather_than_guessed(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""The process exited; nothing about the session was witnessed. Say so."""
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"), session_glob="**/*{session_id}*nonexistent.jsonl"
		)
		adapter = make_adapter(tmp_path, spec)
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.session_path is None
		assert record.declared_complete is False
		assert "nothing about this session was witnessed" in (record.note or "")

	async def test_single_shot_dispatch_reports_the_capability_loss(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""FR-144: a degraded run must not look like the plan was honoured."""
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.mode.value == "single_shot"
		assert record.capability_loss is not None
		assert "FR-144" in (record.note or "")

	async def test_prompt_only_goal_entry_is_reported_as_unforced(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.goal_entry_observed is GoalEntry.PROMPT
		assert "may decline" in (record.note or "")

	async def test_exceeding_the_wall_clock_cap_is_budget_exhausted_not_failed(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""A kill by SoFact is SoFact exercising FR-140, not the work failing.

		The child is fast on the probe and hangs on the dispatch, so the probe really
		succeeds and the timeout is really the dispatch budget rather than a dead probe.
		"""
		adapter = adapter_for(tmp_path, "slow-after-first", probe_timeout=20.0)
		profile = await adapter.probe()
		assert profile.is_usable is True
		step = _step(plan, 0)
		tight = step.model_copy(
			update={"budget": step.budget.model_copy(update={"max_wall_clock_seconds": 0.5})}
		)
		record = await adapter.dispatch(tight, plan, profile=profile)
		assert record.outcome is StepOutcome.BUDGET_EXHAUSTED
		assert record.exit_code is None
		assert record.is_within_budget is False
		assert any("wall-clock cap" in v for v in record.budget_violations)
		assert any("FR-140" in v for v in record.budget_violations)

	async def test_the_pinned_hashes_are_carried_onto_the_record(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""FR-139: the record must name what the producer was actually given."""
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		step = _step(plan, 0)
		record = await adapter.dispatch(step, plan, profile=profile)
		assert record.goal_hash == step.goal_hash
		assert record.contract_hash == plan.contract_hash
		assert record.plan_id == plan.id
		assert record.goal_id == plan.goal_id
		assert record.step_id == step.id
		assert record.step_ordinal == step.ordinal

	async def test_the_argv_the_child_received_is_on_the_record(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		step = _step(plan, 0)
		record = await adapter.dispatch(step, plan, profile=profile)
		assert record.argv[-1] == step.goal.render(plan.goal_style)
		assert record.workspace == str(adapter.workspace)

	async def test_a_stderr_tail_is_kept_for_diagnosis(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		script = tmp_path / "noisy.py"
		script.write_text('import sys; sys.stderr.write("boom " * 900)\n', encoding="utf-8")
		spec = HarnessSpec(
			name="noisy",
			argv=(sys.executable, str(script), "{session_dir}", "{session_id}", "plain"),
		)
		adapter = make_adapter(tmp_path, spec)
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.stderr_tail is not None
		# A *tail* of a long stream starts mid-token by construction; do not demand
		# word alignment, only that the last thing the child said survived.
		assert "boom" in record.stderr_tail
		assert record.stderr_tail.endswith("boom ")
		assert len(record.stderr_tail) <= 2_048

	async def test_a_token_cap_overrun_is_recorded_after_the_fact(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		step = _step(plan, 0)
		capped = step.model_copy(
			update={"budget": step.budget.model_copy(update={"max_tokens": 10})}
		)
		record = await adapter.dispatch(capped, plan, profile=profile)
		assert any("token cap 10 exceeded" in v for v in record.budget_violations)
		assert record.tokens_observed == 120

	async def test_a_continuation_cap_overrun_is_recorded(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		step = _step(plan, 0)
		capped = step.model_copy(
			update={"budget": step.budget.model_copy(update={"max_continuations": 0})}
		)
		record = await adapter.dispatch(capped, plan, profile=profile)
		assert any("continuation cap 0 exceeded" in v for v in record.budget_violations)

	async def test_dispatch_is_recorded_as_failing_when_the_binary_vanishes(
		self, tmp_path: Path, plan: GoalPlan, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A workspace that had a harness at probe time and does not at dispatch time."""
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()

		def without_python(name: str, *rest: object, **kwargs: object) -> str | None:
			return None if name == sys.executable else shutil.which(name)

		monkeypatch.setattr(shutil, "which", without_python)
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert "no longer on PATH" in (record.note or "")
