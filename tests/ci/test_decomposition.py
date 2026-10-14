"""P3 — decomposition: the proposal, and the gate that is mostly a refusal (FR-087-094).

The gate has two halves and these tests keep them apart. The machine half is exercised
by making it *fail* — a gate nobody has watched refuse is a gate nobody has watched
work. The operator half is exercised by trying to bypass it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError
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
	interface_groups,
	minimal_interface_count,
	propose,
)
from sofact.planner import DEFAULT_MODULE_BUDGET, compile_plan
from sofact.views import (
	MODULE_CLASS_CEILING,
	AutonomyLevel,
	Contract,
	Decomposition,
	DecompositionGate,
	InterfaceMember,
	InterfaceMemberKind,
	Module,
	ModuleBudget,
	ModuleClass,
	OracleClass,
	OracleDeclaration,
	ReasoningClass,
	SystemInterface,
	SystemModel,
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
	budget: ModuleBudget = DEFAULT_MODULE_BUDGET,
) -> Module:
	"""A module built directly, so a test can construct a graph the proposer never would."""
	return Module(
		id=uuid7str(),
		name=name,
		module_class=module_class,
		interface=f"{name} interface",
		clause_ids=clauses,
		depends_on=depends_on,
		budget=budget,
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
	def test_every_clause_becomes_a_module_without_a_model(
		self, make_contract: MakeContract
	) -> None:
		"""FR-088 direction two, at the proposal: no obligation is left unowned.

		Without a model there is no declared grouping to honour, so one module per clause is
		the proposal — which is what this asserts. The *model-bearing* case is
		:class:`TestTheInterfaceCount`: FR-091 makes a declared interface over several
		clauses one surface, and a test named "every clause becomes a module" would then be
		a lie about the proposer rather than a test of it.
		"""
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

	def test_every_module_carries_a_definition_of_done(self, make_contract: MakeContract) -> None:
		"""FR-093: each module states what "done" means, and the gate refuses one that does not."""
		contract = make_contract(
			("the schema defines the reminder table", oracle(OracleClass.SCHEMA)),
			("the total is summed", oracle(OracleClass.CONTRACT)),
			("the balance is never negative", oracle(OracleClass.PROPERTY)),
			("the order moves pending to shipped", oracle(OracleClass.STATE_MACHINE)),
		)

		proposal = propose(contract)

		assert all(m.completion_criteria for m in proposal.modules)
		assert gate(proposal, contract).failed == ()

	def test_the_criteria_are_the_clause_oracles_shape_of_proof(
		self, make_contract: MakeContract
	) -> None:
		"""Derived from the oracle class, not authored — so two statements cannot drift.

		The four classes below compile to four different step kinds, and the criteria must
		follow the step rather than the module's name or its class. If this ever passes
		with one criterion repeated across all four, the derivation has been replaced by a
		constant.
		"""
		contract = make_contract(
			("the schema defines the reminder table", oracle(OracleClass.SCHEMA)),
			("the total is summed", oracle(OracleClass.CONTRACT)),
			("the balance is never negative", oracle(OracleClass.PROPERTY)),
			("the order moves pending to shipped", oracle(OracleClass.STATE_MACHINE)),
		)

		criteria = [m.completion_criteria for m in propose(contract).modules]

		assert len({c for group in criteria for c in group}) == len(criteria), (
			"each oracle class must yield its own condition; identical sets mean the "
			"derivation collapsed to a constant"
		)
		assert "interface conformance passes for every declared stub" in criteria[0]
		assert "property tests for this clause pass" in " ".join(criteria[2])

	def test_the_criteria_match_what_the_plan_asks_of_the_session(
		self, make_contract: MakeContract
	) -> None:
		"""FR-093 says the criteria are "the precondition for P5", so they are one statement.

		Two statements of one condition drift, and the drift is invisible because both read
		as plausible prose. This pins the two ends together: a module's Definition of Done
		is the exit evidence of the session its clause compiles to.
		"""
		contract = make_contract(
			("the total is summed", oracle(OracleClass.CONTRACT)),
			("the balance is never negative", oracle(OracleClass.PROPERTY)),
		)
		plan = compile_plan(contract)

		for module in propose(contract).modules:
			step = next(s for s in plan.steps if set(s.clause_ids) & set(module.clause_ids))
			assert module.completion_criteria == step.exit_evidence

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
# FR-091: the interface count, and what "minimise" is checkable as
# --------------------------------------------------------------------------- #


def model_with(*interfaces: SystemInterface) -> SystemModel:
	return SystemModel(interfaces=interfaces)


def an_interface(
	name: str, clause_ids: tuple[str, ...], *members: InterfaceMember
) -> SystemInterface:
	return SystemInterface(name=name, clause_ids=clause_ids, members=members)


class TestTheInterfaceCount:
	"""FR-091, and the line §7.1 draws that this must not cross.

	"Minimise interface surface" is checkable *only* against a grouping the operator
	declared: §7.1 says there is no oracle for choosing one. FR-083 already made the model
	the single source for interface definitions, and an interface there is declared over
	clauses — so the model states how many surfaces those clauses need, and the proposer
	either honours it or multiplies it. These tests exercise both, and the state where
	nothing was declared to minimise against.
	"""

	def test_without_a_model_one_module_per_clause(self, make_contract: MakeContract) -> None:
		"""Nothing declared, nothing merged: the proposer's behaviour is unchanged.

		This is the state of every project whose P2 declared no model, and it is why the
		grouping cannot be a behaviour change for existing deployments.
		"""
		contract = make_contract(
			("the api returns 200", oracle()),
			("the total is summed", oracle()),
		)

		proposal = propose(contract)

		assert len(proposal.modules) == 2
		assert minimal_interface_count(contract) == 2

	def test_a_declared_interface_over_two_clauses_is_one_module(
		self, make_contract: MakeContract
	) -> None:
		"""The minimisation itself: one declared surface, one integration point.

		The model says these two clauses introduce one interface. Giving each its own
		module contradicts the model it was handed — which is FR-083's defect one phase
		later, and exactly what FR-091's "minimise" exists to stop.
		"""
		contract = make_contract(
			("the ledger records an entry", oracle()),
			("the ledger keeps a running balance", oracle()),
		)
		first, second = (c.id for c in contract.clauses)
		model = model_with(
			an_interface(
				"ledger",
				(first, second),
				InterfaceMember(name="record", kind=InterfaceMemberKind.FUNCTION),
				InterfaceMember(name="sum", kind=InterfaceMemberKind.FUNCTION),
			)
		)

		proposal = propose(contract, model)

		assert len(proposal.modules) == 1, "one declared interface is one surface"
		assert proposal.interface_count == 1
		assert minimal_interface_count(contract, model) == 1
		module = proposal.modules[0]
		assert set(module.clause_ids) == {first, second}
		assert module.name == "ledger", "the module is named after the interface it is"
		assert [m.name for m in module.surface] == ["record", "sum"], (
			"the surface is the model's, and it is the union of what the group's clauses introduce"
		)
		assert proposal.interface_members == 2

	def test_interfaces_over_disjoint_clauses_merge_nothing(
		self, make_contract: MakeContract
	) -> None:
		"""Two interfaces, four clauses, no overlap: there is nothing to merge."""
		contract = make_contract(
			("the ledger records an entry", oracle()),
			("the ledger keeps a running balance", oracle()),
			("the api returns 200", oracle()),
			("the api returns 404", oracle()),
		)
		first, second, third, fourth = (c.id for c in contract.clauses)
		model = model_with(
			an_interface("ledger", (first, second)),
			an_interface("api", (third, fourth)),
		)

		proposal = propose(contract, model)

		assert len(proposal.modules) == 2
		assert proposal.interface_count == minimal_interface_count(contract, model) == 2

	def test_two_clauses_sharing_an_interface_in_different_lanes_do_not_merge(
		self, make_contract: MakeContract
	) -> None:
		"""``ModuleClass`` is "the class of work this module needs" (FR-050).

		Two clauses in different lanes are different kinds of work however they are
		surfaced, and merging them would move a module's autonomy ceiling — §14 gives G7 L1
		*by class*. The interface is honoured; the lane is what stops it.
		"""
		contract = make_contract(
			("the session service issues a token", oracle()),  # G7: "session", "token"
			("the api returns 200", oracle()),  # G3: "api"
		)
		first, second = (c.id for c in contract.clauses)
		assert classify(contract.clauses[0].statement) is not classify(
			contract.clauses[1].statement
		), "the fixture must put the two clauses in different lanes or it tests nothing"
		model = model_with(an_interface("gateway", (first, second)))

		proposal = propose(contract, model)
		check = next(
			c
			for c in gate(proposal, contract, model=model).checks
			if c.name == "interface_count_minimised"
		)

		assert len(proposal.modules) == 2, "a declared interface does not merge across lanes"
		assert minimal_interface_count(contract, model) == 2, (
			"the *grouping* respects the lane too, so the model does not ask for one surface "
			"here — the proposer is not under-delivering against it"
		)
		assert check.passed, "the proposer did the only thing the lane rule permits"
		assert "gateway spans" in check.detail and "FR-050" in check.detail, (
			"the tension between the model's declaration and the lane rule is reported "
			"rather than silently resolved, because the operator is the one who can "
			"re-declare the interface"
		)

	def test_transitive_interfaces_group_everything_they_reach(
		self, make_contract: MakeContract
	) -> None:
		"""Interfaces chain: one over {a, b} and one over {b, c} put all three on one surface.

		Honouring only the first would leave the second split, which is the same defect
		half-fixed.
		"""
		contract = make_contract(
			("the ledger records an entry", oracle()),
			("the ledger keeps a running balance", oracle()),
			("the ledger rejects an unbalanced entry", oracle()),
		)
		first, second, third = (c.id for c in contract.clauses)
		model = model_with(
			an_interface("ledger", (first, second)),
			an_interface("reconciliation", (second, third)),
		)

		groups = interface_groups(contract, model)

		assert len(groups) == 1
		assert {c.id for c in groups[0]} == {first, second, third}

	def test_the_grouping_is_deterministic(self, make_contract: MakeContract) -> None:
		"""Two runs over one unchanged contract and model must agree, name for name."""
		contract = make_contract(
			("the ledger records an entry", oracle()),
			("the ledger keeps a running balance", oracle()),
			("the api returns 200", oracle()),
		)
		first, second = (c.id for c in contract.clauses[:2])
		model = model_with(an_interface("ledger", (first, second)))

		left, right = propose(contract, model), propose(contract, model)

		assert [m.name for m in left.modules] == [m.name for m in right.modules]
		assert [m.clause_ids for m in left.modules] == [m.clause_ids for m in right.modules]
		assert [m.interface for m in left.modules] == [m.interface for m in right.modules]

	def test_a_split_declared_interface_fails_the_gate(self, make_contract: MakeContract) -> None:
		"""The refusal, exercised the only way it can be: a decomposition built by hand.

		``propose`` honours the model, so a split means a module was revised by hand or a
		future proposer stopped reading the model — which is the case the check is for. A
		gate that trusted the proposer would fail open the moment a second proposer exists.
		"""
		contract = make_contract(
			("the ledger records an entry", oracle()),
			("the ledger keeps a running balance", oracle()),
		)
		first, second = (c.id for c in contract.clauses)
		model = model_with(an_interface("ledger", (first, second)))
		split = decomposition_of(
			module_of("record", (first,)),
			module_of("sum", (second,)),
			contract=contract,
		)

		result = gate(split, contract, model=model)
		check = next(c for c in result.checks if c.name == "interface_count_minimised")

		assert not check.passed
		assert "record" in check.detail and "sum" in check.detail, (
			"a refusal that does not name both modules is one the operator re-derives by hand"
		)
		assert "ledger ->" in check.detail, "and it names the interface that was split"

	def test_a_proposal_the_model_drove_passes_that_check(
		self, make_contract: MakeContract
	) -> None:
		"""The default path: what the proposer emits is what the check passes on."""
		contract = make_contract(
			("the ledger records an entry", oracle()),
			("the ledger keeps a running balance", oracle()),
		)
		first, second = (c.id for c in contract.clauses)
		model = model_with(an_interface("ledger", (first, second)))

		result = gate(propose(contract, model), contract, model=model)
		check = next(c for c in result.checks if c.name == "interface_count_minimised")

		assert check.passed, check.detail
		assert "1 module(s) for 1 declared interface(s)" in check.detail

	def test_no_model_is_a_vacuous_pass_and_says_so(self, make_contract: MakeContract) -> None:
		"""NFR-025: nothing measured is not the same as nothing wrong.

		§7.1's denial makes this the honest answer for a project that declared no model —
		the factory cannot minimise against a declaration that does not exist, and a check
		that manufactured a refusal would make every such project red until it authored one.
		"""
		contract = make_contract(("the api returns 200", oracle()))

		check = next(
			c
			for c in gate(propose(contract), contract).checks
			if c.name == "interface_count_minimised"
		)

		assert check.passed
		assert "asserts nothing" in check.detail
		assert "NFR-025" in check.detail

	def test_a_model_with_no_interfaces_is_the_same_vacuous_pass(
		self, make_contract: MakeContract
	) -> None:
		"""A model of entities alone declares no surface, so nothing is split.

		This is the state ``synthetic.a_model_for`` produces, and therefore the state of
		every test in this suite that comes through P2.
		"""
		contract = make_contract(("the api returns 200", oracle()))

		check = next(
			c
			for c in gate(propose(contract, SystemModel()), contract, model=SystemModel()).checks
			if c.name == "interface_count_minimised"
		)

		assert check.passed
		assert "declares no interfaces" in check.detail

	def test_the_reported_count_names_the_members_and_the_ratio(
		self, make_contract: MakeContract
	) -> None:
		"""§20.1 names "interface count per module", and a count of surfaces is not it.

		Two decompositions can expose the same number of surfaces at very different widths,
		so the reported check carries the member total and the ratio beside the count.
		"""
		contract = make_contract(
			("the ledger records an entry", oracle()),
			("the ledger keeps a running balance", oracle()),
		)
		first, second = (c.id for c in contract.clauses)
		model = model_with(
			an_interface(
				"ledger",
				(first, second),
				InterfaceMember(name="record", kind=InterfaceMemberKind.FUNCTION),
				InterfaceMember(name="sum", kind=InterfaceMemberKind.FUNCTION),
			)
		)

		check = next(
			c
			for c in gate(propose(contract, model), contract, model=model).checks
			if c.name == "interface_count_reported"
		)

		assert check.passed, "the reported half never fails — there is no number to test against"
		assert "1 integration point(s)" in check.detail
		assert "2 declared member(s)" in check.detail
		assert "2.0 per module" in check.detail
		assert "§1.3's modules dimension" in check.detail, (
			"the bound on integration points is the envelope's, and the detail must say so "
			"rather than implying an interface threshold that does not exist"
		)

	def test_the_hash_moves_when_the_grouping_moves(self, make_contract: MakeContract) -> None:
		"""An approval describes the modules it approved, and the grouping is a decision.

		The merged proposal and the split one are different architectures — one surface or
		two — so an approval of one must not validate the other.
		"""
		contract = make_contract(
			("the ledger records an entry", oracle()),
			("the ledger keeps a running balance", oracle()),
		)
		first, second = (c.id for c in contract.clauses)
		model = model_with(an_interface("ledger", (first, second)))

		merged = propose(contract, model)
		split = decomposition_of(
			module_of("record", (first,)),
			module_of("sum", (second,)),
			contract=contract,
		)

		assert decomposition_hash(merged) != decomposition_hash(split)


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
			"every_module_has_completion_criteria",
			"every_module_declares_a_budget",
			"interface_count_minimised",
			"interface_count_reported",
			"within_delivery_envelope",
		}

	def test_a_module_with_no_completion_criteria_fails_the_gate(
		self, make_contract: MakeContract
	) -> None:
		"""FR-093: "not eligible to be built" is a refusal, not a remark.

		``propose`` cannot produce this — the derivation is total over the oracle classes
		— so the gate is checked against a module built by hand, which is the only way one
		arrives empty. A gate that trusted the proposer would be a gate that fails open
		the moment a second proposer exists.
		"""
		contract = make_contract(("the api returns 200", oracle()))
		proposal = decomposition_of(module_of("api", (contract.clauses[0].id,)), contract=contract)

		result = gate(proposal, contract)

		failure = next(c for c in result.failed if c.name == "every_module_has_completion_criteria")
		assert "api" in failure.detail, "the refusal must name the module, or it is not actionable"
		assert not result.is_satisfied


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

	def test_the_hash_moves_when_a_modules_criteria_change(
		self, make_contract: MakeContract
	) -> None:
		"""The criteria are what P5 is handed, so an approval has to cover them (FR-093).

		A revision that changed a module's Definition of Done without touching its
		interface would otherwise hash identically, and the operator's approval would
		describe a module nobody was told to build.
		"""
		contract = make_contract(("the api returns 200", oracle()))
		proposal = propose(contract)
		(module,) = proposal.modules
		revised = proposal.model_copy(
			update={
				"modules": (
					module.model_copy(update={"completion_criteria": ("the api returns 200",)}),
				)
			}
		)

		assert decomposition_hash(revised) != decomposition_hash(proposal)

	def test_the_hash_moves_when_a_modules_budget_changes(
		self, make_contract: MakeContract
	) -> None:
		"""FR-097: the budget is what P7 holds the build to, so the approval must cover it.

		A revision that raised a bound without touching the interface would otherwise hash
		identically, and P7 would measure a module against a number the operator never saw.
		"""
		contract = make_contract(("the api returns 200", oracle()))
		proposal = propose(contract)
		(module,) = proposal.modules
		revised = proposal.model_copy(
			update={
				"modules": (
					module.model_copy(
						update={
							"budget": ModuleBudget(
								max_files=1,
								max_loc=10,
								reasoning_class=ReasoningClass.REASONING,
							)
						}
					),
				)
			}
		)

		assert decomposition_hash(revised) != decomposition_hash(proposal)


# --------------------------------------------------------------------------- #
# FR-097: every module declares what it may cost
# --------------------------------------------------------------------------- #


class TestTheModuleBudget:
	def test_a_proposal_declares_a_budget_for_every_module(
		self, make_contract: MakeContract
	) -> None:
		"""FR-097's word is "must declare", so a proposal that omitted one is not a proposal."""
		contract = make_contract(("the api returns 200", oracle()), ("the api logs", oracle()))

		proposal = propose(contract)

		assert all(m.budget == DEFAULT_MODULE_BUDGET for m in proposal.modules)
		assert DEFAULT_MODULE_BUDGET.max_files == 30, "§7.3's own worked example"
		assert DEFAULT_MODULE_BUDGET.max_loc == 2500
		assert DEFAULT_MODULE_BUDGET.reasoning_class is ReasoningClass.THROUGHPUT

	def test_a_module_with_no_budget_is_refused_by_the_type(
		self, make_contract: MakeContract
	) -> None:
		"""No default: a defaulted budget is an undeclared one that reads as a declaration."""
		contract = make_contract(("the api returns 200", oracle()))

		# Validated from a payload rather than constructed, because the payload is how a
		# module arrives from outside the factory — and because a missing keyword argument
		# is a *static* error, which would prove the type checker refuses this rather than
		# the validator an operator's hand-written module would actually meet.
		payload = {
			"id": uuid7str(),
			"name": "m",
			"module_class": ModuleClass.G1,
			"interface": "m interface",
			"clause_ids": (contract.clauses[0].id,),
		}

		with pytest.raises(ValidationError, match="budget"):
			Module.model_validate(payload)

	def test_a_budget_with_a_zero_bound_is_refused(self) -> None:
		"""A bound of zero files is not a bound, it is a module that may not exist."""
		with pytest.raises(ValidationError, match="file bound must be at least 1"):
			ModuleBudget(max_files=0, max_loc=100, reasoning_class=ReasoningClass.THROUGHPUT)
		with pytest.raises(ValidationError, match="line bound must be at least 1"):
			ModuleBudget(max_files=10, max_loc=0, reasoning_class=ReasoningClass.THROUGHPUT)

	def test_the_gate_reports_every_modules_declared_budget(
		self, make_contract: MakeContract
	) -> None:
		"""The bound is printed where the approval happens, not only where it is enforced."""
		contract = make_contract(("the api returns 200", oracle()))
		proposal = propose(contract)

		check = next(
			c for c in gate(proposal, contract).checks if c.name == "every_module_declares_a_budget"
		)

		assert check.passed
		assert "30f/2500l/throughput" in check.detail

	def test_the_gate_refuses_a_budget_the_modules_own_surface_cannot_fit(
		self, make_contract: MakeContract
	) -> None:
		"""A surface member needs a line to be defined in, so the contradiction is at P3.

		``propose`` cannot produce this — it declares §7.3's 2500 — so the gate is checked
		against a module built by hand, which is the only way one arrives impossible.
		"""
		contract = make_contract(("the api returns 200", oracle()))
		module = module_of("m", (contract.clauses[0].id,)).model_copy(
			update={
				"surface": tuple(
					InterfaceMember(name=f"f{n}", kind=InterfaceMemberKind.FUNCTION)
					for n in range(3)
				),
				"budget": ModuleBudget(
					max_files=1, max_loc=2, reasoning_class=ReasoningClass.THROUGHPUT
				),
			}
		)
		proposal = decomposition_of(module, contract=contract)

		check = next(
			c for c in gate(proposal, contract).checks if c.name == "every_module_declares_a_budget"
		)

		assert not check.passed
		assert "3 declared surface member(s) against a budget of 2 line(s)" in check.detail

	def test_a_budget_the_surface_fits_is_not_refused(self, make_contract: MakeContract) -> None:
		"""The complement, so the check is a floor and not a blanket refusal."""
		contract = make_contract(("the api returns 200", oracle()))
		module = module_of("m", (contract.clauses[0].id,)).model_copy(
			update={
				"surface": tuple(
					InterfaceMember(name=f"f{n}", kind=InterfaceMemberKind.FUNCTION)
					for n in range(3)
				),
				"budget": ModuleBudget(
					max_files=1, max_loc=3, reasoning_class=ReasoningClass.THROUGHPUT
				),
			}
		)

		check = next(
			c
			for c in gate(decomposition_of(module, contract=contract), contract).checks
			if c.name == "every_module_declares_a_budget"
		)

		assert check.passed, "three names in three lines is tight but not impossible"

	def test_a_reasoning_class_is_a_class_and_never_a_model_name(self) -> None:
		"""NFR-026: a model name in a contract would make the contract depend on a vendor."""
		assert {c.value for c in ReasoningClass} == {"throughput", "reasoning", "evaluation"}


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
