"""FR-053, FR-055 and FR-134 — what the factory must not be able to reach.

Three requirements, one shape, and the shape decides what these tests are. Each says the
factory **cannot** do something, so the instrument is reachability — the transitive import
closure of an authoring surface — and the tests are about whether that measurement is
sound in both directions:

* a surface that genuinely cannot reach a model is reported **clean**, and the closure is
  the closure rather than the roots (a direct-import check would call a two-hop path clean,
  and the whole reason for transitivity is that the two-hop path is the one that appears);
* a surface that **can** reach one is reported as reaching, which is the canary. It is
  driven against a deliberately broken tree on disk, because the real package is clean and
  a test that only ever sees the clean case cannot tell a working detector from a stub
  that returns ``()``.

The scanner's own forms get their own tests, because two of them fail *open* and the real
package exercises neither: ``from sofact import api`` records the submodule among the
aliases rather than in ``node.module``, and ``from .views import X`` resolves against the
importing module's package. A scanner that loses either reports a smaller closure and
calls it clean, and no test over the clean package would notice.

FR-055's two halves are tested as *rules* rather than against the real vocabulary. An
assertion that the shipped :class:`~sofact.views.LedgerKind` has no commercial member
passes for any marker list, including an empty one; the rule is
:func:`~sofact.authorship.commercial_kinds`, so that is what gets a planted input.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sofact._uuid7 import uuid7str
from sofact.authorship import (
	AUTHORSHIP_SURFACES,
	COMMERCIAL_INTERFACES,
	GOVERNANCE_ABSENT_REASON,
	MODEL_REACHING_MODULES,
	commercial_kinds,
	detect_authorship,
	governance_is_absent,
	import_closure,
	installed_package_root,
)
from sofact.service import FactoryService
from sofact.views import (
	AUTHORSHIP_REQUIREMENTS,
	TUNED_MODEL_UNREACHABLE,
	AuthorshipCheck,
	AuthorshipFinding,
	AuthorshipSurface,
	LedgerKind,
	now,
)

# --------------------------------------------------------------------------- #
# fixtures — a synthetic package, so the broken cases have somewhere to live
# --------------------------------------------------------------------------- #


def _package(root: Path, modules: dict[str, str]) -> Path:
	"""Write a package from ``{"sofact.thing": "source"}``, creating directories.

	The root *is* the package directory, which is the shape
	:func:`~sofact.authorship.installed_package_root` returns: the instrument names a file
	``sofact.contract`` when it sits at ``<root>/contract.py``. Nesting the tree one level
	deeper would name it ``sofact.sofact.contract`` and the surface roots would not resolve,
	which is the assertion in :func:`~sofact.authorship.import_closure` doing its job.
	"""
	for name, source in modules.items():
		parts = name.split(".")[1:]
		path = root.joinpath(*parts).with_suffix(".py")
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(source, encoding="utf-8")
	return root


_CLEAN_TREE: dict[str, str] = {
	"sofact.__init__": "",
	"sofact.views": "VALUE = 1\n",
	"sofact.elicitation": "from sofact.views import VALUE\n",
	"sofact.contract": "from sofact.views import VALUE\n",
	"sofact.manufacture": "from sofact.views import VALUE\n",
}


def _broken(root: Path, *, where: str, how: str) -> Path:
	"""The clean tree with one module's imports replaced by ``how``."""
	modules = dict(_CLEAN_TREE)
	modules[where] = how
	return _package(root, modules)


# --------------------------------------------------------------------------- #
# the detector, in both directions
# --------------------------------------------------------------------------- #


