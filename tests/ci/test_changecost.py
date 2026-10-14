"""FR-159: the change-cost instrument is a proxy, and its baseline is unmeasured.

FR-159's own words set the substance of this file: the instrument is a **proxy** (NFR-024
applies, and it must be declared as one), it measures change *cost* and not design
*quality*, and it is admissible only as a **trend alarm** and a Mode M ceiling *input*,
never as a verdict. So the tests below are not "does it count lines". They are:

* does a footprint come off a real repository's real diff, including the two shapes that
  make a naive reader wrong — a rename and a binary file;
* does a rising footprint on *comparable* units raise the alarm, and does an incomparable
  one not;
* does a unit with no recorded change report **unmeasured** rather than clean, which is
  ADR-0054's precedent and the whole reason the row carries ``measured``;
* and do the two constants FR-159 would have to move — the evolvability debt and the Mode M
  ceiling — stay exactly where FR-158 put them.

The last one is the test that matters most and the one that would be easiest to lose: an
instrument landing is precisely the event that tempts a report to promote its own proxy.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from sofact._uuid7 import uuid7str
from sofact.changecost import (
	load_change_units,
	measure_change_costs,
	pin_unit,
	trend_statement,
)
from sofact.git import GitUnavailableError, diff_footprint, git_available, head_commit
from sofact.views import (
	CHANGE_COST_BASELINE_UNMEASURED,
	CHANGE_COST_NOT_A_VERIFICATION,
	CHANGE_COST_PROXY_DECLARATION,
	CHANGE_COST_RISE_FACTOR,
	EVOLVABILITY_DEBT,
	MAINTAINABILITY_NOT_VERIFIED,
	MODE_M_CEILING,
	AutonomyLevel,
	ChangeCostReport,
	ChangeUnit,
	DeliveryReport,
	now,
)

pytestmark = pytest.mark.skipif(not git_available(), reason="git is not installed")


async def git(workspace: Path, *args: str) -> str:
	"""Run git the way the module does, and return its stdout."""
	process = await asyncio.create_subprocess_exec(
		"git",
		*args,
		cwd=workspace,
		stdin=asyncio.subprocess.DEVNULL,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)
	stdout, stderr = await process.communicate()
	assert process.returncode == 0, f"git {' '.join(args)} failed: {stderr.decode()}"
	return stdout.decode("utf-8", errors="replace")


async def a_repository(root: Path) -> Path:
	"""A real repository with one commit, so a diff has something to be against."""
	workspace = root / "repo"
	workspace.mkdir()
	await git(workspace, "init", "-q", ".")
	await git(workspace, "config", "user.email", "factory@example.invalid")
	await git(workspace, "config", "user.name", "SoFact")
	(workspace / "src" / "pkg").mkdir(parents=True)
	(workspace / "src" / "pkg" / "one.py").write_text("a\nb\nc\n", encoding="utf-8")
	await git(workspace, "add", "--all")
	await git(workspace, "commit", "--quiet", "-m", "first")
	return workspace


async def commit(workspace: Path, message: str) -> str:
	"""Commit whatever is in the tree, and return the new HEAD."""
	await git(workspace, "add", "--all")
	await git(workspace, "commit", "--quiet", "-m", message)
	sha = await head_commit(workspace)
	assert sha is not None, "a commit that succeeded must leave a resolvable HEAD"
	return sha


# --------------------------------------------------------------------------- #
# the footprint comes off a real diff
# --------------------------------------------------------------------------- #


class TestTheFootprintIsReadFromARealDiff:
	"""A mocked git would assert that SoFact runs the commands its author believed were
	right, which is exactly the belief FR-159 exists to check. So: real git, real tree."""

	async def test_the_counts_are_the_diff_s(self, tmp_path: Path) -> None:
		workspace = await a_repository(tmp_path)
		base = await head_commit(workspace)
		assert base is not None
		(workspace / "src" / "pkg" / "one.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
		head = await commit(workspace, "grow one")

		footprint = await diff_footprint(workspace, base=base, head=head)

		assert footprint.files_touched == 1
		assert footprint.lines_added == 2
		assert footprint.lines_removed == 0
		assert footprint.lines_changed == 2
		assert footprint.hunks == 1
		assert footprint.modules_crossed == 1

	async def test_a_rename_is_one_file_and_no_lines(self, tmp_path: Path) -> None:
		"""Measured 2026-10-15 against a real repository: ``--numstat -z`` writes a rename
		as ``0\\t0\\t`` **with an empty path field**, then the old and new names as their
		own NUL-separated fields.

		The empty *path* is the tell and not the empty counts, and the difference is not
		cosmetic: a reader keyed on the counts treats the rename as an ordinary file with
		no name, which gets the *file* count right by luck (the two bare name fields are
		skipped by the ``len(parts) < 3`` guard) while filing the rename under a module
		called ``""``.

		So the discriminating assertion is ``modules_crossed``, and it needs the rename's
		own package to also carry an ordinary edit — otherwise the correct module
		(``src/pkg``) and the defect's nameless one (``""``) are two distinct names either
		way and the count comes out the same. Canaried 2026-10-15: the file-count, line
		and *plain* module assertions all passed against the misfiling reader.
		"""
		workspace = await a_repository(tmp_path)
		base = await head_commit(workspace)
		assert base is not None
		await git(workspace, "mv", "src/pkg/one.py", "src/pkg/renamed.py")
		(workspace / "src" / "pkg" / "edited.py").write_text("y\n", encoding="utf-8")
		head = await commit(workspace, "rename and an edit beside it")

		footprint = await diff_footprint(workspace, base=base, head=head)

		assert footprint.files_touched == 2, "a rename is one file, not two"
		assert footprint.lines_added == 1, "moving a file changes no line of it"
		assert footprint.lines_removed == 0
		assert footprint.binary_paths == (), "a rename is not a binary"
		assert footprint.modules_crossed == 1, (
			"both paths are src/pkg. Two means the rename was filed under a nameless module"
		)

	async def test_a_binary_is_named_and_not_counted_as_zero(self, tmp_path: Path) -> None:
		"""``--numstat`` reports ``-`` for both counts on a binary path. Reading that as
		zero would let a unit that added a 40 MB artefact report the footprint of a
		comment, so the path is named and the line totals exclude it."""
		workspace = await a_repository(tmp_path)
		base = await head_commit(workspace)
		assert base is not None
		(workspace / "blob.bin").write_bytes(b"\x00\x01\x02\x03")
		head = await commit(workspace, "add a binary")

		footprint = await diff_footprint(workspace, base=base, head=head)

		assert footprint.files_touched == 1, "the file is still a file that was touched"
		assert footprint.binary_paths == ("blob.bin",), "named, not silently zeroed"
		assert footprint.lines_added == 0
		assert footprint.lines_removed == 0

	async def test_modules_crossed_is_the_package_and_not_the_layout(self, tmp_path: Path) -> None:
		"""``src/sofact/git.py`` and ``src/sofact/views.py`` are one module. A reader
		taking the first path segment would call both ``src`` and count every change to
		the tree as crossing one module, which is a measurement of nothing."""
		workspace = await a_repository(tmp_path)
		base = await head_commit(workspace)
		assert base is not None
		(workspace / "src" / "pkg" / "one.py").write_text("a\nb\nc\nd\n", encoding="utf-8")
		(workspace / "src" / "pkg" / "two.py").write_text("z\n", encoding="utf-8")
		(workspace / "other").mkdir()
		(workspace / "other" / "three.py").write_text("y\n", encoding="utf-8")
		head = await commit(workspace, "two packages")

		footprint = await diff_footprint(workspace, base=base, head=head)

		assert footprint.files_touched == 3
		assert footprint.modules_crossed == 2, "src/pkg and other, not src and other"

	async def test_a_hunk_count_separates_scattered_from_contiguous(self, tmp_path: Path) -> None:
		"""Two units can change the same number of lines while one makes a single edit and
		the other makes several scattered ones. It is the scattered one that is shotgun
		surgery, and a lines-only magnitude would call them equal."""
		workspace = await a_repository(tmp_path)
		base = await head_commit(workspace)
		assert base is not None
		(workspace / "src" / "pkg" / "one.py").write_text("a\nX\nb\nc\nY\n", encoding="utf-8")
		head = await commit(workspace, "two edits")

		footprint = await diff_footprint(workspace, base=base, head=head)

		assert footprint.hunks == 2, "two separated edits are two hunks"
		assert footprint.magnitude == footprint.lines_changed + 2

	async def test_an_unreadable_range_is_an_error_and_not_a_zero(self, tmp_path: Path) -> None:
		"""A footprint of zero and a diff that could not be taken are different facts, and
		FR-159's whole claim rests on the first being measured."""
		workspace = await a_repository(tmp_path)

		with pytest.raises(GitUnavailableError, match="not-a-commit"):
			await diff_footprint(workspace, base="not-a-commit", head="HEAD")


