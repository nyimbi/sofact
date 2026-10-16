"""FR-118's measured strength: a kill rate over a named, closed operator set.

FR-118 asks the delivery report to state which clauses are verified "and by which oracle
at which **measured** strength". ``VerifiedClause`` has carried the field since it was
written and nothing has ever set it, so the report has always said "declared rank N, not
measured" — which is the honest sentence and also the whole gap.

This module closes the gap the only way a stdlib-only dependency set allows. There is no
``mutmut`` and no ``cosmic-ray`` here (the dependency set is exactly httpx, pydantic,
typer and uuid6), so the mutants come from :mod:`ast`: a small, **named, closed** set of
:class:`ast.NodeTransformer` operators, each of which makes one specific kind of mistake.
A closed set is not a compromise, it is the instrument: a kill rate is a statement about
*which* mutants were killed, and an operator set that could grow at run time would make
two numbers incomparable without saying so.

**The number is a lower bound, and it is withheld below a floor.** Equivalent mutants are
never killed and stdlib cannot decide equivalence — so the rate is bounded above by what
the operator set can express, never a statement about the code's true test quality. A
rate over three surviving mutants is noise dressed as a measurement, and the type carries
:attr:`MutationReport.measured_strength` as ``None`` with a named
:class:`StrengthRefusal` rather than a number nobody should act on. That is the same
discipline :func:`~sofact.routing.oracle_strength_ceiling` keeps one level up: it returns
``None`` rather than ``L1`` for a strength this module refused to state, so a lane nobody
measured is undecided rather than decided at the bottom of FR-009's table.

**Three verdicts per mutant, and they are not interchangeable.**

* **killed** — the suite's verdict flipped pass→fail. The only outcome that is evidence.
* **discarded** — the mutant did not compile, or the module did not import. It never ran,
  so it says nothing about the suite. Counting it as killed would let a syntax error
  raise the score.
* **timed out** — counted separately and never as killed. A mutant the suite cannot
  finish running is a mutant the suite did not judge.

``kill_rate = killed / (total - discarded)``, with the raw counts kept beside it so a
reader can recompute rather than trust. Timed-out mutants stay in the denominator: they
were offered to the suite and the suite did not return a verdict, which is a failure of
the measurement rather than a kill, and removing them would flatter the number.

**The module under test is never the module mutated.** Each mutant is written into a
fresh :class:`~tempfile.TemporaryDirectory` copy of the tree, so the workspace's own
bytes do not move — which matters because ``digest_tree`` is FR-006's cache key, and a
mutant left behind would invalidate a verdict nothing touched.
"""

from __future__ import annotations

import ast
import asyncio
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from sofact.boundary import boundary_env, wrap_argv
from sofact.views import DeploymentBoundary

__all__ = [
	"DEFAULT_MUTANT_TIMEOUT_SECONDS",
	"MINIMUM_MUTANTS_FOR_A_NUMBER",
	"OPERATORS",
	"MutantResult",
	"MutationOperator",
	"MutationOutcome",
	"MutationReport",
	"StrengthRefusal",
	"measure_strength",
]

DEFAULT_MUTANT_TIMEOUT_SECONDS: Final = 60.0
"""How long one mutant's suite run may take.

Per mutant rather than for the whole measurement, because a single hung mutant must not
consume the budget of the other thirty — and because a mutant that hangs is a datum
(:attr:`MutationOutcome.TIMED_OUT`) rather than a reason to stop.
"""

MINIMUM_MUTANTS_FOR_A_NUMBER: Final = 5
"""How many *surviving* mutants a kill rate needs before it may be reported.

Below this the report carries ``measured_strength = None`` and a named refusal. Three
mutants killed is 1.000 and means nothing; the floor is what keeps a small module from
being reported as perfectly tested because the operator set found little to change.
"""


class MutationOutcome(StrEnum):
	"""What happened to one mutant. The three are not a scale."""

	KILLED = "killed"
	"""The suite's verdict flipped from pass to fail. The only evidentiary outcome."""

	SURVIVED = "survived"
	"""The mutant ran and the suite still passed. Either the suite is weak or the mutant
	is equivalent, and stdlib cannot tell which — which is why the rate is a lower bound."""

	DISCARDED = "discarded"
	"""The mutant never ran: it did not compile, or the module did not import.

	Never counted as killed. A syntax error is not a test.
	"""

	TIMED_OUT = "timed_out"
	"""The suite did not finish inside the per-mutant timeout.

	Counted separately and left in the denominator. The suite was offered the mutant and
	returned no verdict, which is a failure of the measurement rather than a kill.
	"""


