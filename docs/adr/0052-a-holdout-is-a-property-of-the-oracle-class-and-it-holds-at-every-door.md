# 0052 — A holdout is a property of the oracle class, and it holds at every door

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-106, FR-017, FR-103, FR-059, FR-016, FR-019;
  [ADR-0050](0050-coverage-is-a-conjunction-and-the-debt-and-the-cap-are-one-measure.md),
  [ADR-0022](0022-a-refutation-is-a-work-order.md)

## Context

FR-106 requires that "example-based oracles supplied by the operator must be
**held out** from the builder (FR-017)". FR-017 is sharper: holdouts "must
**never** be included in any context window shown to a producer. Leakage of a
holdout into producer context is a lane-halting defect." §13's R8 names the
residual risk and the fix in one line — "context assembly must be a permission
boundary, not a prompt instruction".

The roadmap row read "Not built — no holdout mechanism", which was true and
understated the problem. The factory had no holdout, and it also had the exact
defect FR-106 exists to prevent, reachable by two routes:

1. **The planning door.** `_oracle_lines` (`planner.py:248`) renders every
   oracle's `description`, `command_hint` and `expect_stdout_contains` into the
   producer's `verification_surface`. An operator's example oracle — the exact
   expected output and the exact command — therefore appeared verbatim in the
   goal text, while the *same goal's* `boundaries` said "Do not read the oracle
   corpus, holdout scenarios, or factory credentials (FR-059)". The prompt
   forbade reading what the prompt itself printed.

2. **The repair door.** `_command_output` (`verification.py:130`) builds a
   violated verdict's reason as `f"stdout did not contain {required!r}"`, and
   `refutation_diagnosis` (`planner.py:677`) joins that reason into the repair
   goal's `outcome`. Closing door 1 alone would have left the value arriving one
   phase later, in the goal authored *from the failure*.

A probe confirmed both: a contract with an EXAMPLE oracle carrying
`command_hint="pytest tests/test_report.py"` and `expect_stdout_contains="TOTAL 42"`
compiled to an operation goal containing both strings, and the repair goal for the
same clause carried them again through the diagnosis.

## Decision

**The holdout is a property of the oracle class, stated once on
`OracleDeclaration`, and applied at every door that renders the oracle into
producer context.**

1. **`OracleDeclaration.held_out` is derived, not stored.** It returns
   `self.oracle_class is OracleClass.EXAMPLE`. A boolean field defaulting to
   `False` would leave the leak open on every oracle constructed without it — a
   control that exists and is never applied — whereas a derivation is correct at
   every site that reads it. This is ADR-0050's argument for `covers` applied to
   a second predicate.

2. **The class *is* the provenance, and that is FR-103's table rather than an
   inference.** Rank 6's source column reads "operator-supplied cases", so an
   example oracle is the operator's by definition. No `supplied_by` field was
   added: it would be a second statement of what the class already says, and the
   two would drift the first time one was set without the other.

3. **What is withheld is the case, not the obligation.** The description, the
   command and the expected output are held back; the clause statement, the
   oracle class and the rank are not. A producer told the obligation and the
   strength can build to the intent, which is what FR-106 says the example is a
   proxy for. One told the expected output builds to the sample, which FR-103's
   own strength column calls "sample, not coverage".

4. **The line names the holdout rather than going silent.** A producer shown only
   "example oracle (rank 6)" would read a check it cannot see and might conclude
   the factory lost the detail. The rendered line says the case is held out and
   cites FR-106.

5. **Ranks 6 and 7 are both weak and only 6 is held out.** FR-103's source column
   gives a golden file as "output of a reference run" — usually the producer's own
   recording — and withholding it would hide the artefact the producer is asked to
   reproduce. FR-106 says "example-based" and means it.

6. **The repair door suppresses the value and keeps the fact.** A held-out
   oracle's violated reason states that stdout did not contain the operator's
   required output and says where both halves live — the expected value on the
   clause's oracle, the observed stdout in the clause's evidence — without quoting
   either. The verdict is unchanged: still `VIOLATED`, still scoped to the clause.

7. **The premise is asserted, not commented.** `suggest_oracle` asserts that its
   suggestion is not held out. The property's soundness rests on the factory
   manufacturing no EXAMPLE oracle; an assertion is what keeps that true rather
   than assumed.

## Consequences

**Both doors are closed, and the tests fail at each independently.** The planner
tests assert the payload is absent from every step that covers the clause, with a
control arm proving the same payload *is* printed for a GOLDEN oracle — otherwise
"absent" would be indistinguishable from a renderer that prints no oracle line for
any class. `TestTheHoldoutSurvivesTheRepairDoor` drives the real composition
(`verify` → `refutation_diagnosis` → `repair_goal` → `render`) rather than
inferring it from two unit tests, because FR-106 is a claim about the payload and
not about a function.

**The `bootstrap` step is excluded from the assertion deliberately.** It covers no
clause and renders no oracle line, so asserting against it would pass without the
fix — a canary that never ran. `_steps_covering` selects the steps that actually
carry the clause and asserts the selection is non-empty.

**A holdout that silenced the failure would be a worse defect than the leak.** The
producer has to be able to act, so the reason names the clause and the kind of
failure. The operator loses nothing: the oracle is in the contract, which is
hashed (FR-139) and which the producer cannot edit.

**This is one requirement of the confinement family, not the family.** FR-016
(no read access to holdouts, no write access to oracle artefacts) and FR-019
(isolation enforced by the deployment boundary) remain unbuilt and are blocked on
ADR-0005's refusal of containers. What this closes is the *context-assembly* half
of R8, which is the half the codebase can enforce without a deployment boundary —
and R8's own remedy line is exactly that: context assembly as a permission
boundary rather than a prompt instruction. FR-106's remaining half — holdouts
*existing* for every lane above L2, versioned — is not built, because nothing
manufactures an oracle yet (FR-103, blocked on D5's target language).

## Evidence

- `TestAnOracleIsHeldOutOrNot` (7 tests) in `tests/ci/test_views.py`;
  `TestAHeldOutOracleIsNamedAndNotDescribed` (6 tests) and
  `TestTheHoldoutSurvivesTheRepairDoor` (2 tests) in `tests/ci/test_planner.py`;
  two tests in `tests/ci/test_verification.py`.
- Canaried three ways, each asserting its target string was present before
  mutating and reverted from a file backup: the planner branch dropped (4 fail),
  the verdict-reason branch dropped (3 fail), the predicate forced to `False`
  (8 fail, including the property test itself).
- `ruff check` and `ruff format --check` clean; `pyright` 0 errors; full
  `tests/ci` **1181 passed**.
