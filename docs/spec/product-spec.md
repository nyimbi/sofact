# SoFact — Product Specification

| | |
| --- | --- |
| **Document** | `docs/spec/product-spec.md` |
| **Version** | **0.4** — objective restated; plugin-admission discipline (supersedes 0.3, 0.2, 0.1) |
| **Date** | 2026-09-12 |
| **Status** | Draft for review. Contains 13 open decisions (§22) gating the build; D1 superseded, D11/D14/D16 resolved. |
| **Name** | **SoFact.** Display name is SoFact; the CLI binary, package, and repository slug stay lowercase `sofact` — lowercase is a packaging constraint, not the product name (D14 resolved). |
| **Grounded in** | `docs/research/findings.md`, `docs/sources/` (S01–S24) |

## What changed in 0.4

Two changes, and the first is a change of *objective* rather than of scope.

1. **The objective is capability, not commerce.** The operator has stated that
   commercialization is not a goal; the goal is **to imagine a product and create
   it efficiently**. §19's business case therefore moves from *constraint* to
   *optional context*, and every requirement that existed to satisfy a third party
   — multi-tenancy, attributable approval chains (FR-130), the L4 ceiling priced for
   external promises — becomes deferrable. The **mechanism** in §1.4 is unaffected
   and in fact sharpened: human attention is spent per platform, not per module, and
   for a single operator that attention is the only scarce resource there is. See
   §1.4 and D17.
2. **The verification requirement is unchanged in kind and lower in degree.** Removing
   a market removes an *oracle*: a product nobody buys fails visibly, and that
   signal is gone. SoFact's own P6 becomes the only barrier between an imagined
   product and a false one, which makes it more load-bearing — while the *strength*
   it must reach drops, because the blast radius is the operator's own afternoon
   rather than a customer's production system. Target autonomy for personal use is
   **L2–L3 with escape-rate tracking**, not L4 with θ ≥ 0.80 (D17, FR-157).

Also recorded this version: **FR-155/FR-156** (the plugin-admission deletion test;
configuration before code — §8.7), risks **R28/R29**, the source entry **[S23]** on
harness base candidates, and the measurement that `oh-my-dsh` names at least eight
unrelated repositories while `oh-my-pi` is a detached hard fork of `pi`.

Recorded later in this version: source entry **[S24]** with findings **F15/F16**
and §9.5, the evolvability requirements **FR-158/FR-159/FR-160**, risk **R30**, open
decision **D18**, and **FR-161** — the harness adapter table is data, not code
(§8.5, §8.6, §17).

## What changed in 0.3

Three changes. All three narrow what SoFact must build; none removes anything from
0.2.

1. **SoFact is a meta-harness — a harness of harnesses.** It does not merely call a
   coding harness. It orchestrates **N goal-mode harness sessions**, one per module
   contract, each running unattended to completion (§8). The inner loop
   (edit → run → observe → revise, and persistence across it) belongs to the
   harness. The outer loop (contract → goal plan → dispatch → verify → integrate)
   belongs to SoFact. **SoFact contains no coding loop of its own.** This is the
   same discipline as §1.5's non-goal, applied one level deeper.
2. **`/goal` completion is a termination signal, never a verification result**
   (§8.3, FR-138). Delegating to a goal-mode agent creates a *third* instance of the
   regress in §2.3, and it is the most dangerous one, because a goal-mode harness
   reports success in exactly the shape a verification result would have.
3. **The harness is fixed; the model is not** (§8.6, D11 resolved). SoFact v1 drives
   **`dsh`** — the DeepSeek Harness [S20] — as its primary adapter, with **`pi`**
   [S18] [S19] as the second implementation. The two axes are orthogonal: `dsh`
   exposes the *loop*, *sandbox*, and *scheduler* as plugins and the *model* as a
   route, so fixing the harness does not fix the model. This is the first decision
   in this document resolved by inspecting the artifact rather than by argument.

New: §2.4, §8 (rewritten, incl. §8.6 and §8.7), §18.4, §20.4,
FR-135–FR-154, R22–R29, D15 revised, D16, **D11 resolved**.

## What changed in 0.2

v0.1 specified a **verification-first maintenance factory**: it worked on existing
repositories, inherited their test suites as oracles, and refused work it could not
verify. That product was coherent but small — its lanes were dependency bumps,
lint debt, and doc sync.

0.2 specifies an **intent-to-platform factory**: it takes a goal, interrogates the
operator, researches the problem, specifies it, decomposes it into systems and
modules, and builds a deployable platform. This is a different and much harder
product.

The v0.1 machinery is not discarded — it is *relocated*. Verification remains the
mechanism; it is no longer the whole product. Four structural changes:

| | v0.1 | v0.2 |
| --- | --- | --- |
| **Entry point** | A lane-typed intent on an existing repo | A goal in natural language, from a human |
| **Oracle origin** | **Inherited** from the repo's test suite | **Manufactured** from intent (§9.2) |
| **Human gate** | Review of each diff | Review of **spec, decomposition, and deploy** (§3.3) |
| **Coding engine** | Implicit — assumed to be built | An **existing harness** behind an adapter (§8) |

**Requirement numbering is append-only.** FR-001–056 and NFR-001–024 retain their
v0.1 meaning where their section survives; new material starts at FR-057. This
preserves the traceability chain in `docs/research/findings.md` and the source
ledger.

---

## 0. How to read this document

Requirements are numbered and **testable**: `FR-nnn` functional, `NFR-nnn`
non-functional. A requirement that cannot be checked is a defect in this document.

Confidence is marked, because not all of this is equally known:

- **(measured)** — observed on real hardware, in a real repository, or in a real
  session.
- **(argued)** — follows from cited sources but not measured here.
- **(assumed)** — a design choice requiring validation. §21 tracks what breaks if
  it is wrong.

The single most important thing to read is **§1.3 (the envelope)** and **§2.3
(ground-truth debt)**. The first bounds the claim; the second is the central
technical risk.

---

## 1. Scope and scale

### 1.1 What SoFact is

SoFact is an agentic system that converts a stated goal into a deployed software
platform. Its pipeline has four human gates and eight machine phases. It produces
**new repositories and working systems**, not patches to existing ones.

Three capabilities distinguish it from an agent harness:

1. **Elicitation** — it interrogates the operator to convert a vague goal into a
   falsifiable specification, and it refuses to proceed while the goal remains
   ambiguous.
2. **Research backstop** — it validates, invalidates, or deepens the operator's
   premise with cited external evidence *before* committing to a build (§5).
3. **Oracle construction** — it derives machine-checkable acceptance criteria from
   intent, so that every module has something to be verified against from the
   moment it exists (§9.2).

Everything else — file editing, refactoring, running tests, navigating a
repository — is delegated to an existing coding harness (§8).

### 1.2 Two modes

Both modes share the verification subsystem (§9), the autonomy router (§12), and
the escape oracle (§9.6). They differ in where oracles come from.

| Mode | Trigger | Oracle origin | Target |
| --- | --- | --- | --- |
| **Mode G — Genesis** | A goal, no codebase | Manufactured from intent (§9.2) | A new, deployable platform |
| **Mode M — Maintenance** | An existing repository | Inherited from its test suite (§13) | Verified changes to that repo |

Mode G is the primary scope of this document. Mode M is retained because it is
the same machinery at lower risk, it produces the escape-rate evidence that
calibrates Mode G's thresholds, and it is the commercially easier entry (§19).

### 1.3 The delivery envelope

"Entire platforms" is unbounded, and an unbounded claim cannot be verified or
priced. The envelope is therefore stated with numbers. **These are targets, not
measurements** — M0 (§20.3) exists to replace them.

| Dimension | v1 target | Rationale |
| --- | --- | --- |
| **Systems per platform** | 1–3 | Enough for real integration; small enough to verify |
| **Modules per platform** | 8–25 | Below the point where interface count dominates (`n²` interactions) |
| **Delivered size** | 3,000–15,000 LOC | Measurable by a human in the gates allotted |
| **External integrations** | ≤ 3 | Each adds an oracle we do not control |
| **Human gates per platform** | **4** (spec, decomposition, contract sample, deploy) | The economic claim (§1.4) |
| **Human-minutes per platform** | 180–600 | Sets the price and the ceiling |
| **Wall-clock per platform** | 2–10 days unattended | Bounded by harness throughput, not by SoFact |
| **Value hypothesis** | Declared and falsifiable (§6.4) | "Economic value" is otherwise unfalsifiable |

**FR-057** SoFact must refuse a goal whose decomposition exceeds the envelope, and
must say which dimension was exceeded. An over-scoped goal must be split by the
operator, not silently attempted.

**NFR-025** The envelope must be configuration, and every delivery must report
actuals against it. The envelope is a hypothesis under test.

### 1.4 Where human attention goes — the value argument

**The objective function.** SoFact exists to let one person convert an imagined
product into a working one, efficiently. It is not required to be sellable, and it
is not optimized for any third party's requirements. What it must do is reduce the
*operator's* time from intent to usable artifact, and refuse to produce artifacts
that only appear finished.

The reason this is worth building is not that it writes code. It is that
**human attention is spent per platform, not per module.**

| Phase | Human involvement | Scales with |
| --- | --- | --- |
| P0 Elicit | Source of intent; answers questions | **Per platform** |
| P1 Research | Reviews contradictions | Per platform |
| P2 Specify | **Gate: approves specification** | **Per platform** |
| P3 Decompose | **Gate: approves decomposition** | **Per platform** |
| P4 Contract | Samples oracle quality | Per platform |
| P5 Build *(per module)* | **None** | — |
| P6 Verify *(per module)* | Exceptions only | Sub-linear |
| P7 Integrate | Reviews integration failures | Sub-linear |
| P8 Deliver | **Gate: approves deploy** | **Per platform** |
| P9 Evolve | Monitors scorecards | Per platform |

**The consequence is counter-intuitive and it is the value case: SoFact's
economics improve as the platform gets larger.** Gates are per-platform; work is
per-module. A 25-module platform costs roughly the same human attention as an
8-module one while producing 3× the software. This inverts the v0.1 conclusion
(where review bandwidth was the binding constraint at ~4 units/hour) and it argues
for **bigger deliveries, not smaller ones** — provided the envelope in §1.3 holds
and integration risk does not grow faster than module count.

**Assumption to test.** Integration risk plausibly grows as `n²` in interfaces
while human attention grows as `n⁰`. If it does, there is an optimal platform size
and it may be small. M0 must measure interface count versus integration failure
rate; §21 R13 tracks this.

### 1.5 Not-goals

| Non-goal | Why |
| --- | --- |
| **Building a coding harness** | Existing harnesses are mature, and bespoke apparatus is the documented failure mode of every prior software-factory wave [S10]. SoFact owns specification, verification, and delivery — not file editing (§8). |
| **Fully autonomous commercial judgement** — pricing, contracts, counterparties | No oracle exists. [S16] places them at L1. Monetization is human-decided, machine-executed. (Unchanged from 0.1.) |
| **L5 / dark-factory autonomy** | Not defensible. Autonomy is a per-phase property, and four phases are human-gated (§1.4). |
| **Autonomous production deploy** | Blast radius is not machine-bounded for a deploy. Gate P8 is permanent. |
| **Autonomous decomposition** | Architecture. Machine-proposed, human-validated, always (§7.2). |
| **Being a better model** | Model- and harness-agnostic by design (§18), to avoid vendor repricing risk [S13]. |
| **Guaranteeing economic value** | SoFact can deliver a functioning, verified system. Whether it earns money is realized in the operator's market, which no oracle we can build observes. §6.4 requires a *falsifiable value hypothesis* instead of a guarantee. |
| **Being a `dsh` plugin** | It would put the verifier inside the runtime of the party it verifies, and make the product a dsh ABI dependency in the most crowded part of that ecosystem (§8.7, D16). A thin *client* plugin in v2 is a distribution surface, not the architecture. SoFact composes third-party plugins only through a frozen profile (FR-154). |
| **Replacing the customer's CI** | SoFact *uses* CI. |

**Change from 0.1.** v0.1 listed "architecture and ambiguous-requirement work" as
out of scope. That is now **in scope but human-gated** — decomposition is the
product's core technical challenge (§7), not an excluded domain. This is the single
largest scope change in 0.2.

### 1.6 The harness boundary

Explicit, because it determines what SoFact must build.

| SoFact owns | An existing harness owns |
| --- | --- |
| Elicitation and intent capture (§4) | Repository navigation |
| Research and citation (§5) | File reading and editing |
| Specification and the system model (§6) | Applying diffs / writing files |
| Decomposition and contracts (§7) | Running shell commands and tests |
| Oracle construction and measurement (§9) | The generate→run→observe→revise loop |
| Cross-module integration verification (§10) | Local context management |
| Delivery, packaging, deployment (§11) | Tool use within a task |
| Autonomy routing and the process loop (§12) | — |

**FR-058** The coding engine must be accessed through a **single adapter interface**
with at least two independent implementations, so the harness is replaceable
without changes elsewhere. Rationale is identical to the model abstraction
(FR-049): vendor risk [S13]. **v1 ships one implementation (`dsh`) plus a second
(`pi`) that exists to *test the interface*, not to hedge** — see §8.6. A third is
written only when a delivery needs it; pre-emptive adapters are apparatus cost
(F6, [S10]).

**FR-059** The harness must run inside the lane's sandbox with no access to the
oracle corpus, holdout scenarios, or factory credentials (FR-002, FR-016, FR-028).

**SoFact is a harness of harnesses.** The unit of delegation is not *a task* — it
is *a contract handed to a goal-mode harness session that runs unattended to
completion*. SoFact schedules, sandboxes, budgets, and verifies those sessions; it
does not contain a coding loop.

| Layer | Owns | Does **not** own |
| --- | --- | --- |
| **Goal-mode harness** | inner loop: edit → run → observe → revise; session persistence; `/goal` continuation | verification authority; gate decisions; its own budget |
| **SoFact (meta-harness)** | outer loop: contract, goal plan, scheduling, sandboxing, budget, independent verification, integration, delivery | file editing; code generation |
| **Human** | gates P2, P3, P4-sample, P8 | per-diff review |

**R14 (risk).** Harnesses are optimised for *patch generation against an existing
codebase*. Bootstrapping an empty repository — creating project structure, build
configuration, test scaffolding, and initial interfaces from nothing — is a
different mode and may be poorly served. See D11. Note the evidence asymmetry:
[S04] (~78.4% SWE-bench Verified) and [S05] (77.4%) measure harnesses in the *Mode
M* setting, where a repo and its test suite already exist. **There is no
equivalent benchmark evidence for Mode G**, so harness fitness for genesis work is
unknown and must be probed (M0 item 6).

---

## 2. Vocabulary

Extends §2 of v0.1. New terms marked **†**.

| Term | Definition |
| --- | --- |
| **Lane** | A bounded class of work with declared intent source, oracle, and blast radius. The unit of autonomy configuration. |
| **Oracle** | A machine procedure returning pass/fail, which the producer cannot write to. |
| **Oracle strength** | Measured ability to detect wrong behaviour. Mutation score for behavioural oracles. |
| **Blast bound** | Declared, enforceable limit on what a failed change can affect. |
| **Concerns floor** | A constraint that can only *lower* autonomy, never raise it. |
| **Verified unit (VU)** | One change that passed its oracle set and was accepted. |
| **VUHM** | Verified units per human-minute. |
| **Escape** | An accepted change later reverted, hot-fixed, or implicated in an incident. The only oracle the producer cannot influence. |
| **Autonomy level** | L0–L4 per [S16], defined by fallback responsibility. |
| **Intent clause †** | One atomic, falsifiable statement derived from the operator's goal. The unit of intent traceability. |
| **Contract †** | The artifact defining a module: interface, invariants, acceptance criteria, oracle suite, and completion criteria. Authored *before* implementation. |
| **Ground-truth debt †** | The gap between the oracles a module has and the oracles its intent requires. Genesis starts with total debt. |
| **Oracle manufacturing †** | Constructing oracles from intent rather than inheriting them from a test suite (§9.2). |
| **Decomposition †** | The mapping from intent clauses to systems, modules, interfaces, and a dependency DAG. |
| **Gate †** | A pipeline point where a human decision is required and machine progress stops. |
| **Value hypothesis †** | A falsifiable claim about the economic effect of the delivered platform, with a named instrument that would refute it. |

### 2.3 The central risk, stated once

**Ground-truth debt is the defining problem of Mode G, and it is worse than
v0.1's problem, not better.**

In Mode M, the oracle is a test suite that grew over years alongside real
failures. It is *exogenous* — it encodes knowledge the factory did not create, and
that is exactly why it can be trusted to judge the factory's output.

In Mode G, there is no such artifact. The factory must invent the acceptance
criteria, then build to them, then check itself against them. If the criteria are
wrong, every check passes and the platform is wrong — and it is wrong in a way that
looks maximally verified, because the verification was built from the same
misunderstanding as the code.

**This is the specification-level analogue of reward hacking [S15], and no internal
mechanism can close it.** The only closure is the human gate at P2 (§3.3), which is
why that gate is non-negotiable and why §7 requires intent traceability at clause
granularity: the operator must be able to see the specification *in the language of
their intent*, not in the language of implementation.

