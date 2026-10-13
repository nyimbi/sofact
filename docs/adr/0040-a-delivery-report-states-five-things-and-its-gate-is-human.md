# 0040 — A delivery report states five things, its gate is human, and its checks are scoped to what the factory owes

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-117, FR-118, FR-119, FR-120, FR-121, FR-086, FR-108, FR-122,
  FR-123, FR-124, FR-126, FR-082, §1.5, §11, §13, §14;
  [ADR-0004](0004-delegate-the-coding-loop-to-an-external-harness.md),
  [ADR-0005](0005-no-container-runtime.md),
  [ADR-0039](0039-the-envelope-refuses-a-ceiling-and-reports-a-floor.md)

## Context

§11 is P8: FR-117 (a deployable artifact, infrastructure-as-code, a runbook and a
delivery report carrying the traceability chain from intent clause to deployed
component), FR-118 (five statements the report must make), FR-119 (a human, permanent
deploy gate presenting the report), FR-120 (a machine-usable API surface), and FR-121
(Mode M handover). None of it was built. `DeliveryReport` appeared nowhere in `src/`,
and the pipeline ended at P7's integration report with no artefact saying what had
actually been delivered.

The gap was blocked on two things. One was FR-118's fifth statement — "the actuals
against the §1.3 envelope" — which had nothing to report against until ADR-0039 built
FR-057 and NFR-025. The other was the packaging decision FR-117's "container image or
equivalent" depends on, and that one is still open: ADR-0005 refuses to assume a
container runtime, and FR-124 makes a deployment's topology a per-deployment decision.
P8 could therefore be built only in part, and the part that could not be built had to be
*reported* rather than quietly omitted.

Five things about the requirements decide the design.

**FR-118's five statements are not equally comfortable.** "Requirements were verified,
not value" (FR-086) is the one that makes a report read as less than a guarantee. "Which
clauses are unverified" (FR-118's second bullet, FR-108's ground-truth debt) is the one
that makes the factory look bad. A report is the artefact an operator reads under time
pressure, and prose is the easiest place for a qualification to go missing.

**FR-117 asks for four artefacts and SoFact can produce two.** A runbook and the
delivery report itself are files the factory writes. A deployable artifact needs a
packaging decision, and infrastructure-as-code needs a named target environment. Both
are the operator's calls, made at the deploy gate rather than at P3.

**FR-118 asks for the oracle "at which measured strength", and nothing measures one.**
`OracleDeclaration.rank` is a declaration the operator made; no mutation score is
computed anywhere in SoFact.

**FR-119's gate is permanent, which is a statement about what a gate may show.** A gate
that approved one report and displayed another is the stale-evidence mistake FR-006
refuses one phase earlier.

**FR-121's composition claim — "the output of Mode G is a valid input to Mode M" — is
only checkable if the handover is an artefact.** §13's maintenance lanes (L01-L12) are a
different taxonomy from §14's module classes (G1-G8): a lane says what kind of
maintenance work something is, and a class says what a module *is*.

## Decision

**P8 renders a report whose five statements are five required fields; FR-086's sentence
is a constant on the type; the traceability chain draws its gaps; a measured strength
that does not exist is reported as declared; the deploy gate names the report it
approved and is passed only by a person; and the artefact check is scoped to what the
factory owes.**

1. **`DeliveryReport`'s five statements are five fields, and the type refuses a report
   that omits one.** `artifacts` and `chain` for FR-117, `verified` and `unverified` for
   FR-118's first two bullets, `unvalidated_assumptions` for the third, `handover` for
   FR-121, `envelope_actuals` for the fifth. `_the_five_statements_are_whole` refuses an
   empty chain, an empty artefact list, two artefacts of one kind, an empty check list,
   and a handover with no lane. A field cannot be forgotten the way a paragraph can.

2. **FR-086's sentence is a `ClassVar`, not a field.** `VERIFIED_NOT_VALUE` is the only
   string the report will produce for it, and `value_statement` returns it. A free-text
   field would put the claim back in the hands of whatever built the report; a constant
   makes it unavailable to every code path. That is the difference between a report that
   *says* the factory did not certify value and one *written by* a factory that could
   not have.

