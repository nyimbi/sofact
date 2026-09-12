---
id: S23
slug: harness-base-candidates
title: "Harness base candidates: `oh-my-pi` and `oh-my-dsh`"
type: ecosystem-survey
verification: content-verified (GitHub API metadata); reported (README claims)
confidence: medium-high
accessed: 2026-09-12
retrieved_via: "GitHub REST API (`/repos/*`, `/search/repositories`); raw README fetch; `npm view`"
relates_to: [S20, S21, S22]
---

**Why this entry exists.** The operator stated an intent to use "either `oh-my-pi` or
`oh-my-dsh` as the harness." Both names are load-bearing for the harness decision
(D11, D15) and neither was in the ledger. Measuring them changed the picture: one is
a 30k-star hard fork of `pi`, and the other is **a name with at least eight
claimants and no determinate referent**.

## 1. `oh-my-dsh` is not one project

Eight distinct repositories in the curated list [S22] carry the name. GitHub search
returns more. They are *four different kinds of artifact*:

| Repo | ★ | Kind | What it actually is |
| --- | --: | --- | --- |
| `like-study1/Oh-My-DSH` | 84 | **catalog** | Python, MIT. Auto-synced plugin directory, rebuilt every 4 hours from the `dsh-plugin` topic. A discovery index, not a base. |
| `LaplaceYoung/oh-my-dsh` | 58 | **capability library** | TypeScript. **530 plugins, 3,731 tests, 2,183/2,183 e2e registration checks.** "Never touching the agent loop." Has a `GAP-LEDGER.md`. |
| `agi-fans/oh-my-dsh` | 31 | **agent** | "Keyboard-first DeepSeek coding agent built on the plugin architecture of DSH, inspired by the interaction quality of `oh-my-pi`." Topics include `oh-my-pi`. |
| `amplifthq/oh-my-dsh` | 14 | **distribution overlay** | "A curated distribution of DeepSeek Harness. **Overlay, not a fork.**" Topics include `dap`. |
| `nightBrise/Oh-My-DSH` | — | bundle | "A comprehensive plugin bundle designed for DeepSeek Harness." |
| `byhongyu/oh-my-dsh` | — | presets | "Curated Coding, Research, and Investing agent setups." |
| `my-dsh/oh-my-dsh` | — | distribution | "Distribution/plugin collection with token-tracking and token-usage tooling." |
| `secretxuan/oh-my-dsh` | — | agent teams | "Agent Teams for DeepSeek Harness, with optional Windows computer-use." |
| `wangshunnn/oh-my-dsh` | — | collection | "A collection of DeepSeek Harness plugins." |

**Consequence.** "Use `oh-my-dsh` as the harness" is not a decision that can be
executed. It must become *"use `<owner>/oh-my-dsh` at commit `<sha>`."* Two of the
eight are catalogs — a catalog is not a base, and treating one as a base would mean
shipping an index as infrastructure.

## 2. `LaplaceYoung/oh-my-dsh` overlaps SoFact's pipeline directly

This is the significant finding. Per its README, the 530 plugins are **ports of
capabilities from peer harnesses** (Claude Code, `oh-my-pi`, kimi-code, opencode,
Codex CLI) onto DSH extension seams. The named capabilities map onto SoFact phases:

| `oh-my-dsh` plugin | SoFact phase it duplicates |
| --- | --- |
| `deep-research` — decomposes a compound question into sub-questions, searches and fetches in parallel, synthesizes a **cited report** | **P1 (research)** |
| `tower` — dispatches instructions to worker subagents iterating one repo concurrently; each worker reads a shared brief; then **a reviewer, always on the primary model, re-reads outputs and flags conflicts** | **P4 (dispatch) + §12 wave scheduling + P7 conflict detection** |
| `fleet-orchestrator`, `microagents`, `specialist-agents` | P4 fan-out shapes |
| `secret-scanner` — a `tools.guard` denying `write`/`edit`/`apply_patch` carrying secrets, **before any filesystem mutation, with no allow-override path** | the guard layer (producer-side) |
| `repo-secret-audit`, `git-secret-gate` | commit-time guard |
| `stream-rules` — injects regex-matched reminders mid-drift | producer-side hygiene |

