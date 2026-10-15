# 0063 — The hacker's verdict is the verifier's, and a fixer's word is not a clearance

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** FR-012, FR-013, FR-014, FR-015, FR-107, FR-108, FR-138, NFR-024, ADR-0053, ADR-0054, ADR-0062

## Context

FR-012–015 is the row the roadmap has carried as **Not built** the longest, and it was
carried honestly: ADR-0053 built the *oracle-side* instrument FR-107 asks for — a
must-fail canary that runs every probeable oracle against an empty workspace and reports
one that is satisfied there — and that instrument is what FR-012's loop would point at. The
loop itself did not exist.

FR-012 states the loop's purpose in one sentence that decides the whole design:

> The **hacker** role must attempt to obtain a passing verdict on a lane's output *without
> solving the task* — editing tests, hard-coding expected values, special-casing fixtures,
> disabling assertions, over-fitting to the sample.

Four further things the requirement fixes, each of which constrains the implementation more
than it first appears:

- **FR-013** — every demonstrated exploit must produce a fixer action that closes it, *and*
  the exploit must be retained as a permanent regression case. Two halves, and the second is
  the one that gets dropped.
- **FR-014** — the audit is sampled 1-in-N (N configurable) at or below L3, **100%** above
  it, and "the sample rate must increase automatically when an exploit is found."
- **FR-015** — the exploit discovery rate is a first-class metric, "should trend to zero and
  stay there", and "a non-zero plateau means **the lane** is not actually verified."
- **§4.4's design note** — sample rates are "a throughput/assurance tradeoff made explicit
  and configurable, never implicit."

## Decision

### The measurement is the verdict's movement, read by the real verifier

The attacked oracle is run by the real `OracleRunner` and its output read by the real
`verify()`, exactly as at P6. The alternative — deciding "satisfied?" locally from the exit
code — would be a manufactured *judge*, which is the same defect as a manufactured oracle
one level up: a component that agrees with itself.

`_score_attempt` therefore compares the attacked verdict against the baseline verdict, and
an attempt counts as an exploit only when a violated oracle became a satisfied one.

### Three of FR-012's five techniques are source transforms, and two are named as not attempted

`EDITED_TEST`, `DISABLED_ASSERTION` and `SPECIAL_CASED_FIXTURE` are mechanical rewrites of
a file's text. `HARDCODED_EXPECTED` and `OVERFIT_TO_SAMPLE` require a model to invent code
that satisfies an intent without implementing it, and inventing that is precisely what the
factory must not do unattended.

They are reported as `NOT_ATTEMPTED` via `UNADDRESSED_TECHNIQUES`, never silently dropped.
The distinction matters because FR-015's rate is over the techniques actually attacked: a
reader who assumed all five were covered would read a zero as "nothing gets through" rather
than "nothing tried the other two", which is the same defect as an unrun oracle reading as
a satisfied one.

### The honest tree runs first, and it decides what can be attacked at all

A hacker's job is to obtain a *passing* verdict. Against an oracle that already passes
honestly there is nothing to obtain, so a clause whose honest verdict is `SATISFIED` yields
`NOT_ATTEMPTED` — the audit learned nothing — rather than `HELD`. `HELD` would credit the
oracle with resisting an attack that was never meaningful, and would put a clause nobody
attacked into FR-015's denominator.

### `passed` is `not exploited`, and a fixer's "closed" is not a clearance

This is the design decision the first test run forced, and it is FR-138 applied one level
up. FR-013's fix is a *claim* that the exploit is closed, and **nothing in this pass
verifies it** — the verification is the next audit, which attacks the rewritten oracle. So
a pass that found one exploit and wrote one fix saying "closed" still reports
`passed = False`, and `exploits_unclosed` is the separate signal saying whether anything is
still open.

A gate that treated a fixer's word as a clearance would be accepting the producer's own
declaration, which is the whole of what FR-138 forbids. The first draft had `passed` read
the fixes; the test caught it, and the fix went into the source rather than the test.

### Sampling is a deterministic stride, and the escalation is read off the log

`sample_decision` is `ordinal % N == 0` rather than a random draw. Deterministic sampling is
not a weaker instrument here: FR-014's purpose is coverage *over time*, and a stride
guarantees that every Nth change is examined while a random draw only makes it likely. A
random sampler also makes the rate irreproducible from the log, which is what FR-015's trend
is read from.

`effective_sample_floor` reads the prior passes for the contract and returns 1 once an
exploit has been found. Three details are load-bearing:

- **The most recent pass that attacked anything decides it.** One pass, so the escalation
  relaxes — a rule that never relaxed would make the first exploit a permanent full-rate tax
  on the lane, which is a throughput decision FR-014 does not make.
- **A sampled-out pass is skipped, not read as clean.** It exploited nothing *because it
  attempted nothing*, so letting it de-escalate would restore the sample on the strength of
  an audit that never ran. The walk tests `attempted`, never `exploited` alone.
