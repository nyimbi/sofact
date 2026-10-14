"""Oracle manufacturing: a check built from structure the factory already owns.

FR-103 ranks seven ways to manufacture an oracle, strongest first, and this module is the
seam that decides which of them a given clause can have. It is a *seam* rather than a
builder because the honest answer is often "not this one", and a builder that always
returned something would be manufacturing confidence rather than checks.

Four properties are load-bearing.

**The seam is async because it runs processes.** Earning a hint means launching the
artefact and then re-running it against an empty tree, and a synchronous method inside an
async pipeline has only bad options: a nested event loop (which raises), or a second
process-launch path that would not carry the boundary. The project is async throughout, and
this is the reason rather than the style.

**A refusal is a return value, not an exception.** "This rank cannot be built from the
structured data available" is an ordinary outcome: most of FR-103's table needs a declared
invariant or a declared state machine, and a contract whose clauses are English prose
declares neither. Raising would make the common case look like a fault, and would push
callers toward a bare ``except`` that swallows the uncommon real ones.

**The hint is earned, never fabricated.** :func:`~sofact.contract.suggest_oracle` keeps
that invariant by abstaining; manufacturing keeps it by *earning* it. The assertions run
at the seam, on the artefact, before any declaration is built, and a backend cannot skip
them because it does not run them: it returns a path and an argv, and this module decides
whether the two describe a command that exists.

**A manufactured oracle that passes on an empty tree is refused.** That is FR-107's
adversarial audit, and it is a *precondition* here rather than a separate procedure. The
same argv is re-run against a directory holding the artefact and nothing else, and an exit
of zero there means the check is satisfied by nothing. A vacuous oracle is worse than a
missing one — FR-107's own words are that it "manufactures false confidence" — so it never
reaches a contract.

**Rank 6 is refused before any backend is consulted.** ``held_out`` is ``oracle_class is
OracleClass.EXAMPLE`` and :func:`~sofact.contract.suggest_oracle` asserts that a suggestion
is never held out, so the factory's own example would be withheld from the factory's own
producer. A backend able to return one would re-open FR-106 by the manufacturing door, and
the door is closed here rather than in each backend.

The factory's own data is the limit, and it is worth naming. ``Module.surface`` is the one
machine-readable signature source a proposal carries — a name, a kind and an arity per
member. Declared entities, invariants and criteria are English, and deriving a *predicate*
from English is fabrication, not manufacturing. So this module builds what a declared
surface supports, refuses the rest by name, and leaves the refusal visible as ground-truth
debt (FR-108) rather than as a plausible-looking check.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import shlex
import tempfile
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Final, Protocol, TypeGuard, cast

from sofact.boundary import boundary_env, wrap_argv
from sofact.views import (
	ClauseKind,
	ManufactureRefusal,
	ManufactureRefusalReason,
	DeploymentBoundary,
	EvidenceKind,
	InterfaceMember,
	OracleClass,
	OracleDeclaration,
)

__all__ = [
	"BACKENDS",
	"MANUFACTURE_SPECS",
	"ConfiguredManufactureAdapter",
	"ManufactureBackend",
	"ManufactureRefusal",
	"ManufactureRefusalReason",
	"ManufactureRequest",
	"ManufactureSpec",
	"ManufacturedOracle",
	"artefact_index",
	"copy_artefacts",
	"load_manufacture_specs",
	"manufacture_declarations",
	"manufacture_spec_for",
	"place_artefacts",
	"refusal",
	"slug",
]

DEFAULT_MANUFACTURE_TIMEOUT_SECONDS: Final = 120.0
"""How long one manufacturing run may take.

The artefact is a check the factory wrote moments ago over a tree the factory controls, so
a run that has not finished in two minutes is not slow, it is wrong — a check that walks a
dependency tree, or that waits on a network. Both are refused rather than waited for.
"""


@dataclass(frozen=True)
class ManufactureRequest:
	"""One clause, the module that owes it, and the surface that module declared.

	The surface travels on the request rather than being looked up by the backend, because
	the backend has no way to find it: it is P3's proposal, held in the log, and a backend
	that went looking would be reading the factory's state to decide what the factory meant.
	"""

	clause_id: str
	statement: str
	kind: ClauseKind
	oracle_class: OracleClass
	module_name: str
	surface: tuple[InterfaceMember, ...]
	workspace: Path

	def __post_init__(self) -> None:
		assert self.clause_id, "a manufacturing request names a clause"
		assert self.statement.strip(), "a manufacturing request carries the clause's words"
		assert self.module_name.strip(), "a manufacturing request names the module that owes it"

	@property
	def slug(self) -> str:
		"""The module's name as an identifier in the target language."""
		return slug(self.module_name)


