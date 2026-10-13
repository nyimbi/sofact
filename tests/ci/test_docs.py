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

from sofact.views import Phase, PhaseGate

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
PHASES = ROOT / "docs" / "phases.md"

_ROW = re.compile(r"^\|\s*\*\*(P[A-Za-z0-9]*)\b", re.M)
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
