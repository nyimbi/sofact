"""The Python manufacturing backend: a surface check the interpreter can run.

Stdlib only, and that is a constraint rather than a preference: the project's dependency
set is exactly httpx, pydantic, typer and uuid6, so a backend reaching for hypothesis
would be a backend that cannot run where the factory runs. FR-103 ranks property-based
tests first and this backend cannot build one — that is stated as a refusal rather than
worked around, because a "property test" written without a generator is a test with a
handful of examples wearing a stronger rank's name.

What it *can* build is derived from the one machine-readable signature source a proposal
carries: :class:`~sofact.views.Module.surface`. Three modes, and each is a real check with
a real domain.

``complete`` (rank 3, CONTRACT) — every declared member is present with its declared
arity. It checks *shape*, not behaviour, and that limit is why rank 3 is covering rather
than strong: a stub with the right names passes. FR-103's own strength column calls it
"generated, so complete by construction", which is exactly what a name-and-arity check is.

``closed`` (rank 1, PROPERTY) — nothing public in the built module is undeclared. This is
the shape a *negative* clause takes: "the process never writes outside its workspace"
bounds what the module may do, and the machine-readable statement of that bound is the
declared surface. The domain is the module's own public names, so an empty declaration
gives an unconstrained domain and is refused rather than reported as held.

``model`` (rank 5, SCHEMA) — the same completeness check against the surface the *system
model* declared rather than the one the decomposition bound. FR-083 makes the model the
single source for interface definitions, so a disagreement between the two is the
integration defect FR-083 names, and this is the oracle that can see it before P7.

Every artefact exits non-zero when it has nothing to quantify over — no module, two
candidates, an empty declaration. That is the vacuity discipline expressed in the artefact
itself: ``verification._command_output`` judges a non-zero exit as ``VIOLATED``, so a
check that found nothing to check fails loudly instead of passing vacuously.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from sofact.manufacture import (
	ManufactureRefusal,
	refusal,
	ManufactureRefusalReason,
	ManufacturedOracle,
	ManufactureRequest,
	ManufactureSpec,
	artefact_index,
	render_argv,
	slug,
)
from sofact.views import InterfaceMember, InterfaceMemberKind, OracleClass

__all__ = ["PYTHON_BACKEND", "PythonManufactureBackend"]

PYTHON_BACKEND: Final = "python"

_MODES: Final = {
	OracleClass.CONTRACT: "complete",
	OracleClass.PROPERTY: "closed",
	OracleClass.SCHEMA: "model",
}
"""Which check each rank builds. Absence is the refusal, so the table is the whole policy."""

_ARTEFACT_NAME: Final = "surface_check.py"

_ARTEFACT: Final = '''"""A manufactured surface check. Written by SoFact (FR-103); do not edit.

