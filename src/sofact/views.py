"""Immutable value objects.

Every type here is frozen and rejects unknown fields. Nothing in this module reaches
for I/O — models are data plus invariants, so they can be constructed, compared and
hashed without a session.

Two invariants are enforced by *type* rather than by convention, because conventions
do not survive contact with a producer that wants to declare victory:

* a :class:`Clause` cannot exist without an :class:`OracleDeclaration` (spec FR-001,
  "no oracle, no autonomy");
* a producer's :class:`CompletionClaim` is a different type from :class:`Evidence`
  and is never an input to verification (spec FR-138, "termination is not
  verification").
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Any, Final, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from sofact._uuid7 import uuid7str

__all__ = [
	"INTEGRATION_REQUIREMENTS",
	"MODULE_CLASS_CEILING",
	"ORACLE_RANK",
	"Assumption",
	"AutonomyLevel",
	"CapabilityFinding",
	"Clause",
	"ClauseKind",
	"ClauseStem",
	"ClauseVerdict",
	"CompletionClaim",
	"Contract",
	"DeclarationPrecision",
	"Decomposition",
	"DecompositionGate",
	"DimensionStatus",
	"DispatchMode",
	"DispatchRecord",
	"ElicitationAnswer",
	"ElicitationDimension",
	"Evidence",
	"EvidenceKind",
	"GateCheck",
	"Goal",
	"GoalEntry",
	"GoalPlan",
	"GoalSpec",
	"GoalStep",
	"GoalStyle",
	"HarnessCapability",
	"HarnessProfile",
	"IntegrationCheck",
	"IntegrationFinding",
	"IntegrationFindingKind",
	"IntegrationReport",
	"IntegrityCheck",
	"IntegrityOutcome",
	"IntegritySubject",
	"InterfaceMember",
	"InterfaceMemberKind",
	"LedgerEntry",
	"LedgerKind",
	"Module",
	"ModuleCheckout",
	"ModuleClass",
	"NonGoal",
	"OracleClass",
	"OracleDeclaration",
	"Phase",
	"PhaseAdvance",
	"PhaseGate",
	"PhaseStatus",
	"PlanStepKind",
	"ProbeOutcome",
	"ProjectState",
	"Readiness",
	"RepairAttempt",
	"RepairOutcome",
	"Requirement",
	"Specification",
	"SpecificationDraft",
	"SpecificationGate",
	"StepBudget",
	"StepOutcome",
	"SystemEntity",
	"SystemInvariant",
	"SystemModel",
	"SystemRelationship",
	"ValueHypothesis",
	"VerdictOutcome",
	"VerificationMethod",
	"VerificationReport",
	"canonical_json",
	"ceiling_for_rank",
	"content_hash",
	"now",
]

GENESIS_HASH = "0" * 64
"""``prev_hash`` of the first ledger entry."""


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #


def now() -> datetime:
	"""Current time, always timezone-aware UTC."""
	return datetime.now(UTC)


def canonical_json(value: Any) -> str:
	"""Deterministic JSON: sorted keys, no insignificant whitespace.

	Hashing a dict without this would make the hash depend on insertion order, which
	would make a valid artefact appear tampered with.
	"""
	return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_hash(value: Any) -> str:
	"""SHA-256 of the canonical form of ``value``.

	Accepts a model or a plain structure. Models are dumped in JSON mode first so
	that datetimes and enums hash identically whether they arrived from memory or
	from the ledger.
	"""
	if isinstance(value, BaseModel):
		value = value.model_dump(mode="json")
	return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _non_empty(value: str) -> str:
	text = value.strip()
	if not text:
		raise ValueError("must not be empty or whitespace")
	return text


def _uuid7(value: str) -> str:
	try:
		parsed = uuid.UUID(value)
	except (ValueError, AttributeError, TypeError) as exc:
		raise ValueError(f"not a UUID: {value!r}") from exc
	if parsed.version != 7:
		raise ValueError(f"not a UUID7 (version {parsed.version}): {value!r}")
	return str(parsed)


NonEmptyStr = Annotated[str, AfterValidator(_non_empty)]
UUID7 = Annotated[str, AfterValidator(_uuid7)]


class View(BaseModel):
	"""Base for all value objects: frozen, named-or-aliased, no extra fields."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
		frozen=True,
	)


# --------------------------------------------------------------------------- #
# autonomy
# --------------------------------------------------------------------------- #


class AutonomyLevel(IntEnum):
	"""Shapiro-style autonomy ladder, L0 (manual) to L5 (unattended).

	L5 is representable but unreachable through :func:`ceiling_for_rank`: the spec
	declines to offer a dark factory. A type that *can* express a level it will never
	grant is a type that can be misused, so the guard lives in the deriving function
	rather than in the enum.
	"""

	L0 = 0
	L1 = 1
	L2 = 2
	L3 = 3
	L4 = 4
	L5 = 5


class OracleClass(StrEnum):
	"""Ranked classes of machine-checkable oracle (spec FR-103)."""

	PROPERTY = "property"
	STATE_MACHINE = "state_machine"
	CONTRACT = "contract"
	METAMORPHIC = "metamorphic"
	SCHEMA = "schema"
	EXAMPLE = "example"
	GOLDEN = "golden"


ORACLE_RANK: dict[OracleClass, int] = {
	OracleClass.PROPERTY: 1,
	OracleClass.STATE_MACHINE: 2,
	OracleClass.CONTRACT: 3,
	OracleClass.METAMORPHIC: 4,
	OracleClass.SCHEMA: 5,
	OracleClass.EXAMPLE: 6,
	OracleClass.GOLDEN: 7,
}
"""Rank 1 is strongest. Ranks 1-2 are mandatory above autonomy L2."""

STRONG_ORACLE_MAX_RANK = 2


def ceiling_for_rank(rank: int) -> AutonomyLevel:
	"""Highest autonomy a contract may claim, given its weakest oracle rank.

	The ceiling is set by the *weakest* clause, not the strongest: a contract is
	only as verifiable as its least verifiable part.

	Ranks 1-2 admit L4; ranks 3-4 admit L3; anything weaker caps at L2. L5 is never
	returned.
	"""
	assert 1 <= rank <= len(ORACLE_RANK), f"rank out of range: {rank}"
	if rank <= STRONG_ORACLE_MAX_RANK:
		return AutonomyLevel.L4
	if rank <= 4:
		return AutonomyLevel.L3
	return AutonomyLevel.L2


# --------------------------------------------------------------------------- #
# P0 — elicitation
# --------------------------------------------------------------------------- #


class ElicitationDimension(StrEnum):
	"""The questions a goal must answer before it is falsifiable.

	Deliberately small. Each dimension exists because a specification cannot be
	written without it, and removing any one of them produces a specific, known
	failure: no OUTCOME and the goal cannot be tested, no ORACLE and it cannot be
	checked, no FAILURE and its blast radius is unbounded.
	"""

	OUTCOME = "outcome"
	CONSUMER = "consumer"
	BOUNDARY = "boundary"
	ORACLE = "oracle"
	CONSTRAINT = "constraint"
	FAILURE = "failure"


class Goal(View):
	"""The operator's stated intent, before it has been interrogated."""

	id: UUID7
	statement: NonEmptyStr
	created_at: datetime


class ElicitationAnswer(View):
	"""One operator answer to one dimension."""

	id: UUID7
	goal_id: UUID7
	dimension: ElicitationDimension
	text: NonEmptyStr
	answered_by: NonEmptyStr
	at: datetime


class DimensionStatus(View):
	"""Whether a dimension is resolved, and if not, why not."""

	dimension: ElicitationDimension
	resolved: bool
	reasons: tuple[str, ...]

	def __bool__(self) -> bool:
		return self.resolved


class Readiness(View):
	"""The elicitation gate's verdict."""

	goal_id: UUID7
	statuses: tuple[DimensionStatus, ...]

	@property
	def open_dimensions(self) -> tuple[ElicitationDimension, ...]:
		"""Dimensions that are still unresolved, in declaration order."""
		return tuple(s.dimension for s in self.statuses if not s.resolved)

	@property
	def is_ready(self) -> bool:
		"""True when every dimension is resolved. The only way past P0."""
		return not self.open_dimensions

	@property
	def progress(self) -> tuple[int, int]:
		"""``(resolved, total)``."""
		done = sum(1 for s in self.statuses if s.resolved)
		return done, len(self.statuses)


# --------------------------------------------------------------------------- #
# P2 — specification and contract
# --------------------------------------------------------------------------- #


class ClauseKind(StrEnum):
	"""Positive clauses assert a behaviour; negative clauses bound the blast radius."""

	POSITIVE = "positive"
	NEGATIVE = "negative"


class ClauseStem(View):
	"""A clause before an oracle has been assigned.

	Stems are the honest output of a conversation: the operator's own words, split
	into testable units but not yet checkable. Turning a stem into a
	:class:`Clause` requires naming an oracle.
	"""

	id: UUID7
	statement: NonEmptyStr
	kind: ClauseKind
	derived_from: ElicitationDimension


class OracleDeclaration(View):
	"""How a clause would be checked, and at what strength."""

	oracle_class: OracleClass
	description: NonEmptyStr
	command_hint: NonEmptyStr | None = None
	expect_exit_code: int = 0
	expect_stdout_contains: NonEmptyStr | None = None

	@property
	def rank(self) -> int:
		"""1 (strongest) to 7 (weakest); see :data:`ORACLE_RANK`."""
		return ORACLE_RANK[self.oracle_class]

	@property
	def is_executable(self) -> bool:
		"""Whether this oracle names a command, and so can be run unattended.

		An oracle with no command is not a weaker oracle, it is an *intention*: the
		verifier reports it as insufficient rather than pretending otherwise.
		"""
		return self.command_hint is not None


class Clause(View):
	"""A falsifiable unit of the contract.

	``oracle`` is required and non-nullable. That is the whole point: a contract
	clause that cannot be checked is not a weaker clause, it is not a clause.
	"""

	id: UUID7
	statement: NonEmptyStr
	kind: ClauseKind
	oracle: OracleDeclaration


class SpecificationDraft(View):
	"""Conversation output: clause stems, with no oracle assigned yet."""

	id: UUID7
	goal_id: UUID7
	created_at: datetime
	stems: tuple[ClauseStem, ...]

	@model_validator(mode="after")
	def _require_stems(self) -> Self:
		if not self.stems:
			raise ValueError("a draft with no clause stems asserts nothing")
		return self


