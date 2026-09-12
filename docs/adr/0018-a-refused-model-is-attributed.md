# 18. A refused model is attributed, not blamed on the producer

* Status: Accepted
* Date: 2026-09-12
* Deciders: operator
* Related: [ADR-0009](0009-no-oracle-no-autonomy.md),
  [ADR-0012](0012-the-harness-table-is-data-not-code.md),
  [ADR-0016](0016-a-harness-path-names-its-own-envelope.md),
  [ADR-0017](0017-a-completed-session-is-checked.md)

## Context

FR-148 requires the capability matrix to be *measured*, never asserted. The probe measured
`non_interactive`, `telemetry`, `context_files_disabled`, `goal_mode`, and
`bootstrap_empty_repo`; it did **not** measure whether the harness resolves the model it was
handed. SoFact's README said the quiet part out loud: "a bad model is a child-process failure
the probe catches."

It caught it as *a failure*, which is not the same as catching it. A harness handed an
identifier its registry does not know exits non-zero and writes no session record. A producer
handed a goal it cannot do also exits non-zero and can write no record. The two are the same
bytes. Everything downstream — `StepOutcome.FAILED`, `capability_loss`, the run's exit status,
any report built on the ledger — attributed the first to the second, and the operator was told
the producer failed when nothing had been produced because nothing had been asked.

Two facts made the confusion avoidable, and both were already measured:

1. **The identifier is resolved by the harness's own registry, not by the model server.** A
   tag Ollama serves can be one the harness refuses. Measured at `pi` 0.85.1: `--list-models`
   advertises seven ollama models, and `qwen3.6-coding:latest` — a real local tag — is refused.
2. **The harness says so in its own words, on stderr, with a distinctive string.**
   `Error: Model "qwen3.6-coding:latest" not found. Use --list-models to see available
   models.` A refusal is therefore a *positive* observation, which by FR-153 is decidable even
   though the absence of one would not be.

## Decision

1. **`model_resolved` is the tenth capability**, and it is the only row decidable in both
   directions. A declared refusal string found in the child's output is `ABSENT`; a clean exit
   that left a readable record is `CONFIRMED`. No third state is inferred from a clean exit.
2. **The refusal string is data on the spec** (`model_error_pattern`), not a branch on the
   harness's name. This is ADR-0012's rule applied to a failure mode: a harness quirk belongs
   in the table. A spec that declares no pattern reports `INCONCLUSIVE` and says it does not
   know how to read the failure — an unattributed non-zero exit is never re-read as a model
   problem, because a harness that fails for a *different* reason would then be reported as a
   bad model.
3. **The profile records the model it was measured with**, and a dispatch whose model differs
   is refused. A capability finding is a claim about a configuration, not about a binary name;
   applying another configuration's finding is the same class of error as reading a path under
   the wrong envelope (ADR-0016).
4. **Both refusals are gates, not warnings** — `ABSENT` at probe time, mismatch at dispatch
   time — because both mean nothing can run. They are distinct from `goal_mode`'s downgrade
   (FR-144), which means something can run with a reported capability loss.
5. **Refusals reach the operator.** The CLI preflights the model it *can* see and prints the
   harness's own words; for the mismatch it cannot see, the record's note is printed, because
   for a step that never ran the note *is* the fact. The `not_dispatched` case no longer reuses
   the "incomplete session asserts nothing" line, which was misleading about a step that never
   started.

## Alternatives refused

* **Validate the model on SoFact's side** — ask Ollama what it serves, or keep a list of
  harness-approved ids. Wrong oracle: Ollama's list is not the harness's registry, and a
  hardcoded list is stale by construction, which is exactly what FR-148 exists to prevent.
* **Treat any non-zero exit with no record as a model problem.** Then a harness that fails for
  its own reasons is reported to the operator as a model misconfiguration, and the operator
  spends the afternoon on `SOFACT_MODEL`. An unattributed failure is recorded as unattributed.
* **Match on the model name to decide which findings apply.** Names are not identities: two
  configurations can share a model id and differ in tools, flags, or provider.
