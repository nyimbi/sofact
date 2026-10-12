"""P1 — the source ledger, read from the producer's artefacts (FR-070).

The spec calls the hand-built ledger in ``docs/sources/`` the **reference
implementation** of this phase and says its structure "is the specification for the
automation". So this module is a transcription, not an invention: one markdown file per
source with YAML front-matter and four fixed body sections, a machine-readable claims
file, and the judgements the hand ledger recorded by hand promoted to types that can
refuse.

**The producer's artefacts are untrusted, so every refusal here fails closed.** A
front-matter line that is neither ``key: value`` nor a list item raises rather than
being skipped; a block scalar raises rather than parsing as the literal ``"|"``; a
document with no critique section raises rather than becoming a source with an empty
one. The failure mode this avoids is a parser that drops what it cannot read and
reports a clean ledger over the remains — a subset predicate failing toward "clean",
which is the shape of every silent gate failure in this project's history.

**What is not here: attributing spec FR ids to sources.** The obvious use for a parsed
spec is to derive ``supports`` by walking it for ``[S01]``-style citations, and it was
refused after measuring: of the 21 sources the spec cites, **5 cite only in prose
outside any requirement**, so a markdown walk would attribute them to nothing and
report a completeness the artefact does not have. The edge FR-070 actually names runs
source-to-claim *inside the ledger*, and that is what :meth:`SourceLedger.resting_on`
derives.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any, Final, cast

from sofact.views import (
	Claim,
	ClaimKind,
	ClauseClassification,
	Contradiction,
	GateCheck,
	ResearchClassification,
	ResearchVerdict,
	Source,
	SourceLedger,
	SourcePosture,
	VerificationStatus,
	now,
)

__all__ = [
	"LEDGER_CLAIMS_FILENAME",
	"LEDGER_CLASSIFICATION_FILENAME",
	"LEDGER_SOURCES_DIRNAME",
	"classification_checks",
	"ledger_checks",
	"parse_claim_document",
	"parse_classification",
	"parse_ledger",
	"parse_source_document",
]

LEDGER_SOURCES_DIRNAME: Final = "research-sources"
"""Where a research session leaves one document per source."""

LEDGER_CLAIMS_FILENAME: Final = "research-claims.json"
"""Where it leaves the claims and the contradictions between them."""

LEDGER_CLASSIFICATION_FILENAME: Final = "research-classification.json"
"""Where it leaves FR-068's verdict on each intent clause.

