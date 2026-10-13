"""P8 — delivery: the report FR-118 asks for, and the handover FR-121 asks for.

§11 states five requirements. Three of them are artefacts SoFact can derive from the
log, and this module derives them:

* **FR-117** — a delivery report carrying the traceability chain from intent clause to
  deployed component. The chain is three hops and the log holds all three: clause to
  requirement (P2), requirement to module (P3), module to the step that built it (P5).
  :func:`chain` walks it and *draws the gaps* rather than stopping at the first missing
  hop, because a chain printed only where it is whole reads as a complete trace.
* **FR-118** — the report's five statements. Four are derived here and the fifth,
  FR-086's, is a constant on the type: the factory's only permitted statement about the
  value hypothesis is that it was declared, so the sentence is not a field a caller can
  write.
* **FR-121** — the Mode M handover. The lanes are §13's, retained from v0.1; the oracles
  a lane inherits are the contract's, referenced by clause rather than copied.

**FR-119** and **FR-120** are not derived here and are not claimed here. FR-119's deploy
gate is a human act — :class:`~sofact.views.DeliveryGate` refuses to be satisfied without
a named approver — and FR-120's machine-usable surface is a property of the *delivered
platform*, which SoFact does not write (ADR-0004 delegates the coding loop). Both are
reported as unimplemented on the report rather than passed by default.

The two artefacts FR-117 requires that SoFact cannot produce are named as missing with a
reason rather than omitted: a deployable artifact needs a packaging decision no ADR makes
(ADR-0005 refuses to assume a container runtime), and infrastructure-as-code is for a
target environment the operator names at deploy time. A report that carried only the
runbook and the report itself would read as a delivery with two artefacts, which is not
the same statement as a delivery missing two.

The two it *can* produce — ``RUNBOOK.md`` and ``DELIVERY.md`` — are rendered by
:mod:`sofact.writing`, which this module does not import: the report says whether they are
present and :meth:`~sofact.service.FactoryService.render_delivery` writes them. Keeping the
dependency one-way is what lets a report be rendered from the log alone, with no delivery
root and nothing written (ADR-0044).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Final

from sofact._uuid7 import uuid7str
from sofact.escape import ceilings_from
from sofact.views import (
	EVOLVABILITY_DEBT,
	MODE_G_CEILING,
	MODE_M_CEILING,
	MODULE_CLASS_CEILING,
	TOPOLOGY_ISOLATION,
	TOPOLOGY_MODIFIER,
	UNPRODUCIBLE,
	UNPRODUCIBLE_KINDS,
	AutonomyLevel,
	Contract,
	Decomposition,
	DeliveryArtifact,
	DeliveryArtifactKind,
	DeliveryReport,
	DeploymentTopology,
	EnvelopeActuals,
	EscapeReport,
	GateCheck,
	GateCost,
	GoalPlan,
	Handover,
	InheritedOracle,
	MaintenanceLane,
	ModuleClass,
	Specification,
	TraceLink,
	UnverifiedClause,
	VerdictOutcome,
	VerifiedClause,
	now,
	topology_ceiling,
	topology_refusal,
)

__all__ = [
	"DELIVERY_ARTIFACT_PATHS",
	"LANE_ORACLE_KEYWORDS",
	"UNPRODUCIBLE",
	"artifact",
	"ceiling",
	"chain",
	"handover",
	"module_autonomy",
	"refused_by_topology",
	"report",
	"topology_statement",
	"verified_and_unverified",
]

DELIVERY_ARTIFACT_PATHS: Final[dict[DeliveryArtifactKind, str]] = {
	DeliveryArtifactKind.RUNBOOK: "RUNBOOK.md",
	DeliveryArtifactKind.REPORT: "DELIVERY.md",
}
"""Where the two artefacts SoFact writes land, relative to the delivery root.

