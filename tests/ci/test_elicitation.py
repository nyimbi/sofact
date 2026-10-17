"""P0 — the deterministic floor under the interrogation.

Everything here holds with the model unreachable, because the gate is not the
model's judgement (ADR-0007). What the tests pin is narrow and deliberate: what
counts as an answer, which dimension is asked next, and what a draft is allowed to
say. A floor is a filter against non-answers, not a measure of quality, and the
tests are written to keep that distinction intact — none of them asserts that a
passed floor means a requirement is good.

Two claims carry more weight than the rest. A refusal is matched *exactly*, so an
answer that merely contains the word "none" survives; and a draft keeps the
operator's words verbatim, because a machine that rewrites a requirement has
invented one.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

import pytest
from conftest import GOOD_ANSWERS

from sofact._uuid7 import uuid7str
from sofact.elicitation import (
	DIMENSIONS,
	MIN_STEM_CHARS,
	REFUSALS,
	advise_prompt,
	assess,
	draft_stems,
	next_open,
	spec_for,
)
from sofact.views import (
	MODEL_ANSWER_PREFIX,
	ClauseKind,
	ElicitationAnswer,
	ElicitationAttestation,
	ElicitationDimension,
	Readiness,
	SpecificationDraft,
	now,
)

DECLARATION_ORDER = tuple(spec.dimension for spec in DIMENSIONS)


def answered(dimension: ElicitationDimension, text: str, *, goal_id: str) -> ElicitationAnswer:
	"""One recorded answer. Ids are real UUID7s because the view validates them."""
	return ElicitationAnswer(
		id=uuid7str(),
		goal_id=goal_id,
		dimension=dimension,
		text=text,
		answered_by="operator",
		at=now(),
	)


def all_answered(
	goal_id: str,
	overrides: Mapping[ElicitationDimension, str] | None = None,
) -> tuple[ElicitationAnswer, ...]:
	"""Every dimension answered, with ``overrides`` replacing the good answers."""
	texts = {**GOOD_ANSWERS, **(overrides or {})}
	return tuple(
		answered(spec.dimension, texts[spec.dimension], goal_id=goal_id) for spec in DIMENSIONS
	)


# --------------------------------------------------------------------------- #
# the questions themselves
# --------------------------------------------------------------------------- #


def test_the_question_order_is_the_declaration_order() -> None:
	"""Order is the contract: ``next_open`` asks, and a test asserts, in this order."""
	assert tuple(ElicitationDimension) == DECLARATION_ORDER
	assert len(DIMENSIONS) == 8


def test_every_dimension_asks_a_question_and_states_a_floor() -> None:
	for spec in DIMENSIONS:
		assert spec.question.endswith("?"), f"{spec.dimension.value} is not phrased as a question"
		assert spec.rationale.strip(), f"{spec.dimension.value} gives no reason for asking"
		assert spec.min_chars > 0, f"{spec.dimension.value} has no floor at all"


def test_spec_for_returns_the_declared_spec() -> None:
	for spec in DIMENSIONS:
		assert spec_for(spec.dimension) is spec


def test_only_the_oracle_dimension_demands_a_checking_mechanism() -> None:
	"""A marker list is only meaningful for the dimension that asks for an oracle."""
	required = {spec.dimension for spec in DIMENSIONS if spec.required_markers}
	assert required == {ElicitationDimension.ORACLE}


def test_only_the_scale_dimension_demands_a_quantity() -> None:
	"""The other content floor, pinned to its dimension for the same reason.

	``required_markers`` is pinned above and ``requires_quantity`` is pinned here, because
	each is a floor that a later refactor can drop silently: an unpinned field is a rule
	with no reader, and a dimension that acquires one by accident is a floor nobody chose.
	"""
	required = {spec.dimension for spec in DIMENSIONS if spec.requires_quantity}
	assert required == {ElicitationDimension.SCALE}


def test_the_spec_rows_the_enum_dropped_are_now_present() -> None:
	"""FR-064's table lists *Scale* and *Non-negotiables*; both are dimensions again.

	They were absent with no record until ADR-0077, which is the failure a list not bound
	to its authority produces. This test names them so a later edit that removes one has
	to delete a test that says why it exists.
	"""
	assert ElicitationDimension.SCALE in DECLARATION_ORDER
	assert ElicitationDimension.NON_NEGOTIABLES in DECLARATION_ORDER


def test_the_constraints_question_no_longer_asks_about_non_negotiables() -> None:
	"""The absorbed row, asserted on the text: a rewording reverts silently otherwise.

	CONSTRAINT used to read "What are the non-negotiables — platform, stack, …?", so the
	spec's separate *Non-negotiables* row was never asked and the gap read as a count
	mismatch rather than a question that had swallowed another's.
	"""
	constraint = spec_for(ElicitationDimension.CONSTRAINT).question
	non_negotiables = spec_for(ElicitationDimension.NON_NEGOTIABLES).question

	assert "non-negotiable" not in constraint.lower()
	assert "must not change" in non_negotiables.lower(), "the spec's Non-negotiables row"
	assert "regulatory" in constraint.lower(), "the spec's Constraints row, restored"
	assert constraint != non_negotiables, "two dimensions asking one question"


def test_the_oracle_markers_name_real_mechanisms() -> None:
	"""The load-bearing dimension must not be satisfiable by prose alone."""
	markers = set(spec_for(ElicitationDimension.ORACLE).required_markers)
	assert {"test", "assert", "property", "exit code", "schema", "http"} <= markers


# --------------------------------------------------------------------------- #
# the gate
# --------------------------------------------------------------------------- #


def test_an_unanswered_dimension_is_reported_as_not_answered() -> None:
	goal_id = uuid7str()
	readiness = assess(goal_id, ())

	assert not readiness.is_ready
	assert len(readiness.statuses) == len(DIMENSIONS)
	for status in readiness.statuses:
		assert not status.resolved
		assert status.reasons == ("not answered yet",)


@pytest.mark.parametrize("refusal", sorted(REFUSALS))
def test_every_declared_refusal_is_refused(refusal: str) -> None:
	goal_id = uuid7str()
	readiness = assess(
		goal_id, (answered(ElicitationDimension.BOUNDARY, refusal, goal_id=goal_id),)
	)
	status = readiness.statuses[DECLARATION_ORDER.index(ElicitationDimension.BOUNDARY)]

	assert not status.resolved
	assert "non-answer" in status.reasons[0]


def test_a_refusal_is_matched_case_insensitively_and_exactly() -> None:
	goal_id = uuid7str()
	readiness = assess(goal_id, (answered(ElicitationDimension.BOUNDARY, "N/A", goal_id=goal_id),))
	assert not readiness.statuses[2].resolved


def test_a_real_answer_that_contains_a_refusal_word_survives() -> None:
	"""Exact matching is why "none" inside a sentence is not mistaken for "none"."""
	goal_id = uuid7str()
	text = "This has none of the things I asked for and is long enough to count"
	readiness = assess(goal_id, (answered(ElicitationDimension.OUTCOME, text, goal_id=goal_id),))

	assert readiness.statuses[0].resolved
	assert readiness.statuses[0].reasons == ()


def test_a_thin_answer_reports_the_floor_it_missed() -> None:
	goal_id = uuid7str()
	readiness = assess(
		goal_id, (answered(ElicitationDimension.OUTCOME, "It works", goal_id=goal_id),)
	)
	reasons = readiness.statuses[0].reasons

	assert not readiness.statuses[0].resolved
	assert "at least 20 characters" in reasons[0]
	assert "got 8" in reasons[0]


def test_a_scale_with_no_quantity_does_not_resolve_and_one_with_a_quantity_does() -> None:
	"""FR-064's *adversarial* clause, on the dimension that had no floor for it.

	Both directions in one test on purpose. Asserting only the refusal would pass for a
	floor that refuses everything; asserting only the pass would pass for no floor at all.
	The inputs are literals rather than built from the bound, because a text computed from
	the constant it tests moves with that constant and proves nothing.
	"""
	goal_id = uuid7str()
	vague = "A lot of users, and as many as needed later on."
	assert len(vague) > spec_for(ElicitationDimension.SCALE).min_chars, (
		"the vague answer must clear the length floor, or this test passes for the wrong "
		"reason and the quantity rule goes unexercised"
	)

	status = assess(
		goal_id, (answered(ElicitationDimension.SCALE, vague, goal_id=goal_id),)
	).statuses[DECLARATION_ORDER.index(ElicitationDimension.SCALE)]
	assert not status.resolved
	assert "names no quantity" in status.reasons[0]

	for stated in ("About 200 users at launch.", "Roughly five thousand records."):
		resolved = assess(
			goal_id, (answered(ElicitationDimension.SCALE, stated, goal_id=goal_id),)
		).statuses[DECLARATION_ORDER.index(ElicitationDimension.SCALE)]
		assert resolved.resolved, f"{stated!r} names a quantity and must resolve"


def test_confidence_is_not_an_oracle() -> None:
	"""The distinction the whole design rests on, stated as an assertion."""
	goal_id = uuid7str()
	prose = "I will know it works because the operator will tell me it feels right and reliable."
	assert len(prose) > spec_for(ElicitationDimension.ORACLE).min_chars

	status = assess(
		goal_id, (answered(ElicitationDimension.ORACLE, prose, goal_id=goal_id),)
	).statuses[3]
	assert not status.resolved
	assert "does not name a checking mechanism" in status.reasons[0]
	assert "confidence is not an oracle" in status.reasons[0]

	# The same statement, once it names a mechanism, clears the floor.
	named = f"{prose} A pytest test asserts it."
	assert (
		assess(
			goal_id,
			(answered(ElicitationDimension.ORACLE, named, goal_id=goal_id),),
		)
		.statuses[3]
		.resolved
	)


def test_a_later_answer_supersedes_an_earlier_one_for_the_same_dimension() -> None:
	"""Re-answering is how an operator corrects a thin reply, so it must not double-count."""
	goal_id = uuid7str()
	readiness = assess(
		goal_id,
		(
			answered(ElicitationDimension.OUTCOME, "It works", goal_id=goal_id),
			answered(
				ElicitationDimension.OUTCOME,
				GOOD_ANSWERS[ElicitationDimension.OUTCOME],
				goal_id=goal_id,
			),
		),
	)

	assert readiness.statuses[0].resolved
	assert readiness.progress == (1, len(DIMENSIONS))


def test_answers_recorded_for_another_goal_do_not_resolve_this_one() -> None:
	goal_id, other = uuid7str(), uuid7str()
	readiness = assess(goal_id, all_answered(other))

	assert not readiness.is_ready
	assert readiness.progress == (0, len(DIMENSIONS))


def test_readiness_covers_every_dimension_in_declaration_order() -> None:
	readiness = assess(uuid7str(), ())
	assert tuple(status.dimension for status in readiness.statuses) == DECLARATION_ORDER


def test_progress_counts_resolved_dimensions_and_readiness_flips_at_the_end() -> None:
	goal_id = uuid7str()
	assert assess(goal_id, ()).progress == (0, len(DIMENSIONS))

	answers: list[ElicitationAnswer] = []
	for index, spec in enumerate(DIMENSIONS, start=1):
		answers.append(answered(spec.dimension, GOOD_ANSWERS[spec.dimension], goal_id=goal_id))
		readiness = assess(goal_id, tuple(answers))
		assert readiness.progress == (index, len(DIMENSIONS))
		assert readiness.is_ready is (index == len(DIMENSIONS))


def test_next_open_returns_the_first_unresolved_dimension() -> None:
	goal_id = uuid7str()
	assert next_open(assess(goal_id, ())) is ElicitationDimension.OUTCOME

	answers = [
		answered(
			ElicitationDimension.OUTCOME,
			GOOD_ANSWERS[ElicitationDimension.OUTCOME],
			goal_id=goal_id,
		)
	]
	assert next_open(assess(goal_id, tuple(answers))) is ElicitationDimension.CONSUMER

	assert next_open(assess(goal_id, all_answered(goal_id))) is None


# --------------------------------------------------------------------------- #
# a machine's answer is not a person's (FR-173)
# --------------------------------------------------------------------------- #


def a_proposal(
	dimension: ElicitationDimension,
	text: str,
	*,
	goal_id: str,
	by: str = f"{MODEL_ANSWER_PREFIX}qwen",
) -> ElicitationAnswer:
	"""One model-proposed answer, otherwise identical to :func:`answered`."""
	return ElicitationAnswer(
		id=uuid7str(),
		goal_id=goal_id,
		dimension=dimension,
		text=text,
		answered_by=by,
		at=now(),
	)


def proposed_everything(goal_id: str) -> tuple[ElicitationAnswer, ...]:
	"""Every dimension answered by a model, with text that clears every floor.

	The text is :data:`GOOD_ANSWERS` deliberately: these proposals are *adequate*. If
	they were thin, a test that reports them open would pass for the wrong reason —
	the floor would be doing the work, and the authorship rule would be untested.
	"""
	return tuple(
		a_proposal(spec.dimension, GOOD_ANSWERS[spec.dimension], goal_id=goal_id)
		for spec in DIMENSIONS
	)


def test_is_model_proposed_is_derived_from_answered_by() -> None:
	"""The reader ``answered_by`` did not have, and the whole of FR-173's mechanism."""
	goal_id = uuid7str()
	assert (
		answered(ElicitationDimension.OUTCOME, "x" * 40, goal_id=goal_id).is_model_proposed is False
	)
	assert (
		a_proposal(ElicitationDimension.OUTCOME, "x" * 40, goal_id=goal_id).is_model_proposed
		is True
	)


