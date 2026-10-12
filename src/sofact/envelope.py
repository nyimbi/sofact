"""§1.3's delivery envelope: the bounds, and the actuals measured against them.

Two requirements, and they are different in kind:

* **FR-057** is a *refusal*: a decomposition that exceeds the envelope is refused, and
  the refusal names the dimension. It belongs in P3's gate, because the decomposition is
  the first artefact that says how big the platform will be, and a refusal at P8 would
  be a refusal after the build.
* **NFR-025** is a *measurement*: the envelope is configuration, and every delivery
  reports actuals against it.

The distinction decides everything below. §1.3 states its numbers as "**targets, not
measurements**" and says the envelope "is a hypothesis under test", so the gate refuses
one end and reports the other: a delivery over a ceiling is the over-scoped goal FR-057
refuses, and a delivery under a floor is a small project — a legitimate thing to build.
A gate that failed on the floor would refuse to build anything smaller than a platform,
which is the opposite of what a factory that must earn trust should do.

Three of the eight dimensions are **unmeasured**, and that is reported rather than
papered over. Nothing in the log declares a *system* (§7.2's decomposition maps clauses
to modules, and §1.3 counts systems), nothing reads the delivered source to count lines
(ADR-0025 leaves the target language open, so SoFact does not know what a source file
is), and wall-clock and human-minutes are outcomes of a build rather than facts about a
plan. Each unmeasured dimension names what would have to exist before anything could be
counted, which is a work item rather than a gap in the arithmetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from sofact.views import (
	PHASE_GATE,
	Decomposition,
	DeliveryEnvelope,
	DimensionBound,
	EnvelopeActuals,
	EnvelopeDimension,
	EnvelopeMeasurement,
	ModuleClass,
)

__all__ = [
	"MEASURED_AT_P3",
	"UNMEASURED_AT_P3",
	"load_envelope",
	"measure",
]

MEASURED_AT_P3: tuple[EnvelopeDimension, ...] = (
	EnvelopeDimension.MODULES,
	EnvelopeDimension.EXTERNAL_INTEGRATIONS,
	EnvelopeDimension.HUMAN_GATES,
	EnvelopeDimension.VALUE_HYPOTHESIS,
)
"""The dimensions a decomposition and an approved specification can actually settle.

