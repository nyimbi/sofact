"""The verifier's rules.

The verifier is the only place a conclusion is drawn, so these tests are mostly
about what it refuses to conclude. Three claims matter more than the rest:

* an unrun or malformed oracle yields ``INSUFFICIENT``, never a pass — an
  instrument that did not report is not an instrument that reported success;
* ``INSUFFICIENT`` outranks ``SATISFIED`` and ``VIOLATED`` outranks everything, so
  a single counterexample cannot be outvoted by corroboration;
* the verifier cannot see the executor or a completion claim, which is asserted
  structurally rather than by convention.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Mapping
from pathlib import Path

from sofact import verification
from sofact.verification import SEVERITY, verify
from sofact.views import (
	Clause,
	Contract,
	Evidence,
	EvidenceKind,
	OracleClass,
	OracleDeclaration,
	VerdictOutcome,
)

MakeOracle = Callable[..., OracleDeclaration]
MakeContract = Callable[..., Contract]

PRODUCER = "test-producer"


def observe(clause: Clause, kind: EvidenceKind, payload: Mapping[str, object]) -> Evidence:
	"""Record an observation for a clause, as the executor would."""
	return Evidence.record(
		clause_id=clause.id,
		kind=kind,
		produced_by=PRODUCER,
		payload=dict(payload),
	)


def only(contract: Contract) -> Clause:
	"""The single clause of a one-clause contract."""
	assert len(contract.clauses) == 1, "helper assumes exactly one clause"
	return contract.clauses[0]


# --------------------------------------------------------------------------- #
# structural guarantees
# --------------------------------------------------------------------------- #


def test_verifier_cannot_reach_the_executor() -> None:
	"""FR-038. A verifier able to run the oracle could arrange its own evidence.

	Asserted against the module's *imports*, not its text. The docstring has to name
	the executor in order to explain why it is never imported, so a text search would
	fail on the documentation of the very rule it checks.
	"""
	tree = ast.parse(Path(verification.__file__).read_text(encoding="utf-8"))
	imported: set[str] = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			imported.update(alias.name for alias in node.names)
		elif isinstance(node, ast.ImportFrom):
			imported.add(node.module or "")

	assert imported, "expected the verifier to import something"
	reaching = {name for name in imported if name.startswith("subprocess") or "execution" in name}
	assert not reaching, f"the verifier must not reach the executor, but imports {reaching}"


def test_verify_takes_no_completion_claim() -> None:
	"""FR-138 expressed as a signature: termination is not an input to verification."""
	assert list(inspect.signature(verify).parameters) == ["contract", "evidence"]


def test_severity_ordering_is_worst_case_dominant() -> None:
	assert SEVERITY[VerdictOutcome.VIOLATED] > SEVERITY[VerdictOutcome.INSUFFICIENT]
	assert SEVERITY[VerdictOutcome.INSUFFICIENT] > SEVERITY[VerdictOutcome.SATISFIED]


# --------------------------------------------------------------------------- #
# silence is not success
# --------------------------------------------------------------------------- #


def test_clause_with_no_evidence_is_insufficient(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(("the endpoint answers", make_oracle("true")))
	report = verify(contract, [])
	assert report.outcome is VerdictOutcome.INSUFFICIENT
	assert report.verdicts[0].outcome is VerdictOutcome.INSUFFICIENT
	assert report.verdicts[0].evidence_ids == ()
	assert not report.is_clean


def test_report_names_the_exact_contract_it_verified(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(("x holds", make_oracle("true", oracle_class=OracleClass.PROPERTY)))
	report = verify(contract, [])
	assert report.contract_id == contract.id
	assert report.contract_hash == contract.content_hash
	assert report.weakest_oracle_rank == contract.weakest_oracle_rank
	assert report.ceiling == contract.ceiling


# --------------------------------------------------------------------------- #
# command output
# --------------------------------------------------------------------------- #


def test_command_exit_zero_satisfies(make_contract: MakeContract, make_oracle: MakeOracle) -> None:
	contract = make_contract(("the build passes", make_oracle("true")))
	report = verify(
		contract, [observe(only(contract), EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0})]
	)
	assert report.outcome is VerdictOutcome.SATISFIED
	assert report.is_clean


def test_command_exit_nonzero_violates(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(("the build passes", make_oracle("true")))
	report = verify(
		contract, [observe(only(contract), EvidenceKind.COMMAND_OUTPUT, {"exit_code": 1})]
	)
	assert report.outcome is VerdictOutcome.VIOLATED
	assert "exit code 1" in report.verdicts[0].reason


def test_expected_exit_code_is_honoured(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""The criterion lives in the contract, so a nonzero expectation can pass."""
	contract = make_contract(
		("the check reports a refusal", make_oracle("exit 3", expect_exit_code=3))
	)
	report = verify(
		contract, [observe(only(contract), EvidenceKind.COMMAND_OUTPUT, {"exit_code": 3})]
	)
	assert report.outcome is VerdictOutcome.SATISFIED


