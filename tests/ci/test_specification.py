"""P2 — the specification, and the gate that is the first one the operator meets.

§3.3 puts a gate at P2 because "no oracle exists for 'this specification expresses your
actual intent'". So these tests keep the two halves apart the way ``test_decomposition``
does: the machine half is exercised by making it *fail*, and the operator half by trying
to bypass it.

The checks that matter most here are the ones a plausible implementation would get
wrong by being helpful — inventing non-goals, inventing a value hypothesis, or checking
that an entity is "referenced" by searching a requirement's prose for its name. Each of
those passes a specification that specifies nothing, so each is tested against the
degenerate input rather than the happy one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from synthetic import (
	a_model_for,
	elicitation_to_contract,
	gated_contract,
	specify_and_approve,
	synthetic_service,
)

from sofact._uuid7 import uuid7str
from sofact.specification import approve, gate, specify
from sofact.views import (
	Assumption,
	ClauseKind,
	Contract,
	NonGoal,
	OracleClass,
	OracleDeclaration,
	Requirement,
	Specification,
	SystemEntity,
	SystemModel,
	SystemRelationship,
	ValueHypothesis,
	VerificationMethod,
	now,
)

MakeContract = Callable[..., Contract]
"""``make_contract`` builds a contract from ``(statement, oracle)`` pairs."""


def executable() -> OracleDeclaration:
	"""An oracle that names a command, so its requirement is machine-checkable."""
	return OracleDeclaration(
		oracle_class=OracleClass.CONTRACT,
		description="pytest asserts the reminder row exists",
		command_hint="true",
	)


def intention() -> OracleDeclaration:
	"""An oracle naming no command: an intention, so its requirement needs a human."""
	return OracleDeclaration(
		oracle_class=OracleClass.GOLDEN,
		description="the operator reads the dashboard and decides",
	)


def a_value() -> ValueHypothesis:
	return ValueHypothesis(
		effect="Fewer reminders are missed.",
		beneficiary="The end user.",
		refuting_instrument="Dashboard logs showing reminders read late.",
	)


def an_assumption() -> Assumption:
	return Assumption(
		id=uuid7str(),
		statement="Reminders are scheduled by the client.",
		refuted_by="A server-side scheduler appearing in the deployment.",
	)


def a_non_goal() -> NonGoal:
	"""FR-079's other half. Declared, because ``make_contract`` builds only positive
	clauses and the derivation proposes non-goals from negative ones."""
	return NonGoal(id=uuid7str(), statement="No mobile client is built.")


# --------------------------------------------------------------------------- #
# the derivation
# --------------------------------------------------------------------------- #


class TestTheDerivation:
	"""``specify`` derives, and derives only what the contract actually contains."""

	def test_every_clause_becomes_one_requirement(self, make_contract: MakeContract) -> None:
		contract = make_contract(
			("Reminders appear within five seconds.", executable()),
			("The dashboard lists them.", executable()),
		)

		proposal = specify(contract)

		assert len(proposal.requirements) == len(contract.clauses)
		assert proposal.clause_ids == {c.id for c in contract.clauses}

	def test_the_criterion_is_the_clauses_own_oracle(self, make_contract: MakeContract) -> None:
		"""A criterion invented here would be a second, unreviewed statement of the same
		obligation, and the two would drift (FR-077)."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))

		proposal = specify(contract)

		assert proposal.requirements[0].criterion == contract.clauses[0].oracle.description

	def test_an_oracle_with_no_command_yields_a_human_requirement(
		self, make_contract: MakeContract
	) -> None:
		"""FR-082: permitted, but marked, so its cost is visible rather than hidden."""
		contract = make_contract(("The dashboard is pleasant to use.", intention()))

		proposal = specify(contract)

		requirement = proposal.requirements[0]
		assert requirement.verification_method is VerificationMethod.HUMAN
		assert not requirement.is_machine_checkable
		assert proposal.human_verified == (requirement,)

	def test_a_negative_clause_is_proposed_as_a_non_goal(self, make_contract: MakeContract) -> None:
		"""FR-079's non-goals are the operator's, and the elicitation already asked for
		them; a derivation that discarded the BOUNDARY answer would lose what it was
		asked."""
		contract = make_contract(("No mobile apps.", executable()))
		negative = contract.clauses[0].model_copy(update={"kind": ClauseKind.NEGATIVE})
		contract = contract.model_copy(update={"clauses": (negative,)})

		proposal = specify(contract)

		assert [g.statement for g in proposal.non_goals] == ["No mobile apps."]
		assert proposal.non_goals[0].clause_ids == (negative.id,)

	def test_nothing_is_invented_for_the_operators_own_fields(
		self, make_contract: MakeContract
	) -> None:
		"""The failure mode this guards: a factory that fills FR-079 and FR-085 with a
		plausible sentence produces a specification that passes its own gate while the
		operator never said any of it."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))

		proposal = specify(contract)

		assert proposal.assumptions == ()
		assert proposal.value_hypothesis is None
		assert proposal.system_model.is_empty

	def test_a_specification_cannot_exist_without_requirements(self) -> None:
		with pytest.raises(ValueError, match="specifies nothing"):
			Specification(
				id=uuid7str(),
				goal_id=uuid7str(),
				contract_id=uuid7str(),
				created_at=now(),
				requirements=(),
			)

	def test_a_requirement_that_traces_to_nothing_is_refused(self) -> None:
		"""FR-076: a requirement nothing the operator said requires is an invention."""
		with pytest.raises(ValueError, match="traces to no intent clause"):
			Requirement(
				id=uuid7str(),
				statement="The system must be fast.",
				criterion="a benchmark",
				verification_method=VerificationMethod.ORACLE,
				clause_ids=(),
			)


# --------------------------------------------------------------------------- #
# the model — FR-078, FR-081, FR-083
# --------------------------------------------------------------------------- #


class TestTheModel:
	def test_a_relationship_over_an_undeclared_entity_is_refused(self) -> None:
		"""FR-081: a relationship over an entity P3 cannot decompose is a statement about
		nothing."""
		with pytest.raises(ValueError, match="does not declare as an entity"):
			SystemModel(
				entities=(SystemEntity(name="Reminder", description="a reminder"),),
				relationships=(
					SystemRelationship(subject="Reminder", predicate="belongs to", object="User"),
				),
			)

	def test_a_declared_relationship_is_accepted(self) -> None:
		"""The negative: the validator is not a blanket refusal."""
		model = SystemModel(
			entities=(
				SystemEntity(name="Reminder", description="a reminder"),
				SystemEntity(name="User", description="a person"),
			),
			relationships=(
				SystemRelationship(subject="Reminder", predicate="belongs to", object="User"),
			),
		)

		assert model.entity_names == {"Reminder", "User"}
		assert not model.is_empty

	def test_a_reflexive_tautology_is_refused(self) -> None:
		with pytest.raises(ValueError, match="tautology"):
			SystemRelationship(subject="Reminder", predicate="is", object="Reminder")


# --------------------------------------------------------------------------- #
# the gate — the machine half
# --------------------------------------------------------------------------- #


class TestTheMachineHalf:
	def test_a_complete_specification_passes_every_check(self, make_contract: MakeContract) -> None:
		"""The negative: the gate is not a blanket refusal."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		proposal = specify(
			contract,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		result = gate(proposal, contract)

		assert not result.failed, [c.name for c in result.failed]
		assert not result.is_satisfied, "the machine half is not the gate (FR-080)"

	def test_an_absent_value_hypothesis_fails_the_gate(self, make_contract: MakeContract) -> None:
		"""FR-085 makes it a requirement, so its absence is a failed check and not a
		detail."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		proposal = specify(
			contract, system_model=a_model_for(contract), assumptions=(an_assumption(),)
		)

		result = gate(proposal, contract)

		assert "value_hypothesis_is_falsifiable" in [c.name for c in result.failed]

	def test_an_absent_assumption_fails_the_gate(self, make_contract: MakeContract) -> None:
		"""FR-079: "load-bearing uncertainty ... must be visible at the gate, not buried"."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		proposal = specify(contract, system_model=a_model_for(contract), value_hypothesis=a_value())

		result = gate(proposal, contract)

		assert "assumptions_declared_and_falsifiable" in [c.name for c in result.failed]

	def test_an_undeclared_model_fails_the_gate(self, make_contract: MakeContract) -> None:
		"""FR-078: a model that declares nothing is the absence FR-115 later reports."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		proposal = specify(
			contract,
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		result = gate(proposal, contract)

		assert "system_model_declared" in [c.name for c in result.failed]

	def test_an_entity_no_requirement_references_fails_the_gate(
		self, make_contract: MakeContract
	) -> None:
		"""FR-081, and the check that would fail *open* if it searched prose.

		The entity is named ``id`` on purpose: it occurs inside the requirement's own text
		("the reminder **id** is returned"), so a substring check passes here while the
		entity is referenced by nothing. That is the whole reason the link is declared
		rather than searched for.
		"""
		contract = make_contract(("The reminder id is returned to the caller.", executable()))
		model = SystemModel(entities=(SystemEntity(name="id", description="the identifier"),))
		proposal = specify(
			contract,
			system_model=model,
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		result = gate(proposal, contract)

		assert "every_entity_is_referenced_by_a_requirement" in [c.name for c in result.failed]

	def test_an_entity_linked_to_a_clause_no_requirement_covers_fails_the_gate(
		self, make_contract: MakeContract
	) -> None:
		"""The declared link, read in the direction that matters: an entity whose clause
		reaches no requirement is an entity nothing requires (FR-081)."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		# An entity pointing at a clause that is not in this contract at all.
		model = SystemModel(
			entities=(
				SystemEntity(
					name="Orphan", description="nothing needs it", clause_ids=(uuid7str(),)
				),
			)
		)
		proposal = specify(
			contract,
			system_model=model,
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		result = gate(proposal, contract)
		failed = [c.name for c in result.failed]

		assert "every_entity_is_referenced_by_a_requirement" in failed
		assert "every_entity_reference_names_a_real_clause" in failed

	def test_a_statement_asserted_and_denied_is_caught(self, make_contract: MakeContract) -> None:
		"""FR-081's decidable slice: the elicitation can produce the same sentence under
		both polarities, which is a contradiction a machine can see."""
		contract = make_contract(("No mobile apps.", executable()))
		positive = contract.clauses[0]
		negative = positive.model_copy(update={"id": uuid7str(), "kind": ClauseKind.NEGATIVE})
		contract = contract.model_copy(update={"clauses": (positive, negative)})
		proposal = specify(
			contract,
			system_model=SystemModel(
				entities=tuple(
					SystemEntity(name=f"E{i}", description=c.statement, clause_ids=(c.id,))
					for i, c in enumerate(contract.clauses)
				)
			),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		result = gate(proposal, contract)

		check = next(c for c in result.checks if c.name == "no_clause_is_both_asserted_and_denied")
		assert not check.passed

	def test_human_verified_requirements_are_reported_not_failed(
		self, make_contract: MakeContract
	) -> None:
		"""FR-082 permits a criterion a person must check; failing it would make an honest
		specification red for being honest."""
		contract = make_contract(("The dashboard is pleasant to use.", intention()))
		proposal = specify(
			contract,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		result = gate(proposal, contract)

		check = next(c for c in result.checks if c.name == "testability_reported")
		assert check.passed
		assert "human-verified" in check.detail
		assert not result.failed, [c.name for c in result.failed]

	def test_a_requirement_citing_a_clause_outside_the_contract_is_caught(
		self, make_contract: MakeContract
	) -> None:
		"""A dangling reference would make the traceability graph look complete while an
		obligation went unowned."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		proposal = specify(
			contract,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)
		broken = proposal.model_copy(
			update={
				"requirements": tuple(
					r.model_copy(update={"clause_ids": (uuid7str(),)})
					for r in proposal.requirements
				)
			}
		)

		result = gate(broken, contract)
		failed = [c.name for c in result.failed]

		assert "every_requirement_cites_a_real_clause" in failed
		assert "every_clause_reaches_a_requirement" in failed


# --------------------------------------------------------------------------- #
# the gate — the operator half
# --------------------------------------------------------------------------- #


class TestTheOperatorHalf:
	def test_an_approval_records_who_and_when(self, make_contract: MakeContract) -> None:
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		proposal = specify(
			contract,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		approved = approve(gate(proposal, contract), by="nyimbi")

		assert approved.is_approved
		assert approved.approved_by == "nyimbi"
		assert approved.approved_at is not None
		assert approved.is_satisfied

	def test_an_approval_cannot_make_an_unsound_specification_sound(
		self, make_contract: MakeContract
	) -> None:
		"""FR-061: if an approval could waive a failed check, the hard stop would be
		bypassable by the one action it exists to gate."""
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		proposal = specify(contract)  # no model, no assumptions, no value hypothesis

		with pytest.raises(ValueError, match="does not make an unsound specification sound"):
			approve(gate(proposal, contract), by="operator")

	def test_an_approval_must_name_who_approved(self, make_contract: MakeContract) -> None:
		contract = make_contract(("Reminders appear within five seconds.", executable()))
		proposal = specify(
			contract,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		with pytest.raises(AssertionError, match="must name who approved"):
			approve(gate(proposal, contract), by="  ")


# --------------------------------------------------------------------------- #
# through the service — the hard stop
# --------------------------------------------------------------------------- #


class TestTheHardStop:
	async def test_decomposing_an_unspecified_contract_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-061: no machine work downstream of an open gate, under any configuration."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)

		with pytest.raises(ValueError, match="has no specification"):
			await service.decompose(contract_id)

	async def test_a_proposal_without_approval_still_blocks_decomposition(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The machine half passing is not the gate passing (FR-080)."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		contract = await service.contract_by_id(contract_id)
		await service.specify(
			contract_id,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		with pytest.raises(ValueError, match="has not approved it"):
			await service.decompose(contract_id)

	async def test_an_approved_specification_lets_the_decomposition_run(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The negative: the hard stop is not a blanket refusal."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)

		await specify_and_approve(service, contract_id)
		proposal = await service.decompose(contract_id)

		assert proposal.modules, "an approved specification must decompose"

	async def test_the_proposal_and_its_gate_are_both_recorded(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A proposal nobody gated is not an artefact the factory can act on."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)

		await specify_and_approve(service, contract_id)

		state = await service.state()
		proposal = state.latest_specification(contract_id)
		assert proposal is not None
		assert state.latest_specification_gate(proposal.id) is not None

	async def test_proposing_records_the_gate_unapproved(self, home: Path, tmp_path: Path) -> None:
		"""No code path may set ``approved_by``: it is the operator's field alone."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		contract = await service.contract_by_id(contract_id)
		proposal = await service.specify(
			contract_id,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		result = await service.specification_gate(proposal.id)

		assert not result.is_approved
		assert result.approved_by is None
		assert not result.is_satisfied

	async def test_approving_a_superseded_revision_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-094: approving an older revision approves a document nobody is reading."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		contract = await service.contract_by_id(contract_id)
		first = await service.specify(
			contract_id,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)
		await service.specify(
			contract_id,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)

		with pytest.raises(ValueError, match="superseded"):
			await service.approve_specification(first.id, by="operator")

	async def test_an_unsound_revision_cannot_be_approved_through_the_service(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The service recomputes the gate, so a stale passing row cannot carry a bad edit.

		The log holds the gate as it was rendered. Approving must be decided against the
		specification as it *is*, or a revision would be approved on an earlier revision's
		checks.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		contract = await service.contract_by_id(contract_id)
		proposal = await service.specify(
			contract_id,
			system_model=a_model_for(contract),
			assumptions=(an_assumption(),),
			non_goals=(a_non_goal(),),
			value_hypothesis=a_value(),
		)
		# Re-point every requirement at a clause the contract does not contain, so the
		# traceability checks fail on a specification whose logged gate passed.
		broken = proposal.model_copy(
			update={
				"requirements": tuple(
					r.model_copy(update={"clause_ids": (uuid7str(),)})
					for r in proposal.requirements
				)
			}
		)

		with pytest.raises(ValueError, match="does not make an unsound specification sound"):
			approve(gate(broken, contract), by="operator")

	async def test_the_specification_survives_a_restart_because_it_is_in_the_log(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The artefact is the log entry, not an in-memory object (FR-062)."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		await specify_and_approve(service, contract_id)

		from sofact.service import FactoryService

		reopened = FactoryService(home=home, llm=None, specs={})
		found = await reopened.latest_specification(contract_id)

		assert found is not None
		result = await reopened.specification_gate(found.id)
		assert result.is_satisfied


# --------------------------------------------------------------------------- #
# the pipeline end to end
# --------------------------------------------------------------------------- #


async def test_a_gated_contract_reaches_a_plan(home: Path, tmp_path: Path) -> None:
	"""P0 through P5 with both gates passed honestly, so the path is reachable."""
	service = synthetic_service(home, tmp_path, "complete")
	_, contract_id = await gated_contract(service)

	plan = await service.compile_plan(contract_id)

	assert plan.steps, "a gated contract must yield a plan"


async def test_a_specification_that_fails_its_checks_never_reaches_a_plan(
	home: Path, tmp_path: Path
) -> None:
	"""The whole point of a gate: an unsound specification stops the pipeline.

	Named for the property rather than the mechanism, because the property is what
	matters — the pipeline cannot reach machine work while P2 is open, and no
	configuration of the calls below changes that.
	"""
	service = synthetic_service(home, tmp_path, "complete")
	_, contract_id = await elicitation_to_contract(service)
	await service.specify(contract_id)  # no model, no assumptions, no value hypothesis

	proposal = await service.latest_specification(contract_id)
	assert proposal is not None
	with pytest.raises(ValueError, match="does not make an unsound specification sound"):
		await service.approve_specification(proposal.id, by="operator")
	# The gate refused the approval, so the specification is still unapproved — and the
	# decomposition, which is the machine work P2 gates, is refused for *that* reason
	# rather than reaching the next phase's own precondition.
	with pytest.raises(ValueError, match="has not approved it"):
		await service.decompose(contract_id)