class TestTheDetectorTellsAReachableSurfaceFromAnUnreachableOne:
	"""Both directions, because a detector only ever shown the clean case is a stub."""

	def test_the_shipped_package_cannot_reach_a_model_from_either_surface(
		self,
	) -> None:
		"""FR-053 and FR-134's claim about *this* build, measured rather than asserted."""
		findings, governance_absent = detect_authorship(package_root=installed_package_root())
		assert governance_absent, "the shipped package reaches a commercial interface"
		measured = {surface for surface, _, _ in findings}
		assert measured == set(AUTHORSHIP_SURFACES), (
			"a surface went unmeasured, and an unmeasured surface reports clean by "
			"never having been looked at (NFR-024)"
		)
		for surface, closure, reaching in findings:
			assert closure, f"{surface} measured an empty closure, which is not a measurement"
			assert not reaching, f"{surface} can reach {reaching}"

	def test_a_surface_that_imports_the_model_client_is_reported_as_reaching(
		self, tmp_path: Path
	) -> None:
		"""The canary. Without this the clean result above is not evidence of anything.

		The mutation is disjoint from what the predicate looks for in the sense that
		matters: the clean tree's ``contract`` module imports ``sofact.views`` and the
		broken one imports ``sofact.llm``, so the module is not merely different — the
		model-reaching name is *absent* from the original and *present* in the mutant.
		"""
		root = _broken(tmp_path, where="sofact.contract", how="import sofact.llm\n")
		findings, _ = detect_authorship(package_root=root)
		by_surface = {surface: reaching for surface, _, reaching in findings}
		assert by_surface["contract_authoring"] == ("sofact.llm",), (
			"a contract-authoring module importing the model client was not reported"
		)
		assert by_surface["oracle_authoring"] == ("sofact.llm",), (
			"the oracle surface shares sofact.contract and must inherit the finding"
		)

	def test_reach_is_reported_through_an_intermediate_module(self, tmp_path: Path) -> None:
		"""Transitivity, which is the property a direct-import check would not have.

		``elicitation`` imports ``helper`` and ``helper`` imports the client. Nothing on the
		surface names a model, so a check that read the surface's own files reports clean —
		and the helper is exactly the shape an unrelated later change adds.
		"""
		root = _package(
			tmp_path,
			{
				**_CLEAN_TREE,
				"sofact.helper": "import sofact.llm\n",
				"sofact.elicitation": "import sofact.helper\n",
			},
		)
		findings, _ = detect_authorship(package_root=root)
		by_surface = {surface: reaching for surface, _, reaching in findings}
		assert by_surface["contract_authoring"] == ("sofact.llm",)

	def test_an_external_network_module_is_a_finding_too(self, tmp_path: Path) -> None:
		"""The set is wider than the factory's own client, and deliberately so.

		A surface that imported ``httpx`` could reach a model without ever naming
		``sofact.llm``, so a check that only looked for its own client would be a check on
		the spelling rather than on the capability.
		"""
		root = _broken(tmp_path, where="sofact.manufacture", how="import httpx\n")
		findings, _ = detect_authorship(package_root=root)
		by_surface = {surface: reaching for surface, _, reaching in findings}
		assert by_surface["oracle_authoring"] == ("httpx",)
		assert by_surface["contract_authoring"] == (), (
			"the contract surface does not import manufacture and must be unaffected"
		)

	def test_a_surface_naming_a_module_it_does_not_import_is_not_a_finding(
		self, tmp_path: Path
	) -> None:
		"""The control arm for the scanner: prose is not an import.

		``llm``'s docstring in this tree explains that it is the only ``httpx`` importer,
		and a text search would report that module as importing itself. ``ast`` is what
		makes the measurement a measurement.
		"""
		root = _package(
			tmp_path,
			{
				**_CLEAN_TREE,
				"sofact.elicitation": (
					'"""This module never imports sofact.llm, and says so."""\n'
					"from sofact.views import VALUE\n"
				),
			},
		)
		findings, _ = detect_authorship(package_root=root)
		by_surface = {surface: reaching for surface, _, reaching in findings}
		assert by_surface["contract_authoring"] == ()


# --------------------------------------------------------------------------- #
# the scanner's forms — two of which fail open
# --------------------------------------------------------------------------- #