def render_argv(
	spec: ManufactureSpec, artefact: Path, output: Path | None = None
) -> tuple[str, ...]:
	"""The spec's run template with the artefact and the build product substituted.

	One function rather than a rule each backend re-implements, because the seam has to
	locate the artefact element in the result and compare it against the path the backend
	wrote: a backend that placed the artefact somewhere unexpected would have its own
	command's artefact argument read as something else, and the comparison would pass on a
	mismatch. Substituting here means the placement is the spec's, and the spec is data.
	"""
	rendered: list[str] = []
	for part in spec.run_argv:
		text = part.replace("{artefact}", str(artefact))
		if output is not None:
			text = text.replace("{output}", str(output))
		rendered.append(text)
	assert any(str(artefact) in part for part in rendered), (
		f"the {spec.language} run argv does not name the artefact after substitution"
	)
	return tuple(rendered)


def artefact_index(spec: ManufactureSpec) -> int:
	"""Which element of the rendered argv is the artefact, by construction."""
	index = next(
		(position for position, part in enumerate(spec.run_argv) if "{artefact}" in part),
		None,
	)
	assert index is not None, f"the {spec.language} run argv must name {{artefact}}"
	return index


@dataclass(frozen=True)
class ManufacturedOracle:
	"""An artefact on disk and the command that checks with it.

	``argv`` is the command, split, rather than a shell string: the seam resolves
	``argv[artefact_argument]`` against the workspace and requires it to *be* the file the
	backend wrote, and a shell string cannot be compared that way without re-implementing
	shell quoting. :attr:`command_hint` joins it back for the declaration, because that is
	what :class:`~sofact.execution.OracleRunner` executes.

	``artefact_argument`` is an index rather than a convention, because the seam has to
	prove the artefact the command names is the artefact that was written, and only the
	command itself can say which element that is.
	"""

	path: Path
	argv: tuple[str, ...]
	artefact_argument: int
	provenance: str
	"""How the check was derived, in the factory's words — the rank's structured source.

	Recorded because FR-118 asks which oracle established a clause, and "a rank-3 contract
	check" is not an answer a reader can act on. "declared surface: 3 member(s) of module
	'ledger'" is.
	"""

	observed_exit_code: int = 0
	"""What the command returned when the seam ran it. Filled in by the seam, not the backend."""

	output: Path | None = None
	"""A build product the command leaves behind, which the seam removes after running.

	``rustc`` needs one: it writes ``.rmeta`` beside its ``-o`` target, so ``-o /dev/null``
	fails with "couldn't create a temp dir" rather than compiling. The path is named at
	manufacture time because it has to be in the argv the declaration carries, and the seam
	deletes it afterwards because a compiled binary inside the workspace would be committed
	by the seal and folded into FR-006's cache key — a build product is not the change under
	test, and a digest that moved because of one would invalidate a verdict nothing touched.
	"""

	@property
	def command_hint(self) -> str:
		"""The command as one shell string, which is what a declaration carries."""
		assert self.argv, "a manufactured oracle names a command"
		return shlex.join(self.argv)

	@property
	def evidence_kind(self) -> EvidenceKind:
		"""What a run of this artefact produces: a command's exit status and its output.

		Derived rather than stored, and that is the point. ``OracleRunner`` produces
		:attr:`~sofact.views.EvidenceKind.COMMAND_OUTPUT` and nothing else, so a backend
		declaring ``TEST_RESULT`` or ``PROPERTY_RUN`` would be describing evidence no
		component in this build emits — and ``verification`` would judge the payload by a
		rule written for a producer that does not exist. A field that could only ever hold
		one value is a field that lies about being a choice.
		"""
		return EvidenceKind.COMMAND_OUTPUT


