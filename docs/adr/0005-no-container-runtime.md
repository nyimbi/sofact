# 0005 — No container runtime

- **Status:** Accepted (resolves D9) — **partly superseded.** The refusal of a
  confinement layer is withdrawn by [0060](0060-the-boundary-is-measured-and-the-ceiling-follows-the-measurement.md);
  what stands is the T1 lowering as the *degraded default*, the trusted-input
  consequence for a deployment that measures no boundary, and the ruling that no
  runtime is **required**.
- **Date:** 2026-09-12
- **Superseded by:** [0060](0060-the-boundary-is-measured-and-the-ceiling-follows-the-measurement.md)
  — the container layer. This record is not deleted, and its reasoning is not
  withdrawn: 0060 keeps every one of its consequences and changes only which case is
  the default. Its closing line, "if a sandbox is ever added, the ceilings in this ADR
  are the number to revisit, and a superseding record should say so explicitly rather
  than silently raising them", is the instruction 0060 followed.

## Context

SoFact runs oracle commands. Those commands are arbitrary shell, authored by an
operator or derived from a contract. The instinct is to isolate them: give each run
its own container, its own filesystem, its own network namespace, and cap the blast
radius structurally.

The target host has no container runtime. `docker` is absent from the tooling
inventory. This was initially treated as a development-machine inconvenience — the
kind of thing that would be present in production — and it was worth asking whether
that assumption held.

It does not, for two reasons:

1. **The product promises hardware-agnostic deployment** on `x86_64` and `arm64`
   Linux with no GPU required, in a *single* form. Requiring a container runtime
   makes root-level infrastructure a prerequisite, which contradicts the delivery
   envelope (spec §1.3) in which SoFact is something you run, not something you
   provision a cluster for.
2. **Isolation was never the actual guarantee.** The autonomy ceiling is set by the
   weakest oracle rank in the contract, and by escape rate — not by how the process
   was boxed. A container that runs a weak oracle is a well-isolated weak oracle.

## Decision

**No containers.** Oracle commands execute as **local processes**, in an explicit
workspace directory, under a timeout, with output truncated.

Confinement is scoped by *filesystem and blast bound*, not by a kernel boundary:
SoFact states the workspace it will run in, and records what actually happened. It
does not imply a sandbox it does not enforce.

This changes the specification in two places: FR-019 (isolation) and the T1/T2
autonomy ceilings. The honest ceilings are lower than they would be with a real
sandbox, and they are lowered rather than left aspirational.

## Evidence

- `docker` is absent from the tooling inventory on the development host.
- `OracleRunner` takes an explicit `workspace` and a `timeout`, runs via
  `asyncio.create_subprocess_shell(cwd=workspace)`, and records `timed_out` and the
  exit code as observations.
- A timeout is recorded as evidence yielding **`INSUFFICIENT`**, not `VIOLATED`: a
  hung instrument falsifies nothing, and because `INSUFFICIENT` grants no autonomy
  either, hanging buys a producer nothing. Asserted in
  `tests/ci/test_execution.py::test_timeout_is_recorded_and_terminates_the_process`.

## Consequences

- **Oracle commands are trusted input.** They run with the invoking user's
  privileges. This is a real limitation, stated rather than papered over. The
  mitigation is that oracles are operator-authored: FR-155's admission test and
  FR-156 (config before code) both narrow the surface, and G7 lanes —
  auth, secrets, payments, PII — are capped at L1 and human-authored regardless.
- The `command_hint` on an oracle is therefore load-bearing in a way a sandboxed
  design would not require. A fabricated `command_hint` is not merely wrong, it is
  wrong *and executed*, which is why `contract.suggest_oracle` never invents one.
- Removing the container dependency keeps the single-form deployment promise intact.
- If a sandbox is ever added, the ceilings in this ADR are the number to revisit, and
  a superseding record should say so explicitly rather than silently raising them.
