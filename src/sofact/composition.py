"""FR-154-156 — the frozen plugin composition, and the deletion test that admits into it.

FR-154: the harness plugin composition "must be **frozen, minimal, pinned, and
hash-verified** for the duration of a build, and must never be the operator's own
profile".
FR-155: "A third-party plugin may enter the P5 composition **only if SoFact would reach
the same verdict without it.**"
FR-156: "Where a capability can be obtained by **configuration** rather than by installing
third-party code, configuration is mandatory."

**Why the three are one module.** FR-155's test has nothing to admit into until FR-154
freezes something, and a freeze with no admission test pins whatever happened to be
installed — so a build would report a composition it had verified the *shape* of and never
asked a question about. §8.7's hazard is specific and structural: the `dsh` plugin set is
mutable **at runtime by the agent** ([S22]), so a producer that can influence its own
composition can influence its own verifier. The deletion test is the one filter that
survives that, because it does not ask whether a plugin is good — it asks whether SoFact's
verdict changes when the plugin is gone.

**What this module derives, and what it refuses to derive.** The freeze has two halves and
only one of them is a list. ``argv_frozen`` is read off
:attr:`~sofact.harness.HarnessSpec.freezing_argv` — the command line itself refuses to
auto-load installed plugins — and ``pins`` is the digest-verified enumeration. A composition
with neither is not frozen, and :attr:`~sofact.views.PluginComposition.discharged` reports
FR-154 as **not carried out** rather than reporting a clean freeze it does not have. That is
the honest reading for `dsh` today: §8.7 records that its composition is mutable by the
agent, and no flag in :data:`~sofact.harness.DSH_SPEC` stops it.

**The deletion test is not automated here, and cannot be.** Whether deleting a plugin
changes SoFact's completion verdict is a question about a running system, and a function
that answered it from a table would be asserting the very thing it claims to check. What
this module does is make the *answer* checkable: an admission carries the verdict surfaces
SoFact holds without the plugin, and :class:`~sofact.views.PluginAdmission` refuses a row
whose verdict does not follow from that set. §8.7's worked table is the corpus — the
admissions a deployment declares are transcribed from an audit of that kind, and the
type is what stops one being written down wrong.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from sofact._uuid7 import uuid7str
from sofact.harness import HarnessSpec
from sofact.views import (
	VERDICT_SURFACES,
	PluginAdmission,
	PluginComposition,
	PluginVerdict,
	now,
)

__all__ = [
	"composition_for",
	"load_composition",
	"verify_composition",
]


def _surfaces(value: object, plugin: str) -> frozenset[str]:
	"""The verdict surfaces a declaration claims SoFact holds without the plugin.

	A missing list is refused rather than defaulted to the full set: defaulting to "all
	held" would make every admission that forgot the field admissible, which is the
	subset failure in its most expensive direction — the plugins that look like the
	biggest saving are the ones that must be refused (§8.7).
	"""
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError(
			f"plugin {plugin!r}: surfaces_held must be an array of FR-155's surface names "
			f"{list(VERDICT_SURFACES)}; omitting it would default every admission to "
			"admissible"
		)
	seq = cast("Sequence[object]", value)
	out: list[str] = []
	for item in seq:
		if not isinstance(item, str):
			raise ValueError(f"plugin {plugin!r}: surfaces_held must contain only strings")
		out.append(item)
	return frozenset(out)


def _pins(value: object) -> tuple[tuple[str, str], ...]:
	"""``[[plugin, digest], ...]`` — the same two-string-pair shape ``env`` uses."""
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError("pins must be an array of [plugin, digest] pairs")
	pairs = cast("Sequence[object]", value)
	out: list[tuple[str, str]] = []
	for pair in pairs:
		if isinstance(pair, str) or not isinstance(pair, Sequence):
			raise ValueError("each pin must be a [plugin, digest] pair")
		items = tuple(cast("Sequence[object]", pair))
		if len(items) != 2:
			raise ValueError("each pin must have exactly two elements")
		name, digest = items[0], items[1]
		if not isinstance(name, str) or not isinstance(digest, str):
			raise ValueError("pin names and digests must be strings")
		if not digest.strip():
			raise ValueError(
				f"plugin {name!r} is pinned with an empty digest; FR-154's word is "
				"hash-verified, and a pin that verifies nothing freezes a name while "
				"leaving what it resolves to free to change"
			)
		out.append((name, digest))
	return tuple(out)


def _admission(entry: Mapping[str, Any], path: Path) -> PluginAdmission:
	"""One declared admission, with the refusals that make the row mean what it says.

	The type does the semantic checking — an ``ADMISSIBLE`` verdict with a surface missing
	raises there — so this reader only has to make sure the *shape* is right and that the
	message names the file. Duplicating the type's rules here would give two places to
	change when FR-155's list moves, which is the drift this project keeps finding.
	"""
	plugin = entry.get("plugin")
	if not isinstance(plugin, str) or not plugin.strip():
		raise ValueError(f"{path}: every admission names its plugin")
	verdict = entry.get("verdict")
	if not isinstance(verdict, str):
		raise ValueError(f"{path}: plugin {plugin!r} declares no verdict")
	try:
		resolved = PluginVerdict(verdict)
	except ValueError as exc:
		known_verdicts = ", ".join(v.value for v in PluginVerdict)
		raise ValueError(
			f"{path}: plugin {plugin!r} has verdict {verdict!r}, which is not one of "
			f"{known_verdicts}"
		) from exc
	rationale = entry.get("rationale")
	if not isinstance(rationale, str) or not rationale.strip():
		raise ValueError(
			f"{path}: plugin {plugin!r} states no rationale; a verdict with no reason "
			"attached is re-litigated at the next plugin, which is the cost FR-155's "
			"refusals are recorded to avoid"
		)
	superseded_by = entry.get("superseded_by")
	if superseded_by is not None and not isinstance(superseded_by, str):
		raise ValueError(f"{path}: plugin {plugin!r}: superseded_by must be a string")
	licence = entry.get("licence")
	if licence is not None and not isinstance(licence, str):
		raise ValueError(f"{path}: plugin {plugin!r}: licence must be a string")
	return PluginAdmission(
		plugin=plugin,
		verdict=resolved,
		surfaces_held=_surfaces(entry.get("surfaces_held"), plugin),
		superseded_by=superseded_by,
		licence=licence,
		rationale=rationale,
	)


def _composition_body(
	name: str, body: object, *, spec: HarnessSpec, path: Path
) -> PluginComposition:
	"""One harness's declared composition, with the freeze read off its own spec."""
	if not isinstance(body, dict):
		raise ValueError(f"{path}: harness {name!r} must map to an object")
	declared = cast("dict[str, Any]", body)
	known = {"pins", "admissions"}
	unknown = sorted(set(declared) - known)
	if unknown:
		raise ValueError(
			f"{path}: harness {name!r}: unknown field(s) {unknown}; a composition declares "
			f"{sorted(known)} and nothing else. Whether the argv freezes the composition is "
			"read from the harness spec, so a file cannot claim a freeze the command line "
			"does not enforce"
		)
	raw_admissions = declared.get("admissions", [])
	if isinstance(raw_admissions, str) or not isinstance(raw_admissions, Sequence):
		raise ValueError(f"{path}: harness {name!r}: admissions must be an array of objects")
	admissions: list[PluginAdmission] = []
	for item in cast("Sequence[object]", raw_admissions):
		if not isinstance(item, dict):
			raise ValueError(f"{path}: harness {name!r}: each admission must be an object")
		admissions.append(_admission(cast("Mapping[str, Any]", item), path))
	return PluginComposition(
		id=uuid7str(),
		harness=name,
		created_at=now(),
		pins=_pins(declared.get("pins", [])),
		admissions=tuple(admissions),
		# Derived, never declared. A spec the file names but this deployment does not
		# register is refused above, so this read always has a spec behind it.
		argv_frozen=spec.composition_frozen,
	)


