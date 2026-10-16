"""FR-168 — a transcript is a record, and the transcriber is declared rather than bundled.

The operator's request is to *say* what they want. The tempting implementation is to add a
speech-to-text dependency and call it, and the reason not to is the same reason this product
declares harnesses and manufacture backends rather than shipping them: a capability the
factory cannot verify is a capability it should describe, not one it should own.

So a transcriber is an argv template in a JSON table, resolved by name, launched as a child
process, and judged by the file it wrote. There is **no built-in transcriber**, and that is a
decision rather than an omission: no speech-to-text tool is a dependency of this product, so
there is no ambient one to fall back to, and a machine with none configured gets a refusal
that names the variable to set. A default here would be the factory guessing which model
heard the operator's voice.

**The transcript is read from the file the tool wrote, never from stdout.** Whisper's CLI
prints progress bars and timings to stdout beside the text, and a parser that stripped them
would be guessing where the transcript began. The artefact protocol is what makes the run
observable, which is ADR-0021's discipline applied one phase earlier.

The audio's SHA-256 is recorded with the transcript. A transcript whose digest is not the
digest of the file you passed is not a transcript of it, and without the field there would be
no way to tell — the same argument :class:`~sofact.views.DiffReview` makes about recording
the sha it reviewed rather than reading ``HEAD`` later.
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
from sofact.views import Transcript, now

__all__ = [
	"AUDIO_SUFFIXES",
	"TRANSCRIBERS",
	"ConfiguredTranscriberAdapter",
	"TranscriberRefusal",
	"TranscriberSpec",
	"load_transcriber_specs",
	"transcriber_spec_for",
]

AUDIO_SUFFIXES: Final[tuple[str, ...]] = (
	".wav",
	".mp3",
	".m4a",
	".flac",
	".ogg",
	".opus",
	".aiff",
	".aac",
	".webm",
	".mp4",
)
"""What the verb accepts as a recording.

A closed set rather than "any file", because the failure it prevents is passing a text file
by mistake and receiving a transcriber's complaint about a codec — a message that names the
wrong problem. The list is the formats the declared tools actually take, not a preference.
"""


class TranscriberRefusal(Exception):
	"""A transcriber could not be resolved, launched, or read. Never a silent empty text."""


@dataclass(frozen=True, slots=True)
class TranscriberSpec:
	"""A deployment's speech-to-text configuration (FR-168).

	Data rather than code, for :class:`~sofact.harness.HarnessSpec`'s reason: a deployment
	that wants a different model should describe it in a file, and "which transcriber heard
	this" should be one thing to read rather than a property of import order.
	"""

	name: str
	argv: tuple[str, ...]
	"""How to run the tool, as a template. ``{audio}`` is the recording's path.

	A template rather than a fixed argv because the binary's name is a deployment's
	business: ``whisper``, ``whisper-cli`` and ``mlx_whisper`` are the same idea on three
	hosts.
	"""

	text_glob: str = ""
	"""The file the tool writes the transcript to, relative to the working directory.

	Empty means the tool prints the transcript to stdout and writes no file, which is the
	one case where stdout is read. Named as a glob because several of these tools derive
	the output name from the input's stem.

	Defaulted rather than required, because empty is a *legal* declaration and not a
	missing one: a deployment whose tool writes to stdout says so by omitting the field,
	and a required field would make that spec unconstructible from a table — the reader
	would raise ``TypeError`` on the very shape the docstring above permits.
	"""

	text_key: str = ""
	"""For a JSON artefact, the key path holding the text. Empty for plain text."""

	model: str = ""
	"""The model id, recorded with the transcript. Empty when the tool declares none."""

	expect_exit_code: int = 0
	notes: str = ""

	def __post_init__(self) -> None:
		assert self.name.strip(), "a transcriber spec names itself"
		assert self.argv, "a transcriber spec names the command it runs"
		joined = " ".join(self.argv)
		assert "{audio}" in joined, (
			f"the {self.name} argv must name the audio, or the tool is run on nothing and "
			"the transcript is of nothing"
		)
		assert self.text_glob or self.text_key == "", (
			f"the {self.name} spec names a JSON key ({self.text_key!r}) but no file to read "
			"it from, so the key can never be looked up"
		)

	@classmethod
	def from_mapping(cls, name: str, payload: Mapping[str, object]) -> TranscriberSpec:
		"""Build a spec from a JSON-shaped mapping, refusing unknown fields by name.

		A misspelled ``text_glb`` that silently fell back to empty would switch the reader
		from the artefact to stdout, which is worse than an error: the tool would run, a
		transcript would appear, and it would be the progress bars rather than the words.
		"""
		declared = {field.name for field in fields(cls)}
		unknown = sorted(set(payload) - declared)
		if unknown:
			raise ValueError(f"transcriber {name!r}: unknown field(s) {unknown}")
		missing = [field for field in ("argv",) if field not in payload]
		if missing:
			raise ValueError(f"transcriber {name!r}: missing field(s) {missing}")
		changes: dict[str, object] = {"name": name}
		for field in ("text_glob", "text_key", "model", "notes"):
			if field in payload:
				changes[field] = _text(payload[field], field, name)
		changes["argv"] = _texts(payload["argv"], "argv", name)
		if "expect_exit_code" in payload:
			changes["expect_exit_code"] = _int(
				payload["expect_exit_code"], "expect_exit_code", name
			)
		return cls(**changes)  # pyright: ignore[reportArgumentType]


def _text(value: object, field: str, name: str) -> str:
	if not isinstance(value, str):
		raise ValueError(f"transcriber {name!r}: {field} must be a string")
	return value


def _int(value: object, field: str, name: str) -> int:
	if isinstance(value, bool) or not isinstance(value, int):
		raise ValueError(f"transcriber {name!r}: {field} must be an integer")
	return value


def _texts(value: object, field: str, name: str) -> tuple[str, ...]:
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError(f"transcriber {name!r}: {field} must be an array of strings")
	items = cast("Sequence[object]", value)
	out: list[str] = []
	for item in items:
		if not isinstance(item, str):
			raise ValueError(f"transcriber {name!r}: {field} must contain only strings")
		out.append(item)
	return tuple(out)


def _str_keyed(value: object) -> TypeGuard[Mapping[str, object]]:
	if not isinstance(value, dict):
		return False
	obj = cast("Mapping[object, object]", value)
	return all(isinstance(key, str) for key in obj)


TRANSCRIBERS: Final[dict[str, TranscriberSpec]] = {}
"""The built-in table, and it is deliberately empty (FR-168).

