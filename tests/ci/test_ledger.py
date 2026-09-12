"""Ledger integrity.

The chain is the only reason derived state can be trusted, so these tests attack it
rather than merely exercising it: edit an entry, reorder entries, break the JSON.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from sofact.ledger import Ledger, LedgerCorruptError
from sofact.views import GENESIS_HASH, LedgerEntry, LedgerKind


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
	return Ledger(tmp_path / "ledger.jsonl")


def _append_three(ledger: Ledger) -> None:
	ledger.append(LedgerKind.GOAL_CREATED, {"goal": {"n": 1}})
	ledger.append(LedgerKind.ANSWER_RECORDED, {"answer": {"n": 2}})
	ledger.append(LedgerKind.ADVISOR_NOTE, {"text": "note"})
	assert len(ledger) == 3


class TestEmptyLedger:
	def test_missing_file_reads_as_empty(self, ledger: Ledger) -> None:
		assert len(ledger) == 0
		assert ledger.entries() == ()

	def test_genesis_hash_when_empty(self, ledger: Ledger) -> None:
		assert ledger.last_hash() == GENESIS_HASH

	def test_empty_chain_verifies(self, ledger: Ledger) -> None:
		status = ledger.verify_chain()
		assert status.ok
		assert status.length == 0


class TestChaining:
	def test_first_entry_chains_onto_genesis(self, ledger: Ledger) -> None:
		entry = ledger.append(LedgerKind.GOAL_CREATED, {"goal": {"n": 1}})
		assert entry.index == 0
		assert entry.prev_hash == GENESIS_HASH

	def test_each_entry_chains_onto_its_predecessor(self, ledger: Ledger) -> None:
		_append_three(ledger)
		entries = ledger.entries()
		pairs = list(pairwise(entries))
		assert len(pairs) == 2
		assert all(later.prev_hash == earlier.entry_hash for earlier, later in pairs)
		assert ledger.last_hash() == entries[-1].entry_hash

	def test_chain_verifies_after_appends(self, ledger: Ledger) -> None:
		_append_three(ledger)
		status = ledger.verify_chain()
		assert status.ok
		assert status.length == 3

	def test_entries_survive_a_reread(self, ledger: Ledger) -> None:
		"""Hashes must not depend on in-memory state, or a restart would look like tampering."""
		_append_three(ledger)
		before = [e.entry_hash for e in ledger.entries()]
		ledger.invalidate()
		assert [e.entry_hash for e in ledger.entries()] == before
		assert ledger.verify_chain().ok

	def test_ledger_must_be_jsonl(self, tmp_path: Path) -> None:
		with pytest.raises(AssertionError, match="jsonl"):
			Ledger(tmp_path / "ledger.json")


class TestTamperDetection:
	def _rewrite(
		self, ledger: Ledger, index: int, payload: dict[str, Any], *, fix_hash: bool
	) -> None:
		"""Rewrite one entry on disk, optionally making it self-consistent again.

		``fix_hash=False`` models a careless edit: the payload changes and the recorded
		hash does not. ``fix_hash=True`` models a *deliberate* one: the attacker
		recomputes the entry's own hash so it self-verifies. The second case is the one
		that matters, because it is only detectable through the successor's
		``prev_hash``.
		"""
		lines = ledger.path.read_text(encoding="utf-8").splitlines()
		entry = LedgerEntry.model_validate_json(lines[index])
		mutated = entry.model_copy(update={"payload": payload})
		if fix_hash:
			mutated = mutated.model_copy(update={"entry_hash": mutated.computed_hash()})
		lines[index] = mutated.model_dump_json()
		ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
		ledger.invalidate()

	def test_editing_a_payload_is_detected(self, ledger: Ledger) -> None:
		_append_three(ledger)
		self._rewrite(ledger, 1, {"answer": {"n": 999}}, fix_hash=False)
		status = ledger.verify_chain()
		assert not status.ok
		assert status.broken_at == 1
		assert "entry_hash mismatch" in (status.reason or "")

	def test_editing_the_first_entry_breaks_the_whole_chain(self, ledger: Ledger) -> None:
		"""Because each hash covers the previous, one edit invalidates the tail."""
		_append_three(ledger)
		self._rewrite(ledger, 0, {"goal": {"n": 0}}, fix_hash=False)
		status = ledger.verify_chain()
		assert not status.ok
		assert status.broken_at == 0

	def test_a_self_consistent_forgery_is_still_detected(self, ledger: Ledger) -> None:
		"""An attacker who recomputes entry 1's own hash cannot recompute entry 2's
		``prev_hash`` without rewriting the entire tail."""
		_append_three(ledger)
		self._rewrite(ledger, 1, {"answer": {"n": 999}}, fix_hash=True)
		status = ledger.verify_chain()
		assert not status.ok
		assert status.broken_at == 2
		assert "prev_hash" in (status.reason or "")

	def test_the_forged_entry_itself_verifies(self, ledger: Ledger) -> None:
		"""Confirms the previous test is measuring the right thing: entry 1 is
		self-consistent, so only the chain link can catch it."""
		_append_three(ledger)
		self._rewrite(ledger, 1, {"answer": {"n": 999}}, fix_hash=True)
		entry = ledger.entries()[1]
		assert entry.computed_hash() == entry.entry_hash

	def test_reordering_entries_is_detected(self, ledger: Ledger) -> None:
		_append_three(ledger)
		lines = ledger.path.read_text(encoding="utf-8").splitlines()
		lines[0], lines[1] = lines[1], lines[0]
		ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
		ledger.invalidate()
		status = ledger.verify_chain()
		assert not status.ok
		assert status.broken_at == 0

	def test_appending_to_a_broken_chain_is_refused(self, ledger: Ledger) -> None:
		"""Continuing would mean producing verdicts over possibly-edited history."""
		_append_three(ledger)
		self._rewrite(ledger, 1, {"answer": {"n": 999}}, fix_hash=False)
		with pytest.raises(LedgerCorruptError, match="chain broken"):
			ledger.append(LedgerKind.ADVISOR_NOTE, {"text": "after"})

	def test_require_intact_raises_with_the_position(self, ledger: Ledger) -> None:
		_append_three(ledger)
		self._rewrite(ledger, 2, {"payload": {"text": "changed"}}, fix_hash=False)
		with pytest.raises(LedgerCorruptError, match="broken at 2"):
			ledger.require_intact()


class TestMalformedLog:
	def test_a_line_that_is_not_an_entry_is_rejected(self, tmp_path: Path) -> None:
		path = tmp_path / "ledger.jsonl"
		path.write_text('{"not": "a ledger entry"}\n', encoding="utf-8")
		with pytest.raises(LedgerCorruptError, match="is not a ledger entry"):
			Ledger(path).entries()

	def test_a_non_json_line_is_rejected(self, tmp_path: Path) -> None:
		path = tmp_path / "ledger.jsonl"
		path.write_text("this is not json\n", encoding="utf-8")
		with pytest.raises(LedgerCorruptError):
			Ledger(path).entries()

	def test_blank_lines_are_ignored(self, tmp_path: Path) -> None:
		path = tmp_path / "ledger.jsonl"
		ledger = Ledger(path)
		ledger.append(LedgerKind.GOAL_CREATED, {"goal": {"n": 1}})
		path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
		ledger.invalidate()
		assert len(ledger) == 1
		assert ledger.verify_chain().ok
