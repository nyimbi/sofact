# Roadmap gap audit — the specification against the implementation

**Date: 2026-10-12.** This is a **snapshot**. The tree changed while it was being
written: FR-112's check landed mid-audit (ADR-0027, commit-in-progress), and the
counts below reflect the tree after that change. Re-run the greps before acting.

Scope: every `FR-xxx` the spec states, classified against `src/sofact/*.py` and
`tests/ci/*.py`. Verdict classes:

- **Implemented** — a named function and a named test that fails if it is removed.
- **Partly** — the named half that is missing.
- **Deferred** — named in an ADR as not-built.
- **Not built** — no code, no test, no record.

`tests/ci` at this snapshot: **725 passed, 0 failed**.

---

## 1. The FR table

| FR | Verdict | Evidence |
| --- | --- | --- |
| FR-001–005 declared oracles, read-only corpus, canaries, audit trail, invalidation | **Partly** | `Clause.oracle` required (`views.py:351`), `require_executable` (`contract.py:110`). Canaries, oracle-corpus read-only enforcement and cache invalidation have **no code** — the string `canary` appears in no `src/` or `tests/` file. FR-006's second half is FR-166 (below). |
| FR-006 no stale result decides a later state | **Implemented** | `verdict_cache_key` (`verification.py:71`); `test_a_different_change_keys_differently` (`test_verification.py:477`), `test_a_completed_dispatch_is_checked_without_a_declaration` (`test_service.py:1127`). |
| FR-007 O1 alone caps at L2 | **Implemented** | `ceiling_for_rank` (`views.py:209`); `test_rank_maps_to_ceiling` (`test_views.py:97`). |
| FR-008–011 mutation score per module, thresholds, trend | **Not built** | No mutation-scoring code. Oracle *rank* is a declaration, not a measurement. |
| FR-012–015 adversarial audit, sampling, exploit metric | **Not built** | No code. |
| FR-016–020 isolation | **Partly** | No enforced boundary: producer isolation is **asserted in goal text only** (`planner.py:127`, FR-059), and ADR-0005 refuses the container layer FR-019 names. What *is* measured now is the narrower claim a spec makes about its own environment: the `store_isolated` probe row (`harness.py`, `_probe_store_isolated`) runs the same goal twice with `HOME` relocated and the spec's containment variables applied in one arm and withheld in the other, so "an isolation variable is not a boundary" is decided rather than assumed. Measured 2026-10-12 for `claude`: zero files under the isolated arm's `HOME`, three under the control's. |
| FR-021–023 escape oracle, automatic downgrade | **Not built** | No code. |
| FR-024–035 routing function, blast bounds, ladder, per-deployment ceilings | **Not built** | No code. |
| FR-036 per-language mutation/property tooling | **Not built** | Cited once in a spec open-decision; no code. |
| FR-038 verifier/executor import direction | **Implemented** | `test_verifier_cannot_reach_the_executor` (`test_verification.py:72`) scans this file's imports. |
| FR-049 model-agnostic | **Implemented** | `SOFACT_MODEL` / `--model` resolved by the harness registry; `test_the_probe_reports_the_model_it_measured` (`test_cli.py:406`). |
| FR-052–056 fine-tuning, monetization | **Not built** | Prose only (§18.3, §18.5). |
| FR-057 envelope refusal | **Not built** | No envelope type; `ENVELOPE` appears nowhere in `src/`. |
| FR-058 single adapter interface | **Implemented** | `ConfiguredHarnessAdapter` (`harness.py:819`), three specs; `test_every_shipped_harness_has_a_spec` (`test_harness.py:102`). |
| FR-059 harness cannot reach oracle corpus/credentials | **Partly** | Prompt text only (`planner.py:127`). No sandbox, no check. |
| FR-060 phase state machine, resumable after SIGKILL | **Implemented** (2026-10-12, ADR-0030) | `Phase`/`PHASE_SEQUENCE`/`PhaseAdvance` (`views.py`), `advance_phase`/`approve_gate`/`current_phase`/`open_gate` (`service.py`), `sofact phase` and `sofact gate`; `test_the_phase_survives_a_restart_because_it_is_in_the_log` (`test_phase.py`). A transition is its own ledger row, so a new process reads the phase off disk. |
| FR-061 gate is a hard stop | **Implemented** | `require_approved_decomposition` (`service.py`) for P3, and now structural for all four gates: `PhaseAdvance` refuses a completed gate phase with no approver, `advance_phase` cannot complete a gate, and it refuses when any earlier phase is incomplete — so P5 is unreachable without P2 and P3. Canaried by deleting the forward check. |
| FR-062 every phase emits a durable artifact | **Partly** | Decomposition/contract/plan/verdict are ledger rows, a phase transition is one (`LedgerKind.PHASE_ADVANCED`), **P2 now is too** (`SPECIFICATION_PROPOSED`/`SPECIFICATION_GATED`), and **P1's ledger now is** (`SOURCE_LEDGER_RECORDED`, FR-070/ADR-0035). What is still missing is the per-clause classification artefact FR-068 asks for. |
| FR-063 goal not accepted until reduced to falsifiable | **Implemented** | `Readiness.is_ready` (`views.py:290`); `test_progress_counts_resolved_dimensions_and_readiness_flips_at_the_end` (`test_elicitation.py:217`). |
| FR-064 adversarial elicitation, 7 dimensions | **Partly** | `ElicitationDimension` (`views.py:231`) has **6** members; the spec's *Scale* and *Non-negotiables* are absent. `test_readiness_covers_every_dimension_in_declaration_order` (`test_elicitation.py:212`). |
| FR-065 elicitation terminates, unresolved reported as risk | **Implemented** | `next_open` (`elicitation.py:226`), `Readiness.open_dimensions`; `test_next_open_returns_the_first_unresolved_dimension` (`test_elicitation.py:229`). |
| FR-066 elicitation proposes no implementation | **Implemented** | `_SHARED_CONSTRAINTS` (`planner.py:110`) + `draft_stems` polarity (`elicitation.py:254`); `test_polarity_follows_the_dimension` (`test_elicitation.py:281`). |
| FR-067 each clause carries `confidence` and `verification_method` | **Partly** | `Clause` (`views.py:351`) carries **neither**; ambiguity is not quantified per clause. `test_confidence_is_not_an_oracle` (`test_elicitation.py:160`) asserts the *opposite* rule. |
| FR-068 clause classified by research into validated/invalidated/… | **Not built** | No classification type. |
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
| FR-083 machine-readable system model as the single interface source | **Partly** | The model is machine-readable and carries entities/relationships/invariants. It is **not yet the single source for interface definitions**: ADR-0027 still declares surfaces on `Module`, and nothing derives a module's surface from the model. |
| FR-084 model updated as part of any change | **Not built** | No model. |
| FR-085 falsifiable value hypothesis | **Implemented** | `ValueHypothesis` (`views.py`) names effect, beneficiary and refuting instrument; `value_hypothesis_is_falsifiable` is a gate check. |
| FR-086 factory must not certify value | **Partly** (2026-10-12) | The type carries no verdict field and nothing in `specification.py` can mark a hypothesis satisfied — the factory's only permitted statement about one is that it was *declared*, and `sofact specify` prints it under "declared, never certified". **The delivery-report half is unbuilt**: FR-118 has nowhere to make the statement. |
| FR-087 decomposition machine-proposed, human-validated | **Implemented** | `propose` (`decomposition.py:282`), `approve` (`:493`); `test_the_proposal_is_deterministic` (`test_decomposition.py:93`), `test_approval_names_who_and_when` (`:340`). |
| FR-088 traceability both directions | **Implemented** | `gate` checks `every_module_traces_to_a_requirement` and `every_requirement_traces_to_a_module` (`decomposition.py:423,438`); `test_an_unowned_clause_fails_the_gate` (`test_decomposition.py:260`). |
| FR-089 DAG, no cycles | **Implemented** | `test_the_proposal_never_contains_a_cycle` (`test_decomposition.py:109`), `test_a_cycle_fails_the_gate` (`:239`). |
| FR-090 declared interface and dependencies | **Implemented** | `Module.interface` / `depends_on` (`views.py:491`); `test_a_dependency_follows_the_oracle_the_contract_already_carries` (`test_decomposition.py:121`). |
| FR-091 minimise interface surface, report the count | **Partly** | `interface_count` (`views.py:641`) is **reported**, not minimised — `decomposition.py:473` says so explicitly. No threshold, no alternative proposal. |
| FR-092 declared build order | **Implemented** | `build_order_exists` check (`decomposition.py:413`); `test_a_sound_proposal_passes_every_machine_check` (`test_decomposition.py:291`). |
| FR-093 per-module completion criteria | **Not built** | `completion_criteria` appears nowhere in `src/` or `tests/`. |
| FR-094 revisable without invalidating the whole | **Implemented** | Revisions + `decomposition_hash`; `test_approving_a_superseded_revision_is_refused` (`test_decomposition.py:467`). The **rollback verb** the capability map recorded as missing now exists (2026-10-12): `FactoryService.cut` / `sofact rollback --to N` records a `cut.recorded` row and the fold reads through the target (ADR-0034); `TestRollback` (`test_service.py`), `test_a_cut_hides_the_entries_after_its_target` (`test_state.py`). |
| FR-095 P5 given the contract and only the contract | **Partly** | Goals are compiled from the contract (`compile_plan`, `planner.py:576`) and pinned by hash; the *envelope* the producer may see is not otherwise constrained or checked. |
| FR-096 contracts frozen before P5, immutable during | **Implemented** | `compile_plan` pins `contract_hash`; `check_integrity` (`planner.py:712`); `test_an_undisturbed_plan_reports_intact` (`test_service.py:1192`). |
| FR-097 explicit budget (files, LOC, reasoning class) | **Partly** | `StepBudget` (`views.py:1060`) has wall clock, continuations, attempts, tokens. **No** `max_files`, `max_loc`, or reasoning class. |
| FR-098 three modes incl. bootstrap empty repo | **Partly** | Bootstrap is a plan tier (`planner.py:231`), not an adapter mode; diagnostic mode exists via `repair_plan` (`service.py:1081`). Probe row `bootstrap_empty_repo` (`views.py:1416`) is measured, not exercised. |
| FR-099 idempotent per task | **Partly** | Stated in the goal text (`planner.py:114`); `test_re_running_the_same_step_is_idempotent` (`test_git.py:158`) covers the git half only. |
| FR-100 branch per module, never in place | **Implemented** | `ensure_module_branch` (`git.py:139`), `seal_branch` (`:258`); `test_the_branch_is_not_in_place` (`test_git.py:91`), `test_two_steps_of_one_module_share_its_branch` (`:115`). |
| FR-101 escalate with diagnosis, not retry forever | **Implemented** | `repair_plan` bounded per clause; `test_the_loop_is_bounded_and_says_so_when_it_gives_up` (`test_service.py:961`). |
| FR-102 attempt telemetry | **Partly** | Per-dispatch `tokens_observed`/`wall_clock_seconds`/`continuations_observed` (`views.py:1672`); `test_a_step_runs_and_is_recorded` (`test_service.py:525`). **No attempt-level aggregation.** |
| FR-103 oracle manufacturing from contract structure | **Partly** | `suggest_oracle` (`contract.py:46`) proposes a class and a command from clause polarity; `test_negative_clauses_suggest_a_property_and_positive_ones_a_contract` (`test_contract.py:64`). No test *generation*, no rank ordering, no mutation. |
| FR-104 ranks 1–2 mandatory above L2 | **Partly** | `STRONG_ORACLE_MAX_RANK` (`views.py:204`) + `ceiling_for_rank` cap the ceiling; nothing *manufactures* a rank-1/2 oracle. |
| FR-105 measured strength before P5 | **Partly** | `Contract.weakest_oracle_rank` (`views.py:407`) is a declaration. `test_ceiling_follows_the_weakest_clause` (`test_views.py:166`). Nothing measures. |
| FR-106 operator examples held out | **Not built** | No holdout mechanism. |
| FR-107 adversarial audit of oracles | **Not built** | No code. |
| FR-108 per-module ground-truth debt | **Implemented** | `ground_truth_debt` (`contract.py:73`); `test_debt_is_the_fraction_of_uncheckable_clauses` (`test_contract.py:109`). |
| FR-109 uncovered clauses cap at L2 | **Partly** | `ceiling_for_rank` caps on rank, not on clause coverage; `refuted_steps` (`service.py:176`) tracks refutations. `test_an_oracle_too_weak_to_trust_narrows_the_ceiling` (`test_cli.py:209`) tests the rank path. |
| FR-110 O8 Integration oracle class | **Not built** | `OracleClass` (`views.py:183`) has **7** members; there is no O8. |
| FR-111 P7 build order | **Implemented** | `check_build_order` (`integration.py:286`); `test_a_module_built_before_its_dependency_is_a_finding` (`test_integration.py:331`). |
| FR-112 empty public-API diff | **Implemented** (2026-10-12, ADR-0027) | `check_interface_conformance` (`integration.py:390`), `public_surface` (`:336`), `Module.surface` (`views.py:510`); `test_a_declared_name_the_build_does_not_expose_is_a_finding` (`test_integration.py:422`), `test_a_declared_surface_discharges_fr_112_and_the_report_stops_naming_it` (`:513`). Discharged **only when a module declares a surface** — a proposal derives none, so the default report still names FR-112. |
| FR-113 no module reaches another's internals | **Implemented** | `check_imports` (`integration.py:183`); `test_a_module_reaching_another_without_declaring_it_is_a_finding` (`test_integration.py:157`). |
| FR-114 minimum violating set | **Implemented** | `attribute_files` (`integration.py:87`), `IntegrationReport.violating_modules` (`views.py:1348`); `test_the_repair_scope_is_the_findings_union_and_never_the_plan` (`test_integration.py:571`). |
| FR-115 system model conformance | **Not built** | Named on every report (`not_implemented`, `views.py:1331`); `test_the_report_names_every_requirement_it_did_not_discharge` (`test_integration.py:491`). |
| FR-116 system-level acceptance criteria | **Not built** | Same mechanism; blocked on P2 (FR-076). |
| FR-117–121 P8 delivery, deploy gate, handover | **Not built** | No delivery artifact, report, deploy gate, API-surface publication, or Mode M handover. FR-120's machine-usable surface exists only as the CLI itself. |
| FR-122 autonomy per phase and per module, lower governs | **Not built** | Ceilings are per module *class* only. No per-phase computation. |
| FR-123 Mode G delivery caps at L2 and must be reported | **Not built** | Nothing computes or reports a delivery-level autonomy number. |
| FR-124 per-deployment topology ceilings | **Not built** | No deployment topology type. |
| FR-125 G1–G2 target classes, class distribution reported | **Implemented** | `class_distribution` (`views.py:650`) reported in the gate (`decomposition.py:484`); `test_a_sound_proposal_passes_every_machine_check` (`test_decomposition.py:291`). |
| FR-126 G7 human-authored | **Implemented** | `MODULE_CLASS_CEILING` (`views.py:478`); `test_g7_is_the_only_l1_class` (`test_decomposition.py:217`), `test_every_g7_marker_classifies_as_g7` (`:204`). |
| FR-127 intent traceability graph first-class | **Partly** | Traceability is a gate *check* over the clause→module relation (`decomposition.py:438`), not a graph with escape attribution. |
| FR-128 model as single source of interface truth | **Not built** | No model (FR-083). ADR-0027 declares surfaces on the module instead. |
| FR-129 no shared model context across phases | **Partly** | `sofact.llm` is advisory and used only for elicitation advice; no other phase calls a model. Nothing *enforces* the separation. |
| FR-130 attributable approval | **Implemented** | `approve(..., by=…)` (`decomposition.py:493`); `test_approval_names_who_and_when` (`test_decomposition.py:340`), `test_half_an_approval_is_refused_by_the_type` (`:351`). |
| FR-131 UUID7 + version hash per artifact | **Implemented** | `uuid7str` shim, `content_hash` (`views.py:117`); `test_uuid7_is_version_7` (`test_views.py:38`), `test_content_hash_is_stable_across_a_model_round_trip` (`:76`). |
| FR-132 tiered declarative model config | **Partly** | One model per harness/dispatch (`--model`); no tier table, no per-phase default. |
| FR-133 spend attributed per phase and per module | **Partly** | Attributed per **dispatch step and harness** (`DispatchRecord`, `views.py:1672`); not per phase, not per module, and not against an envelope. |
| FR-134 fine-tuned models must not be oracles/contract authors | **Not built** | No fine-tuning; nothing to constrain. |
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
| FR-147 harness selection empirical | **Partly** | `declaration_precision` is scoped to one harness (`test_precision_is_scoped_to_one_harness`, `test_service.py:1252`). **No selection**: nothing chooses a harness from the measurement. |
| FR-148 capability matrix discovered at runtime | **Implemented** | `probe` (`harness.py:1072`); `test_an_unprobed_capability_reads_inconclusive_not_absent` (`test_harness.py:448`). |
| FR-149 hermetic invocation | **Partly** | Flags are explicit in `HarnessSpec.argv` (`harness.py:443`); `test_pi_argv_matches_the_S19_measurement` (`test_harness.py:138`). No *enforced* boundary — `dsh`'s telemetry egress is documented as unmitigated (`harness.py:590`). |
| FR-150 context-file loading disabled in P5 | **Implemented** | `supports_context_file_flag` + goal text (`harness.py:1204`); `test_dsh_cannot_disable_context_files_but_pi_can` (`test_harness.py:166`). |
| FR-151 telemetry read from the session record | **Implemented** | `parse_usage` (`harness.py:765`), `parse_completion` (`:748`); `test_usage_is_summed_across_records` (`test_harness.py:357`). |
| FR-152 `--offline` is not the egress boundary | **Implemented (as a documented refusal)** | `harness.py:683,691` state it; `test_claude_notes_record_the_unconfined_child_and_the_egress` (`test_harness.py:206`). No boundary is built — the requirement is that none be claimed. |
| FR-153 goal entry forced, not requested | **Implemented** | `parse_goal_entry` (`harness.py:789`); `test_a_goal_typed_event_means_the_session_carried_the_goal` (`test_harness.py:419`). |
| FR-154 plugin composition frozen, pinned | **Partly** | `--no-extensions` on the build spec (`harness.py:491,552`); `test_claude_notes_record_the_unconfined_child_and_the_egress`. No hash-verified pin or licence audit. |
| FR-155 third-party plugin deletion test | **Not built** | The test is applied in prose (§8.7 table); no code, no gate. |
| FR-156 capability by configuration not code | **Implemented** | `load_specs` (`harness.py:406`), `--tools`/`SOFACT_TOOLS`; `test_the_readme_example_loads_through_the_real_loader` (`test_cli.py:717`). |
| FR-157 deployment-scoped autonomy target | **Not built** | No deployment scope type; the θ gate (FR-024–035) is absent so nothing can be scoped. |
| FR-158 evolvability debt reported as first-class, Mode M L1 | **Not built** | No code. ADR-0011 Decision 1 says it "must be reported" — see §3. |
| FR-159 differential change-cost oracle | **Not built** | ADR-0011 records it as "specified and **unbuilt**". |
| FR-160 gate-cost measurement | **Not built** | No code. |
| FR-161 adapter table is data, not code | **Implemented** | `HarnessSpec.from_mapping` refuses unknown/missing fields by name (`harness.py:236`); `test_a_malformed_field_is_refused_by_name` (`test_harness.py:640`), `test_an_unknown_field_is_refused` (`:662`). |
| FR-162 verdict describes one attempt | **Implemented** | `verify` run-scoped (`verification.py:232`); `test_a_verdict_can_be_scoped_to_one_run` (`test_verification.py:114`), `test_scoping_to_a_run_that_observed_nothing_is_insufficient` (`:135`). |
| FR-163 completed session triggers the check | **Implemented** | `check_dispatch` returns `None` unless `outcome == COMPLETED` (`service.py:523`); `test_a_completed_dispatch_is_checked_without_a_declaration` (`test_service.py:1127`), `test_a_failed_session_is_not_checked` (`:1148`). |
| FR-164 probe reports model resolution | **Implemented** | `HarnessCapability.MODEL_RESOLVED` (`views.py:1416`); `test_the_probe_records_the_refusal` (`test_service.py:457`). |
| FR-165 undecidable row measured by differential | **Implemented** | `test_an_unprobed_capability_reads_inconclusive_not_absent` (`test_harness.py:448`), `test_a_quick_probe_skips_the_rows_that_need_a_second_child` (`test_service.py:423`). |
| FR-166 key then reuse | **Implemented** | `verdict_cache_key` (`verification.py:71`), `VERDICT_REUSED` (`views.py:1848`); `test_an_unchanged_workspace_reuses_the_verdict` (`test_service.py:1336`), `test_a_changed_artefact_is_measured_again` (`:1373`). |
| FR-167 research is dispatched, not performed | **Implemented** | `research` (`service.py:1326`); `test_a_completed_loop_records_the_report_and_its_sources` (`test_service.py:1453`), `test_a_truncated_loop_is_a_fact_not_a_failure_to_report` (`:1481`). |

