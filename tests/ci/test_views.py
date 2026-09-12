"""Value-object invariants.

These tests exist because the two load-bearing rules of the spec are enforced here,
at construction time, and a regression would be silent: a contract with an
unassigned oracle, or a verifier that accepts a producer's own claim.
"""

from __future__ import annotations

import uuid
from itertools import pairwise

import pytest
from pydantic import ValidationError

from sofact._uuid7 import uuid7str
from sofact.views import (
	GENESIS_HASH,
	AutonomyLevel,
	ClauseKind,
	ClauseStem,
	CompletionClaim,
	Contract,
	ElicitationDimension,
	Evidence,
	EvidenceKind,
	OracleClass,
	OracleDeclaration,
	SpecificationDraft,
	canonical_json,
	ceiling_for_rank,
	content_hash,
	now,
)


class TestIdentifiers:
	def test_uuid7_is_version_7(self) -> None:
		assert uuid.UUID(uuid7str()).version == 7

	def test_uuid7_is_lexicographically_ordered(self) -> None:
		"""Time-ordered ids are why the ledger can key on the id and still replay in
		causal order."""
		generated = [uuid7str() for _ in range(50)]
		pairs = list(pairwise(generated))
		assert len(pairs) == 49
		assert all(earlier < later for earlier, later in pairs)

	def test_goal_rejects_a_v4_id(self) -> None:
		from sofact.views import Goal

		with pytest.raises(ValidationError, match="not a UUID7"):
			Goal(id=str(uuid.uuid4()), statement="x", created_at=now())

	def test_goal_rejects_garbage_id(self) -> None:
		from sofact.views import Goal

		with pytest.raises(ValidationError, match="not a UUID"):
			Goal(id="not-a-uuid", statement="x", created_at=now())

	def test_statement_is_trimmed_and_must_not_be_blank(self) -> None:
		from sofact.views import Goal

		goal = Goal(id=uuid7str(), statement="  pad  ", created_at=now())
		assert goal.statement == "pad"
		with pytest.raises(ValidationError, match="must not be empty"):
			Goal(id=uuid7str(), statement="   ", created_at=now())


class TestHashing:
	def test_canonical_json_ignores_key_order(self) -> None:
		"""Without this, a dict round-tripped through the ledger would look tampered
		with purely because its keys moved."""
		assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})

	def test_content_hash_is_stable_across_a_model_round_trip(self) -> None:
		declaration = OracleDeclaration(
			oracle_class=OracleClass.PROPERTY,
			description="hypothesis asserts ordering",
		)
		assert content_hash(declaration) == content_hash(declaration.model_dump(mode="json"))


class TestAutonomyCeiling:
	@pytest.mark.parametrize(
		("rank", "expected"),
		[
			(1, AutonomyLevel.L4),
			(2, AutonomyLevel.L4),
			(3, AutonomyLevel.L3),
			(4, AutonomyLevel.L3),
			(5, AutonomyLevel.L2),
			(6, AutonomyLevel.L2),
			(7, AutonomyLevel.L2),
		],
	)
	def test_rank_maps_to_ceiling(self, rank: int, expected: AutonomyLevel) -> None:
		assert ceiling_for_rank(rank) == expected

	def test_l5_is_never_granted(self) -> None:
		"""SoFact does not offer a dark factory; no oracle strength reaches L5."""
		assert {ceiling_for_rank(r) for r in range(1, 8)} == {
			AutonomyLevel.L4,
			AutonomyLevel.L3,
			AutonomyLevel.L2,
		}

	def test_out_of_range_rank_is_rejected(self) -> None:
		with pytest.raises(AssertionError, match="rank out of range"):
			ceiling_for_rank(0)


def _stem(statement: str = "the dashboard shows the reminder") -> ClauseStem:
	return ClauseStem(
		id=uuid7str(),
		statement=statement,
		kind=ClauseKind.POSITIVE,
		derived_from=ElicitationDimension.OUTCOME,
	)