# --------------------------------------------------------------------------- #
# the trend, on comparable units only
# --------------------------------------------------------------------------- #


class TestTheTrendIsDifferential:
	"""FR-159: "a rising footprint on **comparable** change units". Comparable is a claim
	the unit makes about itself, before the work — a grouping derived from the diff would
	put every unit in a group of its own, which is a trend over one point."""

	async def test_a_rising_footprint_on_one_scope_raises_the_alarm(self, tmp_path: Path) -> None:
		workspace = await a_repository(tmp_path)
		first_base = await head_commit(workspace)
		assert first_base is not None
		(workspace / "src" / "pkg" / "one.py").write_text("a\nb\nc\nd\n", encoding="utf-8")
		first_head = await commit(workspace, "one line")
		(workspace / "src" / "pkg" / "one.py").write_text(
			"a\nb\nc\nd\ne\nf\ng\nh\ni\n", encoding="utf-8"
		)
		second_head = await commit(workspace, "five lines")

		small = pin_unit("add a line", scope="edit", base_commit=first_base, head_commit=first_head)
		large = pin_unit(
			"add five lines", scope="edit", base_commit=first_head, head_commit=second_head
		)
		report = await measure_change_costs([small, large], workspace=workspace)

		assert report.discharged == ("FR-159",), "two units of one scope is a trend"
		assert report.rising, "a unit that tripled its footprint must raise the alarm"
		assert report.rising[0].unit.id == large.id
		assert report.rows[0].rose is None, "the first unit has no baseline, which is not False"

	async def test_a_second_scope_does_not_set_the_first_scope_s_bar(self, tmp_path: Path) -> None:
		"""A trend line pooled over all units moves when the *mix* of work changes, so a
		quarter of small fixes would read as an improvement whether or not anything got
		cheaper to change."""
		workspace = await a_repository(tmp_path)
		base = await head_commit(workspace)
		assert base is not None
		(workspace / "src" / "pkg" / "one.py").write_text("a\nb\nc\nd\n", encoding="utf-8")
		head = await commit(workspace, "small edit")
		(workspace / "src" / "pkg" / "big.py").write_text(
			"".join(f"line {n}\n" for n in range(200)), encoding="utf-8"
		)
		huge = await commit(workspace, "a large new module")

		small = pin_unit("small", scope="edit", base_commit=base, head_commit=head)
		big = pin_unit("large", scope="new-module", base_commit=head, head_commit=huge)
		report = await measure_change_costs([small, big], workspace=workspace)

		assert set(report.scopes) == {"edit", "new-module"}
		assert report.rising == (), (
			"each scope has one unit, so neither has a baseline and neither can have risen"
		)

	async def test_the_baseline_is_earlier_units_only(self, tmp_path: Path) -> None:
		"""A baseline computed over the whole scope *including* the unit itself would move
		with the unit it is judging: a large change would raise its own bar and shrink its
		own ratio, which is the measurement excusing the thing it was built to notice."""
		workspace = await a_repository(tmp_path)
		base = await head_commit(workspace)
		assert base is not None
		(workspace / "src" / "pkg" / "one.py").write_text("a\nb\nc\nd\n", encoding="utf-8")
		one = await commit(workspace, "one")
		(workspace / "src" / "pkg" / "one.py").write_text(
			"a\nb\nc\nd\ne\nf\ng\nh\ni\nj\nk\nl\nm\nn\n", encoding="utf-8"
		)
		two = await commit(workspace, "two")

		first = pin_unit("first", scope="edit", base_commit=base, head_commit=one)
		second = pin_unit("second", scope="edit", base_commit=one, head_commit=two)
		report = await measure_change_costs([first, second], workspace=workspace)

		assert report.rows[0].baseline is None, "nothing precedes the first unit"
		assert report.rows[1].baseline == report.rows[0].footprint.magnitude, (  # type: ignore[union-attr]
			"the second unit is compared to the first and to nothing else"
		)
		assert report.rows[1].ratio is not None
		assert report.rows[1].ratio >= CHANGE_COST_RISE_FACTOR


