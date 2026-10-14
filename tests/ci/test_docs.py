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

from sofact.views import Phase, PhaseGate

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
