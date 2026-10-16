"""FR-172 — a notification is a record, and one that was not sent is not a notification.

There is no notification surface anywhere else in this product: the ledger is an event log
with no subscriber, and the machine API publishes state on request rather than pushing it.
So this is new construction, and the shape it takes is the one the rest of the tree already
uses for an external tool — an argv template in a JSON table, resolved by name, launched as a
child process, judged by its exit code.

**The row is written whether or not a process launched.** That is the whole design. A record
written only on success makes "we told them" and "we meant to tell them" print the same line,
and the second is the one worth knowing about: an operator who was not told has to be able to
find that out from the log rather than from the absence of a row. ``delivered`` is therefore
*derived* from the exit code and never declared, and ``exit_code is None`` is never delivered.

**The body is digested, not stored.** A notification body names the system being built, and
the ledger is a durable artefact that outlives the conversation; ``body_sha256`` and
``body_chars`` make "was a notification sent, and was it this one" answerable without the log
holding a client's words forever. The subject is stored, because it is short, it is composed
from the run's terminal state rather than from free text, and it is what the operator
actually received.

**The subject says which terminal state, and it is composed from that state and nothing
else.** A notification reading "built" while a gate is open is the worst defect this feature
can have, so the sentence is not assembled from any field a caller supplies.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Final, TypeGuard, cast

from sofact._uuid7 import uuid7str
from sofact.views import DriverRun, DriverTerminal, Notification, now

__all__ = [
	"NOTIFIERS",
	"ConfiguredNotifierAdapter",
	"NotificationRefusal",
	"NotificationSpec",
	"load_notification_specs",
	"notifier_spec_for",
	"render_subject",
]

NOTIFIERS: Final[dict[str, NotificationSpec]] = {}
"""The built-in table, empty for the same reason :data:`~sofact.transcribe.TRANSCRIBERS` is.

