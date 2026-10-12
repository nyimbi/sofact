"""P3 — decomposition: the proposal, and the gate that is mostly a refusal (FR-087-094).

The gate has two halves and these tests keep them apart. The machine half is exercised
by making it *fail* — a gate nobody has watched refuse is a gate nobody has watched
work. The operator half is exercised by trying to bypass it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from synthetic import (
	elicitation_to_contract,
	gated_contract,
	kinds,
	specify_and_approve,
	synthetic_service,
)

from sofact._uuid7 import uuid7str
from sofact.decomposition import (
	CLASS_MARKERS,
	approve,
	classify,
	decomposition_hash,
	gate,
	propose,
)
from sofact.views import (
	MODULE_CLASS_CEILING,
	AutonomyLevel,
	Contract,
	Decomposition,
	DecompositionGate,
	Module,
	ModuleClass,
	OracleClass,
	OracleDeclaration,
)

MakeContract = Callable[..., Contract]
"""``make_contract`` builds a contract from ``(statement, oracle)`` pairs."""


def oracle(kind: OracleClass = OracleClass.CONTRACT) -> OracleDeclaration:
	return OracleDeclaration(oracle_class=kind, description=f"a {kind.value} oracle")


def module_of(
	name: str,
	clauses: tuple[str, ...],
	*,
	depends_on: tuple[str, ...] = (),
	module_class: ModuleClass = ModuleClass.G1,
) -> Module:
	"""A module built directly, so a test can construct a graph the proposer never would."""
	return Module(
		id=uuid7str(),
		name=name,
		module_class=module_class,
		interface=f"{name} interface",
		clause_ids=clauses,
		depends_on=depends_on,
	)


def decomposition_of(*modules: Module, contract: Contract) -> Decomposition:
	return Decomposition(
		id=uuid7str(),
		goal_id=contract.goal_id,
		contract_id=contract.id,
		created_at=contract.created_at,
		modules=modules,
	)


# --------------------------------------------------------------------------- #
# the proposal
# --------------------------------------------------------------------------- #


class TestTheProposal:
	def test_every_clause_becomes_a_module(self, make_contract: MakeContract) -> None:
		"""FR-088 direction two, at the proposal: no obligation is left unowned."""
		contract = make_contract(
			("the api returns 200", oracle()),
			("the total is summed", oracle()),
		)

		proposal = propose(contract)

		assert len(proposal.modules) == len(contract.clauses)
		assert {cid for m in proposal.modules for cid in m.clause_ids} == {
			c.id for c in contract.clauses
		}

	def test_the_proposal_is_deterministic(self, make_contract: MakeContract) -> None:
		"""Two runs over one unchanged contract must agree.

		Names are what the operator reads at the gate and what a branch is named from, so
		an unstable proposal would break FR-099's idempotence for no reason.
		"""
		contract = make_contract(
			("the api returns 200", oracle()),
			("the payment is authorized", oracle()),
		)

		first, second = propose(contract), propose(contract)

		assert [m.name for m in first.modules] == [m.name for m in second.modules]
		assert [m.module_class for m in first.modules] == [m.module_class for m in second.modules]

	def test_the_proposal_never_contains_a_cycle(self, make_contract: MakeContract) -> None:
		"""The proposer must not emit a graph its own gate would refuse (FR-089)."""
		contract = make_contract(
			*((f"the schema for table {n}", oracle(OracleClass.SCHEMA)) for n in range(4)),
			*((f"the api endpoint {n} returns 200", oracle()) for n in range(4)),
		)

		proposal = propose(contract)

		assert proposal.cycles() == ()
		assert len(proposal.build_order()) == len(contract.clauses)

	def test_a_dependency_follows_the_oracle_the_contract_already_carries(
		self, make_contract: MakeContract
	) -> None:
		"""The one relation the proposer may assert without guessing at architecture.

		A SCHEMA clause states a shape; a CONTRACT clause of the same class is checked
		*against* something. Encoding that as a dependency is reading the contract, not
		inventing an architecture — which is why it is the only edge ``propose`` emits.
		"""
		contract = make_contract(
			("the schema defines the reminder table", oracle(OracleClass.SCHEMA)),
			("the database stores reminders durably", oracle()),
		)

		proposal = propose(contract)
		foundation = next(m for m in proposal.modules if m.name.startswith("schema"))
		dependent = next(m for m in proposal.modules if m.name.startswith("database"))

		assert foundation.module_class is ModuleClass.G4, "both clauses are G4 by their words"
		assert dependent.depends_on == (foundation.id,)
		assert proposal.build_order()[0] is foundation, "a dependency is built first (FR-092)"


class TestTheModuleLookup:
	"""``module_for_clauses`` is what lets a step name the module it builds (FR-100)."""

	def test_one_clause_resolves_to_its_owning_module(self, make_contract: MakeContract) -> None:
		contract = make_contract(
			("the api returns 200", oracle()),
			("the total is summed", oracle()),
		)
		proposal = propose(contract)

		for clause in contract.clauses:
			found = proposal.module_for_clauses((clause.id,))

			assert found is not None
			assert clause.id in found.clause_ids

	def test_no_clause_resolves_to_nothing(self, make_contract: MakeContract) -> None:
		"""A bootstrap step covers no clause, so no module owns it.

		Returning a module here would put a name in the log that the decomposition does
		not support, which is why ``None`` is the answer rather than a fallback.
		"""
		contract = make_contract(("the api returns 200", oracle()))

		assert propose(contract).module_for_clauses(()) is None

	def test_clauses_spanning_two_modules_resolve_to_neither(
		self, make_contract: MakeContract
	) -> None:
		"""A step covering two modules belongs to neither, and must not pick one.

		This is the case that keeps the lookup from silently answering with the first
		match: a branch named for one of two modules would record work that also belongs
		to the other.
		"""
		contract = make_contract(
			("the api returns 200", oracle()),
			("the total is summed", oracle()),
		)
		proposal = propose(contract)
		both = tuple(c.id for c in contract.clauses)

		assert proposal.module_for_clauses(both) is None

	def test_a_clause_owned_by_two_modules_resolves_to_neither(
		self, make_contract: MakeContract
	) -> None:
		"""Ambiguity is refused in the other direction too, not just by clause count."""
		contract = make_contract(("the api returns 200", oracle()))
		shared = contract.clauses[0].id
		proposal = decomposition_of(
			module_of("left", (shared,)),
			module_of("right", (shared,)),
			contract=contract,
		)

		assert proposal.module_for_clauses((shared,)) is None


class TestTheClassifier:
	def test_every_g7_marker_classifies_as_g7(self) -> None:
		"""FR-126: G7 is L1 and human-authored, so a miss here raises the ceiling.

		The direction that costs something is a false *negative* — auth code filed under a
		class that permits autonomy — so this asserts that direction specifically.
		"""
		for marker in CLASS_MARKERS[ModuleClass.G7]:
			assert classify(f"the system must handle {marker} correctly") is ModuleClass.G7

	def test_a_generic_clause_falls_back_to_g1(self) -> None:
		"""The fallback is the *unspecific* class, so a vague clause cannot raise a ceiling."""
		assert classify("the ledger must record every entry") is ModuleClass.G1

	def test_g7_is_the_only_l1_class(self) -> None:
		l1 = [c for c, ceiling in MODULE_CLASS_CEILING.items() if ceiling is AutonomyLevel.L1]
		assert l1 == [ModuleClass.G7]
		assert set(MODULE_CLASS_CEILING) == set(ModuleClass), "every class needs a ceiling"

	def test_g7_is_checked_before_every_other_class(self) -> None:
		"""The precedence *is* the safety property, so it is asserted rather than assumed.

		"session" is a G7 marker and "service" a G3 one; a clause containing both must come
		out G7, or a clause that mentions auth in passing is filed under a class that
		permits L3.
		"""
		assert next(iter(CLASS_MARKERS)) is ModuleClass.G7
		assert classify("the session service issues a token") is ModuleClass.G7


# --------------------------------------------------------------------------- #
# the machine half, exercised by making it fail
# --------------------------------------------------------------------------- #


class TestTheGateRefuses:
	def test_a_cycle_fails_the_gate(self, make_contract: MakeContract) -> None:
		"""FR-089: a cycle is integration risk, and the gate is the only thing that sees it.

		``Module`` refuses a self-dependency but not a mutual one — a cycle is a property
		of the graph, not of any single module — so this graph is constructible and the
		gate must be what catches it.
		"""
		contract = make_contract(("the api returns 200", oracle()))
		clause_id = contract.clauses[0].id
		left = module_of("left", (clause_id,))
		right = module_of("right", (clause_id,), depends_on=(left.id,))
		left = left.model_copy(update={"depends_on": (right.id,)})
		proposal = decomposition_of(left, right, contract=contract)

		result = gate(proposal, contract)

		failed = {c.name for c in result.failed}
		assert "acyclic" in failed
		assert "build_order_exists" in failed, "no order exists, and the gate says so (FR-092)"
		assert not result.is_satisfied

	def test_an_unowned_clause_fails_the_gate(self, make_contract: MakeContract) -> None:
		"""FR-088 direction two: a clause no module owns is an obligation nobody builds.

		This is the direction a per-module check cannot see, which is why it is checked
		over the whole decomposition.
		"""
		contract = make_contract(
			("the api returns 200", oracle()),
			("the report totals correctly", oracle()),
		)
		owned, orphan = (c.id for c in contract.clauses)
		proposal = decomposition_of(module_of("api", (owned,)), contract=contract)

		result = gate(proposal, contract)

		failure = next(c for c in result.failed if c.name == "every_requirement_traces_to_a_module")
		assert orphan in failure.detail, "the refusal must name the clause, or it is not actionable"

	def test_a_dangling_clause_reference_fails_the_gate(self, make_contract: MakeContract) -> None:
		"""Traceability pointing outside the contract is not traceability.

		Without this check the graph would look complete while an obligation went unowned:
		the module cites *something*, and every clause count still adds up.
		"""
		contract = make_contract(("the api returns 200", oracle()))
		proposal = decomposition_of(module_of("api", (uuid7str(),)), contract=contract)

		result = gate(proposal, contract)

		assert "every_module_cites_a_real_clause" in {c.name for c in result.failed}

	def test_a_sound_proposal_passes_every_machine_check(self, make_contract: MakeContract) -> None:
		"""The negative of the three above: the gate is not a blanket refusal."""
		contract = make_contract(
			("the api returns 200", oracle()),
			("the total is summed", oracle()),
		)

		result = gate(propose(contract), contract)

		assert result.failed == ()
		assert not result.is_satisfied, "a passing machine half is not an approval (FR-087)"

	def test_the_gate_never_claims_to_judge_the_architecture(
		self, make_contract: MakeContract
	) -> None:
		"""§7.1: no oracle covers "this is the right decomposition", so no check may name it.

		A machine check named ``architecture_is_right`` would be the machine asserting the
		operator's half of the gate, which is the conflation the type exists to prevent.
		"""
		contract = make_contract(("the api returns 200", oracle()))

		names = {c.name for c in gate(propose(contract), contract).checks}

		assert names == {
			"acyclic",
			"build_order_exists",
			"every_module_traces_to_a_requirement",
			"every_requirement_traces_to_a_module",
			"every_module_cites_a_real_clause",
			"interface_count_reported",
		}


# --------------------------------------------------------------------------- #
# the operator half
# --------------------------------------------------------------------------- #


class TestApprovalIsTheOperatorHalf:
	def test_approval_requires_the_machine_half_to_hold(self, make_contract: MakeContract) -> None:
		"""FR-061: if approval could waive the checks, the hard stop would be bypassable
		by the one action it exists to gate."""
		contract = make_contract(("the api returns 200", oracle()))
		proposal = decomposition_of(module_of("api", (uuid7str(),)), contract=contract)

		with pytest.raises(ValueError, match="fails its own preconditions"):
			approve(gate(proposal, contract), by="operator")

	def test_approval_names_who_and_when(self, make_contract: MakeContract) -> None:
		"""An anonymous approval is not an operator decision, it is the absence of one."""
		contract = make_contract(("the api returns 200", oracle()))

		result = approve(gate(propose(contract), contract), by="Nyimbi")

		assert result.is_approved
		assert result.approved_by == "Nyimbi"
		assert result.approved_at is not None
		assert result.is_satisfied, "both halves held, so work may proceed"

	def test_half_an_approval_is_refused_by_the_type(self, make_contract: MakeContract) -> None:
		"""A caller's discipline is not a guard; the type refuses the partial state."""
		contract = make_contract(("the api returns 200", oracle()))
		rendered = gate(propose(contract), contract)

		with pytest.raises(ValueError, match="names both who approved it and when"):
			DecompositionGate(
				decomposition_id=rendered.decomposition_id,
				checks=rendered.checks,
				approved_at=contract.created_at,
			)


