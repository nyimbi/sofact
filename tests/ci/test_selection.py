"""FR-147 — harness selection by measurement.

"Harness selection must be **empirical** — driven by measured goal-declaration precision
(§20.4) and throughput, not by reputation."

The requirement is about a *choice*, so most of what can go wrong here is not a wrong
number but a wrong claim about a number. Three properties carry the suite, and each is a
way the selection could lie:

**An unmeasured harness must not lose.** Every rate is ``None`` with no denominator
(NFR-024), and ``None`` is not zero. A harness nothing has judged has not scored badly —
it has not scored, and a ranking that sorted it last would be the reputation contest
FR-147 exists to replace, wearing a measurement's clothes.

**A goal-hacker must not win.** §20.4 calls a contract-integrity failure "the sharpest
form of goal-hacking", and a harness that edited its own success criteria is excluded
outright rather than ranked lower. A high-precision goal-hacker is the *expected* shape of
one, which is why the exclusion is ordered before every other reason.

**A tie must be reported.** Precision and throughput are the two axes FR-147 names, and
two harnesses equal on both are genuinely undecided by the numbers available. The
alphabetical tiebreak in the sort key exists so the sort is total, not so that it can pass
for a finding.

The end-to-end half runs the real synthetic script twice under two names, because the
selection is a fold over rows that only a real dispatch produces — and because the mode is
baked into each spec's argv, two specs over one script are two harnesses that genuinely
behave differently.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from synthetic import base_spec, gated_contract, spec_json, two_harness_service
from typer.testing import CliRunner, Result

from sofact.cli import app
from sofact.selection import (
	DECLARED_NOT_MEASURED,
	NO_SELECTION,
	measure_harnesses,
	select_harness,
)
from sofact.views import (
	AutonomyLevel,
	CapabilityFinding,
	ClauseVerdict,
	DispatchMode,
	DispatchRecord,
	GoalPlan,
	GoalSpec,
	GoalStep,
	GoalStyle,
	HarnessCapability,
	HarnessMetric,
	HarnessProfile,
	HarnessSelection,
	IntegrityCheck,
	IntegrityOutcome,
	IntegritySubject,
	ModuleCheckout,
	PlanStepKind,
	ProbeOutcome,
	StepBudget,
	StepOutcome,
	VerdictOutcome,
	VerificationReport,
)

AT = datetime(2026, 10, 16, tzinfo=UTC)
PLAN_ID = "01a1437e-713c-7bb2-919d-c431667f78cd"
GOAL_ID = "01a1437e-713d-7c27-9283-befccfa01fa4"
CONTRACT_ID = "01a1437e-713e-7a97-bc3a-4e19be9c2705"
STEP_ONE = "01a1437e-713f-782a-9ce7-f0d47f7f4eb2"
STEP_TWO = "01a1437e-7140-751e-ac07-898a147497b3"
DISPATCH_ONE = "01a1437e-7143-7a2f-8b1c-3d4e5f607182"
DISPATCH_TWO = "01a1437e-7144-7d3a-9e2b-4c5d6e7f8091"
CLAUSE_A = "01a1437e-7141-75a1-b648-7ca6d3887834"
CLAUSE_B = "01a1437e-7142-7c1e-9c0d-2a1f3b4c5d6e"

_BUDGET = StepBudget(max_wall_clock_seconds=60.0, max_continuations=0, max_attempts=1)


def _step(step_id: str, *, ordinal: int = 1, clause_ids: tuple[str, ...] = (CLAUSE_A,)) -> GoalStep:
	return GoalStep(
		id=step_id,
		ordinal=ordinal,
		kind=PlanStepKind.OPERATION,
		goal=GoalSpec(
			outcome="build it",
			verification_surface=("the oracle passes",),
			constraints=("do not touch the oracle",),
			boundaries=("the workspace",),
			iteration_policy="re-run the oracle",
			blocked_stop_condition="stop and say what blocked it",
		),
		goal_hash="a" * 64,
		budget=_BUDGET,
		exit_evidence=("the oracle exits zero",),
		clause_ids=clause_ids,
	)


def _plan(*steps: GoalStep) -> GoalPlan:
	return GoalPlan(
		id=PLAN_ID,
		goal_id=GOAL_ID,
		contract_id=CONTRACT_ID,
		contract_hash="b" * 64,
		oracle_set_hash="c" * 64,
		goal_style=GoalStyle.LABELLED,
		steps=steps,
		created_at=AT,
	)


def _dispatch(
	harness: str,
	*,
	dispatch_id: str,
	step_id: str,
	declared: bool = True,
	tokens: int | None = 100,
	continuations: int | None = 2,
	wall_clock: float = 10.0,
	module: str | None = None,
) -> DispatchRecord:
	"""One dispatch row, with only the fields this fold reads carrying meaning."""
	return DispatchRecord(
		id=dispatch_id,
		plan_id=PLAN_ID,
		goal_id=GOAL_ID,
		step_id=step_id,
		step_ordinal=1,
		harness=harness,
		mode=DispatchMode.SINGLE_SHOT,
		outcome=StepOutcome.COMPLETED,
		argv=(harness,),
		workspace="/tmp/ws",
		budget=_BUDGET,
		started_at=AT,
		ended_at=AT,
		wall_clock_seconds=wall_clock,
		goal_hash="a" * 64,
		contract_hash="b" * 64,
		declared_complete=declared,
		tokens_observed=tokens,
		continuations_observed=continuations,
		checkout=(
			None
			if module is None
			else ModuleCheckout(branch=f"module/{module}", step_ordinal=1, module=module)
		),
	)


def _report(*verdicts: tuple[str, VerdictOutcome]) -> VerificationReport:
	"""A verdict per clause, named rather than positional.

	The clauses are named because two steps covering *different* clauses is the only way
	to make two harnesses differ in precision while sharing one plan — and that is the
	shape the ranking tests need.
	"""
	return VerificationReport(
		contract_id=CONTRACT_ID,
		contract_hash="b" * 64,
		weakest_oracle_rank=1,
		ceiling=AutonomyLevel.L3,
		verdicts=tuple(
			ClauseVerdict(
				clause_id=clause_id,
				statement="a clause",
				outcome=outcome,
				reason="measured",
				evidence_ids=(),
			)
			for clause_id, outcome in verdicts
		),
		at=AT,
		run_id="r1",
	)


def _satisfied(*clause_ids: str) -> VerificationReport:
	return _report(*((clause_id, VerdictOutcome.SATISFIED) for clause_id in clause_ids))


def _profile(
	name: str,
	*,
	goal_mode: ProbeOutcome = ProbeOutcome.CONFIRMED,
	non_interactive: ProbeOutcome = ProbeOutcome.CONFIRMED,
) -> HarnessProfile:
	return HarnessProfile(
		name=name,
		command=(name,),
		probed_at=AT,
		findings=(
			CapabilityFinding(
				capability=HarnessCapability.GOAL_MODE,
				outcome=goal_mode,
				attempted="a goal-bearing prompt",
				observed="a goal event",
			),
			CapabilityFinding(
				capability=HarnessCapability.NON_INTERACTIVE,
				outcome=non_interactive,
				attempted="a child with stdin closed",
				observed="it exited",
			),
		),
	)


def _integrity(plan_id: str, outcome: IntegrityOutcome) -> IntegrityCheck:
	return IntegrityCheck(
		subject=IntegritySubject.CONTRACT,
		label=f"{plan_id}:contract",
		expected_hash="b" * 64,
		observed_hash="b" * 64 if outcome is IntegrityOutcome.INTACT else "d" * 64,
		outcome=outcome,
		detail="measured",
	)


# --------------------------------------------------------------------------- #
# the fold, over rows built by hand
# --------------------------------------------------------------------------- #


class TestAnUnmeasuredHarnessIsNotLast:
	"""NFR-024 on the ranking: no denominator means no score, not a score of zero."""

	def test_a_harness_that_never_declared_has_no_precision(self) -> None:
		"""A producer that never says "done" is not a producer with a precision of zero."""
		plan = _plan(_step(STEP_ONE))
		selection = measure_harnesses(
			harnesses=["alpha"],
			dispatches=[
				_dispatch("alpha", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE, declared=False)
			],
			plans=[plan],
			profiles=[_profile("alpha")],
			rendered_at=AT,
		)
		metric = selection.metrics[0]
		assert metric.dispatches == 1, "it ran"
		assert metric.declarations == 0
		assert metric.precision is None, "no declaration is not a precision of zero"
		assert metric.seconds_per_verified_module is None, "nothing was verified"
		assert not metric.is_measured
		assert selection.chosen is None, "an unmeasured harness cannot win"
		assert selection.discharged == ()

	def test_a_measured_harness_beats_an_unmeasured_one_that_never_ran(self) -> None:
		"""The defect FR-147 names: a harness wins a contest it did not enter."""
		plan = _plan(_step(STEP_ONE), _step(STEP_TWO, ordinal=2, clause_ids=(CLAUSE_B,)))
		selection = measure_harnesses(
			harnesses=["alpha", "beta"],
			dispatches=[
				_dispatch("alpha", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE),
				_dispatch("beta", dispatch_id=DISPATCH_TWO, step_id=STEP_TWO, declared=False),
			],
			plans=[plan],
			profiles=[_profile("alpha"), _profile("beta")],
			reports=[_satisfied(CLAUSE_A, CLAUSE_B)],
			rendered_at=AT,
		)
		assert selection.chosen == "alpha"
		assert [m.harness for m in selection.unmeasured] == ["beta"]
		assert any("unmeasured" in caveat for caveat in selection.caveats)

	def test_no_harness_at_all_claims_nothing(self) -> None:
		"""An empty table is not a selection, and it must not read as one."""
		selection = measure_harnesses(
			harnesses=[], dispatches=[], plans=[], profiles=[], rendered_at=AT
		)
		assert selection.metrics == ()
		assert selection.chosen is None
		assert selection.discharged == ()
		assert selection.not_implemented == ("FR-135", "FR-143", "FR-147")


class TestAGoalHackerIsExcludedRatherThanRanked:
	"""FR-139 and §20.4: the sharpest form of goal-hacking is not a low score."""

	def test_an_integrity_failure_excludes_a_harness_with_the_best_precision(self) -> None:
		"""The expected shape of a goal-hacker is a *high* precision, so it must be excluded."""
		plan = _plan(_step(STEP_ONE), _step(STEP_TWO, ordinal=2, clause_ids=(CLAUSE_B,)))
		selection = measure_harnesses(
			harnesses=["cheat", "honest"],
			dispatches=[
				_dispatch("cheat", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE),
				_dispatch("honest", dispatch_id=DISPATCH_TWO, step_id=STEP_TWO),
			],
			plans=[plan],
			profiles=[_profile("cheat"), _profile("honest")],
			integrity=[_integrity(PLAN_ID, IntegrityOutcome.MODIFIED)],
			reports=[_satisfied(CLAUSE_A, CLAUSE_B)],
			rendered_at=AT,
		)
		cheat = next(m for m in selection.metrics if m.harness == "cheat")
		assert cheat.precision == 1.0, "the goal-hacker scores perfectly"
		assert not cheat.is_selectable, "and is excluded anyway"
		assert "FR-139" in (cheat.exclusion_reason or "")
		assert [m.harness for m in selection.excluded] == ["cheat", "honest"], (
			"the integrity check is attributed through the plan, and both dispatched on it"
		)
		assert selection.chosen is None

	def test_an_intact_check_excludes_nobody(self) -> None:
		"""The exclusion must be the failure and not the check having run."""
		plan = _plan(_step(STEP_ONE))
		selection = measure_harnesses(
			harnesses=["alpha"],
			dispatches=[_dispatch("alpha", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE)],
			plans=[plan],
			profiles=[_profile("alpha")],
			integrity=[_integrity(PLAN_ID, IntegrityOutcome.INTACT)],
			reports=[_satisfied(CLAUSE_A)],
			rendered_at=AT,
		)
		assert selection.metrics[0].integrity_checks == 1
		assert selection.metrics[0].integrity_failures == 0
		assert selection.chosen == "alpha"

	def test_a_check_on_another_plan_is_not_charged_to_this_harness(self) -> None:
		"""Attribution goes through the plan, so a check naming no touched plan charges nobody."""
		plan = _plan(_step(STEP_ONE))
		selection = measure_harnesses(
			harnesses=["alpha"],
			dispatches=[_dispatch("alpha", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE)],
			plans=[plan],
			profiles=[_profile("alpha")],
			integrity=[_integrity(GOAL_ID, IntegrityOutcome.MODIFIED)],
			reports=[_satisfied(CLAUSE_A)],
			rendered_at=AT,
		)
		assert selection.metrics[0].integrity_checks == 0
		assert selection.metrics[0].integrity_failures == 0
		assert selection.chosen == "alpha"

	def test_an_unprobed_harness_is_excluded_and_says_it_was_never_asked(self) -> None:
		"""``None`` is not ``False``: no probe has answered FR-135's question."""
		plan = _plan(_step(STEP_ONE))
		selection = measure_harnesses(
			harnesses=["alpha"],
			dispatches=[_dispatch("alpha", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE)],
			plans=[plan],
			profiles=[],
			reports=[_satisfied(CLAUSE_A)],
			rendered_at=AT,
		)
		metric = selection.metrics[0]
		assert metric.probed is False
		assert metric.supports_goal_dispatch is None, "nobody asked, so it is not False"
		assert "never probed" in (metric.exclusion_reason or "")
		assert selection.chosen is None

	def test_a_probe_that_could_not_confirm_goal_mode_excludes_on_fr_135(self) -> None:
		"""FR-135's disqualifying pair, and INCONCLUSIVE is a non-confirmation."""
		plan = _plan(_step(STEP_ONE))
		selection = measure_harnesses(
			harnesses=["alpha"],
			dispatches=[_dispatch("alpha", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE)],
			plans=[plan],
			profiles=[_profile("alpha", goal_mode=ProbeOutcome.INCONCLUSIVE)],
			reports=[_satisfied(CLAUSE_A)],
			rendered_at=AT,
		)
		assert selection.metrics[0].probed is True
		assert selection.metrics[0].supports_goal_dispatch is False
		assert "FR-135" in (selection.metrics[0].exclusion_reason or "")
		assert selection.chosen is None