class Contract(View):
	"""A draft whose every stem has been given an oracle.

	Construction is the gate: :meth:`from_draft` refuses a draft with unassigned
	oracles, so an unverifiable contract cannot be built by any code path.
	"""

	id: UUID7
	goal_id: UUID7
	version: int
	created_at: datetime
	clauses: tuple[Clause, ...]

	@model_validator(mode="after")
	def _require_clauses(self) -> Self:
		if not self.clauses:
			raise ValueError("a contract with no clauses verifies nothing")
		if self.version < 1:
			raise ValueError(f"version must be >= 1, got {self.version}")
		return self

	@property
	def content_hash(self) -> str:
		"""Hash of the clause set. Recorded so verification can prove *which*
		contract it verified, and so post-hoc edits are detectable (FR-139)."""
		return content_hash([c.model_dump(mode="json") for c in self.clauses])

	@property
	def weakest_oracle_rank(self) -> int:
		"""Rank of the least verifiable clause. Sets the autonomy ceiling."""
		return max(c.oracle.rank for c in self.clauses)

	@property
	def ceiling(self) -> AutonomyLevel:
		"""Autonomy this contract may claim, per :func:`ceiling_for_rank`."""
		return ceiling_for_rank(self.weakest_oracle_rank)

	@classmethod
	def from_draft(
		cls,
		draft: SpecificationDraft,
		oracles: dict[str, OracleDeclaration],
		*,
		version: int = 1,
	) -> Self:
		"""Build a contract, or refuse.

		``oracles`` maps :class:`ClauseStem` id to its declaration. Every stem must
		appear. The error names the stems that did not, because "unverifiable" is
		only actionable when it is specific.
		"""
		assert draft.stems, "draft must carry stems before contracting"
		missing = [s.id for s in draft.stems if s.id not in oracles]
		if missing:
			raise ValueError(
				f"{len(missing)} clause stem(s) have no oracle, so no contract exists: "
				+ ", ".join(missing),
			)
		clauses = tuple(
			Clause(id=s.id, statement=s.statement, kind=s.kind, oracle=oracles[s.id])
			for s in draft.stems
		)
		contract = cls(
			id=uuid7str(),
			goal_id=draft.goal_id,
			version=version,
			created_at=now(),
			clauses=clauses,
		)
		assert contract.weakest_oracle_rank >= 1, "contract has no ranked oracle"
		return contract


# --------------------------------------------------------------------------- #
# P3 — decomposition
# --------------------------------------------------------------------------- #


class ModuleClass(StrEnum):
	"""The Mode G lane classes (spec §14), which fix a module's oracle ceiling.

	The ceiling is a property of the *class*, not of a measurement, because it is a
	statement about what kinds of oracle are manufacturable for that kind of code —
	G7 is auth, secrets, payments or PII, and no manufactured oracle justifies autonomy
	there (FR-126). The measured ceiling from the contract still applies on top: the
	effective ceiling is the lower of the two, which is what keeps a G7 module from
	inheriting L4 because someone wrote strong oracles for it.
	"""

	G1 = "G1"
	G2 = "G2"
	G3 = "G3"
	G4 = "G4"
	G5 = "G5"
	G6 = "G6"
	G7 = "G7"
	G8 = "G8"


MODULE_CLASS_CEILING: dict[ModuleClass, AutonomyLevel] = {
	ModuleClass.G1: AutonomyLevel.L4,
	ModuleClass.G2: AutonomyLevel.L4,
	ModuleClass.G3: AutonomyLevel.L3,
	ModuleClass.G4: AutonomyLevel.L3,
	ModuleClass.G5: AutonomyLevel.L2,
	ModuleClass.G6: AutonomyLevel.L2,
	ModuleClass.G7: AutonomyLevel.L1,
	ModuleClass.G8: AutonomyLevel.L2,
}
"""Spec §14's table. G7 is L1 *by class* — FR-126 makes it human-authored."""


class Module(View):
	"""One unit of decomposition: what gets built, and what it may depend on (FR-090).

	``interface`` is declared rather than inferred. FR-090 forbids depending on another
	module's internals, and the only way that is checkable is if the permitted surface
	is written down before the module exists. ``depends_on`` names module ids, and
	:meth:`Decomposition` refuses a cycle (FR-089).

	``clause_ids`` is FR-088's traceability in one direction: the requirements this
	module exists to satisfy. The other direction — every requirement reaching a module
	— is a property of the whole decomposition, so it is checked there rather than here.
	"""

	id: UUID7
	name: NonEmptyStr
	module_class: ModuleClass
	interface: NonEmptyStr
	clause_ids: tuple[UUID7, ...] = ()
	depends_on: tuple[UUID7, ...] = ()
	surface: tuple[InterfaceMember, ...] = ()
	"""The declared public names, in a form FR-112 can diff a build against.

	Empty is a real state and not an error: nothing in a contract's clauses is a
	machine-readable signature (``OracleDeclaration`` carries a class, a description and
	an optional command, and no parameter list), so a proposal has nothing to derive one
	from and says so by leaving this empty. P7 reports an empty surface as *uncovered*
	rather than as conforming, which is the difference between "the diff was empty" and
	"there was nothing to diff".
	"""

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if not self.clause_ids:
			raise ValueError(
				f"module {self.name!r} maps to no requirement, so nothing would be missed "
				"if it were never built (FR-088)"
			)
		if self.id in self.depends_on:
			raise ValueError(f"module {self.name!r} depends on itself")
		return self

	@property
	def ceiling(self) -> AutonomyLevel:
		"""The highest autonomy this module's *class* permits (FR-125/FR-126)."""
		return MODULE_CLASS_CEILING[self.module_class]


class InterfaceMemberKind(StrEnum):
	"""What kind of public name a module declares on its surface (FR-090, FR-112)."""

	FUNCTION = "function"
	CLASS = "class"
	CONSTANT = "constant"


class InterfaceMember(View):
	"""One declared public name, in a form a machine can diff against a build (FR-112).

	FR-112 requires the public-API diff to be empty, and a diff needs two sides. This is
	the declared side: what the module's surface *is*, stated before the module exists.

	``parameters`` is empty for a constant and for a class, and for a function it is the
	parameter names in order. It is deliberately not a type signature: SoFact does not
	know the operator's language (ADR-0025), and a type it invented would be a fabricated
	contract that P5 implements and P7 certifies. A name and its arity is the part that is
	both language-agnostic and checkable.
	"""

	name: NonEmptyStr
	kind: InterfaceMemberKind
	parameters: tuple[NonEmptyStr, ...] = ()

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if self.kind is not InterfaceMemberKind.FUNCTION and self.parameters:
			raise ValueError(f"{self.name!r} is a {self.kind.value} and cannot carry parameters")
		return self


class GateCheck(View):
	"""One machine-checkable precondition of a gate, and whether it holds.

	Modelled as a check with a reason rather than a bare boolean so a refusal can name
	*which* precondition failed. A gate that returns only "no" is one an operator has to
	re-derive by hand, which is how a gate becomes theatre.
	"""

	name: NonEmptyStr
	passed: bool
	detail: NonEmptyStr

	def __bool__(self) -> bool:
		return self.passed


class Decomposition(View):
	"""P3's artefact: modules, their dependency DAG, and the order to build them (FR-092).

	A *proposal* until the operator approves it. Nothing here is a gate result — the gate
	is :class:`DecompositionGate`, computed from this, because FR-087 separates what the
	machine proposes from what the human validates and a single type would blur the two.
	"""

	id: UUID7
	goal_id: UUID7
	contract_id: UUID7
	created_at: datetime
	modules: tuple[Module, ...]

	@model_validator(mode="after")
	def _well_formed(self) -> Self:
		if not self.modules:
			raise ValueError("a decomposition with no modules decomposes nothing")
		names = [m.name for m in self.modules]
		if len(set(names)) != len(names):
			raise ValueError("two modules share a name, so no build order could name them")
		known = {m.id for m in self.modules}
		for module in self.modules:
			unknown = [d for d in module.depends_on if d not in known]
			if unknown:
				raise ValueError(f"module {module.name!r} depends on unknown module(s): {unknown}")
		return self

	def module(self, module_id: str) -> Module | None:
		"""Look up a module by id."""
		return next((m for m in self.modules if m.id == module_id), None)

	def module_by_name(self, name: str) -> Module | None:
		"""Look up a module by name. Names are unique, so this is a real lookup."""
		return next((m for m in self.modules if m.name == name), None)

	def module_for_clauses(self, clause_ids: tuple[str, ...]) -> Module | None:
		"""The module that owns ``clause_ids``, or ``None`` when no single one does.

		This is what lets a *step* name the module it builds (FR-100). FR-136 forbids one
		goal session per module -- a module does not fit in one session's context -- so a
		module's work spans several steps, and each of those steps is on the module's
		branch because of this lookup.

		``None`` is a real answer, not an error: a bootstrap step covers no clause, and a
		step whose clauses span two modules is a step that belongs to neither. Both are
		cases where naming a module would be a guess, and a branch named from a guess is
		worse than a branch named from the step.
		"""
		owners = {m.id for m in self.modules if set(clause_ids) & set(m.clause_ids)}
		if len(owners) != 1:
			return None
		return self.module(next(iter(owners)))

	@property
	def interface_count(self) -> int:
		"""How many module surfaces must integrate (FR-091).

		A first-class metric rather than a derived nicety: integration risk grows with
		it, possibly as ``n²`` (§1.4), so it is a gate input.
		"""
		return len(self.modules)

	@property
	def class_distribution(self) -> dict[ModuleClass, int]:
		"""Modules per lane class, which FR-125 makes a decomposition-quality signal."""
		distribution: dict[ModuleClass, int] = {}
		for module in self.modules:
			distribution[module.module_class] = distribution.get(module.module_class, 0) + 1
		return distribution

	@property
	def target_class_share(self) -> float:
		"""Fraction of modules in G1-G2, the invariant-rich classes FR-125 targets.

		Not a pass/fail threshold, and deliberately not turned into one: the spec calls
		it a signal. A decomposition of a UI is legitimately 0.0 and is not thereby
		wrong.
		"""
		if not self.modules:
			return 0.0
		target = {ModuleClass.G1, ModuleClass.G2}
		return sum(1 for m in self.modules if m.module_class in target) / len(self.modules)

	def build_order(self) -> tuple[Module, ...]:
		"""Modules in topological order, dependencies first (FR-092).

		Kahn's algorithm over the declared DAG. Ties are broken by name so the order is
		*deterministic*: an order that varies between runs would make the plan's step
		ordinals — and therefore its branch names — unstable for an unchanged
		decomposition, which would break FR-099's idempotence for no reason.
		"""
		remaining = {m.id: m for m in self.modules}
		done: set[str] = set()
		ordered: list[Module] = []
		while remaining:
			ready = sorted(
				(m for m in remaining.values() if set(m.depends_on) <= done),
				key=lambda m: m.name,
			)
			if not ready:
				raise ValueError(
					"decomposition has a dependency cycle; no module can be built first"
				)
			for module in ready:
				ordered.append(module)
				done.add(module.id)
				del remaining[module.id]
		return tuple(ordered)

	def cycles(self) -> tuple[tuple[str, ...], ...]:
		"""Cycles in the declared dependency graph (FR-089).

		Reported rather than raised so the gate can name them: "this decomposition has a
		cycle" is actionable only when it says which modules are in it.
		"""
		edges = {m.id: list(m.depends_on) for m in self.modules}
		by_id = {m.id: m for m in self.modules}
		found: list[tuple[str, ...]] = []
		colour: dict[str, int] = {}

		def visit(node: str, path: list[str]) -> None:
			colour[node] = 1
			path.append(node)
			for neighbour in edges.get(node, []):
				if colour.get(neighbour) == 1:
					start = path.index(neighbour)
					found.append(tuple(by_id[n].name for n in [*path[start:], neighbour]))
				elif colour.get(neighbour, 0) == 0:
					visit(neighbour, path)
			path.pop()
			colour[node] = 2

		for module_id in sorted(edges, key=lambda i: by_id[i].name):
			if colour.get(module_id, 0) == 0:
				visit(module_id, [])
		return tuple(found)


