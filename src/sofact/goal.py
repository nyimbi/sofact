"""FR-144, FR-153 — §20.3 item 6a: was goal entry *forced*, and were continuations seen?

§20.3's M0 item 6a is the probe the whole delegated-P5 design rests on, and §20.3 states
what is still open in its own words:

	What remains open is not whether the capability exists but whether entry can be
	**forced** and continuations observed.

The capability question was answered by [S21] and is recorded on the adapter: `dsh`'s
`goal` package is present and loaded, and in a live unattended run the producer never
entered it — zero goal-typed events, `todo_write` substituted, one turn, `finish_reason:
completed`. So goal mode is *available and model-discretionary*, which is why
:class:`~sofact.views.GoalEntry` ranks its mechanisms by forcefulness and why
:attr:`~sofact.views.DispatchRecord.capability_loss` reports a single-shot run rather than
letting the plan appear honoured.

**Why this module exists.** Two fields carried the answer per dispatch and nothing read
them. `DispatchRecord.goal_entry_observed` and `DispatchRecord.continuations_observed` were
written by the adapter, asserted in one test each, and referenced nowhere in `src/` — the
"written and never read" defect, where a field is collected and no reader ever fails. So
the M0 question had an answer in the log that no surface could state, and this is the fold
that states it.

**It is a pure fold**, the contract :mod:`sofact.telemetry` and :mod:`sofact.escape` both
keep: every input is a record the caller already read, and nothing here opens a file, runs
a session, or consults a clock. A number reproducible from the log is evidence; one
computed from live state is a summary.

**The two things it refuses.** It will not read a goal *mode* as evidence of goal *entry* —
the mode is the probe's prediction, made before the session started, and the entry is what
the record shows afterwards; a project whose goal dispatches all carried a prompt entry has
not exercised the capability FR-153 requires, and :attr:`GoalModeReport.discharged` says so
by returning nothing. And it will not round an unmeasured continuation count to `1` —
`pi`, `claude` and `opencode` declare no turn boundary, so their dispatches are
*unmeasured*, and a mean that treated them as single-turn would report the cheapest
possible goal behaviour as the observed one (NFR-024).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sofact._uuid7 import uuid7str
from sofact.views import (
	DispatchRecord,
	GoalModeReport,
	GoalModeRow,
	now,
)

__all__ = ["measure_goal_mode"]


def measure_goal_mode(
	dispatches: Sequence[DispatchRecord],
	*,
	rendered_at: datetime | None = None,
) -> GoalModeReport:
	"""Fold a project's dispatches into §20.3 item 6a's two answers.

	Every dispatch is carried, including the ones that were never sent — a refusal has a
	mode and no entry, and dropping it would make "the probe found the harness unusable"
	invisible in a report whose subject is whether the harness could run a goal at all.
	The rows that were never *witnessed* are counted and excluded from the denominator by
	:attr:`~sofact.views.GoalModeReport.witnessed` rather than filtered here, so the
	difference between "no goal event was found" and "no record was read" survives into the
	report instead of being erased at the fold.

	Order is log order, which is dispatch order, so a project that began by asking and
	later forced entry reads as that sequence rather than as an unordered set of facts.
	"""
	rows = tuple(
		GoalModeRow(
			dispatch_id=record.id,
			step_id=record.step_id,
			harness=record.harness,
			mode=record.mode,
			entry=record.goal_entry_observed,
			continuations=record.continuations_observed,
		)
		for record in dispatches
	)

	return GoalModeReport(
		id=uuid7str(),
		rendered_at=rendered_at if rendered_at is not None else now(),
		rows=rows,
	)
