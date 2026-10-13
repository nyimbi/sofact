"""P8 — delivery: the report, the deploy gate, and the handover (FR-117 to FR-121).

Three separable claims are under test. The *types* refuse a report that omits one of
FR-118's statements, a gate that presents a report other than the one it approved, and a
deploy recorded against an unsatisfied gate — so the awkward statement cannot be dropped
and the stale-evidence mistake cannot be made. The *derivation* is where the honesty
lives: a clause with no module has to draw a gap rather than a shorter chain, an
unmeasured dimension has to read as unmeasured, and an autonomy claim has to be the
lower of the two ceilings rather than the flattering one. The *gate* is where the human
half is: nothing in this module deploys, and a failed machine check is not waivable.

The module-level constant :data:`sofact.views.DeliveryReport.VERIFIED_NOT_VALUE` is
tested for the property that matters — that it is a constant on the type rather than a
field, so no code path can write a report claiming the factory certified value.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from synthetic import (
	base_spec,
	decompose_and_approve,
	elicitation_to_contract,
	specify_and_approve,
	synthetic_service,
)

from sofact._uuid7 import uuid7str
from sofact.decomposition import propose
from sofact.delivery import (
	DELIVERY_ARTIFACT_PATHS,
	LANE_ORACLE_KEYWORDS,
	UNPRODUCIBLE,
	artifact,
	ceiling,
	chain,
	handover,
	module_autonomy,
	refused_by_topology,
	report,
	topology_statement,
	verified_and_unverified,
)
from sofact.planner import compile_plan
from sofact.service import FactoryService
from sofact.views import (
	DELIVERY_ARTIFACTS,
	DELIVERY_REQUIREMENTS,
	MODE_G_CEILING,
	MODULE_CLASS_CEILING,
	TOPOLOGY_ISOLATION,
	TOPOLOGY_MODIFIER,
	Assumption,
	AutonomyLevel,
	ClauseKind,
	ClauseStem,
	Contract,
	DeliveryArtifact,
	DeliveryArtifactKind,
	DeliveryEnvelope,
	DeliveryGate,
	DeliveryReport,
	DeploymentTopology,
	DeployRecord,
	ElicitationDimension,
	EnvelopeDimension,
	GateCheck,
	GateCost,
	Handover,
	InheritedOracle,
	MaintenanceLane,
	ModuleClass,
	OracleClass,
	OracleDeclaration,
	Phase,
	PhaseGate,
	PhaseStatus,
	SpecificationDraft,
	TraceLink,
	UnverifiedClause,
	VerdictOutcome,
	VerifiedClause,
	now,
)

BASELINE = DeploymentTopology.T2
"""§5.4's product target, whose ceiling modifier is zero.

FR-122's tests below are about the *lower bound* over the contract's ceiling and the
module classes' — not about the deployment — so they name the baseline topology
explicitly. Leaving the argument off would exercise T1's -1 modifier as well, and a
failure there would be a statement about §5.4 rather than about the minimum this class
tests. The modifier has its own tests, below.
"""


def oracle(
	kind: OracleClass = OracleClass.CONTRACT,
	*,
	command: str | None = None,
) -> OracleDeclaration:
	"""The smallest real oracle, executable when a command is given."""
	return OracleDeclaration(
		oracle_class=kind,
		description=f"a {kind.value} oracle",
		command_hint=command,
	)


def one_clause_contract(
	*statements: str,
	command: str | None = None,
	oracle_class: OracleClass = OracleClass.CONTRACT,
) -> Contract:
	"""A contract built directly, so no elicitation has to run to reach P8.

	``oracle_class`` defaults to ``CONTRACT`` (rank 3, ceiling L3) because that is what
	most of this suite wants: a contract strong enough to be interesting and weak enough
	that a module class can still lower it. A test that needs the *strongest* ceiling —
	L4, which §5.4's worked example is about — passes ``OracleClass.PROPERTY`` (rank 1).
	"""
	text = statements or ("the ledger records entries",)
	stems = tuple(
		ClauseStem(
			id=uuid7str(),
			statement=statement,
			kind=ClauseKind.POSITIVE,
			derived_from=ElicitationDimension.OUTCOME,
		)
		for statement in text
	)
	draft = SpecificationDraft(id=uuid7str(), goal_id=uuid7str(), created_at=now(), stems=stems)
	return Contract.from_draft(
		draft,
		{stem.id: oracle(oracle_class, command=command) for stem in stems},
	)


def a_check(passed: bool = True) -> GateCheck:
	"""One gate check, so a report can be built without running a pipeline."""
	return GateCheck(name="a_check", passed=passed, detail="what the check found")


def a_lane(name: str = "L04", *oracles: InheritedOracle) -> MaintenanceLane:
	"""One maintenance lane, empty of oracles when none are given."""
	return MaintenanceLane(
		lane=name,
		description=f"the {name} lane",
		inherited_oracles=oracles,
		ceiling=AutonomyLevel.L3,
	)


def an_oracle(clause_id: str | None = None, *, command: str | None = "true") -> InheritedOracle:
	"""One inherited oracle, executable unless a command is withheld."""
	return InheritedOracle(
		clause_id=clause_id or uuid7str(),
		statement="the ledger records entries",
		command_hint=command,
		rank=1,
	)


def _a_delivery_root(tmp_path: Path, name: str = "delivery") -> Path:
	"""An empty delivery root to hand :meth:`render_delivery`.

	Empty on purpose. The factory writes the two artefacts FR-117 names that it owes
	(``sofact.writing``), so a test that pre-wrote them would pass whether or not the
	factory produced them — and producing them is the thing under test. The name is the
	CLI suite's for the same helper, so the two suites cannot drift into asserting
	different behaviour about the same directory.

	``name`` exists so a test that renders twice — two topologies over one state
	directory — gives each render its own root. One root would mean the second render
	overwrites the first, and a test comparing the two reports would be comparing a
	report against a document that had already been rewritten under it.
	"""
	root = tmp_path / name
	root.mkdir()
	return root


def a_report(**overrides: object) -> DeliveryReport:
	"""A minimal whole report, so a test can vary one field and see what the type does."""
	clause_id = uuid7str()
	fields: dict[str, object] = {
		"id": uuid7str(),
		"goal_id": uuid7str(),
		"contract_id": uuid7str(),
		"plan_id": uuid7str(),
		"rendered_at": now(),
		"artifacts": tuple(
			DeliveryArtifact(kind=kind, present=False, missing_because="nothing wrote one")
			for kind in DeliveryArtifactKind
		),
		"chain": (
			TraceLink(
				clause_id=clause_id,
				statement="the ledger records entries",
				requirement_id=uuid7str(),
				module="ledger",
				step_ordinal=0,
			),
		),
		"verified": (),
		"unverified": (),
		"unvalidated_assumptions": (),
		"envelope_actuals": None,
		"autonomy": AutonomyLevel.L2,
		"module_autonomy": AutonomyLevel.L2,
		"topology": DeploymentTopology.T1,
		"topology_configured": False,
		"handover": Handover(
			system="the ledger service",
			entry_point="/srv/ledger",
			lanes=(a_lane("L04", an_oracle(clause_id)),),
		),
		"checks": (a_check(),),
	}
	fields.update(overrides)
	return DeliveryReport.model_validate(fields)


# --------------------------------------------------------------------------- #
# FR-118's five statements are fields, and the type refuses four
# --------------------------------------------------------------------------- #


class TestTheFiveStatementsAreFields:
	def test_the_requirements_constant_names_all_of_section_11(self) -> None:
		"""The same rule :data:`INTEGRATION_REQUIREMENTS` states one phase earlier: a
		report that named only the part it implements could not tell a delivered platform
		from a directory of files."""
		assert DELIVERY_REQUIREMENTS == ("FR-117", "FR-118", "FR-119", "FR-120", "FR-121")

	def test_the_four_artefact_kinds_are_the_four_fr_117_names(self) -> None:
		"""FR-117's "container image or equivalent", infrastructure-as-code, runbook and
		report. A kind the code cannot spell is an artefact nothing can be recorded as
		missing, so the report would read as complete."""
		assert [kind.value for kind in DELIVERY_ARTIFACTS] == [
			"image",
			"infrastructure",
			"runbook",
			"report",
		]

	def test_a_report_over_no_clause_is_refused(self) -> None:
		"""FR-117 asks for the chain from intent clause to deployed component; a report
		over no clause traces nothing and is not a report."""
		with pytest.raises(ValidationError, match="traces nothing"):
			a_report(chain=())

	def test_a_report_with_no_artefact_is_refused(self) -> None:
		with pytest.raises(ValidationError, match="reports nothing"):
			a_report(artifacts=())

	def test_two_artefacts_of_one_kind_are_refused(self) -> None:
		"""The check is on *kinds*, not on the count: two runbooks and no image would
		otherwise satisfy a length check while FR-117's fourth kind went unmentioned."""
		twice = (
			DeliveryArtifact(
				kind=DeliveryArtifactKind.RUNBOOK,
				present=False,
				missing_because="nothing wrote one",
			),
			DeliveryArtifact(kind=DeliveryArtifactKind.RUNBOOK, present=True, path="RUNBOOK.md"),
		)

		with pytest.raises(ValidationError, match="share a kind"):
			a_report(artifacts=twice)

	def test_a_report_with_no_check_is_refused(self) -> None:
		with pytest.raises(ValidationError, match="not a report"):
			a_report(checks=())

	def test_a_report_whose_handover_has_no_lane_is_refused(self) -> None:
		"""FR-121 makes the handover the Mode M input. A report whose handover carries no
		lane would leave a delivered system nothing to maintain it under."""
		with pytest.raises(ValidationError, match="no lane"):
			a_report(
				handover=Handover(system="s", entry_point="e", lanes=()),
			)