The other two kinds are absent from this mapping on purpose: an absent entry is what
makes :func:`report` record them as missing rather than as present at a path nothing
wrote. A table that named a path for every kind would produce a report claiming four
artefacts the moment someone added a key.
"""


def artifact(kind: DeliveryArtifactKind, root: Path | None) -> DeliveryArtifact:
	"""One FR-117 artefact, present when a file for it exists under ``root``.

	Presence is a filesystem fact and nothing else. A caller that could *declare* an
	artefact present would make the report's most load-bearing field an assertion, which
	is the failure FR-112 already refuses one phase earlier by diffing a declared surface
	against a built one.
	"""
	relative = DELIVERY_ARTIFACT_PATHS.get(kind)
	if relative is None:
		return DeliveryArtifact(kind=kind, present=False, missing_because=UNPRODUCIBLE[kind])
	if root is None:
		return DeliveryArtifact(
			kind=kind,
			present=False,
			missing_because=(
				"no delivery root was named, so nothing was written. A report is rendered "
				"from the log alone and does not write files; the delivery root is where "
				"the artefacts it names would be found"
			),
		)
	if not (root / relative).is_file():
		return DeliveryArtifact(
			kind=kind,
			present=False,
			missing_because=f"nothing was written at {relative} under the delivery root",
		)
	return DeliveryArtifact(kind=kind, present=True, path=relative)


def chain(
	contract: Contract,
	decomposition: Decomposition | None,
	plan: GoalPlan | None,
	*,
	requirement_for_clause: Mapping[str, str],
) -> tuple[TraceLink, ...]:
	"""The traceability chain from intent clause to deployed component (FR-117).

	One link per clause in the contract, and the chain is walked to the end for every one
	of them. A link whose hop is missing carries ``None`` at that hop, so
	:attr:`~sofact.views.TraceLink.is_whole` can count the gaps — a walk that stopped at
	the first missing hop would return a shorter chain, and the report could not tell that
	from a contract with fewer clauses.

	The three hops are three declarations and no measurement. Clause to requirement is
	P2's ``Requirement.clause_ids``, passed in because the requirement ids are minted by
	:func:`~sofact.specification.specify` rather than derived here; clause to module is
	P3's ``Module.clause_ids``; and module to step is P5's ``GoalStep.clause_ids`` read
	through :meth:`~sofact.views.Decomposition.module_for_clauses`.

	A hop is ``None`` where its phase produced nothing, which is the state of a project
	delivered without a specification or a plan. The chain reports it rather than
	refusing, because a report whose whole purpose is to state what is not there is the
	last place to raise.
	"""
	module_for_clause: dict[str, str] = {}
	if decomposition is not None:
		for module in decomposition.modules:
			for clause_id in module.clause_ids:
				module_for_clause.setdefault(clause_id, module.name)

	# The first step whose clause cover a single module owns. FR-136 forbids one session
	# per module, so several steps can share one; the earliest is what built it, and
	# "earliest" is the plan's ordinal order rather than the dispatches' arrival order.
	step_for_module: dict[str, int] = {}
	if decomposition is not None and plan is not None:
		for step in plan.steps:
			module = decomposition.module_for_clauses(step.clause_ids)
			if module is not None:
				step_for_module.setdefault(module.name, step.ordinal)

	links: list[TraceLink] = []
	for clause in contract.clauses:
		module = module_for_clause.get(clause.id)
		links.append(
			TraceLink(
				clause_id=clause.id,
				statement=clause.statement,
				requirement_id=requirement_for_clause.get(clause.id),
				module=module,
				step_ordinal=step_for_module.get(module) if module is not None else None,
			)
		)
	return tuple(links)


def verified_and_unverified(
	contract: Contract,
	verdicts: Mapping[str, VerdictOutcome],
) -> tuple[tuple[VerifiedClause, ...], tuple[UnverifiedClause, ...]]:
	"""FR-118's first two statements, split by the verdict each clause carries.

	A clause is *verified* only on ``SATISFIED``. ``INSUFFICIENT`` and ``VIOLATED`` are
	both unverified — the second is worse, not better — and the reason says which, because
	"the oracle ran and could not decide" and "the oracle was never run" need different
	repairs and FR-118 asks for one list.
	"""
	verified: list[VerifiedClause] = []
	unverified: list[UnverifiedClause] = []
	for clause in contract.clauses:
		outcome = verdicts.get(clause.id)
		if outcome is VerdictOutcome.SATISFIED:
			verified.append(
				VerifiedClause(
					clause_id=clause.id,
					statement=clause.statement,
					oracle_class=clause.oracle.oracle_class,
					rank=clause.oracle.rank,
				)
			)
			continue
		if outcome is None:
			because = (
				"no verdict was ever rendered for this clause. Its oracle is "
				+ ("executable" if clause.oracle.is_executable else "prose")
				+ (
					", so the build never ran it (FR-108 ground-truth debt)"
					if not clause.oracle.is_executable
					else ", so a verification run would decide it"
				)
			)
		elif outcome is VerdictOutcome.INSUFFICIENT:
			because = (
				"the oracle ran and could not decide: the evidence it produced does not "
				"settle the clause. A stronger oracle is needed, not another run (FR-105)"
			)
		else:
			because = (
				"the oracle ran and the clause was violated. This is a build defect rather "
				"than ground-truth debt (FR-114 scopes the repair to the modules it names)"
			)
		unverified.append(
			UnverifiedClause(
				clause_id=clause.id,
				statement=clause.statement,
				outcome=outcome,
				because=because,
			)
		)
	return tuple(verified), tuple(unverified)


def topology_statement(
	topology: DeploymentTopology,
	*,
	configured: bool,
) -> str:
	"""The topology, its isolation and its modifier, as one sentence (FR-030).

	FR-030 asks for three things reported together — "the active topology, its isolation
	guarantees, and its ceiling modifier" — and this is the one place they are joined, so
	a report, a gate check and the rendered document cannot state two of the three
	differently. A modifier reported without its isolation is a number to trust rather
	than a fact to check, which is R2's failure.

	``configured`` is separate from the topology because "this deployment is T1" and
	"nobody declared a topology, so T1's degraded ceiling is being used" are different
	facts about the world (FR-042). The second is the one an operator needs to see: it is
	the difference between a factory that chose the dev configuration and one that never
	said where it was running.
	"""
	modifier = TOPOLOGY_MODIFIER[topology]
	sign = f"{modifier:+d}" if modifier else "0"
	return f"{topology.value} ({TOPOLOGY_ISOLATION[topology]}), ceiling modifier {sign}" + (
		"" if configured else " — **not declared**, so the degraded default is in use"
	)


def refused_by_topology(
	contract: Contract,
	decomposition: Decomposition | None,
	*,
	topology: DeploymentTopology,
) -> tuple[str, ...]:
	"""Module classes this topology refuses outright, with the reason (FR-031).

	FR-031 refuses rather than downgrades, and it refuses a *specific* thing: a lane that
	would be L4 in T2 running at T1. So the test is per module class — the classes whose
	:data:`~sofact.views.MODULE_CLASS_CEILING` is L4 are exactly the ones T2 admits at L4
	— and the refusal names the class and the level.

	Scoped to the decomposition because that is where module classes exist. A contract
	with no decomposition has no class to refuse, and reporting a refusal for a class
	nobody proposed would refuse a build that has not been decomposed yet; the contract's
	own ceiling is still lowered by the modifier through :func:`module_autonomy`, so
	nothing escapes the topology by being undecomposed.

	The returned reasons are empty at T2/T3/T4 by construction (their modifiers are zero,
	so :func:`~sofact.views.topology_refusal` returns ``None`` for every level), which is
	why this is a tuple rather than an ``assert``: a deployment that refuses nothing must
	be able to say it refused nothing.
	"""
	assert contract.clauses, "cannot refuse a topology for a contract with no clauses"
	if decomposition is None:
		return ()
	reasons: list[str] = []
	for module in decomposition.modules:
		level = MODULE_CLASS_CEILING[module.module_class]
		refusal = topology_refusal(level, topology)
		if refusal is not None:
			reasons.append(f"{module.name} ({module.module_class.value}): {refusal}")
	return tuple(reasons)


def module_autonomy(
	contract: Contract,
	decomposition: Decomposition | None,
	*,
	topology: DeploymentTopology = DeploymentTopology.T1,
	lane_ceilings: Mapping[ModuleClass, AutonomyLevel] | None = None,
) -> AutonomyLevel:
	"""The autonomy the *modules* sustain: the lower of the two measured ceilings (FR-122).

	The contract's ceiling is ``ceiling_for_rank`` on the weakest oracle (FR-007); the
	decomposition's is :data:`~sofact.views.MODULE_CLASS_CEILING` on each module's class
	(FR-125/FR-126). The lower governs, so a G7 module — auth, secrets, payments or PII,
	where FR-126 makes the work human-authored — lowers a delivery the contract alone
	would have raised.

	This is the number FR-123 calls the *internal* one. It is not the delivery's, and the
	difference between the two is what :func:`ceiling` computes and the report states.

	``topology`` applies §5.4's modifier to the result (FR-019, FR-124), and it is
	applied *here* rather than inside :func:`ceiling` because §5.4's modifier is a
	statement about what the hardware isolates, which is what bounds the modules' blast
	radius. The default is T1 — the degraded configuration — so a caller that has not
	said where the factory is running gets the lower ceiling rather than the product
	target's (FR-042).
	"""
	assert contract.clauses, "cannot compute an autonomy for a contract with no clauses"
	measured = contract.ceiling
	if decomposition is not None:
		for module in decomposition.modules:
			granted = MODULE_CLASS_CEILING[module.module_class]
			if lane_ceilings is not None:
				# FR-023's reduction composes with §14's class ceiling rather than
				# replacing it: a G7 lane is L1 and a reduction may lower it to L0, never
				# raise it. `min` rather than assignment is what keeps a caller that hands
				# in a *raised* ceiling from raising a lane the class ceiling forbids.
				granted = AutonomyLevel(
					min(granted, lane_ceilings.get(module.module_class, granted))
				)
			measured = AutonomyLevel(min(measured, granted))
	return topology_ceiling(measured, topology)


def ceiling(
	contract: Contract,
	decomposition: Decomposition | None,
	*,
	topology: DeploymentTopology = DeploymentTopology.T1,
) -> AutonomyLevel:
	"""The autonomy the *delivery* may claim: the module number, capped at L2 (FR-123).

	FR-123's argument is that P2, P3 and P8 are human gates, so a Mode G delivery is L2
	end-to-end however strong its oracles are. Applying the cap here — and unconditionally,
	including when no decomposition exists — is the whole of the requirement's force: a
	report that could exceed L2 because a phase artefact was missing would be a cap that
	fails open on missing input.

	The cap is not a claim about the modules. :func:`module_autonomy` is reported beside
	this number, because "individual modules may run at L4 internally; the delivery is L2"
	is a *distinction* and one number cannot express it.

	``topology`` reaches this only through :func:`module_autonomy`. The modifier is not
	applied twice: FR-123's L2 is already at or below every topology's number, so lowering
	the delivery again would report T1 as L1 for a reason §5.4 does not state, and the
	report would attribute to the deployment a reduction the cap had already made.
	"""
	return AutonomyLevel(
		min(module_autonomy(contract, decomposition, topology=topology), MODE_G_CEILING)
	)


def _lane_oracles(contract: Contract) -> tuple[InheritedOracle, ...]:
	"""The contract's oracles, in the form a maintenance lane inherits (FR-121)."""
	return tuple(
		InheritedOracle(
			clause_id=clause.id,
			statement=clause.statement,
			command_hint=clause.oracle.command_hint,
			rank=clause.oracle.rank,
		)
		for clause in contract.clauses
	)


