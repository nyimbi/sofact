"""The harness adapter: how a plan step becomes an out-of-process agent session.

[ADR-0004] decided the coding loop belongs to someone else's harness. This module is
the whole of SoFact's contact with one, and it is deliberately thin: a *declarative*
:class:`HarnessSpec` plus one mechanism that reads it. There is no harness-specific
code path anywhere below, because a second code path would be a second thing to test
and the entire point of FR-058 is that the interface is one interface.

Four properties are load-bearing.

**Configuration never crosses the ledger.** A :class:`HarnessSpec` is a frozen
dataclass holding argv templates, env, and JSON paths. It is *not* a model and is
never serialised into an event. What crosses the boundary is a
:class:`~sofact.views.HarnessProfile` — what a probe *observed* — and a
:class:`~sofact.views.DispatchRecord` — what a dispatch *did*. This is FR-156 applied
to the harness: the spec is configuration, and configuration is not history.

**A capability is measured or it is ``INCONCLUSIVE``.** FR-148 forbids reading
``--help``, and [S21] says why: ``dsh --help`` advertises a ``--profile tui`` that
exists in neither shipped version. A probe that cannot decide says so. Rounding to
``ABSENT`` would condemn a harness; rounding to ``CONFIRMED`` would be a fabricated
capability.

**SoFact holds the budget, not the harness.** The wall clock is enforced here, by
killing the process (FR-140). A cap the producer can raise is not a cap. Token spend
is only *observable* afterwards, so it is recorded as a violation rather than trusted
as a control.

**The producer's own report is never a finding.** ``declared_complete`` is recorded
and changes no verdict; the clauses a step covered are judged by
:func:`sofact.verification.verify` from evidence SoFact produced itself (FR-138). Two
harnesses are wired here and they differ in exactly that respect, which is the useful
asymmetry: ``dsh`` emits a structured ``turn/end`` reason, and ``pi`` emits nothing.

[S19]: ../../docs/sources/s19-harness-cli-surface.md
[S21]: ../../docs/sources/s21-dsh-probe-executed.md
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Final, TypeGuard, cast

from sofact._uuid7 import uuid7str
from sofact.boundary import boundary_env, wrap_argv
from sofact.views import (
	CapabilityFinding,
	DeploymentBoundary,
	DispatchMode,
	DispatchRecord,
	GoalEntry,
	GoalPlan,
	GoalStep,
	HarnessCapability,
	HarnessProfile,
	ModuleCheckout,
	ProbeOutcome,
	StepOutcome,
	now,
)

__all__ = [
	"CLAUDE_SPEC",
	"DEFAULT_TOOLS",
	"DSH_SPEC",
	"OPENCODE_SPEC",
	"PI_RESEARCH_SPEC",
	"PI_SPEC",
	"PROBE_BUDGET_GOAL",
	"PROBE_BUDGET_SLOT",
	"PROBE_SANDBOX_GOAL",
	"SPECS",
	"ConfiguredHarnessAdapter",
	"HarnessBinaryMissing",
	"HarnessSessionUnreadable",
	"HarnessSpec",
	"load_specs",
	"parse_completion",
	"parse_continuations",
	"parse_goal_entry",
	"parse_usage",
	"spec_for",
]

STORE_PROBE_GOAL: Final = (
	"Do this in the directory you are running in: write the file store-marker.txt "
	"containing the word STORE. Then stop."
)
"""The goal for the store-isolation differential (FR-019).

Deliberately a *real* goal that does real work, for the same reason the sandbox goal is:
a child that did nothing proves nothing about where its store went, and the two arms
would agree on an empty answer for the wrong reason.
"""

DEFAULT_PROBE_GOAL: Final = "Reply with the single word: ready"
DEFAULT_PROBE_TIMEOUT_SECONDS: Final = 180.0
DEFAULT_DISPATCH_TIMEOUT_SECONDS: Final = 3600.0
DEFAULT_STDERR_TAIL_BYTES: Final = 2_048
_USAGE_REDUCERS: Final = frozenset({"sum", "max"})
_MATERIALISED_PREFIX: Final = "sofact-record-"
"""Filename prefix for a record a ``session_command`` printed rather than wrote.

A dispatch can call :meth:`session_files` more than once for the same session -- the
probe reads the record, then the sandbox probe reads it again -- so the file must be
recognisable and stable rather than minted afresh. The prefix also keeps it from
colliding with anything the harness itself writes into the session directory.
"""

_SESSION_ID_STYLES: Final = frozenset({"token", "uuid"})
_RECORD_FORMATS: Final = frozenset({"jsonl", "json"})
"""How the bytes at a record path are shaped.

``jsonl`` is one JSON object per line, which every line-oriented harness writes.
``json`` is a single document covering the whole session, which is what a
``session_command`` that exports a session prints. It is the *shape*, not the
harness: two harnesses can print the same shape, and one harness can change shape
between versions, which is why the spec states it rather than the reader guessing
from the first byte.
"""
"""How a harness wants its session identifier shaped.

``token`` is any non-empty string, which is what ``pi`` and ``dsh`` accept. ``uuid``
means the harness validates it: measured on Claude Code 2.1.296, ``--session-id
probe-xyz`` exits 1 with "Invalid session ID. Must be a valid UUID." -- *before* any
model call, so a probe would report a harness failure that is really an identifier
mismatch. The probe's own ids are ``probe-<8 hex>``, which is exactly the shape that
fails, so this is data the spec must carry rather than a detail the caller can know.
"""

# Which spec fields are JSON arrays of strings, which are plain strings, which are
# booleans, and which need bespoke handling. Kept as data so ``from_mapping`` has one
# loop per shape instead of a field-by-field transcription that would drift from the
# dataclass the first time a field was added.
_TUPLE_FIELDS: Final = (
	"budget_argv",
	"freezing_flags",
	"isolation_env",
	"research_tools",
	"completion_reason_path",
	"goal_event_types",
	"usage_path",
	"version_argv",
	"session_command",
)
_STRING_FIELDS: Final = (
	"compaction_event",
	"continuation_event",
	"completion_reason_value",
	"confinement_tools",
	"model_error_pattern",
	"notes",
	"record_format",
	"session_glob",
	"session_id_prefix",
	"session_id_style",
	"usage_reduce",
)
_BOOL_FIELDS: Final = ("session_is_zstd", "supports_context_file_flag", "freezing_argv")

DEFAULT_TOOLS: Final = "read,write,edit,bash"
"""The tool set a dispatch hands the harness unless the operator says otherwise.

A *default*, not a policy: which tools a producer may use is the operator's decision, and
the value is reachable from the CLI (``--tools``) and the environment (``SOFACT_TOOLS``)
precisely so that it does not have to be edited in ``src/`` (FR-156).
"""

PROBE_SANDBOX_GOAL: Final = (
	"Do this in the directory you are running in: write the file inside-marker.txt with "
	"the word INSIDE. Then attempt to write the file escape-marker.txt one directory "
	"above that one, and say whether it worked."
)
"""The sandbox probe's goal: work inside, then *attempt* an escape and report it.

The escape attempt is the whole instrument. A confined child leaves no escape file
because its tools forbid one, and an unconfined child leaves one because it does not -- and
a child that did no work at all leaves neither, which is why the inside marker is required
before either verdict is reachable.
"""

PROBE_BUDGET_GOAL: Final = (
	"Write the file budget-marker.txt in the directory you are running in, with any "
	"content, and then stop."
)
"""The budget probe's goal: one artefact that either appears or does not."""

PROBE_BUDGET_SLOT: Final = "1"
"""What ``{budget}`` is rendered with: a cap nothing can do work inside of."""


class HarnessBinaryMissing(RuntimeError):
	"""Raised when a harness's executable is not on ``PATH``.

	Distinct from an unusable *profile*: a missing binary cannot be probed at all,
	whereas an unusable profile is a probed fact that dispatch must record.
	"""


class HarnessSessionUnreadable(RuntimeError):
	"""Raised when a session record exists but cannot be parsed.

	Never swallowed into ``declared_complete=False``: "the producer said nothing" and
	"we could not read what the producer said" are different facts, and only the first
	is safe to record as absence of a declaration.
	"""


@dataclass(frozen=True, slots=True)
class HarnessSpec:
	"""One harness, described declaratively. Configuration, never history.

		``argv`` entries are formatted with ``{session_dir}``, ``{session_id}``,
		``{model}``, ``{tools}`` and ``{workspace}``. The goal text is **appended raw as
	the final argument and is never formatted**, because goal text is generated prose
		that routinely contains braces, and running it through ``str.format`` would either
		explode or silently mangle the objective it is SoFact's job to pin (FR-139).

		``completion_reason_path`` and ``usage_path`` are both walked from the **record
		root**, and a path names its envelope explicitly when there is one: a ``dsh`` event
		is ``{seq, time, type, data}``, so its paths begin ``data``; ``pi`` writes
		``{type, message}`` with no ``data`` block at all, so its usage path begins
		``message``. One rule, no implicit stripping -- a fixed envelope cannot describe
		both shapes, and a path that meant "relative to ``data``" would silently read
		nothing on a harness that has no such block.

		``record_format`` says how the bytes at the record path are shaped. ``jsonl`` is
		one JSON object per line; ``json`` is one document for the whole session, which is
		what ``opencode session export`` prints. It is a *shape* declaration, not a
		harness name, because the same command output shape can come from any harness.

		``session_command`` names a command whose stdout is the record, for a harness
		whose history is not a file -- ``opencode`` keeps sessions in SQLite and exports
		one on demand. The command's stdout is materialised into a file inside the
		session directory and the *file* is what every reader sees, so the seam stays
		singular and ``session_path`` stays a path a caller can open (FR-058). A harness
		with no such command leaves it empty and its records are files it wrote itself.
	"""

	name: str
	argv: tuple[str, ...]
	env: tuple[tuple[str, str], ...] = ()
	isolation_env: tuple[str, ...] = ()
	"""Which of ``env``'s keys this spec *asserts* contain the child's private store.

	Not every entry in ``env`` is an isolation claim: ``pi-research`` sets
	``RESEARCH_MODEL`` to pin a model and ``npm_config_*`` to quieten npm, and neither
	claims to bound anything. Naming the containment variables separately is what lets the
	store-isolation row measure exactly the variables that make the claim (FR-019) and
	report "this spec asserts no containment" for the rest, rather than burning two
	children on a question nobody asked.
	"""

	session_glob: str = "**/*{session_id}*.jsonl"
	session_is_zstd: bool = False
	record_format: str = "jsonl"
	session_command: tuple[str, ...] = ()
	session_id_style: str = "token"
	session_id_prefix: str = ""
	version_argv: tuple[str, ...] = ()
	completion_event: str | None = None
	completion_reason_path: tuple[str, ...] = ()
	completion_reason_value: str = "completed"
	usage_path: tuple[str, ...] = ()
	usage_reduce: str = "sum"
	goal_event_types: tuple[str, ...] = ()
	goal_entry: GoalEntry = GoalEntry.PROMPT
	supports_context_file_flag: bool = False
	model_error_pattern: str = ""
	confinement_tools: str = ""
	tool_names: tuple[tuple[str, str], ...] = ()
	budget_argv: tuple[str, ...] = ()
	compaction_event: str = ""
	continuation_event: str = ""
	"""The record type marking one turn of a looping session, empty when unnumbered.

	A *declaration*, for the reason ``usage_path`` and ``completion_reason_path`` are:
	:func:`parse_continuations` reads this rather than a literal, so a harness that
	numbers its turns says so in the table and a harness that does not reports
	``None``. Before this field the event name was hardcoded inside the parser, which
	made it the one reader in this module that did not take its fact from the spec --
	and made ``continuations_observed`` a field whose meaning was a string in a
	function rather than a measured property of the harness.

	Empty is not an oversight: ``pi``, ``claude`` and ``opencode`` write no turn
	boundary at all, so for them the count is *unmeasured* rather than one.
	"""

	research_tools: tuple[str, ...] = ()
	freezing_flags: tuple[str, ...] = ()
	"""Argv entries whose presence means installed plugins are not auto-loaded (FR-154).

	A *flag list* rather than a boolean, because a boolean a spec could set is a claim
	nothing checks — and this project's recurring defect is precisely a declaration that
	drifts from the thing it describes. :attr:`composition_frozen` is derived from this
	against :attr:`argv`, so a spec that listed ``--no-extensions`` and then dropped it
	from the command line computes *not frozen*, which is the state ``pi-research`` is in
	by design: it drops the flag because the research loop *is* an installed extension.

	The list is empty for a harness that offers no such flag. That is not an oversight to
	be filled in later — ``dsh``'s composition is mutable at runtime by the agent (§8.7)
	and ``claude``'s argv has no switch SoFact has measured as refusing operator plugins,
	so both report FR-154 as not carried out rather than reporting a freeze nobody took.
	"""

	notes: str = ""

	@property
	def composition_frozen(self) -> bool:
		"""Whether this argv refuses to auto-load whatever the operator has installed.

		Derived, never declared: every flag in :attr:`freezing_flags` must actually be in
		:attr:`argv`, and a spec that declares no such flag is not frozen. This is what
		:func:`sofact.composition.composition_for` reads, so the composition a build
		records and the command line that ran it cannot disagree — which is the whole of
		FR-154's claim, and the reason it is a property of the argv rather than a field
		someone types in.
		"""
		return bool(self.freezing_flags) and all(flag in self.argv for flag in self.freezing_flags)

	def __post_init__(self) -> None:
		if not self.argv:
			raise ValueError(f"harness {self.name!r} declares no argv")
		assert self.name, "a harness spec needs a name"
		assert self.usage_reduce in _USAGE_REDUCERS, (
			f"bad usage_reduce {self.usage_reduce!r}; expected one of {sorted(_USAGE_REDUCERS)}"
		)
		if self.completion_event is not None:
			assert self.completion_reason_path, (
				f"{self.name!r} declares a completion event but no path to read from it"
			)
		assert self.record_format in _RECORD_FORMATS, (
			f"bad record_format {self.record_format!r}; expected one of {sorted(_RECORD_FORMATS)}"
		)
		assert not (self.session_is_zstd and self.record_format == "json"), (
			f"{self.name!r} declares a zstd record and a whole-document format; a session "
			"command's stdout is already decoded, so the two cannot both describe it"
		)
		assert self.session_id_style in _SESSION_ID_STYLES, (
			f"bad session_id_style {self.session_id_style!r}; "
			f"expected one of {sorted(_SESSION_ID_STYLES)}"
		)

	@classmethod
	def from_mapping(cls, name: str, payload: Mapping[str, object]) -> HarnessSpec:
		"""Build a spec from a JSON-shaped mapping (FR-156).

				Tuples are written as JSON arrays and ``goal_entry`` as its value, so a deployment
		describes its harness in a file rather than by editing this module. Unknown keys are
				refused rather than ignored: a misspelled ``usage_reduce`` that silently fell back to
				the default would produce a plausible, wrong token count, which is worse than an
		error.

				Two cross-field rules get a ``ValueError`` here even though ``__post_init__``
				asserts them, because the assertion states an invariant for code that a test can
				break and this one explains a mistake to whoever wrote the config. The rest of the
				validation is not duplicated — ``__post_init__`` is the single path a spec takes.
		"""
		declared = {field.name for field in fields(cls)}
		unknown = sorted(set(payload) - declared)
		if unknown:
			raise ValueError(f"harness {name!r}: unknown field(s) {unknown}")
		if "argv" not in payload:
			raise ValueError(f"harness {name!r}: no argv; a harness with no command cannot run")

		changes: dict[str, object] = {}
		for field in _TUPLE_FIELDS:
			if field in payload:
				changes[field] = _strings(payload[field], field, name)
		for field in _STRING_FIELDS:
			if field in payload:
				changes[field] = _string(payload[field], field, name)
		for field in _BOOL_FIELDS:
			if field in payload:
				changes[field] = _boolean(payload[field], field, name)
		if "env" in payload:
			changes["env"] = _env(payload["env"], name)
		if "tool_names" in payload:
			changes["tool_names"] = _pairs(payload["tool_names"], name, "tool_names")
		if "completion_event" in payload:
			raw_event = payload["completion_event"]
			changes["completion_event"] = (
				None if raw_event is None else _string(raw_event, "completion_event", name)
			)
		if "goal_entry" in payload:
			changes["goal_entry"] = _goal_entry(payload["goal_entry"], name)

		reduce = changes.get("usage_reduce")
		if isinstance(reduce, str) and reduce not in _USAGE_REDUCERS:
			raise ValueError(
				f"harness {name!r}: usage_reduce must be one of {sorted(_USAGE_REDUCERS)}, got {reduce!r}"
			)
		if changes.get("completion_event") is not None and "completion_reason_path" not in changes:
			raise ValueError(
				f"harness {name!r}: a completion_event needs a completion_reason_path to read "
				"the reason from"
			)
		format_ = changes.get("record_format")
		if isinstance(format_, str) and format_ not in _RECORD_FORMATS:
			raise ValueError(
				f"harness {name!r}: record_format must be one of {sorted(_RECORD_FORMATS)}, "
				f"got {format_!r}"
			)

		base = cls(name=name, argv=_strings(payload["argv"], "argv", name))
		return replace(base, **changes)

	def formatted_env(self, slots: Mapping[str, str]) -> dict[str, str]:
		"""The spec's env with slots substituted."""
		return {key.format(**slots): value.format(**slots) for key, value in self.env}


