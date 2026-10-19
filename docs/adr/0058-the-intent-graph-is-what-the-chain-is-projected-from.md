# 0058 — The intent graph is what the chain is projected from, and an attribution says which kind it is

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** FR-127, FR-117, FR-021–023, FR-076, FR-088, FR-089, FR-091, FR-131,
  FR-139, §2.3, §2.4, §9.6, §7;
  [ADR-0044](0044-the-factory-writes-the-two-artefacts-it-owes-and-the-delivery-is-a-fixed-point.md),
  [ADR-0054](0054-the-escape-rate-is-the-one-number-no-producer-authored.md),
  [ADR-0057](0057-the-autonomy-target-is-a-deployment-scoped-type.md)

## Context

FR-127's sentence carries its own argument: the intent traceability graph "must be a
**first-class component, not a derived report**. It is the only mechanism by which an
escape (§9.6) can be attributed back to the intent clause that was misunderstood — and per
§2.3 that attribution is the single most valuable learning signal the product produces."

§2.3 says why. Ground-truth debt is the defining problem of Mode G: "if the criteria are
wrong, every check passes and the platform is wrong — and it is wrong in a way that looks
maximally verified." The only closure §2.3 admits is the operator reading the
specification at P2. An escape is the one event that tells you a clause *was* wrong, after
the fact — and the roadmap recorded the row as **Partly** because nothing could connect
one to the other: "Traceability is a gate *check* over the clause→module relation
(`decomposition.py:438`), not a graph with escape attribution."

Two facts about the existing code decided the design.

**The three relations are not a chain.** `TraceLink` prints clause → requirement → module
→ step, and `delivery.chain` walked them in that order. In the log they are not
consecutive: P2's `Requirement.clause_ids` and P3's `Module.clause_ids` are *independent*
declarations off the same clause, so requirement and module are sibling branches, and only
the module reaches a step (P5). A linear rendering is what a report must produce; it is
not what the log holds. Holding the relations as directed edges is what makes the backward
walk — module to the clauses that cite it — a hop rather than a search over everything.

**And there were two implementations of one walk.** `delivery.chain` built the links, and
the graph would have built them again. Two structures derived independently from one set
of inputs agree until someone edits one, and the disagreement is invisible precisely
because each is internally consistent.

## Decision

**The graph is the structure; the chain is a projection of it.** `delivery.chain` now
delegates to `IntentGraph.project()`. A hop the graph does not hold cannot appear in a
report, and a hop it does hold cannot go missing from one, because there is one structure.
This is what makes FR-127's "first-class component, not a derived report" structural
rather than rhetorical: a graph that only rendered a picture of the same walk would have
satisfied the word and not the requirement.

**The graph is addressable on its own** — `FactoryService.intent_graph(contract_id)` and a
`sofact intent` verb — because a component reachable only through a delivery report is a
derived report arriving by another route. Reading it directly is what an operator does
before there is anything to deliver, and it is where a clause the decomposition dropped is
visible: `IntentGraph.gaps` reports it, and a gap is a *worse* finding than an escape,
since nothing was built for that clause and no escape can ever be attributed to it.

**Attribution starts from the lane, and the module is what narrows it.** An escape names a
lane (`ModuleClass`), and a lane is a class — G4 may be four modules — so a lane-wide
escape attributes to every clause those modules cite. That is a candidate set, not the
"intent clause that was misunderstood". So `EscapeEvent` gained an optional `module`, and
`record_escape` refuses a name the deployment did not build or one outside the lane it was
filed against: a module that did not break would point the attribution at the wrong clause,
which is worse than no attribution because it reads as a finding. `EscapeAttribution.narrowed`
carries the distinction onto the type, because a reader who could not tell an answer from a
candidate set would read the set as a finding — which is how an attribution becomes a false
accusation.

**The graph states what it cannot do.** Every edge is a declaration a phase made, so it can
say "the module built for this clause is the one that got reverted" and cannot say the
clause was ambiguous, that the operator meant something else, or that the oracle was too
weak. §2.3 makes the operator the only ground truth; the component's job is to put the
right clause in front of them. The type's docstring, the report's section and the CLI all
say this in those terms.

## Consequences

- **FR-117's chain and FR-127's graph cannot drift**, because there is one walk. The
  delegation is asserted directly (`test_the_report_chain_is_the_graph_projection`).
- **The report carries the graph it was rendered from**, not one rebuilt at read time. A
  graph rebuilt now would attribute an escape to whatever the decomposition says *today*,
  and after a repair that is a different graph than the change was built against.
- **An escape recorded after a render appears in the next one.** A report describes the log
  at the moment it is rendered. That is not a gap in the rate — which is a fold over the
  whole ledger — but it is a fact a reader of a stored report needs, and FR-117 versions
  reports precisely so an approver's copy stays as it was. Asserted rather than assumed.
- **`DELIVERY.md` gained an "Escape attribution" section**, and the heading constant is
  load-bearing: a section renamed or dropped fails the render rather than silently leaving
  the document.
- **The graph is published** as a read-only machine operation (`intent`), because a
  component no surface can reach is not first-class.
- **A clause the graph cannot walk is now visible before a delivery.** It was previously
  reported only as a broken link inside a rendered report, which is later and quieter.

## Evidence

- `tests/ci/test_intent.py` — 28 tests, new. The structure (four vertex kinds, three hop
  kinds, the requirement and module branching off the clause rather than chaining, the
  class only on a module), the projection read against the *declarations* rather than
  against another projection, the attribution in both states, the two refusals, the
  contract scoping, the vacuous pass, the gap report, the contract hash, the report's
  carriage of the graph, and the two surfaces.
- **Five canaries, each watched failing, each reverted from a file backup** (never `git
  checkout`): the module narrowing removed (1 test failed), the requirement hop dropped
  from the projection (1), the module refusal disabled (2), the vacuous pass removed (1),
  the gap report emptied (1).
- **Two of those canaries passed on their first run, and both were defects in the tests
  rather than in the code.** The narrowing canary passed because the helper picked the
  first chain link — a G5 module in a lane of one — where narrowing is a no-op, and because
  the assertion was `<=`, which equality satisfies. The projection canary passed because
  the test compared `graph.project()` against `delivery.chain(...)`, which by then delegated
  to `project()`: a tautology, and a test whose two sides are one function proves only that
  the function is deterministic. Both were fixed and both canaries then fired. A canary that
  passes is a claim about the instrument, and the instrument is what to suspect first.
- One real defect was found by the projection test while it was still a comparison:
  `build_graph` minted requirement vertices only from a `Specification`, so a caller
  holding the clause→requirement map alone silently lost that hop. Fixed at the source —
  a requirement the specification did not supply still gets a vertex.
- `uv run pyright` — 0 errors, 0 warnings. `uv run ruff check` and `ruff format --check` clean.
- Full suite **1424 passed, 0 failed**, read from the log's own summary line (the one failure
  on the first run was the README's own suite-count gate, which had drifted 1396 to 1424 —
  the gate working, not the code).
