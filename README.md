# SoFact

**Describe a product. Get a verified one — or a precise account of why you did not.**

SoFact is a software factory for people who want to *imagine* a platform and then
actually have it built. It interrogates a vague goal until it is falsifiable, compiles
it into a contract whose every clause names the oracle that would check it, hands the
building to a coding agent, and then verifies the result **independently of whoever
produced it**.

SoFact contains no coding loop. It is the control plane around one: the part that
decides what "done" means, and the part that refuses to take a producer's word for it.

```sh
uv tool install git+https://github.com/nyimbi/sofact.git
sofact
```

That is the whole entry point. It asks you a question and keeps asking until your
answer can be tested.

---

## The problem

Coding agents are good at writing code and bad at telling you whether it works. Ask one
to build a feature and you get a diff plus a confident summary; the summary is the part
that is not evidence. Two failure modes follow, and they are the ones this project
exists to remove:

- **You cannot tell "done" from "looks done."** A session that ran out of context, hit a
  refusal, or silently lost its tools still exits `0` and still says it finished. Measured
  on `claude` 2026-10-12: run with `--tools read,write`, it accepts the flag, reports
  `terminal_reason: completed`, and gives the producer **no tools at all** — the names are
  capitalised. Nothing in the exit code says so.
- **The spec drifts from the build.** By the time there is code, the intent lives in your
  head, the requirements live in a ticket, and the tests were written by the same process
  that wrote the code. Nothing connects them.

SoFact's answer is a single rule, enforced by the type system rather than by discipline:
**no oracle, no autonomy** ([ADR-0009](docs/adr/0009-no-oracle-no-autonomy.md)). A clause
without a machine-checkable acceptance criterion cannot exist in a contract, so it cannot
be built, and it cannot be claimed. What you get at the end is not a green checkmark; it is
a report naming every clause that was verified, every clause that was not, and exactly what
would change each one.

## See it work

Elicitation is a deterministic questionnaire. The model advises; it does not decide
([ADR-0008](docs/adr/0008-the-model-is-advisory-only.md)). Answers are checked against
floors — a length, and for the oracle dimension a requirement that you name a real checking
mechanism — so a non-answer is refused rather than recorded. Here the goal is stated, three
dimensions resolve, and then a plausible-sounding answer is rejected because it describes an
outcome and names no way to check it:

```text
$ sofact
What do you want to build?: Every reminder appears in the dashboard within 60 seconds
of being scheduled.

[1/6] outcome
  What observable state change tells you this worked?
  ↳ Without an observable outcome there is nothing to test, so there can be no oracle
    and no autonomy above L0.
  :   ✓ resolved

[4/6] oracle
  How would a machine check the outcome, without asking you?
  ↳ This is the load-bearing question. An answer must name a real checking mechanism —
    a test, a property, a query, a digest — because a description of confidence is not
    an oracle.
  :   ✗ does not name a checking mechanism; expected something like one of: test,
      assert, property, invariant, exit code, hash, … (a statement of confidence is
      not an oracle)

  advisor: What machine-readable signal—DOM selector, API response field, or log
  event—proves the reminder is displayed, and where is the scheduling timestamp
  recorded for comparison?
  (answer again to replace it)
```

The advisor line is the model's and varies run to run; the `✗` line above it is the floor,
and it does not. Answer the oracle question properly and the interrogation closes. A
contract then assigns one oracle to every stem, and reports the ceiling those oracles can
support:

```text
$ sofact contract --command 'pytest -q'
contract 01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f6 v1
  6 clause(s)
  weakest oracle rank 3 → ceiling L3
  ground-truth debt 0%
```

Run the oracles and the verdict is a fact about a run, not a claim about the code. Here
the workspace held no test suite, so `pytest -q` exited 5 — and the verdict says so, per
clause:

```text
$ sofact run --workspace ./ws && sofact verify
verdict VIOLATED
  contract 01a136fc-097a-7aa6-aeb7-6e4f5e5ce2f6 @ e976faedf2d4
  ceiling L3 from weakest oracle rank 3
  ✗ The dashboard shows the reminder row within 60 seconds of it being scheduled
      exit code 5, expected 0
  ✗ The end user reads the dashboard
      exit code 5, expected 0
  ✗ a scheduler calls the store API to enqueue a reminder
      exit code 5, expected 0

Not verified. Only an all-satisfied report grants autonomy — an unrun oracle is
not a passing one.
```

Omit `--command` and the factory does not guess an oracle. It reports **100%
ground-truth debt** and caps the ceiling, because a clause nothing can check is a clause
nothing has checked.

## Install

