# 0066 — The egress half of the boundary is measured, and an open network is not credited

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** ADR-0060, FR-019, FR-016–020, FR-124, FR-152, FR-030, FR-059, NFR-024

## Context

ADR-0060 built the boundary as a measurement: `detect_boundary` runs one real child that
writes inside its directory and then tries to write above it, and a mechanism is credited
only when the inside marker appeared and the escape marker did not. That instrument
measures **one half of FR-019's isolation** — the filesystem — and FR-019's own ceiling is
priced against what a producer can *do*.

Two documents named the missing half and neither was acted on. FR-124's row read
"packaging and **egress** are not read from the topology", and M0 item 5 makes it an exit
criterion in the spec's words: "container boundary and **egress denial actually hold**"
(FR-019). So a delivery reported `enforced` — and therefore a ceiling modifier of 0 rather
than T1's −1 — on the strength of the write half alone, while nothing had asked whether the
confined child could reach the network.

The gap is not academic on this host. Measured 2026-10-15: a child under
`seatbelt_profile`'s output is refused a TCP connect to a listener the measuring process
has bound on `127.0.0.1`, and the same source with no profile connects. The profile's
`(deny default)` denies `network*` — which is also the mechanism by which the write half
works. So the property holds and **nothing recorded it**, which is the same failure ADR-0060
was written about one layer up: R2, "isolation asserted but never verified".

## Decision

**`DeploymentBoundary` gains `egress`, `egress_observed` and `egress_confined`, and the
measurement is a second launch against a listener this process owns.**

**The probe is loopback, and that is the whole design.** An earlier draft connected to a
public address and was rejected for three separate reasons, each a defect on its own: it
needs the internet to run, so an offline host reports "no egress" for a boundary that may
not hold; it needs DNS, which the profile also governs, so a name-resolution failure and a
denied connect are indistinguishable in the observation; and it sends a packet to a third
party every time a factory measures itself, which is an egress from the thing measuring
egress. A listener bound by the measuring process answers deterministically, so "refused"
cannot be confused with "nothing was routable".

**`egress` is a `ProbeOutcome`, not a `bool`, and it defaults to `INCONCLUSIVE`.** The
three states are three different facts: a child watched being refused (`CONFIRMED`), a
child watched connecting (`ABSENT`), and a probe that could not run (`INCONCLUSIVE`). The
default is the third so a record written before the probe existed reads as *not measured*
rather than as *measured and open* — the only direction that cannot over-claim.

**An open egress is not credited, and a denied one is not credited either when the
filesystem half failed.** `enforced` is false when `egress` is `ABSENT`, because a
producer that can reach the network has an exfiltration path whatever it can write. The
converse is enforced in the renderer: `_egress_clause` conditions the "holds by
measurement" wording on `enforced`, because it is reachable from the *degraded* branch of
`topology_statement`, where printing the egress credit beside a modifier of −1 would put
two contradictory claims about one deployment in one sentence.

**The egress child is a separate launch, not a branch in the probe script.** Seatbelt's
rules are last-match-wins, so an `(allow network*)` inserted for a wrapped child would be
a rule the *enforcement* profile does not carry — measuring a profile the dispatch will
never run. The same profile is rebuilt for both launches, so the two differ in exactly one
thing: the script they run.

## Evidence

**Measured on this host, 2026-10-15.** A listener bound on loopback; the same source run
with and without the profile:

| Child | Result |
| --- | --- |
| No profile | `CONNECTED` |
| `seatbelt_profile` output | `PermissionError: [Errno 1] Operation not permitted` |

`detect_boundary` on a real workspace reports `mechanism=seatbelt, enforced=True,
egress=confirmed, writes_confined=True`, with the `deny_read` subtree the caller named.

**Four canaries, each watched failing and reverted from a file backup:**

1. **`enforced = egress is not ProbeOutcome.ABSENT` → `enforced = True`** — the open
   network credited anyway.
2. **The two verdict words swapped** (`EGRESS_DENIED` and `EGRESS_ALLOWED`) — caught by
   both the positive and the negative test.
3. **The `INCONCLUSIVE` default → `CONFIRMED`** — an unmeasured half reporting as a
   measured one.
4. **`if not boundary.enforced:` → `if False:`** in `_egress_clause` — a degraded boundary
   reclaiming the egress credit.

**The first canary was MISSED, and that is the finding this record exists for.** The
negative case had been tested by `model_copy` on a finished record, which exercises the
*renderer* and never the *detector* — so the fold that turns a measured-open egress into
`enforced=False` had no test at all, and blinding it changed nothing the suite could see.
The fix was `egress_unwrapped`, a switch that runs the same source against the same
listener with no profile, making `ABSENT` reachable from a real child. The canary was then
re-run against the strengthened gate and **caught**. A test-only switch on a detector is a
liability — it is a way to make the instrument lie — so it is documented as the control it
is and it can only ever make the egress half report *less* confinement, never more.

## Consequences

1. **FR-019's second half is measured, and M0 item 5's egress criterion is met on this
   host** — for the Seatbelt mechanism. The container path is unchanged: this host has
   `podman` installed and not operational, so `_container_prefix` still returns `None` and
   the container's `--network=none` is written but never exercised.
2. **FR-124's row moves on the egress half and stays Partly on packaging.** Nothing reads
   the topology to vary how an artifact is packaged, and that half is untouched here.
3. **A delivery now prints the network half beside the modifier.** FR-030's requirement is
   that isolation be reported beside the ceiling; the report previously named the
   filesystem confinement and left a reader to supply the network half from the word
   "confined".
4. **The probe binds a port per measurement.** It is closed in a `finally`, and the
   service caches the boundary for the life of the run, so this is one port per service
   rather than one per dispatch.
5. **It does not measure egress for a container**, and it says so. The `CONTAINER` branch
   returns `INCONCLUSIVE` when no runtime or image is configured, rather than reading the
   absence as confinement.
6. **The probe forced a module split, and the authorship instrument is what found it.** A
   loopback listener needs `socket`, so `sofact/boundary.py` came to import it — and
   `sofact.manufacture` imports `boundary_env`/`wrap_argv` from that module, which put
   `socket` inside the `oracle_authoring` surface's transitive import closure that ADR-0064
   measures. The check failed, correctly. The boundary is now two modules: `sofact.boundary`
   applies a measured boundary and imports neither `socket` nor `asyncio`, and
   `sofact.boundary_probe` measures one. See ADR-0067.

## What this does not do

- **It does not prove egress denial for anything but the mechanism measured.** A
  deployment whose `only` excludes Seatbelt measures nothing, and the record says
  `INCONCLUSIVE`.
- **It does not make `--offline` a boundary.** FR-152 is unchanged: `--offline` is a
  documented refusal to claim one, and this probe measures the *boundary*, not the flag.
- **It does not change the container's egress handling.** `--network=none` remains written
  and unexercised on this host.
- **It does not raise any ceiling.** `DeploymentBoundary.modifier` still tops out at 0, so
  a measured egress can only restore what a degraded declaration gave up.
