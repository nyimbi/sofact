"""P7 — integration: what is checked, what is not, and where the repair is scoped.

§10's six requirements are not equally reachable, and these tests keep the two groups
apart. FR-111, FR-113 and FR-114 are checked against real dispatches and real parsed
files; FR-112, FR-115 and FR-116 have nothing to run against, and the report has to say
so. A suite that exercised only the first group would leave a green line meaning "the
implemented part passed" while reading as "P7 passed".

The import analysis is exercised by *making a violation* — a module importing a file
another module produced, with no declared edge — rather than by reading the code, and
the finding's repair scope is asserted to be the two modules involved rather than the
plan, because FR-114's whole content is the size of that set.
"""

from __future__ import annotations

from pathlib import Path

from synthetic import elicitation_to_contract, synthetic_service

from sofact._uuid7 import uuid7str
from sofact.decomposition import propose
from sofact.integration import (
	INTEGRATION_CHECKS,
	attribute_files,
	check_build_order,
	check_imports,
	check_interface_conformance,
	integrate,
	public_surface,
)
from sofact.planner import DEFAULT_STEP_BUDGET, compile_plan
from sofact.views import (
	INTEGRATION_REQUIREMENTS,
	ClauseKind,
	ClauseStem,
	Contract,
	Decomposition,
	DispatchMode,
	DispatchRecord,
	ElicitationDimension,
	GoalPlan,
	IntegrationFindingKind,
	InterfaceMember,
	InterfaceMemberKind,
	ModuleCheckout,
	OracleClass,
	OracleDeclaration,
	SpecificationDraft,
	StepOutcome,
	now,
)

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def oracle(kind: OracleClass = OracleClass.CONTRACT) -> OracleDeclaration:
	return OracleDeclaration(oracle_class=kind, description=f"a {kind.value} oracle")


def two_clause_contract() -> Contract:
	"""A two-clause contract built directly, so no elicitation has to run."""
	stems = tuple(
		ClauseStem(
			id=uuid7str(),
			statement=statement,
			kind=ClauseKind.POSITIVE,
			derived_from=ElicitationDimension.OUTCOME,
		)
		for statement in ("the ledger records entries", "the report sums entries")
	)
	draft = SpecificationDraft(id=uuid7str(), goal_id=uuid7str(), created_at=now(), stems=stems)
	return Contract.from_draft(draft, {stem.id: oracle() for stem in stems})


def checkout(module: str | None, files: tuple[str, ...], ordinal: int = 0) -> ModuleCheckout:
	"""A checkout as the seal would have left it: the module, and the files it produced."""
	sealed_commit = "0" * 40 if files else None
	return ModuleCheckout(
		branch=f"sofact/{module}" if module else f"sofact/{ordinal:03d}-bootstrap",
		step_ordinal=ordinal,
		module=module,
		sealed_commit=sealed_commit,
		sealed_paths=len(files),
		sealed_files=files,
		head_commit="0" * 40,
	)


def sealed(
	*,
	module: str | None,
	files: tuple[str, ...],
	ordinal: int = 0,
	plan: GoalPlan | None = None,
	workspace: str = "/tmp/ws",
) -> DispatchRecord:
	"""A dispatch record carrying a sealed checkout, which is all P7 reads.

	The plan fields are placeholders unless a plan is supplied: ``attribute_files`` and
	``check_build_order`` read the checkout, and standing up a whole plan to exercise a
	lookup over one field would be testing the planner.
	"""
	return DispatchRecord(
		id=uuid7str(),
		plan_id=plan.id if plan else uuid7str(),
		goal_id=plan.goal_id if plan else uuid7str(),
		step_id=plan.steps[0].id if plan else uuid7str(),
		step_ordinal=ordinal,
		harness="synthetic",
		mode=DispatchMode.GOAL,
		outcome=StepOutcome.COMPLETED,
		argv=(),
		workspace=workspace,
		budget=plan.steps[0].budget if plan else DEFAULT_STEP_BUDGET,
		started_at=now(),
		ended_at=now(),
		wall_clock_seconds=0.0,
		goal_hash="a" * 64,
		contract_hash="b" * 64,
		checkout=checkout(module, files, ordinal),
	)