# --------------------------------------------------------------------------- #
# unmeasured is not clean — ADR-0054's precedent
# --------------------------------------------------------------------------- #


class TestUnmeasuredIsNotClean:
	"""ADR-0054 built the escape instrument and reported its *baseline* unmeasured rather
	than clean, because a rate needs a deployment. FR-159's baseline needs a codebase
	history the same way, and the failure this class closes is the report that prints
	"no trend" over one unit and is read as "stable"."""

	async def test_a_unit_with_no_recorded_change_is_unmeasured(self, tmp_path: Path) -> None:
		workspace = await a_repository(tmp_path)
		landed = pin_unit("landed", scope="edit", base_commit="HEAD", head_commit="HEAD")
		unlanded = pin_unit("pinned but not built", scope="edit")
		report = await measure_change_costs([landed, unlanded], workspace=workspace)

		row = report.rows[1]
		assert row.measured is False, "no range is not a footprint of zero"
		assert row.footprint is None
		assert row.unmeasured_because is not None
		assert "no commit range" in row.unmeasured_because
		assert [r.unit.id for r in report.unmeasured_rows] == [unlanded.id]

	async def test_no_repository_measures_nothing_rather_than_clean(self, tmp_path: Path) -> None:
		unit = pin_unit("anything", scope="edit", base_commit="a", head_commit="b")
		report = await measure_change_costs([unit], workspace=None)

		assert report.repository is None
		assert report.measured_rows == ()
		assert report.rows[0].measured is False
		assert report.discharged == (), "a reading over nothing claims nothing"

	async def test_one_unit_per_scope_is_unmeasured_and_says_so(self, tmp_path: Path) -> None:
		"""The whole of the ADR-0054 precedent: the instrument exists and the baseline does
		not, and the honest output is the scope's *name* rather than a flat line."""
		workspace = await a_repository(tmp_path)
		base = await head_commit(workspace)
		assert base is not None
		(workspace / "src" / "pkg" / "one.py").write_text("a\nb\nc\nd\n", encoding="utf-8")
		head = await commit(workspace, "one edit")
		unit = pin_unit("the only one", scope="edit", base_commit=base, head_commit=head)
		report = await measure_change_costs([unit], workspace=workspace)

		assert report.measured_rows, "the unit *was* measured"
		assert report.discharged == (), "and no trend was, because one point is not a trend"
		assert report.unmeasured_scopes == ("edit",)
		statement = trend_statement(report)
		assert "no trend to read" in statement
		assert "unmeasured rather than stable" in statement
		assert CHANGE_COST_BASELINE_UNMEASURED in statement

	async def test_an_unreadable_range_is_reported_not_raised(self, tmp_path: Path) -> None:
		"""A repository whose history has been rewritten under a pinned unit is a real
		state, and the honest answer is a row saying so rather than a render that dies."""
		workspace = await a_repository(tmp_path)
		unit = pin_unit("orphaned", scope="edit", base_commit="deadbeef", head_commit="HEAD")
		report = await measure_change_costs([unit], workspace=workspace)

		assert report.rows[0].measured is False
		assert "could not be read" in (report.rows[0].unmeasured_because or "")


