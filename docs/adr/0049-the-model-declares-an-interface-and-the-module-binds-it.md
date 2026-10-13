# 0049 — The model declares an interface and the module binds it

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-083, FR-084, FR-112, FR-115, FR-081, FR-114, FR-061;
  [ADR-0027](0027-a-declared-surface-is-diffed-in-both-directions-and-a-claim-is-not-a-discharge.md),
  [ADR-0038](0038-a-system-criterion-spans-clauses-and-its-verdicts-are-the-worst.md)

## Context

FR-083 is two sentences and only the first was ever built:

> **FR-083** The system model must be **machine-readable** and must be the **single source
> for interface definitions**. Hand-written interfaces that disagree with the model are an
> integration defect by construction.

The model became machine-readable at P2 (entities, relationships, invariants). The second
sentence stayed open, and the roadmap recorded why: ADR-0027 made FR-112 checkable by
declaring a public surface on `Module`, which is a declaration *beside* the model. A module
could hold one opinion about its own public names and the model another, and nothing in the
system said which was the truth. The roadmap's own verdict for the row read: "It is **not
yet the single source for interface definitions**."

The shape of the failure matters, because it is not the same as "FR-083 is unimplemented".
A surface on a module is checked against the *build* (FR-112) — so a module could agree with
its code and disagree with the model, and every check would pass. Two declarations of one
thing, each internally consistent, is precisely the drift FR-084 exists to make expensive
and the reason the MDSE literature this factory draws on failed.

## Decision

**`SystemInterface` declares an interface in the model; `Module.surface` is its binding, and
`propose` derives the binding rather than accepting it.**

1. **The declaration site is the model.** `SystemModel.interfaces` holds
   `SystemInterface` values. Each names the clause it comes from and the `InterfaceMember`
   values it exposes — the *same* member type a module declares, deliberately, so a surface
   moved from a module to the model is one vocabulary in two places rather than a
   translation between two shapes.

2. **The binding is by clause, not by name.** A module owns clauses and an interface names
   clauses, so `interface → clause → module` is a set comparison — the mechanism
   `SystemEntity` already uses for FR-081 and FR-115. Name matching would pass on
   coincidence (an interface called `store` and a module called `store`) and fail on honest
   renames.

3. **`propose(contract, model)` derives each module's surface** from the interfaces its
   clauses introduce. The proposer never chooses a public name. A model that declares no
   interfaces derives nothing and every surface stays empty, which is ADR-0027's state
   recorded rather than a guess: nothing in a contract's clause is a signature.

4. **`None` and "a model with no interfaces" are different.** `None` means the caller has no
   model; the empty case means the model exists and declares nothing. Both are honest, and
   P7 reports them differently because a project that never described its system and one
   that described it as having no interfaces are different facts.

5. **P7 checks the model against the declared surfaces** in both directions
   (`check_model_is_the_interface_source`), emitting `MODEL_INTERFACE_NOT_BOUND` for an
   interface no module owns and `SURFACE_DISAGREES_WITH_MODEL` for a module whose surface
   is not the one the model derives. An unbound interface's repair scope is *empty* rather
   than a guessed module, because the repair is a revised decomposition (FR-114).

6. **P2 refuses an interface citing a clause outside the contract.** A phantom clause means
   the interface reaches no module, which would otherwise surface at P7 as an unbound
   interface — one phase after the operator could have fixed it. Same reasoning FR-057's
   envelope check uses at P3.

## Consequences

**A disagreement is now possible in exactly one place, and it is reported.** Because
`propose` derives the surface, a proposal cannot disagree with its own model; the finding
arises on a module revised by hand or by a future proposer that stopped reading the model.
That is the drift FR-084 makes expensive, and it is now visible at P7 rather than invisible
everywhere.

**The check compares declarations, not the build.** Whether a declared name exists in the
code is FR-112's diff, run against the build where the build is the evidence. Running it
again here would report one defect twice under two requirement ids, so the check's
`uncovered` names the boundary explicitly.

**FR-083 joins `INTEGRATION_REQUIREMENTS` and is claimed but not discharged when the model
declares no interfaces.** The check runs, binds nothing, and claims nothing — the same shape
FR-112 already has, and the reason `IntegrationCheck.discharged` is separate from
`requirements`. A project with no model reports FR-083 as not implemented rather than
passing on the strength of a check that compared nothing. Three existing tests asserting
`not_implemented` tuples were updated for this, which is the tuple doing its job: it is
derived from what the checks discharged, so adding a check changes it without a list being
edited.

**Two interfaces may not share a name.** The type refuses it, naming both clauses, because
a source that answers one name twice is not a source — and the duplicate case is the one a
merge of two clauses would produce.

**The CLI gained `--interface`.** `NAME:MEMBER,MEMBER:CLAUSE-INDEX`, with members written
`name`, `name(kind)` or `name(kind,param,param)` and the kind defaulting to *function*
explicitly. A requirement the operator's own statement discharges needs a way in, or the
gate behind it can never pass while still reporting itself as a gate. The member list is
split on the commas at parenthesis depth zero: the grammar puts a comma in two places
(between members, between parameters) and a naive `split(",")` reads
`record(f,entry_id),LIMIT(k)` as four members, the first of which opens a parenthesis it
never closes. That defect was found by the CLI test, not by reading the parser.

**FR-084 is not thereby discharged.** The model must be *updated* as part of any change, and
that is a process obligation on the operator, not a property a check can observe. What is
now observable is the consequence of failing to: a model that stopped matching the
decomposition is a P7 finding.

## Evidence

- `propose(contract, model)` derives a module's surface from the model's interfaces, and a
  proposal built that way emits no `SURFACE_DISAGREES_WITH_MODEL` finding
  (`tests/ci/test_integration.py::TestTheModelIsTheInterfaceSource`).
- Canaried three ways, each by mutating the code under test and watching the suite fail:
  the check returning early for every model (4 findings tests fail), the P2 gate's predicate
  replaced with `passed=True` (the phantom-clause test fails), and the derivation replaced
  with `surface=()` (3 tests fail). Each canary asserted its target string was present
  before mutating and was reverted from a file backup.
- `1131 passed` on the full `tests/ci` run; `ruff check` clean, `ruff format --check` clean,
  `pyright` 0 errors.
