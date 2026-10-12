# 0039 — The envelope refuses a ceiling, reports a floor, and names what it cannot measure

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-057, NFR-025, FR-118, FR-160, FR-087, FR-125, ADR-0025,
  ADR-0038; [ADR-0005](0005-no-container-runtime.md)

## Context

§1.3 states the delivery envelope as a table of eight dimensions and then makes two
requirements of it that are different in kind. **FR-057** is a refusal: "must refuse a
goal whose decomposition exceeds the envelope, and must say which dimension was
exceeded". **NFR-025** is a measurement: "must be configuration, and every delivery
must report actuals against it. The envelope is a hypothesis under test."

Neither was built. `ENVELOPE` appeared nowhere in `src/`, so every goal was accepted
however large, and FR-118's fifth required statement — "the actuals against the §1.3
envelope" — had nothing to report against. P8 is the gap this unblocks.

Four things about the requirement decide the design.

**§1.3 says its numbers are "targets, not measurements", and the two ends are not the
same claim.** A delivery *above* a ceiling is the over-scoped goal FR-057 refuses. A
delivery *below* a floor is a small project — which §1.4's whole argument says the
factory should be able to build, because gates are per-platform and the economics
improve with size only *given* that the envelope holds. A gate that failed on the floor
would refuse to build anything smaller than a platform.

**NFR-025 makes the envelope configuration, and §1.3 calls it "a hypothesis under
test".** A factory that applied §1.3's numbers without anyone choosing them would
report actuals against a hypothesis its operator never adopted, and refuse over-scoped
goals against numbers nobody set. Configuration is therefore the seam, and *unset* is a
state — not the same as "the defaults".

**Only four of the eight dimensions are decidable when P3 runs.** Modules come from the
decomposition. External integrations are the G6 modules, which §14 defines as external
integration adapters. Human gates are §3.3's four. The value hypothesis is P2's. The
other four are not missing by oversight: nothing in the log declares a *system* (§7.2
has the decomposition map clauses to modules, and §1.3 counts systems), nothing reads
delivered source to count lines (ADR-0025 leaves the target language open, so SoFact
does not know what a source file is), and human-minutes and wall-clock are outcomes of
a build rather than facts about a plan.

**A missing measurement is the one default that fails open.** A dimension nothing
measures, reported as inside the envelope, is indistinguishable from a satisfied one —
the same failure ADR-0038 refused for an absent verdict, one phase later.

## Decision

**§1.3's eight dimensions are a type; a bound over its ceiling fails P3's gate and a
bound under its floor is reported; a dimension nothing measures reads as unmeasured and
names what would be needed; the envelope is loaded from JSON and unset is not the
default.**

1. **`DeliveryEnvelope` is a type with eight fixed fields, defaulting to §1.3's table
   verbatim.** Fixed fields rather than a mapping, so `extra="forbid"` makes a config
   file naming a dimension this build does not know a refusal rather than a setting that
   is silently ignored. The defaults are written out rather than derived because
   NFR-025 calls the envelope a hypothesis under test: a deployment may widen or narrow
   it, but the factory's own default may not quietly differ from the spec's stated
   target, or an operator comparing a delivery against §1.3 would be comparing it
   against numbers the factory never used.
2. **`EnvelopeDimension` names the eight, so a measurement can name one back.** FR-057
   requires the refusal to say *which* dimension was exceeded, and a dimension named by
   a free string is one a report can misspell while still reading as complete.
3. **A bound carries `minimum` and `maximum` as separate fields.** They are not the same
   kind of claim — see the Context — and keeping them apart is what lets the gate refuse
   one and merely report the other. `exceeded_by` and `below` are separate predicates for
   the same reason; a single `admits` would collapse the distinction at the first call
   site that needed only one answer.
4. **A bound with neither end is refused by the type.** An unbounded dimension belongs
   out of the envelope, not in it with two empty fields, where a reader counts it as a
   dimension that was checked. A range whose floor is above its ceiling is refused too:
   no delivery could be inside it, so it is a bound that bounds nothing while looking
   configured.
5. **FR-057's check lives in P3's gate, and it is the only check there that can fail for
   a reason outside the decomposition's own soundness.** The decomposition is the first
   artefact that says how big the platform will be; a refusal at P8 would be a refusal
   after the build, and §1.3's own words are "must be split by the operator, not silently
   attempted".
6. **Over a ceiling fails; under a floor passes and is reported.** See the Context. The
   passing detail names the dimensions below their floor and the ones left unmeasured,
   because a green check whose text said only "within the envelope" would read as a
   claim about all eight.
