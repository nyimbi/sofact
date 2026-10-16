"""Model tiers: which model a phase runs on, as data (FR-132, NFR-012).

FR-132 asks for a model configuration that is **tiered and declarative**, "a large
model where reasoning depth matters (P3 decomposition, P6 failure diagnosis, the
adversary), and a cheap or local model for high-volume low-depth work (P5 module
builds, test generation, triage)". Before this module the tree had one model for
everything: ``--model``, else ``SOFACT_MODEL``, else :data:`~sofact.llm.DEFAULT_MODEL`,
resolved at the adapter and identical for every dispatch of every phase.

**The split is the whole design.** SoFact owns *which phases need depth* — that is a
statement about the pipeline, and it is the same for every deployment. The deployment
owns *which model sits in each tier* — that is a statement about its hardware, its
budget and its data-residency obligations, and SoFact must not have an opinion about
it (NFR-026, FR-049). So :data:`TIER_PHASES` is built in and a tier's *model* is
configuration. A deployment with no tier table gets exactly today's behaviour: one
model, every phase, no silent substitution.

**A tier with no model is not a tier with a default model.** An operator who declares
the ``deep`` tier and names no model for it has said "these phases are the expensive
ones" without saying what runs them, and answering that with the cheap model would be
the substitution FR-132 exists to prevent — so the tier's phases fall back to the
operator's single model, which is a *named* fallback rather than a guess, and
:func:`resolve_model` reports which one it used.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeGuard, cast

from sofact.views import Phase, PlanStepKind, ReasoningClass

__all__ = [
	"MODEL_TIERS_ENV",
	"REASONING_CLASS_TIER",
	"STEP_PHASE",
	"TIER_PHASES",
	"ModelTier",
	"ModelTierRefusal",
	"load_model_tiers",
	"phase_tier",
	"resolve_model",
	"step_phase",
	"tier_statement",
]

MODEL_TIERS_ENV: Final = "SOFACT_MODEL_TIERS"
"""Where a deployment declares its per-tier models (FR-132).

Beside ``SOFACT_HARNESS_SPECS`` and ``SOFACT_MANUFACTURE_SPECS``: the same seam, the
same file shape, and the same refusal naming the variable when it cannot be read.
"""

TIER_PHASES: Final[dict[str, tuple[Phase, ...]]] = {
	"deep": (Phase.DECOMPOSE, Phase.VERIFY, Phase.CONTRACT),
	"cheap": (Phase.BUILD, Phase.INTEGRATE),
}
"""Which phases need reasoning depth, and which are high-volume (FR-132, NFR-012).

Read off FR-132's own words rather than invented: it names P3 decomposition and P6
failure diagnosis as the depth cases, and P5 module builds and test generation as the
high-volume ones.

``CONTRACT`` is here and FR-132 does not name it. It is assigned to ``deep`` because
P4 is where a clause gets the oracle that decides whether it was ever satisfied
(FR-103), and an oracle assigned by a cheap model is a weak oracle *recorded as a
decision* — the one artefact in the pipeline that is cheaper to get wrong later than
to get right now. ``INTEGRATE`` is assigned to ``cheap`` because FR-142's wave
scheduler runs it mechanically in topological order.

The assignment is deliberately *not* exhaustive: a phase in no tier is a phase whose
depth SoFact has not decided, and :func:`phase_tier` returns ``None`` for it rather
than forcing it into a bucket. A default that covers every phase would be a claim
about P0, P1, P7 and P9 that nothing in FR-132 supports.
"""


STEP_PHASE: Final[dict[PlanStepKind, Phase]] = {
	PlanStepKind.BOOTSTRAP: Phase.BUILD,
	PlanStepKind.INTERFACES: Phase.BUILD,
	PlanStepKind.OPERATION: Phase.BUILD,
	PlanStepKind.INVARIANT: Phase.BUILD,
	PlanStepKind.STATE_MACHINE: Phase.BUILD,
	PlanStepKind.REPAIR: Phase.VERIFY,
}
"""Which phase a dispatched step belongs to (FR-133).

