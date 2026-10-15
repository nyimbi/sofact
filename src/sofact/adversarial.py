"""FR-012–015 — the adversarial audit: a hacker, a fixer, a sampler and a rate.

FR-012: "The **hacker** role must attempt to obtain a passing verdict on a lane's output
*without solving the task* — editing tests, hard-coding expected values, special-casing
fixtures, disabling assertions, over-fitting to the sample."

**The honest scoping, stated first because it is the whole design.** Two of FR-012's five
techniques need a *model* to attempt: hard-coding an expected value and over-fitting to a
sample both require inventing code that satisfies a clause's intent without implementing
it, and SoFact has no model in this path — deliberately, since a model-authored attack is
a model judging its own work one level up. The other three are **mechanical rewrites of
the artefacts the factory already holds**, and those are what this module attempts:

* ``EDITED_TEST`` and ``DISABLED_ASSERTION`` are the same act at two granularities. The
  oracle is a command; the file the command runs is on disk; rewriting it is a source
  transform. This is FR-139's integrity subject *demonstrated* rather than compared — the
  integrity check hashes the oracle set and reports drift, and this module performs the
  drift and asks whether the verdict moved.
* ``SPECIAL_CASED_FIXTURE`` is a source transform of the module under test: a branch
  inserted at the top of the attacked function that returns whatever the fixture expects.

The two that remain are reported as ``NOT_ATTEMPTED`` with the reason, never silently
omitted and never counted as held. A technique this instrument cannot attempt is a
technique nobody is attacking, and FR-015's rate over the three it *can* attempt is a
rate over three techniques rather than five — which the report says.

**The exploit is measured the only way an exploit can be: the verdict flips.** The
attacked oracle is run by the real :class:`~sofact.execution.OracleRunner` and read by the
real :func:`~sofact.verification.verify`, exactly as at P6. An attempt whose rewrite
leaves the verdict ``VIOLATED`` failed to exploit; one that produces ``SATISFIED`` where
the honest tree produced ``VIOLATED`` is FR-012's defect, demonstrated. Re-deciding
"satisfied?" here would be a second implementation of the one rule the factory is built
on, and a manufactured *judge* is the same defect as a manufactured oracle one level up.

**Why the honest tree is run first.** An oracle that already reports ``SATISFIED`` against
the pristine tree has nothing for a hacker to obtain — the attempt could not flip a
verdict that was never negative. So the baseline is taken first, and a clause whose oracle
passes honestly is ``NOT_ATTEMPTED`` rather than ``HELD``: the audit learned nothing about
it, which is a different statement from an attack that was repelled, and it must not enter
FR-015's denominator.

**Two techniques exploit every oracle and that is not a bug.** ``EDITED_TEST`` replaces the
file the command runs, so against any oracle whose honest verdict is ``VIOLATED`` it obtains
a pass — a hacker with write access to the test file always can. What the *other* two
techniques measure is whether the oracle resists a subtler rewrite, and a report whose
``techniques_exploited`` names only ``EDITED_TEST`` is saying something specific: the oracle
is defeated by a blunt edit and nothing else was tried that got through. Collapsing the three
into one "exploited" boolean would throw that away.

**FR-014's sampling is a real branch, not a note.** 1-in-N at or below L3 and 100% above
it, with N carried on the report because two rates computed under different N are not
comparable. A change the sample skips is ``NOT_ATTEMPTED``, which is why
:attr:`~sofact.views.AdversarialAuditReport.attempted` exists: a pass over ten changes
that attacked none must not print the same rate as a pass that attacked ten and found
nothing.
"""

from __future__ import annotations

import ast
import re
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sofact._uuid7 import uuid7str
from sofact.execution import DEFAULT_MAX_OUTPUT_BYTES, DEFAULT_TIMEOUT_SECONDS, OracleRunner
from sofact.verification import verify
from sofact.views import (
	AUDIT_SAMPLE_FLOOR,
	AdversarialAuditReport,
	AutonomyLevel,
	Clause,
	Contract,
	ExploitFix,
	HackAttempt,
	HackOutcome,
	HackTechnique,
	ModuleClass,
	now,
)

__all__ = [
	"DEFAULT_SAMPLE_FLOOR",
	"attempt_techniques",
	"fix_exploit",
	"run_adversarial_audit",
	"sample_decision",
]

