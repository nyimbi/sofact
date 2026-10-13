# OpenRig and Paperclip, capability by capability, against this tree

Date 2026-10-12. Sources: [S26](../../sources/s26-openrig.md) (OpenRig, Apache 2.0,
0.6.0) and [S27](../../sources/s27-paperclip.md) (Paperclip, MIT). Companion to
[neighbouring-orchestrators](../neighbouring-orchestrators/README.md), which found the
ledger defect and the differentiation table; this note answers a different question.

**The question.** *SoFact needs the relevant capabilities of OpenRig and Paperclip.*
Both are product READMEs — neither was installed or executed — so every capability
below is the vendor's description of its own system. The disposition of each is decided
against SoFact's **spec**, not against the vendor's judgement of what matters: a
capability is a gap here only if an FR requires it and the code does not do it, and a
capability is refused here only if an FR or ADR refuses it.

**Outcome.** Twelve capabilities are already covered, several by a mechanism with a
property the vendor's lacks — and one more since this note was written: FR-070's
addressable source ledger, which §2.4 had recorded as "covered, weaker", is now built
(ADR-0035). Five were real gaps against SoFact's own requirements, and
three of the five are **deferrals whose own stated condition has been met** — the tree
is wrong about itself, which is the failure mode this ledger has been bitten by before.
Four are refused with a spec reason, and four are not applicable because the vendor's
scope is broader than SoFact's and the extra scope is a company simulator's, not a
factory's.

**The useful reading.** The neighbours are not a feature list to copy. Every gap this
note finds is a requirement **SoFact already wrote for itself** — which makes OpenRig
and Paperclip independent evidence about which unbuilt requirements are load-bearing,
rather than a source of new ones. The one capability they have that SoFact genuinely
lacked was atomic checkout, and that was found and fixed in
[neighbouring-orchestrators](../neighbouring-orchestrators/README.md) before this note.

## 1. Method, and what a row is allowed to claim

A row is `capability | vendor evidence | SoFact status | disposition`. SoFact's status
is **measured from this tree** (file and line, or a grep that returns nothing), never
inferred from the presence of a similarly-named type. The disposition is one of:

- **Covered** — the capability exists; the row names where.
- **Covered, stronger** — the capability exists *and* carries a property the vendor's
  description does not claim (usually: the record is in the hash chain).
- **Gap — build** — an FR requires it, the code does not do it. These are the answer to
  the operator's question.
- **Gap — deferred, and the condition has fired** — a recorded deferral whose own
  stated trigger is now met. These are worse than plain gaps: the tree is wrong about
  itself, and that is the failure mode this ledger has been bitten by before.
- **Refused** — an FR or ADR refuses it, and the row names which and why.
- **Not applicable** — the capability serves a scope SoFact does not have.

## 2. The inventory

### 2.1 Orchestration

| Capability | Vendor evidence | SoFact status | Disposition |
| --- | --- | --- | --- |
| Declarative multi-harness topology | `RigSpec` YAML (pods, edges, continuity); Paperclip org chart + agent specs | `HarnessSpec` + `ConfiguredHarnessAdapter` (`harness.py:819`), three specs, one interface (FR-058); `Decomposition` is the topology and it is derived from clauses, not authored | **Covered, stronger** — SoFact's topology is *derived* from the contract and gated (FR-087/088), so it cannot be hand-authored into an untraceable shape |
| Per-seat / per-agent permission policy | `rig seat set-permissions`, audited; "YOLO is off by default" | No per-module permission policy. `ModuleClass` ceilings (`views.py:478`) cap autonomy by class; the sandbox is prompt text | **Gap — build** (FR-059): "The harness must run inside the lane's sandbox with no access to the oracle corpus, holdout scenarios, or factory credentials." Ceilings are declared; the boundary is asserted in goal text only (`planner.py:127`) |
| Budget hard-stops, cost control | per-seat policy; "budget hard-stops"; cost events | `StepBudget` (`views.py:1060`) — wall clock, continuations, attempts, tokens; `BUDGET_EXHAUSTED` is a real `StepOutcome`; budgets are SoFact's authority (FR-140) | **Covered, stronger** — FR-140 makes budget SoFact's and *not the harness's*, which is the structural version of "hard-stop"; the vendor's is policy the agent is asked to honour |
| Atomic checkout / execution locks | "A single assignee and execution locks prevent competing runs from claiming the same task" | `Ledger._exclusive` — `fcntl.flock` across the read-modify-write (ADR-0029) | **Covered** — this was the defect, found by reading S27 and fixed |
| Durable audit log | SQLite + `bundle-audit.jsonl`; Postgres "durable activity" | The ledger: append-only, hash-chained, 30 `LedgerKind`s (`views.py`), `require_intact` before every fold | **Covered, stronger** — tamper-*evident*, which neither vendor claims; the chain is the reason FR-003 is a hard error rather than a log line |
| Revision + rollback | snapshot/restore; "revisioned config with rollback" | `Decomposition` revisions + `decomposition_hash`; approving a superseded revision is refused (FR-094); `sofact rollback --to N` cuts the log's reading rule and records why (ADR-0034) | **Covered, stronger** — the vendor's rollback restores a snapshot; SoFact's is a reading rule over an append-only, hash-chained log, so the work a rollback hides is still there to be read and the chain still verifies. The vendor cannot show what it rolled back *from* |
| Goal ancestry / traceability | culture + continuity; "goal ancestry" | `decomposition.gate` checks traceability both directions (`decomposition.py:423,438`) | **Covered** — Paperclip carries ancestry for agent *context*; SoFact carries it for escape attribution (FR-127). Same mechanism, different purpose |

