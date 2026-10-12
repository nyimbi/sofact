# Harness argv: specs vs the binaries on this machine

Date 2026-10-12. Every claim below is backed by a command whose output is quoted, or is
marked **unverified** where no non-paying invocation could decide it. Nothing in
`src/sofact/harness.py` was changed; the last section is a proposal only.

Installed on this machine:

| harness | path | version |
|---|---|---|
| `pi` | `/opt/homebrew/bin/pi` | `1.1.0` |
| `dsh` | `/opt/homebrew/bin/dsh` → `@deepseek-ai/dsh` (npm) | `0.1.0-rc.6` |
| `claude` | `/Users/nyimbiodero/.local/bin/claude` | `2.1.296 (Claude Code)` |

Note: `dsh` is **also** a zsh alias, `npx @deepseek-ai/dsh web --port 8181`. `command -v dsh`
returns the alias text first; `type -a dsh` shows both. The binary is the second entry. A
dispatch through a shell would hit the alias and boot the web profile, so a dispatch must
invoke the binary by path, not by name.

---

## pi — version 1.1.0

`pi --version` → `1.1.0`. `PI_SPEC` was measured against **0.85.1**; the argv below is
re-verified against 1.1.0.

| spec field | value | verdict | evidence |
|---|---|---|---|
| `argv` flags | `--mode`, `--print`/`-p`, `--offline`, `--no-context-files`, `--no-extensions`, `--model`, `--session-dir`, `--session-id`, `--tools`, `--` | **confirmed** | `pi --help` lists each: `--mode <mode>`, `--print, -p`, `--offline`, `--no-context-files, -nc`, `--no-extensions, -ne`, `--model <pattern>`, `--session-dir <dir>`, `--session-id <id>`, `--tools, -t <tools>`, `--` ("End option parsing") |
| `session_glob` `**/*{session_id}*.jsonl` | plain JSONL, name embeds id | **confirmed** | real record `/Users/nyimbiodero/.pi/agent/sessions/--Users-nyimbiodero-src-pjs--/2026-10-09T06-01-42-430Z_01a11f40-cb1d-73b5-8246-1bb82a87e6f7.jsonl`; header `id` = `01a11f40-…` |
| `session_is_zstd` `False` | | **confirmed** | file is plain text JSONL |
| `usage_path` `("message","usage","output")` | | **confirmed** | real record: `message.usage` keys = `input, output, cacheRead, cacheWrite, reasoning, totalTokens, cost` |
| `completion_event` `None` | no completion signal | **confirmed** | observed record types: `session, model_change, thinking_level_change, message` — no completion event |
| `model_error_pattern` `"not found. Use --list-models"` | | **unverified** | would need a run against a bad tag; no paying call made |
| `session_id_style` `token` | | **confirmed** | `--session-id <id>` takes a project id, not a UUID; a real record id is a UUID-shaped value pi generated itself, not a constraint on the caller |

pi is otherwise **not refuted**: the argv and record shape still hold at 1.1.0.

---

## dsh — version 0.1.0-rc.6

`dsh --version` → `0.1.0-rc.6`. This is **newer** than the 0.1.5rc1 the spec's blocker was
recorded against. `DSH_SPEC.argv` is refuted on three independent counts.

| spec field | value | verdict | evidence |
|---|---|---|---|
| `argv` `--profile sdk` | | **refuted** | `DSH_HOME=/tmp/x dsh --profile sdk --help` → exit 1, `Error: dsh: profile "sdk" does not exist; create it with 'dsh plugin --profile sdk add <package>'`. The shipped profiles are `headless` and `web`. |
| `argv` `--print` | | **refuted** | `dsh --profile headless --print hi` → exit 1, `error: unknown option '--print'`. `headless` has no `--print`; running with no task → exit 1, `error: a task is required, for example: dsh --profile headless "run the tests"`. |
| `argv` `--model {model}` | | **refuted** | `dsh --profile headless --model m` → exit 1, `error: unknown option '--model m'`. |
| `argv` `--cwd {workspace}` | | **refuted** | `dsh --profile headless --cwd /tmp` → exit 1, `error: unknown option '--cwd /tmp'`. The headless runner sets `meta: { cwd: process.cwd() }`, so cwd is the **process cwd**, which SoFact already sets via `create_subprocess_exec(cwd=self.workspace)`. |
| session id flag | (spec passes none) | **confirmed** | `headless` generates its own id: `SessionId(\`session-${randomUUID()}\`)` (`dsh-headless/lib/index.js:71`). SoFact cannot pin it, so `session_glob` cannot key on a SoFact-chosen id — see below. |
| `env` `DSH_HOME={session_dir}` | explicit home | **confirmed** | with `DSH_HOME` unset the SDK still resolves `~/.dsh`; the headless runner materializes a `headless` profile into `$DSH_HOME/profiles` on first use. Keeping it explicit still isolates the operator's real `~/.dsh`. |
| `session_glob` `**/session-{session_id}/session.v3.jsonl.zstd` | | **refuted** | real files are `session.jsonl.zstd` (no `v3`). Layout (`dsh-session-persistence-jsonl/README.md`): `<root>/--<normalized-cwd>--/<encoded-id>/session.jsonl.zstd`. `--profile headless` always stamps `session-` (line 71); **`web` does not** — a real `web` session dir is `--Users-nyimbiodero-src-pjs-eel--/2507cf75-…/`. And `{session_id}` cannot match, because the id is generated inside the runner. |
| `session_is_zstd` `True` | | **confirmed** | `zstd -dc <file>` decompresses cleanly |
| `completion_event` `turn/end` | | **confirmed** | real record (14 372 rows) contains `turn/end` |
| `completion_reason_path` `("data","reason","kind")`, value `completed` | | **confirmed** | `{"type":"turn/end","seq":25531,"time":…,"data":{"turn":1,"reason":{"kind":"completed"}}}` |
| `usage_path` `("data","usage","outputTokens")` | | **confirmed** | `assistant/message` rows carry `data.usage` with `inputTokens`/`outputTokens` (26 each in the sampled record) |
| blocker "`--profile headless` is broken in 0.1.5rc1 (missing `@deepseek-ai/dsh-session-title-llm`)" | | **does not reproduce** | on rc.6, `dsh --profile headless --help` exits 0 and prints help; `--dump-default-config` composes `@deepseek-ai/dsh-session-title-llm` successfully. No missing-module error was seen in any invocation. |

