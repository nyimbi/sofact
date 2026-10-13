"""FR-021-023 — the escape oracle, which is where the regress terminates.

§2.4 asks "Who verifies the verifier?" and answers that the regress "terminates in exactly
one place: reality, after deployment". Every other ceiling in SoFact is derived from a
declaration — oracle rank, module class, topology — and a declaration can be wrong in a
direction nobody observes until something is reverted. This suite is about the one number
in the product that no producer authored.

Four separable claims are under test. The *refusals* are the API being hard to get wrong:
an escape from a change that never shipped, and an escape filed against a lane the
deployment never touched. The *reading rule* is where the honesty lives: a rate whose
numerator or denominator is implicit is a rate two readers compute differently from one
ledger. The *reduction* is FR-023's automatic lowering, and its two boundaries — a lane
already at L0 is not lowered further, and an unbudgeted lane is not lowered at all
because NFR-024 forbids inventing the threshold. The *override* is FR-023's escape hatch,
which must lift the reduction and be attributable by name, or it is the silent downgrade
FR-031 forbids.

The escape rate is also the one metric a producer cannot inflate, so the last class tests
the property rather than the arithmetic: nothing on the factory's verification path writes
to the ledger rows this fold reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from synthetic import (
	decompose_and_approve,
	elicitation_to_contract,
	specify_and_approve,
	synthetic_service,
)

from sofact.escape import lanes_of, load_escape_budget, measure_escapes
from sofact.service import FactoryService
from sofact.views import (
	MODULE_CLASS_CEILING,
	AutonomyLevel,
	EscapeBudget,
	EscapeKind,
	EscapeOverride,
	ModuleClass,
	lane_ceiling,
)

# The synthetic decomposition is a G4/G5/G7/G8 graph — see `lanes_of` below, which reads it
# off the report rather than assuming it. These two are named because the tests need a lane
# §14 puts at L3 (so a reduction has somewhere to go) and one at L1 (so a reduction can
# reach the floor), and a test that guessed a name would fail on a fixture change rather
# than on the behaviour it is about.
AT_L3 = ModuleClass.G4
AT_L1 = ModuleClass.G7


async def deployed_service(home: Path, tmp_path: Path) -> tuple[FactoryService, str, str]:
	"""A service with one deployed delivery. Returns ``(service, report_id, contract_id)``."""
	service = synthetic_service(home, tmp_path, "complete")
	await service.probe_harness(None)
	_, contract_id = await elicitation_to_contract(service, commands="true")
	await specify_and_approve(service, contract_id)
	await decompose_and_approve(service, contract_id)
	plan = await service.compile_plan(contract_id)
	root = tmp_path / "delivery"
	root.mkdir()
	report = await service.render_delivery(plan.id, root=root)
	assert report.passed, [check.name for check in report.failed]
	await service.approve_deploy(report.id, by="operator")
	return service, report.id, contract_id


async def with_budget(
	home: Path, tmp_path: Path, maximum_rate: float, lane: ModuleClass
) -> tuple[FactoryService, str, str]:
	"""The same, with one lane's budget declared and a service that knows it."""
	service = synthetic_service(home, tmp_path, "complete")
	service.escape_budgets = (
		EscapeBudget(lane=lane, maximum_rate=maximum_rate, declared_by="the operator"),
	)
	await service.probe_harness(None)
	_, contract_id = await elicitation_to_contract(service, commands="true")
	await specify_and_approve(service, contract_id)
	await decompose_and_approve(service, contract_id)
	plan = await service.compile_plan(contract_id)
	root = tmp_path / "delivery"
	root.mkdir()
	report = await service.render_delivery(plan.id, root=root)
	assert report.passed, [check.name for check in report.failed]
	await service.approve_deploy(report.id, by="operator")
	return service, report.id, contract_id


# --------------------------------------------------------------------------- #
# the lane-resolution rule, which the refusal and the denominator share
# --------------------------------------------------------------------------- #


