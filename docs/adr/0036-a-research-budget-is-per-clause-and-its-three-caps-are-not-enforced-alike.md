# 0036 — A research budget is per clause, and its three caps are not enforced alike

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-072, FR-140, FR-167, NFR-024, NFR-009;
  [ADR-0021](0021-research-is-dispatched-not-performed.md),
  [ADR-0008](0008-the-model-is-advisory-only.md),
  [ADR-0035](0035-a-source-ledger-is-a-graph-of-addressable-claims.md)

## Context

FR-072 is one sentence: "Research must be **bounded**: a declared budget of sources,
time, and model calls per intent clause. Unbounded research is a way to never build."
The roadmap audit recorded it as **Partly**: "`--timeout` and the extension's own loop
ceiling bound wall clock; there is no source/model-call budget per clause."

Three things about that sentence decide the design.

**It says *per intent clause*, not per run.** That is not a stylistic choice. A goal
whose elicitation produced eight clauses has eight premises to check and one that
produced one has one; a flat ceiling bounds both identically, which is a bound on the
*goal* rather than on the research. So the declaration is per clause and the figure a
run is measured against is the product — two different quantities, and a reader must be
able to tell which one a number is.

**Three quantities are named, and they cannot be handled the same way.** ADR-0021
settled that research is *dispatched*, so the work happens inside a harness SoFact does
not control, and FR-140 says budgets belong to SoFact because "a cap the producer can
raise is not a cap". Wall clock SoFact can hold: it owns the timeout and kills the
child. Sources and model calls it can only *read off the artefacts afterwards* — the
count of cited URLs, and the loop's own turn count in `research-meta.json` ([S25]).
Enforcing either inside the producer's runtime would be the producer grading its own
spend.

**The numbers are not SoFact's to invent.** [S25] measured the delegated loop: its
advertised floor is "must call the search tool at least 5 times", its own ceilings are
240 s (deep) and 360 s (super), and on a local 35 B model the ceiling binds before the
floor — 3 searches, then a 140-character stub. So the source cap and the call cap are
that floor read back as a ceiling (5), and the wall-clock cap is set **above** the
loop's own ceiling (300 s) so that a truncation is attributed to the extension that
caused it rather than to SoFact's outer envelope.

## Decision

**One budget type declared per intent clause, scaled into a per-run allowance that the
record carries, with the wall-clock cap enforced and the other two observed.**

1. **`ResearchBudget` is per clause and holds exactly FR-072's three quantities.**
   `max_sources_per_clause`, `max_wall_clock_seconds_per_clause`,
   `max_model_calls_per_clause`. Nothing else, because the requirement names three and
   a fourth would be a bound nobody asked for.
2. **A zero cap is refused at construction, not read as a tight budget.** A zero
   multiplies to a whole-run allowance of zero, so *every* run would violate its budget
   and the violation would stop carrying information. An operator who wants no research
   does not dispatch one.
3. **`scaled(clauses)` returns a `ResearchAllowance`, a separate type.** "5 sources per
   clause" is a declaration; "25 sources for this run" is the figure the run is measured
   against. One field carrying both would make those the same sentence, and the record
   would no longer say which the operator declared.
4. **`scaled` refuses a clause count below one.** The substitution — *a goal with no
   draft yet is one subject* — is made by the caller that can see the goal, and the
   allowance records the count it used. Hidden in an arithmetic helper, the substitution
   would be invisible in the record and an allowance of zero would be reachable by
   accident.
5. **A goal with no draft counts as one clause, and the record says so.** The first
   research run on a fresh goal is a real and common case; giving it an allowance of zero
   would make it violate its own budget by construction.
6. **Wall clock is enforced; sources and model calls are observed.** The timeout SoFact
   passes is the scaled allowance. Exceeding either observed cap appends to
   `budget_violations` with wording that says which kind of bound it was — "process
   killed by SoFact, which holds the budget" for the first, "observed after the fact so
   recorded rather than enforced" for the others. Printing them alike would make an
   observed overspend look like a bound that held.
7. **An unmeasured count produces no violation, in either direction.** A truncated meta
   carries no turn count, and `model_calls_observed` stays `None`. Rounding that to zero
   would report the cheapest possible run; treating it as a violation would report a
   spend nobody measured (NFR-024). The CLI prints `calls    unmeasured` and says the cap
   was not checked either way.
8. **An overspend is not a failure.** `outcome` is what the process did and
   `budget_violations` is what it spent; FR-138 keeps those apart, and a run that
   overspent and still produced a readable ledger is recorded as exactly that. The record
   is the same shape either way.
9. **An explicit `timeout` overrides the scaled wall clock for one run, and does not
   rewrite the budget.** The allowance on the record stays the declared figure, because a
   run whose enforced bound differs from its declared budget is a run whose budget line
   does not describe it — and an operator who raised a cap has to be able to see that
   they did.
10. **The budget is stated in the goal text.** `research_goal` names the totals and the
    per-clause figures. This is not enforcement and is not claimed as such; it is what
    makes "exceeded its budget" a statement about a producer that was told one.
11. **The record carries `budget` and `allowance` as optional fields, defaulting rather
    than required.** An older log's rows fold without them — `allowance` is `None` there
    — so a project recorded before this decision stays readable. The default is a
    *budget*, never a missing measurement: `budget_violations` defaults to `()`, which is
    "none recorded", and the CLI's `unmeasured` branch is what keeps that from reading as
    "none occurred".

## Alternatives refused

* **A single flat ceiling per run.** Refused in the Context: FR-072 says per intent
  clause, and a flat bound gives a one-clause goal the same allowance as an eight-clause
  one — which is a bound on the goal, not on the research.