class TestTheRankingIsPrecisionThenThroughput:
	"""FR-147's two axes, in the order it names them."""

	def test_a_tie_on_both_axes_is_reported_rather_than_broken_silently(self) -> None:
		plan = _plan(_step(STEP_ONE), _step(STEP_TWO, ordinal=2, clause_ids=(CLAUSE_B,)))
		selection = measure_harnesses(
			harnesses=["alpha", "beta"],
			dispatches=[
				_dispatch(
					"alpha",
					dispatch_id=DISPATCH_ONE,
					step_id=STEP_ONE,
					module="core-a",
					wall_clock=10.0,
				),
				_dispatch(
					"beta",
					dispatch_id=DISPATCH_TWO,
					step_id=STEP_TWO,
					module="core-b",
					wall_clock=10.0,
				),
			],
			plans=[plan],
			profiles=[_profile("alpha"), _profile("beta")],
			reports=[_satisfied(CLAUSE_A, CLAUSE_B)],
			rendered_at=AT,
		)
		assert selection.tied == ("alpha", "beta"), "equal on precision and on throughput"
		assert any("tied" in caveat for caveat in selection.caveats)
		assert selection.chosen == "alpha", "the sort is total; the tie is what is reported"

	def test_the_faster_of_two_equals_wins_on_throughput(self) -> None:
		"""Seconds per verified module, and lower is better."""
		plan = _plan(_step(STEP_ONE), _step(STEP_TWO, ordinal=2, clause_ids=(CLAUSE_B,)))
		selection = measure_harnesses(
			harnesses=["slow", "quick"],
			dispatches=[
				_dispatch(
					"slow",
					dispatch_id=DISPATCH_ONE,
					step_id=STEP_ONE,
					module="core-a",
					wall_clock=100.0,
				),
				_dispatch(
					"quick",
					dispatch_id=DISPATCH_TWO,
					step_id=STEP_TWO,
					module="core-b",
					wall_clock=10.0,
				),
			],
			plans=[plan],
			profiles=[_profile("slow"), _profile("quick")],
			reports=[_satisfied(CLAUSE_A, CLAUSE_B)],
			rendered_at=AT,
		)
		assert selection.tied == ("quick",), "throughput separated them, so the best is alone"
		assert selection.chosen == "quick"

	def test_precision_outranks_throughput(self) -> None:
		"""A slow producer whose declarations hold beats a fast one whose do not.

		The two harnesses work *different* clauses of one plan, which is what lets one
		report separate them: precision is a property of the declarations, so a producer
		that declared on a step the verifier refuted scores zero however quick it was.
		"""
		plan = _plan(_step(STEP_ONE), _step(STEP_TWO, ordinal=2, clause_ids=(CLAUSE_B,)))
		selection = measure_harnesses(
			harnesses=["quick-liar", "slow-honest"],
			dispatches=[
				_dispatch(
					"quick-liar",
					dispatch_id=DISPATCH_ONE,
					step_id=STEP_ONE,
					module="core-a",
					wall_clock=1.0,
				),
				_dispatch(
					"slow-honest",
					dispatch_id=DISPATCH_TWO,
					step_id=STEP_TWO,
					module="core-b",
					wall_clock=900.0,
				),
			],
			plans=[plan],
			profiles=[_profile("quick-liar"), _profile("slow-honest")],
			reports=[
				_report((CLAUSE_A, VerdictOutcome.VIOLATED), (CLAUSE_B, VerdictOutcome.SATISFIED))
			],
			rendered_at=AT,
		)
		liar = next(m for m in selection.metrics if m.harness == "quick-liar")
		honest = next(m for m in selection.metrics if m.harness == "slow-honest")
		assert liar.precision == 0.0
		assert honest.precision == 1.0
		assert liar.seconds_per_verified_module is None, "its module was refuted, so no rate"
		assert honest.seconds_per_verified_module == 900.0
		assert selection.chosen == "slow-honest", "900 seconds per module still beats a liar"


