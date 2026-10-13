# 0047 — The debt is a number, and Mode M's ceiling is not Mode G's

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-158, FR-159, FR-108, FR-086, FR-121, FR-123, NFR-024, R30, D18;
  [ADR-0011](0011-the-factory-refuses-to-claim-maintainability.md),
  [ADR-0040](0040-a-delivery-report-states-five-things-and-its-gate-is-human.md),
  [ADR-0041](0041-a-mode-g-delivery-is-l2-and-the-modules-are-reported-separately.md),
  [ADR-0009](0009-no-oracle-no-autonomy.md)

## Context

ADR-0011 decided that SoFact refuses to claim maintainability, and FR-158 is that decision
written as a requirement. The roadmap recorded FR-158 as **"Not built"** and §3 of the gap
audit recorded the sharper version of the same fact: the ADR's index row
(`docs/adr/README.md`, D18) said "the debt is named and defaulted to total", which reads as
done, while no code computed, stored, or reported an evolvability debt anywhere. The record
was honest two sections later — FR-159 is "specified and **unbuilt**" — so the *record* was
consistent with itself and the *index* was the thing that lied.

The requirement has three clauses and they are three different mechanisms:

> **FR-158** *(refusal)* SoFact must report **evolvability debt** as a first-class debt term
> alongside ground-truth debt (FR-108), whose value in v1 is **1.0 by construction** for
> every module, because no oracle in O1–O8 observes change cost. A debt of 1.0 is the
> correct value, not a measurement failure. Consequently: (a) **Mode M's ceiling is L1**
> until a change-cost oracle exists … (b) Mode G's ceiling is unaffected … and the two
> ceilings **must not be reported as one number**; (c) the delivery report must state that
> maintainability was not verified.

Three questions had to be answered: **what makes the debt "first-class"**, **where the cap
is enforced so it cannot be forgotten**, and **what stops the sentence from being phrased
away**.

## Decisions

### 1. The debt is a number on the report, not a clause inside a sentence

`EVOLVABILITY_DEBT: Final[float] = 1.0` is a module constant, surfaced as
`DeliveryReport.evolvability_debt` — a property, not a field.

A field would be the bug. FR-158 says the value *is* 1.0 in v1; a field of type `float`
with a default is a number a caller can set to 0.4, and the report would then carry a
maintainability claim nothing measured. As a property over a constant, the only value any
report can carry is the requirement's.

The word "first-class" is what makes this a number rather than prose. FR-108's debt is a
*measured* fraction — `ground_truth_debt(contract)`, the clauses no machine can check,
counted off the contract, with `UnverifiedClause.is_ground_truth_debt` marking each one in
the report. FR-158's is the same *kind* of thing and is not the same number. A report
carrying one debt figure would be read as carrying the measurable one, and the unmeasurable
half is the half that bounds what the delivery may claim — so the two are reported side by
side, each named, and the delivery document has a `## Debt` section that states both.

### 2. The sentence interpolates the number

`MAINTAINABILITY_NOT_VERIFIED` is a `ClassVar` on `DeliveryReport` — the mechanism
ADR-0040 established for FR-086's `VERIFIED_NOT_VALUE`, and for the same reason: a free-text
field lets a report state the qualification in a sentence of the author's choosing, and the
failure FR-158 corrects is not a report that *omits* the sentence, it is one that says
something adjacent and flattering about a green suite.

The sentence formats the constant (`{EVOLVABILITY_DEBT:g}`) rather than restating "1.0".
Two statements of one fact drift, and the drift here would be invisible because both would
read as correct English — the argument ADR-0042 makes about a module's Definition of Done,
one artefact along. A test asserts the interpolation, so a future edit that changes the
number without the sentence fails.

### 3. Mode M's ceiling is a separate constant, and the lane type refuses to exceed it

`MODE_M_CEILING = AutonomyLevel.L1`, beside the existing `MODE_G_CEILING = L2`. FR-158(b)
says the two "must not be reported as one number", and a second constant is the cheapest
honest way to say that — the alternative, a single `ceiling` with a mode parameter, is a
number that reads as one number.

The cap is enforced **on the type**, in `MaintenanceLane._a_lane_names_itself`. A caller who
had to remember to clamp is a caller who can forget, which is the failure mode a refusal
exists to close.