class TestLanesAreReadOffTheChain:
	"""One function decides which lanes a deployment exercised, so a refusal and a rate
	cannot disagree about it. That is the whole reason it is a function and not two loops."""

	async def test_the_lanes_are_the_module_classes_the_chain_reaches(
		self, home: Path, tmp_path: Path
	) -> None:
		service, report_id, _ = await deployed_service(home, tmp_path)
		state = await service.state()
		report = next(r for r in state.deliveries if r.id == report_id)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)

		lanes = lanes_of(report, decomposition)

		assert lanes, "the synthetic decomposition reaches at least one module"
		named = {link.module for link in report.chain if link.module is not None}
		modules = {m.name: m for m in decomposition.modules}
		assert lanes == {modules[name].module_class for name in named if name in modules}

	def test_no_decomposition_is_no_lanes_rather_than_a_crash(self) -> None:
		"""A report whose decomposition the log does not hold resolves to nothing, which is
		the honest answer: the chain names modules by *name*, and a name with no
		decomposition behind it is a gap `traceability_chain` already fails on."""
		from test_delivery import a_report

		assert lanes_of(a_report(), None) == frozenset()


# --------------------------------------------------------------------------- #
# recording refuses two things
# --------------------------------------------------------------------------- #


class TestRecordingRefusesWhatCannotHaveEscaped:
	async def test_an_escape_from_an_undeployed_report_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""`record_gate_cost`'s rule on the other side of the deploy: an escape from a change
		that never shipped is a defect that never got out, and counting it would credit a
		lane with a failure reality never had the chance to cause."""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)
		root = tmp_path / "delivery"
		root.mkdir()
		report = await service.render_delivery(plan.id, root=root)
		assert report.passed

		with pytest.raises(ValueError, match="nothing escaped from it"):
			await service.record_escape(
				report.id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
			)

	async def test_a_lane_the_deployment_never_exercised_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The lane is the operator's — only they know which module broke — and validating it
		against the report's own chain makes filing an escape against a lane that was never
		deployed impossible."""
		service, report_id, _ = await deployed_service(home, tmp_path)
		state = await service.state()
		report = next(r for r in state.deliveries if r.id == report_id)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
		exercised = lanes_of(report, decomposition)
		absent = next(lane for lane in ModuleClass if lane not in exercised)

		with pytest.raises(ValueError, match="exercises no"):
			await service.record_escape(
				report_id, lane=absent, kind=EscapeKind.REVERT, defect="it broke", by="operator"
			)

	async def test_the_refusal_names_the_lanes_that_were_reached(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A refusal that did not say which lanes *were* deployed would leave the operator to
		guess at the one fact they need to correct the record."""
		service, report_id, _ = await deployed_service(home, tmp_path)
		state = await service.state()
		report = next(r for r in state.deliveries if r.id == report_id)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
		exercised = lanes_of(report, decomposition)
		absent = next(lane for lane in ModuleClass if lane not in exercised)

		with pytest.raises(ValueError) as raised:
			await service.record_escape(
				report_id, lane=absent, kind=EscapeKind.REVERT, defect="it broke", by="operator"
			)

		for lane in exercised:
			assert lane.value in str(raised.value)

	async def test_a_lane_the_deployment_did_exercise_is_recorded(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The control arm. A refusal that also refused the valid case would be a refusal of
		the feature rather than of the mistake."""
		service, report_id, _ = await deployed_service(home, tmp_path)

		escape = await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)

		assert escape.report_id == report_id
		assert escape.lane is AT_L3
		assert escape.defect == "it broke"
		assert await service.escapes(report_id) == (escape,)


# --------------------------------------------------------------------------- #
# the reading rule — the denominator
# --------------------------------------------------------------------------- #


