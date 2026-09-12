---
id: S05
slug: live-swe-agent
title: "Live-SWE-agent (self-evolving software engineering agent)"
type: paper / system
url: null
retrieved: 2026-09-12
verification: reported
confidence: low-medium
tags: [benchmark, self-evolving-agent, swe-bench]
---

## Precis

A minimal-scaffold software-engineering agent that *writes its own tools at
runtime* rather than carrying a large fixed harness. Reported SWE-bench Verified
result: **77.4%**, claimed to be competitive with heavily engineered scaffolds
while being far smaller. The interesting mechanism is self-extension: when the
agent hits a capability gap, it synthesises a helper (script, tool wrapper) and
continues, rather than failing.

## Key claims

- A large part of scaffold complexity can be replaced by runtime tool synthesis.
- Self-evolution of the harness is a viable substitute for hand-built tool suites.

## Why it matters for sofact

Directly relevant to a single-machine factory, where every hand-built tool is
maintenance load. But note the second-order risk: an agent that writes its own
tools can write tools that satisfy its evaluator rather than the requirement
(see S15). Tool synthesis must be gated by the same oracle discipline as code.

## Concerns / information quality

- arXiv ID not captured in-session; treat the specific number as directional.
- "Self-evolving" claims are hard to audit; the evaluation protocol is the
  question, not the headline number.