# --------------------------------------------------------------------------- #
# the proxy declaration, and the two constants it does not move
# --------------------------------------------------------------------------- #


class TestTheProxyDeclaration:
	"""FR-159: "it is a **proxy** (NFR-024 applies, and it must be declared as one)"."""

	def test_the_report_declares_itself_a_proxy(self) -> None:
		report = ChangeCostReport(id=_uuid(), rendered_at=_now())

		assert CHANGE_COST_PROXY_DECLARATION in report.caveats
		assert CHANGE_COST_NOT_A_VERIFICATION in report.caveats
		assert "PROXY" in CHANGE_COST_PROXY_DECLARATION
		assert "never a verdict" in CHANGE_COST_PROXY_DECLARATION

	def test_the_comparison_rule_is_stated_not_left_to_the_reader(self) -> None:
		"""A trend line pooled over all units is the obvious chart and the wrong
		measurement, so the rule that replaces it is on the report rather than in a
		comment."""
		report = ChangeCostReport(id=_uuid(), rendered_at=_now())

		assert any("comparable" in caveat for caveat in report.caveats)

	def test_the_declaration_is_a_constant_so_no_render_can_phrase_it_away(self) -> None:
		"""A declaration left to each report's author survives until the report that would
		rather not make it, which is the failure ``MAINTAINABILITY_NOT_VERIFIED`` exists to
		close — so it is a module constant and not a field."""
		assert isinstance(CHANGE_COST_PROXY_DECLARATION, str)
		assert isinstance(CHANGE_COST_NOT_A_VERIFICATION, str)
		assert "proxy" not in ChangeCostReport.model_fields
		assert "caveat" not in " ".join(ChangeCostReport.model_fields)

	def test_an_empty_report_claims_nothing(self) -> None:
		report = ChangeCostReport(id=_uuid(), rendered_at=_now())

		assert report.discharged == ()
		assert report.not_implemented == ("FR-159",)
		assert report.trends == {}
		assert report.rising == ()