Five of §1.3's eight are not here, and none of the five is an omission: ``systems``
needs a tier the decomposition does not have, ``delivered_loc`` needs a declared
artefact root, and ``human_minutes``/``wall_clock_days`` are outcomes of the build. The
set is a constant rather than a computed thing so that :func:`measure` cannot silently
start reporting a dimension by accident.
"""

UNMEASURED_AT_P3: tuple[EnvelopeDimension, ...] = tuple(
	dimension for dimension in EnvelopeDimension if dimension not in MEASURED_AT_P3
)


def load_envelope(path: Path) -> DeliveryEnvelope:
	"""Read an envelope from a JSON file (NFR-025).

	This is the seam that makes the envelope *configuration* rather than a constant, and
	it is deliberately the same shape as :func:`sofact.harness.load_specs`: a bare object
	of dimensions, or the same object under an ``envelope`` key.

	A partial override is merged onto §1.3's defaults **per dimension**, because an
	operator narrowing the module ceiling should not have to restate the other seven. The
	merge is per dimension and not per field: supplying ``{"modules": {"maximum": 5}}``
	keeps the default floor of 8, and the bound type then refuses the empty range with its
	own sentence rather than silently dropping a floor the operator never removed.
	Dropping it would widen the envelope by omission, which is the one direction an
	envelope must not drift.
	"""
	try:
		text = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read envelope {path}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{path}: not valid JSON: {exc}") from exc
	if not isinstance(raw, dict):
		raise ValueError(f"{path}: expected a JSON object of dimensions")
	document = cast("dict[str, Any]", raw)
	body: object = document["envelope"] if set(document) == {"envelope"} else document
	if not isinstance(body, dict):
		raise ValueError(f"{path}: expected an object of dimensions under 'envelope'")
	declared = cast("dict[str, Any]", body)
	if not declared:
		raise ValueError(
			f"{path}: no dimensions; an envelope that bounds nothing would let every "
			"decomposition through while reading as configured (FR-057)"
		)

	base = DeliveryEnvelope()
	merged: dict[str, Any] = {}
	for name, payload in declared.items():
		try:
			dimension = EnvelopeDimension(name)
		except ValueError as exc:
			known = ", ".join(d.value for d in EnvelopeDimension)
			raise ValueError(f"{path}: {name!r} is not a §1.3 dimension; known: {known}") from exc
		if not isinstance(payload, dict):
			raise ValueError(f"{path}: dimension {name!r} must be an object of bounds")
		fields = cast("dict[str, Any]", payload)
		unknown = set(fields) - {"unit", "minimum", "maximum"}
		if unknown:
			raise ValueError(
				f"{path}: dimension {name!r} names {sorted(unknown)}, which is not a bound; "
				"a misspelled field would otherwise be ignored and the bound would read as "
				"configured while bounding what it always did"
			)
		current = base.bound(dimension)
		merged[dimension.value] = DimensionBound(
			unit=fields.get("unit", current.unit),
			minimum=fields.get("minimum", current.minimum),
			maximum=fields.get("maximum", current.maximum),
		)
	return base.model_copy(update=merged)


def measure(
	envelope: DeliveryEnvelope,
	decomposition: Decomposition | None,
	*,
	value_hypothesis_declared: bool | None = None,
) -> EnvelopeActuals:
	"""Every dimension's actual, from what the log holds (NFR-025, FR-118).

	``decomposition is None`` means P3 has not run, and then nothing at all is measured:
	reporting module counts for a project with no decomposition would be reporting the
	absence of an artefact as a measurement of it.

	``value_hypothesis_declared`` has three states, not two, and the third is the one
	that matters: ``None`` means the caller did not ask, and the dimension is then
	*unmeasured* rather than counted as zero. P3's gate does not read the specification,
	so a two-state flag would make every P3 run report a missing value hypothesis — a
	measurement of the caller's silence, printed as a fact about the project.

	Every derivation here is a *count of declarations*, never a reading of code. SoFact
	holds no build, and ADR-0025 leaves the language open, so a number obtained by
	looking at a workspace would be a number about something the factory did not decide.
	"""
	if decomposition is None:
		unrun = tuple(
			EnvelopeMeasurement(
				dimension=dimension,
				bound=envelope.bound(dimension),
				detail="no decomposition has been proposed, so P3 has measured nothing yet",
			)
			for dimension in EnvelopeDimension
		)
		return EnvelopeActuals(envelope=envelope, measurements=unrun)

	modules = len(decomposition.modules)
	integrations = sum(
		1 for module in decomposition.modules if module.module_class is ModuleClass.G6
	)
	gates = len(PHASE_GATE)
	clauses = len(
		{clause_id for module in decomposition.modules for clause_id in module.clause_ids}
	)

	actuals: dict[EnvelopeDimension, tuple[float, str]] = {
		EnvelopeDimension.MODULES: (
			modules,
			f"{modules} module(s) proposed, owning {clauses} clause(s)",
		),
		EnvelopeDimension.EXTERNAL_INTEGRATIONS: (
			integrations,
			f"{integrations} module(s) classified G6 (external integration adapter). "
			"`classify` assigns G6 by keyword, so this is a stated basis rather than an "
			"inventory of what the delivered system calls (FR-125)",
		),
		EnvelopeDimension.HUMAN_GATES: (
			gates,
			f"{gates} gated phase(s) in the pipeline: "
			+ ", ".join(sorted(gate.value for gate in PHASE_GATE.values())),
		),
	}
	if value_hypothesis_declared is not None:
		actuals[EnvelopeDimension.VALUE_HYPOTHESIS] = (
			1 if value_hypothesis_declared else 0,
			"declared at P2 and required for the gate (FR-085)"
			if value_hypothesis_declared
			else "the approved specification declares none, which FR-085 makes a P2 gate "
			"failure — reaching P3 in this state means the gate was bypassed",
		)

	reasons: dict[EnvelopeDimension, str] = {
		EnvelopeDimension.SYSTEMS: (
			"no artefact in the log declares a system. §7.2 has the decomposition map "
			"clauses to modules, and §1.3 counts systems, so counting one here would be "
			"inventing a boundary the operator never drew (FR-087)"
		),
		EnvelopeDimension.DELIVERED_LOC: (
			"nothing reads the delivered source. ADR-0025 leaves the target language "
			"open, so SoFact does not know what a source file is; a count needs a "
			"declared artefact root first"
		),
		EnvelopeDimension.HUMAN_MINUTES: (
			"gate cost is an outcome of the build, not a fact about a plan (FR-160 makes "
			"it a measurement each gate records, and no gate records one yet)"
		),
		EnvelopeDimension.WALL_CLOCK_DAYS: (
			"wall clock is spent by dispatch, not planned by decomposition. Per-step "
			"wall clock is recorded (FR-140); per-platform wall clock is not derived"
		),
		EnvelopeDimension.VALUE_HYPOTHESIS: (
			"the caller did not read the approved specification, so whether one was "
			"declared is unknown here rather than false (FR-085)"
		),
	}

	measurements: list[EnvelopeMeasurement] = []
	for dimension in EnvelopeDimension:
		bound = envelope.bound(dimension)
		if dimension in actuals:
			value, detail = actuals[dimension]
			measurements.append(
				EnvelopeMeasurement(
					dimension=dimension,
					bound=bound,
					actual=value,
					within=bound.admits(value),
					detail=detail,
				)
			)
			continue
		assert dimension in reasons, f"dimension {dimension.value} is neither measured nor refused"
		measurements.append(
			EnvelopeMeasurement(dimension=dimension, bound=bound, detail=reasons[dimension])
		)
	return EnvelopeActuals(envelope=envelope, measurements=tuple(measurements))
