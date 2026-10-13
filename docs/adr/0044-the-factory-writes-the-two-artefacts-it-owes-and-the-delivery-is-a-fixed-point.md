# 0044 — The factory writes the two artefacts it owes, and the delivery is a fixed point

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-117, FR-118, FR-119, FR-121, FR-086, ADR-0005, FR-124, FR-160;
  [ADR-0040](0040-a-delivery-report-states-five-things-and-its-gate-is-human.md),
  [ADR-0042](0042-a-modules-definition-of-done-is-derived-from-its-oracles-shape.md)

## Context

ADR-0040 scoped the artefact check to the two of FR-117's four kinds the *factory* owes —
`RUNBOOK.md` and `DELIVERY.md` — on the argument that the other two (a container image and
infrastructure-as-code) are decisions ADR-0005 and FR-124 leave to the operator, so a check
over all four could never pass.

The scoping was right and the consequence was not noticed: **nothing produced the two it
kept.** `delivery.artifact` reads presence off the filesystem, honestly, so a report over a
fresh delivery root failed its own artefact check, `sofact deliver` exited non-zero, and
`sofact deploy` could not be reached at all. The only way past it was for a human to
hand-write the two documents the factory claims to produce.

A factory that refuses to deliver until someone else has written its output is not a
factory. This is the same shape as the gap ADR-0042 closed one artefact along: a field that
looks like a derived output, with nothing deriving it.

## Decisions

### 1. The rendering is deterministic and model-free

`sofact.writing` renders both documents from the `DeliveryReport` and nothing else. Every
input is a record the log already holds, so two renders of one report are byte-identical and
a diff between two deliveries is a diff between two sets of facts.

This is the whole design constraint, and it is not a stylistic preference. A runbook written
by a language model would be plausible prose about a system nobody ran, and it would be
indistinguishable from the real thing at exactly the moment it mattered — the moment a human
reads it to decide whether to deploy. SoFact already refuses transcription from prose in
`research.py` for the weaker version of this reason; a *generated* document is worse than a
transcribed one, because the transcription at least had a source.

### 2. The runbook is derived from the handover, not written beside it

FR-121 makes the maintenance lanes the next mode's input, so the operational document and
the machine-readable handover are **one derivation with two renderings**. Two statements of
one fact drift, and the drift would be invisible because both would read as plausible prose.
`render_runbook` reads `report.handover` and adds no lane, ceiling, or oracle the handover
does not carry.

`render_delivery_artifacts` returns both by kind, so a caller cannot render one without the
other. A runbook quoting a report id that no `DELIVERY.md` exists for is not a delivery.

### 3. Every heading is always written, and the constants assert it

A reader under time pressure cannot notice a section that is *absent* — that is the one
failure a report cannot signal about itself. So `DELIVERY_HEADINGS` and `RUNBOOK_HEADINGS`
are constants, every heading is written whether or not it has content, and each renderer
ends by asserting every heading survived:

```python
missing = [heading for heading in DELIVERY_HEADINGS if f"## {heading}" not in rendered]
assert not missing, f"the delivery document lost section(s): {missing}"
```

A section renamed or dropped by a later edit fails here rather than silently leaving the
document. `_EMPTY` is a sentence rather than an empty body for the same reason, and `None`
is also the honest word: an empty list of unverified clauses is a finding about the
delivery, not a formatting accident.

### 4. The delivery is computed as a fixed point, not in one pass

The documents render the report, and the report's artefact check reads the filesystem. That
is a cycle: the report cannot be final until the files exist, and the files are rendered from
the report.

`render_delivery` therefore renders, writes, renders again, and stops when a render agrees
with what is on disk. Two rounds settle it because the only thing the first write can change
is presence, and presence does not change back. The loop is bounded rather than `while True`
so that a root the render cannot agree with is a refusal with a sentence rather than a spin,
and the `else` raises naming FR-119: a report the gate shows must describe the root it was
shown over.

