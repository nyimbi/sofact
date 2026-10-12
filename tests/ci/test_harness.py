"""The FR-058 adapter, driven against real subprocesses.

No mocks. The harness here is a real Python program that really runs, really writes a
session record, and really exits (or is really killed). The only synthetic thing is the
*wire format*, and that is deliberate: a spec is a declarative claim about a wire format,
so the mapping from bytes on disk back to observations is exactly what needs testing.

The real `pi` and `dsh` are pinned by shape assertions on :data:`PI_SPEC` and
:data:`DSH_SPEC` instead of being run, because running them would make this suite depend
on a cloud model's uptime. What those assertions encode is what [S19] and [S21] measured.
"""

from __future__ import annotations

import dataclasses
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from synthetic import base_spec, db_spec, seed_store

from sofact.harness import (
	CLAUDE_SPEC,
	DSH_SPEC,
	OPENCODE_SPEC,
	PI_RESEARCH_SPEC,
	PI_SPEC,
	SPECS,
	ConfiguredHarnessAdapter,
	HarnessBinaryMissing,
	HarnessSessionUnreadable,
	HarnessSpec,
	parse_completion,
	parse_continuations,
	parse_goal_entry,
	parse_usage,
	spec_for,
)
from sofact.planner import compile_plan
from sofact.views import (
	Contract,
	GoalEntry,
	GoalPlan,
	GoalStep,
	HarnessCapability,
	HarnessProfile,
	OracleClass,
	OracleDeclaration,
	ProbeOutcome,
	StepOutcome,
	now,
)

# --------------------------------------------------------------------------- #
# a real, tiny harness
# --------------------------------------------------------------------------- #


def make_adapter(
	tmp_path: Path,
	spec: HarnessSpec,
	*,
	probe_timeout: float = 10.0,
) -> ConfiguredHarnessAdapter:
	"""Bind a spec to a real workspace and session directory under ``tmp_path``."""
	workspace = tmp_path / "workspace"
	workspace.mkdir(parents=True, exist_ok=True)
	return ConfiguredHarnessAdapter(
		spec,
		workspace=workspace,
		session_dir=tmp_path,
		model="synthetic-model",
		probe_timeout=probe_timeout,
	)


def adapter_for(
	tmp_path: Path,
	mode: str,
	*,
	name: str = "synthetic",
	zstd: bool = False,
	zstd_ext: str = "zstd",
	probe_timeout: float = 10.0,
) -> ConfiguredHarnessAdapter:
	"""The common case: the script above, in a given mode."""
	spec = base_spec(tmp_path, mode, name=name, zstd=zstd, zstd_ext=zstd_ext)
	return make_adapter(tmp_path, spec, probe_timeout=probe_timeout)


def _records(*rows: dict[str, object]) -> tuple[dict[str, object], ...]:
	return tuple(rows)


# --------------------------------------------------------------------------- #
# spec shape: what was measured, pinned so it cannot drift silently
# --------------------------------------------------------------------------- #