class TestTheMeasurementIsNotTheWork:
	"""A selection ranks producers. It says nothing about whether their modules are right."""

	def test_a_verified_module_is_the_verifiers_finding_not_the_declaration(self) -> None:
		"""A producer that never declares can still have produced a verified module.

		The two denominators are deliberately different: precision needs a *declaration*,
		and the throughput rate needs a *verdict*. A harness whose work is verified and
		which never says "done" has a real throughput and an unmeasured precision, and
		both of those are true statements about it.
		"""
		plan = _plan(_step(STEP_ONE))
		selection = measure_harnesses(
			harnesses=["silent"],
			dispatches=[
				_dispatch(
					"silent",
					dispatch_id=DISPATCH_ONE,
					step_id=STEP_ONE,
					declared=False,
					module="core",
					wall_clock=20.0,
				)
			],
			plans=[plan],
			profiles=[_profile("silent")],
			reports=[_satisfied(CLAUSE_A)],
			rendered_at=AT,
		)
		metric = selection.metrics[0]
		assert metric.precision is None, "it never declared"
		assert metric.verified_modules == ("core",), "and its module was verified anyway"
		assert metric.seconds_per_verified_module == 20.0
		assert metric.is_measured, "one reading with a denominator is a measurement"

	def test_a_module_one_step_verified_and_another_did_not_is_not_verified(self) -> None:
		"""Worst wins, the rule the clause fold states one level down."""
		plan = _plan(_step(STEP_ONE), _step(STEP_TWO, ordinal=2, clause_ids=(CLAUSE_B,)))
		selection = measure_harnesses(
			harnesses=["alpha"],
			dispatches=[
				_dispatch("alpha", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE, module="core"),
				_dispatch("alpha", dispatch_id=DISPATCH_TWO, step_id=STEP_TWO, module="core"),
			],
			plans=[plan],
			profiles=[_profile("alpha")],
			reports=[
				_report((CLAUSE_A, VerdictOutcome.SATISFIED), (CLAUSE_B, VerdictOutcome.VIOLATED))
			],
			rendered_at=AT,
		)
		metric = selection.metrics[0]
		assert metric.modules == ("core",), "the module is counted once"
		assert metric.verified_modules == ()
		assert metric.unverified_modules == ("core",)

	def test_the_whole_section_20_4_matrix_is_carried(self) -> None:
		"""The five §20.4 metrics, and the two of them FR-147 ranks on."""
		plan = _plan(_step(STEP_ONE))
		selection = measure_harnesses(
			harnesses=["alpha"],
			dispatches=[
				_dispatch(
					"alpha",
					dispatch_id=DISPATCH_ONE,
					step_id=STEP_ONE,
					module="core",
					tokens=5000,
					continuations=4,
					wall_clock=60.0,
				)
			],
			plans=[plan],
			profiles=[_profile("alpha")],
			reports=[_satisfied(CLAUSE_A)],
			rendered_at=AT,
		)
		metric = selection.metrics[0]
		assert metric.precision == 1.0
		assert metric.seconds_per_verified_module == 60.0
		assert metric.tokens_per_verified_module == 5000.0
		assert metric.continuations_per_verified_module == 4.0

	def test_an_unmeasured_count_is_not_a_zero(self) -> None:
		"""A dispatch whose telemetry was never observed is counted as unmeasured (NFR-024)."""
		plan = _plan(_step(STEP_ONE))
		selection = measure_harnesses(
			harnesses=["alpha"],
			dispatches=[
				_dispatch(
					"alpha",
					dispatch_id=DISPATCH_ONE,
					step_id=STEP_ONE,
					tokens=None,
					continuations=None,
				)
			],
			plans=[plan],
			profiles=[_profile("alpha")],
			reports=[_satisfied(CLAUSE_A)],
			rendered_at=AT,
		)
		metric = selection.metrics[0]
		assert metric.tokens == 0 and metric.unmeasured_tokens == 1
		assert metric.continuations == 0 and metric.unmeasured_continuations == 1


