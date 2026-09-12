# 0021. Research is dispatched, not performed

## Status

Accepted.

## Context

P1 — *deep research to flesh out the idea and understand the state of the art* — was the
one phase of the pipeline that existed only as a spec verb. The interrogation (P0), the
contract (P4), the dispatch (P5) and the check (P6) all ran live against real harnesses;
`sofact research` did not exist, so the research that the project itself had accumulated
([S19]–[S25]) had been performed *by hand*, outside the platform, with no mechanism.

Meanwhile the operator installed a research engine into the harness: `@forecastx/
deep-research`, a `pi` extension whose tools spawn a recursive headless `pi` that runs a
web-search loop and saves a report plus a machine-readable `meta.json` ([S25], measured).
Two measured facts shaped the decision. First, the extension **auto-loads into every
`pi` session**, so SoFact's build producers were silently carrying it — and any other
installed extension — which is the composition FR-154 freezes. Second, on a local model
the extension's own 240 s loop ceiling binds before its advertised five-search floor:
a truncated loop leaves a short report with an empty `sources` array, which is exactly
the shape NFR-024 forbids rounding into a conclusion.

## Decision

**SoFact performs no research. It authors the research goal deterministically, dispatches
it to a harness whose research spec is a deliberate composition, and records the
artefacts the run leaves — never a conclusion about them.**

1. **The goal is written with zero model involvement** (`research_goal`), the same
   discipline as a build step (FR-136's compiler): it names the tool, the exact query —
   the current goal's statement unless one is passed — and the two files the workspace
   must hold. SoFact writes the prompt; the model does the research.
2. **The research spec is data, and its composition is deliberate** (`PI_RESEARCH_SPEC`):
   the build spec's argv with `--offline` and `--no-extensions` removed and
   `RESEARCH_MODEL` pinned to the operator's model. The build spec keeps its freeze;
   this is the one place an extension is allowed, because the extension *is* the
   capability the phase delegates to. The default research harness is
   `pi-research` if the configured table contains it; otherwise the verb refuses and
   names the table, because silently building a research adapter would re-inline the
   table into code (FR-161).
3. **The artefact protocol is two workspace files**: `research-report.md` (the report
   text, verbatim) and `research-meta.json` (the loop's own counts and sources). SoFact
   reads what those hold — report size, `stats.searches`, the cited URLs — and records
   them as facts. It does **not** read the extension's `~/.forecastx-reports` store
   directly; the producer copies the meta into the workspace, which keeps SoFact's
   knowledge of the run inside the workspace it already observes (FR-149).
4. **Sources are recorded, not verified.** URLs from the report text and the meta's
   `sources` array are folded, deduplicated, in order of first appearance, into the
   record. A report with no sources is recorded as exactly that — `source_urls == ()`
   with a warning line — which reads "unmeasured", never "none found" (NFR-024). The
   report prose itself is advisory input (ADR-0008), the same standing a completion
   claim has: recorded, and never consulted as a verdict.
5. **The exit rule mirrors dispatch**: the run was responsible for leaving a report, so
   a session that did not complete, or completed without one, exits non-zero; a report
   with no sources is a measured fact printed in warning colour, not a failure.
6. **No probe is required** before a research dispatch, unlike a build dispatch
   (FR-148). A research run's capability claims are the artefacts themselves, which the
   run measures directly; a session that cannot run is one failed artefact rather than
   an assumed capability.

## Alternatives refused

* **SoFact performs research itself** — its own web searches, its own synthesis loop.
  Refused: it is a research engine, which is §8's boundary for harness code generally,
  and the harness already ships one whose loop is tested by its authors.
* **Read `~/.forecastx-reports/<id>/meta.json` directly.** Refused: it couples SoFact to
  the extension's private storage layout and reaches outside the observed workspace.
  The producer copies the meta in; SoFact reads the workspace only.
* **Treat a report as verified research.** Refused: a report is the producer's word about
  the world, which is the same epistemic shape as a completion declaration (FR-138) —
  recorded as a signal, never consulted as a verdict.
* **Require a probe before research.** Refused: the probe gates a *build's* assumptions
  about unattended capability; a research run that cannot run is one failed artefact,
  already recorded honestly by the outcome.
* **Let build sessions keep the extension loaded** (no `--no-extensions`). Refused after
  measurement: an unextended argv hands a build producer whatever the operator has
  installed, and a producer able to spawn recursive research mid-build is a composition
  FR-154 exists to freeze.
* **Invent a report-quality floor** ("a report under N characters is failed"). Refused:
  the numbers are recorded and printed; a floor would convert a measured fact into an
  invented threshold, and the honest default is the operator's judgement in front of
  the numbers.

## Consequences

* P1 exists as executable code: `sofact research [query]`, one ledger kind
  (`research.run`), one state field (`research`), one derived spec in the built-in table.
* The extension's own timeout is the binding constraint on local models ([S25]);
  `sofact research --timeout` bounds only the outer session. A deployment that wants
  longer loops sets the extension's environment or accepts truncation, which the
  record shows honestly rather than rounding away.
* Report language follows the extension's prompt (Chinese), not the operator's language.
  A deployment that wants a different language writes its own research spec with its own
  prompt-bearing extension — the table is data.
* Per-source verification (fetch each URL, check it resolves, write a precis) remains
  future work, and the record's shape admits it: each source is already an addressable
  row.

## Evidence

* `src/sofact/harness.py` — `PI_RESEARCH_SPEC` (derived from `PI_SPEC`), `invoke`.
* `src/sofact/service.py` — `research`, `research_goal`, `extract_source_urls`,
  `RESEARCH_TIMEOUT_SECONDS`, `DEFAULT_RESEARCH_HARNESS`.
* `src/sofact/cli.py` — the `research` verb and its exit rules.
* `tests/ci/test_harness.py` — the research spec is a deliberate variant of the build
  spec (the two web-facing flags removed, `RESEARCH_MODEL` pinned).
* `tests/ci/test_service.py::TestTheResearchRun` — 6 tests: sources recorded, the
  truncated loop as a fact, a failed session, query defaulting, table refusal, no-goal
  refusal.
* `tests/ci/test_cli.py::TestTheResearchVerb` — 3 tests, including the truncated loop's
  warning line.
* [S25] — the extension measured: source read in full, one live run executed.

## References

* ADR-0004 — delegate the coding loop to an external harness (the same boundary, held
  for research).
* ADR-0012 — the harness table is data (the research spec is one row, not a subclass).
* ADR-0016 / ADR-0018 — measure the configuration, not the harness's name.
* [S25], FR-149, FR-154, FR-161, FR-167, NFR-024.