class TestTheDenominator:
	async def test_a_second_deploy_of_one_report_is_not_a_second_change(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A change is a deployed *report*, keyed by id rather than counted by row. Two deploy
		records over one report are a decision and a re-affirmation of it, and counting rows
		would halve a lane's apparent escape rate for a reason no requirement asks for."""
		service, report_id, _ = await deployed_service(home, tmp_path)
		await service.approve_deploy(report_id, by="operator", note="again")

		report = await service.escape_report()

		for lane in report.lanes:
			assert lane.deployed_changes == 1
		# And the whole-measurement count, which `discharged` reads: the per-lane sets would
		# collapse the duplicate on their own, so a test that checked only those would pass
		# while the report claimed a measurement over two changes where there was one.
		assert report.deployed_changes == 1

	async def test_a_second_render_is_a_second_change(self, home: Path, tmp_path: Path) -> None:
		"""The other arm, and the reason the key is the id: a re-render carries a new
		``report_id``, so it is a second change and the denominator moves with it."""
		service, _, _ = await deployed_service(home, tmp_path)
		state = await service.state()
		plan_id = state.plans[-1].id
		second_root = tmp_path / "second"
		second_root.mkdir()
		second = await service.render_delivery(plan_id, root=second_root)
		await service.approve_deploy(second.id, by="operator")

		report = await service.escape_report()

		assert report.deployed_changes == 2
		for lane in report.lanes:
			assert lane.deployed_changes == 2, "one report spanning a lane is one change in it"

	async def test_the_rate_includes_the_deployment_that_escaped(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The stated limit: an escape is filed against a deployed report, so that report is
		in the denominator by construction. One escape in one deployment reads as 1.0, which
		is conservatively high and the correct direction for a safety metric."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L3)

		assert row.deployed_changes == 1
		assert row.escapes == 1
		assert row.rate == 1.0

	async def test_a_lane_with_no_deployment_is_not_in_the_report(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A lane with no deployments is unmeasured, not clean. Omitting it is the difference
		between a report of what was measured and a report of what went wrong."""
		service, _, _ = await deployed_service(home, tmp_path)
		state = await service.state()
		report = next(r for r in state.deliveries)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
		exercised = lanes_of(report, decomposition)

		measured = await service.escape_report()

		assert {row.lane for row in measured.lanes} == set(exercised)


# --------------------------------------------------------------------------- #
# the reading rule — the numerator
# --------------------------------------------------------------------------- #


class TestTheNumerator:
	async def test_one_defect_taking_two_events_is_one_escape(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-021 names three kinds of event and one defect can produce two of them — a revert
		and then a hot-fix. Counting rows would report one failure as two; FR-021 wants the
		*kinds* recorded, which they are, and FR-022 wants the rate, which is a rate of
		defects."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="the total is wrong", by="op"
		)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.HOTFIX, defect="the total is wrong", by="op"
		)

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L3)

		assert row.escapes == 1, "two events, one defect"
		assert len(await service.escapes(report_id)) == 2, "both events are still recorded"

	async def test_two_distinct_defects_are_two_escapes(self, home: Path, tmp_path: Path) -> None:
		"""The control arm: distinct defects are distinct failures however they are spelled."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="the total is wrong", by="op"
		)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.INCIDENT, defect="the page is blank", by="op"
		)

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L3)

		assert row.escapes == 2
		assert row.rate == 2.0

	async def test_an_escape_in_another_lane_does_not_count_here(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The lane is what attributes a defect. A rate that counted every escape against
		every lane would make the per-lane axis FR-022 asks for meaningless."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L1, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L3)

		assert row.escapes == 0
		assert row.rate == 0.0


# --------------------------------------------------------------------------- #
# FR-023's reduction
# --------------------------------------------------------------------------- #


class TestTheReduction:
	async def test_over_budget_lowers_the_ceiling_one_level(
		self, home: Path, tmp_path: Path
	) -> None:
		"""§5.4's own modifier unit is "-1 level": the ladder is ordinal and the spec supplies
		no other quantum, so a larger step would be an invented policy."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L3)

		assert row.over_budget is True
		assert row.granted_ceiling is MODULE_CLASS_CEILING[AT_L3]
		assert row.reduced_ceiling == AutonomyLevel(row.granted_ceiling - 1)
		assert row.reduced is True
		assert row.reduced_by_fr_023 is True

	async def test_a_lane_already_at_l0_is_not_lowered_further(
		self, home: Path, tmp_path: Path
	) -> None:
		"""G7 is L1 by class, so FR-023 lowers it to L0 and stops. A reduction that went below
		the floor would be a level the ladder does not have."""
		assert MODULE_CLASS_CEILING[AT_L1] is AutonomyLevel.L1
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L1)
		await service.record_escape(
			report_id, lane=AT_L1, kind=EscapeKind.INCIDENT, defect="secrets leaked", by="op"
		)

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L1)

		assert row.reduced_ceiling is AutonomyLevel.L0
		assert row.reduced is True

	async def test_the_reduction_lifts_when_the_rate_returns(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-023 says "reduced **until** escape rate returns to budget", so the reduction is a
		function of the *current* rate and not a ratchet. A second, clean deployment halves a
		rate of 1.0 to 0.5, which is under a budget of 0.6."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.6, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)
		over = await service.escape_report()
		assert next(row for row in over.lanes if row.lane is AT_L3).over_budget is True

		state = await service.state()
		second_root = tmp_path / "second"
		second_root.mkdir()
		second = await service.render_delivery(state.plans[-1].id, root=second_root)
		await service.approve_deploy(second.id, by="operator")

		under = await service.escape_report()
		row = next(lane for lane in under.lanes if lane.lane is AT_L3)

		assert row.rate == 0.5
		assert row.over_budget is False
		assert row.reduced_ceiling is row.granted_ceiling
		assert row.reduced is False

	async def test_an_unbudgeted_lane_is_not_reduced_and_is_named(
		self, home: Path, tmp_path: Path
	) -> None:
		"""NFR-024 forbids reporting a target the product has not measured, so there is no
		default threshold and an undeclared lane is *unbudgeted* rather than bounded at zero.
		The honest treatment is to name the gap, not to guess a number."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L1, kind=EscapeKind.INCIDENT, defect="secrets leaked", by="op"
		)

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L1)

		assert row.budget is None
		assert row.over_budget is None, "unbudgeted is not within budget"
		assert row.reduced_ceiling is row.granted_ceiling
		assert row.reduced is False
		assert AT_L1 in report.unbudgeted

	def test_lane_ceiling_is_pure_and_its_two_boundaries_hold(self) -> None:
		"""Called directly, because the two boundaries are the requirement's own words and a
		service-level test would only reach the ones a fixture happens to trip."""
		budget = EscapeBudget(lane=AT_L3, maximum_rate=0.0, declared_by="the operator")
		granted = MODULE_CLASS_CEILING[AT_L3]

		assert lane_ceiling(AT_L3, rate=0.0, budget=budget) is granted, "at budget is not over"
		assert lane_ceiling(AT_L3, rate=1.0, budget=None) is granted, "unbudgeted is unchanged"
		assert lane_ceiling(AT_L3, rate=1.0, budget=budget) == AutonomyLevel(granted - 1)


