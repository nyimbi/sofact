# 0077 — The interrogation asks eight dimensions, and scale is one of them

- **Status:** Accepted
- **Date:** 2026-10-17
- **Related:** FR-064, FR-065, FR-057, FR-079, FR-108, R19, §1.3, §4;
  [ADR-0007](0007-the-elicitation-gate-is-deterministic.md),
  [ADR-0011](0011-the-factory-refuses-to-claim-maintainability.md),
  [ADR-0039](0039-the-envelope-refuses-a-ceiling-and-reports-a-floor.md)

## Context

**FR-064** says elicitation must be "adversarial to ambiguity, not agreeable", and names
the dimensions it must resolve in a seven-row table:

| | |
| --- | --- |
| **Goal** | What decision or action does this enable? |
| **Success** | What observable outcome means it worked? |
| **Scope boundary** | What is explicitly *not* included? |
| **Scale** | How many users/entities/records? What is the growth expectation? |
| **Constraints** | Regulatory, data residency, latency, budget, existing systems to integrate |
| **Non-negotiables** | What must not change or be touched? |
| **Failure** | What does unacceptable failure look like? |

`ElicitationDimension` had **six** members: `OUTCOME`, `CONSUMER`, `BOUNDARY`, `ORACLE`,
`CONSTRAINT`, `FAILURE`.

**The gap is not six-versus-seven, and reading it that way is the first error.** Five of
the spec's rows were present (`Goal` is the statement being elicited; `Success` =
`OUTCOME`; `Scope boundary` = `BOUNDARY`; `Constraints` = `CONSTRAINT`; `Failure` =
`FAILURE`), and **two were absent** (`Scale`, `Non-negotiables`) — while the enum carried
**two the table does not list**: `CONSUMER`, split out of the table's single *Success*
row, and `ORACLE`, which is FR-067's `verification_method` and deliberately produces no
clause of its own. So the target is **eight**, and **no member order reproduces the
table**: the table has no *Oracle* row and one *Success* row that the enum reads as two.
A count is not a correspondence, and this record does not claim one.

**One dropped row had been absorbed into another's question.** `CONSTRAINT`'s question
read *"What are the non-negotiables — platform, stack, dependencies, time?"*. So the
spec's *Non-negotiables* row was not lost by oversight; it was folded into the Constraints
question, where it asks about the stack rather than about what must not be touched. An
operator answering it named Python and a container size, and **nothing asked what the
system must not break** — while the spec's own Constraints row, regulatory and residency
and latency and budget and integration, appeared nowhere. That is why the gap read as a
count mismatch: the missing question had a plausible-looking answer sitting where it
should have been.

**Scale is the one row a stated risk depends on.** R19 — *"Unbounded goals produce
unbounded platforms"* — names two mechanisms: "FR-057 envelope refusal; **P0 must resolve
scale (§4, FR-064)**". The first is built and tested (`envelope.py`, `decomposition.py`'s
P3 refusal, ADR-0039). The second was never started: nothing in P0 asked about scale, and
`ElicitationAnswer.text` is `NonEmptyStr`, so nothing downstream could have read a number
if it had.

## Decision

**`ElicitationDimension` gains `SCALE` and `NON_NEGOTIABLES`, reaching eight members.**
Each gains a `DimensionSpec` and a `_STEM_KIND` entry, so each becomes a clause stem and
travels the same route as every other requirement. `SCALE` is `POSITIVE` — the operator's
stated size is an obligation the system must meet, where a negative reading of the same
words would assert only that some unspecified limit is not exceeded. `NON_NEGOTIABLES` is
`NEGATIVE`, for `BOUNDARY`'s and `FAILURE`'s reason: what must not change is a bound on
the blast radius.

They are placed adjacent to their spec neighbours — `SCALE` after `ORACLE`,
`NON_NEGOTIABLES` between `CONSTRAINT` and `FAILURE` — which is the minimal diff that keeps
each new member next to the row it came from and leaves every positional read in the
existing tests correct.

