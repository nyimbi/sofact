# 0061 — Manufacturing earns the hint, and the strength number is withheld below its floor

- **Status:** Accepted (resolves D2 and D5)
- **Date:** 2026-10-14
- **Related:** FR-103, FR-105, FR-106, FR-107, FR-108, FR-118, FR-156, NFR-024, D2, D5;
  [ADR-0005](0005-no-container-runtime.md),
  [ADR-0040](0040-a-delivery-report-states-five-things-and-its-gate-is-human.md),
  [ADR-0050](0050-coverage-is-a-conjunction-and-the-debt-and-the-cap-are-one-measure.md),
  [ADR-0052](0052-a-holdout-is-a-property-of-the-oracle-class-and-it-holds-at-every-door.md),
  [ADR-0054](0054-the-escape-rate-is-the-one-number-no-producer-authored.md),
  [ADR-0060](0060-the-boundary-is-measured-and-the-ceiling-follows-the-measurement.md)

## Context

D5 left the target language open and D2 left the runtime open, and between them they held
five requirement rows at zero: FR-103's seven oracle ranks, FR-105's strength measurement,
FR-106's holdout half, FR-008–011 and FR-036. Each of those rows was blocked on the same
question — *what does a manufactured oracle get written in?* — and none of them could be
answered while the answer was "whichever language the operator picks".

Two invariants were already in force and neither could be relaxed to unblock them.

The first is `contract.py:46-72`:

> Suggestions never invent a command. A fabricated `command_hint` would be a lie that
> `sofact.execution` would later faithfully execute.

`suggest_oracle` keeps that by **abstaining** — a clause whose statement is English prose
gets a declaration with no command, and FR-108's ground-truth debt is the measure of how
much of a contract that is. Abstention is honest and it is also the ceiling: a factory
that only ever abstains manufactures nothing.

The second is FR-106's holdout. `held_out` is exactly `oracle_class is OracleClass.EXAMPLE`
and ADR-0052 established that the holdout is a property of the oracle *class*, holding at
every door. A manufacturing subsystem is a new door.

## Decision

### D2 — Python, and the other languages are registered beside it, not behind a flag

The factory builds in Python by default. `MANUFACTURE_SPECS` names `python`, `typescript`
and `rust`, and each is a `ManufactureSpec` — a frozen dataclass read the way a
`HarnessSpec` is read, with `from_mapping` refusing unknown fields **by name** and an
unknown `backend` refused by name rather than falling back to Python. `SOFACT_MANUFACTURE`
replaces the table wholesale, which is what makes D5's ruling *data* rather than a branch:
a deployment that wants a fourth language describes it in a file.

A silent fallback is the failure this rules out. A TypeScript module judged by a Python
check would produce an artefact that exists, a command that runs, a non-zero exit, and a
report attributing all of that to the module.

### The hint is earned at the seam, and a backend cannot skip the earning

`ManufactureBackend` has three members and no more: `language`, `supports(oracle_class)`
and `manufacture(request)`. A backend returns a `path` and an `argv`; it does not run its
artefact and it does not decide whether the run meant anything. `ConfiguredManufactureAdapter`
does both, once, for every language — the `ConfiguredHarnessAdapter` rule, because the gate
is the half that must not vary by language.

Four assertions run before a declaration is built, cheapest-falsifying first:

1. the artefact resolves **inside** the module workspace (else the producer could rewrite
   the check that judges it, FR-059);
2. the argv's artefact element *is* that path — an index, not a convention, because only
   the command can say which element names the file;
3. the file exists;
4. the command runs and terminates.

Then the fifth step, which is not an assertion but a measurement: **the same argv is
re-run against a directory holding the artefact and nothing else**, mirrored at the same
relative path. A non-zero exit is the pass. Exit zero means the check is satisfied without
the module existing, and FR-107's own words are that this is worse than a missing test — so
`VACUOUS` is a refusal and the artefact never reaches a contract.

The audit is the *same command* in a *tree the factory did not choose to be empty*. A check
re-written for the audit would be audited as a different check; a tree that happened to be
empty would be the instrument measuring its own choice. The artefact is copied byte-for-byte
into a `TemporaryDirectory` and the argv is passed unchanged.

### Rank 6 is refused before any backend is consulted

The `EXAMPLE` check is the first statement of `ConfiguredManufactureAdapter.manufacture`,
above the `supports` call and above the backend. The door is closed at the seam rather than
in each backend because a backend is the part a deployment replaces: a third-party backend
able to return a held-out oracle would re-open FR-106, and the operator would have no way to
see that it had.

