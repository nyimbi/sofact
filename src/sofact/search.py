"""FR-174 — web search as a capability of this product, and the queries as SoFact's own text.

The operator asked for a system that "must include web search and deep research to find
answers and competitive information". SoFact already dispatches deep research (ADR-0021,
FR-167): it authors the goal and a harness performs it. What it did not have is any way to
*look something up* — to take a question it has written and put it to a search provider
itself, before or beside the research dispatch, so that a run which needs a fact can go and
get it rather than only describing the fact it wishes it had.

**SoFact authors the queries; the provider answers them.** That division is the whole
design, and it is the same one :func:`sofact.service.research_goal` makes about clause ids.
A provider asked "what should I search for?" chooses its own subject list, and the check
that the right things were searched then measures the provider against itself. Here the
queries are composed from the goal's own elicitation answers, in the goal's own words, and
they are written into the log before any provider runs — so "what was asked" is answerable
from the ledger alone, without re-running anything.

**The provider is declared, not bundled.** An argv template in a JSON table, resolved by
name, launched as a child process, judged by the JSON it wrote — :class:`~sofact.harness.
HarnessSpec`'s shape, for its reason: this product opens no socket to the open web of its
own accord, and the fleet already runs a SearXNG instance, so the useful thing to ship is
the *shape* of a provider rather than a client for one. There is **no built-in provider**,
and that is a decision rather than an omission: an engine's address is a deployment's
business, and a built-in one would be this factory choosing whose index its research
rests on.

**A hit is a lead, not a source.** Every hit is recorded at
:attr:`~sofact.views.VerificationStatus.REPORTED` — the weakest rung — and
:class:`~sofact.views.SearchHit` refuses to be constructed at ``CONTENT_VERIFIED`` at all.
A provider returns a title, a url and a snippet it chose and possibly generated; promoting
that to evidence would let a machine-written excerpt be cited as a page a human read, which
is precisely the substitution :class:`~sofact.views.VerificationStatus`'s own docstring
exists to prevent. The scan widens what the research phase *can* go and verify; it never
stands in for the verifying.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from time import monotonic
from typing import Final, TypeGuard, cast

from sofact._uuid7 import uuid7str
from sofact.views import (
	GateCheck,
	SearchHit,
	SearchOutcome,
	SearchQueryResult,
	SearchScan,
	SourceLedger,
	SourcePosture,
	VerificationStatus,
	now,
)

__all__ = [
	"SEARCHERS",
	"ConfiguredSearchAdapter",
	"SearchRefusal",
	"SearcherSpec",
	"authored_queries",
	"load_searcher_specs",
	"parse_search_results",
	"scan_checks",
	"searcher_spec_for",
]

SEARCHERS: Final[dict[str, SearcherSpec]] = {}
"""The built-in table, empty for :data:`~sofact.transcribe.TRANSCRIBERS`'s reason (FR-174).

