"""Compiling a frozen contract into a goal plan (FR-136), and rendering its goals.

A contract is a set of obligations. A goal plan is a *sequence of sessions* whose
union discharges them, because a single session is bounded by context and token
budget and a 2,500-LOC module will not fit in one (spec §8.4). That is the entire
reason this module exists: the contract says *what must hold*, and the plan says how
to hand it to a worker that cannot hold all of it at once.

Three properties are load-bearing.

**Pure.** No I/O, no model call, one timestamp. The mapping from clause to step is a
function of the contract alone, so the same contract compiles to the same plan shape
and the same goal text. FR-139 hashes that text, and a compiler whose output moved
under it would make every integrity check a false alarm.

**Total, and visibly so.** Every clause maps to a step, and :meth:`GoalPlan.
uncovered_clause_ids` exists to *prove* it. A clause the plan quietly skipped would
be indistinguishable from a clause that was satisfied, which is the most expensive
way to be wrong at delivery. The compiler asserts non-omission at the end rather
than trusting the mapping table.

**Derived, not ceremonial.** The repair step is emitted only when some clause's
oracle cannot support the contract's ceiling (:func:`weak_oracle_clauses`), and the
bootstrap step is the only one that covers no clause. A plan that always contains
six steps regardless of the contract would be apparatus for its own sake, and
apparatus cost is the failure mode this design is most exposed to.

The steps are deliberately small. [S08] records objective drift under compaction:
a long session loses the contract and completes something else. Short steps with
narrow objectives and one exit condition each are the cheap structural mitigation,
which is why an operation is one step *per clause* rather than one step per module.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sofact._uuid7 import uuid7str
from sofact.contract import executable_clauses, oracle_set_hash, weak_oracle_clauses
from sofact.views import (
	STRONG_ORACLE_MAX_RANK,
	Clause,
	ClauseVerdict,
	Contract,
	DispatchRecord,
	GoalPlan,
	GoalSpec,
	GoalStep,
	GoalStyle,
	IntegrityCheck,
	IntegrityOutcome,
	IntegritySubject,
	OracleClass,
	PlanStepKind,
	StepBudget,
	content_hash,
	now,
)

__all__ = [
	"DEFAULT_REPAIR_ATTEMPTS",
	"DEFAULT_STEP_ATTEMPTS",
	"DEFAULT_STEP_BUDGET",
	"DEFAULT_STEP_CONTINUATIONS",
	"DEFAULT_STEP_WALL_CLOCK_SECONDS",
	"GOAL_PLAN_TIERS",
	"check_integrity",
	"compile_plan",
	"refutation_diagnosis",
	"repair_goal",
	"revised_plan",
	"step_kind_for",
]

DEFAULT_STEP_WALL_CLOCK_SECONDS = 3600.0
DEFAULT_STEP_CONTINUATIONS = 8

DEFAULT_STEP_ATTEMPTS = 1
"""One attempt, not three.

FR-101: an unbounded retry loop is the most expensive failure mode available to an
unattended factory, because it consumes wall clock — the binding resource. Retrying
is therefore an operator decision, made by dispatching again, and never a default the
scheduler applies on its own.
"""

DEFAULT_STEP_BUDGET = StepBudget(
	max_wall_clock_seconds=DEFAULT_STEP_WALL_CLOCK_SECONDS,
	max_continuations=DEFAULT_STEP_CONTINUATIONS,
	max_attempts=DEFAULT_STEP_ATTEMPTS,
)

DEFAULT_REPAIR_ATTEMPTS = 2
"""How many times one refuted clause may be handed back to a producer.

