# 0056 — The freeze is derived from the argv, and the deletion test is what admits a plugin

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** FR-154, FR-155, FR-156; FR-140, FR-141, FR-146, FR-152, R28, R29, D9, D15,
  D16; [ADR-0033](0033-a-worktree-is-per-module-and-a-wave-is-isolated-only-when-every-step-has-one.md),
  [ADR-0053](0053-the-adversarial-audit-is-a-must-fail-canary-and-the-empty-tree-is-the-input.md)

## Context

FR-154, FR-155 and FR-156 are one mechanism written as three requirements, and the roadmap
recorded them apart: FR-154 **Partly**, FR-155 **Not built**, FR-156 **Implemented**. The
split is the defect. A deletion test with no frozen composition to admit into is a rule
nothing consults, and a freeze with no admission test pins whatever happened to be
installed — so "FR-156 is implemented" was true and meant only that the product had not
installed anything yet.

The hazard §8.7 names is structural rather than hygienic. The `dsh` plugin set is mutable
**at runtime by the agent** ([S22]: `memorax-ai/dsh-harmony` patches and replaces plugins
at runtime, `dsh-super-injector` hot-injects packages into a running instance,
`swaylq/dsh-genie` promotes a dynamic package to a permanent bundle,
`green-dalii/dsh-plugin-dev-skill` teaches an agent to author plugins to spec). An
in-process verifier is reachable by the party it verifies. R29 is that fact as a risk; R28
is the ordinary supply-chain risk beside it, whose third failure mode is
**licence-incompatible**.

§8.7 answers the plugin question with a worked table over the measured ecosystem, and the
table is the decision procedure. It reaches four distinct verdicts, not the two a
refuse/admit pair would give: *Refuse as oracle*, *Refuse as authority*, *Refuse*,
**Refuse; built here instead** (`dsh-git-worktree`), *Refuse in favour of configuration*
(`030611/dsh-telemetry-redactor`), *Refuse as boundary*, *Refuse; study as prior art*
(`LongHorizon-Harness`), and **Admissible** (`upstream-radar`) — one plugin out of eight
rows.

## Decision

