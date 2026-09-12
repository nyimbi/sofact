---
id: S21
slug: dsh-probe-executed
title: "`dsh` 0.1.5rc1 executed under probe — measured behaviour of the primary harness"
publisher: measured locally (SoFact probe)
type: execution-record
url: (n/a — local probe)
repo: https://github.com/deepseek-ai/deepseek-harness
docs: https://deepseek-harness.github.io/deepseek-harness/
license: MIT
version_at_retrieval: "**two distinct installs.** npm-global CLI on PATH `@deepseek-ai/dsh@0.1.0-rc.6` (`--version` → `0.1.0-rc.6`); npm registry `latest` = `0.1.5-rc.1`; Python SDK `deepseek-harness-sdk` 0.1.5rc1 bundling runtime `0.1.5-rc.1`. See Correction 5."
released: 2026-08-13
retrieved: 2026-09-12
verification: content-verified
confidence: high
tags: [harness, probe, measurement, session-log, goal-mode, plugin-architecture, egress]
supersedes_claims_in: [S20]
---

## Precis

This entry records what `dsh` **did** on this machine, not what it documents. It is
the first entry in the ledger that is a measurement rather than a reading, and it
resolves the highest-value open question in `docs/sources/README.md`. It also
**corrects four claims in [S20]**, which was assembled from documentation and
search results.

Method: a throwaway venv (`/tmp/dshprobe/.venv`, Python 3.13.11), a scratch
`DSH_HOME` (`/tmp/dshprobe/home`, seeded with a copy of the real `settings.yaml`),
and a scratch git repo (`/tmp/sofact-probe-repo`, empty at probe start). Model was
**local ollama** (`qwen3.8:27b-mlx`) over an OpenAI-compatible endpoint — no cloud
API key was used. Three probe scripts (`probe1.py`–`probe3.py`).

## Corrections to [S20]

| [S20] said | Measured |
| --- | --- |
| Version `0.1.0-rc.8` | **Not what installs**, but the replacement figure in this entry was itself wrong — see Correction 5 below. The installable pair is npm CLI `0.1.0-rc.6` (on PATH) and SDK runtime `0.1.5-rc.1`. |
| Integration surface is "**in-process**, not screen-scraping" | **Wrong.** The SDK is a *subprocess* SDK: PyPI describes it as "Python **subprocess** SDK for driving DeepSeek Harness over **newline-delimited JSON-RPC on stdio**". It ships a **260 MB self-contained runtime binary** (no system Node). The surface is narrower and cleaner than claimed — which *strengthens* the adapter argument in §8.6. |
| Runtime modes: "Standard / Code / Minimal / Creator" | Those are **runtime modes, not profiles**. Profiles are `sdk` and `headless`; `minimal`/`code` are not profiles. [S20] conflated the two axes. |
| "212,481 stars … more likely a scraping artifact. **Do not cite these numbers.**" | **Retracted.** The authoritative GitHub API reports **220,569 stars / 26,126 forks**, created 2026-08-13, pushed 2026-09-11. Extraordinary, and real. (Note the converse hazard: the curated `awesome-deepseek-harness` README displays a **38,238** badge for the same repo — third-party star counts are unreliable in *both* directions. Cite the API, or nothing.) |

Also corrected: **all 7 PyPI releases are pre-releases** (`0.0.0.dev0`, `0.1.0rc6`,
`0.1.0rc7`, `0.1.1rc1`, `0.1.2a3`, `0.1.2rc1`, `0.1.5rc1`). The project has **never
shipped a stable release**. This permanently strengthens R26. Separately, the PyPI
name `deepseek-harness` is a **different, unrelated package** by another author — a
naming hazard for anyone not using the `-sdk` suffix.

### Correction 5 — this entry confused three version numbers (added after S21)

A second pass found that this entry's own version claim was wrong in the same way it
accused [S20] of being wrong. There are **three** different version numbers in play,
and only one of them is "the version of `dsh`" for any given question:

