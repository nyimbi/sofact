# 0060 — The boundary is measured, and the ceiling follows the measurement

- **Status:** Accepted (supersedes ADR-0005's refusal of a confinement layer; resolves D9)
- **Date:** 2026-10-14
- **Related:** FR-019, FR-016–020, FR-059, FR-149, FR-030, FR-042, FR-124, FR-152, R2, D9;
  [ADR-0005](0005-no-container-runtime.md),
  [ADR-0045](0045-a-topology-is-a-type-and-a-refusal-is-not-a-downgrade.md),
  [ADR-0053](0053-the-adversarial-audit-is-a-must-fail-canary-and-the-empty-tree-is-the-input.md),
  [ADR-0057](0057-the-autonomy-target-is-a-deployment-scoped-type.md)

## Context

ADR-0005 read FR-019 as a question about *containers* and answered it "no". That was the
right answer to the question it asked, and it left a different one untouched.

FR-019's own text is conditional in three places:

> Isolation must be enforced by the deployment boundary **where one exists**: container,
> VM, or host (§8.3). Same-host, same-filesystem execution is the **degraded**
> configuration and must **lower autonomy ceilings** (§5.4).

*Where one exists* is a measurement. *Degraded* is a finding about a deployment, not a
property of the design. ADR-0005 collapsed all three into a constant: the factory declared
T1, priced every ceiling as degraded, and never asked whether the host it was running on
could confine a child. R2 named the consequence — "autonomy depends on isolation (FR-019)
that is **asserted but never verified**" — and the roadmap's A2 row was blocked on the
decision ADR-0005 had made by omission.

There was a second gap ADR-0005 could not see from where it stood. FR-019 bounds what a
child can **write**. FR-059 bounds what it can **read**: "The harness must run inside the
lane's sandbox with no access to the oracle corpus, holdout scenarios, or factory
credentials (FR-002, FR-016, FR-028)." A boundary that confined writes and permitted global
reads would confine the blast radius and leave the producer its own exam paper — and a
producer that can read the holdout has the answer whatever it can write. The two are
different claims, and the second is the one that decides whether a passing oracle means
anything.

## Decision

**The boundary is a measurement with the same evidence shape as a capability claim.**
`DeploymentBoundary` carries `mechanism`, `enforced`, `attempted`, `observed`, `probed_at`
— the shape `CapabilityFinding` already uses, because "a mechanism confines a child here"
is the same kind of claim as "a harness supports resuming". A boundary reported without
the attempt and the observation is a number to trust rather than a fact to check, which is
what FR-030 forbids.

**`enforced` is separate from `mechanism`, because "the tool is present" and "the tool
confines" came apart on this host.** Measured 2026-10-14: `sandbox-exec` refuses a profile
whose subpath is unresolved — `/tmp` is a symlink to `/private/tmp`, and the kernel matches
the path it is handed. A detector that passed the unresolved path would have reported
`enforced` for a mechanism that confined nothing. This is the whole reason the verdict is a
probe and not a lookup.

**`writes_confined` is separate from `enforced`, because the halves fail independently.**
`enforced` is the credit: writes *and* reads held. A mechanism that confined writes and
left the holdout legible is a real and specific finding — it is kept as the verdict of
record rather than overwritten by the generic "nothing confined the child", which says less
and points at a different remedy.

**`deny_read` is measured, and empty means unmeasured rather than open.** The detector
plants a canary in each named subtree and watches a child fail to open it. Asserting the
rule was written would report the profile's text; planting a canary reports the kernel's
behaviour, and the two came apart for writes. The record names the *subtree roots*, not the
canary files, because enforcement rebuilds a profile from this tuple and a file-level deny
would leave the subtree it sits in readable — a weaker rule than the one measured, reported
as though it were the same.

**A dispatch owns two writable directories, and the profile grants both.** The workspace
is the one FR-019 is written about; the session store is the one the harness writes its
record into. Measured 2026-10-14: a profile granting writes under the workspace alone
denies `touch <session_dir>/record.jsonl` with `Operation not permitted`, and the run then
reports "no session completed, so no oracle ran" for a session that was never permitted to
write one. Every harness was affected — the record always goes to `session_dir` — so the
first version of this boundary broke every wrapped dispatch while looking like confinement.
`writable` is recorded on the boundary for the same reason `deny_read` is: enforcement
rebuilds the profile from the record, and a rebuild that dropped the grant would run a
dispatch under a *narrower* profile than the one measured.

**The escape target is asserted to be outside every grant.** The probe writes
`ESCAPE_MARKER` one directory above the workspace, so a grant containing that directory
would let the child write the marker legitimately and the detector would read its own grant
as a mechanism that failed to confine — reporting no boundary where one holds. The factory's
layout does not hit this (`<home>/workspace` and `<home>/sessions` both leave `<home>` as
the target), and `_escape_target` asserts it rather than assuming it, because the failure is
silent and points the wrong way.

**Seatbelt's rules are last-match-wins, and the position of the deny is the mechanism.**
`(allow file-read*)` → `(deny file-read* (subpath "<home>"))` → `(allow file-read*
(subpath "<workspace>"))` is what makes "deny the factory home, allow the workspace inside
it" expressible at all. A deny emitted before the blanket allowance would be overridden; a
deny emitted after the workspace re-allowance would lock the session out of its own
directory. Both orderings are asserted in `tests/ci/test_boundary.py`, because the failure
is silent in one direction and catastrophic in the other.

**The modifier space does not grow.** §5.4's table tops out at **0** — T4 is "+0, unlocks
L4 admissibility, not a level" — so a measured boundary may only *restore* the baseline a
degraded declaration gave up, never exceed it. `DeploymentBoundary.modifier` is therefore
`0 if enforced else TOPOLOGY_MODIFIER[T1]`, and the cap is what keeps two existing
invariants true without editing either: `topology_ceiling`'s `assert modified <=
int(HIGHEST_GRANTABLE)` and the declared table's `all(modifier <= 0 …)`. A2 is an override
at the call site, not a change to the table.

**`None` is distinct from `enforced=False`.** "No probe was run" and "a probe ran and found
nothing" are different facts about a deployment, and only the second is a finding about
this one. This is FR-042's "not declared" ≠ "declared T1" carried to the boundary, and it
is why `DispatchRecord.boundary` and `DeliveryReport.boundary` are both nullable.

**The restriction knob can only lower.** `SOFACT_BOUNDARY` names which mechanisms the probe
may attempt. It is a *restriction* rather than a declaration: naming a mechanism still
requires the probe to confirm it confines a real child, so no value can raise a ceiling
without a measurement behind it. `SOFACT_BOUNDARY=none` measures nothing and is therefore a
deliberate declaration of the degraded configuration, not a way to claim isolation.

## Evidence

All measured on the development host (darwin 27.0.0, 2026-10-14), not assumed:

- **`sandbox-exec` is present at `/usr/bin/sandbox-exec` and enforces.** A workspace-only
  write profile denied a sibling write (`sibling: DENIED PermissionError`).
- **Seatbelt denies egress.** Unsandboxed, `socket.create_connection(("1.1.1.1", 53))`
  returned `EGRESS_ALLOWED`; under the profile, `EGRESS_DENIED_OR_DOWN PermissionError
  [Errno 1] Operation not permitted`.
- **Seatbelt rules are last-match-wins.** With the three-rule ordering above the result was
  `workspace: READ`, `ledger: DENIED`, `holdout: DENIED`.
- **The realpath is load-bearing.** A profile naming `/tmp` did not deny; the same profile
  naming `/private/tmp` did. A detector passing the unresolved path reports confinement it
  never tested.
- **`TMPDIR` is a real hazard.** A child under a workspace-only profile has its
  `tempfile.mkdtemp()` denied unless `TMPDIR` points inside the workspace — measured twice,
  because the first probe passed only for the accident that the workspace was already under
  `TMPDIR`. `boundary_env` redirects the variable and *creates* the directory rather than
  widening the profile, since widening would admit the probe's own escape target and break
  the instrument.
- **A workspace-only grant denies the session store.** `touch <session_dir>/record.jsonl`
  under the profile returned `Operation not permitted` while the same command in the
  workspace returned 0 — the write half of the profile working exactly as designed, on the
  directory the dispatch needed most. The fix is a grant, not a widened profile: the store
  is a directory the producer legitimately owns, so it belongs in the profile's allow-list
  beside the workspace rather than in the deny's exceptions.
- **`pi` writes its config, registry and auth store outside `--session-dir`, and that store
  is not relocatable.** `~/.pi/agent` measured at 341 MB. Relocating it with
  `PI_CODING_AGENT_DIR` was tried on 2026-10-14 and *refuted*: under a fresh directory
  `pi --list-models` lost this host's custom provider and the probe failed with `Model
  "…" not found`, because the registry is operator configuration rather than something `pi`
  rebuilds. Seeding it forward is not available either — `models.json` carries provider API
  keys, so copying it into the producer's store is the FR-059 violation the boundary exists
  to prevent. This is stated as a limitation rather than solved: `pi` names no store, the
  STORE_ISOLATED row reports `inconclusive` for it, and a deployment that wraps `pi` in a
  boundary denies it the config writes it makes on startup.
- **`podman` is installed and not operational** (`/opt/homebrew/bin/podman`; `podman run`
  fails with `Cannot connect to Podman… connection refused` — its VM is not started).
  `bwrap`, `docker` and `firejail` are absent. So the boundary had to be a *table of
  mechanisms with an honest detector*, not a podman branch: a podman-only path would be
  code that cannot be exercised on the host that has to run it.

## Consequences

- **ADR-0005's refusal is superseded; the rest of it stands.** The T1 lowering survives as
  the *degraded default* rather than the universal case; "oracle commands are trusted
  input" survives for any deployment that measures no boundary, which is still the default
  on a host with no mechanism; "no **required** runtime" survives intact and is the reason
  the mechanism is a table rather than a dependency. Only the claim that a confinement
  layer is out of scope is withdrawn.
- **The ceiling is now a measurement, so it can differ between two runs of the same
  configuration on the same host** — which is the point. A delivery rendered on a host with
  Seatbelt reports T1's ceiling *restored*, and one rendered where nothing confines reports
  T1's penalty. FR-030's "isolation, modifier, topology reported together" now reports a
  measured isolation rather than a documented string.
- **A partially-confining deployment is reportable and is not credited.** Writes held,
  reads open is a finding with its own remedy (narrow the profile, or move the holdout out
  of the denied subtree's reach), and the record says which half failed rather than
  rounding to "not isolated".
- **The container path is measured but not applied to dispatch.** `_container_prefix`
  returns `None` when no image is configured, so the container is not reported as an
  enforced boundary while dispatch runs unwrapped — that conflation is R2 inverted. Its
  read half is deliberately not attempted: the canaries are planted on the host and the
  container mounts only the workspace, so a host canary would be *absent* rather than
  denied, and reporting that as confinement would be the instrument measuring its own
  mount.
- **A third process launch is exempt, and the exemption is written down.** The factory's
  own `session_command` export writes into the session directory inside the factory home
  that FR-059 denies a producer. Wrapping it would have the factory lock itself out of its
  own records and report the resulting empty export as "the session left no record". The
  boundary bounds what the *producer* may reach; the export is not the producer, and saying
  so at the call site is what keeps the exemption from reading as an oversight.
- **A harness config store is not relocatable when it is operator configuration.** `pi`
  keeps its config and model registry at `~/.pi/agent`, and the boundary denies writes
  there, so a wrapped `pi` dispatch is denied the lock files it writes on startup. The
  spec names no store because relocating it was measured to break model resolution and
  because forwarding it would copy credentials into the producer's directory. The
  capability probe does not reach this — `probe_harness` builds its adapter without a
  boundary, deliberately, since the sandbox row's whole instrument is an escape a host
  boundary would mask — so what this costs is confined to a wrapped *dispatch* of `pi`,
  and it is recorded here rather than smoothed over by a relocation that loses the
  registry.