def test_a_model_proposed_answer_that_clears_every_floor_still_does_not_resolve() -> None:
	"""The defect FR-173 exists for, asserted on the floor it would otherwise clear.

	The same texts through :func:`all_answered` are ready; through a model they are not.
	That is the whole distinction — specificity is not authorship — and asserting both
	halves in one test is what stops the second from passing because the texts are thin.
	"""
	goal_id = uuid7str()
	proposals = proposed_everything(goal_id)
	assert assess(goal_id, proposals, attested=frozenset(a.id for a in proposals)).is_ready, (
		"the proposal texts must be adequate, or this test measures the floor"
	)
	assert assess(goal_id, all_answered(goal_id)).is_ready

	readiness = assess(goal_id, proposals)
	assert not readiness.is_ready
	assert readiness.open_dimensions == DECLARATION_ORDER


def test_the_open_reason_names_the_proposal_and_the_verb_that_resolves_it() -> None:
	"""A refusal that does not say what to do about it is a wall, not a gate."""
	goal_id = uuid7str()
	proposals = proposed_everything(goal_id)
	readiness = assess(goal_id, proposals)

	proposal_ids = {a.id for a in proposals}
	named = 0
	for status in readiness.statuses:
		assert not status.resolved
		reason = " ".join(status.reasons)
		assert "attested by nobody" in reason
		assert "sofact attest" in reason
		named += sum(1 for answer_id in proposal_ids if answer_id in reason)
	assert named == len(DIMENSIONS), "every open dimension must name its own proposal"


