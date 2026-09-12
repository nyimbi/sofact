---
id: S04
slug: swe-bench-verified
title: "SWE-bench Verified (leaderboard / benchmark)"
publisher: OpenAI / Princeton NLP (SWE-bench); Verified subset curated with OpenAI
type: benchmark
url: https://www.swebench.com/
retrieved: 2026-09-12
verification: reported
confidence: medium-high
tags: [benchmark, capability-ceiling, frontier-models]
---

## Precis

SWE-bench is the canonical repository-level issue-resolution benchmark: given a
real GitHub issue (drawn from 12 popular Python repos), produce a patch that makes
the project's own tests pass. The *Verified* subset (500 human-validated instances)
is the number everyone quotes. Reported frontier state at retrieval: **~78.4%**.

## Key claims

- Frontier solve rates on a curated, test-verified subset sit in the high 70s.
- The *oracle is the repo's own test suite* — the benchmark is only well-defined
  because verification is mechanical. This is S01's thesis made concrete.
- Remaining failures cluster on multi-file reasoning, under-specified issues, and
  tests that the issue does not exercise.

## Why it matters for sofact

Sets the realistic ceiling for the factory's hardest lane. Also the right template
for sofact's own internal benchmark: harvest real issues, hold out the tests, and
score patch-acceptance by running them.

## Concerns / information quality

- Python-only, issue-shaped, single-shot. It systematically over-represents tasks
  that are already verifiable, which is exactly why it flatters agentic systems.
- Leaderboard numbers drift and vary by scaffold; the scaffold is part of the
  system under test and is often unreported. "78.4%" is a scaffold+model number,
  not a model number.
- Percentage reported in-session; not re-confirmed against the live leaderboard.
