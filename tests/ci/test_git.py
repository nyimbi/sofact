"""Branch-per-module checkouts (FR-100).

These run real git against a real temporary directory. That is the only way to test
this module: a mocked git would assert that SoFact calls the commands its author
believed were correct, which is exactly the belief FR-100 exists to check.
"""

from __future__ import annotations

import asyncio
from itertools import pairwise
from pathlib import Path

import pytest

from sofact.git import (
	BRANCH_PREFIX,
	GitUnavailableError,
	ensure_module_branch,
	ensure_module_worktree,
	git_available,
	integrate_worktree,
	seal_branch,
)

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


async def refs_of(workspace: Path) -> str:
	"""Every ref, or the empty string when there are none.

	``git show-ref`` exits 1 on a repository with no refs — which is the *normal* state
	of an unsealed branch, and the exact thing one of these tests asserts. ``run_git``
	would turn that expected answer into a test error, so the expected-non-zero case
	gets its own helper rather than a weakened assertion in the shared one.
	"""
	process = await asyncio.create_subprocess_exec(
		"git",
		"show-ref",
		cwd=workspace,
		stdin=asyncio.subprocess.DEVNULL,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)
	stdout, stderr = await process.communicate()
	assert process.returncode in (0, 1), f"git show-ref failed: {stderr.decode()}"
	return stdout.decode("utf-8", errors="replace")


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


async def test_two_steps_of_different_modules_do_not_share_a_branch(tmp_path: Path) -> None:
	"""FR-100: the separation is between modules, and this is the case that shows it."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	first = await ensure_module_branch(workspace, 0, "interfaces", module="ledger-model")
	second = await ensure_module_branch(workspace, 1, "operation", module="reporting-api")

	assert first.branch == f"{BRANCH_PREFIX}ledger-model"
	assert second.branch == f"{BRANCH_PREFIX}reporting-api"
	assert first.branch != second.branch
	assert await branch_of(workspace) == second.branch, "the switch did not take effect"
	assert second.created_branch is True


async def test_two_steps_of_one_module_share_its_branch(tmp_path: Path) -> None:
	"""The reconciliation of FR-100 with FR-136, which is the whole reason for ``module``.

	FR-136 forbids one goal session per module -- a module does not fit in one session's
	context -- so a module's work spans several steps. Those steps must land on the
	module's branch, or "per module" would be per step wearing a module's name.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	first = await ensure_module_branch(workspace, 2, "operation", module="ledger-model")
	second = await ensure_module_branch(workspace, 5, "invariant", module="ledger-model")

	assert first.branch == second.branch == f"{BRANCH_PREFIX}ledger-model"
	assert first.created_branch is True
	assert second.created_branch is False, "the second step recreated the module's branch"


async def test_a_step_with_no_module_falls_back_to_its_own_ordinal(tmp_path: Path) -> None:
	"""A branch named from a guess is worse than one named from the step.

	A bootstrap step covers no clause, so no module owns it; the record must say which
	happened rather than leave a reader to infer it from the branch name.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()

	checkout = await ensure_module_branch(workspace, 0, "bootstrap")

	assert checkout.branch == f"{BRANCH_PREFIX}000-bootstrap"
	assert checkout.module is None


async def test_a_module_named_step_records_the_module(tmp_path: Path) -> None:
	"""The dispatch record carries *which* module, so the branch is checkable after the fact."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()

	checkout = await ensure_module_branch(workspace, 0, "interfaces", module="ledger-model")

	assert checkout.module == "ledger-model"
	assert checkout.branch == f"{BRANCH_PREFIX}ledger-model"


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


# --------------------------------------------------------------------------- #
# sealing: a branch is a boundary only once it has a commit
# --------------------------------------------------------------------------- #


async def test_an_unsealed_step_leaves_no_branch_behind(tmp_path: Path) -> None:
	"""The defect this fixes, asserted directly rather than described.

	A step that never commits produces no ref, so ``show-ref`` is empty and the branch
	exists only as HEAD's target. That is what let the *next* step branch from an unborn
	HEAD and the two steps become unrelated histories over one working tree.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	await ensure_module_branch(workspace, 0, "bootstrap")

	assert (await refs_of(workspace)).strip() == "", (
		"an unsealed branch must not be a ref -- this is the defect being pinned"
	)


async def test_sealing_creates_the_ref_and_names_the_commit(tmp_path: Path) -> None:
	"""The seal is what turns a branch name into a branch."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_branch(workspace, 0, "bootstrap")
	(workspace / "module.py").write_text("x = 1\n", encoding="utf-8")

	sealed = await seal_branch(checkout, workspace, note="bootstrap")

	assert sealed.sealed_commit is not None, "nothing was committed"
	assert sealed.sealed_paths == 1
	assert sealed.sealed_files == ("module.py",), "the seal must name what it committed (FR-113)"
	assert sealed.head_commit == sealed.sealed_commit
	refs = await refs_of(workspace)
	assert f"refs/heads/{checkout.branch}" in refs, "the branch is still not a ref"