Requires **Python ≥ 3.12** and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/nyimbi/sofact.git   # install the `sofact` command
```

Or from a checkout, for development:

```sh
git clone https://github.com/nyimbi/sofact.git
cd sofact
uv sync
uv run sofact
```

State lives in `./.sofact`, or `$SOFACT_HOME`. Nothing is written outside it, no
containers are used ([ADR-0005](docs/adr/0005-no-container-runtime.md)), and the only
network egress is the model you configure.

**The model is optional.** SoFact talks to any OpenAI-compatible endpoint and defaults to
Ollama on `http://localhost:11434/v1`. If nothing is listening, it degrades to a plain
deterministic questionnaire — the floors, the gates and the verdicts are not model-driven,
so the product works without one. Point it elsewhere with `SOFACT_MODEL` / `SOFACT_BASE_URL`.

## The pipeline

Ten phases, four human gates. A gate is placed only where **no oracle can decide** — the
machine checks run and are reported, and then a person approves, naming themselves:

```text
P0 Elicit ──▶ P1 Research ──▶ ┌─ GATE: specification ─┐
                              │      P2 Specify       │
                              └───────────┬───────────┘
                                          ▼
                          ┌─ GATE: decomposition ─┐
                          │      P3 Decompose     │
                          └──────────┬────────────┘
                                     ▼
                    P4 Contract ──▶ P5 Build ──▶ P6 Verify
                                     │
                                     ▼
                          ┌─ GATE: deploy ─┐
                          │   P8 Deliver   │◀── P7 Integrate
                          └───────┬────────┘
                                  ▼
                            P9 Evolve
```

| Phase | What it produces |
| --- | --- |
| **P0 Elicit** | Intent clauses, from a Socratic dialogue with a deterministic resolution gate. |
| **P1 Research** | Cited findings that validate, invalidate or deepen the premise — before you build. |
| **P2 Specify** | A specification: one requirement per clause, each carrying that clause's oracle. **Gate.** |
| **P3 Decompose** | Modules, interfaces and a dependency DAG, derived from the contract with no model call. **Gate.** |
| **P4 Contract** | A per-clause oracle suite with its strength measured. **Gate** (`contract_sample`, sampled). |
| **P5 Build** | Goal sessions dispatched to a harness, one branch per module. |
| **P6 Verify** | Oracle results, out of process. The verdict takes no completion claim. |
| **P7 Integrate** | Build order, import discipline, interface and model conformance, system criteria. |
| **P8 Deliver** | The delivery report: artefacts, traceability chain, unverified clauses, handover. **Gate.** |
| **P9 Evolve** | *Not built.* The escape measurement it consumes exists; the scorecard and the lane adjustment do not. |

Every phase's state, and the argument behind it, is in [**`docs/phases.md`**](docs/phases.md).
That file is the long form of this table, moved there from it rather than rewritten, so the
detail has one home. A test asserts the two agree on which phases exist and that every gate
the code defines is named on this page — a reference describing a phase the code lacks, or a
front page silently dropping one, fails rather than reads.

Two commands make the machine's own position legible:

```sh
sofact phase    # where the pipeline is; exits non-zero while a gate is open
sofact status   # the goal, the phase, readiness per dimension, ledger health
```

A gate cannot be passed by anything except a person naming themselves, and an approval
cannot waive a failed machine check:

```sh
sofact gate --present P2            # the machine half: run the checks, report them
sofact gate --approve P2 --by you   # the human half: recorded with who and when
```

## How it works

**The ledger is the system.** Every fact is an append-only, hash-chained event. All state
is a pure fold over that log, so any state can be re-derived from scratch and any tampering
is detectable ([ADR-0003](docs/adr/0003-the-ledger-is-append-only-and-hash-chained.md)):

```sh
sofact ledger          # the append-only event log
sofact verify-ledger   # recompute the hash chain; exit 1 if it does not verify
```

**A rollback is a reading rule, not a deletion.** `sofact rollback --to 12 --reason "…"`
reads the project as of an earlier entry and records why. The log grows, the chain still
verifies, and the work the rollback hides is still there to be read
([ADR-0034](docs/adr/0034-a-rollback-is-a-reading-rule-and-the-log-keeps-what-it-hides.md)).

**The report states what it cannot claim.** FR-118's statements are required *fields*, not
paragraphs, because a report is read under time pressure and prose is where a qualification
goes missing. "Requirements were verified, not value" is a constant on the type, so no code
path can produce a report that omits it or claims otherwise. Two of the four delivery
artefacts are **decisions rather than omissions** — a deployable artifact needs a packaging
decision the factory refuses to assume — and the check is scoped to the two it actually owes,
because a gate that can never pass is one an operator learns to bypass.