``DispatchRecord`` carries a plan step, and a plan step carries no phase — the
decomposition is P3's artefact and the plan is P5's, so the two never met. FR-133 asks
for spend "attributed per phase", which needs that join, and this is it: derived from
:class:`~sofact.views.PlanStepKind` rather than added as a field, because a field would
be a second place for the same fact to be wrong.

The assignment follows §8.4's step kinds. Five of the six kinds build something, and
they are P5 by construction. ``REPAIR`` is P6's: FR-101's loop re-works the clauses whose
oracles could not support the contract's ceiling, which is failure diagnosis, and it is
the one kind FR-132 names as needing depth.

**A step kind this build does not know is a refusal, not a guess.** The dict is total
over the enum, and a caller cannot reach the missing branch without adding a member —
which is the point: a new step kind is a new phase assignment somebody has to make, and
defaulting it to ``BUILD`` would silently attribute the spend of a phase nobody
considered to the one phase that already dominates the envelope.
"""


def step_phase(kind: PlanStepKind) -> Phase:
	"""The phase ``kind`` belongs to (FR-133).

	Total over :class:`~sofact.views.PlanStepKind`, and asserted so: a member added to the
	enum without an entry here raises rather than returning a default, because the default
	would be a phase assignment nobody made.
	"""
	phase = STEP_PHASE.get(kind)
	assert phase is not None, f"step kind {kind.value!r} has no phase assignment (FR-133)"
	return phase


class ModelTierRefusal(Exception):
	"""A tier table that cannot be read, or a tier named with nothing to run (FR-132)."""


@dataclass(frozen=True, slots=True)
class ModelTier:
	"""One deployment's model for one tier, and why (FR-132).

	``rationale`` is required rather than optional for :class:`~sofact.harness.HarnessSpec`'s
	reason one level over: a tier table is read by whoever inherits the deployment, and
	"why is P5 on the small model" is the question that decides whether the answer is
	still right after the hardware changes. A table that cannot answer it is a table
	whose entries get copied forward unexamined.
	"""

	name: str
	model: str
	rationale: str

	def __post_init__(self) -> None:
		if not self.name.strip():
			raise ModelTierRefusal("a tier needs a name")
		if not self.model.strip():
			raise ModelTierRefusal(
				f"tier {self.name!r} names no model; declare one or drop the tier, because "
				"falling back to another tier's model is the substitution FR-132 prevents"
			)
		if not self.rationale.strip():
			raise ModelTierRefusal(f"tier {self.name!r} gives no reason for its model")


def _str_keyed(value: object) -> TypeGuard[Mapping[str, object]]:
	"""True when ``value`` is a JSON object, so ``json.loads`` output can be narrowed."""
	if not isinstance(value, dict):
		return False
	# A cast rather than an annotation, for the reason ``harness._str_keyed`` gives: pyright
	# keeps ``isinstance``'s narrowed ``dict[Unknown, Unknown]`` over a declared supertype,
	# so the ``Unknown`` would survive to every read. The ``isinstance`` is the check.
	obj = cast("Mapping[object, object]", value)
	return all(isinstance(key, str) for key in obj)


def _text(name: str, payload: Mapping[str, object], key: str) -> str:
	"""One string field of a tier entry, absent as the empty string.

	Refuses a non-string rather than ``str()``-ing it: ``"model": {"name": "x"}`` is a
	plausible mistake, and stringifying it would produce a model named ``{'name': 'x'}``
	that the harness rejects later, from a place that cannot say which tier it came from.
	"""
	value = payload.get(key)
	if value is None:
		return ""
	if not isinstance(value, str):
		raise ModelTierRefusal(
			f"tier {name!r}: {key!r} must be a string, not {type(value).__name__}"
		)
	return value


def load_model_tiers(path: Path) -> dict[str, ModelTier]:
	"""Read a tier table from a JSON file (FR-132).

	Two shapes are accepted — ``{"tiers": {name: {...}}}`` and a bare ``{name: {...}}``
	— for :func:`sofact.harness.load_specs`'s reason: a deployment writing the file by
	hand should not have to know which spelling the reader prefers.

	A tier naming a phase-set SoFact does not know is refused rather than ignored. The
	built-in assignment is SoFact's half of the split, so a table that tries to move a
	phase between tiers is asking to own the half it does not own — and silently
	dropping the request would leave the operator believing a phase had been retiered.
	"""
	try:
		text = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise ModelTierRefusal(f"cannot read model tier table {path}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ModelTierRefusal(f"{path}: not valid JSON: {exc}") from exc
	if not _str_keyed(raw):
		raise ModelTierRefusal(f"{path}: expected a JSON object")
	body: object = raw["tiers"] if set(raw) == {"tiers"} else raw
	if not _str_keyed(body):
		raise ModelTierRefusal(f"{path}: expected an object of tiers under 'tiers'")
	tiers: dict[str, ModelTier] = {}
	for name, payload in body.items():
		if not _str_keyed(payload):
			raise ModelTierRefusal(f"{path}: tier {name!r} must be an object")
		if name not in TIER_PHASES:
			known = ", ".join(sorted(TIER_PHASES))
			raise ModelTierRefusal(
				f"{path}: tier {name!r} is not one of this build's tiers ({known}). Which "
				"phases need depth is SoFact's assignment rather than a deployment's "
				"(FR-132); a table names the model each tier runs, not which phases are in it"
			)
		unknown = sorted(set(payload) - {"name", "model", "rationale"})
		if unknown:
			raise ModelTierRefusal(f"{path}: tier {name!r}: unknown field(s) {unknown}")
		declared = _text(name, payload, "name")
		if declared and declared != name:
			# The key is what :func:`phase_tier` looks up and the field is what a reader
			# believes the entry is about. Two names for one tier is one tier that two
			# readers disagree about, and the lookup would win silently.
			raise ModelTierRefusal(
				f"{path}: tier {name!r} declares itself as {declared!r}; the key is the name"
			)
		tiers[name] = ModelTier(
			name=name,
			model=_text(name, payload, "model"),
			rationale=_text(name, payload, "rationale"),
		)
	if not tiers:
		raise ModelTierRefusal(f"{path}: no tiers; an empty table names no model to run")
	return tiers


def phase_tier(phase: Phase) -> str | None:
	"""The tier ``phase`` belongs to, or ``None`` if SoFact assigns it none (FR-132).

	``None`` is the honest answer for a phase whose depth nothing has decided, and it is
	not the same as the ``cheap`` tier: a phase SoFact put in ``cheap`` has been *judged*
	high-volume, while a phase in no tier has not been judged at all.
	"""
	for name, phases in TIER_PHASES.items():
		if phase in phases:
			return name
	return None


REASONING_CLASS_TIER: Final[dict[ReasoningClass, str]] = {
	ReasoningClass.THROUGHPUT: "cheap",
	ReasoningClass.REASONING: "deep",
	ReasoningClass.EVALUATION: "deep",
}
"""Which tier a module's *declared* reasoning class routes to (FR-050, FR-097).

