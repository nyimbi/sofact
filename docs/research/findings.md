# sofact — Research Findings

Synthesis of the source ledger in `docs/sources/`. Written 2026-09-12.

**Provenance warning.** Every source is `reported` — encountered in this session,
not re-verified. The arXiv API rate-limited the re-verification pass, and three
essays were captured without URLs. Treat specific numbers below as *directional
hypotheses to be measured*, not facts. The structural findings (which rest on
multiple independent sources agreeing) are more trustworthy than any figure in
them. See `docs/sources/README.md` § Verification queue.

---

## 1. The fourteen convergent findings

### F1 — Verifiability, not capability, is the binding constraint

[S01] [S04] [S11] [S15] — four independent sources, same conclusion from
different directions:

- The SLR [S01] finds output verifiability is the dominant predictor of how much
  autonomy teams actually grant. Capability is necessary, not sufficient.
- SWE-bench [S04] is only a well-defined benchmark *because* the oracle is the
  repo's own test suite. Every headline agentic-coding number is measured on
  tasks that were selected for being mechanically checkable.
- [S11] reduces routing to three binary qualifiers: intent machine-derivable,
  outcome machine-observable, blast radius machine-bounded.
- [S15] shows what happens when you skip the third and fourth checks: ~16% of
  benchmark tasks are passable *without solving them*.

**Consequence.** sofact's design axis is not "which model" but "which oracle." For
every lane, name the machine oracle that decides pass/fail *before* deciding how
much autonomy the lane gets. A lane with no oracle gets read-only or human-gated
autonomy regardless of model quality.

### F2 — The evaluator must be causally isolated from the producer, and this is the hardest constraint here

[S02] argues holdout scenarios plus isolated evaluators, on the grounds that a
producer sharing an evaluation substrate with its own critic degenerates into
Goodhart's law. [S15] demonstrates the mechanism concretely: a solver scored
against a suite it can edit will edit the suite.

On a single M2 Max this is structurally awkward — same box, same filesystem, and
plausibly the same model weights for producer and evaluator. Isolation therefore
has to be *constructed*, not inherited:

1. **Oracle corpus is read-only to producers.** Enforced by filesystem
   permissions, not by prompting.
2. **Oracle integrity is self-tested each cycle.** A canary suite that must pass
   and a canary mutant that must be killed; if either moves, halt the factory.
3. **Two independent oracle classes.** Tests (behavioural) plus model-level
   structural checks [S07] (interfaces, invariants, schema conformance). Different
   classes fail differently.
4. **Separate context, ideally separate weights** for producer and reviewer. With
   96 GiB unified memory, co-residency is affordable — this is exactly what the
   memory budget should be spent on.

[S09] supplies the structural version of the same argument: verification is its
own *layer* with its own input/output contract, not a step inside execution. A
producer that calls its own `verify()` helper is not layered — it is a producer
grading its own work, and the permission boundary has to exist somewhere real.

### F3 — Local economics invert the cloud design: throughput-constrained, not cost-constrained

[S12] [S13]. Hosted agents optimise $/token; a local factory has zero marginal
token cost and a hard wall-clock ceiling. The design objective flips from *minimise
spend* to *maximise verified artifacts per hour*.

The arithmetic that drives model choice — decode is memory-bandwidth-bound:

| Model class | Weights @4-bit | Bytes read/token | Ceiling @ ~400 GB/s | Realistic |
| --- | --- | --- | --- | --- |
| Dense 27B | ~14 GB | ~14 GB | ~28 tok/s | 15–22 tok/s |
| MoE 35B-A3B | ~18 GB resident | ~1.5–2 GB (3B active) | ~230 tok/s | 60–120 tok/s |

Total parameters buy *quality per token*; **active** parameters set *tokens per
second*. A 5–8× decode gap compounds across a 50-turn agent loop into minutes
versus tens of minutes. **MoE is the correct workhorse for lane execution**; dense
models are for planning steps where reasoning depth per token matters and volume
is low.

Second-order lever most people miss: on Apple Silicon, **prefill is compute-bound
and re-runs every turn** unless KV cache is reused. Context length is therefore a
*latency* variable, not merely a cost variable. Prompt-prefix caching and tight
context discipline are throughput features.

### F4 — Autonomy is per-lane, decided by two orthogonal dials

[S02] [S16] [S11]: the qualifiers [S11] decide *admission*; the ladder [S02][S16]
decides *level*; concerns (security, PII, money, compliance, cost) are **floors
that veto**, not qualifiers. The ladder is defined by who owns the outcome gate —
*fallback responsibility* — not by how much work the machine does.

This gives a clean three-stage routing function:

```text
admissible(lane) = intent_derivable ∧ oracle_observable ∧ blast_radius_bounded
level(lane)      = min(ladder_position(oracle_quality), floor(concerns))
```

### F5 — Multi-day autonomy is a durability problem, not a reasoning problem