**The escape rate is the one number no producer authored.** `sofact escape` records a
revert, hot-fix or incident against a deployed change; `sofact escapes` folds the ledger
into a per-lane rate. The producer writes oracles and modules — it does not write deploys or
reverts, which is what makes this the factory's only ground truth. A lane over its declared
budget has its ceiling reduced automatically until the rate returns
([ADR-0054](docs/adr/0054-the-escape-rate-is-the-one-number-no-producer-authored.md)).
`sofact scope` declares what the deployment is aiming at, so the rate has something to be
aimed at: the target is **deployment-scoped, not product-scoped**, and there is deliberately
no default
([ADR-0057](docs/adr/0057-the-autonomy-target-is-a-deployment-scoped-type.md)).

## Harness

SoFact has no coding loop ([ADR-0004](docs/adr/0004-delegate-the-coding-loop-to-an-external-harness.md)).
`dispatch` hands each plan step to a harness as an **out-of-process** session, then reads
the harness's *own* session record — exit code, tokens, continuations, whether goal mode was
really entered — instead of asking it. `pi`, `dsh`, `claude` and `opencode` ship as specs.

```sh
sofact probe                        # attempt a harness; record what was observed
sofact dispatch --all               # run the plan; stops at the first refuted wave
sofact repair                       # hand each refuted clause back to the producer
sofact attempts                     # what the repair loop cost: attempts, tokens, wall clock
sofact composition                  # the frozen plugin set, and whether FR-154's freeze holds
sofact composition --verify a=<sha> # re-check the pins against what is installed now
sofact scope                        # the autonomy target this deployment declared (FR-157)
sofact integrity                    # re-verify the pinned hashes
sofact integrate                    # P7
sofact deliver --root ./delivery    # P8: the report, its chain, its handover
sofact deploy                       # present FR-119's gate; nothing deploys
sofact deploy --approve <report-id> --by me   # pass it, as a person, on the record
```

`attempts` folds the repair rows against the sessions they produced, and it **says when it
could not measure everything**: a harness that reports no usage yields a *floor*, not a
total, and the count of sessions that reported nothing travels with the number. Three zeros
over a run that never repaired anything is not a cheap build, and the verb exits non-zero
rather than print it
([ADR-0055](docs/adr/0055-attempt-telemetry-is-a-join-and-the-unmeasured-token-count-is-part-of-it.md)).

`composition` prints the plugin set a build runs with and **exits non-zero while any part
of FR-154–156 is open**. The freeze has two independent halves — the harness's own argv
refusing to auto-load installed plugins, or the plugins enumerated and pinned by digest —
and both are *derived* from the harness spec rather than declared, so a spec cannot claim a
freeze its command line does not enforce. `pi` runs frozen; `dsh`, whose plugin set is
mutable at runtime by the agent, does not, and the verb says so instead of printing a clean
table. §8.7's worked audit of the ecosystem is the corpus: eight measured rows, four
distinct verdicts, one plugin admitted
([ADR-0056](docs/adr/0056-the-freeze-is-derived-from-the-argv-and-the-deletion-test-admits.md)).

`scope` reports what this deployment is aiming at, and **exits non-zero when none was
declared** — there is no default, because FR-157 makes the target deployment-scoped and a
product-supplied one would be the θ gate imposed as the very default it removes. `escapes`
prints the same comparison against the last delivery's own number. The target is a *type*
rather than a number because the two ways a declared target can be one this build cannot
honour carry different remedies: a personal deployment may not reach L4, and a third-party
one may not either while the gate that admits it is unbuilt. Absence is a state, not a
missed target: a deployment that declared none is told no comparison was made, not that it
fell short
([ADR-0057](docs/adr/0057-the-autonomy-target-is-a-deployment-scoped-type.md)).

`probe` is not optional: dispatching against an assumed capability is exactly what the spec
forbids, so `dispatch` refuses until a profile exists. Which harness is a **row of data, not
a class** — point SoFact at a new one without touching `src/`:

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

```sh
SOFACT_HARNESS_SPECS=./my-harness.json sofact probe
```

Unknown fields, wrong types, missing required fields and bare strings where a sequence
belongs are refused **by name**. A misspelled key that silently defaulted would produce a
plausible, wrong number rather than an error. This example is executed by the test suite
through the real loader, so it cannot rot.

A spec's own reliability is recorded with it, and not every shipped row is equally
trustworthy. `pi`, `dsh` and `claude` were witnessed end to end; **`opencode`'s spec has
not been** — every run on the machine where it was written failed after the argv was
accepted, because the configured account was out of credit. What *is* measured there is
narrower and stated as such: the session-id format, and that `session export` prints one
JSON document. It ships because the adapter is data and the seam was cheap, not because it
was seen to build anything.