async def test_the_seal_records_every_path_the_producer_wrote(tmp_path: Path) -> None:
	"""FR-113's input: which files a module produced, which only the seal can say.

	The producer reports nothing about what it wrote, so this is the sole place the
	attribution exists. A count cannot be analysed for imports, and the branches are
	cumulative, so a module's own files are the ones *its* step sealed.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_branch(workspace, 0, "operation", module="ledger-core")
	(workspace / "src").mkdir()
	(workspace / "src" / "core.py").write_text("x = 1\n", encoding="utf-8")
	(workspace / "src" / "helpers.py").write_text("y = 2\n", encoding="utf-8")

	sealed = await seal_branch(checkout, workspace, note="ledger-core work")

	assert set(sealed.sealed_files) == {"src/core.py", "src/helpers.py"}
	assert sealed.sealed_paths == len(sealed.sealed_files)


async def test_a_later_step_branches_from_the_sealed_one(tmp_path: Path) -> None:
	"""The whole point of sealing: the second step's history contains the first's.

	Without the seal this test fails with ``base_branch is None`` and an orphan branch,
	which is exactly what the pre-fix code did.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	first = await ensure_module_branch(workspace, 0, "bootstrap")
	(workspace / "module.py").write_text("x = 1\n", encoding="utf-8")
	first = await seal_branch(first, workspace, note="bootstrap")

	second = await ensure_module_branch(workspace, 1, "interfaces")

	assert second.base_branch == first.branch, "the second step did not branch from the first"
	# `merge-base --is-ancestor` says it with its exit code and prints nothing, so the
	# call itself is the assertion: run_git raises unless git exited 0.
	await run_git(workspace, "merge-base", "--is-ancestor", first.branch, second.branch)


async def test_the_earlier_steps_file_is_not_stageable_on_the_later_branch(tmp_path: Path) -> None:
	"""The concrete harm: unsealed work is adopted by whichever branch comes next."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	first = await ensure_module_branch(workspace, 0, "bootstrap")
	(workspace / "module.py").write_text("x = 1\n", encoding="utf-8")
	await seal_branch(first, workspace, note="bootstrap")

	await ensure_module_branch(workspace, 1, "interfaces")

	assert (await run_git(workspace, "status", "--porcelain")).strip() == "", (
		"the first step's file is still pending on the second step's branch"
	)


async def test_module_branches_are_cumulative_not_isolated(tmp_path: Path) -> None:
	"""A measured limitation, pinned so no later reader mistakes these for isolation.

	Each module's branch is created off the previous one's tip, so a later module's branch
	*contains* every earlier module's files and is a descendant of its branch. Measured:
	after three module steps, ``sofact/reporting`` listed ``ledger-model.py`` and
	``ledger-core.py`` alongside its own, and each branch was an ancestor of the next.

	This is what a branch can be. A branch is a pointer into one history, so separate
	branches over one working tree cannot hold separate files — only a worktree can
	(FR-141, deferred in ADR-0024). P7's import analysis must therefore read a module's
	files from the *commit range* between its branch and its parent, not from the branch's
	tree, or every module would appear to contain every other module's code and FR-113's
	"no module reaches another module's internals" would be untestable.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	modules = ("ledger-model", "ledger-core", "reporting")
	branches: list[str] = []
	for ordinal, module in enumerate(modules):
		checkout = await ensure_module_branch(workspace, ordinal, "operation", module=module)
		(workspace / f"{module}.py").write_text(f"# {module}\n", encoding="utf-8")
		await seal_branch(checkout, workspace, note=f"{module} work")
		branches.append(checkout.branch)

	last = await run_git(workspace, "ls-files")
	assert "ledger-model.py" in last, "the measurement changed: branches are no longer cumulative"
	assert "reporting.py" in last
	for earlier, later in pairwise(branches):
		await run_git(workspace, "merge-base", "--is-ancestor", earlier, later)