# --------------------------------------------------------------------------- #
# FR-086's sentence is a constant on the type, not a field
# --------------------------------------------------------------------------- #


class TestValueIsNotCertified:
	def test_the_sentence_is_a_class_constant(self) -> None:
		"""This is the whole of FR-086's delivery half. A *field* would put the claim back
		in the hands of whatever built the report; a ``ClassVar`` makes the sentence
		unavailable to every code path, so a report that omitted it cannot be
		constructed."""
		assert isinstance(DeliveryReport.VERIFIED_NOT_VALUE, str)
		assert "VERIFIED_NOT_VALUE" not in DeliveryReport.model_fields

	def test_every_report_carries_the_same_sentence(self) -> None:
		assert a_report().value_statement == a_report().value_statement
		assert "verified, not value" in a_report().value_statement

	def test_the_sentence_says_the_value_hypothesis_is_untested(self) -> None:
		"""FR-085 makes the value hypothesis falsifiable and FR-086 forbids the factory
		from certifying it, so the sentence has to name what was *not* tested rather than
		only what was."""
		statement = DeliveryReport.VERIFIED_NOT_VALUE

		assert "value" in statement
		assert "untested" in statement or "not tested" in statement


# --------------------------------------------------------------------------- #
# an absence carries a reason, and presence is a filesystem fact
# --------------------------------------------------------------------------- #


class TestAnArtefactIsPresentWhenAFileExists:
	def test_a_present_artefact_names_a_path(self) -> None:
		"""A deploy gate has to be able to open the runbook; "we have one" is not a
		statement an operator can act on."""
		with pytest.raises(ValidationError, match="no path"):
			DeliveryArtifact(kind=DeliveryArtifactKind.RUNBOOK, present=True)

	def test_an_absent_artefact_carries_a_reason(self) -> None:
		with pytest.raises(ValidationError, match="indistinguishable from an oversight"):
			DeliveryArtifact(kind=DeliveryArtifactKind.RUNBOOK, present=False)

	def test_an_absent_artefact_cannot_also_name_a_path(self) -> None:
		with pytest.raises(ValidationError, match="absent and names a path"):
			DeliveryArtifact(
				kind=DeliveryArtifactKind.RUNBOOK,
				present=False,
				path="RUNBOOK.md",
				missing_because="nothing wrote one",
			)

	def test_a_present_artefact_cannot_also_say_why_it_is_not(self) -> None:
		with pytest.raises(ValidationError, match="present and says why it is not"):
			DeliveryArtifact(
				kind=DeliveryArtifactKind.RUNBOOK,
				present=True,
				path="RUNBOOK.md",
				missing_because="nothing wrote one",
			)

	def test_the_two_unproducible_kinds_carry_different_reasons(self) -> None:
		"""The image needs a packaging decision and the IaC needs a named environment, so
		one shared sentence would make the report's two actionable items one vague one."""
		reasons = set(UNPRODUCIBLE.values())

		assert set(UNPRODUCIBLE) == {
			DeliveryArtifactKind.IMAGE,
			DeliveryArtifactKind.INFRASTRUCTURE,
		}
		assert len(reasons) == 2, "the two unproducible kinds need different actions"
		assert not reasons & set(DELIVERY_ARTIFACT_PATHS.values())

	def test_a_missing_file_is_absent_even_when_a_root_is_named(self, tmp_path: Path) -> None:
		"""Presence is a filesystem fact. A caller that could *declare* an artefact present
		would make the report's most load-bearing field an assertion."""
		built = artifact(DeliveryArtifactKind.RUNBOOK, tmp_path)

		assert built.present is False
		assert built.missing_because is not None
		assert "nothing was written" in built.missing_because

	def test_a_written_file_is_present_and_names_its_path(self, tmp_path: Path) -> None:
		(tmp_path / DELIVERY_ARTIFACT_PATHS[DeliveryArtifactKind.RUNBOOK]).write_text(
			"# runbook", encoding="utf-8"
		)

		built = artifact(DeliveryArtifactKind.RUNBOOK, tmp_path)

		assert built.present is True
		assert built.path == "RUNBOOK.md"

	def test_no_root_is_a_different_absence_from_a_root_with_nothing_in_it(
		self, tmp_path: Path
	) -> None:
		"""The two need different actions — write the files, or name where they are — so
		the report distinguishes them rather than printing one "missing"."""
		unnamed = artifact(DeliveryArtifactKind.RUNBOOK, None)
		empty = artifact(DeliveryArtifactKind.RUNBOOK, tmp_path)

		assert unnamed.present is False and empty.present is False
		assert unnamed.missing_because != empty.missing_because
		assert "no delivery root was named" in (unnamed.missing_because or "")

	def test_the_image_is_unproducible_under_any_root(self, tmp_path: Path) -> None:
		"""A packaging decision is not something a delivery root can supply, so naming one
		must not make the image appear present."""
		assert artifact(DeliveryArtifactKind.IMAGE, tmp_path).present is False
		assert artifact(DeliveryArtifactKind.IMAGE, None).present is False


# --------------------------------------------------------------------------- #
# FR-117's chain draws its gaps rather than shortening
# --------------------------------------------------------------------------- #


