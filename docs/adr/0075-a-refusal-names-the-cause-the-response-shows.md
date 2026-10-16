# 0075 — A refusal names the cause the response shows

- **Status:** Accepted
- **Date:** 2026-10-16
- **Related:** FR-168, FR-172, FR-173, NFR-024, ADR-0002, ADR-0070;
  [ADR-0021](0021-research-is-dispatched-not-performed.md)

## Context

The front door was exercised end to end — `sofact build --statement …` against a
fresh home, at the shipped defaults, with no environment overrides. It failed, and
it failed twice for one reason: **the refusal described something other than what
happened.**

**First.** The run stopped at P0 with

```text
no proposal: boundary: deepseek-v4.1-flash:cloud produced only a reasoning
channel, no content.
```

The cause is in the response, and the response said so:

```console
$ # the same prompt, against the same endpoint the refusal named
content: ''
reasoning chars: 4804
finish: length  usage: {'completion_tokens': 1024, 'total_tokens': 1049}
```

`finish_reason: "length"` with 1024 of 1024 completion tokens spent. The budget was
exhausted **inside** the reasoning channel — a fact an operator can act on, since it
is fixed by one environment variable. The message named the channel, which is a
symptom, and withheld the budget, which is the cause. Measured over P0's six
dimension prompts on the default model at the shipped cap of 1024, **two of six —
`boundary` and `failure` — failed this way.** So the default configuration could not
complete the interrogation the front door opens with.

The attribution was also wrong in a second, quieter way. The predicate was "the reply
carries a non-empty `reasoning` field", and every provider that streams the chain of
thought *beside* the answer rather than inside the budget — DeepSeek-R1 and Qwen3
return `reasoning_content` — sets that field on **good** replies. A local `qwen3.5:9b`
was probed and returned `content: ""` with `reasoning_content` of 4804 characters
under the key `reasoning`, and separately a working reply with `reasoning_content`
set. The client read the first as "a reasoning channel" and would have read the second
the same way had `content` been empty for any other reason. It asserted a cause it had
not checked.

**Second.** Re-run with the budget raised, the run stopped at P0 again:

```text
no proposal: boundary: http://localhost:11434/v1 unreachable: .
```

The sentence ends on a bare colon. Every `httpx` transport error — `ConnectError`,
`ConnectTimeout`, `ReadTimeout` — stringifies to `""`, so `f"unreachable: {exc}"`
produced nothing where the reason belonged. The class name is the whole
distinguishing fact here, because a refused connection and a timeout have different
fixes, and the message dropped it.

**Third.** With both fixed the run drafted all six dimensions — and then stopped anyway:

```text
  [done] propose-answers (P0)
    drafted 6 proposal(s); a person must attest them
  [skipped] propose-answers (P0)
    no dimension left to propose: the interrogation is already answered and awaiting a
    person's attestation. Run `sofact build --resume` once they have read them (FR-173)
  terminal: exhausted
  next: sofact   (bare: the questionnaire resumes at the open dimension)
```

Two lines of one report gave contradictory instructions. The `detail` said `build
--resume`; the `next:` line directly beneath it said the questionnaire. Neither was
right: `readiness` reports a model-proposed answer nobody attested as **open** (FR-173)
— correctly, since the floor measures specificity and this measures authorship — so
the second iteration selected `propose-answers` again, found every dimension already
holding a proposal, and proposed nothing. `--resume` re-selects that same action and
prints that same sentence forever. The verb that works is `sofact attest`, and the run
was not waiting on a resume at all.

The selector's own comment claimed it selected `propose-answers` "only when a dimension
is genuinely open"; `ready` is false for both ways a dimension is open, so it selected
it for either. Every other test of this path either configures no model — so the run
stops on the *unreachable* branch — or answers the dimensions itself, which is why 1987
tests passed over it.

Neither defect is caught by a test that passes a healthy reply, and none was caught by
the 1987-test suite. All three were caught by running the product.

## Decision

**A refusal is composed from what the response actually contains, and says what the
operator can do about it.**

