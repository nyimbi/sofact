# 0046 — A module declares its budget, and P7 measures the artefact

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-026, FR-097, FR-050, FR-093, FR-114, FR-113, FR-061, NFR-024, NFR-026;
  [ADR-0019](0019-the-diff-is-the-artefact.md),
  [ADR-0042](0042-a-modules-definition-of-done-is-derived-from-its-oracles-shape.md)

## Context

Two requirements state the same bound in two vocabularies.

FR-097: *"Every contract must declare an explicit budget (files, LOC, reasoning class);
exceeding it fails the module and escalates, on the same logic as FR-026."*

FR-026 (old spec §5.2): a lane declares **a maximum changed-file count and a maximum diff
size**, because *"a large diff is unverifiable regardless of oracle results, because review
bandwidth is the binding resource (§7.3)"*.

§14 makes a **module** the Mode G lane, so both land on one declaration, and FR-097's own
sentence — "fails the module" — names the scope: one module, not the plan.

The roadmap recorded the row as **"Partly"**: `StepBudget` (`views.py`) carries wall clock,
continuations, attempts and tokens, and has no `max_files`, no `max_loc`, and no reasoning
class. A budget with no size in it cannot bound a blast radius, and §7.3's argument is
entirely about size.

Three questions had to be answered before any code: **where the bound is declared**, **where
it is measured**, and **what quantity it is a bound on**.

## Decisions

### 1. The bound is declared on the `Module`, and required

`Module.budget: ModuleBudget` has no default. FR-097's word is "must declare", and a
defaulted budget is an undeclared one that reads as a declaration: any default would be a
number the factory invented, and a module whose size nobody bounded is exactly the module
§7.3 is about.

`StepBudget` is the wrong home. It is per **session** — one dispatch's wall clock and
continuations — while FR-097 says "every *contract*" and the size of a module is the sum
over however many sessions it took. A per-session file cap would let a module exceed its
bound by taking one more session, which is the opposite of a bound.

Declaring it on `Module` also puts it where P3 approves it: `decomposition_hash` now covers
the budget, so an approval describes the number P5 is held to. A revision that raises a
bound is a revision of the thing approved, which is the distinction FR-094 asks the hash to
make.

### 2. It is measured at P7, from the decomposition

P7 is the only stage that knows which files a module produced. `integration.attribute_files`
(FR-113) already derives that from the dispatch records' branches, and it is the only honest
source: the branches are cumulative, so reading the working tree would charge one module for
another module's size.

`integrate` reads the budget map **from the decomposition** rather than taking it as a
parameter. The same argument `check_integration` already makes about the module graph
applies: a caller who could supply the budget map could supply one that makes an oversized
module look within bounds. The bound is part of the artefact being integrated, so it travels
with it.

The measurement is a `MODULE_OVER_BUDGET` finding, which makes FR-114's repair scope exactly
the one module that overspent — FR-026's "fails the module and escalates" as a scoped
escalation rather than a halt.

### 3. The bound is on the built artefact, not on the diff

FR-026's words are "maximum changed-file count and a maximum diff size". The measured
quantity here is the **artefact**: the non-blank lines of the files the module's own steps
sealed.

This is a tightening, not a substitution. For a module P5 built from nothing — the normal
case — the added lines *are* the artefact's lines, and the two numbers agree. They diverge
only after a repair, where the artefact is the larger and therefore the stricter bound: a
module cannot grow without limit across repairs that each stay inside a diff bound. Reading
the diff instead would be the looser of the two and would fail open on exactly the case
FR-026 is worried about.

The other reason is FR-114. A repository-wide diff names no module, and the repair scope
needs a name; a per-module diff would require diffing each module's branch against a base
that the dispatch record does not carry.

The report says which quantity it measured, in `uncovered`, rather than calling the number a
diff. A bound reported under the wrong name is the failure ADR-0040 forbids.

The line count is every **non-blank** line, comments included. Which lines a comment occupies
is a property of a language, and ADR-0025 leaves the target language open, so a comment-aware
count would be a count of the factory's guess at the language rather than of the artefact.