class TestTheChainDrawsItsGaps:
	def test_a_whole_link_carries_every_hop(self) -> None:
		link = TraceLink(
			clause_id=uuid7str(),
			statement="the ledger records entries",
			requirement_id=uuid7str(),
			module="ledger",
			step_ordinal=3,
		)

		assert link.is_whole is True
		assert "(no " not in link.rendered

	def test_a_link_missing_a_hop_is_not_whole_and_draws_the_gap(self) -> None:
		"""A report that printed a chain stopping at the first missing hop would return a
		shorter chain, and nothing could tell that from a contract with fewer clauses."""
		link = TraceLink(
			clause_id=uuid7str(),
			statement="the ledger records entries",
			requirement_id=uuid7str(),
			module=None,
			step_ordinal=None,
		)

		assert link.is_whole is False
		assert "(no module)" in link.rendered
		assert "(never dispatched)" in link.rendered

	def test_a_clause_with_no_requirement_says_so(self) -> None:
		link = TraceLink(clause_id=uuid7str(), statement="s", module="ledger", step_ordinal=0)

		assert link.is_whole is False
		assert "(no requirement)" in link.rendered

	def test_the_chain_covers_every_clause_and_none_twice(self) -> None:
		"""One link per clause. A chain that dropped a clause would report the clauses it
		happened to walk and read as complete."""
		contract = one_clause_contract("one", "two", "three")

		links = chain(contract, None, None, requirement_for_clause={})

		assert len(links) == len(contract.clauses)
		assert len({link.clause_id for link in links}) == len(contract.clauses)

	def test_with_no_decomposition_and_no_plan_every_hop_is_a_gap(self) -> None:
		"""The honest state of a project delivered without a specification or a plan. The
		report is the last place to raise, so it states it instead."""
		contract = one_clause_contract("one")

		links = chain(contract, None, None, requirement_for_clause={})

		assert all(not link.is_whole for link in links)
		assert links[0].requirement_id is None
		assert links[0].module is None
		assert links[0].step_ordinal is None

	def test_a_requirement_hop_is_taken_from_the_map_it_is_given(self) -> None:
		"""Clause-to-requirement is P2's declaration, minted by ``specify`` rather than
		derived here, so the chain reports the requirement the specification actually
		holds rather than one this module guessed."""
		contract = one_clause_contract("one")
		clause = contract.clauses[0]
		requirement_id = uuid7str()

		links = chain(contract, None, None, requirement_for_clause={clause.id: requirement_id})

		assert links[0].requirement_id == requirement_id


# --------------------------------------------------------------------------- #
# FR-118's first two statements split on the verdict, not on the oracle
# --------------------------------------------------------------------------- #


class TestVerifiedAndUnverified:
	def test_only_a_satisfied_clause_is_verified(self) -> None:
		"""``INSUFFICIENT`` and ``VIOLATED`` are both unverified — the second is worse,
		not better — so a split on "did the oracle run" would report a violated clause as
		verified."""
		contract = one_clause_contract("one", "two", "three")
		first, second, third = (clause.id for clause in contract.clauses)

		verified, unverified = verified_and_unverified(
			contract,
			{
				first: VerdictOutcome.SATISFIED,
				second: VerdictOutcome.INSUFFICIENT,
				third: VerdictOutcome.VIOLATED,
			},
		)

		assert [v.clause_id for v in verified] == [first]
		assert {u.clause_id for u in unverified} == {second, third}

	def test_a_clause_with_no_verdict_is_ground_truth_debt(self) -> None:
		"""FR-108's debt fraction counts clauses no machine can check, so a clause whose
		oracle never ran has to be distinguishable from one that ran and could not
		decide — the two need different repairs."""
		contract = one_clause_contract("one")

		_, unverified = verified_and_unverified(contract, {})

		assert unverified[0].outcome is None
		assert unverified[0].is_ground_truth_debt is True

	def test_a_clause_whose_oracle_ran_is_not_ground_truth_debt(self) -> None:
		contract = one_clause_contract("one")
		clause = contract.clauses[0]

		_, unverified = verified_and_unverified(contract, {clause.id: VerdictOutcome.VIOLATED})

		assert unverified[0].outcome is VerdictOutcome.VIOLATED
		assert unverified[0].is_ground_truth_debt is False
		assert "build defect" in unverified[0].because

	def test_the_reason_for_a_prose_oracle_differs_from_an_executable_one(self) -> None:
		"""Both are debt, but one is retired by writing a command and the other by
		running one — so the report says which rather than printing one reason."""
		prose = one_clause_contract("one")
		executable = one_clause_contract("one", command="true")

		_, prose_unverified = verified_and_unverified(prose, {})
		_, executable_unverified = verified_and_unverified(executable, {})

		assert "prose" in prose_unverified[0].because
		assert "prose" not in executable_unverified[0].because
		assert "would decide it" in executable_unverified[0].because

	def test_a_verified_clause_reports_its_declared_rank_as_declared(self) -> None:
		"""FR-118 asks for the oracle *at which measured strength*. Nothing measures one,
		so printing the declared rank under the word "measured" would be the exact
		euphemism FR-118 forbids."""
		contract = one_clause_contract("one", command="true")
		clause = contract.clauses[0]

		verified, _ = verified_and_unverified(contract, {clause.id: VerdictOutcome.SATISFIED})

		assert verified[0].measured is False
		assert "not measured" in verified[0].rendered
		assert "measured 1" not in verified[0].rendered

	def test_an_unverified_clause_renders_its_own_words_and_its_verdict(self) -> None:
		"""FR-118 asks the report to state *which* clauses are unverified. A list of
		UUIDs makes the operator open the log to learn what was verified, which is the
		report failing to be one."""
		clause = UnverifiedClause(
			clause_id=uuid7str(),
			statement="a reminder is never delivered twice",
			outcome=VerdictOutcome.VIOLATED,
			because="the oracle ran and the clause was violated",
		)

		assert "never delivered twice" in clause.rendered
		assert "violated" in clause.rendered
		assert clause.clause_id not in clause.rendered

	def test_a_clause_whose_oracle_never_ran_says_so_rather_than_naming_a_verdict(self) -> None:
		clause = UnverifiedClause(
			clause_id=uuid7str(),
			statement="s",
			outcome=None,
			because="no verdict was ever rendered",
		)

		assert "never run" in clause.rendered
		assert "None" not in clause.rendered

	def test_a_verified_clause_renders_its_own_words(self) -> None:
		clause = VerifiedClause(
			clause_id=uuid7str(),
			statement="a reminder appears within five seconds",
			oracle_class=OracleClass.CONTRACT,
			rank=3,
		)

		assert "within five seconds" in clause.rendered
		assert clause.clause_id not in clause.rendered

	def test_a_measured_strength_would_be_reported_as_measured(self) -> None:
		"""The other arm, so the rendering is a branch on the value rather than a
		constant that would read the same either way."""
		clause = VerifiedClause(
			clause_id=uuid7str(),
			statement="s",
			oracle_class=OracleClass.PROPERTY,
			rank=1,
			measured_strength=0.87,
		)

		assert clause.measured is True
		assert "measured 0.87" in clause.rendered


# --------------------------------------------------------------------------- #
# FR-122/FR-123 — two numbers: what the modules sustain, and what the delivery claims
# --------------------------------------------------------------------------- #


