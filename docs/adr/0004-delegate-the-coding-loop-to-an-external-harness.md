# 0004 — Delegate the coding loop to an external harness

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

SoFact's purpose is to turn an imagined product into a verifiable one. Writing code
is the obvious middle of that pipeline, and the temptation is to build a coding loop:
edit, run, read the error, revise.

But `src/sofact/` contains no coding loop, and the codebase has no mechanism to hand
work to one either. Establishing that took an executed probe rather than a reading
of documentation.

The goal-mode harness landscape was surveyed and measured:

- **`pi`** — the harness this project is developed under; goal-mode interface verified
  from source (`/goal`, `create_goal`/`get_goal`/`update_goal`, and `update_goal`
  accepts only `status: "complete"`).
- **`dsh`** (DeepSeek harness) — MIT, very widely starred; three different version
  numbers in play (`0.1.0-rc.6` globally, `0.1.5-rc.1` latest, `0.1.5-rc.1` bundled);
  **all seven releases are pre-releases**; `--profile headless` fails out of the box
  in the bundled macOS runtime (missing `@deepseek-ai/dsh-session-title-llm`); no TUI
  (`@deepseek-ai/dsh-tui` is a 404, and the `tui` profile advertised in help text does
  not exist); and default telemetry exports to
  `https://harness-telemetry.deepseeksvc.com/v1/logs` [S20, S21].
- **`oh-my-dsh` / `omp`** — "oh-my-dsh" does not resolve to a single repository (≥8
  candidates, the most prominent declaring no licence), and `omp` is a detached `pi`
  fork. The name does not identify a referent [S22, S23].

A census of the harness plugin ecosystem found `gate` mentioned 258 times, `verif*`
155, `bench` 135, `evidence` 80, and **`elicit` zero times** — an ecosystem densely
populated with checking and entirely empty of interrogation [S22].

## Decision

SoFact **contains no coding loop and no coding harness**. The loop is delegated:

- The **inner loop** (edit, run, revise) belongs to an external goal-mode harness.
- The **outer loop** (contract, goal plan, dispatch, collect, verify, integrate)
  belongs to SoFact.
- The boundary is **out of process**. SoFact is not a plugin of any harness — it is an
  independent control plane, and D16 resolves to *no*. A thin *client* plugin that
  holds no authority is a possible v2 distribution surface, not an architecture.
- The first adapter targets `dsh`; `pi` is the second adapter and the interface test
  (D11). The rationale is structural and does not depend on commercialisation.
- **v1 writes zero harness plugins** (D15 narrowed): the adapter consumes documented
  CLI surface, so there is nothing of ours to break when the harness changes.

## Evidence

```console
grep -rnE "create_subprocess|asyncio\.subprocess|HarnessAdapter|dispatch\(" src/
```

returns nothing. The absence is structural, not a matter of discipline: no module in
`src/sofact/` can start a harness process.

A decompressed `dsh` session log was census'd at 63 records with **zero goal-typed
events**, and the `sdk` profile exposes no `user-questions` tool [S21]. The second
finding is why FR-145 exists: elicitation is SoFact's job because the harness
demonstrably does not do it.

## Consequences

- **SoFact cannot be evaluated on code quality alone**, because it does not generate
  code. Its measurable claim is narrower and checkable: that no clause without an
  oracle ever receives autonomy, and that a producer's completion claim never becomes
  a verdict. This is by design — the narrower claim is the one that can be tested.
- SoFact inherits a dependency whose failure modes are not its own. `dsh` headless is
  broken out of the box, its goal continuation loop is **unproven** (zero goal-typed
  events in the census), it ships only pre-releases, and it phones home by default.
  The adapter must therefore verify capability by *attempting* it rather than by
  reading `--help` (FR-148) — the stale `tui` profile in the help text is the proof
  that harness documentation is not an oracle.
- The boundary must be one-directional. A harness may declare completion; it may not
  grant autonomy, spend budget, or pass a gate. Those are SoFact's, and the gate is
  the human's — confirmed at n=2 harnesses (FR-140).
- Because SoFact does not build a coding loop, `pi` remains a viable second adapter
  chosen on structural grounds. D11 survives D17 (commercialisation declined) — the
  grounds were never commercial.