**Corollary, and it is uncomfortable: autonomous creation of new software is
plausibly harder than autonomous maintenance of existing software.** v0.1's
maintenance lanes had stronger oracles than v0.2's genesis modules can expect. The
product is bigger, but the per-module assurance is lower. Any claim that 0.2 makes
0.1's guarantees *and* new software is a false claim, and §12 refuses it.

### 2.4 The regress is recursive — it appears three times

The same structure recurs at every delegation boundary, and every occurrence must
be handled identically: **the producer's own assessment is never the verdict.**

| Level | Producer | The producer's claim | Independent verdict | Enforcement |
| --- | --- | --- | --- | --- |
| **1** | SoFact | "this specification captures your intent" | the operator | gate P2 (FR-061) |
| **2** | SoFact | "this oracle measures the invariant" | measured strength + adversarial audit | FR-008, FR-107 |
| **3** | a harness | "`update_goal({ status: "complete" })`" | SoFact's P6 run of the oracle set | **FR-138 (new in 0.3)** |

Level 3 is the one most likely to be overlooked, because a goal-mode harness
reports success in exactly the shape a verification result would have: a
termination event, a status, a summary of what it changed. A goal-mode harness is
an **autonomous producer that reports its own success**, and the more capable it
is, the more convincing that report will be. It is still not verification.

Note the symmetry with level 1: SoFact is the *producer* at levels 1 and 2 and the
*verifier* at level 3. It occupies both chairs, which is precisely why the
authority split in FR-140 has to be structural rather than procedural.

---

## 3. The production pipeline

### 3.1 Phases and gates

```text
P0 Elicit ──▶ P1 Research ──▶ ┌─ GATE: specification ─┐
                              │      P2 Specify       │
                              └───────────┬───────────┘
                                          ▼
                          ┌─ GATE: decomposition ─┐
                          │      P3 Decompose     │
                          └──────────┬────────────┘
                                     ▼
                    P4 Contract ──▶ P5 Build ──▶ P6 Verify
                       (per module, all modules)
                                     │
                                     ▼
                          ┌─ GATE: deploy ─┐
                          │   P8 Deliver   │◀── P7 Integrate
                          └───────┬────────┘
                                  ▼
                            P9 Evolve (process loop)
```

**FR-060** Phase transitions must be explicit state machine transitions,
persisted durably, auditable, and resumable after SIGKILL at any point
(NFR-006). A platform build is a long-running job and must survive interruption.

**FR-061** A gate must be a **hard stop**. No machine work downstream of an
unapproved gate. There must be no configuration under which the factory proceeds
past an unapproved gate, because that is the one thing that makes §2.3
unrecoverable.

**FR-062** Every phase must emit a durable artifact. The artifacts — intent
clauses, findings, specification, decomposition, contracts, oracle results — are
the product's actual output, and they are re-derivable only at the cost of
re-running the phase.

### 3.2 Phase summary

| Phase | Input | Output | Autonomy | Machine-checkable? |
| --- | --- | --- | --- | --- |
| **P0** Elicit | A goal in prose | Intent clauses + open questions | L1 — machine asks, human answers | No |
| **P1** Research | Intent clauses | Cited findings; validated/invalidated premises | L2–L3 | Partially — citations are checkable |
| **P2** Specify | Intent + findings | Requirements, acceptance criteria, value hypothesis | **Gate** | Yes — criteria are machine-checkable by construction |
| **P3** Decompose | Specification | System graph, module list, interfaces, dependency DAG | **Gate** | Partially — interface conformance is checkable |
| **P4** Contract | Module spec | Per-module contract + oracle suite + measured strength | L2 | Yes — strength is measured |
| **P5** Build | Goal plan (§8.4) | Module implementation, built by harness sessions | L3–L4 | Yes — via P6, never via harness self-report (FR-138) |
| **P6** Verify | Module + oracles | Oracle result set | L4 | Yes |
| **P7** Integrate | Verified modules | Assembled system, contract-tested | L2–L3 | Yes — cross-module contracts |
| **P8** Deliver | Assembled system | Deployable artifact, IaC, docs | **Gate** (deploy) | Partially |
| **P9** Evolve | Scorecards + escapes | Lane adjustments, backlog | L3–L4 | Yes |

### 3.3 Why exactly four gates

Each gate is at a point where a machine cannot decide because **there is no
ground truth to check against**:

- **P2** — no oracle exists for "this specification expresses your actual intent."
  It is a lossy compression of something only the operator holds.
- **P3** — no oracle exists for "this decomposition is the right architecture."
  Any decomposition can be made to satisfy the specification.
- **P4 (sampled)** — oracle strength is measurable, but "this oracle measures the
  right thing" is not.
- **P8** — deploy has unbounded blast radius.

Gates are deliberately **not** placed at P5/P6. Adding a per-module human gate
would restore the review bottleneck v0.1 identified and destroy the §1.4 economic
argument. The bet is that reviewing 4 artifacts per platform is cheaper and
higher-leverage than reviewing N×M diffs. This bet is testable (§20.3) and it is
the product's central empirical claim.

---

## 4. Elicitation — the Socratic phase (P0)

**FR-063** SoFact must not accept a goal as buildable until it has been reduced to
**intent clauses**: atomic, falsifiable statements in the operator's own domain
language.

**FR-064** Elicitation must be **adversarial to ambiguity**, not agreeable. It must
ask questions that discriminate between materially different builds — not
clarifying pleasantries. Specifically, for each intent clause it must resolve:

| Dimension | Question asked until answerable |
| --- | --- |
| **Goal** | What decision or action does this enable? What changes if it exists? |
| **Success** | What observable outcome means it worked? Who observes it? |
| **Scope boundary** | What is explicitly *not* included? |
| **Scale** | How many users/entities/records? What is the growth expectation? |
| **Constraints** | Regulatory, data residency, latency, budget, existing systems to integrate |
| **Non-negotiables** | What must not change or be touched? |
| **Failure** | What does unacceptable failure look like? What is the cost of one? |

**FR-065** The elicitation must **terminate**. It must converge when every intent
clause is falsifiable and the §1.3 envelope dimensions are determined, and it must
report any dimension it could not resolve as an explicit risk rather than
inventing an answer.

**FR-066** The elicitation must **not** propose implementation. Its output is what
and why, never how. Proposing architecture during elicitation anchors the operator
and corrupts P2/P3.

**FR-067** Ambiguity must be **quantified**: each intent clause carries a
`confidence` and a `verification_method` (how we will know it was satisfied). A
clause with no verification method is not a clause; it is a wish and must be
returned to the operator.

**Design note.** This is the phase that determines whether the product works at
all. §2.3 says the operator's review of the specification is the only ground truth
for correctness of intent. If elicitation produced a plausible-sounding but
unfaithful specification, every downstream guarantee is worthless, and the failure
is silent. Elicitation quality is therefore a *first-class product metric*
(§20.1: specification acceptance rate, clauses reopened after approval).

---

## 5. Research — the validation backstop (P1)

The operator's premise is often wrong, and building on a wrong premise is the most
expensive failure available: it is discovered at P8, after every module has been
built and verified.

**Research is a cheap probe on the viability of the intent, and its purpose is to
fail fast.**

### 5.1 Requirements

**FR-068** Every intent clause must be classified by the research phase into one
of four verdicts, with cited evidence:

| Verdict | Meaning | Action |
| --- | --- | --- |
| **Validated** | External evidence supports the premise | Proceed |
| **Invalidated** | External evidence contradicts it | **Return to P0.** Do not build. |
| **Unverifiable** | No evidence either way | Proceed as an explicitly flagged assumption |
| **Deepened** | Evidence reframes the problem | Revise clauses, return to P0 |

**FR-069** Every finding must carry **provenance**: a URL or citation, a retrieval
date, a verification status, and a confidence. Uncited claims must be labelled as
opinion and must not support a decision.

**FR-070** The research output must be a **versioned source ledger** — one entry
per source, with a precis, the claims it supports, and an explicit
information-quality critique. Claims and sources must be separately addressable,
so that invalidating a source invalidates the claims resting on it.

**FR-071** The research phase must actively seek **disconfirming** evidence, not
corroborating evidence. A research phase that only finds support is a
rationalisation engine, and must be detectable as such: report the count of
disconfirming sources found.

**FR-072** Research must be **bounded**: a declared budget of sources, time, and
model calls per intent clause. Unbounded research is a way to never build.

**This is measured, not argued.** The source ledger and findings synthesis in
`docs/sources/` and `docs/research/findings.md` were produced by exactly this
procedure, by hand, in a single session — including the practice of recording
verification status honestly (`reported`, not `verified`) and critiquing each
source's commercial interest. That work is the **reference implementation** of this
phase, and its structure is the specification for the automation.

**That automation exists as of ADR-0035.** `sofact sources --from-run <id>` reads a
run's `research-sources/` directory and its `research-claims.json` and records a
`SourceLedger` in the log: `Source` and `Claim` are separate addressable types, the
edge between them is derived (`resting_on`), and a claim citing a source the ledger
does not hold is refused at construction rather than at read time. `docs/sources/`
stays the reference implementation and is now the *slower* way to produce a ledger,
not the only one.

**The one thing the automation deliberately does not derive is `supports:`.** The
obvious way to fill that field is to walk this specification for citations, and the
walk was measured before it was built: of the 21 sources cited here, 5 ([S18], [S19],
[S20], [S23], [S24]) appear only in prose outside any requirement. A citation walk
would attribute those to nothing and report a complete ledger over an incomplete
derivation. The edge FR-070 asks for therefore runs source-to-claim *inside* the
ledger, where the producer states it, rather than spec-to-source, where it would be
guessed.

**And the verdict is an artefact as of ADR-0037.** `sofact classify --from-run <id>`
reads a run's `research-classification.json` and records a `ResearchClassification`:
one `ClauseClassification` per intent clause, each carrying its verdict, its rationale
and its evidence. Two things about the table above are load-bearing rather than
descriptive.

**The Action column is data.** `VERDICT_ACTION` maps each verdict to its action, and
three readers read it: the type (`ClauseClassification.action`), the CLI (which prints
the action beside every verdict), and `advance_phase`, which **refuses to complete P1**
while the current classification returns to P0 — naming each stopping clause and its
verdict. A verdict that says *do not build* therefore cannot be printed as a finding for
a reader to act on or not; the pipeline does not advance over it.

**The clause list is the operator's, not the producer's.** `research_goal` writes the
draft's clause ids and statements into the prompt, and the check measures "every clause
is classified" against the draft's stems. A producer that classified one of five clauses
is measured against the five it was given, rather than passing by being asked about
itself.

**Unverifiable's action is what makes it falsifiable.** The verdict becomes an
`Assumption` whose `refuted_by` is the classification's `settled_by`, so a producer that
cannot name what would settle the question has not produced an Unverifiable verdict at
all — FR-079's rule that "an assumption without a refuting observation is a belief",
applied to the one verdict whose action is to proceed. An Unverifiable verdict that
*cites evidence* is refused at construction, because "no evidence either way" is a
statement about absence. An unknown verdict is refused rather than defaulted, since
Unverifiable is the one verdict whose action is *proceed* and so the one wrong default.

### 5.2 Where the research engine must exceed the manual reference

**FR-073** The automated engine must additionally perform **contradiction
detection**: flag where two cited sources disagree, because that is where the
operator's decision actually is.

**FR-074** It must distinguish **evidence from positioning**. Vendor content,
manifests, and marketing must be classified and prevented from supporting a
decision on their own (as `S03`/`S17` are in the ledger).

**FR-075** It must **detect its own staleness**. Model landscapes and vendor terms
change fastest of anything in this domain; findings must carry expiry where the
claim is time-sensitive.

---

## 6. Specification (P2) — the first gate

### 6.1 Requirements

**FR-076** The specification must be expressed as requirements, each traceable to
one or more intent clauses. **FR-077** Every requirement must have a
**machine-checkable acceptance criterion**. A requirement without one is a defect
in the specification and must block the P2 gate.

**FR-078** The specification must include the **system model** [S07]: entities,
relationships, state machines, invariants, and external interfaces — not just a
requirement list. This is what makes P3 decomposable and P6 verifiable, and it
gives the factory a second oracle class (O3 structural) that does not require
running code (§9.2).

**FR-079** Every specification must declare its **non-goals** and its
**assumptions**. Assumptions are the load-bearing uncertainty and must be visible
at the gate, not buried.

**FR-080** The P2 gate must present the specification **in the operator's
language**. An operator who cannot evaluate a specification cannot discharge the
§2.3 responsibility, and the gate becomes theatre.

### 6.2 Specification completeness

**FR-081** The specification must be checked for **internal consistency** before
the gate: no two requirements may contradict; every entity in the model must be
referenced by a requirement; every requirement must map to at least one module in
P3.

**FR-082** The specification must be checked for **testability**: for each
requirement, a demonstration that the acceptance criterion can be mechanically
evaluated. Where it cannot, the requirement must be marked `human-verified` and
its verification cost counted against the human budget (§1.4).

### 6.3 The system model as an artifact

Per [S07], agents operating on raw text lose the invariant information needed to
verify anything a test does not exercise. The model is therefore not documentation
— it is the **input to decomposition** and the **substrate for structural
oracles**.

**FR-083** The system model must be machine-readable and must be the single source
for interface definitions. Hand-written interfaces that disagree with the model are
an integration defect by construction.

**FR-084** The model must be updated as part of any change. A change that alters
behaviour without updating the model must fail verification. This makes the model
self-enforcing rather than aspirational — the reason MDSE historically failed was
that the model drifted and nobody paid for the drift.

### 6.4 The value hypothesis

**FR-085** Every specification must declare a **falsifiable value hypothesis**:
what economic effect the platform is expected to produce, for whom, and the
instrument that would refute it.

**FR-086** SoFact must **not** certify the value hypothesis, and must state
explicitly in its delivery report that it verified *requirements*, not *value*.
Conflating the two is the product's largest credibility risk (R15).

---

## 7. Decomposition (P3) — the hard problem

### 7.1 Why this is the crux

Decomposition determines interface count, coupling, integration risk, and
whether the platform can be verified incrementally. **It is architecture, and
architecture is [S16]'s L1 by definition** — there is no oracle for "this is the
right decomposition," only for "this decomposition satisfies the specification,"
which many decompositions do.

Everything downstream inherits the decomposition's quality. A bad decomposition
produces modules that are individually correct and collectively incoherent, and no
amount of per-module verification detects that.

### 7.2 Requirements

**FR-087** Decomposition must be **machine-proposed and human-validated**. The
factory proposes systems, modules, interfaces, and a dependency DAG; the P3 gate
requires operator approval. Proceeding without approval must be impossible
(FR-061).

**FR-088** The decomposition must be **traceable**: every module maps to ≥1
requirement, and every requirement maps to ≥1 module. Orphans in either direction
must block the gate.

**FR-089** The decomposition must be a **DAG** with no cycles. Cycles are
integration risk and must be either broken or justified explicitly at the gate.

**FR-090** Each module must declare its **interface** and its **dependencies by
interface only**. A module must not depend on another module's internals —
enforced at integration (§10), not merely intended.

**FR-091** The decomposition must **minimise interface surface**, and must report
the interface count. Rationale: interface count drives integration risk, possibly
as `n²` (§1.4). Interface count is therefore a first-class metric and a gate
input.

**FR-092** The decomposition must declare a **build order** (topological). This is
what makes P5/P6/P7 incremental: each module can be verified against its declared
contracts before its dependents exist, using generated contract stubs.

**FR-093** Each module must have **completion criteria** (its Definition of Done) —
the user's "determine what a completed module should do." This is the contract
(§7.3) and it is the precondition for P5. A module without completion criteria is
not eligible to be built.

**FR-094** The decomposition must be **revisable without invalidating the whole
build**. When the operator rejects part of a decomposition at the gate, the factory
must propose a revision affecting the minimum module set, and must report which
already-built modules are invalidated.

### 7.3 The module contract

The contract is the artifact that makes autonomous module construction possible.
It is authored at P4, before any implementation, and it is the *only* thing P5 is
given.

```yaml
module: ledger-core
intent_clauses: [IC-003, IC-007]
requirements: [REQ-011, REQ-012, REQ-019]
interface:
  kind: library
  operations:
    - name: post_entry
      signature: "post_entry(entry: Entry) -> Result[EntryId, PostError]"
      invariants:
        - "sum(debits) == sum(credits) for every posted transaction"
        - "post_entry is idempotent on idempotency_key"
      errors: [UnbalancedError, DuplicateKeyError, ClosedPeriodError]
state:
  machine: "draft -> posted -> reconciled -> closed"
  invariants:
    - "posted entries are immutable"
    - "no entry may be posted into a closed period"
completion_criteria:            # Definition of Done — FR-093
  - "every operation has a passing contract test generated from `interface`"
  - "all declared invariants are property-tested over >= 10k generated cases"
  - "state machine transitions are exhaustively tested, including illegal transitions"
  - "oracle strength >= theta_hi on this module"
  - "no dependency on any other module's internals (verified at P7)"
  - "public API diff is empty against the frozen interface"
oracles:                        # manufactured per §9.2
  - {ref: o1-contract-tests,  class: O1, required: true}
  - {ref: o2-property-invariants, class: O2, required: true}
  - {ref: o3-state-machine,   class: O3, required: true}
  - {ref: o5-build-repro,     class: O5, required: true}
budget:
  max_files: 30
  max_loc: 2500
  reasoning_class: throughput
```

