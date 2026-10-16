"""FR-024–FR-035 — the routing function, and the θ gate it is named for.

§5.1 states the whole of admission control in three lines:

```text
admissible(lane) = intent_derivable
                 ∧ oracle_exists
                 ∧ blast_radius_bounded(deployment)

ceiling(lane)    = min( f(oracle_strength),      # §4.3
                        g(blast_bound),          # §5.2
                        h(deployment_isolation)  # §5.4
                      )

level(lane)      = min( ceiling(lane), floor(concerns) )
```

Every one of those terms is a fact this factory already holds and nothing had ever
computed together. The class ceiling (:data:`~sofact.views.MODULE_CLASS_CEILING`), the
topology modifier (:func:`~sofact.views.topology_ceiling`), FR-023's escape reduction
(:func:`~sofact.views.lane_ceiling`), the declared budget
(:class:`~sofact.views.ModuleBudget`), the measured boundary
(:class:`~sofact.views.DeploymentBoundary`), the oracle ranks and FR-105's measured
strength were each built, each tested, and each read by something that was not this
function. The roadmap row said so in six words: *"§5.1's ``admissible(lane)`` and
``ceiling(lane)`` remain uncomputed."*

**The term that was genuinely missing is θ, and building it is what moves
:data:`~sofact.views.THETA_GATE_BUILT`.** FR-009's table maps a *measured* oracle
strength to a level, and until this module nothing compared
:attr:`~sofact.mutation.MutationReport.measured_strength` against anything: FR-105 says a
module below θ_lo "must be reported as unbuildable-at-autonomy and escalated, not built
anyway", and the number was recorded, rendered, and gating nothing.

**Three readings this module refuses, and each is a way the function could lie.**

1. **An unmeasured strength is not a low one.** :func:`oracle_strength_ceiling` returns
   ``None`` when no clause of the lane has a measurement that survived
   :mod:`sofact.mutation`'s floor, and ``None`` is not ``L1``. Rounding it to ``L1``
   would report a lane nobody measured as a lane measured badly — and it would make the
   gate *pass* on the absence of evidence, which is NFR-024's forbidden target one level
   up. :attr:`~sofact.views.RouteDecision.undecided` names the terms that are ``None`` so
   a reader can tell "decided low" from "not decided".
2. **A concerns floor may only lower, and no concern means no floor.** FR-024's own
   sentence: "the implementation must reject a configuration where a concerns floor is
   used to justify a *higher* level." §5.1's third line is a ``min``, so a declared floor
   above the built-in one is refused by name rather than applied — see
   :func:`load_concerns_floors`. The other direction matters as much:
   :data:`~sofact.views.CONCERNS_FLOOR` is sparse by design (G7 alone), so a lane §14
   names no concern for has *no* floor, and :attr:`RouteDecision.concerns_floor` is
   ``None`` rather than ``L0``. A floor is what a concern imposes; a lane without one is
   not a lane nothing may touch, and defaulting the absence to ``L0`` would collapse every
   lane in the ladder to zero.
3. **Exceeding a blast bound fails the lane; it does not lower it.** FR-026's words are
   "fails the lane and escalates — a large diff is unverifiable regardless of oracle
   results". A reduction would say the lane is still admissible at a lower level, which
   is the opposite of "regardless of oracle results". FR-027's permission half is the
   other direction and is *not* an admission term: it caps the level below L4
   (:func:`permission_ceiling`), because FR-027's own sentence is scoped there and
   refusing at admission would refuse the T1 deployment FR-124 says still runs.

**Where ``g(blast_bound)`` went, stated rather than dropped.** §5.1 renders it as a ``min``
term of ``ceiling``, and §5.2 supplies no table mapping a blast bound to a level — the only
computable fact is whether the bound *held*. FR-026 puts that fact in admissibility ("a lane
must declare a maximum changed-file count and a maximum diff size. Exceeding either fails
the lane and escalates") and §5.4's T4 note agrees, calling the blast bound what "unlocks L4
for lanes whose blast bound previously failed" — an admissibility change, not a level
change. So the bound is checked as the third conjunct of :func:`admissible` and there is no
``g`` returning a level, because inventing one would be this module writing policy the spec
does not state. A lane that exceeds its bound is *refused*, which is strictly stronger than
the reduction a fabricated ``g`` would have applied.

**FR-027 is the neighbouring requirement and it is not the same fact**, which this module
got wrong on the first pass and now states: FR-026 is a *declared number* whose breach fails
the lane, and FR-027 is a *level* gate — "Autonomy L4 requires that the lane's file scope be
declared and enforced by permission". Enforcing FR-027 at admission makes every lane at an
unmeasured deployment inadmissible, and FR-124 requires the opposite. It is applied as
:func:`permission_ceiling` on the computed ceiling.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from sofact.views import (
	CONCERNS_FLOOR,
	DEFAULT_THETA,
	MODULE_CLASS_CEILING,
	AutonomyLevel,
	Clause,
	Contract,
	DeploymentBoundary,
	DeploymentTopology,
	ElicitationDimension,
	Module,
	ModuleClass,
	Requirement,
	RouteDecision,
	RouteTerm,
	RoutingRefusal,
	Specification,
	SpecificationDraft,
	ThetaThresholds,
	topology_ceiling,
)

__all__ = [
	"CONCERNS_FLOORS_ENV",
	"ROUTING_REQUIREMENTS",
	"THETA_THRESHOLDS_ENV",
	"ConcernsFloor",
	"admissible",
	"load_concerns_floors",
	"load_theta_thresholds",
	"oracle_strength_ceiling",
	"permission_ceiling",
	"route",
	"route_statement",
]

CONCERNS_FLOORS_ENV: Final = "SOFACT_CONCERNS_FLOORS"
"""Where a deployment declares its concerns floors (FR-024, NFR-018).

