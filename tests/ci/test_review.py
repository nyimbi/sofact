"""§20.3 item 3's per-diff half: what reviewing one sealed diff cost.

FR-160 records what a *gate* cost; §20.3 item 3 asks for the same number per *diff* as
well, "so §1.4's claim can be compared directly against the v0.1 alternative". §1.4's
claim is that human attention is spent per platform rather than per module, and the
alternative it must beat is v0.1's per-diff review at roughly four units an hour.

The tests below hold the four things that decide whether the number is worth having:

- a review attaches to a dispatch that actually **sealed a diff**, and the reviewed
  commit is taken from the dispatch rather than asked for;
- the diff, not the step, is the key — a step can be dispatched twice and each dispatch
  seals its own commit, so keying by step would understate review time;
- the total is over the **latest** review per dispatch, so a diff reviewed twice is one
  diff and the denominator does not inflate;
- coverage travels with the mean, because §1.4's claim wants per-module attention to
  look small and a mean over the reviewed subset reports exactly that.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from synthetic import plan_and_service
from typer.testing import CliRunner

from sofact._uuid7 import uuid7str
from sofact.cli import app
from sofact.service import FactoryService
from sofact.views import (
	EVOLVABILITY_DEBT,
	MODE_M_CEILING,
	THETA_GATE_BUILT,
	V01_REVIEW_MINUTES_PER_DIFF,
	AutonomyLevel,
	DeliveryEnvelope,
	DiffReview,
	EnvelopeDimension,
	LedgerKind,
	Phase,
	PhaseGate,
	PhaseStatus,
)

RUNNER = CliRunner()


def a_review(*, human_minutes: float = 10.0, rework_fraction: float = 0.0) -> DiffReview:
	"""One review, built directly so the type's own guards can be exercised alone."""
	return DiffReview(
		dispatch_id=uuid7str(),
		step_id=uuid7str(),
		sealed_commit="a" * 40,
		human_minutes=human_minutes,
		rework_fraction=rework_fraction,
		reviewed_by="operator",
		reviewed_at=datetime.now(UTC),
	)


async def reviewed_service(
	home: Path, tmp_path: Path, *, dispatches: int = 1
) -> tuple[FactoryService, str, list[str]]:
	"""A service with real sealed diffs, and the dispatch ids that sealed them.

	``writes-work`` is the mode that matters: a producer that leaves real work in the
	tree is the only one a seal can be distinguished on, and a review needs a sealed
	commit to attach to (§20.3 item 3).

	Distinct *steps* rather than repeated dispatches of one, because the producer writes
	the same content on a second run: ``seal_branch`` then finds nothing changed, and the
	second diff does not exist. A fixture that forced one would be measuring the fixture.
	"""
	service, plan = await plan_and_service(
		home, tmp_path, "writes-work-complete-writes-module", commands="true"
	)
	await service.dispatch_plan(plan.id, max_steps=dispatches)
	state = await service.state()
	sealed = [
		d.id
		for d in state.dispatches
		if d.checkout is not None and d.checkout.sealed_commit is not None
	]
	assert len(sealed) >= dispatches, (
		f"the fixture sealed {len(sealed)} diff(s) for {dispatches} step(s), so nothing "
		"below is under test"
	)
	return service, plan.id, sealed


