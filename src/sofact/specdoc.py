"""FR-171 — the product specification, rendered at P2 and annotated with its provenance.

The operator asked for a "detailed and annotated product specification document". Before this
module, the specification existed only as typed log records: `writing.py` renders two
documents, both at P8, and neither is the artefact P2 is a gate *on*. A gate on a
specification nobody can read is not a gate on anything a human did.

**The rendering is deterministic and model-free**, which is what makes it admissible, and it
is ADR-0044's argument one phase earlier: every input is a record the log already holds, so
two renders of one specification are byte-identical and a diff between two specifications is a
diff between two sets of facts. A specification written by a language model would be plausible
prose about a system nobody has agreed to build, and it would be indistinguishable from the
real thing at exactly the moment the operator was deciding whether to approve it.

**"Annotated" is the whole content of the feature.** A requirement is not a sentence this
document asserts; it is a sentence with a provenance — the elicitation answers it descends
from and *who gave them*, what research concluded about the clauses it traces to, the oracle
class and rank that will check it, the module that owns it, and any exceedance declared
against it. Two consequences follow, and both are the point:

- **An unattested requirement is visibly unattested.** A requirement built from a model
  proposal that no person confirmed renders under its own heading with
  :data:`~sofact.views.UNATTESTED_MARKER` beside it, and the marker is *derived* from the
  ledger rather than passed in. A document cannot be rendered clean over a specification whose
  answers a human never read.
- **An unoracled requirement prints as unverified**, with its verification method, so the
  document cannot read as stronger than the contract it renders.

The module imports :mod:`sofact.views` and nothing else that is not the standard library.
That is a constraint rather than a coincidence: this renderer must never become reachable from
an authoring surface, and a module whose import list is one package deep cannot pull one in.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from sofact.views import (
	UNATTESTED_MARKER,
	AnswerProvenance,
	ClauseVerdictProvenance,
	Contract,
	ElicitationAnswer,
	ElicitationDimension,
	ExceedsClaim,
	ProductSpecificationDocument,
	Requirement,
	RequirementAnnotation,
	Specification,
	SpecificationDraft,
)

__all__ = [
	"PRODUCT_SPEC_FILENAME",
	"PRODUCT_SPEC_HEADINGS",
	"annotate",
	"render_product_specification",
]

PRODUCT_SPEC_FILENAME: Final = "SPECIFICATION.md"
"""Where :func:`render_product_specification` writes, under the caller's root."""

PRODUCT_SPEC_HEADINGS: Final[tuple[str, ...]] = (
	"What this is",
	"Intent and its provenance",
	"Research verdicts",
	"The competitive baseline",
	"Requirements",
	"Requirements that exceed the best known",
	"Unattested requirements",
	"Assumptions",
	"Non-goals",
	"Oracle strength",
	"Machine checks",
)
"""The headings :func:`render_product_specification` always writes, in order.

A constant rather than an inline sequence because the test suite asserts the rendered
document against it: a heading that went missing would take its section with it, and the one
thing an annotated specification cannot tolerate is reading as complete while a qualification
has quietly dropped out of it. Same device as :data:`~sofact.writing.DELIVERY_HEADINGS`.
"""

_EMPTY: Final[str] = "_None._"
"""What a section says when it has nothing to list — :data:`~sofact.writing._EMPTY`'s rule.

A sentence rather than an empty body, because a heading with nothing under it reads as a
document that lost a section.
"""


