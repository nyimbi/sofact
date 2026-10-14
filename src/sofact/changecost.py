"""FR-159 — the differential change-cost instrument (D18).

FR-159: "Maintainability has no **absolute** oracle, but decay is a **trend**, and a trend
needs only a consistent measurement, never a correct one. Where SoFact measures change cost
at all, it must do so **differentially**: for a pinned set of change units held out from the
producer, record the mechanical diff footprint per unit (files touched, hunks, lines
changed, modules crossed) and track it across the codebase's history."

**Why this module exists at all, given FR-158.** FR-158 makes evolvability debt 1.0 by
construction and caps Mode M at L1, because no oracle in O1-O8 observes change cost. That
is the honest state, and D18 asks whether it must be the permanent one. It must not: [S24]'s
thesis is that new model capability is exactly what will not arrive, and this is the one
instrument the spec specifies that requires none. So the instrument is built and the two
constants it would have to move — :data:`~sofact.views.EVOLVABILITY_DEBT` and
:data:`~sofact.views.MODE_M_CEILING` — are **left where they are**. Building an instrument
is not the same act as believing its first reading, and the gap between those two is where
this module's honesty lives.

**What it measures, precisely.** The mechanical diff a *pinned* unit produced, read from
git: files touched, hunks, lines added and removed, modules crossed. Every one of those is
a fact about a diff, taken by a program that cannot be persuaded. The unit is pinned
*before* the work — its id, its statement, its scope and the modules it expects to touch
are declared first — because a unit chosen after the diff is a unit chosen by whoever wrote
the diff, which is the same producer-authors-the-measurement failure FR-022 closes for
escapes one subsystem over.

**What it does not measure, and this is the whole boundary.** It measures change *cost* and
not design *quality*. A codebase can get cheaper to change through better tests, better
tooling, or plain familiarity, and none of those moves a line count. So it is a **proxy**
(:data:`~sofact.views.CHANGE_COST_PROXY_DECLARATION`), admissible as a trend alarm and as
a Mode M ceiling *input*, and **never as a verdict**
(:data:`~sofact.views.CHANGE_COST_NOT_A_VERIFICATION`). NFR-024 applies and is discharged
by declaration rather than by omission.

**The baseline, and why it is reported unmeasured.** ADR-0054 is the precedent and it is
exact: the escape instrument was built, its mechanism became real, and its *baseline* was
reported as unmeasured rather than clean, because a rate needs a deployment. FR-159's
baseline needs a codebase history the same way — a project with one unit per scope has no
trend, and "the footprint is stable" over one unit is NFR-024's forbidden target wearing a
chart. So a scope with fewer than two measured units is reported as *unmeasured*, by name.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from statistics import median
from typing import Any, Final, cast

from sofact._uuid7 import uuid7str
from sofact.git import GitUnavailableError, diff_footprint
from sofact.views import (
	CHANGE_COST_BASELINE_UNMEASURED,
	ChangeCostReport,
	ChangeCostRow,
	ChangeUnit,
	now,
)

__all__ = [
	"load_change_units",
	"measure_change_costs",
	"pin_unit",
	"trend_statement",
]

_CHANGE_UNIT_FIELDS: Final[frozenset[str]] = frozenset(
	{
		"statement",
		"scope",
		"expected_modules",
		"clause_id",
		"base_commit",
		"head_commit",
	}
)
"""The fields a declared unit may carry, which are the ones :func:`pin_unit` takes.

