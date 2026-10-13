# 0035 — A source ledger is a graph of addressable claims, not a reading list

- **Status:** Accepted
- **Date:** 2026-10-12
- **Related:** FR-068, FR-069, FR-070, FR-071, FR-073, FR-074, FR-075, FR-062, NFR-024;
  [ADR-0007](0007-the-elicitation-gate-is-deterministic.md),
  [ADR-0021](0021-research-is-dispatched-not-performed.md),
  [ADR-0034](0034-a-rollback-is-a-reading-rule-and-the-log-keeps-what-it-hides.md)

## Context

The capability map's §5 build order named this as item 6, the last of six, and its §2.4
row recorded it as "covered, weaker — SoFact has no *addressing* mechanism for its own
context; FR-070 is the stronger version and is unbuilt". The roadmap audit agreed:
"One report path plus a URL tuple; sources are not addressable and claims do not point
at them."

Two artefacts already existed to build from. The spec's §5.1 names the second one
explicitly: the hand-built ledger in `docs/sources/` "is the **reference
implementation** of this phase, and its structure is the specification for the
automation." So the design question was not *what should a ledger contain* — 28
`docs/sources/sNN-slug.md` files with fixed YAML front-matter and four fixed body
sections answer that by having been used — but **where the automation ends**.

**FR-070's requirement is a relation, not a field.** "Claims and sources must be
separately addressable, so that invalidating a source invalidates the claims resting on
it." That sentence names an edge. A ledger whose claims are strings inside a source
entry cannot have that edge, and one whose claims are a flat list beside the sources
has it only if something derives the dependants — so the edge has to be a type, and the
derivation has to be a method, or the requirement is prose again.

**The producer's artefacts are untrusted, and the failure mode here is silence.** This
module reads files a model wrote. A parser that skips the lines it cannot parse reports
a clean ledger over the documents it dropped, and a clean ledger is indistinguishable
from a good one — the shape of every silent gate failure recorded in this project's
lessons. So the parser had to fail closed: unreadable line, refusal; missing critique
section, refusal; unparseable date, refusal rather than a dropped field.

**Two spellings of every list already exist in the reference ledger.** `tags:
[harness, research]` and a `key:` line followed by two-space-indented `- item` lines both
occur across the 28 documents. A parser for one of them is a parser that silently drops the other,
which is the same failure as above with a longer fuse.

**One thing the spec's structure invites, and it is a trap.** The obvious use for a
parsed spec is to derive `supports` — the front-matter field `docs/sources/README.md`
reserves as "spec claim IDs this source backs, once the spec exists" — by walking the
spec for `[S01]`-style citations. It was measured before being built: of the 21 sources
the spec cites, **5 cite only in prose outside any requirement** ([S18], [S19], [S20],
[S23], [S24]). A markdown walk attributes those to nothing and reports a completeness
the artefact does not have.

## Decision

**The ledger is a set of addressable sources, a set of addressable claims, and the
edges between them — recorded in the log, versioned, and read from the producer's own
artefacts rather than inferred from its prose.**

1. **`Source` and `Claim` are separate types, and the edge is `Claim.source_ids`.**
   FR-070 asks for two addressable things, so there are two addressable things.
   `SourceLedger.resting_on(source_id)` derives the claims a source's invalidation
   takes with it; the relation is a set, not a partition, because a claim citing two
   sources rests on both.
2. **A dangling edge is refused at construction.** A claim citing a source the ledger
   does not hold, or a `superseded_by` naming an entry that is not there, is a
   `ValueError` — because an edge to nothing cannot be invalidated with its source,
   which is the one operation the edge exists for.
3. **The parser fails closed.** A front-matter line that is neither `key: value` nor a
   list item raises; a block scalar (`|`, `>`) raises rather than being read as the
   literal pipe character; a document with no `## Precis` or no `## Concerns /
   information quality` raises; a non-ISO date raises rather than being dropped.
   `docs/sources/README.md`'s own words are the reason the critique is required: the
   value of an entry is the judgement about the source, and a document without one is a
   link.
4. **Both list spellings parse.** Inline `[a, b]` and block `- item` lines, because both
   are in the reference ledger and a parser for one silently loses the other.
5. **Sections are matched exactly, then by prefix.** `## Key claims (observed, not
   reported)` is a claims section with a caveat, and the reference ledger qualifies its
   headings by how the claims were obtained. Exact-only matching would find the
   qualified ones missing.
6. **The disconfirming count is reported and is deliberately not a check (FR-071).**
   The count is printed by `sofact sources`. It is not one of the gate checks, because
   a check that failed at zero would pay a producer for inventing a disconfirming claim
   — a gate that rewards fabrication is worse than no gate. FR-071 asks for
   *detectability*, and a reported count is detectable. The three checks that do exist
   are provenance, positioning-as-grounds, and expiry.
