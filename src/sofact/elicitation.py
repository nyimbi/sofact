"""P0 — elicitation: the questions, and the deterministic gate that ends it.

The gate is deliberately *not* the model's judgement. Each dimension has a
machine-checkable floor — a length, and where the dimension's own question demands it a
content floor: the oracle dimension must name an actual checking mechanism, and the
scale dimension must name a quantity. An answer that clears the floor is not
thereby *true*; it is only specific enough to be worked with. That distinction is the
whole design, and it is why the model here is an advisor and not a judge
(ADR-0007, ADR-0008).

The floors are conservative and transparent. They are a filter against non-answers,
not a measure of quality, and nothing downstream is permitted to treat a passed floor
as evidence that a requirement is met.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sofact._uuid7 import uuid7str
from sofact.views import (
	ClauseKind,
	ClauseStem,
	DimensionStatus,
	ElicitationAnswer,
	ElicitationDimension,
	Readiness,
	SpecificationDraft,
	now,
)

__all__ = [
	"DIMENSIONS",
	"MIN_STEM_CHARS",
	"advise_prompt",
	"assess",
	"draft_stems",
	"next_open",
	"propose_prompt",
	"spec_for",
]

MIN_STEM_CHARS = 12
"""A clause stem shorter than this is a fragment, not a requirement."""

_QUANTITY_MARKERS: tuple[str, ...] = (
	"dozen",
	"tens",
	"hundred",
	"hundreds",
	"thousand",
	"thousands",
	"million",
	"millions",
	"billion",
	"billions",
)
"""Magnitude words that name a quantity without a numeral.