class TestTheTwoConstantsDoNotMove:
	"""**The test that matters most.** An instrument landing is precisely the event that
	tempts a report to promote its own proxy, and FR-159 says in its own words that it is
	admissible "only as a trend alarm and a Mode M ceiling input, never as a verdict".

	D18's question — whether the ceiling may rise — is answered by a human reading a trend,
	not by this change. So the debt stays 1.0 by construction and the ceiling stays L1, and
	the delivery sentence still begins "Maintainability was not verified"."""

	def test_the_evolvability_debt_is_still_one(self) -> None:
		assert EVOLVABILITY_DEBT == 1.0

	def test_mode_m_is_still_capped_at_l1(self) -> None:
		assert MODE_M_CEILING is AutonomyLevel.L1

	def test_the_delivery_sentence_still_refuses_the_claim(self) -> None:
		assert MAINTAINABILITY_NOT_VERIFIED.startswith("Maintainability was not verified.")
		assert "Mode M is capped at L1" in MAINTAINABILITY_NOT_VERIFIED

	def test_the_sentence_names_the_instrument_without_softening_the_refusal(self) -> None:
		"""The edit this sentence must not be given: an instrument landing is exactly what
		would let "was not verified" soften into "and a trend was measured". The instrument
		is named, its proxy status is named, and the refusal is still the first sentence."""
		assert "FR-159" in MAINTAINABILITY_NOT_VERIFIED
		assert "proxy, not an oracle" in MAINTAINABILITY_NOT_VERIFIED

	def test_the_report_carries_the_measurement_and_reads_nothing_from_it(self) -> None:
		"""FR-159 is a ceiling *input*, and the input is read by a human deciding D18's
		question. The report gains a field; the two numbers the requirement would have to
		move to make it a verdict are the two asserted above, and this asserts the third
		half — that the field exists on the report at all, so a caller can read the trend
		without a second render."""
		assert "change_cost" in DeliveryReport.model_fields
		field = DeliveryReport.model_fields["change_cost"]
		assert field.default is None, (
			"the default is no measurement, which is not an empty measurement"
		)


def _uuid() -> str:
	return uuid7str()


def _now() -> datetime:
	return now()


class TestTheUnitIsPinnedBeforeTheWork:
	"""FR-159: "for a pinned set of change units **held out from the producer**". A unit
	chosen after the diff is a unit chosen by whoever wrote the diff."""

	def test_pinning_records_the_scope_and_the_declared_modules(self) -> None:
		unit = pin_unit(
			"make the ledger hash-chained",
			scope="ledger",
			expected_modules=("ledger", "views"),
			clause_id=_uuid(),
		)

		assert isinstance(unit, ChangeUnit)
		assert unit.scope == "ledger"
		assert unit.expected_modules == ("ledger", "views")
		assert unit.declared_at is not None, "pinned means the moment it was declared"
		assert unit.measured_range is None, "and no range until the work lands"

	def test_a_unit_with_no_scope_is_refused_by_the_type(self) -> None:
		"""A unit with no comparison group is a unit that can never be compared, which is
		the one thing FR-159's instrument needs it to be."""
		from pydantic import ValidationError

		with pytest.raises(ValidationError):
			ChangeUnit(id=_uuid(), statement="orphan", scope="")