### 4. "Unmeasured" is not "within bounds"

A module that sealed no file has no artefact for a bound to be about; a module whose files
could not be read has a bound that is **unmeasured**. Both are named in the check's
`uncovered` list. Only the second is a finding, because only the second is a state where the
factory was asked to measure and could not.

The check distinguishes "the caller supplied no root and no sources" (the bound was not
exercised) from "the artefact is missing" (a finding). NFR-024 is the reason: a green line
over an unmeasured bound is the appearance of verification.

### 5. The P3 gate reports the budget and refuses only an impossible one

The gate gains `every_module_declares_a_budget`. It **reports** each module's declared bound
rather than thresholding it, for the reason FR-091's interface count is reported: the spec
prints one worked example (§7.3 — `max_files: 30`, `max_loc: 2500`, `reasoning_class:
throughput`) and no rule that would let a machine call a different number wrong.

What it can refuse is a bound that is *impossible*: each declared surface member has to be
defined by the artefact, a definition occupies at least one non-blank line, so a module whose
surface needs more lines than its budget allows can never satisfy its interface. Dispatching
P5 against it would spend a session to discover a contradiction the proposal already
contained. The floor is the conservative reading — a module that only re-exports could fit
more names than lines, and such a module defines nothing, which is a different problem.

`propose` supplies `DEFAULT_MODULE_BUDGET`, which is §7.3's own worked example read back.
Taking the spec's number rather than inventing a tighter one is the same discipline
`DeliveryEnvelope` states about §1.3: a factory whose default quietly differs from the
spec's stated figure leaves an operator comparing a build against numbers the factory never
used.

`INTEGRATION_REQUIREMENTS` gains FR-026 and FR-097. They are not §10's numbers, but P7 is
where they are discharged, and a requirement a check claims but the report's vocabulary does
not contain is a requirement the report cannot name as unimplemented.

## Alternatives refused

- **Put the budget on `StepBudget`.** Refused in Decision 1: it is per session, and a
  per-session cap lets a module exceed its bound by taking one more session.
- **Default the field on `Module`.** Refused in Decision 1: a defaulted budget is an
  undeclared one that reads as a declaration, and the number would be the factory's.
- **Measure at P5, when the session seals.** Refused: a session sees its own files, not the
  module's — the module is the sum over its sessions, and P7 is the first place that sum
  exists.
- **Take the budget map as an `integrate` parameter.** Refused in Decision 2: a caller who
  can supply the bounds can supply bounds that fit.
- **Bound the diff.** Refused in Decision 3: it names no module, it is the looser bound after
  a repair, and it would need a base revision the dispatch record does not carry.
- **Count lines with a comment-aware parser.** Refused in Decision 3: the language is open
  (ADR-0025), so it would measure the factory's guess.
- **Gate the budget as a threshold at P3.** Refused in Decision 5: the spec prints no rule,
  and a gate that fails for a number its operator cannot act on is one that gets bypassed —
  which turns off the check that does matter.
- **Report an unmeasured bound as inside it.** Refused in Decision 4: NFR-024.

## Consequences

- `ModuleBudget` and `ReasoningClass` are types in `views.py`; `Module.budget` is required.
- `ReasoningClass` is §10.2's three classes — `throughput`, `reasoning`, `evaluation`. A
  class, never a model name, because NFR-026 makes the factory model-agnostic and a model
  name in a contract would make the contract depend on a vendor.
- `integration.check_module_budget` reports `MODULE_OVER_BUDGET` findings; `integrate` gains
  a `module_budget` check and reads the bounds from the decomposition.
- `sofact decompose` prints each module's budget, because an operator approving at P3 is
  approving that number.
- FR-026 and FR-097 leave the roadmap's gap list. FR-024's *routing* half — a function that
  reads the declared reasoning class to pick a lane — remains unbuilt; the class is now
  declared, and nothing yet routes on it.
- FR-027's T4 blast bound, which ADR-0045 named as the thing T4 unlocks, is still not held:
  this bound is declared per module by the proposer, not derived from a measured blast
  radius.
