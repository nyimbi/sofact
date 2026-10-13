"""FR-107 — the adversarial audit of the oracle set.

FR-107: "Oracle manufacturing must be **adversarially audited** exactly as code is
(FR-012). A manufactured oracle that can be satisfied without implementing the invariant
is a worse defect than a missing test, because it manufactures false confidence."

The instrument is FR-004's must-fail canary, and the known-bad input is the one input
every language has: **an empty workspace**. FR-004 requires every oracle to be
canary-tested each cycle with "a known-good input that must pass, and a known-bad input
(seeded mutant) that must fail". A seeded mutant needs the operator's language and a
working toolchain, which SoFact does not have (ADR-0025) — but an empty tree needs
neither, and it is the strictly harder case: an oracle that passes against *nothing*
would pass against any mutant, so it cannot be a canary at all.

So the measurement is one run per clause and one reading of it: an oracle that reports
SATISFIED against an empty workspace was satisfied without implementing anything. That is
FR-107's defect, stated as something a machine can observe rather than as something a
reviewer has to notice.

**The judge is the real verifier.** :func:`~sofact.verification.verify` decides what the
observation means, exactly as it does at P6, and :class:`~sofact.execution.OracleRunner`
produces it, exactly as it does at P6. Re-deciding "was this satisfied?" here would be a
second implementation of the one rule the factory is built on, and a manufactured *judge*
is the same defect as a manufactured oracle one level up: it would report agreement with
itself. The audit differs from P6 only in the workspace and in what it does with a pass.

**What is deliberately not probed, and why the audit says so rather than passing it.**

* **Negative clauses.** A negative clause asserts an absence — "the process never writes
  outside its workspace". An empty workspace satisfies an absence by containing nothing,
  so the oracle reports SATISFIED for a reason that is true and uninformative. That is a
  true statement about an empty tree, not a weak oracle, and counting it would report a
  finding the operator cannot act on. This is a real limit of the empty-workspace
  instrument and it is why the skip list exists: a clause the audit could not ask about is
  not a clause it cleared.
* **Oracles naming no command.** There is nothing to run. That is FR-108's ground-truth
  debt and the audit cannot retire it; reporting it here as a finding would conflate two
  defects with two different remedies, which is the mistake
  :class:`~sofact.views.UnverifiedClause` already refuses one phase later.

Both lists are reported on the report, so a green audit over a contract of intentions
reads as "nothing was asked" rather than as "nothing was wrong" — the same distinction
:attr:`~sofact.views.IntegrationCheck.discharged` draws for P7.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sofact._uuid7 import uuid7str
from sofact.execution import DEFAULT_MAX_OUTPUT_BYTES, DEFAULT_TIMEOUT_SECONDS, OracleRunner
from sofact.verification import verify
from sofact.views import (
	Clause,
	ClauseKind,
	Contract,
	OracleAuditFinding,
	OracleAuditReport,
	OracleAuditSkip,
	VerdictOutcome,
	now,
)

__all__ = ["EMPTY_WORKSPACE_INSTRUMENT", "audit_oracles", "probe_targets"]

EMPTY_WORKSPACE_INSTRUMENT = (
	"an oracle that reports satisfied against an empty workspace was satisfied without "
	"implementing anything, which is FR-107's defect"
)
"""The instrument, stated once so the report and its reader use the same sentence."""


def probe_targets(contract: Contract) -> tuple[tuple[Clause, ...], tuple[OracleAuditSkip, ...]]:
	"""Split a contract's clauses into what the instrument can ask about and what it cannot.

	Separated from :func:`audit_oracles` because it is the whole scoping rule and it needs
	no process to run: a test can hold it to the boundary — that a negative clause is
	skipped and *named* rather than quietly dropped — without spawning anything.
	"""
	assert contract.clauses, "cannot audit a contract with no clauses"
	probed: list[Clause] = []
	skipped: list[OracleAuditSkip] = []
	for clause in contract.clauses:
		if not clause.oracle.is_executable:
			skipped.append(
				OracleAuditSkip(
					clause_id=clause.id,
					statement=clause.statement,
					because=(
						"the oracle names no command, so there is nothing to run against an "
						"empty workspace; this is ground-truth debt (FR-108) and the audit "
						"cannot retire it"
					),
				)
			)
			continue
		if clause.kind is ClauseKind.NEGATIVE:
			skipped.append(
				OracleAuditSkip(
					clause_id=clause.id,
					statement=clause.statement,
					because=(
						"the clause asserts an absence, which an empty workspace satisfies by "
						"containing nothing; a pass there is a true statement about an empty "
						"tree rather than evidence about the oracle, so this instrument "
						"cannot ask the question"
					),
				)
			)
			continue
		probed.append(clause)
	assert len(probed) + len(skipped) == len(contract.clauses), (
		"every clause must be either probed or reported as skipped"
	)
	return tuple(probed), tuple(skipped)


async def audit_oracles(
	contract: Contract,
	*,
	timeout: float = DEFAULT_TIMEOUT_SECONDS,
	max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
	workspace: Path | None = None,
) -> OracleAuditReport:
	"""Run every probeable oracle against an empty workspace and report what passed anyway.

	``workspace`` is for tests that want to see the tree the oracles ran in. Production
	passes nothing and a fresh temporary directory is used, removed on the way out: an
	audit that left a directory behind in the operator's home would be a bookkeeping file,
	and FR-003 makes the ledger the only account of a run.

	A probed oracle that comes back ``VIOLATED`` is the good case and produces no finding —
	the oracle *can* fail, which is what FR-004 asks of a canary and what makes it an
	instrument at all. ``INSUFFICIENT`` (a timeout, or a malformed observation) is not a
	finding either: it says the audit learned nothing, not that the oracle is satisfiable
	by nothing. Only ``SATISFIED`` is FR-107's defect.
	"""
	probed, skipped = probe_targets(contract)
	if not probed:
		return OracleAuditReport(
			id=uuid7str(),
			contract_id=contract.id,
			contract_hash=contract.content_hash,
			rendered_at=now(),
			probed=(),
			skipped=skipped,
			findings=(),
		)

	with tempfile.TemporaryDirectory(prefix="sofact-oracle-audit-") as created:
		tree = Path(workspace) if workspace is not None else Path(created)
		assert tree.is_dir(), f"audit workspace does not exist: {tree}"
		run_id = uuid7str()
		# A contract over the probed clauses alone, so the verifier weighs exactly the
		# observations this audit produced and nothing else. The identity fields are the
		# real contract's, because the finding is about *its* clause; only the clause set
		# is narrowed, and that is what makes the verdict scope the probed set.
		narrowed = Contract(
			id=contract.id,
			goal_id=contract.goal_id,
			version=contract.version,
			created_at=contract.created_at,
			clauses=probed,
		)
		evidence = await OracleRunner(
			tree,
			timeout=timeout,
			max_output_bytes=max_output_bytes,
			run_id=run_id,
		).run_all(narrowed)
		report = verify(narrowed, evidence, run_id=run_id)

	by_clause = {clause.id: clause for clause in probed}
	collected: list[OracleAuditFinding] = []
	for verdict in report.verdicts:
		if verdict.outcome is not VerdictOutcome.SATISFIED:
			continue
		clause = by_clause[verdict.clause_id]
		command = clause.oracle.command_hint
		assert command is not None, (
			f"clause {clause.id} was probed, so its oracle named a command; a probeable "
			"clause reaching here without one means the scoping rule and this loop disagree"
		)
		collected.append(
			OracleAuditFinding(
				clause_id=verdict.clause_id,
				statement=verdict.statement,
				oracle_class=clause.oracle.oracle_class,
				command=command,
				detail=(
					f"ran `{command}` against an empty workspace and it reported satisfied "
					f"({verdict.reason}); an oracle that cannot fail establishes nothing, so "
					"this clause's coverage is not evidence"
				),
			)
		)
	findings = tuple(collected)
	return OracleAuditReport(
		id=uuid7str(),
		contract_id=contract.id,
		contract_hash=contract.content_hash,
		rendered_at=now(),
		probed=tuple(clause.id for clause in probed),
		skipped=skipped,
		findings=findings,
	)
