"""FR-169 — the competitive scan, and the baseline it is allowed to be.

The operator asked for research on "the very best systems in the world". SoFact cannot name
those for an arbitrary domain, and pretending to would be the machine writing the claim it
then measures — so the producer identifies them, under a criterion SoFact writes into the
research goal, and the identification is admissible only as an artefact with its own
evidence.

Three refusals carry the whole design, and each is a way a baseline could be inflated:

- **A rival with no source is refused outright** (:class:`~sofact.views.RivalSystem`). A
  system nobody can look up is not one of the best systems in the world; it is a name.
- **A capability with no source is refused outright** (:class:`~sofact.views.RivalCapability`).
  An uncited capability cannot be the baseline an exceedance is declared against, because
  there would be nothing to check the claim of exceeding it.
- **A retitled scan is refused** (:class:`~sofact.views.CompetitiveLandscape`). The producer
  echoes the subject SoFact authored, and a landscape whose subject differs is not an answer
  to the question that was asked. This is the same failure
  :func:`sofact.service.research_goal` prevents by writing the clause ids into the prompt
  rather than letting the producer choose its own subject list.

**A scan that found nothing is a measurement, not a failure.** A domain with no comparable
system is a real finding about the domain, and treating it as an error would push a producer
toward inventing rivals to avoid one. :func:`competitor_checks` reports it as exactly what
it is and passes either way — a check that reports never gates, unless it is a gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from sofact._uuid7 import uuid7str
from sofact.views import (
	CapabilityKind,
	CompetitiveLandscape,
	GateCheck,
	RivalCapability,
	RivalSystem,
	SourceLedger,
	SourcePosture,
	now,
)

__all__ = [
	"LEDGER_COMPETITORS_FILENAME",
	"competitor_checks",
	"parse_competitors",
]

LEDGER_COMPETITORS_FILENAME: Final = "research-competitors.json"
"""The artefact the competitive scan is read from (FR-169)."""

_SYSTEM_KEYS: Final = frozenset(
	{"id", "name", "vendor", "url", "source_ids", "posture"},
)
_CAPABILITY_KEYS: Final = frozenset({"id", "system_id", "statement", "kind", "source_ids"})
_DOCUMENT_KEYS: Final = frozenset(
	{"subject", "domain", "selection_criterion", "systems", "capabilities"}
)


def _object(value: object, *, what: str) -> Mapping[str, Any]:
	if not isinstance(value, dict):
		raise ValueError(f"{what} must be an object, got {type(value).__name__}")
	return cast("Mapping[str, Any]", value)


def _unknown_keys(mapping: Mapping[str, Any], allowed: frozenset[str], *, what: str) -> None:
	extra = sorted(set(mapping) - allowed)
	if extra:
		raise ValueError(
			f"{what} carries unknown key(s) {extra}: a field this build does not read is a "
			"judgement the producer made that the landscape would silently drop"
		)


def _text(value: object, *, key: str) -> str | None:
	if value is None:
		return None
	if not isinstance(value, str) or not value.strip():
		raise ValueError(f"{key}: expected a non-empty string or null, got {value!r}")
	return value.strip()


def _required_text(value: object, *, key: str) -> str:
	out = _text(value, key=key)
	if out is None:
		raise ValueError(f"{key}: required, and a landscape without one cannot be read")
	return out


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


def _mapping_list(value: object, *, key: str) -> list[Mapping[str, Any]]:
	if value is None:
		return []
	if not isinstance(value, list):
		raise ValueError(f"{key}: expected a list, got {type(value).__name__}")
	return [_object(item, what=f"an entry in {key}") for item in cast("list[object]", value)]


def parse_competitors(
	payload: object,
	*,
	goal_id: str,
	query: str,
	version: int = 1,
) -> CompetitiveLandscape:
	"""The competitive scan, from ``research-competitors.json`` (FR-169).

	Fails closed on every axis :func:`sofact.research.parse_classification` does: an unknown
	key is refused rather than dropped, a missing statement is refused rather than
	defaulted, and a posture that is not one of the two raises rather than becoming
	``evidence`` — the one *wrong* default, because a vendor's own marketing page defaulted
	to evidence would let positioning support a decision.

	``subject`` is required and checked against ``query`` by
	:class:`~sofact.views.CompetitiveLandscape`. The producer is asked to echo it back
	rather than to choose it, which is the point.
	"""
	document = _object(payload, what="the competitors file")
	_unknown_keys(document, _DOCUMENT_KEYS, what="the competitors file")
	systems: list[RivalSystem] = []
	for raw in _mapping_list(document.get("systems"), key="systems"):
		_unknown_keys(raw, _SYSTEM_KEYS, what="a rival system")
		posture_text = (
			_text(raw.get("posture"), key="system posture") or SourcePosture.EVIDENCE.value
		)
		try:
			posture = SourcePosture(posture_text)
		except ValueError as exc:
			choices = ", ".join(p.value for p in SourcePosture)
			raise ValueError(
				f"rival system {raw.get('name')!r}: posture {posture_text!r} is not one of "
				f"{choices} (FR-074): a vendor page defaulted to evidence would let "
				"positioning support a decision"
			) from exc
		systems.append(
			RivalSystem(
				id=_required_text(raw.get("id"), key="system id"),
				name=_required_text(raw.get("name"), key="system name"),
				vendor=_text(raw.get("vendor"), key="system vendor"),
				url=_required_text(raw.get("url"), key="system url"),
				source_ids=_string_list(raw.get("source_ids"), key="system source_ids"),
				posture=posture,
			)
		)
	capabilities: list[RivalCapability] = []
	for raw in _mapping_list(document.get("capabilities"), key="capabilities"):
		_unknown_keys(raw, _CAPABILITY_KEYS, what="a rival capability")
		kind_text = _required_text(raw.get("kind"), key="capability kind")
		try:
			kind = CapabilityKind(kind_text)
		except ValueError as exc:
			choices = ", ".join(k.value for k in CapabilityKind)
			raise ValueError(
				f"capability {raw.get('statement')!r}: kind {kind_text!r} is not one of "
				f"{choices} (FR-169): the operator asked about features, capabilities and "
				"functionality, and merging them loses the distinction the exceedance "
				"declaration needs"
			) from exc
		capabilities.append(
			RivalCapability(
				id=_required_text(raw.get("id"), key="capability id"),
				system_id=_required_text(raw.get("system_id"), key="capability system_id"),
				statement=_required_text(raw.get("statement"), key="capability statement"),
				kind=kind,
				source_ids=_string_list(raw.get("source_ids"), key="capability source_ids"),
			)
		)
	return CompetitiveLandscape(
		id=_text(document.get("id"), key="landscape id") or uuid7str(),
		goal_id=goal_id,
		query=query,
		subject=_required_text(document.get("subject"), key="landscape subject"),
		version=version,
		systems=tuple(systems),
		capabilities=tuple(capabilities),
		scanned_at=now(),
	)


def competitor_checks(
	landscape: CompetitiveLandscape,
	ledger: SourceLedger | None,
) -> tuple[GateCheck, ...]:
	"""What the landscape can and cannot be read as (FR-169).

	Every check passes. That is not a formality: this phase produces a *baseline*, and a
	baseline being thin is a measurement about the domain rather than a defect in the run,
	so refusing the phase over one would teach a producer to inflate it. The checks exist to
	put the counts and the caveat in front of the reader at the gate, which is what
	:func:`sofact.delivery`'s ``machine_surface_not_verified`` does one phase along.
	"""
	known = {s.id for s in (ledger.sources if ledger is not None else ())}
	dangling_systems = tuple(
		sid for s in landscape.systems for sid in s.source_ids if sid not in known
	)
	dangling_caps = tuple(
		sid for c in landscape.capabilities for sid in c.source_ids if sid not in known
	)
	unexamined = landscape.unexamined_systems
	checks: list[GateCheck] = [
		GateCheck(
			name="scan_subject_is_the_one_sofact_asked_for",
			passed=True,
			detail=(
				f"the scan's subject is {landscape.subject!r}, which is the subject SoFact "
				"authored: the producer echoed it back rather than choosing its own (FR-169)"
			),
		),
		GateCheck(
			name="every_rival_cites_a_source",
			passed=True,
			detail=(
				f"{len(landscape.sourced_systems)} of {len(landscape.systems)} rival(s) cite "
				f"at least one source"
				+ (
					f", and {len(dangling_systems)} cited id(s) name no source the ledger holds"
					if dangling_systems
					else ""
				)
				+ ": a rival nobody can look up is a name rather than a baseline (FR-169)"
			),
		),
		GateCheck(
			name="every_rival_was_examined",
			passed=True,
			detail=(
				f"{len(unexamined)} of {len(landscape.systems)} rival(s) have no capability "
				"recorded, so the scan looked at them and enumerated nothing: a landscape of "
				"well-sourced rivals whose capabilities were never listed is a weaker "
				"baseline than one rival that was examined, and the counts are the only "
				"thing that says which this is (FR-169)"
			),
		),
	]
	if landscape.found_nothing:
		checks.append(
			GateCheck(
				name="the_scan_found_nothing",
				passed=True,
				detail=(
					"the competitive pass returned no rival system at all. That is a "
					"measurement about the domain rather than a failure of the run — a domain "
					"with no comparable system is a real finding — and it is reported as one "
					"so that a producer is never pushed toward inventing rivals (FR-169, "
					"NFR-024)"
				),
			),
		)
	if dangling_caps:
		checks.append(
			GateCheck(
				name="uncited_capabilities",
				passed=True,
				detail=(
					f"{len(dangling_caps)} capability source id(s) name no source the ledger "
					"holds: an uncited capability cannot be the baseline an exceedance is "
					"declared against, because there would be nothing to check the claim of "
					"exceeding it (FR-169)"
				),
			),
		)
	return tuple(checks)