**The freeze has two independent halves, and it is derived rather than declared.** A
composition is frozen when the harness's own `argv` refuses to auto-load installed plugins
(`pi`'s `--no-extensions`), or when the plugins are enumerated and pinned by digest. Either
is sufficient; neither is a substitute for the other. `HarnessSpec.freezing_flags` names
the flags that constitute the first half and `HarnessSpec.composition_frozen` computes
whether the spec's `argv` actually carries them — so a spec cannot assert a freeze its
command line does not enforce. `pi-research` is the proof case: it carries the same flag
list through and drops the flag from its `argv` because the research loop *is* an installed
extension, and it computes not-frozen without anyone declaring it.

**A harness whose argv does not freeze reports FR-154 as not carried out, and that is the
honest reading.** `dsh` is unfrozen today and no flag in `DSH_SPEC` changes that. A
composition that reported a clean freeze there would be a declaration drifting from the
thing it describes, which is this project's recurring defect.

**`PluginAdmission` carries the surfaces SoFact still decides without the plugin**, and
refuses the rows that do not mean what they say. FR-155's five surfaces are
`completion`, `contract_integrity`, `oracle_strength`, `budget`, `egress`. An `ADMISSIBLE`
verdict with a surface missing is refused — it would admit a plugin that took over a
decision, which is precisely the class §8.7 says looks like the biggest saving. A `REFUSED`
verdict with every surface held is refused — that is a refusal with no defect behind it. A
surface outside FR-155's five is refused, because it would answer a question the
requirement does not ask.

**Four verdicts, because §8.7 reaches four.** `BUILT_HERE` is distinct from `SUPERSEDED`:
the first is SoFact's own code replacing the plugin, the second is FR-156's configuration
remedy. Folding them would record a plugin as replaced by a setting when what replaced it
was code, and the next reader would go looking for the setting.

**A licence is required exactly on an admitted plugin.** R28's third failure mode is
licence-incompatible, and a licence discovered after installation is discovered too late.
A plugin that is not installed has no licence to record, and carrying one would read as an
admission with an odd verdict.

**`argv_frozen` is in the composition hash.** Two builds can pin the same plugins and
differ in whether the harness was *also* told not to auto-load; a hash over the pins alone
would call those two compositions the same. The admissions are in the hash for the same
reason: a plugin re-classified under a later reading of FR-155 changes what the build's
trust boundary was, and the freeze exists so a build can be shown to have run the
composition it was approved with.

**The composition is configuration, not code.** `load_composition` reads a JSON file
through the seam `load_specs` and `load_escape_budget` already provide, and
`SOFACT_COMPOSITION` names it. FR-156's rule reaches the declaration itself: a composition
that could only be expressed by editing `src/` would be a capability obtained by code. The
file cannot declare `argv_frozen` — that is read from the harness spec — and it cannot name
a harness this deployment does not register, because the freeze is derived from that
harness's spec and a body naming an unregistered one would have nothing behind the read.

**The vacuous case reports, and FR-156 is its floor.** A composition that considered no
plugin has applied the deletion test to nothing, so `discharged` leaves FR-155 open rather
than printing a clean filter that filtered nothing. An unfrozen composition leaves FR-154
open even when it has admissions, because the admission rows describe a list the argv does
not enforce. FR-156 is the one requirement that applies either way — an empty, unfrozen
composition *is* the configuration-only answer — so it is the floor this returns and never
the whole set by default. `sofact composition` exits non-zero while any row is open.

**What is not automated, and cannot be.** Whether deleting a plugin changes SoFact's
completion verdict is a question about a running system. A function that answered it from a
table would be asserting the very thing it claims to check, which is the manufactured-judge
defect ADR-0053 refuses one level down. What this builds is the form the answer is written
in, and the type is what stops one being written down wrong. §8.7's table is the corpus the
tests transcribe, and the transcription is the only check that the four verdicts are the
right four.

## Consequences

- `pi` runs frozen; `dsh`, `claude` and `opencode` do not, and `sofact composition` says so
  with a non-zero exit rather than a clean table. Making `dsh` frozen requires either a
  flag that refuses plugin auto-load or a pinned enumeration — a deployment decision, not a
  code change.
- Every P5 session's `DispatchRecord` now carries `composition_hash`, so a stored build can
  be tied to the composition it ran under (FR-149, R29). The hash is over what was frozen,
  not when it was frozen, so two builds with the same freeze agree.
- A deployment that installs a plugin must now write down the verdict, the surfaces held
  without it, and the licence — in a file, before the build. The cost is real and it is the
  point: the alternative is a plugin set that changed without a record of why.
- `verify_composition` reports a plugin present in the pins and absent from the observed
  set, because an uninstalled member is as much a change as an altered one.
- One limit, stated rather than papered over: nothing here reads the filesystem, so
  `--verify NAME=DIGEST` is only as good as what the caller passes. The freeze detects a
  composition that moved; it does not discover what is installed.

## Evidence

- `tests/ci/test_composition.py` — 48 tests. §8.7's eight-row table transcribes through the
  real loader (`frozen True minimal True`, one admitted, five refused, one superseded, one
  built here, all three requirements discharged); the `pi`-vs-`pi-research` freeze asymmetry
  computes from the argv; every type and loader refusal; the vacuous case; `verify_composition`
  drift and absence; the CLI verb's non-zero exits.
- Five canaries, each watched failing and reverted from a file backup: the `discharged`
  vacuous-pass guard (4 failures), the `frozen` property (5), `verify_composition`'s drift
  filter (3), the CLI's non-zero exit (2), and the loader's missing-surfaces refusal (1).
- Empirical, on the five registered specs: `pi frozen=True`, `pi-research frozen=False`,
  `dsh frozen=False`, `claude frozen=False`, `opencode frozen=False`.
- Full suite 1350 passed; `uv run pyright` 0 errors; `ruff check` and `ruff format --check`
  clean.