The alternative — write first with a placeholder identity, then read back the written
document to discover what was written — is the read-modify-write this module refuses
everywhere else. Every argument to each round is the same object, read once from the log, and
the report identity is pinned by the caller, so a round can only differ from the last by
`artifacts` — by exactly the two files the previous round wrote. Nothing is re-read from the
log, so nothing drifts.

### 5. The report identity is minted by the caller

`delivery.report` gained `report_id` and `rendered_at` so a writer can know the id *before*
the report exists. The two documents quote it — that is what lets a deploy gate tie a runbook
to the checks it approved (FR-119) — and rendering twice to discover it would be rendering
the same facts twice, with the second render being the one a reader trusts.

Both default to `None`, which mints them inside `report`. That keeps `report` usable as a
pure function of the log for every caller that is not writing files.

### 6. `sofact deliver` requires `--root`

A delivery now has a place it is written to, so the flag is required rather than defaulted:
a default would put a delivery wherever the operator happened to be standing. The refusal
names the flag.

This is also the *declared artefact root* that ADR-0039's `delivered_loc` reason says does
not exist — "a count needs a declared artefact root first". The reason is left unchanged
here, because naming a root is not the same as reading source under it and ADR-0025 still
leaves the target language open; what has changed is that the precondition is now
satisfiable.

## Alternatives refused

- **A model writes the documents.** Refused in Decision 1: plausible prose about a system
  nobody ran, indistinguishable from the real thing when it matters.
- **The artefact check is dropped or made to pass.** Refused by ADR-0040's argument, which
  this record does not reopen: the check is the reason the shortfall was visible at all. The
  fix is to produce the artefacts, not to stop looking for them.
- **The files are written by the CLI, outside `render_delivery`.** Refused because the report
  the deploy gate shows would then be a report that never saw the files it names, and
  `report.passed` would be a property of which entry point was used. The API and the CLI must
  agree about what a delivery is.
- **`render_delivery` defaults the root to `home`.** Refused: a delivery written into the
  project's own state directory would mix the factory's records with the artefacts they
  describe, and `root is None` already has an honest meaning — nothing was written, and the
  report says so in the words of the two artefacts.
- **A third round, or a loop until stable.** Refused as unfalsifiable: the fixed point is
  reachable in one write, so a loop that could run longer would be running for a reason the
  design does not have. Two rounds with an assertion is the whole property.

## Consequences

- `sofact deliver --root <dir>` succeeds on a fresh project and writes both documents.
- `DELIVERY.md` and `RUNBOOK.md` are quotable evidence: each carries the report id the deploy
  gate names, so an approval cannot stand over a document from a different delivery.
- The two tests that asserted the *old* behaviour are rewritten rather than deleted. The CLI
  test now asserts the files exist **and** carry the report's id — a presence check alone
  would pass on two placeholders. The service test reaches the failing check through
  `render_delivery` with no root, which the API allows and the CLI refuses, so the gate's
  refusal is still exercised on a real failed check rather than a planted one.
- FR-120 (the machine-usable API surface) is **still unbuilt**. This record closes FR-117's
  artefact half, not FR-120.

## Evidence

The canary for Decision 4: with the write loop disabled (`if root is not None and False:`),
`test_an_empty_delivery_root_is_filled_by_the_delivery` fails at its first assertion because
the root is still empty — the write is what makes the check true. Watched failing before
being believed; restored from a file backup, never `git checkout`.

The canary for Decision 3: renaming one heading in the body (`## Gate cost` →
`## Gate spend`) while leaving `DELIVERY_HEADINGS` alone fails the assertion at the end of
the render, and 14 tests fail with it. Watched failing before being believed; restored from
a file backup, never `git checkout`. The only way to silence it is to edit the constant and
the body together, which is a deliberate edit rather than a drift — that is why the
constant is a module constant rather than an inline sequence.
