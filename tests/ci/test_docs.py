"""The prose in this repository, held to the claims it makes about itself.

Two documents here are load-bearing in a way a reader cannot check by reading them.
``README.md`` is the front door, and ``docs/phases.md`` is where the long-form phase
arguments live; the README says a test keeps them in step, so this is that test. A
claim in a document about a *test* is the one kind of documentation claim that can be
made false silently — the test is deleted, the sentence stays, and nothing fails.

The check is deliberately narrow. It does not diff the two files, because they are
different lengths by design and a diff would be a gate that can never pass — the
failure mode the ADRs warn about. It asserts the one thing the README promises: that
each phase named in the front-page table is a phase the reference also describes, and
that the reference's rows are phases the enum actually has.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import COLLECTED

from sofact.views import ElicitationDimension, Phase, PhaseGate

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
PHASES = ROOT / "docs" / "phases.md"

_ROW = re.compile(r"^\|\s*\*\*(P[A-Za-z0-9]*)\b", re.M)

_SUITE_COUNT = re.compile(r"^uv run pytest -vxs tests/ci\s+#\s*(\d+) tests$", re.M)
"""The README's own line for running the suite, and the figure it states.

Anchored to the whole line rather than searching for a bare number, because a four-digit
figure appears all over a README and a check that matched any of them would pass on the
wrong one — and would then be a gate about nothing in particular.
"""
"""A phase code in the row shape both documents use.

The pattern is ``P[A-Za-z0-9]*`` rather than ``P\\d`` deliberately. Written as ``P\\d``
it matched only well-formed codes, so ``PX`` — the exact shape a typo takes — was never
captured and the membership check below could not see it. A canary that renamed a row to
``PX`` passed, which is the subset rule: a predicate that matches less than the thing it
tests fails open, and it fails toward "clean". ``P10`` is caught by the same widening,
since ``\\b`` does not fall between two word characters."""


def _phase_codes(text: str) -> set[str]:
	"""The phase codes a document's table names, in the ``| **P3 …`` row shape."""
	return set(_ROW.findall(text))


class TestThePhaseReferenceMatchesTheFrontPage:
	def test_the_reference_describes_every_phase_the_front_page_lists(self) -> None:
		"""The README's promise, verbatim: the reference is the long form of its table."""
		listed = _phase_codes(README.read_text(encoding="utf-8"))
		described = _phase_codes(PHASES.read_text(encoding="utf-8"))

		assert listed, "the README no longer lists phases in the documented row shape"
		assert listed <= described, f"README lists phases the reference omits: {listed - described}"

	def test_both_tables_name_phases_the_enum_has(self) -> None:
		"""A row for a phase the code does not have is a document describing a different
		program. ``P4`` is absent from the reference's own rows on purpose — it shares a
		row with P2 — so this checks membership, not exhaustiveness."""
		known = {phase.value for phase in Phase}
		for path in (README, PHASES):
			unknown = _phase_codes(path.read_text(encoding="utf-8")) - known
			assert not unknown, f"{path.name} names phases that do not exist: {sorted(unknown)}"

	def test_every_gate_the_code_has_is_named_in_the_readme(self) -> None:
		"""The README's pipeline table marks gates. §3.3 makes them the product's central
		claim, so a gate that exists in the enum and nowhere in the front page is a
		capability a reader cannot find."""
		text = README.read_text(encoding="utf-8").lower()
		for gate in PhaseGate:
			assert gate.value.replace("_", " ") in text or gate.value in text, gate.value


# --------------------------------------------------------------------------- #
# the suite's size, which the README states and nothing checked
# --------------------------------------------------------------------------- #