The probe's rows are **measured, not assumed**, and the answers are not always flattering.
Measured live, neither `pi` nor `claude` confines its child: told to escape a workspace with
a tool allowlist in place, each wrote one directory above it. An allowlist filters which
tools exist, not where they reach — so `sandboxable` reads `absent` for both, and a worktree
is recorded as containment rather than confinement. A harness whose help text suggests
otherwise is exactly the case the probe exists to catch.

## Model

Default: `deepseek-v4.1-flash:cloud` via Ollama's OpenAI-compatible endpoint — a 1M-token
context model served through Ollama's cloud, not locally. Override with `SOFACT_MODEL` /
`SOFACT_BASE_URL`. See
[ADR-0002](docs/adr/0002-model-access-is-one-openai-compatible-interface.md) for what that
costs in hermeticity.

For a real coding session the model must be one the **harness** can resolve, not merely one
Ollama serves: `pi` validates `--model` against its own registry and refuses a tag it does
not list. Run `sofact probe` before dispatching, and read its answer — a refused model is
recorded as a measured capability, in the harness's own words, rather than blamed on the
producer ([ADR-0018](docs/adr/0018-a-refused-model-is-attributed.md)).

## What this does not do

A README that only lists capabilities is a README you have to verify yourself. These are
structural, decided deliberately, and recorded in the ADRs:

- **It does not write code.** There is no edit-run-revise loop. Building is delegated to a
  harness, and that delegation is an accepted structural disadvantage
  ([ADR-0010](docs/adr/0010-delegation-to-a-third-party-harness-is-an-accepted-disadvantage.md)).
- **It uses no containers.** Confinement is the harness's tool allowlist, and the probe
  measures that this is weaker than it sounds. A filesystem boundary is not built.
- **It does not claim maintainability.** The factory has no oracle for change cost, so it
  says so rather than implying a green suite means maintainable code
  ([ADR-0011](docs/adr/0011-the-factory-refuses-to-claim-maintainability.md)).
- **It does not certify value.** Requirements are verified; the value hypothesis is
  declared and untested, and the report says exactly that in a constant.
- **It does not deploy.** §1.5 makes deploy permanently manual. What `deploy` records is the
  evidence of a human decision.
- **It produces new repositories, not patches.** Mode M (maintenance of an existing repo) is
  specified and retained, but Mode G (genesis) is what is built.

The spec's own status section lists every requirement against its implementation, with the
gaps named rather than omitted:
[`docs/research/roadmap-gap`](docs/research/roadmap-gap/README.md).

## Develop

```sh
uv run pytest -vxs tests/ci          # 1396 tests
uv run pyright
uv run ruff format --check .
npx --yes markdownlint-cli2 "docs/**/*.md" "README.md"
```

The paths are explicit on purpose: an unanchored `**/*.md` also lints `.venv`, which is not
this repository's prose and fails on third-party licences.

Two config files, because markdownlint splits its settings across two levels and silently
ignores a key filed at the wrong one:

- **`.markdownlint-cli2.jsonc`** holds the cli2-level keys — which files to lint and what to
  skip. `docs/sources/archive/` is skipped because it holds verbatim copies of other
  projects' READMEs, and this repo does not get to restyle text it is quoting. The `globs`
  list is what makes a bare `markdownlint-cli2` (no arguments, as an editor hook runs it)
  lint the repository rather than discover `ignores` and stop.
- **`.markdownlint.json`** holds the rules. **MD010 inside code blocks** is off deliberately:
  `ruff format` also formats fenced Python in Markdown and rewrites it to tabs, so leaving
  MD010 on makes the two tools rewrite each other's bytes forever
  ([ADR-0014](docs/adr/0014-markdown-fence-ownership.md)).

Conventions: async throughout, tabs, Pydantic v2 with `extra="forbid"`, UUID7 string ids,
immutable value objects in `views.py`, orchestration in `service.py`.

## Documentation

| | |
| --- | --- |
| [**`docs/spec/product-spec.md`**](docs/spec/product-spec.md) | The specification: every requirement, the pipeline, the risks. |
| [**`docs/adr/`**](docs/adr/) | 54 architecture decisions — what was decided, what forced it, what it costs. |
| [**`docs/phases.md`**](docs/phases.md) | Each phase's state in full. |
| [**`docs/research/roadmap-gap`**](docs/research/roadmap-gap/README.md) | The spec against the implementation, requirement by requirement. |
| [**`docs/sources/`**](docs/sources/README.md) | The source ledger: what the design rests on, and how strongly. |
| [**`docs/research/findings.md`**](docs/research/findings.md) | What the research concluded, and where it is weak. |

## License

MIT — see [LICENSE](LICENSE).
