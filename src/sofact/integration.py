"""P7 — integration: what can be checked about the assembled system, and what cannot.

§10 states six requirements and this module computes five of them, plus **O8** (§9.4),
which is P7's own and not one of the six. The four that are facts about artefacts SoFact
holds:

* **FR-110 (O8)** — the boundary contract. Every other check here compares a module
  against *itself*: FR-112 against its own declaration, FR-113 against its own
  ``depends_on``. Neither asks whether the name a consumer reached for across a declared
  edge was ever promised by the producer, and that is the incoherence O8 exists for —
  FR-110's own premise is that per-module verification "structurally cannot detect
  cross-module incoherence". A consumer that imports a declared dependency and calls a
  name that module never declared passes both neighbours and does not run.
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
* **FR-115** — the assembled system against §6.3's model. An entity names the clauses
  that introduced it and a module names the clauses it exists to satisfy, so *present* is
  a set comparison over declarations — never a search for the entity's name in a
  producer's source, which passes on an entity called ``id``. Relationships and
  invariants are declared and **not** conformed, and the check says so: a relationship is
  a claim about two entities' interaction, which no declaration in the log describes.

**FR-116** and **FR-112** are the two that are only as reachable as other phases make
them, and the difference is reported rather than smoothed over:

* **FR-116** checks P2's system-level criteria, which span more than one clause. It
  verifies that every clause a criterion spans carries a satisfied verdict; it does not
  *run* the criterion, because a system-level criterion is not in the contract's oracle
  set and there is no command to run. That is stated as uncovered on the check.
* **FR-112** needs an interface a machine can diff against. ``Module.interface`` is prose
  by design — SoFact does not know the operator's language (ADR-0025) — so "the public-API
  diff is empty" has no left-hand side until a module declares a machine-readable surface,
  and a proposal derives none.

A specification that declared no model and no criteria leaves FR-115 and FR-116 in
:attr:`~sofact.views.IntegrationReport.not_implemented` — the honest state of a project
that has not described its system as a whole, not a green line. Every such gap is
reported as an unimplemented requirement on the report itself, so a green line cannot be
read as "P7 is done". That distinction is the whole reason
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
from collections.abc import Mapping, Sequence
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
	InterfaceMember,
	InterfaceMemberKind,
	ModuleBudget,
	SystemCriterion,
	SystemModel,
	VerdictOutcome,
	now,
)

__all__ = [
	"INTEGRATION_CHECKS",
	"attribute_files",
	"check_boundary_contracts",
	"check_build_order",
	"check_imports",
	"check_interface_conformance",
	"check_model_conformance",
	"check_model_is_the_interface_source",
	"check_module_budget",
	"check_system_criteria",
	"integrate",
	"public_surface",
]

INTEGRATION_CHECKS: Final[tuple[str, ...]] = (
	"boundary_contracts",
	"build_order",
	"import_discipline",
	"interface_conformance",
	"model_interface_source",
	"module_budget",
	"model_conformance",
	"system_criteria",
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


def check_module_budget(
	ownership: dict[str, tuple[str, ...]],
	budgets: Mapping[str, ModuleBudget],
	*,
	sources: Mapping[str, str],
) -> tuple[IntegrationFinding, ...]:
	"""Report every module whose built artefact exceeds the budget it declared (FR-026).

	The bound is checked over the files the module's *own steps sealed*, which is the
	same attribution FR-113 is checked over and the only one the log holds: the branches
	are cumulative, so a module's branch contains every earlier module's code and reading
	the tree would charge one module for another's size. ``ownership`` is
	:func:`attribute_files`' output, so a module that sealed nothing is absent from it
	and is reported by the build-order check instead of here.

	**The measured quantity is the artefact, not the diff**, and the two are worth telling
	apart because FR-026's words are "maximum changed-file count and a maximum diff size".
	For a module P5 built from nothing the added lines *are* the artefact's lines, and the
	two diverge only after a repair — where the artefact is the larger and therefore the
	stricter bound, so a module cannot grow without limit across repairs that each stayed
	inside a diff bound. What the factory cannot do is measure a diff *per module*: a
	repository-wide diff names no module, and FR-114's repair scope needs a name. So the
	bound is on the artefact and the report says so rather than calling the number a diff.

	The line count is every non-blank line, comments included. Which lines a comment
	occupies is a property of the language, and ADR-0025 leaves the language open — a
	comment-aware count would be a number about a language the factory did not choose.

	A module whose files were not all read is reported as *unmeasured* rather than as
	within bounds: ``sources`` missing a sealed path means the artefact was not there to
	measure, and a missing file is not a small one (NFR-024).
	"""
	assert budgets, "cannot check budgets without a declared budget per module"
	findings: list[IntegrationFinding] = []
	for module in sorted(ownership):
		budget = budgets.get(module)
		if budget is None:
			continue
		paths = ownership[module]
		unread = tuple(path for path in paths if path not in sources)
		if unread:
			findings.append(
				IntegrationFinding(
					kind=IntegrationFindingKind.MODULE_OVER_BUDGET,
					detail=(
						f"{module} declared a budget of {budget.max_files} file(s) and "
						f"{budget.max_loc} line(s) and {len(unread)} of its "
						f"{len(paths)} sealed file(s) could not be read, so the bound is "
						"unmeasured rather than met (FR-026, NFR-024)"
					),
					modules=(module,),
					evidence=unread,
				)
			)
			continue
		lines = sum(_count_lines(sources[path]) for path in paths)
		over_files = len(paths) - budget.max_files
		over_lines = lines - budget.max_loc
		if over_files <= 0 and over_lines <= 0:
			continue
		exceeded: list[str] = []
		if over_files > 0:
			exceeded.append(
				f"{len(paths)} file(s) against a bound of {budget.max_files} (+{over_files})"
			)
		if over_lines > 0:
			exceeded.append(f"{lines} line(s) against a bound of {budget.max_loc} (+{over_lines})")
		findings.append(
			IntegrationFinding(
				kind=IntegrationFindingKind.MODULE_OVER_BUDGET,
				detail=(
					f"{module} is over the budget its contract declared: "
					+ "; ".join(exceeded)
					+ ". A build this size is unverifiable regardless of its oracle results, "
					"because review bandwidth is the binding resource (§7.3), and the repair "
					"scope is this module and not the plan (FR-026, FR-114)"
				),
				modules=(module,),
				evidence=tuple(
					f"{path}: {_count_lines(sources[path])} line(s)" for path in sorted(paths)
				),
			)
		)
	return tuple(findings)


def _count_lines(text: str) -> int:
	"""Non-blank lines in ``text``, which is what the factory can count without a language."""
	return sum(1 for line in text.splitlines() if line.strip())


def _count_lines_all(sources: Mapping[str, str], paths: tuple[str, ...]) -> int:
	"""Non-blank lines over several files, for a check's ``covered`` line."""
	return sum(_count_lines(sources[path]) for path in paths)


