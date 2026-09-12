"""The command line.

A presentation adapter holds no policy, so what is under test here is not formatting
but the decisions it makes: which state directory a spelling resolves to, which exit
code a missing precondition produces, and whether a misconfiguration arrives as a
message or as a traceback. Those are the three ways a thin CLI still goes wrong.

The other half of this module drives a **real child process** through a **real
``SOFACT_HARNESS_SPECS`` file**. That is the point of the configuration seam: a
deployment registers a harness in a file, and the CLI then probes, contracts, plans,
dispatches, checks integrity and measures precision against it with no Python-side
injection at all. If that file were the only way to reach the seam, the seam would be
unreachable — which is what it was before this suite existed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import GOOD_ANSWERS
from synthetic import base_spec, spec_json
from typer.testing import CliRunner, Result

from sofact.cli import app
from sofact.elicitation import DIMENSIONS
from sofact.harness import SPECS, HarnessSpec, load_specs

RUNNER = CliRunner()

_STATEMENT = "A reminder service that shows scheduled reminders in a web dashboard."


def conversation(home: Path) -> None:
	"""Drive the real interrogation to completion through the real CLI."""
	result = RUNNER.invoke(app, ["--home", str(home)], input=f"{_STATEMENT}\n{_answers()}\n")
	assert result.exit_code == 0, result.output
	assert "every dimension resolved" in result.output, result.output


def configure(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str = "complete"
) -> HarnessSpec:
	"""Register the synthetic harness with the CLI the way a deployment would."""
	spec = base_spec(tmp_path, mode)
	table = tmp_path / "harnesses.json"
	table.write_text(
		json.dumps({"harnesses": {spec.name: spec_json(spec)}}),
		encoding="utf-8",
	)
	monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(table))
	return spec


# --------------------------------------------------------------------------- #
# the conversation — the product's headline claim
# --------------------------------------------------------------------------- #


class TestTheConversation:
	def test_no_arguments_starts_an_interrogation(self, home: Path) -> None:
		"""`sofact` with nothing else is the product. Everything below is a side door."""
		conversation(home)
		assert (home / "ledger.jsonl").exists()

	def test_an_empty_statement_starts_nothing(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home)], input="\n")
		assert result.exit_code == 0, result.output
		assert "nothing to interrogate" in result.output
		assert not (home / "ledger.jsonl").exists()

	def test_stopping_midway_keeps_the_goal(self, home: Path) -> None:
		"""EOF is how a piped run ends. It must not be how progress ends."""
		stopped = RUNNER.invoke(app, ["--home", str(home)], input=f"{_STATEMENT}\n")
		assert stopped.exit_code == 0, stopped.output
		assert "stopped. Progress is in the log" in stopped.output

		resumed = RUNNER.invoke(app, ["--home", str(home)], input="\n")
		assert resumed.exit_code == 0, resumed.output
		assert "resuming goal" in resumed.output

	def test_the_advisor_is_optional(self, home: Path) -> None:
		"""The model is advisory (ADR-0008): with none reachable the interview proceeds."""
		result = RUNNER.invoke(app, ["--home", str(home)], input=f"{_STATEMENT}\n")
		assert "advisor:" in result.output
		assert "unreachable" in result.output
		assert "continuing with the plain questionnaire" in result.output


# --------------------------------------------------------------------------- #
# one state directory, whichever spelling
# --------------------------------------------------------------------------- #


class TestOneStateDirectory:
	def test_both_spellings_agree(self, home: Path) -> None:
		"""`sofact --home X status` and `sofact status --home X` must read one log.

		The regression this pins: the root option landed on the callback while the
		subcommand's copy landed on the subcommand, so the second spelling read
		``./.sofact`` and reported a goal that plainly existed as missing.
		"""
		RUNNER.invoke(app, ["--home", str(home)], input=f"{_STATEMENT}\n")
		before = RUNNER.invoke(app, ["--home", str(home), "status"])
		after = RUNNER.invoke(app, ["status", "--home", str(home)])
		assert before.exit_code == after.exit_code == 0
		assert "no goal yet" not in before.output
		assert "no goal yet" not in after.output
		assert _STATEMENT in after.output

	def test_softhome_is_honoured(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		"""`SOFACT_HOME` is the deployment knob; `--home` is the per-run override."""
		target = tmp_path / "env-home"
		monkeypatch.setenv("SOFACT_HOME", str(target))
		result = RUNNER.invoke(app, [], input="\n")
		assert result.exit_code == 0, result.output
		assert str(target) in result.output

	def test_version_needs_no_state(self) -> None:
		result = RUNNER.invoke(app, ["--version"])
		assert result.exit_code == 0
		assert result.output.startswith("sofact ")


# --------------------------------------------------------------------------- #
# preconditions — the CLI reports the missing step, it does not guess
# --------------------------------------------------------------------------- #


class TestPreconditions:
	@pytest.mark.parametrize("command", ["plan", "dispatch", "integrity"])
	def test_with_no_goal_it_says_so(self, home: Path, command: str) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), command])
		assert result.exit_code == 1
		assert "no goal yet." in result.output

	@pytest.mark.parametrize("command", ["plan", "dispatch", "integrity"])
	def test_with_no_contract_it_says_so(self, home: Path, command: str) -> None:
		RUNNER.invoke(app, ["--home", str(home)], input=f"{_STATEMENT}\n{_answers()}\n")
		result = RUNNER.invoke(app, ["--home", str(home), command])
		assert result.exit_code == 1
		assert "no contract yet" in result.output

	def test_dispatch_before_a_plan_says_so(self, home: Path) -> None:
		conversation(home)
		assert _contract(home).exit_code == 0
		result = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		assert result.exit_code == 1
		assert "no plan yet" in result.output

	def test_dispatch_with_nothing_selected_shows_the_plan(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The refusal to guess is also the discovery path: it prints what to pick."""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0
		result = RUNNER.invoke(app, ["--home", str(home), "dispatch"])
		assert result.exit_code == 0, result.output
		assert "nothing selected" in result.output
		assert "wave 0" in result.output