def test_attesting_every_proposal_resolves_the_interrogation() -> None:
	goal_id = uuid7str()
	proposals = proposed_everything(goal_id)
	attested = frozenset(a.id for a in proposals)

	assert assess(goal_id, proposals, attested=attested).is_ready


def test_attesting_one_proposal_resolves_one_dimension() -> None:
	"""Partial attestation is the ordinary case: a person reads what they have read."""
	goal_id = uuid7str()
	proposals = proposed_everything(goal_id)
	one = proposals[0]
	readiness = assess(goal_id, proposals, attested=frozenset({one.id}))

	resolved = {s.dimension for s in readiness.statuses if s.resolved}
	assert resolved == {one.dimension}


def test_an_operators_own_answer_supersedes_a_proposal_and_needs_no_attestation() -> None:
	"""The cheap way out, and it must stay cheap: answering is not a separate ritual."""
	goal_id = uuid7str()
	proposals = proposed_everything(goal_id)
	mine = answered(
		ElicitationDimension.ORACLE,
		GOOD_ANSWERS[ElicitationDimension.ORACLE],
		goal_id=goal_id,
	)
	readiness = assess(goal_id, (*proposals, mine))

	resolved = {s.dimension for s in readiness.statuses if s.resolved}
	assert resolved == {ElicitationDimension.ORACLE}


