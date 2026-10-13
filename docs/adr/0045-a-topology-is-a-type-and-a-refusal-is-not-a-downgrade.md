# 0045 — A topology is a type, and a refusal is not a downgrade

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-124, FR-030, FR-031, FR-042, FR-019, FR-122, FR-123, FR-157;
  [ADR-0040](0040-a-delivery-report-states-five-things-and-its-gate-is-human.md),
  [ADR-0041](0041-a-mode-g-delivery-is-l2-and-the-modules-are-reported-separately.md),
  [ADR-0044](0044-the-factory-writes-the-two-artefacts-it-owes-and-the-delivery-is-a-fixed-point.md)

## Context

FR-124 is one sentence in the spec — "per-deployment topology ceilings (FR-019, FR-030,
FR-031) apply to Mode G unchanged" — and it is three requirements wearing one number.

§5.4's principle is that *the same lane has different admissible ceilings on different
hardware*, because what bounds blast radius is the isolation the environment actually
provides. Four topologies follow from that, and one of them is not a ceiling change at all:

| Topology | Isolation | Modifier |
| --- | --- | --- |
| T1 dev / reference | none — shared filesystem, no container boundary | **−1 level** |
| T2 cloud VM *(product target)* | container per lane, VM boundary, egress-denied | baseline |
| T3 air-gapped | T2's boundary with no egress at all | baseline |
| T4 split | producer and evaluator on separate hosts | **+0**, unlocks L4 for lanes whose blast bound previously failed |

The roadmap recorded the whole row as **"Not built — no deployment topology type."** The
delivery report already carried two autonomy numbers (ADR-0041) and neither of them knew
where the factory was running, so a T1 dev instance reported the same ceilings as a T2
deployment and there was nothing in the log to tell them apart.

## Decisions

### 1. The topology is a `StrEnum` and the tables are keyed by it

`DeploymentTopology` is a `StrEnum` whose values are §5.4's own identifiers, so a report
and the spec agree on what to call the thing. `TOPOLOGY_ISOLATION` and `TOPOLOGY_MODIFIER`
are both keyed by it, and a test asserts the two tables and the enum have the same key set.

The pairing is the requirement's substance, not a convenience. FR-030 asks for the
topology, its **isolation guarantees**, and its modifier — a reader told "T2, baseline" and
not told what T2 guarantees has been given a number to trust rather than a fact to check.
That is R2 in the old spec's risk table: "autonomy depends on isolation (FR-019) that is
asserted but never verified."

The modifier is stored as an *integer delta* rather than as a table of resulting levels. A
pre-applied table would have to be rewritten every time `MODULE_CLASS_CEILING` or
`ceiling_for_rank` moved, and the two would drift silently; a delta is what §5.4 actually
states.

### 2. The default is T1, and "not configured" is a distinct fact from "T1"

A ceiling that fails open on an unconfigured deployment is the one failure a ceiling may
not have — the argument ADR-0041 already makes about FR-123's cap being a constant rather
than a mode-keyed lookup. So a factory that has not been told where it is running claims
T1's *lower* number.

But T1 is also a legitimate choice, and FR-042 requires the dev instance to "report its
degraded ceiling rather than silently behaving as if it were T2". A deployment that chose
T1 and one that configured nothing both report T1, so `FactoryService` keeps `None` (no
topology declared) distinct from `DeploymentTopology.T1`, and the report carries
`topology_configured` beside `topology`. The CLI prints the T1 line in yellow and adds the
sentence naming `SOFACT_TOPOLOGY` when the flag is false.

The default is applied on *read* rather than in `__init__` for exactly this reason: a
`__init__` that substituted T1 would destroy the distinction the report needs.

### 3. The modifier is applied to the modules' number and not to the delivery's

`module_autonomy` ends in `topology_ceiling(...)`; `ceiling` does not apply the modifier at
all. FR-123's L2 cap is at or below every topology's number, so applying §5.4's modifier to
the delivery would report T1 as L1 for a reason §5.4 does not state, and would attribute to
the deployment a reduction the cap had already made. A test pins this
(`test_the_delivery_cap_is_not_lowered_a_second_time`).

The clamp at L0 is not decoration: T1's modifier is one level and a G7 module class is
already L1 (FR-126), so the arithmetic reaches L0 − 1, which `AutonomyLevel` cannot
represent. A clamp is the right shape rather than a refusal, because the refusal FR-031
asks for is about a specific case and is raised by a function that knows the level the lane
*would* have had.

### 4. FR-031's refusal is per module class, and it is a gate check

FR-031 refuses a specific thing: "a lane that would be L4 in T2 must be **refused** at L1
in T1 rather than silently downgraded, unless an explicit operator override is recorded."

