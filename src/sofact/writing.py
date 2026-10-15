"""Render FR-117's two owed artefacts from the report (FR-117, FR-118, FR-121).

§11 requires a delivery to contain four things, and ADR-0040 scoped SoFact's artefact
check to the two the *factory* owes: ``RUNBOOK.md`` and ``DELIVERY.md``. Until now
nothing wrote them. The check was honest about the shortfall and the consequence was
worse than a missing feature — ``sofact deliver`` could not succeed on a fresh project,
because a report over a root with nothing in it correctly fails its own artefact check.
A factory that refuses to deliver until a human has hand-written the documents it claims
to produce is not a factory.

The rendering is **deterministic and model-free**, which is what makes it admissible:
every input is a record the log already holds, so two renders of one report are
byte-identical and a diff between two deliveries is a diff between two sets of facts.
Nothing here paraphrases, summarises, or adds a sentence the report does not support.
That is the whole design constraint. A runbook written by a language model would be
plausible prose about a system nobody ran, and it would be indistinguishable from the
real thing at exactly the moment it mattered.

The runbook is **derived from the handover**, not written beside it: FR-121 makes the
maintenance lanes the next mode's input, so the operational document and the machine-
readable handover are one derivation with two renderings. Two statements of one fact
drift, and the drift would be invisible because both would read as plausible prose —
the argument ADR-0042 makes about a module's Definition of Done, one artefact along.
"""

from __future__ import annotations

from typing import Final

from sofact.views import (
	DELIVERY_REQUIREMENTS,
	TOPOLOGY_ISOLATION,
	TOPOLOGY_MODIFIER,
	V01_REVIEW_MINUTES_PER_DIFF,
	DeliveryArtifactKind,
	DeliveryReport,
	DeploymentTopology,
	EnvelopeMeasurement,
)

__all__ = [
	"DELIVERY_HEADINGS",
	"RUNBOOK_HEADINGS",
	"render_delivery_artifacts",
	"render_delivery_document",
	"render_runbook",
]

DELIVERY_HEADINGS: Final[tuple[str, ...]] = (
	"What was built",
	"The traceability chain",
	"Verified",
	"Unverified",
	"Unvalidated assumptions",
	"Envelope actuals",
	"Gate cost",
	"Debt",
	"Machine surface",
	"Autonomy",
	"Escapes",
	"Escape attribution",
	"Maintenance handover",
	"Machine checks",
)
"""The headings :func:`render_delivery_document` always writes, in order.

A constant rather than an inline sequence because the test suite asserts the rendered
document against it: a heading that went missing would take its section with it, and the
one thing FR-118 cannot tolerate is a report that reads as complete while a qualification
has quietly dropped out of it.
"""

RUNBOOK_HEADINGS: Final[tuple[str, ...]] = (
	"What this system is",
	"How to run it",
	"Maintenance lanes",
	"Verification you inherit",
	"Not covered",
)
"""The headings :func:`render_runbook` always writes, in order."""

_EMPTY: Final[str] = "_None._"
"""What a section says when it has nothing to list.

A sentence rather than an empty body: a heading with nothing under it reads as a
document that lost a section, which is the failure mode this whole module exists to
avoid. ``None`` is also the honest word — an empty list of unverified clauses is a
finding about the delivery, not a formatting accident.
"""


def _measured(measurement: EnvelopeMeasurement) -> str:
	"""One envelope dimension as a line, saying *unmeasured* where that is the case."""
	if measurement.actual is None:
		return f"- **{measurement.dimension.value}**: unmeasured. {measurement.detail}"
	return (
		f"- **{measurement.dimension.value}**: {measurement.actual:g} "
		f"(bound {measurement.bound.stated()}), "
		f"{'within' if measurement.within else 'OUTSIDE'}. {measurement.detail}"
	)