**`CONSTRAINT` stops asking the other dimension's question.** Its text becomes the spec's
Constraints row, and `NON_NEGOTIABLES` takes the spec's own words. This is a **rewording,
not a new question**: the non-negotiable half already existed inside `CONSTRAINT`, which is
precisely why the drop was invisible. The spec's Constraints row is a *topic list*, not a
question, and the module's own test requires every question to end in `?` — so it is
rendered as a question ("What regulatory, data-residency, latency, budget or integration
constraints apply?") rather than copied verbatim. The two recovered rows are questions in
the spec and are near-verbatim.

**Scale carries a second kind of content floor.** FR-064's own word is *adversarial*, and
"a lot of users" is exactly the clarifying pleasantry it forbids — which `min_chars` cannot
see, since it clears any length. So `DimensionSpec` gains `requires_quantity: bool`, and
`_reasons` refuses an answer naming neither a numeral nor a magnitude word. It is a
**separate field** from `required_markers` on purpose: a marker list means "name a checking
mechanism", which is `ORACLE`'s question and no other's, and `test_only_the_oracle_dimension_demands_a_checking_mechanism`
pins that. The two floors are pinned by tests separately, so neither can spread unnoticed.
The quantity test is deliberately loose about *what* is counted and strict about there being
a count: `200 records` and `a few hundred users` pass, `a lot of users` and `as many as
needed` do not. Bare `ten` is excluded from the magnitude list because it is a substring of
*often*, *written* and *threaten* — a floor clearable by an unrelated word is a floor
failing open.

**What the clause route buys, and what it does not.** A `SCALE` clause is **not verified**,
and this record does not claim it is. The trace: `service.contract` assigns
`suggest_oracle(stem)` to every stem, which for a positive stem is `OracleClass.CONTRACT`
with `command_hint=None`; `is_executable` is `command_hint is not None`; `execution.run_all`
does `if not clause.oracle.is_executable: continue`, so a prose oracle is never run;
`verification._decide` returns `INSUFFICIENT` on no observations; and `delivery.py` counts
only `SATISFIED` as verified and reports the rest through `unverified_clauses_stated`, a
check that **passes** and reports. So a `SCALE` clause lands as ground-truth debt and caps
the contract's ceiling, exactly as every other fixture clause does. The envelope route is
the **refusing** one — `decomposition.py`'s P3 check sets `passed=False` on an over-scoped
proposal — so the clause route is *weaker* than the envelope, not stronger.

What it does buy is that the answer becomes a `Clause` with an oracle **declared against
it**: it appears in the contract, in P4's oracle sampling, in FR-108's debt figure and in
the delivery report's unverified list. It is a named obligation that is visibly unmet
rather than a paragraph nobody reads. `NON_NEGOTIABLES` additionally flows into the
specification's non-goals, the route FR-079 already uses.

## Consequences

- **R19's mitigation is half-built, and this record says which half.** R19 names the
  envelope refusal *and* P0 resolving scale. The envelope half is implemented; this unit
  builds the second half's **question**. Binding a prose answer to a numeric
  `DimensionBound` is refused deliberately: the bounds are `float`, a P0 answer is
  `NonEmptyStr`, and reading a number out of prose to populate a bound is the fabrication
  FR-065 forbids ("report any dimension it could not resolve as an explicit risk rather than
  inventing an answer"). So R19 is not discharged, and a recovered dimension must not be
  read as a discharged risk.
- **The unit does not enforce scale.** A `SCALE` clause's oracle is a suggested prose
  declaration, so P6 records it `INSUFFICIENT`. This is the central limitation and the
  reason the previous draft of this decision was wrong.
- **Nothing binds the spec's table to the enum**, which is *why* this gap survived: no test
  compares `len(ElicitationDimension)` against the table's row count, so a dimension could
  be dropped and only a reader would notice. A test that reads the spec's table is the
  durable fix and is a separate unit, because it changes how the spec is *read* rather than
  what P0 asks.
- **A count in prose is a claim, and this unit was about a count that drifted.** Three
  statements of "six dimensions" in `llm.py`, `test_llm.py` and `README.md` are *measurements*
  taken when P0 asked six questions — two of those prompts exhausted a 1024-token budget —
  so they are dated ("the six dimension prompts P0 then asked") rather than incremented,
  which would falsify the measurement. The incidental counts in `driver.py` and
  `test_driver.py` say "every dimension" instead of a number, since the number was never
  the point and re-arming it only schedules the next drift.
- The floors remain crude proxies for quality. A scale answer naming a quantity is not
  necessarily a *bound* the envelope can enforce, and the module's own docstring already
  says a passed floor is not evidence a requirement is met.

## Evidence

- `tests/ci/test_elicitation.py::test_the_spec_rows_the_enum_dropped_are_now_present` — the
  eight members and the two recovered rows.
- `test_only_the_scale_dimension_demands_a_quantity` pins `requires_quantity` to `SCALE`
  alone, the way `required_markers` is pinned to `ORACLE`.
- `test_a_scale_with_no_quantity_does_not_resolve_and_one_with_a_quantity_does` asserts both
  directions with **literal** inputs, so neither can pass because the text is thin — the
  tautology trap where an input computed from the bound it tests moves with the bound.
- `test_the_constraints_question_no_longer_asks_about_non_negotiables` pins the rewording,
  since a rewording is exactly the change a later edit reverts silently.
- `test_each_fixture_answer_yields_exactly_one_stem` guards the arithmetic in
  `test_draft_stems_*`, which asserts `len(draft.stems) == len(DIMENSIONS) - 1` and holds
  only while every fixture answer is one stem.
- **Four canaries, all caught**: deleting the quantity branch (a scale answer of "a lot of
  users" resolving P0); removing `NON_NEGOTIABLES`'s `_STEM_KIND` entry (the dimension
  asked, resolved, and contributing no clause — written and never read); flipping `SCALE`
  to `NEGATIVE` (polarity wrong while every count still passes); and reverting
  `CONSTRAINT`'s question (the absorbed-row defect returning). The middle pair is the point:
  both mutations are invisible to the count assertions the rest of the suite is built on.
- The fixture's clause count moves 5 → 7, which moves the plan's wave-1 operation count
  3 → 4 and the module actual 5 → 7; every count that moved was re-derived from a run, not
  incremented by hand.
