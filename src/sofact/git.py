"""Branch-per-module and worktree-per-module checkouts: the one place SoFact touches git.

FR-100 requires build to occur "on a branch per module, never in place", and FR-141
requires concurrent sessions to be isolated by "git worktree per module" because
branches share one working tree. Both halves live here:

* :func:`ensure_module_branch` is the sequential path. It brings the dispatch workspace
  to a repository on the branch named for the plan step, so a producer that commits
  lands on the branch the goal text names.
* :func:`ensure_module_worktree` is the concurrent path. It gives each concurrent step
  its *own* directory on its module's branch, so two sessions in one wave cannot see or
  overwrite each other's files. :func:`integrate_worktree` merges that branch back onto
  the integration line and removes the directory, which is what stops a concurrent wave
  from building work the next wave never sees.

The scope is deliberately narrow. SoFact does not push, and does not resolve a merge
conflict — a conflict is a *result* and is recorded as one rather than invented away.

Every function is idempotent and safe to re-run: a second dispatch of the same step
finds the repository, the branch and the worktree already present and changes nothing.
That is FR-099 applied to the harness, because a retry that re-created the repository
would discard the work it was retrying.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Final

from sofact.views import ModuleCheckout

__all__ = [
	"BRANCH_PREFIX",
	"WORKTREE_DIRNAME",
	"GitUnavailableError",
	"ensure_module_branch",
	"ensure_module_worktree",
	"git_available",
	"integrate_worktree",
	"seal_branch",
]

BRANCH_PREFIX: Final = "sofact/"
"""Every branch SoFact creates is namespaced, so an operator's own branches are untouched."""

WORKTREE_DIRNAME: Final = ".sofact-worktrees"
"""Where a concurrent step's worktree lives, relative to the repository it belongs to.

Inside the repository rather than beside it, so it is removed with the workspace and an
operator moving or deleting the tree moves all of it. It is excluded from sealing and
from FR-006's artefact digest, because a sibling module's checkout is not this module's
work and a digest that folded it in would key a verdict to another step's files.
"""

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


def _branch_name(step_ordinal: int, step_kind: str, module: str | None) -> str:
	"""The branch a step's work belongs on, named from the module when one owns it.

	FR-100 asks for a branch per **module**, and FR-136 forbids one goal session per
	module — a module does not fit in one session's context — so a module's work spans
	several steps and those steps share one branch. When no module owns the step
	(bootstrap; a step spanning two), the branch falls back to the step's ordinal and
	kind, because a branch named from a guess is worse than one named from the step.
	"""
	if module is not None:
		return f"{BRANCH_PREFIX}{module}"
	return f"{BRANCH_PREFIX}{step_ordinal:03d}-{step_kind}"


async def _ensure_repository(workspace: Path) -> bool:
	"""Make ``workspace`` a repository, leaving whatever is there alone. Reports creation.

	The integration line is ``main``, and a worktree path never switches off it: the
	worktree holds the module's branch, so the main working tree stays on the line the
	worktrees are merged *into*. Measured: checking the branch out in the main tree first
	makes ``git worktree add`` refuse it — a branch cannot be checked out twice.
	"""
	if await _is_repository(workspace):
		return False
	code, _, stderr = await _git(("init", "--quiet", "-b", "main", "."), cwd=workspace)
	if code != 0:
		raise GitUnavailableError(f"git init failed in {workspace}: {stderr.strip()}")
	return True


async def ensure_module_branch(
	workspace: Path, step_ordinal: int, step_kind: str, *, module: str | None = None
) -> ModuleCheckout:
	"""Bring ``workspace`` to a repository on the branch this step's work belongs on.

	This is the **sequential** path: the session works in the shared tree, on the branch
	its work belongs on. :func:`ensure_module_worktree` is the concurrent path and gives
	the branch a working tree of its own instead.

	Idempotent by construction: an existing repository keeps its history, an existing
	branch is checked out rather than recreated, and a workspace that is already on the
	right branch is left alone. The returned :class:`~sofact.views.ModuleCheckout`
	records *what the branch is* so a dispatch can carry it in the log, which is what
	makes FR-100 checkable after the fact rather than only at the moment of dispatch.
	"""
	assert workspace.is_dir(), f"workspace does not exist: {workspace}"
	branch = _branch_name(step_ordinal, step_kind, module)
	created_repository = await _ensure_repository(workspace)
	created_branch = False

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
			module=module,
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
		module=module,
		created_repository=created_repository,
		created_branch=created_branch,
		base_branch=base_branch,
	)


