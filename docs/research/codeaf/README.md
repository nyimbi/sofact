# CodeAF — a factory that is also a harness

Date 2026-10-13. Source: [S28](../../sources/s28-codeaf.md) (CodeAF, Apache 2.0, by
AgentField AI). A product README, fetched raw and read in full; not installed, not
executed. Archive at `docs/sources/archive/s28-codeaf-README.md`.

**Outcome:** one measurement the ledger has never held (a comparative harness cost, in
which SoFact's two wired adapters are the expensive side); one shipped mechanism SoFact
has no counterpart for (a verdict distribution feeding back into dispatch); one direct
counterexample to FR-140; and no change to the spec. Read this beside
[`neighbouring-orchestrators`](../neighbouring-orchestrators/README.md) — [S26] and
[S27] are the same layer as SoFact, and CodeAF is the same layer *and* a harness, which
is why it gets its own study rather than a fourth row in that one's table.

## 1. Why this neighbour is a different kind of neighbour

OpenRig and Paperclip are control planes over other people's agents. CodeAF is that
**and** a coding harness — the same binary that schedules the work also does it, and it
benchmarks itself against the harnesses SoFact dispatches to. That makes it the first
source in this ledger that can say something about the *adapter table* (FR-161) rather
than about the orchestration layer above it.

Its own framing of the category is worth recording because it is the same argument
SoFact makes, from the other end:

> Agents run by hand got fast, but the scheduling, checking and merging stayed with you.
> … A factory is the third picture: one line out, one line back.

## 2. The finding: a comparative harness cost, and SoFact's adapters are the expensive ones

The ledger holds harness measurements — [S21] executed `dsh`, [S25] executed
`pi-research`, `docs/research/driver-set` compares `pi`, `omp` and `opencode` on argv and
record shape. None of them is a **cost per solved task**. [S12]'s verification queue
(item 3) asks for exactly this, one level down, about models.

CodeAF publishes it, one level up, about harnesses. On DeepSeek V4 Flash, over 113 real
GitHub issues from DeepSWE, graded by the benchmark's own verifiers, `/senior-dev` is
reported first of ten at **54.9%**, with every rival's cost per *solved* issue expressed
as a multiple of its own:

| harness | cost per solved issue |
| --- | --- |
| CodeAF `/senior-dev` | 1.0x |
| mini-swe-agent | 1.9x |
| codex | 2.1x |
| **`pi`** | **2.4x** |
| **`claude-code`** | **3.4x** |
| `omp`, `kilo`, `opencode` | ≈4.5x |
| muse-code | 11.3x |
| deepseek-harness | 26.6x |

**`pi` and `claude` are the two adapters SoFact has wired** (`PI_SPEC`, `CLAUDE_SPEC`),
and both are on the losing side of this table. If the numbers hold, SoFact's dispatch
path is spending 2.4x and 3.4x what the cheapest measured harness spends for the same
solved issue, on the same model.

Three things must be said before this is acted on, and the first two are why it is
recorded rather than adopted.

- **It is a vendor's benchmark of its own product, on a model and a harness set it
  chose.** "Graded by the official verifiers" is a claim about the grading, not about
  the selection. The method is in `docs/benchmarks/deepswe`, which was not fetched; the
  `Pareto Crewing` paper is a PDF in the repo and was not read.
- **The cost multiplier is not the whole cost.** A harness that is cheaper per solved
  issue and *less* amenable to a machine-readable completion reason is more expensive to
  SoFact, because FR-140 requires SoFact to hold the budget and read the outcome itself.
  `pi` "emits nothing" and `dsh` emits a structured `turn/end` — that asymmetry is
  already recorded in `harness.py` and it does not appear in any cost table.
- **What it does establish is that the dimension exists and is unmeasured here.** FR-161
  makes the adapter table data; nothing in it is a cost. That is a gap this source
  exposes without filling.

**The honest use of this table is as a probe list, not a migration.** The cheap version
of the question is whether CodeAF's own headless surface (`codeaf do … --json`) satisfies
`HarnessSpec` — and the table then becomes a reason to add a fourth spec, not to drop
the first two.

## 3. The counterexample: `do` takes its best answer

This is the sharpest thing in the source, and it is stated plainly rather than buried:

> `do` takes your brief byte for byte, plans, runs and checks it, and prints one JSON
> object and an exit code. **Where the conversation would ask, it takes its best answer
> and records the assumption.**

SoFact's §2.4 argument is that the authority to resolve an open question sits with the
human, and FR-140 makes the split structural rather than procedural: a producer that can
answer its own question has quietly widened its own specification, and the widening is
invisible because it looks like progress. `do` does the opposite by design.

It is a defensible trade for the stated use — CI, cron, a benchmark harness; an
unattended run has nobody to ask — and CodeAF does not hide it. But it is the exact
inversion of SoFact's first rule, and it belongs in the record as a **counterexample
with a real constituency**, not as a gap in SoFact. A reader who prefers CodeAF's
behaviour is choosing unattended throughput over specification fidelity, and that is a
choice the spec should be read as having made deliberately (FR-001, §1.5).

The narrower observation underneath it: CodeAF's answer to the unverifiable case is a
**queue**, not a refusal.

> Work that passes its check lands on your branch by itself… Work nothing could check
> waits under `unread`: `1` accept, `2` not right.

SoFact refuses to let an unverifiable clause exist (FR-001). CodeAF lets it exist and
routes it to a human. Same problem, opposite structural answer, and CodeAF's is the one
that ships in a product people use. That is worth knowing.

## 4. The mechanism with no counterpart: a verdict distribution that moves dispatch

CodeAF grades every finished task "by the check it already had to pass", then uses the
distribution of those outcomes to move the per-seat model weights:

> Each seat is scored from its catalog metadata by learned weights, **moved by how this
> install's own tasks ended**.

SoFact does the first half and not the second. `verify` produces verdicts, `escape`
(FR-021–023, ADR-0054) folds the ledger into a per-lane rate, and the rate reduces an
autonomy ceiling — measurement feeding policy, which is the same shape. The difference is
what the policy *is*: SoFact's rate moves an autonomy level, CodeAF's moves a model
choice. Nothing in SoFact reads a verdict distribution back into a dispatch decision.

This is the one mechanism here with genuinely no counterpart, and it is adjacent to work
already done rather than to work not started: FR-022's rate is computed, and the dispatch
path already takes per-step configuration. Whether a measured success rate should pick a
harness per step is a design question this study does not answer — but it is now a
question with a shipped precedent, and [S22]'s negative result ("every mechanism SoFact
treats as differentiated already exists free") does not cover it, because this one is not
about verification. It is about *routing*.

## 5. What was not learned, and why

- **Not installed or executed.** Every claim above is the vendor's description of its own
  system. The one question that would decide its adapter value — whether `codeaf do
  --json` carries a machine-readable *incomplete* state, as the subharness abstraction
  implies — is not answerable from a README.
- **The DeepSWE numbers were not reproduced, and cannot be cheaply.** Reproducing them
  needs the benchmark's issues, its verifiers and a DeepSeek V4 Flash seat. The `pi` and
  `claude` multipliers are the most quotable numbers in this source and the least
  verified; do not cite them as established.
- **The performance table (53 MB binary, 27 MB per session, 145 ms resume) was not
  measured.** It compares against `claude` and `opencode` with the method behind a link
  that was not fetched. Resource footprint is not a SoFact decision input today, so this
  is recorded and left.
- **`Pareto Crewing` was not read**, nor `docs/HEADLESS.md`, nor the benchmark method.
  Any of the three could change §2 or §4; all three are named so the next pass starts
  from the right place.
- **The star count was not captured**, and the project is "early preview" by its own
  badge — treat its command surface as moving.

## Sources

- `docs/sources/s28-codeaf.md` — [S28], archive at `docs/sources/archive/s28-codeaf-README.md`
  (sha256 `990bae76d70e373c8fc7209c2f48167dd2bcbaaa081401adf95fb9eae6f8c499`)
- `src/sofact/harness.py` — `HarnessSpec`, and the `completion_reason_path` asymmetry
  between `dsh` and `pi`
- `docs/research/neighbouring-orchestrators/README.md` — [S26], [S27], the same negative
  result at the orchestration layer
- `docs/research/driver-set/README.md` — the existing harness comparison, on argv and
  record shape rather than cost
- `docs/sources/s22-dsh-plugin-ecosystem.md` — the same negative result one layer down
