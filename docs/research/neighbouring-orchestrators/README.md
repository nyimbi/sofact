# Two neighbouring orchestrators — what OpenRig and Paperclip change here

Date 2026-10-12. Sources: [S26](../../sources/s26-openrig.md) (OpenRig, Apache 2.0,
0.6.0) and [S27](../../sources/s27-paperclip.md) (Paperclip, MIT, 100.7k★). Both are
product READMEs, read in full; neither was installed or executed. Both sit at the same
layer as SoFact — above the harnesses, not inside one — so they are the nearest
available evidence about what that layer's hard parts actually are.

**Outcome:** one defect found and reproduced in SoFact (the ledger had no atomic
append), now fixed under [ADR-0029](../../adr/0029-an-append-takes-an-exclusive-lock.md);
one reporting gap; one isolation hazard to check; and one negative result about
differentiation. Nothing here changes the spec; the defect was a bug against FR-003.

## 1. The finding: SoFact's ledger is not atomic, and Paperclip names the fix

Paperclip's README leads its "why this is special" table with:

> **Atomic task checkout.** A single assignee and execution locks prevent competing
> runs from claiming the same task.

That is a claim about a shared mutable store under concurrency, which is exactly what
SoFact's ledger is. `Ledger.append` reads the cached tail, builds the next entry on it,
and writes, with no lock and no re-read:

```python
entries = self.entries()                 # the cache, or a read of the file
entry = LedgerEntry.create(index=len(entries), ..., prev_hash=self.last_hash())
with self.path.open("a", ...) as handle:
    handle.write(...)
self._cache = (*entries, entry)
```

Two appends that read the same tail both claim the same `index` and the same
`prev_hash`. **Measured on this tree**, two processes synchronized so that both read an
empty log before either appended:

```
a: index=0 prev=000000000000
b: index=0 prev=000000000000
--- what the file holds ---
 index 0 advisor.note {'text': 'a'} prev 000000000000
 index 0 advisor.note {'text': 'b'} prev 000000000000
chain: ok=False length=2 broken_at=1 reason='index 0 at position 1'
```

The damage is not the lost row. FR-003 makes a broken chain `LedgerCorruptError`, and
`FactoryService.state()` calls `require_intact()` before every fold — so the project
becomes **unreadable** until a human repairs the file by hand. A concurrency bug that
halts the tool rather than corrupting one answer is the worse of the two failure modes.

**It is reachable from the shipped surface, not only from a contrived test.**
`dispatch_plan(concurrent=True)` gathers every step in a wave:

```python
if concurrent and len(wave) > 1:
	records = list(await asyncio.gather(*(self.dispatch_step(...) for step in wave)))
```

Every `dispatch_step` ends in `self._commit(...)`, and `_commit` calls
`ledger.append`. Within one event loop the coroutines interleave at `await` points, and
`_commit` is synchronous — but a wave is gathered, the loop is shared, and the `await`s
between two commits are many. The in-process case is narrower than the two-process one
reproduced above, and it is not zero. The two-process case is the real one: nothing in
SoFact claims the log has a single writer, and `sofact --home <shared>` from two shells
is an ordinary thing to do.

**This is a bug, not a design decision, and it is fixed rather than merely recorded.**
The fix is an exclusive lock held across read-tail-and-append, which is what Paperclip's
"execution locks" are. `fcntl.flock` on a sibling `ledger.lock` is the POSIX answer and
was already available; the lock covers the whole read-modify-write, and the read cache
is dropped inside it so the tail chained onto is the one on disk rather than the one
this process remembers. The lock file is a sibling rather than the log itself because
`flock` binds to an inode, and the log's inode is not something this code owns. This is
recorded as [ADR-0029](../../adr/0029-an-append-takes-an-exclusive-lock.md), with
`TestConcurrentAppend` in `tests/ci/test_ledger.py` driving two real subprocesses
synchronised on marker files.

**The generalisable lesson** (this is the one worth keeping): a hash-chained log makes
history *tamper-evident*, and it is easy to mistake that for making it
*append-safe*. The chain detects a fork after the fact and then refuses to read; it
does nothing to prevent one. Detection is not prevention, and a store whose response to
corruption is to halt is a store that needs a lock, not a better hash.

## 2. A reporting gap: "the work cannot be resumed without a human"

OpenRig's restore reports per-node outcomes, and one of them is a state SoFact does not
have:

> `awaiting-decision` (the original conversation can't resume; choose `--fresh`)

SoFact's `StepOutcome` is `NOT_DISPATCHED | COMPLETED | FAILED | BUDGET_EXHAUSTED`. A
step whose session left no record — the harness exited without writing one, or the
record command printed nothing (ADR-0028) — was **measured** on this tree to read as
`outcome=completed, exit_code=0, session_path=None`, with a note beginning "no session
record was found, so nothing about this session was witnessed beyond the process exit".

`completed` is **correct** and is not the defect. FR-163 triggers the check on the
session's *process* outcome — "when its process exits without timing out" — and the
verdict is about the artefact in the workspace, not about the record. The spec already
documents a prior defect caused by gating that trigger on a declaration the default
harness cannot make, and re-gating it on the record would repeat it. An earlier reading
of this section proposed a `StepOutcome.UNWITNESSED`; that was wrong for exactly that
reason and was reverted.

The defect was in the **display**. `_print_dispatch` printed `record.note` only when
the outcome was `NOT_DISPATCHED`, so a session that exited 0 and left no record read as
`completed` in green with "its artefact was checked" underneath, while the one sentence
saying nothing was witnessed sat unprinted in a field the operator never sees. A caveat
the operator cannot see is a caveat that does not exist, and this one contradicts the
line above it. The fix prints the note for every outcome — red for `NOT_DISPATCHED`,
yellow otherwise — with the defect recorded in the comment, and
`test_a_recordless_session_does_not_read_as_a_green_completion` in `tests/ci/test_cli.py`
holds it, canaried against the unpatched `cli.py` where it fails.

OpenRig's five states remain a fair shape for a *future* state that says *the work may
have happened and cannot be recovered*, which is load-bearing for FR-006's verdict
reuse: a verdict keyed to an artefact whose provenance is unknown stands on nothing.
That is a real distinction NFR-024 would want named. It is **not** what the outcome
field is for, and it is not needed to fix the reporting: the note already carries it,
and the note is now visible. Queued as a separate question, not folded into the enum.

## 3. An isolation hazard to check: an env var is not a boundary

OpenRig's README states, unusually plainly:

> The provider files are separate from instance state. Here `~` means the daemon user's
> home; **changing `OPENRIG_HOME` alone does not isolate provider configuration.**

SoFact's harness specs isolate with environment variables — `CLAUDE_CONFIG_DIR` for
`claude`, `OPENCODE_DB` + `OPENCODE_TEST_HOME` for `opencode` — and the opencode pair
was *measured* to matter only together with `--standalone` (ADR-0028). OpenRig's warning
generalises that single measurement into a rule:

**An isolation variable is not an isolation boundary until something measures that the
provider honoured it.** The probe already has the machinery to do this — it runs a
second child for the rows that need one (FR-019, `_probe_concurrent`). A row that
asserts the private store is empty after a session, and that the user's real store did
not move, is a differential measurement of the kind FR-165 already describes. This is
worth adding to the probe rather than assuming; the alternative is a spec field that
*looks* like isolation and has never been observed to isolate.

## 4. The negative result: differentiation is not orchestration

S22 found that every mechanism SoFact treats as differentiated already exists free in
the `dsh` plugin ecosystem. Read against that, these two are the same result at the
orchestration layer:

| SoFact mechanism | OpenRig | Paperclip |
| --- | --- | --- |
| Declarative multi-harness topology (FR-058, FR-161) | `RigSpec` YAML | org chart, agent specs |
| Budgets (FR-097, FR-140) | per-seat policy | "budget hard-stops", cost control |
| Durable audit log (FR-004, NFR-027) | SQLite + `bundle-audit.jsonl` | "durable activity", Postgres |
| Revision + rollback (FR-094) | snapshot/restore | "revisioned config with rollback" |
| Goal ancestry / traceability (FR-127) | culture + continuity | "goal ancestry" |
| Permission policy per seat (FR-059) | audited `set-permissions` | RBAC, gateway actions |
| Producer isolation (FR-016–020, FR-141) | tmux + workspace trust | workspaces & runtime |
| **Oracle required per clause (FR-001)** | — | — |
| **Verdict over producer-independent evidence (FR-006, FR-012)** | — | — |
| **Autonomy ceiling from measured oracle rank (FR-007, FR-105)** | — | — |
| **Escape attribution to the misunderstood clause (FR-127's purpose)** | — | — |

Three projects at this layer, three times the same absence. Paperclip's verification is
"verify from diffs, screenshots & tests" with an approval stage governing completion —
a human reading artefacts, with no separation between the party that produces the
evidence and the party that judges it. OpenRig's is "review the exact candidate
artifact."

The honest reading cuts both ways, and both halves belong in the record. Either the four
rows at the bottom are SoFact's actual differentiation, or they are evidence that the
market does not want them — 100.7k stars for Paperclip against zero for SoFact is a
fact about demand, not about correctness. The spec already knows this: §6.4 and R15
name "credibility risk" as the product's largest, and FR-086 exists to stop SoFact
claiming value it cannot measure. **The same discipline applies to this table**: it is
evidence about positioning, and it must not be read as evidence that the verification
discipline works. Nothing in either source tests that.

## 5. What was not learned, and why

- **Neither project was installed or executed.** Every claim above is the vendor's
  description of its own system. The one claim this session could test independently —
  atomic checkout — was tested against SoFact instead, which is where it mattered.
- **Paperclip's 100.7k stars are not evidence of quality.** See [S27]'s concerns
  section; the figure is an outlier against every comparable source in this ledger and
  no independent adoption evidence was gathered.
- **OpenRig's `Culture`/`CULTURE.md` mechanism was not evaluated.** It is a way to layer
  norms onto a default team, which is adjacent to SoFact's goal-text constraints, but
  nothing here measured whether it changes behaviour. It is queued, not concluded.
- **Paperclip's plugin system and OpenRig's MCP server were not read.** Both would bear
  on FR-155's third-party deletion test, which the roadmap audit already records as
  prose-only.

## Sources

- `docs/sources/s26-openrig.md` — [S26], archive at `docs/sources/archive/s26-openrig-README.md`
- `docs/sources/s27-paperclip.md` — [S27], archive at `docs/sources/archive/s27-paperclip-README.md`
- `src/sofact/ledger.py` — `Ledger.append`, the unlocked read-modify-write
- `src/sofact/service.py:1038` — `dispatch_plan`'s `asyncio.gather` over a wave
- `docs/sources/s22-dsh-plugin-ecosystem.md` — the same negative result one layer down