**FR-095** P5 must be given the contract and **only** the contract — not the
specification, not the intent clauses, not the system model. This is the isolation
that makes the oracle meaningful: if the builder can read the acceptance criteria's
*derivation*, it can satisfy the derivation rather than the criterion.

**FR-096** Contracts must be frozen before P5 and must be immutable during it. A
contract change requires returning to P4 and invalidates any partial build.

**FR-097** Every contract must declare an explicit budget (files, LOC, reasoning
class). Exceeding it fails the module and escalates, on the same logic as FR-026.

---

## 8. Build (P5) — the meta-harness

SoFact does not write code and does not contain a coding loop. It writes contracts,
compiles them into harness goals, dispatches those goals to goal-mode harness
sessions, and verifies what comes back.

SoFact is the **outer loop**; each harness session is an **inner loop**; each module
gets its own session. This is the harness-of-harnesses architecture.

### 8.1 Why delegate the loop

Building a generate → run → revise loop — with checkpointing, context management,
objective re-injection, and self-tests on its own tooling — is *exactly* the
bespoke-apparatus trap [S10], and it is the thing [S08] shows is hard to get right
for multi-day runs. A mature goal-mode harness has already paid that cost, and
[S08]'s failure taxonomy (context exhaustion, drift from the objective, silent
degradation of the agent's own tooling, unrecoverable state after a crash) is
evidence about *how much* there is to get right.

What delegation costs is a new trust boundary. §8.3 is about that.

### 8.2 The goal interface, grounded in a real one

A goal-mode harness exposes at minimum: a way to set a long-running objective, a
budget, and a lifecycle (status / pause / resume / clear). **`pi-goal` 0.1.7** —
installed and inspected on this machine, recorded as ledger entry [S18], the first
`content-verified` entry in the ledger — is the reference implementation, and
several of its deliberate choices are worth copying verbatim:

| pi-goal behaviour | Why SoFact depends on it |
| --- | --- |
| Objective re-injected as message content on every continuation | Survives context compaction; [S08]'s "objective re-injection" made concrete |
| Goal state in session entries; no external database | The session is disposable and restartable |
| Reload **pauses** rather than silently resuming | No unattended zombie after a crash |
| Token budget (`--tokens`) with a budget-limited stop | A spend bound outside the model's control |
| `update_goal` accepts **only** `status: "complete"` | **Capability asymmetry** — see §8.3 and FR-140 |
| `get_goal` / `update_goal` exposed only while a goal is active | An unrelated session is never tempted to declare victory |

The last two are the design gift. The model can *only* declare completion. It
cannot pause, resume, clear, or extend its own budget — those are user or extension
authority. SoFact must reproduce this asymmetry structurally (FR-140), because it
is the mechanism that makes level 3 of the regress (§2.4) survivable.

`pi-goal-writer`'s stated goal shape — outcome, verification surface, constraints,
boundaries, iteration policy, blocked stop condition — and its note that the same
shape applies to *other* goal modes is evidence that goal mode is a **portable
idiom**, not a pi quirk. That is what makes a harness-agnostic adapter (§8.4)
plausible at all.

### 8.3 Termination is not verification (FR-138)

A goal-mode harness ends a session by declaring its objective achieved. That
declaration is **the producer's own claim about its own work** — structurally
identical to a coding agent asserting "my tests pass".

> **SoFact must never accept a harness completion declaration as a verification
> result.** It is a *trigger* to run P6, and nothing more.

The harness is expected to report its evidence — files changed, commands run, output
observed. That evidence is **untrusted input**: to be checked, not believed. FR-138
requires SoFact to record the two signals *independently* and to treat disagreement
as a first-class measurement (§20.4).

Why this matters commercially as well as technically: a harness that declares
completion at a low verification rate is not a defective *module*, it is a
defective *worker*. The response is to replace the harness, and goal-declaration
precision is the instrument that tells you to (FR-147).

### 8.4 Compiling a contract into a goal plan

A single harness session is bounded by context and token budget. A 2,500-LOC module
will not fit in one session, so the adapter must **not** dispatch one goal per
module.

**FR-136** The adapter must compile one frozen contract (§7.3) into an **ordered
goal plan**: a sequence of goal sessions whose union implements the contract, each
with its own objective, completion evidence, and budget.

Canonical plan shape:

| Step | Goal | Exit evidence |
| --- | --- | --- |
| 1 | Bootstrap: project skeleton, build config, test harness, CI entry point | build succeeds; empty suite runs green |
| 2 | Interfaces and typed stubs generated from the contract | interface conformance passes (FR-112) |
| 3 | Implement operations, one per step | that operation's contract tests pass (rank 3) |
| 4 | Satisfy invariants | property tests pass at ≥ 10k generated cases (rank 1) |
| 5 | Satisfy the state machine | exhaustive transition tests pass, incl. illegal transitions (rank 2) |
| 6 | Repair to threshold | measured oracle strength ≥ θ_hi |

**FR-137** Each goal must be rendered in the harness's goal idiom and must carry the
six-part shape [S18]: **outcome, verification surface, constraints, boundaries,
iteration policy, blocked stop condition**. SoFact does not invent this format — a
cross-harness convention exists, and the module contract (§7.3) is already nearly
isomorphic to it. **The contract must be authored so that it *serializes* into a
goal.** This is a real constraint on the contract format, and it is why §7.3
expresses completion criteria as executable evidence rather than prose.

### 8.5 Requirements

**FR-058, FR-059** apply (single adapter interface, two implementations in v1 —
`dsh` primary, `pi` as the interface's own test; harness sandboxed with no access
to oracle corpus, holdout scenarios, or credentials).

**FR-098** The adapter must support three modes: **project bootstrap** (empty repo
→ buildable skeleton), **task execution** (goal → implementation), and
**diagnostic repair** (failing oracle → fix attempt). A harness that supports only
the second cannot be used (R14).

**FR-099** **Idempotent per task**: re-running the same goal must be safe and must
not compound changes (NFR-009).

**FR-100** Build must occur on a **branch per module**, never in place (FR-025).

**FR-101** Failed builds must **escalate with diagnosis**, not retry indefinitely.
An unbounded retry loop is the most expensive failure mode available to an
unattended factory, because it consumes wall clock — the binding resource.

**FR-102** Build must report **attempt telemetry** (attempts, tokens, wall clock).

**FR-135** The harness **capability matrix** (D11) must record per candidate: goal
mode present; unattended/non-interactive operation; budget controls;
completion-signal semantics; telemetry available; sandboxability; concurrent
instances; ability to bootstrap an empty repository; whether the goal text
survives compaction; and whether the spec's declared containment variables actually
contain the child's private store (FR-019). **A harness lacking goal mode or
interactive-free operation is disqualifying for P5** (see FR-144 for the reduced
mode).

**FR-136** Contract → goal plan compilation (§8.4), with per-step budget and exit
evidence.

**FR-137** Goals rendered in the harness idiom, carrying the six-part shape, derived
from the frozen contract.

**FR-138** **Termination is not verification.** A harness completion declaration must
trigger P6 and must never satisfy it. Both signals must be recorded separately and
disagreement must be reported.

**FR-139** At completion SoFact must **re-verify that the contract, goal text, and
oracle set are unmodified** (hash against the frozen versions). A harness that edits
its own completion criteria or its tests has produced a rejected module, not a
passing one. Extends the canary mechanism (FR-003).

**FR-140** **Authority separation.** The harness may only declare completion.
Budgets, pause, resume, termination, and retry are SoFact's. Gates are the human's.
**No harness may alter its own budget or extend its own session.** Mirrors
`pi-goal`'s deliberate tool asymmetry (§8.2) rather than inventing it.

**FR-141** Concurrent sessions must be isolated by **git worktree per module**, not
by branch alone — branches share a working tree, so branch-per-module is not
sufficient isolation for parallel dispatch (FR-100). The main working tree holds the
**integration line** and the module's branch lives only in its worktree, because git
refuses a branch checked out twice; each isolated step's branch is merged back onto
that line before the next wave is dispatched, so a dependent builds on what its
dependency produced. A wave is isolated only when every step in it is owned by a
*distinct* module: a step no module owns has no worktree to be given, and two steps of
one module would share a branch and therefore one directory. Either case runs the wave
sequentially rather than partially isolated. A worktree is **containment, not
confinement** — it stops two sessions at once from seeing each other's files and does
not stop one that wanders (ADR-0023, ADR-0005). Built 2026-10-12; ADR-0033.

**FR-142** Dispatch must follow the **topological build order** (FR-092) as
**waves**: modules whose dependencies are *verified* — not merely built — may run
concurrently; a dependent must not start on an unverified dependency. Wave width
must be bounded by declared memory, token, and cost budgets.

**FR-143** Every goal session must report tokens, wall clock, continuation count,
completion declarations, and verification outcome. This is the input to
goal-declaration precision (§20.4) and to harness selection (FR-147).

**FR-144** SoFact must **degrade gracefully** where goal mode is absent: fall back
to single-shot task dispatch (one goal per plan step, no continuation), reporting
the capability loss. A harness without goal mode is usable at reduced throughput,
not unusable.

**FR-145** No phase may require an interactive prompt from the harness. A harness
that blocks awaiting input is unusable for P5, and must be **detected by the
capability probe** (FR-135) rather than hanging a build. Note that the *absence* of
a human-facing UI does not establish the absence of blocking: `dsh` ships no TUI
([S21]), yet exposes `dsh-terminal`, a **persistent PTY seam** through which the
agent can drive an interactive program and hang on it. Blocking is detected by
observation, not inferred from the interface inventory.

**FR-146** SoFact must drive harnesses it did not author and whose internals it
cannot modify. Where a harness lacks a capability, the response is a different
harness or a reduced mode — **never a fork** (FR-058, §1.5). This includes
*plugins*: a missing sandbox, loop, or scheduling plugin is a documented capability
gap, not a plugin SoFact writes (§8.6).

**FR-148** The harness **capability matrix must be discovered at runtime**, not
asserted from a static table. Extensions and plugins register their own CLI flags
and routes [S19] [S20], so a hand-maintained matrix is stale by construction — and
the harness's *own* help text is not a reliable source either: `dsh --help`
advertises a `--profile tui` that does not exist in either shipped version ([S21]).
The probe must **attempt** each capability and observe the outcome, read the
installed package manifest, and record the version it observed. Help text may
propose a probe; it may not answer one.

**Which rows a probe actually decides** (v0.1, measured):
`non_interactive` (the child either exits or had to be killed), `telemetry` (a
usage block in the record or none), `context_files_disabled` (the flag either ran
cleanly or did not), `model_resolved` (FR-164), `goal_mode` **on positive evidence
only** (FR-153), and `bootstrap_empty_repo` **on positive evidence only** — the
probe invokes the harness with its workspace as `cwd`, so a cold start is counted
*before* the child runs, and a workspace that is not empty is reported as an
unwitnessed capability rather than as a failure to bootstrap. The remaining five
rows — `sandboxable`, `concurrent`, `budget_control`, `goal_survives_compaction`,
`store_isolated` — are **attempted** (FR-165), each by a *differential* rather than
by a longer look at one run, and each reports the attempt it made even when the
answer is inconclusive.

**Two rows gate, and they gate differently.** `non_interactive` refuses dispatch
(FR-145); `model_resolved` also refuses it, but only for the model the refusal was
measured against (FR-164). `goal_mode` **downgrades** a step to single-shot and
records the capability loss rather than refusing it (FR-144). Every other row is
reported. No capability may be promoted to a gate while its probe row still reads
`INCONCLUSIVE`, and none may be demoted to a report once it decides whether a
build can run unattended.

**FR-164** The probe must report whether the harness **resolves the configured
model**, and a refusal must be **attributed before a step runs** rather than left
to surface as a session that exited non-zero and wrote no record — which is
byte-for-byte what a producer that tried and failed looks like. The check is a
measurement, not a validation: the identifier is resolved by the *harness's own
registry*, not by the model server, so a tag `ollama` serves can be one the
harness refuses, and only the child can answer. The refusal string is **data on
the spec** (`model_error_pattern`, FR-161), measured for `pi` as
`not found. Use --list-models`; a harness that declares none reports
`INCONCLUSIVE` rather than reading an unattributed failure as a model problem.
This row is decidable in **both** directions, which no other row is: a positive
observation of refusal is `ABSENT`, and a clean exit that left a readable record
is `CONFIRMED` (FR-153). A profile records the model it was probed with, and a
dispatch whose model differs from the profile's is refused, because a capability
finding describes the configuration that was measured, not the harness's name.

**FR-165** A capability row that one bounded invocation cannot decide must be
**measured by a differential**, not left as an unmeasured default. A probe is what a
dispatch is allowed to assume, so a row the probe did not attempt has to be
*indistinguishable from a row it attempted and could not decide* — and the two are
different statements about different things. Five rows are attempted this way:

- **`sandboxable`** — one child, handed a tool set that cannot write outside its
  directory, is told to work there and then to **attempt an escape** one directory
  up. The escape file appearing is `ABSENT` (the confinement did not hold); the
  inside write appearing with no escape file is `CONFIRMED`; neither is
  `INCONCLUSIVE`, because a child that did no work proves nothing either way. The
  finding **names the tool set it used**, because confinement here is SoFact's
  restriction of the producer's tools (FR-158), not a property of the harness: an
  operator can narrow the set and probe again.
- **`concurrent`** — two children run **simultaneously** with distinct session ids,
  and the question is only whether their session records land on distinct paths.
  Distinct records are `CONFIRMED`; one shared path is `ABSENT`, because a step that
  overwrote its sibling's history would destroy the evidence for half a wave
  (FR-142).
- **`budget_control`** — only attempted when the spec **declares a budget flag**
  (FR-161); a harness that declares none is `INCONCLUSIVE` *for that reason*, since
  there is nothing to attempt. Where one is declared, the same goal runs twice in two
  scratch directories — once with the flag rendered at a cap nothing can do work
  inside of, once without it — and the observable is the artefact: written under the
  cap is `ABSENT` (the flag is accepted and not honoured), written only without the
  cap is `CONFIRMED`, and neither is `INCONCLUSIVE`, because absence under a cap
  proves nothing while the uncapped run did no work. By FR-140 nothing depends on
  this row: SoFact holds the wall clock either way.
- **`store_isolated`** — only attempted when the spec **declares containment
  variables** (FR-161, `isolation_env`); a harness that declares none is
  `INCONCLUSIVE` *for that reason*, and one isolated by argv instead (`pi`'s
  `--session-dir`) is not decided by it in either direction. Where they are declared,
  the same goal runs twice with `HOME` pointed at a fresh empty directory — once with
  those variables applied, once with them withheld and every other spec variable held
  constant — and the observable is the file count under each arm's own `HOME`. The
  isolated arm empty **and** the control arm non-empty is `CONFIRMED`; the isolated arm
  non-empty is `ABSENT`, which is OpenRig's warning measured rather than quoted; a
  control arm that is also empty is `INCONCLUSIVE`, because a harness that writes
  nothing under `HOME` in any configuration has not been shown to be contained, only to
  be invisible to this instrument (ADR-0019). The **control arm is the row**: without
  it an empty `HOME` reads as containment for a harness whose store the probe cannot
  see. This row measures the *store* and not the child — `sandboxable` is where
  confinement is decided, and the two are not allowed to stand in for each other.
- **`goal_survives_compaction`** — costs no child, because it reads the **primary**
  run's own record: a declared compaction event (FR-161) with at least one turn the
  harness itself numbered is `CONFIRMED`, and either half alone is `INCONCLUSIVE`. A
  short probe goal never reaches a context limit, so this row is decided on positive
  evidence only — as FR-153 requires.

The extra attempts run **after** the primary attempt and only when the primary
actually did work (exit 0, not timed out, a readable record); a run that was skipped
says **which** of those failed, naming the primary's exit code. They never run
*concurrently with* the primary: the extras share one local model and one machine, so
contention between generations would be indistinguishable from incapability, and the
row it would corrupt is the one deciding whether anything can run unattended at all.
Each extra also gets its own scratch directory, so a stale file can never be read as
this run's evidence.

`probe --quick` skips exactly the rows that need a second child and records the skip
**in each row's own reason**, since an attempt never made and an attempt that found
nothing are different facts. `goal_survives_compaction` is not skipped: it costs no
child.

**FR-167** *(research is dispatched, not performed)* SoFact must **author the research
goal deterministically** — zero model involvement, the same discipline as a build step
— and dispatch it to a harness whose research spec is a deliberate composition, then
record the artefacts the run leaves: the report's size, the loop's own search count,
and the source URLs the report cites. SoFact performs no research of its own, exactly
as it performs no coding of its own (FR-058): the loop is delegated to the harness
([S25]). The research spec is data in the built-in table — the build spec's argv with
`--offline` and `--no-extensions` removed, and `RESEARCH_MODEL` pinned to the
operator's model — while the build spec keeps its composition freeze; a session that
needs an extension gets a spec that names it, never a default that carries everything.
**Naming an extension includes naming its tools**: the spec's `research_tools` are
appended to the producer's `--tools` allowlist, because pi's allowlist governs
extension tools exactly as it governs built-in ones — measured, an allowlist that
omits `deep_research` left the producer no way to call the loop at all, and it spent
its wall clock hand-rolling a recursive `pi` instead ([S25]).
The artefact protocol is two workspace files (`research-report.md`,
`research-meta.json`), so SoFact observes only the workspace it already observes
(FR-149) and never the extension's private store. **Sources are recorded, not
verified**: a report with no sources is the recorded shape of a truncated loop —
measured on a local model, where the extension's own 240 s ceiling binds before its
five-search floor ([S25]) — and reads *unmeasured*, never *none found* (NFR-024). The
report prose is advisory input with the same standing as a completion claim (ADR-0008,
FR-138): recorded as a signal, never consulted as a verdict.