class TestTheModulesCeiling:
	"""FR-122: the lower of the contract's measured ceiling and every module class's."""

	def test_a_contract_alone_gives_its_own_ceiling(self) -> None:
		contract = one_clause_contract("one", command="true")

		assert module_autonomy(contract, None, topology=BASELINE) == contract.ceiling

	def test_a_module_class_can_lower_the_delivery_below_the_contract(self) -> None:
		"""FR-126 makes a G7 module — auth, secrets, payments, PII — human-authored
		regardless of how strong the oracles are, so a delivery reporting the contract's
		ceiling alone would claim an autonomy a module forbids.

		The G7 class comes from the clause's own words, because that is how
		:func:`~sofact.decomposition.classify` assigns it — a test that forced the class
		would be testing a rule production does not have.
		"""
		contract = one_clause_contract(
			"the password reset flow authenticates a user", command="true"
		)
		assert contract.ceiling > MODULE_CLASS_CEILING[ModuleClass.G7]

		decomposition = propose(contract)

		assert {module.module_class for module in decomposition.modules} == {ModuleClass.G7}
		assert (
			module_autonomy(contract, decomposition, topology=BASELINE)
			== MODULE_CLASS_CEILING[ModuleClass.G7]
		)

	def test_no_module_can_raise_the_ceiling_above_the_contract(self) -> None:
		"""The other direction, which is why the rule is a minimum rather than a lookup:
		a weak oracle caps the contract, and a G1 module does not undo that."""
		weak = one_clause_contract("the ledger records entries")
		assert weak.ceiling < MODULE_CLASS_CEILING[ModuleClass.G1]

		decomposition = propose(weak)

		assert module_autonomy(weak, decomposition, topology=BASELINE) == weak.ceiling

	def test_the_lowest_module_class_governs_when_several_disagree(self) -> None:
		"""Three clauses, three classes, and the delivery claims the lowest — the whole
		point of a minimum over a set rather than a lookup of one."""
		contract = one_clause_contract(
			"the ledger records entries",
			"a migration adds the ledger table",
			"the password reset flow authenticates a user",
			command="true",
		)

		decomposition = propose(contract)
		classes = {module.module_class for module in decomposition.modules}

		assert len(classes) > 1, "the fixture must exercise a disagreement"
		assert module_autonomy(contract, decomposition, topology=BASELINE) == min(
			MODULE_CLASS_CEILING[module_class] for module_class in classes
		)
		assert (
			module_autonomy(contract, decomposition, topology=BASELINE)
			== MODULE_CLASS_CEILING[ModuleClass.G7]
		)


class TestTheModeGCap:
	"""FR-123: the delivery is L2 however strong the modules are, and both are reported."""

	def test_a_delivery_is_never_above_l2(self) -> None:
		"""The requirement's whole content, and the reason it is a cap rather than a
		lookup: a contract of strong oracles admits L4 for its modules, and the *delivery*
		is still L2 because P2, P3 and P8 are human gates."""
		strong = one_clause_contract("the ledger records entries", command="true")
		assert strong.ceiling > MODE_G_CEILING, "the fixture must reach above the cap"

		assert ceiling(strong, None, topology=BASELINE) == MODE_G_CEILING
		assert module_autonomy(strong, None, topology=BASELINE) == strong.ceiling

	def test_the_cap_applies_with_no_decomposition(self) -> None:
		"""A cap that failed open on missing input would be no cap: the decomposition is
		the *lowering* half of FR-122, and the ceiling is the *capping* half of FR-123,
		so the second has to hold when the first has nothing to say."""
		strong = one_clause_contract("the ledger records entries", command="true")

		assert ceiling(strong, None, topology=BASELINE) == MODE_G_CEILING
		assert ceiling(strong, None, topology=BASELINE) <= module_autonomy(
			strong, None, topology=BASELINE
		)

	def test_a_g7_module_does_not_raise_the_delivery_to_the_cap(self) -> None:
		"""The cap is a ceiling, not a floor. A G7 module caps at L1 (FR-126), so a
		delivery whose weakest class is G7 reports L1 — and a rule written as "the
		delivery is L2" rather than "at most L2" would report the flattering number."""
		contract = one_clause_contract(
			"the password reset flow authenticates a user", command="true"
		)
		decomposition = propose(contract)

		assert (
			ceiling(contract, decomposition, topology=BASELINE)
			== MODULE_CLASS_CEILING[ModuleClass.G7]
		)
		assert ceiling(contract, decomposition, topology=BASELINE) < MODE_G_CEILING

	async def test_the_report_states_both_numbers(self, home: Path, tmp_path: Path) -> None:
		"""FR-123 asks for the *distinction*, not the lower number: "individual modules
		may run at L4 internally; the delivery is L2". One number cannot state one, and a
		report carrying only the capped value would read as a pipeline that cannot build
		above L2 — a different and false claim."""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)

		report = await service.render_delivery(plan.id, root=_a_delivery_root(tmp_path))

		assert report.autonomy <= MODE_G_CEILING
		assert report.module_autonomy >= report.autonomy
		check = next(c for c in report.checks if c.name == "autonomy_capped_for_mode_g")
		assert check.passed is True
		assert report.module_autonomy.name in check.detail


async def _walk_to_the_specification_gate(service: FactoryService) -> None:
	"""Complete P0 and P1, present P2's gate and pass it (FR-061).

	Written out rather than imported from ``test_phase``, which is a test module and not
	a shared fixture: a suite that imported another suite's helper would break the moment
	that helper changed shape for its own reasons.
	"""
	await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
	await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE)
	await service.approve_gate(Phase.SPECIFY, by="operator")


# --------------------------------------------------------------------------- #
# FR-124/FR-030/FR-031/FR-042 — the deployment modifies the ceiling, and says so
# --------------------------------------------------------------------------- #


class TestTheTopologyIsATypeNotAComment:
	"""FR-124: §5.4's four deployments, as data rather than prose in a spec.

	§5.4's principle is that the same lane has different admissible ceilings on different
	hardware, so the topology is an input to the autonomy computation and not an
	operational note. Before this, "T1" existed only in ``product-spec-old.md`` §5.4 and
	no code could name it.
	"""

	def test_every_topology_has_an_isolation_and_a_modifier(self) -> None:
		"""FR-030 asks for the isolation and the modifier *reported*, so a table missing
		either would make the requirement unstatable for that topology. The two tables
		are keyed by the same enum, and this asserts neither has a hole."""
		assert set(TOPOLOGY_MODIFIER) == set(DeploymentTopology)
		assert set(TOPOLOGY_ISOLATION) == set(DeploymentTopology)

	def test_only_the_degraded_topology_lowers_the_ceiling(self) -> None:
		"""§5.4's table read back: T1 is -1, T2 and T3 are baseline, T4 is +0. A modifier
		that *raised* a level would be a deployment claiming autonomy its isolation does
		not support, which is R2's silent unsafety."""
		assert TOPOLOGY_MODIFIER[DeploymentTopology.T1] == -1
		assert TOPOLOGY_MODIFIER[DeploymentTopology.T2] == 0
		assert TOPOLOGY_MODIFIER[DeploymentTopology.T3] == 0
		assert TOPOLOGY_MODIFIER[DeploymentTopology.T4] == 0
		assert all(modifier <= 0 for modifier in TOPOLOGY_MODIFIER.values())

	def test_t1_lowers_a_strong_contract_by_exactly_one_level(self) -> None:
		"""§5.4's own worked example: "L4 lanes run at L3". A contract of rank-1 oracles
		reaches L4 through ``ceiling_for_rank``; at T1 the *modules'* number is L3."""
		strong = one_clause_contract(
			"the ledger records entries", command="true", oracle_class=OracleClass.PROPERTY
		)
		assert strong.ceiling is AutonomyLevel.L4, "the fixture must reach L4"

		assert module_autonomy(strong, None, topology=DeploymentTopology.T1) is AutonomyLevel.L3
		assert module_autonomy(strong, None, topology=DeploymentTopology.T2) is AutonomyLevel.L4

	def test_the_modifier_does_not_push_a_level_below_l0(self) -> None:
		"""A G7 module caps at L1 (FR-126), and §5.4's modifier is -1, so the arithmetic
		reaches L0 rather than -1. The clamp is asserted here because the alternative is
		an ``IntEnum`` value that does not exist, which would raise at the point a report
		is rendered rather than at the point a table is edited."""
		g7 = one_clause_contract("the password reset flow authenticates a user", command="true")
		decomposition = propose(g7)
		assert MODULE_CLASS_CEILING[ModuleClass.G7] is AutonomyLevel.L1

		assert (
			module_autonomy(g7, decomposition, topology=DeploymentTopology.T1) is AutonomyLevel.L0
		)

	def test_the_delivery_cap_is_not_lowered_a_second_time(self) -> None:
		"""FR-123's L2 is at or below every topology's number, so applying §5.4's modifier
		to the *delivery* would report T1 as L1 for a reason §5.4 does not state. The
		modifier reaches the delivery only through the modules' number."""
		strong = one_clause_contract("the ledger records entries", command="true")

		for topology in DeploymentTopology:
			assert ceiling(strong, None, topology=topology) is MODE_G_CEILING

	def test_the_default_topology_is_the_degraded_one(self) -> None:
		"""A ceiling that failed open on an unconfigured deployment is the one failure a
		ceiling may not have, so the default is T1 rather than the product target. This
		is the same argument ADR-0041 makes about FR-123's cap being a constant."""
		strong = one_clause_contract("the ledger records entries", command="true")

		assert module_autonomy(strong, None) is module_autonomy(
			strong, None, topology=DeploymentTopology.T1
		)