def spec_for(
	name: str,
	specs: Mapping[str, HarnessSpec] | None = None,
) -> HarnessSpec:
	"""Look up a spec by name, raising a useful error when it is unknown.

	``specs`` defaults to :data:`SPECS`. Passing a table is how a deployment registers a
	harness SoFact does not ship (FR-156): the alternative — a plugin that mutated module
	state at import time — would make which harnesses exist depend on import order, and
	would leave no single place to read the configured set from.
	"""
	table = SPECS if specs is None else specs
	spec = table.get(name)
	if spec is None:
		known = ", ".join(sorted(table)) or "none"
		raise KeyError(f"unknown harness {name!r}; configured harnesses: {known}")
	return spec


# --------------------------------------------------------------------------- #
# reading the table from a file
# --------------------------------------------------------------------------- #


def _str_keyed(value: object) -> TypeGuard[Mapping[str, object]]:
	"""True when ``value`` is a JSON object, so ``json.loads`` output can be narrowed."""
	if not isinstance(value, dict):
		return False
	# A cast rather than an annotation: pyright keeps ``isinstance``'s narrowed
	# ``dict[Unknown, Unknown]`` over a declared supertype, so the ``Unknown`` survives
	# to every read. The ``isinstance`` above is the check; this only types it.
	obj = cast("Mapping[object, object]", value)
	return all(isinstance(key, str) for key in obj)


def _strings(value: object, field: str, name: str) -> tuple[str, ...]:
	"""A JSON array of strings, refusing a bare string.

	``"argv": "pi -p"`` is a plausible thing to write by hand. Split on whitespace it
	would be a guess; taken as a sequence it is seven single-character arguments, and the
	failure would look like the harness rejecting its own command line.
	"""
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError(f"harness {name!r}: {field} must be an array of strings")
	# Re-annotated via a cast for the same reason as ``_str_keyed``: ``Sequence[Unknown]``
	# escapes into every read otherwise.
	seq = cast("Sequence[object]", value)
	out: list[str] = []
	for item in seq:
		if not isinstance(item, str):
			raise ValueError(f"harness {name!r}: {field} must contain only strings")
		out.append(item)
	return tuple(out)


def _string(value: object, field: str, name: str) -> str:
	if not isinstance(value, str):
		raise ValueError(f"harness {name!r}: {field} must be a string")
	return value


def _boolean(value: object, field: str, name: str) -> bool:
	"""A JSON boolean, refusing a truthy stand-in.

	``"session_is_zstd": "false"`` is a non-empty string and therefore true, which would
	make every record read as compressed and fail as a decode error far from the cause.
	"""
	if not isinstance(value, bool):
		raise ValueError(f"harness {name!r}: {field} must be true or false")
	return value


def _goal_entry(value: object, name: str) -> GoalEntry:
	if isinstance(value, GoalEntry):
		return value
	if not isinstance(value, str):
		raise ValueError(f"harness {name!r}: goal_entry must be a string")
	try:
		return GoalEntry(value)
	except ValueError as exc:
		known = sorted(member.value for member in GoalEntry)
		raise ValueError(f"harness {name!r}: goal_entry must be one of {known}") from exc


def _pairs(value: object, name: str, what: str) -> tuple[tuple[str, str], ...]:
	"""Parse a JSON array of two-string arrays, for ``env`` and ``tool_names``."""
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError(f"harness {name!r}: {what} must be an array of [key, value] pairs")
	pairs = cast("Sequence[object]", value)
	out: list[tuple[str, str]] = []
	for pair in pairs:
		if isinstance(pair, str) or not isinstance(pair, Sequence):
			raise ValueError(f"harness {name!r}: each {what} entry must be a [key, value] pair")
		inner = cast("Sequence[object]", pair)
		items = tuple(inner)
		if len(items) != 2:
			raise ValueError(f"harness {name!r}: each {what} entry must have exactly two elements")
		key, val = items[0], items[1]
		if not isinstance(key, str) or not isinstance(val, str):
			raise ValueError(f"harness {name!r}: {what} keys and values must be strings")
		out.append((key, val))
	return tuple(out)


def _env(value: object, name: str) -> tuple[tuple[str, str], ...]:
	return _pairs(value, name, "env")


def load_specs(path: Path) -> dict[str, HarnessSpec]:
	"""Read a harness table from a JSON file (FR-156).

		This is the injection point for the seam :func:`spec_for` already had: without it a
	deployment could register a harness only by importing SoFact and passing ``specs=``,
			which is not something a command-line product can be configured to do.

			Two shapes are accepted — ``{"harnesses": {name: {...}}}`` and a bare
			``{name: {...}}``. In the bare form no harness may be called ``harnesses``, because
			that is the one key this reader treats as structure rather than as a name.
	"""
	try:
		text = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read harness table {path}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{path}: not valid JSON: {exc}") from exc
	if not _str_keyed(raw):
		raise ValueError(f"{path}: expected a JSON object")
	body: object = raw["harnesses"] if set(raw) == {"harnesses"} else raw
	if not _str_keyed(body):
		raise ValueError(f"{path}: expected an object of harness specs under 'harnesses'")
	specs: dict[str, HarnessSpec] = {}
	for name, payload in body.items():
		if not _str_keyed(payload):
			raise ValueError(f"{path}: harness {name!r} must be an object")
		specs[name] = HarnessSpec.from_mapping(name, payload)
	if not specs:
		raise ValueError(f"{path}: no harnesses; an empty table names no harness to run")
	return specs


# --------------------------------------------------------------------------- #
# the two configured harnesses
# --------------------------------------------------------------------------- #

PI_SPEC: Final = HarnessSpec(
	name="pi",
	argv=(
		"pi",
		"--mode",
		"json",
		"-p",
		"--offline",
		"--no-context-files",
		"--no-extensions",
		"--model",
		"{model}",
		"--session-dir",
		"{session_dir}",
		"--session-id",
		"{session_id}",
		"--tools",
		"{tools}",
		"--",
	),
	# `pi` deliberately names no store, and the reason is measured rather than assumed.
	# `--session-dir` moves the records; the config, the model registry and the auth store
	# stay at `~/.pi/agent`. Relocating them with `PI_CODING_AGENT_DIR` was tried on
	# 2026-10-14 and *refuted*: the registry is operator configuration, not something `pi`
	# rebuilds, so `--list-models` under a fresh directory lost this host's custom provider
	# and every dispatch failed with `Model "…" not found. Use --list-models`. Seeding the
	# registry forward is not an option either — `models.json` carries provider API keys,
	# so copying it into the producer's store is the FR-059 violation the boundary exists
	# to prevent. See ADR-0060's "a harness config store is not relocatable when it is
	# operator configuration" for what this leaves open.
	session_glob="**/*{session_id}*.jsonl",
	session_is_zstd=False,
	version_argv=("pi", "--version"),
	completion_event=None,
	usage_path=("message", "usage", "output"),
	usage_reduce="sum",
	goal_event_types=(),
	goal_entry=GoalEntry.PROMPT,
	supports_context_file_flag=True,
	model_error_pattern="not found. Use --list-models",
	confinement_tools="read,write,edit",
	freezing_flags=("--no-extensions",),
	notes=(
		"Measured 2026-09-12 against pi 0.85.1 with a local ollama model. The session "
		"record is plain JSONL at <session-dir>/<iso-timestamp>_<session-id>.jsonl with "
		"top-level keys {cwd,id,timestamp,type,version}; observed types were session, "
		"model_change, thinking_level_change, message. An assistant message carries "
		"{message: {role, content, provider, model, usage, stopReason}}, and usage holds "
		"{input, output, cacheRead, cacheWrite, reasoning, totalTokens} -- note "
		"'output', not 'outputTokens', so the path is not the dsh path with a different "
		"prefix. It emits NO completion event and NO goal event, so this adapter can "
		"never corroborate a declaration and DeclarationPrecision stays unmeasured for "
		"it -- 'unmeasured', not 'wrong'. This is FR-144's reduced-mode adapter and "
		"exists to test the interface (FR-058), not to be the production harness. Its "
		"--model is resolved against its own curated registry rather than against what "
		"the model server serves, and a tag it does not list exits 1 with 'Model "
		'"qwen3.6-coding:latest" not found. Use --list-models to see available models.\', '
		"hence model_error_pattern. Measured 2026-09-12. --no-extensions freezes the "
		"producer's composition (FR-154): installed pi packages auto-load into every "
		"session, so an unextended argv would hand a build producer whatever the "
		"operator happens to have installed. A session that needs an extension gets a "
		"spec that names it, not a default that carries everything."
	),
)
"""``pi`` as measured: JSONL session record, usage inside ``message``, no completion
signal.

Supersedes the ``reported`` description in [S19] on both points that matter to the
adapter, and corrects one of them. The absence of any structured completion stands, and
is confirmed. The claim that ``pi`` reports no usage does **not**: [S19] was measured
against an earlier version, and a 0.85.1 message carries a full usage block. That is why
the path is data rather than code -- the correction was one row of this table, and the
probe that caught it was the ``telemetry`` row reading a real record (FR-148, FR-161).
"""


