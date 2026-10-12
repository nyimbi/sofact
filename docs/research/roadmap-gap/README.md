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

`tests/ci` at this snapshot: **630 passed, 0 failed**.

---

## 1. The FR table

| FR | Verdict | Evidence |
| --- | --- | --- |
| FR-001–005 declared oracles, read-only corpus, canaries, audit trail, invalidation | **Partly** | `Clause.oracle` required (`views.py:351`), `require_executable` (`contract.py:110`). Canaries, oracle-corpus read-only enforcement and cache invalidation have **no code** — the string `canary` appears in no `src/` or `tests/` file. FR-006's second half is FR-166 (below). |
| FR-006 no stale result decides a later state | **Implemented** | `verdict_cache_key` (`verification.py:71`); `test_a_different_change_keys_differently` (`test_verification.py:477`), `test_a_completed_dispatch_is_checked_without_a_declaration` (`test_service.py:1127`). |
| FR-007 O1 alone caps at L2 | **Implemented** | `ceiling_for_rank` (`views.py:209`); `test_rank_maps_to_ceiling` (`test_views.py:97`). |
| FR-008–011 mutation score per module, thresholds, trend | **Not built** | No mutation-scoring code. Oracle *rank* is a declaration, not a measurement. |
| FR-012–015 adversarial audit, sampling, exploit metric | **Not built** | No code. |
| FR-016–020 isolation | **Not built** | Producer isolation is **asserted in goal text only** (`planner.py:127`, FR-059). No enforced boundary. |
| FR-021–023 escape oracle, automatic downgrade | **Not built** | No code. |
| FR-024–035 routing function, blast bounds, ladder, per-deployment ceilings | **Not built** | No code. |
| FR-036 per-language mutation/property tooling | **Not built** | Cited once in a spec open-decision; no code. |
| FR-038 verifier/executor import direction | **Implemented** | `test_verifier_cannot_reach_the_executor` (`test_verification.py:72`) scans this file's imports. |
| FR-049 model-agnostic | **Implemented** | `SOFACT_MODEL` / `--model` resolved by the harness registry; `test_the_probe_reports_the_model_it_measured` (`test_cli.py:406`). |
| FR-052–056 fine-tuning, monetization | **Not built** | Prose only (§18.3, §18.5). |
| FR-057 envelope refusal | **Not built** | No envelope type; `ENVELOPE` appears nowhere in `src/`. |
| FR-058 single adapter interface | **Implemented** | `ConfiguredHarnessAdapter` (`harness.py:819`), three specs; `test_every_shipped_harness_has_a_spec` (`test_harness.py:102`). |
| FR-059 harness cannot reach oracle corpus/credentials | **Partly** | Prompt text only (`planner.py:127`). No sandbox, no check. |
| FR-060 phase state machine, resumable after SIGKILL | **Not built** | Phases are not a state machine; no `init`/resume verb. |
| FR-061 gate is a hard stop | **Implemented** | `require_approved_decomposition` (`service.py:719`); `test_planning_without_a_decomposition_is_refused` (`test_decomposition.py:411`). |
| FR-062 every phase emits a durable artifact | **Partly** | Decomposition/contract/plan/verdict are ledger rows (`LedgerKind`, `views.py:1848`). There is **no P2 specification artifact** (FR-076) and no findings artifact beyond a research report path. |
| FR-063 goal not accepted until reduced to falsifiable | **Implemented** | `Readiness.is_ready` (`views.py:290`); `test_progress_counts_resolved_dimensions_and_readiness_flips_at_the_end` (`test_elicitation.py:217`). |
| FR-064 adversarial elicitation, 7 dimensions | **Partly** | `ElicitationDimension` (`views.py:231`) has **6** members; the spec's *Scale* and *Non-negotiables* are absent. `test_readiness_covers_every_dimension_in_declaration_order` (`test_elicitation.py:212`). |
| FR-065 elicitation terminates, unresolved reported as risk | **Implemented** | `next_open` (`elicitation.py:226`), `Readiness.open_dimensions`; `test_next_open_returns_the_first_unresolved_dimension` (`test_elicitation.py:229`). |
| FR-066 elicitation proposes no implementation | **Implemented** | `_SHARED_CONSTRAINTS` (`planner.py:110`) + `draft_stems` polarity (`elicitation.py:254`); `test_polarity_follows_the_dimension` (`test_elicitation.py:281`). |
| FR-067 each clause carries `confidence` and `verification_method` | **Partly** | `Clause` (`views.py:351`) carries **neither**; ambiguity is not quantified per clause. `test_confidence_is_not_an_oracle` (`test_elicitation.py:160`) asserts the *opposite* rule. |
| FR-068 clause classified by research into validated/invalidated/… | **Not built** | No classification type. |
| FR-069 finding provenance | **Partly** | `ResearchRecord.source_urls` (`views.py:1561`) records URLs only. No retrieval date, no verification status, no confidence, no opinion labelling. |
| FR-070 versioned source ledger, claims separately addressable | **Not built** | One report path plus a URL tuple; sources are not addressable and claims do not point at them. |
| FR-071 disconfirming count reported | **Not built** | No disconfirming search or count. |
| FR-072 research bounded by declared budget | **Partly** | `--timeout` and the extension's own loop ceiling bound wall clock; there is no source/model-call budget per clause. |
| FR-073 contradiction detection | **Not built** | No code. |
| FR-074 evidence vs positioning classification | **Not built** | No code. |
| FR-075 self-staleness / expiry | **Not built** | No code. |
| FR-076 specification as traceable requirements | **Not built** | There is no P2 specification artifact; `ClauseStem`→`Clause` is contract-level, not spec-level. |
| FR-077 machine-checkable acceptance criterion per requirement | **Partly** | A `Clause` cannot exist without an oracle (`views.py:351`), which is the same idea one phase later. No spec-level gate. |
| FR-078 system model in the specification | **Not built** | Researched (`docs/research/system-model/`), not built. |
| FR-079 non-goals and assumptions declared | **Not built** | No code. |
| FR-080 P2 gate presents the spec in the operator's language | **Not built** | No P2 gate. |
| FR-081 internal consistency check | **Not built** | No code. |
| FR-082 testability check, `human-verified` marking | **Not built** | No code. |
| FR-083 machine-readable system model as the single interface source | **Not built** | The research note says exactly this is the blocker for FR-112/115; ADR-0027 routes around it for FR-112. |
| FR-084 model updated as part of any change | **Not built** | No model. |
| FR-085 falsifiable value hypothesis | **Not built** | No code. |
| FR-086 factory must not certify value | **Not built** | Nothing to certify against; no delivery report (FR-118). |
| FR-087 decomposition machine-proposed, human-validated | **Implemented** | `propose` (`decomposition.py:282`), `approve` (`:493`); `test_the_proposal_is_deterministic` (`test_decomposition.py:93`), `test_approval_names_who_and_when` (`:340`). |
| FR-088 traceability both directions | **Implemented** | `gate` checks `every_module_traces_to_a_requirement` and `every_requirement_traces_to_a_module` (`decomposition.py:423,438`); `test_an_unowned_clause_fails_the_gate` (`test_decomposition.py:260`). |
| FR-089 DAG, no cycles | **Implemented** | `test_the_proposal_never_contains_a_cycle` (`test_decomposition.py:109`), `test_a_cycle_fails_the_gate` (`:239`). |
| FR-090 declared interface and dependencies | **Implemented** | `Module.interface` / `depends_on` (`views.py:491`); `test_a_dependency_follows_the_oracle_the_contract_already_carries` (`test_decomposition.py:121`). |
| FR-091 minimise interface surface, report the count | **Partly** | `interface_count` (`views.py:641`) is **reported**, not minimised — `decomposition.py:473` says so explicitly. No threshold, no alternative proposal. |
| FR-092 declared build order | **Implemented** | `build_order_exists` check (`decomposition.py:413`); `test_a_sound_proposal_passes_every_machine_check` (`test_decomposition.py:291`). |
| FR-093 per-module completion criteria | **Not built** | `completion_criteria` appears nowhere in `src/` or `tests/`. |
| FR-094 revisable without invalidating the whole | **Implemented** | Revisions + `decomposition_hash`; `test_approving_a_superseded_revision_is_refused` (`test_decomposition.py:467`). |
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
| FR-141 worktree per module | **Deferred** | ADR-0024. Prompt text only (`planner.py:124`); README states it is the largest gap. |
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

