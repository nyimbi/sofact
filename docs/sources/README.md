# Source Ledger — SoFact

Traceable record of every external source encountered while researching the
software-factory design. Purpose: the eventual specification must be able to cite
*why* it believes something. Uncited claims are opinions; this directory is what
separates the two.

## Conventions

One file per source: `sNN-slug.md`, with YAML front-matter:

| Field | Meaning |
| --- | --- |
| `id` | Stable citation key (`S01`…). Referenced from the spec as `[S01]`. |
| `slug` | Filename stem, stable. |
| `title` | As published. |
| `type` | `paper` \| `essay` \| `product-doc` \| `benchmark` \| `protocol-spec` \| `news` \| `background` \| `primary` \| `execution-record` \| `ecosystem-survey` |
| `url` | Canonical URL, or `null` if never captured. Use `evidence:`/`path:` instead for `primary` entries. |
| `arxiv` | arXiv ID where applicable. |
| `retrieved` | Date encountered. |
| `verification` | See legend below. |
| `confidence` | How much weight this source can carry. |
| `tags` | Retrieval keys. |
| `supports` | *(reserved)* spec claim IDs this source backs, once the spec exists. |

Body sections are fixed: **Precis** (what it says), **Key claims** (falsifiable),
**Why it matters for SoFact** (design consequence), **Concerns / information
quality** (why it might be wrong).

## Verification legend

Honesty about provenance is the whole point of this file. Statuses:

| Status | Meaning |
| --- | --- |
| `content-verified` | Full text read this session, or — for `execution-record` entries — actually executed here. Present: S18, S19, S21, S22, S23, S24, S25. |
| `url-verified` | URL resolved successfully this session. |
| `reported` | Encountered during research earlier in this session (pre-compaction); content not re-read, URL not re-resolved. **Check `superseded_by` before citing**: S20 is partially superseded by S21. |
| `reported-via-secondary` | Known only through another source's citation, not read directly. |
| `unresolved-url` | Content seen; canonical URL never captured. |

**Every entry is currently `reported`, `reported-via-secondary`, or
`unresolved-url`.** No source has been re-verified since the research pass. This
is a known, deliberate debt — see *Verification queue* below. Do not treat any
figure in this ledger as confirmed until its status changes.

## Index