### Counts

Recounted from the table above on 2026-10-13 after the FR-072 unit, by reading the
verdict column rather than by arithmetic on the previous snapshot — the earlier numbers
in this file (47/21/1/48, then 59/28/1/31) did not match the rows they claimed to count.

| Verdict | n |
| --- | --- |
| Implemented | 67 |
| Partly | 26 |
| Deferred (ADR-0024) | 0 |
| Not built | 26 |
| **Total rows** | **119** |

Rows, not FR numbers: several rows cover a stated range (FR-008–011, FR-016–020), so
this counts the classification units rather than the FR identifiers inside them.

NFRs are not tabulated: NFR-001–024 are retained verbatim from v0.1 and are not
restated, so there is nothing to check them against. Of the new ones, NFR-025
(envelope) and NFR-030 (per-module attribution) are **not built**; NFR-027
(version-controlled artifacts) is **partly** (ledger + reports); NFR-028 (resume)
is **not built**; NFR-029 (per-phase wall-clock bound) is **partly** (per-step
only).

---

## 2. Gaps, ranked by what they block

1. ~~**No system model and no P2 specification (FR-076, FR-078, FR-083, FR-115,
   FR-116).**~~ **Mostly closed 2026-10-12.** P2 now produces a `Specification` —
   requirements traceable to clauses, a machine-readable model of entities,
   relationships and invariants, non-goals, assumptions and a value hypothesis — and
   gates on it. What remains of this gap, named so it does not read as finished:
   **FR-083 is half done** (the model is machine-readable but is not yet the single
   source for interface definitions, which ADR-0027 still routes around by declaring
   surfaces on `Module`), **FR-078 omits state machines**, **FR-081's first clause is
   not machine-decidable** and the check says so rather than pretending, and
   **FR-115/FR-116 remain unbuilt** — the P7 conformance check and system-level
   acceptance criteria now have a model to conform against and still do not conform
   anything. That last part is the next unit, not a blocker.
