# 16. A harness path names its own envelope

* Status: Accepted
* Date: 2026-09-12
* Deciders: operator
* Supersedes: the `data`-relative path convention documented in `HarnessSpec`'s docstring
* Related: [ADR-0012](0012-the-harness-table-is-data-not-code.md),
  [ADR-0010](0010-delegation-to-a-third-party-harness-is-an-accepted-disadvantage.md)

## Context

FR-161 made the harness adapter table data rather than code. Two of its fields are
**paths into a session record**: `completion_reason_path` (where a completion declaration
says `completed`) and `usage_path` (where token spend is reported). Both were documented as
relative to a record's `data` block, because every `dsh` event on the wire is
`{seq, time, type, data}` — the envelope was stripped before either path was walked
(`_data_of`).

That convention was a fact about the first harness, written down as a rule about harnesses.

## The defect

The decisive probe of this turn ran `sofact probe` against a real `pi` 0.85.1 binary on a
fresh home, and produced this row:

```text
  absent        telemetry
                attempted: read the session record for a per-message usage block
                observed:  session record contains no usage block, so spend cannot be
                           attributed from the record
```

The record on disk said otherwise. `/tmp/sf-real/sessions/pi/2026-09-12T06-02-18-170Z_probe-01a09435.jsonl`,
five rows, ends with:

```json
{"type": "message", "id": "05926676", "parentId": "35d42583", "timestamp": "2026-09-12T06:02:21.459Z",
 "message": {"role": "assistant", "content": [{"type": "text", "text": "ready"}],
 "api": "openai-completions", "provider": "ollama", "model": "deepseek-v4.1-flash:cloud",
 "usage": {"input": 3535, "output": 3, "cacheRead": 0, "cacheWrite": 0, "reasoning": 0,
 "totalTokens": 3538, "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0}},
 "stopReason": "stop", "timestamp": 1789192939000}}
```

**There is no `data` key anywhere in a `pi` record.** Top-level keys are
`{cwd, id, timestamp, type, version}` for the session row and
`{id, message, parentId, timestamp, type}` for a message row. `_data_of` therefore returned
`None` for every record, `parse_usage` returned `None`, and the probe reported the only
thing it could see.

Two independent facts compounded:

1. `PI_SPEC.usage_path` was `()`, which short-circuits `parse_usage` before any record is
   read. That value was itself a stale measurement: [S19] recorded that `pi` emits no usage,
   which was true of the version measured then and is false at 0.85.1.
2. Even with a path, the walk started at a block `pi` does not write.

**The failure mode is the dangerous one, because it is not an error.** `telemetry ABSENT`
is a legitimate outcome — NFR-024's honest "unmeasured" — and the probe's own strings
distinguish `unmeasured` from `wrong`. A wrong path therefore produced a row that was
indistinguishable from a true negative, in the correct format, with a confident reason
string. This is exactly the class FR-161 names for a misspelled `usage_reduce`; the
difference is that a misspelling is caught by the loader and a wrong *root* was not.

It was caught only because a human read the record the machine had just written.

## Decision

**A path names its own envelope, and nothing is stripped implicitly.**

1. **Both paths are walked from the record root.** `parse_completion` and `parse_usage`
   call `_walk(record, spec.<path>)`; `_data_of` is **deleted**, so no implicit stripping
   and no fallback root exists to go stale.
2. **The envelope is spelled out in the spec.** `DSH_SPEC` carries
   `completion_reason_path=("data", "reason", "kind")` and
   `usage_path=("data", "usage", "outputTokens")`; `PI_SPEC` carries
   `usage_path=("message", "usage", "output")`.
3. **A wrong path stays `None`, which the probe reports as `unmeasured`** — never `0`. The
   new root does not weaken NFR-024; it restores a distinction the old root had erased.
4. **Key names are not normalized across harnesses.** `pi`'s `output` and `dsh`'s
   `outputTokens` are the same quantity under different names, and that equivalence is
   documented in `PI_SPEC.notes` and §8.5 rather than encoded in an alias table.
