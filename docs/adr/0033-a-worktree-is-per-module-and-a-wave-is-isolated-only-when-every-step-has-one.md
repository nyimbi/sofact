# 0033 — A worktree is per module, and a wave is isolated only when every step can have one

- **Status:** Accepted
- **Date:** 2026-10-12
- **Supersedes:** ADR-0024's deferral of FR-141, and its decision 3 ("FR-141 stays
  deferred") and the consequence "parallel dispatch stays off by default". ADR-0024's
  FR-100 half — the branch, and the seal that makes it a boundary — stands unchanged, as
  does its decision 4 (a worktree is containment, not confinement).
- **Related:** FR-100, FR-141, FR-142, FR-136, FR-006, FR-138, FR-140, FR-003, FR-099;
  [ADR-0005](0005-no-container-runtime.md), [ADR-0023](0023-a-record-is-addressed-by-a-path.md),
  [ADR-0024](0024-branch-per-step-is-built-worktrees-are-deferred.md),
  [ADR-0025](0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md),
  [ADR-0030](0030-phases-are-a-state-machine-and-a-gate-is-a-type-boundary.md)

## Context

FR-141 requires concurrent sessions to be isolated by "git worktree per module", on the
grounds that branches share a working tree. ADR-0024 deferred it on a condition its own
author wrote: "until a wave runs concurrently or a plan spans more than one module,
whichever comes first". The capability map measured both halves and found the condition
had fired (`docs/research/orchestrator-capabilities/README.md` §3.1): a plan spanning more
than one module is the case `_module_for` exists for, and `dispatch_plan(concurrent=True)`
existed at the API while the CLI had no flag to reach it — so ADR-0024's "the operator
owns" was, in practice, the operator being unable to choose.

Two things had to be settled before it could be built, and both were settled by
measurement rather than by reading git's documentation.

**Where does the branch live?** The obvious implementation — check the module's branch out
in the main tree, then `git worktree add` it — does not work, and the reason is a
constraint rather than a bug: **a branch cannot be checked out twice**. Measured: with the
main tree switched onto `sofact/ledger-core`, `git worktree add` for that branch refuses,
and the error names the path that already holds it. The design that works is the opposite
one: the main working tree stays on the **integration line**, and the module's branch lives
only in its worktree. That is also the design the requirement wants — the worktrees are
merged *into* the line the main tree holds.