def _answers() -> str:
	return "\n".join(GOOD_ANSWERS[spec.dimension] for spec in DIMENSIONS)


def _contract(home: Path) -> Result:
	return RUNNER.invoke(app, ["--home", str(home), "contract", "--command", "true"])


# --------------------------------------------------------------------------- #
# the contract, and what it admits it cannot pay
# --------------------------------------------------------------------------- #


class TestTheContract:
	def test_a_command_makes_every_clause_executable(self, home: Path) -> None:
		conversation(home)
		result = _contract(home)
		assert result.exit_code == 0, result.output
		assert "ground-truth debt 0%" in result.output
		assert "these clauses name no command" not in result.output

	def test_without_a_command_the_debt_is_stated(self, home: Path) -> None:
		"""SoFact will not invent a command, so it reports the gap instead (§2.3)."""
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "contract"])
		assert result.exit_code == 0, result.output
		assert "ground-truth debt 100%" in result.output
		assert "these clauses name no command" in result.output

	def test_an_oracle_too_weak_to_trust_narrows_the_ceiling(self, home: Path) -> None:
		"""A suggested oracle names no command *and* ranks weak, so the ceiling drops."""
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "contract"])
		assert result.exit_code == 0, result.output
		assert "ceiling" in result.output


# --------------------------------------------------------------------------- #
# the configured harness table — the seam FR-156 asks for
# --------------------------------------------------------------------------- #


