"""Contract construction policy.

:class:`~sofact.views.Contract` enforces the hard rule — no oracle, no clause — and
:meth:`~sofact.views.Contract.from_draft` refuses a draft with unassigned oracles.
This module holds the *judgement* that sits around that rule: what to suggest when
the operator has not said, and how much of a contract a machine can actually check.

Suggestions never invent a command. A fabricated ``command_hint`` would be a lie that
:mod:`sofact.execution` would later faithfully execute, which is strictly worse than
an honest gap: an honest gap is visible as ground-truth debt, whereas a fabricated
command produces a real green result that means nothing.

Ground-truth debt is the fraction of clauses no machine can currently check. It is the
one number that says how much of a "verified" contract is actually verified.
"""

from __future__ import annotations

from sofact.views import (
	STRONG_ORACLE_MAX_RANK,
	Clause,
	ClauseKind,
	ClauseStem,
	Contract,
	OracleClass,
	OracleDeclaration,
	content_hash,
)

__all__ = [
	"UnexecutableContractError",
	"executable_clauses",
	"ground_truth_debt",
	"oracle_set_hash",
	"require_executable",
	"suggest_oracle",
	"unexecutable_clauses",
	"weak_oracle_clauses",
]


class UnexecutableContractError(ValueError):
	"""Raised when a contract is asked to be fully executable but is not."""


def suggest_oracle(stem: ClauseStem) -> OracleDeclaration:
	"""A defensible default oracle class for a stem. Advisory, and non-executable.

	Negative clauses bound the blast radius and are naturally stated as properties
	("for every input in this range, the process never does X"). Positive clauses
	assert a behaviour, which is a contract obligation. Neither default carries a
	command, because SoFact does not know how to run the operator's system.
	"""
	assert stem.statement.strip(), "cannot suggest an oracle for an empty stem"
	return OracleDeclaration(
		oracle_class=OracleClass.PROPERTY
		if stem.kind is ClauseKind.NEGATIVE
		else OracleClass.CONTRACT,
		description=stem.statement,
	)


def executable_clauses(contract: Contract) -> tuple[Clause, ...]:
	"""Clauses whose oracle names a command, and so can be run unattended."""
	return tuple(c for c in contract.clauses if c.oracle.is_executable)


def unexecutable_clauses(contract: Contract) -> tuple[Clause, ...]:
	"""Clauses whose oracle is an intention rather than a check."""
	return tuple(c for c in contract.clauses if not c.oracle.is_executable)


def ground_truth_debt(contract: Contract) -> float:
	"""Fraction of clauses no machine can currently check.

	``0.0`` is the only good value. Anything above it means the contract's autonomy
	ceiling is a claim about clauses that were never run.
	"""
	assert contract.clauses, "cannot measure debt on a contract with no clauses"
	debt = len(unexecutable_clauses(contract)) / len(contract.clauses)
	assert 0.0 <= debt <= 1.0, f"debt must be a fraction, got {debt}"
	return debt


def oracle_set_hash(contract: Contract) -> str:
	"""Hash of the oracle declarations alone, ignoring the clause statements.

	FR-139 pins three things separately — the contract, the goal text, and the oracle
	set — because a single hash can only say *that* something moved. Hashing the
	oracles apart from the statements is what lets a later mismatch say *which* moved,
	and "the oracles changed" is the one sentence a producer must never be able to
	cause quietly.
	"""
	assert contract.clauses, "cannot hash the oracle set of a contract with no clauses"
	return content_hash([c.oracle.model_dump(mode="json") for c in contract.clauses])


def weak_oracle_clauses(contract: Contract) -> tuple[Clause, ...]:
	"""Clauses whose oracle cannot support the contract's strongest ceiling.

	Exactly the clauses where ``rank > STRONG_ORACLE_MAX_RANK``, and therefore
	exactly the set that stops this contract reaching L4 (FR-157's target aside).
	This set drives the plan's repair step, so repair is derived from the contract
	rather than being a step the compiler always emits out of ceremony.
	"""
	assert contract.clauses, "a contract with no clauses has no weak oracles"
	return tuple(c for c in contract.clauses if c.oracle.rank > STRONG_ORACLE_MAX_RANK)


def require_executable(contract: Contract) -> None:
	"""Raise unless every clause names a command.

	The error names the offending clauses, because "this contract is not runnable" is
	only actionable when it says which parts are not.
	"""
	missing = unexecutable_clauses(contract)
	if missing:
		raise UnexecutableContractError(
			f"{len(missing)} of {len(contract.clauses)} clause(s) name no command, so "
			"this contract cannot be fully executed: "
			+ ", ".join(f"{c.id} ({c.oracle.oracle_class.value})" for c in missing),
		)
