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
from datetime import UTC, date, datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Any, ClassVar, Final, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from sofact._uuid7 import uuid7str

__all__ = [
	"HIGHEST_GRANTABLE",
	"INTEGRATION_REQUIREMENTS",
	"MODE_G_CEILING",
	"MODULE_CLASS_CEILING",
	"ORACLE_RANK",
	"TOPOLOGY_ISOLATION",
	"TOPOLOGY_MODIFIER",
	"Assumption",
	"AutonomyLevel",
	"CapabilityFinding",
	"Claim",
	"ClaimKind",
	"Clause",
	"ClauseClassification",
	"ClauseKind",
	"ClauseStem",
	"ClauseVerdict",
	"CompletionClaim",
	"Contract",
	"Contradiction",
	"Cut",
	"DeclarationPrecision",
	"Decomposition",
	"DecompositionGate",
	"DeliveryArtifact",
	"DeliveryArtifactKind",
	"DeliveryEnvelope",
	"DeliveryGate",
	"DeliveryReport",
	"DeployRecord",
	"DeploymentTopology",
	"DimensionBound",
	"DimensionStatus",
	"DispatchMode",
	"DispatchRecord",
	"ElicitationAnswer",
	"ElicitationDimension",
	"EnvelopeActuals",
	"EnvelopeDimension",
	"EnvelopeMeasurement",
	"Evidence",
	"EvidenceKind",
	"GateCheck",
	"GateCost",
	"Goal",
	"GoalEntry",
	"GoalPlan",
	"GoalSpec",
	"GoalStep",
	"GoalStyle",
	"Handover",
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
	"MaintenanceLane",
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
	"ResearchAllowance",
	"ResearchBudget",
	"ResearchClassification",
	"ResearchMode",
	"ResearchRecord",
	"ResearchVerdict",
	"Source",
	"SourceLedger",
	"SourcePosture",
	"Specification",
	"SpecificationDraft",
	"SpecificationGate",
	"StepBudget",
	"StepOutcome",
	"SystemCriterion",
	"SystemEntity",
	"SystemInvariant",
	"SystemModel",
	"SystemRelationship",
	"TraceLink",
	"UnverifiedClause",
	"ValueHypothesis",
	"VerdictOutcome",
	"VerificationMethod",
	"VerificationReport",
	"VerificationStatus",
	"VerifiedClause",
	"canonical_json",
	"ceiling_for_rank",
	"content_hash",
	"now",
	"topology_ceiling",
	"topology_refusal",
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


MODE_G_CEILING: Final[AutonomyLevel] = AutonomyLevel.L2
"""The end-to-end autonomy of a Mode G delivery, and it is a cap (FR-123).

FR-123's argument is that P2, P3 and P8 are human gates, so a delivery assembled through
them cannot be reported as L3 or L4 no matter how strong the oracles are. Individual
modules may run at L4 internally — that is what :func:`ceiling_for_rank` and
:data:`MODULE_CLASS_CEILING` compute — and the *delivery* is L2. §2.3's honest headline
is the same sentence: autonomous module construction inside a human-validated
architecture.

A constant rather than a lookup, because the pipeline this build implements is Mode G's
(§1.2: a goal and no codebase, P0–P9) and every report this build can render is a Mode G
report. A mode-keyed table with a default would be a cap that fails open on a mode nobody
has written yet, which is the one failure a cap may not have; when a Mode M pipeline
exists this becomes a lookup and the type will force the change.
"""


# --------------------------------------------------------------------------- #
# §5.4 — deployment topology, and the ceiling it modifies (FR-019, FR-030, FR-031, FR-042)
# --------------------------------------------------------------------------- #


class DeploymentTopology(StrEnum):
	"""Where the factory is running, as §5.4's four deployments (FR-124).

	§5.4's principle is that *the same lane has different admissible ceilings on
	different hardware*, because what bounds blast radius is the isolation the environment
	actually provides. So the topology is not an operational detail; it is an input to the
	autonomy computation, which is why FR-030 requires it reported in every oracle report
	and attached to every change.

	The four are named rather than numbered because ``T1`` in a report is a name a reader
	has to look up. ``value`` is still §5.4's identifier, so a report and the spec agree
	on what to call it.

	``T1`` is the *default* rather than ``T2``, and that direction is deliberate: T1 is
	the degraded configuration (no isolation boundary at all), so a factory that has not
	been told where it is running claims the *lower* ceiling. Defaulting to the product
	target would be a ceiling that fails open on an unconfigured deployment, which is the
	one failure a ceiling may not have — the same argument ADR-0041 makes about FR-123's
	cap being a constant rather than a mode-keyed lookup.
	"""

	T1 = "T1"
	T2 = "T2"
	T3 = "T3"
	T4 = "T4"


TOPOLOGY_ISOLATION: dict[DeploymentTopology, str] = {
	DeploymentTopology.T1: (
		"none: shared filesystem, no container boundary, producer and evaluator on one host"
	),
	DeploymentTopology.T2: (
		"container per lane, VM boundary, egress denied by default, git-backed"
	),
	DeploymentTopology.T3: "T2's boundary with no egress at all; customer-hosted, local models",
	DeploymentTopology.T4: "T2's boundary, with the producer and the evaluator on separate hosts",
}
"""§5.4's isolation column, so a report can state what it is *relying* on (FR-030).

FR-030 requires the isolation guarantees reported beside the modifier, and the pairing is
the requirement's substance: a reader who is told "T2, baseline" and not told what T2
guarantees has been given a number to trust rather than a fact to check. R2 in the old
spec's risk table is exactly this failure — "autonomy depends on isolation (FR-019) that
is asserted but never verified".
"""

TOPOLOGY_MODIFIER: dict[DeploymentTopology, int] = {
	DeploymentTopology.T1: -1,
	DeploymentTopology.T2: 0,
	DeploymentTopology.T3: 0,
	DeploymentTopology.T4: 0,
}
"""§5.4's ceiling modifier, in autonomy levels, applied to the modules' number.

An integer rather than a table of resulting levels, because the modifier is what §5.4
states and a pre-applied table would have to be rewritten every time
:data:`MODULE_CLASS_CEILING` or :func:`ceiling_for_rank` moved. It is applied to
:func:`sofact.delivery.module_autonomy` — the modules' number — and *not* to the
delivery's, because the delivery is already capped at L2 by FR-123 and lowering a cap
changes nothing about it.

T4 is ``0`` and is not therefore a no-op. §5.4's "+0, but unlocks L4 for lanes whose blast
bound previously failed" is a change to *admissibility*, not to the level, and the blast
bound it unlocks is not a fact this factory holds: §5.2's FR-027 requires a lane's file
scope be declared and enforced by permission, and nothing in the log declares one. So T4
is reported as baseline with its isolation stated, and the unlock is named as the thing
it is rather than applied as a level this code cannot justify. Claiming a *higher* number
for T4 would be the direction a ceiling must never move on an unmeasured premise.
"""


def topology_ceiling(
	level: AutonomyLevel,
	topology: DeploymentTopology,
) -> AutonomyLevel:
	"""``level`` lowered by the topology's modifier, never below L0 (FR-019, FR-124).

	The modifier is applied to the *modules'* number and the delivery's cap is applied
	after, so T1 lowers what the modules sustain (L4 becomes L3, which is §5.4's own
	worked example) and FR-123's L2 cap is untouched by it.

	The clamp at L0 is not decoration: §5.4's T1 modifier is one level and the ladder's
	floor is L0, so a module class already at L1 would otherwise compute L0-1 = -1, which
	:class:`AutonomyLevel` cannot represent. A clamp is the right shape here rather than a
	refusal, because the *refusal* FR-031 asks for is about a specific case — a lane that
	would be L4 in T2 — and it is raised by :func:`topology_refusal`, which knows the
	level the lane would have had.

	The assertion is the guard :data:`HIGHEST_GRANTABLE` exists for: a modifier that
	*raised* a level would be a deployment claiming autonomy its isolation does not
	support, which is the failure R2 names. It is an assertion rather than a min() because
	a silent cap on a raising modifier would leave the table saying one thing and the
	computation another.
	"""
	modified = int(level) + TOPOLOGY_MODIFIER[topology]
	assert modified <= int(HIGHEST_GRANTABLE), (
		f"{topology.value}'s modifier of {TOPOLOGY_MODIFIER[topology]:+d} would raise "
		f"{level.name} to {modified}, above the {HIGHEST_GRANTABLE.name} the ladder "
		"offers at all (FR-019, §1.5)"
	)
	return AutonomyLevel(max(int(AutonomyLevel.L0), modified))


def topology_refusal(
	level: AutonomyLevel,
	topology: DeploymentTopology,
) -> str | None:
	"""Why a level is refused outright at this topology, or ``None`` (FR-031).

	FR-031 is precise and it is a *refusal*, not a downgrade: "a lane that would be L4 in
	T2 must be **refused** at L1 in T1 rather than silently downgraded, unless an explicit
	operator override is recorded."

	The distinction matters because a silent downgrade is indistinguishable, in the log,
	from work that was never L4-eligible. A lane that runs at L3 in T1 either because T1
	lowered it or because its oracles are weak is two different facts about the world, and
	only the first is a deployment limitation an operator could lift by moving to T2. So
	the refusal is a sentence naming both numbers and the topology that separates them.

	It states the *refusal* and not the remedy. The remedy — record an override, or move
	the deployment — depends on state this function cannot see: whether an override was
	already recorded. A sentence that told an operator to record one, printed over a
	refusal that was already accepted, is an instruction to redo something done, and a
	check that reads that way is one a reader learns to skim. The gate in
	:mod:`sofact.delivery` holds the remedy because it holds the override.

	T1 is the only topology whose modifier is negative and therefore the only one that can
	refuse: at T2/T3/T4 the modifier is zero, so the level T2 admits is the level
	admitted, and returning a refusal there would refuse the baseline case.
	"""
	if TOPOLOGY_MODIFIER[topology] >= 0:
		return None
	if level < AutonomyLevel.L4:
		return None
	lowered = topology_ceiling(level, topology)
	return (
		f"{level.name} is not admissible at {topology.value}: §5.4's modifier is "
		f"{TOPOLOGY_MODIFIER[topology]:+d} level, which would run this at {lowered.name}, "
		"and FR-031 refuses a silent downgrade — a lane lowered by its deployment and a "
		"lane whose oracles never supported the level are two different facts, and only "
		"the first is lifted by moving to T2"
	)


HIGHEST_GRANTABLE: Final[AutonomyLevel] = AutonomyLevel.L4
"""The highest level any topology may grant, and it is not L5 (§1.5, FR-157).

L5 is representable in :class:`AutonomyLevel` and unreachable through
:func:`ceiling_for_rank`, which is the same guard one level up: the spec declines to
offer a dark factory. Named here so :func:`topology_ceiling` can assert that no modifier
raises a number past what the ladder offers at all, rather than only that it does not
raise it past L5 — a modifier is data, and data can be edited.
"""


# --------------------------------------------------------------------------- #
# §1.3 — the delivery envelope (FR-057, NFR-025)
# --------------------------------------------------------------------------- #


class EnvelopeDimension(StrEnum):
	"""The eight dimensions §1.3 bounds, named so a measurement can name one back.

	An enum rather than a string key because FR-057 requires the refusal to say *which*
	dimension was exceeded, and a dimension named by a free string is one a report can
	misspell while still reading as complete. §1.3's table has eight rows and this enum
	has eight members; a dimension added to one and not the other is a delivery that
	stops reporting something the spec bounds.
	"""

	SYSTEMS = "systems"
	MODULES = "modules"
	DELIVERED_LOC = "delivered_loc"
	EXTERNAL_INTEGRATIONS = "external_integrations"
	HUMAN_GATES = "human_gates"
	HUMAN_MINUTES = "human_minutes"
	WALL_CLOCK_DAYS = "wall_clock_days"
	VALUE_HYPOTHESIS = "value_hypothesis"


class DimensionBound(View):
	"""One dimension's permitted range, and the unit it is stated in (§1.3).

	``minimum`` and ``maximum`` are separate fields rather than one range object because
	they are not the same kind of claim. §1.3 says its numbers are "**targets, not
	measurements**", and the two ends then behave differently: a delivery *above* a
	ceiling is the over-scoped goal FR-057 refuses, while a delivery *below* a floor is a
	small project, which is a legitimate thing to build and not a defect. Keeping them
	apart is what lets the gate refuse one and merely report the other.
	"""

	unit: NonEmptyStr
	minimum: float | None = None
	maximum: float | None = None

	@model_validator(mode="after")
	def _a_bound_bounds_something(self) -> Self:
		if self.minimum is None and self.maximum is None:
			raise ValueError(
				f"the {self.unit} bound has neither a floor nor a ceiling, so it admits "
				"every value and bounds nothing — an unbounded dimension belongs out of "
				"the envelope, not in it with two empty fields (NFR-025)"
			)
		if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
			raise ValueError(
				f"the {self.unit} bound has a floor of {self.minimum:g} above its ceiling "
				f"of {self.maximum:g}, so no delivery could ever be inside it"
			)
		return self

	def admits(self, value: float) -> bool:
		"""Whether ``value`` is inside the bound. Floors and ceilings both apply."""
		if self.minimum is not None and value < self.minimum:
			return False
		return not (self.maximum is not None and value > self.maximum)

	def exceeded_by(self, value: float) -> bool:
		"""Whether ``value`` is over the ceiling — FR-057's refusal, and only that end."""
		return self.maximum is not None and value > self.maximum

	def below(self, value: float) -> bool:
		"""Whether ``value`` is under the floor. A measurement, never a refusal."""
		return self.minimum is not None and value < self.minimum

	def stated(self) -> str:
		"""The bound as an operator reads it, in the dimension's own unit."""
		if self.minimum is not None and self.maximum is not None:
			if self.minimum == self.maximum:
				return f"{_number(self.minimum)} {self.unit}"
			return f"{_number(self.minimum)}-{_number(self.maximum)} {self.unit}"
		if self.maximum is not None:
			return f"at most {_number(self.maximum)} {self.unit}"
		assert self.minimum is not None, "a bound with neither end was refused by the type"
		return f"at least {_number(self.minimum)} {self.unit}"


def _number(value: float) -> str:
	"""A count as an operator reads it: ``5``, not ``5.0``."""
	return f"{value:g}"


class DeliveryEnvelope(View):
	"""§1.3's eight dimensions as configuration (NFR-025, FR-057).

	The defaults are §1.3's table verbatim, and that is the point of writing them out
	rather than deriving them: NFR-025 makes the envelope configuration *and* calls it
	"a hypothesis under test", so a deployment may widen or narrow it — but the
	factory's own default may not quietly differ from the spec's stated target, or an
	operator comparing a delivery against §1.3 would be comparing it against numbers the
	factory never used.

	Fixed fields rather than a mapping, so ``extra="forbid"`` makes a config file that
	names a dimension this build does not know a refusal rather than a setting that is
	silently ignored — the failure mode of a config seam is a typo that changes nothing
	and reports success.
	"""

	systems: DimensionBound = DimensionBound(unit="systems", minimum=1, maximum=3)
	modules: DimensionBound = DimensionBound(unit="modules", minimum=8, maximum=25)
	delivered_loc: DimensionBound = DimensionBound(unit="LOC", minimum=3000, maximum=15000)
	external_integrations: DimensionBound = DimensionBound(
		unit="integrations", minimum=0, maximum=3
	)
	human_gates: DimensionBound = DimensionBound(unit="gates", minimum=4, maximum=4)
	human_minutes: DimensionBound = DimensionBound(unit="minutes", minimum=180, maximum=600)
	wall_clock_days: DimensionBound = DimensionBound(unit="days", minimum=2, maximum=10)
	value_hypothesis: DimensionBound = DimensionBound(unit="declared", minimum=1, maximum=1)

	def bound(self, dimension: EnvelopeDimension) -> DimensionBound:
		"""The bound on one dimension. Total over the enum, so no dimension is unreachable."""
		return getattr(self, dimension.value)


class EnvelopeMeasurement(View):
	"""One dimension's actual, and whether anything in the log measures it at all.

	``actual`` and ``within`` are both optional and they move together: ``actual is
	None`` means nothing SoFact holds measures this dimension, and ``within`` is then
	``None`` rather than ``True``. A missing measurement reported as inside the envelope
	is the one wrong default available here, because it makes an unmeasured dimension
	indistinguishable from a satisfied one — the same rule ADR-0038 applies to an absent
	verdict, applied to delivery.
	"""

	dimension: EnvelopeDimension
	bound: DimensionBound
	actual: float | None = None
	within: bool | None = None
	detail: NonEmptyStr
	"""What was measured, or what would have to exist before anything could be."""

	@model_validator(mode="after")
	def _an_unmeasured_dimension_is_never_within(self) -> Self:
		if (self.actual is None) != (self.within is None):
			raise ValueError(
				f"the {self.dimension.value} measurement carries actual={self.actual!r} "
				f"with within={self.within!r}; a dimension is either measured and judged, "
				"or unmeasured and unjudged, and a half-measurement would let a missing "
				"reading be reported as a satisfied one (NFR-025)"
			)
		if self.actual is not None and self.within is not self.bound.admits(self.actual):
			raise ValueError(
				f"the {self.dimension.value} measurement claims within={self.within} for "
				f"{_number(self.actual)}, which is {'inside' if self.bound.admits(self.actual) else 'outside'} "
				f"its bound of {self.bound.stated()}"
			)
		return self

	@property
	def statement(self) -> str:
		"""The measurement as one line an operator reads in a report."""
		if self.actual is None:
			return f"{self.dimension.value}: unmeasured — {self.detail}"
		verdict = "within" if self.within else "OUTSIDE"
		return (
			f"{self.dimension.value}: {_number(self.actual)} {self.bound.unit} "
			f"({verdict} {self.bound.stated()}) — {self.detail}"
		)


class EnvelopeActuals(View):
	"""A project's measured dimensions against the envelope (NFR-025, FR-118).

	Derived rather than recorded, like everything else that is a fact about the log: a
	stored actuals row would be a reading that could disagree with the log it claims to
	have read.
	"""

	envelope: DeliveryEnvelope
	measurements: tuple[EnvelopeMeasurement, ...]

	@property
	def exceeded(self) -> tuple[EnvelopeMeasurement, ...]:
		"""Measured dimensions over their ceiling — what FR-057 refuses a goal for."""
		return tuple(m for m in self.measurements if m.within is False and self._over(m))

	@property
	def below(self) -> tuple[EnvelopeMeasurement, ...]:
		"""Measured dimensions under their floor. A measurement, not a defect (§1.3)."""
		return tuple(
			m for m in self.measurements if m.actual is not None and m.bound.below(m.actual)
		)

	@property
	def unmeasured(self) -> tuple[EnvelopeMeasurement, ...]:
		"""Dimensions nothing SoFact holds measures, each naming what would be needed."""
		return tuple(m for m in self.measurements if m.actual is None)

	@property
	def is_within(self) -> bool:
		"""True when no *measured* dimension is over its ceiling.

		Not a claim about the unmeasured ones — :attr:`unmeasured` names those, and a
		report that printed this boolean alone would read as "the delivery is inside the
		envelope" while three of the eight dimensions were never looked at.
		"""
		return not self.exceeded

	@staticmethod
	def _over(measurement: EnvelopeMeasurement) -> bool:
		assert measurement.actual is not None, "an exceeded dimension has been measured"
		return measurement.bound.exceeded_by(measurement.actual)


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


class ReasoningClass(StrEnum):
	"""The routing class a module's work needs (FR-050, FR-097).

	§10.2's three classes, and the requirement's own point is that this is what a lane
	declares — "the class they need (reasoning-depth or throughput), not a model name"
	(FR-050). A model name in a contract would make the contract depend on a vendor, and
	NFR-026 makes the factory model-agnostic for exactly that reason.

	``EVALUATION`` is in §10.2's table and is marked there as "ideally deterministic
	tooling, not a model". It is kept because a declared budget that cannot name the
	class a lane needs is not the declaration FR-097 asks for, and the table's own
	comment is a reason to prefer a tool, not a reason the class does not exist.
	"""

	THROUGHPUT = "throughput"
	"""High-volume, low-depth: test generation, codemods, triage, classification."""

	REASONING = "reasoning"
	"""Low-volume, depth per token: planning, failure diagnosis, adversarial hacking."""

	EVALUATION = "evaluation"
	"""Oracle strength, differential analysis — deterministic tooling where possible."""


class ModuleBudget(View):
	"""What one module may cost, declared before it is built (FR-026, FR-097).

	Two requirements wear this type. FR-097 says "every contract must declare an explicit
	budget (files, LOC, reasoning class)", and FR-026 says a lane must declare a maximum
	changed-file count and a maximum diff size — "a large diff is unverifiable
	regardless of oracle results, because review bandwidth is the binding resource".
	§14 makes a module the Mode G lane, so the two are one declaration over one object,
	and FR-097's own words are that exceeding it "fails the module and escalates, on the
	same logic as FR-026".

	Every field is required. A budget with a missing dimension is not a partial budget,
	it is an undeclared one: the absence of a file cap would read as an unlimited file
	cap, which is the one default a bound may not have (the argument
	:data:`MODE_G_CEILING` makes about a cap keyed to input nobody supplied).

	**The bound is on the artefact and not on the diff**, and the difference is a
	deliberate tightening rather than a substitution. For a module built from nothing —
	which is what P5 builds, a module that did not exist — the added lines *are* the
	artefact's lines. The two differ only after a repair, where the diff is smaller than
	the module; and there a bound on the artefact is the stricter one, because a diff
	bound would let a module grow without limit across repairs that each stayed inside
	it. P7 measures the artefact because the attribution it already computes (FR-113's,
	per module) is what makes the number attributable at all — a repository-wide diff
	names no module, and FR-114's repair scope needs one.
	"""

	max_files: int
	"""The most files this module's steps may seal between them."""

	max_loc: int
	"""The most lines those files may hold, counted over every one of them."""

	reasoning_class: ReasoningClass
	"""The class of work this module needs (FR-050). A class, never a model name."""

	@model_validator(mode="after")
	def _positive_bounds(self) -> Self:
		if self.max_files < 1:
			raise ValueError(f"file bound must be at least 1, got {self.max_files}")
		if self.max_loc < 1:
			raise ValueError(f"line bound must be at least 1, got {self.max_loc}")
		return self


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

	completion_criteria: tuple[NonEmptyStr, ...] = ()
	"""FR-093's Definition of Done, as the conditions that must hold for this module.

	Derived from the *clause's oracle class* rather than authored per module, and that is
	the point: the oracle class is the clause's shape of proof, so a property clause is
	done when property tests pass and a schema clause is done when interface conformance
	passes. An operator-written DoD would be a second statement of what the oracle already
	says, and the two would drift.

	Empty is a real state and is refused at the gate, not by the type — see
	:func:`sofact.decomposition.completion_criteria` for why the refusal lives there.
	"""

	budget: ModuleBudget
	"""What this module may cost, declared before it is built (FR-026, FR-097).

	Required, with no default, because FR-097's own word is "must declare" and a
	defaulted budget is an undeclared one that reads as a declaration. A module whose
	size nobody bounded is exactly the module §7.3's review-bandwidth argument is about,
	and the type is the only place that refusal costs nothing to enforce: a default here
	would have to be some number, and any number would be the factory inventing a
	bound the operator never set.
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


class SystemCriterion(View):
	"""A P2 acceptance criterion that no single module can satisfy (FR-116).

	FR-116 asks integration to run "system-level acceptance criteria from P2 that no
	single module can satisfy. These are the criteria that validate the *decomposition*,
	not the modules." The criterion is therefore declared as *spanning clauses*: a
	criterion over one clause is a module's job and belongs in the contract, and one over
	several is precisely the claim a decomposition makes and can get wrong.

	``clause_ids`` is what makes it checkable rather than a second prose statement of the
	same obligation: the criterion is satisfied exactly when every clause it spans carries
	a satisfied verdict, which is a fact about the log and not about anyone's reading of
	the sentence. It points at clauses rather than at requirement ids for the reason
	:class:`SystemEntity` does — a clause is the stable thing an operator can name.
	"""

	id: UUID7
	statement: NonEmptyStr
	criterion: NonEmptyStr
	"""How the criterion is known to hold, in the operator's words."""
	clause_ids: tuple[UUID7, ...]

	@model_validator(mode="after")
	def _spans_more_than_one_module_can_own(self) -> Self:
		if len(self.clause_ids) < 2:
			raise ValueError(
				f"system criterion {self.statement[:40]!r} spans {len(self.clause_ids)} "
				"clause(s): FR-116 asks for criteria *no single module can satisfy*, and "
				"one clause is one module's job — it belongs in the contract, where P6 "
				"already checks it"
			)
		if len(set(self.clause_ids)) != len(self.clause_ids):
			raise ValueError(
				f"system criterion {self.statement[:40]!r} names a clause twice, so it "
				"spans fewer clauses than it claims to"
			)
		return self


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
	system_criteria: tuple[SystemCriterion, ...] = ()
	"""FR-116's criteria, which no single module can satisfy.

	Declared at P2 rather than derived, and empty is a real state: a system whose every
	obligation is a module's own has no system-level criterion, and :func:`gate` reports
	that as a *measurement* rather than as a failure — the same treatment FR-082 gives a
	human-verified requirement. Inventing a criterion by joining two clauses would be the
	machine writing the claim that its own decomposition composes, which is the claim P7
	exists to test.
	"""

	@model_validator(mode="after")
	def _system_criteria_span_declared_clauses(self) -> Self:
		known = self.clause_ids
		for criterion in self.system_criteria:
			strangers = tuple(cid for cid in criterion.clause_ids if cid not in known)
			if strangers:
				raise ValueError(
					f"system criterion {criterion.statement[:40]!r} spans clause(s) no "
					f"requirement traces to: {list(strangers)} — a criterion over a clause "
					"the specification dropped cannot be satisfied by anything (FR-116)"
				)
		return self

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


PHASE_GATE_INVERSE: dict[PhaseGate, Phase] = {gate: phase for phase, gate in PHASE_GATE.items()}
"""The phase a gate belongs to. Derived from :data:`PHASE_GATE`, so the two cannot
disagree — and derived rather than written out because a second hand-maintained table
is a second place for a gate to be attached to the wrong phase."""


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


class GateCost(View):
	"""FR-160's measurement: what one human gate actually cost.

	§1.3's 180-600 human-minute figure is a **budget**, and FR-160's argument for
	recording against it is that a factory measuring the producer's budget and not the
	reviewer's is optimising its cheapest step. So every gate records two numbers: the
	human-minutes it took, and the share of the slice the operator sent back.

	Both are **declared**, and the instrument being the human is not a weakness to be
	designed around — it is the measurement. Nothing in SoFact observes a person
	reading, and the log holds no clock on human attention, so a *derived* number here
	would be an invention wearing a measurement's clothes. This is the one operator-
	supplied value in SoFact that is not a restatement of something the log already
	holds, which is why it is admissible at all: FR-093's Definition of Done is derived
	because the oracle already states it, and this is recorded because nothing does.

	``recorded_by`` names the declarer for the same reason every gate names its
	approver: an unattributed number is one nobody is accountable for. The report marks
	these as declared rather than observed (NFR-024), so a reader is never told the
	factory measured something it was told.

	``rework_fraction`` is a share of the *slice* — the requirements or modules put in
	front of the operator — not of the time. §20.2's claim is about attention, and a
	gate that cost 40 minutes and sent 60% of the artefact back is a different datum
	from one that cost 40 and sent nothing back, which is why the two are separate
	fields rather than one "cost" number.
	"""

	gate: PhaseGate
	human_minutes: float
	rework_fraction: float
	recorded_by: NonEmptyStr
	recorded_at: datetime

	@model_validator(mode="after")
	def _a_cost_is_a_measurement(self) -> Self:
		if self.human_minutes < 0:
			raise ValueError(
				f"a gate cannot cost {self.human_minutes:g} human-minutes; a negative "
				"cost would lower §1.3's total, which is the one direction a measurement "
				"of the binding constraint must not be able to move (FR-160)"
			)
		if not 0.0 <= self.rework_fraction <= 1.0:
			raise ValueError(
				f"the rework fraction of {self.rework_fraction:g} is not a share; 0.0 is "
				"a slice the operator accepted whole and 1.0 is one returned entire, and "
				"nothing outside that range is a fraction of a slice (FR-160)"
			)
		return self


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
	topology: DeploymentTopology = DeploymentTopology.T1
	"""The deployment this verdict was rendered under (FR-030).

	FR-030 requires the active topology reported in "every oracle report", not only in
	the delivery, and the reason is §5.4's: an oracle report is where an autonomy claim
	is made, so it is where the claim's premise has to appear. A verdict rendered under
	T1 and one rendered under T2 can support different levels for the same clause, and a
	report that carried only the level could not be told from the other.

	The default is the degraded topology, like :attr:`DeliveryReport.topology`.
	"""

	topology_configured: bool = False
	"""Whether the deployment declared its topology or fell back to T1 (FR-042)."""

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

	MISSING_ENTITY = "missing_entity"
	"""An entity's clause maps to a module the decomposition does not declare (FR-115)."""

	UNOWNED_ENTITY = "unowned_entity"
	"""No module owns any clause that introduces the entity (FR-115)."""

	UNSATISFIED_SYSTEM_CRITERION = "unsatisfied_system_criterion"
	"""A system-level criterion has no satisfied verdict from any module (FR-116)."""

	MODULE_OVER_BUDGET = "module_over_budget"
	"""A module's built artefact exceeds the budget its contract declared (FR-026, FR-097).

	The modules are the *minimum violating set* here in the strictest sense: the bound is
	per module, so the repair scope is exactly the one module that overspent and never the
	plan. That is what makes FR-026's "fails the module and escalates" a scoped escalation
	rather than a halt.
	"""


class IntegrationFinding(View):
	"""One violation, attributed to the modules it implicates (FR-114).

	``modules`` is the *minimum violating set*: the modules that must be repaired for the
	finding to go away. FR-114 forbids a platform-wide rebuild in response to a local
	failure, so the set is as small as the evidence allows and is what a repair is
	scoped to.

	``modules`` may be empty, and that is a real answer rather than a defect: FR-115's
	structural findings are about the *model* and FR-116's about *criteria*, so a finding
	whose cause is the absence of a module cannot name one. An empty set here means the
	repair is not scoped to a module at all — it is a specification change — and
	:attr:`IntegrationReport.violating_modules` excludes it rather than widening the
	scope to the platform, which is what FR-114 refuses.
	"""

	kind: IntegrationFindingKind
	detail: NonEmptyStr
	modules: tuple[NonEmptyStr, ...]
	evidence: tuple[NonEmptyStr, ...] = ()
	"""The concrete lines — the import statement, the path — so the finding is checkable."""


INTEGRATION_REQUIREMENTS: Final[tuple[str, ...]] = (
	"FR-026",
	"FR-097",
	"FR-111",
	"FR-112",
	"FR-113",
	"FR-114",
	"FR-115",
	"FR-116",
)
"""Every requirement P7 can discharge, so a check can claim one and a report can see the rest.

The list is the *whole* of P7 rather than the part that is implemented. A report that
named only what it ran could not distinguish a system that integrates from a system
nothing was checked on, and the difference is exactly what a green line hides.

FR-026 and FR-097 are here rather than among §10's own numbers because both are bounds on
a *built module*, and P7 is the only stage that knows which files a module produced
(FR-113's attribution is the same fact). A bound checked anywhere else would be checked
against a guess at what the module contains.
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
		from this tuple on the strength of a check that compared nothing. FR-115 and FR-116
		are the same shape one level up: their checks run, but they discharge nothing until
		the approved specification declares a system model and criteria spanning more than
		one clause, so a project that described no system still reports them here. All of
		those gaps land in this tuple, and none of them needs a list edited to get here.
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


# --------------------------------------------------------------------------- #
# §11 — delivery (P8): the report, the deploy gate, and the handover
# --------------------------------------------------------------------------- #

DELIVERY_REQUIREMENTS: Final[tuple[str, ...]] = (
	"FR-117",
	"FR-118",
	"FR-119",
	"FR-120",
	"FR-121",
)
"""Every requirement §11 states. The whole of P8, not the part that is implemented.

The same rule :data:`INTEGRATION_REQUIREMENTS` states one phase earlier: a report that
named only what it produced could not distinguish a delivered platform from a directory
of files, and the difference is what a green line hides.
"""


class DeliveryArtifactKind(StrEnum):
	"""What FR-117 requires a delivery to contain.

	Four kinds and no fifth. FR-117 names them, and a kind the code cannot spell is an
	artefact nothing can be recorded as missing — so the report would read as complete
	because it never mentioned the thing it did not build.
	"""

	IMAGE = "image"
	"""The deployable artifact: a container image "or equivalent" (FR-117)."""

	INFRASTRUCTURE = "infrastructure"
	"""Infrastructure-as-code for the target environment (FR-117)."""

	RUNBOOK = "runbook"
	"""The operational runbook (FR-117)."""

	REPORT = "report"
	"""The delivery report itself, which carries the traceability chain (FR-117)."""


DELIVERY_ARTIFACTS: Final[tuple[DeliveryArtifactKind, ...]] = tuple(DeliveryArtifactKind)


UNPRODUCIBLE: Final[dict[DeliveryArtifactKind, str]] = {
	DeliveryArtifactKind.IMAGE: (
		"no packaging decision exists. FR-117 says a container image 'or equivalent', and "
		"ADR-0005 refuses to assume a container runtime, so what a deployable artifact is "
		"for this platform is the operator's call at deploy time (T2, open)"
	),
	DeliveryArtifactKind.INFRASTRUCTURE: (
		"infrastructure-as-code is written for a named target environment, and the "
		"operator names one at the deploy gate rather than at P3. Producing it here would "
		"be the factory choosing a topology, which FR-124 makes a per-deployment decision"
	),
}
"""The FR-117 artefacts SoFact does not produce, and what would have to exist.

A reason per kind rather than one shared string, because the two need different actions:
the image needs a packaging decision and the IaC needs a named environment.

This table is why the delivery-artefact check is scoped rather than whole. A check over
all four kinds can never pass, because two of them are decisions SoFact has deliberately
not made — and a gate that cannot pass is one an operator learns to bypass, which turns
off the part of it that does matter. The check therefore fails on the artefacts the
factory owes and reports these two as decisions the gate is where to take.
"""

UNPRODUCIBLE_KINDS: Final[frozenset[DeliveryArtifactKind]] = frozenset(UNPRODUCIBLE)
"""The same fact as a membership test, so a caller does not rebuild the set."""


class DeliveryArtifact(View):
	"""One artefact FR-117 requires, and whether this delivery has it.

	``path`` is relative to the delivery root and is required when ``present`` is true,
	because "we have a runbook" is not a statement a deploy gate can act on: the operator
	has to be able to open it. An absent artefact carries ``missing_because`` instead, and
	that field is required in the other direction for the reason
	:class:`~sofact.views.IntegrationCheck` requires ``uncovered`` — an absence with no
	reason is indistinguishable from an oversight, and the two need different responses.
	"""

	kind: DeliveryArtifactKind
	present: bool
	path: NonEmptyStr | None = None
	missing_because: NonEmptyStr | None = None

	@model_validator(mode="after")
	def _presence_is_whole(self) -> Self:
		if self.present and self.path is None:
			raise ValueError(
				f"the {self.kind.value} artefact is recorded present with no path, so a "
				"deploy gate could not show it to anyone (FR-117)"
			)
		if not self.present and self.path is not None:
			raise ValueError(f"the {self.kind.value} artefact is absent and names a path")
		if not self.present and self.missing_because is None:
			raise ValueError(
				f"the {self.kind.value} artefact is absent with no reason, which is "
				"indistinguishable from an oversight (FR-117)"
			)
		if self.present and self.missing_because is not None:
			raise ValueError(f"the {self.kind.value} artefact is present and says why it is not")
		return self


class TraceLink(View):
	"""One intent clause and the deployed component that satisfies it (FR-117).

	FR-117 asks the delivery report to contain "the traceability chain from intent clause
	to deployed component", and this is one hop of it. The chain has three hops in
	SoFact's log — clause to requirement (P2), requirement to module (P3), module to the
	step that built it (P5) — and a report that printed only the endpoints would leave the
	middle unverifiable, which is where a fabricated link would live.
	"""

	clause_id: UUID7
	statement: NonEmptyStr
	"""The clause's own words, so a reader of the report does not have to open the log."""

	requirement_id: UUID7 | None = None
	module: NonEmptyStr | None = None
	step_ordinal: int | None = None

	@property
	def is_whole(self) -> bool:
		"""Whether every hop of the chain is present.

		A link missing a hop is the honest state of a project whose decomposition dropped
		the clause or whose plan never dispatched the module, and the report counts them
		rather than printing a chain that stops halfway as though it were complete.
		"""
		return (
			self.requirement_id is not None
			and self.module is not None
			and self.step_ordinal is not None
		)

	@property
	def rendered(self) -> str:
		"""The chain, with a gap drawn where a hop is missing rather than elided."""
		requirement = self.requirement_id if self.requirement_id is not None else "(no requirement)"
		module = self.module if self.module is not None else "(no module)"
		step = (
			f"step {self.step_ordinal}" if self.step_ordinal is not None else "(never dispatched)"
		)
		return f"{self.clause_id} -> {requirement} -> {module} -> {step}"


class VerifiedClause(View):
	"""A clause that is verified, and by which oracle at which measured strength (FR-118).

	FR-118's first bullet asks for the oracle **and its measured strength**. SoFact
	measures neither today: ``OracleDeclaration.rank`` is a declaration the operator made
	(FR-105 records the same gap one phase earlier), and nothing runs a mutation score. So
	this type carries ``rank`` as declared and ``measured_strength`` as ``None``, and
	:attr:`measured` says which it is — a report that printed the declared rank under the
	word "measured" would be the exact euphemism FR-118 forbids.
	"""

	clause_id: UUID7
	statement: NonEmptyStr
	oracle_class: OracleClass
	rank: int
	"""The declared rank, 1 (strongest) to 7. Read from the clause's own oracle."""

	measured_strength: float | None = None
	"""A measured mutation score, when one exists. Nothing produces one yet."""

	@property
	def measured(self) -> bool:
		"""Whether the strength above is a measurement or a declaration."""
		return self.measured_strength is not None

	@property
	def rendered(self) -> str:
		"""The clause in its own words, with the strength and how it was arrived at.

		The clause's *statement* rather than its id, because FR-118 asks the report to
		state which clauses are verified and an operator reading a list of UUIDs has to
		open the log to learn what was verified — which is the report failing to be one.
		The id stays on the type for the traceability chain to join on.
		"""
		strength = (
			f"measured {self.measured_strength:.2f}"
			if self.measured_strength is not None
			else f"declared rank {self.rank}, not measured"
		)
		return f"{self.statement} [{self.oracle_class.value}, {strength}]"


class UnverifiedClause(View):
	"""A clause nothing verified, and why (FR-118's second bullet, FR-108).

	FR-118 requires the report to state which clauses are **unverified** — "ground-truth
	debt" — and the reason is the load-bearing part: a clause whose oracle names no
	command is debt the operator can retire by writing one, while a clause whose oracle
	ran and returned insufficient is debt that needs a stronger oracle. Collapsing both
	into one count would make the report's most important number unactionable.
	"""

	clause_id: UUID7
	statement: NonEmptyStr
	outcome: VerdictOutcome | None
	"""The worst verdict the clause received, or ``None`` if its oracle never ran."""

	because: NonEmptyStr
	"""What would have to change for this clause to be verified."""

	@property
	def is_ground_truth_debt(self) -> bool:
		"""Whether no machine can check this clause at all (FR-108).

		Distinct from a clause that *was* checked and came back insufficient: the first is
		a contract defect, the second is a build defect, and FR-108's debt fraction counts
		only the first.
		"""
		return self.outcome is None

	@property
	def rendered(self) -> str:
		"""The clause in its own words, and what would change its state (FR-118).

		The statement rather than the id, for the reason
		:attr:`VerifiedClause.rendered` gives: a list of UUIDs is not a report.
		"""
		verdict = self.outcome.value if self.outcome is not None else "never run"
		return f"{self.statement} [{verdict}]: {self.because}"


class InheritedOracle(View):
	"""One oracle a Mode M lane inherits from the Mode G contract (FR-121).

	FR-121's composition claim — "the output of Mode G is a valid input to Mode M" — is
	the claim that a maintenance lane has something to run. This is that something, and
	it is a *reference to a clause* rather than a copy of its oracle, so the handover
	cannot drift from the contract it came from: editing the oracle here would make the
	delivered system's maintenance criteria differ from the ones its build was verified
	against.
	"""

	clause_id: UUID7
	statement: NonEmptyStr
	command_hint: NonEmptyStr | None = None
	"""The command the clause's oracle names, or ``None`` for an intention (FR-082).

	``None`` is the honest state of a clause whose oracle is prose: a lane inheriting it
	inherits a criterion a human has to check, and the handover says so rather than
	counting it as coverage.
	"""

	rank: int

	@property
	def is_executable(self) -> bool:
		"""Whether a maintenance run could execute this unattended."""
		return self.command_hint is not None


class MaintenanceLane(View):
	"""One Mode M lane the delivered system is handed over under (FR-121).

	§13's lanes are retained from v0.1 and are the *maintenance* entry point: L01-L12,
	with L11 the adversarial audit service and L12 self-maintenance. A handover names the
	lanes the delivered system can be maintained under, so that "the output of Mode G is
	a valid input to Mode M" is a claim the artefact carries rather than one the operator
	has to reconstruct.

	The lane classes are §13's and are *not* §14's module classes: Mode M's lanes are
	typed by what kind of maintenance work they are (dependency bump, test repair,
	adversarial audit), and a G-class says what a module *is*. A handover that named G
	classes would be handing the next mode a taxonomy for building rather than for
	maintaining.
	"""

	lane: NonEmptyStr
	"""The lane's §13 identifier, e.g. ``L01``."""

	description: NonEmptyStr
	inherited_oracles: tuple[InheritedOracle, ...]
	"""The contract clauses whose oracles this lane runs (FR-121).

	Empty is a real state and not an error: a lane whose work no contract clause covers
	is a lane the delivered system cannot be maintained under with an oracle, and naming
	that is more useful than inventing a clause to fill the row.
	"""

	ceiling: AutonomyLevel
	"""The lane's §13 autonomy, a property of the lane and not of the delivery."""

	@model_validator(mode="after")
	def _a_lane_names_itself(self) -> Self:
		if not self.lane.strip():
			raise ValueError("a maintenance lane with no name cannot be selected")
		clauses = [oracle.clause_id for oracle in self.inherited_oracles]
		if len(set(clauses)) != len(clauses):
			raise ValueError(
				f"lane {self.lane!r} inherits two oracles for one clause, so one of them "
				"is not what the contract says (FR-121)"
			)
		return self

	@property
	def executable_oracles(self) -> tuple[InheritedOracle, ...]:
		"""The inherited oracles a maintenance run could execute unattended (FR-082)."""
		return tuple(oracle for oracle in self.inherited_oracles if oracle.is_executable)


class Handover(View):
	"""FR-121's maintenance handover: how the delivered system is maintained next.

	Genesis and maintenance must compose — "the output of Mode G is a valid input to Mode
	M" — and the composition is only checkable if the handover is an artefact. This is
	that artefact: the lanes, the oracles they inherit, and the entry point a maintenance
	run starts from.

	``unmaintainable`` is derived rather than stored, and it is the property that makes
	the composition claim honest: a delivered system whose every clause is prose has lanes
	with nothing to run, and a handover that reported only its lanes would read as a
	system ready for maintenance when it is a system waiting for someone to write the
	first test.
	"""

	system: NonEmptyStr
	"""What was delivered, named so a maintenance run can address it."""

	entry_point: NonEmptyStr
	"""Where a Mode M run begins: the repository and the lane configuration (FR-121)."""

	lanes: tuple[MaintenanceLane, ...]

	@model_validator(mode="after")
	def _the_handover_carries_something(self) -> Self:
		if not self.lanes:
			raise ValueError(
				"a handover with no lane is not a valid Mode M input: a maintenance run "
				"would have no lane to select (FR-121)"
			)
		named = {lane.lane for lane in self.lanes}
		if len(named) != len(self.lanes):
			raise ValueError("two maintenance lanes share a name, so a run could not select one")
		return self

	@property
	def inherited_oracles(self) -> tuple[InheritedOracle, ...]:
		"""Every oracle the handover passes on, deduplicated across lanes.

		Derived from the lanes rather than stored beside them: two statements of one fact
		is how a handover comes to disagree with itself about what the delivered system
		can check.
		"""
		seen: dict[str, InheritedOracle] = {}
		for lane in self.lanes:
			for oracle in lane.inherited_oracles:
				seen.setdefault(oracle.clause_id, oracle)
		return tuple(seen.values())

	@property
	def unmaintainable(self) -> tuple[InheritedOracle, ...]:
		"""Inherited oracles that name no command, so no lane can run them (FR-082).

		The delivered system's ground-truth debt, one phase later: FR-108 counts it in the
		contract, and this counts what actually reaches the maintenance mode.
		"""
		return tuple(oracle for oracle in self.inherited_oracles if not oracle.is_executable)


class DeliveryReport(View):
	"""P8's artefact: what was delivered, and what is true about it (FR-117, FR-118).

	FR-118's five statements are five *fields* rather than five paragraphs of prose,
	because a report is the one artefact an operator reads under time pressure and a
	sentence is the easiest place for a qualification to go missing. Each field is
	required, so a report cannot be constructed that omits the awkward one — which is
	FR-118's own word, "explicitly and without euphemism".

	The fifth statement, FR-086's, is a *constant*: :attr:`VERIFIED_NOT_VALUE` is the only
	string this type will accept for it. That is the difference between a report that
	says the factory did not certify value and one that was written by a factory which
	could not have certified it — FR-086 makes the claim unavailable to every code path,
	and a free-text field would put it back.
	"""

	VERIFIED_NOT_VALUE: ClassVar[str] = (
		"Requirements were verified, not value. Every clause below is a claim that an "
		"oracle decided; the value hypothesis is declared and untested (FR-086)."
	)

	id: UUID7
	goal_id: UUID7
	contract_id: UUID7
	plan_id: UUID7
	rendered_at: datetime

	artifacts: tuple[DeliveryArtifact, ...]
	"""FR-117's four required artefacts, one entry each, present or absent with a reason."""

	chain: tuple[TraceLink, ...]
	"""FR-117's traceability chain, one link per intent clause."""

	verified: tuple[VerifiedClause, ...]
	"""FR-118's first statement: which clauses are verified, and at what strength."""

	unverified: tuple[UnverifiedClause, ...]
	"""FR-118's second statement: which clauses are not, and what would change that."""

	unvalidated_assumptions: tuple[Assumption, ...]
	"""FR-118's third statement: every P2 assumption that remains unvalidated.

	Every declared assumption, not a filtered subset. FR-118 says "every assumption from
	P2 that remains unvalidated", and nothing in SoFact validates one — FR-079 makes an
	assumption falsifiable by naming its refuting observation, and nothing runs that
	observation. So the honest report is all of them, and a filter here would be the
	factory asserting a validation it never performed.
	"""

	envelope_actuals: EnvelopeActuals | None
	"""FR-118's fifth statement: the actuals against the §1.3 envelope (NFR-025).

	``None`` when the deployment configured no envelope, which is a different statement
	from "every dimension is within bounds" — the report says which it is rather than
	printing an empty table that reads as compliance.

	Carries FR-160's human-minutes when any gate recorded a cost, because §1.3's
	``human_minutes`` is one of the eight dimensions. The rework fraction is not a
	dimension and is carried separately in :attr:`gate_costs`.
	"""

	gate_costs: tuple[GateCost, ...] = ()
	"""FR-160's measurement, carried by the report rather than computed beside it.

	FR-160 says both numbers "must appear in the delivery report", and the requirement's
	argument is §20.2's: if review is the binding constraint once implementation is
	agent-driven, a factory that measures the producer's budget but not the reviewer's is
	optimising its cheapest step. So the per-gate costs travel with the report the deploy
	gate presents, and a report over a project whose gates recorded nothing says so
	instead of printing an empty table.

	Empty is a real state and means *unmeasured*, not *free*. The sum of these is
	:attr:`sofact.views.ProjectState.total_human_minutes`, and it reaches the report
	through ``envelope_actuals``; this field is what makes the per-gate detail — including
	the rework fraction, which no envelope dimension holds — readable at the gate.
	"""

	@property
	def rework_fraction(self) -> float | None:
		"""The mean share of each gated slice returned to the producer (FR-160).

		``None`` when no gate recorded a cost, for the reason every unmeasured dimension
		gives: zero would be the claim that nothing was ever sent back, which is a
		different and flattering statement. A mean rather than a sum because a fraction of
		a slice does not add across gates — four gates each returning a quarter is a
		quarter, not one.
		"""
		if not self.gate_costs:
			return None
		return sum(c.rework_fraction for c in self.gate_costs) / len(self.gate_costs)

	autonomy: AutonomyLevel
	"""The lowest ceiling anything in the delivery carries (FR-122), capped at L2 (FR-123).

	The *delivery's* number, which FR-123 fixes at L2 for a Mode G run because P2, P3 and
	P8 are human gates. The modules' number is :attr:`module_autonomy` and is usually
	higher; the two are separate fields because the requirement is a distinction and one
	number cannot state one.
	"""

	module_autonomy: AutonomyLevel
	"""What the modules sustain internally: the lower of the contract's measured ceiling
	and every module class's (FR-122), with no Mode G cap applied.

	Reported beside :attr:`autonomy` because FR-123 requires the *distinction* to be
	explicit — "individual modules may run at L4 internally; the delivery is L2" — and a
	report carrying only the capped number would read as a pipeline that cannot build
	above L2, which is a different and false claim.

	The number carries §5.4's topology modifier (FR-019, FR-124), so a T1 deployment
	reports the lowered value rather than the one its hardware cannot support.
	"""

	topology: DeploymentTopology = DeploymentTopology.T1
	"""The deployment this delivery was rendered under (FR-030, FR-124).

	A field with a default, and the default is the *degraded* topology. §5.4's whole
	point is that the same work has different admissible ceilings on different hardware,
	so a report that did not say where it ran would be a ceiling claim with its premise
	missing. T1 is the default for the same reason :data:`MODE_G_CEILING` is a constant
	rather than a lookup: a ceiling that fails open on unconfigured input is the one
	failure a ceiling may not have (FR-042).

	It is a field rather than a property of the service so that a report stays readable
	from the log alone — the topology a delivery was rendered under is part of what the
	report *says*, not something a later reader has to reconstruct from the deployment's
	current configuration, which may since have changed.
	"""

	topology_configured: bool = False
	"""Whether the deployment *declared* its topology, or fell back to T1 (FR-042).

	Separated from :attr:`topology` because the two facts differ and only one of them is
	a defect: a factory deliberately running on a dev machine and one that never said
	where it runs both report T1, and an operator who cannot tell them apart cannot tell
	whether the low number is a choice or a missing setting. FR-042 asks for exactly this
	— the dev instance "must report its degraded ceiling rather than silently behaving as
	if it were T2".
	"""

	handover: Handover
	"""FR-121's Mode M handover, carried by the report rather than computed beside it.

	A field and not a separate artefact because FR-121's claim is a claim about *this*
	delivery — that its output is a valid Mode M input — and a handover rendered from the
	contract at some other time could be rendered from a contract this delivery was not
	verified against. The deploy gate shows it for the same reason: whoever passes the
	gate is the last person who can refuse a delivery whose maintenance story is empty.
	"""

	checks: tuple[GateCheck, ...]

	@model_validator(mode="after")
	def _the_five_statements_are_whole(self) -> Self:
		if not self.chain:
			raise ValueError("a delivery report over no intent clause traces nothing (FR-117)")
		if not self.artifacts:
			raise ValueError("a delivery report with no artefacts reports nothing (FR-117)")
		kinds = [a.kind for a in self.artifacts]
		if len(set(kinds)) != len(kinds):
			raise ValueError("two artefacts share a kind, so one of FR-117's four is missing")
		if not self.checks:
			raise ValueError("a delivery report with no checks is not a report")
		if not self.handover.lanes:
			raise ValueError(
				"a delivery report whose handover has no lane is not an FR-121 Mode M "
				"input, so the delivery would leave nothing to maintain it with"
			)
		return self

	@property
	def missing_artifacts(self) -> tuple[DeliveryArtifact, ...]:
		"""FR-117's artefacts this delivery does not have, each with its reason."""
		return tuple(a for a in self.artifacts if not a.present)

	@property
	def undecided_artifacts(self) -> tuple[DeliveryArtifact, ...]:
		"""FR-117's artefacts SoFact does not produce, as decisions the gate must take.

		Separated from :attr:`missing_artifacts` because the two need different
		responses: a missing runbook is work the factory owes, and a missing image is a
		packaging decision no factory can make on the operator's behalf (ADR-0005). A
		single "missing" list would make the report's actionable items and its
		open decisions one indistinguishable set.
		"""
		return tuple(a for a in self.artifacts if a.kind in UNPRODUCIBLE_KINDS)

	@property
	def missing_artifacts_factory_owes(self) -> tuple[DeliveryArtifact, ...]:
		"""The missing artefacts that are not one of :attr:`undecided_artifacts`.

		This is the set the delivery-artefact check is scoped to. A check over all four
		kinds could never pass, and a gate that cannot pass is one an operator learns to
		bypass — which would turn off the part of the check that does matter.
		"""
		return tuple(a for a in self.missing_artifacts if a.kind not in UNPRODUCIBLE_KINDS)

	@property
	def complete(self) -> bool:
		"""Whether every artefact FR-117 names exists. Not whether the delivery is sound."""
		return not self.missing_artifacts

	@property
	def broken_links(self) -> tuple[TraceLink, ...]:
		"""Chain entries missing a hop, so the traceability claim is not whole (FR-117)."""
		return tuple(link for link in self.chain if not link.is_whole)

	@property
	def value_statement(self) -> str:
		"""FR-086's statement, which is the same sentence on every report ever rendered."""
		return self.VERIFIED_NOT_VALUE

	@property
	def passed(self) -> bool:
		"""Whether the machine half holds. The deploy gate's human half is separate (FR-119)."""
		return all(check.passed for check in self.checks)

	@property
	def failed(self) -> tuple[GateCheck, ...]:
		"""Machine checks that did not hold."""
		return tuple(check for check in self.checks if not check.passed)


class DeliveryGate(View):
	"""P8's gate: FR-119's deploy gate, human and permanent.

	The same two-half shape as :class:`DecompositionGate` and :class:`SpecificationGate`,
	and FR-119 adds two properties the others do not have. It is **human** — the type
	refuses to be satisfied without a named approver, so no code path can deploy. And it
	is **permanent**: the report it presented is named by id, so a later delivery cannot
	be approved against an earlier report's checks, which is the stale-evidence mistake
	FR-006 refuses one phase earlier and the one a deploy gate can least afford.
	"""

	report_id: UUID7
	checks: tuple[GateCheck, ...]
	report: DeliveryReport
	approved_by: NonEmptyStr | None = None
	approved_at: datetime | None = None

	@model_validator(mode="after")
	def _the_gate_presents_the_report_it_approved(self) -> Self:
		if self.report.id != self.report_id:
			raise ValueError(
				f"the deploy gate names report {self.report_id} and carries {self.report.id}: "
				"a gate that approved one report and shows another is not a gate (FR-119)"
			)
		if (self.approved_by is None) != (self.approved_at is None):
			raise ValueError("an approval names both who approved it and when")
		return self

	@property
	def failed(self) -> tuple[GateCheck, ...]:
		"""Machine checks that did not hold."""
		return tuple(check for check in self.checks if not check.passed)

	@property
	def is_approved(self) -> bool:
		"""Whether a human has passed this deploy gate (FR-119)."""
		return self.approved_by is not None

	@property
	def is_satisfied(self) -> bool:
		"""Whether the system may be deployed. Both halves, and never automatically (§1.5).

		The machine half is not negotiable by approving, for the reason
		:class:`DecompositionGate` gives: approval cannot make an unsound artefact sound.
		"""
		return not self.failed and self.is_approved


class DeployRecord(View):
	"""One deploy decision, recorded (FR-119, §1.5).

	Deploy is never automatic, so this row exists to be the *evidence* of a human act
	rather than the act itself. It carries the report it approved and the gate's own
	checks, so a reader can see what the approver was shown — a record that named only
	who approved would make "the gate presented the report" an assertion.
	"""

	id: UUID7
	goal_id: UUID7
	report_id: UUID7
	gate: DeliveryGate
	deployed_by: NonEmptyStr
	deployed_at: datetime
	note: NonEmptyStr | None = None

	@model_validator(mode="after")
	def _a_deploy_is_approved(self) -> Self:
		if not self.gate.is_satisfied:
			raise ValueError(
				"a deploy record over an unsatisfied gate: FR-119 makes deploy a human, "
				"permanent decision and §1.5 makes it never automatic"
			)
		if self.gate.report_id != self.report_id:
			raise ValueError("the deploy record and its gate name different reports")
		return self


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


DEFAULT_RESEARCH_SOURCES_PER_CLAUSE: Final = 5
"""FR-072's source bound, per intent clause.

Five because the loop SoFact delegates to advertises "must call the search tool at
least 5 times" ([S25]) — so this is the producer's own floor read back as a ceiling,
which is the one number here that is not SoFact's invention. A clause that needs more
than five sources is a clause whose premise is not a single question, and the
operator's answer to that is to override this, not to widen it silently.
"""

DEFAULT_RESEARCH_SECONDS_PER_CLAUSE: Final = 300.0
"""FR-072's time bound, per intent clause, **enforced** by killing the process.

Larger than the extension's own ceiling (240 s deep, 360 s super, [S25]) on purpose:
this is the outer envelope, and the inner ceiling is what binds first on a local
model. A bound set below the producer's own would report SoFact's cap as the cause of
a truncation the extension caused.
"""

DEFAULT_RESEARCH_CALLS_PER_CLAUSE: Final = 5
"""FR-072's model-call bound, per intent clause, **observed** from the loop's own meta.

Measured against the meta's ``turns``, which is the loop's own count of model turns
([S25]). Recorded rather than enforced: a cap the producer's runtime honours is the
producer grading its own spend (FR-140).
"""


class ResearchBudget(View):
	"""FR-072's declared bound on one research run, expressed **per intent clause**.

	Three quantities and no others, because the spec names three: sources, time, and
	model calls. Per clause rather than per run because a goal with more clauses has
	more to check, and one flat ceiling would bound a one-clause goal and an
	eight-clause one identically — which is a bound on the *goal*, not on the research.

	The three are not handled alike, and the split is FR-140's. Wall clock is
	**enforced**: SoFact holds the timeout, so exceeding it kills the process. Sources
	and model calls can only be **observed** from the artefacts the loop left, so
	exceeding one is recorded as a violation rather than prevented. A cap enforced
	inside the producer's own runtime would be the producer grading its own spend, and
	a budget the producer can raise is not a budget.
	"""

	max_sources_per_clause: int = DEFAULT_RESEARCH_SOURCES_PER_CLAUSE
	max_wall_clock_seconds_per_clause: float = DEFAULT_RESEARCH_SECONDS_PER_CLAUSE
	max_model_calls_per_clause: int = DEFAULT_RESEARCH_CALLS_PER_CLAUSE

	@model_validator(mode="after")
	def _every_cap_bounds_something(self) -> Self:
		"""A zero cap is not a tight budget, it is a refusal to research.

		Refused at construction because the alternative is worse than an error: a zero
		here multiplies to a whole-run allowance of zero, so every run violates its
		budget and the violation stops meaning anything. An operator who wants no
		research does not dispatch one.
		"""
		for label, value in (
			("source cap", self.max_sources_per_clause),
			("model-call cap", self.max_model_calls_per_clause),
			("wall-clock cap", self.max_wall_clock_seconds_per_clause),
		):
			if value <= 0:
				raise ValueError(
					f"research {label} must be positive, got {value}: a zero cap is a "
					"refusal to research wearing a budget's clothes (FR-072)"
				)
		return self

	def scaled(self, intent_clauses: int) -> ResearchAllowance:
		"""The whole-run allowance for a goal of ``intent_clauses`` clauses (FR-072).

		Refuses a count below one rather than defaulting it, so the substitution — *a
		goal with no draft yet is one subject* — is made by the caller that can see the
		goal and can say so in the record, not hidden in an arithmetic helper.
		"""
		if intent_clauses < 1:
			raise ValueError(
				f"cannot scale a per-clause budget by {intent_clauses} clauses: a run with "
				"no subject has no bound to be given (FR-072)"
			)
		return ResearchAllowance(
			intent_clauses=intent_clauses,
			max_sources=self.max_sources_per_clause * intent_clauses,
			max_wall_clock_seconds=self.max_wall_clock_seconds_per_clause * intent_clauses,
			max_model_calls=self.max_model_calls_per_clause * intent_clauses,
		)


class ResearchAllowance(View):
	"""One run's totals: the per-clause budget multiplied by the clause count (FR-072).

	A type of its own rather than three more fields on the budget, because the two are
	different quantities and a reader must not have to infer which one a number is. "5
	sources per clause" is a declaration; "40 sources for this run" is the figure the
	run is measured against. One field carrying both would make those the same
	sentence, and the record would no longer say which the operator declared.
	"""

	intent_clauses: int
	"""How many clauses the budget was multiplied by.

	``1`` when the elicitation has not produced a draft: a goal with no clauses yet is
	one subject, and the alternative — an allowance of zero — would make the first
	research run on a fresh goal violate its own budget by construction.
	"""

	max_sources: int
	max_wall_clock_seconds: float
	max_model_calls: int


class ResearchRecord(View):
	"""One research dispatch (FR-167) and what it left behind.

	The record keeps the report a **fact about an artefact**, not a verdict about
	research: ``report_chars`` and ``source_urls`` are measurements, and an empty
	``source_urls`` means *none were recorded*, never *none exist* (NFR-024). A
	truncated research loop and a completed one look different only in these numbers,
	which is why they are recorded at all.

	``budget_violations`` follows :class:`DispatchRecord`'s rule rather than inventing a
	second one: a fact about spend, not a verdict. A run that exceeded a cap is
	recorded as having exceeded it, and the fact that it produced a usable ledger is
	not overwritten by that — the two are different statements (FR-138, FR-072).
	"""

	id: UUID7
	goal_id: UUID7
	query: str
	harness: str
	mode: ResearchMode
	argv: tuple[str, ...]
	workspace: str
	budget: ResearchBudget = ResearchBudget()
	allowance: ResearchAllowance | None = None
	"""What this run was measured against (FR-072).

	``None`` only on a record written before budgets existed. Every record this build
	produces carries one, because the alternative — measuring a run against nothing —
	is the state FR-072 exists to remove.
	"""

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
	model_calls_observed: int | None = None
	"""The loop's own turn count, read from ``research-meta.json`` (FR-072, [S25]).

	``None`` means *not observed*, never *zero* — a truncated loop that wrote no meta
	is a run whose call count nobody measured, and rounding that to zero would report
	the cheapest possible run (NFR-024).
	"""

	budget_violations: tuple[str, ...] = ()
	note: str | None = None

	@property
	def is_within_budget(self) -> bool:
		"""True when no cap was exceeded. A *fact about spend*, not a verdict (FR-072)."""
		return not self.budget_violations


class VerificationStatus(StrEnum):
	"""How much of a source was actually checked (FR-069).

	The legend ``docs/sources/README.md`` already uses, promoted to a type because the
	distinction it draws is the whole point of the field: *content-verified* means the
	text was read, *url-verified* means the link resolved, *reported* means neither, and
	*unresolved-url* means the content was seen but its address was never captured.
	Collapsing these into a boolean ``verified`` would let a source that resolved be
	cited as though it had been read — the exact substitution the legend exists to
	prevent.
	"""

	CONTENT_VERIFIED = "content-verified"
	URL_VERIFIED = "url-verified"
	REPORTED = "reported"
	REPORTED_VIA_SECONDARY = "reported-via-secondary"
	UNRESOLVED_URL = "unresolved-url"


class SourcePosture(StrEnum):
	"""Whose interest a source serves (FR-074).

	``EVIDENCE`` is a source whose content a decision may rest on. ``POSITIONING`` is
	vendor content, a manifesto, or marketing: it is *recorded* — a market claim is a
	fact about the market — but it cannot support a decision alone, which is why the
	refusal lives in :meth:`SourceLedger.unbacked_decisions` rather than in a warning.
	"""

	EVIDENCE = "evidence"
	POSITIONING = "positioning"


class ClaimKind(StrEnum):
	"""What role a claim plays in the argument (FR-068, FR-071).

	``SUPPORTING`` and ``DISCONFIRMING`` are the two directions FR-071 asks the research
	phase to distinguish, and keeping them a typed field rather than a sign convention in
	prose is what makes the disconfirming count a measurement rather than a reading.
	``REFUTED`` is a claim the ledger itself no longer holds up — a superseded figure,
	a claim whose only source turned out to be positioning — and it is kept rather than
	deleted for the reason the log keeps everything: the record of having believed
	something is part of how the current belief is read.
	"""

	SUPPORTING = "supporting"
	DISCONFIRMING = "disconfirming"
	REFUTED = "refuted"


class Claim(View):
	"""One addressable statement in the source ledger (FR-070).

	Addressable means the claim has an id and a source points at it, so a claim can be
	invalidated without editing the source that carried it and a source can be
	invalidated without deleting the claims it carried. Those two operations are the
	reason this is a separate type from :class:`Source` rather than a list of strings
	inside one: FR-070's requirement is that "invalidating a source invalidates the
	claims resting on it", and that is a graph edge, not a sentence.

	``opinion`` is FR-069's label, and it is not a weaker kind of claim — it is a claim
	with no source that is *allowed to exist* and *not allowed to support a decision*.
	An uncited assertion recorded as opinion is honest; the same assertion recorded as
	supporting is the failure the field prevents.
	"""

	id: NonEmptyStr
	statement: NonEmptyStr
	kind: ClaimKind = ClaimKind.SUPPORTING
	opinion: bool = False
	"""True when no source backs this. An opinion may be recorded and may not decide."""

	source_ids: tuple[NonEmptyStr, ...] = ()
	"""The sources this claim rests on. Empty is legal and means *unsupported*."""

	superseded_by: NonEmptyStr | None = None
	"""The claim that replaced this one, when one did (FR-073, FR-075)."""

	expires: date | None = None
	"""When this claim stops being safe to cite (FR-075). ``None`` for a durable claim."""

	@model_validator(mode="after")
	def _an_opinion_rests_on_nothing(self) -> Self:
		if self.opinion and self.source_ids:
			raise ValueError(
				f"claim {self.id!r} is labelled opinion and cites {len(self.source_ids)} "
				"source(s): a claim either rests on evidence or it is the operator's "
				"reading, and a record that claims both is unreadable (FR-069)"
			)
		return self


class Contradiction(View):
	"""Two cited sources that disagree, and where (FR-073).

	Recorded rather than resolved. The spec is explicit that a contradiction is "where
	the operator's decision actually is", so a machine that picked a winner would be
	answering the one question the phase exists to hand over.
	"""

	id: NonEmptyStr
	statement: NonEmptyStr
	"""What the two sources disagree *about*, in the ledger's own words."""

	source_ids: tuple[NonEmptyStr, ...]
	resolution: NonEmptyStr | None = None
	"""The operator's ruling, when one was given. ``None`` means the disagreement stands
	and is still the operator's to settle — which is a real state, not an omission."""

	@model_validator(mode="after")
	def _a_contradiction_names_at_least_two(self) -> Self:
		if len(self.source_ids) < 2:
			raise ValueError(
				f"contradiction {self.id!r} names {len(self.source_ids)} source(s): a "
				"source cannot disagree with itself (FR-073)"
			)
		return self


class Source(View):
	"""One entry in the versioned source ledger (FR-070).

	Every field here exists because the hand-built ledger in ``docs/sources/`` needed it
	— the spec calls that ledger the reference implementation of this phase, so the
	automation is a transcription of a structure that was already proven by use, not an
	invention. ``precis`` and ``critique`` are the two body sections that carried the most
	weight there: what the source says, and why it might be wrong.
	"""

	id: NonEmptyStr
	"""Stable citation key (``S01``…). What a claim points at, so it is not a slug."""

	slug: NonEmptyStr
	title: NonEmptyStr
	type: NonEmptyStr
	url: str | None = None
	retrieved: date | None = None
	verification: VerificationStatus = VerificationStatus.REPORTED
	confidence: NonEmptyStr
	posture: SourcePosture = SourcePosture.EVIDENCE
	precis: NonEmptyStr
	critique: NonEmptyStr
	"""The information-quality critique (FR-070). Required, because a ledger without one
	is a list of links: the value of the entry is the judgement about the source, not the
	source."""

	expires: date | None = None
	"""When this source stops being safe to cite (FR-075), for a source that drifts."""

	superseded_by: NonEmptyStr | None = None

	@model_validator(mode="after")
	def _a_positioning_source_is_not_evidence(self) -> Self:
		if self.posture is SourcePosture.POSITIONING and self.verification is (
			VerificationStatus.CONTENT_VERIFIED
		):
			raise ValueError(
				f"source {self.id!r} is positioning and content-verified: reading vendor "
				"content carefully does not make it evidence, and recording it as both is "
				"how a marketing claim acquires a citation (FR-074)"
			)
		return self


class SourceLedger(View):
	"""The versioned source ledger for one research run (FR-070, FR-069).

	Sources and claims are held together but addressed separately, which is the shape
	FR-070 asks for and the reason both live here rather than inside
	:class:`ResearchRecord`: the record is a measurement of a *dispatch*, and this is the
	artefact the dispatch was supposed to produce.
	"""

	version: int = 1
	"""FR-070's *versioned*. Bumped when a run re-states a ledger already on the log."""

	goal_id: UUID7
	query: NonEmptyStr
	sources: tuple[Source, ...] = ()
	claims: tuple[Claim, ...] = ()
	contradictions: tuple[Contradiction, ...] = ()
	"""Where two cited sources disagree (FR-073). A field rather than a check, because
	an empty tuple is the finding "none were detected" and a missing field is no finding
	at all."""

	@model_validator(mode="after")
	def _ids_are_unique(self) -> Self:
		for label, ids in (
			("source", [s.id for s in self.sources]),
			("claim", [c.id for c in self.claims]),
		):
			duplicates = sorted({i for i in ids if ids.count(i) > 1})
			if duplicates:
				raise ValueError(
					f"duplicate {label} id(s) {duplicates}: an address that names two "
					"things addresses neither (FR-070)"
				)
		return self

	@model_validator(mode="after")
	def _every_link_resolves(self) -> Self:
		known_sources = {s.id for s in self.sources}
		known_claims = {c.id for c in self.claims}
		for claim in self.claims:
			missing = sorted(set(claim.source_ids) - known_sources)
			if missing:
				raise ValueError(
					f"claim {claim.id!r} cites unknown source(s) {missing}: a claim resting "
					"on a source the ledger does not hold cannot be invalidated with it, "
					"which is the whole point of the edge (FR-070)"
				)
			if claim.superseded_by is not None and claim.superseded_by not in known_claims:
				raise ValueError(
					f"claim {claim.id!r} is superseded by {claim.superseded_by!r}, which the "
					"ledger does not hold"
				)
		for source in self.sources:
			if source.superseded_by is not None and source.superseded_by not in known_sources:
				raise ValueError(
					f"source {source.id!r} is superseded by {source.superseded_by!r}, which "
					"the ledger does not hold"
				)
		for found in self.contradictions:
			unknown = sorted(set(found.source_ids) - known_sources)
			if unknown:
				raise ValueError(f"contradiction {found.id!r} names unknown source(s) {unknown}")
		return self

	@property
	def disconfirming(self) -> tuple[Claim, ...]:
		"""Claims that argue *against* the premise (FR-071).

		The count of these is what makes a rationalisation engine detectable: a research
		phase that only ever finds support has a disconfirming count of zero, and a zero
		that is a measurement is a finding while a zero that is an absence is not.
		"""
		return tuple(c for c in self.claims if c.kind is ClaimKind.DISCONFIRMING)

	@property
	def unbacked_decisions(self) -> tuple[Claim, ...]:
		"""Claims that must not decide anything on their own (FR-069, FR-074).

		An opinion with no source, or a supporting claim whose every source is
		positioning. Both are recorded and both are refused as grounds for a decision —
		which is FR-074's "prevented from supporting a decision on their own", made
		checkable rather than advised.
		"""
		posture = {s.id: s.posture for s in self.sources}
		unbacked: list[Claim] = []
		for claim in self.claims:
			if claim.kind is ClaimKind.REFUTED or claim.opinion:
				unbacked.append(claim)
				continue
			if claim.source_ids and all(
				posture.get(sid) is SourcePosture.POSITIONING for sid in claim.source_ids
			):
				unbacked.append(claim)
		return tuple(unbacked)

	def source(self, source_id: str) -> Source | None:
		"""One source by id, or ``None``. The addressable read FR-070 asks for."""
		return next((s for s in self.sources if s.id == source_id), None)

	def claim(self, claim_id: str) -> Claim | None:
		"""One claim by id, or ``None``."""
		return next((c for c in self.claims if c.id == claim_id), None)

	def resting_on(self, source_id: str) -> tuple[Claim, ...]:
		"""Every claim whose validity depends on ``source_id`` (FR-070).

		This is the derivation FR-070's requirement names: invalidating a source
		invalidates the claims resting on it, and that set has to be computable rather
		than remembered. A claim citing two sources rests on both, so this is a *set* of
		dependants, not a partition of the claims.
		"""
		return tuple(c for c in self.claims if source_id in c.source_ids)

	def expired(self, as_of: date) -> tuple[Source | Claim, ...]:
		"""Sources and claims past their expiry on ``as_of`` (FR-075).

		Time-sensitive claims are the ones that rot: model landscapes and vendor terms
		change fastest of anything in this domain. A ledger that cannot say which of its
		entries have gone stale is a ledger whose figures are all equally trustworthy,
		which is the state FR-075 exists to prevent.
		"""
		stale: list[Source | Claim] = []
		stale.extend(s for s in self.sources if s.expires is not None and s.expires < as_of)
		stale.extend(c for c in self.claims if c.expires is not None and c.expires < as_of)
		return tuple(stale)


class ResearchVerdict(StrEnum):
	"""What research concluded about one intent clause (FR-068).

	Four members and no fifth, because the spec's table gives each one a *different
	action*: a verdict whose action is the same as another's is a distinction that costs
	a word and buys nothing. The action is not prose here — it is
	:data:`VERDICT_ACTION`, read by the CLI and by the P1 completion rule, so a clause
	the evidence contradicts cannot be advanced past by a reader who skipped a paragraph.
	"""

	VALIDATED = "validated"
	INVALIDATED = "invalidated"
	UNVERIFIABLE = "unverifiable"
	DEEPENED = "deepened"


VERDICT_ACTION: dict[ResearchVerdict, str] = {
	ResearchVerdict.VALIDATED: "proceed",
	ResearchVerdict.INVALIDATED: "return to P0: the premise is contradicted and must not be built",
	ResearchVerdict.UNVERIFIABLE: "proceed as an explicitly flagged assumption",
	ResearchVerdict.DEEPENED: "return to P0: revise the clauses the evidence reframed",
}
"""FR-068's action column, as data.

A dict rather than a method so the P1 completion rule, the gate and the CLI all read
the *same* table: three call sites each spelling out "invalidated means stop" is how one
of them comes to disagree with the spec.
"""


class ClauseClassification(View):
	"""One intent clause, classified by the research phase with its evidence (FR-068).

	``evidence`` is where FR-068's "with cited evidence" is enforced, and it is enforced
	*in both directions*: a verdict of Validated, Invalidated or Deepened with no source
	cited is a judgement the ledger cannot check, and a verdict of Unverifiable that
	cites a source contradicts itself — "no evidence either way" is a statement about the
	absence of evidence, and a record holding both is unreadable.

	``settled_by`` is what makes Unverifiable's action ("proceed as an explicitly flagged
	assumption") more than a shrug. FR-079 requires every assumption to name the
	observation that would show it false, so an unverifiable clause has to say what would
	settle it; without that field the flagged assumption would be unfalsifiable and P2
	would refuse it. The field is refused on the other three verdicts rather than ignored
	— a producer's judgement that the reader silently drops is worse than a producer's
	error the reader reports, which is the same rule the ledger's parser applies to an
	unknown key.
	"""

	clause_id: UUID7
	statement: NonEmptyStr
	"""The clause in its own words, as it read when it was classified. Carried rather
	than looked up, because P2 may revise the clause and the classification is evidence
	about the clause that *was* researched (FR-068's Deepened action)."""

	verdict: ResearchVerdict
	rationale: NonEmptyStr
	"""Why this verdict, in the researcher's words. Required: a verdict with no stated
	reason is a label, and FR-068 asks for a classification, not a tag."""

	evidence: tuple[NonEmptyStr, ...] = ()
	"""Source ids from the ledger that decided this. Empty only for Unverifiable."""

	settled_by: NonEmptyStr | None = None
	"""What observation would settle an Unverifiable clause. Required there, refused
	elsewhere."""

	@model_validator(mode="after")
	def _the_evidence_matches_the_verdict(self) -> Self:
		if self.verdict is ResearchVerdict.UNVERIFIABLE:
			if self.evidence:
				raise ValueError(
					f"clause {self.clause_id} is unverifiable and cites "
					f"{len(self.evidence)} source(s) {list(self.evidence)}: *no evidence "
					"either way* is a statement about the absence of evidence, and a "
					"classification holding both is unreadable (FR-068)"
				)
			if self.settled_by is None:
				raise ValueError(
					f"clause {self.clause_id} is unverifiable and names nothing that would "
					"settle it: FR-068's action is to proceed *as an explicitly flagged "
					"assumption*, and FR-079 refuses an assumption with no refuting "
					"observation (FR-068, FR-079)"
				)
			return self
		if not self.evidence:
			raise ValueError(
				f"clause {self.clause_id} is {self.verdict.value} with no source cited: "
				"FR-068 requires cited evidence, and a verdict the ledger cannot check is "
				"an opinion wearing a verdict's name (FR-068, FR-069)"
			)
		if self.settled_by is not None:
			raise ValueError(
				f"clause {self.clause_id} is {self.verdict.value} and names what would "
				f"settle it ({self.settled_by!r}): that field is how an *unverifiable* "
				"clause becomes a falsifiable assumption, and a reader that ignored it "
				"here would drop a judgement the producer made (FR-068)"
			)
		return self

	@property
	def action(self) -> str:
		"""What FR-068's table says to do about this verdict."""
		return VERDICT_ACTION[self.verdict]

	@property
	def returns_to_p0(self) -> bool:
		"""Whether this verdict sends the pipeline back (FR-068).

		Invalidated and Deepened both do, for different reasons — one says the premise is
		false, the other says the premise was the wrong question — and both mean the
		clauses must be revised before anything is built on them.
		"""
		return self.verdict in (ResearchVerdict.INVALIDATED, ResearchVerdict.DEEPENED)

	@property
	def flagged_assumption(self) -> Assumption | None:
		"""This clause as the assumption FR-068's Unverifiable action carries into P2.

		``None`` for the other three verdicts. The assumption's ``refuted_by`` is
		``settled_by``, which the validator above guarantees is present — so an
		unverifiable clause cannot reach P2 as an unfalsifiable belief.
		"""
		if self.verdict is not ResearchVerdict.UNVERIFIABLE or self.settled_by is None:
			return None
		return Assumption(
			id=uuid7str(),
			statement=f"Unverified premise (FR-068): {self.statement}",
			refuted_by=self.settled_by,
		)


class ResearchClassification(View):
	"""P1's second artefact: a verdict on every intent clause (FR-068).

	The ledger (FR-070) is what the research *found*; this is what it *concluded about
	the goal*. They are separate types because they fail separately — a ledger can be
	complete and the conclusion wrong, and a classification citing a source the ledger
	does not hold is a conclusion resting on nothing. FR-062's "every phase emits a
	durable artifact" is satisfied by the pair, and FR-068 is the half that had no type
	until now.
	"""

	version: int = 1
	"""FR-070's versioning rule, applied to the conclusions. A re-classification after a
	return to P0 is a new record rather than an edit to the old one, because the old one
	is *why* the pipeline went back."""

	goal_id: UUID7
	query: NonEmptyStr
	classifications: tuple[ClauseClassification, ...]

	@model_validator(mode="after")
	def _every_clause_is_classified_once(self) -> Self:
		if not self.classifications:
			raise ValueError(
				"a classification with no clauses classifies nothing: FR-068 asks for a "
				"verdict on every intent clause (FR-068)"
			)
		ids = [c.clause_id for c in self.classifications]
		duplicates = sorted({i for i in ids if ids.count(i) > 1})
		if duplicates:
			raise ValueError(
				f"clause(s) {duplicates} classified more than once: two verdicts on one "
				"premise means the reader picks, and the pick is the research (FR-068)"
			)
		return self

	@property
	def invalidated(self) -> tuple[ClauseClassification, ...]:
		"""Clauses the evidence contradicts. FR-068: do not build."""
		return tuple(c for c in self.classifications if c.verdict is ResearchVerdict.INVALIDATED)

	@property
	def deepened(self) -> tuple[ClauseClassification, ...]:
		"""Clauses the evidence reframed. FR-068: revise the clauses."""
		return tuple(c for c in self.classifications if c.verdict is ResearchVerdict.DEEPENED)

	@property
	def unverifiable(self) -> tuple[ClauseClassification, ...]:
		"""Clauses with no evidence either way — the flagged assumptions."""
		return tuple(c for c in self.classifications if c.verdict is ResearchVerdict.UNVERIFIABLE)

	@property
	def returns_to_p0(self) -> tuple[ClauseClassification, ...]:
		"""Clauses that send the pipeline back to P0 (FR-068).

		Read through :attr:`ClauseClassification.returns_to_p0` rather than by comparing
		verdicts here, so "which verdicts stop the pipeline" is written down once.
		"""
		return tuple(c for c in self.classifications if c.returns_to_p0)

	@property
	def flagged_assumptions(self) -> tuple[Assumption, ...]:
		"""Every Unverifiable clause as a falsifiable assumption for P2 (FR-068, FR-079)."""
		return tuple(a for c in self.classifications if (a := c.flagged_assumption) is not None)

	def unclassified(self, clause_ids: frozenset[str]) -> tuple[str, ...]:
		"""Clauses the draft holds that this classification does not name (FR-068).

		The direction FR-068's "every intent clause" needs, and the same two-way rule
		:meth:`Specification.uncovered_clauses` applies one phase later. A method rather
		than a validator because the type cannot see the draft it was written against.
		"""
		return tuple(sorted(clause_ids - {c.clause_id for c in self.classifications}))

	def classification(self, clause_id: str) -> ClauseClassification | None:
		"""One clause's verdict, or ``None``. The addressable read FR-068 implies."""
		return next((c for c in self.classifications if c.clause_id == clause_id), None)


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
	worktree: str | None = None
	"""The directory this step's session ran in, when it was given its own (FR-141).

	``None`` means the session ran in the shared workspace on its branch, which is the
	sequential path: with one writer there is nothing to isolate it from. A path means the
	session had a checkout of its own, so a sibling step's files were not present in it and
	this step's files were not present in the sibling's.

	The path stays after the worktree has been integrated and removed, because it is a
	record of *where the session ran* rather than of what exists now — the same way
	``workspace`` names a directory rather than asserting one is there. Whether the
	directory is still live is answered by ``integrated_commit``, not by this field.

	This is **containment, not confinement**. Measured (ADR-0023), neither ``pi`` nor
	``claude`` confines its child to its working directory, so a producer that wanders
	escapes a worktree exactly as easily as it escapes a shared tree. What a worktree buys
	is that a session that stays put cannot collide with its sibling — and that is the
	whole of what FR-141 can be without a container runtime (ADR-0005).
	"""
	integrated_commit: str | None = None
	"""The commit the integration line reached when this worktree was merged back.

	Set only by :func:`~sofact.git.integrate_worktree`. ``None`` on a worktree checkout
	means no merge has been recorded, which is the normal state while the session is
	running and the *abnormal* state afterwards — a worktree that was never merged is work
	the next wave cannot see, and P7's build-order check reads this field to say so. A
	session that changed nothing also leaves it ``None``, because there was nothing to
	merge; ``sealed_commit`` and ``head_commit`` both being ``None`` is what tells that
	case apart from a merge that never happened.
	"""
	merge_conflict: bool = False
	"""Whether the merge back onto the integration line conflicted and was aborted.

	A conflict is a recorded outcome, not an error: two concurrent steps that touched one
	file are a real scheduling result, and reporting it as a crash would lose the
	distinction between a factory that cannot merge and two modules that genuinely
	overlap. The merge is aborted rather than left half-applied, so the workspace stays a
	tree a human can reason about.
	"""
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
		if self.integrated_commit is not None and self.worktree is None:
			raise ValueError(
				"only a worktree checkout has a merge to report: "
				f"worktree={self.worktree!r} integrated={self.integrated_commit!r}"
			)
		if self.merge_conflict and self.integrated_commit is not None:
			raise ValueError(
				"an aborted merge does not leave the integration line at a commit: "
				f"integrated={self.integrated_commit!r}"
			)
		if self.integrated_commit is not None and self.head_commit != self.integrated_commit:
			raise ValueError(
				"a merge that succeeded leaves the integration line at the branch tip: "
				f"head={self.head_commit!r} integrated={self.integrated_commit!r}"
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
	RESEARCH_CLASSIFIED = "research.classified"
	SOURCE_LEDGER_RECORDED = "source_ledger.recorded"
	REPAIR_ATTEMPTED = "repair.attempted"
	DECOMPOSITION_PROPOSED = "decomposition.proposed"
	DECOMPOSITION_GATED = "decomposition.gated"
	SPECIFICATION_PROPOSED = "specification.proposed"
	SPECIFICATION_GATED = "specification.gated"
	PHASE_ADVANCED = "phase.advanced"
	CUT_RECORDED = "cut.recorded"
	DELIVERY_RENDERED = "delivery.rendered"
	DEPLOY_RECORDED = "deploy.recorded"
	GATE_COST_RECORDED = "gate_cost.recorded"


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


class Cut(View):
	"""An operator's decision to read the log as of an earlier entry (FR-094, FR-003).

	A *reading rule*, not a deletion. FR-003 makes the log append-only and the chain is
	what makes it tamper-evident, so history is not erasable here — and truncating the
	file would destroy the evidence that the rolled-back work ever happened, which is
	the one thing an operator rolling back most needs to keep. So the cut is recorded
	in the log it cuts, and the fold applies it.

	The rule is "read through ``target_index``, then resume after the cut row": entries
	after the target *and* before the cut are skipped, and everything the operator does
	next is folded normally. Without that second half a cut would be a permanent
	dead-end — the project could never make progress again — and with it a cut is
	exactly "the state as of entry N, plus whatever has happened since I decided that".

	The **latest** cut wins. Cutting again to a later entry un-does the first, because
	that is what "read as of entry M" means and a stack of cuts whose effects compose
	would make the current state depend on a history of decisions rather than on one.
	"""

	target_index: int
	"""The last entry index the state is read *through*, inclusive."""

	at: datetime
	by: NonEmptyStr
	"""Who cut: an operator verb, so this is a name rather than ``factory``."""

	reason: NonEmptyStr
	"""Why, in the operator's words. A cut with no reason is an unexplained gap in
	the state, and the next reader has no way to tell it from a bug."""

	@model_validator(mode="after")
	def _index_is_real(self) -> Self:
		if self.target_index < 0:
			raise ValueError(f"a cut target must be a real entry index, got {self.target_index}")
		return self


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
	cuts: tuple[Cut, ...] = ()
	deliveries: tuple[DeliveryReport, ...] = ()
	"""Every delivery report the log records, oldest first (FR-117).

	Versioned like the ledger and the classification, and for a stronger reason: a
	delivery report is what a deploy gate presented, so superseding one must not erase
	what an approver was shown. The operative one is :attr:`delivery`.
	"""

	deploys: tuple[DeployRecord, ...] = ()
	"""Every deploy decision, oldest first (FR-119). Appended, never superseded: §1.5
	makes deploy a permanent human act, and a second deploy is a second act rather than
	an amendment of the first."""

	gate_costs: tuple[GateCost, ...] = ()
	"""What each human gate cost, oldest first (FR-160). Appended and never keyed.

	Two recordings of one gate are two measurements, not an edit: the second is either a
	correction — in which case the history of what was first claimed is itself the
	datum §20.3 wants — or a re-measurement after rework, which is a different cost.
	:meth:`gate_cost` reads the latest, and the sum over all of them would be wrong, so
	the accessor is the only intended reader.
	"""

	def gate_cost(self, gate: PhaseGate) -> GateCost | None:
		"""The most recent recorded cost for one gate, if any (FR-160)."""
		matching = [c for c in self.gate_costs if c.gate is gate]
		return matching[-1] if matching else None

	@property
	def total_human_minutes(self) -> float | None:
		"""§1.3's human-minutes actual: the sum over gates that were measured (FR-160).

		``None`` when no gate has recorded a cost, which is a different statement from
		zero — the distinction :func:`sofact.envelope.measure` draws for every other
		dimension, and the one that matters most here: a factory that reported 0 minutes
		would be reporting that its gates were free.

		Summed over the *latest* cost per gate rather than over every row, because two
		rows for one gate are one gate's cost recorded twice, and adding them would
		inflate the number that decides whether §1.4's economic claim holds.
		"""
		latest = [c for gate in PHASE_GATE.values() if (c := self.gate_cost(gate)) is not None]
		if not latest:
			return None
		return sum(c.human_minutes for c in latest)

	@property
	def delivery(self) -> DeliveryReport | None:
		"""The latest delivery report, or ``None`` (FR-117).

		The **latest**, for the reason :attr:`ledger` is: a re-rendered report supersedes
		the one before it, and the older one stays in ``deliveries`` because a deploy gate
		approved against it has to remain readable.
		"""
		return self.deliveries[-1] if self.deliveries else None

	@property
	def deploy(self) -> DeployRecord | None:
		"""The most recent deploy decision, or ``None`` (§1.5, FR-119)."""
		return self.deploys[-1] if self.deploys else None

	"""Every cut the log records, oldest first (FR-094).

	A collection like every other field, because that is what the log holds: rows. The
	*operative* rule is :attr:`cut`, and it is derived from this rather than stored
	beside it — two fields describing one decision is how a state comes to disagree
	with itself.
	"""

	research: tuple[ResearchRecord, ...] = ()
	ledgers: tuple[SourceLedger, ...] = ()
	"""Every source ledger the log records, oldest first (FR-070).

	A collection rather than one field, because FR-070's ledger is *versioned*: a later
	run that re-states the same ground appends a new ledger rather than editing the old
	one, exactly as the log itself does. The operative ledger is :attr:`ledger`, derived
	from this rather than stored beside it.
	"""

	classifications: tuple[ResearchClassification, ...] = ()
	"""Every per-clause classification the log records, oldest first (FR-068).

	Versioned for the same reason the ledger is, and for one more: a classification
	whose Invalidated verdict sent the pipeline back to P0 is the *reason* it went back,
	so superseding it must not erase it. The operative one is
	:attr:`classification`.
	"""

	@property
	def classification(self) -> ResearchClassification | None:
		"""The current per-clause classification, or ``None`` (FR-068).

		The **latest**, by log order, for the reason :attr:`ledger` is: a re-classification
		after a return to P0 supersedes the one that caused the return, and the older one
		stays in ``classifications`` because the record of what was concluded before is
		how the current conclusion is read.
		"""
		return self.classifications[-1] if self.classifications else None

	@property
	def ledger(self) -> SourceLedger | None:
		"""The current source ledger, or ``None`` before any research has been recorded.

		The **latest** ledger, by log order: a re-stated ledger supersedes the one before
		it for the same reason a re-answered elicitation dimension does (ADR-0007), and
		the older one stays in ``ledgers`` because the record of what was believed before
		is how the current belief is read.
		"""
		return self.ledgers[-1] if self.ledgers else None

	@property
	def cut(self) -> Cut | None:
		"""The rollback this state is read under, or ``None`` (FR-094, FR-003).

		The **latest** cut, because that is the only one whose rule the fold applies: a
		second cut to a later entry un-does the first, so naming the earliest would
		describe a rule the state was not folded under.

		A state folded under a cut is not the same object as one that genuinely stopped at
		that entry, and the difference is invisible in every other field — both have the
		same goals, the same contracts, the same reports. Without this, a rolled-back
		project and a project that simply never got further would be indistinguishable to
		every reader including the gates, which is exactly the confusion a rollback must
		not create.
		"""
		return self.cuts[-1] if self.cuts else None

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

	def deliveries_for(self, contract_id: str) -> tuple[DeliveryReport, ...]:
		"""Every delivery report rendered for a contract, in log order (FR-117)."""
		return tuple(d for d in self.deliveries if d.contract_id == contract_id)

	def deploys_for(self, report_id: str) -> tuple[DeployRecord, ...]:
		"""Every deploy decision recorded against one report (FR-119)."""
		return tuple(d for d in self.deploys if d.report_id == report_id)

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
