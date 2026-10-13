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
from sofact.envelope import measure
from sofact.planner import DEFAULT_MODULE_BUDGET, exit_evidence_for
from sofact.views import (
	Clause,
	Contract,
	Decomposition,
	DecompositionGate,
	DeliveryEnvelope,
	GateCheck,
	Module,
	ModuleClass,
	OracleClass,
	SystemModel,
	content_hash,
	now,
)

__all__ = [
	"CLASS_MARKERS",
	"classify",
	"completion_criteria",
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


def completion_criteria(clause: Clause) -> tuple[str, ...]:
	"""FR-093's Definition of Done for the module a clause becomes.

	Derived, never authored. §7.3's module contract carries a ``completion_criteria``
	field an operator may write, and an authored one would be a second statement of what
	the clause's oracle already says: the oracle class *is* the clause's shape of proof,
	so a property clause is done when property tests pass and a schema clause is done
	when interface conformance passes. Two statements of one condition drift, and the
	drift is invisible because both read as plausible prose.

	The derivation is :func:`sofact.planner.exit_evidence_for` — the same conditions P5's
	session is asked to leave behind. That is not a coincidence to be tolerated: FR-093
	says completion criteria are "the precondition for P5", so the module's DoD and the
	session's exit evidence are one statement, and this function is the place that says
	so rather than a place that copies it.

	Never empty. ``_STEP_FOR_ORACLE`` is total over :class:`~sofact.views.OracleClass`
	and every step kind in :data:`_EXIT_EVIDENCE` carries at least one condition, so a
	clause with a declared oracle always yields criteria — which is why FR-093's refusal
	("not eligible to be built") can live in :func:`gate` as a check over the modules
	rather than as a branch here. A module built by hand, outside :func:`propose`, is the
	one that can arrive empty, and that is exactly what the gate check is for.
	"""
	return exit_evidence_for(clause)


def propose(contract: Contract, model: SystemModel | None = None) -> Decomposition:
	"""Propose a decomposition of ``contract`` into modules, deterministically (FR-087).

	One module per clause, grouped by the class the clause's words imply, with
	dependencies derived from the oracle class rather than invented: a clause checked by
	``SCHEMA`` describes a shape that other clauses are checked against, so the modules
	whose oracles are contract-level depend on it. That is a real, checkable relation
	between two clauses — unlike a dependency guessed from reading English.

	This is a *proposal*. It is sound in the sense FR-089 and FR-092 mean — acyclic,
	ordered, traceable — and that is the only sense in which a machine may call a
	decomposition sound.

	``model`` is FR-083's binding, and passing it is what makes the model the *single
	source for interface definitions* rather than a parallel declaration. Each module's
	surface is the members the model declares for the interfaces its clauses introduce —
	so the surface is **derived**, and a module cannot hold an opinion about its own
	public names that differs from the model's. A model that declares no interfaces
	derives nothing and every surface stays empty, which is the honest state ADR-0027
	recorded rather than a guess: nothing in a contract's clauses is a signature.

	``None`` means the caller has no model, which is the state of every project whose P2
	declared none. It is not the same as a model with no interfaces, and the difference
	shows up at P7: the first is a project that never declared one, the second is one
	whose declaration is empty.
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
			# FR-083: the model is the single source, so the surface is read off it
			# rather than invented here. A module's clauses may intersect several
			# interfaces, and the model's own deduplication by name is what keeps two
			# clauses naming the same member from producing two surface entries.
			surface=model.surface_for_clauses((clause.id,)) if model is not None else (),
			completion_criteria=completion_criteria(clause),
			# FR-097's budget, declared here rather than defaulted on the type: a proposal
			# is the one place the factory can put a number in front of the operator at P3,
			# and the gate below reports it as a check so the approval covers it. The value
			# is §7.3's own worked example, so the factory holds a build to the number the
			# spec printed rather than to one it invented.
			budget=DEFAULT_MODULE_BUDGET,
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
				# The declared surface is part of what was approved, or an approval would
				# describe a module whose public names could change underneath it. Same
				# reasoning as ADR-0025's exclusion of ids, in the other direction: ids
				# are excluded because they are minted per proposal, and the surface is
				# included because it is a decision.
				"surface": [member.model_dump(mode="json") for member in m.surface],
				# FR-093's Definition of Done is what P5 is handed, so it is part of what
				# the operator approved. Derived from the clause today and therefore stable
				# across two proposals — but FR-094 makes revisions normal, and a revision
				# could change a module's criteria without touching its interface. An
				# approval that did not cover the criteria would describe a module P5 was
				# never told to build.
				"completion_criteria": list(m.completion_criteria),
				"clauses": list(m.clause_ids),
				"depends_on": sorted(m.depends_on),
				# FR-097's budget is what P7 holds the built module to, so an approval
				# that did not cover it would approve a module and then measure it against
				# a bound nobody signed off. A revision that raises a bound is a revision
				# of the thing approved, which is the distinction FR-094 asks this to make.
				"budget": m.budget.model_dump(mode="json"),
			}
			for m in decomposition.modules
		]
	)


def gate(
	decomposition: Decomposition,
	contract: Contract,
	*,
	envelope: DeliveryEnvelope | None = None,
	value_hypothesis_declared: bool | None = None,
) -> DecompositionGate:
	"""Every P3 precondition a machine can check, as named results (FR-088/089/091/092).

	The checks are *facts about the proposal*, not an opinion of it. ``architecture_is_right``
	is deliberately not among them: §7.1 says there is no oracle for it, so a check named
	that would be a machine claiming the operator's half of the gate. That half stays in
	``DecompositionGate.approved_by``, unset until a human sets it.

	``envelope`` adds FR-057: a proposal over a §1.3 ceiling is refused, and the check
	names the dimension. ``None`` means the caller measured nothing and the check reports
	that rather than passing — the same distinction :func:`sofact.envelope.measure` draws,
	for the same reason.
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

	# FR-093: a module with no completion criteria is not eligible to be built. This is a
	# refusal and not a warning, because the criteria are what P5 is handed: a session
	# dispatched against a module whose DoD is empty has been told to build something and
	# not told what "done" means, which is the failure FR-093 exists to name.
	#
	# `propose` cannot produce such a module — `completion_criteria` is total over the
	# oracle classes and every step kind carries a condition — so a failure here means a
	# decomposition built by hand or by a future proposer that dropped the field. That is
	# the case the check is for: the proposer being correct today is not a reason for the
	# gate to assume it.
	undefined = tuple(m.name for m in decomposition.modules if not m.completion_criteria)
	checks.append(
		GateCheck(
			name="every_module_has_completion_criteria",
			passed=not undefined,
			detail=(
				f"all {len(decomposition.modules)} module(s) carry a Definition of Done "
				f"({len({c for m in decomposition.modules for c in m.completion_criteria})} "
				"distinct condition(s) across them), each derived from its clause's oracle "
				"class rather than authored (FR-093)"
				if not undefined
				else f"{len(undefined)} module(s) with no completion criteria, so nothing "
				f"states what done means for them: {', '.join(undefined)}. A module without "
				"completion criteria is not eligible to be built (FR-093)"
			),
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

	# FR-097: every module declares what it may cost. The type makes the field required, so
	# reaching here means a budget exists — asserted anyway, because a gate that reports a
	# fact it did not check is the failure this whole module exists to avoid.
	#
	# The bound is *reported* rather than thresholded, for the reason FR-091's interface
	# count is: the spec prints one worked example (§7.3) and no rule that would let a
	# machine call a different number wrong. What the gate can refuse is a bound that is
	# *impossible* — each declared surface member has to be defined by the artefact, and a
	# definition occupies at least one non-blank line, so a module whose own surface needs
	# more lines than its budget allows can never satisfy its interface. Dispatching P5
	# against it would spend a session to discover a contradiction the proposal already
	# contained. (A module that only re-exports could fit more names than lines; such a
	# module defines nothing and has a different problem, and this floor is the conservative
	# reading rather than the tight one.)
	impossible = tuple(
		f"{m.name}: {len(m.surface)} declared surface member(s) against a budget of "
		f"{m.budget.max_loc} line(s)"
		for m in decomposition.modules
		if len(m.surface) > m.budget.max_loc
	)
	checks.append(
		GateCheck(
			name="every_module_declares_a_budget",
			passed=not impossible,
			detail=(
				f"all {len(decomposition.modules)} module(s) declare a budget: "
				+ ", ".join(
					f"{m.name} {m.budget.max_files}f/{m.budget.max_loc}l/"
					f"{m.budget.reasoning_class.value}"
					for m in decomposition.modules
				)
				if not impossible
				else f"{len(impossible)} module(s) declare a budget their own surface "
				"cannot fit: " + "; ".join(impossible) + ". Such a module is not buildable, "
				"and the contradiction is in the proposal rather than in the build (FR-097)"
			),
		)
	)

	# FR-057: a decomposition that exceeds the §1.3 envelope is refused, naming the
	# dimension. The decomposition is where the refusal belongs, because it is the first
	# artefact that says how big the platform will be — a refusal at P8 would be a
	# refusal after the build, and §1.3's own words are "must be split by the operator,
	# not silently attempted".
	#
	# Note the asymmetry, which is §1.3's: a proposal *over* a ceiling fails the gate,
	# and one *under* a floor is reported and passes. §1.3's numbers are "targets, not
	# measurements", and a factory that refused to build anything smaller than a platform
	# would refuse the small projects that earn it the trust to attempt large ones.
	checks.append(_envelope_check(decomposition, envelope, value_hypothesis_declared))

	return DecompositionGate(decomposition_id=decomposition.id, checks=tuple(checks))


def _envelope_check(
	decomposition: Decomposition,
	envelope: DeliveryEnvelope | None,
	value_hypothesis_declared: bool | None,
) -> GateCheck:
	"""FR-057's check: measured dimensions against §1.3, refused on the ceilings."""
	if envelope is None:
		return GateCheck(
			name="within_delivery_envelope",
			passed=True,
			detail=(
				"no envelope was supplied, so nothing was measured against §1.3 and this "
				"check asserts nothing (NFR-025). A project run without one is not "
				"thereby over-scoped; it is unmeasured, and the delivery report will say "
				"the same thing"
			),
		)
	actuals = measure(envelope, decomposition, value_hypothesis_declared=value_hypothesis_declared)
	exceeded = actuals.exceeded
	if exceeded:
		named = "; ".join(
			f"{m.dimension.value} {m.actual:g} > {m.bound.stated()}" for m in exceeded
		)
		return GateCheck(
			name="within_delivery_envelope",
			passed=False,
			detail=(
				f"over the §1.3 envelope on {len(exceeded)} dimension(s): {named}. "
				"An over-scoped goal must be split by the operator, not silently "
				"attempted (FR-057)"
			),
		)
	under = actuals.below
	unmeasured = actuals.unmeasured
	reported = ", ".join(
		f"{m.dimension.value}={m.actual:g}" for m in actuals.measurements if m.actual is not None
	)
	notes: list[str] = []
	if under:
		notes.append("below the floor on " + ", ".join(m.dimension.value for m in under))
	if unmeasured:
		notes.append("unmeasured: " + ", ".join(m.dimension.value for m in unmeasured))
	return GateCheck(
		name="within_delivery_envelope",
		passed=True,
		detail=(
			f"within the §1.3 ceilings: {reported}"
			+ (". " + "; ".join(notes) if notes else "")
			+ ". A dimension below its floor is a small delivery and not a defect, and an "
			"unmeasured one is named rather than counted as satisfied (NFR-025)"
		),
	)


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