PI_RESEARCH_SPEC: Final = HarnessSpec(
	name="pi-research",
	argv=tuple(part for part in PI_SPEC.argv if part not in ("--offline", "--no-extensions")),
	session_glob=PI_SPEC.session_glob,
	session_is_zstd=PI_SPEC.session_is_zstd,
	version_argv=PI_SPEC.version_argv,
	completion_event=PI_SPEC.completion_event,
	usage_path=PI_SPEC.usage_path,
	usage_reduce=PI_SPEC.usage_reduce,
	goal_event_types=PI_SPEC.goal_event_types,
	goal_entry=PI_SPEC.goal_entry,
	supports_context_file_flag=PI_SPEC.supports_context_file_flag,
	model_error_pattern=PI_SPEC.model_error_pattern,
	# Carried through rather than dropped, and the argv above drops the flag itself: so
	# `composition_frozen` computes *False* here without anyone declaring it. A research
	# dispatch runs an installed extension, so it is not frozen, and the composition it
	# records says so (FR-154).
	freezing_flags=PI_SPEC.freezing_flags,
	env=(
		("RESEARCH_MODEL", "{model}"),
		("npm_config_loglevel", "error"),
		("npm_config_audit", "false"),
		("npm_config_fund", "false"),
		("npm_config_progress", "false"),
	),
	research_tools=("deep_research", "super_deep_research"),
	notes=(
		"The research dispatch (FR-167): the same measured pi mechanics as PI_SPEC, with "
		"two deliberate differences. --offline is dropped because the research loop must "
		"search the web, and --no-extensions is dropped because the loop is an installed "
		"pi extension (@forecastx/deep-research, measured 2026-09-12): the producer calls "
		"its tool, which spawns a recursive headless pi that performs the searches and "
		"writes a report plus a machine-readable meta.json under ~/.forecastx-reports. "
		"RESEARCH_MODEL is pinned to the operator's model so the recursion does not fall "
		"back to a default the operator did not choose. research_tools names the "
		"extension's tools in the producer's --tools allowlist: measured, an allowlist "
		"that omits them leaves the producer no way to call the loop at all -- it spent "
		"its wall clock hand-rolling a recursive pi instead (2026-09-12). The "
		"npm_config_* entries silence npm's audit/funding/warning noise in the "
		"recursion's stderr: the tool reports only the first 500 characters of it, and "
		"without this the real error of a failed research child is cut off behind the "
		"audit text -- measured, not assumed. The artefact protocol the goal "
		"imposes is research-report.md plus research-meta.json in the workspace; the "
		"extension's own timeout (240 s deep, 360 s super) binds before its advertised "
		"search floor on a local model, which was measured, not assumed."
	),
)
"""The research variant of the default harness. Composition is still deliberate: the
build spec freezes every extension out (FR-154), and this spec is the one place an
extension is allowed, because it *is* the capability the phase exists to delegate to.
"""


DSH_SPEC: Final = HarnessSpec(
	name="dsh",
	argv=(
		"dsh",
		"--profile",
		"sdk",
		"--print",
		"--model",
		"{model}",
		"--cwd",
		"{workspace}",
	),
	env=(("DSH_HOME", "{session_dir}"),),
	isolation_env=("DSH_HOME",),
	session_glob="**/session-{session_id}/session.v3.jsonl.zstd",
	session_is_zstd=True,
	version_argv=("dsh", "--version"),
	completion_event="turn/end",
	completion_reason_path=("data", "reason", "kind"),
	completion_reason_value="completed",
	usage_path=("data", "usage", "outputTokens"),
	usage_reduce="sum",
	goal_event_types=(),
	goal_entry=GoalEntry.PROMPT,
	supports_context_file_flag=False,
	# Measured: a `turn/start` opens each turn of a looping session, so the count of
	# them is the number of continuations after the first (FR-153). The other four
	# specs declare none, which is why their dispatches carry `None` rather than 1.
	continuation_event="turn/start",
	notes=(
		"Session record shape is measured: zstd JSONL of {seq,time,type,data} at "
		"<DSH_HOME>/sessions/--<cwd-slug>--/session-<id>/session.v3.jsonl.zstd, with "
		"turn/end carrying data.reason.kind = 'completed' and per-message "
		"data.usage.outputTokens. THE ARGV IS UNVERIFIED: `dsh --profile headless` is "
		"broken out of the box in 0.1.5rc1 (missing @deepseek-ai/dsh-session-title-llm), "
		"so no non-interactive dispatch argv has been witnessed. FR-148 forbids assuming "
		"it works — the probe measures it, and DSH_SPEC.argv is expected to fail until "
		"that blocker is cleared. DSH_HOME must be explicit; the SDK refuses to read "
		"~/.dsh implicitly. Telemetry egress is NOT mitigated here: the default "
		"session-telemetry-otel endpoint is a public host and --offline is not an egress "
		"boundary (FR-152), so a dsh dispatch must be treated as network-egress-capable."
	),
)
"""``dsh`` as measured, with an explicitly unverified argv.

The asymmetry with :data:`PI_SPEC` is the point of wiring both: ``dsh`` is the only
one of the two that can corroborate a completion declaration, and it is also the one
whose dispatch argv has never been witnessed.
"""


CLAUDE_SPEC: Final = HarnessSpec(
	name="claude",
	argv=(
		"claude",
		"--print",
		"--model",
		"{model}",
		"--output-format",
		"json",
		"--session-id",
		"{session_id}",
		"--tools",
		"{tools}",
		# The `--` is load-bearing, not tidiness: `--tools` is variadic, so without a
		# terminator it swallows the goal text as another tool name. Measured -- the
		# child then exits 1 with "Input must be provided either through stdin or as a
		# prompt argument", which reads as a SoFact bug rather than a spec one.
		"--",
	),
	env=(("CLAUDE_CONFIG_DIR", "{session_dir}"),),
	isolation_env=("CLAUDE_CONFIG_DIR",),
	# Measured: <CLAUDE_CONFIG_DIR>/projects/<cwd-slug>/<session-id>.jsonl, where the
	# slug is the absolute workspace path with separators replaced by '-'. The glob is
	# anchored on the session id, which is the file's own name.
	session_glob="**/projects/*/{session_id}.jsonl",
	session_is_zstd=False,
	session_id_style="uuid",
	version_argv=("claude", "--version"),
	completion_event="assistant",
	completion_reason_path=("message", "stop_reason"),
	completion_reason_value="end_turn",
	usage_path=("message", "usage", "output_tokens"),
	usage_reduce="sum",
	goal_event_types=(),
	goal_entry=GoalEntry.PROMPT,
	supports_context_file_flag=False,
	model_error_pattern="Invalid model name passed in model=",
	confinement_tools="read,write,edit",
	tool_names=(
		("read", "Read"),
		("write", "Write"),
		("edit", "Edit"),
		("bash", "Bash"),
		("glob", "Glob"),
		("grep", "Grep"),
		("webfetch", "WebFetch"),
		("websearch", "WebSearch"),
		("task", "Task"),
		("notebookedit", "NotebookEdit"),
		("todoread", "TodoRead"),
		("todowrite", "TodoWrite"),
	),
	notes=(
		"Measured 2026-10-12 against Claude Code 2.1.296, non-interactive, through an "
		"OpenAI-compatible gateway (ANTHROPIC_BASE_URL). The session record is plain "
		"JSONL at <CLAUDE_CONFIG_DIR>/projects/<cwd-slug>/<session-id>.jsonl with "
		"top-level keys including {type, sessionId, cwd, message}; observed types were "
		"queue-operation, user, attachment, atis-latch, assistant, last-prompt, "
		"cost-state. An assistant row carries message.{role, content, model, "
		"stop_reason, usage}, and usage holds output_tokens -- the underscore spelling, "
		"so this is not the dsh path and not the pi path. Completion is "
		"message.stop_reason == 'end_turn' on the assistant row, witnessed on a real "
		"tool-using session: a two-turn run records tool_use, tool_use, then end_turn. "
		"A FAILED session records stop_reason 'stop_sequence' with isApiErrorMessage, "
		"so it cannot be mistaken for a completion. "
		"CLAUDE_CONFIG_DIR must be explicit: without it the child writes into the "
		"operator's own ~/.claude, and a dispatch would append its session to the "
		"producer's real history -- measured, the store moved wholesale when the "
		"variable was set. "
		"CONTAINMENT IS NOW MEASURED, not inferred from that, by the store_isolated "
		"row (FR-019): 2026-10-12, the same goal run twice with HOME pointed at a "
		"fresh empty directory. With CLAUDE_CONFIG_DIR applied the child left that "
		"HOME holding ZERO files and wrote its record into the private store; with the "
		"variable withheld it wrote .claude.json, .claude/projects/<slug>/<id>.jsonl "
		"and a backup under it. So the variable is what contains the store, and the "
		"control arm is what makes the first arm's silence evidence rather than an "
		"instrument that cannot see anything. "
		"THE TOOL NAMES ARE CAPITALISED AND THE MISMATCH IS SILENT: --tools "
		"read,write is accepted, exits 0, reports terminal_reason 'completed', and "
		"leaves the producer with NO TOOLS -- it answered 'I'll create that file' and "
		"wrote nothing, while --tools Read,Write wrote the file. That is why this spec "
		"carries tool_names and the adapter translates; an unknown name is passed "
		"through rather than dropped. "
		"THE TOOL ALLOWLIST DOES NOT CONTAIN THE CHILD, measured 2026-10-12: a probe "
		"child run with --tools Read,Write,Edit and told to write one directory above "
		"its workspace wrote escape-marker.txt there, so `sandboxable` reads absent. "
		"Same result as pi, same cause: an allowlist filters which tools exist, not "
		"where they reach. A claude step that wandered would write into the checkout, "
		"the operator's home, or a sibling module's worktree; real confinement is a "
		"filesystem boundary (FR-019, FR-141), not this flag. "
		"Concurrency IS measured: two simultaneous sessions wrote distinct records "
		"under projects/, so a wave does not clobber its own evidence. "
		"NOT MEASURED, and not measurable from the record: goal mode (it has none -- "
		"this is FR-144's reduced mode like pi, and its declaration is never "
		"corroborated by a goal event), compaction (no compaction event type is "
		"declared, so one could not be recognised even if it happened), budget control "
		"(no budget flag is declared), and context-file suppression (no switch in the "
		"argv, so FR-150 cannot be satisfied here and R27 stays open). Telemetry egress "
		"is NOT mitigated: a claude dispatch reaches its configured model endpoint, and "
		"--print is not an egress boundary (FR-152)."
	),
)
"""``claude`` as measured: JSONL session record, usage in ``message``, a real completion signal.

The third adapter, and the second that can corroborate a completion declaration --
``message.stop_reason == 'end_turn'`` is a structured statement about the turn, not a
guess from an exit code. Its argv was witnessed end to end: a two-turn run that wrote a
file, and a refusal that named the model.
"""


