"""FR-169 — the competitive baseline, and the two ways it could become a rumour.

SoFact cannot name the best systems in the world for an arbitrary domain, and a factory
that did would be writing the claim it then measures. So the producer identifies the
systems — under a criterion SoFact writes into the research goal — and the identification
is admissible only with the evidence behind it.

Two properties carry the module. **A rival with no source is refused outright**, so a
baseline cannot be assembled from names nobody can look up. And **the subject is the one
SoFact asked for**: a scan that retitled the question would otherwise be read downstream
as an answer to it, which is the same failure ``research_goal`` prevents by writing the
clause ids into the prompt rather than letting the producer choose them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sofact._uuid7 import uuid7str
from sofact.competitive import (
	LEDGER_COMPETITORS_FILENAME,
	competitor_checks,
	parse_competitors,
)
from sofact.views import (
	CapabilityKind,
	CompetitiveLandscape,
	RivalCapability,
	RivalSystem,
	SourcePosture,
)

QUERY = "meter reading services"


def a_system(
	*,
	name: str = "Rival",
	source_ids: tuple[str, ...] | None = None,
	url: str = "https://example.invalid/rival",
	posture: str = SourcePosture.EVIDENCE.value,
) -> dict[str, object]:
	return {
		"id": uuid7str(),
		"name": name,
		"vendor": "Rival Ltd",
		"url": url,
		"source_ids": [uuid7str()] if source_ids is None else list(source_ids),
		"posture": posture,
	}


def a_capability(
	system_id: str, *, statement: str = "Reads a meter.", kind: str = "feature"
) -> dict[str, object]:
	return {
		"id": uuid7str(),
		"system_id": system_id,
		"statement": statement,
		"kind": kind,
		"source_ids": [uuid7str()],
	}


def a_scan(
	systems: list[dict[str, object]] | None = None,
	capabilities: list[dict[str, object]] | None = None,
	*,
	subject: str = QUERY,
) -> dict[str, object]:
	return {
		"subject": subject,
		"domain": "utility metering",
		"selection_criterion": "The systems most cited in utility procurement 2024-2026.",
		"systems": systems if systems is not None else [],
		"capabilities": capabilities if capabilities is not None else [],
	}


def parse(payload: object, *, version: int = 1) -> CompetitiveLandscape:
	return parse_competitors(payload, goal_id=uuid7str(), query=QUERY, version=version)


# --------------------------------------------------------------------------- #
# what is admissible
# --------------------------------------------------------------------------- #


def test_a_well_formed_scan_parses() -> None:
	system = a_system()
	landscape = parse(a_scan([system], [a_capability(str(system["id"]))]))
	assert len(landscape.systems) == 1
	assert len(landscape.capabilities) == 1
	assert landscape.sourced_systems == landscape.systems


def test_a_rival_with_no_source_is_refused() -> None:
	"""The whole of what makes a name a baseline: evidence behind it.

	This is the exclusion the plan's canary 6 removes, and it is the one that matters —
	a landscape of five unsourced rivals is a list of names, and every downstream reader
	would take it as a survey.
	"""
	with pytest.raises(ValueError, match="no source"):
		parse(a_scan([a_system(source_ids=())]))


def test_a_scan_that_renamed_the_subject_is_refused() -> None:
	"""A producer cannot answer a different question and have it read as this one."""
	with pytest.raises(ValueError, match="not the subject SoFact asked for"):
		parse(a_scan(subject="something else entirely"))


def test_a_capability_of_no_known_system_is_refused() -> None:
	"""A capability of nothing cannot be compared against anything."""
	with pytest.raises(ValueError, match="name a system the scan does not carry"):
		parse(a_scan([a_system()], [a_capability(uuid7str())]))


def test_a_posture_that_is_not_one_of_the_two_raises() -> None:
	"""Positioning defaulted to evidence would let a vendor's own page support a decision."""
	with pytest.raises(ValueError, match="not one of"):
		parse(a_scan([a_system(posture="marketing")]))


