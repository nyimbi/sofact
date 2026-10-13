# 0042 — A module's Definition of Done is derived from its oracle's shape

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-093, FR-090, FR-136, FR-094, FR-088, FR-007, §7.1, §7.3, §8.4;
  [ADR-0025](0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md)

## Context

**FR-093** is the last requirement in §7.2 with nothing behind it:

> Each module must have **completion criteria** (its Definition of Done) — the user's
> "determine what a completed module should do." This is the contract (§7.3) and it is
> the precondition for P5. **A module without completion criteria is not eligible to be
> built.**

The roadmap audit recorded it as `completion_criteria` appearing nowhere in `src/` or
`tests/`. §7.3's module-contract YAML lists the field, so the requirement's own shape
invites a per-module authored field.

That invitation is the trap. A clause already carries an `OracleDeclaration`, and its
`oracle_class` *is* the clause's shape of proof: a `PROPERTY` clause is checked by
property tests, a `SCHEMA` clause by interface conformance. An authored Definition of
Done would be a second statement of the same condition, in prose, written by hand, and
the two would drift — invisibly, because both would read as plausible English. The
factory would then dispatch P5 against a DoD that disagrees with the oracle the verifier
will apply, which is worse than having no DoD: it is a DoD that looks authoritative and
is wrong.

`planner.py` already held the derivation without knowing it. `_EXIT_EVIDENCE` maps every
`PlanStepKind` to the conditions the session must leave behind — "interface conformance
passes for every declared stub", "property tests for this clause pass at >= 10000
generated cases" — and `_STEP_FOR_ORACLE` maps every `OracleClass` to a step kind. The
composition of the two is FR-093's Definition of Done, already written, already the thing
P5 is handed.

## Decision

1. **The criteria are derived, never authored.** `decomposition.completion_criteria(clause)`
   returns the conditions for the module that clause becomes. §7.3's YAML field is
   satisfied by a derived value; an operator who wants different criteria changes the
   clause's oracle, which is the one place that decision belongs.

2. **The derivation lives in `planner.py` as `exit_evidence_for(clause)`, and
   `decomposition` calls it.** FR-093 says the criteria are "the precondition for P5", so
   the module's DoD and the session's exit evidence are *one statement*. Writing it twice
   — once in the decomposition, once in the plan compiler — is the drift this ADR exists
   to prevent, and the drift would be undetectable because both copies would be correct
   English. `decomposition` imports `planner` (no cycle: `planner` imports `views` and
   `contract`, not `decomposition`).

3. **The step kind is authoritative, not the oracle class.** `exit_evidence_for` returns
   `_EXIT_EVIDENCE[step_kind_for(clause)]`. The two agree today for every oracle class,
   and the docstring says which governs when they do not: the oracle says how the clause
   is *checked* and the step says what the session is asked to *leave behind*, and FR-093
   is a condition on the work.

4. **Empty criteria are refused at the gate, not by the type.** `Module.completion_criteria`
   defaults to `()`. A validator would have made the field required, which would have
   broken every hand-built `Module` in the test suite for no gain — `propose` cannot
   produce an empty set, so the type would be enforcing a precondition the only real
   proposer already meets. The gate check `every_module_has_completion_criteria` fails on
   an empty set and names the modules, which is FR-093's "not eligible to be built" stated
   as a refusal an operator can act on. The check exists for the case the type cannot see:
   a decomposition built by hand, or by a second proposer that dropped the field.

5. **The criteria are part of the decomposition hash.** They are what P5 is handed, so an
   approval has to cover them. Derived from the clause today and therefore stable across
   two proposals — but FR-094 makes revisions normal, and a revision could change a
   module's criteria without touching its interface. An approval that did not cover the
   criteria would describe a module nobody was told to build.

6. **The CLI prints them.** `sofact decompose` emits `done when: …` under each module's
   interface. FR-093's criteria are the precondition for P5, so the operator has to see
   them at the gate they are approving; a Definition of Done that exists only as a JSON
   field is not something anyone can check before the build starts.

## Alternatives refused

1. **An authored `completion_criteria` field on §7.3's module contract, filled in by the
   operator at P3.** Refused: it is a second statement of what the oracle already says.
   The spec's own §7.3 YAML invites it, and the invitation is the reason this ADR is
   written down — the field exists in the spec, and a reader implementing it literally
   would produce the drift. The derived value *is* the field's content; what is refused is
   authorship of it.

2. **A per-module-class DoD table** (one Definition of Done per `ModuleClass` G1–G8).
   Refused: the class is a heuristic over the clause's keywords (`CLASS_MARKERS`, and the
   module docstring calls it "deliberately crude and visible"), so keying the DoD to it
   would key a precondition of P5 to a guess. The oracle class is not a guess — it is
   declared in the contract and is what the verifier will apply.

