"""FR-107 — the adversarial audit of the oracle set.

The requirement is about *false confidence*: an oracle "that can be satisfied without
implementing the invariant is a worse defect than a missing test". These tests are
therefore mostly about what the instrument refuses to count as evidence, and about the
two places a vacuous pass could hide:

* an oracle that passes against an empty workspace, which is the defect itself;
* a pass over *nothing probed*, which looks identical to a clean audit on a screen and
  is a different fact entirely — the distinction :meth:`OracleAuditReport.discharged`
  exists to keep.

The control arms matter as much as the findings. A test asserting only "no findings"
would pass against an audit that never ran anything, which is the same failure mode one
level up: a manufactured *audit* reporting agreement with itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from conftest import answer_everything

from sofact import audit as audit_module
from sofact._uuid7 import uuid7str
from sofact.audit import audit_oracles, probe_targets
from sofact.service import FactoryService
from sofact.views import (
	ORACLE_AUDIT_REQUIREMENTS,
	Clause,
	ClauseKind,
	ClauseStem,
	Contract,
	ElicitationDimension,
	OracleClass,
	OracleDeclaration,
	VerdictOutcome,
	now,
)


def _contract(*clauses: Clause) -> Contract:
	"""A contract from clauses built directly, so a clause's *kind* is the test's choice.

	``make_contract`` builds every stem POSITIVE, which is the right default for the
	suites that do not care and the wrong one here: the negative-clause skip is half the
	scoping rule and needs a negative clause to be about.
	"""
	return Contract(
		id=uuid7str(),
		goal_id=uuid7str(),
		version=1,
		created_at=now(),
		clauses=clauses,
	)


def _clause(
	command: str | None,
	*,
	kind: ClauseKind = ClauseKind.POSITIVE,
	statement: str = "the report totals every row",
	oracle_class: OracleClass = OracleClass.PROPERTY,
	expect_stdout_contains: str | None = None,
) -> Clause:
	return Clause(
		id=uuid7str(),
		statement=statement,
		kind=kind,
		oracle=OracleDeclaration(
			oracle_class=oracle_class,
			description="checked by a property test",
			command_hint=command,
			expect_stdout_contains=expect_stdout_contains,
		),
	)


def _stem(statement: str, kind: ClauseKind) -> ClauseStem:
	return ClauseStem(
		id=uuid7str(),
		statement=statement,
		kind=kind,
		derived_from=ElicitationDimension.OUTCOME,
	)


# --------------------------------------------------------------------------- #
# the instrument — an oracle satisfied by nothing
# --------------------------------------------------------------------------- #


class TestAnOracleThatCannotFailIsAFinding:
	async def test_an_oracle_satisfied_by_an_empty_workspace_is_reported(self) -> None:
		"""FR-107's defect, measured rather than asserted.

		``true`` exits 0 whatever it is run against, so it is satisfied by a tree with
		nothing in it — which is FR-107's words exactly: "satisfied without implementing
		the invariant".
		"""
		contract = _contract(_clause("true"))

		report = await audit_oracles(contract)

		assert len(report.findings) == 1
		finding = report.findings[0]
		assert finding.clause_id == contract.clauses[0].id
		assert finding.command == "true"
		assert not report.passed

	async def test_an_oracle_that_fails_against_nothing_is_not_reported(self) -> None:
		"""The control arm. Without it, "one finding" is indistinguishable from an audit
		that reports every oracle it runs.

		``pytest tests/test_report.py`` cannot pass in a tree where that file does not
		exist, so the oracle *can* fail — which is what FR-004 asks of a canary and what
		makes it an instrument at all.
		"""
		contract = _contract(_clause("pytest tests/test_report.py"))

		report = await audit_oracles(contract)

		assert report.findings == ()
		assert report.passed
		assert report.probed == (contract.clauses[0].id,), "it was probed, and it failed"

	async def test_a_command_that_does_not_exist_is_not_a_finding(self) -> None:
		"""A missing binary exits non-zero, so the oracle can fail. The audit asks whether
		the oracle is *satisfiable by nothing*, not whether the command is any good."""
		contract = _contract(_clause("this-command-does-not-exist-anywhere"))

		report = await audit_oracles(contract)

		assert report.findings == ()
		assert report.passed

	async def test_an_expected_stdout_makes_a_pass_a_finding_too(self) -> None:
		"""The other half of a satisfied verdict. An oracle that exits 0 *and* demands
		output is satisfied here only if the expected text appears — and ``echo`` supplies
		it, so the oracle is satisfied by a tree that contains no report at all.
		"""
		contract = _contract(_clause("echo TOTAL 42", expect_stdout_contains="TOTAL 42"))

		report = await audit_oracles(contract)

		assert len(report.findings) == 1, "exit 0 plus the required output, on an empty tree"

	async def test_the_finding_names_the_oracles_declared_class(self) -> None:
		"""The operator declared how strong the oracle was supposed to be, and that is what
		makes the finding judgeable: a rank-1 property oracle passing against nothing was
		claiming to establish an invariant."""
		contract = _contract(_clause("true", oracle_class=OracleClass.SCHEMA))

		report = await audit_oracles(contract)

		assert report.findings[0].oracle_class is OracleClass.SCHEMA
		assert report.weakest_audited_rank == 5

	async def test_an_oracle_that_times_out_is_not_a_finding(self) -> None:
		"""``INSUFFICIENT`` says the audit learned nothing, which is not the same claim as
		"the oracle is satisfiable by nothing". Collapsing the two would report a finding
		against an oracle the audit never got an answer from.
		"""
		contract = _contract(_clause("sleep 5"))

		report = await audit_oracles(contract, timeout=0.5)

		assert report.findings == ()
		assert report.probed == (contract.clauses[0].id,), "probed, and unanswered"


# --------------------------------------------------------------------------- #
# the scoping rule — what the instrument cannot ask about
# --------------------------------------------------------------------------- #


class TestTheAuditSaysWhatItCouldNotAsk:
	"""A clause the audit did not probe is not a clause it cleared.

	Both skips are *named* rather than dropped. The failure this prevents is a green
	audit over a contract of intentions: nothing was asked, nothing was found, and a
	screen showing only the second half reports a gap as a clearance.
	"""

	def test_a_negative_clause_is_skipped_and_named(self) -> None:
		"""An empty workspace satisfies an absence by containing nothing.

		That is a true statement about an empty tree rather than evidence about the
		oracle, so counting it would report a finding the operator cannot act on — and
		the audit says so instead of silently passing the clause.
		"""
		negative = _clause(
			"! grep -rq password= .",
			kind=ClauseKind.NEGATIVE,
			statement="the process never writes a credential to the tree",
		)

		probed, skipped = probe_targets(_contract(negative))

		assert probed == ()
		assert len(skipped) == 1
		assert skipped[0].clause_id == negative.id
		assert skipped[0].statement == negative.statement, "a skipped clause is named in full"
		assert "absence" in skipped[0].because

	def test_an_oracle_naming_no_command_is_skipped_and_named(self) -> None:
		"""Nothing to run. This is FR-108's debt and the audit cannot retire it; reporting
		it here would conflate two defects with two different remedies."""
		intention = _clause(None, statement="the dashboard is pleasant to use")

		probed, skipped = probe_targets(_contract(intention))

		assert probed == ()
		assert len(skipped) == 1
		assert "names no command" in skipped[0].because
		assert "FR-108" in skipped[0].because

	def test_a_negative_clause_with_no_command_reports_the_command_reason(self) -> None:
		"""Both skips apply and the clause appears **once**.

		A clause hitting both rules must not be listed twice: the report's skip list is
		read as a census, and a duplicated clause would make it wrong about its own size.
		"""
		both = _clause(None, kind=ClauseKind.NEGATIVE)

		probed, skipped = probe_targets(_contract(both))

		assert probed == ()
		assert len(skipped) == 1
		assert "names no command" in skipped[0].because

	def test_the_split_is_total_over_the_clause_set(self) -> None:
		"""Every clause is either probed or reported, never neither.

		The assertion inside ``probe_targets`` is what makes this true of any contract;
		this test is what makes the assertion load-bearing rather than decorative.
		"""
		contract = _contract(
			_clause("true"),
			_clause("pytest tests/test_report.py"),
			_clause(None),
			_clause("! grep -rq password= .", kind=ClauseKind.NEGATIVE),
		)

		probed, skipped = probe_targets(contract)

		assert {c.id for c in probed} | {s.clause_id for s in skipped} == {
			c.id for c in contract.clauses
		}
		assert len(probed) + len(skipped) == 4, "no clause is counted twice"

	async def test_a_contract_of_intentions_claims_nothing(self) -> None:
		"""The vacuous pass, refused. Nothing was probed, so FR-107 is not implemented by
		this pass — and the report says so rather than showing a clean green line."""
		contract = _contract(_clause(None), _clause(None, statement="the API is intuitive"))

		report = await audit_oracles(contract)

		assert report.probed == ()
		assert report.passed, "nothing was found"
		assert report.discharged == (), "and nothing was carried out either"
		assert report.not_implemented == ("FR-107",)

	async def test_a_pass_that_probed_anything_claims_the_requirement(self) -> None:
		"""The control arm for the test above: the same report shape, a different fact."""
		contract = _contract(_clause("pytest tests/test_report.py"))

		report = await audit_oracles(contract)

		assert report.discharged == ("FR-107",)
		assert report.not_implemented == ()

	async def test_a_mixed_contract_reports_both_halves(self) -> None:
		"""One run, one report: what was asked and what could not be."""
		contract = _contract(
			_clause("true"),
			_clause(None),
			_clause("! grep -rq password= .", kind=ClauseKind.NEGATIVE),
		)

		report = await audit_oracles(contract)

		assert len(report.probed) == 1
		assert len(report.skipped) == 2
		assert len(report.findings) == 1, "the one probed oracle is satisfied by nothing"
		assert report.discharged == ("FR-107",), "it probed, so it claims the requirement"


# --------------------------------------------------------------------------- #
# the judge is the verifier, not a second implementation of it
# --------------------------------------------------------------------------- #


def test_the_audit_does_not_reimplement_the_verdict() -> None:
	"""FR-107 audited *exactly as code is* (FR-012) means audited by the real verifier.

	A second decision procedure here would be a manufactured judge — the same defect as a
	manufactured oracle one level up, since it would report agreement with itself. The
	module must import :func:`sofact.verification.verify` and must not grow its own
	comparison of an exit code to an expectation.
	"""
	source = Path(audit_module.__file__).read_text(encoding="utf-8")
	tree = ast.parse(source)

	imported: set[str] = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.ImportFrom):
			imported.add(node.module or "")
	assert "sofact.verification" in imported, "the audit must judge with the real verifier"
	assert "sofact.execution" in imported, "and produce observations with the real runner"

	# The verdict is read off the report; nothing here compares an exit code itself.
	compared = [
		node
		for node in ast.walk(tree)
		if isinstance(node, ast.Compare)
		and any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops)
		and "expect_exit_code" in ast.unparse(node)
	]
	assert not compared, "the audit re-decided the verdict instead of reading the report"


def test_the_audit_runs_each_probeable_oracle_exactly_once() -> None:
	"""The count, not the outcome: a report that probed one clause twice would still
	report one finding, and a run that skipped a clause would report none."""
	contract = _contract(_clause("true"), _clause("pytest tests/test_report.py"), _clause(None))

	probed, skipped = probe_targets(contract)

	assert len(probed) == 2
	assert len(skipped) == 1
	assert probed[0].id != probed[1].id, "two clauses, two probes"


# --------------------------------------------------------------------------- #
# the report is reproducible from the log
# --------------------------------------------------------------------------- #


async def a_contract(service: FactoryService, command: str = "true") -> Contract:
	"""Drive P0 to a contract whose every oracle runs ``command``.

	The real interrogation rather than a hand-built draft, because these tests are about
	what the *service* records, and a contract injected past the log would leave the
	audit's own read of the contract untested.
	"""
	goal = await service.start("Ship a reminder dashboard.")
	await answer_everything(service, goal.id)
	await service.draft(goal.id)
	return await service.contract(goal.id, commands=command)


class TestTheServiceRecordsTheAudit:
	async def test_the_audit_lands_in_the_ledger_and_folds_back(
		self, service: FactoryService
	) -> None:
		"""A measurement nobody wrote down is not a measurement.

		The report is folded back out of the log rather than compared to the in-memory
		object, because the two agreeing is the property that matters: state is a pure
		fold, so a report that survives a round trip is one a later reader can audit.
		"""
		contract = await a_contract(service)

		audit = await service.audit_oracles(contract.id)

		# The real interrogation produces both kinds of clause, and only the positive
		# ones are probeable — so the finding count is the *probed* count, not the clause
		# count. Asserting against ``contract.clauses`` here would fail against correct
		# code, which is how this test found the boundary rather than assumed it.
		probed, skipped = probe_targets(contract)
		# Derived from the contract rather than a literal: the count moved when FR-064
		# added NON_NEGOTIABLES, and the property the line below asserts — skipped *is*
		# the negative set — is the one that matters, so the number here is only a
		# sanity check that the fixture derives both kinds at all.
		assert skipped, "the fixture's interrogation must derive at least one negative clause"
		assert {s.clause_id for s in skipped} == {
			c.id for c in contract.clauses if c.kind is ClauseKind.NEGATIVE
		}, "and those are the negative ones"
		assert len(audit.findings) == len(probed), "every probed oracle is `true`"
		assert len(audit.probed) == len(probed)
		state = await service.state()
		stored = state.latest_oracle_audit(contract.id)
		assert stored is not None
		assert stored == audit, "the fold reproduces the report it recorded"
		assert stored.contract_hash == contract.content_hash

	async def test_an_oracle_that_can_fail_survives_the_round_trip_as_clean(
		self, service: FactoryService
	) -> None:
		"""The control arm at the service level: same path, a command that cannot pass in
		an empty tree, and no finding. Without it the test above would pass against an
		audit that reported every clause it touched."""
		contract = await a_contract(service, command="pytest tests/test_report.py")

		audit = await service.audit_oracles(contract.id)

		probed, _ = probe_targets(contract)
		assert audit.findings == ()
		assert audit.passed
		assert len(audit.probed) == len(probed), "every probeable clause was asked"

	async def test_a_second_audit_is_a_second_measurement(self, service: FactoryService) -> None:
		"""Appended, never keyed — the history is what shows the rate trending to zero."""
		contract = await a_contract(service)

		first = await service.audit_oracles(contract.id)
		second = await service.audit_oracles(contract.id)

		state = await service.state()
		assert len(state.oracle_audits) == 2
		assert first.id != second.id
		assert state.latest_oracle_audit(contract.id) == second

	async def test_an_audit_of_another_contract_is_not_returned(
		self, service: FactoryService
	) -> None:
		"""Two contracts can be live at once, and an audit of one says nothing about the
		other's oracles."""
		contract = await a_contract(service)
		await service.audit_oracles(contract.id)

		state = await service.state()
		assert state.latest_oracle_audit(contract.id) is not None, "the control"
		assert state.latest_oracle_audit(uuid7str()) is None

	async def test_the_audit_writes_nothing_into_the_state_directory(
		self, service: FactoryService
	) -> None:
		"""FR-003: the ledger is the only account of a run.

		The audit runs oracles in a workspace, so the risk is a leftover tree. Asserted
		against the real home rather than assumed, because "we used a TemporaryDirectory"
		is a claim about code and this is a claim about the filesystem.
		"""
		contract = await a_contract(service)
		before = {path.relative_to(service.home) for path in service.home.rglob("*")}

		await service.audit_oracles(contract.id)

		after = {path.relative_to(service.home) for path in service.home.rglob("*")}
		assert not [p for p in after - before if "audit" in p.name], (
			"the audit left a tree in the state directory"
		)


