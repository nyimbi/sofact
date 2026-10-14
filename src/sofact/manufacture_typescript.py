"""The TypeScript manufacturing backend: a type-level surface check.

TypeScript's type system is the language's own oracle, so this backend builds the check
*as a type* rather than as a runtime assertion. ``tsc --noEmit`` decides it, and a missing
member is a compile error rather than a failed comparison — which is the same rank-3
content a Python name-and-arity check has, decided by a stronger instrument.

That is a real advantage and it is worth naming: ``Has<typeof m, "tally">`` is checked by
the compiler against the module's actual export set, so there is no gap between what the
artefact believes and what the module exposes. A Python ``hasattr`` can be fooled by a
``__getattr__``; a type cannot.

Two modes, both rank 3 and rank 5, and the refusal for the rest.

``complete`` (rank 3, CONTRACT) — every declared member is a key of the module's exports.

``model`` (rank 5, SCHEMA) — the same, against the model's declared interface rather than
the decomposition's surface. The two agree when FR-083 holds and disagree when it does not.

**What this backend cannot do, and says so.** Rank 1's property check has no analogue
here: "nothing public is undeclared" is not expressible as a type without mapped-type
machinery whose own correctness would then need checking, and a check that needs a check
is not an oracle. So a NEGATIVE clause gets the Python backend's ``closed`` mode where the
module is Python, and a named refusal where it is not — ``UNSUPPORTED_RANK``, carrying the
reason.

The artefact is one file per check, and it imports the module by its **relative path**,
so the same artefact runs in the workspace and in the vacuity audit's empty mirror without
editing. The mirror holds the artefact and nothing else, so the import fails and ``tsc``
exits non-zero — which is the audit passing.
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

__all__ = ["TYPESCRIPT_BACKEND", "TypeScriptManufactureBackend"]

TYPESCRIPT_BACKEND: Final = "typescript"

_MODES: Final = {
	OracleClass.CONTRACT: "complete",
	OracleClass.SCHEMA: "model",
}

_ARTEFACT: Final = """// A manufactured surface check. Written by SoFact (FR-103); do not edit.
//
// `tsc --noEmit` decides it: the check is a type, and a missing member is a compile error
// rather than a comparison someone has to trust. Exit non-zero means the check did not
// hold *or* that there was nothing to hold it against — the vacuity audit depends on the
// second, and a check that passed with no module to check would establish nothing.

type Expect<T extends true> = T;
type Has<T, K extends string> = K extends keyof T ? true : false;

import * as subject from "__RELATIVE__";

__ASSERTIONS__

export const _check = (): void => {
__BODY__
};
"""


class TypeScriptManufactureBackend:
	"""The TypeScript backend: one template, two modes, refusals by name for the rest."""

	def __init__(self, spec: ManufactureSpec) -> None:
		self.spec = spec

	@property
	def language(self) -> str:
		return self.spec.language

	def supports(self, oracle_class: OracleClass) -> bool:
		"""Ranks 3 and 5. Rank 1 is refused: see the module docstring for why."""
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
					f"the typescript backend builds ranks 3 and 5. A rank-1 property over a "
					"TypeScript module needs mapped-type machinery whose own correctness "
					f"would then need checking, and a check that needs a check is not an "
					f"oracle (FR-103)"
				),
			)
		declared = request.surface
		if not declared:
			return refusal(
				request,
				ManufactureRefusalReason.NO_DECLARED_SURFACE,
				(
					f"module {request.module_name!r} declares no surface, so the check would "
					"assert `Has<typeof subject, never>`, which every module satisfies — "
					"including a module that does not exist (FR-090, FR-107)"
				),
			)
		directory = Path(self.spec.artefact_directory)
		target = directory / f"{slug(request.module_name)}_{mode}.ts"
		absolute = request.workspace / target
		absolute.parent.mkdir(parents=True, exist_ok=True)
		absolute.write_text(self._render(request, mode, declared, target), encoding="utf-8")
		return ManufacturedOracle(
			path=target,
			argv=render_argv(self.spec, target),
			artefact_argument=artefact_index(self.spec),
			provenance=(
				f"rank {request.oracle_class.value} from the declared surface of module "
				f"{request.module_name!r}: {len(declared)} member(s), checked by the compiler"
			),
		)

	def _render(
		self,
		request: ManufactureRequest,
		mode: str,
		declared: tuple[InterfaceMember, ...],
		target: Path,
	) -> str:
		"""The artefact's source, with one assertion per declared member.

		The import is relative to the artefact's own directory, computed from the two paths
		rather than assumed: a spec free to put artefacts anywhere would otherwise need the
		template to know the workspace layout, which is the one thing it must not depend on.
		"""
		directory = Path(self.spec.artefact_directory)
		up = "../" * len(directory.parts)
		relative = f"{up}{slug(request.module_name)}" if up else f"./{slug(request.module_name)}"
		assertions: list[str] = []
		body: list[str] = []
		for index, member in enumerate(declared):
			name = member.name
			assertions.append(f'type _assert_{index} = Expect<Has<typeof subject, "{name}">>;')
			body.append(f"  void (0 as unknown as _assert_{index});")
			if member.kind is InterfaceMemberKind.FUNCTION and member.parameters:
				# Arity is checked only where the surface declared parameters, because a
				# function's parameter count is the one part of a signature this factory can
				# state without inventing a type (ADR-0025's line, held here).
				assertions.append(
					f"type _arity_{index} = Expect<\n"
					f"  typeof subject.{name} extends (...args: infer A) => unknown\n"
					f"    ? A['length'] extends {len(member.parameters)}\n"
					f"      ? true\n"
					f"      : false\n"
					f"    : false\n"
					f">;"
				)
				body.append(f"  void (0 as unknown as _arity_{index});")
		return (
			_ARTEFACT.replace("__RELATIVE__", relative)
			.replace("__ASSERTIONS__", "\n".join(assertions))
			.replace("__BODY__", "\n".join(body))
		)
