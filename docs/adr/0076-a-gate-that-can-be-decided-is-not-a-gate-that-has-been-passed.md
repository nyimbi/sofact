# 0076 — A gate that can be decided is not a gate that has been passed

- **Status:** Accepted
- **Date:** 2026-10-17
- **Related:** FR-009, FR-010, FR-024–FR-035, FR-026, FR-027, FR-105, FR-108, FR-124,
  FR-157, NFR-018, NFR-024, §4.3, §5.1, §5.2, §5.4, §14;
  [ADR-0045](0045-a-topology-is-a-type-and-a-refusal-is-not-a-downgrade.md),
  [ADR-0046](0046-a-module-declares-its-budget-and-p7-measures-the-artefact.md),
  [ADR-0054](0054-the-escape-rate-is-the-one-number-no-producer-authored.md),
  [ADR-0060](0060-the-boundary-is-measured-and-the-ceiling-follows-the-measurement.md),
  [ADR-0061](0061-manufacturing-earns-the-hint-and-withholds-the-number.md),
  [ADR-0074](0074-a-modules-declared-class-outranks-its-phases-tier.md)

## Context

**§5.1** states the whole of admission control in three lines:

```text
admissible(lane) = intent_derivable
                 ∧ oracle_exists
                 ∧ blast_radius_bounded(deployment)

ceiling(lane)    = min( f(oracle_strength),      # §4.3
                        g(blast_bound),          # §5.2
                        h(deployment_isolation)  # §5.4
                      )

level(lane)      = min( ceiling(lane), floor(concerns) )
```

Every term in those lines was a fact this tree already held, and nothing had ever computed
them together. `MODULE_CLASS_CEILING` (§14), `topology_ceiling` (§5.4, ADR-0045),
`lane_ceiling` (FR-023, ADR-0054), `ModuleBudget` (ADR-0046), `DeploymentBoundary`
(ADR-0060) and FR-105's `measured_strength` (ADR-0061) were each built, each tested, and
each read by something that was not this function. The roadmap row said so in six words:
*"§5.1's `admissible(lane)` and `ceiling(lane)` remain uncomputed."*

**The term that was genuinely missing was θ.** FR-009's table maps a measured oracle
strength to a level — at or above θ_hi (0.80) admits L4, at or above θ_lo (0.60) admits L3,
below θ_lo is "L1, oracle is informational only" — and nothing in this build compared
`MutationReport.measured_strength` against anything. FR-105 says a module below θ_lo "must
be reported as unbuildable-at-autonomy and escalated, not built anyway", and the number was
recorded, rendered in the delivery report, and gating nothing. `THETA_GATE_BUILT` was
`False`, which is why `DeploymentScope.admits_l4` refused a third-party L4 target: there
was no instrument, so a declaration would have been doing the gate's work.

**Two requirements in one section are not one fact, and this unit wrote them as one first.**
FR-026 (§5.2) is a *declared number*: "A lane must declare a maximum changed-file count and
a maximum diff size. Exceeding either fails the lane and escalates." FR-027 (§5.2) is a
*level* gate, and its own first three words scope it: "**Autonomy L4 requires** that the
lane's file scope be **declared and enforced by permission**, not merely intended." The first
pass put `boundary.enforced` into `admissible`, which made every lane at a deployment with no
measured boundary inadmissible — and FR-124 says in as many words that such a deployment
still runs: "T1 (dev instance, **no isolation boundary**) runs Mode G at −1 level". A
requirement scoped to L4, enforced at admission, refuses the deployment the spec says runs.

**§5.1 renders a `g(blast_bound)` term and §5.2 supplies no table for it.** The only
computable fact is whether the bound *held*, and FR-026 puts that fact in admissibility. §5.4
agrees from the other side: T4's note calls the blast bound what "unlocks L4 for lanes whose
blast bound previously failed" — an *admissibility* change, not a level change.

## Decision

**§5.1's three lines are computed by `sofact.routing`, and the θ gate they are named for is
now decidable — which is a statement about the instrument and not about any lane.**

1. **`oracle_strength_ceiling(strength) -> AutonomyLevel | None`** reads FR-009's three rows
   as stated, interpolates no L2 row (the spec has none), and returns **`None` for an
   unmeasured strength**. `None` is not `L1`: rounding an absent measurement to the bottom of
   the table reports a lane nobody measured as a lane measured badly, and it would make
   FR-105's escalation fire on the absence of evidence rather than on evidence — NFR-024's
   forbidden reading, one level up.

2. **A lane's strength is its weakest clause's, and `None` if any clause is unmeasured** —
   `Contract.weakest_oracle_rank`'s rule (a lane is only as verifiable as its least
   verifiable part). Averaging over the clauses that *were* measured would report a lane
   strength over a subset nobody chose, so one unmeasured clause makes the lane undecided
   rather than slightly weaker.