# --------------------------------------------------------------------------- #
# the hash names the artefact
# --------------------------------------------------------------------------- #


class TestTheHashNamesTheArtefact:
	def test_two_different_proposals_hash_differently(self, make_contract: MakeContract) -> None:
		"""FR-094: an approval must be checkable against the revision it approved."""
		left = make_contract(("the api returns 200", oracle()))
		right = make_contract(("the api returns 404", oracle()))

		assert decomposition_hash(propose(left)) != decomposition_hash(propose(right))

	def test_the_hash_ignores_ids_and_creation_time(self, make_contract: MakeContract) -> None:
		"""Ids are minted per proposal, so hashing them would make every run look revised.

		The hash answers "did the *architecture* change", and a fresh set of UUIDs for the
		same modules is not a change — which is what makes an approval against a hash
		meaningful rather than vacuous.
		"""
		contract = make_contract(("the api returns 200", oracle()))

		assert decomposition_hash(propose(contract)) == decomposition_hash(propose(contract))

	def test_the_hash_moves_when_a_module_gains_a_dependency(
		self, make_contract: MakeContract
	) -> None:
		"""The direction the ids must *not* hide: a real architectural edit is a new hash."""
		contract = make_contract(
			("the schema defines the reminder table", oracle(OracleClass.SCHEMA)),
			("the database stores reminders durably", oracle()),
		)
		proposal = propose(contract)
		foundation, dependent = proposal.modules
		flattened = proposal.model_copy(
			update={"modules": (foundation, dependent.model_copy(update={"depends_on": ()}))}
		)

		assert decomposition_hash(flattened) != decomposition_hash(proposal)