* **Promote it to `INCONCLUSIVE` for `pi` and document the gap,** as the other four gaps are
  documented. Refused: the string is measurable, the positive observation is decidable, and
  this is the failure the operator hits first on a fresh deployment.
* **Refuse at dispatch by re-running the probe there.** The probe is expensive and is not the
  dispatch's job; a recorded profile is what FR-148 exists to produce.

## Consequences

* **A fresh deployment fails loudly and correctly**, before any session starts: `probe` exits
  1 naming the harness's own error, and `dispatch` refuses rather than reporting a producer
  failure that never happened. The end-to-end demo's own failure mode — five sessions, exit 0,
  nothing verified (ADR-0017) — now has a sibling that is caught earlier.
* **`pi` gains a second gate**, so a deployment that probed with the good model and dispatches
  with another gets a refusal rather than a mysterious producer failure. The cost is that a
  profile must be re-probed when the model changes; that is a consequence of the profile being
  a measurement.
* **Old profiles stay readable.** The model field defaults to empty, and an empty model gates
  nothing, so a ledger written before this record does not suddenly refuse every dispatch.
* **The probe's output is no longer discarded.** It was already being captured and thrown away;
  reading it is what makes the row decidable.
* **This does not weaken the honest claim about coverage.** Four rows remain unwitnessed gaps
  that say so in their own reason strings. `model_resolved` stopped being a fifth.

## Evidence

* **Live, against the real binary.** `SOFACT_MODEL=qwen3.6-coding:latest sofact --home
  /tmp/sf-model probe` → exit `1`, with `model qwen3.6-coding:latest` printed, the row
  `absent model_resolved`, the reason quoting `'Error: Model "qwen3.6-coding:latest" not
  found. Use --list-models to see available models.'`, and the closing line *"the harness
  cannot resolve the model 'qwen3.6-coding:latest', so every dispatch would fail before any
  work started -- fix SOFACT_MODEL (or --model) and probe again (FR-148)."* The identifier is
  a real Ollama tag, which is the point.
* **The probe stops discarding the child's output.** `probe()` previously bound it to
  `_stdout`/`_stderr`; the pattern check reads both streams, because `pi` writes the refusal to
  stderr and a harness may write it to stdout.
* **Tests, 19 new** — `test_harness.py::TestModelResolution` (11) covers `CONFIRMED`,
  `ABSENT` with the verbatim quote, no declared pattern, an unattributed non-zero exit, a clean
  exit with no record, the row count against `len(HarnessCapability)`, both dispatch gates, that
  an `INCONCLUSIVE` row does not stop a run (FR-153), and that a pre-existing profile with no
  model recorded gates nothing. `test_service.py::TestModelResolutionThroughTheService` (4)
  covers the probe-to-dispatch path and that the refusal is in the *ledger*, not only in a
  return value. `test_cli.py::TestTheModelIsPartOfTheConfiguration` (4) covers the printed
  model, the probe refusal, the preflight refusal, and the adapter refusal reaching the
  operator.
* **The synthetic harness refuses the same way the real one does.** Mode `badmodel-once`
  prints the same sentence to stderr and exits 1 on its first call only, so one test can watch
  the probe record a refusal *and* leave the dispatch a working child — which is what proves
  the gate refused before anything ran, rather than the child having failed.
* **Gate after:** `465 passed`, pyright `0 errors, 0 warnings, 0 informations`,
  `ruff check` clean, `markdownlint` 0 issues over 47 files.

## References

* `src/sofact/harness.py` — `HarnessSpec.model_error_pattern`, `PI_SPEC`, `probe()`'s
  `model_outcome`, `dispatch()`'s two gates
* `src/sofact/views.py` — `HarnessCapability.MODEL_RESOLVED`, `HarnessProfile.model`,
  `HarnessProfile.model_resolved`
* `src/sofact/cli.py` — `_print_profile`'s model line, `_probe`'s and `_dispatch`'s preflight
  refusals, `_print_dispatch`'s note
* `docs/spec/product-spec.md` §8.5 — **FR-164**, and the gate paragraph rewritten
* `[S19]` — `pi`'s CLI and registry surface, measured at 0.85.1