Every notifier is a deployment's choice — a topic name, a webhook URL, a phone number — so
none can be built in without inventing a destination. A deployment registers its own with
``SOFACT_NOTIFIER_SPECS``.
"""


class NotificationRefusal(Exception):
	"""A notifier could not be resolved or launched. Never a silent success."""


@dataclass(frozen=True, slots=True)
class NotificationSpec:
	"""A deployment's notification configuration (FR-172).

	``argv`` carries ``{subject}`` and ``{body_path}``, and the body travels as a **file**
	rather than as an argv element. That is not a convenience: a body is multi-line prose, and
	a multi-line argument in an argv is one quoting mistake away from a shell injection or a
	truncated message. Writing it to a file the child reads removes the class.
	"""

	name: str
	argv: tuple[str, ...]
	"""How to send, as a template. ``{subject}`` and ``{body_path}`` are the slots."""

	expect_exit_code: int = 0
	is_remote: bool = False
	"""Whether the body leaves this machine.

	Recorded so a report can say whether a client's system name was transmitted, which is a
	fact an operator is entitled to and which no other field carries.
	"""

	message_max_chars: int = 0
	"""The transport's limit, or ``0`` for none. The body is truncated to it and the record
	says it was."""

	notes: str = ""

	def __post_init__(self) -> None:
		assert self.name.strip(), "a notifier spec names itself"
		assert self.argv, "a notifier spec names the command it runs"
		joined = " ".join(self.argv)
		assert "{subject}" in joined, (
			f"the {self.name} argv must name the subject, or the message arrives with no "
			"indication of which run it is about"
		)
		assert "{body_path}" in joined, (
			f"the {self.name} argv must name the body path, or the body is written to a file "
			"nothing reads and the operator receives a subject alone"
		)

	@classmethod
	def from_mapping(cls, name: str, payload: Mapping[str, object]) -> NotificationSpec:
		"""Build a spec from a JSON-shaped mapping, refusing unknown fields by name.

		A misspelled ``is_remot`` that silently fell back to ``False`` would report a body as
		having stayed on this machine when it was transmitted, which is worse than an error.
		"""
		declared = {field.name for field in fields(cls)}
		unknown = sorted(set(payload) - declared)
		if unknown:
			raise ValueError(f"notifier {name!r}: unknown field(s) {unknown}")
		if "argv" not in payload:
			raise ValueError(f"notifier {name!r}: missing field(s) ['argv']")
		changes: dict[str, object] = {"name": name}
		if "notes" in payload:
			changes["notes"] = _text(payload["notes"], "notes", name)
		for field in ("expect_exit_code", "message_max_chars"):
			if field in payload:
				changes[field] = _int(payload[field], field, name)
		if "is_remote" in payload:
			value = payload["is_remote"]
			if not isinstance(value, bool):
				raise ValueError(f"notifier {name!r}: is_remote must be a boolean")
			changes["is_remote"] = value
		changes["argv"] = _texts(payload["argv"], "argv", name)
		return cls(**changes)  # pyright: ignore[reportArgumentType]


def _text(value: object, field: str, name: str) -> str:
	if not isinstance(value, str):
		raise ValueError(f"notifier {name!r}: {field} must be a string")
	return value


def _int(value: object, field: str, name: str) -> int:
	if isinstance(value, bool) or not isinstance(value, int):
		raise ValueError(f"notifier {name!r}: {field} must be an integer")
	return value


def _texts(value: object, field: str, name: str) -> tuple[str, ...]:
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError(f"notifier {name!r}: {field} must be an array of strings")
	items = cast("Sequence[object]", value)
	out: list[str] = []
	for item in items:
		if not isinstance(item, str):
			raise ValueError(f"notifier {name!r}: {field} must contain only strings")
		out.append(item)
	return tuple(out)


def _str_keyed(value: object) -> TypeGuard[Mapping[str, object]]:
	if not isinstance(value, dict):
		return False
	obj = cast("Mapping[object, object]", value)
	return all(isinstance(key, str) for key in obj)


def load_notification_specs(path: Path) -> dict[str, NotificationSpec]:
	"""Read a notifier table from a JSON file (FR-172).

	Two shapes, as :func:`~sofact.harness.load_specs` accepts: ``{"notifiers": {...}}`` and a
	bare ``{name: {...}}``.
	"""
	try:
		text = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read notifier table {path}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{path}: not valid JSON: {exc}") from exc
	if not _str_keyed(raw):
		raise ValueError(f"{path}: expected a JSON object")
	body: object = raw["notifiers"] if set(raw) == {"notifiers"} else raw
	if not _str_keyed(body):
		raise ValueError(f"{path}: expected an object of notifier specs under 'notifiers'")
	specs: dict[str, NotificationSpec] = {}
	for name, payload in body.items():
		if not _str_keyed(payload):
			raise ValueError(f"{path}: notifier {name!r} must be an object")
		specs[name] = NotificationSpec.from_mapping(name, payload)
	if not specs:
		raise ValueError(f"{path}: no notifiers; an empty table names no way to reach anyone")
	return specs


def notifier_spec_for(name: str | None, specs: Mapping[str, NotificationSpec]) -> NotificationSpec:
	"""Resolve one notifier by name, refusing an unknown one by name."""
	if not specs:
		raise NotificationRefusal(
			"no notifier is configured, and this build ships none: set SOFACT_NOTIFIER_SPECS "
			"to a JSON table naming one, or SOFACT_NOTIFIER to a name in such a table (FR-172)"
		)
	if name is None:
		if len(specs) == 1:
			return next(iter(specs.values()))
		known = ", ".join(sorted(specs))
		raise NotificationRefusal(
			f"{len(specs)} notifiers are configured ({known}); name one explicitly"
		)
	if name not in specs:
		known = ", ".join(sorted(specs))
		raise NotificationRefusal(f"unknown notifier {name!r}; configured: {known}")
	return specs[name]


def render_subject(run: DriverRun, goal_statement: str) -> str:
	"""The one-line subject, composed from the run's terminal state (FR-172).

	Every branch reads ``run.terminal`` and nothing else decides the verb. The statement is
	truncated into the subject rather than paraphrased, so what the operator reads is their
	own words.

	``claims_built`` is the only thing that may produce the word "built", and it is a
	property of :class:`~sofact.views.DriverRun` that is true for ``DELIVERED`` alone — so a
	run stopped at a gate cannot reach that sentence even if this function were edited
	carelessly, because the property it would have to read is false.
	"""
	head = goal_statement.strip().splitlines()[0][:60] if goal_statement.strip() else "a goal"
	if run.claims_built:
		return f"sofact: {head} — built and verified"
	if run.terminal is DriverTerminal.GATE_OPEN:
		gate = run.open_gate.value.upper() if run.open_gate is not None else "a gate"
		return f"sofact: {head} — awaiting {gate} approval, not built"
	if run.terminal is DriverTerminal.RETURNED_TO_P0:
		# FR-068's stop, and it is not a failure: the evidence withdrew a premise, so the
		# system is not built and the reason is a *finding* rather than a fault. Worded as
		# the requirement words its action, because the operator's next move is a revision
		# and a subject reading "failed" would send them looking for a broken thing.
		return f"sofact: {head} — returned to P0: the evidence contradicted a premise, not built"
	return f"sofact: {head} — {run.terminal.value}: {run.terminal_detail[:80]}"


@dataclass(frozen=True, slots=True)
class ConfiguredNotifierAdapter:
	"""Sends one notification through a declared notifier and records the attempt (FR-172)."""

	spec: NotificationSpec

	def build_argv(self, subject: str, body_path: Path) -> tuple[str, ...]:
		"""The argv to launch, with the slots filled and nothing else substituted."""
		return tuple(
			part.replace("{subject}", subject).replace("{body_path}", str(body_path))
			for part in self.spec.argv
		)

	async def send(
		self,
		*,
		subject: str,
		body: str,
		workdir: Path,
		timeout: float = 60.0,
		goal_id: str | None = None,
		run_id: str | None = None,
	) -> Notification:
		"""Send one notification and record what happened, including not having sent it.

		The body is written to a file under ``workdir`` before launch and truncated to the
		spec's limit first, so what is digested is what was actually transmitted rather than
		what the caller composed.
		"""
		workdir.mkdir(parents=True, exist_ok=True)
		sent_body = body
		if self.spec.message_max_chars and len(sent_body) > self.spec.message_max_chars:
			sent_body = sent_body[: self.spec.message_max_chars]
		body_path = workdir / f"notification-{uuid7str()}.txt"
		body_path.write_text(sent_body, encoding="utf-8")
		digest = hashlib.sha256(sent_body.encode("utf-8")).hexdigest()
		argv = self.build_argv(subject, body_path)
		common: dict[str, object] = {
			"goal_id": goal_id,
			"run_id": run_id,
			"notifier": self.spec.name,
			"argv": argv,
			"subject": subject,
			"body_sha256": digest,
			"body_chars": len(sent_body),
			"expect_exit_code": self.spec.expect_exit_code,
		}
		try:
			proc = await asyncio.create_subprocess_exec(
				*argv,
				cwd=str(workdir),
				stdin=asyncio.subprocess.DEVNULL,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
			)
		except OSError as exc:
			# A launch that failed is recorded rather than raised, because the operator
			# still needs a row saying nobody was told. `exit_code` stays None, which
			# `Notification.delivered` reads as not delivered.
			return Notification(
				id=uuid7str(),
				error=f"{type(exc).__name__}: {exc}",
				exit_code=None,
				at=now(),
				**common,  # pyright: ignore[reportArgumentType]
			)
		try:
			_, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
		except TimeoutError:
			proc.kill()
			await proc.wait()
			return Notification(
				id=uuid7str(),
				exit_code=None,
				error=f"timed out after {timeout:.0f}s",
				at=now(),
				**common,  # pyright: ignore[reportArgumentType]
			)
		error = stderr_b.decode("utf-8", errors="replace").strip()[-2000:] or None
		return Notification(
			id=uuid7str(),
			exit_code=proc.returncode,
			error=None if proc.returncode == self.spec.expect_exit_code else error,
			at=now(),
			**common,  # pyright: ignore[reportArgumentType]
		)