def refusal(
	request: ManufactureRequest,
	reason: ManufactureRefusalReason,
	detail: str,
) -> ManufactureRefusal:
	"""A refusal that names its clause and its rank, built from the request.

	One constructor rather than a literal at each site, because the two facts a refusal
	cannot be read without — which clause, which rank — are exactly the two the request
	already carries, and a site that passed them by hand could pass the wrong ones.
	"""
	return ManufactureRefusal(
		clause_id=request.clause_id,
		oracle_class=request.oracle_class,
		reason=reason,
		detail=detail,
	)


ManufactureOutcome = ManufacturedOracle | ManufactureRefusal


class ManufactureBackend(Protocol):
	"""One target language's manufacturing rules.

	Deliberately three members. A backend that also *ran* its artefact, or *judged* whether
	the run meant anything, would own the gate as well as the generator — and the gate is
	the half a backend must not be able to reach, because a backend is the part a deployment
	replaces.
	"""

	@property
	def language(self) -> str:
		"""The target language this backend builds for."""
		...

	def supports(self, oracle_class: OracleClass) -> bool:
		"""Whether this backend builds this rank. ``False`` is a supported answer."""
		...

	async def manufacture(self, request: ManufactureRequest) -> ManufactureOutcome:
		"""Write the artefact and return it, or refuse by name."""
		...


# --------------------------------------------------------------------------- #
# the spec, read the way a harness spec is read
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ManufactureSpec:
	"""A deployment's manufacturing configuration for one language (FR-156, D5).

	Data rather than code, for the reason :class:`~sofact.harness.HarnessSpec` is: a
	deployment that wants a fourth language should describe it in a file, and "which
	languages does this factory build oracles in" should be one thing to read rather than a
	property of import order.
	"""

	language: str
	backend: str
	"""The registered backend's name. Resolved by :func:`backends_for`, refused by name."""

	artefact_directory: str
	"""Where artefacts are written, relative to the workspace.

	One directory rather than a path per clause, so a worktree copy is one directory and so
	a reader can tell the factory's checks from the producer's tests at a glance.
	"""

	source_suffixes: tuple[str, ...]
	"""Extensions the artefact searches when it looks for the module it checks."""

	run_argv: tuple[str, ...]
	"""How to run an artefact, as a template. ``{artefact}`` is replaced by its path.

	A template rather than a fixed argv because the interpreter is a deployment's business:
	``python3`` and ``python3.12`` are the same language and different hosts.
	"""

	notes: str = ""

	def __post_init__(self) -> None:
		assert self.language.strip(), "a manufacture spec names a language"
		assert self.backend.strip(), "a manufacture spec names a backend"
		assert self.artefact_directory.strip(), "a manufacture spec names where artefacts go"
		assert self.source_suffixes, "a manufacture spec names the extensions it searches"
		assert "{artefact}" in " ".join(self.run_argv), (
			f"the {self.language} run argv must name the artefact, or the check cannot be run"
		)
		if any("{output}" in part for part in self.run_argv):
			# A spec that names a build product must name one the backend can place, and the
			# only way it can is if the artefact is a path the backend chose. Stated as an
			# assertion because a spec naming `{output}` with no `{artefact}` would render a
			# command that compiles something unnamed into somewhere unknown.
			assert "{artefact}" in " ".join(self.run_argv), (
				f"the {self.language} run argv names an output but no artefact, so the build "
				"product has no directory to sit in"
			)

	@classmethod
	def from_mapping(cls, name: str, payload: Mapping[str, object]) -> ManufactureSpec:
		"""Build a spec from a JSON-shaped mapping, refusing unknown fields by name.

		A misspelled ``run_arg`` that silently fell back to the default would produce a
		command that runs the wrong thing, which is worse than an error: the artefact would
		exist, the check would execute, and the verdict would be about something else.
		"""
		declared = {field.name for field in fields(cls)}
		unknown = sorted(set(payload) - declared)
		if unknown:
			raise ValueError(f"manufacture {name!r}: unknown field(s) {unknown}")
		required = ("language", "backend", "artefact_directory", "source_suffixes", "run_argv")
		missing = [field for field in required if field not in payload]
		if missing:
			raise ValueError(f"manufacture {name!r}: missing field(s) {missing}")
		changes: dict[str, object] = {}
		for field in ("language", "backend", "artefact_directory", "notes"):
			if field in payload:
				changes[field] = _text(payload[field], field, name)
		for field in ("source_suffixes", "run_argv"):
			changes[field] = _texts(payload[field], field, name)
		return cls(**changes)  # pyright: ignore[reportArgumentType]