class DecompositionGate(View):
	"""P3's deterministic gate: what the machine can check, and what only the operator can.

	Two halves, and conflating them is the mistake this type exists to prevent.

	*The machine half* is computed here from the decomposition alone — traceability both
	ways (FR-088), acyclicity (FR-089), a declared build order (FR-092), and that every
	module maps to a requirement that exists in the contract. These are facts.

	*The operator half* is FR-087's "human-validated": architecture has no oracle
	(§7.1), so "this is the right decomposition" cannot be machine-checked, and
	:attr:`is_satisfied` is false until a human says so. A gate whose machine half passed
	and whose operator half did not is *not* passable, which is FR-061's hard stop.
	"""

	decomposition_id: UUID7
	checks: tuple[GateCheck, ...]
	approved_by: NonEmptyStr | None = None
	approved_at: datetime | None = None

	@model_validator(mode="after")
	def _approval_is_whole(self) -> Self:
		if (self.approved_by is None) != (self.approved_at is None):
			raise ValueError("an approval names both who approved it and when")
		return self

	@property
	def machine_checks(self) -> tuple[GateCheck, ...]:
		"""The checks the factory computed, as opposed to the operator's decision."""
		return self.checks

	@property
	def failed(self) -> tuple[GateCheck, ...]:
		"""Machine checks that did not hold."""
		return tuple(c for c in self.checks if not c.passed)

	@property
	def is_approved(self) -> bool:
		"""Whether a human has approved this decomposition (FR-087)."""
		return self.approved_by is not None

	@property
	def is_satisfied(self) -> bool:
		"""Whether work may proceed past P3. The only way through (FR-061).

		Both halves, and the machine half is not negotiable by approving: an operator can
		approve a *sound* decomposition, but approval cannot make an unsound one sound.
		"""
		return not self.failed and self.is_approved


# --------------------------------------------------------------------------- #
# P2 — the specification artifact (FR-076 to FR-086)
# --------------------------------------------------------------------------- #


class VerificationMethod(StrEnum):
	"""How a requirement's acceptance criterion is evaluated (FR-077, FR-082).

	``HUMAN`` is first-class and is not a failure. FR-082 says a requirement whose
	criterion cannot be mechanically evaluated "must be marked ``human-verified`` and its
	verification cost counted against the human budget". Collapsing it into the
	machine-checkable set would make the human budget a number nobody computes, and
	collapsing it into a defect would make an honest specification look broken.
	"""

	ORACLE = "oracle"
	"""A machine runs the clause's oracle. The only method that costs no human time."""

	HUMAN = "human"
	"""The operator reads an artefact and decides. Counted against the human budget."""


class Requirement(View):
	"""One specification-level requirement, traceable to the clauses that stated it.

	FR-076 asks for requirements traceable to intent clauses; FR-077 requires each to
	carry a machine-checkable acceptance criterion, and makes its absence "a defect in
	the specification" that "must block the P2 gate".

	``criterion`` is required and non-empty for the same reason a :class:`Clause` cannot
	exist without an oracle: a requirement nobody can evaluate is not a weaker
	requirement, it is a wish. ``verification_method`` is what keeps FR-082 honest — a
	criterion stated in prose is allowed, but only as ``HUMAN``, where its cost is
	visible at the gate rather than hidden in the word "checkable".
	"""

	id: UUID7
	statement: NonEmptyStr
	criterion: NonEmptyStr
	"""How the requirement is known to hold, in a form the method below can evaluate."""

	verification_method: VerificationMethod
	clause_ids: tuple[UUID7, ...]
	"""The intent clauses this requirement traces to (FR-076). Never empty."""

	@model_validator(mode="after")
	def _traces_to_something(self) -> Self:
		if not self.clause_ids:
			raise ValueError(
				f"requirement {self.statement[:40]!r} traces to no intent clause, so "
				"nothing the operator said requires it (FR-076)"
			)
		return self

	@property
	def is_machine_checkable(self) -> bool:
		"""Whether an oracle can decide this without a human (FR-077, FR-082)."""
		return self.verification_method is VerificationMethod.ORACLE


class NonGoal(View):
	"""Something the specification explicitly does not do (FR-079).

	Declared rather than inferred. A non-goal is the operator's boundary decision, and
	the spec's own elicitation already asks for it (the ``BOUNDARY`` dimension) — this
	is where that answer becomes part of the artefact P2 gates on.
	"""

	id: UUID7
	statement: NonEmptyStr
	clause_ids: tuple[UUID7, ...] = ()


class Assumption(View):
	"""Load-bearing uncertainty, declared and visible at the gate (FR-079).

	FR-079: "Assumptions are the load-bearing uncertainty and must be visible at the
	gate, not buried." ``refuted_by`` is what makes an assumption falsifiable rather
	than a disclaimer: it names the observation that would show the assumption false,
	which is the same shape FR-085 asks of the value hypothesis.
	"""

	id: UUID7
	statement: NonEmptyStr
	refuted_by: NonEmptyStr
	"""What would show this assumption false. Required: an unfalsifiable assumption
	is a belief, and FR-079 asks for uncertainty the gate can act on."""


class ValueHypothesis(View):
	"""What economic effect the platform is expected to produce, and how to refute it.

	FR-085 requires it falsifiable, naming the effect, for whom, and the instrument that
	would refute it. FR-086 then forbids SoFact from certifying it, which is why this
	type carries no verdict field and nothing in this module can mark it satisfied: the
	factory's only permitted statement about a value hypothesis is that it was *declared*.
	"""

	effect: NonEmptyStr
	"""The economic effect expected, stated so that its absence would be observable."""

	beneficiary: NonEmptyStr
	"""Who the effect accrues to."""

	refuting_instrument: NonEmptyStr
	"""The measurement that would show the effect did not occur (FR-085)."""


class SystemEntity(View):
	"""A thing the system stores or manipulates (FR-078, FR-083).

	FR-083 makes the model "the single source for interface definitions", so an entity
	here is not documentation: it is what P3 decomposes against and what P7 checks the
	assembled system for (FR-115).

	``clause_ids`` is FR-081's "every entity in the model must be referenced by a
	requirement", declared rather than searched. The cheap check is to look for the
	entity's name inside a requirement's prose, and it fails open: an entity called
	``id`` or ``job`` occurs in unrelated sentences, so a text search passes on
	specifications that reference nothing. The link points at the *clause* rather than at
	a requirement id because :func:`~sofact.specification.specify` derives requirements
	one per clause and mints their ids, so a clause is the stable thing an operator can
	actually name when declaring the model.
	"""

	name: NonEmptyStr
	description: NonEmptyStr
	clause_ids: tuple[UUID7, ...] = ()


class SystemRelationship(View):
	"""How two entities are related (FR-078).

	Named by entity *name* rather than id because the model is declared before any
	entity has an identity, and a relationship that had to wait for ids could not be
	part of the same declaration the entities are.
	"""

	subject: NonEmptyStr
	predicate: NonEmptyStr
	object: NonEmptyStr

	@model_validator(mode="after")
	def _not_reflexive_by_accident(self) -> Self:
		if self.subject == self.object and self.predicate.strip().lower() in {
			"is",
			"equals",
			"same",
		}:
			raise ValueError(
				f"{self.subject!r} {self.predicate} itself asserts nothing; a "
				"relationship names two entities or it is a tautology"
			)
		return self


class SystemInvariant(View):
	"""A property the system must hold at all times (FR-078).

	The model's invariants are the second oracle class §9.2 calls O3 structural: they
	are checkable against a declaration before any code runs, which is why they belong
	in the model rather than in the contract's oracle set.
	"""

	id: UUID7
	statement: NonEmptyStr
	entity_names: tuple[NonEmptyStr, ...] = ()


class SystemModel(View):
	"""The machine-readable model: entities, relationships, invariants (FR-078, FR-083).

	FR-083: "must be machine-readable and must be the single source for interface
	definitions". The interface half lives on :class:`Module.surface`, derived from the
	contract, and this type carries the half that is not per-module — the entities and
	relationships that only exist once the system is assembled, which is exactly what
	FR-115 checks and what ADR-0027 could not reach.
	"""

	entities: tuple[SystemEntity, ...] = ()
	relationships: tuple[SystemRelationship, ...] = ()
	invariants: tuple[SystemInvariant, ...] = ()

	@model_validator(mode="after")
	def _relationships_name_declared_entities(self) -> Self:
		"""FR-081: "every entity in the model must be referenced by a requirement".

		The converse — a relationship naming an entity the model does not declare — is
		the defect this catches, and it is a real one: a relationship over an undeclared
		entity is a statement about something P3 cannot decompose and P7 cannot check.
		"""
		known = {e.name for e in self.entities}
		for rel in self.relationships:
			for side in (rel.subject, rel.object):
				if side not in known:
					raise ValueError(
						f"relationship {rel.subject!r} {rel.predicate} {rel.object!r} "
						f"names {side!r}, which the model does not declare as an entity "
						"(FR-081)"
					)
		return self

	@property
	def is_empty(self) -> bool:
		"""Whether the model declares nothing, so nothing can be conformed against."""
		return not (self.entities or self.relationships or self.invariants)

	@property
	def entity_names(self) -> frozenset[str]:
		"""Every declared entity name, for reference checks."""
		return frozenset(e.name for e in self.entities)


class Specification(View):
	"""P2's artefact: requirements, the system model, non-goals, assumptions, value (FR-076).

	The thing the first gate is a gate *on*. Before this type existed, P2 produced
	nothing and the gate had no subject, which is why FR-076 through FR-086 were all
	unbuilt and why both remaining P7 checks were blocked.

	A *proposal* until the operator approves it, exactly as :class:`Decomposition` is:
	the machine proposes and the human validates (FR-087's precedent), and the two are
	separate types so a proposal cannot be mistaken for an approved one.
	"""

	id: UUID7
	goal_id: UUID7
	contract_id: UUID7
	created_at: datetime
	requirements: tuple[Requirement, ...]
	system_model: SystemModel = SystemModel()
	non_goals: tuple[NonGoal, ...] = ()
	assumptions: tuple[Assumption, ...] = ()
	value_hypothesis: ValueHypothesis | None = None

	@model_validator(mode="after")
	def _requires_requirements(self) -> Self:
		if not self.requirements:
			raise ValueError("a specification with no requirements specifies nothing")
		return self

	@property
	def clause_ids(self) -> frozenset[str]:
		"""Every intent clause this specification traces to (FR-076)."""
		return frozenset(cid for r in self.requirements for cid in r.clause_ids)

	def requirements_for_clause(self, clause_id: str) -> tuple[Requirement, ...]:
		"""Requirements that trace to one intent clause."""
		return tuple(r for r in self.requirements if clause_id in r.clause_ids)

	def uncovered_clauses(self, clause_ids: frozenset[str]) -> tuple[str, ...]:
		"""Clauses in ``clause_ids`` that no requirement traces to (FR-076).

		FR-076 says every requirement is traceable *to* a clause; the direction that
		makes the specification complete is the other one, and it is the same two-way
		rule FR-088 applies one phase later.
		"""
		return tuple(sorted(clause_ids - self.clause_ids))

	@property
	def human_verified(self) -> tuple[Requirement, ...]:
		"""Requirements whose criterion needs a person (FR-082)."""
		return tuple(r for r in self.requirements if not r.is_machine_checkable)

	@property
	def content_hash(self) -> str:
		"""Hash of the specification, so a later phase can prove which one it read."""
		return content_hash(self.model_dump(mode="json"))


