# 0050 — Coverage is a conjunction, and the debt and the cap are one measure

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-108, FR-109, FR-103, FR-104, FR-105, FR-007;
  [ADR-0009](0009-no-oracle-no-autonomy.md),
  [ADR-0041](0041-a-mode-g-delivery-is-l2-and-the-modules-are-reported-separately.md)

## Context

FR-108 defines ground-truth debt as intent clauses "not covered by a **rank-1–5**
oracle". FR-109 caps a module with such a clause at L2. Two things followed the same
word — *covered* — and each tested one half of it.

`Contract.ceiling` read the **rank** alone. `ground_truth_debt` read **executability**
alone (`command_hint is not None`). Measured on the build before this ADR:

| Contract | debt | rank | ceiling |
| --- | --- | --- | --- |
| every clause a rank-1 property, **no command** | 1.0 | 1 | **L4** |
| every clause a rank-6 example, **with a command** | 0.0 | 6 | L2 |

Both rows are §2.3's failure stated as a number. The first grants the strongest
autonomy the ladder offers to a contract **nothing can run** — a rank is a claim about
how a clause *would* be checked, and an oracle naming no command makes the claim
unobservable, because nothing distinguishes a property test that exists from one typed
into a field. The second reports **zero debt** on a contract FR-103's own table calls
"sample, not coverage": a rank-6 example names a command, so the executability measure
counted it, while FR-108's words require rank 1–5.

The two halves are different failures and neither implies the other. A weak oracle that
runs measures the wrong thing; a strong oracle that does not run measures nothing. It
takes both conjuncts to *look* verified, so it takes both to refuse the look.

## Decision

**Coverage is the conjunction of executability and rank ≤ 5, stated once, and both the
debt and the cap read it.**

1. **The predicate lives on the oracle.** `OracleDeclaration.covers` is
   `is_executable and rank <= COVERING_ORACLE_MAX_RANK`. Both facts are fields of the
   oracle, so the predicate belongs where they are — a free function taking `(rank,
   executable)` would let a caller pass a rank that is not the oracle's.

2. **`COVERING_ORACLE_MAX_RANK = 5`, and FR-103's table is why.** Ranks 1–5 derive a
   check from something the contract already asserts — an invariant, a state machine, a
   signature, a relation between operations, the system model. Ranks 6 and 7 do not:
   FR-103's strength column calls them "sample, not coverage" and "detects change, not
   wrongness".

3. **One measure, in one place.** `Contract.uncovered_clauses` is the complement of
   `covers` over the clause set; `Contract.ground_truth_debt` is its size as a fraction;
   `contract.ground_truth_debt` delegates to the property. The function and the property
   were the same count until FR-108's rank half was read, and a report whose printed
   debt and applied cap could disagree is the drift this removes.

4. **`Contract.ceiling` applies FR-109 as a cap, not a downgrade.** An uncovered clause
   caps the contract at `UNCOVERED_CLAUSE_CEILING` (L2). It is a *cap* because an
   intention is still the operator's stated intent — it is the autonomy, not the intent,
   that the missing command bounds. L1 would say the clause is not intent at all.

5. **`UNCOVERED_CLAUSE_CEILING` is a separate constant from `MODE_G_CEILING`**, though
   both are L2. FR-123 caps a *delivery* because its architecture passed human gates;
   FR-109 caps a *contract* because a clause in it is unestablished. One symbol would
   make a future change to either silently move the other.

6. **`ceiling_for_rank` stays a pure rank→level map.** It has no oracle to consult, so
   FR-109 is applied where the oracle is known. Its rank cap and FR-109's coverage cap
   are asserted separately in the tests, so a change to one cannot stand in for the
   other.

7. **The CLI names the reason on the line that prints the number.** `sofact contract`
   prints the weakest rank and the ceiling together; when the cap is what moved the
   number, it says so and lists each uncovered clause with which conjunct failed. A
   number that dropped with no reason given is one the operator cannot act on.

## Consequences

**A rank-1 property intention no longer grants L4.** The strongest claim the ladder
offers is now reachable only by a contract every clause of which names a command.

**Debt rose on contracts covered by examples and golden files.** This is the intended
direction: those contracts were reporting 0.0 on clauses FR-103 declines to call
coverage. No oracle *manufacturing* is added — FR-105's measured strength is still a
declaration, and the roadmap row says so.

**`test_contract_builds_when_every_stem_has_an_oracle` failed on the first run, and it
was the defect.** It built a `PROPERTY` oracle with no command and asserted L4 — the
exact row in the table above. The fixture's helper now defaults to a command, because
every test using it asserts a *rank-derived* ceiling and an unexecutable default would
have made those assertions about coverage while reading as if they were about rank.

**FR-104 was investigated and is not a code defect.** FR-104 says ranks 1–2 are
mandatory above L2, but §14's own module-class table puts G3 (API/service) and G4
(persistence) at **L3 with rank-3 contract tests** — the same L3 `ceiling_for_rank(3)`
grants. Read literally, FR-104 would make §14's G3 and G4 unreachable. That is a
spec-internal conflict needing a spec decision (narrow FR-104 to the G7 classes, or
lower §14's G3/G4), not a cap to add; it is recorded in the roadmap row rather than
silently "fixed" in code, because a cap that contradicts the class table would be a
second wrong answer.

**FR-110 (O8) is untouched.** `OracleClass` still has seven members.

## Evidence

- `TestAnUncoveredClauseCapsTheCeiling` (6 tests) and `TestAnOracleCoversItsClause`
  (9 cases) in `tests/ci/test_views.py`; `test_debt_counts_a_weak_oracle_even_when_it_runs`,
  `test_debt_is_zero_at_the_rank_five_boundary` and
  `test_the_measure_is_the_contracts_own_property` in `tests/ci/test_contract.py`; and
  `test_an_uncovered_clause_says_the_ceiling_is_l2` in `tests/ci/test_cli.py`.
- Canaried three ways, each asserting its target string was present before mutating and
  reverted from a file backup: `covers` dropping the rank conjunct (6 tests fail),
  `ceiling` ignoring `uncovered_clauses` (3 fail), and `ground_truth_debt` reverting to
  the executability-only count (2 fail).
- `1150 passed` on the full `tests/ci` run; `ruff check` clean.