**FR-149** Harness invocations must be **hermetic**: every flag that could cause a
session to read operator state, ambient configuration, or network resources must be
explicitly set rather than defaulted. A build that depends on an unset default is
not reproducible (NFR-009).

**FR-150** During P5 the harness must be invoked with **context-file loading
disabled** (`--no-context-files` on `pi`; the equivalent composition on `dsh`). A
module under construction can otherwise write a `CLAUDE.md` / `AGENTS.md` that a
subsequent session reads as *instructions* — a producer→builder injection vector,
and a direct route around FR-140.

**FR-151** Telemetry must be read from the **harness's own session record**, not
requested from the harness. `pi` writes a JSONL transcript at `PI_SESSION_FILE`
[S19]; `dsh` writes a typed append-only event log to JSONL or SQLite [S20].
The second is materially better for P6: its event taxonomy names `tool/call`,
`tool/result`, and `turn/end` individually, and derives LLM history from the log, so
evidence does not depend on the producer's cooperation or veracity.

**FR-152** `--offline` is **not** the FR-019 egress boundary. The flag controls the
harness's own network use; it does not prove that model traffic, tool side effects,
or plugin behaviour stayed confined. Egress denial must be enforced and *proved* at
the sandbox layer (FR-019, NFR-015).

**FR-153** Harness **goal entry must be forced, not requested**. [S21] measured that
goal mode is model-discretionary: the `goal` package was loaded and available, and
the session ran unattended to completion — but the producer never entered goal
mode, using its in-turn `todo_write` tool instead, and the session log contained
**zero goal-typed events**. SoFact must therefore *enter* goal mode by construction
(`command-goal`, the `/goal` command, or a goal-bearing session) rather than by
instructing the producer to do so, and must **verify entry from the session log**
by asserting goal-typed events. A producer that runs single-shot is not executing a
goal plan; FR-144's reduced mode is the honest fallback and must be reported as a
capability loss, not silently accepted.

**FR-154** The harness **plugin composition must be frozen, minimal, pinned, and
hash-verified** for the duration of a build, and must never be the operator's own
profile. The `dsh` ecosystem holds thousands of third-party plugins that install
from bare `github:` specs and can be mounted *into a running instance* ([S22]), so a
producer able to influence its own composition can influence its own verifier. P5
runs in an isolated `DSH_HOME` with an explicit composition: no plugin
installation, no operator-profile inheritance, and no runtime composition change
during a build. The observed composition hash is recorded with the session
(FR-149, R29).

**FR-155** A third-party plugin may enter the P5 composition **only if SoFact would
reach the same verdict without it.** The admission test is deletion:

> Remove the plugin. Does every SoFact verdict — completion, contract integrity,
> oracle strength, budget, egress — come out the same? If yes, the plugin is
> *below the trust boundary* and is admissible as a mechanical convenience. If no,
> the plugin has taken over a decision SoFact exists to make, and it is refused
> regardless of quality.

The rationale is not risk appetite; it is that a decision delegated to the
producer's own runtime is not a decision SoFact made. Producer-side checks raise
the *rate* of honest reporting and are welcome on those terms — but they are
inadmissible as the *source* of a verdict, because they are mutable by the party
they constrain (R29) and because relying on them would make the harness's honesty a
precondition of SoFact's correctness. Where a plugin and SoFact would disagree, the
plugin is a **control arm for measurement**, not an oracle (FR-107).

**FR-156** Where a capability can be obtained by **configuration** rather than by
installing third-party code, configuration is mandatory. The measured case is
telemetry: `dsh`'s default composition egresses to a vendor endpoint ([S21]), and
the correct response is to *disable the exporter*, not to install a redactor that
scrubs the export. Redaction guards a path that should not exist; it is not an
egress boundary (FR-152, FR-019). The general rule: **the cheapest safe composition
is the one with the fewest moving parts, and config is not a dependency.**

**FR-157** The autonomy target is **deployment-scoped, not product-scoped**. Where
the blast radius of a false completion is the operator's own working time — the
personal-use case (D17) — the required ceiling is **L2–L3 with escape-rate tracking**
(FR-107), and the θ_hi = 0.80 gate that admits L4 (FR-024–FR-035) must not be imposed
as a default. Where the artifact is consumed by third parties, the L4 gate applies
unchanged.

This is not a relaxation of §9; it is the same machinery with an honest threshold.
A false completion costs a third party a production incident and costs the operator
a debugging session with code they did not write — both real, neither equal. **What
does not scale down is the requirement itself:** with no external market there is no
exogenous escape signal, so P6 is the *only* thing distinguishing an imagined product
from a plausible-looking one, and FR-138/FR-140/FR-155 are therefore load-bearing at
every ceiling.

**FR-161** The harness **adapter table must be data, not code** (FR-058, FR-156). A
harness is a declarative spec — argv template, session-record glob, completion event,
usage path, goal-entry mode, environment — and adding or replacing one must be a
configuration act, not a subclass. Two implementations of FR-058's interface are
therefore **one adapter class plus two specs**, which is what keeps §8.6's portability
claim from decaying into per-harness branches. A spec file is operator input, so the
loader must **refuse, by name, every input it cannot honour**: an unknown field, a
missing required field, a field of the wrong type, a bare string where a sequence is
required, and an empty table. A misspelled `usage_reduce` that silently fell back to
the default would produce a plausible and wrong token count — worse than an error,
because nobody can see it. Default resolution obeys the same rule: explicit name, then
`SOFACT_HARNESS`, then the built-in default **if it is present in the configured
table**, then the sole entry when the table holds exactly one, and otherwise
**refuse**. Choosing among several configured harnesses by position would dispatch an
unattended build to an arbitrary producer, which is not a decision a factory may make
silently.

Both path fields — the completion-reason path and the usage path — are walked **from the
record root**, and the envelope is named explicitly when there is one: a `dsh` event is
`{seq, time, type, data}`, so its paths begin `data`; `pi` writes `{type, message}` with
no `data` block at all, so its usage path begins `message` and its token key is `output`
rather than `outputTokens`. Nothing may be stripped implicitly. The failure mode is not a
crash but a **plausible wrong answer**: a path that means "relative to `data`" reads
nothing on a harness without that block, and the probe then reports `telemetry absent`
for a harness that reports every token it spends — `unmeasured` masquerading as `none`,
which is the one direction NFR-024 forbids. This was a real defect, found by running the
probe against a real harness and noticing that an `ABSENT` row contradicted a record
already on disk, and it is fixed in the spec table rather than in a branch — the
correction was one row, which is the argument for the table being data (FR-161).

### 8.6 The harness decision (D11 resolved)

**v1 drives `dsh` as the primary harness and `pi` as the second adapter.** The
reasoning, and the case against, in full.

| | **`dsh`** — DeepSeek Harness [S20] | **`pi`** [S18] [S19] |
| --- | --- | --- |
| Integration surface | **Python SDK** (`pip install deepseek-harness-sdk`) + JSON-RPC; bundled runtime, no system Node | CLI subprocess, `--mode json` |
| Session record | **Typed, append-only event log**; `SessionEventMap` with `tool/call`, `tool/result`, `turn/end`; monotonic `seq`; history *derived* from the log; JSONL or SQLite | JSONL transcript at `PI_SESSION_FILE`; readable, not a documented event contract |
| Loop as a seam | **Yes — the agent loop is a plugin** | No |
| Sandbox as a seam | **Yes — sandbox is a plugin**; but the example composition is `danger-full-access` | OS/container level only |
| Scheduling as a seam | **Yes — scheduling is a plugin** (bears on FR-142) | No |
| Goal mode | First-party `goal` package; `/goal`, `/plan` | `pi-goal` 0.1.7, inspected |
| Other harnesses inside it | **Native** — Claude Code / Codex installable as Profile Bundles with non-interactive permission modes | Not supported |
| Replay / fork | Native, over the same event stream | Session fork/resume; no replay contract |
| Maturity | **0.1.0-rc.8, released 2026-08-13**, with an explicit all-caps breaking-changes warning | 0.1.x line, in daily use here |
| Platform matrix | Linux x64, Linux arm64, macOS 14+ arm64 | Host + Linux |
| Model routes | Plugins — any model | `--provider` / `--model`; DeepSeek available today |
| Licence | MIT | — |

The decision is not close on capability, and the reason is structural rather than
feature-counting. SoFact's differentiator is **evidence about what happened**, and
`dsh` makes the evidence a first-class, replayable, typed artifact while exposing
the loop, sandbox, and scheduler as replaceable plugins. That is the exact seam
§8.1 needs and §1.5 forbids SoFact from building. Its own idiom — a subagent is a
harness inside a harness — *is* §1.6's architecture.

**The case against, stated at full strength.** `dsh` is a developer preview one
month old whose maintainers warn in all caps that interfaces will break. For a
factory that runs unattended for days and must reproduce oracle strength across
time (NFR-009), a moving foundation is a genuine hazard — F6's apparatus cost in a
new form: not "we built too much", but "our ground moved". The mitigations are
narrow and must be honoured: **pin the version**, confine the harness-specific
surface to one module behind FR-058's interface (§16 component 7), keep `pi`
working as the escape hatch, and treat every `dsh` capability as probed rather than
assumed.

**The trap is real.** "Everything is a plugin" invites SoFact to author plugins —
which is writing a harness after all. v1 writes **none**. If a needed sandbox, loop,
or scheduling plugin does not exist, that is a capability gap recorded per D15.

**Harness ≠ model (§18.1).** Fixing on `dsh` does not fix on DeepSeek *models*:
model routes are plugins, and `pi` reaches DeepSeek models directly. The brief's
"use DeepSeek-V3" is therefore a **model** statement, and it lands on the model
axis, not this one.

`pi`'s role is deliberate. FR-058 asked for ≥2 implementations against a
hypothetical vendor change; using the harness already installed here makes the
second implementation a **real test of the interface** at near-zero marginal cost,
which is how a portability claim earns the right to be believed.

**The adapter table is data (FR-161).** The decision above is a choice of shipped
*specs*, not of classes: `dsh` and `pi` are two entries in one declarative table, and
an operator adds a third by configuration (`SOFACT_HARNESS_SPECS`) rather than by
writing Python. This is FR-156 applied to the harness axis, and it is what makes the
"two implementations" claim in the table cheap to hold: when a vendor changes, the
response is an edited spec, not a fork (FR-146). It is also why the probe (FR-148) is
written against the **spec** rather than against `dsh` or `pi` — a capability answer
belongs to a harness, and a harness the code has never heard of must still be probed
before it can be dispatched to.

---

### 8.7 The plugin question (D16 resolved)

**SoFact is not a `dsh` plugin, and v1 ships none. A thin *client* plugin is a v2
distribution surface, never the architecture.**

*Against, and decisively.*

1. **A plugin is in-process; SoFact's whole claim is out-of-process authority.**
   FR-140 divides authority: the harness may only declare completion, budgets and
   termination are SoFact's, and gates are the human's. A Cordis plugin runs in the
   same runtime as the agent loop — and the plugin set is **mutable at runtime by
   the agent**: `memorax-ai/dsh-harmony` is "a library for patching, replacing, and
   decorating DSH plugins **at runtime**"; `dsh-super-injector` hot-injects plugin
   packages into a running instance; `swaylq/dsh-genie` promotes a
   `cordis_define` dynamic package to a permanent bundle; `green-dalii/dsh-plugin-dev-skill`
   teaches any agent to author plugins to spec ([S22]). An in-process verifier is
   reachable by the party it verifies. That converts R22 from a behavioural risk
   into a structural capability, and it is the strongest argument in this document
   against the plugin route.
2. **It inverts the product boundary.** FR-058 and NFR-026 exist because the harness
   axis is where vendor risk lands [S13]. A plugin is a `dsh` dependency at *ABI*
   level, which breaks harder than FR-058's adapter, and `dsh` has never shipped a
   stable release while warning of breaking changes (R26). [S21] measured the
   adapter surface and found it narrow and clean — a subprocess over stdio
   JSON-RPC, with `base_url` injection and a mandatory explicit `DSH_HOME`. There
   is no engineering reason to reach in-process.
3. **It is a feature, not a product.** Every mechanism this spec treats as
   differentiated already exists as a free MIT plugin: evidence-gated completion
   (≥5 independent implementations), worktree isolation (built here 2026-10-12,
   ADR-0033), budget caps, wave
   scheduling, LLM-as-verifier (≥7), and meta-harness orchestration across
   harnesses including `pi` ([S22]). The marketplaces are free and the one paid
   channel is plugin licensing. Meanwhile **`elicit` occurs zero times across 4,609
   ecosystem repositories** while `gate`, `verif*`, `bench` and `audit` are
   saturated. SoFact's actual differentiator — the intent front end plus *measured*
   oracle strength — is the uncontested space, and a plugin would place the product
   in the crowded one.
4. **Multi-tenancy would be a retrofit.** T2 (cloud VM, several clients, audit
   trail) is a server shape. The plugins that attempt it are retrofitting one onto a
   single-process desktop runtime.

*For, narrowly:* distribution. `dsh plugin add`, the `#dsh` GitHub topic, and four
or more community marketplaces constitute a real and free go-to-market channel, and
native event access would simplify telemetry.

*Resolution — integration surface ≠ architecture.* SoFact is an **independent
control plane**: own process, own store, own gates, budgets, and ledger, with `dsh`
behind FR-058's adapter, driven out-of-process. In v2 SoFact may ship a **thin
plugin that acts as a client**: it forwards to the control plane over HTTP and holds
**no authority** — no gates, no budgets, no verification decisions. That is a
land-and-expand funnel consistent with D13 (the free plugin reaches P0–P2; the paid
control plane does P3–P9), it stays off the critical path, and D15/FR-146's "zero
Cordis plugins" stands for v1. SoFact builds no mechanism as a plugin; it *uses*
third-party plugins only through FR-154's frozen composition. New risks: R28, R29.

### Applying FR-155's deletion test to the measured ecosystem

The temptation is asymmetric, and that is the point. The **most** crowded ecosystem
categories (`gate` 258, `verif*` 155, `complet` 92, `evidence` 80, `budget` 25) are
exactly SoFact's authority surface — so the plugins that look like they would save
the most work are the ones that must be refused, while the admissible mechanical
ones are thin wrappers around tools SoFact already drives.

| Measured plugin | Test | Verdict |
| --- | --- | --- |
| `dsh-completion-guard`, `beforedone`, `stalegreen`, `dsh-evidence-gate`, `reliability-governor` | Fails deletion: deleting it changes SoFact's completion verdict | **Refuse as oracle.** Admissible only as an optional *producer-side hygiene* measure, off the trust path, with FR-107 measuring whether SoFact's external verification catches what the guard missed. |
| `dsh-plugin-agent-budget`, `dsh-budget` | Fails deletion: budget is SoFact's authority (FR-140) | **Refuse as authority.** Own budget accounting stays in the control plane. |
| `dsh-plugin-kit` (shared approval/session-event gates) | Fails deletion: it *is* the gate | **Refuse.** Gates are the human's (FR-140); a shared plugin makes them a dependency. |
| `dsh-git-worktree` (FR-141) | Passes deletion | **Refuse; built here instead.** It is a thin wrapper over `git worktree add`, and FR-141 is no longer deferred: SoFact drives `init`, `switch`, `config`, `add`, `commit`, `status`, `worktree add`/`list`/`remove`, `merge` and `merge --abort` ([ADR-0033](../adr/0033-a-worktree-is-per-module-and-a-wave-is-isolated-only-when-every-step-has-one.md)). What the wrapper would have to supply that SoFact does not — the integration line, the per-wave merge order, the conflict record — is the part that makes the feature safe, and it is the part a wrapper cannot see. Vetting plus pinning plus licence review costs more than the code either way. |
| `030611/dsh-telemetry-redactor` | Passes deletion, but is superseded by config | **Refuse in favour of configuration** (FR-156). See below. |
| `dsh-research-container`, egress plugins (FR-019/FR-152) | Fails: an in-process guard cannot be the boundary of the process it guards | **Refuse as boundary.** Egress confinement belongs to the container/network layer (D9). |
| `LongHorizon-Harness` (T4 split producer/evaluator) | Fails: it is an outer loop, i.e. §8's subject | **Refuse; study as prior art.** |
| `upstream-radar` (breaking-change monitoring) | Passes deletion | **Admissible** — and its existence is evidence that R28 is a real, already-productised problem. |

The telemetry row is the clearest instance of FR-156. The hazard is that the default
composition *exports to a vendor endpoint at all* ([S21]). Installing a redactor
leaves the export path in place and adds a plugin whose correctness is now part of
SoFact's egress claim. Disabling the exporter removes the path. Configuration wins
because it deletes a moving part instead of guarding one.

**What the ecosystem is actually good for** — none of which is adoption:

