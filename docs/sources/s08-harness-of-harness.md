---
id: S08
slug: harness-of-harness
title: "Harness of Harness: multi-day autonomous agent operation"
type: paper
venue: arXiv (preprint)
arxiv: "2609.01481"
url: https://arxiv.org/abs/2609.01481
retrieved: 2026-09-12
verification: reported
confidence: medium
tags: [long-horizon, autonomy, harness, context-management]
---

## Precis

Studies what breaks when an agent is left running for days rather than minutes,
and proposes a harness structure that survives it. Reported **+52.25%** over the
baseline on their long-horizon measure. The failure modes are the interesting
part: context exhaustion, drift from the original objective, silent degradation of
the agent's own tooling, and unrecoverable state after a crash mid-task.

## Key claims

- Long-horizon autonomy is limited by *state durability* and *objective
  retention*, not by per-step reasoning quality.
- A layered harness (checkpointing, objective re-injection, health checks on the
  agent's own tools) is the mechanism, not a better model.

## Why it matters for sofact

sofact's stated goal is unattended multi-day operation. This is the most directly
applicable source for that requirement: the design must be resumable and
objective-anchored. Concretely — durable task state on disk (not in context),
explicit objective re-injection each cycle, and self-tests on the factory's own
tooling so silent breakage is detected.

## Concerns / information quality

- A single +52.25% figure with an unspecified baseline is weak evidence; the
  qualitative failure-mode taxonomy is more trustworthy than the number.
- Preprint; URL unresolved in-session.