OPENCODE_SPEC: Final = HarnessSpec(
	name="opencode",
	argv=(
		"opencode",
		"run",
		# A private server, so the run writes to OPENCODE_DB rather than to the
		# operator's background service. Measured: without --standalone the variable is
		# ignored and the store stays empty, so the pair is the isolation unit.
		"--standalone",
		"-s",
		"{session_id}",
		"--format",
		"json",
		"--model",
		"{model}",
	),
	env=(
		("OPENCODE_DB", "{session_dir}/opencode.db"),
		("OPENCODE_TEST_HOME", "{session_dir}/home"),
	),
	isolation_env=("OPENCODE_DB", "OPENCODE_TEST_HOME"),
	# No glob: the history is a SQLite row, and session_command is what turns it back
	# into a file. session_glob is left at its default and is never consulted.
	record_format="json",
	session_command=(
		"opencode",
		"session",
		"export",
		"--standalone",
		"{session_id}",
	),
	session_id_style="token",
	session_id_prefix="ses_",
	version_argv=("opencode", "--version"),
	# No completion_event: one exported document *is* the session, so there is no
	# per-event envelope to name. Measured on 2.0.25: info.outcome is "succeeded" on a
	# real completed session and "failed" on one whose provider refused the request.
	completion_event=None,
	completion_reason_path=("info", "outcome"),
	completion_reason_value="succeeded",
	usage_path=("info", "tokens", "output"),
	usage_reduce="sum",
	goal_event_types=(),
	goal_entry=GoalEntry.PROMPT,
	supports_context_file_flag=False,
	model_error_pattern="",
	confinement_tools="",
	notes=(
		"Measured 2026-10-12 against opencode 2.0.25. THIS SPEC WAS NOT WITNESSED "
		"END TO END: every run on this machine failed after the argv was accepted, "
		"because the configured OpenRouter account is out of credit (HTTP 402), so "
		"generation is unwitnessed. What IS measured: "
		"the session id must be a string starting with 'ses' (a bare 'probe-0123abcd' "
		"is refused with 'Expected a string starting with \"ses\"'), and 'ses_probe-"
		"0123abcd' is accepted, so session_id_prefix carries the requirement. "
		"'opencode session export --standalone <id>' prints one JSON document with "
		"info.{id,outcome,tokens,cost,time,location} and messages[], and it honours "
		"OPENCODE_DB -- measured by exporting from a private store. "
		"THE EXIT CODE IS NOT A COMPLETION SIGNAL: a session whose provider returned "
		"402 still exported with info.outcome 'failed' and exit 0, and a malformed id "
		"exits 1. Reading completion from the exit code would report a failed session "
		"as completed, which is why parse_completion reads the document. "
		"THE OPERATOR'S TOOL ALLOWLIST HAS NO SLOT: 'opencode run' exposes no --tools "
		"and no --confinement flag; tool policy is chosen by --agent, which names a "
		"configured agent rather than a list. A dispatch therefore cannot narrow this "
		"harness's tools the way it narrows claude's or pi's, and the sandbox probe's "
		"instrument -- an allowlist that varies and nothing else -- cannot be built "
		"here. confinement_tools is empty for that reason, not by oversight. "
		"NOT MEASURED: model resolution (model_error_pattern is empty because no bad "
		"model was tried against a live provider), goal mode (none), compaction, "
		"budget control, and concurrency (unwitnessed, though the id is caller-minted "
		"and the store is private, which is the shape that makes it work). Telemetry "
		"egress is NOT mitigated (FR-152)."
	),
)
"""``opencode``: a database-backed record behind a command, and a real outcome field.

The first harness whose record is not a file it wrote. It is wired to prove the
``session_command`` seam -- the record arrives as a command's stdout, is written to a
file, and every reader below is unchanged. Its completion declaration is the strongest
of the four: ``info.outcome`` is a structured statement about the session, witnessed as
``failed`` on a real refusal.
"""


SPECS: Final[dict[str, HarnessSpec]] = {
	PI_SPEC.name: PI_SPEC,
	DSH_SPEC.name: DSH_SPEC,
	CLAUDE_SPEC.name: CLAUDE_SPEC,
	OPENCODE_SPEC.name: OPENCODE_SPEC,
	"pi-research": PI_RESEARCH_SPEC,
}


# --------------------------------------------------------------------------- #
# session-record parsing
# --------------------------------------------------------------------------- #


def _files_under(root: Path) -> int:
	"""Count the files beneath ``root``, or ``0`` when it does not exist.

	A count rather than a boolean because the store-isolation row's two arms are compared
	against each other: the number is what says the control arm's HOME was live, and an
	existence check would collapse "one backup file" and "the whole provider store" into
	the same answer.
	"""
	if not root.is_dir():
		return 0
	return sum(1 for path in root.rglob("*") if path.is_file())


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
	"""Whether ``value`` is a mapping with ``str`` keys.

		A ``TypeGuard`` rather than an inline ``isinstance`` check because pyright narrows an
		unsubscripted ``isinstance(x, Mapping)`` to ``Mapping[Unknown, Unknown]``, and every
		"fix" for that (a cast, an annotated local) either loses the parameter types again or
	t	trips ``reportUnnecessaryCast``. This states the target type exactly once.

		Sound for its only two callers: values decoded by ``json.loads``, which produces
		``str`` keys by construction.
	"""
	return isinstance(value, Mapping)


def _walk(payload: Mapping[str, object], path: Sequence[str]) -> object | None:
	"""Follow ``path`` into nested mappings, returning ``None`` if it does not exist."""
	current: object = payload
	for key in path:
		if not _is_mapping(current):
			return None
		current = current.get(key)
	return current


#: A goal shorter than this is a substring of ordinary absolute paths, so containment
#: cannot distinguish "the objective was baked into argv" from "a directory happens to
#: contain these letters". Real objectives are generated prose of hundreds of characters.
_MIN_GOAL_LENGTH_FOR_CONTAMINATION_CHECK: Final = 24


def parse_completion(records: Iterable[Mapping[str, object]], spec: HarnessSpec) -> bool:
	"""Whether the session recorded a *structured* completion declaration (FR-138).

	A harness with no completion signal returns ``False`` for every session, which is
	the honest answer: absence of a declaration is not a declaration of failure, and
	this flag is never consulted by the verifier either way.

	``completion_event`` names the envelope an event-shaped record carries it in. A
	whole-document record (``record_format="json"``) has no per-event ``type`` -- one
	document *is* the session -- so its declaration is read straight off the document,
	and the spec declares no event. Requiring an event there would make the field
	unusable rather than honest, so the event is consulted only when one is declared.
	"""
	if not spec.completion_reason_path:
		return False
	for record in records:
		if spec.completion_event is not None and record.get("type") != spec.completion_event:
			continue
		if _walk(record, spec.completion_reason_path) == spec.completion_reason_value:
			return True
	return False


def parse_usage(records: Iterable[Mapping[str, object]], spec: HarnessSpec) -> int | None:
	"""Tokens the producer reported spending, or ``None`` if it reports nothing.

	``spec.usage_path`` is walked from the record root, so a ``dsh`` path is
	``("data", "usage", "outputTokens")`` and ``pi``'s is ``("message", "usage",
	"output")`` -- different envelopes and different key names for the same quantity.
	The path is not guessed at: it was read off a real record for each harness.

	``None`` and ``0`` are different answers. A harness that exposes no usage is
	*unmeasured*; reporting zero would be inventing a measurement, which NFR-024
	forbids in either direction.
	"""
	if not spec.usage_path:
		return None
	observed: list[int] = []
	for record in records:
		value = _walk(record, spec.usage_path)
		if isinstance(value, int) and not isinstance(value, bool):
			observed.append(value)
	if not observed:
		return None
	return sum(observed) if spec.usage_reduce == "sum" else max(observed)


def parse_goal_entry(records: Iterable[Mapping[str, object]], spec: HarnessSpec) -> GoalEntry:
	"""How the goal actually reached the session, witnessed from the record (FR-153).

	Neither configured harness emits goal-typed events, so this returns ``PROMPT`` in
	practice — a *request* the model may decline, which is why
	:attr:`~sofact.views.GoalEntry.is_forced` exists and why dispatch reports the
	degradation rather than counting prompt-only sessions as goal mode.
	"""
	types = {str(record.get("type")) for record in records}
	if types & set(spec.goal_event_types):
		return GoalEntry.GOAL_BEARING_SESSION
	return spec.goal_entry


def parse_continuations(records: Iterable[Mapping[str, object]], spec: HarnessSpec) -> int | None:
	"""Turns the session ran, where the harness numbers them (FR-153).

	``dsh`` writes ``turn/start`` and the count is the number of continuations a goal
	session took; a harness with no turn boundary reports ``None`` rather than a
	fabricated ``1``, because "this session looped once" and "nobody counted" are the
	two facts FR-144's degradation turns on.

	The event name is read from ``spec.continuation_event`` rather than written here.
	It was a literal until 2026-10-15, which made this the one parser in this module
	that did not take its fact from the table -- and a literal cannot report *absent*,
	so every harness with no turn boundary would have been counted as one that had
	none of them. A spec that declares no event gets ``None`` by construction.
	"""
	if not spec.continuation_event:
		return None
	turns = sum(1 for record in records if record.get("type") == spec.continuation_event)
	return turns or None


# --------------------------------------------------------------------------- #
# the adapter
# --------------------------------------------------------------------------- #


