# 0003 — The ledger is append-only and hash-chained

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

SoFact draws conclusions (verdicts) from observations (evidence) produced by a
different party (the harness, or an operator's command). For such a conclusion to
mean anything later, the reader must be able to establish two things after the fact:
that the observations have not been altered, and that the conclusion was drawn
against *this* set of clauses rather than a more convenient one.

A mutable state store gives neither. A row can be updated; a contract can be
regenerated with weaker clauses and re-verified; and nothing in the resulting
database records that either happened.

## Decision

The event log is **append-only JSONL**, one event per line, each entry carrying a
SHA-256 `entry_hash` computed over

```text
(index, at, kind, payload, prev_hash)
```

The first entry's `prev_hash` is `GENESIS_HASH` (`"0" * 64`). Because `entry_hash`
covers `prev_hash`, altering any entry invalidates every entry after it and
`verify_chain` reports the position of the break.

All current state is a **pure fold** of the log (`state.fold(entries) -> ProjectState`).
Nothing else may assemble state. An unknown event kind raises rather than being
skipped, so a log written by a newer SoFact fails loudly instead of folding to stale
state that looks current.

## Evidence

`tests/ci/test_ledger.py` covers chaining, four tamper modes, and malformed input:

- editing a payload in place → detected;
- rewriting an entry **and** recomputing its own hash (a self-consistent forgery) →
  detected via the successor's `prev_hash`, which is the case a naive
  "hash the entry" design misses;
- reordering entries → detected;
- appending to a broken chain → refused;
- non-JSON lines → reported, not ignored.

## Consequences

- The log is **tamper-evident, not tamper-proof**. Anyone with write access can
  rewrite the whole file and recompute every hash. Detecting that requires an anchor
  outside the file (a signed head, an external notary), which is out of scope for v1
  and is recorded here so the gap is not mistaken for a guarantee.
- Cost is disk, and the log grows monotonically. Acceptable: events are small and the
  delivery envelope is bounded (spec §1.3).
- Verification can cite the exact clause set it judged: `VerificationReport` carries
  `contract_hash`, so a verdict cannot be detached from its contract (FR-139).
- The log is the *record*, and the verdict is about the *artefact*. These are two
  different judgements — `verify_ledger` and `verify_contract` — and conflating them
  would let a tampered log read as a passing build.
