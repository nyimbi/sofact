# 0065 — The roadmap tally is counted from its rows, and the rule has two disjuncts

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** ADR-0064, FR-006, NFR-024

## Context

`docs/research/roadmap-gap/README.md` publishes a tally — how many of its 119 rows are
Implemented, Partly, Deferred or Not built — and every refresh states its arithmetic in
prose, because the number is how a reader decides whether the product is nearly done. The
file's own history says the number has been wrong repeatedly: one refresh found *nine* rows
closed without the count moving, and a later one found the prose line and the table
disagreeing by two rows on the same tree.

The file also claims, twice, that the number "is asserted against the 119 row count rather
than trusted". Nothing asserted it. No test read the roadmap table at all; the claim was a
statement about a check that did not exist, which is the class of documentation defect
`test_docs.py`'s own docstring names as the one that goes false silently — the test is
never written, the sentence stays, and nothing fails.

**The near-miss that made this concrete.** While refreshing the table for ADR-0064, the
counting rule was re-derived and found to be *narrower than the classifier behind it*. The
document stated one disjunct — a verdict cell that names an unbuilt half — while the
classifier that produced every published number had been applying two: the second being an
evidence cell carrying a `**Still open**` marker. **FR-124** is the row that separates them:
its half sat in its evidence cell under that marker while its verdict cell read bare
`**Implemented**`. Under the stated rule it is Implemented; under the rule that produced
the tables it is Partly. Every published table from ADR-0060 to ADR-0063 counts it Partly.

That was settled by running both readings against the four committed tables rather than by
choosing the one that looked right:

| Revision | Published table | One disjunct | Two disjuncts |
| --- | --- | --- | --- |
| ADR-0060 | `91/22/0/6` | `92/21/0/6` | `91/22/0/6` |
| ADR-0061 | `91/24/0/4` | `92/23/0/4` | `91/24/0/4` |
| ADR-0062 | `91/25/0/3` | `92/24/0/3` | `91/25/0/3` |
| ADR-0063 | `91/26/0/2` | `92/25/0/2` | `91/26/0/2` |

The one-disjunct statement reads all four one Implemented too high. The rule is two
disjuncts, and the document now says so.

**One published table does not reproduce, and it is recorded rather than smoothed.** The
pre-A2 tree (`c3c2057`) gives `90/23/0/6` where that refresh published `91/22/0/6`. The
single row responsible is **FR-059**, whose verdict cell read a bare `**Partly**` there —
so the refresh's *own stated convention*, "it classifies on the cell's **leading** token",
counts it Partly, and the table it published did not. That is the same staleness its prose
confesses for nine other rows. ADR-0060 then promoted FR-059's cell to "Implemented where a
boundary holds", which is the honest form for a capability that holds only where a
mechanism confines reads, and every table from ADR-0060 onward reproduces exactly.

## Decision

**A test reads the rows and derives the tally, and the number is a consequence rather than
an assertion.** `TestTheRoadmapTallyIsDerivedFromItsRows` (`test_docs.py`) parses every
`| FR-… | verdict | evidence |` row, classifies it by the two-disjunct rule, and asserts
the published table equals the count. It is two tests, not one:

- **The tally equals the rows.** A verdict that moves without the table moving fails here,
  and so does a table edited without a row.
- **Every verdict cell leads with a word the rule knows.** Separate, because a cell
  reshaped to something the rule cannot classify would otherwise surface as an arithmetic
  difference — an operator chasing a count when the defect is a cell.

**The rows are split on the pipe, not matched with a regex.** The first draft used a
non-greedy pattern and read **77 rows where the table has 119**, because evidence cells
contain `|`. It failed loudly on the total, which is luck rather than design: a pattern
that had happened to match 119 of a larger table would have reported clean. The parser
splits the line, which is what the ad-hoc classifier did when it produced the published
numbers.

**The exclusions are held as data, not as prose.** The rule's second disjunct is the
`**Still open**` marker, and the test's docstring carries the table above as its
justification. A future reader who thinks the second disjunct is redundant has the four
published tables in front of them.

## Evidence

The four canaries, each watched failing and reverted from a file backup:

1. **A verdict moved** (FR-016–020, Partly → Implemented, tally untouched) — caught by the
   tally test.
2. **A tally digit changed** (Partly 28 → 27) — caught by the tally test.
3. **An unknown leading word** (`Partly` → `Partially`) — caught by *both*, the
   leading-word test on its own line.
4. **Both disjuncts blinded** (FR-124 reverted to bare `**Implemented**` *and* its
   `**Still open**` marker un-bolded) — caught by the tally test, which is the direct
   demonstration that the second disjunct is load-bearing rather than decorative.

The fourth canary is the one that matters: it is the only mutation that fails if and only
if the second disjunct is doing work.

The gate passes on the shipped tree with the tally at `91/28/0/0`.

## Consequences

1. **The claim in the document is now true.** "Asserted against the 119 row count rather
   than trusted" describes a check that exists.
2. **A refresh that moves a verdict must move the table.** The failure names the label and
   both numbers, so the remedy is one edit rather than a recount.
3. **The rule is stated where it is applied.** The test's `_classify` docstring and the
   document's rule paragraph now agree, and the ADR-0064 refresh is what made them
   disagree visibly enough to find.
4. **It does not check the verdicts are right.** It checks the tally is derived from the
   rows; whether a row's classification is honest is a judgement the refresh makes and this
   gate cannot. That limit is why the two moved rows in ADR-0064 carry their reasoning in
   their own cells rather than in the number.