If this is adopted, **P1, P4, the wave scheduler, and P7's conflict review largely
stop being SoFact's to build.**

**Verification status.** All of the above is **self-authored README text**. Zero of
the 530 plugins were installed or executed. It is `reported`-quality, in the sense
established by [S21]'s four falsified claims. The repo's own test/e2e counts are
likewise unverified badges. No licence is declared in the GitHub API response
(`license: None`) — a real blocker before adoption, not a footnote.

## 3. `oh-my-pi` is a hard fork of `pi`, not a plugin

| Field | Measured |
| --- | --- |
| Repo | `can1357/oh-my-pi` — "⌥ Coding agent with the IDE wired in" |
| Stars / forks | **30,727 / 3,176** |
| Created / pushed | 2025-12-31 / **2026-09-12** (actively developed) |
| Language / size | TypeScript (+ ~80k lines Rust core per README); **602 MB** repo |
| Licence | MIT |
| GitHub `fork` flag | **`false`** — no `parent`, no `source` |
| Open issues | **2,802** |
| npm | `@oh-my-pi/pi-coding-agent` @ **18.1.18** |
| Distribution | `omp.sh` install script, `can1357/tap` Homebrew, Bun, Nix |
| Self-description | "**Fork of Pi** by @mariozechner" |

**The important distinction.** GitHub does **not** mark it as a fork, and it has no
`parent`/`source` link — so it is a *detached hard fork*, now an independent
versioned product at 18.x with its own install channel. It is not "someone's fork
branch of a live upstream." But the README's own words are "Fork of Pi," and it
shares Pi's lineage. For D15/FR-146's purposes it **is** a fork, even though for
maintenance-risk purposes it behaves like an independent product.

**Consequence for D11's rationale.** D11 chose `dsh` as primary partly because it
exposes a **typed, replayable, append-only event log** ([S20], [S21]) — SoFact's
product is evidence about what happened, and `dsh` makes evidence a first-class
artifact. That ground is about **evidence quality**, not economics, so it survives
the operator's reframing intact. `oh-my-pi` being `pi`-shaped therefore does not
inherit S19's findings automatically; it would need its own session-log measurement
before it could displace `dsh` on those grounds.

## 4. Cross-links observed inside the ecosystem

- `AndrasSama/dsh-omp-advisor` — "`oh-my-pi` **advisor subsystem** ported to
  DeepSeek Harness — independent reviewer models watch your agent and advise it
  (nit injects, concern/blocker steer)." So `oh-my-pi` ships an **independent
  reviewer subsystem** that others consider worth porting. This is the
  independent-verifier pattern arrived at independently — relevant as prior art and
  as a *control arm* (FR-107), and as an in-process verifier that fails FR-155's
  deletion test.
- `mytianyi0712/dsh-tui-plugin-OhMyPi` — a terminal-styling plugin for `dsh`
  "inspired by Oh My Pi."
- `vavilonska/SeekAnchor` — steering adapters for **Pi, Oh My Pi, and OpenAI**;
  confirms `oh-my-pi` is treated as a peer harness surface.

So `oh-my-pi` functions as a **reference point inside the `dsh` ecosystem** — its
capabilities are being ported *into* `dsh` by third parties. That is an argument for
using `dsh` + ports rather than switching base, and it is measurable.

## 5. What this entry does not establish

- Whether any of the 530 plugins install, boot, or work. **Nothing was executed.**
- Whether `oh-my-pi`'s session log is typed or replayable; whether it has goal mode.
- Whether `LaplaceYoung/oh-my-dsh` declares a licence compatible with use.
- Which of the eight `oh-my-dsh` repos the operator actually meant.

## Source references

- `https://github.com/can1357/oh-my-pi`
- `https://github.com/LaplaceYoung/oh-my-dsh`
- `https://github.com/like-study1/Oh-My-DSH`
- `https://github.com/amplifthq/oh-my-dsh`
- `https://github.com/agi-fans/oh-my-dsh`
- GitHub REST API: `/repos/{owner}/{repo}`, `/search/repositories`
- `npm view @oh-my-pi/pi-coding-agent`
- [S22] — the curated list these were found in; term-frequency census
- [S21] — the measured `dsh` probe; source of the "descriptions are `reported`" standard
