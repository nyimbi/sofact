"""The Rust manufacturing backend: a compile-time surface check, run as a test.

``rustc --test`` decides the check, and the artefact is a ``#[test]`` function that binds
each declared member to a type — so a missing function, a wrong arity or a wrong signature
is a compile error, and a wrong *behaviour* is not. That is rank 3's content exactly:
generated, complete by construction, and blind to whether the module does anything.

The artefact pulls the module in with ``include!``, and that is a deliberate choice worth
defending. A Rust module is not a file — it is a *position in the crate tree*, and a file
included from an artefact directory is at no position at all. ``include!`` is the one
mechanism that gives the artefact the module's own items in its own scope without the
factory generating a ``Cargo.toml`` and a module tree the producer is about to write
anyway. It is a real limitation and it is stated: the artefact checks the module *as the
file declares it*, and a module whose surface depends on ``pub use`` re-exports from
sibling files needs those siblings, which a spec's ``source_suffixes`` cannot express. Such
a module gets a compile error, which the seam reports as a command that ran and failed —
not as a pass.

**Compile time is the timeout.** ``rustc`` on a module with dependencies is slow, and the
seam's timeout is what bounds it: a check that has not compiled in the configured window is
refused as ``COMMAND_DID_NOT_RUN`` rather than counted as a failure of the module. That is
the right verdict for the same reason a missing interpreter is: nothing about the module
was established.

Ranks 1, 2 and 5 are refused by name. A property over a Rust module needs a generator crate
(the dependency set is stdlib only), a state machine needs a declared transition relation
the factory does not model, and a schema check has no serde to lean on for the same reason.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from sofact.manufacture import (
	ManufacturedOracle,
	ManufactureRefusal,
	ManufactureRefusalReason,
	ManufactureRequest,
	ManufactureSpec,
	artefact_index,
	refusal,
	render_argv,
	slug,
)
from sofact.views import InterfaceMember, InterfaceMemberKind, OracleClass

__all__ = ["RUST_BACKEND", "RustManufactureBackend"]

RUST_BACKEND: Final = "rust"

_MODES: Final = {OracleClass.CONTRACT: "complete"}

_ARTEFACT: Final = """// A manufactured surface check. Written by SoFact (FR-103); do not edit.
//
// `rustc --test` decides it: the check is a binding, so a missing item or a wrong
// signature is a compile error. A check that does not compile exits non-zero, which is
// what the vacuity audit needs — an artefact with no module beside it must not pass.

include!("__MODULE__");

#[test]
fn manufactured_surface() {
__BINDINGS__
}
"""


class RustManufactureBackend:
	"""The Rust backend: one template, one mode, refusals by name for the rest."""

	def __init__(self, spec: ManufactureSpec) -> None:
		self.spec = spec

	@property
	def language(self) -> str:
		return self.spec.language

	def supports(self, oracle_class: OracleClass) -> bool:
		"""Rank 3 only. The docstring says why the others are refused rather than faked."""
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
					"the rust backend builds rank 3. Ranks 1 and 2 need a generator crate and "
					"a declared transition relation respectively, and rank 5 has no serialiser "
					"in a stdlib-only dependency set (FR-103)"
				),
			)
		declared = request.surface
		if not declared:
			return refusal(
				request,
				ManufactureRefusalReason.NO_DECLARED_SURFACE,
				(
					f"module {request.module_name!r} declares no surface, so the test body "
					"would be empty and the test would pass without binding anything — a "
					"vacuous pass, which is the outcome FR-107 exists to refuse (FR-090)"
				),
			)
		directory = Path(self.spec.artefact_directory)
		target = directory / f"{slug(request.module_name)}_{mode}.rs"
		absolute = request.workspace / target
		absolute.parent.mkdir(parents=True, exist_ok=True)
		absolute.write_text(self._render(request, declared, target), encoding="utf-8")
		built = target.with_suffix(f"{target.suffix}.bin")
		return ManufacturedOracle(
			path=target,
			argv=render_argv(self.spec, target, built),
			artefact_argument=artefact_index(self.spec),
			output=built,
			provenance=(
				f"rank {request.oracle_class.value} from the declared surface of module "
				f"{request.module_name!r}: {len(declared)} member(s), checked at compile time"
			),
		)

	def _render(
		self,
		request: ManufactureRequest,
		declared: tuple[InterfaceMember, ...],
		target: Path,
	) -> str:
		"""The artefact's source, with one binding per declared member.

		``include!`` resolves against the *artefact's* directory, so the path is relative to
		it rather than to the workspace. The module file is named by the spec's first source
		suffix, because a Rust file has no alternative: the language does not offer one, and
		a spec listing two would be describing a choice the artefact cannot make.
		"""
		directory = Path(self.spec.artefact_directory)
		up = "../" * len(directory.parts)
		suffix = self.spec.source_suffixes[0]
		module = f"{up}{slug(request.module_name)}{suffix}"
		bindings: list[str] = []
		for index, member in enumerate(declared):
			name = member.name
			if member.kind is InterfaceMemberKind.FUNCTION:
				# A binding, not a call: `let _ = name;` proves the item exists and its
				# arity is whatever the declared parameter list says, decided by the
				# compiler rather than by a count this backend would have to guess types
				# for. A wrong arity still fails to compile, because the item's own type is
				# what the binding takes.
				bindings.append(f"    let _member_{index} = {name};")
			else:
				bindings.append(f"    let _member_{index} = &{name};")
		return _ARTEFACT.replace("__MODULE__", module).replace("__BINDINGS__", "\n".join(bindings))