FR-101 forbids an *unbounded* retry loop because it consumes wall clock, the binding
resource. A bound is the answer to that, not zero: a factory that halts at the first
refutation cannot finish a system, and one that retries forever cannot be left
unattended. Two is chosen so the loop is demonstrably a loop (one retry is not a
loop) while a third pass over the same clause is left to the operator — a clause
refuted twice is more likely to be a wrong contract than a wrong build, and that is a
human's call rather than the scheduler's.
"""

_SHARED_CONSTRAINTS: tuple[str, ...] = (
	"Declaring completion is the only authority you hold (FR-140). Report it when "
	"done; change nothing else about this session's terms.",
	"Do not raise your own budget, extend your own session, or start a second one.",
	"Do not modify the contract, this goal text, or any oracle — including any test "
	"assertion that serves as one. Editing your own completion criteria is detected "
	"by hash and rejects the work (FR-139).",
	"Work idempotently: re-running this goal must be safe and must not compound changes (FR-099).",
	"You are already on the branch SoFact created for this step. Work on it and do "
	"not switch branches, create one, or commit to another: the branch is what keeps "
	"this step's work from being built in place (FR-100).",
	"Context-file loading is disabled and stays disabled: do not create or rely on "
	"AGENTS.md or CLAUDE.md (FR-150).",
)

_SHARED_BOUNDARIES: tuple[str, ...] = (
	"Stay inside the workspace you were given. That directory is where your work is "
	"verified, so an edit outside it is an edit no oracle will see (FR-141).",
	"Do not read the oracle corpus, holdout scenarios, or factory credentials (FR-059).",
	"Change nothing outside the clauses this step covers.",
)

_ITERATION_POLICY = (
	"Edit, run, observe, revise, as many times as the budget allows. Stop at the "
	"first green run rather than continuing to improve: unrequested refactoring is "
	"out of scope and nothing checks it."
)

_STOP_FLOOR = (
	"On stopping, report what was attempted, what was observed, and the specific "
	"input needed. A blocked step that reports nothing is indistinguishable from a "
	"step that was never dispatched."
)

_EXIT_EVIDENCE: dict[PlanStepKind, tuple[str, ...]] = {
	PlanStepKind.BOOTSTRAP: (
		"the project builds from a clean checkout",
		"the test harness runs and reports zero failures over an otherwise empty suite",
	),
	PlanStepKind.INTERFACES: ("interface conformance passes for every declared stub",),
	PlanStepKind.OPERATION: ("the covered clause's oracle passes",),
	PlanStepKind.INVARIANT: ("property tests for this clause pass at >= 10000 generated cases",),
	PlanStepKind.STATE_MACHINE: (
		"exhaustive transition tests pass for this clause, including transitions that "
		"must be refused",
	),
	PlanStepKind.REPAIR: (
		f"a rank <= {STRONG_ORACLE_MAX_RANK} oracle supplied from outside this session "
		"passes for this clause",
	),
}

_STEP_FOR_ORACLE: dict[OracleClass, PlanStepKind] = {
	OracleClass.SCHEMA: PlanStepKind.INTERFACES,
	OracleClass.CONTRACT: PlanStepKind.OPERATION,
	OracleClass.EXAMPLE: PlanStepKind.OPERATION,
	OracleClass.GOLDEN: PlanStepKind.OPERATION,
	OracleClass.PROPERTY: PlanStepKind.INVARIANT,
	OracleClass.METAMORPHIC: PlanStepKind.INVARIANT,
	OracleClass.STATE_MACHINE: PlanStepKind.STATE_MACHINE,
}
"""Which session kind discharges a clause, keyed by its verification shape.

The oracle class *is* the clause's shape of proof, so it is also the right
discriminator for which session has to do the work. Two mappings are worth defending:

``EXAMPLE`` and ``GOLDEN`` map to ``OPERATION``. §8.4's canonical shape has no
weak-oracle step, and inventing one would be inventing a step the spec does not ask
for. A worked example or a golden file is still a claim about one behaviour, so it
belongs to the session that implements that behaviour — and the *weakness* is then
handled where the spec does handle it, by the repair step.

``METAMORPHIC`` maps to ``INVARIANT``. A metamorphic relation is a property of the
form "f(g(x)) == h(f(x))" — an invariant over a family of inputs, which is exactly
what the invariant step exists to establish.
"""

GOAL_PLAN_TIERS: tuple[tuple[PlanStepKind, ...], ...] = (
	(PlanStepKind.BOOTSTRAP,),
	(PlanStepKind.INTERFACES,),
	(PlanStepKind.OPERATION,),
	(PlanStepKind.INVARIANT, PlanStepKind.STATE_MACHINE),
	(PlanStepKind.REPAIR,),
)
"""Canonical session order, grouped into tiers that may run concurrently.

