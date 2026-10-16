"""FR-024 to FR-035 — §5.1's routing function, and the θ gate it reads.

The roadmap row this suite is written against said the routing function's *other* inputs
were absent: "§5.1's ``admissible(lane)`` and ``ceiling(lane)`` are not computed from an
oracle strength or a measured blast radius, and nothing routes on ``intent_derivable``".
So the substance here is the three lines of §5.1 and the four refusals they carry:

    admissible(lane) = intent_derivable ∧ oracle_exists ∧ blast_radius_bounded(deployment)
    ceiling(lane)    = min( f(oracle_strength), g(blast_bound), h(deployment_isolation) )
    level(lane)      = min( ceiling(lane), floor(concerns) )

Three of those are properties of the *reading* rather than of the arithmetic, and each has
a class below because each is a way this function could pass while being wrong:

**An unmeasured strength is not a low one.** FR-009's table has no row for "nobody
measured", and the tempting filling — ``L1`` — is the one NFR-024 forbids: it reports a
measurement that does not exist as a measurement at the bottom of the table. The same
argument reaches a lane with *one* unmeasured clause, which is why the lane's strength is
``None`` rather than a mean over the clauses that happened to be measured.

**A concerns floor may only lower.** FR-024's words are that the implementation "must
reject a configuration where a concerns floor is used to justify a *higher* level", so the
rejection is a refusal by name and the ``min`` is not the rejection.

**Exceeding a blast bound fails the lane.** FR-026 says "exceeding either fails the lane
and escalates — a large diff is unverifiable regardless of oracle results". So an over-
budget lane is *inadmissible* and has no ceiling at all, rather than a lane whose ceiling
was lowered — the distinction that makes the failure an escalation.

**FR-027 is a level gate, not an admission one**, and the two requirements are separated
here because writing them together is the mistake this suite made first. FR-026 is about a
number the lane declared; FR-027's sentence is "**Autonomy L4 requires** that the lane's
file scope be declared and enforced by permission". Enforcing it at admission makes every
lane at a deployment with no measured boundary inadmissible, and FR-124 requires the
opposite — "T1 (dev instance, no isolation boundary) runs Mode G at −1 level". So it caps
the *level* below L4, and the class below tests both directions.

Everything runs on real objects: real :class:`Clause` rows, a real
:class:`DeploymentBoundary` as :mod:`sofact.boundary_probe` produces one, and a real
service for the end-to-end case.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from synthetic import gated_contract, synthetic_service

from sofact._uuid7 import uuid7str
from sofact.integration import module_budget_readings
from sofact.routing import (
	CONCERNS_FLOORS_ENV,
	THETA_THRESHOLDS_ENV,
	ConcernsFloor,
	RoutingRefusal,
	admissible,
	load_concerns_floors,
	load_theta_thresholds,
	oracle_strength_ceiling,
	permission_ceiling,
	route,
	route_statement,
)
from sofact.service import FactoryService
from sofact.views import (
	CONCERNS_FLOOR,
	DEFAULT_THETA,
	L3_GATE_THETA,
	L4_GATE_THETA,
	MODULE_CLASS_CEILING,
	AutonomyLevel,
	BoundaryMechanism,
	Clause,
	ClauseKind,
	ClauseStem,
	Contract,
	DeploymentBoundary,
	DeploymentTopology,
	ElicitationDimension,
	Module,
	ModuleBudget,
	ModuleClass,
	OracleClass,
	OracleDeclaration,
	ReasoningClass,
	Requirement,
	Specification,
	SpecificationDraft,
	VerificationMethod,
	now,
)

RUNNABLE = OracleDeclaration(
	oracle_class=OracleClass.PROPERTY,
	description="a property test",
	command_hint="pytest -q",
)
PROSE = OracleDeclaration(oracle_class=OracleClass.PROPERTY, description="we will check it by hand")


def clause(*, executable: bool = True, kind: ClauseKind = ClauseKind.POSITIVE) -> Clause:
	return Clause(
		id=uuid7str(),
		statement="the reminder is delivered once and only once",
		kind=kind,
		oracle=RUNNABLE if executable else PROSE,
	)


def contract_of(*clauses: Clause) -> Contract:
	return Contract(
		id=uuid7str(),
		goal_id=uuid7str(),
		version=1,
		created_at=now(),
		clauses=clauses or (clause(),),
	)


def module_of(
	contract: Contract,
	*,
	module_class: ModuleClass = ModuleClass.G1,
	max_files: int = 4,
	max_loc: int = 200,
	name: str = "delivery",
) -> Module:
	return Module(
		id=uuid7str(),
		name=name,
		module_class=module_class,
		interface="deliver(reminder: Reminder) -> Receipt",
		clause_ids=tuple(c.id for c in contract.clauses),
		budget=ModuleBudget(
			max_files=max_files, max_loc=max_loc, reasoning_class=ReasoningClass.THROUGHPUT
		),
	)


def boundary(*, enforced: bool = True) -> DeploymentBoundary:
	"""A boundary as the probe produces one, with ``enforced`` the measurement it made."""
	return DeploymentBoundary(
		mechanism=BoundaryMechanism.SEATBELT if enforced else BoundaryMechanism.NONE,
		enforced=enforced,
		attempted="ran one child told to escape its directory",
		probed_at=datetime.now(UTC),
		observed="measured for this test",
	)


def specification_for(contract: Contract) -> tuple[Specification, SpecificationDraft]:
	"""A specification whose requirements trace to the contract's clauses, plus the draft.

	The draft is the *traceability* half of FR-076's ``intent_derivable`` conjunct: the
	stem map :func:`admissible` reads is keyed by clause id and its value is the dimension
	the stem was derived from. A draft the type refuses to build empty, so the
	"nobody answered" case is expressed by passing no stem map at all — which is what a
	caller with no draft has, and is the state the term is there to catch.
	"""
	stems = tuple(
		ClauseStem(
			id=c.id,
			statement=c.statement,
			kind=c.kind,
			derived_from=ElicitationDimension.ORACLE,
		)
		for c in contract.clauses
	)
	draft = SpecificationDraft(
		id=uuid7str(),
		goal_id=contract.goal_id,
		created_at=now(),
		stems=stems,
	)
	requirements = tuple(
		Requirement(
			id=uuid7str(),
			statement=f"the system must satisfy: {c.statement}",
			criterion="the property test passes",
			verification_method=VerificationMethod.ORACLE,
			clause_ids=(c.id,),
		)
		for c in contract.clauses
	)
	specification = Specification(
		id=uuid7str(),
		goal_id=contract.goal_id,
		contract_id=contract.id,
		created_at=now(),
		requirements=requirements,
	)
	return specification, draft


def strengths_for(contract: Contract, value: float) -> dict[str, float]:
	return {c.id: value for c in contract.clauses}


class TestThetaIsReadAndNotInvented:
	"""FR-009's table, and the row it does not have (NFR-024)."""

	def test_an_unmeasured_strength_has_no_ceiling(self) -> None:
		"""The whole of NFR-024 in one call. ``L1`` would report a lane nobody measured as a
		lane measured at the bottom of the table, and it would make FR-105's escalation fire
		on the absence of evidence rather than on evidence."""
		assert oracle_strength_ceiling(None) is None

	def test_the_three_rows_of_fr_009(self) -> None:
		"""At, above and below each threshold — the boundaries read from both sides, because
		a table that admitted L4 at ``θ_hi - ε`` would pass a test that only checked ``1.0``."""
		assert oracle_strength_ceiling(1.0) is AutonomyLevel.L4
		assert oracle_strength_ceiling(L4_GATE_THETA) is AutonomyLevel.L4
		assert oracle_strength_ceiling(L4_GATE_THETA - 0.01) is AutonomyLevel.L3
		assert oracle_strength_ceiling(L3_GATE_THETA) is AutonomyLevel.L3
		assert oracle_strength_ceiling(L3_GATE_THETA - 0.01) is AutonomyLevel.L1

	def test_there_is_no_l2_row_and_none_is_interpolated(self) -> None:
		"""§4.3's table jumps from L3 to L1 and this build does not fill the gap. A function
		that interpolated an L2 for a middling strength would be stating a threshold the
		specification does not.

		``None`` is deliberately absent from the expected set: it is the answer for *no
		measurement*, and a sweep over ``0.00`` to ``1.00`` is a sweep over measurements.
		A ``None`` appearing here would mean the function had started reading a number as
		an absence.
		"""
		admitted = {oracle_strength_ceiling(s / 100) for s in range(101)}

		assert AutonomyLevel.L2 not in admitted
		assert admitted == {AutonomyLevel.L1, AutonomyLevel.L3, AutonomyLevel.L4}

	def test_the_default_pair_is_fr_009s_and_says_it_is_assumed(self) -> None:
		"""FR-010: the built-in numbers are "(assumed) and must be calibrated ... before they
		are trusted". The pair has to be able to *say* nobody calibrated it, or the
		assumption is invisible at exactly the moment it is load-bearing."""
		assert DEFAULT_THETA.hi == L4_GATE_THETA
		assert DEFAULT_THETA.lo == L3_GATE_THETA
		assert DEFAULT_THETA.assumed
		assert "assumed" in DEFAULT_THETA.statement

	def test_a_crossed_pair_is_refused(self) -> None:
		"""θ_lo above θ_hi would make FR-009's table non-monotone, so a *weaker* oracle would
		admit a *higher* level — which is the one direction the table may not fail in."""
		from sofact.views import ThetaThresholds

		with pytest.raises(ValueError, match="θ_lo"):
			ThetaThresholds(hi=0.5, lo=0.9)

	def test_a_calibrated_pair_carries_its_provenance(self) -> None:
		from sofact.views import ThetaThresholds

		calibrated = ThetaThresholds(hi=0.9, lo=0.7, calibrated_by="measured over 40 escapes")

		assert not calibrated.assumed
		assert "measured over 40 escapes" in calibrated.statement


