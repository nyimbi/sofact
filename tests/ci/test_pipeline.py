"""End-to-end: a goal becomes a verdict, through the real service and a real log.

The centrepiece is :func:`test_a_success_claim_does_not_survive_a_failing_oracle`.
A producer that announces it is finished, while the oracle it was measured against
fails, must come out ``VIOLATED``. That is FR-138 demonstrated rather than asserted,
and it is the behaviour that makes every other guarantee in SoFact mean anything.

Nothing here is mocked except the model, which is absent: the deterministic path is
the product. Every test drives the same objects the CLI drives.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from conftest import answer_everything
from synthetic import plan_and_service

from sofact.contract import ground_truth_debt
from sofact.service import FactoryService
from sofact.views import LedgerKind, VerdictOutcome

MakeContract = Callable[..., object]


async def interrogate(service: FactoryService, statement: str) -> str:
	"""Take a goal from statement to contract-ready draft; return the goal id."""
	goal = await service.start(statement)
	await answer_everything(service, goal.id)
	await service.draft(goal.id)
	return goal.id


# --------------------------------------------------------------------------- #
# the centrepiece
# --------------------------------------------------------------------------- #


async def test_a_success_claim_does_not_survive_a_failing_oracle(
	service: FactoryService, tmp_path: Path
) -> None:
	"""Announce victory, then fail the oracle. The verdict must be VIOLATED."""
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id, commands="exit 1")

	claim = await service.declare_completion(goal_id, by="probe-harness", note="all green")
	produced = await service.run(contract.id, workspace=tmp_path)
	report = await service.verify_contract(contract.id)

	assert claim.declared_by == "probe-harness"
	assert len(produced) == len(contract.clauses), "every clause has a command"
	assert report.outcome is VerdictOutcome.VIOLATED
	assert not report.is_clean
	assert len(report.violated) == len(contract.clauses)
	for verdict in report.verdicts:
		assert "exit code 1" in verdict.reason


async def test_a_passing_oracle_yields_a_clean_report(
	service: FactoryService, tmp_path: Path
) -> None:
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id, commands="exit 0")
	await service.run(contract.id, workspace=tmp_path)
	report = await service.verify_contract(contract.id)

	assert report.outcome is VerdictOutcome.SATISFIED
	assert report.is_clean
	assert report.contract_hash == contract.content_hash


# --------------------------------------------------------------------------- #
# a claim is not evidence
# --------------------------------------------------------------------------- #


async def test_declaring_completion_changes_no_verdict(
	service: FactoryService, tmp_path: Path
) -> None:
	"""Run the same verification before and after a claim; nothing may differ."""
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id, commands="exit 0")
	await service.run(contract.id, workspace=tmp_path)

	before = await service.verify_contract(contract.id)
	await service.declare_completion(goal_id, by="harness", note="done, honestly")
	after = await service.verify_contract(contract.id)

	assert before.outcome is after.outcome
	assert [(v.clause_id, v.outcome) for v in before.verdicts] == [
		(v.clause_id, v.outcome) for v in after.verdicts
	]


async def test_a_claim_without_evidence_leaves_the_clause_insufficient(
	service: FactoryService,
) -> None:
	"""The degenerate case: claiming success with nothing run proves nothing."""
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id, commands="exit 0")
	claim = await service.declare_completion(goal_id, by="harness")

	report = await service.verify_contract(contract.id)

	assert claim.id
	assert report.outcome is VerdictOutcome.INSUFFICIENT
	assert all("no evidence" in v.reason for v in report.verdicts)


# --------------------------------------------------------------------------- #
# refusing to pretend
# --------------------------------------------------------------------------- #


async def test_a_contract_with_no_commands_is_total_ground_truth_debt(
	service: FactoryService,
) -> None:
	"""Suggested oracles are honest gaps. The debt is reported, not hidden."""
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id)

	assert ground_truth_debt(contract) == 1.0
	report = await service.verify_contract(contract.id)
	assert report.outcome is VerdictOutcome.INSUFFICIENT
	assert not report.is_clean


# --------------------------------------------------------------------------- #
# the log is the state
# --------------------------------------------------------------------------- #


async def test_evidence_and_verdicts_round_trip_through_the_ledger(
	service: FactoryService, tmp_path: Path
) -> None:
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id, commands="exit 0")
	await service.run(contract.id, workspace=tmp_path)
	await service.verify_contract(contract.id)

	state = await service.state()
	assert len(state.evidence) == len(contract.clauses)
	for clause in contract.clauses:
		assert state.evidence_for(clause.id), f"clause {clause.id} lost its evidence"
	assert state.latest_report(contract.id) is not None

	kinds = [entry.kind for entry in await service.entries()]
	assert LedgerKind.EVIDENCE_RECORDED in kinds
	assert LedgerKind.VERDICT_RENDERED in kinds
	assert LedgerKind.CONTRACT_CREATED in kinds


async def test_the_ledger_chain_holds_across_the_whole_pipeline(
	service: FactoryService, tmp_path: Path
) -> None:
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id, commands="exit 0")
	await service.run(contract.id, workspace=tmp_path)
	await service.verify_contract(contract.id)
	await service.declare_completion(goal_id, by="harness")

	chain = await service.verify_ledger()
	assert chain.ok, f"chain broke at {chain.broken_at}: {chain.reason}"
	assert chain.length > 0


async def test_a_repaired_clause_can_turn_green(service: FactoryService, tmp_path: Path) -> None:
	"""FR-006 at the artefact level: the verdict describes the latest attempt.

	The oracle asks whether a file exists, so it is refutable and then satisfiable by
	the same contract. A verdict that weighed the whole history would answer "has this
	clause ever failed?" and this repair would be reported as a failure forever — which
	would make the plan's repair tier unable to observe its own success and would accuse
	the producer of lying about work that succeeded.
	"""
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id, commands="test -f marker.txt")

	await service.run(contract.id, workspace=tmp_path)
	before = await service.verify_contract(contract.id)
	assert before.outcome is VerdictOutcome.VIOLATED

	(tmp_path / "marker.txt").write_text("repaired", encoding="utf-8")

	await service.run(contract.id, workspace=tmp_path)
	after = await service.verify_contract(contract.id)
	assert after.outcome is VerdictOutcome.SATISFIED
	assert after.is_clean

	tampered = await service.verify_ledger()
	assert tampered.ok, "both verdicts stay in the log: the history is not rewritten"


async def test_a_verdict_can_be_asked_for_a_specific_run(
	service: FactoryService, tmp_path: Path
) -> None:
	"""Naming the run answers the provenance question on purpose, not by accident."""
	goal_id = await interrogate(service, "Every reminder appears in the dashboard.")
	contract = await service.contract(goal_id, commands="test -f marker.txt")

	await service.run(contract.id, workspace=tmp_path)
	(tmp_path / "marker.txt").write_text("repaired", encoding="utf-8")
	await service.run(contract.id, workspace=tmp_path)

	latest = await service.verify_contract(contract.id)
	state = await service.state()
	runs = [item.run_id for item in state.evidence if item.run_id is not None]
	assert len(set(runs)) == 2, "two runs, two identities"

	oldest = await service.verify_contract(contract.id, run_id=runs[0])
	assert oldest.outcome is VerdictOutcome.VIOLATED
	assert latest.outcome is VerdictOutcome.SATISFIED


async def test_a_restarted_service_reconstructs_everything_from_the_log(
	home: Path, tmp_path: Path
) -> None:
	"""State is derived, never stored. A second service on the same home must agree."""
	first = FactoryService(home=home, llm=None)
	goal_id = await interrogate(first, "Every reminder appears in the dashboard.")
	contract = await first.contract(goal_id, commands="exit 0")
	await first.run(contract.id, workspace=tmp_path)
	await first.verify_contract(contract.id)

	second = FactoryService(home=home, llm=None)
	resumed = await second.current_goal()
	assert resumed is not None
	assert resumed.id == goal_id

	report = await second.latest_report(contract.id)
	assert report is not None
	assert report.outcome is VerdictOutcome.SATISFIED
	assert report.contract_hash == contract.content_hash


# --------------------------------------------------------------------------- #
# the whole claim, once: a specification goes in and a working system comes out
# --------------------------------------------------------------------------- #


async def test_a_specification_becomes_a_working_system_without_a_hand_on_it(
	home: Path, tmp_path: Path
) -> None:
	"""The factory's headline claim, end to end and unattended.

	Every other test in this suite checks one joint. This one checks the claim those
	joints exist to support: a statement of intent goes in, sessions run, the artefact
	comes back refuted, the factory repairs it *itself* from the verifier's diagnosis,
	and what comes out satisfies the contract — with no operator step between the first
	session and the last, and with the repair visible in the log rather than inferred.

	The repair is real in the only sense that matters: the file the oracle asks for is
	written by the repair session and by nothing else. The synthetic child writes it for
	a goal phrased as a repair, so the oracle's first failure is the truth and its later
	success is the session's work.
	"""
	service, plan = await plan_and_service(
		home, tmp_path, "goal-repair", commands="test -f repair-marker.txt"
	)
	# The factory's own workspace, not the test's tmp dir: sessions and the tree they
	# edit live under the SoFact home, and a test that pointed at tmp_path would be
	# measuring a directory nothing wrote to.
	built = service.home / "workspace"
	assert not (built / "repair-marker.txt").exists(), "the oracle must start refuted"

	dispatched = await service.dispatch_plan(plan.id)
	refuted = await service.latest_report(plan.contract_id)
	assert refuted is not None and refuted.outcome is VerdictOutcome.VIOLATED
	assert len(dispatched) < len(plan.steps), "the plan stopped at the refuted wave"

	attempts = await service.repair_plan(plan.id)

	assert attempts, "a refuted specification must produce a repair attempt"
	assert (built / "repair-marker.txt").read_text(encoding="utf-8") == "REPAIRED", (
		"the artefact must be the repair session's work, not the test's"
	)
	final = await service.latest_report(plan.contract_id)
	assert final is not None and final.is_clean, (
		"the claim is a working system, not a verdict that says it does not work"
	)

	# And the whole thing survives being read back: nothing above is in memory.
	replayed = await FactoryService(home=home, llm=None).latest_report(plan.contract_id)
	assert replayed is not None and replayed.is_clean
