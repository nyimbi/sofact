# 23. A session record is addressed by a path, and that bounds the producer set

* Status: Accepted
* Date: 2026-10-12
* Deciders: operator
* Related: [ADR-0012](0012-the-harness-table-is-data-not-code.md),
  [ADR-0016](0016-a-harness-path-names-its-own-envelope.md),
  [ADR-0010](0010-delegation-to-a-third-party-harness-is-an-accepted-disadvantage.md)

## Context

The producer set is a row of data (FR-161): a harness is a `HarnessSpec` naming an argv, a
session glob, and paths into the record that argv writes. Adding a producer is meant to be
a table edit, and for three of the four candidates named as targets it was — `pi` and
`dsh` shipped as specs, and `claude` was added in this turn as one more row, measured end
to end before it was written down.

`opencode` did not fit, and the way it failed is the decision here.

## What was measured

`opencode` v2.0.25, on this machine, against its real install:

```console
$ opencode run --help
  --session, -s string    Session ID to continue, or to create if it does not exist
  --format choice         Output format (choices: default, json)

$ sqlite3 ~/.local/share/opencode/opencode.db '.schema session'
CREATE TABLE `session` (
  `id` text PRIMARY KEY,
  ...
  `tokens_input` integer DEFAULT 0 NOT NULL,
  `tokens_output` integer DEFAULT 0 NOT NULL,
  ...
)
```

Three of the four things an adapter needs are present. It accepts a session id SoFact
mints, so the adapter can address its own dispatch rather than guessing at a name. It has a
structured output format. And its record is queryable, with token spend as a column and the
session id as the primary key — a *better* telemetry surface than either file-based
harness.

The fourth is missing. `session_glob` is a filesystem glob. `~/.local/share/opencode/opencode.db`
is a single SQLite file whose `session` table holds every session this machine has ever
run; the record for one dispatch is a *row*, and a row is not a path. No glob names it. The
adapter reads the record by globbing `session_dir` and parsing what it finds
(`HarnessAdapter.session_files`), so for `opencode` it would find the database, not the
session, and either read nothing or read all 68 GB of it.

## Decision

**The record-access seam stays glob-shaped, and `opencode` is dropped as a target.**

1. **No record-source seam is built.** The alternative is a per-harness way to fetch a
   record — a command, or a query — behind the same interface `session_files` already
   presents. It is refused here on cost, not on impossibility: it is real machinery
   (subprocess, SQL, a schema to keep in step with someone else's migrations) in exchange
   for a fourth producer when three are wired and measured.
2. **The gap is recorded as a cost, not as an unfinished task.** The README states what
   fails and why, so the next person to consider `opencode` reads the measurement instead
   of repeating it. A capability gap described as "not yet done" invites work that this
   record has already priced and declined.
3. **The bound is named.** `session_glob` is not an incidental field; it is the constraint
   that makes file-based harnesses cheap and database-backed ones expensive. A future
   harness whose history is a service or a database is out of scope by this rule, and that
   is a fact about the seam an operator should know before proposing one.
4. **Nothing is claimed about `opencode`'s quality.** It was not rejected for being a worse
   harness. It was dropped because reading its record costs more than a fourth producer is
   worth, and the three wired producers already cover the shapes that matter — `pi` with no
   completion signal, `dsh` with a structured one, `claude` with a structured one and a
   capitalisation hazard.

## Alternatives refused

* **Shell out to `sqlite3` the way `session_is_zstd` shells out to `zstd -dc`.** Refused as
  a *first* move, though it is the shape a future seam would take. The zstd case is one
  command with no schema; this is a query against a table whose columns belong to another
  project's migration history, and a wrong column name fails the way ADR-0016's wrong path
  failed — silently, as `unmeasured`.
* **Point `session_glob` at the database file and parse it as JSONL.** Refused: it would
  read a binary file as text and report a parse failure that names the wrong cause.
* **Give `opencode` a private store via an environment variable, as `claude` gets
  `CLAUDE_CONFIG_DIR`.** Refused for lack of evidence: no such variable was measured, and
  inventing one would put an unverified value in a spec — the class of defect ADR-0018 and
  the `pi` `--tools` finding both punished.
* **Keep `opencode` in the table with an unprobed argv.** Refused: `probe` requires a
  session record to read (FR-148), so a spec whose record cannot be found is a row that can
  never leave `unmeasured`. It would be a claim of support with no way to test it.

## Consequences

* **The producer set is `pi`, `dsh`, `claude`** (plus `pi-research`, which is a
  configuration of `pi` rather than a fourth harness). The user's stated set included
  `opencode`; three of four are wired, and the fourth is declined with its cost on the
  record.
* **`claude` is the newest row and the most heavily measured.** Its spec carries a
  `tool_names` translation table and a `session_id_style`, both added because live probes
  found failures that data could fix: `--tools read,write` is accepted, exits 0, reports
  `completed`, and disables every tool, and `--session-id probe-xyz` is refused with
  "Invalid session ID. Must be a valid UUID." Neither is a code branch (FR-161).
* **A measured negative is recorded rather than rounded off.** The same probe run answered
  `sandboxable: absent` for `claude` — a child told to escape wrote one directory above its
  workspace, so `--tools Read,Write,Edit` does not confine it. This is the `pi` result
  again, now measured twice on two harnesses, and it is the strongest argument in the
  repository that confinement needs a filesystem boundary (FR-019, FR-141) rather than a
  tool allowlist.
* **The seam's limit is now documented where a spec is written**, so an operator proposing
  a database- or service-backed harness learns the cost from the README rather than from a
  probe that reads nothing.

## Evidence

* `opencode run --help` on v2.0.25 — `--session` accepts a caller-minted id; `--format json`
  exists.
* `sqlite3 ~/.local/share/opencode/opencode.db '.schema session'` — `id` is the primary
  key; `tokens_input` and `tokens_output` are columns. The database is 68 GB.
* `find ~/.local/share/opencode -name '*.jsonl'` — no match: there is no file-shaped
  session record to glob.
* Live `claude` probe, `/tmp/sofact-claude-live2`, two escape probes both writing
  `escape-marker.txt` one directory above their workspace:
  `sessions/claude/.probe/01a12ec2-.../escape-marker.txt` (contents `ESCAPED`) and
  `01a12ec3-.../escape-marker.txt` (contents `ESCAPE`).
* The same probe's `concurrent` row is `confirmed`: two simultaneous sessions wrote
  distinct `.jsonl` records under `projects/`.
* `src/sofact/harness.py` — `CLAUDE_SPEC`, its `tool_names` table, and
  `HarnessAdapter.session_id` / `render_tools`.
* `tests/ci/test_harness.py` — `TestTheToolVocabulary` and
  `test_claude_tool_names_are_capitalised_and_translated`.
* `README.md` § Harness — the `claude` measurement and the `opencode` cost.

## References

* FR-144 (reduced mode where goal mode is absent), FR-148 (the capability matrix is
  discovered at runtime), FR-161 (the adapter table is data); FR-019 and FR-141 (isolation
  needs a boundary, not an allowlist).
* [S23](../sources/s23-harness-base-candidates.md) — the candidate harness set, of which
  `opencode` is one.
* [ADR-0016](0016-a-harness-path-names-its-own-envelope.md) — the last time a field's
  *shape* was a fact about one harness written down as a rule about harnesses. This record
  is the same lesson applied before the defect rather than after it.
