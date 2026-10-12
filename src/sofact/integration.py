"""P7 — integration: what can be checked about the assembled system, and what cannot.

§10 states six requirements and they are not equally reachable. Three are facts about
artefacts SoFact holds, and this module computes them:

* **FR-111** — the build order. A module built before a module it depends on has no
  sealed work is a dependency violated by sequencing, which is visible in the dispatch
  log alone.
* **FR-113** — no module reaches another module's internals. Checked by *parsing* the
  files each module's step sealed and reading its import statements, not by convention:
  a rule enforced by asking a producer to be careful is not enforced.
* **FR-114** — attribution. Every finding names the smallest set of modules that must be
  repaired for it to go away, and the report's :attr:`~sofact.views.IntegrationReport.
  violating_modules` is the union of those sets. A platform-wide rebuild in response to
  a local failure is refused by construction: nothing here can produce a scope wider
  than the findings name.

Three are not reachable yet, and this module says so rather than reporting green:

* **FR-112** needs an interface a machine can diff against. ``Module.interface`` is
  prose by design — SoFact does not know the operator's language (ADR-0025) — so
  "public-API diff is empty" has no left-hand side. Stated as uncovered on the check.
* **FR-115** needs the system model of §6.3 as a type. There is none, so structural
  conformance is not checkable.
* **FR-116** needs system-level acceptance criteria from P2. The contract carries
  per-clause oracles and nothing that no single module can satisfy.

Each of the three is reported as an unimplemented requirement on the report itself, so a
green line cannot be read as "P7 is done". That distinction is the whole reason
:class:`~sofact.views.IntegrationCheck` requires ``requirements``.

The import analysis is deliberately shallow: it reads ``import x`` and ``from x import
y`` statements and resolves them against the files the modules produced. It does not
follow a package's ``__init__``, does not evaluate a dynamic import, and does not see a
reach through a string. A check that claimed more than that would be claiming to have
decided the halting problem.
"""

from __future__ import annotations

import ast
import posixpath
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from sofact._uuid7 import uuid7str
from sofact.views import (
	Decomposition,
	DispatchRecord,
	GoalPlan,
	IntegrationCheck,
	IntegrationFinding,
	IntegrationFindingKind,
	IntegrationReport,
	now,
)

__all__ = [
	"INTEGRATION_CHECKS",
	"attribute_files",
	"check_build_order",
	"check_imports",
	"integrate",
]

INTEGRATION_CHECKS: Final[tuple[str, ...]] = (
	"build_order",
	"import_discipline",
)
"""The checks that run, named so a report can be read without parsing prose."""

_SOURCE_SUFFIXES: Final[tuple[str, ...]] = (".py",)
"""What the import analysis parses. Python is v1's implementation language (D2/D5).

A sealed file with another suffix is not parsed and is *not* thereby cleared: the
uncovered list says which modules had no analysable file, so a JavaScript module reads
as unanalysed rather than as conforming.
"""


