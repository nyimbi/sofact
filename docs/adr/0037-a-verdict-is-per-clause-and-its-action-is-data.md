# 0037 — A research verdict is per clause, and its action is data

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-068, FR-062, FR-079, FR-071, FR-073, FR-070, NFR-024;
  [ADR-0035](0035-a-source-ledger-is-a-graph-of-addressable-claims.md),
  [ADR-0021](0021-research-is-dispatched-not-performed.md),
  [ADR-0008](0008-the-model-is-advisory-only.md),
  [ADR-0036](0036-a-research-budget-is-per-clause-and-its-three-caps-are-not-enforced-alike.md)

## Context

FR-068 is a table with three columns: an intent clause, a verdict on it, and what
happens next. The verdicts are Validated, Invalidated, Unverifiable, Deepened; the
actions are proceed, do not build, proceed as a flagged assumption, and revise the
clauses. The roadmap recorded it as **Not built** — "No classification type."

Four things about that table decide the design.

**The third column is the requirement.** A system that records "clause C3 was
invalidated" and leaves it to a reader to remember that invalidated means *do not build*
has implemented a report, not the requirement. The action has to be carried by the
verdict, or the pipeline can advance past a premise the research just refuted.

**It says every intent clause.** The clause list is the operator's, produced by P0's
elicitation and held in the draft. If the producer supplies both the clauses and the
verdicts, then "every clause is classified" is the producer measured against itself —
the shape the user's own lessons name as a checker enumerating one of two ways to write
the thing it checks.

**Unverifiable is the one verdict whose action is to proceed.** A parse that fails open
— an unknown or misspelled verdict read as Unverifiable — therefore lets an unreadable
verdict through the phase. Every other default is a stop, and stops are visible.

**"With cited evidence" is a claim about the ledger.** ADR-0035 made the source ledger a
graph of addressable claims, so a verdict's evidence can be *checked*: a citation to
`S07` when the ledger holds `S01` and `S02` is a conclusion resting on a source that
cannot be invalidated with it.

## Decision

**One verdict per intent clause, classified against SoFact's clause list, carrying its
own action, with the evidence checked against the ledger.**

1. **`ClauseClassification` holds exactly FR-068's row**: `clause_id`, `statement`,
   `verdict`, `rationale`, `evidence`, `settled_by`. Nothing else, because the
   requirement names these and a `confidence` field would be a producer's judgement with
   no action attached to it.
2. **The action is data, not prose.** `VERDICT_ACTION: dict[ResearchVerdict, str]` maps
   each verdict to its action; `ClauseClassification.action` reads it, the CLI prints it
   beside every verdict, and `advance_phase` refuses on it. One table, three readers —
   so "Invalidated means do not build" cannot be true in the check and false in the
   printout.
3. **Invalidated and Deepened stop P1 from completing.** `advance_phase` raises when the
   current classification returns to P0, naming each stopping clause and its verdict.
   The two are stopped for different reasons — one says the premise is contradicted, the
   other that the evidence reframed the question — and the message carries both the
   count and the clause ids so an operator knows what to revise.
4. **Unverifiable becomes a flagged assumption with a refuter.** `flagged_assumption`
   returns an `Assumption` whose `refuted_by` is the classification's `settled_by`.
   Without this, FR-068's third action would be a sentence in a document; with it, FR-079
   ("an assumption without a refuting observation is a belief") is what makes the action
   real, and a producer that cannot name what would settle the question has not produced
   an Unverifiable verdict.
5. **The evidence must match the verdict, in both directions.** A decided verdict with no
   evidence is an opinion wearing a verdict's name. An Unverifiable verdict *citing*
   evidence contradicts itself: "no evidence either way" is a statement about absence,
   and a verdict holding both is unreadable. So Unverifiable refuses evidence and
   requires `settled_by`; the other three require evidence and refuse `settled_by`.
6. **The clause list comes from the draft, and is written into the goal.** `research_goal`
   takes `clauses` and writes `- {id}: {statement}` lines into the prompt;
   `classification_checks` measures "every clause is classified" against the draft's
   stems. The producer is told the subject list, so a run that classified one of five
   clauses is measured against the five it was given.