A separate file from the claims, because the two answer different questions: the claims
are what the research *found* and the classification is what it *concluded about the
goal*. Folding them into one file would make "the producer wrote no conclusions" and
"the producer concluded nothing" the same bytes on disk.
"""

_FRONT_MATTER: Final = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n?", re.DOTALL)
_HEADING: Final = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
_BLOCK_SCALARS: Final = frozenset({"|", ">", "|-", ">-", "|+", ">+"})

_PRECIS_HEADINGS: Final = ("precis", "summary")
_CRITIQUE_HEADINGS: Final = ("concerns / information quality", "concerns", "information quality")

_CLAIM_KEYS: Final = frozenset(
	{"id", "statement", "kind", "opinion", "source_ids", "superseded_by", "expires"}
)
_CONTRADICTION_KEYS: Final = frozenset({"id", "statement", "source_ids", "resolution"})
_CLASSIFICATION_KEYS: Final = frozenset(
	{"clause_id", "statement", "verdict", "rationale", "evidence", "settled_by"}
)


def _scalar(raw: str) -> str:
	"""One front-matter value, unquoted. ``null``/``~`` become the empty string.

	Empty rather than ``None`` so the return type stays one thing, and because an
	explicitly null field and an omitted one mean the same to every reader downstream:
	the ledger does not have it.
	"""
	value = raw.strip()
	if value in _BLOCK_SCALARS:
		raise ValueError(
			f"front-matter value {value!r} opens a block scalar, which this parser does "
			"not read; write it as one quoted line rather than a silently-misread block"
		)
	if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
		return value[1:-1]
	if value in {"null", "~", "None"}:
		return ""
	return value


def _front_matter(text: str) -> tuple[dict[str, str | tuple[str, ...]], str]:
	"""The leading ``---`` block as fields, plus the body after it.

	Handles exactly the subset ``docs/sources/`` uses: ``key: value``, quoted values,
	inline ``[a, b]`` lists, and ``key:`` followed by ``  - item`` lines. Anything else
	raises, naming the line — see the module docstring for why that is the point.
	"""
	match = _FRONT_MATTER.match(text)
	if match is None:
		raise ValueError(
			"no front-matter: the document must open with a '---' line, the fields, and "
			"a closing '---' line"
		)
	fields: dict[str, str | tuple[str, ...]] = {}
	key: str | None = None
	items: list[str] = []
	for number, raw in enumerate(match.group("body").splitlines(), start=2):
		line = raw.rstrip()
		if not line.strip() or line.lstrip().startswith("#"):
			continue
		if line.lstrip().startswith("- "):
			if key is None:
				raise ValueError(f"line {number}: a list item before any key")
			items.append(_scalar(line.lstrip()[2:]))
			continue
		if key is not None and items:
			fields[key] = tuple(items)
			items = []
		name, separator, value = line.partition(":")
		if not separator or not name.strip() or " " in name.strip():
			raise ValueError(f"line {number}: {line!r} is neither 'key: value' nor a list item")
		key = name.strip()
		stripped = value.strip()
		if stripped.startswith("["):
			inner = stripped.strip("[]").strip()
			fields[key] = tuple(_scalar(part) for part in inner.split(",") if part.strip())
			key = None
			continue
		fields[key] = _scalar(stripped)
	if key is not None and items:
		fields[key] = tuple(items)
	return fields, text[match.end() :]


def _sections(body: str) -> dict[str, str]:
	"""Level-two sections by lowercased title. A repeated title keeps the first."""
	found: dict[str, str] = {}
	matches = list(_HEADING.finditer(body))
	for position, heading in enumerate(matches):
		end = matches[position + 1].start() if position + 1 < len(matches) else len(body)
		found.setdefault(heading.group("title").strip().lower(), body[heading.end() : end].strip())
	return found


def _section(sections: Mapping[str, str], candidates: tuple[str, ...]) -> str | None:
	"""The first section matching ``candidates``, exactly then by prefix.

	Prefix matching is what lets ``docs/sources/``'s ``## Key claims (observed, not
	reported)`` answer a request for ``key claims``: the hand ledger qualifies its
	headings with how the claims were obtained, and a reader that required an exact
	title would find the qualified ones missing.
	"""
	for candidate in candidates:
		if candidate in sections:
			return sections[candidate]
	for candidate in candidates:
		for title, text in sections.items():
			if title.startswith(candidate):
				return text
	return None


def _text(fields: Mapping[str, str | tuple[str, ...]], key: str) -> str | None:
	"""One front-matter field as text, or ``None`` when absent, empty, or a list.

	A list asked for as text is a producer error rather than a value: the ledger's own
	fields that hold lists are read through :func:`_items`, and a scalar field carrying
	one means the document disagrees with itself. Returning ``None`` leaves the caller's
	own required-field refusal to name it.
	"""
	value = fields.get(key)
	if value is None or isinstance(value, tuple):
		return None
	return value or None


def _day(fields: Mapping[str, str | tuple[str, ...]], key: str) -> date | None:
	"""One front-matter field as a date, or ``None``.

	A value that is not an ISO date raises rather than being dropped: a retrieval date
	the ledger cannot read is a provenance claim it cannot make, and silently losing it
	would leave the entry looking fully sourced.
	"""
	raw = _text(fields, key)
	if raw is None:
		return None
	try:
		return date.fromisoformat(raw)
	except ValueError as exc:
		raise ValueError(f"{key}: {raw!r} is not an ISO date (YYYY-MM-DD)") from exc


def _enum[E](enum: type[E], raw: str | None, key: str, *, default: E) -> E:
	"""A front-matter field as one member of ``enum``, by value or by name.

	Generic rather than ``StrEnum``-bound because :class:`~sofact.views.SourcePosture`
	and friends are enums of strings, and a ``type[StrEnum]`` parameter would lose the
	member type at every call site.
	"""
	if raw is None:
		return default
	members: list[Any] = list(enum)  # type: ignore[call-overload]
	for member in members:
		if member.value == raw:
			return member  # type: ignore[no-any-return]
	for member in members:
		if str(member.name).lower().replace("_", "-") == raw.lower():
			return member  # type: ignore[no-any-return]
	allowed = ", ".join(str(member.value) for member in members)
	raise ValueError(f"{key}: {raw!r} is not one of {allowed}")


def parse_source_document(text: str, *, fallback_id: str) -> Source:
	"""One source entry from one document (FR-070).

	``fallback_id`` is used when the document carries no ``id``: the file's ordinal in
	the directory, so a producer that omitted the citation key still gets addressable
	rows rather than a ledger nothing can point at.
	"""
	fields, body = _front_matter(text)
	sections = _sections(body)
	precis = _section(sections, _PRECIS_HEADINGS)
	critique = _section(sections, _CRITIQUE_HEADINGS)
	title = _text(fields, "title")
	if title is None:
		raise ValueError("a source needs a title: an untitled entry cannot be cited")
	if precis is None:
		raise ValueError(
			f"source {_text(fields, 'id') or fallback_id} has no '## Precis' section: what "
			"the source says is the entry (FR-070)"
		)
	if critique is None:
		raise ValueError(
			f"source {_text(fields, 'id') or fallback_id} has no '## Concerns / information "
			"quality' section: a ledger entry without the judgement about the source is a "
			"link, not evidence (FR-070)"
		)
	confidence = _text(fields, "confidence")
	if confidence is None:
		raise ValueError(
			f"source {_text(fields, 'id') or fallback_id} carries no confidence: how much "
			"weight a source can bear is the field that decides whether it may be cited "
			"(FR-069)"
		)
	slug = _text(fields, "slug") or _text(fields, "id") or fallback_id
	return Source(
		id=_text(fields, "id") or fallback_id,
		slug=slug,
		title=title,
		type=_text(fields, "type") or "unclassified",
		url=_text(fields, "url"),
		retrieved=_day(fields, "retrieved"),
		verification=_enum(
			VerificationStatus,
			_text(fields, "verification"),
			"verification",
			default=VerificationStatus.REPORTED,
		),
		confidence=confidence,
		posture=_enum(
			SourcePosture, _text(fields, "posture"), "posture", default=SourcePosture.EVIDENCE
		),
		precis=precis,
		critique=critique,
		expires=_day(fields, "expires"),
		superseded_by=_text(fields, "superseded_by"),
	)


def _unknown_keys(mapping: Mapping[str, Any], allowed: frozenset[str], *, what: str) -> None:
	extra = sorted(set(mapping) - allowed)
	if extra:
		raise ValueError(
			f"{what} carries unknown key(s) {extra}: a field this build does not read is a "
			"judgement the producer made that the ledger would silently drop"
		)


def _string_list(value: object, *, key: str) -> tuple[str, ...]:
	if value is None:
		return ()
	if not isinstance(value, list):
		raise ValueError(f"{key}: expected a list, got {type(value).__name__}")
	items: list[str] = []
	for item in cast("list[object]", value):
		if not isinstance(item, str) or not item.strip():
			raise ValueError(f"{key}: every entry must be a non-empty string, got {item!r}")
		items.append(item.strip())
	return tuple(items)


def _optional_string(value: object, *, key: str) -> str | None:
	if value is None:
		return None
	if not isinstance(value, str) or not value.strip():
		raise ValueError(f"{key}: expected a non-empty string or null, got {value!r}")
	return value.strip()


def _object(value: object, *, what: str) -> Mapping[str, Any]:
	"""``value`` as a JSON object, or a refusal naming what it was instead."""
	if not isinstance(value, dict):
		raise ValueError(f"{what} must be an object, got {type(value).__name__}")
	return cast("Mapping[str, Any]", value)


def parse_claim_document(payload: object) -> tuple[tuple[Claim, ...], tuple[Contradiction, ...]]:
	"""The claims and contradictions from ``research-claims.json`` (FR-068, FR-073).

	Every key is checked and every unknown one refused, because a producer's judgement
	that the ledger drops is worse than a producer's error the ledger reports: the first
	is invisible and the second is not.
	"""
	document = _object(payload, what="the claims file")
	_unknown_keys(document, frozenset({"claims", "contradictions"}), what="the claims file")
	claims: list[Claim] = []
	for raw in _mapping_list(document.get("claims"), key="claims"):
		_unknown_keys(raw, _CLAIM_KEYS, what="a claim")
		claim_id = _optional_string(raw.get("id"), key="claim id")
		statement = _optional_string(raw.get("statement"), key="claim statement")
		if claim_id is None or statement is None:
			raise ValueError("a claim needs both an id and a statement")
		claims.append(
			Claim(
				id=claim_id,
				statement=statement,
				kind=_enum(
					ClaimKind,
					_optional_string(raw.get("kind"), key="claim kind"),
					"kind",
					default=ClaimKind.SUPPORTING,
				),
				opinion=_flag(raw.get("opinion"), key="claim opinion"),
				source_ids=_string_list(raw.get("source_ids"), key="claim source_ids"),
				superseded_by=_optional_string(raw.get("superseded_by"), key="claim superseded_by"),
				expires=_day_from(raw.get("expires"), key="claim expires"),
			)
		)
	contradictions: list[Contradiction] = []
	for raw in _mapping_list(document.get("contradictions"), key="contradictions"):
		_unknown_keys(raw, _CONTRADICTION_KEYS, what="a contradiction")
		found_id = _optional_string(raw.get("id"), key="contradiction id")
		statement = _optional_string(raw.get("statement"), key="contradiction statement")
		if found_id is None or statement is None:
			raise ValueError("a contradiction needs both an id and a statement")
		contradictions.append(
			Contradiction(
				id=found_id,
				statement=statement,
				source_ids=_string_list(raw.get("source_ids"), key="contradiction source_ids"),
				resolution=_optional_string(raw.get("resolution"), key="contradiction resolution"),
			)
		)
	return tuple(claims), tuple(contradictions)


def _flag(value: object, *, key: str) -> bool:
	"""A JSON boolean, refusing a truthy stand-in.

	``bool("false")`` is ``True``, so coercing here would turn a producer writing the
	string ``"false"`` into an opinion labelled as sourced — the exact inversion the
	field exists to prevent.
	"""
	if value is None:
		return False
	if not isinstance(value, bool):
		raise ValueError(f"{key}: expected true or false, got {value!r}")
	return value


def _mapping_list(value: object, *, key: str) -> tuple[Mapping[str, Any], ...]:
	"""A JSON array of objects, or ``()`` when the key is absent."""
	if value is None:
		return ()
	if not isinstance(value, list):
		raise ValueError(f"{key}: expected a list, got {type(value).__name__}")
	entries: list[Mapping[str, Any]] = []
	for item in cast("list[object]", value):
		entries.append(_object(item, what=f"{key} entry"))
	return tuple(entries)


def _day_from(raw: object, *, key: str) -> date | None:
	"""A JSON ISO date, or ``None``. An unparseable one is refused, not dropped."""
	if raw is None:
		return None
	if not isinstance(raw, str):
		raise ValueError(f"{key}: expected an ISO date string, got {raw!r}")
	try:
		return date.fromisoformat(raw)
	except ValueError as exc:
		raise ValueError(f"{key}: {raw!r} is not an ISO date (YYYY-MM-DD)") from exc


def parse_ledger(
	*,
	goal_id: str,
	query: str,
	documents: Iterable[str],
	claims: object | None = None,
	version: int = 1,
) -> SourceLedger:
	"""A whole ledger from the documents and the claims file (FR-070).

	``version`` is the caller's, because only the caller knows how many ledgers the log
	already holds: this module reads one run's artefacts and has no view of history.
	"""
	sources = tuple(
		parse_source_document(text, fallback_id=f"S{position:02d}")
		for position, text in enumerate(documents, start=1)
	)
	parsed_claims, contradictions = parse_claim_document(claims) if claims is not None else ((), ())
	return SourceLedger(
		version=version,
		goal_id=goal_id,
		query=query,
		sources=sources,
		claims=parsed_claims,
		contradictions=contradictions,
	)


def ledger_checks(ledger: SourceLedger, *, as_of: date | None = None) -> tuple[GateCheck, ...]:
	"""What a machine can check about a ledger (FR-069, FR-074, FR-075).

	Three checks, each of which can fail, and nothing else. The **disconfirming count is
	deliberately not one of them** (FR-071): it is a measurement, reported by the CLI,
	and a check that failed at zero would reward a producer for inventing a
	disconfirming claim — a gate that pays for fabrication is worse than no gate. What
	FR-071 asks for is detectability, and a reported count is detectable.
	"""
	day = as_of if as_of is not None else now().date()
	unsourced = tuple(
		c
		for c in ledger.claims
		if c.kind is not ClaimKind.REFUTED and not c.opinion and not c.source_ids
	)
	positioning_only = tuple(
		c for c in ledger.unbacked_decisions if c.kind is not ClaimKind.REFUTED and not c.opinion
	)
	stale = ledger.expired(day)
	return (
		GateCheck(
			name="claims-carry-provenance",
			passed=not unsourced,
			detail=(
				f"every claim cites a source ({len(ledger.claims)} claim(s))"
				if not unsourced
				else "uncited claim(s) "
				+ ", ".join(c.id for c in unsourced)
				+ ": an assertion with no source is an opinion and must be labelled one "
				"(FR-069)"
			),
		),
		GateCheck(
			name="positioning-is-not-evidence",
			passed=not positioning_only,
			detail=(
				"no claim rests only on positioning"
				if not positioning_only
				else "claim(s) resting only on positioning: "
				+ ", ".join(c.id for c in positioning_only)
				+ ": vendor content, manifests and marketing cannot support a decision on "
				"their own (FR-074)"
			),
		),
		GateCheck(
			name="nothing-has-expired",
			passed=not stale,
			detail=(
				f"no source or claim is past its expiry as of {day.isoformat()}"
				if not stale
				else f"{len(stale)} entry(ies) expired before {day.isoformat()}: "
				+ ", ".join(entry.id for entry in stale)
				+ " — a stale figure cited as current is the failure FR-075 names"
			),
		),
	)


def parse_classification(
	payload: object,
	*,
	goal_id: str,
	query: str,
	version: int = 1,
) -> ResearchClassification:
	"""FR-068's per-clause verdicts, from ``research-classification.json``.

	Fails closed on every axis the ledger's parser does: an unknown key is refused
	rather than dropped, a missing statement is refused rather than defaulted, and a
	verdict that is not one of the four raises rather than becoming Unverifiable — the
	one *wrong* default, because Unverifiable's action is "proceed" and a typo would
	therefore let an unreadable verdict through the phase.

	**The evidence is checked against the ledger, not here.** Whether ``evidence`` names
	sources the ledger actually holds is a question about two artefacts, and this
	function sees one; :func:`classification_checks` is where they meet.
	"""
	document = _object(payload, what="the classification file")
	_unknown_keys(document, frozenset({"classifications"}), what="the classification file")
	classifications: list[ClauseClassification] = []
	for raw in _mapping_list(document.get("classifications"), key="classifications"):
		_unknown_keys(raw, _CLASSIFICATION_KEYS, what="a classification")
		clause_id = _optional_string(raw.get("clause_id"), key="classification clause_id")
		statement = _optional_string(raw.get("statement"), key="classification statement")
		rationale = _optional_string(raw.get("rationale"), key="classification rationale")
		if clause_id is None or statement is None or rationale is None:
			raise ValueError(
				f"a classification needs a clause_id, a statement and a rationale, got "
				f"{raw!r}: FR-068 asks for a verdict *with cited evidence*, and a verdict "
				"with no stated reason is a label (FR-068)"
			)
		verdict_text = _optional_string(raw.get("verdict"), key="classification verdict")
		if verdict_text is None:
			raise ValueError(
				f"classification of clause {clause_id} names no verdict: defaulting to "
				"unverifiable would let a typo proceed as a flagged assumption (FR-068)"
			)
		try:
			verdict = ResearchVerdict(verdict_text)
		except ValueError as exc:
			choices = ", ".join(v.value for v in ResearchVerdict)
			raise ValueError(
				f"classification of clause {clause_id}: {verdict_text!r} is not one of "
				f"{choices} (FR-068)"
			) from exc
		classifications.append(
			ClauseClassification(
				clause_id=clause_id,
				statement=statement,
				verdict=verdict,
				rationale=rationale,
				evidence=_string_list(raw.get("evidence"), key="classification evidence"),
				settled_by=_optional_string(raw.get("settled_by"), key="classification settled_by"),
			)
		)
	return ResearchClassification(
		version=version,
		goal_id=goal_id,
		query=query,
		classifications=tuple(classifications),
	)


def classification_checks(
	classification: ResearchClassification,
	ledger: SourceLedger | None,
	*,
	clause_ids: frozenset[str],
) -> tuple[GateCheck, ...]:
	"""What a machine can check about FR-068's conclusions.

	Three checks, and each one is a way the classification could be *about something
	else* than the research it claims to rest on:

	* **every intent clause is classified.** FR-068 says "every intent clause"; the
		direction that makes that true is the draft's clause list minus the classification,
		and it is the same two-way rule P2's ``uncovered_clauses`` applies one phase later.
	* **every cited source is in the ledger.** A verdict resting on a source the ledger
		does not hold is a conclusion resting on nothing, and it cannot be invalidated with
		that source the way FR-070's edge requires.
	* **a contradicted clause stops the pipeline.** Not a check on the producer but on
		the *phase*: FR-068's action for Invalidated is "return to P0, do not build", and a
		check that merely reported it would let a caller advance P1 and read the ledger as
		grounds for proceeding. Reported here so ``sofact classify`` exits non-zero and
		``advance_phase`` can refuse.

	The **Unverifiable and Deepened counts are not checks** (FR-068, FR-071's precedent):
	they are measurements, printed, and a gate that failed on either would pay a producer
	for not looking — the exact pressure ADR-0035 decision 6 refuses.
	"""
	missing = classification.unclassified(clause_ids)
	known: set[str] = {s.id for s in ledger.sources} if ledger is not None else set()
	dangling: list[str] = []
	for entry in classification.classifications:
		dangling.extend(f"{entry.clause_id}→{sid}" for sid in entry.evidence if sid not in known)
	invalidated = classification.invalidated
	return (
		GateCheck(
			name="every-clause-is-classified",
			passed=not missing,
			detail=(
				f"all {len(clause_ids)} intent clause(s) classified"
				if not missing
				else f"{len(missing)} clause(s) unclassified ({', '.join(missing)}): FR-068 "
				"asks for a verdict on every intent clause, and an unclassified clause is "
				"one the research never reached"
			),
		),
		GateCheck(
			name="classification-cites-the-ledger",
			passed=not dangling,
			detail=(
				"every cited source is in the ledger"
				if not dangling
				else "classification cites source(s) the ledger does not hold "
				+ ", ".join(dangling)
				+ ": a conclusion resting on a source outside the ledger cannot be "
				"invalidated with it (FR-068, FR-070)"
			),
		),
		GateCheck(
			name="nothing-is-invalidated",
			passed=not invalidated,
			detail=(
				"no clause was invalidated by the evidence"
				if not invalidated
				else f"{len(invalidated)} clause(s) invalidated: "
				+ "; ".join(f"{c.clause_id} — {c.rationale}" for c in invalidated)
				+ " — FR-068's action is to return to P0 and not build"
			),
		),
	)
