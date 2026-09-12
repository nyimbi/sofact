# 0002 — Model access is one OpenAI-compatible interface

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

An early constraint on SoFact was "use a local ollama model as the LLM", on the
reasoning that locality buys hermeticity: no egress, no third-party uptime, no data
leaving the deployment.

That reasoning does not survive contact with the daemon. Ollama's OpenAI-compatible
endpoint at `http://localhost:11434/v1` serves models whose weights are *not* on the
machine: the `:cloud` suffix names a model executed by Ollama's hosted service and
proxied through the local daemon. The default model chosen for this project,
`deepseek-v4.1-flash:cloud`, is exactly that. It answers on `localhost` and does not
appear in `ollama list`.

So "the model answers on loopback" and "the model is local" are different
propositions, and the first does not imply the second. A system that treats them as
equivalent has an egress boundary in its documentation and none in its behaviour.

The broader product requirement (spec §"Hardware") is hardware-agnostic: `x86_64`
and `arm64` Linux, no GPU required, with an optional accelerator if one is detected.
That rules out binding to any one runtime's native API.

## Decision

All model access goes through **one OpenAI-compatible interface**, configured by
environment:

- `SOFACT_BASE_URL` — default `http://localhost:11434/v1`
- `SOFACT_MODEL` — default `deepseek-v4.1-flash:cloud`
- `SOFACT_LLM_TIMEOUT`

No code path may assume that reaching the endpoint implies local execution. The
distinction between "local weights" and "cloud-routed through a local daemon" is a
deployment property, recorded by the operator, not inferred by SoFact.

Tests must never depend on the default: the `_no_network` autouse fixture points
`SOFACT_BASE_URL` at `http://127.0.0.1:9/v1` (the discard port, which refuses
immediately), so an unconfigured test run cannot reach anyone's service.

## Evidence

- Ollama 0.34.0 serving `POST /v1/chat/completions` on `localhost:11434`; response
  body reports `"model": "deepseek-v4.1-flash"` (the `:cloud` suffix is stripped
  server-side).
- `deepseek-v4.1-flash:cloud` is absent from `ollama list` — it is not a local blob.
- Reasoning models in this family emit a separate `reasoning` field and consume small
  `max_tokens` budgets entirely before producing content, so budgets below ~300
  produce empty content. Recorded because it presents as a broken model.

## Consequences

- The default configuration **is not hermetic**. Hermeticity is a deployment choice
  (a genuinely local model tag, or an air-gapped host), not a default.
- SoFact can swap providers — a fully local `llama-server`, a different Ollama tag, a
  hosted API — without code change. This is the point.
- Any future claim of offline operation must be proved by an egress test, not by the
  base URL starting with `127.0.0.1`. A loopback URL is not an egress boundary.
- FR-152 (default telemetry phone-home must be disabled) generalises this lesson to
  third-party tooling: an `--offline` flag that does not stop a default exporter is
  not an egress boundary either.