def render_delivery_document(report: DeliveryReport) -> str:
	"""``DELIVERY.md``: FR-118's five statements, as the document the gate presents.

	The document is a *rendering* of :class:`~sofact.views.DeliveryReport` and holds no
	fact the report does not. Every section is written whether or not it has content,
	because the reader is a person deciding whether to deploy and a missing section is
	the one thing they cannot notice.
	"""
	assert report.checks, "a report with no machine checks cannot be rendered"
	lines: list[str] = [
		"# Delivery report",
		"",
		f"- Report: `{report.id}`",
		f"- Rendered: {report.rendered_at.isoformat()}",
		f"- Contract: `{report.contract_id}`",
		f"- Plan: `{report.plan_id}`",
		f"- Requirements: {', '.join(DELIVERY_REQUIREMENTS)}",
		"",
		f"> {report.value_statement}",
		"",
		f"> {report.maintainability_statement}",
		"",
		"## Debt",
		"",
		"- **Ground-truth debt** (FR-108): the unverified clause(s) below, each saying "
		"whether a machine could check it.",
		f"- **Evolvability debt** (FR-158): {report.evolvability_debt:g} — every module, by "
		"construction. No oracle in O1-O8 observes change cost, so this is the correct "
		"value rather than a measurement failure, and it is reported as its own number "
		"rather than folded into the one above.",
		"",
		"## Machine surface",
		"",
		"FR-120 asks that this system be machine-usable as well as human-usable. **That is "
		"not verified here.** No oracle in O1-O8 observes whether an artefact exposes a "
		"usable interface, so a check would be one that cannot pass — and this is a "
		"producer obligation the report names rather than one the factory discharges. The "
		"factory's own surface is separate and is built: `sofact api <operation>` "
		"(ADR-0048).",
		"",
		"## What was built",
		"",
	]
	for artifact in report.artifacts:
		if artifact.present:
			lines.append(f"- **{artifact.kind.value}**: present at `{artifact.path}`")
		else:
			lines.append(f"- **{artifact.kind.value}**: absent. {artifact.missing_because}")

	whole = len(report.chain) - len(report.broken_links)
	lines += [
		"",
		"## The traceability chain",
		"",
		f"{whole} of {len(report.chain)} clause(s) trace from intent to the step that built them.",
		"",
	]
	for link in report.chain:
		lines.append(f"- {link.rendered}")

	lines += ["", "## Verified", ""]
	if report.verified:
		for clause in report.verified:
			strength = (
				f"measured {clause.measured_strength:.3f}"
				if clause.measured
				else f"declared rank {clause.rank}, not measured"
			)
			lines.append(
				f"- `{clause.clause_id}` ({clause.oracle_class.value}, {strength}): "
				f"{clause.statement}"
			)
	else:
		lines.append(_EMPTY)

	lines += ["", "## Unverified", ""]
	if report.unverified:
		for clause in report.unverified:
			outcome = clause.outcome.value if clause.outcome is not None else "no verdict"
			lines.append(f"- `{clause.clause_id}` ({outcome}): {clause.statement}")
			lines.append(f"  - because: {clause.because}")
	else:
		lines.append(_EMPTY)

	lines += ["", "## Unvalidated assumptions", ""]
	if report.unvalidated_assumptions:
		for assumption in report.unvalidated_assumptions:
			lines.append(f"- {assumption.statement}")
			lines.append(f"  - refuted by: {assumption.refuted_by}")
	else:
		lines.append(_EMPTY)

	lines += ["", "## Envelope actuals", ""]
	if report.envelope_actuals is None:
		lines.append(
			"No envelope is configured for this deployment, so nothing was measured "
			"against one. This is not the same statement as every dimension being within "
			"bounds."
		)
	else:
		for measurement in report.envelope_actuals.measurements:
			lines.append(_measured(measurement))

	lines += ["", "## Gate cost", ""]
	if report.gate_costs:
		for cost in report.gate_costs:
			lines.append(
				f"- **{cost.gate.value}**: {cost.human_minutes:g} human-minute(s), "
				f"{cost.rework_fraction:.0%} of the slice returned to the producer "
				f"(recorded by {cost.recorded_by})"
			)
		lines.append(
			f"- **Total**: {sum(c.human_minutes for c in report.gate_costs):g} "
			f"human-minute(s); mean rework fraction {report.rework_fraction:.3f}"
		)
	else:
		lines.append(
			"No gate has recorded what it cost, so the reviewer's budget is unmeasured "
			"rather than zero (FR-160)."
		)

	lines += ["", "## Diff review", ""]
	if report.diff_reviews:
		for row in report.diff_reviews:
			lines.append(
				f"- **{row.dispatch_id[:8]}** at `{row.sealed_commit[:7]}`: "
				f"{row.human_minutes:g} human-minute(s), "
				f"{row.rework_fraction:.0%} of the diff returned to the producer "
				f"(reviewed by {row.reviewed_by})"
			)
		lines.append(
			f"- **Total**: {report.reviewed_minutes:g} human-minute(s) over "
			f"{len(report.diff_reviews)} reviewed diff(s); mean "
			f"{report.mean_diff_minutes:.1f} per reviewed diff; mean rework fraction "
			f"{report.diff_rework_fraction:.3f}"
			+ (
				f". Coverage: {report.review_coverage[0]} of "
				f"{report.review_coverage[1]} sealed diff(s)"
				if report.review_coverage is not None
				else ""
			)
		)
		lines.append(
			"\n§1.4 names v0.1's review rate as roughly four units an hour — about "
			f"{V01_REVIEW_MINUTES_PER_DIFF:g} minutes a diff. The mean above is over the "
			"diffs that were reviewed, so the coverage count beside it is what says how "
			"much of the project it describes. §21 R13's comparison — gate-minutes "
			"against diff-minutes — is stated in the delivery report's "
			"`diff_review_reported` check, where both totals are printed and neither is "
			"divided by the other."
		)
	else:
		lines.append(
			"No diff review has been recorded, so the per-diff half of §20.3 item 3 is "
			"unmeasured rather than zero (§20.3 item 3)."
		)

	lines += [
		"",
		"## Autonomy",
		"",
		f"- Delivery: **{report.autonomy.name}** (FR-123 caps a Mode G delivery at L2, "
		"because P2, P3 and P8 are human gates)",
		f"- Modules: **{report.module_autonomy.name}** (FR-122) — autonomous module "
		"construction inside a human-validated architecture",
		f"- Deployment: **{report.topology.value}**, "
		f"{TOPOLOGY_ISOLATION[report.topology]} — ceiling modifier "
		f"{TOPOLOGY_MODIFIER[report.topology]:+d} (FR-019, FR-030, FR-124)"
		+ (
			""
			if report.topology_configured
			else ". **No topology was declared**, so the degraded default is in use and the "
			"numbers above are T1's (FR-042)"
		),
	]

	lines += [
		"",
		"## Escapes",
		"",
	]

	if report.escapes is None:
		lines.append(
			"No escape measurement was taken, so **FR-023 is not in force for this "
			"delivery**: this deployment declared no per-lane escape budget and no escape "
			"has been recorded. That is not the same statement as every lane being within "
			"budget, and §20.3 item 4 records why no default is invented here — until a "
			"deployment has happened, every ceiling is a hypothesis (NFR-024)."
		)
	elif not report.escapes.deployed_changes:
		lines.append(
			"No change has been deployed, so FR-022's rate has no denominator and this "
			"measurement claims nothing (FR-021)."
		)
	else:
		escapes = report.escapes
		lines.append(
			f"Escape rate per lane (FR-022) — {escapes.deployed_changes} deployed "
			f"change(s) measured:"
		)
		lines.append("")
		lines.append("| Lane | Escapes | Deployments | Rate | Budget | Ceiling |")
		lines.append("| --- | --- | --- | --- | --- | --- |")
		for lane in escapes.lanes:
			budget = f"{lane.budget.maximum_rate:.3f}" if lane.budget is not None else "undeclared"
			ceiling = lane.granted_ceiling.name
			if lane.reduced:
				ceiling = f"{lane.granted_ceiling.name} → **{lane.reduced_ceiling.name}**"
			elif lane.reduced_by_fr_023:
				# FR-023 is in force and moved nothing: the lane is already at L0, which is
				# the floor of the ladder rather than the floor of the reduction. Rendering
				# this as a plain ceiling would make it identical to a lane that was never
				# over budget — the one state an operator most needs told apart.
				ceiling = f"{ceiling} (FR-023 in force, at the ladder floor)"
			elif lane.over_budget and lane.override is not None:
				ceiling = f"{ceiling} (override: {lane.override.accepted_by})"
			lines.append(
				f"| {lane.lane.value} | {lane.escapes} | {lane.deployed_changes} | "
				f"{lane.rate:.3f} | {budget} | {ceiling} |"
			)
		if escapes.unbudgeted:
			lines.append("")
			lines.append(
				f"**{len(escapes.unbudgeted)} lane(s) were measured with no declared "
				"budget** ("
				+ ", ".join(lane.value for lane in escapes.unbudgeted)
				+ "), so FR-023 cannot reduce them. No threshold is invented: an undeclared "
				"budget is the absence of a declaration rather than a bound at zero."
			)
		if escapes.orphan_deployments:
			lines.append("")
			lines.append(
				f"{escapes.orphan_deployments} deployed report(s) reach no module, so they "
				"fall in no lane's denominator. Counted rather than dropped."
			)
		lines.append("")
		for caveat in escapes.caveats:
			lines.append(f"- {caveat}")

	lines += ["", "## Escape attribution", ""]
	if not report.attributions:
		lines.append(
			"No escape is attributed to a clause (FR-127). Either none has been recorded "
			"against this contract's changes, or the graph holds no module in the lane one "
			"was filed against — and the second is a gap in the traceability rather than a "
			"clean history."
		)
	else:
		lines.append(
			"Each recorded escape, traced back to the intent clause the change was built "
			"for (FR-127). This is a pointer for a human and not a diagnosis: every hop is "
			"a declaration, so it can say *which* clause the escaped module was built for "
			"and cannot say the clause was ambiguous. §2.3 makes the operator's reading the "
			"only ground truth there is."
		)
		lines.append("")
		lines.append("| Lane | Clause | Statement | Narrowed |")
		lines.append("| --- | --- | --- | --- |")
		for attribution in report.attributions:
			lines.append(
				f"| {attribution.lane.value} | `{attribution.clause_id}` | "
				f"{attribution.statement} | "
				f"{'yes' if attribution.narrowed else '**no — candidate set**'} |"
			)
		if not all(a.narrowed for a in report.attributions):
			lines.append("")
			lines.append(
				"A row that is not narrowed is a *candidate set*: the escape named a lane "
				"rather than a module, so it points at every clause that lane's modules "
				"cite. Recording the module (`--module`) narrows it to an answer."
			)
	if report.intent is not None and report.intent.gaps:
		lines.append("")
		lines.append(
			f"**{len(report.intent.gaps)} clause(s) the graph cannot walk.** Nothing was "
			"built for them, so no escape can ever be attributed to them — a worse finding "
			"than an escape, and one a rendered chain draws as a gap and moves past."
		)

	lines += [
		"",
		"## Maintenance handover",
		"",
		f"- System: {report.handover.system}",
		f"- Entry point: `{report.handover.entry_point}`",
		"",
	]
	for lane in report.handover.lanes:
		lines.append(f"- **{lane.lane}** ({lane.ceiling.name}): {lane.description}")
		for oracle in lane.inherited_oracles:
			command = (
				f"`{oracle.command_hint}`"
				if oracle.is_executable
				else "no command — this oracle cannot be re-run as delivered"
			)
			lines.append(f"  - `{oracle.clause_id}` (rank {oracle.rank}): {command}")

	lines += ["", "## Machine checks", ""]
	for check in report.checks:
		mark = "PASS" if check.passed else "FAIL"
		lines.append(f"- **[{mark}] {check.name}**: {check.detail}")

	lines.append("")
	rendered = "\n".join(lines)
	# The constant is load-bearing rather than decorative: a section renamed or dropped
	# by a later edit fails here instead of silently leaving the document, and the reader
	# who would notice a missing section is the one deciding whether to deploy.
	missing = [heading for heading in DELIVERY_HEADINGS if f"## {heading}" not in rendered]
	assert not missing, f"the delivery document lost section(s): {missing}"
	return rendered