LANE_ORACLE_KEYWORDS: Final[tuple[tuple[str, str, AutonomyLevel, tuple[str, ...]], ...]] = (
	(
		"L01",
		"dependency and version bumps on an existing repository",
		AutonomyLevel.L4,
		("depend", "version", "upgrade", "pin", "lock"),
	),
	(
		"L04",
		"test repair against an existing suite",
		AutonomyLevel.L4,
		("test", "assert", "suite", "coverage"),
	),
	(
		"L08",
		"schema and migration work",
		AutonomyLevel.L3,
		("migration", "schema", "column", "table", "index"),
	),
	(
		"L10",
		"documentation and configuration maintenance",
		AutonomyLevel.L3,
		("document", "readme", "config", "setting"),
	),
	(
		"L11",
		"adversarial audit service",
		AutonomyLevel.L3,
		("security", "audit", "vulnerab", "exploit", "threat"),
	),
)
"""§13's lanes, matched to a contract clause by the clause's own words.

The same shape as :func:`sofact.decomposition.classify` one phase earlier, and for the
same reason: the lane is *proposed* from what the operator wrote, and the proposal is a
starting point rather than a claim. A lane no clause matches is absent from the handover,
which is a fact about the delivered system rather than a failure — §13's lanes are
maintenance work, and a platform whose contract states no maintenance obligation has
none to hand over.

L11 is the adversarial audit service and is included because §13 retains it; L12
(self-maintenance) is not, because a lane that maintains SoFact is not a lane for the
delivered system.
"""


