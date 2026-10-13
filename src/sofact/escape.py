"""FR-021-023 — the escape oracle.

FR-021: "Every accepted change must be tracked forward through deploy. Escape events —
revert, hot-fix, or incident implicating the same defect — must be recorded against the
change, its lane, its oracle-strength band, and its autonomy level."
FR-022: "Escape rate must be reported per lane and per autonomy level, and is the
**primary safety metric** of the product. It cannot be gamed by the producer because it is
measured by events the producer does not author."
FR-023: "A lane whose escape rate exceeds its declared budget must have its autonomy
ceiling **automatically reduced** until escape rate returns to budget. Manual override
must be logged and attributed."

§2.4 asks "Who verifies the verifier?" and answers that the regress "terminates in exactly
one place: **reality, after deployment**". This module is that place. Every other ceiling
in SoFact is derived from declarations — oracle rank, module class, topology — and a
declaration can be wrong in a direction nobody observes until something is reverted. The
escape rate is the one number in the product that no producer authored, which is what
FR-022 means by "cannot be gamed": the producer writes oracles and modules, and does not
write deploys or reverts.

**What this module reads, and what it refuses to read.** It is a pure fold over the log:
deploy records, delivery reports, and the escapes an operator recorded. It opens no file,
runs no oracle, and consults no declaration of strength. FR-021's "its oracle-strength
band, and its autonomy level" are *derived* here from the change's contract and module
class rather than copied onto the escape row — see :attr:`~sofact.views.EscapeReport.caveats`
for why, stated on the report so a reader does not have to infer the choice.

**The honest limit, which is not FR-022's claim.** A producer cannot inflate this number.
An operator who does not record an escape lowers it, and no code can prevent that — FR-021's
recording discipline is a human obligation, and pretending otherwise would be the factory
grading its own homework one level up. The report names the limit rather than letting
"cannot be gamed by the producer" be read as "cannot be gamed".
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sofact._uuid7 import uuid7str
from sofact.views import (
	MODULE_CLASS_CEILING,
	AutonomyLevel,
	Contract,
	Decomposition,
	DeliveryReport,
	DeployRecord,
	EscapeBudget,
	EscapeEvent,
	EscapeOverride,
	EscapeReport,
	LaneEscape,
	ModuleClass,
	lane_ceiling,
	now,
)

__all__ = ["ceilings_from", "lanes_of", "load_escape_budget", "measure_escapes"]


def lanes_of(report: DeliveryReport, decomposition: Decomposition | None) -> frozenset[ModuleClass]:
	"""The module classes a delivery exercised, read off its traceability chain (FR-021).

	This is the single lane-resolution rule: :meth:`~sofact.service.FactoryService.record_escape`
	uses it to refuse an escape filed against a lane the deployment never touched, and
	:func:`measure_escapes` uses it to build each lane's denominator. One function, so a
	refusal and a rate cannot disagree about which lanes a deployment exercised.

	A :class:`~sofact.views.DeliveryReport` carries ``chain`` — one
	:class:`~sofact.views.TraceLink` per intent clause, each naming a module by *name* — and
	no ``decomposition_id``, so the class is resolved through the decomposition the caller
	holds. Two links resolve to nothing and neither is an error here: a link whose
	``module`` is ``None`` is a clause the decomposition dropped, and a name matching no
	module is a chain gap ``traceability_chain`` already fails on at the gate. This
	function reports the lanes a report *exercised*; a report that exercised none is
	counted by :func:`measure_escapes` as an orphan deployment rather than silently dropped.
	"""
	assert report.chain is not None, "a report's chain is a tuple, never None"
	if decomposition is None:
		return frozenset()
	lanes: set[ModuleClass] = set()
	for link in report.chain:
		if link.module is None:
			continue
		module = decomposition.module_by_name(link.module)
		if module is not None:
			lanes.add(module.module_class)
	return frozenset(lanes)


def load_escape_budget(path: Path) -> tuple[EscapeBudget, ...]:
	"""Read per-lane escape budgets from a JSON file (FR-023).

	The same seam :func:`sofact.envelope.load_envelope` and :func:`sofact.harness.load_specs`
	provide, and for the same reason: FR-023 says a lane is reduced when it exceeds "its
	**declared** budget", so the budget is a deployment's declaration rather than a constant
	in the product. §20.3 item 4 records that no escape baseline exists until there has been
	a deployment, and NFR-024 forbids reporting a target the product has not measured — so
	there is no default here, and a deployment that declares none gets no reduction and a
	report that says so.

	Two shapes are accepted, matching the other loaders: a bare object of lanes, or the same
	object under an ``escape_budget`` key. A lane name that is not §14's is refused rather
	than ignored, because a misspelled lane would read as configured while bounding nothing.
	"""
	target = path
	try:
		text = target.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read escape budget {target}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{target}: not valid JSON: {exc}") from exc
	if not isinstance(raw, dict):
		raise ValueError(f"{target}: expected a JSON object of lanes")
	document = cast("dict[str, Any]", raw)
	body: object = document["escape_budget"] if set(document) == {"escape_budget"} else document
	if not isinstance(body, dict):
		raise ValueError(f"{target}: expected an object of lanes under 'escape_budget'")
	declared = cast("dict[str, Any]", body)
	if not declared:
		raise ValueError(
			f"{target}: no lanes; FR-023 reduces a lane over its *declared* budget, and a "
			"file that declares none would read as configured while reducing nothing"
		)

	budgets: list[EscapeBudget] = []
	for name, payload in declared.items():
		try:
			lane = ModuleClass(name)
		except ValueError as exc:
			known = ", ".join(c.value for c in ModuleClass)
			raise ValueError(f"{target}: {name!r} is not a §14 lane class; known: {known}") from exc
		if not isinstance(payload, dict):
			raise ValueError(f"{target}: lane {name!r} must be an object with a budget")
		fields = cast("dict[str, Any]", payload)
		unknown = set(fields) - {"maximum_rate", "declared_by"}
		if unknown:
			raise ValueError(
				f"{target}: lane {name!r} names {sorted(unknown)}, which is not a budget "
				"field; a misspelled field would otherwise be ignored and the budget would "
				"read as declared while bounding what it always did"
			)
		if "maximum_rate" not in fields:
			raise ValueError(
				f"{target}: lane {name!r} declares no maximum_rate, so it declares no "
				"budget; FR-023 reduces a lane over a rate, and a lane with no rate is "
				"unbudgeted rather than bounded at zero"
			)
		budgets.append(
			EscapeBudget(
				lane=lane,
				maximum_rate=float(fields["maximum_rate"]),
				declared_by=str(fields.get("declared_by", f"{target}")),
			)
		)
	return tuple(budgets)


def measure_escapes(
	*,
	deploys: Sequence[DeployRecord],
	reports: Sequence[DeliveryReport],
	decompositions: Sequence[Decomposition],
	escapes: Sequence[EscapeEvent],
	budgets: Sequence[EscapeBudget] = (),
	overrides: Sequence[EscapeOverride] = (),
	contracts: Sequence[Contract] = (),
	rendered_at: datetime | None = None,
) -> EscapeReport:
	"""Fold the log into FR-022's rate, and FR-023's reduction, per lane.

	Pure: every input is a record the caller already read, and nothing here opens a file or
	runs a process. That is what makes the number reproducible from the log, which is what
	makes it evidence rather than a summary.

	**The denominator** is the number of distinct deployed reports whose traceability chain
	reaches a module of the lane. A *deployed* report, because FR-021 tracks a change
	"forward through deploy" and a report nobody deployed has not met reality yet; distinct
	by ``report_id``, because a re-render of one report is one change rather than two.

	**The numerator** is the number of distinct ``defect`` values recorded against the lane
	across those deployments. Distinct defects rather than rows, because FR-021 names three
	kinds of event and one defect can produce two of them — a revert and then a hot-fix —
	and counting rows would report one failure as two. FR-021 wants the *kinds* recorded,
	which they are; FR-022 wants the *rate*, which is a rate of defects.

	**The denominator includes the change that escaped.** An escape is recorded against a
	deployed report, so that report is in the lane's set by construction. The rate is
	therefore conservatively high — one escape in one deployment reads as 1.0 — and that is
	the correct direction for a safety metric. The report states it rather than leaving a
	reader to assume escaped changes are excluded.

	``rendered_at`` is the instant the measurement describes, and a caller that is
	*storing* the report supplies it — :func:`sofact.delivery.report` pins the delivery's
	instant so the delivery and its escape table carry one timestamp rather than two that
	differ by however long the render took. The default is now, which is what a caller
	reading the rate for its own sake wants.
	"""
	by_report_id = {report.id: report for report in reports}
	deployed_ids: list[str] = []
	seen: set[str] = set()
	for deploy in deploys:
		if deploy.report_id in seen:
			continue
		seen.add(deploy.report_id)
		deployed_ids.append(deploy.report_id)

	decomposition_for: dict[str, Decomposition] = {}
	for decomposition in decompositions:
		decomposition_for[decomposition.contract_id] = decomposition
	contract_for = {contract.id: contract for contract in contracts}

	lane_deployments: dict[ModuleClass, set[str]] = {}
	lane_bands: dict[ModuleClass, set[int]] = {}
	orphans = 0
	for report_id in deployed_ids:
		report = by_report_id.get(report_id)
		if report is None:
			# A deploy naming a report the log no longer holds. Counted as an orphan rather
			# than skipped silently: the metric could not place it, and a reader is owed the
			# number of changes it could not place.
			orphans += 1
			continue
		decomposition = decomposition_for.get(report.contract_id)
		lanes = lanes_of(report, decomposition)
		if not lanes:
			orphans += 1
			continue
		# FR-021's oracle-strength band, derived from the change's own contract rather than
		# copied onto the escape row. `weakest_oracle_rank` is the number `Contract.ceiling`
		# is computed from, so the band an escape is attributed to is the same number the
		# delivery's ceiling came from and the two cannot disagree.
		contract = contract_for.get(report.contract_id)
		band = contract.weakest_oracle_rank if contract is not None else None
		for lane in lanes:
			lane_deployments.setdefault(lane, set()).add(report_id)
			if band is not None:
				lane_bands.setdefault(lane, set()).add(band)

	budget_for = {budget.lane: budget for budget in budgets}
	defects_for: dict[ModuleClass, set[str]] = {}
	for escape in escapes:
		if escape.report_id not in seen:
			# An escape against a report no deploy approved. `record_escape` refuses this,
			# so reaching here means the log was written by an older or a foreign producer;
			# the honest treatment is to leave it out of every lane rather than to credit a
			# lane with an escape from a change that never shipped.
			continue
		defects_for.setdefault(escape.lane, set()).add(escape.defect)

	rows: list[LaneEscape] = []
	unbudgeted: list[ModuleClass] = []
	for lane in ModuleClass:
		deployed = lane_deployments.get(lane)
		if not deployed:
			# A lane with no deployments is unmeasured, not clean. Omitting it is the
			# difference between a report of what was measured and a report of what went
			# wrong; `EscapeReport.discharged` is what keeps a fully empty report from
			# reading as a clearance.
			continue
		budget = budget_for.get(lane)
		defects = defects_for.get(lane, set())
		rate = len(defects) / len(deployed)
		if budget is None:
			unbudgeted.append(lane)
			over: bool | None = None
		else:
			over = rate > budget.maximum_rate
		override = next((o for o in reversed(overrides) if o.lane is lane), None)
		rows.append(
			LaneEscape(
				lane=lane,
				deployed_changes=len(deployed),
				escapes=len(defects),
				rate=rate,
				budget=budget,
				over_budget=over,
				granted_ceiling=MODULE_CLASS_CEILING[lane],
				oracle_ranks=tuple(sorted(lane_bands.get(lane, set()))),
				reduced_ceiling=lane_ceiling(lane, rate=rate, budget=budget, override=override),
				override=override if over else None,
			)
		)

	return EscapeReport(
		id=uuid7str(),
		rendered_at=now() if rendered_at is None else rendered_at,
		lanes=tuple(rows),
		unbudgeted=tuple(unbudgeted),
		orphan_deployments=orphans,
		deployed_reports=len(deployed_ids),
	)


def ceilings_from(escapes: EscapeReport | None) -> Mapping[ModuleClass, AutonomyLevel] | None:
	"""The lane ceilings an escape measurement implies, for the autonomy computation.

	``None`` when there is no measurement at all, which is a different statement from a
	measurement that reduced nothing — :func:`sofact.delivery.module_autonomy` takes
	``None`` to mean "nothing measured" and reports that rather than reading it as "no
	reduction".
	"""
	if escapes is None:
		return None
	return {lane.lane: lane.reduced_ceiling for lane in escapes.lanes}
