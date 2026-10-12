# SoFact

**Turn an imagined product into a verifiable one.** SoFact interrogates a goal until
it is falsifiable, compiles it into a contract whose every clause names the oracle
that would check it, and then verifies the result *independently of whoever produced
it*.

SoFact is not a coding agent. It contains no edit-run-revise loop. It is the control
plane around one: the part that decides what "done" means, and the part that refuses
to believe a producer's own claim that it is done.

## Status

| Phase | State |
| --- | --- |
| **P0 — Elicit** | **Working.** Interactive Socratic dialogue with a deterministic resolution gate. |
| **P2/P4 — Specify & contract** | **Working.** Clause stems are drafted from the conversation; `contract` assigns one oracle to every stem. Without a `--command` it reports **100% ground-truth debt** rather than hiding it. |
| **P6 — Verify** | **Working.** `run` executes the oracles out-of-process and records observations; `verify` renders the verdict — and takes **no completion claim**, by signature (FR-138). A verdict describes one *run* (FR-006/FR-162), so a repaired clause can turn green. |
| **P3 — Decompose** | **Working.** `decompose` proposes one module per clause — deterministically, from the contract alone, with no model call — and gates it: traceability both ways (FR-088), acyclicity (FR-089), a build order (FR-092), a declared interface per module (FR-090) and the interface count (FR-091). The gate has **two halves and cannot be passed on one**: the machine checks are facts, and `--approve` records the operator's separate judgement, so an approval cannot waive a failed check (FR-087/FR-061). `plan` **refuses to run** past an unapproved gate. [ADR-0025](docs/adr/0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md) records why a module is one clause. |
| **P5 — Dispatch** | **Working.** `plan` compiles the contract into ordered goal sessions with pinned hashes (FR-136/139); `probe` measures a harness instead of trusting it (FR-148); `dispatch` runs the plan in waves, one out-of-process session per step, on a **branch per module** (FR-100), resolved from the approved decomposition so several steps of one module share its branch — that is how FR-100's "per module" reconciles with FR-136's refusal to dispatch one session per module. The branch is established before the session starts, and SoFact commits the session's work onto it when the session ends, so each step is a commit on its own ref rather than a pile of files the next step inherits; branch and seal are both carried on the dispatch record, so "never in place" is a fact in the log rather than a line in a prompt; it stops at the first **refuted** wave (FR-142/FR-163); `repair` turns that refutation into another session, bounded per clause, with the diagnosis and every attempt recorded (FR-098 diagnostic mode, FR-101, FR-102). **Worktree isolation (FR-141) is not implemented**, and it is the gap that matters most — a probe measured that neither `pi` nor `claude` confines its child to the working directory, so a step that wanders writes into the checkout, branch or no branch. [ADR-0024](docs/adr/0024-branch-per-step-is-built-worktrees-are-deferred.md) records why worktrees are deferred rather than built now, and what makes them necessary. What remains for FR-141 is the measurement ADR-0024 named, not a missing concept: the branch already names the module. |
| **P7 — Integrate** | **Partly working, and the report says which part.** `integrate` runs three checks over the dispatched work: the **build order** (FR-111) — a module built before a dependency of it sealed anything — **import discipline** (FR-113), which *parses* the files each module's step sealed and reads their `import` statements rather than asking a producer to be careful, and **interface conformance** (FR-112), which diffs the public names a module's files actually expose against the surface its module *declared*. Every finding carries FR-114's **minimum violating set**, so a repair is scoped to the modules implicated and never to the platform. **FR-112 is only discharged once a module declares a machine-readable surface** — a proposal derives none, because nothing in a contract's clauses is a signature and inventing one would fabricate the contract P5 implements and P7 certifies (ADR-0025) — so the check runs, diffs nothing, and the report names FR-112 as `not_implemented` alongside **FR-115** (the §6.3 system model is not a type) and **FR-116** (P2 acceptance criteria the contract does not carry). A green line here is not a claim about those. |
| **P1 — Research** | **Working.** `research` authors the session's goal with zero model involvement, dispatches it, and records the artefacts it left (FR-167). A report with no cited sources is recorded as a run that found nothing, never rounded into research that happened. |

This is a deliberate vertical slice of the part that survives every argument in
[`docs/spec`](docs/spec/product-spec.md) and
[`docs/research/findings.md`](docs/research/findings.md): the intent front end plus
independent verification. Everything else — including the coding harness — is
delegated, per [ADR-0004](docs/adr/0004-delegate-the-coding-loop-to-an-external-harness.md) and
[ADR-0005](docs/adr/0005-no-container-runtime.md).

## Run it

Ollama must be reachable for the advisory model. SoFact degrades gracefully to a
deterministic questionnaire without it.

