# The driver set: opencode, omp, omc — measured against the binaries

Date 2026-10-12. Every claim is backed by a command whose output is quoted, or marked
**unverified**. No model call completed: this machine's OpenRouter balance is exhausted
(402 on every provider), so each run below fails *after* the harness accepted the argv.
That is the useful part — argv acceptance, session-id handling and record retrieval are
all witnessed; only generation is not.

Installed:

| harness | path | version |
|---|---|---|
| `pi` | `/opt/homebrew/bin/pi` | 1.1.0 |
| `omp` | `~/.local/bin/omp`, `/opt/homebrew/bin/omp` | 18.8.6 |
| `omc` | `/opt/homebrew/bin/omc` | 4.10.2 |
| `opencode` | `/opt/homebrew/bin/opencode` | 2.0.25 |
| `claude` | `~/.local/bin/claude` | 2.1.296 |

## opencode — ADR-0023's three refusals no longer hold

ADR-0023 dropped `opencode` for one reason with three parts. Re-measured at v2.0.25, all
three have moved:

1. **"`session_glob` is a filesystem glob and a row is not a path."** Still true — the
   record is in `~/.local/share/opencode/opencode.db`, a **68 GB** SQLite file. But
   `opencode session export <id>` now exists and prints the whole session as JSON:
   ```console
   $ opencode session export ses_f07f78a71ffe22oD4YTvhzC1w0 | head -c 200
   {
     "info": {
       "id": "ses_f07f78a71ffe22oD4YTvhzC1w0",
       ...
       "tokens": { "input": 3223920, "output": 283814, "reasoning": 47658, ... },
       "outcome": "succeeded",
   ```
   This is the "shell out to a command" seam ADR-0023 priced as *real machinery* and
   declined "as a first move". It is now one command that returns JSON — no SQL, no
   schema to track, which was the objection the ADR actually made.

2. **"Give it a private store via an env var, as `claude` gets `CLAUDE_CONFIG_DIR` —
   refused for lack of evidence."** The variable exists: **`OPENCODE_DB`**, and with
   `--standalone` it works.
   ```console
   $ OPENCODE_DB=/tmp/oc_priv2/priv.db OPENCODE_TEST_HOME=/tmp/oc_priv2/home \
       opencode run --standalone -s ses_sofactpriv000000000000002 --format json "…"
   $ ls /tmp/oc_priv2/
   priv.db  priv.db-shm  priv.db-wal
   ```
   Without `--standalone` the run goes to the background service and `OPENCODE_DB` is
   ignored — the store stayed empty. So the pair is the isolation unit, not the variable
   alone.

3. **"Keep it in the table with an unprobed argv — refused."** Moot: the argv probes
   clean, and it is the *only* candidate that accepts a SoFact-minted session id (below).

### What the spec would say

| field | value | evidence |
|---|---|---|
| `argv` | `("opencode","run","--standalone","-s","{session_id}","--format","json","--model","{model}")` | `run --help` lists `-s/--session`, `--format json`, `--standalone`, `-m/--model` |
| `session_id_style` | **`token`, but prefixed `ses`** | `-s plain-token-id` → `Expected a string starting with "ses"`; `-s ses_abc` → accepted; `-s ses_01234567890123456789012345` → accepted and streamed events |
| record access | **a command, not a glob** | `session export <id>` → JSON |
| `completion_reason_path` | `("info","outcome")`, value `succeeded` | export info carries `"outcome":"succeeded"` on a real session and `"failed"` on the quota-refused one |
| `usage_path` | `("info","tokens","output")` | export info `tokens` = `{input, output, reasoning, cache}` |
| private store | `OPENCODE_DB` + `--standalone` | measured above |
| model pin | `-m/--model` `provider/model#variant` | `run --help` |

**The blocker is the seam, not opencode.** `HarnessSpec.session_glob` is a glob and
`HarnessAdapter.session_files` globs a directory. opencode needs `(argv → JSON)` behind
the same interface. That is a real change to the one seam FR-058 exists to keep singular,
and it is the decision to make — not a spelling fix.

**Not witnessed:** a *successful* generation, so `completion_reason_value="succeeded"` is
inferred from a real completed session's export, not from a run this adapter made. The
`--format json` event stream's own terminal event was never reached.