1. **Prior art with a negative result.** Five independent, competent attempts at
evidence-gated completion all landed *inside* the trust boundary. That is measured
support for D16 and §8.7, and it is the strongest argument available that the
distributed design space has a systematic blind spot.
2. **Capability-gap naming.** When SoFact needs something the harness lacks, D15/FR-146
requires saying so rather than papering over it.
3. **Control arms.** A plugin that claims to improve completion honesty is a
*comparison condition* for FR-107's escape rate, not a component.
4. **Distribution**, in v2 only.
5. **A warning about the distribution position.** SoFact composed as a bundle of
existing plugins *is* `oh-my-tianshu` or a suite distribution — free, crowded, and
in permanent maintenance debt for everything it bundles (F6). "Just add the
plugins" is the route to being a distribution rather than a product, and the route
is taken one justified-looking plugin at a time, which is precisely why the test
must be written down rather than judged case by case.

### 8.8 The base question — a distribution is a bigger commitment than a plugin

The operator indicated an intention to use "either `oh-my-pi` or `oh-my-dsh` as the
harness." [S23] measured both, and the finding is that **neither name presently
resolves to a single artifact:**

- **`oh-my-dsh` has at least eight unrelated repositories** spanning four kinds of
  thing — a 530-plugin capability library, an explicitly-labelled "curated
distribution, overlay not a fork," an auto-synced catalog, and standalone agents.
- **`oh-my-pi`** (`can1357/oh-my-pi`, 30,727★, MIT, npm `@oh-my-pi/pi-coding-agent`
  @ 18.1.18) is a **detached hard fork of `pi`** — GitHub reports `fork: false`
  with no parent, so it is an independent versioned product, but it is a fork of
  the D11 secondary adapter rather than a harness in its own right.

Adopting a *distribution* is a strictly larger commitment than adding a plugin, and
it is not the same decision. Three consequences follow, and none of them is about
commercialization.

1. **A distribution is somebody else's outer loop.** [S23] records a capability
   library that already ships `deep-research` (P1), `tower` (P4 dispatch with wave
   semantics *and* an in-process conflict reviewer), `fleet-orchestrator` (P4 fan-out),
   and `secret-scanner` (a pre-write `tools.guard`). If adopted, **P1, P4, T4 wave
   scheduling, and P7's conflict review largely stop being SoFact's to build** —
   which is good, and is D17's composition preference applied one level up. But two
   orchestrators on one session contend over the same budgets, git state, and event
   stream. §8's outer loop must be *reduced to the residue the base does not cover*,
   and that residue must be measured, not assumed (FR-148).
2. **You inherit the composition, so FR-155 becomes an audit rather than a filter.**
   A distribution arrives with plugins already chosen. `tower`'s reviewer is
   in-process and fails the deletion test; `secret-scanner`'s guard is producer-side
   and is admissible only as hygiene. FR-155 does not stop applying because someone
   else made the choice — it converts into an inventory of *which of SoFact's
   verdicts would change if the base were removed*, performed against `--dump-config`
   and the resolved plugin set.
3. **FR-154 and curation are in direct tension.** A distribution exists to change:
   one catalog rebuilds every four hours, and the measured candidates were pushed
   within the last two days. FR-154 requires a frozen, pinned, hash-verified
   composition (R26, R28). The reconciliation is that **SoFact pins the whole base at
   one commit and treats upgrades as governed changes** — which is correct, and which
   means the efficiency of a distribution is partly spent on maintaining a snapshot.
   That is the price, and it is still lower than building the base.

**What this does to D11.** D11's structural ground survives the reframing intact,
because it was never an economic argument: SoFact's product is evidence about what
happened, and `dsh` makes evidence a first-class typed, replayable artifact ([S20],
[S21]). `oh-my-pi` is `pi`-shaped, so it inherits none of S19's findings
automatically and would need its own session-log measurement before displacing `dsh`
on those grounds. A third observation cuts the same way: third parties are porting
`oh-my-pi` capabilities **into** `dsh` ([S23] §4) — notably an independent reviewer
subsystem — so "`dsh` plus ports" is a measurable alternative to changing base.

**Open, and blocking a base decision:** which `oh-my-dsh` repository is meant; its
licence (`LaplaceYoung/oh-my-dsh` declares none in the GitHub API response); and
whether a distribution's composition leaves any residue for §8's outer loop to own.
The honest sequencing is to pick **one** repository, pin it, and run FR-148 discovery
against it before deleting any SoFact phase on the assumption that the base covers it.

---

## 9. Verification

Retains v0.1's subsystem — the oracle classes (§9.2 below), oracle strength and
mutation scoring, adversarial audit, isolation, and the escape oracle — with one
substantial addition: **oracle manufacturing** for Mode G.

### 9.1 Requirements (retained from v0.1, unchanged in force)

**FR-001**–**FR-006** (declared oracles, read-only enforcement, canaries, audit
trail, cache invalidation), **FR-007** (O1 alone caps at L2), **FR-008**–**FR-011**
(mutation score per module, thresholds, trend), **FR-012**–**FR-015** (adversarial
audit, sampling, exploit metric), **FR-016**–**FR-020** (isolation),
**FR-021**–**FR-023** (escape oracle, automatic downgrade).

These were the substance of v0.1 and they apply unchanged. The sections are
summarised below rather than repeated.

| Subsystem | v0.1 ref | Function |
| --- | --- | --- |
| Oracle declaration & integrity | FR-001–006 | No oracle, no autonomy; canaries halt on drift |
| Oracle classes | O1–O7, §4.2 v0.1 | Seven classes, each failing differently; O1 alone ≤ L2 |
| Oracle strength | FR-008–011 | Mutation score per module gates the ceiling |
| Adversarial audit | FR-012–015 | Hacker/fixer loop, sampled, exploit metric |
| Isolation | FR-016–020 | Read-only oracle corpus, holdout never in producer context |
| Escape oracle | FR-021–023 | Reality as the exogenous oracle; auto-downgrade |

### 9.2 Oracle manufacturing (Mode G) — new

In Mode M, oracles are inherited. In Mode G they must be constructed from the
contract, and they are weaker. Manufacturing must therefore be systematic, not
opportunistic.

**FR-103** Oracle manufacturing must proceed from the contract's structure, in
descending order of reliability:

| Rank | Mechanism | Derived from | Strength |
| --- | --- | --- | --- |
| 1 | **Property-based tests** | Declared invariants | High — invariants are the intent |
| 2 | **State-machine exhaustive tests** | Declared state machine | High — illegal transitions are enumerable |
| 3 | **Contract tests** | Interface signatures and errors | Medium-high — generated, so complete by construction |
| 4 | **Metamorphic tests** | Relations between operations | Medium — catches wrongness without knowing rightness |
| 5 | **Schema/type conformance** | System model (§6.3) | Medium — O3, cheap, runs before code |
| 6 | **Example-based tests** | Operator-supplied cases | Low-medium — sample, not coverage |
| 7 | **Golden/snapshot tests** | Output of a reference run | Low — detects change, not wrongness |

**FR-104** Property-based and state-machine oracles (ranks 1–2) are **mandatory**
for any module above L2. They are the closest thing to intent in executable form,
and they are the reason genesis autonomy is possible at all.

**FR-105** Oracle manufacturing must produce a **measured** strength for every
module before P5 begins. A module whose manufactured oracle is below θ_lo must be
reported as unbuildable-at-autonomy and escalated, not built anyway.

**FR-106** Example-based oracles supplied by the operator must be **held out**
from the builder (FR-017). Operator examples are the operator's intent and
therefore the best available proxy for correctness; they are wasted if the builder
can read them.

**FR-107** Oracle manufacturing must be **adversarially audited** exactly as code
is (FR-012). A manufactured oracle that can be satisfied without implementing the
invariant is a worse defect than a missing test, because it manufactures false
confidence. This is the specific instance of R7 that Mode G introduces.

### 9.3 Ground-truth debt accounting

**FR-108** Every module must report its **ground-truth debt** (§2.3): the gap
between its oracles and its intent clauses, expressed as intent clauses that are
not covered by a rank-1–5 oracle. Debt must be a gate input at P2 and reported in
the delivery report.

**FR-109** Modules with uncovered intent clauses must not exceed L2. An intent
clause we cannot check is exactly the clause where the §2.3 failure lives.

### 9.4 Integration oracles (O8) — new

**FR-110** An eighth oracle class **O8 — Integration** must exist: consumer-driven
contract tests across module boundaries, exercised in P7. Per-module verification
(O1–O7) structurally cannot detect cross-module incoherence, which is where
multi-module systems actually fail.

### 9.5 Evolvability — the oracle we do not have

[S24] is the sharpest available objection to this whole section, and it is aimed at
SoFact's premise rather than at its details. Its argument: coding models are trained by
RLVR against bounded pass/fail rewards, that reward shape contains no term for design
quality, and the cost of bad architecture arrives weeks or months after the decision
that caused it — so the reward cannot be assigned to the action. No harness can supply
what the training objective never asked for.

SoFact **is** a harness. It therefore cannot answer this, and must not appear to try.
What it can do is refuse to convert a green suite into a claim the suite cannot
support. Three requirements follow, and the first is a refusal.

**FR-158** *(refusal)* SoFact must report **evolvability debt** as a first-class debt
term alongside ground-truth debt (FR-108), whose value in v1 is **1.0 by construction**
for every module, because no oracle in O1–O8 observes change cost. A debt of 1.0 is the
correct value, not a measurement failure. Consequently: (a) **Mode M's ceiling is L1**
until a change-cost oracle exists, because Mode M's claim is maintenance and
maintenance is precisely the unverifiable claim; (b) Mode G's ceiling is unaffected,
because Mode G's claim is obligation satisfaction — a strictly narrower and genuinely
checkable claim — and the two ceilings **must not be reported as one number**; (c) the
delivery report must state that maintainability was not verified. The defect this
corrects is real and was v0.4's: a single per-module ceiling let a green suite about
one claim silently license the other. F1 applies to the factory's own output too — **an
unverifiable property does not become verifiable by being adjacent to a verifiable
one.** ([ADR-0011](../adr/0011-the-factory-refuses-to-claim-maintainability.md))

**FR-159** *(the differential oracle)* Maintainability has no **absolute** oracle, but
decay is a **trend**, and a trend needs only a consistent measurement, never a correct
one. Where SoFact measures change cost at all, it must do so **differentially**: for a
pinned set of change units held out from the producer, record the mechanical diff
footprint per unit (files touched, hunks, lines changed, modules crossed) and track it
across the codebase's history. A rising footprint on comparable change units is
Fowler's shotgun surgery observed rather than asserted. Boundaries, stated because
over-claiming here would repeat the error being corrected: it is a **proxy** (NFR-024
applies, and it must be declared as one); it measures change *cost*, not design
*quality* (a codebase can get cheaper to change through better tests, better tooling,
or familiarity); and it is admissible only as a **trend alarm** and a Mode M ceiling
input, never as a verdict. It is worth building because it requires **no new model
capability** — which is decisive, since [S24]'s thesis is that new model capability is
exactly what will not arrive. Whether to build it is D18.

**FR-160** *(gate cost is measured, not assumed)* §1.3's 180–600 human-minute envelope
is a **budget**; every human gate must record its actual **human-minutes** and its
**rework fraction** (the share of the slice returned to the producer), and both must
appear in the delivery report (§20.2). If review is the binding constraint once
implementation is agent-driven [S24], then a factory that measures the producer's
budget but not the reviewer's is optimising its cheapest step. Same discipline as
FR-157: if it decides the ceiling, it is measured.

---

### 9.6 When a verdict is invalid, and what triggers one

FR-006 and FR-138 were both stated and only one of them was implemented. FR-006's
scoping was contradicted by an aggregation rule that existed only in code — worst-case
dominance applied across the **log's whole history** — and FR-138's trigger was absent, so
nothing ran the oracles after a declaration. Both defects are silent: a monotone verdict
looks like a strict verifier, and an untriggered check looks like an unfired one.

**FR-162** *(a verdict describes one attempt)* A verdict must describe **one execution of
an oracle set**, never the log's accumulated history. An observation must carry the
identity of the run that produced it; worst-case dominance must apply **within** an
evaluation, so a single counterexample still cannot be outvoted by corroboration; and a
result from an earlier run must never decide a later state (FR-006, carried forward
unchanged). Asking for a named run must answer the *provenance* question — "has this
clause ever failed?" — as a question explicitly distinct from the status one. The
consequence is not stylistic: a clause refuted in one attempt must be able to come out
satisfied in the next, or the repair tier (FR-103) cannot observe its own success, and
declaration precision (FR-147) reports a number produced by a missing check rather than
by a dishonest producer. Run identity is an **ordering token, not a content hash**: it
satisfies the half of FR-006 that forbids a stale result from deciding a newer state,
and it does not satisfy the half that keys a cache by the content of the change and the
oracle definition. That second half is FR-166.

**FR-166** *(a verdict whose inputs are all still present holds without re-running)*
The dispatch check must **key, then reuse**: before any oracle runs, the workspace the
session worked in is digested — a content hash over the tree, ignoring VCS metadata,
interpreter caches, dependency installs and build outputs, skipping symlinks rather than
following them — and the digest is combined with the contract hash and the oracle-set
hash. A previous verdict rendered against the same key holds without re-running, and the
reuse is committed as its own row (`verdict.reused`) naming the moment of the verdict it
stands in for, so the log shows a reuse as a reuse and never as a second measurement.
All three components are in the key because a reuse that cannot say what it held constant
cannot be audited: the contract hash includes the clause *statements*, so a reworded
clause cannot silently inherit a verdict phrased for the old words; the digest is the
change; and the oracle set is named explicitly even though it is derivable from the
contract, because FR-006 names it and a future change to that derivation should be caught
by the key rather than silently re-keying every verdict. `dispatch --fresh` bypasses the
reuse, because the cache is an optimisation and not an obligation. The cache is **not a
pass cache** — a violated verdict is exactly as reproducible as a satisfied one, and a
reused refutation still refuses the dependent wave. Reuse applies only where the artefact
is addressable: `verify` weighs the log and has no tree to digest, so it re-measures from
the recorded evidence every time. A workspace that holds no change at all between two
steps of one plan is the measured case: a plan run through one unchanged workspace
rendered one verdict and reused the rest, which is ADR-0015's redundancy cost paid
exactly once per distinct tree.

**FR-163** *(a completed session triggers a check on the whole contract, in the session's
workspace)* SoFact must run that contract's oracles **in the workspace the session worked
in** — a verdict about a different tree is a verdict about an artefact no session wrote —
whenever a dispatched session **completes**, that is, when its process exits without timing
out. Where the harness also declares completion, the **claim** and the **verdict** must be
recorded as separate rows, claim first, so that a disagreement between the producer's word
and the artefact's behaviour stays legible rather than being resolved by whichever ran last
(FR-138). **The trigger is the session's outcome, not the producer's word.** Gating the
check on a declaration makes the *default* harness unverifiable: `pi` has no completion
event at all (measured at 0.85.1, [S19]), so a declaration-gated trigger never fires, and a
run of five real sessions that produced working code recorded **zero** evidence rows while
`dispatch --all` still exited `0`. A declaration is therefore an *additional* recorded
signal, never a precondition. The check must run **every executable clause of the
contract**, not merely the clauses the step covers: under FR-162's run scoping, a partial
report would mark every unrun clause `INSUFFICIENT` and thereby destroy the corroboration
of steps that were verified a moment earlier. A session that did **not** complete (failed,
refused, or budget-exhausted) was still changing the tree and must trigger no check at all —
inventing a verdict for it manufactures a signal the producer never gave. A build command
must **exit non-zero** when nothing was verified, when a step was refuted by its own check,
or when a plan that ran to its end left the contract not clean — a green exit code for an
unverified artefact is the same lie at the shell boundary. A run the operator **capped**
(`--max-steps`) is progress rather than failure and may exit `0`, provided no step it ran
was refuted; the contract line still reports how much of the contract holds.