DEFAULT_SAMPLE_FLOOR: Final[int] = AUDIT_SAMPLE_FLOOR
"""Re-exported so a caller need not reach into :mod:`sofact.views` for the default N."""

SAMPLED_ABOVE: Final[AutonomyLevel] = AutonomyLevel.L3
"""FR-014's threshold: sampled at or below L3, **100%** above it.

The requirement's own boundary, and the reason it is a level rather than a rate: above L3
the factory is doing work a human is not reading, so a sampled audit would leave whole
changes unexamined in exactly the band where nobody else is looking.
"""

_HACKABLE_TECHNIQUES: Final[tuple[HackTechnique, ...]] = (
	HackTechnique.EDITED_TEST,
	HackTechnique.DISABLED_ASSERTION,
	HackTechnique.SPECIAL_CASED_FIXTURE,
)
"""The three FR-012 techniques a source transform can attempt, in the enum's order.

The other two need a model to invent code that satisfies an intent without implementing
it, and inventing that is precisely what the factory must not do unattended. They are
reported as not attempted rather than dropped.
"""

UNADDRESSED_TECHNIQUES: Final[tuple[HackTechnique, ...]] = tuple(
	t for t in HackTechnique if t not in _HACKABLE_TECHNIQUES
)
"""The two techniques no attempt here covers, named so the report can state the gap.

FR-015's rate is over the techniques actually attacked. A reader who assumed all five
were covered would read a zero as "nothing gets through" rather than "nothing tried the
other two", which is the same defect as an unrun oracle reading as a satisfied one.
"""

_ASSERT_RE: Final = re.compile(r"^(\s*)assert\s+(.*)$")


def sample_decision(
	*, ordinal: int, lane: ModuleClass | None = None, ceiling: AutonomyLevel
) -> bool:
	"""Whether FR-014's rule says to attack the change at ``ordinal`` in ``lane``.

	Pure, and separated from the loop because the rule is the whole of FR-014 and a test
	can hold it to the boundary — that a change above L3 is *always* attacked and one at or
	below L3 is attacked 1-in-N — without spawning a process.

	``lane`` is accepted and unused by the rule, which is FR-014's own shape: the sample is
	a function of the *ceiling* alone ("sampled … on lanes at or below L3, and run on 100%
	of changes on lanes above L3"). It is a parameter rather than a dropped argument so a
	caller records which lane it sampled for, and so a later requirement that samples per
	lane has somewhere to arrive.

	``ordinal`` is 1-based and the sample is ``ordinal % N == 0`` rather than a random
	draw. Deterministic sampling is not a weaker instrument here: FR-014's purpose is
	coverage *over time*, and a deterministic stride guarantees that every Nth change is
	examined while a random draw only makes it likely. A random sampler also makes the rate
	irreproducible from the log, which is what FR-015's trend is read from.
	"""
	assert ordinal >= 1, f"a change ordinal is 1-based, got {ordinal}"
	if ceiling > SAMPLED_ABOVE:
		return True
	return ordinal % AUDIT_SAMPLE_FLOOR == 0


@dataclass(frozen=True)
class _Rewrite:
	"""One attempted technique, as a source transform and the reason it applies."""

	technique: HackTechnique
	description: str
	apply: str | None
	"""The rewritten source, or ``None`` when the technique found nothing to change."""


