"""P2 — the specification artefact, and the deterministic half of its gate.

§6 calls P2 "the first gate" and §3.3 explains why it is a gate at all: *"no oracle
exists for 'this specification expresses your actual intent'."* So this module does the
part that is checkable and refuses to pretend about the rest:

* :func:`specify` derives a specification from the contract, deterministically. It reads
  the clauses the operator's own answers produced and groups them into requirements. It
  does not call a model. A model-written specification would be a document whose
  provenance is a completion, and FR-080's gate would then be the operator validating a
  machine's paraphrase of their own words — which is the lossy compression §3.3 is
  talking about, performed twice.
* :func:`gate` computes every precondition that follows from the specification itself —
  traceability both ways (FR-076), a criterion on every requirement (FR-077), the
  model's internal consistency (FR-081), and testability (FR-082) — and reports them as
  named checks.
* Neither decides whether the specification expresses the operator's intent. That is the
  operator's half, and :class:`~sofact.views.SpecificationGate` keeps it a separate field
  so a passed machine half can never be mistaken for approval.

**What is derived and what is not.** FR-079's non-goals and assumptions and FR-085's
value hypothesis are *the operator's*, and nothing here invents them. A specification
proposed without them is not incomplete in a way this module can fix — it is a
specification whose operator has not said, and :func:`gate` reports that as a failed
check rather than filling the gap with a plausible sentence. That is the same rule
:func:`~sofact.contract.suggest_oracle` follows about commands: an honest gap is
visible, a fabricated one is not.
"""

from __future__ import annotations

from sofact._uuid7 import uuid7str
from sofact.views import (
	Assumption,
	Clause,
	ClauseKind,
	Contract,
	GateCheck,
	NonGoal,
	Requirement,
	Specification,
	SpecificationGate,
	SystemModel,
	ValueHypothesis,
	VerificationMethod,
	now,
)

__all__ = [
	"approve",
	"gate",
	"specify",
]


def _criterion(clause: Clause) -> tuple[str, VerificationMethod]:
	"""The acceptance criterion for a requirement derived from ``clause`` (FR-077).

	The criterion is the clause's own oracle description, because that is the thing that
	was actually assigned and it is already in the operator's words. A criterion invented
	here would be a second, unreviewed statement of the same obligation, and the two would
	drift.

	The *method* is read from whether the oracle names a command. FR-082 asks for "a
	demonstration that the acceptance criterion can be mechanically evaluated", and an
	oracle with no ``command_hint`` cannot be — it is an intention
	(:attr:`~sofact.views.OracleDeclaration.is_executable`), so the requirement is
	``HUMAN`` and its cost is counted at the gate. This is the one place the two
	requirements meet, and marking it is the whole of FR-082's teeth.
	"""
	assert clause.statement.strip(), "cannot derive a criterion from an empty clause"
	method = VerificationMethod.ORACLE if clause.oracle.is_executable else VerificationMethod.HUMAN
	return clause.oracle.description, method


def specify(
	contract: Contract,
	*,
	system_model: SystemModel | None = None,
	non_goals: tuple[NonGoal, ...] = (),
	assumptions: tuple[Assumption, ...] = (),
	value_hypothesis: ValueHypothesis | None = None,
) -> Specification:
	"""Derive a specification from ``contract``, deterministically (FR-076).

	One requirement per clause. That is not a limitation to be apologised for: the clause
	*is* the falsifiable unit the operator's answers produced, and FR-077's criterion is
	the oracle already assigned to it. Grouping clauses into fewer, larger requirements
	would be a judgement about which obligations belong together, and a machine that made
	that judgement would be inventing the structure P3 is supposed to decompose.

	``system_model``, ``non_goals``, ``assumptions`` and ``value_hypothesis`` are the
	operator's and default to empty. Nothing is invented for them; :func:`gate` reports
	their absence as a failed check, which is the difference between an incomplete
	specification and a plausible-looking wrong one.
	"""
	assert contract.clauses, "cannot specify a contract with no clauses"

	requirements: list[Requirement] = []
	derived_non_goals: list[NonGoal] = list(non_goals)
	for clause in contract.clauses:
		criterion, method = _criterion(clause)
		requirements.append(
			Requirement(
				id=uuid7str(),
				statement=clause.statement,
				criterion=criterion,
				verification_method=method,
				clause_ids=(clause.id,),
			)
		)
		# A negative clause reads as "the system does not do X", which is the shape
		# FR-079 asks a non-goal to have, so it is proposed as one *in addition* to being
		# a requirement. Proposed, not assumed: the operator can drop it, and a
		# derivation that silently discarded the boundary the elicitation asked for would
		# be the machine deciding what the operator's answer meant.
		if clause.kind is ClauseKind.NEGATIVE:
			derived_non_goals.append(
				NonGoal(id=uuid7str(), statement=clause.statement, clause_ids=(clause.id,))
			)

	specification = Specification(
		id=uuid7str(),
		goal_id=contract.goal_id,
		contract_id=contract.id,
		created_at=now(),
		requirements=tuple(requirements),
		system_model=system_model if system_model is not None else SystemModel(),
		non_goals=tuple(derived_non_goals),
		assumptions=assumptions,
		value_hypothesis=value_hypothesis,
	)
	assert specification.clause_ids <= {c.id for c in contract.clauses}, (
		"a requirement cites a clause outside the contract"
	)
	return specification