def _read(root: Path, ownership: dict[str, tuple[str, ...]]) -> dict[str, str]:
	"""The text of every produced file that exists under ``root``."""
	sources: dict[str, str] = {}
	for paths in ownership.values():
		for path in paths:
			candidate = root / path
			if candidate.is_file():
				sources[path] = candidate.read_text(encoding="utf-8", errors="replace")
	return sources


def check_model_conformance(
	decomposition: Decomposition,
	model: SystemModel,
	*,
	module_for_clause: Mapping[str, str],
) -> tuple[IntegrationFinding, ...]:
	"""FR-115: is every declared entity present in the assembled system?

	§6.3 makes the model "the input to decomposition and the substrate for structural
	oracles", and FR-115 is "the point at which the model earns its maintenance cost".
	What makes it checkable without reading code is the link :class:`SystemEntity`
	already carries: an entity names the clauses that introduced it, a module names the
	clauses it exists to satisfy, so *an entity is present* means some built module owns
	one of its clauses. That is a set comparison over declarations, not a search for the
	entity's name in the producer's source — an entity called ``id`` or ``job`` occurs in
	unrelated lines, so a text search would report conformance for a system that
	implements nothing (the failure :class:`SystemEntity` was written to avoid).

	``module_for_clause`` maps a clause id to the name of the module that owns it, and is
	built by the caller from the *decomposition* rather than from the dispatches: a
	module that was never built is still a module the system is missing, and deriving
	ownership from what happened to be dispatched would make a plan that skipped half its
	modules report a conforming system.

	Two directions, because one alone is satisfiable by a system that does nothing. An
	entity no module owns is a declared capability nobody built; an entity whose clause
	no module claims at all is a model that drifted from the decomposition, which is the
	drift FR-084 exists to make expensive.
	"""
	assert module_for_clause or not model.entities, (
		"a model with entities needs the clause-to-module map to be conformed against"
	)
	findings: list[IntegrationFinding] = []
	known = {module.name for module in decomposition.modules}
	for entity in model.entities:
		owners = sorted(
			{
				module_for_clause[clause_id]
				for clause_id in entity.clause_ids
				if clause_id in module_for_clause
			}
		)
		if not owners:
			# No module claims the clause, so this is a decomposition defect rather than a
			# build defect -- and the finding says which, because FR-114's repair scope is
			# the difference between re-running a step and revising the decomposition.
			findings.append(
				IntegrationFinding(
					kind=IntegrationFindingKind.UNOWNED_ENTITY,
					detail=(
						f"entity {entity.name!r} is declared and no module owns the "
						f"{len(entity.clause_ids)} clause(s) that introduce it, so the "
						"decomposition and the model disagree about what the system "
						"contains (FR-084, FR-115)"
					),
					modules=(),
					evidence=tuple(f"{entity.name} -> clause {cid}" for cid in entity.clause_ids),
				)
			)
			continue
		absent = tuple(name for name in owners if name not in known)
		if absent:
			findings.append(
				IntegrationFinding(
					kind=IntegrationFindingKind.MISSING_ENTITY,
					detail=(
						f"entity {entity.name!r} is owned by module(s) the decomposition "
						f"does not declare: {', '.join(absent)} (FR-115)"
					),
					modules=(),
					evidence=tuple(f"{entity.name} -> {name}" for name in absent),
				)
			)
	return tuple(findings)