class TestTheSuiteCountIsTheOneThatRan:
	"""The README publishes a test count, and it had drifted 1282 to 1394 unnoticed.

	An unguarded figure in a living document is a figure that is eventually wrong, and
	this one is read by exactly the person deciding whether to trust the project. The
	count asserted is pytest's own, not one derived from the tree: an inventory read from
	the source is not an inventory of what runs.
	"""

	def test_the_readme_states_a_count_at_all(self) -> None:
		assert _SUITE_COUNT.search(README.read_text(encoding="utf-8")), (
			"README.md no longer states the suite's size on the command line that runs it"
		)

	def test_the_stated_count_is_the_one_this_run_collected(self) -> None:
		"""Skipped on a filtered run, and the skip is the point.

		``-k``/``-m`` make the collected count differ from the run's, so a gate asserting
		on it would fail for a reason its operator cannot act on — the way a check teaches
		people to bypass it. A filtered run is not a run that measured this.
		"""
		assert COLLECTED.get("all"), "conftest did not record what was collected"
		if not COLLECTED.get("whole_suite"):
			pytest.skip("only an unfiltered run over tests/ci measures the suite's size")

		match = _SUITE_COUNT.search(README.read_text(encoding="utf-8"))
		assert match is not None, "the count line is absent; the sibling test reports that"
		stated = int(match.group(1))
		assert stated == COLLECTED["all"], (
			f"README.md says {stated} tests and this run collected {COLLECTED['all']}. "
			"The count is the suite's size, so update the line when the suite changes."
		)


# --------------------------------------------------------------------------- #
# the roadmap tally, which claims to be derived from the rows and was not
# --------------------------------------------------------------------------- #

ROADMAP = ROOT / "docs" / "research" / "roadmap-gap" / "README.md"

_ROADMAP_TALLY = re.compile(
	r"^\| (Implemented|Partly|Deferred \(ADR-0024\)|Not built) \| (\d+) \|$", re.M
)
_TALLY_TOTAL = re.compile(r"^\| \*\*Total rows\*\* \| \*\*(\d+)\*\* \|$", re.M)
_STAMP = re.compile(r"\((?:19|20)\d\d-\d\d-\d\d[^)]*\)")

_HALF_IN_VERDICT = re.compile(
	r"\bhalf\b[^.]*\b(not built|not read|is not|is unchanged|absent)|"
	r"\b(not built|not read)\b|still open",
	re.I,
)
"""A verdict cell that leads "Implemented" and then names a half that is missing.

Deliberately not a phrase list: ``where a boundary holds`` and ``as a P7 check`` are
conditions and scope notes, not missing halves, and a rule that matched either would
count two rows Partly that every published table counts Implemented. The disjunction
above is the one that reproduces all four committed tables.
"""


def _roadmap_rows(text: str) -> list[tuple[str, str, str]]:
	"""Every ``| FR-… | verdict | evidence |`` row, as (number, verdict, evidence).

	Split on the pipe rather than matched with a regex, because an evidence cell
	contains ``|`` characters and a non-greedy pattern stops at the first one — which
	reads 77 rows where the table has 119, and does it silently.
	"""
	rows: list[tuple[str, str, str]] = []
	for line in text.splitlines():
		if not line.startswith("| FR-"):
			continue
		cells = [cell.strip() for cell in line.split("|")[1:-1]]
		if len(cells) >= 3:
			rows.append((cells[0], cells[1], cells[2]))
	return rows


def _classify(verdict: str, evidence: str) -> str:
	"""The document's counting rule, as the two disjuncts it actually is.

	The rule was *stated* as one disjunct — a verdict cell that names an unbuilt half —
	and *implemented* as two, and the gap is where FR-124 lived: its half sat in its
	evidence cell under a ``**Still open**`` marker while its verdict cell read bare
	``**Implemented**``. Re-running this function over every committed revision
	reproduces the table each refresh published (``91/22/0/6`` at ADR-0060 through
	``91/26/0/2`` at ADR-0063); the one-disjunct version reads all four one Implemented
	too high. That is why the docstring in the document now states both.
	"""
	bare = re.sub(r"[*_`]", "", verdict)
	lead = bare.split()[0].rstrip(",;") if bare.split() else ""
	if lead == "Partly":
		return "Partly"
	if lead == "Not":
		return "Not built"
	if lead in ("Implemented", "Deferred"):
		tail = _STAMP.sub("", bare[len(lead) :])
		if _HALF_IN_VERDICT.search(tail) or "**Still open**" in evidence:
			return "Partly"
		return "Implemented"
	return f"UNCLASSIFIED:{bare[:40]}"


