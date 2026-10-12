"""P3 — decomposition: proposing modules, and the deterministic half of the gate.

§7.1 of the specification calls this the crux and the hard problem, and the reason is
stated there rather than here: **architecture is L1 by definition**, so there is no
oracle for "this is the right decomposition", only for "this decomposition satisfies the
specification" — and many do. Everything downstream inherits the choice.

So this module does the part that *is* checkable and refuses to pretend about the rest:

* :func:`propose` derives modules from the contract, deterministically. It reads the
  clause stems' own words and the oracle classes already assigned to them. It does not
  call a model. A model-proposed architecture would be a proposal whose provenance is a
  completion, and FR-087's gate would then be validating a machine's opinion about a
  machine's opinion.
* :func:`gate` computes every precondition that follows from the decomposition itself —
  traceability both ways (FR-088), acyclicity (FR-089), interface count (FR-091),
  a build order (FR-092) — and reports them as named checks.
* Neither decides whether the architecture is right. That is the operator's half of the
  gate, and :class:`~sofact.views.DecompositionGate` keeps it as a separate field so a
  passed machine half can never be mistaken for approval.

The class assignment is a *heuristic over keywords*, and it is deliberately crude and
visible rather than clever and hidden. FR-125 makes the class distribution a
decomposition-quality signal the operator reads at the gate; a signal computed by an
opaque rule would be read as a measurement, and this is a guess with a stated basis.
"""

from __future__ import annotations

import re
from typing import Final

from sofact._uuid7 import uuid7str
from sofact.views import (
	Clause,
	Contract,
	Decomposition,
	DecompositionGate,
	GateCheck,
	Module,
	ModuleClass,
	OracleClass,
	content_hash,
	now,
)

__all__ = [
	"CLASS_MARKERS",
	"classify",
	"decomposition_hash",
	"gate",
	"propose",
]

CLASS_MARKERS: dict[ModuleClass, tuple[str, ...]] = {
	ModuleClass.G7: (
		"auth",
		"authenticat",
		"authoriz",
		"authoris",
		"login",
		"password",
		"credential",
		"secret",
		"token",
		"payment",
		"billing",
		"invoice",
		"pii",
		"personal data",
		"encrypt",
		"signature",
		"permission",
		"role",
		"access control",
		"session",
	),
	ModuleClass.G4: (
		"migration",
		"schema",
		"persist",
		"database",
		"table",
		"column",
		"index",
		"constraint",
		"foreign key",
		"transaction",
		"row",
	),
	ModuleClass.G6: (
		"webhook",
		"callback",
		"third-party",
		"third party",
		"external api",
		"integration",
		"vendor",
		"provider",
		"upstream",
		"smss",
		"gateway",
	),
	ModuleClass.G5: (
		"page",
		"screen",
		"button",
		"render",
		"display",
		"ui",
		"user interface",
		"form",
		"template",
		"layout",
		"dashboard",
		"chart",
		"css",
		"component",
	),
	ModuleClass.G3: (
		"endpoint",
		"route",
		"http",
		"rest",
		"api",
		"request",
		"response",
		"status code",
		"json",
		"server",
		"handler",
		"service",
	),
	ModuleClass.G2: (
		"transform",
		"convert",
		"parse",
		"serialize",
		"deserialize",
		"format",
		"normalize",
		"aggregate",
		"etl",
		"import",
		"export",
		"report",
		"calculate",
		"compute",
		"sum",
		"total",
	),
	ModuleClass.G8: (
		"deploy",
		"infrastructure",
		"provision",
		"container",
		"pipeline",
		"configuration",
		"environment variable",
		"terraform",
		"kubernetes",
		"docker",
		"ci/cd",
		"backup",
	),
}
"""Keywords per class, most specific first — the order of iteration is the precedence.

G1 is absent on purpose. It is the fallback: "pure domain logic" is what is left when
nothing more specific is claimed, and making it the default keeps the classifier from
inventing a specific class out of a generic clause. G7 is checked first because it is
the only class where a *wrong* answer is dangerous — FR-126 makes it human-authored, so
a misclassification that buries auth inside a G1 module would quietly raise the ceiling
on exactly the code the spec refuses to grant autonomy over.
"""

_GENERIC_STEMS: Final = frozenset(
	{
		"the",
		"a",
		"an",
		"and",
		"or",
		"of",
		"to",
		"in",
		"on",
		"for",
		"with",
		"is",
		"are",
		"be",
		"must",
		"should",
		"shall",
		"will",
		"it",
		"its",
		"this",
		"that",
		"each",
		"every",
		"all",
		"any",
		"no",
		"not",
		"when",
		"while",
		"if",
		"then",
		"than",
		"as",
		"at",
		"by",
		"from",
		"into",
		"over",
		"under",
		"user",
		"users",
		"system",
		"data",
		"value",
		"values",
	},
)
"""Words too common to name a module.

Without this a stem of "the system must record every value" would produce a module
called ``the``, and the name is what the operator reads at the gate. Stripping the
generic vocabulary leaves the words that carry the clause's subject.
"""


