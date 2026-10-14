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

import asyncio
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
from sofact.service import FactoryService
from sofact.views import GateCheck, Phase, PhaseGate, PhaseStatus

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
# the phase machine — FR-060 and FR-061 at the operator's surface
# --------------------------------------------------------------------------- #


class TestThePhaseVerb:
	"""The phase must be readable, and an open gate must be a stop, not a label."""

	def test_a_fresh_home_is_in_p0(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "phase"])
		assert result.exit_code == 0, result.output
		assert "phase P0" in result.output
		assert "P0 elicit" in result.output

	def test_status_shows_the_phase_alongside_the_goal(self, home: Path) -> None:
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "status"])
		assert result.exit_code == 0, result.output
		assert "phase P0" in result.output

	def test_presenting_a_gate_stops_the_verb_with_a_nonzero_exit(self, home: Path) -> None:
		"""FR-061 as an exit code: a script driving the pipeline can check this.

		The gate is presented through the service because the phase's own command is
		where machine checks are computed; this test is about the *reporting*, so it
		only needs a gate to exist.
		"""
		service = FactoryService(home)
		asyncio.run(service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE))
		asyncio.run(service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE))
		asyncio.run(
			service.advance_phase(
				Phase.SPECIFY,
				PhaseStatus.AWAITING_GATE,
				checks=(
					GateCheck(
						name="internal_consistency",
						passed=True,
						detail="no clause contradicts another",
					),
				),
			)
		)

		result = RUNNER.invoke(app, ["--home", str(home), "phase"])
		assert result.exit_code == 1, result.output
		assert "stopped at the specification gate" in result.output
		assert "internal_consistency" in result.output
		assert "sofact gate --approve P2" in result.output

	def test_a_gate_with_no_checks_says_so_rather_than_offering_approval(self, home: Path) -> None:
		"""An approval button over nothing presented is the theatre FR-080 warns about."""
		service = FactoryService(home)
		asyncio.run(service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE))
		asyncio.run(service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE))
		asyncio.run(service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE))
		result = RUNNER.invoke(app, ["--home", str(home), "phase"])
		assert result.exit_code == 1
		assert "nothing has been presented to approve yet" in result.output

	def test_gate_requires_exactly_one_of_present_or_approve(self, home: Path) -> None:
		both = RUNNER.invoke(
			app, ["--home", str(home), "gate", "--present", "P2", "--approve", "P2"]
		)
		assert both.exit_code == 1
		assert "exactly one of" in both.output

		neither = RUNNER.invoke(app, ["--home", str(home), "gate"])
		assert neither.exit_code == 1
		assert "exactly one of" in neither.output

	def test_an_unknown_phase_names_the_ones_that_exist(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "gate", "--present", "P42"])
		assert result.exit_code == 1
		assert "not a phase" in result.output
		assert "P0" in result.output

	def test_approving_a_gate_nobody_presented_is_refused(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "gate", "--approve", "P2"])
		assert result.exit_code == 1
		assert "cannot approve" in result.output

	def test_an_ungated_phase_cannot_be_presented(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "gate", "--present", "P5"])
		assert result.exit_code == 1
		assert "cannot present" in result.output

	def test_present_then_approve_moves_the_pipeline_and_names_who(self, home: Path) -> None:
		"""The whole operator path, end to end, through the CLI only."""
		service = FactoryService(home)
		asyncio.run(service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE))
		asyncio.run(service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE))

		presented = RUNNER.invoke(
			app, ["--home", str(home), "gate", "--present", "P2", "--by", "operator"]
		)
		assert presented.exit_code == 0, presented.output
		assert "P2 presented" in presented.output
		assert "specification gate" in presented.output

		approved = RUNNER.invoke(
			app, ["--home", str(home), "gate", "--approve", "P2", "--by", "nyimbi"]
		)
		assert approved.exit_code == 0, approved.output
		assert "P2 approved by nyimbi" in approved.output
		assert "P3" in approved.output

		after = RUNNER.invoke(app, ["--home", str(home), "phase"])
		assert after.exit_code == 0, after.output
		assert "phase P3" in after.output


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


SPECIFY_ARGS: list[str] = [
	"--entity",
	"Reminder:1",
	"--assumption",
	"Reminders are scheduled client-side | a server scheduler in the deployment",
	"--value",
	"Fewer missed reminders | the end user | dashboard session logs",
]
"""The operator's half of the P2 gate, as flags.

FR-078, FR-079 and FR-085 make the model, the assumptions and the value hypothesis
required, and they are the operator's own statements rather than derivations — so a
pipeline that wants to reach P3 has to supply them, exactly as production does. Kept in
one place because every CLI test that wants a plan now runs through this gate.
"""


def _proposed(home: Path) -> Result:
	"""Run P4, P2 and P3's proposal, stopping short of the approval.

	Needed by the tests whose subject *is* the refusal: ``_contract`` approves, and a
	decomposition the envelope refuses cannot be approved — so a helper that insisted on
	one would make the refusal unreachable from the tests written to observe it.
	"""
	result = RUNNER.invoke(app, ["--home", str(home), "contract", "--command", "true"])
	if result.exit_code != 0:
		return result
	specified = RUNNER.invoke(app, ["--home", str(home), "specify", "--approve", *SPECIFY_ARGS])
	if specified.exit_code != 0:
		return specified
	return RUNNER.invoke(app, ["--home", str(home), "decompose"])


def _contract(home: Path) -> Result:
	"""Run P4, then P2, then P3, then approve — the gates FR-061 says nothing may pass.

	``decompose`` refuses a contract whose specification is unapproved, and ``plan``
	refuses one whose decomposition is unapproved, so every test that wants a plan has to
	come through both gates. Folding them into the helper rather than passing a bypass
	keeps the suite on the path production has.
	"""
	result = RUNNER.invoke(app, ["--home", str(home), "contract", "--command", "true"])
	if result.exit_code != 0:
		return result
	specified = RUNNER.invoke(app, ["--home", str(home), "specify", "--approve", *SPECIFY_ARGS])
	if specified.exit_code != 0:
		return specified
	decomposed = RUNNER.invoke(app, ["--home", str(home), "decompose", "--approve"])
	if decomposed.exit_code != 0:
		return decomposed
	return result


# --------------------------------------------------------------------------- #
# the contract, and what it admits it cannot pay
# --------------------------------------------------------------------------- #


class TestTheContract:
	def test_a_command_makes_every_clause_executable(self, home: Path) -> None:
		conversation(home)
		result = _contract(home)
		assert result.exit_code == 0, result.output
		assert "ground-truth debt 0%" in result.output
		assert "no oracle covers" not in result.output

	def test_without_a_command_the_debt_is_stated(self, home: Path) -> None:
		"""SoFact will not invent a command, so it reports the gap instead (§2.3)."""
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "contract"])
		assert result.exit_code == 0, result.output
		assert "ground-truth debt 100%" in result.output
		assert "no oracle covers" in result.output
		assert "names no command" in result.output

	def test_an_oracle_too_weak_to_trust_narrows_the_ceiling(self, home: Path) -> None:
		"""A suggested oracle names no command *and* ranks weak, so the ceiling drops."""
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "contract"])
		assert result.exit_code == 0, result.output
		assert "ceiling" in result.output

	def test_an_uncovered_clause_says_the_ceiling_is_l2(self, home: Path) -> None:
		"""FR-109, at the surface the operator reads.

		The suggested oracle ranks 3 (a contract test), which on rank alone grants L3. It
		names no command, so nothing can run it and the cap is what makes the printed
		ceiling L2 — and the line has to say so, because a number that dropped with no
		reason given is one the operator cannot act on.
		"""
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "contract"])
		assert result.exit_code == 0, result.output
		assert "weakest oracle rank 3" in result.output
		assert "ceiling L2" in result.output, "rank 3 alone would print L3"
		assert "no oracle covers, so the ceiling is L2 (FR-109)" in result.output


class TestTheInterfaceCount:
	"""FR-091 at the surface: the number the operator approves is the number §20.1 names.

	The gate reports it and the CLI prints it, and the two are read at different moments by
	different readers. Checking the printed line against *itself* is what is available here
	without reaching into the service: the count has to be the size of the list printed
	underneath it, and the ratio has to be the members over that same count. A number that
	disagrees with the list it counts is a number nobody can act on.
	"""

	def test_the_count_is_the_size_of_the_list_beneath_it(self, home: Path) -> None:
		conversation(home)
		result = _proposed(home)
		assert result.exit_code == 0, result.output
		counts = re.search(
			r"(\d+) module\(s\); (\d+) declared member\(s\) on their surfaces "
			r"\(([\d.]+) per module, FR-091\)",
			result.output,
		)
		assert counts is not None, result.output
		modules, members, ratio = int(counts.group(1)), int(counts.group(2)), counts.group(3)
		order = re.search(r"build order: (.+)", result.output)
		assert order is not None, result.output
		assert len(order.group(1).split(" -> ")) == modules
		assert ratio == f"{members / modules:.1f}", "the ratio is the members over that count"
		assert "G1-G2 share" in result.output, "FR-125 is printed beside it, not instead of it"


# --------------------------------------------------------------------------- #
# the adversarial audit — FR-107 at the operator's surface
# --------------------------------------------------------------------------- #


