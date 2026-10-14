"""FR-157 — the autonomy target is deployment-scoped, not product-scoped.

The requirement's sentence is short and its consequence is not: "the required ceiling is
L2 to L3 with escape-rate tracking (FR-107), and the θ_hi = 0.80 gate that admits L4
(FR-024 to FR-035) must not be imposed as a default. Where the artifact is consumed by third
parties, the L4 gate applies unchanged." Three separable claims follow from it, and each
is a class below.

**The target is a type, not a number.** The two ways a declared target can be one this
build cannot honour are structural and carry *different remedies*: a personal scope may
not reach L4 because the gate must not be imposed as a default (nor reached by declaring
it), and a third-party scope may not either while the gate is unbuilt, because there the
gate applies unchanged and nothing measures an oracle strength to decide it. One message
for both would send the second operator looking for a setting.

**Absence is a state, not a default.** ``None`` means *this deployment declared none*.
The failure this suite is written against is the one the requirement names: a product that
supplies the personal band as a default has imposed the very gate D17 removed, and a
report would show a target nobody chose as though someone had. So
:attr:`EscapeReport.meets_target` returns ``None`` rather than ``False`` when either input
is missing — ``False`` reads as a shortfall, which is a claim about a comparison that was
never made.

**The declaration is configuration.** FR-156's rule reaches the declaration itself, so
:func:`load_deployment_scope` reads a JSON file through the seam the envelope, the budgets
and the composition already provide, and refuses a misspelled key rather than defaulting
past it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli import SPECIFY_ARGS, configure, conversation
from test_escape import deployed_service
from typer.testing import CliRunner

from sofact.cli import app
from sofact.escape import load_deployment_scope, measure_escapes
from sofact.service import FactoryService
from sofact.views import (
	L4_GATE_THETA,
	PERSONAL_AUTONOMY_BAND,
	AutonomyLevel,
	Consumer,
	DeploymentScope,
	now,
)

RUNNER = CliRunner()

PERSONAL = Consumer.OPERATOR
THIRD_PARTY = Consumer.THIRD_PARTY


def scope(
	*,
	consumer: Consumer = PERSONAL,
	target: AutonomyLevel = AutonomyLevel.L3,
	escape_tracking: bool = True,
	declared_by: str = "the operator",
) -> DeploymentScope:
	"""A scope that is admissible unless the test varies the one field it is about."""
	return DeploymentScope(
		consumer=consumer,
		target=target,
		escape_tracking=escape_tracking,
		declared_by=declared_by,
		declared_at=now(),
	)


def measured(declared: DeploymentScope | None, delivered: AutonomyLevel | None):
	"""An escape measurement carrying a scope and a delivery ceiling, and nothing else.

	Over no deployments, because this suite is about the comparison rather than the rate:
	the two are independent, and a test that first had to deploy something would fail for
	the rate's reasons when it is asking about the target's.
	"""
	return measure_escapes(
		deploys=(),
		reports=(),
		decompositions=(),
		escapes=(),
		scope=declared,
		delivered_ceiling=delivered,
	)


def delivered(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Drive the real CLI to a deployed delivery, through every gate before it.

	``test_cli``'s ``_deployed`` does the same and is private, and reaching into another
	module's underscore is a coupling pyright refuses and a reader should not have to
	reason about. The steps are four public verbs and a ``configure``, which is what a
	deployment runs.
	"""
	configure(tmp_path, monkeypatch)
	conversation(home)
	for argv in (
		["probe"],
		["contract", "--command", "true"],
		["specify", "--approve", *SPECIFY_ARGS],
		["decompose", "--approve"],
		["plan"],
	):
		step = RUNNER.invoke(app, ["--home", str(home), *argv])
		assert step.exit_code == 0, (argv, step.output)
	root = tmp_path / "delivery"
	root.mkdir()
	rendered = RUNNER.invoke(app, ["--home", str(home), "deliver", "--root", str(root)])
	assert rendered.exit_code == 0, rendered.output
	report_id = rendered.output.split("delivery report ")[1].split("\n")[0].strip()
	approved = RUNNER.invoke(
		app, ["--home", str(home), "deploy", "--approve", report_id, "--by", "operator"]
	)
	assert approved.exit_code == 0, approved.output


# --------------------------------------------------------------------------- #
# the refusals, which are the API being hard to get wrong
# --------------------------------------------------------------------------- #


