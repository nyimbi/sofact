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
from collections.abc import Iterable
from datetime import UTC, date, datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Any, ClassVar, Final, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, computed_field, model_validator

from sofact._uuid7 import uuid7str

__all__ = [
	"ATTEMPT_TELEMETRY_REQUIREMENTS",
	"AUDIT_REQUIREMENTS",
	"AUDIT_SAMPLE_FLOOR",
	"AUTHORSHIP_READING",
	"AUTHORSHIP_REQUIREMENTS",
	"CHANGE_COST_AXIS",
	"CHANGE_COST_BASELINE_UNMEASURED",
	"CHANGE_COST_NOT_A_VERIFICATION",
	"CHANGE_COST_PROXY_DECLARATION",
	"CHANGE_COST_REQUIREMENTS",
	"CHANGE_COST_RISE_FACTOR",
	"COMPOSITION_REQUIREMENTS",
	"ESCAPE_RATE_READING",
	"ESCAPE_REQUIREMENTS",
	"EVOLVABILITY_DEBT",
	"GOAL_CONTINUATION_UNMEASURED",
	"GOAL_ENTRY_NOT_FORCED",
	"GOAL_MODE_REQUIREMENTS",
	"HARNESS_SELECTION_REQUIREMENTS",
	"HIGHEST_GRANTABLE",
	"INTEGRATION_REQUIREMENTS",
	"INTENT_REQUIREMENTS",
	"L4_GATE_THETA",
	"MACHINE_API_VERSION",
	"MAINTAINABILITY_NOT_VERIFIED",
	"MODEL_ANSWER_PREFIX",
	"MODE_G_CEILING",
	"MODE_M_CEILING",
	"MODULE_CLASS_CEILING",
	"ORACLE_AUDIT_REQUIREMENTS",
	"ORACLE_RANK",
	"PERSONAL_AUTONOMY_BAND",
	"THETA_GATE_BUILT",
	"TOPOLOGY_ISOLATION",
	"TOPOLOGY_MODIFIER",
	"TUNED_MODEL_UNREACHABLE",
	"UNATTESTED_MARKER",
	"VERDICT_SURFACES",
	"AdversarialAuditReport",
	"AnswerProvenance",
	"Assumption",
	"AttemptTelemetry",
	"AttemptTelemetryReport",
	"AuthorshipCheck",
	"AuthorshipFinding",
	"AuthorshipSurface",
	"AutonomyLevel",
	"CapabilityFinding",
	"CapabilityKind",
	"ChangeCostReport",
	"ChangeCostRow",
	"ChangeFootprint",
	"ChangeUnit",
	"Claim",
	"ClaimKind",
	"Clause",
	"ClauseClassification",
	"ClauseKind",
	"ClauseStem",
	"ClauseVerdict",
	"ClauseVerdictProvenance",
	"CompetitiveLandscape",
	"CompletionClaim",
	"Consumer",
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
	"DeploymentScope",
	"DeploymentTopology",
	"DiffReview",
	"DimensionBound",
	"DimensionStatus",
	"DispatchMode",
	"DispatchRecord",
	"DriverOutcome",
	"DriverRun",
	"DriverStep",
	"DriverTerminal",
	"ElicitationAnswer",
	"ElicitationAttestation",
	"ElicitationDimension",
	"EnvelopeActuals",
	"EnvelopeDimension",
	"EnvelopeMeasurement",
	"EscapeAttribution",
	"EscapeBudget",
	"EscapeEvent",
	"EscapeKind",
	"EscapeOverride",
	"EscapeReport",
	"Evidence",
	"EvidenceKind",
	"ExceedsClaim",
	"ExploitFix",
	"GateCheck",
	"GateCost",
	"Goal",
	"GoalEntry",
	"GoalModeReport",
	"GoalModeRow",
	"GoalPlan",
	"GoalSpec",
	"GoalStep",
	"GoalStyle",
	"HackAttempt",
	"HackOutcome",
	"HackTechnique",
	"Handover",
	"HarnessCapability",
	"HarnessMetric",
	"HarnessProfile",
	"HarnessSelection",
	"IntegrationCheck",
	"IntegrationFinding",
	"IntegrationFindingKind",
	"IntegrationReport",
	"IntegrityCheck",
	"IntegrityOutcome",
	"IntegritySubject",
	"IntentEdge",
	"IntentGraph",
	"IntentHop",
	"IntentNode",
	"IntentNodeKind",
	"InterfaceMember",
	"InterfaceMemberKind",
	"LaneEscape",
	"LedgerEntry",
	"LedgerKind",
	"MachineEnvelope",
	"MachineOperation",
	"MachineRequest",
	"MaintenanceLane",
	"Module",
	"ModuleCheckout",
	"ModuleClass",
	"NonGoal",
	"Notification",
	"OracleAuditFinding",
	"OracleAuditReport",
	"OracleAuditSkip",
	"OracleClass",
	"OracleDeclaration",
	"Phase",
	"PhaseAdvance",
	"PhaseGate",
	"PhaseStatus",
	"PlanStepKind",
	"PluginAdmission",
	"PluginComposition",
	"PluginVerdict",
	"ProbeOutcome",
	"ProductSpecificationDocument",
	"ProjectState",
	"Readiness",
	"RepairAttempt",
	"RepairOutcome",
	"Requirement",
	"RequirementAnnotation",
	"ResearchAllowance",
	"ResearchBudget",
	"ResearchClassification",
	"ResearchMode",
	"ResearchRecord",
	"ResearchVerdict",
	"RivalCapability",
	"RivalSystem",
	"SearchHit",
	"SearchOutcome",
	"SearchQueryResult",
	"SearchScan",
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
	"SystemInterface",
	"SystemInvariant",
	"SystemModel",
	"SystemRelationship",
	"TraceLink",
	"Transcript",
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
	"lane_ceiling",
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


def is_uuid7(value: str) -> bool:
	"""Whether ``value`` is a UUID7, by the same validator :data:`UUID7` applies (FR-171).

	Public because a caller holding a producer's string — a research classification's
	evidence ids, which arrive as free text — has to decide whether it can go into a
	``UUID7`` field. Delegating to :func:`_uuid7` rather than re-testing the version keeps
	one definition of "is a UUID7"; a second check would drift the first time either was
	relaxed, and the two would then disagree about which ids are admissible.
	"""
	try:
		_uuid7(value)
	except ValueError:
		return False
	return True


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


class ManufactureRefusalReason(StrEnum):
	"""Why the factory built no oracle of a requested rank (FR-103, FR-105).

	A named reason rather than a message, because the *reason* is what decides the
	remedy: ``NO_STRUCTURED_SOURCE`` is retired by declaring the invariant,
	``NEEDS_A_REFERENCE_RUN`` by building first, and ``UNSUPPORTED_RANK`` by writing a
	backend. A caller given only prose has to re-derive which of those it is holding.

	Here rather than in :mod:`sofact.manufacture` because a refusal is *recorded*, and
	what the ledger folds has to be a :class:`View` — while ``manufacture`` imports
	``views`` and not the other way round. The enum lives beside :data:`ORACLE_RANK`,
	which is the table it is a statement about.
	"""

	HELD_OUT = "held_out"
	"""Rank 6. FR-106's holdout is the operator's example, so the factory manufactures none."""

	UNSUPPORTED_RANK = "unsupported_rank"
	"""This backend does not build this rank, and does not claim to."""

	NO_STRUCTURED_SOURCE = "no_structured_source"
	"""The rank needs a declaration the contract does not carry: an invariant, a transition
	relation, a field set. The clause is prose, and a predicate read out of prose is invented."""

	NO_DECLARED_SURFACE = "no_declared_surface"
	"""The module declares no public surface, so the check would quantify over nothing.

	FR-090 makes the surface the permitted set, and an empty one is a real state — a
	proposal derives nothing when the model declares no interfaces. Manufacturing against it
	would produce a check with an empty domain, which is satisfied by every tree including an
	empty one. Refusing is what keeps the empty domain from reading as a pass.
	"""

	NEEDS_A_REFERENCE_RUN = "needs_a_reference_run"
	"""Rank 7 records a reference run's output, and before P5 there is nothing to run.

	A golden captured now would be the digest of an empty tree, blessed as the expected
	value — FR-108's ground-truth debt, recorded as though it were coverage.
	"""

	ARTEFACT_OUTSIDE_WORKSPACE = "artefact_outside_workspace"
	"""The backend named a path the producer could reach and the factory did not write."""

	ARTEFACT_MISSING = "artefact_missing"
	"""The backend named a path it did not write."""

	COMMAND_NAMES_ANOTHER_FILE = "command_names_another_file"
	"""The command's artefact argument is not the path the backend wrote.

	Separate from :attr:`ARTEFACT_MISSING` because the remedy is different and the evidence
	is different. There the write is missing; here the write happened and the *command* points
	somewhere else, so the check that would run is not the check that was built — and a spec
	whose ``run_argv`` is wrong would produce this for every module while every artefact on
	disk looked correct.
	"""

	COMMAND_DID_NOT_RUN = "command_did_not_run"
	"""The command could not be launched, or did not terminate inside the timeout.

	Distinct from a command that ran and failed. "There is no interpreter here" and "the
	check ran and disagreed" need different repairs, and only the second is a verdict.
	"""

	VACUOUS = "vacuous"
	"""The check passed against a tree holding nothing but itself (FR-107).

	This is the refusal that matters. Every other one says the factory could not build a
	check; this one says it built a check that establishes nothing, which is the defect
	FR-107 calls "worse than a missing test".
	"""


class ManufactureRefusal(View):
	"""One clause the factory could not build a check for, and why (FR-105).

	Recorded rather than returned and dropped, because it is the fact that *explains* a
	clause's remaining ground-truth debt (FR-108): a reader holding only the debt knows
	that something could not be built and not what, and re-running manufacturing to find
	out would rewrite files to answer a question about a past state.

	``clause_id`` is what makes it actionable — the remedy is per clause, and a refusal
	that named only a reason would leave the operator to guess which clause to declare an
	invariant for.
	"""

	clause_id: UUID7
	oracle_class: OracleClass
	reason: ManufactureRefusalReason
	detail: NonEmptyStr

	contract_id: UUID7 | None = None
	"""The contract this refusal is filed against, once there is one.

	``None`` is the state a refusal is *born* in and it is not an oversight: manufacturing
	runs inside P4, before the contract exists, so the seam cannot know the id of the
	contract its refusal will end up explaining. The service fills it in when it files the
	refusal, and a refusal read with ``None`` is one that was never filed — the distinction
	FR-042 draws between "declared T1" and "nobody said", one phase along.
	"""

	@property
	def remedy(self) -> str:
		"""What would retire this refusal, in one sentence.

		Derived from the reason rather than stored, so a new reason is a type error here
		rather than a refusal the report renders with a blank line beside it.
		"""
		match self.reason:
			case ManufactureRefusalReason.HELD_OUT:
				return "supply the case yourself; FR-106's holdout is the operator's example"
			case ManufactureRefusalReason.UNSUPPORTED_RANK:
				return f"write a backend for {self.oracle_class.value}, or accept the debt"
			case ManufactureRefusalReason.NO_STRUCTURED_SOURCE:
				return (
					"declare the invariant, transition relation or field set it would quantify over"
				)
			case ManufactureRefusalReason.NO_DECLARED_SURFACE:
				return "declare an interface for this clause in the system model (FR-083)"
			case ManufactureRefusalReason.NEEDS_A_REFERENCE_RUN:
				return "build once, then record the reference run's output as the golden"
			case ManufactureRefusalReason.ARTEFACT_OUTSIDE_WORKSPACE:
				return "fix the backend: an artefact the producer can rewrite is not a check"
			case ManufactureRefusalReason.ARTEFACT_MISSING:
				return "fix the backend: it named a path and did not write it"
			case ManufactureRefusalReason.COMMAND_NAMES_ANOTHER_FILE:
				return "fix the spec's run argv: it names an artefact the backend did not write"
			case ManufactureRefusalReason.COMMAND_DID_NOT_RUN:
				return "fix the run argv or the host: the check could not be launched or hung"
			case ManufactureRefusalReason.VACUOUS:
				return (
					"strengthen the check: it passes on a tree holding nothing but itself (FR-107)"
				)


STRONG_ORACLE_MAX_RANK = 2
"""Rank 1 is strongest. Ranks 1-2 are mandatory above autonomy L2."""

COVERING_ORACLE_MAX_RANK = 5
"""The weakest oracle class that still *covers* a clause (FR-108).

FR-103's table is why the line is here and not at 7. Ranks 1-5 derive a check from
something the contract already asserts — an invariant, a state machine, a signature, a
relation between operations, the system model. Ranks 6 and 7 do not: an example is a
sample of behaviour and a golden file is a recording of one run, and FR-103's own
strength column calls them "sample, not coverage" and "detects change, not wrongness".
A clause covered only by an example is a clause nothing establishes, which is the debt
§2.3 is about.

Rank 6-7 are also capped at L2 by :func:`ceiling_for_rank`, but that is a *different*
refusal with a different reach: the rank cap applies to a contract whose weakest clause
is weak, and this one applies to a clause that is covered by nothing at all.
"""

UNCOVERED_CLAUSE_CEILING: Final[AutonomyLevel] = AutonomyLevel.L2
"""The highest autonomy a contract with any uncovered clause may claim (FR-109).

The same number as :data:`MODE_G_CEILING` and a different requirement, so it is a
different symbol: FR-123 caps a *delivery* because its architecture passed human gates,
and FR-109 caps a *contract* because a clause in it is unestablished. Collapsing them
would make a future change to either silently move the other.
"""


def ceiling_for_rank(rank: int) -> AutonomyLevel:
	"""Highest autonomy a contract may claim, given its weakest oracle rank.

	The ceiling is set by the *weakest* clause, not the strongest: a contract is
	only as verifiable as its least verifiable part.

	Ranks 1-2 admit L4; ranks 3-4 admit L3; anything weaker caps at L2. L5 is never
	returned.

	Rank alone, deliberately: this maps a *number* to a level and has no oracle to
	consult, so FR-109's executability cap is applied where the oracle is known —
	:attr:`Contract.ceiling` and :attr:`OracleDeclaration.covers`.
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


MODE_M_CEILING: Final[AutonomyLevel] = AutonomyLevel.L1
"""The end-to-end autonomy a *maintenance* claim may carry, and it is L1 (FR-158).

FR-158(a): Mode M's claim is maintenance, and maintenance is the one claim no oracle in
O1–O8 observes — a green suite says an obligation was satisfied, which is a strictly
narrower and genuinely checkable claim than "this can be maintained". So the two ceilings
are not one number, and this is the second of them.

L1 and not L2, and the difference is the whole of the requirement. L2 means the factory
proposes changes and a human verifies each one; L1 means the factory informs and never
mutates. A maintenance run at L2 would be a run whose changes a human reviews, which is
admissible only if the *review* is the oracle — and §20.2 measures review bandwidth as
the binding resource, so making the human the oracle for maintenance is exactly the
substitution FR-158 refuses. At L1 the factory reports what a change would cost and the
human owns the outcome, which is the honest shape while the change-cost oracle is absent.

Raising this is D18's decision and requires FR-159's instrument, not a larger number here:
the value is a *consequence* of the absent oracle, so a deployment that raised it without
building the oracle would be claiming a measurement it never took (NFR-024).
"""

EVOLVABILITY_DEBT: Final[float] = 1.0
"""FR-158's debt term, as a number, beside FR-108's ground-truth debt.

FR-108's debt is a *measured* fraction: the clauses no machine can currently check,
counted off the contract. FR-158's is not measured at all — it is 1.0 for every module
because no oracle in O1-O8 observes change cost, and 1.0 is the correct value rather than
a measurement failure. The two are one *kind* of thing (a debt fraction the report
carries) and not one number, which is why this is a separate constant with its own name
and not a term folded into the ground-truth count: a reader who saw one debt figure
would read the measurable one and take it for the whole.

Interpolated into :data:`MAINTAINABILITY_NOT_VERIFIED` so the sentence and the number
cannot drift into two statements of one fact.
"""

MAINTAINABILITY_NOT_VERIFIED: Final[str] = (
	"Maintainability was not verified. Every oracle this factory ran decides whether a "
	"clause was satisfied, and no oracle in O1-O8 observes what a change costs — so a "
	"green suite here is evidence about obligations and no evidence at all about whether "
	f"this system can be changed cheaply or safely. The evolvability debt of every module "
	f"is {EVOLVABILITY_DEBT:g} by construction, which is the correct value rather than a "
	"measurement failure (FR-158). Mode M is capped at L1 for the same reason. FR-159's "
	"change-cost instrument measures a diff footprint and is a proxy, not an oracle: where "
	"it reports a trend it reports one over a declared scope, and where it has no history "
	"to trend it reports that rather than a flat line."
)
"""FR-158(c), as a constant, for the reason :data:`DeliveryReport.VERIFIED_NOT_VALUE` is one.

FR-158 says the delivery report "must state that maintainability was not verified". A
free-text field would let a report state it in a sentence of the author's choosing, and
the failure mode is not a report that omits the sentence — it is a report that says
something adjacent and flattering. As a constant no code path can phrase it away, which
is what makes the refusal structural rather than editorial.

The FR-159 clause is appended rather than allowed to *replace* anything, and that is the
edit this sentence must not be given: an instrument landing is exactly the event that
tempts a report to soften "was not verified" into "and a trend was measured". The
instrument is named, its proxy status is named, and the two constants it would have to
move — the debt and the ceiling — are not moved.
"""

# --------------------------------------------------------------------------- #
# FR-159 — the change-cost instrument, and what it is not (D18, NFR-024)
# --------------------------------------------------------------------------- #

CHANGE_COST_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-159",)
"""What one change-cost measurement can carry out.

One requirement, because FR-159 is one instrument. A reading that measured no unit
carries nothing, which is a different state from a reading whose units all held — the
rule :data:`ESCAPE_REQUIREMENTS` states one subsystem over.
"""

CHANGE_COST_PROXY_DECLARATION: Final[str] = (
	"change cost is a PROXY. FR-159 measures the mechanical diff footprint a change unit "
	"produced — files touched, hunks, lines added and removed, modules crossed — and not "
	"the cost of making it: a codebase can get cheaper to change through better tests, "
	"better tooling, or familiarity, none of which moves a line count. NFR-024 applies, so "
	"this is declared as a proxy wherever it is reported and it is never a verdict."
)
"""FR-159's own boundary, stated once so no render can phrase it away.

FR-159 says the instrument "is a **proxy** (NFR-024 applies, and it must be declared as
one)". A declaration left to each report's author is a declaration that survives until
the report that would rather not make it, which is the failure mode
:data:`MAINTAINABILITY_NOT_VERIFIED` exists to close — so it is a constant.
"""

CHANGE_COST_AXIS: Final[str] = (
	"the axis is *comparable* change units, not calendar time. FR-159's claim is "
	"differential — a rising footprint on units of the same declared scope is shotgun "
	"surgery observed — so a unit is compared against units of its own scope and never "
	"against the codebase's average, which would report a large module as a decay."
)
"""FR-159's comparison rule, stated because the alternative reading is the tempting one.

A trend line over all units pooled is the obvious chart and the wrong measurement: it
moves when the *mix* of work changes, so a quarter of small fixes would read as an
improvement whether or not anything got cheaper to change.
"""

CHANGE_COST_RISE_FACTOR: Final[float] = 1.5
"""How much larger a unit's footprint must be before the trend alarm sounds (FR-159).

A factor rather than an absolute delta, because the units are line counts and a module
that grew from 200 to 400 lines is a different statement from one that grew from 20 to
40 — the ratio is the quantity that is comparable across units, and the spec's own
quantity is a *trend*.

1.5 is a declared threshold and it is declared here rather than defaulted per
deployment: unlike FR-023's escape budget, which bounds a *rate* the product has never
measured (§20.3 item 4), a footprint ratio is defined the moment two comparable units
exist. It is still not a verdict — the alarm reports that the footprint rose, and
whether that is decay is the human's reading.
"""

CHANGE_COST_BASELINE_UNMEASURED: Final[str] = (
	"the baseline is UNMEASURED. FR-159 tracks a footprint across a codebase's history, "
	"and a codebase that has produced one unit per scope has no history to trend over — so "
	"a scope with fewer than two measured units is reported as unmeasured rather than "
	"clean, exactly as ADR-0054 reported the escape rate's baseline before a deployment "
	"existed. 'No trend observed' and 'not enough history to observe one' are different "
	"statements and must not print the same line."
)
"""ADR-0054's precedent, applied to the second instrument that needs a history.

The escape rate needed a deployment and got a report saying so; a change-cost trend needs
a codebase history and gets the same treatment. NFR-024 forbids reporting a target the
product has not measured, and "the footprint is stable" over one unit is that forbidden
target wearing a chart.
"""

CHANGE_COST_NOT_A_VERIFICATION: Final[str] = (
	"this is not a verification and cannot become one. FR-159 is admissible as a trend "
	"alarm and as an input to a Mode M ceiling decision; it observes no clause and "
	"discharges none, so a delivery whose change-cost trend is flat is a delivery about "
	"which nothing further has been verified. The evolvability debt stays 1.0 by "
	"construction (FR-158) and the Mode M ceiling stays L1."
)
"""The line that keeps the instrument from being read as the oracle FR-158 says is absent.

D18 adopted FR-159 as a *proxy*, and the pressure on a proxy that produces a number is
always to promote it: a flat trend is the shape a reader wants to see beside a delivery,
and the sentence they will supply unprompted is "and it can be maintained". This constant
is the refusal of that promotion, and it names the two things that do not move when the
instrument lands — the debt and the ceiling — because those are the two a promotion would
have to move.
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


class ProbeOutcome(StrEnum):
	"""What a probe actually observed, for a capability (FR-148) or a boundary (FR-019).

	``INCONCLUSIVE`` is first-class for the same reason ``INSUFFICIENT`` is on the
	verdict side: a probe that could not decide must not be rounded to either verdict.
	Rounding it to ``ABSENT`` would condemn a harness or a boundary that may well hold;
	rounding it to ``CONFIRMED`` would be a fabricated capability.

	It lives above :class:`BoundaryMechanism` rather than beside the harness types it was
	written for, because :class:`DeploymentBoundary` defaults a field to it and a pydantic
	model resolves its annotations and defaults at class-build time — a forward reference
	to a later class in the same module is a ``NameError``, not a lazy lookup.
	"""

	CONFIRMED = "confirmed"
	ABSENT = "absent"
	INCONCLUSIVE = "inconclusive"


class BoundaryMechanism(StrEnum):
	"""What actually confines a child process, as *measured* rather than declared (FR-019).

	FR-019's own words are "the deployment boundary **where one exists**", which is a
	conditional: the requirement anticipates deployments without one and calls that
	configuration degraded. :class:`DeploymentTopology` records where the factory is
	*meant* to run; this records what was *observed* to hold. The two are different facts
	and R2 is the failure of conflating them — "autonomy depends on isolation (FR-019)
	that is asserted but never verified".

	``NONE`` is a member rather than the absence of one, for the reason ``ABSENT`` is a
	:class:`ProbeOutcome`: "a boundary was sought and none held" is a finding, and it must
	be distinguishable from "no boundary was sought".
	"""

	NONE = "none"
	SEATBELT = "seatbelt"
	CONTAINER = "container"
	NAMESPACE = "namespace"


class DeploymentBoundary(View):
	"""The isolation a probe measured, with the attempt and the observation (FR-019, FR-030).

	The evidence for a boundary claim is the same kind of evidence as for a capability
	claim, so the shape is :class:`CapabilityFinding`'s: ``attempted`` names the action and
	``observed`` the result. A boundary reported without them is a number to trust rather
	than a fact to check, which is the failure FR-030 forbids and this type exists to fix.

	``enforced`` is a separate field from ``mechanism`` because they answer different
	questions — *what was tried* and *whether it held* — and a mechanism that was present
	but did not confine is exactly the case a single enum would round to a lie. Measured
	on 2026-10-14: ``sandbox-exec`` refuses a profile whose subpath is unresolved, so
	"the tool exists" and "the tool confines" came apart on this very host.

	``None`` (no probe was run) is distinct from ``enforced=False`` (a probe ran and found
	nothing), which is FR-042's distinction between "not declared" and "declared T1"
	carried to the boundary: a factory that never measured must not be able to report the
	same thing as one that measured and found none.
	"""

	mechanism: BoundaryMechanism
	enforced: bool
	attempted: NonEmptyStr
	observed: NonEmptyStr
	probed_at: datetime
	writes_confined: bool = False
	"""Whether the FR-019 half held, recorded apart from the verdict (FR-059).

	``enforced`` is the *credit*: both halves held. This is one half, and keeping it
	separate is what lets a reader tell "nothing confined this child" from "writes were
	confined and the answer key stayed legible" — two different deployments with two
	different remedies, which a single boolean would round to the same report. It is also
	what lets :func:`~sofact.boundary.detect_boundary` keep a partially-confining
	mechanism as the finding of record instead of overwriting it with a generic verdict
	that says less.
	"""
	deny_read: tuple[str, ...] = ()
	"""Subtrees the probe found *unreadable*, as resolved paths (FR-059).

	FR-019 bounds what a child can write; FR-059 bounds what it can read — "no access to
	the oracle corpus, holdout scenarios, or factory credentials". The two are different
	claims and a boundary can hold one without the other: a profile permitting global
	reads confines a session's blast radius while leaving it the answer key. So the read
	half is recorded separately and is *measured*, by a probe that tries to read a file
	inside each named subtree rather than asserting that the rule was written.

	Empty means the read half was not measured, which is not the same as measured-and-open
	— the same distinction ``None`` makes one level up. A reader asking "could the producer
	read the holdout" must be able to tell those apart, because only one of them is a
	finding about this deployment.
	"""
	writable: tuple[str, ...] = ()
	"""Directories the probe granted writes to *besides* the workspace, as resolved paths.

	A dispatch owns two directories: its workspace and its session store. The store is the
	one this field exists for — measured 2026-10-14, a profile granting writes under the
	workspace alone denies ``touch <session_dir>/record.jsonl``, and every harness writes
	its record there, so the narrower profile broke every wrapped dispatch rather than
	confining it.

	It is recorded for the same reason ``deny_read`` is: :func:`~sofact.boundary.wrap_argv`
	rebuilds the enforcement profile from this record, and a rebuild that dropped the grant
	would run the dispatch under a *narrower* profile than the one measured — reporting
	confinement a session never had, which is the mirror of the defect this field fixes.
	"""

	egress: ProbeOutcome = ProbeOutcome.INCONCLUSIVE
	"""Whether the probe measured network egress to be denied (FR-019, FR-124, FR-152).

	FR-019's isolation is two properties, not one: the blast radius a child can *write* to
	and the network it can *reach*. FR-124's missing half names the second by hand —
	"packaging and egress are not read from the topology" — and M0 item 5 makes it an exit
	criterion: "container boundary and egress denial actually hold". Neither was measured
	before this field existed, so the delivery reported a boundary as enforced on the
	strength of the filesystem half alone.

	It is a :class:`ProbeOutcome` rather than a ``bool`` for the reason that enum exists:
	``INCONCLUSIVE`` is a probe that could not decide, and it must not be rounded to
	``ABSENT`` (which would condemn a boundary that may well hold) or to ``CONFIRMED``
	(which would be a fabricated capability). The default is ``INCONCLUSIVE`` so a record
	written before the probe existed reads as *not measured* rather than as *measured and
	open* — the same direction ``deny_read``'s empty tuple takes, and the only direction
	that cannot over-claim.

	``CONFIRMED`` means the child's connect was **refused**, which is the counter-intuitive
	reading: the outcome names the *boundary holding*, not the operation succeeding.
	"""

	egress_observed: str = ""
	"""What the egress probe saw, in the probe's own words (FR-030, FR-148).

	Separate from :attr:`observed` because the two halves can disagree, and a single
	sentence would have to pick one to lead with. A reader asking "could a producer reach
	the network from inside the lane" needs the answer to *that* question, and it is not
	always the answer to the write question.
	"""

	@property
	def egress_confined(self) -> bool:
		"""Whether network egress was *measured* denied, distinct from not measured.

		``enforced`` folds the two halves together, and this is the half a reader needs
		alone when the question is FR-152's — ``--offline`` is not an egress boundary, so
		the only thing that bounds egress is a boundary that was watched refusing a
		connection.
		"""
		return self.egress is ProbeOutcome.CONFIRMED

	@property
	def degraded(self) -> bool:
		"""Whether this is the degraded configuration FR-019 names (§5.4).

		True when no boundary held. A reader asking "is this factory isolated" gets a
		boolean that is false for the degraded case, rather than having to know which
		mechanism names mean isolation.
		"""
		return not self.enforced

	@property
	def modifier(self) -> int:
		"""The §5.4 ceiling modifier this *measured* boundary supports.

		Zero when a boundary held, and this is the whole of A2's arithmetic. §5.4's table
		tops out at 0 — T4 is "+0, unlocks L4 admissibility, not a level" — so a measured
		boundary may only *restore* the baseline a degraded declaration gave up, never
		exceed it. That is what keeps
		:func:`topology_ceiling`'s guard and :data:`HIGHEST_GRANTABLE` true without
		editing either: a modifier that could raise a level above L4 remains impossible,
		because the maximum this returns is 0.
		"""
		return 0 if self.enforced else TOPOLOGY_MODIFIER[DeploymentTopology.T1]