**The half of the routing function that was missing.** FR-050's sentence is that lanes
declare "the class they need (reasoning-depth or throughput), not a model name", and
FR-097 makes that class a required field of every module's budget. The class was declared
on every module in every decomposition and read by exactly two print statements — a
``ModuleBudget`` saying ``reasoning`` put a module on the same model as one saying
``throughput``, which is the "written and never read" defect: a field the system collects
and never uses.

The mapping is SoFact's and not a deployment's, on :data:`TIER_PHASES`' own argument one
level down. That a reasoning-class module needs a deeper model than a throughput-class one
is a statement about what the *classes mean* — §10.2 defines them as depth-per-token
against high-volume — and it is the same for every deployment. *Which* model sits in
``deep`` remains the deployment's, exactly as for a phase.

``EVALUATION`` routes to ``deep`` rather than to a tier of its own. §10.2 marks it
"ideally deterministic tooling, not a model", so a deployment that has such tooling should
configure it as the ``deep`` tier's model for the modules that need it; giving the class
its own tier would be SoFact inventing a fourth bucket for a case FR-051 says should not
be a model at all. Routing it to ``cheap`` would be the worse error of the two, because
the class exists precisely for work whose verdict matters.

A class this build does not know is a refusal rather than a fall-through, for
:func:`step_phase`'s reason: the dict is total over the enum, and a new member is a
routing decision somebody has to make rather than one that silently inherits ``cheap``.
"""


def class_tier(reasoning_class: ReasoningClass) -> str:
	"""The tier a module declaring ``reasoning_class`` routes to (FR-050).

	Total over :class:`~sofact.views.ReasoningClass`, and asserted so. Defaulting to
	``cheap`` would put a class nobody considered on the high-volume model, which is the
	direction that fails toward an unmeasured verdict.
	"""
	tier = REASONING_CLASS_TIER.get(reasoning_class)
	assert tier is not None, (
		f"reasoning class {reasoning_class.value!r} has no tier assignment (FR-050)"
	)
	return tier


def resolve_model(
	phase: Phase,
	*,
	explicit: str | None = None,
	tiers: Mapping[str, ModelTier] | None = None,
	operator_model: str | None = None,
	environ: Mapping[str, str] | None = None,
	reasoning_class: ReasoningClass | None = None,
) -> tuple[str, str]:
	"""The model ``phase`` runs on, and which rule chose it (FR-132, FR-050).

	Returns ``(model, source)``. The source is returned rather than inferred by the
	caller because "which model ran this phase, and on whose authority" is the question
	the tier design exists to make answerable — and a caller that re-derived it from the
	same inputs would be a second implementation of this precedence.

	The order is **explicit, then the module's declared class, then the phase's tier,
	then operator, then default**:

	- ``explicit`` — ``--model`` on the verb. An operator naming a model for *this* run
		outranks a table written for every run, which is the ordinary meaning of a flag.
	- the tier :func:`class_tier` derives from ``reasoning_class``, when the caller
		supplied the class a module declared and the deployment named a model for that tier.
	- the tier of the *phase*, when the phase is in one **and** the deployment named one.
	- ``operator_model`` — ``SOFACT_MODEL``, else :data:`~sofact.llm.DEFAULT_MODEL`.

	**Why the class outranks the phase.** FR-132 assigns depth *per phase* and FR-097 makes
	it a required declaration *per module*, and the two disagree by construction: every P5
	step is ``BUILD``, which FR-132 puts in ``cheap``, while a module may declare
	``reasoning`` because its work needs depth. The phase is a statement about the
	*pipeline* — P5 is high-volume work in general — and the module is a statement about
	*this* module. Reading the phase first would make the module's declaration
	unobservable, which is the state this argument exists to end.

	A class the caller does not supply changes nothing: the phase's tier applies, which is
	every existing caller's behaviour. And a class whose tier the deployment named no model
	for falls through to the phase's tier rather than to another tier's model, for the
	reason a declared-but-empty tier falls through to the operator's: answering it with a
	model nobody chose is the substitution FR-132 prevents.
	"""
	env = os.environ if environ is None else environ
	if explicit is not None and explicit.strip():
		return explicit, "--model"

	if reasoning_class is not None and tiers is not None:
		class_name = class_tier(reasoning_class)
		declared = tiers.get(class_name)
		if declared is not None:
			return declared.model, f"tier:{class_name}"

	name = phase_tier(phase)
	if name is not None and tiers is not None:
		tier = tiers.get(name)
		if tier is not None:
			return tier.model, f"tier:{name}"

	if operator_model is not None and operator_model.strip():
		return operator_model, "SOFACT_MODEL"
	from_env = env.get("SOFACT_MODEL", "")
	if from_env.strip():
		return from_env, "SOFACT_MODEL"

	from sofact.llm import DEFAULT_MODEL

	return DEFAULT_MODEL, "default"


def tier_statement(tiers: Mapping[str, ModelTier]) -> str:
	"""One line saying what the tiers are, for a probe or a status report (FR-132).

	Says *unconfigured* rather than printing an empty table, for the reason the delivery
	report says *unmeasured* rather than ``0`` (NFR-024): a deployment with no tiers runs
	one model everywhere, and a blank line where the tiers should be reads as a table
	nobody filled in rather than as a decision nobody made.
	"""
	if not tiers:
		return (
			"no model tiers are configured, so every phase runs the operator's model "
			f"(set {MODEL_TIERS_ENV} to a JSON table to run P3/P4/P6 on a deeper one)"
		)
	parts: list[str] = []
	for name in sorted(tiers):
		phases = ", ".join(p.value for p in TIER_PHASES[name])
		parts.append(f"{name}={tiers[name].model} ({phases})")
	return "; ".join(parts)
