---
id: S22
slug: dsh-plugin-ecosystem
title: "The `dsh` plugin ecosystem — 4,100 repositories, and what is already commoditized"
publisher: community (curated list by Dominic789654 + GitHub API)
type: ecosystem-survey
url: https://github.com/Dominic789654/awesome-deepseek-harness
repo: https://github.com/Dominic789654/awesome-deepseek-harness
docs: https://deepseek-harness.github.io/deepseek-harness/
license: NOASSERTION (list; constituent repos vary)
version_at_retrieval: "list README 998 KB / 4,903 lines; pushed 2026-09-12T01:02:47Z"
released: 2026-08-13
retrieved: 2026-09-12
verification: content-verified
confidence: high
tags: [ecosystem, plugins, marketplaces, competition, supply-chain, distribution]
---

## Precis

A curated list of `dsh` plugins, skills, MCP servers, profile/patch layers,
orchestrators and UIs, plus the surrounding marketplaces. It answers a question
SoFact had not asked and needed to: **which of SoFact's mechanisms are still
differentiated, and which are commodity?** The answer changes the spec.

Method: fetched `README.md` (998 KB, 4,903 lines) and measured it, rather than
reading it. Counts below are computed from the file, not quoted from it.

## Scale (measured, not claimed)

- **4,609 distinct GitHub repositories** linked; **4,150** of them
  `dsh`/harness/DeepSeek-named. 23 sections.
- 238 stars / 157 forks on the list itself, created 2026-08-13 (same day as `dsh`),
  pushed 2026-09-12. It is as new as the thing it catalogues, which is the strongest
  signal about the ecosystem's age.
- The list itself references "the **13k-plugin** ecosystem" and a marketplace that
  live-syncs "the GitHub `dsh-plugin` topic (**1800+ repos**)". Those are claims; the
  4,150 measured figure is the defensible one.
- DeepSeek's stated discovery mechanism is the **`#dsh` GitHub topic** — plugin
  repositories are asked to carry it. Distribution is therefore a topic tag plus a
  package manager, not a review process.

## Term frequency — where the ecosystem is crowded

Occurrences across the 4,609 entries:

| term | n | | term | n | | term | n |
| --- | ---: | --- | --- | ---: | --- | --- | ---: |
| gate | 258 | | complet | 92 | | worktree | 32 |
| verif* | 155 | | evidence | 80 | | replay | 30 |
| bench | 135 | | orchestrat | 80 | | verifier | 27 |
| loop | 112 | | sandbox | 72 | | goal | 27 |
| audit | 110 | | eval | 57 | | budget | 25 |
| spec | 105 | | ledger | 46 | | contract | 18 |
| | | | | | | **elicit** | **0** |

**`elicit` appears zero times.** In a corpus of 4,609 repositories about autonomous
software agents, nobody has built — or even named — intent elicitation. Meanwhile
`gate` (258), `verif*` (155), `bench` (135) and `audit` (110) are saturated. SoFact's
P0 is uncontested; its P6 is the most crowded space in the ecosystem.

## SoFact mechanisms that already exist as free plugins

Each of these is a SoFact requirement with a shipping third-party implementation:

| SoFact | Existing plugin(s) |
| --- | --- |
| **FR-138** termination ≠ verification / evidence-gated completion | `GreenLv/dsh-completion-guard` (*"block Goal and task-completion claims until a checkpoint binds matching evidence"*), `rrrrrredy/beforedone`, `pavangupta352/stalegreen`, `chenjie1129/deepseek-harness-reliability-governor`, `AaronandWork/dsh-evidence-gate` (*"cross-checking claimed observations against the session's recorded tool activity"* — F10, implemented) |
| **FR-140** budgets, autonomy authority | `winter-street/dsh-plugin-agent-budget`, `PerryLink/dsh-budget` |
| **FR-141** git worktree per module | `wloops/dsh-git-worktree` (*ready-for-review / apply / finish / discard*) |
| **FR-139/§8.5** contract integrity, replay | `GreenLv/dsh-completion-guard` (immutable requirement ledger surviving `/compact` and resume) |
| **FR-142** wave scheduling | `AMAP-ML/LongHorizon-Harness` (role-scoped patches: `workspace-write` for executors, `read-only` for auditors) |
| **P0–P9 pipeline** | `songoao25/virtual-product-team` (*PM → Engineer → QA → Release, idea to shipped product*), `duyanta123/dsh-preset-scaffold`, `qwe225380/dsh-omni-router` |
| **P0 elicitation** | `light051001/dsh-preset-qa-mode` (*nine dimensions, max 5 rounds, confirmation gate*) — the only one |
| **P1 research** | `higekibaka/dsh-ciel` (pre-planning advisor, prior art, pitfalls) |
| **P6 independent verification** | ≥7 LLM-as-verifier plugins (`uson1x/dsh-plugin-llm-verifier`, `DevRico003/dsh-verifier-gate`, `zouyuanqing/dsh-verify-reflux`, `jmche/dsh-llm-verifier-pro`, …) |
| **§8 meta-harness / multi-runtime** | `dancingteeth/agent-looper` (Cursor/Cline/OpenCode/Codex/**DSH**/**Pi**), `cnlangzi/nightme` (Claude Code/Codex/OpenCode/**Pi**/**DSH**) |
| **FR-058** two-harness adapter | `weijiafu14/pi2dsh` (*"one Pi Host ABI runs unmodified Pi extensions as native DSH plugins"*), + ≥3 siblings |
| **FR-019** egress boundary | `pricklywiggles/dsh-research-container` (default-deny egress via `pf`), `NeevCloudAI/dsh-neev-sandbox` (gVisor), `omdsh-dev/dsh-sandbox-micro` (microVM), `GuoMonth/dsh-isolated-runtime` (K8s one-tenant-one-pod) |
| **FR-151** telemetry | `bigsongeth/dsh-events` (*"the `--json` that dsh doesn't have yet"*), `JohnXu22786/headless-json` (NDJSON + JUnit XML), `loongsuite/dsh-plugin`, `tma1-ai/dsh-otel`, `PerryLink/dsh-observe` |
| **NFR-015** telemetry privacy | `030611/dsh-telemetry-redactor` (*fail-closed export-copy redaction*, against the exact phone-home [S21] measured) |
| **Multi-tenancy** | `GuoMonth/dsh-multi-tenant`, `slywalker2006/dsh-passwords` |
| **Isolated harness homes** | `33moren33/dsh-box` (*"keep every run out of your real `~/.dsh`"*), `PerryLink/dsh-test-drive` (throwaway `DSH_HOME`) |

