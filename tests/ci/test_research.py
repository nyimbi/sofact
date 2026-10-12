"""P1's artefact reader — the source ledger (FR-070).

The parser is the boundary between a producer's files and a typed ledger, and every
refusal in it fails *closed*: a line it cannot read raises rather than being skipped,
because a parser that drops what it does not understand reports a clean ledger over the
remains. That property is what most of this module measures — a refusal that was never
exercised is a refusal nobody can rely on.

The documents here are written the way ``docs/sources/`` writes them, because that
ledger is the spec's own reference implementation of this phase.
"""

from __future__ import annotations

from datetime import date

import pytest

from sofact.research import (
	ledger_checks,
	parse_claim_document,
	parse_ledger,
	parse_source_document,
)
from sofact.views import (
	ClaimKind,
	SourceLedger,
	SourcePosture,
	VerificationStatus,
)

GOOD = """\
---
id: S01
slug: measured-paper
title: "A measured paper"
type: paper
url: https://example.com/paper
retrieved: 2026-09-12
verification: content-verified
confidence: medium
tags: [harness, research]
---

## Precis

The paper measures a thing and reports the number.

## Key claims

- the number is 42

## Concerns / information quality

Preprint; not peer reviewed.
"""


def _document(**overrides: str) -> str:
	"""``GOOD`` with front-matter lines replaced, so each test moves one thing.

	Keys are the front-matter spellings themselves (``superseded_by``, not
	``superseded-by``): the ledger's own field names are the ones under test, and a
	helper that translated them would test its own translation.
	"""
	lines: list[str] = list(GOOD.split("\n"))
	for name, value in overrides.items():
		for position, line in enumerate(lines):
			if line.startswith(f"{name}:"):
				lines[position] = f"{name}: {value}"
				break
		else:
			lines.insert(1, f"{name}: {value}")
	return "\n".join(lines)


class TestOneSourceDocument:
	def test_the_reference_ledgers_shape_parses(self) -> None:
		source = parse_source_document(GOOD, fallback_id="S99")

		assert source.id == "S01"
		assert source.slug == "measured-paper"
		assert source.title == "A measured paper"
		assert source.url == "https://example.com/paper"
		assert source.retrieved == date(2026, 9, 12)
		assert source.verification is VerificationStatus.CONTENT_VERIFIED
		assert source.posture is SourcePosture.EVIDENCE
		assert source.precis.startswith("The paper measures")
		assert source.critique.startswith("Preprint")
		assert source.expires is None

	def test_a_block_list_parses_as_readily_as_an_inline_one(self) -> None:
		"""``docs/sources/`` uses both spellings; a parser for one loses the other."""
		block = GOOD.replace("tags: [harness, research]", "tags:\n  - harness\n  - research")
		source = parse_source_document(block, fallback_id="S99")

		assert source.id == "S01"

	def test_a_qualified_heading_still_answers_for_its_section(self) -> None:
		"""``## Key claims (observed, not reported)`` is a claims section with a caveat."""
		qualified = GOOD.replace("## Precis", "## Precis (what it says)")
		source = parse_source_document(qualified, fallback_id="S99")

		assert source.precis.startswith("The paper measures")

	def test_the_fallback_id_is_used_when_the_document_has_none(self) -> None:
		"""An entry without a citation key is still addressable, or nothing can cite it."""
		lines = [line for line in GOOD.split("\n") if not line.startswith("id:")]
		source = parse_source_document("\n".join(lines), fallback_id="S07")

		assert source.id == "S07"

	def test_a_document_with_no_front_matter_is_refused(self) -> None:
		with pytest.raises(ValueError, match="no front-matter"):
			parse_source_document("## Precis\n\nnothing\n", fallback_id="S01")

	def test_a_block_scalar_is_refused_rather_than_misread(self) -> None:
		"""``|`` read as a scalar would make the value the literal pipe character."""
		with pytest.raises(ValueError, match="block scalar"):
			parse_source_document(_document(confidence="|"), fallback_id="S01")

	def test_a_line_that_is_neither_a_pair_nor_a_list_item_is_refused(self) -> None:
		broken = GOOD.replace("type: paper", "type paper")
		with pytest.raises(ValueError, match="neither 'key: value' nor a list item"):
			parse_source_document(broken, fallback_id="S01")

	def test_a_list_item_before_any_key_is_refused(self) -> None:
		broken = GOOD.replace("---\nid: S01", "---\n- orphan")
		with pytest.raises(ValueError, match="list item before any key"):
			parse_source_document(broken, fallback_id="S01")

	@pytest.mark.parametrize(
		("override", "message"),
		[
			({"title": '""'}, "needs a title"),
			({"confidence": '""'}, "carries no confidence"),
			({"retrieved": "last Tuesday"}, "not an ISO date"),
			({"verification": "probably"}, "is not one of"),
		],
	)
	def test_a_required_or_typed_field_that_cannot_be_read_is_refused(
		self, override: dict[str, str], message: str
	) -> None:
		with pytest.raises(ValueError, match=message):
			parse_source_document(_document(**override), fallback_id="S01")

	@pytest.mark.parametrize("heading", ["## Precis", "## Concerns / information quality"])
	def test_a_missing_body_section_is_refused(self, heading: str) -> None:
		"""The critique is the entry: a source without one is a link, not evidence."""
		lines: list[str] = list(GOOD.split("\n"))
		start = lines.index(heading)
		end = next(
			(
				position
				for position in range(start + 1, len(lines))
				if lines[position].startswith("## ")
			),
			len(lines),
		)
		with pytest.raises(ValueError, match="section"):
			parse_source_document("\n".join(lines[:start] + lines[end:]), fallback_id="S01")

	def test_an_unknown_posture_is_refused(self) -> None:
		with pytest.raises(ValueError, match="is not one of"):
			parse_source_document(_document(posture="probably"), fallback_id="S01")