def test_a_kind_that_is_not_one_of_the_three_raises() -> None:
	"""The operator asked about features, capabilities and functionality, and merging them
	loses the distinction the exceedance declaration needs."""
	with pytest.raises(ValueError, match=r"not one of feature, capability, functionality"):
		system = a_system()
		parse(a_scan([system], [a_capability(str(system["id"]), kind="thing")]))


def test_an_unknown_document_key_is_refused_rather_than_dropped() -> None:
	"""Fail-closed on every axis, the discipline ``parse_classification`` follows."""
	payload = a_scan()
	payload["rivals"] = []
	with pytest.raises(ValueError, match=r"unknown key\(s\) \['rivals'\]"):
		parse(payload)


def test_an_unknown_system_key_is_refused() -> None:
	system = a_system()
	system["market_share"] = 0.4
	with pytest.raises(ValueError, match=r"unknown key\(s\) \['market_share'\]"):
		parse(a_scan([system]))


def test_a_missing_statement_is_refused_rather_than_defaulted() -> None:
	system = a_system()
	del system["name"]
	with pytest.raises(ValueError, match="system name: required"):
		parse(a_scan([system]))


def test_the_version_is_the_callers_not_the_producers() -> None:
	"""Read off the folded state, so two scans cannot share a number."""
	assert parse(a_scan(), version=3).version == 3


# --------------------------------------------------------------------------- #
# what the landscape measures
# --------------------------------------------------------------------------- #


def test_a_scan_that_found_nothing_is_a_measurement_not_a_failure() -> None:
	"""A domain with no comparable system is a real finding about the domain.

	Treating it as an error would push a producer toward inventing rivals to avoid one.
	"""
	landscape = parse(a_scan())
	assert landscape.found_nothing
	assert landscape.sourced_systems == ()


def test_a_rival_with_no_capability_is_unexamined() -> None:
	"""A landscape of well-sourced rivals whose capabilities were never enumerated is a
	*weaker* baseline than one rival that was examined, and the count says so."""
	system = a_system()
	landscape = parse(a_scan([system]))
	assert landscape.unexamined_systems == landscape.systems
	assert landscape.found_nothing is False


def test_the_three_kinds_survive_as_three_kinds() -> None:
	"""The operator's three words are kept distinct rather than merged into one list."""
	system = a_system()
	sid = str(system["id"])
	landscape = parse(
		a_scan(
			[system],
			[
				a_capability(sid, statement="Does X.", kind="feature"),
				a_capability(sid, statement="Holds under load.", kind="capability"),
				a_capability(sid, statement="Reached over HTTP.", kind="functionality"),
			],
		)
	)
	assert {c.kind for c in landscape.capabilities} == {
		CapabilityKind.FEATURE,
		CapabilityKind.CAPABILITY,
		CapabilityKind.FUNCTIONALITY,
	}


# --------------------------------------------------------------------------- #
# the checks
# --------------------------------------------------------------------------- #


def test_every_check_passes_because_a_thin_baseline_is_a_measurement() -> None:
	"""Refusing the phase over a thin baseline would teach a producer to inflate it."""
	landscape = parse(a_scan([a_system()]))
	checks = competitor_checks(landscape, None)
	assert checks
	assert all(c.passed for c in checks)


def test_the_counts_reach_the_gate() -> None:
	"""The checks exist to put the counts in front of the reader at the gate."""
	system = a_system()
	landscape = parse(a_scan([system]))
	detail = next(
		c.detail for c in competitor_checks(landscape, None) if c.name == "every_rival_was_examined"
	)
	assert "1 of 1 rival(s) have no capability recorded" in detail


def test_a_cited_id_the_ledger_does_not_hold_is_reported_as_dangling() -> None:
	"""Reported rather than dropped: a rival whose evidence cannot be found is a weaker
	baseline than one whose can, and the difference has to be visible."""
	landscape = parse(a_scan([a_system()]))
	detail = next(
		c.detail
		for c in competitor_checks(landscape, None)
		if c.name == "every_rival_cites_a_source"
	)
	assert "1 cited id(s) name no source the ledger holds" in detail