def test_a_draft_refuses_a_proposal_nobody_attested() -> None:
	"""``attested`` is threaded through rather than dropped, so a stale readiness
	reading cannot reach a draft built from a proposal."""
	goal_id = uuid7str()
	proposals = proposed_everything(goal_id)

	with pytest.raises(ValueError) as caught:
		draft_stems(goal_id, proposals)
	assert "still open:" in str(caught.value)

	attested = frozenset(a.id for a in proposals)
	assert draft_stems(goal_id, proposals, attested=attested).stems


def test_an_attestation_by_a_machine_is_refused() -> None:
	"""A model signing for a person restores exactly the state the record exists to
	make visible, so the view refuses it rather than the caller being trusted not to."""
	goal_id = uuid7str()
	answer = a_proposal(ElicitationDimension.OUTCOME, "x" * 40, goal_id=goal_id)

	with pytest.raises(ValueError) as caught:
		ElicitationAttestation(
			id=uuid7str(),
			answer_id=answer.id,
			attested_by=f"{MODEL_ANSWER_PREFIX}qwen",
			at=now(),
		)
	assert "an attestation by a machine is not an attestation" in str(caught.value)

	record = ElicitationAttestation(
		id=uuid7str(),
		answer_id=answer.id,
		attested_by="operator",
		at=now(),
	)
	assert record.answer_id == answer.id


