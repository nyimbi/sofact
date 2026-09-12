"""UUID7 string identifiers.

UUID7 is time-ordered: the high bits are a millisecond timestamp, so lexicographic
sort order matches creation order. That property is why the ledger can be keyed by
id and still replay in causal order, and why ids are stored as strings rather than
``uuid.UUID`` objects — every boundary in this system is JSON.

Shimmed here so the dependency is declared once (parent convention).
"""

from __future__ import annotations

from uuid6 import uuid7

__all__ = ["uuid7str"]


def uuid7str() -> str:
	"""Return a new UUID7 as a lowercase hyphenated string."""
	value = str(uuid7())
	assert len(value) == 36, f"uuid7 produced an unexpected string: {value!r}"
	assert value[14] == "7", f"uuid7 produced a non-v7 identifier: {value!r}"
	return value
