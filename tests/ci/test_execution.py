"""The executor.

Real subprocesses, no mocks: the executor's whole job is to mediate between a shell
and a record, so a fake shell would test the fake. The commands used here (``true``,
``sleep``, ``printf``) are POSIX and present everywhere SoFact claims to run.

The recurring assertion is that the executor *observes and stops*. It records exit
codes and timeouts; it never decides whether the clause held.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sofact.execution import PRODUCER_NAME, OracleNotExecutableError, OracleRunner
from sofact.verification import verify
from sofact.views import Contract, EvidenceKind, OracleClass, OracleDeclaration, VerdictOutcome

MakeOracle = Callable[..., OracleDeclaration]
MakeContract = Callable[..., Contract]


async def test_successful_command_records_its_exit_code(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(("the check passes", make_oracle("true")))
	evidence = await OracleRunner(tmp_path).run(contract.clauses[0])

	assert evidence.kind is EvidenceKind.COMMAND_OUTPUT
	assert evidence.payload["exit_code"] == 0
	assert evidence.payload["timed_out"] is False
	assert evidence.payload["command"] == "true"
	assert evidence.produced_by == PRODUCER_NAME
	assert evidence.content_hash


async def test_failing_command_records_its_exit_code(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(("the check passes", make_oracle("false")))
	evidence = await OracleRunner(tmp_path).run(contract.clauses[0])
	assert evidence.payload["exit_code"] == 1


async def test_stdout_is_captured(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(("it prints", make_oracle("echo hello-sofact")))
	evidence = await OracleRunner(tmp_path).run(contract.clauses[0])
	assert "hello-sofact" in str(evidence.payload["stdout"])


async def test_stderr_is_captured_separately(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""Keeping the streams apart matters: an error message is not evidence of output."""
	contract = make_contract(("it warns", make_oracle("echo oops 1>&2")))
	evidence = await OracleRunner(tmp_path).run(contract.clauses[0])
	assert "oops" in str(evidence.payload["stderr"])
	assert "oops" not in str(evidence.payload["stdout"])


async def test_oracle_runs_inside_the_named_workspace(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""Proved by side effect rather than by reading back a path, since ``pwd``
	inside a shell may report an inherited ``$PWD``."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	contract = make_contract(("it writes", make_oracle("touch marker.txt")))
	await OracleRunner(workspace).run(contract.clauses[0])
	assert (workspace / "marker.txt").exists()


async def test_timeout_is_recorded_and_terminates_the_process(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""A hang is data, not an exception, and it yields INSUFFICIENT downstream."""
	contract = make_contract(("it returns promptly", make_oracle("sleep 30")))
	evidence = await OracleRunner(tmp_path, timeout=0.25).run(contract.clauses[0])

	assert evidence.payload["timed_out"] is True
	assert evidence.payload["exit_code"] is None
	assert verify(contract, [evidence]).outcome is VerdictOutcome.INSUFFICIENT


async def test_output_is_truncated_to_the_cap(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""A chatty oracle must not be able to bloat the ledger."""
	contract = make_contract(("it is brief", make_oracle("yes x | head -c 5000")))
	evidence = await OracleRunner(tmp_path, max_output_bytes=64).run(contract.clauses[0])
	assert len(str(evidence.payload["stdout"])) == 64


async def test_non_executable_oracle_refuses_rather_than_faking(
	tmp_path: Path, make_contract: MakeContract
) -> None:
	"""An intention is not an observation. Refusing is the honest outcome."""
	contract = make_contract(
		(
			"never double-delivers",
			OracleDeclaration(
				oracle_class=OracleClass.PROPERTY,
				description="for every schedule, delivery happens at most once",
			),
		)
	)
	with pytest.raises(OracleNotExecutableError):
		await OracleRunner(tmp_path).run(contract.clauses[0])


async def test_run_all_skips_the_inexecutable_and_runs_the_rest(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	contract = make_contract(
		("the build passes", make_oracle("true")),
		(
			"no PII in logs",
			OracleDeclaration(
				oracle_class=OracleClass.PROPERTY,
				description="for every log line, no email address appears",
			),
		),
	)
	produced = await OracleRunner(tmp_path).run_all(contract)

	assert len(produced) == 1
	assert produced[0].clause_id == contract.clauses[0].id


async def test_identical_observations_hash_identically(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	"""The payload hash is what makes evidence tamper-evident in the ledger, so it
	must depend on the observation and not on when it happened."""
	contract = make_contract(("it prints", make_oracle("echo stable")))
	runner = OracleRunner(tmp_path)
	first = await runner.run(contract.clauses[0])
	second = await runner.run(contract.clauses[0])

	assert first.id != second.id
	assert first.content_hash == second.content_hash


async def test_changing_the_command_changes_the_hash(
	tmp_path: Path, make_contract: MakeContract, make_oracle: MakeOracle
) -> None:
	one = make_contract(("it prints", make_oracle("echo a")))
	two = make_contract(("it prints", make_oracle("echo b")))
	runner = OracleRunner(tmp_path)
	assert (await runner.run(one.clauses[0])).content_hash != (
		await runner.run(two.clauses[0])
	).content_hash