def check_model_is_the_interface_source(
	decomposition: Decomposition,
	model: SystemModel,
	*,
	module_for_clause: Mapping[str, str],
) -> tuple[IntegrationFinding, ...]:
	"""FR-083: is the model actually the single source for interface definitions?

	The requirement's second clause is the one that has been open since ADR-0027: the
	model "must be **the single source for interface definitions**. Hand-written
	interfaces that disagree with the model are an integration defect by construction."
	ADR-0027 made FR-112 checkable by declaring a surface on :class:`Module`, which is a
	declaration *beside* the model — so a model and a module could hold two opinions about
	one module's public names and nothing said which was the truth.

	The check has two halves, and they are the two ways a model stops being the source:

	1. **An interface no module is bound to.** The model declares a surface and the
	decomposition never asked anyone to expose it, so the declaration reached nothing.
	This is :data:`~sofact.views.IntegrationFindingKind.MODEL_INTERFACE_NOT_BOUND`, and
	it is a *decomposition* defect — the repair is a revised decomposition, not a
	rebuilt module, which is why its ``modules`` is empty rather than naming a guess.
	2. **A module whose declared surface is not the one the model derives.** Since
	:func:`~sofact.decomposition.propose` derives the surface from the model, this
	cannot happen on a proposal; it happens on a module revised by hand or by a future
	proposer that stopped reading the model, which is exactly the drift FR-084 makes
	expensive. The comparison is by name and kind, not by the whole member: a
	parameter list that differs is FR-112's ``wrong_arity``, reported against the build
	where the build is the evidence.

	``model.interfaces`` empty means nothing was declared, and the check reports nothing
	rather than passing — the absence is owned by the P2 gate's ``system_model_declared``,
	and a check that manufactured findings for a project with no model would make every
	run red until the model was authored, which is the pressure that gets a gate disabled.
	"""
	findings: list[IntegrationFinding] = []
	if not model.interfaces:
		return ()
	bound = {
		interface.name: {
			module_for_clause[clause_id]
			for clause_id in interface.clause_ids
			if clause_id in module_for_clause
		}
		for interface in model.interfaces
	}
	for interface in model.interfaces:
		if not bound[interface.name]:
			findings.append(
				IntegrationFinding(
					kind=IntegrationFindingKind.MODEL_INTERFACE_NOT_BOUND,
					detail=(
						f"the model declares interface {interface.name!r} over "
						f"{len(interface.clause_ids)} clause(s) and no module owns any of "
						"them, so the system was never asked to expose it (FR-083)"
					),
					modules=(),
					evidence=tuple(
						f"{interface.name} -> clause {cid}" for cid in interface.clause_ids
					),
				)
			)
	for module in decomposition.modules:
		derived = {member.name: member for member in model.surface_for_clauses(module.clause_ids)}
		if not derived:
			# No interface reaches this module's clauses, so the model says nothing about
			# its surface and there is nothing to disagree with. Reporting the absence
			# here would double-count the unbound interface above.
			continue
		declared = {member.name: member for member in module.surface}
		for name in sorted(set(derived) - set(declared)):
			findings.append(
				IntegrationFinding(
					kind=IntegrationFindingKind.SURFACE_DISAGREES_WITH_MODEL,
					detail=(
						f"the model declares {name!r} for {module.name} through its clauses "
						"and the module's own surface does not carry it, so the model is "
						"not the single source for this module's interface (FR-083)"
					),
					modules=(module.name,),
					evidence=(f"{module.name}: model declares {name}",),
				)
			)
		for name in sorted(set(declared) - set(derived)):
			findings.append(
				IntegrationFinding(
					kind=IntegrationFindingKind.SURFACE_DISAGREES_WITH_MODEL,
					detail=(
						f"{module.name} declares {name!r} on its surface and no interface "
						"in the model does, so the module holds an interface definition the "
						"model does not — a hand-written interface beside the model rather "
						"than from it (FR-083)"
					),
					modules=(module.name,),
					evidence=(f"{module.name}: declares {name}, which the model does not",),
				)
			)
	return tuple(findings)


