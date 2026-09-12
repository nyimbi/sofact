# 0020. A verdict whose inputs are all still present holds without re-running

## Status

Accepted.

## Context

FR-006 has two halves, and for a long time only one of them existed. The ordering half —
*a result older than the change under test must not decide that change* — was implemented
as run scoping (ADR-0015): every observation carries the identity of the run that produced
it, and a verdict weighs one run. The keyed half — *"caching must be keyed by content hash
of both the change and the oracle definition"* — was left open, and ADR-0015 said so
plainly: nothing hashes the artefact, nothing is cached, each check re-runs the oracles.

Leaving it open was safe; leaving it open was also expensive, and the cost was already
measured. ADR-0015's own Consequences recorded it: because FR-163 checks *every* clause of
the contract after *every* completed session, a nine-step plan through one workspace
rendered nine full reports — 45 clause verdicts for five clauses. Each re-run of an oracle
set is wall clock on a shared machine, the binding resource FR-101 names, and the oracles
run identically every time because nothing between the runs moved.

The gap was in *what identifies a verdict's inputs*. Three things decide what a verdict
says: the clause set it is phrased against, the tree the oracles inspected, and the oracle
declarations that ran. Run scoping says the verdict is fresh; the content hash says the
verdict is still true.

## Decision

**The dispatch check keys its verdict before it measures, and reuses a verdict whose key
matches a previous one.**

1. **The key is three hashes, folded.** `verdict_cache_key(contract, artefact_digest)`:
   the contract's content hash, a digest of the workspace tree, and
   `oracle_set_hash(contract)`. All three, deliberately:
   * the **contract hash** includes the clause *statements*. A verdict is phrased per
     clause; reusing one across a reworded clause would attach old words to new clauses,
     which no digest of the oracles alone can catch;
   * the **artefact digest** is `digest_tree(workspace)` — a content hash over every
     regular file, ignoring VCS metadata, interpreter caches, dependency installs and
     build outputs (`DEFAULT_DIGEST_EXCLUDES`), and **skipping symlinks rather than
     following them**, because a link aimed outside the tree would fold bytes no session
     wrote into the key and give a producer a route to freeze its own verdict;
   * the **oracle-set hash** is FR-006's named component. It is derivable from the
     contract hash, so it is redundant — and it stays, because a requirement that names a
     key component should find that component in the key, and because a future change to
     the derivation is caught by the key instead of silently re-keying every verdict.
2. **Reuse is recorded as a reuse.** A matched verdict is re-committed as
   `verdict.reused`, carrying the original verdicts and a `reused_from` moment naming the
   verdict it stands in for. The CLI prints the same line. A reuse that looked like a
   second measurement would be a fabricated measurement.
3. **The digest is taken before any oracle runs.** An oracle that mutates the tree would
   otherwise corrupt the key of the very verdict it is being measured for.
4. **`dispatch --fresh` bypasses.** The cache is an optimisation, not an obligation; an
   operator who doubts it re-measures without re-configuring.
5. **The cache is not a pass cache.** A `VIOLATED` verdict is exactly as reproducible as
   a `SATISFIED` one, and a reused refutation still refuses its dependent wave.
6. **Reuse applies only where the artefact is addressable.** `check_dispatch` owns a
   workspace and digests it. `verify_contract` weighs the log and has no tree to digest,
   so it re-measures from recorded evidence every time — and a report it renders carries
   an empty `cache_key`, which is recorded as never reusable rather than as silently
   reusable.

## Alternatives refused

* **mtime/size fingerprints.** Refused: mtime does not survive a copy or a fresh clone,
  size does not survive an equal-length edit, and a producer able to touch timestamps
  could freeze its own verdict. Content is the only honest fingerprint.
* **`git status` / the git index as the change hash.** Refused: a workspace need not be a
  repository, and a producer able to write its own index would be able to write its own
  cache key.
* **Cache in `verify_contract` too.** Refused for now: that path weighs *recorded*
  evidence and has no workspace, so there is no change hash to key on. The honest default
  is an empty key, which never matches.
* **Reuse only when the prior verdict was clean.** Refused as an asymmetry with no
  mechanism behind it: the same inputs that reproduce a pass reproduce a failure, and a
  one-sided cache would quietly bias the log towards green.
* **Digest after the oracles run.** Refused: it would key the verdict to a tree the
  oracles themselves had mutated, making the key say "unchanged" for the wrong tree.
* **Key on the oracle set alone.** Refused: clause *statements* can move while oracles
  stand still, and a reuse across a reworded clause is a verdict about words nobody wrote.

## Consequences

* ADR-0015's redundancy cost is paid **once per distinct tree** instead of once per
  completed session. The measured case is the degenerate one — a plan run through one
  unchanged workspace rendered one verdict and reused the rest — and the same mechanism
  gives back the cost on real runs, where a no-op step no longer re-runs the whole oracle
  set.
* The reuse line names its moment, so an operator auditing the log sees a chain of
  reuses terminating in one measured verdict — provenance survives the optimisation.
* `digest_tree` reads every file it admits; on a large workspace that is real I/O before
  every check. The excludes keep it proportional to *the change*, not to the toolchain's
  debris, and the excludes are data (a parameter), so a deployment can widen them.
* An oracle that is genuinely non-deterministic (reads a clock, draws a random case) can
  be reused over: the key says the tree is unchanged, not that the oracles are pure. The
  honest instruments for that are property oracles with seeded generation, or `--fresh`.

## Evidence

* `src/sofact/execution.py` — `digest_tree`, `DEFAULT_DIGEST_EXCLUDES`.
* `src/sofact/verification.py` — `verdict_cache_key`; `verify` stamps `cache_key` and
  `run_id` on the report and refuses a key without a run.
* `src/sofact/views.py` — `VerificationReport.run_id` / `cache_key` / `reused_from`;
  `LedgerKind.VERDICT_REUSED`.
* `src/sofact/service.py` — `check_dispatch(reuse=…)`, `dispatch_step(fresh=…)`,
  `dispatch_plan(fresh=…)`.
* `tests/ci/test_execution.py::TestDigestTree` — 9 tests: order-independence, cache
  exclusion, symlink skipping, loud failure on a missing tree.
* `tests/ci/test_verification.py::TestTheCacheKey` — 7 tests, including the three
  components each keying on its own.
* `tests/ci/test_service.py::TestTheVerdictCache` — 6 tests, including the reuse of a
  *violated* verdict and the `--fresh` bypass.
* `tests/ci/test_cli.py::TestTheVerdictCache` — the reuse is printed, and `--fresh`
  suppresses it.
* Measured during development: the fold-census test caught the new kind immediately, and
  a full `dispatch_plan` through one unchanged workspace reuses after the first check.

## References

* ADR-0015 — a verdict describes one run (the ordering half of FR-006; the redundancy
  cost that motivated this record is in its Consequences).
* ADR-0003 — the ledger is append-only and hash-chained, which is why a reuse must be a
  row rather than a cache in memory.
* FR-006, FR-136, FR-139, FR-163.