Bare ``"ten"`` is deliberately absent: it is a substring of *often*, *written* and
*threaten*, so matching it would pass an answer that names no quantity at all — and a
floor that can be cleared by an unrelated word is the floor failing open, which is the
one failure a gate may not have.
"""


@dataclass(frozen=True, slots=True)
class DimensionSpec:
	"""One elicitation dimension: how to ask it, and what counts as an answer."""

	dimension: ElicitationDimension
	question: str
	rationale: str
	min_chars: int
	required_markers: tuple[str, ...] = field(default=())
	requires_quantity: bool = False
	"""Whether a resolving answer must name a quantity (FR-064).

	A second *content* floor beside :attr:`required_markers`, and separate from it on
	purpose: a marker list asks "does this name a checking mechanism", which is the
	oracle dimension's question and no other's. Scale's question is "how many", and an
	answer of "a lot of users" clears any length while naming nothing — which is the
	clarifying pleasantry FR-064 says elicitation must not accept.
	"""


DIMENSIONS: tuple[DimensionSpec, ...] = (
	DimensionSpec(
		dimension=ElicitationDimension.OUTCOME,
		question="What observable state change tells you this worked?",
		rationale=(
			"Without an observable outcome there is nothing to test, so there can be no "
			"oracle and no autonomy above L0."
		),
		min_chars=20,
	),
	DimensionSpec(
		dimension=ElicitationDimension.CONSUMER,
		question="Who or what consumes this, and how do they invoke it?",
		rationale=(
			"The consumer fixes the interface and therefore the shape of every test. An "
			"unstated consumer is a requirement that will be invented later, by the machine."
		),
		min_chars=15,
	),
	DimensionSpec(
		dimension=ElicitationDimension.BOUNDARY,
		question="What is explicitly out of scope?",
		rationale=(
			"Decomposition is unbounded without a boundary, and unbounded decomposition is "
			"how a small request becomes an unverifiable platform."
		),
		min_chars=10,
	),
	DimensionSpec(
		dimension=ElicitationDimension.ORACLE,
		question="How would a machine check the outcome, without asking you?",
		rationale=(
			"This is the load-bearing question. An answer must name a real checking "
			"mechanism — a test, a property, a query, a digest — because a description of "
			"confidence is not an oracle."
		),
		min_chars=40,
		required_markers=(
			"test",
			"assert",
			"property",
			"invariant",
			"exit code",
			"hash",
			"digest",
			"checksum",
			"schema",
			"query",
			"row",
			"table",
			"count",
			"diff",
			"file",
			"benchmark",
			"latency",
			"http",
			"status",
			"response",
			"metric",
			"log",
			"lint",
			"type check",
			"reproduce",
			"compare",
			"validate",
		),
	),
	DimensionSpec(
		dimension=ElicitationDimension.SCALE,
		question="How many users, entities or records? What is the growth expectation?",
		rationale=(
			"R19: unbounded goals produce unbounded platforms, and §1.3's envelope cannot "
			"bound a goal whose size was never stated. A scale with no quantity is the "
			"ambiguity this dimension exists to remove."
		),
		min_chars=15,
		requires_quantity=True,
	),
	DimensionSpec(
		dimension=ElicitationDimension.CONSTRAINT,
		question="What regulatory, data-residency, latency, budget or integration constraints apply?",
		rationale=(
			"Constraints are the difference between a design and a preference. Recording "
			"them up front prevents the builder from silently choosing for you."
		),
		min_chars=10,
	),
	DimensionSpec(
		dimension=ElicitationDimension.NON_NEGOTIABLES,
		question="What must not change or be touched?",
		rationale=(
			"What must not break is a different question from what the stack is, and folding "
			"it into the constraints question is how it went unasked. It bounds the blast "
			"radius of every other answer."
		),
		min_chars=15,
	),
	DimensionSpec(
		dimension=ElicitationDimension.FAILURE,
		question="What must never happen — what is the worst outcome you would not accept?",
		rationale=(
			"Negative requirements bound the blast radius. They are also the clause class "
			"most often omitted, which is why they have their own dimension."
		),
		min_chars=15,
	),
)

_BY_DIMENSION = {spec.dimension: spec for spec in DIMENSIONS}

REFUSALS: frozenset[str] = frozenset(
	{
		"n/a",
		"na",
		"none",
		"unknown",
		"tbd",
		"todo",
		"?",
		"-",
		"--",
		"idk",
		"not sure",
		"no idea",
		"later",
		"skip",
	},
)
"""Exact-match non-answers. Matched exactly rather than by substring so that a real
answer containing the word "none" is not discarded."""


def spec_for(dimension: ElicitationDimension) -> DimensionSpec:
	"""The spec for one dimension."""
	assert dimension in _BY_DIMENSION, f"no spec for {dimension}"
	return _BY_DIMENSION[dimension]


def _names_a_quantity(text: str) -> bool:
	"""Whether ``text`` names a quantity, by a numeral or a magnitude word.

	Deliberately loose about *what* the quantity counts and strict about there being
	one: "a few hundred users" and "200 records" both pass, and "a lot of users" fails.
	Reading a magnitude out of prose is not reading a *number* — nothing here parses a
	bound, and :data:`~sofact.views.DimensionBound` is never built from an answer, which
	would be the factory inventing a figure the operator never gave (FR-065).
	"""
	lowered = text.lower()
	return any(char.isdigit() for char in text) or any(
		marker in lowered for marker in _QUANTITY_MARKERS
	)


def _reasons(spec: DimensionSpec, text: str) -> tuple[str, ...]:
	"""Why ``text`` does not resolve ``spec``, or an empty tuple if it does."""
	stripped = text.strip()
	if stripped.lower() in REFUSALS:
		return ("this is a non-answer; the dimension cannot be resolved by declining it",)
	reasons: list[str] = []
	if len(stripped) < spec.min_chars:
		reasons.append(f"needs at least {spec.min_chars} characters, got {len(stripped)}")
	if spec.required_markers:
		lowered = stripped.lower()
		if not any(marker in lowered for marker in spec.required_markers):
			preview = ", ".join(spec.required_markers[:6])
			reasons.append(
				"does not name a checking mechanism; expected something like one of: "
				f"{preview}, … (a statement of confidence is not an oracle)",
			)
	if spec.requires_quantity and not _names_a_quantity(stripped):
		reasons.append(
			'names no quantity; a scale of "a lot" or "as many as needed" is the '
			"ambiguity this dimension exists to remove, and the envelope cannot bound a "
			"goal whose size was never stated (FR-064, R19)",
		)
	return tuple(reasons)


def assess(
	goal_id: str,
	answers: tuple[ElicitationAnswer, ...],
	*,
	attested: frozenset[str] = frozenset(),
) -> Readiness:
	"""Resolve every dimension against the answers recorded for ``goal_id``.

	Later answers supersede earlier ones for the same dimension, so re-answering is
	how an operator corrects a thin reply — and it is also how they take a model's
	proposal over: their own answer supersedes it and needs no attestation, because
	the superseding answer is theirs.

	**A model-proposed answer that nobody attested is reported as open** (FR-173). It may
	clear every floor in :data:`DIMENSIONS` and still not resolve the dimension, because
	the floors measure specificity and this measures authorship. A machine can write
	something specific; it cannot have wanted anything. Without this, a proposal that
	clears ``MIN_STEM_CHARS`` and ORACLE's markers would pass P0 and become a requirement
	in a specification a human then approved — the "written and never read" defect with a
	signature on it, which is the one failure this phase exists to prevent.

	``attested`` is the set of answer ids a person has confirmed. Defaulting to empty is
	deliberate: a caller that forgets it gets the *refusing* answer, not the permissive
	one, so a forgotten argument makes a gate stricter rather than open.
	"""
	latest: dict[ElicitationDimension, ElicitationAnswer] = {}
	for answer in answers:
		if answer.goal_id == goal_id:
			latest[answer.dimension] = answer

	statuses: list[DimensionStatus] = []
	for spec in DIMENSIONS:
		answer = latest.get(spec.dimension)
		if answer is None:
			statuses.append(
				DimensionStatus(
					dimension=spec.dimension,
					resolved=False,
					reasons=("not answered yet",),
				),
			)
			continue
		if answer.is_model_proposed and answer.id not in attested:
			statuses.append(
				DimensionStatus(
					dimension=spec.dimension,
					resolved=False,
					reasons=(
						f"proposed by {answer.answered_by!r} and attested by nobody; a person "
						f"must confirm it or answer the dimension themselves (FR-173): "
						f"sofact attest {answer.id} --by <you>",
					),
				),
			)
			continue
		reasons = _reasons(spec, answer.text)
		statuses.append(
			DimensionStatus(dimension=spec.dimension, resolved=not reasons, reasons=reasons)
		)

	readiness = Readiness(goal_id=goal_id, statuses=tuple(statuses))
	assert len(readiness.statuses) == len(DIMENSIONS), "readiness must cover every dimension"
	return readiness


def next_open(readiness: Readiness) -> ElicitationDimension | None:
	"""The next unanswered dimension in declaration order, or ``None`` if ready."""
	open_dimensions = readiness.open_dimensions
	return open_dimensions[0] if open_dimensions else None


_STEM_SPLIT = re.compile(r"(?:^|\n)\s*(?:[-*•]|\d+[.)])?\s*|\s*;\s*|\s+\.\s+")
"""Split an answer into candidate clauses on newlines, bullets, semicolons, and
sentence boundaries. Deliberately crude: over-splitting produces a stem that fails
review, while under-splitting silently merges two requirements into one."""


def _split_stems(text: str) -> list[str]:
	candidates = (part.strip(" \t.;,") for part in _STEM_SPLIT.split(text))
	return [c for c in candidates if len(c) >= MIN_STEM_CHARS]


_STEM_KIND: dict[ElicitationDimension, ClauseKind] = {
	ElicitationDimension.OUTCOME: ClauseKind.POSITIVE,
	ElicitationDimension.CONSUMER: ClauseKind.POSITIVE,
	ElicitationDimension.CONSTRAINT: ClauseKind.POSITIVE,
	ElicitationDimension.SCALE: ClauseKind.POSITIVE,
	ElicitationDimension.BOUNDARY: ClauseKind.NEGATIVE,
	ElicitationDimension.NON_NEGOTIABLES: ClauseKind.NEGATIVE,
	ElicitationDimension.FAILURE: ClauseKind.NEGATIVE,
}
"""ORACLE is absent on purpose: how a requirement will be checked is metadata that
drives oracle assignment, not a requirement in its own right.

