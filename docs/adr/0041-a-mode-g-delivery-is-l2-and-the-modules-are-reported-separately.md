# 0041 — A Mode G delivery is L2, and the modules' number is reported separately

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-123, FR-122, FR-007, FR-125, FR-126, FR-118, FR-157, §1.5, §2.3,
  §3.2, §3.3, §14; [ADR-0040](0040-a-delivery-report-states-five-things-and-its-gate-is-human.md),
  [ADR-0005](0005-no-container-runtime.md)

## Context

**FR-123** is the most emphatic requirement in §12 and it was the only one in that
section with nothing behind it:

> The **maximum end-to-end autonomy of a Mode G delivery is L2**, because P2 and P3 are
> human gates and P8 is a human gate. Individual modules may run at L4 internally; the
> *delivery* is L2. **SoFact must report this distinction explicitly and must never
> report a Mode G delivery as L3 or L4.**

Two clauses, and the second is the harder one. The first is a cap. The second is a
requirement to report a *distinction* — and the requirement's own justification says
why: "the alternative is a false claim, and false claims about autonomy are how this
class of product destroys trust."

ADR-0040 built `delivery.ceiling` as the minimum of the contract's measured ceiling
(FR-007, from the weakest oracle rank) and every module class's
(`MODULE_CLASS_CEILING`, FR-125/FR-126). That computes FR-122's number correctly and
enforces none of FR-123's: a contract of rank-1 oracles admits L4, and the report said
L4. The roadmap audit recorded this as the one place where "the spec's most emphatic
honesty requirement is unenforced".

The synthetic pipeline makes the gap concrete. Its fixture — four clauses, classes G4,
G5, G7 and G8 — has a contract ceiling of **L3** and a module minimum of **L1**. Under
ADR-0040 the report said L1, which is FR-123-compliant by luck: the G7 clause (a
password-reset flow, which FR-126 caps at L1) happened to be the lowest thing in the
delivery. A fixture with no G7 clause would have reported L3, and the cap would have
been broken without anything failing.

## Decision

1. **`MODE_G_CEILING` is a constant on the type, `AutonomyLevel.L2`.** FR-123's number
   is not computed, because it is not a measurement: it follows from P2, P3 and P8
   being human gates (§3.3), which is a fact about the pipeline rather than about any
   particular delivery.

2. **The cap is applied last and unconditionally in `ceiling`** — including when the
   decomposition is `None`. A cap that failed open on missing input would be no cap:
   the decomposition is the *lowering* half of FR-122 and the ceiling is the *capping*
   half of FR-123, so the second has to hold when the first has nothing to say.

3. **`module_autonomy` is a separate function, and both numbers are fields of
   `DeliveryReport`.** FR-123 asks for the distinction, and one number cannot state one.
   A report carrying only the capped value would read as a pipeline that cannot build
   above L2 — which is a different claim from "the delivery is L2" and a false one.

4. **The pair is reported at the CLI and as a gate check.** `sofact deliver` prints
   `autonomy:` and `modules:` on consecutive lines with the sentence that joins them —
   §2.3's "autonomous module construction inside a human-validated architecture".
   `autonomy_capped_for_mode_g` is a check on the report so the pair is in the artefact
   the deploy gate presents, not only on the operator's terminal.

5. **`ceiling` asserts the contract has clauses.** `module_autonomy` reads
   `contract.ceiling`, which reads `weakest_oracle_rank`, which is `max()` over an empty
   sequence — so an empty contract would raise `ValueError` from the standard library
   rather than from SoFact. The assertion names the real precondition.

6. **The cap is a cap, not a floor.** A delivery whose weakest module class is G7
   reports L1, below `MODE_G_CEILING`. FR-123 says "maximum", and a rule written as "the
   delivery is L2" would report the flattering number for a delivery that has not
   earned it. `test_a_g7_module_does_not_raise_the_delivery_to_the_cap` pins this.

7. **A constant rather than a mode-keyed table.** Every report this build can render is
   a Mode G report: §1.2 defines Mode G as "a goal, no codebase", the pipeline is P0–P9,
   and no Mode M entry point exists. A table keyed by mode with a default would be a cap
   that fails open on a mode nobody has written yet — the one failure a cap may not have.
   When a Mode M pipeline exists this becomes a lookup and the type will force the
   change, because `MODE_G_CEILING` will be one arm of an exhaustive `match`.

## Alternatives refused

1. **Compute the cap from the phase table.** §3.2 gives each phase an autonomy band
   (P0 L1, P1 L2–L3, P2/P3 gate, P5 L3–L4, P6 L4, P8 gate) and a minimum over the bands
   would land near L2 anyway. Refused because the bands are ranges, not numbers: P5 is
   "L3–L4" and P1 is "L2–L3", so the minimum is a range and the report would have to
   pick an end of it — which is exactly the judgement FR-123 has already made and does
   not want remade per delivery. It is also the *other* requirement: FR-122 asks for
   per-phase autonomy, which remains unbuilt and is recorded as such.

