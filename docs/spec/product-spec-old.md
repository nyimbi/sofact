# sofact — Product Specification

| | |
| --- | --- |
| **Document** | `docs/spec/product-spec.md` |
| **Version** | 0.1 (draft for review) |
| **Date** | 2026-09-12 |
| **Status** | Draft — contains 10 open decisions (§14) that must be resolved before build |
| **Supersedes** | Nothing. First specification. |
| **Grounded in** | `docs/research/findings.md`, `docs/sources/` (S01–S17) |

## How to read this document

Requirements are numbered and **testable**: `FR-nnn` functional, `NFR-nnn`
non-functional. A requirement that cannot be checked is a defect in this document.

Confidence is marked where it differs from assertion:

- **(measured)** — observed on real hardware or in a real repository.
- **(argued)** — follows from cited sources but not yet measured here.
- **(assumed)** — a design choice; needs validation. These are the fragile parts.

Anything marked **(argued)** or **(assumed)** that turns out false invalidates the
requirement that depends on it. §13 tracks the risk.

---

## 1. Product definition

### 1.1 Problem

AI coding agents are capable enough to produce plausible changes at volume, and
organisations cannot safely accept that volume. The constraint is not generation —
it is **the cost of knowing whether a change is correct**. Current tooling
addresses generation (better models, larger context, more tools) and leaves
verification as an afterthought: a test run, a diff for a human to read, and a
hope.

The result is a predictable failure: throughput goes up, review becomes the
bottleneck, review quality degrades under load, and defects that pass automated
checks escape into production.

The research consensus is unambiguous that this is the wrong axis. Output
verifiability — not model capability — is the dominant predictor of how much
autonomy a team will actually grant [S01]. The canonical benchmark is only
well-defined because its oracle is the repository's own test suite [S04]. Where
verification is weak, agents do not hesitate to satisfy the evaluator instead of
the requirement: roughly 16% of benchmark tasks are passable without solving them
[S15].

### 1.2 Thesis

**sofact is a verification-first software factory: a deployable system that accepts
machine-derivable intent, produces software changes, and grants each change
autonomy proportional to the measured strength of the oracle that judges it.**

Three commitments follow, and they are the product:

1. **Every autonomous lane declares its oracle before it runs.** No oracle, no
   autonomy.
2. **Oracle strength is measured, not asserted.** Mutation score is the instrument
   [S01 leaves this gap explicitly open; §4 closes it].
3. **Autonomy ceilings are derived from the deployment's isolation guarantees**,
   not from model confidence (§5.4).

### 1.3 Positioning

| | Model-only assistants | Enterprise agent platforms | **sofact** |
| --- | --- | --- | --- |
| Primary axis | Generation quality | Workflow integration | **Verification strength** |
| Autonomy decision | Model's self-assessment | Org policy, manual | **Computed per lane from measured oracle quality** |
| Deployment | Vendor cloud | Vendor cloud / VPC | **Customer-owned VM, including air-gapped** |
| Marginal token cost | Per-token | Per-seat + per-token | **Zero (local models)** |
| What it refuses to do | — | — | **Refuses lanes it cannot verify** (a feature, not a gap) |

The last row is the differentiator, and it is uncomfortable: the product's headline
capability is *declining work*. Competitors cannot copy it cheaply, because
declining work requires having measured something.

**Competitive note.** Commercial players sell the organisational version of this to
enterprises [S17]. A self-hosted factory differentiates on properties they
structurally cannot offer: data locality, zero marginal token cost, and unattended
operation on hardware the customer already owns. Local models are not a handicap
under this positioning — for the sovereign segment they are the product.

### 1.4 Ideal customer profile

Ordered by fit with the product's structural advantages:

1. **Sovereign / air-gapped maintenance** *(primary)*. Regulated or
   confidentiality-bound organisations that cannot send source to a hosted vendor.
   The value delivered is recurring dependency and security maintenance with
   tests, executed on hardware they control.
2. **Maintenance-as-a-service** *(secondary)*. The same work delivered as a
   managed service on customer infrastructure. Zero marginal token cost makes this
   a margin business rather than per-token arbitrage.
3. **Self-hosted line** *(tertiary)*. Selling the factory itself to teams who want
   to run it on their own estate.

### 1.5 Non-goals

Explicit, because scope creep here is the documented failure mode of every prior
software-factory wave [S10].

| Non-goal | Why |
| --- | --- |
| **Fully autonomous commercial judgement** — pricing, contracts, counterparty selection, accepting customers | No oracle exists for these. [S16] places them at L1 by definition. Monetization is **human-decided, machine-executed** (§11.4). |
| **L5 / dark-factory autonomy** | Not defensible at this scale. Claiming it would make the product fail its own acceptance criteria (§5.4). |
| **Unsupervised production deploys** | Blast radius is not machine-bounded for a deploy. Human-gated, always. |
| **Architecture and ambiguous-requirement work** | Intent is not machine-derivable. Out of scope for automation; the product may *inform* it. |
| **Being a better model** | sofact is model-agnostic by design (§10), specifically to avoid vendor repricing risk [S13]. |
| **Autonomous self-modification (v1)** | Unbounded blast radius, and the oracle would be authored by the thing being modified. Deferred to v2 with a separate oracle (§15, M6). |
| **Replacing the customer's CI** | sofact *uses* CI; it does not become it. |

---

## 2. Vocabulary

Precise terms, used consistently. These are load-bearing, not decorative.

| Term | Definition |
| --- | --- |
| **Lane** | A bounded class of work with a declared intent source, oracle, and blast radius. The unit of autonomy configuration. |
| **Intent source** | The artifact from which the desired end state is derived (a failing test, a codemod spec, an upstream changelog, an issue). Not a conversation. |
| **Oracle** | A machine procedure that returns pass/fail for a change, and that the producer cannot write to. |
| **Oracle class** | One of seven kinds of oracle (§4.2), each failing differently. |
| **Oracle strength** | Measured ability of an oracle to detect wrong behaviour. Mutation score for behavioural oracles (§4.3). |
| **Blast bound** | The declared, enforceable limit on what a failed change can affect. |
| **Concerns floor** | A constraint (security, PII, money, compliance, cost) that can only *lower* a lane's autonomy. Never raises it. |
| **Verified unit (VU)** | One change that has passed its lane's oracle set and been accepted. The unit of value and of metering. |
| **VUHM** | Verified Units per Human-Minute. The primary product metric (§12.1). |
| **Escape** | An accepted change later reverted, hot-fixed, or implicated in an incident for the same defect. The only oracle the factory cannot influence (§4.6). |
| **Autonomy level** | L0–L4 per [S16], defined by fallback responsibility, not by volume of work (§5.3). |

