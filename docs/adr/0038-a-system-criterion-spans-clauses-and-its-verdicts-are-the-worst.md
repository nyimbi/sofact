# 0038 — A system criterion spans clauses, and its verdict is the worst one

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-115, FR-116, FR-078, FR-081, FR-083, FR-084, FR-088, FR-111,
  FR-112, FR-114, FR-006, FR-061, ADR-0025, ADR-0027;
  [ADR-0036](0036-a-research-budget-is-per-clause-and-its-three-caps-are-not-enforced-alike.md)

## Context

§10 states six requirements and P7 implemented four. FR-115 asks that "the assembled
system satisfy the system model (§6.3) structurally — every declared entity,
relationship, and interface present and conforming", and FR-116 that integration "run
system-level acceptance criteria from P2 that no single module can satisfy". Both were
recorded as **Not built**, and the report named them on every run through
`not_implemented` — which is honest, and is also the state in which a green line reads
as "P7 passed" while two of its six requirements were never attempted.

The roadmap blocked both on P2, and that block lifted when `Specification` landed:
`SystemEntity` already carried `clause_ids`, and `Module` already carried the clauses it
exists to satisfy. What was missing was the two types and the two checks.

Four things about the requirements decide the design.

**FR-115 says "present", and the cheap way to test presence is a text search.** Look for
the entity's name in the module's source and call it present. That fails open on exactly
the entities that matter: an entity called `id`, `job` or `entry` occurs in unrelated
lines, so a specification that references nothing passes. `SystemEntity.clause_ids`
exists to avoid this (its own docstring says so), and the check has to use it.

**"Structurally" is a claim about declarations, not about behaviour.** A relationship is
"two entities interact"; no artefact in the log describes an interaction, so a check that
claimed to conform one would be reporting a decision it did not make. The requirement's
own word is *structurally*, and the honest reading is the one the declarations support.

**FR-116's criteria validate the decomposition, not the modules.** A criterion over one
clause is that clause's module's job and P6 already checks it. The criteria FR-116 asks
for are the ones that span modules, because composition is the claim a decomposition
makes and can get wrong — and no module's own verification can catch it. That makes
"spans more than one clause" part of the criterion's *definition*, not a validation
nicety.

**A criterion over clauses needs a verdict per clause, and there is more than one
report.** P6 records a report per module. A criterion whose clauses two modules own
therefore has two sources of evidence, and the choice between them decides whether the
check can be trusted.

## Decision

**An entity is present when some module owns one of its clauses; a system criterion is
satisfied when every clause it spans carries a satisfied verdict; a clause's verdict is
the worst it has received.**

1. **`SystemCriterion` is a type, and it spans at least two clauses.** `id`, `statement`,
   `criterion`, `clause_ids`; `_spans_more_than_one_module_can_own` refuses one clause and
   refuses a clause named twice. The floor is in the type rather than in the check because
   a one-clause criterion is not a weaker system criterion — it is a different thing
   wearing the name, and a check that accepted it would report a module's own obligation
   as a validated decomposition.
2. **`Specification.system_criteria` defaults to `()` and validates its span.** Every
   clause a criterion names must be one the contract has, checked once at P2 rather than
   per integration pass: a criterion over a clause no requirement traces to can never be
   satisfied, and finding that out at P7 would be finding it out after the build.
3. **FR-115's presence test is a set comparison over declarations.** An entity is present
   when `module_for_clause` maps one of its `clause_ids` to a module. Never a text search
   — see the Context. The map is built from the **decomposition**, not from the
   dispatches: a module that was never dispatched is still a module the system is missing,
   and reading ownership off what happened to be built would make a plan that skipped half
   its modules report a conforming system.
4. **FR-115 has two finding kinds, because the two failures have different repairs.**
   `UNOWNED_ENTITY` — no module owns the clause, so the model and the decomposition
   disagree; `MISSING_ENTITY` — the map names a module the decomposition does not declare,
   so the graph is stale. Both carry `modules=()`, and that is a **real answer**: the
   repair is a specification change, and FR-114 forbids widening a local failure into a
   platform rebuild. A finding with no modules is scoped to nothing, not to everything.