async def _head_commit(workspace: Path) -> str | None:
	code, stdout, _ = await _git(("rev-parse", "--verify", "--quiet", "HEAD"), cwd=workspace)
	if code != 0:
		return None
	return stdout.strip() or None


def _worktree_path(workspace: Path, branch: str) -> Path:
	"""Where ``branch``'s worktree lives, named from the branch and nothing else.

	The branch is the identity, so the directory is derived from it rather than from a
	counter or a session id: a re-dispatch of the same step finds the same directory
	(FR-099), and two steps of one module share it exactly as they share the branch
	(FR-136). ``sofact/`` is stripped because a nested ``sofact`` directory under the
	worktree root would read as the namespace rather than as a name.
	"""
	assert branch.startswith(BRANCH_PREFIX), f"not a SoFact branch: {branch}"
	name = branch[len(BRANCH_PREFIX) :]
	assert name, "a branch with no name under the prefix has no worktree to name"
	return workspace / WORKTREE_DIRNAME / name.replace("/", "-")


async def _registered_worktrees(workspace: Path) -> dict[str, Path]:
	"""Every worktree git has registered, keyed by the branch it holds.

	Read from git rather than from the filesystem, because a directory that *looks* like
	a worktree and is not registered is not one: ``git worktree add`` refuses a path it
	already knows, so the decision to reuse or create has to be made against git's own
	record.
	"""
	code, stdout, stderr = await _git(("worktree", "list", "--porcelain"), cwd=workspace)
	if code != 0:
		raise GitUnavailableError(f"git worktree list failed in {workspace}: {stderr.strip()}")
	found: dict[str, Path] = {}
	path: Path | None = None
	for line in stdout.splitlines():
		if line.startswith("worktree "):
			path = Path(line[len("worktree ") :].strip())
		elif line.startswith("branch ") and path is not None:
			ref = line[len("branch ") :].strip()
			found[ref.removeprefix("refs/heads/")] = path
			path = None
	return found


async def ensure_module_worktree(
	workspace: Path, step_ordinal: int, step_kind: str, *, module: str | None = None
) -> ModuleCheckout:
	"""Give this step its own checkout of its module's branch (FR-141).

	FR-141 exists because a branch is not isolation: every branch of one repository
	shares one working tree, so two concurrent sessions on two branches still write the
	same files. A worktree is a second working tree over the same object store, which is
	the weakest thing that actually separates them.

	The branch is established through :func:`_branch_name`, the same function the
	sequential path uses, so both agree on which branch a step belongs to — a worktree on
	a different branch from the sequential path's would make FR-100's record depend on
	whether a wave happened to be concurrent.

	**The integration line is the shared workspace's own HEAD.** The module's branch is
	checked out *only* in the worktree, because a branch cannot be checked out twice and
	the shared tree is where the worktrees are merged back to. A worktree therefore
	branches off whatever the shared tree holds — which is the previous wave's integrated
	work, whether that arrived sequentially on a module branch or by an earlier merge.

	**A step with no module gets a branch of its own but no worktree.** ``module is None``
	means no single module owns the step's clauses, so there is no module for the worktree
	to be *per*; and two module-less steps of one wave share the fallback branch, which
	would put them in one directory and reintroduce exactly the collision FR-141 forbids.
	The caller is expected to keep such a wave sequential, and this refusal is what makes
	that expectation visible rather than a silent sharing.

	Idempotent: a re-dispatch of the same step finds the branch and the registered
	worktree and reuses both (FR-099), so a retry does not discard the work it retries.
	"""
	assert workspace.is_dir(), f"workspace does not exist: {workspace}"
	if module is None:
		return await ensure_module_branch(workspace, step_ordinal, step_kind, module=None)
	branch = _branch_name(step_ordinal, step_kind, module)
	created_repository = await _ensure_repository(workspace)
	path = _worktree_path(workspace, branch)
	registered = await _registered_worktrees(workspace)
	existing = registered.get(branch)
	has_history = await _has_commits(workspace)
	base_branch = (await _current_branch(workspace)) if has_history else None
	if existing is not None:
		if existing.resolve() != path.resolve():
			raise GitUnavailableError(
				f"branch {branch} is already checked out at {existing}, not at the "
				f"path this step derives ({path}); two worktrees cannot hold one branch"
			)
		return ModuleCheckout(
			branch=branch,
			step_ordinal=step_ordinal,
			module=module,
			created_repository=created_repository,
			created_branch=False,
			base_branch=base_branch,
			worktree=str(path),
		)

	path.parent.mkdir(parents=True, exist_ok=True)
	# A repository whose HEAD is unborn cannot `worktree add` a branch off it, so the first
	# worktree of a fresh project is created as an orphan -- which is the state the
	# sequential path's first branch is in too, and it merges into the unborn line with
	# `--ff-only` once it has a commit.
	args = (
		("worktree", "add", "--quiet", "--orphan", "-b", branch, str(path))
		if not has_history
		else ("worktree", "add", "--quiet", "-b", branch, str(path))
	)
	code, _, stderr = await _git(args, cwd=workspace)
	if code != 0:
		raise GitUnavailableError(
			f"git worktree add for {branch} failed in {workspace}: {stderr.strip()}"
		)
	# A worktree inherits no identity, and the seal commits from inside it. Scoped to the
	# worktree rather than written to the operator's global config, for the same reason the
	# branch path scopes it.
	await _git(("config", "user.name", _COMMITTER_NAME), cwd=path)
	await _git(("config", "user.email", _COMMITTER_EMAIL), cwd=path)
	return ModuleCheckout(
		branch=branch,
		step_ordinal=step_ordinal,
		module=module,
		created_repository=created_repository,
		created_branch=True,
		base_branch=base_branch,
		worktree=str(path),
	)


