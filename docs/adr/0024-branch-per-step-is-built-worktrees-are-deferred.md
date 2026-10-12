# 24. Branch-per-step is built; worktree isolation is deferred

* Status: Accepted
* Date: 2026-10-12
* Deciders: operator
* Supersedes: the first version of this record, which claimed a branch was "a *record*
  of separation" while nothing committed to it — a claim refuted by measurement the same
  day (§ Consequences, "the seal")
* Related: [ADR-0005](0005-no-container-runtime.md),
  [ADR-0006](0006-the-verifier-cannot-reach-the-executor.md),
  [ADR-0023](0023-a-record-is-addressed-by-a-path.md)

## Context

FR-100 requires build to occur "on a branch per module, never in place", and FR-141
requires concurrent sessions to be isolated by "git worktree per module", on the grounds
that branches share a working tree. Neither was implemented: the dispatch workspace was
`mkdir`-ed by `FactoryService.dispatch_step` and never `git init`-ed, nothing invoked
git, and `dispatch_plan` runs waves sequentially with `concurrent` off by default.

That gap was invisible because two documents asserted the feature existed. Every
dispatched goal instructed the producer to "Work in the assigned worktree on the assigned
branch" — a tree nothing assigned, on a branch nothing created, in a directory that was
not a repository. The spec's own tooling table went further and described
`dsh-git-worktree` as "a thin wrapper over `git worktree add`, **which SoFact already
drives**".

The goal text was corrected first, in the commit before this record, and is pinned by
`test_no_goal_claims_a_worktree_or_branch_nothing_assigns`. This record decides what to
build in its place, and the two requirements do not move together.

## Decision

**FR-100 is built. FR-141 is deferred. They are separate requirements and treating them
as one was the mistake that let both go unimplemented while looking done.**

1. **A branch per step is established at dispatch.** `sofact.git.ensure_module_branch`
   brings the workspace to a repository on a branch named for the step's ordinal and kind
   (`sofact/000-bootstrap`), called by `dispatch_step` *before* the session starts. The
   resulting `ModuleCheckout` is carried on the `DispatchRecord`, so "never in place" is a
   checkable fact in the log rather than an instruction in a prompt. The goal text may now
   truthfully tell the producer it is already on its branch, and that it must not switch.
2. **FR-100 is enforceable by SoFact alone, which is why it was worth building now.**
   It needs no module identity: a step is the unit, and a step already has an ordinal.
   The worktree requirement needs a `module` field that `GoalStep` does not have, which is
   a decomposition question rather than a git one.
2b. **SoFact commits each step's work onto its branch when the session ends.** Creating a
   branch is not enough to make it a boundary, and the first version of this record
   assumed it was. Measured: with no commit, `sofact/000-bootstrap` is not a ref at all
   (`git show-ref` is empty), the next step's `switch -c` branches from an **unborn HEAD**
   so every step reports `base_branch=None`, and the first step's files stage cleanly on
   the second step's branch — two unrelated histories over one working tree. `seal_branch`
   commits whatever the session left, and the checkout now carries `sealed_commit`,
   `sealed_paths` and `head_commit`. Sealing is the factory's job because FR-140 reserves
   session lifecycle to it: a producer asked to commit can decline, and the boundary would
   then be fictional while the goal text asserted it.
3. **FR-141 stays deferred.** Nothing depends on it while dispatch is single-module and
   sequential: with `concurrent` off there is no second writer, and a branch already keeps
   this step's work off the default line. FR-141 becomes necessary at the moment a wave
   runs concurrently or a plan spans more than one module, whichever comes first.
4. **Worktrees are containment, not confinement, and must not be sold as the latter.**
   Measured twice (ADR-0023): neither `pi` nor `claude` confines its child to its working
   directory, so a wandering producer escapes a worktree exactly as easily as a shared
   tree. A filesystem boundary is what contains a process, and ADR-0005 refuses
   containers. A branch is weaker still: it is a *record* of separation rather than a
   boundary, and a producer that ignores its branch is not stopped by anything here. What
   a sealed branch does buy is that the separation is **real once the session ends** — the
   step's work is a commit on a ref, not a pile of files the next step inherits. What
   stops a violation being invisible is that the checkout is on the dispatch record.
5. **The reason to keep worktrees in the design is verdict attribution, not git hygiene.**
   An oracle runs against a workspace. Two sessions sharing one means clause A's verdict
   is polluted by session B's edits, and the factory loses the ability to say *whose work*
   a green light describes — which is FR-138 and FR-006. That argument holds with zero
   parallelism, so isolation is a correctness feature rather than a speed one.

## Alternatives refused

* **Build FR-141 now, ahead of need.** Refused: it is machinery whose only consumer is a
  feature that does not exist, and a worktree needs a module identity the plan cannot
  supply. Building it first also invites the false confidence the previous commit removed
  — a constraint that *looks* enforced.