2. **No confinement boundary of any kind (FR-016–020, FR-059).** FR-141 is **built**
   as of 2026-10-12 (ADR-0033) and no longer belongs in this gap: two sessions at once
   cannot see or overwrite each other's files. What remains is that a worktree
   *contains* a session that stays put and does not *confine* one that wanders;
   FR-059's "the harness cannot reach the oracle corpus" is prompt text and nothing
   else; FR-149's hermeticity is a property of the argv, not of the process. The
   measurement that forced this is in ADR-0024: neither `pi` nor `claude` confines
   its child. **Blocker: confinement needs a filesystem/network boundary
   (ADR-0005 refuses containers), so there is no layer left to put it in.**
   **Narrowed 2026-10-12**, and the narrowing is worth stating precisely because it
   does not close the gap: the `store_isolated` row now measures whether the spec's
   environment contains the child's *private store*, which is the claim OpenRig's own
   warning is about. It does not measure where the child may **write** — that is
   `sandboxable`, still absent for both harnesses — and it does not bound egress
   (FR-152). A store that is contained and a child that is not are both true at once.
3. **No oracle manufacturing and no measured oracle strength (FR-103–107, FR-008–
   011, FR-110).** `suggest_oracle` picks a class from clause polarity; nothing
   generates a test, nothing measures whether an oracle measures anything, and the
   rank that sets every ceiling is a declaration the operator made. O8 does not
   exist as a class. This is the requirement the product's own thesis rests on
   (§1.1 capability 3). **Blocker: manufacturing needs a target language, which
   D5 leaves open and ADR-0025 records as out of scope.**
