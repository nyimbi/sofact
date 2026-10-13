"""Contract construction policy.

The hard rule (no oracle, no clause) is enforced by :class:`~sofact.views.Contract`
itself; these tests cover the judgement layered on top — what gets suggested when
the operator has not said, and how much of a contract is actually checkable.

The central claim is that a suggestion never invents a command a machine could
later run. A fabricated ``command_hint`` is worse than a gap: the gap shows up as
debt, whereas the fabrication produces a real green result that means nothing.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from sofact._uuid7 import uuid7str
from sofact.contract import (
	UnexecutableContractError,
	executable_clauses,
	ground_truth_debt,
	require_executable,
	suggest_oracle,
	unexecutable_clauses,
)
from sofact.views import (
	ClauseKind,
	ClauseStem,
	Contract,
	ElicitationDimension,
	OracleClass,
	OracleDeclaration,
	SpecificationDraft,
	now,
)

MakeOracle = Callable[..., OracleDeclaration]
MakeContract = Callable[..., Contract]


def stem(statement: str, kind: ClauseKind) -> ClauseStem:
	return ClauseStem(
		id="01a092ed-c120-722c-8d66-cb25c6d3b009",
		statement=statement,
		kind=kind,
		derived_from=ElicitationDimension.FAILURE,
	)


# --------------------------------------------------------------------------- #
# suggestions
# --------------------------------------------------------------------------- #


def test_suggestion_never_invents_a_command() -> None:
	"""The load-bearing property. If this breaks, debt stops being visible."""
	for kind in ClauseKind:
		suggested = suggest_oracle(stem("something holds", kind))
		assert suggested.command_hint is None
		assert not suggested.is_executable, f"{kind} suggestion invented a command"


def test_negative_clauses_suggest_a_property_and_positive_ones_a_contract() -> None:
	"""A blast-radius bound is naturally stated as a property; an obligation is not.

	Property is also rank 1, which matters: negative clauses are where a weak oracle
	does the most damage, so the default leans strong.
	"""
	bounded = suggest_oracle(stem("no PII may appear in the logs", ClauseKind.NEGATIVE))
	obligation = suggest_oracle(stem("the dashboard lists reminders", ClauseKind.POSITIVE))

	assert bounded.oracle_class is OracleClass.PROPERTY
	assert obligation.oracle_class is OracleClass.CONTRACT
	assert bounded.rank < obligation.rank


def test_suggestion_carries_the_statement_as_its_description() -> None:
	statement = "every reminder appears within five seconds"
	assert suggest_oracle(stem(statement, ClauseKind.POSITIVE)).description == statement


# --------------------------------------------------------------------------- #
# ground-truth debt
# --------------------------------------------------------------------------- #


def test_debt_is_total_when_nothing_is_runnable(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(
		("a holds", make_oracle()),
		("b holds", make_oracle()),
	)
	assert ground_truth_debt(contract) == 1.0


def test_debt_is_zero_when_everything_is_runnable(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(
		("a holds", make_oracle("true")),
		("b holds", make_oracle("true")),
	)
	assert ground_truth_debt(contract) == 0.0
	require_executable(contract)


def test_debt_is_the_fraction_of_uncheckable_clauses(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(
		("a holds", make_oracle("true")),
		("b holds", make_oracle()),
		("c holds", make_oracle()),
		("d holds", make_oracle("true")),
	)
	assert ground_truth_debt(contract) == 0.5


def test_executable_and_unexecutable_partition_the_contract(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(
		("a holds", make_oracle("true")),
		("b holds", make_oracle()),
	)
	runnable = {c.id for c in executable_clauses(contract)}
	intentions = {c.id for c in unexecutable_clauses(contract)}

	assert runnable | intentions == {c.id for c in contract.clauses}
	assert runnable & intentions == set()


def test_debt_counts_a_weak_oracle_even_when_it_runs(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""FR-108's "rank-1-5" half, which the count of unexecutable clauses did not have.

	A rank-6 example test names a command, so the executability measure read it as
	coverage. FR-103's own table calls it "sample, not coverage", and FR-108's words are
	"covered by a rank-1-5 oracle" — so a contract covered only by examples is in debt.
	"""
	contract = make_contract(
		("a holds", make_oracle("pytest -k a", oracle_class=OracleClass.EXAMPLE)),
		("b holds", make_oracle("pytest -k b", oracle_class=OracleClass.GOLDEN)),
	)

	assert all(c.oracle.is_executable for c in contract.clauses), "both run; neither covers"
	assert ground_truth_debt(contract) == 1.0


def test_debt_is_zero_at_the_rank_five_boundary(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""Rank 5 is the weakest covering class, and the boundary is inclusive."""
	contract = make_contract(
		("a holds", make_oracle("pytest -k a", oracle_class=OracleClass.SCHEMA)),
		("b holds", make_oracle("pytest -k b", oracle_class=OracleClass.METAMORPHIC)),
	)

	assert ground_truth_debt(contract) == 0.0


def test_the_measure_is_the_contracts_own_property(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""One measure in one place: the function and the property cannot drift.

	The debt a report prints and the cap :attr:`Contract.ceiling` applies are the same
	set, so a change to either that did not reach the other would be a report whose
	number disagreed with its own ceiling.
	"""
	contract = make_contract(
		("a holds", make_oracle("true")),
		("b holds", make_oracle()),
		("c holds", make_oracle("pytest -k c", oracle_class=OracleClass.GOLDEN)),
	)

	assert ground_truth_debt(contract) == contract.ground_truth_debt
	assert len(contract.uncovered_clauses) == 2


# --------------------------------------------------------------------------- #
# refusing to pretend
# --------------------------------------------------------------------------- #


def test_require_executable_names_the_offending_clauses(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	""" "This contract is not runnable" is only actionable when it says which parts."""
	contract = make_contract(
		("a holds", make_oracle("true")),
		("b holds", make_oracle()),
	)
	with pytest.raises(UnexecutableContractError) as caught:
		require_executable(contract)

	message = str(caught.value)
	assert "1 of 2" in message
	assert contract.clauses[1].id in message
	assert contract.clauses[0].id not in message


def test_a_stem_without_an_oracle_cannot_become_a_clause(
	make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""FR-001 at its source: the missing oracle is named, not silently defaulted."""
	first = ClauseStem(
		id=uuid7str(),
		statement="a holds",
		kind=ClauseKind.POSITIVE,
		derived_from=ElicitationDimension.OUTCOME,
	)
	second = ClauseStem(
		id=uuid7str(),
		statement="b holds",
		kind=ClauseKind.POSITIVE,
		derived_from=ElicitationDimension.OUTCOME,
	)
	draft = SpecificationDraft(
		id=uuid7str(), goal_id=uuid7str(), created_at=now(), stems=(first, second)
	)

	with pytest.raises(ValueError) as caught:
		Contract.from_draft(draft, {first.id: make_oracle("true")})

	assert second.id in str(caught.value)
	assert first.id not in str(caught.value)


def test_a_fully_declared_oracle_is_executable(make_oracle: MakeOracle) -> None:
	declared = OracleDeclaration(
		oracle_class=OracleClass.EXAMPLE,
		description="run the acceptance suite",
		command_hint="uv run pytest -q tests/ci",
	)
	assert declared.is_executable
	assert declared.rank == 6