def _text(value: object, field: str, name: str) -> str:
	if not isinstance(value, str):
		raise ValueError(f"manufacture {name!r}: {field} must be a string")
	return value


def _texts(value: object, field: str, name: str) -> tuple[str, ...]:
	if isinstance(value, str) or not isinstance(value, Sequence):
		raise ValueError(f"manufacture {name!r}: {field} must be an array of strings")
	items = cast("Sequence[object]", value)
	out: list[str] = []
	for item in items:
		if not isinstance(item, str):
			raise ValueError(f"manufacture {name!r}: {field} must contain only strings")
		out.append(item)
	return tuple(out)


def _str_keyed(value: object) -> TypeGuard[Mapping[str, object]]:
	if not isinstance(value, dict):
		return False
	obj = cast("Mapping[object, object]", value)
	return all(isinstance(key, str) for key in obj)


def load_manufacture_specs(path: Path) -> dict[str, ManufactureSpec]:
	"""Read a manufacturing table from a JSON file (FR-156).

	Two shapes, as :func:`~sofact.harness.load_specs` accepts: ``{"languages": {...}}`` and
	a bare ``{name: {...}}``. In the bare form no language may be called ``languages``,
	because that is the one key this reader treats as structure rather than as a name.
	"""
	try:
		text = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise ValueError(f"cannot read manufacture table {path}: {exc}") from exc
	try:
		raw: object = json.loads(text)
	except ValueError as exc:
		raise ValueError(f"{path}: not valid JSON: {exc}") from exc
	if not _str_keyed(raw):
		raise ValueError(f"{path}: expected a JSON object")
	body: object = raw["languages"] if set(raw) == {"languages"} else raw
	if not _str_keyed(body):
		raise ValueError(f"{path}: expected an object of manufacture specs under 'languages'")
	specs: dict[str, ManufactureSpec] = {}
	for name, payload in body.items():
		if not _str_keyed(payload):
			raise ValueError(f"{path}: language {name!r} must be an object")
		specs[name] = ManufactureSpec.from_mapping(name, payload)
	if not specs:
		raise ValueError(f"{path}: no languages; an empty table names nothing to manufacture")
	return specs


MANUFACTURE_SPECS: Mapping[str, ManufactureSpec] = {
	"python": ManufactureSpec(
		language="python",
		backend="python",
		artefact_directory=".sofact-oracles",
		source_suffixes=(".py",),
		run_argv=("python3", "{artefact}"),
		notes=(
			"D5's ruling, encoded as data rather than as a branch: Python is the language "
			"the factory builds in by default, and the other two are registered beside it "
			"rather than behind a flag. FR-156 is the reason this is a table."
		),
	),
	"typescript": ManufactureSpec(
		language="typescript",
		backend="typescript",
		artefact_directory=".sofact-oracles",
		source_suffixes=(".ts", ".tsx"),
		run_argv=(
			"tsc",
			"--noEmit",
			"--strict",
			"--module",
			"esnext",
			"--moduleResolution",
			"bundler",
			"{artefact}",
		),
		notes=(
			"The compiler is the instrument: a missing export is a type error rather than "
			"a failed comparison, so the check cannot disagree with the module's real "
			"surface."
		),
	),
	"rust": ManufactureSpec(
		language="rust",
		backend="rust",
		artefact_directory=".sofact-oracles",
		source_suffixes=(".rs",),
		run_argv=("rustc", "--test", "--edition", "2021", "-o", "{output}", "{artefact}"),
		notes=(
			"`--test` compiles *and* runs, so the artefact is decided at compile time and "
			"the test body is the evidence that it ran at all."
		),
	),
}
"""The languages this build manufactures oracles for, and the D5 ruling in one place.

A mapping rather than three branches in the seam, because which languages a factory builds
in is a deployment's answer: ``SOFACT_MANUFACTURE`` replaces this table wholesale, and an
unknown ``backend`` name is refused by name rather than falling back to Python — a silent
fallback would run a Python check against a Rust module and report the resulting failure as
a defect in the module.
"""


