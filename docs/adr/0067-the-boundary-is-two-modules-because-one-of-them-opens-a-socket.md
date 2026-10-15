# 0067 — The boundary is two modules, because one of them opens a socket

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** ADR-0060, ADR-0064, ADR-0066, FR-019, FR-053, FR-134, FR-016–020

## Context

ADR-0060 built the deployment boundary in one module, `sofact/boundary.py`, and ADR-0066
added the egress half to it. The egress half binds a loopback listener, so it needs
`socket`. That import was added to `boundary.py` at module scope, and the authorship
instrument of ADR-0064 reported the consequence immediately:

```text
contract_authoring     closure=  4  reaching=()
oracle_authoring       closure=  5  reaching=('socket',)
```

The edge is real and the scanner is right. `sofact.manufacture` imports
`boundary_env`/`wrap_argv` from `sofact.boundary` (`manufacture.py:62`), `manufacture` is a
root of the `oracle_authoring` surface, and `boundary.py` had come to import `socket`. The
closure is transitive, so a surface that reaches `boundary` reaches whatever `boundary`
reaches — which is the whole design: ADR-0064 chose reachability over a call-site count
precisely because "a call-site check passes the moment somebody adds one."

ADR-0064's own Evidence block records the pre-egress measurement: `oracle_authoring`
closure `5`, `reaching=()`. So the finding is not that the check is too strict. It is that
a change to the tree moved a surface into reach of a network primitive, and the instrument
said so before anything shipped.

**`sofact.manufacture` never calls the detector.** It imports two functions that take an
already-measured `DeploymentBoundary` and return `tuple[str, ...]` and `dict[str, str]`.
It has no use for `detect_boundary`, for `egress_probe`, or for a socket, and it never had
one. The import edge existed only because the two capabilities — *applying* a boundary and
*measuring* one — were written in one file.

## Decision

**The boundary is two modules. `sofact.boundary` applies a measured boundary and imports
neither `socket` nor `asyncio`; `sofact.boundary_probe` measures one and is the only half
that opens a socket.**

The split is along the line the two callers already drew, not along a line invented to
satisfy the scanner:

- **`sofact/boundary.py`** — `seatbelt_profile`, `container_prefix`, `wrap_argv`,
  `boundary_env`, `TEMP_DIRNAME`, `SEATBELT`, `CONTAINER_IMAGE_ENV`. Every one is a pure
  function of a measured record and a path. The four process-launching callers
  (`execution`, `harness`, `mutation`, `manufacture`) import only from here.
- **`sofact/boundary_probe.py`** — `detect_boundary`, `egress_probe`, the probe script, the
  marker constants, `_measure`, `_measure_egress`. The one caller is `service.py`, which
  measures the boundary once per service and caches it.

`seatbelt_profile` and `container_prefix` live in the applying half and the probe imports
them, because the profile the detector *measures* and the profile a dispatch *runs under*
must be the same construction — ADR-0060's rule that "the rules a dispatch runs under are
the rules the probe measured." Sharing them one way (probe → apply) keeps that identity and
keeps the socket out of the applying half; duplicating them would let the two drift.

`_container_prefix` is renamed `container_prefix` in the move. A leading underscore on a
name that another module imports is the wrong signal, and the probe half is a legitimate
second reader.

**`PROFILE_NAME` is deleted rather than moved.** It was written and read by nothing — the
profile is passed to `sandbox-exec -p` as text, so no profile file is ever named. A
constant whose only occurrence is its own definition is a claim about a mechanism that does
not exist.

## Evidence

**Before** (the state that failed `test_the_verb_reports_both_surfaces_and_exits_zero`):

```text
oracle_authoring       closure=  5  reaching=('socket',)
    sofact.manufacture -> sofact.boundary -> socket
```

**After** the split, measured with the same instrument:

```text
contract_authoring     closure=  4  reaching=()
    ('sofact._uuid7', 'sofact.contract', 'sofact.elicitation', 'sofact.views')
oracle_authoring       closure=  5  reaching=()
    ('sofact._uuid7', 'sofact.boundary', 'sofact.contract', 'sofact.manufacture', 'sofact.views')
```

Both closures are byte-identical to ADR-0064's recorded measurement. `sofact.boundary_probe`
is not in either closure, which is the point: the measuring half is reachable from
`service.py` and from nowhere an authoring surface can get to.

`tests/ci/test_boundary.py` (30 tests) passes unchanged apart from its imports, and
`tests/ci/test_authorship.py` + `TestTheAuthorshipVerb` (31 tests) pass.

## Consequences

1. **The authoring surfaces cannot reach a socket, and the closure says so rather than a
   comment.** The property ADR-0064 measures is restored, and it is now structural: a
   future edit that adds a network import to the applying half fails the same check.
2. **A module boundary now encodes a capability boundary.** The next person who wants to
   measure something by opening a socket has a module to put it in and a reason the reason
   is not merely stylistic.
3. **`service.py` imports from two modules where it imported from one.** That is the honest
   shape: it is the only component that both measures a boundary and applies one.
4. **The finding is recorded rather than quietly fixed.** The instrument caught a real
   regression introduced by ADR-0066's own work, which is evidence the instrument works —
   and the same evidence ADR-0064 was written to produce.

## What this does not do

- **It does not change what is measured.** `detect_boundary` runs the same two children
  against the same markers and the same listener; only the file it lives in changed.
- **It does not weaken the egress probe.** The probe still binds a real listener and the
  child still attempts a real connect; the socket simply lives where a socket belongs.
- **It does not add a gate.** The closure check already existed (ADR-0064) and already
  failed. This record is about what the failure meant and what was done about it.