async def test_a_step_that_changed_nothing_seals_nothing(tmp_path: Path) -> None:
	"""A no-op session is not a failure, and must not invent an empty commit."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_branch(workspace, 0, "bootstrap")

	sealed = await seal_branch(checkout, workspace, note="nothing happened")

	assert sealed.sealed_commit is None
	assert sealed.sealed_paths == 0
	assert sealed.head_commit is None, "an unborn HEAD reports no commit, not a fabricated one"


async def test_a_producer_that_committed_its_own_work_is_reported_as_such(tmp_path: Path) -> None:
	"""``head_commit`` without ``sealed_commit`` is a different fact from doing nothing."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_branch(workspace, 0, "bootstrap")
	(workspace / "module.py").write_text("x = 1\n", encoding="utf-8")
	await run_git(workspace, "add", "module.py")
	await run_git(workspace, "commit", "-qm", "producer committed this itself")

	sealed = await seal_branch(checkout, workspace, note="bootstrap")

	assert sealed.sealed_commit is None, "there was nothing left for SoFact to seal"
	assert sealed.head_commit is not None, "the producer's own commit must still be reported"


async def test_excluded_paths_are_not_committed(tmp_path: Path) -> None:
	"""SoFact's own bookkeeping is not the module being built."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_branch(workspace, 0, "bootstrap")
	(workspace / "module.py").write_text("x = 1\n", encoding="utf-8")
	sessions = workspace / "sessions"
	sessions.mkdir()
	(sessions / "transcript.json").write_text("{}\n", encoding="utf-8")

	sealed = await seal_branch(checkout, workspace, note="bootstrap", exclude=("sessions",))

	assert sealed.sealed_paths == 1, "the session directory was swept into the commit"
	assert sealed.sealed_files == ("module.py",), (
		"the recorded paths must exclude the factory's own bookkeeping, or P7's import "
		"analysis would read SoFact's ledger as part of the module it is analysing"
	)
	tracked = await run_git(workspace, "ls-files")
	assert "module.py" in tracked
	assert "sessions/transcript.json" not in tracked, "the factory committed its own bookkeeping"


# --------------------------------------------------------------------------- #
# FR-141: worktree per module
# --------------------------------------------------------------------------- #


async def test_a_worktree_gives_the_step_its_own_directory(tmp_path: Path) -> None:
	"""The whole point: two branches of one repository share one working tree."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()

	checkout = await ensure_module_worktree(workspace, 0, "operation", module="ledger-core")

	assert checkout.worktree is not None, "an isolated step must name where it ran"
	assert Path(checkout.worktree).is_dir()
	assert Path(checkout.worktree).resolve() != workspace.resolve()
	assert checkout.branch == f"{BRANCH_PREFIX}ledger-core"


async def test_two_isolated_steps_cannot_see_each_others_files(tmp_path: Path) -> None:
	"""Measured, because this is the property a branch alone does *not* have.

	The sibling branch test above pins the opposite result for branches: each module's
	branch contains every earlier module's files. Here each step's *directory* holds only
	its own, which is what FR-141 asks for and what makes a concurrent wave safe.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	left = await ensure_module_worktree(workspace, 0, "operation", module="ledger-core")
	right = await ensure_module_worktree(workspace, 1, "operation", module="reporting")
	assert left.worktree is not None and right.worktree is not None

	(Path(left.worktree) / "core.py").write_text("# core\n", encoding="utf-8")
	(Path(right.worktree) / "report.py").write_text("# report\n", encoding="utf-8")

	assert not (Path(left.worktree) / "report.py").exists(), (
		"a sibling step's file appeared in this step's worktree, so the wave is not isolated"
	)
	assert not (Path(right.worktree) / "core.py").exists()
	assert not (workspace / "core.py").exists(), (
		"an isolated session's file reached the shared workspace before it was integrated"
	)


async def test_re_isolating_the_same_step_reuses_its_worktree(tmp_path: Path) -> None:
	"""FR-099: a retry must not discard the worktree it is retrying."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	first = await ensure_module_worktree(workspace, 0, "operation", module="ledger-core")
	assert first.worktree is not None
	(Path(first.worktree) / "core.py").write_text("# core\n", encoding="utf-8")

	second = await ensure_module_worktree(workspace, 0, "operation", module="ledger-core")

	assert second.worktree == first.worktree
	assert (Path(second.worktree or "") / "core.py").exists(), "the retry discarded the work"


