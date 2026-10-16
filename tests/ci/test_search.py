"""FR-174 — web search, and the two things that must stay true of it.

A real provider script, run as a real subprocess, writing a real results file. No
mocks: the whole point of the phase is that a *declared tool* answers the queries
SoFact authored, and a fake adapter would test the fake rather than the protocol.

Two properties carry the module. **SoFact authors the queries** — they are composed
from the goal's own words before any provider runs, and a provider cannot choose its
own subject list. And **a hit is a lead, not a source**: every hit is recorded at the
weakest verification rung, a hit with no url is refused outright, and a query that
failed is recorded as failed rather than as a domain with no results. Those are the
two ways this feature could lie, and each has a test that would fail if it did.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from sofact._uuid7 import uuid7str
from sofact.search import (
	SEARCHERS,
	SearcherSpec,
	SearchRefusal,
	authored_queries,
	load_searcher_specs,
	parse_search_results,
	scan_checks,
	searcher_spec_for,
)
from sofact.search import ConfiguredSearchAdapter as SearchAdapter
from sofact.views import (
	SearchHit,
	SearchOutcome,
	SearchQueryResult,
	SearchScan,
	SourcePosture,
	VerificationStatus,
	now,
)

PROVIDER = '''\
"""A search provider: writes a results file, or fails, or returns nothing."""
import json, sys
from pathlib import Path

mode, query, workspace = sys.argv[1], sys.argv[2], Path(sys.argv[3])
if mode == "crash":
	sys.exit(3)
if mode == "silent":
	sys.exit(0)
if mode == "empty":
	payload = {"query": query, "results": []}
elif mode == "malformed":
	payload = {"query": query, "results": [{"title": "a hit with no url"}]}
elif mode == "positioning":
	payload = {"query": query, "results": [
		{
			"title": "Our platform",
			"url": "https://vendor.example/why",
			"content": "the leader in this space",
			"category": "vendor",
		},
		{
			"title": "A study",
			"url": "https://journal.example/study",
			"content": "measured results",
			"category": "general",
		},
	]}
else:
	payload = {"query": query, "results": [
		{
			"title": f"Result for {query}",
			"url": f"https://example.test/{abs(hash(query)) % 97}",
			"content": "a snippet the provider chose",
			"publishedDate": "2026-01-02",
		},
	]}
(workspace / "results.json").write_text(json.dumps(payload))
'''


def provider_spec(tmp_path: Path, mode: str, *, name: str = "synthetic-search") -> SearcherSpec:
	"""A spec describing the shared provider script, with the mode baked into argv."""
	script = tmp_path / "provider.py"
	if not script.exists():
		script.write_text(PROVIDER, encoding="utf-8")
	return SearcherSpec(
		name=name,
		argv=(sys.executable, str(script), mode, "{query}", "{workspace}"),
		results_glob="results.json",
		posture_key="category",
		positioning_values=("vendor",),
		date_key="publishedDate",
	)


# --------------------------------------------------------------------------- #
# the queries are SoFact's
# --------------------------------------------------------------------------- #


def test_authored_queries_are_composed_before_any_provider_runs() -> None:
	"""The statement, the dimensions, then the extras — deduped, in that order."""
	queries = authored_queries(
		"a payments platform",
		dimensions={"actors": "a payments platform", "data": "settlement ledgers"},
		extra=("a payments platform", "competitors of stripe"),
	)
	assert queries == (
		"a payments platform",
		"competitors of stripe",
		"settlement ledgers",
	), "the operator's own words, deduped in order, with the goal's statement first"


def test_authored_queries_are_deterministic() -> None:
	"""Two calls over one goal produce the same list, so the log's record reproduces."""
	first = authored_queries("a thing", dimensions={"a": "x", "b": "y"})
	second = authored_queries("a thing", dimensions={"a": "x", "b": "y"})
	assert first == second


def test_authored_queries_stop_at_the_limit() -> None:
	"""A provider's rate limit is real, and the first queries are the goal's own."""
	queries = authored_queries(
		"the goal", dimensions={f"d{i}": f"dimension {i}" for i in range(20)}, limit=3
	)
	assert len(queries) == 3


# --------------------------------------------------------------------------- #
# the spec table
# --------------------------------------------------------------------------- #


