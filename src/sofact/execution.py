"""The executor: runs oracles and records what happened.

This is the *producer* side. It observes and never concludes. Everything it returns
is an :class:`~sofact.views.Evidence`, a type with no verdict field, so this module
is structurally incapable of deciding whether its own command succeeded.
:mod:`sofact.verification` must never import it; the dependency runs one way only.

Threat model, stated plainly: ``command_hint`` is executed through a shell, because
oracle commands are operator-authored and routinely need pipelines and globs. SoFact
therefore does not pretend to sandbox them. It runs them inside an explicit workspace,
under a timeout, and records the blast radius as a fact rather than implying a
boundary it does not enforce — the spec's D9 resolution (no container runtime).

A timeout is recorded, not raised, and it yields ``INSUFFICIENT`` rather than
``VIOLATED``: a hung instrument tells you nothing about the property, and an
unrun oracle must never be laundered into a pass. Because ``INSUFFICIENT`` grants no
autonomy either, hanging buys a producer nothing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sofact.views import Clause, Contract, Evidence, EvidenceKind

__all__ = ["PRODUCER_NAME", "OracleNotExecutableError", "OracleRunner"]

PRODUCER_NAME = "sofact.oracle_runner"
"""Recorded on every observation, so evidence can be attributed in the log."""

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_OUTPUT_BYTES = 65_536


class OracleNotExecutableError(ValueError):
	"""Raised when asked to run an oracle that names no command."""


class OracleRunner:
	"""Runs a contract's executable oracles inside one workspace."""

	def __init__(
		self,
		workspace: Path,
		*,
		timeout: float = DEFAULT_TIMEOUT_SECONDS,
		max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
	) -> None:
		assert timeout > 0, f"timeout must be positive, got {timeout}"
		assert max_output_bytes > 0, f"max_output_bytes must be positive, got {max_output_bytes}"
		self.workspace = Path(workspace)
		self.timeout = timeout
		self.max_output_bytes = max_output_bytes

	def __repr__(self) -> str:
		return f"OracleRunner(workspace={self.workspace}, timeout={self.timeout})"

	async def run(self, clause: Clause) -> Evidence:
		"""Execute one clause's oracle and record the observation.

		Raises :class:`OracleNotExecutableError` if the clause names no command — a
		clause that cannot be run is a contract defect, and silently returning
		something would hide it.
		"""
		command = clause.oracle.command_hint
		if command is None:
			raise OracleNotExecutableError(
				f"clause {clause.id} declares a {clause.oracle.oracle_class.value} oracle "
				"but names no command, so there is nothing to run",
			)
		assert self.workspace.is_dir(), f"workspace does not exist: {self.workspace}"

		process = await asyncio.create_subprocess_shell(
			command,
			cwd=self.workspace,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)

		timed_out = False
		try:
			stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
		except TimeoutError:
			timed_out = True
			process.kill()
			await process.wait()
			stdout, stderr = b"", b""

		payload: dict[str, object] = {
			"command": command,
			"exit_code": None if timed_out else process.returncode,
			"timed_out": timed_out,
			"stdout": stdout.decode("utf-8", errors="replace")[: self.max_output_bytes],
			"stderr": stderr.decode("utf-8", errors="replace")[: self.max_output_bytes],
		}
		evidence = Evidence.record(
			clause_id=clause.id,
			kind=EvidenceKind.COMMAND_OUTPUT,
			produced_by=PRODUCER_NAME,
			payload=payload,
		)
		assert evidence.content_hash, "recorded evidence must carry a payload hash"
		return evidence

	async def run_all(self, contract: Contract) -> tuple[Evidence, ...]:
		"""Run every executable clause, in contract order.

		Non-executable clauses are skipped rather than faked; the caller is expected
		to report them, and :func:`sofact.contract.ground_truth_debt` measures them.
		"""
		results: list[Evidence] = []
		for clause in contract.clauses:
			if not clause.oracle.is_executable:
				continue
			results.append(await self.run(clause))
		return tuple(results)