7. **`EnvelopeMeasurement` moves `actual` and `within` together, and the type recomputes
   the judgement.** `actual is None` means nothing SoFact holds measures the dimension
   and `within` is then `None`. A half-measurement — an actual with no verdict, or a
   verdict with no actual — is refused at construction, and so is a `within` that
   disagrees with the bound's own `admits`. A caller's arithmetic is not a guard.
8. **`is_within` is a claim about the *measured* dimensions only.** The unmeasured ones
   are `EnvelopeActuals.unmeasured`, named separately. A report that printed the boolean
   alone would read as "the delivery is inside the envelope" while four dimensions were
   never looked at.
9. **Every unmeasured dimension carries a work item.** Each names what would have to
   exist before anything could be counted — a declared artefact root, a gate that
   records its cost, a system tier — rather than an apology. A reader of the delivery
   report has to be able to act on it.
10. **`load_envelope` merges per dimension, not per field.** An operator raising one
    ceiling should not have to restate the other seven, and a floor they did not mention
    must survive — dropping it would widen the envelope by omission, which is the one
    direction an envelope must not drift. Supplying a ceiling below the surviving floor
    then reaches the bound type, which refuses the empty range with its own sentence.
11. **An unknown dimension name and an unknown field within one are both refused.** A
    typo that changes nothing and reports success is the failure mode a config seam has.
    `extra="forbid"` on the type cannot catch the first, because the key never reaches
    it.
