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
from sofact.views import (
	AttemptTelemetry,
	AttemptTelemetryReport,
	DispatchRecord,
	RepairAttempt,
	now,
)

__all__ = ["measure_attempts"]


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