def test_required_stdout_must_appear(make_contract: MakeContract, make_oracle: MakeOracle) -> None:
	"""Exit code alone is not always the obligation. Silence can be the failure."""
	contract = make_contract(
		("the CLI prints the version", make_oracle("echo ok", expect_stdout_contains="v1.2.3"))
	)
	clause = only(contract)
	missing = verify(
		contract,
		[observe(clause, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0, "stdout": "ok"})],
	)
	assert missing.outcome is VerdictOutcome.VIOLATED
	assert "v1.2.3" in missing.verdicts[0].reason

	present = verify(
		contract,
		[observe(clause, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0, "stdout": "ok v1.2.3"})],
	)
	assert present.outcome is VerdictOutcome.SATISFIED


def test_timeout_is_insufficient_not_violated(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""A hung instrument falsifies nothing. It also demonstrates nothing."""
	contract = make_contract(("the suite is fast", make_oracle("true")))
	report = verify(
		contract,
		[
			observe(
				only(contract), EvidenceKind.COMMAND_OUTPUT, {"timed_out": True, "exit_code": None}
			)
		],
	)
	assert report.outcome is VerdictOutcome.INSUFFICIENT
	assert "timed out" in report.verdicts[0].reason


def test_malformed_payload_is_never_coerced(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""A string exit code must not be coerced, and must not be read as success."""
	contract = make_contract(("x", make_oracle("true")))
	for bad in ({"exit_code": "0"}, {"exit_code": True}, {"stdout": "0"}, {}):
		report = verify(contract, [observe(only(contract), EvidenceKind.COMMAND_OUTPUT, bad)])
		assert report.outcome is VerdictOutcome.INSUFFICIENT, f"{bad} was coerced into a verdict"


# --------------------------------------------------------------------------- #
# test results
# --------------------------------------------------------------------------- #


def test_failing_tests_violate(make_contract: MakeContract, make_oracle: MakeOracle) -> None:
	contract = make_contract(("the suite passes", make_oracle("pytest")))
	report = verify(
		contract,
		[observe(only(contract), EvidenceKind.TEST_RESULT, {"passed": 9, "failed": 1})],
	)
	assert report.outcome is VerdictOutcome.VIOLATED


def test_errored_tests_violate(make_contract: MakeContract, make_oracle: MakeOracle) -> None:
	contract = make_contract(("the suite passes", make_oracle("pytest")))
	report = verify(
		contract,
		[
			observe(
				only(contract), EvidenceKind.TEST_RESULT, {"passed": 0, "failed": 0, "errors": 2}
			)
		],
	)
	assert report.outcome is VerdictOutcome.VIOLATED


def test_zero_tests_collected_is_insufficient(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""A green suite that collected nothing is the classic false oracle."""
	contract = make_contract(("the suite passes", make_oracle("pytest")))
	report = verify(
		contract,
		[observe(only(contract), EvidenceKind.TEST_RESULT, {"passed": 0, "failed": 0})],
	)
	assert report.outcome is VerdictOutcome.INSUFFICIENT
	assert "zero tests" in report.verdicts[0].reason


def test_passing_tests_satisfy(make_contract: MakeContract, make_oracle: MakeOracle) -> None:
	contract = make_contract(("the suite passes", make_oracle("pytest")))
	report = verify(
		contract,
		[observe(only(contract), EvidenceKind.TEST_RESULT, {"passed": 12, "failed": 0})],
	)
	assert report.outcome is VerdictOutcome.SATISFIED


# --------------------------------------------------------------------------- #
# property runs and digests
# --------------------------------------------------------------------------- #


def test_property_counterexample_violates(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(
		("never double-delivers", make_oracle("hypothesis", oracle_class=OracleClass.PROPERTY))
	)
	report = verify(
		contract,
		[observe(only(contract), EvidenceKind.PROPERTY_RUN, {"cases": 500, "failures": 1})],
	)
	assert report.outcome is VerdictOutcome.VIOLATED


def test_property_with_no_cases_is_insufficient(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(("never double-delivers", make_oracle("hypothesis")))
	report = verify(
		contract,
		[observe(only(contract), EvidenceKind.PROPERTY_RUN, {"cases": 0, "failures": 0})],
	)
	assert report.outcome is VerdictOutcome.INSUFFICIENT


def test_digest_mismatch_violates(make_contract: MakeContract, make_oracle: MakeOracle) -> None:
	contract = make_contract(("the artefact is unchanged", make_oracle("sha256sum")))
	clause = only(contract)
	report = verify(
		contract,
		[
			observe(
				clause,
				EvidenceKind.ARTIFACT_DIGEST,
				{"expected": "a" * 64, "actual": "b" * 64},
			)
		],
	)
	assert report.outcome is VerdictOutcome.VIOLATED

	matching = verify(
		contract,
		[observe(clause, EvidenceKind.ARTIFACT_DIGEST, {"expected": "a" * 64, "actual": "a" * 64})],
	)
	assert matching.outcome is VerdictOutcome.SATISFIED


# --------------------------------------------------------------------------- #
# dominance, orphans, and multiple observations
# --------------------------------------------------------------------------- #


def test_one_counterexample_outweighs_corroboration(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""Three passes and one failure is a failure. This is the whole point."""
	contract = make_contract(("x holds", make_oracle("true")))
	clause = only(contract)
	passed = [
		observe(clause, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0}),
		observe(clause, EvidenceKind.TEST_RESULT, {"passed": 40, "failed": 0}),
		observe(clause, EvidenceKind.PROPERTY_RUN, {"cases": 900, "failures": 0}),
	]
	report = verify(
		contract, [*passed, observe(clause, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 1})]
	)
	assert report.outcome is VerdictOutcome.VIOLATED
	assert len(report.verdicts[0].evidence_ids) == 4, "all observations should be cited"