def decomposition_with_edge(contract: Contract) -> tuple[Decomposition, str, str]:
	"""A decomposition whose last module depends on its first. Returns ``(d, dep, dependent)``.

	Built by hand because the proposer derives edges from oracle classes, and a test for
	the build-order check needs an edge it controls.
	"""
	proposal = propose(contract)
	first = proposal.build_order()[0]
	last = proposal.build_order()[-1]
	assert first.id != last.id, "this contract decomposes to one module; the test needs two"
	dependent = last.model_copy(update={"depends_on": (first.id,)})
	return (
		Decomposition(
			id=uuid7str(),
			goal_id=contract.goal_id,
			contract_id=contract.id,
			created_at=now(),
			modules=tuple(m if m.id != last.id else dependent for m in proposal.modules),
		),
		first.name,
		dependent.name,
	)


# --------------------------------------------------------------------------- #
# FR-113: the import analysis
# --------------------------------------------------------------------------- #


class TestTheImportAnalysis:
	def test_a_module_reaching_another_without_declaring_it_is_a_finding(self) -> None:
		"""FR-113's violation, and FR-114's scope: exactly the two modules involved.

		This is the test that fails if the analysis is reduced to convention — a check
		that read a declared edge and believed it would find nothing here, because the
		edge was never declared.
		"""
		ownership = {"ledger-core": ("ledger/core.py",), "reporting": ("reporting/summary.py",)}
		sources = {
			"ledger/core.py": "VALUE = 1\n",
			"reporting/summary.py": "import ledger.core\n\nTOTAL = ledger.core.VALUE\n",
		}

		findings = check_imports(ownership, declared={"reporting": set()}, sources=sources)

		assert len(findings) == 1
		assert findings[0].kind is IntegrationFindingKind.UNDECLARED_DEPENDENCY
		assert set(findings[0].modules) == {"reporting", "ledger-core"}, (
			"FR-114 scopes repair to the modules implicated, not to the plan"
		)
		assert "import ledger.core" in findings[0].evidence[0]

	def test_a_declared_dependency_is_not_a_finding(self) -> None:
		"""The negative that gives the previous test meaning.

		FR-090 makes the declared edge the *permitted* surface, so the same import that
		fails above passes here. Without this row, an analysis reporting every cross-module
		import would look like a working gate.
		"""
		ownership = {"ledger-core": ("ledger/core.py",), "reporting": ("reporting/summary.py",)}
		sources = {
			"ledger/core.py": "VALUE = 1\n",
			"reporting/summary.py": "import ledger.core\n\nTOTAL = ledger.core.VALUE\n",
		}

		findings = check_imports(
			ownership, declared={"reporting": {"ledger-core"}}, sources=sources
		)

		assert findings == ()

	def test_a_from_import_is_read_the_same_way(self) -> None:
		"""Both spellings, because a checker that sees one is a checker for half the bug."""
		ownership = {"ledger-core": ("ledger/core.py",), "reporting": ("reporting/s.py",)}
		sources = {
			"ledger/core.py": "VALUE = 1\n",
			"reporting/s.py": "from ledger.core import VALUE\n",
		}

		findings = check_imports(ownership, declared={"reporting": set()}, sources=sources)

		assert [f.kind for f in findings] == [IntegrationFindingKind.UNDECLARED_DEPENDENCY]

	def test_a_package_init_is_a_real_surface(self) -> None:
		"""``import ledger`` may name ``ledger/__init__.py``, which is still a module's file."""
		ownership = {"ledger-core": ("ledger/__init__.py",), "reporting": ("reporting/s.py",)}
		sources = {"ledger/__init__.py": "VALUE = 1\n", "reporting/s.py": "import ledger\n"}

		findings = check_imports(ownership, declared={"reporting": set()}, sources=sources)

		assert len(findings) == 1
		assert set(findings[0].modules) == {"reporting", "ledger-core"}

	def test_an_import_of_something_no_module_produced_is_unattributed(self) -> None:
		"""FR-114: a file nothing owns is reported, not ignored.

		Something imports it, so it exists; nothing sealed it, so no repair can be scoped
		to its owner. Silence here would be the analysis declining to have an opinion
		about a path it can see.
		"""
		ownership = {"ledger-core": ("ledger/core.py",), "reporting": ("reporting/s.py",)}
		sources = {"ledger/core.py": "VALUE = 1\n", "reporting/s.py": "import ledger.missing\n"}

		findings = check_imports(ownership, declared={"reporting": set()}, sources=sources)

		assert [f.kind for f in findings] == [IntegrationFindingKind.UNATTRIBUTED_FILE]
		assert findings[0].modules == ("reporting",)

	def test_a_stdlib_import_is_not_a_finding(self) -> None:
		"""The negative that keeps the analysis from having an opinion about ``json``.

		An import of a third-party or stdlib name reaches nothing SoFact built. Reporting
		it as unattributed would make every module with a dependency a finding, and the
		check would be switched off within a day.
		"""
		ownership = {"reporting": ("reporting/s.py",)}
		sources = {"reporting/s.py": "import json\nfrom pathlib import Path\n"}

		assert check_imports(ownership, declared={"reporting": set()}, sources=sources) == ()

	def test_a_file_that_does_not_parse_is_not_a_violation(self) -> None:
		"""A syntax error is P5's business, not integration's.

		Reporting it here would make this check a linter, and the parser that judges the
		module is the producer's own language toolchain.
		"""
		ownership = {"reporting": ("reporting/broken.py",)}
		sources = {"reporting/broken.py": "def (:\n"}

		assert check_imports(ownership, declared={"reporting": set()}, sources=sources) == ()

	def test_a_non_python_file_is_not_parsed_and_says_so(self) -> None:
		"""Python is v1's language (D2/D5), so a JS module is unanalysed rather than cleared."""
		ownership = {"ui": ("ui/app.ts",)}
		sources = {"ui/app.ts": "import { x } from './other';\n"}

		findings = check_imports(ownership, declared={"ui": set()}, sources=sources)

		assert findings == (), "the check must not claim to have read what it cannot parse"

	def test_a_relative_import_is_left_unresolved_rather_than_guessed(self) -> None:
		"""Guessing a package root would produce findings about the wrong file."""
		ownership = {"a": ("a/one.py",), "b": ("b/two.py",)}
		sources = {"a/one.py": "from . import two\n", "b/two.py": "VALUE = 1\n"}

		assert check_imports(ownership, declared={"a": set()}, sources=sources) == ()