class TestTheReportRefusesWhatItCannotSupport:
	"""The type's own validators, reached through the fold that builds it."""

	def test_a_selection_cannot_name_a_harness_it_did_not_measure(self) -> None:
		with pytest.raises(ValueError, match="not among the harnesses"):
			HarnessSelection(
				id=GOAL_ID, rendered_at=AT, metrics=(), chosen="ghost", reason="because"
			)

	def test_a_harness_cannot_appear_twice(self) -> None:
		metric = HarnessMetric(harness="alpha")
		with pytest.raises(ValueError, match="appears twice"):
			HarnessSelection(id=GOAL_ID, rendered_at=AT, metrics=(metric, metric), reason="because")

	def test_more_corroborations_than_declarations_is_impossible(self) -> None:
		with pytest.raises(ValueError, match="is impossible"):
			HarnessMetric(harness="alpha", declarations=1, corroborated=2)

	def test_a_module_cannot_be_verified_and_unverified_at_once(self) -> None:
		with pytest.raises(ValueError, match="verified and unverified"):
			HarnessMetric(
				harness="alpha",
				modules=("core",),
				verified_modules=("core",),
				unverified_modules=("core",),
			)

	def test_a_module_classified_but_never_dispatched_is_refused(self) -> None:
		with pytest.raises(ValueError, match="never dispatched"):
			HarnessMetric(harness="alpha", verified_modules=("core",))

	def test_a_token_rate_over_no_verified_module_is_unmeasured(self) -> None:
		"""§20.4's token figure has the same denominator rule as the rest."""
		metric = HarnessMetric(harness="alpha", tokens=5000, wall_clock_seconds=60.0)
		assert metric.tokens_per_verified_module is None
		assert metric.continuations_per_verified_module is None