class TestMeasuredSpecs:
	def test_every_shipped_harness_has_a_spec(self) -> None:
		assert set(SPECS) == {"pi", "dsh", "claude", "opencode", "pi-research"}
		assert spec_for("pi") is PI_SPEC
		assert spec_for("dsh") is DSH_SPEC
		assert spec_for("claude") is CLAUDE_SPEC
		assert spec_for("opencode") is OPENCODE_SPEC
		assert spec_for("pi-research") is PI_RESEARCH_SPEC

	def test_unknown_harness_names_the_configured_set(self) -> None:
		with pytest.raises(KeyError, match="configured harnesses: claude, dsh, opencode, pi"):
			spec_for("omp")

	def test_the_research_spec_is_a_deliberate_variant_of_the_build_spec(self) -> None:
		"""FR-167: the same measured mechanics, with the two web-facing flags removed."""
		assert "pi-research" in SPECS
		assert spec_for("pi-research") is PI_RESEARCH_SPEC
		assert "--offline" not in PI_RESEARCH_SPEC.argv, "the research loop must search"
		assert "--no-extensions" not in PI_RESEARCH_SPEC.argv, (
			"the loop IS an installed extension, so this spec names it by omission"
		)
		assert "--no-extensions" in PI_SPEC.argv, "and the build spec still freezes them"
		assert PI_RESEARCH_SPEC.env == (
			("RESEARCH_MODEL", "{model}"),
			("npm_config_loglevel", "error"),
			("npm_config_audit", "false"),
			("npm_config_fund", "false"),
			("npm_config_progress", "false"),
		), (
			"the npm noise is silenced so a child failure's own error reaches the tool's "
			"500-character report window instead of being cut off behind the audit text"
		)
		assert PI_RESEARCH_SPEC.research_tools == ("deep_research", "super_deep_research")
		assert PI_SPEC.research_tools == (), "a build spec delegates no research tool"
		assert PI_RESEARCH_SPEC.session_glob == PI_SPEC.session_glob
		assert PI_RESEARCH_SPEC.usage_path == PI_SPEC.usage_path
		assert PI_RESEARCH_SPEC.model_error_pattern == PI_SPEC.model_error_pattern

	def test_pi_argv_matches_the_S19_measurement(self) -> None:
		assert PI_SPEC.argv[:2] == ("pi", "--mode")
		assert "--offline" in PI_SPEC.argv
		assert "--no-context-files" in PI_SPEC.argv
		assert "--no-extensions" in PI_SPEC.argv, (
			"installed packages auto-load into every pi session, so an unextended argv "
			"would hand a build producer whatever the operator has installed (FR-154)"
		)
		assert PI_SPEC.session_is_zstd is False
		assert PI_SPEC.usage_path == ("message", "usage", "output")

	def test_pi_has_no_completion_signal_so_precision_stays_unmeasured(self) -> None:
		"""The asymmetry with dsh is a measured fact, not an oversight."""
		assert PI_SPEC.completion_event is None
		assert DSH_SPEC.completion_event == "turn/end"

	def test_dsh_requires_explicit_home_and_writes_zstd(self) -> None:
		assert DSH_SPEC.env == (("DSH_HOME", "{session_dir}"),)
		assert DSH_SPEC.session_is_zstd is True
		assert DSH_SPEC.completion_reason_path == ("data", "reason", "kind")
		assert DSH_SPEC.completion_reason_value == "completed"

	def test_dsh_notes_record_the_headless_blocker_and_the_egress(self) -> None:
		"""An UNVERIFIED argv and an unmitigated egress route must stay visible."""
		low = DSH_SPEC.notes.lower()
		assert "unverified" in low
		assert "telemetry" in low

	def test_dsh_cannot_disable_context_files_but_pi_can(self) -> None:
		assert PI_SPEC.supports_context_file_flag is True
		assert DSH_SPEC.supports_context_file_flag is False

	def test_claude_argv_matches_the_2026_10_12_measurement(self) -> None:
		"""The `--` is load-bearing: `--tools` is variadic and would eat the goal."""
		assert CLAUDE_SPEC.argv[0] == "claude"
		assert "--print" in CLAUDE_SPEC.argv
		assert CLAUDE_SPEC.argv[-1] == "--", (
			"without the terminator the variadic --tools swallows the goal text as "
			"another tool name, and the child exits 1 asking for a prompt"
		)
		assert CLAUDE_SPEC.argv.index("--tools") < CLAUDE_SPEC.argv.index("--")
		assert CLAUDE_SPEC.env == (("CLAUDE_CONFIG_DIR", "{session_dir}"),), (
			"without this the child appends to the operator's own ~/.claude history"
		)
		assert CLAUDE_SPEC.session_glob == "**/projects/*/{session_id}.jsonl"
		assert CLAUDE_SPEC.session_is_zstd is False

	def test_claude_completion_is_a_stop_reason_not_an_exit_code(self) -> None:
		"""A real completion signal, unlike pi -- so precision is measurable for it."""
		assert CLAUDE_SPEC.completion_event == "assistant"
		assert CLAUDE_SPEC.completion_reason_path == ("message", "stop_reason")
		assert CLAUDE_SPEC.completion_reason_value == "end_turn"
		assert CLAUDE_SPEC.usage_path == ("message", "usage", "output_tokens"), (
			"the underscore spelling; not the dsh path and not the pi path"
		)

	def test_claude_tool_names_are_capitalised_and_translated(self) -> None:
		"""Measured: `--tools read,write` is ACCEPTED and leaves the producer with none.

		It exits 0, reports `terminal_reason: completed`, and writes nothing --
		the producer answers "I'll create that file" and stops. `--tools Read,Write`
		writes the file. So the spelling is not a formatting detail; a wrong name is a
		producer that cannot work while looking exactly like one that finished.
		"""
		assert CLAUDE_SPEC.tool_names, "claude needs the translation or every build is inert"
		assert dict(CLAUDE_SPEC.tool_names)["write"] == "Write"
		assert dict(CLAUDE_SPEC.tool_names)["read"] == "Read"

	def test_claude_notes_record_the_unconfined_child_and_the_egress(self) -> None:
		"""A measured negative and an unmitigated egress route must stay visible.

		`sandboxable: absent` is the row a reader is most likely to want rounded off,
		because it says the producer SoFact dispatches to can write anywhere. It is a
		measurement, not a caveat: a child told to escape wrote one directory above its
		workspace with `--tools Read,Write,Edit` in force. If a later edit drops it from
		the notes, nothing else in the suite would notice.
		"""
		low = CLAUDE_SPEC.notes.lower()
		assert "sandboxable" in low or "does not contain the child" in low
		assert "absent" in low
		assert "egress" in low, "the unmitigated telemetry route is FR-152's open finding"

	def test_a_spec_naming_no_argv_is_refused(self) -> None:
		with pytest.raises(ValueError, match="declares no argv"):
			HarnessSpec(name="empty", argv=())

	def test_the_specs_that_claim_containment_declare_which_variables_do_it(self) -> None:
		"""FR-019: the variables a spec *asserts* isolate, named apart from the rest.

		``env`` carries two different kinds of thing -- a containment claim and an
		ordinary setting -- and the store-isolation row measures only the first. Without
		this declaration the row would withhold ``RESEARCH_MODEL`` and npm's log level
		alongside ``CLAUDE_CONFIG_DIR``, and a difference between the two arms could no
		longer be attributed to containment. ``pi`` and ``pi-research`` declare none, which
		is the honest answer: ``pi`` isolates by ``--session-dir`` in its argv.
		"""
		assert CLAUDE_SPEC.isolation_env == ("CLAUDE_CONFIG_DIR",)
		assert DSH_SPEC.isolation_env == ("DSH_HOME",)
		assert OPENCODE_SPEC.isolation_env == ("OPENCODE_DB", "OPENCODE_TEST_HOME")
		assert PI_SPEC.isolation_env == (), "pi isolates by --session-dir, not by env"
		assert PI_RESEARCH_SPEC.isolation_env == ()

	def test_a_containment_variable_is_one_the_spec_actually_sets(self) -> None:
		"""A declared name the env does not carry would measure a variable never applied."""
		for spec in SPECS.values():
			declared = set(spec.isolation_env)
			applied = {key for key, _ in spec.env}
			assert declared <= applied, (
				f"{spec.name!r} declares containment on {sorted(declared - applied)}, "
				"which its env never sets"
			)

	def test_opencode_takes_its_record_from_a_command_not_a_glob(self) -> None:
		"""The seam that makes a database-backed harness wireable at all (FR-058).

		opencode keeps sessions in SQLite, so there is no file for a glob to find and
		the record arrives as `session export`'s stdout instead.
		"""
		assert OPENCODE_SPEC.session_command, "without this the harness has no readable record"
		assert OPENCODE_SPEC.session_command[0] == "opencode"
		assert OPENCODE_SPEC.record_format == "json", (
			"one exported document is the whole session, not one event per line"
		)
		assert "**/projects/*" not in OPENCODE_SPEC.session_glob, (
			"the glob is never consulted for this spec; leaving a claude-shaped one here "
			"would be a lie about where the record comes from"
		)

	def test_opencode_session_ids_must_carry_the_ses_prefix(self) -> None:
		"""Measured: a bare token is refused with `Expected a string starting with "ses"`.

		The prefix is data on the spec rather than a rule in the caller, because the
		probe mints its own ids and would otherwise fail on the identifier rather than
		on the harness -- which reads as a harness failure.
		"""
		assert OPENCODE_SPEC.session_id_prefix == "ses_"
		adapter = make_adapter(Path("/tmp"), OPENCODE_SPEC)
		assert adapter.session_id("probe").startswith("ses_probe-")

	def test_opencode_completion_is_the_document_outcome_not_the_exit_code(self) -> None:
		"""Measured: a 402-refused session exports outcome `failed` and still exits 0."""
		assert OPENCODE_SPEC.completion_event is None, (
			"one exported document is the session; there is no per-event envelope to name"
		)
		assert OPENCODE_SPEC.completion_reason_path == ("info", "outcome")
		assert OPENCODE_SPEC.completion_reason_value == "succeeded"
		assert OPENCODE_SPEC.usage_path == ("info", "tokens", "output")

	def test_opencode_notes_record_the_unwitnessed_run_and_the_missing_tool_slot(self) -> None:
		"""Two facts a reader would most like rounded off, so they are pinned here.

		The spec was never witnessed end to end (the account is out of credit), and
		`opencode run` has no flag that narrows the tool set, so the sandbox probe's
		instrument cannot be built for it.
		"""
		low = OPENCODE_SPEC.notes.lower()
		assert "not witnessed end to end" in low
		assert "tool allowlist has no slot" in low
		assert OPENCODE_SPEC.confinement_tools == "", (
			"empty because the harness has no such flag, not by oversight"
		)

	def test_a_record_format_outside_the_known_shapes_is_refused(self) -> None:
		with pytest.raises(AssertionError, match="bad record_format"):
			HarnessSpec(name="x", argv=("true",), record_format="xml")

	def test_a_zstd_record_cannot_also_be_a_whole_document(self) -> None:
		"""A session command's stdout is already decoded, so the pair is incoherent."""
		with pytest.raises(AssertionError, match="zstd record and a whole-document format"):
			HarnessSpec(name="x", argv=("true",), session_is_zstd=True, record_format="json")

	def test_a_completion_event_without_a_path_to_read_it_is_refused(self) -> None:
		with pytest.raises(AssertionError, match="no path to read from it"):
			HarnessSpec(name="x", argv=("true",), completion_event="turn/end")

	def test_an_unknown_usage_reducer_is_refused(self) -> None:
		with pytest.raises(AssertionError, match="bad usage_reduce"):
			HarnessSpec(name="x", argv=("true",), usage_reduce="mean")

	def test_the_spec_env_is_slot_substituted(self) -> None:
		spec = HarnessSpec(name="x", argv=("true",), env=(("HOME_{session_id}", "{session_dir}"),))
		assert spec.formatted_env({"session_id": "s1", "session_dir": "/tmp/s"}) == {
			"HOME_s1": "/tmp/s"
		}


# --------------------------------------------------------------------------- #
# argv construction
# --------------------------------------------------------------------------- #


