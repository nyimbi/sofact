"""§1.3's delivery envelope: the bounds, the refusal, and the actuals (FR-057, NFR-025).

Three things are under test and they are separable. The *types* refuse to express a
bound that bounds nothing and a measurement that is half-judged. The *loader* is a
configuration seam, so its failures are the interesting part — a typo that changes
nothing and reports success is the failure mode a config reader has. The *measurement*
is where the honesty requirement lives: a dimension nothing measures must read as
unmeasured, never as satisfied.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError
from synthetic import (
	elicitation_to_contract,
	gated_contract,
	specify_and_approve,
	synthetic_service,
)

from sofact.decomposition import gate, propose
from sofact.envelope import MEASURED_AT_P3, UNMEASURED_AT_P3, load_envelope, measure
from sofact.service import FactoryService
from sofact.views import (
	Contract,
	DeliveryEnvelope,
	DimensionBound,
	EnvelopeActuals,
	EnvelopeDimension,
	EnvelopeMeasurement,
	ModuleClass,
	OracleClass,
	OracleDeclaration,
)

MakeContract = Callable[..., Contract]
"""``make_contract`` builds a contract from ``(statement, oracle)`` pairs."""


def oracle(kind: OracleClass = OracleClass.CONTRACT) -> OracleDeclaration:
	"""The smallest real oracle, for contracts built directly rather than elicited."""
	return OracleDeclaration(oracle_class=kind, description=f"a {kind.value} oracle")


def write_envelope(tmp_path: Path, payload: object) -> Path:
	"""A JSON envelope file, written the way an operator would hand one over."""
	path = tmp_path / "envelope.json"
	path.write_text(json.dumps(payload), encoding="utf-8")
	return path


# --------------------------------------------------------------------------- #
# the bounds
# --------------------------------------------------------------------------- #


class TestABoundBoundsSomething:
	def test_the_defaults_are_the_specs_own_numbers(self) -> None:
		"""NFR-025 makes the envelope a hypothesis under test; §1.3's table is the
		hypothesis, and a default that quietly differed from it would make an operator's
		comparison against §1.3 a comparison against numbers nobody used."""
		envelope = DeliveryEnvelope()

		assert envelope.modules.stated() == "8-25 modules"
		assert envelope.delivered_loc.stated() == "3000-15000 LOC"
		assert envelope.human_gates.stated() == "4 gates"
		assert envelope.wall_clock_days.stated() == "2-10 days"

	def test_every_dimension_in_the_enum_has_a_bound(self) -> None:
		"""The enum and the type are two spellings of one list. A dimension added to the
		enum with no field would be a dimension §1.3 bounds and the report never names."""
		envelope = DeliveryEnvelope()

		for dimension in EnvelopeDimension:
			assert envelope.bound(dimension) is not None

	def test_a_bound_with_neither_end_is_refused(self) -> None:
		"""An unbounded dimension belongs out of the envelope, not in it with two empty
		fields: a reader would count it as a dimension that was checked."""
		with pytest.raises(ValidationError, match="bounds nothing"):
			DimensionBound(unit="modules")

	def test_an_empty_range_is_refused(self) -> None:
		with pytest.raises(ValidationError, match="no delivery could ever be inside it"):
			DimensionBound(unit="modules", minimum=25, maximum=8)

	def test_a_ceiling_only_bound_admits_everything_below_it(self) -> None:
		bound = DimensionBound(unit="integrations", maximum=3)

		assert bound.admits(0)
		assert bound.admits(3)
		assert not bound.admits(4)
		assert bound.exceeded_by(4)
		assert not bound.below(0), "a bound with no floor cannot be under one"

	def test_the_two_ends_are_different_claims(self) -> None:
		"""§1.3: over a ceiling is the over-scoped goal FR-057 refuses; under a floor is
		a small delivery, which is legitimate. Keeping them apart is what lets the gate
		refuse one and report the other."""
		bound = DeliveryEnvelope().modules

		assert bound.exceeded_by(30)
		assert not bound.exceeded_by(2), "two modules is small, not over-scoped"
		assert bound.below(2)
		assert not bound.below(30)


# --------------------------------------------------------------------------- #
# the measurements
# --------------------------------------------------------------------------- #


class TestAMeasurementIsWholeOrAbsent:
	def test_a_missing_reading_is_never_inside_the_envelope(self) -> None:
		"""The one wrong default available here. An unmeasured dimension reported as
		within makes it indistinguishable from a satisfied one."""
		measurement = EnvelopeMeasurement(
			dimension=EnvelopeDimension.SYSTEMS,
			bound=DeliveryEnvelope().systems,
			detail="nothing declares a system",
		)

		assert measurement.actual is None
		assert measurement.within is None, "unmeasured is not the same as within"
		assert "unmeasured" in measurement.statement

	def test_a_half_measurement_is_refused_by_the_type(self) -> None:
		with pytest.raises(ValidationError, match="half-measurement"):
			EnvelopeMeasurement(
				dimension=EnvelopeDimension.MODULES,
				bound=DeliveryEnvelope().modules,
				actual=9,
				detail="nine modules",
			)

	def test_a_measurement_that_contradicts_its_own_bound_is_refused(self) -> None:
		"""A caller's arithmetic is not a guard: the type recomputes it."""
		with pytest.raises(ValidationError, match="which is outside"):
			EnvelopeMeasurement(
				dimension=EnvelopeDimension.MODULES,
				bound=DeliveryEnvelope().modules,
				actual=40,
				within=True,
				detail="forty modules",
			)

	def test_an_exceeded_actuals_names_only_the_ceilings(self) -> None:
		envelope = DeliveryEnvelope()
		actuals = EnvelopeActuals(
			envelope=envelope,
			measurements=(
				EnvelopeMeasurement(
					dimension=EnvelopeDimension.MODULES,
					bound=envelope.modules,
					actual=40,
					within=False,
					detail="forty modules",
				),
				EnvelopeMeasurement(
					dimension=EnvelopeDimension.HUMAN_GATES,
					bound=envelope.human_gates,
					actual=2,
					within=False,
					detail="two gates",
				),
			),
		)

		assert [m.dimension for m in actuals.exceeded] == [EnvelopeDimension.MODULES]
		assert [m.dimension for m in actuals.below] == [EnvelopeDimension.HUMAN_GATES]
		assert not actuals.is_within

	def test_within_is_not_a_claim_about_the_unmeasured(self) -> None:
		"""``is_within`` is true when no *measured* dimension is over. The unmeasured
		ones are named separately, and a report that printed the boolean alone would read
		as "the delivery is inside the envelope" while three were never looked at."""
		envelope = DeliveryEnvelope()
		actuals = EnvelopeActuals(
			envelope=envelope,
			measurements=(
				EnvelopeMeasurement(
					dimension=EnvelopeDimension.MODULES,
					bound=envelope.modules,
					actual=9,
					within=True,
					detail="nine modules",
				),
				EnvelopeMeasurement(
					dimension=EnvelopeDimension.DELIVERED_LOC,
					bound=envelope.delivered_loc,
					detail="nothing reads the delivered source",
				),
			),
		)

		assert actuals.is_within
		assert [m.dimension for m in actuals.unmeasured] == [EnvelopeDimension.DELIVERED_LOC]


