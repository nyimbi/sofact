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
import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Final

from sofact.boundary import TEMP_DIRNAME, boundary_env, wrap_argv
from sofact.git import WORKTREE_DIRNAME
from sofact.views import (
	Clause,
	Contract,
	DeploymentBoundary,
	Evidence,
	EvidenceKind,
	content_hash,
)

__all__ = [
	"DEFAULT_DIGEST_EXCLUDES",
	"PRODUCER_NAME",
	"OracleNotExecutableError",
	"OracleRunner",
	"digest_tree",
]

PRODUCER_NAME = "sofact.oracle_runner"
"""Recorded on every observation, so evidence can be attributed in the log."""

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_OUTPUT_BYTES = 65_536

DEFAULT_DIGEST_EXCLUDES: Final = (
	".git",
	".hg",
	".svn",
	".venv",
	".pytest_cache",
	".ruff_cache",
	".mypy_cache",
	".sofact",
	TEMP_DIRNAME,
	"__pycache__",
	"node_modules",
	"build",
	"dist",
	"*.egg-info",
	WORKTREE_DIRNAME,
)
"""Names a digest of the artefact ignores, at any depth.

VCS metadata, interpreter caches, dependency installs and build outputs are not the
change under test: a producer that runs its own test suite will populate ``__pycache__``
as a side effect, and a digest that moved because of it would invalidate a verdict the
oracles would have reproduced exactly. Glob patterns (``*.egg-info``) match one path
component; the rest match whole component names.

``.git`` is here for that reason and one stronger one: a session's work is *sealed* into
a commit when it ends (FR-100), so the repository's own bytes change after every session
whether or not the artefact did. Digesting them would make FR-006's cache key move on
every dispatch and no verdict would ever be reused.

``WORKTREE_DIRNAME`` is here because a concurrent wave's sibling checkouts live inside
the workspace (FR-141): each holds a *copy* of the modules built so far, so folding them
in would key a verdict to another step's files and make two sessions of one wave look
like one change.
"""


def digest_tree(root: Path, *, excludes: tuple[str, ...] = DEFAULT_DIGEST_EXCLUDES) -> str:
	"""Content hash of every regular file under ``root`` that the excludes let through.

	FR-006's cache key needs a content hash of **the change**, and the change is the
	artefact the session left in its workspace. The digest is deliberately not a git
	index read: a workspace need not be a repository, and a producer able to write its
	own index would be able to write its own cache key.

	Order-independent by construction: the fold runs over paths sorted canonically, so
	two trees holding identical content produce identical digests however they were
	created. Symlinks are skipped rather than followed — a link aimed outside the tree
	would otherwise fold bytes no session wrote into the key, and give a producer a
	route to freeze its own verdict.

	Raises :class:`AssertionError` when ``root`` is not a directory: digesting a missing
	tree must fail loudly, because a caller that cached over an absent artefact would
	key a verdict to nothing.
	"""
	assert root.is_dir(), f"cannot digest a tree that does not exist: {root}"
	globs = tuple(pattern for pattern in excludes if any(c in pattern for c in "*?[]"))
	names = frozenset(pattern for pattern in excludes if pattern not in globs)

	kept: list[tuple[str, str]] = []
	for path in sorted(root.rglob("*")):
		if path.is_symlink() or not path.is_file():
			continue
		relative = path.relative_to(root)
		if any(part in names for part in relative.parts):
			continue
		if any(fnmatch.fnmatch(part, pattern) for part in relative.parts for pattern in globs):
			continue
		kept.append((relative.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
	return content_hash(kept)


class OracleNotExecutableError(ValueError):
	"""Raised when asked to run an oracle that names no command."""


class OracleRunner:
	"""Runs a contract's executable oracles inside one workspace.

	``run_id`` is stamped on every observation this runner produces, so that a later
	attempt can be told apart from an earlier one. Identity is injected rather than
	generated here: a runner that invented its own id would make two runners
	incomparable without ever saying so.
	"""

	def __init__(
		self,
		workspace: Path,
		*,
		timeout: float = DEFAULT_TIMEOUT_SECONDS,
		max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
		run_id: str | None = None,
		boundary: DeploymentBoundary | None = None,
	) -> None:
		assert timeout > 0, f"timeout must be positive, got {timeout}"
		assert max_output_bytes > 0, f"max_output_bytes must be positive, got {max_output_bytes}"
		assert run_id is None or run_id, "a run id, when given, must name a run"
		self.workspace = Path(workspace)
		self.timeout = timeout
		self.max_output_bytes = max_output_bytes
		self.run_id = run_id
		# FR-019: the isolation measured for this runner's host, applied to every command
		# it runs. An oracle that executed outside the boundary its dispatch ran inside
		# would judge a producer's work under conditions the producer never had.
		self.boundary = boundary

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

		# FR-019: the command runs inside the boundary measured for this host, or beside
		# it with that fact already recorded on the delivery. `create_subprocess_exec` on
		# an explicit `/bin/sh -c` rather than `create_subprocess_shell`, because the
		# wrapper has to be able to put a mechanism in front of the shell: a boundary that
		# could only wrap the command *string* could not wrap the process at all.
		process = await asyncio.create_subprocess_exec(
			*wrap_argv(("/bin/sh", "-c", command), self.boundary, self.workspace),
			cwd=self.workspace,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
			env={**os.environ, **boundary_env(self.boundary, self.workspace)},
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
			run_id=self.run_id,
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