def handover(
	contract: Contract,
	*,
	system: str,
	entry_point: str,
) -> Handover:
	"""FR-121's Mode M handover, derived from the contract the build was verified against.

	Every lane carries *every* contract clause's oracle rather than a keyword-matched
	subset. A maintenance run does not know in advance which clause its change touches, so
	a lane handed only the oracles that mention its own keywords would be missing the ones
	its regression needs — which is the failure mode a maintenance mode exists to avoid.
	:data:`LANE_ORACLE_KEYWORDS` decides which *lanes* exist; the oracles are the whole
	contract's.

	Every lane's ceiling is clamped to :data:`~sofact.views.MODE_M_CEILING` (FR-158).
	§13 gives L01 and L04 an L4, and those are *Mode M* levels — the level at which the
	maintenance lane's own work would run — which is a different claim from the level at
	which the delivery may be maintained. FR-158(a) refuses the second for as long as no
	oracle observes change cost, so the clamp is applied here and the lane type refuses an
	unclamped one, which is what keeps §13's table and FR-158's cap from being two
	statements of one number.
	"""
	oracles = _lane_oracles(contract)
	lowered = [(clause.statement.lower(), clause.id) for clause in contract.clauses]
	lanes: list[MaintenanceLane] = []
	for lane, description, ceiling, keywords in LANE_ORACLE_KEYWORDS:
		matching = {cid for statement, cid in lowered if any(k in statement for k in keywords)}
		if not matching:
			continue
		lanes.append(
			MaintenanceLane(
				lane=lane,
				description=description,
				inherited_oracles=tuple(o for o in oracles if o.clause_id in matching),
				ceiling=AutonomyLevel(min(ceiling, MODE_M_CEILING)),
			)
		)
	if not lanes:
		# A handover with no lane is refused by the type, and the honest answer for a
		# contract that states no maintenance obligation is one lane carrying the whole
		# contract: the delivered system can still be maintained, it just has no lane of
		# §13's to be maintained *under*. Inventing a lane to satisfy the type would put
		# a §13 identifier on work §13 does not describe.
		lanes.append(
			MaintenanceLane(
				lane="L00",
				description=(
					"unclassified maintenance: no clause in the contract matches a §13 lane, "
					"so the whole oracle set is handed over without a lane to file it under"
				),
				inherited_oracles=oracles,
				ceiling=AutonomyLevel(min(contract.ceiling, MODE_M_CEILING)),
			)
		)
	return Handover(system=system, entry_point=entry_point, lanes=tuple(lanes))