class TestTheScannerSeesEveryFormOfImport:
	"""``from X import y`` has two readings and one of them loses the submodule."""

	def test_from_package_import_submodule_names_the_submodule(self, tmp_path: Path) -> None:
		"""``from sofact import llm`` must yield ``sofact.llm``, not ``sofact``.

		``ast`` records this form as ``module="sofact"`` with ``llm`` among the aliases.
		Yielding ``node.module`` alone names the package initialiser, and the closure stops
		there — the fail-open direction, on the form ``cli.py`` uses for ``sofact.api``.
		"""
		root = _broken(tmp_path, where="sofact.contract", how="from sofact import llm\n")
		findings, _ = detect_authorship(package_root=root)
		by_surface = {surface: reaching for surface, _, reaching in findings}
		assert by_surface["contract_authoring"] == ("sofact.llm",)

	def test_the_real_package_walks_the_from_package_import_submodule_form(self) -> None:
		"""The same rule against the shipped tree, where the form actually occurs.

		``cli.py`` imports ``sofact.api`` as ``from sofact import api as machine_api``. The
		closure of a surface that reached ``cli`` would stop at the initialiser without the
		alias half — so this walks ``sofact.cli``'s closure and asserts the submodule is in
		it. The root is named rather than reached through a surface, because the point is
		the scanner's form and not the surface's shape.
		"""
		closure, _ = import_closure(("sofact.cli",), package_root=installed_package_root())
		assert "sofact.api" in closure, (
			"the `from sofact import api` alias half was dropped, so the closure stopped "
			"at the package initialiser and everything under sofact.api reads as unreachable"
		)
		assert "sofact.service" in closure
		assert "sofact.views.Clause" not in closure, (
			"an imported *name* was walked as a module; it is not one, so the closure "
			"would be reporting a module that does not exist"
		)

	def test_the_relative_form_resolves_against_the_importing_module(self, tmp_path: Path) -> None:
		"""``from .views import X`` in ``sofact/boundary.py`` means ``sofact.views``.

		A scanner that skipped ``level > 0`` reports boundary's closure as empty and calls
		it clean. The real package has exactly one such file, so this is the only place the
		rule is exercised — driven here through the closure rather than through the helper,
		so the whole path is what is measured.
		"""
		root = _package(
			tmp_path,
			{
				"sofact.__init__": "",
				"sofact.views": "import sofact.llm\n",
				"sofact.contract": "from .views import VALUE\n",
			},
		)
		closure, reaching = import_closure(("sofact.contract",), package_root=root)
		assert "sofact.views" in closure, "`from .views import X` did not reach the sibling"
		assert reaching == ("sofact.llm",)

		root = _package(
			tmp_path / "two",
			{
				"sofact.__init__": "",
				"sofact.views": "import sofact.llm\n",
				"sofact.contract": "from . import views\n",
			},
		)
		closure, reaching = import_closure(("sofact.contract",), package_root=root)
		assert "sofact.views" in closure, "`from . import views` names the sibling submodule"
		assert reaching == ("sofact.llm",)

	def test_a_relative_import_in_a_nested_package_stays_in_that_package(
		self, tmp_path: Path
	) -> None:
		"""The level arithmetic, held against a package that is not the top one.

		``from .views import X`` inside ``sofact.sub.thing`` means ``sofact.sub.views``.
		Resolving it against ``sofact`` would report a nested package's closure as reaching
		whatever the top-level ``sofact.views`` reaches, which is a wrong answer that looks
		like a right one — so the top-level ``views`` here imports nothing and the nested
		one is where the model client lives.
		"""
		root = _package(
			tmp_path,
			{
				"sofact.__init__": "",
				"sofact.views": "VALUE = 1\n",
				"sofact.sub.__init__": "",
				"sofact.sub.views": "import sofact.llm\n",
				"sofact.sub.thing": "from .views import VALUE\n",
			},
		)
		closure, reaching = import_closure(("sofact.sub.thing",), package_root=root)
		assert "sofact.sub.views" in closure
		assert "sofact.views" not in closure, (
			"the relative import was resolved against the top-level package rather than "
			"the importing module's own"
		)
		assert reaching == ("sofact.llm",)

		# In a package's own `__init__`, `.` is the package rather than its parent.
		root = _package(
			tmp_path / "pkg",
			{
				"sofact.__init__": "",
				"sofact.sub.__init__": "from . import views\n",
				"sofact.sub.views": "import sofact.llm\n",
			},
		)
		closure, reaching = import_closure(("sofact.sub",), package_root=root)
		assert "sofact.sub.views" in closure
		assert reaching == ("sofact.llm",)

	def test_a_missing_surface_module_is_refused_rather_than_skipped(self, tmp_path: Path) -> None:
		"""A closure over a root that is not there would be the empty closure.

		Refused loudly, because "measured nothing" and "measured clean" are the two states
		the whole report exists to keep apart.
		"""
		root = _package(tmp_path, {"sofact.__init__": ""})
		with pytest.raises(AssertionError, match="not modules in"):
			import_closure(("sofact.elicitation",), package_root=root)


# --------------------------------------------------------------------------- #
# FR-055 — the two halves, tested as rules
# --------------------------------------------------------------------------- #


