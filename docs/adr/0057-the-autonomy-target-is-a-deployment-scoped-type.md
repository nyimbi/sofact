# 0057 — The autonomy target is a deployment-scoped type, and absence is a state

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** FR-157; FR-021–023, FR-024–035, FR-107, FR-022, FR-156, NFR-024, D17, D18;
  [ADR-0053](0053-the-adversarial-audit-is-a-must-fail-canary-and-the-empty-tree-is-the-input.md),
  [ADR-0054](0054-the-escape-rate-is-the-one-number-no-producer-authored.md),
  [ADR-0056](0056-the-freeze-is-derived-from-the-argv-and-the-deletion-test-admits.md)

## Context

FR-157's sentence is short: "The autonomy target is **deployment-scoped, not
product-scoped**." Its consequence is not. For D17's personal-use case the requirement
fixes a band — "the required ceiling is **L2–L3 with escape-rate tracking** (FR-107), and
the θ_hi = 0.80 gate that admits L4 (FR-024–FR-035) **must not be imposed as a default**"
— and for a third party it fixes the opposite: "the L4 gate applies unchanged."

The roadmap recorded the row as **Partly** and named the gap exactly: the *inputs* had
arrived — FR-107's adversarial audit (ADR-0053) and FR-022's escape rate (ADR-0054) — and
"no deployment scope type carries 'this deployment targets L3', so nothing compares a
measured rate against a declared ambition."

There was a second, quieter defect underneath. `EscapeReport` carried a rate, a budget,
a reduction and a set of ceilings, and **nothing anywhere said what any of it was aiming
at**. A deployment could report L2 delivered, every oracle passed, the rate inside budget,
and no artefact in the product could answer whether L2 was the goal or a disappointment.

## Decision

**The target is a type, not a number in a config file.** `DeploymentScope` carries the
consumer, the target level, the tracking flag, who declared it and when. What makes it
worth a type is the refusal set: the two ways a declared target can be one this build
cannot honour are structural, and both are worth catching before a build rather than
after a delivery.

**A personal scope may not target L4.** FR-157 says the gate "must not be imposed as a
default" for D17's case, and the symmetric error is a deployment that grants itself the
level the gate exists to withhold — declaring the target *is* the gate imposed by the side
door, with the requirement's own remedy (measure it, or do not claim it) skipped.

**A third-party scope may not target L4 either, and the refusal is a different sentence.**
There the gate applies unchanged, so L4 is reachable *through* it — and `THETA_GATE_BUILT`
is `False`, so this build cannot decide it. The two refusals have different remedies: one
is "you are not aiming at the right band", the other is "the instrument that would admit
you is not built yet". A single message would send the second operator looking for a
setting. `L4_GATE_THETA` and `THETA_GATE_BUILT` are named constants for the same reason
`UNCOVERED_CLAUSE_CEILING` is separate from `MODE_G_CEILING` (ADR-0050): building
FR-024–FR-035 flips one boolean rather than rewriting a sentence in three places.

**The refusal is conditional on the flag, not unconditional with a self-check arm.** The
first draft raised unconditionally and carried a third branch whose message said "this
refusal is unreachable and is a defect in this validator". The test that flips the flag
caught it: an unconditional raise means the flag can never do the one thing its docstring
says it does, which makes it a comment with a type. The branch is a conjunction now.

**Escape-rate tracking is required of both consumers.** FR-157 names the rate beside the
personal band, but its argument is general — with no external market there is no
exogenous escape signal, so the rate is the only thing distinguishing an imagined product
from a plausible-looking one. A scope that declares a target and declines the instrument
is the target NFR-024 refuses: one the product has not measured.