class TestTheTopologyRefusesRatherThanDowngrades:
	"""FR-031: a lane that would be L4 in T2 is **refused** at T1, not silently lowered.

	The distinction is the whole requirement: a lane running at L3 in T1 because the
	deployment lowered it and one whose oracles never supported L4 are two different facts
	about the world, and only the first is lifted by moving to T2. A silent downgrade
	collapses them into one number.
	"""

	def test_a_class_that_would_be_l4_in_t2_is_refused_at_t1(self) -> None:
		"""G1 is L4 through ``MODULE_CLASS_CEILING``, so T1 refuses it. The refusal names
		the module and the class, because a refusal an operator cannot locate is a refusal
		they will route around."""
		contract = one_clause_contract("the ledger records entries", command="true")
		decomposition = propose(contract)
		assert MODULE_CLASS_CEILING[ModuleClass.G1] is AutonomyLevel.L4

		refused = refused_by_topology(contract, decomposition, topology=DeploymentTopology.T1)

		assert len(refused) == 1, "the fixture must propose exactly one L4 class"
		assert decomposition.modules[0].name in refused[0]
		assert "L4" in refused[0]

	def test_the_same_classes_are_admitted_at_t2(self) -> None:
		"""The other half, and it is what makes the first a *deployment* refusal rather
		than a general one: at the baseline topology nothing is refused."""
		contract = one_clause_contract("the ledger records entries", command="true")
		decomposition = propose(contract)

		for topology in (
			DeploymentTopology.T2,
			DeploymentTopology.T3,
			DeploymentTopology.T4,
		):
			assert refused_by_topology(contract, decomposition, topology=topology) == ()

	def test_a_class_that_never_reached_l4_is_not_refused(self) -> None:
		"""FR-031 refuses L4-at-T2, not "anything T1 lowers". A G5 module caps at L2
		(FR-126), so T1's modifier lowers it to L1 without a refusal — and refusing it
		would make the requirement fire on the ordinary case."""
		contract = one_clause_contract("the dashboard renders a chart", command="true")
		decomposition = propose(contract)
		assert MODULE_CLASS_CEILING[decomposition.modules[0].module_class] < AutonomyLevel.L4

		assert refused_by_topology(contract, decomposition, topology=DeploymentTopology.T1) == ()

	def test_an_undecomposed_contract_refuses_nothing_and_still_loses_a_level(self) -> None:
		"""A contract with no decomposition has no class to refuse, so the refusal list is
		empty — but the *modifier* still applies through the contract's own ceiling.
		Without this, "not yet decomposed" would be a way to escape §5.4 entirely."""
		strong = one_clause_contract("the ledger records entries", command="true")

		assert refused_by_topology(strong, None, topology=DeploymentTopology.T1) == ()
		assert module_autonomy(strong, None, topology=DeploymentTopology.T1) < strong.ceiling


class TestTheRefusalReachesTheGate:
	"""FR-031's refusal is a *gate check*, not only a function.

	A control that exists is not a control that is applied. ``refused_by_topology``
	being correct says nothing about whether a delivery that a topology refuses can be
	approved — so what is asserted here is the path from the refusal to the gate. No
	separate enforcement was written: the check is a machine check and ``approve_deploy``
	already raises on any failed machine check, which is exactly the property worth
	confirming rather than assuming.
	"""

	def _a_delivery(
		self,
		*,
		topology: DeploymentTopology,
		override: str | None = None,
	) -> DeliveryReport:
		"""A whole report for a contract whose only module class is L4 (G1)."""
		contract = one_clause_contract("the ledger records entries", command="true")
		decomposition = propose(contract)
		assert MODULE_CLASS_CEILING[decomposition.modules[0].module_class] is AutonomyLevel.L4, (
			"the fixture must propose the class FR-031 is about"
		)
		return report(
			contract,
			goal_id=contract.goal_id,
			plan=compile_plan(contract),
			decomposition=decomposition,
			specification=None,
			verdicts={},
			envelope_actuals=None,
			system="the ledger service",
			entry_point="/srv/ledger",
			topology=topology,
			topology_configured=True,
			topology_override=override,
		)

	def _refusal_check(self, rendered: DeliveryReport) -> GateCheck:
		return next(
			check
			for check in rendered.checks
			if check.name == "topology_refuses_l4_at_a_degraded_deployment"
		)

	def test_an_l4_class_fails_the_check_at_t1(self) -> None:
		"""The refusal is a failed machine check, so it is not waivable by approving: a
		deploy over this report is refused, and refused by the check rather than by a
		sentence in a document."""
		rendered = self._a_delivery(topology=DeploymentTopology.T1)

		assert self._refusal_check(rendered).passed is False
		assert rendered.passed is False
		assert "topology_refuses_l4_at_a_degraded_deployment" in {
			check.name for check in rendered.failed
		}

	def test_the_same_contract_passes_the_check_at_the_baseline(self) -> None:
		"""The other direction, and it is what makes the first a deployment refusal
		rather than a general one: at T2 the identical contract and decomposition pass.

		Only the refusal check is asserted green. The report as a whole also carries the
		artefact check, and no root is named here, so the two owed artefacts are absent
		by design — a test that asserted ``report.passed`` would be asserting the
		fixture wrote files it deliberately did not write.
		"""
		rendered = self._a_delivery(topology=DeploymentTopology.T2)

		assert self._refusal_check(rendered).passed is True
		assert "topology_refuses_l4_at_a_degraded_deployment" not in {
			check.name for check in rendered.failed
		}

	def test_a_recorded_override_is_what_fr_031_asks_for_instead(self) -> None:
		"""FR-031's alternative is an *explicit operator override*, and the override has
		to name who accepted it: an unnamed override is indistinguishable from the silent
		downgrade the requirement forbids. The name reaches the check's own detail, which
		is what makes the log's record of it checkable rather than a flag that was set.

		The refusal's *own words* stay in the detail, and they should: what was refused is
		part of the record of what was accepted. What must not stay is the instruction to
		do the thing the operator has already done — a check that still says "record an
		override" over a recorded override is one a reader learns to skim.
		"""
		rendered = self._a_delivery(topology=DeploymentTopology.T1, override="ada")

		check = self._refusal_check(rendered)
		assert check.passed is True
		assert "ada" in check.detail
		assert "Record an explicit operator override" not in check.detail
		assert "L4" in check.detail, "what was refused is still named"