class TestBuildArgv:
	def test_goal_is_appended_raw_and_last(self, tmp_path: Path) -> None:
		adapter = adapter_for(tmp_path, "complete")
		goal = "Do the thing {with} braces and a {nested: format} spec"
		argv = adapter.build_argv(goal, "s1")
		assert argv[-1] == goal
		assert "{with}" in argv[-1]

	def test_slots_are_substituted_in_the_template(self, tmp_path: Path) -> None:
		adapter = adapter_for(tmp_path, "complete")
		argv = adapter.build_argv("g", "session-42")
		assert str(adapter.session_dir) in argv
		assert "session-42" in argv
		assert "{session_id}" not in " ".join(argv)

	def test_a_goal_baked_into_the_template_is_refused_not_formatted(self, tmp_path: Path) -> None:
		"""A hard-coded objective in the template is the failure this guard catches."""
		goal = "prove the duplicate-delivery clause by replaying the outbox"
		spec = dataclasses.replace(base_spec(tmp_path, "complete"), argv=("echo", goal))
		with pytest.raises(AssertionError, match="formatted argv template"):
			make_adapter(tmp_path, spec).build_argv(goal, "s1")

	def test_a_short_goal_is_not_mistaken_for_template_contamination(self, tmp_path: Path) -> None:
		"""A one-character goal occurs in most absolute paths; that proves nothing."""
		adapter = adapter_for(tmp_path, "complete")
		assert adapter.build_argv("g", "s1")[-1] == "g"

	def test_a_long_goal_resembling_a_slot_is_still_accepted(self, tmp_path: Path) -> None:
		"""The guard fires on the goal itself, not on the word 'session'."""
		adapter = adapter_for(tmp_path, "complete")
		goal = "make the session directory carry the session id in its name"
		assert adapter.build_argv(goal, "s1")[-1] == goal

	def test_an_empty_goal_is_refused(self, tmp_path: Path) -> None:
		adapter = adapter_for(tmp_path, "complete")
		with pytest.raises(AssertionError, match="needs a goal"):
			adapter.build_argv("   ", "s1")

	def test_an_empty_model_is_refused_at_construction(self, tmp_path: Path) -> None:
		with pytest.raises(AssertionError, match="needs a model"):
			ConfiguredHarnessAdapter(PI_SPEC, workspace=tmp_path, session_dir=tmp_path, model=" ")

	def test_a_non_positive_probe_timeout_is_refused(self, tmp_path: Path) -> None:
		with pytest.raises(AssertionError, match="probe timeout must be positive"):
			ConfiguredHarnessAdapter(
				PI_SPEC, workspace=tmp_path, session_dir=tmp_path, model="m", probe_timeout=0.0
			)