# --------------------------------------------------------------------------- #
# the draft
# --------------------------------------------------------------------------- #


def test_a_draft_cannot_be_built_from_an_unresolved_interrogation() -> None:
	"""A half-interrogated goal must never become a specification."""
	with pytest.raises(ValueError) as caught:
		draft_stems(uuid7str(), ())

	message = str(caught.value)
	assert "still open:" in message
	for dimension in ElicitationDimension:
		assert dimension.value in message


def test_a_draft_keeps_the_operators_words_verbatim() -> None:
	"""No ``MUST`` is injected and nothing is paraphrased: the machine may not invent."""
	goal_id = uuid7str()
	draft = draft_stems(goal_id, all_answered(goal_id))

	assert isinstance(draft, SpecificationDraft)
	for stem in draft.stems:
		assert stem.statement in GOOD_ANSWERS[stem.derived_from]
		assert "MUST" not in stem.statement


def test_the_oracle_dimension_contributes_no_clause() -> None:
	"""How a requirement will be checked is metadata, not a requirement."""
	goal_id = uuid7str()
	draft = draft_stems(goal_id, all_answered(goal_id))

	assert not [stem for stem in draft.stems if stem.derived_from is ElicitationDimension.ORACLE]
	assert len(draft.stems) == len(DIMENSIONS) - 1


def test_polarity_follows_the_dimension() -> None:
	goal_id = uuid7str()
	draft = draft_stems(goal_id, all_answered(goal_id))
	kind_of = {stem.derived_from: stem.kind for stem in draft.stems}

	assert kind_of[ElicitationDimension.BOUNDARY] is ClauseKind.NEGATIVE
	assert kind_of[ElicitationDimension.FAILURE] is ClauseKind.NEGATIVE
	assert kind_of[ElicitationDimension.NON_NEGOTIABLES] is ClauseKind.NEGATIVE
	assert kind_of[ElicitationDimension.OUTCOME] is ClauseKind.POSITIVE
	assert kind_of[ElicitationDimension.CONSUMER] is ClauseKind.POSITIVE
	assert kind_of[ElicitationDimension.CONSTRAINT] is ClauseKind.POSITIVE
	assert kind_of[ElicitationDimension.SCALE] is ClauseKind.POSITIVE