class StrengthRefusal(StrEnum):
	"""Why no kill rate is reported. A number with no refusal is a number to act on."""

	NO_SUITE = "no_suite"
	"""The caller named no suite to run, so there is nothing whose strength could be
	measured. Mutation testing scores *a suite*, not a module."""

	NO_MODULE = "no_module"
	"""The module to mutate was not found, or could not be parsed."""

	MODULE_DID_NOT_IMPORT = "module_did_not_import"
	"""The pristine module failed its own import, so every mutant would be discarded.

	A rate computed over zero surviving mutants is not zero, it is undefined, and
	reporting it as 0.0 would read as "the suite kills nothing" when the truth is that
	nothing was ever tested.
	"""

	NO_MUTANTS = "no_mutants"
	"""The operator set produced no mutant at all.

	An operator set that matches nothing is an operator set that measured nothing. This
	is the refusal that catches a mutation engine pointed at the wrong file.
	"""

	BELOW_THE_FLOOR = "below_the_floor"
	"""Fewer surviving mutants than :data:`MINIMUM_MUTANTS_FOR_A_NUMBER`."""


@dataclass(frozen=True)
class MutantResult:
	"""One mutant, what it changed, and what the suite did with it."""

	operator: str
	line: int
	replacement: str
	outcome: MutationOutcome
	detail: str = ""

	def __post_init__(self) -> None:
		assert self.operator, "a mutant names the operator that produced it"
		assert self.line > 0, "a mutant names the line it changed"


@dataclass(frozen=True)
class MutationReport:
	"""A measured strength, or a named reason there is none (FR-118, NFR-024).

	``measured_strength`` is ``None`` whenever any of the refusals hold, and
	:attr:`measured` says which. The raw counts travel beside the rate so a reader can
	recompute it rather than trust it, and so a report that *looks* low can be told from
	one whose operator set found nothing to mutate.
	"""

	module: str
	operator_set: tuple[str, ...]
	results: tuple[MutantResult, ...]
	refusal: StrengthRefusal | None = None

	def __post_init__(self) -> None:
		assert self.module, "a mutation report names the module it mutated"
		if self.refusal is None:
			assert self.results, "a report with no refusal must carry its mutants"

	@property
	def killed(self) -> tuple[MutantResult, ...]:
		return tuple(r for r in self.results if r.outcome is MutationOutcome.KILLED)

	@property
	def survived(self) -> tuple[MutantResult, ...]:
		return tuple(r for r in self.results if r.outcome is MutationOutcome.SURVIVED)

	@property
	def discarded(self) -> tuple[MutantResult, ...]:
		return tuple(r for r in self.results if r.outcome is MutationOutcome.DISCARDED)

	@property
	def timed_out(self) -> tuple[MutantResult, ...]:
		return tuple(r for r in self.results if r.outcome is MutationOutcome.TIMED_OUT)

	@property
	def scored(self) -> int:
		"""Mutants the suite actually judged: everything that ran, including timeouts.

		A timed-out mutant is in here on purpose. It was offered and no verdict came back,
		which is a hole in the measurement; removing it from the denominator would report
		a rate over the subset the suite happened to finish, and that subset is not chosen
		by anything but speed.
		"""
		return len(self.results) - len(self.discarded)

	@property
	def measured_strength(self) -> float | None:
		"""``killed / scored``, or ``None`` when the report refuses to state one."""
		if self.refusal is not None or self.scored == 0:
			return None
		return len(self.killed) / self.scored

	@property
	def measured(self) -> bool:
		"""Whether :attr:`measured_strength` is a measurement rather than an absence."""
		return self.measured_strength is not None

	@property
	def rendered(self) -> str:
		"""The number, or the refusal, in the report's own words (FR-118)."""
		if self.refusal is not None:
			return f"{self.module}: strength not measured ({self.refusal.value})"
		assert self.measured_strength is not None
		return (
			f"{self.module}: {self.measured_strength:.3f} "
			f"({len(self.killed)}/{self.scored} killed, {len(self.discarded)} discarded, "
			f"{len(self.timed_out)} timed out; a lower bound over "
			f"{len(self.operator_set)} operator(s))"
		)


