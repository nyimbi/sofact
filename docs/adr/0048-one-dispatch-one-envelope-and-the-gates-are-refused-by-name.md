# 0048 — One dispatch, one envelope, and the gates are refused by name

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-120, FR-117, FR-119, FR-086, FR-142, FR-161, NFR-024, D18;
  [ADR-0005](0005-the-factory-does-not-run-the-delivered-system.md),
  [ADR-0040](0040-a-delivery-report-states-five-things-and-its-gate-is-human.md)

## Context

FR-120 is one sentence with two subjects in it:

> **FR-120** SoFact must produce the system so that it is **machine-usable** as well as
> human-usable: a documented, stable API surface. A delivered platform that only a human
> can drive fails the stated goal.

The requirement's subject is the *delivered* system. The gap audit's capability map
(`docs/research/orchestrator-capabilities/README.md`, row 85) recorded the sharper reading
when the OpenRig comparison was made: OpenRig ships an MCP server, SoFact's only surface is
the CLI, and **"SoFact's own surface being CLI-only is the same defect one level up."** That
row has said **Gap — build** since it was written, and §3 of the roadmap gap audit carried
FR-120 as the one open half of P8.

Two subjects, two obligations, and they are not the same size:

1. **The factory's own surface.** A machine caller must be able to ask this factory what it
   knows without parsing prose written for a person. This is buildable now, and it is what
   this ADR decides.
2. **The delivered system's surface.** A system the factory builds must expose a documented,
   stable API. This is a *producer obligation*: it is a property of the artefact, it is not
   checkable by any oracle the factory currently has, and making it a machine check would be
   a check that cannot pass — the thing §3 already argues an operator learns to bypass.

The second is recorded rather than built. `DELIVERY_REQUIREMENTS` already names FR-120 in the
delivered report, which is the honest form of an unmet obligation the factory cannot yet
check; §11 of the spec says it "is not built" and that sentence becomes false about half the
requirement the moment this ADR lands, so §11 is amended to say which half.

## Decisions

### 1. One dispatch, one envelope — not a `--json` flag on every verb

The alternative was `--json` on the twenty-odd `typer` commands. It is the wrong shape for a
reason this repository already argues elsewhere: **a flag per verb is a schema per verb**,
each written beside its human rendering, and the two drift the first time one is edited. The
human rendering is the thing a person reads and the JSON is the thing a program reads; a
surface where those are two code paths is a surface where they disagree.

`sofact api <operation>` carries **one** envelope, one error shape, and one place where the
fact "this surface cannot mutate anything" is enforced. The CLI verbs stay the human surface
and gain nothing.

### 2. The table is the surface, and the dispatch has no default

`MACHINE_OPERATIONS` is a dict keyed by operation name, so a duplicate name is impossible by
construction. `payload_for` has **no `else` branch and no default**: an operation added to
the table without a branch raises rather than being answered with another operation's data,
which is the failure a default would produce and the one a caller could not detect. A test
asserts exactly this by calling `payload_for` with an unpublished name and requiring the
`AssertionError`.

The operations are **named rather than numbered**, so a name cannot be reused for a different
meaning. Adding one is additive; changing what one returns is a change to a published
surface, which is what FR-120's word "stable" costs. `MACHINE_API_VERSION` is a string
carried on every response, because the useful thing a caller does with a version is compare
it for equality, not order it.

### 3. Read-only, and the invariant travels with the operation

Every operation folds the log or reads a record. `READ_ONLY_INVARIANT` is a **field on each
`MachineOperation`** rather than a sentence in this ADR, so a caller that reads the table
learns why the operation is shaped as it is without reading the source, and the same sentence
appears on the response. A test asserts the invariant across the whole table rather than per
entry, and a second test asserts that **no operation appends to the log** by comparing the
entry count before and after dispatching every operation in the table — the failure mode is
an operation added later that quietly writes.

### 4. The four human gates are absent from the table and refused *by name*

§3.3 makes four acts human because no oracle decides them: P2's specification approval, P3's
decomposition approval, P4's sampled contract, and P8's deploy — which §1.5 keeps permanent.
A machine surface that could pass one would be a machine passing a human gate, which is the
thing the gates exist to prevent.

So the gate names are **recognised specifically**. `HUMAN_GATE_OPERATIONS` maps each name a
machine would ask for to the human verb to use, and a caller that asks for one is refused
with `HUMAN_GATE_INVARIANT` and the verb — a *different* answer from the one an unpublished
name gets. An operation missing from a table is a bug; an operation refused by an invariant
is a fact about the factory, and the difference is the difference between a caller checking
the code and a caller trusting the docs. The second column is the useful half: a caller told
only "refused" retries, and a caller told which verb to use stops.