def test_a_scan_over_no_rival_claims_nothing() -> None:
	"""``None`` when the artefact is absent, and a scan over zero sourced rivals claims
	nothing — never a clean baseline."""
	landscape = parse(a_scan())
	detail = next(
		c.detail
		for c in competitor_checks(landscape, None)
		if c.name == "every_rival_cites_a_source"
	)
	assert "0 of 0 rival(s) cite at least one source" in detail


# --------------------------------------------------------------------------- #
# the view's own invariants
# --------------------------------------------------------------------------- #


def test_a_landscape_cannot_hold_an_uncited_rival() -> None:
	"""The refusal is at construction, so no caller can build one by any route."""
	with pytest.raises(ValueError, match="no source"):
		RivalSystem(
			id=uuid7str(),
			name="Rival",
			url="https://example.invalid",
			source_ids=(),
			posture=SourcePosture.EVIDENCE,
		)


def test_a_capability_cannot_name_a_stranger_system() -> None:
	with pytest.raises(ValueError, match="name a system the scan does not carry"):
		CompetitiveLandscape(
			id=uuid7str(),
			goal_id=uuid7str(),
			query=QUERY,
			subject=QUERY,
			systems=(),
			capabilities=(
				RivalCapability(
					id=uuid7str(),
					system_id=uuid7str(),
					statement="Reads a meter.",
					kind=CapabilityKind.FEATURE,
					source_ids=(uuid7str(),),
				),
			),
			scanned_at=__import__("sofact.views", fromlist=["now"]).now(),
		)


# --------------------------------------------------------------------------- #
# the service path, end to end over a real artefact file
# --------------------------------------------------------------------------- #


async def test_the_scan_is_read_from_the_runs_workspace(tmp_path: Path) -> None:
	"""Read from the run's own artefact, the rule ``ledger_from`` follows: the scan is a
	finding about a dispatch rather than something a caller can assert."""
	from sofact.service import FactoryService
	from sofact.views import ResearchMode, ResearchRecord, now

	service = FactoryService(home=tmp_path / "home", llm=None)
	goal = await service.start(QUERY)
	workspace = tmp_path / "workspace"
	workspace.mkdir()
	system = a_system()
	(workspace / LEDGER_COMPETITORS_FILENAME).write_text(
		json.dumps(a_scan([system], [a_capability(str(system["id"]))])), encoding="utf-8"
	)
	record = ResearchRecord(
		id=uuid7str(),
		goal_id=goal.id,
		query=goal.statement,
		mode=ResearchMode.DEEP,
		harness="synthetic",
		argv=(),
		workspace=str(workspace),
		started_at=now(),
		ended_at=now(),
	)
	landscape = await service.competitors(record=record)
	assert len(landscape.systems) == 1
	assert landscape.version == 1
	# And the second scan is version 2, read off the folded state rather than passed in.
	assert (await service.competitors(record=record)).version == 2


async def test_a_run_that_left_no_scan_is_refused_rather_than_read_as_empty(
	tmp_path: Path,
) -> None:
	"""An empty scan would read as a producer that looked and found no rival — a real
	finding — rather than one that was never asked (NFR-024)."""
	from sofact.service import FactoryService
	from sofact.views import ResearchMode, ResearchRecord, now

	service = FactoryService(home=tmp_path / "home", llm=None)
	goal = await service.start(QUERY)
	workspace = tmp_path / "empty"
	workspace.mkdir()
	record = ResearchRecord(
		id=uuid7str(),
		goal_id=goal.id,
		query=goal.statement,
		mode=ResearchMode.DEEP,
		harness="synthetic",
		argv=(),
		workspace=str(workspace),
		started_at=now(),
		ended_at=now(),
	)
	with pytest.raises(ValueError, match=r"left no research\-competitors\.json"):
		await service.competitors(record=record)


async def test_the_competitive_gate_is_empty_with_no_scan(tmp_path: Path) -> None:
	"""The rule ``ledger_gate`` follows: nothing recorded, nothing to check."""
	from sofact.service import FactoryService

	service = FactoryService(home=tmp_path / "home", llm=None)
	assert await service.competitive_gate() == ()