async def test_a_step_no_module_owns_gets_a_branch_but_no_worktree(tmp_path: Path) -> None:
	"""A worktree is per *module*, and a bootstrap step has none to be per.

	Handing it one would be worse than refusing: two module-less steps of a wave share
	the fallback branch, so they would share one directory and collide exactly as two
	branches of one working tree do.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()

	checkout = await ensure_module_worktree(workspace, 0, "bootstrap")

	assert checkout.module is None
	assert checkout.worktree is None, "no module means no worktree to be per"
	assert checkout.branch == f"{BRANCH_PREFIX}000-bootstrap", "the branch is still established"


async def test_integrating_a_worktree_moves_its_work_onto_the_line(tmp_path: Path) -> None:
	"""A worktree that is never merged is a place work goes to disappear."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_worktree(workspace, 0, "operation", module="ledger-core")
	assert checkout.worktree is not None
	(Path(checkout.worktree) / "core.py").write_text("# core\n", encoding="utf-8")
	sealed = await seal_branch(checkout, Path(checkout.worktree), note="core work")

	merged = await integrate_worktree(workspace, sealed, note="integrate ledger-core")

	assert merged.integrated_commit is not None
	assert merged.merge_conflict is False
	assert merged.worktree == checkout.worktree, (
		"the checkout still records where the session ran; integrated_commit says the work landed"
	)
	assert not Path(checkout.worktree).exists()
	assert (workspace / "core.py").exists(), "the work did not reach the integration line"


async def test_a_later_step_branches_from_the_integrated_line(tmp_path: Path) -> None:
	"""The integration line is what the *next* wave checks out, so it must advance."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	first = await ensure_module_worktree(workspace, 0, "operation", module="ledger-core")
	assert first.worktree is not None
	(Path(first.worktree) / "core.py").write_text("# core\n", encoding="utf-8")
	sealed = await seal_branch(first, Path(first.worktree), note="core work")
	await integrate_worktree(workspace, sealed, note="integrate ledger-core")

	second = await ensure_module_worktree(workspace, 1, "operation", module="reporting")

	assert second.worktree is not None
	assert (Path(second.worktree) / "core.py").exists(), (
		"the second wave's worktree lacks the first wave's work, so a dependent is building "
		"on a tree its dependency never touched"
	)


async def test_a_conflicting_merge_is_recorded_rather_than_raised(tmp_path: Path) -> None:
	"""Two steps that touched one file is a scheduling result, not a crash.

	The merge is aborted, so the integration line stays a tree a human can read instead
	of one holding conflict markers no oracle can parse -- and the branch survives as a
	ref, so the work is recoverable.
	"""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	base = await ensure_module_worktree(workspace, 0, "operation", module="ledger-core")
	assert base.worktree is not None
	(Path(base.worktree) / "shared.py").write_text("v = 1\n", encoding="utf-8")
	await integrate_worktree(
		workspace,
		await seal_branch(base, Path(base.worktree), note="base"),
		note="integrate base",
	)

	left = await ensure_module_worktree(workspace, 1, "operation", module="reporting")
	right = await ensure_module_worktree(workspace, 2, "operation", module="metrics")
	assert left.worktree is not None and right.worktree is not None
	(Path(left.worktree) / "shared.py").write_text("v = 2\n", encoding="utf-8")
	(Path(right.worktree) / "shared.py").write_text("v = 3\n", encoding="utf-8")
	sealed_left = await seal_branch(left, Path(left.worktree), note="left")
	sealed_right = await seal_branch(right, Path(right.worktree), note="right")

	await integrate_worktree(workspace, sealed_left, note="integrate left")
	conflicted = await integrate_worktree(workspace, sealed_right, note="integrate right")

	assert conflicted.merge_conflict is True
	assert conflicted.integrated_commit is None
	assert not Path(right.worktree).exists(), "an aborted merge still removes its worktree"
	assert (workspace / "shared.py").read_text(encoding="utf-8") == "v = 2\n", (
		"the abort left the integration line holding a half-applied merge"
	)
	assert "<<<<<<<" not in (workspace / "shared.py").read_text(encoding="utf-8")


async def test_integrating_a_checkout_with_no_worktree_is_refused(tmp_path: Path) -> None:
	"""A shared-tree checkout has nothing to merge, and inventing one would be a lie."""
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	checkout = await ensure_module_branch(workspace, 0, "bootstrap")

	with pytest.raises(AssertionError, match="only a worktree checkout can be integrated"):
		await integrate_worktree(workspace, checkout, note="nothing to do")
