"""Branch-per-module checkouts (FR-100).

These run real git against a real temporary directory. That is the only way to test
this module: a mocked git would assert that SoFact calls the commands its author
believed were correct, which is exactly the belief FR-100 exists to check.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sofact.git import BRANCH_PREFIX, GitUnavailableError, ensure_module_branch, git_available

pytestmark = pytest.mark.skipif(not git_available(), reason="git is not installed")


async def run_git(workspace: Path, *args: str) -> str:
	"""Run git the way the module does, and return its stdout.

	``asyncio`` rather than ``subprocess.run`` so the test drives the same event loop
	the code under test uses; a blocking call here would also deadlock the concurrency
	test below, which is the one place the difference would show up as a hang rather
	than a failure.
	"""
	process = await asyncio.create_subprocess_exec(
		"git",
		*args,
		cwd=workspace,
		stdin=asyncio.subprocess.DEVNULL,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)
	stdout, stderr = await process.communicate()
	assert process.returncode == 0, f"git {' '.join(args)} failed: {stderr.decode()}"
	return stdout.decode("utf-8", errors="replace")


async def branch_of(workspace: Path) -> str:
	"""The workspace's current branch, read the way git itself would report it."""
	return (await run_git(workspace, "symbolic-ref", "--quiet", "--short", "HEAD")).strip()


async def test_a_bare_directory_becomes_a_repository_on_a_named_branch(tmp_path: Path) -> None:
	"""The whole point: a workspace with no repository does not stay that way."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	assert not (workspace / ".git").exists()

	checkout = await ensure_module_branch(workspace, 0, "bootstrap")

	assert (workspace / ".git").is_dir(), "git init did not run"
	assert checkout.created_repository is True
	assert checkout.created_branch is True
	assert checkout.branch == f"{BRANCH_PREFIX}000-bootstrap"
	assert await branch_of(workspace) == checkout.branch, (
		"the workspace is not on the branch it reports"
	)


async def test_the_branch_is_not_in_place(tmp_path: Path) -> None:
	"""FR-100's actual requirement: the branch is not the default one."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_branch(workspace, 3, "operation")

	assert checkout.branch != "main", "building on main is building in place"
	assert await branch_of(workspace) != "main"


async def test_the_ordinal_and_kind_distinguish_two_steps(tmp_path: Path) -> None:
	"""Two steps of one plan must not share a branch, or FR-100 is decorative."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	first = await ensure_module_branch(workspace, 0, "bootstrap")
	second = await ensure_module_branch(workspace, 1, "interfaces")

	assert first.branch != second.branch
	assert await branch_of(workspace) == second.branch, "the switch did not take effect"
	assert second.created_branch is True


async def test_re_running_the_same_step_is_idempotent(tmp_path: Path) -> None:
	"""FR-099 for the harness: a retry must not re-create what it is retrying."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	first = await ensure_module_branch(workspace, 2, "invariant")
	second = await ensure_module_branch(workspace, 2, "invariant")

	assert first.branch == second.branch
	assert second.created_repository is False, "a second dispatch re-initialised the repository"
	assert second.created_branch is False, "a second dispatch recreated the branch"


async def test_an_existing_repository_keeps_its_history(tmp_path: Path) -> None:
	"""SoFact must not discard work that is already there."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	await run_git(workspace, "init", "-q", "-b", "main", ".")
	await run_git(workspace, "config", "user.email", "t@t")
	await run_git(workspace, "config", "user.name", "t")
	(workspace / "existing.txt").write_text("prior work", encoding="utf-8")
	await run_git(workspace, "add", "existing.txt")
	await run_git(workspace, "commit", "-qm", "prior")

	checkout = await ensure_module_branch(workspace, 0, "bootstrap")

	assert checkout.created_repository is False
	assert checkout.base_branch == "main"
	assert (workspace / "existing.txt").read_text(encoding="utf-8") == "prior work"
	assert await branch_of(workspace) == checkout.branch


async def test_an_unborn_head_is_not_an_error(tmp_path: Path) -> None:
	"""A fresh repo has no commits, so there is no branch to have come from."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_branch(workspace, 0, "bootstrap")

	assert checkout.base_branch is None, "a fresh repository has no base branch to report"


async def test_a_missing_workspace_is_refused(tmp_path: Path) -> None:
	"""Silently creating it would put a repository somewhere nobody asked for."""
	with pytest.raises(AssertionError, match="does not exist"):
		await ensure_module_branch(tmp_path / "absent", 0, "bootstrap")


async def test_two_concurrent_checkouts_do_not_corrupt_each_other(tmp_path: Path) -> None:
	"""Concurrency is FR-141's subject, but the branch call must at least not race.

	Two different workspaces, because two sessions on one workspace is precisely what
	FR-141 forbids and this module does not claim to solve.
	"""
	left, right = tmp_path / "left", tmp_path / "right"
	left.mkdir()
	right.mkdir()

	a, b = await asyncio.gather(
		ensure_module_branch(left, 0, "bootstrap"),
		ensure_module_branch(right, 0, "bootstrap"),
	)

	assert a.branch == b.branch, "same step, same branch name"
	assert await branch_of(left) == a.branch
	assert await branch_of(right) == b.branch


async def test_git_unavailable_error_is_a_runtime_error() -> None:
	"""The failure type is catchable as a plain RuntimeError, not a bespoke base."""
	assert issubclass(GitUnavailableError, RuntimeError)