def annotate(
	specification: Specification,
	contract: Contract,
	draft: SpecificationDraft | None,
	answers: Sequence[ElicitationAnswer],
	attested: frozenset[str],
	verdicts: Mapping[str, ClauseVerdictProvenance] = {},
	exceeds: Iterable[ExceedsClaim] = (),
	modules: Mapping[str, str] = {},
) -> tuple[RequirementAnnotation, ...]:
	"""Every requirement, with the facts that explain why it exists (FR-171).

	The join this performs is **not derivable from the contract alone**, and that is worth
	stating because it is the reason the function takes six arguments. A ``ClauseStem``
	carries ``derived_from``, and ``Contract.from_draft`` keeps the stem's id as the clause's
	id — but the draft's stems are not on the contract, so a renderer holding only the
	contract cannot say which elicitation dimension a requirement came from. The draft is
	read from the log by ``goal_id`` and matched on clause id, and the read is stated here
	rather than assumed at the call site.

	``draft`` is optional because a contract can be built with no P0 history at all
	(``Contract.from_draft`` takes any draft), in which case the annotation is empty rather
	than invented — and an empty annotation means :attr:`RequirementAnnotation.unattested`
	is ``False``, which is correct: there is no answer behind it to be unattested.

	``attested`` is the set of answer ids a person confirmed. It is passed in rather than
	read here because this module holds no ledger, and a renderer that reached for one would
	be a renderer that could disagree with the fold.
	"""
	stem_by_id = {s.id: s for s in (draft.stems if draft is not None else ())}
	answer_by_dimension: dict[ElicitationDimension, ElicitationAnswer] = {}
	for answer in answers:
		answer_by_dimension[answer.dimension] = answer
	clause_by_id = {c.id: c for c in contract.clauses}
	exceeds_by_clause: dict[str, list[str]] = {}
	for claim in exceeds:
		for clause_id in claim.clause_ids:
			exceeds_by_clause.setdefault(clause_id, []).append(claim.id)

	annotations: list[RequirementAnnotation] = []
	for requirement in specification.requirements:
		dimensions: list[ElicitationDimension] = []
		for clause_id in requirement.clause_ids:
			stem = stem_by_id.get(clause_id)
			if stem is not None and stem.derived_from not in dimensions:
				dimensions.append(stem.derived_from)
		elicitation: list[AnswerProvenance] = []
		for dimension in dimensions:
			answer = answer_by_dimension.get(dimension)
			if answer is None:
				continue
			elicitation.append(
				AnswerProvenance(
					dimension=dimension,
					answer_id=answer.id,
					answered_by=answer.answered_by,
					attested=answer.id in attested,
				)
			)
		research: list[ClauseVerdictProvenance] = []
		for clause_id in requirement.clause_ids:
			found = verdicts.get(clause_id)
			if found is not None:
				research.append(found)
		claim_ids: list[str] = []
		for clause_id in requirement.clause_ids:
			claim_ids.extend(exceeds_by_clause.get(clause_id, ()))
		first = requirement.clause_ids[0] if requirement.clause_ids else None
		clause = clause_by_id.get(first) if first is not None else None
		annotations.append(
			RequirementAnnotation(
				requirement=requirement,
				clause_ids=requirement.clause_ids,
				elicitation=tuple(elicitation),
				research=tuple(research),
				oracle_class=clause.oracle.oracle_class if clause is not None else None,
				oracle_rank=clause.oracle.rank if clause is not None else None,
				module_id=modules.get(first) if first is not None else None,
				exceeds_claim_ids=tuple(dict.fromkeys(claim_ids)),
			)
		)
	return tuple(annotations)


def _annotation_lines(
	requirement: Requirement,
	annotation: RequirementAnnotation | None,
) -> list[str]:
	"""One requirement and its provenance, as a bullet with indented sub-bullets."""
	lines = [f"- `{requirement.id}` {requirement.statement}"]
	if annotation is None:
		lines.append("  - provenance: not recorded — this requirement traces to no draft stem")
		return lines
	lines.append(f"  - criterion: {requirement.criterion}")
	lines.append(
		f"  - verification: {requirement.verification_method.value}"
		+ (
			" (a machine can decide this)"
			if requirement.is_machine_checkable
			else " (a human must decide this, and that cost is visible at the gate)"
		)
	)
	lines.append(f"  - traces to clause(s): {', '.join(annotation.clause_ids) or 'none'}")
	if annotation.oracle_class is not None:
		lines.append(
			f"  - oracle: {annotation.oracle_class.value}, rank {annotation.oracle_rank} "
			"(1 is strongest)"
		)
	else:
		lines.append(
			"  - oracle: none — this requirement traces to no clause in the contract, so "
			"nothing checks it"
		)
	if annotation.module_id is not None:
		lines.append(f"  - module: `{annotation.module_id}`")
	for answer in annotation.elicitation:
		marker = "attested" if answer.attested else "NOT attested"
		lines.append(
			f"  - from the {answer.dimension.value} answer `{answer.answer_id}`, "
			f"given by {answer.answered_by!r} ({marker})"
		)
	if not annotation.elicitation:
		lines.append("  - from: no elicitation answer is recorded behind this requirement")
	for verdict in annotation.research:
		evidence = ", ".join(verdict.source_ids) or "none"
		lines.append(
			f"  - research on `{verdict.clause_id}`: {verdict.verdict.value} "
			f"(evidence: {evidence})"
		)
	if annotation.exceeds_claim_ids:
		lines.append(
			f"  - exceeds the baseline, as declared in: {', '.join(annotation.exceeds_claim_ids)}"
		)
	return lines


