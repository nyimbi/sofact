# 0007 — The elicitation gate is deterministic

- **Status:** Accepted
- **Date:** 2026-09-12
- **Amended by:** [ADR-0077](0077-the-interrogation-asks-eight-dimensions-and-scale-is-one-of-them.md) — the dimension list is **eight**, not six: the spec's *Scale* and *Non-negotiables* rows were absent, and *Non-negotiables* had been folded into the constraints question. The gate is unchanged and remains deterministic; what changed is what it asks and that `SCALE` carries a second content floor. The rest of this record stands.

## Context

SoFact's first phase is Socratic interrogation: it asks a goal a small set of
questions until the goal is falsifiable. A local model is available throughout, and
the obvious design is to let it decide when an answer is good enough — it can read
nuance that a length check cannot.

The problem is that this makes the gate unmeasurable and unappealable. If a model
decides when interrogation is over, then:

- the gate's verdict is not reproducible, so re-running the same goal can pass and
  then fail;
- a model that is unusually agreeable advances a vague goal to a contract, which is
  where vagueness becomes expensive;
- the "spec acceptance rate" metric becomes a measure of model mood.

A census of the harness plugin ecosystem is the external version of this problem:
`gate` appears 258 times and `verif*` 155 times, but **`elicit` appears zero times**
[S22]. If SoFact's first phase is where it differs, that phase had better produce a
verdict that can be held to account.

## Decision

The readiness gate is a **pure function of the recorded answers**, in
`elicitation.py`, with no model involvement. `assess(goal_id, answers) -> Readiness`
and `next_open(...)` are deterministic; the same answers always yield the same gate.

Each of the eight dimensions carries its own floor, expressed as a predicate over the
answer text — a `min_chars` bound, smallest where an honest answer is naturally terse:

| Dimension | Floor |
| ----------- | ------- |
| `OUTCOME` | 20 chars |
| `CONSUMER` | 15 chars |
| `BOUNDARY` | 10 chars |
| `ORACLE` | 40 chars **+** a required marker |
| `SCALE` | 15 chars **+** a required quantity |
| `CONSTRAINT` | 10 chars |
| `NON_NEGOTIABLES` | 15 chars |
| `FAILURE` | 15 chars |

**Two dimensions carry a content floor, not only a length** (ADR-0077). The `ORACLE`
floor is the one that carries weight: ≥ 40 characters **and** at least one
of 27 markers naming a real checking mechanism — `test`, `property`, `query`, `digest`,
`exit code`, `schema`, `http`, `latency`, and so on. Failing it says so in as many
words: "does not name a checking mechanism … a statement of confidence is not an
oracle".

The `SCALE` floor is the second: ≥ 15 characters **and** a numeral or a magnitude word,
because FR-064's own word is *adversarial* and "a lot of users" clears any length while
naming nothing (ADR-0077). It is a separate field from the marker list on purpose — a marker
list means "name a checking mechanism", which is `ORACLE`'s question and no other's.

Two further properties keep the gate honest:

- **Non-answers are refused by exact match** (`none`, `later`, `skip`, …) rather than by
  substring, so a real answer that happens to contain the word "none" is not discarded.
- **Re-answering supersedes — in `assess`, not in the fold.** The log keeps every
  attempt (append-only, ADR-0003); the gate collapses them last-write-wins per
  dimension. An operator can therefore correct a thin reply, and the correction is
  itself recorded rather than quietly replacing the history.

Failing answers produce reasons naming the specific floor that was missed, never a bare
rejection.

The model may **advise** on an answer (ADR-0008). It may not resolve a dimension.

## Evidence

- `tests/ci/conftest.py::GOOD_ANSWERS` clears every floor on the first attempt for all
  eight dimensions, and `answer_everything` walks the interrogation to completion. Both
  are exercised end to end by `tests/ci/test_pipeline.py`.
- The `ORACLE` floor exists because of a specific failure: "I'll know it when I see
  it" is a description of confidence, not a checking mechanism, and a contract cannot
  be built on one. The dimension's own rationale text says so.
- Debugging `answer_everything` showed the gate behaves as specified: after the last
  answer `open_question` returns `None` on the *next* call, i.e. readiness is
  re-derived rather than tracked, and the helper had to check once more after the
  loop.

## Consequences

- The gate can be replayed, tested, argued with, and measured. A refusal always names
  its reason, so an operator can dispute a specific floor rather than a verdict.
- The floors are crude proxies for quality — a 40-character answer containing the
  word "test" is not necessarily an oracle. This is accepted: a crude gate that is
  reproducible and appealable is worth more than a subtle one that is neither, and
  the model's advice runs alongside for nuance.
- Because the gate is deterministic, the specification's acceptance metrics are about
  the *operator's* answers, not about a model. Under D17 (commercialisation declined)
  this matters more, not less: with no market as an oracle, a reproducible gate is one
  of the few things that can be checked at all.
- Interrogation terminates in a bounded number of turns, which is what makes the
  delivery envelope's human-minutes figure a budget rather than a hope.