```sh
uv run sofact                     # start (or resume) a conversation
uv run sofact status              # where am I
uv run sofact phase               # which pipeline phase, and is a gate open
uv run sofact ledger              # the append-only event log
uv run sofact verify-ledger       # re-check the hash chain
```

State lives in `./.sofact` by default, or `$SOFACT_HOME`. Nothing is written outside
it, no containers are used, and the only network egress is the model you configure.

## How it works

The ledger is the system. Every fact is an append-only, hash-chained event; all state
is a pure fold over that log, so any state can be re-derived and any tampering is
detectable ([ADR-0003](docs/adr/0003-the-ledger-is-append-only-and-hash-chained.md)). Elicitation is gated by
deterministic floors rather than model judgement
([ADR-0007](docs/adr/0007-the-elicitation-gate-is-deterministic.md)), and the model is an
*advisor* whose opinions are recorded but never authoritative
([ADR-0008](docs/adr/0008-the-model-is-advisory-only.md)).

The pipeline is a phase machine with four human gates
([ADR-0030](docs/adr/0030-phases-are-a-state-machine-and-a-gate-is-a-type-boundary.md)).
`sofact phase` exits non-zero while a gate is open, and the gate cannot be passed by
anything but an operator naming themselves:

```sh
uv run sofact gate --present P2            # the phase's machine checks are ready
uv run sofact gate --approve P2 --by you   # the human half, recorded with who and when
```

A clause without an oracle cannot exist, which is the type-level enforcement of the
spec's first rule: **no oracle, no autonomy** (FR-001).

P2 turns the contract into a **specification**
([ADR-0031](docs/adr/0031-a-specification-derives-what-the-contract-says-and-declares-what-it-does-not.md)):
one requirement per clause, each carrying that clause's own oracle as its acceptance
criterion, plus the system model, non-goals, assumptions and value hypothesis. The
requirements are *derived* and the rest is *yours* — the factory invents none of it,
because a specification filled with plausible sentences would pass its own gate while you
had approved nothing. A criterion no command can evaluate is marked `human-verified` and
counted, not failed: FR-082 permits it and makes its cost visible instead.

## Harness

SoFact contains no coding loop. `dispatch` hands each plan step to a harness as an
**out-of-process** session, then reads the harness's *own* session record — exit code,
tokens, continuations, whether goal mode was really entered — instead of asking it.
Which harness is a **row of data, not a class**:

```sh
uv run sofact contract --command 'pytest -q'   # every stem needs an oracle
uv run sofact specify                          # contract → requirements, gated but unapproved
uv run sofact specify --approve --by me \
  --entity 'Reminder:1' \
  --assumption 'client schedules | a server scheduler appears' \
  --value 'fewer missed | the end user | session logs'
uv run sofact decompose                        # contract → modules, gated but unapproved
uv run sofact decompose --approve --by me      # the operator's half of the gate (FR-087)
uv run sofact plan                             # contract → ordered goal sessions
uv run sofact probe                            # attempt a harness; record observations
uv run sofact dispatch --all                   # run the plan; stops at the first refuted wave
uv run sofact repair                           # hand each refuted clause back to the producer
uv run sofact integrity                        # re-verify the pinned hashes (FR-139)
uv run sofact integrate                        # P7: build order + import discipline + surface diff
uv run sofact precision                        # did the claims survive verification?
```

`dispatch` stops at the first refuted wave, which is correct — a dependent must not build
on an unverified dependency. `repair` is the next move: a refutation is *information*, and
a verdict naming which obligation does not hold is exactly what another session needs. It
authors a **new plan revision** per round (an edited plan would make FR-139 compare the
plan against itself), hands the producer the verifier's own words as the diagnosis, and
re-runs the oracles. The loop is bounded twice — `--max-attempts` per clause and the clause
set itself — and when a clause spends its budget the attempt is recorded `exhausted` rather
than the run quietly ending, because "ran out of attempts" and "nothing to repair" must not
look alike. The repair goal forbids editing the oracle and is pinned by hash like any other,
so the loop cannot become a producer editing its own completion criteria.

`probe` is not optional: dispatching against an assumed capability is exactly what
FR-148 forbids, so `dispatch` refuses until a profile exists.

Which tools the producer gets is the operator's decision, so it is a flag rather than a
constant: `--tools read,edit` (or `SOFACT_TOOLS`) narrows the allowlist, and `probe`
prints the set it resolved before anything is dispatched. An empty set is refused — an
empty allowlist is a producer with no way to write, and that must not arrive later as a
failed step.

