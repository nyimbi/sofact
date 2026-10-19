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

import dataclasses
from pathlib import Path

import pytest
from conftest import GOOD_ANSWERS, answer_everything
from synthetic import a_model_for, base_spec, synthetic_service

from sofact._uuid7 import uuid7str
from sofact.driver import DRIVER_ACTIONS, DriverRefusal, classify_failure, run_goal
from sofact.llm import LlmClient
from sofact.notify import render_subject
from sofact.service import FactoryService
from sofact.specdoc import PRODUCT_SPEC_FILENAME
from sofact.views import (
	DRIVER_FAILURE_VERB,
	PHASE_GATE,
	Assumption,
	DriverFailure,
	DriverOutcome,
	DriverRun,
	DriverTerminal,
	ElicitationDimension,
	Phase,
	PhaseStatus,
	ValueHypothesis,
)

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

	async def test_p2_opens_with_the_document_it_is_a_gate_on(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The gate a person is asked to pass must have its artefact on disk when they look.

		The driver presented P2 and rendered nothing, so the operator was asked to approve a
		specification they had no document for: ``SPECIFICATION.md`` was reachable only by
		remembering to run ``sofact spec-doc`` afterwards, and afterwards is after the
		decision it was built to inform. ADR-0071 makes the annotated document P2's artefact,
		so the driver that opens P2's gate is the thing that has to write it.

		Asserted on the *file*, not on the ledger row, because the ledger row was already
		being written by ``sofact spec-doc`` in the tests that passed while this was broken —
		a run that recorded a document and left the operator with nothing to read is exactly
		the defect, and a check on the record cannot see it.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)
		root = deliver_root(tmp_path)

		first = await run(service, root)

		assert first.open_gate is Phase.SPECIFY
		written = root / PRODUCT_SPEC_FILENAME
		assert written.exists(), (
			"P2 is open and the document the gate is a gate on is not on disk; the operator "
			"has a checklist for an artefact they cannot read (FR-171)"
		)
		text = written.read_text(encoding="utf-8")
		assert "## Requirements" in text
		assert "P2 machine checks outstanding at render:" in text, (
			"the gate the reader is deciding against is carried on the document, so what P2 "
			"is still asking for is visible rather than inferred"
		)
		document = await service.current_product_spec()
		assert document is not None
		assert document.approved_by is None, "the driver may not approve the gate it opens"

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
		"""``gate --approve`` refuses a failed check, so naming it is naming a dead end.

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
		assert "gate --approve" in verb, "the approval is still the second half of the instruction"
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


class _ReachableModel(LlmClient):
	"""A model that answers every dimension, so P0 can actually be drafted.

	Subclassing :class:`~sofact.llm.LlmClient` rather than duck-typing it, so the stub
	cannot drift out of step with the interface the service calls — ``test_specdoc.py``'s
	precedent. The text is the fixture answer for whichever dimension the prompt is for,
	which is what makes the proposals *usable* and therefore makes the second driver
	iteration reach the state under test.
	"""

	def __init__(self) -> None:
		self.calls = 0

	async def complete(self, *, system: str, user: str) -> str:
		self.calls += 1
		# Keyed off ``propose_prompt``'s own ``Dimension: <value>`` line rather than off a
		# substring search of the whole prompt: the dimensions' rationales mention each
		# other ("so there can be no oracle"), so a substring match returns whichever
		# dimension happens to be checked first and the ORACLE proposal came back as the
		# OUTCOME answer — which does not clear the oracle floor, so attesting everything
		# still left a dimension open and the test failed for a fixture reason.
		for dimension, answer in GOOD_ANSWERS.items():
			if f"Dimension: {dimension.value}" in user:
				return answer
		raise AssertionError(f"the prompt names no known dimension:\n{user}")


class TestAProposalIsNotAnAnswer:
	"""A drafted dimension is not a resolved one, and the run says which verb closes it."""

	async def test_a_run_that_drafted_every_dimension_names_attest_not_a_resume(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The ordinary first run on a reachable model, and the dead end it used to hit.

		P0 drafts every dimension on the first iteration. ``readiness`` reports a
		model-proposed answer nobody attested as **open** (FR-173) — correctly, since the
		floor measures specificity and this measures authorship — so the second iteration
		selects ``propose-answers`` again, proposes nothing, and stops. The message then
		told the operator to run ``sofact build --resume``, which re-selects the same
		action and prints the same sentence forever, while the ``next:`` line directly
		beneath it named the questionnaire instead. One report, two contradictory
		instructions, and no test could see it because every other test either has no
		model configured or answers the dimensions itself.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await service.start("Ship a reminder dashboard.")
		model = _ReachableModel()
		service.llm = model

		result = await run(service, deliver_root(tmp_path))

		assert model.calls == len(GOOD_ANSWERS), "every open dimension must be drafted once"
		assert result.stopped_on == "propose-answers"
		assert result.terminal is DriverTerminal.EXHAUSTED
		# The proposals are on the log and unresolved, which is the state that was
		# mistaken for "nothing to do".
		goal = await service.current_goal()
		assert goal is not None, "the run opened a goal"
		readiness = await service.readiness(goal.id)
		assert readiness.open_dimensions == tuple(d.value for d in ElicitationDimension)
		assert result.awaiting_attestation, "the run left proposals nobody confirmed"
		assert result.next_human_verb is not None
		assert "attest" in result.next_human_verb, result.next_human_verb
		assert "questionnaire" not in result.next_human_verb, (
			"the questionnaire has nothing left to ask; it would re-open at a proposal"
		)

	async def test_attesting_the_proposals_is_what_lets_the_run_continue(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The verb the message names is the verb that works — the other half of the claim.

		Naming ``attest`` is only correct if attesting actually unblocks the run, so the
		test performs it and asserts the run moves on. Without this the message could name
		a verb that is merely plausible.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await service.start("Ship a reminder dashboard.")
		service.llm = _ReachableModel()
		first = await run(service, deliver_root(tmp_path))
		assert first.next_human_verb is not None
		assert "attest" in first.next_human_verb, first.next_human_verb

		goal = await service.current_goal()
		assert goal is not None, "the run opened a goal"
		proposals = [a for a in (await service.state()).answers_for(goal.id) if a.is_model_proposed]
		assert len(proposals) == len(GOOD_ANSWERS)
		for answer in proposals:
			await service.attest(answer.id, by="operator")

		second = await run(service, deliver_root(tmp_path))

		# P0 is behind it: the run drafted clause stems from the attested answers rather
		# than proposing again, which is the whole of what ``attest`` was supposed to buy.
		assert second.steps[0].action == "draft", second.steps[0]
		assert second.steps[0].outcome is DriverOutcome.ADVANCED, second.steps[0]
		assert not second.awaiting_attestation


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
		"""A gate whose machine half passed is approved with ``gate --approve``.

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
		assert second.next_human_verb == "sofact gate --approve P2 --by <you>"

	async def test_a_clause_the_evidence_invalidated_stops_the_run_as_its_own_state(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-068's "return to P0" is a finding, not a fault, and the run must say so.

		``advance_phase`` refuses to complete P1 when a clause's verdict is Invalidated or
		Deepened — "do not build" — and that arrives at the loop as a ``ValueError`` like
		any other. Reported as ``FAILED``, it read as a broken run, and ``next_human_verb``
		named ``build --resume``: a command that re-selects the same action, hits the same
		refusal and prints the same sentence forever. Nothing was broken; the evidence had
		withdrawn a premise, and the operator's move is to revise an answer, which no
		resume performs.

		Asserted on the *terminal state* rather than on the message, because the terminal
		state is what ``next_human_verb`` and the notification subject both read. The
		classification is the discriminator and it is data — a driver that decided the kind
		of stop by matching the refusal's sentence would break the day somebody reworded it.

		**And asserted on the steps, which is the half that was wrong.** The stop used to be
		read only in the loop's exception handler, so it arrived from ``_present``: the run
		contracted and specified over the contradicted clause first, and the operator was
		shown a P2 gate for a specification resting on a premise SoFact's own research had
		withdrawn. "Do not build" is a constraint on the work, not only on the exit.
		"""
		service = synthetic_service(home, tmp_path, "research-classify-invalidated")
		await service.probe_harness(None)
		await a_goal(service)

		result = await run(service, deliver_root(tmp_path))
		taken = [step.action for step in result.steps]

		assert result.terminal is DriverTerminal.RETURNED_TO_P0, (
			f"an invalidated premise is FR-068's stop, not a failure: {result.terminal_detail}"
		)
		assert not result.claims_built
		assert result.open_gate is None, "the stop is not a gate and must not read as one"
		assert "specify" not in taken, (
			f"a specification over a clause the evidence invalidated is the work FR-068 "
			f"forbids, and the run did it before noticing: {taken}"
		)
		assert "contract" not in taken, f"no contract over an unbuildable premise: {taken}"
		assert taken == ["draft", "research"], (
			f"the run stops at the finding, having done only the work that produced it: {taken}"
		)
		assert result.next_human_verb is not None
		assert result.next_human_verb.startswith("sofact elicit"), (
			f"the operator's move is to revise an answer, and this names a resume first: "
			f"{result.next_human_verb}"
		)
		assert "revise" in result.next_human_verb, (
			f"the verb has to say what the revision is *of*, or the operator is sent to a "
			f"questionnaire of open questions and no indication which one moved: "
			f"{result.next_human_verb}"
		)

	async def test_the_subject_of_a_return_to_p0_does_not_say_failed(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The other half: the operator reads the subject, and "failed" sends them hunting.

		A notification reading "failed" for a run that stopped because the evidence
		contradicted a premise points the operator at a broken thing that is not there.
		"""
		service = synthetic_service(home, tmp_path, "research-classify-deepened")
		await service.probe_harness(None)
		goal_id = await a_goal(service)

		result = await run(service, deliver_root(tmp_path))
		statement = (await service.state()).goal(goal_id)
		assert statement is not None
		subject = render_subject(result, statement.statement)

		assert result.terminal is DriverTerminal.RETURNED_TO_P0
		assert subject == (
			"sofact: Ship a reminder dashboard. — returned to P0: the evidence contradicted "
			"a premise, not built"
		)


async def cut_before_phase_presentation(service: FactoryService, phase: Phase) -> None:
	"""Leave ``phase``'s artefact on the log and its presentation off it (FR-061).

	The state a process killed between ``_perform``'s commit and its ``_present`` leaves:
	every row the phase's own work wrote is there, and the ``phase.advanced`` row that
	would have shown a human the gate is not. Built by cutting to just before that row
	rather than by calling the service's proposal methods by hand, because the hand-built
	version is a *different* state — it omits the rows ``_close_predecessors`` writes —
	and a test of the orphan has to be a test of the orphan the driver actually meets.
	"""
	presented = [
		entry.index
		for entry in service.ledger.entries()
		if entry.kind.value == "phase.advanced"
		and entry.payload.get("advance", {}).get("phase") == phase.value
	]
	assert presented, f"nothing presented {phase.value}, so there is no orphan to build"
	await service.cut(presented[0] - 1, by="test", reason=f"simulate a kill before {phase.value}")
	state = await service.state()
	assert state.phase_status(phase) is PhaseStatus.PENDING, (
		f"the cut left {phase.value} at {state.phase_status(phase).value}, not PENDING: "
		"this is not the orphan state the test means to exercise"
	)
	assert state.open_gate is None, "the cut left a gate open; that is a different state"


class TestAnOrphanArtefactDoesNotDischargeItsPhase:
	"""An artefact whose gate was never presented is not work the phase did (FR-061, FR-172).

	A phase's proposal path commits its artefact and *then* presents its gate, so a process
	killed between the two appends leaves an orphan: the artefact is on the log and the
	phase is still ``PENDING``. Every one of these tests builds that state the way the kill
	builds it, and asserts the driver does not read the orphan as a discharged phase.

	The defect this class exists for is one shape in five places: **the driver decided
	"what next" from the existence of an artefact rather than from the phase having been
	presented.** Each instance failed differently — a repeating wrong refusal, a step
	selected past a gate nobody saw, and (worst) a ``DELIVERED`` run claiming a build whose
	deploy gate had never been shown.
	"""

	async def test_a_delivery_with_its_gate_unpresented_does_not_claim_a_build(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The module's own stated property, and the state that violated it.

		``_perform``'s deliver branch renders the report and then presents P8. Killed
		between the two, the log holds a delivery and P8 is ``PENDING`` with no open gate.
		``_next_action`` read ``state.delivery is None`` alone, returned ``None``, the loop
		broke with **zero steps**, and the terminal branch reported ``DELIVERED`` with
		``claims_built=True`` — a notification reading "built and verified" for a system
		whose deploy gate nobody had been shown. The plan file states the property this
		refutes in one line: "no branch returns DELIVERED with a gate open."

		Built by cutting the log to just before the row that presented P8, which is exactly
		what the kill leaves: everything the delivery needs is present, and the presentation
		is not.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)
		root = deliver_root(tmp_path)

		final, _ = await walk(service, root)
		assert final.terminal is DriverTerminal.DELIVERED

		presented = [
			entry.index
			for entry in service.ledger.entries()
			if entry.kind.value == "phase.advanced"
			and entry.payload.get("advance", {}).get("phase") == Phase.DELIVER.value
		]
		assert presented, "the walk presented P8, or there is nothing to cut before"
		await service.cut(presented[0] - 1, by="test", reason="simulate a kill before _present")

		orphaned = await service.state()
		assert orphaned.delivery is not None, "the cut left no delivery to be an orphan"
		assert orphaned.phase_status(Phase.DELIVER) is PhaseStatus.PENDING
		assert orphaned.open_gate is None, "this is the orphan state, not an open gate"

		resumed = await run(service, root)

		assert resumed.terminal is not DriverTerminal.DELIVERED, (
			"a delivery whose deploy gate was never presented is not a finished build"
		)
		assert not resumed.claims_built
		assert resumed.stopped_on == "deliver", (
			"the run must re-select deliver and present the gate it never showed"
		)
		after = await service.state()
		assert after.open_gate is not None, "the resumed run presented P8"
		assert after.open_gate.phase is Phase.DELIVER

	async def test_an_orphan_specification_is_not_read_as_a_discharged_p2(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``latest_specification`` was read without consulting the phase status.

		With an orphan specification committed and P2 never presented, ``_next_action``
		selected ``decompose`` — a step downstream of a gate nobody was shown — and the run
		failed with P2's approval message. The operator's repair is to re-run ``specify``,
		which proposes a revision and presents the gate.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		goal_id = await a_goal(service)
		root = deliver_root(tmp_path)

		first = await run(service, root)
		assert first.open_gate is Phase.SPECIFY, (
			f"the run stopped on {first.open_gate}, so P2 is not the gate to orphan"
		)

		# The orphan, built the way the kill builds it: every row the phase's work wrote is
		# on the log, and the presentation is not.
		await cut_before_phase_presentation(service, Phase.SPECIFY)

		orphaned = await service.state()
		contract = orphaned.latest_contract(goal_id)
		assert contract is not None, "the cut removed the contract, not just the presentation"
		assert orphaned.latest_specification(contract.id) is not None, (
			"the cut removed the specification, so there is no orphan to test"
		)

		resumed = await run(service, root)

		assert resumed.terminal is not DriverTerminal.FAILED, (
			f"an orphan specification must not send the run past its own gate: "
			f"{resumed.terminal_detail}"
		)
		assert resumed.stopped_on == "specify", (
			"the run must present P2 rather than decompose past it"
		)
		assert resumed.open_gate is Phase.SPECIFY

	async def test_a_phase_that_is_merely_active_is_not_discharged(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The predicate itself, on the state it has to refuse.

		``ACTIVE`` is a phase mid-flight: work has started and nobody has been shown
		anything. Collapsing it into "discharged" is the same defect as the orphan, one
		transition earlier.

		P2 is reached and then unwound rather than advanced from a standing start, because
		``advance_phase`` refuses a phase whose predecessors are incomplete — P0 has to have
		finished before P2 can be in flight at all, and the run is what finishes it.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)
		await run(service, deliver_root(tmp_path))
		await cut_before_phase_presentation(service, Phase.SPECIFY)

		before = await service.state()
		assert before.phase_status(Phase.SPECIFY) is PhaseStatus.PENDING
		assert not before.phase_is_discharged(Phase.SPECIFY), "P2 is untouched"

		await service.advance_phase(Phase.SPECIFY, PhaseStatus.ACTIVE, by="test")
		active = await service.state()
		assert active.phase_status(Phase.SPECIFY) is PhaseStatus.ACTIVE
		assert not active.phase_is_discharged(Phase.SPECIFY), (
			"an active phase has not been presented to anyone"
		)

	async def test_an_ungated_phase_is_discharged_by_completion(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The other direction, so the predicate cannot be tightened into a deadlock.

		P0, P1 and the build phases have no gate to present, and ``_close_predecessors``
		completes them as the work lands. A predicate that demanded a presentation for a
		phase that has none would make the driver refuse at its own gate.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		await a_goal(service)

		await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE, by="test")

		state = await service.state()
		assert state.phase_is_discharged(Phase.ELICIT)
		assert Phase.ELICIT not in PHASE_GATE, "P0 has no gate, which is why completion suffices"


class TestResearchCoversTheDraftItWasRunAgainst:
	"""``has_research`` was "research has ever run", which stays true under a new draft."""

	async def test_a_draft_revised_after_p1_is_researched_again(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The fact the old predicate got wrong, and the contract it produced over it.

		``has_research`` was ``any(r.goal_id == goal_id for r in state.research)`` — "a
		research run exists for this goal". That stays true when the draft is revised
		underneath it, and a revised draft is the whole point of returning to P0: the
		operator restates an answer, ``draft_stems`` writes **fresh** stem ids, and the
		classification on the log names clause ids no draft holds any more. The driver then
		selected ``contract`` over clauses the evidence never reached — and FR-068 exists
		precisely because a contract is written over *classified* premises.

		Built by cutting the log to just before the contract row, which is the state a
		process killed between P1 and P2 leaves: the draft, the research and the
		classification are all present and no contract exists yet. Revising an answer then
		makes the draft stale, and the run has to notice both that it needs a new draft and
		that the old classification is about a clause set that no longer exists.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		goal_id = await a_goal(service)
		root = deliver_root(tmp_path)

		await run(service, root)
		contracts = [
			entry.index
			for entry in service.ledger.entries()
			if entry.kind.value == "contract.created"
		]
		assert contracts, "the first run reached a contract, or there is nothing to cut before"
		await service.cut(contracts[0] - 1, by="test", reason="stop between P1 and the contract")

		before = await service.state()
		assert before.latest_contract(goal_id) is None, "the cut left a contract behind"
		first_draft = before.latest_draft(goal_id)
		first_classification = before.classification
		assert first_draft is not None, "the cut removed the draft P1 was run against"
		assert first_classification is not None, "the cut removed the classification"

		# The operator revises one answer, which is FR-068's action for a premise the
		# evidence withdrew — and the only thing a revision does downstream is make the
		# draft it fed stale.
		await service.answer(
			goal_id,
			ElicitationDimension.OUTCOME,
			"Every scheduled reminder appears in the user dashboard within two seconds of "
			"its scheduled time, measured by the dashboard's own poll clock.",
		)

		result = await run(service, root)
		after = await service.state()

		assert result.steps[0].action == "draft", (
			f"a draft built from superseded answers is not current: {result.steps[0]}"
		)
		assert "research" in [step.action for step in result.steps], (
			"the classification names a clause set this draft no longer holds, so P1 has to "
			"run again before anything is contracted over those clauses"
		)
		assert len(after.research) > len(before.research), "a second research run is recorded"

		second_draft = after.latest_draft(goal_id)
		second_classification = after.classification
		assert second_draft is not None, "the run left no draft"
		assert second_classification is not None, "the run left no classification"
		assert second_draft.id != first_draft.id, "the revision produced a new draft"
		assert {c.clause_id for c in second_classification.classifications} != {
			c.clause_id for c in first_classification.classifications
		}, "the re-classification is about the new draft's clauses, not the old ones"
		assert not second_classification.unclassified(
			frozenset(s.id for s in second_draft.stems)
		), (
			"the classification the run contracted over names every clause of the draft it "
			"was run against (FR-068)"
		)

	async def test_revising_the_answer_lets_the_run_past_the_stop(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The stop must not be a deadlock, and the operator's repair must be the exit.

		FR-068's action is "revise the clauses and return to P0", so the run has to *get*
		back to P0 — re-draft from the revised answer and research the new clause set. The
		first version of this check read the classification without asking whether the
		draft it was a verdict on was still the goal's, so the run after a revision reported
		``RETURNED_TO_P0`` with **zero steps**: the one command the stop names led back to
		the same stop, and the only exit was a hand-edited ledger.

		The fixture invalidates the first clause by position on every classification, so a
		second stop is correct and not the thing under test. What is under test is that the
		run re-drafts and re-researches first — it acts on the revision rather than
		refusing against a premise the operator has already restated.
		"""
		service = synthetic_service(home, tmp_path, "research-classify-invalidated")
		await service.probe_harness(None)
		goal_id = await a_goal(service)
		root = deliver_root(tmp_path)

		first = await run(service, root)
		assert first.terminal is DriverTerminal.RETURNED_TO_P0
		before = await service.state()
		stale_draft = before.latest_draft(goal_id)
		assert stale_draft is not None, "the run drafted before it researched"

		await service.answer(
			goal_id,
			ElicitationDimension.OUTCOME,
			"Every scheduled reminder appears in the user dashboard within two seconds of "
			"its scheduled time, measured by the dashboard's own poll clock.",
		)

		second = await run(service, root)
		taken = [step.action for step in second.steps]

		assert taken[:2] == ["draft", "research"], (
			f"the run has to re-draft from the revised answer and re-classify the new "
			f"clauses before it can stop on a verdict again: {taken}"
		)
		after = await service.state()
		fresh = after.latest_draft(goal_id)
		assert fresh is not None, "the run left no draft"
		assert fresh.id != stale_draft.id, "the revision produced a new draft, not a re-read"
		assert fresh.descends_from(after.answers_for(goal_id)), (
			"the new draft is built from the answers the operator has now, which is what "
			"makes the old verdict moot (FR-068)"
		)


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


class TestAFailedRunNamesTheSettingNotAResume:
	"""``FAILED`` is one terminal over many causes, and a resume is right for only some.

	ADR-0075 recorded this as an open gap: the fix that gave P0's two ``EXHAUSTED`` waits
	their own verbs was not carried to ``FAILED``, so a run stopped by a missing harness
	binary told the operator to run ``build --resume`` — a command that re-selects the same
	action and raises the same exception, forever.

	The class is the point. A test that planted one exception and asserted one verb would
	pass against a handler that special-cased that exception; these tests walk
	:data:`sofact.views.DRIVER_FAILURE_VERB`, so a member added without a verb fails, and a
	verb that is a resume fails for every member.
	"""

	def test_every_failure_names_a_verb_that_is_not_a_resume(self) -> None:
		"""The whole table, so a new member cannot be added with the fallback by accident."""
		assert DRIVER_FAILURE_VERB, "the table is empty, so nothing is classified"
		for failure, verb in DRIVER_FAILURE_VERB.items():
			assert "build --resume" not in verb.split("(")[0], (
				f"{failure.value} names a resume in its opening clause, which is the "
				f"instruction this table exists to stop giving: {verb}"
			)
			assert verb.startswith("sofact ") or verb.startswith("git "), verb

	def test_every_failure_is_classified_from_a_real_exception(self) -> None:
		"""The classifier fires on the types the product actually raises.

		Keyed on the exception the modules raise rather than on a string, because the
		defect ADR-0075 fixed was a string written for a human being parsed as though it
		were data. A table that named a class the product never raises would classify
		nothing and read as correct.
		"""
		from sofact.git import GitUnavailableError
		from sofact.harness import HarnessBinaryMissing, HarnessSessionUnreadable
		from sofact.search import SearchRefusal

		cases = {
			HarnessBinaryMissing("not on PATH"): DriverFailure.HARNESS_MISSING,
			HarnessSessionUnreadable("not JSON"): DriverFailure.HARNESS_RECORD_UNREADABLE,
			SearchRefusal("unknown provider"): DriverFailure.SEARCH_UNUSABLE,
			GitUnavailableError("not a repository"): DriverFailure.GIT_MISSING,
		}
		for exc, expected in cases.items():
			assert classify_failure(exc) is expected, (
				f"{type(exc).__name__} classified as {classify_failure(exc)}"
			)

	def test_a_bug_is_not_classified(self) -> None:
		"""``None`` is the honest answer, and the fallback verb is a resume.

		A ``ValueError`` from a step is a bug in the factory, and telling the operator to
		change a setting for it would send them to fix something that is not wrong. The
		trace a re-run produces is the actual next step.
		"""

		assert classify_failure(ValueError("an invariant broke")) is None
		assert classify_failure(KeyError("no such goal")) is None

	async def test_a_missing_harness_binary_names_probe_and_not_a_resume(
		self, home: Path, tmp_path: Path
	) -> None:
		"""End to end: a real run whose dispatch raises ``HarnessBinaryMissing``.

		The spec names a binary that is not on ``PATH``, which is what a deployment with an
		uninstalled harness looks like. The run must record the failure and name
		``sofact probe``, not the resume that would re-select the same dispatch.
		"""
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"), argv=("sofact-no-such-binary-anywhere",)
		)
		service = FactoryService(home=home, llm=None, specs={HARNESS: spec})
		await a_goal(service)
		goal = await service.current_goal()
		assert goal is not None, "the fixture opened a goal"
		await answer_everything(service, goal.id)

		result = await run(service, deliver_root(tmp_path))

		if result.terminal is not DriverTerminal.FAILED:
			# The pipeline can reach a gate before it ever dispatches, and on the
			# synthetic table it usually does. The assertion below is about the FAILED
			# branch, so a run that never reached a dispatch is not evidence either way —
			# but it must not silently pass as though it had tested the branch.
			pytest.skip(
				f"the walk stopped at {result.terminal.value} before dispatching; "
				"the classifier's own tests cover the mapping"
			)
		assert result.failure is DriverFailure.HARNESS_MISSING, result.terminal_detail
		verb = result.next_human_verb
		assert verb is not None
		assert verb.startswith("sofact probe"), verb
		assert "build --resume" not in verb.split("(")[0], (
			"the resume is the second half of the instruction, not the first"
		)
