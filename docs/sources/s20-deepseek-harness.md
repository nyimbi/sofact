---
id: S20
slug: deepseek-harness
title: "DeepSeek Harness (`dsh`) — plugin harness with Python SDK and event-sourced sessions"
publisher: DeepSeek AI
type: product-doc / system
url: https://deepseek.com/harness/en/
repo: https://github.com/deepseek-ai/deepseek-harness
docs: https://deepseek-harness.github.io/deepseek-harness/
license: MIT
version_at_retrieval: "0.1.0-rc.8 (tag dsh-v0.1.0-rc.8) — **superseded: the installable version is 0.1.5-rc.1** ([S21])"
released: 2026-08-13
retrieved: 2026-09-12
verification: reported — **partially superseded by [S21] (measured)**
confidence: medium
superseded_by: [S21]
tags: [harness, plugin-architecture, sandbox, session-log, python-sdk, goal-mode, subagents]
---

> **Read [S21] first.** This entry was assembled from documentation and search
> results. Four of its claims were subsequently falsified by direct execution:
> the version, the integration surface (it is a *subprocess* SDK, not in-process),
> the profile names (runtime modes were conflated with profiles), and the
> star-count retraction (the counts are real). [S21] is the authoritative record;
> this entry is retained for provenance and for its architecture reading.
---

## Precis

`dsh` is DeepSeek's open-source agent harness (MIT, developer preview from
2026-08-13). Its organising idea is **"everything is a plugin"**, built on the
Cordis meta-framework: models, tools, skills, sessions, **sandboxes**, storage,
**the agent loop**, scheduling, and the UI are all replaceable in configuration
without forking. Press framed it as an open-source rival to Claude Code.

Two properties make it directly relevant to SoFact's build phase: it exposes a
**Python SDK**, and its session state is an **append-only event log**. Both were
confirmed by execution in [S21] — and a third property turned out to matter more
than either: **the plugin composition can be authored and mounted at runtime**, by
the agent itself ([S22]).

### Pages consulted

- `https://deepseek.com/harness/en/` — official product page (plugin claim,
  runtime modes, session-log claim).
- `https://github.com/deepseek-ai/deepseek-harness` — official README.
- `https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.0-rc.8` —
  release notes (goal/plan multimodal input, subagent Profile Bundles).
- `https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/core`
  — core subsystem reference (session event taxonomy, agent lifecycle).
- `.../docs/user/guide/python-sdk.md` — Python SDK tutorial.
- `https://deepseekharness.io/what-is-deepseek-harness` — **third-party SEO site,
  not official.** See Concerns.

## Key claims (reported, not independently verified)

### Architecture

- Every capability is a plugin: models, tools, skills, sessions, **sandboxes**,
  storage, **loops**, scheduling, UI.
- `packages/` contains `core`, `llm`, `mcp`, `sandbox`, `context`, **`plan`**,
  **`goal`**, and others — i.e. **goal mode is a first-party subsystem**, not only
  a third-party extension.
- Extending means *mounting a plugin*, "not forking the project".
- Built on Cordis; the design paper is cited as arXiv **2608.25512**
  (*A Programming Paradigm for Spatiotemporal Composability*) — **not verified**.

### Session log — the capability that matters most here

- "Everything the model sees is recorded in an **append-only session log**:
  system prompts, reasoning, tool calls and results, subagent scheduling, and
  every context injection."
- **Resume, fork, search, and replay all operate on the same event stream.**
- Core reference documents a typed event taxonomy — `SessionEventMap` with
  `turn/start`, `turn/end`, `step/start`, `step/end`, `user/message`,
  `assistant/chunk`, `assistant/message`, **`tool/call`**, **`tool/result`**,
  `steering/message`, `todo/write`, `request/header`. Every entry carries a
  monotonic `seq` and `time`.
- The LLM history is *derived* from the log (`deriveMessages()`), not stored
  separately — so the log is the single source of truth.
