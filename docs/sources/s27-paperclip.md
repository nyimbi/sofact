---
id: S27
slug: paperclip
title: "Paperclip — orchestration for teams of AI agents"
type: product-doc
verification: url-verified (raw README fetched and read in full this session)
confidence: medium
accessed: 2026-10-12
retrieved_via: "raw.githubusercontent.com/paperclipai/paperclip/master/README.md; GitHub repository search"
archive: archive/s27-paperclip-README.md
url: https://github.com/paperclipai/paperclip
relates_to: [S22, S26]
---

**Why this entry exists.** Paperclip is the largest project in this space by
attention — **100.7k stars**, measured on the repository page this session — and it
sits at the same layer as OpenRig: it orchestrates other people's agents rather than
being one. It is the strongest available evidence about what the *market* considers
the hard part, and its README names one mechanism SoFact does not have and needs.

## Precis

"The open-source app everyone uses to manage agents at work"; "If OpenClaw is an
employee, Paperclip is the company." A Node.js server plus React UI that orchestrates
a team of agents to run a business: "a full control plane, not a wrapper." Twelve named
subsystems (Identity & Access, Org Chart & Agents, Work & Task System, Heartbeat
Execution, Workspaces & Runtime, Governance & Approvals, Budget & Cost Control,
Routines & Schedules, Plugins, Secrets & Storage, Activity & Events, Company
Portability). Agents are Claude Code, Codex, Cursor, Gemini CLI, OpenClaw and others;
"We don't tell you how to build agents. We tell you how to run a company made of them."
Embedded PostgreSQL, S3-compatible storage, MIT.

## Key claims

1. **"Atomic task checkout. A single assignee and execution locks prevent competing
   runs from claiming the same task."** Listed first among the things that make
   Paperclip "special," and restated in the subsystem table as "atomic checkout with
   execution locks."
2. **"Governance with rollback. Approval gates are enforced, config changes are
   revisioned, and bad changes can be rolled back safely."**
3. **"Goal-aware execution. Linked tasks and projects carry goal ancestry so agents see
   the 'why,' not just a title."**
4. **Verification is human review over produced artefacts**: "verify from diffs,
   screenshots & tests"; "review and approval stages"; "Configured task reviews govern
   completion."
5. **Durable activity log**: "Mutating actions, heartbeat state changes, cost events,
   approvals, comments, and work products are recorded as durable activity so operators
   can audit what happened and why."
6. **Multi-organization isolation**: "Company-scoped access checks keep each
   organization's work, agents, and activity separate within one deployment."
7. Anonymous telemetry is **on by default** with documented opt-outs; opt-in
   OpenTelemetry tracing.

## Why it matters for SoFact

- **Claim 1 is a defect report against SoFact, and it was reproduced here.** Paperclip
  leads with atomic checkout *because* concurrent claims on one work item are the
  failure mode of any scheduler with a shared mutable store. SoFact's scheduler has
  `dispatch_plan(concurrent=True)`, which `asyncio.gather`s every step in a wave, and
  the ledger is the shared store. `Ledger.append` reads the cached tail, chains onto
  it, and writes with no lock and no re-read. Two appends that read the same tail both
  claim the same `index` and the same `prev_hash`. **Measured on this tree, two
  processes synchronized to both read an empty log before either appended:** both wrote
  `index 0, prev 000000000000`, and `verify_chain()` then returned
  `ok=False, broken_at=1, reason='index 0 at position 1'`. The consequence is worse than
  a lost row: FR-003 makes a broken chain `LedgerCorruptError` and `require_intact` runs
  before every fold, so the project **cannot be read at all** until a human repairs the
  log by hand. Paperclip names the mechanism that prevents this; SoFact has none. This
  is the highest-value item in this entry.
- **Claim 2 is the mirror of SoFact's revision story, and Paperclip's is weaker in one
  way and stronger in another.** Paperclip revisions *config* and rolls it back.
  SoFact revisions the *decomposition* (FR-094) and refuses to approve a superseded
  proposal, which is the same idea aimed at architecture. SoFact's advantage is that
  every revision is a ledger row with a hash chain; Paperclip's is that rollback is a
  first-class operator action rather than a re-proposal.
- **Claim 4 marks the boundary precisely.** Paperclip's verification is a human reading
  diffs, screenshots and tests, with an approval stage governing completion. There is no
  oracle, no clause that cannot exist without one, and no separation between the party
  that produces the evidence and the party that judges it. This is the same boundary S22
  drew around the `dsh` ecosystem and S26 around OpenRig. Three independent projects at
  this layer, three times the same absence — which is either SoFact's differentiation or
  evidence that the market does not want it.
- **Claim 3 corroborates FR-127.** SoFact makes the intent traceability graph
  first-class for escape attribution. Paperclip carries "goal ancestry" through tasks so
  agents see the why. Same mechanism, different purpose: Paperclip uses it for agent
  context, SoFact for attributing a failure back to the clause that was misunderstood.
- **Claim 6 is a scaling question SoFact has not asked.** SoFact is one goal per state
  directory, with `current_goal()` returning the most recent. Paperclip runs many
  organizations in one deployment behind access checks. That is not a gap to close now —
  but "one operator, many goals, one log" has no answer in this tree.

## Concerns / information quality

- A **product README**, read for positioning. Nothing executed, no version installed.
  The 100.7k figure is a repository star count read this session, not an adoption
  measure.
- **The star count is an outlier that deserves suspicion.** 100.7k stars for a project
  at this stage is far above every comparable source in this ledger (S22's ecosystem
  census, S23's 30k for a hard fork of `pi`). Popularity at this magnitude is frequently
  bought, botted, or a consequence of a launch campaign, and this ledger has no
  independent adoption evidence. **Do not cite the star count as evidence of quality or
  of market validation.** It is cited here only as a reason the project is worth reading.
- Every architectural claim (PostgreSQL, execution locks, plugin isolation) is the
  vendor's description of its own system. The atomic-checkout claim is credible
  precisely because it is the *only* one this session could test against an independent
  implementation — and SoFact fails that test.
- Telemetry on by default is a difference in posture from SoFact, which has none.