def manufacture_spec_for(
	name: str,
	specs: Mapping[str, ManufactureSpec] | None = None,
) -> ManufactureSpec:
	"""Look up a spec by language, raising a useful error when it is unknown."""
	table = MANUFACTURE_SPECS if specs is None else specs
	spec = table.get(name)
	if spec is None:
		known = ", ".join(sorted(table)) or "none"
		raise KeyError(f"unknown manufacturing language {name!r}; configured: {known}")
	return spec


# --------------------------------------------------------------------------- #
# the backends this build ships
# --------------------------------------------------------------------------- #


BACKENDS: Mapping[str, str] = {
	"python": "sofact.manufacture_python:PythonManufactureBackend",
	"typescript": "sofact.manufacture_typescript:TypeScriptManufactureBackend",
	"rust": "sofact.manufacture_rust:RustManufactureBackend",
}
"""Registered backends, as ``module:Class`` strings rather than as imported classes.

A string registry because the dependency is a cycle: a backend imports this module for its
types, so importing the backends here would import a partially-initialised module and fail
on the first name it asked for — measured, not reasoned about. Resolving the name at first
use keeps the seam's knowledge of the backends to a name, and the name is what a spec
writes, so there is exactly one place a backend is registered and exactly one place an
unknown one is refused.
"""


def backends_for(spec: ManufactureSpec) -> ManufactureBackend:
	"""The backend a spec names, built for that spec.

	An unknown name is refused **by name** rather than falling back to Python. A silent
	fallback would run a Python check against a TypeScript module: the artefact would exist,
	the command would run, the exit code would be non-zero, and every layer would report a
	genuine failure of the module rather than a misconfiguration.
	"""
	entry = BACKENDS.get(spec.backend)
	if entry is None:
		known = ", ".join(sorted(BACKENDS)) or "none"
		raise KeyError(
			f"manufacture spec {spec.language!r} names backend {spec.backend!r}, which is "
			f"not one of: {known}"
		)
	module_name, _, class_name = entry.partition(":")
	module = importlib.import_module(module_name)
	built: object = getattr(module, class_name, None)
	assert built is not None, f"{entry} names a class {module_name} does not define"
	constructor = cast("Callable[[ManufactureSpec], ManufactureBackend]", built)
	return constructor(spec)


def place_artefacts(declaration: OracleDeclaration, *, workspace: Path) -> tuple[Path, ...]:
	"""The files a declaration's command reads, as paths relative to ``workspace``.

	Read out of the command rather than recorded beside it, because the command is what
	:class:`~sofact.execution.OracleRunner` executes and a stored path that disagreed with
	it would copy a file the run never opens. A manifest that drifted from the argv is the
	same defect :func:`render_argv` exists to prevent, one phase later.

	An element is a path when it is not a flag, does not contain a shell or template
	metacharacter, and names a file that exists. That last clause is what makes the
	function honest rather than clever: ``python3`` is an element of every python argv and
	is not a path *inside the workspace*, so "exists under the workspace" is the test, not
	"looks like a path". A command naming no file the workspace holds returns an empty
	tuple, and the caller then dispatches with nothing placed — which is the correct
	behaviour for an oracle that reads only what the producer wrote.

	FR-141 is why this exists at all. Under ``isolate`` the session works in a worktree,
	and an artefact written at P4 sits in the shared tree — so a command that named it
	would run in the worktree, find nothing, and report a failure of the module. Copying is
	the fix and it is the *same* fix for the seal: the artefact travels with the module's
	branch because it is in the tree the seal commits.
	"""
	assert workspace.is_dir(), f"cannot place artefacts in a missing workspace: {workspace}"
	command = declaration.command_hint
	if command is None:
		return ()
	root = workspace.resolve()
	found: list[Path] = []
	for part in shlex.split(command):
		if part.startswith("-") or any(ch in part for ch in "{}*?[]$`|&;<>()"):
			continue
		candidate = Path(part)
		absolute = candidate if candidate.is_absolute() else (workspace / candidate)
		if not absolute.is_file():
			continue
		resolved = absolute.resolve()
		if resolved != root and root not in resolved.parents:
			# Outside the workspace: not this function's to place, and copying it would be
			# a way to smuggle a file the factory owns into the producer's tree.
			continue
		found.append(resolved.relative_to(root))
	return tuple(found)


