"""FR-012–015 — the adversarial audit: a hacker, a fixer, a sampler and a rate.

The requirement's claim is about *false confidence* one level up from FR-107: an oracle
that can be satisfied without solving the task is a verdict the factory should not have
issued. These tests are therefore about three things and the third matters most:

* an attempt that **gets through** is reported as an exploit, with the technique named;
* an attempt that is **repelled** is reported as held, and the two are different rows;
* an attempt that **never happened** — because FR-014's sample skipped it, or because the
  technique found nothing to change, or because the oracle already passed honestly — is
  reported as neither. That is the control arm, and without it "no exploits" is
  indistinguishable from "no attacks".

Every attack is driven against a real temporary tree with a real oracle command, because
the measurement is the verdict's movement and a fabricated verdict would be the same
defect as a manufactured oracle: agreement with itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sofact._uuid7 import uuid7str
from sofact.adversarial import (
	DEFAULT_SAMPLE_FLOOR,
	UNADDRESSED_TECHNIQUES,
	attempt_techniques,
	fix_exploit,
	run_adversarial_audit,
	sample_decision,
)
from sofact.views import (
	AUDIT_REQUIREMENTS,
	AdversarialAuditReport,
	AutonomyLevel,
	Clause,
	ClauseKind,
	Contract,
	HackAttempt,
	HackOutcome,
	HackTechnique,
	ModuleClass,
	OracleClass,
	OracleDeclaration,
	now,
)

# --------------------------------------------------------------------------- #
# fixtures — a real tree, a real oracle, and a real check to defeat
# --------------------------------------------------------------------------- #

_CHECK = """\
import sys

TOTAL = int(sys.argv[1])
if TOTAL != 12:
    sys.exit(1)
print("totals agree")
"""

_PLAIN_CHECK = """\
import sys

TOTAL = int(sys.argv[1])
assert TOTAL == 12
print("totals agree")
"""

_GUARDED_CHECK = """\
import sys

TOTAL = int(sys.argv[1])
assert TOTAL == 12
if TOTAL != 12:
    sys.exit(1)
print("totals agree")
"""

_IMPLEMENTATION = """\
def total(rows):
    return sum(rows)
