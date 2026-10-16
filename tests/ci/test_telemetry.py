"""FR-102 — attempt telemetry.

"Build must report **attempt telemetry** (attempts, tokens, wall clock)."

The requirement is one sentence with three nouns, and the interesting part is the third
one's absence. ``DispatchRecord.tokens_observed`` is ``int | None`` because a harness may
report no usage at all, and ``None`` is *unmeasured* rather than zero (NFR-024, stated at
the source in :func:`sofact.harness.parse_usage`). So the property this suite spends most
of its effort on is not "does the total add up" but **"does the total say what it left
out"** — a sum that treated ``None`` as ``0`` would report a cheap build where the truth
is a build nobody measured, which is FR-118's missing qualification in arithmetic form.

Two halves, tested two ways. The **join** — an attempt row to the session record that
spent it — is exercised end to end against the real synthetic harness, because that is
where the two ledger rows actually meet. The **floor** is exercised against
:func:`sofact.telemetry.measure_attempts` directly, because the input it needs is a
dispatch whose harness reported nothing, and the honest way to build one is to construct
it rather than to reach into a real record and blank a field.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from synthetic import plan_and_service
from typer.testing import CliRunner, Result

from sofact.cli import app
from sofact.telemetry import measure_attempts, measure_spend
from sofact.views import (
	AttemptTelemetry,
	AttemptTelemetryReport,
	DeliveryEnvelope,
	DispatchMode,
	DispatchRecord,
	GoalPlan,
	GoalSpec,
	GoalStep,
	GoalStyle,
	Phase,
	PlanStepKind,
	RepairAttempt,
	RepairOutcome,
	SpendAttribution,
	StepBudget,
	StepOutcome,
)

PLAN_ID = "01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f0"
STEP_ID = "01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f2"


def a_goal() -> GoalSpec:
	"""A minimal goal, for the plan a spend fold is measured against.

	The six parts are restated here rather than imported from another suite for this
	module's own reason: no suite here imports across test modules, and a cross-module
	import would make this file's failure depend on that one's collection order.
	"""
	return GoalSpec(
		outcome="Implement the reminder store.",
		verification_surface=("the oracle exits 0",),
		constraints=("no new dependency",),
		boundaries=("the module directory only",),
		iteration_policy="one attempt, then stop",
		blocked_stop_condition="stop and report if the interface is missing",
	)


REPAIR_ORACLE = "test -f repair-marker.txt"
"""The refuted-until-repaired oracle, as ``test_service`` defines it.