Steps inside a tier are independent of each other and depend on the previous
non-empty tier. This is the primitive FR-142's wave dispatch needs: modules whose
dependencies are *verified* may run together, so the plan is a DAG of tiers rather
than a list, even though a single module's plan is usually a chain.
"""


def step_kind_for(clause: Clause) -> PlanStepKind:
	"""The session kind that would discharge ``clause``."""
	return _STEP_FOR_ORACLE[clause.oracle.oracle_class]


def _oracle_lines(clauses: Sequence[Clause]) -> tuple[str, ...]:
	"""One line per clause naming how it will be checked, and at what strength.

	Strength is stated because it is the thing the producer most needs to know and is
	least likely to infer: a rank-6 oracle and a rank-1 oracle can carry identical
	prose, and only one of them can support an autonomous build.
	"""
	lines: list[str] = []
	for clause in clauses:
		oracle = clause.oracle
		line = f"{oracle.oracle_class.value} oracle (rank {oracle.rank}): {oracle.description}"
		if oracle.command_hint is not None:
			line += f" — run `{oracle.command_hint}`, expect exit {oracle.expect_exit_code}"
			if oracle.expect_stdout_contains is not None:
				line += f", stdout containing {oracle.expect_stdout_contains!r}"
		lines.append(line)
	return tuple(lines)


def _statements(clauses: Sequence[Clause]) -> str:
	"""The covered clauses' own words, joined. Never paraphrased."""
	return "; ".join(c.statement for c in clauses)


def _bootstrap_goal(contract: Contract) -> GoalSpec:
	"""The one step that covers no clause: the scaffold every other step needs.

	It is stated as covering *no* obligations deliberately. A bootstrap step that
	also started implementing behaviour could not be reviewed as a skeleton, and the
	scaffold is the thing most likely to be wrong in ways the contract cannot see.
	"""
	runnable = len(executable_clauses(contract))
	return GoalSpec(
		outcome=(
			"Create a buildable skeleton for the system this contract describes: project "
			"structure, build configuration, a test harness able to run "
			f"{runnable} executable oracle command(s), and a CI entry point. Implement "
			"none of the contract's obligations in this step."
		),
		verification_surface=(
			"the project builds from a clean checkout",
			"the test harness runs and reports zero failures over an otherwise empty suite",
			"the CI entry point exits zero",
		),
		constraints=_SHARED_CONSTRAINTS,
		boundaries=(
			*_SHARED_BOUNDARIES,
			"Do not implement any clause of the contract yet.",
		),
		iteration_policy=_ITERATION_POLICY,
		blocked_stop_condition=(
			"Stop and report if the build toolchain is unavailable, if the skeleton "
			"cannot be made to build without network access, or if the language or "
			"framework is not derivable from the contract above. " + _STOP_FLOOR
		),
	)


def _interfaces_goal(clauses: Sequence[Clause]) -> GoalSpec:
	return GoalSpec(
		outcome=(
			"Define the interfaces and typed stubs that the following obligation(s) "
			f"attach to, so each can be checked before it is implemented: "
			f"{_statements(clauses)}"
		),
		verification_surface=(
			*_oracle_lines(clauses),
			"interface conformance passes for every declared stub",
		),
		constraints=_SHARED_CONSTRAINTS,
		boundaries=(
			*_SHARED_BOUNDARIES,
			"Stubs only. An interface step that implements behaviour cannot be checked "
			"as an interface.",
		),
		iteration_policy=_ITERATION_POLICY,
		blocked_stop_condition=(
			"Stop and report if an obligation cannot be expressed as an interface over "
			"the declared types, or if the types are not derivable from the contract. "
			+ _STOP_FLOOR
		),
	)


def _operation_goal(clause: Clause) -> GoalSpec:
	"""One clause, one session. The narrowest step the canonical shape allows."""
	return GoalSpec(
		outcome=(
			"Implement the behaviour this obligation names, so that its oracle passes: "
			f"{clause.statement}"
		),
		verification_surface=_oracle_lines((clause,)),
		constraints=_SHARED_CONSTRAINTS,
		boundaries=_SHARED_BOUNDARIES,
		iteration_policy=_ITERATION_POLICY,
		blocked_stop_condition=(
			"Stop and report if this obligation cannot be satisfied without also "
			"satisfying a different clause, if its oracle cannot be made to pass as "
			"written, or if it contradicts the contract. " + _STOP_FLOOR
		),
	)