# --------------------------------------------------------------------------- #
# the configuration seam
# --------------------------------------------------------------------------- #


class TestTheEnvelopeIsConfiguration:
	def test_a_bare_object_of_dimensions_is_read(self, tmp_path: Path) -> None:
		path = write_envelope(tmp_path, {"modules": {"minimum": 1, "maximum": 5}})

		envelope = load_envelope(path)

		assert envelope.modules.maximum == 5

	def test_the_envelope_key_is_also_accepted(self, tmp_path: Path) -> None:
		path = write_envelope(tmp_path, {"envelope": {"modules": {"minimum": 1, "maximum": 5}}})

		assert load_envelope(path).modules.maximum == 5

	def test_a_partial_override_keeps_the_other_fields(self, tmp_path: Path) -> None:
		"""An operator raising one ceiling should not have to restate the other seven
		dimensions — and the floor they did not mention must survive, or the envelope
		would widen by omission."""
		path = write_envelope(tmp_path, {"human_minutes": {"maximum": 900}})

		envelope = load_envelope(path)

		assert envelope.human_minutes.maximum == 900
		assert envelope.human_minutes.minimum == 180, "the unmentioned floor is not dropped"
		assert envelope.delivered_loc.maximum == 15000, "the other dimensions are untouched"

	def test_an_unknown_dimension_is_refused(self, tmp_path: Path) -> None:
		"""A typo that changes nothing and reports success is the failure mode a config
		seam has. ``extra="forbid"`` on the type cannot catch this one, because the key
		never reaches it."""
		path = write_envelope(tmp_path, {"moduels": {"maximum": 5}})

		with pytest.raises(ValueError, match=r"is not a §1\.3 dimension"):
			load_envelope(path)

	def test_an_unknown_field_within_a_dimension_is_refused(self, tmp_path: Path) -> None:
		path = write_envelope(tmp_path, {"modules": {"ceiling": 5}})

		with pytest.raises(ValueError, match="is not a bound"):
			load_envelope(path)

	def test_an_empty_envelope_is_refused(self, tmp_path: Path) -> None:
		"""An envelope that bounds nothing would let every decomposition through while
		reading as configured — the same fail-open shape the type refuses one level down."""
		path = write_envelope(tmp_path, {})

		with pytest.raises(ValueError, match="bounds nothing"):
			load_envelope(path)

	def test_a_narrowed_ceiling_that_empties_the_range_is_refused(self, tmp_path: Path) -> None:
		"""The floor survives the merge, so the bound type gets to refuse the empty range
		with its own sentence rather than the loader inventing one."""
		path = write_envelope(tmp_path, {"modules": {"maximum": 5}})

		with pytest.raises(ValidationError, match="no delivery could ever be inside it"):
			load_envelope(path)

	def test_missing_file_names_the_path(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="cannot read envelope"):
			load_envelope(tmp_path / "absent.json")

	def test_invalid_json_names_the_file(self, tmp_path: Path) -> None:
		path = tmp_path / "envelope.json"
		path.write_text("{not json", encoding="utf-8")

		with pytest.raises(ValueError, match="not valid JSON"):
			load_envelope(path)