"""


def _tree(root: Path, *, check: str = _CHECK, name: str = "check_total.py") -> Path:
	"""A workspace holding a check that fails unless it is given the right total."""
	(root / name).write_text(check, encoding="utf-8")
	(root / "report.py").write_text(_IMPLEMENTATION, encoding="utf-8")
	return root


def _clause(command: str, *, statement: str = "the report totals every row") -> Clause:
	return Clause(
		id=uuid7str(),
		statement=statement,
		kind=ClauseKind.POSITIVE,
		oracle=OracleDeclaration(
			oracle_class=OracleClass.PROPERTY,
			description="checked by running the total against a known row set",
			command_hint=command,
		),
	)


def _contract(*clauses: Clause) -> Contract:
	return Contract(
		id=uuid7str(),
		goal_id=uuid7str(),
		version=1,
		created_at=now(),
		clauses=clauses,
	)


# --------------------------------------------------------------------------- #
# FR-014 — the sample, which is the rule that decides whether anything is attacked
# --------------------------------------------------------------------------- #


class TestTheSampleDecidesWhetherAnythingIsAttacked:
	"""FR-014's rule, held to both of its boundaries.

	The rule is a function of the ceiling alone — "sampled … on lanes at or below L3, and
	run on 100% of changes on lanes above L3" — so both sides are asserted with levels and
	ordinals rather than with a rate that could drift with N.
	"""

	def test_a_change_above_l3_is_always_attacked(self) -> None:
		"""The requirement's own boundary, and the one that must not be sampled away.

		Above L3 nobody else is reading the change, so a sampled audit there would leave
		whole changes unexamined in exactly the band where the factory is unattended.
		"""
		for ordinal in (1, 2, 3, 4, 5, 17):
			assert sample_decision(ordinal=ordinal, ceiling=AutonomyLevel.L4) is True, ordinal
		assert sample_decision(ordinal=1, ceiling=AutonomyLevel.L5) is True

	def test_a_change_at_l3_is_sampled_and_not_always_attacked(self) -> None:
		"""The other side. An implementation that returned ``True`` unconditionally would
		pass the boundary above and fail here, which is why both are asserted."""
		attacked = [
			ordinal
			for ordinal in range(1, DEFAULT_SAMPLE_FLOOR * 3 + 1)
			if sample_decision(ordinal=ordinal, ceiling=AutonomyLevel.L3)
		]
		assert attacked == [DEFAULT_SAMPLE_FLOOR, DEFAULT_SAMPLE_FLOOR * 2, DEFAULT_SAMPLE_FLOOR * 3]

	def test_the_stride_is_deterministic_so_the_rate_is_reproducible(self) -> None:
		"""FR-015's trend is read from the log, so the same change must sample the same way
		twice. A random draw would make the rate irreproducible from the ledger alone.

		Reproducibility alone is weak evidence for a pure function, so the pattern is also
		asserted against the rule and ``lane`` is held to being *ignored*: FR-014's sample is
		a function of the ceiling, and a lane that changed the answer would make two lanes'
		rates incomparable without saying so.
		"""
		first = [sample_decision(ordinal=n, ceiling=AutonomyLevel.L2) for n in range(1, 20)]
		second = [sample_decision(ordinal=n, ceiling=AutonomyLevel.L2) for n in range(1, 20)]
		assert first == second
		assert first == [
			n % DEFAULT_SAMPLE_FLOOR == 0 for n in range(1, 20)
		], "the stride is ordinal % N, not an arbitrary reproducible pattern"
		assert first == [
			sample_decision(ordinal=n, lane=ModuleClass.G1, ceiling=AutonomyLevel.L2)
			for n in range(1, 20)
		], "FR-014's sample is a function of the ceiling alone"

	def test_an_ordinal_below_one_is_refused(self) -> None:
		with pytest.raises(AssertionError, match="1-based"):
			sample_decision(ordinal=0, ceiling=AutonomyLevel.L3)


# --------------------------------------------------------------------------- #
# FR-012 — the hacker, and what an attempt actually does
# --------------------------------------------------------------------------- #


class TestTheHackerObtainsAVerdictWithoutSolvingTheTask:
	async def test_disabling_the_assertion_flips_the_verdict_and_is_an_exploit(
		self, tmp_path: Path
	) -> None:
		"""FR-012's defect, demonstrated end to end.

		The check is driven with a *failing* total, so the honest verdict is violated and a
		hacker has a passing verdict to obtain. Disabling the assertion obtains it: the
		file still runs, still prints its success line, and the oracle reports satisfied
		without the total having been computed correctly. That flip is the exploit.
		"""
		tree = _tree(tmp_path, check=_PLAIN_CHECK)
		clause = _clause(f"{sys.executable} check_total.py 11")

		report = await run_adversarial_audit(
			_contract(clause), workspace=tree, ceiling=AutonomyLevel.L4
		)

		disabled = [a for a in report.attempts if a.technique is HackTechnique.DISABLED_ASSERTION]
		assert len(disabled) == 1
		assert disabled[0].outcome is HackOutcome.EXPLOITED
		assert disabled[0].is_finding
		assert disabled[0] in report.exploited
		assert report.passed is False

	async def test_an_attempt_the_oracle_survives_is_held_and_not_a_finding(
		self, tmp_path: Path
	) -> None:
		"""The control arm, and the one that makes the exploit above mean something.

		``_GUARDED_CHECK`` asserts *and* exits non-zero on the same condition, so removing
		the assertion leaves the check failing: the verdict stays violated and the attempt
		is ``HELD``. Without this, "an exploit was found" would be indistinguishable from an
		instrument that reports every attempt as one.

		``EDITED_TEST`` still exploits it, and that is the honest result rather than a leak:
		the technique replaces the whole file, so *every* oracle whose honest verdict is
		violated falls to it — a hacker who can write the test file always can. What the
		guarded check measures is resistance to the subtle rewrite, so the assertion names
		``techniques_exploited`` rather than emptiness: the blunt technique got through and
		the two that leave the file runnable did not.
		"""
		tree = _tree(tmp_path, check=_GUARDED_CHECK)
		clause = _clause(f"{sys.executable} check_total.py 11")

		report = await run_adversarial_audit(
			_contract(clause), workspace=tree, ceiling=AutonomyLevel.L4
		)

		disabled = [a for a in report.attempts if a.technique is HackTechnique.DISABLED_ASSERTION]
		assert len(disabled) == 1
		assert disabled[0].outcome is HackOutcome.HELD
		assert not disabled[0].is_finding
		assert report.techniques_exploited == (HackTechnique.EDITED_TEST,)
		assert disabled[0] not in report.exploited

	async def test_an_oracle_that_passes_honestly_is_not_attempted_not_held(
		self, tmp_path: Path
	) -> None:
		"""The outcome that keeps the audit from crediting an attack that never happened.

		The oracle already reports satisfied against the honest tree, so there is no
		passing verdict left to obtain. It is ``NOT_ATTEMPTED`` — the same bucket as a
		change FR-014's sample skipped — and not ``HELD``, which would credit the oracle
		with resisting an attack that could not have been meaningful, and not
		``INCONCLUSIVE``, which is reserved for an attack that ran and could not be read.
		"""
		tree = _tree(tmp_path)
		clause = _clause(f"{sys.executable} check_total.py 12")

		report = await run_adversarial_audit(
			_contract(clause), workspace=tree, ceiling=AutonomyLevel.L4
		)

		assert report.exploited == ()
		assert report.attempted == ()
		assert report.exploit_rate is None
		assert all(a.outcome is HackOutcome.NOT_ATTEMPTED for a in report.attempts)
		assert "no passing verdict left to obtain" in report.attempts[0].detail

	async def test_the_techniques_a_source_transform_cannot_attempt_are_named(self) -> None:
		"""FR-012 lists five techniques and this instrument attempts three.

		The other two need a model to invent code that satisfies an intent without
		implementing it, which is exactly what the factory must not do unattended. The gap
		is a module constant rather than a comment, so a report can state it and a reader
		cannot read a zero as "nothing gets through".
		"""
		assert set(UNADDRESSED_TECHNIQUES) == {
			HackTechnique.HARDCODED_EXPECTED,
			HackTechnique.OVERFIT_TO_SAMPLE,
		}
		assert not set(UNADDRESSED_TECHNIQUES) & {
			HackTechnique.EDITED_TEST,
			HackTechnique.DISABLED_ASSERTION,
			HackTechnique.SPECIAL_CASED_FIXTURE,
		}

	async def test_the_attempted_set_is_a_proper_subset_of_the_requirement(self) -> None:
		"""``discharged`` must not claim FR-012 when two of its five techniques were never
		attempted — the same rule :meth:`OracleAuditReport.discharged` states for FR-107."""
		report = AdversarialAuditReport(
			id=uuid7str(),
			plan_id=uuid7str(),
			contract_id=uuid7str(),
			contract_hash="a" * 64,
			rendered_at=now(),
		)
		assert report.attempted == ()
		assert report.discharged == ()
		assert report.not_implemented == AUDIT_REQUIREMENTS
		assert report.exploit_rate is None

	async def test_a_clause_whose_oracle_names_no_file_is_not_attempted(
		self, tmp_path: Path
	) -> None:
		"""An oracle that is a shell pipeline over generated input has no single source to
		rewrite, and saying so beats attacking an arbitrary token.

		The command *fails* honestly, so the clause is genuinely attackable and the run
		reaches the source lookup rather than the baseline branch. It is ``NOT_ATTEMPTED``
		rather than ``INCONCLUSIVE`` for the reason the honest-pass case is: no attack was
		staged, so the clause must not enter FR-015's denominator. ``INCONCLUSIVE`` is
		reserved for an attack that ran and could not be read.
		"""
		tree = _tree(tmp_path)
		clause = _clause(f'{sys.executable} -c "raise SystemExit(1)"')

		report = await run_adversarial_audit(
			_contract(clause), workspace=tree, ceiling=AutonomyLevel.L4
		)

		assert all(a.outcome is HackOutcome.NOT_ATTEMPTED for a in report.attempts)
		assert report.attempted == ()
		assert report.exploit_rate is None
		assert "names no file this instrument can read" in report.attempts[0].detail


class TestTheRewritesAreRealSourceTransforms:
	"""``attempt_techniques`` is pure, so the transforms are held to their own boundary."""

	def test_disabling_assertions_keeps_the_file_and_removes_every_assert(self) -> None:
		"""The technique that has to leave a *runnable* file behind: a rewrite that broke
		the syntax would be discarded and would measure nothing."""
		rewrites = attempt_techniques(_PLAIN_CHECK)
		disabled = next(r for r in rewrites if r.technique is HackTechnique.DISABLED_ASSERTION)
		assert disabled.apply is not None
		assert "assert " not in disabled.apply
		assert "print" in disabled.apply
		compile(disabled.apply, "check_total.py", "exec")

	def test_a_file_with_no_assertion_yields_no_rewrite_for_that_technique(self) -> None:
		"""An absence, not an empty edit. A rewrite identical to the pristine source would
		be scored as held for a reason about the technique rather than about the oracle."""
		rewrites = attempt_techniques(_CHECK)
		disabled = next(r for r in rewrites if r.technique is HackTechnique.DISABLED_ASSERTION)
		assert disabled.apply is None

	def test_the_comment_the_rewrite_writes_does_not_itself_contain_an_assertion(self) -> None:
		"""The rewrite's own `pass  # assertion disabled` comment is the reason the
		assertion above is spelled `assert ` and not `assert`: a check that looked for the
		bare word would flag the comment the transform writes, which is the substring
		mistake a gate makes when its predicate is a superstring of what it looks for."""
		rewrites = attempt_techniques(_PLAIN_CHECK)
		disabled = next(r for r in rewrites if r.technique is HackTechnique.DISABLED_ASSERTION)
		assert disabled.apply is not None
		assert "# assertion disabled" in disabled.apply
		assert "assert " not in disabled.apply

	def test_the_special_case_returns_the_literal_the_command_names(self) -> None:
		"""``SPECIAL_CASED_FIXTURE`` is the technique FR-139's hash cannot see, because it
		leaves the oracle untouched. It inserts a branch returning the value the check
		compares against — read from the command, never invented."""
		rewrites = attempt_techniques(_IMPLEMENTATION, expects="12")
		special = next(r for r in rewrites if r.technique is HackTechnique.SPECIAL_CASED_FIXTURE)
		assert special.apply is not None
		assert "return '12'" in special.apply
		compile(special.apply, "report.py", "exec")

	def test_without_a_named_literal_the_special_case_finds_nothing(self) -> None:
		"""A special case for a value nobody named is not a special case."""
		rewrites = attempt_techniques(_IMPLEMENTATION, expects=None)
		special = next(r for r in rewrites if r.technique is HackTechnique.SPECIAL_CASED_FIXTURE)
		assert special.apply is None

	def test_every_attemptable_technique_produces_exactly_one_rewrite(self) -> None:
		"""The count is asserted rather than assumed, so adding a technique to the enum
		without adding its transform fails here rather than silently shrinking coverage."""
		rewrites = attempt_techniques(_PLAIN_CHECK, expects="12")
		assert len(rewrites) == 3
		assert {r.technique for r in rewrites} == {
			HackTechnique.EDITED_TEST,
			HackTechnique.DISABLED_ASSERTION,
			HackTechnique.SPECIAL_CASED_FIXTURE,
		}


# --------------------------------------------------------------------------- #
# FR-013 — the fixer, and the regression case that gets dropped
# --------------------------------------------------------------------------- #


class TestTheFixerClosesTheExploitAndKeepsTheCase:
	"""FR-013 has two halves and the second is the one that gets dropped."""

	def _exploit(self) -> HackAttempt:
		return HackAttempt(
			id=uuid7str(),
			clause_id=uuid7str(),
			statement="the report totals every row",
			technique=HackTechnique.DISABLED_ASSERTION,
			outcome=HackOutcome.EXPLOITED,
			detail="the assertion was disabled and the oracle still reported satisfied",
			oracle_class=OracleClass.PROPERTY,
			baseline_command="python check_total.py 11",
		)

	def test_a_fix_must_answer_the_retention_question(self) -> None:
		"""Neither a path nor a reason is refused by the type: an absence with no reason is
		indistinguishable from an oversight, and the two need different responses."""
		from pydantic import ValidationError

		with pytest.raises(ValidationError, match="retained no regression case"):
			fix_exploit(self._exploit(), closed=True, detail="the oracle now fails on a bad total")

	def test_a_retained_case_does_not_also_carry_a_reason_for_none(self) -> None:
		from pydantic import ValidationError

		with pytest.raises(ValidationError, match="does not also carry a reason"):
			fix_exploit(
				self._exploit(),
				closed=True,
				detail="closed",
				regression_case="tests/test_totals.py::test_assertion_present",
				regression_because="not needed",
			)

	def test_a_held_attempt_has_nothing_for_a_fixer_to_close(self) -> None:
		"""A fixer row for an attempt that found nothing would make the exploit count and
		the fix count disagree, which is how a rate stops meaning anything."""
		held = self._exploit().model_copy(update={"outcome": HackOutcome.HELD})
		with pytest.raises(ValueError, match="did not demonstrate an exploit"):
			fix_exploit(held, closed=True, detail="nothing to do", regression_because="none")

	def test_the_fix_reaches_the_report_and_closes_the_exploit(self) -> None:
		"""The seam, driven through the report's own accessor rather than the fix alone: a
		fix that does not reach :attr:`exploits_unclosed` is a fix nothing consults.

		``passed`` stays ``False``, and that is the deliberate half. A fixer's "closed" is a
		*claim* — nothing in this pass verifies it, the verification is the next audit
		attacking the rewritten oracle — so a pass that found an exploit still failed,
		however promptly it was answered. ``exploits_unclosed`` is the separate signal
		saying whether anything is still open, and the two answer different questions.
		"""
		exploit = self._exploit()
		fix = fix_exploit(
			exploit,
			closed=True,
			detail="the oracle was rewritten to compare a computed total",
			regression_case="tests/test_totals.py::test_assertion_present",
		)
		report = AdversarialAuditReport(
			id=uuid7str(),
			plan_id=uuid7str(),
			contract_id=uuid7str(),
			contract_hash="a" * 64,
			rendered_at=now(),
			attempts=(exploit,),
			fixes=(fix,),
		)
		assert report.exploits_unclosed == ()
		assert report.passed is False
		assert report.exploit_rate == 1.0

	def test_an_exploit_whose_fix_did_not_close_it_stays_open(self) -> None:
		"""``closed=False`` is a real outcome and must not be read as a fix. The report
		derives openness from the fixes rather than from their count."""
		exploit = self._exploit()
		fix = fix_exploit(
			exploit,
			closed=False,
			detail="the oracle needs a rewrite that is not in this session's scope",
			regression_because="no case can be written until the oracle is rewritten",
		)
		report = AdversarialAuditReport(
			id=uuid7str(),
			plan_id=uuid7str(),
			contract_id=uuid7str(),
			contract_hash="a" * 64,
			rendered_at=now(),
			attempts=(exploit,),
			fixes=(fix,),
		)
		assert report.exploits_unclosed == (exploit,)
		assert report.passed is False


# --------------------------------------------------------------------------- #
# FR-015 — the rate, and the three states it must not collapse
# --------------------------------------------------------------------------- #


class TestTheExploitRateDistinguishesNothingFoundFromNothingTried:
	"""FR-015's rate is a *rate*, and a rate over zero attempts is undefined."""

	def _report(self, *outcomes: HackOutcome) -> AdversarialAuditReport:
		attempts = tuple(
			HackAttempt(
				id=uuid7str(),
				clause_id=uuid7str(),
				statement="the report totals every row",
				technique=HackTechnique.DISABLED_ASSERTION,
				outcome=outcome,
				detail="detail",
				oracle_class=OracleClass.PROPERTY,
			)
			for outcome in outcomes
		)
		return AdversarialAuditReport(
			id=uuid7str(),
			plan_id=uuid7str(),
			contract_id=uuid7str(),
			contract_hash="a" * 64,
			rendered_at=now(),
			attempts=attempts,
		)

	def test_a_rate_over_no_attempt_is_none_and_not_zero(self) -> None:
		"""FR-015's target is zero, so a zero over nothing is the target state printed for
		a lane nobody attacked. ``None`` is what keeps the plateau from reading as success."""
		report = self._report(HackOutcome.NOT_ATTEMPTED, HackOutcome.NOT_ATTEMPTED)
		assert report.attempted == ()
		assert report.exploit_rate is None
		assert report.discharged == ()

	def test_a_rate_over_attempts_that_all_held_is_zero(self) -> None:
		"""The control arm: an instrument that returned ``None`` for everything would pass
		the test above and fail this one."""
		report = self._report(HackOutcome.HELD, HackOutcome.HELD)
		assert report.exploit_rate == 0.0
		assert report.discharged == ("FR-012", "FR-014", "FR-015")

	def test_the_rate_counts_exploits_per_attempt_and_names_the_techniques(self) -> None:
		"""FR-015 wants a rate, and a plateau needs the techniques beside it: one recurring
		is a fixable defect, five is a subsystem nobody is auditing."""
		report = self._report(HackOutcome.EXPLOITED, HackOutcome.HELD, HackOutcome.NOT_ATTEMPTED)
		assert report.exploit_rate == 0.5
		assert report.techniques_exploited == (HackTechnique.DISABLED_ASSERTION,)
		assert report.discharged == AUDIT_REQUIREMENTS

	def test_an_inconclusive_attempt_counts_as_attempted_but_not_as_an_exploit(self) -> None:
		"""It ran, so it is in the denominator — the same rule a timed-out mutant gets in
		:mod:`sofact.mutation`. It demonstrated nothing, so it is not a numerator."""
		report = self._report(HackOutcome.INCONCLUSIVE, HackOutcome.HELD)
		assert len(report.attempted) == 2
		assert report.exploit_rate == 0.0
		assert report.passed is True