**The trigger was on the wrong signal, and only a live run could show it.** Two defects in
this section were found by executing the product rather than by reading it: the verdict was
monotone across the log's history, and the trigger waited for a declaration. The second one
survived its own test suite, because a synthetic harness that *declares* completion is a
harness whose declaration is exactly what a declaration-gated trigger needs — the suite
measured the rule and never measured the default harness's inability to feed it. The live
run against `pi` (five sessions, `qwen3.6:35b-mlx` via ollama, real files written, the
contract's own oracle green by hand) recorded `5 step.dispatched`, `0 evidence.recorded`,
`0 verdict.rendered`, and exit status `0`. A capability the trigger depends on must be
treated like any other capability: if the default harness cannot supply it, the trigger
must not depend on it.

---

## 10. Integration (P7) — where multi-module systems fail

**FR-111** Integration must proceed in the **topological build order** (FR-092).
Each module is verified against its declared contracts *before* its dependents are
built, using generated contract stubs. This is what makes integration incremental
rather than a single terminal event.

**FR-112** Integration must verify **interface conformance**: every module's actual
interface matches the frozen declaration exactly (FR-090). Public-API diff must be
empty.

**FR-113** Integration must verify that **no module reaches another module's
internals** — enforced by import/dependency analysis, not by convention. Violations
must fail integration.

**FR-114** Integration failures must be **attributed to the minimum violating
module set**, and the factory must attempt repair only within that set. A
platform-wide rebuild in response to a local integration failure is a throughput
defect and must be refused.

**FR-115** The assembled system must satisfy the **system model** (§6.3)
structurally — every declared entity, relationship, and interface present and
conforming. This is the point at which the model earns its maintenance cost.

**FR-116** Integration must run **system-level acceptance criteria** from P2 that
no single module can satisfy. These are the criteria that validate the
decomposition, not the modules.

**And P7 is now eight checks as of ADR-0051.** FR-115 and FR-116
were the two P7 reported as unimplemented on every run — honestly, and in a way that let
a green line read as "P7 passed" while a third of §10 was never attempted. Both now run,
and both are only as reachable as P2's specification makes them, so the report says which
state a project is in rather than smoothing the two together. FR-110's O8 check
(`boundary_contracts`) is the eighth and the one §10 does not state: it is §9.4's, and it
asks the question FR-112 and FR-113 each hold half of — whether the name a consumer
reached for across a declared edge was one the producer ever declared.

FR-115's *present* is a set comparison over declarations, never a search for the entity's
name in a producer's source: an entity names the clauses that introduced it and a module
names the clauses it exists to satisfy, so presence is decidable without reading code —
and a text search passes on an entity called `id`. The clause-to-module map is built from
the **decomposition** rather than the dispatches, because a module nobody dispatched is a
module the system is missing. The requirement's word is *structurally*, and relationships
and invariants are reported as **not** conformed on every run, passing or failing: a
relationship is a claim about two entities' interaction, and no declaration in the log
describes one.

FR-116's criterion spans **at least two clauses** — the floor is in the type, because a
one-clause criterion is a module's own obligation that P6 already checks, and accepting
it would let a decomposition validate itself against criteria it satisfies by
construction. A criterion is satisfied exactly when every clause it spans carries a
satisfied verdict, and the verdict taken per clause is the **worst across the log**, not
the latest report: a criterion that failed on one module and passed on another would
otherwise read as passing, which is the composition failure the criterion exists to
catch. A clause with no verdict counts as insufficient rather than satisfied — the one
default that fails open.

---

## 11. Delivery (P8) — the deploy gate

**FR-117** Delivery must produce: a **deployable artifact** (container image or
equivalent), **infrastructure-as-code** for the target environment, **operational
runbook**, and a **delivery report** containing the traceability chain from intent
clause to deployed component.

**FR-118** The delivery report must state, explicitly and without euphemism:

- which intent clauses are verified, and by which oracle at which measured strength
- which intent clauses are **unverified** (ground-truth debt, FR-108)
- every assumption from P2 that remains unvalidated
- that **requirements were verified, not value** (FR-086)
- the actuals against the §1.3 envelope

**FR-119** The deploy gate must be human, permanent, and must present the delivery
report. Deploy is never automatic (§1.5).

**FR-120** SoFact must produce the system so that it is **machine-usable** as well
as human-usable: a documented, stable API surface. A delivered platform that only
a human can drive fails the stated goal.

**FR-121** Delivery must include a **maintenance handover**: the Mode M lane
configuration for the delivered system (initializing its inherited oracles from the
manufactured ones), so that P9 and future Mode M work are possible on the artifact
just created. Genesis and maintenance must compose: **the output of Mode G is a
valid input to Mode M.**

---

## 12. Autonomy, admission control, and topology

Retained from v0.1 with one addition: autonomy is **per-phase and per-module**, not
per-lane only.

**FR-024**–**FR-035** (routing function, blast bounds, ladder, per-deployment
ceilings, staging modes) apply unchanged.

**FR-122** Autonomy must be computed **per phase** (§3.2) *and* per module, and the
lower bound must govern. A platform cannot claim an autonomy level that any
mandatory phase cannot sustain.

**FR-123** The **maximum end-to-end autonomy of a Mode G delivery is L2**, because
P2 and P3 are human gates and P8 is a human gate. Individual modules may run at L4
internally; the *delivery* is L2. **SoFact must report this distinction explicitly
and must never report a Mode G delivery as L3 or L4.**

This requirement exists because the alternative is a false claim, and false claims
about autonomy are how this class of product destroys trust. Per §2.3, the honest
headline is: **autonomous module construction inside a human-validated
architecture.**

**FR-124** Per-deployment topology ceilings (FR-019, FR-030, FR-031) apply to
Mode G unchanged. T1 (dev instance, no isolation boundary) runs Mode G at −1 level,
and L4 module construction is unavailable there.

---

## 13. Mode M — maintenance lanes (unchanged from v0.1)

Retained in full: L01–L05 (L4-eligible), L06–L07 (L3), L08–L09 (L2–L3), L10 (L3),
L11 (adversarial audit service), L12 (self-maintenance, L2 gated).

Mode M is demoted from *the product* to *a mode of the product*, but it is not
deprioritised in the roadmap: it is the calibration source for Mode G's thresholds
(§20.3) and the commercially easier entry (§19.2). Its lanes have stronger oracles
than Mode G's modules, which is the point made in §2.3.

---

## 14. Mode G lane classes — new

Genesis work is organised into phases, not lanes, but P4/P5 need lane-typed
contracts so that autonomy can be assigned per module type:

| Class | Module type | Manufactured oracles | Ceiling |
| --- | --- | --- | --- |
| **G1** | Pure domain logic (invariant-rich) | Property-based + state machine | **L4** |
| **G2** | Data transformation / ETL | Property-based + schema + metamorphic | **L4** |
| **G3** | API/service layer | Contract tests + schema + O8 integration | **L3** |
| **G4** | Persistence / schema migration | Migration round-trip + property tests | **L3** |
| **G5** | UI / presentation | Snapshot + contract; weak oracles | **L2** |
| **G6** | External integration adapters | Recorded-fixture differential (O6) | **L2** |
| **G7** | Auth, secrets, payments, PII handling | — | **L1, human-authored** |
| **G8** | Infrastructure / deployment config | Plan-diff review | **L2** |

**FR-125** G1–G2 are the target classes: invariant-rich logic has the strongest
manufactured oracles. Genesis should be decomposed so that as much mass as possible
lands in G1–G2, and the P3 gate must report the **class distribution** of modules
as a decomposition-quality signal.

**FR-126** G7 must be human-authored. No manufactured oracle justifies autonomy on
auth, secrets, payments, or PII (NFR-018). This directly constrains the example
goal in §14.1.

### 14.1 Worked example — "track the economics of my organization"

The goal named in the brief, run through the pipeline:

| Phase | Output |
| --- | --- |
| **P0** | Intent clauses: which economic quantities? from which systems? for whom? what decision does it enable? data residency? who may see what? **Ambiguity is severe** — "economics" is not falsifiable, and P0 must resolve it to clauses such as "monthly cash position per cost centre, from the ERP, available within 1 business day." |
| **P1** | Research: accounting-system export APIs, data protection constraints, comparable open-source systems. Likely verdict on some premises: **invalidated** — the ERP may not expose the required granularity. |
| **P2** | Specification + system model: entities (account, cost centre, period, entry), invariants (double-entry balance), value hypothesis (time-to-close reduction), non-goals (no ledger of record — read-only mirror). |
| **P3** | Decomposition, e.g.: ingestion adapter (G6), normalisation (G2), ledger model (G1), reporting API (G3), dashboard (G5), **auth/RBAC (G7, human-authored)**. |
| **P4** | Contracts. G7's contract is written by the operator, not manufactured. |
| **P5–P7** | Modules built and integrated in topological order. |
| **P8** | Delivery report: financial data handling means NFR-018 concerns floors apply throughout; deploy is gated; the value hypothesis is *not* certified. |

**Why this example is instructive.** The goal looks like a data project and is
actually a **financial-data project**. It lands 3 modules in G1–G3, one in G5, one
in G6, and — critically — one in G7 that the factory **cannot** build. The example
therefore demonstrates both the product's reach and its limit in the same
delivery, which is the honest way to present it.

---

## 15. Non-functional requirements

**NFR-001**–**NFR-024** retained from v0.1 (portability, durability, throughput,
security, observability, no-unmeasured-targets). New requirements:

**NFR-025** The delivery envelope (§1.3) must be configuration, and every delivery
must report actuals against it.

**NFR-026** SoFact must be **harness-agnostic** (FR-058) and **model-agnostic**
(FR-049) such that neither is a hard dependency for any phase other than P5.

**NFR-027** All pipeline artifacts (intent clauses, findings, specification,
decomposition, contracts, oracle results) must be **human-readable and
version-controlled**. The artifacts are the product's durable output; the code is
re-derivable from them at the cost of a rebuild.

**NFR-028** SoFact must be able to **resume a platform build** at any phase
boundary after arbitrary interruption, with no phase re-executed unnecessarily and
no gate re-passed silently.

**NFR-029** The factory must **bound total wall clock per phase** and escalate on
exceedance rather than continuing (§1.4, FR-101).

**NFR-030** Every phase's model and harness usage must be attributed and reported
per module, so that cost per delivered module is knowable.

---

## 16. Architecture

### 16.1 Components

v0.1's ten components plus seven for genesis. Component count is still budgeted
[S10]; where a component can be a configuration rather than code, it must be.

| # | Component | Phase | New in 0.2 |
| --- | --- | --- | --- |
| 1 | Elicitation engine | P0 | **yes** |
| 2 | Research engine + source ledger | P1 | **yes** |
| 3 | Specification store + system model | P2 | **yes** |
| 4 | Decomposition planner | P3 | **yes** |
| 5 | Contract author | P4 | **yes** |
| 6 | Oracle manufacturer | P4 | **yes** |
| 7 | Harness adapter + goal-plan compiler | P5 | **yes** |
| 8 | Verifier | P6 | no (v0.1) |
| 9 | Adversary | P6/P4 | no (v0.1) |
| 10 | Integration verifier + O8 | P7 | **yes** |
| 11 | Delivery packager | P8 | **yes** |
| 12 | Oracle registry | all | no (v0.1) |
| 13 | Router/policy (pure function) | all | no (v0.1) |
| 14 | State store (durable, resumable) | all | no (v0.1) |
| 15 | Process loop / scorecards | P9 | no (v0.1) |
| 16 | Escalation surface | all | no (v0.1) |
| 17 | Intent traceability graph | all | **yes** |
| 18 | Harness scheduler (waves, worktrees, budgets, capability matrix) | P5 | **yes (0.3)** |

**FR-127** The **intent traceability graph** must be a first-class component, not a
derived report. It is the only mechanism by which an escape (§9.6) can be
attributed back to the intent clause that was misunderstood — and per §2.3 that
attribution is the single most valuable learning signal the product produces.

**FR-128** The system model (§6.3) must be the single source of interface truth,
and every component must read interfaces from it rather than from code.

**FR-129** Elicitation, research, specification, and decomposition must share no
model context with build and verify. Separation of the *specification* from the
*builder* is symmetric to v0.1's producer/evaluator isolation (FR-018) and is
required for the same reason.

---

## 17. Interfaces

v0.1's lane and oracle definition formats are retained. New surface:

- **`sofact goal`** — submit a goal; begins P0.
- **`sofact elicit`** — the Socratic dialogue; interactive or batch.
- **`sofact research`** — P1; produces the source ledger and verdicts.
- **`sofact sources`** — reads a research run's artefacts into a `SourceLedger`
  (`--from-run <id>`), or prints the one the log holds. Claims and sources are
  separately addressable, and the command exits non-zero when a provenance, evidence,
  or staleness check fails (FR-069, FR-070, FR-071, FR-073–FR-075; ADR-0035).
- **`sofact classify`** — reads a research run's `research-classification.json` into a
  `ResearchClassification` (`--from-run <id>`), or prints the one the log holds. Each
  verdict is printed with the action FR-068 gives it, its rationale and its evidence;
  Unverifiable verdicts are printed as the flagged assumptions they become, and the
  clauses that return the pipeline to P0 are named in a block of their own. The command
  exits non-zero when a clause is unclassified, when a verdict cites a source the ledger
  does not hold, or when anything is invalidated (FR-068, FR-079; ADR-0037).
- **`sofact specify`** — proposes the specification and gates it. `--entity`,
  `--assumption`, `--value` and `--criterion` carry the parts that are the *operator's*
  statements rather than derivations, and the criterion form is
  `STATEMENT | CRITERION | CLAUSE-INDEX,CLAUSE-INDEX` with at least two clauses — a
  one-clause criterion is a module's own obligation (FR-078, FR-079, FR-085, FR-116;
  ADR-0038).
- **`sofact decompose`** — proposes the module graph and gates it.
- **`sofact integrate`** — P7 over the plan's dispatched work: build order (FR-111), the
  interface diff (FR-112), import discipline (FR-113, FR-114), model conformance
  (FR-115) and the system-level criteria (FR-116). Every check prints what it did *not*
  cover, and the requirements the approved specification left nothing to check are named
  as not implemented rather than passed (ADR-0027, ADR-0038).
- **`sofact contract`** — P4; emits contracts + manufactured oracles.
- **`sofact build`** — P5–P7; runs the platform build.
- **`sofact report`** — the delivery report (§11).
- **`sofact gate approve <phase>`** — the only way past a gate, attributable to a
  human identity (FR-061, NFR-017).

**Running in v0.1** — the subset of the above that exists as executable code today:
`sofact` (the interrogation itself, which is P0), `research` (P1 dispatched: FR-167),
`sources` (P1's ledger, read from the run's artefacts: FR-069–FR-075, ADR-0035),
`classify` (P1's per-clause verdicts: FR-068, ADR-0037),
`specify`, `decompose`, `integrate` (P2, P3 and P7: ADR-0031, ADR-0038; the proposal's
per-module Definition of Done is FR-093 — ADR-0042),
`contract`, `plan`, `probe`, `dispatch`, `verify`, `integrity`, `precision`, `claim`,
`dimensions`, `draft`, `status`, `ledger`, `verify-ledger`, `rollback`, `repair`, `run`,
`envelope` (§1.3: FR-057, NFR-025 — ADR-0039), `deliver` and `deploy` (§11's report and
its human gate: FR-117–FR-119, FR-121, FR-086 — ADR-0040; the report's autonomy pair is
FR-122/FR-123 — ADR-0041), and `api` (FR-120's machine surface: one read-only dispatch,
one closed envelope, the four human gates refused by name — ADR-0048). `deliver` **writes the two artefacts the factory owes**
(`RUNBOOK.md`, `DELIVERY.md`) under the root `--root` names, rendered deterministically from
the report and not by a model (ADR-0044); the delivery is computed as a fixed point because
the documents render the report and the report's artefact check reads the filesystem. FR-120's
two halves are reported apart: the **factory's own** surface is built (`api` above), while the
**delivered** system's machine-usable surface remains a producer obligation: no oracle in
O1-O8 observes whether an artefact exposes a usable interface, so the delivery report names
it in a `machine_surface_not_verified` check and `DELIVERY_REQUIREMENTS` keeps it in the list
rather than dropping it. The planned
verbs remain the target surface; `plan` is §8.4's compiler, `probe` is FR-148, `dispatch` is
FR-142's wave scheduler (and FR-163's trigger: **a completed session** is checked against the
contract,
and the command exits non-zero when nothing was verified, when a step was refuted, or when
a plan that ran to its end left the contract not clean), and `integrity`/`precision`
are FR-139 and §20.4. `run` is clause-complete and `verify` is run-scoped, so
`run` + `verify` re-checks an artefact after a repair (§9.6, FR-162).

- **`SOFACT_MODEL`** (or `dispatch --model`) — the model id handed to the harness. It is
  resolved by the **harness's own registry**, not by the model server: `pi` refuses a local
  ollama tag it does not list, exits 1, and writes no session record. So a tier is a
  harness registry entry (FR-132), and the check happens in the child — which is why it is
  **measured and then attributed** rather than validated on SoFact's side. The probe
  records `model_resolved` and the model it measured (FR-164); `probe` and `dispatch` both
  exit non-zero on a refusal, naming the harness's words for it, so a refused model is
  never reported as a producer failure.
- **`--tools`** (or `SOFACT_TOOLS`) — the comma-separated allowlist handed to the
  producer, default `read,write,edit,bash`. The tool set is the whole of what an agent may
  do, so it is operator-tunable rather than a constant in `src/` (FR-156), and the probe
  prints the set it resolved so a build's capability is visible *before* it starts. An
  **empty** set is refused rather than forwarded: an empty allowlist disables every tool,
  so the producer could not write, and the failure would surface later as a broken step
  with no cause attached.
- **`--quick`** (on `probe`) — skip the capability rows that need a second child
  (`sandboxable`, `concurrent`, `budget_control`) when a full probe is slower than the
  question is worth (FR-165). The rows are still **reported**, each saying that the
  attempt was not made, so a quick probe cannot be mistaken for a clean one. The
  `goal_survives_compaction` row is not skipped: it reads the record the probe already
  has.
- **Spec fields a deployment declares, not code it writes** (FR-161): `confinement_tools`
  is the tool set the `sandboxable` probe hands its child (empty means the operator's
  resolved `--tools`, so the row measures the configuration actually in force);
  `budget_argv` is the harness's budget flag, rendered with a `{budget}` slot, and its
  absence is what makes `budget_control` report *nothing to attempt* rather than a gap;
  `compaction_event` is the record type that means a compaction happened, and a spec that
  declares none can never confirm survival across one. All three are optional, and each
  one narrows what the probe can decide rather than being assumed (FR-153).
