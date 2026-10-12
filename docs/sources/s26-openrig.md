---
id: S26
slug: openrig
title: "OpenRig — a rig wraps your harnesses"
type: product-doc
verification: url-verified (raw README fetched and read in full this session)
confidence: medium
accessed: 2026-10-12
retrieved_via: "raw.githubusercontent.com/mvschwarz/openrig/main/README.md; GitHub HTML page"
archive: archive/s26-openrig-README.md
url: https://github.com/mvschwarz/openrig
relates_to: [S18, S20, S22, S23]
---

**Why this entry exists.** OpenRig is a *second, independent implementation* of the
same architectural position SoFact occupies — a layer above the harnesses rather than
a harness. It is the nearest neighbour in the ledger to SoFact's FR-058 adapter
position, and it was named by the operator as a source to learn from.

## Precis

"A harness wraps a model. A rig wraps your harnesses." OpenRig is a local daemon +
CLI + TUI + MCP server, built on **tmux**, that runs a declarative team of coding
agents drawn from Claude Code, Codex and Pi. Topology is YAML (`RigSpec`: pods,
edges, continuity policies, culture file). State lives under `OPENRIG_HOME`
(`~/.openrig`): SQLite, plugin resources, context-usage and provider-usage, a
context library, bundle imports with a `bundle-audit.jsonl`. It is Apache 2.0, Node
22/24 only, Windows via WSL2 only.

Key abstractions, in its own words: **Seat** (a stable role/address such as
`dev-build@starter`, "whose occupant may change while identity persists"), **Pod**,
**AgentSpec**, **RigBundle** (portable archive with SHA-256 integrity), **Culture**
(`CULTURE.md`), **Discovery/Adopt** (fingerprinting and managing existing tmux
sessions), **Snapshot/Restore**.

## Key claims

1. **"YOLO is off by default."** A seat with no permission policy launches with a
   per-launch *team default*: ordinary `rig` commands, project reads and common tests
   without prompting, while lifecycle commands (`rig up`/`rig down`) still prompt.
   Full bypass is a separate, explicitly selected policy, and
   `rig seat set-permissions` records an audited choice.
2. **Permission changes follow a real user answer.** Broader access "ships as a
   separate opt-in bundle," and the agent "requires your actual answer before" adding
   remembered rules. No answer preserves the stricter default.
3. **`OPENRIG_HOME` alone does not isolate provider configuration.** The README states
   this outright: provider files (`.claude.json`, `CODEX_HOME/config.toml`) are
   separate from instance state, and startup writes them.
4. **Restore reports per-node outcomes**: `resumed`, `fresh-primed`,
   `awaiting-decision` ("the original conversation can't resume; choose `--fresh`"),
   `attention_required`, `failed`. A restore that could not resume a node *says so*
   rather than reporting a clean restore.
5. **Discovery and adopt, not fresh-start-only**: `rig discover` fingerprints existing
   tmux sessions and `rig adopt` brings them under management.
6. Telemetry payloads "exclude prompt text and tool arguments."

## Why it matters for SoFact

- **The nearest-neighbour falsifier.** S22 found that every mechanism SoFact treats as
  differentiated already exists free in the `dsh` plugin ecosystem. OpenRig is the same
  result for the *orchestration* layer: declarative multi-harness topologies, budgets,
  snapshots, a durable audit log, and per-seat permission policy all exist here. The
  honest reading is that SoFact's differentiation cannot be "it orchestrates harnesses."
  It has to be the verification discipline — no oracle, no clause; a verdict over
  evidence the producer did not author.
- **Where OpenRig stops is exactly where SoFact starts.** Nothing in this README is a
  claim about whether the work is *correct*. There is no oracle, no clause, no verdict,
  no falsifiable acceptance criterion. "Review the exact candidate artifact" is a human
  reading a diff. That is the boundary, and it is worth stating because it is the same
  boundary S22 drew around the `dsh` plugin ecosystem's "evidence gates."
- **Point 3 is a hazard SoFact shares and should check.** SoFact's own harness specs
  write `CLAUDE_CONFIG_DIR` and `OPENCODE_DB` for isolation. OpenRig's warning is that
  an instance-state variable does not relocate *provider* configuration — a harness
  still reads and writes the user's real provider files. SoFact's `CLAUDE_SPEC` sets
  `CLAUDE_CONFIG_DIR`, but the opencode spec's `OPENCODE_TEST_HOME` was measured to
  matter only alongside `--standalone`. The general lesson: **an isolation variable is
  not an isolation boundary until something measures that the provider honoured it.**
- **Point 4 is a reporting pattern worth copying.** SoFact's `StepOutcome` already
  distinguishes `NOT_DISPATCHED` / `COMPLETED` / `FAILED` / `BUDGET_EXHAUSTED`, and
  NFR-024 forbids rounding an absent observation into a present one. OpenRig's
  `awaiting-decision` is a fifth state SoFact does not have: *the work cannot be
  resumed, and continuing requires a human choice*. SoFact's equivalent gap is a step
  whose session left no record — currently indistinguishable from one that never ran.

## Concerns / information quality

- A **product README**, so every claim is the vendor's own positioning. Nothing here
  was executed; no version was installed. The architectural claims (tmux-based, SQLite,
  daemon) are corroborated by the document's own command surface but not measured.
- **Star count not captured** in this session; the repository was reached through the
  operator's link, not through a search that would have reported one.
- The project is at 0.6.0 with a 0.5.9 layout migration described as "agent-operated."
  Its own README notes automated tests do not yet run on WSL2, which is a
  self-reported coverage gap.
- **No verification claims to evaluate.** This source cannot move any SoFact decision
  about verification, because it makes no verification claim. It is cited for
  architecture and isolation, and for the negative result in "Why it matters."
