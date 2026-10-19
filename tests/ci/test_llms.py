"""The agent-facing manual, held to the surface it describes.

``llms.txt`` is read by an agent that will act on it: it types the verbs the file names
and reads the state the file describes. That makes two of its claims executable and
therefore checkable — that every command the product registers is in the manual, and that
every command the manual names is one the product registers — and one claim that is not
a claim at all unless a diagram parses.

Both directions are checked, and neither is sufficient alone. A forward-only check lets
a verb be renamed and the manual keep printing the old name; a backward-only check lets
a new command ship undocumented. The pair is the same rule the ADR records for a link
checker that matched one of the two spellings a link is written in.
"""

from __future__ import annotations

import re
from pathlib import Path

from sofact.cli import app as the_app

ROOT = Path(__file__).resolve().parents[2]
LLMS = ROOT / "llms.txt"
README = ROOT / "README.md"

_VERB = re.compile(r"`sofact ([a-z][a-z-]*)`")
"""A command the manual tells an agent to type.

Backticked and prefixed with the literal ``sofact``, because that is the shape the file
uses for a command. A bare word would match prose — the manual says "research" in a
sentence about the phase and means the phase, not the verb.
"""

_MERMAID = re.compile(r"^```mermaid\s*$(.*?)^```\s*$", re.M | re.S)

_KEYWORD = re.compile(
	r"^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram-v2|erDiagram"
	r"|journey|gantt|pie|quadrantChart|requirementDiagram|gitGraph|mindmap|timeline"
	r"|sankey-beta|xychart-beta|block-beta|packet-beta|architecture-beta|C4Context)\b"
)
"""The diagram types GitHub renders.

Enumerated rather than accepting any first word, because the failure this catches is a
misspelling — ``flowchrt``, ``sequenceDigram`` — and a check that accepted any word would
pass on both. A type added to Mermaid and not to this list fails as "unrecognised", which
is the correct direction for a gate to be wrong in: it asks a person to look.
"""


def _registered() -> set[str]:
	"""The commands the CLI registers, read off the object ``--help`` is built from.

	The same source ``test_cli.py`` uses, rather than parsing ``--help`` output: the help
	text is a rendering and a rendering can be reformatted without the surface changing.
	"""
	return {
		command.name or (command.callback.__name__ if command.callback is not None else "")
		for command in the_app.registered_commands
	}


def _documented() -> set[str]:
	"""The commands the manual tells an agent to type."""
	return set(_VERB.findall(LLMS.read_text(encoding="utf-8")))


class TestTheManualNamesTheSurfaceThatExists:
	def test_the_file_exists_and_is_a_manual(self) -> None:
		"""A gate over an absent file passes every assertion about its contents."""
		assert LLMS.exists(), (
			"llms.txt is the agent-facing entry point the README links to; without it the "
			"front page's Documentation table has a dead row"
		)
		text = LLMS.read_text(encoding="utf-8")
		assert text.startswith("# "), "the manual opens with an H1, so an indexer can parse it"
		assert len(text.splitlines()) > 100, (
			f"the manual is {len(text.splitlines())} lines; a file this short is a stub"
		)

	def test_every_command_is_documented(self) -> None:
		"""The forward direction: a command the product registers must be in the manual.

		This is the direction that catches a verb shipped and never written down. The
		command set is read from ``app.registered_commands`` — the object ``--help`` is
		rendered from — so a command added to the app and not to the file fails here
		rather than shipping an agent an incomplete surface.
		"""
		registered, documented = _registered(), _documented()
		assert registered, "no commands registered; the app object or this test moved"
		missing = sorted(registered - documented)
		assert not missing, (
			f"these commands are registered and llms.txt does not name them: {missing}. "
			"An agent reading the manual cannot discover them."
		)

	def test_every_documented_verb_exists(self) -> None:
		"""The reverse direction: a verb the manual names must be a command.

		This is the direction that catches a rename. ``sofact gate approve`` was printed
		to operators in five files and refused by the parser, because every test compared
		the string to a copy of itself; the fix was to invoke the CLI. Here the check is
		the same idea without a subprocess: the manual's verbs are compared to the app's
		own registry, which is what the parser is built from.
		"""
		registered, documented = _registered(), _documented()
		assert documented, "the manual names no command; the extractor or the file moved"
		invented = sorted(documented - registered)
		assert not invented, (
			f"llms.txt tells an agent to type these, and no such command exists: {invented}"
		)

	def test_the_manual_covers_the_four_gates(self) -> None:
		"""The four gates are the one part of the surface an agent must not guess at.

		``PhaseGate``'s values are the names a gate is presented and approved by, and the
		manual is where an agent learns that it cannot pass one. Asserted separately from
		the command sweep because the sweep covers verbs and this covers arguments.
		"""
		from sofact.views import PhaseGate

		text = LLMS.read_text(encoding="utf-8")
		absent = sorted(gate.value for gate in PhaseGate if gate.value not in text)
		assert not absent, f"llms.txt never names these gates: {absent}"


class TestTheReadmeDiagramsParse:
	def test_the_readme_carries_at_least_thirty_two_diagrams(self) -> None:
		"""The count the request asked for, asserted rather than assumed.

		Thirty-two is the floor the operator set. Written as a literal rather than read
		from a constant, so the assertion does not move with the thing it measures.
		"""
		fences = _MERMAID.findall(README.read_text(encoding="utf-8"))
		assert len(fences) >= 32, (
			f"README.md carries {len(fences)} mermaid diagrams; the request asks for at least 32"
		)

	def test_every_mermaid_fence_declares_a_type_github_renders(self) -> None:
		"""A fence tagged ``mermaid`` with an unparseable body renders as an error box.

		The tag is what markdownlint's MD040 wants and says nothing about whether the
		diagram is one — a misspelt keyword passes the linter and fails the reader. This
		reads the first non-comment, non-blank line of every fence, which is where the
		type is declared.
		"""
		bad: list[str] = []
		for number, body in enumerate(_MERMAID.findall(README.read_text(encoding="utf-8")), 1):
			lines = [line.strip() for line in body.splitlines()]
			declared = next((line for line in lines if line and not line.startswith("%%")), "")
			if not _KEYWORD.match(declared):
				bad.append(f"diagram {number}: {declared[:60]!r}")
		assert not bad, (
			"these mermaid fences do not declare a diagram type GitHub renders:\n  "
			+ "\n  ".join(bad)
		)