def copy_artefacts(paths: Sequence[Path], *, source: Path, target: Path) -> tuple[Path, ...]:
	"""Copy ``paths`` from ``source`` into ``target``, returning what was written.

	``source`` is where manufacturing wrote them — the workspace the contract was built
	against. ``target`` is where the run will happen, which is the same directory in the
	sequential case and the module's worktree under FR-141's isolation.

	Idempotent, and the copy is unconditional rather than "skip if present": a re-contract
	(FR-096) rewrites an artefact in the source, and a worktree still holding the previous
	revision's copy would run the check the operator has since replaced. The bytes are the
	seam's output, not the producer's, so overwriting costs nothing a producer authored.
	"""
	written: list[Path] = []
	for path in paths:
		origin = source / path
		if not origin.is_file():
			raise FileNotFoundError(
				f"manufactured artefact {path} is not in {source}; the contract was built "
				"against a different workspace than the one being dispatched into"
			)
		destination = target / path
		destination.parent.mkdir(parents=True, exist_ok=True)
		destination.write_bytes(origin.read_bytes())
		written.append(path)
	return tuple(written)


def slug(name: str) -> str:
	"""A module name as an identifier, for a filename and for a language's own rules.

	Lossy on purpose and recorded rather than hidden: the slug is what the artefact searches
	for, so two modules differing only in punctuation would collide, and the check that found
	two candidates refuses rather than picking one.
	"""
	out = [ch if (ch.isalnum() or ch == "_") else "_" for ch in name.strip().lower()]
	text = "".join(out).strip("_")
	if text and text[0].isdigit():
		text = f"m_{text}"
	assert text, f"module name {name!r} has no identifier in it"
	return text


# --------------------------------------------------------------------------- #
# the seam: the four assertions, and the audit
# --------------------------------------------------------------------------- #