3. **`admissible` returns one `RouteTerm` per conjunct, not a boolean.** The three have three
   different remedies — re-elicit the dimension, assign an executable oracle, bring the lane
   inside its declared budget — and a single `False` sends an operator looking for the wrong
   one. The same argument `GateCheck` makes about naming *which* precondition failed. The
   third conjunct is **FR-026's declared budget**, and `within_budget=None` (the lane's sealed
   files could not be read) is not `False`.

4. **FR-027 is applied as `permission_ceiling` on the computed ceiling**, capping at L3
   unless `boundary.enforced`. This is a **narrowing rather than a relaxation**: a lane that
   cannot be confined is still held below the level at which nobody checks its work; it is
   *lowered* rather than *refused*, which is FR-031's own distinction between a silent
   downgrade and a refusal. FR-031's refusal stays where it was, in `topology_refusal`, and
   fires on the topology rather than on the permission half. `enforced` is the predicate
   rather than `writes_confined`, because `enforced` is the credit for both halves (ADR-0060)
   and a scope whose writes are confined while its holdouts stay legible is not a scope
   enforced by permission.

5. **FR-024's raise-refusal lives in `load_concerns_floors`, not in the `min`.** §5.1's third
   line is a `min`, so a declared floor above the built-in one is refused *by name* — the
   requirement forbids "a concerns floor ... used to justify a *higher* level", and a `min`
   would make one harmless rather than rejected, which is not the same act. The built-in
   `CONCERNS_FLOOR` exists so the refusal has something to compare against.

6. **No concern means no floor.** `RouteDecision.concerns_floor` is `None`, not `L0`. §5.1's
   third line has no second operand where no concern applies, so the level *is* the ceiling.
   `CONCERNS_FLOOR` is sparse by design (G7 alone), and defaulting the absence to `L0` would
   invent a floor of zero for every lane §14 names no concern for — which reads a floor
   backwards and collapses the whole ladder to L0.

7. **There is no `g` returning a level, and the absence is stated rather than filled.** The
   bound is the third conjunct of `admissible`; a lane that exceeds it is *refused*, which is
   strictly stronger than the reduction a fabricated `g` would apply, and §5.2 supplies no
   table that would let one be computed. Inventing the table would be this module writing
   policy the spec does not state.

8. **`THETA_GATE_BUILT` is `True`, and `RouteDecision.undecided` is what keeps the two facts
   apart.** The flag means *this build can decide the gate* — it does, from a measured
   strength — and not *this lane passed it*. A lane with no surviving measurement is
   `undecided` on `f(oracle_strength)` and has **no level at all**, which is the state a
   reader must be able to tell from "decided low". `THETA_THRESHOLDS_ENV` reads a calibrated
   θ *pair* from a file, because FR-010 says the built-in numbers are "(assumed)" and must be
   calibrated per language and per repository; a file naming only one of the two is refused
   rather than completed from the defaults, since one threshold from a measurement beside one
   from the defaults would make FR-009's two rows describe two different populations.

9. **`FactoryService.routing_report` reads its inputs from the log, not from the caller.**
   The contract, the *approved* decomposition, the specification and the draft are all read,
   for `check_integration`'s reason: a caller that could supply the clause-to-module map could
   supply one that makes an underivable lane look admissible. A contract with no approved
   decomposition is refused **naming the gate** rather than returning an empty tuple, because
   an empty tuple reads as "every lane is fine". `measured_strength` is off by default, for
   `render_delivery`'s reason — it launches a process per mutant — and with it off every lane
   is `undecided`, which is the honest state rather than a missing feature.

## Consequences

**The ladder is now computable, and most lanes compute to `undecided`.** That is the
intended reading and it is worth stating plainly: with `--measured-strength` off, every lane
reports `no level — f(oracle_strength): no measured strength survived FR-105's floor`. The
`sofact route` verb exits non-zero on that, which is correct — a ladder nobody measured is not
a ladder of zeros. A deployment that wants a decided ladder asks for the measurement, and
FR-105's floor (`MINIMUM_MUTANTS_FOR_A_NUMBER = 5`) means a small module still reports `None`
rather than a rate over three mutants.

**`THETA_GATE_BUILT` moving to `True` admits an L4 target for a third-party scope, and grants
L4 to no lane.** `DeploymentScope.admits_l4` reads the flag, so a third-party deployment may
now declare an L4 ambition — and `route` decides, returning `L4` only for a strength at or
above θ_hi that FR-105 actually measured over a mutant set that cleared its floor. The two
facts the constant must not be read as collapsing are "the instrument exists" and "this lane
passed it".

**FR-027's correction lowers lanes that were being refused.** A lane at a deployment with no
measured boundary, or with a boundary whose probe found nothing, is capped at L3 rather than
found inadmissible. The two cases are kept distinct in the decision's own terms — no probe ran
is *unmeasured*, a probe that found no confinement is *measured and open* — because the
remedies differ: one is to measure, the other to fix what was measured.

