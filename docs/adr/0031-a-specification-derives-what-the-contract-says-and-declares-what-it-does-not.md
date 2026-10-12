# 0031 — A specification derives what the contract says and declares what it does not

**Status:** Accepted
**Date:** 2026-10-12
**Context:** FR-076 to FR-086, §3.3, §6.1–6.4. Closes most of the roadmap audit's gap 1.
Builds on [ADR-0030](0030-phases-are-a-state-machine-and-a-gate-is-a-type-boundary.md),
which gave P2 a phase to gate and made `advance_phase` refuse P3 while P2 was incomplete.

## Context

The roadmap audit's first-ranked gap was that P2 produced nothing. FR-076 through FR-086
describe a specification artifact, a system model, non-goals, assumptions and a value
hypothesis; the tree had a `Contract` (clauses with oracles) and a `SpecificationDraft`
(clause stems without them), and neither is a specification. ADR-0026 named the
consequence: two of §10's six integration requirements could not be checked because there
was no model to conform against, and ADR-0027 worked around a third by declaring surfaces
on `Module` instead.

Two questions had to be answered before any of it could be built.

**What does the machine derive, and what does it refuse to?** §3.3 places a gate at P2
because *"no oracle exists for 'this specification expresses your actual intent'"*. That
sentence rules out one design and does not settle the rest: a factory that asked a model to
write the specification would be presenting the operator with a machine's paraphrase of
their own answers and calling the operator's nod validation. That is the lossy compression
§3.3 warns about, performed twice — once by the model, once by the gate.

**How is "every entity is referenced by a requirement" checked?** FR-081 states it as a
requirement. The obvious implementation searches each requirement's prose for the entity's
name. That check fails open: an entity called `id`, `job` or `user` occurs in sentences
that have nothing to do with it, so the check passes on specifications that reference
nothing, and a check that fails open is worse than no check because it reports green.

## Decision

**1. The specification is derived, deterministically, and nothing is invented for the
operator.** `specify(contract)` produces one `Requirement` per clause. The criterion is
the clause's own `oracle.description`, not a restatement: a criterion written here would be
a second, unreviewed statement of the same obligation and the two would drift.

**2. One requirement per clause, because grouping is a judgement the machine must not
make.** Merging clauses into fewer, larger requirements is a decision about which
obligations belong together. That is the structure P3 exists to decompose, and a machine
that decided it here would be pre-empting the phase whose whole job it is.

**3. The operator's own statements are arguments, never derivations.** `SystemModel`,
`NonGoal`, `Assumption` and `ValueHypothesis` are passed in. FR-079 and FR-085 make them
requirements; they are not machine-guessable, and a factory that filled them with plausible
sentences would produce a specification that passes its own gate while the operator said
none of it. What *is* derived is a non-goal proposed from each NEGATIVE clause, because the
elicitation already asked for that answer under its `BOUNDARY` dimension and discarding it
would be the machine deciding what the answer meant.

**4. `VerificationMethod` marks a criterion a human must check, and the gate reports that
rather than failing it.** FR-082's own rule: a requirement whose oracle names no command is
permitted, it must be "marked `human-verified` and its verification cost counted against
the human budget". Failing it would make an honest specification red for being honest;
collapsing it into the machine-checkable set would make the human budget a number nobody
computes. `is_executable` is the discriminator, and it is the same property
`execution.py` already uses to decide whether an oracle can be run.

**5. The FR-081 entity reference is a declared link, not a search.** `SystemEntity`
carries `clause_ids`, and the gate compares sets. It points at a *clause* rather than at a
requirement id because requirements are minted by `specify`, so a clause is the only stable
thing an operator can name when declaring a model. The check is run in both directions:
every declared entity's clause must reach a requirement, and every cited clause must exist
in the contract. Canaried by reverting the check to a substring search and watching
`test_an_entity_no_requirement_references_fails_the_gate` fail — an entity named `id` passes
the search and is referenced by nothing.