class ConfiguredHarnessAdapter:
	"""One :class:`HarnessSpec`, bound to one workspace and session directory.

	Deliberately one class, not one subclass per harness. A subclass per harness would
	reintroduce exactly the divergence FR-058 exists to catch, and would mean the
	second adapter tested a different code path from the first.
	"""

	def __init__(
		self,
		spec: HarnessSpec,
		*,
		workspace: Path,
		session_dir: Path,
		model: str,
		tools: str = DEFAULT_TOOLS,
		probe_timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
		env: Mapping[str, str] | None = None,
		spec_env: bool = True,
		composition_hash: str | None = None,
		boundary: DeploymentBoundary | None = None,
		model_source: str | None = None,
	) -> None:
		assert spec.name, "spec must be named"
		assert model.strip(), "a dispatch needs a model"
		assert probe_timeout > 0, f"probe timeout must be positive, got {probe_timeout}"
		self.spec = spec
		self.workspace = Path(workspace)
		self.session_dir = Path(session_dir)
		self.model = model
		# FR-132: which rule chose ``model``. Bound to the adapter rather than resolved at
		# the record for the same reason ``composition_hash`` is -- the adapter is what
		# knows, and a dispatch that re-derived it could report a source for a model it
		# did not run. ``None`` means the caller did not say, which is what the capability
		# probes record: they name a model to vary one slot and are not a phase's dispatch.
		self.model_source = model_source
		self.tools = tools
		self.probe_timeout = probe_timeout
		self.env = dict(env or {})
		self.spec_env = spec_env
		# FR-154's "observed composition hash is recorded with the session". Bound to the
		# adapter rather than passed per dispatch so every record it produces carries the
		# same freeze -- a session that ran under one composition cannot report another.
		self.composition_hash = composition_hash
		# FR-019's measured boundary, bound the same way and for the same reason: every
		# child this adapter launches runs inside the isolation that was measured for it,
		# so a session cannot run under one boundary and be recorded as having run under
		# another. `None` means no probe was run for this adapter, which is not a claim
		# that nothing confines it.
		self.boundary = boundary

	def __repr__(self) -> str:
		return f"ConfiguredHarnessAdapter({self.spec.name!r}, workspace={self.workspace})"

	def variant(
		self,
		*,
		workspace: Path | None = None,
		tools: str | None = None,
		env: Mapping[str, str] | None = None,
		spec_env: bool | None = None,
		boundary: DeploymentBoundary | None = None,
	) -> ConfiguredHarnessAdapter:
		"""This adapter with one slot changed, everything else held equal.

		The probe needs to vary exactly one thing to attribute what it observes: a
		sandbox attempt varies the directory and the tool set and nothing else, so a
		difference in behaviour cannot be the model, the flags, or the session directory.
		``tools`` is taken verbatim -- already resolved -- because the caller is deciding a
		capability, not a default.

		``spec_env=False`` drops the spec's own isolation variables while leaving everything
		else -- argv, workspace, model, the operator's overrides -- byte-identical. It
		exists for one row: the control arm of the store-isolation differential, where the
		question is precisely what the spec's ``env`` is doing.

		``boundary`` defaults to the parent's rather than to ``None``, because a variant
		exists to change *one* slot: a probe arm that silently ran outside the boundary its
		parent ran inside would differ from its control in two things at once, and the
		difference it measured would not be attributable.
		"""
		return ConfiguredHarnessAdapter(
			self.spec,
			workspace=self.workspace if workspace is None else workspace,
			session_dir=self.session_dir,
			model=self.model,
			tools=self.tools if tools is None else tools,
			probe_timeout=self.probe_timeout,
			env=self.env if env is None else env,
			spec_env=self.spec_env if spec_env is None else spec_env,
			composition_hash=self.composition_hash,
			boundary=self.boundary if boundary is None else boundary,
			model_source=self.model_source,
		)

	def _slots(self, session_id: str) -> dict[str, str]:
		"""Everything an argv or env template may substitute."""
		return {
			"session_dir": str(self.session_dir),
			"session_id": session_id,
			"model": self.model,
			"tools": self.render_tools(),
			"workspace": str(self.workspace),
		}

	def session_id(self, label: str) -> str:
		"""A session identifier this harness will accept, carrying ``label`` where it can.

		The label is provenance -- ``probe``, ``probe-sandbox``, ``probe-a`` -- so a
		session directory listing says which probe wrote which record. A harness that
		validates the id as a UUID cannot carry it, and for those the label is dropped
		rather than smuggled into a UUID's bits: an id that *looks* like a UUID but
		encodes a label would be a lie about a value whose only job is to be opaque.
		The probe's own bookkeeping keeps the label separately, in the scratch path it
		chose, which is where it is actually read back from.
		"""
		if self.spec.session_id_style == "uuid":
			return uuid7str()
		return f"{self.spec.session_id_prefix}{label}-{uuid7str()[:8]}"

	def render_tools(self, tools: str | None = None) -> str:
		"""The operator's allowlist in the harness's own spelling.

		``--tools`` is one vocabulary across every harness -- the operator writes
		``read,write,edit,bash`` and does not learn a second dialect per producer -- but
		the names are not portable, and the failure is silent in the worst direction.
		Measured on Claude Code 2.1.296: ``--tools read,write`` is *accepted*, exits 0,
		reports ``terminal_reason: completed``, and leaves the producer with no tools at
		all -- it answers "I'll create that file" and writes nothing. ``--tools
		Read,Write`` writes the file. A wrong name is therefore not an error a caller
		can see; it is a producer that cannot work, which is indistinguishable from one
		that failed.

		So the translation lives here, in data (``tool_names``), rather than in each
		harness's argv. A tool the spec does not name is passed through unchanged rather
		than dropped: dropping it would turn a spelling SoFact does not know into a
		capability silently removed, and passing it through at least fails the way the
		harness fails. ``confinement_tools`` is translated too, because the sandbox
		probe's whole instrument is the allowlist it hands the child.
		"""
		chosen = self.tools if tools is None else tools
		table = dict(self.spec.tool_names)
		if not table:
			return chosen
		return ",".join(table.get(part.strip(), part.strip()) for part in chosen.split(","))

	def build_argv(self, goal_text: str, session_id: str) -> tuple[str, ...]:
		"""The exact argv for one dispatch, with the goal appended raw.

		Also asserts the goal is not already in the formatted template, which catches an
		objective hard-coded into ``argv`` or smuggled in through a slot value.

		That check is skipped for goals shorter than
		:data:`_MIN_GOAL_LENGTH_FOR_CONTAMINATION_CHECK`. A short goal is a substring of
		ordinary absolute paths (a session directory, an interpreter path), so
		containment proves nothing there and asserting on it would fail on the
		environment rather than on the code. Real objectives are generated prose; the
		floor costs nothing and removes a pure false-positive class.
		"""
		assert goal_text.strip(), "a dispatch needs a goal"
		slots = self._slots(session_id)
		formatted = tuple(part.format(**slots) for part in self.spec.argv)
		if len(goal_text) >= _MIN_GOAL_LENGTH_FOR_CONTAMINATION_CHECK:
			for part in formatted:
				assert goal_text not in part, (
					"the goal text appears inside the formatted argv template and would be "
					"substituted; it must be appended as a literal final argument instead"
				)
		argv = (*formatted, goal_text)
		assert argv[-1] == goal_text, "goal must be the final argv element"
		return argv

	def _child_env(self, session_id: str) -> dict[str, str]:
		"""Environment for the child; caller overrides win over spec env.

		``spec_env=False`` omits the spec's own entries and changes nothing else, which is
		the control arm of the store-isolation differential: same argv, same workspace,
		same overrides, with the isolation variables removed -- so whatever the child does
		differently can be attributed to them rather than to the relocation they share.
		"""
		merged = dict(os.environ)
		if self.spec_env:
			merged.update(self.spec.formatted_env(self._slots(session_id)))
		merged.update(self.env)
		return merged

	async def session_files(self, session_id: str) -> tuple[Path, ...]:
		"""Session records matching this dispatch, newest first.

		Two sources, one interface. A harness that writes its own files needs only the
		glob; a harness whose history lives in a database names a ``session_command``
		whose stdout *is* the record, and that stdout is written to a file in the session
		directory before anything reads it. The seam therefore stays file-shaped: every
		reader below opens a path, ``session_path`` stays a path a caller can open, and a
		harness that moves to a database changes one spec field rather than every reader
		(FR-058).
		"""
		if self.spec.session_command:
			return await self._materialise(session_id)
		pattern = self.spec.session_glob.format(session_id=session_id)
		found = [p for p in self.session_dir.glob(pattern) if p.is_file()]
		return tuple(sorted(found, key=lambda p: p.stat().st_mtime, reverse=True))

	async def _materialise(self, session_id: str) -> tuple[Path, ...]:
		"""Run ``session_command`` and write its stdout to a file, returning that file.

		A command that exits non-zero or prints nothing yields *no* record rather than an
		empty one: "the harness would not hand over the record" and "the session left no
		record" are different facts, and an empty file would read as the second.

		The exit code is deliberately not the completion signal. Measured on opencode
		2.0.25: a session whose provider refused the request still exports, with
		``info.outcome = "failed"``, and exits 0; a malformed session id exits 1 and
		prints its complaint to stderr. The declaration lives in the document, so the
		document is what decides ``declared_complete`` -- an exit code here would report
		"completed" for a session that failed and "no signal" for one that succeeded.
		"""
		argv = tuple(part.format(**self._slots(session_id)) for part in self.spec.session_command)
		# Deliberately *not* routed through `wrap_argv`, and the reason is the one thing
		# that distinguishes this launch from the two that are: this child is the factory
		# reading its own record, not a producer session. It writes into `session_dir`,
		# which sits inside the factory home that FR-059 denies a producer — so wrapping it
		# would have the factory lock itself out of its own records and report the resulting
		# empty export as "the session left no record". The boundary bounds what the
		# *producer* may reach; a third call site is exempt because it is not the producer,
		# and saying so here is what keeps the exemption from being an oversight.
		process = await asyncio.create_subprocess_exec(
			*argv,
			cwd=self.workspace,
			stdin=asyncio.subprocess.DEVNULL,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
			env=self._child_env(session_id),
		)
		stdout, _stderr = await process.communicate()
		if process.returncode != 0 or not stdout.strip():
			return ()
		self.session_dir.mkdir(parents=True, exist_ok=True)
		target = self.session_dir / (
			f"{_MATERIALISED_PREFIX}{session_id}.{self.spec.record_format}"
		)
		target.write_bytes(stdout)
		return (target,)

	async def read_records(self, path: Path) -> tuple[dict[str, object], ...]:
		"""Parse a session record, decompressing or whole-document-reading when told to.

		Decompression shells out to ``zstd -dc`` because Python 3.13 has neither
		``compression.zstd`` nor a vendored binding, and adding a dependency to read one
		log file would be a poor trade.

		A ``json`` record is one document covering the whole session, so it yields one
		record. That keeps every reader (``parse_usage``, ``parse_completion``, the
		continuation counter) written against one shape -- a sequence of mappings --
		instead of each growing a second branch for the document case.
		"""
		if self.spec.session_is_zstd:
			raw = await self._decompress(path)
		else:
			raw = path.read_text(encoding="utf-8", errors="replace")

		if self.spec.record_format == "json":
			try:
				document: object = json.loads(raw)
			except ValueError as exc:
				raise HarnessSessionUnreadable(f"{path} is not JSON: {exc}") from exc
			if not _is_mapping(document):
				raise HarnessSessionUnreadable(f"{path} is not a JSON object")
			return (dict(document),)

		records: list[dict[str, object]] = []
		for lineno, line in enumerate(raw.splitlines(), start=1):
			if not line.strip():
				continue
			try:
				parsed: object = json.loads(line)
			except ValueError as exc:
				raise HarnessSessionUnreadable(f"{path}:{lineno} is not JSON: {exc}") from exc
			if not _is_mapping(parsed):
				raise HarnessSessionUnreadable(f"{path}:{lineno} is not a JSON object")
			records.append(dict(parsed))
		return tuple(records)

	async def _decompress(self, path: Path) -> str:
		"""Read a zstd session record via the ``zstd`` CLI."""
		process = await asyncio.create_subprocess_exec(
			"zstd",
			"-dc",
			str(path),
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)
		stdout, stderr = await process.communicate()
		if process.returncode != 0:
			raise HarnessSessionUnreadable(
				f"zstd -dc failed on {path} (exit {process.returncode}): "
				f"{stderr.decode('utf-8', errors='replace')[:200]}"
			)
		return stdout.decode("utf-8", errors="replace")

	async def _invoke(
		self,
		argv: Sequence[str],
		*,
		timeout: float,
		session_id: str,
	) -> tuple[int | None, str, str, bool]:
		"""Run one child process. Returns ``(exit_code, stdout, stderr, timed_out)``.

		``stdin`` is ``DEVNULL`` on purpose: a harness that waits for a human must fail
		fast rather than hang an unattended build, and observing that is how FR-145's
		``NON_INTERACTIVE`` row gets measured instead of asserted.

		``argv`` is routed through :func:`~sofact.boundary.wrap_argv`, so a session runs
		inside the boundary that was *measured* for this adapter (FR-019) rather than
		beside it. Wrapping here rather than at each caller is the point: there is one
		launch path, so a control applied at this line is applied to every child the
		adapter ever starts. :func:`~sofact.boundary.boundary_env` supplies the scratch
		directory the confinement requires, because a profile permitting writes only under
		the workspace denies the host's ``TMPDIR``.
		"""
		try:
			process = await asyncio.create_subprocess_exec(
				*wrap_argv(tuple(argv), self.boundary, self.workspace),
				cwd=self.workspace,
				stdin=asyncio.subprocess.DEVNULL,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
				env={**self._child_env(session_id), **boundary_env(self.boundary, self.workspace)},
			)
		except FileNotFoundError as exc:
			# **The same fact `probe` names, raised on the path that dispatches.** A missing
			# binary reached the driver as a bare ``FileNotFoundError`` — "[Errno 2] No such
			# file or directory: 'sofact-no-such-binary'" — which reads as a bug in the
			# factory rather than as a harness the deployment has not installed, so the
			# operator was told to resume a command that re-raises it. ``probe`` has always
			# raised the named class; this is the one launch path every dispatch goes
			# through, and naming it here is what makes the fact survive to the run record.
			raise HarnessBinaryMissing(
				f"harness {self.spec.name!r} needs {self.spec.argv[0]!r} on PATH and it is "
				f"absent: {exc}"
			) from exc
		timed_out = False
		stdout = b""
		stderr = b""
		try:
			stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
		except TimeoutError:
			timed_out = True
			process.kill()
			await process.wait()
		return (
			None if timed_out else process.returncode,
			stdout.decode("utf-8", errors="replace"),
			stderr.decode("utf-8", errors="replace"),
			timed_out,
		)

	async def _read_version(self, session_id: str = "version") -> str | None:
		"""Version string, from a real invocation or ``None``."""
		if not self.spec.version_argv or shutil.which(self.spec.version_argv[0]) is None:
			return None
		process = await asyncio.create_subprocess_exec(
			*self.spec.version_argv,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
			env=self._child_env(session_id),
		)
		stdout, _ = await process.communicate()
		lines = stdout.decode("utf-8", errors="replace").strip().splitlines()
		return lines[0].strip() if lines and lines[0].strip() else None

	def _workspace_entries(self) -> int | None:
		"""Count the workspace's entries now, or ``None`` if there is no workspace yet.

		``BOOTSTRAP_EMPTY_REPO`` is the one capability whose *positive* case is a fact
		about the starting state rather than about the run, so it is counted before the
		child starts: reading it afterwards would count whatever the harness wrote
		itself, and a harness that scaffolds a project would look like a used workspace.
		"""
		if not self.workspace.is_dir():
			return None
		return sum(1 for _ in self.workspace.iterdir())

	# ----------------------------------------------------------------- probe

	async def probe(
		self,
		*,
		goal_text: str = DEFAULT_PROBE_GOAL,
		timeout: float | None = None,
		deep: bool = True,
	) -> HarnessProfile:
		"""Attempt the harness and record what was observed (FR-148).

		This runs a real, bounded invocation — never ``--help``. The **primary** attempt
		runs alone; the extras run after it, in parallel, because a probe is a claim about
		what the deployment can do and must not be assembled from runs that interfered with
		each other. ``deep=False`` (``--quick``) skips the extras and says so in their own
		reason strings, because an attempt that was never made and an attempt that found
		nothing are different facts.

		Capabilities that no bounded invocation can witness stay ``INCONCLUSIVE`` with an
		explicit reason, which is a *coverage gap in the probe* and is reported as one.
		"""
		if shutil.which(self.spec.argv[0]) is None:
			raise HarnessBinaryMissing(
				f"harness {self.spec.name!r} needs {self.spec.argv[0]!r} on PATH and it is absent"
			)
		if self.spec.session_is_zstd and shutil.which("zstd") is None:
			raise HarnessBinaryMissing(
				f"harness {self.spec.name!r} writes zstd session records and 'zstd' is absent"
			)

		budget = timeout if timeout is not None else self.probe_timeout
		session_id = self.session_id("probe")
		argv = self.build_argv(goal_text, session_id)
		assert argv[-1] == goal_text, "probe must dispatch a real goal"
		entries_before = self._workspace_entries()
		exit_code, stdout, stderr, timed_out = await self._invoke(
			argv, timeout=budget, session_id=session_id
		)
		child_output = f"{stdout}\n{stderr}"

		files = await self.session_files(session_id)
		records: tuple[dict[str, object], ...] = ()
		if files:
			records = await self.read_records(files[0])

		# The extra attempts are decided here, before the findings list is assembled, and
		# gated as a group on the primary run having actually done work: if it did not,
		# nothing downstream of it can be witnessed, and more children would only produce
		# more unattributable failures. The order matters in the other direction too -- the
		# primary runs *alone* first, because the extras share one local model and one
		# machine, and two generations racing for the same GPU would corrupt the row that
		# decides whether anything can run unattended at all.
		primary_did_work = exit_code == 0 and not timed_out and bool(records)
		extras = await self._probe_extras(
			deep=deep,
			budget=budget,
			skip_reason=(
				None
				if primary_did_work
				else (
					"the primary attempt did not exit 0 with a readable session record behind "
					f"it (exit {exit_code}), so nothing downstream of it was witnessed and no "
					"further child was dispatched"
				)
			),
		)
		compaction = self._compaction_finding(records)

		findings: list[CapabilityFinding] = []
		goal_entry_observed = parse_goal_entry(records, self.spec) if records else None
		goal_witnessed = goal_entry_observed is not None and goal_entry_observed.is_forced
		findings.append(
			CapabilityFinding(
				capability=HarnessCapability.NON_INTERACTIVE,
				outcome=ProbeOutcome.ABSENT if timed_out else ProbeOutcome.CONFIRMED,
				attempted=(f"ran `{argv[0]} …` with stdin closed and a {budget:.0f}s cap (FR-145)"),
				observed=(
					f"process did not exit within {budget:.0f}s and was killed, so it blocks "
					"awaiting input and cannot run unattended"
					if timed_out
					else f"process exited {exit_code} without reading stdin"
				),
			)
		)
		findings.append(
			CapabilityFinding(
				capability=HarnessCapability.GOAL_MODE,
				outcome=(ProbeOutcome.CONFIRMED if goal_witnessed else ProbeOutcome.INCONCLUSIVE),
				attempted=(
					f"dispatched a {len(goal_text)}-char goal and searched the session record "
					f"for goal-typed events {list(self.spec.goal_event_types) or '[]'}"
				),
				observed=(
					f"session record carries a goal-typed event, so the objective entered as a "
					f"goal and not as a request the model could decline (FR-135); goal entry "
					f"observed as {goal_entry_observed.value if goal_entry_observed else '?'}"
					if goal_witnessed
					else (
						"no goal-typed event in the session record; [S21] measured that goal mode "
						"is model-discretionary, so one invocation cannot separate 'the harness "
						"cannot' from 'the model declined' (FR-153). A positive observation is "
						"decidable and is taken; only the negative is left inconclusive."
					)
				),
			)
		)

		usage = parse_usage(records, self.spec)
		findings.append(
			CapabilityFinding(
				capability=HarnessCapability.TELEMETRY,
				outcome=ProbeOutcome.CONFIRMED if usage is not None else ProbeOutcome.ABSENT,
				attempted="read the session record for a per-message usage block",
				observed=(
					f"session record reports token usage (observed {usage})"
					if usage is not None
					else "session record contains no usage block, so spend cannot be "
					"attributed from the record"
				),
			)
		)
		findings.append(
			CapabilityFinding(
				capability=HarnessCapability.CONTEXT_FILES_DISABLED,
				outcome=(
					ProbeOutcome.CONFIRMED
					if self.spec.supports_context_file_flag and exit_code == 0
					else (
						ProbeOutcome.ABSENT
						if self.spec.supports_context_file_flag
						else ProbeOutcome.INCONCLUSIVE
					)
				),
				attempted=(
					"invoked with the context-file-disabling flag (FR-150)"
					if self.spec.supports_context_file_flag
					else "no context-file flag is configured for this harness"
				),
				observed=(
					f"invocation carrying the flag exited {exit_code}"
					if self.spec.supports_context_file_flag and exit_code == 0
					else (
						f"invocation carrying the flag exited {exit_code}, so the flag was not "
						"accepted cleanly"
						if self.spec.supports_context_file_flag
						else "this harness exposes no context-file switch in the configured argv, "
						"so FR-150 cannot be satisfied here and the injection route R27 remains "
						"open for it"
					)
				),
			)
		)
		findings.append(extras[HarnessCapability.BUDGET_CONTROL])
		# MODEL_RESOLVED is decidable in *both* directions here, which no other row is: the
		# harness names its own failure, so a refusal is a positive observation and a clean
		# run with a record is a positive observation of the opposite. The string is data
		# (FR-161), so a deployment can teach the probe its harness's wording rather than
		# wait for a source change.
		pattern = self.spec.model_error_pattern
		refusal = next(
			(line.strip() for line in child_output.splitlines() if pattern and pattern in line),
			None,
		)
		if refusal is not None:
			model_outcome = ProbeOutcome.ABSENT
			model_reason = (
				f"the harness rejected `{self.model}` in its own words -- {refusal!r}. The "
				"identifier is resolved by the harness's registry, not by the model server, so "
				"a tag the server serves can still be one the harness refuses"
			)
		elif not pattern:
			model_outcome = ProbeOutcome.INCONCLUSIVE
			model_reason = (
				"this harness declares no model-resolution error string, so a clean exit cannot "
				"be separated from a failure the probe does not know how to read (FR-153)"
			)
		elif timed_out:
			model_outcome = ProbeOutcome.INCONCLUSIVE
			model_reason = (
				f"the run did not finish within {budget:.0f}s, so it neither resolved nor "
				"rejected the model"
			)
		elif exit_code != 0:
			model_outcome = ProbeOutcome.INCONCLUSIVE
			model_reason = (
				f"the run exited {exit_code} without the declared refusal string, so the "
				"failure is unattributed: this may be the model, and it may be anything else"
			)
		elif not records:
			model_outcome = ProbeOutcome.INCONCLUSIVE
			model_reason = (
				"the run exited 0 but left no readable session record, so no work was "
				"witnessed and nothing shows which model did it"
			)
		else:
			model_outcome = ProbeOutcome.CONFIRMED
			model_reason = (
				f"`{self.model}` was accepted and the run exited 0 with a readable session record"
			)
		findings.append(
			CapabilityFinding(
				capability=HarnessCapability.MODEL_RESOLVED,
				outcome=model_outcome,
				attempted=(
					f"dispatched with `--model {self.model}` and read the child's output for "
					f"the harness's own model-resolution error"
					if self.spec.model_error_pattern
					else "no model-resolution error string is configured for this harness"
				),
				observed=model_reason,
			)
		)
		# BOOTSTRAP_EMPTY_REPO is observable, because the probe runs with the workspace as
		# cwd and therefore starts cold on a fresh deployment. The outcome is the predicate
		# below -- one source of truth -- and the chain only explains the reason it failed.
		bootstrapped = entries_before == 0 and exit_code == 0 and not timed_out and bool(records)
		if entries_before is None:
			bootstrap_reason = (
				"the workspace did not exist when the run started, so the harness created "
				"it and the cold start this row is about was never entered"
			)
		elif entries_before > 0:
			bootstrap_reason = (
				f"the workspace already held {entries_before} entries when the run started, "
				"so this invocation is not a cold start and cannot witness one; the first "
				"probe on a fresh deployment is, and a used workspace is not the question "
				"this row answers"
			)
		elif timed_out:
			bootstrap_reason = (
				f"the run did not finish within {budget:.0f}s in an empty workspace, so "
				"nothing about bootstrapping was witnessed"
			)
		elif exit_code != 0:
			bootstrap_reason = (
				f"the run exited {exit_code} in an empty workspace; one invocation cannot "
				"separate 'the harness cannot bootstrap' from 'the model declined' "
				"(FR-153) -- a positive observation is decidable and is taken, and only the "
				"negative is left inconclusive"
			)
		elif not records:
			bootstrap_reason = (
				"the run exited 0 in an empty workspace but left no readable session "
				"record, so there is nothing to inspect and no capability to claim"
			)
		else:
			bootstrap_reason = (
				"the workspace held nothing when the run started and the harness exited 0 "
				"with a session record, so it does begin work in a tree with no repository "
				"and no files (FR-135)"
			)
		findings.append(
			CapabilityFinding(
				capability=HarnessCapability.BOOTSTRAP_EMPTY_REPO,
				outcome=(ProbeOutcome.CONFIRMED if bootstrapped else ProbeOutcome.INCONCLUSIVE),
				attempted=(
					"dispatched a real goal with the workspace as cwd and counted its entries "
					"immediately before the run (found "
					f"{'no directory' if entries_before is None else entries_before})"
				),
				observed=bootstrap_reason,
			)
		)
		findings.append(extras[HarnessCapability.SANDBOXABLE])
		findings.append(extras[HarnessCapability.CONCURRENT])
		findings.append(extras[HarnessCapability.STORE_ISOLATED])
		findings.append(compaction)

		profile = HarnessProfile(
			name=self.spec.name,
			command=argv,
			probed_at=now(),
			findings=tuple(findings),
			version=await self._read_version(),
			manifest_path=str(files[0]) if files else None,
			model=self.model,
		)
		assert len(profile.findings) == len(HarnessCapability), (
			"probe must report on every capability: got {len(profile.findings)} "
			f"of {len(HarnessCapability)}"
		)
		return profile

	async def invoke(
		self,
		argv: Sequence[str],
		*,
		timeout: float,
		session_id: str,
	) -> tuple[int | None, str, str, bool, Path | None, int | None]:
		"""Run one session that is not a plan step (FR-167's research run).

		:meth:`dispatch` is shaped by the plan: it renders a step goal, gates on a
		probe, and produces a :class:`~sofact.views.DispatchRecord`. A research run
		shares the session mechanics — argv, workspace, record parsing, token
		accounting — but none of the plan shape, so it goes through this thinner door.
		The caller builds ``argv`` with :meth:`build_argv` and owns the goal text; this
		method owns the process, the record it left, and the tokens the record
		reports. The last two elements are the session record's path (``None`` when
		the run wrote nothing) and the usage total (``None`` when unmeasured —
		NFR-024's other direction), so the caller records observations without
		re-globbing or re-parsing.
		"""
		exit_code, stdout, stderr, timed_out = await self._invoke(
			argv, timeout=timeout, session_id=session_id
		)
		files = await self.session_files(session_id)
		tokens: int | None = None
		if files:
			try:
				records = await self.read_records(files[0])
				tokens = parse_usage(records, self.spec)
			except HarnessSessionUnreadable:
				tokens = None
		return exit_code, stdout, stderr, timed_out, files[0] if files else None, tokens

	# ------------------------------------------------------- the extra attempts

	def _unattempted(self, capability: HarnessCapability, why: str) -> CapabilityFinding:
		"""One row that reports *why* nothing was attempted, rather than the fact of nothing."""
		return CapabilityFinding(
			capability=capability,
			outcome=ProbeOutcome.INCONCLUSIVE,
			attempted=f"no attempt was made for {capability.value}",
			observed=why,
		)

	async def _probe_extras(
		self,
		*,
		deep: bool,
		budget: float,
		skip_reason: str | None,
	) -> dict[HarnessCapability, CapabilityFinding]:
		"""The four rows that need more than one child, attempted together and gated.

		They run as a group *after* the primary attempt has finished, because a probe is a
		statement about what this deployment can do, and a deployment whose children
		contend for one GPU would produce rows that describe the contention rather than the
		harness. Each extra is a differential in its own scratch directory, so none of them
		can be confused by the primary run's leftovers or by another extra's.
		"""
		capabilities = (
			HarnessCapability.SANDBOXABLE,
			HarnessCapability.CONCURRENT,
			HarnessCapability.BUDGET_CONTROL,
			HarnessCapability.STORE_ISOLATED,
		)
		if not deep:
			why = (
				"deep probing was not requested (--quick), so this attempt was not made; an "
				"attempt that was skipped and an attempt that found nothing are different "
				"facts, and this row reports the first"
			)
			return {capability: self._unattempted(capability, why) for capability in capabilities}
		if skip_reason is not None:
			return {
				capability: self._unattempted(capability, skip_reason)
				for capability in capabilities
			}
		sandbox, concurrent, capped, isolated = await asyncio.gather(
			self._probe_sandboxable(budget=budget),
			self._probe_concurrent(budget=budget),
			self._probe_budget_control(budget=budget),
			self._probe_store_isolated(budget=budget),
		)
		return {
			HarnessCapability.SANDBOXABLE: sandbox,
			HarnessCapability.CONCURRENT: concurrent,
			HarnessCapability.BUDGET_CONTROL: capped,
			HarnessCapability.STORE_ISOLATED: isolated,
		}

	def _scratch(self, session_id: str, name: str = "work") -> Path:
		"""A per-run directory beside the sessions, one level below the escape target.

		``<session-dir>/.probe/<session-id>/work``: the parent is where the sandbox probe's
		child is told to escape *to*, and it is per-run so that a stale marker from an
		earlier probe can never be read as this one's evidence.
		"""
		directory = self.session_dir / ".probe" / session_id / name
		directory.mkdir(parents=True, exist_ok=True)
		return directory

	async def _probe_store_isolated(self, *, budget: float) -> CapabilityFinding:
		"""Whether the spec's environment actually contains the child's private store.

		OpenRig states the hazard plainly about its own isolation variable: changing it
		alone does not isolate provider configuration. SoFact's specs isolate the same way
		-- ``CLAUDE_CONFIG_DIR`` for claude, ``OPENCODE_DB`` + ``OPENCODE_TEST_HOME`` for
		opencode -- and a spec field that *looks* like a boundary and has never been
		observed to bound anything is the hazard S26 names (FR-019).

		The instrument is a differential with a **control arm**, because one arm cannot
		answer it. Both arms run the same goal in their own workspace with ``HOME`` pointed
		at a fresh empty directory; they differ in exactly one thing -- whether the spec's
		``env`` is applied. The isolated arm leaving that HOME empty is only evidence if
		the control arm fills its own: the control proves a relocated ``HOME`` is a live
		variable for this harness, so the first arm's silence is containment rather than an
		instrument that cannot see anything. Without the control the row would report
		``CONFIRMED`` for a harness that never writes under ``HOME`` at all.

		Measured 2026-10-12 for claude: with ``CLAUDE_CONFIG_DIR`` applied the child left a
		fresh ``HOME`` holding zero files and wrote its record into the private store, and
		with the variable withheld it wrote ``$HOME/.claude/projects/<slug>/<session>.jsonl``.

		Only the keys named in :attr:`HarnessSpec.isolation_env` are varied. Everything else
		the spec sets -- a pinned model, npm's log level -- stays applied in both arms, so
		the difference between them is the containment claim and nothing else. A spec that
		names none is not measured here at all: it asserts no containment, and two children
		spent deciding a question nobody asked would be a row reported for its own sake.
		"""
		declared = self.spec.isolation_env
		if not declared:
			return self._unattempted(
				HarnessCapability.STORE_ISOLATED,
				(
					"this harness declares no containment variables (isolation_env), so there "
					"is nothing to apply and nothing to withhold. The row measures whether a "
					"spec's environment contains the child's store; a harness isolated by argv "
					"instead (pi's --session-dir) is not decided by it in either direction"
				),
			)
		scratch_id = self.session_id("probe-store")
		work_isolated = self._scratch(scratch_id, "store-isolated")
		work_control = self._scratch(scratch_id, "store-control")
		home_isolated = work_isolated.parent / "home-isolated"
		home_control = work_control.parent / "home-control"
		home_isolated.mkdir(parents=True, exist_ok=True)
		home_control.mkdir(parents=True, exist_ok=True)
		iso_id, ctl_id = self.session_id("probe-store-a"), self.session_id("probe-store-b")
		# The control arm keeps every other spec variable and drops only the declared
		# containment ones: one thing varies, so the difference is attributable.
		rest = {
			key: value
			for key, value in self.spec.formatted_env(self._slots(ctl_id)).items()
			if key not in declared
		}
		isolated = self.variant(workspace=work_isolated, env={"HOME": str(home_isolated)})
		control = self.variant(
			workspace=work_control,
			env={"HOME": str(home_control), **rest},
			spec_env=False,
		)
		exit_a, _, stderr_a, timed_out_a = await isolated._invoke(
			isolated.build_argv(STORE_PROBE_GOAL, iso_id), timeout=budget, session_id=iso_id
		)
		exit_b, _, stderr_b, timed_out_b = await control._invoke(
			control.build_argv(STORE_PROBE_GOAL, ctl_id), timeout=budget, session_id=ctl_id
		)
		marker_a = work_isolated / "store-marker.txt"
		marker_b = work_control / "store-marker.txt"
		escaped = _files_under(home_isolated)
		witnessed = _files_under(home_control)
		variables = ", ".join(declared)
		attempted = (
			"ran the same goal twice with HOME pointed at a fresh empty directory "
			f"({home_isolated.name} and {home_control.name}): once with {variables} applied "
			"and once with them withheld (every other spec variable held constant), then "
			"counted the files each arm left under its own HOME"
		)
		if escaped:
			outcome, reason = (
				ProbeOutcome.ABSENT,
				(
					f"with its isolation variables applied the child still wrote {escaped} "
					f"file(s) under {home_isolated}, so {variables} do not contain its store: a "
					"dispatch would write into the operator's own home and two steps would share "
					"one history (FR-019, FR-141)"
				),
			)
		elif timed_out_a or exit_a != 0 or not marker_a.exists():
			outcome, reason = (
				ProbeOutcome.INCONCLUSIVE,
				(
					f"the isolated arm did no work (exit {exit_a}, timed out {timed_out_a}, "
					f"{marker_a.name} {'written' if marker_a.exists() else 'absent'}), so its "
					"HOME being empty says nothing about where its store went"
					+ (f"; stderr said {stderr_a.strip()[:200]!r}" if stderr_a.strip() else "")
				),
			)
		elif timed_out_b or exit_b != 0 or not marker_b.exists():
			outcome, reason = (
				ProbeOutcome.INCONCLUSIVE,
				(
					f"the control arm did no work (exit {exit_b}, timed out {timed_out_b}, "
					f"{marker_b.name} {'written' if marker_b.exists() else 'absent'}), so there "
					"is nothing showing that a fresh HOME is a live variable for this harness "
					"and the isolated arm's empty HOME cannot be read as containment"
					+ (f"; stderr said {stderr_b.strip()[:200]!r}" if stderr_b.strip() else "")
				),
			)
		elif witnessed == 0:
			outcome, reason = (
				ProbeOutcome.INCONCLUSIVE,
				(
					f"the control arm -- the spec's env withheld -- also left {home_control} "
					"empty, so this harness writes nothing under a fresh HOME whether or not its "
					"isolation variables are applied. The instrument cannot see this harness's "
					"store, so the isolated arm's empty HOME is not evidence that it was "
					"contained, and this row reports a limit of the probe rather than a property "
					"of the harness (ADR-0019)"
				),
			)
		else:
			outcome, reason = (
				ProbeOutcome.CONFIRMED,
				(
					f"with {variables} applied the child left {home_isolated} empty, and with "
					f"them withheld it wrote {witnessed} file(s) under {home_control} -- so the "
					"variables are what contained the store, and the private store SoFact reads "
					"is the only one the run touched (FR-019)"
				),
			)
		return CapabilityFinding(
			capability=HarnessCapability.STORE_ISOLATED,
			outcome=outcome,
			attempted=attempted,
			observed=reason,
		)

	async def _probe_sandboxable(self, *, budget: float) -> CapabilityFinding:
		"""One confined child, told to work inside its directory and then to try to escape.

		The escape attempt is the instrument. A confined child leaves no escape file because
		its tools forbid one; an unconfined child leaves one because it does not. A child
		that did no work at all leaves neither, which is why the inside marker gates both
		verdicts -- the absence of an escape file only means something once the run has
		proved it was working.

		This is a claim about a *tool set*: confinement here is SoFact's, not the harness's,
		so the finding names the set it used and the operator can narrow it and probe again.
		"""
		# Translated, not raw: the row is a claim about the set the *child* was handed, and
		# a set the harness does not recognise is the no-tools case wearing the operator's
		# spelling. Measuring the untranslated string would report confinement for a child
		# that had no tools to escape with, which is the one answer this row must not give
		# by accident.
		tools = self.render_tools(self.spec.confinement_tools or self.tools)
		session_id = self.session_id("probe-sandbox")
		work = self._scratch(session_id)
		confined = self.variant(workspace=work, tools=tools)
		argv = confined.build_argv(PROBE_SANDBOX_GOAL, session_id)
		exit_code, _stdout, stderr, timed_out = await confined._invoke(
			argv, timeout=budget, session_id=session_id
		)
		inside = work / "inside-marker.txt"
		escape = work.parent / "escape-marker.txt"
		attempted = (
			f"ran one child in {work} with tools {tools!r}, told to write "
			f"{inside.name} there and then to write {escape.name} one directory above"
		)
		if escape.exists():
			outcome = ProbeOutcome.ABSENT
			reason = (
				f"the child wrote {escape} outside the directory it was confined to, so "
				f"tools {tools!r} do not confine it: a step that wandered would write into "
				"the checkout, the home directory, or a sibling module's worktree (FR-141)"
			)
		elif inside.exists():
			outcome = ProbeOutcome.CONFIRMED
			reason = (
				f"the child did the work inside {work} and left no {escape.name} above it, "
				f"so tools {tools!r} confine it to the directory it was given. The escape "
				"was attempted rather than omitted, because the goal asked for it"
			)
		else:
			outcome = ProbeOutcome.INCONCLUSIVE
			reason = (
				f"neither {inside.name} nor {escape.name} appeared (exit {exit_code}"
				f"{' after being killed at the cap' if timed_out else ''}), so the child did "
				"no work and neither confinement nor its absence was witnessed"
				+ (f"; stderr said {stderr.strip()[:200]!r}" if stderr.strip() else "")
			)
		return CapabilityFinding(
			capability=HarnessCapability.SANDBOXABLE,
			outcome=outcome,
			attempted=attempted,
			observed=reason,
		)

	async def _probe_concurrent(self, *, budget: float) -> CapabilityFinding:
		"""Two children at once with distinct session ids, and whether their records collide.

		This is the question FR-142's wave scheduling turns on: two steps dispatched in
		parallel must not be able to overwrite each other's history. Colliding record paths
		are a positive observation of the failure, which is what makes the row decidable
		without waiting for a real wave to corrupt a real build.
		"""
		first, second = self.session_id("probe-a"), self.session_id("probe-b")
		goal = DEFAULT_PROBE_GOAL
		results = await asyncio.gather(
			self._invoke(self.build_argv(goal, first), timeout=budget, session_id=first),
			self._invoke(self.build_argv(goal, second), timeout=budget, session_id=second),
		)
		(exit_a, _, _, timed_out_a), (exit_b, _, _, timed_out_b) = results
		files_a, files_b = await self.session_files(first), await self.session_files(second)
		attempted = (
			f"ran two children simultaneously with session ids {first} and {second} in the "
			"same workspace and session directory, and compared the records each produced"
		)
		if timed_out_a or timed_out_b:
			outcome, reason = (
				ProbeOutcome.INCONCLUSIVE,
				(
					f"one of the two simultaneous runs did not finish within {budget:.0f}s, so "
					"whether they collide was not witnessed"
				),
			)
		elif exit_a != 0 or exit_b != 0:
			outcome, reason = (
				ProbeOutcome.INCONCLUSIVE,
				(
					f"the two simultaneous runs exited {exit_a} and {exit_b}, so neither of them "
					"did the work a collision would have been observed on"
				),
			)
		elif not files_a or not files_b:
			outcome, reason = (
				ProbeOutcome.INCONCLUSIVE,
				(
					"one of the two simultaneous runs left no readable session record, so there "
					"is nothing to compare"
				),
			)
		elif files_a[0] == files_b[0]:
			outcome, reason = (
				ProbeOutcome.ABSENT,
				(
					f"both simultaneous sessions wrote to {files_a[0].name}, so two steps running "
					"at once overwrite each other's history and a wave would destroy the evidence "
					"for half of itself (FR-142)"
				),
			)
		else:
			outcome, reason = (
				ProbeOutcome.CONFIRMED,
				(
					f"two simultaneous sessions wrote {files_a[0].name} and {files_b[0].name} -- "
					"distinct records, so a wave can run concurrently without one session's "
					"history clobbering another's"
				),
			)
		return CapabilityFinding(
			capability=HarnessCapability.CONCURRENT,
			outcome=outcome,
			attempted=attempted,
			observed=reason,
		)

	async def _probe_budget_control(self, *, budget: float) -> CapabilityFinding:
		"""Two children with a checkable artefact: one under a cap, one with no cap.

		The cap is rendered into the argv the spec declares, so this row is decidable only
		for a harness that *has* one. A harness with no budget flag is not a gap in the
		probe -- there is nothing to attempt -- and the row says which it is.

		Nothing depends on the answer (FR-140: SoFact holds the wall clock), which is why an
		unwitnessed cap is reported rather than treated as a missing capability.
		"""
		if not self.spec.budget_argv:
			return CapabilityFinding(
				capability=HarnessCapability.BUDGET_CONTROL,
				outcome=ProbeOutcome.INCONCLUSIVE,
				attempted="looked for a budget flag in the configured argv",
				observed=(
					f"harness {self.spec.name!r} declares no budget flag, so a cap cannot be "
					"attempted at all; SoFact's own wall clock is what holds the budget "
					"(FR-140), so nothing about dispatch depends on the harness having one"
				),
			)
		work_a = self._scratch(self.session_id("probe-budget-a"))
		work_b = self._scratch(self.session_id("probe-budget-b"))
		capped = self.variant(workspace=work_a)
		uncapped = self.variant(workspace=work_b)
		flag = tuple(part.format(budget=PROBE_BUDGET_SLOT) for part in self.spec.budget_argv)
		base = capped.build_argv(PROBE_BUDGET_GOAL, self.session_id("probe-cap-a"))
		# The goal must stay the final argument (FR-139), so a flag fragment is inserted
		# before it rather than appended. One insert, and the same assertion guards both.
		argv_a = (*base[:-1], *flag, base[-1])
		assert argv_a[-1] == PROBE_BUDGET_GOAL, "the budget flag must not displace the goal"
		rendered = " ".join(flag)
		cap_id = self.session_id("probe-cap-a")
		plain_id = self.session_id("probe-cap-b")
		exit_a, _, stderr_a, timed_out_a = await capped._invoke(
			argv_a, timeout=budget, session_id=cap_id
		)
		exit_b, _, _stderr_b, timed_out_b = await uncapped._invoke(
			uncapped.build_argv(PROBE_BUDGET_GOAL, plain_id), timeout=budget, session_id=plain_id
		)
		marker_a, marker_b = work_a / "budget-marker.txt", work_b / "budget-marker.txt"
		attempted = (
			f"ran the same goal twice in {work_a} and {work_b}: once with {rendered!r} "
			f"({self.spec.budget_argv} rendered at {PROBE_BUDGET_SLOT}) and once without it, "
			f"then checked whether {marker_a.name} appeared either time"
		)
		if timed_out_a or exit_a != 0:
			outcome, reason = (
				ProbeOutcome.INCONCLUSIVE,
				(
					f"the capped run exited {exit_a} (timed out: {timed_out_a}), so the harness "
					f"did not accept {rendered!r} and no cap was in force to observe"
					+ (f"; stderr said {stderr_a.strip()[:200]!r}" if stderr_a.strip() else "")
				),
			)
		elif marker_a.exists():
			outcome, reason = (
				ProbeOutcome.ABSENT,
				(
					f"the run was capped at {rendered!r} and wrote {marker_a.name} anyway, so the "
					"flag is accepted and not honoured: it cannot be relied on to bound anything"
				),
			)
		elif timed_out_b or exit_b != 0 or not marker_b.exists():
			shortfall = (
				f"the uncapped run was killed at the {budget:.0f}s cap"
				if timed_out_b
				else (
					f"the uncapped run exited {exit_b}"
					if exit_b != 0
					else f"the uncapped run wrote no {marker_b.name}"
				)
			)
			outcome, reason = (
				ProbeOutcome.INCONCLUSIVE,
				(
					f"{shortfall}, so there was no uncapped work for the capped run's silence to "
					"be compared against: absence under a cap proves nothing about the cap"
				),
			)
		else:
			outcome, reason = (
				ProbeOutcome.CONFIRMED,
				(
					f"capped at {rendered!r} the run wrote nothing, and uncapped it wrote "
					f"{marker_b.name}, so the flag bounds the work it names"
				),
			)
		return CapabilityFinding(
			capability=HarnessCapability.BUDGET_CONTROL,
			outcome=outcome,
			attempted=attempted,
			observed=reason,
		)

	def _compaction_finding(self, records: tuple[dict[str, object], ...]) -> CapabilityFinding:
		"""Whether a compaction boundary was witnessed, read off the primary run's record.

		No extra child: a compaction is either in the record or it is not, and one short
		probe goal will not reach a context limit. So this row is ``CONFIRMED`` only on a
		*positive* observation -- a declared compaction event with turns on both sides of it
		-- and otherwise says exactly which part was missing (FR-153).
		"""
		declared = self.spec.compaction_event
		witnessed = bool(declared) and any(
			str(record.get("type")) == declared for record in records
		)
		continuations = parse_continuations(records, self.spec)
		attempted = (
			f"searched the primary session record for a declared compaction event "
			f"({declared!r}) and counted the turns the harness itself numbered"
			if declared
			else "looked for a compaction event type in the configured spec"
		)
		if not declared:
			outcome = ProbeOutcome.INCONCLUSIVE
			reason = (
				f"harness {self.spec.name!r} declares no compaction event, so a compaction "
				"could not be recognised in the record even if one happened"
			)
		elif witnessed and (continuations or 0) >= 1:
			outcome = ProbeOutcome.CONFIRMED
			reason = (
				f"the record carries {declared!r} and the harness numbered "
				f"{continuations} turn(s), so the session continued across a compaction "
				"boundary rather than ending at it (FR-135)"
			)
		elif witnessed:
			outcome = ProbeOutcome.INCONCLUSIVE
			reason = (
				f"the record carries {declared!r} but the harness numbered no turn, so a "
				"compaction is visible and survival across it is not"
			)
		else:
			outcome = ProbeOutcome.INCONCLUSIVE
			reason = (
				f"no {declared!r} appears in the record: one short probe goal never reaches "
				"a context limit, so this run neither triggered nor witnessed a compaction"
			)
		return CapabilityFinding(
			capability=HarnessCapability.GOAL_SURVIVES_COMPACTION,
			outcome=outcome,
			attempted=attempted,
			observed=reason,
		)

	# -------------------------------------------------------------- dispatch

	async def dispatch(
		self,
		step: GoalStep,
		plan: GoalPlan,
		*,
		profile: HarnessProfile | None = None,
		session_id: str | None = None,
		checkout: ModuleCheckout | None = None,
	) -> DispatchRecord:
		"""Run one plan step as one out-of-process session.

		Returns a record in every case, including the cases where nothing ran. A step
		that could not be dispatched is a recorded fact
		(:attr:`~sofact.views.StepOutcome.NOT_DISPATCHED`) rather than a missing row,
		because a missing row is indistinguishable from a step nobody got to.

		``checkout`` is the branch this step's work sits on (FR-100), established by the
		caller because git is the service's concern rather than the adapter's — the
		adapter runs a harness and does not manage repositories.
		"""
		if plan.step_by_id(step.id) is None:
			raise ValueError(f"step {step.id} is not in plan {plan.id}")
		session = session_id or uuid7str()
		argv = self.build_argv(step.goal.render(plan.goal_style), session)
		workspace = str(self.workspace)
		started = now()

		def record(
			*,
			outcome: StepOutcome,
			mode: DispatchMode,
			note: str,
			exit_code: int | None = None,
			stderr_tail: str | None = None,
			session_path: str | None = None,
			declared_complete: bool = False,
			declaration_note: str | None = None,
			goal_entry_observed: GoalEntry | None = None,
			tokens: int | None = None,
			continuations: int | None = None,
			violations: tuple[str, ...] = (),
		) -> DispatchRecord:
			ended = now()
			return DispatchRecord(
				id=uuid7str(),
				plan_id=plan.id,
				goal_id=plan.goal_id,
				step_id=step.id,
				step_ordinal=step.ordinal,
				harness=self.spec.name,
				mode=mode,
				outcome=outcome,
				model=self.model,
				model_source=self.model_source,
				argv=argv,
				workspace=workspace,
				budget=step.budget,
				started_at=started,
				ended_at=ended,
				wall_clock_seconds=max(0.0, (ended - started).total_seconds()),
				goal_hash=step.goal_hash,
				contract_hash=plan.contract_hash,
				declared_complete=declared_complete,
				declaration_note=declaration_note,
				note=note,
				exit_code=exit_code,
				tokens_observed=tokens,
				continuations_observed=continuations,
				goal_entry_observed=goal_entry_observed,
				budget_violations=violations,
				session_path=session_path,
				stderr_tail=stderr_tail,
				checkout=checkout,
				composition_hash=self.composition_hash,
				boundary=self.boundary,
			)

		if profile is None:
			return record(
				outcome=StepOutcome.NOT_DISPATCHED,
				mode=DispatchMode.SINGLE_SHOT,
				note=(
					f"harness {self.spec.name!r} was never probed, and FR-148 forbids assuming "
					"a capability because it was declared. Probe it first."
				),
			)
		if profile.name != self.spec.name:
			raise ValueError(
				f"profile is for {profile.name!r} but this adapter is {self.spec.name!r}; "
				"dispatching against the wrong capability record is not a recoverable error"
			)
		# The profile is a statement about one *configuration*, and the model is the slot most
		# likely to have been re-pointed since the probe. A profile measured with a different
		# model says nothing about this one, and a profile that watched the harness refuse the
		# model says the run would fail before any work started. Both are attributed here, in
		# the harness's own words, rather than left to surface as an unexplained exit code.
		if profile.model and profile.model != self.model:
			return record(
				outcome=StepOutcome.NOT_DISPATCHED,
				mode=DispatchMode.SINGLE_SHOT,
				note=(
					f"the recorded profile is for model {profile.model!r} but this dispatch would "
					f"use {self.model!r}; the capability findings describe the configuration that "
					"was measured, so probe this one before dispatching against it (FR-148)"
				),
			)
		if profile.model_resolved is ProbeOutcome.ABSENT:
			finding = profile.finding(HarnessCapability.MODEL_RESOLVED)
			return record(
				outcome=StepOutcome.NOT_DISPATCHED,
				mode=DispatchMode.SINGLE_SHOT,
				note=(
					f"the harness could not resolve the model {self.model!r}, so this is a "
					"model-resolution failure and not a producer failure; nothing was dispatched. "
					f"Observed: {finding.observed if finding else 'no finding recorded'}"
				),
			)
		mode = DispatchMode.GOAL if profile.supports_goal_dispatch else DispatchMode.SINGLE_SHOT
		if not profile.is_usable:
			return record(
				outcome=StepOutcome.NOT_DISPATCHED,
				mode=mode,
				note=(
					f"harness {self.spec.name!r} is unusable: it did not exit without reading "
					"stdin, so it cannot run unattended (FR-145)"
				),
			)
		if shutil.which(self.spec.argv[0]) is None:
			return record(
				outcome=StepOutcome.NOT_DISPATCHED,
				mode=mode,
				note=f"harness binary {self.spec.argv[0]!r} is no longer on PATH",
			)

		exit_code, _stdout, stderr, timed_out = await self._invoke(
			argv, timeout=step.budget.max_wall_clock_seconds, session_id=session
		)

		files = await self.session_files(session)
		session_path = str(files[0]) if files else None
		records: tuple[dict[str, object], ...] = ()
		if files:
			records = await self.read_records(files[0])

		violations: list[str] = []
		if timed_out:
			violations.append(
				f"wall-clock cap {step.budget.max_wall_clock_seconds:.0f}s exceeded; "
				"process killed by SoFact, which holds the budget (FR-140)"
			)

		declared = parse_completion(records, self.spec) if records else False
		tokens = parse_usage(records, self.spec) if records else None
		continuations = parse_continuations(records, self.spec) if records else None
		goal_entry = parse_goal_entry(records, self.spec) if records else None

		if (
			tokens is not None
			and step.budget.max_tokens is not None
			and tokens > step.budget.max_tokens
		):
			violations.append(
				f"token cap {step.budget.max_tokens} exceeded: observed {tokens} "
				"(observed after the fact, so recorded rather than enforced)"
			)
		if continuations is not None and continuations > step.budget.max_continuations:
			violations.append(
				f"continuation cap {step.budget.max_continuations} exceeded: "
				f"observed {continuations}"
			)

		if timed_out:
			outcome = StepOutcome.BUDGET_EXHAUSTED
		elif exit_code == 0:
			outcome = StepOutcome.COMPLETED
		else:
			outcome = StepOutcome.FAILED

		notes: list[str] = []
		if mode is DispatchMode.SINGLE_SHOT:
			notes.append(
				"goal mode unavailable; step ran single-shot with no continuation (FR-144)"
			)
		if not records:
			notes.append(
				"no session record was found, so nothing about this session was witnessed "
				"beyond the process exit"
			)
		if goal_entry is not None and not goal_entry.is_forced:
			notes.append(
				f"goal entry was {goal_entry.value}: the objective was delivered as a request "
				"the model may decline, not a forced entry (FR-153)"
			)
		if mode is DispatchMode.GOAL and goal_entry is not None and not goal_entry.is_forced:
			notes.append(
				"the probe claimed goal mode but this session shows no forced entry; treat "
				"that capability as unproven rather than acting on it"
			)
		if profile.model_resolved is ProbeOutcome.INCONCLUSIVE:
			notes.append(
				f"the probe could not decide whether the harness resolves {self.model!r}, so "
				"this run's outcome is attributed to the producer and an unresolved model "
				"would look the same (FR-153)"
			)

		return record(
			outcome=outcome,
			mode=mode,
			note="; ".join(notes) or "dispatched",
			exit_code=exit_code,
			stderr_tail=stderr[-DEFAULT_STDERR_TAIL_BYTES:] or None,
			session_path=session_path,
			declared_complete=declared,
			declaration_note=(
				(
					f"harness {self.spec.name!r} reported completion via "
					f"{'.'.join(self.spec.completion_reason_path)}"
					+ (
						f" on a {self.spec.completion_event!r} event"
						if self.spec.completion_event is not None
						else " in the session document"
					)
					+ ". This is a claim, not a finding: it changes no verdict (FR-138)."
				)
				if declared
				else (
					f"harness {self.spec.name!r} has no structured completion signal, so "
					"nothing was declared either way"
					if not self.spec.completion_reason_path
					else f"harness {self.spec.name!r} did not report completion"
				)
			),
			goal_entry_observed=goal_entry,
			tokens=tokens,
			continuations=continuations,
			violations=tuple(violations),
		)