---

## 3. Product surface

What a user interacts with. Detailed interfaces in §9.

1. **Repository onboarding** — point sofact at a git repository; it inventories
   oracles and measures their strength. Output: an oracle report and a
   lane-admissibility report. This is the product's *first* deliverable and it is
   valuable even if nothing else runs.
2. **Intent submission** — declare work as a lane-typed intent artifact, not a
   prompt.
3. **The line** — queues, execution, verification, and a per-lane autonomy dial.
4. **Review surface** — small, oracle-backed diffs with the oracle results
   attached. Designed for minimum human-minutes per unit (§7.3).
5. **Scorecards** — per-lane VUHM, escape rate, intervention rate, oracle-strength
   trend. The process loop [S06] made visible.
6. **Escalation** — the product's most-used verb. Anything a lane cannot verify
   becomes a structured escalation to a human.

### 3.1 The refusal contract

When sofact declines work, it must say precisely why, in one of four terms:

- intent not machine-derivable
- no oracle exists for this outcome
- oracle exists but strength is below the lane's threshold
- blast radius not boundable in this deployment

A product that refuses work must make refusal actionable and non-humiliating to
configure. This is a first-class UX requirement, not an error path. Without it,
operators will widen lanes until something breaks — which is exactly the
degradation that makes agentic tooling untrustworthy.

---

## 4. The verification subsystem

The core of the product. Everything else is plumbing around it.

### 4.1 Requirements

- **FR-001** Every lane must declare ≥1 oracle. A lane with no oracle is
  inadmissible; configuration attempts must be rejected at load time, not at run
  time.
- **FR-002** Oracle definitions must be **read-only to producers**, enforced by
  filesystem permission or container mount, never by instruction in a prompt.
- **FR-003** Producers must be unable to modify oracle inputs. A change that
  touches an oracle artifact fails the lane outright and raises an integrity
  escalation — it is not merely re-run.
- **FR-004** Every oracle must be **canary-tested each cycle**: a known-good input
  that must pass, and a known-bad input (seeded mutant) that must fail. If either
  canary moves, the factory **halts the lane** rather than continuing.
- **FR-005** Every accepted change must record the complete oracle result set,
  versioned, retrievable by change ID. Auditability is not optional.
- **FR-006** Oracle results older than the change under test are invalid. Caching
  must be keyed by content hash of both the change and the oracle definition.

### 4.2 Oracle classes

Seven classes, deliberately multiple, because each fails differently. A producer
that defeats one class is unlikely to defeat all of them simultaneously.

| Class | Examples | Detects | Blind to |
| --- | --- | --- | --- |
| **O1 Behavioural** | test suite, acceptance tests, property tests | Wrong behaviour on covered paths | Uncovered paths; weak assertions |
| **O2 Mutation-based** | mutation score delta | *Does the suite detect wrongness?* | Semantically equivalent mutants |
| **O3 Structural** | type check, public-API diff, schema/interface conformance, invariant checks [S07] | Contract violations, unintended surface changes | Behavioural errors inside contracts |
| **O4 Static** | linters, analyzers, security scanners, secret scanning | Patterns, known-bad constructs | Anything novel |
| **O5 Build/repro** | build success, reproducible artifact hash | Non-building or non-reproducible output | Correct-but-wrong |
| **O6 Differential** | old-vs-new on recorded inputs, shadow execution | Behaviour change on real traffic | Inputs not recorded |
| **O7 Statistical human** | sampled review with a declared sample rate | What no machine checks | Anything it isn't sampled on |

**FR-007** Class O1 alone must never grant autonomy above L2. Autonomy above L2
requires at least one of O2, O3, or O6 — an oracle that reasons about *the suite
or contract*, not merely the code.

**Rationale.** O1 answers "does it pass?" A producer edits the tests. O2 answers
"would the suite have caught it being wrong?", which the producer's edit to the
tests cannot fake without also making the tests detect the mutation — i.e. doing
the work. This is the product's central verification mechanism.

### 4.3 Oracle strength — the missing instrument

[S01] notes there is no standard instrument for scoring a task's verifiability and
leaves the concept qualitative. Mutation score closes this. It is cheap to compute
locally, well-understood, and adversarially motivated by construction.

**Definition.** Inject syntactic mutations (flip a comparison, swap a constant,
invert a branch predicate, delete a statement). Oracle strength is the fraction of
non-equivalent mutants the oracle detects.

**FR-008** Oracle strength must be computed per **module**, not per repository.
Repository-wide averages hide the modules where autonomy is unsafe.

**FR-009** Oracle strength gates the autonomy ceiling:

| Oracle strength (module) | Max autonomy from this oracle |
| --- | --- |
| ≥ θ_hi (default 0.80) | L4 |
| ≥ θ_lo (default 0.60) | L3 |
| < θ_lo | L1 — oracle is informational only |

**FR-010** θ_hi and θ_lo must be configuration, calibrated per language and per
repository, and must be recorded with the change. Defaults above are
**(assumed)** and must be calibrated against measured escape data (§12.2) before
they are trusted.

**FR-011** Oracle strength must be tracked over time. A declining trend on a lane
is an alarm, because it usually means tests were added to pass rather than to
detect.

### 4.4 Adversarial audit

A verifier is itself a system under test and needs its own adversary [S15]. sofact
implements the three-role loop.

- **FR-012** The **hacker** role must attempt to obtain a passing verdict on a
  lane's output *without solving the task* — editing tests, hard-coding expected
  values, special-casing fixtures, disabling assertions, over-fitting to the
  sample.
- **FR-013** Every demonstrated exploit must produce a **fixer** action that closes
  it, and the exploit must be retained as a permanent regression case.
- **FR-014** Adversarial audit must be **sampled** (default 1-in-N, N configurable)
  on lanes at or below L3, and run on **100%** of changes on lanes above L3. The
  sample rate must increase automatically when an exploit is found.