class TestTheReportStatesWhereItRan:
	"""FR-030/FR-042: the topology, its isolation and its modifier, on the report."""

	def test_the_statement_names_all_three_things_fr_030_asks_for(self) -> None:
		"""A modifier reported without its isolation is a number to trust rather than a
		fact to check, which is R2's failure mode. The three are joined in one function
		so a report, a gate check and a rendered document cannot disagree."""
		stated = topology_statement(DeploymentTopology.T2, configured=True)

		assert "T2" in stated
		assert TOPOLOGY_ISOLATION[DeploymentTopology.T2] in stated
		assert "-1" not in stated, "T2 is baseline, and the statement must not read as lowered"

	def test_an_undeclared_topology_says_so_rather_than_reading_as_a_choice(self) -> None:
		"""FR-042's requirement in one assertion: the dev instance "must report its
		degraded ceiling rather than silently behaving as if it were T2". A factory that
		never declared a topology and one that chose T1 both report T1, and only the
		report can tell an operator which they have."""
		declared = topology_statement(DeploymentTopology.T1, configured=True)
		undeclared = topology_statement(DeploymentTopology.T1, configured=False)

		assert declared != undeclared
		assert "not declared" in undeclared
		assert "not declared" not in declared

	async def test_a_rendered_report_carries_the_topology_and_its_checks(
		self, home: Path, tmp_path: Path
	) -> None:
		"""End to end: the field, the modifier applied to the modules' number, and both
		topology checks present. The checks are asserted by name because a report that
		carried the field but no check would state a premise nothing acted on.

		The level is asserted as an *equality with the pure function* rather than against
		a constant: what class the synthetic clauses land in is the classifier's business
		and not this test's, and pinning it here would make a classification change look
		like a topology regression. What is under test is the seam — that the number on
		the report is the number for the topology the report names. §5.4's arithmetic
		itself is tested directly above, on contracts chosen to reach L4.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)

		report = await service.render_delivery(plan.id, root=_a_delivery_root(tmp_path))

		names = {check.name for check in report.checks}
		assert "topology_ceiling_applied" in names
		assert "topology_refuses_l4_at_a_degraded_deployment" in names
		assert report.topology is DeploymentTopology.T1
		assert report.topology_configured is False, (
			"the synthetic service declares no topology, so the report must say the "
			"degraded default is in use (FR-042)"
		)

		contract = await service.contract_by_id(contract_id)
		decomposition = await service.require_approved_decomposition(contract_id)
		assert report.module_autonomy == module_autonomy(
			contract, decomposition, topology=report.topology
		), "the modules' number on the report must be the one this topology gives (FR-030)"
		assert report.module_autonomy <= module_autonomy(
			contract, decomposition, topology=BASELINE
		), "§5.4's T1 modifier is -1, so T1 can never report a higher number than T2"

	async def test_a_declared_topology_reaches_the_report(self, home: Path, tmp_path: Path) -> None:
		"""The configuration seam, from the service rather than the CLI: a deployment
		that declares T2 reports T2, an unmodified ceiling, and says it declared one.

		The service that declared T2 and the one that declared nothing run the *same*
		pipeline over the same state directory, so the two reports differ in the
		topology fields and nothing else — which is what makes the comparison evidence
		about the seam rather than about two fixtures.
		"""
		undeclared = synthetic_service(home, tmp_path, "complete")
		await undeclared.probe_harness(None)
		_, contract_id = await elicitation_to_contract(undeclared, commands="true")
		await specify_and_approve(undeclared, contract_id)
		await decompose_and_approve(undeclared, contract_id)
		plan = await undeclared.compile_plan(contract_id)

		service = FactoryService(
			home=home,
			specs={"synthetic": base_spec(tmp_path, "complete")},
			topology=DeploymentTopology.T2,
		)
		report = await service.render_delivery(plan.id, root=_a_delivery_root(tmp_path))
		at_t1 = await undeclared.render_delivery(
			plan.id, root=_a_delivery_root(tmp_path, "delivery-at-t1")
		)

		assert report.topology is DeploymentTopology.T2
		assert report.topology_configured is True
		assert report.module_autonomy > at_t1.module_autonomy, (
			"the whole point of declaring T2 is that the ceiling is not T1's: §5.4's "
			"modifier is -1 at T1 and 0 at T2"
		)

	async def test_the_topology_reaches_the_oracle_report_too(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-030 says "every oracle report", not only the delivery. A verdict rendered
		under T1 and one rendered under T2 can support different levels for the same
		clause, so a verdict carrying only the level could not be told from the other."""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")

		report = await service.verify_contract(contract_id)

		assert report.topology is DeploymentTopology.T1
		assert report.topology_configured is False


# --------------------------------------------------------------------------- #
# FR-160 — the gate cost travels with the report, and unmeasured is not zero
# --------------------------------------------------------------------------- #


class TestTheGateCostIsReported:
	"""FR-160 says both numbers "must appear in the delivery report" (§20.2).

	The report is the last artefact a human reads before the deploy gate, so a cost
	recorded but not carried there would be a measurement nobody acts on. What is under
	test is that the pair survives the trip *and* that the empty case reads as
	unmeasured: a report printing an empty table is the same shape as a report printing
	zero, and only one of those is true.
	"""

	def a_cost(self, minutes: float = 90.0, rework: float = 0.25) -> GateCost:
		return GateCost(
			gate=PhaseGate.SPECIFICATION,
			human_minutes=minutes,
			rework_fraction=rework,
			recorded_by="operator",
			recorded_at=now(),
		)

	def test_the_mean_rework_fraction_is_a_mean_and_not_a_sum(self) -> None:
		"""Rework is a share of each gated slice, so two gates at a quarter each are a
		quarter on average -- not a half. Summing shares is the arithmetic that would
		report more rework the more gates a project has."""
		two = a_report(gate_costs=(self.a_cost(90.0, 0.25), self.a_cost(30.0, 0.75)))

		assert two.rework_fraction == pytest.approx(0.5)

	def test_no_recorded_cost_is_none_rather_than_zero(self) -> None:
		assert a_report().gate_costs == ()
		assert a_report().rework_fraction is None

	async def test_an_unmeasured_project_reports_unmeasured_rather_than_failing(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A gate check that *failed* on an unmeasured project would block a deploy for a
		measurement the operator has not been asked for yet -- FR-160 asks for the number
		to be reported, not for the gate to depend on it. And the detail has to say
		*unmeasured*, because an empty table and a zero are the same shape on a terminal
		and only one of them is true."""
		# NFR-025 makes the envelope configuration, so the fixture names one: an
		# unconfigured service reports no actuals at all, which is a different claim
		# from a configured envelope with an unmeasured dimension.
		service = synthetic_service(home, tmp_path, "complete", envelope=DeliveryEnvelope())
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)

		rendered = await service.render_delivery(plan.id, root=_a_delivery_root(tmp_path))

		assert rendered.gate_costs == ()
		assert rendered.rework_fraction is None
		check = next(c for c in rendered.checks if c.name == "gate_cost_reported")
		assert check.passed is True
		assert "unmeasured rather than zero" in check.detail
		assert rendered.envelope_actuals is not None
		minutes = next(
			m
			for m in rendered.envelope_actuals.measurements
			if m.dimension is EnvelopeDimension.HUMAN_MINUTES
		)
		assert minutes.actual is None
		assert "sofact gate --cost" in (minutes.detail or "")

	async def test_a_recorded_cost_reaches_the_report_the_deploy_gate_presents(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The pair has to survive the trip to the report, because the report is the last
		artefact a human reads before the deploy gate: a cost recorded but not carried
		there is a measurement nobody acts on."""
		# NFR-025 makes the envelope configuration, so the fixture names one: an
		# unconfigured service reports no actuals at all, which is a different claim
		# from a configured envelope with an unmeasured dimension.
		service = synthetic_service(home, tmp_path, "complete", envelope=DeliveryEnvelope())
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)

		# FR-160 refuses a cost for a gate nobody sat at, so the approval comes first --
		# which is the requirement's own ordering rather than a test convenience.
		await _walk_to_the_specification_gate(service)
		cost = await service.record_gate_cost(
			PhaseGate.SPECIFICATION, human_minutes=90.0, rework_fraction=0.25, by="operator"
		)
		rendered = await service.render_delivery(plan.id, root=_a_delivery_root(tmp_path))

		assert rendered.gate_costs == (cost,)
		assert rendered.rework_fraction == pytest.approx(0.25)
		check = next(c for c in rendered.checks if c.name == "gate_cost_reported")
		assert check.passed is True
		assert "specification 90min/0.25 by operator" in check.detail
		assert rendered.envelope_actuals is not None
		minutes = next(
			m
			for m in rendered.envelope_actuals.measurements
			if m.dimension is EnvelopeDimension.HUMAN_MINUTES
		)
		assert minutes.actual == 90.0