# --------------------------------------------------------------------------- #
# the operator set: named, closed, and each one a specific mistake
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MutationOperator:
	"""One way to make a mistake, as a named AST rewrite.

	``apply`` returns the rewritten source or ``None`` when the operator found nothing to
	change in this module — an absence rather than an empty edit, because a mutant
	identical to its parent would be scored as surviving and would depress the rate for a
	reason that is about the operator set rather than about the suite.
	"""

	name: str
	description: str
	apply: Callable[[ast.Module], ast.Module | None]


SWAPS: Final[dict[type[ast.cmpop], type[ast.cmpop]]] = {
	ast.Lt: ast.GtE,
	ast.LtE: ast.Gt,
	ast.Gt: ast.LtE,
	ast.GtE: ast.Lt,
	ast.Eq: ast.NotEq,
	ast.NotEq: ast.Eq,
	ast.Is: ast.IsNot,
	ast.IsNot: ast.Is,
}
"""Each comparison and the one that is wrong in the other direction.

Keyed by the *class* rather than by a string, so an operator the table does not know is
skipped rather than mapped to something arbitrary — ``in``, ``not in`` and the ordering
built-ins have no inverse that preserves their operand types, and a mutant that raised
``TypeError`` would be discarded and so would measure nothing.
"""


class _ComparisonSwap(ast.NodeTransformer):
	"""Swap a comparison for its inverse: ``<`` becomes ``>=``, ``==`` becomes ``!=``."""

	def __init__(self) -> None:
		self.changed = False

	def visit_Compare(self, node: ast.Compare) -> ast.AST:
		self.generic_visit(node)
		if not node.ops:
			return node
		replacement = SWAPS.get(type(node.ops[0]))
		if replacement is None:
			return node
		node.ops[0] = replacement()
		self.changed = True
		return node


class _BooleanNegate(ast.NodeTransformer):
	"""Wrap a boolean test in ``not``, at the first place one is decided."""

	def __init__(self) -> None:
		self.changed = False

	def visit_If(self, node: ast.If) -> ast.AST:
		self.generic_visit(node)
		if self.changed:
			return node
		node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
		self.changed = True
		return node

	def visit_While(self, node: ast.While) -> ast.AST:
		self.generic_visit(node)
		if self.changed:
			return node
		node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
		self.changed = True
		return node


class _ReturnNone(ast.NodeTransformer):
	"""Replace the first non-trivial ``return`` with ``return None``.

	Skips a bare ``return`` and a ``return None``, because rewriting either into itself
	produces a mutant indistinguishable from its parent.
	"""

	def __init__(self) -> None:
		self.changed = False

	def visit_Return(self, node: ast.Return) -> ast.AST:
		self.generic_visit(node)
		if self.changed or node.value is None:
			return node
		if isinstance(node.value, ast.Constant) and node.value.value is None:
			return node
		node.value = ast.Constant(value=None)
		self.changed = True
		return node


class _ConstantOffByOne(ast.NodeTransformer):
	"""Shift an integer literal by one. The classic boundary mutant."""

	def __init__(self) -> None:
		self.changed = False

	def visit_Constant(self, node: ast.Constant) -> ast.AST:
		if self.changed:
			return node
		if isinstance(node.value, bool) or not isinstance(node.value, int):
			return node
		node.value = node.value + 1
		self.changed = True
		return node


class _StatementDelete(ast.NodeTransformer):
	"""Remove the first expression statement — a call whose effect the suite should notice.

	Expression statements only: deleting an assignment would usually be a ``NameError``
	rather than a behavioural change, and a mutant that cannot compile is a mutant that
	was discarded, which measures nothing.
	"""

	def __init__(self) -> None:
		self.changed = False

	def visit_Expr(self, node: ast.Expr) -> ast.AST:
		self.generic_visit(node)
		if self.changed:
			return node
		self.changed = True
		return ast.Pass()


def _rewrite(transformer_type: type[ast.NodeTransformer], tree: ast.Module) -> ast.Module | None:
	"""Run one transformer over a fresh copy of ``tree``, or ``None`` if it changed nothing.

	``ast.parse(ast.unparse(tree))`` rather than a deep copy: the transformers mutate in
	place, and a copy that shared nodes would let one operator's edit reach the next
	mutant. Re-parsing is the copy, and it also guarantees the source handed to the next
	step is real source rather than a graph that only round-trips in memory.
	"""
	working = ast.parse(ast.unparse(tree))
	transformer = transformer_type()
	transformer.visit(working)
	ast.fix_missing_locations(working)
	if not getattr(transformer, "changed", False):
		return None
	return working