## omp (oh-my-pi) — pi-shaped record, no id to pin

omp 18.8.6 is pi's superset by the same author: `-p/--print`, `--model`, `--mode
text|json|rpc|rpc-ui`, `--session-dir`, `--tools`, `--no-extensions`, `--max-time`,
`--cwd`.

Its record is **exactly pi's shape** — measured over a real record:

```
types: {'title': 1, 'session': 1, 'model_change': 1, 'thinking_level_change': 1, 'message': 2, 'custom': 1}
usage keys: ['cacheRead', 'cacheWrite', 'cost', 'input', 'output', 'totalTokens']
```

So `usage_path=("message","usage","output")`, `session_is_zstd=False`, and **no completion
event** — the same asymmetry `pi` has. `session_glob="**/*{session_id}*.jsonl"` would hold
*if* an id could be pinned, and it cannot:

- there is **no `--session-id`**: `omp --session-id test-id-123` → `Error: unknown flag:
  --session-id`. The record name is `<iso-timestamp>_<uuid>.jsonl` with a uuid omp mints.
- `--resume <id>` refuses an id it has not already stored (`Session "…" not found`), so it
  cannot be used to pre-seed one.
- `--session-dir <dir>` **is** honoured and does isolate the store — measured, one run
  wrote exactly one `.jsonl` into a fresh directory. A private directory therefore makes
  "the newest record" unambiguous even without a pinnable id.

That last point is the same shape as dsh's: **a harness that mints its own id needs a
"newest record in a private directory" lookup, not an id-keyed glob.** Two candidates now
need that, so it is a seam question rather than an omp question.

**Not witnessed:** any successful generation; `--model` resolution and the
`model_error_pattern` are unverified.

## omc (oh-my-claude) — not a producer

omc 4.10.2 is an **orchestrator that launches Claude Code**, not a harness with its own
record. `omc launch` starts Claude Code under tmux; `omc ask <claude|codex|gemini>` runs
an advisor prompt and writes an "ask artifact"; the rest is team/telemetry/HUD machinery.

It has no argv that makes it the coding agent and no session record of its own — the
record belongs to the Claude Code it launched. Wiring it as a `HarnessSpec` would mean
reading Claude Code's record through omc's wrapper, which is `CLAUDE_SPEC` with extra
steps. **Recommendation: not a driver.** If omc's orchestration is wanted, it is a layer
*above* SoFact's dispatch (or a `claude` spec variant), not a row in the harness table.

## The decision this leaves — now made

Two things were separable, and ADR-0023 conflated them:

1. **The record-source seam.** Whether `HarnessSpec` may name a *command* that yields a
   record, not only a glob over a directory. Three candidates want it: opencode
   (command), omp (private dir + newest), dsh (private dir + newest). The refusal in
   ADR-0023 was about cost; the cost has since dropped to one command per harness, and the
   set of harnesses that need it has grown from one to three.

2. **The producer set.** `opencode` is now the strongest candidate of the three named
   here: it is the only one that accepts a caller-minted id, so a dispatch addresses its
   own record instead of guessing, and it exposes `outcome` as a structured completion
   signal. `omp` is a pi variant and adds nothing pi does not already give.

**Both are decided in [ADR-0028](../../adr/0028-a-record-source-may-be-a-command-whose-stdout-is-the-record.md),
which supersedes ADR-0023 decision 1.** `HarnessSpec` now carries `session_command` (an
argv whose stdout is the record) and `record_format` (`jsonl` or `json`), the command's
stdout is materialised into a file so the seam stays singular, and `opencode` is wired as
a fourth spec. Two measured facts the spec depends on are recorded there: a failed session
still exports and exits 0, so completion is read from the document; and `opencode run` has
no flag that narrows the tool set, so the sandbox probe cannot be built for it.

`omp` is **not** wired. Its record is pi's shape and it adds nothing pi does not give, so
the private-directory-plus-newest lookup it would need has no second customer yet.

## Sources

- `docs/adr/0023-a-record-is-addressed-by-a-path.md` — the record this re-measures
- `docs/research/harness-argv/README.md` — the pi/dsh/claude measurements
- Commands above, run 2026-10-12 against the versions in the table