def test_the_builtin_table_is_empty_and_says_so() -> None:
	"""No engine is bundled: whose index the research rests on is a deployment's choice."""
	assert SEARCHERS == {}
	with pytest.raises(SearchRefusal) as caught:
		searcher_spec_for(None, SEARCHERS)
	assert "SOFACT_SEARCHER_SPECS" in str(caught.value)


def test_an_unknown_provider_is_refused_by_name_listing_what_is_configured() -> None:
	specs = {"one": provider_spec(Path("/tmp"), "ok", name="one")}
	with pytest.raises(SearchRefusal) as caught:
		searcher_spec_for("two", specs)
	assert "two" in str(caught.value) and "one" in str(caught.value)


def test_a_spec_without_a_query_slot_is_refused(tmp_path: Path) -> None:
	"""A provider run on nothing returns results for no question."""
	with pytest.raises(AssertionError, match="must name the query"):
		SearcherSpec(name="bad", argv=("curl", "https://example.test"), results_glob="r.json")


def test_a_spec_naming_no_results_file_is_refused() -> None:
	with pytest.raises(AssertionError, match="names no results file"):
		SearcherSpec(name="bad", argv=("curl", "{query}"), results_glob="")


def test_a_spec_with_a_posture_key_and_no_values_is_refused() -> None:
	"""A field that is read and never decides is the defect this refuses."""
	with pytest.raises(AssertionError, match="without the values"):
		SearcherSpec(
			name="bad",
			argv=("curl", "{query}"),
			results_glob="r.json",
			posture_key="category",
		)


def test_an_unknown_field_is_refused_by_name(tmp_path: Path) -> None:
	"""A misspelled url_key would read every hit's url as absent."""
	path = tmp_path / "searchers.json"
	path.write_text(json.dumps({"s": {"argv": ["x"], "results_glob": "r.json", "url_ky": "u"}}))
	with pytest.raises(ValueError, match="url_ky"):
		load_searcher_specs(path)


def test_an_empty_table_is_refused(tmp_path: Path) -> None:
	path = tmp_path / "searchers.json"
	path.write_text(json.dumps({"searchers": {}}))
	with pytest.raises(ValueError, match="no searchers"):
		load_searcher_specs(path)


def test_both_table_shapes_load(tmp_path: Path) -> None:
	wrapped = tmp_path / "a.json"
	wrapped.write_text(
		json.dumps({"searchers": {"s": {"argv": ["x", "{query}"], "results_glob": "r.json"}}})
	)
	bare = tmp_path / "b.json"
	bare.write_text(json.dumps({"s": {"argv": ["x", "{query}"], "results_glob": "r.json"}}))
	assert set(load_searcher_specs(wrapped)) == set(load_searcher_specs(bare)) == {"s"}


# --------------------------------------------------------------------------- #
# a hit is a lead, not a source
# --------------------------------------------------------------------------- #


def test_a_hit_with_no_url_is_refused(tmp_path: Path) -> None:
	"""A result nobody can look up is a name, not a lead."""
	spec = provider_spec(tmp_path, "malformed")
	with pytest.raises(SearchRefusal, match="no 'url'"):
		parse_search_results({"results": [{"title": "a hit with no url"}]}, spec=spec, query="q")


def test_a_hit_refuses_to_be_content_verified() -> None:
	"""The strongest rung is unreachable by construction, not by convention."""
	with pytest.raises(ValueError, match="content-verified"):
		SearchHit(
			rank=1,
			title="t",
			url="https://example.test/x",
			provider="p",
			verification=VerificationStatus.CONTENT_VERIFIED,
		)


def test_a_parsed_hit_is_reported_never_content_verified(tmp_path: Path) -> None:
	"""Every hit the parser produces sits at the weakest rung."""
	spec = provider_spec(tmp_path, "ok")
	hits = parse_search_results(
		{"results": [{"title": "t", "url": "https://example.test/x", "content": "s"}]},
		spec=spec,
		query="q",
	)
	assert [h.verification for h in hits] == [VerificationStatus.REPORTED]
	assert hits[0].rank == 1


def test_a_rank_must_be_one_based() -> None:
	with pytest.raises(ValueError, match="one-based"):
		SearchHit(rank=0, title="t", url="https://example.test/x", provider="p")