def _words(text: str) -> list[str]:
	return re.findall(r"[a-z0-9]+", text.lower())


def classify(statement: str) -> ModuleClass:
	"""The lane class a clause's own words imply, most specific match first.

	Public because it is the whole of the class-assignment policy, and FR-125 makes the
	resulting distribution a signal the operator reads at the gate. A signal whose rule is
	private is one an operator cannot audit when it looks wrong.
	"""
	lowered = statement.lower()
	for module_class, markers in CLASS_MARKERS.items():
		if any(marker in lowered for marker in markers):
			return module_class
	return ModuleClass.G1


def _module_name(clause: Clause, taken: set[str]) -> str:
	"""A short, stable, human-readable name for the module a clause becomes.

	Deterministic and derived from the clause's own words: the operator reads these at
	the gate, and a name that changed between two runs over one unchanged contract would
	make the proposal look revised when it was not.
	"""
	meaningful = [w for w in _words(clause.statement) if w not in _GENERIC_STEMS and len(w) > 2]
	stem = "-".join(meaningful[:3]) or "module"
	name = stem
	suffix = 2
	while name in taken:
		name = f"{stem}-{suffix}"
		suffix += 1
	taken.add(name)
	return name


def _interface(clause: Clause) -> str:
	"""The module's declared surface, stated as the obligation it must expose (FR-090).

	Deliberately *not* a signature. SoFact does not know the operator's language, and an
	invented signature would be a fabricated interface that P5 then implements and P7
	then integrates against — a made-up contract that looks authoritative. What it can
	state honestly is the obligation, which is what the clause already says.
	"""
	return f"{clause.statement} (oracle: {clause.oracle.oracle_class.value})"


def propose(contract: Contract) -> Decomposition:
	"""Propose a decomposition of ``contract`` into modules, deterministically (FR-087).

	One module per clause, grouped by the class the clause's words imply, with
	dependencies derived from the oracle class rather than invented: a clause checked by
	``SCHEMA`` describes a shape that other clauses are checked against, so the modules
	whose oracles are contract-level depend on it. That is a real, checkable relation
	between two clauses — unlike a dependency guessed from reading English.

	This is a *proposal*. It is sound in the sense FR-089 and FR-092 mean — acyclic,
	ordered, traceable — and that is the only sense in which a machine may call a
	decomposition sound.
	"""
	assert contract.clauses, "cannot decompose a contract with no clauses"
	timestamp = now()

	taken: set[str] = set()
	by_clause: dict[str, Module] = {}
	for clause in contract.clauses:
		by_clause[clause.id] = Module(
			id=uuid7str(),
			name=_module_name(clause, taken),
			module_class=classify(clause.statement),
			interface=_interface(clause),
			clause_ids=(clause.id,),
		)

	# A clause whose oracle is SCHEMA or PROPERTY declares a shape or an invariant, and a
	# clause checked by CONTRACT or EXAMPLE is checked *against* something. Encoding that
	# as a dependency is reading the oracle the contract already carries, not guessing at
	# architecture.
	foundations = [m for m in by_clause.values() if _foundational(contract, m)]
	dependents = [m for m in by_clause.values() if not _foundational(contract, m)]
	# Only depend on a foundation of a *different* class: a module depending on every
	# foundation would make the DAG a star and the build order meaningless, and a module
	# depending on itself is refused by the type.
	with_deps = [
		module.model_copy(
			update={
				"depends_on": tuple(
					f.id
					for f in foundations
					if f.id != module.id and f.module_class == module.module_class
				)
			}
		)
		for module in dependents
	]
	for module in with_deps:
		by_clause[module.clause_ids[0]] = module

	decomposition = Decomposition(
		id=uuid7str(),
		goal_id=contract.goal_id,
		contract_id=contract.id,
		created_at=timestamp,
		modules=tuple(by_clause[c.id] for c in contract.clauses),
	)
	assert decomposition.modules, "a proposal must name at least one module"
	assert not decomposition.cycles(), "the proposer must not emit a cycle"
	return decomposition


_FOUNDATIONAL_ORACLES: Final = frozenset({OracleClass.SCHEMA, OracleClass.PROPERTY})


def _foundational(contract: Contract, module: Module) -> bool:
	"""Whether this module states something others are checked against."""
	clause = next((c for c in contract.clauses if c.id == module.clause_ids[0]), None)
	return clause is not None and clause.oracle.oracle_class in _FOUNDATIONAL_ORACLES


def decomposition_hash(decomposition: Decomposition) -> str:
	"""Hash of the proposed modules, so an approval can be shown to describe *this* one.

	An approval that does not name the artefact it approved is an approval of whatever
	was on screen, and FR-094 makes revisions normal — so the gate must be able to say
	that the thing approved and the thing about to be built are the same thing.
	"""
	return content_hash(
		[
			{
				"name": m.name,
				"class": m.module_class.value,
				"interface": m.interface,
				"clauses": list(m.clause_ids),
				"depends_on": sorted(m.depends_on),
			}
			for m in decomposition.modules
		]
	)