# --------------------------------------------------------------------------- #
# FR-121 — the handover is §13's lanes, and it says what cannot be run
# --------------------------------------------------------------------------- #


class TestTheHandover:
	def test_every_lane_is_a_section_13_lane(self) -> None:
		"""A handover naming §14's module classes would hand the next mode a taxonomy for
		building rather than for maintaining."""
		known = {lane for lane, _, _, _ in LANE_ORACLE_KEYWORDS}

		assert known <= {"L01", "L04", "L08", "L10", "L11"}
		assert not known & {member.value for member in ModuleClass}

	def test_a_lane_inherits_every_contract_clause(self) -> None:
		"""A maintenance run does not know in advance which clause its change touches, so
		a lane handed only the oracles mentioning its own keywords would be missing the
		ones its regression needs."""
		contract = one_clause_contract("the test suite asserts the ledger records entries")

		handed = handover(contract, system="ledger", entry_point="/srv/ledger")

		for lane in handed.lanes:
			assert len(lane.inherited_oracles) == len(contract.clauses)

	def test_a_contract_matching_no_lane_still_hands_something_over(self) -> None:
		"""The type refuses a handover with no lane, and the honest answer for a contract
		stating no maintenance obligation is one lane carrying the whole contract —
		inventing a §13 identifier for work §13 does not describe would be worse."""
		contract = one_clause_contract("the ledger records entries")

		handed = handover(contract, system="ledger", entry_point="/srv/ledger")

		assert [lane.lane for lane in handed.lanes] == ["L00"]
		assert len(handed.inherited_oracles) == len(contract.clauses)

	def test_the_inherited_oracles_are_derived_from_the_lanes(self) -> None:
		"""Two statements of one fact is how a handover comes to disagree with itself
		about what the delivered system can check."""
		oracle_id = uuid7str()
		handed = Handover(
			system="s",
			entry_point="e",
			lanes=(a_lane("L01", an_oracle(oracle_id)), a_lane("L04", an_oracle(oracle_id))),
		)

		assert len(handed.inherited_oracles) == 1, "one clause, two lanes, one oracle"
		assert "inherited_oracles" not in Handover.model_fields

	def test_an_oracle_with_no_command_is_unmaintainable(self) -> None:
		"""The delivered system's ground-truth debt, one phase later: FR-108 counts it in
		the contract and this counts what actually reaches the maintenance mode."""
		handed = Handover(
			system="s",
			entry_point="e",
			lanes=(a_lane("L04", an_oracle(command=None), an_oracle(command="pytest -q")),),
		)

		assert len(handed.unmaintainable) == 1
		assert len(handed.lanes[0].executable_oracles) == 1

	def test_a_lane_with_no_oracle_is_a_real_state(self) -> None:
		"""A lane whose work no contract clause covers is a lane the system cannot be
		maintained under with an oracle, and naming that beats inventing a clause."""
		handed = Handover(system="s", entry_point="e", lanes=(a_lane("L11"),))

		assert handed.lanes[0].inherited_oracles == ()
		assert handed.inherited_oracles == ()

	def test_two_lanes_of_one_name_are_refused(self) -> None:
		"""A run could not select one, so the handover would not be a usable input."""
		with pytest.raises(ValidationError, match="share a name"):
			Handover(system="s", entry_point="e", lanes=(a_lane("L04"), a_lane("L04")))

	def test_one_lane_inheriting_two_oracles_for_a_clause_is_refused(self) -> None:
		"""One of them would not be what the contract says, and a maintenance run reading
		the lane could not tell which."""
		oracle_id = uuid7str()

		with pytest.raises(ValidationError, match="two oracles for one clause"):
			a_lane("L04", an_oracle(oracle_id), an_oracle(oracle_id))

	def test_an_inherited_oracle_references_the_clause_rather_than_copying_it(self) -> None:
		"""Editing the oracle in the handover would make the delivered system's
		maintenance criteria differ from the ones its build was verified against."""
		contract = one_clause_contract("the test suite asserts the ledger records entries")

		handed = handover(contract, system="ledger", entry_point="/srv/ledger")

		assert {o.clause_id for o in handed.inherited_oracles} == {
			clause.id for clause in contract.clauses
		}


# --------------------------------------------------------------------------- #
# FR-119 — the gate is human, permanent, and not waivable
# --------------------------------------------------------------------------- #


class TestTheDeployGate:
	def test_a_gate_presenting_a_different_report_is_refused(self) -> None:
		"""FR-119's permanence. A gate that approved one report and shows another is the
		stale-evidence mistake FR-006 refuses one phase earlier, and the one a deploy
		gate can least afford."""
		report = a_report()

		with pytest.raises(ValidationError, match="not a gate"):
			DeliveryGate(report_id=uuid7str(), checks=(a_check(),), report=report)

	def test_a_gate_is_not_satisfied_until_a_human_passes_it(self) -> None:
		"""§1.5 makes deploy never automatic, so no code path may produce a satisfied
		gate on its own."""
		report = a_report()
		gate = DeliveryGate(report_id=report.id, checks=report.checks, report=report)

		assert gate.is_approved is False
		assert gate.is_satisfied is False

	def test_a_failed_machine_check_is_not_waivable_by_approval(self) -> None:
		"""Approval cannot make an unsound artefact sound. The machine half and the human
		half are separate, and only one of them is negotiable."""
		report = a_report(checks=(a_check(passed=False),))
		gate = DeliveryGate(
			report_id=report.id,
			checks=report.checks,
			report=report,
			approved_by="operator",
			approved_at=now(),
		)

		assert gate.is_approved is True
		assert len(gate.failed) == 1
		assert gate.is_satisfied is False

	def test_an_approval_names_both_who_and_when(self) -> None:
		report = a_report()

		with pytest.raises(ValidationError, match="both who approved it and when"):
			DeliveryGate(
				report_id=report.id,
				checks=report.checks,
				report=report,
				approved_by="operator",
			)

	def test_a_satisfied_gate_is_approved_over_passing_checks(self) -> None:
		report = a_report()
		gate = DeliveryGate(
			report_id=report.id,
			checks=report.checks,
			report=report,
			approved_by="operator",
			approved_at=now(),
		)

		assert gate.is_satisfied is True

	def test_a_deploy_cannot_be_recorded_against_an_unsatisfied_gate(self) -> None:
		"""The record is the evidence of the human act, so a record over an unpassed gate
		would be a deploy nobody approved."""
		report = a_report()
		gate = DeliveryGate(report_id=report.id, checks=report.checks, report=report)

		with pytest.raises(ValidationError, match="unsatisfied gate"):
			DeployRecord(
				id=uuid7str(),
				goal_id=report.goal_id,
				report_id=report.id,
				gate=gate,
				deployed_by="operator",
				deployed_at=now(),
				note=None,
			)