A producer's declaration is **not evidence, and it is not the trigger either**. Whenever a
dispatched session **completes**, SoFact runs that contract's oracles in the *session's*
workspace and records the verdict; when the harness also declares completion, the claim is
recorded as its own separate row, first (FR-138/FR-163). Gating that check on a declaration
makes the default harness unverifiable — `pi` has no completion event at all — so a run
that built working code would record no evidence and still exit `0`. So `dispatch` exits
**non-zero** when nothing was verified, when a step was refuted by its own check, or when a
plan that ran to its end left the contract unclean (including *insufficient*: an artefact
nothing could check is not a verified one). A run you capped with `--max-steps` is progress
rather than failure and exits `0` unless a step it ran was refuted. `verify` remains the
command that renders a verdict on demand (P6).

`pi`, `dsh`, `claude` and `opencode` ship as specs. To point SoFact at another harness
without editing `src/`, write a JSON table and set `SOFACT_HARNESS_SPECS`:

```json
{
	"harnesses": {
		"my-harness": {
			"argv": ["my-harness", "--goal", "{goal}", "--session", "{session_id}"],
			"session_glob": "**/*{session_id}*.jsonl",
			"completion_event": "turn/end",
			"completion_reason_path": ["data", "reason", "kind"],
			"goal_event_types": ["goal/created"]
		}
	}
}
```

Omitted fields keep their defaults; unknown fields, wrong types, missing required
fields and bare strings where a sequence belongs are refused **by name**. A misspelled
key that silently defaulted would produce a plausible, wrong number rather than an
error (FR-161). A malformed file, an unknown harness name, or a table holding several
harnesses with no default all exit non-zero instead of guessing.

`completion_reason_path` and `usage_path` are walked **from the record root**, and the
envelope is named explicitly when there is one — `dsh` events are
`{seq, time, type, data}`, so its paths begin `data`; `pi` writes `{type, message}` and
its usage path begins `message`. Nothing is stripped implicitly, because a fixed
envelope silently reads nothing on a harness that has no such block, and "no usage" is
indistinguishable from "wrong path" once that happens.

A record need not be a file the harness wrote. A harness whose history is a database
declares `session_command` — an argv whose **stdout is the record** — and `record_format`
(`jsonl` for one object per line, `json` for one document covering the session). SoFact
runs the command and writes its stdout to a file in the session directory, so every reader
sees a path and the seam stays single. `opencode` is wired this way:

```json
{
	"argv": ["opencode", "run", "--standalone", "-s", "{session_id}", "--format", "json",
	         "--model", "{model}"],
	"record_format": "json",
	"session_command": ["opencode", "session", "export", "--standalone", "{session_id}"],
	"session_id_prefix": "ses_",
	"completion_reason_path": ["info", "outcome"],
	"completion_reason_value": "succeeded"
}
```

Completion is read from the **record**, never the exit code: a measured opencode session
whose provider refused the request still exported `outcome: "failed"` and exited `0`. A
`session_command` that exits non-zero or prints nothing yields *no* record, because "the
harness would not hand it over" and "the session left no record" are different facts.

## Model

Default: `deepseek-v4.1-flash:cloud` via Ollama's OpenAI-compatible endpoint — a
1M-token context model served through Ollama's cloud, not locally. Override with
`SOFACT_MODEL` / `SOFACT_BASE_URL`. See
[ADR-0002](docs/adr/0002-model-access-is-one-openai-compatible-interface.md) for what that costs in hermeticity.

For a real coding session the model must be one the **harness** can resolve, not merely one
Ollama serves: `pi` validates `--model` against its own registry and refuses a local tag it
does not list (`Error: Model "…" not found`, exit 1, no session record). `qwen3.6:35b-mlx`
is what the end-to-end run used — `SOFACT_MODEL=qwen3.6:35b-mlx sofact probe` before
dispatching.

That refusal is **attributed rather than blamed on the producer**. A session that exits
non-zero having written no record is byte-for-byte what a producer that tried and failed
looks like, so the probe asks the question directly and records the answer as the
`model_resolved` row, quoting the harness's own words; a profile that watched a refusal
makes `probe` and `dispatch` exit non-zero before anything runs, saying so. The refusal
string is **data on the spec** (`model_error_pattern`), so pointing SoFact at another
harness teaches the probe that harness's wording rather than requiring a source change
(FR-161, FR-164). A profile also records *which* model it measured: dispatch against a
different one is refused, because "this harness works" is a claim about a configuration,
not about a name.