3. **An absent artefact carries a reason, and presence is a filesystem fact.**
   `DeliveryArtifact` requires `path` when `present` and `missing_because` when not,
   refusing both mismatches. `artifact()` looks for the file; it does not accept a
   declaration. A caller that could declare an artefact present would make the report's
   most load-bearing field an assertion — the failure FR-112 already refuses one phase
   earlier by diffing a declared surface against a built one.

4. **The two artefacts SoFact does not produce carry a reason each, and are separated
   from the missing ones.** `UNPRODUCIBLE` names the image (a packaging decision, T2
   open) and the IaC (a named environment, FR-124). `DeliveryReport.undecided_artifacts`
   and `.missing_artifacts_factory_owes` split the missing set, because the two need
   different responses: a missing runbook is work the factory owes and a missing image is
   a decision the operator has not taken.

5. **The artefact check is scoped to what the factory owes.** A check over all four
   FR-117 kinds can never pass, and a gate that cannot pass is one an operator learns to
   bypass — which turns off the part of the check that does matter. The refusal is
   real, not disabled: a delivery root with nothing in it fails the check and the verb
   exits non-zero. `undecided_artifacts_stated` reports the other two rather than
   failing, and says why.

6. **The traceability chain draws its gaps rather than shortening.** `TraceLink` keeps
   every hop as `| None` — clause to requirement (P2), requirement to module (P3), module
   to the step that built it (P5) — and `is_whole` is the conjunction.
   `broken_links` counts them. A walk that stopped at the first missing hop would return
   a shorter chain, and the report could not tell that from a contract with fewer
   clauses.

7. **A clause is verified only on `SATISFIED`.** `INSUFFICIENT` and `VIOLATED` are both
   unverified — the second is worse, not better — and the reason says which, because
   "the oracle ran and could not decide" and "the oracle was never run" need different
   repairs. `UnverifiedClause.is_ground_truth_debt` is `outcome is None`, which is
   FR-108's debt fraction one phase later.

8. **A measured strength that does not exist is reported as declared.**
   `VerifiedClause.measured_strength` is `None` and `measured` says which it is;
   `rendered` prints "declared rank N, not measured" rather than the declared rank under
   the word "measured", which is the exact euphemism FR-118 forbids.

9. **Every P2 assumption is reported, unfiltered.** FR-118 says "every assumption from
   P2 that remains unvalidated", and nothing in SoFact validates one — FR-079 makes an
   assumption falsifiable by naming its refuting observation and nothing runs that
   observation. A filter here would be the factory asserting a validation it never
   performed.

10. **The report carries FR-121's handover as a field.** A handover rendered from the
    contract at some other time could be rendered from a contract this delivery was not
    verified against, and FR-121's claim is a claim about *this* delivery.

11. **The handover's lanes are §13's, not §14's.** `LANE_ORACLE_KEYWORDS` matches a
    contract clause to a lane by the clause's own words, the same shape
    `decomposition.classify` uses one phase earlier. L11 (adversarial audit) is included
    because §13 retains it; L12 (self-maintenance) is not, because a lane that maintains
    SoFact is not a lane for the delivered system.

12. **Every lane inherits every contract clause's oracle.** A maintenance run does not
    know in advance which clause its change touches, so a lane handed only the oracles
    that mention its own keywords would be missing the ones its regression needs — which
    is the failure mode a maintenance mode exists to avoid. The keyword table decides
    which *lanes* exist; the oracles are the whole contract's.

13. **A contract matching no lane gets one lane carrying the whole contract.** The type
    refuses a handover with no lane, and the honest answer for a contract stating no
    maintenance obligation is one lane without a §13 identifier — inventing one for work
    §13 does not describe would be worse than an `L00`.

14. **`InheritedOracle` references the clause rather than copying its oracle, and
    `Handover.inherited_oracles` is derived from the lanes.** Two statements of one fact
    is how a handover comes to disagree with itself about what the delivered system can
    check. `unmaintainable` is the inherited oracles naming no command: the delivered
    system's ground-truth debt, counted where it actually reaches Mode M.

15. **Autonomy is the lower of the contract's ceiling and every module class's.**
    FR-122 makes the lower number govern and there are two bounds:
    `Contract.ceiling` from the weakest oracle (FR-007) and `MODULE_CLASS_CEILING` on
    each module's class. A delivery reporting the contract's ceiling alone would claim an
    autonomy a G7 module forbids, because FR-126 makes auth, secrets, payments and PII
    human-authored regardless of how strong the oracles are.