def _invariant_goal(clauses: Sequence[Clause]) -> GoalSpec:
	return GoalSpec(
		outcome=(
			"Make this invariant hold for every input in its stated domain, not merely for "
			f"the cases already exercised: {_statements(clauses)}"
		),
		verification_surface=(
			*_oracle_lines(clauses),
			"property tests pass at >= 10000 generated cases",
		),
		constraints=_SHARED_CONSTRAINTS,
		boundaries=_SHARED_BOUNDARIES,
		iteration_policy=_ITERATION_POLICY,
		blocked_stop_condition=(
			"Stop and report if this invariant does not hold in general and the contract "
			"does not say which cases are excluded, or if satisfying it would require "
			"changing a different clause. " + _STOP_FLOOR
		),
	)


def _state_machine_goal(clauses: Sequence[Clause]) -> GoalSpec:
	return GoalSpec(
		outcome=(
			"Implement the state machine this obligation describes, including every "
			f"transition that must be refused: {_statements(clauses)}"
		),
		verification_surface=(
			*_oracle_lines(clauses),
			"exhaustive transition tests pass, including transitions that must be refused",
		),
		constraints=_SHARED_CONSTRAINTS,
		boundaries=_SHARED_BOUNDARIES,
		iteration_policy=_ITERATION_POLICY,
		blocked_stop_condition=(
			"Stop and report if a transition's legality is not derivable from the clause "
			"above, or if the state set is incomplete. " + _STOP_FLOOR
		),
	)


def _repair_goal(clauses: Sequence[Clause]) -> GoalSpec:
	"""Raise verification strength on one clause whose oracle blocks the ceiling.

	The sharper half of this step is what it *forbids*. A producer asked to improve
	its own verification is a producer handed the pen that writes its own completion
	criteria — which is FR-139's precise failure, and R22. So the stronger oracle is
	supplied from outside the session, and authoring one is a blocking condition.
	"""
	ranks = sorted({c.oracle.rank for c in clauses})
	return GoalSpec(
		outcome=(
			f"Bring the code into a state where the clause below can be checked by a rank "
			f"<= {STRONG_ORACLE_MAX_RANK} oracle, and make that stronger oracle pass. Its "
			f"current oracle rank is {', '.join(str(r) for r in ranks)}. The stronger "
			"oracle is authored outside this session and is not yours to change: "
			f"{_statements(clauses)}"
		),
		verification_surface=(
			*_oracle_lines(clauses),
			f"a rank <= {STRONG_ORACLE_MAX_RANK} oracle for this clause, supplied from "
			"outside this session, passes",
		),
		constraints=_SHARED_CONSTRAINTS,
		boundaries=_SHARED_BOUNDARIES,
		iteration_policy=_ITERATION_POLICY,
		blocked_stop_condition=(
			f"Stop and report if no rank <= {STRONG_ORACLE_MAX_RANK} oracle has been "
			"supplied for this clause. Do not author, weaken, or replace an oracle "
			"yourself — editing your own completion criteria is refused by hash and "
			"rejects the whole module (FR-139). Report what an oracle for this clause "
			"would have to observe. " + _STOP_FLOOR
		),
	)


