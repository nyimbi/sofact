# 17. A completed session is checked, and an unverified run is not a pass

* Status: Accepted
* Date: 2026-09-12
* Deciders: operator
* Supersedes: the *trigger* half of
  [ADR-0015](0015-a-verdict-describes-one-run.md); its run-scoping half stands unchanged
* Related: [ADR-0006](0006-the-verifier-cannot-reach-the-executor.md),
  [ADR-0009](0009-no-oracle-no-autonomy.md),
  [ADR-0015](0015-a-verdict-describes-one-run.md),
  [ADR-0016](0016-a-harness-path-names-its-own-envelope.md)

## Context

FR-138 states that a harness completion declaration "must trigger P6 and must never satisfy
it". ADR-0015 implemented the trigger as `check_declaration(plan_id, dispatch_id)`, which
returned `None` unless `record.declared_complete` — a precondition on a producer's
*vocabulary*. The default harness does not have that vocabulary: `PI_SPEC.completion_event`
is `None` because `pi` emits no completion event at all (measured at 0.85.1, [S19]).

So for `pi` — which is `DEFAULT_HARNESS` — the trigger was dead code. Not "rarely fired":
**never**. The verification phase (P6) was unreachable through `dispatch`, and the only way
to get a verdict was to run `sofact run` plus `sofact verify` by hand and hope the operator
remembered.

## The defect, measured

A real build, from a real Socratic interrogation to real files: a six-clause contract whose
single oracle command is
`python3 -c "from wordcount import count_words; assert count_words('a b a') == {'a': 2, 'b': 1}"`,
dispatched against `pi` 0.85.1 driving `qwen3.6:35b-mlx` through ollama (local weights), five
sessions, `tools="read,write,edit,bash"`.

```text
/tmp/sf-build  (before)               /tmp/sf-build2  (after)
  5 step.dispatched                     5 step.dispatched
  0 evidence.recorded                  30 evidence.recorded    (5 runs × 6 clauses)
  0 claim.declared                      0 claim.declared
  0 verdict.rendered                    5 verdict.rendered
  dispatch --all --max-steps 5 → 0      dispatch --all --max-steps 5 → 0
  verify → INSUFFICIENT                 verify → 6 of 6 clauses hold, exit 0
  "no evidence was recorded"            "exit code 0 and required output present"
```

Both runs produced working code — `wordcount/__init__.py` plus a project around it — and the
contract's own oracle passes by hand in both workspaces. The difference is that the first
run **verified nothing**, and its exit status said otherwise.

Every session completed in 20–34 s and reported token counts (460–730), which were readable
only because of ADR-0016's fix: the same live harness, one turn earlier, had reported
`telemetry absent` for a record containing a usage block.

**Why the suite missed it.** The trigger tests drove the synthetic harness in its `complete`
mode — precisely the one side of the capability the trigger depended on. A test of a rule
that only exercises the rule's *enabling* condition cannot observe that condition's absence,
and one of those tests,
`test_a_dispatch_that_declares_nothing_triggers_nothing`, asserted the defect as though it
were the design.

## Decision

1. **The trigger is the session's outcome.** `check_dispatch` runs the contract's oracles
   when `record.outcome is StepOutcome.COMPLETED` — the process exited and did not time out.
   That is a fact SoFact observed about a process it started, not a claim anyone made.
2. **A declaration stays a separate, additional signal.** `CLAIM_DECLARED` is written only
   when the harness declared, and it is written *before* the verdict. FR-138 is untouched:
   the claim is not an input to `verify`, whose signature has nowhere to put one.
3. **A session that did not complete triggers nothing.** Unchanged from ADR-0015. A failed
   or budget-exhausted dispatch was still changing the tree; a verdict there is a
   manufactured signal.
4. **The method is renamed `check_dispatch`.** The old name asserted a precondition that no
   longer holds, and a name that states the wrong trigger is the same class of error as the
   code that enforced it.
5. **The shell boundary distinguishes the three failures.** Exit non-zero when nothing was
   verified at all, when any dispatched step was *refuted* by its own check, or when a plan
   that ran to its end left the contract not clean (including `INSUFFICIENT`). A run the
   operator capped with `--max-steps` is progress rather than failure and may exit 0,
   provided nothing it ran was refuted.
6. **The CLI says which case each step is in** — declared complete, completed-and-checked,
   or not checked — so a reader never has to infer it from an absence.

