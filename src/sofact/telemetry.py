"""FR-102 — attempt telemetry.

"Build must report **attempt telemetry** (attempts, tokens, wall clock)."

The three quantities FR-102 names were already in the log before this module existed, in
two places that nothing joined. A repair attempt is a :class:`~sofact.views.RepairAttempt`
row carrying the clause, the ordinal, the diagnosis and the outcome; the session it
produced is a :class:`~sofact.views.DispatchRecord` carrying ``wall_clock_seconds``,
``tokens_observed`` and ``continuations_observed``. The roadmap audit marked the
requirement **Partly** for exactly that reason — "per-dispatch telemetry exists; the
requirement is about attempts, which are not aggregated anywhere" — and this module is
the aggregation.

**It is a pure fold.** Every input is a record the caller already read; nothing here opens
a file, runs a session, or consults a clock. That is the same contract
:mod:`sofact.escape` keeps, and for the same reason: a number that is reproducible from
the log is evidence, and a number computed from live state is a summary.

**The one thing it refuses to do is sum a ``None``.** ``DispatchRecord.tokens_observed``
is ``int | None``, and ``None`` means the harness reported no usage — *unmeasured*, never
zero (NFR-024, and :func:`sofact.harness.parse_usage` states the rule at the source). A
total that added ``None`` as zero would report a cheap build where the truth is a build
whose cost nobody observed, which is FR-118's missing qualification in arithmetic form.
So the total sums what reported and carries the count of what did not, and
:attr:`~sofact.views.AttemptTelemetryReport.tokens_complete` says whether the sum is
exact.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sofact._uuid7 import uuid7str
from sofact.tiers import step_phase
from sofact.views import (
	AttemptTelemetry,
	AttemptTelemetryReport,
	DeliveryEnvelope,
	DispatchRecord,
	GoalPlan,
	RepairAttempt,
	SpendAttribution,
	SpendReport,
	now,
)

__all__ = ["measure_attempts", "measure_spend"]


def measure_attempts(
	*,
	plan_id: str,
	repairs: Sequence[RepairAttempt],
	dispatches: Sequence[DispatchRecord],
	rendered_at: datetime | None = None,
) -> AttemptTelemetryReport:
	"""Fold a plan's repair attempts and dispatches into FR-102's three numbers.

	``repairs`` is filtered to ``plan_id`` here rather than by the caller, so a run that
	passes the whole ledger cannot accidentally report another plan's spend. That is the
	one filter this function applies: a repair attempt whose ``plan_id`` is the origin plan
	*is* this run's attempt, and :attr:`~sofact.views.RepairAttempt.revision_id` exists for
	looking the step up, not for deciding whether the attempt belongs.

	**An attempt with no dispatch is kept, and reports zero.** ``dispatch_id`` is ``None``
	on a ``NOT_COMPLETED`` attempt — the session never ran — and dropping the row would
	make "the producer never started" invisible in a report whose whole subject is what the
	run cost. It contributes one attempt, no wall clock and no tokens, and the type refuses
	any other reading.

	**A dispatch id that resolves to no record is a floor, not a failure.** The log is
	append-only and a dispatch row is written when its session ends, so an attempt whose
	dispatch is missing is a torn read rather than a corrupt ledger. It is counted as
	unmeasured — the same treatment a harness that reports no usage gets — because the
	honest answer to "what did it cost" is *nobody observed*, and inventing a zero would be
	the substitution NFR-024 forbids.
	"""
	by_id = {d.id: d for d in dispatches}
	rows: list[AttemptTelemetry] = []
	for attempt in repairs:
		if attempt.plan_id != plan_id:
			continue
		dispatch = by_id.get(attempt.dispatch_id) if attempt.dispatch_id else None
		if dispatch is None:
			rows.append(
				AttemptTelemetry(
					attempt_id=attempt.id,
					clause_ids=attempt.clause_ids,
					attempt=attempt.attempt,
					outcome=attempt.outcome,
					dispatch_id=None,
					unmeasured_tokens=1 if attempt.dispatch_id else 0,
				)
			)
			continue
		tokens = dispatch.tokens_observed
		rows.append(
			AttemptTelemetry(
				attempt_id=attempt.id,
				clause_ids=attempt.clause_ids,
				attempt=attempt.attempt,
				outcome=attempt.outcome,
				dispatch_id=dispatch.id,
				wall_clock_seconds=dispatch.wall_clock_seconds,
				tokens=tokens if tokens is not None else 0,
				unmeasured_tokens=0 if tokens is not None else 1,
			)
		)

	return AttemptTelemetryReport(
		id=uuid7str(),
		plan_id=plan_id,
		rendered_at=rendered_at if rendered_at is not None else now(),
		attempts=tuple(rows),
	)


def _bucket(
	key: str,
	records: Sequence[DispatchRecord],
) -> SpendAttribution:
	"""One spend bucket over ``records`` (FR-133).

	``tokens`` sums only what reported and ``unmeasured_tokens`` counts the rest, which is
	:class:`~sofact.views.AttemptTelemetry`'s rule stated once more rather than a second
	one: a total that added ``None`` as zero would report a cheap phase where the truth is
	a phase whose cost nobody observed (NFR-024).

	``models`` is read from ``record.model`` and never from ``argv``. The harness's own
	command line carries a ``--model`` for some harnesses and not others, so a reader
	would be parsing a producer's argv to learn something SoFact resolved itself — and for
	the harnesses that do not take the flag, the model would read as absent.
	"""
	tokens = sum(r.tokens_observed for r in records if r.tokens_observed is not None)
	unmeasured = sum(1 for r in records if r.tokens_observed is None)
	models = sorted({r.model for r in records if r.model})
	return SpendAttribution(
		key=key,
		dispatches=len(records),
		wall_clock_seconds=sum(r.wall_clock_seconds for r in records),
		tokens=tokens,
		unmeasured_tokens=unmeasured,
		models=tuple(models),
	)


def measure_spend(
	*,
	plan: GoalPlan,
	dispatches: Sequence[DispatchRecord],
	envelope: DeliveryEnvelope | None = None,
	rendered_at: datetime | None = None,
) -> SpendReport:
	"""Fold a plan's dispatches into FR-133's per-phase and per-module attribution.

	``plan`` is the plan the spend is attributed against, and it is required rather than
	optional: the phase of a dispatch is a property of the *step* it ran, and a dispatch
	row carries ``step_id`` without the step's kind. Handing this fold only the dispatches
	would leave it unable to name a phase at all — and the tempting fix, a ``phase`` field
	on :class:`~sofact.views.DispatchRecord`, would be a second place for one fact to be
	right, written at dispatch time from the same join this function already makes.

	``dispatches`` is filtered to ``plan.id`` here rather than by the caller, for
	:func:`measure_attempts`'s reason: a run handed the whole ledger must not report
	another plan's spend.

	**The phase comes from the step kind**, through :func:`~sofact.tiers.step_phase`,
	because a plan step carries no phase — P3 produced the decomposition and P5 produced
	the plan, and the two never met. That join is the whole of FR-133's first half.

	**The module comes from the checkout**, which is where FR-100 already records it.
	``None`` there is a real state — a bootstrap step covers no clause and a step spanning
	two modules belongs to neither — and those dispatches are counted in
	:attr:`~sofact.views.SpendReport.unattributed` rather than dropped, so the module
	buckets plus that count account for every row the phase buckets counted.

	**A dispatch whose step is not in the plan is a refusal, not a default.** The plan is
	the authority on what its steps are, so a row naming a step it does not hold is a torn
	read or a cross-plan leak, and attributing it to some default phase would put a
	stranger's spend in this plan's totals.
	"""
	kinds = {step.id: step.kind for step in plan.steps}
	mine: list[DispatchRecord] = []
	by_phase: dict[str, list[DispatchRecord]] = {}
	by_module: dict[str, list[DispatchRecord]] = {}
	unattributed = 0
	for record in dispatches:
		if record.plan_id != plan.id:
			continue
		kind = kinds.get(record.step_id)
		if kind is None:
			raise ValueError(
				f"dispatch {record.id} names step {record.step_id}, which plan {plan.id} "
				"does not hold; the phase of this spend cannot be derived, and guessing "
				"one would attribute it to a phase it never ran in (FR-133)"
			)
		mine.append(record)
		by_phase.setdefault(step_phase(kind).value, []).append(record)
		module = record.checkout.module if record.checkout is not None else None
		if module:
			by_module.setdefault(module, []).append(record)
		else:
			unattributed += 1

	return SpendReport(
		id=uuid7str(),
		plan_id=plan.id,
		rendered_at=rendered_at if rendered_at is not None else now(),
		by_phase=tuple(
			_bucket(key, rows) for key, rows in sorted(by_phase.items(), key=lambda kv: kv[0])
		),
		by_module=tuple(
			_bucket(key, rows) for key, rows in sorted(by_module.items(), key=lambda kv: kv[0])
		),
		envelope=envelope,
		unattributed=unattributed,
	)