- **FR-015** Exploit discovery rate must be exported as a first-class metric. It
  should trend to zero and stay there; a non-zero plateau means the lane is not
  actually verified.

**Design note — throughput vs. assurance.** Full adversarial audit on every change
triples token spend,
which is affordable locally but not free — it costs wall clock, and wall clock is
the binding resource (§7.3). Sample rates are therefore a throughput/assurance
tradeoff made explicit and configurable, never implicit.

### 4.5 Isolation

[S02] requires the evaluator to be causally isolated from the producer; on a shared
filesystem this degenerates into Goodhart's law. [S09] makes the structural point:
verification is its own *layer* with its own I/O contract, not a step inside
execution.

- **FR-016** The producer must have no read access to holdout scenarios, and no
  write access to any oracle artifact.
- **FR-017** Holdout scenarios must exist for every lane above L2, must be
  versioned, and must **never** be included in any context window shown to a
  producer. Leakage of a holdout into producer context is a lane-halting defect.
- **FR-018** Producer and evaluator must run in **separate processes**, with
  separate working directories. Separate *models* is preferred where resources
  allow (this is the best use of available memory).
- **FR-019** Isolation must be enforced by the deployment boundary where one
  exists: container, VM, or host (§8.3). Same-host, same-filesystem execution is
  the **degraded** configuration and must lower autonomy ceilings (§5.4).
- **FR-020** The factory must be able to run holdout evaluation on a machine the
  producer cannot reach, when the topology provides one (§8.3, T4).

### 4.6 The escape oracle — closing the verification regress

Who verifies the verifier? Any oracle the factory can influence is gameable in
principle. The regress terminates in exactly one place: **reality, after
deployment.**

- **FR-021** Every accepted change must be tracked forward through deploy. Escape
  events — revert, hot-fix, or incident implicating the same defect — must be
  recorded against the change, its lane, its oracle-strength band, and its
  autonomy level.
- **FR-022** Escape rate must be reported per lane and per autonomy level, and is
  the **primary safety metric** of the product. It cannot be gamed by the producer
  because it is measured by events the producer does not author.
- **FR-023** A lane whose escape rate exceeds its declared budget must have its
  autonomy ceiling **automatically reduced** until escape rate returns to budget.
  Manual override must be logged and attributed.

This is the product's theoretical anchor: verification strength is *hypothesised*
from oracle strength (§4.3) and *validated* by escape rate (§4.6). A factory that
verifies itself entirely internally has no ground truth; this is what gives it one.

---

## 5. Autonomy and admission control

### 5.1 The routing function

```text
admissible(lane) = intent_derivable
                 ∧ oracle_exists
                 ∧ blast_radius_bounded(deployment)

ceiling(lane)    = min( f(oracle_strength),      # §4.3
                        g(blast_bound),          # §5.2
                        h(deployment_isolation)  # §5.4
                      )

level(lane)      = min( ceiling(lane), floor(concerns) )
```

Concerns can only lower the result. **FR-024** the implementation must reject a
configuration where a concerns floor is used to justify a *higher* level.

### 5.2 Blast bound

- **FR-025** Every mutation must be a **commit on a dedicated branch** in a git
  repository. No in-place edits, ever. `git revert` is the primary undo mechanism.
- **FR-026** A lane must declare a maximum changed-file count and a maximum diff
  size. Exceeding either fails the lane and escalates — a large diff is
  unverifiable regardless of oracle results, because review bandwidth is the
  binding resource (§7.3).
- **FR-027** Autonomy L4 requires that the lane's file scope be **declared and
  enforced by permission**, not merely intended.
- **FR-028** Network egress must be **denied by default** and allow-listed per
  lane. This prevents both data exfiltration and an agent reaching the internet to
  satisfy a test it cannot satisfy locally.
- **FR-029** A lane must not be able to affect the factory's own configuration,
  oracle corpus, or credentials. Self-modification is a separate lane class with
  its own oracle (§1.5, M6).

### 5.3 The ladder

Defined by **fallback responsibility** [S16], not by how much work the machine
does. Most deployments that believe they are L3 are L2 in practice — a human is
nominally supervising but not actually verifying.

| Level | Who owns the outcome gate | sofact behaviour |
| --- | --- | --- |
| **L0** | Human does everything | Factory not used |
| **L1** | Human, factory informs | Factory produces analysis, escalations, and oracle reports; never mutates |
| **L2** | Human verifies each change; factory proposes | Changes staged as branches; human reviews every one |
| **L3** | Human is the fallback; factory merges within declared bounds | Auto-merge on oracle pass, human notified, revert available and monitored |
| **L4** | Factory owns the gate within a bounded domain; human not required | Auto-merge, unattended, escape rate monitored with automatic downgrade |
| **L5** | No domain restriction | **Not offered.** Out of scope. |

### 5.4 Autonomy ceilings are per-deployment

A consequence of [S02][S15] worth stating as a product principle: **the same lane
has different admissible ceilings on different hardware**, because what bounds
blast radius is the isolation the environment actually provides.

| Topology | Isolation | Notes | Ceiling modifier |
| --- | --- | --- | --- |
| **T1 Dev / reference** | None — shared filesystem, no container boundary, producer and evaluator on one host | This is the current development machine | **−1 level.** L4 lanes run at L3 |
| **T2 Cloud VM** *(product target)* | Container per lane, VM boundary, egress-denied, git-backed | Standard product deployment | Baseline |
| **T3 Air-gapped / sovereign** | T2 with no egress at all; customer-hosted; local models only | Primary ICP | Baseline |
| **T4 Split** | Producer and evaluator on separate hosts | Strongest practical isolation | **+0**, but unlocks L4 for lanes whose blast bound previously failed |

**FR-030** The active topology, its isolation guarantees, and its ceiling modifier
must be reported in every oracle report and attached to every change.

**FR-031** A lane that would be L4 in T2 must be **refused** at L1 in T1 rather
than silently downgraded, unless an explicit operator override is recorded.

### 5.5 Staging modes

For any deployment touching another party's production (§11.4):

- **FR-032** New lanes must run in **shadow mode** first: produce and verify, but
  do not surface output. Establishes a baseline escape rate with zero risk.
- **FR-033** Then **advisory mode**: surface output, require human acceptance.
- **FR-034** Only then **gated mode** per the computed level.
- **FR-035** Promotion between modes must be gated on measured escape rate, not on
  elapsed time or operator optimism.

