---
id: S13
slug: anthropic-harness-billing
title: "Anthropic billing change: Claude Pro no longer covers third-party agent harnesses"
type: news / primary (vendor policy)
url: null
retrieved: 2026-09-12
verification: reported
confidence: low-medium
tags: [economics, hosting, vendor-risk, local-vs-cloud]
---

## Precis

Reported April 2026 change: subscription plans stopped covering usage of
third-party agent harnesses, moving that traffic to per-token billing. The
practical effect is that the "flat-rate subscription + open-source agent harness"
pattern, which is how a lot of agentic tooling was economically viable, stopped
being viable. This is cited in the local-model discourse as the trigger for
"switch to local".

## Key claims

- Harness freedom and subscription economics are coupled; vendors control both.
- Agentic workloads have a very different cost profile from chat (many long
  contexts, high token volume per task), which makes per-token pricing bite hard.
- This is structural vendor risk for any factory that depends on a hosted model:
  the harness is the thing being repriced, and you do not control it.

## Why it matters for sofact

The strongest available argument for the local-model bet, and a governance point
for the spec: the factory's economics must not depend on a vendor's tolerance for
agentic harness traffic. It also implies the factory should be *model-agnostic
behind an interface* so the local/remote split is a config decision, not a
rewrite.

## Concerns / information quality

- Second-hand in-session; the exact scope and effective date need re-verification
  against Anthropic's own pricing/terms before being cited.
- The local-vs-cloud framing in the discourse is partly ideological; the real
  question is a cost/throughput crossover per lane, which is measurable.
