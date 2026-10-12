# The system model — research for FR-083, FR-112, FR-115

Snapshot: 2026-10-12. Scope: what a machine-readable system model has to be for
FR-112 and FR-115 to become checkable, and what it must *not* be.

**Outcome:** the proposal below was adopted for its interface half —
[ADR-0027](../adr/0027-a-declared-surface-is-diffed-in-both-directions-and-a-claim-is-not-a-discharge.md)
implements `Module.surface` and the two-directional diff, which makes FR-112 checkable
for any module that declares a surface. Nothing derives a surface yet, so the check runs
and diffs nothing on a proposal. FR-115 is untouched: entities and relationships are a
separate decision, as the last section says.

## The blocker, stated exactly

P7 ships two checks and names three unimplemented requirements (ADR-0026). Two of the
three fail for one reason: there is no declared, machine-readable interface.

- **FR-112** requires "public-API diff must be empty". A diff needs two sides. The
  left-hand side is the frozen declaration (FR-090); the right is what was built.
  `Module.interface` is prose, so the left side does not exist.
- **FR-115** requires the assembled system to satisfy the §6.3 model "structurally —
  every declared entity, relationship, and interface present and conforming". The
  model is not a type.

FR-083 is the requirement that makes both reachable, and it is also the constraint
that forbids the cheap fix: *"The system model must be machine-readable and must be
the single source for interface definitions. Hand-written interfaces that disagree
with the model are an integration defect by construction."*

## What the source actually claims

[S07] (MAGE, arXiv 2608.25174, preprint, `verification: reported`, `confidence:
medium`) argues that agents on raw text lose the invariant information needed to
verify anything a test does not exercise, and that an explicit model — interfaces,
state machines, invariants, schemas — permits **structural conformance checks that
run before any code executes**, shrinking the search space a low-capability model
must reason over.

Two things follow for this decision, and one caveat:

1. The model's value here is that it is a **second oracle class that runs before
   code**. That is exactly P7's shape: a check over declarations, not over behaviour.
2. The claim is that the model is what makes the factory self-describing. SoFact
   holding a model of the system it is building is the same mechanism as SoFact
   holding a model of itself.
3. **The caveat is load-bearing**: MDSE's history is "elegant frameworks that failed
   on maintenance cost". FR-084 answers that with "a change that alters behaviour
   without updating the model must fail verification" — the model is self-enforcing
   or it is documentation. The repo's own `findings.md` F7 records this as medium
   confidence on an unresolved preprint URL, so the design must not depend on the
   claim being true. A model that costs more to maintain than it catches is the
   failure mode, and the only defence is that the model is *derived* where it can be
   and *diffed* where it is declared.

## The design tension, and why the obvious answer is wrong

The obvious move is to have `propose` emit machine-readable signatures for each
module. ADR-0025 refused this and the refusal still holds: SoFact does not know the
operator's language (D2/D5 fixes Python for v1, but the decomposition runs before any
language-specific artefact exists and `Module.interface` is consumed by the gate,
which is language-agnostic). A signature invented by a keyword proposer is a
fabricated contract that P5 implements and P7 then certifies — worse than an admitted
gap, because it looks authoritative.

The second obvious move is to let the operator author the whole model by hand. That
contradicts FR-083's "single source" only in spirit, but it puts an L1 artefact on the
operator for every module, which §20.2's gate-load concern (R20) already flags as the
binding human cost.

## Decision (proposed)

**The system model is a declared artefact, proposed from the contract and validated by
the operator, and P7 diffs the built surface against it.**

Concretely:

1. **`InterfaceSurface`** — a machine-readable declaration on `Module`, replacing the
   prose `interface` field's role as *the* interface: a tuple of `InterfaceMember`,
   each with a name, a kind (function / class / constant), and — where the clause's
   oracle is `CONTRACT` — the parameter and return names the contract tests exercise.
   Prose stays as `summary` (human-readable), but it is no longer the thing diffed.
2. **Proposal is derived, not invented.** FR-103 rank 3 says contract tests are
   "derived from interface signatures and errors", so a clause whose oracle is
   `CONTRACT` already *has* a machine-readable obligation behind it. `propose` may
   populate `InterfaceSurface` from those clauses. A clause whose oracle is not
   `CONTRACT`/`SCHEMA` contributes **no** members, which is the honest answer rather
   than a guess.
3. **The diff is both directions.** FR-112 says "diff must be empty", which is
   symmetric: a declared member absent from the build is a violation, and a built
   public name absent from the declaration is *also* a violation — that is the half
   that catches a producer quietly widening a surface.
4. **The public surface is read from the AST.** Python's public API is the top-level
   `def`/`class`/assignment names not starting with `_`, plus their parameter names.
   That is a real, checkable extraction over the files the seal recorded, using the
   same `ast` pass FR-113's import analysis already runs.
5. **A module with no declared members reports `uncovered`, not `passed`.** This is
   ADR-0026's rule applied to the new check: an empty declaration means nothing was
   diffed, and the report must say so.

## Rejected options

- **Invent signatures in the proposer.** Refused (ADR-0025): fabricating the contract
  P7 certifies. The failure is silent because the fabricated surface is well-formed.
- **Diff against the prose interface with a fuzzy match.** Refused: a similarity
  threshold is a number nobody can defend, and it fails for a reason its operator
  cannot act on — the exact pathology ADR-0026's FR-114 and the repo's tone-gate
  lesson both record.
- **Declare the model in a separate file the operator maintains by hand.** Refused as
  the *first* step: FR-084's self-enforcement needs the model to be diffed on every
  run, and a file outside the ledger is not diffed by anything. It can be an *import*
  path later, not the substrate.
- **Treat FR-115 as satisfied by FR-112.** Refused: FR-115 is about entities and
  relationships across the assembled system, not only each module's surface. A module
  can conform perfectly and the system still lack a declared entity.
- **Gate on the model's presence.** Refused: it would make every run red until the
  model is authored, which is the pressure that gets a gate disabled.

## What this does not settle

- **Where the operator's validation is recorded.** FR-087's precedent is a gate with
  two halves; whether the model gets its own gate row or rides on the decomposition's
  is a decision for the ADR that implements this, not for the research.
- **Whether entities and relationships are in v1.** Interfaces alone unblock FR-112;
  FR-115 needs entities and relationships too. The honest sequence is FR-112 first,
  then FR-115, rather than a model type that claims both and checks one.
- **[S07]'s empirical support.** Medium confidence, preprint, URL unresolved. The
  design does not rest on the claim being true — it rests on FR-083, which is the
  operator's requirement, not the paper's.

## Sources

- `docs/sources/s07-mage-model-based-agentic-se.md` (local copy, [S07])
- `docs/spec/product-spec.md` §6.3 (FR-083, FR-084), §9.2 (FR-103 rank 3), §10
  (FR-112, FR-115)
- `docs/adr/0025-...md` (why the interface is prose), `docs/adr/0026-...md` (the
  report that names the gap)
- `docs/research/findings.md` F7
