# 0025 — The decomposition gate has two halves, and a module is one clause

- **Status:** Accepted
- **Date:** 2026-10-12
- **Supersedes:** nothing
- **Related:** FR-087–094, FR-125, FR-126, FR-061, §7.1, §14; [ADR-0024](0024-branch-per-step-is-built-worktrees-are-deferred.md) (which named module identity as FR-141's blocker)

## Context

P3 is the crux. §7.1 says why: **architecture is L1 by definition**. There is no oracle
for "this is the right decomposition" — only for "this decomposition satisfies the
specification", and many do. Everything downstream inherits the choice, so a wrong
decomposition is not a wrong step, it is a wrong build.

Three things had to be decided, and each had a tempting wrong answer.

1. **What proposes the decomposition.** The obvious move is a model: ask it for modules.
   But FR-087 requires the proposal to be *machine-proposed and human-validated*, and a
   model-proposed architecture would make the gate validate one model's opinion about
   another model's opinion. The proposal's provenance would be a completion.

2. **What the gate may check.** A gate that returns "the architecture is sound" is
   asserting the operator's half. A gate that returns only a boolean is one the operator
   has to re-derive by hand, which is how a gate becomes theatre.

3. **What a module *is*.** ADR-0024 recorded that FR-141's worktree-per-module was
   deferred because the build had no module identity — it had steps, and a step is not a
   module. Without deciding what a module is, "per module" in FR-100 is a word in a
   prompt.

## Decision

**A module is one clause, and the proposal is a function of the contract alone.**
`propose` emits one module per clause. The module's class comes from the clause's own
words (a keyword table); its dependency edges come from the oracle class the contract
already carries, and from nothing else. It calls no model. The proposal is therefore
reproducible: two runs over an unchanged contract produce the same modules, in the same
order, with the same names — which is what keeps FR-099's idempotence intact and branch
names stable.

The classifier is deliberately **crude and public**. FR-125 makes the class distribution
a decomposition-quality signal the operator reads at the gate, and a signal computed by
an opaque rule would be read as a measurement. This is a guess with a stated basis, and
`classify` is exported so an operator can audit the rule when the distribution looks
wrong. G7 (auth, secrets, payments, PII) is checked **first**, because it is the only
class where a wrong answer is dangerous: FR-126 makes G7 human-authored, so a
misclassification that buried auth inside a G1 module would quietly raise the ceiling on
exactly the code the specification refuses to grant autonomy over.

**The gate has two halves and the type keeps them apart.** `DecompositionGate` carries
`checks` (machine) and `approved_by`/`approved_at` (operator). The machine half is facts
about the proposal: acyclicity (FR-089), a build order (FR-092), traceability in both
directions (FR-088), that every module cites a clause the contract actually contains, and
the interface count (FR-091). `is_satisfied` is `not failed and is_approved`, so
**approval cannot waive a failed check** — if it could, FR-061's hard stop would be
bypassable by the one action it exists to gate. No code path sets `approved_by`; the
field is unset until a human sets it.

The interface count is **reported, not thresholded**. FR-091 makes it a first-class
metric, and the specification gives no number for it; inventing one would turn a quality
signal into a gate that fails for a reason its operator cannot act on.

**`compile_plan` refuses to run past an unapproved gate**, and that refusal is the
default rather than a flag a caller opts into (FR-061). `require_approval=False` exists
so a demonstration can compile without standing up an operator, and it is named for what
it turns *off*.

## Consequences

- **A module identity now exists, and it is not yet what names the branch.** This is the
  honest boundary of this decision. `compile_plan` still compiles steps from the
  contract's clause *kinds* (`step_kind_for`), and `ensure_module_branch` still names a
  branch from a step's ordinal and kind — so the build remains branch-per-**step**, and
  FR-100's "per module" is a type that exists rather than a wiring that is done. What
  changed is that the gap is now a connection to make rather than a concept to invent:
  the approved `Decomposition` is in the log, its modules carry interfaces and
  dependencies, and a step can name the module it implements. Until that wiring lands,
  a plan whose steps span several modules is still a plan whose branches do not.
- ADR-0024's deferral of FR-141 was blocked on module identity; it is not any more. It
  remains blocked on the wiring above, and on the measurement it always named — a wave
  running concurrently, or a plan spanning more than one module.
- The proposal can be wrong. It is a proposal, and the operator's half of the gate is
  where that is caught. This is the design, not a defect: §7.1 says no machine can make
  that call.
- `approve_decomposition` **recomputes** the gate rather than reading the log row. The
  log holds the gate as it was rendered; approving must be decided against the
  decomposition as it *is*, or a revision would be approved on an earlier revision's
  passing checks.
- `decomposition_hash` covers names, classes, interfaces, clause sets and dependency
  edges, and **not** ids or creation time. Ids are minted per proposal, so hashing them
  would make every run look revised and an approval against a hash would be vacuous.
- One module per clause means a contract with many clauses produces many modules and a
  high interface count. That is visible at the gate by construction — FR-091's metric
  doing its job — but it also means a verbose contract decomposes badly, and the fix is
  to revise the contract, not the proposer.
- The classifier is a keyword table. It will misclassify prose that does not name what it
  is about, and the class distribution at the gate is where that shows up.

## Evidence

26 tests in `tests/ci/test_decomposition.py`, all through real objects.

The gate's refusals are exercised by **making them fail**, not by reading the code:
a mutual dependency fails `acyclic` and `build_order_exists`; an unowned clause fails
`every_requirement_traces_to_a_module` and the refusal names the clause; a dangling
clause reference fails `every_module_cites_a_real_clause`; a sound proposal passes every
machine check and is still not `is_satisfied`.

Both halves were canaried, each from a file backup rather than `git checkout`:

- With the FR-061 refusal removed from `compile_plan`, three tests failed
  (`test_planning_without_a_decomposition_is_refused`,
  `test_planning_with_a_proposal_but_no_approval_is_refused`,
  `test_an_unsound_revision_cannot_be_approved_through_the_service`).
- With FR-088's second direction blinded (`uncovered = ()`),
  `test_an_unowned_clause_fails_the_gate` failed.

`test_the_gate_never_claims_to_judge_the_architecture` asserts the check set *exactly*,
so adding a machine check that names the operator's judgement fails a test rather than
passing review.
