# 0051 — O8 is a P7 check, not an oracle class

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-110, FR-090, FR-103, FR-108, FR-112, FR-113, FR-114;
  [ADR-0026](0026-p7-checks-three-of-six-requirements-and-names-the-rest.md),
  [ADR-0027](0027-a-declared-surface-is-diffed-in-both-directions-and-a-claim-is-not-a-discharge.md),
  [ADR-0050](0050-coverage-is-a-conjunction-and-the-debt-and-the-cap-are-one-measure.md)

## Context

FR-110 requires "an eighth oracle class **O8 — Integration**": consumer-driven
contract tests across module boundaries, exercised in P7. The roadmap row read
"`OracleClass` has 7 members; there is no O8", which presents the gap as a missing
enum member.

It is not. Every member of `OracleClass` is a *per-clause* shape of proof:

- it is a field of `Clause` (`OracleDeclaration.oracle_class`);
- `ORACLE_RANK` gives it a rank, and `ceiling_for_rank` turns that rank into a
  ceiling for the contract;
- `_STEP_FOR_ORACLE` maps it to the P5 step kind that discharges *that clause*, and
  `test_the_mapping_is_total_over_the_enum` requires that map be total — "a new
  oracle class must not silently fall through to a default";
- `decomposition.propose` gives each clause exactly one owning module.

FR-110's own justification is that this is the wrong shape for O8: "per-module
verification (O1–O7) **structurally cannot detect cross-module incoherence**, which
is where multi-module systems actually fail." §14's class table agrees — G3 is
"contract tests + schema + **O8 integration**", an oracle *beside* the per-clause
ones — and §23's build order puts O8 at **P7**, not P5.

Adding an `O8` member would therefore have required inventing a P5 session kind for
a P7 check, and would have made `covers` and `ceiling` treat a boundary oracle as
per-clause coverage it is not. That is the wrong repair, and it would have moved two
other decisions to accommodate it.

## Decision

**O8 is a P7 check. `OracleClass` keeps its seven members, and FR-110 is discharged
by a check in `integration.py` that runs in P7 alongside the others.**

1. **The check is `check_boundary_contracts`, reported as the `boundary_contracts`
   row.** It asks the one question neither neighbour asks: does the name a consumer
   reached for across a *declared* edge appear on the producer's *declared* surface?

2. **Only declared edges are examined.** An undeclared edge is already FR-113's
   finding, and reporting it here too would name one defect twice under two
   requirement ids — the mistake `check_model_is_the_interface_source` exists to
   avoid.

3. **A new finding kind, `UNSATISFIED_BOUNDARY_CONTRACT`.** Its `modules` is both
   ends of the boundary, because the finding is a disagreement between two
   declarations and either one may be the one to change. A repair scoped to one end
   alone would be a guess about which declaration is wrong.

4. **A producer declaring no surface is uncovered, not conforming.** The check is
   gated on `declared_surfaces` exactly as FR-112's is, and the report says which
   state the project is in rather than passing vacuously.

5. **`FR-110` joins `INTEGRATION_REQUIREMENTS`.** It is not one of §10's numbers, but
   the list is already "every requirement P7 can discharge" rather than §10's set —
   FR-026, FR-083 and FR-097 are there on the same reasoning.

6. **The CLI's not-implemented sentence names it and says why.** FR-110 is open by
   default (no module declares a surface), so a report that printed it with no reason
   would be a number the operator cannot act on.

## Consequences

**The gap FR-110 names was real, and it is now closed at P7.** A consumer could
import a declared dependency and call a name that module never promised, and every
existing check passed: FR-113 sees a declared edge, FR-112 compares the producer
against its own declaration. The assembled system does not run and nothing in P7
noticed. `test_the_neighbours_pass_while_the_boundary_fails` asserts exactly that —
both neighbours clear on the same input, and only O8 sees the defect.

**`not_implemented` grows by one on every project that declares no surface.** Three
existing tests pinned that tuple and were updated. The direction is right: FR-110 is
no more reachable than FR-112 is, and for the same reason.

**Three shapes of reach are reported as uncovered rather than checked.** `import X`
followed by `X.foo` (the attribute access is below the import), `from X import *`
(the names are whatever X defined), and a relative import. Each is stated on the
check, so a green line is not read as covering them.

**`OracleClass` stays at seven, and the roadmap row is corrected.** The row read as
a missing enum member; it was a missing P7 check. Recorded here so the next reader
does not add the member.

## Evidence

- `TestTheBoundaryContract` (9 tests) and `TestTheBoundaryContractInTheReport`
  (3 tests) in `tests/ci/test_integration.py`; `test_a_specification_with_no_criteria_says_fr_116_is_not_implemented`
  in `tests/ci/test_cli.py` now also asserts FR-110 is named and explained.
- Canaried three ways, each asserting its target string was present before mutating
  and reverted from a file backup: the finding suppressed (4 fail), the promised set
  widened to include every reached name (4 fail), and the declared-edge guard dropped
  so FR-113's defect would be reported twice (1 fail).
- `ruff check` and `ruff format --check` clean; `pyright` 0 errors.
