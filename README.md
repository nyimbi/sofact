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
| **P3/P5 — Decompose & dispatch** | **Partial.** `plan` compiles the contract into ordered goal sessions with pinned hashes (FR-136/139); `probe` measures a harness instead of trusting it (FR-148); `dispatch` runs the plan in waves, one out-of-process session per step, and stops at the first **refuted** wave (FR-142/FR-163). Single-module only — worktree isolation (FR-141) is not implemented. |
| **P1 — Research** | Not implemented. |

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

A clause without an oracle cannot exist, which is the type-level enforcement of the
spec's first rule: **no oracle, no autonomy** (FR-001).

## Harness

SoFact contains no coding loop. `dispatch` hands each plan step to a harness as an
**out-of-process** session, then reads the harness's *own* session record — exit code,
tokens, continuations, whether goal mode was really entered — instead of asking it.
Which harness is a **row of data, not a class**:

```sh
uv run sofact contract --command 'pytest -q'   # every stem needs an oracle
uv run sofact plan                             # contract → ordered goal sessions
uv run sofact probe                            # attempt a harness; record observations
uv run sofact dispatch --all                   # run the plan; stops at the first refuted wave
uv run sofact integrity                        # re-verify the pinned hashes (FR-139)
uv run sofact precision                        # did the claims survive verification?
```

`probe` is not optional: dispatching against an assumed capability is exactly what
FR-148 forbids, so `dispatch` refuses until a profile exists.

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

`pi` and `dsh` ship as specs. To point SoFact at another harness without editing
`src/`, write a JSON table and set `SOFACT_HARNESS_SPECS`:

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

## Model

Default: `deepseek-v4.1-flash:cloud` via Ollama's OpenAI-compatible endpoint — a
1M-token context model served through Ollama's cloud, not locally. Override with
`SOFACT_MODEL` / `SOFACT_BASE_URL`. See
[ADR-0002](docs/adr/0002-model-access-is-one-openai-compatible-interface.md) for what that costs in hermeticity.

For a real coding session the model must be one the **harness** can resolve, not merely one
Ollama serves: `pi` validates `--model` against its own registry and refuses a local tag it
does not list (`Error: Model "…" not found`, exit 1, no session record). `qwen3.6:35b-mlx`
is what the end-to-end run used — `SOFACT_MODEL=qwen3.6:35b-mlx sofact probe` before
dispatching, since a bad model is a child-process failure the probe catches.

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
