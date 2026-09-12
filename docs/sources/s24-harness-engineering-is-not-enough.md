---
id: S24
slug: s24-harness-engineering-is-not-enough
title: "Harness Engineering is not Enough: Why Software Factories Fail"
author: Dex Horthy (HumanLayer)
type: essay
url: https://ai.engineer/talks/harness-engineering-is-not-enough-why-software-factories-fail
alt_urls:
  - https://www.linkedin.com/pulse/why-software-factories-fail-dexter-horthy-ttxae
  - https://www.youtube.com/watch?v=Ib5GBkD555M
  - https://news.ycombinator.com/ (discussion: 341 points, 242 comments, 2026-07)
arxiv: null
retrieved: 2026-09-12
verification: content-verified
confidence: medium-high — directionally strong, evidentially weak, self-admittedly so
tags:
  - maintainability
  - oracle-absence
  - reward-signal
  - rlvr
  - code-review
  - frontier-code
  - slopcodebench
  - counter-argument
supports:
  - FR-158
  - FR-159
  - FR-160
  - R30
  - D18
  - F15
  - F16
---

## Precis

The strongest published counter-argument to the premise a software factory rests on,
delivered as a keynote at AI Engineer World's Fair 2026 (19:18) and expanded into a
long-form post (2026-07-25).

Horthy's claim is narrow and therefore hard to dismiss: **no amount of harness
engineering can repair a missing reward signal.** Coding models are trained by RLVR
against bounded pass/fail rewards (SWE-bench task shape), and that reward structure
has no term for design quality. So models optimise what *can* be scored — passing
tests — and a harness can only make a model better at what it was already trained to
do. "Loopsmaxxing" cannot substitute for a training objective that does not exist.

The mechanism he gives for why this is not merely underinvestment is **credit
assignment**: a test gives a verdict in seconds; the cost of bad architecture
arrives in weeks or months, when someone opens a file for a one-line change and
discovers eleven places must move. A reward cannot be propagated back across that
gap. He states plainly that he **cannot prove** the resulting claim that "models
degrade codebase quality over time," because "there are no good benchmarks" for it.

His prescription is not to abandon agents but to move human judgment *earlier*:
four phases before implementation — **Product Review → System Architecture →
Program Design → Vertical Slices** — with the operating claim that ~30 minutes of
front-loaded alignment removes hours of review. His conclusion: "for now we're stuck
reading the code," and the judge remains the human.

## Key claims

1. **A harness cannot fix a training deficiency.** "No amount of harness engineering
   or loopsmaxxing can solve what is fundamentally a model-training issue."
2. **There is no penalty for eroding maintainability.** The SWE-bench reward is
   `FAIL_TO_PASS ∧ PASS_TO_PASS`; nothing in it scores program design. Consequently
   models produce expedient artifacts the reward cannot see — gratuitous
   `try/catch`, casts through `any`, tests commented out.
3. **Maintainability has no fast oracle, so it cannot be rewarded.** RL requires a
   fast, reliable oracle; maintainability's cost function is measured in
   weeks-to-years. If a model could reliably tell good code from bad, it would
   probably have written the good version to begin with.
4. **RL-inside-the-harness is a permanent structural advantage.** Citing OpenAI's
   Codex team: a harness builder that does not own the weights and cannot RL inside
   its own loop is *always* at a disadvantage to one that owns both. This is
   attributed as the explanation for Claude Code's dominance over Aider/Codebuff,
   which had identical tools.
5. **The lights-off factory fails in practice.** HumanLayer ran full lights-off from
   July 2025 and abandoned it after ~3 months; the agent could not resolve one
   incident class, and the team had to re-read a codebase it had stopped reading.
   Agent-built codebases drift toward brownfield in **3–6 months**, not 10 years.
6. **Review, not implementation, is the binding constraint.** Once implementation is
   agent-driven (minutes-hours), review and testing still cost hours-days, so review
   becomes the bottleneck. "You don't have too many PRs, you have too many bad PRs."
7. **FrontierCode's test-quality check is the interesting move**: it penalises a
   model for writing tests that *do not fail on the pre-patch code* — i.e. it scores
   the oracle, not just the patch. (This is mutation testing, arriving from a
   different direction.)