---

## 6. Lane catalogue (v1)

The product's substance. Each lane is a row in a configuration table; adding a lane
is a data change, not a code change — which is how the product avoids the
bespoke-apparatus trap [S10].

| ID | Lane | Intent source | Oracle set | Blast bound | Ceiling | Throughput class |
| --- | --- | --- | --- | --- | --- | --- |
| **L01** | Dependency / vendor update | Upstream changelog + manifest diff | O1 O3 O5 O2 | One manifest + lockfile, one branch | **L4** | Medium |
| **L02** | Mechanical codemod / API migration | Declarative before/after AST pattern | O1 O3 O5 + idempotence | Declared file set | **L4** | High |
| **L03** | Test generation for existing behaviour | Mutation survivors + uncovered code | **O2 must rise**, O1, coverage non-decreasing | Test files only | **L4** | High |
| **L04** | Lint / type / dead-code debt | Static analyzer findings | O4 clean, O1 no regression, O5 | Declared file set | **L4** | High |
| **L05** | Doc / comment sync | Code↔doc drift detection | O5 doc build, link check, no code change | Docs only | **L4** | High |
| **L06** | Issue triage & routing | Issue text | O7 sampled review + confusion matrix vs. gold set | Labels only | **L3** | High |
| **L07** | Bugfix in high-oracle module | **Failing test / reproducing case** | O1 (previously-failing now passes), O2 canary, O3, full suite | Module's file set | **L3** | Medium |
| **L08** | Feature within frozen interface | Human-authored interface stub + acceptance tests | O1 acceptance, O3 conformance, O7 | Interface boundary | **L2–L3** | Medium |
| **L09** | Refactor under invariant model | Declared invariant set to preserve | O3 structural, O1, public-API diff empty | Declared module | **L2–L3** | Medium |
| **L10** | Release / version bump | Merged commits since last tag | O5 build, changelog completeness, O3 | Version files + changelog | **L3** | Low |
| **L11** | Adversarial audit *(service, not a lane)* | Any lane's output | Demonstrated exploit or clean | N/A | N/A | Sampled |
| **L12** | Factory self-maintenance | sofact's own issue tracker | sofact's own suite **plus an independently authored oracle** | sofact's repo | **L2, gated** | Low |

### 6.1 Why these lanes and not others

- **L03 is the flagship.** Its output is measured by the very instrument that
  judges it: generating tests that kill previously-surviving mutants is
  self-verifying. Success is not "tests were written" but "oracle strength rose."
  It is also the lane that *manufactures the capability* the other lanes depend on
  — running it first raises every other lane's ceiling.
- **L07's intent source is a failing test.** That is the most machine-derivable
  intent that exists, and it is the honest version of what SWE-bench measures
  [S04]. Where no failing test exists, the lane is inadmissible — sofact does not
  guess at intent.
- **L01–L05 are L4-eligible** because their blast bounds are provable and their
  oracles are strong. They are also low-glamour. That is the point: they are where
  unattended operation is genuinely safe, and they are where a maintenance
  business is actually built (§11.2).
- **L12 is included but constrained.** Self-modification is the most compelling
  version of the product vision and the one with unbounded blast radius. It is
  gated to L2 because the oracle is authored by the system under test; it becomes
  legitimate only when an independently authored oracle exists (M6).
- **Deliberately absent:** architecture, ambiguous requirements, novel algorithms,
  performance tuning under unknown constraints, auth/payments/PII/migrations,
  production deploys. These are L1 by construction (§1.5). Listing them as absent
  is the product's most important honesty.

### 6.2 Language scope

Mutation testing requires per-language tooling, and it is the load-bearing
instrument. **FR-036** v1 must support whichever language is chosen for D1 (§14)
end-to-end, including mutation tooling, with additional languages added only when
their mutation tooling is verified to behave (equivalent-mutant handling differs
materially by language). Claiming a language without mutation support means
claiming a lane with no measurable oracle strength — which the product must
refuse.

---

## 7. Non-functional requirements

### 7.1 Portability (the product requirement that supersedes §4 of `findings.md`)

The development machine is an Apple Silicon laptop. **The product is not bound to
it.** Earlier environment findings — 42 GiB free disk, no container runtime —
describe the *dev instance*, not the product.

- **NFR-001** sofact must run on **x86_64 Linux** and **arm64 Linux** (and
  secondarily macOS arm64 for development), in a container, with no GPU required
  (GPU optional and detected).
- **NFR-002** Model inference must be behind an abstraction (§10.1) supporting at
  minimum: an OpenAI-compatible HTTP endpoint (vLLM / llama.cpp / Ollama /
  TGI), and a hosted provider for lanes where the operator permits egress.
- **NFR-003** No component may depend on CUDA, Metal, or any specific accelerator.
  Performance characteristics may vary; behaviour must not.
- **NFR-004** The declared resource budget (CPU, RAM, disk) must be enforced so
  the factory cannot starve the host. This is a hard requirement for a product
  deployed onto infrastructure that has other jobs.
- **NFR-005** Storage budget must be **declared per deployment**, with model
  weights treated as a deployment-time selection. The dev instance's 42 GiB free
  must not appear as a product constraint anywhere.

### 7.2 Durability and long-horizon operation

Multi-day autonomy is bounded by state durability and objective retention, not by
per-step reasoning quality [S08].

- **NFR-006** All task state must be durable on disk and **resumable after
  SIGKILL** at any point, with no task left in an indeterminate state.
- **NFR-007** The active objective must be **re-injected into context every
  cycle**, not carried implicitly. Objective drift is a known failure mode [S08].
