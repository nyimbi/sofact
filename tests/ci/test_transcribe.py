"""FR-168 — a spoken goal, and the two things that make it evidence.

A real transcriber script, run as a real subprocess, writing a real transcript file. No
mocks: the point of the phase is that a *declared tool* turns a recording into words, and
a fake adapter would test the fake rather than the protocol.

Two properties carry the module. **The audio's digest is recorded beside the text**, so a
transcript is bound to the recording it came from — a tool that hashed its own input would
be vouching for itself, so SoFact takes the digest before the child runs. And **a
transcript that produced nothing is a real state**, reported rather than rounded into an
empty goal statement that would then be interrogated against nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sofact.service import FactoryService
from sofact.transcribe import (
	TRANSCRIBERS,
	TranscriberRefusal,
	TranscriberSpec,
	audio_digest,
	load_transcriber_specs,
	transcriber_spec_for,
)

TRANSCRIBER = '''\
"""A transcriber: writes a transcript file, or fails, or hears nothing."""
import json, sys
from pathlib import Path

mode, audio, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
if mode == "crash":
	sys.stderr.write("no model loaded\\n")
	sys.exit(4)
if mode == "silent":
	# A real tool that heard nothing writes an *empty* transcript and exits 0. It does not
	# write no file at all, which is a spec mismatch rather than silence and is refused by
	# the reader as such.
	(out / (audio.stem + ".txt")).write_text("", encoding="utf-8")
	sys.exit(0)
if mode == "json":
	(out / "transcript.json").write_text(
		json.dumps({"result": {"text": "Ship a meter reading service."}}), encoding="utf-8"
	)
elif mode == "stdout":
	print("Ship a meter reading service from standard output.")
else:
	(out / (audio.stem + ".txt")).write_text(
		"Ship a meter reading service that answers usage queries.\\n", encoding="utf-8"
	)
'''

SPEC_NAME = "synthetic-whisper"


def write_transcriber(tmp_path: Path) -> Path:
	script = tmp_path / "synthetic_transcriber.py"
	script.write_text(TRANSCRIBER, encoding="utf-8")
	return script


def audio_file(tmp_path: Path, *, name: str = "goal.wav", payload: bytes = b"RIFF....") -> Path:
	target = tmp_path / name
	target.write_bytes(payload)
	return target


def spec_for(
	tmp_path: Path,
	mode: str,
	*,
	text_glob: str = "*.txt",
	text_key: str = "",
	name: str = SPEC_NAME,
) -> TranscriberSpec:
	script = write_transcriber(tmp_path)
	return TranscriberSpec(
		name=name,
		argv=(sys.executable, str(script), mode, "{audio}", "{workspace}"),
		text_glob=text_glob,
		text_key=text_key,
	)


def service_with(home: Path, spec: TranscriberSpec) -> FactoryService:
	return FactoryService(home=home, llm=None, transcriber=spec)


# --------------------------------------------------------------------------- #
# the spec table
# --------------------------------------------------------------------------- #


def test_the_built_in_table_ships_no_transcriber() -> None:
	"""No speech-to-text tool is a dependency, so there is no ambient one to fall back to.

	An empty table is the *only* honest default: a factory that picked whichever binary
	happened to be installed would record a producer nobody chose, and the transcript's
	``transcriber`` field would name a tool the operator never configured.
	"""
	assert TRANSCRIBERS == {}


def test_a_spec_without_an_audio_slot_is_refused() -> None:
	"""The slot is what makes the argv a template rather than a fixed command."""
	with pytest.raises(AssertionError, match="must name the audio"):
		TranscriberSpec(name="broken", argv=("whisper", "--out", "here"), text_glob="*.txt")


def test_a_spec_naming_a_json_key_and_no_file_is_refused() -> None:
	"""A key with no file to read it from can never be looked up."""
	with pytest.raises(AssertionError, match="but no file to read it from"):
		TranscriberSpec(name="broken", argv=("whisper", "{audio}"), text_glob="", text_key="text")


def test_resolving_no_name_with_no_table_names_the_variable() -> None:
	"""No transcriber configured is a sentence about configuration, not an ImportError."""
	with pytest.raises(TranscriberRefusal, match="SOFACT_TRANSCRIBER_SPECS"):
		transcriber_spec_for(None, {})


def test_a_misspelled_spec_field_is_refused_rather_than_defaulted(tmp_path: Path) -> None:
	"""A typo that fell back to empty would switch the reader from the artefact to stdout.

	The tool would run, a transcript would appear, and it would be the progress bars
	rather than the words — which is why the refusal is on the *field name*.
	"""
	table = tmp_path / "transcribers.json"
	table.write_text(
		'{"transcribers": {"w": {"argv": ["whisper", "{audio}"], "text_glb": "*.txt"}}}',
		encoding="utf-8",
	)
	with pytest.raises(ValueError, match=r"unknown field\(s\) \['text_glb'\]"):
		load_transcriber_specs(table)


def test_a_bare_table_and_a_wrapped_one_both_load(tmp_path: Path) -> None:
	"""Two accepted shapes, because both are what a deployment writes by hand."""
	bare = tmp_path / "bare.json"
	bare.write_text('{"w": {"argv": ["whisper", "{audio}"]}}', encoding="utf-8")
	wrapped = tmp_path / "wrapped.json"
	wrapped.write_text('{"transcribers": {"w": {"argv": ["whisper", "{audio}"]}}}', encoding="utf-8")
	assert set(load_transcriber_specs(bare)) == {"w"}
	assert set(load_transcriber_specs(wrapped)) == {"w"}


def test_an_empty_table_is_refused(tmp_path: Path) -> None:
	"""An empty table leaves nothing to choose from, so it is not the same as no table."""
	table = tmp_path / "empty.json"
	table.write_text('{"transcribers": {}}', encoding="utf-8")
	with pytest.raises(ValueError, match="no transcribers"):
		load_transcriber_specs(table)


# --------------------------------------------------------------------------- #
# the digest
# --------------------------------------------------------------------------- #


def test_the_digest_is_of_the_bytes_on_disk(tmp_path: Path) -> None:
	import hashlib

	audio = audio_file(tmp_path, payload=b"RIFF-not-really")
	digest, size = audio_digest(audio)
	assert digest == hashlib.sha256(b"RIFF-not-really").hexdigest()
	assert size == len(b"RIFF-not-really")


def test_a_missing_audio_file_is_refused(tmp_path: Path) -> None:
	with pytest.raises(TranscriberRefusal, match="no such recording"):
		audio_digest(tmp_path / "nothing.wav")


# --------------------------------------------------------------------------- #
# the service path
# --------------------------------------------------------------------------- #


async def test_a_transcript_is_read_from_the_file_the_tool_wrote(tmp_path: Path) -> None:
	"""Not from stdout: the artefact is what the protocol is, and stdout is a progress bar."""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "file"))
	audio = audio_file(tmp_path)
	transcript = await service.speak(audio)
	assert transcript.is_usable
	assert "meter reading service" in transcript.text
	assert transcript.transcriber == SPEC_NAME
	assert transcript.exit_code == 0
	assert transcript.audio_sha256 == audio_digest(audio)[0]


async def test_a_json_artefact_is_read_by_key(tmp_path: Path) -> None:
	service = service_with(
		tmp_path / "home", spec_for(tmp_path, "json", text_glob="*.json", text_key="result.text")
	)
	transcript = await service.speak(audio_file(tmp_path))
	assert transcript.text == "Ship a meter reading service."


async def test_a_spec_with_no_glob_reads_stdout(tmp_path: Path) -> None:
	"""The one case where stdout is read, and it is declared rather than assumed."""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "stdout", text_glob=""))
	transcript = await service.speak(audio_file(tmp_path))
	assert "standard output" in transcript.text


async def test_a_crashed_transcriber_records_a_transcript_with_no_text(tmp_path: Path) -> None:
	"""A failure is a *record*, not an exception: the attempt is what explains the goal.

	The row is appended with the child's own stderr, so the operator reading the log sees
	the tool's words rather than SoFact's summary of them.
	"""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "crash"))
	transcript = await service.speak(audio_file(tmp_path))
	assert not transcript.is_usable
	assert transcript.exit_code == 4
	assert transcript.text == ""
	assert transcript.stderr_tail is not None and "no model loaded" in transcript.stderr_tail


async def test_a_zero_exit_with_no_text_is_not_usable(tmp_path: Path) -> None:
	"""A transcriber that heard nothing has not produced a statement.

	Both conjuncts of :attr:`Transcript.is_usable` are required, and this is the one the
	second exists for: an exit code of zero would otherwise make silence look like a
	transcript and open a goal from an empty string.
	"""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "silent"))
	transcript = await service.speak(audio_file(tmp_path))
	assert transcript.exit_code == 0
	assert not transcript.is_usable


async def test_the_transcript_is_recorded_in_the_log(tmp_path: Path) -> None:
	"""The attempt reaches the ledger, so a goal's provenance is readable afterwards."""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "file"))
	audio = audio_file(tmp_path)
	await service.speak(audio)
	recorded = await service.transcripts()
	assert len(recorded) == 1
	assert recorded[0].audio_sha256 == audio_digest(audio)[0]