5. **Relationships and invariants are declared and not conformed, and the check says so.**
   Stated in `uncovered` on every run, including a passing one. The alternative —
   conforming a relationship by checking that both entities exist — would report the
   conjunction of two facts as the fact itself.
6. **A criterion is satisfied only when *every* spanned clause carries `SATISFIED`.** One
   violated or unverified clause fails the whole criterion. A criterion is a claim about
   composition, so it cannot survive one of its sides failing.
7. **A clause with no verdict counts as `INSUFFICIENT`, not as satisfied.** The one wrong
   default is the one that fails open, and "nobody checked this" read as "this passed"
   would make a criterion over unchecked work report green. `INSUFFICIENT` and `VIOLATED`
   produce the same *finding kind* and different *detail*, because a clause nobody could
   check and a clause that was checked and failed are different problems.
8. **The verdict per clause is the worst across every report in the log.** Rank
   `SATISFIED < INSUFFICIENT < VIOLATED`; worst wins. Latest-report-wins would make a
   criterion's outcome depend on dispatch order, and a criterion that failed on the first
   module and passed on the last would read as passing — the composition failure the
   criterion exists to catch. Worst is also the honest reading of a history: the map has
   no ordering, so it reports the strongest evidence against the claim.
9. **`UNSATISFIED_SYSTEM_CRITERION` names the modules that own the failing clauses**, so
   the finding is repairable within FR-114's minimum set. A criterion whose clauses are
   owned by two modules produces a finding scoped to those two and to nothing else.
10. **`integrate` takes `model`, `criteria` and `verdicts` as parameters, not reads.** The
    service holds the log; this module holds none. Absent `model` or `criteria` is the
    honest state of a specification that declared neither, and FR-115/FR-116 then stay in
    `not_implemented` — the same distinction FR-112 draws between an empty diff and no
    diff. They are optional in that sense and **not** skippable in the other: a project
    whose P2 declared a model and criteria has them conformed on every pass, with no flag
    to turn it off.
11. **P2's gate reports the criteria count and never fails on its absence.** A
    `system_criteria_reported` check, always passing, whose detail says either how many
    criteria span how many clauses or that none were declared and what that means. An
    honestly-modular system has no system-level criterion; failing it there would make a
    specification red for being modular, and a gate that cannot pass is one its operator
    learns to bypass.
12. **`sofact specify --criterion "STATEMENT | CRITERION | INDEX,INDEX"`** carries the
    operator's criteria, by clause *index* like `--entity` (the operator reads a numbered
    clause list). A bad index, a missing separator and a one-clause criterion each arrive
    as a sentence rather than a traceback.

## Alternatives refused

- **Test entity presence by searching the source for the entity's name.** Refused in
  decision 3. It passes on a specification that implements nothing, for exactly the
  entities whose names are common words — the failure `SystemEntity.clause_ids` was
  introduced to avoid.
- **Let a criterion span one clause.** Refused in decision 1: FR-116 asks for the criteria
  *no single module can satisfy*, and a one-clause criterion is a module's own obligation
  that P6 already checks. Accepting it would let a decomposition validate itself against
  criteria it satisfies by construction.
- **Treat an absent verdict as satisfied.** Refused in decision 7. It is the default that
  fails open, and the one a check can least afford.
- **Take the latest verdict per clause.** Refused in decision 8: it makes the answer depend
  on dispatch order and lets a composition failure be laundered by re-verifying one side.
- **Fail the P2 gate when no criteria are declared.** Refused in decision 11. An honestly
  modular system has none, and a gate that fails on a legitimate outcome teaches its
  operator to bypass it.
- **Attribute an unowned entity to the whole plan.** Refused in decision 4. FR-114's whole
  content is the size of the repair set, and a missing module is repaired by changing the
  specification — no module exists to blame.
- **Run the criterion as a command.** Refused: a system-level criterion is not in the
  contract's oracle set, so there is no command to run. The check states this in
  `uncovered` rather than implying it ran something. Wiring an oracle set for criteria is
  a refinement to make when the contract can carry one.
- **Derive `module_for_clause` from the dispatches.** Refused in decision 3: a module that
  was never dispatched is a module the system is missing, and the check would then report a
  plan that skipped half its modules as conforming.