def topology_ceiling(
	level: AutonomyLevel,
	topology: DeploymentTopology,
	*,
	boundary: DeploymentBoundary | None = None,
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

	``boundary`` is the isolation a probe *measured*, and it overrides the declared
	topology's modifier when one held (FR-019). This is the fix for R2 rather than a
	widening of §5.4: a deployment that declared T1 and was then measured to confine its
	children is not running the degraded configuration, so charging it T1's penalty would
	be the same conflation in the other direction. The override can only ever *raise* the
	modifier to 0 — :attr:`DeploymentBoundary.modifier` is capped there by §5.4's own
	table, whose maximum is 0 — so the assertion below keeps its full force: nothing here
	can lift a level above :data:`HIGHEST_GRANTABLE`.
	"""
	modifier = (
		boundary.modifier
		if boundary is not None and boundary.enforced
		else TOPOLOGY_MODIFIER[topology]
	)
	modified = int(level) + modifier
	assert modified <= int(HIGHEST_GRANTABLE), (
		f"{topology.value}'s modifier of {modifier:+d} would raise "
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


MODEL_ANSWER_PREFIX: Final[str] = "model:"
"""How ``answered_by`` says a machine wrote an answer rather than a person (FR-173).

A prefix on the existing field rather than a new boolean, because the field already
carried the identity and nothing read it. ``by="operator"`` and ``by="model:qwen"`` were
indistinguishable to :func:`sofact.elicitation.assess`, so a model-drafted answer counted
as a resolved dimension and cleared P0 — the "written and never read" defect with a
human's signature on it one gate later.
"""


class ElicitationAnswer(View):
	"""One answer to one dimension, and who gave it.

	``answered_by`` is an identity, not a label: it is the whole of what separates an
	operator's words from a machine's proposal, and :attr:`is_model_proposed` is the
	reader it did not have until FR-173.
	"""

	id: UUID7
	goal_id: UUID7
	dimension: ElicitationDimension
	text: NonEmptyStr
	answered_by: NonEmptyStr
	at: datetime

	@property
	def is_model_proposed(self) -> bool:
		"""Whether a machine wrote this answer rather than a person (FR-173).

		Derived from ``answered_by`` rather than stored, for :attr:`OracleDeclaration.held_out`'s
		reason: a field defaulting to ``False`` would leave the distinction open at every
		answer built without it, whereas a derivation is correct at every site that reads
		it. A proposal is not a lie — it is an answer nobody has read yet, which is why
		:class:`ElicitationAttestation` exists rather than a refusal.
		"""
		return self.answered_by.startswith(MODEL_ANSWER_PREFIX)


class ElicitationAttestation(View):
	"""A person confirming a model-proposed answer, or editing it into their own (FR-173).

	Attestation records that a human **read** an answer, not that the answer is *true* —
	the same distinction :mod:`sofact.elicitation` draws about its deterministic floor. Its
	job is to make "a machine wrote this and nobody checked" a state the log can express,
	so it can be refused rather than silently approved.

	An operator who re-answers a dimension instead of attesting the proposal needs no
	attestation at all: :func:`sofact.elicitation.assess` lets a later answer supersede an
	earlier one, and the superseding answer is the operator's own.
	"""

	id: UUID7
	answer_id: UUID7
	attested_by: NonEmptyStr
	at: datetime

	@model_validator(mode="after")
	def _an_attestation_is_a_person(self) -> Self:
		if self.attested_by.startswith(MODEL_ANSWER_PREFIX):
			raise ValueError(
				f"attested_by {self.attested_by!r} is model-proposed, and an attestation by "
				"a machine is not an attestation: the whole content of FR-173 is that a "
				"person read the answer, so a model signing for one restores exactly the "
				"state this record exists to make visible"
			)
		return self


class Transcript(View):
	"""What a transcriber produced from one audio file, and how (FR-168).

	``text`` is a plain ``str`` and not a ``NonEmptyStr``, because a transcription that
	failed is a real state and rounding it into an empty goal would be the defect: the
	operator would see a goal with a blank statement rather than a tool that did not run.
	:attr:`is_usable` is the only predicate any caller should branch on.

	The audio's digest is recorded so a transcript is bound to *the* recording it came
	from. A transcript whose ``audio_sha256`` is not the digest of the file you passed is
	not a transcript of it, and without the field there would be no way to tell.
	"""

	id: UUID7
	goal_id: UUID7 | None = None
	audio_path: str
	audio_sha256: NonEmptyStr
	audio_bytes: int
	transcriber: NonEmptyStr
	model: str | None = None
	argv: tuple[str, ...] = ()
	exit_code: int | None = None
	text: str = ""
	stderr_tail: str | None = None
	at: datetime

	@property
	def is_usable(self) -> bool:
		"""Whether this is a transcript at all: the tool ran and said something.

		Both conjuncts are required. An exit code of zero with no text is a transcriber
		that heard nothing, and text beside a non-zero exit is a partial output from a
		run that failed — neither is a statement an operator made.
		"""
		return self.exit_code == 0 and bool(self.text.strip())


class CapabilityKind(StrEnum):
	"""The three words the operator used, kept distinct rather than merged (FR-169).

	FR-169 asks for "the features capabilities and functionality" of the best systems, and
	those are three different questions about one product: a *feature* is something it
	does, a *capability* is something it can be relied on to do under load or failure, and
	*functionality* is the surface those are reached through. Collapsing them into one
	list would lose the distinction at exactly the point the exceedance declaration needs
	it — you can exceed a feature by adding one and you cannot exceed a capability without
	evidence, which is why the type survives.
	"""

	FEATURE = "feature"
	CAPABILITY = "capability"
	FUNCTIONALITY = "functionality"


class RivalSystem(View):
	"""One of the best-known systems for this domain, as the producer identified it (FR-169).

	``source_ids`` is non-empty and that is the whole of what makes this a baseline rather
	than a rumour: SoFact cannot name the best systems in the world for an arbitrary
	domain, so the producer does — under a criterion SoFact writes into the research goal
	— and the identification is admissible only with the evidence behind it.
	"""

	id: UUID7
	name: NonEmptyStr
	vendor: str | None = None
	url: NonEmptyStr
	source_ids: tuple[UUID7, ...]
	posture: SourcePosture

	@model_validator(mode="after")
	def _a_rival_cites_something(self) -> Self:
		if not self.source_ids:
			raise ValueError(
				f"rival system {self.name!r} cites no source, so it is a rumour rather than "
				"a baseline: FR-169's comparison is against the best systems in the world, "
				"and a system nobody can look up is not one of them"
			)
		return self


class RivalCapability(View):
	"""One feature, capability or functionality of one rival, with its evidence (FR-169)."""

	id: UUID7
	system_id: UUID7
	statement: NonEmptyStr
	kind: CapabilityKind
	source_ids: tuple[UUID7, ...]

	@model_validator(mode="after")
	def _a_capability_cites_something(self) -> Self:
		if not self.source_ids:
			raise ValueError(
				f"capability {self.statement[:40]!r} cites no source: an uncited capability "
				"cannot be the baseline an exceedance is declared against, because there "
				"would be nothing to check the claim of exceeding it (FR-169)"
			)
		return self


class CompetitiveLandscape(View):
	"""What the competitive research pass found, with its own selection criterion (FR-169).

	``subject`` must equal ``query``: SoFact authors the research subject and the producer
	echoes it back. Without that check a producer could retitle the scan — research
	"competitors in X" and return a survey of Y — and every downstream reader would take
	the landscape as an answer to the question SoFact asked. It is the same failure
	:func:`sofact.service.research_goal` prevents by writing the clause ids into the
	prompt rather than letting the producer choose its own subject list.
	"""

	id: UUID7
	goal_id: UUID7
	query: NonEmptyStr
	subject: NonEmptyStr
	version: int = 1
	systems: tuple[RivalSystem, ...] = ()
	capabilities: tuple[RivalCapability, ...] = ()
	scanned_at: datetime

	@model_validator(mode="after")
	def _the_subject_is_the_one_sofact_asked_for(self) -> Self:
		if self.subject.strip() != self.query.strip():
			raise ValueError(
				f"the scan's subject {self.subject!r} is not the subject SoFact asked for "
				f"({self.query!r}): a landscape that retitles the question is not an answer "
				"to it, and every reader downstream would take it as one (FR-169)"
			)
		if self.version < 1:
			raise ValueError(f"version must be >= 1, got {self.version}")
		return self

	@model_validator(mode="after")
	def _every_capability_belongs_to_a_system(self) -> Self:
		known = {s.id for s in self.systems}
		strangers = tuple(c.system_id for c in self.capabilities if c.system_id not in known)
		if strangers:
			raise ValueError(
				f"{len(strangers)} capability(ies) name a system the scan does not carry: a "
				"capability of nothing cannot be compared against anything (FR-169)"
			)
		return self

	@property
	def sourced_systems(self) -> tuple[RivalSystem, ...]:
		"""The rivals that cite at least one source.

		Equal to :attr:`systems` by construction, since :class:`RivalSystem` refuses an
		uncited one. Exposed anyway because the *count* is what the report prints beside
		the total, and a reader comparing them should be able to see they agree rather
		than be told the invariant holds.
		"""
		return tuple(s for s in self.systems if s.source_ids)

	@property
	def unexamined_systems(self) -> tuple[RivalSystem, ...]:
		"""Rivals with no capability recorded, so the scan looked but found nothing.

		Not a failure and not a pass: it is the measurement FR-169 has to carry, because a
		landscape of five well-sourced rivals whose capabilities were never enumerated
		would otherwise read as a stronger baseline than one rival that was examined.
		"""
		examined = {c.system_id for c in self.capabilities}
		return tuple(s for s in self.systems if s.id not in examined)

	@property
	def found_nothing(self) -> bool:
		"""Whether the pass returned no rival at all.

		A measurement rather than a failure, and reported as one: a domain with no
		comparable system is a real finding about the domain, and the alternative —
		treating it as an error — would push a producer toward inventing rivals to avoid
		one.
		"""
		return not self.systems


class ExceedsClaim(View):
	"""A declared capability that is meant to exceed a cited rival's (FR-170).

	**No oracle in O1–O7 compares two systems, so this is never a verified fact.**
	``measured_margin`` returns ``None`` always, and that is not an unimplemented method —
	it is NFR-024 stated as a type. There is no measurement behind the claim, so there is
	no number to report, and a renderer that printed one would be inventing it.

	``baseline_source_ids`` is non-empty for the reason :class:`RivalSystem`'s is: a claim
	to exceed something nobody can look up is a wish. ``clause_ids`` is non-empty so the
	claim traces to something the operator actually asked for (FR-076's rule, applied to
	the declaration rather than the requirement).
	"""

	id: UUID7
	goal_id: UUID7
	capability: NonEmptyStr
	baseline: NonEmptyStr
	baseline_source_ids: tuple[UUID7, ...]
	rationale: NonEmptyStr
	clause_ids: tuple[UUID7, ...]
	declared_by: NonEmptyStr
	declared_at: datetime

	@model_validator(mode="after")
	def _a_claim_to_exceed_names_what_it_exceeds(self) -> Self:
		if not self.baseline_source_ids:
			raise ValueError(
				f"exceedance {self.capability[:40]!r} cites no source for its baseline "
				f"({self.baseline!r}): a capability declared to exceed something with no "
				"evidence behind it cannot be checked by a reader or an oracle, and FR-170 "
				"asks for a comparison, not an assertion"
			)
		if not self.clause_ids:
			raise ValueError(
				f"exceedance {self.capability[:40]!r} traces to no intent clause, so nothing "
				"the operator asked for requires it (FR-076)"
			)
		return self

	@property
	def measured_margin(self) -> None:
		"""Always ``None``: nothing measures this, so nothing may report a figure (FR-170).

		Returns ``None`` rather than raising, so a renderer reads the same value it reads
		for every other unmeasured quantity and prints *unmeasured*. A method that raised
		would invite a caller to wrap it, and the wrapper is where a default would appear.
		"""
		return None


class AnswerProvenance(View):
	"""Which answer a requirement descends from, and whether a person ever read it (FR-171)."""

	dimension: ElicitationDimension
	answer_id: UUID7
	answered_by: NonEmptyStr
	attested: bool

	@property
	def unattested(self) -> bool:
		"""Whether a machine proposed this and no person has confirmed it (FR-173).

		**Both conjuncts are required.** The attested set holds attestation *rows*, and a
		row exists only for a model-proposed answer — :meth:`FactoryService.attest` refuses
		to attest the operator's own words, because a person confirming themselves is not a
		reading. So ``not self.attested`` alone is true of every operator answer ever
		written, and the document would print the unattested marker against every
		requirement in a specification the operator typed themselves. The authorship half is
		what makes the predicate mean what its name says.
		"""
		return not self.attested and self.answered_by.startswith(MODEL_ANSWER_PREFIX)


class ClauseVerdictProvenance(View):
	"""What research concluded about one clause a requirement traces to (FR-171)."""

	clause_id: UUID7
	verdict: ResearchVerdict
	source_ids: tuple[UUID7, ...] = ()


class RequirementAnnotation(View):
	"""One requirement, with every fact that explains why it exists (FR-171).

	This is what "annotated" means in the operator's request: a requirement is not a
	sentence the specification asserts, it is a sentence with a provenance. The annotation
	carries the elicitation answers it descends from, what research concluded about the
	clauses it traces to, the oracle class and rank that will check it, the module that
	owns it, and any exceedance declared against it.

	The requirement is **held**, not referenced. A ``requirement_id`` alone would make the
	document a join between two collections, and a renderer that failed the join would print
	an annotation of nothing — the document could then disagree with the record it claims to
	render. Holding it makes that state unrepresentable.

	:attr:`unattested` is derived from the answers rather than passed in, which is the
	property that makes the document honest: a requirement built from a model proposal
	nobody read cannot be rendered as though a person had.
	"""

	requirement: Requirement
	clause_ids: tuple[UUID7, ...]
	elicitation: tuple[AnswerProvenance, ...] = ()
	research: tuple[ClauseVerdictProvenance, ...] = ()
	oracle_class: OracleClass | None = None
	oracle_rank: int | None = None
	module_id: UUID7 | None = None
	exceeds_claim_ids: tuple[UUID7, ...] = ()

	@property
	def requirement_id(self) -> str:
		"""The requirement's id, so a caller need not reach through the annotation."""
		return self.requirement.id

	@property
	def unattested(self) -> bool:
		"""Whether any answer behind this requirement is a proposal nobody confirmed.

		One unattested answer is enough, and it is not a majority rule: the requirement
		states what the operator wants, and a single clause of it that a machine wrote and
		nobody read is a clause of the specification no person has agreed to.
		"""
		return any(a.unattested for a in self.elicitation)

	@property
	def unattested_answers(self) -> tuple[AnswerProvenance, ...]:
		"""The specific answers behind this requirement that nobody attested (FR-173)."""
		return tuple(a for a in self.elicitation if a.unattested)


UNATTESTED_MARKER: Final[str] = "**UNATTESTED — proposed by a machine, not confirmed by a person**"
"""What the specification document prints beside an unattested requirement (FR-173).

A constant because the test suite asserts the rendered document against it: the marker
is the one thing in the document that must never quietly change, since its whole job is
to be noticed by a human deciding whether to approve the gate.
"""


class ProductSpecificationDocument(View):
	"""The rendered specification and the facts it was rendered from (FR-171).

	The document is a *rendering* of this record rather than the record itself, which is
	the arrangement ADR-0044 established for the delivery: two renders of one document are
	byte-identical, so a diff between two specifications is a diff between two sets of
	facts rather than between two paraphrases.

	``attested`` is a property and not a field. A stored flag would let a caller render a
	document as approved without an approval, and the approval is exactly what the first
	gate is.
	"""

	id: UUID7
	goal_id: UUID7
	specification_id: UUID7
	contract_id: UUID7
	landscape_id: UUID7 | None = None
	rendered_at: datetime
	requirements: tuple[RequirementAnnotation, ...] = ()
	exceeds: tuple[ExceedsClaim, ...] = ()
	approved_by: NonEmptyStr | None = None
	approved_at: datetime | None = None

	@property
	def unattested(self) -> tuple[RequirementAnnotation, ...]:
		"""The requirements in this document no person has attested (FR-173)."""
		return tuple(r for r in self.requirements if r.unattested)

	@property
	def attested(self) -> bool:
		"""Whether a human has approved this specification, and nothing behind it is open.

		Both conjuncts, and the second is the one that matters: an approval recorded
		against a document whose requirements include a model proposal nobody read is not
		an approval of that requirement, so the document stays unattested until either the
		answer is attested or the requirement is removed.
		"""
		return self.approved_by is not None and not self.unattested


class DriverOutcome(StrEnum):
	"""What one step of the driver did (FR-172)."""

	ADVANCED = "advanced"
	HALTED = "halted"
	REFUSED = "refused"
	SKIPPED = "skipped"


class DriverTerminal(StrEnum):
	"""Why the driver stopped, and there is no member for "still going" (FR-172).

	The driver is a loop over the ledger rather than a held process, so every run ends and
	ends in one of these. ``GATE_OPEN`` is the ordinary case and not an error: FR-061 makes
	a gate a hard stop, so a run that reaches one has done all the machine work there is.
	"""

	GATE_OPEN = "gate_open"
	DELIVERED = "delivered"
	REFUSED = "refused"
	EXHAUSTED = "exhausted"
	FAILED = "failed"


class DriverStep(View):
	"""One thing the driver did, recorded whether it worked or not (FR-172)."""

	id: UUID7
	phase: Phase
	action: NonEmptyStr
	outcome: DriverOutcome
	detail: NonEmptyStr
	at: datetime


class DriverRun(View):
	"""One invocation of the driver, from wherever it started to wherever it stopped (FR-172).

	``claims_built`` is a property derived from ``terminal``, and it is the single source
	of the notification's wording. A body that said "built" while a gate was open is the
	worst defect this feature can have, so it is made unrepresentable rather than merely
	avoided: nothing composes that sentence from any field but this one.
	"""

	id: UUID7
	goal_id: UUID7
	started_at: datetime
	ended_at: datetime
	steps: tuple[DriverStep, ...] = ()
	terminal: DriverTerminal
	terminal_detail: NonEmptyStr
	open_gate: Phase | None = None
	gate_failures: tuple[str, ...] = ()
	"""The machine checks that failed at the open gate, by name, or empty (FR-172).

	Carried as names rather than as :class:`GateCheck` rows because the only thing read
	off them is whether the gate's machine half failed at all — and a gate whose machine
	half failed is *not* resumable with ``gate approve``, which refuses it. See
	:attr:`next_human_verb`.

	The default is empty, and empty is the truthful reading for a run that recorded no
	failures: an older row in a ledger written before this field existed folds to "the
	machine half passed", which is what ``gate approve`` did with it at the time.
	"""

	notification_id: UUID7 | None = None

	@property
	def claims_built(self) -> bool:
		"""Whether this run may say the system was built (FR-172).

		``DELIVERED`` and nothing else. Every other terminal names a reason the run
		stopped, and each of them is a reason the system is not built.
		"""
		return self.terminal is DriverTerminal.DELIVERED

	@property
	def next_human_verb(self) -> str | None:
		"""The command that would let this run continue, or ``None`` if it is finished.

		Printed beside the terminal state so the operator is never told a run stopped
		without being told what to type. A ``DELIVERED`` run has no next verb; every other
		terminal does, including ``FAILED`` — a failure still has a human action, and
		reporting one without the other is how a stopped run reads as a dead one.

		``EXHAUSTED`` is the one that needs care, because it covers two different waits. A
		run that stopped with the interrogation still open is waiting on a *person to
		answer*, and telling it to resume would be telling the operator to re-run a loop
		that will do nothing until they do — so the verb is read off the steps the run
		actually took rather than assumed from the terminal alone.

		**An open gate whose machine half failed is not approved with ``gate approve``.**
		That verb refuses a failed check, so naming it sent the operator to a command that
		could only refuse — and the fix for a failed machine half is to supply what the
		checks found missing and produce the artefact again, which is the phase's own verb.
		:data:`PHASE_PRODUCER_VERB` is that verb, and the branch is keyed on
		:attr:`gate_failures` rather than on the gate being open at all, because a gate
		whose machine half passed *is* approved with ``gate approve`` and saying otherwise
		would be the opposite mistake.
		"""
		if self.terminal is DriverTerminal.DELIVERED:
			return None
		if self.open_gate is not None:
			if self.gate_failures:
				producer = PHASE_PRODUCER_VERB.get(self.open_gate)
				if producer is not None:
					return (
						f"sofact {producer}  (then `sofact gate approve "
						f"{self.open_gate.value} --by <you>` once the checks pass)"
					)
			return f"sofact gate approve {self.open_gate.value} --by <you>"
		if self.stopped_on == "propose-answers":
			# ``sofact`` with no subcommand is the questionnaire — the product's own front
			# door — so the verb really is bare. It is spelled out as ``sofact`` rather than
			# as an empty string, because the trailing space read as a missing command in a
			# line whose whole job is to tell the operator what to type.
			return "sofact   (bare: the questionnaire resumes at the open dimension)"
		return "sofact build --resume"

	@property
	def stopped_on(self) -> str | None:
		"""The action the run stopped on, or ``None`` if it stopped between actions.

		Read from the last step, because that is the only place the reason a run halted is
		recorded: the terminal names the *kind* of stop and the step names what was being
		attempted when it happened.
		"""
		return self.steps[-1].action if self.steps else None


class Notification(View):
	"""One attempt to tell the operator something, and whether it worked (FR-172).

	**A notification that was not sent is not a notification**, which is why the row is
	appended whether or not a process launched and ``delivered`` is derived from the exit
	code rather than declared. A record written only on success would make "we told them"
	and "we meant to tell them" indistinguishable in the log, and the second is the one
	worth knowing about.

	The body is **digested, not stored**. A notification body names the system being
	built, and the ledger is a durable artefact; ``body_sha256`` and ``body_chars`` make
	"was a notification sent, and was it this one" answerable without the ledger holding
	a client's words forever.
	"""

	id: UUID7
	goal_id: UUID7 | None = None
	run_id: UUID7 | None = None
	notifier: NonEmptyStr
	argv: tuple[str, ...] = ()
	subject: NonEmptyStr
	body_sha256: NonEmptyStr
	body_chars: int
	exit_code: int | None = None
	expect_exit_code: int = 0
	error: str | None = None
	at: datetime

	@property
	def delivered(self) -> bool:
		"""Whether a process ran and reported success (FR-172).

		``None`` is never delivered: an exit code of ``None`` means no process ran, which
		is the launch failure and not a silent success.
		"""
		return self.exit_code is not None and self.exit_code == self.expect_exit_code


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

	@property
	def covers(self) -> bool:
		"""Whether this oracle *covers* its clause: strong enough and runnable (FR-108).

		Both conjuncts are required, and each was missing from one consumer before this
		existed. :attr:`Contract.ceiling` read the rank alone, so a rank-1 property
		*intention* — prose with no command — granted L4 to a contract nothing could run.
		:func:`~sofact.contract.ground_truth_debt` read executability alone, so a rank-6
		example test with a command reported zero debt on a clause FR-103's own table
		calls "sample, not coverage".

		Neither half suffices. A weak oracle that runs measures the wrong thing; a strong
		oracle that does not run measures nothing. §2.3's failure is a contract that
		*looks* verified, and it takes both conjuncts to look that way, so it takes both
		to refuse it.
		"""
		return self.is_executable and self.rank <= COVERING_ORACLE_MAX_RANK

	@property
	def held_out(self) -> bool:
		"""Whether this oracle's payload is withheld from the producer (FR-106).

		The class *is* the provenance, and that is FR-103's own table rather than an
		inference drawn here: row 6's source column reads "operator-supplied cases", so
		an example oracle is the operator's by definition. FR-106 turns on exactly that
		— "operator examples are the operator's intent and therefore the best available
		proxy for correctness; they are wasted if the builder can read them" — and
		FR-017 makes reading one a lane-halting defect rather than a quality problem.

		What is withheld is the *scenario*: the description, the command and the
		expected output, which together are the operator's case. What is not withheld
		is the obligation, which is the clause's own statement, nor the class and rank,
		which say how strong the check is without saying what it checks. A producer
		told the obligation and the strength can build to the intent; one told the
		expected output builds to the sample, and FR-103 calls rank 6 "sample, not
		coverage" for the same reason.

		Ranks 6 and 7 are both weak and only 6 is held out. FR-103's source column is
		why: a golden file is "output of a reference run", usually the producer's own
		recording, and withholding it would hide the thing the producer is being asked
		to reproduce. FR-106 says "example-based" and means it.

		This is a property rather than a stored flag on purpose. A field defaulting to
		``False`` would leave the leak open on every oracle built without it — a control
		that exists and is never applied — whereas a derivation from the class is
		correct at every site that reads it. The premise it rests on, that the factory
		manufactures no example oracle, is asserted in :func:`sofact.contract.suggest_oracle`
		rather than left as a comment here.
		"""
		return self.oracle_class is OracleClass.EXAMPLE


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
	def uncovered_clauses(self) -> tuple[Clause, ...]:
		"""Clauses no oracle covers (FR-108): not runnable, or too weak to establish.

		The complement of :attr:`OracleDeclaration.covers` over the clause set. This is
		the set FR-109's L2 cap is about and the set ground-truth debt is the size of,
		expressed once here so the cap and the debt cannot come to mean different things.
		"""
		return tuple(c for c in self.clauses if not c.oracle.covers)

	@property
	def ground_truth_debt(self) -> float:
		"""Fraction of clauses no oracle covers (FR-108, §2.3).

		``0.0`` is the only good value. Anything above it means the contract's autonomy
		ceiling is a claim about clauses that were never established — which is why
		:attr:`ceiling` reads this and caps at L2 when it is non-zero.
		"""
		return len(self.uncovered_clauses) / len(self.clauses)

	@property
	def ceiling(self) -> AutonomyLevel:
		"""Autonomy this contract may claim, per :func:`ceiling_for_rank`.

		Capped at L2 when any clause is uncovered (FR-109). The rank half and the
		coverage half are different failures: a weak-but-runnable oracle *measures*
		something and bounds the ceiling by what it measures, whereas an uncovered clause
		measures nothing, so a contract containing one cannot be reported above the level
		at which a human still checks the result.
		"""
		level = ceiling_for_rank(self.weakest_oracle_rank)
		if self.uncovered_clauses:
			return AutonomyLevel(min(level, UNCOVERED_CLAUSE_CEILING))
		return level

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

		It is the count of *surfaces*, which is one per module: a module is the unit that
		exposes an interface, so the integration points are the modules. That is why the
		number is minimised by grouping clauses rather than by trimming a member list —
		and why :meth:`interface_members` is reported beside it, since a count of
		surfaces says nothing about how wide each one is.

		The bound on this number is §1.3's modules dimension. The spec gives no *interface*
		threshold, so none is invented here; what FR-091 makes checkable is the comparison
		against the grouping the system model declares, which lives in
		:func:`sofact.decomposition.interface_groups` — one rule in one place, because a
		proposer and a gate that read the model differently would let the proposer emit a
		proposal its own gate refuses.
		"""
		return len(self.modules)

	@property
	def interface_members(self) -> int:
		"""Total declared public names across every module's surface (FR-091, §20.1).

		The other half of the interface metric. Two decompositions can expose the same
		number of surfaces at very different widths, and §20.1's "interface count per
		module" is the ratio of the two. Counted with duplicates, because the same name on
		two surfaces is two places a caller can reach it — which is the integration
		exposure the number exists to state.
		"""
		return sum(len(module.surface) for module in self.modules)

	@property
	def interfaces_per_module(self) -> float:
		"""§20.1's metric, as the ratio it names rather than a second absolute count."""
		if not self.modules:
			return 0.0
		return self.interface_members / len(self.modules)

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


class SystemInterface(View):
	"""A surface the system exposes, declared *in the model* rather than on a module.

	FR-083's second clause is the one that has been open since ADR-0027: "the system model
	must be **the single source for interface definitions**. Hand-written interfaces that
	disagree with the model are an integration defect by construction." ADR-0027 put the
	declared surface on :class:`Module` instead, which made FR-112 checkable and left FR-083
	half-discharged — a surface declared on a module is a surface declared *beside* the
	model, so a model and a module can disagree and nothing says which one is the truth.

	This type closes that by making the model the place an interface is *declared* and the
	module the place it is *bound*. The binding is what keeps it honest: an interface here
	names the clause it comes from, and a module owns clauses, so ``entity -> clause ->
	module`` is the same set comparison :class:`SystemEntity` already uses — no name
	searching, no fuzzy matching.

	``members`` is the same :class:`InterfaceMember` a module declares, deliberately: the
	two are one vocabulary, so a surface moved from a module to the model is the *same*
	declaration in a different place rather than a translation between two shapes. That is
	what makes FR-083's "single source" checkable — P7 can diff the model's interfaces
	against the built surface directly, and a module whose ``surface`` disagrees with the
	model's interface for its own clause is a finding rather than a silent second opinion.
	"""

	name: NonEmptyStr
	clause_ids: tuple[UUID7, ...] = ()
	members: tuple[InterfaceMember, ...] = ()

	@model_validator(mode="after")
	def _an_interface_comes_from_something(self) -> Self:
		if not self.clause_ids:
			raise ValueError(
				f"interface {self.name!r} names no clause, so no module can be shown to "
				"owe it and FR-083's binding has nothing to bind to (FR-081, FR-083)"
			)
		return self


class SystemModel(View):
	"""The machine-readable model: entities, relationships, invariants, interfaces.

	FR-083: "must be machine-readable and must be the single source for interface
	definitions". Both halves are here now. ``interfaces`` is the declaration, and
	:class:`Module.surface` is the *binding* of it to the module that owes it — the module
	still carries the surface FR-112 diffs a build against, and the model now carries the
	one the operator declared, so the two are compared rather than one being trusted.

	What the model does **not** carry is a second copy of every module's surface. A model
	that duplicated it would be two declarations to keep in step, which is the drift FR-084
	exists to make expensive and the reason MDSE failed. An interface here is declared once
	per clause; a module's surface is derived from the interfaces its clauses introduce,
	and a disagreement between them is the integration defect FR-083 says it is.
	"""

	entities: tuple[SystemEntity, ...] = ()
	relationships: tuple[SystemRelationship, ...] = ()
	invariants: tuple[SystemInvariant, ...] = ()
	interfaces: tuple[SystemInterface, ...] = ()

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

	@model_validator(mode="after")
	def _no_two_interfaces_share_a_name(self) -> Self:
		"""Two interfaces under one name is a model whose meaning depends on lookup order.

		The same refusal :data:`~sofact.api.MACHINE_OPERATIONS` makes about operation
		names, one type along: FR-083 makes this the single source, and a source that
		answers a question two ways is not a source. It is also the case a merge would
		produce — two clauses each contributing an interface called ``store`` — so the
		refusal names both clauses rather than the name alone.
		"""
		seen: dict[str, str] = {}
		for interface in self.interfaces:
			previous = seen.get(interface.name)
			if previous is not None:
				raise ValueError(
					f"the model declares two interfaces called {interface.name!r} "
					f"(clauses {previous} and {interface.clause_ids[0]}); FR-083 makes the "
					"model the single source for interface definitions, and a source that "
					"answers one name twice is not one"
				)
			seen[interface.name] = interface.clause_ids[0]
		return self

	@property
	def is_empty(self) -> bool:
		"""Whether the model declares nothing, so nothing can be conformed against."""
		return not (self.entities or self.relationships or self.invariants or self.interfaces)

	@property
	def entity_names(self) -> frozenset[str]:
		"""Every declared entity name, for reference checks."""
		return frozenset(e.name for e in self.entities)

	def interfaces_for_clauses(self, clause_ids: Iterable[str]) -> tuple[SystemInterface, ...]:
		"""The interfaces whose clauses intersect ``clause_ids``, in declaration order.

		This is FR-083's binding, and it is the whole of it: a module owns clauses, an
		interface names clauses, so a module's declared surface is the members of the
		interfaces its clauses introduce. No name matching, so an interface called
		``store`` and a module called ``store`` are related by the clause they share and
		not by their spelling — which is the difference between a check and a coincidence.
		"""
		wanted = set(clause_ids)
		return tuple(i for i in self.interfaces if wanted & set(i.clause_ids))

	def surface_for_clauses(self, clause_ids: Iterable[str]) -> tuple[InterfaceMember, ...]:
		"""Every member the model declares for a module owning ``clause_ids``.

		Deduplicated by name, first declaration winning, because two interfaces over one
		module's clauses may legitimately name the same member — the same entity appearing
		in two clauses is the ordinary case — and a surface is a set of public names, not a
		multiset of the statements that introduced them.
		"""
		members: dict[str, InterfaceMember] = {}
		for interface in self.interfaces_for_clauses(clause_ids):
			for member in interface.members:
				members.setdefault(member.name, member)
		return tuple(members.values())


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


PHASE_PRODUCER_VERB: dict[Phase, str] = {
	Phase.SPECIFY: "specify",
	Phase.DECOMPOSE: "decompose",
	Phase.CONTRACT: "plan",
	Phase.DELIVER: "deliver",
}
"""The verb that produces the artefact a gate is a gate on, per gated phase.

It exists because **a gate can be open with a failed machine half**, and the verb that
resumes such a run is not ``gate approve``. ``gate approve`` refuses a failed check —
correctly, since approval cannot make an unsound artefact sound — so a run that stopped
there and named it sent the operator to a command that could only refuse them, with no
way forward that did not involve editing the ledger by hand.

The fix for a failed machine half is to supply what the checks found missing and produce
the artefact again, which is the phase's own verb: ``specify`` takes the operator's system
model, assumptions and value hypothesis, ``decompose`` re-proposes over a repaired
specification, ``plan`` re-audits the oracles. Naming that verb is the difference between
a hard stop and a dead end.

Keyed by phase rather than by gate because the phase is what the operator types, and
hand-written rather than derived because there is no machine-readable link from a phase to
a CLI verb — the alternative would be importing the CLI into the view layer, which is the
dependency arrow pointing the wrong way.
"""


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


class DiffReview(View):
	"""What one human review of one sealed diff cost (§20.3 item 3).

	FR-160 records what a *gate* cost, and §20.3 item 3 asks for the same number
	**per diff** as well: "logged per gate *and* per diff, so §1.4's claim can be
	compared directly against the v0.1 alternative." §1.4's claim is that human
	attention is spent per platform rather than per module, and the alternative it
	must beat is v0.1's per-diff review — whose rate §1.4 names as roughly four units
	an hour, about fifteen minutes a diff. Gate-minutes alone cannot make that
	comparison; only a per-diff number can, and it does not exist unless it is asked
	for, for exactly the reason :class:`GateCost` gives: nothing in SoFact observes a
	person reading.

	**The diff is identified by its dispatch and its commit, never by its step.** A
	step can be dispatched more than once — a repair, a re-dispatch after a stall —
	and each dispatch seals its own commit. Keying a review by step would collapse two
	reviewable diffs into one and *understate* review time, which is the one direction
	a measurement of the binding constraint must not be able to move. ``sealed_commit``
	is recorded rather than left implicit for :class:`ChangeUnit`'s reason: a review
	whose number could later be read against a different diff is not a measurement of
	a diff.

	``human_minutes`` and ``rework_fraction`` are declared, like the gate pair and for
	the same argument. ``rework_fraction`` is a share of the *diff* — how much of what
	was sealed came back — and it is deliberately not comparable to the gate's
	fraction of a *slice*: the denominators differ, so the two are reported as
	separate means rather than pooled into one.
	"""

	dispatch_id: UUID7
	step_id: UUID7
	sealed_commit: NonEmptyStr
	"""The commit this review read, as it stood when it was read.

	Recorded rather than resolved at read time because a diff is a fixed comparison:
	a number attached to "whatever the branch tip is now" would move under the review
	that produced it, which is the failure :class:`ChangeUnit` refuses for its own
	range.
	"""

	human_minutes: float
	rework_fraction: float
	reviewed_by: NonEmptyStr
	reviewed_at: datetime

	@model_validator(mode="after")
	def _a_review_is_a_measurement(self) -> Self:
		if self.human_minutes < 0:
			raise ValueError(
				f"a review cannot cost {self.human_minutes:g} human-minutes; a negative "
				"cost would lower the per-diff total §1.4's claim is read against, which "
				"is the one direction a measurement of the binding constraint must not be "
				"able to move (§20.3 item 3)"
			)
		if not 0.0 <= self.rework_fraction <= 1.0:
			raise ValueError(
				f"the rework fraction of {self.rework_fraction:g} is not a share; 0.0 is "
				"a diff the reviewer accepted whole and 1.0 is one returned entire, and "
				"nothing outside that range is a fraction of a diff (§20.3 item 3)"
			)
		return self


V01_REVIEW_MINUTES_PER_DIFF: Final[float] = 15.0
"""§1.4's v0.1 alternative, as the number the per-diff measurement is read against.

The spec states it twice in prose — "roughly four units an hour" (§1.4) and "about fifteen
minutes a diff" (§20.3 item 3's comparison) — and the two are one rate. Held here so the
sentence and the number cannot drift into two statements of one fact, which is what
:data:`MAINTAINABILITY_NOT_VERIFIED` does for the debt term.

It is a *reading*, not a ceiling: nothing in this build refuses a diff that cost more than
this, for the reason :data:`THETA_GATE_BUILT` and :data:`MODE_M_CEILING` both give — a
measured actual may not move a bound, and one project's log cannot state §1.4's claim,
which is about a population.
"""


def diff_review_detail(
	reviews: tuple[DiffReview, ...],
	sealed_dispatches: int,
	gate_minutes: float | None,
) -> str:
	"""The per-diff reading, stated once so the report, the document and the CLI agree.

	Three surfaces state these figures, and a mean computed at three call sites is three
	numbers that agree only until one of them is edited. This is the one implementation;
	:meth:`DeliveryReport.diff_review_detail` and the CLI both call it.

	**Two comparisons, both stated.** §20.3 item 3 asks for the per-diff number so §1.4's
	claim can be read against v0.1's ~15 minutes a diff; §21 R13 asks for the comparison
	*the other way*, gate-minutes against diff-minutes, because R13's failure mode is
	integration risk growing as n² while human attention stays flat. A check that named
	only the diff total would leave R13 readable from the `sofact deliver` screen, where
	the two headings happen to be adjacent, and not from the report a deploy gate
	approves — which is where it has to be readable.

	The coverage clause is unconditional when diffs exist, because the mean is over the
	reviewed subset: a reader who takes it for the project's whole per-diff cost has been
	misled in §1.4's favour, which is the failure this instrument was built around.
	"""
	total = sum(r.human_minutes for r in reviews)
	coverage = len(reviews), sealed_dispatches
	if not reviews:
		return (
			"no diff review has been recorded, so the per-diff half of §20.3 item 3 is "
			"unmeasured rather than zero — and §1.4's claim cannot be read against the "
			"v0.1 alternative until it is. `sofact review` records one, and "
			"`sofact review --list` names the sealed diffs to read"
		)
	mean = total / len(reviews)
	rework = sum(r.rework_fraction for r in reviews) / len(reviews)
	gate_clause = (
		f"Gate-minutes {gate_minutes:g} against diff-minutes {total:g} is §21 R13's "
		"comparison, and the two are printed rather than divided: a ratio of a declared "
		"pair is a derived claim, and a verdict on it would be a ceiling raised on an "
		"unmeasured number. "
		if gate_minutes is not None
		else "No gate has recorded a cost, so §21 R13's gate-against-diff comparison "
		"cannot be read yet. "
	)
	return (
		f"{len(reviews)} diff(s) reviewed, {total:g} human-minute(s) total, "
		f"mean {mean:.1f} human-minute(s) per reviewed diff, mean rework fraction "
		f"{rework:.3f}. Coverage: {coverage[0]} of {coverage[1]} sealed diff(s). "
		+ gate_clause
		+ "§1.4 names v0.1's review rate as roughly four units an hour, about "
		f"{V01_REVIEW_MINUTES_PER_DIFF:g} minutes a diff, and this is the number to read "
		"against it. The mean is over the diffs that were reviewed, not over the "
		"project, so it is not the whole review cost — the coverage count beside it is "
		"what says so. A single project's log cannot settle §1.4 either way: "
		"sub-linearity is an observation about a population, not about one log"
	)


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
# FR-107 — the adversarial audit of the oracle set
# --------------------------------------------------------------------------- #

ORACLE_AUDIT_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-107",)
"""What one audit pass can carry out.

One requirement, and :attr:`OracleAuditReport.discharged` is what decides whether the
pass carried it: an audit over nothing probed makes no claim, which is a different state
from an audit that probed and found nothing. The two must not print the same line, which
is the rule :data:`INTEGRATION_REQUIREMENTS` states one phase later.
"""


class OracleAuditFinding(View):
	"""An oracle that was satisfied by nothing, and the clause it was meant to check (FR-107).

	FR-107's own words: an oracle "that can be satisfied without implementing the
	invariant". The finding is a measurement rather than a judgement about the command's
	spelling — the oracle was *run* against an empty workspace and reported SATISFIED — so
	it cannot be argued with by rewording a hint.

	There is deliberately no ``kind`` field and no companion enum. A single-member enum
	would name one thing and read as a capability, and the type *is* the kind: this class
	means "satisfied by nothing" and nothing else. A second finding class arrives with its
	own type when a second kind of defect is actually measured.
	"""

	clause_id: UUID7
	statement: NonEmptyStr
	oracle_class: OracleClass
	"""The operator's own declaration of how strong this oracle was supposed to be.

	Carried because the severity differs and the operator is the one who must judge it: a
	rank-1 property oracle that passes against nothing was claiming to establish an
	invariant and establishes nothing, while a rank-6 example passing there is a sample
	that sampled nothing. Both are findings; the first is the one that grants autonomy.
	"""

	command: NonEmptyStr
	"""The oracle's command, so the finding names something the operator can act on.

	An operator-facing value: this report reaches the ledger and the operator's screen,
	and nothing renders it into producer context. The producer-facing holdout is FR-106's
	and lives on :attr:`OracleDeclaration.held_out`; if an audit report ever does become
	producer input, that predicate is the one to apply here.
	"""

	detail: NonEmptyStr


class OracleAuditSkip(View):
	"""A clause this pass did not probe, in its own words, and why (FR-107).

	``statement`` is carried here and not on the probed set, and the asymmetry is the
	point: a *skipped* clause is one the operator may have to act on — by writing a
	command, or by accepting that the scoping rule excludes it — so naming it by id alone
	would force a lookup for the one list that needs reading. The probed clauses are the
	ones with nothing to report, and their ids answer the only question asked of them.
	"""

	clause_id: UUID7
	statement: NonEmptyStr
	because: NonEmptyStr


class OracleAuditReport(View):
	"""One adversarial pass over a contract's oracle set (FR-107).

	Names the contract *and* its hash for the reason FR-139 gives a verdict the same
	treatment: a finding is only actionable against the exact oracle set it was measured
	on, and re-keying it to a later contract would attach an old measurement to oracles
	nobody ran.
	"""

	id: UUID7
	contract_id: UUID7
	contract_hash: str
	rendered_at: datetime
	probed: tuple[UUID7, ...] = ()
	"""Clauses whose oracle was run against an empty workspace and judged."""

	skipped: tuple[OracleAuditSkip, ...] = ()
	"""Clauses this pass did not ask about. Reported rather than passed over: a clause the
	audit could not reach is not a clause it cleared, and FR-108's debt and FR-107's audit
	are different questions with different remedies."""

	findings: tuple[OracleAuditFinding, ...] = ()

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this pass actually carried out, which may be none.

		The same rule :attr:`~sofact.views.IntegrationCheck.discharged` states: a pass over
		no probed oracle claims nothing, however clean it looks. ``passed`` is not the test
		— a contract of intentions has nothing to probe and is reported as unclaimed rather
		than as audited.
		"""
		if not self.probed:
			return ()
		return ORACLE_AUDIT_REQUIREMENTS

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-107 this pass did not carry out.

		Derived from what was discharged rather than from a hand-kept list, so a pass that
		stops probing takes the requirement with it into this tuple. A contract whose every
		oracle is an intention naming no command lands here, and that is the honest reading:
		the audit asked nothing, so it found nothing, and a screen showing only the second
		half would report a gap as a clearance.
		"""
		discharged = set(self.discharged)
		return tuple(name for name in ORACLE_AUDIT_REQUIREMENTS if name not in discharged)

	@property
	def passed(self) -> bool:
		"""Whether the pass found no oracle satisfied by nothing.

		Says only that nothing was found, never that the oracles are good: a pass that
		probed nothing passes vacuously, and :attr:`not_implemented` is what distinguishes
		it from a pass that probed and found nothing.
		"""
		return not self.findings

	@property
	def weakest_audited_rank(self) -> int | None:
		"""The weakest rank among the probed oracles, or ``None`` when nothing was probed.

		Read off the findings rather than carried as a field, because the useful number is
		about the *unprobed* set and a second stored copy would be a second thing to keep
		true. ``None`` is not ``0``: nothing probed is an absent measurement.
		"""
		ranks = {ORACLE_RANK[finding.oracle_class] for finding in self.findings}
		return max(ranks) if ranks else None


# --------------------------------------------------------------------------- #
# FR-012-015 — the adversarial audit: hacker, fixer, sampling, exploit rate
# --------------------------------------------------------------------------- #

AUDIT_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-012", "FR-013", "FR-014", "FR-015")
"""What one adversarial pass can carry out.

Four requirements and they are one loop: a hacker that obtains a verdict without
solving the task (FR-012), a fixer that closes what it found and keeps the exploit as a
regression case (FR-013), a sampling rule that says how often the loop runs (FR-014),
and the rate that trends to zero (FR-015). A pass that ran no attempt carries none of
them — the rule :data:`ORACLE_AUDIT_REQUIREMENTS` states one section up.
"""

EXPLOIT_TRENDS_TO_ZERO: Final[str] = (
	"FR-015's target is zero, and a non-zero plateau means the lane is not actually "
	"verified. The rate is exploits found / adversarial passes run, per lane; a lane with "
	"no pass in the window is unmeasured rather than clean, because a zero over nothing is "
	"the forbidden target NFR-024 names."
)
"""FR-015's reading rule, stated once so the report and its reader use one sentence."""

AUDIT_SAMPLE_FLOOR: Final[int] = 3
"""The default N in FR-014's 1-in-N, declared rather than left to each deployment.

FR-014 makes N configurable and supplies no number, so a default has to be chosen
somewhere; choosing it here means two deployments that configured nothing still compute
the same rate. It is *not* a threshold the product has calibrated — §20.3 item 4 is
explicit that no rate has been measured yet — so the report states the N it used beside
every rate it prints.
"""


class HackTechnique(StrEnum):
	"""FR-012's five ways to obtain a passing verdict without solving the task.

	The set is the requirement's own list — "editing tests, hard-coding expected values,
	special-casing fixtures, disabling assertions, over-fitting to the sample" — and not
	an invention, because FR-015's rate is a rate *per technique*: a plateau explained by
	one technique is a different defect from a plateau spread across five.

	``DISABLED_ASSERTION`` and ``EDITED_TEST`` are the two a machine can *attempt* without
	a model, and they are the two that matter most: an oracle is a command, so editing the
	file the command runs and disabling the assertion inside it are the same act at two
	granularities, and both are exactly FR-139's integrity subject.
	"""

	EDITED_TEST = "edited_test"
	"""The oracle's own command was rewritten so it no longer checks what it claimed."""

	DISABLED_ASSERTION = "disabled_assertion"
	"""An assertion inside the oracle's target was neutralised, so it cannot fail."""

	HARDCODED_EXPECTED = "hardcoded_expected"
	"""The expected value was written into the implementation rather than computed."""

	SPECIAL_CASED_FIXTURE = "special_cased_fixture"
	"""The implementation recognises its own fixture and returns the expected answer."""

	OVERFIT_TO_SAMPLE = "overfit_to_sample"
	"""The implementation satisfies the supplied cases and nothing else."""


class HackOutcome(StrEnum):
	"""What the hacker's attempt did to the verdict (FR-012).

	``EXPLOITED`` is the finding and ``HELD`` is the good case, but ``NOT_ATTEMPTED`` is
	the one that must exist: FR-012's loop is sampled (FR-014), so most changes are not
	attacked, and a report that folded "we did not try" into "we tried and it held" would
	state a clearance over an unrun instrument. That is the same distinction
	:class:`~sofact.views.OracleAuditSkip` draws for FR-107.
	"""

	EXPLOITED = "exploited"
	"""The attempt obtained a passing verdict without solving the task. FR-012's defect."""

	HELD = "held"
	"""The attempt ran and the verdict did not flip. The only outcome that is evidence."""

	NOT_ATTEMPTED = "not_attempted"
	"""No attack was made, and there are two reasons, both of which mean no attack.

	FR-014's sample skipped this change, or the oracle already reported satisfied against
	the honest tree so there was no passing verdict to obtain. Both are "the audit did not
	attack", which is why they share an outcome: an oracle with nothing to obtain is not a
	resisted attack, and folding either into ``HELD`` would report a clearance over an
	instrument that never ran.
	"""

	INCONCLUSIVE = "inconclusive"
	"""The attack ran and the verdict could not be read, so it decided nothing.

	First-class for :class:`~sofact.views.ProbeOutcome`'s reason: rounding it to ``HELD``
	would fabricate a clearance and rounding it to ``EXPLOITED`` would report a defect
	nobody demonstrated.
	"""


class HackAttempt(View):
	"""One adversarial attempt against one change, and what it obtained (FR-012).

	Recorded as its own row rather than as a boolean on the dispatch, because the
	*technique* and the *evidence* are what a fixer acts on: "the audit failed" is not
	actionable, and "a rank-3 surface check reports SATISFIED after its assertion was
	removed" is.

	It carries an ``id``, unlike :class:`OracleAuditFinding`, because FR-013's fixer
	response points back at *this* attempt: a finding is read once, and an exploit has to
	be named by something for its fix to reference.
	"""

	id: UUID7
	clause_id: UUID7
	statement: NonEmptyStr
	technique: HackTechnique
	outcome: HackOutcome
	detail: NonEmptyStr
	oracle_class: OracleClass
	"""The declared class of the oracle attacked, because severity is not uniform.

	A rank-1 property oracle defeated by a hard-coded expected value was claiming to
	establish an invariant and establishes nothing; a rank-6 example defeated the same way
	is a sample that sampled nothing. Both are exploits, and FR-012's argument is about
	the first.
	"""

	baseline_command: NonEmptyStr | None = None
	"""The oracle's command before the attempt, so the finding names something to fix."""

	@property
	def is_finding(self) -> bool:
		"""Whether this attempt demonstrated an exploit. The one predicate that gates."""
		return self.outcome is HackOutcome.EXPLOITED


class ExploitFix(View):
	"""The fixer's response to one demonstrated exploit (FR-013).

	FR-013 has two halves and both are here. The first is that "every demonstrated
	exploit must produce a **fixer** action that closes it" — ``closed`` with the reason
	it is or is not. The second is that "the exploit must be retained as a permanent
	regression case", which is ``regression_case``: a path, or ``None`` with the reason
	it was not retained.

	The second half is the one that gets dropped. A fix that closes an exploit and keeps
	no case for it is a fix nobody can re-test, and the same exploit returns at the next
	refactor with the audit reporting a rate of zero in between.
	"""

	attempt_id: UUID7
	clause_id: UUID7
	closed: bool
	detail: NonEmptyStr
	regression_case: NonEmptyStr | None = None
	regression_because: NonEmptyStr | None = None

	@model_validator(mode="after")
	def _retention_is_whole(self) -> Self:
		if self.regression_case is None and self.regression_because is None:
			raise ValueError(
				"an exploit retained no regression case and gave no reason; FR-013 makes "
				"retention a requirement, and an absence with no reason is "
				"indistinguishable from an oversight"
			)
		if self.regression_case is not None and self.regression_because is not None:
			raise ValueError("a retained regression case does not also carry a reason for none")
		return self


class AdversarialAuditReport(View):
	"""One pass of FR-012's loop over a plan's changes, with FR-015's rate.

	Names the plan *and* the contract hash for the reason
	:class:`~sofact.views.OracleAuditReport` gives: an exploit is only actionable against
	the exact oracle set it defeated, and re-keying it to a later contract would attach an
	old finding to oracles nobody attacked.
	"""

	id: UUID7
	plan_id: UUID7
	contract_id: UUID7
	contract_hash: str
	rendered_at: datetime
	lane: ModuleClass | None = None
	"""The lane this pass audited, which is FR-015's unit of measurement.

	FR-015 says the rate is per lane and its plateau "means **the lane** is not actually
	verified", so a report that did not name one would make the requirement's own sentence
	uncomputable from the log. ``None`` is a real state and not a default: an audit driven
	over a whole contract rather than a lane has no lane, and saying ``None`` is how it
	declines to attribute its rate to one.

	This is the *declared* lane the caller sampled for — the argument
	:func:`sofact.adversarial.sample_decision` accepts and does not use — recorded rather
	than derived, because deriving it from the attempts would pick the lanes of whatever
	clauses happened to be probeable and report a per-lane rate that is really a per-clause
	one.
	"""

	attempts: tuple[HackAttempt, ...] = ()
	fixes: tuple[ExploitFix, ...] = ()
	sample_rate: int = AUDIT_SAMPLE_FLOOR
	"""FR-014's N, as used for this pass, reported beside the rate it produced.

	Carried rather than read from configuration at render time: a rate computed under
	1-in-3 and one computed under 1-in-30 are not comparable, and a reader of the log
	months later cannot recover which was in force.

	This is the **effective** N, not the configured floor: FR-014's third sentence raises
	it when a prior pass found an exploit, and a report carrying the configured value
	would say 1-in-3 about a pass that attacked every change.
	"""

	changes_considered: int = 0
	"""How many changes FR-014's rule was applied to, which is the rate's denominator."""

	@property
	def exploited(self) -> tuple[HackAttempt, ...]:
		"""The attempts that demonstrated an exploit. FR-012's findings."""
		return tuple(a for a in self.attempts if a.is_finding)

	@property
	def attempted(self) -> tuple[HackAttempt, ...]:
		"""Attempts that actually ran, which excludes what sampling skipped.

		The distinction :class:`HackOutcome` exists for: a pass over ten changes that
		attacked none is a pass that learned nothing, however many rows it wrote.
		"""
		return tuple(a for a in self.attempts if a.outcome is not HackOutcome.NOT_ATTEMPTED)

	@property
	def techniques_exploited(self) -> tuple[HackTechnique, ...]:
		"""Which of FR-012's five techniques got through, in the enum's order.

		FR-015 wants a rate, and a rate that has plateaued needs this beside it: one
		technique recurring is a fixable defect, five recurring is a subsystem that is not
		being audited at all.
		"""
		found = {a.technique for a in self.exploited}
		return tuple(t for t in HackTechnique if t in found)

	@property
	def exploits_unclosed(self) -> tuple[HackAttempt, ...]:
		"""Demonstrated exploits with no fixer action that closed them (FR-013).

		Derived from the fixes rather than counted, so an exploit whose fix was attempted
		and did not close it stays in this tuple. A pass that found one exploit and wrote
		one fix saying "not closed" is a pass with an open exploit.
		"""
		closed = {f.attempt_id for f in self.fixes if f.closed}
		return tuple(a for a in self.exploited if a.id not in closed)

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this pass carried out, which may be none.

		The rule :attr:`OracleAuditReport.discharged` states: a pass that attacked nothing
		claims nothing, and FR-013's half is only carried where an exploit was actually
		found to fix.
		"""
		if not self.attempted:
			return ()
		if not self.exploited:
			return ("FR-012", "FR-014", "FR-015")
		return AUDIT_REQUIREMENTS

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-012-015 this pass did not carry out."""
		discharged = set(self.discharged)
		return tuple(name for name in AUDIT_REQUIREMENTS if name not in discharged)

	@property
	def exploit_rate(self) -> float | None:
		"""FR-015's rate: exploits found per attempted pass, or ``None`` if none ran.

		``None`` rather than ``0.0`` over zero attempts, which is the whole point of
		:attr:`attempted` existing. A lane whose every change was sampled out has a rate
		that is *undefined*, and printing zero there would report the plateau FR-015
		warns about as the target state.
		"""
		if not self.attempted:
			return None
		return len(self.exploited) / len(self.attempted)

	@property
	def passed(self) -> bool:
		"""Whether the pass found no exploit at all.

		**A closed exploit does not make the pass clean**, and that is deliberate: FR-013's
		fix is a *claim* that the exploit is closed, and nothing in this pass verifies it —
		the verification is the next audit, which attacks the rewritten oracle. So a pass
		that found one exploit and wrote one fix saying "closed" still reports
		``passed = False``, and :attr:`exploits_unclosed` is the separate signal saying
		whether anything is still open. A gate that treated a fixer's word as a clearance
		would be accepting the producer's own declaration one level up, which is the whole
		of what FR-138 forbids.

		Says only that nothing was found, never that the changes are unattackable: a pass
		that attacked nothing passes vacuously, and :attr:`not_implemented` is what tells
		the two apart.
		"""
		return not self.exploited


# --------------------------------------------------------------------------- #
# FR-052-056, FR-134 — the factory's relationship to models it did not write
# --------------------------------------------------------------------------- #

AUTHORSHIP_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-053", "FR-055", "FR-134")
"""What one authorship check can carry out.

Three requirements with one subject: a model the factory trained or tuned must never be
the thing that *judges* (FR-053's oracle, FR-134's contract), and the factory must never
act on another party's behalf (FR-055). FR-052, FR-054 and FR-056 are absent because they
are not claims about *this* build's code — FR-052 and FR-054 are deployment decisions about
what a tuning run would target and what a vendor ships, and FR-056 needs a staging
sequence that does not exist. A check that listed them would report three requirements
discharged by a module that never looked at any of them, which is the defect
:data:`ORACLE_AUDIT_REQUIREMENTS` names one section up.
"""

AUTHORSHIP_READING: Final[str] = (
	"reachability = whether the transitive import closure of the authoring path contains "
	"any module that can talk to a model. The claim is *cannot reach*, not *does not call*: "
	"a guard that counted call sites would pass the moment someone added one, while an "
	"unreachable module cannot call out however the code above it changes."
)
"""FR-053/FR-134's reading rule, stated once so the report and its reader use one sentence."""

TUNED_MODEL_UNREACHABLE: Final[str] = (
	"FR-053 and FR-134 forbid a fine-tuned model from being an oracle or a contract author, "
	"and the factory holds no tuning capability (FR-052's target is a deployment's choice) "
	"so there is no tuned model to name. What this build can establish is the structural "
	"half: the paths that write a clause's words and the paths that assign its oracle "
	"cannot reach a model at all."
)
"""Why the check is structural rather than a model-identity assertion."""


class AuthorshipSurface(StrEnum):
	"""The two paths FR-053 and FR-134 name, each with its own closure.

	Two surfaces rather than one because the requirements are two: FR-053 constrains what
	an *oracle* may be, FR-134 constrains who may *author a contract*. They share an
	implementation today and that is a fact about this tree, not a fact about the rule — a
	build that let a model propose oracles but not contracts would satisfy one and violate
	the other, and a single check could not say which.
	"""

	CONTRACT_AUTHORING = "contract_authoring"
	"""Where a clause's statement and kind are decided (FR-134)."""

	ORACLE_AUTHORING = "oracle_authoring"
	"""Where a clause's oracle is chosen or manufactured (FR-053)."""


class AuthorshipFinding(View):
	"""One surface, its import closure, and whether a model is reachable from it.

	``reaching`` is the finding and ``closure`` is the evidence, both recorded: a reader
	told only "not reachable" has to re-derive the closure to check the claim, and the
	closure is what moves when someone adds an import three modules down. The list is
	sorted so two runs over one tree produce one document, which is what makes it
	diffable — an unordered set would print differently and a diff would be noise.
	"""

	surface: AuthorshipSurface
	closure: tuple[str, ...]
	"""The transitive ``sofact.*`` modules reachable from this surface, sorted."""

	reaching: tuple[str, ...]
	"""Modules in the closure that can reach a model, sorted. Empty is the requirement met.

	*Can reach a model* rather than *imports a model client*: the closure is transitive, so
	the check is whether any module the surface depends on — however deep — imports
	:mod:`sofact.llm`, ``httpx``, or anything else that opens a socket. A surface that
	imported a helper which imported the client would be reported here, which a
	direct-import check would miss.
	"""

	@property
	def clean(self) -> bool:
		"""Whether the surface cannot reach a model, which is FR-053/FR-134 satisfied."""
		return not self.reaching


class AuthorshipCheck(View):
	"""FR-053/FR-134's measurement over the tree, with FR-055's governance boundary.

	FR-055 is a different kind of claim from the other two and it is carried here rather
	than in a report of its own because the honest finding about it is a *structural* one:
	the factory must not autonomously set prices, accept customers, sign agreements, move
	money, or make commitments. That is not a guard to write, it is a capability that must
	be absent — and absence is checkable the same way reachability is. So the finding is a
	statement of what the tree does not contain, and ``governance_absent`` says whether the
	check found it absent rather than whether it looked.
	"""

	id: UUID7
	checked_at: datetime
	findings: tuple[AuthorshipFinding, ...]

	governance_absent: bool
	"""Whether no module in the tree reaches a payment, agreement or pricing interface.

	``True`` means the check looked and found none. It is a *negative* finding and the
	type says so by being a boolean beside a ``governance_reason`` rather than by being an
	empty tuple: an empty tuple of findings cannot distinguish "nothing found" from
	"nothing looked for".
	"""

	governance_reason: NonEmptyStr
	"""Why the boundary is absent, in the tree's own terms rather than in a promise."""

	@model_validator(mode="after")
	def _every_surface_is_measured_once(self) -> Self:
		if not self.findings:
			raise ValueError(
				"an authorship check with no findings checked nothing: FR-053 and FR-134 "
				"are claims about two named surfaces, and a check that measured neither "
				"would report them clean by never looking (NFR-024)"
			)
		seen = [f.surface for f in self.findings]
		duplicates = sorted({s.value for s in seen if seen.count(s) > 1})
		if duplicates:
			raise ValueError(
				f"surface(s) {duplicates} measured more than once: two findings for one "
				"surface means the reader picks, and the pick is the verdict"
			)
		return self

	def finding(self, surface: AuthorshipSurface) -> AuthorshipFinding | None:
		"""This surface's finding, or ``None`` when the check did not measure it."""
		return next((f for f in self.findings if f.surface is surface), None)

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this check actually carried out, which may be none.

		The rule :attr:`OracleAuditReport.discharged` states: a check that measured no
		surface claims nothing. Every surface is required by the type, so the empty case is
		reachable only by a caller constructing the model with an empty tuple, which the
		validator refuses — the property is here because the *reader* is a report that has
		to print the same three-way distinction as every other measurement in this file.
		"""
		if not self.findings:
			return ()
		covered = {f.surface for f in self.findings}
		carried: list[str] = []
		if AuthorshipSurface.CONTRACT_AUTHORING in covered:
			carried.append("FR-134")
		if AuthorshipSurface.ORACLE_AUTHORING in covered:
			carried.append("FR-053")
		if self.governance_absent:
			carried.append("FR-055")
		return tuple(name for name in AUTHORSHIP_REQUIREMENTS if name in carried)

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-053/FR-055/FR-134 this check did not carry out."""
		discharged = set(self.discharged)
		return tuple(name for name in AUTHORSHIP_REQUIREMENTS if name not in discharged)

	@property
	def clean(self) -> bool:
		"""Whether every measured surface is model-free and the boundary is absent.

		Says only that the surfaces *cannot reach* a model, never that a tuned model was
		checked for: nothing in this build tunes one (FR-052), so a claim that a tuned model
		is not an oracle would be a claim about a thing that does not exist. The
		distinction is what :data:`TUNED_MODEL_UNREACHABLE` states, and it is why the
		report prints it beside the verdict.
		"""
		return all(f.clean for f in self.findings) and self.governance_absent

	@property
	def rendered(self) -> str:
		"""The verdict, the evidence, and the structural limit, in the report's own words."""
		lines = [
			f"FR-053/FR-134: {len(self.findings)} authoring surface(s) measured, "
			f"{sum(1 for f in self.findings if f.clean)} model-free"
		]
		for finding in self.findings:
			if finding.clean:
				lines.append(
					f"  {finding.surface.value}: cannot reach a model "
					f"({len(finding.closure)} module(s) in the closure)"
				)
			else:
				lines.append(
					f"  {finding.surface.value}: REACHES a model via " + ", ".join(finding.reaching)
				)
		lines.append(f"FR-055: {self.governance_reason}")
		return "\n".join(lines)


# --------------------------------------------------------------------------- #
# FR-021-023 — the escape oracle
# --------------------------------------------------------------------------- #

ESCAPE_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-021", "FR-022", "FR-023")
"""What one escape measurement can carry out.

Three requirements, and :attr:`EscapeReport.discharged` decides whether a reading
carried them: a rate over zero deployments makes no claim, which is a different state
from a rate of zero over deployments that all held. The two must not print the same
line, which is the rule :data:`ORACLE_AUDIT_REQUIREMENTS` states one phase earlier.
"""

ESCAPE_RATE_READING: Final[str] = (
	"rate = distinct defects recorded against the lane / distinct deployed reports whose "
	"traceability chain reaches a module of that lane. The denominator includes the "
	"deployment an escape escaped from, so the rate is conservatively high; the numerator "
	"counts a defect once however many events it produced, so a revert followed by a "
	"hotfix is one escape rather than two."
)
"""FR-022's reading rule, stated once so the report and its reader use one sentence.

A rate whose numerator and denominator rules are implicit is a rate two readers compute
differently from one ledger, which is the failure the rule exists to prevent.
"""


class EscapeKind(StrEnum):
	"""FR-021's three escape events, and its own three words.

	The set is the requirement's, not an invention: "revert, hot-fix, or incident
	implicating the same defect". A fourth kind would need a requirement to name it, and a
	free-text ``kind`` would make FR-022's per-kind breakdown ungroupable.
	"""

	REVERT = "revert"
	HOTFIX = "hotfix"
	INCIDENT = "incident"


class EscapeEvent(View):
	"""One escape: a deployed change that reality rejected (FR-021).

	FR-021 asks every accepted change to be "tracked forward through deploy", with escape
	events "recorded against the change, its lane, its oracle-strength band, and its
	autonomy level". This type carries the first two; the band and the level are *derived*
	at read time from the change's contract and its module class rather than copied here.
	Storing them would freeze the numbers in force on the day of recording, and FR-023
	reads the *current* rate to decide the *current* ceiling — a frozen band would let a
	re-measured contract keep lowering an autonomy it no longer carries.
	:attr:`EscapeReport` states the choice, so a reader does not have to infer it.

	``lane`` is the operator's, and :meth:`~sofact.service.FactoryService.record_escape`
	validates it against the report's own chain. Deriving it would discard the one thing
	only the operator knows — *which* module broke, when a deployment spans several —
	while validating it makes naming a lane that was never deployed impossible.
	"""

	id: UUID7
	report_id: UUID7
	"""The delivery that escaped. This is what makes "tracked forward through deploy"
	checkable: an escape names the deployment it got past, and recording refuses one that
	names a report no deploy record approved (FR-021, FR-119)."""

	lane: ModuleClass
	kind: EscapeKind
	defect: NonEmptyStr
	"""What was wrong, in the operator's words. The rate's numerator counts *distinct*
	values of this field per lane, so one defect that took a revert and then a hotfix is
	one escape rather than two (FR-022)."""

	module: NonEmptyStr | None = None
	"""The module that broke, when the operator can name it (FR-127).

	``lane`` is a *class* — G4 may be four modules — so a lane-wide escape attributes to
	every clause those modules cite, which is a candidate set rather than the "intent
	clause that was misunderstood" FR-127 asks for. The operator who recorded the escape
	is the only one who knows which module it was, and this field is where they say so:
	naming one narrows the attribution to that module's clauses, and
	:meth:`~sofact.service.FactoryService.record_escape` refuses a name the deployment did
	not build or one outside the lane it was filed against.

	Optional, because an incident report often cannot say, and a required field would be
	filled with a guess — which is worse than a candidate set that says it is one.
	"""

	recorded_by: NonEmptyStr
	recorded_at: datetime
	note: NonEmptyStr | None = None


class EscapeBudget(View):
	"""One lane's declared escape budget, and who declared it (FR-023).

	FR-023 says "a lane whose escape rate exceeds its **declared** budget". Declared, so
	there is no default: §20.3 item 4 records that no escape baseline exists until there
	has been a deployment, and NFR-024 forbids reporting a target the product has not
	measured. Inventing a threshold here would be exactly the invented target that
	requirement refuses, so an undeclared lane is *unbudgeted* — reported as such, and
	left unreduced.

	The budget is a rate, not a count: a lane deployed once that escaped once and a lane
	deployed a hundred times that escaped once are not the same safety story, and only the
	rate distinguishes them.
	"""

	lane: ModuleClass
	maximum_rate: float
	declared_by: NonEmptyStr

	@model_validator(mode="after")
	def _a_budget_bounds_a_rate(self) -> Self:
		if not 0.0 <= self.maximum_rate <= 1.0:
			raise ValueError(
				f"the escape budget of {self.maximum_rate:g} is not a rate; 0.0 is a lane "
				"that must escape never and 1.0 is one every deployment of which may escape, "
				"and nothing outside that range is a share of deployments (FR-023)"
			)
		return self


class EscapeOverride(View):
	"""An operator's decision to run a lane over its escape budget, attributed (FR-023).

	FR-023's last sentence is "manual override must be logged and attributed", and both
	words carry weight. *Logged*, so this is a ledger row rather than a flag on a render:
	the reduction it lifts persists until the rate returns to budget, so the override that
	lifts it must persist too, and a render parameter would evaporate at the next render
	and silently restore the reduction. *Attributed*, so the field is a name rather than a
	boolean — an override with nobody attached is indistinguishable from the silent
	downgrade FR-031 forbids, which is why ``topology_override`` is a string for the same
	reason.

	Reading is latest-per-lane (:meth:`ProjectState.latest_escape_override`), the rule
	:meth:`ProjectState.gate_cost` states: two overrides of one lane are a decision and a
	revision of it, not two decisions.
	"""

	lane: ModuleClass
	accepted_by: NonEmptyStr
	reason: NonEmptyStr
	"""Why, in the operator's words. FR-023's whole mechanism is that a human may accept a
	risk the measurement flags; an override with no reason records that the risk was taken
	and not what was understood about it."""

	recorded_at: datetime


class LaneEscape(View):
	"""One lane's escape measurement, and what it did to the lane's ceiling (FR-022).

	Every field is required, including the awkward ones: ``budget`` is ``None`` rather
	than a default because an undeclared budget is the absence of a declaration, and
	``over_budget`` is ``None`` for the same reason — a lane with no budget is not *within*
	it, it is unbudgeted, and collapsing those would report a clearance the operator never
	declared.
	"""

	lane: ModuleClass
	deployed_changes: int
	"""Distinct deployed reports whose chain reaches a module of this lane."""

	escapes: int
	"""Distinct defects recorded against this lane across those deployments."""

	rate: float
	budget: EscapeBudget | None
	over_budget: bool | None
	"""``None`` when the lane is unbudgeted, which is not ``False``."""

	granted_ceiling: AutonomyLevel
	"""§14's ceiling for the class, before FR-023."""

	oracle_ranks: tuple[int, ...] = ()
	"""The oracle-strength bands FR-021 asks an escape be attributed to, weakest first.

	One rank per *deployed change* whose chain reaches this lane, deduplicated. Derived at
	read time from each change's own contract (:attr:`Contract.weakest_oracle_rank`) rather
	than stored on the escape, for the reason :attr:`EscapeEvent` states: a stored band
	would be the number in force on the day, and FR-023 reads the *current* rate to decide
	the *current* ceiling.

	Empty when no contract in the log accounts for this lane's deployments — a gap the
	report shows rather than fills with a guess, since a band nobody derived is not a
	measurement (NFR-024).
	"""

	reduced_ceiling: AutonomyLevel
	"""The ceiling after FR-023. Equal to :attr:`granted_ceiling` when not over budget."""

	override: EscapeOverride | None = None
	"""The operator's acceptance, when one is in force for this lane (FR-023).

	Carried on the row rather than looked up beside it so the report answers "who accepted
	this?" in the same place it answers "how far over is it?" — an over-budget lane whose
	row did not name its override would leave the reader to cross-reference the ledger for
	the one fact FR-023 requires be attributable.
	"""

	@property
	def reduced(self) -> bool:
		"""Whether FR-023 lowered this lane, which is a different fact from being over
		budget: an over-budget lane already at L0 is not lowered further, and one an
		operator accepted is not lowered at all."""
		return self.reduced_ceiling < self.granted_ceiling

	@property
	def reduced_by_fr_023(self) -> bool:
		"""Whether the reduction is in force: over budget, and not accepted by a named human."""
		return bool(self.over_budget) and self.override is None


class EscapeReport(View):
	"""FR-022's measurement: the escape rate per lane and per autonomy level.

	The **primary safety metric**, and the requirement's argument for why is the reason
	this type holds no producer input: FR-022 says the rate "cannot be gamed by the
	producer because it is measured by events the producer does not author". Every field
	here is a fold over deploy records and operator-recorded escapes. Nothing in the
	factory's verification path writes to either.

	Its honest limit is a *different* claim and is stated rather than conflated: the rate
	is only as complete as the operator's recording. A producer cannot inflate it, but an
	operator who does not record an escape lowers it, and "not gameable by the producer"
	must not be read as "not gameable". That limit is FR-021's recording discipline, and
	:attr:`caveats` names it.
	"""

	id: UUID7
	rendered_at: datetime
	lanes: tuple[LaneEscape, ...] = ()
	"""One entry per lane that was *measured*, which includes lanes with zero escapes.

	A lane with deployments and no escapes is the good case and must be visible; omitting
	it would make the report a list of problems rather than a measurement."""

	unbudgeted: tuple[ModuleClass, ...] = ()
	"""Lanes with deployments and no declared budget. Reported, never reduced: FR-023
	reduces a lane "whose escape rate exceeds its declared budget", and a lane with no
	declaration is not one whose rate exceeds it."""

	orphan_deployments: int = 0
	"""Deployed reports whose traceability chain reaches no module, so they fall in no
	lane's denominator. Counted rather than dropped: a report the metric cannot place is a
	gap in the measurement, and a reader is owed the number."""

	deployed_reports: int = 0
	"""Distinct deployed reports the measurement saw, placed or not.

	A field rather than ``sum(lane.deployed_changes)``, because one report spanning four
	lanes is *one* change and appears in four denominators — summing the rows would report
	it as four, and this number is what :attr:`discharged` reads to decide whether the
	reading claims anything at all.
	"""

	scope: DeploymentScope | None = None
	"""The target this deployment declared, when it declared one (FR-157).

	Carried on the *measurement* rather than beside it, because FR-157's whole point is
	that a rate with no declared ambition is a number nobody is aiming at: "the θ_hi = 0.80
	gate ... must not be imposed as a default" is the same statement read the other way,
	and a deployment that declared no target has one fewer thing to be measured against.
	``None`` means *no target was declared*, which the report states rather than assuming
	:data:`PERSONAL_AUTONOMY_BAND`'s floor — a default target would be a product-scoped
	one, which is exactly what the requirement refuses.
	"""

	delivered_ceiling: AutonomyLevel | None = None
	"""The delivery's own number, when the caller supplied one, for :attr:`meets_target`.

	``None`` when the measurement is read for its own sake rather than as part of a
	delivery. The comparison FR-157 asks for is against what the *deployment* may claim,
	and this module does not compute that — :func:`sofact.delivery.ceiling` does, from a
	contract and a decomposition this fold does not hold. So the number arrives from the
	caller and its absence is a state the report names rather than fills.
	"""

	@property
	def meets_target(self) -> bool | None:
		"""Whether the delivery reaches the declared target (FR-157).

		``None`` in either of two cases, and they are the same case: no target was declared,
		or no delivery ceiling was supplied. A boolean here would have to be ``False`` for
		both, and ``False`` reads as a *shortfall* — which is a claim about a comparison
		that was never made. The report says which of the three states it is in, which is
		the rule :attr:`discharged` keeps one property down.
		"""
		if self.scope is None or self.delivered_ceiling is None:
			return None
		return self.scope.met_by(self.delivered_ceiling)

	@property
	def target_shortfall(self) -> int | None:
		"""How many levels short of the target the delivery is, or ``None`` (FR-157).

		Signed rather than clamped: a delivery above its target is a real and reportable
		state — a deployment aiming at L2 whose modules sustain L3 has headroom, not a
		problem — and clamping at zero would erase the difference between meeting a target
		exactly and exceeding it.
		"""
		if self.meets_target is None:
			return None
		assert self.scope is not None and self.delivered_ceiling is not None
		return int(self.scope.target) - int(self.delivered_ceiling)

	@property
	def deployed_changes(self) -> int:
		"""How many distinct deployed reports the measurement saw, placed or not."""
		return self.deployed_reports

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this reading carried out, which may be none.

		The rule :attr:`OracleAuditReport.discharged` states: a rate over zero deployments
		claims nothing. A project with no deploy has no ground truth yet, and a screen
		showing "0 escapes" over it would report the absence of a measurement as a clean
		bill of health.
		"""
		if not self.deployed_changes:
			return ()
		return ESCAPE_REQUIREMENTS

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-021-023 this reading did not carry out."""
		discharged = set(self.discharged)
		return tuple(name for name in ESCAPE_REQUIREMENTS if name not in discharged)

	@property
	def over_budget(self) -> tuple[LaneEscape, ...]:
		"""The lanes whose rate exceeds their declared budget (FR-023)."""
		return tuple(lane for lane in self.lanes if lane.over_budget)

	@property
	def by_autonomy_level(self) -> dict[AutonomyLevel, tuple[LaneEscape, ...]]:
		"""FR-022's second axis: the same lanes grouped by the ceiling they were granted.

		Grouped by the *granted* ceiling — §14's class ceiling — rather than by the
		delivery's, because in Mode G the delivery axis is degenerate: FR-123 caps every
		Mode G delivery at :data:`MODE_G_CEILING` unconditionally, so every lane would land
		in one bucket and the grouping would read as a finding when it is a cap. That is
		stated on the report rather than left for a reader to notice, because a
		single-bucket breakdown looks like a result.
		"""
		grouped: dict[AutonomyLevel, list[LaneEscape]] = {}
		for lane in self.lanes:
			grouped.setdefault(lane.granted_ceiling, []).append(lane)
		return {level: tuple(rows) for level, rows in sorted(grouped.items())}

	@property
	def caveats(self) -> tuple[str, ...]:
		"""What this measurement does not claim, stated rather than left to inference.

		Three sentences, each closing a reading a careful operator would otherwise supply:
		the numerator and denominator rules, the operator-recording limit that FR-022's
		"cannot be gamed" must not be stretched over, and the derived-band choice that
		FR-021's "its oracle-strength band, and its autonomy level" is satisfied by
		derivation rather than by a stored copy.
		"""
		return (
			ESCAPE_RATE_READING,
			"the rate is complete only as far as the operator records escapes; FR-022's "
			"claim is that no *producer* authors an input to it, which is not the claim "
			"that it cannot be gamed at all",
			"FR-021's oracle-strength band and autonomy level are derived at read time from "
			"the change's contract and module class rather than stored on the escape, so a "
			"re-measured contract is judged at the strength it now carries",
		)


def lane_ceiling(
	lane: ModuleClass,
	*,
	rate: float,
	budget: EscapeBudget | None,
	override: EscapeOverride | None = None,
) -> AutonomyLevel:
	"""The ceiling a lane may claim once FR-023's reduction is applied.

	§14's class ceiling, lowered **one level** when the lane's rate exceeds its declared
	budget. One level because §5.4's own modifier unit is "-1 level": the ladder is
	ordinal and the spec supplies no other quantum, so a larger step would be an invented
	policy rather than a reading of the requirement.

	**Not cumulative.** The reduction is a function of the *current* rate, so it is in
	force while the rate is over budget and lifts when the rate returns — which is what
	"reduced **until** escape rate returns to budget" says. A ratchet that remembered
	every bad period would make a lane's ceiling a function of its history rather than of
	its present, and no requirement asks for that.

	An unbudgeted lane is unchanged: FR-023 reduces a lane over "its declared budget", and
	a lane with no declaration is not one whose rate exceeds it. Guessing a threshold
	would be NFR-024's forbidden target.

	An override **lifts the reduction**, because that is what a manual override of an
	automatic reduction means: the operator has accepted the risk the measurement flags and
	says so by name. It is a ledger row rather than a flag precisely so that acceptance is
	not silent — and it moves the ceiling and the deploy gate's refusal together, since a
	delivery that passed its gate while still reporting a reduced ceiling would be
	reporting two contradictory things. The measurement is not erased by the override:
	:attr:`LaneEscape.rate`, ``budget`` and ``over_budget`` all still carry it, so a reader
	sees that the lane is over budget *and* that a named person accepted it.
	"""
	granted = MODULE_CLASS_CEILING[lane]
	if budget is None or rate <= budget.maximum_rate:
		return granted
	if override is not None:
		return granted
	return AutonomyLevel(max(int(granted) - 1, int(AutonomyLevel.L0)))


# --------------------------------------------------------------------------- #
# FR-159 — the change-cost instrument (D18)
# --------------------------------------------------------------------------- #


class ChangeUnit(View):
	"""One pinned change, held out from the producer (FR-159).

	FR-159's instrument is differential, which is what makes it buildable without a new
	model capability: decay is a *trend*, and a trend needs a consistent measurement
	rather than a correct one. So the unit is **pinned** — declared before the work, with
	the scope it is expected to touch — because a unit chosen after the diff is a unit
	chosen by the person who wrote the diff.

	``expected_modules`` is the declared scope, and it is what makes the comparison
	*comparable*: FR-159 tracks "a rising footprint on comparable change units", and two
	units are comparable when they declared the same scope. It is deliberately not
	compared against the modules the diff actually touched — that would make the
	comparison a tautology, since a unit that crossed more modules would be compared
	against a baseline that also crossed more.

	``clause_id`` ties the unit to an intent clause when one owns it, so a footprint that
	rose can be read against *what* got more expensive to change rather than only *that*
	something did.
	"""

	id: UUID7
	statement: NonEmptyStr
	"""What the change is, in the operator's words. Not parsed and not verified."""

	scope: NonEmptyStr
	"""The comparison group: units declaring the same scope are compared to each other."""

	expected_modules: tuple[NonEmptyStr, ...] = ()
	"""The modules the unit declares it will touch, which is a *prediction*, not a bound.

	A unit that crossed more modules than it declared is the ordinary case and is
	reported as ``crossed`` rather than refused: FR-159's quantity is what a change cost,
	and a unit that could not be confined to its declared modules cost more by exactly
	that fact.
	"""

	clause_id: UUID7 | None = None
	declared_at: datetime | None = None

	base_commit: NonEmptyStr | None = None
	"""The commit the unit's work started from, or ``None`` when none is recorded.

	``None`` is the ordinary state of a unit that has been *pinned* and not yet landed,
	which is why both this and :attr:`head_commit` are optional: FR-159's units are held
	out from the producer before the work, and a unit whose work has not happened has no
	range. It is measured as unmeasured rather than as a zero footprint
	(:data:`CHANGE_COST_BASELINE_UNMEASURED`).
	"""

	head_commit: NonEmptyStr | None = None
	"""The commit the unit's work ended at, or ``None`` when none is recorded.

	Stored as a *sha* rather than defaulting to ``HEAD``, because FR-159's units are
	**pinned**: a unit that read ``HEAD`` at measurement time would measure whatever had
	landed since, which is the opposite of a fixed comparison.
	"""

	@property
	def measured_range(self) -> tuple[str, str] | None:
		"""``(base, head)`` when both ends are recorded, else ``None``."""
		if self.base_commit is None or self.head_commit is None:
			return None
		return (self.base_commit, self.head_commit)


class ChangeFootprint(View):
	"""The mechanical diff one change unit produced (FR-159).

	Mechanical, and the word is the whole of the instrument's honesty: every number here
	is read from ``git diff --numstat`` and ``git diff`` between two commits. Nothing in
	this type required a model, a judgement, or a producer's cooperation, which is why
	FR-159 is the one instrument [S24] leaves available.

	**Binary files are counted as files and contribute no lines.** ``--numstat`` reports
	``-`` for both counts on a binary path, and reading that as zero would let a unit
	that added a 40 MB artefact report the footprint of a comment. The counts are ``None``
	rather than 0 for such a path, and the unit's line totals exclude it — stated here
	because a reader comparing two units needs to know that one of them may be carrying a
	binary the other is not.
	"""

	files_touched: int
	"""Paths the diff names, renames counted once — a rename is one file, not two."""

	hunks: int
	"""``@@`` blocks across every changed file. The count that distinguishes one edit in
	forty files from forty edits in one, which a line count alone cannot."""

	lines_added: int
	lines_removed: int
	modules_crossed: int
	"""Distinct top-level packages the touched paths fall under.

	A coarser unit than the file and a finer one than the count, and the one FR-159 names:
	fifty files inside one package is a large change to one thing, and fifty files across
	fifty packages is a change to fifty things.
	"""

	binary_paths: tuple[NonEmptyStr, ...] = ()
	"""Touched paths whose line counts git declines to report. Named, not silently zeroed."""

	@property
	def lines_changed(self) -> int:
		"""Added plus removed, which is the spec's "lines changed"."""
		return self.lines_added + self.lines_removed

	@property
	def magnitude(self) -> int:
		"""The single number two units of one scope are compared by (FR-159).

		``lines_changed + hunks``, and the hunk term is not decoration: two units can
		change the same number of lines while one makes a single contiguous edit and the
		other makes thirty scattered ones, and it is the scattered one that is shotgun
		surgery. A lines-only magnitude would call those two equal.
		"""
		return self.lines_changed + self.hunks


class ChangeCostRow(View):
	"""One unit's footprint, and what it is measured against (FR-159).

	Every field is required, including the awkward ones, for :class:`LaneEscape`'s reason:
	``measured`` is ``False`` rather than the row being absent, because a unit with no
	recorded diff is a *gap in the measurement* and a report that dropped it would show a
	trend over the units that happened to have one.
	"""

	unit: ChangeUnit
	measured: bool
	"""Whether a diff was read for this unit. ``False`` is not "clean"."""

	unmeasured_because: str | None = None
	"""Why no diff was read, named. Required when :attr:`measured` is ``False``."""

	footprint: ChangeFootprint | None = None
	"""``None`` exactly when :attr:`measured` is ``False``, and never a zeroed one."""

	baseline: float | None = None
	"""The median magnitude of this scope's *earlier* measured units, or ``None``.

	``None`` when this unit is the first of its scope — the unmeasured baseline ADR-0054
	established as the honest answer. Not ``0.0``, which would make the first unit of
	every scope an infinite regression.
	"""

	@property
	def ratio(self) -> float | None:
		"""This unit's magnitude over its baseline, or ``None`` when there is no baseline."""
		if not self.measured or self.footprint is None or not self.baseline:
			return None
		return self.footprint.magnitude / self.baseline

	@property
	def rose(self) -> bool | None:
		"""Whether the footprint rose past :data:`CHANGE_COST_RISE_FACTOR` (FR-159).

		``None`` when there is no baseline, which is the third state and not ``False``: a
		unit with nothing to compare against has not held steady, it is unmeasured.
		"""
		ratio = self.ratio
		if ratio is None:
			return None
		return ratio >= CHANGE_COST_RISE_FACTOR


class ChangeCostReport(View):
	"""FR-159's measurement: the footprint per pinned unit, and the trend per scope.

	A fold over pinned units and a repository's own history. It runs no oracle, reads no
	contract, and decides nothing — :data:`CHANGE_COST_NOT_A_VERIFICATION` says so on every
	report, because the pressure on a proxy that produces a number is to promote it.
	"""

	id: UUID7
	rendered_at: datetime
	rows: tuple[ChangeCostRow, ...] = ()
	repository: str | None = None
	"""The tree the diffs were read from, or ``None`` when none was read.

	Named because a footprint is a fact about *one* repository: two projects' units are
	not comparable, and a report that pooled them would trend a mix of work rather than a
	cost.
	"""

	@property
	def measured_rows(self) -> tuple[ChangeCostRow, ...]:
		"""The units a diff was actually read for."""
		return tuple(row for row in self.rows if row.measured)

	@property
	def unmeasured_rows(self) -> tuple[ChangeCostRow, ...]:
		"""The units with no diff, which are gaps and are reported as gaps."""
		return tuple(row for row in self.rows if not row.measured)

	@property
	def scopes(self) -> dict[str, tuple[ChangeCostRow, ...]]:
		"""The measured units grouped by the scope they declared (FR-159).

		Grouped by declaration rather than inferred, because "comparable" is a claim the
		unit makes about itself before the work: a grouping derived from the diff would
		put every unit in a group of its own, which is a trend over one point.
		"""
		grouped: dict[str, list[ChangeCostRow]] = {}
		for row in self.measured_rows:
			grouped.setdefault(row.unit.scope, []).append(row)
		return {scope: tuple(rows) for scope, rows in sorted(grouped.items())}

	@property
	def trends(self) -> dict[str, tuple[float, ...]]:
		"""Each scope's measured magnitudes in declaration order — the trend itself."""
		return {
			scope: tuple(row.footprint.magnitude for row in rows if row.footprint is not None)
			for scope, rows in self.scopes.items()
		}

	@property
	def rising(self) -> tuple[ChangeCostRow, ...]:
		"""The units whose footprint rose past the factor, on a scope with a baseline."""
		return tuple(row for row in self.measured_rows if row.rose)

	@property
	def unmeasured_scopes(self) -> tuple[str, ...]:
		"""Scopes with fewer than two measured units, so no trend is claimed for them.

		This is ADR-0054's report shape: the instrument exists and the baseline does not,
		and the honest output is the scope's *name* rather than a flat line.
		"""
		return tuple(scope for scope, rows in self.scopes.items() if len(rows) < 2)

	@property
	def declared_baseline(self) -> str:
		"""FR-159's baseline statement, which is a constant for FR-158(c)'s reason."""
		return CHANGE_COST_BASELINE_UNMEASURED

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this reading carried out, which may be none (NFR-024).

		A trend over zero measured units claims nothing, and so does one over a single unit
		per scope: :data:`CHANGE_COST_BASELINE_UNMEASURED` is the statement, and this
		property is the machine-readable half of it.
		"""
		trended = [scope for scope, rows in self.scopes.items() if len(rows) >= 2]
		if not trended:
			return ()
		return CHANGE_COST_REQUIREMENTS

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-159 this reading did not carry out."""
		discharged = set(self.discharged)
		return tuple(name for name in CHANGE_COST_REQUIREMENTS if name not in discharged)

	@property
	def caveats(self) -> tuple[str, ...]:
		"""What this measurement does not claim, stated rather than left to inference."""
		return (
			CHANGE_COST_PROXY_DECLARATION,
			CHANGE_COST_AXIS,
			CHANGE_COST_NOT_A_VERIFICATION,
		)


# --------------------------------------------------------------------------- #
# FR-157 — the deployment-scoped autonomy target
# --------------------------------------------------------------------------- #


class Consumer(StrEnum):
	"""Who consumes the delivered artefact, which is what FR-157 scopes the target by.

	The requirement's whole move is that the *same* machinery carries two thresholds
	because the cost of a false completion differs by who bears it: "a false completion
	costs a third party a production incident and costs the operator a debugging session
	with code they did not write — both real, neither equal".
	"""

	OPERATOR = "operator"
	"""D17's personal-use case: the blast radius is the operator's own working time."""

	THIRD_PARTY = "third_party"
	"""The artefact is consumed by someone who did not commission it."""


PERSONAL_AUTONOMY_BAND: Final[tuple[AutonomyLevel, AutonomyLevel]] = (
	AutonomyLevel.L2,
	AutonomyLevel.L3,
)
"""FR-157's "required ceiling is L2–L3 with escape-rate tracking" for D17's case.

A *band* rather than a number because the requirement states a range: L2 is the floor
below which the escape-rate tracking it mandates is measuring something nobody is aiming
at, and L3 is the top of what a personal deployment may claim. L4 is outside it in both
directions of reasoning — above because FR-157 says the θ_hi = 0.80 gate "must not be
imposed as a default", and a target that could be reached by declaring it would be that
gate imposed by a side door.
"""

L4_GATE_THETA: Final[float] = 0.80
"""The measured oracle strength FR-157 leaves unchanged for third-party consumers.

FR-024–FR-035's gate. It is named here because FR-157 is the requirement that decides
*who it applies to*, and a number stated in one requirement and applied in another is a
number a reader has to go looking for.
"""

THETA_GATE_BUILT: Final[bool] = False
"""Whether this build can decide the θ ≥ 0.80 gate (FR-024–FR-035).

``False``, and the roadmap records why: the routing function, the autonomy ladder and the
θ computation are **Partly** — the ceilings half is built and the θ half is not, so
nothing in this build measures an oracle strength to compare against
:data:`L4_GATE_THETA`. It is a named constant rather than a comment so that a third-party
scope's refusal can say *which* thing is missing, and so that building FR-024–FR-035
flips one boolean instead of rewriting a sentence in three places.
"""


class DeploymentScope(View):
	"""The autonomy target one deployment is aiming at (FR-157).

	FR-157's requirement is that the target be "**deployment-scoped, not
	product-scoped**", and the roadmap recorded the gap precisely: the *inputs* existed —
	FR-107's audit and FR-022's escape rate — and "no deployment scope type carries 'this
	deployment targets L3', so nothing compares a measured rate against a declared
	ambition".

	So this type is the ambition, and :meth:`met_by` is the comparison. What makes it
	worth a type rather than a number in a config file is the refusal set: the two ways a
	declared target can be one this build cannot honour are both structural, and both are
	worth catching before a build rather than after a delivery.

	**A personal scope may not target L4.** FR-157 says the θ gate "must not be imposed as
	a default" for D17's case, and the symmetric error is a deployment that grants itself
	the level the gate exists to withhold — declaring the target would be the gate imposed
	by a side door, with the requirement's own remedy (measure, or do not claim) skipped.

	**A third-party scope may not target L4 either, and for a different reason.** There the
	gate applies unchanged, so L4 is reachable *through* it — and :data:`THETA_GATE_BUILT`
	is ``False``, so this build cannot decide it. The two refusals carry different
	sentences because they have different remedies: one is "you are not aiming at the right
	band", the other is "the instrument that would admit you is not built yet", and a
	single message would send the second operator looking for a setting.

	**Escape-rate tracking is required of both.** FR-157 names it beside the personal band,
	but its argument is general: with no external market there is no exogenous escape
	signal, so the rate is the only thing distinguishing an imagined product from a
	plausible-looking one. A scope that declares a target and declines the instrument is
	the target NFR-024 refuses — one the product has not measured.
	"""

	consumer: Consumer
	target: AutonomyLevel
	"""The ceiling this deployment is aiming at, inside :attr:`band`."""

	escape_tracking: bool
	"""Whether FR-022's rate is measured for this deployment.

	Required ``True``: a target with no instrument is an unmeasured target (NFR-024), and
	FR-157's own text pairs the personal band with "with escape-rate tracking".
	"""

	declared_by: NonEmptyStr
	declared_at: datetime
	note: NonEmptyStr | None = None

	@model_validator(mode="after")
	def _a_target_this_build_can_honour(self) -> Self:
		floor, ceiling = self.band
		if not self.escape_tracking:
			raise ValueError(
				f"the {self.consumer.value} scope declares a target of {self.target.name} "
				"with no escape-rate tracking; FR-157 pairs its band with the rate and "
				"FR-022 makes it the primary safety metric, so a declared target nobody "
				"measures is the unmeasured target NFR-024 refuses"
			)
		if self.consumer is Consumer.OPERATOR and not floor <= self.target <= ceiling:
			raise ValueError(
				f"a personal-use deployment targets {self.target.name}, outside FR-157's "
				f"required band {floor.name}-{ceiling.name}. Above it, the θ_hi = "
				f"{L4_GATE_THETA:g} gate that admits L4 must not be imposed as a default "
				"and must not be reached by declaring it either; below it, the escape-rate "
				"tracking the requirement mandates is measuring a level nobody is aiming at"
			)
		if (
			self.consumer is Consumer.THIRD_PARTY
			and self.target > AutonomyLevel.L3
			and not THETA_GATE_BUILT
		):
			raise ValueError(
				f"a third-party deployment targets {self.target.name}, which FR-157 admits "
				f"only through the unchanged θ_hi = {L4_GATE_THETA:g} gate (FR-024–FR-035) "
				f"— and that gate is not built in this build, so nothing here measures an "
				f"oracle strength to decide it. Declaring the target does not discharge the "
				f"gate"
			)
		return self

	@property
	def band(self) -> tuple[AutonomyLevel, AutonomyLevel]:
		"""The range a target may fall in for this consumer (FR-157).

		The personal band is the requirement's own L2 to L3. A third-party band runs to L4
		because the gate applies *unchanged* rather than being raised — so the top of the
		range is reachable in principle and by the gate in practice, which is the
		distinction :attr:`admits_l4` exists to keep.
		"""
		if self.consumer is Consumer.OPERATOR:
			return PERSONAL_AUTONOMY_BAND
		return (AutonomyLevel.L2, AutonomyLevel.L4)

	@property
	def admits_l4(self) -> bool:
		"""Whether this scope could reach L4 *in this build* (FR-157, FR-024 to FR-035).

		Both conditions are required and neither is a formality: a personal scope never
		does, whatever the gate's state, and a third-party scope does only once the gate
		can be decided. A property rather than a field because it is a fact about the
		build and the consumer, and a stored boolean would be a claim nothing checks.
		"""
		return self.consumer is Consumer.THIRD_PARTY and THETA_GATE_BUILT

	def met_by(self, ceiling: AutonomyLevel) -> bool:
		"""Whether a delivery's computed ceiling reaches this scope's target (FR-157).

		``ceiling`` is the delivery's number — :func:`sofact.delivery.ceiling`, FR-123's
		cap applied — and not the modules'. The target FR-157 scopes is what the
		*deployment* may claim, so comparing it against a per-module number would report a
		shortfall the delivery never had.
		"""
		return ceiling >= self.target

	@property
	def caveats(self) -> tuple[str, ...]:
		"""What a declared target does not claim, stated rather than left to inference.

		The same discipline :attr:`EscapeReport.caveats` keeps. A target is an *ambition*:
		it is not a measurement, it does not raise any ceiling, and the two directions of
		the personal band are refused for two different reasons that a reader of the
		number alone would collapse into one.
		"""
		return (
			"the target is an ambition and not a measurement: it raises no ceiling, and "
			"whether it is met is decided by comparing it against the delivery's own "
			"number (FR-157)",
			f"L4 is admitted only through the θ_hi = {L4_GATE_THETA:g} gate (FR-024–FR-035), "
			f"which is {'built' if THETA_GATE_BUILT else 'not built in this build'}; "
			f"a {self.consumer.value} deployment {'may' if self.admits_l4 else 'may not'} "
			f"reach it here",
			"the personal band's two ends are refused for different reasons — above it the "
			"gate must not be imposed as a default, below it the mandated escape-rate "
			"tracking would be measuring a level nobody aims at — so a target outside the "
			"band is not one error but one of two",
		)


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
	"""What a P7 integration check found (FR-110-116).

	Every kind here is produced by a check that runs. A kind the code cannot emit would
	be an enum member nothing reaches, which reads as a capability in the type and is a
	gap in the report.
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

	MODEL_INTERFACE_NOT_BOUND = "model_interface_not_bound"
	"""A model interface's clause reaches no module, so nothing was asked to expose it.

	FR-083's defect by construction: the model is the single source for interface
	definitions, so an interface the decomposition never bound to a module is a declared
	surface the system was never told to have.
	"""

	SURFACE_DISAGREES_WITH_MODEL = "surface_disagrees_with_model"
	"""A module's declared surface is not the one the model derives for its clauses (FR-083).

	This is the finding FR-083 exists to produce. A surface declared on a module *beside*
	the model is a second opinion about the same public names, and the two can differ —
	so the model is not the source, it is one of two sources. Derived surfaces cannot
	differ, and a hand-revised module is exactly the case that can, which is why the check
	compares rather than assumes.
	"""

	UNSATISFIED_SYSTEM_CRITERION = "unsatisfied_system_criterion"
	"""A system-level criterion has no satisfied verdict from any module (FR-116)."""

	MODULE_OVER_BUDGET = "module_over_budget"
	"""A module's built artefact exceeds the budget its contract declared (FR-026, FR-097).

	The modules are the *minimum violating set* here in the strictest sense: the bound is
	per module, so the repair scope is exactly the one module that overspent and never the
	plan. That is what makes FR-026's "fails the module and escalates" a scoped escalation
	rather than a halt.
	"""

	UNSATISFIED_BOUNDARY_CONTRACT = "unsatisfied_boundary_contract"
	"""A module reaches for a name its dependency never declared (FR-110, O8).

	This is O8, and it is the one defect neither of its neighbours can see. FR-113 asks
	whether the dependency *edge* was declared, and it is satisfied by a `depends_on` that
	names the right module whatever the consumer then does with it. FR-112 asks whether a
	module built the surface it declared, and it compares a module against *its own*
	declaration. Neither asks the question O8 exists for: does the name the consumer
	reached for appear on the producer's declared surface at all?

	A consumer can therefore import a declared dependency and call a name that module
	never promised — an internal, a private helper, a name that was renamed. Every
	existing check passes: the edge was declared, and the producer matched its own
	declaration exactly. The system does not run, and the failure is invisible to
	per-module verification by construction, which is FR-110's whole premise.

	``modules`` is both ends of the boundary — the consumer that reached and the producer
	that was reached for — because the finding is a disagreement between two declarations
	and either one may be the one to change. A repair scoped to one end alone would be a
	guess about which declaration is wrong.
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
	"FR-083",
	"FR-097",
	"FR-110",
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

FR-083 is here because it is §6.3's model requirement and its second clause is a claim
about *integration*: "hand-written interfaces that disagree with the model are an
integration defect by construction". P2 declares the model and P3 binds it, but only P7
holds both the model and the decomposition, so only P7 can see a module whose declared
surface is not the one the model derives.
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


# --------------------------------------------------------------------------- #
# FR-127 — the intent traceability graph
# --------------------------------------------------------------------------- #


INTENT_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-127",)
"""The requirement this graph discharges, named so a reading can report it."""


class IntentHop(StrEnum):
	"""The three declarations the graph is built from, one per phase that makes one.

	FR-127 asks for a graph rather than a report, and these edges are the whole reason.
	The three relations :class:`TraceLink` prints as a chain are **not** a chain in the
	log: a clause cites its requirement (P2) and its module (P3) *independently*, so the
	two are sibling branches off the clause rather than a requirement-to-module hop, and
	only the module reaches a step (P5). Printing them linearly is what a report has to
	do; holding them as directed edges is what lets an escape be walked backwards, which
	is the mechanism FR-127 says does not otherwise exist.
	"""

	CLAUSE_TO_REQUIREMENT = "clause_to_requirement"
	"""P2's ``Requirement.clause_ids``, read in the direction the requirement stated it."""

	CLAUSE_TO_MODULE = "clause_to_module"
	"""P3's ``Module.clause_ids``: the module that owns the clause."""

	MODULE_TO_STEP = "module_to_step"
	"""P5's ``GoalStep.clause_ids`` resolved through the one module that owns them."""


class IntentNodeKind(StrEnum):
	"""What a vertex stands for. Four kinds, because four phases declare into the graph."""

	CLAUSE = "clause"
	REQUIREMENT = "requirement"
	MODULE = "module"
	STEP = "step"


class IntentNode(View):
	"""One vertex of FR-127's graph, naming the record it stands for.

	``label`` is the record's own words — a clause's statement, a requirement's statement,
	a module's name, a step's ordinal — because the graph exists to be *read* by the
	operator whose intent is being traced, and a graph of UUIDs is one they would have to
	open the log to read. That is also the sense in which FR-127's attribution is the
	learning signal §2.3 calls it: the answer has to arrive in the language of the intent,
	not of the implementation.
	"""

	id: UUID7
	kind: IntentNodeKind
	label: NonEmptyStr
	module_class: ModuleClass | None = None
	"""Set on module vertices only, so a lane resolves to its modules without the
	decomposition. An escape names a *lane*, so "which clauses does this escape point at"
	starts from the class, and a graph that could not answer that from itself would send
	every caller back to the decomposition — which is the derived-report shape FR-127
	refuses."""

	@model_validator(mode="after")
	def _only_a_module_carries_a_class(self) -> Self:
		if self.module_class is not None and self.kind is not IntentNodeKind.MODULE:
			raise ValueError(
				f"a {self.kind.value} vertex carries module class {self.module_class.value}, "
				"but only a module has one. A class on any other vertex would make a lane "
				"resolve to clauses that no module of it owns"
			)
		return self


class IntentEdge(View):
	"""One declaration, as a directed edge from the citing record to the cited one.

	Directed, and the direction is load-bearing rather than conventional: the graph is
	walked backwards to attribute an escape, so an edge that pointed the other way would
	make every attribution a search over the whole graph instead of a hop.
	"""

	source: UUID7
	target: UUID7
	hop: IntentHop


class EscapeAttribution(View):
	"""One escape traced back to one intent clause — which is FR-127's entire purpose.

	"the only mechanism by which an escape (§9.6) can be attributed back to the intent
	clause that was misunderstood". The walk is the graph read backwards: the escape names
	a lane, the lane names its modules, and the modules name the clauses that cite them.

	**What this is, and what it is not.** It is a *pointer for a human*, not a diagnosis.
	Every hop of the walk is a declaration, so the graph can say "the module built for this
	clause is the one that got reverted" and cannot say the clause was ambiguous, that the
	operator meant something else, or that the oracle was too weak to catch it. §2.3 makes
	the operator's reading of the specification the only ground truth there is, and this
	type's job is to put the right clause in front of them — the judgement stays theirs.
	"""

	escape_id: UUID7
	report_id: UUID7
	lane: ModuleClass
	module: NonEmptyStr | None
	"""The module the operator named, when they named one. ``None`` for a lane-wide escape."""

	clause_id: UUID7
	statement: NonEmptyStr
	"""The clause's own words, so the attribution is readable without opening the log."""

	requirement_id: UUID7 | None = None
	step_ordinal: int | None = None

	@property
	def narrowed(self) -> bool:
		"""Whether this is *the* clause rather than one of a candidate set.

		``True`` when the operator named the module: a module's clauses are the specific
		obligations that escaped. ``False`` when the escape was filed against the lane
		alone, which is a real and common case — a revert often cannot say which module —
		and leaves a candidate set instead of an answer. The distinction is on the type
		because a reader who cannot tell the two apart would read a candidate set as a
		finding, which is how an attribution becomes a false accusation.
		"""
		return self.module is not None

	@property
	def rendered(self) -> str:
		"""The attribution as one line, saying *candidate* where that is what it is."""
		qualifier = "" if self.narrowed else " (candidate: the escape named no module)"
		return f"{self.lane.value} escape -> {self.clause_id}: {self.statement}{qualifier}"


class IntentGraph(View):
	"""FR-127's intent traceability graph: the clauses, and every record that cites them.

	"must be a first-class component, not a derived report". The distinction is structural
	rather than rhetorical, and this type is built to make it so: :meth:`project` is how
	FR-117's chain is obtained, so the report is a *projection* of the graph rather than a
	second walk over the same declarations. Two structures derived independently from one
	set of inputs agree until someone changes one of them, and the disagreement is invisible
	precisely because each is internally consistent — which is the failure mode a graph
	that only rendered a picture would not have closed.

	Every edge is a declaration made by a phase, so the graph is as trustworthy as the
	phases that wrote it and no more. What it adds over a rendered chain is the *inverse*
	walk: forward, the chain answers "what was built for this clause"; backward, the
	question is "which clause was misunderstood", and the only route is from the module
	that broke to the clauses that cite it. :meth:`attribute` is that route.
	"""

	id: UUID7
	contract_id: UUID7
	goal_id: UUID7
	built_at: datetime
	nodes: tuple[IntentNode, ...] = ()
	edges: tuple[IntentEdge, ...] = ()
	contract_hash: str | None = None
	"""The contract this graph was built against (FR-131, FR-139).

	Carried so a stored attribution can prove *which* specification it traces — a clause
	reworded after an escape would otherwise be attributed under its new words, and the
	whole value of §2.3's signal is that the operator sees what they actually approved.
	"""

	@property
	def clauses(self) -> tuple[IntentNode, ...]:
		"""The clause vertices, in contract order. The graph's spine."""
		return tuple(node for node in self.nodes if node.kind is IntentNodeKind.CLAUSE)

	@property
	def modules(self) -> tuple[IntentNode, ...]:
		"""The module vertices, in decomposition order."""
		return tuple(node for node in self.nodes if node.kind is IntentNodeKind.MODULE)

	def node(self, node_id: str) -> IntentNode | None:
		"""Look up a vertex by the id of the record it stands for."""
		return next((n for n in self.nodes if n.id == node_id), None)

	def modules_in_lane(self, lane: ModuleClass) -> tuple[IntentNode, ...]:
		"""The modules of one §14 lane, which is where an escape's attribution starts."""
		return tuple(m for m in self.modules if m.module_class is lane)

	def clauses_of_module(self, module_id: str) -> tuple[IntentNode, ...]:
		"""The clauses one module owns, in contract order.

		Ordered by the contract rather than by edge arrival, because an attribution list
		whose order depended on how the decomposition happened to be written would be a
		different list for the same facts.
		"""
		cited = {
			edge.source
			for edge in self.edges
			if edge.hop is IntentHop.CLAUSE_TO_MODULE and edge.target == module_id
		}
		return tuple(node for node in self.clauses if node.id in cited)

	def _hops(self) -> tuple[dict[str, str], dict[str, str], dict[str, int]]:
		"""The three relations as lookups: clause to requirement, clause to module, module to step.

		One reader for both :meth:`project` and :meth:`attribute`, so a chain and an
		attribution can never disagree about which module a clause was built by — the same
		argument that makes :func:`sofact.escape.lanes_of` one function.
		"""
		requirement_of: dict[str, str] = {}
		module_of: dict[str, str] = {}
		step_of: dict[str, int] = {}
		for edge in self.edges:
			if edge.hop is IntentHop.CLAUSE_TO_REQUIREMENT:
				requirement_of.setdefault(edge.source, edge.target)
			elif edge.hop is IntentHop.CLAUSE_TO_MODULE:
				module_of.setdefault(edge.source, edge.target)
			else:
				step = self.node(edge.target)
				# The earliest step that built the module, which is `setdefault` on a graph
				# whose edges were added in plan order. FR-136 forbids one session per
				# module, so several steps can share one; the first is what built it.
				if step is not None:
					step_of.setdefault(edge.source, int(step.label))
		return requirement_of, module_of, step_of

	def project(self) -> tuple[TraceLink, ...]:
		"""FR-117's chain, read off the graph.

		This is what makes the graph first-class rather than a second view over the same
		inputs. A hop the graph does not hold cannot appear in a report, and a hop it does
		hold cannot go missing from one, because there is only one structure.
		"""
		requirement_of, module_of, step_of = self._hops()
		links: list[TraceLink] = []
		for clause in self.clauses:
			module_id = module_of.get(clause.id)
			module = self.node(module_id) if module_id is not None else None
			links.append(
				TraceLink(
					clause_id=clause.id,
					statement=clause.label,
					requirement_id=requirement_of.get(clause.id),
					module=None if module is None else module.label,
					step_ordinal=step_of.get(module_id) if module_id is not None else None,
				)
			)
		return tuple(links)

	@property
	def gaps(self) -> tuple[TraceLink, ...]:
		"""Clauses the graph cannot walk all the way, as the links that stop short.

		The same rule as the report's, deliberately: a gap in the graph and a gap in the
		chain are one fact, and two definitions of "gap" would eventually disagree. A
		clause with no module edge was dropped by the decomposition, so nothing was built
		for it and **no escape can ever be attributed to it** — a worse finding than an
		escape, and exactly what a rendered chain hides by drawing a gap and moving on.
		"""
		return tuple(link for link in self.project() if not link.is_whole)

	def attribute(self, escape: EscapeEvent) -> tuple[EscapeAttribution, ...]:
		"""Trace one escape back to the intent clause(s) it implicates (FR-127).

		The graph walked backwards: lane to modules, module to the clauses that cite it.
		The operator may have named the module, which narrows the answer to that module's
		clauses; without a name the escape points at every clause in the lane, and each
		attribution says which of the two it is rather than presenting a candidate set as
		an answer.

		An escape against a lane the graph holds no module for attributes to **nothing**,
		and that empty tuple is the honest result rather than a gap to paper over: it means
		the change's decomposition is not the one this graph was built from, which
		:meth:`~sofact.service.FactoryService.record_escape` refuses at recording time and
		which a foreign log can still contain.
		"""
		assert escape.lane is not None, "an escape names a lane"
		modules = self.modules_in_lane(escape.lane)
		if escape.module is not None:
			modules = tuple(m for m in modules if m.label == escape.module)
		requirement_of, _, step_of = self._hops()
		attributions: list[EscapeAttribution] = []
		seen: set[str] = set()
		for module in modules:
			for clause in self.clauses_of_module(module.id):
				if clause.id in seen:
					# One attribution per escape and clause. A decomposition whose modules
					# overlap on a clause would otherwise report the same clause twice for
					# one escape, which reads as two signals.
					continue
				seen.add(clause.id)
				attributions.append(
					EscapeAttribution(
						escape_id=escape.id,
						report_id=escape.report_id,
						lane=escape.lane,
						module=escape.module,
						clause_id=clause.id,
						statement=clause.label,
						requirement_id=requirement_of.get(clause.id),
						step_ordinal=step_of.get(module.id),
					)
				)
		return tuple(attributions)

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this graph carried out, which may be none.

		The vacuous-pass rule the rest of the product keeps: a graph over zero clauses has
		traced nothing, and reporting FR-127 as discharged over an empty contract would be
		a clearance derived from the absence of a specification.
		"""
		if not self.clauses:
			return ()
		return INTENT_REQUIREMENTS

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-127 this graph did not carry out."""
		carried = set(self.discharged)
		return tuple(name for name in INTENT_REQUIREMENTS if name not in carried)


class VerifiedClause(View):
	"""A clause that is verified, and by which oracle at which measured strength (FR-118).

	FR-118's first bullet asks for the oracle **and its measured strength**, and the two
	are different kinds of statement: ``rank`` is what the operator declared, and
	``measured_strength`` is what a suite was *observed* to notice. A report that printed
	the declared rank under the word "measured" would be the exact euphemism FR-118
	forbids, so :attr:`measured` says which of the two the number above it is.

	``measured_strength`` is ``None`` by default and stays ``None`` unless a caller hands
	a measurement in. That is not a gap being papered over: FR-105's instrument
	(:mod:`sofact.mutation`) is a kill rate over a closed operator set, it is a **lower
	bound**, and it is *withheld* below a mutant floor — so "no number" is the honest
	state of most clauses and the rendering says so in words.
	"""

	clause_id: UUID7
	statement: NonEmptyStr
	oracle_class: OracleClass
	rank: int
	"""The declared rank, 1 (strongest) to 7. Read from the clause's own oracle."""

	measured_strength: float | None = None
	"""A kill rate measured over a named operator set (FR-105, FR-118).

	``None`` means *no measurement was taken or none survived the floor*, which is not
	zero and must not render as one — :mod:`sofact.mutation` states the refusal by name
	and this type reports the absence rather than a number nobody should act on.
	"""

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
	"""The lane's §13 autonomy, capped at :data:`MODE_M_CEILING` (FR-158).

	§13 gives each lane a level, and FR-158(a) lowers every one of them to L1 for as long
	as no oracle observes change cost. The cap is applied by the type rather than by the
	caller, because a lane that carried §13's L4 into a handover would be a maintenance
	claim at L4 — the exact claim FR-158 refuses — and a caller who had to remember to
	clamp it is a caller who can forget.
	"""

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
		if self.ceiling > MODE_M_CEILING:
			raise ValueError(
				f"lane {self.lane!r} declares {self.ceiling.name}, above the "
				f"{MODE_M_CEILING.name} a maintenance claim may carry: no oracle in O1-O8 "
				"observes change cost, so the higher level would be a claim about "
				"maintainability nothing measured (FR-158, NFR-024)"
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

	FR-158(c) adds a sixth statement of the same kind: the report must say that
	maintainability was not verified. It is :attr:`MAINTAINABILITY_NOT_VERIFIED`, a
	constant on the type for FR-086's reason — the failure FR-158 corrects is not a report
	that omits the sentence, it is one that says something adjacent and flattering about a
	green suite.
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

	diff_reviews: tuple[DiffReview, ...] = ()
	"""§20.3 item 3's per-diff half: what each reviewed diff cost, one row per dispatch.

	FR-160's per-gate measurement is :attr:`gate_costs`; this is the number §20.3 puts
	beside it so §1.4's claim — attention is spent per platform rather than per module —
	can be read against the v0.1 alternative, which reviewed every diff at roughly four
	units an hour. Empty means *unmeasured*, not *free to review*.

	One row per dispatch rather than every recorded sitting, because a diff reviewed
	twice is one diff: :attr:`diff_rework_fraction` and the coverage pair would both be
	wrong if the denominator counted sittings.
	"""

	sealed_dispatches: int = 0
	"""How many dispatches sealed a commit, so the review mean has a denominator.

	Carried beside :attr:`diff_reviews` rather than derived here, because the count
	comes from the dispatch log and a report that carried only the reviewed rows would
	be unable to say what fraction of the project's diffs anyone read — which is the
	number that keeps the per-diff mean from flattering §1.4's claim.
	"""

	@property
	def reviewed_minutes(self) -> float | None:
		"""What the reviewed diffs cost in total, or ``None`` when none was reviewed.

		``None`` rather than ``0.0`` for :attr:`rework_fraction`'s reason: zero would be
		the claim that the project's diffs were free to read, which is a different and
		flattering statement (§20.3 item 3, NFR-024).

		This is the per-diff half of what :attr:`sofact.views.ProjectState.total_human_minutes`
		is for gates, and the two are **not** summed: a gate's minutes are spent per
		platform and a diff's per module, so one total over both would average §1.4's two
		populations and answer neither question. Both are printed and read separately.
		"""
		if not self.diff_reviews:
			return None
		return sum(r.human_minutes for r in self.diff_reviews)

	@property
	def mean_diff_minutes(self) -> float | None:
		"""The mean human-minutes one reviewed diff took, or ``None`` when none was.

		The number §20.3 item 3 exists to produce: §1.4's claim is read by putting this
		beside v0.1's roughly four units an hour, about fifteen minutes a diff.

		The denominator is the *reviewed* diffs, not the project's diffs, so this figure
		on its own flatters §1.4's claim in exactly the direction the claim wants —
		which is why :attr:`review_coverage` is never printed without it.
		"""
		if not self.diff_reviews:
			return None
		return sum(r.human_minutes for r in self.diff_reviews) / len(self.diff_reviews)

	@property
	def diff_rework_fraction(self) -> float | None:
		"""The mean share of each reviewed diff returned to the producer (§20.3 item 3).

		``None`` when no diff was reviewed, for the reason :attr:`rework_fraction` gives.
		Deliberately separate from :attr:`rework_fraction` rather than pooled with it: a
		gate's fraction is of a *slice* and a diff's is of a *diff*, so the denominators
		differ and one mean over both would average two quantities.
		"""
		if not self.diff_reviews:
			return None
		return sum(r.rework_fraction for r in self.diff_reviews) / len(self.diff_reviews)

	@property
	def review_coverage(self) -> tuple[int, int] | None:
		"""Reviewed diffs against sealed diffs, or ``None`` when none sealed (§20.3 item 3).

		The pair travels with the mean because §1.4's claim wants per-module attention to
		look small, and a mean over the diffs somebody chose to review reports exactly
		that while the rest were read by nobody.
		"""
		if not self.sealed_dispatches:
			return None
		return (len(self.diff_reviews), self.sealed_dispatches)

	def _diff_review_detail(self) -> str:
		"""The per-diff reading for this report (:func:`diff_review_detail`).

		A method rather than a property because the module-level function is the one
		implementation and three surfaces call it; this is the report's door to it.
		"""
		return diff_review_detail(
			self.diff_reviews,
			self.sealed_dispatches,
			sum(c.human_minutes for c in self.gate_costs) if self.gate_costs else None,
		)

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
	reports the lowered value rather than the one its hardware cannot support. When
	:attr:`boundary` records a *measured* boundary that held, the modifier is §5.4's
	baseline rather than the degraded topology's penalty, because the isolation the number
	was priced against was measured rather than declared.
	"""

	boundary: DeploymentBoundary | None = None
	"""The isolation a probe measured for this delivery, or ``None`` if none was measured
	(FR-019, FR-030).

	FR-030 requires the topology, its isolation and its modifier reported together, and
	this is the half of that triple which is *measured* rather than documented. R2's
	failure was autonomy depending on isolation "asserted but never verified": a report
	carrying :attr:`topology` alone states what the deployment declared, and a reader has
	no way to tell a deployment that confines its children from one that merely says so.

	``None`` means no probe was run, which is not the same as a probe that found nothing —
	that is a boundary whose :attr:`DeploymentBoundary.degraded` is true.
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

	escapes: EscapeReport | None = None
	"""FR-022's escape measurement, or ``None`` when none was taken (FR-021-023).

	A field rather than a property, for :attr:`topology`'s reason: the report must stay
	readable from the log alone, and the rate a delivery was approved under is part of what
	the report *says* rather than something a later reader reconstructs from escapes
	recorded afterwards. ``None`` means the deployment configured no escape budget — a
	different statement from a measurement that found nothing, and the report prints which.

	The value is a reading of the log *at the moment of rendering*, so an escape recorded
	after this report is not in it and the reduction appears in the next render. That is not
	a gap in FR-022's rate, which is a fold over the whole ledger, but it is a fact a reader
	of a stored report needs — and FR-117 versions reports precisely so an approver's copy
	stays as it was.
	"""

	change_cost: ChangeCostReport | None = None
	"""FR-159's change-cost measurement, or ``None`` when none was taken (D18).

	Beside :attr:`escapes` and for the same reason: a report must stay readable from the
	log alone, so a trend a delivery was rendered under is part of what the report *says*
	rather than something a later reader reconstructs from a repository that has since
	moved.

	``None`` means no measurement was taken — no pinned units, or no repository — which is
	a different statement from a measurement that found no trend, and
	:attr:`ChangeCostReport.discharged` is what distinguishes them. This field **does not
	change the ceiling and does not change the debt**: FR-159 is admissible as a trend
	alarm and a Mode M ceiling *input*, and the input is read by a human deciding D18's
	question, not by this report.
	"""

	intent: IntentGraph | None = None
	"""FR-127's traceability graph this report's :attr:`chain` was projected from.

	Carried rather than recomputed, and that is the whole of FR-127's "first-class
	component, not a derived report": the report holds the graph, so an escape can be
	attributed against the *same* structure the chain came from. A reader who rebuilt the
	graph from the log would be attributing against whatever the decomposition says now,
	which after a repair is a different graph than the one that was deployed — and the
	escape would be pointed at a clause the change was never built against.

	``None`` for a report rendered without one, which only a hand-built fixture does; the
	renderer always supplies it.
	"""

	attributions: tuple[EscapeAttribution, ...] = ()
	"""Every escape attributed back to an intent clause, as of this render (FR-127).

	Beside :attr:`escapes` rather than inside it, because the two answer different
	questions from one log: the rate says *how much* escaped and this says *what was
	understood wrongly*. §2.3 calls the second the most valuable signal the product
	produces, and a reader who had to derive it would be reading a number without the
	thing that makes it actionable.
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

	exceeds: tuple[ExceedsClaim, ...] = ()
	"""FR-170's declarations, carried so the report can say what was *claimed* (FR-118).

	A field rather than a property, for :attr:`escapes`' reason: a report must stay
	readable from the log alone. Empty means *none was declared*, which is a different
	statement from every declaration being met — no oracle in O1-O8 compares two systems,
	so nothing here is ever met or unmet, and the check that reads this field says
	"declared, 0 verified by oracle" rather than printing an empty table that reads as a
	comparison nobody made.
	"""

	notifications: tuple[Notification, ...] = ()
	"""FR-172's attempts to tell the operator, carried so the report says whether it did.

	Empty means *no attempt was made*. The body is not here — it is digested on
	:class:`Notification` — because a notification names the system being built and this
	report is a durable artefact a client may hold.
	"""

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
	def maintainability_statement(self) -> str:
		"""FR-158(c)'s statement, on every report until a change-cost oracle exists.

		Not conditional on anything in the report, and that is the point: FR-158 makes the
		debt 1.0 *by construction*, so there is no delivery this factory can render for
		which the sentence would be different. A conditional here would be the code path
		that claims maintainability, which is the path FR-158 exists to close.
		"""
		return MAINTAINABILITY_NOT_VERIFIED

	@property
	def evolvability_debt(self) -> float:
		"""FR-158's debt term, as a number the report carries (FR-158).

		Beside ground-truth debt and not inside it. FR-108's debt is measured — the
		unverified clauses this report lists, each saying in :attr:`UnverifiedClause.because`
		whether it is ground-truth debt — and FR-158's is not measured at all. A report
		that carried one debt number would be read as carrying the measurable one, and the
		unmeasurable half is the half that decides what the delivery may claim (NFR-024).
		"""
		return EVOLVABILITY_DEBT

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
	model: NonEmptyStr | None = None
	"""The model this session ran on (FR-132), or ``None`` when none was resolved.

	Recorded rather than left in ``argv``. The harness's own command line carries a
	``--model`` for some harnesses and not others, and for those it carries it the flag
	is one token among twenty — a reader wanting to know which model produced a module
	would be parsing a producer's command line, which is the inference FR-132's
	declarative table exists to remove. ``None`` means no model was resolved for this
	dispatch, which is what a refusal records; it is not the same as the default model.
	"""
	model_source: NonEmptyStr | None = None
	"""Which rule chose :attr:`model` — ``--model``, ``tier:<name>``, ``SOFACT_MODEL``
	or ``default`` (FR-132).

	The *source* is the half that makes a tier table checkable. A row saying
	``model="qwen3-coder"`` answers "what ran"; ``model_source="tier:cheap"`` answers
	"and it ran because the table said so", which is the question a deployment asks
	when the bill arrives or the depth of a diagnosis is doubted. Without it a factory
	with a tier table and a factory without one produce identical records whenever the
	models happen to coincide, and the table's effect would be unobservable.
	"""
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

	composition_hash: str | None = None
	"""The digest of the plugin composition this session ran under (FR-154, FR-149, R29).

	FR-154's last sentence is "the observed composition hash is recorded with the session",
	and this is where. It is a *hash* rather than the composition itself for the same reason
	the ledger chains hashes: the row has to stay small and the freeze has to be checkable,
	and :meth:`PluginComposition.pinned_content` is reproducible from the log, so a reader
	can recompute it and compare rather than trusting a copy.

	``None`` means no composition was recorded, which is not the same as an empty one. A
	session whose record predates FR-154, or one that was refused before a composition could
	be established, carries the null — and FR-154's requirement that a build *report* its
	composition is discharged by the composition the dispatch recorded, not by this field
	being non-null on every row.
	"""

	boundary: DeploymentBoundary | None = None
	"""The isolation actually in force for this dispatch, as measured (FR-019).

	FR-019 makes isolation the thing autonomy is priced against, so "which boundary was in
	force" is a fact about the *dispatch* rather than about the deployment in general: a
	host can offer a mechanism that holds for one workspace and not another, and a
	deployment's declared topology says where it is meant to run rather than what confined
	this child. Recording it here is what lets a reader check the ceiling against the
	isolation it was priced at, instead of taking both on trust — R2's failure.

	``None`` means no boundary was measured for this dispatch, which is distinct from a
	measurement that found none: the first is an absent instrument and the second is a
	degraded configuration. ``DeploymentBoundary.degraded`` states the second explicitly.
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


# --------------------------------------------------------------------------- #
# FR-154/155/156 — the composition, and the deletion test that admits into it
# --------------------------------------------------------------------------- #

COMPOSITION_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-154", "FR-155", "FR-156")
"""What one composition freeze carries out.

FR-154 freezes and hashes the composition, FR-155 admits a plugin into it only by the
deletion test, and FR-156 prefers configuration to code. They are one mechanism: a test
with no frozen composition to admit into is a rule nothing consults, and a freeze with no
admission test pins whatever was installed.
"""

VERDICT_SURFACES: Final[tuple[str, ...]] = (
	"completion",
	"contract_integrity",
	"oracle_strength",
	"budget",
	"egress",
)
"""FR-155's own list, verbatim: "completion, contract integrity, oracle strength, budget,
egress".

The five are the requirement's, not a taxonomy invented here. The deletion test asks
whether *every* one comes out the same without the plugin, so the list has to be closed —
"does SoFact still decide the same way?" over an open set is not a question a machine can
answer, and an admission whose check could be satisfied by naming four of five surfaces
would be the subset failure this project keeps finding in its own gates.
"""


class PluginVerdict(StrEnum):
	"""What FR-155's deletion test concludes about one plugin."""

	ADMISSIBLE = "admissible"
	"""Below the trust boundary: every verdict surface is SoFact's with or without it."""

	REFUSED = "refused"
	"""It took over a decision SoFact exists to make. Refused regardless of quality."""

	SUPERSEDED = "superseded"
	"""FR-156's case: configuration obtains the capability, so the plugin is not installed.

	A separate verdict from REFUSED because the remedy differs — the plugin was not
	harmful, it was unnecessary, and FR-156's rule is that the cheapest safe composition is
	the one with the fewest moving parts.
	"""

	BUILT_HERE = "built_here"
	"""The capability is SoFact's own, so the plugin is unnecessary rather than harmful.

	§8.7's ``dsh-git-worktree`` row is this verdict: it *passes* the deletion test and is
	still refused, because FR-141 stopped being deferred and the wrapper would have had to
	supply the integration line, the per-wave merge order and the conflict record — the
	parts that make the feature safe. Distinct from :attr:`SUPERSEDED`, which is FR-156's
	*configuration* remedy: folding the two would record a plugin as replaced by a setting
	when what replaced it was code, and the next reader would go looking for the setting.
	"""


class PluginAdmission(View):
	"""FR-155's deletion test, applied to one plugin and recorded as its outcome.

	> Remove the plugin. Does every SoFact verdict — completion, contract integrity,
	> oracle strength, budget, egress — come out the same?

	``surfaces_held`` is what makes the answer checkable rather than asserted: the verdict
	surfaces SoFact still decides **without** the plugin. A plugin is admissible exactly when
	that set covers :data:`VERDICT_SURFACES`, and the type refuses the two ways to write a
	row that does not mean what it says — an ``ADMISSIBLE`` verdict with a surface missing
	(which would admit a plugin that took over a decision), and a ``REFUSED`` verdict with
	every surface held (which would refuse one that took over nothing).

	``superseded_by`` is FR-156's remedy and is required for a ``SUPERSEDED`` verdict: the
	configuration that obtains the capability instead. Naming it is what distinguishes
	"this plugin is unnecessary" from "this plugin was not looked at".

	``licence`` is the one check that is neither a verdict nor a measurement: FR-154's
	composition is pinned by digest, and a digest says what was installed and nothing about
	whether it may be. It is required on an admitted plugin for the reason the requirement
	gives — R28's third failure mode is licence-incompatible, and a licence nobody wrote down
	is a licence nobody checked.
	"""

	plugin: NonEmptyStr
	verdict: PluginVerdict
	surfaces_held: frozenset[str] = frozenset()
	"""Verdict surfaces SoFact decides without the plugin, from :data:`VERDICT_SURFACES`.

	A ``frozenset`` because the test is set membership and never an ordering — a tuple
	would invite a reader to compare two admissions positionally, and two rows listing the
	same surfaces in different orders are the same finding.
	"""

	superseded_by: NonEmptyStr | None = None
	licence: NonEmptyStr | None = None
	"""The licence the plugin ships under, recorded at composition time (FR-154, R28).

	Required exactly when the verdict is :attr:`PluginVerdict.ADMISSIBLE`. That is the only
	verdict under which the plugin is installed, and it is the only one where the answer
	has consequences — a refused plugin's licence is a fact about something that is not in
	the build.
	"""

	rationale: NonEmptyStr

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		unknown = sorted(self.surfaces_held - set(VERDICT_SURFACES))
		if unknown:
			raise ValueError(
				f"unknown verdict surface(s) {unknown}; FR-155 names exactly "
				f"{list(VERDICT_SURFACES)}, and a surface outside that list would make the "
				"deletion test answer a question the requirement does not ask"
			)
		held = self.surfaces_held >= set(VERDICT_SURFACES)
		if self.verdict is PluginVerdict.ADMISSIBLE and not held:
			missing = sorted(s for s in VERDICT_SURFACES if s not in self.surfaces_held)
			raise ValueError(
				f"{self.plugin!r} is admissible but SoFact does not reach the same verdict "
				f"on {missing} without it; a plugin that holds a decision is refused "
				"regardless of quality (FR-155)"
			)
		if self.verdict is PluginVerdict.REFUSED and held:
			raise ValueError(
				f"{self.plugin!r} is refused but every verdict surface is held without it; "
				"a plugin below the trust boundary is admissible, and refusing one that "
				"took over nothing is a refusal with no defect behind it"
			)
		if self.verdict is PluginVerdict.SUPERSEDED and self.superseded_by is None:
			raise ValueError(
				f"{self.plugin!r} is superseded by configuration (FR-156) but names none; "
				"without the setting this is indistinguishable from a plugin nobody looked at"
			)
		if self.verdict is PluginVerdict.ADMISSIBLE and self.licence is None:
			raise ValueError(
				f"{self.plugin!r} is admitted with no licence recorded; R28's third failure "
				"mode is licence-incompatible, and FR-154 checks it at composition time "
				"because a licence discovered after installation is a licence discovered "
				"too late"
			)
		if self.verdict is not PluginVerdict.ADMISSIBLE and self.licence is not None:
			raise ValueError(
				f"{self.plugin!r} is {self.verdict.value} but carries a licence; a plugin "
				"that is not installed has no licence to record, and the field would read "
				"as an admission with an odd verdict"
			)
		return self


class PluginComposition(View):
	"""FR-154's frozen composition, and FR-155's admission test applied to every member.

	FR-154: the composition "must be **frozen, minimal, pinned, and hash-verified** for the
	duration of a build, and must never be the operator's own profile". The hazard is
	specific — a `dsh` composition is mutable *at runtime* by the agent (§8.7), so a
	producer able to influence its own composition can influence its own verifier.

	``pins`` is the hash-verified half: plugin name to the digest of what was installed. A
	composition that named plugins without pinning them would freeze a *list* while leaving
	what the list resolves to free to change, which is the drift FR-154's word "pinned" is
	for. The hash is computed over :meth:`pinned_content`, so the freeze covers the
	admissions too: an admission cannot be revised without the composition hash moving, and
	a build pinned to a hash is therefore pinned to the reasoning that admitted its members.

	``operator_profile`` records whether the composition inherited the operator's own
	profile. FR-154 says it must never be, and the type refuses it rather than reporting it,
	because the failure is that a producer reaches the verifier through the operator's
	installed set — a fact worth refusing at construction rather than counting.

	``argv_frozen`` records the *other* way a composition is frozen, and the two are not
	alternatives to be chosen between: the argv that ran the harness can refuse to auto-load
	whatever the operator has installed (``pi``'s ``--no-extensions``), or the plugins can be
	enumerated and pinned. A composition with neither is not frozen, and saying so is the
	point — §8.7 records that a ``dsh`` composition is mutable *at runtime by the agent*, so
	a ``dsh`` build reports FR-154 as not carried out rather than reporting a clean freeze
	it does not have.
	"""

	id: UUID7
	harness: NonEmptyStr
	created_at: datetime
	pins: tuple[tuple[str, str], ...] = ()
	"""``(plugin, digest)`` pairs. A composition with no plugins is the minimal one."""

	admissions: tuple[PluginAdmission, ...] = ()
	"""FR-155's test, one row per plugin that was considered — including the refused ones.

	Considered, not admitted: a refusal is the more valuable row, because it is the one
	that records *why* a capability the ecosystem offers is not in the build. A composition
	that listed only its members would make its refusals invisible and they would be
	re-litigated at the next plugin.
	"""

	operator_profile: bool = False
	"""Whether this composition inherited the operator's own profile. FR-154 forbids it."""

	argv_frozen: bool = False
	"""Whether the argv that ran this harness refuses to auto-load installed plugins.

	Derived from :attr:`~sofact.harness.HarnessSpec.freezing_argv` by
	:func:`sofact.composition.composition_for` rather than typed in by a caller, so the
	record states what the command line does and not what someone believed it did.
	"""

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if self.operator_profile:
			raise ValueError(
				"a P5 composition must never be the operator's own profile (FR-154): a "
				"producer that inherits it reaches whatever the operator happens to have "
				"installed, which is a route to its own verifier"
			)
		pinned = [name for name, _ in self.pins]
		if len(pinned) != len(set(pinned)):
			raise ValueError(f"a plugin is pinned twice in {self.harness!r}; one pin per name")
		admitted = {a.plugin for a in self.admissions if a.verdict is PluginVerdict.ADMISSIBLE}
		unpinned = sorted(admitted - set(pinned))
		if unpinned:
			raise ValueError(
				f"admitted plugin(s) {unpinned} carry no pin; FR-154 requires the "
				"composition be pinned as well as admitted, or a name freezes while what "
				"it resolves to does not"
			)
		refused = sorted(a.plugin for a in self.admissions if a.verdict is PluginVerdict.REFUSED)
		installed = sorted(set(pinned) & set(refused))
		if installed:
			raise ValueError(
				f"refused plugin(s) {installed} are installed anyway; FR-155 refuses a "
				"plugin that holds a decision, and installing it while recording the "
				"refusal would put it in the build the test excluded"
			)
		return self

	@property
	def frozen(self) -> bool:
		"""Whether anything actually freezes this composition (FR-154).

		Two ways, and either is enough: the argv refuses to auto-load installed plugins, or
		the plugins are enumerated and pinned. A composition with neither is not frozen —
		the harness loads whatever the operator has installed, which is the state FR-154
		exists to make impossible — and this is the property that says so rather than
		letting a composition report a freeze it does not have.
		"""
		return self.argv_frozen or bool(self.pins)

	@property
	def pinned_content(self) -> str:
		"""SHA-256 over the pins and the admissions — what FR-154's freeze covers.

		The admissions are in the hash deliberately. A composition is frozen so that a build
		can be shown to have run the composition it was approved with, and the *reasoning*
		that admitted each member is part of that: a plugin admitted under one reading of
		FR-155 and later re-classified changes what the build's trust boundary was, and a
		hash over the pins alone would not move.

		``argv_frozen`` is in it for the same reason and a sharper one: it is the half of the
		freeze that is not a list. Two builds can pin the same plugins and differ in whether
		the harness was *also* told not to auto-load, and a hash that ignored the flag would
		call those two compositions the same.
		"""
		return content_hash(
			{
				"harness": self.harness,
				"argv_frozen": self.argv_frozen,
				"pins": sorted(self.pins),
				"admissions": [
					{
						"plugin": a.plugin,
						"verdict": a.verdict.value,
						"surfaces_held": sorted(a.surfaces_held),
						"superseded_by": a.superseded_by,
						"licence": a.licence,
					}
					for a in self.admissions
				],
			}
		)

	@property
	def admitted(self) -> tuple[str, ...]:
		"""The plugins that entered the build, in pin order."""
		passing = {a.plugin for a in self.admissions if a.verdict is PluginVerdict.ADMISSIBLE}
		return tuple(name for name, _ in self.pins if name in passing)

	@property
	def refused(self) -> tuple[PluginAdmission, ...]:
		"""The plugins FR-155 kept out, with the surfaces that kept them out."""
		return tuple(a for a in self.admissions if a.verdict is PluginVerdict.REFUSED)

	@property
	def superseded(self) -> tuple[PluginAdmission, ...]:
		"""The plugins FR-156 replaced with configuration."""
		return tuple(a for a in self.admissions if a.verdict is PluginVerdict.SUPERSEDED)

	@property
	def minimal(self) -> bool:
		"""Whether every member was admitted by the deletion test, and none refused is installed.

		FR-154's word is "minimal", and this is what it can honestly mean to a machine: not
		"as few plugins as possible" — no number exists for that — but "no plugin is in the
		build that FR-155 would keep out". A composition can therefore be minimal and
		non-empty, which is the case the adjective is for.
		"""
		return not ({name for name, _ in self.pins} & {a.plugin for a in self.refused})

	@property
	def built_here(self) -> tuple[PluginAdmission, ...]:
		"""The plugins FR-154 replaced with SoFact's own code rather than with a setting."""
		return tuple(a for a in self.admissions if a.verdict is PluginVerdict.BUILT_HERE)

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this composition carries out, which may be none.

		The vacuous-pass rule the other reports keep, applied twice over. A composition that
		considered no plugin has not applied the deletion test to anything, so it leaves
		FR-155 open rather than reporting a clean filter that filtered nothing. A
		composition that is not :attr:`frozen` leaves FR-154 open even when it has
		admissions: an unfrozen harness loads whatever the operator installed, and the
		admission rows describe a list the argv does not enforce. FR-156 is the one that
		still applies either way — an empty, unfrozen composition *is* the configuration-only
		answer — so it is the floor this can return and never the whole set by default.
		"""
		discharged: list[str] = ["FR-156"]
		if self.frozen:
			discharged.append("FR-154")
		if self.admissions:
			discharged.append("FR-155")
		return tuple(name for name in COMPOSITION_REQUIREMENTS if name in discharged)

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-154-156 this composition did not carry out."""
		discharged = set(self.discharged)
		return tuple(name for name in COMPOSITION_REQUIREMENTS if name not in discharged)


class AttemptTelemetry(View):
	"""FR-102's attempt telemetry: what one repair attempt cost, and what it achieved.

	"Build must report **attempt telemetry** (attempts, tokens, wall clock)." The three
	quantities are per *attempt*, and an attempt is a :class:`RepairAttempt` row joined to
	the :class:`DispatchRecord` its session produced. Before this type the two rows existed
	and nothing joined them, so the three numbers FR-102 names could only be read one
	dispatch at a time.

	**``tokens`` is a floor, and says so.** A harness that reports no usage yields
	``tokens_observed=None``, which is *unmeasured* rather than zero (NFR-024). Summing
	``None`` as zero would report a cheap attempt where the truth is an unmeasured one, so
	:attr:`tokens` sums only the attempts that reported and :attr:`unmeasured_tokens` counts
	the rest. A total that hid its own coverage would be the defect FR-118 names — a
	qualification that went missing where it was least visible.
	"""

	attempt_id: UUID7
	clause_ids: tuple[UUID7, ...]
	attempt: int
	"""1-based, counting attempts at *this* clause, as :class:`RepairAttempt` numbers it."""

	outcome: RepairOutcome
	dispatch_id: UUID7 | None = None
	"""``None`` when no session ran, so the attempt cost no wall clock and no tokens.

	A refusal and a cheap attempt are different facts. ``NOT_COMPLETED`` with no dispatch
	is the producer never starting; a dispatch that exited in a second is a producer that
	started and stopped. Both have near-zero cost and only one of them is a measurement.
	"""

	wall_clock_seconds: float = 0.0
	"""Observed session duration. ``0.0`` when no session ran — a fact, not a floor."""

	tokens: int = 0
	"""Sum of the token counts the sessions *did* report. A floor, not a total."""

	unmeasured_tokens: int = 0
	"""How many joined dispatches reported no usage. ``0`` means the sum is complete."""

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if self.attempt < 1:
			raise ValueError(f"attempt must be 1-based, got {self.attempt}")
		if self.wall_clock_seconds < 0:
			raise ValueError(f"wall clock cannot be negative, got {self.wall_clock_seconds}")
		if self.tokens < 0:
			raise ValueError(f"tokens cannot be negative, got {self.tokens}")
		if self.unmeasured_tokens < 0:
			raise ValueError("unmeasured_tokens cannot be negative")
		if self.dispatch_id is None and (self.wall_clock_seconds or self.tokens):
			raise ValueError(
				"an attempt with no dispatch reports no spend: a cost with no session "
				"attached is a measurement of nothing"
			)
		return self

	@property
	def tokens_measured(self) -> bool:
		"""True when every joined dispatch reported usage, so :attr:`tokens` is exact."""
		return self.unmeasured_tokens == 0


class AttemptTelemetryReport(View):
	"""FR-102's aggregation: the attempt telemetry of one repair run, totalled.

	The requirement asks build to *report* attempts, tokens and wall clock. The rows
	carried the first and the dispatches carried the other two; this is the fold that
	produces the three numbers in one place, per run and per clause.

	**The vacuous pass is refused.** A run that made no attempt returns
	``discharged == ()`` — the rule :attr:`OracleAuditReport.discharged` and
	:attr:`EscapeReport.discharged` both state. "0 tokens over 0 attempts" is not a
	measurement of a cheap build; it is the absence of a measurement, and a screen showing
	it as a total would report a clean bill of health for work nobody did.

	**What it is not.** It reports *cost*, never *value*. An attempt that burned the most
	wall clock is not the attempt that fixed the clause — that is :attr:`outcome`'s job,
	and the two are deliberately separate columns so a reader cannot read spend as progress.
	"""

	id: UUID7
	plan_id: UUID7
	rendered_at: datetime
	attempts: tuple[AttemptTelemetry, ...] = ()
	"""One entry per repair attempt, in log order."""

	@property
	def total_attempts(self) -> int:
		"""How many attempts the run made. FR-102's first quantity."""
		return len(self.attempts)

	@property
	def total_wall_clock_seconds(self) -> float:
		"""Summed session duration. FR-102's third quantity."""
		return sum(a.wall_clock_seconds for a in self.attempts)

	@property
	def total_tokens(self) -> int:
		"""Summed tokens over the attempts that reported usage. A floor, not a total."""
		return sum(a.tokens for a in self.attempts)

	@property
	def unmeasured_tokens(self) -> int:
		"""Joined dispatches that reported no usage, across every attempt."""
		return sum(a.unmeasured_tokens for a in self.attempts)

	@property
	def tokens_complete(self) -> bool:
		"""True when every joined dispatch reported usage, so the token total is exact."""
		return self.unmeasured_tokens == 0

	@property
	def by_clause(self) -> tuple[tuple[UUID7, int], ...]:
		"""Attempt counts per clause, so a stubborn clause is visible as a cost centre.

		Counted at the clause because that is the unit FR-101 bounds the loop in, and
		because a plan with one stubborn clause would otherwise hide its spend inside a
		run-wide total. An attempt covering several clauses counts once for each, which is
		why the counts can sum past :attr:`total_attempts` — the alternative is a
		per-clause figure that depends on what else the attempt happened to cover.
		"""
		counts: dict[UUID7, int] = {}
		for attempt in self.attempts:
			for clause_id in attempt.clause_ids:
				counts[clause_id] = counts.get(clause_id, 0) + 1
		return tuple(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this reading carried out, which may be none.

		A run that made no attempt claims nothing, for the reason
		:attr:`EscapeReport.discharged` gives: the absence of a measurement is not a
		measurement, and FR-102's numbers over an empty run are the shape a clean result
		takes when there was no run at all.
		"""
		if not self.attempts:
			return ()
		return ATTEMPT_TELEMETRY_REQUIREMENTS


class SpendAttribution(View):
	"""One bucket of dispatch spend: a phase, or a module (FR-133, NFR-030).

	FR-133 asks for spend "attributed per phase and per module", and NFR-030 says why:
	"so that cost per delivered module is knowable". The two keys are the same numbers
	bucketed twice, which is why this is one type used in two tuples rather than two
	types — a second type would be a second set of totals to keep in step with the first.

	**``tokens`` is a floor and ``unmeasured_tokens`` is its coverage.** Same rule as
	:class:`AttemptTelemetry` (NFR-024): a harness that reported no usage is *unmeasured*,
	never zero, so a bucket sums what reported and counts what did not. A phase whose
	every dispatch was unmeasured reports ``tokens=0, unmeasured_tokens=N`` and
	:attr:`tokens_measured` is ``False`` — which is a different statement from a phase
	that spent nothing, and the only one of the two that is a measurement.

	``models`` is the set of models this bucket ran on, sorted. FR-132's tier table is
	what makes it a *set* rather than a name: a phase whose steps ran on two models is a
	phase the table was changed under, and a single-model field would report whichever
	dispatch was read last.
	"""

	key: NonEmptyStr
	"""The phase's value, or the module's name. Never empty — see :attr:`SpendReport`."""

	dispatches: int = 0
	wall_clock_seconds: float = 0.0
	tokens: int = 0
	unmeasured_tokens: int = 0
	models: tuple[NonEmptyStr, ...] = ()

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		if self.dispatches < 0:
			raise ValueError(f"dispatches cannot be negative, got {self.dispatches}")
		if self.wall_clock_seconds < 0:
			raise ValueError(f"wall clock cannot be negative, got {self.wall_clock_seconds}")
		if self.tokens < 0 or self.unmeasured_tokens < 0:
			raise ValueError("token counts cannot be negative")
		if self.unmeasured_tokens > self.dispatches:
			raise ValueError(
				f"{self.unmeasured_tokens} unmeasured token counts over {self.dispatches} "
				"dispatch(es): more unmeasured dispatches than dispatches means the "
				"coverage count is not a count of this bucket's rows (NFR-024)"
			)
		if self.dispatches == 0 and (self.tokens or self.wall_clock_seconds or self.models):
			raise ValueError(
				f"bucket {self.key!r} has no dispatches but reports spend; a cost with no "
				"session attached is a measurement of nothing"
			)
		return self

	@property
	def tokens_measured(self) -> bool:
		"""True when every dispatch in this bucket reported usage, so ``tokens`` is exact."""
		return self.unmeasured_tokens == 0

	@property
	def tokens_per_dispatch(self) -> float | None:
		"""Mean tokens per dispatch, or ``None`` when the bucket is not fully measured.

		``None`` rather than a mean over the measured subset: a mean whose denominator
		silently excludes the dispatches nobody measured is the flattering reading, and it
		is the one a cost comparison would use.
		"""
		if not self.tokens_measured or self.dispatches == 0:
			return None
		return self.tokens / self.dispatches


class SpendReport(View):
	"""FR-133's attribution: the same dispatch spend bucketed per phase and per module.

	**Every bucket is a count of rows that exist, and ``dispatches`` sums to the total.**
	That is the property that makes this a fold rather than a summary: a reader can add
	the phase buckets and get the same number as adding the module buckets, and a
	discrepancy is a bug rather than a rounding. ``unattributed`` carries the dispatches
	whose step no module owned — a bootstrap step covers no clause, and FR-100's own
	:attr:`~sofact.views.ModuleCheckout.module` is ``None`` for it — so the module buckets
	plus ``unattributed`` account for every row. Dropping them would make the module
	totals quietly smaller than the phase totals with nothing to say why.

	**Against the §1.3 envelope, and honest about which dimension.** §1.3's eight
	dimensions contain exactly one that bounds spend: ``wall_clock_days``. There is no
	token dimension, so FR-133's "reported against the envelope" is discharged for wall
	clock and *stated as unbounded* for tokens — :attr:`token_dimension` is ``None`` and
	:attr:`token_envelope_note` says why. Inventing a ninth dimension to have something to
	compare against would be SoFact bounding a resource its operator never bounded
	(NFR-025), and silently omitting the comparison would leave the requirement reading as
	met when half of it has nowhere to be measured.

	**The vacuous pass is refused**, on :attr:`AttemptTelemetryReport.discharged`'s rule: a
	plan with no dispatch returns ``()``. "0 tokens over 0 sessions" is the shape a clean
	result takes when there was no run, not a measurement of a cheap one.
	"""

	id: UUID7
	plan_id: UUID7
	rendered_at: datetime
	by_phase: tuple[SpendAttribution, ...] = ()
	by_module: tuple[SpendAttribution, ...] = ()
	envelope: DeliveryEnvelope | None = None
	"""The §1.3 envelope this run is measured against, or ``None`` when none is configured.

	``None`` is *no envelope was chosen*, not "§1.3's defaults" — :meth:`FactoryService.envelope`
	draws that distinction and this field carries it rather than re-deciding it.
	"""

	unattributed: int = 0
	"""Dispatches whose step no single module owned. Counted, never dropped (FR-100)."""

	@property
	def total_dispatches(self) -> int:
		return sum(bucket.dispatches for bucket in self.by_phase)

	@property
	def total_wall_clock_seconds(self) -> float:
		return sum(bucket.wall_clock_seconds for bucket in self.by_phase)

	@property
	def total_tokens(self) -> int:
		"""Summed tokens over the dispatches that reported usage. A floor, not a total."""
		return sum(bucket.tokens for bucket in self.by_phase)

	@property
	def unmeasured_tokens(self) -> int:
		return sum(bucket.unmeasured_tokens for bucket in self.by_phase)

	@property
	def tokens_complete(self) -> bool:
		"""True when every dispatch reported usage, so the token total is exact."""
		return self.unmeasured_tokens == 0

	@property
	def token_dimension(self) -> EnvelopeDimension | None:
		"""Always ``None``: §1.3 bounds no token dimension, so there is nothing to compare.

		A property rather than an absent field so the *reason* travels with the reading —
		a reader who looks for the token comparison and finds nothing must find this
		instead of concluding the number was forgotten.
		"""
		return None

	@property
	def token_envelope_note(self) -> str:
		"""Why tokens are attributed but not compared to the envelope (FR-133, NFR-025)."""
		dimensions = ", ".join(d.value for d in EnvelopeDimension)
		return (
			f"§1.3 bounds {len(EnvelopeDimension)} dimensions ({dimensions}) and none of "
			"them is tokens. FR-133's attribution is reported above and the envelope "
			"comparison is made on wall clock, the one dimension that bounds spend; a "
			"token bound would be a resource SoFact bounded and its operator did not "
			"(NFR-025, and §20.4's 'tokens per verified module' is a metric rather than a "
			"bound)"
		)

	@property
	def wall_clock_measurement(self) -> EnvelopeMeasurement | None:
		"""The run's wall clock against §1.3's ``wall_clock_days``, or ``None``.

		``None`` when no envelope is configured — the three-state rule
		:class:`EnvelopeMeasurement` states: an unmeasured dimension is never reported as
		satisfied, and "nobody set an envelope" is not "the envelope held".

		**A measurement rather than a boolean, because §1.3's bound is a range.** Its
		``wall_clock_days`` is 2-10: a floor *and* a ceiling, since §1.3 is a hypothesis
		under test about what a delivery costs rather than a cap. A bare ``within`` would
		report a run that took twenty minutes and a run that took twenty days as the same
		answer, and only one of those is the failure FR-133 is about — so the direction is
		carried by :attr:`EnvelopeMeasurement.within` *and* by the detail, and
		:attr:`wall_clock_over_envelope` answers the overspend question on its own.
		"""
		if self.envelope is None:
			return None
		days = self.total_wall_clock_seconds / 86400.0
		bound = self.envelope.bound(EnvelopeDimension.WALL_CLOCK_DAYS)
		within = bound.admits(days)
		if within:
			detail = (
				f"{days:.4f} day(s) of session wall clock, inside §1.3's {bound.stated()} (FR-133)"
			)
		elif bound.minimum is not None and days < bound.minimum:
			detail = (
				f"{days:.4f} day(s) of session wall clock is *below* §1.3's "
				f"{bound.stated()}. This is not an overspend: §1.3's figure is a target "
				"range and the run came in under it, which for a partial run is expected "
				"and for a complete one is the envelope's floor being wrong"
			)
		else:
			detail = (
				f"{days:.4f} day(s) of session wall clock exceeds §1.3's "
				f"{bound.stated()}. FR-133's own rationale is this direction: an "
				"unattended build with no spend attribution is an unbounded financial "
				"commitment (NFR-029, FR-101)"
			)
		return EnvelopeMeasurement(
			dimension=EnvelopeDimension.WALL_CLOCK_DAYS,
			bound=bound,
			actual=days,
			within=within,
			detail=detail,
		)

	@property
	def wall_clock_over_envelope(self) -> bool | None:
		"""True only when the run's wall clock *exceeds* §1.3's ceiling (FR-133).

		``None`` when no envelope is configured. ``False`` covers both "inside the range"
		and "below the floor", because neither is an overspend — and reporting a fast run
		as an envelope failure is the reading that would train an operator to ignore this
		column.
		"""
		measurement = self.wall_clock_measurement
		if measurement is None or measurement.actual is None:
			return None
		ceiling = measurement.bound.maximum
		return ceiling is not None and measurement.actual > ceiling

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this reading carried out, which may be none."""
		if not self.by_phase:
			return ()
		return SPEND_ATTRIBUTION_REQUIREMENTS


SPEND_ATTRIBUTION_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-133", "NFR-030")
"""What :attr:`SpendReport.discharged` reports when the fold carried it out.

FR-133 is the requirement and NFR-030 is the reason it exists — "cost per delivered
module is knowable" is the sentence the per-module bucket answers. Naming both keeps a
future gate from discharging the attribution while leaving the module key absent, which
is the state this unit was written to leave.
"""


ATTEMPT_TELEMETRY_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-102",)
"""What :attr:`AttemptTelemetryReport.discharged` reports when the fold carried it out.

One requirement, because FR-102 is one sentence with three nouns in it. Naming it here
rather than in the fold keeps the two readings of "is this discharged" — the property and
any future gate — from drifting apart.
"""


GOAL_MODE_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-144", "FR-153")
"""What one goal-mode reading can carry out.

Two requirements, and the pair is deliberate. FR-153 is the one §20.3 item 6a leaves open
— entry must be *forced* and verified from the session log — and FR-144 is the degradation
that must be *reported* when it is not. A reading that counted goal-mode dispatches without
checking whether their entry was forced would discharge neither: it would report sessions
that were asked to enter goal mode as sessions that did.

**FR-135 is deliberately absent.** The capability matrix is the *probe's* discharge, on a
:class:`HarnessProfile` this fold does not read, and a dispatch is not evidence about the
matrix — it is evidence about what one session did. Naming FR-135 here would let a
project's dispatch history stand in for a probe it never ran.
"""

GOAL_ENTRY_NOT_FORCED: Final[str] = (
	"a dispatch whose mode is `goal` and whose observed entry is `prompt` was *asked* to "
	"enter goal mode, not made to. [S21] measured that the capability is loaded and the "
	"producer never entered it; FR-153 requires entry by construction and verification "
	"from the session log, so such a dispatch is a capability loss reported under FR-144 "
	"rather than a goal session. The count is stated beside the goal-mode count because "
	"the flattering reading — 'goal mode ran' — is available from the mode alone, and the "
	"mode is what the probe decided before the session began."
)

GOAL_CONTINUATION_UNMEASURED: Final[str] = (
	"a harness that writes no turn boundary reports `None`, never 1. `pi`, `claude` and "
	"`opencode` declare no continuation event, so a dispatch on them is *unmeasured* "
	"rather than a single-turn session — and a mean over the harnesses that do number "
	"their turns is a fact about those harnesses, which is why the coverage count travels "
	"beside it (NFR-024)."
)


class GoalModeRow(View):
	"""One dispatch's goal-mode facts, as its session record witnessed them (FR-153).

	Three fields and they must not be merged. ``mode`` is what the *probe* decided before
	the session started — it is a prediction. ``entry`` is how the objective actually
	reached the session, read from the record afterwards. ``continuations`` is how many
	turns the session took, where the harness numbers them.

	A dispatch can carry a goal ``mode`` and a ``prompt`` entry, and that pair is the whole
	subject of §20.3 item 6a: the probe said goal-capable, and the session shows the model
	was asked rather than made to enter it.
	"""

	dispatch_id: UUID7
	step_id: UUID7
	harness: NonEmptyStr
	mode: DispatchMode
	entry: GoalEntry | None = None
	"""How the goal reached the session, or ``None`` when no record was read.

	``None`` is *not observed*, which is a different fact from :attr:`GoalEntry.PROMPT`.
	A dispatch that left no session record behind has no entry to report, and rounding it
	to ``PROMPT`` would invent a reading of a session nobody saw.
	"""

	continuations: int | None = None
	"""Turns the session ran, or ``None`` where the harness numbers none (FR-153)."""

	@property
	def forced(self) -> bool:
		"""Whether the objective *entered* the session rather than being requested."""
		return self.entry is not None and self.entry.is_forced

	@property
	def ran_as_goal(self) -> bool:
		"""Whether the dispatch was sent as a goal, per the probe's decision."""
		return self.mode is DispatchMode.GOAL

	@property
	def is_contradiction(self) -> bool:
		"""A dispatch sent as a goal whose *read* session shows no forced entry (FR-153).

		This is the defect the whole reading exists to make visible, and it is invisible
		from either field alone: the mode says goal, the entry says prompt, and only the
		conjunction says *the capability the probe claimed was not exercised*.

		Requires :attr:`entry` to be non-``None``. A dispatch whose session left no record
		has nothing to contradict: the contradiction is a claim about what the record
		showed, and a session nobody read showed nothing. Reading ``entry is None`` as a
		prompt would report every unwitnessed dispatch as a capability loss, which is the
		same error as reporting an unmeasured continuation count as one turn.
		"""
		return self.ran_as_goal and self.entry is not None and not self.forced


class GoalModeReport(View):
	"""§20.3 item 6a: whether goal entry was forced, and whether continuations were seen.

	The M0 probe's blocking question, read from dispatches rather than from documentation.
	[S21] answered it at n=1 — goal mode present and loaded, the producer never entered it,
	zero goal-typed events, `todo_write` substituted — and §20.3 says what remains open is
	"not whether the capability exists but whether entry can be **forced** and continuations
	observed". This fold is that question asked of a project's own sessions.

	**What it does not claim.** A project whose producers never entered goal mode is more
	observations of [S21], not a proof that entry cannot be forced — the mechanism may
	exist on a harness this project never dispatched, and a negative over one configuration
	is not a negative over the interface. So :attr:`forced_entries` of zero is reported as
	*not observed to be forcible* and the caveat says so, which is the same limit
	:attr:`EscapeReport.discharged` and §1.4's sub-linearity both carry: a reading over one
	population is a fact about that population.
	"""

	id: UUID7
	rendered_at: datetime
	rows: tuple[GoalModeRow, ...] = ()

	@property
	def witnessed(self) -> tuple[GoalModeRow, ...]:
		"""The dispatches whose session record was read, so an entry could be observed.

		The denominator for every claim here, and the reason a dispatch that left no record
		is counted rather than dropped: "no goal event was found" and "no record was read"
		are the two answers §20.3 item 6a must keep apart, and only the first is evidence.
		"""
		return tuple(row for row in self.rows if row.entry is not None)

	@property
	def goal_dispatches(self) -> tuple[GoalModeRow, ...]:
		"""The dispatches sent as goals, per the probe's pre-session decision."""
		return tuple(row for row in self.rows if row.ran_as_goal)

	@property
	def forced_entries(self) -> tuple[GoalModeRow, ...]:
		"""The sessions whose objective *entered* goal mode — FR-153's positive evidence."""
		return tuple(row for row in self.witnessed if row.forced)

	@property
	def contradictions(self) -> tuple[GoalModeRow, ...]:
		"""Goal dispatches with no forced entry: the capability the probe claimed, absent."""
		return tuple(row for row in self.rows if row.is_contradiction)

	@property
	def measured_continuations(self) -> tuple[GoalModeRow, ...]:
		"""The dispatches on a harness that numbers its turns."""
		return tuple(row for row in self.rows if row.continuations is not None)

	@property
	def total_continuations(self) -> int:
		"""Summed turns over the harnesses that number them. A floor, not a total."""
		return sum(row.continuations or 0 for row in self.measured_continuations)

	@property
	def mean_continuations(self) -> float | None:
		"""Turns per measured session, or ``None`` when none was measured (NFR-024).

		``None`` rather than ``0.0`` for :attr:`AttemptTelemetryReport.tokens_complete`'s
		reason: zero continuations is the claim that every session ran exactly one turn,
		which is a measurement, and a harness that writes no turn boundary has not made it.
		"""
		measured = self.measured_continuations
		if not measured:
			return None
		return self.total_continuations / len(measured)

	@property
	def continuation_coverage(self) -> tuple[int, int] | None:
		"""Measured sessions against witnessed ones, or ``None`` when none was witnessed.

		Beside the mean rather than in a footnote, for ADR-0068's reason: a mean over the
		harnesses that number their turns is a fact about those harnesses, and a reader who
		takes it for the project's goal behaviour has been misled by a subset that happens
		to be the measurable one.
		"""
		if not self.witnessed:
			return None
		return len(self.measured_continuations), len(self.witnessed)

	@property
	def entry_forced(self) -> bool | None:
		"""Whether forced entry was *observed at all*, or ``None`` when nothing was read.

		Three states and they are not two. ``True`` — at least one session shows a forced
		entry, so the mechanism works on this configuration. ``False`` — sessions were read
		and none was forced, which is [S21] reproduced, not a proof of impossibility.
		``None`` — no session record was read, so the question was never asked. Collapsing
		``False`` and ``None`` would report an absent instrument as a measured negative.
		"""
		if not self.witnessed:
			return None
		return bool(self.forced_entries)

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this reading carried out, which may be none (NFR-024).

		A reading over zero witnessed sessions claims nothing, and neither does one whose
		goal dispatches all contradicted their own mode: FR-153 is discharged by a session
		that *entered* goal mode, so a project that only ever asked has not carried it out.
		That is the rule :attr:`EscapeReport.discharged` states, applied where the vacuous
		pass would otherwise be the *likely* outcome rather than an edge case.
		"""
		if not self.forced_entries:
			return ()
		return GOAL_MODE_REQUIREMENTS

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-144/FR-153 this reading did not carry out."""
		discharged = set(self.discharged)
		return tuple(name for name in GOAL_MODE_REQUIREMENTS if name not in discharged)

	@property
	def caveats(self) -> tuple[str, ...]:
		"""What this reading does not claim, stated rather than left to inference."""
		return (GOAL_ENTRY_NOT_FORCED, GOAL_CONTINUATION_UNMEASURED)


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


HARNESS_SELECTION_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-135", "FR-143", "FR-147")
"""What a harness selection is a reading *of*, so a vacuous one can refuse to claim it.

The rule :data:`ATTEMPT_TELEMETRY_REQUIREMENTS` and :data:`ESCAPE_REQUIREMENTS` both
state: a report over nothing discharges nothing. A selection that chose a harness
because the deployment declared a default has not carried out FR-147, and saying it had
would be the reputation-driven choice this requirement exists to replace.
"""


class HarnessMetric(View):
	"""One harness's §20.4 readings, and which of them are measurements (FR-147).

	FR-147: "Harness selection must be **empirical** — driven by measured
	goal-declaration precision (§20.4) and throughput, not by reputation." §20.4 lists
	five meta-harness metrics; this type carries all five so a reader sees the whole
	matrix, and :func:`sofact.selection.select_harness` ranks on the two FR-147 names.

	**Two questions that look like one, and are not.** ``corroborated`` is over the
	dispatches that *declared* completion, which is :class:`DeclarationPrecision`'s
	denominator: a producer that never says it is done has no precision, and dividing by
	its silence would score it on nothing. ``verified_modules`` is over every dispatch
	regardless of declaration, because whether a module's clauses were satisfied is the
	*verifier's* finding and does not depend on the producer having an opinion. A harness
	that never declares and whose work is nonetheless verified clean has good throughput
	and unmeasured precision, and those are both true statements about it.

	**Unmeasured is not zero and it is not disqualifying.** Every rate here is ``None``
	when its denominator is zero (NFR-024), and ``None`` sorts *last* in a ranking rather
	than first — the defect this type exists to make impossible is a harness that has
	never run winning a contest against one that has, on the strength of a rate nobody
	computed.
	"""

	harness: NonEmptyStr
	probed: bool = False
	"""Whether a capability probe has ever run against this harness (FR-148)."""

	supports_goal_dispatch: bool | None = None
	"""FR-135's disqualifying pair, or ``None`` when no probe has answered it.

	``None`` rather than ``False``, because an unprobed harness has not *failed* to
	support goal mode — nobody asked it. Collapsing the two would exclude a harness from
	selection on the strength of a probe that never ran, which is
	:attr:`~sofact.views.HarnessProfile.observation`'s ``INCONCLUSIVE`` rule one level up.
	"""

	dispatches: int = 0
	declarations: int = 0
	corroborated: int = 0
	modules: tuple[NonEmptyStr, ...] = ()
	verified_modules: tuple[NonEmptyStr, ...] = ()
	unverified_modules: tuple[NonEmptyStr, ...] = ()
	continuations: int = 0
	unmeasured_continuations: int = 0
	tokens: int = 0
	unmeasured_tokens: int = 0
	wall_clock_seconds: float = 0.0
	integrity_checks: int = 0
	integrity_failures: int = 0

	@model_validator(mode="after")
	def _consistent(self) -> Self:
		counts = {
			"dispatches": self.dispatches,
			"declarations": self.declarations,
			"corroborated": self.corroborated,
			"continuations": self.continuations,
			"unmeasured_continuations": self.unmeasured_continuations,
			"tokens": self.tokens,
			"unmeasured_tokens": self.unmeasured_tokens,
			"integrity_checks": self.integrity_checks,
			"integrity_failures": self.integrity_failures,
		}
		negative = sorted(name for name, value in counts.items() if value < 0)
		if negative:
			raise ValueError(f"{self.harness}: {negative} cannot be negative")
		if self.corroborated > self.declarations:
			raise ValueError(
				f"{self.harness}: {self.corroborated} corroborated declarations out of "
				f"{self.declarations} is impossible"
			)
		if self.integrity_failures > self.integrity_checks:
			raise ValueError(
				f"{self.harness}: {self.integrity_failures} integrity failures over "
				f"{self.integrity_checks} check(s) is impossible"
			)
		if self.wall_clock_seconds < 0:
			raise ValueError(
				f"{self.harness}: wall clock cannot be negative, got {self.wall_clock_seconds}"
			)
		# A module cannot be both, and neither list can name a module the harness never
		# touched. Both are counts *of* `modules`, and a subset that escaped it would be
		# a rate with a denominator nobody could check.
		known = set(self.modules)
		stray = sorted((set(self.verified_modules) | set(self.unverified_modules)) - known)
		if stray:
			raise ValueError(f"{self.harness}: {stray} are classified but were never dispatched")
		both = sorted(set(self.verified_modules) & set(self.unverified_modules))
		if both:
			raise ValueError(f"{self.harness}: {both} are recorded as verified and unverified")
		return self

	@property
	def precision(self) -> float | None:
		"""§20.4's goal-declaration precision, or ``None`` with no declaration (FR-143)."""
		if self.declarations == 0:
			return None
		return self.corroborated / self.declarations

	@property
	def is_measured(self) -> bool:
		"""Whether *any* §20.4 reading here has a denominator.

		Precision needs a declaration and the per-module rates need a verified module, so
		a harness with dispatches and no verdict is unmeasured rather than bad — it has
		run and nothing has judged it yet.
		"""
		return self.declarations > 0 or bool(self.verified_modules)

	@property
	def seconds_per_verified_module(self) -> float | None:
		"""Throughput, inverted so that *lower is better* — the unit FR-147 ranks on.

		Seconds per module rather than modules per second because a module-per-second
		rate on a fast harness rounds to a number that cannot be compared with a slow
		one, and because wall clock is the resource §1.3 bounds.
		"""
		if not self.verified_modules:
			return None
		return self.wall_clock_seconds / len(self.verified_modules)

	@property
	def tokens_per_verified_module(self) -> float | None:
		"""§20.4's token rate, or ``None`` — reported, and deliberately not ranked on.

		FR-147 names precision and throughput, and this is neither. It is carried because
		it is the number that drives §1.3's envelope actuals and FR-132's tiering, and a
		selection report that omitted it would send its reader to a second verb for the
		one figure that explains the bill.
		"""
		if not self.verified_modules:
			return None
		return self.tokens / len(self.verified_modules)

	@property
	def continuations_per_verified_module(self) -> float | None:
		"""§20.4's plan-compilation reading, or ``None``. Reported, not ranked on."""
		if not self.verified_modules:
			return None
		return self.continuations / len(self.verified_modules)

	@property
	def exclusion_reason(self) -> str | None:
		"""Why this harness cannot be selected, or ``None`` when it can (FR-135, FR-147).

		Three reasons, and the *order* is the point: a harness that edited its own
		success criteria is excluded whatever else it measures, because §20.4 calls that
		"the sharpest form of goal-hacking" and a harness that goal-hacks is not one you
		rank lower — it is one you do not run. FR-135's disqualifying pair comes next, and
		it is FR-135's word: a harness lacking goal mode or interactive-free operation is
		disqualifying for P5. Never having been probed is last and is a different claim
		again: the harness may be excellent and simply unmeasured, and FR-148 requires a
		recorded profile before any dispatch, so it cannot be chosen here either.
		"""
		if self.integrity_failures:
			return (
				f"{self.integrity_failures} contract-integrity failure(s) (FR-139): a harness "
				"that edited its own success criteria or its own tests is not a harness to "
				"rank lower, it is one not to run (§20.4)"
			)
		if not self.probed:
			return (
				"never probed, and FR-148 requires a recorded profile before any dispatch, so "
				"there is no capability finding to select on"
			)
		if not self.supports_goal_dispatch:
			return (
				"FR-135: goal mode and interactive-free operation are both required for P5, "
				"and the probe did not confirm them (FR-144's reduced mode is the fallback)"
			)
		return None

	@property
	def is_selectable(self) -> bool:
		"""Whether this harness may be chosen at all, measurement aside (FR-135)."""
		return self.exclusion_reason is None


class HarnessSelection(View):
	"""Which harness FR-147 selects, on what measurement, and why not the others.

	**The defect this type exists to prevent is a contest that was never run.** Before it,
	the only thing that chose a harness was :meth:`~sofact.service.FactoryService.harness_name`,
	which takes ``--harness``, then ``SOFACT_HARNESS``, then :data:`~sofact.service.DEFAULT_HARNESS`,
	then a table with exactly one entry — and refuses an ambiguous table rather than
	picking one. Every one of those is *reputation or declaration*, which is precisely what
	FR-147 says selection must not be driven by. So this report can return
	``chosen is None``: that is not a failure to decide, it is the honest answer when
	nothing has been measured and the deployment declared no default.

	**A selection is not a measurement of the work.** It says which producer is likelier to
	know when it is done, at what speed. It says nothing about whether the modules either
	produced are correct — that is :class:`VerificationReport`'s question and FR-138's whole
	point. Reading this as a quality ranking would be the substitution
	:attr:`HarnessProfile.goal_mode` warns about one level down.

	**The vacuous pass is refused**, on :attr:`AttemptTelemetryReport.discharged`'s rule: a
	selection that fell back to a declared default returns ``discharged == ()``, because
	choosing what the operator already named is not carrying out FR-147.
	"""

	id: UUID7
	rendered_at: datetime
	metrics: tuple[HarnessMetric, ...] = ()
	"""Every configured harness, measured or not, in name order.

	*Every* one, including the excluded: a report that listed only the candidates would
	make a harness that failed FR-135 indistinguishable from one that was never
	configured, and the operator's next question is always about the one that is missing.
	"""

	chosen: NonEmptyStr | None = None
	"""The selected harness, or ``None`` when nothing could be selected (FR-147).

	``None`` is a first-class answer and never a silent fallback: the CLI reports it as
	*no selection* and the driver refuses rather than dispatching to a harness the
	measurement did not choose.
	"""

	reason: NonEmptyStr
	"""Why, in words — including which rule decided, so a reader can audit the decision."""

	@model_validator(mode="after")
	def _the_choice_is_a_candidate(self) -> Self:
		names = {m.harness for m in self.metrics}
		if len(names) != len(self.metrics):
			raise ValueError("a harness appears twice in one selection")
		if self.chosen is not None and self.chosen not in names:
			raise ValueError(
				f"selected {self.chosen!r}, which is not among the harnesses this selection "
				"measured; a choice outside the candidate set is a choice nothing supports"
			)
		return self

	@property
	def candidates(self) -> tuple[HarnessMetric, ...]:
		"""Harnesses that may be chosen at all, in name order (FR-135)."""
		return tuple(m for m in self.metrics if m.is_selectable)

	@property
	def excluded(self) -> tuple[HarnessMetric, ...]:
		"""Harnesses that may not be chosen, each carrying its own reason."""
		return tuple(m for m in self.metrics if not m.is_selectable)

	@property
	def measured(self) -> tuple[HarnessMetric, ...]:
		"""Candidates with at least one §20.4 reading that has a denominator."""
		return tuple(m for m in self.candidates if m.is_measured)

	@property
	def unmeasured(self) -> tuple[HarnessMetric, ...]:
		"""Candidates nothing has judged yet — a real state, and not a low score."""
		return tuple(m for m in self.candidates if not m.is_measured)

	@property
	def ranked(self) -> tuple[HarnessMetric, ...]:
		"""The measured candidates best-first: precision, then throughput (FR-147).

		The two axes FR-147 names, in the order it names them. A tie on both is not
		broken here — :attr:`tied` reports it, because a sort key that silently resolved
		one would be an arbitrary choice wearing a measurement's clothes.
		"""
		return tuple(
			sorted(
				self.measured,
				key=lambda m: (
					-(m.precision if m.precision is not None else 0.0),
					m.seconds_per_verified_module
					if m.seconds_per_verified_module is not None
					else float("inf"),
					m.harness,
				),
			)
		)

	@property
	def best(self) -> HarnessMetric | None:
		"""The top of :attr:`ranked`, or ``None`` when nothing is measured."""
		ranked = self.ranked
		return ranked[0] if ranked else None

	@property
	def tied(self) -> tuple[NonEmptyStr, ...]:
		"""Candidates equal to the best on *both* ranked axes, best included (FR-147).

		More than one name here means the measurement did not separate them, and the
		selection says so rather than letting the alphabetical fallback in :attr:`ranked`
		read as a finding. A tie between two harnesses that have both run is genuinely
		undecided by the two numbers FR-147 supplies.
		"""
		top = self.best
		if top is None:
			return ()
		return tuple(
			m.harness
			for m in self.ranked
			if m.precision == top.precision
			and m.seconds_per_verified_module == top.seconds_per_verified_module
		)

	@property
	def discharged(self) -> tuple[str, ...]:
		"""The requirements this selection carried out, which may be none (NFR-024).

		FR-147 is discharged only when the choice rested on a measurement. A fallback to
		the deployment's declared default is a decision and is not a measurement of
		anything, so it discharges nothing — and the report says which happened rather
		than leaving a reader to infer it from ``chosen`` being non-``None``.
		"""
		if self.chosen is None or self.best is None:
			return ()
		return HARNESS_SELECTION_REQUIREMENTS

	@property
	def not_implemented(self) -> tuple[str, ...]:
		"""Requirements of FR-135/FR-143/FR-147 this selection did not carry out."""
		discharged = set(self.discharged)
		return tuple(name for name in HARNESS_SELECTION_REQUIREMENTS if name not in discharged)

	@property
	def caveats(self) -> tuple[str, ...]:
		"""What this selection does not claim, stated rather than left to inference."""
		notes: list[str] = []
		if self.unmeasured:
			names = ", ".join(m.harness for m in self.unmeasured)
			notes.append(
				f"{names} have run and nothing has judged them yet, so they are unmeasured "
				"rather than ranked last; a harness with no reading cannot lose a contest "
				"it has not entered (NFR-024)"
			)
		if len(self.tied) > 1:
			notes.append(
				"the top candidates are tied on both precision and throughput, so the order "
				"between them is arbitrary and the measurement did not decide it (FR-147)"
			)
		if self.chosen is not None and self.best is None:
			notes.append(
				"the choice was not empirical: it fell back to a declared harness because "
				"nothing has been measured (FR-147, NFR-024)"
			)
		return tuple(notes)


class SearchOutcome(StrEnum):
	"""What one query returned, which is not the same question as whether it ran (FR-174).

	``OK`` and ``NO_RESULTS`` are both successful executions: a search that found nothing
	answered the question, and recording it as a failure would push a provider — or a
	reader — toward treating an empty result as a reason to re-run rather than as the
	measurement it is. The same distinction :func:`sofact.competitive.parse_competitors`
	draws about a scan over zero rivals.

	``FAILED`` is the only member that means the tool did not answer, and it is separate
	from the run-level exit code because one query of six failing does not make the scan
	unusable — it makes five of six queries usable, and the count is the finding.
	"""

	OK = "ok"
	NO_RESULTS = "no-results"
	FAILED = "failed"


class SearchHit(View):
	"""One result a search provider returned, and how far it was checked (FR-174).

	**A hit is a lead, not a source.** A search provider returns a title, a url and a
	snippet, and a snippet is a fragment the provider chose and possibly generated. The
	honest record of that is ``REPORTED`` — neither the text read nor the link resolved —
	which is why the default is the weakest rung of :class:`VerificationStatus` rather
	than the strongest. A hit promoted to ``CONTENT_VERIFIED`` by this phase would let a
	provider's excerpt be cited as though a human had read the page, which is the exact
	substitution that enum's own docstring exists to prevent.

	``posture`` is recorded for the same reason and with the same default: a provider
	cannot know whose interest a result serves, and a vendor's own page ranking first is
	not evidence about the vendor. It is ``POSITIONING`` when the provider says so and
	``EVIDENCE`` otherwise, and either way
	:meth:`SourceLedger.unbacked_decisions` is what stops it deciding anything.
	"""

	rank: int
	title: NonEmptyStr
	url: NonEmptyStr
	snippet: str = ""
	provider: NonEmptyStr
	verification: VerificationStatus = VerificationStatus.REPORTED
	posture: SourcePosture = SourcePosture.EVIDENCE
	published: date | None = None
	"""The provider's date for the result, when it gave one. ``None`` is *undated*."""

	@model_validator(mode="after")
	def _a_rank_is_one_based(self) -> Self:
		if self.rank < 1:
			raise ValueError(
				f"search hit {self.url!r} has rank {self.rank}: ranks are one-based, and a "
				"zero or negative rank would make 'the top result' unreadable (FR-174)"
			)
		return self

	@model_validator(mode="after")
	def _a_hit_is_not_content_verified(self) -> Self:
		if self.verification is VerificationStatus.CONTENT_VERIFIED:
			raise ValueError(
				f"search hit {self.url!r} is content-verified: a search result is a title, "
				"a url and a provider's snippet, and no part of this phase read the page. "
				"Marking one content-verified would let an excerpt be cited as though a "
				"human had read it (FR-174, FR-069)"
			)
		return self


class SearchQueryResult(View):
	"""One authored query and what it returned (FR-174).

	The query is stored verbatim. It is SoFact's own text — authored before any provider
	ran — so keeping it makes "what was asked" answerable from the log alone, which is
	the same reason :func:`sofact.service.research_goal` writes the clause ids into the
	prompt rather than letting a producer choose its subject list.
	"""

	query: NonEmptyStr
	outcome: SearchOutcome
	hits: tuple[SearchHit, ...] = ()
	provider: NonEmptyStr
	exit_code: int | None = None
	error: str | None = None
	"""The provider's own words, when it failed. Kept because a refusal that drops the
	tool's message leaves an operator with nothing to act on."""

	duration_seconds: float | None = None

	@model_validator(mode="after")
	def _a_failed_query_carries_its_reason(self) -> Self:
		if self.outcome is SearchOutcome.FAILED and not self.error:
			raise ValueError(
				f"query {self.query!r} is recorded failed with no reason: a failure whose "
				"cause was dropped is indistinguishable from a provider that returned "
				"nothing, and the two need different responses (FR-174)"
			)
		return self

	@model_validator(mode="after")
	def _a_result_without_hits_is_not_ok(self) -> Self:
		if self.outcome is SearchOutcome.OK and not self.hits:
			raise ValueError(
				f"query {self.query!r} is recorded ok with no hits: a provider that "
				"returned nothing returned no results, and recording that as success "
				"would inflate the hit count this phase is measured by (FR-174, NFR-024)"
			)
		return self

	@property
	def hit_count(self) -> int:
		return len(self.hits)


class SearchScan(View):
	"""One search provider's answers to the queries SoFact authored (FR-174).

	This is the phase that makes "web search and deep research" a capability of this
	product rather than a thing it asks someone else to do. SoFact authors the queries
	deterministically, a declared provider answers them, and the answers are recorded as
	leads with the weakest verification rung — so the scan widens what the research phase
	can cite without ever letting a provider's snippet become the evidence itself.

	``provider`` is recorded per scan as well as per result because a run may consult
	more than one, and "which engine said this" is part of how a hit is read.
	"""

	id: UUID7
	goal_id: UUID7 | None = None
	provider: NonEmptyStr
	results: tuple[SearchQueryResult, ...] = ()
	started_at: datetime
	finished_at: datetime | None = None
	exit_code: int | None = None
	error: str | None = None

	@property
	def hits(self) -> tuple[SearchHit, ...]:
		"""Every hit from every query, in query order."""
		return tuple(hit for result in self.results for hit in result.hits)

	@property
	def hit_count(self) -> int:
		return len(self.hits)

	@property
	def queries_answered(self) -> int:
		"""Queries the provider actually answered, either way (FR-174).

		A no-results answer counts. It is an answer, and excluding it would make a scan
		over a narrow domain read as a scan that never ran.
		"""
		return sum(1 for r in self.results if r.outcome is not SearchOutcome.FAILED)

	@property
	def found_nothing(self) -> bool:
		"""Whether every query was answered and none returned a hit (NFR-024).

		``None``-like: false when any query failed, because a scan with a failed query
		has not established that there is nothing — it has established that it does not
		know. Reading a partial scan as "nothing exists" is the inventing-a-measurement
		failure NFR-024 names.
		"""
		return (
			bool(self.results)
			and self.hit_count == 0
			and self.queries_answered == len(self.results)
		)

	@property
	def unanswered_queries(self) -> tuple[str, ...]:
		return tuple(r.query for r in self.results if r.outcome is SearchOutcome.FAILED)


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
	DIFF_REVIEWED = "diff.reviewed"
	ORACLE_AUDITED = "oracle.audited"
	ADVERSARIAL_AUDITED = "adversarial.audited"
	AUTHORSHIP_CHECKED = "authorship.checked"
	ESCAPE_RECORDED = "escape.recorded"
	ESCAPE_OVERRIDE_RECORDED = "escape_override.recorded"
	TRANSCRIPT_RECORDED = "transcript.recorded"
	ELICITATION_ATTESTED = "elicitation.attested"
	COMPETITIVE_SCAN_RECORDED = "competitive_scan.recorded"
	EXCEEDS_DECLARED = "exceeds.declared"
	PRODUCT_SPEC_RENDERED = "product_spec.rendered"
	DRIVER_ADVANCED = "driver.advanced"
	NOTIFICATION_SENT = "notification.sent"
	SEARCH_SCAN_RECORDED = "search_scan.recorded"


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


# --------------------------------------------------------------------------- #
# FR-120 — the machine surface's envelope
# --------------------------------------------------------------------------- #

MACHINE_API_VERSION: Final[str] = "1"
"""The machine surface's version, carried on every response (FR-120).

A *string* and not a number, because FR-120's word is "stable" and the useful thing a
caller can do with a version is compare it for equality, not order it. Bumping it is how a
change to an operation's shape is announced; the operations themselves are named, so
adding one does not bump this and changing what one returns does.
"""


class MachineOperation(View):
	"""One operation FR-120's surface publishes.

	The ``invariant`` is a field rather than a docstring because it travels: a caller that
	reads the table learns *why* the operation is shaped as it is, and the same sentence
	appears on the response the operation returns. An operation whose invariant is only in
	the source is one a caller has to read the source to trust.
	"""

	name: NonEmptyStr
	summary: NonEmptyStr
	returns: NonEmptyStr
	invariant: NonEmptyStr


class MachineRequest(View):
	"""One call against FR-120's surface.

	``arguments`` is a free mapping rather than a typed union, because the surface is
	read-only and its operations take at most a name. A typed union of nine near-empty
	argument models would be nine types to keep in step with the table for no gain; when an
	operation needs an argument, this field's *contents* get a type and the shape of the
	envelope does not change.
	"""

	operation: NonEmptyStr
	arguments: dict[str, str] = {}


class MachineEnvelope(View):
	"""What FR-120's surface returns: one closed shape for every operation.

	``ok`` is **derived** from ``error`` rather than stored beside it, so a response cannot
	report success and carry an error at once — the discipline
	:func:`sofact.delivery.report` applies to its own checks, one surface along. A refused
	operation carries ``result=None``: a refusal that also returned a partial answer is an
	answer a caller would use.

	It is a :func:`~pydantic.computed_field` rather than a plain property for a reason that
	is the whole surface: the caller here is a *program* reading JSON, and a plain property
	is absent from the serialised document, so the one field a caller branches on would be
	the one field it could not see. Computed is still not stored — the field cannot be set,
	and a payload that carried ``ok`` would be rejected as an extra field.
	"""

	id: UUID7
	api_version: str
	operation: str
	invariant: str
	error: str | None = None
	result: Any = None

	@computed_field  # type: ignore[prop-decorator]
	@property
	def ok(self) -> bool:
		"""Whether the operation was answered. The one place the two halves can disagree."""
		return self.error is None

	@model_validator(mode="after")
	def _a_refusal_carries_no_result(self) -> Self:
		if self.error is not None and self.result is not None:
			raise ValueError(
				"a refused operation cannot also carry a result: a caller would use the "
				"partial answer and never read the refusal (FR-120)"
			)
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

	reviews: tuple[DiffReview, ...] = ()
	"""What each human review of a sealed diff cost, oldest first (§20.3 item 3).

	Appended and never keyed, by ``gate_costs``' rule: a second sitting on one diff is
	a second measurement rather than an edit, and the history of what was first claimed
	is itself part of what §20.3 is measuring. :meth:`latest_reviews` reads the latest
	per dispatch, so ``reviewed_minutes`` cannot double-count a diff reviewed twice.
	"""

	oracle_audits: tuple[OracleAuditReport, ...] = ()
	"""Every adversarial oracle audit the log records, oldest first (FR-107).

	Appended, never keyed, and for :attr:`gate_costs`'s reason: an audit is a measurement
	of a contract's oracles at a moment, so a second audit of a repaired oracle is a second
	measurement rather than an amendment of the first. :meth:`latest_oracle_audit` reads
	the most recent; the history is what shows FR-012's exploit-discovery rate over time.
	"""

	adversarial_audits: tuple[AdversarialAuditReport, ...] = ()
	"""Every adversarial audit pass the log records, oldest first (FR-012–015).

	Appended and never keyed, and the reason is FR-015's own shape: its subject is a
	*trend* — a rate that should go to zero and stay there — so the series is the datum and
	a latest-wins field would destroy exactly the plateau the requirement exists to make
	visible. :meth:`latest_adversarial_audit` reads the most recent for a report.
	"""

	authorship_checks: tuple[AuthorshipCheck, ...] = ()
	"""Every authorship check the log records, oldest first (FR-053, FR-055, FR-134).

	Appended and never keyed, and for a reason the other two audit series do not share: the
	subject is the *tree*, which changes under the check rather than around it. Keying to the
	latest would report the closure measured today while the reader believes it is reading
	the closure that held when the contract was authored — the stale-evidence mistake FR-006
	refuses one phase over. :meth:`latest_authorship_check` reads the most recent.
	"""

	escapes: tuple[EscapeEvent, ...] = ()
	"""Every escape the operator recorded, oldest first (FR-021).

	Appended, never keyed, and for a stronger reason than :attr:`gate_costs`: an escape is
	an event that happened, so two rows are two events — a revert and then a hotfix — and
	keying them would delete the second. FR-022's numerator collapses them by *defect*
	rather than by row, which is where that judgement belongs.
	"""

	escape_overrides: tuple[EscapeOverride, ...] = ()
	"""Every operator override of an escape budget, oldest first (FR-023).

	Appended, never keyed, with :meth:`latest_escape_override` reading the most recent per
	lane — :attr:`gate_costs`'s rule. The history is what makes FR-023's "logged and
	attributed" checkable: an override that was later withdrawn is still an override
	someone signed.
	"""

	transcripts: tuple[Transcript, ...] = ()
	"""Every transcription attempt, oldest first (FR-168).

	Appended, never keyed, and the reason is that a failed transcription is a real row:
	the attempt that produced nothing is what explains why the goal statement is what it
	is, and a fold that kept only usable transcripts would make the failure invisible.
	:meth:`transcript_for` reads the latest usable one per goal.
	"""

	attestations: tuple[ElicitationAttestation, ...] = ()
	"""Every human attestation of a model-proposed answer, oldest first (FR-173).

	Appended, never keyed, and for the opposite reason to a measurement: an attestation is
	a person's act rather than a reading, so a second one is a second person having read
	the answer. :meth:`attested_answer_ids` is the only intended reader.
	"""

	landscapes: tuple[CompetitiveLandscape, ...] = ()
	"""Every competitive scan the log records, oldest first (FR-169).

	Versioned like :attr:`ledgers` and :attr:`classifications`, and for the same reason: a
	rescan supersedes a landscape rather than replacing it, and what the earlier pass found
	is part of how the current baseline is read. :attr:`landscape` is the operative one.
	"""

	exceeds: tuple[ExceedsClaim, ...] = ()
	"""Every declared exceedance, oldest first (FR-170).

	Appended, never keyed — :attr:`gate_costs`'s rule. A declaration and its revision are
	two claims someone made, and :meth:`exceeds_for` reads the latest per requirement while
	the log keeps what was first claimed.
	"""

	product_specs: tuple[ProductSpecificationDocument, ...] = ()
	"""Every rendered product specification, oldest first (FR-171).

	Versioned like :attr:`deliveries`, and for a stronger reason: the document rendered
	before the P2 approval and the one rendered after it differ in exactly the marker the
	approver was deciding about, so superseding the first would erase what they were shown.
	:attr:`product_spec` is the operative one.
	"""

	driver_runs: tuple[DriverRun, ...] = ()
	"""Every driver invocation, oldest first (FR-172).

	Appended, never keyed: a resumed run is a second row rather than an amendment of the
	first, and that is what makes the resumable loop honest — the log shows how many times
	the driver ran and where each run stopped.
	"""

	notifications: tuple[Notification, ...] = ()
	"""Every notification attempt, oldest first (FR-172).

	Appended, never keyed, and the row exists whether or not it was delivered: "we told
	them" and "we meant to tell them" must not print the same line. :meth:`notification`
	reads the most recent.
	"""

	scans: tuple[SearchScan, ...] = ()
	"""Every search scan recorded, oldest first (FR-174).

	Appended, never keyed: a scan is one provider's answers to one set of authored
	queries, so two scans are two measurements rather than a correction of one.
	:meth:`scans_for` returns every scan for a goal, because the union of two providers'
	hits is what the research phase draws on.
	"""

	def transcript_for(self, goal_id: str) -> Transcript | None:
		"""The most recent *usable* transcript for one goal, if any (FR-168).

		Usable rather than merely latest: a later attempt that failed must not displace an
		earlier one that worked, because the goal statement came from the earlier one and
		the record explaining it would otherwise vanish.
		"""
		matching = [t for t in self.transcripts if t.goal_id == goal_id and t.is_usable]
		return matching[-1] if matching else None

	def attested_answer_ids(self) -> frozenset[str]:
		"""Every answer a person has attested (FR-173).

		A set rather than a per-answer accessor because that is how
		:func:`sofact.elicitation.assess` consumes it: the question it asks is "is *this*
		proposal attested", and a membership test is the whole of the answer.
		"""
		return frozenset(a.answer_id for a in self.attestations)

	@property
	def landscape(self) -> CompetitiveLandscape | None:
		"""The operative competitive scan, or ``None`` if none was recorded (FR-169)."""
		return self.landscapes[-1] if self.landscapes else None

	def exceeds_for(self, requirement_id: str) -> tuple[ExceedsClaim, ...]:
		"""Every exceedance declared against one requirement, oldest first (FR-170).

		All of them rather than the latest, unlike :meth:`gate_cost`: a requirement may
		exceed two different rivals on two different capabilities, so these are separate
		claims rather than revisions of one.
		"""
		return tuple(e for e in self.exceeds if requirement_id in e.clause_ids)

	@property
	def product_spec(self) -> ProductSpecificationDocument | None:
		"""The operative rendered specification, or ``None`` (FR-171)."""
		return self.product_specs[-1] if self.product_specs else None

	@property
	def driver_run(self) -> DriverRun | None:
		"""The most recent driver invocation, or ``None`` (FR-172)."""
		return self.driver_runs[-1] if self.driver_runs else None

	@property
	def notification(self) -> Notification | None:
		"""The most recent notification attempt, or ``None`` (FR-172).

		Most recent and not most recent *delivered*, deliberately: a run whose last
		notification failed is a run whose operator was not told, and returning the last
		one that worked would report the opposite.
		"""
		return self.notifications[-1] if self.notifications else None

	def scans_for(self, goal_id: str) -> tuple[SearchScan, ...]:
		"""Every search scan recorded for one goal, oldest first (FR-174).

		All of them, not the latest: two scans are two providers' answers to the same
		authored queries, and the union of their hits is what the research phase can
		draw on. Returning the last would silently discard the first provider's results.
		"""
		return tuple(s for s in self.scans if s.goal_id == goal_id)

	@property
	def scan(self) -> SearchScan | None:
		"""The most recent search scan, or ``None`` (FR-174)."""
		return self.scans[-1] if self.scans else None

	def latest_oracle_audit(self, contract_id: str) -> OracleAuditReport | None:
		"""The most recent audit of one contract's oracles, if any was rendered (FR-107).

		Keyed by contract rather than returned as a single latest, because two contracts can
		be live at once — a re-contracted goal — and an audit of one says nothing about the
		other's oracles.
		"""
		matching = [a for a in self.oracle_audits if a.contract_id == contract_id]
		return matching[-1] if matching else None

	def latest_adversarial_audit(self, contract_id: str) -> AdversarialAuditReport | None:
		"""The most recent adversarial pass over one contract, if any ran (FR-012–015).

		Keyed by contract for :meth:`latest_oracle_audit`'s reason: an exploit is only
		actionable against the exact oracle set it defeated, and a pass over a re-contracted
		goal says nothing about the other contract's oracles.
		"""
		matching = [a for a in self.adversarial_audits if a.contract_id == contract_id]
		return matching[-1] if matching else None

	def latest_authorship_check(self) -> AuthorshipCheck | None:
		"""The most recent authorship check, if one ran (FR-053, FR-055, FR-134).

		**Not keyed by contract**, unlike :meth:`latest_oracle_audit` and
		:meth:`latest_adversarial_audit`, and the difference is the subject rather than an
		oversight: those two measure an oracle set, which belongs to one contract, while
		this measures the package's own import graph. Two contracts in one project share one
		tree, so a per-contract key would duplicate one measurement and imply the two could
		differ.
		"""
		return self.authorship_checks[-1] if self.authorship_checks else None

	def latest_escape_override(self, lane: ModuleClass) -> EscapeOverride | None:
		"""The most recent override of one lane's escape budget, if any (FR-023).

		Latest per lane, the rule :meth:`gate_cost` states: two overrides of one lane are a
		decision and a revision of it rather than two decisions, and only the current one is
		in force. The history stays in the log, which is what makes "logged and attributed"
		checkable after the fact.
		"""
		matching = [o for o in self.escape_overrides if o.lane is lane]
		return matching[-1] if matching else None

	def escapes_for(self, report_id: str) -> tuple[EscapeEvent, ...]:
		"""Every escape recorded against one deployed change (FR-021).

		FR-021's "tracked forward through deploy" is this lookup: an escape names a report,
		and a report's escapes are the events reality filed against it.
		"""
		return tuple(e for e in self.escapes if e.report_id == report_id)

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

	def review_for(self, dispatch_id: str) -> DiffReview | None:
		"""The most recent review of one dispatch's diff, if any (§20.3 item 3).

		Keyed by dispatch rather than by step, because a step can be dispatched more
		than once and each dispatch seals its own commit — keying by step would collapse
		two reviewable diffs into one and understate the per-diff total.
		"""
		matching = [r for r in self.reviews if r.dispatch_id == dispatch_id]
		return matching[-1] if matching else None

	@property
	def latest_reviews(self) -> tuple[DiffReview, ...]:
		"""One review per reviewed dispatch, the most recent (§20.3 item 3).

		The reader every per-diff aggregate goes through, because ``reviews`` is
		appended and never keyed: summing the rows would count a diff reviewed twice as
		two diffs, which inflates the denominator of the very comparison §1.4's claim
		rests on.
		"""
		seen: dict[str, DiffReview] = {}
		for review in self.reviews:
			seen[review.dispatch_id] = review
		return tuple(seen.values())

	@property
	def reviewed_minutes(self) -> float | None:
		"""Total human-minutes spent reviewing sealed diffs (§20.3 item 3).

		``None`` when no diff has been reviewed, which is a different statement from
		zero — the same three-state shape :attr:`total_human_minutes` draws, and for the
		same reason: a factory reporting 0 here would be reporting that its diffs were
		free to read.
		"""
		latest = self.latest_reviews
		if not latest:
			return None
		return sum(r.human_minutes for r in latest)

	@property
	def mean_diff_rework(self) -> float | None:
		"""The mean share of each reviewed diff returned to the producer (§20.3 item 3).

		A mean rather than a sum because a fraction of a diff does not add across diffs,
		and kept separate from :attr:`DeliveryReport.rework_fraction` because the
		denominators differ: a gate's fraction is of a *slice*, a diff's is of a *diff*.
		Pooling them would average two different quantities.
		"""
		latest = self.latest_reviews
		if not latest:
			return None
		return sum(r.rework_fraction for r in latest) / len(latest)

	@property
	def sealed_dispatches(self) -> tuple[DispatchRecord, ...]:
		"""The dispatches that sealed a commit — the diffs a human could have read.

		**One definition, because two would drift.** The coverage denominator and the
		delivery report's ``sealed_dispatches`` count are the same set, and a
		comprehension repeated at each site is two answers to one question that agree
		only until one of them is edited.

		``sealed_commit is None`` covers two facts that ``head_commit`` distinguishes: a
		session that changed nothing, and a session whose producer committed its own
		work. For *this* question they are one fact — SoFact sealed no diff, so there is
		nothing a review could attach to — and the consequence is an accepted limit
		rather than a defect: a producer that commits its own work is unreviewable
		through ``sofact review``, because the alternative is letting an operator
		hand-type a commit sha and attach a number to a diff that may have moved.
		"""
		return tuple(
			d
			for d in self.dispatches
			if d.checkout is not None and d.checkout.sealed_commit is not None
		)

	@property
	def review_coverage(self) -> tuple[int, int] | None:
		"""How many sealed diffs were reviewed, and how many sealed one (§20.3 item 3).

		**The number that keeps the per-diff mean honest.** §1.4's claim wants human
		attention per module to be small, so a mean taken over only the diffs somebody
		chose to review flatters it — 3 reviewed of 40 sealed would report a tidy
		per-diff cost while 37 diffs were read by nobody. The mean is a fact about the
		reviewed subset; this pair is what says so, and the two travel together.

		``None`` when no dispatch sealed a commit, which is not ``(0, 0)``: no diff
		existed to review, and a zero pair would read as a project that reviewed nothing
		when it is a project that produced nothing to review (NFR-024).
		"""
		sealed = {d.id for d in self.sealed_dispatches}
		if not sealed:
			return None
		reviewed = {r.dispatch_id for r in self.latest_reviews}
		return (len(sealed & reviewed), len(sealed))

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

	def answer(self, answer_id: str) -> ElicitationAnswer | None:
		"""Look up one answer by id (FR-173).

		Needed because an attestation names an answer id and the operator attests from
		the CLI, where the answer was printed in an earlier process. Looking it up here
		rather than filtering in the service keeps the "which answer is this" question
		answered in one place.
		"""
		return next((a for a in self.answers if a.id == answer_id), None)

	def latest_contract(self, goal_id: str) -> Contract | None:
		"""Most recent contract for a goal, if one exists."""
		matching = [c for c in self.contracts if c.goal_id == goal_id]
		return matching[-1] if matching else None

	def contract(self, contract_id: str) -> Contract | None:
		"""Look up a contract by id, returning its **latest revision**.

		The latest rather than the first, because a contract id is stable across
		revisions: FR-096 makes a contract change a return to P4, and a return that
		issued a new id would orphan the specification and the decomposition that bind
		to it — so a revision keeps the id and raises ``version``. A lookup that
		returned the first row would then hand every caller the superseded oracles while
		:meth:`latest_contract` handed them the current ones, and the two disagreeing is
		exactly the drift FR-139 exists to catch.
		"""
		matching = [c for c in self.contracts if c.id == contract_id]
		return matching[-1] if matching else None

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

	def origin_plan(self, contract_id: str) -> GoalPlan | None:
		"""The first plan compiled from a contract — the one repairs are filed under.

		Distinct from :meth:`latest_plan`, and the distinction is load-bearing rather than
		cosmetic: a repair authors a *new plan revision* for each attempt, so the latest
		plan is the tail of the revision chain while every :class:`RepairAttempt` carries
		the id of the plan the loop was entered with. Asking "what did this contract's
		build cost" of the latest plan therefore returns the revision, whose id appears on
		no repair row, and the honest-looking answer is an empty total. The plan that owns
		the attempts is the first one.
		"""
		matching = [p for p in self.plans if p.contract_id == contract_id]
		return matching[0] if matching else None

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
