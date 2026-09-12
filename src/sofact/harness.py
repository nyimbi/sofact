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
from sofact.views import (
	CapabilityFinding,
	DispatchMode,
	DispatchRecord,
	GoalEntry,
	GoalPlan,
	GoalStep,
	HarnessCapability,
	HarnessProfile,
	ProbeOutcome,
	StepOutcome,
	now,
)

__all__ = [
	"DSH_SPEC",
	"PI_SPEC",
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

DEFAULT_PROBE_GOAL: Final = "Reply with the single word: ready"
DEFAULT_PROBE_TIMEOUT_SECONDS: Final = 180.0
DEFAULT_DISPATCH_TIMEOUT_SECONDS: Final = 3600.0
DEFAULT_STDERR_TAIL_BYTES: Final = 2_048
_USAGE_REDUCERS: Final = frozenset({"sum", "max"})

# Which spec fields are JSON arrays of strings, which are plain strings, which are
# booleans, and which need bespoke handling. Kept as data so ``from_mapping`` has one
# loop per shape instead of a field-by-field transcription that would drift from the
# dataclass the first time a field was added.
_TUPLE_FIELDS: Final = (
	"completion_reason_path",
	"goal_event_types",
	"usage_path",
	"version_argv",
)
_STRING_FIELDS: Final = (
	"completion_reason_value",
	"notes",
	"session_glob",
	"usage_reduce",
)
_BOOL_FIELDS: Final = ("session_is_zstd", "supports_context_file_flag")

INCONCLUSIVE_NO_PROBE: Final = (
	"no probe implemented: one bounded invocation cannot witness this capability, "
	"so it is recorded as a coverage gap rather than assumed either way (FR-148)"
)


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

		``completion_reason_path`` and ``usage_path`` are both **relative to a record's
		``data`` block**, not to the record itself: every event on the wire is
		``{seq, time, type, data}``, so the envelope is stripped before either is walked.
	"""

	name: str
	argv: tuple[str, ...]
	env: tuple[tuple[str, str], ...] = ()
	session_glob: str = "**/*{session_id}*.jsonl"
	session_is_zstd: bool = False
	version_argv: tuple[str, ...] = ()
	completion_event: str | None = None
	completion_reason_path: tuple[str, ...] = ()
	completion_reason_value: str = "completed"
	usage_path: tuple[str, ...] = ()
	usage_reduce: str = "sum"
	goal_event_types: tuple[str, ...] = ()
	goal_entry: GoalEntry = GoalEntry.PROMPT
	supports_context_file_flag: bool = False
	notes: str = ""

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


def _env(value: object, name: str) -> tuple[tuple[str, str], ...]:
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError(f"harness {name!r}: env must be an array of [key, value] pairs")
	pairs = cast("Sequence[object]", value)
	out: list[tuple[str, str]] = []
	for pair in pairs:
		if isinstance(pair, str) or not isinstance(pair, Sequence):
			raise ValueError(f"harness {name!r}: each env entry must be a [key, value] pair")
		inner = cast("Sequence[object]", pair)
		items = tuple(inner)
		if len(items) != 2:
			raise ValueError(f"harness {name!r}: each env entry must have exactly two elements")
		key, val = items[0], items[1]
		if not isinstance(key, str) or not isinstance(val, str):
			raise ValueError(f"harness {name!r}: env keys and values must be strings")
		out.append((key, val))
	return tuple(out)


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
	session_glob="**/*{session_id}*.jsonl",
	session_is_zstd=False,
	version_argv=("pi", "--version"),
	completion_event=None,
	usage_path=(),
	goal_event_types=(),
	goal_entry=GoalEntry.PROMPT,
	supports_context_file_flag=True,
	notes=(
		"Measured 2026-09-12 against pi with a local ollama model. The session record is "
		"plain JSONL at <session-dir>/<iso-timestamp>_<session-id>.jsonl with top-level "
		"keys {cwd,id,timestamp,type,version}; observed types were session, model_change, "
		"thinking_level_change, message. It emits NO usage block and NO completion event, "
		"so this adapter can never corroborate a declaration and DeclarationPrecision "
		"stays unmeasured for it — 'unmeasured', not 'wrong'. This is FR-144's reduced-mode "
		"adapter and exists to test the interface (FR-058), not to be the production "
		"harness."
	),
)
"""``pi`` as measured: JSONL session record, no usage, no completion signal.

Supersedes the ``reported`` description in [S19] on the two points that matter to the
adapter — usage reporting and the absence of any structured completion — both of which
were observed directly rather than read.
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
	session_glob="**/session-{session_id}/session.v3.jsonl.zstd",
	session_is_zstd=True,
	version_argv=("dsh", "--version"),
	completion_event="turn/end",
	completion_reason_path=("reason", "kind"),
	completion_reason_value="completed",
	usage_path=("usage", "outputTokens"),
	usage_reduce="sum",
	goal_event_types=(),
	goal_entry=GoalEntry.PROMPT,
	supports_context_file_flag=False,
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


SPECS: Final[dict[str, HarnessSpec]] = {PI_SPEC.name: PI_SPEC, DSH_SPEC.name: DSH_SPEC}


# --------------------------------------------------------------------------- #
# session-record parsing
# --------------------------------------------------------------------------- #


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


def _data_of(record: Mapping[str, object]) -> Mapping[str, object] | None:
	"""The ``data`` block of a session record, or ``None`` if it has none."""
	value = record.get("data")
	return value if _is_mapping(value) else None


#: A goal shorter than this is a substring of ordinary absolute paths, so containment
#: cannot distinguish "the objective was baked into argv" from "a directory happens to
#: contain these letters". Real objectives are generated prose of hundreds of characters.
_MIN_GOAL_LENGTH_FOR_CONTAMINATION_CHECK: Final = 24


def parse_completion(records: Iterable[Mapping[str, object]], spec: HarnessSpec) -> bool:
	"""Whether the session recorded a *structured* completion declaration (FR-138).

	A harness with no completion signal returns ``False`` for every session, which is
	the honest answer: absence of a declaration is not a declaration of failure, and
	this flag is never consulted by the verifier either way.
	"""
	if spec.completion_event is None:
		return False
	for record in records:
		if record.get("type") != spec.completion_event:
			continue
		data = _data_of(record)
		if data is None:
			continue
		if _walk(data, spec.completion_reason_path) == spec.completion_reason_value:
			return True
	return False


def parse_usage(records: Iterable[Mapping[str, object]], spec: HarnessSpec) -> int | None:
	"""Tokens the producer reported spending, or ``None`` if it reports nothing.

	``spec.usage_path`` is walked against each record's ``data`` block, so a ``dsh``
	path is ``("usage", "outputTokens")`` and not ``("data", "usage", ...)``.

	``None`` and ``0`` are different answers. A harness that exposes no usage is
	*unmeasured*; reporting zero would be inventing a measurement, which NFR-024
	forbids in either direction.
	"""
	if not spec.usage_path:
		return None
	observed: list[int] = []
	for record in records:
		data = _data_of(record)
		if data is None:
			continue
		value = _walk(data, spec.usage_path)
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
	"""Turns the session ran, where the harness numbers them.

	``dsh`` writes ``turn/start``; ``pi`` writes nothing comparable, so this is ``None``
	there rather than a fabricated ``1``.
	"""
	_ = spec
	turns = sum(1 for record in records if record.get("type") == "turn/start")
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
		tools: str = "read,write,edit,bash",
		probe_timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
		env: Mapping[str, str] | None = None,
	) -> None:
		assert spec.name, "spec must be named"
		assert model.strip(), "a dispatch needs a model"
		assert probe_timeout > 0, f"probe timeout must be positive, got {probe_timeout}"
		self.spec = spec
		self.workspace = Path(workspace)
		self.session_dir = Path(session_dir)
		self.model = model
		self.tools = tools
		self.probe_timeout = probe_timeout
		self.env = dict(env or {})

	def __repr__(self) -> str:
		return f"ConfiguredHarnessAdapter({self.spec.name!r}, workspace={self.workspace})"

	def _slots(self, session_id: str) -> dict[str, str]:
		"""Everything an argv or env template may substitute."""
		return {
			"session_dir": str(self.session_dir),
			"session_id": session_id,
			"model": self.model,
			"tools": self.tools,
			"workspace": str(self.workspace),
		}

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
		"""Environment for the child; caller overrides win over spec env."""
		merged = {**os.environ, **self.spec.formatted_env(self._slots(session_id))}
		merged.update(self.env)
		return merged

	def session_files(self, session_id: str) -> tuple[Path, ...]:
		"""Session records matching this dispatch, newest first."""
		pattern = self.spec.session_glob.format(session_id=session_id)
		found = [p for p in self.session_dir.glob(pattern) if p.is_file()]
		return tuple(sorted(found, key=lambda p: p.stat().st_mtime, reverse=True))

	async def _read_records(self, path: Path) -> tuple[dict[str, object], ...]:
		"""Parse a session record, decompressing when the spec says so.

		Decompression shells out to ``zstd -dc`` because Python 3.13 has neither
		``compression.zstd`` nor a vendored binding, and adding a dependency to read one
		log file would be a poor trade.
		"""
		if self.spec.session_is_zstd:
			raw = await self._decompress(path)
		else:
			raw = path.read_text(encoding="utf-8", errors="replace")

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
		"""
		process = await asyncio.create_subprocess_exec(
			*argv,
			cwd=self.workspace,
			stdin=asyncio.subprocess.DEVNULL,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
			env=self._child_env(session_id),
		)
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

	# ----------------------------------------------------------------- probe

	async def probe(
		self,
		*,
		goal_text: str = DEFAULT_PROBE_GOAL,
		timeout: float | None = None,
	) -> HarnessProfile:
		"""Attempt the harness and record what was observed (FR-148).

		This runs a real, bounded invocation — never ``--help``. Capabilities that one
		bounded invocation cannot witness are recorded ``INCONCLUSIVE`` with an explicit
		reason, which is a *coverage gap in the probe* and is reported as one.
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
		session_id = f"probe-{uuid7str()[:8]}"
		argv = self.build_argv(goal_text, session_id)
		assert argv[-1] == goal_text, "probe must dispatch a real goal"
		exit_code, _stdout, _stderr, timed_out = await self._invoke(
			argv, timeout=budget, session_id=session_id
		)

		files = self.session_files(session_id)
		records: tuple[dict[str, object], ...] = ()
		if files:
			records = await self._read_records(files[0])

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
		findings.append(
			CapabilityFinding(
				capability=HarnessCapability.BUDGET_CONTROL,
				outcome=ProbeOutcome.INCONCLUSIVE,
				attempted="enforced the wall clock externally by killing the process (FR-140)",
				observed=(
					"SoFact's own cap is enforced and observable; whether the harness has an "
					"independent internal cap is not witnessed by one invocation, and by FR-140 "
					"nothing depends on it"
				),
			)
		)
		for capability in (
			HarnessCapability.SANDBOXABLE,
			HarnessCapability.CONCURRENT,
			HarnessCapability.BOOTSTRAP_EMPTY_REPO,
			HarnessCapability.GOAL_SURVIVES_COMPACTION,
		):
			findings.append(
				CapabilityFinding(
					capability=capability,
					outcome=ProbeOutcome.INCONCLUSIVE,
					attempted=f"no bounded attempt configured for {capability.value}",
					observed=INCONCLUSIVE_NO_PROBE,
				)
			)

		profile = HarnessProfile(
			name=self.spec.name,
			command=argv,
			probed_at=now(),
			findings=tuple(findings),
			version=await self._read_version(),
			manifest_path=str(files[0]) if files else None,
		)
		assert len(profile.findings) == len(HarnessCapability), (
			f"probe must report on every capability: got {len(profile.findings)} "
			f"of {len(HarnessCapability)}"
		)
		return profile

	# -------------------------------------------------------------- dispatch

	async def dispatch(
		self,
		step: GoalStep,
		plan: GoalPlan,
		*,
		profile: HarnessProfile | None = None,
		session_id: str | None = None,
	) -> DispatchRecord:
		"""Run one plan step as one out-of-process session.

		Returns a record in every case, including the cases where nothing ran. A step
		that could not be dispatched is a recorded fact
		(:attr:`~sofact.views.StepOutcome.NOT_DISPATCHED`) rather than a missing row,
		because a missing row is indistinguishable from a step nobody got to.
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

		files = self.session_files(session)
		session_path = str(files[0]) if files else None
		records: tuple[dict[str, object], ...] = ()
		if files:
			records = await self._read_records(files[0])

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
					f"harness {self.spec.name!r} reported completion via {self.spec.completion_event}. "
					"This is a claim, not a finding: it changes no verdict (FR-138)."
				)
				if declared
				else (
					f"harness {self.spec.name!r} has no structured completion signal, so "
					"nothing was declared either way"
					if self.spec.completion_event is None
					else f"harness {self.spec.name!r} did not report completion"
				)
			),
			goal_entry_observed=goal_entry,
			tokens=tokens,
			continuations=continuations,
			violations=tuple(violations),
		)