- **`--fresh`** (on `dispatch`) — re-run the oracles even when the workspace and the
  oracle set are unchanged since a standing verdict (FR-166). The default reuses: a
  verdict whose key — contract hash, artefact digest, oracle-set hash — matches a
  previous report holds without re-running, and the reuse is written down as its own
  row naming the verdict it stands in for. The cache is not a pass cache: a refuted
  verdict is reused too, and still refuses its dependents.
- **`sofact research [query]`** — dispatch one research run on the current goal (FR-167).
  SoFact authors the goal deterministically; the harness's research loop does the
  searching (`pi-research` in the built-in table, [S25]). The verb records what the
  workspace holds — report size, the loop's own search count, cited URLs — and never
  rounds a report with no sources into research that happened. `--super` asks for the
  multi-phase loop. The run is **bounded by a declared budget** (FR-072, ADR-0036):
  `--max-sources`, `--max-calls` and `--seconds` set the caps **per intent clause**, and
  the allowance for the whole run is the product — the clause count coming from the
  goal's latest draft, with a goal that has no draft yet counted as one clause and the
  record saying so. The defaults are 5 sources, 5 model calls and 300 s per clause: the
  first two are the delegated loop's own five-search floor read back as a ceiling, and
  the wall clock is set above the extension's 240 s/360 s ceilings so that a truncation
  is attributed to the extension that caused it. Only wall clock is enforced — SoFact
  holds the timeout and kills the child; the other two are observed from the producer's
  artefacts afterwards and recorded in `budget_violations` when exceeded, because a cap
  enforced inside the producer's runtime is the producer grading its own spend (FR-140).
  An unmeasured turn count yields no violation in either direction and prints as
  `unmeasured`, not as zero (NFR-024). `--timeout` overrides the scaled wall clock for
  one run without rewriting the declared budget. An overspend is recorded rather than
  fatal: the ledger the phase exists to produce is still read.
- **`SOFACT_HARNESS_SPECS`** — path to a JSON harness table, so FR-161's table can be
  replaced without editing `src/`. Accepts `{"harnesses": {...}}` or a bare
  `{name: {...}}`. Unset means the **built-in** table, which is not the same as an
  empty table: an empty table leaves no harness from which to name a default. A
  malformed file, an unknown harness name, or an ambiguous table is reported and
  exits non-zero rather than falling back to something usable-looking (FR-161).
- **`SOFACT_HOME`** (or `--home`) — the state directory holding the event log
  (ADR-0003). Defaults to `<cwd>/.sofact`.

**FR-130** Gate approval must be **attributable and auditable**: which human,
when, which artifact version. Anonymous approval is not approval.

**FR-131** Every artifact must be addressable by a **UUID7** identifier and
version-hashed, so that the traceability chain survives artifact revision
(parent-project convention; §9.1 v0.1).

---

## 18. Model and harness strategy

### 18.1 The stated choice, and its arithmetic

**Two axes, kept separate.** The brief names DeepSeek-V3 as the implementation
model *and* raises a DeepSeek harness. These are independent: the harness is fixed
(§8.6, D11) and the model is swappable behind the adapter. `pi` reaches DeepSeek
models directly (`--provider deepseek`) and `dsh` treats model routes as plugins, so
*which model* is configuration in either case, never architecture (FR-049, FR-132,
NFR-026).

**DeepSeek-V3 is no longer the current generation.** `dsh`'s own SDK example
defaults to `deepseek-v4-flash`, and the catalogue lists V4-Pro and V4.1-Flash; V3
remains reachable through third-party routes. The brief's naming is best read as "a
DeepSeek-class model" rather than a pinned version [S20]. Vendor pricing is also
reported to have moved sharply for the V4 generation, though only secondhand — it
must be confirmed against DeepSeek's own terms before entering a cost model (S13's
lesson).

This is a **hosted-vs-self-hosted decision with real money attached**, and the
arithmetic should be stated before it is committed to:

- DeepSeek-V3 is a ~671B-parameter MoE with ~37B active. At 4-bit, weights are
  roughly **335 GB**, so a self-hosted deployment needs a VM with ~400 GB+ RAM and
  GPUs for usable latency.
- **CPU-only self-hosting is not viable.** Decode is bandwidth-bound by active
  parameters: ~18.5 GB read per token at 4-bit. At a typical CPU memory bandwidth
  of ~100 GB/s that is **~5 tokens/second** — an order of magnitude too slow for
  agentic coding, where a single module build is millions of tokens.
- GPU self-hosting is viable (~200 tok/s with several high-bandwidth GPUs) at
  roughly **$8–16/hour** of VM cost. That is ~$200–400 per day of unattended
  building.
- The hosted API is **one to two orders of magnitude cheaper for intermittent
  use**, and is the only sane v1 default.

**These figures are first-principles estimates, not measurements. They must be
replaced with measured numbers in M0 (§20.3).** The parameters are stated so the
arithmetic can be re-run rather than trusted.

**FR-132** The model configuration must be **tiered and declarative**, with a
default that is economical for the phase: a large model where reasoning depth
matters (P3 decomposition, P6 failure diagnosis, the adversary), and a cheap or
local model for high-volume low-depth work (P5 module builds, test generation,
triage) — per NFR-012.

**FR-133** Model and harness spend must be **attributed per phase and per module**
and must be reported against the §1.3 envelope (NFR-030). An unattended build with
no spend attribution is an unbounded financial commitment.

### 18.2 The contradiction this creates

**The sovereign / air-gapped ICP (§1.4 v0.1) is incompatible with a hosted
DeepSeek-V3 default.** Those customers cannot send source to a third party. Under
the §1.2 Mode G scope this is sharper than it was in v0.1: genesis work sends
*specifications, models, and designs* — the most valuable artifacts a company has —
not just diffs.

Options, as D12: (a) hosted default, sovereign deferred; (b) self-hosted tier
requiring GPU VMs, priced accordingly; (c) two-tier product with an explicitly
degraded air-gapped mode using a smaller local model and accepting lower
throughput. **These are materially different businesses and the choice cannot be
deferred indefinitely.**

### 18.3 Fine-tuning

**FR-052**–**FR-054** retained. In Mode G the highest-value fine-tuning target is
**oracle manufacturing** — specifically, generating property-based tests and
invariants from contracts (§9.2, ranks 1–2), which is high-volume, narrow, and has
objectively measurable success (does oracle strength rise?). This supersedes v0.1's
proposed target of lane routing.

**FR-134** Fine-tuned models must not be oracles (FR-053) and must not author
contracts, because a contract written by a model trained on the factory's own
outputs closes the §2.3 loop rather than opening it.

### 18.4 Goal-mode harness selection

**FR-147** Harness selection must be **empirical** — driven by measured
goal-declaration precision (§20.4) and throughput, not by reputation. D11's matrix
is the selection instrument and must be populated from probes (M0 item 6), not from
vendor claims. **The ledger gap on this landscape is now closed for two harnesses
— [S18] [S19] (`pi`) and [S20] (`dsh`) — and closed at the level of documentation,
not measurement.** §8.6's choice is a decision on documented capability; FR-147
decides *among* candidates by measurement, and `dsh` can still lose that contest.
The two are not in conflict: §8.6 picks what to probe first, FR-147 picks what to
keep.

**The evidence gap, stated plainly.** [S04] (~78.4%) and [S05] (77.4%) measure
harnesses on *patch generation against existing repositories with an existing test
suite* — the Mode M setting. There is **no benchmark evidence for Mode G** (empty
repository, contract-driven construction). Harness fitness for genesis work is
therefore genuinely unknown, and R14 is the risk that it is poor. Any plan that
commits to Mode G before M0 item 6 returns is a plan built on an untested
assumption.

---

## 19. Business model

> **Scope note (0.4).** Commercialization is **explicitly not a goal** (D17). This
> section is retained as *optional context*: it describes what could be sold if the
> operator ever wanted to, which is a legitimate way to test whether an artifact is
> coherent, and it is the reason §19.1's last row (P0–P2 standalone) is interesting.
> **No requirement in this document may be justified by this section alone.** Where
> the business case and the capability objective disagree, the capability objective
> (D17) wins.

### 19.1 What is sellable, honestly

| Offering | What is delivered | Evidence it works |
| --- | --- | --- |
| **Oracle assessment** (Mode M) | `sofact init`: how much autonomy your codebase actually supports | Measured mutation score per module |
| **Maintenance** (Mode M) | Recurring verified dependency/security/quality maintenance | Escape rate against budget |
| **Genesis** (Mode G) | A delivered, verified, deployable platform | Delivery report + unverified-clause list |
| **Elicitation + specification** (P0–P2 only) | A falsifiable specification and value hypothesis, research-backed | Gate artifacts, no build required |

The last row is commercially interesting and was not in v0.1: **P0–P2 is valuable
without building anything.** Many organisations cannot state a falsifiable
specification for what they want, and finding out that a premise is invalidated at
P1 is enormously cheaper than finding out after a build. This is the land-and-expand
surface, and it is honest about the product's limits.

### 19.2 Sequencing

Mode M first, on the operator's own repositories. Reasons: it calibrates θ
thresholds with real escape data (§20.3), it produces revenue sooner, its oracles
are stronger, and it validates the verification subsystem under conditions where
failure is cheap. **Genesis is the goal; maintenance is the runway.**

### 19.3 Governance boundary

**FR-055**, **FR-056** retained. Monetization is human-decided, machine-executed;
SoFact does not set prices, accept customers, or move money.

---

## 20. Metrics

### 20.1 Primary metrics

v0.1's six (VUHM, escape rate, oracle strength, intervention rate, exploit
discovery rate, cost per VU) plus the Mode G and meta-harness metrics below.

| Metric | Definition | Why |
| --- | --- | --- |
| **Specification acceptance rate** | Intent clauses approved at P2 without reopening | **The** quality metric for P0–P2. A low rate means elicitation is failing and every downstream guarantee is void (§2.3). |
| **Clause reopen rate** | Approved clauses later found unfaithful | The lagging indicator of the same failure |
| **Ground-truth debt** | Uncovered intent clauses per module (§9.3) | Leading indicator of silent wrongness |
| **Interface count per module** | From the decomposition (§7.1, FR-091) | Leading indicator of integration risk |
| **Integration failure rate** | P7 failures per module, versus interface count | Tests the `n²` hypothesis (§1.4, R13) |
| **Human-minutes per platform** | Summed across all gates | The §1.4 economic claim, measured |

### 20.4 Meta-harness metrics (new in 0.3)

These measure the **worker**, not the work. They are the only instrument that makes
FR-147 a decision rather than a preference.

| Metric | Definition | Why |
| --- | --- | --- |
| **Goal-declaration precision** | verified completions ÷ harness completion declarations | The single number that says whether a harness can be trusted to know when it is done. Low precision ⇒ replace the harness, not the module (§8.3) |
| **Continuations per module** | Goal sessions spawned per verified module | Measures plan-compilation quality (FR-136); a high count means the contract→goal split is wrong |
| **Tokens per verified module** | Spend attributable to P5+P6 | Drives §1.3 envelope actuals and model tiering (FR-132) |
| **Wave utilisation** | Concurrent sessions ÷ wave width | Measures whether the topological order (§7.1) actually permits parallelism, or whether the DAG is a chain |
| **Contract-integrity failures** | FR-139 hash mismatches | Detects harnesses that edit their own success criteria — the sharpest form of goal-hacking |

### 20.2 The claim under test

SoFact's central empirical claim is: **human attention per delivered platform is
sub-linear in module count because gates are per-platform while work is
per-module.** If human-minutes per platform grow linearly with modules, the product
has no economic advantage over reviewing diffs, and §1.4 is false. This must be
tested, not assumed.

### 20.3 Baseline measurement (M0) — blocking

1. **Throughput table** — tokens/s and prefill latency per model class × context
   length, including whatever hosts DeepSeek-V3 (NFR-011).
2. **Oracle strength baseline** — mutation score per module on a real repo (Mode M)
   *and* measured strength of manufactured oracles on one real contract (Mode G).
3. **Human review time** — logged per gate *and* per diff, so §1.4's claim can be
   compared directly against the v0.1 alternative.
4. **Escape baseline** — requires a deployment. Until then all ceilings are
   hypotheses.
5. **Isolation verification** — container boundary and egress denial actually hold
   (FR-019).