**Absence is a state, not a default.** `EscapeReport.scope` is `None` when the deployment
declared none, and `meets_target` returns `None` — not `False` — when either the scope or
the delivery ceiling is missing. `False` would read as a *shortfall*, which is a claim
about a comparison that was never made. This is the vacuous-pass rule `EscapeReport`,
`OracleAuditReport`, `AttemptTelemetryReport` and `PluginComposition` already keep, at the
requirement that most invites breaking it: a product that supplied
`PERSONAL_AUTONOMY_BAND`'s floor as a default would be imposing the very gate D17 removed,
and a report would show a target nobody chose as though someone had.

**The shortfall is signed rather than clamped.** A deployment aiming at L2 whose delivery
sustains L3 has headroom, not a problem, and clamping at zero would erase the difference
between meeting a target exactly and exceeding it — the one thing a reader of the number
wants.

**The delivery ceiling arrives from the caller.** `meets_target` compares against
`DeliveryReport.autonomy`, read off the latest *report* rather than derived again here, so
the target and the rate cannot disagree about what was delivered. `measure_escapes` does
not compute it: `delivery.ceiling` does, from a contract and a decomposition this fold
does not hold, and a second derivation would be a second answer.

**The declaration is configuration, not code.** `load_deployment_scope` reads JSON through
the seam `load_envelope`, `load_escape_budget` and `load_composition` already provide, and
`SOFACT_SCOPE` names it. FR-156's rule reaches the declaration itself: a target that could
only be expressed by editing `src/` would be a capability obtained by code. One object
rather than a list, unlike the budgets — a deployment aims at *one* level, and a target
that is one of two numbers is a target nobody is aiming at. Unknown fields are refused
rather than ignored, because here a misspelled key would leave the target defaulting past
the validator's floor.

**The loader does not bypass the type.** A personal L4 written in JSON is refused with the
same sentence a Python caller gets, because the file is a way to declare a target and not
a way around the type.

## Consequences

- `sofact scope` reports the declared target, its band, and what it does not claim, and
  exits non-zero when none was declared — there is no default to fall back on, and a
  script has to be able to tell that from a configured deployment.
- `sofact escapes` gains a target block with three states, and exits non-zero on a
  shortfall. The middle state — a target declared and nothing delivered — is why the
  screen is not a boolean.
- A deployment that wants L4 must now say who consumes the artefact, and the answer
  decides which instrument is required rather than which number is typed.
- The third-party band runs to L4 *in principle* and to L3 *in this build*. `admits_l4`
  is the property that keeps those two statements apart, and the scope's caveats say
  which one applies.
- One limit, stated rather than papered over: the target is an **ambition**. It raises no
  ceiling, and what raises a ceiling is a stronger oracle. `scope.caveats` says so on
  every surface that prints the number.

## Evidence

- `tests/ci/test_scope.py` — 44 tests. Every refusal (personal L4, personal L1,
  third-party L4 while the gate is unbuilt, `escape_tracking=False`, and the flag flip
  that opens the band); `band`/`admits_l4`/`met_by`; `meets_target` returning `None` in
  both absence cases and the signed `target_shortfall`; every `load_deployment_scope`
  refusal; the `scope` verb and the `escapes` verb's target block, each with its exit code.
- Five canaries, each asserting its target string is present and unique before mutating,
  each watched failing and reverted from a file backup: the personal-band refusal (3
  failures), the third-party gate refusal (2), `meets_target`'s `None` guard (3), the
  third-party note's condition on `admits_l4` (1), and the CLI's non-zero exit on a
  shortfall (1).
- Full suite **1396 passed**, read from the log's own summary line; `uv run pyright` 0
  errors; `ruff check` and `ruff format --check` clean.
- One defect found outside FR-157 while writing its evidence, and fixed here because the
  unit is what surfaced it: `README.md` stated the suite's size and **nothing checked
  it**, so the figure had drifted 1282 to 1394. `tests/ci/test_docs.py` now asserts the
  stated count against what pytest itself collected, and declines to compare on a run
  that is not the whole suite (`-k`, `-m`, `--maxfail`, or a positional path narrower than
  `testpaths`) — a gate that failed on a filtered run would fail for a reason its operator
  cannot act on, which is how a check teaches people to bypass it.