**How does the first worktree land on an unborn line?** A fresh workspace has no commits,
so `git merge --no-ff` refuses ("Non-fast-forward commit does not make sense into an empty
head") and so does `--allow-unrelated-histories`. Measured: `merge --ff-only` is the only
form that lands the first worktree's history on an unborn line, and the worktrees
themselves must be created with `worktree add --orphan` for the same reason. Six concurrent
`worktree add` calls all succeed, and orphan worktrees are genuinely isolated from each
other.

## Decision

**FR-141 is built. A worktree is per module, the main tree holds the integration line, and
a wave is isolated only when every step in it can be given a worktree of its own.**

1. **`ensure_module_worktree` creates the branch *in the worktree*, never in the main
   tree.** The repository is created if absent, the worktree is added on a new branch off
   HEAD (`--orphan` when HEAD is unborn), and the main tree is left on the line the merges
   land on. A re-dispatch of the same step finds the same directory, because the path is
   derived from the branch and the branch from the module (FR-099).
2. **`dispatch_step(isolate=True)` moves the adapter's workspace into the worktree.** Every
   thing downstream — the seal, the session directory, the oracles — then operates on the
   worktree without knowing the difference, which is why the change is one branch rather
   than a parallel code path. The seal excludes `.sofact-worktrees` unconditionally:
   measured, with four worktrees live and the exclusion absent, one step's seal reported
   **600 paths**, and those paths are what P7 attributes files *from* — so every module
   would have appeared to contain every other module's code.
3. **The wave is integrated before it is judged.** `_integrate_wave` merges each isolated
   step's branch back onto the integration line, in the wave's own order, before the next
   wave is dispatched. Without it a dependent builds on a tree missing everything its
   dependency produced, which is precisely what FR-142 exists to prevent. The order is the
   wave's rather than the sessions' completion order, because the merge order is what the
   line's history *means* and a nondeterministic order would make two runs of one plan
   differ in a way nothing explains.
4. **A conflicted merge is recorded, not raised.** `merge_conflict=True`, the merge is
   aborted, and the branch survives as a ref. Two overlapping modules is a *scheduling*
   result — the decomposition said these could be built independently and the work says
   otherwise — and turning it into an exception would discard the evidence that the
   decomposition was wrong.
5. **A wave is isolated only when every step in it is owned by a distinct module.**
   `wave_is_isolatable` is the predicate, and both of its conditions are directory
   collisions rather than preferences. A step no module owns has no worktree to be given —
   `ensure_module_worktree` hands it the shared-tree branch, because a worktree is per
   module and there is no module to name one after — so two such steps would both run in
   the shared tree. Two steps of the **same** module would be given the same branch and
   therefore the same directory, which FR-136 makes normal *sequentially* and exactly one
   directory too few concurrently. A wave that fails either test runs sequentially.
6. **`--concurrent` becomes an operator flag, and it is off by default.** The default
   stays off for the reason ADR-0024 gave and this record does not overturn: two sessions
   in one tree is a merge conflict, not a speedup, and the operator is the one who knows
   whether the plan's modules are genuinely disjoint. What changed is that the operator can
   now choose.
7. **The merge is a second ledger row, never a rewrite.** The log is append-only (FR-003)
   and a rewritten dispatch row would break the chain that makes it tamper-evident, so the
   integration appends its own `step.dispatched` row carrying the merged checkout. The fold
   was changed to key dispatches by id with the latest row winning, preserving
   first-appearance position — so log order still means *when a dispatch started* rather
   than when it was last amended. The rule for reading the log changed; the log did not.
8. **This is containment, not confinement, and the docs still say so.** A worktree
   contains a session that stays put; it does not confine one that wanders. `sandboxable`
   remains `ABSENT` for both `pi` and `claude` (ADR-0023), and ADR-0005 still refuses
   containers. What a worktree buys is that two sessions at once cannot see or overwrite
   each other's files — the FR-138 and FR-006 argument from ADR-0024 §5 — and that is the
   whole of the claim.

## Alternatives refused

- **Check the branch out in the main tree, then add a worktree for it.** Refused by
  measurement: git refuses a branch checked out twice, so this cannot be built. The
  constraint is what forces the integration-line design, which is also the better one.
- **Isolate every wave, including the module-less ones.** Refused: a module-less step has
  no worktree to be given, and inventing a branch-per-step fallback worktree would put the
  *shared* step in a private directory whose work the integration line then has to learn
  about — machinery with no requirement behind it. Sequential is the honest answer, and the
  predicate says which case it is.
- **Raise on a merge conflict.** Refused in decision 4. A conflict is the decomposition
  being wrong, and that is a finding the operator needs; an exception thrown mid-wave
  destroys the record of which branches collided.
- **Rewrite the dispatch row with the merged checkout.** Refused: it would break FR-003's
  chain, and the chain is what makes the log evidence rather than a claim. The fold keys
  instead.
- **Leave the worktree in place after integration, as a cache.** Refused: a worktree that
  outlives its wave is a leak that compounds per wave, and the branch is the durable
  artefact — the directory is a place a session ran, not a place work is kept. Measured
  after the change: an isolated wave leaves the worktree root empty.
- **Sell the worktree as a sandbox.** Refused, as in ADR-0024 §4 and ADR-0023: neither
  harness confines its child, so a worktree is not one either. The `store_isolated` row
  (ADR-0032) narrows this hazard without closing it.

## Consequences

- **A concurrent wave runs in per-module worktrees and lands on one line.** Measured on
  this tree: a wave of three module-owned steps produces three distinct worktree paths,
  none of them the shared workspace; the integration line afterwards holds every step's
  work; and the worktree root is empty when the wave ends.
- **The module-less bootstrap step still runs in the shared tree.** It is the first wave
  and it is alone in it, so nothing collides; the predicate refuses a wave that would put
  it beside another step.
- **The refusal path is not reachable through `dispatch_plan` today.** The compiler emits
  one clause per step and the proposer one module per clause, so no wave it produces
  contains two module-less steps or two steps of one module. `wave_is_isolatable` is
  therefore tested on waves assembled from the plan's own steps, because a guard with no
  test is one nobody notices is broken — and it is what stands between a future compiler
  that emits such a wave and two sessions in one directory.
- **`dispatch_step` grows an `isolate` parameter that a direct caller must integrate.**
  It defaults to off, and its docstring says what a caller that turns it on owes: a record
  whose `checkout.worktree` is set and whose `integrated_commit` is not. `dispatch_plan`
  is the caller that pays it.
- **`ModuleCheckout` gains `worktree`, `integrated_commit` and `merge_conflict`**, with
  validators that make three impossible states unrepresentable: an integrated commit
  without a worktree, a conflict alongside an integrated commit, and an integrated commit
  that is not the branch tip. `worktree` stays set after integration because it records
  *where the session ran*; whether the work reached the line is `integrated_commit`'s to
  say, and one field answering both questions would have to be wrong about one of them.
- **The state fold now resolves a keyed dispatch.** `dispatches` is a mapping rather than
  a list, which is a change to how the log is read and not to what may be written to it.
- **`.sofact-worktrees` is excluded from sealing and from FR-006's artefact digest.** A
  sibling module's checkout is not this module's work, and a digest that folded it in would
  key a verdict to another step's files.
- **The spec's tooling table loses its second false claim about this feature.** The
  `dsh-git-worktree` entry said SoFact "drives only `init`, `switch`, `config`, `add`,
  `commit` and `status`" and that FR-141 was deferred; SoFact now drives `worktree add`,
  `worktree list`, `worktree remove` and `merge` as well, and the composition decision is
  now about a wrapper over a feature that exists rather than one that does not.

## Evidence

- `src/sofact/git.py` — `ensure_module_worktree`, `integrate_worktree`, `_ensure_repository`,
  `_worktree_path`, `_registered_worktrees`, `WORKTREE_DIRNAME`.
- `tests/ci/test_git.py` — 8 tests under the FR-141 banner: a worktree gives the step its
  own directory; two isolated steps cannot see each other's files; re-isolating reuses the
  worktree; a module-less step gets a branch but no worktree; integrating moves the work
  onto the line; a later step branches from the integrated line; a conflicting merge is
  recorded rather than raised; integrating a checkout with no worktree is refused.
  `tests/ci/test_git.py`: **29 passed**.
- `tests/ci/test_service.py::TestWorktreeIsolation` — 6 tests: a concurrent wave isolates
  every step it can; an isolated wave leaves no worktree behind; the integration line holds
  every isolated step's work; the shared workspace sees what the wave built; a wave with an
  unownable step is not isolated; the merge is recorded as its own row.
- **Canary**: `wave_is_isolatable`'s predicate was replaced with `return True` (the patch
  asserted its target string was present first, and the file was restored from a backup
  rather than from git), and `test_a_wave_with_an_unownable_step_is_not_isolated` failed.
  Restored, it passes.
- Measured while building, each by running git rather than reading its documentation: a
  branch cannot be checked out twice; `merge --no-ff` refuses an unborn head while
  `--ff-only` does not; `worktree add --orphan` creates an isolated tree on an unborn HEAD;
  six concurrent `worktree add` calls all succeed.
- `tests/ci` at this commit: **739 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

- FR-141 (worktree per module), FR-100 (branch per module), FR-142 (wave dispatch), FR-136
  (a module's work spans several steps), FR-003 (append-only chain), FR-006 and FR-138 (a
  verdict describes one run's work), FR-099 (a re-dispatch finds what the last one left),
  FR-140 (session lifecycle is the factory's).
- [ADR-0023](0023-a-record-is-addressed-by-a-path.md) — containment is not confinement.
- [ADR-0025](0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md) —
  where the module identity this record needed came from.
- `docs/research/orchestrator-capabilities/README.md` §3.1 — the measurement that the
  deferral's condition had fired.