def _oracle(oracle_class: OracleClass = OracleClass.PROPERTY) -> OracleDeclaration:
	return OracleDeclaration(oracle_class=oracle_class, description="checked by a property test")


def _draft(*stems: ClauseStem) -> SpecificationDraft:
	return SpecificationDraft(
		id=uuid7str(),
		goal_id=uuid7str(),
		created_at=now(),
		stems=stems or (_stem(),),
	)


class TestClauseRequiresAnOracle:
	def test_clause_cannot_be_built_without_an_oracle(self) -> None:
		"""FR-001. ``oracle`` is non-nullable, so this is a type error, not a policy
		decision made somewhere downstream."""
		from sofact.views import Clause

		with pytest.raises(ValidationError):
			Clause(id=uuid7str(), statement="x", kind=ClauseKind.POSITIVE, oracle=None)  # type: ignore[arg-type]


class TestContractGate:
	def test_contract_refuses_a_stem_with_no_oracle(self) -> None:
		first, second = _stem("a"), _stem("b")
		draft = _draft(first, second)
		with pytest.raises(ValueError, match="have no oracle"):
			Contract.from_draft(draft, {first.id: _oracle()})

	def test_the_error_names_the_offending_stems(self) -> None:
		"""'Unverifiable' is only actionable when it is specific."""
		stem = _stem()
		with pytest.raises(ValueError) as caught:
			Contract.from_draft(_draft(stem), {})
		assert stem.id in str(caught.value)

	def test_contract_builds_when_every_stem_has_an_oracle(self) -> None:
		stem = _stem()
		contract = Contract.from_draft(_draft(stem), {stem.id: _oracle()})
		assert len(contract.clauses) == 1
		assert contract.version == 1
		assert contract.ceiling == AutonomyLevel.L4

	def test_ceiling_follows_the_weakest_clause(self) -> None:
		strong, weak = _stem("strong"), _stem("weak")
		contract = Contract.from_draft(
			_draft(strong, weak),
			{strong.id: _oracle(OracleClass.PROPERTY), weak.id: _oracle(OracleClass.GOLDEN)},
		)
		assert contract.weakest_oracle_rank == 7
		assert contract.ceiling == AutonomyLevel.L2

	def test_content_hash_covers_the_clause_set(self) -> None:
		"""FR-139: verification records which contract it verified."""
		stem = _stem()
		one = Contract.from_draft(_draft(stem), {stem.id: _oracle()})
		two = Contract.from_draft(_draft(stem), {stem.id: _oracle(OracleClass.GOLDEN)})
		assert one.content_hash != two.content_hash

	def test_a_contract_with_no_clauses_is_rejected(self) -> None:
		with pytest.raises(ValidationError, match="verifies nothing"):
			Contract(id=uuid7str(), goal_id=uuid7str(), version=1, created_at=now(), clauses=())


class TestDraftRequiresStems:
	def test_empty_draft_is_rejected(self) -> None:
		with pytest.raises(ValidationError, match="asserts nothing"):
			SpecificationDraft(id=uuid7str(), goal_id=uuid7str(), created_at=now(), stems=())


class TestEvidenceIsNotAClaim:
	def test_evidence_carries_no_verdict_field(self) -> None:
		"""A producer may report what it saw, never whether the clause holds."""
		assert "passed" not in Evidence.model_fields
		assert "status" not in Evidence.model_fields

	def test_evidence_hashes_its_payload(self) -> None:
		evidence = Evidence.record(
			clause_id=uuid7str(),
			kind=EvidenceKind.COMMAND_OUTPUT,
			produced_by="runner",
			payload={"exit_code": 0, "stdout": "ok"},
		)
		assert evidence.content_hash == content_hash({"exit_code": 0, "stdout": "ok"})

	def test_claim_is_a_distinct_type_from_evidence(self) -> None:
		assert CompletionClaim is not Evidence
		assert GENESIS_HASH == "0" * 64
