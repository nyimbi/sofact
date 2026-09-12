# 12. The harness adapter table is data, not code

* Status: Accepted
* Date: 2026-09-12
* Deciders: operator
* Supersedes: none
* Related: [ADR-0004](0004-delegate-the-coding-loop-to-an-external-harness.md), [ADR-0008](0008-the-model-is-advisory-only.md), [ADR-0009](0009-no-oracle-no-autonomy.md)

## Context

[ADR-0004](0004-delegate-the-coding-loop-to-an-external-harness.md) settled that the
coding loop is delegated to an external harness. The first implementation of that
delegation then put the harness definitions in `harness.py` as a module constant
(`SPECS`, two entries: `pi` and `dsh`) and the default harness in `service.py` as a
literal name (`DEFAULT_HARNESS = "pi"`).

That arrangement works for exactly one deployment, and it failed in three ways that
were observed rather than imagined:

1. **A new harness costs a code change.** Registering a third harness means editing
   `src/`, which is the thing a deployment of a released artifact cannot do.
2. **The hardcoded default bypassed the injected table.** `harness_name()` returned
   `DEFAULT_HARNESS` whenever no override was given, without consulting the table it
   had been handed. A deployment that registered only `dsh` therefore had its table
   silently ignored on every path that took the default — and it did not fail loudly,
   it failed as "that harness is not configured", naming the very harness it had
   configured.
3. **The seam was unreachable from outside.** The table was injectable from Python
   (`FactoryService(..., specs=...)`), but a deployment runs a binary. There was no
   configuration path, so the injectable table was reachable only by test code.

FR-155 (third-party admission is tested by deletion) and FR-156 (configuration beats
plugins) make the general form of this sharper: if adding a participant requires
editing SoFact, then SoFact is not a control plane, it is a program with a
configuration file bolted on.

The counter-pressure is real and is why this is a decision rather than an obvious
refactor. A table read from a file is *untrusted input*, and a harness spec decides
what process SoFact executes. A permissive parser would turn a typo into behaviour:
`"session_is_zstd": "false"` is a non-empty string and therefore truthy, so a
misspelled or misquoted key would produce a plausible, wrong reading rather than an
error. Every boolean field is therefore refused unless it is literally `true` or
`false`.

## Decision

**The harness adapter table is a data artifact, loaded and validated at the boundary.**

1. **Loading is a function, not a class hierarchy.** `load_specs(path) -> dict[str, HarnessSpec]`
   reads a JSON table. Two shapes are accepted: wrapped (`{"harnesses": {...}}`,
   unwrapped only when the top-level key set is exactly `{"harnesses"}`) and bare
   (`{name: {...}}`). In the bare form a harness may not be named `harnesses`.
2. **Validation refuses by name.** An unknown field, a missing required field, a
   wrong-typed value, a bare string where a sequence belongs, a non-object harness,
   a harness naming no `argv`, and a `completion_event` with no path to read it are
   all `ValueError`s naming both the harness and the field — `harness 'h':
   goal_event_types must be an array of strings`. Nothing is defaulted away and nothing
   is coerced.
3. **An empty table is not "unset".** `_configured_specs()` returns `None` when
   `SOFACT_HARNESS_SPECS` is unset, meaning *use the built-in table*. A table that is
   present but empty is refused, because it names no harness to run and is therefore a
   mistake rather than a request for defaults.
4. **Default resolution consults the table.** Explicit argument, then
   `SOFACT_HARNESS`, then `DEFAULT_HARNESS` **if the configured table contains it**,
   then the sole entry if the table has exactly one, then refuse. A table with two
   entries and no default is an error: picking one would dispatch to an arbitrary
   harness.
5. **Refusal names the alternatives.** An unknown harness raises with the configured
   set: `unknown harness 'x'; configured harnesses: dsh, pi`.

## Consequences

* Registering a harness is a deployment act: write a JSON file, set one environment
  variable. SoFact's own source is untouched, which is the property FR-155 tests for
  by deletion.