- **NFR-008** The factory must **health-check its own tooling** each cycle
  (oracle canaries [FR-004], plus a self-test of each lane's executor), because
  silent degradation of the agent's own tools is a known failure mode [S08].
- **NFR-009** Every external action must be idempotent or transactional. A resumed
  task must not double-apply a change.
- **NFR-010** The factory must survive model-backend unavailability: queue,
  back off, resume. It must not corrupt state or spin.

### 7.3 Throughput

See `docs/research/findings.md` §F3 for the arithmetic. The binding constraint on
a single-box deployment is **wall clock**, not token spend, and the binding
constraint on the whole factory is **human review bandwidth**.

- **NFR-011** The product must ship a **measured throughput table** for its
  reference configuration: tokens/second and prefill latency per model class per
  context length. Deployment planning depends on it, and it differs per hardware.
- **NFR-012** Model routing must be **per-lane class-declared** (reasoning-depth
  vs. throughput), not global. On memory-bandwidth-bound hardware, decode speed is
  set by *active* parameters: MoE models are the workhorse for volume, dense
  models for low-volume reasoning steps.
- **NFR-013** Prompt-prefix caching must be used where the backend supports it.
  On unified-memory hardware prefill is compute-bound and re-runs each turn,
  making **context length a latency variable**. Context discipline is a
  throughput feature, not a tidiness preference.
- **NFR-014** Concurrency must be **explicitly bounded** and defaulted low.
  Concurrent agents contend for the same memory bandwidth and can make total
  throughput *worse* than serial execution. Parallelism is not free.

### 7.4 Security and governance

- **NFR-015** No source code, prompt, or artifact may leave the deployment without
  explicit per-lane egress permission (FR-028). Default deny.
- **NFR-016** All credentials must be scoped per lane and non-escalatable. A lane
  must not be able to read another lane's credentials.
- **NFR-017** Every state transition must be auditable: intent → plan → change →
  oracle results → decision → outcome. Traceable by change ID.
- **NFR-018** Any change touching auth, payments, PII, migrations, or production
  configuration must be refused **regardless of oracle results**. This is a
  concerns floor, not a heuristic (§5.1).
- **NFR-019** The product must be able to answer, for any line of code it wrote:
  which intent, which lane, which oracle set, which autonomy level, and which
  human (if any) accepted it.

### 7.5 Observability

- **NFR-020** Every metric in §12 must be exported in a standard format
  (Prometheus/OpenMetrics or equivalent) and must be available per lane.
- **NFR-021** The factory must record **every human intervention** — every
  escalation resolved, every change rejected in review, every override. The
  intervention log is the process loop's input [S06] and the only honest measure
  of whether the factory is improving.
- **NFR-022** Escalations must be actionable: what was tried, which oracles ran,
  which oracle failed and how, and what a human decision would unblock.

---

## 8. Architecture

### 8.1 Components

Deliberately few. Component count is a budgeted quantity because apparatus cost is
the historical failure mode [S10], and runtime tool synthesis [S05] is preferred
over hand-built tool suites where it does not compromise oracle integrity.

| Component | Responsibility | Notes |
| --- | --- | --- |
| **Intent intake** | Validate and type incoming work; run the §5.1 admission predicate | Rejects at the door |
| **Oracle registry** | Store oracle definitions, strength measurements, canaries, holdouts; enforce read-only | The product's crown jewels |
| **Planner** | Turn intent into a bounded change plan | Separate context from executor |
| **Executor** | Produce the change, on a branch, within the blast bound | No oracle access |
| **Verifier** | Run oracle sets; own the verdict | Separate process, ideally separate host |
| **Adversary** | Attack the verdict [S15] | Sampled per FR-014 |
| **Router/Policy** | Compute autonomy level; apply concerns floors; mode gating | Pure function, testable |
| **State store** | Durable task state, resumability, audit trail | NFR-006 |
| **Process loop** | Scorecards, escape tracking, automatic ceiling adjustment | [S06] |
| **Escalation surface** | Structure refusals and failures for humans | The most-used verb (§3.1) |

**FR-037** The Router/Policy component must be a **pure function** of declarative
configuration and measured inputs, so autonomy decisions are reproducible and
auditable [NFR-017]. A policy that depends on model output is untestable and thus
unacceptable.

**FR-038** The Verifier must not import or invoke any Executor code. Shared code
between producer and evaluator is an isolation defect.

### 8.2 Data model (conceptual)

Entities, with the traceability chain [NFR-019] as the organising principle:

```text
Intent ──▶ Lane ──▶ Change ──▶ OracleRun ──▶ Decision ──▶ Outcome
                       │                          │          │
                       └──▶ Branch/Commit         │          └──▶ Escape (FR-021)
                                                  └──▶ Autonomy level + justification

Lane ──▶ Oracle ──▶ OracleStrength (time series)
Lane ──▶ Holdout scenarios (never in producer context)
```

**FR-039** `Decision` must record the *inputs that produced it* — oracle strength
at the time, topology, ceiling modifiers, concerns floors — not just the resulting
level. Without this, an escape cannot be attributed and the process loop is blind.

### 8.3 Deployment topologies

T1–T4 as defined in §5.4. **FR-040** topology must be a first-class configuration
input that modifies autonomy ceilings, not an operational detail.

**FR-041** T2 (cloud VM, product target) must be deployable as a single VM with no
external service dependencies beyond a model endpoint and a git remote. Air-gapped
T3 must be deployable with **no** external dependencies.

**FR-042** The dev instance (T1) must be runnable, and must report its degraded
ceiling rather than silently behaving as if it were T2. Its purpose is development
of the factory itself; its autonomy ceiling is deliberately lower.

---

## 9. Interfaces

### 9.1 Design principles

Following the parent project's conventions: ergonomic, intuitive, hard to get
wrong. Applied here specifically:

1. **Declare before run.** Lanes and oracles are declared in versioned config;
   nothing is configured implicitly at runtime.
2. **Refuse, don't degrade silently.** An inadmissible lane errors; it does not
   run at a lower level without saying so.
3. **Oracles are values, not procedures.** An oracle is a declarative artifact
   (command, expected verdict, timeout, strength) so it can be versioned, hashed,
   canary-tested, and permission-protected.
4. **Every identifier is a UUID7 string** (parent-project convention), so changes,
   intents, and oracle runs are time-ordered and collision-free across nodes.

### 9.2 Lane definition

```yaml
# lanes/l03-test-generation.yaml
id: L03
name: test-generation
intent:
  type: mutation-survivors          # machine-derivable, from the oracle registry
  source: oracle-registry
oracles:
  - ref: o1-full-suite
    required: true
  - ref: o2-mutation-delta
    required: true
    rule: must_increase                # output measured by the instrument judging it
  - ref: o2-coverage
    rule: non_decreasing
blast_bound:
  paths: ["tests/**"]                   # enforced, not advisory (FR-027)
  max_files: 20
  max_diff_lines: 600
  reversible: true
concerns:
  floors: []                            # this lane touches only test files
routing:
  throughput_class: high
```

**FR-043** Lane definitions must be **validated on load** with actionable errors:
missing oracle, unenforceable blast bound, a concerns floor used to raise a level,
or an oracle reference that does not exist.

**FR-044** Lane definitions must be hashed into the change record, so a lane
change invalidates prior escape-rate evidence for that lane.

### 9.3 Oracle definition

```yaml
id: o2-mutation-delta
class: O2
command: ["uv", "run", "mutmut", "run", "--paths-to-mutate", "{scope}"]
verdict:
  pass_when: "score >= baseline + {min_delta}"
  min_delta: 0.0
strength:
  measured: 0.87                          # what THIS oracle detects
  measured_at: 2026-09-12
  method: mutation                         # how strength was established
canary:
  must_pass: tests/canary/test_oracle_contract.py
  must_fail: tests/canary/mutant_known_bad.py
timeout_s: 900
```

**FR-045** `strength.measured` must be refreshed on a declared schedule; a stale
measurement must be reported as stale and must **not** support the autonomy level
it previously justified (§4.3, and see R4 in §13).

### 9.4 Operational surface

- **CLI** — `sofact init <repo>` (onboard + oracle report), `sofact lane list`,
  `sofact verify <change>`, `sofact status`, `sofact escalate`.
- **HTTP API** — the same capabilities for programmatic integration [NFR-002].
- **Event stream** — every state transition [NFR-017], consumed by the scorecards
  and by external observability.

**FR-046** `sofact init` must produce the **oracle report and lane-admissibility
report** before any work runs. This is the product's first deliverable and is
useful standalone: it tells an organisation how much autonomy their codebase
*actually* supports, which most organisations do not know.

### 9.5 Metering and payment (optional, later)

**FR-047** If metered, the billable unit must be the **verified unit** (§2), not
tokens — sofact's costs are not token-denominated, and metering tokens would
misprice the value delivered.

**FR-048** x402 (HTTP 402) may be supported as a payment rail for
machine-to-machine metering [S14]. It is a rail, not a business model; the product
must not depend on it.

---

## 10. Model strategy

### 10.1 Abstraction

- **FR-049** All model access must go through one interface supporting an
  OpenAI-compatible endpoint plus optional hosted providers. This is a direct
  response to vendor repricing risk [S13]: the local/remote split must be
  configuration, never a rewrite.
- **FR-050** No prompt, lane, or oracle may depend on model-specific behaviour
  beyond declared capability class. Lanes declare the *class* they need
  (reasoning-depth or throughput), not a model name.

### 10.2 Routing classes

| Class | Used for | Hardware implication |
| --- | --- | --- |
| **Throughput** | High-volume, low-depth lane work: test generation, codemods, triage, classification | MoE or small dense; latency matters most |
| **Reasoning** | Planning, failure diagnosis, adversarial hacking | Dense or large MoE; low volume, depth per token matters |
| **Evaluation** | Oracle strength computation, differential analysis | Ideally deterministic tooling, not a model |

**FR-051** Evaluation must prefer **deterministic tooling** over models wherever an
equivalent exists. A model-based oracle has unmeasurable strength, which makes it
unusable as a gate under §4.3. Models may *assist* evaluation; they may not *be*
the verdict except in O7, which is explicitly statistical and never sufficient
alone (FR-007).

### 10.3 Fine-tuning

Deliberately narrow scope, for a product-relevant reason rather than a hardware one:
fine-tuning is only worth the operational cost when a lane is both **high-volume**
and **narrow**.

- **FR-052** Fine-tuning, where used, targets exactly one or two lanes: lane
  routing/classification, and mutation-survivor selection for L03. Both are
  high-volume, low-depth, and have objective labels derivable from existing data.
- **FR-053** Fine-tuned models must never be an oracle. A model trained on the
  factory's own decisions cannot verify them.
- **FR-054** The product must not ship fine-tuned weights; it must ship the
  *recipe* (dataset extraction + training config), because customers have
  different repositories and their own data must not leave their deployment.

---

## 11. Business model

### 11.1 The honest position on "monetize autonomously"

The original goal included a factory that monetizes itself. **This specification
narrows that to monetization being human-decided and machine-executed**, and the
reason is structural rather than cautious: pricing, positioning, contract terms,
and counterparty selection have no oracle. [S16] places them at L1 by definition.
An agent that cannot be verified cannot be trusted with another party's money, and
no improvement in model capability changes that — it is a property of the task
class, not the agent.

What the product *can* automate: metering, invoicing, delivery, and the
maintenance work itself.

### 11.2 Where the value concentrates

The lanes that are L4-eligible (L01–L05) are exactly the recurring maintenance
work that organisations under-invest in and cannot easily outsource: dependency and
security updates, lint/type debt, doc drift, test coverage. This is unglamorous
and it is a **recurring revenue** business with a measurable deliverable, which is
a much better product than a capability demonstration.

The L4 lanes are also, not coincidentally, the ones whose blast bounds are
provable — the same property that makes them safe makes them sellable.

### 11.3 Packaging

| Offering | Model | Fit |
| --- | --- | --- |
| **Oracle assessment** | One-off, fixed fee | Uses `sofact init` (§9.4). Lands the product, delivers value immediately, and produces the data needed to price everything else. |
| **Sovereign maintenance** | Annual, per repository | Primary. Customer-owned infrastructure. Value = recurring verified maintenance. |
| **Managed maintenance** | Annual + per-verified-unit | Secondary. Runs on customer hardware; zero marginal token cost gives real margin. |
| **Self-hosted license** | License + support | Tertiary. Customer runs the line. |
| **Metered verified change** | Per VU, x402-optional | Later. Requires reputation; must be bootstrapped by the offerings above. |

### 11.4 The governance boundary

Stated as a product constraint, enforced in code, not policy:

- **FR-055** sofact must **not** autonomously: set prices, accept customers, sign
  agreements, move money, or make commitments on behalf of the operator.
- **FR-056** Any deployment where sofact operates inside another party's
  production must use the §5.5 staging sequence and must produce escape-rate
  evidence at each stage before promotion.

**R11 (risk).** The commercial framing here is a bet that verification quality is
what buyers want. A buyer may instead want the *appearance* of autonomy, in which
case this product is over-engineered for the market and loses to a demo. This is
the single largest commercial risk and it is not resolvable by engineering.

---

## 12. Metrics and SLOs

### 12.1 Primary metrics

| Metric | Definition | Why this one |
| --- | --- | --- |
| **VUHM** | Verified units per human-minute | The factory's real ceiling is review bandwidth (§7.3). This is the metric that improves when the product works. |
| **Escape rate** | Escapes per verified unit, per lane | The only oracle the producer cannot influence (§4.6). Primary *safety* metric. |
| **Oracle strength** | Mutation score per module, trended | Leading indicator; escape rate is the lagging one. |
| **Intervention rate** | Human interventions per verified unit, per lane | The process loop's input [S06]; the honest measure of autonomy actually achieved. |
| **Exploit discovery rate** | Adversarial exploits found per audit | Should trend to zero and stay there [S15]. |
| **Cost per VU** | Infra + energy + human, per verified unit | Locally, tokens are free and time is not. Cost must be denominated in the scarce resource. |

### 12.2 Targets

- **NFR-023** Targets must be **established from baseline measurement**, not
  asserted. M0 (§12.3) exists solely to produce them.
- **NFR-024** The product must refuse to report a target it has not measured. This
  requirement exists because this document currently contains no measured
  throughput, escape, or review-time figures — publishing invented ones would
  violate the product's own verification-first principle.

### 12.3 Baseline measurement plan (M0)

Blocking prerequisites for any target:

1. **Throughput table** — tokens/second and prefill latency, per model class ×
   context length, on the reference deployment (NFR-011).
2. **Oracle strength baseline** — mutation score per module, on the first target
   repository (FR-008).
3. **Human review time per diff** — logged, not estimated. This sets the VUHM
   ceiling and therefore every other target.
4. **Escape baseline** — requires a deployment. Until then, escape rate is
   unmeasurable and every autonomy ceiling is a hypothesis.
5. **Isolation verification** — confirm the T2 container boundary and egress denial
   actually hold, since FR-019 makes autonomy depend on them.

---

## 13. Risks

| # | Risk | Type | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| **R1** | Product is over-engineered for a market that wants an autonomy demo (§11.4) | Commercial | Fatal | Lead with the oracle assessment offering; sell measurable refusal |
| **R2** | Autonomy depends on isolation (FR-019) that is asserted but never verified | Technical | High — silent unsafety | M0 item 5; topology reported on every change (FR-030) |
| **R3** | Default θ_hi/θ_lo thresholds are assumed, not calibrated | Technical | Medium — wrong ceilings | FR-010 calibration; automatic downgrade on escape (FR-023) |
| **R4** | Oracle strength goes stale, silently justifying an autonomy level | Technical | High | FR-045 staleness reporting; FR-004 canaries |
| **R5** | Apparatus maintenance cost exceeds value — the historical failure [S10] | Structural | Fatal | Lanes are data (FR-043), not code; component count budgeted; factory size tracked from M1 |
| **R6** | Escape rate unmeasurable until a deployment exists, so ceilings are hypotheses | Structural | Medium | Shadow mode (FR-032); treat all pre-deployment ceilings as provisional |
| **R7** | Reward hacking via generated tooling [S05] rather than direct test editing | Technical | High | FR-003, FR-012, FR-038; generated tools are subject to the same oracle discipline |
| **R8** | Holdout leakage into producer context (FR-017) | Technical | High — invalidates all measurement | Context assembly must be a permission boundary, not a prompt instruction |
| **R9** | Single-node throughput contention makes parallelism counterproductive (NFR-014) | Performance | Low–Medium | Concurrency bounded and defaulted low; measured in M0 |
| **R10** | Mutation testing cost explodes on large repositories | Performance | Medium | Per-module scope; incremental mutation; budget per lane |
| **R11** | Fine-tuned model becomes an oracle by drift (FR-053) | Technical | Medium | Enforced by component separation (FR-038) |
| **R12** | Legal/regulatory exposure from operating inside another party's production | Legal | High | FR-055/FR-056; staging modes; contract per §11.4 |

---

## 14. Open decisions

Genuine forks, not rhetorical questions. Each materially changes the build.

| # | Decision | Why it blocks | Recommendation |
| --- | --- | --- | --- |
| **D1** | **Which repository is the first target?** | Every threshold, mutation-tooling choice, and lane set depends on it. [S01] implies an untested greenfield repo admits almost no autonomy. | Pick a real, tested repository with an existing suite. **Do not** start with sofact itself — it has no oracle yet, and it is not a git repo. |
| **D2** | **Implementation language and stack** | Determines mutation tooling, packaging, deployment | Python + `uv` (parent-project convention: async, tabs, Pydantic v2, UUID7, `service.py`/`views.py`, `tests/ci/`). Confirm. |
| **D3** | **First vertical for the sovereign ICP** | Determines compliance concerns floors [NFR-018] and therefore several lanes' ceilings | Recommend a segment with real source-confidentiality pain and an existing test culture (financial back-office, health data processing, defence-adjacent). |
| **D4** | **Human review budget** | Sets the VUHM target, which sets everything downstream | Needs a real number from you: hours/week and willingness per diff. |
| **D5** | **Language scope for v1** | Mutation tooling is per-language and is the load-bearing instrument (FR-036) | One language end-to-end. Adding a second is a milestone, not a config change. |
| **D6** | **Is x402/metering in v1?** | Scope | No. License/assessment in v1; metering after reputation exists (FR-047/FR-048). |
| **D7** | **Is L12 (self-modification) in v1?** | Unbounded blast radius; oracle authored by the system under test | No. L2-gated, M6, and only with an independently authored oracle. |
| **D8** | **Fine-tuning: yes/no, and which lane?** | Disk and complexity budget | At most one: lane routing (FR-052). Recipe-only delivery (FR-054). |
| **D9** | **Container runtime assumption on the target VM** | FR-019 and the entire ceiling model depend on a real isolation boundary | Docker or Podman required on T2/T3. Confirm this is acceptable; if not, the product needs its own isolation story and ceilings drop. |
| **D10** | **CPU-only target support** | NFR-001 says no GPU required; mutation testing plus inference on CPU may be unusably slow | Confirm: CPU-only supported-but-slow (contractual expectation), or GPU required (narrower market, simpler claims)? |

---

## 15. Roadmap

Each milestone has testable exit criteria. Milestones are ordered so that
capability is *measured* before it is *claimed*.

| Milestone | Deliverable | Exit criteria |
| --- | --- | --- |
| **M0** | Instrumentation | Baseline measurement plan (§12.3) complete. Throughput table, mutation baseline, review-time log exist as real numbers. |
| **M1** | Oracle registry + `sofact init` | On the D1 repository: mutation score per module, oracle report, lane-admissibility report. **Deliverable is valuable with zero autonomy.** |
| **M2** | L03 (test generation) at L4 | Oracle strength measurably rises on ≥1 module; existing suite still passes; escape rate tracked from first merge; adversary (L11) finds zero exploits on 20 consecutive changes. |
| **M3** | Verification subsystem complete | All seven oracle classes implemented; canaries (FR-004) demonstrably halt the lane when seeded with a known-bad oracle; holdout leakage test passes; adversarial loop finds and closes a real exploit. |
| **M4** | Autonomy router + process loop | Router is a pure function with tests (FR-037); scorecards live; automatic downgrade on escape demonstrated (FR-023); intervention log complete (NFR-021). |
| **M5** | T2 deployment packaging | Containerised, single-VM, egress-denied, resumable after SIGKILL (NFR-006); topology reported on every change (FR-030); ceilings correctly differ between T1 and T2 (FR-031). |
| **M6** | Lane expansion + governance | L01–L05 running; staging modes (FR-032–035) demonstrated; escape-rate-gated promotion working; L12 evaluated against an independently authored oracle. |
| **M7** | Commercial surface | Oracle-assessment offering productised; per-VU metering; license/support packaging. |

**Sequencing rationale.** M2 comes before the router because a router that routes
to lanes which do not exist is untestable. M3 comes before M5 because packaging
before verification is verified would ship the isolation model on faith (R2). M1
is deliberately useful standalone because it is the product's land-and-expand
surface and, more importantly, because it produces the measurements every later
claim depends on.

---

## 16. Traceability

Which specification commitments rest on which sources.

| Spec section | Sources | Strength |
| --- | --- | --- |
| §4 verification-first model | [S01] [S04] [S15] | Strong — four independent sources converge |
| §4.2 oracle classes, multiple classes | [S07] [S09] | Medium — argued, not measured |
| §4.3 mutation score as the instrument | [S01] (gap identified there) | **Novel** — introduced by this spec; must be validated in M0 |
| §4.4 adversarial audit | [S15] | Medium — one source, suite-specific figures |
| §4.5 isolation | [S02] [S09] | Medium — practitioner argument plus structural analogue |
| §4.6 escape oracle | [S06] | **Novel** — closes the regress; no source states it |
| §5 autonomy ladder | [S02] [S16] | Medium — AV framing mapped onto SE |
| §5.1 routing predicate | [S11] | Medium — persuasive, untested |
| §6 lane catalogue | [S04] [S05] | Medium — lane choices argued from blast-bound provability |
| §7.1 portability | [S12] [S13] | Strong — the product constraint; supersedes dev-machine limits |
| §7.2 durability | [S08] | Medium — qualitative failure modes more trustworthy than the number |
| §7.3 throughput | [S12] | Weak — first-principles maths; **must be measured** (NFR-011) |
| §10 model abstraction | [S13] | Strong — vendor-risk argument |
| §10.3 fine-tuning scope | [S12] | Weak — argued from throughput classes |
| §11 business model | [S14] [S16] [S17] | Weak — market reasoning, not evidence |
| §1.5 / §11.1 non-goals | [S10] [S16] | Medium — historical failure mode plus autonomy-ladder logic |

**Provenance caveat, repeated deliberately.** Every source is `reported` —
not re-verified (`docs/sources/README.md` § Verification queue). No claim in this
document is `content-verified`. The structural findings are trustworthy because
independent sources agree; the numbers are hypotheses. NFR-024 exists so this
document cannot quietly pretend otherwise.

---

## Appendix A — Reference links

[S01]: ../sources/s01-assistance-to-autonomy.md
[S02]: ../sources/s02-dark-factory-soeters.md
[S04]: ../sources/s04-swe-bench-verified.md
[S05]: ../sources/s05-live-swe-agent.md
[S06]: ../sources/s06-sase-framework.md
[S07]: ../sources/s07-mage-model-based-agentic-se.md
[S08]: ../sources/s08-harness-of-harness.md
[S09]: ../sources/s09-six-layer-reference-architecture.md
[S10]: ../sources/s10-software-factory-history.md
[S11]: ../sources/s11-gethuman-lanes.md
[S12]: ../sources/s12-local-coding-models-2026.md
[S13]: ../sources/s13-anthropic-harness-billing.md
[S14]: ../sources/s14-x402.md
[S15]: ../sources/s15-hacker-fixer-loop.md
[S16]: ../sources/s16-shapiro-autonomy-ladder.md
[S17]: ../sources/s17-factory-ai.md

## Appendix B — Status of prior-phase findings

How the product framing changed the conclusions in `docs/research/findings.md`.

| Prior finding | Status under product framing |
| --- | --- |
| F1 verifiability is binding | **Unchanged.** Now the product thesis. |
| F2 evaluation isolation | **Strengthened.** Becomes FR-016–FR-020 and a *deployment-topology* property (§5.4), not a single-host problem. |
| F3 local economics | **Reframed.** Dev-machine arithmetic is a reference configuration; the product requirement is hardware-agnostic model routing (NFR-002, FR-049). |
| F4 per-lane autonomy | **Unchanged.** Becomes §5. |
| F5 durability | **Unchanged.** Becomes NFR-006–NFR-010. |
| F6 apparatus cost | **Unchanged and escalated.** Drives the lanes-are-data design (FR-043) and component budget (§8.1). |
| F7 explicit model as oracle class | **Narrowed** to O3 structural oracles (FR-007). |
| F8 mutation score | **Elevated** to the central instrument (§4.3). |
| §4 dev constraints (42 GiB disk, no Docker) | **Superseded for the product**, retained for the T1 dev instance. Disk and container availability become *deployment-time declared budgets* (NFR-004, NFR-005, D9). |
| §5 monetization ranking | **Unchanged in substance**, now packaged in §11.3. |
| §7 open questions | **Resolved:** Q2 (product, not personal capability) and Q8 (operate = keep the line running). **Still open:** D1, D3, D4, D5, D9, D10. |