class TestConfiguredHarnesses:
	def test_the_cli_probes_a_harness_from_a_file(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch)
		result = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert result.exit_code == 0, result.output
		assert "synthetic probe" in result.output
		assert "synthetic 1.2.3" in result.output
		assert "usable=True" in result.output

	def test_a_single_configured_harness_becomes_the_default(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Otherwise a deployment that registered exactly one could not run it."""
		configure(tmp_path, monkeypatch)
		result = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert result.exit_code == 0, result.output
		assert "goal-mode=inconclusive" in result.output

	def test_the_whole_pipeline_runs_through_the_cli(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""probe → contract → plan → dispatch → integrity → precision, file-configured.

		Every arrow is a real command and every subprocess is the real child. This is
		the end-to-end evidence that the dispatch capability is reachable from the
		product's own surface rather than only from Python.
		"""
		configure(tmp_path, monkeypatch, mode="goal")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0

		probed = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert probed.exit_code == 0, probed.output
		assert "goal-mode=confirmed" in probed.output
		assert "→ goal dispatch" in probed.output

		dispatched = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		assert dispatched.exit_code == 0, dispatched.output
		assert "completed" in dispatched.output
		assert "declared complete" in dispatched.output

		checked = RUNNER.invoke(app, ["--home", str(home), "integrity"])
		assert checked.exit_code == 0, checked.output
		assert "intact" in checked.output

		measured = RUNNER.invoke(app, ["--home", str(home), "precision"])
		assert measured.exit_code == 0, measured.output
		assert "declaration precision of synthetic" in measured.output

	def test_a_failing_wave_exits_nonzero(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A run that stalls is a failed run, and the exit code is the contract."""
		configure(tmp_path, monkeypatch, mode="fail-after-first")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0

		dispatched = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		assert dispatched.exit_code == 1
		assert "failed" in dispatched.output
		assert "a declaration is not a finding" in dispatched.output

	def test_a_run_that_verified_nothing_exits_nonzero(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""An exit code is the contract: a run that checked nothing is not a pass.

		Measured before this rule existed: ``dispatch --all`` against a real harness exited
		0 having recorded zero evidence rows, because the trigger waited on a completion
		declaration the default harness cannot make.
		"""
		configure(tmp_path, monkeypatch, mode="fail")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0

		dispatched = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		assert dispatched.exit_code == 1
		assert "no verdict" in dispatched.output
		assert "not checked" in dispatched.output

	def test_a_capped_run_reports_progress_rather_than_failure(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""``--max-steps`` is a resumable workflow, so stopping early is not a failure.

		The oracle here is ``false`` on purpose, so the contract is *not* clean; the single
		step that ran covers no clause and therefore refuted nothing. The run made progress,
		the contract line says how much holds, and the exit code stays 0.
		"""
		configure(tmp_path, monkeypatch, mode="goal")
		conversation(home)
		contract = RUNNER.invoke(app, ["--home", str(home), "contract", "--command", "false"])
		assert contract.exit_code == 0, contract.output
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0

		dispatched = RUNNER.invoke(
			app, ["--home", str(home), "dispatch", "--all", "--max-steps", "1"]
		)
		assert dispatched.exit_code == 0, dispatched.output
		assert "contract violated" in dispatched.output
		assert "does not hold yet" in dispatched.output


# --------------------------------------------------------------------------- #
# misconfiguration — a message, not a traceback
# --------------------------------------------------------------------------- #


class TestTheToolSet:
	"""The producer's tool allowlist, reachable from the product's own surface.

	The adapter had a ``tools`` parameter from the beginning and no way to set it, which
	is the same as not having one: a value an operator cannot reach is a constant.
	"""

	def test_the_probe_reports_the_set_it_will_hand_over(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The tool set must be visible at probe time, not discovered mid-build."""
		configure(tmp_path, monkeypatch)
		result = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert result.exit_code == 0, result.output
		assert "tools   read,write,edit,bash" in result.output, result.output

	def test_the_flag_narrows_it(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch)
		result = RUNNER.invoke(app, ["--home", str(home), "probe", "--tools", "read"])
		assert result.exit_code == 0, result.output
		assert "tools   read" in result.output, result.output

	def test_the_environment_also_narrows_it(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch)
		monkeypatch.setenv("SOFACT_TOOLS", "read,grep")
		result = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert result.exit_code == 0, result.output
		assert "tools   read,grep" in result.output, result.output

	def test_an_empty_set_is_a_message_not_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch)
		result = RUNNER.invoke(app, ["--home", str(home), "probe", "--tools", ""])
		assert result.exit_code == 1, result.output
		assert "cannot use that tool set" in result.output
		assert "empty allowlist" in result.output
		assert "Traceback" not in result.output

	def test_dispatch_refuses_it_before_starting_a_session(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A refusal is only useful if nothing ran: no session, no ledger row."""
		configure(tmp_path, monkeypatch, mode="goal")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0

		refused = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all", "--tools", ""])
		assert refused.exit_code == 1, refused.output
		assert "cannot use that tool set" in refused.output
		assert "step.dispatched" not in refused.output


class TestTheModelIsPartOfTheConfiguration:
	"""The probe names the model it measured, and a refusal is a refusal to dispatch.

	A model the harness cannot resolve produced a session that exited non-zero with no
	record -- the same bytes as a producer that tried and failed. The two are different
	facts, and the operator is the one who has to act on the difference.
	"""

	def test_the_probe_reports_the_model_it_measured(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch)
		monkeypatch.setenv("SOFACT_MODEL", "qwen3.6:35b-mlx")
		result = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert result.exit_code == 0, result.output
		assert "model   qwen3.6:35b-mlx" in result.output, result.output
		assert "model_resolved" in result.output, "the row must be reported like any other"

	def test_a_refused_model_fails_the_probe_and_says_which_party_is_at_fault(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch, mode="badmodel-once")
		monkeypatch.setenv("SOFACT_MODEL", "synthetic-nonesuch:latest")
		result = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert result.exit_code == 1, result.output
		assert "cannot resolve the model" in result.output
		assert "fix SOFACT_MODEL" in result.output
		assert "Traceback" not in result.output

	def test_the_dispatched_refusal_names_the_model_not_the_producer(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Dispatch must attribute it before it starts, not after a session fails."""
		configure(tmp_path, monkeypatch, mode="badmodel-once")
		monkeypatch.setenv("SOFACT_MODEL", "synthetic-nonesuch:latest")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		probed = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert probed.exit_code == 1, probed.output

		refused = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		assert refused.exit_code == 1, refused.output
		assert "model-resolution failure and not a producer failure" in refused.output
		assert "synthetic-nonesuch:latest" in refused.output
		assert "step.dispatched" not in refused.output

	def test_a_refusal_reached_through_the_adapter_is_printed(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The CLI gate catches one refusal; the adapter's gate catches the other.

		A profile measured with a different model is not visible to the preflight check,
		so the only place its reason reaches the operator is the record's own note.
		"""
		configure(tmp_path, monkeypatch, mode="complete")
		monkeypatch.setenv("SOFACT_MODEL", "a-model-that-was-probed")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0

		refused = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"dispatch",
				"--all",
				"--model",
				"a-model-nobody-probed",
			],
		)
		assert refused.exit_code == 1, refused.output
		assert "not_dispatched" in refused.output
		assert "a-model-that-was-probed" in refused.output
		assert "a-model-nobody-probed" in refused.output
		assert "nothing ran, so there is no artefact" in refused.output
		assert "not checked: an incomplete session" not in refused.output


class TestMisconfiguration:
	def test_an_unknown_harness_is_reported(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "probe", "--harness", "nosuch"])
		assert result.exit_code == 1
		assert "unknown harness 'nosuch'" in result.output
		assert "configured harnesses: dsh, pi" in result.output

	def test_a_malformed_config_file_is_reported(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		table = tmp_path / "bad.json"
		table.write_text("{not json", encoding="utf-8")
		monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(table))
		result = RUNNER.invoke(app, ["--home", str(home), "status"])
		assert result.exit_code == 1
		assert "cannot read SOFACT_HARNESS_SPECS" in result.output
		assert "not valid JSON" in result.output

	def test_a_missing_config_file_is_reported(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(tmp_path / "absent.json"))
		result = RUNNER.invoke(app, ["--home", str(home), "status"])
		assert result.exit_code == 1
		assert "cannot read harness table" in result.output

	def test_an_ambiguous_table_refuses_to_guess(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Naming neither of two harnesses must refuse, not pick one at random."""
		alpha = base_spec(tmp_path, "complete", name="alpha")
		beta = base_spec(tmp_path, "complete", name="beta")
		table = tmp_path / "two.json"
		table.write_text(
			json.dumps({"harnesses": {"alpha": spec_json(alpha), "beta": spec_json(beta)}}),
			encoding="utf-8",
		)
		monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(table))

		result = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert result.exit_code == 1
		assert "cannot choose a harness" in result.output

		named = RUNNER.invoke(app, ["--home", str(home), "probe", "--harness", "alpha"])
		assert named.exit_code == 0, named.output
		assert "alpha probe" in named.output


# --------------------------------------------------------------------------- #
# the loader, on its own terms
# --------------------------------------------------------------------------- #


class TestLoadSpecs:
	def test_the_built_in_table_is_untouched(self) -> None:
		assert set(SPECS) == {"dsh", "pi"}

	def test_a_round_trip_preserves_every_field(self, tmp_path: Path) -> None:
		"""Derived from the real spec, so this cannot drift from the dataclass."""
		spec = base_spec(tmp_path, "complete", zstd=True)
		path = tmp_path / "table.json"
		path.write_text(
			json.dumps({"harnesses": {spec.name: spec_json(spec)}}),
			encoding="utf-8",
		)
		assert load_specs(path) == {spec.name: spec}

	@pytest.mark.parametrize("wrapped", [True, False])
	def test_both_shapes_are_accepted(self, tmp_path: Path, wrapped: bool) -> None:
		spec = base_spec(tmp_path, "complete")
		specs = {spec.name: spec_json(spec)}
		body = {"harnesses": specs} if wrapped else specs
		path = tmp_path / f"table-{wrapped}.json"
		path.write_text(json.dumps(body), encoding="utf-8")
		assert set(load_specs(path)) == {spec.name}

	@pytest.mark.parametrize(
		("field", "value", "fragment"),
		[
			("argv", "pi -p", "argv must be an array of strings"),
			("argv", [1, 2], "argv must contain only strings"),
			("version_argv", 5, "version_argv must be an array of strings"),
			("env", "DSH_HOME=/tmp", "env must be an array"),
			("env", [["a"]], "exactly two elements"),
			("env", [["a", 1]], "env keys and values must be strings"),
			("session_is_zstd", "false", "session_is_zstd must be true or false"),
			("supports_context_file_flag", 1, "must be true or false"),
			("usage_reduce", "total", "usage_reduce must be one of"),
			("goal_entry", "banana", "goal_entry must be one of"),
			("goal_entry", 3, "goal_entry must be a string"),
			("notes", 7, "notes must be a string"),
			("completion_event", 4, "completion_event must be a string"),
		],
	)
	def test_a_malformed_field_is_refused_by_name(
		self, tmp_path: Path, field: str, value: object, fragment: str
	) -> None:
		"""Every message names the harness and the field: a typo must be findable."""
		payload = spec_json(base_spec(tmp_path, "complete"))
		payload[field] = value
		path = tmp_path / "table.json"
		path.write_text(json.dumps({"harnesses": {"synthetic": payload}}), encoding="utf-8")
		with pytest.raises(ValueError, match=fragment) as raised:
			load_specs(path)
		assert "synthetic" in str(raised.value)

	@pytest.mark.parametrize("drop", ["argv", "completion_reason_path"])
	def test_a_required_field_is_refused(self, tmp_path: Path, drop: str) -> None:
		payload = spec_json(base_spec(tmp_path, "complete"))
		del payload[drop]
		path = tmp_path / "table.json"
		path.write_text(json.dumps({"harnesses": {"synthetic": payload}}), encoding="utf-8")
		with pytest.raises(ValueError) as raised:
			load_specs(path)
		assert drop in str(raised.value)

	def test_an_unknown_field_is_refused(self, tmp_path: Path) -> None:
		"""A misspelled field that fell back to its default would be a silent wrong."""
		payload = spec_json(base_spec(tmp_path, "complete"))
		payload["usgae_reduce"] = "sum"
		path = tmp_path / "table.json"
		path.write_text(json.dumps({"harnesses": {"synthetic": payload}}), encoding="utf-8")
		with pytest.raises(ValueError, match="unknown field"):
			load_specs(path)

	def test_an_empty_table_is_refused(self, tmp_path: Path) -> None:
		"""An empty table names no harness, so it is a mistake rather than a no-op."""
		path = tmp_path / "empty.json"
		path.write_text("{}", encoding="utf-8")
		with pytest.raises(ValueError, match="no harnesses"):
			load_specs(path)

	def test_a_non_object_harness_is_refused(self, tmp_path: Path) -> None:
		path = tmp_path / "table.json"
		path.write_text(json.dumps({"harnesses": {"synthetic": "pi -p"}}), encoding="utf-8")
		with pytest.raises(ValueError, match="must be an object"):
			load_specs(path)


class TestTheDocumentedTable:
	"""README.md's example table is executed by the real loader.

	Documentation that is never run is documentation that is eventually wrong, and this
	particular document is load-bearing: it is the only place the table's *shape* is shown
	to someone pointing SoFact at a new harness. A drift here is not a typo, it is a user
	writing a file that SoFact refuses.
	"""

	ROOT = Path(__file__).resolve().parents[2]

	def load_documented_tables(self, tmp_path: Path) -> dict[str, HarnessSpec]:
		"""Every JSON fence in README.md, through the loader the CLI calls.

		A fence the loader refuses is skipped rather than failed, because the README is
		allowed to show a deliberately broken example. What must not happen is that *no*
		fence loads, which the callers assert by requiring the documented name.
		"""
		text = (self.ROOT / "README.md").read_text(encoding="utf-8")
		blocks = re.findall(r"```json\n(.*?)```", text, re.S)
		assert blocks, "README.md no longer shows a JSON harness table"

		loaded: dict[str, HarnessSpec] = {}
		for index, block in enumerate(blocks):
			path = tmp_path / f"readme-{index}.json"
			path.write_text(block, encoding="utf-8")
			try:
				loaded.update(load_specs(path))
			except ValueError:
				continue
		return loaded

	def test_the_readme_example_loads_through_the_real_loader(self, tmp_path: Path) -> None:
		loaded = self.load_documented_tables(tmp_path)
		assert "my-harness" in loaded, sorted(loaded)

	def test_the_documented_placeholders_are_the_ones_the_adapter_fills(
		self, tmp_path: Path
	) -> None:
		"""The prose promises ``{goal}`` and ``{session_id}``; the example must show them."""
		spec = self.load_documented_tables(tmp_path)["my-harness"]

		assert "{goal}" in spec.argv
		assert "{session_id}" in spec.argv