- **The escalation destination is a constant and the floor is a parameter.** FR-014 makes N
  configurable and supplies no number; it makes the increase automatic and supplies no
  number either. So the relaxation target is a deployment's throughput choice and the
  escalation destination is what the requirement says must happen.

### The lane is recorded, because FR-015's sentence names one

FR-015 says the rate is per lane and its plateau "means **the lane** is not actually
verified", so a report that did not carry a lane would make the requirement's own sentence
uncomputable from the log. `AdversarialAuditReport.lane` is the *declared* lane the caller
sampled for, recorded rather than derived: deriving it from the attempts would pick the
lanes of whatever clauses happened to be probeable and report a per-clause rate under a
per-lane name. `None` is a real state — an audit over a whole contract has no lane — and is
how the report declines to attribute its rate to one.

### A rate over zero attempts is `None`, not `0.0`

FR-015's *target* is zero, so a zero over nothing would print the target state for a lane
nobody attacked — NFR-024's forbidden reading. `exploit_rate` returns `None` when
`attempted` is empty, and `discharged` returns `()` so the pass claims nothing.

### The instrument is wired, because one only its own tests can reach is not built

`LedgerKind.ADVERSARIAL_AUDITED`, the fold arm, `ProjectState.adversarial_audits` (appended,
never keyed — FR-015's subject is a *trend*, so the series is the datum and latest-wins would
destroy the plateau the requirement exists to make visible), `latest_adversarial_audit`,
`FactoryService.adversarial_audit()`, and `sofact audit --adversarial`.

The service derives the floor from the log rather than taking it from the caller, and keys
it to the contract: a different contract's exploit says nothing about these oracles, and a
shared escalation would be one goal's defect taxing another goal's throughput.

### `EDITED_TEST` exploits every violated oracle, and that is not a bug

The technique replaces the whole file the oracle's command runs, so it defeats any oracle
that was violated. A hacker with write access to the test file always can. What
`DISABLED_ASSERTION` and `SPECIAL_CASED_FIXTURE` measure is resistance to the subtler
rewrites, and the tests assert *which* techniques got through rather than how many.

## Evidence

Measured on 2026-10-15 against this tree:

1. `pytest -q tests/ci/test_adversarial.py`: **42 passed**.
2. `pyright` over the tree: 0 errors, 0 warnings, 0 informations. `ruff check` clean;
   `ruff format --check` clean over 73 files.
3. Six canaries on the instrument, all watched failing and reverted from a file backup with
   `cmp -s` confirming byte-identical: the exploit predicate, the sample stride, the
   unattackable branch, the rate's `None` over zero attempts, `passed` reading the fixes, and
   the baseline branch.
4. Three canaries on the wiring: removing the fold's `case` arm fails three of four seam
   tests; removing the `floor=` argument from the service fails exactly
   `test_an_exploit_escalates_the_next_pass_through_the_service`; deleting the skip clause
   in `effective_sample_floor` fails exactly
   `test_a_sampled_out_pass_neither_raises_nor_relaxes`.
5. **Two design defects were found by the first test run and fixed in the source**: `passed`
   reading the fixes (above), and both "no attack staged" branches reporting `INCONCLUSIVE`
   where the correct outcome is `NOT_ATTEMPTED` — an unattacked clause must not enter FR-015's
   denominator.

## Consequences

1. **FR-012–015 moves from Not built to Partly.** The loop, the fixer, the sampling rule
   with its escalation, the lane, the rate and the trend series are built. What is not built
   is the two techniques that need a model to invent code, and they are reported as
   not attempted rather than claimed.
2. **The rate is a measurement and not a gate.** Nothing reads it to change a ceiling;
   FR-015's target is a direction, and §20.3 item 4 records that no rate has been calibrated.
3. **A fixer's word does not clear a pass**, so the CLI exits non-zero on `passed` and prints
   the unclosed count beside it — the operator sees the non-zero exit and what was done about
   it without the two being the same signal.
4. **`AUDIT_SAMPLE_FLOOR = 3` is declared rather than calibrated**, and the report states the
   N it used beside every rate it prints, because a rate computed under 1-in-3 and one under
   1-in-30 are not comparable.
5. **The instrument is reachable from the product**, so it does not repeat FR-159's defect —
   a correct instrument with no call site is a capability nobody can reach. The same defect
   is still live in `sofact.mutation`'s call graph and is not fixed here.

## What this does not do

1. **It does not attempt the two model-needing techniques.** `HARDCODED_EXPECTED` and
   `OVERFIT_TO_SAMPLE` are named in `UNADDRESSED_TECHNIQUES` and every report can state the
   gap. Closing them needs a model in the loop and a decision about what it may write
   unattended.
2. **It does not trend the rate across contracts.** `adversarial_audits` is the series and
   `exploit_rate` is per pass; a per-lane trend over history is a reading rule nothing
   computes yet, and FR-015's "should trend to zero and stay there" is a direction the data
   now permits rather than a chart the product draws.
3. **It does not verify a fix.** FR-013's `closed` is recorded and reported, and the
   verification is the next pass. A product that verified it in the same pass would be the
   fixer grading its own work.