- Persistence backends: **JSONL** and **SQLite**, with a `session/flush`
  checkpoint and crash recovery.

### Runtime modes

Standard (full toolset, incl. skills, planning, **goals**, subagents, workflows),
Code (tools via a Code Mode SDK), Minimal (two tools, for benchmarking models),
Creator (runtime inspection, plugin authoring).

**Correction from [S21].** These are **runtime modes, not profiles** — the two axes
were conflated here. The actual CLI profiles are `sdk` and `headless`;
`minimal`/`code` are not profiles. In the shipped 0.1.5-rc.1 runtime the `sdk`
profile boots and the `headless` profile does not (a missing package in the
packaged wheel).

### Subagents — "harness of harnesses" is native

- "**Claude Code and Codex subagents [are] installable on demand as Profile
  Bundles**, with **non-interactive permission modes** and named instances."
- Child agents inherit the parent's composition via `composeFrom()` — the *same*
  plugin instances, not a re-resolution.

### Python SDK (decisive for SoFact)

```python
from deepseek_harness import DeepSeekHarness

with DeepSeekHarness(
	provider="deepseek-official",
	model="deepseek-v4-flash",
	max_tokens=49_152,
	cwd=str(workspace),
	session_root=str(sessions),
	cordis=str(config),
) as harness:
	result = harness.run(
		"Inspect the repository and fix the failing tests.", session_id="example-001"
	)
```

- `pip install deepseek-harness-sdk`; Python ≥ 3.10; **bundled runtime, no system
  Node.js required**.
- **Correction from [S21]:** the SDK drives the harness as a **subprocess over
  newline-delimited JSON-RPC on stdio** — *not* in-process, as claimed in the
  mapping table below. It bundles a ~260 MB runtime binary. The surface is
  narrower than this entry implied, which strengthens rather than weakens the
  adapter argument (§8.6). `DeepSeekHarnessConfig` takes `base_url` and `api_key`
  as first-class parameters, so any OpenAI-compatible endpoint — including a local
  ollama — serves as the model, with no DeepSeek dependency.
- Reusing a harness + session id preserves the session-owned persistent Bash
  process (cwd, exports, shell functions). Fresh id for independent tasks.
- Platform support: **Linux x64, Linux arm64, macOS 14+ on arm64.**

### Sandboxing — and the warning that comes with it

- Sandbox is a *plugin*, so the boundary is chosen rather than inherited.
- The minimal example composition uses **`danger-full-access`** and its own docs
  say: "Run it only inside a disposable checkout or container: Bash and the editor
  can modify any path allowed to the runtime process." Sandbox facts are logged as
  runtime context. **The default is not a boundary.**

## Why it matters for SoFact

**It supplies, natively, most of what SoFact's build phase was going to have to
engineer.** Mapped to requirements:

| SoFact requirement | `dsh` mechanism |
| --- | --- |
| FR-058 adapter interface | Python SDK + JSON-RPC agent API (**subprocess on stdio**, not screen-scraping — [S21]) |
| FR-136 contract → goal plan | first-party `goal` package; `/goal` and `/plan` commands |
| **FR-138 termination ≠ verification** | typed `tool/call` / `tool/result` / `turn/end` events give SoFact the *evidence*, independent of the harness's own completion claim |
| FR-139 contract integrity | append-only log + `request/header` records what the model was actually given |
| FR-141 worktree isolation | session `fork` and `resume` over the same event stream |
| FR-142 wave scheduling | **scheduling is a plugin** |
| FR-143 telemetry | the session log *is* the telemetry: monotonic `seq`, per-event timestamps, JSONL or SQLite |
| FR-059 sandboxing | sandbox plugin — but see the `danger-full-access` warning |
| NFR-009 determinism | **replay** on the same event stream |
| FR-132 model tiering | model routes are plugins |
| FR-049 model abstraction | bring any model; DeepSeek is a default route, not a requirement |