``id`` and ``declared_at`` are absent deliberately: the factory mints both, so a file
that named them would be refused rather than silently ignored.
"""


def pin_unit(
	statement: str,
	*,
	scope: str,
	expected_modules: Sequence[str] = (),
	clause_id: str | None = None,
	base_commit: str | None = None,
	head_commit: str | None = None,
) -> ChangeUnit:
	"""Pin one change unit before the work, and return it (FR-159).

	*Before* is the requirement's word and the reason this is a function rather than a
	constructor call at the measurement site: a unit declared after its diff is a unit
	whose scope was chosen to make the diff look comparable, and the whole differential
	claim rests on the comparison having been fixed in advance.

	``base_commit`` and ``head_commit`` are supplied by a caller that already knows the
	range — a build that sealed a branch knows both. A caller that does not leaves them
	``None``, and the unit measures as unmeasured rather than as a zero footprint.
	"""
	return ChangeUnit(
		id=uuid7str(),
		statement=statement,
		scope=scope,
		expected_modules=tuple(expected_modules),
		clause_id=clause_id,
		declared_at=now(),
		base_commit=base_commit,
		head_commit=head_commit,
	)


async def measure_change_costs(
	units: Iterable[ChangeUnit],
	*,
	workspace: Path | None = None,
) -> ChangeCostReport:
	"""Read each unit's footprint from ``workspace``, and trend them per scope (FR-159).

	A pure read: no oracle runs, no contract is consulted, and nothing is written. The only
	process this launches is ``git``.

	**The baseline is the median of the scope's earlier units, in declaration order**, and
	the word *earlier* is load-bearing. A baseline computed over the whole scope including
	the unit itself would move with the unit it is judging — a large change would raise its
	own baseline and shrink its own ratio, which is the measurement quietly excusing the
	thing it was built to notice. Median rather than mean because one pathological unit
	should not set the bar for its scope.

	``workspace`` is ``None`` when no repository is under measurement, which is a real state
	— a report rendered before any code exists — and every unit then measures as unmeasured
	with that reason. A report over nothing is a report claiming nothing, which is
	:attr:`~sofact.views.ChangeCostReport.discharged` returning ``()`` rather than a clean
	trend line.
	"""
	ordered = tuple(units)
	rows: list[ChangeCostRow] = []
	history: dict[str, list[float]] = {}

	for unit in ordered:
		row = await _measure_one(unit, workspace=workspace, history=history)
		rows.append(row)
		if row.measured and row.footprint is not None:
			history.setdefault(unit.scope, []).append(row.footprint.magnitude)

	return ChangeCostReport(
		id=uuid7str(),
		rendered_at=now(),
		rows=tuple(rows),
		repository=str(workspace) if workspace is not None else None,
	)


async def _measure_one(
	unit: ChangeUnit,
	*,
	workspace: Path | None,
	history: dict[str, list[float]],
) -> ChangeCostRow:
	"""One unit's row, with its baseline read from what the scope has already measured."""
	earlier = history.get(unit.scope, [])
	baseline = median(earlier) if earlier else None

	if workspace is None:
		return ChangeCostRow(
			unit=unit,
			measured=False,
			unmeasured_because=(
				"no repository was under measurement, so no diff could be read. FR-159's "
				"footprint is a fact about a repository and there is none here."
			),
		)
	span = unit.measured_range
	if span is None:
		return ChangeCostRow(
			unit=unit,
			measured=False,
			unmeasured_because=(
				"the unit records no commit range, so there is no diff to read. FR-159's "
				"units are pinned before the work, and a unit whose work has not landed "
				"has no footprint — which is not a footprint of zero."
			),
		)
	base, head = span
	try:
		footprint = await diff_footprint(workspace, base=base, head=head)
	except GitUnavailableError as exc:
		return ChangeCostRow(
			unit=unit,
			measured=False,
			unmeasured_because=(
				f"the diff {base}..{head} could not be read ({exc}), so this unit is "
				"unmeasured rather than clean. A footprint of zero and a diff that could "
				"not be taken are different facts (NFR-024)."
			),
		)

	return ChangeCostRow(
		unit=unit,
		measured=True,
		footprint=footprint,
		baseline=baseline,
	)