### Manufacturing is complete where the factory's own data is structured, and refuses where it is prose

A clause's only content is an English `statement`, and deriving a *predicate* from English is
fabrication rather than manufacturing. The one machine-readable signature source a proposal
carries is `Module.surface` — a name, a kind and an arity per member, derived from the model
by ADR-0049. So the Python backend builds three ranks and refuses four:

| Rank | Class | Built as | Why |
| ----- | ----- | -------- | --- |
| 3 | `CONTRACT` | every declared member present with its declared arity | generated, so complete by construction — and a stub passes, which is exactly why rank 3 is covering and not strong |
| 1 | `PROPERTY` | nothing public in the module is undeclared | the shape a *negative* clause takes; the domain is the module's own public names |
| 5 | `SCHEMA` | the same completeness check against the **model's** interface | FR-083 makes the model the declaration site, so a disagreement between the two is the integration defect, visible before P7 |
| 2, 4, 6, 7 | — | refused by name | a transition relation, a metamorphic relation, an operator example and a reference run are all things the contract does not carry |

TypeScript builds ranks 3 and 5, Rust builds rank 3. Both refuse rank 1 in their own words:
a property test without a generator is a test with a handful of examples wearing a stronger
rank's name.

Every artefact exits **non-zero when it has nothing to quantify over** — no module, two
candidates, an empty declaration. `verification._command_output` judges a non-zero exit as
`VIOLATED`, so a check that found nothing to check fails loudly instead of passing vacuously.
An empty surface is refused at the seam too (`NO_DECLARED_SURFACE`), because manufacturing
against it would produce a check whose domain is empty and which an empty tree satisfies.

A module whose only oracle is manufactured stays at `UNCOVERED_CLAUSE_CEILING = L2`. That is
the subsystem telling the truth about what it can build.

### The strength number is a lower bound, and it is withheld below a floor

FR-118 asks the report to state "by which oracle at which **measured** strength".
`VerifiedClause.measured_strength` has carried the field since it was written and no code
path ever set it, so every report has said "declared rank N, not measured" — the honest
sentence, and the whole gap.

`mutation.py` closes it with a kill rate over a **named, closed** operator set of
`ast.NodeTransformer`s: comparison swap, boolean negate, return-none, constant off-by-one,
statement delete. There is no `mutmut` and no `cosmic-ray` here — the dependency set is
exactly httpx, pydantic, typer and uuid6 — and a closed set is not a compromise but the
instrument: a kill rate is a statement about *which* mutants were killed, and an operator
set that could grow at run time would make two numbers incomparable without saying so.

Three verdicts, and they are not a scale:

- **killed** — the suite's verdict flipped pass→fail. The only evidentiary outcome.
- **discarded** — the mutant did not compile, or the module did not import. It never ran, so
  it says nothing about the suite, and counting it as killed would let a syntax error raise
  the score.
- **timed out** — counted separately, never as killed, and **kept in the denominator**. It
  was offered to the suite and no verdict came back, which is a hole in the measurement;
  removing it would report a rate over the subset the suite happened to finish, and that
  subset is chosen by nothing but speed.

`kill_rate = killed / (total - discarded)`, with the raw counts kept beside it so a reader can
recompute rather than trust.

**The number is `None` below `MINIMUM_MUTANTS_FOR_A_NUMBER = 5`**, with a named
`StrengthRefusal`: `NO_SUITE`, `NO_MODULE`, `MODULE_DID_NOT_IMPORT`, `NO_MUTANTS`,
`BELOW_THE_FLOOR`. Three mutants killed is 1.000 and means nothing. Equivalent mutants are
never killed and stdlib cannot decide equivalence, so the rate is bounded above by what the
operator set can express — it is a lower bound, never a statement about the code's true test
quality. `measured` and `measured_strength` are two fields rather than one number precisely
because **zero is a result and `None` is the absence of one**.

`THETA_GATE_BUILT` stays `False` and `L4_GATE_THETA` is not consulted. The number is
recorded and rendered, never a gate input — raising that is a separate decision this change
does not take.

### Measurement is opt-in at the render, because it launches processes

`render_delivery(..., measured_strength: bool = False)`. It is the only input to a render
that runs a process per mutant, and a caller that did not ask must not pay for one. The CLI
carries `--measured-strength` and, when the flag was passed and nothing scored, says so on
the line that would otherwise print nothing.

The measurement runs **once, outside the two-round fixed-point loop** ADR-0044 established.
Inside it, a render that disagreed with disk would re-run the whole engine, and the cost
would be paid for a reason that has nothing to do with the number.

## Evidence

