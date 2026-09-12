---
id: S09
slug: six-layer-reference-architecture
title: "A six-layer reference architecture for agentic software production"
type: paper
venue: arXiv (preprint)
arxiv: "2604.26275"
url: https://arxiv.org/abs/2604.26275
retrieved: 2026-09-12
verification: reported
confidence: low-medium
tags: [architecture, layering, software-factory]
---

## Precis

A layered decomposition of an agentic software production system: intent/spec
capture, planning, execution, verification, integration/release, and
observation/feedback. Each layer has a defined input/output contract and its own
verification obligations. The value is not novelty but vocabulary: it gives names
to the seams where a factory either holds or leaks.

## Key claims

- Production systems need explicit layer contracts; a monolithic agent loop
  cannot be evolved or audited.
- Verification is its own layer, not a step inside execution.

## Why it matters for sofact

Candidate skeleton for the spec's architecture section, and a checklist for
finding leaks: e.g. execution layer writing directly to release artifacts is a
layering violation, regardless of whether the output happens to be correct.

## Concerns / information quality

- Six-layer decompositions are easy to publish and hard to falsify. No strong
  empirical claim here; treat as a naming convention.
- Reported in-session without URL confirmation.