def test_a_provider_declaring_positioning_is_recorded_as_positioning(tmp_path: Path) -> None:
	"""A vendor page ranking first is not evidence about the vendor (FR-074)."""
	spec = provider_spec(tmp_path, "positioning")
	hits = parse_search_results(
		{
			"results": [
				{"title": "Our platform", "url": "https://v/x", "category": "vendor"},
				{"title": "A study", "url": "https://j/x", "category": "general"},
			]
		},
		spec=spec,
		query="q",
	)
	assert hits[0].posture is SourcePosture.POSITIONING
	assert hits[1].posture is SourcePosture.EVIDENCE


def test_the_query_is_named_in_every_refusal(tmp_path: Path) -> None:
	"""A refusal that drops which query failed leaves nothing to act on."""
	spec = provider_spec(tmp_path, "malformed")
	with pytest.raises(SearchRefusal) as caught:
		parse_search_results({"results": [{}]}, spec=spec, query="the exact query")  # pyright: ignore[reportUnknownArgumentType]
	assert "the exact query" in str(caught.value)


# --------------------------------------------------------------------------- #
# the scan, end to end, over a real child process
# --------------------------------------------------------------------------- #


async def test_a_scan_records_what_the_provider_returned(tmp_path: Path) -> None:
	adapter = SearchAdapter(provider_spec(tmp_path, "ok"))
	scan = await adapter.search(("first query", "second query"), workdir=tmp_path / "run")
	assert [r.outcome for r in scan.results] == [SearchOutcome.OK, SearchOutcome.OK]
	assert scan.hit_count == 2
	assert scan.queries_answered == 2
	assert scan.exit_code == 0


async def test_a_provider_that_crashes_records_a_failed_query_not_a_raised_one(
	tmp_path: Path,
) -> None:
	"""Five of six queries answering is a usable scan; losing them would discard it."""
	adapter = SearchAdapter(provider_spec(tmp_path, "crash"))
	scan = await adapter.search(("q",), workdir=tmp_path / "run")
	assert scan.results[0].outcome is SearchOutcome.FAILED
	assert scan.results[0].exit_code == 3
	assert scan.results[0].error, "a failure whose cause was dropped is not actionable"


async def test_a_provider_writing_no_results_file_records_a_failed_query(tmp_path: Path) -> None:
	adapter = SearchAdapter(provider_spec(tmp_path, "silent"))
	scan = await adapter.search(("q",), workdir=tmp_path / "run")
	assert scan.results[0].outcome is SearchOutcome.FAILED
	assert "results.json" in (scan.results[0].error or "")


async def test_an_empty_result_set_is_an_answer_not_a_failure(tmp_path: Path) -> None:
	"""A search that found nothing answered the question."""
	adapter = SearchAdapter(provider_spec(tmp_path, "empty"))
	scan = await adapter.search(("q",), workdir=tmp_path / "run")
	assert scan.results[0].outcome is SearchOutcome.NO_RESULTS
	assert scan.queries_answered == 1
	assert scan.found_nothing is True


async def test_a_scan_with_a_failed_query_has_not_established_that_nothing_exists(
	tmp_path: Path,
) -> None:
	"""``found_nothing`` is false when a query failed — the scan does not know."""
	adapter = SearchAdapter(provider_spec(tmp_path, "crash"))
	scan = await adapter.search(("q",), workdir=tmp_path / "run")
	assert scan.found_nothing is False
	assert scan.unanswered_queries == ("q",)


def test_an_ok_result_with_no_hits_is_refused() -> None:
	"""Recording an empty return as success would inflate the hit count."""
	with pytest.raises(ValueError, match="ok with no hits"):
		SearchQueryResult(query="q", outcome=SearchOutcome.OK, hits=(), provider="p")


def test_a_failed_result_must_carry_its_reason() -> None:
	with pytest.raises(ValueError, match="no reason"):
		SearchQueryResult(query="q", outcome=SearchOutcome.FAILED, provider="p")


def test_a_scan_over_no_results_does_not_claim_to_have_found_nothing() -> None:
	"""An unstarted scan has established nothing, in either direction (NFR-024)."""
	scan = SearchScan(id=uuid7str(), provider="p", started_at=now())
	assert scan.found_nothing is False