6. **Harness capability probe** — ordered, cheapest-falsifying-first:
   **(a)** does goal mode loop unattended under `pi --print` / `harness.run()` with
   no human in the loop? This is the single assumption the whole delegated-P5
   design rests on. **Partially answered, and re-shaped, by [S21]:** the `dsh`
   `goal` package is present and loaded, but in a live unattended run the producer
   **never entered it** — zero goal-typed events, `todo_write` substituted, single
   turn, `finish_reason: completed`. Goal mode is therefore *available and
   model-discretionary* (FR-153, R25). What remains open is not whether the
   capability exists but whether entry can be **forced** and continuations
   observed;
   **(b)** the FR-135 matrix, **discovered at runtime** (FR-148): goal mode present;
   unattended operation; budget enforcement; telemetry source and event taxonomy;
   sandboxability (and what `dsh`'s default composition actually permits);
   concurrency; empty-repo bootstrap; goal survival across compaction;
   completion-signal semantics;
   **(c)** then dispatch **≥ 10 real goals** and measure **goal-declaration
   precision** (§20.4) for *both* `dsh` and `pi`.
   **This gates the entire Mode G design and must be answered before P5 is built**
   (R14, R25, R26). [S21] returned **(b) in part** — the runtime composition was
   dumped in full and the live event taxonomy observed, which is what makes §8.6
   rest on a measurement of the *integration surface*. Goal continuation, however,
   still rests on documentation and on n=1 evidence, so (a) remains the blocking
   probe.
7. **Model hosting arithmetic** — measured cost and latency for hosted vs
   self-hosted, per §18.1, for a current DeepSeek-class model (not V3 specifically).

**NFR-024** retained: SoFact must refuse to report a target it has not measured.
This document contains no measured figures.

---

## 21. Risks

v0.1's R1–R12 retained. New risks from the 0.2 scope:

| # | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| **R13** | Integration risk grows as `n²` while human attention is flat, so the §1.4 economic claim is false beyond small platforms | **Fatal to the business case** | M0 item 3 compares gate-minutes to diff-minutes directly; interface count is a gate input (FR-091) and its correlation with integration failure is measured (§20.1). Envelope (§1.3) is deliberately conservative. |
| **R14** | The chosen harness cannot bootstrap an empty repo, making Mode G unbuildable on existing tooling | **Fatal to Mode G** | M0 item 6 is a blocking probe. FR-098 requires three adapter modes. FR-058 requires ≥2 adapter implementations. |
| **R15** | "Real economic value" is claimed but not measured, and buyers discover the gap | High — credibility | FR-085 falsifiable value hypothesis; FR-086 explicit non-certification; FR-118 delivery report |
| **R16** | Ground-truth debt (§2.3) produces correct-by-spec, wrong-in-intent systems that pass every check | **Highest technical risk** | P2 gate is non-negotiable (FR-061); intent traceability at clause granularity (FR-127); §9.3 debt accounting with L2 cap; operator examples held out (FR-106) |
| **R17** | Manufactured oracles are satisfiable without implementing the invariant | High — false confidence | FR-107 adversarial audit of oracles; FR-103 ranks property-based first |
| **R18** | Hosted model default contradicts the sovereign ICP; self-hosting is uneconomic on CPU | High — market | §18.2; D12. Must be decided before pricing. |
| **R19** | Unbounded goals produce unbounded platforms | Medium | FR-057 envelope refusal; P0 must resolve scale (§4, FR-064) |
| **R20** | Four gates per platform is still too much human load at scale | Medium | §20.2 measures it; gates may move to sampling if specification acceptance rate is high |
| **R21** | Attended wall clock per platform (2–10 days) is longer than a human would take for small goals | Medium | Mode G targets platforms, not tasks; small goals should be refused or routed to Mode M |
| **R22** | **Goal-hacking** — the harness optimises its own completion criteria: weakens tests, satisfies the letter, declares victory | High — manufactures false confidence | Held-out operator examples (FR-106); independent P6 (FR-138); adversarial audit of *oracles* not just code (FR-107); contract-integrity hash (FR-139) |
| **R23** | **Objective drift under compaction** — a long goal session loses the contract and completes something else ([S08]) | High — silent, and only visible at P7 | Objective re-injection every continuation (§8.2); contract hash re-verified at completion (FR-139); goal-plan steps are short by construction (§8.4) |
| **R24** | **Runaway spend** — a harness goal loop burns tokens or wall clock unattended | High — the binding resource (§1.4) | Budget enforced *outside* the harness (FR-140, FR-101, NFR-029); per-session and per-wave cost caps; spend attribution per module (NFR-030, FR-143) |
| **R25** | **Goal-mode entry** — the producer does not enter goal mode, or enters it and does not continue | **Revised by measurement** — `dsh` goal mode is present and loaded, but a live probe **never entered it** (zero goal-typed events; `todo_write` was substituted) [S21]. Capability is not engagement, and entry is model-discretionary | FR-153 forces entry and verifies it from the session log; FR-144 provides the single-shot fallback as a reported capability loss; FR-135/FR-147 keep the matrix current |
| **R26** | **Harness coupling** — `dsh` is a one-month-old developer preview that warns of breaking changes; the interface moves under an unattended multi-day build | High — the foundation, not the feature | Version pinned; harness surface confined to one module (§16 component 7, FR-148); `pi` adapter retained as the escape hatch; every capability probed (FR-147). **Accepted deliberately, not mitigated away.** |
| **R27** | **Context-file injection** — a module writes `CLAUDE.md`/`AGENTS.md` that a later session reads as instructions, bypassing FR-140 | High — routes around authority separation | FR-150 disables context-file loading during P5; FR-139 hash check catches criteria edits; the injection would still have to survive P6 |
| **R28** | **Plugin supply chain** — a third-party `dsh` plugin in the producer's composition is malicious, abandoned, or licence-incompatible | Medium–High — executes inside the producer's runtime, with the producer's filesystem and credentials | FR-154: frozen, minimal, pinned, hash-verified composition; no operator-profile inheritance; no installation during P5; per-plugin licence check at composition time [S22]; R26's pinning now applies to the whole composition, not just `dsh` |
| **R29** | **Runtime composition mutation** — the producer authors or mounts a plugin, altering its own tools or its own verifier | High — the structural form of R22; verification becomes unreachable rather than merely unreliable | FR-138 keeps verification out-of-process by construction, which is the real defence; FR-154 (immutable composition, isolated `DSH_HOME`); composition hash recorded per session (FR-149); FR-150 closes the context-file route |
| **R30** | **The factory's own output becomes brownfield faster than its verification horizon** — agent-built codebases drift toward unmaintainable in **3–6 months**, not 10 years ([S24], N=1 but directionally consistent with F5). Every oracle in O1–O8 is bounded by a seconds-to-minutes pass/fail reward, so the factory is structurally blind to the failure mode that arrives in months | **High, and it is the factory's characteristic failure** — it is invisible to all of SoFact's instruments by construction | FR-158 names the debt and defaults it to total rather than hiding it; FR-159 gives a model-free trend alarm if D18 adopts it; FR-160 measures the constraint that actually binds; FR-106 holds out change units so the trend cannot be produced by the producer; P9 Evolve is judged on the **differential** metric, not on green tests. **Residual accepted:** if D18 rejects FR-159, the mitigation degrades to disclosure, and the honest fallback is [S24]'s own — the human remains the judge |

---

## 22. Open decisions

v0.1's D1–D10 retained; **D1 is superseded**, **D14 and D16 are resolved**, and D3/D8 are revised. New: D11–D17, of which **D11, D16, and D17 are resolved** (§8.6, §8.7, §1.4).

| # | Decision | Why it blocks | Recommendation |
| --- | --- | --- | --- |
| ~~**D1**~~ | ~~First target repository~~ | **Superseded by D11.** Mode M still needs one; Mode G needs a first *goal*. | Both: one repo for Mode M calibration, one goal for Mode G. |
| **D2** | Implementation language and stack | Determines mutation tooling, property-testing framework, packaging | Python + `uv` (parent convention). Confirm. |
| **D3** | First Mode M repository | Calibration source for θ | Your own repository, ideally one with an existing suite |
| **D4** | Human review budget | Sets VUHM and prices everything | Real number needed: hours/week |
| **D5** | Language scope for v1 | Mutation *and* property-based tooling are per-language (FR-036, FR-103) | One language end-to-end |
| **D6** | x402/metering in v1 | Scope | No |
| **D7** | L12 self-modification in v1 | Unbounded blast radius | No — M6 |
| **D8** | Fine-tuning target | Complexity budget | **Revised:** oracle manufacturing (§18.3), not lane routing |
| **D9** | Container runtime on target VM | FR-019 and all ceilings depend on a real boundary | Docker/Podman required |
| **D10** | CPU-only target support | §18.1 says CPU-only DeepSeek-V3 is ~5 tok/s = unusable | **Revised:** CPU-only must be explicitly unsupported for Mode G, or a small local model becomes the CPU-only tier |
| ~~**D11**~~ | ~~Which goal-mode harness first?~~ | — | **Resolved: `dsh` primary, `pi` second adapter** (§8.6). Grounds: Python SDK; typed replayable event log (FR-151); loop, sandbox, and scheduler as plugins; first-party goal package; harness-in-harness as its own idiom; MIT; Linux x64/arm64. `pi` retained as the interface's real test. **Residual:** the choice is made on documentation [S20], and M0 item 6 may overturn it — FR-147 governs. |
| **D12** | **Hosted vs self-hosted model tiering** | Determines which ICP is servable and what the product costs to run (§18.2) | Two-tier: cheap hosted default + self-hosted GPU tier for sovereign, priced separately |
| **D13** | **Does the operator want the P0–P2 artifacts as a standalone offering?** | Changes the go-to-market and the roadmap order | Yes — it is the cheapest, most honest entry and needs no build capability (§19.1) |
| ~~**D14**~~ | ~~Product name~~ | **Resolved:** **SoFact**. CLI binary / package / repo slug remain lowercase `sofact` (packaging constraint). | — |
| **D15** | **Does SoFact own a harness at all, or only adapters?** | Determines whether FR-058's second implementation is written, forked, or only configured | **Adapters only, never a fork, and no plugins either** (FR-146, §8.6). v1 writes exactly two adapters and zero Cordis plugins. If no candidate satisfies FR-135, the correct output is a *documented capability gap*, not a new harness built in-house — that is the §1.5 trap [S10] |
| ~~**D16**~~ | ~~Is SoFact a `dsh` plugin?~~ | — | **Resolved: no — not as architecture** (§8.7). SoFact is an independent control plane and `dsh` sits behind FR-058's adapter, out-of-process; an in-process verifier is mutable by the agent it verifies ([S22], R29). A thin **client** plugin is a v2 distribution surface and holds no authority. v1 ships zero plugins (D15, FR-146); third-party plugins are used only through FR-154's frozen composition, and only if they pass FR-155's deletion test. FR-156 is the same discipline on configuration: where a capability can be removed by config rather than guarded by code, config is mandatory |
| ~~**D17**~~ | ~~Is commercialization a goal?~~ | **Resolved: no.** The objective is *capability* — imagine a product and create it efficiently (operator statement, 2026-09-12). | **Consequences:** §19 becomes optional context and may not justify any requirement; the L4/θ ≥ 0.80 gate is not the default ceiling (FR-157); third-party-facing requirements (multi-tenancy T2, FR-130 attributable approval chains, hosted/self-hosted tiering D12) become deferrable rather than load-bearing; and composition is favoured over construction wherever FR-155 permits it, because the operator's time — not a market — is the budget. **What does *not* change:** FR-138/FR-140/FR-155. With no market there is no exogenous escape signal, so verification is the *only* oracle and gets more load-bearing, not less |
| **D18** | **Adopt a change-amplification instrument (FR-159), or declare the entire evolvability class out of scope?** | Decides whether Mode M can ever exceed L1 (FR-158), and whether R30 has a mitigation or only a disclosure. This is the one place [S24] leaves SoFact a path that needs no new model capability, so it is the highest-value cheap decision open | **Adopt — but only after M0.** It is model-free, needs no new model capability, and is the only instrument specified here that observes the failure [S24] describes. It must nevertheless be built as a *proxy* with its limits declared (NFR-024). If it cannot be made cheap enough to run per change unit, the honest fallback is disclosure: FR-158 stands, Mode M stays at L1, and the residual is recorded in the delivery report rather than engineered around. **Do not** substitute mutation score (FR-157) for it — FR-157 measures test adequacy under perturbation, which is a different quantity and would be exactly the conflation FR-158 exists to prevent |

---

## 23. Roadmap

Revised: v0.1's M1–M7 are reordered so that Mode M calibrates before Mode G
commits, and a blocking harness probe precedes any Mode G build investment.

| Milestone | Deliverable | Exit criteria |
| --- | --- | --- |
| **M0** | Instrumentation | §20.3 items 1–7 complete as real numbers. **Item 6a (does goal mode loop unattended?) is the first blocking probe; item 6b then confirms or overturns §8.6.** |
| **M1** | Oracle registry + `sofact init` (Mode M) | Mutation score per module, oracle report, lane-admissibility report on D3's repo |
| **M2** | Mode M lanes L01–L05 at L4 | Oracle strength rises on ≥1 module; escape rate tracked; adversary finds zero exploits in 20 consecutive changes |
| **M3** | Verification subsystem complete | All 8 oracle classes (incl. O8); canary halt demonstrated; holdout leakage test passes; adversarial loop closes a real exploit |
| **M4** | P0–P2 (Elicit, Research, Specify) | On a real goal: intent clauses with verification methods; cited research with ≥1 disconfirming source; gated specification with machine-checkable criteria. **Valuable with zero build capability.** |
| **M5** | P3 + P4 (Decompose, Contract) | DAG with traceability, interface count, class distribution; contracts with measured manufactured-oracle strength; §9.3 debt accounting |
| **M6** | P5–P7 (Build, Verify, Integrate) | One module of class G1 built to contract at L4 by a goal-mode harness session, with **termination and verification recorded as separate signals** (FR-138); goal-declaration precision measured (§20.4); contract-integrity check exercised (FR-139); then 8–25 modules integrated in topological order across **waves** (FR-142); O8 conformance passes; integration failure attribution works |
| **M7** | P8–P9 (Deliver, Evolve) + T2 packaging | Containerised deployable artifact from a Mode G run; delivery report with unverified clauses; Mode M handover (FR-121) works on the delivered system |
| **M8** | Commercial surface | Oracle assessment productised; P0–P2 offering productised; envelope actuals across ≥3 deliveries |

**Sequencing rationale.** M4 lands before M6 because P0–P2 is independently
valuable, needs no harness, and produces the artifacts everything else consumes.
M0 item 6a precedes all Mode G build work because R14 could invalidate the design
outright, and it is cheap: one goal, one session, no factory. M0 item 6b follows
because §8.6's harness choice rests on documentation, and documentation is not
measurement.
M2 precedes M3 because Mode M gives real escape data to calibrate θ before
manufactured oracles depend on it.

---

## 24. Traceability

| Specification commitment | Sources | Strength |
| --- | --- | --- |
| §2.3 ground-truth debt; spec-level regress | [S01] [S15] [S07] | Medium — **novel synthesis**; the regress is not stated in any single source |
| §3 pipeline and gates | [S06] [S09] | Medium — layering and the two-loop model |
| §4 elicitation as ambiguity resolution | [S11] (intent must be machine-derivable) | Weak — argued; elicitation is the mechanism that *creates* that property |
| §5 research engine | measured in this session | **Strong** — the ledger and findings in this repo are the working reference implementation |
| §6 system model as artifact | [S07] | Medium |
| §7 decomposition as L1 architecture | [S16] [S11] | Medium — the AV ladder mapped onto architecture |
| §8 harness reuse, not construction | [S10] [S05] | Strong — apparatus cost is the documented failure mode |
| §8.2 goal interface | [S18] | **Strong — content-verified.** `pi-goal` 0.1.7 read directly, on this machine |
| §8.3 termination ≠ verification | [S08] [S18] | Medium — **novel synthesis**; [S08] gives the failure modes, not this conclusion |
| §8.1 delegation vs apparatus cost | [S08] [S10] | Strong for the costs of building the loop; [S08]'s phrase "harness of harness" means *layered harness for durability*, **not** orchestration of many harnesses — the term is reused here with a different meaning |
| §18.4 Mode G harness evidence gap | [S04] [S05] | Medium — the cited figures are Mode M settings and do **not** transfer |
| §9.2 oracle manufacturing | [S01] [S15] [S07] | Medium — novel; ranks proposed by this spec |
| §9.4 O8 integration oracle | [S07] [S09] | Weak — argued |
| §10 integration is where systems fail | [S09] | Weak — conventional wisdom, not evidenced here |
| §12 FR-123 Mode G delivery is L2 | [S16] | Strong — follows directly from the ladder's definition |
| §18 model arithmetic | — | **None. First-principles estimate only. Must be measured.** |
| §19.2 Mode M as runway | [S17] [S13] | Weak — market reasoning |

**Provenance caveat, repeated.** Every source is `reported`, not re-verified
(`docs/sources/README.md`). No claim here is `content-verified`. §20.3 and NFR-024
exist so this document cannot quietly pretend otherwise. The harness landscape
(D11) has **no sources at all** — that is the largest hole in this specification.

---

## Appendix A — Source index

All ledger entries, including those not cited in the current text. Rendered as a
table rather than reference-style link definitions so that markdownlint does not
delete the uncited ones.

| Key | Source | Verification | File |
| --- | --- | --- | --- |
| S01 | Assistance-to-autonomy (arXiv 2605.15245) | `reported` | [s01](../sources/s01-assistance-to-autonomy.md) |
| S02 | Dark-factory essay (Soeters) | `reported` — URL unresolved | [s02](../sources/s02-dark-factory-soeters.md) |
| S03 | StrongDM software factory | `reported` — vendor | [s03](../sources/s03-strongdm-software-factory.md) |
| S04 | SWE-bench Verified (~78.4%) | `reported` | [s04](../sources/s04-swe-bench-verified.md) |
| S05 | Live-SWE-agent (77.4%) | `reported` | [s05](../sources/s05-live-swe-agent.md) |
| S06 | SASE framework (2509.06216) | `reported` | [s06](../sources/s06-sase-framework.md) |
| S07 | MAGE model-based agentic SE (2608.25174) | `reported` | [s07](../sources/s07-mage-model-based-agentic-se.md) |
| S08 | Harness of Harness (2609.01481) | `reported` | [s08](../sources/s08-harness-of-harness.md) |
| S09 | Six-layer reference architecture (2604.26275) | `reported` | [s09](../sources/s09-six-layer-reference-architecture.md) |
| S10 | Software-factory history (Bemer → Factory.ai) | `reported` | [s10](../sources/s10-software-factory-history.md) |
| S11 | Lane qualifiers (three conditions) | `reported` — URL unresolved | [s11](../sources/s11-gethuman-lanes.md) |
| S12 | Local coding models, 2026 | `reported` | [s12](../sources/s12-local-coding-models-2026.md) |
| S13 | Vendor harness billing change | `reported` | [s13](../sources/s13-anthropic-harness-billing.md) |
| S14 | x402 (HTTP 402) | `reported` | [s14](../sources/s14-x402.md) |
| S15 | Hacker/fixer loop (2606.08960) | `reported` | [s15](../sources/s15-hacker-fixer-loop.md) |
| S16 | Autonomy ladder L0–L5 | `reported` | [s16](../sources/s16-shapiro-autonomy-ladder.md) |
| S17 | Factory.ai | `reported` — vendor | [s17](../sources/s17-factory-ai.md) |
| **S18** | **Goal-mode harness interface (`pi-goal` 0.1.7)** | **`content-verified`** — primary, read locally | [s18](../sources/s18-goal-mode-harness-interface.md) |
| **S19** | **Harness CLI surface (`pi`)** | **`content-verified`** — primary, `--help`/`list` read live | [s19](../sources/s19-harness-cli-surface.md) |
| **S20** | **DeepSeek Harness (`dsh`) — plugin harness, Python SDK, event-sourced sessions** | `reported` — official docs; **partially superseded by [S21]** (version, integration surface, profiles, star counts all corrected); primary D11 source | [s20](../sources/s20-deepseek-harness.md) |
| **S21** | **`dsh` 0.1.5rc1 executed under probe — measured harness behaviour** | **`content-verified`** — primary; executed locally with a local model; first measurement entry in the ledger | [s21](../sources/s21-dsh-probe-executed.md) |
| **S22** | **`dsh` plugin ecosystem — 4,609 repositories, and what is already commoditized** | **`content-verified`** — measured from the source list and the GitHub API | [s22](../sources/s22-dsh-plugin-ecosystem.md) |
| **S23** | **Harness base candidates — `oh-my-pi` and `oh-my-dsh`** | **`content-verified`** (GitHub API metadata, npm, README fetch); README capability claims are `reported` | [s23](../sources/s23-harness-base-candidates.md) |
| **S24** | **“Harness Engineering is not Enough: Why Software Factories Fail” (Dex Horthy, HumanLayer)** — maintainability has no fast oracle; a harness cannot repair a missing reward signal | `content-verified` — talk transcript and long-form post; **author declares the central claim unprovable**, and the Faros figures are self-described correlation signal, not causation | [s24](../sources/s24-harness-engineering-is-not-enough.md) |

## Appendix B — Status of v0.1

| v0.1 element | Status in 0.2 |
| --- | --- |
| Verification subsystem (oracle classes, strength, audit, isolation) | **Retained verbatim**, extended with manufacturing (§9.2) and O8 |
| Escape oracle | **Retained**, now the attribution target of the traceability graph (FR-127) |
| Autonomy ladder + topology ceilings | **Retained**; extended per-phase (FR-122) and capped at L2 end-to-end for Mode G (FR-123) |
| Lane catalogue L01–L12 | **Retained as Mode M** (§13), demoted from primary scope, retained as calibration |
| "Architecture out of scope" | **Reversed.** Decomposition is the crux (§7), human-gated |
| "Greenfield admits almost no autonomy" | **Resolved, not dropped.** Oracles are now manufactured; the honest consequence is that genesis assurance is *lower* than maintenance assurance (§2.3) |
| Dev-machine constraints (disk, no Docker) | Unchanged — deployment-time declared budgets |
| Business model | **Revised**: P0–P2-only offering added; Mode M reordered as runway, not primary |
| Build phase | **Rewritten in 0.3**: P5 delegates to goal-mode harness sessions orchestrated as a harness of harnesses (§8), with termination explicitly separated from verification (FR-138) |