def repair_goal(
	clauses: Sequence[Clause],
	diagnosis: str,
	*,
	attempt: int,
	max_attempts: int,
) -> GoalSpec:
	"""Author a session that repairs clauses a verdict has **refuted** (the repair loop).

	This is not :func:`_repair_goal`, and the difference is the whole point. ``_repair_goal``
	is compiled from the contract *before* anything runs and asks for a stronger *oracle*;
	it repairs the verification. This asks the producer to fix the *artefact*, and it is
	authored *after* a verdict exists, from that verdict's own words. A clause whose oracle
	passes but whose behaviour is wrong gets no step at all under ``_repair_goal`` — which
	is precisely the gap between a factory that stops at the first refutation and one that
	finishes.

	Two things make this safe to loop, and both are structural rather than advisory.

	**The diagnosis is the verifier's, not the producer's.** The producer is handed the
	refutation the oracle produced — exit code, stderr — and told to make *that* stop
	happening. It is never handed its own summary of what it did, because a producer
	asked to describe its own failure will describe the failure it can fix.

	**The oracle is out of reach.** The producer may not touch the oracle, the contract,
	or this goal text: FR-139 pins all three to hashes and a mismatch rejects the work
	rather than passing it. A repair loop without that pin is a producer editing its own
	completion criteria, which is R22 and the reason ``DEFAULT_STEP_ATTEMPTS`` is 1.

	The attempt counter is in the goal text so the producer can see the bound. A worker
	that knows it is on attempt 2 of 2 stops proposing the fix that already failed.
	"""
	assert clauses, "a repair goal repairs at least one clause"
	assert diagnosis.strip(), "a repair goal needs the refutation it was authored from"
	assert attempt >= 1, f"attempt is 1-based, got {attempt}"
	assert max_attempts >= attempt, (
		f"attempt {attempt} exceeds the cap {max_attempts}; a goal past the bound is "
		"not a repair, it is an unbounded retry (FR-101)"
	)
	plural = "clause" if len(clauses) == 1 else "clauses"
	return GoalSpec(
		outcome=(
			f"Repair {len(clauses)} refuted {plural} (attempt {attempt} of {max_attempts}). "
			"An oracle ran against this workspace and did not pass. Make it pass. The "
			f"failure it reported is: {diagnosis.strip()} "
			f"The obligation(s) it checks: {_statements(clauses)}"
		),
		verification_surface=(
			*_oracle_lines(clauses),
			f"the refutation above no longer reproduces: {diagnosis.strip()}",
		),
		constraints=(
			*_SHARED_CONSTRAINTS,
			"Fix the behaviour, not the check. The oracle, the contract and this goal "
			"text are pinned by hash and compared after your session: a workaround that "
			"makes the oracle stop complaining without making the obligation hold is "
			"refused, and the module is rejected rather than accepted (FR-139).",
			"Do not weaken, skip, delete or rewrite any test assertion that serves as an "
			"oracle, and do not change the clause this step covers.",
		),
		boundaries=(
			*_SHARED_BOUNDARIES,
			"Change only what is needed to make the refuted obligation hold. The clauses "
			"that already passed must still pass when you are done.",
		),
		iteration_policy=(
			"Reproduce the failure first, then fix it, then re-run the oracle. Do not "
			"propose a fix you have not observed working — a repair session that reports "
			"success without watching the oracle pass has not repaired anything."
		),
		blocked_stop_condition=(
			f"Stop and report if the refutation is not reproducible, if the obligation "
			f"cannot hold without violating a clause this step does not cover, or if you "
			f"have exhausted the approaches available to you on attempt {attempt} of "
			f"{max_attempts}. Report the specific input needed to proceed. Do not attempt "
			"to satisfy the oracle by editing it. " + _STOP_FLOOR
		),
	)


_PER_CLAUSE_GOAL: dict[PlanStepKind, Callable[[Sequence[Clause]], GoalSpec]] = {
	PlanStepKind.INVARIANT: _invariant_goal,
	PlanStepKind.STATE_MACHINE: _state_machine_goal,
	PlanStepKind.REPAIR: _repair_goal,
}
"""Goal builders for the step kinds compiled one step per clause.

Bound at module scope below the builders rather than inside ``_tiers``, so the
step-kind-to-builder relation is inspectable instead of being implied by an if-tree.

One step per clause, not one step per kind, and the reason is R22: short steps with
narrow objectives and one exit condition each are the cheap structural mitigation for
goal hacking, and a step covering three unrelated invariants hands one producer three
obligations behind a single exit condition. It can then satisfy the cheapest and exit.
The wave scheduler (FR-142) runs same-tier steps concurrently, so the split costs
latency only when the tier is genuinely serial — and it makes
``DeclarationPrecision`` measurable per obligation rather than per kind.
"""