class TestADiffReviewIsAskedFor:
	"""§20.3 item 3: nothing observes a person reading, so the number is asked for."""

	async def test_a_review_records_against_the_diff_that_was_sealed(
		self, home: Path, tmp_path: Path
	) -> None:
		service, _, sealed = await reviewed_service(home, tmp_path)
		dispatch_id = sealed[0]
		record = await service.state()
		dispatched = record.dispatch(dispatch_id)
		assert dispatched is not None and dispatched.checkout is not None

		review = await service.record_diff_review(
			dispatch_id, human_minutes=22.0, rework_fraction=0.3, by="operator"
		)

		assert review.dispatch_id == dispatch_id
		assert review.step_id == dispatched.step_id
		assert review.sealed_commit == dispatched.checkout.sealed_commit, (
			"the reviewed commit is taken from the dispatch, so a review cannot name a "
			"diff the factory did not seal"
		)
		assert review.human_minutes == 22.0
		assert review.rework_fraction == 0.3
		assert await service.diff_reviews() == (review,)

	async def test_a_review_of_a_dispatch_that_sealed_nothing_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A session that changed nothing is not a diff a human could have read.

		This is ``record_gate_cost``'s refusal one requirement along: a review recorded
		against a diff that never existed is a measurement of a sitting that never
		happened, and it would let the per-diff total be assembled from nothing.
		"""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="true")
		await service.dispatch_plan(plan.id, max_steps=1)
		state = await service.state()
		unsealed = [
			d.id for d in state.dispatches if d.checkout is None or d.checkout.sealed_commit is None
		]
		assert unsealed, "the fixture sealed something, so the refusal is not under test"

		with pytest.raises(ValueError, match="sealed no commit"):
			await service.record_diff_review(
				unsealed[0], human_minutes=10.0, rework_fraction=0.0, by="operator"
			)

		assert await service.diff_reviews() == ()

	async def test_an_unknown_dispatch_is_refused(self, home: Path, tmp_path: Path) -> None:
		service, _, _ = await reviewed_service(home, tmp_path)

		with pytest.raises(ValueError, match="no dispatch"):
			await service.record_diff_review(
				"01HZZZZZZZZZZZZZZZZZZZZZZZ",
				human_minutes=10.0,
				rework_fraction=0.0,
				by="operator",
			)

	async def test_a_negative_minute_is_refused_at_the_type(self) -> None:
		"""A negative cost would lower the per-diff total §1.4's claim is read against,
		which is the one direction a measurement of the binding constraint must not move."""

		with pytest.raises(ValueError, match="negative cost"):
			a_review(human_minutes=-5.0)

	async def test_a_fraction_outside_the_unit_interval_is_refused(self) -> None:

		with pytest.raises(ValueError, match="not a share"):
			a_review(rework_fraction=1.4)


class TestTheReviewAttachesToTheDiffNotTheStep:
	"""A step can be dispatched more than once, and each dispatch seals its own commit.

	Keying a review by step would collapse two reviewable diffs into one and understate
	review time — the one direction §1.4's claim must not be able to move.
	"""

	async def test_two_dispatches_of_one_step_each_carry_their_own_review(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The log is the authority here, and it is the honest place to test it.

		Driving two real dispatches of one step is not reliable: the producer writes the
		same content on the second run, ``seal_branch`` finds nothing changed, and the
		second diff does not exist — so a fixture that produced one would be measuring
		the fixture. What matters is the *key*, and the key is exercised by folding two
		dispatch rows of one step and reviewing both.
		"""
		service, _, sealed = await reviewed_service(home, tmp_path)
		first = sealed[0]
		state = await service.state()
		original = state.dispatch(first)
		assert original is not None and original.checkout is not None
		second = original.model_copy(
			update={
				"id": uuid7str(),
				"checkout": original.checkout.model_copy(update={"sealed_commit": "b" * 40}),
			}
		)
		# ``_commit`` rather than ``ledger.append``: it invalidates the derived-state
		# cache, and without that the ``state()`` below folds a stale ``ProjectState``
		# and the second dispatch is invisible. Reaching a private member is the point
		# of the test, not an accident of it, so the ignore is stated rather than the
		# call routed around -- ``test_delivery`` reaches ``_repository_of`` the same way.
		service._commit(  # pyright: ignore[reportPrivateUsage]
			LedgerKind.STEP_DISPATCHED, {"dispatch": second.model_dump(mode="json")}
		)
		state = await service.state()
		assert {d.step_id for d in state.dispatches} == {original.step_id}, (
			"this test needs two dispatches of one step"
		)

		await service.record_diff_review(
			first, human_minutes=20.0, rework_fraction=0.0, by="operator"
		)
		await service.record_diff_review(
			second.id, human_minutes=30.0, rework_fraction=0.0, by="operator"
		)

		state = await service.state()
		assert state.reviewed_minutes == 50.0, (
			"two diffs of one step are two diffs to read, and collapsing them by step "
			"would understate the review cost"
		)
		assert len(state.latest_reviews) == 2
		assert state.review_for(first).sealed_commit != state.review_for(second.id).sealed_commit  # type: ignore[union-attr]

	async def test_a_diff_reviewed_twice_is_counted_once(self, home: Path, tmp_path: Path) -> None:
		"""Two recordings of one diff are two measurements, not two diffs.

		The log keeps both — the history of what was first claimed is itself part of what
		§20.3 is measuring — but the total reads the latest per dispatch, or a diff
		reviewed twice would inflate the denominator of the comparison §1.4 rests on.
		"""
		service, _, sealed = await reviewed_service(home, tmp_path)
		dispatch_id = sealed[0]
		await service.record_diff_review(
			dispatch_id, human_minutes=40.0, rework_fraction=0.5, by="operator"
		)
		await service.record_diff_review(
			dispatch_id, human_minutes=15.0, rework_fraction=0.1, by="operator"
		)

		state = await service.state()
		assert len(state.reviews) == 2, "both sittings stay in the log"
		assert state.reviewed_minutes == 15.0, "the latest measurement of the one diff"
		assert len(state.latest_reviews) == 1
		assert state.review_for(dispatch_id) is not None
		assert state.review_for(dispatch_id).human_minutes == 15.0  # type: ignore[union-attr]


