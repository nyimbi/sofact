---
id: S06
slug: sase-framework
title: "SASE: A Framework for Self-Adaptive Software Engineering with LLM Agents"
type: paper
venue: arXiv (preprint)
arxiv: "2509.06216"
url: https://arxiv.org/abs/2509.06216
retrieved: 2026-09-12
verification: reported
confidence: medium
tags: [software-factory, architecture, self-adaptive, frameworks]
---

## Precis

Proposes a reference framework for self-adaptive software engineering: the agentic
system observes its own delivery signal (test outcomes, review feedback, incident
data) and adjusts its process — not just its artifacts. The adaptation loop sits
above the task loop. Positions MAPE-K-style self-adaptation (Monitor, Analyse,
Plan, Execute over a shared Knowledge base) as the organising structure for
agentic SDLC systems.

## Key claims

- Process-level adaptation is a distinct loop from task-level execution.
- A shared knowledge base (project conventions, past failures, oracle inventory)
  is what makes adaptation cheap rather than exploratory.

## Why it matters for sofact

Justifies a two-layer design: task loop (issue → patch → verify) and process loop
(which lanes are working, which oracles are noisy, where humans keep intervening).
The intervention log is the training signal for the process loop.

## Concerns / information quality

- Preprint. Framework papers of this shape often stop before validation; check
  whether any evaluation is empirical before relying on the structure.