def check_system_criteria(
	criteria: Sequence[SystemCriterion],
	*,
	verdicts: Mapping[str, VerdictOutcome],
	module_for_clause: Mapping[str, str],
) -> tuple[IntegrationFinding, ...]:
	"""FR-116: does the assembled system satisfy the criteria no module can?

	FR-116's criteria "validate the decomposition, not the modules", and the check is the
	one that makes that literal: a criterion spanning clauses is satisfied when **every**
	clause it spans carries a satisfied verdict. A criterion over clauses owned by two
	different modules is exactly a claim that those modules compose, which is the claim
	the decomposition made and can get wrong — and no single module's own verification
	could have caught it, which is what FR-116 asks integration to add.

	``verdicts`` is the latest verdict per clause across every module's report, and the
	caller passes the *worst* outcome a clause received. Reading only the latest report
	for one contract would let a criterion pass on the strength of a module that happened
	to be verified last, which is the same stale-evidence mistake FR-006 refuses one
	phase earlier.

	An ``INSUFFICIENT`` clause fails the criterion and is reported as insufficient rather
	than as violated: the two are different findings and collapsing them would report a
	clause nobody could check as a clause that was checked and failed.
	"""
	findings: list[IntegrationFinding] = []
	for criterion in criteria:
		unsatisfied = tuple(
			(clause_id, verdicts.get(clause_id, VerdictOutcome.INSUFFICIENT))
			for clause_id in criterion.clause_ids
			if verdicts.get(clause_id) is not VerdictOutcome.SATISFIED
		)
		if not unsatisfied:
			continue
		modules = tuple(
			sorted(
				{
					module_for_clause[clause_id]
					for clause_id, _ in unsatisfied
					if clause_id in module_for_clause
				}
			)
		)
		findings.append(
			IntegrationFinding(
				kind=IntegrationFindingKind.UNSATISFIED_SYSTEM_CRITERION,
				detail=(
					f"system criterion {criterion.statement[:60]!r} spans "
					f"{len(criterion.clause_ids)} clause(s) and {len(unsatisfied)} of them "
					"are not satisfied: "
					+ ", ".join(f"{cid} ({v.value})" for cid, v in unsatisfied)
				),
				modules=modules,
				evidence=(f"{criterion.criterion[:80]}",),
			)
		)
	return tuple(findings)


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


def public_surface(paths: Sequence[str], sources: dict[str, str]) -> tuple[InterfaceMember, ...]:
	"""The public names a module's files actually expose, read from their ASTs (FR-112).

	Python's public surface is the top-level names that do not begin with an underscore:
	module-level ``def`` and ``class`` statements, and module-level assignments. Nested
	definitions are not part of the module's surface — a method is reached through its
	class, and counting it here would report a difference the moment a producer added a
	private helper method.

	A file that does not parse contributes nothing, which is the same choice FR-113's
	analysis makes and for the same reason: judging syntax is the producer's language
	toolchain's job, not integration's.
	"""
	found: list[InterfaceMember] = []
	for path in paths:
		if not path.endswith(_SOURCE_SUFFIXES):
			continue
		text = sources.get(path)
		if text is None:
			continue
		try:
			tree = ast.parse(text)
		except SyntaxError:
			continue
		for node in tree.body:
			if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
				if node.name.startswith("_"):
					continue
				found.append(
					InterfaceMember(
						name=node.name,
						kind=InterfaceMemberKind.FUNCTION,
						parameters=tuple(
							arg.arg
							for arg in (
								*node.args.posonlyargs,
								*node.args.args,
								*node.args.kwonlyargs,
							)
						),
					)
				)
			elif isinstance(node, ast.ClassDef):
				if not node.name.startswith("_"):
					found.append(InterfaceMember(name=node.name, kind=InterfaceMemberKind.CLASS))
			elif isinstance(node, ast.Assign | ast.AnnAssign):
				for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
					if isinstance(target, ast.Name) and not target.id.startswith("_"):
						found.append(
							InterfaceMember(name=target.id, kind=InterfaceMemberKind.CONSTANT)
						)
	return tuple(found)