class SpecificationGate(View):
	"""P2's gate: what the machine can check, and what only the operator can (FR-061, FR-080).

	The same two-half shape as :class:`DecompositionGate`, for the same reason: §3.3
	places a gate at P2 because "no oracle exists for 'this specification expresses your
	actual intent'", so :attr:`is_satisfied` is false until a human says so, and a
	passing machine half cannot be approved into soundness.
	"""

	specification_id: UUID7
	checks: tuple[GateCheck, ...]
	approved_by: NonEmptyStr | None = None
	approved_at: datetime | None = None

	@model_validator(mode="after")
	def _approval_is_whole(self) -> Self:
		if (self.approved_by is None) != (self.approved_at is None):
			raise ValueError("an approval names both who approved it and when")
		return self

	@property
	def failed(self) -> tuple[GateCheck, ...]:
		"""Machine checks that did not hold."""
		return tuple(c for c in self.checks if not c.passed)

	@property
	def is_approved(self) -> bool:
		"""Whether a human has approved this specification."""
		return self.approved_by is not None

	@property
	def is_satisfied(self) -> bool:
		"""Whether work may proceed past P2. Both halves (FR-061)."""
		return not self.failed and self.is_approved


# --------------------------------------------------------------------------- #
# the phase machine — FR-060, FR-061, NFR-028
# --------------------------------------------------------------------------- #


class Phase(StrEnum):
	"""The production pipeline's phases (spec §3.1), in order.

	Named as a closed enum because FR-060 asks for *explicit* transitions: a phase
	the code cannot spell is a phase no transition can name, and "which phase are we
	in" would go back to being inferred from whichever ledger rows happen to exist.

	P7 is a member even though §3.2's summary table omits it. The diagram places
	``P7 Integrate`` between P6 and the deploy gate, and FR-111 to FR-116 give it
	requirements and two checks, so the table is the thing that is wrong. A phase
	machine built from the table would have nowhere to record an integration pass,
	which is the artefact FR-114's minimum violating set is read from.
	"""

	ELICIT = "P0"
	RESEARCH = "P1"
	SPECIFY = "P2"
	DECOMPOSE = "P3"
	CONTRACT = "P4"
	BUILD = "P5"
	VERIFY = "P6"
	INTEGRATE = "P7"
	DELIVER = "P8"
	EVOLVE = "P9"


PHASE_SEQUENCE: tuple[Phase, ...] = tuple(Phase)
"""Pipeline order. ``tuple(Phase)`` because a StrEnum's member order is its definition
order, so the sequence cannot drift from the enum by being written out twice."""


class PhaseGate(StrEnum):
	"""The four human gates (spec §3.3). Deliberately four, not ten.

	§3.3 places a gate only where a machine cannot decide because there is no ground
	truth to check against. Adding one at P5/P6 would restore the per-diff review
	bottleneck the product exists to remove, which is why this enum is short and why
	the phase machine must not grow a fifth without that argument being made.
	"""

	SPECIFICATION = "specification"
	DECOMPOSITION = "decomposition"
	CONTRACT_SAMPLE = "contract_sample"
	DEPLOY = "deploy"


PHASE_GATE: dict[Phase, PhaseGate] = {
	Phase.SPECIFY: PhaseGate.SPECIFICATION,
	Phase.DECOMPOSE: PhaseGate.DECOMPOSITION,
	Phase.CONTRACT: PhaseGate.CONTRACT_SAMPLE,
	Phase.DELIVER: PhaseGate.DEPLOY,
}
"""Which phases are gated. Read from §3.3's list, not from the diagram's boxes — the
diagram draws P2 and P3 as gates and P4's is sampled rather than blocking, so a
reader of the picture alone would place three."""


class PhaseStatus(StrEnum):
	"""Where a phase is. ``AWAITING_GATE`` is the one that carries FR-061.

	A gated phase whose machine work is done is *not* complete and *not* merely active:
	it is waiting for a human, and FR-061 says nothing downstream may proceed while it
	waits. Collapsing that into ``ACTIVE`` would make a phase that cannot advance look
	identical to one that is working, which is the state an operator most needs to see.
	"""

	PENDING = "pending"
	ACTIVE = "active"
	AWAITING_GATE = "awaiting_gate"
	COMPLETE = "complete"


class PhaseAdvance(View):
	"""One transition of the phase machine: where it went, and who moved it (FR-060).

	Recorded as its own ledger row rather than derived, because FR-060 asks for
	transitions that are "explicit ... persisted durably, auditable" and a value
	recomputed from other rows is none of those — it is a guess that happens to agree
	with the log today.

	The two validators below are the structural half of FR-061. A gate phase cannot be
	marked complete without naming who approved it, and a phase that has no gate cannot
	carry an approval at all. Both are refusals to *construct* a record that would
	claim something the pipeline never did, which is stronger than checking for it
	later: there is no code path that can write the lie in the first place.
	"""

	phase: Phase
	status: PhaseStatus
	at: datetime
	by: NonEmptyStr
	"""Who moved it: ``operator`` for a gate, ``factory`` for machine work."""

	checks: tuple[GateCheck, ...] = ()
	"""What the machine could check before the gate, where there is one.

	Empty for an ungated phase. ``GateCheck`` is reused rather than re-invented because
	its property — a check carries the reason it failed, not only a boolean — is exactly
	what FR-080 needs when it asks the P2 gate to present the specification in the
	operator's language.
	"""

	approved_by: NonEmptyStr | None = None
	approved_at: datetime | None = None
	note: NonEmptyStr | None = None

	@model_validator(mode="after")
	def _approval_is_whole(self) -> Self:
		if (self.approved_by is None) != (self.approved_at is None):
			raise ValueError("an approval names both who approved it and when")
		return self

	@model_validator(mode="after")
	def _a_gate_is_never_passed_by_a_machine(self) -> Self:
		gated = self.phase in PHASE_GATE
		if self.approved_by is not None and not gated:
			raise ValueError(
				f"{self.phase.value} has no gate, so an approval on it would name a "
				"decision the pipeline never asks for (FR-061)"
			)
		if self.status is PhaseStatus.COMPLETE and gated and self.approved_by is None:
			raise ValueError(
				f"{self.phase.value} is a gate phase and cannot be complete without an "
				f"approval; FR-061 makes {PHASE_GATE[self.phase].value} a hard stop"
			)
		if self.status is PhaseStatus.AWAITING_GATE and not gated:
			raise ValueError(f"{self.phase.value} has no gate to await (FR-061)")
		return self

	@property
	def gate(self) -> PhaseGate | None:
		"""The gate this phase must pass, or ``None`` for an ungated phase."""
		return PHASE_GATE.get(self.phase)

	@property
	def is_blocking(self) -> bool:
		"""Whether this transition leaves the pipeline stopped at a gate (FR-061)."""
		return self.status is PhaseStatus.AWAITING_GATE


# --------------------------------------------------------------------------- #
# producer claims and evidence — deliberately different types
# --------------------------------------------------------------------------- #


class EvidenceKind(StrEnum):
	"""Forms of machine-produced evidence a verifier may consider."""

	TEST_RESULT = "test_result"
	PROPERTY_RUN = "property_run"
	COMMAND_OUTPUT = "command_output"
	ARTIFACT_DIGEST = "artifact_digest"


class Evidence(View):
	"""Something a machine observed.

	Evidence carries raw observations, never a conclusion. There is no ``passed``
	field: the verifier decides, from the payload, whether the clause holds.

	``run_id`` groups the observations made by one execution of an oracle set. It is an
	*ordering token*, not a content hash: it distinguishes a later observation from an
	earlier one, which is what FR-006 needs in order to refuse a stale result, but it
	does not prove that the artefact changed. ``None`` means unattributed — evidence
	recorded without a run, which a verdict then treats as one undifferentiated set.
	"""

	id: UUID7
	clause_id: UUID7
	kind: EvidenceKind
	produced_by: NonEmptyStr
	payload: dict[str, Any]
	content_hash: str
	at: datetime
	run_id: UUID7 | None = None

	@classmethod
	def record(
		cls,
		*,
		clause_id: str,
		kind: EvidenceKind,
		produced_by: str,
		payload: dict[str, Any],
		run_id: str | None = None,
	) -> Self:
		"""Record an observation, hashing its payload for integrity."""
		assert clause_id and produced_by, "evidence needs a clause and a producer"
		return cls(
			id=uuid7str(),
			clause_id=clause_id,
			kind=kind,
			produced_by=produced_by,
			payload=payload,
			content_hash=content_hash(payload),
			at=now(),
			run_id=run_id,
		)


class CompletionClaim(View):
	"""A producer asserting it is finished.

	This type exists to be *recorded and ignored*. It is not evidence, it is a fact
	about the producer, and no verifier accepts it (FR-138). Keeping it as a
	separate type means the mistake is a type error rather than a judgement call.
	"""

	id: UUID7
	goal_id: UUID7
	declared_by: NonEmptyStr
	note: NonEmptyStr | None = None
	at: datetime


# --------------------------------------------------------------------------- #
# verification verdicts
# --------------------------------------------------------------------------- #


class VerdictOutcome(StrEnum):
	"""What the verifier concluded about one clause.

	``INSUFFICIENT`` is a first-class outcome, not an error. A clause whose oracle
	could not be run is *not* satisfied, and collapsing that into either of the other
	two would be the single most expensive mistake this system could make.
	"""

	SATISFIED = "satisfied"
	VIOLATED = "violated"
	INSUFFICIENT = "insufficient"


class ClauseVerdict(View):
	"""A verifier's conclusion about one clause of one contract."""

	clause_id: UUID7
	statement: NonEmptyStr
	outcome: VerdictOutcome
	reason: NonEmptyStr
	evidence_ids: tuple[UUID7, ...] = ()


class VerificationReport(View):
	"""The whole verdict for a contract.

	The report names the contract *and* its hash, so a verdict cannot be detached
	from the exact clause set it was rendered against (FR-139).
	"""

	contract_id: UUID7
	contract_hash: str
	weakest_oracle_rank: int
	ceiling: AutonomyLevel
	verdicts: tuple[ClauseVerdict, ...]
	at: datetime
	run_id: str = ""
	"""The run whose observations this report weighed. Empty only on a report that
	weighed an unnamed scope."""

	cache_key: str = ""
	"""FR-006's key: content hash of the contract, the change, and the oracle set.
	Empty when no artefact was digestable, in which case the verdict is never reusable."""

	reused_from: datetime | None = None
	"""When the reused verdict was first rendered, if this one is a reuse."""

	@model_validator(mode="after")
	def _require_verdicts(self) -> Self:
		if not self.verdicts:
			raise ValueError("a report with no verdicts reports nothing")
		return self

	@property
	def satisfied(self) -> tuple[ClauseVerdict, ...]:
		"""Clauses demonstrated to hold."""
		return tuple(v for v in self.verdicts if v.outcome is VerdictOutcome.SATISFIED)

	@property
	def violated(self) -> tuple[ClauseVerdict, ...]:
		"""Clauses demonstrated *not* to hold."""
		return tuple(v for v in self.verdicts if v.outcome is VerdictOutcome.VIOLATED)

	@property
	def insufficient(self) -> tuple[ClauseVerdict, ...]:
		"""Clauses on which no conclusion could be reached."""
		return tuple(v for v in self.verdicts if v.outcome is VerdictOutcome.INSUFFICIENT)

	@property
	def is_clean(self) -> bool:
		"""True only when *every* clause is satisfied.

		Partial verification is not verification. This is the single predicate any
		gate should consult.
		"""
		return len(self.satisfied) == len(self.verdicts)

	@property
	def outcome(self) -> VerdictOutcome:
		"""Aggregate verdict, worst-case dominant.

		One counterexample outweighs any amount of corroboration, and an unrun oracle
		outweighs silence, so the ordering is violated > insufficient > satisfied.
		"""
		if self.violated:
			return VerdictOutcome.VIOLATED
		if self.insufficient:
			return VerdictOutcome.INSUFFICIENT
		return VerdictOutcome.SATISFIED


