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
property the vendor's lacks. Five are real gaps against SoFact's own requirements, and
three of the five have a *deferral whose stated condition has since fired*. Four are
refused with a spec reason, and four are not applicable because the vendor's scope is
broader than SoFact's and the extra scope is a company simulator's, not a factory's.

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
| Durable audit log | SQLite + `bundle-audit.jsonl`; Postgres "durable activity" | The ledger: append-only, hash-chained, 18 `LedgerKind`s (`views.py:1848`), `require_intact` before every fold | **Covered, stronger** — tamper-*evident*, which neither vendor claims; the chain is the reason FR-003 is a hard error rather than a log line |
| Revision + rollback | snapshot/restore; "revisioned config with rollback" | `Decomposition` revisions + `decomposition_hash`; approving a superseded revision is refused (FR-094) | **Covered, partly** — revision yes; there is **no operator rollback verb**. `grep -rn rollback src/` returns nothing. Over an append-only fold this is cheap: replay to a chosen entry index |
| Goal ancestry / traceability | culture + continuity; "goal ancestry" | `decomposition.gate` checks traceability both directions (`decomposition.py:423,438`) | **Covered** — Paperclip carries ancestry for agent *context*; SoFact carries it for escape attribution (FR-127). Same mechanism, different purpose |

### 2.2 Durability and resumption

| Capability | Vendor evidence | SoFact status | Disposition |
| --- | --- | --- | --- |
| Explicit phase state machine, resumable | `rig up`/`rig down`; snapshot/restore | No state machine. Phases are implied by which ledger rows exist; no `init`/resume verb. The root command's help says "run `sofact` to resume" — and what resumes is the *interrogation*, not a phase | **Gap — build** (FR-060): "Phase transitions must be explicit state machine transitions, persisted durably, auditable, and **resumable after SIGKILL** at any point." This is SoFact's own requirement, unbuilt |
| Per-node restore outcomes, incl. "cannot resume" | `resumed`, `fresh-primed`, `awaiting-decision`, `attention_required`, `failed` | `StepOutcome` is four members; a recordless session reads `completed` (measured) with a caveat in `note` | **Covered in part** — the caveat is now printed for every outcome, so the *reporting* half is done. The five-state vocabulary remains a fair shape for a future state meaning "the work may have happened and cannot be recovered"; see [neighbouring §2] |
| Snapshot / restore of a whole rig | `rig snapshot`, `rig restore` | The ledger *is* the snapshot: `state.fold` reconstructs everything. But there is no verb that materialises a restored workspace, and no per-node outcome | **Gap — build**, and it is the same gap as FR-060: a fold that cannot be re-entered is a snapshot without a restore |
| Discovery / adopt of existing sessions | `rig discover`, `rig adopt` (fingerprints live tmux sessions) | Sessions are factory-created under `<home>/sessions/<module>` (`service.py:836`) and disposable; state is the ledger | **Not applicable** — adopt exists because OpenRig's state lives *in* live tmux sessions. SoFact's does not, which is the property that makes a killed session survivable |

### 2.3 Isolation and integrity

| Capability | Vendor evidence | SoFact status | Disposition |
| --- | --- | --- | --- |
| Producer isolation by enforced boundary | tmux + workspace trust; Paperclip workspaces & runtime | `CLAUDE_CONFIG_DIR`, `OPENCODE_DB`+`OPENCODE_TEST_HOME` as env vars; `--standalone` measured to matter (ADR-0028). No worktree | **Gap — build** (FR-141 + FR-059). See §3.1: the deferral's condition has fired |
| "An isolation variable is not a boundary" | stated outright: `OPENRIG_HOME` alone does not isolate provider config | The probe has `_probe_concurrent` machinery (FR-019/FR-165) but **no row asserts the private store was honoured** | **Gap — build** — scheduled in [neighbouring §3], still unbuilt. A spec field that *looks* like isolation and has never been observed to isolate is the exact hazard S26 names |
| Imported-bundle SHA-256 integrity | `RigBundle`, `bundle-audit.jsonl` | No import mechanism at all, so nothing to protect. The archive discipline for *sources* is a human process (`docs/sources/archive/`, global rule) | **Not applicable** — and if a bundle import is ever built, this row becomes a build item, not a nice-to-have |
| Multi-organization isolation | "Company-scoped access checks keep each organization's work, agents, and activity separate" | One goal per state directory; `current_goal()` returns the most recent (`service.py:297`) | **Not applicable now** — S27 says the same. It becomes relevant at FR-124 (per-deployment topology ceilings), which is itself unbuilt |

### 2.4 Presentation, surface, and posture

