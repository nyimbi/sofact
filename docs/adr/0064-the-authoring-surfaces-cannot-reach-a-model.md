# 0064 — The authoring surfaces cannot reach a model, and absence is the finding

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** FR-052, FR-053, FR-054, FR-055, FR-056, FR-134, FR-002, FR-006, NFR-024, ADR-0053, ADR-0054, ADR-0062

## Context

Three roadmap rows state claims of one shape, and the shape is the reason this is one record
rather than three: each says the factory **cannot** do something.

- **FR-053** — a fine-tuned model "must never be an oracle".
- **FR-134** — a fine-tuned model "must not author contracts".
- **FR-055** — the factory must not "set prices, accept customers, sign agreements, move
  money, or make commitments" without human governance.

A claim of that kind cannot be verified by looking for a call. A call-site check passes the
moment somebody adds one, so it is a statement about today's code wearing a statement about
the design's clothes. The durable form of "cannot" is **reachability**: the code path in
question must be unable to get to the capability at all, however the code above it changes.

The roadmap carried all three as **Not built**, and carried them honestly — there was no
instrument, and the prose in the gap file said so. FR-052, FR-054 and FR-056 are the rows
*beside* these three and they are not the same kind of claim:

- **FR-052** and **FR-054** are deployment decisions — what a tuning run would target, and
  that the product ships a recipe rather than weights. They are not properties of this
  build's code and no module can discharge them.
- **FR-056** needs a staging sequence (shadow → advisory → gated) that does not exist in
  this build.

That distinction decides the record's scope, and getting it wrong is the defect
`ORACLE_AUDIT_REQUIREMENTS` names one phase over: a check that listed six requirements would
report six discharged by a module that looked at none of them.

## Decision

### The measurement is the transitive import closure, not a call-site count

`sofact.authorship` walks the **transitive import closure** of each authoring surface and
reports whether anything in it can talk to a model. Transitivity is the whole point: a helper
three imports down that imports `sofact.llm` is a finding even though the surface's own file
names no model, and a direct-import check would call that clean.

Two surfaces, each with its own closure:

- **`contract_authoring`** (FR-134) — `sofact.elicitation`, `sofact.contract`, `sofact.views`.
- **`oracle_authoring`** (FR-053) — `sofact.contract`, `sofact.manufacture`, `sofact.views`.

`views` is a root of both and that is not padding: the declaration types *are* where a
clause's words and an oracle's class become durable objects, so a module that could reach a
model through `views` could write either.

The model-reaching set is deliberately wider than the factory's own client — `sofact.llm`,
`httpx`, `socket`, `ssl`, `urllib` and the rest — because the claim is that the surface cannot
reach a *model*, and a module that opened a socket to something else could reach one through
it. The set is closed rather than a predicate, for the reason `sofact.mutation`'s operator set
is closed: the finding is a statement about *which* module opened the door, and a predicate
that grew at run time would make two reports incomparable without saying so.

### FR-055's finding is an absence, measured in two halves

FR-055 is a different kind of claim from the other two and it is carried here because the
honest finding about it is also structural. It is measured in two halves and **neither alone
is sufficient**:

- **The import half is the capability.** A module that imported `stripe` could charge a card.
- **The kind half is the vocabulary.** FR-002 makes the ledger the only mutable thing in the
  system, so a `LedgerKind` named for an act *is* the factory having the act — a factory that
  can record an accepted agreement has accepted one.

A tree with no payment library but a `PRICE_SET` kind has the act and no implementation; a
tree with a payment library and no kind has the capability and no place to put it.

**`_COMMERCIAL_ACT_MARKERS` deliberately excludes "contract" and "cost", and the exclusions
are the load-bearing decision.** SoFact's contract is a *verification* contract — the
product's central artifact, `CONTRACT_CREATED` — and `GATE_COST_RECORDED` is what the factory
*spends*, not what it *charges*. A marker list containing either word would fail on every
project, which is the failure mode that teaches an operator to disable the gate.

## Evidence

Measured against the shipped tree on 2026-10-15:

```
contract_authoring     closure=  4  reaching=()
    ('sofact._uuid7', 'sofact.contract', 'sofact.elicitation', 'sofact.views')
oracle_authoring       closure=  5  reaching=()
    ('sofact._uuid7', 'sofact.boundary', 'sofact.contract', 'sofact.manufacture', 'sofact.views')
governance_absent = True
```