The class is where that is decidable, because `MODULE_CLASS_CEILING` is where L4 lives — a
module class whose ceiling is L4 is exactly a lane that would be L4 in T2. So
`refused_by_topology` walks the decomposition's classes, and a contract with no
decomposition refuses nothing. That is not an escape from §5.4: the modifier still applies
through the contract's own ceiling, which a test asserts.

The refusal is a **failed machine check** rather than a separate enforcement path, because
`approve_deploy` already raises on any failed machine check. No second code path was added
for it. What was added is a test that the refusal *reaches* the gate — a correct function
nobody calls is a control that exists and is not applied, and the delivery path is exactly
where that gap would be invisible.

### 5. The override is a name, not a boolean

FR-031's own word is "recorded". An override with no name attached is indistinguishable, in
the log, from the silent downgrade the requirement forbids — which is the entire content of
the requirement. So `topology_override` is a `str | None` threaded from `--override-topology`
through `render_delivery` into `report`, and the check's detail names who accepted it.

### 6. The refusal states the fact; the gate holds the remedy

`views.topology_refusal` returns the refusal and stops. It does not say "record an override
or move the deployment", because whether that remedy is *outstanding* depends on state it
cannot see. The first draft put the sentence in the refusal, and the check printed "Record
an explicit operator override to run it here" directly above "An explicit operator override
was recorded by ada" — an instruction to redo something already done, over a refusal that
had been accepted. A check that reads that way is one a reader learns to skim, and a skimmed
check is a disabled one.

The remedy lives in `delivery.report`, which holds the override and can therefore say which
of the two branches is true. The test asserts both halves: what was refused stays named, and
the instruction is absent once it has been acted on.

### 7. T4 is reported as baseline, and its unlock is named rather than applied

§5.4's T4 is "+0, but unlocks L4 for lanes whose blast bound previously failed". The `+0` is
a level change of zero; the unlock is a change to *admissibility* on a blast bound, and
SoFact does not hold one. §5.2's FR-027 requires a lane's file scope be declared and
enforced by permission, and nothing in the log declares one.

So T4's modifier is `0` and its isolation is stated, and the docstring records the unlock as
the thing it is rather than applying it as a level this code cannot justify. Claiming a
*higher* number for T4 would be a ceiling moving in the direction a ceiling must never move
on an unmeasured premise.

## Alternatives refused

- **Default to T2, the product target.** Refused in Decision 2: a ceiling that fails open on
  an unconfigured deployment is the one failure a ceiling may not have.
- **One `topology` field with no `topology_configured`.** Refused: it makes "we chose T1" and
  "nobody configured anything" the same report, which is precisely what FR-042 forbids.
- **A pre-applied table of resulting levels per topology.** Refused in Decision 1: it
  duplicates `MODULE_CLASS_CEILING` and `ceiling_for_rank` and drifts from them silently.
- **Apply the modifier inside `ceiling` as well.** Refused in Decision 3: it lowers a cap
  that was already below, and reports T1 as L1 for a reason §5.4 does not state.
- **A boolean `--override-topology`.** Refused in Decision 5: an unnamed override is the
  silent downgrade the requirement exists to forbid.
- **A separate enforcement path for FR-031.** Refused in Decision 4: the check is a machine
  check and `approve_deploy` already refuses on those; a second path would be a second place
  for the rule to live and the two would eventually disagree.
- **Treat the topology as an operational detail and infer it from the environment.** Refused
  by FR-040's own words: topology is "a first-class configuration input that modifies
  autonomy ceilings, not an operational detail". Inferring isolation from the filesystem
  would be measuring the thing FR-019 says is asserted and never verified.

## Consequences

- `SOFACT_TOPOLOGY` declares the deployment; `sofact deliver` reports it with its isolation,
  its signed modifier, and whether it was declared at all.
- `--override-topology <name>` records FR-031's acceptance, and the gate check names who
  accepted it.
- A T1 deployment refuses an L4 module class by failing a machine check, so `sofact deploy`
  is refused for free on a report the topology refuses.
- `DELIVERY.md` and `RUNBOOK.md` state where the factory ran. The runbook says explicitly
  that a system built on a dev machine inherits no claim about its own deployment — the
  topology is where the *factory* ran.
- The two tables are keyed by the enum and a test asserts the key sets match, so a fifth
  topology added to the enum without an isolation or a modifier fails rather than defaulting.
- The synthetic end-to-end tests assert the modifier as an *equality with the pure function*
  for the topology the report names, rather than against a level constant. What class the
  synthetic clauses land in is the classifier's business, and pinning it would make a
  classification change look like a topology regression.
- FR-124's per-topology half is now built. FR-040's "first-class configuration input" is
  satisfied for the *ceiling*; nothing yet reads the topology to change anything else
  (packaging, egress, or the container boundary FR-019 depends on), which is D9's open
  decision rather than this record's.
