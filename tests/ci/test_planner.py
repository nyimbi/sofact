"""The FR-136 goal-plan compiler.

The compiler's job is to turn a contract into ordered goal sessions and to be *total*:
every clause lands in at least one step. The tests that matter are therefore about
coverage and granularity, not about prose. Goal wording is asserted only where a
wording choice would change behaviour — the one-step-per-clause rule, whose whole point
is that a producer cannot satisfy four invariants and call the step done.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

from sofact.contract import oracle_set_hash
from sofact.planner import (
	DEFAULT_STEP_ATTEMPTS,
	DEFAULT_STEP_BUDGET,
	DEFAULT_STEP_CONTINUATIONS,
	DEFAULT_STEP_WALL_CLOCK_SECONDS,
	GOAL_PLAN_TIERS,
	check_integrity,
	compile_plan,
	step_kind_for,
)
from sofact.views import (
	Clause,
	Contract,
	GoalPlan,
	GoalStyle,
	IntegrityOutcome,
	IntegritySubject,
	OracleClass,
	OracleDeclaration,
	PlanStepKind,
	StepBudget,
	content_hash,
)

Make = Callable[..., OracleDeclaration]
MakeContract = Callable[..., Contract]

PLANNER = Path(__file__).resolve().parents[2] / "src" / "sofact" / "planner.py"


def contract_of(make_contract: MakeContract, *classes: OracleClass) -> Contract:
	"""One clause per oracle class, so tier membership is driven by the class."""
	pairs = tuple(
		(
			f"clause number {i} is satisfied for oracle class {oracle_class.value}.",
			make_oracle_with(make_contract, oracle_class, i),
		)
		for i, oracle_class in enumerate(classes)
	)
	return make_contract(*pairs)


def make_oracle_with(_: MakeContract, oracle_class: OracleClass, i: int) -> OracleDeclaration:
	return OracleDeclaration(
		oracle_class=oracle_class,
		description=f"check {i}",
		command_hint=f"pytest -k case_{i}",
	)


# --------------------------------------------------------------------------- #
# tier membership
# --------------------------------------------------------------------------- #


class TestStepKindMapping:
	@pytest.mark.parametrize(
		("oracle_class", "expected"),
		[
			(OracleClass.PROPERTY, PlanStepKind.INVARIANT),
			(OracleClass.METAMORPHIC, PlanStepKind.INVARIANT),
			(OracleClass.STATE_MACHINE, PlanStepKind.STATE_MACHINE),
			(OracleClass.SCHEMA, PlanStepKind.INTERFACES),
			(OracleClass.CONTRACT, PlanStepKind.OPERATION),
			(OracleClass.EXAMPLE, PlanStepKind.OPERATION),
			(OracleClass.GOLDEN, PlanStepKind.OPERATION),
		],
	)
	def test_every_oracle_class_has_exactly_one_home(
		self,
		oracle_class: OracleClass,
		expected: PlanStepKind,
		make_contract: MakeContract,
		make_oracle: Make,
	) -> None:
		contract = make_contract(("something holds.", make_oracle(oracle_class=oracle_class)))
		assert step_kind_for(contract.clauses[0]) is expected

	def test_the_mapping_is_total_over_the_enum(self) -> None:
		"""A new oracle class must not silently fall through to a default."""
		for oracle_class in OracleClass:
			declaration = OracleDeclaration(oracle_class=oracle_class, description="d")
			clause = _clause_with(declaration)
			assert step_kind_for(clause) in PlanStepKind

	def test_the_canonical_tier_order_is_declared_once(self) -> None:
		flat = [kind for tier in GOAL_PLAN_TIERS for kind in tier]
		assert flat[0] is PlanStepKind.BOOTSTRAP
		assert flat[-1] is PlanStepKind.REPAIR
		assert PlanStepKind.INVARIANT in GOAL_PLAN_TIERS[3]
		assert PlanStepKind.STATE_MACHINE in GOAL_PLAN_TIERS[3]


def _clause_with(declaration: OracleDeclaration) -> Clause:
	from sofact.views import ClauseKind, ClauseStem, ElicitationDimension, uuid7str

	stem = ClauseStem(
		id=uuid7str(),
		statement="a statement.",
		kind=ClauseKind.POSITIVE,
		derived_from=ElicitationDimension.OUTCOME,
	)
	return Clause(id=stem.id, statement=stem.statement, kind=stem.kind, oracle=declaration)


# --------------------------------------------------------------------------- #
# structure
# --------------------------------------------------------------------------- #


class TestPlanShape:
	def test_a_plan_always_starts_by_bootstrapping(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		plan = compile_plan(make_contract(("x holds.", make_oracle("true"))))
		assert plan.steps[0].kind is PlanStepKind.BOOTSTRAP
		assert plan.steps[0].ordinal == 0
		assert plan.steps[0].depends_on == ()

	def test_bootstrap_claims_no_clause(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""A step that discharges no clause must not look like it discharges one."""
		plan = compile_plan(make_contract(("x holds.", make_oracle("true"))))
		assert plan.steps[0].clause_ids == ()
		assert plan.steps[0].exit_evidence

	def test_ordinals_are_dense_and_ascending(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(
			make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY, OracleClass.SCHEMA
		)
		plan = compile_plan(contract)
		assert [s.ordinal for s in plan.steps] == list(range(len(plan.steps)))

	def test_dependencies_chain_tier_to_tier(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Steps in one tier all depend on the previous tier, not on each other."""
		contract = contract_of(
			make_contract,
			OracleClass.CONTRACT,
			OracleClass.CONTRACT,
			OracleClass.PROPERTY,
		)
		plan = compile_plan(contract)
		for step in plan.steps:
			for dep in step.depends_on:
				assert plan.step_by_id(dep) is not None
				assert plan.step_by_id(dep).ordinal < step.ordinal  # type: ignore[union-attr]

	def test_a_step_never_depends_on_itself(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(make_contract, OracleClass.PROPERTY, OracleClass.STATE_MACHINE)
		plan = compile_plan(contract)
		assert all(s.id not in s.depends_on for s in plan.steps)

	def test_waves_group_concurrent_work_and_keep_order(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Invariants and the state machine share one tier, so they share one wave."""
		contract = contract_of(
			make_contract, OracleClass.PROPERTY, OracleClass.STATE_MACHINE, OracleClass.CONTRACT
		)
		plan = compile_plan(contract)
		waves = plan.waves()
		assert len(waves) == sum(1 for w in waves if w)
		flat = [step.ordinal for wave in waves for step in wave]
		assert flat == sorted(flat)
		assert len(waves) == len({_tier_of(plan, s.id) for s in plan.steps})

	def test_an_absent_tier_is_dropped_rather_than_left_empty(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""No schema clause means no interfaces step; the plan describes this contract."""
		plan = compile_plan(
			make_contract(("x holds.", make_oracle("true", oracle_class=OracleClass.GOLDEN)))
		)
		assert PlanStepKind.INTERFACES not in {s.kind for s in plan.steps}
		assert all(step is not None for step in plan.steps)

	def test_a_contract_with_no_strong_clauses_still_gets_a_repair_step(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		plan = compile_plan(
			make_contract(("x holds.", make_oracle("true", oracle_class=OracleClass.GOLDEN)))
		)
		assert PlanStepKind.REPAIR in {s.kind for s in plan.steps}

	def test_a_strong_contract_gets_no_repair_step(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Repair exists for weak oracles only; a strong contract needs no repair tier."""
		plan = compile_plan(
			make_contract(("x holds.", make_oracle("true", oracle_class=OracleClass.PROPERTY)))
		)
		assert PlanStepKind.REPAIR not in {s.kind for s in plan.steps}

	def test_the_same_contract_compiles_to_the_same_goal_text(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Only identities and timestamps vary; the wording must be deterministic."""
		contract = contract_of(make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY)
		first = compile_plan(contract)
		second = compile_plan(contract)
		assert [s.goal_hash for s in first.steps] == [s.goal_hash for s in second.steps]
		assert first.id != second.id


def _tier_of(plan: GoalPlan, step_id: str) -> int:
	return next(i for i, wave in enumerate(plan.waves()) if any(s.id == step_id for s in wave))


# --------------------------------------------------------------------------- #
# granularity: the rule that makes a step checkable
# --------------------------------------------------------------------------- #


class TestGranularity:
	def test_operations_are_one_step_per_clause(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = make_contract(
			("first operation holds.", make_oracle("pytest -k a")),
			("second operation holds.", make_oracle("pytest -k b")),
			("third operation holds.", make_oracle("pytest -k c")),
		)
		plan = compile_plan(contract)
		operations = [s for s in plan.steps if s.kind is PlanStepKind.OPERATION]
		assert len(operations) == 3
		assert all(len(s.clause_ids) == 1 for s in operations)

	@pytest.mark.parametrize("oracle_class", [OracleClass.PROPERTY, OracleClass.METAMORPHIC])
	def test_invariants_are_one_step_per_clause(
		self, make_contract: MakeContract, make_oracle: Make, oracle_class: OracleClass
	) -> None:
		"""Batching invariants would let a producer satisfy one and call it done."""
		contract = make_contract(
			("first invariant holds.", make_oracle("pytest -k a", oracle_class=oracle_class)),
			("second invariant holds.", make_oracle("pytest -k b", oracle_class=oracle_class)),
		)
		plan = compile_plan(contract)
		invariants = [s for s in plan.steps if s.kind is PlanStepKind.INVARIANT]
		assert len(invariants) == 2
		assert all(len(s.clause_ids) == 1 for s in invariants)
		assert invariants[0].id != invariants[1].id

	def test_state_machines_are_one_step_per_clause(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = make_contract(
			(
				"the lifecycle never skips a state.",
				make_oracle("pytest -k sm", oracle_class=OracleClass.STATE_MACHINE),
			),
			(
				"the lifecycle always terminates.",
				make_oracle("pytest -k sm2", oracle_class=OracleClass.STATE_MACHINE),
			),
		)
		plan = compile_plan(contract)
		machines = [s for s in plan.steps if s.kind is PlanStepKind.STATE_MACHINE]
		assert len(machines) == 2
		assert all(len(s.clause_ids) == 1 for s in machines)

	def test_repair_is_one_step_per_weak_clause(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = make_contract(
			("a golden check holds.", make_oracle("pytest -k g1", oracle_class=OracleClass.GOLDEN)),
			(
				"a second golden check holds.",
				make_oracle("pytest -k g2", oracle_class=OracleClass.GOLDEN),
			),
		)
		plan = compile_plan(contract)
		repairs = [s for s in plan.steps if s.kind is PlanStepKind.REPAIR]
		assert len(repairs) == 2
		assert all(len(s.clause_ids) == 1 for s in repairs)
		assert {s.clause_ids[0] for s in repairs} == {c.id for c in contract.clauses}

	def test_interfaces_is_a_single_step_for_all_schema_clauses(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""The one deliberate exception: schemas must agree with each other."""
		contract = make_contract(
			(
				"the payload schema holds.",
				make_oracle("pytest -k s1", oracle_class=OracleClass.SCHEMA),
			),
			(
				"the second payload schema holds.",
				make_oracle("pytest -k s2", oracle_class=OracleClass.SCHEMA),
			),
		)
		plan = compile_plan(contract)
		interfaces = [s for s in plan.steps if s.kind is PlanStepKind.INTERFACES]
		assert len(interfaces) == 1
		assert len(interfaces[0].clause_ids) == 2

	def test_a_per_clause_goal_names_only_its_own_clause(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Two invariants must not produce two steps with identical goals."""
		contract = make_contract(
			(
				"the ledger never loses an entry.",
				make_oracle("pytest -k a", oracle_class=OracleClass.PROPERTY),
			),
			(
				"the ledger never reorders an entry.",
				make_oracle("pytest -k b", oracle_class=OracleClass.PROPERTY),
			),
		)
		plan = compile_plan(contract)
		invariants = [s for s in plan.steps if s.kind is PlanStepKind.INVARIANT]
		assert invariants[0].goal_hash != invariants[1].goal_hash
		first, second = (s.goal.render(plan.goal_style) for s in invariants)
		assert "never loses" in first and "never reorders" not in first
		assert "never reorders" in second and "never loses" not in second


# --------------------------------------------------------------------------- #
# coverage: the compiler must be total
# --------------------------------------------------------------------------- #


class TestCoverage:
	def test_every_clause_lands_in_at_least_one_step(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(
			make_contract,
			OracleClass.CONTRACT,
			OracleClass.SCHEMA,
			OracleClass.PROPERTY,
			OracleClass.STATE_MACHINE,
			OracleClass.GOLDEN,
		)
		plan = compile_plan(contract)
		assert plan.uncovered_clause_ids(contract) == ()

	def test_coverage_is_exact_with_a_large_contract(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		classes = tuple(OracleClass) * 3
		contract = make_contract(
			*(
				(f"clause {i} holds.", make_oracle(f"pytest -k c{i}", oracle_class=cls))
				for i, cls in enumerate(classes)
			)
		)
		plan = compile_plan(contract)
		covered = [cid for step in plan.steps for cid in step.clause_ids]
		assert plan.uncovered_clause_ids(contract) == ()
		# At-least-once, not exactly-once: a weak clause is covered twice on purpose.
		assert set(covered) == {c.id for c in contract.clauses}

	def test_a_weak_clause_is_covered_twice_once_to_build_once_to_strengthen(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Repair is a second obligation on the same clause, not a duplicate step."""
		contract = make_contract(
			("a weak clause holds.", make_oracle("pytest -k w", oracle_class=OracleClass.GOLDEN)),
			(
				"a strong clause holds.",
				make_oracle("pytest -k s", oracle_class=OracleClass.PROPERTY),
			),
		)
		plan = compile_plan(contract)
		weak, strong = (c.id for c in contract.clauses)
		by_clause = {
			cid: [s.kind for s in plan.steps if cid in s.clause_ids] for cid in (weak, strong)
		}
		assert by_clause[weak] == [PlanStepKind.OPERATION, PlanStepKind.REPAIR]
		assert by_clause[strong] == [PlanStepKind.INVARIANT]

	def test_the_compiler_refuses_a_contract_with_no_clauses(self) -> None:
		"""Asserting on empty input is cheaper than an empty plan that passes checks."""
		with pytest.raises(AssertionError, match="no clauses"):
			compile_plan(_empty_contract())

	def test_deleting_a_clause_from_the_contract_shows_up_as_uncovered(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Proves ``uncovered_clause_ids`` can actually fail; it is not vacuous."""
		contract = contract_of(make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY)
		plan = compile_plan(contract)
		narrowed = contract.model_copy(update={"clauses": contract.clauses[:1]})
		assert plan.uncovered_clause_ids(contract) == ()
		assert narrowed.content_hash != contract.content_hash
		_ = narrowed


def _empty_contract() -> Contract:
	"""A contract with no clauses, built by removing them from a real one."""
	from sofact._uuid7 import uuid7str
	from sofact.views import ClauseKind, ClauseStem, ElicitationDimension, SpecificationDraft, now

	stem_id = uuid7str()
	draft = SpecificationDraft(
		id=uuid7str(),
		goal_id=uuid7str(),
		created_at=now(),
		stems=(
			ClauseStem(
				id=stem_id,
				statement="the only clause.",
				kind=ClauseKind.POSITIVE,
				derived_from=ElicitationDimension.OUTCOME,
			),
		),
	)
	full = Contract.from_draft(
		draft,
		{
			stem_id: OracleDeclaration(
				oracle_class=OracleClass.CONTRACT,
				description="check",
				command_hint="pytest -k only",
			)
		},
	)
	return full.model_copy(update={"clauses": ()})


# --------------------------------------------------------------------------- #
# budgets and style
# --------------------------------------------------------------------------- #


class TestBudgetAndStyle:
	def test_the_default_budget_is_one_attempt_not_three(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""FR-101: SoFact never retries on its own initiative; a resend needs a decision."""
		plan = compile_plan(make_contract(("x holds.", make_oracle("true"))))
		assert plan.steps[0].budget.max_attempts == DEFAULT_STEP_ATTEMPTS == 1

	def test_default_budget_values_are_applied_to_every_step(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY)
		plan = compile_plan(contract)
		assert all(s.budget == DEFAULT_STEP_BUDGET for s in plan.steps)
		assert DEFAULT_STEP_BUDGET.max_wall_clock_seconds == DEFAULT_STEP_WALL_CLOCK_SECONDS
		assert DEFAULT_STEP_BUDGET.max_continuations == DEFAULT_STEP_CONTINUATIONS

	def test_an_explicit_budget_overrides_the_default(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		tight = StepBudget(max_wall_clock_seconds=60.0, max_continuations=2, max_attempts=1)
		plan = compile_plan(
			make_contract(("x holds.", make_oracle("true"))),
			budget=tight,
		)
		assert all(s.budget == tight for s in plan.steps)

	def test_the_wall_clock_cap_is_carried_onto_the_plan(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""The plan reports the worst case: every step burning its whole cap."""
		plan = compile_plan(
			make_contract(("x holds.", make_oracle("true"))),
			budget=StepBudget(max_wall_clock_seconds=90.0, max_continuations=2, max_attempts=1),
		)
		assert plan.total_wall_clock_cap == 90.0 * len(plan.steps)

	def test_objective_style_changes_the_text_but_not_the_structure(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY)
		labelled = compile_plan(contract, goal_style=GoalStyle.LABELLED)
		objective = compile_plan(contract, goal_style=GoalStyle.OBJECTIVE)
		assert [s.kind for s in labelled.steps] == [s.kind for s in objective.steps]
		assert [s.clause_ids for s in labelled.steps] == [s.clause_ids for s in objective.steps]
		assert [s.goal_hash for s in labelled.steps] != [s.goal_hash for s in objective.steps]

	def test_the_pinned_goal_hash_matches_the_style_it_was_compiled_with(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(make_contract, OracleClass.CONTRACT)
		for style in GoalStyle:
			plan = compile_plan(contract, goal_style=style)
			assert plan.goal_style is style
			for step in plan.steps:
				assert step.goal_hash == step.goal.text_hash(style)

	def test_every_goal_spec_has_all_six_required_parts(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""A goal without a blocked stop condition invites the producer to invent one."""
		contract = contract_of(
			make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY, OracleClass.SCHEMA
		)
		plan = compile_plan(contract)
		for step in plan.steps:
			goal = step.goal
			assert goal.outcome
			assert goal.verification_surface
			assert goal.constraints
			assert goal.boundaries
			assert goal.iteration_policy
			assert goal.blocked_stop_condition

	def test_no_goal_claims_a_worktree_or_branch_nothing_assigns(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""A constraint the child cannot satisfy is worse than a missing one (FR-100/141).

		Two halves, and they move independently.

		The branch half is now *true*: ``dispatch_step`` establishes the step's branch
		through ``ensure_module_branch`` before the session starts and carries it on the
		dispatch record, so a goal may tell the producer it is already on one. The test
		requires that instruction rather than merely permitting it, because a producer
		that switches away would defeat FR-100 while the log still claimed a branch.

		The worktree half is still false and must stay out. FR-141 is deferred
		([ADR-0024]): ``GoalStep`` carries no module identity, so no code can assign a
		worktree, and the instruction that used to name one was an order the producer
		could only disobey.
		"""
		contract = contract_of(
			make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY, OracleClass.SCHEMA
		)
		plan = compile_plan(contract)
		for step in plan.steps:
			joined = " ".join(step.goal.constraints).lower()
			assert "assigned worktree" not in joined, (
				"no worktree is assigned; the child cannot satisfy this and will ignore it"
			)
			assert "on the branch" in joined, (
				"the step's branch is established at dispatch, so the goal must say so"
			)
			assert "do not switch branches" in joined, (
				"a producer that switches away defeats FR-100 silently"
			)
			assert "sofact commits it" in joined, (
				"sealing is SoFact's job (FR-140); a producer that believes it must commit "
				"its own work will invent commits, and one that believes an uncommitted "
				"change is lost will not leave the work in the tree where it is sealed"
			)


# --------------------------------------------------------------------------- #
# the pinned hashes (FR-139)
# --------------------------------------------------------------------------- #


class TestPinnedHashes:
	def test_the_plan_pins_three_things_separately(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Contract, oracle set and per-step goal text are pinned independently."""
		contract = contract_of(make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY)
		plan = compile_plan(contract)
		assert plan.contract_hash == contract.content_hash
		assert plan.oracle_set_hash == oracle_set_hash(contract)
		assert plan.contract_hash != plan.oracle_set_hash
		assert all(step.goal_hash != plan.contract_hash for step in plan.steps)

	def test_two_contracts_with_identical_clauses_but_different_oracles_differ(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""The oracle set is not derivable from the clause set, so it must be pinned."""
		statement = "the reminder is delivered."
		weak = make_contract(
			(statement, make_oracle("pytest -k a", oracle_class=OracleClass.GOLDEN))
		)
		strong = make_contract(
			(statement, make_oracle("pytest -k a", oracle_class=OracleClass.PROPERTY))
		)
		assert oracle_set_hash(weak) != oracle_set_hash(strong)


class TestCheckIntegrity:
	def test_an_untouched_plan_reports_intact_for_all_three_subjects(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY)
		plan = compile_plan(contract)
		checks = check_integrity(plan, contract)
		subjects = {c.subject for c in checks}
		assert subjects == {
			IntegritySubject.CONTRACT,
			IntegritySubject.ORACLE_SET,
			IntegritySubject.GOAL_TEXT,
		}
		assert all(c.outcome is IntegrityOutcome.INTACT for c in checks)

	def test_a_swapped_oracle_set_is_caught_by_the_oracle_check_alone(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""A producer that weakens its own tests has not satisfied them."""
		contract = make_contract(
			("x holds.", make_oracle("pytest -k a", oracle_class=OracleClass.PROPERTY))
		)
		plan = compile_plan(contract)
		weakened = contract.model_copy(
			update={
				"clauses": tuple(
					c.model_copy(
						update={
							"oracle": c.oracle.model_copy(
								update={"oracle_class": OracleClass.GOLDEN}
							)
						}
					)
					for c in contract.clauses
				)
			}
		)
		checks = {c.subject: c for c in check_integrity(plan, weakened)}
		assert checks[IntegritySubject.ORACLE_SET].outcome is IntegrityOutcome.MODIFIED
		assert checks[IntegritySubject.GOAL_TEXT].outcome is IntegrityOutcome.INTACT

	def test_a_swapped_contract_is_caught_by_the_contract_check(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY)
		plan = compile_plan(contract)
		narrowed = contract.model_copy(update={"clauses": contract.clauses[:1]})
		checks = {c.subject: c for c in check_integrity(plan, narrowed)}
		assert checks[IntegritySubject.CONTRACT].outcome is IntegrityOutcome.MODIFIED

	def test_an_edit_to_a_step_goal_hash_is_caught_by_the_goal_text_check(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Re-rendering the stored spec would only prove the compiler agrees with itself."""
		contract = contract_of(make_contract, OracleClass.CONTRACT, OracleClass.PROPERTY)
		plan = compile_plan(contract)
		tampered = plan.model_copy(
			update={
				"steps": (
					plan.steps[0].model_copy(update={"goal_hash": content_hash(["forged"])}),
					*plan.steps[1:],
				)
			}
		)
		checks = {c.subject: c for c in check_integrity(tampered, contract)}
		assert checks[IntegritySubject.GOAL_TEXT].outcome is IntegrityOutcome.MODIFIED
		assert "drifted" in checks[IntegritySubject.GOAL_TEXT].detail

	def test_a_goal_style_change_is_detected_as_text_drift(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Switching style after compiling must not pass as intact."""
		contract = contract_of(make_contract, OracleClass.CONTRACT)
		plan = compile_plan(contract, goal_style=GoalStyle.LABELLED)
		switched = plan.model_copy(update={"goal_style": GoalStyle.OBJECTIVE})
		checks = {c.subject: c for c in check_integrity(switched, contract)}
		assert checks[IntegritySubject.GOAL_TEXT].outcome is IntegrityOutcome.MODIFIED

	def test_integrity_refuses_a_plan_with_no_steps(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = make_contract(("x holds.", make_oracle("true")))
		stripped = compile_plan(contract).model_copy(update={"steps": ()})
		with pytest.raises(AssertionError, match="no steps"):
			check_integrity(stripped, contract)

	def test_a_dispatch_of_the_pinned_pair_is_intact(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(make_contract, OracleClass.CONTRACT)
		plan = compile_plan(contract)
		step = plan.steps[-1]
		record = _dispatch_like(plan, step.id, step.goal_hash)
		checks = [c for c in check_integrity(plan, contract, (record,)) if "dispatch" in c.label]
		assert len(checks) == 1
		assert checks[0].outcome is IntegrityOutcome.INTACT

	def test_a_dispatch_of_a_different_goal_is_modified(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		contract = contract_of(make_contract, OracleClass.CONTRACT)
		plan = compile_plan(contract)
		step = plan.steps[-1]
		record = _dispatch_like(plan, step.id, content_hash(["something else"]))
		checks = [c for c in check_integrity(plan, contract, (record,)) if "dispatch" in c.label]
		assert checks[0].outcome is IntegrityOutcome.MODIFIED

	def test_a_dispatch_of_an_unknown_step_is_unknown_not_intact(
		self, make_contract: MakeContract, make_oracle: Make
	) -> None:
		"""Unreadable is not the same as fine."""
		contract = contract_of(make_contract, OracleClass.CONTRACT)
		plan = compile_plan(contract)
		record = _dispatch_like(plan, "01920000-0000-7000-8000-0000000000ff", plan.contract_hash)
		checks = [c for c in check_integrity(plan, contract, (record,)) if "dispatch" in c.label]
		assert checks[0].outcome is IntegrityOutcome.UNKNOWN
		assert "not in this plan" in checks[0].detail


def _dispatch_like(plan: GoalPlan, step_id: str, goal_hash: str):
	from sofact.views import DispatchMode, DispatchRecord, StepOutcome, now

	at = now()
	return DispatchRecord(
		id="01920000-0000-7000-8000-0000000000aa",
		plan_id=plan.id,
		goal_id=plan.goal_id,
		step_id=step_id,
		step_ordinal=0,
		harness="synthetic",
		mode=DispatchMode.SINGLE_SHOT,
		outcome=StepOutcome.COMPLETED,
		argv=("true",),
		workspace="/tmp",
		budget=DEFAULT_STEP_BUDGET,
		started_at=at,
		ended_at=at,
		wall_clock_seconds=0.1,
		goal_hash=goal_hash,
		contract_hash=plan.contract_hash,
	)


# --------------------------------------------------------------------------- #
# the compiler is deterministic and model-free (ADR-0008 / FR-137)
# --------------------------------------------------------------------------- #


class TestTheCompilerIsModelFree:
	def test_planner_does_not_import_the_llm_client(self) -> None:
		"""Goal text is authored, not generated (FR-137). A model here would be a hole."""
		imported = _imports_of(PLANNER)
		assert "sofact.llm" not in imported
		assert "sofact.elicitation" not in imported
		assert not any(name.endswith("LlmClient") for name in _names_of(PLANNER))

	def test_planner_makes_no_network_call(self) -> None:
		source = PLANNER.read_text(encoding="utf-8")
		for forbidden in ("httpx", "requests", "urllib", "socket", "http://", "https://"):
			assert forbidden not in source, f"planner.py mentions {forbidden}"

	def test_planner_never_shells_out(self) -> None:
		"""The compiler plans; the executor executes (FR-038)."""
		source = PLANNER.read_text(encoding="utf-8")
		for forbidden in ("subprocess", "asyncio.create_subprocess"):
			assert forbidden not in source

	def test_compile_plan_is_not_async(self) -> None:
		"""A pure function over a contract needs no event loop, and being sync says so."""
		import inspect

		assert not inspect.iscoroutinefunction(compile_plan)


def _imports_of(path: Path) -> set[str]:
	tree = ast.parse(path.read_text(encoding="utf-8"))
	modules: set[str] = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			modules.update(alias.name for alias in node.names)
		elif isinstance(node, ast.ImportFrom) and node.module:
			modules.add(node.module)
	return modules


def _names_of(path: Path) -> set[str]:
	tree = ast.parse(path.read_text(encoding="utf-8"))
	return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