class TestTheThresholdsSeam:
	"""FR-010's calibration is configuration, read through the same seam as the rest."""

	def test_a_pair_is_read_and_names_who_calibrated_it(self, tmp_path: Path) -> None:
		path = tmp_path / "theta.json"
		path.write_text('{"theta": {"hi": 0.9, "lo": 0.7, "calibrated_by": "operator"}}')

		loaded = load_theta_thresholds(path)

		assert (loaded.hi, loaded.lo) == (0.9, 0.7)
		assert loaded.calibrated_by == "operator"

	def test_a_half_calibrated_pair_is_refused_rather_than_completed(self, tmp_path: Path) -> None:
		"""One threshold from a measurement beside one from the defaults would make
		FR-009's two rows describe two different populations."""
		path = tmp_path / "theta.json"
		path.write_text('{"hi": 0.9}')

		with pytest.raises(RoutingRefusal, match=r"calibrates the .pair"):
			load_theta_thresholds(path)

	def test_an_unknown_field_is_refused_by_name(self, tmp_path: Path) -> None:
		path = tmp_path / "theta.json"
		path.write_text('{"hi": 0.9, "lo": 0.7, "hi2": 0.1}')

		with pytest.raises(RoutingRefusal, match="hi2"):
			load_theta_thresholds(path)

	def test_an_unreadable_file_names_the_variable(self, tmp_path: Path) -> None:
		with pytest.raises(RoutingRefusal, match=THETA_THRESHOLDS_ENV):
			load_theta_thresholds(tmp_path / "absent.json")