class TestTheRoadmapTallyIsDerivedFromItsRows:
	"""The gap file publishes a tally and says it was read off the rows by a script.

	Nothing checked that, and the number had drifted: the file's own prose records a
	refresh that found nine rows closed without the count moving, and a later one where
	the prose line and the table disagreed by two rows on the same tree. A count that
	is asserted against itself is not derived from anything, so this reads the rows.
	"""

	def test_the_table_totals_the_rows_it_claims_to_count(self) -> None:
		text = ROADMAP.read_text(encoding="utf-8")
		rows = _roadmap_rows(text)
		assert rows, "the roadmap table no longer has rows in the documented shape"

		stated = dict(_ROADMAP_TALLY.findall(text))
		assert stated, "the roadmap tally table is absent or reshaped"

		counted: dict[str, int] = {"Implemented": 0, "Partly": 0, "Not built": 0}
		for _number, verdict, evidence in rows:
			verdict_class = _classify(verdict, evidence)
			assert not verdict_class.startswith("UNCLASSIFIED"), (
				f"{_number}'s verdict cell leads with {verdict_class!r}, which the counting "
				"rule does not recognise. Add the shape to the rule or fix the cell."
			)
			counted[verdict_class] += 1

		total = _TALLY_TOTAL.search(text)
		assert total is not None, "the tally no longer states its row total"
		assert int(total.group(1)) == len(rows), (
			f"the tally says {total.group(1)} rows and the table has {len(rows)}"
		)

		for label, key in (
			("Implemented", "Implemented"),
			("Partly", "Partly"),
			("Not built", "Not built"),
		):
			assert int(stated[label]) == counted[key], (
				f"the roadmap tally says {label}={stated[label]} and its own rows count "
				f"{counted[key]}. The number is read off the rows, so update the table "
				"when a row's verdict moves."
			)

	def test_every_verdict_cell_leads_with_a_word_the_rule_knows(self) -> None:
		"""A cell whose leading word is none of the three is a row nothing can count.

		Separate from the tally so a reshaped cell reports itself rather than surfacing
		as an arithmetic difference an operator would chase in the wrong place.
		"""
		known = {"Implemented", "Partly", "Not built", "Deferred"}
		for number, verdict, _ in _roadmap_rows(ROADMAP.read_text(encoding="utf-8")):
			bare = re.sub(r"[*_`]", "", verdict)
			lead = bare.split()[0].rstrip(",;") if bare.split() else ""
			assert lead in known, (
				f"{number}'s verdict cell leads with {lead!r}, which is not one of {sorted(known)}"
			)


ADR_DIR = ROOT / "docs" / "adr"
ADR_INDEX = ADR_DIR / "README.md"

_ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
_ADR_ROW = re.compile(r"^\| \[(\d{4})\]\((\d{4}-[a-z0-9-]+\.md)\)")
_NON_RESOLUTION_COUNT = re.compile(
	r"^Not every decision resolves a `D`\. ([A-Za-z]+(?:-[a-z]+)?) records here", re.M
)
_WORDS = {
	"Twenty": 20,
	"Thirty": 30,
	"Forty": 40,
	"Fifty": 50,
	"Sixty": 60,
	"Seventy": 70,
	"Eighty": 80,
	"Ninety": 90,
}
_UNITS = {
	"one": 1,
	"two": 2,
	"three": 3,
	"four": 4,
	"five": 5,
	"six": 6,
	"seven": 7,
	"eight": 8,
	"nine": 9,
}
"""The number words the sentence uses, so the count is read rather than pattern-matched.

A regex for a run of digits would not match the prose as written, and rewriting the
sentence into digits to make it matchable would be changing the document to suit the
check.
"""


def _word_value(word: str) -> int:
	"""``"Fifty-two"`` → 52, ``"Forty"`` → 40. Hyphenated tens and units only."""
	head, _, tail = word.partition("-")
	value = _WORDS.get(head)
	assert value is not None, f"{word!r} is not a number word this check can read"
	if not tail:
		return value
	assert tail in _UNITS, f"{word!r} has a unit this check cannot read"
	return value + _UNITS[tail]