def load_composition(path: Path, specs: Mapping[str, HarnessSpec]) -> dict[str, PluginComposition]:
	"""Read declared plugin compositions from a JSON file (FR-154).

	The seam :func:`sofact.harness.load_specs` and :func:`sofact.escape.load_escape_budget`
	provide, and for the same reason: the composition is a deployment's declaration, not a
	constant in the product. FR-156's rule reaches the declaration itself — a composition
	that could only be expressed by editing ``src/`` would be a capability obtained by code.

	Two shapes, matching ``load_specs`` exactly: ``{"compositions": {harness: {...}}}`` or a
	bare ``{harness: {...}}``. The harness name is the key rather than a field inside the
	body, because the freeze is *derived from that harness's spec* — a body that named its
	own harness could name one this deployment does not register, and the read that
	establishes ``argv_frozen`` would then have nothing behind it.
	"""
	try:
		text = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read composition {path}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{path}: not valid JSON: {exc}") from exc
	if not isinstance(raw, dict):
		raise ValueError(f"{path}: expected a JSON object")
	document = cast("dict[str, Any]", raw)
	body: object = document["compositions"] if set(document) == {"compositions"} else document
	if not isinstance(body, dict):
		raise ValueError(f"{path}: expected an object of harnesses under 'compositions'")
	declared = cast("dict[str, Any]", body)
	if not declared:
		raise ValueError(
			f"{path}: no harnesses; a file that declares no composition would read as "
			"configured while freezing nothing"
		)

	out: dict[str, PluginComposition] = {}
	for name, entry in declared.items():
		spec = specs.get(name)
		if spec is None:
			known_harnesses = ", ".join(sorted(specs)) or "none"
			raise ValueError(
				f"{path}: {name!r} is not a harness this deployment registers, so its argv "
				f"cannot be read and FR-154's freeze cannot be derived. Registered: "
				f"{known_harnesses}"
			)
		out[name] = _composition_body(name, entry, spec=spec, path=path)
	return out


