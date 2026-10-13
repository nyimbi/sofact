---
id: S28
slug: codeaf
title: "CodeAF — the open-source software factory"
type: product-doc
verification: url-verified (raw README fetched and read in full this session)
confidence: medium
accessed: 2026-10-13
retrieved_via: "raw.githubusercontent.com/Agent-Field/codeaf/main/README.md (17444 bytes, sha256 990bae76d70e373c8fc7209c2f48167dd2bcbaaa081401adf95fb9eae6f8c499)"
archive: archive/s28-codeaf-README.md
url: https://github.com/Agent-Field/codeaf
relates_to: [S18, S19, S20, S21, S22, S23, S26, S27]
---

**Why this entry exists.** CodeAF was named by the operator as a source to learn from,
alongside OpenRig and Paperclip ([S26], [S27]). It sits in the same category as those
two — an orchestration layer above the harnesses — but it is also a **harness in its own
right**, which is what makes it more than a fourth data point on the negative result in
§4 of `docs/research/neighbouring-orchestrators`. It claims a capability SoFact's
adapter table has no row for: a harness that reports a **structured completion reason**.

## Precis

A single Go binary (53 MB), Apache 2.0, by AgentField AI. It presents itself as "a
coding harness built for open models" and "a different way to work once more than one
thing is going on" — one terminal window that lists every project on the machine, hands
work off, and surfaces only the questions that need a human. Install is a curl-to-bash
script; providers are OpenRouter, DeepSeek, GLM, Kimi, MiniMax, Qwen, Codex via a
ChatGPT plan, Ollama, or any OpenAI-compatible endpoint.

Key abstractions, in its own words: **task** (a conversation can fan out into a tree of
tasks, each in its own copy of the repository on its own branch), **subharness** ("a
specialist built for exactly that job … takes typed input and returns typed output, so
it delivers what it promised or is marked incomplete"), **seat** (worker / planner /
checker — a crew of models chosen per task), **standing orders** (rules, reminders and
watches that persist across sessions), **Model Pool** (installs share computed,
text-free model-performance numbers under a per-install nonce).

## Key claims

1. **"Work that passes its check lands on your branch by itself, never on `main`, `dev`
   or a release branch. Work nothing could check waits under `unread`: `1` accept, `2`
   not right."** This is the closest thing in the source to SoFact's producer/verifier
   separation, and it is a *routing* rule rather than a verdict: unverifiable work is
   not refused, it is queued for a human.
2. **A subharness "delivers what it promised or is marked incomplete."** Typed input,
   typed output, an explicit incomplete state. That is a declared-completion asymmetry
   of the kind [S18] measured in `pi-goal`.
3. **`do` takes a brief and "where the conversation would ask, it takes its best answer
   and records the assumption."** Headless mode resolves an unanswerable question by
   guessing and logging the guess.
4. **`#1 on DeepSWE` of ten harnesses on one model** (DeepSeek V4 Flash), 54.9% of 113
   real GitHub issues, "at the lowest cost per solved issue" — measured against
   `mini-swe-agent`, `codex`, `pi`, `claude-code`, `omp`, `kilo`, `opencode`,
   `muse-code` and `deepseek-harness`, graded by the benchmark's official verifiers.
5. **Every finished task "is graded by the check it already had to pass."** The grader
   is the task's own acceptance check, and per-seat model choice is then moved by how
   this install's tasks ended.
6. **A performance table** measured against `claude` and `opencode`: 53 MB on disk
   (claude 224 MB), 27 MB RAM per added session (claude 216 MB), 145 ms to resume a
   50-turn session (claude 392 ms, opencode 3.0 s).
7. **Telemetry is on by default**; the README is the whole disclosure and "a test holds
   it to the code."

## Why it matters for SoFact

- **Claim 4 names `pi` and `claude` — SoFact's two wired adapters — as measured
  competitors.** The ledger has never held a comparative harness number of this kind.
  `pi` is priced at **2.4x** CodeAF's cost per solved issue and `claude-code` at
  **3.4x**; both are on the losing side of the same benchmark, on the same model. This
  is exactly the input [S12]'s verification-queue item 3 asks for ("replace the
  aggregated model landscape with measured numbers"), except one level up — it is about
  harnesses, not models, and SoFact's FR-161 adapter table has no cost column at all.
  It does not change a decision; it makes a *previously unmeasured* dimension visible.
  **It is the vendor's own benchmark of its own product**, which is the weakest form of
  the evidence, and it must be treated as such until independently reproduced.
