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

from sofact.execution import (
	PRODUCER_NAME,
	OracleNotExecutableError,
	OracleRunner,
	digest_tree,
)
from sofact.verification import verify
from sofact.views import (
	Contract,
	EvidenceKind,
	OracleClass,
	OracleDeclaration,
	VerdictOutcome,
	content_hash,
)

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


# --------------------------------------------------------------------------- #
# the artefact digest (FR-006's key)
# --------------------------------------------------------------------------- #


class TestDigestTree:
	"""FR-006's cache key needs a content hash of *the change*, and the change is the
	tree the session left behind.

	Every property here is about the two ways a digest can lie: naming a file the
	producer did not write (``__pycache__`` a test run left behind), and reading a file
	the producer pointed a link at.
	"""

	def test_two_identical_trees_digest_the_same_however_they_were_created(
		self, tmp_path: Path
	) -> None:
		"""The fold is over canonically sorted paths, so creation order is invisible."""
		first = tmp_path / "first"
		second = tmp_path / "second"
		for root, order in ((first, ("a.txt", "sub/b.txt")), (second, ("sub/b.txt", "a.txt"))):
			root.mkdir(parents=True, exist_ok=True)
			(root / "sub").mkdir(exist_ok=True)
			for name in order:
				(root / name).write_text("content", encoding="utf-8")

		assert digest_tree(first) == digest_tree(second)

	def test_an_unchanged_tree_digests_the_same_twice(self, tmp_path: Path) -> None:
		(tmp_path / "keep.txt").write_text("same bytes", encoding="utf-8")
		assert digest_tree(tmp_path) == digest_tree(tmp_path)

	def test_changing_a_file_changes_the_digest(self, tmp_path: Path) -> None:
		target = tmp_path / "keep.txt"
		target.write_text("before", encoding="utf-8")
		before = digest_tree(tmp_path)
		target.write_text("after", encoding="utf-8")

		assert digest_tree(tmp_path) != before

	def test_a_new_file_changes_the_digest(self, tmp_path: Path) -> None:
		before = digest_tree(tmp_path)
		(tmp_path / "added.txt").write_text("new", encoding="utf-8")

		assert digest_tree(tmp_path) != before

	def test_caches_and_metadata_are_not_the_change(self, tmp_path: Path) -> None:
		"""A producer running its own suite populates caches; the digest must not move."""
		(tmp_path / "code.py").write_text("x = 1", encoding="utf-8")
		clean = digest_tree(tmp_path)

		junk = tmp_path / "__pycache__" / "code.cpython-313.pyc"
		junk.parent.mkdir()
		junk.write_bytes(b"bytecode")
		(tmp_path / ".git" / "objects").mkdir(parents=True)
		(tmp_path / ".git" / "objects" / "ab").write_bytes(b"objects")
		(tmp_path / ".ruff_cache").mkdir()
		(tmp_path / ".ruff_cache" / "results").write_text("{}", encoding="utf-8")
		egg = tmp_path / "wordcount-0.1.egg-info" / "PKG-INFO"
		egg.parent.mkdir()
		egg.write_text("Metadata-Version: 2.1", encoding="utf-8")

		assert digest_tree(tmp_path) == clean

	def test_a_symlink_is_skipped_not_followed(self, tmp_path: Path) -> None:
		"""A link aimed outside the tree must not fold bytes no session wrote into the key."""
		outside = tmp_path.parent / "digest-outside.txt"
		outside.write_text("not written by any session", encoding="utf-8")
		(tmp_path / "keep.txt").write_text("inside", encoding="utf-8")
		clean = digest_tree(tmp_path)
		(tmp_path / "link.txt").symlink_to(outside)

		assert digest_tree(tmp_path) == clean
		outside.unlink(missing_ok=True)

	def test_an_empty_tree_digests_the_empty_fold(self, tmp_path: Path) -> None:
		assert digest_tree(tmp_path) == content_hash([])

	def test_a_missing_directory_fails_loudly(self, tmp_path: Path) -> None:
		with pytest.raises(AssertionError, match="does not exist"):
			digest_tree(tmp_path / "nowhere")

	def test_the_excludes_are_overridable(self, tmp_path: Path) -> None:
		(tmp_path / "code.py").write_text("x = 1", encoding="utf-8")
		cache = tmp_path / "__pycache__" / "code.cpython-313.pyc"
		cache.parent.mkdir()
		cache.write_bytes(b"bytecode")

		assert digest_tree(tmp_path) != digest_tree(tmp_path, excludes=())