def _adr_index_rows(text: str) -> list[tuple[str, str]]:
	"""``(number, filename)`` for every row of the ADR **index** table.

	Scoped to the ``## Index`` section, because the file carries a **second** table of
	ADR rows further down (the records that resolve no open decision). A scan over the
	whole file reads both and reports 124 rows for 72 records, and the repeats would make
	the uniqueness check fail on a document that is correct. The index is the table that
	is meant to be the complete set, so it is the one read.
	"""
	head = text.index("\n## Index")
	tail = text.index("\n## ", head + 1)
	rows: list[tuple[str, str]] = []
	for line in text[head:tail].splitlines():
		match = _ADR_ROW.match(line)
		if match is not None:
			rows.append((match.group(1), match.group(2)))
	return rows


class TestTheAdrIndexIsTheSetOfRecords:
	"""The ADR index lists every record and the prose count is the one that ran.

	The count in ``docs/adr/README.md`` had drifted: the prose said forty-nine records
	while the table it introduces had fifty-one, because two rows were added without the
	sentence moving. Nothing failed, and the sentence is where a reader takes the size of
	the decision log from. The roadmap file had the same defect and ADR-0065 fixed it
	there; this is the same rule one document over.

	The index and the directory are checked against each other in both directions,
	because either alone is satisfied by a different mistake: a file with no row is a
	decision nobody can find, and a row with no file is a link that 404s.
	"""

	def test_every_record_has_a_row_and_every_row_has_a_record(self) -> None:
		on_disk = {name for name in (p.name for p in ADR_DIR.iterdir()) if _ADR_FILE.match(name)}
		assert on_disk, "no ADR files found; the directory or the naming convention moved"

		rows = _adr_index_rows(ADR_INDEX.read_text(encoding="utf-8"))
		assert rows, "the ADR index has no rows in the documented shape"
		listed = {name for _number, name in rows}

		missing = sorted(on_disk - listed)
		assert not missing, (
			f"{missing} exist in docs/adr/ and no index row names them, so a decision "
			"recorded here cannot be found by reading the index"
		)
		dangling = sorted(listed - on_disk)
		assert not dangling, f"the index names {dangling}, which no file in docs/adr/ provides"

		numbers = [number for number, _ in rows]
		assert len(set(numbers)) == len(numbers), f"the index lists a number twice: {numbers}"

	def test_the_stated_count_of_non_resolution_records_is_the_table(self) -> None:
		text = ADR_INDEX.read_text(encoding="utf-8")
		stated = _NON_RESOLUTION_COUNT.search(text)
		assert stated is not None, (
			"the sentence introducing the non-resolution table no longer states a count, "
			"so nothing can be checked against the table it introduces"
		)
		expected = _word_value(stated.group(1))

		head = text.index(stated.group(0))
		rows = [line for line in text[head:].splitlines() if line.startswith("| [00")]
		assert rows, "the non-resolution table is absent or reshaped"
		assert expected == len(rows), (
			f"the sentence says {expected} non-resolution records and the table beneath it "
			f"has {len(rows)}. The number is read off the table, so move it when a row is added."
		)


# --------------------------------------------------------------------------- #
# the elicitation table, which the code must answer to and never did
# --------------------------------------------------------------------------- #

SPEC = ROOT / "docs" / "spec" / "product-spec.md"

_SPEC_DIMENSION_ROW = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|", re.M)


def _spec_dimension_rows(text: str) -> list[str]:
	"""The FR-064 table's dimension names, read from the section that holds it.

	Scoped to FR-064's own block rather than the whole document, because ``**Goal**``
	and ``**Failure**`` are words this spec uses as row labels in several tables and a
	document-wide match would collect a different table's rows and call the result the
	elicitation dimensions.
	"""
	start = text.index("**FR-064**")
	end = text.index("**FR-065**", start)
	block = text[start:end]
	names = _SPEC_DIMENSION_ROW.findall(block)
	return [name for name in names if name != "Dimension"]