# --------------------------------------------------------------------------- #
# FR-023's override
# --------------------------------------------------------------------------- #


class TestTheOverride:
	async def test_an_override_lifts_the_reduction_and_names_who_accepted_it(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-023's "manual override must be logged and attributed". The override lifts the
		reduction — otherwise it does nothing — and the row names the human, because an
		override with nobody attached is the silent downgrade FR-031 forbids."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)

		await service.record_escape_override(
			AT_L3, by="the duty officer", reason="the fix is scheduled for Friday"
		)

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L3)

		assert row.over_budget is True, "the measurement is not erased by the acceptance"
		assert row.rate == 1.0
		assert row.reduced_ceiling is row.granted_ceiling
		assert row.reduced is False
		assert row.reduced_by_fr_023 is False
		assert row.override is not None
		assert row.override.accepted_by == "the duty officer"
		assert row.override.reason == "the fix is scheduled for Friday"

	async def test_the_override_is_a_ledger_row_rather_than_a_render_parameter(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-031's override is threaded into one render; FR-023's reduction *persists*, so the
		acceptance that lifts it must persist too. A parameter would evaporate at the next
		render and silently restore the reduction the operator had already weighed."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)
		await service.record_escape_override(AT_L3, by="the duty officer", reason="Friday")

		state = await service.state()
		second_root = tmp_path / "second"
		second_root.mkdir()
		second = await service.render_delivery(state.plans[-1].id, root=second_root)

		assert second.escapes is not None
		row = next(lane for lane in second.escapes.lanes if lane.lane is AT_L3)
		assert row.override is not None, "a second render still sees the acceptance"
		assert row.reduced_ceiling is row.granted_ceiling

	async def test_only_the_latest_override_is_in_force(self, home: Path, tmp_path: Path) -> None:
		"""Latest per lane, the rule `gate_cost` states: two overrides of one lane are a
		decision and a revision of it rather than two decisions."""
		service, _, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape_override(AT_L3, by="first", reason="one")
		await service.record_escape_override(AT_L3, by="second", reason="two")

		state = await service.state()

		latest = state.latest_escape_override(AT_L3)
		assert latest is not None
		assert latest.accepted_by == "second"
		assert len(state.escape_overrides) == 2, "the history stays in the log"

	async def test_an_override_with_nobody_attached_cannot_be_constructed(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The type refuses it, so `record_escape_override` cannot be reached around."""
		from pydantic import ValidationError

		with pytest.raises(ValidationError):
			EscapeOverride(
				lane=AT_L3,
				accepted_by="   ",
				reason="because",
				recorded_at=__import__("sofact.views", fromlist=["now"]).now(),
			)

	async def test_an_override_of_one_lane_does_not_lift_another(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Attribution is per lane, so accepting a risk in one lane cannot quietly raise
		another's ceiling."""
		service, report_id, _ = await with_budget(home, tmp_path, 0.0, AT_L3)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)
		await service.record_escape_override(AT_L1, by="someone", reason="elsewhere")

		report = await service.escape_report()
		row = next(lane for lane in report.lanes if lane.lane is AT_L3)

		assert row.override is None
		assert row.reduced_ceiling == AutonomyLevel(MODULE_CLASS_CEILING[AT_L3] - 1)


# --------------------------------------------------------------------------- #
# the vacuous pass, and the derived band
# --------------------------------------------------------------------------- #


class TestAnEmptyMeasurementClaimsNothing:
	async def test_zero_deployments_discharges_nothing(self, home: Path, tmp_path: Path) -> None:
		"""A rate over zero deployments claims nothing. A screen showing "0 escapes" over it
		would report the absence of a measurement as a clean bill of health — the rule
		`OracleAuditReport.discharged` states one phase earlier."""
		service = synthetic_service(home, tmp_path, "complete")
		report = await service.escape_report()

		assert report.deployed_changes == 0
		assert report.lanes == ()
		assert report.discharged == ()
		assert report.not_implemented == ("FR-021", "FR-022", "FR-023")

	async def test_a_deployment_that_held_discharges_all_three(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The control arm: the same type over a real deployment carries the requirements."""
		service, _, _ = await deployed_service(home, tmp_path)
		report = await service.escape_report()

		assert report.deployed_changes >= 1
		assert report.discharged == ("FR-021", "FR-022", "FR-023")
		assert report.not_implemented == ()


class TestTheBandIsDerivedNotStored:
	async def test_the_oracle_rank_comes_from_the_change_s_own_contract(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-021 asks an escape be recorded against "its oracle-strength band". Storing it
		would freeze the number in force on the day; deriving it means a re-measured contract
		is judged at the strength it now carries, which is what FR-023 reads."""
		service, _, contract_id = await deployed_service(home, tmp_path)
		state = await service.state()
		contract = next(c for c in state.contracts if c.id == contract_id)

		report = await service.escape_report()

		for row in report.lanes:
			assert row.oracle_ranks == (contract.weakest_oracle_rank,)

	async def test_the_band_moves_when_the_contract_is_re_measured(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The property the choice buys. `measure_escapes` takes the contracts it is given, so
		a contract carrying a weaker oracle than the one on the log changes the band without
		any escape row being rewritten."""
		service, _, contract_id = await deployed_service(home, tmp_path)
		state = await service.state()
		contract = next(c for c in state.contracts if c.id == contract_id)
		weakened = contract.model_copy(update={"clauses": contract.clauses[:-1]})

		measured = measure_escapes(
			deploys=state.deploys,
			reports=state.deliveries,
			decompositions=state.decompositions,
			escapes=(),
			contracts=(weakened,),
		)
		replaced = measure_escapes(
			deploys=state.deploys,
			reports=state.deliveries,
			decompositions=state.decompositions,
			escapes=(),
			contracts=(),
		)

		assert all(row.oracle_ranks for row in measured.lanes)
		assert all(row.oracle_ranks == () for row in replaced.lanes), (
			"a lane whose contract the log does not hold reports no band rather than a guess"
		)

	async def test_the_band_is_stated_on_the_report_as_a_caveat(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The choice is stated so a reader does not have to infer it from the absence of a
		field."""
		service, _, _ = await deployed_service(home, tmp_path)
		report = await service.escape_report()

		assert any("derived at read time" in caveat for caveat in report.caveats)
		assert any("cannot be gamed at all" in caveat for caveat in report.caveats)


# --------------------------------------------------------------------------- #
# the property FR-022 is actually about
# --------------------------------------------------------------------------- #


class TestNoProducerAuthorsAnInput:
	async def test_the_fold_reads_only_deploys_and_operator_rows(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-022's claim is that the rate "cannot be gamed by the producer because it is
		measured by events the producer does not author". The check is structural: the fold's
		inputs are deploy records, delivery reports, decompositions and the two operator rows
		— and nothing on the factory's verification path writes any of them."""
		service, report_id, _ = await deployed_service(home, tmp_path)
		await service.record_escape(
			report_id, lane=AT_L3, kind=EscapeKind.REVERT, defect="it broke", by="operator"
		)
		state = await service.state()

		before = await service.escape_report()

		# Everything a producer's run touches: dispatch, integrity, verdicts, repairs.
		await service.check_integrity(state.plans[-1].id)
		after = await service.escape_report()

		assert [row.rate for row in after.lanes] == [row.rate for row in before.lanes]
		assert after.deployed_changes == before.deployed_changes

	async def test_the_report_states_its_own_limit(self, home: Path, tmp_path: Path) -> None:
		"""The honest limit, which is a *different* claim from FR-022's and must not be
		conflated with it: a producer cannot inflate the rate, but an operator who does not
		record an escape lowers it, and no code can prevent that."""
		service, _, _ = await deployed_service(home, tmp_path)
		report = await service.escape_report()

		assert any("operator records escapes" in caveat for caveat in report.caveats)


# --------------------------------------------------------------------------- #
# the config seam
# --------------------------------------------------------------------------- #


class TestTheDeclaredBudgetComesFromAFile:
	def test_a_bare_object_of_lanes_is_accepted(self, tmp_path: Path) -> None:
		path = tmp_path / "budget.json"
		path.write_text('{"G4": {"maximum_rate": 0.25, "declared_by": "the CTO"}}')

		budgets = load_escape_budget(path)

		assert budgets == (
			EscapeBudget(lane=ModuleClass.G4, maximum_rate=0.25, declared_by="the CTO"),
		)

	def test_the_same_object_under_a_key_is_accepted(self, tmp_path: Path) -> None:
		path = tmp_path / "budget.json"
		path.write_text('{"escape_budget": {"G7": {"maximum_rate": 0.0}}}')

		budgets = load_escape_budget(path)

		assert budgets[0].lane is ModuleClass.G7
		assert budgets[0].maximum_rate == 0.0
		assert budgets[0].declared_by.endswith("budget.json"), "the file declares it by default"

	def test_an_unknown_lane_is_refused_not_ignored(self, tmp_path: Path) -> None:
		"""A misspelled lane would read as configured while bounding nothing."""
		path = tmp_path / "budget.json"
		path.write_text('{"G9": {"maximum_rate": 0.1}}')

		with pytest.raises(ValueError, match=r"not a .14 lane class"):
			load_escape_budget(path)

	def test_an_unknown_field_is_refused(self, tmp_path: Path) -> None:
		"""A misspelled field would otherwise be ignored and the budget would read as declared
		while bounding what it always did."""
		path = tmp_path / "budget.json"
		path.write_text('{"G4": {"maximum-rate": 0.1}}')

		with pytest.raises(ValueError, match="not a budget field"):
			load_escape_budget(path)

	def test_a_lane_with_no_rate_is_refused(self, tmp_path: Path) -> None:
		"""FR-023 reduces a lane over a *rate*, and a lane with no rate is unbudgeted rather
		than bounded at zero."""
		path = tmp_path / "budget.json"
		path.write_text('{"G4": {"declared_by": "someone"}}')

		with pytest.raises(ValueError, match="declares no maximum_rate"):
			load_escape_budget(path)

	def test_an_empty_file_is_refused(self, tmp_path: Path) -> None:
		"""A file that declares no lanes would read as configured while reducing nothing."""
		path = tmp_path / "budget.json"
		path.write_text("{}")

		with pytest.raises(ValueError, match="no lanes"):
			load_escape_budget(path)

	def test_an_unreadable_file_is_a_message_not_a_traceback(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="cannot read escape budget"):
			load_escape_budget(tmp_path / "absent.json")

	def test_a_rate_outside_zero_to_one_is_refused(self, tmp_path: Path) -> None:
		"""The type's own guard, reached through the loader: nothing outside 0.0-1.0 is a
		share of deployments."""
		path = tmp_path / "budget.json"
		path.write_text('{"G4": {"maximum_rate": 1.5}}')

		with pytest.raises(ValueError):
			load_escape_budget(path)


# --------------------------------------------------------------------------- #
# the report the delivery carries
# --------------------------------------------------------------------------- #


class TestTheDeliveryCarriesTheMeasurement:
	async def test_a_configured_budget_puts_the_measurement_on_the_report(
		self, home: Path, tmp_path: Path
	) -> None:
		"""`DeliveryReport.escapes` is a field rather than a property so the report stays
		readable from the log alone, for `topology`'s reason.

		Measured on the *second* delivery, because the first one's own render happens before
		it is deployed — the denominator is deployed reports, and at that instant there are
		none. That is the stated limit rather than a defect: a report describes the log at
		the moment it is rendered, so a measurement appears from the second delivery on.
		"""
		service, _, _ = await with_budget(home, tmp_path, 0.5, AT_L3)
		state = await service.state()
		second_root = tmp_path / "second"
		second_root.mkdir()
		second = await service.render_delivery(state.plans[-1].id, root=second_root)

		assert second.escapes is not None
		assert {row.lane for row in second.escapes.lanes}

	async def test_the_first_delivery_carries_a_measurement_over_no_deployments(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The stated limit, asserted rather than left implicit: the first report's own render
		precedes its deploy, so its escape table has no denominator and claims nothing."""
		service, _, _ = await with_budget(home, tmp_path, 0.5, AT_L3)
		state = await service.state()
		first = state.deliveries[0]

		assert first.escapes is not None, "the deployment declared a budget"
		assert first.escapes.deployed_changes == 0
		assert first.escapes.lanes == ()
		assert first.escapes.discharged == ()

	async def test_an_unconfigured_deployment_reports_no_measurement(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``None`` means the deployment configured no escape budget — which the report prints
		as a sentence rather than an empty table that reads as compliance."""
		service, _, _ = await deployed_service(home, tmp_path)
		state = await service.state()

		assert state.deliveries[-1].escapes is None

	async def test_the_delivery_and_its_escape_table_share_one_instant(
		self, home: Path, tmp_path: Path
	) -> None:
		"""One report, one timestamp. A table stamped with the moment it was folded would date
		a delivery's own evidence to a different second than the delivery, and `rendered_at`
		is what pins the report's identity for FR-117's versioning."""
		service, _, _ = await with_budget(home, tmp_path, 0.5, AT_L3)
		state = await service.state()
		report = state.deliveries[-1]

		assert report.escapes is not None
		assert report.escapes.rendered_at == report.rendered_at
