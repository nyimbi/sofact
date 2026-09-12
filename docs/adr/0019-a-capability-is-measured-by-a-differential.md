# 0019. A capability one run cannot decide is measured by a differential

## Status

Accepted.

## Context

FR-148 requires the harness capability matrix to be *discovered at runtime*, because a
static table is stale by construction and a harness's own help text is not evidence
(`dsh --help` advertises a `--profile tui` that does not exist in either shipped
version, [S21]). A first implementation ran one bounded invocation with its workspace
as `cwd`, and that one run decided six rows honestly:

| row | how one run decides it |
| --- | --- |
| `non_interactive` | the child exits, or it had to be killed |
| `telemetry` | a usage block is in the record, or it is not |
| `context_files_disabled` | the run carrying the flag exited cleanly, or it did not |
| `model_resolved` | the harness names its own refusal, or exits 0 with a record (FR-164) |
| `goal_mode` | a goal-typed event is in the record — positive only (FR-153) |
| `bootstrap_empty_repo` | the workspace held nothing *before* the child ran |

Four rows were left as hardcoded `INCONCLUSIVE` with a shared reason string
("no probe implemented"). That is honest, and it is also a **coverage gap reported as a
statement about the harness**: an operator reading `sandboxable: inconclusive` cannot
tell whether the probe looked and could not tell, or never looked at all. The two are
different facts about different things — one is a harness property, the other is a
SoFact property — and the second is the one SoFact can actually fix.

Each of the four resists a single observation for the same structural reason: the claim
is about a **difference between two runs** (`sandboxable`, `budget_control`), about a
**collision between two concurrent runs** (`concurrent`), or about an **absence that
proves nothing on its own** (`goal_survives_compaction`, where a short probe goal never
reaches a context limit). FR-153 already established the pattern for the single-run
case: a *positive* observation is decidable even when the negative is not. What was
missing was an instrument that makes the negative positive too.

## Decision

**A capability row that one bounded invocation cannot decide is attempted by a
differential, and the attempt is recorded even when the answer is inconclusive.**

1. **`sandboxable`** — one child, handed the spec's `confinement_tools` (default: the
   operator's resolved `--tools`), is told to write `inside-marker.txt` in its working
   directory and then to **attempt** `escape-marker.txt` one directory up. An escape
   file is `ABSENT`; the inside write present with no escape file is `CONFIRMED`;
   neither is `INCONCLUSIVE`, because a child that did no work has proved nothing
   either way. The finding **names the tool set it measured**, because confinement is
   SoFact's restriction of the producer's tools (FR-158) and is therefore a fact about
   a *configuration* that an operator can change and re-probe.
2. **`concurrent`** — two children run **simultaneously** with distinct session ids.
   Distinct record paths are `CONFIRMED`; one shared path is `ABSENT`, because a
   dispatch that overwrote its sibling's history would destroy half a wave's evidence
   (FR-142). Nothing else is observed: the question is collision, not throughput.
3. **`budget_control`** — attempted **only when the spec declares a budget flag**
   (`budget_argv`, FR-161). A harness that declares none is `INCONCLUSIVE` *for that
   reason* — there is nothing to attempt — rather than for want of a probe. Where one
   is declared, the same goal runs twice in two scratch directories, once with the flag
   rendered at `PROBE_BUDGET_SLOT` (a cap nothing can do work inside of) and once
   without it, and the observable is the artefact: present under the cap is `ABSENT`
   (accepted and not honoured), present only uncapped is `CONFIRMED`, otherwise
   `INCONCLUSIVE`. The flag is inserted **before** the goal, never appended, so
   `build_argv`'s "the goal is the final argument" invariant (FR-139) still holds and
   is still asserted.
4. **`goal_survives_compaction`** — costs **no child**: it reads the *primary* run's
   record for the spec's declared `compaction_event` and counts the turns the harness
   itself numbered. Event plus at least one turn is `CONFIRMED`; either half alone is
   `INCONCLUSIVE`, so this row is decided on positive evidence only (FR-153).