class TestCoverageIsCarriedBesideTheMean:
	"""§1.4's claim wants per-module attention to look small.

	A mean over the diffs somebody chose to review reports exactly that while the rest
	were read by nobody, so the coverage pair travels with the mean.
	"""

	async def test_the_coverage_pair_counts_reviewed_against_sealed(
		self, home: Path, tmp_path: Path
	) -> None:
		service, _, sealed = await reviewed_service(home, tmp_path, dispatches=3)
		await service.record_diff_review(
			sealed[0], human_minutes=20.0, rework_fraction=0.0, by="operator"
		)

		state = await service.state()
		reviewed, total = state.review_coverage  # type: ignore[misc]
		assert reviewed == 1
		assert total >= 3, "every sealed diff is in the denominator, reviewed or not"
		assert reviewed < total, "the fixture must leave some diffs unreviewed"

	async def test_the_report_states_the_coverage_beside_the_mean(
		self, home: Path, tmp_path: Path
	) -> None:
		service, plan_id, sealed = await reviewed_service(home, tmp_path, dispatches=2)
		await service.record_diff_review(
			sealed[0], human_minutes=24.0, rework_fraction=0.2, by="operator"
		)

		report = await service.render_delivery(plan_id)

		check = next(c for c in report.checks if c.name == "diff_review_reported")
		assert check.passed is True, "the check reports; it does not gate the deploy"
		reviewed, total = report.review_coverage  # type: ignore[misc]
		assert (reviewed, total) == (1, report.sealed_dispatches)
		assert total > reviewed, "the fixture must leave diffs nobody read"
		assert f"Coverage: {reviewed} of {total} sealed diff(s)" in check.detail, check.detail
		assert "mean 24.0" in check.detail, check.detail
		assert "v0.1" in check.detail, check.detail
		assert f"{V01_REVIEW_MINUTES_PER_DIFF:g} minutes a diff" in check.detail, check.detail
		assert "not the whole review cost" in check.detail, check.detail


