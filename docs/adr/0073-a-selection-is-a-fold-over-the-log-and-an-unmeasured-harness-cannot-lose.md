# 0073 — A selection is a fold over the log, and an unmeasured harness cannot lose

- **Status:** Accepted
- **Date:** 2026-10-16
- **Related:** FR-135, FR-139, FR-143, FR-147, FR-148, FR-138, NFR-024, §8.6, §20.4;
  [ADR-0004](0004-delegate-the-coding-loop-to-an-external-harness.md),
  [ADR-0012](0012-the-harness-table-is-data-not-code.md),
  [ADR-0055](0055-attempt-telemetry-is-a-join-and-the-unmeasured-token-count-is-part-of-it.md),
  [ADR-0064](0064-the-authoring-surfaces-cannot-reach-a-model.md),
  [ADR-0072](0072-the-depth-assignment-is-sofacts-and-the-model-is-the-deployments.md)

## Context

**FR-147** is one sentence: "Harness selection must be **empirical** — driven by measured
goal-declaration precision (§20.4) and throughput, not by reputation. D11's matrix is the
selection instrument and must be populated from probes (M0 item 6), not from vendor claims."
The roadmap row named the gap in five words: *"No selection: nothing chooses a harness from
the measurement."*

That was literally true. `FactoryService.harness_name` took `--harness`, then
`SOFACT_HARNESS`, then `DEFAULT_HARNESS` if it was in the table, then a table of exactly one
entry — and **refused an ambiguous table outright** rather than choosing. Every one of those
is a declaration or a reputation. A deployment that configured two harnesses and probed both
had learned something and could not use it.

**The metrics did not exist either.** §20.4 lists five meta-harness metrics and a grep for
all five found zero implementations. FR-143's `declaration_precision` was scoped to one
harness. So the ranking had nothing to rank on, which is why the row was `Partly` and not
`Not built` — the instrument's *reader* was missing, not its inputs.

**And the inputs were already in the log.** `DispatchRecord` carries `harness`,
`declared_complete`, `tokens_observed`, `continuations_observed`, `wall_clock_seconds` and
`checkout` (with `ModuleCheckout.module`). `GoalPlan.step_by_id` resolves a dispatch's step
to the clauses it covered. `VerificationReport` says which of those clauses the verifier
satisfied. `HarnessProfile` carries the probe's findings. `IntegrityCheck` carries FR-139's
hash verdicts.

## Decision

### 1. The selection is a pure fold over rows that already exist

`sofact.selection.measure_harnesses` reads dispatches, plans, profiles, integrity checks and
verdicts, and produces one `HarnessMetric` per configured harness. Nothing opens a file,
launches a child or consults a clock. That is `sofact.escape`'s and `sofact.telemetry`'s
contract and for the same reason: **a choice reproducible from the log is evidence, and one
computed from live state is a preference.**

It follows that there is **no new `LedgerKind` and no `state.py` change**. `SpendReport` set
this precedent for FR-133 and ADR-0055 for FR-102; a row for a computation the log already
determines would be a second source of truth, and the second one is the one that goes stale.

`harnesses` is an **input** rather than derived from the dispatches. A report built from
dispatch rows alone would omit the harness that never ran — and "absent from the report" and
"excluded by FR-135" would then look identical, when the operator's next question is always
about the one that is missing.

### 2. `None` is not zero, and it is not disqualifying either

Every rate is `None` when its denominator is zero (NFR-024). `HarnessSelection.ranked`
contains only *measured* candidates, so an unmeasured harness is not last — it is **not in
the ranking at all**, and `HarnessSelection.unmeasured` names it. The defect this prevents is
the one FR-147 exists to replace: a harness that has never run winning a contest against one
that has, on the strength of a rate nobody computed.

`is_measured` is `declarations > 0 or bool(verified_modules)` — **two denominators, and they
are deliberately different.** Precision needs a *declaration*: a producer that never says it
is done has no precision, and dividing by its silence would score it on nothing.
`verified_modules` needs a *verdict*: whether a module's clauses were satisfied is the
**verifier's** finding and does not depend on the producer having an opinion. A harness that
never declares and whose work is nonetheless verified clean has good throughput and
unmeasured precision, and both are true statements about it.

### 3. The ranking is precision, then throughput — and a tie is reported

`ranked` sorts on `(-precision, seconds_per_verified_module, harness)`. The two axes are the
ones FR-147 names, in the order it names them. Seconds per module rather than modules per
second because a module-per-second rate on a fast harness rounds to a number that cannot be
compared with a slow one, and because wall clock is the resource §1.3 bounds.

The alphabetical third key exists so the sort is **total**, not so that it can pass for a
finding. `HarnessSelection.tied` reports every candidate equal to the best on **both** axes,
and `caveats` says the order between them is arbitrary. A sort key that silently resolved a
tie would be an arbitrary choice wearing a measurement's clothes.