| Capability | Vendor evidence | SoFact status | Disposition |
| --- | --- | --- | --- |
| Machine-usable surface (MCP server) | OpenRig ships an MCP server | The CLI is the only surface (`cli.py`; 20 commands) | **Gap — build** (FR-120): "SoFact must produce the system so that it is **machine-usable** as well as human-usable: a documented, stable API surface." Note the requirement's subject is the *delivered* system; SoFact's own surface being CLI-only is the same defect one level up, and P8 (FR-117) is unbuilt regardless |
| TUI | OpenRig ships one | None; `typer` commands printing to stdout | **Refused** — a TUI is apparatus cost against F6/[S10]; FR-120 asks for a machine-usable surface, and a TUI is the opposite of that |
| Provider-usage / context-usage tracking | `provider-usage`, `context-usage` under `OPENRIG_HOME` | Per-dispatch `tokens_observed`, `wall_clock_seconds`, `continuations_observed` (`views.py:1672`) | **Covered** — narrower than the vendor's (no per-provider aggregation, no attempt-level rollup, which the roadmap audit already records under FR-102) |
| Culture / `CULTURE.md` | layered norms onto a default team | `_SHARED_CONSTRAINTS` (`planner.py:110`) + goal text + contract clauses | **Covered** — the same idea with a difference that matters: SoFact's constraints are compiled from the contract and pinned by hash (FR-096), so a norm cannot drift from the artefact it governs |
| Context library | a library under `OPENRIG_HOME` | `docs/` + the spec + the ledger | **Covered, weaker** — SoFact has no *addressing* mechanism for its own context; FR-070 (addressable claims) is the stronger version and is unbuilt |
| Telemetry on by default | anonymous telemetry, documented opt-outs; opt-in OTel | None | **Refused by default** — NFR-024 argues for recording what was observed, not for shipping observations off-box. If telemetry is ever added, it is opt-in, and it must not carry prompt text (S26's own payload rule) |
| Routines & schedules, heartbeat execution, work & task system, secrets & storage, company portability, org chart | Paperclip's 12 subsystems | Not in scope | **Not applicable** — these serve "run a company made of agents". SoFact's unit is a contract handed to a session, and §1.3's envelope is a platform, not an org |

## 3. The three deferrals whose condition has fired

This is the part of the note worth acting on. A deferral is a claim that the tree is
correct *for now*; when the trigger it named is met, the claim is false and nothing
fails to tell you.

### 3.1 FR-141 worktree-per-module

ADR-0024 defers worktrees, and the spec's own table states the condition: FR-141 is
deferred "until a wave runs concurrently or a plan spans more than one module"
(`product-spec.md:1240`). ADR-0024 §3 states it again as "whichever comes first".
**The multi-module half has fired, and the concurrent half has fired at the API but not
at the surface.** Measured:

- `dispatch_plan(concurrent=True)` exists and `asyncio.gather`s a wave
  (`service.py:1038`), but **the CLI has no flag for it** — `grep -n concurrent
  src/sofact/cli.py` returns one hit and it is a print of the word "concurrent" for a
  wave heading. So the operator cannot turn concurrency on; only a test can, and one
  does (`test_service.py:802`). ADR-0024's "the operator owns" is currently the
  operator being unable to choose.
- A plan spanning more than one module is not merely possible, it is the case
  `_module_for` was written for: it resolves a step's branch from its clauses, and its
  own docstring names "a step whose clauses span two modules" as a real input
  (`service.py:904`). Any decomposition with two modules produces one.

ADR-0024 §5 is the reason this matters at zero parallelism, and it is the strongest
argument in that record: *"An oracle runs against a workspace. Two sessions sharing one
means clause A's verdict is polluted by session B's edits, and the factory loses the
ability to say whose work a green light describes — which is FR-138 and FR-006. That
argument holds with zero parallelism."* The ledger lock (ADR-0029) protects the **log**;
nothing protects the **checkout**. Fixing the log and leaving the tree unguarded fixes
the cheaper half of the same race.

`grep -rn worktree src/` returns four hits and every one is a comment saying it is
deferred — including `harness.py:732` and `harness.py:1685`, where the *probe* tells the
operator that real confinement is elsewhere.

### 3.2 FR-060 resumable phase machine

The root command's help text promises a resume that does not exist at the phase level.
`sofact` with no subcommand resumes the interrogation; there is no phase state, so
"resume" after a SIGKILL means re-deriving position from whichever ledger rows happen
to exist. FR-060 asks for explicit transitions *persisted durably* and *auditable* —
which the ledger is built to hold, and which is why this is a build item rather than a
redesign.

### 3.3 FR-019 isolation differential

Scheduled in [neighbouring §3] as "worth adding to the probe rather than assuming". The
probe already has the second-child machinery for the rows that need one. Unbuilt.

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

Dependency-ordered, cheapest first where the order allows:

1. **FR-141 worktree per module** (§3.1) — the condition has fired, the race is live at
   zero parallelism (ADR-0024 §5), and `git worktree add` is already the tool. It
   unblocks honest concurrency, and it is also what lets `concurrent` become an operator
   flag rather than a test-only parameter.
2. **FR-019 isolation differential row** (§3.3) — a probe row, not a subsystem; makes
   the isolation claim measured rather than asserted, which is what FR-148 requires.
3. **FR-060 phase state machine + resume** (§3.2) — the largest of the three; it is
   also the prerequisite for a P2 gate (FR-080) and for FR-062's "every phase emits a
   durable artifact".
4. **Ledger rollback to a chosen entry** (§2.1) — an operator verb over the fold;
   pairs with FR-094 and is what Paperclip's "rollback" is. Small, and only safe once
   the tree is isolated (item 1).
5. **FR-070 addressable source ledger** (§2.4) — the stronger version of the durable
   activity log both vendors ship; already recorded as unbuilt in the roadmap audit.

Items 1–3 are the answer to the operator's request. Items 4–5 are the two rows where
the vendor's version is *weaker* than an FR SoFact already has, and they are listed so
the gap is recorded rather than rediscovered.

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
- `docs/spec/product-spec.md` — FR-059, FR-060, FR-070, FR-094, FR-117, FR-120, FR-140, FR-141, FR-148, FR-165, NFR-024
