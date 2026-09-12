# 0006 — The verifier cannot reach the executor

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

SoFact separates producing an artefact from judging it. In the limit, the producer is
an autonomous harness that has both the motive and the opportunity to arrange the
evidence it will be judged on: run a weaker command, run it in the wrong directory,
or simply report what it would have liked the command to print.

Verification therefore has to be causally isolated from production — the evaluator
must not be able to influence what it evaluates. Stating this as a rule for
developers does not hold: the rule is invisible at the call site, and the natural
implementation of "verify this clause" is to run the clause.

The specification puts it as FR-038: the verifier must not import executor code.

## Decision

The producer and the judge are **separate modules with a one-way dependency**:

- `execution.py` — `OracleRunner`. Runs commands, records `Evidence`. Has no verdict
  type in scope and could not reach one.
- `verification.py` — `verify`. Consumes `Contract` and `Evidence`, returns a
  `VerificationReport`. **Must not import `execution`, `subprocess`, or anything that
  can start a process.**
- `service.py` is the only module permitted to use both, and it does so to *sequence*
  them — run, then verify — never to fuse them.

The separation is enforced by a test that parses `verification.py`'s imports, not by
convention. It is enforced against imports rather than against behaviour because the
claim is about what the code *can* do; a behavioural test would only show what it
happens to do today.

## Evidence

`tests/ci/test_verification.py::test_verifier_cannot_reach_the_executor` walks the
module's AST and asserts no import names `subprocess` or contains `execution`.

This test was written, failed, and corrected in the same session. The first version
searched the module's *text*, and failed on the module's own docstring — which has to
name `sofact.execution` in order to explain why it is never imported. The lesson is
recorded here because it generalises: **a test that greps prose will fire on the
documentation of the rule it is checking.** Assert on structure.

Supporting properties, all asserted:

- `Evidence` has no trusted `passed` field; the verifier derives the verdict from the
  payload, and every field is type-checked first. An unrecognised shape yields
  `INSUFFICIENT` rather than being coerced — a string `"0"` is not an exit code and a
  boolean is not an integer.
- An oracle with no command raises `OracleNotExecutableError` rather than returning
  a vacuous observation.
- `verify`'s signature is `(contract, evidence)`. There is nowhere to put a claim.

## Consequences

- Verification is a **pure function of the contract and the observations**, so a
  verdict is reproducible from the log alone and needs no live system to re-derive.
- The cost is some duplication of shape knowledge: the verifier must know what a
  `TEST_RESULT` payload looks like without importing the runner that produces it. This
  is deliberate — the two modules agreeing by importing each other is the coupling the
  decision forbids, so they agree by the payload contract in the ledger instead.
- `service.py` becomes the only place where ordering can be got wrong. It is a small
  surface, and `verify_contract` re-reads evidence from the log rather than accepting
  it from the caller, so a caller cannot supply the observations it wants judged.