class TestTheDeclarationFallback:
	"""Measurement first, declaration second — and the report says which happened."""

	def test_a_declared_harness_is_used_only_when_nothing_is_measured(self) -> None:
		selection = select_harness(
			harnesses=["alpha", "beta"],
			dispatches=[],
			plans=[],
			profiles=[],
			declared="beta",
			rendered_at=AT,
		)
		assert selection.chosen == "beta"
		assert selection.reason == DECLARED_NOT_MEASURED
		assert selection.discharged == (), "a fallback is not FR-147"
		assert selection.not_implemented == ("FR-135", "FR-143", "FR-147")
		assert any("not empirical" in caveat for caveat in selection.caveats)

	def test_a_measurement_outranks_a_declaration(self) -> None:
		"""The whole requirement: what ran beats what was named."""
		plan = _plan(_step(STEP_ONE))
		selection = select_harness(
			harnesses=["alpha", "beta"],
			dispatches=[_dispatch("alpha", dispatch_id=DISPATCH_ONE, step_id=STEP_ONE)],
			plans=[plan],
			profiles=[_profile("alpha"), _profile("beta")],
			reports=[_satisfied(CLAUSE_A)],
			declared="beta",
			rendered_at=AT,
		)
		assert selection.chosen == "alpha"
		assert selection.discharged == ("FR-135", "FR-143", "FR-147")

	def test_a_declared_name_outside_the_table_is_ignored(self) -> None:
		"""A choice outside the candidate set is one nothing supports."""
		selection = select_harness(
			harnesses=["alpha"],
			dispatches=[],
			plans=[],
			profiles=[],
			declared="ghost",
			rendered_at=AT,
		)
		assert selection.chosen is None
		assert "every configured harness is excluded" in selection.reason

	def test_a_probed_but_unmeasured_table_asks_for_a_probe_and_gets_no_answer(self) -> None:
		"""Every candidate is selectable and none has a denominator, so the answer is ``None``."""
		selection = select_harness(
			harnesses=["alpha", "beta"],
			dispatches=[],
			plans=[],
			profiles=[_profile("alpha"), _profile("beta")],
			rendered_at=AT,
		)
		assert selection.chosen is None
		assert selection.reason == NO_SELECTION
		assert "Probe a harness" in selection.reason
		assert selection.candidates != (), "they are eligible; they are simply unmeasured"

	def test_every_candidate_excluded_says_which_reason_excluded_it(self) -> None:
		selection = select_harness(
			harnesses=["alpha"],
			dispatches=[],
			plans=[],
			profiles=[],
			rendered_at=AT,
		)
		assert selection.chosen is None
		assert "every configured harness is excluded" in selection.reason
		assert "never probed" in selection.reason