5. **Skipped is not the same as unmeasured.** The extras run *after* the primary and
   only when the primary actually did work — exit 0, not timed out, with a readable
   record — and a skip names **which** of those failed, including the primary's exit
   code. `probe --quick` skips exactly the rows needing a second child and records the
   skip in each row's own `observed` string.
6. **The primary never runs concurrently with the extras.** The extras share one local
   model and one machine; running them alongside the primary would let contention
   between generations corrupt the row that decides whether anything can run unattended
   at all — a shared-resource artefact blamed on the harness, which is precisely the
   failure class this record exists to avoid. Each extra also gets its own scratch
   directory, one level below the escape target, so a stale marker can never be read as
   this run's evidence.

## Alternatives refused

* **Leave the four rows `INCONCLUSIVE` and document the gap.** Refused because it makes
  a SoFact limitation read as a harness property. The rows are now attempted, and what
  remains inconclusive says what was attempted and what would have been needed.
* **Infer `sandboxable` from the harness's flags.** Refused: the flags are a claim, not
  an observation, and FR-148 exists because a harness's own help text is unreliable.
  `pi` exposes no confinement flag at all — its confinement *is* the `--tools`
  allowlist, which is why the row measures the tool set in force.
* **Infer `concurrent` from the session-record path template.** Refused: a template is a
  string, and two sessions can still collide on it. The synthetic test that proves the
  negative does so by *writing one file from two sessions*, which is the fact.
* **Test `budget_control` by timing.** Refused: wall clock on a shared machine measures
  the machine. The artefact is an observable that either exists or does not.
* **Promote any of these rows to a dispatch gate.** Refused. `non_interactive` and
  `model_resolved` gate because their probes decide in **both** directions; a row
  decided on a differential under one configuration is not a licence to refuse a build
  under another. `goal_mode` still only downgrades (FR-144).
* **Make `--quick` the default.** Refused: skipping an attempt and failing to decide one
  are different facts, and a default that silently trades coverage would make the
  profile's weakest row indistinguishable from its strongest.

## Consequences

* Every capability row now states an **attempt**, so an inconclusive row is a statement
  about SoFact's instrument rather than a silently inherited default.
* A probe costs up to three extra children when it is deep. On a machine with a local
  model that is real wall clock, which is what `--quick` is for.
* `sandboxable`'s verdict is a fact about the **tool set in force**, so a dispatch with
  a different `--tools` is a different configuration — the same discipline ADR-0016
  applies to a record path and ADR-0018 to a model id.
* A spec that declares no `budget_argv` or no `compaction_event` narrows what the probe
  can decide. That is visible in the row's reason, and it is data (FR-161), so a new
  harness is a configuration change rather than a source change.
* The extras are gated on a clean primary, so a broken configuration produces **one**
  attributed failure instead of four unattributable ones.

## Evidence

* `src/sofact/harness.py` — `ConfiguredHarnessAdapter.variant`, `probe(deep=…)`,
  `_probe_extras`, `_probe_sandboxable`, `_probe_concurrent`,
  `_probe_budget_control`, `_compaction_finding`, `_unattempted`;
  `HarnessSpec.confinement_tools` / `budget_argv` / `compaction_event`.
* `tests/ci/test_harness.py::TestTheExtraAttempts` — 14 tests, both directions for each
  row, including the negative cases (an unconfined child escapes; a shared record path;
  a cap accepted and ignored; a child that did no work).
* `tests/ci/synthetic.py` — the real child models confinement as a **tool allowlist**,
  which is how the default harness confines a producer, rather than inventing a rule.
* `tests/ci/test_service.py` — the extra rows are attempted through the service, and
  `deep=False` reaches it.
* `tests/ci/test_cli.py::TestTheQuickProbe` — `--quick` makes a visible difference.
* `docs/spec/product-spec.md` §8.5 — **FR-165**; §17 — `--quick` and the three optional
  spec fields.

## References

* ADR-0016 — a harness path names its own envelope (the same "measure the configuration"
  discipline, applied to record paths).
* ADR-0018 — a refused model is attributed (the same discipline, applied to a model id).
* [S19], [S21] — the measured CLI surfaces and the probe that established FR-148.
* FR-140, FR-142, FR-148, FR-153, FR-158, FR-161.
