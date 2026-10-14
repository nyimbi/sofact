# 0059 — The declared interface is the surface grouping, and the count is checked against it

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** FR-091, FR-083, FR-050, FR-057, FR-093, FR-125, FR-126, NFR-025, §1.3,
  §1.4, §7.1, §20.1;
  [ADR-0039](0039-the-envelope-refuses-a-ceiling-and-reports-a-floor.md),
  [ADR-0058](0058-the-intent-graph-is-what-the-chain-is-projected-from.md)

## Context

FR-091: *"The decomposition must **minimise interface surface**, and must report the
interface count. Rationale: interface count drives integration risk, possibly as `n²`
(§1.4). Interface count is therefore a first-class metric and a gate input."*

The roadmap recorded the row as **Partly**, and the gap was not an omission. `propose`
emitted **exactly one module per clause**, so three separate things followed from one line
of code:

- `Decomposition.interface_count` was `len(self.modules)` — literally `len(contract.clauses)`.
  The "interface count" was the module count wearing a second name, and §1.3 already has a
  *separate* dimension for that ("Modules per platform | 8–25"). One number, two dimensions,
  no way to tell them apart.
- Nothing minimised anything. The gate said so out loud: *"It is reported, not thresholded:
  the spec gives no number, and inventing one would make a quality signal into a gate that
  fails for a reason its operator cannot act on."* The check was `passed=True`, a literal.
- §20.1 names the metric **"Interface count per module"**. Neither the ratio nor the surface
  size was reported anywhere.

The spec indeed prints no interface threshold, so the existing comment was right about the
number. But §7.1's denial is narrower than it reads: *"there is no oracle for 'this is the
right decomposition,' only for 'this decomposition satisfies the specification,' which many
decompositions do."* That denies an oracle for **choosing** a grouping. Reading a grouping
the operator already declared is a different act, and the codebase already draws that line —
`_foundational` derives the dependency DAG from the oracle the contract carries, with the
comment *"reading the oracle the contract already carries, not guessing at architecture."*

**The declaration was already there and was being discarded.** FR-083 made
`SystemModel.interfaces` the single source for interface definitions, and a `SystemInterface`
declares `clause_ids`. `propose` gave every clause its own module and set
`surface = model.surface_for_clauses((clause.id,))` — so one interface the model declares
over two clauses became **two modules exposing the same surface**. The model said one
integration point; the decomposition produced two. That inflation is measurable, and
removing it is the minimisation FR-091 asks for without inventing a single architectural
choice.

## Decision

**The model's declared interfaces are the operator's surface grouping, and `propose`
proposes the minimal grouping they imply.**

Clauses are grouped when they share a declared interface **and** the same `module_class`.
A group becomes one module; everything else about the proposal is unchanged.

### The merge is bounded by the lane

`ModuleClass` is "the class of work this module needs" (FR-050), and `MODULE_CLASS_CEILING`
grants G7 L1 *by class* (FR-126). Merging two clauses from different lanes would put one
lane's work under another lane's autonomy ceiling — a decision about autonomy taken by a
grouping heuristic. So the merge requires equal `classify(...)` output, and a declared
interface spanning two lanes produces two modules **and says so**:

> Not merged, and not a defect: `<interface>` spans `<a>`, `<b>` and FR-050 keeps different
> lanes apart

That is reported rather than refused, on the precedent `delivery.py` set for
`escape_ceiling_applied`: a check that failed for a reason its operator cannot act on —
here, an interface the operator declared *before* the lanes were computed — is how a gate
teaches its operators to bypass it.

### The threshold is derived, not invented

`interface_count_minimised` passes when `interface_count <= minimal_interface_count`, where
the minimum is `len(interface_groups(contract, model))` — a re-derivation of the proposer's
own rule, in one function, called by both. A hand-built decomposition that splits a declared
interface fails it; the proposer's own output cannot.

This is the point of putting the rule in one place. A proposer and a gate that read the
model differently would let the proposer emit a proposal its own gate refuses — which is
exactly what the first draft did: the proposer merged only within a lane and the gate was
lane-blind, so the proposer's output failed the proposer's gate. The test suite found it,
and the fix was to make the gate call the proposer's rule rather than restate it.

The two outcomes are kept apart on the type of the return value —
`_splits_a_declared_interface` returns `(splits, lane_forced)` — because only one of them is
a refusal. The lane-forced case carries the same shape as the split case and is not the same
finding.

### Absence of a model is a vacuous pass, and says so

`model is None` ⇒ `passed=True` with the sentence that this check *asserts nothing*
(NFR-025: nothing measured is not the same as nothing wrong). A model that declares no
interfaces is the same state — every project whose P2 declared entities alone. Every
existing fixture takes this path, and `synthetic.a_model_for` returns
`SystemModel(entities=entities)`, so **the no-model path is byte-identical to the previous
behaviour**: one module per clause, unchanged names, unchanged hashes.

### The report states the three numbers the spec implies

`interface_count_reported` never fails and now prints integration points, declared surface
members and interfaces per module, plus the class distribution — and states that the *bound*
on integration points is §1.3's modules dimension (FR-057), not an interface threshold the
spec does not print. §20.1's metric is the ratio; §1.3's bound is the count. They are
different numbers and the line names both.

## Consequences

- `Decomposition` gains `interface_members` and `interfaces_per_module`; `interface_count`'s
  docstring now says it is the count of *module surfaces*, minimised against the model.
- `gate()` gains a keyword-only `model`, wired from `specification.system_model` at the one
  call site in `service._gate_decomposition`, which already held the specification.
- The CLI prints the count, the members and the ratio, so the number the operator approves
  at P3 is the number FR-091 names.
- `check_model_is_the_interface_source` (FR-083) is unchanged and now harder to trip: with
  one module per interface group, `surface_for_clauses(module.clause_ids)` equals the model's
  surface by construction.

## What this does not do

**It does not choose an architecture.** The machine reads the grouping the operator declared
and refuses to multiply it. A model that declares one interface over twenty clauses produces
one module — a large one — and that is the operator's declaration being honoured, not the
factory's opinion. They see it at the P3 gate and may reject it; §7.1's division of labour
puts the architectural judgement there and nowhere else.

**It does not threshold the count against a number.** The spec prints none for interfaces,
and inventing one would fail for a reason its operator cannot act on. What is checkable is
the *contradiction* between the model and the decomposition, which is the same shape as
FR-083's `SURFACE_DISAGREES_WITH_MODEL` — a fact about two artefacts, not an opinion about
design.

**It does not reduce `n²` integration risk on its own.** It removes the inflation the
proposer was creating; the count that remains is the count the operator declared.