def trend_statement(report: ChangeCostReport) -> str:
	"""One sentence stating what the trend does and does not claim (FR-159).

	The report carries :attr:`ChangeCostReport.caveats` and this is the *reading* of them
	against the numbers in hand — which is a different thing and is why it is a function
	rather than a constant. The three states are kept apart because collapsing any two of
	them produces a sentence that is false:

	* nothing measured — no repository, or no unit with a range;
	* measured but untrended — every scope has fewer than two units, so the
		baseline statement is the one returned;
	* measured and trended — the counts, and the units that rose.
	"""
	measured = report.measured_rows
	if not measured:
		return (
			"no change unit has a footprint, so nothing is claimed: "
			+ CHANGE_COST_BASELINE_UNMEASURED
		)
	unmeasured = report.unmeasured_scopes
	if not report.discharged:
		return (
			f"{len(measured)} unit(s) measured, and no scope has two of them — so there is "
			"no trend to read and the footprint is unmeasured rather than stable. Scopes "
			f"awaiting a second unit: {', '.join(unmeasured) if unmeasured else 'none'}. "
			+ CHANGE_COST_BASELINE_UNMEASURED
		)
	rising = report.rising
	scopes = ", ".join(f"{scope} ({len(rows)})" for scope, rows in report.scopes.items())
	verdict = (
		f"{len(rising)} unit(s) rose past the declared factor and are worth a human read"
		if rising
		else "no unit rose past the declared factor, which is not a claim that the code is "
		"cheap to change"
	)
	partial = (
		f" {len(unmeasured)} scope(s) have one unit and no trend: {', '.join(unmeasured)}."
		if unmeasured
		else ""
	)
	return (
		f"{len(measured)} unit(s) measured across {len(report.scopes)} scope(s) "
		f"({scopes}); {verdict}.{partial} This is FR-159's proxy and not a verification: "
		"it observes no clause and discharges none."
	)


def load_change_units(path: Path) -> tuple[ChangeUnit, ...]:
	"""Read the pinned change units from a JSON file (FR-159).

	The same seam :func:`sofact.escape.load_escape_budget` and
	:func:`sofact.envelope.load_envelope` provide, and for the same reason: FR-159's units
	are "held out from the producer", so the set is a *deployment's* declaration rather
	than something the product infers. A factory that discovered the pinned set from a
	repository's log would be choosing the units after seeing the diffs, which is the one
	thing pinning exists to prevent.

	Two shapes are accepted, matching the other loaders: a bare array of units, or the same
	array under a ``change_units`` key. An unknown field is **refused by name** rather than
	ignored — a misspelled ``base_commit`` would otherwise load as a unit with no range,
	which measures as *unmeasured* and reads as a unit whose work has not landed.

	``id`` and ``declared_at`` are assigned here rather than read from the file: the
	document declares *what* is pinned and *where the comparison group is*, and the
	identity and the pinning timestamp are the factory's to mint. A file that could set
	``declared_at`` could backdate a unit into an earlier baseline, which is the
	comparison being chosen by the thing being compared.
	"""
	target = path
	try:
		text = target.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read change units {target}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{target}: not valid JSON: {exc}") from exc
	if isinstance(raw, dict):
		document = cast("dict[str, Any]", raw)
		body: object = document["change_units"] if set(document) == {"change_units"} else document
	else:
		body = raw
	if not isinstance(body, list):
		raise ValueError(f"{target}: expected an array of change units under 'change_units'")
	declared = cast("list[Any]", body)
	if not declared:
		raise ValueError(
			f"{target}: no change units; FR-159 measures a trend across a *pinned* set, and "
			"a file that declares none would read as configured while measuring nothing"
		)

	units: list[ChangeUnit] = []
	for index, payload in enumerate(declared):
		if not isinstance(payload, dict):
			raise ValueError(f"{target}: unit {index} must be an object")
		fields = cast("dict[str, Any]", payload)
		unknown = set(fields) - _CHANGE_UNIT_FIELDS
		if unknown:
			raise ValueError(
				f"{target}: unit {index} names {sorted(unknown)}, which is not a change-unit "
				"field; a misspelled field would otherwise be ignored and the unit would "
				"read as declared while pinning something else"
			)
		missing = {"statement", "scope"} - set(fields)
		if missing:
			raise ValueError(
				f"{target}: unit {index} declares no {sorted(missing)}; a unit with no "
				"scope cannot be compared to anything, which is the one thing FR-159's "
				"instrument needs it to be"
			)
		try:
			units.append(
				pin_unit(
					str(fields["statement"]),
					scope=str(fields["scope"]),
					expected_modules=tuple(str(m) for m in fields.get("expected_modules", ())),
					clause_id=fields.get("clause_id"),
					base_commit=fields.get("base_commit"),
					head_commit=fields.get("head_commit"),
				)
			)
		except ValueError as exc:
			raise ValueError(f"{target}: unit {index} is not a change unit: {exc}") from exc
	return tuple(units)
