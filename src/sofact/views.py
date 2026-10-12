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
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from sofact._uuid7 import uuid7str

__all__ = [
	"ORACLE_RANK",
	"AutonomyLevel",
	"CapabilityFinding",
	"Clause",
	"ClauseKind",
	"ClauseStem",
	"ClauseVerdict",
	"CompletionClaim",
	"Contract",
	"DeclarationPrecision",
	"DimensionStatus",
	"DispatchMode",
	"DispatchRecord",
	"ElicitationAnswer",
	"ElicitationDimension",
	"Evidence",
	"EvidenceKind",
	"Goal",
	"GoalEntry",
	"GoalPlan",
	"GoalSpec",
	"GoalStep",
	"GoalStyle",
	"HarnessCapability",
	"HarnessProfile",
	"IntegrityCheck",
	"IntegrityOutcome",
	"IntegritySubject",
	"LedgerEntry",
	"LedgerKind",
	"OracleClass",
	"OracleDeclaration",
	"PlanStepKind",
	"ProbeOutcome",
	"ProjectState",
	"Readiness",
	"RepairAttempt",
	"RepairOutcome",
	"SpecificationDraft",
	"StepBudget",
	"StepOutcome",
	"VerdictOutcome",
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
"""Rank 1 is strongest. Ranks 1–2 are mandatory above autonomy L2."""

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
	VERDICT_REUSED = "verdict.reused"
	RESEARCH_RUN = "research.run"
	REPAIR_ATTEMPTED = "repair.attempted"


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
	dispatches: tuple[DispatchRecord, ...] = ()
	profiles: tuple[HarnessProfile, ...] = ()
	integrity: tuple[IntegrityCheck, ...] = ()
	claims: tuple[CompletionClaim, ...] = ()
	research: tuple[ResearchRecord, ...] = ()
	repairs: tuple[RepairAttempt, ...] = ()
	notes: tuple[str, ...] = ()

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