What a working headless argv looks like: `dsh --profile headless "<task>"` — flags come
**before** the task, the task is the positional argument, cwd is inherited from the process.
The completion/usage record fields are real, but the dispatch argv has still never been
witnessed end to end, because a real run needs a model call and that was out of scope here.

---

## claude — version 2.1.296

`claude --version` → `2.1.296 (Claude Code)`. This matches the version `CLAUDE_SPEC` records
as measured, so the spec is re-confirmed rather than merely consistent.

| spec field | value | verdict | evidence |
|---|---|---|---|
| `argv` flags | `--print`, `--model`, `--output-format`, `--session-id`, `--tools`, `--` | **confirmed** | `claude --help`: `-p, --print`, `--model <model>`, `--output-format <format>`, `--session-id <uuid>` ("Use a specific session ID"), `--tools <tools...>` |
| `--` terminator | | **confirmed** | `--tools <tools...>` is variadic (help shows `"Bash,Edit,Read"`), so the terminator is still needed; the spec comment's rationale stands |
| `session_id_style` `uuid` | | **confirmed** | `--session-id <uuid>` — the help names the type |
| `env` `CLAUDE_CONFIG_DIR={session_dir}` | | **confirmed** | real store is `<CLAUDE_CONFIG_DIR>/projects/<cwd-slug>/<session-id>.jsonl` |
| `session_glob` `**/projects/*/{session_id}.jsonl` | | **confirmed** | e.g. `~/.claude/projects/-Users-nyimbiodero-src-pjs-fab-ext/1c4a27a0-….jsonl` |
| `completion_event` `assistant` | | **confirmed** | real record has `assistant` rows |
| `completion_reason_path` `("message","stop_reason")`, value `end_turn` | | **confirmed** | real record `stop_reason` values: `{'tool_use': 501, 'end_turn': 10}` |
| `usage_path` `("message","usage","output_tokens")` | | **confirmed** | `message.usage` keys include `output_tokens` (underscore) |
| `tool_names` capitalisation | `read`→`Read` … | **confirmed** | `--tools` help names tools `"Bash,Edit,Read"`; the translation is required |

claude is **not refuted** on any field.

---

## What this changes in `src/sofact/harness.py`

Proposal only. `pi` and `claude` need no edit; `DSH_SPEC` needs five.

1. `DSH_SPEC.argv` — old
   `("dsh","--profile","sdk","--print","--model","{model}","--cwd","{workspace}")` →
   new `("dsh","--profile","headless")`. The task is appended raw as the final argument, so
   no `{model}`/`{cwd}`/`{session_id}` slot is needed in the argv. (Drop the model flag: the
   model comes from the profile's `agent-default-model` config; pin it via a `--patch` overlay
   or a profile config if a dispatch must fix it.)
2. `DSH_SPEC.session_glob` — old `"**/session-{session_id}/session.v3.jsonl.zstd"` → the
   `{session_id}` and `v3` are both wrong. A glob cannot name the id the runner generates;
   the best a spec can do is the newest `session.jsonl.zstd` under the project dir. This is a
   real limitation, not a spelling fix — consider whether `HarnessSpec` needs a "no id in the
   glob" mode, or whether the adapter should read the id out of the record header (the header
   row carries `"id":"session-<uuid>"`).
3. `DSH_SPEC.session_is_zstd` — `True`, **unchanged** (confirmed).
4. `DSH_SPEC.completion_event` / `completion_reason_path` / `completion_reason_value` /
   `usage_path` — **unchanged** (all four confirmed against a real record).
5. `DSH_SPEC.env` `DSH_HOME={session_dir}` — **unchanged**, and still worth keeping explicit.
6. `DSH_SPEC.notes` — the blocker sentence is stale: `--profile headless` works on 0.1.0-rc.6,
   and the real defect is that the argv named a profile (`sdk`) that does not exist and flags
   (`--print`, `--model`, `--cwd`) that `headless` does not accept. Replace "THE ARGV IS
   UNVERIFIED … 0.1.5rc1 …" with the rc.6 finding, and keep the telemetry-egress caveat
   (`--profile headless` still reaches a model endpoint; not an egress boundary).

Also worth a note: `dsh` is shadowed by a zsh alias on this machine, so any dispatch that
resolves the name through a shell boots the `web` profile. The adapter invokes the binary
directly via `create_subprocess_exec`, so it is unaffected — but a `which`-based probe and a
human copy-pasting the command are not.

## Method notes

- Only `--help`/`--version`/`--dump-default-config` and one aborted `--print` were run. No
  coding session was started; no model call was made; nothing was written outside `/tmp`.
- Session records were read from the operator's own stores (`~/.pi`, `~/.dsh/sessions`,
  `~/.claude/projects`) and decompressed with `zstd -dc` into `/tmp`; analysis scripts read
  them with `python3 -I` from a separate directory.
