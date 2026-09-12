# 0001 — Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-09-12

## Context

SoFact is being built ahead of a market. Its product specification carries 118
functional requirements and 13 open decisions, and its central claim — that a
producer's assertion of success is not evidence of success — cannot be checked by
looking at whether the software appears to work. The reasoning behind a requirement
is the part that is easiest to lose and most expensive to reconstruct.

Two specific hazards motivate a written record rather than commit messages:

1. **Requirements outlive their context.** Several decisions in the specification
   were reached by *narrowing* scope (L5 autonomy declined, commercialisation
   declined, plugin surface declined). A future reader sees only the narrow version
   and re-opens a question that was answered deliberately.
2. **Some decisions rest on measurements.** The harness choice rests on an executed
   probe; the isolation posture rests on the absence of a container runtime on the
   target host. Those grounds are not visible in the resulting code.

## Decision

Every architecturally significant decision is recorded as a numbered ADR in
`docs/adr/`, in the form it was made, with its cost stated. Records are immutable;
a changed decision is a new record that names what it supersedes.

A decision is architecturally significant if it constrains what future code can do,
or if reversing it would require touching more than one module. Decisions that only
affect the inside of one module are comments, not ADRs.

## Consequences

- The specification's `D<n>` identifiers and the ADR numbers are two namespaces for
  overlapping material. [README.md](README.md) carries the mapping so neither has to
  be the single source of truth.
- Writing an ADR is a real cost at the moment of deciding, paid to avoid a larger
  cost at the moment of remembering.
- The record can go stale relative to code. This is accepted: a stale ADR that is
  read and found wrong is still better than no record, because it makes the
  divergence visible. The remedy is a superseding record, not an edit.