**`RouteDecision.concerns_floor` is `None`-able, which moved three call sites.** The field was
`AutonomyLevel` and is now `AutonomyLevel | None`, and `route_statement`'s binding-term
selection had to grow the guard — testing `floor < ceiling` alone would report every
concern-free lane as bound by a floor that does not exist. The type change is the point: an
`L0` default would have been a value the field cannot distinguish from a real floor.

**`routing_report` translates `require_approved_decomposition`'s `ValueError` into a
`RoutingRefusal`.** The gate is FR-061's hard stop and raises `ValueError` for its other
callers; `sofact route` catches `RoutingRefusal` and prints one line, so an unconverted
`ValueError` would reach the operator as a traceback — the failure mode every other verb's
test asserts against.

## What this does not do

**It does not measure a blast radius.** FR-027's T4 note names the blast radius as what T4
unlocks, and `ModuleBudget` remains a number the *proposer declared* (ADR-0046), not one
derived from a measured radius. What is new is that the declared number is now read by the
routing function as well as by P7's check — the same `module_budget_readings` fold, so a lane
is routed against the bound P7 would report on.

**It does not calibrate θ.** FR-010 requires the pair be calibrated against measured escape
data (§12.2) per language and per repository, and no such data exists in this build. The seam
is a file and the defaults say "(assumed)"; a deployment with a calibration declares it.

**It does not route on `intent_derivable` in the sense of *refusing a build*.** The term is
computed and a lane whose intent is underivable is inadmissible with the clause named, but
nothing yet consults the routing decision at dispatch time — the decision is a reading of the
log, reachable through `sofact route`, and the wiring of it into `dispatch_step` is the next
unit's.

**It does not discharge FR-028–FR-035.** FR-028's egress denial and FR-029's "a lane must not
affect the factory's own configuration" are `sofact.boundary`'s measurements — this module
reads the boundary that probe took and does not re-measure it. FR-030's reporting half is
`route_statement`; FR-031's refusal is `topology_refusal`; FR-032–FR-035 are staging and
per-deployment ceilings this unit reads rather than builds. `ROUTING_REQUIREMENTS` names the
four a routing decision can carry out and says why the others are not listed.

## Evidence

**Five canaries, all caught, each reverted from a `cp` file backup with `__pycache__`
cleared.** Two were run in a mutated pair, because the second is the one that distinguishes a
cap from a flattening.

1. `oracle_strength_ceiling`'s `None` branch changed to return `L1` — **5 failed**. This is
   NFR-024's forbidden reading restored, so the gate is watching the thing that would be
   wrong rather than a nearby mutation.
2. FR-024's raise-refusal in `load_concerns_floors` replaced by `if False:` — **1 failed**,
   the refusal by name. The `min` does not reject a raising floor; only the loader does.
3. `permission_ceiling`'s cap removed (return `level` unconditionally) — **3 failed**.
4. `permission_ceiling`'s cap applied unconditionally (return `L3` for every level) — **2
   failed**. Together 3 and 4 are the pair: one canary says the cap does something, the other
   says it does not do *everything*, and a single mutation in either direction passes while
   flattening the ladder.
5. The absent floor defaulted back to `L0` — **5 failed**. This is the original defect
   restored, and it is the one the first test run caught: `test_a_strong_lane_at_l4_is_capped_by_its_class`
   read `L0` where it expected `L2`, and the fix went into the source rather than the
   assertion.
6. `THETA_GATE_BUILT = False` — **6 failed across four suites** (`test_routing`,
   `test_scope`, `test_mutation`, `test_review`), which is the check that the flag is read
   where it is claimed to be read.

After reverting all six: **139 passed** across the five touched suites, and the full suite
**2060 passed, 2 failed** — both failures being the two this unit's own edits had introduced
(see below), each fixed and re-run.

**Two defects the full suite found, both in this unit's own new text.**

`test_no_module_names_a_sofact_verb_this_cli_does_not_have` flagged
`sofact does at routing.py:430`. The comment read *"sofact does not guess at intent"*, and the
scanner read the verb. The fix was to **reword the prose** — "guessing at intent is not
something this factory does" — rather than widen the test's exemption list, which exists for
pre-existing text and not for text written the same day. A gate whose escape hatch is widened
whenever it fires is a gate that has stopped being one.

The README's suite count said 2009 and the run collected 2062. `TestTheSuiteCountIsTheOneThatRan`
is the test whose whole job is to fail when the suite moves and the count does not, and it did.

**One design defect the first test run found, fixed in the source.** The `L0` default in
canary 5 above. The assertion was right and the code was wrong, and the fix is in three
docstrings — `RouteDecision.concerns_floor`, `route`, and the module header's reading 2 —
because the reason the absence is not zero is the thing a later reader would otherwise
re-derive wrongly.
