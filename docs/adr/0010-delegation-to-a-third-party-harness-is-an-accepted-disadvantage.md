# 10. Delegating to a harness whose weights we do not own is an accepted structural disadvantage

* Status: Accepted
* Date: 2026-09-12
* Deciders: operator
* Supersedes: none
* Related: [ADR-0004](0004-delegate-the-coding-loop-to-an-external-harness.md), [ADR-0008](0008-the-model-is-advisory-only.md), [ADR-0009](0009-no-oracle-no-autonomy.md)
* Source: [S24](../sources/s24-harness-engineering-is-not-enough.md)

## Context

[ADR-0004](0004-delegate-the-coding-loop-to-an-external-harness.md) decided that the
coding loop belongs to someone else's harness behind FR-058's adapter. That decision
was made on cost and on blast radius. [S24] supplies a second, less comfortable
reason it will hold, and one that cannot be engineered away.

Horthy reports the argument, attributing it to OpenAI's Codex team: a harness builder
that does not own the model weights and cannot run reinforcement learning inside its
own loop is *permanently* at a disadvantage against a builder that owns both. The
supporting anecdote is that Aider and Codebuff shipped the same tool set — read,
write, edit, grep, bash — and were nonetheless overtaken, the accepted explanation
being that Claude Code was the first agent whose model lab trained against the exact
harness it later distributed.

Two things must be said about the quality of this evidence, because the decision
rests on it. First, it is **second-hand** — a talk cited at a remove — and the Claude
Code attribution is offered in [S24] as "the canonically-accepted explanation," which
is folklore with a plausible mechanism rather than a measured comparison. Second, the
mechanism is nonetheless *structural rather than empirical*: if tool-calling competence
is partly a property of the weights, then no amount of adapter engineering by a third
party reproduces it. A structural claim of that shape does not need the anecdote to be
well-evidenced; it needs only to be possible, because the cost of assuming it wrongly
is asymmetric.

SoFact is, by construction, on the disadvantaged side of that line. It will never own
`dsh`'s or `pi`'s weights, and both D11 candidates are equally third-party. The
disadvantage is real, permanent, and unaffected by any decision this project can make.

## Decision

We accept the disadvantage, and we constrain the product so that it does not sit on
top of it.

1. **SoFact does not compete on inner-loop competence.** Its claim is *what the inner
   loop is allowed to conclude*, never how well the loop calls its tools. Every
   load-bearing mechanism — FR-138's signature-level separation, FR-139's hashes,
   FR-140's authority split, [ADR-0008](0008-the-model-is-advisory-only.md)'s advisory
   model — is on the verification side of the boundary, which is the side where the
   advantage is architectural rather than weight-borne.
2. **No requirement may depend on a capability that only a weights-owning harness has.**
   If the capability cannot be obtained from FR-058's adapter interface against a
   third-party harness, it is not a requirement — it is a wanted feature that the
   product cannot honestly promise.
3. **A missing capability is reported as a gap, never closed by building a harness.**
   This is D15 already, restated here because the pressure to violate it will come
   specifically from this disadvantage: when a third-party harness cannot do something
   a lab-native one can, the correct output is a documented capability gap (FR-148,
   FR-135), not a new harness written in-house and not a fork.
4. **FR-148's probe is where the disadvantage becomes observable.** Capability
   discovery must *attempt* operations rather than read help text, which means the
   adapter will produce direct evidence of what a third-party harness cannot do. That
   evidence is the intended product of the probe, not a failure of it.
5. **We do not tune the interface to exploit harness-specific idioms.** A goal rendered
   to flatter one harness's tool-calling quirks makes the interface untestable against
   the second adapter, which is the only instrument (FR-058) that keeps the interface
   honest.

## Consequences

* SoFact's value must be attributable to architecture. If a benchmark ever shows SoFact
  and a lab-native harness performing identically on verification outcomes while the
  lab-native one wins on inner-loop tasks, that is the *expected* result and not a
  defect to repair.
* Cross-harness capability comparisons will systematically favour lab-native harnesses
  on inner-loop work. Reports must state this as a known bias rather than presenting a
  gap as a defect of the third-party harness.
* D11's choice of `dsh` over `pi` is unaffected — both are third-party, so this
  disadvantage is orthogonal to that decision and cannot be used to argue for either.
* The honest summary of SoFact's ceiling: it can make an existing model's work
  *auditable and refusable*; it cannot make that model better at writing code. [S24]'s
  thesis is that the second thing is where the difficulty lives, and this record
  concedes that rather than arguing with it.

## Evidence

`grep -rnE "openai|anthropic|deepseek" src/sofact/` — no product mechanism depends on
model- or harness-vendor-specific behaviour; the only configuration points are
`SOFACT_BASE_URL`, `SOFACT_MODEL`, and `SOFACT_LLM_TIMEOUT`
([ADR-0002](0002-model-access-is-one-openai-compatible-interface.md)).

The claim that the coding loop is not in this repository is verifiable: the only
subprocess call in `src/sofact/` is `asyncio.create_subprocess_shell` at
`execution.py:74`, which runs oracles, and the only file write is
`handle.write(json.dumps(entry...))` at `ledger.py:146`, which appends SoFact's own
event log.

That the disadvantage is not yet *operationally* visible is also verifiable, and is
the honest state of the probe: `grep -rnE "HarnessAdapter|dispatch\(" src/` returns
nothing, because FR-058's adapter is specified and not yet wired. This record was
therefore taken on evidence read rather than measured, and FR-148's probe is the
instrument that will replace it.