[S08] [S06]. What breaks over days is context exhaustion, objective drift, silent
degradation of the agent's own tooling, and unrecoverable state after a crash
mid-task. The mechanisms are unglamorous: task state durably on disk (not in
context), explicit objective re-injection each cycle, health self-tests on the
factory's own tools.

[S06] adds the structural point: there are **two loops**. The task loop (issue →
patch → verify) and the process loop (which lanes work, which oracles are noisy,
where humans keep intervening). The intervention log is the process loop's input,
and it is the only honest measure of whether the factory is improving.

### F6 — History's verdict: bespoke apparatus is the documented failure mode

[S10]. Every prior software-factory wave (Bemer 1968; Hitachi/Toshiba/NEC in the
1970s–80s; Microsoft's 2004 reorganisation) died of the same cause — the cost of
*maintaining the specialised production apparatus* exceeded the value it produced.
The current wave claims to escape this because the "machines" are general models
and the specialisation lives in prompts and oracles rather than bespoke tooling.

That claim is testable and the burden of proof is on us. It argues for **a small
number of generic, well-instrumented lanes over a large taxonomy of specialised
agents**, and for treating the factory's own size as a budgeted, capped quantity
from day one.

[S05] is the strongest counter-proposal on record: a minimal scaffold that
synthesises its tools *at runtime* rather than shipping a large fixed harness. If
that generalises, it converts hand-built apparatus into generated apparatus —
which is exactly the cost curve the previous waves lost on. The catch is that
generated tooling falls under the same oracle discipline as generated code
[S15]: a generated tool is a new place to satisfy the evaluator instead of the
requirement, and it is authored by the party being evaluated.

### F7 — An explicit model of the system is a second, cheaper oracle class

[S07]. Agents operating on raw text lose the invariant information needed to
verify anything a test suite doesn't exercise. An explicit model (interfaces,
state machines, invariants, schemas) permits structural conformance checks that
run *before* any code executes, and shrinks the search space a low-capability
local model has to reason over.

This matters more locally than in the cloud: reasoning depth is the scarce
resource on a 35B-A3B, so anything that reduces the search space is worth more
than a bigger model. It is also the argument for sofact being self-describing.

### F8 — The missing instrument: mutation score as the operational definition of verifiability

[S01] explicitly notes there is no standard instrument for scoring a task's
verifiability — it is left qualitative. This is a gap sofact can close cheaply,
and closing it converts the entire framework from vibes to arithmetic.

**A test suite's mutation score is its measured ability to detect wrong
behaviour.** Inject a syntactic mutation (flip a comparison, swap a constant,
delete a branch) and check whether the suite fails. A suite killing 85% of
mutants is an oracle you can trust at L4; one killing 30% is an oracle that will
certify reward-hacked patches [S15].

Proposed rule: **admissible autonomy level is a function of measured oracle
quality per module**, with thresholds set empirically rather than asserted. Tools
exist (`mutmut`/`cosmic-ray` for Python). This makes [S11]'s
"outcome machine-observable" a *number* instead of a judgement, and it makes an
honest L3-vs-L4 decision per lane a measurement rather than an argument.

---

### F9 — A goal-mode harness is an autonomous producer that reports its own success

[S18] (primary, `content-verified`), [S08], [S04], [S05]. Added in the 0.3 round,
from reading a working goal-mode harness on this machine rather than from
literature — the ledger had no source on this landscape at all.

`pi-goal` 0.1.7 exposes `/goal <objective>` and keeps the agent running turns until
the *model* calls `update_goal({ status: "complete" })`, a budget runs out, or the
user intervenes. Three consequences, in ascending order of importance.

1. **The delegation unit is a goal, not a task.** SoFact can hand a whole module
   contract to one long-running session rather than driving a step-by-step loop.
   That removes SoFact's need for an inner loop entirely, which is the same
   apparatus-cost discipline as [F6] applied one level deeper.
2. **Goal mode is a portable idiom.** The harness's bundled goal-writing skill
   specifies a six-part contract — outcome, verification surface, constraints,
   boundaries, iteration policy, blocked stop condition — and states the same shape
   applies to other goal modes. That shape is nearly isomorphic to what a module
   contract needs to be, so the contract should be authored *to serialize into a
goal*. A real design constraint, discovered not assumed.
3. **The completion signal is a claim, not a result.** The harness is the producer
   and it is the one that says "done". Its own guidance tells it to audit against
   real evidence first — but that is a *prompt*, not an enforcement, and the tool
   boundary permits an optimistic or wrong declaration. A goal-mode harness
   therefore reports success **in exactly the shape a verification result would
   have**, which makes it the most persuasive possible false positive. SoFact must
   treat the declaration as a *trigger* to run its own oracles, never as the
   verdict.

