# 0032 — An isolation variable is measured by a differential with a control arm

**Status:** Accepted
**Date:** 2026-10-12
**Context:** FR-019, FR-148, FR-165. Closes §3.3 of the capability map and the row it
listed as the cheapest unmeasured claim in the tree.

## Context

SoFact's harness specs isolate a child by environment variable: `CLAUDE_CONFIG_DIR` for
`claude`, `OPENCODE_DB` + `OPENCODE_TEST_HOME` for `opencode`, `DSH_HOME` for `dsh`. Each
spec's notes say what happens without it, and for `claude` and `opencode` that was
*measured* — the store moved wholesale when the variable was set.

A measurement that a variable works is not a measurement that it is a **boundary**. The
capability map recorded this as its sharpest unbuilt row, quoting OpenRig's own README
about its equivalent variable: changing `OPENRIG_HOME` alone does not isolate provider
configuration. The generalisation is that an isolation variable is not an isolation
boundary until something measures that the provider honoured it, and a spec field that
*looks* like isolation and has never been observed to isolate is worse than no field,
because a reader counts it as one. That is the hazard S26 names outright.

Two things had to be settled before it could be built.

**What is the observable?** The obvious one — "the operator's real store did not move" —
is not measurable. The operator's store is live: on this machine `~/.claude.json` is
rewritten by the very session doing the measuring, so its mtime moves whether or not the
probe touched it. A row keyed on it would fail on the instrument's own noise.

**What makes a negative decidable?** "The private store was honoured" is an absence, and
an absence is only evidence once something has shown the instrument can see the
difference. A row that reports `CONFIRMED` because a directory is empty would report it
for a harness that writes nothing there under any configuration.

## Decision

**1. The observable is a relocated `HOME`, and the differential has a control arm.** Both
arms run the same goal in their own workspace with `HOME` pointed at a fresh empty
directory; they differ in exactly one thing — whether the spec's containment variables are
applied. `CONFIRMED` requires the isolated arm's `HOME` to be empty **and** the control
arm's to be non-empty. The control is what turns the first arm's silence into evidence: it
proves a relocated `HOME` is a live variable for this harness, so the difference between
the arms is attributable to containment rather than to an instrument that cannot see
anything.

**2. A spec declares *which* of its variables make the containment claim.** `env` carries
two different kinds of thing. `pi-research` sets `RESEARCH_MODEL` to pin a model and
`npm_config_*` to quieten npm's stderr; neither claims to bound anything. The new
`HarnessSpec.isolation_env` names the containment variables, and only those are withheld
from the control arm — so the differential varies one thing, not three. A spec that names
none is reported `INCONCLUSIVE` with "declares no containment variables" and costs no
child, because it asserts nothing for this row to check.

**3. A harness the instrument cannot see reports a limit of the probe, not a property of
the harness.** When the control arm's `HOME` is *also* empty, the row is `INCONCLUSIVE`
and says the probe is blind here. This is ADR-0019's rule applied to a new instrument:
`ABSENT` would condemn a harness the probe never observed, and `CONFIRMED` would be a
fabricated capability.

**4. The row measures the store and says it does not measure the child.** `sandboxable`
remains `ABSENT` for both `pi` and `claude` — measured, the tool allowlist does not
contain the child. A contained store and an uncontained child are both true at once, and
the finding's own text names `FR-019, FR-141` for the store while the sandbox row carries
the confinement result. Neither is allowed to stand in for the other.

## Consequences

- `HarnessCapability.STORE_ISOLATED` is the eleventh row, and the probe's existing
  completeness assertion (`len(profile.findings) == len(HarnessCapability)`) means a
  capability added without a row fails the suite. The pinned count in
  `test_every_capability_including_this_one_is_reported` moved 10 → 11.
- The row is gated with the other extras: it runs only after the primary attempt did
  work, and `--quick` skips it with its own reason string.
- `ConfiguredHarnessAdapter` gains `spec_env: bool`, and `variant()` gains `env` and
  `spec_env` slots. `spec_env=False` drops the spec's entries and changes nothing else,
  which is the whole control arm.
- **This narrows gap 2 in the roadmap audit; it does not close it.** The audit row moved
  from *Not built* to *Partly*, and both documents say what is still missing: no enforced
  boundary anywhere, `FR-059` still prompt text, egress still unmitigated (FR-152).
- `pi` and `pi-research` declare no containment variables, which is the honest answer:
  `pi` isolates by `--session-dir` in its argv. This row cannot decide them in either
  direction, and reports that rather than inferring.

## Alternatives refused

**Measure the operator's real store.** Refused in Context. It is live — the measuring
session writes to it — so the row would report the operator's own activity as a leak. The
relocated `HOME` is a store the probe owns end to end.

**One arm, keyed on the private store being non-empty.** Refused in decision 1. It reads
`CONFIRMED` for any harness that writes nothing under `HOME` in any configuration, which
is precisely the class of harness this row exists to catch.

**Vary the whole of `env` between the arms.** Refused in decision 2. Withholding
`RESEARCH_MODEL` alongside `CLAUDE_CONFIG_DIR` leaves two arms differing in several ways
at once, and a difference can no longer be attributed to containment.

**Report `ABSENT` when the control arm is also empty.** Refused in decision 3: that
condemns a harness on evidence the probe never gathered, and the honest report is a
coverage gap in the instrument.

**Extend the row to egress.** Refused. FR-152 is a network question and a filesystem
`HOME` cannot answer it; folding them together would let a contained store read as a
closed egress route.

## Evidence

- `src/sofact/harness.py` — `_probe_store_isolated`, `STORE_PROBE_GOAL`, `_files_under`,
  `HarnessSpec.isolation_env`, `ConfiguredHarnessAdapter.spec_env`.
- `tests/ci/test_harness.py` — `TestStoreIsolation`, 8 tests. The pair that matters:
  `test_a_spec_whose_env_contains_the_store_is_confirmed` and
  `test_a_variable_that_does_not_contain_the_child_is_absent`.
- Canary: the control-arm branch was deleted from a scratch copy (the patch asserted its
  target string was present first), and
  `test_the_control_arm_is_what_makes_the_empty_home_mean_something` failed — the row
  read `CONFIRMED` for a harness whose store the probe cannot see. Restored from the
  backup file, not from git.
- Measured against the real `claude` spec on 2026-10-12: with `CLAUDE_CONFIG_DIR` applied
  the child left its relocated `HOME` holding **0** files; with the variable withheld it
  wrote **3** — `.claude.json`, `.claude/projects/<slug>/<id>.jsonl`, and a backup. The
  finding reads `confirmed` end to end.
- `tests/ci` at this commit: **725 passed, 0 failed**. `pyright`: 0 errors.