| Verdict | n |
| --- | --- |
| Implemented | 46 |
| Partly | 21 |
| Deferred (ADR-0024) | 1 |
| Not built | 49 |
| **Total FR numbers in the spec** | **144** (some are stated only as retained ranges, counted once) |

NFRs are not tabulated: NFR-001–024 are retained verbatim from v0.1 and are not
restated, so there is nothing to check them against. Of the new ones, NFR-025
(envelope) and NFR-030 (per-module attribution) are **not built**; NFR-027
(version-controlled artifacts) is **partly** (ledger + reports); NFR-028 (resume)
is **not built**; NFR-029 (per-phase wall-clock bound) is **partly** (per-step
only).

---

## 2. Gaps, ranked by what they block

1. **No system model and no P2 specification (FR-076, FR-078, FR-083, FR-115,
   FR-116).** One absent artifact blocks four requirements and both remaining P7
   checks. Every downstream phase that the spec says consumes the model — P3's
   decomposition, P6's structural oracles, P7's conformance check — reads the
   contract instead. ADR-0026 named it; ADR-0027 worked around it for FR-112 by
   declaring surfaces on the module. **Blocker: nothing defines what a
   machine-readable system model *is*, and the research note in
   `docs/research/system-model/` deliberately does not pick one.**
2. **No isolation boundary of any kind (FR-016–020, FR-059, FR-141).** FR-141 is
   deferred by ADR-0024 and is the gap the README itself names as mattering most;
   FR-059's "the harness cannot reach the oracle corpus" is prompt text and nothing
   else; FR-149's hermeticity is a property of the argv, not of the process. The
   measurement that forced this is in ADR-0024: neither `pi` nor `claude` confines
   its child. **Blocker: confinement needs a filesystem/network boundary
   (ADR-0005 refuses containers), so there is no layer left to put it in.**
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
5. **No phase state machine and no resume (FR-060, FR-062, NFR-028).** The pipeline
   is a sequence of CLI invocations over one log; the log survives, but "resume at
   any phase boundary with no gate re-passed silently" is not a property anything
   checks, and `sofact init` (the spec's planned verb, §23 M1) does not exist.
   **Blocker: gates are enforced by refusal inside commands, not by a state
   machine, so there is no phase state to resume *to*.**

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