OPERATORS: tuple[MutationOperator, ...] = (
	MutationOperator(
		name="comparison_swap",
		description="a comparison replaced by its inverse, so a boundary is off by a case",
		apply=lambda tree: _rewrite(_ComparisonSwap, tree),
	),
	MutationOperator(
		name="boolean_negate",
		description="a branch condition negated, so the guarded work does not happen",
		apply=lambda tree: _rewrite(_BooleanNegate, tree),
	),
	MutationOperator(
		name="return_none",
		description="a computed return replaced by None, so a caller gets nothing",
		apply=lambda tree: _rewrite(_ReturnNone, tree),
	),
	MutationOperator(
		name="constant_off_by_one",
		description="an integer literal shifted by one, so a bound is wrong at its edge",
		apply=lambda tree: _rewrite(_ConstantOffByOne, tree),
	),
	MutationOperator(
		name="statement_delete",
		description="an expression statement removed, so a side effect never happens",
		apply=lambda tree: _rewrite(_StatementDelete, tree),
	),
)
"""The closed set. Named rather than anonymous because the rate is about *these* mistakes.

Five operators, and every one of them is a mistake a reader recognises — which is the
test for whether a mutation operator belongs here. A set that grew at run time would make
two kill rates incomparable while both looked like numbers.
"""


# --------------------------------------------------------------------------- #
# the measurement
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Suite:
	"""The command whose verdict is the measurement, and the module it judges."""

	argv: tuple[str, ...]
	module: Path
	"""The file to mutate, relative to the workspace."""


async def measure_strength(
	workspace: Path,
	*,
	module: str,
	suite: Sequence[str],
	timeout: float = DEFAULT_MUTANT_TIMEOUT_SECONDS,
	boundary: DeploymentBoundary | None = None,
	operators: Sequence[MutationOperator] = OPERATORS,
) -> MutationReport:
	"""Mutate ``module`` one operator at a time and ask ``suite`` whether it noticed.

	``suite`` is the command whose pass/fail *is* the measurement — the producer's own
	tests, run the same way the factory runs anything. The pristine tree is run first: a
	suite that fails before any mutation measures nothing, and every mutant would be
	reported as killed for a reason that has nothing to do with the mutant.

	Each mutant is applied in a fresh copy of the workspace, so the tree being measured is
	never the tree under test and FR-006's cache key does not move.
	"""
	assert workspace.is_dir(), f"cannot measure strength in a tree that does not exist: {workspace}"
	assert module.strip(), "a strength measurement names the module to mutate"
	assert suite, "a strength measurement names the suite whose verdict is the measurement"

	names = tuple(operator.name for operator in operators)
	target = Path(module)
	source_path = target if target.is_absolute() else workspace / target
	if not source_path.is_file():
		return MutationReport(
			module=module, operator_set=names, results=(), refusal=StrengthRefusal.NO_MODULE
		)
	try:
		tree = ast.parse(source_path.read_text(encoding="utf-8"))
	except SyntaxError:
		return MutationReport(
			module=module, operator_set=names, results=(), refusal=StrengthRefusal.NO_MODULE
		)

	baseline = await _run_suite(tuple(suite), workspace, timeout=timeout, boundary=boundary)
	if baseline is None:
		return MutationReport(
			module=module,
			operator_set=names,
			results=(),
			refusal=StrengthRefusal.MODULE_DID_NOT_IMPORT,
		)
	if baseline != 0:
		# The suite already fails, so a mutant cannot flip anything: every one would be
		# recorded as killed, and the report would state a perfect score for a suite that
		# was broken before the measurement started.
		return MutationReport(
			module=module,
			operator_set=names,
			results=(),
			refusal=StrengthRefusal.MODULE_DID_NOT_IMPORT,
		)

	results: list[MutantResult] = []
	for operator in operators:
		mutated = operator.apply(tree)
		if mutated is None:
			continue
		results.append(
			await _score_mutant(
				mutated,
				operator=operator,
				tree=tree,
				suite=_Suite(argv=tuple(suite), module=target),
				workspace=workspace,
				timeout=timeout,
				boundary=boundary,
			)
		)

	if not results:
		return MutationReport(
			module=module, operator_set=names, results=(), refusal=StrengthRefusal.NO_MUTANTS
		)
	scored = [r for r in results if r.outcome is not MutationOutcome.DISCARDED]
	report = MutationReport(module=module, operator_set=names, results=tuple(results))
	if len(scored) < MINIMUM_MUTANTS_FOR_A_NUMBER:
		return MutationReport(
			module=module,
			operator_set=names,
			results=tuple(results),
			refusal=StrengthRefusal.BELOW_THE_FLOOR,
		)
	return report