def composition_for(spec: HarnessSpec) -> PluginComposition:
	"""The composition a harness runs with when this deployment declares none (FR-154).

	An *empty* composition, and for `pi` that is the true one: its argv refuses to
	auto-load installed plugins, so there is nothing to enumerate and nothing to admit. It
	is minimal by construction — the fewest moving parts is zero — and FR-156's answer
	rather than a gap.

	For a harness whose argv does not freeze — `dsh`, whose composition §8.7 records as
	mutable at runtime by the agent, and `pi-research`, which drops the flag because the
	research loop *is* an installed extension — the same empty composition is **not**
	frozen, and :attr:`~sofact.views.PluginComposition.discharged` leaves FR-154 open. That
	asymmetry is the whole reason this reads the spec instead of returning a constant: the
	identical composition is a freeze on one harness and an unfrozen profile on another.
	"""
	return PluginComposition(
		id=uuid7str(),
		harness=spec.name,
		created_at=now(),
		argv_frozen=spec.composition_frozen,
	)


def verify_composition(
	composition: PluginComposition, *, pins: Mapping[str, str]
) -> tuple[str, ...]:
	"""The plugins whose digest no longer matches what the composition pinned (FR-154).

	FR-154's word is **hash-verified**, and a pin nobody re-checks is a name with a digest
	beside it. This is the check: the caller supplies what is installed *now*, and the
	return value is the plugins whose content moved. A plugin present in ``pins`` and absent
	from the observed set is returned too — an uninstalled member is as much a change to the
	composition as an altered one, and a build pinned to a hash it can no longer reproduce
	is exactly what the freeze exists to detect.

	Returns an empty tuple for an unchanged composition, which is the only case in which
	FR-154's freeze held. Nothing here reads the filesystem: what is installed is a fact
	about a machine, and this module's contract is that it is a pure function of what it is
	handed.
	"""
	pinned = dict(composition.pins)
	drifted = sorted(name for name, digest in pinned.items() if pins.get(name) != digest)
	return tuple(drifted)