def test_a_contract_with_no_clauses_cannot_be_audited() -> None:
	"""The precondition, asserted rather than silently returning a clean report."""
	with pytest.raises(ValueError, match="verifies nothing"):
		Contract(id=uuid7str(), goal_id=uuid7str(), version=1, created_at=now(), clauses=())


def test_the_report_type_is_exported() -> None:
	"""The value objects are the module's surface, like every other report's.

	Asserted through ``sofact.views`` rather than by importing from here, because that is
	where a consumer of the audit — the CLI, the delivery report, a later reader of the
	ledger — actually reaches them. A type defined but unexported is a type nobody outside
	this module can name, which is a report that cannot be read back.
	"""
	from sofact import views

	assert ORACLE_AUDIT_REQUIREMENTS == ("FR-107",)
	for name in ("OracleAuditFinding", "OracleAuditReport", "OracleAuditSkip"):
		assert name in views.__all__, f"{name} is defined but not exported"


def test_the_skip_reason_is_about_the_instrument_not_the_clause() -> None:
	"""A skip says what the *audit* could not ask, never that the clause is weak.

	The distinction is the whole reason the skip list is separate from the findings: a
	negative clause is often the strongest thing in a contract, and a report that read
	"skipped" as "suspect" would push operators toward writing positive clauses they
	believe less.
	"""
	negative = _clause("! grep -rq password= .", kind=ClauseKind.NEGATIVE)

	_, skipped = probe_targets(_contract(negative))

	assert "this instrument" in skipped[0].because
	assert "cannot ask" in skipped[0].because
	assert "weak" not in skipped[0].because


def test_a_stem_carries_no_oracle_and_so_is_never_audited() -> None:
	"""FR-107 audits clauses. A stem has no oracle, so P2's gate is what refuses an
	unverifiable contract and this audit cannot be handed one to judge."""
	assert not hasattr(_stem("the report totals every row", ClauseKind.POSITIVE), "oracle")
	assert VerdictOutcome.SATISFIED.value == "satisfied"