7. **An unknown verdict raises rather than defaulting.** Decision 3 of the Context: the
   one wrong default is Unverifiable, whose action is *proceed*. A typo becoming "no
   evidence either way" is the failure that lets an unreadable verdict through.
8. **An unknown key raises rather than being dropped.** Same rule as the source ledger's
   parser (ADR-0035): a producer's judgement that the reader silently discards is worse
   than an error it reports.
9. **A classification is versioned and appended, never edited.** `LedgerKind.RESEARCH_CLASSIFIED`
   is a row like any other; a second classification is version 2 and the first stays in
   the log. The earlier conclusion is *why* the pipeline went back to P0, so deleting it
   would delete the reason.
10. **The machine checks exactly three things**, and they are the three ways a
    classification can be about something other than the research it claims to rest on:
    every clause is classified, every cited source is in the ledger, nothing is
    invalidated. The Unverifiable and Deepened *counts* are deliberately not checks —
    they are measurements a reader acts on, and a check that fails on a legitimate
    outcome is a check that gets disabled.
11. **`classifications` defaults to `()` and `classification` is the latest.** An older
    log's rows fold without the field, and a project that has not classified yet is not a
    project that failed a classification check — `classification_gate` returns `()`.

## Alternatives refused

* **Record the verdict and print the action in the CLI only.** Refused in decision 2: the
  action would then exist in a printout and not in the state machine, so a `sofact phase`
  advance would not see it — which is exactly the "a control that exists is not a control
  that is applied" failure.
* **Let the producer supply the clause list.** Refused in decision 6. It would make
  "every clause is classified" trivially true and the check would measure nothing.
* **Default an unknown verdict to Unverifiable.** Refused in decision 7: Unverifiable is
  the only verdict whose action is *proceed*, so the default would be the one that fails
  open.
* **Make Unverifiable's action "stop and gather more evidence".** Refused: FR-068's table
  says proceed-as-a-flagged-assumption, and inventing a stop the requirement does not ask
  for would block the pipeline on questions research structurally cannot answer. The
  honesty is carried by the assumption's `refuted_by`, not by halting.
* **A single `ResearchClassification` with a `clauses: dict[str, str]` verdict map.**
  Refused: a dict cannot carry the rationale, the evidence, or `settled_by` per clause,
  and those are the parts a reader needs to act on the verdict.
* **A check for "no Unverifiable clauses".** Refused in decision 10: unverifiable
  premises are a normal research outcome, and a gate that fails on a normal outcome
  teaches its operator to bypass it.
* **Let `evidence` name a claim id instead of a source id.** Refused: ADR-0035's claims
  are addressable and the ledger already resolves source→claims, so the source is the
  coarser and checkable reference. A claim-level citation is a refinement to make when a
  producer can be relied on to name claims correctly.

## Consequences

* **FR-068 moves from Not built to Implemented, and FR-062's remaining half closes.** P1
  now emits three artefacts: the research record (bounded, FR-072), the source ledger
  (addressable, FR-070), and the per-clause classification (FR-068). A resume lands on a
  phase whose output is an artefact in every phase P0–P3.
* **`advance_phase` gains a refusal at P1 completion.** A project with an invalidated or
  deepened clause cannot advance out of P1 through the service or the CLI; the way
  forward is a new elicitation, which is FR-068's own action.
* **`research_goal` gains a `clauses` parameter**, defaulting to empty. A goal with no
  clauses still runs — the budget path (ADR-0036) depends on that — and the
  classification's own check is what reports the empty case.
* **`ProjectState` gains `classifications` and `classification`**, mirroring
  `ledger`/`ledgers`. `test_state.py`'s census counts record *kinds*; the new kind is
  added to the enum, so the census assertion grows by one and its diff is the change.
* **A new verb**, `sofact classify [--from-run <id>]`, which reads a run's
  `research-classification.json` into the log and prints each verdict with its action,
  its rationale and its evidence, plus the flagged assumptions and a red block naming the
  clauses that return to P0. A failed check exits 1.