class TestTheConcernsFloorOnlyLowers:
	"""FR-024's refusal, and the reason it lives in the loader."""

	def test_a_floor_below_the_built_in_one_is_accepted(self, tmp_path: Path) -> None:
		path = tmp_path / "floors.json"
		path.write_text(
			'{"concerns_floors": {"G4": {"level": 1, "reason": "payments", "declared_by": "operator"}}}'
		)

		floors = load_concerns_floors(path)

		assert len(floors) == 1
		assert floors[0].lane is ModuleClass.G4
		assert floors[0].level is AutonomyLevel.L1

	def test_a_floor_above_the_built_in_one_is_refused_by_name(self, tmp_path: Path) -> None:
		"""FR-024: "the implementation must reject a configuration where a concerns floor is
		used to justify a *higher* level". G7's built-in floor is L1 and this declaration
		would raise it, which is the refusal the requirement is about."""
		path = tmp_path / "floors.json"
		path.write_text(
			'{"concerns_floors": {"G7": {"level": 3, "reason": "we have good tests", '
			'"declared_by": "operator"}}}'
		)

		with pytest.raises(RoutingRefusal, match="FR-024"):
			load_concerns_floors(path)

	def test_a_floor_with_no_reason_is_refused(self, tmp_path: Path) -> None:
		"""NFR-018 names a risk class; a floor with no reason is one the next reader deletes
		when it blocks something."""
		path = tmp_path / "floors.json"
		path.write_text('{"concerns_floors": {"G4": {"level": 1, "declared_by": "operator"}}}')

		with pytest.raises(RoutingRefusal, match="reason"):
			load_concerns_floors(path)

	def test_an_empty_table_is_refused_rather_than_read_as_no_floors(self, tmp_path: Path) -> None:
		path = tmp_path / "floors.json"
		path.write_text('{"concerns_floors": {}}')

		with pytest.raises(RoutingRefusal, match="empty"):
			load_concerns_floors(path)

	def test_an_unreadable_file_names_the_variable(self, tmp_path: Path) -> None:
		with pytest.raises(RoutingRefusal, match=CONCERNS_FLOORS_ENV):
			load_concerns_floors(tmp_path / "absent.json")

	def test_the_built_in_table_is_the_one_nfr_018_names(self) -> None:
		"""G7 is §14's auth/secrets/payments/PII class, which is the class NFR-018's
		sentence is about — and it is the only entry, because the other concerns NFR-018
		lists are not module classes (a migration is G4, which §14 gives L3)."""
		assert CONCERNS_FLOOR == {ModuleClass.G7: AutonomyLevel.L1}