**[S18] also reports the fix, already implemented.** `update_goal` accepts *only*
`status: "complete"`; pausing, resuming, clearing, and budget-limiting belong to
the user or extension runtime. The producer may **declare victory** but may not
**extend its own budget**, **pause itself**, or **clear the goal**. SoFact should
mirror that asymmetry structurally rather than invent one — and generalise it:
*the producer's own assessment is never the verdict, at any delegation boundary.*

That generalisation is the finding. It appears three times in this design — the
operator judges the specification, measured strength judges the oracle, and SoFact
judges the harness — and each instance needs its own independent check. See
`docs/spec/product-spec.md` §2.4.

**Information quality.** `n = 1`: one harness, one author, v0.1.x, inspected
locally. Not peer-reviewed and not a recommendation. The *shape* of the asymmetry
is the durable part; the specific harness is expendable. *(0.3 addendum: [S20]
gives a second harness, and it corroborates the shape while changing the
recommendation. See [F10].)*

### F10 — Harness architecture, not harness quality, decides what a factory can prove

[S20] (documentation, `reported`), [S18], [S19]. Added after [F9] prompted the
question of *which* harness to fix on. The finding is not "`dsh` is better than
`pi`". It is that the two differ in **kind**, not degree, and along the axis SoFact
cares about most.

SoFact's product is evidence about what happened. A harness can therefore be
judged by whether its evidence is an **artifact** or a **byproduct**:

- `pi` writes a JSONL transcript to a known path [S19]. Readable, uncooperative —
good — but it is a *conversation log*: SoFact must infer what was done from text.
- `dsh` writes an append-only event log whose taxonomy *names the acts* —
`tool/call`, `tool/result`, `turn/start`, `turn/end` — with monotonic `seq`, and
**derives LLM history from the log** rather than storing it separately [S20]. The
log is the source of truth, not a record of one. Replay, fork, and search are all
defined over it.

Four consequences.

1. **Termination-vs-verification ([F9], FR-138) becomes checkable rather than
   merely enforceable.** With typed `tool/call` and `tool/result` events, SoFact can
   compare what the producer *claimed* against what it *did*, from an artifact the
   producer never wrote for SoFact's benefit. That is a stronger position than
   trusting a self-report and re-running oracles.
2. **The seam SoFact was going to build already exists.** [F9] established that
   SoFact owns the outer loop and the harness owns the inner one. `dsh` exposes the
   inner loop, the sandbox, and the scheduler *as plugins* — so the boundary is a
   configuration surface, not an interface SoFact must reverse-engineer. The
   §1.5 non-goal becomes cheaper to honour, not just more important.
3. **"Harness of harnesses" is a native idiom, not a SoFact invention.** `dsh`
   hosts Claude Code and Codex as Profile Bundles with non-interactive permission
   modes. §1.6's architecture is the platform's own design; SoFact is a
   *configuration* of it plus a verification layer.
4. **Maturity and capability are anti-correlated here, and the maturity side is
   the risk.** `dsh` is one month old at rc.8 and warns in all caps of breaking
   changes [S20]; `pi` is stable but thinner. There is no candidate that is both.
   The honest resolution is to pin, isolate the harness behind one adapter, and
   keep the lesser harness working as an escape hatch — see §8.6 and R26.

**The generalisable form.** *A harness's evidence contract, not its benchmark
score, determines what a factory built on it can prove.* Benchmark scores measure
the producer; evidence contracts constrain the verifier. The ledger contains
plenty of the former ([S04] [S05]) and, before [S20], none of the latter.

**Information quality.** [S20] is documentation, not observation, and it was the
only source for every `dsh` claim above. Its own event-taxonomy detail came from a
reference page rather than a live session. Two credibility anomalies were recorded
in [S20] and are not repeated as fact here: an implausible star/fork count and a
mixed-provenance source bundle including a third-party SEO site.

**Update — [S21], executed.** The count was *not* an artifact (the GitHub API
confirms 220,569 stars / 26,126 forks) and four [S20] claims were falsified by
execution. The finding itself survived, and sharpened: a live run produced a
63-record typed log with monotonic `seq`, `request/header` carrying
`{config, tools}` verbatim, and twelve `tool/call`/`tool/result` pairs — evidence as
**artifact**, observed rather than inferred. Three further results bear directly on
this finding:

- The integration surface is a **subprocess on stdio JSON-RPC**, not in-process.
  The `dsh` column of §8.6 is now a measurement, not a reading.
- The default composition **egresses** (`session-telemetry-otel` →
  `harness-telemetry.deepseeksvc.com`), so an "offline" flag is not an evidence
  boundary and not an egress boundary either.
- **Goal mode was never entered.** The producer used `todo_write` and finished in
  one turn. Architecture decided what the harness *could* prove; the model decided
  what it *did* prove. See [F11].

---

### F11 — Capability is not engagement: goal mode is entered by the model, not by the harness

[S21], executed. The strongest negative result in the project so far, and one that
documentation could not have produced.

