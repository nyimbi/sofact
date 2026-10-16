"""FR-147 — harness selection by measurement.

"Harness selection must be **empirical** — driven by measured goal-declaration precision
(§20.4) and throughput, not by reputation. D11's matrix is the selection instrument and
must be populated from probes (M0 item 6), not from vendor claims."

The matrix FR-148 populates is a *description* of each harness. Before this module
nothing read it to choose: :meth:`~sofact.service.FactoryService.harness_name` takes
``--harness``, then ``SOFACT_HARNESS``, then :data:`~sofact.service.DEFAULT_HARNESS`,
then a table of exactly one — every one of which is a declaration or a reputation, and an
ambiguous table was refused outright rather than decided. So a deployment that configured
two harnesses and probed both could not use what it had learned, which is the gap the
roadmap row names in five words: *"No selection: nothing chooses a harness from the
measurement."*

**The fold is pure and reads only rows that already exist.** Dispatches, plans, profiles,
integrity checks and verdicts; nothing here opens a file, launches a child or consults a
clock. That is :mod:`sofact.escape`'s and :mod:`sofact.telemetry`'s contract, and for the
same reason: a choice reproducible from the log is evidence, and one computed from live
state is a preference.

**Three things it refuses to do, and each is the defect it exists to prevent.**

1. **Rank an unmeasured harness.** Every rate is ``None`` with no denominator (NFR-024),
   and ``None`` is not zero — a harness nothing has judged has not scored badly, it has
   not scored. :attr:`~sofact.views.HarnessSelection.unmeasured` names them and
   :attr:`~sofact.views.HarnessSelection.discharged` is empty, so a selection made on no
   measurement claims nothing.
2. **Resolve a tie silently.** Precision and throughput are the two axes FR-147 names,
   and two harnesses equal on both are genuinely undecided by the numbers available.
   :attr:`~sofact.views.HarnessSelection.tied` reports it rather than letting the
   alphabetical tiebreak in the sort key read as a finding.
3. **Let a goal-hacker win.** §20.4 calls a contract-integrity failure "the sharpest form
   of goal-hacking", and a harness that edited its own success criteria is excluded
   outright rather than ranked lower — see
   :attr:`~sofact.views.HarnessMetric.exclusion_reason`, which orders its reasons.

**What it cannot do.** It cannot compare two harnesses on *correctness* of the work, and
it does not try: :attr:`HarnessMetric.verified_modules` counts modules whose clauses the
*verifier* satisfied, which is a fact about the modules, not about the producer. A harness
whose sessions all pass and whose modules are wrong is not a harness this instrument can
see, because SoFact's verdicts come from its own oracles and never from the producer's
report (FR-138).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from sofact._uuid7 import uuid7str
from sofact.views import (
	DispatchRecord,
	GoalPlan,
	GoalStep,
	HarnessMetric,
	HarnessProfile,
	HarnessSelection,
	IntegrityCheck,
	IntegrityOutcome,
	VerdictOutcome,
	VerificationReport,
	now,
)

__all__ = [
	"DECLARED_NOT_MEASURED",
	"NO_SELECTION",
	"measure_harnesses",
	"select_harness",
	"step_corroborated",
]


DECLARED_NOT_MEASURED = (
	"chosen by declaration rather than by measurement: this deployment named it, and "
	"nothing has been measured to compare it against (FR-147, NFR-024)"
)
"""Why a fallback happened, in one sentence, for the report and the CLI to share."""


NO_SELECTION = (
	"no harness could be selected: nothing has been measured, no harness was named, and "
	"the configured table is ambiguous — so there is no measurement to choose on and no "
	"declaration to fall back to (FR-147). Probe a harness, or name one with --harness"
)
"""The other honest ending, and it is not a failure: it is a question nobody answered."""


def step_corroborated(
	step: GoalStep,
	report: VerificationReport | None,
) -> bool:
	"""Whether the *verifier* satisfied every clause ``step`` covered (FR-143).

	The one rule :meth:`~sofact.service.FactoryService.declaration_precision` and
	:func:`measure_harnesses` both need, stated once. A step covering no clause is never
	corroborated: a bootstrap step has no verdict to confirm it, and counting vacuous
	truth as corroboration would give the least checkable step the best score.
	"""
	if not step.clause_ids or report is None:
		return False
	verdicts = {verdict.clause_id: verdict.outcome for verdict in report.verdicts}
	return all(verdicts.get(clause_id) is VerdictOutcome.SATISFIED for clause_id in step.clause_ids)


def _module_of(record: DispatchRecord) -> str | None:
	"""The module a dispatch's work belongs to, from FR-100's checkout (FR-133)."""
	return None if record.checkout is None else record.checkout.module


def measure_harnesses(
	*,
	harnesses: Sequence[str],
	dispatches: Sequence[DispatchRecord],
	plans: Sequence[GoalPlan],
	profiles: Sequence[HarnessProfile],
	integrity: Sequence[IntegrityCheck] = (),
	reports: Sequence[VerificationReport] = (),
	rendered_at: datetime | None = None,
) -> HarnessSelection:
	"""Fold the log into one §20.4 reading per configured harness (FR-147).

	``harnesses`` is every name the deployment configured, and it is an input rather than
	derived from the dispatches because a harness that has never run is exactly the one a
	reader needs to see — a report built from dispatch rows alone would omit it, and
	"absent from the report" and "excluded by FR-135" would look the same.

	``integrity`` is attributed to a harness through the **plan** its check names, not to
	the harness directly: :class:`~sofact.views.IntegrityCheck` carries no harness field,
	because FR-139's question is whether the artefacts still match what the plan pinned
	and the answer does not depend on who was asked to produce them. So a plan whose
	contract was modified charges the failure to every harness that dispatched on it,
	which can over-attribute when two harnesses worked the same plan. That direction is
	chosen deliberately: over-attribution excludes a harness that may be innocent, and
	under-attribution would let a goal-hacker stay selectable, which is the worse error.
	"""
	rendered = rendered_at if rendered_at is not None else now()
	by_id = {plan.id: plan for plan in plans}
	report_for: dict[str, VerificationReport | None] = {
		plan.id: next(
			(r for r in reversed(reports) if r.contract_id == plan.contract_id),
			None,
		)
		for plan in plans
	}
	metrics: list[HarnessMetric] = []
	for name in sorted(set(harnesses)):
		rows = [record for record in dispatches if record.harness == name]
		declarations = 0
		corroborated = 0
		continuations = 0
		unmeasured_continuations = 0
		tokens = 0
		unmeasured_tokens = 0
		wall_clock = 0.0
		modules: list[str] = []
		verified: set[str] = set()
		unverified: set[str] = set()
		touched_plans: set[str] = set()
		for record in rows:
			wall_clock += record.wall_clock_seconds
			if record.tokens_observed is None:
				unmeasured_tokens += 1
			else:
				tokens += record.tokens_observed
			if record.continuations_observed is None:
				unmeasured_continuations += 1
			else:
				continuations += record.continuations_observed
			plan = by_id.get(record.plan_id)
			if plan is not None:
				touched_plans.add(plan.id)
			module = _module_of(record)
			if module is not None and module not in modules:
				modules.append(module)
			step = None if plan is None else plan.step_by_id(record.step_id)
			ok = (
				plan is not None
				and step is not None
				and step_corroborated(step, report_for.get(plan.id))
			)
			if record.declared_complete:
				declarations += 1
				if ok:
					corroborated += 1
			if module is not None:
				(verified if ok else unverified).add(module)
		# Worst wins across a module's steps: a module one step satisfied and another left
		# unverified is not a verified module, which is the rule `_worst_verdict_per_clause`
		# states for clauses one level down.
		verified -= unverified
		profile = next((p for p in reversed(profiles) if p.name == name), None)
		metrics.append(
			HarnessMetric(
				harness=name,
				probed=profile is not None,
				supports_goal_dispatch=(
					None if profile is None else profile.supports_goal_dispatch
				),
				dispatches=len(rows),
				declarations=declarations,
				corroborated=corroborated,
				modules=tuple(sorted(modules)),
				verified_modules=tuple(sorted(verified)),
				unverified_modules=tuple(sorted(unverified)),
				continuations=continuations,
				unmeasured_continuations=unmeasured_continuations,
				tokens=tokens,
				unmeasured_tokens=unmeasured_tokens,
				wall_clock_seconds=wall_clock,
				integrity_checks=sum(
					1 for check in integrity if check.label.split(":", 1)[0] in touched_plans
				),
				integrity_failures=sum(
					1
					for check in integrity
					if check.outcome is not IntegrityOutcome.INTACT
					and check.label.split(":", 1)[0] in touched_plans
				),
			)
		)

	# The ranking lives on :class:`HarnessSelection` and is read from it here rather than
	# recomputed: two copies of a sort key are two answers to "which is best" the day one
	# of them is edited, and this module's whole job is that the answer be one number.
	undecided = HarnessSelection(
		id=uuid7str(),
		rendered_at=rendered,
		metrics=tuple(metrics),
		chosen=None,
		reason=NO_SELECTION,
	)
	best = undecided.best
	return undecided.model_copy(
		update={
			"chosen": None if best is None else best.harness,
			"reason": _why(best, metrics),
		}
	)


def _why(best: HarnessMetric | None, metrics: Sequence[HarnessMetric]) -> str:
	"""The sentence explaining a selection, naming the numbers it rested on (FR-147)."""
	if best is None:
		if not metrics:
			return "no harness is configured, so there is nothing to select"
		if not any(m.is_selectable for m in metrics):
			reasons = "; ".join(f"{m.harness}: {m.exclusion_reason}" for m in metrics)
			return f"every configured harness is excluded ({reasons})"
		return NO_SELECTION
	precision = best.precision
	rate = best.seconds_per_verified_module
	parts = [
		f"{best.harness} has the best measured goal-declaration precision of the "
		f"{sum(1 for m in metrics if m.is_measured)} measured harness(es)"
	]
	if precision is not None:
		parts.append(f"{best.corroborated}/{best.declarations} = {precision:.0%}")
	if rate is not None:
		parts.append(f"{rate:.0f}s per verified module over {len(best.verified_modules)} module(s)")
	return "; ".join(parts) + " (FR-147: precision, then throughput)"


def select_harness(
	*,
	harnesses: Sequence[str],
	dispatches: Iterable[DispatchRecord],
	plans: Sequence[GoalPlan],
	profiles: Sequence[HarnessProfile],
	integrity: Sequence[IntegrityCheck] = (),
	reports: Sequence[VerificationReport] = (),
	declared: str | None = None,
	rendered_at: datetime | None = None,
) -> HarnessSelection:
	"""Select a harness, falling back to ``declared`` only when nothing is measured.

	``declared`` is what the deployment named — ``--harness``, ``SOFACT_HARNESS`` or
	:data:`~sofact.service.DEFAULT_HARNESS` — and the precedence is **measurement first,
	declaration second**, which is FR-147 read literally: "driven by measured
	goal-declaration precision and throughput, not by reputation". A declared harness is
	not a reputation, and it is still not a measurement, so it is used only where the
	measurement has nothing to say and the report says which of the two happened.

	A ``declared`` name that is not configured is ignored rather than honoured: the
	candidate set is ``harnesses``, and choosing outside it would be a selection this
	module cannot measure or explain.
	"""
	selection = measure_harnesses(
		harnesses=harnesses,
		dispatches=list(dispatches),
		plans=plans,
		profiles=profiles,
		integrity=integrity,
		reports=reports,
		rendered_at=rendered_at,
	)
	if selection.chosen is not None or declared is None or declared not in set(harnesses):
		return selection
	return selection.model_copy(update={"chosen": declared, "reason": DECLARED_NOT_MEASURED})