class TestAdmissibility:
	"""§5.1's first line, term by term (FR-076, FR-108, FR-027)."""

	def test_all_three_terms_hold_on_a_healthy_lane(self) -> None:
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		terms = admissible(
			module_of(contract),
			clauses={c.id: c for c in contract.clauses},
			requirements={r.id: r for r in specification.requirements},
			stems={s.id: s.derived_from for s in draft.stems},
			within_budget=True,
		)

		assert [t.name for t in terms] == [
			"intent_derivable",
			"oracle_exists",
			"blast_radius_bounded",
		]
		assert all(terms)
		assert all(t.requirement for t in terms), "every term cites the requirement it carries"

	def test_a_prose_oracle_makes_the_lane_inadmissible(self) -> None:
		"""FR-108: an oracle with no command "is not a weaker oracle, it is an *intention*",
		and §5.1's term is about existence rather than strength."""
		contract = contract_of(clause(executable=False))
		specification, draft = specification_for(contract)

		terms = admissible(
			module_of(contract),
			clauses={c.id: c for c in contract.clauses},
			requirements={r.id: r for r in specification.requirements},
			stems={s.id: s.derived_from for s in draft.stems},
			within_budget=True,
		)

		failed = [t for t in terms if not t.held]
		assert [t.name for t in failed] == ["oracle_exists"]
		assert "intention rather than a check" in failed[0].detail

	def test_a_clause_whose_dimension_nobody_answered_is_underivable(self) -> None:
		"""FR-076's conjunct, and the reason it is a term rather than an assumption: §6.1
		refuses to guess at intent, so a clause whose stem names no answered dimension is a
		clause whose intent is a guess. No draft at all is the strongest form of that —
		every clause is underivable — and a draft whose stems are for *other* clauses is
		the same fact with the traceability half present."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		no_draft = admissible(
			module_of(contract),
			clauses={c.id: c for c in contract.clauses},
			requirements={r.id: r for r in specification.requirements},
			stems={},
			within_budget=True,
		)
		elsewhere = admissible(
			module_of(contract),
			clauses={c.id: c for c in contract.clauses},
			requirements={r.id: r for r in specification.requirements},
			stems={s.id: s.derived_from for s in draft.stems if s.id != contract.clauses[0].id},
			within_budget=True,
		)

		for terms in (no_draft, elsewhere):
			failed = [t for t in terms if not t.held]
			assert [t.name for t in failed] == ["intent_derivable"]

	def test_exceeding_the_blast_bound_fails_the_lane(self) -> None:
		"""FR-026's own words: "Exceeding either **fails the lane and escalates**". So the
		term is false and the sentence names the budget — it does not lower a ceiling."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		terms = admissible(
			module_of(contract),
			clauses={c.id: c for c in contract.clauses},
			requirements={r.id: r for r in specification.requirements},
			stems={s.id: s.derived_from for s in draft.stems},
			within_budget=False,
		)

		blast = next(t for t in terms if t.name == "blast_radius_bounded")
		assert not blast.held
		assert "exceeded the blast bound its own budget declared (FR-026)" in blast.detail

	def test_an_unmeasured_budget_is_not_a_met_one(self) -> None:
		"""``within_budget=None`` — the artefact was not read — fails the term rather than
		passing it, because a bound nobody measured is not a bound that was met (NFR-024)."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		terms = admissible(
			module_of(contract),
			clauses={c.id: c for c in contract.clauses},
			requirements={r.id: r for r in specification.requirements},
			stems={s.id: s.derived_from for s in draft.stems},
			within_budget=None,
		)

		blast = next(t for t in terms if t.name == "blast_radius_bounded")
		assert not blast.held
		assert "were not read" in blast.detail


class TestPermissionIsALevelGateAndNotAnAdmissionOne:
	"""FR-027, in the place the requirement puts it: "**Autonomy L4 requires** that the
	lane's file scope be declared and enforced by permission".

	The scope matters and this class is the test of it. FR-026 and FR-027 sit in one
	section and are two facts: FR-026 is a declared number whose breach fails the lane, and
	FR-027 gates the *level*. Written as an admission conjunct — which is how this suite
	first had it — a deployment with no measured boundary admits nothing, and FR-124 says
	in as many words that it runs: "T1 (dev instance, no isolation boundary) runs Mode G at
	−1 level".
	"""

	def test_a_lane_with_no_measured_boundary_is_admissible_and_capped_below_l4(self) -> None:
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract, module_class=ModuleClass.G1),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			topology=DeploymentTopology.T2,
			boundary=None,
			within_budget=True,
		)

		assert decision.admissible, "FR-124: T1 runs, so an unmeasured boundary is not a refusal"
		assert decision.level is AutonomyLevel.L3, "and L4 is out of reach without permission"

	def test_an_enforced_boundary_is_what_lifts_the_cap(self) -> None:
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract, module_class=ModuleClass.G1),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			topology=DeploymentTopology.T2,
			boundary=boundary(),
			within_budget=True,
		)

		assert decision.level is AutonomyLevel.L4

	def test_a_probe_that_found_no_confinement_does_not_lift_it(self) -> None:
		"""``enforced=False`` is a probe that ran and found nothing, which is a different
		fact from no probe at all — and neither is a scope enforced by permission."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract, module_class=ModuleClass.G1),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			topology=DeploymentTopology.T2,
			boundary=boundary(enforced=False),
			within_budget=True,
		)

		assert decision.level is AutonomyLevel.L3

	def test_a_lane_already_below_l4_is_not_moved_by_the_cap(self) -> None:
		"""The cap may only lower, and a G5 lane is L2 by class: the permission half is not
		a second reduction on a lane that never reached the level it gates."""
		assert permission_ceiling(AutonomyLevel.L2, boundary=None) is AutonomyLevel.L2
		assert permission_ceiling(AutonomyLevel.L4, boundary=None) is AutonomyLevel.L3
		assert permission_ceiling(AutonomyLevel.L4, boundary=boundary()) is AutonomyLevel.L4