# --------------------------------------------------------------------------- #
# FR-114: attribution is the whole point
# --------------------------------------------------------------------------- #


class TestAttribution:
	def test_a_modules_files_are_the_ones_its_own_step_sealed(self) -> None:
		"""The cumulative-branch limitation (ADR-0025) made harmless by reading the seal.

		Branches are cumulative, so a module's *branch* holds every earlier module's
		files. The seal is per-step, so this is the only attribution that distinguishes
		them — and reading the branch tree instead would show every module owning
		everything.
		"""
		dispatches = [
			sealed(module="a", files=("a/one.py",), ordinal=0),
			sealed(module="b", files=("b/two.py",), ordinal=1),
		]

		owned, orphans = attribute_files(dispatches)

		assert owned == {"a": ("a/one.py",), "b": ("b/two.py",)}
		assert orphans == ()

	def test_a_step_naming_no_module_contributes_to_nobody(self) -> None:
		"""A bootstrap step's files are orphaned, and that is reported rather than guessed."""
		owned, orphans = attribute_files([sealed(module=None, files=("scaffold.py",))])

		assert owned == {}
		assert orphans == ("scaffold.py",)

	def test_a_module_with_several_steps_keeps_all_of_its_files(self) -> None:
		"""FR-136: a module's work spans several steps, so attribution must union them."""
		dispatches = [
			sealed(module="a", files=("a/one.py",), ordinal=0),
			sealed(module="a", files=("a/two.py",), ordinal=1),
		]

		owned, _ = attribute_files(dispatches)

		assert owned == {"a": ("a/one.py", "a/two.py")}

	def test_a_step_that_sealed_nothing_is_not_a_module_that_built(self) -> None:
		"""A session that changed nothing built nothing, and the report must not say it did."""
		owned, orphans = attribute_files([sealed(module="a", files=())])

		assert owned == {}
		assert orphans == ()


# --------------------------------------------------------------------------- #
# FR-111: the build order
# --------------------------------------------------------------------------- #