Both closures are small, which is itself the finding: the authoring paths are a handful of
pure modules and the model client is not among their dependencies.

**Two scanner defects were found and fixed while writing this, and both failed open.** They
are recorded because each is the kind of bug that a test over the clean package cannot see:

1. **`from sofact import api` records the submodule among the aliases, not in `node.module`.**
   Yielding `node.module` alone names the package initialiser, so the closure stops at
   `sofact/__init__.py` and everything under the real submodule reads as unreachable.
   `cli.py` imports `sofact.api` exactly that way. The first draft of the scanner had this
   bug, and the first measurement it produced — a 4-module closure for the oracle surface —
   was the wrong answer rather than the right one.
2. **A relative import resolves against the importing module's package.** `from .views import
   X` means `sofact.views` in `sofact/boundary.py` and `sofact.sub.views` in
   `sofact/sub/thing.py`. The first draft resolved it against the top-level `PACKAGE` and
   dropped the `node.module` tail for the `from . import views` form, which inflated the
   oracle closure to 31 modules and reported `sofact.llm` as reachable — a false positive that
   would have failed the build.

Both are now tested directly, against synthetic packages, because the real tree exercises
neither in a way that would fail.

**A third defect was in the finding's own wording, and it is the one a test over the
mechanism could not see.** The absence reason printed "a payment, billing, contracting or
pricing interface" while the predicate tests membership in a closed set of sixteen *vendor*
names — and **`contract` is the one word the act markers deliberately exclude**. The
finding therefore named a thing the check was built not to look for, which is the same
class of defect as a gate scoped to the bug rather than the claim: a reader told the check
looks for "contracting" would read its silence as a statement about contracts. The string
now names what the predicate measures (payment, e-signature and settlement providers), and
a test holds it to that — asserting the two excluded words are absent and the measured one
is present, so a later edit that reintroduces an unmeasured word fails rather than reads as
thoroughness.

## Consequences

1. **The check is reachable from the product.** `sofact authorship` calls
   `FactoryService.check_authorship()` and exits non-zero when a surface reaches a model or
   the governance boundary is present. An instrument with no call site is a capability nobody
   can reach — FR-159's defect, checked for here rather than repeated.
2. **The event is appended, never keyed.** `authorship_checks` is a series and
   `latest_authorship_check()` reads the last. FR-053 and FR-134 are claims about the *tree*,
   and the tree moves: a check keyed to the latest would report the current closure while the
   reader believes it is reading the one measured when the contract was authored — the
   stale-evidence mistake FR-006 refuses one phase over.
3. **The finding is reported, not repaired.** A surface that reaches a model is a fact about
   the tree; what to do about it is the operator's decision, and a check that silently rewrote
   an import would be doing the thing it exists to observe.
4. **`AUTHORSHIP_REQUIREMENTS` names three requirements, not six.** FR-052, FR-054 and FR-056
   are absent because they are not claims about this build's code, and the docstring says so
   by name.

## What this does not do

1. **It does not establish the identity half, and every report says so.** FR-053 and FR-134
   are about a *fine-tuned* model specifically. This build holds no tuning capability (FR-052
   makes the target a deployment's choice; FR-054 ships a recipe, not weights), so there is no
   tuned model to name, and a claim that "no tuned model is an oracle" would be a claim about
   a thing that does not exist. `TUNED_MODEL_UNREACHABLE` states this and the CLI prints it
   beside the verdict rather than in a footnote.
2. **It does not build FR-052, FR-054 or FR-056.** The recipe-not-weights rule and the staging
   sequence remain unbuilt and are named as absent in `AUTHORSHIP_REQUIREMENTS`.
3. **It does not read an operator's tree.** The subject is this package — the only import
   graph the factory controls. A deployment's own modules are its business, and the default
   root comes from `sofact.__file__` rather than the working directory so the check measures
   the code that is actually running.
4. **It does not detect a model reached without an import.** A subprocess launched with an
   argv the tree assembled, or a plugin loaded at run time, would not appear in the closure.
   The check's claim is about the static import graph, and it is stated as such rather than
   widened to cover a mechanism it cannot see.
