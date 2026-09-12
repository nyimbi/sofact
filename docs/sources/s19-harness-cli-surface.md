---
id: S19
slug: harness-cli-surface
title: "Host harness CLI surface (`pi` — invocation, isolation, telemetry flags)"
type: primary / local-inspection
evidence: "`pi --help`, `pi list`, live environment on this machine"
path: /opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent
retrieved: 2026-09-12
verification: content-verified
confidence: high
tags: [harness, adapter, isolation, telemetry, sandbox, reproducibility, prompt-injection]
---

## Precis

`pi` as measured, and one measured claim in [S19] corrected. The absence of any
structured completion stands. The claim that `pi` reports no usage does not: recorded
against an earlier version, it is false for 0.85.1, where an assistant `message` record
carries `usage: {input, output, cacheRead, cacheWrite, reasoning, totalTokens, cost}`.
The adapter was corrected by editing one row of its spec table, and the `telemetry` probe
row now reads `confirmed (observed 3)` against a real invocation — see the note under
Telemetry below.

Second `content-verified` entry, and the second non-web one. `pi`'s own CLI was read
directly (`pi --help`, `pi list`) to answer a question SoFact depends on: **can a
harness be driven, restricted, and observed entirely from outside, by a program?**
For this harness the answer is substantially yes, through documented flags rather
than code changes.

This matters because it converts several SoFact requirements from "things the
adapter must somehow achieve" into "flags to pass", and because it is primary
evidence that the adapter boundary (FR-058) is achievable without forking.

## Key claims (observed)

### Drivability

- `--mode <text|json|rpc>` — machine-readable output modes. **This is the adapter
  interface.** (Semantics of `rpc` are not documented in `--help`; see Concerns.)
- `--print, -p` — non-interactive: process prompt and exit.
- `--append-system-prompt <text>` — repeatable. Lets SoFact inject the frozen
  contract into the system prompt.
- `--name`, `--session-id <id>` (creates if missing), `--session-dir <dir>`,
  `--session <path|id>`, `--fork <path|id>` — deterministic session addressing.
- `--continue/-c`, `--resume/-r` — session continuation.
- `--no-session` — ephemeral run.
- `--export <file>` — export a session to HTML.

### Restriction (the sandbox surface, FR-059)

- `--tools, -t <names>` — allowlist across built-in, extension, and custom tools.
- `--exclude-tools, -xt <names>` — denylist.
- `--no-tools`, `--no-builtin-tools` — disable all, or all built-ins only.
- `--offline` (= `PI_OFFLINE=1`) — disable startup network operations. **Egress
  denial is a flag.**
- `--no-context-files, -nc` — disable `AGENTS.md` / `CLAUDE.md` discovery.
- `--approve,-a` / `--no-approve,-na` — trust / ignore project-local files.
- `--no-extensions, -ne`, `--no-skills, -ns`, `--no-prompt-templates, -np`,
  `--no-themes` — strip ambient configuration for a hermetic environment.
  `--extension/-e`, `--skill`, `--prompt-template`, `--theme` explicitly load.

### Model and depth control (FR-132 tiering)

- `--provider`, `--model <pattern>` (`provider/id`, optional `:thinking` suffix),
  `--models`, `--list-models [search]`.
- `--thinking <off|minimal|low|medium|high|xhigh|max>`.
- **`--model` is resolved against `pi`'s own registry, not against the provider.** A model
  id that ollama serves but `pi` does not list is refused outright — measured at 0.85.1:
  `--model qwen3.6-coding:latest` (present in `ollama list`, 19 GB) exits 1 with
  `Error: Model "qwen3.6-coding:latest" not found. Use --list-models to see available
  models`, and writes no session record at all. The `ollama` provider advertises seven
  models, so a local build must name one of them (`qwen3.6:35b-mlx` was used for the live
  end-to-end run). Consequence for FR-132's model tiering: a tier is a *harness* registry
  entry, and the probe is what catches a bad one, because the check happens in the child.

### Introspection and lifecycle

- `pi list` — installed packages with resolved paths.
- `pi install <source>` / `remove` / `update [source|self|pi]` / `config [-l]`.
- Package capability is **declarative and machine-readable** in `package.json`:
  `"pi": { "extensions": [...], "skills": [...] }` (confirmed in `pi-goal`).
- **Extensions register their own CLI flags.** `--help` prints a separate
  "Extension CLI Flags" section; e.g. `--plan` (read-only plan mode) comes from an
  extension, and `pi-lens` contributes ~20 flags.

### Telemetry

- The session is a **JSONL file at a known path**, exposed as `PI_SESSION_FILE`
  (observed live), under `<session-dir>/<project-slug>/<timestamp>_<uuid>.jsonl`.