16. **`DeliveryGate` names its `report_id` and carries the report, refusing a
    mismatch.** FR-119's permanence as a type boundary: a deploy cannot be approved
    against checks the approver never saw. `is_satisfied` is `not failed and
    is_approved`, so a failed machine check is not waivable by approving — approval
    cannot make an unsound artefact sound.

17. **`DeployRecord` refuses an unsatisfied gate, and deploys nothing.** §1.5 makes
    deploy never automatic, so this row is the *evidence* of a human act rather than the
    act. It carries the gate and its checks, so a reader can see what the approver was
    shown; a record naming only who approved would make "the gate presented the report"
    an assertion.

18. **`render_delivery` does not require a decomposition or a specification.**
    `check_integration` does, because without a decomposition there is nothing to be a
    violation *of*. A report states what is true, and "no decomposition exists" is one of
    the things it must be able to say — the missing hop is a gap in the chain. Everything
    else it reads from the log rather than taking from the caller, so a caller cannot
    supply a clause-to-module map that makes the chain look whole.

19. **`delivery_gate` is built from the *named* report, not the latest.** FR-119's
    permanence again, from the other side: `DELIVERY_RENDERED` appends rather than keys,
    so re-rendering supersedes without erasing and an earlier report stays readable.

20. **FR-119 and FR-120 are reported, not claimed.** `DELIVERY_REQUIREMENTS` names all
    five of §11's requirements, and the module docstring in `delivery.py` says which are
    derived and which are not. FR-120's machine-usable surface is not built, and a
    constant naming only the four that are would make "P8 passed" a claim the operator
    cannot check.

## Alternatives refused

- **FR-118's statements as prose in one rendered document.** Refused in decision 1. A
  paragraph can be written without the awkward clause; a required field cannot.
- **A `value_statement: str` field defaulting to the sentence.** Refused in decision 2:
  a default is a value a caller may override, and the sentence is the one thing no
  caller may change.
- **One "missing artefacts" list.** Refused in decision 4: the factory's work and the
  operator's open decision would be one indistinguishable set, and the check over them
  would fail forever.
- **A check over all four FR-117 kinds, failing on the two unproducible ones.** Refused
  in decision 5. It is the gate that cannot pass, and the fix people reach for is to
  stop running it.
- **A chain that stops at the first missing hop.** Refused in decision 6: the report
  could not tell a dropped clause from a contract that never had one.
- **Printing the declared rank under the word "measured".** Refused in decision 8: it is
  the euphemism FR-118 names.
- **`measured_strength: float = 0.0`.** Refused: zero is a measurement, and a report
  showing `0.00` for every clause would read as measured-and-weak rather than
  unmeasured.
- **A `MaintenanceLane.inherited_oracles: tuple[str, ...]` of bare statements, with the
  handover's own list stored beside it and a validator asserting the two agreed.**
  Refused in decision 14. Two statements of one fact, and a string cannot distinguish an
  executable oracle from prose — so a lane could not report what a maintenance run can
  actually execute. This was written and then rewritten.
- **Naming §14's module classes in the handover.** Refused in decision 11: the next mode
  would get a taxonomy for building rather than for maintaining.
- **`DeliveryReport.plan_id: UUID7 | None`.** Refused: it forced a `""` into a UUID7
  field, a hole no caller can reach because a report is only ever rendered for a plan.
- **Deploying.** Refused in decision 17 and by §1.5's "Autonomous production deploy"
  non-goal: SoFact produces specifications and verifies systems; it does not run
  releases.

## Consequences

- **FR-117, FR-118, FR-119 and FR-121 move from Not built to Implemented.** FR-120 (a
  machine-usable API surface) remains Not built and is named as such in
  `DELIVERY_REQUIREMENTS` rather than dropped from it.
- **FR-086's delivery half is discharged.** The value statement reaches the deploy gate
  as a constant, and the check that reports it cannot fail — which is the point: it is
  not a thing the factory might get right, it is a thing the type does not permit it to
  get wrong.
- **Two new ledger kinds** (`delivery.rendered`, `deploy.recorded`) and two new
  `ProjectState` fields (`deliveries`, `deploys`), taking `ProjectState` to 25 fields.
  Both append rather than key: a re-render and a second deploy are new records rather
  than amendments, because FR-119 makes both permanent.
- **Two new verbs.** `sofact deliver` renders and prints the report; `sofact deploy`
  presents the gate, and `--approve <id> --by <you>` passes it. Neither deploys
  anything.
