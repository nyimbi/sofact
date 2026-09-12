---
id: S12
slug: local-coding-models-2026
title: "Local coding-model landscape, 2026 (Qwen3.6, DeepSeek V4-Flash, Gemma 4, MoE tiers)"
type: survey / aggregated
url: null
retrieved: 2026-09-12
verification: reported
confidence: low-medium
tags: [local-models, moe, quantisation, throughput, ollama]
---

## Precis

Aggregated 2026 picture of open-weight coding models usable locally: Qwen3.6-27B
(dense), Qwen3.6-35B-A3B (MoE, ~3B active), DeepSeek V4-Flash (284B total / ~13B
active, MIT-licensed), Gemma 4, and various 4B-9B distilled coding models.
Guidance is VRAM-tiered rather than capability-tiered, because for local inference
*decode speed is bounded by active parameters, not total parameters*.

## Key claims

- MoE is the correct architecture for local agentic loops: a 35B-A3B model at
  ~4-bit reads roughly the active-parameter footprint per token (~2 GB), so on an
  M2 Max (~400 GB/s) theoretical decode is ~200 tok/s vs. ~20-25 tok/s for a
  dense 27B at ~18 GB. Real-world figures are lower, but the ratio holds.
- Total parameter count buys *quality per token*; active parameter count sets
  *tokens per second*. For high-volume lane work, throughput dominates.
- 4-bit quantisation (Q4_K_M / MLX 4-bit) is the working point for agentic use.

## Why it matters for sofact

Determines the model plan. On a single M2 Max / 96 GiB box the factory is
throughput-constrained, not capability-constrained at the top — so the design
should route by required throughput and required reasoning depth, not by "best
model for everything". 96 GiB unified memory also permits running producer and
evaluator concurrently, which is what S02's isolation requirement needs.

## Concerns / information quality

- Aggregated from multiple secondary sources in-session; no single authoritative
  benchmark captured. Specific model names/versions must be re-verified before
  they go in the spec.
- Tokens/sec figures are first-principles estimates, not measurements on this
  machine. **Measure locally before committing to a plan.**