# --------------------------------------------------------------------------- #
# P3/P4 — the goal plan (FR-136, FR-137)
# --------------------------------------------------------------------------- #


class PlanStepKind(StrEnum):
	"""The kinds of goal session a contract compiles into (spec §8.4).

	The set is the canonical plan shape, not an invention: bootstrap, interfaces
	stubs, one step per operation, invariants, the state machine, and repair to
	threshold. Each kind exists because it needs a *different* session, which is the
	only real constraint — a single session is bounded by context and token budget.
	"""

	BOOTSTRAP = "bootstrap"
	INTERFACES = "interfaces"
	OPERATION = "operation"
	INVARIANT = "invariant"
	STATE_MACHINE = "state_machine"
	REPAIR = "repair"


class GoalStyle(StrEnum):
	"""How a goal is rendered for a harness (FR-137).

	Two renderings of the same six parts. Which one a harness receives is a property
	of the harness, not a decision SoFact makes, so it is configuration (FR-156).
	"""

	LABELLED = "labelled"
	OBJECTIVE = "objective"


def _terminated(text: str) -> str:
	"""``text`` with exactly one terminal full stop.

	Exists because the six goal parts are written independently and each ends in its own
	punctuation, so naive interpolation produces ``…(FR-150).. Use …``. Cosmetic on the
	face of it, but this text is hashed (FR-139) and read by a model, and a goal that
	reads as boilerplate is a goal that gets skimmed.
	"""
	stripped = text.rstrip()
	return stripped if stripped.endswith(".") else f"{stripped}."


def _sentences(items: tuple[str, ...]) -> str:
	"""Join independent statements into one sentence, dropping each one's own stop."""
	return "; ".join(item.rstrip().rstrip(".").rstrip() for item in items)


class GoalSpec(View):
	"""One session's objective, in the cross-harness six-part shape (FR-137).

	The shape is not ours: [S18] records it as portable across goal modes, and that
	portability is what makes a harness-agnostic adapter possible at all. Every part
	is required, because the parts are not decoration — a goal with no verification
	surface cannot be checked, and a goal with no blocked stop condition is a goal
	that runs until its budget dies.
	"""

	outcome: NonEmptyStr
	verification_surface: tuple[NonEmptyStr, ...]
	constraints: tuple[NonEmptyStr, ...]
	boundaries: tuple[NonEmptyStr, ...]
	iteration_policy: NonEmptyStr
	blocked_stop_condition: NonEmptyStr

	@model_validator(mode="after")
	def _require_teeth(self) -> Self:
		if not self.verification_surface:
			raise ValueError("a goal with no verification surface is not checkable")
		if not self.boundaries:
			raise ValueError("a goal with no boundaries has an unbounded blast radius")
		return self

	def render(self, style: GoalStyle = GoalStyle.LABELLED) -> str:
		"""Render the six parts as the text a harness receives.

		Deterministic by construction. FR-139 hashes this text and re-hashes it after
		the session, so any variation between compiling and dispatching would be
		indistinguishable from a producer editing its own objective.
		"""
		if style is GoalStyle.OBJECTIVE:
			return (
				f"{_terminated(self.outcome)} Verified by "
				f"{_sentences(self.verification_surface)}. "
				f"Preserve {_sentences(self.constraints)}. "
				f"Stay within {_sentences(self.boundaries)}; anything outside that scope is out "
				"of bounds. "
				f"Between iterations, {_terminated(self.iteration_policy)} "
				"If blocked or no defensible path remains, stop with "
				f"{_terminated(self.blocked_stop_condition)}"
			)
		sections: tuple[tuple[str, tuple[str, ...]], ...] = (
			("Verification surface", self.verification_surface),
			("Constraints", self.constraints),
			("Boundaries", self.boundaries),
		)
		lines = [self.outcome]
		for heading, items in sections:
			if not items:
				continue
			lines.extend(("", f"{heading}:"))
			lines.extend(f"- {item}" for item in items)
		lines.extend(("", "Iteration policy:", self.iteration_policy))
		lines.extend(("", "Blocked stop condition:", self.blocked_stop_condition))
		return "\n".join(lines)

	def text_hash(self, style: GoalStyle = GoalStyle.LABELLED) -> str:
		"""Hash of the rendered goal, pinned at compile time (FR-139)."""
		return content_hash(self.render(style))


class StepBudget(View):
	"""The spend authority for one goal session.

	Budgets belong to SoFact, never to the harness (FR-140): a cap the producer can
	raise is not a cap. Wall clock is enforced *live*, by killing the process. Token
	spend can only be *observed* afterwards, because a limit enforced inside the
	harness's own runtime would be the harness grading its own spend — so it is
	recorded as a violation rather than silently trusted.
	"""

	max_wall_clock_seconds: float
	max_continuations: int
	max_attempts: int
	max_tokens: int | None = None

	@model_validator(mode="after")
	def _positive_caps(self) -> Self:
		if self.max_wall_clock_seconds <= 0:
			raise ValueError(f"wall-clock cap must be positive, got {self.max_wall_clock_seconds}")
		if self.max_continuations < 0:
			raise ValueError(f"continuation cap cannot be negative, got {self.max_continuations}")
		if self.max_attempts < 1:
			raise ValueError(f"attempt cap must be >= 1, got {self.max_attempts}")
		if self.max_tokens is not None and self.max_tokens <= 0:
			raise ValueError(f"token cap must be positive, got {self.max_tokens}")
		return self


class GoalStep(View):
	"""One goal session: the objective, its proof obligation, and the cap on it.

	``clause_ids`` is a *cover*, not a partition: a weak clause may be the subject of
	an operation step and again of the repair step, because repair re-works the clauses
	whose oracles cannot support the contract's ceiling.
	"""

	id: UUID7
	ordinal: int
	kind: PlanStepKind
	goal: GoalSpec
	goal_hash: str
	budget: StepBudget
	exit_evidence: tuple[NonEmptyStr, ...]
	clause_ids: tuple[UUID7, ...] = ()
	depends_on: tuple[UUID7, ...] = ()

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if self.ordinal < 0:
			raise ValueError(f"ordinal must be non-negative, got {self.ordinal}")
		if not self.exit_evidence:
			raise ValueError("a step with no exit evidence can never be known to be done")
		if self.id in self.depends_on:
			raise ValueError("a step cannot depend on itself")
		return self


class GoalPlan(View):
	"""A frozen contract compiled into ordered goal sessions (FR-136).

	Carries the hash of the contract it was compiled against, so a plan can later be
	shown to still describe the contract it claims to (FR-139) rather than silently
	dispatching sessions against an objective that has since moved.
	"""

	id: UUID7
	goal_id: UUID7
	contract_id: UUID7
	contract_hash: str
	oracle_set_hash: str
	goal_style: GoalStyle
	created_at: datetime
	steps: tuple[GoalStep, ...]

	@model_validator(mode="after")
	def _well_formed(self) -> Self:
		if not self.steps:
			raise ValueError("a plan with no steps dispatches nothing")
		ordinals = [s.ordinal for s in self.steps]
		if ordinals != sorted(ordinals):
			raise ValueError("steps must be stored in ordinal order")
		if len(set(ordinals)) != len(ordinals):
			raise ValueError("two steps share an ordinal")
		known = {s.id for s in self.steps}
		for step in self.steps:
			unknown = [dep for dep in step.depends_on if dep not in known]
			if unknown:
				raise ValueError(f"step {step.ordinal} depends on unknown step(s): {unknown}")
		return self

	def step_by_id(self, step_id: str) -> GoalStep | None:
		"""Look up a step by id."""
		return next((s for s in self.steps if s.id == step_id), None)

	@property
	def total_wall_clock_cap(self) -> float:
		"""Sum of the per-step caps.

		A ceiling on the whole plan, not a schedule: parallel steps do not shorten it,
		because the cap exists to bound spend rather than to estimate duration.
		"""
		return sum(step.budget.max_wall_clock_seconds for step in self.steps)

	@property
	def covered_clause_ids(self) -> tuple[str, ...]:
		"""Every clause id some step claims to discharge, deduplicated, in order."""
		seen: dict[str, None] = {}
		for step in self.steps:
			for clause_id in step.clause_ids:
				seen.setdefault(clause_id, None)
		return tuple(seen)

	def uncovered_clause_ids(self, contract: Contract) -> tuple[str, ...]:
		"""Clauses no step will touch.

		The honesty check on the compiler. A clause the plan does not mention would
		otherwise be dropped in silence, and a silently dropped obligation is
		indistinguishable from a satisfied one at delivery.
		"""
		covered = set(self.covered_clause_ids)
		return tuple(c.id for c in contract.clauses if c.id not in covered)

	def waves(self) -> tuple[tuple[GoalStep, ...], ...]:
		"""Dependency levels, the primitive FR-142's wave dispatch needs.

		A step may start only once every step it depends on has been *verified*, not
		merely built — that gate belongs to the scheduler, not here. This reports only
		which steps are free to run concurrently.
		"""
		remaining: list[GoalStep] = list(self.steps)
		done: set[str] = set()
		levels: list[tuple[GoalStep, ...]] = []
		while remaining:
			ready: tuple[GoalStep, ...] = tuple(
				step for step in remaining if set(step.depends_on) <= done
			)
			if not ready:
				raise ValueError("goal plan has a dependency cycle; no step can ever start")
			levels.append(ready)
			done.update(step.id for step in ready)
			remaining = [step for step in remaining if step.id not in done]
		return tuple(levels)


class IntegrationFindingKind(StrEnum):
	"""What a P7 integration check found (FR-111-116).

	Three kinds, and each is produced by a check that runs. A kind the code cannot emit
	would be an enum member nothing reaches, which reads as a capability in the type and
	is a gap in the report.
	"""

	UNDECLARED_DEPENDENCY = "undeclared_dependency"
	"""A module imports a file owned by a module absent from its ``depends_on`` (FR-113)."""

	UNBUILT_DEPENDENCY = "unbuilt_dependency"
	"""A module was built before a module it depends on had any sealed work (FR-111)."""

	UNATTRIBUTED_FILE = "unattributed_file"
	"""A module imports a file that no module's step sealed, so no module owns it (FR-114)."""

	UNDECLARED_PUBLIC_NAME = "undeclared_public_name"
	"""The build exposes a public name the module never declared (FR-112)."""

	MISSING_PUBLIC_NAME = "missing_public_name"
	"""A declared public name is absent from the build (FR-112)."""

	WRONG_ARITY = "wrong_arity"
	"""A declared function's parameter count differs from the build (FR-112)."""