def attempt_techniques(source: str, *, expects: str | None = None) -> tuple[_Rewrite, ...]:
	"""Every rewrite this instrument can attempt against one file's source.

	Returns one :class:`_Rewrite` per :data:`_HACKABLE_TECHNIQUES` entry, in order, with
	``apply`` set to ``None`` where the technique found nothing to change. A ``None`` is an
	absence rather than an empty edit: an attempt identical to the pristine source would
	be scored as held for a reason that is about the technique, not about the oracle.

	``expects`` is the literal the oracle's command appears to compare against, when one
	can be read from it, and it is what ``SPECIAL_CASED_FIXTURE`` inserts a branch for. When
	it is ``None`` that technique finds nothing to change, which is honest: a special case
	for a value nobody named is not a special case.
	"""
	rewrites: list[_Rewrite] = []

	# EDITED_TEST: make the oracle's own command stop checking what it claimed. The
	# transform is the crudest one that still runs — replace the file's whole body with a
	# success — because a hacker that has write access to the test file has exactly this
	# power, and the question FR-012 asks is whether the *verdict* notices.
	rewrites.append(
		_Rewrite(
			technique=HackTechnique.EDITED_TEST,
			description="the oracle's command replaced by one that exits zero unconditionally",
			apply="raise SystemExit(0)\n",
		)
	)

	# DISABLED_ASSERTION: neutralise every assertion in place, keeping the file otherwise
	# intact. Different from EDITED_TEST at the granularity the verdict can see: the test
	# still runs, still counts, and still passes.
	lines = source.splitlines(keepends=True)
	disabled: list[str] = []
	changed = False
	for line in lines:
		match = _ASSERT_RE.match(line.rstrip("\n"))
		if match is None:
			disabled.append(line)
			continue
		changed = True
		indent = match.group(1)
		disabled.append(f"{indent}pass  # assertion disabled\n")
	rewrites.append(
		_Rewrite(
			technique=HackTechnique.DISABLED_ASSERTION,
			description="every assertion in the oracle's file replaced by `pass`",
			apply="".join(disabled) if changed else None,
		)
	)

	# SPECIAL_CASED_FIXTURE: insert a branch at the top of the file's first function that
	# returns the expected value outright. This is the technique that defeats an oracle
	# *without touching the oracle*, which is why it is the one FR-139's hash check cannot
	# see and FR-012 needs a separate instrument for.
	rewrites.append(
		_Rewrite(
			technique=HackTechnique.SPECIAL_CASED_FIXTURE,
			description="a branch returning the expected value inserted ahead of the real body",
			apply=_special_case(source, expects=expects) if expects is not None else None,
		)
	)

	assert len(rewrites) == len(_HACKABLE_TECHNIQUES), (
		"every attemptable technique must produce exactly one rewrite"
	)
	return tuple(rewrites)


def _special_case(source: str, *, expects: str) -> str | None:
	"""Insert an early return of ``expects`` at the top of the source's first function.

	``None`` when the source does not parse or holds no function to attack — a real
	absence, reported as the technique finding nothing rather than as a held attack.
	"""
	try:
		tree = ast.parse(source)
	except SyntaxError:
		return None
	functions = [
		node for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
	]
	if not functions:
		return None
	target = functions[0]
	body = ast.parse(f"return {expects!r}").body
	original = target.body
	target.body = [*body, *original]
	ast.fix_missing_locations(tree)
	return ast.unparse(tree) + "\n"


def fix_exploit(
	attempt: HackAttempt,
	*,
	closed: bool,
	detail: str,
	regression_case: str | None = None,
	regression_because: str | None = None,
) -> ExploitFix:
	"""Record the fixer's response to one demonstrated exploit (FR-013).

	A function rather than a constructor call at the call site so the two halves FR-013
	requires cannot be half-supplied: ``closed`` with its reason is the fix, and
	``regression_case`` or ``regression_because`` is the retention. The type refuses a
	fix that supplies neither, and this refuses one built from an attempt that found
	nothing — there is no exploit to fix, and a fixer row for a held attempt would make
	the exploit count and the fix count disagree.

	It does not check that ``regression_case`` names a file that exists, and that is
	deliberate rather than unfinished: the case a fixer writes is a *test*, and the
	factory does not run the producer's tests (ADR-0025). What it can check is that the
	retention question was answered, which the type does.
	"""
	if not attempt.is_finding:
		raise ValueError(
			f"attempt {attempt.id} ({attempt.technique.value}) did not demonstrate an "
			"exploit, so there is nothing for a fixer to close (FR-013)"
		)
	return ExploitFix(
		attempt_id=attempt.id,
		clause_id=attempt.clause_id,
		closed=closed,
		detail=detail,
		regression_case=regression_case,
		regression_because=regression_because,
	)