* **Enforce all three inside SoFact.** Refused: two of the three are only knowable from
  artefacts written *after* the work. A cap enforced before the artefact exists is a cap
  on a guess.
* **Enforce the call cap by counting the producer's turns live.** Refused for the same
  reason ADR-0021 refuses to grade the report: the count comes from the loop's own meta,
  which is the producer's word. Reading it as a *measurement* is honest; enforcing
  against it would make a producer's arithmetic authoritative.
* **A cap of zero as an explicit "no research" setting.** Refused in decision 2: it
  makes every run violate its budget, which destroys the signal the violation carries.
  "Do not research" is expressed by not dispatching a research run.
* **Fail the run when a cap is exceeded.** Refused in decision 8, and this is the
  tempting one — it would make FR-072 look enforced end to end. But the artefact is
  already written by then, and discarding a usable ledger to punish a spend overrun
  loses the evidence the phase exists to produce. The spend is recorded; the ledger is
  read; the operator decides what an overspend means.
* **Default `allowance` to a scaled budget so the field is never `None`.** Refused: it
  would make "this run was measured against 5 sources" and "this row predates budgets"
  the same value, which is the collapse decision 3 exists to prevent.

## Consequences

* **FR-072 moves from Partly to Implemented**, and the roadmap's last P1 gap closes. P1
  now has a bound, an artefact (ADR-0035), and a per-clause declaration; FR-068's
  per-clause *verdict* remains the phase's open requirement and is a different artefact.
* **`--timeout` changes meaning.** It was the only bound; it is now an override of the
  scaled one. Its default changes from `RESEARCH_TIMEOUT_SECONDS` (900 s) to `None`,
  which is a behaviour change for a caller that passed nothing — the run is now bounded
  by `300 s × clauses` instead of 900 s flat. For a one-clause goal that is *tighter*
  (300 < 900), and that is the intended direction: the flat default was three times the
  per-clause bound for the commonest case.
* **Three new flags**: `--max-sources`, `--max-calls`, `--seconds`, all per clause, all
  defaulting to the declared budget. A bad one exits 1 with the field named rather than
  raising through typer.
* **`ResearchRecord` gains three fields and a property.** `test_state.py`'s census does
  not count record fields, so the field-count assertion is unaffected; `budget`,
  `allowance`, `model_calls_observed` and `budget_violations` all have defaults, so an
  older row folds.
* **The synthetic harness now writes `turns` in its meta**, which is what makes the call
  cap measurable in tests at all — and its `research-stub` variant deliberately omits it,
  so the unmeasured branch is exercised rather than assumed.
* **`RESEARCH_TIMEOUT_SECONDS` survives as the flag's default only.** The per-clause
  constant is what bounds a run; the old constant is what a caller gets when it says
  "ignore that for this one", and its docstring now says so.

## Evidence

* `src/sofact/views.py` — `ResearchBudget` (with `_every_cap_bounds_something` and
  `scaled`), `ResearchAllowance`, `DEFAULT_RESEARCH_{SOURCES,SECONDS,CALLS}_PER_CLAUSE`,
  `ResearchRecord.budget`/`allowance`/`model_calls_observed`/`budget_violations` and
  `is_within_budget`.
* `src/sofact/service.py` — `research` (the clause count, the scaled allowance, the
  override), `_research_violations`, and `research_goal`'s budget paragraph.
* `src/sofact/cli.py` — `--max-sources`, `--max-calls`, `--seconds`, the budget line,
  the violation lines and the `calls    unmeasured` branch.
* `tests/ci/test_service.py::TestTheResearchRun` — 7 new tests: the allowance on the
  record, scaling with the clause count, an overspend recorded as a violation and not a
  failure, an unmeasured count producing no violation, the timeout override leaving the
  declared budget intact, the zero-cap refusals, and `scaled(0)`.
* `tests/ci/test_cli.py::TestTheResearchVerb` — 4 new tests: the budget line, the
  overspent line, the unmeasured line, and a zero flag refused without a traceback.
* `tests/ci/synthetic.py` — `turns` in the meta, the `research-greedy` overspend
  variant, and the stub's deliberate omission.
* **Canaries**, each with the target string asserted present before the patch and the
  file restored from a `/tmp` backup rather than from git. The first attempt's patch did
  **not** apply — the indentation in the target differed — and the `assert` is what
  caught it; a canary whose patch silently no-ops is a canary that did not run.
  * `ResearchBudget._every_cap_bounds_something` replaced with `if False:` —
    `test_a_zero_cap_is_refused_rather_than_read_as_a_tight_budget` failed.
  * `_research_violations`' model-call branch replaced with `if False and ...` —
    `test_an_overspent_run_records_the_cap_it_broke` failed.
  * `research`'s clause count hardcoded to `1` —
    `test_the_allowance_scales_with_the_clause_count` failed.
* `tests/ci` at this commit: **815 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

* FR-072 (bounded research), FR-140 (budgets are SoFact's), FR-167 (research is
  dispatched), FR-138 (a declaration is not a finding), NFR-024 (record what was
  observed), NFR-009 (reproducibility).
* [S25] — the delegated loop measured: its five-search floor, its 240 s/360 s ceilings,
  and the local-model truncation that sets the wall-clock cap above them.
* [ADR-0021](0021-research-is-dispatched-not-performed.md) — research is dispatched, so
  its spend is observable and not controllable.
* [ADR-0035](0035-a-source-ledger-is-a-graph-of-addressable-claims.md) — the artefact
  this budget bounds.
