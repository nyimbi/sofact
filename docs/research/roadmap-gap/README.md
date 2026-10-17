# Roadmap gap audit — the specification against the implementation

**Date: 2026-10-12, counts refreshed 2026-10-14.** This is a **snapshot**. The tree
changed while it was being written: FR-112's check landed mid-audit (ADR-0027,
commit-in-progress), and the counts below reflect the tree after that change. Re-run
the greps before acting.

Scope: every `FR-xxx` the spec states, classified against `src/sofact/*.py` and
`tests/ci/*.py`. Verdict classes:

- **Implemented** — a named function and a named test that fails if it is removed.
- **Partly** — the named half that is missing.
- **Deferred** — named in an ADR as not-built.
- **Not built** — no code, no test, no record.

`tests/ci` at the last refresh: **1437 passed, 0 failed** (2026-10-14, after ADR-0059). The
previous run of this unit's tree failed exactly one test,
`test_docs.TestTheSuiteCountIsTheOneThatRan`, whose whole job is to fail when the suite's size
moves without the README's count line moving — it caught this unit's thirteen new tests, the
line was updated, and the run above is the rerun. The table below was written at 725; the
verdicts are the part that matters and the ones closed since carry their date.

---

## 1. The FR table

| FR | Verdict | Evidence |
| --- | --- | --- |
| FR-001–005 declared oracles, read-only corpus, canaries, audit trail, invalidation | **Partly** | `Clause.oracle` required (`views.py:351`), `require_executable` (`contract.py:110`). **FR-004's must-fail canary is now built for the oracle set** (2026-10-13, ADR-0053): `audit_oracles` runs every probeable oracle against an empty workspace and reports one that is satisfied there, which is the canary that cannot move. What remains unbuilt: the **known-good** arm of the canary (a corpus the oracle must pass, which needs FR-002's read-only corpus), oracle-corpus read-only enforcement, and cache invalidation. FR-006's second half is FR-166 (below). |
| FR-006 no stale result decides a later state | **Implemented** | `verdict_cache_key` (`verification.py:71`); `test_a_different_change_keys_differently` (`test_verification.py:477`), `test_a_completed_dispatch_is_checked_without_a_declaration` (`test_service.py:1127`). |
| FR-007 O1 alone caps at L2 | **Implemented** | `ceiling_for_rank` (`views.py:209`); `test_rank_maps_to_ceiling` (`test_views.py:97`). |
| FR-008–011 mutation score per module, thresholds, trend | **Partly** (2026-10-14, ADR-0061) | The **score** half is built: `measure_strength` (`mutation.py`) runs a closed, named operator set of `ast.NodeTransformer`s over the module a clause traces to and reports a kill rate, and `VerifiedClause.measured_strength` renders it in the delivery report — the field FR-118 asked for and no code path had ever set. **The thresholds half is now built** (2026-10-17, ADR-0076): `oracle_strength_ceiling` (`routing.py`) reads FR-009's table against the measured number and `route` applies FR-105's escalation as the lane's *ceiling*, so θ_lo is compared rather than merely recorded, and `THETA_GATE_BUILT` is `True`. **Not built:** the **trend** across history, which is FR-159's instrument — built (ADR-0062) and reporting *unmeasured* until a scope has two measured units. The number is a lower bound and is withheld below `MINIMUM_MUTANTS_FOR_A_NUMBER = 5`, so it is a measurement rather than a gate input. It *is* now a gate input since ADR-0076 — a strength below θ_lo caps the lane at L1 — and the withholding is what makes that honest: a lane whose mutant set was too small to score is `undecided` rather than L1, because `oracle_strength_ceiling` returns `None` for an unmeasured strength and never the bottom of the table. `THETA_GATE_BUILT` is `True`. |
| FR-012–015 adversarial audit, sampling, exploit metric | **Partly** (2026-10-15, ADR-0063) | The **loop** is built. `sofact.adversarial` rewrites the file each oracle command runs — three of FR-012's five techniques are mechanical source transforms (`EDITED_TEST`, `DISABLED_ASSERTION`, `SPECIAL_CASED_FIXTURE`) — and the attacked oracle is run by the **real `OracleRunner`** and read by the **real `verify()`**, exactly as at P6, because deciding "satisfied?" locally would be a manufactured *judge*, the same defect as a manufactured oracle one level up. The honest tree runs first and decides what is attackable: against an oracle that already passes there is no passing verdict to obtain, so a satisfied baseline yields `NOT_ATTEMPTED` rather than `HELD`. FR-014 is complete: the sample is a deterministic `ordinal % N == 0` stride at or below L3 with **100%** above, and the third sentence — "the sample rate must increase automatically when an exploit is found" — is `effective_sample_floor`, read off this contract's prior passes, returning 1 once an exploit was found and relaxing after a pass that attacked and held. A sampled-out pass is **skipped, not read as clean**, and the escalation destination is a constant while the floor is a parameter. FR-015's rate is `None` over zero attempts (its target is zero, so a zero over nothing is the forbidden reading) and the report carries the **lane**, because the requirement's own sentence is per-lane. Audits are appended, never keyed: the subject is a trend. `passed` is `not exploited` — FR-013's fix is a claim the *next* audit verifies, so a fixer's word is not a clearance (FR-138 one level up). Wired: `LedgerKind.ADVERSARIAL_AUDITED`, the fold, `ProjectState.adversarial_audits`, `latest_adversarial_audit`, `FactoryService.adversarial_audit()`, `sofact audit --adversarial`. 42 tests in `test_adversarial.py`. **Not built:** the two techniques that need a model to invent code satisfying an intent without implementing it — `HARDCODED_EXPECTED` and `OVERFIT_TO_SAMPLE` — are named in `UNADDRESSED_TECHNIQUES` and reported as `NOT_ATTEMPTED`, never dropped; and a per-lane **trend** over history is a reading rule nothing computes yet, so FR-015's "should trend to zero and stay there" is a direction the data now permits rather than a chart the product draws. |
| FR-016–020 isolation | **Partly** (2026-10-14, ADR-0060) | The boundary is now **measured and applied**, which is the half that did not exist. `DeploymentBoundary` (`views.py`) carries `mechanism`, `enforced`, `attempted`, `observed`, `probed_at`, `writes_confined` and `deny_read`; `detect_boundary`/`seatbelt_profile`/`wrap_argv`/`boundary_env` (`boundary_probe.py` for the detector, `boundary.py` for the appliers — split in ADR-0067 so the socket the egress probe binds is not in an authoring surface's import closure) run **one real child** that writes inside its directory, tries to write one level above, and tries to open a planted canary in each subtree it must not read. Both process-launch points route through `wrap_argv` — the dispatch (`harness.py`) and the oracle command (`execution.py`) — so the control is applied at every launch rather than at the one that was convenient. **Measured on this host, not assumed:** `sandbox-exec` confines a sibling write; Seatbelt's rules are last-match-wins, so `(allow file-read*)` → `(deny file-read* (subpath "<home>"))` → `(allow file-read* (subpath "<workspace>"))` yields `workspace: READ, ledger: DENIED, holdout: DENIED`; the profile denies egress (`EGRESS_DENIED_OR_DOWN`, `Errno 1`); and a profile naming an *unresolved* path denies nothing, which is why every path is resolved and why that trap has its own test. The ceiling follows the measurement (FR-019's "where one exists"): a measured boundary restores the baseline a degraded declaration gave up, and §5.4's table topping out at 0 is what keeps the modifier space from growing. **Still not built:** FR-016's "no read access to holdouts" is measured only where a subtree is named to deny — the factory passes its own home, and nothing yet enumerates a *per-lane* holdout set; FR-020's blast bound is not read from the topology to change packaging or egress; and a host with no mechanism still runs fully degraded, which is now *reported* rather than silently assumed. `TestTheBoundaryIsMeasured`, `TestTheReadHalfIsMeasuredToo`, `TestTheCeilingFollowsTheMeasurement`, `TestTheBoundaryWrapsEveryLaunch` (`test_boundary.py`, 19 tests), `TestTheTopologySeam` (`test_cli.py`, +2). **The egress half is now measured too (2026-10-15, ADR-0066):** `DeploymentBoundary.egress`/`egress_observed`/`egress_confined` record whether a child was *watched* being refused a TCP connect to a listener the measuring process had bound on loopback, so `enforced` no longer rests on the filesystem half alone — a boundary whose egress measured open is not credited. What stays open is FR-124's *packaging* half and the container path, which this host cannot exercise. |
| FR-021–023 escape oracle, automatic downgrade | **Implemented** (2026-10-13, ADR-0054) | `escape.py` — `measure_escapes`, `lanes_of`, `load_escape_budget`, `ceilings_from` — plus `EscapeEvent`/`EscapeBudget`/`EscapeOverride`/`LaneEscape`/`EscapeReport` (`views.py`), `record_escape`/`record_escape_override`/`escape_report` (`service.py`), `sofact escape` and `sofact escapes` (`cli.py`), the `escapes` machine operation (`api.py`), and an `## Escapes` section in `DELIVERY.md`. **The denominator** is distinct deployed report ids and the **numerator** distinct `defect` values; `deployed_reports` is a field, not a sum of the per-lane rows (one report spanning four lanes is one change). FR-021's band is **derived** from `contract.weakest_oracle_rank`, never stored. FR-023's reduction is one level, non-cumulative, clamped at L0, and **unset is not zero** (no declared budget ⇒ `unbudgeted`, `over_budget=None`). The over-budget check **reports** (`escape_ceiling_applied`, `passed=True`) rather than failing, because a failing check would refuse the very deploy that dilutes the rate back to budget and make FR-023's automatic recovery unreachable — the reduction still binds through `lane_ceilings` into `module_autonomy`. 42 + 14 + 14 tests. |
| FR-024–035 routing function, blast bounds, ladder, per-deployment ceilings | **Partly** (2026-10-16, ADR-0045, ADR-0046, ADR-0074) | The **ceilings** half is built: `DeploymentTopology` with its isolation and signed modifier (`views.py`), the per-module-class refusal (FR-031), and the T1 default (FR-042) — ADR-0045. The **blast bound** half is now declared: `ModuleBudget` (`max_files`, `max_loc`, `reasoning_class`) on every `Module`, checked at P7 as `module_budget` (FR-026, FR-097) — ADR-0046. The **class half of the routing function** is now built (2026-10-16, ADR-0074): `REASONING_CLASS_TIER`/`class_tier` (`tiers.py`) turn a module's declared `reasoning_class` into a tier, `resolve_model` consults it after `--model` and before the phase's, and `dispatch_step` resolves the module *before* the adapter so the declaration reaches `DispatchRecord.model_source`. The field had been written by every decomposition, gated at P3 and hashed into `decomposition_hash` while its only readers were two print statements — a module declaring `reasoning` ran on the same model as one declaring `throughput`. **The routing function itself is now built** (2026-10-17, ADR-0076): `sofact.routing` computes all three lines of §5.1 — `admissible` returns one named `RouteTerm` per conjunct (`intent_derivable`, `oracle_exists`, `blast_radius_bounded`), `route` takes the `min` of `f(oracle_strength)` (FR-009's θ table, the term that did not exist), §14's class ceiling and §5.4's topology modifier, and then applies the concerns floor and FR-027's permission cap — reachable through `FactoryService.routing_report` and `sofact route --contract <id>`. `THETA_GATE_BUILT` is `True` because the instrument exists, and `RouteDecision.undecided` keeps *the instrument exists* and *this lane passed it* apart: a lane with no surviving measurement has **no level**, not a low one. **Still absent, and named rather than counted:** FR-027's **measured** blast radius — ADR-0045 named it as the thing T4 unlocks, and `ModuleBudget` remains the number the proposer *declared* (ADR-0046), though it is now read by the routing function as well as by P7's check, through the same `module_budget_readings` fold; and nothing yet consults a routing decision at **dispatch** time, so the ladder is a reading of the log rather than an interlock. §5.1 renders a `g(blast_bound)` term and §5.2 supplies no table mapping a bound to a level, so there is no `g` — the bound is the third conjunct of `admissible` and exceeding it refuses the lane, which is strictly stronger than the reduction a fabricated `g` would apply. |
| FR-036 per-language mutation/property tooling | **Partly** (2026-10-14, ADR-0061) | The **per-language manufacturing** half is built and D5 is resolved: `MANUFACTURE_SPECS` names `python`, `typescript` and `rust` as `ManufactureSpec` data, `SOFACT_MANUFACTURE` replaces the table wholesale, and an unknown backend is refused by name rather than falling back to Python. Each backend declares which ranks it builds — Python 1/3/5, TypeScript 3/5, Rust 3 — and refuses the rest by name. **Not built:** no per-language *mutation* engine. The strength instrument is Python-only (`ast`), so `_measured_strengths` filters a module's sealed files to `.py` and a TypeScript or Rust module renders "not measured" rather than a rate over a file the engine did not read. |
| FR-038 verifier/executor import direction | **Implemented** | `test_verifier_cannot_reach_the_executor` (`test_verification.py:72`) scans this file's imports. |
| FR-049 model-agnostic | **Implemented** | `SOFACT_MODEL` / `--model` resolved by the harness registry; `test_the_probe_reports_the_model_it_measured` (`test_cli.py:406`). |
| FR-052–056 fine-tuning, monetization | **Partly** (2026-10-15, ADR-0064) | FR-053 and FR-055 are built; FR-052, FR-054 and FR-056 are not, and the cell names them rather than counting the row complete on two of six. **FR-053** (a fine-tuned model must never be an oracle) and **FR-055** (the factory must not set prices, accept customers, sign agreements, move money or make commitments) share one shape with FR-134 and one instrument: `sofact.authorship` walks the **transitive import closure** of the two authoring surfaces and reports whether anything in it can talk to a model, and FR-055 is measured in two halves — the import half (a module importing `stripe` could charge a card) and the kind half (FR-002 makes the ledger the only mutable thing, so a `LedgerKind` named for an act *is* the factory having the act). `sofact authorship` exits non-zero on either. **Not built:** FR-052's tuning target and FR-054's recipe-not-weights rule are deployment decisions no module in this build can discharge — the factory holds no tuning capability, which is why the check establishes the *structural* half only and `TUNED_MODEL_UNREACHABLE` is printed beside every verdict. FR-056 needs a staging sequence (shadow → advisory → gated) that does not exist here. |
| FR-057 envelope refusal | **Implemented** (2026-10-13, ADR-0039) | `DeliveryEnvelope`/`DimensionBound` (`views.py`), `load_envelope`/`measure` (`envelope.py`), the `within_delivery_envelope` check in P3's gate (`decomposition.py`), `SOFACT_ENVELOPE` and `sofact envelope` (`cli.py`). Refuses the **ceiling** and names the dimension; a dimension below its floor is reported and passes, because §1.3's numbers are targets and §1.4 wants small deliveries buildable. Four of eight dimensions are measured at P3; the rest are named as unmeasured with what would have to exist. `TestTheGateRefusesAnOverScopedProposal` (`test_envelope.py`), `TestTheEnvelopeVerb` (`test_cli.py`). |
| FR-058 single adapter interface | **Implemented** | `ConfiguredHarnessAdapter` (`harness.py:819`), three specs; `test_every_shipped_harness_has_a_spec` (`test_harness.py:102`). |
| FR-059 harness cannot reach oracle corpus/credentials | **Implemented where a boundary holds** (2026-10-14, ADR-0060) | The read half is now **measured**, not asserted: the detector plants a canary in each subtree named to deny and watches a child fail to open it, so "denied" means a file that exists was unreadable rather than a rule that was written. `DeploymentBoundary.deny_read` names the denied **subtree roots** — not the canary files — because enforcement rebuilds a profile from that tuple and a file-level deny would leave the subtree it sits in readable. `FactoryService.boundary` passes the factory home, which holds the ledger, the holdout scenarios and the credentials, and the workspace usually sits inside it, so the deny-then-re-allow ordering is exercised by one probe rather than one half being assumed from the other. A subtree that turned out readable makes the boundary `enforced=False` **even when writes held**: a producer that can read the holdout has the answer whatever it can write, so crediting write confinement while the answer key stayed legible would raise a ceiling on half a property. **The limit, stated:** this holds only where a mechanism confines reads — on a host with none, the row is a measured absence rather than a guarantee, and the prompt-text half (`planner.py:127`) is unchanged. `deny_read` empty means *not measured*, which is recorded as such and is not the same as measured-and-open. |
| FR-060 phase state machine, resumable after SIGKILL | **Implemented** (2026-10-12, ADR-0030) | `Phase`/`PHASE_SEQUENCE`/`PhaseAdvance` (`views.py`), `advance_phase`/`approve_gate`/`current_phase`/`open_gate` (`service.py`), `sofact phase` and `sofact gate`; `test_the_phase_survives_a_restart_because_it_is_in_the_log` (`test_phase.py`). A transition is its own ledger row, so a new process reads the phase off disk. |
| FR-061 gate is a hard stop | **Implemented** | `require_approved_decomposition` (`service.py`) for P3, and now structural for all four gates: `PhaseAdvance` refuses a completed gate phase with no approver, `advance_phase` cannot complete a gate, and it refuses when any earlier phase is incomplete — so P5 is unreachable without P2 and P3. Canaried by deleting the forward check. |
| FR-062 every phase emits a durable artifact | **Implemented** (2026-10-13, ADR-0037) | Decomposition/contract/plan/verdict are ledger rows, a phase transition is one (`LedgerKind.PHASE_ADVANCED`), P2 emits `SPECIFICATION_PROPOSED`/`SPECIFICATION_GATED`, P1 emits `SOURCE_LEDGER_RECORDED` (FR-070/ADR-0035) **and now `RESEARCH_CLASSIFIED`** (FR-068/ADR-0037), so every phase P0–P3 has an artefact a resume lands on. |
| FR-063 goal not accepted until reduced to falsifiable | **Implemented** | `Readiness.is_ready` (`views.py:290`); `test_progress_counts_resolved_dimensions_and_readiness_flips_at_the_end` (`test_elicitation.py:217`). |
| FR-064 adversarial elicitation, 8 dimensions | **Implemented** (2026-10-17, ADR-0077) | `ElicitationDimension` (`views.py:1293`) has **8** members and the spec's two rows it lacked — *Scale* and *Non-negotiables* — are among them; the count is eight rather than the table's seven because `CONSUMER` is split out of the table's single *Success* row and `ORACLE` is FR-067's `verification_method`, which the module documents as producing no clause, so no member order reproduces the table and the ADR says so. `SCALE` carries a second content floor (`requires_quantity`, `test_only_the_scale_dimension_demands_a_quantity`), and the *Non-negotiables* row is its own question rather than folded into `CONSTRAINT`'s, which is where it had been. **The limit is inside the requirement and is the requirement's own word:** a scale clause's oracle is prose, so `execution.run_all` skips it and P6 records `INSUFFICIENT` — the obligation is declared and visibly unmet, and R19's second half is a question here rather than a bound. `test_the_spec_rows_the_enum_dropped_are_now_present` (`test_elicitation.py`). |
| FR-065 elicitation terminates, unresolved reported as risk | **Implemented** | `next_open` (`elicitation.py:226`), `Readiness.open_dimensions`; `test_next_open_returns_the_first_unresolved_dimension` (`test_elicitation.py:229`). |
| FR-066 elicitation proposes no implementation | **Implemented** | `_SHARED_CONSTRAINTS` (`planner.py:110`) + `draft_stems` polarity (`elicitation.py:254`); `test_polarity_follows_the_dimension` (`test_elicitation.py:281`). |
| FR-067 each clause carries `confidence` and `verification_method` | **Partly** | `Clause` (`views.py:351`) carries **neither**; ambiguity is not quantified per clause. `test_confidence_is_not_an_oracle` (`test_elicitation.py:160`) asserts the *opposite* rule. |
| FR-068 clause classified by research into validated/invalidated/… | **Implemented** (2026-10-13, ADR-0037) | `ClauseClassification`/`ResearchClassification`, `VERDICT_ACTION` as data read by the type, the CLI and `advance_phase`, which refuses to complete P1 over an Invalidated or Deepened clause. The clause list is the draft's and is written into the producer's goal, so "every clause is classified" is not the producer measured against itself. `sofact classify` prints each verdict with its action; `TestTheClauseClassification` (21) and `TestTheClassifyVerb` (8). |
| FR-069 finding provenance | **Implemented** (2026-10-12, ADR-0035) | `Source` carries `url`, `retrieved`, `verification` (`VerificationStatus`, the `docs/sources/README.md` legend as a type) and `confidence`; `Claim.opinion` labels the uncited assertion, and `SourceLedger.unbacked_decisions` refuses one as grounds for a decision. `ResearchRecord.source_urls` remains the *dispatch* measurement. |
| FR-070 versioned source ledger, claims separately addressable | **Implemented** (2026-10-12, ADR-0035) | `Source`/`Claim`/`Contradiction`/`SourceLedger` (`views.py`), parsed from the producer's `research-sources/*.md` and `research-claims.json` by `sofact.research`, recorded as `LedgerKind.SOURCE_LEDGER_RECORDED`, printed by `sofact sources`. `SourceLedger.resting_on(id)` derives the set a source's invalidation takes with it; `version` counts the ledgers the project reads under. `test_a_claim_points_at_its_source_and_the_edge_is_navigable` (`test_service.py`). |
| FR-071 disconfirming count reported | **Implemented** (2026-10-12, ADR-0035) | `Claim.kind` is `supporting`/`disconfirming`/`refuted`; `SourceLedger.disconfirming` counts them and `sofact sources` prints the count. **Deliberately not a gate check** — a check that failed at zero would pay a producer for inventing one, so the count is a measurement (see ADR-0035 decision 6). |
| FR-072 research bounded by declared budget | **Implemented** (2026-10-13, ADR-0036) | `ResearchBudget` holds FR-072's three quantities **per intent clause** and `scaled(clauses)` returns the whole-run `ResearchAllowance` the `ResearchRecord` carries; the clause count comes from the latest draft and a goal with no draft counts as one, recorded rather than defaulted silently. Wall clock is **enforced** (SoFact owns the timeout and kills the child); sources and model calls are **observed** from the producer's artefacts and recorded in `budget_violations` when exceeded, because a cap enforced inside the producer's runtime is the producer grading its own spend (FR-140). An unmeasured turn count produces no violation in either direction — `None` is not `0` (NFR-024) — and `sofact research` prints `calls unmeasured`. `--max-sources`/`--max-calls`/`--seconds` set the per-clause caps; `--timeout` overrides the scaled wall clock for one run without rewriting the declared budget. `test_the_allowance_scales_with_the_clause_count`, `test_an_overspent_run_records_the_cap_it_broke` (`test_service.py`). |
| FR-073 contradiction detection | **Implemented** (2026-10-12, ADR-0035) | `Contradiction` (`views.py`), read from the claims file, with `resolution` left `None` when the operator has not ruled — an unresolved disagreement is a real state, and `sofact sources` prints it as `UNRESOLVED`. Recorded rather than resolved: the spec says the disagreement is where the operator's decision is. |
| FR-074 evidence vs positioning classification | **Implemented** (2026-10-12, ADR-0035) | `Source.posture` (`SourcePosture`), with the type refusing `positioning` + `content-verified` together; `SourceLedger.unbacked_decisions` and the `positioning-is-not-evidence` check make "prevented from supporting a decision on their own" structural. |
| FR-075 self-staleness / expiry | **Implemented** (2026-10-12, ADR-0035) | `expires` on both `Source` and `Claim`; `SourceLedger.expired(as_of)` and the `nothing-has-expired` check are as-of a date, so the same ledger can be current and then not. |
| FR-076 specification as traceable requirements | **Implemented** (2026-10-12) | `Specification`/`Requirement` (`views.py`), `specify` derives one requirement per clause (`specification.py`), `sofact specify`; both traceability directions are gate checks. `test_every_clause_reaches_a_requirement` (`test_specification.py`). |
| FR-077 machine-checkable acceptance criterion per requirement | **Implemented** | `Requirement.criterion` is required and non-empty (`views.py`), taken from the clause's own oracle so the two cannot drift; `every_requirement_has_a_criterion` is a gate check. |
| FR-078 system model in the specification | **Implemented** (2026-10-12) | `SystemModel`/`SystemEntity`/`SystemRelationship`/`SystemInvariant` (`views.py`); entities, relationships and invariants, machine-readable, carried on `Specification`. **State machines are not modelled** — the spec's FR-078 lists them and the type does not have them. |
| FR-079 non-goals and assumptions declared | **Implemented** | `NonGoal`/`Assumption` (`views.py`); `Assumption.refuted_by` is required, so an unfalsifiable assumption cannot be declared. Non-goals are *proposed* from NEGATIVE clauses and never invented. Both are gate checks and both are printed by `sofact specify`. |
| FR-080 P2 gate presents the spec in the operator's language | **Implemented** (2026-10-12) | `SpecificationGate` + `sofact specify`/`--approve`; the proposal, its checks, its non-goals, its assumptions and its value hypothesis print in the operator's own words, since every statement is theirs. Approval is a separate act and cannot waive a failed check. |
| FR-081 internal consistency check | **Partly** (2026-10-12) | Two of three clauses. **Every entity referenced by a requirement** is a gate check over declared links, and **every requirement maps to a module** is checked in the P3 gate where modules exist. **"No two requirements may contradict" is not machine-decidable in prose** — the check covers the polarity case only (one statement asserted and denied) and says so in its own detail line rather than claiming a clean bill. |
| FR-082 testability check, `human-verified` marking | **Implemented** (2026-10-12) | `VerificationMethod` (`views.py`); a requirement whose oracle names no command is `HUMAN`, counted and printed at the gate. The check **reports rather than fails**, which is FR-082's own rule: a criterion needing a person is permitted, it must have its cost counted. |
| FR-083 machine-readable system model as the single interface source | **Implemented** (2026-10-13, ADR-0049) | Both clauses. The model carries `SystemInterface` values (`views.py`), each naming the clause it comes from and the `InterfaceMember` values it exposes — the same member type a module declares, so a surface moved from a module to the model is one vocabulary in two places. The model is the **declaration site** and `Module.surface` its **binding**: `propose(contract, model)` *derives* each module's surface from the interfaces its clauses introduce, so the proposer never chooses a public name and a proposal cannot disagree with its own model. P7 checks both directions — `MODEL_INTERFACE_NOT_BOUND` for an interface no module owns, `SURFACE_DISAGREES_WITH_MODEL` for a module whose surface is not the one the model derives (`check_model_is_the_interface_source`, `integration.py`) — and P2 refuses an interface citing a clause outside the contract. `TestTheModelIsTheInterfaceSource` (`test_integration.py`), `--interface` round-trip (`test_cli.py`). **FR-084 is not thereby discharged**: updating the model as part of a change is a process obligation, and what is now observable is its consequence. |
| FR-084 model updated as part of any change | **Partly** (2026-10-13, ADR-0049) | A model now exists and is the single source for interface definitions, so a stale model is *detectable*: a model that stopped matching the decomposition is a P7 finding (`MODEL_INTERFACE_NOT_BOUND`, `SURFACE_DISAGREES_WITH_MODEL`). What is not built is the obligation itself — "updated as part of any change" is a process rule over every change, not a property a check observes, and no mechanism forces a model edit to accompany an unrelated one. |
| FR-085 falsifiable value hypothesis | **Implemented** | `ValueHypothesis` (`views.py`) names effect, beneficiary and refuting instrument; `value_hypothesis_is_falsifiable` is a gate check. |
| FR-086 factory must not certify value | **Implemented** (2026-10-13, ADR-0040) | The type carries no verdict field and nothing in `specification.py` can mark a hypothesis satisfied — the factory's only permitted statement about one is that it was *declared*, and `sofact specify` prints it under "declared, never certified". **The delivery half is now discharged**: `DeliveryReport.VERIFIED_NOT_VALUE` is a `ClassVar`, so no code path can produce a report that omits the sentence or claims otherwise, and the deploy gate prints it. `test_the_sentence_is_a_class_constant` (`test_delivery.py`), `test_the_report_states_that_value_was_not_certified` (`test_cli.py`). |
| FR-087 decomposition machine-proposed, human-validated | **Implemented** | `propose` (`decomposition.py:282`), `approve` (`:493`); `test_the_proposal_is_deterministic` (`test_decomposition.py:93`), `test_approval_names_who_and_when` (`:340`). |
| FR-088 traceability both directions | **Implemented** | `gate` checks `every_module_traces_to_a_requirement` and `every_requirement_traces_to_a_module` (`decomposition.py:423,438`); `test_an_unowned_clause_fails_the_gate` (`test_decomposition.py:260`). |
| FR-089 DAG, no cycles | **Implemented** | `test_the_proposal_never_contains_a_cycle` (`test_decomposition.py:109`), `test_a_cycle_fails_the_gate` (`:239`). |
| FR-090 declared interface and dependencies | **Implemented** | `Module.interface` / `depends_on` (`views.py:491`); `test_a_dependency_follows_the_oracle_the_contract_already_carries` (`test_decomposition.py:121`). |
| FR-091 minimise interface surface, report the count | **Implemented** (2026-10-14, ADR-0059) | Both clauses, and the gap was **structural rather than a missing threshold**: `propose` emitted exactly one module per clause, so `interface_count` (`views.py`) was literally `len(self.modules)` == `len(contract.clauses)` — the module count wearing a second name, which §1.3 already had a separate dimension for. The grouping was **already declared and being discarded**: FR-083 made `SystemModel.interfaces` the single source for interface definitions and a `SystemInterface` names its `clause_ids`, so one declared interface over two clauses was becoming two modules exposing the same surface. `interface_groups`/`minimal_interface_count` (`decomposition.py`) group clauses that share a declared interface *and* the same `classify(...)` lane — the lane bound exists because `ModuleClass` is the class of work (FR-050) and `MODULE_CLASS_CEILING` grants autonomy by class (FR-126) — and `propose` loops over those groups. `interface_count_minimised` refuses a decomposition that splits a declared interface, comparing against the proposer's own rule re-derived in one function so a proposal cannot fail its own gate; a lane-forced split is **reported, never failed**, on `escape_ceiling_applied`'s precedent. `interface_count_reported` names integration points, surface members and §20.1's per-module ratio, and says the bound is §1.3's modules dimension rather than an invented interface number. A model with no interfaces merges nothing, so every existing fixture is byte-identical. `TestTheInterfaceCount` (13, `test_decomposition.py`), `TestTheInterfaceCount` (`test_cli.py`), `interface_members`/`interfaces_per_module` (`views.py`). |
| FR-092 declared build order | **Implemented** | `build_order_exists` check (`decomposition.py:413`); `test_a_sound_proposal_passes_every_machine_check` (`test_decomposition.py:291`). |
| FR-093 per-module completion criteria | **Implemented** | `completion_criteria(clause)` (`decomposition.py`), derived from `planner.exit_evidence_for` — the same conditions P5's session is handed, so the module's DoD and the session's exit evidence are one statement (ADR-0042). `propose` populates `Module.completion_criteria`; the gate check `every_module_has_completion_criteria` refuses an empty set ("not eligible to be built"); the criteria are in `decomposition_hash` and printed by `sofact decompose`. 6 tests + 2 CLI tests; canaried twice. |
| FR-094 revisable without invalidating the whole | **Implemented** | Revisions + `decomposition_hash`; `test_approving_a_superseded_revision_is_refused` (`test_decomposition.py:467`). The **rollback verb** the capability map recorded as missing now exists (2026-10-12): `FactoryService.cut` / `sofact rollback --to N` records a `cut.recorded` row and the fold reads through the target (ADR-0034); `TestRollback` (`test_service.py`), `test_a_cut_hides_the_entries_after_its_target` (`test_state.py`). |
| FR-095 P5 given the contract and only the contract | **Partly** | Goals are compiled from the contract (`compile_plan`, `planner.py:576`) and pinned by hash; the *envelope* the producer may see is not otherwise constrained or checked. |
| FR-096 contracts frozen before P5, immutable during | **Implemented** | `compile_plan` pins `contract_hash`; `check_integrity` (`planner.py:712`); `test_an_undisturbed_plan_reports_intact` (`test_service.py:1192`). |
| FR-097 explicit budget (files, LOC, reasoning class) | **Implemented** (2026-10-13, ADR-0046) | `ModuleBudget` and `ReasoningClass` (`views.py`), required on `Module.budget` with no default, declared by `propose` from `DEFAULT_MODULE_BUDGET` (§7.3's own worked example: 30 files, 2500 lines, throughput), covered by `decomposition_hash`, reported by the P3 gate check `every_module_declares_a_budget` (`decomposition.py`), measured at P7 by `check_module_budget` (`integration.py`) as a `MODULE_OVER_BUDGET` finding scoped to the one module, and printed by `sofact decompose` (`cli.py`). `StepBudget` keeps the per-session fields it had; the two are different scopes and neither substitutes for the other. `TestTheModuleBudget` (`test_decomposition.py`, `test_integration.py`). |
| FR-098 three modes incl. bootstrap empty repo | **Partly** | Bootstrap is a plan tier (`planner.py:231`), not an adapter mode; diagnostic mode exists via `repair_plan` (`service.py:1081`). Probe row `bootstrap_empty_repo` (`views.py:1416`) is measured, not exercised. |
| FR-099 idempotent per task | **Partly** | Stated in the goal text (`planner.py:114`); `test_re_running_the_same_step_is_idempotent` (`test_git.py:158`) covers the git half only. |
| FR-100 branch per module, never in place | **Implemented** | `ensure_module_branch` (`git.py:139`), `seal_branch` (`:258`); `test_the_branch_is_not_in_place` (`test_git.py:91`), `test_two_steps_of_one_module_share_its_branch` (`:115`). |
| FR-101 escalate with diagnosis, not retry forever | **Implemented** | `repair_plan` bounded per clause; `test_the_loop_is_bounded_and_says_so_when_it_gives_up` (`test_service.py:961`). |
| FR-102 attempt telemetry | **Implemented (2026-10-14, ADR-0055)** | `measure_attempts` (`telemetry.py`) folds a plan's `RepairAttempt` rows against the `DispatchRecord` each produced, giving the requirement's three nouns at attempt level: attempts, tokens, wall clock. Per-dispatch `tokens_observed`/`wall_clock_seconds`/`continuations_observed` (`views.py:1672`) were already recorded; the gap was the **join**, and it is where the module spends its care — `tokens_observed` is `int \| None` and `None` is *unmeasured*, never zero (NFR-024), so `AttemptTelemetryReport` sums what reported and carries `unmeasured_tokens` with `tokens_complete` saying whether the sum is exact. An attempt whose dispatch is absent (a torn read on an append-only log) is a floor, not a free session; an attempt that never ran is zero spend *and* nothing hidden — different facts, different rows. `discharged` returns `()` when no attempt was made, so a run that repaired nothing lands FR-102 in `not_implemented` rather than printing three green zeros. `sofact attempts` exits non-zero on that empty run. **The defect the suite caught:** the verb asked `latest_plan`, which returns the *revision* a repair authored, while every `RepairAttempt.plan_id` is the **origin** the loop was entered with — so the total was honestly and uselessly empty. `ProjectState.origin_plan` and `FactoryService.origin_plan` resolve it, and `TestTheAttemptsAreFiledUnderTheOriginPlan` asserts the two ids differ rather than merely that a number is non-zero. `TestTheFoldCountsWhatWasMeasured` (3), `TestTheTotalSaysWhatItLeftOut` (4), `TestTheRowTypeRefusesImpossibleSpend` (2), `TestTheVacuousPassIsRefused` (2), `TestTheAttemptsAreFiledUnderTheOriginPlan` (3), `TestTheScopeIsThePlan` (2), `TestTheReportIsAPureFold` (1), `TestPerClauseCounts` (1), `TestTheCliReportsIt` (2) in `test_telemetry.py`. |
| FR-103 oracle manufacturing from contract structure | **Partly** (2026-10-14, ADR-0061) | `manufacture.py` is the seam: a `ManufactureBackend` protocol of three members, a spec table read the way a harness spec is read, and one `ConfiguredManufactureAdapter` parameterised by spec so the gate does not vary by language. The hint is **earned** rather than fabricated — the artefact must resolve inside the module workspace, the argv's artefact element must *be* that path, the file must exist, the command must run, and FR-107's audit re-runs the same argv against a tree holding nothing but the artefact. `manufacture_python.py` builds rank 3 (every declared member present with its declared arity), rank 1 (nothing public is undeclared) and rank 5 (the same check against the model's declared interface, which is FR-083's integration defect seen before P7); TypeScript builds 3 and 5, Rust builds 3. `suggest_oracle` (`contract.py:46`) still proposes the class and abstains on the command; manufacturing adds executability to what it left alone, and a refusal leaves the clause exactly as it was. **Still not built:** ranks 2 and 4 need a declared transition relation and a declared metamorphic relation, which the contract does not carry — deriving a predicate from English prose would be fabrication, so both are refused by name rather than approximated. |
| FR-104 ranks 1–2 mandatory above L2 | **Partly, and it conflicts with §14** | `STRONG_ORACLE_MAX_RANK` (`views.py:269`) + `ceiling_for_rank` cap the ceiling; nothing *manufactures* a rank-1/2 oracle. **The code is right and the requirement is the outlier:** FR-104 says ranks 1–2 are mandatory above L2, but §14's own module-class table puts **G3 (API/service) and G4 (persistence) at L3 with rank-3 contract tests** — the same L3 `ceiling_for_rank(3)` grants. Read literally, FR-104 would make §14's G3 and G4 unreachable. Resolving it needs a spec decision (narrow FR-104 to G7-class modules, or lower §14's G3/G4), not a code change; recorded here so the conflict is not mistaken for a missing cap. |
| FR-105 measured strength before P5 | **Partly** (2026-10-14, ADR-0061) | The **measurement** is built: `MutationReport.measured_strength` is `killed / (total - discarded)` over a named closed operator set, `StrengthRefusal` names the five ways it is withheld (`NO_SUITE`, `NO_MODULE`, `MODULE_DID_NOT_IMPORT`, `NO_MUTANTS`, `BELOW_THE_FLOOR`), and `render_delivery(measured_strength=True)` threads it into `VerifiedClause.measured_strength` so FR-118's "by which oracle at which measured strength" is now two facts rather than one plus a disclaimer. **Not built, and the reason the row is Partly:** the **θ_lo comparison and the escalation**. FR-105 says a module below θ_lo "must be reported as unbuildable-at-autonomy and escalated, not built anyway", and θ is D3's calibration on a real repository — so nothing compares the number against a threshold, `THETA_GATE_BUILT` stays `False`, and the number is recorded and rendered rather than gating. The measurement runs at the render and is off by default, because it is the only input to a render that launches processes. |
| FR-106 operator examples held out | **Implemented for the context-assembly half (2026-10-13, ADR-0052); the holdout-existence half is not built** | `OracleDeclaration.held_out` (`views.py:905`) derives the holdout from the oracle class, because FR-103's rank-6 source column reads "operator-supplied cases" — so the class *is* the provenance and no `supplied_by` field was added. The factory had the defect FR-106 exists to prevent, reachable twice: `_oracle_lines` (`planner.py:248`) rendered the operator's `description`, `command_hint` and `expect_stdout_contains` into the producer's `verification_surface`, so the goal text printed the answer the *same goal's* boundaries forbade reading (FR-059); and `_command_output` (`verification.py:130`) built the violated reason as `f"stdout did not contain {required!r}"`, which `refutation_diagnosis` joins into the repair goal — so closing the planning door alone left the value arriving one phase later. Both doors are closed and tested independently: `TestAHeldOutOracleIsNamedAndNotDescribed` (6) and `TestTheHoldoutSurvivesTheRepairDoor` (2) in `test_planner.py`, `TestAnOracleIsHeldOutOrNot` (7) in `test_views.py`, 2 in `test_verification.py`. **The manufacturing door is now closed too** (2026-10-14, ADR-0061): `ConfiguredManufactureAdapter.manufacture` refuses `OracleClass.EXAMPLE` as its first statement, above the `supports` call and above the backend, because a backend is the part a deployment replaces — so no third-party backend can return a held-out oracle and re-open FR-106 by the manufacturing route. **Still not built:** holdouts *existing* for every lane above L2 and being versioned. FR-016 (no read access to holdouts) and FR-019 (isolation by deployment boundary) are **no longer blocked**: the boundary is measured and applied as of 2026-10-14 (ADR-0060), so FR-019's read half is enforced where a mechanism confines reads, and FR-106's own remaining half is the holdout *set* rather than the boundary that protects it. |
| FR-107 adversarial audit of oracles | **Implemented (2026-10-13, ADR-0053)** | `audit_oracles` (`audit.py`) runs every probeable oracle in an **empty workspace** via `OracleRunner` and judges it with `verification.verify` — the real runner and the real verifier, so the audit cannot report agreement with itself. An oracle that reports `SATISFIED` there was satisfied without implementing anything; that is the defect and a probe demonstrated it live (rank-1 `PROPERTY` with `command_hint="true"`: 0.0 debt, L4, `covers=True`, satisfied). `sofact audit` exits non-zero on a finding. Two skips are **reported, not passed**: negative clauses (an empty tree satisfies an absence by containing nothing — a true statement about an empty tree, not a weak oracle) and oracles naming no command (FR-108's debt, different remedy). `OracleAuditReport.discharged` returns `()` when nothing was probed, so a contract of intentions lands FR-107 in `not_implemented` rather than printing a green line. `ProjectState.oracle_audits` appended, never keyed. `TestAnOracleThatCannotFailIsAFinding` (6), `TestTheAuditSaysWhatItCouldNotAsk` (7), `TestTheServiceRecordsTheAudit` (5) in `test_audit.py`; `TestTheAuditVerb` (5) in `test_cli.py`. **A different instrument from FR-012–015's loop**, which is now built (ADR-0063): this audits the oracle *set* against an empty tree, that one attacks a single oracle's verdict by rewriting what it runs. |
| FR-108 per-module ground-truth debt | **Implemented** | One measure, `Contract.uncovered_clauses` (`views.py:999`), read by `Contract.ground_truth_debt` and by the cap; `contract.ground_truth_debt` delegates to it. The set is FR-108's own: **executable *and* rank ≤ 5** (`COVERING_ORACLE_MAX_RANK`), because FR-103's table calls rank 6–7 "sample, not coverage". `test_debt_counts_a_weak_oracle_even_when_it_runs` (`test_contract.py`). |
| FR-109 uncovered clauses cap at L2 | **Implemented (2026-10-13, ADR-0050)** | `Contract.ceiling` (`views.py:1019`) caps at `UNCOVERED_CLAUSE_CEILING` when `uncovered_clauses` is non-empty, so a rank-1 property *intention* no longer grants L4. `sofact contract` names the reason on the line that prints the number. `TestAnUncoveredClauseCapsTheCeiling` (6 tests). |
| FR-110 O8 Integration oracle class | **Implemented (2026-10-13, ADR-0051) — as a P7 check, not an enum member** | `check_boundary_contracts` (`integration.py`), reported as the `boundary_contracts` row; `IntegrationFindingKind.UNSATISFIED_BOUNDARY_CONTRACT`; FR-110 in `INTEGRATION_REQUIREMENTS`. `OracleClass` keeps its **7** members deliberately: every member is a *per-clause* shape (a `Clause` field, ranked, mapped by `_STEP_FOR_ORACLE` to the P5 session that discharges that one clause), and FR-110's own premise is that per-module verification "structurally cannot detect cross-module incoherence" — so O8 cannot be one of them. The gap was real and it was at P7: a consumer could import a **declared** dependency and call a name the producer never declared, and FR-113 (edge declared) and FR-112 (producer matches *its own* declaration) both passed. `test_the_neighbours_pass_while_the_boundary_fails` (`test_integration.py`). |
| FR-111 P7 build order | **Implemented** | `check_build_order` (`integration.py:650`); `test_a_module_built_before_its_dependency_is_a_finding` (`test_integration.py:331`). |
| FR-112 empty public-API diff | **Implemented** (2026-10-12, ADR-0027) | `check_interface_conformance` (`integration.py:754`), `public_surface` (`:700`), `Module.surface` (`views.py:510`); `test_a_declared_name_the_build_does_not_expose_is_a_finding` (`test_integration.py:422`), `test_a_declared_surface_discharges_fr_112_and_the_report_stops_naming_it` (`:513`). Discharged **only when a module declares a surface** — a proposal derives none, so the default report still names FR-112. |
| FR-113 no module reaches another's internals | **Implemented** | `check_imports` (`integration.py:216`); `test_a_module_reaching_another_without_declaring_it_is_a_finding` (`test_integration.py:157`). |
| FR-114 minimum violating set | **Implemented** | `attribute_files` (`integration.py:87`), `IntegrationReport.violating_modules` (`views.py:1348`); `test_the_repair_scope_is_the_findings_union_and_never_the_plan` (`test_integration.py:571`). |
| FR-115 system model conformance | **Implemented** (2026-10-13, ADR-0038) | `check_model_conformance` (`integration.py`), `SystemCriterion`/`SystemEntity.clause_ids` (`views.py`); `TestTheSystemModelConformance` (6 tests), `TestTheIntegrateVerb` (`test_cli.py`, 5 tests). Discharged when the approved specification declares a model whose entities a module owns — relationships and invariants are reported as **not** conformed. |
| FR-116 system-level acceptance criteria | **Implemented** (2026-10-13, ADR-0038) | `check_system_criteria` (`integration.py`), `Specification.system_criteria` (`views.py`), `--criterion` (`cli.py`); `TestTheSystemCriteria` (8 tests). A criterion spans ≥2 clauses and is satisfied only when every one carries a `SATISFIED` verdict; the verdict per clause is the worst in the log. |
| FR-117–121 P8 delivery, deploy gate, handover | **Partly** (2026-10-13, ADR-0040, ADR-0048) | **FR-117, FR-118, FR-119 and FR-121 are implemented.** `DeliveryReport`/`DeliveryGate`/`Handover` (`views.py`), `artifact`/`chain`/`verified_and_unverified`/`ceiling`/`handover`/`report` (`delivery.py`), `render_delivery`/`current_delivery`/`delivery_gate`/`approve_deploy` (`service.py`), `sofact deliver`/`sofact deploy` (`cli.py`); `TestTheDeliverVerb`/`TestTheDeployVerb` (`test_cli.py`, 11 tests), `test_delivery.py` (122 tests), `test_api.py` (33 tests). **FR-120's factory surface is built** (2026-10-13, ADR-0048): `sofact.api` publishes ten read-only operations behind one closed `MachineEnvelope`, `sofact api <operation>`/`--list` is the verb, and the four §3.3 human gates are refused by name with the human verb to use. **The delivered-system half is not built and is recorded as a producer obligation** — no oracle in O1-O8 observes whether an artefact is machine-usable, so the report names it in a `machine_surface_not_verified` check and `DELIVERY_REQUIREMENTS` keeps it in the list rather than dropping it. FR-117's image and IaC are reported as decisions (ADR-0005, FR-124) and the artefact check is scoped to the two the factory owes — **and the factory now writes those two** (2026-10-13, ADR-0044): `sofact.writing` renders `DELIVERY.md` and `RUNBOOK.md` deterministically from the report, `render_delivery` computes the delivery as a fixed point (render, write, render until a render agrees with disk), and `sofact deliver` requires `--root`. Before this, `sofact deliver` could not succeed on a fresh project: the factory reported its own output as missing. |
| FR-122 autonomy per phase and per module, lower governs | **Partly** (2026-10-13, ADR-0040/0041) | `delivery.module_autonomy` takes the **minimum** of `Contract.ceiling` (the weakest oracle, FR-007) and every module's `MODULE_CLASS_CEILING`, so a G7 module lowers a delivery the contract alone would have raised. `test_a_module_class_can_lower_the_delivery_below_the_contract`, `test_the_lowest_module_class_governs_when_several_disagree` (`test_delivery.py`). **No per-*phase* computation**, and nothing reports it at the gate rather than in the delivery report. |
| FR-123 Mode G delivery caps at L2 and must be reported | **Implemented** (2026-10-13, ADR-0041) | `MODE_G_CEILING` (`views.py`) is applied **last and unconditionally** in `delivery.ceiling`, including when no decomposition exists — a cap that failed open on missing input would be no cap. The report carries **two** numbers, `autonomy` (capped) and `module_autonomy` (not), because FR-123 asks for the *distinction*: one number cannot state "modules at L4 internally, delivery at L2". `autonomy_capped_for_mode_g` is a gate check and `sofact deliver` prints both lines. Canaried by removing the cap: `test_a_delivery_is_never_above_l2` and `test_the_cap_applies_with_no_decomposition` both fail. |
| FR-124 per-deployment topology ceilings | **Implemented for the ceiling half (2026-10-13, ADR-0045); packaging and egress are not read from the topology** | `DeploymentTopology`/`TOPOLOGY_ISOLATION`/`TOPOLOGY_MODIFIER`/`topology_ceiling`/`topology_refusal`/`HIGHEST_GRANTABLE` (`views.py`), `topology_statement`/`refused_by_topology` plus the `topology_ceiling_applied` and `topology_refuses_l4_at_a_degraded_deployment` gate checks (`delivery.py`), `SOFACT_TOPOLOGY`/`--override-topology` (`cli.py`), the two fields on `DeliveryReport` and `VerificationReport`, and the deployment lines in `DELIVERY.md`/`RUNBOOK.md` (`writing.py`). §5.4's modifier is a delta applied to the **modules'** number and not to the delivery's (FR-123's L2 cap is already at or below every topology's). FR-031's refusal is per module class and is a **failed machine check**, so `approve_deploy` refuses it with no second enforcement path; the override is a **name**, not a flag. T4 is reported as baseline with its unlock named rather than applied, because the blast bound it unlocks is one SoFact does not hold (FR-027). `TestTheTopologyIsATypeNotAComment`, `TestTheTopologyRefusesRatherThanDowngrades`, `TestTheRefusalReachesTheGate`, `TestTheReportStatesWhereItRan` (`test_delivery.py`), `TestTheTopologySeam` (`test_cli.py`, 5 tests). **Still open**: FR-040's "first-class configuration input" is satisfied for the ceiling and, since ADR-0060, for the *boundary* — the topology no longer decides whether a confinement layer exists, a measurement does, and that measurement is applied at both launch points. **Egress** moved on 2026-10-15 (ADR-0066): it is now *measured* — `DeploymentBoundary.egress` records a child watched being refused a loopback connect, and `topology_statement` prints it beside the modifier — so the row no longer names it as unread. What remains is **packaging** alone: nothing reads the topology to vary how an artifact is packaged, so the row is Partly on that half. |
| FR-125 G1–G2 target classes, class distribution reported | **Implemented** | `class_distribution` (`views.py:650`) reported in the gate (`decomposition.py:484`); `test_a_sound_proposal_passes_every_machine_check` (`test_decomposition.py:291`). |
| FR-126 G7 human-authored | **Implemented** | `MODULE_CLASS_CEILING` (`views.py:478`); `test_g7_is_the_only_l1_class` (`test_decomposition.py:217`), `test_every_g7_marker_classifies_as_g7` (`:204`). |
| FR-127 intent traceability graph first-class | **Implemented** (2026-10-14, ADR-0058) | `intent.py` — `build_graph`, `requirement_map`, `attributions_for` — plus `IntentNode`/`IntentEdge`/`IntentHop`/`IntentNodeKind`/`IntentGraph`/`EscapeAttribution` (`views.py`), `intent_graph`/`attributions` (`service.py`), `sofact intent` (`cli.py`), the `intent` machine operation (`api.py`), and an `## Escape attribution` section in `DELIVERY.md`. **The graph is the structure and FR-117's chain is a projection of it**: `delivery.chain` delegates to `IntentGraph.project()`, so the two cannot drift — a graph that merely rendered the same walk would have satisfied FR-127's word ("first-class component, not a derived report") and not its requirement. The three relations are held as directed edges because they are **not a chain in the log**: a clause cites its requirement (P2) and its module (P3) independently, so requirement and module are sibling branches and only the module reaches a step (P5), which makes the backward walk a hop instead of a search. `record_escape` gained a third refusal — a module the deployment did not build in that lane — because a module that did not break points the attribution at the wrong clause, which is worse than no attribution since it reads as a finding; `EscapeAttribution.narrowed` keeps an answer distinct from a candidate set on the type. `IntentGraph.gaps` reports a clause the decomposition dropped, which is a *worse* finding than an escape: nothing was built for it, so no escape can ever be attributed to it. 28 tests (`test_intent.py`), five canaries watched failing. |
| FR-128 model as single source of interface truth | **Implemented** (2026-10-13, ADR-0049) | The same mechanism as FR-083's second clause: the model declares the interface, the module binds it, and `propose` derives the binding rather than accepting one. This row and FR-083 were one gap counted twice; both close together. |
| FR-129 no shared model context across phases | **Partly** | `sofact.llm` is advisory and used only for elicitation advice; no other phase calls a model. Nothing *enforces* the separation. |
| FR-130 attributable approval | **Implemented** | `approve(..., by=…)` (`decomposition.py:493`); `test_approval_names_who_and_when` (`test_decomposition.py:340`), `test_half_an_approval_is_refused_by_the_type` (`:351`). |
| FR-131 UUID7 + version hash per artifact | **Implemented** | `uuid7str` shim, `content_hash` (`views.py:117`); `test_uuid7_is_version_7` (`test_views.py:38`), `test_content_hash_is_stable_across_a_model_round_trip` (`:76`). |
| FR-132 tiered declarative model config | **Implemented** (2026-10-16) | `sofact.tiers` splits the two facts the requirement names. **SoFact owns which phases need depth** — `TIER_PHASES` (`deep`: P3/P4/P6, `cheap`: P5/P7) and `STEP_PHASE`/`step_phase` mapping every `PlanStepKind` to the phase it runs in, with an assertion that refuses a kind with no assignment rather than defaulting one. **The deployment owns which model sits in each tier** — `ModelTier` (`name`, `model`, `rationale`, each refused when blank) read from `SOFACT_MODEL_TIERS` by `load_model_tiers`, two accepted shapes, refusing an empty table, an unknown field and a key/name disagreement. `resolve_model` states the precedence and returns the *source* with the model: `--model` → `tier:<name>` → `SOFACT_MODEL` → `DEFAULT_MODEL`. A phase in no tier falls through to the operator's **named** single model and reports `SOFACT_MODEL`, never silently to another tier's model; `phase_tier` returning `None` is "SoFact assigns no depth here", which is not the same as `cheap`. `DispatchRecord.model`/`model_source` record the resolution on every row, and `ConfiguredHarnessAdapter` binds the source so a record cannot claim another adapter's rule. A capability probe resolves no tier and records `model_source=None`, because the two arms must differ in one thing. `sofact tiers` prints the depth table and the resolution per phase. `TestTheDepthAssignmentIsSoFacts`, `TestThePrecedence`, `TestTheTierTypeRefusesAnEntryThatNamesNothing`, `TestReadingATable`, `TestTheStatement`, `TestTheCliReportsIt`, `TestADispatchIsTiered`, `TestADispatchRecordsTheModel` (`test_tiers.py`, 36). |
| FR-133 spend attributed per phase and per module | **Implemented** (2026-10-16) | `measure_spend` (`telemetry.py`) folds a plan's dispatches into `SpendReport` — `by_phase` and `by_module` buckets, each a `SpendAttribution` carrying dispatches, wall clock, tokens, `unmeasured_tokens`, models. **The phase key is derived, not stored**: `DispatchRecord` carries `step_id` and not the step's kind, so the fold reads the plan's steps and refuses (`ValueError`, naming the dispatch and the step) a dispatch naming a step the plan does not hold — guessing a phase would attribute spend to a phase it never ran in. The **module** key is `ModuleCheckout.module` (FR-100), and a dispatch with no module is counted in `unattributed` rather than dropped, so `by_module` plus `unattributed` equals the phase total. `tokens_observed` is `int | None` and `None` is *unmeasured*, never zero (NFR-024): `tokens_measured`/`tokens_complete` say whether the sum is exact and `tokens_per_dispatch` is `None` unless it is. **Against §1.3:** `SpendReport` has **no token dimension** because §1.3's envelope has none, and it says so in `token_envelope_note` rather than inventing a bound. The wall-clock comparison is the finding this unit's test caught: §1.3's `wall_clock_days` is a **target range (2–10 days), not a cap**, so a run under the floor is reported as *below* the envelope and explicitly **not an overspend** — `wall_clock_measurement` returns the `EnvelopeMeasurement` with a `detail` naming the direction, and `wall_clock_over_envelope` is `True` only above the ceiling. `sofact spend` prints both tables and exits non-zero on an over-ceiling run and on an empty one. `TestSpendIsAttributedPerPhaseAndPerModule`, `TestTheAttributionSaysWhatItLeftOut`, `TestTheEnvelopeComparisonIsMadeWhereThereIsADimension`, `TestTheSpendBucketTypeRefusesImpossibleSpend` (`test_telemetry.py`, 37). |
| FR-134 fine-tuned models must not be oracles/contract authors | **Partly** (2026-10-15, ADR-0064) | The **contract-authoring half** is built and measured: `sofact.authorship` walks the transitive import closure of `sofact.elicitation`, `sofact.contract` and `sofact.views` and reports the modules in it that can reach a model — 4 modules, none of them reaching. Reachability rather than a call-site count, because a call-site check passes the moment someone adds one. `AuthorshipCheck`/`AuthorshipFinding`/`AuthorshipSurface` (`views.py`), `LedgerKind.AUTHORSHIP_CHECKED`, `FactoryService.check_authorship()`, `sofact authorship` (`cli.py`), `TestTheDetectorTellsAReachableSurfaceFromAnUnreachableOne` (27, `test_authorship.py`) with the canary driven against a tree whose `contract.py` imports `sofact.llm`. **Not built:** the *identity* half. FR-134 is about a **fine-tuned** model and this build holds no tuning capability (FR-052 makes the target a deployment's choice), so there is no tuned model to name and the check establishes only that the path cannot reach one at all. `TUNED_MODEL_UNREACHABLE` says so and the report prints it beside the verdict rather than in a footnote. |
| FR-135 harness capability matrix | **Implemented** | `HarnessCapability` (`views.py:1416`, 10 rows); `test_probe_reports_every_capability_exactly_once` (`test_harness.py:442`). Rows `concurrent`, `bootstrap_empty_repo`, `goal_survives_compaction` are present and measured/attempted. |
| FR-136 contract → goal plan compilation | **Implemented** | `compile_plan` (`planner.py:576`); `test_every_goal_spec_has_all_six_required_parts` (`test_planner.py:509`). |
| FR-137 goals in the harness idiom, six-part shape | **Implemented** | `GoalStep`/`GoalSpec` (`views.py:1090`); same test as FR-136. |
| FR-138 termination is not verification | **Implemented** | `verify` takes no claim (`verification.py:232`); `test_verify_takes_no_completion_claim` (`test_verification.py:92`), `test_a_lying_producer_is_measured_not_believed` (`test_service.py:1108`). |
| FR-139 re-verify contract/goal/oracle hashes at completion | **Implemented** | `oracle_set_hash` (`contract.py:85`), `check_integrity` (`planner.py:712`); `test_an_undisturbed_plan_reports_intact` (`test_service.py:1192`). |
| FR-140 authority separation | **Implemented** | Budgets live in `StepBudget` (`views.py:1060`) and are enforced by killing the child (`harness.py:1072`); `test_exceeding_the_wall_clock_cap_is_budget_exhausted_not_failed` (`test_harness.py:886`), `test_a_spec_with_no_budget_flag_reports_that_rather_than_a_gap` (`test_harness.py:1068`). |
| FR-141 worktree per module | **Implemented** | ADR-0033 supersedes ADR-0024's deferral. `ensure_module_worktree` / `integrate_worktree` (`git.py`), `dispatch_step(isolate=…)` and `wave_is_isolatable` (`service.py:1396`), `--concurrent` (`cli.py`); `TestWorktreeIsolation` (`test_service.py:816`) and the FR-141 banner (`test_git.py:411`). The main tree holds the integration line; the module's branch lives only in its worktree. |
| FR-142 dispatch follows topological order, waves | **Implemented** | `dispatch_plan` (`service.py:1009`), `GoalPlan.waves` (`views.py:1182`); `test_steps_run_in_wave_order` (`test_service.py:745`), `test_the_default_is_not_concurrent` (`:805`). |
| FR-143 per-session telemetry | **Implemented** | `DispatchRecord` + `declaration_precision` (`service.py:1509`); `test_precision_now_measures_instead_of_reporting_zero` (`test_service.py:1167`). |
| FR-144 degrade where goal mode is absent | **Implemented** | `DispatchMode.SINGLE_SHOT` (`views.py:1533`), `capability_loss` (`views.py:1725`); `test_the_full_probe_measures_the_rows_the_quick_one_skips` (`test_cli.py:532`). |
| FR-145 no interactive prompt required | **Implemented** | `probe` kills a non-exiting child; `test_a_process_that_never_exits_is_unusable` (`test_harness.py:509`). |
| FR-146 drive harnesses not authored here | **Implemented** | `HarnessSpec.from_mapping` (`harness.py:236`), `load_specs` (`:406`); `test_a_round_trip_preserves_every_field` (`test_harness.py:603`). |
| FR-147 harness selection empirical | **Implemented** (2026-10-16, ADR-0073) | `measure_harnesses` builds one `HarnessMetric` per configured harness from the dispatches, plans, profiles, integrity checks and verdicts already in the log (`selection.py:112`), and `HarnessSelection.ranked` sorts on measured goal-declaration precision then seconds per verified module (`views.py:9200`). `HarnessMetric.exclusion_reason` refuses a goal-hacker by FR-139's integrity failures before the score is read, then an unprobed harness, then FR-135's disqualifying pair. `sofact select` (`cli.py:3139`) prints the ranking, the exclusions and the caveats; `TestTheSelectionOverRealDispatches` (`test_selection.py:708`) drives two harnesses through real child processes and asserts the measured one wins. `--harness` is now a fallback rather than the choice, and `discharged` is `()` whenever the answer was declared. |
| FR-148 capability matrix discovered at runtime | **Implemented** | `probe` (`harness.py:1072`); `test_an_unprobed_capability_reads_inconclusive_not_absent` (`test_harness.py:448`). |
| FR-149 hermetic invocation | **Partly** (2026-10-14, ADR-0060) | Flags are explicit in `HarnessSpec.argv` (`harness.py:443`); `test_pi_argv_matches_the_S19_measurement` (`test_harness.py:138`). **New:** the invocation is now wrapped in the measured boundary at the launch point, and the shipped Seatbelt profile denies egress by construction — `(deny default)` with no `(allow network*)`, measured once on this host as `EGRESS_DENIED_OR_DOWN`. **Still open:** the detector does not *probe* egress per run, so FR-152's "enforced and **proved** at the sandbox layer" is half satisfied — denied by the profile's construction and by a recorded one-time measurement, not by a per-delivery observation. `dsh`'s telemetry egress is still documented as unmitigated (`harness.py:590`) for a deployment that measures no boundary. |
| FR-150 context-file loading disabled in P5 | **Implemented** | `supports_context_file_flag` + goal text (`harness.py:1204`); `test_dsh_cannot_disable_context_files_but_pi_can` (`test_harness.py:166`). |
| FR-151 telemetry read from the session record | **Implemented** | `parse_usage` (`harness.py:765`), `parse_completion` (`:748`); `test_usage_is_summed_across_records` (`test_harness.py:357`). |
| FR-152 `--offline` is not the egress boundary | **Implemented (as a documented refusal)** | `harness.py:683,691` state it; `test_claude_notes_record_the_unconfined_child_and_the_egress` (`test_harness.py:206`). No boundary is built — the requirement is that none be claimed. |
| FR-153 goal entry forced, not requested | **Implemented** | `parse_goal_entry` (`harness.py:789`); `test_a_goal_typed_event_means_the_session_carried_the_goal` (`test_harness.py:419`). |
| FR-154 plugin composition frozen, pinned | **Implemented** (2026-10-14, ADR-0056) | `PluginComposition` (`views.py`) with `pins`, `admissions`, `argv_frozen`, `frozen`, `pinned_content`; `composition_for`/`load_composition`/`verify_composition` (`composition.py`), `SOFACT_COMPOSITION`, `FactoryService.composition`/`composition_hash`, `DispatchRecord.composition_hash` (FR-149, R29), and `sofact composition`. **The freeze is derived, not declared**: `HarnessSpec.freezing_flags` + `composition_frozen` compute from the spec's own `argv`, so `pi` is frozen by `--no-extensions`, `pi-research` is not (it drops the flag because the research loop *is* an extension), and `dsh` is not — reported as FR-154 not carried out rather than a clean freeze it does not have. `argv_frozen` is in the hash, and so are the admissions. A licence is required exactly on an admitted plugin (R28). `TestTheFreezeIsDerivedFromTheArgv`, `TestTheFreezeIsVerifiable`, `TestTheLoader`. |
| FR-155 third-party plugin deletion test | **Implemented** (2026-10-14, ADR-0056) | `PluginVerdict` (four values, because §8.7 reaches four — `BUILT_HERE` is code replacing the plugin, `SUPERSEDED` is FR-156's configuration remedy) and `PluginAdmission` over FR-155's five surfaces (`VERDICT_SURFACES`: completion, contract integrity, oracle strength, budget, egress). The type refuses an `ADMISSIBLE` verdict with a surface missing, a `REFUSED` verdict with every surface held, a surface outside the five, a `SUPERSEDED` with no setting named, and a licence on a plugin that is not installed. **The deletion test itself is not automated and cannot be** — whether removing a plugin changes a verdict is a question about a running system, and a function answering it from a table would be the manufactured-judge defect ADR-0053 refuses; what is built is the form the answer is written in. §8.7's eight-row table transcribes through the real loader in `TestTheDeletionTestOnTheMeasuredEcosystem`, which is the only check that the four verdicts are the right four. |
| FR-156 capability by configuration not code | **Implemented** (2026-10-14, ADR-0056) | `load_specs` (`harness.py`), `--tools`/`SOFACT_TOOLS`; `test_the_readme_example_loads_through_the_real_loader` (`test_cli.py`). Extended to the composition itself: `load_composition` reads JSON through the same seam and `SOFACT_COMPOSITION` names it, so a composition that could only be expressed by editing `src/` would be a capability obtained by code. The file cannot declare `argv_frozen` (read from the harness spec) and cannot name an unregistered harness. FR-156 is also the floor `PluginComposition.discharged` always returns — an empty composition *is* the configuration-only answer, which is why it is never the whole set by default. `TestTheConfigurationSeam`, `TestTheVacuousComposition`. |
| FR-157 deployment-scoped autonomy target | **Implemented** (2026-10-14, ADR-0057) | `DeploymentScope` (`views.py`) carries the target, and `EscapeReport.meets_target` is the comparison. The target is a **type** rather than a number because the two ways a declared target can be one this build cannot honour are structural and carry different remedies: a personal scope may not reach L4 (the gate "must not be imposed as a default", nor reached by declaring it), and a third-party scope may not either while `THETA_GATE_BUILT` is `False` (there the gate applies unchanged, and nothing measures an oracle strength to decide it). `None` means *this deployment declared none* — a product-supplied default would be the very gate D17 removed — so `meets_target` returns `None` rather than `False` when either input is missing. `load_deployment_scope` reads it through `SOFACT_SCOPE` (FR-156's rule reaching the declaration). What remains outside the requirement: **FR-024–035's θ gate was absent and is now built** (2026-10-17, ADR-0076), which is what bounded a third-party target to L2–L3 here: `THETA_GATE_BUILT` is `True`, so `admits_l4` no longer refuses the target on the instrument's absence, and the decision is `route`'s — a lane with no measured strength is `undecided` rather than L4, which is the distinction the flag exists to keep. The caveat on the scope's own report reads the same flag, so the sentence and the check moved together. |
| FR-158 evolvability debt reported as first-class, Mode M L1 | **Implemented** | `EVOLVABILITY_DEBT = 1.0` and `MODE_M_CEILING = L1` (`views.py:322`, `views.py:301`), the number surfaced as `DeliveryReport.evolvability_debt` beside FR-108's measured debt; `MAINTAINABILITY_NOT_VERIFIED` (`views.py:337`) is a `ClassVar` interpolating it, so the sentence and the number cannot drift; `MaintenanceLane.ceiling` refuses a lane above the cap and `delivery.handover` clamps §13's L4 lanes to it; the `maintainability_not_verified` check reports both ceilings as two numbers (FR-158(b)); both renderers and `sofact deliver` state it. 12 tests (`test_delivery.py::TestMaintainabilityIsNotVerified`). |
| FR-159 differential change-cost oracle | **Partly** (2026-10-14, ADR-0062) | `sofact.changecost` records the mechanical diff footprint of a **pinned** change unit — files touched, hunks, lines added and removed, modules crossed — read from git by `diff_footprint` (`git.py`, the one place SoFact touches git), and trends it per **declared scope**. `pin_unit` pins the unit before the work and stores the commit range as shas, because a unit chosen after its diff is a unit chosen by whoever wrote the diff. A scope with fewer than two measured units reports **unmeasured** rather than clean (ADR-0054's precedent), and a unit with no recorded range, no repository, or an unreadable diff is a row saying which rather than a zero. Four measured details, each canaried: a rename is one file and the tell is the empty *path* and not empty counts; a binary path is named, not zeroed; `modules crossed` is the package and not the layout; and a hunk count separates scattered edits from a contiguous one. **Still not built, and the reason the row is Partly:** a *baseline*, which needs a codebase history no single delivery has — so `discharged` returns `()` and the report says so by name. `MODE_M_CEILING` stays L1 and `EVOLVABILITY_DEBT` stays 1.0: FR-159 is a trend alarm and a ceiling *input*, never a verdict. The declaration is a deployment's (`SOFACT_CHANGE_UNITS`, read by `_configured_change_units` and refused by name when malformed), the measurement is opt-in (`sofact deliver --change-cost`), and the trend is printed beside FR-158's debt with its three caveats and never as a verdict. 32 tests (`test_changecost.py`), plus the seam driven end to end in `test_cli.py::TestTheChangeCostSeam` (5) and the render path in `test_delivery.py::TestTheChangeCostReachesTheReport` (4). |
| FR-160 gate-cost measurement | **Implemented** | `GateCost` (`views.py`) carries the pair FR-160 names — `human_minutes` and `rework_fraction` — and `FactoryService.record_gate_cost` refuses a cost for a gate whose phase is not complete, because the approval is the evidence a human was there. `ProjectState.gate_cost` reads the latest per gate so `total_human_minutes` cannot double-count a re-measure, and `None` means unmeasured rather than free. `envelope.measure(human_minutes=...)` now measures §1.3's `HUMAN_MINUTES` (one fewer unmeasured dimension), the pair travels into `DeliveryReport.gate_costs` with a mean `rework_fraction`, and the `gate_cost_reported` check reports without failing on an unmeasured project. `sofact gate --cost P2:90:0.25` records one; `sofact deliver` prints the pair under its own heading (ADR-0043). 4 + 4 + 6 tests; canaried three times. |
| FR-161 adapter table is data, not code | **Implemented** | `HarnessSpec.from_mapping` refuses unknown/missing fields by name (`harness.py:236`); `test_a_malformed_field_is_refused_by_name` (`test_harness.py:640`), `test_an_unknown_field_is_refused` (`:662`). |
| FR-162 verdict describes one attempt | **Implemented** | `verify` run-scoped (`verification.py:232`); `test_a_verdict_can_be_scoped_to_one_run` (`test_verification.py:114`), `test_scoping_to_a_run_that_observed_nothing_is_insufficient` (`:135`). |
| FR-163 completed session triggers the check | **Implemented** | `check_dispatch` returns `None` unless `outcome == COMPLETED` (`service.py:523`); `test_a_completed_dispatch_is_checked_without_a_declaration` (`test_service.py:1127`), `test_a_failed_session_is_not_checked` (`:1148`). |
| FR-164 probe reports model resolution | **Implemented** | `HarnessCapability.MODEL_RESOLVED` (`views.py:1416`); `test_the_probe_records_the_refusal` (`test_service.py:457`). |
| FR-165 undecidable row measured by differential | **Implemented** | `test_an_unprobed_capability_reads_inconclusive_not_absent` (`test_harness.py:448`), `test_a_quick_probe_skips_the_rows_that_need_a_second_child` (`test_service.py:423`). |
| FR-166 key then reuse | **Implemented** | `verdict_cache_key` (`verification.py:71`), `VERDICT_REUSED` (`views.py:1848`); `test_an_unchanged_workspace_reuses_the_verdict` (`test_service.py:1336`), `test_a_changed_artefact_is_measured_again` (`:1373`). |
| FR-167 research is dispatched, not performed | **Implemented** | `research` (`service.py:1326`); `test_a_completed_loop_records_the_report_and_its_sources` (`test_service.py:1453`), `test_a_truncated_loop_is_a_fact_not_a_failure_to_report` (`:1481`). |
| FR-168 a spoken goal, and the audio digest it came from | **Implemented** (corrected 2026-10-16, ADR-0075) | `TranscriberSpec`/`load_transcriber_specs`/`TRANSCRIBERS`/`parse_transcript` (`transcribe.py`), `speak` (`service.py`), `sofact speak` (`cli.py`); `test_transcribe.py`. The transcript is read from the file the tool wrote rather than from stdout, and the audio's SHA-256 is recorded — a transcript whose digest is not the audio you passed is not a transcript of it. **No built-in entry ships**, because no speech-to-text tool is a dependency of this product. |
| FR-169 the competitive baseline is a cited artefact, and an unsourced rival does not count | **Implemented** | `CompetitiveScan`/`Competitor`/`CompetitorCapability`/`parse_scan` (`competitive.py`), the competitive section in `research_goal` (`service.py:255`), `competitors` (`service.py`), `sofact competitors` (`cli.py`); `test_competitive.py`. A competitor with no `source_ids` is recorded **unsourced** and excluded from the baseline; one with no capabilities is **unexamined**; a scan over zero sourced competitors reports `None`, never `0` (NFR-024). SoFact cannot name the best systems in an arbitrary domain, so the producer identifies them under a criterion SoFact writes, and the identification is an artefact with its own evidence. |
| FR-170 an exceedance is a declaration against a cited baseline | **Implemented** | `ExceedanceDeclaration` (`views.py`), `declare_exceedance`/`exceedances` (`service.py`), the `exceedance_declared` check (`delivery.py`), `sofact exceed` (`cli.py`); `TestTheExceedanceIsDeclaredNotVerified` (`test_delivery.py`). A baseline with no source ids is refused — a claim to exceed nothing is a wish. **No oracle in O1–O8 compares two systems**, so the check reports `N declared, 0 verified by oracle` with `passed=True` and the obligation stays in `DELIVERY_REQUIREMENTS`: nothing may print an exceedance as a verified capability. |
| FR-171 the specification document is rendered at P2 and every requirement annotated | **Implemented** (2026-10-16) | **Corrected 2026-10-16 (ADR-0071): it is rendered *before* the approval, not after it.** `SPEC_DOC_HEADINGS`/`RequirementAnnotation`/`annotate`/`render_specification_document` (`specdoc.py`), `write_specification` (`service.py`), `sofact spec-doc` (`cli.py`); `test_specdoc.py`. Every requirement carries its provenance — the stem it descends from, that stem's elicitation dimension, the answer's id **and whether it was operator or `model:` and whether it was attested**, the research verdict, the competitor capabilities, the exceedance, and the oracle's class and rank. An unattested requirement is visibly unattested with the marker derived from the ledger, so the document cannot be rendered clean over a specification whose answers nobody read. |
| FR-172 one verb drives the pipeline, stops at every gate, and is idempotent | **Implemented** (corrected 2026-10-16, ADR-0075) | `DriverAction`/`DRIVER_ACTIONS`/`run_goal` (`driver.py`), `DriverRun`/`DriverStep`/`DriverTerminal`/`DriverOutcome` (`views.py`), `record_driver_run`/`current_gate_checks` (`service.py`), `sofact build` (`cli.py`); `test_driver.py`. **No branch returns `DELIVERED` with a gate open**, and the driver has no code path that advances one (FR-061) — it halts at each of the four in turn and `--resume` continues from the ledger, because the loop re-reads state rather than holding a cursor. Idempotency is asserted on ledger length. **Four defects the end-to-end walk found, all one shape — a name that reads as an instruction and is not one:** `approve_gate` decided on the frozen presented row, so a gate whose defect was repaired could never be passed; the driver named the approval for a gate whose machine half had failed, a verb that can only refuse — and named it `gate approve`, which the CLI does not accept, as every printed approval did; and the build guard read `sealed_dispatches`, which filters on reviewability, so a producer that commits its own work left it empty and the whole plan was re-dispatched 64 times until the run reported `exhausted` on a completed build. |
| FR-173 a model-proposed answer does not resolve a dimension | **Implemented** | `MODEL_ANSWER_PREFIX`/`ElicitationAnswer.is_model_proposed`/`ElicitationAttestation` (`views.py`), `assess(..., attested=...)` (`elicitation.py`), `propose_answers`/`attest` (`service.py`), `sofact attest` (`cli.py`); `TestAModelProposalIsNotAnAnswer` (`test_elicitation.py`). A model-proposed unattested answer is reported **open** with the proposal's id, so `draft` cannot be reached; an attestation whose `attested_by` is itself model-prefixed is refused. The floor stays deterministic — what changes is that a paragraph a model wrote can no longer clear it on the operator's behalf. **Attestation records that a human read an answer, not that it is correct.** |
| FR-174 SoFact authors its own search queries and every hit is a lead | **Implemented** | `SearcherSpec`/`load_searcher_specs`/`authored_queries`/`parse_search_results` (`search.py`), `search` (`service.py`), `sofact search` (`cli.py`); `test_search.py`. The queries are composed from the goal's own words **before any provider runs** and written into the log, so what was asked is answerable from the ledger alone — a provider asked what to search for chooses its own subject list. Every hit is recorded at `VerificationStatus.REPORTED` and `SearchHit` refuses to be constructed at `CONTENT_VERIFIED` at all; a hit with no url is refused; a failed query is recorded as failed rather than as a domain with no results. |

### Counts

Recounted from the table above on 2026-10-14 after the FR-102 attempt-telemetry unit,
by reading the verdict cell of every row with a script rather than by arithmetic on the
previous snapshot — the earlier numbers in this file (47/21/1/48, then 59/28/1/31, then
67/26/0/26, then 69/25/0/25, then 71/25/0/23, then 72/25/0/22, then 76/26/0/17, then
86/26/0/7) did not match the rows they claimed to count. The script reads the cell rather
than grepping the line, because a row whose *evidence* names another verdict would
otherwise be counted twice; it classifies on the cell's **leading** token, so the rows
whose verdict carries a date or a qualification still land in the right bucket.

****The previous snapshot was itself stale, and the recount found it.** Running the script
against `HEAD` gives 85/25/0/9 where the file recorded 76/26/0/17 — nine rows had been
closed by the ADR-0035..0053 units without the count being moved, which is the same
class of defect this audit exists to find in other people's documents. The ADR-0054 unit
moved exactly two rows (FR-021-023 Not built → Implemented, FR-157 Not built → Partly),
so 85/25/0/9 became 86/26/0/7; the FR-102 unit moved one (Partly → Implemented) to
87/25/0/7, the ADR-0056 unit moved two (FR-154 Partly → Implemented, FR-155 Not built →
Implemented) to 88/25/0/6, and the ADR-0057 unit moved one (FR-157 Partly → Implemented).

**The 2026-10-14 A2 unit (ADR-0060) moved no row's verdict, and the count is
re-derived rather than adjusted.** The three rows it touches — FR-016–020, FR-059,
FR-149 — each already read Partly for a half that is *still* open after it (a per-lane
holdout set, a per-run egress proof, packaging read from the topology), so a verdict
that moved would be a verdict inflated by the work rather than measured by it. What did
change is that the prose line and the table below **disagreed** on the same tree: the
line read `89/24/0/6` and the table `91/22/0/6`. The table was right. Re-running the
classifier over all 119 rows gives **91/22/0/6**, and the discrepancy is the counting
rule the previous refresh stated but did not fully apply — it named **FR-106** as the one
row whose cell leads with "Implemented" and then names a missing half, and **FR-124** is
a second. FR-124's missing half was named in its *evidence* cell
(`**Still open**: … nothing reads the topology to change packaging, egress, or the
container boundary`) while its *verdict* cell read bare `**Implemented**`, so the row was
Partly by what it said and Implemented by the one cell the rule's statement named. Two
rows, not one, which is exactly the 2-row gap between the line and the table. Both are
Partly now, the line and the table are one number, and that number is **derived from the
rows by a test rather than trusted** — `TestTheRoadmapTallyIsDerivedFromItsRows` in
`tests/ci/test_docs.py` reads every row, classifies it by the rule below, and fails when the
published table disagrees (ADR-0065). Until 2026-10-15 that sentence was a claim about a
check that did not exist, which is the one documentation claim that goes false silently.
**FR-124's verdict cell was brought into line on
2026-10-15**, in the refresh that found the rule's statement was narrower than the
classifier behind it: it now reads `**Implemented for the ceiling half …; packaging and
egress are not read from the topology**`, which is the shape FR-106 already had. The count
did not move — the classifier had been counting the row Partly through the `**Still open**`
marker all along, which is why the statement and the arithmetic disagreed while the
arithmetic and the table agreed.

**The 2026-10-14 B2 unit (ADR-0061) moved two rows, and the arithmetic is stated
because it is the only way to check it.** FR-008–011 and FR-036 leave **Not built** for
Partly; FR-103 and FR-105 were already Partly and stay there while their cells change
from "nothing manufactures" and "nothing measures" to a built seam and a measurement
with the θ comparison still absent. So Partly rises by two and Not built falls by two:
`91/22/0/6` becomes **`91/24/0/4`**, re-derived by re-running the classifier over all
119 rows rather than adjusted by hand.

**The 2026-10-14 FR-159 unit (ADR-0062) moved one row, and the arithmetic is stated for
the same reason.** FR-159 leaves **Not built** for Partly — the instrument, the trend, the
alarm and the unmeasured baseline are built, and what is absent is a *baseline*, which
needs a codebase history no single delivery has. So Partly rises by one and Not built falls
by one: `91/24/0/4` becomes **`91/25/0/3`**, re-derived by re-running the classifier over
all 119 rows. **The 2026-10-15 FR-012–015 unit (ADR-0063) moved one row**, and the
arithmetic is stated for the same reason every refresh states it: FR-012–015 leaves **Not
built** for Partly — the loop, the fixer, the sampling rule with its escalation, the lane
and the rate are built, and what is absent is the two techniques that need a model to
invent code. So Partly rises by one and Not built falls by one: `91/25/0/3` becomes
**`91/26/0/2`**, re-derived by re-running the classifier over all 119 rows. Implemented is
unchanged, which is the honest direction: a row that leaves Not built for a half-built state
does not become Implemented.

**The 2026-10-15 FR-053/FR-055/FR-134 unit (ADR-0064) moved the last two rows, and it is the
refresh that empties the Not built column.** FR-052–056 and FR-134 both leave **Not built**
for Partly — each names a half that is not built and says so in its own verdict cell, which is
this document's counting rule rather than a judgement about how much was done. For FR-134 that
half is the *identity* half: the closure is measured and the model is not in it, but FR-134 is
about a **fine-tuned** model and this build holds no tuning capability, so the check can
establish only that the authoring path cannot reach a model at all. For FR-052–056 it is three
of six requirements — FR-052, FR-054 and FR-056 are deployment decisions and a staging
sequence that no module here discharges. So Partly rises by two and Not built falls by two:
`91/26/0/2` becomes **`91/28/0/0`**, re-derived by re-running the classifier over all 119 rows.
Implemented is again unchanged, and the direction is worth stating once more: a row that names
a missing half is Partly however much of it is built, which is why two rows leaving the last
column does not move a single row into the first.

**The FR-103 cell is deliberately left as Partly rather than promoted.** Its first draft
led with "Implemented for ranks 1, 3 and 5", and the classifier caught it on the run
that checked the count: this document's counting rule reads the **leading word**, so a
cell that leads with "Implemented" and names the missing half inside the verdict's own
qualification is exactly the shape the rule was written to stop — FR-106 and FR-124 are
the two rows it was written for, and a third would have re-opened the hole from the
other side. Rank 6 is not "a half still missing": it is a class the factory refuses by
design (ADR-0061), and ranks 2 and 4 are unbuildable from what a contract carries. That
is a real limitation and the verdict says so.

The `Implemented` count includes FR-152's row, whose cell reads
`**Implemented (as a documented refusal)**` — the one verdict spelled with a
qualification rather than as the bare word, and so the one a prefix match would silently
drop. That is why the tally is **derived from the row count by a test** (ADR-0065) rather
than trusted, and why the derivation splits each row on the pipe rather than matching it
with a regex: an evidence cell contains `|`, so a non-greedy pattern reads 77 rows where the
table has 126.

| Verdict | n |
| --- | --- |
| Implemented | 102 |
| Partly | 24 |
| Deferred (ADR-0024) | 0 |
| Not built | 0 |
| **Total rows** | **126** |

Rows, not FR numbers: several rows cover a stated range (FR-008–011, FR-016–020), so
this counts the classification units rather than the FR identifiers inside them.

**The 2026-10-16 front-door unit (ADR-0070, ADR-0071) added seven rows and moved none.**
FR-168 through FR-174 — transcription, the competitive baseline, the exceedance
declaration, the specification document, the driver, attestation and SoFact's own search —
are new requirements rather than newly-satisfied old ones, so every one of them enters at
**Implemented** and the arithmetic is `91/28/0/0` becomes **`98/28/0/0`** over **126** rows.
Implemented is the honest class for each: every row names a module, a service method, a verb
and a test module that fails if the behaviour is removed, and each verdict cell states the
limit that is *inside* the requirement rather than a missing half of it — FR-170's oracle
count is zero by design because no oracle class compares two systems, FR-169 reports `None`
rather than `0` over an empty baseline, and FR-172's driver stops at four gates because
FR-061 makes a gate a hard stop. A limit the requirement itself names is the requirement
discharged; a limit the requirement does not name is the Partly column, and none of these
seven has one. Re-derived by re-running the classifier over all 126 rows rather than adjusted
by hand.

**The 2026-10-16 depth unit (ADR-0072) moved two rows and stated no arithmetic, which is the
omission this paragraph repairs.** FR-132 and FR-133 both leave **Partly** for Implemented —
the tier table with its two owners and the spend fold with its two attributions are built, and
each row's cell now names the module, the verb and the test module rather than the missing half.
So Implemented rises by two and Partly falls by two: `98/28/0/0` becomes **`100/26/0/0`** over
**126** rows, re-derived by re-running the classifier rather than adjusted by hand. The
arithmetic was absent from the tree for the length of one commit, which is exactly the drift
ADR-0065 exists to catch; the *table* was right and the *sentence* was missing, so no check
fired.

**The 2026-10-16 FR-147 unit (ADR-0073) moved one row.** FR-147 leaves **Partly** for
Implemented: `sofact.selection` measures every configured harness from the log and ranks on
goal-declaration precision then throughput, so "nothing chooses a harness from the
measurement" is no longer true. So Implemented rises by one and Partly falls by one:
`100/26/0/0` becomes **`101/25/0/0`**, re-derived by re-running the classifier over all 126
rows. FR-143's row is untouched — `declaration_precision` remains scoped to one harness,
because that is what FR-143 asks for; FR-147 is the requirement that compares them.

**The 2026-10-16 routing unit (ADR-0074) moved no row's verdict, and the count is
re-derived rather than adjusted.** FR-024–035 stays **Partly**, and the verdict cell is the
reason: the row's missing half was named as three things, and this unit discharges one of
them. SoFact can now read a module's declared `ReasoningClass` and pick a lane with it —
`REASONING_CLASS_TIER`/`class_tier` and the branch in `resolve_model`, with `dispatch_step`
supplying the class so the declaration reaches `DispatchRecord.model_source`. What is still
absent is the rest of §5.1's routing function — `admissible(lane)` and `ceiling(lane)` are
not computed from an oracle strength or a measured blast radius — plus FR-024's autonomy
ladder and FR-027's T4 blast radius. The row was Partly for three missing halves and it is
Partly for two, which is the same class: this document's rule is that a row naming a half
that is not built is Partly however much of it is built, and the direction matters — a row
is not promoted because a third of it landed. The tally is therefore unchanged at
**`101/25/0/0`** over **126** rows, re-derived by re-running the classifier rather than
adjusted by hand.

**The 2026-10-16 ordering unit (ADR-0071, corrected) moved no row and closed a defect
inside one.** FR-171's verdict was already **Implemented** and stays there: the module, the
verb and the test module all existed and every one was exercised. What was wrong was the
*order* — `write_specification` required the P2 gate to have been passed, so the document
could only ever be rendered to someone who had already decided, and `sofact spec-doc
--approve` refused before the approval it performs. Three defects shared that root: the
driver opened P2's gate without writing the artefact the gate is a gate on,
`approve_specification_document` recorded the approval in the ledger and left the file on
disk saying "not yet", and the CLI test that should have caught the first ran `specify
--approve` before `spec-doc` — the sequence the defect forced on anyone using the product.
So the arithmetic is `101/25/0/0` **unchanged** over **126** rows, re-derived rather than
assumed, and the direction is worth naming: a verdict class counts whether a requirement is
discharged, not whether it was discharged correctly the first time. The row's evidence cell
carries the correction, because a reader who trusted the bare "Implemented" would re-derive
the same wrong order from the same sentence.

**The 2026-10-16 front-door unit (ADR-0075) moved no row, fixed four defects inside
two already-Implemented ones, and found two gaps that are still open.** FR-168 (a spoken
goal) and FR-172 (one verb drives the pipeline) were both **Implemented** and stay there:
the modules, the verbs and the test modules existed, and the test modules passed. What was
wrong is that the product did not run. `sofact build` against a fresh home at the shipped
defaults failed at P0 three times over — a completion cap of 1024 that two of the six
dimension prompts P0 then asked exhausted inside the model's reasoning channel, a refusal
that reported "only a reasoning channel" for a `finish_reason: "length"` the response
stated plainly, an unreachable endpoint printed as `unreachable: .` because every httpx
transport error stringifies to `""`, and a stop whose own two lines named different next
commands
(`build --resume` above, the questionnaire below) when the verb that works is `attest`. The
fourth is the one that matters most, because it is the only route past a gate: **every
printed approval read `sofact gate approve P2 --by you`, and the `gate` command's option is
`--approve`**, so the single verb that passes a gate exited 2 with `Got unexpected extra
argument(s) (approve P2)` for every operator who typed what the product told them to. It
appeared in five files and every test that covered it compared the string to a literal
written from the same misreading — the one assertion that cannot fail. The replacement
check invokes the **installed CLI** on every verb the product prints, which is the only
oracle for "is this a command". Every one of the four is a defect *inside* a discharged
requirement rather than a missing half of one, which is why no verdict moves: the counting
rule asks whether a requirement is discharged, and this document has already stated that
it does not ask whether it was discharged correctly the first time. The tally is therefore
`101/25/0/0` **unchanged** over **126** rows.

**The two gaps the same walk found are open, and neither is a verdict to move.** Both
are reachable from the front door at the shipped defaults, and neither is a wording defect.
Neither is an unbuilt half of the row it sits under either, which is why the tally stays
where it is rather than being adjusted by work that did not discharge it:

- **FR-068's action column names a remedy nothing implements.** The walk reached P2, P1
  having classified twelve of the draft's thirty-six clauses `invalidated`/`deepened`, and
  the pipeline refused — correctly, since the spec's own table says "Return to P0. Do not
  build." But **P0 cannot be re-entered**: `advance_phase(P0, ACTIVE)` raises "P0 is already
  complete; a phase is not re-entered by advancing it again (FR-060)", and `sofact draft`
  re-emits *the same thirty-six clause ids* from the same answers, so re-eliciting produces
  the same draft, the same ids, and — with the same sources — the same verdicts. The only
  verb that touches the clauses, `sofact draft`, takes no input with which to revise one.
  So the recovery `sofact build --resume` prints after this refusal re-selects `decompose`,
  which refuses identically: three runs, byte for byte. **A pipeline stopped by its own
  evidence has no documented exit.** FR-068 is not the row that is short: its requirement is
  that every clause is *classified*, the classification is delivered, and the refusal to
  build on an invalidated premise is enforced in `advance_phase`, where it cannot be routed
  around. What is missing is a **recovery verb** — "revise the clauses and re-elicit" is an
  action column with nothing behind it — and that is a requirement the spec does not state,
  rather than a half of one it does.
- **A `FAILED` run's `next_human_verb` is `RESUME_VERB` for every failure, including the
  ones a resume cannot act on.** The third defect above was fixed for the two `EXHAUSTED`
  waits and not for `FAILED`, so the loop above is what the operator is told to run. Whether
  a resume can act is a fact about *why* the run failed, and the driver holds it.

Neither gap is fixed here. Both need a design decision — what "revise the clauses and
re-elicit" is as a verb, and whether a `FAILED` run carries the action it failed on — and
neither is a wording change. They are recorded because a walk that stops at the first
refusal it can explain leaves the next operator to find the second one.

The finding worth carrying forward is about evidence rather than about these bugs: **1987
passing tests said nothing about whether `sofact build` runs**, because no test drives the
front door at the shipped defaults against a reachable model — every test of that path
either configures no model, and so stops on the unreachable branch, or answers the
interrogation itself. ADR-0075's five canaries and the six live probes are the record.

**The counting rule, stated because the last refresh did not state it, and corrected on
2026-10-15 because the statement was narrower than the classifier it described.** A row is
**Partly** when **either** of two things holds:

**The 2026-10-17 routing unit (ADR-0076) moved no row's verdict, and the count is
re-derived rather than adjusted.** FR-024–035 stays **Partly**, and the reason is the same
one the ADR-0074 note gives: the row names what is missing, and this unit discharges two of
the three halves it named while a third stays. Built: §5.1's `admissible(lane)`,
`ceiling(lane)` and `level(lane)`, computed by `sofact.routing` from the terms the log
already held — including **θ**, the term that genuinely did not exist, which is what moves
`THETA_GATE_BUILT` to `True`. Still absent: FR-027's **measured** blast radius (ADR-0045
named it as what T4 unlocks; `ModuleBudget` is still the proposer's declared number) and any
**dispatch-time** consultation of a routing decision, so the ladder is a reading of the log
rather than an interlock. A row naming a half that is not built is Partly however much of it
is built, so the tally is `101/25/0/0` **unchanged** over **126** rows, re-derived by
re-running the classifier over all 126 rather than adjusted by hand. Two rows *inside* the
class moved their evidence without moving their verdict, and both moved in the same
direction — an absence that had been recorded as still absent is now built:
**FR-008–011**'s "thresholds half" (the θ_lo comparison FR-105 names) and **FR-157**'s
caveat, which recorded FR-024–035's θ gate as the thing bounding a third-party target to
L2–L3. Both keep their verdicts because both name a half that is still missing — the
**trend** across history for one, and nothing for the other beyond the gate it was never
short of — which is the counting rule working as stated rather than a promotion by
proximity.

**The 2026-10-17 elicitation unit (ADR-0077) moved one row, and the row it moved had
been counted wrong in both directions.** FR-064 leaves **Partly** for **Implemented** and the
tally is `102/24/0/0` over **126** rows, re-derived by re-running the classifier over all
126 rather than adjusted by hand. The gap was recorded as "the enum has 6, the spec lists
7", and neither number was the fact: five of the spec's rows were present, **two were
absent**, and the enum carried **two the table does not list** — `CONSUMER`, split out of
the table's single *Success* row, and `ORACLE`, FR-067's `verification_method`, which the
module documents as producing no clause. So the target was eight, and no member order
reproduces the table. **What the row could not have shown, because it counted instead of
reading:** *Non-negotiables* had not been dropped at all — it was folded into
`CONSTRAINT`'s own question ("What are the non-negotiables — platform, stack, dependencies,
time?"), where it asked about the stack, while the spec's *Constraints* row was asked
nowhere. A missing question with a plausible answer already sitting in its place is
invisible to a count, which is the general form of this class. The verdict is Implemented
because the limit inside it is the requirement's own: FR-064 requires the dimensions be
*asked*, and a scale clause's oracle is prose, so it is declared and visibly unmet rather
than verified. R19's second half — "P0 must resolve scale" — is a question now and not a
bound, and the ADR records that as a gap rather than letting a recovered dimension read as
a discharged risk.

1. **its verdict cell names an unbuilt half**, *including* a cell that leads with
   "Implemented" and then names the half that is missing; or
2. **its evidence cell carries the `**Still open**` marker**, which is how a row that was
   promoted to a bare `**Implemented**` verdict and later found to have a half left states
   that half without disturbing its stamp.

The document's own definition of Partly is "the named half that is missing", so the most
honest rows in the table would otherwise be the ones counted as complete. **Both disjuncts
are load-bearing and the second is the one the previous statement omitted.** Re-running the
two-disjunct rule over every committed revision reproduces the table each refresh published
— `91/22/0/6` at ADR-0060, `91/24/0/4` at ADR-0061, `91/25/0/3` at ADR-0062, `91/26/0/2` at
ADR-0063 — and the one-disjunct statement reproduces none of them: it reads every one of
those tables one Implemented too high, because **FR-124** is counted Partly by disjunct 2
alone. That is the check a stated rule needs: run it against the tables the refreshes
actually published, not only against the current tree, or a rule that has quietly narrowed
agrees with itself and disagrees with every number beside it.

The two rows the rule was written for are **FR-106** (ADR-0052), which leads with
"Implemented for the context-assembly half" and names the holdout-existence half as not
built, and **FR-124**, whose half sat in its evidence cell under `**Still open**` while its
verdict cell read bare `**Implemented**`. FR-124's verdict cell was rewritten on 2026-10-15
to name the half in the cell the first disjunct reads, which moved the count by nothing —
the count had already read the row as Partly through the second disjunct. Both are Partly
either way, and that is the point: the two disjuncts exist because a row can state its half
in two places, and a rule that reads one of them is a rule that agrees with its own
arithmetic and disagrees with the table.

**One published table does not reproduce, and it is the one that predates the rule's
first disjunct being applied.** Running the two-disjunct rule over the pre-A2 tree
(`c3c2057`) gives `90/23/0/6` where that refresh published `91/22/0/6`, and the single row
responsible is **FR-059**, whose verdict cell read a bare `**Partly**` there. The refresh
states its own convention in the paragraph above its table — it "classifies on the cell's
**leading** token" — so its own rule counts FR-059 as Partly, and the table it published
did not. That is the same staleness its prose confesses for nine other rows, found by the
same recount that wrote the rule; ADR-0060 then promoted FR-059's cell to "Implemented
where a boundary holds", which is the honest form for a capability that holds only where a
mechanism confines reads, and every table from ADR-0060 onward reproduces exactly. The
discrepancy is recorded rather than smoothed over because a rule validated only against the
current tree would have looked clean at every refresh while the two oldest numbers in the
file disagreed with the rows beside them.

Closed since the 2026-10-13 refresh: **FR-154** (Partly → Implemented) and **FR-155**
(Not built → Implemented), both 2026-10-14, ADR-0056; **FR-157** (Partly → Implemented),
2026-10-14, ADR-0057; **FR-127** (Partly → Implemented), 2026-10-14, ADR-0058 — the row
the 2026-10-12 audit called the most valuable learning signal the product produces and
could not connect to anything; **FR-091** (Partly → Implemented), 2026-10-14, ADR-0059 —
the row the audit **downgraded on inspection** for want of a test, restored now that the
minimisation, its rule and its tests exist. **FR-012–015** (Not built → Partly),
2026-10-15, ADR-0063 — the loop is built and the two model-needing techniques are reported
as not attempted. **FR-052–056 and FR-134** (Not built → Partly), 2026-10-15, ADR-0064 — the
authoring surfaces are measured as unable to reach a model, and the halves that remain (a
tuning target, a recipe, a staging sequence, and the identity of a tuned model that does not
exist) are named in their cells. **No row remains Not built.**

NFRs are not tabulated: NFR-001–024 are retained verbatim from v0.1 and are not
restated, so there is nothing to check them against. Of the new ones, **NFR-025
(envelope) is now implemented** (2026-10-13, ADR-0039): §1.3's eight dimensions are a
type, the envelope is loaded from JSON with *unset* as a distinct state, and
`measure` returns the actuals the delivery report must carry. NFR-030 (per-module
attribution) is **not built**; NFR-027 (version-controlled artifacts) is **partly**
(ledger + reports); NFR-028 (resume) is **not built**; NFR-029 (per-phase wall-clock
bound) is **partly** (per-step only).

---

## 2. Gaps, ranked by what they block

1. ~~**No system model and no P2 specification (FR-076, FR-078, FR-083, FR-115,
   FR-116).**~~ **Mostly closed 2026-10-12.** P2 now produces a `Specification` —
   requirements traceable to clauses, a machine-readable model of entities,
   relationships and invariants, non-goals, assumptions and a value hypothesis — and
   gates on it. What remains of this gap, named so it does not read as finished:
   **FR-083 closed 2026-10-13** (ADR-0049): the model declares the interface, the
   module binds it, and `propose` derives the binding, so a proposal cannot disagree
   with its own model and P7 reports the case where one does. What remains of this
   gap is small and named: **FR-078 omits state machines**, and **FR-081's first
   clause is not machine-decidable**, which the check says rather than pretending.
   **FR-115/FR-116 closed 2026-10-13** (ADR-0038): P7 conforms the assembled system
   against the model and checks the criteria no module can satisfy, so §10 has no
   unbuilt requirement.
2. ~~**No confinement boundary of any kind (FR-016–020, FR-059).**~~ **Blocker
   removed 2026-10-14 (ADR-0060); the gap is now narrow and named.** FR-141 was
   **built** 2026-10-12 (ADR-0033): two sessions at once cannot see or overwrite each
   other's files. What remained was that a worktree *contains* a session that stays put
   and does not *confine* one that wanders, that FR-059's "the harness cannot reach the
   oracle corpus" was prompt text and nothing else, and that FR-149's hermeticity was a
   property of the argv rather than of the process. The measurement that forced this is
   in ADR-0024: neither `pi` nor `claude` confines its child.
   **The blocker was a decision, not an absence of mechanism, and ADR-0060 reverses
   it.** ADR-0005 read FR-019 as a question about containers and answered "no", which
   left FR-019's own conditional — isolation "**where one exists**" — unread. The
   boundary is now a *measurement*: one real child writes inside its directory, tries to
   write one level above it, and tries to open a planted canary in each subtree it must
   not read. Both process-launch points route through one wrapper, so the control is
   applied at every launch. The ceiling follows the measurement, which is the other half
   of FR-019's sentence: a deployment measured to confine its children has the baseline
   *restored*, not T1's penalty charged.
   **What is still open, named so it does not read as finished.** FR-016's holdout set
   is not enumerated per lane — the detector denies the factory home, and a per-lane
   holdout subtree is not yet derived. FR-152's egress denial is a property of the
   shipped profile and a recorded one-time measurement, not a per-run probe, so
   "enforced and **proved** at the sandbox layer" is half satisfied. FR-020's blast bound
   is not read from the topology to change packaging. And on a host offering no
   mechanism the factory runs fully degraded — which is now *reported* rather than
   silently assumed, but is still the case this build cannot fix.
3. ~~**No oracle manufacturing and no measured oracle strength (FR-103–107, FR-008–
   011).**~~ **Closed 2026-10-14 (ADR-0061), except the θ comparison.** The blocker
   named below — *manufacturing needs a target language, which D5 leaves open* — was
   the right diagnosis and is now answered: D5 is resolved as Python-first behind a
   pluggable backend, `manufacture.py` is the seam, and the Python backend builds
   ranks 1, 3 and 5 while refusing 2, 4, 6 and 7 by name. The hint is **earned** rather
   than fabricated (the artefact must exist at the path the command names, must run,
   and must fail against a tree holding nothing but itself), and FR-118's measured
   strength is now a number on the report rather than a field nothing set. What is
   still not built is the **θ_lo comparison and the escalation** FR-105 names, which
   needs D3's calibration on a real repository — so `THETA_GATE_BUILT` stays `False`
   and the number is recorded rather than gating. `suggest_oracle` picks a class from
   clause polarity; manufacturing *adds executability* to what it left alone, and a
   refusal leaves the clause exactly as it was.
   **Narrowed 2026-10-13 (ADR-0050)**, and the narrowing is the half that needed no
   target language: *accounting* for coverage is now correct where it was not.
   FR-108 and FR-109 read one predicate — executable **and** rank ≤ 5 — so a rank-1
   property intention no longer grants L4 and a rank-6 example with a command no
   longer reports zero debt.
   **Narrowed again 2026-10-13 (ADR-0051).** FR-110 was listed here as "O8 does not
   exist as a class", and the class was the wrong object to want. Every `OracleClass`
   member is a per-clause shape — ranked, mapped to the P5 session that discharges
   *one* clause, with `propose` giving each clause exactly one owning module — while
   FR-110's own premise is that per-module verification cannot see across a boundary.
   O8 is therefore a P7 check, and it now runs: `check_boundary_contracts` asks
   whether a consumer that reached across a **declared** edge reached for a name the
   producer ever declared. FR-113 and FR-112 each held half of that question and
   neither asked it, so a system could pass both and not run. O8 needs no target
   language, which is why it came out of the blocked set.
   **Narrowed a third time 2026-10-13 (ADR-0052).** FR-106 was listed here as "Not
   built — no holdout mechanism", which was true and understated it: the factory had
   the defect FR-106 exists to prevent, and it had it twice. `_oracle_lines` rendered
   the operator's example oracle — description, command and expected output — into the
   producer's `verification_surface`, while the *same goal's* boundaries said "Do not
   read the oracle corpus, holdout scenarios, or factory credentials (FR-059)": the
   prompt printed the answer it forbade reading. And the repair door leaked it again,
   because `_command_output` builds the violated reason as `stdout did not contain
   {value!r}` and `refutation_diagnosis` joins that reason into the repair goal. Both
   are closed by one derived predicate, `OracleDeclaration.held_out`, applied at both
   renderers. This is the context-assembly half of R8 — "a permission boundary, not a
   prompt instruction" — and it needed no target language, which is why it too came out
   of the blocked set. **The manufacturing door is closed too (ADR-0061):** the
   `EXAMPLE` refusal is the seam's first statement, above the backend, so no
   third-party backend can re-open FR-106 by that route. FR-106's other half, holdouts
   *existing* for every lane above L2 and being versioned, is still open — the factory
   now manufactures oracles, and none of them is held out, because rank 6 is exactly
   the class the factory refuses to build.
4. ~~**No P8 delivery and no deploy gate (FR-117–121, FR-086, FR-118).**~~
   **Closed 2026-10-13 (ADR-0040), except FR-120's delivered-system half.** The report, the deploy gate and the
   Mode M handover are built: `DeliveryReport`'s five FR-118 statements are five required
   fields, FR-086's sentence is a `ClassVar` no code path can omit, the traceability
   chain draws its gaps rather than shortening, the deploy gate names the report it
   approved and is passed only by a person, and the handover hands §13's lanes the whole
   contract's oracles. Two things are deliberately not closed and are *reported* rather
   than hidden: **FR-117's image and IaC** are decisions ADR-0060 and FR-124 leave to
   the operator — the artefact check is scoped to the two the factory owes, because a
   check that can never pass is one an operator learns to bypass — and **FR-120's
   machine-usable API surface** was unbuilt; **the factory's own surface is now built**
   (2026-10-13, ADR-0048) — `sofact api <operation>` answers ten read-only operations
   through one closed envelope and refuses the four human gates by name — while the
   *delivered* system's surface stays a producer obligation no oracle observes, which the
   report now names in a `machine_surface_not_verified` check and `DELIVERY_REQUIREMENTS`
   keeps in the list rather than dropping. The two the factory does owe were *also* missing until
   2026-10-13 (ADR-0044): the check was scoped to `RUNBOOK.md` and `DELIVERY.md` and
   nothing produced them, so `sofact deliver` could not succeed on a fresh project.
   `sofact.writing` now renders both from the report, deterministically and model-free.
   FR-123 is closed (ADR-0041) and FR-122 is half closed by `delivery.ceiling`: the
   module number and the delivery number are both reported, and no per-*phase*
   computation exists.
5. ~~**No phase state machine and no resume (FR-060, FR-062, NFR-028).**~~ **Closed
   2026-10-13 (ADR-0030, ADR-0031, ADR-0035, ADR-0037).** Phases are a state machine in
   the ledger, a transition is its own row, `sofact phase` exits non-zero while a gate
   is open, and `test_the_phase_survives_a_restart_because_it_is_in_the_log` proves a
   second process reads the phase off disk. **FR-062's other half is closed too**: P2
   emits `Specification`/`SpecificationGate` (ADR-0031), P1 emits `SourceLedger`
   (ADR-0035) **and now the per-clause classification** (FR-068/ADR-0037), so a resume
   lands on a phase whose output is an artefact in every phase P0–P3. `sofact init`
   (§23 M1) remains unbuilt — it is a convenience over the phase machine rather than a
   prerequisite for it.

Honourable mentions, in the same ranking: FR-130/131 are implemented but FR-058's
*portability* claim rests on a second adapter that has never been measured. **FR-127
leaves this list** (2026-10-14, ADR-0058): the graph is the structure the delivery chain
is projected from, `record_escape` can name the module that broke so an attribution is an
answer rather than a candidate set, and `IntentGraph.gaps` reports a clause nothing was
built for.

---

## 3. Doc-versus-code discrepancies

1. **ADR-0011 Decision 1 vs the code — closed 2026-10-13 (ADR-0047).** The record said
   evolvability debt "must be reported" as a first-class term beside ground-truth debt,
   with a value of 1.0 by construction; no code computed, stored, or reported it, and
   there was no `evolvability_debt` anywhere, while the *index*
   (`docs/adr/README.md:67`, D18 row) restated it as "the debt is named and defaulted to
   total", which read as done. The debt is now a number on the report
   (`EVOLVABILITY_DEBT`, surfaced as `DeliveryReport.evolvability_debt`), the Mode M
   ceiling is a separate constant that no lane may exceed, and the delivery report
   states the refusal. FR-159's instrument is now built (2026-10-14, ADR-0062), so the
   *measurement* half of this row is closed; what remains is its **baseline**, reported
   unmeasured because a trend needs a history no single delivery has, and D18's ceiling
   question, which is a decision a human takes on that trend — that is the decision the
   row is *about*, and it is not what was missing.
2. **Spec §8.6 vs the code default.** §8.6 resolves D11 as "v1 drives `dsh` as the
   primary harness and `pi` as the second adapter", and ADR-0004's Decision says
   "the first adapter targets `dsh`". `service.py:108` sets
   `DEFAULT_HARNESS = "pi"` and ADR-0023 demotes `dsh` to an unverified-argv row.
   The later ADR supersedes the earlier one — but the *spec* still states the
   opposite of what ships, and §8.6 is the section the roadmap's M0 probe is
   sequenced against.
3. **Spec §4 FR-064 vs `ElicitationDimension` — closed 2026-10-17 (ADR-0077).** The
   spec's table lists seven dimensions (Goal, Success, Scope boundary, **Scale**,
   Constraints, **Non-negotiables**, Failure) and the enum had six. Both missing rows
   are now members. The gap is recorded here rather than deleted because what it
   actually was is not a count: *Non-negotiables* had been folded into `CONSTRAINT`'s
   own question ("What are the non-negotiables — platform, stack, dependencies,
   time?"), so it was never absent from the interrogation — it was asked as a question
   about the stack, while the spec's *Constraints* row was asked nowhere. And nothing
   compared the enum against the spec's table, which is why both survived; a test that
   reads the table is a separate unit.
4. **Spec §17 verb surface vs the CLI.** §17 says "the planned verbs remain the
   target surface" and lists `sofact init`, `specify`, `build`, `report`, `gate
   approve <phase>`. None exists. The same section's "Running in v0.1" list is
   accurate, so the discrepancy is that the planned verbs are still presented as
   the target with no record of their deferral.
5. **Spec §23 roadmap vs the repo — partly closed 2026-10-15.** M0's exit criterion is
   "§20.3 items 1–7 complete as real numbers", and M1 is `sofact init` (Mode M). The
   claim that "no milestone has an artifact, a tracker, or a test" was **false as of
   ADR-0060/0061** and is corrected here rather than left standing: items 2, 4, 5 and 6b
   each have an instrument with tests — `sofact.mutation` (`test_mutation.py`, 6),
   `sofact.escape` (`test_escape.py`, 10), `sofact.boundary` (`test_boundary.py`, 30) and
   the harness capability probe (`test_harness.py`, 55). Item 3 now has **both halves**:
   ADR-0043's per-gate instrument and ADR-0068's per-diff one (`test_review.py`, 25), so
   §1.4's claim is readable against the v0.1 alternative per project — though the
   **baseline is still unmeasured**, because a rate needs a project somebody actually
   reviewed and no project has been. Item 6a now has a **reading** too — ADR-0069's
   `measure_goal_mode` (`test_goal.py`, 19) folds what each dispatch recorded about forced
   entry and turn count, over two fields that until then were written by the adapter and read
   by nothing in `src/` — but the **probe itself is still open**: a fold can report that entry
   was never forced, and it cannot *force* it, which needs a live run against a harness whose
   argv enters goal mode by construction and no configured spec does that today. What the row
   still states is what remains **open**: items 1 and 7 have no instrument at all, item 6a's
   probe is unrun, item 5's container half is written and never witnessed, and M1's
   `sofact init` does not exist.
   Several M6 exit criteria (O8 conformance, integration failure attribution) are partly
   met, and M3's "all 8 oracle classes" is not. The row was right about the *shape* of
   the gap — an exit criterion measured by prose — and wrong about it being total, which
   is the more dangerous error because a false negative reads as a finding.
6. **README P7 row vs the tree.** The README at HEAD said two checks and named
   FR-112 as unimplemented. That is now stale in the other direction: the working
   tree has three checks and FR-112 discharges when a surface is declared. The
   README *was* updated in the same change, so this is a snapshot artifact, not a
   live defect — but it is the exact class of claim the audit is looking for, and
   it shows the row is edited by hand while the behaviour is derived.

### Method note

Every "Implemented" verdict above names a test. One verdict was **downgraded on
inspection** for want of one: FR-091 (the count is reported; nothing minimises it) — and
it was **restored on 2026-10-14** when the grouping, its rule and its tests landed
(ADR-0059), which is the downgrade working as intended rather than a reversal.
FR-102 was downgraded on the same ground — per-dispatch telemetry existed, but the
requirement is about *attempts*, which nothing aggregated — and was **restored on
2026-10-14** when the aggregation, its tests and the defect they caught landed
(ADR-0055). No requirement was marked Implemented on the strength of a docstring, a
goal-text line, or a README row.