The names are **`PhaseGate`'s own values under a `gate:` prefix**, and both halves of that
were forced by the code rather than chosen. Keying on the enum means the table and the phase
machine cannot drift — a fifth gate fails a test instead of being silently unreachable here.
The prefix exists because the two namespaces **collide**: `decomposition` is both a gate a
person passes and a read of the latest decomposition, and the collision was found by running
the surface, not by reading it. A caller asking what the decomposition *is* must get the
read, so the act needs a name of its own, and `gate:decomposition` makes the distinction
visible in the table rather than leaving it to lookup order.

### 5. The envelope is closed, and `ok` is computed rather than stored

`MachineEnvelope` derives `ok` from `error`. It is a `computed_field`, not a plain property,
for a reason that is the whole surface: **the caller here is a program reading JSON, and a
plain property is absent from the serialised document** — so the one field a caller branches
on would be the one field it could not see. This was found by running the verb, not by
reasoning: `status` printed an envelope with no `ok` in it. Computed is still not stored —
the field cannot be supplied, and a payload carrying `ok` is rejected as an extra field.

A refusal carries `result=None` and a model validator refuses an envelope with both an error
and a result: a refusal that also returned a partial answer is an answer a caller would use
past the refusal.

### 6. A refusal is an envelope, and a non-zero exit code

`dispatch` returns a refusal envelope rather than raising, because this surface's caller is a
program: an exception crossing a subprocess boundary is a traceback and an exit code, while
an envelope is a fact the caller can branch on. `MachineRefusal` exists internally so the
reason travels as data rather than being formatted into a message and re-parsed.

The verb exits **1** on a refusal. A refusal that exited zero would let a shell chain past a
human gate without reading the body, which is the whole failure this verb could have.

### 7. The delivered-system half is a producer obligation, recorded and not faked

FR-120's other subject is a property of the artefact the factory produces, and no oracle in
O1–O8 observes it. The honest handling is what FR-158 got one requirement along: **state it,
name it, and do not manufacture a check for it.** `DELIVERY_REQUIREMENTS` names FR-120 in
every delivered report; §11 of the spec is amended to say which half is built; and the gap
audit's row is closed for the factory's surface with the delivered-system half recorded as
open.

## Alternatives refused

1. **`--json` on every verb.** A schema per verb beside its human rendering, drifting on
   first edit. Refused; see Decision 1.
2. **An MCP server.** OpenRig ships one and the capability map names it. Refused *for now*
   and not on principle: MCP is a transport, and the thing FR-120 needs is a stable surface
   with a closed envelope. A JSON dispatch over stdout is that surface with no dependency,
   and an MCP server can be written *over* it later without changing what the operations
   answer. Building the transport first would put a protocol between the caller and a table
   that does not exist yet.
3. **A typed argument model per operation.** Nine near-empty Pydantic models to keep in step
   with the table for no gain. `MachineRequest.arguments` is a free mapping; when an
   operation needs an argument its *contents* get a type and the envelope's shape does not
   change.
4. **A default branch in `payload_for`.** Refused; it is the failure mode Decision 2 exists
   to prevent.
5. **A tuple of operations rather than a dict.** A tuple permits two operations of one name,
   which makes the surface's behaviour depend on table order.
6. **Unlisting the gates instead of recognising them.** A caller asking for `deploy` would
   get "unknown operation", which is false — the operation is known and deliberately not
   offered. Refused; see Decision 4.
7. **Returning a partial result alongside a refusal.** Refused by a model validator; see
   Decision 5.
8. **A stored `ok` field.** A stored field can disagree with the error beside it. Refused;
   the derived version is emitted, so the caller still sees it.
9. **A writable surface with an `--allow-write` flag.** There is nothing a machine caller
   needs to write that is not a human gate, and a flag that unlocks mutation is a flag a
   script sets once and every caller inherits.

## Consequences

- **The factory is drivable by a program.** `sofact api --list` publishes the surface, and
  `sofact api <operation>` answers one call with one envelope. A caller can discover what may
  be asked and what may not, without reading this repository.
- **Adding an operation is now a two-place edit**, and the test suite says so: a table entry
  without a `payload_for` branch fails rather than answering with someone else's data. That
  is deliberate friction at the one place the surface can silently lie.
- **The gates are visible as refusals rather than as absences.** A caller that tries to
  approve a specification through the machine surface gets the human verb, which is the
  answer that stops it rather than the answer that makes it retry.
- **FR-120 is half closed and the open half is recorded as a producer obligation**, not as a
  missing feature. A delivered system still does not have to expose an API the factory checks
  — and the report says so in every delivery, which is the honest form of the gap.
- **`MACHINE_API_VERSION` is now a promise.** Changing what an operation returns is a change
  to a published surface; the version is how that is announced.
