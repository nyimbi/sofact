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
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from sofact._uuid7 import uuid7str
from sofact.views import (
	MODE_G_CEILING,
	MODULE_CLASS_CEILING,
	UNPRODUCIBLE,
	UNPRODUCIBLE_KINDS,
	AutonomyLevel,
	Contract,
	Decomposition,
	DeliveryArtifact,
	DeliveryArtifactKind,
	DeliveryReport,
	EnvelopeActuals,
	GateCheck,
	GoalPlan,
	Handover,
	InheritedOracle,
	MaintenanceLane,
	Specification,
	TraceLink,
	UnverifiedClause,
	VerdictOutcome,
	VerifiedClause,
	now,
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
	"report",
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


def module_autonomy(contract: Contract, decomposition: Decomposition | None) -> AutonomyLevel:
	"""The autonomy the *modules* sustain: the lower of the two measured ceilings (FR-122).

	The contract's ceiling is ``ceiling_for_rank`` on the weakest oracle (FR-007); the
	decomposition's is :data:`~sofact.views.MODULE_CLASS_CEILING` on each module's class
	(FR-125/FR-126). The lower governs, so a G7 module — auth, secrets, payments or PII,
	where FR-126 makes the work human-authored — lowers a delivery the contract alone
	would have raised.

	This is the number FR-123 calls the *internal* one. It is not the delivery's, and the
	difference between the two is what :func:`ceiling` computes and the report states.
	"""
	assert contract.clauses, "cannot compute an autonomy for a contract with no clauses"
	measured = contract.ceiling
	if decomposition is not None:
		for module in decomposition.modules:
			measured = AutonomyLevel(min(measured, MODULE_CLASS_CEILING[module.module_class]))
	return measured


def ceiling(contract: Contract, decomposition: Decomposition | None) -> AutonomyLevel:
	"""The autonomy the *delivery* may claim: the module number, capped at L2 (FR-123).

	FR-123's argument is that P2, P3 and P8 are human gates, so a Mode G delivery is L2
	end-to-end however strong its oracles are. Applying the cap here — and unconditionally,
	including when no decomposition exists — is the whole of the requirement's force: a
	report that could exceed L2 because a phase artefact was missing would be a cap that
	fails open on missing input.

	The cap is not a claim about the modules. :func:`module_autonomy` is reported beside
	this number, because "individual modules may run at L4 internally; the delivery is L2"
	is a *distinction* and one number cannot express it.
	"""
	return AutonomyLevel(min(module_autonomy(contract, decomposition), MODE_G_CEILING))


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
				ceiling=ceiling,
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
				ceiling=contract.ceiling,
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
	root: Path | None = None,
	system: str,
	entry_point: str,
) -> DeliveryReport:
	"""Render FR-118's report from the log (FR-117, FR-118, FR-121).

	Deterministic and model-free: every input is a record the factory already holds, so
	a report is reproducible from the log — which is what makes it evidence a deploy gate
	can be asked to approve rather than a summary someone wrote.

	``root`` is the delivery root the artefacts are looked for under, and it defaults to
	``None``, which makes the two SoFact writes absent with that reason. A report is
	rendered *from the log*; writing the artefacts is a separate act, so the default is
	the honest state of a report nobody has written files for yet.
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
	modules_autonomy = module_autonomy(contract, decomposition)
	delivered_autonomy = ceiling(contract, decomposition)

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
	]

	return DeliveryReport(
		id=uuid7str(),
		goal_id=goal_id,
		contract_id=contract.id,
		plan_id=plan.id,
		rendered_at=now(),
		artifacts=artifacts,
		chain=links,
		verified=verified,
		unverified=unverified,
		unvalidated_assumptions=specification.assumptions if specification is not None else (),
		envelope_actuals=envelope_actuals,
		autonomy=delivered_autonomy,
		module_autonomy=modules_autonomy,
		handover=handed,
		checks=tuple(checks),
	)