def report(
	contract: Contract,
	*,
	goal_id: str,
	plan: GoalPlan,
	decomposition: Decomposition | None,
	specification: Specification | None,
	verdicts: Mapping[str, VerdictOutcome],
	envelope_actuals: EnvelopeActuals | None,
	gate_costs: tuple[GateCost, ...] = (),
	root: Path | None = None,
	system: str,
	entry_point: str,
	report_id: str | None = None,
	rendered_at: datetime | None = None,
	topology: DeploymentTopology = DeploymentTopology.T1,
	topology_configured: bool = False,
	topology_override: str | None = None,
	escapes: EscapeReport | None = None,
) -> DeliveryReport:
	"""Render FR-118's report from the log (FR-117, FR-118, FR-121).

	Deterministic and model-free: every input is a record the factory already holds, so
	a report is reproducible from the log — which is what makes it evidence a deploy gate
	can be asked to approve rather than a summary someone wrote.

	``root`` is the delivery root the artefacts are looked for under, and it defaults to
	``None``, which makes the two SoFact writes absent with that reason. A report is
	rendered *from the log*; writing the artefacts is a separate act, so the default is
	the honest state of a report nobody has written files for yet.

	``report_id`` and ``rendered_at`` pin the report's identity, and a caller that is
	writing the artefacts supplies them. The two documents quote the report id — that is
	what lets a deploy gate tie a runbook to the checks it approved (FR-119) — so a writer
	has to know the id *before* the report exists. Rendering twice to discover it would be
	rendering the same facts twice, and the second render is the one a reader would trust.

	``topology`` is the deployment this delivery was rendered under (FR-030, FR-124). It
	defaults to T1 — the degraded configuration — so a caller that has not said where the
	factory runs reports the lower ceiling rather than the product target's, and
	``topology_configured`` says which of the two happened (FR-042).

	``topology_override`` is the operator's explicit acceptance of a topology refusal
	(FR-031). It is a *string naming who accepted it* rather than a boolean, because the
	requirement's own word is "recorded": an override with no name attached is
	indistinguishable from the silent downgrade the requirement forbids, and the whole
	point of the refusal is that the difference between "lowered by the deployment" and
	"lowered by weak oracles" survives into the log.
	"""
	assert contract.clauses, "cannot report a delivery for a contract with no clauses"
	requirement_for_clause: dict[str, str] = {}
	if specification is not None:
		for requirement in specification.requirements:
			for clause_id in requirement.clause_ids:
				requirement_for_clause.setdefault(clause_id, requirement.id)
	links = chain(contract, decomposition, plan, requirement_for_clause=requirement_for_clause)
	verified, unverified = verified_and_unverified(contract, verdicts)
	handed = handover(contract, system=system, entry_point=entry_point)
	# FR-023's reduction reaches the autonomy computation as a pre-computed mapping, so
	# `module_autonomy` stays pure and the escape arithmetic lives in `sofact.escape` alone.
	# `ceilings_from` returns `None` when no measurement was taken, which is a different
	# statement from a measurement that reduced nothing — the check below says which.
	if escapes is not None and escapes.rendered_at != rendered_at:
		# One instant for one report. The escape table is a statement *about* this delivery,
		# so a table stamped with the moment it was folded would date a delivery's own
		# evidence to a different second than the delivery — and `rendered_at` is what pins
		# the report's identity for FR-117's versioning.
		escapes = escapes.model_copy(update={"rendered_at": rendered_at})
	lane_ceilings = ceilings_from(escapes)
	modules_autonomy = module_autonomy(
		contract, decomposition, topology=topology, lane_ceilings=lane_ceilings
	)
	delivered_autonomy = ceiling(contract, decomposition, topology=topology)
	refused = refused_by_topology(contract, decomposition, topology=topology)

	artifacts = tuple(artifact(kind, root) for kind in DeliveryArtifactKind)
	# Scoped, and the scoping is the whole of this line's content: two of FR-117's four
	# kinds are decisions SoFact has deliberately not made (ADR-0005, FR-124), so a check
	# over all four could never pass. A gate that cannot pass is one an operator learns
	# to bypass, and the bypass turns off the part of it that does matter.
	owed = tuple(a for a in artifacts if not a.present and a.kind not in UNPRODUCIBLE_KINDS)
	undecided = tuple(a for a in artifacts if a.kind in UNPRODUCIBLE_KINDS)
	broken = tuple(link for link in links if not link.is_whole)
	executable = sum(1 for o in handed.inherited_oracles if o.is_executable)

	checks: list[GateCheck] = [
		GateCheck(
			name="traceability_chain",
			passed=not broken,
			detail=(
				f"every one of {len(links)} clause(s) traces to a module and the step that built it"
				if not broken
				else f"{len(broken)} of {len(links)} clause(s) have a gap in the chain "
				"(FR-117): a clause with no module was dropped by the decomposition, and "
				"one with no step was never dispatched"
			),
		),
		GateCheck(
			name="delivery_artifacts",
			passed=not owed,
			detail=(
				f"the {len(artifacts) - len(undecided)} artefact(s) FR-117 names that the "
				"factory owes exist under the delivery root"
				if not owed
				else f"{len(owed)} artefact(s) the factory owes are missing: "
				+ "; ".join(f"{a.kind.value} ({a.missing_because})" for a in owed)
			),
		),
		GateCheck(
			name="undecided_artifacts_stated",
			passed=True,
			detail=(
				f"{len(undecided)} of FR-117's four artefact(s) are decisions this gate is "
				"where to take rather than omissions: "
				+ "; ".join(f"{a.kind.value} ({a.missing_because})" for a in undecided)
				+ ". This check reports rather than fails for the reason the artefact check "
				"is scoped: neither is something a passing check could produce (ADR-0005, "
				"FR-124)"
			),
		),
		GateCheck(
			name="unverified_clauses_stated",
			passed=True,
			detail=(
				f"{len(unverified)} clause(s) are unverified and stated as such, "
				f"{sum(1 for u in unverified if u.is_ground_truth_debt)} of them ground-truth "
				"debt (FR-108). This check reports rather than fails: FR-118 asks the report "
				"to *state* the debt, and a delivery with debt is a delivery whose limits "
				"are known — refusing here would pay a producer for hiding one"
			),
		),
		GateCheck(
			name="value_not_certified",
			passed=True,
			detail=(
				"the report states that requirements were verified and value was not "
				"(FR-086). The sentence is a constant on the type, so no code path can "
				"produce a report that omits it or claims otherwise"
			),
		),
		GateCheck(
			name="maintainability_not_verified",
			passed=True,
			detail=(
				"the report states that maintainability was not verified and why (FR-158): "
				f"evolvability debt is {EVOLVABILITY_DEBT:g} for every module by construction "
				"— the value the requirement names, not a measurement failure — because no "
				"oracle in O1-O8 observes change cost, and Mode M is capped at "
				f"{MODE_M_CEILING.name} while Mode G's {MODE_G_CEILING.name} is unaffected. "
				"The two are reported as two numbers (FR-158(b)). The sentence is a constant "
				"on the type, so no code path can phrase the claim away. This check reports "
				"rather than fails: FR-158 makes the debt structural, and refusing a delivery "
				"for a debt every delivery carries would refuse all of them"
			),
		),
		GateCheck(
			name="maintenance_handover",
			passed=bool(handed.lanes),
			detail=(
				f"{len(handed.lanes)} maintenance lane(s) handed over, inheriting "
				f"{executable} executable oracle(s) of {len(handed.inherited_oracles)}. "
				+ (
					f"{len(handed.unmaintainable)} inherit an oracle with no command, so a "
					"maintenance run cannot execute them (FR-082)"
					if handed.unmaintainable
					else "every inherited oracle names a command"
				)
			),
		),
		GateCheck(
			name="machine_surface_not_verified",
			passed=True,
			detail=(
				"FR-120 asks that the *delivered* system be machine-usable as well as "
				"human-usable — a documented, stable API surface. **It is not verified "
				"here.** No oracle in O1-O8 observes whether an artefact has a usable "
				"interface, so a check would be one that cannot pass. The factory's own "
				"surface is another matter and is built (`sofact api <operation>`, "
				"ADR-0048); the delivered system's is a producer obligation this report "
				"names rather than verifies. This check reports rather than fails for "
				"FR-158's reason one requirement along: refusing a delivery for a property "
				"no oracle observes would refuse all of them"
			),
		),
		GateCheck(
			name="envelope_actuals_reported",
			passed=True,
			detail=(
				"the actuals against the §1.3 envelope are reported (FR-118, NFR-025): "
				+ (
					f"{len(envelope_actuals.measurements)} dimension(s), "
					f"{len(envelope_actuals.unmeasured)} unmeasured"
					if envelope_actuals is not None
					else "no envelope is configured for this deployment, so nothing was "
					"measured against one. This is not the same statement as every "
					"dimension being within bounds"
				)
			),
		),
		GateCheck(
			name="deploy_is_human",
			passed=True,
			detail=(
				"FR-119's deploy gate is human and permanent: no code path in SoFact "
				"deploys. This report is what the gate presents, and a deploy is recorded "
				"only against a gate a named person passed"
			),
		),
		GateCheck(
			name="gate_cost_reported",
			passed=True,
			detail=(
				"FR-160's measurement is reported beside the producer's budget: "
				+ (
					f"{len(gate_costs)} gate(s) measured, "
					f"{sum(c.human_minutes for c in gate_costs):g} human-minute(s) total, "
					"mean rework fraction "
					f"{sum(c.rework_fraction for c in gate_costs) / len(gate_costs):.3f} "
					"(the share of each gated slice returned to the producer). "
					"Per gate: "
					+ ", ".join(
						f"{c.gate.value} {c.human_minutes:g}min/"
						f"{c.rework_fraction:.2f} by {c.recorded_by}"
						for c in gate_costs
					)
					if gate_costs
					else "no gate has recorded what it cost, so the reviewer's budget is "
					"unmeasured rather than zero. FR-160's argument is §20.2's: if review "
					"is the binding constraint once implementation is agent-driven, a "
					"factory that measures the producer's budget but not the reviewer's "
					"is optimising its cheapest step. `sofact gate --cost` records one"
				)
			),
		),
		GateCheck(
			name="autonomy_capped_for_mode_g",
			passed=delivered_autonomy <= MODE_G_CEILING,
			detail=(
				f"the delivery is {delivered_autonomy.name} and the modules sustain "
				f"{modules_autonomy.name} (FR-122). "
				+ (
					f"The {MODE_G_CEILING.name} cap is FR-123's: P2, P3 and P8 are human "
					"gates, so a Mode G delivery is L2 end-to-end however strong its "
					"oracles are. "
					if modules_autonomy > delivered_autonomy
					else ""
				)
				+ "The two numbers are reported apart because FR-123 asks for the "
				"distinction, not the lower one: 'autonomous module construction inside "
				"a human-validated architecture'"
			),
		),
		GateCheck(
			name="topology_ceiling_applied",
			passed=True,
			detail=(
				f"this delivery was rendered under {topology_statement(topology, configured=topology_configured)}. "
				+ (
					f"The modules' number is {modules_autonomy.name} *after* the modifier, "
					"and the delivery's is "
					f"{delivered_autonomy.name} because FR-123's cap is at or below every "
					"topology's number (FR-019, FR-124)"
					if TOPOLOGY_MODIFIER[topology]
					else "§5.4's modifier for this topology is zero, so the modules' number "
					f"({modules_autonomy.name}) is the one the oracles and module classes "
					"compute (FR-019, FR-124)"
				)
			),
		),
		GateCheck(
			name="topology_refuses_l4_at_a_degraded_deployment",
			passed=not refused or topology_override is not None,
			detail=(
				f"{len(refused)} module class(es) would be L4 in T2 and are refused at "
				f"{topology.value} (FR-031): "
				+ "; ".join(refused)
				+ (
					f". An explicit operator override was recorded by {topology_override}, "
					"which is what FR-031 requires instead of a silent downgrade — so these "
					"classes run here by a named decision rather than by a quieter number"
					if topology_override is not None
					else ". Record an explicit operator override to run them here, or move "
					"the deployment. The refusal above states the *fact*; the remedy is here "
					"because this check is where the override is read, and a sentence telling "
					"an operator to record one would otherwise print over a refusal that was "
					"already accepted"
				)
				if refused
				else f"no module class this decomposition proposes would be L4 in T2, so "
				f"{topology.value} refuses nothing (FR-031)"
			),
		),
		GateCheck(
			name="escape_ceiling_applied",
			# A *reporting* check, `topology_ceiling_applied`'s shape, and the reason it does
			# not fail is a property of FR-023 rather than a concession. A check that failed
			# on `over_budget` would refuse the deploy of the fix: the rate is
			# escapes/deployments, so the only way it returns to budget is by deploying
			# changes that hold, and a gate that blocks those makes the recovery FR-023 is
			# trying to cause unreachable. Requiring an override to deploy the fix would not
			# help — it would make recording an override the routine first step of every
			# recovery, which is how a gate teaches its operators to bypass it.
			#
			# The reduction is nonetheless real and binding: it reaches `module_autonomy`
			# through `lane_ceilings`, so a delivery in a reduced lane *reports* the lower
			# number rather than claiming one FR-023 has withdrawn. FR-119 then makes the
			# deploy a human decision over that report, which is where the weighing belongs.
			passed=True,
			detail=(
				"no escape measurement was taken for this delivery, so FR-023 is not in "
				"force here and no lane is reduced. This is not the same statement as every "
				"lane being within budget: it is the absence of a measurement, and a "
				"deployment that wants FR-023 declares its budgets (SOFACT_ESCAPE_BUDGET)"
				if escapes is None
				else (
					"no lane exceeds its declared escape budget (FR-022, FR-023): "
					+ ", ".join(
						f"{lane.lane.value} {lane.rate:.3f} <= {lane.budget.maximum_rate:.3f}"
						for lane in escapes.lanes
						if lane.budget is not None
					)
					if not escapes.over_budget
					else f"{len(escapes.over_budget)} lane(s) exceed their declared escape "
					"budget (FR-023): "
					+ "; ".join(
						f"{lane.lane.value} escaped {lane.escapes} time(s) in "
						f"{lane.deployed_changes} deployment(s) = {lane.rate:.3f} against a "
						f"declared {lane.budget.maximum_rate:.3f}"
						+ (
							f", and a manual override was recorded by {lane.override.accepted_by}, "
							"so the reduction is lifted by a named decision rather than by a "
							"quieter number"
							if lane.override is not None
							else f", so {lane.lane.value}'s ceiling is reduced from "
							f"{lane.granted_ceiling.name} to {lane.reduced_ceiling.name} "
							"until its rate returns to budget. Record an attributed "
							"override to run it here (FR-023)"
						)
						for lane in escapes.over_budget
						if lane.budget is not None
					)
				)
			),
		),
		GateCheck(
			name="escape_budget_declared",
			passed=True,
			detail=(
				"FR-023 reduces a lane over its *declared* budget, and this deployment "
				"declared none, so no lane is reduced and the escape oracle is unarmed. "
				"§20.3 item 4 records that no escape baseline exists until there has been a "
				"deployment, so no default is invented here (NFR-024)"
				if escapes is None or not escapes.lanes
				else (
					"every measured lane has a declared escape budget (FR-023): "
					+ ", ".join(f"{lane.lane.value}" for lane in escapes.lanes)
					if not escapes.unbudgeted
					else f"{len(escapes.unbudgeted)} lane(s) were measured and have no "
					"declared budget, so FR-023 cannot reduce them: "
					+ ", ".join(lane.value for lane in escapes.unbudgeted)
					+ ". A lane with no declaration is not one whose rate exceeds it, and "
					"inventing a threshold would be the unmeasured target NFR-024 forbids"
				)
			),
		),
	]

	return DeliveryReport(
		id=report_id or uuid7str(),
		goal_id=goal_id,
		contract_id=contract.id,
		plan_id=plan.id,
		rendered_at=rendered_at or now(),
		artifacts=artifacts,
		chain=links,
		verified=verified,
		unverified=unverified,
		unvalidated_assumptions=specification.assumptions if specification is not None else (),
		envelope_actuals=envelope_actuals,
		gate_costs=gate_costs,
		autonomy=delivered_autonomy,
		module_autonomy=modules_autonomy,
		topology=topology,
		topology_configured=topology_configured,
		escapes=escapes,
		handover=handed,
		checks=tuple(checks),
	)