`dsh` ships **four** first-party goal packages (`goal`, `goal-round-driver`,
`command-goal`, `tool-goal`), loads them in the `sdk` profile, and exposes the
`create_goal` / `get_goal` / `update_goal` tool trio. Every capability check passes.
Then an unattended genesis run — empty repo, local model, no human — produced
**zero goal-typed events**. One turn, seven steps, twelve tool calls (`bash` 5,
`write` 4, `todo_write` 3), and `finish_reason: completed`.

The model used `todo_write`, its in-turn planning tool, as a *substitute*. The goal
tools' own descriptions require "a long-running objective that should continue
across autonomous goal rounds" — a judgement the producer makes about its own work,
and this producer declined. This is [F9] seen from the other side: [F9] says the
producer reports its own success; [F11] says the producer also decides **whether to
be a producer over time at all**.

**Consequence for the specification.** FR-136 (contract → goal plan) cannot assume
goal mode. SoFact must force entry by construction and **verify entry from the
session log** (FR-153), with FR-144's single-shot mode as an explicitly reported
capability loss. "The harness supports goal mode" and "this build ran as a goal"
are different propositions, and only the second one is worth anything.

**Generalisable form.** *For any delegated capability, presence of the mechanism
and exercise of the mechanism are separate facts, and only the second is evidence.*
The same discipline already governs completion declarations (FR-138); it applies to
mode selection too.

**Information quality.** n = 1 model, n = 1 run. This may be a property of
`qwen3.8:27b-mlx` rather than of `dsh`. It must be repeated across models before it
is treated as a harness fact — and either way the *requirement* (force entry, verify
entry) is correct, because it is robust to the answer.

### F12 — Mechanism is not differentiation; the front end is

[S22], measured. The `dsh` plugin ecosystem contains **4,609 distinct GitHub
repositories** in one curated list, and every mechanism this specification treats as
differentiated already exists as free MIT plugin code: evidence-gated completion
(≥5 independent implementations), worktree isolation, budget caps, wave scheduling,
LLM-as-verifier (≥7), meta-harness orchestration across harnesses including `pi`,
egress denial, telemetry redaction.

Term frequency across those 4,609 entries: `gate` 258, `verif*` 155, `bench` 135,
`audit` 110, `spec` 105, `complet` 92, `evidence` 80, `orchestrat` 80, `ledger` 46,
`worktree` 32, `verifier` 27, `goal` 27, `budget` 25, `contract` 18 — and
**`elicit` 0**.

Two consequences, one strategic and one architectural.

1. **SoFact's defensible position is the intent front end plus *measured* oracle
   strength**, not the gates. Gates are a commodity utility library (one plugin kit
   ships "fail-closed approval and adaptive session-event gates" as a shared
   dependency). What nobody has built — or even named — is turning a human goal into
   a falsifiable contract. §19's land-and-expand (D13) is therefore not a marketing
   convenience; it is the only uncontested product surface in the ecosystem.
2. **Compose, don't rebuild — but the composition is the boundary.** [F6]'s
   apparatus-cost discipline extends to third-party plugins: do not rewrite
   `dsh-git-worktree`. But thousands of unreviewed repos reachable from the
   producer's runtime is [F6]/[S10]'s failure mode in a new costume. Hence FR-154:
   a frozen, minimal, pinned, hash-verified composition, never the operator's own
   profile. [S21] already ran this way by accident (an isolated `DSH_HOME`), and two
   ecosystem plugins exist purely to do the same.

**The architectural consequence, which is the sharper one.** The plugin set is
**mutable at runtime, by the agent**: a library for "patching, replacing, and
decorating DSH plugins at runtime", a hot-injector, a tool that promotes an
agent-authored `cordis_define` dynamic package into a permanent bundle, and a
plugin-dev skill that teaches any agent to author plugins to spec. **A verifier that
shares the producer's runtime is reachable by the producer.** That is R22 escalated
from a behavioural risk (the producer *might* game the criteria) to a structural
capability (the producer *can replace the checker*). It settles D16: SoFact is an
independent control plane that drives `dsh` out-of-process, not a plugin.

**Information quality.** Descriptions are self-authored README lines; no plugin was
installed or executed. This measures the *density and shape* of the ecosystem, not
the quality of anything in it. A list created the same day as the thing it
catalogues has had no time to stabilise.

### F13 — The crowded category is the one that must be refused

Follows from [F12] and [F11], and it inverts the intuition [F12] invites. If the
ecosystem already implements SoFact's mechanisms, the natural move is to adopt them.
That move fails for the largest and most tempting category.

The admission test (FR-155) is deletion: *remove the plugin — does SoFact reach the
same verdict?* The categories that fail it — evidence-gated completion (`complet`
92, `evidence` 80), gates (`gate` 258), verification (`verif*` 155), budgets
(`budget` 25) — are exactly the categories with the most implementations. So the
plugins that appear to save the most work occupy the authority SoFact exists to
provide, and are inadmissible *because* they are numerous. Meanwhile the admissible
mechanical plugins are thin wrappers over tools SoFact already drives, where vetting
plus pinning plus licence review costs more than writing the code.