3. **Make the field required by a validator.** Refused for the reason in decision 4: it
   enforces a precondition the only proposer already meets, at the cost of every
   hand-built `Module` in the tests, and it cannot see the case that matters — a
   *decomposition* whose modules are individually well-formed but collectively missing a
   DoD is not constructible either, so the refusal belongs where the operator reads it.

4. **Copy `_EXIT_EVIDENCE` into `decomposition.py`** rather than importing
   `planner.exit_evidence_for`. Refused: two copies of one condition drift, and this is
   exactly the failure the requirement is about. It also inverts the dependency —
   `planner` compiles a *contract* into sessions and knows nothing about modules, so a
   module-shaped copy would have to be re-derived there anyway.

5. **State the criteria as "the oracle passes", one line for every module.** Refused:
   that is the *check*, not the completion criteria. FR-093's examples distinguish them —
   a property clause is done when property tests pass **at >= 10000 generated cases**,
   which is a statement about the work, and the oracle only says the property holds.

## Consequences

- **FR-093 is enforced rather than asserted.** Two canaries confirm the tests are scoped
  to the requirement: replacing the gate's `undefined` computation with `()` fails
  `test_a_module_with_no_completion_criteria_fails_the_gate`; removing
  `completion_criteria=completion_criteria(clause)` from `propose` fails 7 tests across
  four classes, including two that reach the plan compiler through the service — so the
  derivation is load-bearing at the gate, in the hash, and downstream.

- **A module's DoD and its session's exit evidence cannot disagree**, because they are one
  function. `test_the_criteria_match_what_the_plan_asks_of_the_session` pins the two ends
  together by compiling a real plan and comparing the values.

- **The criteria are only as good as the oracle class.** A clause whose oracle is
  mis-declared gets a Definition of Done that is wrong in the same way its verification is
  wrong — which is the correct coupling: the DoD is a statement about what will be
  checked, and a factory that promised something other than what it checks would be
  promising a different thing. FR-007's oracle-strength work is where that risk is
  managed, not here.

- **`_EXIT_EVIDENCE` is now load-bearing for two requirements.** A future edit to a step
  kind's exit evidence changes every module's Definition of Done, and
  `test_the_criteria_match_what_the_plan_asks_of_the_session` is what makes that a
  deliberate change rather than a silent one. This is the cost of decision 2 and it is the
  right side of the trade: one statement that can be changed in one place beats two that
  can drift apart.

- **§7.3's YAML is now satisfiable by a derived value**, and a deployment that wants to
  *check* an operator-supplied module contract against it has something to check against.
  Nothing consumes an authored contract file yet.

## Evidence

- `src/sofact/views.py` — `Module.completion_criteria`, defaulting to `()`.
- `src/sofact/planner.py` — `exit_evidence_for(clause)`, exported; the composition of
  `_STEP_FOR_ORACLE` and `_EXIT_EVIDENCE`.
- `src/sofact/decomposition.py` — `completion_criteria(clause)`, exported; `propose`
  populates the field; the `every_module_has_completion_criteria` gate check; the criteria
  added to `decomposition_hash`.
- `src/sofact/cli.py` — `done when: …` under each module in `sofact decompose`.
- `tests/ci/test_decomposition.py` — three tests in `TestTheProposal` (every module has a
  DoD; the four oracle classes yield four distinct conditions, which fails if the
  derivation collapses to a constant; the criteria equal the plan step's exit evidence),
  one in `TestTheGateRefuses`, one in `TestTheHashNamesTheArtefact`, and the check-name
  set in `test_the_gate_never_claims_to_judge_the_architecture` widened by one.
- `tests/ci/test_cli.py` — `TestTheModuleDefinitionOfDone` (2 tests): the criteria and the
  check both reach the operator's terminal.
- **Two canaries**, each with the target string asserted present before the patch and the
  file restored from `/tmp/decomposition.py.bak` rather than from git:
  (a) `undefined = tuple(...)` → `undefined = ()` failed 1 test;
  (b) the `completion_criteria=` keyword removed from `propose` failed 7.
- `tests/ci` at this commit: **989 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

- FR-093 (completion criteria, the refusal), FR-090 (the declared interface), FR-136 (the
  plan compiler), FR-094 (revision and the hash), FR-088 (traceability), FR-007 (oracle
  strength), §7.1 (architecture has no oracle), §7.3 (the module contract), §8.4 (the
  canonical session shape)
- [ADR-0025](0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md) — the
  gate this check joins, and the interface-count metric beside it
- [ADR-0027](0027-a-declared-surface-is-diffed-in-both-directions-and-a-claim-is-not-a-discharge.md)
  — why SoFact states obligations rather than invented signatures, which is why the
  criteria are conditions rather than commands
- §8.4's canonical session shape, whose per-step exit evidence is what the criteria are