| What | Version | How to see it |
| --- | --- | --- |
| **npm-global CLI on `PATH`** | **`0.1.0-rc.6`** | `dsh --version`; `npm ls -g \| grep dsh`; `@deepseek-ai/dsh` in `/opt/homebrew/lib/node_modules` |
| npm registry `latest` dist-tag | `0.1.5-rc.1` | `npm view @deepseek-ai/dsh dist-tags` (`next` `0.1.5-rc.2`, `alpha` `0.1.5-alpha.2`) |
| **Python SDK's bundled runtime** | **`0.1.5-rc.1`** | the 260 MB binary under `deepseek_harness_runtime/runtime/`; `<binary> --version` |

The installs are **independent**: the global npm CLI has its own `node_modules` and
its own `~/.dsh`; the SDK ships a self-contained binary with its own `DSH_HOME`.
Consequences for the measurements recorded above:

- The **`--dump-config` plugin inventory (352 lines) came from `0.1.0-rc.6`**, the
  npm CLI — not from 0.1.5rc1 as this entry's front matter claimed.
- The **`headless` boot failure came from `0.1.5-rc.1`**, the SDK's bundled runtime
  (the stack trace goes through `pkg-sea` VFS paths).
- `dsh --help` was read from **both**; their example blocks are identical (see
  Correction 6).
- The `goal`, `goal-round-driver`, `command-goal`, `tool-goal` packages are
  therefore confirmed present **in `0.1.0-rc.6`**, and the SDK runtime's `sdk`
  profile resolves them too.

This is the [S13] lesson applied to SoFact's own probe work: *a version string is a
measurement, and a dist-tag is not one.* The generalisable warning is that an npm
registry query and an installed binary can disagree by five releases, in a project
where every release is a pre-release — so R26's "pin the version" is not
satisfiable by pinning a *tag*; the composition must be pinned by installed artifact
and checked at runtime (FR-148, FR-154).

### Correction 6 — `dsh` has no TUI; `--help` advertises a profile that does not exist

`dsh --help` prints, in **both** 0.1.0-rc.6 and 0.1.5-rc.1:

```text
Examples:
  dsh --profile tui --patch ./extra.yml      boot a custom profile with one extra overlay
  dsh --profile tui --resume <session>       arguments after the launcher flags reach the app
  dsh plugin --profile tui add <package>     install a plugin into the tui profile
```

**There is no `tui` profile, and no TUI.** Evidence:

- `dsh --profile tui --dump-config` fails hard:
  `profile "tui" does not exist; create it with 'dsh plugin --profile tui add <package>'`.
  (The control, `--profile web`, composes and exits cleanly.)
- No `@deepseek-ai/dsh-tui` package exists (404), and a scope-wide npm registry
  search of 250 `@deepseek-ai` packages returns **no** TUI, terminal, or REPL app.
- The published profile bundles are exactly four: **`dsh-base`**, **`dsh-web-app`**,
  **`dsh-sdk-app`**, **`dsh-headless`**. A profile is
  `dsh-base` + one app bundle (`dsh.profile.bundles` in
  `<DSH_HOME>/profiles/<name>/package.json`), and there is no terminal app bundle.
- `@deepseek-ai/dsh-terminal` **does** exist (0.0.1-rc.3) but is a
  *"persistent PTY session seam … interactive sends, reads, signals, and awaited
  cleanup"* — a way to give **the agent** a persistent shell, not a UI for a human.

**So the human interface of stock `dsh` is a local web app** (`dsh`, `dsh web`, or
`--profile web`), served by `dsh-host-webserver` with `dsh-web-frontend` /
`dsh-client-web`. The `tui` profile name in the help text is a stale example that
shipped in at least two versions. It is a small documentation bug with an unusually
useful property: it is a **proof by construction of FR-148**. Reading `--help`
produced a capability that does not exist, so runtime discovery cannot be
help-text parsing — the probe must attempt the profile and observe the failure.

One caveat for FR-145, and it is not reassuring. The absence of a TUI does not mean
the harness cannot block on a human; it means it cannot *render its own prompt*.
`dsh-terminal`'s PTY seam is the residual risk: an agent that can drive an
interactive program can still hang on one. FR-145's detection requirement stands.

### Correction 7 — a third-party TUI landscape exists, but only as forks

The community list's *UI / Clients* section ([S22]) shows the interface ecosystem is
overwhelmingly **web-UI plugins, themes/skins, and Tauri/Electron shells that wrap
the official web app** for desktop, plus a VS Code extension and Tailscale-based
mobile remotes. Full-screen terminal UIs appear only inside downstream
**distributions** that fork the harness, not as a plugin for stock `dsh`. SoFact
must not assume a terminal-native interface is available from the primary harness.