## Evidence

* `src/sofact/views.py` — `ResearchVerdict`, `VERDICT_ACTION`, `ClauseClassification`
  (with `_the_evidence_matches_the_verdict`, `action`, `returns_to_p0`,
  `flagged_assumption`), `ResearchClassification` (with `_every_clause_is_classified_once`,
  `invalidated`/`deepened`/`unverifiable`/`returns_to_p0`/`flagged_assumptions`/
  `unclassified`/`classification`), `LedgerKind.RESEARCH_CLASSIFIED`, and
  `ProjectState.classifications`/`classification`.
* `src/sofact/research.py` — `LEDGER_CLASSIFICATION_FILENAME`, `parse_classification`
  (fails closed on an unknown key, a missing field and an unknown verdict),
  `classification_checks` (the three checks).
* `src/sofact/service.py` — `research_goal`'s clause block, the P1 refusal in
  `advance_phase`, `classification_from`, `record_classification`,
  `current_classification`, `classification_gate`.
* `src/sofact/state.py` — the `RESEARCH_CLASSIFIED` arm.
* `src/sofact/cli.py` — the `classify` verb, `_VERDICT_COLOUR` and
  `_print_classification`.
* `tests/ci/test_service.py::TestTheClauseClassification` — 21 tests: the fold replay,
  the action per verdict, the P1 refusal on Invalidated and on Deepened, the flagged
  assumption and its refuter, the dangling citation, the partial classification, the
  goal text, the missing artefact, the versioning, the other-goal refusal, the unknown
  verdict, the unknown key, and the four type-level refusals.
* `tests/ci/test_cli.py::TestTheClassifyVerb` — 8 tests: the empty-project message, the
  five verdicts with their actions, the non-zero exit on a stop, the flagged assumption
  block, the dangling citation, the partial classification naming the missing clauses,
  the missing artefact, and the unknown run.
* `tests/ci/synthetic.py` — the `research-classification.json` branch, which reads the
  clause ids *back out of the goal text* rather than inventing them, plus five mode
  variants (`-invalidated`, `-deepened`, `-unverifiable`, `-dangling`, `-partial`).
* **Canaries**, each with the target string asserted present before the patch and the
  file restored from a `/tmp` backup rather than from git:
  * `ClauseClassification._the_evidence_matches_the_verdict` short-circuited with an
    early `return self` — the four type-level refusal tests failed
    (`test_an_unverifiable_verdict_may_not_cite_evidence`,
    `test_a_validated_verdict_must_cite_something`,
    `test_an_unverifiable_verdict_must_name_what_would_settle_it`,
    `test_settled_by_on_a_decided_verdict_is_refused`).
  * `advance_phase`'s P1 refusal guarded with `if False and ...` —
    `test_an_invalidated_clause_stops_the_phase_rather_than_being_reported` and
    `test_a_deepened_clause_stops_the_phase_too` failed.
  * `parse_classification`'s verdict lookup replaced with a constant
    `ResearchVerdict.UNVERIFIABLE` — `test_an_unknown_verdict_is_refused_rather_than_defaulted`
    failed, which is the canary that matters most: it is the one that shows the fail-open
    default is caught rather than silently proceeding.
* `tests/ci` at this commit: **844 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

* FR-068 (a verdict on every intent clause), FR-062 (every phase emits a durable
  artefact), FR-079 (an assumption must name its refuter), FR-071 (the disconfirming
  count), FR-073 (contradiction detection), FR-070 (the addressable ledger), NFR-024
  (record what was observed).
* [ADR-0035](0035-a-source-ledger-is-a-graph-of-addressable-claims.md) — the ledger a
  verdict's evidence is checked against.
* [ADR-0036](0036-a-research-budget-is-per-clause-and-its-three-caps-are-not-enforced-alike.md) —
  the bound on the run that produces the classification.
* [ADR-0021](0021-research-is-dispatched-not-performed.md) — research is dispatched, so
  the classification is a producer artefact SoFact parses and checks.
