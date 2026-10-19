"""FR-105: a lane measured below θ_lo is not built at autonomy.

The requirement has two halves and they meet at one seam. The measurement is
:meth:`~sofact.service.FactoryService.measure_oracle_strength`, which records a row; the
refusal is :meth:`~sofact.service.FactoryService._require_lane_above_theta`, which
``dispatch_step`` calls before any session, branch or worktree exists. Neither half is
useful alone — a number nothing acts on is a note, and a refusal with no number is a guess.

Three absences must dispatch unchanged, and each is a test below rather than a comment:
no row at all, a row that does not name the lane, and a lane at *exactly* θ_lo. The first
two are NFR-024 (unmeasured is not zero) and the third is the spec's own word "below".
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from synthetic import plan_and_service

from sofact._uuid7 import uuid7str
from sofact.service import FactoryService
from sofact.views import (
	DEFAULT_THETA,
	GoalPlan,
	LedgerKind,
	OracleStrengthMeasured,
	ProjectState,
	RoutingRefusal,
	ThetaThresholds,
)


def plant_strength(
	service: FactoryService,
	contract_id: str,
	strengths: dict[str, float],
	*,
	thresholds: ThetaThresholds = DEFAULT_THETA,
) -> OracleStrengthMeasured:
	"""Append one measurement row the way ``measure_oracle_strength`` does.

	The row is constructed and committed rather than measured because mutation scoring
	launches a process per mutant and this suite is about what the *interlock* does with a
	number, not about whether the instrument produces one — that is
	``test_mutation.py``'s subject. The commit goes through the same
	``ORACLE_STRENGTH_MEASURED`` kind and payload shape, so the fold is exercised for real.
	"""
	row = OracleStrengthMeasured(
		id=uuid7str(),
		contract_id=contract_id,
		contract_hash="a" * 64,
		measured_at=datetime.now(UTC),
		strengths=strengths,
		thresholds=thresholds,
	)
	service._commit(  # pyright: ignore[reportPrivateUsage]
		LedgerKind.ORACLE_STRENGTH_MEASURED, {"strength": row.model_dump(mode="json")}
	)
	return row


def step_with_module(state: ProjectState, plan: GoalPlan) -> tuple[str, str]:
	"""A step whose clauses one module owns, and that module's name.

	The fixture is chosen rather than hardcoded: the decomposition is derived from the
	contract, and a test that assumed step 3 belonged to module 2 would break the day the
	synthetic goal changed — reporting a bug in the interlock that was a bug in the test.
	"""
	decomposition = state.latest_decomposition(plan.contract_id)
	assert decomposition is not None, "fixture: gated_contract approved a decomposition"
	for step in plan.steps:
		module = decomposition.module_for_clauses(step.clause_ids)
		if module is not None:
			return step.id, module.name
	raise AssertionError("fixture: no step's clauses resolve to exactly one module")


class TestTheInterlock:
	async def test_a_measured_lane_below_theta_is_not_dispatched(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-105's sentence: reported unbuildable-at-autonomy, not built anyway."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		step_id, module = step_with_module(await service.state(), plan)
		plant_strength(service, plan.contract_id, {module: 0.10})
		with pytest.raises(RoutingRefusal) as caught:
			await service.dispatch_step(plan.id, step_id)
		message = str(caught.value)
		assert module in message
		assert "0.100" in message, "the refusal names the number it read"
		assert f"{DEFAULT_THETA.lo:g}" in message, "and the threshold it fell below"
		assert "unbuildable-at-autonomy" in message

	async def test_the_refused_lane_leaves_no_dispatch_row(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A refusal before the session exists is a refusal with nothing to clean up.

		This is the claim the seam was chosen for: the check sits before the adapter, the
		branch and the worktree, so a refused dispatch has not created any of them. A
		refusal *after* the session started would be a failed step wearing a refusal's
		clothes.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		step_id, module = step_with_module(await service.state(), plan)
		plant_strength(service, plan.contract_id, {module: 0.0})
		with pytest.raises(RoutingRefusal):
			await service.dispatch_step(plan.id, step_id)
		state = await service.state()
		assert state.dispatches_for(plan.id) == ()

	async def test_an_unmeasured_project_dispatches_as_before(
		self, home: Path, tmp_path: Path
	) -> None:
		"""NFR-024: a lane nobody scored is not a lane that scored zero."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		step_id, _ = step_with_module(await service.state(), plan)
		record = await service.dispatch_step(plan.id, step_id)
		assert record.outcome.value == "completed"

	async def test_a_row_that_does_not_name_the_lane_does_not_refuse_it(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The instrument declines some lanes; declining is not scoring badly.

		``strengths`` omits a lane whose oracle names no command, whose rank is above the
		covering set, or whose ownership is not exactly one module. A row that is present
		but silent about this module must dispatch it, or FR-105's escalation would fire on
		the instrument's own refusals.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		step_id, module = step_with_module(await service.state(), plan)
		plant_strength(service, plan.contract_id, {"some-other-module": 0.0})
		record = await service.dispatch_step(plan.id, step_id)
		assert record.outcome.value == "completed"
		assert module not in ("some-other-module",)

	async def test_a_lane_exactly_at_theta_lo_dispatches(self, home: Path, tmp_path: Path) -> None:
		"""The spec says "below θ_lo", and θ_lo is the threshold that *admits* L3."""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		step_id, module = step_with_module(await service.state(), plan)
		plant_strength(service, plan.contract_id, {module: DEFAULT_THETA.lo})
		record = await service.dispatch_step(plan.id, step_id)
		assert record.outcome.value == "completed"

	async def test_a_measurement_of_another_contract_does_not_refuse_this_one(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A number is about the tree and oracle set it ran against.

		Keyed by contract for :meth:`ProjectState.latest_oracle_audit`'s reason: a
		re-contracted goal's lanes are different lanes, and an old measurement attached to
		them would refuse work nobody mutated.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete")
		step_id, module = step_with_module(await service.state(), plan)
		plant_strength(service, "01920000-0000-7000-8000-0000000000ff", {module: 0.0})
		record = await service.dispatch_step(plan.id, step_id)
		assert record.outcome.value == "completed"


class TestTheFold:
	"""The instrument scores clauses; FR-105 refuses modules. The join is explicit."""

	def test_a_lane_takes_its_weakest_clause(self) -> None:
		"""A mean would let one well-tested clause carry a lane nothing else checks."""
		folded = OracleStrengthMeasured.from_clauses(
			{"c1": 0.9, "c2": 0.1}, {"c1": "lane", "c2": "lane"}
		)
		assert folded == {"lane": 0.1}

	def test_a_clause_with_no_module_contributes_nothing(self) -> None:
		folded = OracleStrengthMeasured.from_clauses({"c1": 0.9, "c2": 0.1}, {"c1": "lane"})
		assert folded == {"lane": 0.9}

	def test_a_lane_with_no_scored_clause_is_absent_not_zero(self) -> None:
		"""NFR-024 at the join: the row must not invent a zero for a lane it did not score."""
		assert OracleStrengthMeasured.from_clauses({}, {"c1": "lane"}) == {}

	def test_the_thresholds_in_force_at_the_measurement_are_the_ones_applied(self) -> None:
		"""A number is judged by the calibration it met, not by the one in force later."""
		row = OracleStrengthMeasured(
			id=uuid7str(),
			contract_id=uuid7str(),
			contract_hash="a" * 64,
			measured_at=datetime.now(UTC),
			strengths={"lane": 0.5},
			thresholds=ThetaThresholds(hi=0.95, lo=0.4),
		)
		assert row.unbuildable_at_autonomy == ()
		calibrated = row.model_copy(update={"thresholds": ThetaThresholds(hi=0.95, lo=0.6)})
		assert calibrated.unbuildable_at_autonomy == ("lane",)