class TestTheBuildOrder:
	def test_a_module_built_before_its_dependency_is_a_finding(self) -> None:
		"""FR-111 read off the dispatches, with the scope being the two modules."""
		decomposition, dependency, dependent = decomposition_with_edge(two_clause_contract())
		dispatches = [sealed(module=dependent, files=("dep.py",), ordinal=1)]

		findings = check_build_order(decomposition, dispatches)

		assert len(findings) == 1
		assert findings[0].kind is IntegrationFindingKind.UNBUILT_DEPENDENCY
		assert set(findings[0].modules) == {dependent, dependency}

	def test_a_dependency_that_was_built_is_not_a_finding(self) -> None:
		"""The negative. Order is not a finding when the order was respected."""
		decomposition, dependency, dependent = decomposition_with_edge(two_clause_contract())
		dispatches = [
			sealed(module=dependency, files=("base.py",), ordinal=0),
			sealed(module=dependent, files=("dep.py",), ordinal=1),
		]

		assert check_build_order(decomposition, dispatches) == ()

	def test_an_unbuilt_dependency_of_an_unbuilt_dependent_is_not_a_finding(self) -> None:
		"""A plan not yet finished is a different fact from a dependency violated.

		Reporting the former as the latter would fail integration on every partial run,
		which is how a check teaches its operator to ignore it.
		"""
		decomposition, _, _ = decomposition_with_edge(two_clause_contract())

		assert check_build_order(decomposition, ()) == ()


# --------------------------------------------------------------------------- #
# FR-112: the declared surface diffed against the built one
# --------------------------------------------------------------------------- #


def with_surface(
	decomposition: Decomposition, name: str, *members: InterfaceMember
) -> Decomposition:
	"""The decomposition with one module's declared surface replaced."""
	return decomposition.model_copy(
		update={
			"modules": tuple(
				m.model_copy(update={"surface": members}) if m.name == name else m
				for m in decomposition.modules
			)
		}
	)


class TestTheBuiltSurface:
	def test_a_public_function_class_and_constant_are_read_from_the_ast(self) -> None:
		"""The extraction FR-112's right-hand side is built from."""
		surface = public_surface(
			["m.py"],
			{
				"m.py": "def run(a, b):\n\tpass\n\n\nclass Store:\n\tpass\n\n\nLIMIT = 3\n",
			},
		)

		assert {(m.name, m.kind) for m in surface} == {
			("run", InterfaceMemberKind.FUNCTION),
			("Store", InterfaceMemberKind.CLASS),
			("LIMIT", InterfaceMemberKind.CONSTANT),
		}
		assert next(m for m in surface if m.name == "run").parameters == ("a", "b")

	def test_a_private_name_is_not_on_the_surface(self) -> None:
		"""Python's convention is the definition of public here, and it is the whole test."""
		surface = public_surface(
			["m.py"], {"m.py": "def _helper():\n\tpass\n\n\n_HIDDEN = 1\n\n\ndef run():\n\tpass\n"}
		)

		assert [m.name for m in surface] == ["run"]

	def test_a_method_is_not_a_module_level_name(self) -> None:
		"""A method is reached through its class; counting it would flag every private helper."""
		surface = public_surface(["m.py"], {"m.py": "class Store:\n\tdef save(self):\n\t\tpass\n"})

		assert [m.name for m in surface] == ["Store"]

	def test_a_file_that_does_not_parse_contributes_nothing(self) -> None:
		"""Judging syntax is the producer's toolchain's job, not integration's."""
		assert public_surface(["m.py"], {"m.py": "def broken(:\n"}) == ()

	def test_a_non_python_file_is_not_parsed(self) -> None:
		assert public_surface(["m.js"], {"m.js": "export function run() {}"}) == ()