12. **`FactoryService(envelope=...)` defaults to `None`, and `None` means no envelope.**
    Not "the defaults". With none, FR-057's check passes and says it measured nothing;
    the CLI resolves `SOFACT_ENVELOPE` the way it resolves `SOFACT_HARNESS_SPECS`
    (FR-156's precedent), and `sofact envelope --defaults` prints §1.3's numbers without
    applying them.
13. **The value hypothesis has three states in `measure`, not two.** `None` means the
    caller did not read the specification, and the dimension is then unmeasured rather
    than counted as zero. P3's gate does not read the specification for any other
    purpose, so a two-state flag would make every P3 run report a missing value
    hypothesis — a measurement of the caller's silence, printed as a fact about the
    project.
14. **`_gate_decomposition` is one function because there are two call sites.**
    `decompose` gates and `approve_decomposition` *recomputes*, and a recomputation that
    passed different arguments would make FR-057 a gate with a bypass: the refusal
    printed by `decompose` and then overridden by the approval it exists to stop. This
    is the same reasoning as the recomputation itself, one level up, and the CLI test
    that found it is in Evidence.
15. **The measurement reads declarations, never code.** Module count is
    `len(decomposition.modules)`; integrations are the G6 modules; gates are
    `len(PHASE_GATE)`. A number obtained by looking at a workspace would be a number
    about something the factory did not decide (ADR-0025).

## Alternatives refused

* **Fail the gate on a dimension below its floor.** Refused in decision 6. §1.3's
  numbers are targets, and §1.4's argument is that the factory's economics improve with
  size *provided the envelope holds* — not that small deliveries are defects. A gate
  that refused to build a three-module service would refuse the work that earns the
  trust to attempt a twenty-five-module one.
* **Apply §1.3's defaults when no envelope is configured.** Refused in decision 12.
  NFR-025 calls the envelope a hypothesis under test; applying it without adoption would
  report actuals against numbers nobody chose and refuse goals against them.
* **Report an unmeasured dimension as within.** Refused in decision 7. It is the default
  that fails open, and the one a delivery report can least afford — four of the eight
  dimensions are unmeasured today, so the report would be mostly assertion.
* **Invent a system count from the module classes.** Refused in decision 15 and the
  Context. §14's classes are module *types*, not system boundaries, and a G1/G2/G3 split
  read as three systems would be the factory drawing a boundary the operator never drew
  — which FR-087 makes the operator's act.
* **Count delivered LOC by reading the workspace.** Refused: ADR-0025 leaves the target
  language open, so SoFact does not know what a source file is, and any count would be a
  number about a tree it did not choose. The dimension names the missing artefact root
  instead.
* **A mapping field instead of eight fixed fields.** Refused in decision 1. A mapping
  accepts a dimension this build does not know, and the report then omits a dimension
  §1.3 bounds while reading as complete.
* **Merge a partial override per field, letting an omitted floor be dropped.** Refused
  in decision 10: it widens the envelope by omission.
* **A `minimum`/`maximum` pair collapsed into one `admits`.** Refused in decision 3.
  The refusal and the measurement are different answers to different questions, and one
  predicate would force a caller to re-derive which it meant.
* **Store the actuals in the ledger.** Refused: actuals are derived from the log, like
  every other fact about it. A stored row could disagree with the log it claims to have
  read.

## Consequences

* **FR-057 and NFR-025 move from Not built to Implemented**, and FR-118's fifth
  statement now has an artefact to report from. P8's remaining work — the delivery
  report, the deploy gate, the handover — is unblocked on the envelope half.
* **P3's gate gains a check that can fail for a reason the decomposition cannot fix.**
  The repair is to split the goal, which is the operator's act, and the check says so.
  A project run with no envelope configured is unaffected: the check passes and reports
  that it measured nothing.
* **The delivery report will be mostly unmeasured, and says so.** Four of eight
  dimensions name what would have to exist. That is the honest state and it is a work
  list: FR-160's gate-cost measurement, a declared artefact root, and a system tier.
* **`sofact envelope` is a new verb**, and `SOFACT_ENVELOPE` a new configuration seam
  following `SOFACT_HARNESS_SPECS`.
* **`tests/ci/synthetic.py`'s `synthetic_service` gains an `envelope` parameter
  defaulting to `None`**, so the suite's default remains the unconfigured path rather
  than silently adopting §1.3's numbers.

## Evidence

* `src/sofact/views.py` — `EnvelopeDimension`, `DimensionBound` (with
  `_a_bound_bounds_something`), `DeliveryEnvelope`, `EnvelopeMeasurement` (with
  `_an_unmeasured_dimension_is_never_within`), `EnvelopeActuals`; the five new `__all__`
  entries.
* `src/sofact/envelope.py` (new) — `load_envelope`, `measure`, `MEASURED_AT_P3`,
  `UNMEASURED_AT_P3`.
* `src/sofact/decomposition.py` — `gate`'s two new keyword parameters and
  `_envelope_check`.
* `src/sofact/service.py` — `envelope=`, `envelope()`, `_gate_decomposition`, and the
  two call sites that now share it.
* `src/sofact/cli.py` — `_configured_envelope`, the `envelope` verb, `_print`-style
  actuals output, and `SOFACT_ENVELOPE`.
* `tests/ci/test_envelope.py` — 31 tests across four classes: the bounds, the
  measurements, the configuration seam, and FR-057's refusal.
* `tests/ci/test_cli.py::TestTheEnvelopeVerb` — 7 tests, including the one that found
  the bypass: `test_the_p3_gate_refuses_an_over_scoped_decomposition` failed with
  `assert 0 == 1` because `approve_decomposition` recomputed the gate without the
  envelope and approved a decomposition `decompose` had just refused. Decision 14 is
  that finding.
* **Canaries**, each with the target string asserted present before the patch and the
  file restored from `/tmp/envelope.py.bak` / `/tmp/decomposition.py.bak` rather than
  from git:
  * `measure`'s unmeasured branch given `actual=0.0` — three tests failed, including
    `test_an_unmeasured_dimension_names_what_would_be_needed`, which is the fail-open
    default this ADR exists to refuse.
  * `_envelope_check`'s `if exceeded` short-circuited with `and False` — three tests
    failed, including `test_the_service_refuses_at_p3_when_the_envelope_is_exceeded`.
* The first canary also exposed a **vacuous assertion** in the test it failed:
  `test_an_unmeasured_dimension_names_what_would_be_needed` asserted inside a loop over
  `actuals.unmeasured`, so an empty set passed it. It now compares the dimension set
  before the loop. A loop that asserts only over its own iterable is a test that passes
  when the collection is empty, which is exactly when it should fail.
* `tests/ci` at this commit: **902 passed, 0 failed** (one `git worktree add` flake on
  the first run, passing on rerun and unrelated to this diff). `pyright`: 0 errors.
  `ruff check` and `ruff format --check`: clean.

## References

* FR-057 (the refusal), NFR-025 (the envelope is configuration and actuals are
  reported), FR-118 (the delivery report's five statements, the fifth being the
  actuals), FR-160 (gate cost is measured), FR-087 (machine-proposed,
  human-validated), FR-125 (the class distribution as a quality signal), §1.3, §1.4,
  §3.3, §14.
* [ADR-0025](0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md) —
  why the target language is open, and therefore why delivered LOC is unmeasured.
* [ADR-0038](0038-a-system-criterion-spans-clauses-and-its-verdicts-are-the-worst.md) —
  the same "an absent reading is not a satisfied one" rule, applied to verdicts.
* [ADR-0005](0005-no-container-runtime.md) — the packaging decision P8's deployable
  artifact still depends on.