# --------------------------------------------------------------------------- #
# the checks report and never gate
# --------------------------------------------------------------------------- #


def test_every_scan_check_passes_and_says_leads_not_evidence(tmp_path: Path) -> None:
	"""A thin set of leads is a measurement about the domain, not a defect in the run."""
	scan = SearchScan(
		id=uuid7str(),
		provider="synthetic-search",
		results=(
			SearchQueryResult(
				query="q",
				outcome=SearchOutcome.OK,
				hits=(SearchHit(rank=1, title="t", url="https://x.test/1", provider="p"),),
				provider="p",
			),
		),
		started_at=now(),
	)
	checks = scan_checks(scan, None)
	assert checks, "a scan is reported on"
	assert all(c.passed for c in checks), "these checks report; they never gate"
	joined = " ".join(c.detail for c in checks)
	assert VerificationStatus.REPORTED.value in joined
	assert "lead" in joined


def test_a_scan_that_found_nothing_says_so_as_a_measurement() -> None:
	scan = SearchScan(
		id=uuid7str(),
		provider="p",
		results=(SearchQueryResult(query="q", outcome=SearchOutcome.NO_RESULTS, provider="p"),),
		started_at=now(),
	)
	checks = scan_checks(scan, None)
	names = [c.name for c in checks]
	assert "the_search_found_nothing" in names
	assert all(c.passed for c in checks)


def test_a_failed_query_is_reported_as_not_established() -> None:
	scan = SearchScan(
		id=uuid7str(),
		provider="p",
		results=(
			SearchQueryResult(query="q", outcome=SearchOutcome.FAILED, provider="p", error="boom"),
		),
		started_at=now(),
	)
	detail = " ".join(c.detail for c in scan_checks(scan, None))
	assert "has not established that nothing exists" in detail


# --------------------------------------------------------------------------- #
# the scan reaches the ledger and the goal carries the competitive section
# --------------------------------------------------------------------------- #


async def test_a_scan_is_recorded_and_folds_back(tmp_path: Path) -> None:
	"""The scan is in the log and reads back off the fold, per goal (FR-174)."""
	from synthetic import synthetic_service

	service = synthetic_service(tmp_path / "home", tmp_path, "ok")
	await service.start("A reminder service that shows scheduled reminders.")
	goal = await service.current_goal()
	assert goal is not None
	service._searcher_spec = provider_spec(tmp_path, "ok")  # pyright: ignore[reportPrivateUsage]
	scan = await service.search(queries=("what do rivals do",), timeout=60.0)
	assert scan.provider == "synthetic-search"
	assert scan.goal_id == goal.id
	folded = await service.scans_for()
	assert [s.id for s in folded] == [scan.id]
	assert (await service.current_scan()) is not None
	checks = await service.search_gate()
	assert checks and all(c.passed for c in checks)


async def test_search_without_a_provider_is_refused_by_name(tmp_path: Path) -> None:
	from synthetic import synthetic_service

	service = synthetic_service(tmp_path / "home", tmp_path, "ok")
	await service.start("A reminder service that shows scheduled reminders.")
	with pytest.raises(SearchRefusal, match="no search provider is configured"):
		await service.search(queries=("q",))


async def test_search_without_a_goal_says_so(tmp_path: Path) -> None:
	from synthetic import synthetic_service

	service = synthetic_service(tmp_path / "home", tmp_path, "ok")
	with pytest.raises(KeyError, match="no goal yet"):
		await service.search(queries=("q",))


def test_the_research_goal_asks_for_the_competitive_artefact() -> None:
	"""The goal names the artefact competitive.py parses, and the subject it must echo."""
	from sofact.competitive import LEDGER_COMPETITORS_FILENAME
	from sofact.service import research_goal
	from sofact.views import ResearchAllowance, ResearchMode

	goal = research_goal(
		"a payments platform",
		mode=ResearchMode.DEEP,
		allowance=ResearchAllowance(
			intent_clauses=1, max_sources=5, max_model_calls=5, max_wall_clock_seconds=300.0
		),
	)
	assert LEDGER_COMPETITORS_FILENAME in goal
	assert "echo the Subject above, verbatim" in goal
	assert "selection_criterion" in goal
	assert "inventing rivals to fill it" in goal