### 2.2 Durability and resumption

| Capability | Vendor evidence | SoFact status | Disposition |
| --- | --- | --- | --- |
| Explicit phase state machine, resumable | `rig up`/`rig down`; snapshot/restore | Phases are a state machine in the log: `PhaseAdvance` is its own row, `state.fold` derives `current_phase` and `open_gate`, `sofact phase` exits non-zero while a gate is open, and a second process reads the phase off disk | **Built** (FR-060, ADR-0030/0031/0035/0037, 2026-10-13). What a fold cannot do is *re-enter* a phase's work after SIGKILL mid-step, which is FR-062's remaining half and is recorded in the roadmap's §3 item 5 |
| Per-node restore outcomes, incl. "cannot resume" | `resumed`, `fresh-primed`, `awaiting-decision`, `attention_required`, `failed` | `StepOutcome` is four members; a recordless session reads `completed` (measured) with a caveat in `note` | **Covered in part** — the caveat is now printed for every outcome, so the *reporting* half is done. The five-state vocabulary remains a fair shape for a future state meaning "the work may have happened and cannot be recovered"; see [neighbouring §2] |
| Snapshot / restore of a whole rig | `rig snapshot`, `rig restore` | The ledger *is* the snapshot: `state.fold` reconstructs everything. But there is no verb that materialises a restored workspace, and no per-node outcome | **Partly** — the fold *is* the restore for everything the log records (that is what makes `rollback` a reading rule rather than a truncation, ADR-0034), but no verb materialises a restored workspace and there is no per-node outcome. The FR-060 half is closed; this row's residue is FR-062 |
| Discovery / adopt of existing sessions | `rig discover`, `rig adopt` (fingerprints live tmux sessions) | Sessions are factory-created under `<home>/sessions/<module>` (`service.py:836`) and disposable; state is the ledger | **Not applicable** — adopt exists because OpenRig's state lives *in* live tmux sessions. SoFact's does not, which is the property that makes a killed session survivable |

### 2.3 Isolation and integrity

| Capability | Vendor evidence | SoFact status | Disposition |
| --- | --- | --- | --- |
| Producer isolation by enforced boundary | tmux + workspace trust; Paperclip workspaces & runtime | `CLAUDE_CONFIG_DIR`, `OPENCODE_DB`+`OPENCODE_TEST_HOME` as env vars; `--standalone` measured to matter (ADR-0028); a **worktree per module** with the main tree holding the integration line (FR-141, ADR-0033) | **Half closed 2026-10-12** — FR-141 is built and `--concurrent` is an operator flag; FR-059 is not. A worktree is containment, not confinement: the child is still not confined, and `sandboxable` reads absent for both harnesses |
| "An isolation variable is not a boundary" | stated outright: `OPENRIG_HOME` alone does not isolate provider config | The `store_isolated` row (FR-019) now runs the same goal twice with `HOME` relocated and the spec's containment variables applied in one arm, withheld in the other | **Closed 2026-10-12** — see §3.3. The store is contained and measured; the *child* is not, and `sandboxable` still reads absent for both harnesses |
| Imported-bundle SHA-256 integrity | `RigBundle`, `bundle-audit.jsonl` | No import mechanism at all, so nothing to protect. The archive discipline for *sources* is a human process (`docs/sources/archive/`, global rule) | **Not applicable** — and if a bundle import is ever built, this row becomes a build item, not a nice-to-have |
| Multi-organization isolation | "Company-scoped access checks keep each organization's work, agents, and activity separate" | One goal per state directory; `current_goal()` returns the most recent (`service.py:297`) | **Not applicable now** — S27 says the same. It becomes relevant at FR-124 (per-deployment topology ceilings), which is itself unbuilt |

