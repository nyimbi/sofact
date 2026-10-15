"""FR-144, FR-153 — §20.3 item 6a: forced entry, and continuations observed.

§20.3's blocking probe is one question in two halves, and the interesting part is that
both halves were already *recorded* per dispatch and read by nothing. So this suite spends
most of its effort not on the fold's arithmetic but on the two distinctions the fold exists
to keep: a goal **mode** is not a forced **entry**, and an unmeasured continuation count is
not a single turn.

Two halves, tested two ways, the shape :mod:`test_telemetry` uses. The **fold** is
exercised against :func:`sofact.goal.measure_goal_mode` directly, because the inputs it
needs — a goal dispatch whose session showed a prompt entry, a dispatch on a harness that
numbers no turns — are states a real dispatch reaches only by accident, and constructing
them is the honest way to reach them. The **verb** is exercised end to end through the
registered command against the real synthetic harness, because a reading nobody can reach
is not reported.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from synthetic import plan_and_service
from typer.testing import CliRunner, Result

from sofact.cli import app
from sofact.goal import measure_goal_mode
from sofact.views import (
	DispatchMode,
	DispatchRecord,
	GoalEntry,
	StepBudget,
	StepOutcome,
)

RUNNER = CliRunner()

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _dispatch(
	*,
	mode: DispatchMode = DispatchMode.GOAL,
	entry: GoalEntry | None = GoalEntry.PROMPT,
	continuations: int | None = 1,
	harness: str = "synthetic",
	ordinal: int = 1,
) -> DispatchRecord:
	"""One dispatch record with only the fields this fold reads set to what it reads.

	Built rather than reached into, for ``test_telemetry``'s reason: the states that matter
	here are ones a real dispatch produces by accident, and blanking a field on a real
	record to reach them would test the blanking.
	"""
	step = "0192f3a4-0000-7000-8000-000000000001"
	return DispatchRecord(
		id="0192f3a4-0000-7000-8000-0000000000ff",
		plan_id="0192f3a4-0000-7000-8000-000000000002",
		goal_id="0192f3a4-0000-7000-8000-000000000003",
		step_id=step,
		step_ordinal=ordinal,
		harness=harness,
		mode=mode,
		outcome=StepOutcome.COMPLETED,
		argv=("synthetic",),
		workspace="/tmp/ws",
		budget=StepBudget(
			max_wall_clock_seconds=60.0,
			max_continuations=4,
			max_attempts=1,
			max_tokens=None,
		),
		started_at=NOW,
		ended_at=NOW,
		wall_clock_seconds=1.0,
		goal_hash="a" * 64,
		contract_hash="b" * 64,
		goal_entry_observed=entry,
		continuations_observed=continuations,
	)


class TestAModeIsNotAnEntry:
	"""The distinction §20.3 item 6a turns on: the probe predicts, the record witnesses."""

	def test_a_goal_dispatch_with_a_prompt_entry_is_a_contradiction(self) -> None:
		report = measure_goal_mode([_dispatch()])
		assert len(report.contradictions) == 1
		assert report.forced_entries == ()

	def test_a_forced_entry_is_not_a_contradiction(self) -> None:
		row = _dispatch(entry=GoalEntry.GOAL_BEARING_SESSION)
		report = measure_goal_mode([row])
		assert report.contradictions == ()
		assert len(report.forced_entries) == 1

	def test_a_command_entry_is_forced_too(self) -> None:
		"""``COMMAND`` and ``GOAL_BEARING_SESSION`` are both forced; ``PROMPT`` is not."""
		assert GoalEntry.COMMAND.is_forced is True
		report = measure_goal_mode([_dispatch(entry=GoalEntry.COMMAND)])
		assert len(report.forced_entries) == 1

	def test_a_single_shot_dispatch_is_not_a_contradiction(self) -> None:
		"""FR-144's fallback is a *reported* degradation, not a session that lied."""
		report = measure_goal_mode(
			[_dispatch(mode=DispatchMode.SINGLE_SHOT, entry=GoalEntry.PROMPT)]
		)
		assert report.contradictions == ()
		assert report.goal_dispatches == ()

	def test_a_dispatch_with_no_record_is_unwitnessed_rather_than_a_prompt(self) -> None:
		"""``None`` is *not observed*, which is a different fact from ``PROMPT``."""
		report = measure_goal_mode([_dispatch(entry=None)])
		assert report.witnessed == ()
		assert report.forced_entries == ()
		assert report.contradictions == (), (
			"a session nobody read cannot contradict a mode — the contradiction is a "
			"claim about what the record showed, and there was no record"
		)

	def test_an_unwitnessed_dispatch_is_carried_rather_than_dropped(self) -> None:
		"""The row is kept and excluded by the denominator, not filtered at the fold.

		Filtering here would make "no goal event was found" and "no record was read"
		observationally identical, which is the pair §20.3 item 6a exists to separate. The
		row count is what says a dispatch happened and left nothing behind.
		"""
		report = measure_goal_mode([_dispatch(entry=None), _dispatch(ordinal=2)])
		assert len(report.rows) == 2, "every dispatch is carried, witnessed or not"
		assert len(report.witnessed) == 1, "only the read session is in the denominator"
		assert report.entry_forced is False, (
			"a reading with one witness is decidable, even though the other row was not"
		)

	def test_entry_forced_is_three_states_not_two(self) -> None:
		"""``False`` (read, none forced) and ``None`` (never read) must not collapse."""
		assert measure_goal_mode([_dispatch()]).entry_forced is False
		assert measure_goal_mode([_dispatch(entry=None)]).entry_forced is None
		assert measure_goal_mode([_dispatch(entry=GoalEntry.COMMAND)]).entry_forced is True