5. **The correction is a data edit.** No branch, no subclass, no per-harness code path — the
   row changed and the adapter did not (FR-161). `PI_SPEC.notes` and [S19] were corrected to
   match the measurement, and the docstring now states the rule the fields actually follow.

## Alternatives refused

* **Synthesize a `data` envelope for `pi` before parsing.** Refused: it is a per-harness
  code branch inside FR-161's seam, and it would make a `pi` record *look* like a `dsh`
  record, i.e. discard a measured wire shape to preserve a rule that was only ever a
  generalization from one harness.
* **Try the record root, then fall back to `data`.** Refused: two sources of truth for one
  lookup. A fallback converts a wrong path from a loud `unmeasured` into a quiet guess, and
  the guess need not be a different *presence* — it can be a different **number**.
  `pi` reports `output` and `totalTokens` side by side; a fallback that lands on the wrong
  key reports a plausible, wrong token count, which is strictly worse than the `ABSENT` row
  being fixed here.
* **An alias table mapping harness key names to a canonical name.** Refused for the same
  reason: it accepts spellings nothing measured, and it makes the table's own correctness
  depend on the alias list staying right.

## Consequences

* **`pi` telemetry is measured, live.** The same probe against the same binary now reports
  `confirmed  telemetry — session record reports token usage (observed 3)`, where `3` is
  the output-token count in the record above.
* **A `pi` dispatch can attribute spend** (FR-143, FR-151): `DispatchRecord.tokens_observed`
  is populated from `message.usage.output` summed over the session, so the harness with no
  completion signal is still not the harness with no telemetry. Before this record, `pi`
  was both.
* **The seam's documented shape changed, and it is announced rather than tolerated.** An
  operator table written against the old convention now reads nothing — no error, no
  warning, just `unmeasured`. That is a breaking change to a v0.1 seam, and the response is
  to document the rule where an operator writes a table (README, §8.5 FR-161) instead of
  accepting both roots.
* **`pi` still declares nothing.** `completion_event` remains `None`, so `parse_completion`
  returns `False` without walking a path, and `DeclarationPrecision` stays **unmeasured**
  for `pi` — an asymmetry with `dsh` that is a measured fact about the harnesses, not an
  oversight in the adapter.
* **What remains unmeasured about `pi`:** `goal_mode` is still `INCONCLUSIVE` (no
  goal-typed events), and `sandboxable`, `concurrent`, `budget_control` and
  `goal_survives_compaction` are still probe coverage gaps (FR-148).

## Evidence

* Live probe, fresh home, `pi` 0.85.1, before the fix — `telemetry absent`:
  `/tmp/sf-real`.
* The record that contradicted it:
  `/tmp/sf-real/sessions/pi/2026-09-12T06-02-18-170Z_probe-01a09435.jsonl` (5 rows; types
  `session`, `model_change`, `thinking_level_change`, `message`, `message`).
* Live probe, fresh home, after the fix — `telemetry confirmed … (observed 3)`:
  `/tmp/sf-real2`.
* `tests/ci/test_harness.py`:
  `test_pi_usage_is_read_from_the_message_envelope` (sums `3 + 7` across two assistant
  messages, skipping the user message) and `test_a_data_envelope_is_named_not_assumed`
  (each harness's shape reads `None` through the other's path, and the right number through
  its own).
* The table seam, unchanged and still data:
  `tests/ci/synthetic.py`'s spec carries the `data`-rooted paths, and its records are
  `{..., "data": {...}}` — the same convention `dsh` uses.

## References

* [S19](../sources/s19-harness-cli-surface.md) — `pi`'s CLI and record surface; corrected by
  the re-measurement recorded here.
* [S21](../sources/s21-dsh-probe-executed.md) — the `dsh` record shape the old convention was
  generalized from.
* FR-058, FR-143, FR-148, FR-151, FR-161; NFR-024 (refusing unmeasured targets).
* [ADR-0012](0012-the-harness-table-is-data-not-code.md) — why the fix is a row.