def check_interface_conformance(
	ownership: dict[str, tuple[str, ...]],
	*,
	declared: dict[str, tuple[InterfaceMember, ...]],
	sources: dict[str, str],
) -> tuple[IntegrationFinding, ...]:
	"""Diff each module's built public surface against the surface it declared (FR-112).

	Both directions, because FR-112 says the diff must be *empty* and an empty diff is
	symmetric. A declared name absent from the build is a module that did not deliver
	what it promised; a built name absent from the declaration is a module that widened
	its surface, which is how a producer quietly adds a second way in. Reporting only the
	first would let the second through, and the second is the one that matters for FR-090:
	the declared surface is what dependents are permitted to reach for.

	A module with no declared surface is not checked at all — there is nothing to diff —
	and the caller reports it as uncovered. That is the honest answer while nothing in a
	contract produces a machine-readable signature, and it is the difference between "the
	diff was empty" and "there was nothing to diff".
	"""
	assert sources, "cannot check interface conformance with no sources"
	findings: list[IntegrationFinding] = []
	for module in sorted(ownership):
		declaration = declared.get(module)
		if not declaration:
			continue
		built = {member.name: member for member in public_surface(ownership[module], sources)}
		wanted = {member.name: member for member in declaration}
		for name in sorted(set(wanted) - set(built)):
			findings.append(
				IntegrationFinding(
					kind=IntegrationFindingKind.MISSING_PUBLIC_NAME,
					detail=(
						f"{module} declared {name!r} on its surface and the build does not "
						"expose it (FR-112)"
					),
					modules=(module,),
					evidence=(f"{module}: {wanted[name].kind.value} {name}",),
				)
			)
		for name in sorted(set(built) - set(wanted)):
			findings.append(
				IntegrationFinding(
					kind=IntegrationFindingKind.UNDECLARED_PUBLIC_NAME,
					detail=(
						f"{module} exposes {name!r}, which its declared surface does not "
						"contain, so no dependent may rely on it (FR-090, FR-112)"
					),
					modules=(module,),
					evidence=(f"{module}: {built[name].kind.value} {name}",),
				)
			)
		for name in sorted(set(wanted) & set(built)):
			expected, actual = wanted[name], built[name]
			if expected.kind is not InterfaceMemberKind.FUNCTION:
				continue
			if len(expected.parameters) != len(actual.parameters):
				findings.append(
					IntegrationFinding(
						kind=IntegrationFindingKind.WRONG_ARITY,
						detail=(
							f"{module}.{name} was declared with "
							f"{len(expected.parameters)} parameter(s) and built with "
							f"{len(actual.parameters)} (FR-112)"
						),
						modules=(module,),
						evidence=(
							f"{module}: {name}({', '.join(expected.parameters)}) declared, "
							f"({', '.join(actual.parameters)}) built",
						),
					)
				)
	return tuple(findings)


def _reached_names(tree: ast.Module) -> tuple[tuple[str, tuple[str, ...]], ...]:
	"""Every name a file reaches for on another module, as ``(module, names)`` pairs (FR-110).

	Only ``from X import a, b`` yields names, because only that form *names* what it
	reaches for. ``import X`` followed by ``X.foo`` reaches ``foo`` too, but the reach is
	an attribute access somewhere below the import, and following it is the same
	whole-program analysis FR-113 declines to attempt — so it is left unexamined and the
	check reports it as uncovered rather than pretending it looked.

	A star import is returned with the single name ``*``, which the caller treats as
	uncheckable: ``from X import *`` reaches every public name X has, and the set is
	whatever X happened to define rather than a list this can compare.
	"""
	pairs: list[tuple[str, tuple[str, ...]]] = []
	for node in ast.walk(tree):
		if isinstance(node, ast.ImportFrom) and not node.level and node.module:
			pairs.append((node.module, tuple(alias.name for alias in node.names)))
	return tuple(pairs)


