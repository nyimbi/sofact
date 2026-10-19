"""The app mounts, renders, and cannot pass a gate the CLI would not.

``test_dashboard.py`` covers the facts. This covers the *app*: that it composes, that a
headless pilot can drive it, and that the one thing a terminal must not be able to do —
pass a gate whose machine half failed — is refused at both layers.

Headless rather than a subprocess against a real terminal: ``App.run_test`` mounts the
same app the operator sees and drives it through the same message pump, so a widget
lookup that would fail on a real screen fails here. The alternative, asserting on the
source, would be a test of a copy of the code rather than of the code.

Every test gets its own ``tmp_path`` service. The TUI writes to the log through the same
service methods the CLI does, so a test that shared a state directory would be testing
whichever ran first.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from textual.widgets import DataTable, Input, RichLog, Static, TabbedContent

from sofact.service import FactoryService
from sofact.tui import SoFactApp
from sofact.views import GateCheck, Phase, PhaseStatus

_GOOD = GateCheck(name="criteria_are_machine_checkable", passed=True, detail="6 of 6")
_BAD = GateCheck(
	name="criteria_are_machine_checkable",
	passed=False,
	detail="0 of 6: no criterion names a command",
)


async def _stopped(service: FactoryService, check: GateCheck) -> None:
	await service.start("a service that reports uptime")
	await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE, checks=(check,))


async def test_the_app_mounts_and_reads_the_log(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		assert app.snapshot is not None
		summary = app.query_one("#summary", Static)
		assert "no goal yet" in str(summary.content)


async def test_the_phase_table_lists_every_phase(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		table = cast("DataTable[str]", app.query_one("#phase-table", DataTable))
		assert table.row_count == len(Phase)


async def test_an_open_gate_is_drawn_with_its_checks(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	await _stopped(service, _GOOD)
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		box = app.query_one("#gate-box", Static)
		text = str(box.content)
		assert "specification gate" in text
		assert _GOOD.name in text
		assert "press g to approve" in text


async def test_a_failed_gate_says_approval_is_refused(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	await _stopped(service, _BAD)
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		text = str(app.query_one("#gate-box", Static).content)
		assert "approval is refused" in text
		assert "press g to approve" not in text


async def test_the_approve_key_does_not_open_a_modal_on_a_failed_gate(
	tmp_path: Path,
) -> None:
	"""The UI half of the invariant. The service half is asserted below it."""
	service = FactoryService(home=tmp_path / "state", llm=None)
	await _stopped(service, _BAD)
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		await pilot.press("g")
		await pilot.pause()
		assert len(app.screen_stack) == 1, "no modal: there is nothing this person may approve"
		assert (await service.state()).phase_status(Phase.SPECIFY) is PhaseStatus.AWAITING_GATE


async def test_the_approve_key_opens_a_modal_when_the_machine_half_passed(
	tmp_path: Path,
) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	await _stopped(service, _GOOD)
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		await pilot.press("g")
		await pilot.pause()
		assert len(app.screen_stack) == 2


async def test_typing_a_name_approves_the_gate_and_records_it(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	await _stopped(service, _GOOD)
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		await pilot.press("g")
		await pilot.pause()
		await pilot.press(*"alice")
		await pilot.press("enter")
		await pilot.pause()
		await pilot.pause()

		assert len(app.screen_stack) == 1
		advance = (await service.state()).phase_advance(Phase.SPECIFY)
		assert advance is not None
		assert advance.status is PhaseStatus.COMPLETE
		assert advance.approved_by == "alice", "an approval names the person who gave it"
		assert app.snapshot is not None and app.snapshot.gate is None


async def test_the_service_refuses_a_failed_gate_even_if_the_ui_is_bypassed(
	tmp_path: Path,
) -> None:
	"""The invariant is the service's, not the screen's.

	Asserted by calling the method the modal's callback calls, directly. A guard that
	exists only in the renderer is a guard a second front end would not have.
	"""
	service = FactoryService(home=tmp_path / "state", llm=None)
	await _stopped(service, _BAD)
	refused = False
	try:
		await service.approve_gate(Phase.SPECIFY, by="alice")
	except ValueError:
		refused = True
	assert refused, "approval cannot make an unsound artefact sound (FR-061)"
	assert (await service.state()).phase_status(Phase.SPECIFY) is PhaseStatus.AWAITING_GATE


async def test_the_answer_key_opens_the_question_modal(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	await service.start("a service that reports uptime")
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		assert app.snapshot is not None and app.snapshot.question is not None
		await pilot.press("a")
		await pilot.pause()
		assert len(app.screen_stack) == 2
		# The modal is its own screen, so the input is on ``app.screen`` rather than on
		# the default one ``app.query_one`` searches.
		assert app.screen.query_one(Input).placeholder


async def test_an_answer_typed_into_the_modal_is_recorded(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	await service.start("a service that reports uptime")
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		dimension = app.snapshot.question[0]  # type: ignore[index]
		await pilot.press("a")
		await pilot.pause()
		await pilot.press(*"an uptime page that turns red")
		await pilot.press("enter")
		await pilot.pause()
		await pilot.pause()

		answers = (await service.state()).answers_for(app.snapshot.goal.id)  # type: ignore[union-attr]
		assert any(a.dimension is dimension for a in answers)


async def test_the_ledger_tab_lists_the_entries(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	await service.start("a service that reports uptime")
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		table = cast("DataTable[str]", app.query_one("#ledger-table", DataTable))
		assert table.row_count == len(await service.entries())


async def test_the_runs_tab_says_so_when_there_is_no_run(tmp_path: Path) -> None:
	service = FactoryService(home=tmp_path / "state", llm=None)
	app = SoFactApp(service)
	async with app.run_test(size=(120, 40)) as pilot:
		await pilot.pause()
		# ``RichLog.write`` defers until the widget renders, and a tab that is not the
		# active one never renders. Switching to it is part of the test: the claim is
		# about what an operator sees on the runs tab, not about a queue behind it.
		tabs = app.query_one(TabbedContent)
		tabs.active = "tab-runs"
		await pilot.pause()
		log = app.query_one("#run-log", RichLog)
		assert log.lines, "the tab says so rather than showing nothing"
