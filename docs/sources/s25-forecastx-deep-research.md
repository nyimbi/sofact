---
id: S25
slug: forecastx-deep-research
title: "@forecastx/deep-research 0.1.1 executed — the research loop SoFact delegates to"
publisher: measured locally (SoFact probe)
type: execution-record
url: (n/a — local probe)
repo: https://pi.dev/packages/@forecastx/deep-research
docs: (source read from the installed package)
license: MIT
version_at_retrieval: "0.1.1 (installed under ~/.pi/agent/npm/node_modules)"
released: (registry date not fetched)
retrieved: 2026-09-12
verification: content-verified (source read; one live run executed)
confidence: high
tags: [research, pi-extension, measurement, delegation, composition, timeout]
supersedes_claims_in: []
---

## Precis

This entry records what `@forecastx/deep-research` **is and did** on this machine:
both the extension's source (read, 826 lines of TypeScript) and one live research
run executed against a local model. It is the evidence behind FR-167 (research is
dispatched, not performed) and the composition-freeze correction in [S19]'s
adapter table.

**Source facts (read from the installed package).** Version 0.1.1, MIT, `"pi-package"`
distribution whose entry point is `src/index.ts`. It registers two tools
(`deep_research`, `super_deep_research`) and two slash commands. The tool **spawns a
recursive headless `pi`**: `pi --mode json -p --no-session [--provider P] [--model M]
<prompt>`, with the model pinnable through `RESEARCH_PROVIDER` / `RESEARCH_MODEL`
environment variables. The child runs a search loop and the extension saves its
output under `~/.forecastx-reports/<id>/` as `report.md`, per-section files under
`sections/`, and a machine-readable `meta.json` carrying `query`, `mode`,
`stats` (`searches`, `turns`, token counts, `durationSeconds`), `summary`, `toc`,
and a `sources` array of `{id, title, url: string | null}`. **The research prompt is
hardcoded Chinese** ("输出格式（markdown，全中文）") — output language is dictated by
the prompt, not by the operator or the query. The loop's own ceilings are 240 s
(deep) and 360 s (super), and the "must call the search tool at least 5 times" rule
is instruction, not mechanism.

**Live run (2026-09-12, model `qwen3.6:35b-mlx`, deep mode).** Wall clock 4 m 15 s,
cost $0.00. The loop ran — 3 searches, 2 turns, 13,093 input / 285 output tokens —
and was then **killed by the extension's own 240 s timeout**. The artefacts were
still written: a 140-character stub `report.md` and a `meta.json` with
`sources: []` and `durationSeconds: 240`. The advertised "5+ searches,
3,000–8,000 characters, 1–3 minutes" assumes a fast cloud model; on this machine's
local 35 B model the timeout binds first (three searches consumed the entire deep
budget, so its five-search floor is roughly half of what the ceiling allows).

**Composition facts.** The package auto-loads into every `pi` session from
`~/.pi/agent/npm` — measured by calling the tool from a session that named no
extension flag. SoFact's response is data: the build spec runs `--no-extensions`
(FR-154), and the research spec is the same argv with `--offline` and
`--no-extensions` deliberately removed plus `RESEARCH_MODEL` pinned from the
operator's model (FR-161, FR-167).

## Verification status

Source read in full (`index.ts`, `runner.ts`, `prompts.ts`, `report-store.ts`,
`tools/*.ts`, `types.ts`, `extractor.ts` — 826 lines). One live run executed and
its report store inspected. The *super* mode was not executed; its 360 s ceiling
and 8–15 search claims are from the source code, not measured here.