Restated rather than imported: no other suite here imports across test modules, and a
cross-module import would make this file's failure depend on that one's collection order.
"""

RUNNER = CliRunner()


async def _repaired(home: Path, tmp_path: Path, mode: str = "complete-repair"):
	"""A plan dispatched and repaired once, so there is real telemetry to fold."""
	service, plan = await plan_and_service(home, tmp_path, mode, commands=REPAIR_ORACLE)
	await service.dispatch_plan(plan.id)
	await service.repair_plan(plan.id)
	return service, plan


def _dispatch(
	dispatch_id: str,
	*,
	tokens: int | None,
	wall_clock: float = 3.5,
	step_id: str = STEP_ID,
	plan_id: str = PLAN_ID,
) -> DispatchRecord:
	"""A dispatch record whose harness reported ``tokens``, or reported nothing."""
	at = datetime(2026, 10, 14, tzinfo=UTC)
	return DispatchRecord(
		id=dispatch_id,
		plan_id=plan_id,
		goal_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f1",
		step_id=step_id,
		step_ordinal=1,
		harness="synthetic",
		mode=DispatchMode.SINGLE_SHOT,
		outcome=StepOutcome.COMPLETED,
		argv=("synthetic",),
		workspace="/tmp/ws",
		budget=StepBudget(max_wall_clock_seconds=60.0, max_continuations=0, max_attempts=1),
		started_at=at,
		ended_at=at,
		wall_clock_seconds=wall_clock,
		goal_hash="0" * 64,
		contract_hash="1" * 64,
		tokens_observed=tokens,
	)


def _repair(attempt_id: str, dispatch_id: str | None, *, attempt: int = 1) -> RepairAttempt:
	return RepairAttempt(
		id=attempt_id,
		plan_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f0",
		revision_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f3",
		step_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f2",
		clause_ids=("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f7",),
		attempt=attempt,
		diagnosis="the oracle exited 5",
		goal_hash="2" * 64,
		outcome=RepairOutcome.REPAIRED if dispatch_id else RepairOutcome.NOT_COMPLETED,
		dispatch_id=dispatch_id,
		at=datetime(2026, 10, 14, tzinfo=UTC),
	)


class TestTheFoldCountsWhatWasMeasured:
	async def test_a_repaired_run_totals_its_attempts(self, home: Path, tmp_path: Path) -> None:
		"""FR-102's three quantities, over a real repair session."""
		service, plan = await _repaired(home, tmp_path)
		telemetry = await service.attempt_telemetry(plan.id)

		assert telemetry.plan_id == plan.id
		assert telemetry.total_attempts >= 1
		assert telemetry.total_wall_clock_seconds > 0, (
			"a session ran, so it took wall clock; a zero here would mean the dispatch "
			"was never joined to its attempt"
		)
		assert telemetry.tokens_complete, "the synthetic harness reports its usage"
		assert telemetry.total_tokens > 0

	async def test_an_attempt_names_the_dispatch_that_spent_it(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The join FR-102 needs: an attempt row and the session record, together."""
		service, plan = await _repaired(home, tmp_path)
		telemetry = await service.attempt_telemetry(plan.id)

		for row in telemetry.attempts:
			assert row.dispatch_id is not None, "a completed attempt produced a session"
			assert row.wall_clock_seconds > 0
			assert row.tokens_measured

	async def test_the_total_is_the_sum_of_its_rows(self, home: Path, tmp_path: Path) -> None:
		"""No hidden arithmetic: the report's numbers are the rows'."""
		service, plan = await _repaired(home, tmp_path)
		telemetry = await service.attempt_telemetry(plan.id)

		assert telemetry.total_tokens == sum(a.tokens for a in telemetry.attempts)
		assert telemetry.total_wall_clock_seconds == sum(
			a.wall_clock_seconds for a in telemetry.attempts
		)


class TestTheTotalSaysWhatItLeftOut:
	def test_an_unmeasured_harness_reports_a_floor_not_a_total(self) -> None:
		"""The defect this type exists to prevent, stated as a test.

		A harness that reports no usage yields ``None``, and the total must then be a floor
		carrying the count of what it could not see — never a bare number that reads as
		complete. Two attempts, one measured: the sum is the measured one and the report
		says one is missing.
		"""
		plan_id = "01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f0"
		measured = _dispatch("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f8", tokens=120)
		blind = _dispatch("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f9", tokens=None)

		report = measure_attempts(
			plan_id=plan_id,
			repairs=(
				_repair("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fa", measured.id),
				_repair("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fb", blind.id),
			),
			dispatches=(measured, blind),
		)

		assert report.total_tokens == 120, "the blind session contributed no tokens"
		assert not report.tokens_complete
		assert report.unmeasured_tokens == 1
		assert report.total_wall_clock_seconds == 7.0, "wall clock was observed either way"

	def test_a_fully_measured_run_is_complete(self) -> None:
		"""The other arm: when every session reports, the sum is exact."""
		measured = _dispatch("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f8", tokens=120)
		report = measure_attempts(
			plan_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f0",
			repairs=(_repair("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fa", measured.id),),
			dispatches=(measured,),
		)
		assert report.tokens_complete
		assert report.unmeasured_tokens == 0
		assert report.total_tokens == 120

	def test_a_missing_dispatch_is_unmeasured_not_free(self) -> None:
		"""A torn read is a floor, not a zero.

		The log is append-only and a dispatch is written when its session ends, so an
		attempt whose dispatch is absent is a partial read. Counting it as free would
		invent a measurement NFR-024 forbids.
		"""
		report = measure_attempts(
			plan_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f0",
			repairs=(
				_repair(
					"01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fa", "01a136fc-097a-7aa6-aeb7-6e4f5e5ce2ff"
				),
			),
			dispatches=(),
		)
		assert report.total_tokens == 0
		assert not report.tokens_complete
		assert report.unmeasured_tokens == 1

	def test_an_attempt_that_never_ran_is_not_unmeasured(self) -> None:
		"""No session means no spend *and* nothing hidden — a different fact."""
		report = measure_attempts(
			plan_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f0",
			repairs=(_repair("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fa", None),),
			dispatches=(),
		)
		assert report.total_attempts == 1, "the refusal is a row, not a dropped one"
		assert report.tokens_complete, "nothing ran, so nothing is unmeasured"
		assert report.total_tokens == 0
		assert report.total_wall_clock_seconds == 0.0


class TestTheRowTypeRefusesImpossibleSpend:
	def test_a_cost_with_no_session_is_refused(self) -> None:
		with pytest.raises(ValueError, match="reports no spend"):
			AttemptTelemetry(
				attempt_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fa",
				clause_ids=("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f7",),
				attempt=1,
				outcome=RepairOutcome.NOT_COMPLETED,
				wall_clock_seconds=4.2,
			)

	def test_a_zero_attempt_ordinal_is_refused(self) -> None:
		with pytest.raises(ValueError, match="1-based"):
			AttemptTelemetry(
				attempt_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fa",
				clause_ids=("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f7",),
				attempt=0,
				outcome=RepairOutcome.NOT_COMPLETED,
			)


class TestTheVacuousPassIsRefused:
	async def test_a_plan_with_no_repair_claims_nothing(self, home: Path, tmp_path: Path) -> None:
		"""Zero tokens over zero attempts is the absence of a measurement.

		The rule :attr:`EscapeReport.discharged` and :attr:`OracleAuditReport.discharged`
		both state: a reading that measured nothing carries out nothing.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")
		await service.dispatch_plan(plan.id)

		telemetry = await service.attempt_telemetry(plan.id)

		assert telemetry.attempts == ()
		assert telemetry.total_attempts == 0
		assert telemetry.discharged == (), (
			"FR-102 over a run that made no attempt is not a clean result, it is no result"
		)

	async def test_a_run_with_attempts_discharges_the_requirement(
		self, home: Path, tmp_path: Path
	) -> None:
		service, plan = await _repaired(home, tmp_path)
		telemetry = await service.attempt_telemetry(plan.id)

		assert telemetry.discharged == ("FR-102",)


class TestTheScopeIsThePlan:
	async def test_another_plans_attempts_are_not_in_the_total(
		self, home: Path, tmp_path: Path
	) -> None:
		"""An attempt belongs to the run that made it, so a total cannot absorb a peer's."""
		service, plan = await _repaired(home, tmp_path)
		telemetry = await service.attempt_telemetry(plan.id)

		assert all(row.attempt_id for row in telemetry.attempts)
		state = await service.state()
		assert len(state.repairs_for_plan(plan.id)) >= len(telemetry.attempts)

		other = await service.attempt_telemetry("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2ff")
		assert other.attempts == (), "an unknown plan has no attempts, not everyone's"

	def test_the_fold_filters_by_plan_id(self) -> None:
		"""Stated on the pure function, where the filter actually lives."""
		measured = _dispatch("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f8", tokens=10)
		report = measure_attempts(
			plan_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f0",
			repairs=(_repair("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fa", measured.id),),
			dispatches=(measured,),
		)
		assert report.total_attempts == 1

		empty = measure_attempts(
			plan_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2ee",
			repairs=(_repair("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2fa", measured.id),),
			dispatches=(measured,),
		)
		assert empty.total_attempts == 0


class TestTheAttemptsAreFiledUnderTheOriginPlan:
	"""The join that a repair revision can silently break.

	A repair authors a *new plan revision* per attempt, so the plan the log ends on is
	not the plan the attempts name. Anything that asks the latest plan for the cost gets
	an empty total that looks like a clean run — which is the failure this accessor
	exists to make impossible, and the one the CLI verb actually hit.
	"""

	async def test_the_latest_plan_is_not_the_one_repairs_name(
		self, home: Path, tmp_path: Path
	) -> None:
		service, plan = await _repaired(home, tmp_path)
		state = await service.state()

		latest = state.latest_plan(plan.contract_id)
		assert latest is not None
		assert latest.id != plan.id, "the repair authored a revision, or this proves nothing"
		assert state.repairs_for_plan(latest.id) == (), (
			"a revision owns no attempt; this is why the verb must not ask it"
		)

	async def test_the_origin_plan_owns_them(self, home: Path, tmp_path: Path) -> None:
		service, plan = await _repaired(home, tmp_path)

		origin = await service.origin_plan(plan.contract_id)

		assert origin is not None
		assert origin.id == plan.id, "the plan the loop was entered with is the origin"
		assert (await service.attempt_telemetry(origin.id)).total_attempts >= 1

	async def test_a_contract_with_no_plan_has_no_origin(self, home: Path, tmp_path: Path) -> None:
		"""Absent is absent, not the first of an empty list."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="exit 0")

		assert await service.origin_plan("01a136fc-097a-7aa6-aeb7-6e4f5e5ce2ff") is None
		assert (await service.origin_plan(plan.contract_id)) is not None, (
			"the same service does have one for a contract that was planned, so the "
			"None above is the unknown contract rather than a broken accessor"
		)


class TestTheReportIsAPureFold:
	async def test_the_same_log_folds_to_the_same_numbers(self, home: Path, tmp_path: Path) -> None:
		"""Reproducible from the log alone, which is what makes it evidence."""
		service, plan = await _repaired(home, tmp_path)

		first = await service.attempt_telemetry(plan.id)
		second = await service.attempt_telemetry(plan.id)

		assert first.total_attempts == second.total_attempts
		assert first.total_tokens == second.total_tokens
		assert first.total_wall_clock_seconds == second.total_wall_clock_seconds
		assert isinstance(first, AttemptTelemetryReport)


class TestPerClauseCounts:
	async def test_attempts_are_counted_at_the_clause(self, home: Path, tmp_path: Path) -> None:
		"""FR-101 bounds the loop at the clause, so the cost is legible there too."""
		service, plan = await _repaired(home, tmp_path)
		telemetry = await service.attempt_telemetry(plan.id)

		counted = dict(telemetry.by_clause)
		for row in telemetry.attempts:
			for clause_id in row.clause_ids:
				assert counted[clause_id] >= 1
		assert sum(counted.values()) >= telemetry.total_attempts


class TestTheCliReportsIt:
	"""Through the registered verb, not the coroutine behind it.

	``RUNNER.invoke(app, ...)`` is the only route that proves the command is *wired* —
	a report nobody can reach is not reported, and a suite that called the private
	coroutine would pass against a verb that was never added to the app.

	These two are **synchronous**, unlike every other class here, because the command
	body calls ``asyncio.run`` itself: inside an ``async def`` test there is already a
	running loop, and ``invoke`` raises rather than reporting. Setup goes through
	``asyncio.run`` the way ``test_cli`` does it.
	"""

	def _run(self, home: Path) -> Result:
		return RUNNER.invoke(app, ["attempts", "--home", str(home)])

	def test_the_verb_prints_the_three_quantities(self, home: Path, tmp_path: Path) -> None:
		"""FR-102's three nouns, end to end through the real command."""
		_, plan = asyncio.run(_repaired(home, tmp_path))

		result = self._run(home)

		assert result.exit_code == 0, result.output
		out = result.output
		assert "attempt telemetry" in out
		assert "tokens" in out
		assert "attempt(s)" in out
		assert plan.id in out, (
			"the verb must name the plan the attempts are filed under — the origin, not "
			"the revision the log ends on"
		)

	def test_the_verb_refuses_an_empty_run(self, home: Path, tmp_path: Path) -> None:
		"""A screen showing zeros would read as a cheap build; it exits non-zero instead."""
		service, plan = asyncio.run(plan_and_service(home, tmp_path, "complete", commands="exit 0"))
		asyncio.run(service.dispatch_plan(plan.id))

		result = self._run(home)

		assert result.exit_code == 1, result.output
		assert "absence of a measurement" in result.output


# --------------------------------------------------------------------------- #
# FR-133 — spend attributed per phase and per module
# --------------------------------------------------------------------------- #


class TestSpendIsAttributedPerPhaseAndPerModule:
	"""FR-133's two keys, over one run's real dispatches.

	``DispatchRecord`` carries a step id and no phase, and a ``GoalStep`` carries a kind
	and no phase — P3 produced the decomposition and P5 produced the plan, and the two
	never met. The phase is therefore *derived* from the step kind
	(:func:`sofact.tiers.step_phase`) rather than stored, and the module comes from the
	checkout, which is where FR-100 already records it. This class is what asserts that
	join holds on real rows.
	"""

	async def test_both_keys_account_for_every_dispatch(self, home: Path, tmp_path: Path) -> None:
		"""The two buckets are the same rows totalled twice, so they must sum alike.

		That equality is what makes this a fold rather than two unrelated summaries: the
		module buckets plus the unattributed count must equal the phase buckets, or a row
		went into one key and not the other.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		await service.dispatch_plan(plan.id)
		report = await service.spend_report(plan.id)

		assert report.by_phase, "a dispatched plan must attribute spend to at least one phase"
		per_module = sum(bucket.dispatches for bucket in report.by_module)
		assert per_module + report.unattributed == report.total_dispatches

	async def test_the_phase_is_a_pipeline_phase_not_a_step_kind(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A bucket keyed ``operation`` would be a step kind wearing a phase's name."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		await service.dispatch_plan(plan.id)
		report = await service.spend_report(plan.id)

		keys = {bucket.key for bucket in report.by_phase}
		assert keys, "the report must have at least one phase bucket"
		assert keys <= {phase.value for phase in Phase}

	async def test_the_module_buckets_name_modules_of_the_approved_decomposition(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A module name the decomposition does not hold would be an invented key."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		await service.dispatch_plan(plan.id)
		state = await service.state()
		decomposition = state.latest_decomposition(plan.contract_id)
		assert decomposition is not None
		report = await service.spend_report(plan.id)

		named = {module.name for module in decomposition.modules}
		for bucket in report.by_module:
			assert bucket.key in named

	async def test_a_step_no_module_owns_is_counted_rather_than_dropped(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A bootstrap step covers no clause (FR-100), and its spend is still spend."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		await service.dispatch_plan(plan.id)
		report = await service.spend_report(plan.id)

		unowned = [step for step in plan.steps if step.kind is PlanStepKind.BOOTSTRAP]
		if not unowned:
			pytest.skip("this plan has no module-less step to check")
		assert report.unattributed >= 1

	async def test_the_same_log_folds_to_the_same_attribution(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Reproducible from the log alone, which is what makes it evidence."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		await service.dispatch_plan(plan.id)

		first = await service.spend_report(plan.id)
		second = await service.spend_report(plan.id)

		assert first.total_dispatches == second.total_dispatches
		assert first.total_tokens == second.total_tokens
		assert first.by_module == second.by_module


class TestTheAttributionSaysWhatItLeftOut:
	"""NFR-024 applied to a bucket: an unmeasured dispatch is not a cheap one."""

	def _plan(self) -> GoalPlan:
		step = GoalStep(
			id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f2",
			ordinal=0,
			kind=PlanStepKind.OPERATION,
			goal=a_goal(),
			goal_hash="0" * 64,
			budget=StepBudget(max_wall_clock_seconds=60.0, max_continuations=0, max_attempts=1),
			exit_evidence=("the oracle passes",),
		)
		return GoalPlan(
			id=PLAN_ID,
			goal_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f1",
			contract_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f3",
			contract_hash="1" * 64,
			oracle_set_hash="2" * 64,
			goal_style=GoalStyle.LABELLED,
			created_at=datetime(2026, 10, 14, tzinfo=UTC),
			steps=(step,),
		)

	def test_a_bucket_with_an_unmeasured_dispatch_is_not_fully_measured(self) -> None:
		"""``tokens=0`` with ``unmeasured_tokens=1`` is a different statement from zero."""
		report = measure_spend(plan=self._plan(), dispatches=(_dispatch(STEP_ID, tokens=None),))
		bucket = report.by_phase[0]
		assert bucket.tokens == 0
		assert bucket.unmeasured_tokens == 1
		assert not bucket.tokens_measured
		assert not report.tokens_complete

	def test_a_mean_is_refused_when_the_bucket_is_not_fully_measured(self) -> None:
		"""A mean whose denominator silently drops the unmeasured rows is the flattering one."""
		report = measure_spend(plan=self._plan(), dispatches=(_dispatch(STEP_ID, tokens=None),))
		assert report.by_phase[0].tokens_per_dispatch is None

	def test_a_fully_measured_bucket_reports_its_mean(self) -> None:
		report = measure_spend(
			plan=self._plan(),
			dispatches=(_dispatch(STEP_ID, tokens=100, wall_clock=2.0),),
		)
		bucket = report.by_phase[0]
		assert bucket.tokens_measured
		assert bucket.tokens_per_dispatch == 100.0

	def test_a_vacuous_run_claims_nothing(self) -> None:
		"""A plan with no dispatch is the absence of a measurement, not a cheap build."""
		report = measure_spend(plan=self._plan(), dispatches=())
		assert report.discharged == ()
		assert report.total_dispatches == 0

	def test_a_dispatch_of_another_plan_is_not_folded_in(self) -> None:
		"""The scope is the plan, so one run's spend cannot hide inside another's."""
		other = _dispatch(STEP_ID, tokens=999).model_copy(
			update={"plan_id": "01a136fc-097a-7aa6-aeb7-6e4f5e5ce2ff"}
		)
		report = measure_spend(plan=self._plan(), dispatches=(other,))
		assert report.total_dispatches == 0

	def test_a_dispatch_naming_a_step_the_plan_lacks_is_refused(self) -> None:
		"""A stranger's row must not be attributed to a default phase."""
		orphan = _dispatch(
			"01a136fc-097a-7aa6-aeb7-6e4f5e5ce2ee",
			tokens=10,
			step_id="01a136fc-097a-7aa6-aeb7-6e4f5e5ce2e0",
		)
		with pytest.raises(ValueError, match="does not hold"):
			measure_spend(plan=self._plan(), dispatches=(orphan,))


class TestTheEnvelopeComparisonIsMadeWhereThereIsADimension:
	"""FR-133 says "against the §1.3 envelope", and §1.3 bounds no tokens (NFR-025)."""

	async def test_tokens_are_attributed_but_compared_to_no_dimension(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``token_dimension`` is ``None`` *with a reason*, not a field nobody filled in."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		await service.dispatch_plan(plan.id)
		report = await service.spend_report(plan.id)

		assert report.token_dimension is None
		assert "none of them is tokens" in report.token_envelope_note
		assert report.total_tokens >= 0

	async def test_wall_clock_is_measured_against_the_envelope(
		self, home: Path, tmp_path: Path
	) -> None:
		"""§1.3's ``wall_clock_days`` is a *range*, so a fast run is below its floor.

		This is the finding the boolean would have hidden: a synthetic run takes seconds
		and §1.3 targets 2-10 days, so ``within`` is ``False`` — correctly, because the
		run did not hit the target — while the run is nowhere near an *overspend*. The
		measurement carries the direction; :attr:`wall_clock_over_envelope` answers the
		overspend question, which is the one FR-133's rationale is about.
		"""
		service, plan = await plan_and_service(
			home, tmp_path, "complete", envelope=DeliveryEnvelope()
		)
		await service.dispatch_plan(plan.id)
		report = await service.spend_report(plan.id)

		measurement = report.wall_clock_measurement
		assert measurement is not None
		assert measurement.actual is not None and measurement.actual < 1.0
		assert measurement.within is False, "seconds is below §1.3's 2-day floor"
		assert report.wall_clock_over_envelope is False, (
			"under the floor is not an overspend, and reporting it as one would train "
			"an operator to ignore this column"
		)
		assert "below" in measurement.detail
		assert "not an overspend" in measurement.detail

	async def test_no_envelope_leaves_the_comparison_unmade_rather_than_true(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Three states, and "nobody set an envelope" is not "the envelope held"."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		await service.dispatch_plan(plan.id)
		report = await service.spend_report(plan.id)

		assert report.envelope is None
		assert report.wall_clock_measurement is None
		assert report.wall_clock_over_envelope is None


class TestTheSpendBucketTypeRefusesImpossibleSpend:
	def test_more_unmeasured_than_dispatches_is_refused(self) -> None:
		with pytest.raises(ValueError, match="more unmeasured dispatches"):
			SpendAttribution(key="P5", dispatches=1, unmeasured_tokens=2)

	def test_spend_with_no_dispatch_is_refused(self) -> None:
		with pytest.raises(ValueError, match="no dispatches but reports spend"):
			SpendAttribution(key="P5", dispatches=0, tokens=10)

	def test_a_negative_count_is_refused(self) -> None:
		with pytest.raises(ValueError, match="cannot be negative"):
			SpendAttribution(key="P5", dispatches=-1)