SCALE is *positive* rather than a bound: the operator's stated size is an obligation the
system must meet ("handle 5,000 records"), and a negative reading of the same words would
assert only that some unspecified limit is not exceeded. NON_NEGOTIABLES is negative for
BOUNDARY's and FAILURE's reason — what must not change is a bound on the blast radius.
"""


def draft_stems(
	goal_id: str,
	answers: tuple[ElicitationAnswer, ...],
	*,
	attested: frozenset[str] = frozenset(),
) -> SpecificationDraft:
	"""Turn resolved answers into a draft of unoracled clause stems.

	Statements are kept **verbatim**. No ``MUST`` is prepended and no requirement is
	paraphrased: rewriting the operator's words here would be the machine inventing
	requirements, and the polarity that a modal verb would supply is already carried
	by :class:`~sofact.views.ClauseKind`.

	Raises if the answers are not yet ready, so a draft can never be built from a
	half-interrogated goal — and ``attested`` is threaded through rather than dropped,
	because a draft built from a proposal nobody read is exactly the artefact FR-173
	refuses, and reaching one by way of a stale readiness reading would defeat it.
	"""
	readiness = assess(goal_id, answers, attested=attested)
	if not readiness.is_ready:
		waiting = ", ".join(d.value for d in readiness.open_dimensions)
		raise ValueError(f"cannot draft from an unresolved elicitation; still open: {waiting}")

	latest: dict[ElicitationDimension, ElicitationAnswer] = {}
	for answer in answers:
		if answer.goal_id == goal_id:
			latest[answer.dimension] = answer

	stems: list[ClauseStem] = []
	for spec in DIMENSIONS:
		kind = _STEM_KIND.get(spec.dimension)
		if kind is None:
			continue
		for statement in _split_stems(latest[spec.dimension].text):
			stems.append(
				ClauseStem(
					id=uuid7str(),
					statement=statement,
					kind=kind,
					derived_from=spec.dimension,
				),
			)

	if not stems:  # pragma: no cover - reachable only if every answer is one fragment
		raise ValueError("answers resolved but produced no clause stems at all")

	# The answers this draft was built from, recorded so "is this draft current" is a
	# question the log answers (FR-068). ``latest`` holds one answer per dimension and
	# its iteration order is the dimension order, so the tuple is deterministic — two
	# drafts of the same answers name the same ids in the same order.
	used = tuple(latest[spec.dimension].id for spec in DIMENSIONS if spec.dimension in latest)
	draft = SpecificationDraft(
		id=uuid7str(),
		goal_id=goal_id,
		created_at=now(),
		stems=tuple(stems),
		answer_ids=used,
	)
	assert draft.stems, "draft must carry at least one stem"
	return draft


_SYSTEM = (
	"You are an advisor inside SoFact, a tool that turns a stated goal into a "
	"falsifiable specification. Your only job is to find the single most important "
	"thing missing or ambiguous in one answer. You do not decide anything and your "
	"output is not a verdict.\n\n"
	"Reply with one short paragraph, at most 60 words. Ask one specific follow-up "
	"question. Do not restate the answer. Do not praise it. Do not offer a checklist. "
	"If the answer is already specific enough to be checked by a machine, reply with "
	"exactly: ADEQUATE"
)


def advise_prompt(spec: DimensionSpec, answer: str) -> tuple[str, str]:
	"""Build the ``(system, user)`` pair used to solicit an advisory follow-up."""
	assert answer.strip(), "cannot advise on an empty answer"
	user = (
		f"Dimension: {spec.dimension.value}\n"
		f"Why it matters: {spec.rationale}\n"
		f"The question asked was: {spec.question}\n\n"
		f"The operator answered:\n{answer}\n\n"
		"What is the most important thing this answer leaves unverifiable?"
	)
	return _SYSTEM, user


_PROPOSE_SYSTEM = (
	"You are drafting answers inside SoFact, a tool that turns a stated goal into a "
	"falsifiable specification. A person has described what they want and has not yet "
	"answered every question the specification needs. Your draft is a **proposal**: it "
	"will be shown to them, it will be recorded as machine-written, and no dimension it "
	"fills counts as answered until they read it and confirm it.\n\n"
	"Write the answer that the goal statement actually supports, in the terms a machine "
	"could check. Name concrete observable states, real consumers, and bounds you can "
	"justify from what they said. Where the statement does not support a specific answer, "
	"say what is missing rather than inventing a plausible one — an invented specific is "
	"worse than an admitted gap, because it will read as the operator's own intent.\n\n"
	"Reply with the answer alone. No preamble, no headings, no list of options, no "
	"restatement of the question."
)


def propose_prompt(spec: DimensionSpec, goal_statement: str) -> tuple[str, str]:
	"""Build the ``(system, user)`` pair used to draft a proposal for one dimension.

	The goal statement is included and nothing else is: a proposal made without it would
	be a generic answer to a generic question, and the point of drafting is that the
	operator gets back something about *their* system. Nothing downstream treats the
	output as an answer until a person attests it (FR-173), so the prompt's job is to be
	useful rather than to be safe — the safety is in the attestation, not in the wording.
	"""
	assert goal_statement.strip(), "cannot propose an answer to an unstated goal"
	user = (
		f"The person's goal, in their own words:\n{goal_statement}\n\n"
		f"Dimension: {spec.dimension.value}\n"
		f"Why it matters: {spec.rationale}\n"
		f"The question to answer: {spec.question}\n\n"
		"Write the answer, in their terms, as concretely as the statement allows."
	)
	return _PROPOSE_SYSTEM, user