8. **SlopCodeBench** (Gabe Orlanski's lab, UW) is named as the only benchmark known
   to him that measures a model's ability to *maintain a codebase over time*; he
   reports a 17% strict pass rate for Opus 4.6 and calls it deeply unsaturated.

## Reported figures (carry the talk's own caveat, not ours)

Faros AI, "analysis of 22,000 developers across 4,000 teams," high-AI-adoption
cohort vs baseline:

| Measure | Reported change |
| --- | --- |
| PRs skipping review entirely | +31.3% |
| Review comments per PR | +25% |
| Review comment length | +22.7% |
| Monthly incidents | +57.9% |
| Incidents per PR | +242.7% |
| Bugs per developer | +54% |
| Bugs per PR | +28.7% |

## Concerns / information quality

**The author declares the central claim unprovable.** He says so twice, in the talk
and in the post, and explicitly identifies the missing benchmark. That honesty is
why this entry carries weight despite the weakness of its evidence: the argument is
a *mechanism* argument (reward shape → optimised behaviour), and mechanism arguments
survive absent measurement better than correlation arguments do.

**The Faros numbers are a correlation signal and the source says so.** "More of a
correlation signal than a verifiable smoking gun… the whole point of this post is to
be wary of slop data." No cohort definition, no effect size, no confounds. They
should be read as *consistent with* the thesis, never as establishing it. Two
additional confounds are obvious: high-adoption teams are disproportionately teams
shipping fast for other reasons, and "incidents per PR" is a ratio whose denominator
moves when agentic tooling inflates PR count — a rise is *expected* from the
treatment alone and is not evidence of worse engineering.

**The 3–6 month brownfield threshold is one team's experience**, generalised with an
explicit "you can ask me how I know this." N=1.

**The RL-inside-the-harness claim is second-hand** (OpenAI, "a talk in November"),
and the Claude Code attribution is offered as "the canonically-accepted
explanation" — i.e. folklore with a plausible mechanism, not a measured comparison.
It is nonetheless the most consequential claim in the talk, because it is structural:
if true, it bounds every third-party harness permanently, including SoFact's.

**Survivorship and incentive.** The closing section is a product pitch for
HumanLayer, whose stated roadmap is "better verifiers for software maintainability."
The thesis and the product point the same way. This does not make the thesis false;
it makes the *emphasis* suspect. His own recommendation — move judgment earlier —
is also the shape of the product he sells.

**What the talk gets right that is not in dispute:** the SWE-bench reward shape and
its absence of a design term are matters of record, not interpretation. The
`FAIL_TO_PASS`/`PASS_TO_PASS` construction and the practice of discarding the
agent's test edits are visible in the benchmark's own definition.

**Unverified lead:** SlopCodeBench is cited but not yet fetched by this project. It
is the one source here that could convert claim 3 from "there is no oracle" into
"there is a partial oracle," so it is queued for a dedicated entry rather than cited
as established.

## Why it matters for SoFact

This is the sharpest available objection, and it is aimed at SoFact's core premise.
SoFact **is** a harness. If the objection holds, SoFact's ceiling is set by a model
capability that is unmeasured — which means the correct product response is not to
attempt a fix but to **bound its own claims.**

Four distinct consequences, in descending order of severity:

1. **A training-side objection cannot be answered by an architecture.** SoFact must
   not claim to solve maintainability. It can only refuse to convert a green suite
   into a claim the suite cannot support. This is [S24]'s own conclusion ("the judge
   is you") met from the opposite side: SoFact automates the *bookkeeping* of
   judgment, never the judgment. → **FR-158**, R30.
2. **"No fast oracle exists" is very slightly too strong, and the difference is
   load-bearing.** The talk is right that maintainability has no *absolute* oracle.
   But decay is a **trend**, and a trend needs no absolute scale — only a
   consistently-measured quantity. Change amplification (mechanical diff footprint
   per comparable change unit) is model-free, cheap, and cannot be satisfied by
   editing a test. That converts "the human is the only judge" into "a machine can
   tell you it is getting worse." → **FR-159**, **F16**, D18.
3. **The binding constraint is review cost, so the factory must measure it.**
   SoFact's §1.3 envelope is expressed in human-minutes; nothing in v0.4 requires
   that actual human-minutes be *recorded*. A factory that measures only
   implementation throughput measures its cheapest step. → **FR-160**.
4. **Delegating to a harness whose weights SoFact does not own is a permanent
   structural disadvantage** (claim 4), accepted deliberately rather than
   overlooked. SoFact must therefore never require a capability that depends on
   RL-in-harness — which is exactly what FR-148's capability probing will surface
   operationally. → **ADR-0010**.

## Independent convergence (the deletion test applied)

Per **FR-155**, a third-party idea is adopted only if SoFact would reach the same
verdict without it. On the *mechanical* content, SoFact already had, from its own
line of reasoning, everything the talk prescribes — which is the interesting result:
a talk arguing that factories cannot be designed around a harness arrived at a
process shape this spec reached from oracle accounting.

| [S24] prescription | SoFact, pre-existing | Independent? |
| --- | --- | --- |
| Tests are a bounded oracle; no design term in the reward | FR-001, **ADR-0009**, ground-truth debt (§9.3) | Yes |
| The producer reports its own success, so it is not evidence | FR-138 (`verify()` takes no claim, enforced *by signature*), **ADR-0006** | Yes |
| The producer must not own its completion criteria | FR-139 (contract/oracle/goal-text hashes), FR-140 | Yes |
| Score the oracle, not just the patch (FrontierCode) | FR-157 mutation score, θ_hi = 0.80 → L4 | **Yes — direct convergence from a citation inside the talk** |
| Lights-off does not work | L5 not offered; L4 max per deployment; FR-123 caps Mode G at L2 end-to-end | Yes |
| A model judging quality is circular | **ADR-0008** — the model is advisory only and never renders a verdict | Yes |
| Product Review → Architecture → Program Design → Vertical Slices | P0 Elicit → P2 Specify → P3 Decompose → P4 Contract; §8.4 tiers; `GoalStep.depends_on` **is** vertical slicing | Yes |
| The human stays the judge | Human gates; FR-140 ("gates are the human's") | Yes |

**Net:** the talk adds no mechanism SoFact lacks. It adds three things SoFact was
missing — an admitted debt it had not named, a gate-cost measurement, and a warning
that its own output becomes brownfield in months rather than years — plus one
instrument (FR-159) that closes its strongest claim.