def render_runbook(report: DeliveryReport) -> str:
	"""``RUNBOOK.md``: how to run the delivered system, and what maintenance inherits.

	Derived from the same report, and specifically from its handover. The two documents
	are two renderings of one derivation rather than two statements of one fact: FR-121
	makes the lanes the next mode's input, so a runbook that described the lanes
	differently from the handover would be describing a system that does not exist.
	"""
	assert report.handover.lanes, "a handover with no lanes cannot be rendered"
	executable = sum(1 for o in report.handover.inherited_oracles if o.is_executable)
	unmaintainable = len(report.handover.unmaintainable)
	lines: list[str] = [
		"# Runbook",
		"",
		f"Operational notes for **{report.handover.system}**, delivered from report `{report.id}`.",
		"",
		"## What this system is",
		"",
		f"- Entry point: `{report.handover.entry_point}`",
		f"- {len(report.handover.lanes)} maintenance lane(s), "
		f"{len(report.handover.inherited_oracles)} inherited oracle(s), "
		f"{executable} executable as delivered",
		"",
		f"> {report.value_statement}",
		"",
		f"> {report.maintainability_statement}",
		"",
		"## How to run it",
		"",
		"This factory does not run the delivered system and does not choose how it is "
		"packaged (ADR-0005). The deploy gate is where a human names the target "
		"environment; this section records what SoFact knows and no more.",
		"",
		f"**Where this was built**: {report.topology.value}, "
		f"{TOPOLOGY_ISOLATION[report.topology]} — ceiling modifier "
		f"{TOPOLOGY_MODIFIER[report.topology]:+d} (FR-019, FR-030). "
		+ (
			"This is §5.4's product target, so the ceilings reported above are the ones "
			"the delivered system may claim where it is deployed."
			if report.topology is DeploymentTopology.T2
			else "The delivered system inherits no claim about its own deployment from "
			"this: the topology is where the *factory* ran, and a system built on a dev "
			"machine can be deployed to T2 or T3."
		),
		"",
	]
	for artifact in report.artifacts:
		if artifact.present:
			lines.append(f"- **{artifact.kind.value}**: `{artifact.path}`")
		else:
			lines.append(f"- **{artifact.kind.value}**: absent. {artifact.missing_because}")

	lines += ["", "## Maintenance lanes", ""]
	for lane in report.handover.lanes:
		lines.append(f"### {lane.lane} — {lane.description}")
		lines.append("")
		lines.append(f"Ceiling: **{lane.ceiling.name}**.")
		lines.append("")
		if not lane.inherited_oracles:
			lines.append(_EMPTY)
			lines.append("")
			continue
		for oracle in lane.inherited_oracles:
			command = (
				f"`{oracle.command_hint}`"
				if oracle.is_executable
				else "no command — cannot be re-run as delivered"
			)
			lines.append(f"- `{oracle.clause_id}`: {oracle.statement}")
			lines.append(f"  - {command}")
		lines.append("")

	lines += [
		"## Verification you inherit",
		"",
		f"{len(report.verified)} clause(s) verified before delivery. Re-running the "
		"commands above is how you check the artefact still holds them; the commands are "
		"the ones the factory ran, recorded at P5.",
		"",
	]
	if report.verified:
		for clause in report.verified:
			lines.append(
				f"- `{clause.clause_id}` ({clause.oracle_class.value}): {clause.statement}"
			)
	else:
		lines.append(_EMPTY)

	lines += ["", "## Not covered", ""]
	if unmaintainable:
		lines.append(
			f"{unmaintainable} inherited oracle(s) name no command and cannot be re-run as "
			"delivered. They are the first maintenance debt this system carries."
		)
		lines.append("")
		for oracle in report.handover.unmaintainable:
			lines.append(f"- `{oracle.clause_id}`: {oracle.statement}")
	else:
		lines.append("Every inherited oracle names a command.")
	lines.append("")
	if report.unverified:
		lines.append(f"{len(report.unverified)} clause(s) were **not** verified before delivery:")
		lines.append("")
		for clause in report.unverified:
			lines.append(f"- `{clause.clause_id}`: {clause.statement} — {clause.because}")
		lines.append("")
	lines.append(
		"The factory verified requirements, not value (FR-086). Nothing here is evidence "
		"that the system is worth running."
	)
	lines.append("")
	lines.append(
		"FR-120 asks that this system be machine-usable as well as human-usable, and that "
		"is **not verified here**: no oracle in O1-O8 observes whether an artefact exposes "
		"a usable interface. Whether this system can be driven by a program is a claim "
		"nobody has checked (ADR-0048)."
	)
	lines.append("")
	lines.append(
		f"Evolvability debt is {report.evolvability_debt:g} (FR-158). This is not a "
		"measurement of this system: no oracle in O1-O8 observes what a change costs, so "
		"the value is total for every module the factory builds, and the debt a maintainer "
		"inherits here is unmeasured rather than small."
	)
	lines.append("")
	rendered = "\n".join(lines)
	missing = [heading for heading in RUNBOOK_HEADINGS if f"## {heading}" not in rendered]
	assert not missing, f"the runbook lost section(s): {missing}"
	return rendered


def render_delivery_artifacts(report: DeliveryReport) -> dict[DeliveryArtifactKind, str]:
	"""Both owed artefacts, by kind, from one report.

	The pair is rendered together because they are one derivation with two renderings
	(FR-121), and a caller that could render one without the other could write a runbook
	that quotes a report id no ``DELIVERY.md`` exists for. The service writes what this
	returns; nothing here touches the filesystem, which is what keeps the rendering a
	pure function of the log and lets a test render without a delivery root.
	"""
	return {
		DeliveryArtifactKind.REPORT: render_delivery_document(report),
		DeliveryArtifactKind.RUNBOOK: render_runbook(report),
	}