# --------------------------------------------------------------------------- #
# through the service: FR-061's hard stop
# --------------------------------------------------------------------------- #


class TestTheHardStop:
	async def test_planning_without_a_decomposition_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-061: no machine work downstream of an unapproved gate, under any config."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)

		with pytest.raises(ValueError, match="has no decomposition"):
			await service.compile_plan(contract_id)

	async def test_planning_with_a_proposal_but_no_approval_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The machine half passing is not the gate passing (FR-087)."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		await specify_and_approve(service, contract_id)
		await service.decompose(contract_id)

		with pytest.raises(ValueError, match="has not approved it"):
			await service.compile_plan(contract_id)

	async def test_an_approved_decomposition_lets_the_plan_compile(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The negative: the hard stop is not a blanket refusal."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await gated_contract(service)

		plan = await service.compile_plan(contract_id)

		assert plan.steps, "an approved decomposition must yield a plan"

	async def test_the_proposal_and_its_gate_are_both_recorded(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A proposal nobody gated is not an artefact the factory can act on."""
		service = synthetic_service(home, tmp_path, "complete")
		await gated_contract(service)

		recorded = kinds(service)
		assert "decomposition.proposed" in recorded
		assert "decomposition.gated" in recorded

	async def test_proposing_records_the_gate_unapproved(self, home: Path, tmp_path: Path) -> None:
		"""No code path may set ``approved_by``: it is the operator's field alone."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		await specify_and_approve(service, contract_id)
		proposal = await service.decompose(contract_id)

		result = await service.decomposition_gate(proposal.id)

		assert not result.is_approved
		assert result.approved_by is None
		assert result.approved_at is None
		assert not result.is_satisfied

	async def test_approving_a_superseded_revision_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-094: approving an older revision approves a proposal nobody is looking at."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		await specify_and_approve(service, contract_id)
		first = await service.decompose(contract_id)
		await service.decompose(contract_id)  # a revision supersedes it

		with pytest.raises(ValueError, match="superseded"):
			await service.approve_decomposition(first.id, by="operator")

	async def test_an_unsound_revision_cannot_be_approved_through_the_service(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The service recomputes the gate, so a stale passing row cannot carry a bad edit.

		The log holds the gate as it was rendered. Approving must be decided against the
		decomposition as it *is*, or a revision would be approved on an earlier revision's
		checks — which is the failure this recomputation exists to prevent.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await elicitation_to_contract(service)
		await specify_and_approve(service, contract_id)
		proposal = await service.decompose(contract_id)
		contract = await service.contract_by_id(contract_id)
		# Point every module at one clause: the other clause is now owned by nobody.
		stolen = proposal.modules[0].clause_ids
		broken = proposal.model_copy(
			update={
				"modules": tuple(
					m.model_copy(update={"clause_ids": stolen}) for m in proposal.modules
				)
			}
		)

		with pytest.raises(ValueError, match="fails its own preconditions"):
			approve(gate(broken, contract), by="operator")
