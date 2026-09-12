---
id: S11
slug: gethuman-lanes
title: "gethuman.sh — lanes, qualifiers, and concerns for agentic delivery"
publisher: gethuman.sh
type: essay / product-doc
url: https://gethuman.sh
retrieved: 2026-09-12
verification: reported
confidence: low-medium
tags: [lanes, blast-radius, autonomy-gating, intent]
---

## Precis

A framing for deciding *where* agents may act, built on three qualifiers that a
task must satisfy to be autonomously admissible:
**intent machine-derivable** (the desired end state can be extracted from an
artifact, not a conversation), **outcome machine-observable** (pass/fail is
mechanical), and **blast radius machine-bounded** (the failure cannot escape a
declared boundary). Tasks that clear all three are routed into lanes; lanes are
indexed by intent source × capability. "Concerns" (security, data handling,
compliance, cost) set a floor on any lane regardless of its qualifiers.

## Key claims

- Three binary qualifiers are enough to route most work into autonomous vs.
  gated lanes.
- Concerns are floors, not qualifiers — they can veto a lane that otherwise
  qualifies.
- Autonomy is a property of the *task-in-context*, not of the agent.

## Why it matters for sofact

This is the most directly implementable idea encountered — a routing predicate
rather than a philosophy. It gives sofact a concrete admission-control function
and a natural schema for the spec's lane table. It also composes cleanly with the
autonomy ladder (S02/S16): qualifiers decide admission, the ladder decides level.

## Concerns / information quality

- Vendor-adjacent framing ("gethuman" implies a product in the human-escalation
  space), so the emphasis on escalation may be commercially motivated.
- The three qualifiers are persuasive but untested; blast-radius bounding in
  particular is harder to certify than it sounds for anything touching production.
