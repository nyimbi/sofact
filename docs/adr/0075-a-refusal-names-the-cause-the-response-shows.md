# 0075 — A refusal names the cause the response shows

- **Status:** Accepted
- **Date:** 2026-10-16
- **Amended by:** [ADR-0077](0077-the-interrogation-asks-eight-dimensions-and-scale-is-one-of-them.md) — the measurements in this record were taken when P0 asked **six** dimension prompts, and P0 now asks eight. The counts here are left as measured and dated rather than restated, because the measurement is what makes the 1024-token finding a fact; every decision and consequence below stands.
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

**Fourth.** Acting on the third — attesting the six proposals and resuming — the run
reached P2 and stopped, and told the operator to type a command that does not exist:

```console
$ sofact build --resume
  [done] research (P1)      researched: 70 source(s), 36 clause verdict(s)
  [done] contract (P2)      contracted 36 clause(s)
  [REFUSED] specify (P2)
    ValueError: P1 cannot complete: 12 clause(s) return the pipeline to P0 …
  next: sofact build --resume
```

The refusal is correct and is a finding of its own — P1 classified twelve clauses as
`invalidated`/`deepened`, and FR-068 says those return the pipeline to P0 rather than
being built on. But the run reports `terminal: failed`, and `next_human_verb` for a
failed run is `RESUME_VERB`, which re-selects `decompose` and refuses identically, three
runs in a row, byte for byte. That is the third defect's shape again with a different
terminal.

Then the gate branch, which is the one that matters, since it is the *only* way past a
gate:

```console
$ sofact gate approve P2 --by operator
╭─ Error ─────────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (approve P2)                                   │
╰────────────────────────────────────────────────────────────────────────────────────╯
exit 2
```

Every string this product printed for the approval read `sofact gate approve P2 --by
you`. The command's option is `--approve`, so the spelling was refused by the parser
before reaching any of the checks the sentence was about. It appeared in `views.py`,
`driver.py`, `api.py`, `docs/spec/product-spec.md` and ADR-0070, and the tests that
covered it asserted the string **equal to a literal** — the literal written from the same
misreading as the code, which is the one assertion that cannot fail. `test_cli.py` had
the correct spelling in one place and the wrong one in another, and passed.

Neither defect is caught by a test that passes a healthy reply, and none was caught by
the 1987-test suite. All four were caught by running the product.

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
5. `GATE_APPROVE_VERB` is the one spelling of the approval, and it is the CLI's:
   `sofact gate --approve`. A constant rather than four strings, because the sentence is
   printed from three modules and only the CLI can say which spelling parses — and the
   check that it parses is a **test that invokes the installed CLI** on every verb the
   product prints, rather than an equality against a literal. A string a product tells a
   person to type is an interface; the test for an interface is the interface, not a
   copy of the string.
6. `DriverRun.awaiting_attestation` records which of P0's two waits a run ended in, and
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

**An instruction is a claim, and it is checkable against the thing it instructs.** The
approval sentence was wrong in five files and in every test that covered it, because the
tests compared the string to a copy of itself. The replacement compares it to the CLI:
the prefix is invoked for real, and a parser that rejects it fails the test. That is the
only oracle for "is this a command", and it generalises to every other verb the product
prints — the check enumerates the printed verbs rather than naming the one that was
wrong, so a fifth string added later is covered without an edit.

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

## What this does not fix

Two gaps the same walk reached, both recorded and neither closed here, because both need a
design decision rather than a wording change.

**A pipeline stopped by its own evidence has no exit.** P1 classified twelve of the draft's
thirty-six clauses `invalidated`/`deepened`, and FR-068's table says what to do: "Return to
P0. Do not build." The refusal is enforced and correct. But P0 cannot be re-entered —
`advance_phase(P0, ACTIVE)` raises "P0 is already complete; a phase is not re-entered by
advancing it again (FR-060)" — and `sofact draft` re-emits the *same* thirty-six clause ids
from the same answers, so re-eliciting produces the same draft, the same ids and, with the
same sources, the same verdicts. The one verb that touches the clauses takes no input with
which to revise one. So the remedy FR-068 names is unreachable, and `build --resume`
re-selects `decompose` and refuses identically. The missing thing is a recovery verb, which
is a requirement the specification does not state.

**A `FAILED` run's next verb is `RESUME_VERB` for every failure.** The third defect above
was fixed for P0's two `EXHAUSTED` waits and not for `FAILED`, so a run stopped by the gap
above tells the operator to run the command that provably loops. Whether a resume can act is
a fact about *why* the run failed, and the driver holds it — the same shape as
`awaiting_attestation`, which is why it is named here rather than fixed by guessing.

Both are reachable from the front door at the shipped defaults. Neither is fixed by the
change this ADR records, and neither moves a verdict: FR-068's requirement is that every
clause is classified, which is delivered and enforced, and the missing recovery verb is not
a half of it.

## Evidence

**Five canaries, all caught, each reverted from a `cp` backup with `__pycache__`
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
5. `GATE_APPROVE_VERB` back to `"sofact gate approve"` — 2 of 3 failed in
   `TestTheVerbTheProductTellsTheOperatorToType`, the first on
   `'sofact gate approve' is printed to the operator and the CLI refuses it: … Got
   unexpected extra argument(s) (approve)`. The canary **is** the defect: it is the
   string that shipped, so the gate is watching the thing that was wrong rather than a
   mutation chosen to be nearby.

The three `llm.py` tests are pinned to literals rather than to the constants they check, so
lowering the bound moves the assertion and not the input — the trap recorded in
`tests/ci/test_docs.py`'s lesson about a test whose input is computed from the
constant it tests.

**Six probes against the live endpoint and the live front door**, which is what found
all of this and what a test cannot substitute for: the six-dimension sweep at 1024 (2
refused) and at 4096 (6 answered); the `qwen3.5:9b` reply read field by field to
establish that `reasoning_content` accompanies working answers; `sofact build` against a
fresh home at the shipped defaults, twice, which is how the empty-message defect and the
contradictory-verb defect surfaced; `sofact attest --all` followed by `build --resume`,
which carried the run through P1's research (70 sources, 36 clause verdicts) and the
contract to P2; `sofact gate approve P2 --by operator`, which exited 2 on the spelling
every printed sentence named; and `build --resume` a third time, byte-identical to the
second, which is how the `FAILED`-terminal loop surfaced.