class TestTheLedgerAsAWhole:
	def test_the_edges_between_claims_and_sources_resolve(self) -> None:
		ledger = parse_ledger(
			goal_id="01900000-0000-7000-8000-000000000000",
			query="whether it holds",
			documents=(GOOD,),
			claims={
				"claims": [
					{"id": "C1", "statement": "it holds", "source_ids": ["S01"]},
					{
						"id": "C2",
						"statement": "it may not",
						"kind": "disconfirming",
						"source_ids": ["S01"],
					},
				],
				"contradictions": [],
			},
		)

		assert [claim.id for claim in ledger.resting_on("S01")] == ["C1", "C2"]
		assert [claim.id for claim in ledger.disconfirming] == ["C2"]
		assert ledger.version == 1

	def test_a_claim_citing_a_source_the_ledger_lacks_is_refused(self) -> None:
		"""A dangling edge cannot be invalidated with its source, which is its whole point."""
		with pytest.raises(ValueError, match="cites unknown source"):
			parse_ledger(
				goal_id="01900000-0000-7000-8000-000000000000",
				query="whether it holds",
				documents=(GOOD,),
				claims={"claims": [{"id": "C1", "statement": "it holds", "source_ids": ["S42"]}]},
			)

	def test_two_entries_sharing_an_id_are_refused(self) -> None:
		"""An address that names two things addresses neither."""
		with pytest.raises(ValueError, match="duplicate source id"):
			parse_ledger(
				goal_id="01900000-0000-7000-8000-000000000000",
				query="whether it holds",
				documents=(GOOD, GOOD),
			)

	def test_a_claim_superseded_by_a_claim_the_ledger_lacks_is_refused(self) -> None:
		with pytest.raises(ValueError, match="superseded by"):
			parse_ledger(
				goal_id="01900000-0000-7000-8000-000000000000",
				query="whether it holds",
				documents=(GOOD,),
				claims={
					"claims": [
						{"id": "C1", "statement": "it holds", "superseded_by": "C9"},
					]
				},
			)

	def test_a_source_superseded_by_a_source_the_ledger_lacks_is_refused(self) -> None:
		"""A supersession edge pointing nowhere is a source silently retired."""
		with pytest.raises(ValueError, match="superseded by"):
			parse_ledger(
				goal_id="01900000-0000-7000-8000-000000000000",
				query="q",
				documents=(_document(superseded_by="S99"),),
			)