async def integrate_worktree(
	workspace: Path, checkout: ModuleCheckout, *, note: str
) -> ModuleCheckout:
	"""Merge a sealed worktree's branch back onto the integration line, and remove it.

	FR-141 isolates concurrent sessions; it does not license building work the next wave
	cannot see. Without this, a worktree is a place work goes to disappear: the integration
	line never advances, so a later step checks out a tree that lacks everything the wave
	produced, and P7's import analysis reads modules that are not there.

	**The merge is aborted on conflict, and the conflict is recorded rather than raised.**
	Two concurrent steps that touched one file is a real scheduling result — it means the
	modules genuinely overlap — and reporting it as a crash would lose the difference
	between a factory that cannot merge and two modules that do. The abort is what keeps
	the integration line a tree a human can reason about instead of one holding conflict
	markers no oracle can read.

	The worktree is removed either way. A conflicted branch is still a ref, so the work is
	not lost; leaving the directory behind would leak one per failed merge, and a
	re-dispatch would find it and reuse a checkout whose branch the operator has since
	moved on from.

	A branch with **no commit** is not an error: a session that changed nothing leaves one,
	and there is nothing to merge. The worktree is removed and the checkout comes back with
	no integration recorded, which is the honest report — ``integrated_commit is None``
	alongside ``sealed_commit`` and ``head_commit`` both ``None`` reads as "nothing to
	integrate", not as "not integrated yet".

	``worktree`` stays set either way. It is a record of *where the session ran*, and the
	directory it names is gone by the time anyone reads it — exactly as ``workspace`` names
	a directory rather than asserting one is there. Whether the work reached the line is
	``integrated_commit``'s to say.
	"""
	assert checkout.worktree is not None, "only a worktree checkout can be integrated"
	path = Path(checkout.worktree)
	if checkout.sealed_commit is None and checkout.head_commit is None:
		await _git(("worktree", "remove", "--force", str(path)), cwd=workspace)
		return checkout
	has_history = await _has_commits(workspace)
	args = ["merge", "--no-ff", "--allow-unrelated-histories", "-m", note, checkout.branch]
	if not has_history:
		# An unborn integration line has nothing to be a merge *of*, so the first worktree's
		# history becomes the line. Measured: `git merge` refuses this with "Non-fast-forward
		# commit does not make sense into an empty head", while `--ff-only` takes it.
		args = ["merge", "--ff-only", checkout.branch]
	code, _, stderr = await _git(tuple(args), cwd=workspace)
	conflicted = code != 0
	if conflicted:
		await _git(("merge", "--abort"), cwd=workspace)
	await _git(("worktree", "remove", "--force", str(path)), cwd=workspace)
	if conflicted:
		return checkout.model_copy(update={"merge_conflict": True, "integrated_commit": None})
	integrated = await _head_commit(workspace)
	assert integrated is not None, f"a merge that succeeded must leave a resolvable HEAD: {stderr}"
	return checkout.model_copy(update={"merge_conflict": False, "integrated_commit": integrated})


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
			"sealed_files": owned,
			"head_commit": sealed,
		},
	)