class TestTheAuditVerb:
	def test_an_oracle_satisfied_by_nothing_exits_nonzero(self, home: Path) -> None:
		"""FR-107's defect, at the surface, with a non-zero exit so a script can gate on it.

		``--commands true`` is the operator's own declaration that every clause is checked
		by ``true``, and the audit is what says that declaration checks nothing.
		"""
		conversation(home)
		RUNNER.invoke(app, ["--home", str(home), "contract", "--command", "true"])

		result = RUNNER.invoke(app, ["--home", str(home), "audit"])

		assert result.exit_code == 1, result.output
		assert "FR-107 oracle audit" in result.output
		assert "was satisfied without implementing anything" in result.output
		assert "false claim of coverage" in result.output

	def test_an_oracle_that_can_fail_exits_zero(self, home: Path) -> None:
		"""The control arm: the same verb, a command that cannot pass against nothing."""
		conversation(home)
		RUNNER.invoke(
			app,
			["--home", str(home), "contract", "--command", "pytest tests/test_report.py"],
		)

		result = RUNNER.invoke(app, ["--home", str(home), "audit"])

		assert result.exit_code == 0, result.output
		assert "can fail against an empty workspace" in result.output
		assert "false claim of coverage" not in result.output

	def test_the_audit_names_what_it_could_not_ask(self, home: Path) -> None:
		"""The negative clauses are reported rather than passed.

		The interrogation derives BOUNDARY and FAILURE as negative, so this is the state
		of every real contract — and a screen that showed only the probed half would let
		an operator read "skipped" as "fine".
		"""
		conversation(home)
		RUNNER.invoke(app, ["--home", str(home), "contract", "--command", "true"])

		result = RUNNER.invoke(app, ["--home", str(home), "audit"])

		assert "[skip]" in result.output
		assert "asserts an absence" in result.output

	def test_a_contract_of_intentions_reports_the_gap_not_a_clean_pass(self, home: Path) -> None:
		"""Nothing probed is not the same fact as nothing found, and the screen says which.

		Every suggested oracle names no command, so the audit asks nothing — and it must
		not exit 0 with a green line, because a reader would take that for a clearance.
		"""
		conversation(home)
		RUNNER.invoke(app, ["--home", str(home), "contract"])

		result = RUNNER.invoke(app, ["--home", str(home), "audit"])

		assert "not implemented: FR-107" in result.output
		assert "cleared nothing" in result.output
		assert "can fail against an empty workspace" not in result.output

	def test_the_audit_without_a_contract_says_so(self, home: Path) -> None:
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "audit"])
		assert result.exit_code == 1, result.output
		assert "no contract yet" in result.output


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

	def test_a_recordless_session_does_not_read_as_a_green_completion(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The caveat must be visible, not merely recorded.

		Measured on this tree before the note was printed for every outcome: a child that
		exits 0 and leaves no session record read as ``[0] completed`` in green with "the
		session completed, so its artefact was checked (FR-163)" underneath it — while the
		one sentence saying nothing was witnessed sat unprinted in ``record.note``, shown
		only for ``NOT_DISPATCHED``. The outcome is correct (FR-163 triggers on the
		process, not on the record, and the verdict is about the tree), so the fix is the
		*display*: a caveat the operator cannot see contradicts the line above it.
		"""
		configure(tmp_path, monkeypatch, mode="silent")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0

		dispatched = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		assert "nothing about this session was witnessed" in dispatched.output, dispatched.output

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
		assert (
			RUNNER.invoke(
				app, ["--home", str(home), "specify", "--approve", *SPECIFY_ARGS]
			).exit_code
			== 0
		)
		assert RUNNER.invoke(app, ["--home", str(home), "decompose", "--approve"]).exit_code == 0
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


class TestTheVerdictCache:
	"""A repeated check of an unchanged workspace says it reused, and names the moment.

	The operator must be able to tell a second measurement from a reuse — a verdict that
	looked freshly measured but was carried forward would be exactly the plausible
	signal FR-006 exists to prevent.
	"""

	def test_steps_that_did_not_change_the_workspace_say_what_they_reused(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The synthetic harness writes nothing into the workspace, so only the first
		step's check measures; every later step reuses the standing verdict (FR-006)."""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0

		first = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		assert first.exit_code == 0, first.output
		assert "reused from the check at" in first.output, (
			"a step that changed nothing must say it reused rather than claim a re-measure"
		)
		assert "the oracles did not run again" in first.output

		fresh = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all", "--fresh"])
		assert fresh.exit_code == 0, fresh.output
		assert "reused from" not in fresh.output

	def test_fresh_remeasures_and_says_nothing_about_reuse(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"]).exit_code == 0

		fresh = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all", "--fresh"])
		assert fresh.exit_code == 0, fresh.output
		assert "reused from" not in fresh.output


class TestTheQuickProbe:
	"""``--quick`` trades coverage for time, and says which rows it traded away.

	A probe is what a dispatch is allowed to assume, so a row it skipped has to be
	distinguishable from a row it measured and found wanting. The flag must make a visible
	difference rather than quietly doing less.
	"""

	def test_the_full_probe_measures_the_rows_the_quick_one_skips(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch)
		full = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert full.exit_code == 0, full.output
		assert "not requested" not in full.output, full.output
		assert "sandboxable" in full.output

		quick = RUNNER.invoke(app, ["--home", str(home), "probe", "--quick"])
		assert quick.exit_code == 0, quick.output
		assert "not requested" in quick.output, "the skipped rows must say they were skipped"


class TestMisconfiguration:
	def test_an_unknown_harness_is_reported(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "probe", "--harness", "nosuch"])
		assert result.exit_code == 1
		assert "unknown harness 'nosuch'" in result.output
		assert "configured harnesses: claude, dsh, opencode, pi" in result.output

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
		assert set(SPECS) == {"dsh", "pi", "claude", "opencode", "pi-research"}

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


# --------------------------------------------------------------------------- #
# the research verb (FR-167)
# --------------------------------------------------------------------------- #


class TestTheResearchVerb:
	"""``sofact research`` dispatches a research run and reports its artefacts.

	The verb's exit code follows the dispatch rule: the run is responsible for
	leaving a report, so a session that did not complete — or completed without one
	— is a red light, while a report with no sources is a measured fact printed in
	warning colour rather than a failure.
	"""

	def _configure_research(
		self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
	) -> None:
		spec = base_spec(tmp_path, mode, name="pi-research")
		table = tmp_path / "harnesses.json"
		table.write_text(
			json.dumps({"harnesses": {spec.name: spec_json(spec)}}),
			encoding="utf-8",
		)
		monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(table))

	def test_research_without_a_goal_says_so(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research")
		result = RUNNER.invoke(app, ["--home", str(home), "research"])
		assert result.exit_code == 1
		assert "no goal yet" in result.output
		assert "Traceback" not in result.output

	def test_a_completed_research_run_prints_its_sources(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research")
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "research"])
		assert result.exit_code == 0, result.output
		assert "completed" in result.output
		assert "report" in result.output
		assert "sources 3" in result.output
		assert "https://example.com/one" in result.output
		assert "searches 5" in result.output

	def test_a_truncated_loop_is_reported_as_unmeasured(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research-stub")
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "research"])
		assert result.exit_code == 0, result.output
		assert "searches 2" in result.output
		assert "no source URLs were recorded" in result.output
		assert "not research that found nothing" in result.output

	def test_the_run_prints_the_budget_it_was_measured_against(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-072: the operator sees the bound before reading the spend against it.

		The flags are **per intent clause**, and the fixture's interrogation leaves a
		five-stem draft, so `--max-sources 7` is a whole-run allowance of 35. The line
		prints the totals *and* the clause count, because a reader who saw "35 sources"
		alone would take it for the declaration rather than the product.
		"""
		self._configure_research(tmp_path, monkeypatch, "research")
		conversation(home)
		result = RUNNER.invoke(
			app, ["--home", str(home), "research", "--max-sources", "7", "--max-calls", "4"]
		)
		assert result.exit_code == 0, result.output
		assert "35 source(s), 20 call(s)" in result.output, "5 stems x the per-clause caps"
		assert "5 intent clause(s), FR-072" in result.output
		assert "calls    3" in result.output
		assert "over budget" not in result.output, "3 calls is inside 20"

	def test_an_overspent_run_says_which_cap_it_broke(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The loop's meta reports 9 turns; a per-clause cap of 1 over 5 stems allows 5."""
		self._configure_research(tmp_path, monkeypatch, "research-greedy")
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "research", "--max-calls", "1"])
		assert result.exit_code == 0, result.output
		assert "over budget: model-call cap 5 exceeded: 9 observed" in result.output
		assert "calls    9" in result.output

	def test_an_unmeasured_call_count_is_printed_as_unmeasured(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The truncated meta has no turn count, and the verb says so rather than 0."""
		self._configure_research(tmp_path, monkeypatch, "research-stub")
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "research"])
		assert result.exit_code == 0, result.output
		assert "calls    unmeasured" in result.output
		assert "was not checked either way" in result.output

	def test_a_zero_budget_is_refused_without_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research")
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "research", "--max-sources", "0"])
		assert result.exit_code == 1
		assert "bad research budget" in result.output
		assert "Traceback" not in result.output


# --------------------------------------------------------------------------- #
# the source ledger verb (FR-070)
# --------------------------------------------------------------------------- #


class TestTheSourcesVerb:
	"""``sofact sources`` prints the ledger, and reads one out of a run's workspace.

	The parser and the checks are measured in ``test_service.py``. What is under test
	here is reachability and the exit code: the disconfirming count has to be visible,
	and a failed check has to exit non-zero or nobody notices it failed.
	"""

	def _configure_research(
		self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
	) -> None:
		spec = base_spec(tmp_path, mode, name="pi-research")
		table = tmp_path / "harnesses.json"
		table.write_text(
			json.dumps({"harnesses": {spec.name: spec_json(spec)}}),
			encoding="utf-8",
		)
		monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(table))

	def test_without_a_ledger_the_verb_says_what_to_run(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research")
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "sources"])

		assert result.exit_code == 1, result.output
		assert "no source ledger yet" in result.output
		assert "sofact research" in result.output
		assert "Traceback" not in result.output

	def test_a_run_can_be_read_into_a_ledger_and_printed(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research")
		conversation(home)
		dispatched = RUNNER.invoke(app, ["--home", str(home), "research"])
		assert dispatched.exit_code == 0, dispatched.output
		run_id = dispatched.output.split("research ")[1].split(" @")[0].strip()

		result = RUNNER.invoke(app, ["--home", str(home), "sources", "--from-run", run_id])

		assert result.exit_code == 1, "C3 rests only on positioning: the check must fail"
		assert "recorded ledger v1" in result.output
		assert "[S01] A measured paper" in result.output
		assert "[S02] A vendor page" in result.output
		assert "1 disconfirming" in result.output, "FR-071's count is reported"
		assert "DISCONFIRMS" in result.output
		assert "1 contradiction(s)" in result.output
		assert "UNRESOLVED" in result.output, "FR-073 hands the disagreement to the operator"
		assert "rests on it: C1, C2" in result.output, "FR-070's edge is navigable"
		assert "not allowed to decide anything on their own" in result.output

	def test_the_recorded_ledger_is_read_back_from_the_log(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Once recorded, the ledger is in the log — the workspace is not needed again."""
		self._configure_research(tmp_path, monkeypatch, "research")
		conversation(home)
		dispatched = RUNNER.invoke(app, ["--home", str(home), "research"])
		run_id = dispatched.output.split("research ")[1].split(" @")[0].strip()
		assert (
			RUNNER.invoke(app, ["--home", str(home), "sources", "--from-run", run_id]).exit_code
			== 1
		)

		again = RUNNER.invoke(app, ["--home", str(home), "sources"])

		assert "[S01] A measured paper" in again.output
		assert (
			"source_ledger.recorded" in RUNNER.invoke(app, ["--home", str(home), "ledger"]).output
		)
		assert RUNNER.invoke(app, ["--home", str(home), "verify-ledger"]).exit_code == 0

	def test_a_run_that_left_no_ledger_is_refused_without_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research-stub")
		conversation(home)
		dispatched = RUNNER.invoke(app, ["--home", str(home), "research"])
		run_id = dispatched.output.split("research ")[1].split(" @")[0].strip()

		result = RUNNER.invoke(app, ["--home", str(home), "sources", "--from-run", run_id])

		assert result.exit_code == 1, result.output
		assert "left no research-sources/" in result.output
		assert "Traceback" not in result.output

	def test_an_unknown_run_is_refused(self, home: Path) -> None:
		conversation(home)
		result = RUNNER.invoke(
			app,
			["--home", str(home), "sources", "--from-run", "01900000-0000-7000-8000-000000000000"],
		)

		assert result.exit_code == 1, result.output
		assert "no research run" in result.output
		assert "Traceback" not in result.output


# --------------------------------------------------------------------------- #
# the classification verb (FR-068)
# --------------------------------------------------------------------------- #


class TestTheClassifyVerb:
	"""``sofact classify`` prints a verdict per clause, each with its action.

	The type, the parser and the checks are measured in ``test_service.py``. What is
	under test here is that the *action* reaches the reader and that a stop exits
	non-zero — a verdict printed as a finding rather than a stop is the whole failure
	FR-068 exists to prevent.
	"""

	def _configure_research(
		self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
	) -> None:
		spec = base_spec(tmp_path, mode, name="pi-research")
		table = tmp_path / "harnesses.json"
		table.write_text(
			json.dumps({"harnesses": {spec.name: spec_json(spec)}}),
			encoding="utf-8",
		)
		monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(table))

	def _classified(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
	) -> str:
		"""A drafted goal, a research run, its ledger and its classification, by CLI."""
		self._configure_research(tmp_path, monkeypatch, mode)
		conversation(home)
		assert RUNNER.invoke(app, ["--home", str(home), "draft"]).exit_code == 0
		dispatched = RUNNER.invoke(app, ["--home", str(home), "research"])
		assert dispatched.exit_code == 0, dispatched.output
		run_id = dispatched.output.split("research ")[1].split(" @")[0].strip()
		assert (
			RUNNER.invoke(app, ["--home", str(home), "sources", "--from-run", run_id]).exit_code
			== 1
		), "the ledger is recorded even though its own check fails"
		read = RUNNER.invoke(app, ["--home", str(home), "classify", "--from-run", run_id])
		assert "recorded classification v1" in read.output, read.output
		return run_id

	def test_without_a_classification_the_verb_says_what_to_run(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research")
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "classify"])

		assert result.exit_code == 1, result.output
		assert "no classification yet" in result.output
		assert "sofact classify --from-run" in result.output
		assert "Traceback" not in result.output

	def test_every_verdict_prints_with_its_action(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._classified(home, tmp_path, monkeypatch, "research-classification")

		result = RUNNER.invoke(app, ["--home", str(home), "classify"])

		assert result.exit_code == 0, result.output
		assert "5 clause(s) classified" in result.output
		assert result.output.count("[validated]") == 5
		assert "action: proceed" in result.output
		assert "0 invalidated" in result.output
		assert "every-clause-is-classified" in result.output

	def test_an_invalidated_clause_prints_the_stop_and_exits_non_zero(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-068's action is "do not build", so the verb may not exit 0 over it."""
		self._classified(home, tmp_path, monkeypatch, "research-classify-invalidated")

		result = RUNNER.invoke(app, ["--home", str(home), "classify"])

		assert result.exit_code == 1, result.output
		assert "[invalidated]" in result.output
		assert "return to P0" in result.output
		assert "nothing-is-invalidated" in result.output
		assert "return the pipeline to P0" in result.output, "the stop is stated, not implied"

	def test_an_unverifiable_clause_prints_the_assumption_it_becomes(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-068's Unverifiable action is a flagged assumption, and FR-079 wants a refuter."""
		self._classified(home, tmp_path, monkeypatch, "research-classify-unverifiable")

		result = RUNNER.invoke(app, ["--home", str(home), "classify"])

		assert result.exit_code == 0, "proceeding as an assumption is not a stop"
		assert "[unverifiable]" in result.output
		assert "carried into P2 as flagged assumptions" in result.output
		assert "Unverified premise (FR-068)" in result.output
		assert "refuted by" in result.output

	def test_a_verdict_citing_a_source_outside_the_ledger_fails(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._classified(home, tmp_path, monkeypatch, "research-classify-dangling")

		result = RUNNER.invoke(app, ["--home", str(home), "classify"])

		assert result.exit_code == 1, result.output
		assert "classification-cites-the-ledger" in result.output

	def test_a_producer_that_classified_fewer_clauses_than_it_was_asked_fails(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The clause list is SoFact's, so answering a smaller question is a failure."""
		self._classified(home, tmp_path, monkeypatch, "research-classify-partial")

		result = RUNNER.invoke(app, ["--home", str(home), "classify"])

		assert result.exit_code == 1, result.output
		assert "1 clause(s) classified" in result.output
		assert "every-clause-is-classified" in result.output
		assert "4 clause(s) unclassified" in result.output, "the missing four are named"

	def test_a_run_that_left_no_classification_is_refused_without_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure_research(tmp_path, monkeypatch, "research-stub")
		conversation(home)
		dispatched = RUNNER.invoke(app, ["--home", str(home), "research"])
		run_id = dispatched.output.split("research ")[1].split(" @")[0].strip()

		result = RUNNER.invoke(app, ["--home", str(home), "classify", "--from-run", run_id])

		assert result.exit_code == 1, result.output
		assert "left no research-classification.json" in result.output
		assert "Traceback" not in result.output

	def test_an_unknown_run_is_refused(self, home: Path) -> None:
		conversation(home)
		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"classify",
				"--from-run",
				"01900000-0000-7000-8000-000000000000",
			],
		)

		assert result.exit_code == 1, result.output
		assert "no research run" in result.output
		assert "Traceback" not in result.output


# --------------------------------------------------------------------------- #
# rollback — the operator's verb over the fold (FR-094, FR-003)
# --------------------------------------------------------------------------- #


class TestTheRollbackVerb:
	"""``sofact rollback --to N --reason ...`` reads the project as of entry N.

	The fold's behaviour and the service's refusals are measured elsewhere. What is
	under test here is reachability and the exit code: a capability the operator cannot
	invoke is a constant, and a refusal that exits 0 is a refusal nobody notices.
	"""

	def test_rolling_back_hides_the_work_and_says_so(self, home: Path) -> None:
		conversation(home)
		assert RUNNER.invoke(app, ["--home", str(home), "draft"]).exit_code == 0

		result = RUNNER.invoke(
			app,
			["--home", str(home), "rollback", "--to", "1", "--reason", "the draft was wrong"],
		)

		assert result.exit_code == 0, result.output
		assert "rolled back to entry 1" in result.output
		assert "none deleted" in result.output, "the operator must be told the log kept the work"
		assert "the draft was wrong" in result.output, "the reason is echoed back"

	def test_the_log_keeps_what_the_rollback_hid(self, home: Path) -> None:
		"""A rollback that deleted its own evidence would be the one thing it must not be."""
		conversation(home)
		assert RUNNER.invoke(app, ["--home", str(home), "draft"]).exit_code == 0
		before = RUNNER.invoke(app, ["--home", str(home), "ledger"])
		assert "draft.created" in before.output

		assert (
			RUNNER.invoke(
				app, ["--home", str(home), "rollback", "--to", "1", "--reason", "rework"]
			).exit_code
			== 0
		)
		after = RUNNER.invoke(app, ["--home", str(home), "ledger"])

		assert "draft.created" in after.output, "the draft row is still in the log"
		assert "cut.recorded" in after.output
		assert RUNNER.invoke(app, ["--home", str(home), "verify-ledger"]).exit_code == 0

	def test_a_target_in_the_future_is_refused(self, home: Path) -> None:
		conversation(home)
		result = RUNNER.invoke(
			app, ["--home", str(home), "rollback", "--to", "999", "--reason", "typo"]
		)

		assert result.exit_code == 1, result.output
		assert "does not exist" in result.output
		assert "Traceback" not in result.output

	def test_the_reason_is_required(self, home: Path) -> None:
		"""An unexplained gap reads as a bug, so the flag is not optional."""
		conversation(home)
		result = RUNNER.invoke(app, ["--home", str(home), "rollback", "--to", "1"])

		assert result.exit_code != 0
		assert "--reason" in result.output

	def test_status_says_the_project_is_read_under_a_cut(self, home: Path) -> None:
		"""The whole point of recording the cut: the next reader cannot miss it.

		Every other line ``status`` prints — the phase, the readiness, the draft — is
		read under the cut, so a status that stayed silent would present a rolled-back
		project as the current one.
		"""
		conversation(home)
		plain = RUNNER.invoke(app, ["--home", str(home), "status"])
		assert "rolled back" not in plain.output

		assert (
			RUNNER.invoke(
				app, ["--home", str(home), "rollback", "--to", "1", "--reason", "rework"]
			).exit_code
			== 0
		)
		after = RUNNER.invoke(app, ["--home", str(home), "status"])

		assert after.exit_code == 0, after.output
		assert "rolled back to entry 1" in after.output
		assert "rework" in after.output
		assert "the log keeps what it hid" in after.output


# --------------------------------------------------------------------------- #
# the repair loop — the difference between a factory that stops and one that ends
# --------------------------------------------------------------------------- #

REPAIR_ORACLE = "test -f repair-marker.txt"
"""An oracle the first dispatch cannot satisfy and a repair session can.

The synthetic child writes ``repair-marker.txt`` only for a goal phrased as a repair,
so this command separates the two sessions on the artefact itself rather than on an
argument the test passed. The loop's convergence is then a real filesystem fact.
"""


class TestTheRepairVerb:
	"""``sofact repair`` turns a refuted verdict into another session, from the CLI.

	The loop's own behaviour is measured in ``test_service.py``. What is under test
	here is reachability: a capability the operator cannot invoke is a constant, and
	the exit code is the contract — clean means 0, still refuted means non-zero.
	"""

	def _refuted_pipeline(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
	) -> None:
		"""Drive the real CLI to a refuted verdict, the way an operator would."""
		configure(tmp_path, monkeypatch, mode=mode)
		conversation(home)
		contract = RUNNER.invoke(app, ["--home", str(home), "contract", "--command", REPAIR_ORACLE])
		assert contract.exit_code == 0, contract.output
		assert (
			RUNNER.invoke(
				app, ["--home", str(home), "specify", "--approve", *SPECIFY_ARGS]
			).exit_code
			== 0
		)
		assert RUNNER.invoke(app, ["--home", str(home), "decompose", "--approve"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		probed = RUNNER.invoke(app, ["--home", str(home), "probe"])
		assert probed.exit_code == 0, probed.output
		dispatched = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		# Exit 1 has several causes here, and only one of them leaves anything to
		# repair: a model-resolution refusal or an unprobed harness also exits 1. Naming
		# the reason is what makes this fixture a precondition rather than a coincidence.
		assert dispatched.exit_code == 1, dispatched.output
		assert "a step was refuted" in dispatched.output, dispatched.output

	def test_a_refuted_run_is_repaired_and_the_verb_exits_clean(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._refuted_pipeline(home, tmp_path, monkeypatch, "goal-repair")
		result = RUNNER.invoke(app, ["--home", str(home), "repair"])
		assert result.exit_code == 0, result.output
		assert "repaired" in result.output
		assert "satisfied" in result.output, result.output

	def test_a_repair_that_cannot_work_exits_nonzero(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The session runs and leaves the tree alone, so the clause is refuted again.

		``--max-attempts 1`` makes the budget spend in one round, which is the branch
		where the verb has to say "out of attempts" rather than "nothing to repair".
		"""
		self._refuted_pipeline(home, tmp_path, monkeypatch, "goal-repair-never")
		result = RUNNER.invoke(app, ["--home", str(home), "repair", "--max-attempts", "1"])
		assert result.exit_code == 1, result.output
		assert "exhausted" in result.output, result.output
		assert "not a factory that stopped trying" in result.output

	def test_a_clean_contract_repairs_nothing(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A repair run against a clean contract must not invent work."""
		configure(tmp_path, monkeypatch, mode="goal")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"]).exit_code == 0

		result = RUNNER.invoke(app, ["--home", str(home), "repair"])
		assert result.exit_code == 0, result.output
		assert "nothing is refuted" in result.output

	def test_repair_without_a_verdict_says_so(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""No verdict means no diagnosis, and a goal authored from nothing is a guess."""
		configure(tmp_path, monkeypatch, mode="goal")
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0

		result = RUNNER.invoke(app, ["--home", str(home), "repair"])
		assert result.exit_code == 1
		assert "no verdict yet" in result.output
		assert "the diagnosis has to come from the verifier" in result.output

	def test_repair_refuses_an_unprobed_harness(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The same gate as dispatch: a repair is a session and needs the same evidence."""
		self._refuted_pipeline(home, tmp_path, monkeypatch, "goal-repair")
		unprobed = tmp_path / "other.json"
		unprobed.write_text(
			json.dumps({"harnesses": {"ghost": spec_json(base_spec(tmp_path, "goal"))}}),
			encoding="utf-8",
		)
		monkeypatch.setenv("SOFACT_HARNESS_SPECS", str(unprobed))
		result = RUNNER.invoke(app, ["--home", str(home), "repair", "--harness", "ghost"])
		assert result.exit_code == 1
		assert "has never been probed here" in result.output


# --------------------------------------------------------------------------- #
# P7 from the CLI, including the two requirements the specification decides
# --------------------------------------------------------------------------- #


class TestTheIntegrateVerb:
	"""``sofact integrate`` runs P7 and is honest about what the specification left open.

	FR-115 and FR-116 are discharged by the *approved specification*, not by the check
	alone: a project that declared no system model and no criteria still gets a report
	that names both as not implemented. What is under test here is that the two states
	are distinguishable from the CLI — a report that read the same either way would make
	"P7 passed" a claim the operator cannot check.
	"""

	def _dispatched(
		self,
		home: Path,
		tmp_path: Path,
		monkeypatch: pytest.MonkeyPatch,
		*extra_specify: str,
	) -> None:
		"""Drive the real CLI through both gates to a dispatched plan."""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0
		# ``_contract`` already specified and approved; a test that wants criteria adds
		# them in a second proposal rather than re-implementing the helper.
		if extra_specify:
			assert (
				RUNNER.invoke(
					app,
					["--home", str(home), "specify", "--approve", *SPECIFY_ARGS, *extra_specify],
				).exit_code
				== 0
			)
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0
		dispatched = RUNNER.invoke(app, ["--home", str(home), "dispatch", "--all"])
		assert dispatched.exit_code == 0, dispatched.output

	def test_a_specification_with_no_criteria_says_fr_116_is_not_implemented(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The honest default: the check runs, discharges nothing, and says why.

		``_contract`` supplies one entity, so FR-115 *is* discharged here and FR-116 is
		not — which is the distinction under test. A report that named both, or neither,
		would be reporting its own code rather than what the specification declared.
		"""
		self._dispatched(home, tmp_path, monkeypatch)

		result = RUNNER.invoke(app, ["--home", str(home), "integrate"])

		assert result.exit_code == 0, result.output
		assert "model_conformance" in result.output
		assert "system_criteria" in result.output
		assert "not implemented:" in result.output
		named = result.output.split("not implemented: ")[1].split(".")[0]
		assert "FR-116" in named, f"no criteria were declared, so FR-116 is open: {named}"
		assert "FR-115" not in named, f"an entity was declared, so FR-115 discharged: {named}"
		assert "described no system" in result.output
		assert "needs the system model of §6.3 as a type" not in result.output, (
			"the old message said the type did not exist, which is no longer true"
		)
		assert "boundary_contracts" in result.output, "O8 runs and says so (FR-110)"
		assert "FR-110" in named, (
			f"no module declared a surface, so there is no boundary to contract across: {named}"
		)
		assert "before there is a boundary" in result.output, (
			"the requirement is named *and* the reason it is open is given"
		)

	def test_a_declared_criterion_moves_fr_116_from_open_to_checked(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Declaring a criterion changes which *report* FR-116 gets, not just the count.

		Before the declaration the requirement is open — the check ran and discharged
		nothing. After it, the check ran against real verdicts and reported the criterion
		satisfied, so FR-116 leaves ``not_implemented``. The two states are told apart by
		that tuple, which is derived from what the check discharged rather than from a
		list, so nothing here can be made true by editing a constant.
		"""
		self._dispatched(
			home,
			tmp_path,
			monkeypatch,
			"--criterion",
			"The store and the dashboard agree | both are checked against one fixture | 1,2",
		)

		result = RUNNER.invoke(app, ["--home", str(home), "integrate"])

		assert result.exit_code == 0, result.output
		assert "1 system criterion(s) over 2 clause(s); every one satisfied" in result.output
		assert "not implemented:" in result.output
		named = result.output.split("not implemented: ")[1].split(".")[0]
		assert "FR-116" not in named, (
			f"the check ran against verdicts, so FR-116 is closed: {named}"
		)

	def test_a_criterion_over_one_clause_is_refused_with_a_message(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-116's floor reaches the operator as a sentence, not as a traceback."""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0
		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"specify",
				"--criterion",
				"Only one clause | a criterion that is a module's job | 1",
			],
		)

		assert result.exit_code == 1, result.output
		assert "bad option" in result.output
		assert "Traceback" not in result.output

	def test_a_criterion_naming_a_clause_the_contract_does_not_have_is_refused(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0
		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"specify",
				"--criterion",
				"A criterion | checked somehow | 1,99",
			],
		)

		assert result.exit_code == 1, result.output
		assert "the contract has" in result.output
		assert "Traceback" not in result.output

	def test_a_declared_criterion_is_printed_by_the_proposal(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The operator sees what they declared, with its span, before approving it."""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0
		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"specify",
				*SPECIFY_ARGS,
				"--criterion",
				"The store and the dashboard agree | both are checked against one fixture | 1,2",
			],
		)

		assert result.exit_code == 0, result.output
		assert "system-level criteria (FR-116)" in result.output
		assert "over 2 clause(s)" in result.output

	def test_an_interface_reaches_the_proposal_and_the_terminal(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-083 needs a declaration site, and a verb that could not accept one is not it.

		The same reasoning ``--criterion`` carries: a requirement the operator's own
		statement discharges needs a way in, or the gate behind it can never pass while
		still reporting itself as a gate.
		"""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0

		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"specify",
				*SPECIFY_ARGS,
				"--interface",
				"ledger:record(f,entry_id),LIMIT(k):1",
			],
		)

		assert result.exit_code == 0, result.output
		assert "1 interface(s)" in result.output
		assert "ledger (FR-083)" in result.output
		assert "function record(entry_id)" in result.output
		assert "constant LIMIT" in result.output

	def test_an_interface_over_a_clause_that_does_not_exist_is_refused(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The refusal names the arity, because a wrong index is the likely mistake."""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0

		result = RUNNER.invoke(
			app,
			["--home", str(home), "specify", *SPECIFY_ARGS, "--interface", "ledger:record:99"],
		)

		assert result.exit_code == 1
		assert "bad option" in result.output
		assert "the contract has 5 clause(s)" in result.output

	def test_an_interface_member_with_an_unknown_kind_is_refused(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The default is stated rather than implied, so a wrong kind is a refusal, not a guess."""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0

		result = RUNNER.invoke(
			app,
			["--home", str(home), "specify", *SPECIFY_ARGS, "--interface", "ledger:record(x):1"],
		)

		assert result.exit_code == 1
		assert "use f, c or k" in result.output


# --------------------------------------------------------------------------- #
# FR-093: the module's Definition of Done reaches the operator's terminal
# --------------------------------------------------------------------------- #


class TestTheModuleDefinitionOfDone:
	def _proposal(self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Result:
		configure(tmp_path, monkeypatch)
		conversation(home)
		return _proposed(home)

	def test_the_proposal_prints_what_done_means_for_each_module(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-093's criteria are the precondition for P5, so the operator has to see them
		at the gate they are approving — a Definition of Done that only exists in a JSON
		field is not something anyone can check before the build starts."""
		result = self._proposal(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "done when:" in result.output
		assert "the covered clause's oracle passes" in result.output

	def test_the_gate_reports_the_criteria_check(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The check is on the gate the operator reads, not only in the log."""
		result = self._proposal(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "every_module_has_completion_criteria" in result.output
		assert "Definition of Done" in result.output


# --------------------------------------------------------------------------- #
# §1.3's envelope, through the configuration seam (FR-057, NFR-025)
# --------------------------------------------------------------------------- #


class TestTheEnvelopeVerb:
	def _configure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
		path = tmp_path / "envelope.json"
		path.write_text(json.dumps(payload), encoding="utf-8")
		monkeypatch.setenv("SOFACT_ENVELOPE", str(path))

	def test_an_unconfigured_envelope_is_not_the_default_one(self, home: Path) -> None:
		"""NFR-025 makes the envelope configuration and calls it a hypothesis under
		test. Applying §1.3's numbers without anyone adopting them would report actuals
		against a hypothesis nobody chose."""
		result = RUNNER.invoke(app, ["--home", str(home), "envelope"])

		assert result.exit_code == 1, result.output
		assert "no envelope configured" in result.output
		assert "Traceback" not in result.output

	def test_the_defaults_are_printable_on_request(self, home: Path) -> None:
		"""The operator has to be able to see §1.3's own numbers to decide whether to
		adopt them, and asking for them is not the same as having them applied."""
		result = RUNNER.invoke(app, ["--home", str(home), "envelope", "--defaults"])

		assert result.exit_code == 0, result.output
		assert "8-25 modules" in result.output
		assert "3000-15000 LOC" in result.output

	def test_a_configured_envelope_is_printed_with_its_actuals(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure(tmp_path, monkeypatch, {"modules": {"minimum": 1, "maximum": 25}})
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0

		result = RUNNER.invoke(app, ["--home", str(home), "envelope"])

		assert result.exit_code == 0, result.output
		assert "1-25 modules" in result.output
		assert "actuals (NFR-025)" in result.output
		assert "modules: 5 modules (within 1-25 modules)" in result.output

	def test_an_unmeasured_dimension_is_named_rather_than_counted_as_satisfied(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		self._configure(tmp_path, monkeypatch, {"modules": {"minimum": 1, "maximum": 25}})
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0

		result = RUNNER.invoke(app, ["--home", str(home), "envelope"])

		assert "unmeasured" in result.output
		assert "delivered_loc: unmeasured" in result.output

	def test_an_over_scoped_project_exits_non_zero_and_says_which_dimension(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-057: the refusal names the dimension, and the command is not a report that
		succeeds while the project is out of bounds.

		The decomposition is proposed *without* approval, because with a ceiling of two
		modules the approval is refused — which is the next test's subject.
		"""
		self._configure(tmp_path, monkeypatch, {"modules": {"minimum": 1, "maximum": 2}})
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _proposed(home).exit_code == 0

		result = RUNNER.invoke(app, ["--home", str(home), "envelope"])

		assert result.exit_code == 1, result.output
		assert "over the envelope" in result.output
		assert "modules: 5 modules (OUTSIDE 1-2 modules)" in result.output

	def test_a_bad_dimension_name_is_refused_by_the_reader(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A typo that changes nothing and reports success is the failure mode a config
		seam has, so the name is checked rather than ignored."""
		self._configure(tmp_path, monkeypatch, {"moduels": {"maximum": 5}})

		result = RUNNER.invoke(app, ["--home", str(home), "envelope"])

		assert result.exit_code == 1, result.output
		assert "cannot read SOFACT_ENVELOPE" in result.output
		assert "Traceback" not in result.output

	def test_the_p3_gate_refuses_an_over_scoped_decomposition(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The refusal reaches the gate an operator runs, not only the report verb."""
		self._configure(tmp_path, monkeypatch, {"modules": {"minimum": 1, "maximum": 2}})
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _proposed(home).exit_code == 0

		result = RUNNER.invoke(app, ["--home", str(home), "decompose", "--approve"])

		assert result.exit_code == 1, result.output
		assert "within_delivery_envelope" in result.output
		assert "FR-057" in result.output


# --------------------------------------------------------------------------- #
# P8 from the CLI — the report, and the gate a human passes (FR-117 to FR-121)
# --------------------------------------------------------------------------- #


def _a_delivery_root(tmp_path: Path) -> Path:
	"""The delivery root to hand ``deliver``, created empty and left empty.

	Empty on purpose. The factory writes the two artefacts FR-117 names that it owes
	(``sofact.writing``), so a fresh root is the normal case and the one worth driving
	the real CLI through: a helper that pre-wrote ``RUNBOOK.md`` and ``DELIVERY.md``
	would pass whether or not the factory produced them, and producing them is the thing
	under test.
	"""
	root = tmp_path / "delivery"
	root.mkdir()
	return root


def _delivered(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> Result:
	"""Drive the real CLI to a rendered delivery report, through every gate before it."""
	root = _a_delivery_root(tmp_path)
	configure(tmp_path, monkeypatch)
	conversation(home)
	assert _contract(home).exit_code == 0
	assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0
	assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
	return RUNNER.invoke(app, ["--home", str(home), "deliver", "--root", str(root), *extra])


class TestTheDeliverVerb:
	"""``sofact deliver`` renders FR-118's report; ``sofact deploy`` presents FR-119's gate.

	What is under test is that the report's *awkward* statements survive the trip to the
	terminal — the unverified clauses, the artefacts the factory does not produce, the
	sentence that value was not certified — because a presentation adapter is the last
	place a qualification can go missing, and the deploy gate is the last moment anyone
	can refuse.
	"""

	def test_no_contract_yet_is_a_message_not_a_traceback(self, home: Path) -> None:
		"""Every precondition has a sentence. A thin CLI's characteristic failure is a
		traceback where a message belonged."""
		conversation(home)

		result = RUNNER.invoke(app, ["--home", str(home), "deliver"])

		assert result.exit_code == 1, result.output
		assert "no contract yet" in result.output
		assert "Traceback" not in result.output

	def test_no_delivery_root_is_a_message_not_a_traceback(self, home: Path) -> None:
		"""The factory writes the artefacts it owes, so it needs a root to write them
		under. Refusing without one is the honest version of that: a default would put a
		delivery wherever the operator happened to be standing."""
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0

		result = RUNNER.invoke(app, ["--home", str(home), "deliver"])

		assert result.exit_code == 1, result.output
		assert "no delivery root" in result.output
		assert "--root" in result.output
		assert "Traceback" not in result.output

	def test_an_empty_delivery_root_is_filled_by_the_delivery(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The factory writes the two artefacts it owes, so an empty root is the normal
		case rather than a refusal.

		This replaced a test that asserted the opposite — that a root with nothing in it
		fails the artefact check — and the replacement is the stronger claim. The old
		behaviour meant ``sofact deliver`` could not succeed on a fresh project: the
		factory reported its own output as missing, and the only way past it was for a
		human to hand-write the documents the factory claims to produce. What is asserted
		now is that the files exist *and* carry the report's own id, which is what makes
		them the delivery's documents rather than two placeholders that satisfied a
		presence check.
		"""
		configure(tmp_path, monkeypatch)
		conversation(home)
		assert _contract(home).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "probe"]).exit_code == 0
		assert RUNNER.invoke(app, ["--home", str(home), "plan"]).exit_code == 0
		empty = tmp_path / "empty"
		empty.mkdir()

		result = RUNNER.invoke(app, ["--home", str(home), "deliver", "--root", str(empty)])

		assert result.exit_code == 0, result.output
		written = {path.name for path in empty.iterdir()}
		assert written == {"RUNBOOK.md", "DELIVERY.md"}, written
		report_id = result.output.split("delivery report ")[1].split("\n")[0].strip()
		assert report_id in (empty / "DELIVERY.md").read_text(encoding="utf-8")
		assert report_id in (empty / "RUNBOOK.md").read_text(encoding="utf-8")
		assert "delivery_artifacts" in result.output
		assert "exist under the delivery root" in result.output

	def test_the_report_says_the_delivered_surface_was_not_verified(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-120 has two subjects and only one of them is the factory's (ADR-0048).

		The verb prints the factory's *own* surface as built, so a reader who saw only the
		green lines would take "machine-usable" for a property of what they are about to
		ship. The delivered system's surface is checked by nothing, and the screen has to
		say so.

		The assertion names the **check**, not the substring: ``FR-120`` and ``not
		verified`` both appear elsewhere in the output — the maintainability sentence is
		on the same screen — so a substring test here passes with the check deleted, which
		is exactly what the first canary showed.
		"""
		result = _delivered(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "machine_surface_not_verified" in result.output, result.output
		assert "producer obligation" in result.output

	def test_the_report_states_that_value_was_not_certified(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-086's sentence is the one an operator is most tempted to drop, because it
		is the one that makes the report read as less than a guarantee."""
		result = _delivered(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "verified, not value" in result.output
		assert "value hypothesis is declared and untested" in result.output

	def test_the_report_names_the_artefacts_the_factory_does_not_produce(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-117's image and IaC are decisions rather than omissions, and the CLI has to
		print them apart from the missing ones — a single "missing" list would make work
		the factory owes and an open decision one indistinguishable set."""
		result = _delivered(home, tmp_path, monkeypatch)

		assert "decisions SoFact does not take" in result.output
		assert "[you ]" in result.output, "the undecided kinds get their own marker"
		assert "packaging decision" in result.output

	def test_the_artefact_check_is_scoped_to_what_the_factory_owes(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A check over all four FR-117 kinds could never pass, because two of them are
		decisions ADR-0005 and FR-124 leave to the operator. A gate that cannot pass is
		one an operator learns to bypass, and the bypass turns off the part that matters.
		"""
		result = _delivered(home, tmp_path, monkeypatch)

		assert "delivery_artifacts" in result.output
		assert "undecided_artifacts_stated" in result.output
		scoped = result.output.split("delivery_artifacts: ")[1].split("\n")[0]
		assert "artefact(s) FR-117 names that the factory owes exist" in scoped, scoped
		assert "image" not in scoped, "the unproducible kinds are not this check's business"

	def test_the_handover_is_printed_with_what_cannot_be_run(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-121's composition claim is only checkable if the handover reaches the
		operator, and the count of oracles with no command is the part that says whether
		Mode M has anything to run."""
		result = _delivered(home, tmp_path, monkeypatch)

		assert "maintenance handover (FR-121)" in result.output
		assert "inherited oracle(s)" in result.output
		assert "without a command" in result.output
		assert "entry point:" in result.output

	def test_the_debt_is_stated_rather_than_failed(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-118 asks the report to *state* the unverified clauses. Refusing here would
		pay a producer for hiding one, so the check reports and the report still renders.
		"""
		result = _delivered(home, tmp_path, monkeypatch)

		assert "unverified (FR-118)" in result.output
		assert "no verdict was ever rendered" in result.output


class TestTheTopologySeam:
	"""§5.4's topology through the configuration seam (FR-124, FR-042, FR-031).

	The seam is the part a deployment actually sets, and its two failure modes are the
	ones this class covers: a topology nobody declared must report the *degraded* default
	and say that is what happened, and a malformed value must be refused rather than
	silently defaulted — a typo that quietly picks T1 would lower every ceiling in the
	deployment and look exactly like a deployment that never configured anything.
	"""

	def test_an_undeclared_topology_reports_t1_and_says_it_was_not_declared(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-042's own words: the dev instance "must report its degraded ceiling rather
		than silently behaving as if it were T2". Silence is the failure — a deployment
		reporting T1 with no note reads as a choice someone made."""
		result = _delivered(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "topology: T1" in result.output
		assert "no topology was declared" in result.output
		assert "SOFACT_TOPOLOGY" in result.output, "the message must name the knob"

	def test_a_declared_topology_is_reported_without_the_warning(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The other arm, and it is what makes the first a statement about *this*
		deployment rather than a line the CLI always prints."""
		monkeypatch.setenv("SOFACT_TOPOLOGY", "T2")

		result = _delivered(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "topology: T2" in result.output
		assert "no topology was declared" not in result.output
		assert "ceiling modifier 0" in result.output

	def test_a_malformed_topology_is_refused_rather_than_defaulted(
		self, home: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A typo that changes nothing and reports success is the failure mode a config
		seam has, and here it would be worse than usual: T1 is the *degraded* default, so
		an unrecognised value would silently lower every ceiling in the deployment while
		the operator believed they had set the product target.

		The refusal is not scoped to ``deliver``: the topology is read when a service is
		built, so a bad value refuses the *first* verb that builds one. That is the
		stronger behaviour — the deployment is misconfigured, and finding out at the
		delivery rather than at the start would be finding out after the work.
		"""
		monkeypatch.setenv("SOFACT_TOPOLOGY", "T5")

		result = RUNNER.invoke(app, ["--home", str(home), "envelope"])

		assert result.exit_code == 1, result.output
		assert "cannot read SOFACT_TOPOLOGY" in result.output
		assert "T4" in result.output, "the refusal must list what is accepted"
		assert "Traceback" not in result.output

	def test_the_topology_is_case_insensitive_but_not_fuzzy(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""``t2`` is accepted because a shell variable's case is not a decision, and
		``T2 `` is accepted because a trailing newline from a file is not one either."""
		monkeypatch.setenv("SOFACT_TOPOLOGY", " t2 ")

		result = _delivered(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "topology: T2" in result.output

	def test_a_malformed_boundary_is_refused_rather_than_defaulted(
		self, home: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Same discipline as the topology knob, and it matters more here.

		``SOFACT_BOUNDARY`` does not *declare* isolation — it restricts which mechanisms
		the detector may try. A value it cannot parse would otherwise be ignored, the probe
		would run unrestricted, and the deployment would report a measurement its operator
		never asked for. Refusing by name is the only outcome that leaves the two facts
		apart.
		"""
		monkeypatch.setenv("SOFACT_BOUNDARY", "jail")

		result = RUNNER.invoke(app, ["--home", str(home), "envelope"])

		assert result.exit_code == 1, result.output
		assert "cannot read SOFACT_BOUNDARY" in result.output
		assert "seatbelt" in result.output, "the refusal must list what is accepted"
		assert "Traceback" not in result.output

	def test_the_boundary_knob_accepts_a_mechanism_list_case_insensitively(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A restriction to ``seatbelt`` must still deliver, and the delivery must report
		the measurement rather than the restriction — the knob narrows the probe, it never
		stands in for its verdict."""
		monkeypatch.setenv("SOFACT_BOUNDARY", " seatbelt , container ")

		result = _delivered(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "isolation" in result.output

	def test_the_override_flag_is_wired_to_the_gate(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-031's override has to name who accepted it, so the flag takes a value
		rather than being a switch.

		What this asserts is that the flag *reaches* the report — the check is printed
		and the run succeeds. It cannot assert the override's effect, because the
		synthetic contract proposes no L4 module class and so nothing is refused for it
		to override; the semantics are tested against a real L4 fixture in
		``test_delivery.TestTheRefusalReachesTheGate``, and duplicating that here with a
		fixture that cannot reach the case would be a test of the fixture.
		"""
		result = _delivered(home, tmp_path, monkeypatch, "--override-topology", "ada")

		assert result.exit_code == 0, result.output
		assert "topology_refuses_l4_at_a_degraded_deployment" in result.output


class TestTheDeployVerb:
	def test_no_report_yet_is_a_message_not_a_traceback(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "deploy"])

		assert result.exit_code == 1, result.output
		assert "no delivery report yet" in result.output
		assert "Traceback" not in result.output

	def test_presenting_the_gate_shows_the_checks_and_the_value_statement(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-119 makes this a human decision, and a decision needs the evidence in front
		of it. A gate that printed only "pass or fail" would be theatre."""
		delivered = _delivered(home, tmp_path, monkeypatch)
		assert delivered.exit_code == 0, delivered.output
		report_id = delivered.output.split("delivery report ")[1].split("\n")[0].strip()

		result = RUNNER.invoke(app, ["--home", str(home), "deploy", report_id])

		assert result.exit_code == 0, result.output
		assert f"deploy gate for report {report_id}" in result.output
		assert "verified, not value" in result.output
		assert "human decision, not a check" in result.output

	def test_approving_records_the_decision_and_performs_no_deploy(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""§1.5 makes deploy never automatic, so what this verb produces is the evidence
		of a human act — and it has to say so rather than implying a release."""
		delivered = _delivered(home, tmp_path, monkeypatch)
		assert delivered.exit_code == 0, delivered.output
		report_id = delivered.output.split("delivery report ")[1].split("\n")[0].strip()

		result = RUNNER.invoke(
			app,
			["--home", str(home), "deploy", "--approve", report_id, "--by", "operator"],
		)

		assert result.exit_code == 0, result.output
		assert "passed by operator" in result.output
		assert "recorded, not performed" in result.output

	def test_an_unknown_report_is_refused_with_a_message(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		_delivered(home, tmp_path, monkeypatch)

		result = RUNNER.invoke(
			app,
			["--home", str(home), "deploy", "01a00000-0000-7000-8000-000000000000"],
		)

		assert result.exit_code == 1, result.output
		assert "cannot find that report" in result.output
		assert "Traceback" not in result.output


class TestTheGateCostVerb:
	"""FR-160: ``sofact gate --cost`` is what records what a human gate cost.

	The verb is the only place the number can enter the log -- nothing observes a person
	reading -- so what is under test is that it parses a plausible spelling, refuses an
	implausible one with a sentence rather than a traceback, and refuses a cost for a
	gate nobody has passed.
	"""

	def test_a_cost_needs_a_gate_that_was_passed(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "gate", "--cost", "P2:90:0.25"])

		assert result.exit_code == 1, result.output
		assert "cannot record cost" in result.output
		assert "has not been passed" in result.output
		assert "Traceback" not in result.output

	def test_the_recorded_cost_prints_both_numbers_and_the_budget_it_is_measured_against(
		self, home: Path
	) -> None:
		service = FactoryService(home)
		asyncio.run(service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE))
		asyncio.run(service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE))
		asyncio.run(service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE))
		asyncio.run(service.approve_gate(Phase.SPECIFY, by="operator"))

		result = RUNNER.invoke(
			app,
			["--home", str(home), "gate", "--cost", "P2:90:0.25", "--by", "nyimbi"],
		)

		assert result.exit_code == 0, result.output
		assert "90 human-minute(s)" in result.output
		assert "25% of the slice returned to the producer" in result.output
		assert "180-600 is a budget" in result.output

	def test_a_cost_with_no_rework_defaults_to_a_slice_accepted_whole(self, home: Path) -> None:
		"""The common case is a gate that cost time and sent nothing back, and a verb
		that made an operator type ``0`` every time is one they stop using."""
		service = FactoryService(home)
		asyncio.run(service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE))
		asyncio.run(service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE))
		asyncio.run(service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE))
		asyncio.run(service.approve_gate(Phase.SPECIFY, by="operator"))

		result = RUNNER.invoke(app, ["--home", str(home), "gate", "--cost", "P2:45"])

		assert result.exit_code == 0, result.output
		assert "45 human-minute(s)" in result.output
		assert "0% of the slice" in result.output

	def test_a_malformed_cost_names_the_shape_it_wanted(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "gate", "--cost", "P2:ninety"])

		assert result.exit_code == 1, result.output
		assert "not a cost" in result.output
		assert "MINUTES[:REWORK]" in result.output
		assert "Traceback" not in result.output

	def test_the_cost_flag_is_one_of_the_three_exclusive_modes(self, home: Path) -> None:
		result = RUNNER.invoke(
			app, ["--home", str(home), "gate", "--cost", "P2:90", "--approve", "P2"]
		)

		assert result.exit_code == 1, result.output
		assert "exactly one of" in result.output

	def test_the_delivery_report_prints_the_pair_beside_the_envelope(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-160 puts the numbers in the delivery report (§20.2), and the report is the
		last artefact a human reads before the deploy gate: a cost recorded but not
		printed there is a measurement nobody acts on."""
		delivered = _delivered(home, tmp_path, monkeypatch)

		assert delivered.exit_code == 0, delivered.output
		assert "gate cost (FR-160)" in delivered.output
		assert "unmeasured rather than zero" in delivered.output

		# The measured arm, over the same log: P2's gate is passed and its cost
		# recorded, then the report re-rendered. Re-rendering supersedes rather than
		# erases (FR-070), so the earlier report stays readable and this one is current.
		async def record() -> None:
			service = FactoryService(home)
			await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
			await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
			await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE)
			await service.approve_gate(Phase.SPECIFY, by="operator")
			await service.record_gate_cost(
				PhaseGate.SPECIFICATION, human_minutes=90.0, rework_fraction=0.25, by="operator"
			)

		asyncio.run(record())
		# `_delivered` already made the root; re-rendering reuses it rather than
		# re-creating it, because the artefacts FR-117 names are the same two files.
		again = RUNNER.invoke(
			app, ["--home", str(home), "deliver", "--root", str(tmp_path / "delivery")]
		)

		assert again.exit_code == 0, again.output
		assert "specification: 90 human-minute(s), 25% of the slice" in again.output
		assert "total 90 human-minute(s)" in again.output
		assert "mean rework fraction 0.250" in again.output


# --------------------------------------------------------------------------- #
# FR-021-023 — the escape oracle at the operator's surface
# --------------------------------------------------------------------------- #


def _deployed(
	home: Path,
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	*,
	budget: str | None = None,
) -> str:
	"""Drive the real CLI to a *deployed* delivery. Returns the report id.

	``budget`` writes a real ``SOFACT_ESCAPE_BUDGET`` file and points the environment at
	it, because the seam is the thing under test: a test that injected the budgets in
	Python would prove the CLI reads a variable nobody can set.
	"""
	delivered = _delivered(home, tmp_path, monkeypatch)
	assert delivered.exit_code == 0, delivered.output
	report_id = delivered.output.split("delivery report ")[1].split("\n")[0].strip()
	# Deploying is a separate verb (§1.5 makes deploy never automatic), so the helper
	# drives it rather than assuming `deliver` released anything.
	approved = RUNNER.invoke(
		app, ["--home", str(home), "deploy", "--approve", report_id, "--by", "operator"]
	)
	assert approved.exit_code == 0, approved.output
	if budget is not None:
		path = tmp_path / "budget.json"
		path.write_text(budget)
		monkeypatch.setenv("SOFACT_ESCAPE_BUDGET", str(path))
	return report_id


class TestTheEscapeVerb:
	def test_an_escape_with_nothing_deployed_says_so(self, home: Path) -> None:
		"""A precondition with a sentence rather than a traceback, and a non-zero exit so a
		script can gate on it."""
		conversation(home)

		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"escape",
				"--lane",
				"G4",
				"--kind",
				"revert",
				"--defect",
				"it broke",
			],
		)

		assert result.exit_code == 1, result.output
		assert "nothing has been deployed" in result.output
		assert "Traceback" not in result.output

	def test_an_escape_is_recorded_against_the_latest_deploy(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		report_id = _deployed(home, tmp_path, monkeypatch)

		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"escape",
				"--lane",
				"G4",
				"--kind",
				"revert",
				"--defect",
				"the total was wrong",
				"--by",
				"operator",
			],
		)

		assert result.exit_code == 0, result.output
		assert "escape recorded" in result.output
		assert f"against report {report_id}" in result.output
		assert "revert in G4: the total was wrong" in result.output

	def test_a_lane_the_deployment_never_exercised_is_refused_with_a_sentence(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The refusal has to reach the terminal as a message, and exit non-zero: this is
		the API's "hard to get wrong" at the surface an operator actually uses."""
		_deployed(home, tmp_path, monkeypatch)

		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"escape",
				"--lane",
				"G1",
				"--kind",
				"revert",
				"--defect",
				"it broke",
			],
		)

		assert result.exit_code == 1, result.output
		assert "cannot record that escape" in result.output
		assert "exercises no G1 module" in result.output
		assert "Traceback" not in result.output

	def test_an_unknown_kind_is_a_message_not_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""``--kind`` is FR-021's own three words, so a fourth is a spelling mistake rather
		than a value, and a thin CLI's characteristic failure is a traceback here."""
		_deployed(home, tmp_path, monkeypatch)

		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"escape",
				"--lane",
				"G4",
				"--kind",
				"catastrophe",
				"--defect",
				"it broke",
			],
		)

		assert result.exit_code != 0, result.output
		assert "Traceback" not in result.output or "catastrophe" in result.output


class TestTheEscapesVerb:
	def test_no_deployment_claims_nothing_rather_than_reporting_clean(self, home: Path) -> None:
		"""The vacuous pass at the operator's surface: a screen showing "0 escapes" over no
		deployment would report the absence of a measurement as a clean bill of health."""
		conversation(home)

		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 0, result.output
		assert "FR-022 escape oracle" in result.output
		assert "no change has been deployed" in result.output
		assert "not implemented: FR-021, FR-022, FR-023" in result.output

	def test_the_rate_and_the_budget_are_printed_per_lane(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		_deployed(home, tmp_path, monkeypatch, budget='{"G4": {"maximum_rate": 0.5}}')

		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 0, result.output
		assert "G4: 0 escape(s) / 1 deployment(s) = 0.000, budget 0.500" in result.output

	def test_an_over_budget_lane_exits_nonzero_and_names_the_reduction(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-023's reduction at the surface: the operator has to be able to see it, and a
		script has to be able to gate on it."""
		_deployed(home, tmp_path, monkeypatch, budget='{"G4": {"maximum_rate": 0.0}}')
		RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"escape",
				"--lane",
				"G4",
				"--kind",
				"revert",
				"--defect",
				"it broke",
			],
		)

		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 1, result.output
		assert "over budget: ceiling reduced L3 -> L2" in result.output
		assert "FR-023" in result.output

	def test_a_recorded_override_lifts_the_reduction_and_is_attributed(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-023's escape hatch, at the surface: the reduction lifts and the screen names
		the human, because an override with nobody attached is the silent downgrade FR-031
		forbids."""
		_deployed(home, tmp_path, monkeypatch, budget='{"G4": {"maximum_rate": 0.0}}')
		RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"escape",
				"--lane",
				"G4",
				"--kind",
				"revert",
				"--defect",
				"it broke",
			],
		)

		accepted = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"escapes",
				"--override",
				"G4=the duty officer",
				"--reason",
				"the fix ships Friday",
			],
		)
		assert accepted.exit_code == 0, accepted.output
		assert "accepted by the duty officer" in accepted.output

		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 0, "an accepted lane is not a refusal: " + result.output
		assert "over budget, and accepted by the duty officer" in result.output

	def test_the_rate_is_reported_per_autonomy_level_as_well_as_per_lane(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-022 asks for the rate "per lane **and per autonomy level**", and the second
		axis is a report rather than a regrouping: a level whose lanes all escape is the
		level the ladder has not earned. Asserted at the surface because a property nothing
		prints is a measurement the operator cannot read."""
		_deployed(home, tmp_path, monkeypatch, budget='{"G4": {"maximum_rate": 0.5}}')

		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 0, result.output
		assert "by granted ceiling (FR-022)" in result.output
		# The synthetic decomposition spans G4/G5/G7/G8, whose §14 ceilings differ, so the
		# axis is not degenerate here and each level is named.
		for level in ("L3", "L2", "L1"):
			assert f"      {level}: " in result.output, result.output
		assert "ceiling reduced" not in result.output

	def test_an_unreadable_budget_file_is_a_message_not_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The config seam's own failure mode: a malformed file must arrive as a sentence,
		and refusing is the right answer rather than defaulting — NFR-024 forbids inventing
		a target, and a silently-ignored budget file would read as configured."""
		monkeypatch.setenv("SOFACT_ESCAPE_BUDGET", str(tmp_path / "absent.json"))

		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 1, result.output
		assert "cannot read SOFACT_ESCAPE_BUDGET" in result.output
		assert "Traceback" not in result.output


class TestTheOverrideIsAttributedOrRefused:
	def test_an_override_with_nobody_attached_is_refused(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-023's "attributed": `LANE=` with no name is the silent downgrade FR-031
		forbids, so it is a message and a non-zero exit rather than a recorded row."""
		_deployed(home, tmp_path, monkeypatch)

		result = RUNNER.invoke(app, ["--home", str(home), "escapes", "--override", "G4="])

		assert result.exit_code == 1, result.output
		assert "an override is attributed" in result.output
		assert "Traceback" not in result.output

	def test_an_override_with_no_reason_is_refused(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-023's mechanism is that a human may accept a risk the measurement flags; an
		override with no reason records that the risk was taken and not what was
		understood about it."""
		_deployed(home, tmp_path, monkeypatch)

		result = RUNNER.invoke(
			app, ["--home", str(home), "escapes", "--override", "G4=the duty officer"]
		)

		assert result.exit_code == 1, result.output
		assert "an override states why" in result.output
		assert "Traceback" not in result.output

	def test_an_unknown_lane_is_refused(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		_deployed(home, tmp_path, monkeypatch)

		result = RUNNER.invoke(
			app,
			[
				"--home",
				str(home),
				"escapes",
				"--override",
				"G9=someone",
				"--reason",
				"because",
			],
		)

		assert result.exit_code != 0, result.output
		assert "Traceback" not in result.output


class TestTheChangeCostSeam:
	"""FR-159's instrument is configured the way every other deployment declaration is:
	a file named by an environment variable, read at service construction, refused rather
	than defaulted when malformed.

	The verb under test is ``deliver``, because it is the only command that reaches the
	instrument. A reader asserted on its own would prove the file parses; what these check
	is that a deployment's declaration *arrives* at the render — the seam that can be
	severed while every unit test of the reader still passes.
	"""

	def _units(self, tmp_path: Path, payload: str) -> Path:
		path = tmp_path / "units.json"
		path.write_text(payload, encoding="utf-8")
		return path

	def test_a_declared_set_reaches_the_render(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The whole path: the file is named, the units are pinned, the render measures.

		The delivery root is not a repository, so every unit measures as *unmeasured* —
		which is the point. The assertion is that the render carried a report at all: an
		undeclared deployment renders no ``change_cost`` section, and this one must.
		"""
		path = self._units(
			tmp_path,
			'[{"statement": "add a line", "scope": "root",'
			' "base_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
			' "head_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}]',
		)
		monkeypatch.setenv("SOFACT_CHANGE_UNITS", str(path))

		result = _delivered(home, tmp_path, monkeypatch, "--change-cost")

		assert result.exit_code == 0, result.output
		assert "change cost (FR-159, D18)" in result.output
		assert "unmeasured" in result.output, (
			"a unit whose diff cannot be read must be reported as unmeasured, never as a "
			"footprint of zero"
		)

	def test_an_undeclared_deployment_prints_no_section(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""``--change-cost`` with nothing pinned is a report claiming nothing, and the
		absence is stated rather than rendered as a flat line that reads as stable."""
		result = _delivered(home, tmp_path, monkeypatch, "--change-cost")

		assert result.exit_code == 0, result.output
		assert "change cost (FR-159, D18)" in result.output
		assert "no change unit has a footprint" in result.output

	def test_the_instrument_is_off_unless_asked_for(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Reading a footprint launches ``git`` per unit, and the number moves no ceiling
		(D18) — so a plain ``deliver`` pays for nothing it did not ask for."""
		result = _delivered(home, tmp_path, monkeypatch)

		assert result.exit_code == 0, result.output
		assert "change cost (FR-159, D18)" not in result.output

	def test_a_malformed_declaration_is_a_sentence_not_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The config seam's own failure mode. Refusing is the right answer rather than
		defaulting: a silently-ignored declaration would read as configured while pinning
		nothing.

		Asserted on ``status`` rather than on ``deliver``, and that is the honest place:
		the declaration is read when the *service* is constructed, so a malformed file
		stops every verb rather than the one that happens to use the instrument. A
		refusal that only fired at the render would let an operator run a whole pipeline
		against a declaration the factory could not read.
		"""
		path = self._units(tmp_path, '{"statement": "not an array"}')
		monkeypatch.setenv("SOFACT_CHANGE_UNITS", str(path))

		result = RUNNER.invoke(app, ["--home", str(home), "status"])

		assert result.exit_code == 1, result.output
		assert "cannot read SOFACT_CHANGE_UNITS" in result.output
		assert "Traceback" not in result.output

	def test_a_misspelled_field_is_refused_rather_than_ignored(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""A misspelled ``base_commit`` would otherwise load as a unit with no range, which
		measures as *unmeasured* and reads as work that has not landed — a typo reported as
		a fact about the codebase."""
		path = self._units(
			tmp_path, '[{"statement": "one", "scope": "root", "base_commit_sha": "abc"}]'
		)
		monkeypatch.setenv("SOFACT_CHANGE_UNITS", str(path))

		result = RUNNER.invoke(app, ["--home", str(home), "status"])

		assert result.exit_code == 1, result.output
		assert "not a change-unit field" in result.output
		assert "Traceback" not in result.output