class TestClaimsAndContradictions:
	def test_an_opinion_may_rest_on_no_source_and_may_not_cite_one(self) -> None:
		claims, _ = parse_claim_document(
			{"claims": [{"id": "C1", "statement": "operators will accept this", "opinion": True}]}
		)
		assert claims[0].opinion is True
		assert claims[0].kind is ClaimKind.SUPPORTING

		with pytest.raises(ValueError, match="labelled opinion and cites"):
			parse_claim_document(
				{
					"claims": [
						{
							"id": "C1",
							"statement": "operators will accept this",
							"opinion": True,
							"source_ids": ["S01"],
						}
					]
				}
			)

	def test_a_positioning_source_cannot_be_content_verified(self) -> None:
		"""Reading vendor content carefully does not make it evidence (FR-074)."""
		with pytest.raises(ValueError, match="positioning and content-verified"):
			parse_source_document(
				_document(posture="positioning", verification="content-verified"),
				fallback_id="S01",
			)

	def test_a_truthy_string_is_not_a_boolean(self) -> None:
		"""``bool("false")`` is True: coercion here would invert the label it sets."""
		with pytest.raises(ValueError, match="expected true or false"):
			parse_claim_document({"claims": [{"id": "C1", "statement": "s", "opinion": "false"}]})

	def test_a_contradiction_needs_two_sources(self) -> None:
		with pytest.raises(ValueError, match="a source cannot disagree with itself"):
			parse_claim_document(
				{"contradictions": [{"id": "X1", "statement": "s", "source_ids": ["S01"]}]}
			)

	def test_a_contradiction_may_name_a_source_the_ledger_lacks_only_through_the_ledger(
		self,
	) -> None:
		with pytest.raises(ValueError, match="names unknown source"):
			parse_ledger(
				goal_id="01900000-0000-7000-8000-000000000000",
				query="q",
				documents=(GOOD,),
				claims={
					"contradictions": [{"id": "X1", "statement": "s", "source_ids": ["S01", "S77"]}]
				},
			)

	@pytest.mark.parametrize(
		"payload",
		[
			["not", "an", "object"],
			{"claims": {"C1": "not a list"}},
			{"claims": [{"id": "C1"}]},
			{"claims": [{"id": "C1", "statement": "s", "unexpected": 1}]},
			{"unexpected": []},
		],
	)
	def test_a_malformed_claims_file_is_refused(self, payload: object) -> None:
		with pytest.raises(ValueError):
			parse_claim_document(payload)

	def test_an_expiry_that_cannot_be_read_is_refused_rather_than_dropped(self) -> None:
		"""Dropping it would leave a time-sensitive claim looking durable (FR-075)."""
		with pytest.raises(ValueError, match="not an ISO date"):
			parse_claim_document({"claims": [{"id": "C1", "statement": "s", "expires": "soon"}]})


class TestTheLedgerChecks:
	def _ledger(self, **claim: object) -> SourceLedger:
		base: dict[str, object] = {"id": "C1", "statement": "it holds", "source_ids": ["S01"]}
		base.update(claim)
		return parse_ledger(
			goal_id="01900000-0000-7000-8000-000000000000",
			query="whether it holds",
			documents=(GOOD,),
			claims={"claims": [base]},
		)

	def test_a_sourced_claim_on_an_evidence_source_passes_every_check(self) -> None:
		checks = {check.name: check for check in ledger_checks(self._ledger())}

		assert set(checks) == {
			"claims-carry-provenance",
			"positioning-is-not-evidence",
			"nothing-has-expired",
		}
		assert all(check.passed for check in checks.values())

	def test_an_uncited_claim_that_is_not_labelled_an_opinion_fails(self) -> None:
		checks = {check.name: check for check in ledger_checks(self._ledger(source_ids=[]))}

		assert checks["claims-carry-provenance"].passed is False
		assert "C1" in checks["claims-carry-provenance"].detail

	def test_a_positioning_only_claim_fails_the_evidence_check(self) -> None:
		vendor = GOOD.replace("id: S01", "id: S02").replace(
			"verification: content-verified", "verification: url-verified\nposture: positioning"
		)
		ledger = parse_ledger(
			goal_id="01900000-0000-7000-8000-000000000000",
			query="whether it holds",
			documents=(vendor,),
			claims={"claims": [{"id": "C1", "statement": "s", "source_ids": ["S02"]}]},
		)
		checks = {check.name: check for check in ledger_checks(ledger)}

		assert checks["positioning-is-not-evidence"].passed is False
		assert "C1" in checks["positioning-is-not-evidence"].detail

	def test_an_expired_source_fails_the_staleness_check(self) -> None:
		"""The check is as-of a date, so the same ledger can be current and then not."""
		ledger = parse_ledger(
			goal_id="01900000-0000-7000-8000-000000000000",
			query="q",
			documents=(_document(expires="2026-01-01"),),
		)

		assert ledger_checks(ledger, as_of=date(2025, 12, 31))[2].passed is True
		assert ledger_checks(ledger, as_of=date(2026, 1, 2))[2].passed is False

	def test_the_disconfirming_count_is_never_a_check(self) -> None:
		"""FR-071 asks for detectability; a gate at zero would pay for fabrication."""
		names = {check.name for check in ledger_checks(self._ledger())}

		assert "disconfirming" not in " ".join(names)
		assert all(check.passed for check in ledger_checks(self._ledger()))