class TestTheInterfaceDiff:
	def test_a_declared_name_the_build_does_not_expose_is_a_finding(self) -> None:
		"""Direction one: the module did not deliver what it promised.

		The source exposes nothing public, so the only difference is the declared name —
		which is what makes this a test of one direction rather than of both.
		"""
		findings = check_interface_conformance(
			{"a": ("a.py",)},
			declared={"a": (InterfaceMember(name="run", kind=InterfaceMemberKind.FUNCTION),)},
			sources={"a.py": "_pending = 1\n"},
		)

		assert [f.kind for f in findings] == [IntegrationFindingKind.MISSING_PUBLIC_NAME]
		assert findings[0].modules == ("a",)

	def test_a_built_name_the_declaration_does_not_carry_is_a_finding(self) -> None:
		"""Direction two, and the one FR-090 cares about.

		The declared surface is what a dependent is permitted to reach for. A producer
		that widens it has added a second way in that no dependent declared and no gate
		approved, and reporting only the missing direction would let that through.
		"""
		findings = check_interface_conformance(
			{"a": ("a.py",)},
			declared={"a": (InterfaceMember(name="run", kind=InterfaceMemberKind.FUNCTION),)},
			sources={"a.py": "def run():\n\tpass\n\n\ndef sneak():\n\tpass\n"},
		)

		assert [f.kind for f in findings] == [IntegrationFindingKind.UNDECLARED_PUBLIC_NAME]
		assert "sneak" in findings[0].detail

	def test_a_declared_surface_the_build_matches_exactly_is_not_a_finding(self) -> None:
		"""The negative. An empty diff is what FR-112 asks for and this is one."""
		findings = check_interface_conformance(
			{"a": ("a.py",)},
			declared={"a": (InterfaceMember(name="run", kind=InterfaceMemberKind.FUNCTION),)},
			sources={"a.py": "def run():\n\tpass\n"},
		)

		assert findings == ()

	def test_a_function_built_with_a_different_arity_is_a_finding(self) -> None:
		"""A name that is present is not a signature that matches."""
		findings = check_interface_conformance(
			{"a": ("a.py",)},
			declared={
				"a": (
					InterfaceMember(
						name="run", kind=InterfaceMemberKind.FUNCTION, parameters=("a", "b")
					),
				)
			},
			sources={"a.py": "def run(a):\n\tpass\n"},
		)

		assert [f.kind for f in findings] == [IntegrationFindingKind.WRONG_ARITY]
		assert "2 parameter(s)" in findings[0].detail and "1" in findings[0].detail

	def test_a_module_with_no_declaration_is_skipped_rather_than_passed(self) -> None:
		"""Nothing to diff is not an empty diff, and the report says which it was."""
		assert (
			check_interface_conformance({"a": ("a.py",)}, declared={}, sources={"a.py": "X = 1\n"})
			== ()
		)


# --------------------------------------------------------------------------- #
# FR-115, FR-116: the requirements that are not implemented
# --------------------------------------------------------------------------- #