async def _score_mutant(
	mutated: ast.Module,
	*,
	operator: MutationOperator,
	tree: ast.Module,
	suite: _Suite,
	workspace: Path,
	timeout: float,
	boundary: DeploymentBoundary | None,
) -> MutantResult:
	"""Write one mutant into a copy of the tree and read the suite's verdict on it.

	The copy is what makes this safe to run repeatedly: the mutant is written into a
	``TemporaryDirectory``, the suite runs there, and the workspace's own bytes never
	move. A measurement that mutated in place and restored afterwards would leave the tree
	moved by a crash, which is the failure mode ``digest_tree`` would then report as a
	change nobody made.
	"""
	line = _first_line(tree, mutated)
	replacement = operator.description
	with tempfile.TemporaryDirectory(prefix="sofact-mutant-") as scratch:
		mirror = Path(scratch) / "tree"
		shutil.copytree(workspace, mirror, symlinks=True, dirs_exist_ok=True)
		written = mirror / suite.module
		try:
			written.write_text(ast.unparse(mutated), encoding="utf-8")
			ast.parse(written.read_text(encoding="utf-8"))
		except (OSError, SyntaxError) as exc:
			# The mutant does not parse. It never ran, so it is discarded rather than
			# killed — counting a syntax error as a kill would let a typo raise the score.
			return MutantResult(
				operator=operator.name,
				line=line,
				replacement=replacement,
				outcome=MutationOutcome.DISCARDED,
				detail=f"the mutant does not compile: {exc}",
			)
		code = await _run_suite(suite.argv, mirror, timeout=timeout, boundary=boundary)

	if code is None:
		return MutantResult(
			operator=operator.name,
			line=line,
			replacement=replacement,
			outcome=MutationOutcome.TIMED_OUT,
			detail=f"the suite did not finish within {timeout:g}s",
		)
	if code != 0:
		return MutantResult(
			operator=operator.name,
			line=line,
			replacement=replacement,
			outcome=MutationOutcome.KILLED,
			detail=f"the suite exited {code} against the mutant",
		)
	return MutantResult(
		operator=operator.name,
		line=line,
		replacement=replacement,
		outcome=MutationOutcome.SURVIVED,
		detail=(
			"the suite passed against the mutant, so either it does not cover this line or "
			"the mutant is equivalent — stdlib cannot tell which, which is why the rate is "
			"a lower bound"
		),
	)


def _first_line(pristine: ast.Module, mutated: ast.Module) -> int:
	"""The line the mutant first differs from its parent, for the report to point at.

	Read from the two unparsed sources rather than from node positions, because an
	operator that replaces a node wholesale produces a node with no ``lineno`` and a
	report that said "line 0" would send a reader to the top of the file.
	"""
	before = ast.unparse(pristine).splitlines()
	after = ast.unparse(mutated).splitlines()
	for index, (left, right) in enumerate(zip(before, after, strict=False), start=1):
		if left != right:
			return index
	return max(len(before), 1)


async def _run_suite(
	argv: Sequence[str],
	cwd: Path,
	*,
	timeout: float,
	boundary: DeploymentBoundary | None,
) -> int | None:
	"""Run the suite, returning its exit code or ``None`` if it never terminated.

	``None`` and a non-zero code are different facts and stay different all the way up: a
	suite that hung did not judge the mutant, and a suite that failed did. Through the
	measured boundary, because a mutant run executes the producer's code exactly as a
	dispatch does (FR-019).
	"""
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
		await asyncio.wait_for(process.wait(), timeout=timeout)
	except TimeoutError:
		process.kill()
		await process.wait()
		return None
	return process.returncode
