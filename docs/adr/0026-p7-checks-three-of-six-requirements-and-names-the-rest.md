# 0026 — P7 checks three of six requirements, and the report names the other three

- **Status:** Accepted
- **Date:** 2026-10-12
- **Amended by:** [ADR-0027](0027-a-declared-surface-is-diffed-in-both-directions-and-a-claim-is-not-a-discharge.md) — point 1's rule that `not_implemented` is the complement of what the checks **claim** is superseded: it is the complement of what they **discharge**. The failure it left open is a check that runs, claims a requirement, and exercises none of it — which is exactly the state FR-112's conformance check starts in. The rest of this record stands.
- **Related:** FR-111–116, FR-090, FR-092, FR-061, FR-113, FR-114, §10, §6.3, D2/D5; [ADR-0025](0025-the-decomposition-gate-has-two-halves-and-one-module-per-clause.md) (the cumulative-branch limitation this record's attribution works around)

## Context

§10 states six requirements for integration. Building them all was not the question; the
question was what "integrated" may be *said* to mean when three of the six have nothing to
run against.

The three that are reachable are reachable because SoFact already holds the inputs:

- **FR-111** — the build order. The dispatch log says which step produced work for which
  module, and FR-092 says which module must come first. Nothing has to be executed.
- **FR-113** — no module reaches another's internals. The seal records the files each
  step produced (FR-113's own substrate, added for this), so an import statement in those
  files is a reach that can be *read* rather than requested.
- **FR-114** — attribution. This is a property of the other two's output rather than a
  check of its own: it constrains the *shape* of a finding, not whether one exists.

The three that are not:

- **FR-112** requires an empty public-API diff. A diff needs two sides. `Module.interface`
  is deliberately prose (ADR-0025: SoFact does not know the operator's language), so there
  is no declared signature a machine can compare a built one against. Inventing the
  left-hand side would fabricate the contract P5 implements and P7 then certifies.
- **FR-115** requires the §6.3 system model. It does not exist as a type, and a check
  written against a model nobody maintains is a check against the author's memory of it.
- **FR-116** requires system-level acceptance criteria from P2 that no single module
  satisfies. The contract carries per-clause oracles and nothing at the system level, so
  there is no criterion to run.

## Decision

**The three reachable checks are built; the other three are named on every report.**

1. **`IntegrationReport.not_implemented` is derived from what the checks claim, not from a
   hand-kept list.** Each `IntegrationCheck` carries the `requirements` it discharges, and
   `not_implemented` is the complement of the union of those claims against
   `INTEGRATION_REQUIREMENTS`, which is §10's whole list. A check that stops running takes
   its requirement with it into `not_implemented` automatically; there is no second place
   to forget to update. The point is that a green report cannot be read as "P7 is done",
   because the same object that says "passed" says "FR-112, FR-115, FR-116 are not
   implemented".

2. **Attribution reads the seal, not the branch.** FR-113's analysis needs to know which
   files a module produced, and ADR-0025 measured that the branches are cumulative — a
   later module's branch contains every earlier module's files. Reading the branch tree
   would show every module containing every other module's code, and the check would report
   a violation for every import in the system. `ModuleCheckout.sealed_files` is per-step, so
   a module's files are the ones *its own* step sealed. This is why the seal records names
   and not only a count.

3. **A step that names no module contributes its files to nobody, and that is reported.**
   The bootstrap step in a real run is exactly this case, and it is where the producer's
   first file lands. Attributing it to a module would be a guess; the consequence of not
   attributing it is that an import of it is an `UNATTRIBUTED_FILE` finding, and that the
   file appears in the check's `uncovered` list. Both are visible.

4. **The analysis is shallow and says how shallow.** It reads `import x` and
   `from x import y`, resolves absolute names against the produced files, tries both
   `pkg/mod.py` and `pkg/mod/__init__.py`, and stops. It does not resolve relative imports
   (that needs the package root and the producer's layout, and guessing produces findings
   about the wrong file), does not see `importlib.import_module`, and does not parse a
   non-Python file. Each of those is written into the check's `uncovered` tuple rather than
   left for a reader to discover.

5. **A stdlib import is not a finding, and the narrowing is deliberate.** The first version
   reported every import that resolved to no produced file, which made `import json` an
   `UNATTRIBUTED_FILE` finding — a check that fires on every module with a dependency, which
   is a check its operator disables within a day. It now fires only when the import reaches
   *into a package some module produced* without naming a file any module sealed, which is
   the case where attribution is genuinely missing rather than where the import is
   third-party.

6. **Integration requires an approved decomposition, like planning does (FR-061).** Without
   a module graph there is nothing for a reach to be a violation *of*, so
   `check_integration` calls `require_approved_decomposition` rather than degrading to a
   report over no modules.

## Consequences

- **FR-114 is discharged by the import check, and the report says so.** The minimum
  violating set is a property of every finding (`modules`), and
  `IntegrationReport.violating_modules` is their union. A platform-wide rebuild is refused
  by construction: nothing in `integrate` can produce a scope wider than the findings name,
  because the scope *is* the findings. The test asserts the scope is a strict subset of the
  plan's modules, which is the shape a wider scope would break.
- **A producer that writes during bootstrap is attributed to no module, and P7 is honest
  about it rather than silent.** Measured over a real run: the synthetic producer writes its
  file during step 0, which is the bootstrap tier and covers no clause, so `modules_built`
  is empty and the file is named in `uncovered`. This is a property of *when* the producer
  writes rather than a defect in the check — but it does mean `modules_built` being empty is
  not by itself evidence that nothing was built, and the report distinguishes the two by
  naming the orphan.
- **FR-111 is checked against the decomposition's topological order, not the plan's step
  ordinals.** FR-136 lets a module's work span several steps and the compiler interleaves
  tiers, so the step order is not the module order. Reading one as the other would report a
  violation whenever the compiler's tiers disagreed with the DAG.
- **An unbuilt dependency of an unbuilt dependent is not a finding.** A plan not yet
  finished is a different fact from a dependency violated. Reporting the former as the
  latter fails integration on every partial run, which is how a check teaches its operator
  to ignore it.
- **`check_imports` takes `sources` as well as `root`.** The analysis is over bytes, and
  making every test materialise a repository to exercise a parser would test git rather
  than the check. `integrate` reads from disk in production and the tests supply text.
- **The three unimplemented requirements are real debt and are recorded as such.** This
  record does not schedule them. FR-112 is blocked on a machine-readable interface, which is
  a decision about the implementation language that D2/D5 made and ADR-0025 recorded as out
  of the decomposition's scope; FR-115 is blocked on the system model existing; FR-116 is
  blocked on P2 producing criteria at the system level.

## Alternatives refused

- **Report only the checks that ran.** Refused: it is the failure this record exists to
  prevent. A report whose green line means "of the checks I chose to run, all passed" is
  indistinguishable from one whose green line means "the system integrates", and the
  operator cannot tell which they are reading.
- **Gate on the unimplemented three as `False`.** Refused: a check that fails because it was
  never written makes every integration red for a reason its operator cannot act on, and the
  pressure that creates is to stop running integration at all — the same failure mode the
  tone gate and the dirty check each produced.
- **Infer a machine-readable interface from the clause text.** Refused: that is fabricating
  the contract, and FR-090's whole point is that the permitted surface is *declared* before
  the module exists. A guess presented as a declaration is worse than an admitted gap.
- **Attribute files by branch.** Refused and measured: the branches are cumulative
  (ADR-0025), so every module would appear to own every earlier module's files and FR-113
  would report a violation for essentially every import.

## Evidence

22 tests in `tests/ci/test_integration.py`, plus the fold and field-count changes in
`tests/ci/test_state.py`.

Both implemented gates were **canaried by watching them fail**, each reverted from a file
backup rather than `git checkout`:

- With FR-113's declared-edge check blinded (`if True: continue`), four tests failed, among
  them `test_a_module_reaching_another_without_declaring_it_is_a_finding`.
- With FR-111's order comparison blinded (`if False:`), one test failed,
  `test_a_module_built_before_its_dependency_is_a_finding`.
- With `require_approved_decomposition` replaced by a direct log read, the FR-061 refusal
  test failed.

The FR-111 canary was **run twice**: the first attempt wrote `if False: pass elif ...`,
which still evaluates the `elif`, so the check was never blinded and the suite exited `0`.
That zero was a bug in the canary, not evidence about the gate — the same shape as a passing
canary that is really a canary that did not run.

`test_the_report_names_every_requirement_it_did_not_discharge` asserts the tuple
*exactly*, so a check that stops claiming FR-114 fails a test rather than quietly widening
the unimplemented list, and a requirement that gets implemented cannot be left in it.