def test_each_fixture_answer_yields_exactly_one_stem() -> None:
	"""``test_the_oracle_dimension_contributes_no_clause``'s arithmetic rests on this.

	That test asserts ``len(draft.stems) == len(DIMENSIONS) - 1``, which holds only while
	every non-oracle answer splits into exactly one stem — a fixture property, not a
	design one. An answer containing a ``;`` or a sentence boundary would split in two and
	break a test whose name says nothing about stems, so the property is asserted where it
	can be read.
	"""
	goal_id = uuid7str()
	draft = draft_stems(goal_id, all_answered(goal_id))
	counts = Counter(stem.derived_from for stem in draft.stems)

	for spec in DIMENSIONS:
		if spec.dimension is ElicitationDimension.ORACLE:
			continue
		assert counts[spec.dimension] == 1, (
			f"{spec.dimension.value} produced {counts[spec.dimension]} stems; the fixture "
			"answer must split into exactly one or the clause-count assertions move"
		)


def test_a_draft_splits_a_multi_statement_answer() -> None:
	"""Over-splitting produces a stem that fails review; under-splitting merges two
	requirements into one, so the split is deliberately crude and the floor filters it."""
	goal_id = uuid7str()
	bulleted = (
		"- the dashboard lists the reminder\n"
		"- the list refreshes within five seconds\n"
		"abcdefghijkl\n"
		"abcdefghijk"
	)
	draft = draft_stems(goal_id, all_answered(goal_id, {ElicitationDimension.OUTCOME: bulleted}))
	statements = [
		stem.statement for stem in draft.stems if stem.derived_from is ElicitationDimension.OUTCOME
	]

	assert statements == [
		"the dashboard lists the reminder",
		"the list refreshes within five seconds",
		"abcdefghijkl",
	]


def test_min_stem_chars_is_the_fragment_floor() -> None:
	"""The boundary case: a stem exactly at the floor survives, one below it does not."""
	assert MIN_STEM_CHARS == 12
	assert len("abcdefghijkl") == MIN_STEM_CHARS
	assert len("abcdefghijk") == MIN_STEM_CHARS - 1


def test_draft_ids_are_unique_uuid7_and_the_goal_is_preserved() -> None:
	goal_id = uuid7str()
	draft = draft_stems(goal_id, all_answered(goal_id))
	ids = [stem.id for stem in draft.stems]

	assert len(set(ids)) == len(ids)
	assert all(len(stem_id) == 36 and stem_id[14] == "7" for stem_id in ids)
	assert draft.goal_id == goal_id
	assert draft.created_at <= now()


# --------------------------------------------------------------------------- #
# the advisor's prompt (built deterministically; the model is not consulted)
# --------------------------------------------------------------------------- #


def test_the_advice_prompt_pins_the_dimension_and_the_answer() -> None:
	spec = spec_for(ElicitationDimension.ORACLE)
	text = GOOD_ANSWERS[ElicitationDimension.ORACLE]
	system, user = advise_prompt(spec, text)

	assert "ADEQUATE" in system
	assert "not a verdict" in system
	assert "at most 60 words" in system
	for fragment in (spec.dimension.value, spec.question, spec.rationale, text):
		assert fragment in user


def test_advising_on_an_empty_answer_is_refused() -> None:
	with pytest.raises(AssertionError):
		advise_prompt(spec_for(ElicitationDimension.OUTCOME), "   ")


def test_readiness_is_a_model_not_a_verdict_on_quality() -> None:
	"""Guards the framing: a resolved floor is specificity, not evidence."""
	goal_id = uuid7str()
	readiness = assess(goal_id, all_answered(goal_id))

	assert isinstance(readiness, Readiness)
	assert readiness.is_ready
	assert readiness.open_dimensions == ()