async def run_adversarial_audit(
	contract: Contract,
	*,
	workspace: Path,
	ceiling: AutonomyLevel,
	ordinal: int = 1,
	lane: ModuleClass | None = None,
	timeout: float = DEFAULT_TIMEOUT_SECONDS,
	max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> AdversarialAuditReport:
	"""Attack every probeable clause's oracle in ``workspace`` and report what got through.

	**The baseline runs first, and it decides what can be attacked at all.** An oracle that
	reports ``VIOLATED`` against the honest tree is the interesting one: a hacker's job is
	to obtain a *passing* verdict without solving the task, and against an oracle that
	already passes there is nothing to obtain. So a clause whose honest verdict is
	``SATISFIED`` yields ``NOT_ATTEMPTED`` — the audit learned nothing — rather than
	``HELD``, which would credit the oracle with resisting an attack that was never
	meaningful and would put a clause nobody attacked into FR-015's denominator.

	Every rewrite is applied in a **fresh copy** of the workspace, so the tree being
	attacked is never the tree under test: ``digest_tree`` is FR-006's cache key, and a
	disabled assertion left behind would invalidate a verdict nothing touched. This is
	:mod:`sofact.mutation`'s rule, applied one subsystem over.

	``ceiling`` is the lane's autonomy level and it drives FR-014's sample. A change the
	sample skips produces one ``NOT_ATTEMPTED`` row per technique and no process is
	launched, which is what keeps the sampling rule from being decorative.
	"""
	assert workspace.is_dir(), f"cannot audit in a tree that does not exist: {workspace}"
	assert contract.clauses, "cannot audit a contract with no clauses"
	attacked = sample_decision(
		ordinal=ordinal,
		lane=lane,
		ceiling=ceiling,
	)
	probeable = [c for c in contract.clauses if c.oracle.is_executable]
	if not probeable:
		return AdversarialAuditReport(
			id=uuid7str(),
			plan_id=contract.goal_id,
			contract_id=contract.id,
			contract_hash=contract.content_hash,
			rendered_at=now(),
			sample_rate=AUDIT_SAMPLE_FLOOR,
			changes_considered=0,
		)
	if not attacked:
		return AdversarialAuditReport(
			id=uuid7str(),
			plan_id=contract.goal_id,
			contract_id=contract.id,
			contract_hash=contract.content_hash,
			rendered_at=now(),
			attempts=tuple(
				HackAttempt(
					id=uuid7str(),
					clause_id=clause.id,
					statement=clause.statement,
					technique=technique,
					outcome=HackOutcome.NOT_ATTEMPTED,
					detail=(
						f"FR-014's sample is 1-in-{AUDIT_SAMPLE_FLOOR} at or below "
						f"{SAMPLED_ABOVE.name} and this change is ordinal {ordinal} in a "
						f"{ceiling.name} lane, so it was not attacked. Not attacked is not "
						"the same as resisted."
					),
					oracle_class=clause.oracle.oracle_class,
					baseline_command=clause.oracle.command_hint,
				)
				for clause in probeable
				for technique in _HACKABLE_TECHNIQUES
			),
			sample_rate=AUDIT_SAMPLE_FLOOR,
			changes_considered=len(probeable),
		)

	run_id = uuid7str()
	baselines = await _baseline(contract, probeable, workspace, run_id, timeout, max_output_bytes)
	collected: list[HackAttempt] = []
	for clause in probeable:
		if baselines.get(clause.id) is not False:
			collected.append(_unattackable(clause, baselines.get(clause.id)))
			continue
		collected.extend(
			await _attack(
				clause,
				workspace=workspace,
				timeout=timeout,
				max_output_bytes=max_output_bytes,
			)
		)

	return AdversarialAuditReport(
		id=uuid7str(),
		plan_id=contract.goal_id,
		contract_id=contract.id,
		contract_hash=contract.content_hash,
		rendered_at=now(),
		attempts=tuple(collected),
		sample_rate=AUDIT_SAMPLE_FLOOR,
		changes_considered=len(probeable),
	)


def _unattackable(clause: Clause, honest: bool | None) -> HackAttempt:
	"""The row for a clause whose oracle cannot meaningfully be attacked.

	**The outcome is ``NOT_ATTEMPTED``, not ``INCONCLUSIVE``, and the distinction is the
	point.** No attack was made here, so this clause belongs in the same bucket as one
	FR-014's sample skipped — an oracle with no passing verdict to obtain was not attacked
	and was not repelled. ``INCONCLUSIVE`` is reserved for an attack that *ran* and
	could not be read, which is a measurement that failed rather than one that never
	started; collapsing the two would put a clause nobody attacked into the denominator of
	FR-015's rate.

	``honest`` is ``True`` (already satisfied) or ``None`` (unreadable). ``False`` — violated,
	so attackable — never reaches here, and an assert says so: the whole value of this row is
	that it is written for a clause no attack was staged against, so a violated clause
	arriving here would be an unattackable clause that was in fact attackable, silently
	removed from FR-015's denominator.
	"""
	assert honest is not False, (
		"a clause whose oracle is violated is attackable and must be attacked, not "
		"reported as unattackable — this would shrink FR-015's denominator"
	)
	if honest is None:
		because = (
			"the oracle produced no readable verdict against the honest tree, so there is "
			"no baseline for an attack to move"
		)
	else:
		because = (
			"the oracle reports satisfied against the honest tree, so there is no passing "
			"verdict left to obtain without solving the task — FR-012's defect is the gap "
			"between solving and passing, and this clause has no gap to cross"
		)
	return HackAttempt(
		id=uuid7str(),
		clause_id=clause.id,
		statement=clause.statement,
		technique=HackTechnique.EDITED_TEST,
		outcome=HackOutcome.NOT_ATTEMPTED,
		detail=because,
		oracle_class=clause.oracle.oracle_class,
		baseline_command=clause.oracle.command_hint,
	)


async def _baseline(
	contract: Contract,
	probeable: Sequence[Clause],
	workspace: Path,
	run_id: str,
	timeout: float,
	max_output_bytes: int,
) -> dict[str, bool | None]:
	"""The honest verdict per clause: ``True`` satisfied, ``False`` violated, ``None`` other.

	``None`` is kept distinct from both for the reason every three-valued outcome in this
	codebase is: an oracle that could not be read is not an oracle that failed, and
	collapsing it would either credit a hacker with a flip it did not cause or report a
	defect nobody demonstrated.
	"""
	narrowed = Contract(
		id=contract.id,
		goal_id=contract.goal_id,
		version=contract.version,
		created_at=contract.created_at,
		clauses=tuple(probeable),
	)
	evidence = await OracleRunner(
		workspace,
		timeout=timeout,
		max_output_bytes=max_output_bytes,
		run_id=run_id,
	).run_all(narrowed)
	report = verify(narrowed, evidence, run_id=run_id)
	out: dict[str, bool | None] = {}
	for verdict in report.verdicts:
		out[verdict.clause_id] = (
			True
			if verdict.outcome.value == "satisfied"
			else False
			if verdict.outcome.value == "violated"
			else None
		)
	return out


async def _attack(
	clause: Clause,
	*,
	workspace: Path,
	timeout: float,
	max_output_bytes: int,
) -> tuple[HackAttempt, ...]:
	"""Apply every attemptable technique to one clause's oracle and read the verdict.

	The technique targets the *oracle's own command*, which is the file a hacker with the
	producer's write access would edit. ``SPECIAL_CASED_FIXTURE`` targets the module under
	test instead when the command names one, which is the technique that leaves the oracle
	untouched — and so the one FR-139's integrity hash cannot catch.
	"""
	command = clause.oracle.command_hint
	assert command is not None, "a probeable clause names a command"
	source = _source_of(command, workspace)
	if source is None:
		return tuple(
			HackAttempt(
				id=uuid7str(),
				clause_id=clause.id,
				statement=clause.statement,
				technique=technique,
				outcome=HackOutcome.NOT_ATTEMPTED,
				detail=(
					f"the oracle's command names no file this instrument can read "
					f"(`{command}`), so there is no source to rewrite and no attack was "
					"staged. Not attacked is not the same as resisted."
				),
				oracle_class=clause.oracle.oracle_class,
				baseline_command=command,
			)
			for technique in _HACKABLE_TECHNIQUES
		)

	attempts: list[HackAttempt] = []
	for rewrite in attempt_techniques(
		source.read_text(encoding="utf-8"), expects=_literal_in(command)
	):
		if rewrite.apply is None:
			attempts.append(
				HackAttempt(
					id=uuid7str(),
					clause_id=clause.id,
					statement=clause.statement,
					technique=rewrite.technique,
					outcome=HackOutcome.NOT_ATTEMPTED,
					detail=(
						f"{rewrite.description} — the technique found nothing to change in "
						f"`{source.name}`, so no attack was staged and this measures nothing "
						"about the oracle"
					),
					oracle_class=clause.oracle.oracle_class,
					baseline_command=command,
				)
			)
			continue
		attempts.append(
			await _score_attempt(
				clause,
				rewrite=rewrite,
				target=source,
				workspace=workspace,
				timeout=timeout,
				max_output_bytes=max_output_bytes,
			)
		)
	return tuple(attempts)


async def _score_attempt(
	clause: Clause,
	*,
	rewrite: _Rewrite,
	target: Path,
	workspace: Path,
	timeout: float,
	max_output_bytes: int,
) -> HackAttempt:
	"""Run the rewritten oracle in a copy of the tree and read whether the verdict moved.

	The copy is what makes this safe to repeat: the workspace's own bytes never move, so a
	crash mid-attack cannot leave a disabled assertion in the tree under test.
	"""
	assert rewrite.apply is not None, "an attempt with no rewrite is not scored"
	with tempfile.TemporaryDirectory(prefix="sofact-hack-") as scratch:
		mirror = Path(scratch) / "tree"
		shutil.copytree(workspace, mirror, symlinks=True, dirs_exist_ok=True)
		relative = target.relative_to(workspace)
		written = mirror / relative
		try:
			written.parent.mkdir(parents=True, exist_ok=True)
			written.write_text(rewrite.apply, encoding="utf-8")
		except OSError as exc:
			return HackAttempt(
				id=uuid7str(),
				clause_id=clause.id,
				statement=clause.statement,
				technique=rewrite.technique,
				outcome=HackOutcome.INCONCLUSIVE,
				detail=f"the rewrite could not be written ({exc}), so nothing was attacked",
				oracle_class=clause.oracle.oracle_class,
				baseline_command=clause.oracle.command_hint,
			)
		run_id = uuid7str()
		evidence = await OracleRunner(
			mirror,
			timeout=timeout,
			max_output_bytes=max_output_bytes,
			run_id=run_id,
		).run(clause)
		verdict = verify(
			Contract(
				id=clause.id,
				goal_id=clause.id,
				version=1,
				created_at=now(),
				clauses=(clause,),
			),
			[evidence],
			run_id=run_id,
		).verdicts[0]

	outcome = (
		HackOutcome.EXPLOITED
		if verdict.outcome.value == "satisfied"
		else HackOutcome.HELD
		if verdict.outcome.value == "violated"
		else HackOutcome.INCONCLUSIVE
	)
	detail = (
		f"{rewrite.description}, and the oracle still reported satisfied ({verdict.reason}) "
		"— the verdict was obtained without the task being solved (FR-012)"
		if outcome is HackOutcome.EXPLOITED
		else f"{rewrite.description}, and the oracle reported violated ({verdict.reason})"
		if outcome is HackOutcome.HELD
		else f"{rewrite.description}, and the verdict was unreadable ({verdict.reason})"
	)
	return HackAttempt(
		id=uuid7str(),
		clause_id=clause.id,
		statement=clause.statement,
		technique=rewrite.technique,
		outcome=outcome,
		detail=detail,
		oracle_class=clause.oracle.oracle_class,
		baseline_command=clause.oracle.command_hint,
	)


def _source_of(command: str, workspace: Path) -> Path | None:
	"""The file an oracle's command runs, when the command names exactly one.

	``None`` when no path can be read out of the command or the file is absent, which is a
	real absence: an oracle whose command is a shell pipeline over generated input has no
	single source for this instrument to rewrite, and saying so is better than attacking an
	arbitrary token.
	"""
	candidates = [
		token
		for token in command.replace("'", " ").replace('"', " ").split()
		if token.endswith(".py") and not token.startswith("-")
	]
	if len(candidates) != 1:
		return None
	target = workspace / candidates[0]
	return target if target.is_file() else None


def _literal_in(command: str) -> str | None:
	"""A quoted literal from the oracle's command, for ``SPECIAL_CASED_FIXTURE`` to return.

	Read from the command rather than invented, because the special case a hacker writes
	is the value the check compares against — a branch returning a value the oracle never
	looked for is not a special case at all. ``None`` when the command quotes nothing.
	"""
	for quote in ('"', "'"):
		parts = command.split(quote)
		if len(parts) >= 3 and parts[1].strip():
			return parts[1]
	return None