4. **No P8 delivery and no deploy gate (FR-117–121, FR-086, FR-118).** There is no
   delivery artifact, no report, no handover, and nowhere for FR-086's
   "verified requirements, not value" statement to be made. Every delivery-facing
   requirement is unbuilt. **Blocker: depends on 1 (traceability chain) and on a
   packaging decision (T2) that no ADR makes.**
5. ~~**No phase state machine and no resume (FR-060, FR-062, NFR-028).**~~ **Closed
   2026-10-12 (ADR-0030).** Phases are a state machine in the ledger, a transition is
   its own row, `sofact phase` exits non-zero while a gate is open, and
   `test_the_phase_survives_a_restart_because_it_is_in_the_log` proves a second
   process reads the phase off disk. **What remains of this gap is FR-062's other
   half**, narrowed twice since: P2 now emits `Specification`/`SpecificationGate`
   (ADR-0031) and P1 now emits `SourceLedger` (ADR-0035), so a resume lands on a
   phase whose output is an artefact. What is still missing is FR-068's per-clause
   classification — a verdict on each intent clause, which the ledger holds claims
   *about* but does not attribute to clauses. `sofact init` (§23 M1) also remains
   unbuilt — it is a convenience over the phase machine rather than a prerequisite
   for it.

Honourable mentions, in the same ranking: FR-122/123/124 (no autonomy number is
ever computed at delivery level, so the spec's most emphatic honesty requirement is
unenforced), FR-127 (traceability is a gate check, not the first-class graph escape
attribution needs), FR-130/131 are implemented but FR-058's *portability* claim
rests on a second adapter that has never been measured.