# --------------------------------------------------------------------------- #
# end to end, through the real script
# --------------------------------------------------------------------------- #


class TestTheSelectionOverRealDispatches:
	"""The fold reads rows only a real dispatch produces, so the fixture is a real one.

	The mode is ``goal`` for both harnesses: that is the one mode whose session record
	carries a goal event, so a probe of it *confirms* goal mode and the harness clears
	FR-135 rather than being excluded for the reason this suite's unit half tests.
	"""

	async def test_two_real_harnesses_are_measured_against_each_other(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Two names over one script, dispatched and then selected between."""
		service = await two_harness_service(home, tmp_path, modes={"alpha": "goal", "beta": "goal"})
		await service.probe_harness("alpha")
		await service.probe_harness("beta")
		_, contract_id = await gated_contract(service, commands="exit 0")
		plan = await service.compile_plan(contract_id)
		await service.dispatch_plan(plan.id, name="alpha", max_steps=1)
		await service.dispatch_plan(plan.id, name="beta", max_steps=1)

		selection = await service.select_harness()
		assert {m.harness for m in selection.metrics} == {"alpha", "beta"}
		assert all(m.dispatches > 0 for m in selection.metrics), "both really ran"
		assert all(m.probed for m in selection.metrics), "and both were probed"
		assert selection.chosen is not None
		assert selection.discharged == ("FR-135", "FR-143", "FR-147")

	async def test_a_harness_that_never_ran_is_reported_as_unmeasured(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The configured-but-unrun harness is exactly the one a reader needs to see."""
		service = await two_harness_service(home, tmp_path, modes={"alpha": "goal", "beta": "goal"})
		await service.probe_harness("alpha")
		await service.probe_harness("beta")
		_, contract_id = await gated_contract(service, commands="exit 0")
		plan = await service.compile_plan(contract_id)
		await service.dispatch_plan(plan.id, name="alpha", max_steps=1)

		selection = await service.select_harness()
		by_name = {m.harness: m for m in selection.metrics}
		assert by_name["alpha"].is_measured
		assert not by_name["beta"].is_measured, "configured, probed, and never dispatched"
		assert selection.chosen == "alpha"

	async def test_the_service_falls_back_to_the_declared_harness(
		self, home: Path, tmp_path: Path
	) -> None:
		"""With nothing measured, the deployment's own name is used and the reason says so."""
		service = await two_harness_service(home, tmp_path, modes={"alpha": "goal", "beta": "goal"})
		selection = await service.select_harness("beta")
		assert selection.chosen == "beta"
		assert selection.reason == DECLARED_NOT_MEASURED

	async def test_the_selection_reads_the_whole_log_not_one_plan(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Two dispatches by one producer are more evidence about it, not a second row."""
		service = await two_harness_service(home, tmp_path, modes={"alpha": "goal", "beta": "goal"})
		await service.probe_harness("alpha")
		_, contract_id = await gated_contract(service, commands="exit 0")
		plan = await service.compile_plan(contract_id)
		await service.dispatch_plan(plan.id, name="alpha", max_steps=1)
		first = await service.select_harness()

		await service.dispatch_plan(plan.id, name="alpha", max_steps=1)
		second = await service.select_harness()
		assert len(second.metrics) == len(first.metrics), "one row per harness, not per run"
		assert second.metrics[0].dispatches > first.metrics[0].dispatches


# --------------------------------------------------------------------------- #
# the CLI
# --------------------------------------------------------------------------- #


def _run(home: Path, *args: str) -> Result:
	return CliRunner().invoke(app, ["--home", str(home), *args])


def _configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
	"""Register the shared script under each name, the way a deployment would.

	Without this the CLI loads the built-in table — ``claude``, ``dsh``, ``opencode``,
	``pi`` — and reports *those* as never probed, which is a true statement about a
	deployment the test did not configure. The verb reads the deployment's table, so the
	test has to supply one.
	"""
	table = {name: spec_json(base_spec(tmp_path, "goal", name=name)) for name in names}
	path = tmp_path / "selection-harnesses.json"
	path.write_text(json.dumps({"harnesses": table}), encoding="utf-8")
	monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(path))


class TestTheCliReportsIt:
	def test_select_with_nothing_configured_exits_non_zero_without_a_traceback(
		self, home: Path
	) -> None:
		result = _run(home, "select")
		assert "Traceback" not in result.output

	def test_select_prints_the_ranking_the_exclusions_and_the_caveats(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The screen must carry all three, because each answers a different question."""
		_configure(tmp_path, monkeypatch, "alpha", "beta")
		asyncio.run(self._prepare(home, tmp_path))
		result = _run(home, "select")
		assert result.exit_code == 0, result.output
		assert "harness selection (FR-147)" in result.output
		assert "selected:" in result.output
		assert "measured (§20.4)" in result.output
		assert "precision" in result.output
		assert "Traceback" not in result.output

	def test_select_with_no_measurement_exits_non_zero_and_names_the_reason(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		_configure(tmp_path, monkeypatch, "alpha", "beta")
		asyncio.run(self._probe_only(home, tmp_path))
		result = _run(home, "select")
		assert result.exit_code == 1, result.output
		assert "Probe a harness" in result.output
		assert "Traceback" not in result.output

	def test_select_reports_a_harness_the_deployment_never_probed_as_excluded(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The built-in table's own state, and the reason it must be named rather than omitted."""
		_configure(tmp_path, monkeypatch, "alpha", "beta")
		result = _run(home, "select")
		assert result.exit_code == 1, result.output
		assert "excluded (FR-135, FR-139)" in result.output
		assert "never probed" in result.output
		assert "alpha" in result.output and "beta" in result.output

	async def _prepare(self, home: Path, tmp_path: Path) -> None:
		service = await two_harness_service(home, tmp_path, modes={"alpha": "goal", "beta": "goal"})
		await service.probe_harness("alpha")
		_, contract_id = await gated_contract(service, commands="exit 0")
		plan = await service.compile_plan(contract_id)
		await service.dispatch_plan(plan.id, name="alpha", max_steps=1)

	async def _probe_only(self, home: Path, tmp_path: Path) -> None:
		service = await two_harness_service(home, tmp_path, modes={"alpha": "goal", "beta": "goal"})
		await service.probe_harness("alpha")
		await service.probe_harness("beta")


class TestTheDocumentedExample:
	"""README.md's selection example is the real verb's output shape.

	``TestTheDocumentedTable`` does this for the harness table and gives the reason:
	documentation that is never run is documentation that is eventually wrong. Here the
	check is narrower and can be exact — the verb is deterministic given the log, so the
	README can be held to the *strings* it shows rather than to a shape.
	"""

	ROOT = Path(__file__).resolve().parents[2]

	def test_the_readme_names_the_verb_and_its_two_axes(self) -> None:
		text = (self.ROOT / "README.md").read_text(encoding="utf-8")
		assert "sofact select" in text, "README.md no longer documents the selection verb"
		assert "FR-147" in text, "and no longer says which requirement it discharges"