- **Claim 1 is FR-140's authority split, implemented as a router instead of a gate.**
  SoFact refuses a completion claim by signature (FR-138) and holds the budget itself;
  CodeAF's equivalent is that unchecked work does not land and waits for a human. The
  difference is what happens to the *unverifiable* case: CodeAF queues it, SoFact's
  FR-001 refuses to let it exist in the first place ("no oracle, no clause"). The
  routing rule is the weaker of the two, but it is a real, shipped answer to the same
  problem, and it is worth recording that a production system reached for a queue.
- **Claim 3 is the sharpest thing in the source, and it is a direct instance of what
  FR-140 forbids.** SoFact's whole §2.4 argument is that the authority to resolve an
  open question must sit with the human, because a producer that can answer its own
  question has quietly widened its own specification. `do` does the opposite by design:
  it takes the best answer and records the assumption. That is a defensible engineering
  trade for CI and cron — an unattended run has nobody to ask — but it is the exact
  inversion SoFact's first rule exists to prevent, and it is stated plainly rather than
  hidden. Cite it as the counterexample, not as a gap in SoFact.
- **Claim 5 is a second, cheaper oracle SoFact already knows about (F7).** "Graded by
  the check it already had to pass" is oracle-as-acceptance-criterion, and SoFact's
  contracts do the same thing. The novel part is the **feedback loop**: the check's
  outcome moves the per-seat model weights. SoFact records a verdict and stops; nothing
  in the pipeline reads a verdict distribution back into a dispatch decision. That is
  FR-021–023's shape (measurement feeding a policy) applied to model choice rather than
  autonomy level, and it is the one mechanism here with no SoFact counterpart.
- **Claim 2 is the completion-reason capability FR-140 wants and no wired adapter
  reliably has.** `HarnessSpec.completion_reason_path` exists, `dsh` "emits a structured
  `turn/end` reason" and `pi` "emits nothing" (the asymmetry `harness.py` records). A
  subharness that is *marked incomplete* is a third shape: the producer reports a
  non-completion explicitly. Whether CodeAF's `--json` output carries a machine-readable
  incomplete state is the one probe that would decide its adapter value, and it is not
  answerable from the README.

## Concerns / information quality

- **A product README, read and archived but not installed or executed.** Every claim is
  the vendor's. Nothing here was measured on this tree, so this entry cannot move a
  SoFact decision — it can only queue probes.
- **The benchmark is self-published and self-serving.** CodeAF is first on a benchmark
  it chose, over harnesses it named, on a model it chose. The verifiers are DeepSWE's,
  which is a genuine mitigation, but "graded by the official verifiers" is a claim about
  the grading, not about the harness selection or the model. The paper (`Pareto
  Crewing`) is a PDF in the repo and was **not** read.
- **The performance table compares against `claude` and `opencode` with no method
  stated in the README** beyond a link to `docs/benchmarks/performance`, which was not
  fetched. The 21x/24x figures are the kind of number that is easy to make true by
  choosing what to measure.
- **The star count was not captured** — the repository was reached through the
  operator's link, not a search that would have reported one. Do not cite a star figure
  for this project from this entry.
- **Status is "early preview"** by its own badge, and it says so twice. Treat the
  command surface as moving.
- **Telemetry defaults on, including the Model Pool**, which sends computed model
  numbers from every install by default. SoFact has no telemetry and this is recorded
  only because a harness that egresses by default is a fact an isolation probe would
  need to know — [S21] measured the same property in `dsh` (egress to
  `harness-telemetry.deepseeksvc.com`).
- **The `pi` and `claude` cost multipliers cannot be checked from here.** They are the
  most quotable numbers in this source and the least verifiable: reproducing them means
  running DeepSWE, which needs the benchmark's issues, its verifiers, and a DeepSeek
  V4 Flash seat. Queued, not adopted.
