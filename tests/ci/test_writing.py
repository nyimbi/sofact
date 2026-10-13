"""P8 — the two artefacts SoFact owes are written, and they are facts not prose (FR-117).

ADR-0040 scoped the delivery-artefact check to the two kinds the factory produces, and
nothing produced them: a report over a root with nothing in it correctly failed its own
check, so ``sofact deliver`` could not succeed on a fresh project. A factory that refuses
to deliver until a human has hand-written the documents it claims to produce is not a
factory, and the check being honest about the shortfall did not make the shortfall
acceptable.

Three properties are under test, and the third is the one that matters:

* **Completeness** — every heading the constant names is in the document. A section that
  went missing would take a qualification with it, and the reader who would notice is the
  one deciding whether to deploy.
* **Fidelity** — a fact in the report is a fact in the document. Specifically the
  awkward ones: an unmeasured envelope dimension reads *unmeasured*, a declared oracle
  rank reads "declared rank N, not measured", and the sentence that requirements were
  verified rather than value survives into both documents.
* **Determinism** — two renders of one report are byte-identical, and the rendering is a
  pure function of the report. This is what makes the documents admissible: a runbook
  written by a language model would be plausible prose about a system nobody ran, and it
  would be indistinguishable from the real thing at exactly the moment it mattered.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from synthetic import (
	decompose_and_approve,
	elicitation_to_contract,
	specify_and_approve,
	synthetic_service,
)

from sofact.delivery import DELIVERY_ARTIFACT_PATHS
from sofact.service import FactoryService
from sofact.views import (
	DeliveryArtifactKind,
	DeliveryEnvelope,
	DeliveryReport,
	EnvelopeDimension,
	OracleClass,
	Phase,
	PhaseGate,
	PhaseStatus,
	VerifiedClause,
)
from sofact.writing import (
	DELIVERY_HEADINGS,
	RUNBOOK_HEADINGS,
	render_delivery_artifacts,
	render_delivery_document,
	render_runbook,
)


def _without_identity(text: str) -> str:
	"""A rendered document with the report id and timestamp blanked out.

	Two renders of one log are two *reports*, so the lines naming which report a
	document came from necessarily differ. Everything else must not: a runbook that
	changed between two renders without anything being built would be a document nobody
	could trust, and comparing the rest is how that is checked.
	"""
	kept = [line for line in text.splitlines() if not line.startswith("Operational notes")]
	return "\n".join(kept)


def a_written_root(tmp_path: Path) -> Path:
	"""A delivery root the artefacts are written into, created if it is not there."""
	root = tmp_path / "delivery"
	root.mkdir(parents=True, exist_ok=True)
	return root


async def a_rendered_report(home: Path, tmp_path: Path) -> tuple[FactoryService, DeliveryReport]:
	"""Drive a real project to a rendered report, and return the service and the report."""
	# NFR-025 makes the envelope configuration, so the fixture names one: an
	# unconfigured service reports no actuals at all, which is a different claim.
	service = synthetic_service(home, tmp_path, "complete", envelope=DeliveryEnvelope())
	await service.probe_harness(None)
	_, contract_id = await elicitation_to_contract(service, commands="true")
	await specify_and_approve(service, contract_id)
	await decompose_and_approve(service, contract_id)
	plan = await service.compile_plan(contract_id)
	report = await service.render_delivery(plan.id, root=a_written_root(tmp_path))
	return service, report


class TestTheFactoryWritesWhatItOwes:
	"""FR-117: the two artefacts SoFact produces are produced by SoFact."""

	async def test_a_rendered_delivery_leaves_both_documents_on_disk(
		self, home: Path, tmp_path: Path
	) -> None:
		await a_rendered_report(home, tmp_path)
		root = a_written_root(tmp_path)

		for kind in (DeliveryArtifactKind.RUNBOOK, DeliveryArtifactKind.REPORT):
			written = root / DELIVERY_ARTIFACT_PATHS[kind]
			assert written.is_file(), f"{kind.value} was not written"
			assert written.read_text(encoding="utf-8").strip(), f"{kind.value} is empty"

	async def test_the_report_the_gate_presents_finds_its_own_artefacts(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The check is *scoped*, not disabled: the two kinds the factory owes are present
		because it wrote them, and the two it does not produce are still reported as
		decisions. A check that passed by having been narrowed would be the bypass
		ADR-0040 warns about."""
		_, report = await a_rendered_report(home, tmp_path)

		present = {a.kind for a in report.artifacts if a.present}
		assert present == {DeliveryArtifactKind.RUNBOOK, DeliveryArtifactKind.REPORT}
		assert {a.kind for a in report.undecided_artifacts} == {
			DeliveryArtifactKind.IMAGE,
			DeliveryArtifactKind.INFRASTRUCTURE,
		}

	async def test_a_render_with_no_root_writes_nothing_and_says_so(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``root is None`` is a real state rather than a failure: the report is rendered
		from the log alone, and a caller that named no root asked for a statement rather
		than a directory."""
		# NFR-025 makes the envelope configuration, so the fixture names one: an
		# unconfigured service reports no actuals at all, which is a different claim.
		service = synthetic_service(home, tmp_path, "complete", envelope=DeliveryEnvelope())
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)

		report = await service.render_delivery(plan.id, root=None)

		undecided = {a.kind for a in report.undecided_artifacts}
		owed = [a for a in report.artifacts if a.kind not in undecided]
		assert owed, "the fixture must owe at least one artefact"
		assert all(not a.present for a in owed)
		assert all("no delivery root was named" in (a.missing_because or "") for a in owed)


class TestTheDocumentsAreFactsNotProse:
	async def test_the_runbook_is_derived_from_the_handover(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-121 makes the lanes the next mode's input, so a runbook describing them
		differently from the handover would be describing a system that does not exist."""
		_, report = await a_rendered_report(home, tmp_path)

		text = render_runbook(report)

		for lane in report.handover.lanes:
			assert f"### {lane.lane} — {lane.description}" in text
		assert report.handover.entry_point in text

	async def test_every_heading_is_written_even_when_its_section_is_empty(
		self, home: Path, tmp_path: Path
	) -> None:
		_, report = await a_rendered_report(home, tmp_path)

		document = render_delivery_document(report)
		runbook = render_runbook(report)

		for heading in DELIVERY_HEADINGS:
			assert f"## {heading}" in document
		for heading in RUNBOOK_HEADINGS:
			assert f"## {heading}" in runbook

	async def test_an_unmeasured_dimension_reads_unmeasured_in_the_document(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The euphemism FR-118 forbids, one artefact along: a document that printed only
		the measured dimensions would read as a delivery inside its envelope."""
		_, report = await a_rendered_report(home, tmp_path)
		assert report.envelope_actuals is not None

		document = render_delivery_document(report)
		unmeasured = [m for m in report.envelope_actuals.measurements if m.actual is None]
		assert unmeasured, "the fixture must have an unmeasured dimension to check"
		for measurement in unmeasured:
			assert f"- **{measurement.dimension.value}**: unmeasured." in document

	async def test_the_value_sentence_survives_into_both_documents(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-086's sentence is the one qualification a reader must not be able to miss,
		and a presentation adapter is the last place it can go missing."""
		_, report = await a_rendered_report(home, tmp_path)

		assert report.value_statement in render_delivery_document(report)
		assert report.value_statement in render_runbook(report)
		assert "verified requirements, not value" in render_runbook(report)

	async def test_a_declared_rank_is_not_printed_as_a_measurement(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-118 requires the declared rank be printed under words that say it is
		declared. ``measured_strength`` is ``None`` for a clause nothing measured, which
		is the case the wording exists for -- and the case a report that printed the
		rank under "measured" would misrepresent."""
		_, report = await a_rendered_report(home, tmp_path)
		declared = VerifiedClause(
			clause_id=report.chain[0].clause_id,
			statement="the ledger records entries",
			oracle_class=OracleClass.PROPERTY,
			rank=3,
		)
		# `model_copy` rather than the constructor: the report the fixture rendered has
		# its own fields, and this test varies exactly one of them.
		with_declared = report.model_copy(update={"verified": (declared,)})

		document = render_delivery_document(with_declared)

		assert "declared rank 3, not measured" in document
		assert "measured 3" not in document, (
			"a declared rank printed under the word 'measured' is the euphemism FR-118 "
			"forbids, and it is the failure this wording exists to prevent"
		)

		# And the other arm: a clause carrying a measured score is printed as measured,
		# because a document that printed "declared rank" for a clause something *did*
		# measure would understate it -- the same error pointing the other way.
		measured = declared.model_copy(update={"measured_strength": 0.83})
		with_measurement = report.model_copy(update={"verified": (measured,)})

		assert "measured 0.83" in render_delivery_document(with_measurement)


class TestTheRenderingIsDeterministic:
	"""The property that makes the documents evidence rather than commentary."""

	async def test_two_renders_of_one_report_are_byte_identical(
		self, home: Path, tmp_path: Path
	) -> None:
		_, report = await a_rendered_report(home, tmp_path)

		assert render_delivery_document(report) == render_delivery_document(report)
		assert render_runbook(report) == render_runbook(report)

	async def test_a_second_render_over_the_same_log_rewrites_the_same_facts(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Re-rendering supersedes the report rather than erasing it (FR-070), so the
		documents a second render writes must not *drift* from the first. They are not
		byte-identical, and the difference is exactly the report id and timestamp: two
		renders are two reports over one log, which is what superseding means. Every line
		that describes the system -- the lanes, the clauses, the commands -- is the same,
		and that is the claim a reader can rely on."""
		service = synthetic_service(home, tmp_path, "complete", envelope=DeliveryEnvelope())
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)
		root = a_written_root(tmp_path)

		await service.render_delivery(plan.id, root=root)
		first = (root / DELIVERY_ARTIFACT_PATHS[DeliveryArtifactKind.RUNBOOK]).read_text(
			encoding="utf-8"
		)
		await service.render_delivery(plan.id, root=root)
		second = (root / DELIVERY_ARTIFACT_PATHS[DeliveryArtifactKind.RUNBOOK]).read_text(
			encoding="utf-8"
		)

		identity = [line for line in first.splitlines() if line.startswith("Operational notes")]
		assert len(identity) == 1, "the runbook names the report it came from"
		assert identity[0] != second.splitlines()[3], "the two renders are two reports"
		assert _without_identity(first) == _without_identity(second)

	async def test_the_document_names_the_report_it_was_rendered_from(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The delivery document is the report's own rendering, so it carries the id the
		deploy gate names. A document that could not be tied to a report would be a
		document that could be approved against a different set of checks (FR-119)."""
		_, report = await a_rendered_report(home, tmp_path)

		assert f"`{report.id}`" in render_delivery_document(report)

	def test_a_report_with_no_checks_is_refused_rather_than_rendered_empty(self) -> None:
		"""The assertion is the contract: a report with no machine checks is not a report
		the deploy gate can present, and rendering one would produce a document whose
		"Machine checks" section was empty — the shape of a complete document."""
		with pytest.raises(AssertionError, match="no machine checks"):
			render_delivery_document(_a_report_without_checks())

	async def test_the_pair_is_rendered_together_and_is_the_pair_the_writer_writes(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``render_delivery_artifacts`` returns both owed kinds, keyed so the writer can
		look a path up by kind — and it returns exactly what the two renderers return.

		The pair is one call rather than two because the documents are one derivation with
		two renderings (FR-121): a caller that could render a runbook without its
		``DELIVERY.md`` could write a runbook quoting a report id no delivery document
		exists for, and the deploy gate would then tie an approval to a report it cannot
		show.
		"""
		_, report = await a_rendered_report(home, tmp_path)

		rendered = render_delivery_artifacts(report)

		assert set(rendered) == {DeliveryArtifactKind.RUNBOOK, DeliveryArtifactKind.REPORT}
		assert rendered[DeliveryArtifactKind.REPORT] == render_delivery_document(report)
		assert rendered[DeliveryArtifactKind.RUNBOOK] == render_runbook(report)
		assert set(rendered) <= set(DELIVERY_ARTIFACT_PATHS), (
			"every kind rendered must be one the writer knows a path for"
		)


def _a_report_without_checks() -> DeliveryReport:
	"""A report whose ``checks`` is empty, built by bypassing the type's own validator.

	``model_construct`` rather than the constructor because the validator is what
	refuses the shape, and the point of this test is what happens *after* a report of
	that shape reaches the renderer -- a report from a log written by a build that did
	not check, which is the case a rendering function may not assume away.
	"""
	return DeliveryReport.model_construct(
		id="01a00000-0000-7000-8000-000000000000",
		checks=(),
		artifacts=(),
		chain=(),
		verified=(),
		unverified=(),
		unvalidated_assumptions=(),
	)


class TestTheGateCostAndEnvelopeReachTheDocument:
	async def test_a_recorded_gate_cost_is_in_the_document(
		self, home: Path, tmp_path: Path
	) -> None:
		"""FR-160 puts the pair in the delivery report (§20.2); the document is what a
		human reads, so a number that reached the type and not the file reached nobody."""
		# NFR-025 makes the envelope configuration, so the fixture names one: an
		# unconfigured service reports no actuals at all, which is a different claim.
		service = synthetic_service(home, tmp_path, "complete", envelope=DeliveryEnvelope())
		await service.probe_harness(None)
		_, contract_id = await elicitation_to_contract(service, commands="true")
		await specify_and_approve(service, contract_id)
		await decompose_and_approve(service, contract_id)
		plan = await service.compile_plan(contract_id)
		await service.advance_phase(Phase.ELICIT, PhaseStatus.COMPLETE)
		await service.advance_phase(Phase.RESEARCH, PhaseStatus.COMPLETE)
		await service.advance_phase(Phase.SPECIFY, PhaseStatus.AWAITING_GATE)
		await service.approve_gate(Phase.SPECIFY, by="operator")
		await service.record_gate_cost(
			PhaseGate.SPECIFICATION, human_minutes=90.0, rework_fraction=0.25, by="operator"
		)

		report = await service.render_delivery(plan.id, root=a_written_root(tmp_path))
		document = render_delivery_document(report)

		assert "90 human-minute(s)" in document
		assert "25% of the slice returned to the producer" in document
		assert "mean rework fraction 0.250" in document

	async def test_an_unmeasured_gate_cost_reads_unmeasured_not_free(
		self, home: Path, tmp_path: Path
	) -> None:
		_, report = await a_rendered_report(home, tmp_path)
		assert report.gate_costs == ()

		document = render_delivery_document(report)

		assert "unmeasured rather than zero" in document

	async def test_the_human_minutes_dimension_is_the_one_that_moved(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The dimension FR-160 unblocked is measured at P8 and still unmeasured at P3,
		so the document must report it rather than list it among the unmeasured."""
		_, report = await a_rendered_report(home, tmp_path)
		assert report.envelope_actuals is not None

		minutes = next(
			m
			for m in report.envelope_actuals.measurements
			if m.dimension is EnvelopeDimension.HUMAN_MINUTES
		)
		assert minutes.actual is None
		assert "sofact gate --cost" in minutes.detail