class TestATargetThisBuildCannotHonour:
	"""Four refusals, and each is a distinct sentence because each has a distinct remedy.

	A type that refused all four with one message would be a type whose operator cannot
	tell "you are aiming at the wrong band" from "the instrument that would admit you is
	not built yet".
	"""

	def test_the_personal_band_admits_l2_and_l3(self) -> None:
		for level in PERSONAL_AUTONOMY_BAND:
			assert scope(target=level).target is level

	def test_a_personal_target_of_l4_is_refused_as_the_gate_imposed_by_a_side_door(self) -> None:
		"""FR-157 says the θ gate "must not be imposed as a default" for D17's case. The
		symmetric error is a deployment that grants itself the level the gate withholds —
		and declaring it would be the gate reached by the other door."""
		with pytest.raises(ValueError, match="must not be imposed as a default"):
			scope(target=AutonomyLevel.L4)

	def test_a_personal_target_below_the_band_is_refused_for_the_opposite_reason(self) -> None:
		"""Below L2 the mandated escape-rate tracking is measuring a level nobody is aiming
		at. The two ends of the band are refused for different reasons, which is why the
		message names both."""
		with pytest.raises(ValueError, match="measuring a level nobody is aiming at"):
			scope(target=AutonomyLevel.L1)

	def test_a_third_party_target_of_l4_is_refused_because_the_gate_is_not_built(self) -> None:
		"""The gate applies *unchanged* to a third party, so L4 is reachable through it —
		and the gate is not built, so nothing here measures an oracle strength to decide
		it. Declaring the target does not discharge it."""
		with pytest.raises(ValueError, match="does not discharge the gate"):
			scope(consumer=THIRD_PARTY, target=AutonomyLevel.L4)

	def test_the_two_l4_refusals_are_not_the_same_refusal(self) -> None:
		"""Read together, because the whole reason the type carries two branches is that a
		reader who saw one message would apply the wrong remedy to the other case."""
		with pytest.raises(ValueError) as personal:
			scope(target=AutonomyLevel.L4)
		with pytest.raises(ValueError) as third_party:
			scope(consumer=THIRD_PARTY, target=AutonomyLevel.L4)

		assert "must not be imposed as a default" in str(personal.value)
		assert "not built in this build" in str(third_party.value)
		assert str(personal.value) != str(third_party.value)

	def test_a_scope_that_declines_the_instrument_is_refused(self) -> None:
		"""NFR-024's rule: the product must refuse to report a target it has not measured.
		FR-157 pairs its band with the rate, so a target with no instrument is the
		unmeasured target the requirement refuses."""
		with pytest.raises(ValueError, match="no escape-rate tracking"):
			scope(escape_tracking=False)

	def test_the_instrument_is_required_of_a_third_party_scope_too(self) -> None:
		"""FR-157 names the rate beside the personal band, but its argument is general:
		with no external market there is no exogenous escape signal at all."""
		with pytest.raises(ValueError, match="no escape-rate tracking"):
			scope(consumer=THIRD_PARTY, target=AutonomyLevel.L2, escape_tracking=False)

	def test_building_the_gate_opens_the_third_party_band(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""FR-024 to FR-035 is one boolean away, and this is the boolean. The refusal is
		conditional on it rather than unconditional with a self-check arm, because an
		unconditional raise would mean the flag could never do the one thing its docstring
		says it does — and a flag that cannot change the behaviour it gates is a comment
		with a type."""
		monkeypatch.setattr("sofact.views.THETA_GATE_BUILT", True)

		admitted = scope(consumer=THIRD_PARTY, target=AutonomyLevel.L4)

		assert admitted.target is AutonomyLevel.L4
		assert admitted.admits_l4
		assert scope(target=AutonomyLevel.L3).admits_l4 is False, (
			"and a personal scope still does not, whatever the gate's state"
		)


class TestTheBandAndTheComparison:
	def test_the_personal_band_is_the_requirements_own_range(self) -> None:
		assert scope().band == PERSONAL_AUTONOMY_BAND
		assert PERSONAL_AUTONOMY_BAND == (AutonomyLevel.L2, AutonomyLevel.L3)

	def test_a_third_party_band_runs_to_l4_in_principle(self) -> None:
		"""The gate is applied *unchanged* rather than raised, so the top of the range is
		reachable in principle and by the gate in practice. Those are different statements
		and :attr:`admits_l4` is what keeps them apart."""
		third_party = scope(consumer=THIRD_PARTY, target=AutonomyLevel.L3)

		assert third_party.band == (AutonomyLevel.L2, AutonomyLevel.L4)
		assert not third_party.admits_l4, "in principle is not in this build"

	def test_no_personal_scope_admits_l4_whatever_the_gates_state(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.setattr("sofact.views.THETA_GATE_BUILT", True)

		assert not scope().admits_l4

	def test_met_by_is_a_comparison_against_the_delivery_not_the_modules(self) -> None:
		declared = scope(target=AutonomyLevel.L3)

		assert declared.met_by(AutonomyLevel.L3), "meeting the target exactly is meeting it"
		assert declared.met_by(AutonomyLevel.L4), "exceeding it is meeting it"
		assert not declared.met_by(AutonomyLevel.L2)

	def test_the_caveats_name_the_gate_and_the_bands_two_ends(self) -> None:
		"""A target is an ambition, and what it does not claim is stated rather than left
		to inference — the discipline :attr:`EscapeReport.caveats` keeps one level down."""
		caveats = scope().caveats

		assert len(caveats) == 3
		assert any(f"{L4_GATE_THETA:g}" in caveat for caveat in caveats)
		assert any("raises no ceiling" in caveat for caveat in caveats)
		assert any("may not" in caveat for caveat in caveats)


# --------------------------------------------------------------------------- #
# absence is a state, not a default
# --------------------------------------------------------------------------- #


class TestAnAbsentTargetIsNotAMissedOne:
	"""The vacuous-pass rule, at the requirement that most invites breaking it.

	A deployment with no target has one fewer thing to be measured against, and a report
	that printed "not met" over it would report a shortfall where no comparison was made.
	"""

	def test_no_declared_scope_is_none_rather_than_false(self) -> None:
		assert measured(None, AutonomyLevel.L3).meets_target is None

	def test_a_declared_scope_with_no_delivery_is_none_too(self) -> None:
		"""The same case from the other side: the target exists and there is nothing to
		compare it against, which is a project that has not delivered rather than one that
		fell short."""
		assert measured(scope(), None).meets_target is None

	def test_neither_input_is_a_shortfall_of_none(self) -> None:
		assert measured(None, None).target_shortfall is None
		assert measured(None, AutonomyLevel.L0).target_shortfall is None
		assert measured(scope(), None).target_shortfall is None

	def test_the_comparison_is_made_once_both_inputs_are_present(self) -> None:
		assert measured(scope(target=AutonomyLevel.L3), AutonomyLevel.L3).meets_target is True
		assert measured(scope(target=AutonomyLevel.L3), AutonomyLevel.L2).meets_target is False

	def test_the_shortfall_is_signed_so_headroom_is_not_erased(self) -> None:
		"""A deployment aiming at L2 whose delivery sustains L3 has headroom, not a problem.
		Clamping at zero would erase the difference between meeting a target exactly and
		exceeding it, which is the one thing a reader of the number wants."""
		assert measured(scope(target=AutonomyLevel.L3), AutonomyLevel.L1).target_shortfall == 2
		assert measured(scope(target=AutonomyLevel.L3), AutonomyLevel.L3).target_shortfall == 0
		assert measured(scope(target=AutonomyLevel.L2), AutonomyLevel.L3).target_shortfall == -1

	def test_a_declared_target_does_not_make_the_rate_claim_anything(self) -> None:
		"""The two requirements are independent: FR-157's ambition is not FR-022's
		measurement, and a scope over zero deployments still clears nothing."""
		report = measured(scope(), AutonomyLevel.L3)

		assert report.deployed_changes == 0
		assert report.discharged == ()
		assert report.not_implemented == ("FR-021", "FR-022", "FR-023")


# --------------------------------------------------------------------------- #
# the declaration is configuration
# --------------------------------------------------------------------------- #


class TestTheLoader:
	def test_the_object_bare_is_accepted(self, tmp_path: Path) -> None:
		path = tmp_path / "scope.json"
		path.write_text(
			'{"consumer": "operator", "target": 3, "escape_tracking": true, '
			'"declared_by": "the CTO", "note": "solo project"}'
		)

		loaded = load_deployment_scope(path)

		assert loaded.consumer is Consumer.OPERATOR
		assert loaded.target is AutonomyLevel.L3
		assert loaded.escape_tracking
		assert loaded.declared_by == "the CTO"
		assert loaded.note == "solo project"

	def test_the_same_object_under_a_key_is_accepted(self, tmp_path: Path) -> None:
		path = tmp_path / "scope.json"
		path.write_text(
			'{"deployment_scope": {"consumer": "third_party", "target": 2, '
			'"escape_tracking": true}}'
		)

		loaded = load_deployment_scope(path)

		assert loaded.consumer is Consumer.THIRD_PARTY
		assert loaded.target is AutonomyLevel.L2
		assert loaded.declared_by.endswith("scope.json"), "the file declares it by default"

	def test_a_misspelled_consumer_is_refused_not_defaulted(self, tmp_path: Path) -> None:
		"""The failure this family of loaders guards against: a key that reads as
		configured while configuring nothing."""
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "owner", "target": 2, "escape_tracking": true}')

		with pytest.raises(ValueError, match="is not one of"):
			load_deployment_scope(path)

	def test_a_target_that_is_not_a_level_is_refused(self, tmp_path: Path) -> None:
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "operator", "target": 7, "escape_tracking": true}')

		with pytest.raises(ValueError, match="is not an autonomy level"):
			load_deployment_scope(path)

	@pytest.mark.parametrize("missing", ["consumer", "target", "escape_tracking"])
	def test_a_scope_missing_a_required_field_is_refused(
		self, tmp_path: Path, missing: str
	) -> None:
		"""Not a partial declaration: a scope that defaulted either of these would default
		into the very thing FR-157 refuses."""
		body = {"consumer": "operator", "target": 2, "escape_tracking": True}
		del body[missing]
		path = tmp_path / "scope.json"
		path.write_text(json.dumps(body))

		with pytest.raises(ValueError, match=f"declares no {missing}"):
			load_deployment_scope(path)

	def test_escape_tracking_as_a_string_is_refused(self, tmp_path: Path) -> None:
		"""``"false"`` is truthy, so a scope that stated it as a string would read as
		tracking while tracking nothing."""
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "operator", "target": 2, "escape_tracking": "false"}')

		with pytest.raises(ValueError, match="must be true or false"):
			load_deployment_scope(path)

	def test_an_unknown_field_is_refused(self, tmp_path: Path) -> None:
		path = tmp_path / "scope.json"
		path.write_text(
			'{"consumer": "operator", "target": 2, "escape_tracking": true, "band": "L2"}'
		)

		with pytest.raises(ValueError, match="not a scope field"):
			load_deployment_scope(path)

	def test_a_note_that_is_not_a_string_is_refused(self, tmp_path: Path) -> None:
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "operator", "target": 2, "escape_tracking": true, "note": 3}')

		with pytest.raises(ValueError, match="note must be a string"):
			load_deployment_scope(path)

	def test_the_loader_does_not_bypass_the_types_refusals(self, tmp_path: Path) -> None:
		"""The file is a way to declare a target, not a way around the type. A personal L4
		in JSON is refused with the same sentence a Python caller gets."""
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "operator", "target": 4, "escape_tracking": true}')

		with pytest.raises(ValueError, match="must not be imposed as a default"):
			load_deployment_scope(path)

	def test_a_non_object_is_refused(self, tmp_path: Path) -> None:
		path = tmp_path / "scope.json"
		path.write_text("[1, 2]")

		with pytest.raises(ValueError, match="expected a JSON object"):
			load_deployment_scope(path)

	def test_malformed_json_is_a_message_not_a_traceback(self, tmp_path: Path) -> None:
		path = tmp_path / "scope.json"
		path.write_text("{not json")

		with pytest.raises(ValueError, match="not valid JSON"):
			load_deployment_scope(path)

	def test_an_unreadable_file_is_a_message_not_a_traceback(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="cannot read deployment scope"):
			load_deployment_scope(tmp_path / "absent.json")


# --------------------------------------------------------------------------- #
# the seam, and the verb
# --------------------------------------------------------------------------- #


class TestTheFactoryCarriesTheScope:
	def test_no_scope_configured_is_the_declared_none_state(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``None`` is *this deployment declared none*, which is not the personal default.
		A factory that supplied one would be product-scoping the target."""
		service = FactoryService(home=home, llm=None, specs={})

		assert service.scope is None

	async def test_the_scope_reaches_the_measurement(self, home: Path, tmp_path: Path) -> None:
		declared = scope()
		service = FactoryService(home=home, llm=None, specs={}, scope=declared)

		report = await service.escape_report()

		assert report.scope is declared
		assert report.delivered_ceiling is None, "nothing has been delivered yet"
		assert report.meets_target is None

	async def test_the_delivery_ceiling_is_read_off_the_latest_report(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Compared against the number the render computed rather than one derived again
		here, so the target and the rate cannot disagree about what was delivered.

		Driven through the service rather than the CLI: the CLI's verbs run
		``asyncio.run``, which cannot be called from inside this test's own loop.
		"""
		service, _report_id, _contract_id = await deployed_service(home, tmp_path)
		service.scope = scope(target=AutonomyLevel.L2)

		report = await service.escape_report()

		assert report.delivered_ceiling is not None
		assert report.meets_target is False, "the synthetic delivery sustains L0"
		assert report.target_shortfall == 2, "L0 delivered against an L2 target"


class TestTheScopeVerb:
	def test_no_declared_scope_exits_nonzero_and_says_there_is_no_default(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["--home", str(home), "scope"])

		assert result.exit_code == 1, result.output
		assert "declared none" in result.output
		assert "there is no default" in result.output

	def test_a_declared_scope_prints_its_band_and_what_it_does_not_claim(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "operator", "target": 3, "escape_tracking": true}')
		monkeypatch.setenv("SOFACT_SCOPE", str(path))

		result = RUNNER.invoke(app, ["--home", str(home), "scope"])

		assert result.exit_code == 0, result.output
		assert "target L3, band L2-L3" in result.output
		assert "raises no ceiling" in result.output

	def test_an_unreadable_scope_is_a_message_not_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.setenv("SOFACT_SCOPE", str(tmp_path / "absent.json"))

		result = RUNNER.invoke(app, ["--home", str(home), "scope"])

		assert result.exit_code == 1, result.output
		assert "cannot read SOFACT_SCOPE" in result.output

	def test_a_third_party_scope_says_which_gate_bounds_it(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The note names what this *build* can decide, so it is conditional on
		``admits_l4`` rather than on the consumer alone — a hardcoded sentence would go on
		saying L4 is out of reach after FR-024 to FR-035 puts it in reach."""
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "third_party", "target": 2, "escape_tracking": true}')
		monkeypatch.setenv("SOFACT_SCOPE", str(path))

		result = RUNNER.invoke(app, ["--home", str(home), "scope"])

		assert result.exit_code == 0, result.output
		assert "leaves the" in result.output and "unchanged" in result.output

	def test_the_note_is_absent_once_the_gate_can_be_decided(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "third_party", "target": 2, "escape_tracking": true}')
		monkeypatch.setenv("SOFACT_SCOPE", str(path))
		monkeypatch.setattr("sofact.views.THETA_GATE_BUILT", True)

		result = RUNNER.invoke(app, ["--home", str(home), "scope"])

		assert result.exit_code == 0, result.output
		assert "not built in this build" not in result.output


class TestTheEscapesVerbNamesTheTarget:
	def test_no_declared_target_says_no_comparison_is_made(self, home: Path) -> None:
		"""Exit zero, because a deployment that declared no target has not failed
		anything — it has one fewer thing to be measured against, which the screen says."""
		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 0, result.output
		assert "declared no target" in result.output
		assert "no default" in result.output

	def test_a_delivery_short_of_the_target_exits_nonzero_and_names_the_gap(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The comparison at the operator's surface, and a script can gate on it. The
		synthetic delivery sustains L0, so an L2 target is two levels short."""
		delivered(home, tmp_path, monkeypatch)
		path = tmp_path / "scope.json"
		path.write_text('{"consumer": "operator", "target": 2, "escape_tracking": true}')
		monkeypatch.setenv("SOFACT_SCOPE", str(path))

		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 1, result.output
		assert "is 2 level(s) short of the target" in result.output
		assert "raises no ceiling" in result.output

	def test_a_declared_target_with_nothing_delivered_compares_nothing(self, home: Path) -> None:
		"""Three states, not two. The middle one is why the screen is not a boolean."""
		result = RUNNER.invoke(app, ["--home", str(home), "escapes"])

		assert result.exit_code == 0, result.output
		assert "declared no target" in result.output