class IntegrationFinding(View):
	"""One violation, attributed to the modules it implicates (FR-114).

	``modules`` is the *minimum violating set*: the modules that must be repaired for the
	finding to go away. FR-114 forbids a platform-wide rebuild in response to a local
	failure, so the set is as small as the evidence allows and is what a repair is
	scoped to.
	"""

	kind: IntegrationFindingKind
	detail: NonEmptyStr
	modules: tuple[NonEmptyStr, ...]
	evidence: tuple[NonEmptyStr, ...] = ()
	"""The concrete lines — the import statement, the path — so the finding is checkable."""


INTEGRATION_REQUIREMENTS: Final[tuple[str, ...]] = (
	"FR-111",
	"FR-112",
	"FR-113",
	"FR-114",
	"FR-115",
	"FR-116",
)
"""Every requirement §10 states, so a check can claim one and a report can see the rest.

The list is the *whole* of P7 rather than the part that is implemented. A report that
named only what it ran could not distinguish a system that integrates from a system
nothing was checked on, and the difference is exactly what a green line hides.
"""


class IntegrationCheck(View):
	"""One P7 check, its outcome, and what it did not cover (FR-111-116).

	``covered`` and ``uncovered`` are both required, because an integration report that
	says only "passed" is one an operator cannot tell from a report about a system with
	nothing to check.

	``requirements`` is which of :data:`INTEGRATION_REQUIREMENTS` this check discharges.
	:attr:`IntegrationReport.not_implemented` is the complement, so a requirement nobody
	claims shows up as unimplemented rather than as absent — the failure mode being that
	a report looks complete because it never mentioned the thing it skipped.
	"""

	name: NonEmptyStr
	passed: bool
	detail: NonEmptyStr
	requirements: tuple[NonEmptyStr, ...]
	covered: tuple[NonEmptyStr, ...] = ()
	uncovered: tuple[NonEmptyStr, ...] = ()

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this check actually carried out, which may be fewer than it claims.

		A check can claim a requirement and exercise none of it: FR-112's diff claims
		nothing when no module declared a surface, and a report that counted the claim
		would call that requirement implemented on the strength of a check that diffed
		nothing. ``passed`` is not the test — a check over no modules passes vacuously,
		which is exactly the state FR-112 is in until something declares a surface.
		"""
		if not self.covered:
			return ()
		return self.requirements


class IntegrationReport(View):
	"""The result of one integration pass over a plan's dispatched work (FR-111-116).

	Describes *one pass over one set of dispatches*, in the same sense FR-006 gives a
	verdict: a later dispatch adds evidence and a new report is rendered. ``build_order``
	is recorded because FR-111's incremental integration is only incremental if the order
	is the topological one, and a report that omitted it could not show that.
	"""

	id: UUID7
	plan_id: UUID7
	goal_id: UUID7
	contract_id: UUID7
	rendered_at: datetime
	build_order: tuple[NonEmptyStr, ...]
	modules_built: tuple[NonEmptyStr, ...]
	findings: tuple[IntegrationFinding, ...] = ()
	checks: tuple[IntegrationCheck, ...] = ()

	@model_validator(mode="after")
	def _well_formed(self) -> Self:
		if not self.build_order:
			raise ValueError("an integration report over no build order reports nothing")
		if not self.checks:
			raise ValueError("an integration report with no checks is not a report")
		return self

	@property
	def passed(self) -> bool:
		"""Whether every check passed. Findings are what fail a check, never a summary."""
		return all(check.passed for check in self.checks) and not self.findings

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of §10 that this report did not carry out (FR-112, FR-115, FR-116).

		Derived from what the checks *discharged* rather than from a hand-kept list, so a
		check that stops running takes its requirement with it into this tuple. The
		distinction between claiming and discharging is what keeps FR-112 honest: the
		conformance check always runs, but it diffs nothing until a module declares a
		machine-readable surface, and a report that counted the claim would drop FR-112
		from this tuple on the strength of a check that compared nothing. FR-115 needs a
		system model, which does not exist as a type; FR-116 needs P2 acceptance criteria
		no module satisfies, which the contract does not carry. Both are gaps no check
		claims, and this is where all of them are reported.
		"""
		discharged = {name for check in self.checks for name in check.discharged}
		return tuple(name for name in INTEGRATION_REQUIREMENTS if name not in discharged)

	@property
	def violating_modules(self) -> tuple[str, ...]:
		"""The union of every finding's minimum violating set (FR-114).

		The repair scope: exactly the modules some finding implicates, never the whole
		plan. A union is still a *minimum* set in FR-114's sense — it is derived from the
		findings rather than from the plan's membership.
		"""
		return tuple(sorted({name for finding in self.findings for name in finding.modules}))


class IntegritySubject(StrEnum):
	"""The three things FR-139 requires to be unmodified at completion."""

	CONTRACT = "contract"
	GOAL_TEXT = "goal_text"
	ORACLE_SET = "oracle_set"


class IntegrityOutcome(StrEnum):
	"""Whether a pinned hash still matches what is on disk."""

	INTACT = "intact"
	MODIFIED = "modified"
	UNKNOWN = "unknown"


class IntegrityCheck(View):
	"""One hash comparison, and the verdict on it (FR-139).

	A producer that edits its own completion criteria or its own tests has produced a
	rejected module, not a passing one. This record is how that is proved rather than
	suspected.
	"""

	subject: IntegritySubject
	label: NonEmptyStr
	expected_hash: str
	observed_hash: str | None = None
	outcome: IntegrityOutcome
	detail: NonEmptyStr


# --------------------------------------------------------------------------- #
# harness discovery and dispatch (FR-058, FR-135, FR-148, FR-153)
# --------------------------------------------------------------------------- #


class GoalEntry(StrEnum):
	"""How a goal is put into a harness session, ranked by *forcefulness* (FR-153).

	[S21] measured that goal mode is model-discretionary: the package was loaded, the
	session ran unattended, and the producer still never entered goal mode. Instructing
	the producer to enter it is therefore not a mechanism. Only ``COMMAND`` and
	``GOAL_BEARING_SESSION`` are forced; ``PROMPT`` is a request the model may decline,
	and must be reported as a capability loss (FR-144) rather than counted as goal mode.
	"""

	COMMAND = "command"
	GOAL_BEARING_SESSION = "goal_bearing_session"
	PROMPT = "prompt"
	NONE = "none"

	@property
	def is_forced(self) -> bool:
		"""Whether this mechanism *enters* goal mode rather than requesting it."""
		return self in (GoalEntry.COMMAND, GoalEntry.GOAL_BEARING_SESSION)


class HarnessCapability(StrEnum):
	"""The capability matrix FR-135 requires, one row per entry here."""

	GOAL_MODE = "goal_mode"
	NON_INTERACTIVE = "non_interactive"
	BUDGET_CONTROL = "budget_control"
	TELEMETRY = "telemetry"
	SANDBOXABLE = "sandboxable"
	CONCURRENT = "concurrent"
	BOOTSTRAP_EMPTY_REPO = "bootstrap_empty_repo"
	GOAL_SURVIVES_COMPACTION = "goal_survives_compaction"
	CONTEXT_FILES_DISABLED = "context_files_disabled"
	MODEL_RESOLVED = "model_resolved"
	STORE_ISOLATED = "store_isolated"


class ProbeOutcome(StrEnum):
	"""What a capability probe actually observed (FR-148).

	``INCONCLUSIVE`` is first-class for the same reason ``INSUFFICIENT`` is on the
	verdict side: a probe that could not decide must not be rounded to either verdict.
	Rounding it to ``ABSENT`` would condemn a harness; rounding it to ``CONFIRMED``
	would be a fabricated capability.
	"""

	CONFIRMED = "confirmed"
	ABSENT = "absent"
	INCONCLUSIVE = "inconclusive"


class CapabilityFinding(View):
	"""One capability, the action that attempted it, and what was observed."""

	capability: HarnessCapability
	outcome: ProbeOutcome
	attempted: NonEmptyStr
	observed: NonEmptyStr


class HarnessProfile(View):
	"""One harness as *discovered* at runtime, never as declared (FR-148).

	A hand-maintained matrix is stale by construction, and the harness's own help text
	is not a source either: ``dsh --help`` advertises a ``--profile tui`` that exists in
	neither shipped version [S21]. Every field here is something a probe observed.
	"""

	name: NonEmptyStr
	command: tuple[str, ...]
	probed_at: datetime
	findings: tuple[CapabilityFinding, ...]
	version: NonEmptyStr | None = None
	manifest_path: str | None = None
	model: str = ""
	"""The model this profile was probed with, empty when the spec names none.

	Recorded because a profile is a statement about one *configuration*, and the model is
	the slot most likely to be re-pointed between the probe and the dispatch. A default
	keeps ledger rows written before this field existed readable.
	"""

	def finding(self, capability: HarnessCapability) -> CapabilityFinding | None:
		"""The finding for one capability, or ``None`` if it was never probed."""
		return next((f for f in self.findings if f.capability is capability), None)

	def observation(self, capability: HarnessCapability) -> ProbeOutcome:
		"""The outcome for one capability; ``INCONCLUSIVE`` when never probed.

		Defaulting to ``INCONCLUSIVE`` rather than raising keeps the honest answer
		available at every call site: absence of a probe is not absence of a capability.
		"""
		found = self.finding(capability)
		return ProbeOutcome.INCONCLUSIVE if found is None else found.outcome

	@property
	def goal_mode(self) -> ProbeOutcome:
		"""Whether goal mode was *entered*, witnessed from the session record."""
		return self.observation(HarnessCapability.GOAL_MODE)

	@property
	def non_interactive(self) -> ProbeOutcome:
		"""Whether the harness can run without an interactive prompt (FR-145)."""
		return self.observation(HarnessCapability.NON_INTERACTIVE)

	@property
	def model_resolved(self) -> ProbeOutcome:
		"""Whether the harness's own registry accepts the configured model.

		Distinct from telemetry, which is about the record's shape: this row is about
		the *identifier*, and a harness that rejects it fails before any work starts.
		"""
		return self.observation(HarnessCapability.MODEL_RESOLVED)

	@property
	def is_usable(self) -> bool:
		"""FR-145: a harness that blocks awaiting input is unusable, full stop.

		Blocking is detected by observation, not inferred from the interface
		inventory: ``dsh`` ships no TUI yet still exposes a persistent PTY seam
		through which the agent can hang an unattended build.
		"""
		return self.non_interactive is ProbeOutcome.CONFIRMED

	@property
	def supports_goal_dispatch(self) -> bool:
		"""FR-135: goal mode and interactive-free operation are both required."""
		return self.is_usable and self.goal_mode is ProbeOutcome.CONFIRMED

	@property
	def reduced_mode_available(self) -> bool:
		"""FR-144: usable at reduced throughput when goal mode is absent.

		Not a silent fallback. The capability loss is reported on every dispatch taken
		this way, because a plan executed single-shot is not the plan that was written.
		"""
		return self.is_usable and not self.supports_goal_dispatch


class DispatchMode(StrEnum):
	"""How a step was dispatched, including FR-144's reported degradation."""

	GOAL = "goal"
	SINGLE_SHOT = "single_shot"