7. **`SourcePosture` is enforced by the type, not by a warning (FR-074).** A source
   cannot be `positioning` and `content-verified` at once: reading vendor content
   carefully does not make it evidence, and recording it as both is how a marketing
   claim acquires a citation. `SourceLedger.unbacked_decisions` is the set that may be
   recorded and may not decide — an opinion, or a claim whose every source is
   positioning.
8. **An opinion may rest on nothing and may not cite a source.** `Claim.opinion` is
   FR-069's label, and it is not a weaker claim but a claim with no source that is
   *allowed to exist and not allowed to support a decision*. The type refuses a claim
   that is both labelled an opinion and cites sources, because a record claiming both
   is unreadable.
9. **A contradiction is recorded and never resolved by the machine (FR-073).**
   `Contradiction.resolution` stays `None` when the operator has not ruled, and the CLI
   prints `UNRESOLVED`. The spec is explicit that the disagreement "is where the
   operator's decision actually is", so a machine picking a winner would answer the one
   question the phase exists to hand over.
10. **Expiry is as-of a date, and the check takes one (FR-075).** `Source.expires` and
    `Claim.expires`; `SourceLedger.expired(as_of)` and `nothing-has-expired` are
    evaluated against a day, so the same ledger can be current and then not — which is
    what a staleness check means, and what a boolean cannot express.
11. **The ledger is versioned by the state it is read under.** `version` counts
    `ProjectState.ledgers`, and a re-stated ledger *appends* a row rather than replacing
    one — the same supersede-don't-edit shape ADR-0007 settled for a re-answered
    elicitation dimension. Counting through the fold rather than through the raw log is
    deliberate: a rollback hides a ledger row (ADR-0034), the project's reading then
    holds one fewer ledger, and numbering the next one as though the hidden one were
    still current would describe a ledger the project does not have.
12. **The goal text asks for the artefacts, and the reading is transcription.**
    `research_goal` names `research-sources/`, the front-matter fields, the two required
    body sections, and `research-claims.json`. Asking for a ledger is what makes reading
    one transcription rather than inference from prose — and inference from prose is
    what decision 13 refuses.
13. **`supports` is not derived from the spec, and the measurement is why.** Five of the
    21 sources the spec cites appear only in prose outside any requirement, so a
    citation walk would attribute them to nothing while reporting success. The edge
    FR-070 names runs source-to-claim inside the ledger, and that is what is derived.
14. **`ResearchRecord.source_urls` stays.** It is a measurement of a *dispatch* — which
    URLs the report and the meta cited — and it is not the ledger. Keeping both means a
    run whose ledger failed to parse still has its URLs recorded, and the two are not
    made to agree by construction, which is honest: they are different observations.
15. **No ledger and an empty ledger are different findings.** A run whose workspace has
    no `research-sources/` directory is refused with a message saying so, never recorded
    as an empty ledger (NFR-024). The one thing a reader must not conclude from a
    recorded empty ledger is that the producer looked and found nothing.

## Alternatives refused

- **A claim list inside each source entry.** Refused in the Context: FR-070's
  requirement is that invalidating a source invalidates the claims resting on it, and
  claims nested in a source cannot outlive it — invalidating the source deletes them,
  which is not the same operation and loses the record of what was believed.
- **Derive `supports` by walking the spec for citations.** Refused in decision 13, on a
  measurement rather than a principle: 5 of 21 sources cite only in prose, so the
  derivation would be wrong and would report itself complete.
- **Read the ledger out of the research report's prose.** Refused: a markdown reader
  over free-form model output is a parser whose failure mode is a plausible-looking
  wrong ledger. The artefact protocol is what makes the run observable (ADR-0021), and
  a structured ledger is the same discipline applied to P1's output.
- **A `verified: bool` instead of `VerificationStatus`.** Refused: the five-status
  legend exists because *content read*, *URL resolved*, and *seen but not captured* are
  different provenance claims, and a boolean collapses them — letting a source that
  merely resolved be cited as one that was read.
- **Fail the disconfirming count as a gate check.** Refused in decision 6: it pays for
  fabrication. The count is a measurement, and the operator reads it.
- **Resolve a contradiction by preferring the more-verified source.** Refused in
  decision 9, and it is tempting precisely because it is mechanical. The spec puts the
  decision with the operator; a ranking would silently answer it, and the disagreement
  would then never reach them.
- **Keep the ledger in a file beside the log.** Refused for the reason ADR-0034 gives
  about snapshots: state assembled by anything other than the log is not the record of
  what happened. The ledger is a row, the fold replays it, and `ProjectState.ledger`
  derives the operative one.
- **Skip the front-matter lines the parser cannot read.** Refused in decision 3: this
  is the subset-predicate-fails-toward-clean failure that has bitten this project
  repeatedly, and here it would report a complete ledger over dropped documents.

## Consequences

- **The capability map's build order is complete.** All six items are built; §2.4's
  "Context library" row moves from "Covered, weaker" to "Covered, stronger", and the
  vendor's directory of documents is now the weaker of the two.
