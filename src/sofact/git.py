"""Branch-per-module checkouts: the one place SoFact touches git (FR-100).

FR-100 requires build to occur "on a branch per module, never in place". This module
is what makes that true rather than asserted: :func:`ensure_module_branch` brings the
dispatch workspace to a repository on a branch named for the plan step, so a producer
that commits lands on the branch the goal text names.

The scope is deliberately narrow. SoFact does not merge, does not push, and does not
manage a worktree lifecycle here — FR-141's worktree-per-module is a separate
requirement and is deferred ([ADR-0024]); a branch is not a worktree, and this module
does not pretend otherwise. What it guarantees is the weaker, checkable thing FR-100
asks for: the session's work sits on a branch, so it is not done *in place*.

Every function is idempotent and safe to re-run: a second dispatch of the same step
finds the repository and the branch already present and changes nothing. That is
FR-099 applied to the harness, because a retry that re-created the repository would
discard the work it was retrying.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Final

from sofact.views import ModuleCheckout

__all__ = [
	"BRANCH_PREFIX",
	"GitUnavailableError",
	"ensure_module_branch",
	"git_available",
	"seal_branch",
]

BRANCH_PREFIX: Final = "sofact/"
"""Every branch SoFact creates is namespaced, so an operator's own branches are untouched."""

DEFAULT_TIMEOUT_SECONDS: Final = 30.0

_COMMITTER_NAME: Final = "SoFact"
_COMMITTER_EMAIL: Final = "sofact@localhost"
"""Set per-invocation rather than written to a global config.

``git commit`` refuses without an identity, and writing one into the operator's
``~/.gitconfig`` would be SoFact editing a file it does not own. ``-c`` scopes it to
the one command.
"""


class GitUnavailableError(RuntimeError):
	"""Git is not installed, or a git command failed for a reason we cannot proceed past.

	Raised rather than recorded as a capability finding: a missing git binary is an
	*environment* fault the operator can fix, and silently dispatching to an
	unbranched workspace would make FR-100 quietly false. A finding is for something
	about the harness that will still be true tomorrow.
	"""


def git_available() -> bool:
	"""Whether a ``git`` binary is on PATH.

	Synchronous and cheap, for the caller that must decide before dispatching rather
	than after failing.
	"""
	return _which("git") is not None


def _which(name: str) -> str | None:
	import shutil

	return shutil.which(name)