def gate(decomposition: Decomposition, contract: Contract) -> DecompositionGate:
	"""Every P3 precondition a machine can check, as named results (FR-088/089/091/092).

	The checks are *facts about the proposal*, not an opinion of it. ``architecture_is_right``
	is deliberately not among them: §7.1 says there is no oracle for it, so a check named
	that would be a machine claiming the operator's half of the gate. That half stays in
	``DecompositionGate.approved_by``, unset until a human sets it.
	"""
	assert decomposition.modules, "cannot gate a decomposition with no modules"
	checks: list[GateCheck] = []

	cycles = decomposition.cycles()
	checks.append(
		GateCheck(
			name="acyclic",
			passed=not cycles,
			detail=(
				"no dependency cycle"
				if not cycles
				else "cycles: " + "; ".join(" -> ".join(c) for c in cycles)
			),
		)
	)

	# FR-092: an order must exist. `build_order` raises on a cycle, so this check is the
	# same fact stated as a result rather than an exception -- the gate reports, it does
	# not throw at an operator who is mid-revision.
	try:
		order = decomposition.build_order()
		ordered = True
		detail = " -> ".join(m.name for m in order)
	except ValueError as exc:
		ordered = False
		detail = str(exc)
	checks.append(GateCheck(name="build_order_exists", passed=ordered, detail=detail))

	# FR-088, direction one: every module maps to at least one requirement. Enforced by
	# the Module type, so reaching here means it holds; asserted anyway because a gate
	# that reports a fact it did not check is the failure mode this whole module exists
	# to avoid.
	orphan_modules = tuple(m.name for m in decomposition.modules if not m.clause_ids)
	checks.append(
		GateCheck(
			name="every_module_traces_to_a_requirement",
			passed=not orphan_modules,
			detail=(
				f"all {len(decomposition.modules)} module(s) name at least one clause"
				if not orphan_modules
				else f"modules with no clause: {', '.join(orphan_modules)}"
			),
		)
	)

	# FR-088, direction two: every requirement maps to at least one module. This is the
	# direction a per-module check cannot see, and the one that matters -- a clause no
	# module owns is an obligation nobody will build.
	covered: set[str] = set()
	for module in decomposition.modules:
		covered.update(module.clause_ids)
	uncovered = tuple(c.id for c in contract.clauses if c.id not in covered)
	checks.append(
		GateCheck(
			name="every_requirement_traces_to_a_module",
			passed=not uncovered,
			detail=(
				f"all {len(contract.clauses)} clause(s) are owned by a module"
				if not uncovered
				else f"{len(uncovered)} clause(s) owned by no module: {', '.join(uncovered)}"
			),
		)
	)

	# A module naming a clause the contract does not contain is traceability pointing at
	# nothing -- a dangling reference that would make the graph look complete while an
	# obligation went unowned.
	known_clauses = {c.id for c in contract.clauses}
	strangers = tuple(
		f"{m.name} -> {cid}"
		for m in decomposition.modules
		for cid in m.clause_ids
		if cid not in known_clauses
	)
	checks.append(
		GateCheck(
			name="every_module_cites_a_real_clause",
			passed=not strangers,
			detail="no module cites a clause outside the contract"
			if not strangers
			else f"dangling: {', '.join(strangers)}",
		)
	)

	# FR-091: interface count is a first-class metric. It is *reported*, not thresholded:
	# the spec gives no number, and inventing one would make a quality signal into a
	# gate that fails for a reason its operator cannot act on.
	checks.append(
		GateCheck(
			name="interface_count_reported",
			passed=True,
			detail=(
				f"{decomposition.interface_count} interface(s); "
				f"G1-G2 share {decomposition.target_class_share:.0%}; "
				+ ", ".join(
					f"{k.value}={v}" for k, v in sorted(decomposition.class_distribution.items())
				)
			),
		)
	)

	return DecompositionGate(decomposition_id=decomposition.id, checks=tuple(checks))


def approve(gate_result: DecompositionGate, *, by: str) -> DecompositionGate:
	"""Record the operator's half of the P3 gate (FR-087).

	Refuses when the machine half failed. An approval is the operator saying "this
	architecture is right", not a waiver of the preconditions — and if it could waive
	them, FR-061's hard stop would be bypassable by the one action it exists to gate.
	"""
	assert by.strip(), "an approval must name who approved it"
	failed = gate_result.failed
	if failed:
		raise ValueError(
			"cannot approve a decomposition that fails its own preconditions: "
			+ "; ".join(f"{c.name} ({c.detail})" for c in failed)
		)
	return gate_result.model_copy(update={"approved_by": by, "approved_at": now()})