class TestTheToolVocabulary:
	"""One allowlist spelling for the operator; each harness's own for the child.

	The translation exists because the failure it prevents is silent in the worst
	direction. A harness that rejects an unknown tool name tells the operator; Claude
	Code accepts `read,write`, exits 0, reports a completed turn, and hands the
	producer nothing -- so the build "succeeds" having written no code.
	"""

	def test_a_spec_with_no_table_passes_the_operator_spelling_through(
		self, tmp_path: Path
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		assert adapter.render_tools() == adapter.tools
		assert adapter.render_tools("bash,read") == "bash,read"

	def test_a_known_name_is_translated(self, tmp_path: Path) -> None:
		adapter = make_adapter(tmp_path, CLAUDE_SPEC)
		assert adapter.render_tools("read,write,edit,bash") == "Read,Write,Edit,Bash"

	def test_an_unknown_name_is_passed_through_not_dropped(self, tmp_path: Path) -> None:
		"""Dropping it would turn a spelling SoFact does not know into a capability
		silently removed, which is the failure mode the translation exists to prevent."""
		adapter = make_adapter(tmp_path, CLAUDE_SPEC)
		assert adapter.render_tools("read,mystery") == "Read,mystery"

	def test_the_slot_renders_the_translated_set(self, tmp_path: Path) -> None:
		"""The argv must carry the translated set, not the operator's raw string."""
		adapter = make_adapter(tmp_path, CLAUDE_SPEC)
		argv = adapter.build_argv("g", "s1")
		handed = argv[argv.index("--tools") + 1]
		assert handed == "Read,Write,Edit,Bash"
		assert "read,write" not in handed

	def test_the_confinement_probe_measures_the_translated_set(self, tmp_path: Path) -> None:
		"""Otherwise the sandbox row reports confinement for a child that had no tools."""
		adapter = make_adapter(tmp_path, CLAUDE_SPEC)
		assert adapter.render_tools(CLAUDE_SPEC.confinement_tools) == "Read,Write,Edit"


# --------------------------------------------------------------------------- #
# record parsing: the wire format read back
# --------------------------------------------------------------------------- #


class TestParseCompletion:
	def test_a_completed_turn_is_a_structured_declaration(self) -> None:
		rows = _records({"type": "turn/end", "data": {"reason": {"kind": "completed"}}})
		assert parse_completion(rows, DSH_SPEC) is True

	def test_a_different_reason_is_not_a_declaration(self) -> None:
		rows = _records({"type": "turn/end", "data": {"reason": {"kind": "aborted"}}})
		assert parse_completion(rows, DSH_SPEC) is False

	def test_a_harness_with_no_completion_signal_never_declares(self) -> None:
		"""Absence of a declaration is not a declaration of failure."""
		rows = _records({"type": "turn/end", "data": {"reason": {"kind": "completed"}}})
		assert parse_completion(rows, PI_SPEC) is False

	def test_a_record_without_a_data_block_is_skipped(self) -> None:
		assert parse_completion(_records({"type": "turn/end"}), DSH_SPEC) is False

	def test_a_whole_document_declares_without_an_event_envelope(self) -> None:
		"""An exported session has no per-event `type`, so the path is read directly.

		opencode's `info.outcome` is the declaration, and requiring an event name for a
		spec whose record *is* the document would make the field unusable rather than
		honest.
		"""
		rows = _records({"info": {"outcome": "succeeded"}, "messages": []})
		assert parse_completion(rows, OPENCODE_SPEC) is True
		assert parse_completion(_records({"info": {"outcome": "failed"}}), OPENCODE_SPEC) is False

	def test_a_spec_with_a_path_but_no_event_still_reads_the_path(self) -> None:
		"""The event is a filter when declared, not a precondition for reading."""
		assert OPENCODE_SPEC.completion_event is None
		assert parse_completion(_records({"info": {"outcome": "succeeded"}}), OPENCODE_SPEC) is True


class TestParseUsage:
	def test_usage_is_summed_across_records(self) -> None:
		rows = _records(
			{"type": "a", "data": {"usage": {"outputTokens": 10}}},
			{"type": "b", "data": {"usage": {"outputTokens": 32}}},
		)
		assert parse_usage(rows, DSH_SPEC) == 42

	def test_no_usage_block_is_None_and_not_zero(self) -> None:
		"""A harness that reports nothing is unmeasured; zero would be a fabrication."""
		assert parse_usage(_records({"type": "a", "data": {}}), DSH_SPEC) is None

	def test_pi_usage_is_read_from_the_message_envelope(self) -> None:
		"""Measured on pi 0.85.1: usage sits in ``message``, and the key is ``output``.

		[S19] recorded that pi reports no usage at all. That was true of the version
		measured then and is false now, and the probe's ``telemetry`` row is what caught
		it -- which is the whole argument for the table being data (FR-161).
		"""
		rows = _records(
			{"type": "message", "message": {"role": "assistant", "usage": {"output": 3}}},
			{"type": "message", "message": {"role": "user"}},
			{"type": "message", "message": {"role": "assistant", "usage": {"output": 7}}},
		)
		assert parse_usage(rows, PI_SPEC) == 10

	def test_a_data_envelope_is_named_not_assumed(self) -> None:
		"""A dsh-shaped record read through a pi-shaped path finds nothing, and vice versa.

		That is the point: the root is stated once, so a wrong path reads nothing rather
		than reading the wrong number.
		"""
		pi_shaped = _records({"message": {"usage": {"output": 3}}})
		dsh_shaped = _records({"data": {"usage": {"outputTokens": 5}}})
		assert parse_usage(pi_shaped, DSH_SPEC) is None
		assert parse_usage(dsh_shaped, PI_SPEC) is None
		assert parse_usage(pi_shaped, PI_SPEC) == 3
		assert parse_usage(dsh_shaped, DSH_SPEC) == 5

	def test_a_boolean_is_not_a_token_count(self) -> None:
		rows = _records({"type": "a", "data": {"usage": {"outputTokens": True}}})
		assert parse_usage(rows, DSH_SPEC) is None

	def test_max_reduction_takes_the_largest_single_record(self) -> None:
		spec = HarnessSpec(
			name="m",
			argv=("true",),
			usage_path=("data", "usage", "outputTokens"),
			usage_reduce="max",
		)
		rows = _records(
			{"data": {"usage": {"outputTokens": 10}}},
			{"data": {"usage": {"outputTokens": 99}}},
		)
		assert parse_usage(rows, spec) == 99


class TestParseGoalEntryAndTurns:
	def test_prompt_delivery_is_the_default_and_is_not_forced(self) -> None:
		entry = parse_goal_entry(_records({"type": "user/message"}), DSH_SPEC)
		assert entry is GoalEntry.PROMPT
		assert entry.is_forced is False

	def test_a_goal_typed_event_means_the_session_carried_the_goal(self) -> None:
		spec = HarnessSpec(name="g", argv=("true",), goal_event_types=("goal/created",))
		entry = parse_goal_entry(_records({"type": "goal/created"}), spec)
		assert entry is GoalEntry.GOAL_BEARING_SESSION
		assert entry.is_forced is True

	def test_a_harness_that_emits_no_goal_events_can_only_ever_report_a_prompt(self) -> None:
		"""Absence of a goal event type is a measured limit, not a parsing failure."""
		rows = _records({"type": "goal/created"})
		assert parse_goal_entry(rows, DSH_SPEC) is GoalEntry.PROMPT

	def test_turns_are_counted_and_absence_is_None_not_one(self) -> None:
		rows = _records({"type": "turn/start"}, {"type": "turn/start"})
		assert parse_continuations(rows, DSH_SPEC) == 2
		assert parse_continuations(_records({"type": "message"}), DSH_SPEC) is None


# --------------------------------------------------------------------------- #
# the record source: a file a harness wrote, or a command that prints one
# --------------------------------------------------------------------------- #


class TestTheRecordCommand:
	"""A harness whose history is a database rather than a file (opencode, FR-058).

	Driven against a real child: the export command is a real process whose stdout is
	the record. The glob is one that matches nothing, so a passing test cannot be
	passing because a file happened to be there.
	"""

	async def test_the_record_arrives_as_a_file_the_readers_already_understand(
		self, tmp_path: Path
	) -> None:
		"""The seam's whole point: a command's stdout becomes a path, once."""
		spec = db_spec(tmp_path, "db")
		seed_store(tmp_path, "ses_probe-abc")
		adapter = make_adapter(tmp_path, spec)
		files = await adapter.session_files("ses_probe-abc")
		assert len(files) == 1
		assert files[0].is_file(), "every reader below opens a path, so this must be one"
		assert files[0].name.startswith("sofact-record-")
		records = await adapter.read_records(files[0])
		assert records == (
			{
				"info": {
					"id": "ses_probe-abc",
					"outcome": "succeeded",
					"tokens": {"input": 900, "output": 120, "reasoning": 0},
				},
				"messages": [{"role": "assistant", "content": "done"}],
			},
		)

	async def test_the_glob_is_never_consulted_when_a_command_is_declared(
		self, tmp_path: Path
	) -> None:
		"""A file the glob *would* match must not shadow the declared command."""
		spec = db_spec(tmp_path, "db")
		seed_store(tmp_path, "ses_probe-abc")
		(tmp_path / "decoy.jsonl").write_text('{"info": {"outcome": "failed"}}\n', encoding="utf-8")
		adapter = make_adapter(tmp_path, spec)
		files = await adapter.session_files("ses_probe-abc")
		assert len(files) == 1
		assert files[0].name.startswith("sofact-record-")

	async def test_a_command_that_refuses_yields_no_record_rather_than_an_empty_one(
		self, tmp_path: Path
	) -> None:
		"""`the harness would not hand it over` is not `the session left no record`.

		The working export is the control: without it this test passes on any code path
		that returns nothing, including one that never ran the command at all.
		"""
		seed_store(tmp_path, "ses_probe-abc")
		working = make_adapter(tmp_path, db_spec(tmp_path, "db"))
		assert len(await working.session_files("ses_probe-abc")) == 1

		refusing = make_adapter(tmp_path, db_spec(tmp_path, "db", command="export-refuse"))
		assert await refusing.session_files("ses_probe-abc") == ()

	async def test_a_command_that_prints_nothing_yields_no_record(self, tmp_path: Path) -> None:
		"""An empty stdout is not an empty session, so it is no record at all."""
		seed_store(tmp_path, "ses_probe-abc")
		working = make_adapter(tmp_path, db_spec(tmp_path, "db"))
		assert len(await working.session_files("ses_probe-abc")) == 1

		silent = make_adapter(tmp_path, db_spec(tmp_path, "db", command="export-silent"))
		assert await silent.session_files("ses_probe-abc") == ()

	async def test_reading_twice_returns_the_same_path(self, tmp_path: Path) -> None:
		"""The probe reads the record, then the extras read it again; the file is stable.

		A fresh file per call would make `session_path` a different path in two
		observations of one session, which is a fact about the reader rather than the
		session.
		"""
		seed_store(tmp_path, "ses_probe-abc")
		adapter = make_adapter(tmp_path, db_spec(tmp_path, "db"))
		first = await adapter.session_files("ses_probe-abc")
		second = await adapter.session_files("ses_probe-abc")
		assert first == second
		assert first[0].is_file(), "equality of two empty tuples would prove nothing"

	async def test_a_spec_with_no_command_still_globs(self, tmp_path: Path, plan: GoalPlan) -> None:
		"""The file-shaped source is unchanged; the command is an alternative, not a swap."""
		adapter = adapter_for(tmp_path, "complete")
		assert await adapter.session_files("s1") == ()
		profile = await adapter.probe()
		await adapter.dispatch(_step(plan, 0), plan, profile=profile)

	async def test_a_failed_session_declares_failure_from_the_document(
		self, tmp_path: Path
	) -> None:
		"""Measured on opencode: a 402-refused session exports outcome `failed`, exit 0.

		Reading completion from the exit code would report that session as completed,
		which is why the document is what decides it.
		"""
		seed_store(tmp_path, "ses_probe-abc", outcome="succeeded")
		adapter = make_adapter(tmp_path, db_spec(tmp_path, "db"))
		files = await adapter.session_files("ses_probe-abc")
		records = await adapter.read_records(files[0])
		assert parse_completion(records, adapter.spec) is True

		seed_store(tmp_path, "ses_probe-refused", outcome="failed")
		refused = make_adapter(tmp_path, db_spec(tmp_path, "db-fail"))
		files = await refused.session_files("ses_probe-refused")
		records = await refused.read_records(files[0])
		assert parse_completion(records, refused.spec) is False

	async def test_usage_is_read_from_the_exported_document(self, tmp_path: Path) -> None:
		seed_store(tmp_path, "ses_probe-abc", output_tokens=120)
		adapter = make_adapter(tmp_path, db_spec(tmp_path, "db"))
		files = await adapter.session_files("ses_probe-abc")
		records = await adapter.read_records(files[0])
		assert parse_usage(records, adapter.spec) == 120

	async def test_a_document_that_is_not_an_object_is_unreadable_not_empty(
		self, tmp_path: Path
	) -> None:
		""" "we could not read it" must not be swallowed into "it said nothing"."""
		spec = dataclasses.replace(
			db_spec(tmp_path, "db"), session_command=(sys.executable, "-c", "print('[1, 2, 3]')")
		)
		adapter = make_adapter(tmp_path, spec)
		files = await adapter.session_files("ses_probe-abc")
		with pytest.raises(HarnessSessionUnreadable, match="not a JSON object"):
			await adapter.read_records(files[0])

	async def test_malformed_json_is_unreadable(self, tmp_path: Path) -> None:
		spec = dataclasses.replace(
			db_spec(tmp_path, "db"), session_command=(sys.executable, "-c", "print('nonsense')")
		)
		adapter = make_adapter(tmp_path, spec)
		files = await adapter.session_files("ses_probe-abc")
		with pytest.raises(HarnessSessionUnreadable, match="is not JSON"):
			await adapter.read_records(files[0])


# --------------------------------------------------------------------------- #
# the probe: capability measured, or explicitly not measured
# --------------------------------------------------------------------------- #


class TestProbe:
	async def test_probe_reports_every_capability_exactly_once(self, tmp_path: Path) -> None:
		"""Coverage completeness: adding a capability without a probe row fails here."""
		profile = await adapter_for(tmp_path, "complete").probe()
		assert len(profile.findings) == len(HarnessCapability)
		assert {f.capability for f in profile.findings} == set(HarnessCapability)

	def test_an_unprobed_capability_reads_inconclusive_not_absent(self) -> None:
		profile = HarnessProfile(name="none", command=("true",), probed_at=now(), findings=())
		assert profile.observation(HarnessCapability.CONCURRENT) is ProbeOutcome.INCONCLUSIVE
		assert profile.finding(HarnessCapability.CONCURRENT) is None

	async def test_a_process_that_exits_is_non_interactive(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.non_interactive is ProbeOutcome.CONFIRMED
		assert profile.is_usable is True
		assert profile.reduced_mode_available is True

	async def test_usage_in_the_record_confirms_telemetry(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.observation(HarnessCapability.TELEMETRY) is ProbeOutcome.CONFIRMED

	async def test_a_path_that_reads_nothing_is_absent_rather_than_zero(
		self, tmp_path: Path
	) -> None:
		"""The branch the real `pi` defect lived in, kept reachable on purpose.

		A spec that names no usage path is the honest stand-in for a wrong one: the probe
		reports `ABSENT` and says spend cannot be attributed, rather than reporting `0`
		(NFR-024). A real 0.85.1 `pi` record containing a usage block sat behind exactly
		this row and read `absent` -- see ADR-0016.
		"""
		spec = dataclasses.replace(base_spec(tmp_path, "complete"), usage_path=())
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.TELEMETRY)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.ABSENT
		assert "cannot be attributed" in finding.observed

	async def test_goal_mode_is_inconclusive_from_one_invocation(self, tmp_path: Path) -> None:
		"""One session cannot separate 'the harness cannot' from 'the model declined'."""
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.goal_mode is ProbeOutcome.INCONCLUSIVE
		assert profile.supports_goal_dispatch is False

	async def test_an_accepted_context_flag_is_confirmed(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert (
			profile.observation(HarnessCapability.CONTEXT_FILES_DISABLED) is ProbeOutcome.CONFIRMED
		)

	async def test_a_failing_invocation_means_the_flag_was_not_accepted(
		self, tmp_path: Path
	) -> None:
		profile = await adapter_for(tmp_path, "fail").probe()
		assert profile.observation(HarnessCapability.CONTEXT_FILES_DISABLED) is ProbeOutcome.ABSENT

	async def test_a_harness_without_the_flag_is_inconclusive_not_absent(
		self, tmp_path: Path
	) -> None:
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"), supports_context_file_flag=False
		)
		profile = await make_adapter(tmp_path, spec).probe()
		assert profile.observation(HarnessCapability.CONTEXT_FILES_DISABLED) is (
			ProbeOutcome.INCONCLUSIVE
		)

	async def test_a_process_that_never_exits_is_unusable(self, tmp_path: Path) -> None:
		"""A real kill after a real timeout: the FR-145 row, measured."""
		profile = await adapter_for(tmp_path, "slow", probe_timeout=0.5).probe()
		assert profile.non_interactive is ProbeOutcome.ABSENT
		assert profile.is_usable is False
		assert profile.supports_goal_dispatch is False
		assert profile.reduced_mode_available is False

	async def test_the_version_comes_from_a_real_invocation(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.version == "synthetic 1.2.3"

	async def test_a_cold_workspace_confirms_the_harness_starts_an_empty_repo(
		self, tmp_path: Path
	) -> None:
		"""The probe runs with the workspace as cwd, so a fresh deployment already has
		the experiment this row asks for; it only needed to be read."""
		profile = await adapter_for(tmp_path, "complete").probe()
		finding = profile.finding(HarnessCapability.BOOTSTRAP_EMPTY_REPO)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.CONFIRMED
		assert "no repository" in finding.observed

	async def test_a_used_workspace_cannot_witness_a_cold_start(self, tmp_path: Path) -> None:
		"""A probe that ran after a dispatch is not the experiment, and says so rather
		than reporting the capability either way."""
		adapter = adapter_for(tmp_path, "complete")
		(adapter.workspace / "already-here.txt").write_text("x", encoding="utf-8")
		profile = await adapter.probe()
		finding = profile.finding(HarnessCapability.BOOTSTRAP_EMPTY_REPO)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "already held 1 entries" in finding.observed

	async def test_a_failure_in_an_empty_repo_is_not_a_verdict_on_the_harness(
		self, tmp_path: Path
	) -> None:
		"""FR-153 again: the negative is undecidable, so it is not rounded to ABSENT."""
		profile = await adapter_for(tmp_path, "fail").probe()
		finding = profile.finding(HarnessCapability.BOOTSTRAP_EMPTY_REPO)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "exited 7 in an empty workspace" in finding.observed

	async def test_a_run_that_left_no_record_claims_nothing(self, tmp_path: Path) -> None:
		"""A clean exit with nothing to inspect is not evidence of a capability."""
		profile = await adapter_for(tmp_path, "silent").probe()
		assert profile.manifest_path is None, "the harness wrote no record at all"
		finding = profile.finding(HarnessCapability.BOOTSTRAP_EMPTY_REPO)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "no readable session record" in finding.observed

	async def test_the_session_record_path_is_kept(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.manifest_path is not None
		assert profile.manifest_path.endswith(".jsonl")

	async def test_an_absent_binary_is_a_local_fact_not_a_harness_finding(
		self, tmp_path: Path
	) -> None:
		"""A missing executable says nothing about the harness, so it is not a profile."""
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"), argv=("definitely-not-a-binary",)
		)
		with pytest.raises(HarnessBinaryMissing, match="on PATH and it is absent"):
			await make_adapter(tmp_path, spec).probe()

	async def test_a_zstd_spec_without_zstd_on_path_is_refused(
		self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		def without_zstd(name: str, *rest: object, **kwargs: object) -> str | None:
			return None if name == "zstd" else "/usr/bin/true"

		adapter = adapter_for(tmp_path, "complete", zstd=True)
		monkeypatch.setattr(shutil, "which", without_zstd)
		with pytest.raises(HarnessBinaryMissing, match="writes zstd session records"):
			await adapter.probe()

	async def test_a_zstd_session_record_is_decompressed_by_the_real_zstd_cli(
		self, tmp_path: Path
	) -> None:
		"""Python 3.13 ships no zstd binding, so this shells out; prove it works."""
		profile = await adapter_for(tmp_path, "complete", zstd=True).probe()
		assert profile.manifest_path is not None
		assert profile.manifest_path.endswith(".jsonl.zstd")
		assert profile.observation(HarnessCapability.TELEMETRY) is ProbeOutcome.CONFIRMED

	async def test_a_producer_that_names_its_file_zst_is_read_too(self, tmp_path: Path) -> None:
		"""zstd >= 1.5 defaults to '.zst', and decompression ignores the extension.

		The glob has to follow the producer's filename, which is why this is a spec
		field rather than a hard-coded '.zstd'.
		"""
		profile = await adapter_for(tmp_path, "complete", zstd=True, zstd_ext="zst").probe()
		assert profile.manifest_path is not None
		assert profile.manifest_path.endswith(".jsonl.zst")
		assert profile.observation(HarnessCapability.TELEMETRY) is ProbeOutcome.CONFIRMED

	async def test_a_record_that_is_not_json_is_reported_not_swallowed(
		self, tmp_path: Path
	) -> None:
		with pytest.raises(HarnessSessionUnreadable, match="is not JSON"):
			await adapter_for(tmp_path, "malformed").probe()

	async def test_a_json_line_that_is_not_an_object_is_reported(self, tmp_path: Path) -> None:
		with pytest.raises(HarnessSessionUnreadable, match="is not a JSON object"):
			await adapter_for(tmp_path, "notobject").probe()

	async def test_a_failing_process_still_produces_a_full_profile(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "fail").probe()
		assert profile.is_usable is True
		assert profile.observation(HarnessCapability.TELEMETRY) is ProbeOutcome.CONFIRMED

	async def test_the_profile_records_the_model_it_was_probed_with(self, tmp_path: Path) -> None:
		"""A profile describes one *configuration*, and the model is part of it.

		Without this the finding could not be applied to the run it is supposed to gate:
		"this harness works" is a claim about a model as much as about a binary.
		"""
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.model == "synthetic-model"


class TestModelResolution:
	"""MODEL_RESOLVED: the one row that is decidable in *both* directions.

	A harness that resolves its model against its own registry names the failure in its
	own words, so a refusal is a positive observation (ABSENT) and a clean run that left
	a record is a positive observation of the opposite (CONFIRMED). Neither is a guess.
	"""

	async def test_a_clean_run_resolves_the_model(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.model_resolved is ProbeOutcome.CONFIRMED

	async def test_a_refusal_is_quoted_verbatim(self, tmp_path: Path) -> None:
		"""The reason must quote the child, or the operator cannot act on it."""
		profile = await adapter_for(tmp_path, "badmodel-always").probe()
		assert profile.model_resolved is ProbeOutcome.ABSENT
		finding = profile.finding(HarnessCapability.MODEL_RESOLVED)
		assert finding is not None
		assert "not found. Use --list-models" in finding.observed
		assert "registry" in finding.observed

	async def test_a_spec_with_no_declared_pattern_stays_inconclusive(self, tmp_path: Path) -> None:
		"""Silence is not success: without a declared string the probe cannot read the failure."""
		spec = dataclasses.replace(base_spec(tmp_path, "badmodel-always"), model_error_pattern="")
		profile = await make_adapter(tmp_path, spec).probe()
		assert profile.model_resolved is ProbeOutcome.INCONCLUSIVE
		finding = profile.finding(HarnessCapability.MODEL_RESOLVED)
		assert finding is not None
		assert "does not know how to read" in finding.observed

	async def test_an_undeclared_failure_is_not_blamed_on_the_model(self, tmp_path: Path) -> None:
		"""A non-zero exit with no refusal string is unattributed, and must say so."""
		profile = await adapter_for(tmp_path, "fail").probe()
		assert profile.model_resolved is ProbeOutcome.INCONCLUSIVE
		finding = profile.finding(HarnessCapability.MODEL_RESOLVED)
		assert finding is not None
		assert "unattributed" in finding.observed

	async def test_a_clean_exit_with_no_record_resolves_nothing(self, tmp_path: Path) -> None:
		"""Exiting 0 is not evidence that the model was accepted and did work."""
		profile = await adapter_for(tmp_path, "silent").probe()
		assert profile.model_resolved is ProbeOutcome.INCONCLUSIVE

	async def test_every_capability_including_this_one_is_reported(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "complete").probe()
		assert len(profile.findings) == len(HarnessCapability) == 11

	async def test_dispatch_refuses_when_the_profile_watched_the_refusal(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""The attribution the operator needs: not a producer failure, and nothing ran.

		Before this row existed, a refused model surfaced as a `pi` session that exited 1
		with no record -- indistinguishable from a producer that tried and failed, and
		attributed to the wrong party in every report built on it.
		"""
		adapter = adapter_for(tmp_path, "badmodel-once")
		profile = await adapter.probe()
		assert profile.model_resolved is ProbeOutcome.ABSENT
		assert (tmp_path / ".calls").read_text() == "1", "the probe consumed the refusal"

		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert record.exit_code is None, "no session was started at all"
		assert record.session_path is None
		assert "model-resolution failure and not a producer failure" in (record.note or "")
		assert "synthetic-nonesuch:latest" in (record.note or "")
		assert (tmp_path / ".calls").read_text() == "1", "the gate refused before the child ran"

	async def test_dispatch_refuses_a_profile_measured_with_another_model(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""A capability finding is about the configuration that was measured, not the name."""
		probed = adapter_for(tmp_path, "complete")
		profile = await probed.probe()
		other = ConfiguredHarnessAdapter(
			base_spec(tmp_path, "complete"),
			workspace=probed.workspace,
			session_dir=tmp_path,
			model="a-different-model",
		)
		record = await other.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert "synthetic-model" in (record.note or "")
		assert "a-different-model" in (record.note or "")
		assert record.session_path is None

	async def test_an_inconclusive_row_does_not_stop_the_run(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""FR-153: an undecided row is reported, not promoted to a refusal."""
		adapter = adapter_for(tmp_path, "fail")
		profile = await adapter.probe()
		assert profile.model_resolved is ProbeOutcome.INCONCLUSIVE
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is not StepOutcome.NOT_DISPATCHED
		assert record.exit_code == 7
		assert "could not decide whether the harness resolves" in (record.note or "")

	async def test_a_profile_with_no_model_recorded_gates_nothing(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""Rows written before this field existed must stay readable, not refused."""
		profile = await adapter_for(tmp_path, "complete").probe()
		legacy = profile.model_copy(update={"model": ""})
		record = await adapter_for(tmp_path, "complete").dispatch(
			_step(plan, 0), plan, profile=legacy
		)
		assert record.outcome is StepOutcome.COMPLETED


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #


@pytest.fixture
def plan(
	make_contract: Callable[..., Contract], make_oracle: Callable[..., OracleDeclaration]
) -> GoalPlan:
	"""A real plan, compiled from a real contract, through the real compiler."""
	contract = make_contract(
		(
			"An HTTP GET of /reminders returns the reminder within five seconds.",
			make_oracle("pytest -k reminders"),
		),
		(
			"A reminder is never delivered twice.",
			make_oracle("pytest -k idempotent", oracle_class=OracleClass.PROPERTY),
		),
	)
	return compile_plan(contract)


def _step(plan: GoalPlan, ordinal: int) -> GoalStep:
	step = next((s for s in plan.steps if s.ordinal == ordinal), None)
	assert step is not None, f"plan {plan.id} has no step {ordinal}"
	return step


def _covering(plan: GoalPlan, clauses: int = 1) -> GoalStep:
	"""The first step covering at least ``clauses`` clauses, whatever its ordinal."""
	step = next((s for s in plan.steps if len(s.clause_ids) >= clauses), None)
	assert step is not None, f"no step in plan {plan.id} covers {clauses} clause(s)"
	return step


class TestDispatch:
	async def test_no_profile_means_not_dispatched_never_a_silent_fallback(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""FR-148: 'never probed' cannot be quietly treated as reduced mode."""
		record = await adapter_for(tmp_path, "complete").dispatch(
			_step(plan, 0), plan, profile=None
		)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert "never probed" in (record.note or "")
		assert record.exit_code is None
		assert record.session_path is None

	async def test_a_profile_for_another_harness_is_a_hard_error(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete", name="synthetic")
		other = await adapter_for(tmp_path, "complete", name="elsewhere").probe()
		with pytest.raises(ValueError, match="not a recoverable error"):
			await adapter.dispatch(_step(plan, 0), plan, profile=other)

	async def test_a_step_absent_from_the_plan_is_refused(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		stranger = _step(plan, 0).model_copy(update={"id": "01920000-0000-7000-8000-0000000000ff"})
		with pytest.raises(ValueError, match="is not in plan"):
			await adapter.dispatch(stranger, plan, profile=profile)

	async def test_an_unusable_profile_dispatches_nothing(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "slow", probe_timeout=0.5)
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert "cannot run unattended" in (record.note or "")

	async def test_a_clean_exit_with_a_declaration_records_both_signals_separately(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""The process outcome and the producer's claim are two signals (FR-138)."""
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		record = await adapter.dispatch(_covering(plan), plan, profile=profile)
		assert record.outcome is StepOutcome.COMPLETED
		assert record.exit_code == 0
		assert record.declared_complete is True
		assert "claim, not a finding" in (record.declaration_note or "")
		assert record.tokens_observed == 120
		assert record.continuations_observed == 1

	async def test_a_nonzero_exit_fails_even_with_a_declaration(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete-fail")
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is StepOutcome.FAILED
		assert record.exit_code == 7

	async def test_a_session_with_no_completion_event_declares_nothing(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "plain")
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.declared_complete is False
		assert record.outcome is StepOutcome.COMPLETED
		assert "did not report completion" in (record.declaration_note or "")

	async def test_a_missing_session_record_is_reported_rather_than_guessed(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""The process exited; nothing about the session was witnessed. Say so."""
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"), session_glob="**/*{session_id}*nonexistent.jsonl"
		)
		adapter = make_adapter(tmp_path, spec)
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.session_path is None
		assert record.declared_complete is False
		assert "nothing about this session was witnessed" in (record.note or "")

	async def test_single_shot_dispatch_reports_the_capability_loss(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""FR-144: a degraded run must not look like the plan was honoured."""
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.mode.value == "single_shot"
		assert record.capability_loss is not None
		assert "FR-144" in (record.note or "")

	async def test_prompt_only_goal_entry_is_reported_as_unforced(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.goal_entry_observed is GoalEntry.PROMPT
		assert "may decline" in (record.note or "")

	async def test_exceeding_the_wall_clock_cap_is_budget_exhausted_not_failed(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""A kill by SoFact is SoFact exercising FR-140, not the work failing.

		The child is fast on the probe and hangs on the dispatch, so the probe really
		succeeds and the timeout is really the dispatch budget rather than a dead probe.
		The probe is shallow here on purpose: this child naps for 30s once the counter is
		consumed, and the extra rows would each spend the probe timeout to learn nothing
		about the dispatch budget this test is actually about.
		"""
		adapter = adapter_for(tmp_path, "slow-after-first", probe_timeout=20.0)
		profile = await adapter.probe(deep=False)
		assert profile.is_usable is True
		step = _step(plan, 0)
		tight = step.model_copy(
			update={"budget": step.budget.model_copy(update={"max_wall_clock_seconds": 0.5})}
		)
		record = await adapter.dispatch(tight, plan, profile=profile)
		assert record.outcome is StepOutcome.BUDGET_EXHAUSTED
		assert record.exit_code is None
		assert record.is_within_budget is False
		assert any("wall-clock cap" in v for v in record.budget_violations)
		assert any("FR-140" in v for v in record.budget_violations)

	async def test_the_pinned_hashes_are_carried_onto_the_record(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		"""FR-139: the record must name what the producer was actually given."""
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		step = _step(plan, 0)
		record = await adapter.dispatch(step, plan, profile=profile)
		assert record.goal_hash == step.goal_hash
		assert record.contract_hash == plan.contract_hash
		assert record.plan_id == plan.id
		assert record.goal_id == plan.goal_id
		assert record.step_id == step.id
		assert record.step_ordinal == step.ordinal

	async def test_the_argv_the_child_received_is_on_the_record(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		step = _step(plan, 0)
		record = await adapter.dispatch(step, plan, profile=profile)
		assert record.argv[-1] == step.goal.render(plan.goal_style)
		assert record.workspace == str(adapter.workspace)

	async def test_a_stderr_tail_is_kept_for_diagnosis(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		script = tmp_path / "noisy.py"
		script.write_text('import sys; sys.stderr.write("boom " * 900)\n', encoding="utf-8")
		spec = HarnessSpec(
			name="noisy",
			argv=(sys.executable, str(script), "{session_dir}", "{session_id}", "plain"),
		)
		adapter = make_adapter(tmp_path, spec)
		profile = await adapter.probe()
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.stderr_tail is not None
		# A *tail* of a long stream starts mid-token by construction; do not demand
		# word alignment, only that the last thing the child said survived.
		assert "boom" in record.stderr_tail
		assert record.stderr_tail.endswith("boom ")
		assert len(record.stderr_tail) <= 2_048

	async def test_a_token_cap_overrun_is_recorded_after_the_fact(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		step = _step(plan, 0)
		capped = step.model_copy(
			update={"budget": step.budget.model_copy(update={"max_tokens": 10})}
		)
		record = await adapter.dispatch(capped, plan, profile=profile)
		assert any("token cap 10 exceeded" in v for v in record.budget_violations)
		assert record.tokens_observed == 120

	async def test_a_continuation_cap_overrun_is_recorded(
		self, tmp_path: Path, plan: GoalPlan
	) -> None:
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()
		step = _step(plan, 0)
		capped = step.model_copy(
			update={"budget": step.budget.model_copy(update={"max_continuations": 0})}
		)
		record = await adapter.dispatch(capped, plan, profile=profile)
		assert any("continuation cap 0 exceeded" in v for v in record.budget_violations)

	async def test_dispatch_is_recorded_as_failing_when_the_binary_vanishes(
		self, tmp_path: Path, plan: GoalPlan, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A workspace that had a harness at probe time and does not at dispatch time."""
		adapter = adapter_for(tmp_path, "complete")
		profile = await adapter.probe()

		def without_python(name: str, *rest: object, **kwargs: object) -> str | None:
			return None if name == sys.executable else shutil.which(name)

		monkeypatch.setattr(shutil, "which", without_python)
		record = await adapter.dispatch(_step(plan, 0), plan, profile=profile)
		assert record.outcome is StepOutcome.NOT_DISPATCHED
		assert "no longer on PATH" in (record.note or "")


# --------------------------------------------------------------------------- #
# the rows that need a second child
# --------------------------------------------------------------------------- #


class TestTheExtraAttempts:
	"""(FR-148) Four rows an earlier probe left unmeasured, now attempted.

	Each of these needs more than one child, and each is a *differential*: the claim is
	about a difference between two runs, or about a file that either appeared or did not.
	That is what makes the negative decidable here, where a single bounded invocation
	could only ever show that nothing was witnessed.
	"""

	async def test_a_confined_child_works_inside_and_cannot_escape(self, tmp_path: Path) -> None:
		"""The positive: the child did the work and no escape file exists above it."""
		profile = await adapter_for(tmp_path, "complete").probe()
		finding = profile.finding(HarnessCapability.SANDBOXABLE)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.CONFIRMED
		assert "read,write,edit" in finding.observed
		assert "escape-marker.txt" in finding.observed

	async def test_an_unconfined_child_escapes_and_the_row_names_the_tool_set(
		self, tmp_path: Path
	) -> None:
		"""The negative is a *file that appeared*, not an absence nobody can read."""
		spec = dataclasses.replace(base_spec(tmp_path, "complete"), confinement_tools="")
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.SANDBOXABLE)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.ABSENT
		assert "escape-marker.txt" in finding.observed
		assert "bash" in finding.observed

	async def test_the_sandbox_probe_leaves_the_workspace_untouched(self, tmp_path: Path) -> None:
		"""Confinement is asserted about a scratch directory, never the build's."""
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.finding(HarnessCapability.SANDBOXABLE) is not None
		workspace = tmp_path / "workspace"
		assert list(workspace.iterdir()) == []

	async def test_a_child_that_did_no_work_proves_nothing_about_confinement(
		self, tmp_path: Path
	) -> None:
		"""Neither marker is a coverage gap: the escape's absence means nothing yet."""
		adapter = adapter_for(tmp_path, "quiet-after-first", probe_timeout=1.0)
		profile = await adapter.probe()
		finding = profile.finding(HarnessCapability.SANDBOXABLE)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "did no work" in finding.observed

	async def test_two_sessions_do_not_collide_on_one_record(self, tmp_path: Path) -> None:
		"""Distinct records is what lets a wave run without erasing half its own evidence."""
		profile = await adapter_for(tmp_path, "complete").probe()
		finding = profile.finding(HarnessCapability.CONCURRENT)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.CONFIRMED

	async def test_a_harness_that_writes_one_shared_record_cannot_run_a_wave(
		self, tmp_path: Path
	) -> None:
		"""The negative: two simultaneous sessions landing on the same path (FR-142)."""
		spec = dataclasses.replace(base_spec(tmp_path, "shared"), session_glob="**/shared.jsonl")
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.CONCURRENT)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.ABSENT
		assert "shared.jsonl" in finding.observed
		assert "FR-142" in finding.observed

	async def test_a_spec_with_no_budget_flag_reports_that_rather_than_a_gap(
		self, tmp_path: Path
	) -> None:
		"""Nothing depends on this row (FR-140), so "there is nothing to attempt" is right."""
		profile = await adapter_for(tmp_path, "complete").probe()
		finding = profile.finding(HarnessCapability.BUDGET_CONTROL)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "declares no budget flag" in finding.observed

	async def test_a_cap_that_bounds_the_work_is_confirmed(self, tmp_path: Path) -> None:
		spec = dataclasses.replace(base_spec(tmp_path, "budget"), budget_argv=("--cap", "{budget}"))
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.BUDGET_CONTROL)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.CONFIRMED
		assert "--cap 1" in finding.attempted

	async def test_a_cap_that_is_accepted_and_ignored_is_absent(self, tmp_path: Path) -> None:
		"""A flag the harness parses but does not honour would silently bound nothing."""
		spec = dataclasses.replace(
			base_spec(tmp_path, "budget-ignore"), budget_argv=("--cap", "{budget}")
		)
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.BUDGET_CONTROL)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.ABSENT
		assert "not honoured" in finding.observed

	async def test_a_compaction_the_session_survived_is_confirmed(self, tmp_path: Path) -> None:
		profile = await adapter_for(tmp_path, "compact").probe()
		finding = profile.finding(HarnessCapability.GOAL_SURVIVES_COMPACTION)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.CONFIRMED
		assert "compaction" in finding.observed

	async def test_a_spec_with_no_compaction_event_cannot_recognise_one(
		self, tmp_path: Path
	) -> None:
		spec = dataclasses.replace(base_spec(tmp_path, "compact"), compaction_event="")
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.GOAL_SURVIVES_COMPACTION)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "declares no compaction event" in finding.observed

	async def test_a_quick_probe_says_which_rows_it_skipped(self, tmp_path: Path) -> None:
		"""An attempt that was never made is reported as one, not as a gap in the harness."""
		profile = await adapter_for(tmp_path, "complete").probe(deep=False)
		for capability in (
			HarnessCapability.SANDBOXABLE,
			HarnessCapability.CONCURRENT,
			HarnessCapability.BUDGET_CONTROL,
			HarnessCapability.STORE_ISOLATED,
		):
			finding = profile.finding(capability)
			assert finding is not None
			assert finding.outcome is ProbeOutcome.INCONCLUSIVE
			assert "not requested" in finding.observed
			assert "no attempt was made" in finding.attempted

	async def test_a_quick_probe_still_reads_the_record_it_already_has(
		self, tmp_path: Path
	) -> None:
		"""The compaction row costs no child, so --quick does not excuse it."""
		profile = await adapter_for(tmp_path, "compact").probe(deep=False)
		finding = profile.finding(HarnessCapability.GOAL_SURVIVES_COMPACTION)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.CONFIRMED

	async def test_a_primary_that_failed_is_why_the_extras_were_not_attempted(
		self, tmp_path: Path
	) -> None:
		"""Gated as a group, and the gate names the primary's exit code."""
		profile = await adapter_for(tmp_path, "fail").probe()
		for capability in (
			HarnessCapability.SANDBOXABLE,
			HarnessCapability.CONCURRENT,
			HarnessCapability.BUDGET_CONTROL,
			HarnessCapability.STORE_ISOLATED,
		):
			finding = profile.finding(capability)
			assert finding is not None
			assert finding.outcome is ProbeOutcome.INCONCLUSIVE
			assert "exit 7" in finding.observed


class TestStoreIsolation:
	"""(FR-019) An isolation variable is measured, not asserted.

	The hazard is OpenRig's own warning about its equivalent variable: setting it does
	not by itself isolate provider configuration. A spec field that looks like a boundary
	and has never been observed to bound anything is worse than no field, because a
	reader counts it as one. The row is therefore a *differential with a control arm* --
	the isolated arm's silence is only evidence once the control arm has proved a fresh
	``HOME`` is a live variable for this harness.
	"""

	async def test_a_spec_whose_env_contains_the_store_is_confirmed(self, tmp_path: Path) -> None:
		"""The positive: applied, HOME stays empty; withheld, the store lands there."""
		profile = await adapter_for(tmp_path, "complete").probe()
		finding = profile.finding(HarnessCapability.STORE_ISOLATED)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.CONFIRMED
		assert "SYNTHETIC_HOME" in finding.observed
		assert "home-control" in finding.observed

	async def test_the_row_names_the_variables_it_applied(self, tmp_path: Path) -> None:
		"""A finding about isolation has to say *which* isolation it measured."""
		profile = await adapter_for(tmp_path, "complete").probe()
		finding = profile.finding(HarnessCapability.STORE_ISOLATED)
		assert finding is not None
		assert "SYNTHETIC_HOME" in finding.attempted
		assert "withheld" in finding.attempted

	async def test_a_spec_with_no_isolation_variables_is_not_measured_by_this_row(
		self, tmp_path: Path
	) -> None:
		"""Nothing to apply and nothing to withhold: a gap in the row, said as one.

		``pi`` isolates by ``--session-dir`` in its argv rather than by an environment
		variable, so this row cannot decide it in either direction -- and reporting
		``CONFIRMED`` for a harness the instrument cannot see would be the fabricated
		capability ``ProbeOutcome`` exists to prevent.
		"""
		spec = dataclasses.replace(base_spec(tmp_path, "complete"), env=(), isolation_env=())
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.STORE_ISOLATED)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "declares no containment variables" in finding.observed

	async def test_the_control_arm_is_what_makes_the_empty_home_mean_something(
		self, tmp_path: Path
	) -> None:
		"""Without a live control the row reports a limit of the *probe*, not a property.

		A harness that writes nothing under ``HOME`` either way would otherwise read as
		perfectly isolated, which is the fabricated capability ``ProbeOutcome`` exists to
		prevent. The ``nostore`` child keeps no state under ``HOME`` at all, so both arms
		are empty and the row has nothing to compare.
		"""
		spec = base_spec(tmp_path, "complete-nostore")
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.STORE_ISOLATED)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "also left" in finding.observed
		assert "limit of the probe" in finding.observed

	async def test_a_variable_that_does_not_contain_the_child_is_absent(
		self, tmp_path: Path
	) -> None:
		"""The negative, and the one this row exists for: the store escaped anyway.

		The spec *asserts* containment on a variable the child ignores, so the isolated arm
		writes under its own ``HOME`` -- and the control arm's HOME is a *different*
		directory, so the control stays clean and cannot mask the escape. This is the
		measured shape of OpenRig's warning: a variable that names isolation and delivers
		none.
		"""
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"),
			env=(("SYNTHETIC_IGNORED", "1"),),
			isolation_env=("SYNTHETIC_IGNORED",),
		)
		adapter = make_adapter(tmp_path, spec)
		profile = await adapter.probe()
		finding = profile.finding(HarnessCapability.STORE_ISOLATED)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.ABSENT
		assert "do not contain its store" in finding.observed
		assert "FR-019" in finding.observed

	async def test_only_the_declared_variables_are_withheld_from_the_control(
		self, tmp_path: Path
	) -> None:
		"""A differential varies one thing: the containment claim, not the whole env.

		``pi-research`` sets a pinned model and npm's log level, neither of which claims to
		bound anything. Withholding those too would leave the two arms differing in three
		ways at once, and a difference could no longer be attributed to containment.
		"""
		spec = dataclasses.replace(
			base_spec(tmp_path, "complete"),
			env=(("SYNTHETIC_HOME", "{session_dir}"), ("SYNTHETIC_EXTRA", "kept")),
			isolation_env=("SYNTHETIC_HOME",),
		)
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.STORE_ISOLATED)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.CONFIRMED
		assert "SYNTHETIC_HOME" in finding.attempted
		assert "SYNTHETIC_EXTRA" not in finding.attempted

	async def test_a_spec_that_asserts_no_containment_is_not_measured(self, tmp_path: Path) -> None:
		"""``pi`` isolates by ``--session-dir`` in its argv, and never claims this row."""
		spec = dataclasses.replace(base_spec(tmp_path, "complete"), isolation_env=())
		profile = await make_adapter(tmp_path, spec).probe()
		finding = profile.finding(HarnessCapability.STORE_ISOLATED)
		assert finding is not None
		assert finding.outcome is ProbeOutcome.INCONCLUSIVE
		assert "no attempt was made" in finding.attempted

	async def test_the_store_probe_leaves_the_build_workspace_untouched(
		self, tmp_path: Path
	) -> None:
		"""Both arms work in scratch: a probe never writes into the tree it is about."""
		profile = await adapter_for(tmp_path, "complete").probe()
		assert profile.finding(HarnessCapability.STORE_ISOLATED) is not None
		assert list((tmp_path / "workspace").iterdir()) == []
