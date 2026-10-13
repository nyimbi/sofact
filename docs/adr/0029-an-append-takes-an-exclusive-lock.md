# 29. An append takes an exclusive lock across the read-modify-write

* Status: Accepted
* Date: 2026-10-12
* Deciders: operator
* Related: [ADR-0003](0003-the-ledger-is-append-only-and-hash-chained.md),
  [ADR-0024](0024-branch-per-step-is-built-worktrees-are-deferred.md)

## Context

ADR-0003 built the chain to make history **tamper-evident** and recorded, correctly,
that it is not tamper-proof. It did not ask the adjacent question: is the log
**append-safe**? A hash chain detects a fork after the fact. It does not prevent one,
and the detection here is a *refusal* — FR-003 makes a broken chain
`LedgerCorruptError`, and `FactoryService.state()` calls `require_intact()` before
every fold.

`Ledger.append` read the cached tail, chained onto it, and wrote, with no lock and no
re-read. Two writers that read the same tail therefore claimed the same `index` and
the same `prev_hash`. Measured on this tree, two processes synchronised so that both
read an empty log before either appended:

```text
a: index=0 prev=000000000000
b: index=0 prev=000000000000
chain: ok=False length=2 broken_at=1 reason='index 0 at position 1'
```

The damage is not the lost row. The project becomes **unreadable** — every later
`state()`, `verify_ledger()` and `dispatch` raises until a human repairs the file by
hand. A concurrency bug whose symptom is a halt rather than a wrong answer is the
worse of the two failure modes, because there is no degraded path to fall back to.

It is reachable from the shipped surface. `dispatch_plan(concurrent=True)`
`asyncio.gather`s every step in a wave and each step ends in `_commit` →
`ledger.append`. The in-process window is narrow, since `_commit` is synchronous and
the coroutines interleave only at `await` points. The multi-process window is not
narrow at all: nothing in SoFact claims the log has a single writer, and
`sofact --home <shared>` from two shells is an ordinary thing to do.

## Decision

**`Ledger.append` holds an exclusive `fcntl.flock` across the entire
read-modify-write**, and drops its read cache inside the lock so the tail it chains
onto is the one on disk rather than the one this process remembers.

Three details are part of the decision rather than of the implementation:

1. **The lock is a sibling file, `ledger.lock`, not the log.** `flock` binds to an
   inode. The log is created on first append and is not replaced afterwards, so
   locking the log would work today — but the lock's correctness would then rest on
   an invariant no code states, and `lock_path` is cheap insurance against a future
   atomic-replace. The lock file is created once and never rewritten.
2. **`flock` is advisory.** Every writer in this tree goes through `append`, which is
   why the module docstring states the rule rather than leaving it to the reader. An
   advisory lock is a contract between the parties that honour it; the honest claim is
   "two SoFact processes cannot fork the chain", not "no process can".
3. **The cache is dropped on entry, unconditionally.** The whole point is that the
   cached tail may be stale. Keeping the cache across the lock and merely re-reading
   when a marker changed would reintroduce the same window one level down.

The lock is held for the duration of one short synchronous write, so it serialises
appends without serialising reads: `entries()` and `verify_chain()` still read the
cache and take no lock.

## Consequences

* **Two SoFact processes appending to one log is now safe.** `sofact --home <shared>`
  from two shells produces a chain that verifies, with the second appender chained
  onto the first rather than onto the log both of them read.
* **Every append costs one `open` and one `flock`.** Measurable but small against a
  write; the correctness it buys is a property the tool cannot do without.
* **A second file now exists in the home directory.** It is a synchronisation
  primitive, not an account of the run, so it is added to `_unowned_paths` (it must
  not be sealed into a module being built) and to the exclusion list in
  `test_the_service_writes_exactly_one_file` — where the exclusion is paired with an
  assertion that the file is empty, so it cannot become a place to hide a record.
  That test is the reason the exclusion is stated rather than merely applied: an
  exclusion list that grows silently is how a "one file" invariant stops meaning
  anything.
* **The lock does not make the log tamper-proof**, and does not change ADR-0003's
  conclusion about an external anchor. It closes a fork, not a rewrite.
* **A `NFS`-mounted home is outside this guarantee.** `flock` over NFS has
  historically been unreliable; the deployment envelope (spec §1.3) is a local home
  directory, so this is recorded rather than solved.

## Alternatives refused

* **Re-read the tail without a lock.** Narrows the window; does not close it. Two
  writers can still both read, both build, both write.
* **Lock the log file itself.** Correct today and fragile tomorrow, for the reason in
  decision 1.
* **An in-process `threading.Lock`.** Does nothing for the multi-process case, which
  is the case that was measured. It would have passed a test written from the
  in-process symptom.
* **Detect and repair the fork on read.** This is the failure mode restated as a
  feature. A store that can fork and then reconciles is a store whose history is
  negotiable, which is exactly what the chain exists to deny.
* **Make the ledger a database.** A defensible direction, and not this one: the
  ledger's value is that it is a file a human can read and diff. A lock is the smaller
  change that keeps it one.

## Evidence

`tests/ci/test_ledger.py::TestConcurrentAppend` drives two **real subprocesses**
synchronised on marker files — each asserts it read an empty log, writes a ready
marker, and waits for the go marker — so both have read the tail before either
appends. The synchronisation is on the filesystem, not on `sleep`: a test that races
on timing passes for the wrong reason.

* `test_two_writers_do_not_fork_the_chain` — the chain verifies, length 2, both
  payloads present.
* `test_a_writer_sees_the_other_writers_entry` — indices are `[0, 1]` and the second
  entry's `prev_hash` is the first's `entry_hash`.

Both fail on the unpatched code with the transcript above, and were re-canaried after
the fix by removing the lock and watching them fail again.