The interesting case is §13, whose table gives L01 (dependency bumps) and L04 (test repair)
an **L4**. Those are Mode M levels — the level at which the maintenance lane's own work
would run — and that is a genuinely different claim from the level at which the delivery may
be *maintained*. FR-158(a) refuses the second, so `delivery.handover` clamps every lane with
`min(ceiling, MODE_M_CEILING)`, and the L00 fallback lane is clamped the same way. §13's
table and FR-158's cap stay two statements of two things.

The clamp lowers; it does not drop. A cap that removed the lane would report a system with
no maintenance story at all, which is a different and false claim, and the test asserts the
handover is not emptied.

### 4. The delivery report and both rendered artefacts state the refusal

FR-158(c) says "the delivery report must state that maintainability was not verified". The
report is a pydantic type; the two documents `sofact.writing` renders are what an operator
actually reads. A sentence the report carries and the documents drop is a statement nobody
sees, so `render_delivery_document` and `render_runbook` both emit it, `DELIVERY_HEADINGS`
gains `Debt` (the constant is asserted at the end of every render, so a section cannot go
missing quietly), and `sofact deliver` prints it on the same screen as the lanes — an
operator shown L01 at §13's L4 and not told about the cap would discover it at the gate.

### 5. The check reports rather than fails

`maintainability_not_verified` is a `GateCheck(passed=True)`, and it names both ceilings as
two numbers, which is where FR-158(b)'s "must not be reported as one number" is discharged
in the machine-readable half.

It cannot fail, and that is not a weakening. FR-158 makes the debt *structural*: every
delivery carries it, because no delivery has a change-cost oracle. A check that failed would
refuse every delivery the factory can ever produce, and a gate that cannot pass is one an
operator learns to bypass — which turns off the checks that do matter. The requirement's own
word is "report", and the report is what an operator reads.

## Alternatives refused

- **An `evolvability_debt: float` field on `DeliveryReport`.** Refused in Decision 1: a
  settable number is one a caller can set below 1.0, and the report would then carry a
  maintainability claim nothing measured.
- **Fold the debt into FR-108's ground-truth count.** Refused in Decision 1: they are one
  kind of thing and not one number — FR-108's is measured, FR-158's is not, and a reader who
  saw one figure would take the measurable one for the whole.
- **Restate "1.0" in the sentence instead of interpolating the constant.** Refused in
  Decision 2: two statements of one fact drift, and this pair would drift silently.
- **One `ceiling` with a mode parameter.** Refused in Decision 3: FR-158(b) says the two must
  not be reported as one number, and a parameterised single number is one number.
- **Clamp at the call sites that build a handover.** Refused in Decision 3: a caller who must
  remember is a caller who can forget.
- **Drop a lane whose §13 level is above the cap.** Refused in Decision 3: a handover with no
  lane reports a system with no maintenance story, which is a different and false claim.
- **Leave §13's table alone and report the cap only in the check.** Refused in Decision 3:
  the handover is FR-121's machine-readable input to Mode M, so a lane reaching it at L4 is a
  maintenance claim at L4 whatever the report says.
- **Make the check fail.** Refused in Decision 5: it would refuse every delivery, and a gate
  that cannot pass gets bypassed.
- **Raise `MODE_M_CEILING` now.** Refused: FR-158(a) makes the value a *consequence* of the
  absent oracle. A deployment that raised it without building FR-159's instrument would be
  claiming a measurement it never took (NFR-024), and D18 is the decision that owns the
  question.

## Consequences

- `EVOLVABILITY_DEBT` and `MODE_M_CEILING` are constants in `views.py`;
  `DeliveryReport.evolvability_debt` and `.maintainability_statement` are properties.
- `MAINTAINABILITY_NOT_VERIFIED` interpolates the debt constant, so the sentence and the
  number cannot disagree.
- `MaintenanceLane` refuses a ceiling above the cap; `delivery.handover` clamps §13's L4
  lanes and the L00 fallback.
- The `maintainability_not_verified` check reports the refusal and both ceilings; the
  delivery document gains a `## Debt` section; the runbook states the number in "Not
  covered"; `sofact deliver` prints both.
- FR-158 leaves the roadmap's gap list. **FR-159's differential change-cost oracle is still
  unbuilt and D18 is still open** — that is the decision ADR-0011 deliberately left open, and
  nothing here resolves it. What changed is that the *disclosure* half is now enforced by the
  type rather than asserted in a record.
- §3's first doc-versus-code discrepancy is closed: the index row that read as "done" now
  describes something the code does.