Beside ``SOFACT_ESCAPE_BUDGET`` and ``SOFACT_MODEL_TIERS``: the same seam, the same file
shape, and the same refusal naming the variable when it cannot be read. NFR-018's
concerns are a deployment's — a health-data processor and a static-site generator do not
share a floor — while *the rule that a floor may only lower* is SoFact's, which is why
the table is configuration and the ``min`` is not.
"""

THETA_THRESHOLDS_ENV: Final = "SOFACT_THETA_THRESHOLDS"
"""Where a deployment declares its calibrated θ_hi and θ_lo (FR-010).

FR-010 is explicit that the built-in numbers are "**(assumed)** and must be calibrated
against measured escape data (§12.2) before they are trusted", and that they "must be
configuration, calibrated per language and per repository, and must be recorded with the
change". A file rather than two constants, so a calibration is a thing a deployment
declares and a report can name rather than a number someone edits in the source.
"""

ROUTING_REQUIREMENTS: Final[tuple[str, ...]] = ("FR-024", "FR-025", "FR-026", "FR-027")
"""The requirements one routing decision can carry out.

FR-024 (the concerns floor and the refusal to let one raise), FR-025 (a mutation is a
branch, checked by the git seam rather than here), FR-026 (the declared blast bound and
what exceeding it does) and FR-027 (L4 requires the file scope declared *and enforced*).
FR-028's egress denial and FR-029's "a lane must not affect the factory's own
configuration" are :mod:`sofact.boundary`'s measurements — the boundary this module reads
is the one that probe took, and naming them here would claim a check this function did not
run. FR-030–FR-035 are reporting, topology and staging, and the topology half is applied
rather than measured.
"""


@dataclass(frozen=True, slots=True)
class ConcernsFloor:
	"""One deployment's declared concerns floor for one lane class (FR-024, NFR-018).

	``reason`` is required for :class:`~sofact.harness.HarnessSpec`'s reason one level
	over: NFR-018 is about a *risk* — "auth, payments, PII, migrations, or production
	configuration" — and a floor with no reason attached is a number the next reader
	deletes when it blocks something.
	"""

	lane: ModuleClass
	level: AutonomyLevel
	reason: str
	declared_by: str

	def __post_init__(self) -> None:
		if not self.reason.strip():
			raise RoutingRefusal(
				f"the {self.lane.value} concerns floor gives no reason; NFR-018 names a "
				"risk class, and a floor with no reason is one the next reader deletes"
			)
		if not self.declared_by.strip():
			raise RoutingRefusal(
				f"the {self.lane.value} concerns floor names nobody; a floor is a "
				"deployment's judgement and an unattributed one cannot be revisited"
			)


def _str_keyed(value: object) -> bool:
	"""True when ``value`` is a JSON object with string keys."""
	if not isinstance(value, dict):
		return False
	obj = cast("Mapping[object, object]", value)
	return all(isinstance(key, str) for key in obj)


def load_concerns_floors(path: Path) -> tuple[ConcernsFloor, ...]:
	"""Read a deployment's concerns floors from a JSON file (FR-024, NFR-018).

	Two shapes, matching every other loader in this tree: a bare object of lanes, or the
	same object under ``concerns_floors``.

	**FR-024's refusal lives here**, and it is the reason this function exists rather than a
	dict lookup. A declared floor *above* the built-in one for its lane is refused by name:
	§5.1's third line is ``min(ceiling(lane), floor(concerns))``, so a floor can only lower
	a level, and a declaration that raised one would be the "concerns floor used to justify
	a *higher* level" the requirement forbids. The built-in table is the comparison, so the
	refusal needs :data:`~sofact.views.CONCERNS_FLOOR` to exist even where it restates a
	class ceiling.

	A lane with no built-in floor has no floor to exceed, so any declared level is a
	*lowering* by construction — the refusal applies only where the deployment is trying to
	raise one.
	"""
	target = path
	try:
		text = target.read_text(encoding="utf-8")
	except OSError as exc:
		raise RoutingRefusal(f"cannot read {CONCERNS_FLOORS_ENV} {target}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise RoutingRefusal(f"{target}: not valid JSON: {exc}") from exc
	if not _str_keyed(raw):
		raise RoutingRefusal(f"{target}: expected a JSON object of lanes")
	document = cast("dict[str, Any]", raw)
	body: object = document["concerns_floors"] if set(document) == {"concerns_floors"} else document
	if not _str_keyed(body):
		raise RoutingRefusal(f"{target}: expected an object of lanes under 'concerns_floors'")
	declared = cast("dict[str, Any]", body)
	if not declared:
		raise RoutingRefusal(
			f"{target}: no lanes; a file that declares none would read as configured while "
			"flooring nothing"
		)

	floors: list[ConcernsFloor] = []
	for name, payload in declared.items():
		try:
			lane = ModuleClass(name)
		except ValueError as exc:
			known = ", ".join(c.value for c in ModuleClass)
			raise RoutingRefusal(
				f"{target}: {name!r} is not a §14 lane class; known: {known}"
			) from exc
		if not _str_keyed(payload):
			raise RoutingRefusal(f"{target}: lane {name!r} must be an object")
		fields = cast("dict[str, Any]", payload)
		unknown = sorted(set(fields) - {"level", "reason", "declared_by"})
		if unknown:
			raise RoutingRefusal(
				f"{target}: lane {name!r} names {unknown}, which is not a floor field; a "
				"misspelled field would otherwise be ignored and the floor would read as "
				"declared while flooring nothing"
			)
		if "level" not in fields:
			raise RoutingRefusal(
				f"{target}: lane {name!r} declares no level, so it declares no floor"
			)
		try:
			level = AutonomyLevel(int(fields["level"]))
		except (TypeError, ValueError) as exc:
			raise RoutingRefusal(
				f"{target}: lane {name!r} declares level {fields['level']!r}, which is not "
				"an autonomy level 0-5"
			) from exc
		built_in = CONCERNS_FLOOR.get(lane)
		if built_in is not None and level > built_in:
			raise RoutingRefusal(
				f"{target}: lane {name!r} declares a concerns floor of {level.name}, above "
				f"the built-in {built_in.name}. §5.1 renders the floor as "
				"`min(ceiling(lane), floor(concerns))`, so a concern can only *lower* a "
				"level — and FR-024 forbids exactly this: 'a concerns floor is used to "
				"justify a higher level'"
			)
		floors.append(
			ConcernsFloor(
				lane=lane,
				level=level,
				reason=str(fields.get("reason", "")),
				declared_by=str(fields.get("declared_by", f"{target}")),
			)
		)
	return tuple(floors)


def load_theta_thresholds(path: Path) -> ThetaThresholds:
	"""Read a calibrated θ pair from a JSON file (FR-010).

	Two shapes again: the object bare, or under ``theta``. A file that names only one of
	the two thresholds is refused rather than completed from the defaults, because a
	calibration is a *pair* — θ_hi from a different source than θ_lo would make the two
	rows of FR-009's table describe two different populations.
	"""
	target = path
	try:
		text = target.read_text(encoding="utf-8")
	except OSError as exc:
		raise RoutingRefusal(f"cannot read {THETA_THRESHOLDS_ENV} {target}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise RoutingRefusal(f"{target}: not valid JSON: {exc}") from exc
	if not _str_keyed(raw):
		raise RoutingRefusal(f"{target}: expected a JSON object")
	document = cast("dict[str, Any]", raw)
	body: object = document["theta"] if set(document) == {"theta"} else document
	if not _str_keyed(body):
		raise RoutingRefusal(f"{target}: expected an object under 'theta'")
	fields = cast("dict[str, Any]", body)
	unknown = sorted(set(fields) - {"hi", "lo", "calibrated_by"})
	if unknown:
		raise RoutingRefusal(f"{target}: unknown field(s) {unknown}")
	missing = sorted({"hi", "lo"} - set(fields))
	if missing:
		raise RoutingRefusal(
			f"{target}: declares no {missing}; FR-010 calibrates the *pair*, and one "
			"threshold from the defaults beside one from a measurement would make "
			"FR-009's two rows describe two different populations"
		)
	who = fields.get("calibrated_by")
	if who is not None and not isinstance(who, str):
		raise RoutingRefusal(f"{target}: 'calibrated_by' must be a string naming who calibrated")
	return ThetaThresholds(
		hi=float(fields["hi"]),
		lo=float(fields["lo"]),
		calibrated_by=who,
	)


def oracle_strength_ceiling(
	strength: float | None,
	*,
	thresholds: ThetaThresholds = DEFAULT_THETA,
) -> AutonomyLevel | None:
	"""FR-009's table: what a *measured* oracle strength admits, or ``None``.

	The three rows as stated, and the gap between L3 and L1 is the spec's rather than a
	rounding: θ at or above θ_hi admits L4, θ at or above θ_lo admits L3, and anything
	below θ_lo is "L1 — oracle is informational only". There is no L2 row, so this does
	not interpolate one.

	**``None`` for an unmeasured strength, and that is the whole of NFR-024 here.** A lane
	nobody measured has not scored badly; it has not scored. Returning ``L1`` would report
	it as a lane measured at the bottom of the table, which is a claim about a measurement
	that does not exist — and it would make FR-105's escalation fire on the absence of
	evidence rather than on evidence.
	"""
	if strength is None:
		return None
	if strength >= thresholds.hi:
		return AutonomyLevel.L4
	if strength >= thresholds.lo:
		return AutonomyLevel.L3
	return AutonomyLevel.L1


def permission_ceiling(
	level: AutonomyLevel,
	*,
	boundary: DeploymentBoundary | None,
) -> AutonomyLevel:
	"""``level`` capped at L3 unless the file scope is enforced by permission (FR-027).

	FR-027's own sentence is "**Autonomy L4 requires** that the lane's file scope be
	**declared and enforced by permission**, not merely intended." It is scoped to L4, and
	that scope is the whole content: a lane below L4 is one a human still owns — §5.3 puts
	the outcome gate in human hands at L1 through L3 — so an unenforced file scope is a
	weaker containment, not an inadmissible lane. Applying it at admission instead would
	refuse every lane at a deployment with no measured boundary, which is exactly what
	FR-124 says must still run: "T1 (dev instance, **no isolation boundary**) runs Mode G at
	−1 level".

	This was got wrong here first — the conjunct was written into :func:`admissible` — and
	the correction is a *narrowing*, not a relaxation. A lane that cannot be confined is
	still capped below the level at which nobody checks its work; what changes is that it is
	lowered rather than refused, which is FR-031's own distinction between a silent
	downgrade and a refusal. FR-031's refusal stays where it is, in
	:func:`~sofact.views.topology_refusal`, and fires on the topology rather than on the
	permission half.

	``boundary is None`` (no probe ran) and ``enforced=False`` (a probe found nothing) both
	cap at L3, and the two are kept distinct in the sentence :func:`admissible` no longer
	writes: the remedy for the first is to measure, and for the second to fix what was
	measured. A boundary that held is the only thing that lifts the cap, and
	:attr:`~sofact.views.DeploymentBoundary.writes_confined` is deliberately *not* the
	predicate — ``enforced`` is the credit for both halves (ADR-0060), and a scope whose
	writes are confined while its holdouts stay legible is not a scope enforced by
	permission.
	"""
	if level < AutonomyLevel.L4:
		return level
	return level if boundary is not None and boundary.enforced else AutonomyLevel.L3


def admissible(
	module: Module,
	*,
	clauses: Mapping[str, Clause],
	requirements: Mapping[str, Requirement],
	stems: Mapping[str, ElicitationDimension],
	within_budget: bool | None,
) -> tuple[RouteTerm, ...]:
	"""§5.1's three conjuncts, each as a named term rather than one boolean (FR-024–FR-027).

	The three are checked separately because they have three different remedies — re-elicit
	the dimension, assign an executable oracle, or bring the lane inside its declared budget
	— and a single ``False`` would send an operator looking for the wrong one. That is the
	same argument :class:`~sofact.views.GateCheck` makes about naming *which* precondition
	failed.

	``within_budget`` is ``None`` when the lane's sealed files could not be measured, and
	that is not ``False``: a bound nobody measured is unmeasured rather than exceeded, which
	is :func:`~sofact.integration.check_module_budget`'s own distinction.

	**The third conjunct is FR-026's declared bound and not FR-027's permission.** That
	placement was got wrong here first and the correction is worth stating, because the two
	requirements sit in one section and are not the same fact. FR-026 is "exceeding either
	fails the lane and escalates" — an admission fact about a number the lane declared.
	FR-027 opens "**Autonomy L4 requires** that the lane's file scope be declared and
	enforced by permission", so it gates *the level*, and putting it here instead would make
	every lane at a deployment with no measured boundary inadmissible — which FR-124
	forbids in as many words: "T1 (dev instance, **no isolation boundary**) runs Mode G at −1
	level". A requirement scoped to L4 enforced at admission refuses the deployment the spec
	says still runs. It is applied in :func:`route`, where the level is computed.
	"""
	terms: list[RouteTerm] = []

	# FR-076/FR-173: a lane's intent is derivable when every clause it exists to satisfy
	# traces back to a requirement that traces back to a stem whose elicitation dimension
	# was answered. A clause whose dimension nobody answered is a clause whose *intent* is
	# a guess, which §6.1 refuses: guessing at intent is not something this factory does.
	underivable: list[str] = []
	for clause_id in module.clause_ids:
		clause = clauses.get(clause_id)
		if clause is None:
			underivable.append(f"{clause_id}: no clause on the contract")
			continue
		reaching = [r for r in requirements.values() if clause_id in r.clause_ids]
		if not reaching:
			underivable.append(f"{clause.statement[:40]!r}: no requirement traces to it")
			continue
		unanswered = [
			clause_id
			for requirement in reaching
			if not any(cid in stems for cid in requirement.clause_ids)
		]
		if unanswered:
			underivable.append(
				f"{clause.statement[:40]!r}: its requirement traces to no answered "
				"elicitation dimension"
			)
	terms.append(
		RouteTerm(
			name="intent_derivable",
			held=not underivable,
			detail=(
				f"{len(module.clause_ids)} clause(s) trace to an answered dimension"
				if not underivable
				else "underivable: " + "; ".join(underivable)
			),
			requirement="FR-076",
		)
	)

	# FR-108/FR-103: "oracle_exists" is executability and not the class, because
	# `OracleDeclaration.is_executable`'s own docstring draws the line — an oracle with no
	# command "is not a weaker oracle, it is an *intention*", and §5.1's term is about
	# existence rather than strength. Strength is `f`'s job one function down.
	prose = [
		c.statement[:40]
		for c in (clauses.get(cid) for cid in module.clause_ids)
		if c is not None and not c.oracle.is_executable
	]
	terms.append(
		RouteTerm(
			name="oracle_exists",
			held=not prose,
			detail=(
				"every clause names an executable oracle"
				if not prose
				else f"{len(prose)} clause(s) name no command, so their oracle is an "
				"intention rather than a check: " + "; ".join(prose)
			),
			requirement="FR-108",
		)
	)

	# FR-026: "Exceeding either fails the lane and escalates". The sentence names the budget
	# rather than the boundary, because the budget is what the lane declared and what P7
	# measured — §5.2's own subject. FR-027's permission half is not here; see the docstring.
	if within_budget is None:
		bound = "the lane's sealed files were not read, so its declared budget is unmeasured"
	elif not within_budget:
		bound = "the lane exceeded the blast bound its own budget declared (FR-026)"
	else:
		bound = f"inside the declared budget of {module.budget.max_files} file(s) and {module.budget.max_loc} line(s)"
	terms.append(
		RouteTerm(
			name="blast_radius_bounded",
			held=within_budget is True,
			detail=bound,
			requirement="FR-026",
		)
	)
	return tuple(terms)


def route(
	module: Module,
	*,
	contract: Contract,
	specification: Specification | None = None,
	draft: SpecificationDraft | None = None,
	strengths: Mapping[str, float] | None = None,
	topology: DeploymentTopology = DeploymentTopology.T1,
	boundary: DeploymentBoundary | None = None,
	within_budget: bool | None = None,
	floors: Sequence[ConcernsFloor] = (),
	thresholds: ThetaThresholds = DEFAULT_THETA,
) -> RouteDecision:
	"""§5.1's three lines, for one lane, as one decision (FR-024–FR-035).

	The lane arrives as the :class:`~sofact.views.Module` itself rather than as an id to be
	found in a decomposition: the class ceiling comes from the module (§14 makes the class
	the lane), the clause set comes from the module, and FR-026's budget is on the module —
	so a decomposition parameter would be an argument this function opens and never reads.
	Callers holding the approved decomposition pass the module they already selected.

	``strengths`` is FR-105's measurement keyed by clause id, and the lane's number is the
	**weakest** clause's — :attr:`~sofact.views.Contract.weakest_oracle_rank`'s rule, and
	the same reason: a lane is only as verifiable as its least verifiable part. A clause
	absent from the mapping makes the lane's strength ``None`` rather than contributing
	nothing, so one unmeasured clause makes the lane undecided. That is the strict
	direction and it is the honest one: averaging over the clauses that *were* measured
	would report a lane strength over a subset nobody chose.

	``floors`` are the deployment's declarations, already validated by
	:func:`load_concerns_floors`, which is where FR-024's raise-refusal lives. A lane with
	neither a declaration nor a built-in entry has no floor at all
	(:attr:`~sofact.views.RouteDecision.concerns_floor` is ``None``) and its level is its
	ceiling, because §5.1's third line has no second operand where no concern applies.
	"""
	clauses = {c.id: c for c in contract.clauses}
	requirements = {} if specification is None else {r.id: r for r in specification.requirements}
	# A stem id *is* a clause id (`Contract.from_draft`), so the map from clause to the
	# dimension it was derived from is the draft's stems read by id.
	stems = {} if draft is None else {s.id: s.derived_from for s in draft.stems}

	terms = admissible(
		module,
		clauses=clauses,
		requirements=requirements,
		stems=stems,
		within_budget=within_budget,
	)
	refused = tuple(t for t in terms if not t.held)

	# §5.1 line two. `h` is §5.4's modifier, applied through `topology_ceiling` so the
	# clamp at L0 and the assertion that no modifier raises a level stay in one place.
	measured = [
		strengths[cid] for cid in module.clause_ids if strengths is not None and cid in strengths
	]
	strength = None if len(measured) != len(module.clause_ids) else min(measured)
	strength_term = oracle_strength_ceiling(strength, thresholds=thresholds)

	# §5.1 line three, and the `min` is FR-024's whole force. A declared floor for a lane
	# with no built-in one is a lowering by construction; where one exists the loader has
	# already refused a declaration above it, so this `min` cannot be the thing that
	# rejects a raising floor -- it is the arithmetic that makes one harmless if the loader
	# is ever bypassed by a caller building `ConcernsFloor` objects directly.
	#
	# The default is `None` and not `L0`: where no concern applies the `min` has no second
	# operand, so the level *is* the ceiling. Defaulting to L0 would invent a floor of zero
	# for every lane §14 names no concern for, which reads a floor -- what a concern
	# imposes -- backwards, and collapses the whole ladder to L0.
	declared_floor: AutonomyLevel | None = max(
		(f.level for f in floors if f.lane is module.module_class),
		default=CONCERNS_FLOOR.get(module.module_class),
	)
	class_ceiling = MODULE_CLASS_CEILING[module.module_class]
	ceiling: AutonomyLevel | None = None
	if strength_term is not None and not refused:
		ceiling = AutonomyLevel(min(int(strength_term), int(class_ceiling)))
		ceiling = topology_ceiling(ceiling, topology, boundary=boundary)
		ceiling = permission_ceiling(ceiling, boundary=boundary)
	level = (
		None
		if ceiling is None
		else ceiling
		if declared_floor is None
		else AutonomyLevel(min(int(ceiling), int(declared_floor)))
	)

	undecided: list[str] = []
	if strength is None:
		undecided.append(
			"f(oracle_strength): no measured strength survived FR-105's floor for every "
			"clause of this lane, so FR-009's table cannot be read"
		)
	if refused:
		undecided.append(
			"admissible(lane): " + "; ".join(f"{t.name} ({t.requirement})" for t in refused)
		)

	return RouteDecision(
		module=module.name,
		module_class=module.module_class,
		terms=terms,
		strength=strength,
		strength_ceiling=strength_term,
		class_ceiling=class_ceiling,
		concerns_floor=declared_floor,
		ceiling=ceiling,
		level=level,
		topology=topology,
		thresholds=thresholds,
		undecided=tuple(undecided),
	)


def route_statement(decision: RouteDecision) -> str:
	"""One lane's decision in a sentence, with the term that bound it (FR-030).

	FR-030's requirement is that the topology and its modifier "must be reported in every
	oracle report and attached to every change", and the same argument applies to the level
	itself: a number with no account of which term produced it is a number to trust. So the
	sentence names the binding term — the weakest of the three lines — and the two that did
	not bind.
	"""
	if decision.level is None:
		return f"{decision.module} ({decision.module_class.value}): no level — " + "; ".join(
			decision.undecided
		)
	# A `None` floor is not a floor of zero and cannot be the binding term: where no concern
	# applies, `level == ceiling` by construction, so the sentence falls through to whichever
	# ceiling term bound it. Testing `floor < ceiling` alone would have made every
	# concern-free lane report itself bound by a floor that does not exist.
	binding = (
		"the concerns floor"
		if decision.concerns_floor is not None
		and decision.concerns_floor < (decision.ceiling or AutonomyLevel.L0)
		else f"f(oracle_strength) at {decision.strength:.2f}"
		if decision.strength is not None and decision.strength_ceiling == decision.ceiling
		else f"§14's class ceiling for {decision.module_class.value}"
	)
	return (
		f"{decision.module} ({decision.module_class.value}): {decision.level.name} — "
		f"bound by {binding}, at {decision.topology.value}"
	)