# --------------------------------------------------------------------------- #
# the actuals
# --------------------------------------------------------------------------- #


class TestWhatIsMeasuredAndWhatIsNot:
	def test_no_decomposition_measures_nothing(self) -> None:
		"""Reporting module counts for a project whose P3 never ran would be reporting
		the absence of an artefact as a measurement of it."""
		actuals = measure(DeliveryEnvelope(), None)

		assert actuals.unmeasured == actuals.measurements
		assert actuals.is_within, "nothing measured is not the same as something exceeded"

	def test_the_measured_set_is_exactly_what_a_decomposition_can_settle(self) -> None:
		"""The constant and the enum are two spellings of one partition, and a dimension
		falling out of both would be measured by neither and reported by neither."""
		assert set(MEASURED_AT_P3) | set(UNMEASURED_AT_P3) == set(EnvelopeDimension)
		assert not set(MEASURED_AT_P3) & set(UNMEASURED_AT_P3)

	async def test_a_decomposition_measures_modules_and_integrations(
		self, home: Path, tmp_path: Path
	) -> None:
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await gated_contract(service)
		decomposition = await service.latest_decomposition(contract_id)
		assert decomposition is not None

		actuals = measure(DeliveryEnvelope(), decomposition)

		by_dimension = {m.dimension: m for m in actuals.measurements}
		assert by_dimension[EnvelopeDimension.MODULES].actual == len(decomposition.modules)
		assert by_dimension[EnvelopeDimension.HUMAN_GATES].actual == 4

	async def test_an_unmeasured_dimension_names_what_would_be_needed(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Every unmeasured dimension carries a work item, not an apology: a reader of
		the delivery report has to be able to act on it."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await gated_contract(service)
		decomposition = await service.latest_decomposition(contract_id)
		assert decomposition is not None

		actuals = measure(DeliveryEnvelope(), decomposition)

		# The loop below asserts inside itself, so an empty set would pass it. The set is
		# the four dimensions a decomposition cannot settle *plus* the value hypothesis,
		# which this caller did not ask about — so the count is not UNMEASURED_AT_P3.
		assert {m.dimension for m in actuals.unmeasured} == {
			*UNMEASURED_AT_P3,
			EnvelopeDimension.VALUE_HYPOTHESIS,
		}
		for measurement in actuals.unmeasured:
			assert measurement.detail
			assert measurement.actual is None
			assert measurement.within is None

	async def test_the_value_hypothesis_is_unmeasured_when_the_caller_did_not_ask(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Three states, not two. P3's gate does not read the specification, so a
		two-state flag would make every P3 run report a missing value hypothesis — a
		measurement of the caller's silence, printed as a fact about the project."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await gated_contract(service)
		decomposition = await service.latest_decomposition(contract_id)
		assert decomposition is not None

		unasked = measure(DeliveryEnvelope(), decomposition)
		declared = measure(DeliveryEnvelope(), decomposition, value_hypothesis_declared=True)

		assert (
			next(
				m for m in unasked.measurements if m.dimension is EnvelopeDimension.VALUE_HYPOTHESIS
			).actual
			is None
		)
		assert (
			next(
				m
				for m in declared.measurements
				if m.dimension is EnvelopeDimension.VALUE_HYPOTHESIS
			).actual
			== 1
		)

	async def test_a_wide_envelope_refuses_nothing_and_a_narrow_one_exceeds(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The measurement is what the refusal reads, so both states have to be real."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await gated_contract(service)
		decomposition = await service.latest_decomposition(contract_id)
		assert decomposition is not None

		wide = measure(DeliveryEnvelope(), decomposition)
		narrow = measure(
			DeliveryEnvelope(modules=DimensionBound(unit="modules", maximum=1)), decomposition
		)

		assert wide.is_within
		assert [m.dimension for m in narrow.exceeded] == [EnvelopeDimension.MODULES]

	async def test_the_integration_count_reads_the_module_class(
		self, home: Path, tmp_path: Path
	) -> None:
		"""G6 is the external-integration class (§14). Counting it is reading a
		declaration the decomposition already carries, not inspecting a workspace."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await gated_contract(service)
		decomposition = await service.latest_decomposition(contract_id)
		assert decomposition is not None

		actuals = measure(DeliveryEnvelope(), decomposition)
		expected = sum(1 for m in decomposition.modules if m.module_class is ModuleClass.G6)

		assert (
			next(
				m
				for m in actuals.measurements
				if m.dimension is EnvelopeDimension.EXTERNAL_INTEGRATIONS
			).actual
			== expected
		)


# --------------------------------------------------------------------------- #
# FR-057 — the refusal
# --------------------------------------------------------------------------- #


class TestTheGateRefusesAnOverScopedProposal:
	def test_no_envelope_asserts_nothing_and_says_so(self, make_contract: MakeContract) -> None:
		"""A project run without an envelope is not thereby over-scoped. The check
		reports that it measured nothing rather than passing silently."""
		contract = make_contract(("the api returns 200", oracle()))

		check = next(
			c
			for c in gate(propose(contract), contract).checks
			if c.name == "within_delivery_envelope"
		)

		assert check.passed
		assert "no envelope was supplied" in check.detail

	async def test_an_over_scoped_proposal_fails_and_names_the_dimension(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-057's own words: "must say which dimension was exceeded"."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await gated_contract(service)
		contract = await service.contract_by_id(contract_id)
		decomposition = await service.latest_decomposition(contract_id)
		assert decomposition is not None

		check = next(
			c
			for c in gate(
				decomposition,
				contract,
				envelope=DeliveryEnvelope(modules=DimensionBound(unit="modules", maximum=1)),
			).checks
			if c.name == "within_delivery_envelope"
		)

		assert not check.passed
		assert "modules" in check.detail
		assert "FR-057" in check.detail

	async def test_a_small_proposal_is_reported_and_passes(
		self, home: Path, tmp_path: Path
	) -> None:
		"""§1.3's numbers are targets, not measurements. A factory that refused to build
		anything smaller than a platform would refuse the work that earns it the trust
		to attempt one."""
		service = synthetic_service(home, tmp_path, "complete")
		_, contract_id = await gated_contract(service)
		contract = await service.contract_by_id(contract_id)
		decomposition = await service.latest_decomposition(contract_id)
		assert decomposition is not None

		check = next(
			c
			for c in gate(decomposition, contract, envelope=DeliveryEnvelope()).checks
			if c.name == "within_delivery_envelope"
		)

		assert check.passed, "a small delivery is not an over-scoped goal"
		assert "below the floor" in check.detail
		assert "unmeasured" in check.detail

	async def test_the_service_refuses_at_p3_when_the_envelope_is_exceeded(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The refusal reaches the gate an operator actually runs, not only the function.

		``gated_contract`` cannot be used here, and that is the point: it approves, and
		with a one-module ceiling the approval is refused. So the test walks P0 to P2 by
		hand and stops at P3's proposal.
		"""
		service = FactoryService(
			home=home,
			llm=None,
			specs=synthetic_service(home, tmp_path, "complete").harness_table(),
			envelope=DeliveryEnvelope(modules=DimensionBound(unit="modules", maximum=1)),
		)
		_, contract_id = await elicitation_to_contract(service)
		await specify_and_approve(service, contract_id)

		proposal = await service.decompose(contract_id)
		result = await service.decomposition_gate(proposal.id)

		assert result.failed, "an over-scoped decomposition cannot be approved (FR-057)"
		assert any(c.name == "within_delivery_envelope" for c in result.failed)
		with pytest.raises(ValueError, match="fails its own preconditions"):
			await service.approve_decomposition(proposal.id, by="operator")