- **The ownership half was measured, not assumed.** `_measured_strengths` reads FR-088's
  traceability from the **seal** (`integration.attribute_files`), so a clause is measured
  against the file its own module sealed. The first synthetic fixture wrote one fixed
  `produced.py` on the bootstrap step, so `attribute_files` returned `({}, ('produced.py',))`
  and the measurement correctly returned `{}` — a fixture that could not tell one module's
  measurement from another's. The fixture now names its file after the module its branch
  names.
- **`git` cannot run inside the dispatch's boundary, and that was measured.** Under the
  Seatbelt profile the dispatch runs in, `git` fails outright with `fatal: Invalid path
  '<home>': Operation not permitted` — it canonicalises its repository root by walking up,
  and the profile denies reads above the workspace. `git branch --show-current` answers the
  **empty string** on the first step, whose branch is unborn. Reading `.git/HEAD` directly
  works under the same profile and names the ref whether or not it has a commit yet.
- **The number is a measurement rather than a constant.** With a discriminating oracle the
  contract-rank clauses score `0.80`; with `true` — which exits 0 whatever the module says —
  they score `0.00`; the rank-1 property clauses whose modules never ran render
  `declared rank 1, not measured`.
- **The floor is load-bearing and was hit in testing.** A canary that patched the
  no-targets skip to point at a file with one integer literal changed nothing observable,
  because that file yields fewer than five mutants and the rate was withheld. The canary only
  fired when pointed at a file with enough surface to clear the floor — which is the
  behaviour the floor exists for, observed rather than asserted.

## Consequences

- **`command_hint` is now sometimes a manufactured string, and the invariant survives
  because it is earned.** The command reaches a declaration only after the artefact exists at
  the path the command names and has run once and has failed against an empty tree. What
  changes is not the invariant but the number of clauses it is kept for.
- **FR-108's debt becomes measurable per refusal.** Every `ManufactureRefusal` names its
  clause, its rank and its reason, and rides in the `CONTRACT_CREATED` payload under
  `manufacture_refusals` — no new `LedgerKind`, because a refusal is a fact about a contract
  rather than an event in the pipeline. The fold ignores the key. A reader holding only the
  debt knows something could not be built and not what, and re-running manufacturing to find
  out would rewrite files to answer a question about a past state.
- **A manufactured oracle must fail against an empty workspace, and FR-107's audit will
  probe it there.** `audit_oracles` probes oracles that have a command and are POSITIVE, so a
  manufactured check *will* be run against a tree with no module in it. It fails there by
  construction — `ast.parse` on a missing module raises — and that is a required test rather
  than a happy accident.
- **The artefact is written before the first dispatch, not after.** `dispatch_step` places
  the artefacts in the module's worktree between `ensure_module_worktree` and the dispatch,
  because `OracleRunner` runs with `cwd=self.workspace`, the seal commits the oracle onto the
  module's branch so it travels with the module, and `digest_tree` is FR-006's cache key — so
  writing before the first dispatch is what keeps the key stable.
- **A build product is removed and the removal is named.** `rustc` writes `.rmeta` beside its
  `-o` target and `-o /dev/null` fails with "couldn't create a temp dir", so the path is named
  at manufacture time and deleted afterwards. A compiled binary inside the workspace would be
  committed by the seal and folded into the cache key, and a digest that moved because of one
  would invalidate a verdict nothing touched. The sidecars go by **prefix**, because `rustc`
  names them `<output><random>`.
- **FR-156 is kept by construction.** The backend name is not written to the ledger; the
  artefact's `path` and `command_hint` already carry the language as data about an artefact
  rather than as policy.
- **The measurement reads the module's own `.py` file only.** `_measured_strengths` filters
  the owning module's sealed files to `.py`, because the engine is an `ast` engine. A
  TypeScript or Rust module scores no number yet, and the report says "not measured" rather
  than reporting a Python mutation rate over a file it did not read.

## What this does not do

- **Rank 2 and rank 4 are not built.** A state machine needs a declared transition relation
  and a metamorphic oracle needs a declared relation between two runs; the contract carries
  neither, and inventing one would be the fabrication this record exists to refuse. Both are
  refused by name.
- **The kill rate does not gate anything.** `THETA_GATE_BUILT` is `False` and
  `L4_GATE_THETA` is not consulted. FR-024–035's routing function and the θ gate remain
  unbuilt, and nothing here may be read as passing one.
- **Ranks 1 and 2 above L2 are still not mandatory in practice.** FR-104 read literally would
  make §14's own class table unreachable; ADR-0050 records the conflict rather than resolving
  it with a second wrong answer, and manufacturing does not change it.