class TestTheBudgetVerdictHasOneSource:
	"""FR-026's verdict is computed in :mod:`sofact.integration` and read here."""

	def test_the_reading_agrees_with_the_check(self) -> None:
		"""Two implementations of one bound would be two answers to one question. The
		routing term reads :func:`module_budget_readings`, which
		:func:`check_module_budget` also uses, so this asserts they agree on a lane that is
		over and on one that is inside."""
		budgets = {
			"over": ModuleBudget(max_files=1, max_loc=2, reasoning_class=ReasoningClass.THROUGHPUT),
			"inside": ModuleBudget(
				max_files=4, max_loc=40, reasoning_class=ReasoningClass.THROUGHPUT
			),
		}
		ownership = {"over": ("a.py", "b.py"), "inside": ("c.py",)}
		sources = {"a.py": "x = 1\n", "b.py": "y = 2\n", "c.py": "z = 3\n"}

		readings = module_budget_readings(ownership, budgets, sources=sources)

		assert readings["over"].within is False
		assert readings["over"].files == 2
		assert readings["inside"].within is True

	def test_a_sealed_file_that_was_not_read_is_unmeasured(self) -> None:
		"""``within=None`` rather than ``False``: a missing file is not a small one, and it
		is not an oversized one either."""
		budgets = {
			"a": ModuleBudget(max_files=4, max_loc=40, reasoning_class=ReasoningClass.THROUGHPUT)
		}

		readings = module_budget_readings({"a": ("a.py", "b.py")}, budgets, sources={"a.py": ""})

		assert readings["a"].within is None
		assert readings["a"].unread == ("b.py",)