---

## 3. Doc-versus-code discrepancies

1. **ADR-0011 Decision 1 vs the code.** The record says evolvability debt "must be
   reported" as a first-class term beside ground-truth debt, with a value of 1.0 by
   construction. No code computes, stores, or reports it, and there is no
   `evolvability_debt` field anywhere. The record is honest two sections later
   ("specified and **unbuilt**"), so the *record* is consistent with itself; the
   *index* (`docs/adr/README.md:55`, D18 row) restates it as "the debt is named and
   defaulted to total", which reads as done.
2. **Spec §8.6 vs the code default.** §8.6 resolves D11 as "v1 drives `dsh` as the
   primary harness and `pi` as the second adapter", and ADR-0004's Decision says
   "the first adapter targets `dsh`". `service.py:108` sets
   `DEFAULT_HARNESS = "pi"` and ADR-0023 demotes `dsh` to an unverified-argv row.
   The later ADR supersedes the earlier one — but the *spec* still states the
   opposite of what ships, and §8.6 is the section the roadmap's M0 probe is
   sequenced against.
3. **Spec §4 FR-064 vs `ElicitationDimension`.** The spec's table lists seven
   dimensions (Goal, Success, Scope boundary, **Scale**, Constraints,
   **Non-negotiables**, Failure); the enum has six. Scale and Non-negotiables were
   dropped without a record.
