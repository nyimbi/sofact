"""The terminal interface: the pipeline, the ledger and the next move, on one screen.

``sofact tui`` opens a dashboard over a project's state directory. It shows the same
facts ``sofact status``, ``sofact phase`` and ``sofact ledger`` print, arranged so that
the one question an operator has at any moment — *what do I do next* — is answered
without scrolling.

**What this is not.** It is not a second surface with its own policy. Every fact on the
screen comes from :func:`sofact.dashboard.read_snapshot`, which folds the log the same
way the CLI does, and the only things the app can *do* are the two acts §3.3 keeps
human: answering an elicitation question, and approving a gate a person has read. It
cannot pass a gate on its own — the approve action is a person's keypress naming
themselves, and :meth:`~sofact.service.FactoryService.approve_gate` refuses a failed
machine check regardless of who asked. Nor can it drive the pipeline: ``b`` runs
:func:`sofact.driver.run_goal`, which stops at every gate by construction, and there is
no call to ``approve_gate`` anywhere in the driver.

**Why a snapshot rather than the app reading the service.** The screen's content is
testable without a terminal (``tests/ci/test_dashboard.py``), and this module's claims
are then about layout only. An app that folded the log itself would put the
"what is the next move" logic where nothing can reach it without a headless terminal.

**Refresh is explicit and never silent.** The log is append-only and every mutation
lands as a row, so a stale screen is a screen showing a log that has moved. ``r``
re-reads; every action re-reads after it commits. There is no timer, because a factory
whose state changes on a human's keystroke does not need a poll and a poll would make a
quiet project look busy.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
	DataTable,
	Footer,
	Header,
	Input,
	Label,
	RichLog,
	Static,
	TabbedContent,
	TabPane,
)

from sofact.dashboard import DASHBOARD_TITLE, Snapshot, read_snapshot
from sofact.driver import DriverRefusal, run_goal
from sofact.service import FactoryService
from sofact.views import DriverTerminal, ElicitationDimension, Phase, PhaseStatus

__all__ = ["SoFactApp", "run_tui"]

_MARK: dict[PhaseStatus, str] = {
	PhaseStatus.COMPLETE: "✓",
	PhaseStatus.ACTIVE: "▶",
	PhaseStatus.AWAITING_GATE: "‖",
	PhaseStatus.PENDING: "·",
}
"""The phase markers ``sofact phase`` prints, so the two surfaces agree on the glyphs."""

_GATE_COLOUR = "yellow"
"""The one colour this module names. Everything else is a Textual default, because a
theme is a deployment's choice and hard-coding a palette makes the screen unreadable on
the next terminal."""


def _table(app: SoFactApp, selector: str) -> DataTable[str]:
	"""The table at ``selector``, typed.

	``query_one(selector, DataTable[str])`` reads as the obvious spelling and is a
	runtime failure: Textual uses the expected type in an ``isinstance`` check, and a
	subscripted generic cannot be passed to one. The cast says the same thing to the type
	checker without reaching the call.
	"""
	return cast(DataTable[str], app.query_one(selector, DataTable))


class _QuestionModal(ModalScreen[str | None]):
	"""Ask for one elicitation answer, and return it or ``None`` if dismissed.

	A modal rather than an inline input, because the question carries a rationale the
	operator should read before typing and a modal can show both without the phase panel
	reflowing under it.
	"""

	BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "cancel")]

	def __init__(self, dimension: str, question: str, rationale: str) -> None:
		super().__init__()
		self._dimension = dimension
		self._question = question
		self._rationale = rationale

	def compose(self) -> ComposeResult:
		with Container(id="question-box"):
			yield Label(self._dimension, id="question-dimension")
			yield Static(self._question, id="question-text")
			yield Static(self._rationale, id="question-rationale")
			yield Input(placeholder="your answer, in your own words", id="answer-input")
			yield Static("enter to record · escape to cancel", id="question-hint")

	def on_mount(self) -> None:
		self.query_one("#answer-input", Input).focus()

	def on_input_submitted(self, event: Input.Submitted) -> None:
		self.dismiss(event.value.strip() or None)

	def action_cancel(self) -> None:
		self.dismiss(None)


class SoFactApp(App[None]):
	"""The dashboard. One project, one state directory, no hidden state."""

	TITLE = DASHBOARD_TITLE
	SUB_TITLE = "the pipeline, the ledger, and what to type next"

	CSS = (
		"""
	Screen { layout: vertical; }
	#summary { height: auto; padding: 1 2; background: $panel; }
	#next-move { color: $accent; text-style: bold; }
	#gate-box { height: auto; padding: 1 2; border: round """
		+ _GATE_COLOUR
		+ """; }
	#phase-list { height: auto; }
	#readiness { height: auto; }
	TabbedContent { height: 1fr; }
	DataTable { height: 1fr; }
	#question-box {
		width: 80; height: auto; padding: 1 2;
		border: round $accent; background: $panel;
	}
	#question-dimension { text-style: bold; color: $accent; }
	#question-rationale { color: $text-muted; }
	#question-hint { color: $text-muted; }
	"""
	)

	BINDINGS: ClassVar[list[BindingType]] = [
		Binding("q", "quit", "quit"),
		Binding("r", "refresh", "refresh"),
		Binding("a", "answer", "answer"),
		Binding("g", "approve", "approve gate"),
		Binding("b", "build", "run"),
		Binding("tab", "next_tab", "next tab", show=False),
	]

	def __init__(self, service: FactoryService) -> None:
		super().__init__()
		self._service = service
		self.snapshot: Snapshot | None = None

	# ----------------------------------------------------------------- composition

	def compose(self) -> ComposeResult:
		yield Header()
		with VerticalScroll(id="phase-list"):
			yield Static("reading the log…", id="summary")
			yield Static("", id="next-move")
			yield Static("", id="gate-box")
			yield Static("", id="readiness")
		with TabbedContent(initial="tab-phases"):
			with TabPane("phases", id="tab-phases"), Vertical():
				yield DataTable(id="phase-table")
			with TabPane("ledger", id="tab-ledger"):
				yield DataTable(id="ledger-table")
			with TabPane("runs", id="tab-runs"):
				yield RichLog(id="run-log", wrap=True, markup=False)
		yield Footer()

	async def on_mount(self) -> None:
		table = _table(self, "#phase-table")
		table.add_columns("phase", "status", "gate")
		ledger = _table(self, "#ledger-table")
		ledger.add_columns("index", "at", "kind", "hash")
		await self.refresh_snapshot()

	# ---------------------------------------------------------------------- reading

	async def refresh_snapshot(self) -> None:
		"""Re-read the log and repaint. The only path from the service to the screen."""
		snapshot = await read_snapshot(self._service)
		self.snapshot = snapshot
		self._paint(snapshot)

	def _paint(self, snapshot: Snapshot) -> None:
		summary = self.query_one("#summary", Static)
		if snapshot.goal is None:
			summary.update(
				f"no goal yet in {snapshot.home}\n"
				"run `sofact` to start an interrogation, or press a to answer one"
			)
		else:
			done, total = snapshot.readiness_progress
			chain = "intact" if snapshot.chain.ok else f"BROKEN at {snapshot.chain.broken_at}"
			summary.update(
				f"goal   {snapshot.goal.id}\n"
				f"       {snapshot.goal.statement}\n"
				f"phase  {snapshot.phase.value} {snapshot.phase.name.lower()}\n"
				f"readiness {done}/{total}   ledger {snapshot.ledger_length} entries, {chain}"
			)

		next_move = self.query_one("#next-move", Static)
		next_move.update(f"next:  {snapshot.next_move}")

		gate_box = self.query_one("#gate-box", Static)
		if snapshot.gate is None:
			gate_box.display = False
		else:
			gate_box.display = True
			lines = [
				f"stopped at the {snapshot.gate.gate.value} gate ({snapshot.gate.phase.value})",
				"no machine work downstream of an unapproved gate (FR-061)",
				"",
			]
			if not snapshot.gate.checks:
				lines.append("nothing has been presented to approve yet (FR-080)")
			for check in snapshot.gate.checks:
				lines.append(f"  {'✓' if check.passed else '✗'} {check.name}: {check.detail}")
			lines.append("")
			lines.append(
				"press g to approve, as yourself"
				if snapshot.gate.can_approve
				else "approval is refused until the machine half passes"
			)
			gate_box.update("\n".join(lines))

		readiness = self.query_one("#readiness", Static)
		if not snapshot.readiness:
			readiness.display = False
		else:
			readiness.display = True
			lines = [f"readiness {snapshot.readiness_progress[0]}/{snapshot.readiness_progress[1]}"]
			for status in snapshot.readiness:
				lines.append(f"  {'✓' if status.resolved else '✗'} {status.dimension.value}")
				for reason in status.reasons:
					lines.append(f"      {reason}")
			if snapshot.unattested:
				lines.append(f"  {snapshot.unattested} proposal(s) await your reading (FR-173)")
			readiness.update("\n".join(lines))

		table = _table(self, "#phase-table")
		table.clear()
		for row in snapshot.phases:
			table.add_row(
				f"{_MARK[row.status]} {row.phase.value} {row.phase.name.lower()}",
				row.status.value,
				row.gate.value if row.gate is not None else "",
			)

		ledger = _table(self, "#ledger-table")
		ledger.clear()
		for entry in snapshot.entries:
			ledger.add_row(
				str(entry.index),
				entry.at.isoformat(timespec="seconds"),
				entry.kind.value,
				entry.entry_hash[:12],
			)

		run_log = self.query_one("#run-log", RichLog)
		run_log.clear()
		if snapshot.run is None:
			run_log.write("no driver run recorded in this log")
		else:
			run = snapshot.run
			run_log.write(f"run {run.id}  {run.started_at.isoformat(timespec='seconds')}")
			run_log.write(f"terminal  {run.terminal.value}: {run.terminal_detail}")
			if run.next_human_verb is not None:
				run_log.write(f"next      {run.next_human_verb}")
			if run.gate_failures:
				run_log.write(f"failed    {', '.join(run.gate_failures)}")
			run_log.write("")
			for step in run.steps:
				run_log.write(f"  {step.phase.value}  {step.action:<24} {step.outcome.value}")
				run_log.write(f"       {step.detail}")

	# ---------------------------------------------------------------------- actions

	async def action_refresh(self) -> None:
		await self.refresh_snapshot()
		self.notify("re-read the log")

	def action_answer(self) -> None:
		"""Open the questionnaire at the next unresolved dimension (FR-064).

		Callback style rather than ``push_screen_wait``: the awaited form requires an
		active worker, and an action handler is not one. The callback runs when the modal
		dismisses, which is also where the answer belongs — it is the operator's act, and
		the write happens where the person's words arrive.
		"""
		snapshot = self.snapshot
		if snapshot is None or snapshot.goal is None:
			self.notify("no goal yet: run `sofact` to start one", severity="warning")
			return
		if snapshot.question is None:
			self.notify("every dimension is resolved", severity="information")
			return
		dimension, question, rationale = snapshot.question
		goal_id = snapshot.goal.id
		self.push_screen(
			_QuestionModal(dimension.value, question, rationale),
			lambda answer: self._record_answer(goal_id, dimension, answer),
		)

	async def _record_answer(
		self, goal_id: str, dimension: ElicitationDimension, answer: str | None
	) -> None:
		if answer is None:
			return
		await self._service.answer(goal_id, dimension, answer)
		await self.refresh_snapshot()
		self.notify(f"recorded an answer to {dimension.value}")

	def action_approve(self) -> None:
		"""Pass the open gate, naming the operator (FR-061).

		The person is asked for their name rather than defaulting to ``"operator"``: an
		approval is attributed in the log and an unattributed one is a row nobody is
		accountable for. The service still decides — a failed machine check refuses this
		call regardless of what was typed — so this action cannot pass a gate the CLI
		would not, and that is the invariant rather than a nicety.
		"""
		snapshot = self.snapshot
		if snapshot is None or snapshot.gate is None:
			self.notify("no gate is open", severity="information")
			return
		gate = snapshot.gate
		if not gate.can_approve:
			self.notify(
				f"the {gate.gate.value} gate has not passed its machine checks",
				severity="error",
			)
			return
		self.push_screen(
			_QuestionModal(
				f"approve {gate.gate.value}",
				f"Pass {gate.phase.value}'s {gate.gate.value} gate?",
				"This is recorded against your name. Type it to approve, escape to cancel.",
			),
			lambda by: self._record_approval(gate.phase, gate.gate.value, by),
		)

	async def _record_approval(self, phase: Phase, gate_name: str, by: str | None) -> None:
		"""Pass the gate the operator named themselves at.

		The service decides, not this method: ``approve_gate`` recomputes the machine
		half and refuses a failed check whatever was typed, so a person cannot type their
		way past an unsound artefact here any more than on the CLI.
		"""
		if not by:
			return
		try:
			await self._service.approve_gate(phase, by=by)
		except ValueError as exc:
			self.notify(f"cannot approve: {exc}", severity="error")
			return
		await self.refresh_snapshot()
		self.notify(f"{gate_name} approved by {by}")

	@work(exclusive=True)
	async def action_build(self) -> None:
		"""Run the driver as far as the gates allow (FR-172).

		``run_goal`` stops at every gate by construction, so this cannot carry the
		pipeline past a human act. It is here because an operator watching a run is the
		one thing a terminal shows that a log file does not.
		"""
		snapshot = self.snapshot
		if snapshot is None or snapshot.goal is None:
			self.notify("no goal to run", severity="warning")
			return
		run_log = self.query_one("#run-log", RichLog)
		run_log.write("running…")
		self.notify("running the driver; it stops at every gate")
		try:
			run = await run_goal(self._service, notify=False)
		except DriverRefusal as exc:
			self.notify(f"refused: {exc}", severity="error")
			return
		await self.refresh_snapshot()
		if run.terminal is DriverTerminal.DELIVERED:
			self.notify("delivered")
		else:
			self.notify(f"stopped: {run.terminal.value}", severity="warning")


def run_tui(service: FactoryService, *, home: Path | None = None) -> None:
	"""Open the dashboard over ``service``.

	``home`` is accepted and ignored beyond the title, so the caller passes what the CLI
	already resolved rather than the app re-deriving a state directory — the two spellings
	of ``--home`` disagreeing is the defect ``_home_of`` exists to prevent one surface over.
	"""
	del home
	SoFactApp(service).run()