def check_boundary_contracts(
	ownership: dict[str, tuple[str, ...]],
	*,
	declared: dict[str, tuple[InterfaceMember, ...]],
	dependencies: dict[str, set[str]],
	sources: dict[str, str],
) -> tuple[IntegrationFinding, ...]:
	"""Does each module reach only for names its dependency declared? (FR-110, O8)

	O8's question, and the one neither neighbour asks. :func:`check_imports` establishes
	that the *edge* was declared — and it is satisfied by a ``depends_on`` naming the right
	module, whatever the consumer then does with it. :func:`check_interface_conformance`
	compares a module against its *own* declaration. So a consumer can import a declared
	dependency and call a name that module never promised, and every check passes while the
	assembled system does not run.

	Only *declared* edges are examined. An undeclared one is already FR-113's finding, and
	reporting it here too would name one defect twice under two requirement ids — the
	mistake :func:`check_model_is_the_interface_source` exists to avoid. What this adds is
	the case FR-113 clears: the edge is declared, and the name reached across it is not on
	the producer's surface.

	A producer that declares no surface cannot be checked, and the caller reports it as
	uncovered rather than as conforming — the same distinction FR-112 draws between an
	empty diff and no diff. ``dependencies`` maps module name to the names of the modules
	it declared in ``depends_on``; a reach into a module that is not in that set is left to
	FR-113.
	"""
	assert ownership, "cannot check boundary contracts with no attributed files"
	known = {path for paths in ownership.values() for path in paths}
	findings: list[IntegrationFinding] = []
	for consumer in sorted(ownership):
		allowed = dependencies.get(consumer, set())
		for path in ownership[consumer]:
			if not path.endswith(_SOURCE_SUFFIXES):
				continue
			text = sources.get(path)
			if text is None:
				continue
			try:
				tree = ast.parse(text)
			except SyntaxError:
				continue
			for imported, names in _reached_names(tree):
				if names == ("*",):
					continue
				target = _resolve(imported, path, known)
				if target is None or target in ownership[consumer]:
					continue
				owner = _module_of_path(target, ownership)
				if owner is None or owner == consumer or owner not in allowed:
					continue
				surface = declared.get(owner)
				if not surface:
					continue
				promised = {member.name for member in surface}
				for name in names:
					if name in promised:
						continue
					findings.append(
						IntegrationFinding(
							kind=IntegrationFindingKind.UNSATISFIED_BOUNDARY_CONTRACT,
							detail=(
								f"{consumer} reaches {owner}.{name} through its declared "
								f"dependency, and {owner}'s surface does not declare {name!r} "
								"(FR-110)"
							),
							modules=(consumer, owner),
							evidence=(f"{path}: from {imported} import {name}",),
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
	model: SystemModel | None = None,
	criteria: Sequence[SystemCriterion] = (),
	verdicts: Mapping[str, VerdictOutcome] | None = None,
) -> IntegrationReport:
	"""Run P7's checks over a plan's dispatched work and report what passed and what did not.

	Deterministic and model-free. Every input is a record the factory already holds: the
	plan, the approved decomposition, the dispatches with their checkouts. Nothing is
	re-run and nothing is asked of a producer, so a report is reproducible from the log —
	which is what makes it evidence rather than an assertion about a run.

	``model``, ``criteria`` and ``verdicts`` are P2's and P6's artefacts, and they are
	parameters rather than something this module reads because the service holds the log
	and this function holds none. Absent ``model`` or ``criteria`` is the *honest* state
	of a project whose specification declared neither, and FR-115/FR-116 are then reported
	as unimplemented rather than as passing — the same distinction FR-112 already draws
	between an empty diff and no diff.

	The per-module budget FR-026 and FR-097 ask for is read from the **decomposition**
	rather than taken as a parameter, for the reason :meth:`FactoryService.check_integration`
	gives about the module graph: a caller that could supply the budget map could supply one
	that makes an oversized module look within bounds, and the budget is exactly the number
	the check is supposed to hold the build to. ``Module.budget`` is required, so every
	module the decomposition names carries one and no module is silently unchecked.
	"""
	assert plan.steps, "cannot integrate a plan with no steps"
	budgets: dict[str, ModuleBudget] = {
		module.name: module.budget for module in decomposition.modules
	}
	ownership, orphans = attribute_files(dispatches)
	declared = {
		module.name: {d.name for d in (decomposition.module(i) for i in module.depends_on) if d}
		for module in decomposition.modules
	}
	surfaces = {module.name: module.surface for module in decomposition.modules}
	# The clause-to-module map is built from the decomposition rather than from the
	# dispatches: FR-115 asks whether the assembled system matches the model, and a module
	# that was never dispatched is a module the system is missing. Reading ownership off
	# the dispatches would make a plan that skipped half its modules look conforming.
	module_for_clause: dict[str, str] = {
		clause_id: module.name
		for module in decomposition.modules
		for clause_id in module.clause_ids
	}
	build_findings = check_build_order(decomposition, dispatches)
	import_findings = (
		check_imports(ownership, declared=declared, root=root, sources=sources) if ownership else ()
	)
	# The surface check needs the *text*, not only the paths, so it reads once and the
	# import check reuses what it read -- two passes over the same files would be two
	# chances for them to disagree about what a file says.
	text = sources if sources is not None else (_read(root, ownership) if root else {})
	# FR-026's bound is checked over the same attribution FR-113 uses, and it needs the
	# text for the same reason the surface diff does: a line count is a property of bytes.
	# A caller that supplied neither a root nor sources has not asked for the artefact to
	# be read, which is a different state from an artefact that is missing -- the first
	# reports the bound as unexercised, and only the second is a finding.
	readable = sources is not None or root is not None
	budget_findings = (
		check_module_budget(ownership, budgets, sources=text) if ownership and readable else ()
	)
	declared_surfaces = {name: surface for name, surface in surfaces.items() if surface}
	conformance_findings = (
		check_interface_conformance(ownership, declared=declared_surfaces, sources=text)
		if ownership and declared_surfaces and text
		else ()
	)
	# O8 runs over the *declared* edges and the *declared* surfaces, which is the pair
	# FR-113 and FR-112 each hold one half of. It needs both: an edge to reach across and
	# a surface to compare the reach against, so with either missing there is no boundary
	# contract to check and the report says which state the project is in.
	boundary_findings = (
		check_boundary_contracts(
			ownership, declared=declared_surfaces, dependencies=declared, sources=text
		)
		if ownership and declared_surfaces and text
		else ()
	)
	model_findings = (
		check_model_conformance(decomposition, model, module_for_clause=module_for_clause)
		if model is not None and not model.is_empty
		else ()
	)
	# FR-083 is computed whenever a model exists, including one that declares no
	# interfaces -- the two states are different and the check's own detail says which.
	# Gating on `model.interfaces` here would make "the model declares no interfaces" and
	# "there is no model" print the same line, which is the distinction the whole report
	# is built to keep.
	model_interface_findings = (
		check_model_is_the_interface_source(
			decomposition, model, module_for_clause=module_for_clause
		)
		if model is not None
		else ()
	)
	criterion_findings = check_system_criteria(
		criteria,
		verdicts=verdicts or {},
		module_for_clause=module_for_clause,
	)
	findings = (
		*build_findings,
		*import_findings,
		*budget_findings,
		*conformance_findings,
		*boundary_findings,
		*model_findings,
		*model_interface_findings,
		*criterion_findings,
	)
	conformed = tuple(sorted(e.name for e in (model.entities if model is not None else ())))
	# The interfaces the model declares, as objects rather than names: the check below
	# needs each one's clauses, and a name-keyed lookup would be a second way to reach
	# what the model already holds.
	declared_interfaces = model.interfaces if model is not None else ()
	model_interfaces = tuple(interface.name for interface in declared_interfaces)
	bound_interfaces = tuple(
		sorted(
			{
				module_for_clause[clause_id]
				for interface in declared_interfaces
				for clause_id in interface.clause_ids
				if clause_id in module_for_clause
			}
		)
	)
	criterion_clauses = tuple(sorted({cid for c in criteria for cid in c.clause_ids}))
	verdict_source = "the log's latest verdict per clause" if verdicts else "no verdicts"

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
	diffed = tuple(name for name in built if declared_surfaces.get(name))
	undiffed = tuple(name for name in built if not declared_surfaces.get(name))
	# An edge is checkable when the consumer was built and the module it reaches declares
	# a surface to compare the reach against. Both ends matter: a declared edge into a
	# module with no surface is a boundary nothing can be said about, and counting it as
	# checked would be the vacuous pass FR-110's whole premise warns about.
	borders = tuple(
		sorted(
			f"{consumer} -> {owner}"
			for consumer in built
			for owner in declared.get(consumer, set())
			if declared_surfaces.get(owner)
		)
	)
	unbordered = tuple(
		sorted(
			f"{consumer} -> {owner}: {owner} declares no surface, so the reach across it "
			"was not compared against anything"
			for consumer in built
			for owner in declared.get(consumer, set())
			if not declared_surfaces.get(owner)
		)
	)
	# A module is *measured* only when it sealed at least one file and every one of them
	# could be read. A module that sealed nothing has no artefact for a bound to be about,
	# and one whose files were not read has a bound that is unmeasured rather than met —
	# both are named in `uncovered` rather than counted as inside the budget (NFR-024).
	budgeted = tuple(
		name for name in built if name in budgets and all(path in text for path in ownership[name])
	)
	unbuilt = tuple(name for name in sorted(budgets) if name not in built)
	unread = tuple(
		name
		for name in built
		if name in budgets and not all(path in text for path in ownership[name])
	)

	checks = (
		IntegrationCheck(
			name="boundary_contracts",
			passed=not boundary_findings,
			detail=(
				f"{len(borders)} declared boundary(ies) checked; every name reached across "
				"one is on the producer's declared surface (FR-110)"
				if borders and not boundary_findings
				else f"{len(boundary_findings)} name(s) reached across a declared boundary "
				"that the producer never declared"
				if boundary_findings
				else "no module declared both a surface and a dependency on another module "
				"that declares one, so no boundary contract was exercised"
			),
			requirements=("FR-110",),
			covered=tuple(f"{edge}: every name reached across it is declared" for edge in borders),
			uncovered=(
				*unbordered,
				*(
					f"{name}: no declared surface, so a reach into it was not compared"
					for name in undiffed
				),
				"only `from X import a, b` reaches are seen; `import X` followed by `X.foo` "
				"reaches the same surface through an attribute access this analysis does not "
				"follow",
				"`from X import *` is not checked: the names it reaches are whatever X "
				"happened to define, not a list this can compare",
				"an undeclared edge is FR-113's finding and is not reported here; this "
				"check is about what crossed a boundary that was declared",
			),
		),
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
		IntegrationCheck(
			name="module_budget",
			passed=not budget_findings,
			detail=(
				f"{len(budgeted)} module(s) measured against the budget their contract "
				"declared, and every one is inside it (FR-026, FR-097)"
				if budgeted and not budget_findings
				else f"{len(budget_findings)} module(s) over the budget their contract declared"
				if budget_findings
				else "no module sealed a file, so no budget had an artefact to measure"
			),
			requirements=("FR-026", "FR-097"),
			covered=tuple(
				f"{name}: {len(ownership[name])} file(s) counted against "
				f"{budgets[name].max_files}, {_count_lines_all(text, ownership[name])} "
				f"line(s) against {budgets[name].max_loc}"
				for name in budgeted
			),
			uncovered=(
				*(f"{name}: sealed nothing, so its bound was not exercised" for name in unbuilt),
				*(
					f"{name}: its files were not read, so its bound is unmeasured"
					for name in unread
				),
				"the bound is on the built artefact, not on the diff: a repository-wide "
				"diff names no module, and FR-114's repair scope needs one",
				"a blank line is not counted and a comment line is; which lines a comment "
				"occupies is a property of a language ADR-0025 leaves open",
			),
		),
		IntegrationCheck(
			name="interface_conformance",
			passed=not conformance_findings,
			detail=(
				f"{len(diffed)} module(s) diffed against their declared surface; the diff is empty"
				if diffed and not conformance_findings
				else f"{len(conformance_findings)} difference(s) between a declared and a built surface"
				if conformance_findings
				else "no module declared a machine-readable surface, so nothing was diffed"
			),
			requirements=("FR-112",),
			covered=tuple(
				f"{name}: declared surface diffed against the built public names" for name in diffed
			),
			uncovered=(
				*(
					f"{name}: no declared surface, so the diff had nothing to compare"
					for name in undiffed
				),
				"parameter *types* are not compared; a declared surface carries names and "
				"arity because SoFact does not know the operator's language (ADR-0025)",
				"a name's kind is not compared; a declared constant built as a function "
				"reports only if its arity differs",
			),
		),
		IntegrationCheck(
			name="model_interface_source",
			passed=not model_interface_findings,
			detail=(
				f"{len(model_interfaces)} model interface(s) bound to "
				f"{len(bound_interfaces)} module(s), and every module's declared surface is "
				"the one the model derives for its clauses (FR-083)"
				if model_interfaces and not model_interface_findings
				else f"{len(model_interface_findings)} disagreement(s) between the model and "
				"the surfaces derived from it"
				if model_interface_findings
				else "the model declares no interfaces, so it is not yet the source for any"
				if model is not None
				else "the specification declared no system model, so there is no source"
			),
			requirements=("FR-083",),
			covered=tuple(
				f"{interface.name}: bound to {module_for_clause[cid]}"
				for interface in declared_interfaces
				for cid in interface.clause_ids
				if cid in module_for_clause
			),
			uncovered=(
				*(
					f"{interface.name}: its clauses reach no module, so nothing was asked "
					"to expose it"
					for interface in declared_interfaces
					if not any(cid in module_for_clause for cid in interface.clause_ids)
				),
				"the model is compared against the *declared* surfaces, not against the "
				"build: whether a declared name exists in the code is FR-112's diff, and "
				"running it here would report one defect twice under two requirement ids",
				"a member's parameters are not compared here; an arity difference between "
				"a derived and a declared surface is FR-112's `wrong_arity`",
			)
			if model is not None and model.interfaces
			else (
				"no interface is declared in the model, so FR-083's single-source clause "
				"is unexercised — ADR-0027's state, and the reason the requirement stayed "
				"half-discharged until the model carried interfaces",
			),
		),
		IntegrationCheck(
			name="model_conformance",
			passed=not model_findings,
			detail=(
				f"{len(conformed)} declared entity(ies) owned by a module the decomposition "
				"names, so the assembled system matches the model"
				if conformed and not model_findings
				else f"{len(model_findings)} entity(ies) the assembled system does not match"
				if model_findings
				else "the specification declared no system model, so nothing was conformed"
			),
			requirements=("FR-115",),
			covered=tuple(
				f"{name}: an entity whose introducing clause a module owns" for name in conformed
			),
			uncovered=(
				"relationships and invariants are declared and not conformed: an entity's "
				"presence is decidable from the clause-to-module map, while a relationship "
				"between two entities is a claim about their *interaction*, which no "
				"declaration in the log describes (FR-115, FR-078)",
				"the model is conformed against the decomposition, not against the built "
				"code: FR-115 asks whether the assembled system satisfies the model, and "
				"what this measures is whether the modules that were planned to satisfy it "
				"exist and are named",
			)
			if model is not None and not model.is_empty
			else ("no system model was declared, so no entity was conformed",),
		),
		IntegrationCheck(
			name="system_criteria",
			passed=not criterion_findings,
			detail=(
				f"{len(criteria)} system criterion(s) over {len(criterion_clauses)} "
				"clause(s); every one satisfied"
				if criteria and not criterion_findings
				else f"{len(criterion_findings)} system criterion(s) not satisfied"
				if criterion_findings
				else "P2 declared no system-level criteria, so nothing spanned modules"
			),
			requirements=("FR-116",),
			covered=tuple(
				f"{c.statement[:50]}: every clause it spans carries a satisfied verdict"
				for c in criteria
			),
			uncovered=(
				(
					f"verdicts come from {verdict_source}; a clause with no verdict at all "
					"counts as insufficient rather than as satisfied",
					"a criterion is satisfied when its clauses are, which is a claim about "
					"the modules composing -- it does not run the criterion, because a "
					"system-level criterion is not in the contract's oracle set and there "
					"is no command to run (FR-116)",
				)
				if criteria
				else ("no system-level criteria were declared at P2",)
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