No search provider is a dependency of this product, and a built-in entry would name an
engine whose index, coverage and ranking this factory has no way to characterise. A
deployment registers its own with ``SOFACT_SEARCHER_SPECS``.
"""


class SearchRefusal(Exception):
	"""A provider could not be resolved, launched, or read. Never a silent empty result."""


@dataclass(frozen=True, slots=True)
class SearcherSpec:
	"""A deployment's search configuration (FR-174).

	``argv`` carries ``{query}`` and ``{workspace}``, and the results are read from the
	**file the provider wrote** rather than from stdout. That is
	:class:`~sofact.transcribe.TranscriberSpec`'s reason one layer along: a search tool
	prints progress and warnings beside its payload, and a reader that scraped stdout
	would be guessing where the JSON began.
	"""

	name: str
	argv: tuple[str, ...]
	"""How to run the provider, as a template. ``{query}`` and ``{workspace}`` are the slots."""

	results_glob: str
	"""The JSON file the provider writes its results to, relative to the working directory.

	A glob rather than a fixed name because several engines derive the output name from a
	hash of the query.
	"""

	hits_key: str = "results"
	"""The key path holding the list of hits in that JSON."""

	title_key: str = "title"
	url_key: str = "url"
	snippet_key: str = "content"
	"""Where the three fields sit in one hit. Defaults are SearXNG's, since that is the
	engine this was written against; any provider is described by naming its own."""

	posture_key: str = ""
	"""The key naming the hit's posture, if the provider offers one. Empty means every hit
	is recorded ``EVIDENCE`` and left for the research phase to characterise."""

	positioning_values: tuple[str, ...] = ()
	"""The values of ``posture_key`` that mean positioning (FR-074)."""

	date_key: str = ""
	expect_exit_code: int = 0
	is_remote: bool = True
	"""Whether the query leaves this machine. Recorded, because a query is composed from
	the operator's own words about their system and an operator is entitled to know that
	it was transmitted."""

	max_results: int = 0
	"""The cap asked of the provider, or ``0`` for its own default."""

	notes: str = ""

	def __post_init__(self) -> None:
		assert self.name.strip(), "a searcher spec names itself"
		assert self.argv, "a searcher spec names the command it runs"
		joined = " ".join(self.argv)
		assert "{query}" in joined, (
			f"the {self.name} argv must name the query, or the provider is run on nothing "
			"and the results are for no question"
		)
		assert self.results_glob, (
			f"the {self.name} spec names no results file, so there is nothing to read the "
			"hits from and stdout is not an artefact protocol"
		)
		assert bool(self.posture_key) == bool(self.positioning_values), (
			f"the {self.name} spec names a posture key without the values that mean "
			"positioning (or the reverse), so the field would be read and never decide"
		)

	@classmethod
	def from_mapping(cls, name: str, payload: Mapping[str, object]) -> SearcherSpec:
		"""Build a spec from a JSON-shaped mapping, refusing unknown fields by name.

		A misspelled ``url_key`` that silently fell back to the default would read every
		hit's url as absent, and the scan would record a page of well-titled hits that
		point nowhere — the failure mode :class:`~sofact.views.SearchHit` requires a url
		to prevent.
		"""
		declared = {field.name for field in fields(cls)}
		unknown = sorted(set(payload) - declared)
		if unknown:
			raise ValueError(f"searcher {name!r}: unknown field(s) {unknown}")
		missing = [field for field in ("argv", "results_glob") if field not in payload]
		if missing:
			raise ValueError(f"searcher {name!r}: missing field(s) {missing}")
		changes: dict[str, object] = {"name": name}
		for field in (
			"results_glob",
			"hits_key",
			"title_key",
			"url_key",
			"snippet_key",
			"posture_key",
			"date_key",
			"notes",
		):
			if field in payload:
				changes[field] = _text(payload[field], field, name)
		for field in ("expect_exit_code", "max_results"):
			if field in payload:
				changes[field] = _int(payload[field], field, name)
		if "is_remote" in payload:
			value = payload["is_remote"]
			if not isinstance(value, bool):
				raise ValueError(f"searcher {name!r}: is_remote must be a boolean")
			changes["is_remote"] = value
		if "positioning_values" in payload:
			changes["positioning_values"] = _texts(
				payload["positioning_values"], "positioning_values", name
			)
		changes["argv"] = _texts(payload["argv"], "argv", name)
		return cls(**changes)  # pyright: ignore[reportArgumentType]


def _text(value: object, field: str, name: str) -> str:
	if not isinstance(value, str):
		raise ValueError(f"searcher {name!r}: {field} must be a string")
	return value


def _int(value: object, field: str, name: str) -> int:
	if isinstance(value, bool) or not isinstance(value, int):
		raise ValueError(f"searcher {name!r}: {field} must be an integer")
	return value


def _texts(value: object, field: str, name: str) -> tuple[str, ...]:
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError(f"searcher {name!r}: {field} must be an array of strings")
	items = cast("Sequence[object]", value)
	out: list[str] = []
	for item in items:
		if not isinstance(item, str):
			raise ValueError(f"searcher {name!r}: {field} must contain only strings")
		out.append(item)
	return tuple(out)


def _str_keyed(value: object) -> TypeGuard[Mapping[str, object]]:
	if not isinstance(value, dict):
		return False
	obj = cast("Mapping[object, object]", value)
	return all(isinstance(key, str) for key in obj)


def load_searcher_specs(path: Path) -> dict[str, SearcherSpec]:
	"""Read a searcher table from a JSON file (FR-174).

	Two shapes, as :func:`~sofact.harness.load_specs` accepts: ``{"searchers": {...}}`` and
	a bare ``{name: {...}}``.
	"""
	try:
		text = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read searcher table {path}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{path}: not valid JSON: {exc}") from exc
	if not _str_keyed(raw):
		raise ValueError(f"{path}: expected a JSON object")
	body: object = raw["searchers"] if set(raw) == {"searchers"} else raw
	if not _str_keyed(body):
		raise ValueError(f"{path}: expected an object of searcher specs under 'searchers'")
	specs: dict[str, SearcherSpec] = {}
	for name, payload in body.items():
		if not _str_keyed(payload):
			raise ValueError(f"{path}: searcher {name!r} must be an object")
		specs[name] = SearcherSpec.from_mapping(name, payload)
	if not specs:
		raise ValueError(f"{path}: no searchers; an empty table names no provider to ask")
	return specs


def searcher_spec_for(name: str | None, specs: Mapping[str, SearcherSpec]) -> SearcherSpec:
	"""Resolve one provider by name, refusing an unknown one by name."""
	if not specs:
		raise SearchRefusal(
			"no search provider is configured, and this build ships none: set "
			"SOFACT_SEARCHER_SPECS to a JSON table naming one, or SOFACT_SEARCHER to a name "
			"in such a table (FR-174)"
		)
	if name is None:
		if len(specs) == 1:
			return next(iter(specs.values()))
		known = ", ".join(sorted(specs))
		raise SearchRefusal(
			f"{len(specs)} search providers are configured ({known}); name one explicitly"
		)
	if name not in specs:
		known = ", ".join(sorted(specs))
		raise SearchRefusal(f"unknown search provider {name!r}; configured: {known}")
	return specs[name]


def authored_queries(
	statement: str,
	*,
	dimensions: Mapping[str, str] | None = None,
	extra: Sequence[str] = (),
	limit: int = 6,
) -> tuple[str, ...]:
	"""The queries SoFact will ask, composed before any provider runs (FR-174).

	Deterministic and model-free, so two calls over one goal produce the same query list
	and the log's record of what was asked is reproducible. The statement is searched as
	written, and each answered dimension contributes one query built from the operator's
	own words rather than from a template's — a query the operator did not write is a
	question nobody asked, and the results would answer it anyway.

	The list is deduplicated in order and truncated to ``limit``, because a provider's
	rate limit is a real constraint and the first queries are the ones composed from the
	goal itself.
	"""
	assert limit >= 1, "a query list of nothing asks nothing"
	seen: list[str] = []
	for candidate in (statement.strip(), *(extra or ())):
		if candidate and candidate not in seen:
			seen.append(candidate)
	for value in (dimensions or {}).values():
		text = value.strip()
		if text and text not in seen:
			seen.append(text)
	return tuple(seen[:limit])


def _keyed(payload: Mapping[str, object], key: str) -> object | None:
	"""Walk a dotted key path, returning ``None`` when it is absent rather than raising.

	Absent is a legitimate answer for an optional field; the *required* three are checked
	by :func:`parse_search_results`, which refuses by name.
	"""
	current: object = payload
	for part in key.split("."):
		if not isinstance(current, dict):
			return None
		mapping = cast("Mapping[str, object]", current)
		if part not in mapping:
			return None
		current = mapping[part]
	return current


def _hit_text(hit: Mapping[str, object], key: str) -> str | None:
	if not key:
		return None
	value = _keyed(hit, key)
	if value is None:
		return None
	if not isinstance(value, str) or not value.strip():
		return None
	return value.strip()


def _hit_date(hit: Mapping[str, object], key: str) -> date | None:
	if not key:
		return None
	value = _keyed(hit, key)
	if not isinstance(value, str) or not value.strip():
		return None
	try:
		return date.fromisoformat(value.strip()[:10])
	except ValueError:
		return None


def parse_search_results(
	payload: object,
	*,
	spec: SearcherSpec,
	query: str,
) -> tuple[SearchHit, ...]:
	"""One provider's answer to one query, read fail-closed (FR-174).

	**A hit with no url is refused, and that refusal is not a formality.** A result is
	something an operator can go and look at; a title with no address is a claim that
	cannot be checked, and admitting one would put an unlookupable entry into the scan the
	research phase draws its leads from — the same defect
	:class:`~sofact.views.RivalSystem` refuses for a competitor.

	A malformed hit among well-formed ones raises rather than being skipped, because
	skipping is how a scan silently reports fewer results than the provider returned and
	the count stops being a measurement.
	"""
	if not isinstance(payload, dict):
		raise SearchRefusal(
			f"search provider {spec.name!r}: the results file for {query!r} is a "
			f"{type(payload).__name__}, not an object"
		)
	document = cast("Mapping[str, object]", payload)
	raw_hits = _keyed(document, spec.hits_key) if spec.hits_key else document
	if raw_hits is None:
		raise SearchRefusal(
			f"search provider {spec.name!r}: the results file for {query!r} has no "
			f"{spec.hits_key!r} key, so there is no list of hits to read "
			f"(keys: {sorted(document)})"
		)
	if not isinstance(raw_hits, list):
		raise SearchRefusal(
			f"search provider {spec.name!r}: {spec.hits_key!r} for {query!r} is a "
			f"{type(raw_hits).__name__}, not a list"
		)
	hits: list[SearchHit] = []
	for rank, raw in enumerate(cast("list[object]", raw_hits), start=1):
		if not isinstance(raw, dict):
			raise SearchRefusal(
				f"search provider {spec.name!r}: hit {rank} for {query!r} is a "
				f"{type(raw).__name__}, not an object"
			)
		hit = cast("Mapping[str, object]", raw)
		url = _hit_text(hit, spec.url_key)
		if url is None:
			raise SearchRefusal(
				f"search provider {spec.name!r}: hit {rank} for {query!r} has no "
				f"{spec.url_key!r}: a result nobody can look up is not a lead, and "
				"admitting it would put an uncheckable entry into the scan (FR-174)"
			)
		title = _hit_text(hit, spec.title_key) or url
		posture = SourcePosture.EVIDENCE
		if spec.posture_key:
			raw_posture = _hit_text(hit, spec.posture_key)
			if raw_posture is not None and raw_posture.lower() in {
				v.lower() for v in spec.positioning_values
			}:
				posture = SourcePosture.POSITIONING
		hits.append(
			SearchHit(
				rank=rank,
				title=title,
				url=url,
				snippet=_hit_text(hit, spec.snippet_key) or "",
				provider=spec.name,
				posture=posture,
				published=_hit_date(hit, spec.date_key),
			)
		)
	return tuple(hits)


def _read_results(workdir: Path, spec: SearcherSpec, query: str) -> tuple[SearchHit, ...]:
	"""The hits, from the artefact the spec names."""
	matches = sorted(workdir.glob(spec.results_glob))
	if not matches:
		raise SearchRefusal(
			f"search provider {spec.name!r} wrote no file matching {spec.results_glob!r} "
			f"in {workdir}: the query {query!r} produced no results file to read"
		)
	artefact = matches[-1]
	try:
		raw: object = json.loads(artefact.read_text(encoding="utf-8"))
	except OSError as exc:
		raise SearchRefusal(f"cannot read {artefact}: {exc}") from exc
	except ValueError as exc:
		raise SearchRefusal(f"{artefact}: not valid JSON: {exc}") from exc
	return parse_search_results(raw, spec=spec, query=query)


@dataclass(frozen=True, slots=True)
class ConfiguredSearchAdapter:
	"""Runs one declared provider over a set of authored queries (FR-174)."""

	spec: SearcherSpec

	def build_argv(self, query: str, workdir: Path) -> tuple[str, ...]:
		"""The argv to launch, with the slots filled and nothing else substituted."""
		return tuple(
			part.replace("{query}", query).replace("{workspace}", str(workdir))
			for part in self.spec.argv
		)

	async def _one(
		self,
		query: str,
		*,
		workdir: Path,
		timeout: float,
	) -> SearchQueryResult:
		"""Run one query and record what it returned, including not having returned."""
		run_dir = workdir / uuid7str()
		run_dir.mkdir(parents=True, exist_ok=True)
		argv = self.build_argv(query, run_dir)
		started = monotonic()
		try:
			proc = await asyncio.create_subprocess_exec(
				*argv,
				cwd=str(run_dir),
				stdin=asyncio.subprocess.DEVNULL,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
			)
		except OSError as exc:
			# A launch failure is a *failed query*, not a raised exception: five of six
			# queries answering is a usable scan, and losing the five to record the one
			# would discard the measurement to report the error.
			return SearchQueryResult(
				query=query,
				outcome=SearchOutcome.FAILED,
				provider=self.spec.name,
				exit_code=None,
				error=f"{type(exc).__name__}: {exc}",
			)
		try:
			_, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
		except TimeoutError:
			proc.kill()
			await proc.wait()
			return SearchQueryResult(
				query=query,
				outcome=SearchOutcome.FAILED,
				provider=self.spec.name,
				exit_code=None,
				error=f"timed out after {timeout:.0f}s",
				duration_seconds=monotonic() - started,
			)
		duration = monotonic() - started
		stderr = stderr_b.decode("utf-8", errors="replace").strip()[-2000:]
		if proc.returncode != self.spec.expect_exit_code:
			return SearchQueryResult(
				query=query,
				outcome=SearchOutcome.FAILED,
				provider=self.spec.name,
				exit_code=proc.returncode,
				error=stderr or f"exit code {proc.returncode}",
				duration_seconds=duration,
			)
		try:
			hits = _read_results(run_dir, self.spec, query)
		except SearchRefusal as exc:
			return SearchQueryResult(
				query=query,
				outcome=SearchOutcome.FAILED,
				provider=self.spec.name,
				exit_code=proc.returncode,
				error=str(exc),
				duration_seconds=duration,
			)
		return SearchQueryResult(
			query=query,
			outcome=SearchOutcome.OK if hits else SearchOutcome.NO_RESULTS,
			hits=hits,
			provider=self.spec.name,
			exit_code=proc.returncode,
			error=stderr or None,
			duration_seconds=duration,
		)

	async def search(
		self,
		queries: Sequence[str],
		*,
		workdir: Path,
		timeout: float = 120.0,
		goal_id: str | None = None,
	) -> SearchScan:
		"""Ask the provider every authored query and record the scan (FR-174).

		The queries run in order rather than concurrently: a provider is usually a shared
		service with a rate limit, and a burst is how a scan gets throttled into a page of
		failures that then read as a domain with no results.
		"""
		assert queries, "a scan over no queries asks nothing"
		workdir.mkdir(parents=True, exist_ok=True)
		started_at = now()
		results: list[SearchQueryResult] = []
		for query in queries:
			results.append(await self._one(query, workdir=workdir, timeout=timeout))
		return SearchScan(
			id=uuid7str(),
			goal_id=goal_id,
			provider=self.spec.name,
			results=tuple(results),
			started_at=started_at,
			finished_at=now(),
			exit_code=0 if all(r.exit_code == 0 for r in results) else None,
		)


def scan_checks(
	scan: SearchScan,
	ledger: SourceLedger | None,
) -> tuple[GateCheck, ...]:
	"""What a scan can and cannot be read as (FR-174).

	Every check passes, for :func:`sofact.competitive.competitor_checks`'s reason: this
	phase produces *leads*, and a thin set of leads is a measurement about the domain
	rather than a defect in the run. Refusing the phase over one would teach a provider —
	or an operator — to inflate it.

	The one thing these checks exist to say out loud is the count that separates "the web
	has nothing" from "the provider did not answer", because those two look identical in
	a hit count and call for opposite responses.
	"""
	known = {s.url for s in (ledger.sources if ledger is not None else ()) if s.url}
	seen_urls = {h.url for h in scan.hits}
	novel = tuple(u for u in seen_urls if u not in known)
	checks: list[GateCheck] = [
		GateCheck(
			name="search_queries_are_sofacts_own",
			passed=True,
			detail=(
				f"{len(scan.results)} query/queries were authored by SoFact from the goal's "
				"own words before any provider ran, and recorded verbatim: the provider "
				"answered questions it was handed rather than choosing its own subject "
				"list (FR-174)"
			),
		),
		GateCheck(
			name="hits_are_leads_not_evidence",
			passed=True,
			detail=(
				f"all {scan.hit_count} hit(s) are recorded "
				f"{VerificationStatus.REPORTED.value}, the weakest rung: a provider returns "
				"a title, a url and a snippet it chose, and no part of this phase read the "
				"page. The scan widens what research can go and verify; it never stands in "
				"for the verifying (FR-174, FR-069)"
			),
		),
		GateCheck(
			name="every_query_was_answered",
			passed=True,
			detail=(
				f"{scan.queries_answered} of {len(scan.results)} query/queries were "
				"answered"
				+ (
					f", and {len(scan.unanswered_queries)} failed: "
					+ ", ".join(repr(q) for q in scan.unanswered_queries)
					+ ". A failed query has not established that nothing exists, only that "
					"this scan does not know — the two are different findings and the count "
					"is what distinguishes them (FR-174, NFR-024)"
					if scan.unanswered_queries
					else ""
				)
			),
		),
		GateCheck(
			name="hits_the_ledger_does_not_hold",
			passed=True,
			detail=(
				f"{len(novel)} of {len(seen_urls)} distinct hit url(s) name no source the "
				"ledger holds: a search result is a place to look, and until the research "
				"phase reads it and writes a source entry, it is a lead rather than "
				"evidence (FR-174, FR-070)"
			),
		),
	]
	if scan.found_nothing:
		checks.append(
			GateCheck(
				name="the_search_found_nothing",
				passed=True,
				detail=(
					"every query was answered and none returned a hit. That is a measurement "
					"about the domain rather than a failure of the run, and it is reported "
					"as one so that nobody is pushed toward inventing results to avoid it "
					"(FR-174, NFR-024)"
				),
			)
		)
	return tuple(checks)