## What was measured

### 1. The SDK surface (`deepseek_harness` 0.1.5rc1)

`DeepSeekHarnessConfig` is the load-bearing discovery:

```python
provider='deepseek-official', model='deepseek-v4-flash', reasoning_effort=None,
max_tokens=None, cwd=None, runtime_cwd=None, dsh_bin=None, profile='sdk',
patches=(), dsh_home=None, env={}, initialize_timeout_seconds=30.0,
request_timeout_seconds=None, shutdown_timeout_seconds=1.0,
base_url=None, api_key=None
```

**`base_url` and `api_key` are first-class.** A local ollama OpenAI-compatible
endpoint serves as the model with no patch file and no cloud dependency — which
satisfies the local-model preference and decouples the harness axis from the
DeepSeek vendor axis (§18.1).

`RunResult(session_id, final_response, finish_reason, events, notifications)` —
**typed events are returned directly**, so FR-151 needs no log-scraping fallback.

`dsh` **requires an explicit `DSH_HOME`** and refuses to read `~/.dsh` implicitly.
Hermetic by construction, which is what FR-149 asks for.

### 2. The `sdk` profile boots; the `headless` profile does not

`sdk` boots and completes tasks. `headless` **fails to boot**, reproducibly, in the
macos-arm64 0.1.5rc1 wheel:

```text
failed to import loader entry session-title-llm
(@deepseek-ai/dsh-session-title-first-prompt-llm): Cannot find package
'@deepseek-ai/dsh-session-title-llm'
```

A packaging bug in a shipped runtime. Relevant beyond SoFact: the ecosystem plugin
`AMAP-ML/LongHorizon-Harness` documents driving `dsh --profile headless`, so this
is a live cross-project hazard, not a local misconfiguration. Untested workaround:
`--patch` to disable `session-title-llm`.

### 3. The capability matrix is real and large (FR-148 validated)

`dsh --profile sdk --dump-config` returns **352 lines** of plugin composition
without any prior configuration. Present and relevant:

- **Goal mode**: `goal` (`@deepseek-ai/dsh-goal`), `goal-round-driver`,
  `command-goal`, `tool-goal` — four packages, first-party. `/goal` exists.
- Loop/sandbox/scheduler seams: `agent-loop`, `sandbox`
  (`@deepseek-ai/dsh-sandbox-local`), `bash-sandbox`, `fs-sandbox`,
  `sandbox-policy`, `approval`, `permission`, `plan-mode`, `subagent`,
  `subagent-spawn-in-process`, `subagent-fork-in-process`.
- Evidence surface: `session-persistence-jsonl`, `session-query-sqlite`,
  `session-projection(-cache)`, `session-checkpoint-policy`, `token-meter`,
  `tool-ralph`, `tool-workflow`, `repeat-tool-reminder`, `timeout-policy`.
- **`session-telemetry-otel`**, configured as
  `mode: process.env.DSH_TELEMETRY_MODE || 'FEEDBACK_ONLY'`, exporter
  `url: process.env.DSH_TELEMETRY_OTLP_URL ?? 'https://harness-telemetry.deepseeksvc.com/v1/logs'`.

There is **no `user-questions` tool** in the `sdk` profile tool list — the
composition offers the agent no way to ask a human. FR-145 is satisfied by
construction rather than by detection.

**Default composition contains a remote egress path.** The probe run also created
`<DSH_HOME>/.anonymous-user-id`. This converts FR-152 from prediction to
measurement: **neither `--offline` nor the default profile is an egress
boundary**, and a fresh `DSH_HOME` phones home unless the plugin is reconfigured.

### 4. Session record is a typed, zstd-compressed, append-only log

`<DSH_HOME>/sessions/--<cwd-slug>--/session-<id>/session.v3.jsonl.**zstd**`, plus
`session.lock` and `<DSH_HOME>/storages/session_projcache/sessions/<id>.json`.
**The JSONL is zstd-compressed**, so any reader must decompress — a concrete
implementation note for FR-151 that documentation did not supply.

### 5. A live genesis run (Mode G), unattended

