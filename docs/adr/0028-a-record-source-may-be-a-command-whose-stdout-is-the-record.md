# 28. A record source may be a command whose stdout is the record

* Status: Accepted
* Date: 2026-10-12
* Deciders: operator
* Supersedes: [ADR-0023](0023-a-record-is-addressed-by-a-path.md), decision 1
* Related: [ADR-0012](0012-the-harness-table-is-data-not-code.md),
  [ADR-0016](0016-a-harness-path-names-its-own-envelope.md)

## Context

ADR-0023 dropped `opencode` because `session_glob` is a filesystem glob and opencode's
record is a SQLite row. It refused the record-source seam "on cost, not on impossibility"
and named the price: a subprocess, SQL, and a schema to keep in step with someone else's
migrations, in exchange for a fourth producer when three were wired.

Two things have changed, and both were measured before this record was written.

**The price fell.** `opencode session export <id>` now exists and prints the whole session
as one JSON document. There is no SQL and no schema to track — the objection ADR-0023
actually made was about tracking another project's migrations, and the command removes it.
The cost is now one subprocess per record.

**The demand grew.** Three candidates want a record source that is not a glob:
`opencode` (a command), `omp` (a private session directory and "the newest record", since
it mints its own id and exposes no `--session-id`), and `dsh` (the same shape). The seam
that was declined for one harness is now wanted by three, which changes the trade even if
the cost had not moved.

## Decision

**`HarnessSpec` may name a `session_command` whose stdout is the record, and that stdout is
materialised into a file before anything reads it.**

1. **The seam stays file-shaped.** `session_files` returns paths in both cases. When a spec
   declares a command, the command is run and its stdout is written to
   `<session_dir>/sofact-record-<session_id>.<record_format>`, and *that path* is returned.
   Every reader below — `read_records`, `parse_usage`, `parse_completion`, the continuation
   counter — is unchanged, and `session_path` stays a path a caller can open. FR-058 exists
   to keep the harness interface singular; a second, non-file-shaped return type would have
   made it two interfaces, and every reader would have grown a branch.

2. **A record has a declared *shape*, not a declared harness.** `record_format` is `jsonl`
   (one object per line) or `json` (one document for the whole session). It is a property
   of the bytes, because two harnesses can print the same shape and one harness can change
   shape between versions. `json` reads as a one-element sequence, so the document case
   does not become a second code path in every parser.

3. **Completion is read from the record, never from the exit code.** Measured on opencode
   2.0.25: a session whose provider returned 402 still exports, with
   `info.outcome = "failed"`, and **exits 0**; a malformed session id exits 1. Reading the
   exit code would report a failed session as completed and a succeeded one as unmeasured.
   This is why a `session_command` that exits non-zero or prints nothing yields *no* record
   rather than an empty one — "the harness would not hand it over" and "the session left no
   record" are different facts, and an empty file would read as the second.

4. **A whole-document record declares without an event envelope.** `completion_event` names
   the envelope an event-shaped record carries its reason in. A document *is* the session,
   so there is no per-event `type` to name, and opencode's spec declares none: the path
   `("info", "outcome")` is read straight off the document. `parse_completion` therefore
   treats the event as a filter *when declared*, not as a precondition for reading — the
   previous contract (`completion_event is None` ⇒ no signal) would have made the field
   unusable rather than honest for any document-shaped harness.

5. **A session id's shape is data.** opencode refuses an id that does not start with `ses`,
   measured: `-s probe-0123abcd` fails with `Expected a string starting with "ses"` before
   any model call, so the probe would report a harness failure that is really an identifier
   mismatch. `session_id_prefix` carries that requirement, for the same reason
   `session_id_style` carries claude's UUID rule.

## Consequences

* **`opencode` is wired**, and the producer set is `pi`, `dsh`, `claude`, `opencode` (plus
  `pi-research`). Its spec's argv is measured but **not witnessed end to end**: every run on
  this machine failed after the argv was accepted because the configured account is out of
  credit (HTTP 402), so generation is unwitnessed. The spec says so in its own notes rather
  than implying a successful dispatch.
* **ADR-0023's decision 1 is superseded; its decisions 2–4 stand.** The bound it named —
  that a database- or service-backed harness is expensive under a glob — is still true, and
  is now the reason `session_command` exists rather than a reason to decline the harness.
* **The seam is tested against a real child**, not a mock: the synthetic harness keeps its
  record in a private store that no glob matches, and the export command's stdout is the
  only way to reach it. The glob in that spec is deliberately one that matches nothing, so a
  passing test cannot be passing because a file happened to be there.
* **A canary caught a fixture that proved nothing.** Disabling the whole-document branch
  left the suite green, because the synthetic export printed compact JSON — one line, which
  a line-oriented reader parses happily. The fixture now prints indented JSON, as the real
  command does, and the canary fails. A fixture whose shape is *convenient* rather than
  *measured* tests the reader against an input the producer never emits.

## Alternatives refused

* **Return the document as a mapping from `session_files`, widening its type.** Refused: it
  makes the seam two shapes, and every one of the four readers would branch on which it
  got. The materialised file costs one write and keeps one interface.
* **Shell out to `sqlite3` against opencode's own tables.** Refused, and this is the refusal
  that survives from ADR-0023: the columns belong to another project's migration history,
  and a wrong column name fails the way ADR-0016's wrong path failed — silently, as
  `unmeasured`. The export command is the vendor's own reader, so SoFact tracks a command
  whose output shape is public rather than a schema that is not.
* **Read completion from the process exit code.** Refused on measurement: opencode exits 0
  for a session that failed.
* **Keep `completion_event` mandatory for any completion signal.** Refused: it would force
  a document-shaped harness to name an event that does not exist, or to declare no signal
  while carrying a perfectly good one in `info.outcome`.

## Evidence

* `opencode session export --help` on v2.0.25 — `--standalone`, `--server`, `--sanitize`.
* `OPENCODE_DB=<dir>/priv.db OPENCODE_TEST_HOME=<dir>/home opencode run --standalone -s
  ses_probe0123abcd --format json "say hi"` — exits 1 on a 402; the private store is
  created and `session export --standalone ses_probe0123abcd` then prints
  `info.outcome = "failed"` with `tokens.output = 0`, exit 0.
* `opencode run --standalone -s probe-0123abcd …` — `{"type":"error", … "message":
  "Expected a string starting with \"ses\""}`, so the prefix is required, not cosmetic.
* `opencode run --help` — no `--tools`; tool policy is chosen by `--agent`, so a dispatch
  cannot narrow this harness's tool set and `confinement_tools` is empty by measurement.
* `docs/research/driver-set/README.md` — the full measurement, including the omp and omc
  results and the note that no generation completed.
* `src/sofact/harness.py` — `HarnessSpec.session_command`, `record_format`,
  `session_id_prefix`; `OPENCODE_SPEC`; `session_files` / `_materialise` / `read_records`.
* `tests/ci/test_harness.py` — `TestTheRecordCommand` and the opencode spec-shape tests.