The asymmetry is the finding: **an ecosystem's density measures how cheap a
capability is, not how safe it is to depend on** — and the density concentrates
precisely where dependence is most dangerous.

Three corollaries worth keeping.

1. **Producer-side honesty measures are not verifiers.** A guard constraining the
   producer raises the *rate* of truthful reporting and is welcome on those terms.
   But it is mutable by the party it constrains ([S22] runtime mutation), so relying
   on it would make the harness's honesty a precondition of SoFact's correctness —
   which is the problem SoFact is sold as solving. The strongest support for this is
   negative: five independent, competent attempts at evidence-gated completion all
   landed inside the trust boundary.
2. **Ecosystem descriptions are `reported`-quality evidence.** Zero listed plugins
   were installed or executed. Every claim above rests on self-authored README text —
   the same tier that was falsified four times about `dsh` itself in [S21]. Nothing
   enters a composition (FR-154) on the strength of a description; the deletion test
   is applied to *observed* behaviour, or the plugin is not adopted.
3. **Config beats plugin (FR-156).** Where a capability is obtainable by disabling or
   reconfiguring something, that is mandatory. The measured case is telemetry: the
   correct response to a default vendor export ([S21]) is to remove the exporter, not
   to install a redactor that scrubs it. Guarding a path that should not exist adds a
   moving part to the very claim it is meant to support.

A fourth corollary is strategic: SoFact *composed* as a bundle of these plugins is a
distribution — free, crowded, and in permanent maintenance debt for everything it
bundles ([F6]; compare `oh-my-tianshu`). "Just add the plugins" is the route from
product to distribution, and it is taken one individually-justified plugin at a
time. That is why FR-155 is a written test rather than case-by-case judgement.

### F14 — An ecosystem name is not a referent, and a distribution is a larger commitment than a plugin

[S23], measured. Asked to assume "either `oh-my-pi` or `oh-my-dsh` as the harness,"
the honest reply is that **one of those names does not resolve**. `oh-my-dsh` is at
least eight unrelated repositories spanning four kinds of artifact: a 530-plugin
capability library (`LaplaceYoung`), an explicit "curated distribution, overlay not
a fork" (`amplifthq`), an auto-synced plugin catalog rebuilt every four hours
(`like-study1`), and standalone agents (`agi-fans`, `secretxuan`). "Use oh-my-dsh"
is not executable. It must become *"use `<owner>/oh-my-dsh` at `<sha>`"* — and two of
the eight are catalogs, which are indexes rather than bases.

`oh-my-pi` resolves, but to something category-different than it appears:
`can1357/oh-my-pi` reports GitHub `fork: false` with no parent, so it is a
**detached hard fork** — an independent product at npm 18.1.18 with its own install
channel — but its README's own words are "Fork of Pi," and `pi` is D11's *secondary
adapter*. Adopting it as the base therefore makes the base a fork of one of SoFact's
two adapters, not a harness.

Three durable consequences.

1. **Choosing a base is choosing somebody else's outer loop**, and the measured
   candidate already ships a research phase (P1), a dispatch-and-wave layer with an
   **in-process conflict reviewer** (P4/P7), and a pre-write secret guard. That is
   D17's composition preference applied one level up — genuinely good news for the
   operator's objective, since it removes phases rather than plugins — but two
   orchestrators on one session contend over the same budgets, git state, and event
   stream. §8's outer loop must shrink to the measured residue.
2. **You inherit the composition, so FR-155 stops being a filter and becomes an
   audit.** A distribution arrives pre-populated, and the reviewer it ships fails the
   deletion test. The test still applies; it is just performed against
   `--dump-config` and an inventory of which SoFact verdicts would change if the base
   were removed, rather than against a list of adoption candidates.
3. **Distribution curation and frozen composition are in direct tension.** A
   distribution exists to change (one rebuilds every four hours; the candidates were
   pushed within days of measurement). FR-154 requires a pinned, hash-verified
   snapshot. The efficiency of a distribution is therefore partly spent maintaining
   a snapshot — still cheaper than building the base, but not free, and the cost is
   paid in exactly the currency (F6) the base was adopted to conserve.

The generalisable rule: **in a young ecosystem, names are marketing and artifacts are
facts.** `elicit` = 0 and eight repos share one name for the same reason — the naming
layer is cheap and the verified layer is not.

---

### F15 — A harness cannot answer a training-side objection; it can only refuse to over-claim

[S24], with the objection stated at full strength. Horthy's argument is a *mechanism*
argument — coding models are trained by RLVR against bounded pass/fail rewards, and
that reward shape contains no term for design quality, so no harness can supply what
the training objective never asked for. It is unprovable by his own admission, and
that is exactly why it survives: a mechanism argument does not need the measurement
it says is missing.