class TestTheCeilingAndTheLevel:
	"""§5.1's second and third lines, and the ``min`` that makes the floor a lowering."""

	def test_a_strong_lane_at_l4_is_capped_by_its_class(self) -> None:
		"""§14's class ceiling is the lane's own: a G5 module does not inherit L4 because
		someone wrote a strong oracle for it (FR-125)."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract, module_class=ModuleClass.G5),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			boundary=boundary(),
			within_budget=True,
		)

		assert decision.strength_ceiling is AutonomyLevel.L4
		assert decision.class_ceiling is AutonomyLevel.L2
		assert decision.ceiling is AutonomyLevel.L2
		assert decision.level is AutonomyLevel.L2

	def test_a_weak_lane_is_capped_by_the_table(self) -> None:
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 0.2),
			within_budget=True,
			boundary=boundary(),
		)

		assert decision.strength_ceiling is AutonomyLevel.L1
		assert decision.ceiling is AutonomyLevel.L1

	def test_the_lane_strength_is_the_weakest_clause(self) -> None:
		"""A lane is only as verifiable as its least verifiable part — the rule
		:attr:`Contract.weakest_oracle_rank` already applies to ranks."""
		strong, weak = clause(), clause()
		contract = contract_of(strong, weak)
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths={strong.id: 0.95, weak.id: 0.65},
			within_budget=True,
			boundary=boundary(),
		)

		assert decision.strength == 0.65
		assert decision.strength_ceiling is AutonomyLevel.L3

	def test_one_unmeasured_clause_makes_the_lane_undecided(self) -> None:
		"""Not a mean over the measured subset: a mean over a subset nobody chose is a
		number about that subset, and the clause left out is the one that would have
		lowered it."""
		measured, unmeasured = clause(), clause()
		contract = contract_of(measured, unmeasured)
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths={measured.id: 0.95},
			within_budget=True,
			boundary=boundary(),
		)

		assert decision.strength is None
		assert decision.strength_ceiling is None
		assert decision.ceiling is None
		assert decision.level is None
		assert not decision.decided
		assert "FR-009's table cannot be read" in decision.undecided[0]

	def test_no_strengths_at_all_is_undecided_rather_than_low(self) -> None:
		"""The default path: FR-105's instrument is opt-in, so a report rendered without it
		has no number. The lane is *undecided*, which is the distinction
		:attr:`RouteDecision.level` being ``None`` rather than ``L1`` exists for."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract),
			contract=contract,
			specification=specification,
			draft=draft,
			within_budget=True,
			boundary=boundary(),
		)

		assert decision.level is None
		assert not decision.decided
		assert decision.admissible, "and the lane is admissible — nothing about it failed"

	def test_a_concerns_floor_lowers_the_level(self) -> None:
		"""§5.1's third line. G4's class ceiling is L3, so a floor of L1 lowers it."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract, module_class=ModuleClass.G4),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			boundary=boundary(),
			within_budget=True,
			floors=(
				ConcernsFloor(
					lane=ModuleClass.G4,
					level=AutonomyLevel.L1,
					reason="this module touches the migration chain",
					declared_by="operator",
				),
			),
		)

		assert decision.ceiling is AutonomyLevel.L3
		assert decision.concerns_floor is AutonomyLevel.L1
		assert decision.level is AutonomyLevel.L1

	def test_the_built_in_floor_applies_with_no_declaration(self) -> None:
		"""G7 is L1 by §14 and by NFR-018, so a G7 lane is L1 with nothing declared."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract, module_class=ModuleClass.G7),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			boundary=boundary(),
			within_budget=True,
		)

		assert decision.concerns_floor is AutonomyLevel.L1
		assert decision.level is AutonomyLevel.L1

	def test_an_inadmissible_lane_has_no_ceiling_and_names_the_term(self) -> None:
		"""FR-026's escalation: a lane over its bound does not get a lowered ceiling, it
		gets *no* ceiling — the difference between "you may do less" and "you may not"."""
		contract = contract_of(clause(executable=False))
		specification, draft = specification_for(contract)

		decision = route(
			module_of(contract),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			boundary=boundary(),
			within_budget=True,
		)

		assert not decision.admissible
		assert decision.ceiling is None
		assert decision.level is None
		assert [t.name for t in decision.refused_by] == ["oracle_exists"]
		assert any("oracle_exists (FR-108)" in reason for reason in decision.undecided)

	def test_topology_is_applied_to_the_ceiling(self) -> None:
		"""§5.4's ``h(deployment_isolation)``, applied through the one function that clamps
		at L0 and asserts no modifier raises a level.

		Two facts, tested apart because conflating them is the R2 failure — "autonomy
		depends on isolation (FR-019) that is asserted but never verified". A *declared*
		T1 pays the ``-1``; a T1 that was then *measured* to confine its children does not,
		which is :func:`~sofact.views.topology_ceiling`'s documented override.

		A **G3** lane, because its class ceiling is L3: FR-027's permission cap binds at L4
		and would flatten every comparison here to L3, which is a fact about permission
		rather than about §5.4's modifier. A lane that never reaches L4 is where the table
		can be read on its own.
		"""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)

		def ceiling_at(
			topology: DeploymentTopology, *, measured: DeploymentBoundary | None = None
		) -> AutonomyLevel | None:
			return route(
				module_of(contract, module_class=ModuleClass.G3),
				contract=contract,
				specification=specification,
				draft=draft,
				strengths=strengths_for(contract, 1.0),
				topology=topology,
				boundary=measured,
				within_budget=True,
			).ceiling

		assert ceiling_at(DeploymentTopology.T1) is AutonomyLevel.L2
		assert ceiling_at(DeploymentTopology.T2) is AutonomyLevel.L3

		# The measurement, both ways round: a probe that held restores the baseline a
		# degraded declaration gave up, and one that found nothing does not.
		assert ceiling_at(DeploymentTopology.T1, measured=boundary()) is AutonomyLevel.L3
		assert ceiling_at(DeploymentTopology.T1, measured=boundary(enforced=False)) is (
			AutonomyLevel.L2
		)