class TestGovernanceAbsenceIsMeasuredInTwoHalves:
	"""An import is a capability; a ledger kind is the vocabulary to record the act."""

	def test_a_commercial_import_makes_the_boundary_present(self, tmp_path: Path) -> None:
		"""The import half: a module that imported ``stripe`` could charge a card."""
		root = _package(tmp_path, {**_CLEAN_TREE, "sofact.billing": "import stripe\n"})
		assert not governance_is_absent(package_root=root)

	def test_the_shipped_package_is_absent_and_that_is_measured(self) -> None:
		assert governance_is_absent(package_root=installed_package_root())

	def test_the_kind_rule_fires_on_a_planted_commercial_kind(self) -> None:
		"""The kind half, held against a vocabulary rather than against the real enum.

		Asserting "the shipped ``LedgerKind`` has no commercial member" would pass for an
		empty marker list. The rule is what needs checking, so the rule takes the input.
		"""
		assert commercial_kinds(["goal.created", "contract.created", "escape.recorded"]) == []
		assert commercial_kinds(["goal.created", "price.set"]) == ["price.set"]
		assert commercial_kinds(["customer.accepted"]) == ["customer.accepted"]
		assert commercial_kinds(["agreement.signed", "money.moved"]) == [
			"agreement.signed",
			"money.moved",
		]

	def test_the_kind_rule_does_not_fire_on_the_products_own_vocabulary(self) -> None:
		"""The two words deliberately left out, and the reason they are load-bearing.

		SoFact's contract is a *verification* contract — the product's central artifact —
		and ``GATE_COST_RECORDED`` is what the factory *spends*, not what it *charges*. A
		marker list containing either word would fail on every project, which is the
		failure mode that teaches an operator to disable the gate.
		"""
		assert commercial_kinds([LedgerKind.CONTRACT_CREATED.value]) == []
		assert commercial_kinds([LedgerKind.GATE_COST_RECORDED.value]) == []

	def test_every_shipped_kind_is_clear_of_the_rule(self) -> None:
		"""The rule applied to the real vocabulary, as a second reading of the same fact."""
		assert commercial_kinds(kind.value for kind in LedgerKind) == []

	def test_the_interface_sets_are_disjoint_from_what_the_package_imports(self) -> None:
		"""A sanity check on the lists themselves rather than on the tree.

		``x402`` is named by the spec (§11.3's metered row), so it is on the list rather
		than assumed absent: a requirement that names a protocol is one somebody might
		implement, and the check should fire on the day they do.
		"""
		assert "x402" in COMMERCIAL_INTERFACES
		assert "sofact.llm" in MODEL_REACHING_MODULES
		assert not (COMMERCIAL_INTERFACES & MODEL_REACHING_MODULES)

	def test_the_absence_reason_names_only_what_the_check_measures(self) -> None:
		"""The printed reason must not claim a word the predicate does not test.

		The first draft read "a payment, billing, contracting or pricing interface", and
		**"contract" is the one word the act markers deliberately exclude** — SoFact's
		contract is a verification contract. A finding that named it would tell a reader
		the check looks for something it was built not to look for, which is the same
		class of defect as a gate scoped to the bug rather than the claim.
		"""
		assert "contracting" not in GOVERNANCE_ABSENT_REASON
		assert "pricing" not in GOVERNANCE_ABSENT_REASON
		assert "payment" in GOVERNANCE_ABSENT_REASON


# --------------------------------------------------------------------------- #
# the view — the validator, the three-way verdict, and the round trip
# --------------------------------------------------------------------------- #


def _finding(surface: AuthorshipSurface, *, reaching: tuple[str, ...] = ()) -> AuthorshipFinding:
	return AuthorshipFinding(surface=surface, closure=("sofact.views",), reaching=reaching)


def _check(**overrides: object) -> AuthorshipCheck:
	fields: dict[str, object] = {
		"id": uuid7str(),
		"checked_at": now(),
		"findings": (
			_finding(AuthorshipSurface.CONTRACT_AUTHORING),
			_finding(AuthorshipSurface.ORACLE_AUTHORING),
		),
		"governance_absent": True,
		"governance_reason": "nothing in this tree names one of FR-055's five acts",
	}
	fields.update(overrides)
	return AuthorshipCheck.model_validate(fields)