async def test_a_goal_is_not_opened_by_transcribing(tmp_path: Path) -> None:
	"""The transcript is a record *about* a statement, not a replacement for one.

	``speak`` writes no goal: the caller still calls ``start`` with the text. A method
	that created one would put a machine's rendering of speech in the position the whole
	interrogation exists to treat as suspect.
	"""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "file"))
	await service.speak(audio_file(tmp_path))
	assert (await service.state()).latest_goal() is None


async def test_a_transcript_can_be_attributed_to_a_goal(tmp_path: Path) -> None:
	"""``goal_id`` is optional because transcription usually happens before there is one."""
	service = service_with(tmp_path / "home", spec_for(tmp_path, "file"))
	goal = await service.start("Ship a meter reading service.")
	transcript = await service.speak(audio_file(tmp_path), goal_id=goal.id)
	assert transcript.goal_id == goal.id
	assert [t.id for t in await service.transcripts(goal.id)] == [transcript.id]


async def test_transcribing_an_unknown_goal_is_refused(tmp_path: Path) -> None:
	service = service_with(tmp_path / "home", spec_for(tmp_path, "file"))
	with pytest.raises(KeyError, match="no such goal"):
		await service.speak(audio_file(tmp_path), goal_id="01a14149-0000-7000-8000-000000000000")
