"""The append-only, hash-chained event log.

This is the only thing in SoFact that is written to. Goals, answers, drafts and
contracts are all *derived* by folding the log (see :mod:`sofact.state`), which buys
three properties a mutable store would not:

* **replay** — any past state can be reconstructed exactly;
* **tamper evidence** — every entry's hash covers its predecessor's, so editing
  history invalidates the tail;
* **an audit trail that is the artefact**, not a description of it.

Deliberately synchronous. The work is one ``write`` of one short line; there is no
real await point, and pretending otherwise would only hide the fact that appends are
serialised anyway.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sofact.views import (
	GENESIS_HASH,
	ChainStatus,
	LedgerEntry,
	LedgerKind,
)

__all__ = ["Ledger", "LedgerCorruptError"]

LEDGER_FILENAME = "ledger.jsonl"


class LedgerCorruptError(RuntimeError):
	"""Raised when the log cannot be trusted and work must stop.

	A corrupt chain is not a warning. Continuing would mean producing verdicts over
	history that may have been edited, which is precisely what the chain exists to
	prevent.
	"""


class Ledger:
	"""A JSONL file where each line is one hash-chained :class:`LedgerEntry`."""

	def __init__(self, path: Path) -> None:
		assert path.suffix == ".jsonl", f"ledger must be a .jsonl file, got {path.name!r}"
		self.path = path
		self._cache: tuple[LedgerEntry, ...] | None = None

	def __repr__(self) -> str:
		return f"Ledger({self.path}, entries={len(self.entries())})"

	# ------------------------------------------------------------------ read

	def entries(self) -> tuple[LedgerEntry, ...]:
		"""All entries, oldest first. Missing file reads as an empty log."""
		if self._cache is not None:
			return self._cache
		if not self.path.exists():
			self._cache = ()
			return self._cache
		parsed: list[LedgerEntry] = []
		for lineno, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
			if not line.strip():
				continue
			try:
				parsed.append(LedgerEntry.model_validate_json(line))
			except ValueError as exc:
				raise LedgerCorruptError(
					f"{self.path}:{lineno} is not a ledger entry: {exc}"
				) from exc
		self._cache = tuple(parsed)
		return self._cache

	def __len__(self) -> int:
		return len(self.entries())

	def last_hash(self) -> str:
		"""Hash to chain the next entry onto; the genesis sentinel when empty."""
		entries = self.entries()
		return entries[-1].entry_hash if entries else GENESIS_HASH

	def verify_chain(self) -> ChainStatus:
		"""Recompute every hash and check every link.

		Checks three things per entry: the recorded hash matches the recomputed one,
		the index is the expected position, and ``prev_hash`` is the predecessor's
		hash. Any divergence names the first bad index and stops.
		"""
		entries = self.entries()
		prev = GENESIS_HASH
		for position, entry in enumerate(entries):
			if entry.index != position:
				return ChainStatus(
					ok=False,
					length=len(entries),
					broken_at=position,
					reason=f"index {entry.index} at position {position}",
				)
			if entry.prev_hash != prev:
				return ChainStatus(
					ok=False,
					length=len(entries),
					broken_at=position,
					reason=f"prev_hash {entry.prev_hash[:12]}… does not match predecessor {prev[:12]}…",
				)
			recomputed = entry.computed_hash()
			if recomputed != entry.entry_hash:
				return ChainStatus(
					ok=False,
					length=len(entries),
					broken_at=position,
					reason=f"entry_hash mismatch (recorded {entry.entry_hash[:12]}…)",
				)
			prev = entry.entry_hash
		return ChainStatus(ok=True, length=len(entries))

	def require_intact(self) -> None:
		"""Raise unless the chain verifies. Call before trusting derived state."""
		status = self.verify_chain()
		if not status.ok:
			raise LedgerCorruptError(f"ledger chain broken at {status.broken_at}: {status.reason}")

	# ----------------------------------------------------------------- write

	def append(self, kind: LedgerKind, payload: dict[str, Any]) -> LedgerEntry:
		"""Append one event and return it.

		The new entry is chained onto the current tail, so an out-of-band edit
		elsewhere in the file is detected by :meth:`verify_chain` rather than silently
		absorbed.
		"""
		assert isinstance(kind, LedgerKind), f"kind must be a LedgerKind, got {type(kind)}"
		self.require_intact()
		entries = self.entries()
		entry = LedgerEntry.create(
			index=len(entries),
			kind=kind,
			payload=payload,
			prev_hash=self.last_hash(),
		)
		self.path.parent.mkdir(parents=True, exist_ok=True)
		with self.path.open("a", encoding="utf-8") as handle:
			handle.write(json.dumps(entry.model_dump(mode="json"), separators=(",", ":")) + "\n")
			handle.flush()
		self._cache = (*entries, entry)
		assert self._cache[-1].entry_hash == entry.entry_hash, "append did not reach the cache tail"
		return entry

	def invalidate(self) -> None:
		"""Drop the read cache, forcing a re-read from disk.

		Only needed when something outside this process may have written to the file,
		which tests exercise deliberately.
		"""
		self._cache = None