### 2.4 Presentation, surface, and posture

| Capability | Vendor evidence | SoFact status | Disposition |
| --- | --- | --- | --- |
| Machine-usable surface (MCP server) | OpenRig ships an MCP server | The CLI is the human surface (`cli.py`; 31 commands) and `sofact api` is the machine one (`api.py`; 10 read-only operations) | **Built for the factory, gap for the delivered system** (FR-120, ADR-0048): "SoFact must produce the system so that it is **machine-usable** as well as human-usable: a documented, stable API surface." Note the requirement's subject is the *delivered* system; SoFact's own surface being CLI-only is the same defect one level up. P8 itself is no longer the qualifier: FR-117/FR-118/FR-119/FR-121 are built and the factory writes the two artefacts it owes (2026-10-13, ADR-0040, ADR-0044). **The factory's own surface is now machine-usable too** (ADR-0048): `sofact api --list` publishes ten read-only operations and `sofact api <operation>` answers one call with one closed `MachineEnvelope`; the four §3.3 gates are absent from the table and refused *by name* with the human verb to use. The delivered-system half stays a producer obligation — no oracle observes whether an artefact is machine-usable, so the delivery report names it rather than checking it |
| TUI | OpenRig ships one | None; `typer` commands printing to stdout | **Refused** — a TUI is apparatus cost against F6/[S10]; FR-120 asks for a machine-usable surface, and a TUI is the opposite of that |
| Provider-usage / context-usage tracking | `provider-usage`, `context-usage` under `OPENRIG_HOME` | Per-dispatch `tokens_observed`, `wall_clock_seconds`, `continuations_observed` (`views.py:1672`), rolled up per attempt and per plan by `measure_attempts` (`telemetry.py`, FR-102, ADR-0055) and printed by `sofact attempts` | **Covered** — narrower than the vendor's in one respect: no per-*provider* aggregation, because SoFact runs one harness per run and the provider is the harness's business, not the ledger's |
| Culture / `CULTURE.md` | layered norms onto a default team | `_SHARED_CONSTRAINTS` (`planner.py:110`) + goal text + contract clauses | **Covered** — the same idea with a difference that matters: SoFact's constraints are compiled from the contract and pinned by hash (FR-096), so a norm cannot drift from the artefact it governs |
| Context library | a library under `OPENRIG_HOME` | `docs/` + the spec + the ledger | **Covered, stronger** (2026-10-12, ADR-0035) — FR-070's addressable source ledger is built: `Source`/`Claim`/`Contradiction` are types, `sofact sources` prints and records one, and the claim-to-source edge is derived (`SourceLedger.resting_on`), so invalidating a source invalidates the claims resting on it. The vendor ships a directory of documents; this is a directory of documents whose entries can be cited, contradicted and expired |
| Telemetry on by default | anonymous telemetry, documented opt-outs; opt-in OTel | None | **Refused by default** — NFR-024 argues for recording what was observed, not for shipping observations off-box. If telemetry is ever added, it is opt-in, and it must not carry prompt text (S26's own payload rule) |
| Routines & schedules, heartbeat execution, work & task system, secrets & storage, company portability, org chart | Paperclip's 12 subsystems | Not in scope | **Not applicable** — these serve "run a company made of agents". SoFact's unit is a contract handed to a session, and §1.3's envelope is a platform, not an org |

## 3. The three deferrals whose condition has fired

This is the part of the note worth acting on. A deferral is a claim that the tree is
correct *for now*; when the trigger it named is met, the claim is false and nothing
fails to tell you.

### 3.1 FR-141 worktree-per-module — **closed 2026-10-12**

> **Built.** [ADR-0033](../../adr/0033-a-worktree-is-per-module-and-a-wave-is-isolated-only-when-every-step-has-one.md)
> supersedes ADR-0024's deferral. `ensure_module_worktree` creates the module's branch
> *in* the worktree and leaves the main tree on the integration line, `_integrate_wave`
> merges each isolated step back before the next wave is judged, and `--concurrent` is
> now reachable from the CLI — which was the second half of the condition this section
> measured. The measurement below is kept because it is what made the closure
> decidable, and because the last paragraph's point stands as a method: a requirement
> deferred on a condition its own author wrote has to be re-read against that condition.

ADR-0024 defers worktrees, and the spec's own table states the condition: FR-141 is
deferred "until a wave runs concurrently or a plan spans more than one module"
(`product-spec.md:1240`). ADR-0024 §3 states it again as "whichever comes first".
Measured (and true **as of the measurement**, before the build — the flags
and greps below are what the tree looked like then):

- **The multi-module half had fired.** A plan spanning more than one module is not
  merely possible, it is the case `_module_for` was written for: it resolves a step's
  branch from its clauses, and its own docstring names "a step whose clauses span two
  modules" as a real input (`service.py:904`). Any decomposition with two modules
  produces one. `grep -rn worktree src/` returns four hits and every one is a comment
  saying it is deferred, including `harness.py:732` and `harness.py:1685`, where the
  *probe* tells the operator that real confinement is elsewhere.
- **The concurrent half had fired at the API and not at the surface.**
  `dispatch_plan(concurrent=True)` exists and `asyncio.gather`s a wave
  (`service.py:1038`), but **the CLI has no flag for it** — `grep -n concurrent
  src/sofact/cli.py` returns one hit and it is a print of the word "concurrent" for a
  wave heading. Only a test can turn it on, and one does (`test_service.py:802`).
  ADR-0024's "the operator owns" is currently the operator being unable to choose.

**The live risk is therefore low, and this row is not the emergency the framing
suggests.** ADR-0024 §5's strongest argument — *"an oracle runs against a workspace, so
two sessions sharing one means clause A's verdict is polluted by session B's edits"* —
is about two sessions running **at once**, and the operator cannot currently cause that.
Sequential multi-module steps sharing a tree is by design: the branches are cumulative,
and `sealed_files` exists so a module's own files stay attributable.

What is actually wrong is narrower and worth stating precisely: **a requirement is
deferred on a condition its own author wrote, and that condition is now met.** The
honest resolutions are to build it or to restate the condition as "when concurrency is
reachable from the operator's surface" — and the second is a decision that belongs in
ADR-0024, not a silence. Either way the tree should stop claiming a trigger that has
fired. This is a lower-priority item than §4 implies, and it is listed first in §5 only
because it is cheap to *decide*.

### 3.2 FR-060 resumable phase machine

The root command's help text promises a resume that does not exist at the phase level.
`sofact` with no subcommand resumes the interrogation; there is no phase state, so
"resume" after a SIGKILL means re-deriving position from whichever ledger rows happen
to exist. FR-060 asks for explicit transitions *persisted durably* and *auditable* —
which the ledger is built to hold, and which is why this is a build item rather than a
redesign.

### 3.3 FR-019 isolation differential

Scheduled in [neighbouring §3] as "worth adding to the probe rather than assuming". The
probe already has the second-child machinery for the rows that need one.

**Done 2026-10-12.** `HarnessCapability.STORE_ISOLATED` is the eleventh row, and it is a
differential *with a control arm*, because one arm cannot answer the question: both arms
run the same goal in their own workspace with `HOME` pointed at a fresh empty directory,
and they differ in exactly one thing — whether the spec's declared containment variables
(`HarnessSpec.isolation_env`) are applied. The isolated arm's empty `HOME` is evidence
only once the control arm has filled its own; without that the row would report
`CONFIRMED` for a harness that writes nothing under `HOME` at all, which is the
fabricated capability `ProbeOutcome` exists to prevent. Canaried by deleting the
control-arm branch and watching `test_the_control_arm_is_what_makes_the_empty_home_mean_something`
fail.

Measured against the real `claude` spec on 2026-10-12: with `CLAUDE_CONFIG_DIR` applied
the child left its `HOME` holding **zero** files; with the variable withheld it wrote
`.claude.json`, `.claude/projects/<slug>/<id>.jsonl` and a backup. So the variable is what
contains the store.

What this does **not** decide, and the row says so in its own output: where the child may
**write** (`sandboxable` remains `ABSENT` for both `pi` and `claude`), and egress
(FR-152). A contained store and an uncontained child are both true at once, and the row
must not be read as the second.

## 4. What SoFact has that neither does

Repeating only the conclusion of [neighbouring §4], because it bounds what "relevant
capabilities" can mean: the four rows at the bottom of that table — oracle required per
clause, verdict over producer-independent evidence, autonomy ceiling from measured
oracle rank, escape attribution to the misunderstood clause — exist in neither project.
**The capability gap is real and it is not where the differentiation is.** Closing these
twelve rows does not move SoFact toward being Paperclip, and it must not be mistaken for
progress on the thing SoFact claims. The four rows at the top of §3 are the ones that
matter, and all four are SoFact's *own* requirements — which is the useful reading of
the operator's request: the neighbours are not a feature list to copy, they are
independent evidence about which of SoFact's unbuilt requirements are load-bearing.

## 5. Build order

Dependency-ordered, largest lever first:

1. ~~**FR-060 phase state machine + resume** (§3.2)~~ — **done 2026-10-12**, ADR-0030.
   Phases are a state machine in the ledger, `sofact phase` reports position and exits
   non-zero while a gate is open, and a restart reads the phase off disk. FR-061 is now
   structural: a completed gate phase cannot be constructed without an approver, and P5
   is unreachable without P2 and P3.
2. ~~**The P2 gate** (roadmap gap 1, FR-076–086)~~ — **done 2026-10-12**, ADR-0031.
   Not on the original list, and it should have been: item 1 unblocked it, and it was the
   roadmap audit's top-ranked gap. `sofact specify` derives requirements one per clause
   and gates on the model, non-goals, assumptions and value hypothesis. What remains of
   that gap is FR-115/FR-116 — the P7 conformance check and system-level criteria now have
   a model to conform against and conform nothing yet.
3. ~~**FR-019 isolation differential row** (§3.3)~~ — **done 2026-10-12**. The
   `store_isolated` row is a differential with a control arm, so "an isolation variable
   is not a boundary" is measured rather than assumed. It narrows §3.1's hazard without
   closing it: a contained store is not a confined child, and `sandboxable` still reads
   absent.
4. ~~**FR-141 worktree per module** (§3.1)~~ — **done 2026-10-12** (ADR-0033). The
   worktree is per module, the main tree holds the integration line, and `--concurrent`
   is an operator flag. A wave is isolated only when every step in it is owned by a
   distinct module, because both failure modes are directory collisions: a module-less
   step has no worktree to be given, and two steps of one module share a branch. This is
   also what unblocked item 5 — a rollback is only safe once the tree is isolated.
5. ~~**Ledger rollback to a chosen entry** (§2.1)~~ — **done 2026-10-12** (ADR-0034).
   `sofact rollback --to N --reason ...` records a `cut.recorded` row and the fold reads
   through the target, skipping the range it hides and folding everything after the cut
   normally. Nothing is deleted: the log grows, the chain still verifies, and the work the
   rollback hides stays readable — which is the difference between this and a snapshot
   restore, and the reason the row above is "stronger" rather than "covered".
6. ~~**FR-070 addressable source ledger** (§2.4)~~ — **done 2026-10-12** (ADR-0035).
   `Source`/`Claim`/`Contradiction`/`SourceLedger` are types, the producer's
   `research-sources/*.md` and `research-claims.json` artefacts are read into them by
   `sofact.research`, `sofact sources` prints the ledger and records it as a
   `source_ledger.recorded` row, and the claim-to-source edge is derived rather than
   remembered — `SourceLedger.resting_on("S01")` is the set a source's invalidation
   takes with it. The ledger is versioned, so a re-stated one appends rather than
   replaces.

Items 1–3 are the answer to the operator's request, in the order that serves the rest
of the roadmap rather than the order the request was phrased in. Items 4–5 are the two
rows where the vendor's version is *weaker* than an FR SoFact already has, and they were
listed so the gap is recorded rather than rediscovered. **All six are now built**, so
the build order is complete and the remaining vendor-side gaps are the ones §2.4 records
as deliberately out of scope rather than as work.

## 6. What this note does not settle

- **Nothing here was executed.** Both sources are READMEs. A capability the vendor
  describes badly and one it does not have are indistinguishable from here.
- **"Relevant" is a judgement, and §2.4 is where it is contestable.** I have ruled
  Paperclip's company-simulator subsystems out of scope on the grounds that §1.3's
  envelope is a platform. If the envelope widens, six rows in §2.4 change disposition
  at once, and they change from *not applicable* to *gap*.
- **FR-124 is the row that decides the multi-org question**, and it is unbuilt. Reading
  `current_goal()` as "not applicable" is correct only while one operator drives one
  goal per state directory.

## Sources

- `docs/sources/s26-openrig.md` — [S26], archive at `docs/sources/archive/s26-openrig-README.md`
- `docs/sources/s27-paperclip.md` — [S27], archive at `docs/sources/archive/s27-paperclip-README.md`
- `docs/research/neighbouring-orchestrators/README.md` — the ledger defect and §4's differentiation table
- `docs/research/roadmap-gap/README.md` — the FR audit this note's dispositions are drawn from
- `docs/adr/0024-branch-per-step-is-built-worktrees-are-deferred.md` — the deferral §3.1 fires
- `docs/adr/0033-a-worktree-is-per-module-and-a-wave-is-isolated-only-when-every-step-has-one.md` — the record that closed §3.1
- `docs/spec/product-spec.md` — FR-059, FR-060, FR-070, FR-094, FR-117, FR-120, FR-140, FR-141, FR-148, FR-165, NFR-024