| ID | Source | Type | Verification | Confidence | One-line |
| --- | --- | --- | --- | --- | --- |
| [S01](s01-assistance-to-autonomy.md) | Assistance to Autonomy (SLR) | paper | `reported` | medium | Output **verifiability**, not capability, is the primary enabler of agentic adoption. |
| [S02](s02-dark-factory-soeters.md) | Towards the Dark Factory | essay | `unresolved-url` | medium | Evaluator must be causally isolated from producer; holdout scenarios; autonomy is a ladder. |
| [S03](s03-strongdm-software-factory.md) | StrongDM software-factory manifesto | product-doc | `unresolved-url` | low-med | Unit of work is a specification with machine-checkable acceptance criteria. |
| [S04](s04-swe-bench-verified.md) | SWE-bench Verified | benchmark | `reported` | med-high | Frontier ≈78.4%; the oracle is the repo's own tests — only well-defined because verification is mechanical. |
| [S05](s05-live-swe-agent.md) | Live-SWE-agent | paper/system | `reported` | low-med | 77.4% with a minimal scaffold that synthesises its own tools at runtime. |
| [S06](s06-sase-framework.md) | SASE | paper | `reported` | medium | Process-level adaptation is a distinct loop above the task loop (MAPE-K). |
| [S07](s07-mage-model-based-agentic-se.md) | MAGE | paper | `reported` | medium | Agents should operate on an explicit model, giving a cheaper oracle class than tests. |
| [S08](s08-harness-of-harness.md) | Harness of Harness | paper | `reported` | medium | Multi-day autonomy is bounded by state durability and objective retention, not per-step reasoning. |
| [S09](s09-six-layer-reference-architecture.md) | Six-layer reference architecture | paper | `reported` | low-med | Layered decomposition with verification as its own layer, not a step inside execution. |
| [S10](s10-software-factory-history.md) | Software factory history | background | `reported` | medium | Every prior wave died of apparatus maintenance cost — the documented failure mode. |
| [S11](s11-gethuman-lanes.md) | gethuman.sh | essay | `reported` | low-med | Three routing qualifiers: intent machine-derivable, outcome machine-observable, blast radius machine-bounded. |
| [S12](s12-local-coding-models-2026.md) | Local coding models, 2026 | survey | `reported` | low-med | Decode speed is bounded by *active* params — MoE is the local workhorse. |
| [S13](s13-anthropic-harness-billing.md) | Anthropic harness billing change | news | `reported` | low-med | Subscription pricing stopped covering third-party harnesses → structural vendor risk. |
| [S14](s14-x402.md) | x402 | protocol-spec | `reported` | medium | Revives HTTP 402 as machine-to-machine settlement; the rail is solved. |
| [S15](s15-hacker-fixer-loop.md) | Hacker–fixer–solver loop | paper | `reported` | medium | ~16% of benchmark tasks are hackable; a verifier needs its own adversary. |
| [S16](s16-shapiro-autonomy-ladder.md) | Shapiro autonomy ladder | secondary | `reported-via-secondary` | medium | L0–L5 defined by *fallback responsibility*, not by how much work the system does. |
| [S17](s17-factory-ai.md) | Factory.ai | product-doc | `reported` | low | Market evidence only: the concept has enterprise buyers above the model layer. |
| [S18](s18-goal-mode-harness-interface.md) | Goal-mode harness interface (`pi-goal` 0.1.7) | primary | **`content-verified`** | high | Producer may *declare* completion but not extend its own budget or pause itself; objective re-injected per continuation. |
| [S19](s19-harness-cli-surface.md) | Harness CLI surface (`pi`) | primary | **`content-verified`** | high | Extensions register their own flags, so capabilities must be discovered at runtime; session transcript at `PI_SESSION_FILE` is readable without cooperation. |
| [S20](s20-deepseek-harness.md) | DeepSeek Harness (`dsh`) | product-doc | `reported` — **partially superseded by [S21]** | medium | **`dsh` fixes D11.** Python SDK; typed append-only event log (`tool/call`, `tool/result`, `turn/end`) that history is *derived* from; loop, sandbox, and scheduler are plugins; Claude Code/Codex installable as subagents. Caveat: preview rc, breaking changes warned; default sandbox is `danger-full-access`. **Four claims falsified by [S21]** (version, integration surface, profile names, star counts). |
| [S21](s21-dsh-probe-executed.md) | **`dsh` executed under probe** | **execution-record** | **`content-verified`** | **high** | **The ledger's first measurement.** `sdk` boots, `headless` does not; integration is a subprocess on stdio JSON-RPC with `base_url` injection; default composition **egresses** to `harness-telemetry.deepseeksvc.com`; sessions are zstd-compressed typed logs; a genesis run built and tested a package unattended with a local model — but **never entered goal mode**, so goal mode is model-discretionary (FR-153, R25). Also: **no TUI** — the human interface is a web app, and `--help` advertises a `tui` profile that does not exist. |
| [S22](s22-dsh-plugin-ecosystem.md) | **`dsh` plugin ecosystem** | ecosystem-survey | **`content-verified`** | **high** | **4,609 repos, 4,150 `dsh`-named.** Every mechanism SoFact treats as differentiated already exists free — evidence gates (≥5), worktree isolation, budgets, wave scheduling, LLM verifiers (≥7), cross-harness orchestration. **`elicit` occurs 0 times; `gate` 258.** Plugins are **mutable at runtime by the agent** → an in-process verifier is reachable by the producer (D16, R29). |
| [S23](s23-harness-base-candidates.md) | **Harness base candidates: `oh-my-pi`, `oh-my-dsh`** | ecosystem-survey | **`content-verified`** (GitHub API, npm) / `reported` (README claims) | **medium-high** | **`oh-my-dsh` names ≥8 unrelated repos** across four kinds of artifact — a 530-plugin capability library, a curated overlay distribution, an auto-synced catalog, standalone agents. The name does not resolve to a base. **`oh-my-pi`** is a *detached hard fork of `pi`* (`fork: false`, no parent; 30,727★; npm `@oh-my-pi/pi-coding-agent`@18.1.18; 602 MB; 2,802 open issues). The capability library already ships `deep-research` (P1), `tower` (P4 + wave + **in-process conflict reviewer**), `fleet-orchestrator`, `secret-scanner` → a base would absorb much of SoFact's pipeline and turn FR-155 from a filter into an **audit**. Zero plugins installed; `LaplaceYoung/oh-my-dsh` declares **no licence**. |
| [S25](s25-forecastx-deep-research.md) | **`@forecastx/deep-research` executed** | **execution-record** | **`content-verified`** | **high** | **The research loop SoFact delegates to.** A `pi` extension whose tools spawn a recursive headless `pi` (`pi --mode json -p --no-session`, model pinned by `RESEARCH_MODEL`) that runs a web-search loop and saves `report.md` + machine-readable `meta.json` (query, stats, `sources: {id, title, url}`). **Measured live**: on a local 35 B model its own 240 s ceiling binds before its advertised five-search floor — 3 searches, then a 140-character stub with `sources: []`. The research prompt is hardcoded Chinese; the package **auto-loads into every `pi` session**, which is the measurement that froze SoFact's build composition (FR-154) and motivated the `pi-research` spec (FR-167). |