@dataclass(frozen=True, slots=True)
class _StepDraft:
	"""A step before its identity, ordinal and dependencies are known."""

	kind: PlanStepKind
	goal: GoalSpec
	clauses: tuple[Clause, ...]
	exit_evidence: tuple[str, ...]


def _tiers(contract: Contract) -> list[list[_StepDraft]]:
	"""Group the contract's clauses into the canonical plan tiers.

	Empty tiers are dropped rather than emitted empty, so a contract with no schema
	clauses produces no interfaces step at all. That keeps the plan a description of
	*this* contract instead of a template with holes in it.
	"""
	by_kind: dict[PlanStepKind, list[Clause]] = {}
	for clause in contract.clauses:
		by_kind.setdefault(step_kind_for(clause), []).append(clause)

	tiers: list[list[_StepDraft]] = [
		[
			_StepDraft(
				kind=PlanStepKind.BOOTSTRAP,
				goal=_bootstrap_goal(contract),
				clauses=(),
				exit_evidence=_EXIT_EVIDENCE[PlanStepKind.BOOTSTRAP],
			),
		],
	]

	interfaces = by_kind.get(PlanStepKind.INTERFACES, [])
	if interfaces:
		tiers.append(
			[
				_StepDraft(
					kind=PlanStepKind.INTERFACES,
					goal=_interfaces_goal(interfaces),
					clauses=tuple(interfaces),
					exit_evidence=_EXIT_EVIDENCE[PlanStepKind.INTERFACES],
				),
			],
		)

	operations = by_kind.get(PlanStepKind.OPERATION, [])
	if operations:
		tiers.append(
			[
				_StepDraft(
					kind=PlanStepKind.OPERATION,
					goal=_operation_goal(clause),
					clauses=(clause,),
					exit_evidence=_EXIT_EVIDENCE[PlanStepKind.OPERATION],
				)
				for clause in operations
			],
		)

	aggregate: list[_StepDraft] = []
	for kind in (PlanStepKind.INVARIANT, PlanStepKind.STATE_MACHINE):
		aggregate.extend(
			_StepDraft(
				kind=kind,
				goal=_PER_CLAUSE_GOAL[kind]((clause,)),
				clauses=(clause,),
				exit_evidence=_EXIT_EVIDENCE[kind],
			)
			for clause in by_kind.get(kind, [])
		)
	if aggregate:
		tiers.append(aggregate)

	weak = weak_oracle_clauses(contract)
	if weak:
		tiers.append(
			[
				_StepDraft(
					kind=PlanStepKind.REPAIR,
					goal=_repair_goal((clause,)),
					clauses=(clause,),
					exit_evidence=_EXIT_EVIDENCE[PlanStepKind.REPAIR],
				)
				for clause in weak
			],
		)

	return tiers


def compile_plan(
	contract: Contract,
	*,
	budget: StepBudget | None = None,
	goal_style: GoalStyle = GoalStyle.LABELLED,
	at: datetime | None = None,
) -> GoalPlan:
	"""Compile ``contract`` into a plan of ordered goal sessions (FR-136).

	Coverage is checked before the plan is returned: every clause lands in at least one
	step, and a clause whose oracle is weak (rank above
	:data:`~sofact.views.STRONG_ORACLE_MAX_RANK`) lands in two — once in its natural tier
	to be implemented, once in the repair tier to have its oracle strengthened. A weak
	clause is therefore *not* a duplicate: it is two different obligations.

	``budget`` is applied to every step, because per-step budgets that differ would be a
	scheduling decision, and scheduling belongs to the dispatcher rather than to the
	compiler.
	"""
	assert contract.clauses, "cannot compile a plan from a contract with no clauses"
	step_budget = budget or DEFAULT_STEP_BUDGET
	timestamp = at or now()

	steps: list[GoalStep] = []
	previous: tuple[str, ...] = ()
	for tier in _tiers(contract):
		ids = [uuid7str() for _ in tier]
		for draft, step_id in zip(tier, ids, strict=True):
			steps.append(
				GoalStep(
					id=step_id,
					ordinal=len(steps),
					kind=draft.kind,
					goal=draft.goal,
					goal_hash=draft.goal.text_hash(goal_style),
					budget=step_budget,
					exit_evidence=draft.exit_evidence,
					clause_ids=tuple(c.id for c in draft.clauses),
					depends_on=previous,
				),
			)
		previous = tuple(ids)

	plan = GoalPlan(
		id=uuid7str(),
		goal_id=contract.goal_id,
		contract_id=contract.id,
		contract_hash=contract.content_hash,
		oracle_set_hash=oracle_set_hash(contract),
		goal_style=goal_style,
		created_at=timestamp,
		steps=tuple(steps),
	)

	uncovered = plan.uncovered_clause_ids(contract)
	assert not uncovered, f"compiler dropped {len(uncovered)} clause(s): {uncovered}"
	assert plan.steps[0].kind is PlanStepKind.BOOTSTRAP, "a plan must start by bootstrapping"
	return plan