class StepOutcome(StrEnum):
	"""What the *process* did, kept separate from what the producer claimed (FR-138).

	``BUDGET_EXHAUSTED`` is not a failure of the work — it is SoFact exercising the
	authority FR-140 reserves to it. ``NOT_DISPATCHED`` exists so that a step skipped
	for want of a usable harness is a recorded fact rather than a missing row.
	"""

	COMPLETED = "completed"
	FAILED = "failed"
	BUDGET_EXHAUSTED = "budget_exhausted"
	NOT_DISPATCHED = "not_dispatched"


class ResearchMode(StrEnum):
	"""Which research engine to ask for. Depth is the producer's choice to honour."""

	DEEP = "deep"
	SUPER = "super"


class ResearchRecord(View):
	"""One research dispatch (FR-167) and what it left behind.

	The record keeps the report a **fact about an artefact**, not a verdict about
	research: ``report_chars`` and ``source_urls`` are measurements, and an empty
	``source_urls`` means *none were recorded*, never *none exist* (NFR-024). A
	truncated research loop and a completed one look different only in these numbers,
	which is why they are recorded at all.
	"""

	id: UUID7
	goal_id: UUID7
	query: str
	harness: str
	mode: ResearchMode
	argv: tuple[str, ...]
	workspace: str
	started_at: datetime
	ended_at: datetime | None = None
	wall_clock_seconds: float | None = None
	outcome: StepOutcome = StepOutcome.NOT_DISPATCHED
	exit_code: int | None = None
	tokens_observed: int | None = None
	session_path: str | None = None
	stderr_tail: str | None = None
	report_path: str | None = None
	report_chars: int = 0
	searches_observed: int | None = None
	source_urls: tuple[str, ...] = ()
	note: str | None = None


class ModuleCheckout(View):
	"""The branch a plan step's work sits on (FR-100).

	Recorded on the dispatch so "build never occurs in place" is a fact in the log
	rather than a claim in a goal text. ``branch`` is the branch the session ran on;
	``base_branch`` is what it was switched from, which is what a later integration
	would need and what makes an unexpected switch visible.

	``base_branch`` is ``None`` when the workspace had no branch to leave — a fresh
	repository with an unborn HEAD — which is a real state and not an error.

	``sealed_commit`` is what makes the branch a *boundary* rather than a name. A branch
	with no commit is not a ref at all, so a step that never commits leaves the next step
	branching from nothing: the two become unrelated histories sharing one working tree,
	and the first step's files stage cleanly on the second step's branch.
	"""

	branch: NonEmptyStr
	step_ordinal: int
	module: str | None = None
	"""The module this step's work belongs to, when one owns it (FR-100).

	``None`` for a step no single module owns — a bootstrap step covers no clause, and a
	step spanning two modules belongs to neither. ``branch`` falls back to the step's
	ordinal and kind in that case, so the record says which happened rather than leaving
	a reader to infer it from the branch name.
	"""
	created_repository: bool = False
	created_branch: bool = False
	base_branch: str | None = None
	sealed_commit: str | None = None
	"""The commit SoFact created to seal this step's work, or ``None`` if there was none.

	``None`` is not a failure. A session that changed nothing, and a session whose
	producer committed its own work, both leave SoFact with nothing to seal; the two are
	told apart by ``head_commit``.
	"""
	sealed_paths: int = 0
	sealed_files: tuple[str, ...] = ()
	"""The paths the seal committed, relative to the workspace root.

	The *names*, not only the count, because FR-113's "no module reaches another module's
	internals" is checked by import analysis over the files a module actually produced, and
	a count cannot be analysed. This is the only place that attribution exists: the
	producer reports nothing about what it wrote, and the seal is where the factory sees it.

	Paths, not commits, because the branches are cumulative — a later module's branch
	contains every earlier module's files — so a module's own files are the ones *its* step
	sealed, which only this field records.
	"""
	head_commit: str | None = None
	"""The branch tip after the session, whoever created it.

	Separate from ``sealed_commit`` on purpose: a producer that commits its own work
	leaves ``sealed_commit`` null with a real ``head_commit``, which is a different fact
	from a step that did nothing at all.
	"""

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if self.step_ordinal < 0:
			raise ValueError(f"step_ordinal must be non-negative, got {self.step_ordinal}")
		if self.created_branch and self.base_branch == self.branch:
			raise ValueError("a branch cannot be created on top of itself")
		if self.sealed_paths < 0:
			raise ValueError(f"sealed_paths must be non-negative, got {self.sealed_paths}")
		if self.sealed_paths != len(self.sealed_files):
			raise ValueError(
				f"sealed_paths is the count of sealed_files, got {self.sealed_paths} "
				f"for {len(self.sealed_files)} path(s)"
			)
		if (self.sealed_commit is None) != (self.sealed_paths == 0):
			raise ValueError(
				"a seal names a commit exactly when it names paths: "
				f"commit={self.sealed_commit!r} paths={self.sealed_paths}"
			)
		return self


class DispatchRecord(View):
	"""What one attempt at one plan step actually did.

	Two signals live here and must never be merged (FR-138). ``outcome`` is what the
	*process* did — it exited, it crashed, it was killed for exceeding its budget.
	``declared_complete`` is what the *producer* said about its own work, and it is a
	claim, not a finding. The clauses this step covered are judged somewhere else
	entirely, by :func:`sofact.verification.verify`, from evidence SoFact produced
	itself. Harness-reported evidence is untrusted input and is deliberately never
	recorded as :class:`Evidence`.
	"""

	id: UUID7
	plan_id: UUID7
	goal_id: UUID7
	step_id: UUID7
	step_ordinal: int
	harness: NonEmptyStr
	mode: DispatchMode
	outcome: StepOutcome
	argv: tuple[str, ...]
	workspace: str
	budget: StepBudget
	started_at: datetime
	ended_at: datetime
	wall_clock_seconds: float
	goal_hash: str
	contract_hash: str
	declared_complete: bool = False
	declaration_note: NonEmptyStr | None = None
	note: NonEmptyStr | None = None
	exit_code: int | None = None
	tokens_observed: int | None = None
	continuations_observed: int | None = None
	goal_entry_observed: GoalEntry | None = None
	budget_violations: tuple[str, ...] = ()
	session_path: str | None = None
	stderr_tail: str | None = None
	checkout: ModuleCheckout | None = None
	"""The branch this session ran on (FR-100), or ``None`` when none was established.

	``None`` on a *dispatched* record would mean the work happened in place, which
	FR-100 forbids — so a dispatch that could not establish a branch is refused rather
	than recorded here with a null. The field is optional because the record type also
	covers the refusals, and a refusal has no branch to report.
	"""

	@property
	def is_within_budget(self) -> bool:
		"""True when no cap was exceeded. A *fact about spend*, not a verdict."""
		return not self.budget_violations

	@property
	def capability_loss(self) -> str | None:
		"""The downgrade this dispatch accepted, or ``None`` if it ran as planned.

		FR-144 requires the loss to be *reported*. Single-shot execution of a plan step
		is not a lesser kind of goal — it is a different kind of session, and the record
		says so rather than letting the plan appear to have been honoured.
		"""
		if self.mode is DispatchMode.GOAL:
			return None
		return "goal mode unavailable; step ran single-shot with no continuation (FR-144)"


class RepairOutcome(StrEnum):
	"""How one attempt at repairing a refuted clause ended.

	``ESCALATED`` is the one that must exist. FR-101 forbids an unbounded retry loop,
	and the honest alternative to retrying forever is not retrying never — it is
	retrying under a bound and *saying so* when the bound is reached. A loop that
	stopped silently would make "ran out of attempts" indistinguishable from "nothing
	to do", which is the same defect as an unrun oracle reading as a satisfied one.
	"""

	REPAIRED = "repaired"
	"""A later check found every clause the attempt covered no longer refuted."""

	STILL_REFUTED = "still_refuted"
	"""The attempt ran and completed, and a later check still refutes the clause."""

	NOT_COMPLETED = "not_completed"
	"""The repair session itself did not complete, so nothing was attempted."""

	EXHAUSTED = "exhausted"
	"""The attempt budget ran out with the clause still refuted (FR-101's bound)."""


class RepairAttempt(View):
	"""One pass of the repair loop: a refuted clause, an authored goal, and its result.

	Written as its own ledger row rather than folded into the dispatch it produced,
	because the *reason* a goal exists is not recoverable from the dispatch: a repair
	session and a plan-authored session look identical on the wire, and a reader of the
	log has to be able to tell "the producer was asked to fix a refutation" from "the
	producer was asked to implement a clause". It also carries the diagnosis the goal
	was authored from, which is the only place the refutation's own words survive.

	``attempt`` is 1-based and counts attempts at *this clause*, so a clause refuted,
	repaired, refuted again is legible as two rows rather than one clause with two
	unrelated dispatches.

	Two plan ids, because a repair step lives in a *revision* of the plan the operator
	dispatched and both are worth asking about. ``plan_id`` is the origin — the plan
	:meth:`~sofact.service.FactoryService.repair_plan` was called with — so
	"what repairs ran for this plan?" has an answer that does not require walking the
	revision chain. ``revision_id`` is the plan the repair step actually belongs to,
	which is what a reader needs to look the step up. Collapsing them would make the
	repair invisible to the operator's own plan id.
	"""

	id: UUID7
	plan_id: UUID7
	revision_id: UUID7
	step_id: UUID7
	clause_ids: tuple[UUID7, ...]
	attempt: int
	diagnosis: NonEmptyStr
	goal_hash: str
	outcome: RepairOutcome
	dispatch_id: UUID7 | None = None
	at: datetime

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if self.attempt < 1:
			raise ValueError(f"attempt must be 1-based, got {self.attempt}")
		if not self.clause_ids:
			raise ValueError("a repair attempt that repairs no clause repairs nothing")
		if self.outcome is RepairOutcome.REPAIRED and self.dispatch_id is None:
			raise ValueError("a repair cannot be repaired without a dispatch that did it")
		return self


class DeclarationPrecision(View):
	"""Goal-declaration precision (§20.4, FR-143, FR-147).

	Of the dispatches where the producer declared completion, the fraction whose
	covered clauses were afterwards verified clean. A producer with low precision is
	not a defective module: it is a defective *worker*, and this is the instrument that
	says to replace it.
	"""

	declarations: int
	corroborated: int
	at: datetime

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if self.declarations < 0 or self.corroborated < 0:
			raise ValueError("counts cannot be negative")
		if self.corroborated > self.declarations:
			raise ValueError(
				f"{self.corroborated} corroborated declarations out of {self.declarations} "
				"is impossible",
			)
		return self

	@property
	def precision(self) -> float | None:
		"""``None`` when nothing was declared — deliberately *not* ``0.0``.

		A harness that exposes no completion signal is unmeasured, not wrong. Reporting
		it as zero would be inventing a measurement in the accusing direction, which is
		the same defect as inventing one in the exonerating direction (NFR-024).
		"""
		if self.declarations == 0:
			return None
		return self.corroborated / self.declarations


# --------------------------------------------------------------------------- #
# ledger
# --------------------------------------------------------------------------- #


