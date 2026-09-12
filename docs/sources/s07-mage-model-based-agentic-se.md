---
id: S07
slug: mage-model-based-agentic-se
title: "MAGE: Model-Based Agentic Software Engineering"
type: paper
venue: arXiv (preprint)
arxiv: "2608.25174"
url: https://arxiv.org/abs/2608.25174
retrieved: 2026-09-12
verification: reported
confidence: medium
tags: [software-factory, models, mdse, formal-methods]
---

## Precis

Argues that agentic SE should be *model-based*: agents operate on an explicit
model of the system (architecture, interfaces, invariants, state machines) rather
than on raw source text. The model is the shared artifact that makes multi-agent
work composable and gives verifiers something to check other than tests. This
rehabilitates model-driven software engineering (MDSE) with an LLM as the
transformer between model and code.

## Key claims

- Raw-text-only agents lose the invariant information needed to verify
  non-test-checkable properties.
- An explicit model gives a second, cheaper oracle class: structural/consistency
  checks over the model, before any code runs.
- Model + generator + conformance check beats code + tests for evolvability.

## Why it matters for sofact

This is the strongest argument for sofact *owning a model of its own codebase*
and of the systems it builds. It also explains why the factory should be
self-describing: the model is what lets a low-capability local model make
high-capability decisions, by shrinking the search space it has to reason over.

## Concerns / information quality

- MDSE has a long history of elegant frameworks that failed on maintenance cost.
  The LLM changes the cost curve, but the claim needs empirical support.
- Preprint; URL unresolved in-session.