- **The roadmap audit's FR-069/070/071/073/074/075 rows move together**, which is
  expected: they are one artefact's requirements, and building the artefact is what
  closes them. FR-068 stays open — a per-clause classification is a different artefact
  (a verdict on each intent clause) and the ledger holds claims *about* the premise, not
  attributed to clauses.
- **`ProjectState` gains a field and a property, and `test_state.py`'s census enforces
  the field.** The field count moves 21 → 22 and the `KIND_TO_FIELD` mapping stays total
  in both directions, so a new `LedgerKind` without a state field fails a test.
- **A producer can now fail P1 in three checkable ways** — an uncited claim, a claim
  resting only on positioning, an expired entry — where before the phase's output was
  measured only by the report's size and URL count.
- **`research_goal`'s text is longer, and that is a cost.** The prompt is authored with
  zero model involvement (ADR-0021), so every field the ledger needs is a sentence the
  producer must be given. The alternative — inferring the fields from a prose report —
  is the refused alternative above.
- **The parser is stricter than the reference ledger's loosest documents.** Where a
  hand-written entry would have been read by a person and understood, this refuses.
  That is the intended direction: the reference ledger's own "Verification queue"
  section exists because hand-written entries accumulate debt a reader has to notice,
  and a refusal is noticed for them.

## Evidence

- `src/sofact/views.py` — `VerificationStatus`, `SourcePosture`, `ClaimKind`, `Claim`,
- `Contradiction`, `Source`, `SourceLedger` (with `resting_on`, `unbacked_decisions`,
  `disconfirming`, `expired`), `LedgerKind.SOURCE_LEDGER_RECORDED`, `ProjectState.ledgers`
  and the derived `ProjectState.ledger`.
- `src/sofact/research.py` — the front-matter reader, `parse_source_document`,
  `parse_claim_document`, `parse_ledger`, `ledger_checks`.
- `src/sofact/service.py` — `research_goal`'s ledger protocol, `ledger_from`,
  `record_ledger`, `current_ledger`, `ledger_gate`.
- `src/sofact/cli.py` — `sofact sources`, with `--from-run`.
- `tests/ci/test_research.py` — 36 tests over the parser and the checks, including both
  list spellings, the qualified heading, every refusal, and the dangling edge.
- `tests/ci/test_service.py::TestTheSourceLedger` — 11 tests: the artefact read into a
  ledger and replayed by the fold, the edge navigable, positioning recorded and refused
  as grounds, a contradiction left unresolved, expiry read, the versioned second ledger,
  and the goal text asking for the artefacts.
- `tests/ci/test_cli.py::TestTheSourcesVerb` — 5 tests: reachability, the disconfirming
  count printed, the failed check exiting non-zero, the recorded ledger read back
  without the workspace, and the two refusals.
- **Canaries**, each with the target string asserted present before the patch and the
  file restored from a `/tmp` backup rather than from git:
  - `_scalar`'s block-scalar guard replaced with `if False:` —
    `test_a_block_scalar_is_refused_rather_than_misread` failed.
  - `Source`'s posture/verification refusal replaced with `if False and ...` —
    `test_a_positioning_source_cannot_be_content_verified` failed.
  - `SourceLedger._every_link_resolves`'s missing-source set replaced with `[]` —
    `test_a_claim_citing_a_source_the_ledger_lacks_is_refused` failed.
  - `FactoryService.ledger_from`'s directory check replaced with `if False:` —
    both the service test and the CLI test failed, at both layers.
  - `SourceLedger.unbacked_decisions`'s positioning branch replaced with `if False:` —
    `test_a_positioning_only_claim_fails_the_evidence_check` and the service test failed.
- `tests/ci` at this commit: **804 passed, 0 failed**. `pyright`: 0 errors. `ruff check`
  and `ruff format --check`: clean.

## References

- FR-070 (versioned source ledger), FR-069 (provenance), FR-071 (disconfirming
  evidence), FR-073 (contradiction detection), FR-074 (evidence versus positioning),
  FR-075 (self-staleness), FR-062 (a durable artefact per phase), NFR-024 (record what
  was observed).
- `docs/sources/README.md` — the reference implementation this transcribes, and the
  verification legend `VerificationStatus` promotes to a type.
- [ADR-0007](0007-the-elicitation-gate-is-deterministic.md) — the supersede-don't-edit
  shape the versioned ledger follows.
- [ADR-0021](0021-research-is-dispatched-not-performed.md) — research is dispatched, so
  its output is an artefact protocol rather than a model's prose.
- [ADR-0034](0034-a-rollback-is-a-reading-rule-and-the-log-keeps-what-it-hides.md) — why
  the version counts through the fold.
- `docs/research/orchestrator-capabilities/README.md` §2.4 and §5 item 6 — the rows this
  closes.