Empty git repo, local model, `max_tokens: 8192`. The agent built a `moodclock`
package (`moodclock/mood.py`, `moodclock/__init__.py`, `tests/test_moodclock.py`,
`pyproject.toml`), created a venv, and ran pytest — **no human in the loop**.

Independently re-verified here (not the agent's own report):

- `python -m pytest` in the probe venv: **27 passed in 0.02s**.
- Fresh-interpreter behaviour check against the spec: the hour→mood boundary table
  matches for 0/4/5/11/12/17/18/21/22/23, and `ValueError` is raised for `24`, `-1`,
  `1.5`, `'5'`, `None`, `[5]` — including `bool` rejection.

### 6. **The goal loop did not engage** — the load-bearing negative result

Decompressing the session log gives **63 records**. Full event census:

```text
tool/call 12   tool/result 12   step/start 7   assistant/message 7   step/end 7
user/message 3   todo/write 3   agent/inbox/spliced 2   session 1
permission/preset 1   sandbox/mode 1   approval/policy 1   turn/start 1
system/message 1   request/header 1   request/context 1   session/title 1   turn/end 1
```

Tool calls: `bash` 5, `write` 4, `todo_write` 3.

**There are zero goal-typed events.** One turn, seven steps, twelve tool calls, and
no `create_goal`, no `goal-round-driver`, no continuation. The model used
`todo_write` — its in-turn planning tool — as a *substitute* for goal mode, then
finished with `finish_reason: completed`.

**Interpretation.** Goal mode is **model-discretionary**. The goal tools demand
"a long-running objective that should continue across autonomous goal rounds" —
a judgement the producer makes, and this producer declined. Goal mode is therefore
*available*, *loaded*, and *unexercised*. R25's sharper form is not "does the
harness have goal mode" but "**who enters it, and can SoFact force entry?**"

**Consequence for FR-136.** The contract→goal plan cannot assume the producer
enters goal mode spontaneously. SoFact must force entry (`command-goal`, the `/goal`
command, or a session initialized with the goal present) and must **verify entry**
by asserting goal-typed events in the session log, degrading per FR-144 otherwise.

### 7. `request/header` is native evidence (FR-139 satisfied)

The log's `request/header` record carries
`{"config": {"provider", "model", "maxTokens"}, "tools": [{"name": "bash", …}]}` —
so what the model was *actually given* is recorded by the harness, not asserted by
SoFact. FR-139's contract-integrity check has a native source.

## Why it matters for SoFact

- **§8.6 holds, for better reasons than it was argued.** The integration surface is
  a subprocess on stdio JSON-RPC with `base_url` injection and a mandatory
  `DSH_HOME`; the evidence surface is a typed append-only log; the goal, sandbox,
  loop, and scheduling seams all exist as configuration. Nothing about this argues
  for in-process coupling.
- **FR-136 must force goal entry and verify it.** The probe's central correction.
- **FR-148 is vindicated** — the composition is discoverable only at runtime, and
  it differed from every documented description of it.
- **FR-152 and FR-019 are now measured**: the default composition egresses.
- **F9 is confirmed a third time.** The producer reported success and it happened to
  be true; the report itself was not evidence. Independent re-execution was.
- **F10 gains a mechanism.** Evidence was available as an *artifact* (63 typed
  records with monotonic `seq`) rather than inferred from output — exactly the
  distinction F10 draws, now with a measurement behind it.

## Concerns / information quality

- **One model, one run, n=1.** The goal-mode negative result may be a property of
  `qwen3.8:27b-mlx` rather than of `dsh`. It must be repeated across models before
  it is treated as a harness fact. Flagged as such.
- **The `headless` profile is broken** in this wheel; all results above are
  `--profile sdk`.
- **Default egress is live.** Any SoFact harness invocation must reconfigure
  `session-telemetry-otel` and the sandbox plugin explicitly; a fresh `DSH_HOME` is
  not private.
- **`dsh` has never shipped a stable release**, and the runtime binary is 260 MB —
  a per-image cost that matters for the T2/T3 topologies (§18.2, D9).
- **The `.venv` in the probe repo was created by the agent** inside the scratch
  repo; the probe left disk artifacts behind (disk is 25 GiB free on this box).
