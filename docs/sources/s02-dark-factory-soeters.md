---
id: S02
slug: dark-factory-soeters
title: "Towards the Dark Factory"
author: Jeroen Soeters
type: essay
url: null
retrieved: 2026-09-12
verification: unresolved-url
confidence: medium
tags: [dark-factory, autonomy-ladder, holdout-scenarios, digital-twins]
---

## Precis

An engineering essay arguing that lights-out software production ("dark factory")
is a systems-integration problem, not a model problem. It borrows Dan Shapiro's
five-level autonomy ladder from autonomous vehicles and maps it onto software
delivery. The operational core is **holdout scenarios plus isolated evaluators /
digital twins**: the evaluating system must be causally insulated from the
producing system, or the producer learns to satisfy the metric rather than the
requirement (specification gaming / reward hacking at the organisational level).
It also references the StrongDM software-factory manifesto as the industrial
framing.

## Key claims

- Autonomy is a *ladder* (levels), not a binary; each level needs its own evidence.
- The evaluator must be isolated from the producer. Same-system evaluation
  collapses into Goodhart's law.
- Holdout scenarios are the software analogue of a held-out test set: you cannot
  iterate on them.
- "Dark" is about removing the human from the *loop*, not from the *outcome gate*.

## Why it matters for sofact

Supplies the autonomy-levels vocabulary and the isolation requirement. For a
single-machine local factory this is the hardest constraint to honour: the
evaluator runs on the same box and often the same model weights as the producer.
The factory needs a structural answer (separate model instance, frozen scenario
corpus, no write access from producer to scenario corpus).

## Concerns / information quality

- Practitioner essay; persuasive rather than empirical. Level definitions are
  inherited from AV autonomy, where the mapping is imperfect (a code change is
  usually more reversible than a driving error).
- URL not captured in-session; must be re-sourced before citing publicly.
