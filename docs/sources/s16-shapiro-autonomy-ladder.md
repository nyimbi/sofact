---
id: S16
slug: shapiro-autonomy-ladder
title: "Dan Shapiro's five-level autonomy ladder (as applied to software delivery)"
author: Dan Shapiro (originating framing); applied to SE via S02
type: secondary / conceptual
url: null
retrieved: 2026-09-12
verification: reported-via-secondary
confidence: medium (concept), low (mapping to SE)
tags: [autonomy-levels, human-in-the-loop, gating]
---

## Precis

A five-level autonomy ladder borrowed from vehicle autonomy, giving a shared
vocabulary for how much a human is in the loop: L0 no automation, L1 assistance
(human drives, system assists), L2 partial automation (system drives in bounded
conditions, human supervises), L3 conditional (system drives, human is the
fallback), L4 high (system drives a defined domain; human not required), L5 full
(no domain restriction, no human). Applied to software delivery, the levels are
about who owns the *outcome gate*, not who types.

## Key claims

- The levels are defined by fallback responsibility, not by how much work the
  system does.
- Most real deployments are L2 in spirit: the system produces, a human is
  nominally supervising but not actually verifying.

## Why it matters for sofact

Gives the spec a defensible scale for per-lane autonomy that resists
self-flattery. A concrete use: sofact should be honest that a single-machine local
factory is realistically L2-L3 in most lanes and L4 only where oracle quality is
high and blast radius is provably bounded.

## Concerns / information quality

- Encountered indirectly (as reported in S02), not read in the original. The
  original attribution and exact level definitions should be confirmed before
  being quoted verbatim.
- The AV→SE mapping is imperfect: SE failures are usually more reversible, which
  argues for *higher* admissible autonomy at a given confidence than AV would
  allow.