SoFact **is** a harness. It therefore cannot refute this. The productive response is
to notice which claim was doing the work, because v0.4 conflated two claims that are
routinely conflated:

- *"this obligation was satisfied"* — checkable per clause, the only thing FR-001
authorises, and legitimately capable of supporting L2–L4;
- *"this can be maintained autonomously"* — not observed by **any** oracle in O1–O8,
and therefore by construction not claimable at all.

v0.4 attached a single per-module ceiling to a module, and a green suite was silently
licensing the second claim via the first. [S24] is what makes that collapse visible.
Hence FR-158, which does not fix anything — it *names the debt* and sets its default
to total. The generalisable rule is F1 turned on the factory's own output rather than
on its inputs: **an unverifiable property does not become verifiable by being adjacent
to a verifiable one.** The residual is [S24]'s own sentence, met from the other side:
the human is still the judge. SoFact automates the bookkeeping of judgment, never the
judgment.

### F16 — Maintainability has no absolute oracle, but it has a differential one, and the difference is not rhetorical

[S24]'s central technical claim is that maintainability cannot be rewarded because it
has no *fast oracle*. That is very nearly right, and the gap is worth exactly one
measurement.

What is absent is an **absolute** scale: no number answers "is this codebase well
designed." What is not absent is a **comparison**. The same change unit — a feature, a
refactor, a bug fix — implemented twice on the same codebase at two moments has a
mechanical diff footprint: files touched, hunks, lines changed, modules crossed. Decay
is a *trend* in that quantity. Fowler's shotgun surgery is precisely the prose
description of that trend, and *detecting a trend requires only that the measurement
be consistent, never that it be correct in absolute terms.* That is what makes this
instrument different in kind from everything [S24] surveys: it is model-free, it needs
no reward signal, it cannot be satisfied by editing a test (the exact property
FrontierCode rewards per [S24] claim 7, and which FR-157 already requires), and it
needs no new model capability — which is decisive, because [S24]'s whole thesis is
that new model capability is the thing that will not arrive.

Two boundaries are stated because over-claiming here would repeat the error being
corrected. First, it is a **proxy**, so NFR-024 applies and it must be declared as
one. Second, it measures *change cost*, not design quality: a codebase can get cheaper
to change for reasons unrelated to structure — better tests, better tooling, growing
familiarity. It is therefore admissible as a **trend alarm** and as a Mode M ceiling
input (FR-159), and never as a verdict. The honest statement of the residual stays
[S24]'s: the human is still the judge. What changes is that the human stops being the
only *observer*.

---

## 2. Four tensions the specification must resolve

| # | Tension | Sources | Candidate resolution |
| --- | --- | --- | --- |
| **T1** | Evaluator isolation vs. one box, one filesystem, shared weights | [S02][S15] vs. [S12] | Construct isolation: read-only oracle corpus by permission, oracle canary self-test, two independent oracle *classes*, separate contexts/weights (memory budget exists for this) |
| **T2** | Verification cost vs. throughput — the adversary loop triples token spend | [S15] vs. [S12] | Adaptive: full hacker/fixer loop only on lanes above the autonomy threshold; sampled (1-in-N) adversarial audit below it, with sample rate raised when a leak is found |
| **T3** | Autonomy vs. accountability for *someone else's* production | [S14][S17] vs. [S16] | Contractual gating, not model confidence: anything touching another party's production, money, auth, or PII is human-gated irrespective of oracle quality |
| **T4** | Historical warning about apparatus cost vs. ambition | [S10] vs. all | Explicit maintenance lane; the factory's own LOC/complexity is a capped, tracked budget; the process loop [S06] reports it |

T1 and T2 are engineering problems with real answers. T3 is a governance problem —
and it is the one most likely to be resolved wishfully.

---

## 3. Capability assessment: what is actually defensible on this hardware

Honest read of a 2026 frontier ceiling of ~78% on a curated, test-verified,
Python-only, single-shot benchmark [S04] — a benchmark that *over-represents
verifiable work* and is therefore a flattering upper bound for real lanes.

| Lane | Oracle | Admissible | Notes |
| --- | --- | --- | --- |
| Mechanical transforms (dep bumps, codemods, lint/type debt) | build + existing tests + diff-size bound | **L4** | Highest confidence. Reversible, bounded, cheap to verify. Start here. |
| Test generation for existing behaviour | mutation score must *rise*; existing tests must still pass | **L4** | Self-verifying: the output is measured by the instrument it improves. Elegant. |
| Doc/comment sync with code | doc-build + link check + drift check against code | **L4** | Low blast radius. |
| Triage/classification (issue → lane routing, severity) | human-reviewed sample + confusion matrix | **L3** | Cheap, high volume, MoE territory. Errors are recoverable by construction. |
| Bugfix in a module with high mutation score | full suite + mutation canary | **L3** | The honest version of SWE-bench. |
| Feature within a frozen interface | interface conformance + tests + review | **L2–L3** | Intent must be machine-derivable to be admitted. |
| Refactor under explicit invariant model | structural checks [S07] + tests | **L2–L3** | The [S07] payoff. |
| Architecture / ambiguous requirements | none | **L1** | Human owns. Do not build an agent for this. |
| Novel algorithms, perf tuning under unknown constraints | partial | **L1** | Oracle is expensive and adversarial. |
| Auth, payments, PII, migrations, production deploy | none that bound blast radius | **L1 + contract** | T3. |

