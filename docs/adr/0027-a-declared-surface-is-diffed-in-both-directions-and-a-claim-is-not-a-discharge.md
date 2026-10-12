# 0027 — A declared surface is diffed in both directions, and a claim is not a discharge

- **Status:** Accepted
- **Date:** 2026-10-12
- **Related:** FR-090, FR-112, FR-115, FR-116, FR-061, §6.3, §10; [ADR-0025](0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md) (why `Module.interface` is prose), [ADR-0026](0026-p7-checks-three-of-six-requirements-and-names-the-rest.md) (the report that named FR-112 as blocked)
- **Amends:** [ADR-0026](0026-p7-checks-three-of-six-requirements-and-names-the-rest.md) point 1 — `not_implemented` is the complement of what the checks **discharge**, not of what they **claim**

## Context

ADR-0026 named FR-112 as blocked: the requirement is "public-API diff must be empty"
(§10) and a diff needs two sides, while `Module.interface` is prose by design — SoFact
does not know the operator's language, and a signature invented by a keyword proposer
would be a fabricated contract that P5 implements and P7 then certifies.

That reasoning is sound about *inventing* the left-hand side. It is not sound about
*declaring* one. FR-090 already requires every module to declare its interface before it
exists, and the gate already freezes that declaration as part of what the operator
approves. What was missing was not the declaration but its **form**: `interface` is a
sentence, and a sentence cannot be diffed.

The research pass (`docs/research/system-model/README.md`) settled the shape and refused
three cheaper options. This record is the decision.

## Decision

**A module may declare its surface as machine-readable members, and P7 diffs the built
public names against them in both directions. A check that claims a requirement but
exercised none of it does not discharge it.**

1. **`Module.surface` is a tuple of `InterfaceMember`** — a name, a kind (function /
   class / constant), and for a function the parameter names in order. It is additive:
   `interface` stays as the prose obligation the operator reads, and the surface is the
   part a machine compares. Empty is a real state, not an error.

2. **The diff is symmetric, and the second direction is the one FR-090 needs.** A
   declared name the build does not expose is a module that did not deliver what it
   promised. A built public name the declaration does not carry is a module that
   **widened** its surface — a second way in that no dependent declared and no gate
   approved. Reporting only the first would certify exactly the drift FR-090 forbids.

3. **The built surface is read from the AST**, using the same `ast` pass FR-113's import
   analysis already runs: top-level `def`, `class` and assignment names that do not begin
   with an underscore. A method is not a module-level name — a method is reached through
   its class, and counting it would report a difference the moment a producer added a
   private helper. A file that does not parse contributes nothing: judging syntax is the
   producer's toolchain's job, not integration's.

4. **Arity is compared; types are not.** A declared member carries parameter *names*
   because that is both language-agnostic and checkable. Comparing types would require
   SoFact to know the operator's language, which is the refusal ADR-0025 already made.

5. **A module with no declared surface is `uncovered`, not passed.** The check runs and
   diffs nothing, and the report says which of the two happened. This is ADR-0026's rule
   applied to a new check, and it is what keeps the check from turning a vacuous pass
   into a claim.

6. **`IntegrationCheck.discharged` is a claim minus its coverage, and
   `not_implemented` is derived from it.** This amends ADR-0026 point 1. A check can
   claim a requirement and exercise none of it, and the case is not hypothetical: the
   conformance check always runs, and diffs nothing until some module declares a surface.
   A `not_implemented` computed from claims alone would drop FR-112 from the tuple the
   moment the check was written, on the strength of a check that compared nothing —
   which is the failure ADR-0026 exists to prevent, arriving through the door it left
   open. `discharged` returns `()` when `covered` is empty, and the requirement stays
   named until a diff with two sides actually happens.

7. **The declared surface is hashed into `decomposition_hash`.** It is a decision the
   operator approved, so an approval must stop describing the module if its public names
   change underneath it. Ids stay excluded, for ADR-0025's reason — they are minted per
   proposal — and the surface is included for the mirror-image reason.

## Consequences

- **FR-112 is implemented and, on a proposal, still reported as unimplemented — both are
  true and the report distinguishes them.** `propose` derives no surface, because nothing
  in a contract's clauses is a signature (`OracleDeclaration` carries a class, a
  description and an optional command, and no parameter list). So the default path runs
  the check, diffs nothing, and names FR-112. The path that declares a surface discharges
  it and the same requirement leaves the tuple without any list being edited. Measured in
  two tests that assert the tuple exactly, in both states.
- **A widened surface is now a finding, which is a new way for integration to fail.** It
  is deliberate: FR-090's permitted surface is what dependents may reach for, and a
  producer adding a public name is the case FR-112's "exactly" is for. The repair scope
  is the module that widened, by FR-114's ordinary rule.
- **Nothing populates `surface` in production yet.** The proposal path leaves it empty
  and the honest report says so; a later decision — an operator authoring the surface at
  the gate, or a clause kind that carries one — fills it. This record does not schedule
  that, and FR-112 is not claimed as discharged on any run that does not have it.
- **FR-115 and FR-116 remain unimplemented and stay named.** FR-115 needs entities and
  relationships across the assembled system, not only each module's surface, so FR-112
  does not discharge it. FR-116 needs P2 acceptance criteria no module satisfies.

## Alternatives refused

- **Invent the surface in the proposer.** Refused (ADR-0025): fabricating the contract P7
  certifies. The failure is silent because a fabricated surface is well-formed.
- **Diff against the prose `interface` with a fuzzy match.** Refused: a similarity
  threshold is a number nobody can defend, and it fails for a reason its operator cannot
  act on.
- **Report only the missing direction.** Refused: it certifies a producer that widened
  its surface, which is the drift FR-090 exists to catch.
- **Count a claim as a discharge.** Refused: it is the vacuous-pass failure ADR-0026
  names, and it would have made FR-112 look implemented on a run that diffed nothing.
- **Compare types.** Refused: it requires the language SoFact does not know.

## Evidence

12 new tests in `tests/ci/test_integration.py` (34 in the file), covering the AST
extraction, both diff directions, arity, the parse failure, and the two-state
`not_implemented` assertion.

Both new gates were **canaried by watching them fail**, each reverted from a file backup
rather than `git checkout`:

- With `check_interface_conformance` blinded (`return ()` after its assertion), four tests
  failed, among them `test_a_built_name_the_declaration_does_not_carry_is_a_finding`.
- With `discharged` blinded to always return `requirements`, one test failed:
  `test_the_report_names_every_requirement_it_did_not_discharge`.

The first blinding attempt was **wrong and was caught**: it rewrote the loop header to
`for module in []:`, which removed the loop body's indentation context and broke the
import analysis too — nine failures, only four of them about the check under test. A
canary that disables more than the thing it names is a canary that cannot attribute its
own failures.