* The built-in `pi`/`dsh` table remains the fallback, so "unset" and "empty" stay
  distinguishable — and the same binary can be pointed at a harness SoFact has never
  heard of.
* The default harness is now a property of *the deployment's table* rather than of
  SoFact's source. That is the intended inversion, and it is why the resolution order
  had to be written down rather than inlined.
* Validation lives in `load_specs` (`ValueError`) while the invariants of a
  constructed spec stay as `__post_init__` assertions. The split is deliberate:
  untrusted input is validated, and internal construction is asserted. The important
  detail is that the loader **re-checks the constructor's invariants itself** rather
  than letting an assertion escape, so a plausible-but-inconsistent table cannot arrive
  as a traceback: `a completion_event needs a completion_reason_path to read` and
  `usage_reduce must be one of ['max', 'sum'], got 'mean'` are `ValueError`s from the
  loader, even though constructing the same `HarnessSpec` directly raises
  `AssertionError` (`tests/ci/test_harness.py:141`, `tests/ci/test_harness.py:145`).
* Tests gained the ability to dispatch to a **real** synthetic child process with no
  mocks — the project's standing rule — because a table can be injected. The seam is
  no longer test-only.

## Evidence

* `load_specs` at `harness.py:335`; the empty-table refusal at `harness.py:365`
  (`no harnesses; an empty table names no harness to run`); the field loops that drive
  deserialization at `harness.py:194`, `harness.py:197`, `harness.py:200`
  (`_TUPLE_FIELDS`, `_STRING_FIELDS`, `_BOOL_FIELDS`).
* Unknown-name refusal at `harness.py:247`, asserted by
  `test_unknown_harness_names_the_configured_set` (`tests/ci/test_harness.py:105`).
* Resolution order at `service.py:439` (`harness_name`); the sole-entry rule at
  `service.py:454`; the injectable seam at `service.py:121`
  (`SPECS if specs is None else dict(specs)`). Covered by
  `test_the_default_harness_when_nothing_is_set` (`tests/ci/test_service.py:175`),
  `test_an_explicit_harness_beats_the_environment` (`tests/ci/test_service.py:182`),
  `test_a_deployment_can_register_a_harness_without_patching_code`
  (`tests/ci/test_service.py:195`), `test_a_single_configured_harness_becomes_the_default`
  (`tests/ci/test_cli.py:221`), and `test_an_ambiguous_table_refuses_to_guess`
  (`tests/ci/test_cli.py:309`).
* The loader's refusal matrix is `TestLoadSpecs` (`tests/ci/test_cli.py:336`):
  round-trip of every field, both accepted shapes, malformed field refused by name,
  required field refused, unknown field refused, empty table refused, non-object
  refused.
* The CLI path is `_configured_specs()` (`cli.py:85`), reached through
  `SOFACT_HARNESS_SPECS`; a malformed file exits non-zero with
  `cannot read SOFACT_HARNESS_SPECS: …` (`cli.py:98`).
* The refusal surface was enumerated rather than assumed. Seven plausible-but-wrong
  tables — a `completion_event` with no reason path, an unknown `usage_reduce`, a bare
  string where a sequence belongs, `argv` as a string, an unknown field, a spec with no
  `argv`, and a boolean given as a string — each produced a `ValueError` naming the
  harness and the field, and none of them loaded. This matters because the CLI's
  `_configured_specs()` catches `ValueError` only: an `AssertionError` escaping the
  loader would have printed a traceback instead of a message.
* The documentation is under the same test: `TestTheDocumentedTable`
  (`tests/ci/test_cli.py:422`) extracts every JSON fence from `README.md` and loads it
  with the real `load_specs`, then checks that the documented `{goal}` and
  `{session_id}` placeholders are the ones the adapter fills. README.md's example was
  first checked by hand; this record converts that check into a permanent one, because
  a hand-checked example drifts.
