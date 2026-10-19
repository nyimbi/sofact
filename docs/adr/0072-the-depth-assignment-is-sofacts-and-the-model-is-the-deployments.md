# 0072 — The depth assignment is SoFact's and the model is the deployment's

- **Status:** Accepted
- **Date:** 2026-10-16
- **Related:** FR-132, FR-133, NFR-012, NFR-024, NFR-026, NFR-030, FR-049, FR-100,
  FR-101, FR-102, FR-140, FR-147, §1.3, §1.4, §8.4, §20.4;
  [ADR-0002](0002-model-access-is-one-openai-compatible-interface.md),
  [ADR-0012](0012-the-harness-table-is-data-not-code.md),
  [ADR-0039](0039-the-envelope-refuses-a-ceiling-and-reports-a-floor.md),
  [ADR-0055](0055-attempt-telemetry-is-a-join-and-the-unmeasured-token-count-is-part-of-it.md),
  [ADR-0064](0064-the-authoring-surfaces-cannot-reach-a-model.md)

## Context

**FR-132** asks for a model configuration that is *tiered and declarative*, with a default
that is economical for the phase. Before this change the tree had one model for
everything: `--model`, else `SOFACT_MODEL`, else `DEFAULT_MODEL`, resolved at the adapter
and identical for every dispatch of every phase. §20.4 names the consequence — "tokens per
verified module … drives §1.3 envelope actuals and model tiering (FR-132)" — so the
metric was specified against an instrument that did not exist.

**FR-133** asks for spend attributed *per phase and per module* and reported against the
§1.3 envelope, with its own rationale: "an unattended build with no spend attribution is
an unbounded financial commitment." The tree recorded spend per **dispatch** —
`tokens_observed`, `wall_clock_seconds`, `continuations_observed` — and per **harness**,
and had folded it per **attempt** (ADR-0055). Neither of the two keys FR-133 names
existed, and neither did the envelope comparison.

**The join was missing from both ends.** `DispatchRecord` carries `step_id`; `GoalStep`
carries `id`, `ordinal`, `kind`, `goal`, `budget`, `exit_evidence`, `clause_ids`,
`depends_on` — and **no phase**. The decomposition is P3's artefact and the plan is P5's,
so the two never met, and "spend per phase" had no key to be filed under. `DispatchRecord`
has no module field either; `ModuleCheckout.module` does (FR-100), and it is `None` for a
bootstrap step or one spanning two modules.

## Decision

### 1. The split: SoFact owns which phases need depth, the deployment owns which model

FR-132 has two halves and they belong to different parties. *Which phases need depth* is a
statement about the pipeline, identical for every deployment. *Which model sits in each
tier* is a statement about a machine, a budget and a data-residency obligation, and NFR-026
and FR-049 forbid SoFact having an opinion about it.

So `TIER_PHASES` is built in — `deep`: P3 decompose, P4 contract, P6 verify; `cheap`: P5
build, P7 integrate — and a tier's **model** is configuration, read from
`SOFACT_MODEL_TIERS` by `load_model_tiers` in `HarnessSpec`'s shape and for its reason
(ADR-0012).

`CONTRACT` is in `deep` and FR-132 does not name it. P4 is where a clause gets the oracle
that decides whether it was ever satisfied (FR-103), and an oracle assigned by a cheap
model is a weak oracle *recorded as a decision* — the one artefact in the pipeline that is
cheaper to get wrong later than to get right now. `INTEGRATE` is in `cheap` because FR-142's
wave scheduler runs it mechanically in topological order.

The assignment is deliberately **not exhaustive**. `phase_tier` returns `None` for a phase
in no tier, and `None` is not `cheap`: a phase SoFact put in `cheap` has been *judged*
high-volume, and a phase in no tier has not been judged at all. A default covering every
phase would be a claim about P0, P1, P8 and P9 that nothing in FR-132 supports.

### 2. A declared tier with no model is not a tier with a default model

The tempting fallback — an operator declares `deep` and names no model, so use the cheap
one — is exactly the substitution FR-132 exists to prevent: the phases it just marked
expensive would run on the model it marked cheap, and nothing would say so.

`ModelTier.model` is therefore refused when blank, and `resolve_model`'s precedence is
**explicit → tier → operator → default**, with a tier that has no configured model falling
through to the operator's *named* single model rather than to another tier's. A phase in
no tier falls through the same way.

`resolve_model` returns `(model, source)` and the source travels to
`DispatchRecord.model_source`, because "which model ran this phase, and on whose authority"
is the question the whole design exists to make answerable — and a caller re-deriving it
from the same inputs would be a second implementation of the precedence. `ModelTier`
carries `rationale` as a required field for the same reason one level over: "why is P5 on
the small model" is the question that decides whether the answer is still right after the
hardware changes.