## Verification queue

Cheapest-to-confirm first. Each item is a concrete action, not a wish.

1. **S04** — resolve the live SWE-bench Verified leaderboard; record the actual
   top score *and* the scaffold it was measured with. The scaffold is part of the
   system under test.
2. **S02, S03, S11** — three essays with no captured URL. Re-find and pin.
   Until then they are vocabulary sources, not citable evidence.
3. **S12** — replace the aggregated model landscape with measured numbers *on
   this machine* (see `docs/research/findings.md` § measurement plan). Model
   names and versions drift fastest of anything here.
4. **S01, S06, S07, S08, S09, S15** — arXiv IDs recorded in-session but not
   re-resolved (the arXiv API rate-limited this session). Confirm existence,
   title, and publication status; extract real numbers rather than remembered
   ones.
5. **S13** — confirm against Anthropic's own pricing/terms, not secondhand
   reporting. Effective date and exact scope matter.
6. **S14** — check x402's standardisation status and whether the facilitator role
   has any non-Coinbase implementations.
7. ~~**S20**~~ — **done, and it was worth doing.** Installing and running `dsh`
   falsified four of S20's claims (version, integration surface, profile names,
   star counts) and produced the first measurement in this ledger ([S21]). The
   lesson generalises: for a *runtime*, reading documentation is not partial
   verification, it is a different activity. Remaining in the queue from S20 only:
   whether the breaking-changes warning reaches the SDK surface, and the
   `headless` bug's behaviour on Linux wheels.
8. **S22's constituent plugin repos** — nothing in the ecosystem survey was
   installed. If FR-154's frozen composition is ever to name a third-party plugin,
   that plugin needs its own ledger entry.

## Gaps — sources we do *not* have and probably need

- **The goal-mode harness landscape.** Added 0.3. **Closed as a question of
  capability, reopened as a question of engagement.** The ledger now holds five
  entries across two harnesses — [S18], [S19], [S20], [S21], [S22] — and [S21] is a
  **probe**. What [S21] settled: the `dsh` `sdk` profile boots, the runtime
  composition is discoverable, the event taxonomy is real and typed, the
  integration surface is a clean subprocess RPC, and a local model can build and
  test a package unattended. What it did **not** settle: **goal mode was never
  entered** (zero goal-typed events; `todo_write` substituted). So the open item is
  no longer "does `dsh` have goal mode" but "**can SoFact force entry, and does the
  continuation loop then run?**" (FR-153, [F11], M0 item 6a). Still missing: the
  FR-135 matrix answered empirically for `pi` as well, goal-declaration precision
  for both, and any third harness — so the claim that goal mode is a *portable*
  idiom still rests on `n = 2`.