4. **Spec §17 verb surface vs the CLI.** §17 says "the planned verbs remain the
   target surface" and lists `sofact init`, `specify`, `build`, `report`, `gate
   approve <phase>`. None exists. The same section's "Running in v0.1" list is
   accurate, so the discrepancy is that the planned verbs are still presented as
   the target with no record of their deferral.
5. **Spec §23 roadmap vs the repo.** M0's exit criterion is "§20.3 items 1–7
   complete as real numbers", and M1 is `sofact init` (Mode M). No milestone has an
   artifact, a tracker, or a test; the roadmap is prose with no implementation
   surface. Several M6 exit criteria (O8 conformance, integration failure
   attribution) are now partly met, and M3's "all 8 oracle classes" is not.
6. **README P7 row vs the tree.** The README at HEAD said two checks and named
   FR-112 as unimplemented. That is now stale in the other direction: the working
   tree has three checks and FR-112 discharges when a surface is declared. The
   README *was* updated in the same change, so this is a snapshot artifact, not a
   live defect — but it is the exact class of claim the audit is looking for, and
   it shows the row is edited by hand while the behaviour is derived.

### Method note

Every "Implemented" verdict above names a test. Two verdicts were **downgraded on
inspection** for want of one: FR-091 (the count is reported; nothing minimises it)
and FR-102 (per-dispatch telemetry exists; the requirement is about attempts, which
are not aggregated anywhere). No requirement was marked Implemented on the strength
of a docstring, a goal-text line, or a README row.