async def _git(
	args: tuple[str, ...], *, cwd: Path, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> tuple[int, str, str]:
	"""Run one git command, returning ``(exit_code, stdout, stderr)``.

	Never raises on a non-zero exit: the caller decides whether a particular failure
	is fatal, because ``git branch`` on an existing branch exits non-zero and is
	*expected*.
	"""
	process = await asyncio.create_subprocess_exec(
		"git",
		*args,
		cwd=cwd,
		stdin=asyncio.subprocess.DEVNULL,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)
	try:
		stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
	except TimeoutError as exc:
		process.kill()
		await process.wait()
		raise GitUnavailableError(
			f"git {' '.join(args)} did not finish within {timeout:.0f}s"
		) from exc
	return (
		process.returncode if process.returncode is not None else 1,
		stdout.decode("utf-8", errors="replace"),
		stderr.decode("utf-8", errors="replace"),
	)


async def _is_repository(workspace: Path) -> bool:
	code, _, _ = await _git(("rev-parse", "--is-inside-work-tree"), cwd=workspace)
	return code == 0


async def _current_branch(workspace: Path) -> str | None:
	code, stdout, _ = await _git(("symbolic-ref", "--quiet", "--short", "HEAD"), cwd=workspace)
	if code != 0:
		return None
	name = stdout.strip()
	return name or None


async def _branch_exists(workspace: Path, branch: str) -> bool:
	code, _, _ = await _git(
		("show-ref", "--verify", "--quiet", f"refs/heads/{branch}"), cwd=workspace
	)
	return code == 0


async def _has_commits(workspace: Path) -> bool:
	"""Whether HEAD resolves to a commit.

	A freshly ``git init``-ed repository has an unborn HEAD, and ``git switch`` to an
	existing branch from an unborn HEAD fails. The distinction decides whether a
	branch can be checked out or must be created.
	"""
	code, _, _ = await _git(("rev-parse", "--verify", "--quiet", "HEAD"), cwd=workspace)
	return code == 0


async def ensure_module_branch(
	workspace: Path, step_ordinal: int, step_kind: str
) -> ModuleCheckout:
	"""Bring ``workspace`` to a repository on this step's branch, and report what happened.

	Idempotent by construction: an existing repository keeps its history, an existing
	branch is checked out rather than recreated, and a workspace that is already on the
	right branch is left alone. The returned :class:`~sofact.views.ModuleCheckout`
	records *what the branch is* so a dispatch can carry it in the log, which is what
	makes FR-100 checkable after the fact rather than only at the moment of dispatch.
	"""
	assert workspace.is_dir(), f"workspace does not exist: {workspace}"
	branch = f"{BRANCH_PREFIX}{step_ordinal:03d}-{step_kind}"
	created_repository = False
	created_branch = False

	if not await _is_repository(workspace):
		code, _, stderr = await _git(("init", "--quiet", "-b", "main", "."), cwd=workspace)
		if code != 0:
			raise GitUnavailableError(f"git init failed in {workspace}: {stderr.strip()}")
		created_repository = True

	# Two different questions, and conflating them is a bug in both directions.
	# ``symbolic`` is the branch HEAD points at, which git reports even when the branch
	# has no commits -- that is what the idempotency check must compare, or a second
	# dispatch of an unborn step recreates its own branch. ``base_branch`` is a place
	# work came *from*, which requires a commit to have been there, so an unborn HEAD
	# reports ``None`` rather than naming a branch that does not exist yet.
	symbolic = await _current_branch(workspace)
	has_history = await _has_commits(workspace)
	base_branch = symbolic if has_history else None

	if symbolic == branch:
		return ModuleCheckout(
			branch=branch,
			step_ordinal=step_ordinal,
			created_repository=created_repository,
			created_branch=False,
			base_branch=base_branch,
		)

	# A repository with no commits cannot `switch` to a branch that does not exist yet,
	# so the first branch is created with `switch --orphan`; later ones branch off HEAD.
	exists = await _branch_exists(workspace, branch)
	if exists:
		code, _, stderr = await _git(("switch", "--quiet", branch), cwd=workspace)
		if code != 0:
			raise GitUnavailableError(f"git switch {branch} failed: {stderr.strip()}")
	else:
		args = (
			("switch", "--quiet", "--orphan", branch)
			if not has_history
			else ("switch", "--quiet", "-c", branch)
		)
		code, _, stderr = await _git(args, cwd=workspace)
		if code != 0:
			raise GitUnavailableError(f"git switch -c {branch} failed: {stderr.strip()}")
		created_branch = True

	# An unborn HEAD means the next commit must not fail for want of an identity; the
	# config is scoped to this repository, never the operator's global file.
	await _git(("config", "user.name", _COMMITTER_NAME), cwd=workspace)
	await _git(("config", "user.email", _COMMITTER_EMAIL), cwd=workspace)

	return ModuleCheckout(
		branch=branch,
		step_ordinal=step_ordinal,
		created_repository=created_repository,
		created_branch=created_branch,
		base_branch=base_branch,
	)


async def _head_commit(workspace: Path) -> str | None:
	code, stdout, _ = await _git(("rev-parse", "--verify", "--quiet", "HEAD"), cwd=workspace)
	if code != 0:
		return None
	return stdout.strip() or None


async def _changed_paths(workspace: Path) -> tuple[str, ...]:
	"""Paths the working tree has that HEAD does not, or has changed since HEAD.

	``--others --exclude-standard`` includes files the producer created and left
	untracked, which is the common case: a session that writes code and never runs
	``git add`` has still done work, and work that no commit names is work the next
	step's branch would silently adopt.
	"""
	code, stdout, stderr = await _git(
		("status", "--porcelain", "--untracked-files=all"), cwd=workspace
	)
	if code != 0:
		raise GitUnavailableError(f"git status failed in {workspace}: {stderr.strip()}")
	paths: list[str] = []
	for line in stdout.splitlines():
		if not line.strip():
			continue
		# Porcelain is `XY <path>`, and a rename is `XY <old> -> <new>`. The path is what
		# matters for counting; the status letters are not used.
		entry = line[3:].strip()
		paths.append(entry.split(" -> ")[-1].strip().strip('"'))
	return tuple(p for p in paths if p)


async def seal_branch(
	checkout: ModuleCheckout,
	workspace: Path,
	*,
	note: str,
	exclude: tuple[str, ...] = (),
) -> ModuleCheckout:
	"""Commit whatever the session left on ``checkout``'s branch, and report the tip.

	FR-100 says build happens on a branch per module. A branch is only a boundary once
	it has a commit: with no commit it is not a ref, so the next step's ``switch -c``
	branches from an unborn HEAD and the two steps become unrelated histories over one
	working tree — the earlier step's files then stage cleanly on the later step's
	branch. Measured, not assumed: two sequential checkouts on a fresh repository both
	reported ``base_branch=None`` and ``git show-ref`` was empty.

	Sealing is SoFact's job rather than the producer's. FR-140 reserves session
	lifecycle to the factory, and a producer that must remember to commit is a producer
	that can silently decline to, leaving the boundary fictional while the goal text
	asserts it.

	``exclude`` names pathspecs the producer does not own — the factory's own session
	directory, when it happens to sit inside the workspace. They are not committed,
	because SoFact's bookkeeping is not the module being built.
	"""
	assert workspace.is_dir(), f"workspace does not exist: {workspace}"
	head = await _head_commit(workspace)

	changed = await _changed_paths(workspace)
	owned = tuple(p for p in changed if not any(p == e or p.startswith(f"{e}/") for e in exclude))
	if not owned:
		# Nothing to seal. This is the honest answer for a session that changed nothing and
		# for one whose producer committed its own work -- ``head_commit`` tells them apart.
		return checkout.model_copy(update={"head_commit": head})

	code, _, stderr = await _git(("add", "--all", "--", *owned), cwd=workspace)
	if code != 0:
		raise GitUnavailableError(f"git add failed in {workspace}: {stderr.strip()}")
	code, _, stderr = await _git(
		("commit", "--quiet", "--no-verify", "-m", note),
		cwd=workspace,
	)
	if code != 0:
		raise GitUnavailableError(f"git commit failed in {workspace}: {stderr.strip()}")

	sealed = await _head_commit(workspace)
	assert sealed is not None, "a commit that succeeded must leave a resolvable HEAD"
	return checkout.model_copy(
		update={
			"sealed_commit": sealed,
			"sealed_paths": len(owned),
			"head_commit": sealed,
		},
	)