**Net position.** A single-operator local factory is realistically **L3 in a few
well-instrumented lanes and L2 elsewhere**, with L4 confined to lanes whose oracle
is strong and whose blast radius is provably bounded. The dark-factory framing
[S02][S03] is aspiration; L5 is not on the table at this scale, and a spec that
implies otherwise is a spec that will fail its own acceptance criteria.

### The real bottleneck is human review, not the GPU

If a unit of work costs 20 minutes of wall clock and 10 minutes of human review,
the factory's ceiling is ~4 reviewable units per hour of human attention — and
that ceiling does not move when the model gets faster. **Human review bandwidth is
the binding resource.** Design objective: maximise *verified units per human-minute*.
That argues for small diffs, high oracle coverage, machine-checkable acceptance
criteria [S03], and ruthless exclusion of lanes that produce large hard-to-review
artifacts — which happens to be exactly what [S01] recommends from the other
direction.

---

## 4. Hard environment constraints (measured, not researched)

These were not in the research plan and they materially shape the spec.

| Constraint | Measured | Consequence |
| --- | --- | --- |
| **Disk is 99% full** | 42 GiB free of 3.6 Ti | **Blocks plan A.** QLoRA on a 27B needs tens of GB for weights + optimizer state + checkpoints. Fine-tuning is viable only at the 4B–9B scale. Also caps how many local model weights can coexist. |
| **No Docker** | `docker` absent | Firecracker/gVisor are unavailable (Linux-only). Sandboxing must use macOS-native mechanisms. |
| **Single machine** | M2 Max, 96 GiB, ~400 GB/s | Throughput ceiling is fixed and shared between producer and evaluator. Co-residency is affordable; parallelism is not free — concurrent agents contend for the same bandwidth. |
| Toolchain present | `ollama`, `llama-server`, `uv 0.9.22`, `python3.13`, `git`, `gh`, `pnpm`, `jq` | Enough to build. `ollama` already hosts a MoE 35B `qwen3.6:35b-mlx` and a `deepseek-v4-flash` cloud alias. |

### Fine-tuning implications

The original plan named Unsloth fine-tuning. Given 42 GiB free:

- **Fine-tune small, narrow, high-volume models only** — routing/classification,
  extraction, schema coercion. These are exactly the [F3] high-throughput lanes.
- **Do not plan to fine-tune a coding model.** Both the disk budget and the
  M2's lack of CUDA make this the wrong lever.
- LoRA on a 4B model is the honest ceiling here, and it targets the lanes where
  per-token latency matters most. That is a *good* fit, not a consolation prize.

### Blast-radius bounding without containers

[S11]'s third qualifier is the hardest to honour on this box, since the usual
answer is a container. Available mechanisms, strongest first:

1. **Git is the primary blast-radius bound.** Every mutation is a commit on a
   branch; nothing is ever edited in place; the undo mechanism is `git reset`.
   Cheap, auditable, and already required for other reasons.
2. **Filesystem permissions** — the oracle corpus read-only to the agent's user;
   preferably a separate non-admin macOS user for agent processes.
3. **`sandbox-exec` / seatbelt profiles** — deprecated but functional; the only
   real syscall-level jail available natively.
4. **Apple Virtualization.framework** (via `lima`/`vz`) for a Linux VM if real
   containerisation becomes necessary. Availability not yet checked.
5. **Network egress denial by default**, allowlisted per lane. Prevents both
   exfiltration and the agent reaching the internet to satisfy a test.

---

## 5. Business opportunity assessment

[S14] settles the rail, not the product. x402 makes sub-cent
machine-to-machine payment a protocol primitive with no account creation, which is
genuinely the right shape for a factory selling to *agents* rather than humans.
But payment rails are commoditised; the open question is what is worth paying for.

Honest ranking, by fit with this factory's structural advantages (data locality,
zero marginal token cost, unattended operation on owned hardware):

1. **Sovereign / air-gapped codebase maintenance.** Regulated or
   confidentiality-bound organisations cannot send source to a hosted vendor.
   Hosted competitors *structurally cannot* serve them. Here local models are not
   a handicap — they are the product. Strongest fit.
2. **Maintenance-as-a-service on customer hardware.** Recurring dependency and
   security upgrades with tests, run on the customer's own box, invoiced monthly.
   Zero marginal token cost makes this a margin business rather than a
   per-token arbitrage.
3. **Sell the line, not the output** — self-hosted factory software. Competes
   directly with [S17] on sovereignty and price rather than on model quality.