**The structural point.** SoFact's P5 was specified as delegating to a goal-mode
harness (S18). `dsh` goes further: it exposes the *loop* as a replaceable plugin and
hosts *other harnesses as subagents*. That means SoFact does not have to invent the
outer-loop/inner-loop seam — **the platform already has it**, and a subagent is
literally a harness inside a harness. SoFact's job shrinks to: compile contracts
into goals, dispatch sessions, and verify against the event log.

**FR-143 stops being an adapter burden.** `pi` (S19) offers a JSONL transcript at a
known path; `dsh` offers a documented, typed, replayable event contract with a
derivation rule. For a product whose entire differentiator is *evidence about what
happened*, that is a large difference in kind, not degree.

## Concerns / information quality

- **Developer preview with an explicit breaking-changes warning.** The project's
  own words are in all caps: "**THERE WILL BE COMPATIBILITY-BREAKING CHANGES.**"
  This is the decisive risk for an *unattended multi-day* factory (F5, S08): not
  that the harness is immature, but that the interface can move underneath a
  long-running build. Pin the version.
- **"Everything is a plugin" cuts both ways.** To use sandbox, loop, or scheduling
  plugins *well*, one may have to author Cordis plugins — which means SoFact writes
  harness code after all, contradicting the harness-reuse non-goal (§1.5, F6/S10).
  Mitigation: v1 uses only existing compositions and authors no plugins; a missing
  plugin is a documented capability gap, per D15.
- **The default sandbox is `danger-full-access`.** Must not be mistaken for a
  boundary (FR-019). The sandbox plugin must be explicitly configured and *proved*.
- ~~**Credibility anomaly, flagged.** The GitHub scrape reports **212,481 stars
  and 24,945 forks** … more likely a scraping artifact than a fact. **Do not cite
  these numbers.**~~ **Retracted — [S21].** The authoritative GitHub API confirms
  **220,569 stars / 26,126 forks**, created 2026-08-13, pushed 2026-09-11. The
  trajectory is extraordinary and real. The lesson transfers: the curated
  `awesome-deepseek-harness` list shows **38,238** for the same repo, so
  third-party badge data is unreliable in *both* directions. Cite the API, or
  nothing. Recorded in [S22].
- **Default composition egresses — measured [S21].** `session-telemetry-otel`
  ships with `mode` defaulting to `FEEDBACK_ONLY` and an exporter URL of
  `https://harness-telemetry.deepseeksvc.com/v1/logs`; a run also wrote
  `<DSH_HOME>/.anonymous-user-id`. Confirms FR-152: neither `--offline` nor the
  default profile is an FR-019 egress boundary.
- **Session log is zstd-compressed — measured [S21].** The append-only JSONL lives
  at `session.v3.jsonl.zstd`; readers must decompress. Implementation detail for
  FR-151.
- **Mixed-provenance bundle.** The search results interleave two official DeepSeek
  domains with `deepseekharness.io`, a third-party SEO page. Its claims are
  secondhand, including "DeepSeek quadrupled its prices" for V4-Pro (attributed to
  The Next Web). Pricing must be confirmed against DeepSeek's own terms before use
  in any cost model (cf. S13).
- **arXiv 2608.25512** (Cordis) is asserted but unverified.
- **Model naming is already stale.** The brief specified *DeepSeek-V3*, but the SDK
  example defaults to `deepseek-v4-flash`, and the catalogue now lists V4-Pro,
  V4.1-Flash, etc. V3 appears only via third-party routes (HuggingFace, OpenRouter).
  The model named in the brief is not the current one.
- **Now exercised — see [S21].** The harness boots, completes a genesis task
  unattended with a local model, and emits a 63-record typed event log. But the
  `goal` package was **not entered**: zero goal-typed events, and the model used
  its `todo_write` tool instead. Goal mode is *available, loaded, and
  model-discretionary*. Whether the continuation loop works is **still unproven**,
  and the open question has changed shape — from "does `dsh` have goal mode"
  (yes) to "who enters it, and can SoFact force entry" (unanswered).
