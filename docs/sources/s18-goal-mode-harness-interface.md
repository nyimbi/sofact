---
id: S18
slug: goal-mode-harness-interface
title: "Goal-mode coding harness interface (pi-goal 0.1.7 / pi-goal-writer)"
type: primary / local-inspection
evidence: files read on this machine
path: /Users/nyimbiodero/.pi/agent/npm/node_modules/pi-goal
retrieved: 2026-09-12
verification: content-verified
confidence: high
tags: [harness, goal-mode, long-horizon, interface, autonomy]
---

## Precis

This is the **first `content-verified` entry in the ledger**, and the only non-web
one: `pi-goal` 0.1.7 was read directly from the local installation, not summarised
from a report. It was captured because SoFact's build phase now delegates to
goal-mode harnesses (§8), and the interface it must adapt to should be observed
rather than invented.

`pi-goal` adds a `/goal` command plus goal tools to `pi`. An active goal keeps the
same agent running turns in the same session context until the model marks the goal
complete, the user pauses/clears it, or a token budget is exhausted.

## Key claims (observed, not reported)

### Interface

- `/goal [--tokens 50k] <objective>`; lifecycle: `status`, `pause`, `resume`,
  `clear`, `statusbar on|off`.
- Tools: `create_goal` (only when explicitly requested), `get_goal`,
  `update_goal`.
- `get_goal` and `update_goal` are exposed **only while a goal is `active`**;
  paused/cleared/complete/budget-limited goals hide them.

### The capability asymmetry — the important finding

- `update_goal` accepts **only** `status: "complete"`. Pausing, resuming,
  clearing, and budget-limiting are controlled by the user or the extension
  runtime, never by the model.
- Therefore the model may **declare success** but may not **extend its own
  budget**, **pause itself**, or **clear the goal**.

### Durability mechanics

- Continuation instructions ride along as the *content* of a custom message, so
  **the objective is re-injected on every continuation** and survives context
  compaction.
- Goal state is stored as session entries (`customType: "pi-goal"`), follows the
  active session branch, survives reloads, and needs **no external database**.
- Reloading pauses an active goal rather than silently resuming it.
- Time and tokens are accounted on `turn_end`; the final turn is accounted even if
  the goal completes mid-turn.
- The model is *instructed* to audit completion against real evidence before
  calling `update_goal` — an instruction, not an enforcement.

**The portable goal shape** (from the bundled `pi-goal-writer` skill)

A goal is "not a bigger ordinary prompt; it is a completion contract" with six
parts: **outcome, verification surface, constraints, boundaries, iteration policy,
blocked stop condition**. The skill states this shape also applies to *other* goal
modes, i.e. it is a cross-harness idiom rather than a `pi` quirk.

## Why it matters for SoFact

- **§8.2** — it is the reference implementation the harness adapter is designed
  against, and it is concrete rather than imagined.
- **FR-140** — the authority split SoFact needs is *already implemented here*. The
  producer can only declare completion; budget and termination are external. SoFact
  should mirror this rather than invent it.
- **§8.3 / FR-138** — the asymmetry makes the central hazard precise. A goal-mode
  harness is an autonomous producer that reports its own success. Even with the
  "audit against real evidence" instruction, `update_goal({status:"complete"})` is
  a **claim**, not a verification result. SoFact must treat it as a trigger.
- **FR-136/137** — the six-part goal shape is nearly isomorphic to SoFact's module
  contract (§7.3), which means the contract should be authored *so that it
  serializes into a goal*. That is a genuine design constraint, discovered rather
  than assumed.
- **[S08] closure** — `pi-goal`'s mechanics (re-injection per continuation, no
  external DB, pause-on-reload, token budget) are a working implementation of what
  [S08] prescribes for multi-day operation. The paper names the needs; this
  satisfies several of them.

## Concerns / information quality

- **Single implementation.** One harness, one author, v0.1.x. Do not generalise the
  interface from n = 1; the FR-135 capability matrix exists to test that the idiom
  actually transfers.
- **Primary and local.** Not peer-reviewed, not independent, and not a
  recommendation. It is the closest available object of study, which is not the
  same as the best candidate (D11).
- **`update_goal`'s "audit against real evidence" is a prompt, not a guarantee.**
  Nothing in the tool boundary prevents a model from declaring completion
  incorrectly or optimistically. This is exactly why FR-138 exists.
- **Terminology collision, flagged deliberately.** [S08] uses "harness of harness"
  to mean a *layered harness for durability*. SoFact uses it to mean
  *orchestration of many harness instances*. Same phrase, different mechanism; the
  spec cites [S08] for failure modes only, not for the architecture.
- **No telemetry observed** for continuations, per-step tokens, or completion
  accuracy. FR-143 requires these from any harness; if absent, the adapter must
  derive them externally.