# --------------------------------------------------------------------------- #
# the config seam
# --------------------------------------------------------------------------- #


class TestThePinnedSetComesFromAFile:
	"""FR-159's units are "held out from the producer", so the set is a deployment's
	declaration. A factory that discovered the pinned set from a repository's log would be
	choosing the units after seeing the diffs."""

	def test_a_bare_array_of_units_is_accepted(self, tmp_path: Path) -> None:
		path = tmp_path / "units.json"
		path.write_text(
			'[{"statement": "hash-chain the ledger", "scope": "ledger",'
			' "expected_modules": ["ledger", "views"], "base_commit": "abc",'
			' "head_commit": "def"}]'
		)

		units = load_change_units(path)

		assert len(units) == 1
		assert units[0].scope == "ledger"
		assert units[0].expected_modules == ("ledger", "views")
		assert units[0].measured_range == ("abc", "def")

	def test_the_same_array_under_a_key_is_accepted(self, tmp_path: Path) -> None:
		path = tmp_path / "units.json"
		path.write_text('{"change_units": [{"statement": "one", "scope": "ledger"}]}')

		units = load_change_units(path)

		assert units[0].statement == "one"
		assert units[0].measured_range is None, "a unit with no range is pinned, not landed"

	def test_the_identity_and_the_timestamp_are_the_factorys_to_mint(self, tmp_path: Path) -> None:
		"""A file that could set ``declared_at`` could backdate a unit into an earlier
		baseline — the comparison chosen by the thing being compared. So both fields are
		refused by name rather than read or ignored."""
		path = tmp_path / "units.json"
		path.write_text(
			'[{"statement": "one", "scope": "ledger", "declared_at": "2020-01-01T00:00:00Z"}]'
		)

		with pytest.raises(ValueError, match="not a change-unit field"):
			load_change_units(path)

	def test_an_unknown_field_is_refused_not_ignored(self, tmp_path: Path) -> None:
		"""A misspelled ``base_commit`` would otherwise load as a unit with no range, which
		measures as *unmeasured* and reads as work that has not landed."""
		path = tmp_path / "units.json"
		path.write_text('[{"statement": "one", "scope": "ledger", "base_commit_sha": "abc"}]')

		with pytest.raises(ValueError, match="not a change-unit field"):
			load_change_units(path)

	def test_a_unit_with_no_scope_is_refused_by_the_loader(self, tmp_path: Path) -> None:
		path = tmp_path / "units.json"
		path.write_text('[{"statement": "one"}]')

		with pytest.raises(ValueError, match=r"declares no \['scope'\]"):
			load_change_units(path)

	def test_an_empty_set_is_refused(self, tmp_path: Path) -> None:
		"""A file that declares no units would read as configured while measuring nothing."""
		path = tmp_path / "units.json"
		path.write_text("[]")

		with pytest.raises(ValueError, match="no change units"):
			load_change_units(path)

	def test_an_unreadable_file_is_a_message_not_a_traceback(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="cannot read change units"):
			load_change_units(tmp_path / "absent.json")

	def test_the_declared_set_measures_against_a_real_repository(self, tmp_path: Path) -> None:
		"""The seam and the instrument meet: a file's units produce a trend over a real
		diff, which is the only way to know the loader's field names reach the measurement."""
		path = tmp_path / "units.json"
		path.write_text(
			'[{"statement": "first edit", "scope": "pkg", "base_commit": "BASE",'
			' "head_commit": "HEAD"}]'
		)
		units = load_change_units(path)

		async def scenario() -> None:
			workspace = await a_repository(tmp_path)
			base = await head_commit(workspace)
			assert base is not None
			(workspace / "src" / "pkg" / "one.py").write_text("a\nX\nb\nc\n", encoding="utf-8")
			head = await commit(workspace, "one edit")
			landed = units[0].model_copy(update={"base_commit": base, "head_commit": head})

			report = await measure_change_costs([landed], workspace=workspace)

			assert report.measured_rows, "a declared range measured against a real repo"
			assert report.rows[0].footprint is not None
			assert report.rows[0].footprint.lines_added == 1

		asyncio.run(scenario())