class LedgerKind(StrEnum):
	"""Event types. The log is the only mutable thing in the system."""

	GOAL_CREATED = "goal.created"
	ANSWER_RECORDED = "answer.recorded"
	DRAFT_CREATED = "draft.created"
	CONTRACT_CREATED = "contract.created"
	EVIDENCE_RECORDED = "evidence.recorded"
	VERDICT_RENDERED = "verdict.rendered"
	CLAIM_DECLARED = "claim.declared"
	ADVISOR_NOTE = "advisor.note"
	PLAN_COMPILED = "plan.compiled"
	CAPABILITY_PROBED = "capability.probed"
	STEP_DISPATCHED = "step.dispatched"
	INTEGRITY_CHECKED = "integrity.checked"
	INTEGRATION_CHECKED = "integration.checked"
	VERDICT_REUSED = "verdict.reused"
	RESEARCH_RUN = "research.run"
	REPAIR_ATTEMPTED = "repair.attempted"
	DECOMPOSITION_PROPOSED = "decomposition.proposed"
	DECOMPOSITION_GATED = "decomposition.gated"
	SPECIFICATION_PROPOSED = "specification.proposed"
	SPECIFICATION_GATED = "specification.gated"
	PHASE_ADVANCED = "phase.advanced"


class LedgerEntry(View):
	"""One append-only, hash-chained event.

	``entry_hash`` covers ``prev_hash``, so altering any entry invalidates every
	entry after it. That is what makes the log tamper-*evident* rather than merely
	append-only.
	"""

	index: int
	at: datetime
	kind: LedgerKind
	payload: dict[str, Any]
	prev_hash: str
	entry_hash: str

	def computed_hash(self) -> str:
		"""Recompute this entry's hash from its contents."""
		return content_hash(
			{
				"index": self.index,
				"at": self.at.isoformat(),
				"kind": self.kind.value,
				"payload": self.payload,
				"prev_hash": self.prev_hash,
			},
		)

	@classmethod
	def create(
		cls,
		*,
		index: int,
		kind: LedgerKind,
		payload: dict[str, Any],
		prev_hash: str,
		at: datetime | None = None,
	) -> Self:
		"""Build the next entry, chaining it to ``prev_hash``."""
		assert index >= 0, f"index must be non-negative, got {index}"
		timestamp = at or now()
		draft = cls(
			index=index,
			at=timestamp,
			kind=kind,
			payload=payload,
			prev_hash=prev_hash,
			entry_hash="",
		)
		return draft.model_copy(update={"entry_hash": draft.computed_hash()})


class ChainStatus(View):
	"""Result of re-checking the ledger's hash chain."""

	ok: bool
	length: int
	broken_at: int | None = None
	reason: str | None = None


class Advice(View):
	"""An advisory opinion from the model, plus why it is missing if it is missing.

	Advisory output is recorded in the ledger but is never an input to a gate or a
	verdict. Modelling *failure* explicitly rather than returning ``None`` keeps the
	difference between "the advisor had nothing to add" and "the advisor was
	unreachable" from being silently collapsed.
	"""

	dimension: ElicitationDimension
	text: str | None = None
	unavailable: str | None = None

	@model_validator(mode="after")
	def _exactly_one(self) -> Self:
		if (self.text is None) == (self.unavailable is None):
			raise ValueError("advice must be either text or a reason it is unavailable")
		return self


class ProjectState(View):
	"""All state, derived by folding the ledger. Never edited directly."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
		frozen=True,
	)

	goals: tuple[Goal, ...] = ()
	answers: tuple[ElicitationAnswer, ...] = ()
	drafts: tuple[SpecificationDraft, ...] = ()
	contracts: tuple[Contract, ...] = ()
	evidence: tuple[Evidence, ...] = ()
	reports: tuple[VerificationReport, ...] = ()
	plans: tuple[GoalPlan, ...] = ()
	specifications: tuple[Specification, ...] = ()
	specification_gates: tuple[SpecificationGate, ...] = ()
	decompositions: tuple[Decomposition, ...] = ()
	gates: tuple[DecompositionGate, ...] = ()
	dispatches: tuple[DispatchRecord, ...] = ()
	profiles: tuple[HarnessProfile, ...] = ()
	integrity: tuple[IntegrityCheck, ...] = ()
	integrations: tuple[IntegrationReport, ...] = ()
	claims: tuple[CompletionClaim, ...] = ()
	research: tuple[ResearchRecord, ...] = ()
	repairs: tuple[RepairAttempt, ...] = ()
	notes: tuple[str, ...] = ()
	phases: tuple[PhaseAdvance, ...] = ()

	@property
	def current_phase(self) -> Phase:
		"""The phase the pipeline is in, derived from the transitions (FR-060).

		The last transition *that completed* names the phase whose work is next, so a
		completed P1 means the pipeline is in P2. With no transitions at all it is P0,
		which is the honest answer for a goal nobody has started on: a fresh log has
		done none of the pipeline, and ``Phase.ELICIT`` is where the first work goes.

		A phase left ``AWAITING_GATE`` is *not* skipped past. It reports itself as the
		current phase, because FR-061 makes the gate a hard stop and a machine that
		reported the next phase as current while a gate was open would be describing
		work it is forbidden to do.
		"""
		if not self.phases:
			return Phase.ELICIT
		latest = self.phases[-1]
		if latest.status is PhaseStatus.COMPLETE:
			index = PHASE_SEQUENCE.index(latest.phase)
			return PHASE_SEQUENCE[index + 1] if index + 1 < len(PHASE_SEQUENCE) else latest.phase
		return latest.phase

	def phase_status(self, phase: Phase) -> PhaseStatus:
		"""Where ``phase`` stands. ``PENDING`` for a phase no transition has named."""
		matching = [p for p in self.phases if p.phase is phase]
		return matching[-1].status if matching else PhaseStatus.PENDING

	def phase_advance(self, phase: Phase) -> PhaseAdvance | None:
		"""The most recent transition recorded for ``phase``, if any."""
		matching = [p for p in self.phases if p.phase is phase]
		return matching[-1] if matching else None

	@property
	def open_gate(self) -> PhaseAdvance | None:
		"""The gate the pipeline is stopped at, or ``None`` if it is not stopped.

		This is FR-061 as a query: a caller that wants to know whether machine work may
		proceed asks this, rather than comparing phases and re-deriving the gate table.
		"""
		if not self.phases:
			return None
		latest = self.phases[-1]
		return latest if latest.is_blocking else None

	def goal(self, goal_id: str) -> Goal | None:
		"""Look up a goal by id."""
		return next((g for g in self.goals if g.id == goal_id), None)

	def latest_goal(self) -> Goal | None:
		"""Most recently created goal, or ``None`` on an empty log."""
		return self.goals[-1] if self.goals else None

	def answers_for(self, goal_id: str) -> tuple[ElicitationAnswer, ...]:
		"""All answers recorded against a goal, in log order."""
		return tuple(a for a in self.answers if a.goal_id == goal_id)

	def latest_contract(self, goal_id: str) -> Contract | None:
		"""Most recent contract for a goal, if one exists."""
		matching = [c for c in self.contracts if c.goal_id == goal_id]
		return matching[-1] if matching else None

	def contract(self, contract_id: str) -> Contract | None:
		"""Look up a contract by id."""
		return next((c for c in self.contracts if c.id == contract_id), None)

	def evidence_for(self, clause_id: str) -> tuple[Evidence, ...]:
		"""Every observation recorded against a clause, in log order."""
		return tuple(e for e in self.evidence if e.clause_id == clause_id)

	def latest_report(self, contract_id: str) -> VerificationReport | None:
		"""Most recent verdict rendered for a contract, if any."""
		matching = [r for r in self.reports if r.contract_id == contract_id]
		return matching[-1] if matching else None

	def decomposition(self, decomposition_id: str) -> Decomposition | None:
		"""Look up a proposed decomposition by id."""
		return next((d for d in self.decompositions if d.id == decomposition_id), None)

	def latest_decomposition(self, contract_id: str) -> Decomposition | None:
		"""Most recent proposal for a contract, if any.

		FR-094 makes revision normal, so "the decomposition" is always the latest one and
		never a unique artefact — a gate approval has to name which revision it approved.
		"""
		matching = [d for d in self.decompositions if d.contract_id == contract_id]
		return matching[-1] if matching else None

	def specification(self, specification_id: str) -> Specification | None:
		"""Look up a proposed specification by id."""
		return next((s for s in self.specifications if s.id == specification_id), None)

	def latest_specification(self, contract_id: str) -> Specification | None:
		"""Most recent specification proposed for a contract, if any (FR-094)."""
		matching = [s for s in self.specifications if s.contract_id == contract_id]
		return matching[-1] if matching else None

	def latest_specification_gate(self, specification_id: str) -> SpecificationGate | None:
		"""Most recent gate result for a specification, if it has been gated."""
		matching = [g for g in self.specification_gates if g.specification_id == specification_id]
		return matching[-1] if matching else None

	def latest_gate(self, decomposition_id: str) -> DecompositionGate | None:
		"""Most recent gate result for a decomposition, if it has been gated."""
		matching = [g for g in self.gates if g.decomposition_id == decomposition_id]
		return matching[-1] if matching else None

	def plan(self, plan_id: str) -> GoalPlan | None:
		"""Look up a goal plan by id."""
		return next((p for p in self.plans if p.id == plan_id), None)

	def latest_plan(self, contract_id: str) -> GoalPlan | None:
		"""Most recent plan compiled from a contract, if any."""
		matching = [p for p in self.plans if p.contract_id == contract_id]
		return matching[-1] if matching else None

	def profile(self, name: str) -> HarnessProfile | None:
		"""Most recent probe of a harness, if it has ever been probed."""
		matching = [p for p in self.profiles if p.name == name]
		return matching[-1] if matching else None

	def dispatch(self, dispatch_id: str) -> DispatchRecord | None:
		"""Look up a dispatch attempt by id."""
		return next((d for d in self.dispatches if d.id == dispatch_id), None)

	def dispatches_for(self, plan_id: str) -> tuple[DispatchRecord, ...]:
		"""Every dispatch attempt made for a plan, in log order."""
		return tuple(d for d in self.dispatches if d.plan_id == plan_id)

	def dispatches_for_step(self, step_id: str) -> tuple[DispatchRecord, ...]:
		"""Every attempt at one step, in log order. Retries appear as separate rows."""
		return tuple(d for d in self.dispatches if d.step_id == step_id)

	def repairs_for_plan(self, plan_id: str) -> tuple[RepairAttempt, ...]:
		"""Every repair attempt made against a plan, in log order."""
		return tuple(r for r in self.repairs if r.plan_id == plan_id)

	def integrations_for(self, plan_id: str) -> tuple[IntegrationReport, ...]:
		"""Every integration pass over a plan, in log order."""
		return tuple(r for r in self.integrations if r.plan_id == plan_id)

	def latest_integration(self, plan_id: str) -> IntegrationReport | None:
		"""Most recent integration report for a plan, if one was rendered."""
		matching = [r for r in self.integrations if r.plan_id == plan_id]
		return matching[-1] if matching else None

	def attempts_at_clause(self, clause_id: str) -> tuple[RepairAttempt, ...]:
		"""Every repair attempt at one clause, in log order.

		The bound FR-101 requires is a count of *attempts*, and a count that cannot be
		read off the log is not a bound. Counting here rather than in a scheduler keeps
		the number derivable from what was written down.
		"""
		return tuple(r for r in self.repairs if clause_id in r.clause_ids)

	def integrity_for(self, plan_id: str) -> tuple[IntegrityCheck, ...]:
		"""Integrity checks recorded against a plan, in log order."""
		return tuple(c for c in self.integrity if c.label.startswith(plan_id))