class TestTheCheckCannotClaimMoreThanItMeasured:
	"""``discharged`` is the rule every measurement in this tree states the same way."""

	def test_a_check_with_no_findings_is_refused(self) -> None:
		"""A check that measured nothing claims nothing, and must not be constructible.

		Without this, ``discharged`` returning ``()`` would be reachable by constructing
		the model empty — and an empty check reports clean by never having looked.
		"""
		with pytest.raises(ValueError, match="checked nothing"):
			_check(findings=())

	def test_one_surface_measured_twice_is_refused(self) -> None:
		"""Two findings for one surface means the reader picks, and the pick is the verdict."""
		with pytest.raises(ValueError, match="measured more than once"):
			_check(
				findings=(
					_finding(AuthorshipSurface.CONTRACT_AUTHORING),
					_finding(AuthorshipSurface.CONTRACT_AUTHORING),
				)
			)

	def test_a_clean_check_discharges_all_three_requirements(self) -> None:
		check = _check()
		assert set(check.discharged) == set(AUTHORSHIP_REQUIREMENTS)
		assert check.not_implemented == ()
		assert check.clean

	def test_a_reaching_surface_clears_the_verdict_but_not_the_discharge(self) -> None:
		"""The distinction the whole report turns on: *measured* is not *satisfied*.

		The check carried out FR-134 — it looked, and found a path. A report that dropped
		the requirement from ``discharged`` on a negative finding would be saying it never
		measured, which is the opposite of what happened.
		"""
		check = _check(
			findings=(
				_finding(AuthorshipSurface.CONTRACT_AUTHORING, reaching=("sofact.llm",)),
				_finding(AuthorshipSurface.ORACLE_AUTHORING),
			)
		)
		assert "FR-134" in check.discharged
		assert not check.clean
		assert "REACHES a model" in check.rendered
		assert "sofact.llm" in check.rendered

	def test_governance_present_clears_the_verdict_and_undischarges_fr055(self) -> None:
		"""FR-055 is discharged by *absence*, so a present boundary is a requirement unmet."""
		check = _check(governance_absent=False, governance_reason="stripe is importable here")
		assert "FR-055" not in check.discharged
		assert check.not_implemented == ("FR-055",)
		assert not check.clean

	def test_finding_looks_a_surface_up_by_value(self) -> None:
		check = _check()
		found = check.finding(AuthorshipSurface.ORACLE_AUTHORING)
		assert found is not None
		assert found.surface is AuthorshipSurface.ORACLE_AUTHORING
		assert found.clean

	def test_the_rendered_report_carries_the_structural_limit(self) -> None:
		"""``TUNED_MODEL_UNREACHABLE`` is printed beside the verdict, not in a footnote.

		The check establishes the structural half only — nothing in this build tunes a
		model, so a claim about a *tuned* model would be a claim about a thing that does
		not exist. The sentence saying so is what keeps the clean verdict honest.
		"""
		assert "no tuning capability" in TUNED_MODEL_UNREACHABLE


# --------------------------------------------------------------------------- #
# the service — the ledger round trip
# --------------------------------------------------------------------------- #


class TestTheCheckTravelsThroughTheLedger:
	"""The event is appended and never keyed, and the fold must reproduce it."""

	async def test_a_check_round_trips_through_the_fold(self, service: FactoryService) -> None:
		check = await service.check_authorship()
		assert check.clean, check.rendered
		state = await service.state()
		latest = state.latest_authorship_check()
		assert latest is not None
		assert latest.id == check.id
		assert {f.surface for f in latest.findings} == set(AuthorshipSurface)
		assert latest.governance_absent

	async def test_every_check_is_kept_rather_than_the_latest_winning(
		self, service: FactoryService
	) -> None:
		"""Appended, not keyed, and the reason is the subject rather than a preference.

		FR-053 and FR-134 are claims about the *tree*, and the tree moves. A check keyed to
		the latest would report the current closure while the reader believes it is reading
		the one measured when the contract was authored — the stale-evidence mistake FR-006
		refuses one phase over.
		"""
		first = await service.check_authorship()
		second = await service.check_authorship()
		assert first.id != second.id
		state = await service.state()
		assert len(state.authorship_checks) == 2
		assert state.latest_authorship_check() is not None
		assert state.latest_authorship_check().id == second.id  # type: ignore[union-attr]

	async def test_a_check_over_a_broken_tree_is_recorded_as_reaching(
		self, service: FactoryService, tmp_path: Path
	) -> None:
		"""The service's door is the same door the test uses, and it must report the truth.

		Pointed at a tree whose contract module imports the client, the service records a
		check that is *not* clean. A service that hardcoded the shipped tree's answer would
		pass every other test in this file.
		"""
		root = _broken(tmp_path, where="sofact.contract", how="import sofact.llm\n")
		check = await service.check_authorship(package_root=root)
		assert not check.clean
		assert "FR-053" in check.discharged, (
			"the check still measured the surface; it found a path, which is a finding "
			"rather than a failure to look"
		)

	async def test_the_ledger_kind_exists_and_is_named_for_the_act(self) -> None:
		assert LedgerKind.AUTHORSHIP_CHECKED.value == "authorship.checked"