class TestTheSentenceNamesTheBindingTerm:
	"""FR-030's reason one level up: a number with no account of which term produced it is
	a number to trust rather than a fact to check."""

	def test_the_concerns_floor_is_named_when_it_binds(self) -> None:
		contract = contract_of(clause())
		specification, draft = specification_for(contract)
		decision = route(
			module_of(contract, module_class=ModuleClass.G4),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			boundary=boundary(),
			within_budget=True,
			floors=(
				ConcernsFloor(
					lane=ModuleClass.G4,
					level=AutonomyLevel.L1,
					reason="touches the migration chain",
					declared_by="operator",
				),
			),
		)

		statement = route_statement(decision)

		assert "L1" in statement
		assert "bound by the concerns floor" in statement

	def test_the_class_ceiling_is_named_when_it_binds(self) -> None:
		contract = contract_of(clause())
		specification, draft = specification_for(contract)
		decision = route(
			module_of(contract, module_class=ModuleClass.G5),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			boundary=boundary(),
			within_budget=True,
		)

		statement = route_statement(decision)

		assert "class ceiling for G5" in statement

	def test_an_undecided_lane_says_so_rather_than_naming_a_level(self) -> None:
		"""The worst failure this sentence could have is printing a level for a lane nothing
		decided, so it prints the reason instead and the word "no level"."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)
		decision = route(
			module_of(contract),
			contract=contract,
			specification=specification,
			draft=draft,
			within_budget=True,
			boundary=boundary(),
		)

		statement = route_statement(decision)

		assert "no level" in statement
		assert "L4" not in statement and "L3" not in statement

	def test_the_topology_is_in_every_sentence(self) -> None:
		"""FR-030 requires the topology "reported in every oracle report"."""
		contract = contract_of(clause())
		specification, draft = specification_for(contract)
		decision = route(
			module_of(contract),
			contract=contract,
			specification=specification,
			draft=draft,
			strengths=strengths_for(contract, 1.0),
			topology=DeploymentTopology.T2,
			boundary=boundary(),
			within_budget=True,
		)

		assert "T2" in route_statement(decision)


class TestTheServiceFoldsTheLogIntoDecisions:
	"""The call site: a contract's lanes, routed from what the log holds."""

	async def test_every_lane_of_an_approved_decomposition_is_routed(
		self, home: Path, tmp_path: Path
	) -> None:
		service = synthetic_service(home, tmp_path, "ok")
		_, contract_id = await gated_contract(service)

		decisions = await service.routing_report(contract_id)

		state = await service.state()
		decomposition = state.latest_decomposition(contract_id)
		assert decomposition is not None
		assert len(decisions) == len(decomposition.modules)
		assert {d.module for d in decisions} == {m.name for m in decomposition.modules}

	def test_a_contract_with_no_decomposition_is_refused_by_name(
		self, home: Path, tmp_path: Path
	) -> None:
		"""An empty tuple would read as "every lane is fine", which is the wrong reading for
		a contract nobody decomposed.

		The refusal is ``require_approved_decomposition``'s own sentence — FR-061's hard
		stop, naming P3 and FR-087 — carried out as a :class:`RoutingRefusal` rather than a
		``ValueError``. Both halves are asserted: the *gate* is named, and the type is the
		one ``sofact route`` catches, because a refusal that reached the operator as a
		traceback is the failure every other verb's test guards against.
		"""
		import asyncio

		from synthetic import elicitation_to_contract

		async def run() -> None:
			service = synthetic_service(home, tmp_path, "ok")
			_, contract_id = await elicitation_to_contract(service)
			with pytest.raises(RoutingRefusal, match=r"P3 is a gate.*FR-087"):
				await service.routing_report(contract_id)

		asyncio.run(run())

	async def test_the_report_is_undecided_without_the_measurement(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-105's instrument is opt-in, so the default report is undecided rather than
		decided low — and every lane says why."""
		service = synthetic_service(home, tmp_path, "ok")
		_, contract_id = await gated_contract(service)

		decisions = await service.routing_report(contract_id)

		assert decisions
		for decision in decisions:
			assert decision.level is None
			assert not decision.decided

	async def test_a_contract_the_log_does_not_hold_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		service = synthetic_service(home, tmp_path, "ok")

		with pytest.raises(RoutingRefusal, match="no contract"):
			await service.routing_report("01HZZZZZZZZZZZZZZZZZZZZZZZ")


class TestTheRoutingVerb:
	"""``sofact route`` — the decision on a screen, with a non-zero exit when undecided."""

	def test_a_routed_contract_prints_every_lane_and_exits_non_zero_when_undecided(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Exit 1 rather than 0: a routing table an operator reads as a green light must not
		include a lane nothing decided, and the code is what a script reads."""
		import asyncio

		from synthetic import gated_contract as build
		from typer.testing import CliRunner

		from sofact.cli import app

		runner = CliRunner()

		async def setup() -> str:
			service = synthetic_service(home, tmp_path, "ok")
			_, contract_id = await build(service)
			return contract_id

		contract_id = asyncio.run(setup())

		result = runner.invoke(app, ["--home", str(home), "route", "--contract", contract_id])

		assert "§5.1's routing function" in result.output
		assert "undecided" in result.output
		assert result.exit_code == 1, result.output
		assert "Traceback" not in result.output

	def test_an_unreadable_floor_table_is_a_message_not_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		from typer.testing import CliRunner

		from sofact.cli import app

		monkeypatch.setenv(CONCERNS_FLOORS_ENV, str(tmp_path / "absent.json"))

		result = CliRunner().invoke(app, ["--home", str(home), "route", "--contract", uuid7str()])

		assert result.exit_code == 1, result.output
		assert f"cannot read {CONCERNS_FLOORS_ENV}" in result.output
		assert "Traceback" not in result.output


class TestTheFlagAdmitsATargetAndNotALane:
	"""ADR-0076's distinction, asserted where a reader would look for the collapse."""

	def test_the_flag_is_true_and_the_number_is_fr_009s(self) -> None:
		from sofact.views import THETA_GATE_BUILT

		assert THETA_GATE_BUILT is True
		assert DEFAULT_THETA.hi == L4_GATE_THETA

	def test_an_unmeasured_lane_is_still_not_l4(self) -> None:
		"""The gate can be decided; this lane has not been. ``oracle_strength_ceiling(None)``
		is the function that keeps the two apart, and it is asserted here as well as in the
		table class because this is the class about the flag."""
		assert oracle_strength_ceiling(None) is None

	def test_every_class_ceiling_is_at_or_below_l4(self) -> None:
		"""§14's table as a sanity check on the arithmetic: no class ceiling can exceed L4,
		so ``min`` never has to clamp from above."""
		assert all(int(level) <= int(AutonomyLevel.L4) for level in MODULE_CLASS_CEILING.values())


def test_the_module_class_ceilings_and_floors_do_not_contradict() -> None:
	"""A class with a floor above its own ceiling would be a lane no declaration could
	reach, which is the shape FR-024's refusal exists to prevent at the table level."""
	for lane, floor in CONCERNS_FLOOR.items():
		assert int(floor) <= int(MODULE_CLASS_CEILING[lane]), lane


def test_router_reports_the_same_fixture_under_both_topologies() -> None:
	"""One canary-shaped reading: the T1/T2 difference is the fixture's and not the
	measurement's, so a change that stopped applying §5.4's modifier would show here.

	A G3 lane with **no measured boundary**, for two reasons that are both the point. The
	class ceiling is L3, so the top of the ladder is not what is being compared and the
	``-1`` is visible as ``L2`` against ``L3``; and no probe means the *declared* topology's
	modifier is the one applied, since an enforced boundary waives T1's penalty by
	:func:`~sofact.views.topology_ceiling`'s documented override — passing one here would
	measure the override rather than the table.
	"""
	contract = contract_of(clause())
	specification, draft = specification_for(contract)
	module = module_of(contract, module_class=ModuleClass.G3)
	strengths = strengths_for(contract, 1.0)

	t1 = route(
		module,
		contract=contract,
		specification=specification,
		draft=draft,
		strengths=strengths,
		topology=DeploymentTopology.T1,
		boundary=None,
		within_budget=True,
	)
	t2 = route(
		module,
		contract=contract,
		specification=specification,
		draft=draft,
		strengths=strengths,
		topology=DeploymentTopology.T2,
		boundary=None,
		within_budget=True,
	)

	assert t1.level is not t2.level
	assert int(t2.level or AutonomyLevel.L0) == int(t1.level or AutonomyLevel.L0) + 1


_ = FactoryService  # imported for the type of `synthetic_service`'s return
