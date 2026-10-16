"""FR-171 — the annotated specification, and the marker that must never quietly vanish.

The document is rendered at **P2**, because that is the artefact the first gate is a gate
*on*: a specification nobody can read is not gated by anything a human did. It is a
deterministic, model-free rendering of a record the ledger already holds, so two renders of
one input are byte-identical and a diff between two specifications is a diff between two
sets of facts.

Two properties carry the module, and both are *derived* rather than passed in:

- **An unattested requirement is visibly unattested.** The document cannot be rendered clean
  over a specification whose answer a machine wrote and nobody read — which is the reason
  :attr:`~sofact.views.RequirementAnnotation.unattested` is computed from the answers
  instead of accepted as a flag.
- **An unoracled requirement prints as unverified**, so the document cannot read as stronger
  than the contract it renders.

**The marker is defence in depth, and the tests say so rather than pretending otherwise.**
:func:`~sofact.elicitation.draft_stems` refuses an unattested proposal outright, so no ledger
can hold a machine's paragraph behind a contract and the marker cannot fire on a document
produced end to end. That refusal is asserted here as the *stronger* guarantee, and the
derivation is then tested where it lives — by calling
:func:`~sofact.specdoc.annotate` with an attested set that omits one answer, which is the
only way to reach an unattested requirement and is exactly the input a future relaxation of
the P0 refusal would produce.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from conftest import GOOD_ANSWERS
from synthetic import (
	a_model_for,
	elicitation_to_contract,
	specify_and_approve,
	synthetic_service,
)

from sofact.elicitation import DIMENSIONS
from sofact.llm import LlmClient
from sofact.service import FactoryService
from sofact.specdoc import (
	PRODUCT_SPEC_FILENAME,
	PRODUCT_SPEC_HEADINGS,
	annotate,
	render_product_specification,
)
from sofact.views import (
	UNATTESTED_MARKER,
	ElicitationDimension,
	ProductSpecificationDocument,
)

MODEL_PROPOSAL = (
	"Every scheduled reminder appears in the user dashboard within five seconds of its "
	"scheduled time, and the dashboard shows the reminder's state."
)


class StubModel(LlmClient):
	"""A model that returns one canned paragraph, so the *proposal* path is exercised.

	Subclassing :class:`~sofact.llm.LlmClient` rather than duck-typing it, so the stub cannot
	drift out of step with the interface the service actually calls.
	"""

	def __init__(self, text: str = MODEL_PROPOSAL) -> None:
		self.text = text

	async def complete(self, *, system: str, user: str) -> str:
		return self.text


def a_spec_service(home: Path, tmp_path: Path) -> FactoryService:
	"""A service with the synthetic harness registered, so a contract can be built."""
	return synthetic_service(home, tmp_path, "ok")


async def a_document(
	home: Path,
	tmp_path: Path,
	*,
	propose: ElicitationDimension | None = None,
) -> tuple[FactoryService, ProductSpecificationDocument]:
	"""P0 → P2, rendered. Returns ``(service, document)``.

	``propose`` names one dimension a machine drafts. The proposal is **attested** before the
	draft is built, because ``draft_stems`` refuses an unattested one — so this is the one
	reachable shape in which a machine's words are in a specification at all, and the shape
	the derivation below is measured against.
	"""
	service = a_spec_service(home, tmp_path)
	goal = await service.start("Ship a reminder dashboard.")
	if propose is None:
		for spec in DIMENSIONS:
			await service.answer(goal.id, spec.dimension, GOOD_ANSWERS[spec.dimension])
	else:
		for spec in DIMENSIONS:
			if spec.dimension is not propose:
				await service.answer(goal.id, spec.dimension, GOOD_ANSWERS[spec.dimension])
		service.llm = StubModel()
		proposals = await service.propose_answers(goal.id)
		service.llm = None
		assert [p.dimension for p in proposals] == [propose], (
			"propose_answers must draft exactly the dimensions the operator has not answered"
		)
		await service.attest(proposals[0].id, by="operator")
	await service.draft(goal.id)
	contract = await service.contract(goal.id)
	await specify_and_approve(service, contract.id)
	return service, await service.write_specification(contract.id)


async def an_unattested_document(
	home: Path,
	tmp_path: Path,
) -> tuple[FactoryService, ProductSpecificationDocument]:
	"""A rendered document whose machine answer was **not** attested.

	Reached by calling :func:`~sofact.specdoc.annotate` with an empty attested set, which is
	the derivation under test: the marker is a function of the attested set and the answer's
	authorship, and omitting an answer is the only way to reach an unattested requirement.
	The document is otherwise the real one — same contract, same draft, same answers — so the
	only thing that differs from a clean render is the set the caller passed.
	"""
	service, document = await a_document(home, tmp_path, propose=ElicitationDimension.OUTCOME)
	state = await service.state()
	contract = state.contract(document.contract_id)
	assert contract is not None
	specification = state.latest_specification(contract.id)
	assert specification is not None
	annotations = annotate(
		specification,
		contract,
		await service.latest_draft(contract.goal_id),
		state.answers_for(contract.goal_id),
		frozenset(),
	)
	return service, document.model_copy(update={"requirements": annotations})


# --------------------------------------------------------------------------- #
# the heading set
# --------------------------------------------------------------------------- #


def test_the_heading_constant_covers_the_sections_that_carry_a_qualification() -> None:
	"""The device :data:`~sofact.writing.DELIVERY_HEADINGS` uses: a section that went
	missing fails a test.

	A specification that read as complete while a qualification quietly dropped out of it is
	the one failure an annotated document cannot tolerate, because the whole point of the
	annotation is that the awkward facts travel with the requirements.
	"""
	assert "Unattested requirements" in PRODUCT_SPEC_HEADINGS
	assert "The competitive baseline" in PRODUCT_SPEC_HEADINGS
	assert "Requirements that exceed the best known" in PRODUCT_SPEC_HEADINGS


async def test_every_heading_appears_in_the_render(tmp_path: Path) -> None:
	_, document = await a_document(tmp_path / "home", tmp_path)
	rendered = render_product_specification(document)
	missing = [heading for heading in PRODUCT_SPEC_HEADINGS if f"## {heading}" not in rendered]
	assert not missing, f"the specification document lost section(s): {missing}"


# --------------------------------------------------------------------------- #
# the annotation
# --------------------------------------------------------------------------- #


async def test_every_requirement_carries_its_provenance(tmp_path: Path) -> None:
	"""This is what "annotated" means: a requirement is not a sentence the specification
	asserts, it is a sentence with a provenance.

	The elicitation half is the join that is *not derivable from the contract* — the draft's
	stems are not on the contract, so a renderer holding only the contract could not say which
	dimension a requirement came from.
	"""
	_, document = await a_document(tmp_path / "home", tmp_path)
	assert document.requirements
	for annotation in document.requirements:
		assert annotation.elicitation, annotation.requirement.statement
		assert annotation.oracle_class is not None
		assert annotation.oracle_rank is not None
		assert annotation.clause_ids


async def test_an_operator_answered_specification_renders_no_unattested_marker(
	tmp_path: Path,
) -> None:
	"""The negative half, and the one that makes the marker mean something.

	A document that printed the marker unconditionally would be as useless as one that never
	printed it, so this test is what stops the feature degenerating into decoration. It caught
	a real defect: ``AnswerProvenance.unattested`` was ``not attested``, and since an
	attestation row exists only for a model-proposed answer, that read as true of every
	operator answer ever written.
	"""
	_, document = await a_document(tmp_path / "home", tmp_path)
	assert document.unattested == ()
	assert UNATTESTED_MARKER not in render_product_specification(document)


async def test_an_attested_proposal_renders_no_marker(tmp_path: Path) -> None:
	"""The middle case, and the one that proves the marker follows the *reading* rather than
	the authorship: the same machine paragraph is clean once a person has confirmed it."""
	_, document = await a_document(
		tmp_path / "home", tmp_path, propose=ElicitationDimension.OUTCOME
	)
	assert any(
		a.answered_by.startswith("model:") for r in document.requirements for a in r.elicitation
	), "the fixture must put a machine's answer in the specification"
	assert document.unattested == ()
	assert UNATTESTED_MARKER not in render_product_specification(document)


async def test_a_proposal_nobody_attested_cannot_reach_a_draft(tmp_path: Path) -> None:
	"""The stronger guarantee, and the reason the marker is defence in depth.

	``draft_stems`` refuses outright, so there is no ledger in which a machine's paragraph
	sits behind a contract with nobody's reading recorded against it. That is what stops the
	"written and never read" defect at its source: the marker below is the second line, for
	the day the first is relaxed.
	"""
	service = a_spec_service(tmp_path / "home", tmp_path)
	goal = await service.start("Ship a reminder dashboard.")
	for spec in DIMENSIONS:
		if spec.dimension is not ElicitationDimension.OUTCOME:
			await service.answer(goal.id, spec.dimension, GOOD_ANSWERS[spec.dimension])
	service.llm = StubModel()
	await service.propose_answers(goal.id)
	service.llm = None
	with pytest.raises(ValueError, match="still open: outcome"):
		await service.draft(goal.id)


async def test_an_unattested_answer_makes_the_requirement_unattested(tmp_path: Path) -> None:
	"""The marker is derived, not passed in — so a document cannot be rendered clean over an
	answer nobody read.

	This is the property the plan's canary 1 inverts:
	:attr:`~sofact.views.ElicitationAnswer.is_model_proposed` returning ``False`` makes every
	machine paragraph an answer a person gave, and the marker disappears.
	"""
	_, document = await an_unattested_document(tmp_path / "home", tmp_path)
	assert document.unattested, "an answer nobody attested must make a requirement unattested"
	rendered = render_product_specification(document)
	assert UNATTESTED_MARKER in rendered
	for annotation in document.unattested:
		assert annotation.unattested_answers
		for provenance in annotation.unattested_answers:
			assert provenance.answered_by.startswith("model:")
			assert provenance.attested is False


async def test_the_unattested_section_names_the_answer_to_attest(tmp_path: Path) -> None:
	"""A marker that does not say what to do about it leaves the operator at a gate with no
	action, which is how a gate gets approved rather than satisfied."""
	_, document = await an_unattested_document(tmp_path / "home", tmp_path)
	rendered = render_product_specification(document)
	answer = document.unattested[0].unattested_answers[0]
	assert answer.answer_id in rendered
	assert "sofact attest" in rendered


async def test_an_approval_alone_does_not_attest_a_requirement(tmp_path: Path) -> None:
	"""A signature on a page is not a reading of the page.

	:attr:`ProductSpecificationDocument.attested` requires **both** an approval and no
	unattested requirement, and this asserts the second conjunct where it lives: the same
	document, approved by a person, still carries its unattested requirements. Asserted on
	the view rather than through :meth:`~sofact.service.FactoryService.approve_specification_document`
	because that method reads the document back from the ledger by id, so an in-memory
	revision is not the one it approves — and the property under test is the predicate, not
	the round-trip.
	"""
	_, document = await an_unattested_document(tmp_path / "home", tmp_path)
	assert document.unattested
	approved = document.model_copy(
		update={"approved_by": "operator", "approved_at": document.rendered_at}
	)
	assert approved.approved_by == "operator"
	assert approved.unattested
	assert not approved.attested


# --------------------------------------------------------------------------- #
# determinism and the artefacts
# --------------------------------------------------------------------------- #


async def test_two_renders_of_one_document_are_byte_identical(tmp_path: Path) -> None:
	"""ADR-0044's property: a diff between two specifications is a diff between facts, not
	between two paraphrases."""
	_, document = await a_document(tmp_path / "home", tmp_path)
	assert render_product_specification(document) == render_product_specification(document)


async def test_the_document_is_written_under_the_root(tmp_path: Path) -> None:
	"""The record is what the ledger holds; the file is a rendering of it. Writing the
	rendering rather than the record is what makes a diff of the file meaningful."""
	service = a_spec_service(tmp_path / "home", tmp_path)
	_, contract_id = await elicitation_to_contract(service)
	await specify_and_approve(service, contract_id)
	root = tmp_path / "delivery"
	await service.write_specification(contract_id, root=root)
	written = (root / PRODUCT_SPEC_FILENAME).read_text(encoding="utf-8")
	assert "## Requirements" in written


async def test_the_document_is_recorded_in_the_log(tmp_path: Path) -> None:
	service, document = await a_document(tmp_path / "home", tmp_path)
	current = await service.current_product_spec()
	assert current is not None
	assert current.id == document.id


async def test_rendering_without_a_gated_specification_is_refused(tmp_path: Path) -> None:
	"""The document is what P2's gate is a gate *on*, so it requires a specification that has
	been gated — and **not** one that has been approved.

	This test is the correction of its own predecessor, which asserted the opposite and was
	wrong in a way no other test could see. The old version required
	``require_approved_specification``, so the only way to render the annotated document was
	to pass the gate first: the operator was asked to approve a structure, and the prose that
	qualified it — the unattested markers, the oracle ranks, the open checks — could only be
	produced to someone who had already decided. ``spec-doc --approve`` was therefore
	unreachable, because the render it approves refused before the approval it needs.

	What is still refused is a contract with *no* specification: there is no checklist to
	render against, and a document over nothing is not a document.
	"""
	service = a_spec_service(tmp_path / "home", tmp_path)
	_, contract_id = await elicitation_to_contract(service)
	with pytest.raises(ValueError, match="P2 is a gate"):
		await service.write_specification(contract_id)

	contract = await service.contract_by_id(contract_id)
	proposal = await service.specify(contract_id, system_model=a_model_for(contract))
	document = await service.write_specification(contract_id)
	assert document.specification_id == proposal.id
	assert document.approved_by is None, "rendering is not approving (FR-080)"
	assert document.gate_open, (
		"the machine checks that were outstanding are carried on the document, so a reader "
		"can see what P2 is still asking for rather than inferring it from a blank line"
	)


async def test_the_document_carries_the_gate_the_reader_is_deciding_against(
	tmp_path: Path,
) -> None:
	"""``gate_failures`` is a reading of a moment, and the moment is before the decision.

	A document that looked the gate up afterwards would report the gate that was finally
	passed instead of the one the approver was shown, and the two differ by exactly the
	operator's own answers — which is the state the document exists to make visible.
	"""
	service = a_spec_service(tmp_path / "home", tmp_path)
	_, contract_id = await elicitation_to_contract(service)
	contract = await service.contract_by_id(contract_id)
	proposal = await service.specify(contract_id, system_model=a_model_for(contract))
	before = await service.write_specification(contract_id)
	assert {c.name for c in before.gate_failures} == {
		"assumptions_declared_and_falsifiable",
		"value_hypothesis_is_falsifiable",
	}, "the operator-supplied checks are the ones open before the operator has supplied them"

	assert proposal.id  # the incomplete proposal is the one that was rendered
	# The operator supplies what the open checks were asking for, and the gate is recomputed
	# against the new proposal — ``approve_specification`` re-runs the checks rather than
	# reading the row back, which is what makes the second render a reading of a *different*
	# gate rather than a re-reading of the same one.
	await specify_and_approve(service, contract_id)
	after = await service.write_specification(contract_id)
	assert after.gate_failures == (), "the gate it is rendered against is now clear"
	assert before.gate_failures != after.gate_failures, (
		"the same contract rendered at two moments must not report the same gate; if it "
		"does, the field is being derived at read time rather than recorded"
	)


async def test_an_unknown_contract_is_refused(tmp_path: Path) -> None:
	service = a_spec_service(tmp_path / "home", tmp_path)
	with pytest.raises(KeyError, match="no such contract"):
		await service.write_specification("01a14149-0000-7000-8000-000000000000")


async def test_an_unknown_document_cannot_be_approved(tmp_path: Path) -> None:
	service = a_spec_service(tmp_path / "home", tmp_path)
	with pytest.raises(KeyError, match="no such rendered specification"):
		await service.approve_specification_document(
			"01a14149-0000-7000-8000-000000000000", by="operator"
		)


async def test_the_oracle_rank_reaches_the_document(tmp_path: Path) -> None:
	"""An unoracled requirement prints as unverified, so the document cannot read as stronger
	than the contract it renders — and the rank is what a reader needs beside it to know how
	strong the check behind it is."""
	_, document = await a_document(tmp_path / "home", tmp_path)
	assert all(a.oracle_rank is not None for a in document.requirements)
	rendered = render_product_specification(document)
	assert "## Oracle strength" in rendered
	assert "rank 1" in rendered


# --------------------------------------------------------------------------- #
# the shape of the renderer itself
# --------------------------------------------------------------------------- #


def test_the_renderer_reads_no_clock() -> None:
	"""A pure function of the record: no clock, no ledger, no model.

	The reason it matters is the gate. A document whose text could change between the
	approval and the reading would make "the operator approved this" a claim about a file
	that no longer exists.
	"""
	source = inspect.getsource(render_product_specification)
	assert "now()" not in source
	assert "datetime" not in source


def test_the_headings_are_a_unique_sequence_of_strings() -> None:
	"""The constant is what the assertion above compares against, so it must be the shape the
	renderer writes. A duplicated heading would make one section's loss invisible."""
	assert isinstance(PRODUCT_SPEC_HEADINGS, tuple)
	assert all(heading.strip() for heading in PRODUCT_SPEC_HEADINGS)
	assert len(set(PRODUCT_SPEC_HEADINGS)) == len(PRODUCT_SPEC_HEADINGS)


def test_the_annotation_join_takes_the_draft_and_the_attested_set() -> None:
	"""Stated because it is the non-derivable step: a caller holding only the contract cannot
	produce an annotation, and a refactor that dropped the ``draft`` argument would silently
	empty every provenance while every other test still passed."""
	parameters = set(inspect.signature(annotate).parameters)
	assert {"draft", "attested", "answers", "verdicts"} <= parameters