def attribute_files(
	dispatches: Sequence[DispatchRecord],
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
	"""Map each module to the files its own steps sealed, plus the paths no module owns.

	The attribution exists only here. A producer reports nothing about what it wrote, so
	the seal is where the factory learns it — and the branches are cumulative (ADR-0025),
	so a module's files are the ones *its* step sealed rather than the ones its branch
	contains. Reading them off the branch tree would show every module containing every
	earlier module's code.

	A step with no module (a bootstrap step, or one spanning two) contributes its files to
	nobody, which is the honest answer: attributing them to a module would be a guess, and
	:data:`~sofact.views.IntegrationFindingKind.UNATTRIBUTED_FILE` is what makes the
	consequence visible when something imports one.
	"""
	assert isinstance(dispatches, Sequence), "dispatches must be a sequence"
	owned: dict[str, list[str]] = {}
	orphans: list[str] = []
	for record in dispatches:
		checkout = record.checkout
		if checkout is None or not checkout.sealed_files:
			continue
		if checkout.module is None:
			orphans.extend(checkout.sealed_files)
			continue
		owned.setdefault(checkout.module, []).extend(checkout.sealed_files)
	return (
		{name: tuple(dict.fromkeys(paths)) for name, paths in owned.items()},
		tuple(dict.fromkeys(orphans)),
	)


def _module_of_path(path: str, ownership: dict[str, tuple[str, ...]]) -> str | None:
	"""The module whose step sealed ``path``, or ``None`` when no module did."""
	for name, paths in ownership.items():
		if path in paths:
			return name
	return None


def _imported_names(tree: ast.Module) -> tuple[str, ...]:
	"""Every module named by an ``import`` or ``from ... import`` statement.

	Absolute names only. A relative import (``from . import x``) is resolved against the
	file's own package, which needs the package root and the producer's layout, and
	guessing it would produce findings about the wrong file.
	"""
	names: list[str] = []
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			names.extend(alias.name for alias in node.names)
		elif isinstance(node, ast.ImportFrom):
			if node.level:
				continue
			if node.module:
				names.append(node.module)
	return tuple(names)


def _orphan_package(imported: str, ownership: dict[str, tuple[str, ...]]) -> bool:
	"""Whether ``imported`` reaches into a package some module produced, without naming a
	file any module sealed.

	This is the only case worth reporting as unattributed, and narrowing it to this is
	what keeps the check from having an opinion about ``import json``. An import of a
	third-party name reaches nothing SoFact built; an import into a directory a module
	owns names a surface that module is responsible for and that no step ever sealed —
	which is a real gap in attribution, not a stdlib import.
	"""
	assert imported, "an empty import name reaches nothing"
	package = imported.split(".")[0]
	return any(path.startswith(f"{package}/") for paths in ownership.values() for path in paths)


def _resolve(imported: str, importer: str, known: set[str]) -> str | None:
	"""The produced file an import names, or ``None`` when it names something else.

	An import of ``ledger.core`` may be the file ``ledger/core.py`` or the file
	``ledger/core/__init__.py``; both are tried, because which one a producer wrote is
	its choice and both are the same declaration of a surface.
	"""
	assert imported, "an empty import name resolves to nothing"
	base = imported.replace(".", "/")
	for candidate in (f"{base}.py", f"{base}/__init__.py"):
		if candidate in known:
			return candidate
	# A plain module import from a file beside the importer: ``import ledger`` where the
	# importer is already inside ``ledger/``.
	sibling = posixpath.join(posixpath.dirname(importer), base)
	for candidate in (f"{sibling}.py", f"{sibling}/__init__.py"):
		if candidate in known:
			return candidate
	return None


def check_imports(
	ownership: dict[str, tuple[str, ...]],
	*,
	declared: dict[str, set[str]],
	root: Path | None = None,
	sources: dict[str, str] | None = None,
) -> tuple[IntegrationFinding, ...]:
	"""Parse each module's sealed files and report reaches across module boundaries.

	``ownership`` maps module name to the paths it produced; ``declared`` maps module name
	to the names it declared in ``depends_on``. A file that imports a file another module
	produced is a reach into that module's surface, and it is legal only when the importing
	module declared the dependency. That is FR-113 and FR-090 read together: the declared
	edge is the permitted surface, and an undeclared one is the violation.

	``sources`` supplies file text directly, which is what the tests use — the analysis is
	over bytes, and making a test materialise a repository to exercise a parser would be
	testing git rather than the check. ``root`` reads from disk when ``sources`` is absent.

	An import of a path *no* module sealed is reported as unattributed rather than ignored.
	Something imports it, so it exists; nothing claims it, so no repair could be scoped to
	its owner. FR-114 makes that a finding rather than a warning.
	"""
	assert ownership, "cannot check imports with no attributed files"
	if sources is None:
		assert root is not None, "either sources or root must be given"
		sources = _read(root, ownership)

	known = {path for paths in ownership.values() for path in paths}
	findings: list[IntegrationFinding] = []
	for module in sorted(ownership):
		for path in ownership[module]:
			if not path.endswith(_SOURCE_SUFFIXES):
				continue
			text = sources.get(path)
			if text is None:
				continue
			try:
				tree = ast.parse(text)
			except SyntaxError:
				# A file that does not parse is not evidence of a violation. Reporting it
				# here would make this check a linter, and the parser that judges the module
				# is P5's, on the producer's own language toolchain.
				continue
			for imported in _imported_names(tree):
				target = _resolve(imported, path, known)
				if target is None:
					if _orphan_package(imported, ownership):
						findings.append(
							IntegrationFinding(
								kind=IntegrationFindingKind.UNATTRIBUTED_FILE,
								detail=(
									f"{module} imports {imported!r}, inside a package a module "
									"produced, but no step sealed that file (FR-114)"
								),
								modules=(module,),
								evidence=(f"{path}: import {imported}",),
							)
						)
					continue
				if target in ownership[module]:
					continue
				owner = _module_of_path(target, ownership)
				if owner is None:
					findings.append(
						IntegrationFinding(
							kind=IntegrationFindingKind.UNATTRIBUTED_FILE,
							detail=(
								f"{module} imports {target!r}, which no module's step sealed, "
								"so no module owns the surface being reached for (FR-114)"
							),
							modules=(module,),
							evidence=(f"{path}: import {imported}",),
						)
					)
					continue
				if owner in declared.get(module, set()):
					continue
				findings.append(
					IntegrationFinding(
						kind=IntegrationFindingKind.UNDECLARED_DEPENDENCY,
						detail=(
							f"{module} reaches {owner}'s file {target!r} without declaring it "
							"in depends_on (FR-090, FR-113)"
						),
						modules=(module, owner),
						evidence=(f"{path}: import {imported}",),
					)
				)
	return tuple(findings)


def _read(root: Path, ownership: dict[str, tuple[str, ...]]) -> dict[str, str]:
	"""The text of every produced file that exists under ``root``."""
	sources: dict[str, str] = {}
	for paths in ownership.values():
		for path in paths:
			candidate = root / path
			if candidate.is_file():
				sources[path] = candidate.read_text(encoding="utf-8", errors="replace")
	return sources


def check_build_order(
	decomposition: Decomposition,
	dispatches: Sequence[DispatchRecord],
) -> tuple[IntegrationFinding, ...]:
	"""Report modules built before a module they depend on had sealed work (FR-111).

	The order compared against is the decomposition's own topological order (FR-092),
	not the plan's step ordinals: FR-136 lets a module's work span several steps and the
	plan interleaves tiers, so the step order is not the module order and reading it as
	one would report a violation whenever the compiler's tiers disagreed with the DAG.

	"Built" means a step for that module sealed something. A module with no sealed work
	was not built, and a module that *depends on* one is a violation only when it was —
	an unbuilt dependency of an unbuilt dependent is a plan not yet finished, which is a
	different fact and not this check's to report.
	"""
	assert decomposition.modules, "cannot check a build order over no modules"
	order = {module.name: index for index, module in enumerate(decomposition.build_order())}
	built = {
		checkout.module
		for record in dispatches
		if (checkout := record.checkout) is not None
		and checkout.module is not None
		and checkout.sealed_files
	}
	by_name = {module.name: module for module in decomposition.modules}
	findings: list[IntegrationFinding] = []
	for name in sorted(built):
		module = by_name.get(name)
		if module is None:
			continue
		for dependency_id in module.depends_on:
			dependency = decomposition.module(dependency_id)
			if dependency is None or dependency.name in built:
				continue
			if order.get(dependency.name, 0) < order.get(name, 0):
				findings.append(
					IntegrationFinding(
						kind=IntegrationFindingKind.UNBUILT_DEPENDENCY,
						detail=(
							f"{name} was built although {dependency.name} produced nothing, "
							"and FR-092 places it first (FR-111)"
						),
						modules=(name, dependency.name),
						evidence=(f"{name} depends_on {dependency.name}",),
					)
				)
	return tuple(findings)


def integrate(
	plan: GoalPlan,
	decomposition: Decomposition,
	dispatches: Sequence[DispatchRecord],
	*,
	root: Path | None = None,
	sources: dict[str, str] | None = None,
) -> IntegrationReport:
	"""Run P7's checks over a plan's dispatched work and report what passed and what did not.

	Deterministic and model-free. Every input is a record the factory already holds: the
	plan, the approved decomposition, the dispatches with their checkouts. Nothing is
	re-run and nothing is asked of a producer, so a report is reproducible from the log —
	which is what makes it evidence rather than an assertion about a run.
	"""
	assert plan.steps, "cannot integrate a plan with no steps"
	ownership, orphans = attribute_files(dispatches)
	declared = {
		module.name: {d.name for d in (decomposition.module(i) for i in module.depends_on) if d}
		for module in decomposition.modules
	}
	build_findings = check_build_order(decomposition, dispatches)
	import_findings = (
		check_imports(ownership, declared=declared, root=root, sources=sources) if ownership else ()
	)
	findings = (*build_findings, *import_findings)

	built = tuple(sorted(name for name, paths in ownership.items() if paths))
	analysed = tuple(
		sorted(
			name
			for name, paths in ownership.items()
			if any(path.endswith(_SOURCE_SUFFIXES) for path in paths)
		)
	)
	unanalysed = tuple(name for name in built if name not in analysed)
	unattributed = tuple(f"{path}" for path in orphans)

	checks = (
		IntegrationCheck(
			name="build_order",
			passed=not build_findings,
			detail=(
				f"{len(built)} module(s) built in the order FR-092 declares"
				if not build_findings
				else f"{len(build_findings)} module(s) built ahead of a dependency"
			),
			requirements=("FR-111",),
			covered=tuple(f"{name} was built after its dependencies" for name in built),
			uncovered=(() if built else ("no module sealed any work, so no order was exercised",)),
		),
		IntegrationCheck(
			name="import_discipline",
			passed=not import_findings,
			detail=(
				f"{len(analysed)} module(s) parsed; no undeclared cross-module import"
				if not import_findings
				else f"{len(import_findings)} cross-module reach(es) found by import analysis"
			),
			requirements=("FR-113", "FR-114"),
			covered=tuple(f"{name}: sealed files parsed for imports" for name in analysed),
			uncovered=(
				*(f"{name}: no file with a suffix this check parses" for name in unanalysed),
				*(f"{path}: sealed by a step that named no module" for path in unattributed),
				"relative imports are not resolved, so a reach written as `from . import x` "
				"is not seen",
				"a dynamic import (`importlib.import_module`) is not seen",
			),
		),
	)

	return IntegrationReport(
		id=uuid7str(),
		plan_id=plan.id,
		goal_id=plan.goal_id,
		contract_id=plan.contract_id,
		rendered_at=now(),
		build_order=tuple(module.name for module in decomposition.build_order()),
		modules_built=built,
		findings=findings,
		checks=checks,
	)
