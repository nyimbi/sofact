---
id: S01
slug: assistance-to-autonomy
title: "Assistance to Autonomy: A Systematic Literature Review of Agentic Software Engineering Adoption"
type: paper
venue: arXiv (preprint)
arxiv: "2605.15245"
url: https://arxiv.org/abs/2605.15245
retrieved: 2026-09-12
verification: reported
confidence: medium
tags: [software-factory, verification, adoption, slr, planner-executor-reviewer]
---

## Precis

A systematic literature review of why agentic coding assistants do or do not move
from "assistance" (human drives, agent suggests) to "autonomy" (agent drives,
human gates). The central finding is that **output verifiability — not model
capability — is the primary enabler of agentic adoption**. Teams delegate work
whose correctness they can check mechanically (tests, type errors, linters,
reproducible builds, schema conformance), and withhold work they can only check
by reading. The review also converges on a recurring control topology:
**Planner → Executor → Reviewer**, with the reviewer as an independent role
rather than self-critique.

## Key claims

- Verifiability of the output is the dominant predictor of how much autonomy a
  team actually grants. Capability is necessary, not sufficient.
- Self-review is structurally weak; an independent reviewer (separate context,
  separate model, or a non-LLM oracle) is the recurring fix.
- Adoption is gated by blast radius and reversibility more than by token cost.

## Why it matters for sofact

This is the load-bearing constraint for the whole project. It implies the factory
must be designed **verifiability-first**: for each lane, name the machine oracle
that decides pass/fail *before* deciding how much autonomy the lane gets. Any
lane without an oracle gets read-only or human-gated autonomy, no matter how good
the local model is.

## Concerns / information quality

- Preprint, not peer-reviewed; SLRs inherit the bias of their inclusion criteria.
- "Verifiability" is left partly qualitative; no standard instrument for scoring
  a task's verifiability.