class TestTheElicitationTableIsBoundToTheEnum:
	"""FR-064's table is the authority, and nothing compared it to the code.

	ADR-0077's own finding: *Scale* and *Non-negotiables* were absent from
	``ElicitationDimension`` for as long as both existed, with no record of the drop,
	because no test read the table. A reader was the only mechanism, and a reader who
	does not know the table exists cannot be one. The enum's docstring now says the
	counts differ on purpose; this test is what makes that claim checkable rather than
	a sentence beside a list.
	"""

	def test_the_table_is_readable_and_names_the_specs_own_rows(self) -> None:
		"""Canary the reader against the table it claims to read.

		Every assertion below is vacuous if the extraction returns nothing or returns
		the wrong table, so the known-positive is asserted first: this table has seven
		rows and these seven names, and a reader that returns a different set is the
		finding rather than a reason to loosen the test beneath it.
		"""
		rows = _spec_dimension_rows(SPEC.read_text(encoding="utf-8"))
		assert rows == [
			"Goal",
			"Success",
			"Scope boundary",
			"Scale",
			"Constraints",
			"Non-negotiables",
			"Failure",
		], f"the FR-064 table is not the one this test reads: {rows}"

	def test_every_row_of_the_table_is_a_dimension_the_code_asks(self) -> None:
		"""The property ADR-0077 restores, asserted against the table rather than a list.

		The mapping is a **table** and not an identity, and it has to be, because the
		two lists are not the same list: ``Success`` is two dimensions here (``OUTCOME``
		and ``CONSUMER``, the observer being what an oracle is written against) and the
		table has no *Oracle* row at all. Naming the mapping is the honest form — a
		substring match on the member name would report *Scope boundary* as unasked and
		a fuzzy match would pass on any row, which is the failure this test exists to
		prevent. What it pins is the direction that was broken: a row the spec asks for
		and the code does not ask.
		"""
		asked = {
			"Goal": {ElicitationDimension.OUTCOME},
			"Success": {ElicitationDimension.OUTCOME, ElicitationDimension.CONSUMER},
			"Scope boundary": {ElicitationDimension.BOUNDARY},
			"Scale": {ElicitationDimension.SCALE},
			"Constraints": {ElicitationDimension.CONSTRAINT},
			"Non-negotiables": {ElicitationDimension.NON_NEGOTIABLES},
			"Failure": {ElicitationDimension.FAILURE},
		}
		rows = _spec_dimension_rows(SPEC.read_text(encoding="utf-8"))

		unmapped = sorted(set(rows) - set(asked))
		assert not unmapped, (
			f"the FR-064 table names {unmapped}, which this test does not map to a "
			"dimension. A row added to the table is a question P0 must ask, so map it "
			"to the member that asks it — or to the member that already does."
		)
		for row in rows:
			for dimension in asked[row]:
				assert dimension in set(ElicitationDimension), (
					f"the table's {row!r} row maps to {dimension}, which is not a member"
				)

	def test_every_dimension_is_either_a_table_row_or_declared_as_extra(self) -> None:
		"""The other direction, so the mapping cannot go stale by the enum growing.

		``ORACLE`` is the member with no row, and it is deliberate: FR-067's
		``verification_method`` is a question P0 asks and the table does not list, which
		the enum's docstring states. Pinning it here as a named exception rather than
		allowing any unmapped member is the difference between a decision and a drift —
		a member added tomorrow and left out of the table fails this, and whoever adds
		it has to say which it is.
		"""
		covered = {
			ElicitationDimension.OUTCOME,
			ElicitationDimension.CONSUMER,
			ElicitationDimension.BOUNDARY,
			ElicitationDimension.SCALE,
			ElicitationDimension.CONSTRAINT,
			ElicitationDimension.NON_NEGOTIABLES,
			ElicitationDimension.FAILURE,
		}
		no_row = {ElicitationDimension.ORACLE}
		assert covered | no_row == set(ElicitationDimension), (
			"a dimension is neither mapped to an FR-064 row nor named here as one the "
			f"table does not list: {sorted(set(ElicitationDimension) - covered - no_row)}"
		)