4. **Per-artifact verified output** (x402-metered endpoints). Attractive, but the
   buyer must trust the verification, which requires a reputation the operator
   does not have yet. Needs (1) or (2) to bootstrap credibility.

**Assessment of the original request.** The research supports autonomous
*production under verification*. It does not support autonomous *commercial
judgement* — pricing, positioning, contract terms, and counterparty risk are not
verifiable by any oracle we can build, and [S16] puts them at L1 by definition.
Recommended split: **monetization is human-decided and machine-executed.** An
autonomous agent handling another party's money is T3 territory, and T3 is a
governance problem that oracle quality cannot solve.

Also note: options (1)–(3) all place sofact inside *someone else's* production
blast radius, which raises the required autonomy assurance above what is
defensible at L2–L3. That has to be handled by contract and staging (shadow mode,
advisory mode, then gated mode), not by model confidence.

---

## 6. Measurement plan — do this before specifying

The spec should rest on local measurements, not on remembered numbers. In
priority order:

1. **Decode throughput table.** Four candidate models (MoE 35B, dense 27B, 9B,
   4B) × three context lengths (2k / 8k / 32k) → tok/s and prefill time. This
   decides the routing table. `ollama` and `llama-server` are both present;
   `llama-bench` gives the cleanest numbers.
2. **Mutation score of the first target repo's suite.** Establishes the [F8]
   instrument and calibrates thresholds. Without this, autonomy levels are
   assertions.
3. **Human review time per diff.** Self-log for a week: minutes of review per
   accepted change. This is the actual factory ceiling, and it is unknown until
   measured.
4. **Cost/throughput crossover** for local vs. any hosted option, per lane. The
   number that decides whether the local bet pays, currently argued from
   principle [S13].
5. **Sandbox viability.** Confirm `sandbox-exec` and/or `lima` actually work
   here; write the egress-denial rule; verify git-as-undo.

---

## 7. Open questions for the dialogue

Ordered by how much downstream design they determine. Each is a genuine fork, not
a rhetorical question.

1. **What is the first codebase sofact operates on?** Every lane table, oracle
   threshold, and throughput decision depends on the target. An empty greenfield
   repo has *no* oracle and therefore admits almost no autonomy — the strongest
   possible argument for starting on a real, tested, existing repo (or on sofact
   itself, once it has tests).

   **Status (0.3): partially resolved, and split in two.** SoFact has two modes,
   and this question decomposes. *Mode M* still needs one real tested repo as the
   θ calibration source. *Mode G* starts from a goal, and the answer to "no oracle"
   is **oracle manufacturing** — oracles are constructed from the contract before
   the code exists (spec §9.2). The uncomfortable corollary stands: manufactured
   oracles are weaker than inherited ones, so Mode G assurance is *lower* than
   Mode M assurance, not equal to it. See spec §2.3.
2. **Is the goal a product or a personal capability?** "Monetize" implies
   customers, which drags in T3, contracts, and staging modes. A personal
   capability is a much smaller, much more defensible spec. Which one is this?
3. **What is the human's actual review budget?** Hours per week, and willingness
   to review. This sets the factory's throughput target, and every other number
   follows from it.
4. **Where is the oracle corpus allowed to live, and who can write to it?** The
   [F2] isolation answer. Answering this commits the process architecture.
5. **Is autonomy bought with verification, or with reversibility?** Git-as-undo
   [§4] is strong enough that one could argue for *high* autonomy at *low* oracle
   quality, provided every change is one revert away and blast radius is provably
   local. This is the most interesting design bet in the whole space and it
   conflicts directly with [S02]'s isolation-first position. Worth arguing.
6. **Does the factory get to touch its own source?** Self-modification is the
   most compelling version of the original request and the one with an unbounded
   blast radius. If yes, it needs its own lane with its own oracle — and the
   oracle cannot be produced by the thing being modified.
7. **Fine-tuning: which specific lane is worth a LoRA?** Given the disk ceiling,
   at most one or two. Candidates: lane routing (high volume, low depth) or
   test-mutation generation. Which bottleneck hurts more?
8. **What does "operate" mean concretely?** Monitoring an existing service,
   responding to incidents, or just keeping the factory's own pipeline running?
   These are three different products with three different risk profiles.

---

## Source references

[S01]: ../sources/s01-assistance-to-autonomy.md
[S02]: ../sources/s02-dark-factory-soeters.md
[S03]: ../sources/s03-strongdm-software-factory.md
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
[S18]: ../sources/s18-goal-mode-harness-interface.md
[S19]: ../sources/s19-harness-cli-surface.md
[S20]: ../sources/s20-deepseek-harness.md
[S21]: ../sources/s21-dsh-probe-executed.md
[S22]: ../sources/s22-dsh-plugin-ecosystem.md
[S23]: ../sources/s23-harness-base-candidates.md
[S24]: ../sources/s24-harness-engineering-is-not-enough.md
