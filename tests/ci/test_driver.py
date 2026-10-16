"""FR-172 — the one verb that carries a goal to its gates, and the four it must stop at.

The driver is the only thing in SoFact an operator runs unattended, so what is under test
here is not that it does the work — ``test_service.py`` owns every verb it calls. It is the
three properties that make an unattended run safe to believe:

**It stops at every gate and has no code path that passes one.** FR-061 makes a gate a hard
stop; a driver that could advance one would be a factory approving its own specification.
The tests below walk the pipeline gate by gate, approving from outside the run exactly as
the operator does, and assert that no branch returns ``DELIVERED`` with a gate open.

**It is idempotent, and idempotency is asserted on the ledger's length.** Every step checks
the log before acting. An outcome comparison passes when the second run silently redoes the
work and lands on the same answer, so the assertion is on what got appended.

**Terminal state is reported, never assumed.** ``claims_built`` is true for ``DELIVERED``
alone, the notification subject is composed from it, and a run that stopped at a gate is
never told it built anything.

The harness is ``tests/ci/synthetic.py``'s real child-process script, driven with
``harness="synthetic"`` and ``research_harness="synthetic"`` — the two names are separate
because P1 and P5 dispatch to different specs, and a table with one entry per name is the
smallest configuration that exercises both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sofact.driver import DRIVER_ACTIONS, DriverRefusal, run_goal
from sofact.notify import render_subject
from sofact.service import FactoryService
from sofact.views import (
	PHASE_GATE,
	Assumption,
	DriverOutcome,
	DriverRun,
	DriverTerminal,
	Phase,
	PhaseStatus,
	ValueHypothesis,
)
from sofact._uuid7 import uuid7str

from conftest import answer_everything
from synthetic import a_model_for, synthetic_service

HARNESS = "synthetic"


def deliver_root(tmp_path: Path) -> Path:
	"""Where a walk writes its delivery artefacts.

	Passed explicitly because ``artifact()`` reads presence off the filesystem: with no
	root, ``DELIVERY.md`` and ``RUNBOOK.md`` are recorded missing and P8's
	``delivery_artifacts`` check fails, which is a fact about the *call* rather than about
	the delivery. The driver's ``root`` is that argument.
	"""
	root = tmp_path / "delivery"
	root.mkdir(parents=True, exist_ok=True)
	return root


async def a_goal(service: FactoryService, statement: str = "Ship a reminder dashboard.") -> str:
	"""Open a goal and answer the interrogation, so the driver has work it can do."""
	goal = await service.start(statement)
	await answer_everything(service, goal.id)
	return goal.id


async def operator_specify(service: FactoryService, goal_id: str) -> None:
	"""Supply the three operator halves P2's machine checks require (FR-078/079/085).

	``specify`` is the phase's own verb and this is what running it means: the model, an
	assumption with its refutation, and a value hypothesis with its instrument. A driver
	run cannot produce these — they are the operator's artefacts — so the walk supplies
	them the way the operator does, between runs.
	"""
	state = await service.state()
	contract = state.latest_contract(goal_id)
	assert contract is not None, "the walk asked for a specification before a contract"
	await service.specify(
		contract.id,
		system_model=a_model_for(contract),
		assumptions=(
			Assumption(
				id=uuid7str(),
				statement="Reminders are scheduled by the client, not by the server.",
				refuted_by="A server-side scheduler process appearing in the deployment.",
			),
		),
		value_hypothesis=ValueHypothesis(
			effect="Operators stop missing scheduled reminders.",
			beneficiary="The end user reading the dashboard.",
			refuting_instrument="Dashboard session logs showing reminders read late.",
		),
	)


async def run(
	service: FactoryService,
	root: Path,
	*,
	notify: bool = False,
) -> DriverRun:
	"""One driver invocation against the synthetic table.

	``notify`` defaults to off here because the notifier is ``test_notify.py``'s subject
	and a table with none configured records a row saying so — which is the right default
	for a deployment and noise in a test about the walk.
	"""
	return await run_goal(
		service,
		root=root,
		notify=notify,
		harness=HARNESS,
		research_harness=HARNESS,
	)


async def walk(service: FactoryService, root: Path) -> tuple[DriverRun, list[Phase]]:
	"""Drive to the end, approving each gate from outside the run, as the operator does.

	Returns the final run and the gates it stopped at, in order. The approval loop lives
	here rather than in each test because it *is* the operator's side of the protocol: the
	driver has no code path that passes a gate, so every walk to a delivery is this loop.

	The bound is a guard rather than an expectation — four gates, and a walk that needed
	more would be a driver re-entering a phase, which is the defect worth failing on
	rather than looping until the suite times out.
	"""
	goal = await service.current_goal()
	assert goal is not None, "a walk needs a goal"
	goal_id = goal.id
	seen: list[Phase] = []
	run_result = await run(service, root)
	for _ in range(2 * len(PHASE_GATE) + 2):
		if run_result.open_gate is None:
			return run_result, seen
		assert not run_result.claims_built, "a run at a gate may not claim a build"
		seen.append(run_result.open_gate)
		if run_result.gate_failures:
			await operator_specify(service, goal_id)
		await service.approve_gate(run_result.open_gate, by="operator")
		run_result = await run(service, root)
	raise AssertionError(f"the walk did not terminate; it stopped at {seen}")  # pragma: no cover


class TestTheDriverStopsAtEveryGate:
	"""Four gates, four stops, and the run is resumed from the ledger rather than waited on."""

	async def test_a_run_with_no_goal_is_refused_rather_than_recorded(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The one stopping condition that writes no row, and the reason it does not.

		``DriverRun.goal_id`` is required because a run is a run *of* something. Recording
		one against no goal would force the field optional and make every later reader
		handle a driver run that belongs to nothing — so there is no machine work to report
		and no run to name, and the operator gets a sentence.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		before = len(service.ledger)
		with pytest.raises(DriverRefusal, match="no goal in this log"):
			await run(service, deliver_root(tmp_path))
		assert len(service.ledger) == before, "a refusal must not append a run"

	async def test_the_first_gate_it_reaches_is_p2(self, home: Path, tmp_path: Path) -> None:
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)

		first = await run(service, deliver_root(tmp_path))

		assert first.terminal is DriverTerminal.GATE_OPEN
		assert first.open_gate is Phase.SPECIFY
		assert not first.claims_built

	async def test_the_halting_step_is_the_one_that_opened_the_gate(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``specify`` opened P2, so ``specify`` is what the run stopped on.

		A run that named the driver's first action instead would print "propose-answers
		halted" for a step that never ran — and a resumed run has no steps of its own, so
		the fallback has to read the ``presents`` flag. ``contract`` and ``specify`` are
		both P2 and only the second opens the gate, which is exactly the pair that made
		"the first action with that phase" name the wrong one.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)

		first = await run(service, deliver_root(tmp_path))
		assert first.stopped_on == "specify"

		# Approve from outside the run, then resume: the second run takes no step before
		# it reads the open gate, so its halting action can only come from the fallback.
		current = await service.current_goal()
		assert current is not None, "the first run opened a goal"
		await operator_specify(service, current.id)
		await service.approve_gate(Phase.SPECIFY, by="operator")
		second = await run(service, deliver_root(tmp_path))

		assert second.terminal is DriverTerminal.GATE_OPEN
		assert second.open_gate is Phase.DECOMPOSE
		assert second.stopped_on == "decompose", (
			"a run with no steps of its own must name the action that presents the gate, "
			"not the first action that happens to share its phase"
		)

	async def test_a_gate_whose_machine_half_failed_names_the_producer_not_the_gate(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``gate approve`` refuses a failed check, so naming it is naming a dead end.

		FR-061 makes approval unable to make an unsound artefact sound. A driver that
		reported the stop without saying so sent the operator to a command that could only
		refuse them; the fix for a failed machine half is to supply what the checks found
		missing and produce the artefact again.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)

		first = await run(service, deliver_root(tmp_path))

		assert first.open_gate is Phase.SPECIFY
		assert first.gate_failures, "a driver-proposed specification has no operator halves"
		verb = first.next_human_verb
		assert verb is not None
		assert verb.startswith("sofact specify"), verb
		assert "gate approve" in verb, "the approval is still the second half of the instruction"
		assert "P2 awaits" in first.terminal_detail
		assert "cannot make an unsound artefact sound" in first.terminal_detail

	async def test_the_gate_can_be_approved_once_the_artefact_is_repaired(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The dead end the producer verb exists to route around, closed.

		``approve_gate`` recomputes the checks from the artefact as it is rather than
		deciding on the frozen presented row, which is the rule ``approve_specification``
		already states one level down. Deciding on the row made a repaired gate
		unapprovable: every check would pass and the operator would still be refused.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		goal_id = await a_goal(service)

		first = await run(service, deliver_root(tmp_path))
		assert first.gate_failures

		await operator_specify(service, goal_id)
		await service.approve_gate(Phase.SPECIFY, by="operator")

		state = await service.state()
		presented = state.phase_advance(Phase.SPECIFY)
		assert presented is not None
		assert presented.status is PhaseStatus.COMPLETE
		assert presented.approved_by == "operator"

	async def test_it_walks_all_four_gates_and_then_delivers(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The whole pipeline, one approval at a time, from outside the run.

		This is the property the plan states as **no branch returns ``DELIVERED`` with a
		gate open**: the run halts at each of the four in turn, and only a run that
		reaches the end with every gate approved claims a build.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)

		final, seen = await walk(service, deliver_root(tmp_path))

		assert seen == [Phase.SPECIFY, Phase.DECOMPOSE, Phase.CONTRACT, Phase.DELIVER]
		assert final.terminal is DriverTerminal.DELIVERED
		assert final.claims_built
		assert final.open_gate is None
		assert final.next_human_verb is None, "a delivered run has nothing left to type"

	async def test_every_gate_it_passes_was_approved_by_a_human(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The machine half can move a phase; only ``approve_gate`` can complete a gate.

		Asserted over the ledger rather than over the run, because the run's own report of
		what it did is the thing under test. Every completed gate phase carries an
		approver, and no completed gate phase was completed by the factory.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)

		final, _ = await walk(service, deliver_root(tmp_path))
		assert final.terminal is DriverTerminal.DELIVERED

		state = await service.state()
		completed = [p for p in state.phases if p.status is PhaseStatus.COMPLETE]
		gates = [p for p in completed if p.phase in PHASE_GATE]
		assert len(gates) == len(PHASE_GATE), "every gate must have been passed to deliver"
		for phase in gates:
			assert phase.approved_by == "operator", (
				f"{phase.phase.value} completed without a human approver"
			)


class TestIdempotency:
	"""Every step checks the log before acting, asserted on what got appended."""

	async def test_a_second_run_at_an_open_gate_appends_only_a_run(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Re-running at a gate does no machine work, so the log grows by the run alone.

		The halt is a recorded run, so the length does change — by exactly the rows a
		``DRIVER_RUN`` appends and nothing else. Asserting "unchanged" would be asserting
		something false about a ledger that records its own runs.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)

		await run(service, deliver_root(tmp_path))
		state = await service.state()
		before = len(service.ledger)

		await run(service, deliver_root(tmp_path))

		appended = service.ledger.entries()[before:]
		kinds = {entry.kind.value for entry in appended}
		assert kinds == {"driver.advanced"}, (
			f"a resumed run at an open gate did machine work: {sorted(kinds)}"
		)
		after = await service.state()
		assert len(after.driver_runs) == len(state.driver_runs) + 1

	async def test_a_sealed_step_is_not_re_dispatched(self, home: Path, tmp_path: Path) -> None:
		"""FR-172's idempotency clause, and the defect that made it necessary.

		The guard reads the plan's dispatch rows rather than ``sealed_dispatches``, which
		filters on ``checkout.sealed_commit`` — ``None`` for a producer that commits its
		own work. Read that way the set stayed empty, ``build`` was selected on every
		iteration, and a run that had completed every step re-dispatched the whole plan
		until the iteration bound and reported ``exhausted``.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		goal_id = await a_goal(service)

		final, _ = await walk(service, deliver_root(tmp_path))
		assert final.terminal is DriverTerminal.DELIVERED

		state = await service.state()
		contract = state.latest_contract(goal_id)
		assert contract is not None
		plan = state.latest_plan(contract.id)
		assert plan is not None
		dispatched = state.dispatches_for(plan.id)
		step_ids = [d.step_id for d in dispatched]
		assert len(step_ids) == len(set(step_ids)), (
			"a step was dispatched twice, so the build was not idempotent"
		)
		assert {d.step_id for d in dispatched} == {s.id for s in plan.steps}

	async def test_a_producer_that_commits_its_own_work_still_reads_as_dispatched(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The predicate itself, stated against the state it is read from.

		This is the defect in one assertion. A producer that commits its own work leaves
		``sealed_dispatches`` empty — that filter is about *reviewability*, and an
		unreviewable diff is an accepted limit of the coverage denominator. The dispatch
		rows are the only fact that answers "has this plan been built", so the two sets
		differ here, and the driver must read the second.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		goal_id = await a_goal(service)

		final, _ = await walk(service, deliver_root(tmp_path))
		assert final.terminal is DriverTerminal.DELIVERED

		state = await service.state()
		contract = state.latest_contract(goal_id)
		assert contract is not None
		plan = state.latest_plan(contract.id)
		assert plan is not None
		assert state.dispatches_for(plan.id), "the walk built nothing"
		assert not state.sealed_dispatches, (
			"this fixture's producer is expected to commit its own work, which is what "
			"makes the two sets differ; if it stopped doing so this test no longer "
			"exercises the defect it exists for"
		)


class TestTerminalStateIsReported:
	"""``claims_built`` is true for ``DELIVERED`` alone, and the subject reads it."""

	async def test_a_run_stopped_at_a_gate_never_claims_a_build(
		self, home: Path, tmp_path: Path
	) -> None:
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)

		first = await run(service, deliver_root(tmp_path))
		assert first.terminal is DriverTerminal.GATE_OPEN
		assert not first.claims_built

	async def test_the_subject_at_a_gate_says_awaiting_and_says_not_built(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The single worst defect this feature can have, asserted as a literal string."""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		goal_id = await a_goal(service)

		first = await run(service, deliver_root(tmp_path))
		statement = (await service.state()).goal(goal_id)
		assert statement is not None
		subject = render_subject(first, statement.statement)

		assert subject == "sofact: Ship a reminder dashboard. — awaiting P2 approval, not built"

	async def test_a_cold_run_with_no_model_waits_on_the_questionnaire(
		self, home: Path, tmp_path: Path
	) -> None:
		"""No reachable model is a waiting state, not a failed run.

		P0 is a deterministic interrogation and the operator is its author. Treating an
		unreachable endpoint as FAILED would make the one verb that carries a goal to its
		first gate refuse to start on every deployment without one — the configuration,
		not a fault in the goal. The next verb names the questionnaire rather than a
		resume, because resuming would re-select an action that will do nothing.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await service.start("Ship a reminder dashboard.")

		first = await run(service, deliver_root(tmp_path))

		assert first.terminal is DriverTerminal.EXHAUSTED
		assert first.stopped_on == "propose-answers"
		assert first.steps[-1].outcome is DriverOutcome.SKIPPED
		assert first.next_human_verb is not None
		assert first.next_human_verb.startswith("sofact "), first.next_human_verb
		assert "build --resume" not in first.next_human_verb, (
			"resuming would re-select an action that cannot advance without a person"
		)

	async def test_a_run_that_reaches_a_gate_names_the_verb_that_continues_it(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A gate whose machine half passed is approved with ``gate approve``.

		The other direction of the ``gate_failures`` branch, and the one that would be the
		opposite mistake: telling an operator to re-produce an artefact whose checks all
		pass. The driver runs, the operator supplies the halves it cannot, and the resumed
		run reads a passing gate and names the approval.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		goal_id = await a_goal(service)

		await run(service, deliver_root(tmp_path))
		await operator_specify(service, goal_id)
		second = await run(service, deliver_root(tmp_path))

		assert second.open_gate is Phase.SPECIFY
		assert not second.gate_failures
		assert second.next_human_verb == "sofact gate approve P2 --by <you>"


class TestTheActionTable:
	"""What the driver can do is readable in one place, and each action says which it is."""

	def test_every_action_has_a_distinct_name(self) -> None:
		names = [action.name for action in DRIVER_ACTIONS]
		assert len(names) == len(set(names)), f"two actions share a name: {names}"

	def test_exactly_the_gate_phases_have_a_presenting_action(self) -> None:
		"""``presents`` is what a resumed run reads to name the step it stopped on.

		One action per gate phase, and no phase with two — a second presenter would make
		the fallback ambiguous again, which is the defect the flag was introduced for.
		"""
		presenting = [action for action in DRIVER_ACTIONS if action.presents]
		assert {action.phase for action in presenting} == set(PHASE_GATE)
		assert len(presenting) == len(PHASE_GATE)

	def test_no_action_presents_a_gate_for_an_ungated_phase(self) -> None:
		for action in DRIVER_ACTIONS:
			if action.presents:
				assert action.phase in PHASE_GATE, (
					f"{action.name} claims to present a gate for {action.phase.value}, "
					"which has none"
				)
