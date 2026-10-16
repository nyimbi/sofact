"""FR-172 — telling the operator, and the one line that must never be wrong.

A real notifier script, run as a real subprocess, reading a real body file. No mocks: the
phase exists so a *declared tool* carries a message to a destination the deployment chose,
and a fake adapter would test the fake rather than the protocol.

The property this module is built around is the subject line. **A notification claiming a
build while a gate is open is the worst defect this feature can have**, so the subject is
composed from ``DriverRun.terminal`` and nothing else, and the tests below assert the
literal string for each terminal state. The second property is that **``delivered`` is
derived from the exit code rather than declared** — a notifier exiting non-zero records a
row, and that row says *not delivered*.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sofact._uuid7 import uuid7str
from sofact.notify import (
	NOTIFIERS,
	NotificationRefusal,
	NotificationSpec,
	load_notification_specs,
	notifier_spec_for,
	render_subject,
)
from sofact.service import FactoryService
from sofact.views import (
	DriverOutcome,
	DriverRun,
	DriverStep,
	DriverTerminal,
	Notification,
	Phase,
)

NOTIFIER = '''\
"""A notifier: records the message it was handed, or fails."""
import sys
from pathlib import Path

mode, subject, body_path, out = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
if mode == "crash":
	sys.stderr.write("smtp refused the connection\\n")
	sys.exit(7)
out.write_text(subject + "\\n---\\n" + body_path.read_text(encoding="utf-8"), encoding="utf-8")
'''

SPEC_NAME = "synthetic-ntfy"


def write_notifier(tmp_path: Path) -> Path:
	script = tmp_path / "synthetic_notifier.py"
	script.write_text(NOTIFIER, encoding="utf-8")
	return script


def spec_for(
	tmp_path: Path,
	mode: str,
	*,
	name: str = SPEC_NAME,
	expect_exit_code: int = 0,
	message_max_chars: int = 0,
) -> NotificationSpec:
	script = write_notifier(tmp_path)
	return NotificationSpec(
		name=name,
		argv=(
			sys.executable,
			str(script),
			mode,
			"{subject}",
			"{body_path}",
			str(tmp_path / "sent.txt"),
		),
		expect_exit_code=expect_exit_code,
		message_max_chars=message_max_chars,
	)


def service_with(home: Path, spec: NotificationSpec) -> FactoryService:
	return FactoryService(home=home, llm=None, notifier=spec)


def a_run(
	*,
	terminal: DriverTerminal,
	open_gate: Phase | None = None,
	detail: str = "a detail",
) -> DriverRun:
	stamp = datetime(2026, 10, 15, tzinfo=UTC)
	return DriverRun(
		id=uuid7str(),
		goal_id=uuid7str(),
		started_at=stamp,
		ended_at=stamp,
		steps=(
			DriverStep(
				id=uuid7str(),
				phase=Phase.ELICIT,
				action="propose-answers",
				outcome=DriverOutcome.ADVANCED,
				detail=detail,
				at=stamp,
			),
		),
		terminal=terminal,
		terminal_detail=detail,
		open_gate=open_gate,
	)


# --------------------------------------------------------------------------- #
# the spec table
# --------------------------------------------------------------------------- #


def test_the_built_in_table_ships_no_notifier() -> None:
	"""Every notifier is a destination — a topic, a webhook, a phone number — so none can
	be built in without inventing one."""
	assert NOTIFIERS == {}


def test_a_spec_without_a_subject_slot_is_refused() -> None:
	with pytest.raises(AssertionError, match="must name the subject"):
		NotificationSpec(name="broken", argv=("ntfy", "publish", "{body_path}"))


def test_a_spec_without_a_body_slot_is_refused() -> None:
	"""Without it the body is written to a file nothing reads and the operator gets a
	subject alone — which reads as a message whose content was empty."""
	with pytest.raises(AssertionError, match="must name the body path"):
		NotificationSpec(name="broken", argv=("ntfy", "publish", "{subject}"))


def test_resolving_no_name_with_no_table_names_the_variable() -> None:
	with pytest.raises(NotificationRefusal, match="SOFACT_NOTIFIER_SPECS"):
		notifier_spec_for(None, {})


def test_one_configured_notifier_is_the_default(tmp_path: Path) -> None:
	"""Naming none is unambiguous when exactly one is configured."""
	spec = spec_for(tmp_path, "ok")
	assert notifier_spec_for(None, {spec.name: spec}).name == SPEC_NAME


def test_two_configured_notifiers_require_a_name(tmp_path: Path) -> None:
	"""Choosing between them would be choosing a destination the operator did not."""
	one = spec_for(tmp_path, "ok", name="a")
	two = spec_for(tmp_path, "ok", name="b")
	with pytest.raises(NotificationRefusal, match="name one explicitly"):
		notifier_spec_for(None, {"a": one, "b": two})


def test_an_unknown_notifier_name_lists_the_configured_ones(tmp_path: Path) -> None:
	with pytest.raises(NotificationRefusal, match="configured: synthetic-ntfy"):
		notifier_spec_for("nope", {SPEC_NAME: spec_for(tmp_path, "ok")})


def test_a_misspelled_spec_field_is_refused_rather_than_defaulted(tmp_path: Path) -> None:
	"""A misspelled ``is_remot`` defaulted to ``False`` would report a body as having
	stayed on this machine when it was transmitted."""
	table = tmp_path / "notifiers.json"
	table.write_text(
		'{"n": {"argv": ["x", "{subject}", "{body_path}"], "is_remot": true}}', encoding="utf-8"
	)
	with pytest.raises(ValueError, match=r"unknown field\(s\) \['is_remot'\]"):
		load_notification_specs(table)


def test_a_table_round_trips_through_a_file(tmp_path: Path) -> None:
	table = tmp_path / "notifiers.json"
	table.write_text(
		'{"notifiers": {"n": {"argv": ["x", "{subject}", "{body_path}"], "is_remote": true}}}',
		encoding="utf-8",
	)
	loaded = load_notification_specs(table)
	assert loaded["n"].is_remote is True


# --------------------------------------------------------------------------- #
# the subject: the one line that must never be wrong
# --------------------------------------------------------------------------- #


def test_a_delivered_run_says_built() -> None:
	run = a_run(terminal=DriverTerminal.DELIVERED)
	assert render_subject(run, "Ship a meter service.") == (
		"sofact: Ship a meter service. — built and verified"
	)


def test_a_run_at_a_gate_says_awaiting_and_says_not_built() -> None:
	"""The subject a run stopped at P2 must produce, asserted as a literal.

	Both halves matter: the gate is named so the operator knows what to approve, and the
	word "built" is absent so nothing on their phone reads as a finished system.
	"""
	run = a_run(terminal=DriverTerminal.GATE_OPEN, open_gate=Phase.SPECIFY)
	subject = render_subject(run, "Ship a meter service.")
	assert subject == "sofact: Ship a meter service. — awaiting P2 approval, not built"
	assert "built and verified" not in subject


def test_a_failed_run_names_the_failure() -> None:
	run = a_run(terminal=DriverTerminal.FAILED, detail="harness refused model X")
	subject = render_subject(run, "Ship a meter service.")
	assert subject == "sofact: Ship a meter service. — failed: harness refused model X"
	assert "built" not in subject


def test_every_non_delivered_terminal_avoids_the_word_built() -> None:
	"""The class, not the three instances above: no terminal but DELIVERED may claim it.

	``claims_built`` is a property of ``DriverRun`` rather than a local check, so this
	holds even if :func:`render_subject` were edited carelessly — the property it would
	have to read is false for every one of these.
	"""
	for terminal in DriverTerminal:
		if terminal is DriverTerminal.DELIVERED:
			continue
		subject = render_subject(a_run(terminal=terminal), "Ship a meter service.")
		assert "built and verified" not in subject, terminal


def test_the_subject_carries_the_operators_own_words() -> None:
	"""Truncated rather than paraphrased, and only the first line."""
	run = a_run(terminal=DriverTerminal.DELIVERED)
	long_statement = "A" * 200 + "\nand a second line nobody asked for"
	subject = render_subject(run, long_statement)
	assert subject == f"sofact: {'A' * 60} — built and verified"
	assert "second line" not in subject


# --------------------------------------------------------------------------- #
# the record
# --------------------------------------------------------------------------- #


async def test_a_delivered_notification_is_recorded_as_delivered(tmp_path: Path) -> None:
	service = service_with(tmp_path / "home", spec_for(tmp_path, "ok"))
	record = await service.notify("subject line", "the body")
	assert record.delivered
	assert record.exit_code == 0
	assert record.notifier == SPEC_NAME


async def test_the_child_received_the_subject_and_the_body(tmp_path: Path) -> None:
	"""The body travels as a *file*, so what the child read is what was digested."""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "ok"))
	await service.notify("subject line", "the body")
	written = (tmp_path / "sent.txt").read_text(encoding="utf-8")
	assert written == "subject line\n---\nthe body"


async def test_a_crashing_notifier_is_recorded_as_not_delivered(tmp_path: Path) -> None:
	"""The row is appended whether or not the process succeeded — a record written only on
	success would make "we told them" and "we meant to tell them" print the same line."""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "crash"))
	record = await service.notify("subject line", "the body")
	assert not record.delivered
	assert record.exit_code == 7
	assert record.error is not None and "smtp refused" in record.error


async def test_an_expected_non_zero_exit_is_delivered(tmp_path: Path) -> None:
	"""``delivered`` is derived from the *spec's* expectation, not from zero.

	A transport that reports success by exiting 1 is unusual and legal, and hardcoding
	zero would call every one of its messages undelivered.
	"""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "crash", expect_exit_code=7))
	record = await service.notify("subject line", "the body")
	assert record.delivered
	assert record.exit_code == 7


async def test_no_notifier_configured_records_a_row_rather_than_raising(tmp_path: Path) -> None:
	"""No notifier configured is **not** an exception: it is a recorded attempt with no
	process, which is exactly the fact the operator needs.

	A caller that raised would leave a driver run unable to say it could not tell anyone.
	"""
	service = FactoryService(home=tmp_path / "home", llm=None)
	record = await service.notify("subject line", "the body")
	assert not record.delivered
	assert record.exit_code is None
	assert record.notifier == "none"
	assert record.error is not None and "no notifier is configured" in record.error


async def test_a_launch_failure_is_recorded_not_raised(tmp_path: Path) -> None:
	"""A binary that does not exist leaves ``exit_code`` None, which is not delivered."""
	spec = NotificationSpec(
		name="ghost",
		argv=("/nonexistent/not-a-binary", "{subject}", "{body_path}"),
	)
	service = service_with(tmp_path / "home", spec)
	record = await service.notify("subject line", "the body")
	assert not record.delivered
	assert record.exit_code is None
	assert record.error is not None and "FileNotFoundError" in record.error


async def test_the_body_is_digested_and_not_stored(tmp_path: Path) -> None:
	"""A body names the system being built, and the ledger is a durable artefact.

	``body_sha256`` and ``body_chars`` make "was a notification sent, and was it this one"
	answerable without the ledger holding a client's words forever.
	"""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "ok"))
	body = "The system for Acme's internal billing."
	record = await service.notify("subject line", body)
	assert record.body_sha256 == hashlib.sha256(body.encode()).hexdigest()
	assert record.body_chars == len(body)
	# And the body text is nowhere in the log.
	log = (service.home / "ledger.jsonl").read_text(encoding="utf-8")
	assert "Acme's internal billing" not in log


async def test_a_body_over_the_transport_limit_is_truncated_before_digesting(
	tmp_path: Path,
) -> None:
	"""What is digested is what was transmitted, not what the caller composed."""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "ok", message_max_chars=10))
	record = await service.notify("subject line", "x" * 100)
	assert record.body_chars == 10
	assert record.body_sha256 == hashlib.sha256(b"x" * 10).hexdigest()


async def test_notifications_are_readable_from_the_log(tmp_path: Path) -> None:
	service = service_with(tmp_path / "home", spec_for(tmp_path, "ok"))
	await service.notify("subject line", "the body")
	recorded = await service.notifications()
	assert len(recorded) == 1
	assert recorded[0].subject == "subject line"


async def test_a_notification_needs_a_subject(tmp_path: Path) -> None:
	service = service_with(tmp_path / "home", spec_for(tmp_path, "ok"))
	with pytest.raises(AssertionError, match="needs a subject"):
		await service.notify("   ", "the body")


# --------------------------------------------------------------------------- #
# the view's own invariant
# --------------------------------------------------------------------------- #


def test_a_notification_with_no_exit_code_is_never_delivered() -> None:
	"""``None`` is the launch failure, not a silent success."""
	record = Notification(
		id=uuid7str(),
		notifier="ghost",
		subject="subject line",
		body_sha256="0" * 64,
		body_chars=1,
		exit_code=None,
		error="FileNotFoundError: no such binary",
		at=datetime(2026, 10, 15, tzinfo=UTC),
	)
	assert not record.delivered
