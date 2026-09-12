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

import pytest

from sofact import verification
from sofact.verification import SEVERITY, verdict_cache_key, verify
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

RUN_ONE = "01920000-0000-7000-8000-000000000001"
RUN_TWO = "01920000-0000-7000-8000-000000000002"
"""Two distinguishable runs, so a verdict can be scoped to one of them (FR-006)."""


def observe(
	clause: Clause,
	kind: EvidenceKind,
	payload: Mapping[str, object],
	run_id: str | None = None,
) -> Evidence:
	"""Record an observation for a clause, as the executor would."""
	return Evidence.record(
		clause_id=clause.id,
		kind=kind,
		produced_by=PRODUCER,
		payload=dict(payload),
		run_id=run_id,
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
	"""FR-138 expressed as a signature: termination is not an input to verification.

	Two properties, not one spelling: nothing is accepted positionally beyond the
	evidence, and no parameter is annotated with anything claim-shaped. Pinning the exact
	list of names would fail on every legitimate addition while proving neither — the
	question is whether a claim *could* be passed, not what the extras happen to be.
	"""
	parameters = inspect.signature(verify).parameters
	positional = [
		name
		for name, parameter in parameters.items()
		if parameter.kind is not inspect.Parameter.KEYWORD_ONLY
	]
	assert positional == ["contract", "evidence"]
	assert not any("claim" in name.lower() for name in parameters)
	annotated = " ".join(str(parameter.annotation) for parameter in parameters.values())
	assert "Claim" not in annotated, (
		f"a verdict cannot take a claim, but annotation is {annotated!r}"
	)


def test_a_verdict_can_be_scoped_to_one_run(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""FR-006: a result older than the change under test is invalid.

	The same clause, observed failing and then passing, must be able to turn green —
	otherwise a repair step could never succeed, and the log would answer a provenance
	question while wearing the name of a status one.
	"""
	contract = make_contract(("the endpoint answers", make_oracle("true")))
	clause = only(contract)
	stale = observe(clause, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 1}, run_id=RUN_ONE)
	fresh = observe(clause, EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0}, run_id=RUN_TWO)

	assert verify(contract, [stale, fresh]).outcome is VerdictOutcome.VIOLATED, (
		"unscoped, history still dominates: that is the provenance question"
	)
	assert verify(contract, [stale, fresh], run_id=RUN_TWO).outcome is VerdictOutcome.SATISFIED
	assert verify(contract, [stale, fresh], run_id=RUN_ONE).outcome is VerdictOutcome.VIOLATED


def test_scoping_to_a_run_that_observed_nothing_is_insufficient(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""An unrun oracle must not inherit the verdict of a different run."""
	contract = make_contract(("the endpoint answers", make_oracle("true")))
	passed = observe(only(contract), EvidenceKind.COMMAND_OUTPUT, {"exit_code": 0}, run_id=RUN_ONE)

	report = verify(contract, [passed], run_id=RUN_TWO)
	assert report.outcome is VerdictOutcome.INSUFFICIENT
	assert report.verdicts[0].reason == "no evidence was recorded for this clause"


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


def test_a_truthy_stand_in_for_timed_out_is_not_a_pass(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""``1`` is not ``True``. Reading it as falsy would skip the timeout branch and
	let the stale exit code beside it satisfy the clause — a malformed payload turned
	into a green light, which is the one direction this must never fail in."""
	contract = make_contract(("the suite is fast", make_oracle("true")))
	for stand_in in (1, "true", "yes", [1]):
		report = verify(
			contract,
			[
				observe(
					only(contract),
					EvidenceKind.COMMAND_OUTPUT,
					{"timed_out": stand_in, "exit_code": 0},
				)
			],
		)
		assert report.outcome is VerdictOutcome.INSUFFICIENT, f"{stand_in!r} produced a verdict"
		assert "non-boolean timed_out" in report.verdicts[0].reason


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


# --------------------------------------------------------------------------- #
# the cache key (FR-006's second half)
# --------------------------------------------------------------------------- #


class TestTheCacheKey:
	"""FR-006 names three inputs — the contract, the change, the oracle set — and the
	key must name them all, because a reuse that could not say what it held constant
	could not be audited."""

	def test_the_same_contract_and_change_key_the_same(
		self, make_contract: MakeContract, make_oracle: MakeOracle
	) -> None:
		contract = make_contract(("it holds", make_oracle("true")))
		assert verdict_cache_key(contract, "digest-1") == verdict_cache_key(contract, "digest-1")

	def test_a_different_change_keys_differently(
		self, make_contract: MakeContract, make_oracle: MakeOracle
	) -> None:
		contract = make_contract(("it holds", make_oracle("true")))
		assert verdict_cache_key(contract, "digest-1") != verdict_cache_key(contract, "digest-2")

	def test_a_different_contract_keys_differently(
		self, make_contract: MakeContract, make_oracle: MakeOracle
	) -> None:
		"""Statements are part of the key: verdicts are phrased per clause."""
		first = make_contract(("it holds", make_oracle("true")))
		second = make_contract(("it holds, differently", make_oracle("true")))
		assert verdict_cache_key(first, "digest") != verdict_cache_key(second, "digest")

	def test_a_different_oracle_set_keys_differently(
		self, make_contract: MakeContract, make_oracle: MakeOracle
	) -> None:
		"""The oracle definition is FR-006's named component, so it keys on its own."""
		first = make_contract(("it holds", make_oracle("true")))
		second = make_contract(("it holds", make_oracle("false")))
		assert verdict_cache_key(first, "digest") != verdict_cache_key(second, "digest")

	def test_a_keyed_report_names_its_key_and_its_run(
		self, make_contract: MakeContract, make_oracle: MakeOracle
	) -> None:
		contract = make_contract(("it holds", make_oracle("true")))
		report = verify(contract, (), run_id=RUN_ONE, cache_key="key-1")

		assert report.cache_key == "key-1"
		assert report.run_id == RUN_ONE
		assert report.reused_from is None

	def test_an_unkeyed_report_is_recorded_as_never_reusable(
		self, make_contract: MakeContract, make_oracle: MakeOracle
	) -> None:
		"""An empty key is the honest default: nothing was hashed, so nothing is reused."""
		contract = make_contract(("it holds", make_oracle("true")))
		report = verify(contract, ())

		assert report.cache_key == ""
		assert report.run_id == ""
		assert report.reused_from is None

	def test_a_cache_key_without_a_run_id_is_refused(
		self, make_contract: MakeContract, make_oracle: MakeOracle
	) -> None:
		"""A reuse nobody can trace to the run it stands on is not a reuse."""
		contract = make_contract(("it holds", make_oracle("true")))
		with pytest.raises(AssertionError, match="without a run id"):
			verify(contract, (), cache_key="key-1")