No speech-to-text tool is a dependency of this product. A built-in entry would name a
binary that may not exist, and the failure would surface as a launch error rather than as
the configuration problem it is. A deployment registers its own with
``SOFACT_TRANSCRIBER_SPECS``.
"""


def load_transcriber_specs(path: Path) -> dict[str, TranscriberSpec]:
	"""Read a transcriber table from a JSON file (FR-168).

	Two shapes, as :func:`~sofact.harness.load_specs` accepts: ``{"transcribers": {...}}``
	and a bare ``{name: {...}}``. In the bare form no transcriber may be called
	``transcribers``, because that is the one key this reader treats as structure rather
	than as a name.
	"""
	try:
		text = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read transcriber table {path}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{path}: not valid JSON: {exc}") from exc
	if not _str_keyed(raw):
		raise ValueError(f"{path}: expected a JSON object")
	body: object = raw["transcribers"] if set(raw) == {"transcribers"} else raw
	if not _str_keyed(body):
		raise ValueError(f"{path}: expected an object of transcriber specs under 'transcribers'")
	specs: dict[str, TranscriberSpec] = {}
	for name, payload in body.items():
		if not _str_keyed(payload):
			raise ValueError(f"{path}: transcriber {name!r} must be an object")
		specs[name] = TranscriberSpec.from_mapping(name, payload)
	if not specs:
		raise ValueError(f"{path}: no transcribers; an empty table names no tool to run")
	return specs


def transcriber_spec_for(name: str | None, specs: Mapping[str, TranscriberSpec]) -> TranscriberSpec:
	"""Resolve one transcriber by name, refusing an unknown one by name.

	The refusal lists what *is* configured, because "unknown transcriber" is only
	actionable when it says what the alternatives were.
	"""
	if not specs:
		raise TranscriberRefusal(
			"no transcriber is configured, and this build ships none: set "
			"SOFACT_TRANSCRIBER_SPECS to a JSON table naming one, or SOFACT_TRANSCRIBER to a "
			"name in such a table (FR-168)"
		)
	if name is None:
		if len(specs) == 1:
			return next(iter(specs.values()))
		known = ", ".join(sorted(specs))
		raise TranscriberRefusal(
			f"{len(specs)} transcribers are configured ({known}); name one explicitly"
		)
	if name not in specs:
		known = ", ".join(sorted(specs))
		raise TranscriberRefusal(f"unknown transcriber {name!r}; configured: {known}")
	return specs[name]


def audio_digest(path: Path) -> tuple[str, int]:
	"""The recording's SHA-256 and size, refusing a path that is not a file.

	Both halves are recorded: the digest binds the transcript to *this* recording, and the
	size makes "a zero-byte file was passed" visible in the record rather than inferred from
	a transcriber that returned nothing.
	"""
	if not path.is_file():
		raise TranscriberRefusal(f"no such recording: {path}")
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for block in iter(lambda: handle.read(1 << 20), b""):
			digest.update(block)
	return digest.hexdigest(), path.stat().st_size


def _read_text_key(payload: object, key: str, name: str) -> str:
	"""Walk a dotted key path through a parsed JSON artefact, refusing a missing key.

	Refused rather than defaulted to empty: a JSON artefact whose shape is not what the
	spec declared means the tool is not the one the spec describes, and returning an empty
	transcript would record a silent nothing as a successful run.
	"""
	current: object = payload
	for part in key.split("."):
		if not isinstance(current, dict):
			raise TranscriberRefusal(
				f"transcriber {name!r}: {key!r} walks through a non-object at {part!r}"
			)
		mapping = cast("Mapping[str, object]", current)
		if part not in mapping:
			raise TranscriberRefusal(
				f"transcriber {name!r}: the artefact has no key {part!r} (from {key!r})"
			)
		current = mapping[part]
	if not isinstance(current, str):
		raise TranscriberRefusal(f"transcriber {name!r}: {key!r} is not a string")
	return current


def _extract(workdir: Path, spec: TranscriberSpec, stdout: str) -> str:
	"""The transcript, from the artefact the spec names or from stdout if it names none."""
	if not spec.text_glob:
		return stdout
	matches = sorted(workdir.glob(spec.text_glob))
	if not matches:
		raise TranscriberRefusal(
			f"transcriber {spec.name!r} wrote no file matching {spec.text_glob!r} in "
			f"{workdir}: the run produced no transcript to read"
		)
	artefact = matches[-1]
	try:
		raw = artefact.read_text(encoding="utf-8")
	except OSError as exc:
		raise TranscriberRefusal(f"cannot read {artefact}: {exc}") from exc
	if not spec.text_key:
		return raw
	try:
		payload: object = json.loads(raw)
	except ValueError as exc:
		raise TranscriberRefusal(f"{artefact}: not valid JSON: {exc}") from exc
	return _read_text_key(payload, spec.text_key, spec.name)


@dataclass(frozen=True, slots=True)
class ConfiguredTranscriberAdapter:
	"""Runs one declared transcriber and records what it produced (FR-168)."""

	spec: TranscriberSpec

	def build_argv(self, audio: Path, workdir: Path) -> tuple[str, ...]:
		"""The argv to launch, with the slots filled and nothing else substituted.

		``{audio}`` and ``{workspace}`` are the only two slots, and a part that names
		neither is passed through verbatim — so a spec cannot smuggle a shell expansion in,
		because there is no shell. ``asyncio.create_subprocess_exec`` takes an argv list and
		execs it directly.
		"""
		return tuple(
			part.replace("{audio}", str(audio)).replace("{workspace}", str(workdir))
			for part in self.spec.argv
		)

	async def transcribe(
		self,
		audio: Path,
		*,
		workdir: Path,
		timeout: float = 900.0,
		goal_id: str | None = None,
	) -> Transcript:
		"""Run the transcriber and record the result, successful or not.

		A non-zero exit is **recorded, not raised**: a transcriber that failed is a fact
		about the run, and :attr:`~sofact.views.Transcript.is_usable` is the predicate that
		refuses it. Raising here would lose the stderr that explains it.

		A launch failure is different and does raise: if the binary does not exist then
		nothing ran, there is no transcript to record, and the caller needs the OSError's
		message rather than a row saying a tool that is not installed produced nothing.
		"""
		digest, size = audio_digest(audio)
		workdir.mkdir(parents=True, exist_ok=True)
		argv = self.build_argv(audio, workdir)
		proc = await asyncio.create_subprocess_exec(
			*argv,
			cwd=str(workdir),
			stdin=asyncio.subprocess.DEVNULL,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)
		try:
			stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
		except TimeoutError as exc:
			proc.kill()
			await proc.wait()
			raise TranscriberRefusal(
				f"transcriber {self.spec.name!r} did not finish within {timeout:.0f}s; the "
				"recording may be longer than the declared tool can handle in one pass"
			) from exc
		stdout = stdout_b.decode("utf-8", errors="replace")
		stderr = stderr_b.decode("utf-8", errors="replace")
		exit_code = proc.returncode
		text = ""
		stderr_tail = stderr.strip()[-2000:] or None
		if exit_code == self.spec.expect_exit_code:
			text = _extract(workdir, self.spec, stdout)
		return Transcript(
			id=uuid7str(),
			goal_id=goal_id,
			audio_path=str(audio),
			audio_sha256=digest,
			audio_bytes=size,
			transcriber=self.spec.name,
			model=self.spec.model or None,
			argv=argv,
			exit_code=exit_code,
			text=text,
			stderr_tail=stderr_tail,
			at=now(),
		)