def render_product_specification(document: ProductSpecificationDocument) -> str:
	"""``SPECIFICATION.md``: the specification P2 gates on, annotated with its provenance.

	Every section is written whether or not it has content, and the heading set is asserted
	against the render — a dropped section is the failure a reader cannot notice, because a
	document missing a heading still reads as a document.
	"""
	lines: list[str] = [
		"# Product specification",
		"",
		f"- Document: `{document.id}`",
		f"- Rendered: {document.rendered_at.isoformat()}",
		f"- Specification: `{document.specification_id}`",
		f"- Contract: `{document.contract_id}`",
		(
			f"- Competitive baseline: `{document.landscape_id}`"
			if document.landscape_id is not None
			else "- Competitive baseline: none recorded"
		),
		(
			f"- Approved by {document.approved_by!r} at {document.approved_at.isoformat()}"
			if document.approved_by is not None and document.approved_at is not None
			else "- Approved: not yet — this is a proposal, and the P2 gate is what approves it"
		),
		"",
		"## What this is",
		"",
		"This is a rendering of the specification record, not the record itself: every "
		"sentence below is derived from the ledger, and two renders of one specification are "
		"byte-identical. Nothing here paraphrases or adds a claim the records do not "
		"support.",
		"",
		"Every requirement is annotated with where it came from. **A requirement whose "
		"elicitation answer was proposed by a machine and confirmed by nobody is marked as "
		"unattested** — read that section before approving the gate.",
		"",
		"## Intent and its provenance",
		"",
	]
	seen: dict[str, AnswerProvenance] = {}
	for annotation in document.requirements:
		for answer in annotation.elicitation:
			seen.setdefault(answer.answer_id, answer)
	if seen:
		for answer in seen.values():
			state = "attested by a person" if answer.attested else "NOT attested"
			lines.append(
				f"- **{answer.dimension.value}** — answer `{answer.answer_id}`, given by "
				f"{answer.answered_by!r}, {state}"
			)
	else:
		lines.append(_EMPTY)

	lines += ["", "## Research verdicts", ""]
	verdicts: dict[str, ClauseVerdictProvenance] = {}
	for annotation in document.requirements:
		for verdict in annotation.research:
			verdicts.setdefault(verdict.clause_id, verdict)
	if verdicts:
		for verdict in verdicts.values():
			evidence = ", ".join(verdict.source_ids) or "none"
			lines.append(
				f"- `{verdict.clause_id}`: {verdict.verdict.value} (evidence: {evidence})"
			)
	else:
		lines.append(
			"No research verdict is recorded for any clause this specification traces to. "
			"That is a statement about this run, not about the clauses."
		)

	lines += ["", "## The competitive baseline", ""]
	if document.landscape_id is None:
		lines.append(
			"No competitive scan is recorded, so no requirement here is positioned against "
			"another system."
		)
	else:
		lines.append(
			f"The scan is `{document.landscape_id}`. **SoFact did not choose the systems "
			"compared against** — the research producer identified them under a criterion "
			"SoFact wrote into the goal, and this document does not claim the set is the "
			"best in the world."
		)

	lines += ["", "## Requirements", ""]
	if document.requirements:
		for annotation in document.requirements:
			lines.extend(_annotation_lines(annotation.requirement, annotation))
	else:
		lines.append(_EMPTY)

	lines += ["", "## Requirements that exceed the best known", ""]
	if document.exceeds:
		lines.append(
			"**These are declared targets, not verified facts.** No oracle in O1-O7 "
			"compares two systems, so nothing here is measured — the margin is unmeasured by "
			"construction (FR-170, NFR-024)."
		)
		lines.append("")
		for claim in document.exceeds:
			lines.append(f"- `{claim.id}` {claim.capability}")
			lines.append(f"  - baseline: {claim.baseline}")
			lines.append(
				f"  - baseline evidence: {', '.join(claim.baseline_source_ids)}"
			)
			lines.append(f"  - rationale: {claim.rationale}")
			lines.append(
				f"  - measured margin: unmeasured (declared by {claim.declared_by!r})"
			)
	else:
		lines.append("No capability is declared to exceed another system's.")

	lines += ["", "## Unattested requirements", ""]
	unattested = document.unattested
	if unattested:
		lines.append(
			f"{len(unattested)} of {len(document.requirements)} requirement(s) descend from "
			"an answer a machine proposed and no person confirmed. The P2 gate is where that "
			"changes: either a person attests the answer (`sofact attest <id> --by <you>`) or "
			"answers the dimension themselves, and either way the requirement stops being a "
			"proposal."
		)
		lines.append("")
		for annotation in unattested:
			lines.append(f"- {UNATTESTED_MARKER}")
			lines.append(
				f"  - `{annotation.requirement_id}` {annotation.requirement.statement}"
			)
			for answer in annotation.unattested_answers:
				lines.append(
					f"  - proposed by {answer.answered_by!r} as the "
					f"{answer.dimension.value} answer `{answer.answer_id}`"
				)
	else:
		lines.append(
			"Every requirement descends from an answer a person gave or confirmed."
		)

	lines += ["", "## Assumptions", ""]
	lines += _assumption_lines(document)

	lines += ["", "## Non-goals", ""]
	lines.append(
		"The non-goals are recorded on the specification record and are not carried on this "
		"document's annotations, because they bound the work rather than describe it. Read "
		"them with `sofact specify` before approving: a specification's boundaries are what "
		"a reader is most likely to assume rather than check."
	)

	lines += ["", "## Oracle strength", ""]
	ranks = sorted(
		(annotation.oracle_rank for annotation in document.requirements if annotation.oracle_rank),
	)
	if ranks:
		lines.append(
			f"Requirement oracles range from rank {ranks[0]} (strongest) to rank {ranks[-1]} "
			f"(weakest) over {len(ranks)} requirement(s). Rank 1 is a property, rank 7 a "
			"golden file; a rank above the covering maximum is an intention rather than a "
			"check, and the delivery report names those as unverified."
		)
	else:
		lines.append(
			"No requirement carries an oracle rank, which means none traces to a clause in "
			"the contract. Nothing in this specification can be checked by a machine."
		)

	lines += ["", "## Machine checks", ""]
	lines.append(
		f"- Rendered from {len(document.requirements)} requirement annotation(s)."
	)
	lines.append(
		f"- Unattested: {len(unattested)} requirement(s) "
		f"({len(unattested)} of {len(document.requirements)})."
	)
	lines.append(
		f"- Declared exceedances: {len(document.exceeds)}, of which 0 are verified by oracle."
	)
	lines.append(
		"- This document is a rendering. The record it renders is `"
		f"{document.id}` and the contract it describes is `{document.contract_id}`."
	)

	rendered = "\n".join(lines) + "\n"
	missing = [h for h in PRODUCT_SPEC_HEADINGS if f"## {h}" not in rendered]
	assert not missing, f"the product specification lost section(s): {missing}"
	return rendered


def _assumption_lines(document: ProductSpecificationDocument) -> list[str]:
	"""The assumptions section.

	Read from the annotations' requirements would be wrong — assumptions are the
	specification's, not a requirement's — so the caller passes them through the document.
	Until the document carries them, this says so rather than printing an empty list, which
	would read as "there are none" when the truth is "this renderer does not have them".
	"""
	return [
		"Assumptions are carried on the specification record rather than on the annotations "
		"here, so this section states where to read them rather than reproducing them: "
		"`sofact specify` prints each with the observation that would refute it (FR-079). "
		"An assumption reproduced in two documents is an assumption that can come to "
		"disagree with itself."
	]