class TestTheSampledOutPassIsNotAClearance:
	"""The end-to-end arm of FR-014: a change the sample skips must not be attacked."""

	async def test_a_sampled_out_change_attacks_nothing_and_says_so(self, tmp_path: Path) -> None:
		tree = _tree(tmp_path, check=_PLAIN_CHECK)
		clause = _clause(f"{sys.executable} check_total.py 11")

		report = await run_adversarial_audit(
			_contract(clause),
			workspace=tree,
			ceiling=AutonomyLevel.L2,
			ordinal=1,
		)

		assert len(report.attempts) == 3
		assert all(a.outcome is HackOutcome.NOT_ATTEMPTED for a in report.attempts)
		assert report.attempted == ()
		assert report.exploit_rate is None
		assert report.passed is True
		assert report.not_implemented == AUDIT_REQUIREMENTS
		assert "Not attacked is not the same as resisted" in report.attempts[0].detail

	async def test_the_same_change_above_l3_is_attacked(self, tmp_path: Path) -> None:
		"""The other side of FR-014, driven through the same call with only the ceiling
		changed — so the difference is the rule and not the fixture.

		Not every technique reaches the oracle, and the two reasons for a
		``NOT_ATTEMPTED`` row are told apart here: this command quotes no literal, so
		``SPECIAL_CASED_FIXTURE`` has nothing to special-case and says so. The assertion
		that the *sampling* reason is absent is what keeps the two from collapsing — a
		change attacked at L4 must not carry the row that says it was skipped.
		"""
		tree = _tree(tmp_path, check=_PLAIN_CHECK)
		clause = _clause(f"{sys.executable} check_total.py 11")

		report = await run_adversarial_audit(
			_contract(clause),
			workspace=tree,
			ceiling=AutonomyLevel.L4,
			ordinal=1,
		)

		assert report.attempted != ()
		assert report.exploited != ()
		assert "Not attacked is not the same as resisted" not in "".join(
			a.detail for a in report.attempts
		)
		assert all(
			a.outcome is not HackOutcome.NOT_ATTEMPTED
			for a in report.attempts
			if a.technique is not HackTechnique.SPECIAL_CASED_FIXTURE
		)

	async def test_the_workspace_is_never_moved_by_an_attack(self, tmp_path: Path) -> None:
		"""``digest_tree`` is FR-006's cache key, so a disabled assertion left behind would
		invalidate a verdict nothing touched. The copy is what prevents it."""
		tree = _tree(tmp_path, check=_PLAIN_CHECK)
		before = {p.name: p.read_bytes() for p in sorted(tree.iterdir())}
		clause = _clause(f"{sys.executable} check_total.py 11")

		await run_adversarial_audit(_contract(clause), workspace=tree, ceiling=AutonomyLevel.L4)

		after = {p.name: p.read_bytes() for p in sorted(tree.iterdir())}
		assert after == before
		assert "assert TOTAL == 12" in (tree / "check_total.py").read_text(encoding="utf-8")

	async def test_a_contract_with_no_executable_oracle_audits_nothing(self, tmp_path: Path) -> None:
		"""A contract of intentions has nothing to attack, and the report says so rather
		than printing a clean rate over nothing — the rule FR-107's audit states."""
		tree = _tree(tmp_path)
		clause = _clause("true")
		intention = clause.model_copy(
			update={"oracle": clause.oracle.model_copy(update={"command_hint": None})}
		)

		report = await run_adversarial_audit(
			_contract(intention), workspace=tree, ceiling=AutonomyLevel.L4
		)

		assert report.attempts == ()
		assert report.changes_considered == 0
		assert report.exploit_rate is None
		assert report.discharged == ()

	async def test_the_report_names_the_sample_rate_it_used(self, tmp_path: Path) -> None:
		"""Two rates computed under different N are not comparable, and a reader of the log
		months later cannot recover which was in force."""
		tree = _tree(tmp_path, check=_PLAIN_CHECK)
		clause = _clause(f"{sys.executable} check_total.py 11")

		report = await run_adversarial_audit(
			_contract(clause), workspace=tree, ceiling=AutonomyLevel.L4
		)

		assert report.sample_rate == DEFAULT_SAMPLE_FLOOR
		assert len(report.contract_hash) == 64
		assert report.changes_considered == 1