class ConfiguredManufactureAdapter:
	"""One backend, behind the gate that decides whether its artefact may be declared.

	This is the ``ConfiguredHarnessAdapter`` rule applied to manufacturing: one adapter
	parameterised by a spec, never a subclass per language. A per-language adapter would put
	the gate in three places, and the gate is the half that must not vary by language — a
	TypeScript oracle that could be declared without the vacuity audit would be a weaker
	gate for the languages the factory supports least well.
	"""

	def __init__(
		self,
		spec: ManufactureSpec,
		*,
		workspace: Path,
		timeout: float = DEFAULT_MANUFACTURE_TIMEOUT_SECONDS,
		boundary: DeploymentBoundary | None = None,
	) -> None:
		assert timeout > 0, f"timeout must be positive, got {timeout}"
		self.spec = spec
		self.workspace = Path(workspace)
		self.timeout = timeout
		self.backend = backends_for(spec)
		# FR-019: the check the factory runs is a process, so it runs inside the boundary
		# measured for this host like every other process the factory launches. An artefact
		# that read the factory's ledger while judging the producer would be a route to the
		# oracle corpus (FR-059), and a boundary applied to the session but not to the check
		# is a boundary at one of two doors.
		self.boundary = boundary

	@property
	def language(self) -> str:
		return self.spec.language

	def supports(self, oracle_class: OracleClass) -> bool:
		"""Whether this backend builds this rank, with the held-out refusal applied first."""
		if oracle_class is OracleClass.EXAMPLE:
			return False
		return self.backend.supports(oracle_class)

	async def manufacture(self, request: ManufactureRequest) -> ManufactureOutcome:
		"""Build the artefact, or refuse by name. The refusal is a value, not a raise."""
		if request.oracle_class is OracleClass.EXAMPLE:
			# FR-106, and before the backend is consulted: `held_out` is exactly this
			# class, so a backend allowed to return one would manufacture the factory's
			# own scenario and withhold it from the factory's own producer.
			return refusal(
				request,
				ManufactureRefusalReason.HELD_OUT,
				(
					"FR-106 holds an EXAMPLE oracle out from the producer because the example "
					"is the operator's case; a manufactured one would be the factory's own "
					"scenario, withheld for no reason and unreadable by the operator it is "
					"supposed to have come from"
				),
			)
		if not self.backend.supports(request.oracle_class):
			return refusal(
				request,
				ManufactureRefusalReason.UNSUPPORTED_RANK,
				(f"the {self.spec.language} backend builds no {request.oracle_class.value} oracle"),
			)
		built = await self.backend.manufacture(request)
		if isinstance(built, ManufactureRefusal):
			return built
		return await self._earn(built, request)

	# ------------------------------------------------------------------ the gate

	async def _earn(
		self,
		built: ManufacturedOracle,
		request: ManufactureRequest,
	) -> ManufactureOutcome:
		"""Prove the artefact and the command describe each other, then audit the check.

		Four assertions, in the order that fails cheapest first: the path is inside the
		workspace, the argv's artefact element *is* that path, the file exists, and the
		command runs. The fifth step is not an assertion but a measurement — FR-107's
		adversarial audit — and it is the one that decides whether the check means anything.
		"""
		root = self.workspace.resolve()
		target = built.path if built.path.is_absolute() else (self.workspace / built.path)
		target = target.resolve()
		if root != target and root not in target.parents:
			return refusal(
				request,
				ManufactureRefusalReason.ARTEFACT_OUTSIDE_WORKSPACE,
				f"the artefact {target} is outside the workspace {root}, so the producer could "
				"read and rewrite the check that judges it (FR-059)",
			)
		assert 0 <= built.artefact_argument < len(built.argv), "artefact_argument is in range"
		named = Path(built.argv[built.artefact_argument])
		resolved = named if named.is_absolute() else (self.workspace / named)
		if resolved.resolve() != target:
			return refusal(
				request,
				ManufactureRefusalReason.COMMAND_NAMES_ANOTHER_FILE,
				f"the command names {named} but the artefact was written to {target}, so the "
				"check that would run is not the check that was built",
			)
		if not target.is_file():
			return refusal(
				request,
				ManufactureRefusalReason.ARTEFACT_MISSING,
				f"the backend named {target} and did not write it, so the command would fail "
				"for a reason that says nothing about the module (FR-105)",
			)

		code = await self._run(built.argv, cwd=self.workspace)
		if code is None:
			# A killed compiler leaves what it had written, and this branch is reached
			# precisely when one was killed — so the discard happens here as well as after
			# the audit. A refusal that left a half-built binary in the module directory
			# would be a defect the *gate* caused, and the seal would commit it.
			self._discard(built)
			return refusal(
				request,
				ManufactureRefusalReason.COMMAND_DID_NOT_RUN,
				f"`{built.command_hint}` did not terminate within {self.timeout:g}s, so whether "
				"it checks anything is unknown",
			)
		earned = replace(built, path=target, observed_exit_code=code)
		return await self._audit_vacuity(earned, request)

	async def _audit_vacuity(
		self,
		earned: ManufacturedOracle,
		request: ManufactureRequest,
	) -> ManufactureOutcome:
		"""FR-107: run the same command against a tree that holds nothing but the artefact.

		The audit is the *same argv* with the same relative layout, in a directory with
		nothing else in it — not a modified command, and not a tree the factory chose to be
		empty. That distinction is the whole instrument: a check re-written for the audit
		would be audited as a different check, and a tree that happened to be empty would be
		the instrument measuring its own choice.

		A non-zero exit is the pass. Exit zero means the check is satisfied by nothing, which
		is the one outcome that makes a manufactured oracle worse than no oracle.
		"""
		# The mirror's build product is discarded by the TemporaryDirectory; the workspace's
		# is not, and it is removed on both branches below.

		root = self.workspace.resolve()
		with tempfile.TemporaryDirectory(prefix="sofact-vacuity-") as empty:
			scratch = Path(empty)
			# ``earned.path`` is resolved and the workspace may not be — on darwin `/tmp` is
			# a symlink to `/private/tmp`, so the two disagree by exactly that prefix. Both
			# sides go through ``resolve`` for the same reason the boundary profiles do.
			mirrored = scratch / earned.path.relative_to(root)
			mirrored.parent.mkdir(parents=True, exist_ok=True)
			mirrored.write_bytes(earned.path.read_bytes())
			code = await self._run(earned.argv, cwd=scratch)
		# Both branches discard, and it happens before the return rather than after a
		# success: a vacuity refusal still leaves the workspace's build product behind, and
		# a refusal that littered the module directory would be a defect the audit caused.
		self._discard(earned)
		if code == 0:
			return refusal(
				request,
				ManufactureRefusalReason.VACUOUS,
				f"`{earned.command_hint}` exited 0 against a tree holding nothing but itself, "
				"so the check is satisfied without the module existing — a manufactured "
				"oracle that passes on an empty tree establishes nothing (FR-107)",
			)
		return earned

	def _discard(self, earned: ManufacturedOracle) -> None:
		"""Remove a build product the command left, and its compiler sidecars.

		Named rather than searched for: a ``rglob`` over the workspace to find "things that
		look like build output" would eventually delete a producer's file. The sidecars go by
		prefix, which is what ``rustc`` gives them — it writes ``<output><random>`` for the
		metadata it needs mid-compile, and those are not covered by an exact-name unlink.
		"""
		output = earned.output
		if output is None:
			return
		target = output if output.is_absolute() else (self.workspace / output)
		for sibling in target.parent.glob(f"{target.name}*"):
			if sibling.is_file():
				sibling.unlink(missing_ok=True)

	async def _run(self, argv: Sequence[str], *, cwd: Path) -> int | None:
		"""Run one command, returning its exit code or ``None`` if it never terminated.

		Through the measured boundary, like every other process this factory launches: the
		check reads the tree it is given, and a check that could read the factory's ledger
		while doing so would be a producer's route to the oracle corpus (FR-059).

		``None`` covers two failures that are one refusal: the command could not be launched
		(no interpreter, no compiler), and the command did not terminate. Both mean nothing
		about the module was established, which is why neither is an exit code.
		"""
		boundary = self.boundary
		wrapped = wrap_argv(tuple(argv), boundary, cwd)
		env = {**os.environ, **boundary_env(boundary, cwd)}
		try:
			process = await asyncio.create_subprocess_exec(
				*wrapped,
				cwd=cwd,
				stdout=asyncio.subprocess.DEVNULL,
				stderr=asyncio.subprocess.DEVNULL,
				env=env,
			)
		except OSError:
			return None
		try:
			await asyncio.wait_for(process.wait(), timeout=self.timeout)
		except TimeoutError:
			process.kill()
			await process.wait()
			return None
		return process.returncode