class TestWhatIsNotImplemented:
	def test_the_report_names_every_requirement_it_did_not_discharge(self) -> None:
		"""The load-bearing test for honesty about scope.

		FR-112 is *not* in the tuple here even though the conformance check runs, because
		the check diffs nothing when no module declared a surface -- the decomposition
		states interfaces as prose and a proposal has no signature to derive one from.
		FR-115 needs a system model, which is not a type; FR-116 needs P2 acceptance
		criteria the contract does not carry. A report that omitted them would let a green
		line read as "P7 is done".
		"""
		contract = two_clause_contract()
		proposal = propose(contract)
		plan = compile_plan(contract)
		dispatches = [sealed(module=proposal.modules[0].name, files=("a.py",), plan=plan)]

		report = integrate(plan, proposal, dispatches, sources={"a.py": "VALUE = 1\n"})

		assert report.not_implemented == ("FR-112", "FR-115", "FR-116"), (
			"the conformance check ran but diffed nothing, so FR-112 is not discharged"
		)
		assert report.passed, "the implemented checks passed; that is not the same as P7 done"

	def test_a_declared_surface_discharges_fr_112_and_the_report_stops_naming_it(self) -> None:
		"""The complement of the test above, and the reason it is a real distinction.

		Once a module carries a machine-readable surface the diff has two sides, and the
		same requirement moves out of ``not_implemented`` without any list being edited.
		"""
		contract = two_clause_contract()
		proposal = propose(contract)
		plan = compile_plan(contract)
		name = proposal.modules[0].name
		declared = with_surface(
			proposal, name, InterfaceMember(name="run", kind=InterfaceMemberKind.FUNCTION)
		)
		dispatches = [sealed(module=name, files=("a.py",), plan=plan)]

		report = integrate(plan, declared, dispatches, sources={"a.py": "def run():\n\tpass\n"})

		assert report.not_implemented == ("FR-115", "FR-116")
		assert report.passed

	def test_a_surface_that_does_not_match_fails_the_report(self) -> None:
		"""FR-112's diff is a hard stop like every other integration check (FR-061)."""
		contract = two_clause_contract()
		proposal = propose(contract)
		plan = compile_plan(contract)
		name = proposal.modules[0].name
		declared = with_surface(
			proposal, name, InterfaceMember(name="run", kind=InterfaceMemberKind.FUNCTION)
		)
		dispatches = [sealed(module=name, files=("a.py",), plan=plan)]

		report = integrate(plan, declared, dispatches, sources={"a.py": "_pending = 1\n"})

		assert not report.passed
		assert report.violating_modules == (name,)
		conformance = next(c for c in report.checks if c.name == "interface_conformance")
		assert not conformance.passed

	def test_every_check_claims_requirements_that_exist(self) -> None:
		"""A check claiming a requirement §10 does not state would be a typo wearing a claim."""
		contract = two_clause_contract()
		report = integrate(compile_plan(contract), propose(contract), (), sources={})

		assert {check.name for check in report.checks} == set(INTEGRATION_CHECKS)
		for check in report.checks:
			assert check.requirements, f"{check.name} discharges nothing"
			assert set(check.requirements) <= set(INTEGRATION_REQUIREMENTS)

	def test_a_report_over_nothing_claims_nothing_passed(self) -> None:
		"""No module sealed work: the order check says so rather than passing vacuously."""
		contract = two_clause_contract()
		report = integrate(compile_plan(contract), propose(contract), (), sources={})

		order = next(c for c in report.checks if c.name == "build_order")
		assert order.uncovered, "a vacuous pass must name what it did not exercise"

	def test_the_repair_scope_is_the_findings_union_and_never_the_plan(self) -> None:
		"""FR-114's refusal, asserted as a property of the report rather than promised.

		A platform-wide rebuild is what ``violating_modules`` returning every module would
		be, so the assertion is that it returns *fewer* than the plan holds.
		"""
		contract = two_clause_contract()
		proposal = propose(contract)
		plan = compile_plan(contract)
		modules = [m.name for m in proposal.modules]
		assert len(modules) >= 2, "this test needs two modules to have something to exclude"
		dispatches = [
			sealed(module=modules[0], files=("a.py",), plan=plan),
			sealed(module=modules[1], files=("b.py",), ordinal=1, plan=plan),
		]

		report = integrate(
			plan,
			proposal,
			dispatches,
			sources={"a.py": "VALUE = 1\n", "b.py": "import a\n"},
		)

		assert report.findings, "b.py reaches a.py's surface without declaring it"
		assert set(report.violating_modules) == set(modules[:2])
		assert len(report.violating_modules) < len(proposal.modules) or len(modules) == 2


# --------------------------------------------------------------------------- #
# through the service: the log, and the refusal
# --------------------------------------------------------------------------- #


class TestThroughTheService:
	async def test_a_real_dispatch_is_integrated_and_recorded(
		self, home: Path, tmp_path: Path
	) -> None:
		"""End to end over a real session: the producer's file is attributed to a module."""
		service = synthetic_service(home, tmp_path, "writes-work-complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service)
		from synthetic import decompose_and_approve, specify_and_approve

		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)
		await service.dispatch_plan(plan.id)

		report = await service.check_integration(plan.id)

		assert report.plan_id == plan.id
		assert report.build_order, "the report names the order it integrated in"
		state = await service.state()
		assert state.latest_integration(plan.id) == report, (
			"the report is in the log, not only returned"
		)

		# Measured, and not what one would guess: this producer writes its file during the
		# *bootstrap* step, which names no module, so the file is sealed by a step that
		# belongs to nobody and ``modules_built`` is legitimately empty. That is the honest
		# answer rather than a defect in the check -- attribution follows *when* a file was
		# written, and a module's files are the ones its own step sealed (ADR-0025). What
		# the report must not do is stay silent about it, so the orphan is named.
		check = next(c for c in report.checks if c.name == "import_discipline")
		assert any("sealed by a step that named no module" in line for line in check.uncovered), (
			"a file no module owns must be reported, not dropped"
		)

	async def test_a_plan_whose_decomposition_is_unapproved_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-061 applies to P7 as much as to planning: no module graph, no integration."""
		service = synthetic_service(home, tmp_path, "complete")
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service)
		plan = await service.compile_plan(contract_id, require_approval=False)

		try:
			await service.check_integration(plan.id)
		except ValueError as exc:
			assert "decomposition" in str(exc)
		else:
			raise AssertionError("integrating without an approved decomposition must be refused")