## Consequences

- **FR-115 and FR-116 move from Not built to Implemented**, and §10 has no unbuilt
  requirement. `not_implemented` shrinks to FR-112 for the default project, which is the
  one gap that is a *producer* limitation rather than a specification one — no proposal
  derives a machine-readable surface, because nothing in a clause is a signature.
- **A project with no approved specification still reports both as unimplemented.** The
  checks run and discharge nothing; nothing about the default path changes.
- **`check_integration` reads the approved specification**, and gains
  `_worst_verdict_per_clause`. A specification declared at P2 is therefore conformed on
  every later integration pass, including passes that follow a repair.
- **`sofact specify` gains `--criterion` and prints the criteria it accepted**, so the
  operator sees the span before approving the gate.
- **`docs/research/system-model/` gains a second reader.** The model was written for P3 to
  decompose against; FR-115 makes it something P7 checks, which is the point at which it
  earns its maintenance cost.

## Evidence

- `src/sofact/views.py` — `SystemCriterion` (with `_spans_more_than_one_module_can_own`),
  `Specification.system_criteria` and `_system_criteria_span_declared_clauses`, the three
  `IntegrationFindingKind` members (`MISSING_ENTITY`, `UNOWNED_ENTITY`,
  `UNSATISFIED_SYSTEM_CRITERION`), and the `IntegrationFinding` docstring's account of why
  `modules=()` is an answer.
- `src/sofact/integration.py` — `check_model_conformance`, `check_system_criteria`,
  `integrate`'s three new parameters, the two new `IntegrationCheck` entries and their
  `uncovered` lines.
- `src/sofact/specification.py` — the `system_criteria` parameter and the
  `system_criteria_reported` gate check.
- `src/sofact/service.py` — `check_integration`'s read of the approved specification and
  `_worst_verdict_per_clause`.
- `src/sofact/cli.py` — `_criterion_option`, `--criterion`, `_NOT_IMPLEMENTED_WHY` (the
  old message said the model "does not exist as a type", which stopped being true), and
  the criterion block in `_print_specification`.
- `tests/ci/test_integration.py::TestTheSystemModelConformance` — 6 tests; and
  `::TestTheSystemCriteria` — 8 tests, including the two type-level refusals and the
  P2 gate's two states.
- `tests/ci/test_cli.py::TestTheIntegrateVerb` — 5 tests: FR-116 open with no criteria,
  FR-116 closed once one is declared, the one-clause refusal, the out-of-range index
  refusal, and the printed proposal.
- **Canaries**, each with the target string asserted present before the patch and the file
  restored from `/tmp/integration.py.bak` rather than from git:
  - `check_model_conformance`'s `if not owners` short-circuited with `and False` — the
    unowned-entity tests failed (`test_an_entity_no_module_owns_is_a_decomposition_defect`,
    `test_a_model_with_an_unowned_entity_fails_the_report`).
  - `check_system_criteria`'s verdict lookup defaulted to `SATISFIED` — the absent-verdict
    test failed (`test_a_clause_with_no_verdict_is_insufficient_rather_than_satisfied`),
    which is the canary that matters most: it is the one that shows the fail-open default
    is caught rather than silently passing a criterion over unchecked work.
- `tests/ci` at this commit: **859 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

- FR-115 (the assembled system satisfies the model), FR-116 (system-level criteria),
  FR-078/FR-083 (the model as the source for interfaces), FR-081 (every entity is
  referenced), FR-084 (specification drift), FR-088 (traceability), FR-111/FR-112/FR-113
  (the other P7 checks), FR-114 (minimum violating set), FR-006 (stale evidence),
  FR-061 (the gates), NFR-024.
- [ADR-0025](0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md) — why `Module.interface` is prose,
  and therefore why FR-112 remains open.
- [ADR-0027](0027-a-declared-surface-is-diffed-in-both-directions-and-a-claim-is-not-a-discharge.md) — the check FR-115
  sits beside, and the `discharged` distinction both use.
- [ADR-0036](0036-a-research-budget-is-per-clause-and-its-three-caps-are-not-enforced-alike.md) —
  the prior unit, and the same "a measurement is not a failure" rule as decision 11.