- This means **telemetry is readable by SoFact without harness cooperation**
  (FR-143) — the transcript is a file, not an API.
- **Re-measured 2026-09-12 at 0.85.1** (corrects the first bullet, which is a claim
  about the invocation shape rather than the record's contents). Two corrections:
  with an explicit `--session-dir <dir>`, the record is a **direct child** of that
  directory, `<iso-timestamp>_<session-id>.jsonl`, with no project-slug level; and an
  assistant `message` record carries a **full usage block** —
  `message: {role, content, provider, model, usage, stopReason}` with
  `usage: {input, output, cacheRead, cacheWrite, reasoning, totalTokens, cost}`.
  Top-level keys are `{cwd|id|message|modelId|parentId|provider|thinkingLevel|timestamp|type|version}`
  depending on record type; observed types were `session`, `model_change`,
  `thinking_level_change`, `message`.
- **Consequence for the adapter:** spend *is* attributable for `pi`, so a `pi`
  dispatch can carry a token count after all. The quantity that matches `dsh`'s
  `data.usage.outputTokens` is `message.usage.output` — the same measure under a
  different key, which is precisely why the path is a spec row and not code.

### Installed capabilities on this machine

`npm:@ollama/pi-web-search`, `npm:pi-goal`, `npm:pi-plan`, `npm:pi-lens`,
`npm:pi-hermes-memory` — i.e. research, goal mode, read-only planning, diagnostics,
and memory all already exist as installed extensions.

## Why it matters for SoFact

**R25 is largely dissolved; FR-135 changes shape.** A candidate harness demonstrably — goal mode (S18), unattended operation,
budget control, tool restriction, egress denial, model tiering, session addressing,
and file-level telemetry. The matrix is no longer a research question so much as a
**discovery and verification** exercise.

**FR-135 must become runtime discovery, not a document.** Because extensions
contribute flags, any statically written capability matrix goes stale the moment an
extension is added or removed. SoFact must enumerate capabilities from the live
installation (`pi list`, the `pi.*` manifest fields, the extension-flags section of
`--help`) and treat the matrix as an observed snapshot with provenance.

**Three requirements get native mechanisms:**

| Requirement | Mechanism |
| --- | --- |
| FR-059 harness sandbox, no credentials/oracle access | `--tools`/`--exclude-tools`/`--no-builtin-tools` + `--offline` + cwd scoping |
| FR-143 telemetry | `PI_SESSION_FILE` JSONL transcript, plus `--mode json` |
| NFR-009 determinism / idempotence | hermetic flags (`--no-skills`, `--no-context-files`, `--no-extensions`) strip ambient variation that would otherwise make oracle strength non-comparable across runs |

**A named injection vector (new).** A module under construction can write an
`AGENTS.md` or `CLAUDE.md` into its own repository, and the harness will read that
file as *instructions*. That gives the producer a documented channel to steer its
own builder — including toward satisfying the evaluator rather than the
requirement (S15, R22). SoFact must therefore invoke the harness with
**`--no-context-files`** during P5, and treat any project-local instruction file as
untrusted input. This is a concrete, mechanically available mitigation for a threat
that would otherwise only be abstract.

**Gate evidence has a native format.** `--export <file>` produces a
human-readable session export, which is exactly the artifact shape wanted for a
human gate (P2/P3/P8) and for the escape-attribution trail (§9.6).

## Concerns / information quality

- **The decisive question is unverified.** `--help` documents `--print` *and*
  documents `/goal`, but **nothing here proves that goal mode loops unattended
  under `--print`.** That single interaction decides whether FR-145 and the whole
  delegated-P5 design work as specified, and it has not been tested. It is the
  highest-value probe in M0 (§20.3 item 6) and should be run first.
- **`--mode rpc` semantics are undocumented** in `--help`. Whether RPC is
  bidirectional, whether it supports goal lifecycle events, and whether it is
  stable across versions are all unknown. Treat RPC as promising, not established.
- **`--offline` is scoped to *startup* network operations.** That is not the same
  as a full egress boundary, and it must not be represented as one. FR-019 requires
  an enforced boundary; `--offline` is a convenience, not the boundary.
- **Flag surfaces are unstable by construction.** Extension-contributed flags mean
  the surface varies per installation and per version. Any adapter coupled to
  specific flags inherits that volatility — an argument for capability discovery
  plus a small, well-tested invocation core.
- **`n = 1` again.** One harness, one version, inspected once, on macOS. Nothing
  here establishes that this pattern generalises to other harnesses, which is the
  assumption D11 must test.
- **Primary and local.** Not peer-reviewed, not independent, and no part of a
  recommendation. It is one well-documented object of study.