- **The report will be mostly unverified on a project whose oracles are prose, and says
  so.** That is the honest state of a delivered system with ground-truth debt, and the
  handover counts the same debt again where it reaches Mode M.
- **A delivery root with nothing in it fails its own report.** The two artefacts the
  factory owes are files somebody has to write; `sofact deliver` does not write them,
  and the check says which are missing rather than passing over an empty directory.

## Evidence

- `src/sofact/views.py` — `DELIVERY_REQUIREMENTS`, `DeliveryArtifactKind`,
  `DELIVERY_ARTIFACTS`, `UNPRODUCIBLE`, `UNPRODUCIBLE_KINDS`, `DeliveryArtifact`,
  `TraceLink`, `VerifiedClause`, `UnverifiedClause`, `InheritedOracle`,
  `MaintenanceLane`, `Handover`, `DeliveryReport` (with `VERIFIED_NOT_VALUE`),
  `DeliveryGate`, `DeployRecord`; the `DELIVERY_RENDERED` and `DEPLOY_RECORDED` ledger
  kinds; `ProjectState.deliveries`/`deploys` with their accessors; ten new `__all__`
  entries.
- `src/sofact/delivery.py` (new) — `DELIVERY_ARTIFACT_PATHS`, `artifact`, `chain`,
  `verified_and_unverified`, `ceiling`, `_lane_oracles`, `LANE_ORACLE_KEYWORDS`,
  `handover`, `report`. `artifact`, `ceiling` and `verified_and_unverified` are public
  because each is the whole of a policy an operator has to be able to audit when it
  looks wrong — the same reason `decomposition.classify` is public.
- `src/sofact/state.py` — the two fold arms, the two local lists, the two constructor
  arguments.
- `src/sofact/service.py` — `render_delivery`, `current_delivery`, `delivery_gate`,
  `approve_deploy`.
- `src/sofact/cli.py` — the `deliver` and `deploy` verbs, `_deliver`, `_deploy`, and the
  option singletons they share with the other verbs.
- `tests/ci/test_delivery.py` (new) — 65 tests across ten classes: the five
  statements, FR-086's constant, artefact presence, the chain's gaps, the
  verified/unverified split, the ceiling's lower bound, the handover, the gate, and the
  render-from-the-log path.
- `tests/ci/test_cli.py::TestTheDeliverVerb` and `::TestTheDeployVerb` — 11 tests.
- `tests/ci/test_state.py` — `KIND_TO_FIELD` gained the two kinds and the field count
  went 23 → 25. Both are the guards doing their job: a new kind with no field, or a
  field with no kind, fails.
- **A canary**, with the target string asserted present before the patch and the file
  restored from `/tmp/delivery.py.bak` rather than from git: `owed` widened from
  `not a.present and a.kind not in UNPRODUCIBLE_KINDS` to `not a.present` — the
  artefact check put back over all four kinds. `test_the_artefact_check_is_scoped_to_what_the_factory_owes`
  failed; the empty-root test still passed, which is the distinction the two arms exist
  to draw (a scoped check that still refuses, not a disabled one).
- `tests/ci` at this commit: **978 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

- FR-117 (the four artefacts and the traceability chain), FR-118 (the five statements),
  FR-119 (the human, permanent deploy gate), FR-120 (the machine-usable surface, not
  built), FR-121 (the Mode M handover), FR-086 (value is not certified), FR-108
  (ground-truth debt), FR-122 and FR-123 (autonomy is the lower bound), FR-124
  (per-deployment topology), FR-126 (G7 is human-authored), FR-082 (an oracle with no
  command), FR-007 (the weakest oracle sets the ceiling), §1.3, §1.5, §11, §13, §14.
- [ADR-0039](0039-the-envelope-refuses-a-ceiling-and-reports-a-floor.md) — FR-118's
  fifth statement, and the envelope the report measures against.
- [ADR-0005](0005-no-container-runtime.md) — why the deployable artifact is a decision
  rather than an omission.
- §1.5 ("Autonomous production deploy — blast radius is not machine-bounded for a
  deploy. Gate P8 is permanent") and decision 17 above — why `approve_deploy` records a
  decision and performs no release.
- [ADR-0004](0004-delegate-the-coding-loop-to-an-external-harness.md) — why the factory
  holds no coding loop, and so has no mechanism by which to run one.