def test_insufficient_outweighs_satisfied(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(("x holds", make_oracle("true")))
	clause = only(contract)
	report = verify(
		contract,
		[
			observe(clause, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0}),
			observe(clause, EvidenceKind.TEST_RESULT, {"passed": 0, "failed": 0}),
		],
	)
	assert report.outcome is VerdictOutcome.INSUFFICIENT


def test_evidence_for_an_unknown_clause_is_ignored(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""Unmatched evidence has no clause to satisfy, so it cannot raise a verdict."""
	contract = make_contract(("x holds", make_oracle("true")))
	orphan = make_contract(("y holds", make_oracle("true"))).clauses[0]
	report = verify(
		contract,
		[observe(orphan, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0})],
	)
	assert report.outcome is VerdictOutcome.INSUFFICIENT
	assert report.verdicts[0].evidence_ids == ()


def test_aggregate_outcome_reports_the_worst_clause(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(
		("a holds", make_oracle("true")),
		("b holds", make_oracle("true")),
		("c holds", make_oracle("true")),
	)
	first, second, third = contract.clauses
	report = verify(
		contract,
		[
			observe(first, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0}),
			observe(second, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 1}),
		],
	)
	assert len(report.satisfied) == 1
	assert len(report.violated) == 1
	assert len(report.insufficient) == 1
	assert report.outcome is VerdictOutcome.VIOLATED
	assert report.verdicts[2].clause_id == third.id