def refutation_diagnosis(verdicts: Sequence[ClauseVerdict]) -> str:
	"""The verifier's own words for why these clauses are refuted, joined.

	Never the producer's. A repair goal authored from a producer's summary of its own
	failure would be a goal aimed at the failure the producer can describe rather than
	the one the oracle observed, and the two differ exactly when it matters.

	Each line names the clause and its verdict reason, because the reason carries the
	observation — an exit code, a missing stdout string, a timeout — and it is the
	observation the producer has to make stop happening.
	"""
	assert verdicts, "a diagnosis needs at least one refuted verdict"
	return " | ".join(f"{v.statement!r} — {v.reason}" for v in verdicts)


def revised_plan(
	plan: GoalPlan,
	contract: Contract,
	clauses: Sequence[Clause],
	*,
	diagnosis: str,
	attempt: int,
	max_attempts: int,
	at: datetime | None = None,
) -> GoalPlan:
	"""Extend ``plan`` with one repair step covering ``clauses``, and return the new plan.

	A *new* plan rather than a mutation, because the plan is the thing FR-139 pins
	hashes against: an edited plan would make every integrity check a comparison of the
	plan against itself. The revision carries the original's contract hash and oracle-set
	hash unchanged — the contract did not move, only the plan grew a step — and it chains
	the new step onto the whole previous plan so the repair runs strictly after
	everything it might depend on.

	Every existing step keeps its id, ordinal, goal text and pinned hash. That is what
	lets the log hold two plans for one contract and still answer "which steps has this
	contract already been through?" — the ordinals are stable across revisions, and only
	the tail grows.
	"""
	assert clauses, "a repair revision must cover at least one clause"
	assert diagnosis.strip(), "a repair revision needs the refutation it was authored from"
	timestamp = at or now()
	goal = repair_goal(clauses, diagnosis, attempt=attempt, max_attempts=max_attempts)
	step = GoalStep(
		id=uuid7str(),
		ordinal=len(plan.steps),
		kind=PlanStepKind.REPAIR,
		goal=goal,
		goal_hash=goal.text_hash(plan.goal_style),
		budget=plan.steps[-1].budget,
		exit_evidence=_EXIT_EVIDENCE[PlanStepKind.REPAIR],
		clause_ids=tuple(c.id for c in clauses),
		depends_on=tuple(s.id for s in plan.steps),
	)
	revised = GoalPlan(
		id=uuid7str(),
		goal_id=plan.goal_id,
		contract_id=plan.contract_id,
		contract_hash=plan.contract_hash,
		oracle_set_hash=plan.oracle_set_hash,
		goal_style=plan.goal_style,
		created_at=timestamp,
		steps=(*plan.steps, step),
	)
	uncovered = revised.uncovered_clause_ids(contract)
	assert not uncovered, f"repair revision dropped {len(uncovered)} clause(s): {uncovered}"
	return revised


def _verdict_on(expected: str, observed: str | None) -> IntegrityOutcome:
	"""Compare two hashes, keeping "could not tell" distinct from "changed"."""
	if observed is None:
		return IntegrityOutcome.UNKNOWN
	return IntegrityOutcome.INTACT if observed == expected else IntegrityOutcome.MODIFIED