## Alternatives refused

* **Keep the declaration gate and document the gap.** Then the *default* configuration is a
  factory that builds without verifying, and the honest version of that stance is to make
  `dsh` the default — whose headless profile is broken out of the box here
  (`deepseek-harness-runtime-bin 0.1.5rc1`, missing `@deepseek-ai/dsh-session-title-llm`).
  That trades a silent hole for an unusable default.
* **Read exit code 0 as a declaration.** This is the conflation FR-138 forbids, in the other
  direction: a producer's *silence* would become a claim. Silence is not a claim. It is a
  fact about a process, which is exactly why it can be a trigger and can never be an input.
* **Teach `PI_SPEC` a completion event `pi` does not emit**, so that the declaration gate
  finds something. That invents a wire fact — ADR-0016's failure mode, and the failure mode
  the whole harness-as-data design exists to avoid.
* **Check only the clauses each step covers.** Already refused in FR-163: under FR-162's run
  scoping, a partial report marks the unrun clauses `INSUFFICIENT` and destroys the
  corroboration of the steps verified a moment earlier.

## Consequences

* **The default harness is verified now.** Every completed `pi` step renders a whole-contract
  verdict, which also makes the wave gate (FR-142) live for `pi`: the gate reads verdicts, so
  it was inert for exactly the same reason.
* **`declaration_precision` (FR-143) still reports `unmeasured` for `pi`,** and that is the
  instrument's definition rather than a gap to close — it divides *claims*, and `pi` makes
  none. The new state is verdicts without claims, and the two must not be collapsed: an
  absent signal is not a zero (NFR-024).
* **Cost.** A completed step now runs the contract's oracles; a nine-step plan runs them nine
  times, 54 clause executions over six clauses. ADR-0015 already accepted this redundancy for
  declarations. It is not optimised away, because a partial check would be a different claim
  than the one FR-163 makes.
* **Strictly less coupling.** The trigger reads `StepOutcome`, which SoFact computes from the
  exit code, rather than a wire-format field. A harness whose session *record* is unreadable
  but which exits cleanly is now checked anyway.
* **A second documented exit-code change,** in the same direction as ADR-0015's: `--max-steps`
  no longer implies failure. The contract line still reports how much of the contract holds,
  so a capped run's success is quantified rather than asserted.

## Evidence

* **Before** (`/tmp/sf-build`, home left in place): ledger census `5 step.dispatched`,
  `0 evidence.recorded`, `0 claim.declared`, `0 verdict.rendered`; `dispatch --all
  --max-steps 5` exit `0`; `verify` → `Not verified` with "no evidence was recorded for this
  clause" on every clause. The workspace held a `wordcount/__init__.py` that satisfies the
  oracle.
* **After** (`/tmp/sf-build2`, regenerated from the same interrogation input): ledger census
  `5 step.dispatched`, `30 evidence.recorded`, `0 claim.declared`, `5 verdict.rendered`;
  final dispatch line `contract satisfied: 6 of 6 clauses hold`; `verify` exit `0` with
  "exit code 0 and required output present" per clause; `precision` → `unmeasured: this
  harness never declared completion`.
* **The artefact is real, not a fixture.** `/tmp/sf-build2/workspace` contains
  `wordcount/__init__.py`, `tests/test_oracles.py`, `bin/ci.sh`, `pyproject.toml`, written by
  the dispatched sessions; the contract's oracle command passes there by hand.
* **The failing tests first, then the fix.** `test_a_completed_dispatch_is_checked_without_a_declaration`
  and `test_a_failed_session_is_not_checked` replaced the test that asserted the defect;
  `test_a_run_that_verified_nothing_exits_nonzero` and
  `test_a_capped_run_reports_progress_rather_than_failure` pin the exit rule at the CLI.
  Full gate after: `433 passed`, pyright `0 errors, 0 warnings, 0 informations`, `ruff check`
  clean, `markdownlint` 0 issues over 46 files.

## References

* `src/sofact/service.py` — `check_dispatch` (437), the trigger in `dispatch_step` (704)
* `src/sofact/cli.py` — `_dispatch`'s verdict and exit rule, `_print_dispatch`'s three cases
* `docs/spec/product-spec.md` §9.6 — **FR-163**, rewritten to state the trigger as the
  session's outcome
* `[S19]` — `pi`'s CLI and session-record surface, measured at 0.85.1