2. **One `autonomy` field carrying the capped number, with the modules' number in the
   check detail only.** Refused: FR-118's first statement is a *field* on the report
   because a sentence is the easiest place for a qualification to go missing, and this
   is the same argument. The distinction is the requirement's second clause, so it is a
   field.

3. **Report the modules' number and state the cap in prose.** Refused, and it is the
   tempting one, because it is what the spec's own wording invites: "the *delivery* is
   L2" italicises the delivery as the thing being named. But a prose cap is a claim
   nothing checks, and the whole defect this ADR closes is a requirement whose second
   clause had no code behind it. The cap is a value with a check; the distinction is
   what prose is for.

4. **Apply the cap inside `DeliveryReport` as a validator.** Refused: the type would
   then have to know that a report is a Mode G report, which it cannot — nothing in the
   log declares a mode. A validator that assumed one would be wrong the day a Mode M
   report is rendered, and would refuse a legitimate L4 maintenance report. The cap
   belongs where the mode is known, which is the pipeline that produced the delivery.

5. **Name the constant `MODE_G_L2`.** Refused for the reason
   `STRONG_ORACLE_MAX_RANK` is not named `TWO`: the name should say what the number *is
   for*, and a future Mode M ceiling beside it would make the bare number ambiguous.

## Consequences

- **FR-123 is enforced rather than asserted.** The cap holds with or without a
  decomposition, and the canary confirms the tests fail without it: removing
  `min(…, MODE_G_CEILING)` from `ceiling` fails `test_a_delivery_is_never_above_l2` and
  `test_the_cap_applies_with_no_decomposition`, and leaves the other 67 passing — so the
  tests are scoped to the requirement rather than to the function.

- **The delivery number will usually be lower than the modules' number, and sometimes
  much lower.** The synthetic fixture reports L1 for both because of its G7 clause. A
  delivery of strong oracles with no G7 module reports L2 for the delivery and L4 for
  the modules, which is the sentence FR-123 wants an operator to read.

- **FR-122's per-phase half is still unbuilt**, and this ADR does not close it. What it
  closes is the half of FR-123 that names a number; the half that says "per phase"
  belongs to FR-122 and needs the phase bands to be ranges resolved into numbers, which
  is a design decision this record deliberately does not take (alternative 1).

- **The cap is not a topology ceiling.** FR-124's T1/T2 per-deployment ceilings would
  lower this number further, and they remain unbuilt — there is no deployment topology
  type for them to attach to. A delivery reported at L2 today is L2 *before* any
  deployment ceiling applies, and §12's T1 case ("dev instance, no isolation boundary,
  Mode G at −1 level") would make it lower still.

- **Nothing distinguishes a Mode G delivery from any other at the point the number is
  computed**, and this is a real limitation of decision 7 rather than a solved problem.
  It is acceptable only because no other mode can currently produce a report.

## Evidence

- `src/sofact/views.py` — `MODE_G_CEILING`, added to `__all__`; `DeliveryReport.autonomy`
  re-documented and `DeliveryReport.module_autonomy` added.
- `src/sofact/delivery.py` — `module_autonomy` split out of `ceiling`, the cap applied
  last, the `autonomy_capped_for_mode_g` check, both values passed to the report.
- `src/sofact/cli.py` — `sofact deliver` prints the pair.
- `tests/ci/test_delivery.py` — `TestTheModulesCeiling` (4 tests, FR-122's half, renamed
  from `TestTheCeilingIsTheLowerBound`) and `TestTheModeGCap` (5 tests), one of which
  renders a real report through a real service and asserts the pair reaches the artefact.
- **A canary**, with the target string asserted present before the patch and the file
  restored from `/tmp/delivery.py.bak` rather than from git: `ceiling`'s return changed
  from `AutonomyLevel(min(module_autonomy(contract, decomposition), MODE_G_CEILING))` to
  `module_autonomy(contract, decomposition)`. `test_a_delivery_is_never_above_l2` and
  `test_the_cap_applies_with_no_decomposition` failed; 67 passed.
- Measured on the synthetic fixture before the change: contract ceiling **L3**, module
  classes G4/G5/G7/G8, report **L1** — compliant by accident, which is what motivated
  decision 2's unconditional application.
- `tests/ci` at this commit: **982 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

- FR-123 (the L2 cap and the distinction), FR-122 (per phase and per module, lower
  governs), FR-007 (the weakest oracle sets the ceiling), FR-125/FR-126 (module classes,
  G7 human-authored), FR-118 (the report's statements), FR-157 (deployment-scoped
  autonomy target), FR-124 (per-deployment topology ceilings, unbuilt), §1.5 (L5 and
  autonomous deploy are not-goals), §2.3 (the honest headline), §3.2 (the phase bands),
  §3.3 (why four gates), §14 (the lane classes)
- [S16](../sources/s16-shapiro-autonomy-ladder.md) — the autonomy ladder L0–L5
- [ADR-0040](0040-a-delivery-report-states-five-things-and-its-gate-is-human.md) — the
  delivery report this cap is applied to