A **capability probe resolves no tier** and records `model_source=None`. The probe names a
model to vary **one** slot (ADR-0019), so a tier applied there would make the two arms
differ in two things and the measured difference would be attributable to neither.

### 3. The phase key is derived from the step kind, and the fold refuses rather than guesses

`STEP_PHASE` maps every `PlanStepKind` to the phase it runs in, and `step_phase` asserts
rather than defaults when a kind has no entry. A field on `GoalStep` was rejected: it would
be a second place for the same fact to be wrong, and it would have to be written by
`compile_plan`, which is P5's and does not know which phase it is serving.

`measure_spend` reads the plan and **raises** — naming the dispatch and the step — when a
dispatch names a step the plan does not hold. Guessing a phase there would attribute spend
to a phase it never ran in, which is worse than an empty cell. The module key is
`ModuleCheckout.module`, and a dispatch with no module is counted in `unattributed` rather
than dropped, so `by_module` plus `unattributed` equals the phase total and the two tables
are one fold rather than two summaries that can drift apart.

`None` is *unmeasured*, never zero (NFR-024): `tokens_observed` is `int | None`,
`SpendAttribution` carries `unmeasured_tokens` beside `tokens`, and `tokens_measured` /
`tokens_complete` say whether the sum is exact. `tokens_per_dispatch` is `None` unless it
is. ADR-0055's rule, one requirement along.

### 4. The envelope has no token dimension, and says so rather than inventing one

`SpendReport` carries `token_dimension = None` and a `token_envelope_note` saying the
envelope cannot bound a quantity it does not state. §1.3 states no token bound, and
inventing one to have something to compare against would be a configured ceiling that
nobody configured.

### 5. The wall-clock dimension is a target range, not a cap

**This is the defect the unit's own test caught, and it is the reason the comparison is not
a boolean.** §1.3's `wall_clock_days` is `DimensionBound(minimum=2, maximum=10)` — a
**target range**. The first version returned a single `wall_clock_within_envelope`, and the
first test asserting on a seconds-long synthetic run reported `assert False is True`.

That reading is wrong in the direction that matters. §1.4 wants small deliveries buildable
(ADR-0039's finding, applied to the same dimension), so a run **under the floor** is
expected and is *not an overspend* — and only over-ceiling is what FR-133's rationale is
about. A boolean would have reported every short run as an envelope failure and trained an
operator to ignore the column, which is the failure mode that turns a gate off.

So `wall_clock_measurement` returns the `EnvelopeMeasurement` with a `detail` that names
the direction, and `wall_clock_over_envelope` is `True` only above the ceiling. `sofact
spend` exits non-zero on that and on an empty run.

## Consequences

**What this buys.** A deployment can run P3/P4/P6 on a deep model and P5/P7 on a cheap one
without SoFact having an opinion about which models those are, and every dispatch records
which rule chose its model. Spend is answerable per phase and per module, which is what
§20.4's "tokens per verified module" needed and did not have.

**What it costs.** A tier table is a second configuration file an operator must keep
current, and a stale one is silent: nothing detects that `deep` now points at a model the
harness stopped serving until a dispatch fails. `sofact tiers` prints the resolution per
phase so the table can be read without dispatching, and FR-147's `MODEL_RESOLVED` probe is
the instrument that says whether the harness accepts the identifier — but the table itself
is not validated against any registry, because no registry is reachable from a config
reader (ADR-0002's hermeticity cost, unchanged).

**The limit, stated.** `{model}` is a slot in a harness spec's argv and a spec may simply
not use it, in which case the child runs the harness's default while `DispatchRecord.model`
names the tier's model — the record true about the decision and false about the session.
The `MODEL_RESOLVED` probe observes the harness's *acceptance* of the identifier plus a
readable session record; nothing in this build reads the serving model off the record, so a
harness that accepted the tag and served another one is not detectable here. The config
table states the decision; it does not witness it.

**Nothing was retiered silently.** A deployment with no tier table gets byte-identical
behaviour to before this change: one model, every phase, `model_source=None` on records
written outside a phase resolution. Every existing fixture in the suite runs that path.

## Evidence

- `uv run pytest -x -q tests/ci/test_tiers.py tests/ci/test_telemetry.py` — 73 passed.
- `uv run pyright` — 0 errors.
- The wall-clock finding: the first assertion on the envelope comparison failed with
  `assert False is True` on a synthetic run of a few seconds, which is below §1.3's
  2-day floor. The boolean was replaced by the directional measurement and the test was
  rewritten to assert `within is False`, `wall_clock_over_envelope is False`, and
  `"not an overspend" in measurement.detail`.