# --------------------------------------------------------------------------- #
# the report, end to end, from the log
# --------------------------------------------------------------------------- #


class TestRenderingFromTheLog:
	async def test_a_delivered_plan_renders_a_report_and_records_it(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-117's artefact, rendered from the log. The five statements are present, and
		the row is in the ledger so a gate approved against it stays readable."""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)

		report = await service.render_delivery(plan.id)

		assert report.plan_id == plan.id
		assert report.contract_id == contract_id
		assert len(report.artifacts) == len(DELIVERY_ARTIFACTS)
		assert report.checks
		assert report.handover.lanes
		assert report.value_statement == DeliveryReport.VERIFIED_NOT_VALUE
		# No root was named, so the factory wrote nothing — and says so in the words of
		# the two artefacts rather than reporting them absent without a reason. This is
		# the service-level arm of the CLI's "no delivery root" refusal.
		owed = [a for a in report.artifacts if a.kind in DELIVERY_ARTIFACT_PATHS]
		assert len(owed) == 2
		assert all(not a.present for a in owed)
		assert all("no delivery root was named" in (a.missing_because or "") for a in owed)

	async def test_the_report_is_readable_after_a_second_render(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-119's permanence needs the *named* report to stay readable, so a re-render
		supersedes without erasing."""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)

		first = await service.render_delivery(plan.id)
		second = await service.render_delivery(plan.id)

		assert first.id != second.id
		gate = await service.delivery_gate(first.id)
		assert gate.report.id == first.id, "the earlier report is still the one the gate shows"

	async def test_a_deploy_records_the_human_decision_and_deploys_nothing(
		self, home: Path, tmp_path: Path
	) -> None:
		"""§1.5 makes deploy never automatic, so this row is the evidence of a human act
		rather than a release SoFact carried out.

		The delivery root is written first so the machine half *holds* — a test that
		branched on ``report.passed`` would exercise whichever arm the fixture happened to
		reach and could pass without ever recording a deploy.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)
		root = _a_delivery_root(tmp_path)
		report = await service.render_delivery(plan.id, root=root)
		assert report.passed, [check.name for check in report.failed]

		record = await service.approve_deploy(report.id, by="operator", note="shipping it")

		assert record.deployed_by == "operator"
		assert record.report_id == report.id
		assert record.gate.is_satisfied is True
		assert record.gate.report.id == report.id, "the record carries what the approver saw"

	async def test_a_deploy_over_a_failed_machine_check_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The other arm, and the reason it is its own test: a failed machine check is not
		waivable by approval, and that has to be observable without depending on which arm
		a conditional helper took.

		The failing check is the artefact check reached the *honest* way rather than
		induced by leaving the delivery root empty, which is what this test used to do.
		An empty root no longer fails anything — the factory writes the two artefacts it
		owes, so the delivery fills the root it is given — but a report rendered with no
		root at all names the two owed artefacts absent with that reason, and the check
		fails on a fact rather than on a fixture. The service API can be driven that way
		even though the CLI refuses it, and this is the layer where the gate lives.
		"""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)
		report = await service.render_delivery(plan.id)
		assert [check.name for check in report.failed] == ["delivery_artifacts"], report.checks

		with pytest.raises(ValueError, match="machine checks"):
			await service.approve_deploy(report.id, by="operator")

	async def test_a_deploy_over_an_unknown_report_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		service: FactoryService = synthetic_service(home, tmp_path, "complete")

		with pytest.raises(KeyError):
			await service.delivery_gate(uuid7str())

	async def test_no_delivery_yet_is_not_an_error(self, home: Path, tmp_path: Path) -> None:
		"""The state before P8 has run, which every other verb in the CLI can be asked
		about without raising."""
		service = synthetic_service(home, tmp_path, "complete")

		assert await service.current_delivery() is None


# --------------------------------------------------------------------------- #
# the report is derived, not asserted
# --------------------------------------------------------------------------- #


class TestTheReportIsDerivedFromTheLog:
	def test_the_envelope_actuals_field_is_optional_and_absent_means_unmeasured(self) -> None:
		"""NFR-025: ``None`` is a different statement from "every dimension is within
		bounds", and a report printing an empty table for it would read as compliance."""
		report = a_report()

		assert report.envelope_actuals is None

	def test_the_assumption_list_is_not_filtered(self) -> None:
		"""FR-118 asks for every assumption from P2 that remains unvalidated, and nothing
		in SoFact validates one — so the honest report carries all of them and a filter
		here would assert a validation the factory never performed."""
		assumption = Assumption(
			id=uuid7str(),
			statement="Reminders are scheduled by the client.",
			refuted_by="A server-side scheduler in the deployment.",
		)

		report = a_report(unvalidated_assumptions=(assumption,))

		assert report.unvalidated_assumptions == (assumption,)

	def test_broken_links_are_counted_from_the_chain(self) -> None:
		"""The count the report prints has to come from the links, not from a separate
		tally that could disagree with them."""
		whole = TraceLink(
			clause_id=uuid7str(),
			statement="one",
			requirement_id=uuid7str(),
			module="m",
			step_ordinal=0,
		)
		gapped = TraceLink(clause_id=uuid7str(), statement="two")

		report = a_report(chain=(whole, gapped))

		assert len(report.broken_links) == 1
		assert report.broken_links[0].clause_id == gapped.clause_id

	def test_a_report_with_a_gap_fails_its_own_traceability_check(self) -> None:
		"""``passed`` reads the checks, and the checks are built from the chain, so a
		report cannot be green over a chain with a hole in it."""
		gapped = TraceLink(clause_id=uuid7str(), statement="two")
		report = a_report(
			chain=(gapped,),
			checks=(
				GateCheck(
					name="traceability_chain",
					passed=False,
					detail="1 of 1 clause(s) have a gap in the chain (FR-117)",
				),
			),
		)

		assert report.passed is False
		assert [check.name for check in report.failed] == ["traceability_chain"]

	def test_the_envelope_dimension_enum_is_not_the_delivery_artifact_enum(self) -> None:
		"""Two enums that both enumerate "what a delivery has" would be easy to conflate;
		this asserts they are separate vocabularies so a future edit cannot merge them by
		accident."""
		assert not {d.value for d in EnvelopeDimension} & {k.value for k in DeliveryArtifactKind}

	def test_the_debt_count_and_the_unverified_list_come_from_one_split(self) -> None:
		"""A second count computed elsewhere is a second statement of one fact, which is
		how a report comes to disagree with itself."""
		contract = one_clause_contract("one", "two")
		first = contract.clauses[0].id

		verified, unverified = verified_and_unverified(contract, {first: VerdictOutcome.SATISFIED})

		assert len(verified) + len(unverified) == len(contract.clauses)
		assert sum(1 for u in unverified if u.is_ground_truth_debt) == 1
		assert isinstance(unverified[0], UnverifiedClause)