1. `_why_no_content(message, choice, config)` reads `finish_reason` and the channel,
   and distinguishes three cases: budget spent inside a reasoning channel (naming the
   budget, the channel's size, and the variable to raise), budget spent with no
   channel, and a model that simply returned nothing. `finish_reason == "length"` is
   the discriminator, because it is the response's own statement that the budget ran
   out — rather than the presence of a channel, which is not evidence of anything.
2. The channel is read under both spellings, `reasoning` and `reasoning_content`, so
   the diagnosis works for the Ollama front end and for the providers that use the
   other name.
3. `DEFAULT_MAX_TOKENS` is **4096**, and the constant's docstring records the
   measurement: at 1024 two of six P0 prompts fail; at 4096 all six answer, the
   longest at 2915 characters. The floor is set by the deepest prompt this product
   writes, not by tidiness. The cap bounds a runaway on a local model (ADR-0002); it
   is not a spend control, and the default that makes the front door unusable is the
   wrong default.
4. `httpx` transport errors are reported by **class name** and with the configured
   timeout: `unreachable after 120s: ConnectTimeout`. `str(exc)` is not used, because
   for these types it is empty.
5. `DriverRun.awaiting_attestation` records which of P0's two waits a run ended in, and
   `next_human_verb` reads it. Both waits stop on `propose-answers` with an `EXHAUSTED`
   terminal; only the state distinguishes "no dimension has been answered", where a
   proposal is what is missing, from "every open dimension holds a proposal nobody
   attested", where no amount of driving closes the gap. The driver holds that state
   and the view does not, so it is a **recorded field rather than a derived property** —
   deriving it would mean parsing the reason strings `readiness` writes for a human, and
   the state exposes the same two facts as data (`is_model_proposed`,
   `attested_answer_ids`). It defaults to `False`, which names `build --resume`: correct
   for every other stop, and the reading an older ledger row folds to.

## Consequences

The three cases are now distinguishable from the message alone, which is the whole
point: "raise the budget", "the endpoint is not answering", "the model returned
nothing", and "a person has to attest these" are four different actions, and before
this they arrived as sentences naming none of them or the wrong one.

`LlmConfig.max_tokens` keeps its validator and its env override; only the default
moves. A deployment that set `SOFACT_LLM_MAX_TOKENS` is unaffected.

`DriverRun` gains a field, so a ledger written before this folds the new key to
`False` — the `gate_failures` precedent, and the reason the default is the older
behaviour rather than the more informative one.

This changes no verdict and no gate. The advisor remains allowed to fail — FR-172
records the failure as a named terminal state, and `sofact build` still stops with
`NOT built` and the next verb. What changed is whether the operator is told why, and
whether the verb they are told to type can do anything.

## Evidence

**Four canaries, all caught, each reverted from a `cp` backup with `__pycache__`
cleared.**

1. The `finish_reason == "length"` branch disabled — 1 of 32 failed,
   `test_an_exhausted_budget_names_the_budget_and_not_the_channel`. This is the
   original defect restored, so the test is watching the thing that was wrong.
2. `type(exc).__name__` back to `exc` — 1 of 33 failed,
   `test_an_unreachable_endpoint_becomes_llm_unavailable`, on
   `said.rstrip().endswith("ConnectError")`.
3. `DEFAULT_MAX_TOKENS` back to 1024 — 1 of 33 failed,
   `test_the_default_budget_clears_the_deepest_prompt_the_product_writes`.
4. `awaiting_attestation=_proposals_waiting(...)` replaced by `awaiting_attestation=False`
   — 2 of 20 failed, both in `TestAProposalIsNotAnAnswer`. The flag is the only thing
   that distinguishes P0's two waits, so both the message and the continuation depend
   on it.

The three `llm.py` tests are pinned to literals rather than to the constants they check, so
lowering the bound moves the assertion and not the input — the trap recorded in
`tests/ci/test_docs.py`'s lesson about a test whose input is computed from the
constant it tests.

**Four probes against the live endpoint and the live front door**, which is what found
all of this and what a test cannot substitute for: the six-dimension sweep at 1024 (2
refused) and at 4096 (6 answered); the `qwen3.5:9b` reply read field by field to
establish that `reasoning_content` accompanies working answers; `sofact build` against a
fresh home at the shipped defaults, twice, which is how the empty-message defect and the
contradictory-verb defect surfaced; and `sofact attest --all` followed by
`build --resume` to confirm the verb the message names is the verb that works.
