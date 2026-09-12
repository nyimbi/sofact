# Architecture Decision Records

Decisions are recorded here once they are *made*, in the form they were made. Each
record states what was decided, what forced the decision, and what it now costs. A
record is not a plan and is not edited to match later reality: when a decision
changes, a new record supersedes the old one and both stay.

Format is Nygard-style — **Status**, **Context**, **Decision**, **Consequences** —
with an **Evidence** section where the decision rests on something measured rather
than argued. Numbering is sequential and never reused.

## Index

| ADR | Title | Status |
| ----- | ------- | -------- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-model-access-is-one-openai-compatible-interface.md) | Model access is one OpenAI-compatible interface | Accepted |
| [0003](0003-the-ledger-is-append-only-and-hash-chained.md) | The ledger is append-only and hash-chained | Accepted |
| [0004](0004-delegate-the-coding-loop-to-an-external-harness.md) | Delegate the coding loop to an external harness | Accepted |
| [0005](0005-no-container-runtime.md) | No container runtime | Accepted |
| [0006](0006-the-verifier-cannot-reach-the-executor.md) | The verifier cannot reach the executor | Accepted |
| [0007](0007-the-elicitation-gate-is-deterministic.md) | The elicitation gate is deterministic | Accepted |
| [0008](0008-the-model-is-advisory-only.md) | The model is advisory only | Accepted |
| [0009](0009-no-oracle-no-autonomy.md) | No oracle, no autonomy; termination is not verification | Accepted |
| [0010](0010-delegation-to-a-third-party-harness-is-an-accepted-disadvantage.md) | Delegation to a third-party harness is an accepted structural disadvantage | Accepted |
| [0011](0011-the-factory-refuses-to-claim-maintainability.md) | The factory refuses to claim maintainability | Accepted |
| [0012](0012-the-harness-table-is-data-not-code.md) | The harness adapter table is data, not code | Accepted |
| [0013](0013-a-version-claim-is-checked-against-the-floor.md) | A version claim is checked against the minimum supported version | Accepted |
| [0014](0014-markdown-fence-ownership.md) | Markdown code fences belong to ruff, prose whitespace to markdownlint | Accepted |
| [0015](0015-a-verdict-describes-one-run.md) | A verdict describes one run, and a declaration triggers the check | Accepted |

## Mapping to the specification's open decisions

The product specification uses `D<n>` identifiers for open questions. Where a
`D` was resolved by a decision recorded here, the mapping is:

| Spec id | Resolution | ADR |
| --------- | ----------- | ----- |
| D9 — container runtime for isolation | No containers | [0005](0005-no-container-runtime.md) |
| D11 — which goal-mode harness to target | Delegate to an external harness, `dsh` first | [0004](0004-delegate-the-coding-loop-to-an-external-harness.md) |
| D15 — how much plugin surface to write in v1 | Withdrawn from v1 scope | [0004](0004-delegate-the-coding-loop-to-an-external-harness.md) |
| D16 — is SoFact a `dsh` plugin | No; independent control plane | [0004](0004-delegate-the-coding-loop-to-an-external-harness.md) |
| D17 — is commercialisation a goal | No; capability is the goal | [0008](0008-the-model-is-advisory-only.md) |
| D18 — adopt a change-cost instrument, or declare evolvability out of scope | **Open** — but the *shape* of either answer is now fixed: the debt is named and defaulted to total, so the choice is whether Mode M can exceed L1, not whether the gap is reported | [0011](0011-the-factory-refuses-to-claim-maintainability.md) |

`FR-xxx` identifiers refer to the specification's functional requirements. `[Snn]`
refers to an entry in the [source ledger](../sources/README.md).

## Records that are not resolutions of an open decision

Not every decision resolves a `D`. Four records here answer questions the specification
never had to ask — three because they are about this repository's own tooling rather than
about the factory's behaviour, and one because the rule it replaces was never written
down at all and so had no `D` to resolve:

| ADR | What it settles |
| ----- | ----------------- |
| [0012](0012-the-harness-table-is-data-not-code.md) | That FR-161 is enforced at all — a table read from an untrusted file is validated by name rather than defaulted |
| [0013](0013-a-version-claim-is-checked-against-the-floor.md) | Which interpreter's version each checker validates against, and that no tool gets two configuration files |
| [0014](0014-markdown-fence-ownership.md) | Which tool owns which bytes in Markdown, after two of them spent several turns undoing each other |
| [0015](0015-a-verdict-describes-one-run.md) | When a verdict is invalidated: FR-006 carried forward, and the trigger FR-138 was missing. The superseded rule existed only in `verification.py`, so no `D` ever pointed at it |