## The runtime-mutation finding (decisive for the plugin question)

The plugin set is **mutable at runtime, by the agent**:

- `memorax-ai/dsh-harmony` — *"A library for **patching, replacing, and decorating
  DSH plugins at runtime**."*
- `yjh051108/dsh-super-injector` — *"hot-injects local plugin packages into a
  **running** DSH web instance without patches or restarts."*
- `swaylq/dsh-genie` — *"turns a `cordis_define` **dynamic package** into a real
  installed bundle."* (`cordis_define` is a tool available to the agent.)
- `KannaKuron/dsh-ptc-cordis-preset` — *"self-referential Cordis tools and preset
  authoring."*
- `green-dalii/dsh-plugin-dev-skill` — *"lets **any agent build DSH plugins**
  correctly and to spec."*

So an in-process verifier is reachable by the party it verifies.

## Distribution channels (relevant to §19, not to §8)

- Marketplaces/directories: `DSHPlugin.app`, `DSPlugin.app`, `dshhub.co` (paid,
  code-redemption), `dsh.works`, `Sunrisepeak/dsh-index`, `YELEBAI/dsh-plugin-marketplace`
  ("verified … autonomous registry"), `AwesomeHou/dsh-plugin-marketplace`.
- Install managers: `dsh plugin --profile <p> add <spec>`; ~15 community managers.
- The install spec accepts `github:owner/repo#ref` — no publishing gate.
- `PerryLink/dsh-plugin-kit` ships shared *"fail-closed approval and adaptive
  session-event gates"*: gates are a **commodity utility library**, not an offering.
- `MicroMilo/upstream-radar` exists for *"vulnerability and breaking-change impact
  monitoring for DSH plugins"* — supply-chain risk is real enough that someone
  productized monitoring it.

## Why it matters for SoFact

1. **Mechanism is not differentiation.** Every gate, ledger, worktree, budget, and
   verifier SoFact specified already exists as free MIT code. If SoFact's value were
   the mechanisms, it would already be redundant. Its value must be the **assembled,
   measured, accountable pipeline** — including oracle *strength* as a number
   (F8, §9) — plus the **P0 front end, which nobody has built** (`elicit` = 0).
2. **§19 business shape is constrained.** Marketplaces are free; the one paid channel
   is plugin licensing. SoFact cannot be a plugin subscription. It sells the control
   plane and the measurement, per §19.1's land-and-expand (D13).
3. **Compose rather than rebuild — inside a frozen profile.** F6's apparatus-cost
   discipline extends to plugins: do not rewrite `dsh-git-worktree`. But 4,150
   third-party repos reachable from the producer's runtime is exactly the F6/S10
   failure mode wearing a different hat. The resolution is that the *profile* is the
   boundary: a minimal, pinned, hash-verified composition; never the operator's
   profile; no installation during P5. [S21] already used this pattern
   (`/tmp/dshprobe/home`), as do `dsh-box` and `dsh-test-drive` — external
   corroboration.
4. **New risks.** R28 (plugin supply chain) and R29 (runtime plugin mutation) are
   added to §21 by this entry. R29 is the structural form of R22: if verification
   runs in-process, goal-hacking stops being a behavioural risk and becomes a
   capability.
5. **Star-count hygiene, both directions.** The list displays **38,238** stars for
   `deepseek-ai/deepseek-harness`; the GitHub API reports **220,569**. Third-party
   badge data is unreliable upward *and* downward. Cite the API or nothing.

## Concerns / information quality

- **Descriptions are self-authored.** Every capability claim above is the plugin
  author's own README line. None was installed or executed. This entry measures the
  *shape and density* of the ecosystem, not the quality of any plugin in it.
- **The list is one curator's snapshot** with no inclusion criteria beyond the
  `#dsh` topic; it may over-represent newly-created repos. Its own counts (13k,
  1800+) exceed the 4,150 measured here.
- **A list created the same day as the thing it catalogues** has had no time to
  stabilize, de-duplicate, or weed dead entries.
- **Licence is NOASSERTION** on the list; constituent repos vary, so any composition
  must check licences per plugin, not per list.