class TestContinuationsAreNotInvented:
	"""A harness that writes no turn boundary is unmeasured, never one turn."""

	def test_an_unmeasured_count_is_none_not_one(self) -> None:
		report = measure_goal_mode([_dispatch(continuations=None)])
		assert report.mean_continuations is None
		assert report.measured_continuations == ()

	def test_the_mean_is_over_the_harnesses_that_number_their_turns(self) -> None:
		report = measure_goal_mode(
			[
				_dispatch(continuations=3, harness="dsh"),
				_dispatch(continuations=1, harness="dsh", ordinal=2),
				_dispatch(continuations=None, harness="pi", ordinal=3),
			]
		)
		assert report.total_continuations == 4
		assert report.mean_continuations == 2.0

	def test_coverage_travels_beside_the_mean(self) -> None:
		"""A mean over the measurable subset is a fact about that subset (ADR-0068)."""
		report = measure_goal_mode(
			[
				_dispatch(continuations=3, harness="dsh"),
				_dispatch(continuations=None, harness="pi", ordinal=2),
				_dispatch(continuations=None, harness="pi", ordinal=3),
			]
		)
		assert report.continuation_coverage == (1, 3)

	def test_nothing_witnessed_reports_no_coverage_rather_than_a_zero_pair(self) -> None:
		"""``(0, 0)`` reads as a project that measured nothing; ``None`` says why."""
		report = measure_goal_mode([_dispatch(entry=None, continuations=None)])
		assert report.continuation_coverage is None


class TestTheReadingRefusesTheVacuousPass:
	"""A project that only ever *asked* has not discharged FR-153 (NFR-024)."""

	def test_no_forced_entry_discharges_nothing(self) -> None:
		report = measure_goal_mode([_dispatch(), _dispatch(ordinal=2)])
		assert report.discharged == ()
		assert set(report.not_implemented) == {"FR-144", "FR-153"}

	def test_one_forced_entry_discharges_both_requirements(self) -> None:
		report = measure_goal_mode([_dispatch(entry=GoalEntry.GOAL_BEARING_SESSION)])
		assert set(report.discharged) == {"FR-144", "FR-153"}
		assert report.not_implemented == ()

	def test_an_empty_history_claims_nothing(self) -> None:
		report = measure_goal_mode([])
		assert report.discharged == ()
		assert report.entry_forced is None

	def test_the_report_names_both_caveats(self) -> None:
		report = measure_goal_mode([_dispatch()])
		joined = " ".join(report.caveats)
		assert "[S21]" in joined
		assert "unmeasured" in joined

	def test_the_fold_is_pure_and_model_free(self) -> None:
		"""Same inputs, same reading: nothing here consults a clock or a process."""
		rows = [_dispatch(), _dispatch(entry=GoalEntry.COMMAND, ordinal=2)]
		first = measure_goal_mode(rows, rendered_at=NOW)
		second = measure_goal_mode(rows, rendered_at=NOW)
		assert first.rows == second.rows
		assert first.entry_forced == second.entry_forced


class TestTheGoalModeVerb:
	"""Through the registered verb, not the coroutine behind it.

	Synchronous, unlike the fold classes above, because the command body calls
	``asyncio.run`` itself: inside an ``async def`` test there is already a running loop and
	``invoke`` raises rather than reporting.
	"""

	def _run(self, home: Path) -> Result:
		return RUNNER.invoke(app, ["goalmode", "--home", str(home)])

	def test_the_verb_prints_the_reading(self, home: Path, tmp_path: Path) -> None:
		service, plan = asyncio.run(plan_and_service(home, tmp_path, "goal"))
		asyncio.run(service.dispatch_plan(plan.id))

		result = self._run(home)

		out = result.output
		assert "Traceback" not in out, out
		assert "§20.3 item 6a" in out
		assert "dispatch(es)" in out
		# The synthetic harness declares `goal/created`, so its entry is forced and the
		# reading discharges — which is the positive branch of the verb.
		assert result.exit_code == 0, out
		assert "forced entry" in out

	def test_the_verb_refuses_an_empty_history(self, home: Path) -> None:
		"""A screen showing zeros would read as an answer; it exits non-zero instead."""
		result = self._run(home)

		assert result.exit_code == 1, result.output
		assert "unmeasured rather than" in result.output
		assert "Traceback" not in result.output

	def test_an_unforced_goal_mode_exits_non_zero(self, home: Path, tmp_path: Path) -> None:
		"""The degraded mode FR-144 requires be reported must not read as a pass.

		§20.3 calls this probe blocking for the whole Mode G design, so a pipeline that
		saw exit 0 here would treat an unforced goal mode as answered.
		"""
		service, plan = asyncio.run(plan_and_service(home, tmp_path, "complete"))
		asyncio.run(service.dispatch_plan(plan.id))

		result = self._run(home)

		assert result.exit_code == 1, result.output
		assert "not discharged" in result.output
		assert "FR-153" in result.output