- **`dsh` runtime behaviour.** [S21] answered (b) and (d) in part: the composition
  is dumped by `--dump-config`, and the live event taxonomy was observed (18 types
  across 63 records). Still open and load-bearing:
  (a) **whether goal continuation runs once entered** — the single highest-value
  probe in the project; (c) whether `goal` survives compaction the way `pi-goal`
  does; (e) whether the breaking-changes warning reaches the SDK surface; (f) what
  the sandbox composition actually permits under a non-`danger-full-access`
  profile; (g) whether the `headless` packaging bug reproduces on Linux wheels — it
  affects the ecosystem's own tooling (`LongHorizon-Harness` drives
  `dsh --profile headless`), not just this box; (h) **how the two installs diverge** —
  the npm CLI (`0.1.0-rc.6`) and the SDK's bundled runtime (`0.1.5-rc.1`) are
  separate trees with separate `DSH_HOME`s, and their compositions were not
  diffed against each other.
- **The `dsh` plugin ecosystem.** Added 0.2/S22. [S22] measures density and overlap
  from plugin *descriptions*; nothing was installed or executed. Missing: any
  quality, security, or maintenance signal for individual plugins — necessary before
  FR-154's frozen composition can name specific third-party plugins rather than
  none.
- **Whether the producer can defeat an out-of-process verifier too.** [S22]
  establishes that an *in-process* verifier is reachable. The converse is assumed
  but unmeasured: that an independent control plane reading the session log cannot
  be gamed by what the producer writes into it. This is the load-bearing assumption
  of §8.7 and of FR-138, and no probe has tested it.
- **Cordis / arXiv 2608.25512** — asserted as `dsh`'s design basis in [S20], never
  fetched. Low priority unless SoFact ends up authoring plugins (which §8.6 forbids
  in v1).
- **Harness benchmark evidence for genesis work.** [S04] (~78.4%) and [S05]
  (77.4%) are Mode M measurements — a repo and its test suite already exist. There
  is no equivalent for building from an empty repository, so harness fitness for
  Mode G is unknown. If it exists, capture it; if it does not, say so explicitly.
- **Unsloth / LoRA fine-tuning for tool-use.** The original research plan named
  this; nothing was captured. Directly relevant given the disk constraint.
- **Apple Silicon sandboxing** (Firecracker/gVisor are Linux-only; this box has
  no Docker). Needed for S11's blast-radius qualifier.
- **Context engineering / memory architectures** for long-running agents.
  S08 covers failure modes but not mechanisms.
- **Cost/throughput crossover data** for local vs. hosted per lane — the actual
  number that decides the local bet, currently argued from principle.
- **Human-attention economics**: review throughput as the real bottleneck.

Status of this ledger is tracked as part of the open-question set in
`docs/research/findings.md`.

## Status of this ledger

S01–S25. Seven entries are `content-verified`: [S18], [S19] (primary interface
reads), [S21] (the first **executed** source in the project — a runtime measured
rather than read), [S22] (a measured ecosystem census), [S23] (GitHub API measurements of the
named harness bases), [S24] (the talk transcript plus the author's own long-form
expansion), and [S25] (the research extension read in full and executed once). Everything else is
`reported`, and each such entry should be treated as a hypothesis with a citation
attached, not as evidence.

**Open lead.** [S24] names **SlopCodeBench** (Gabe Orlanski, UW) as the only benchmark
its author knows of that measures a model's ability to maintain a codebase *over time*
— reported at a 17% strict pass rate for one frontier model, and described as deeply
unsaturated. It is cited there but not fetched here, so it is *not* relied on anywhere
in the spec. It is queued because it is the one source that could move F16 from
"there is no absolute oracle" to "there is a partial one," which would change D18.
Until it is fetched and read, [S24]'s own figures must not be treated as established.
