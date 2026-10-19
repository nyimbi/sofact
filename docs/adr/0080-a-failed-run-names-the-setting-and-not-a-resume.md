# 0080 — A failed run names the setting, and not a resume

- **Status:** Accepted
- **Date:** 2026-10-19
- **Related:** FR-172, FR-145, FR-148, FR-173;
  [ADR-0075](0075-a-refusal-names-the-cause-the-response-shows.md)

## Context

`DriverTerminal.FAILED` is one member over every exception a driver step raised, and
`DriverRun.next_human_verb` answered all of them with `sofact build --resume`. For a bug in
the factory that is the right instruction: re-running gets you the trace. For a missing
harness binary it is not. A resume re-selects the same action, dispatches to the same
absent executable, and raises the same exception — forever.

ADR-0075 fixed exactly this shape for P0's two `EXHAUSTED` waits and recorded that it had
not been carried to `FAILED`. Its own note says why it stopped there: "whether a resume can
act is a fact about *why* the run failed, and the driver holds it — the same shape as
`awaiting_attestation`". That is the design decision this record makes.

The gap was not hypothetical. Driving a run against a spec whose `argv[0]` is not on
`PATH` produced:

```text
terminal: failed
  detail: research: [Errno 2] No such file or directory: 'sofact-no-such-binary-anywhere'
  next: sofact build --resume
```

Three facts are wrong in that output and only the first is cosmetic. The failure is a
*deployment setting*, not a fault. The verb is one that provably repeats. And the
exception is a bare `FileNotFoundError` — `HarnessBinaryMissing` existed and was raised by
`probe()` alone, so the class the product already had for this fact never reached the
dispatch path.

## Decision

**A `FAILED` run records *what kind* of failure it was, and the verb is read off that
record.**

`DriverFailure` is a closed enum of the configuration faults: `HARNESS_MISSING`,
`HARNESS_RECORD_UNREADABLE`, `SEARCH_UNUSABLE`, `GIT_MISSING`. `DriverRun.failure` carries
one or `None`, and `next_human_verb` returns `DRIVER_FAILURE_VERB[failure]` when it is set.
The resume stays the fallback, and `None` is its honest reading: a bug in the factory is
fixed by a bug report, and guessing a setting would send the operator to change something
that is not wrong.

It is a **field, not a derivation**, for the reason ADR-0075 gives about
`awaiting_attestation`: the exception is the driver's, and a view that re-derived the class
from `terminal_detail` would be parsing prose written for a human — which is the defect
ADR-0075 exists to record, one level up.

`classify_failure` is a table of exception *types* matched with `isinstance`, so a subclass
reads as its base and the set is one thing a reader can see. `LlmUnavailable` is
deliberately absent: `propose-answers` already catches it and reports a wait rather than a
failure, because P0 is a deterministic interrogation a person can answer by hand. A model
failure that reaches `FAILED` came from somewhere else, and naming the endpoint for it
would be a guess.

**The dispatch path now raises the class the product already had.** `HarnessAdapter._invoke`
wraps `create_subprocess_exec` and re-raises `FileNotFoundError` as
`HarnessBinaryMissing`. This is the one launch path every dispatch goes through, so the
naming is applied at the seam rather than at each caller — the same argument
`wrap_argv` gets for the boundary, and for the same reason: a control at one line covers
every child.

## Consequences

- The four verbs are checked against the installed CLI the way `PHASE_PRODUCER_VERB` is,
  and `test_every_failure_names_a_verb_that_is_not_a_resume` walks the whole table, so a
  member added with the fallback fails rather than reading as classified.
- **That check had to be rebuilt before it could be trusted.** Its first body grepped the
  runner's output for two literal sentences — `unexpected extra argument` and `No such
  command` — and click words a bad *flag* `No such option`, so `sofact tui --nonsense`
  passed it. The predicate is now the parser's own verdict: `make_context` on the group,
  then on the subcommand, with `NoSuchOption` and a missing command failing the test and
  `MissingParameter` tolerated because that argument is the operator's to supply. It also
  stopped executing every command: 252 seconds of real dispatch became 1.4 seconds of
  parsing, and the run was never the thing under test.
- **One entry was passing vacuously.** `git --version` is in the table and is not a SoFact
  verb; stripped to `--version` it was answered by the *group's* own version flag. The test
  now filters the table to the entries that open with `sofact` and leaves the git line
  alone, rather than reporting a pass on a line the parser never read as a command.
- `classify_failure` is public. A private name reached a test and pyright refused it, which
  is the rule working: the function is part of the module's contract, so it is exported.
- The `FAILED` terminal keeps its meaning. This does not split it into four members, because
  the *kind* of stop is one thing — a step raised — and only the instruction differs. A new
  terminal member would move the notification subject and every `claims_built` reader for a
  distinction none of them make.
- ADR-0075's second recorded gap is closed; its first was closed by `9ed8bce`
  (`sofact elicit`). Both notes are updated in place rather than deleted, because a record
  of a gap that was later closed is how a reader learns the shape of the class.

## Evidence

**Five canaries, all caught, each reverted from a `cp` backup verified to hold this
version, with `__pycache__` cleared.**

1. `GIT_MISSING`'s sentence replaced with `sofact build --resume` — 1 failed,
   `test_every_failure_names_a_verb_that_is_not_a_resume`.
2. The classifier's `HarnessBinaryMissing` row remapped to `GIT_MISSING` — 2 failed, the
   table test and the end-to-end run.
3. The `FileNotFoundError` re-raise removed — 1 failed,
   `test_a_missing_harness_binary_names_probe_and_not_a_resume`. This is the original defect
   restored, so the test is watching the thing that was wrong.
4. `GIT_MISSING`'s sentence replaced with `sofact frobnicate` — 1 failed on the source-wide
   scan, which reads every module for a verb the CLI does not have.
5. The same sentence replaced with `sofact tui --nonsense`, a *registered* verb with a flag
   it does not take. The scan passed, correctly: `tui` is a real command. The invocation
   gate passed too, and that was the finding — see the second bullet under Consequences.

The third canary is the one that matters most: the end-to-end test failed on its first run,
before any canary, with `failure=None` against a bare `FileNotFoundError`. The gate found a
defect in the fix rather than confirming it. The fifth is the same lesson one level up: a
gate whose *name* claimed the parser accepts the line was matching two strings instead.