Exits 0 when the check held, and non-zero when it did not *or when there was nothing to
check*: an artefact that passes on an empty tree establishes nothing, which FR-107 calls
worse than a missing test.
"""

import importlib.util
import inspect
import sys
from pathlib import Path

SPEC = __SPEC__


def _candidates(root):
	"""Module files this check could be about. Zero or two are both refusals.

	Two is a refusal rather than a pick, because a slug is lossy: two module names that
	differ only in punctuation collapse to one identifier, and a check that silently chose
	one of them would report a verdict about the other.
	"""
	found = []
	for path in sorted(root.rglob("*")):
		if not path.is_file() or path.suffix not in SPEC["suffixes"]:
			continue
		if SPEC["directory"] in path.relative_to(root).parts:
			continue
		if path.stem == SPEC["slug"]:
			found.append(path)
	return found


def _load(path):
	spec = importlib.util.spec_from_file_location(SPEC["slug"], path)
	if spec is None or spec.loader is None:
		return None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _public(module):
	"""Names the module exposes, excluding imported modules and dunders."""
	import types

	return {
		name
		for name, value in vars(module).items()
		if not name.startswith("_") and not isinstance(value, types.ModuleType)
	}


def main():
	root = Path.cwd()
	found = _candidates(root)
	if len(found) != 1:
		print(
			f"{SPEC['label']}: expected exactly one {SPEC['suffixes']} file named "
			f"{SPEC['slug']!r}, found {len(found)}",
			file=sys.stderr,
		)
		return 1
	module = _load(found[0])
	if module is None:
		print(f"{SPEC['label']}: {found[0]} could not be loaded", file=sys.stderr)
		return 1
	declared = SPEC["members"]
	if not declared:
		print(f"{SPEC['label']}: nothing was declared to check", file=sys.stderr)
		return 1

	if SPEC["mode"] == "closed":
		extra = sorted(_public(module) - {m["name"] for m in declared})
		if extra:
			print(f"{SPEC['label']}: undeclared public name(s): {extra}", file=sys.stderr)
			return 1
		print(f"{SPEC['label']}: {len(declared)} declared name(s), nothing else exposed")
		return 0

	missing = []
	for member in declared:
		if not hasattr(module, member["name"]):
			missing.append(f"{member['name']} is absent")
			continue
		if member["arity"] is None:
			continue
		value = getattr(module, member["name"])
		if not callable(value):
			missing.append(f"{member['name']} is not callable")
			continue
		actual = len(inspect.signature(value).parameters)
		if actual != member["arity"]:
			missing.append(f"{member['name']} takes {actual} parameter(s), declared {member['arity']}")
	if missing:
		print(f"{SPEC['label']}: " + "; ".join(missing), file=sys.stderr)
		return 1
	print(f"{SPEC['label']}: {len(declared)} declared member(s) present")
	return 0


if __name__ == "__main__":
	sys.exit(main())
'''


class PythonManufactureBackend:
	"""The Python backend: one template, three modes, one refusal per unbuildable rank."""

	def __init__(self, spec: ManufactureSpec) -> None:
		self.spec = spec

	@property
	def language(self) -> str:
		return self.spec.language

	def supports(self, oracle_class: OracleClass) -> bool:
		"""Ranks 1, 3 and 5. The rest are refused by name rather than attempted."""
		return oracle_class in _MODES

	async def manufacture(
		self, request: ManufactureRequest
	) -> ManufacturedOracle | ManufactureRefusal:
		"""Render the artefact for this request's rank, or refuse with the reason."""
		mode = _MODES.get(request.oracle_class)
		if mode is None:
			return refusal(
				request,
				ManufactureRefusalReason.UNSUPPORTED_RANK,
				(
					f"the python backend builds ranks 1, 3 and 5; "
					f"{request.oracle_class.value} has no structured source in a Python "
					"contract (FR-103)"
				),
			)
		declared = request.surface
		if not declared:
			return refusal(
				request,
				ManufactureRefusalReason.NO_DECLARED_SURFACE,
				(
					f"module {request.module_name!r} declares no surface, so a "
					f"{request.oracle_class.value} check would quantify over nothing — and a "
					"check over nothing is satisfied by every tree, including an empty one "
					"(FR-090, FR-107)"
				),
			)
		directory = Path(self.spec.artefact_directory)
		target = directory / f"{slug(request.module_name)}_{mode}{Path(_ARTEFACT_NAME).suffix}"
		absolute = request.workspace / target
		absolute.parent.mkdir(parents=True, exist_ok=True)
		absolute.write_text(self._render(request, mode, declared), encoding="utf-8")
		return ManufacturedOracle(
			path=target,
			argv=render_argv(self.spec, target),
			artefact_argument=artefact_index(self.spec),
			provenance=(
				f"rank {request.oracle_class.value} from the declared surface of module "
				f"{request.module_name!r}: {len(declared)} member(s), "
				f"{'closed' if mode == 'closed' else 'complete'} check"
			),
		)

	def _render(
		self,
		request: ManufactureRequest,
		mode: str,
		declared: tuple[InterfaceMember, ...],
	) -> str:
		"""The artefact's source, with the declaration embedded as data.

		Embedded rather than re-read at run time, because a check that looked its own
		expectations up would be reading the tree it is judging — and the producer can write
		that tree.
		"""
		members = [
			{
				"name": member.name,
				"kind": member.kind.value,
				"arity": (
					len(member.parameters) if member.kind is InterfaceMemberKind.FUNCTION else None
				),
			}
			for member in declared
		]
		spec = {
			"label": f"{request.module_name} ({mode})",
			"slug": slug(request.module_name),
			"directory": self.spec.artefact_directory,
			"suffixes": list(self.spec.source_suffixes),
			"mode": mode,
			"members": members,
		}
		# ``repr`` rather than ``json.dumps``: the artefact is a Python module, and JSON's
		# ``null``/``true`` are not Python literals — a spec embedded as JSON fails to parse
		# at the line carrying the first null arity, which is what a canary caught here.
		return _ARTEFACT.replace("__SPEC__", repr(spec))