**6. FR-081's first clause is checked where it is decidable, and the check says where it is
not.** "No two requirements may contradict" is not machine-decidable in prose. What is
decidable is the case the elicitation can actually produce: the operator answers a
dimension twice with one sentence under opposite polarity, so the contract holds the
statement as both a positive and a negative clause. That is a contradiction, it is exactly
checkable, and the check's own detail line states that it covers the polarity case only
rather than reporting a clean bill for a class it cannot see.

**7. A negative clause becomes a requirement *and* a non-goal.** FR-079 asks for
non-goals; the elicitation's `BOUNDARY` and `FAILURE` dimensions produce them. Both are
kept, because a negative clause is also an obligation — the specification must not silently
drop what the operator bounded.

**8. The gate is a hard stop at its own call site, not only in the phase machine.**
`Service.decompose` now calls `require_approved_specification` first. A gate enforced only
by the caller's discipline is a gate with an undocumented bypass, and the phase machine
alone would leave `decompose` reachable from any code path that never consulted a phase.

## Consequences

- P2 emits a durable artefact (`SPECIFICATION_PROPOSED`, `SPECIFICATION_GATED`), so
  FR-062's second half is done for P2 and a resume lands at a phase whose output exists.
- `sofact specify` takes `--entity`, `--assumption` and `--value`. A verb without them
  could never pass its own gate, which is a gate disabled while still reporting itself as
  one — the failure mode the capability map called out about checks that cannot pass.
- Every CLI and service test that reaches a plan now runs through P2 as well as P3. That is
  deliberate: the alternative is a test-only bypass, and a suite exercising a path
  production does not have is how a gate ends up green and unused.
- **FR-083 is half done.** The model is machine-readable, but it is not yet the single
  source for interface definitions: `Module.surface` is still declared separately and
  nothing derives one from the other. Recorded in the roadmap audit rather than implied by
  this record.
- **FR-078 omits state machines.** The spec lists entities, relationships, state machines,
  invariants and external interfaces. The type has three of the five; state machines and
  external interfaces are not modelled. FR-078 is marked Implemented in the audit with that
  omission named, which is a judgement a reader may disagree with.
- FR-115 and FR-116 remain unbuilt, and are now unblocked rather than blocked: the model
  they need exists.

## Alternatives refused

**Ask a model to write the specification.** Refused in decision 1. It would make the P2
gate the operator validating a paraphrase, and it would give the artefact a provenance the
ledger cannot express — a specification whose content is a completion is not reproducible
from the log.

**Derive non-goals, assumptions and the value hypothesis from the answers.** Refused in
decision 3. The elicitation does ask about boundaries, so a derivation is *possible* for
non-goals — and that is exactly why it is dangerous: it would produce a specification that
looks complete and gates green on sentences the operator never approved as non-goals.

**Check entity references by searching requirement text.** Refused in decision 5, with the
canary as the evidence. It is the implementation a reader would reach for and it fails open.

**Fail the gate when a criterion needs a human.** Refused in decision 4: FR-082 explicitly
permits it, and failing it would push an operator toward declaring machine-checkability they
do not have.

**Put the FR-081 module-coverage check in the P2 gate.** It belongs in P3, where modules
exist. Checking it here would require the specification to name modules, which is P3's
artefact — the same boundary error ADR-0026 corrected in the other direction.

## Evidence

- `src/sofact/specification.py` — `specify`, `gate`, `approve`; `src/sofact/views.py` —
  `Requirement`, `NonGoal`, `Assumption`, `ValueHypothesis`, `SystemEntity`,
  `SystemRelationship`, `SystemInvariant`, `SystemModel`, `Specification`,
  `SpecificationGate`, `VerificationMethod`.
- `tests/ci/test_specification.py` — 32 tests. The negative in each pair matters as much as
  the positive: `test_a_complete_specification_passes_every_check` and
  `test_an_approved_specification_lets_the_decomposition_run` are what keep the gate from
  being a blanket refusal.
- Canary: the entity check was reverted to a substring search in a scratch copy; the
  canary patch asserted its target string was present before mutating, and
  `test_an_entity_no_requirement_references_fails_the_gate` failed under it, along with
  seven downstream tests. Restored from the backup file, not from git.
- `tests/ci` at this commit: **715 passed, 0 failed**. `pyright`: 0 errors.