async def manufacture_declarations(
	adapter: ConfiguredManufactureAdapter | None,
	requests: Sequence[tuple[ManufactureRequest, OracleDeclaration]],
) -> tuple[dict[str, OracleDeclaration], tuple[ManufactureRefusal, ...]]:
	"""Manufacture what the adapter can, keep the suggestion where it refuses.

	The pairing is (request, suggested declaration), and the suggestion is what survives a
	refusal. That is deliberate: manufacturing *adds* executability to a clause, and a
	refusal must leave the clause exactly as :func:`~sofact.contract.suggest_oracle` left it
	— honest prose with no command — rather than dropping it from the contract. FR-108's
	ground-truth debt is the measure of how much of a contract that is, and a refusal that
	removed a clause would make the debt unmeasurable.
	"""
	oracles: dict[str, OracleDeclaration] = {}
	refusals: list[ManufactureRefusal] = []
	for request, suggested in requests:
		if adapter is None:
			oracles[request.clause_id] = suggested
			continue
		outcome = await adapter.manufacture(request)
		if isinstance(outcome, ManufactureRefusal):
			refusals.append(outcome)
			oracles[request.clause_id] = suggested
			continue
		oracles[request.clause_id] = OracleDeclaration(
			oracle_class=request.oracle_class,
			description=request.statement,
			command_hint=outcome.command_hint,
		)
	return oracles, tuple(refusals)