* **Drop FR-100/FR-141 from the specification.** Refused: they are the right requirements
  for the parallelism the factory is designed to reach. Deferring a requirement and
  deleting it look identical in a status table and are opposite decisions; this record is
  what tells them apart.
* **Keep the goal text as written and treat it as aspirational.** Refused and already
  reverted. An instruction a producer cannot satisfy is either ignored — teaching it that
  its constraints are advisory — or acted on, and then it invents a worktree inside a
  directory no oracle inspects.
* **Have the goal text name the branch.** Refused: the branch name is derived from the
  step's ordinal, and the goal text is hashed at compile time and re-hashed after the
  session (FR-139). Injecting a value at dispatch would make a legitimate dispatch
  indistinguishable from a producer editing its own objective.

## Consequences

* **A dispatched step's work sits on its own branch, recorded and sealed.**
  `DispatchRecord.checkout` is the branch, its ordinal, what it was branched from, the
  commit SoFact sealed it with, and how many paths that commit holds. `base_branch` is
  `None` for a fresh repository with an unborn HEAD, because a base branch is a place work
  came *from* and there was none; from the second step on it names the previous step's
  branch, and `git merge-base --is-ancestor` confirms the chain rather than assuming it.
* **The seal distinguishes three states that a boolean would have merged.** A session that
  changed nothing, a session whose producer committed its own work, and a session SoFact
  sealed all leave different records: `sealed_commit`/`head_commit` are both `None`,
  `head_commit` alone, and both. Only the third is SoFact's doing, and a record that could
  not tell them apart would report the factory as having sealed work it never touched.
* **The service now writes a second kind of file, and the invariant that says otherwise
  was narrowed deliberately.** `test_the_service_writes_exactly_one_file` excluded
  `sessions` and now also excludes `.git`, each with a stated reason: git's metadata is
  the repository SoFact was asked to create (FR-100), not SoFact's account of the run. The
  assertion still fails if any second *bookkeeping* file appears.
* **git becomes a runtime dependency of dispatch**, and a missing binary raises
  `GitUnavailableError` rather than dispatching unbranched. That is deliberate: a session
  that ran in place has already done the forbidden thing by the time anyone could notice,
  so the refusal must come first. It is an environment fault, not a harness capability
  finding.
* **The spec's tooling table loses a false claim.** `dsh-git-worktree` was justified as a
  wrapper over something SoFact "already drives"; SoFact drives `init`/`switch`/`config`
  and nothing else, and the entry now says the composition decision is deferred with
  FR-141.
* **Parallel dispatch stays off by default**, and the reason is recorded in
  `dispatch_plan`'s docstring: whether a wave may run together is a question about
  worktrees that the operator owns. That stays true until this record is superseded.

## Evidence

* `src/sofact/git.py` — `ensure_module_branch`, idempotent across re-dispatch; and
  `seal_branch`, which commits what the session left.
* `tests/ci/test_git.py` — sixteen tests against real git: a bare directory becomes a
  repository on a named branch, the branch is not `main`, two steps get different
  branches, a re-run creates neither repository nor branch, an existing repository keeps
  its history, an unborn HEAD reports no base branch, a missing workspace is refused, two
  concurrent checkouts do not corrupt each other, and — for the seal — an unsealed branch
  is not a ref, sealing creates the ref, a later step branches from the sealed one, the
  earlier step's file is no longer stageable on the later branch, a no-op session seals
  nothing, a producer's own commit is reported as such, and excluded paths are not
  committed.
* `tests/ci/test_service.py::test_a_dispatched_step_records_the_branch_it_ran_on` — the
  branch reaches the dispatch record, the workspace is a real repository, and the step's
  work is sealed. **Canaried**: with the `seal_branch` call replaced by a comment the test
  fails on `sealed_commit is None`, which is the defect the first version of this record
  shipped.
* `tests/ci/test_planner.py::test_no_goal_claims_a_worktree_or_branch_nothing_assigns` —
  requires the branch instruction and still forbids the worktree claim.
* `rg -n "git worktree|worktree add" src/` — no match outside docstrings.
* `src/sofact/views.py` — `GoalStep` carries `clause_ids` and `depends_on`; no `module`.
* README § Harness — the `pi` and `claude` `sandboxable: absent` measurements.

## References

* FR-100 (branch per module), FR-141 (worktree per module), FR-138 and FR-006 (a verdict
  describes one run's work), FR-139 (the goal text is pinned by hash), FR-025, FR-142.
* [ADR-0005](0005-no-container-runtime.md) — why confinement is not available as a
  boundary here.
* [ADR-0023](0023-a-record-is-addressed-by-a-path.md) — the measurements that show a tool
  allowlist is not confinement.