A verdict is **keyed, then reused** (FR-006's second half, FR-166). Every dispatch check
digests the workspace the session worked in — content hashes over the tree, ignoring VCS
metadata, caches, dependency installs and build outputs, skipping symlinks — and folds the
digest with the contract and oracle-set hashes. A previous verdict with the same key holds
without re-running; the reuse is its own ledger row (`verdict.reused`) naming the verdict
it stands in for, and `dispatch --fresh` bypasses it. A refuted verdict is reused exactly
like a satisfied one. `verify` never reuses: it weighs the log, and a log has no tree to
digest.

**Research is a dispatch too** (`sofact research [query]`, FR-167). SoFact authors the
research goal with zero model involvement and hands it to a harness whose research loop
is an installed `pi` extension ([S25]); the build spec freezes extensions out
(`--no-extensions`) and the research spec is the one row that names its allowance, with
`RESEARCH_MODEL` pinned to the operator's model, and the extension's tools named in the
producer's allowlist — measured, an allowlist without them leaves the producer no way
to call the loop at all. The verb records what the workspace
holds — report size, the loop's own search count from `research-meta.json`, cited URLs —
and never rounds a report with no sources into research that happened: on a local model
the extension's own timeout binds first, and that fact reads *unmeasured*, not *none
found* (NFR-024).

The probe's remaining rows are **attempted rather than assumed** (FR-165). Five of them
need more than one child, so each is a *differential*: `sandboxable` hands one child a tool
set that cannot write outside its directory and tells it to attempt an escape (the escape
file appearing is the negative, and the finding names the tool set, because confinement is
SoFact's tool allowlist and not a harness property); `concurrent` runs two children at once
and compares the record paths they wrote, since a shared path would make a wave destroy its
own evidence; `budget_control` runs the same goal capped and uncapped and compares the
artefact, but only when the spec declares a budget flag; `store_isolated` runs the same goal
twice with `HOME` relocated and the spec's declared containment variables applied in one arm
and withheld in the other, so the isolated arm's empty `HOME` is evidence only once the
control arm's filled — the control is what stops a harness the probe cannot see from reading
as a contained one; `goal_survives_compaction` reads
the primary run's record and costs no child. The extras run **after** the primary and only
if it actually did work, because they share one local model and a contention artefact would
be blamed on the harness. `probe --quick` skips the ones needing a second child and records
the skip in each row's own reason.

One row was decided against the real harness and the answer is not flattering to it:
measured live at `pi` 0.85.1, the `--tools read,write,edit` allowlist **does not confine
the working directory** — a child told to escape wrote one directory up, so `sandboxable`
reads `absent` for `pi`'s default confinement. An allowlist filters which tools exist, not
where they reach; real confinement for `pi` needs a filesystem boundary (FR-019), not a
flag. This is what the matrix is for: the row is a measurement, and a harness whose help
text suggests otherwise is exactly the case FR-148 exists to catch.

`claude` (Claude Code) was measured the same way on 2026-10-12 and answered the same:
run with `--tools Read,Write,Edit` and told to escape, the child wrote one directory above
its workspace, so its `sandboxable` reads `absent` too. Its row also carries a second
measurement worth more than the flag it describes — `--tools read,write` is *accepted*,
exits 0, reports `terminal_reason: completed`, and leaves the producer with **no tools at
all**, because the names are capitalised. A producer that silently loses every tool still
reports success, which is why the spec carries a `tool_names` table and the adapter
translates rather than passing names through.

`opencode` is **not** a target, and the reason is worth recording so nobody re-opens it
blind. Its session history is a SQLite database (`~/.local/share/opencode/opencode.db`),
not a file. Everything else about it fits: `opencode run --session <id>` accepts an id the
adapter mints ("to continue, or to create if it does not exist"), `--format json` exists,
and the `session` table carries `id` as its primary key beside `tokens_input` and
`tokens_output`. What fails is only the addressing — `session_glob` is a filesystem glob,
and a row in a database is not a path, so no glob names the record. Reading it would need a
record *source* seam, the same shape as the zstd case that already shells out to decompress
rather than pretending the file was plain JSONL. That seam is not worth building for a
fourth producer when three are wired, so opencode is dropped as a target rather than left
half-claimed. This is the honest version of a capability gap: not "unmeasured", but
"measured, and the cost of the seam exceeded the value of the producer".

## Develop

```sh
uv run pytest -vxs tests/ci
uv run pyright
uv run ruff format --check .
npx --yes markdownlint-cli2 "docs/**/*.md" "README.md"
```

The markdown lint takes explicit paths on purpose: an unanchored `**/*.md` also lints
`.venv`, which is not this repository's prose and fails on third-party files.

Conventions: async throughout, tabs, Pydantic v2 with `extra="forbid"`, UUID7 string
ids, immutable value objects in `views.py`, orchestration in `service.py`.

`.markdownlint.json` disables **MD010 inside code blocks** deliberately. `ruff format`
also formats fenced Python in Markdown and, honouring `indent-style = "tab"`, rewrites
it to tabs; leaving MD010 on makes the two tools rewrite each other's bytes forever.
Python fences belong to `ruff`, prose whitespace to `markdownlint`.

Decisions are recorded in [`docs/adr`](docs/adr/).