def check_integrity(
	plan: GoalPlan,
	contract: Contract,
	dispatches: Iterable[DispatchRecord] = (),
) -> tuple[IntegrityCheck, ...]:
	"""Re-verify the three things FR-139 pins to a hash.

	Run at *completion*, never at compile time. Its entire purpose is to catch a
	producer that rewrote its own completion criteria during the session, so checking
	it before the session would be checking nothing.

	The goal-text check is the one worth understanding. Re-rendering the stored spec
	would only prove the compiler agrees with itself; what actually matters is whether
	the text a harness *received* is the text the plan pinned, and whether the oracle
	set it ran against is the one it was judged by. That is why dispatches are an input.
	"""
	assert plan.steps, "cannot check integrity of a plan with no steps"
	checks: list[IntegrityCheck] = []

	observed_contract = contract.content_hash
	checks.append(
		IntegrityCheck(
			subject=IntegritySubject.CONTRACT,
			label=f"{plan.id}:contract",
			expected_hash=plan.contract_hash,
			observed_hash=observed_contract,
			outcome=_verdict_on(plan.contract_hash, observed_contract),
			detail=(
				"the clause set is identical to the one this plan was compiled from"
				if plan.contract_hash == observed_contract
				else "the clause set differs from the one this plan was compiled from, so "
				"any verdict rendered against it cannot be attributed to this plan"
			),
		),
	)

	observed_oracles = oracle_set_hash(contract)
	checks.append(
		IntegrityCheck(
			subject=IntegritySubject.ORACLE_SET,
			label=f"{plan.id}:oracles",
			expected_hash=plan.oracle_set_hash,
			observed_hash=observed_oracles,
			outcome=_verdict_on(plan.oracle_set_hash, observed_oracles),
			detail=(
				"the oracle declarations are the ones this plan was compiled against"
				if plan.oracle_set_hash == observed_oracles
				else "the oracle declarations have moved since this plan was compiled; a "
				"producer that edits its own tests has not satisfied them"
			),
		),
	)

	expected_goals = content_hash([step.goal_hash for step in plan.steps])
	observed_goals = content_hash(
		[step.goal.text_hash(plan.goal_style) for step in plan.steps],
	)
	drifted = [
		step.ordinal
		for step in plan.steps
		if step.goal.text_hash(plan.goal_style) != step.goal_hash
	]
	checks.append(
		IntegrityCheck(
			subject=IntegritySubject.GOAL_TEXT,
			label=f"{plan.id}:goal-text",
			expected_hash=expected_goals,
			observed_hash=observed_goals,
			outcome=_verdict_on(expected_goals, observed_goals),
			detail=(
				"every step's rendered goal reproduces its pinned hash"
				if not drifted
				else f"rendered goal text drifted for step(s) {drifted}; the goal a "
				"harness received is not the goal this plan wrote"
			),
		),
	)

	for record in dispatches:
		step = plan.step_by_id(record.step_id)
		if step is None:
			checks.append(
				IntegrityCheck(
					subject=IntegritySubject.GOAL_TEXT,
					label=f"{plan.id}:dispatch:{record.id}",
					expected_hash=plan.contract_hash,
					observed_hash=record.contract_hash,
					outcome=IntegrityOutcome.UNKNOWN,
					detail=f"dispatch names step {record.step_id}, which is not in this plan",
				),
			)
			continue
		agreed = record.goal_hash == step.goal_hash and record.contract_hash == plan.contract_hash
		checks.append(
			IntegrityCheck(
				subject=IntegritySubject.GOAL_TEXT,
				label=f"{plan.id}:dispatch:{record.id}",
				expected_hash=content_hash([step.goal_hash, plan.contract_hash]),
				observed_hash=content_hash([record.goal_hash, record.contract_hash]),
				outcome=IntegrityOutcome.INTACT if agreed else IntegrityOutcome.MODIFIED,
				detail=(
					f"step {step.ordinal} was dispatched the pinned goal against the pinned "
					"contract"
					if agreed
					else f"step {step.ordinal} was dispatched a goal or contract that differs "
					"from the pinned pair"
				),
			),
		)

	assert len(checks) >= 3, "integrity must check at least the three pinned subjects"
	return tuple(checks)