`tokens_per_verified_module` and `continuations_per_verified_module` are **carried and not
ranked on**. FR-147 names precision and throughput; the token rate is neither, and it is
carried because it is the number that explains the bill — a selection report that omitted it
would send its reader to a second verb for the one figure they will ask about.

### 4. A goal-hacker is excluded, not ranked lower

`HarnessMetric.exclusion_reason` returns the first of three reasons, and the **order is the
point**:

1. **`integrity_failures`** — FR-139, and §20.4 calls a contract-integrity failure "the
   sharpest form of goal-hacking". A harness that edited its own success criteria is not one
   you rank below another; it is one you do not run. A *high* precision is the expected shape
   of a goal-hacker, which is why this is checked before the score is read at all.
2. **`not probed`** — FR-148 requires a recorded profile before any dispatch.
3. **`not supports_goal_dispatch`** — FR-135's disqualifying pair, in FR-135's word.

`supports_goal_dispatch` is `bool | None` and `None` is not `False`: an unprobed harness has
not *failed* to support goal mode — nobody asked it. Collapsing the two would exclude a
harness on the strength of a probe that never ran, which is `HarnessProfile.observation`'s
`INCONCLUSIVE` rule one level up.

### 5. Integrity failures are attributed through the plan, and the direction is deliberate

`IntegrityCheck` carries **no harness field**, and that is correct: FR-139's question is
whether the artefacts still match what the plan pinned, and the answer does not depend on who
was asked to produce them. So attribution goes through `check.label.split(":", 1)[0]` — the
plan id — to every harness that dispatched on that plan.

That can **over-attribute** when two harnesses worked the same plan. The direction is chosen:
over-attribution excludes a harness that may be innocent, and under-attribution would let a
goal-hacker stay selectable. Between a false exclusion an operator can see and investigate,
and a false admission nothing surfaces, the second is the worse error — and it is the one
FR-139 exists to prevent.

### 6. The declaration is a fallback, and the report says which happened

`select_harness` takes `declared` — what the deployment named — and uses it **only** when the
measurement chose nothing. The precedence is measurement first, declaration second, which is
FR-147 read literally. A declared harness is not a reputation, and it is still not a
measurement.

A `declared` name outside the configured table is **ignored rather than honoured**: the
candidate set is `harnesses`, and choosing outside it would be a selection this module cannot
measure or explain.

`HarnessSelection.discharged` returns `()` on a fallback and on no selection, so a selection
that rested on no measurement **claims nothing** — `AttemptTelemetryReport.discharged`'s rule
and `EscapeReport`'s before it. `reason` carries a different sentence for each ending, so a
reader is never left to infer which of the two happened from `chosen` being non-`None`.

## Consequences

**What this buys.** A deployment with several harnesses can now use what its own probes and
dispatches taught it, and the choice is reproducible from the ledger. `sofact select` prints
the ranking, the exclusions and the caveats, and exits non-zero only when nothing could be
chosen — so an empirical answer that disagrees with `--harness` is the requirement working
rather than a failure. Four of §20.4's five metrics now have a reader, which is what FR-147
needed and did not have.

**What it costs.** The selection is only as good as the log: a deployment that has probed
nothing and dispatched nothing gets `chosen is None` and a sentence telling it to probe. That
is the honest answer and it is a worse *experience* than a default — an operator who wants a
harness chosen for them must now run a probe first. The alternative was the silent reputation
contest the requirement forbids.

**The limit, stated.** This instrument **cannot compare two harnesses on the correctness of
the work, and does not try.** `verified_modules` counts modules whose clauses the *verifier*
satisfied, which is a fact about the modules, not about the producer. A harness whose
sessions all pass and whose modules are wrong is not a harness this instrument can see —
because SoFact's verdicts come from its own oracles and never from the producer's report
(FR-138), which is the property that makes it worth having.

**One of §20.4's five metrics is still unmeasured, and it is named rather than approximated.**
**Wave utilisation** is concurrent sessions ÷ wave width. The plan knows the wave width
(`GoalPlan.waves()`); the dispatch record does not carry it, and a `DispatchRecord` cannot
say whether its wave *could* have run concurrently. Computing it from the dispatches alone
would produce a number that moves with the dispatch order rather than with the DAG — the
shape §20.4 says the metric exists to detect. It is therefore reported as unmeasured, which
is the state NFR-024 gives it.

**Nothing changed for a single-harness deployment.** `harness_name` is untouched; the new
verb is a reader beside it. A deployment that never runs `sofact select` behaves exactly as
before.

## Evidence

- `uv run pytest -q tests/ci/test_selection.py` — 35 passed.
- `uv run pyright` — 0 errors, 0 warnings, 0 informations.
- Three defects the test module's first run caught, each a fixture claiming something the
  code does not do: `GoalStep.id` is a real UUID7 and `"s1"` is not; `seconds_per_verified_module`
  is `None` without a *module*, so a hand-built dispatch with no checkout has no throughput
  however much wall clock it carries; and `tied` **includes the best itself**, so a
  non-tie is a one-element tuple and `()` means nothing was measured. The third was my own
  assertion being wrong about a correct implementation.
