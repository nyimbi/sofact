# 24. Worktree isolation is deferred, not required

* Status: Accepted
* Date: 2026-10-12
* Deciders: operator
* Related: [ADR-0005](0005-no-container-runtime.md),
  [ADR-0006](0006-the-verifier-cannot-reach-the-executor.md),
  [ADR-0023](0023-a-record-is-addressed-by-a-path.md)

## Context

FR-100 requires build to occur "on a branch per module, never in place", and FR-141
requires concurrent sessions to be isolated by "git worktree per module", on the grounds
that branches share a working tree. Neither is implemented: `GoalStep` carries no module
or branch field, the dispatch workspace is `mkdir`-ed by `FactoryService.dispatch_step`
and never `git init`-ed, and `dispatch_plan` runs waves sequentially with `concurrent`
off by default.

That gap was invisible because two documents asserted the feature existed. Every
dispatched goal instructed the producer to "Work in the assigned worktree on the assigned
branch" — a tree nothing assigned, on a branch nothing created, in a directory that was
not a repository. The spec's own tooling table went further and described
`dsh-git-worktree` as "a thin wrapper over `git worktree add`, **which SoFact already
drives**". Nothing in the codebase invokes git at all.

The goal-text half was corrected in the commit before this record, and is now pinned by
`test_no_goal_claims_a_worktree_or_branch_nothing_assigns`. This record decides the other
half: whether to build it.

## Decision

**FR-100 and FR-141 are deferred. They are not dropped, and they are not required for
the factory to build a single-module system.**

1. **Nothing depends on them today.** Single-module dispatch is a deliberate scope bound
   (README, P3/P5). With one module there is nothing to isolate *from*, and with
   `concurrent` off there is no second writer. The requirement costs nothing to defer
   because the configuration it protects does not exist yet.
2. **They are not a merge-complexity tax, and they are not a velocity win either.** The
   honest accounting: worktrees do not remove the merge, they **defer** it from "two
   writers clobber one file mid-flight" (loud, immediate, attributable) to "N branches
   reconcile at integration" (quiet, and a new place work can conflict silently). That
   deferral is only worth paying for once there is an integration phase to do the
   reconciling, and O8 does not exist.
3. **The reason to keep them in the design is verdict attribution, not git hygiene.**
   An oracle runs against a workspace. Two sessions sharing one means clause A's verdict
   is polluted by session B's edits, and the factory loses the ability to say *whose work*
   a green light describes — which is FR-138 and FR-006, the load-bearing guarantees.
   This argument holds even with zero parallelism, so isolation is not merely a
   concurrency feature.
4. **Worktrees are containment, not confinement, and must not be sold as the latter.**
   Measured twice (ADR-0023): neither `pi` nor `claude` confines its child to its working
   directory, so a wandering producer escapes a worktree exactly as easily as a shared
   tree. A filesystem boundary is what contains a process, and ADR-0005 refuses
   containers. Worktrees keep *honest* producers' work separate; they do not stop a
   dishonest or confused one.
5. **The precondition for revisiting is stated.** FR-141 becomes necessary at the moment
   `dispatch_plan` runs a wave concurrently, or at the moment a plan spans more than one
   module. Whichever comes first, isolation lands in the same commit as the feature that
   needs it — not before.

## Alternatives refused

* **Implement FR-141 now, ahead of need.** Refused: it is machinery whose only consumer
  is a feature that does not exist, and `git worktree add` against a non-repository
  workspace would fail on first dispatch. Building it first also invites the false
  confidence the last commit removed — a constraint that *looks* enforced.
* **Drop FR-100/FR-141 from the specification.** Refused: they are the right requirement
  for the parallelism the factory is designed to reach. Deferring a requirement and
  deleting it look identical in a status table and are opposite decisions; this record is
  what tells them apart.
* **Keep the goal text as written and treat it as aspirational.** Refused and already
  reverted. An instruction a producer cannot satisfy is either ignored — teaching it that
  its constraints are advisory — or acted on, and then it invents a worktree inside a
  directory no oracle inspects.

## Consequences

* **The status table says "not implemented" and means it.** FR-141 was described as a
  done thing that the goal text referred to; it is now named as the gap that matters most
  under P3/P5, with the measurement that makes it concrete.
* **The spec's tooling table loses a false claim.** `dsh-git-worktree` was justified as a
  wrapper over something SoFact "already drives". It drives nothing of the sort, and the
  entry now says the composition decision is deferred with the requirement.
* **A single-module build is unaffected.** The factory still builds, verifies and repairs
  one module end to end with no isolation, because that path never needed it.
* **Parallel dispatch stays off by default**, and the reason is recorded in
  `dispatch_plan`'s docstring: whether a wave may run together is a question about
  worktrees that the operator owns. That stays true until this record is superseded.

## Evidence

* `src/sofact/planner.py` — the removed `_SHARED_CONSTRAINTS` entry, and the boundary that
  replaced it ("Stay inside the workspace you were given").
* `tests/ci/test_planner.py::test_no_goal_claims_a_worktree_or_branch_nothing_assigns`.
* `rg -n "git worktree|worktree add" src/` — no match outside docstrings: nothing invokes
  git.
* `src/sofact/service.py` — `workdir.mkdir(parents=True, exist_ok=True)`, no `git init`.
* `src/sofact/views.py` — `GoalStep` carries `clause_ids` and `depends_on`; no `module`.
* README § Harness — the `pi` and `claude` `sandboxable: absent` measurements.

## References

* FR-100 (branch per module), FR-141 (worktree per module), FR-138 and FR-006 (a verdict
  describes one run's work), FR-025, FR-142 (waves).
* [ADR-0005](0005-no-container-runtime.md) — why confinement is not available as a
  boundary here.
* [ADR-0023](0023-a-record-is-addressed-by-a-path.md) — the measurements that show a tool
  allowlist is not confinement.
