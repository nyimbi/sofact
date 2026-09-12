"""The verifier: decides what observations mean.

This module is deliberately independent of :mod:`sofact.execution`. The executor
produces observations; the verifier judges them. A verifier able to call the executor
could arrange the evidence it is about to weigh, which is precisely the coupling
FR-038 forbids. The dependency is one-way and a test scans this file's imports to
keep it that way.

Nothing here reads a clock other than to timestamp its own report, and nothing here
touches a file or the network. :func:`verify` is a pure function of a contract and a
set of observations, which is what makes a verdict reproducible from the log alone.

The design rule throughout: **never trust a producer's payload shape.** Every field
is type-checked before use, and anything unexpected yields ``INSUFFICIENT``. A
verifier that coerced a malformed payload into a pass would be a verifier that a
careless producer could steer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from sofact.contract import oracle_set_hash
from sofact.views import (
	Clause,
	ClauseVerdict,
	Contract,
	Evidence,
	EvidenceKind,
	OracleDeclaration,
	VerdictOutcome,
	VerificationReport,
	content_hash,
	now,
)

__all__ = ["SEVERITY", "verdict_cache_key", "verify"]

Rule = Callable[[OracleDeclaration, dict[str, object]], "tuple[VerdictOutcome, str]"]

SEVERITY: dict[VerdictOutcome, int] = {
	VerdictOutcome.SATISFIED: 0,
	VerdictOutcome.INSUFFICIENT: 1,
	VerdictOutcome.VIOLATED: 2,
}
"""Worst-case dominance ordering. One counterexample outweighs any corroboration."""


def _as_int(value: object) -> int | None:
	"""Narrow to ``int``, rejecting ``bool`` (which is an ``int`` in Python)."""
	if isinstance(value, bool):
		return None
	return value if isinstance(value, int) else None


def _as_str(value: object) -> str | None:
	return value if isinstance(value, str) else None


def _as_bool(value: object) -> bool | None:
	"""Narrow to ``bool``, so a truthy stand-in is never read as agreement.

	``1``, ``"true"`` and ``"yes"`` are all truthy and none of them is the runner's
	flag. Treating one as ``False`` would be the dangerous direction here: the timeout
	branch would be skipped and a stale ``exit_code`` beside it could satisfy the
	clause. ``None`` means "not a boolean", never "false".
	"""
	return value if isinstance(value, bool) else None


def verdict_cache_key(contract: Contract, artefact_digest: str) -> str:
	"""FR-006's key: content hash of the contract, the change, and the oracle set.

	FR-139 pins three hashes separately because a single hash can only say *that*
	something moved. The cache key names all three for the same reason: a reuse that
	could not say which inputs it held constant would be a reuse nobody could audit.

	``contract`` — the clause set the verdicts are phrased against, statements included.
	Reusing a verdict across a contract whose *statements* moved would attach old words
	to new clauses, which no digest of the oracles alone can catch.

	``change`` — the digest of the artefact tree, computed by the caller. This module
	never touches a file, so the digest arrives rather than being read here.

	``oracles`` — ``oracle_set_hash``, FR-006's named component. Redundant while the
	oracle set is derived from the contract, and kept on purpose: the requirement names
	the oracle definition, so the key names it too, and a future change to that
	derivation is caught by the key instead of silently re-keying every verdict.
	"""
	assert contract.clauses, "cannot key a verdict for a contract with no clauses"
	assert artefact_digest, "an artefact digest must not be empty"
	return content_hash(
		{
			"contract": contract.content_hash,
			"change": artefact_digest,
			"oracles": oracle_set_hash(contract),
		},
	)


# --------------------------------------------------------------------------- #
# per-kind rules
# --------------------------------------------------------------------------- #


def _command_output(
	oracle: OracleDeclaration,
	payload: dict[str, object],
) -> tuple[VerdictOutcome, str]:
	"""An oracle was run. The criterion comes from the contract, the observation
	from the evidence — never both from the same place."""
	timed_out = _as_bool(payload.get("timed_out"))
	if timed_out is None and "timed_out" in payload:
		return (
			VerdictOutcome.INSUFFICIENT,
			f"evidence carries a non-boolean timed_out ({payload['timed_out']!r})",
		)
	if timed_out:
		return (
			VerdictOutcome.INSUFFICIENT,
			"the oracle timed out, so the clause was neither demonstrated nor refuted",
		)
	exit_code = _as_int(payload.get("exit_code"))
	if exit_code is None:
		return VerdictOutcome.INSUFFICIENT, "evidence carries no integer exit_code"
	stdout = _as_str(payload.get("stdout")) or ""
	required = oracle.expect_stdout_contains
	if required is not None and required not in stdout:
		return VerdictOutcome.VIOLATED, f"stdout did not contain {required!r}"
	if exit_code != oracle.expect_exit_code:
		return (
			VerdictOutcome.VIOLATED,
			f"exit code {exit_code}, expected {oracle.expect_exit_code}",
		)
	return VerdictOutcome.SATISFIED, f"exit code {exit_code} and required output present"


def _test_result(
	oracle: OracleDeclaration,
	payload: dict[str, object],
) -> tuple[VerdictOutcome, str]:
	failed = _as_int(payload.get("failed"))
	passed = _as_int(payload.get("passed"))
	errors = _as_int(payload.get("errors")) or 0
	if failed is None or passed is None:
		return VerdictOutcome.INSUFFICIENT, "evidence lacks integer passed/failed counts"
	if failed or errors:
		return VerdictOutcome.VIOLATED, f"{failed} test(s) failed, {errors} errored"
	if passed == 0:
		return (
			VerdictOutcome.INSUFFICIENT,
			"the suite ran zero tests, which demonstrates nothing",
		)
	return VerdictOutcome.SATISFIED, f"{passed} test(s) passed"


def _property_run(
	oracle: OracleDeclaration,
	payload: dict[str, object],
) -> tuple[VerdictOutcome, str]:
	cases = _as_int(payload.get("cases"))
	failures = _as_int(payload.get("failures"))
	if cases is None or failures is None:
		return VerdictOutcome.INSUFFICIENT, "evidence lacks integer cases/failures counts"
	if failures:
		return VerdictOutcome.VIOLATED, f"{failures} counterexample(s) found"
	if cases == 0:
		return VerdictOutcome.INSUFFICIENT, "no cases were generated, which exercises nothing"
	return VerdictOutcome.SATISFIED, f"{cases} case(s) held with no counterexample"


def _artifact_digest(
	oracle: OracleDeclaration,
	payload: dict[str, object],
) -> tuple[VerdictOutcome, str]:
	expected = _as_str(payload.get("expected"))
	actual = _as_str(payload.get("actual"))
	if expected is None or actual is None:
		return VerdictOutcome.INSUFFICIENT, "evidence lacks string expected/actual digests"
	if expected != actual:
		return (
			VerdictOutcome.VIOLATED,
			f"digest {actual[:12]}… does not match {expected[:12]}…",
		)
	return VerdictOutcome.SATISFIED, "artifact digest matches"


_RULES: dict[EvidenceKind, Rule] = {
	EvidenceKind.COMMAND_OUTPUT: _command_output,
	EvidenceKind.TEST_RESULT: _test_result,
	EvidenceKind.PROPERTY_RUN: _property_run,
	EvidenceKind.ARTIFACT_DIGEST: _artifact_digest,
}


# --------------------------------------------------------------------------- #
# the verdict
# --------------------------------------------------------------------------- #


def _decide(clause: Clause, observations: tuple[Evidence, ...]) -> ClauseVerdict:
	"""Weigh every observation for one clause, worst-case dominant."""
	if not observations:
		return ClauseVerdict(
			clause_id=clause.id,
			statement=clause.statement,
			outcome=VerdictOutcome.INSUFFICIENT,
			reason="no evidence was recorded for this clause",
			evidence_ids=(),
		)

	decided: list[tuple[int, VerdictOutcome, str, Evidence]] = []
	for item in observations:
		rule = _RULES.get(item.kind)
		if rule is None:
			outcome = VerdictOutcome.INSUFFICIENT
			reason = f"unrecognised evidence kind {item.kind.value!r}"
		else:
			outcome, reason = rule(clause.oracle, item.payload)
		decided.append((SEVERITY[outcome], outcome, reason, item))

	_, outcome, reason, _ = max(decided, key=lambda entry: entry[0])
	return ClauseVerdict(
		clause_id=clause.id,
		statement=clause.statement,
		outcome=outcome,
		reason=reason,
		evidence_ids=tuple(entry[3].id for entry in decided),
	)


def verify(
	contract: Contract,
	evidence: Iterable[Evidence],
	*,
	run_id: str | None = None,
	cache_key: str = "",
) -> VerificationReport:
	"""Render a verdict for every clause of ``contract``.

	Accepts no :class:`~sofact.views.CompletionClaim` — the signature has nowhere to
	put one. That is FR-138 expressed as a type rather than as a rule someone has to
	remember: a producer may declare victory, and the declaration is simply not an
	input here.

	Evidence pointing at clauses outside ``contract`` is ignored, and cannot raise the
	verdict: unmatched observations have no clause to satisfy.

	``run_id`` scopes the verdict to **one** execution of the oracle set. Without it,
	every observation the log holds is weighed worst-case, which answers *"has this
	clause ever failed?"* — a provenance question. FR-006 asks the other one: a result
	older than the change under test is invalid, so a stale failure must not decide a
	later state. Left unscoped, a repaired clause could never turn green and a repair
	step could never succeed, which would make the repair tier of a goal plan
	unobservable rather than merely hard. Worst-case dominance survives *within* a run,
	where several observations of one clause genuinely compete.

	``cache_key`` is a stamp, not a computation: the caller hashes the artefact (this
	function never touches a file) and hands the key in. A report without one is
	recorded as never reusable, which is the honest default — FR-006 forbids inferring a
	cache hit from inputs nobody hashed.
	"""
	assert contract.clauses, "cannot verify a contract with no clauses"
	assert run_id is None or run_id, "a run id, when given, must name a run"

	by_clause: dict[str, list[Evidence]] = {}
	for item in evidence:
		if run_id is not None and item.run_id != run_id:
			continue
		by_clause.setdefault(item.clause_id, []).append(item)

	verdicts = tuple(_decide(c, tuple(by_clause.get(c.id, ()))) for c in contract.clauses)
	assert len(verdicts) == len(contract.clauses), "every clause must receive a verdict"

	assert run_id is not None or not cache_key, (
		"a cache key without a run id would reuse evidence nobody can name"
	)
	return VerificationReport(
		contract_id=contract.id,
		contract_hash=contract.content_hash,
		weakest_oracle_rank=contract.weakest_oracle_rank,
		ceiling=contract.ceiling,
		verdicts=verdicts,
		at=now(),
		run_id=run_id or "",
		cache_key=cache_key,
	)