def gate(specification: Specification, contract: Contract) -> SpecificationGate:
	"""Compute P2's machine checks (FR-076 to FR-086).

	Deterministic and total: it reports every precondition as a named
	:class:`~sofact.views.GateCheck`, including the ones that depend on the operator
	having supplied something. A check that cannot pass because the operator has not
	answered is still a *check*, and reporting it is what makes the gate a hard stop
	rather than a formality.
	"""
	assert specification.requirements, "cannot gate a specification with no requirements"
	checks: list[GateCheck] = []
	contract_clauses = {c.id for c in contract.clauses}

	# FR-076, direction one: every requirement traces to a real clause. The type
	# enforces that it traces to *something*; this catches it tracing to a clause the
	# contract does not contain, which is a dangling reference that would make the graph
	# look complete while an obligation went unowned.
	strangers = tuple(
		f"{r.statement[:30]} -> {cid}"
		for r in specification.requirements
		for cid in r.clause_ids
		if cid not in contract_clauses
	)
	checks.append(
		GateCheck(
			name="every_requirement_cites_a_real_clause",
			passed=not strangers,
			detail="no requirement cites a clause outside the contract"
			if not strangers
			else f"dangling: {', '.join(strangers)}",
		)
	)

	# FR-076, direction two: every clause reaches a requirement. This is the direction a
	# per-requirement check cannot see, and the one that matters — a clause no
	# requirement covers is an obligation the specification dropped.
	uncovered = specification.uncovered_clauses(frozenset(contract_clauses))
	checks.append(
		GateCheck(
			name="every_clause_reaches_a_requirement",
			passed=not uncovered,
			detail=(
				f"all {len(contract_clauses)} clause(s) are covered by a requirement"
				if not uncovered
				else f"{len(uncovered)} clause(s) reach no requirement: " + ", ".join(uncovered)
			),
		)
	)

	# FR-077: every requirement has a criterion. Enforced by the Requirement type, so
	# reaching here means it holds; asserted anyway, because a gate that reports a fact
	# it did not check is the failure mode this module exists to avoid.
	uncriterioned = tuple(r.statement[:30] for r in specification.requirements if not r.criterion)
	checks.append(
		GateCheck(
			name="every_requirement_has_a_criterion",
			passed=not uncriterioned,
			detail=f"all {len(specification.requirements)} requirement(s) carry a criterion"
			if not uncriterioned
			else f"no criterion: {', '.join(uncriterioned)}",
		)
	)

	# FR-082: testability. This check *reports* rather than fails, and the distinction is
	# FR-082's own: a criterion that cannot be mechanically evaluated is permitted, it
	# must be "marked human-verified and its verification cost counted against the human
	# budget". Failing here would make an honest specification red for being honest.
	human = specification.human_verified
	checks.append(
		GateCheck(
			name="testability_reported",
			passed=True,
			detail=(
				f"{len(specification.requirements) - len(human)} of "
				f"{len(specification.requirements)} requirement(s) are machine-checkable; "
				+ (
					"none need a human"
					if not human
					else f"{len(human)} are human-verified and cost human budget"
				)
			),
		)
	)

	# FR-081, first clause: "no two requirements may contradict". Contradiction in prose
	# is not decidable, and a gate that claimed to check it would be lying. What *is*
	# decidable is the degenerate case the elicitation can actually produce: the operator
	# answers a dimension twice with the same sentence and opposite polarity, so the
	# contract holds one statement as both a positive and a negative clause and the
	# specification derives a requirement asserting it and a requirement denying it.
	# That is a contradiction, it is exactly checkable, and it is the one this can find.
	# The rest of FR-081's first clause is not covered here and the check says so rather
	# than reporting a clean bill for a class it cannot see.
	by_statement: dict[str, set[ClauseKind]] = {}
	for clause in contract.clauses:
		by_statement.setdefault(clause.statement.strip(), set()).add(clause.kind)
	contradictions = tuple(sorted(text for text, kinds in by_statement.items() if len(kinds) > 1))
	checks.append(
		GateCheck(
			name="no_clause_is_both_asserted_and_denied",
			passed=not contradictions,
			detail=(
				"no statement appears as both a positive and a negative clause (this "
				"covers the polarity case only; contradiction between distinct "
				"statements is not machine-decidable)"
				if not contradictions
				else f"{len(contradictions)} statement(s) asserted and denied: "
				+ "; ".join(c[:60] for c in contradictions)
			),
		)
	)

	# FR-081, model half: every entity is referenced by a requirement, and every
	# reference names a declared entity. Both directions, because one alone is satisfiable
	# by a specification that does nothing: a model with no entities passes direction one
	# trivially, and a clause citing nothing passes direction two trivially. The check is
	# a set comparison over declared links, never a search for the entity's name in prose
	# -- an entity called "id" or "job" occurs in unrelated sentences, so a text search
	# would pass on specifications that reference nothing.
	#
	# The link points entity -> clause because requirements are derived here, so a clause
	# is the only stable thing an operator can name when declaring the model. That makes
	# the check "every entity's clause reaches a requirement", which is the same set
	# comparison seen from the other end.
	model = specification.system_model
	cited = specification.clause_ids
	referenced = frozenset(e.name for e in model.entities if cited & set(e.clause_ids))
	unreferenced = tuple(sorted(model.entity_names - referenced))
	contract_clause_ids = {c.id for c in contract.clauses}
	phantom = tuple(
		sorted(
			f"{e.name} -> {cid}"
			for e in model.entities
			for cid in e.clause_ids
			if cid not in contract_clause_ids
		)
	)
	checks.append(
		GateCheck(
			name="every_entity_is_referenced_by_a_requirement",
			passed=not unreferenced,
			detail=(
				# "all 0 entities are referenced" is vacuously true and reads as evidence,
				# which is the one thing a gate line must never do. The absence is owned by
				# ``system_model_declared``, so this line says it found nothing to check
				# rather than claiming it checked something.
				"the model declares no entities, so there is nothing to reference"
				if not model.entities
				else f"all {len(model.entities)} entity(ies) are referenced by a requirement"
				if not unreferenced
				else f"entities no requirement references: {', '.join(unreferenced)} (FR-081)"
			),
		)
	)
	checks.append(
		GateCheck(
			name="every_entity_reference_names_a_real_clause",
			passed=not phantom,
			detail=(
				"every entity's reference names a clause in the contract"
				if not phantom
				else "entities citing clauses outside the contract: " + ", ".join(phantom)
			),
		)
	)

	# FR-081, relationship half: every relationship names two declared entities. Enforced
	# by SystemModel's validator, so this restates it as a gate result.
	checks.append(
		GateCheck(
			name="relationships_name_declared_entities",
			passed=True,
			detail=(
				f"{len(model.relationships)} relationship(s) over "
				f"{len(model.entities)} declared entity(ies)"
			),
		)
	)

	# FR-078/FR-083: the model exists and is machine-readable. A model that declares
	# nothing is not a passing model — it is the absence FR-115 would later report as
	# uncovered, and saying so here is what makes the gate honest about it.
	checks.append(
		GateCheck(
			name="system_model_declared",
			passed=not model.is_empty,
			detail=(
				f"{len(model.entities)} entity(ies), {len(model.relationships)} "
				f"relationship(s), {len(model.invariants)} invariant(s)"
				if not model.is_empty
				else "the model declares no entities, relationships or invariants, so "
				"nothing can be conformed against (FR-078, FR-115)"
			),
		)
	)

	# FR-079: non-goals and assumptions declared, and assumptions visible at the gate.
	# FR-079's sentence is "must be visible at the gate, not buried", which is a claim
	# about this report as much as about the artefact.
	checks.append(
		GateCheck(
			name="non_goals_declared",
			passed=bool(specification.non_goals),
			detail=(
				f"{len(specification.non_goals)} non-goal(s) declared"
				if specification.non_goals
				else "no non-goals declared; a specification with no boundary claims to "
				"do everything (FR-079)"
			),
		)
	)
	checks.append(
		GateCheck(
			name="assumptions_declared_and_falsifiable",
			passed=bool(specification.assumptions),
			detail=(
				f"{len(specification.assumptions)} assumption(s), each naming what would refute it"
				if specification.assumptions
				else "no assumptions declared; a specification resting on nothing "
				"unstated is either trivial or hiding its uncertainty (FR-079)"
			),
		)
	)

	# FR-085: a falsifiable value hypothesis. FR-086 forbids the factory from certifying
	# it, so this check is about *presence and falsifiability*, never about the value
	# being true — there is no field here that could express the latter.
	value = specification.value_hypothesis
	checks.append(
		GateCheck(
			name="value_hypothesis_is_falsifiable",
			passed=value is not None,
			detail=(
				f"declared: {value.effect[:60]} (refuted by {value.refuting_instrument[:40]})"
				if value is not None
				else "no value hypothesis declared (FR-085). Note that SoFact never "
				"certifies it (FR-086): declaring one is the requirement, proving it is "
				"not this factory's claim"
			),
		)
	)

	return SpecificationGate(specification_id=specification.id, checks=tuple(checks))


def approve(gate_result: SpecificationGate, *, by: str) -> SpecificationGate:
	"""Record the operator's half of the P2 gate (FR-061, FR-080).

	Refuses when the machine half failed. FR-080 says the gate "must present the
	specification in the operator's language. An operator who cannot evaluate a
	specification cannot discharge the §2.3 responsibility, and the gate becomes
	theatre" — and an approval that could waive a failed check is precisely that theatre.
	"""
	assert by.strip(), "an approval must name who approved it"
	failed = gate_result.failed
	if failed:
		names = ", ".join(c.name for c in failed)
		raise ValueError(
			f"the specification failed {len(failed)} machine check(s) ({names}); an "
			"approval records a decision, it does not make an unsound specification "
			"sound (FR-061)",
		)
	return gate_result.model_copy(update={"approved_by": by, "approved_at": now()})