class TestUnmeasuredIsNotFree:
	"""``None`` is a different statement from zero, for ``total_human_minutes``' reason.

	A factory that reported 0 minutes here would be reporting that its diffs were free
	to read.
	"""

	async def test_no_review_reports_unmeasured_rather_than_zero(
		self, home: Path, tmp_path: Path
	) -> None:
		service, _, _ = await reviewed_service(home, tmp_path)
		state = await service.state()

		assert state.reviewed_minutes is None
		assert state.mean_diff_rework is None
		assert await service.diff_reviews() == ()

	async def test_nothing_sealed_reports_no_coverage_rather_than_a_zero_pair(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``(0, 0)`` would read as a project that reviewed nothing; it is a project that
		produced nothing to review, which is a different fact (NFR-024)."""
		service, plan = await plan_and_service(home, tmp_path, "complete", commands="true")
		await service.dispatch_plan(plan.id, max_steps=1)

		state = await service.state()
		assert state.review_coverage is None

	async def test_an_unreviewed_project_says_so_in_the_report(
		self, home: Path, tmp_path: Path
	) -> None:
		service, plan_id, _ = await reviewed_service(home, tmp_path)

		report = await service.render_delivery(plan_id)

		check = next(c for c in report.checks if c.name == "diff_review_reported")
		assert check.passed is True
		assert "unmeasured rather than zero" in check.detail, check.detail
		assert "sofact review" in check.detail, check.detail
		assert report.diff_rework_fraction is None


class TestTheComparisonIsAReading:
	"""§20.3 item 3 says "compared directly"; it does not say a verdict is rendered.

	The check names v0.1's rate and states both totals, and it raises no ceiling — the
	precedent every unmeasured or proxy number in this repo follows (NFR-024).
	"""

	async def test_the_check_names_the_v01_alternative_and_the_gate_total(
		self, home: Path, tmp_path: Path
	) -> None:
		service, plan_id, sealed = await reviewed_service(home, tmp_path)
		await service.record_diff_review(
			sealed[0], human_minutes=18.0, rework_fraction=0.0, by="operator"
		)

		report = await service.render_delivery(plan_id)

		check = next(c for c in report.checks if c.name == "diff_review_reported")
		assert "four units an hour" in check.detail, check.detail
		# The figure comes from ``V01_REVIEW_MINUTES_PER_DIFF`` rather than from the
		# sentence, so this asserts the number and not the prose that spells it.
		assert f"{V01_REVIEW_MINUTES_PER_DIFF:g} minutes a diff" in check.detail, check.detail
		assert "population" in check.detail, (
			"a single project's log cannot settle §1.4 either way, and the check must say "
			"so rather than implying the comparison is a verdict"
		)

	async def test_the_check_names_both_totals_for_r13(self, home: Path, tmp_path: Path) -> None:
		"""§21 R13 asks for gate-minutes against diff-minutes, and both must be readable
		from the report a deploy gate approves — not only from the terminal screen where
		the two headings happen to sit adjacent.

		R13's failure mode is integration risk growing as n² while human attention stays
		flat, which is fatal to the business case; the comparison that would refute it
		cannot live in a screen nobody archived.
		"""
		service, plan_id, sealed = await reviewed_service(home, tmp_path)
		# A gate cost attaches only to a gate that was passed, because a cost for a gate
		# nobody sat at is the measurement GateCost refuses (FR-160) — so the two phases
		# before the specification gate are completed and that gate is passed first.
		await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
		await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
		await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE)
		await service.approve_gate(Phase.SPECIFY, by="operator")
		await service.record_gate_cost(
			PhaseGate.SPECIFICATION, human_minutes=90.0, rework_fraction=0.25, by="operator"
		)
		await service.record_diff_review(
			sealed[0], human_minutes=18.0, rework_fraction=0.0, by="operator"
		)

		report = await service.render_delivery(plan_id)

		check = next(c for c in report.checks if c.name == "diff_review_reported")
		assert "Gate-minutes 90" in check.detail, check.detail
		assert "diff-minutes 18" in check.detail, check.detail
		assert "R13" in check.detail, check.detail
		assert "rather than divided" in check.detail, (
			"the pair is printed, not turned into a ratio with a verdict"
		)
		assert check.passed is True

	async def test_the_gate_ceiling_is_not_moved_by_a_review(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A measured actual may not raise a bound (ADR-0062, ADR-0043 decision 5)."""
		service, plan_id, sealed = await reviewed_service(home, tmp_path)
		await service.record_diff_review(
			sealed[0], human_minutes=300.0, rework_fraction=1.0, by="operator"
		)

		report = await service.render_delivery(plan_id)

		assert report.autonomy is AutonomyLevel.L2 or report.autonomy.value <= 2
		assert THETA_GATE_BUILT is True, "the gate is built (ADR-0076) and unmoved by a review"
		assert MODE_M_CEILING is AutonomyLevel.L1
		assert EVOLVABILITY_DEBT == 1.0

	async def test_the_diff_minutes_never_enter_the_human_minutes_dimension(
		self, home: Path, tmp_path: Path
	) -> None:
		"""§1.3's ``HUMAN_MINUTES`` is the *per-platform* budget, and FR-160 unblocked it
		for gate costs only. Pooling diff-minutes into it would corrupt the one dimension
		the per-gate instrument exists to fill — a diff is per module and a gate is per
		platform, so the sum would be over two populations (§1.4).
		"""
		service, plan = await plan_and_service(
			home,
			tmp_path,
			"writes-work-complete-writes-module",
			commands="true",
			envelope=DeliveryEnvelope(),
		)
		await service.dispatch_plan(plan.id, max_steps=1)
		state = await service.state()
		sealed = [d.id for d in state.sealed_dispatches]
		assert sealed, "the fixture sealed no diff, so nothing is under test"
		await service.record_diff_review(
			sealed[0], human_minutes=44.0, rework_fraction=0.0, by="operator"
		)

		report = await service.render_delivery(plan.id)

		assert report.envelope_actuals is not None
		measured = {m.dimension: m.actual for m in report.envelope_actuals.measurements}
		assert measured[EnvelopeDimension.HUMAN_MINUTES] is None, (
			"no gate recorded a cost, so the platform budget is unmeasured — and 44 "
			"diff-minutes are not it"
		)
		assert report.reviewed_minutes == 44.0, "the number is carried, just not there"

	async def test_the_number_does_not_become_a_ninth_envelope_dimension(
		self, home: Path, tmp_path: Path
	) -> None:
		"""§1.3 has eight rows. The per-diff number is carried as its own report field,
		as ``rework_fraction`` is carried separately from ``HUMAN_MINUTES``."""
		service, plan_id, sealed = await reviewed_service(home, tmp_path)
		await service.record_diff_review(
			sealed[0], human_minutes=18.0, rework_fraction=0.0, by="operator"
		)

		report = await service.render_delivery(plan_id)

		assert len(EnvelopeDimension) == 8
		if report.envelope_actuals is not None:
			assert all(
				m.dimension in set(EnvelopeDimension) for m in report.envelope_actuals.measurements
			)

	async def test_the_review_reaches_the_ledger_as_its_own_kind(
		self, home: Path, tmp_path: Path
	) -> None:
		service, _, sealed = await reviewed_service(home, tmp_path)
		await service.record_diff_review(
			sealed[0], human_minutes=18.0, rework_fraction=0.0, by="operator"
		)

		kinds = {entry.kind for entry in service.ledger.entries()}
		assert LedgerKind.DIFF_REVIEWED in kinds


class TestTheDiffReviewVerb:
	"""``sofact review`` is the only place the number can enter the log.

	A UUID7 is long enough that typing one is a chore, and a verb that is a chore is one
	an operator stops using — which leaves §20.3 item 3 unmeasured for the reason the
	measurement is inconvenient. So a unique prefix resolves, and an ambiguous one is
	refused by naming the candidates.
	"""

	def test_the_list_names_the_sealed_diffs(self, home: Path, tmp_path: Path) -> None:
		asyncio.run(reviewed_service(home, tmp_path))

		result = RUNNER.invoke(app, ["--home", str(home), "review", "--list"])

		assert result.exit_code == 0, result.output
		assert "sealed diffs" in result.output
		assert "unreviewed" in result.output
		assert "0 of" in result.output, "the coverage pair is what keeps the mean honest"

	def test_a_review_records_by_a_unique_prefix(self, home: Path, tmp_path: Path) -> None:
		_, _, sealed = asyncio.run(reviewed_service(home, tmp_path))
		prefix = sealed[0][:8]

		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"review",
				prefix,
				"--minutes",
				"21",
				"--rework",
				"0.25",
				"--by",
				"nyimbi",
			],
		)

		assert result.exit_code == 0, result.output
		assert "21 human-minute(s)" in result.output
		assert "25% of the diff returned" in result.output
		assert "Traceback" not in result.output

	def test_recording_without_minutes_says_what_is_missing(
		self, home: Path, tmp_path: Path
	) -> None:
		_, _, sealed = asyncio.run(reviewed_service(home, tmp_path))

		result = RUNNER.invoke(app, ["--home", str(home), "review", sealed[0][:8]])

		assert result.exit_code == 1, result.output
		assert "--minutes is required" in result.output
		assert "Traceback" not in result.output

	def test_an_unknown_id_is_refused_with_a_sentence(self, home: Path, tmp_path: Path) -> None:
		asyncio.run(reviewed_service(home, tmp_path))

		result = RUNNER.invoke(app, ["--home", str(home), "review", "deadbeef", "--minutes", "10"])

		assert result.exit_code == 1, result.output
		assert "no sealed diff" in result.output
		assert "Traceback" not in result.output

	def test_the_list_refuses_when_nothing_has_sealed(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "review", "--list"])

		assert result.exit_code == 1, result.output
		assert "nothing to review" in result.output
		assert "Traceback" not in result.output

	def test_an_ambiguous_prefix_names_the_candidates(self, home: Path, tmp_path: Path) -> None:
		"""Refused rather than resolved by taking the first: silently picking one would
		record a review against a diff the operator did not read.

		UUID7 is time-ordered, so two dispatches of one plan share a leading prefix by
		construction — which is exactly the case an operator hits when they copy the
		short form off a listing.
		"""
		_, _, sealed = asyncio.run(reviewed_service(home, tmp_path, dispatches=2))
		first, second = sealed[0], sealed[1]
		shared = 0
		while shared < min(len(first), len(second)) and first[shared] == second[shared]:
			shared += 1
		assert shared >= 4, f"two dispatches share only {shared} characters: {first} {second}"

		result = RUNNER.invoke(
			app, ["--home", str(home), "review", first[:shared], "--minutes", "10"]
		)

		assert result.exit_code == 1, result.output
		assert "sealed diffs:" in result.output, result.output
		assert "Name more of the id" in result.output
		assert "Traceback" not in result.output

	def test_the_full_id_always_resolves(self, home: Path, tmp_path: Path) -> None:
		"""The prefix path must not shadow the exact one: an id that matches another
		dispatch's prefix is still unambiguously itself."""
		_, _, sealed = asyncio.run(reviewed_service(home, tmp_path, dispatches=2))

		result = RUNNER.invoke(app, ["--home", str(home), "review", sealed[0], "--minutes", "12"])

		assert result.exit_code == 0, result.output
		assert "12 human-minute(s)" in result.output
