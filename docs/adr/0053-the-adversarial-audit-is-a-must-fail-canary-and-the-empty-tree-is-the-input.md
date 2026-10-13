# 0053 — The adversarial audit is a must-fail canary, and the empty tree is the input

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** FR-107, FR-004, FR-012, FR-108, FR-109, FR-103, FR-038;
  [ADR-0050](0050-coverage-is-a-conjunction-and-the-debt-and-the-cap-are-one-measure.md),
  [ADR-0022](0022-a-refutation-is-a-work-order.md)

## Context

FR-107: "Oracle manufacturing must be **adversarially audited** exactly as code is
(FR-012). A manufactured oracle that can be satisfied without implementing the invariant
is a worse defect than a missing test, because it manufactures false confidence."

The roadmap row read "Not built — no code", which was true and understated the problem.
The factory had the defect, and a probe demonstrated it rather than argued it: a contract
whose clause carried a rank-1 `PROPERTY` oracle with `command_hint="true"` reported

```
debt: 0.0     ceiling: L4     covers: True     verdict: satisfied
```

on an empty workspace. That is FR-107's own sentence — the strongest autonomy claim the
ladder offers, on a clause whose check establishes nothing. The gap and the defect were
different facts, and only the second is what the requirement is about.

## Decision

**The audit is FR-004's must-fail canary, and its known-bad input is the one input every
language has: an empty workspace.**

1. **The instrument is FR-004's, not an invention.** FR-004 requires every oracle to be
   "canary-tested each cycle: a known-good input that must pass, and a known-bad input
   (seeded mutant) that must fail". A seeded mutant needs the operator's language and a
   working toolchain, which SoFact does not have (ADR-0025). An empty tree needs neither,
   and it is the strictly harder case: an oracle satisfied by *nothing* would be satisfied
   by any mutant, so it cannot be a canary at all. The language-free input is what makes
   this requirement buildable now rather than blocked on D5 like FR-103 and FR-105.

2. **The measurement is a run, not a reading of the command.** An oracle that reports
   `SATISFIED` against an empty workspace was satisfied without implementing anything.
   Nothing here inspects the spelling of a command hint: `true` is caught because it was
   *run*, and a test that pattern-matched `command_hint` would be a gate a producer could
   satisfy by renaming — the defect wearing the gate's clothes.

3. **The judge is the real verifier.** `audit_oracles` produces observations with
   `OracleRunner` and judges them with `verification.verify`, exactly as P6 does.
   Re-deciding "was this satisfied?" inside the audit would be a second implementation of
   the one rule the factory is built on, and a manufactured *judge* is the same defect as
   a manufactured oracle one level up — it would report agreement with itself. The module
   imports both and a test asserts it does not compare an exit code itself.

4. **Only `SATISFIED` is the finding.** `VIOLATED` is the good case: the oracle *can*
   fail, which is what makes it an instrument. `INSUFFICIENT` — a timeout, a malformed
   observation — says the audit learned nothing, which is a different claim from "the
   oracle is satisfiable by nothing", and collapsing the two would report a finding against
   an oracle the audit never got an answer from.

5. **A clause the audit cannot ask about is reported, never passed.** Two skips, each with
   its reason stated on the report:
   - **Negative clauses.** An empty workspace satisfies an absence by containing nothing.
     A probe confirmed it: `! grep -rq password= .` reports `SATISFIED` on an empty tree.
     That is a *true* statement about an empty tree, not a weak oracle, and counting it
     would report a finding the operator cannot act on. This is a real limit of the
     instrument and the reason the skip list exists.
   - **Oracles naming no command.** Nothing to run. That is FR-108's ground-truth debt with
     its own remedy, and reporting it here would conflate two defects — the mistake
     `UnverifiedClause` already refuses one phase later.

6. **Nothing probed claims nothing.** `OracleAuditReport.discharged` returns `()` when
   `probed` is empty, so FR-107 lands in `not_implemented` — the rule
   `IntegrationCheck.discharged` states for P7, applied here. A contract of intentions has
   nothing to probe, and a screen showing only "no findings" would report a gap as a
   clearance. The CLI prints the requirement by name and does not print the green line.

7. **The audit is appended, never keyed.** `ProjectState.oracle_audits` is a tuple and
   `latest_oracle_audit(contract_id)` reads the most recent for one contract, for
   `gate_costs`'s reason: an audit is a measurement at a moment, so a second audit of a
   repaired oracle is a second measurement. The history is what FR-012's
   exploit-discovery-rate metric will read when FR-012 itself is built.

8. **It writes nothing into the state directory.** The oracles run in a fresh temporary
   directory removed on the way out; a test asserts the home is unchanged afterwards,
   because "we used a `TemporaryDirectory`" is a claim about code and FR-003's claim is
   about the filesystem.

## Consequences

**The finding is actionable, and it names the operator's own declaration.** It carries the
clause, the statement, the declared `OracleClass` and the command. The class is what makes
it judgeable: a rank-1 property oracle passing against nothing was claiming to establish an
invariant, while a rank-6 example passing there sampled nothing — both are findings and the
first is the one that grants autonomy.

**The audit is a P6-adjacent verb, not a gate.** `sofact audit` exits non-zero on a finding
so a script can gate on it, but no phase machine transition consults it. Wiring it into P4
or P8 would be a second autonomy computation beside `Contract.ceiling`, which is the drift
ADR-0050 removed.

**The instrument has a stated blind spot, and the report states it.** Negative clauses are
not asked about. A future audit that manufactures a positive counterpart — an empty tree
plus one file that *should* be absent — would extend the instrument; this ADR does not
claim it, and the skip reason says so rather than leaving a reader to infer it.

**FR-012–015 remain unbuilt, and this is not them.** FR-107 says the audit happens "exactly
as code is (FR-012)", and FR-012 is the hacker/fixer loop with sampling and a discovery
metric. What is built here is the *oracle-side* instrument — the thing FR-012's loop would
point at — not the loop. The roadmap keeps FR-012–015 as separate rows.

## Evidence

- `TestAnOracleThatCannotFailIsAFinding` (6), `TestTheAuditSaysWhatItCouldNotAsk` (7),
  `TestTheServiceRecordsTheAudit` (5) in `tests/ci/test_audit.py`; `TestTheAuditVerb` (5)
  in `tests/ci/test_cli.py`. Control arms throughout: a command that *can* fail produces no
  finding, and a probed pass claims FR-107 while an unprobed pass does not.
- Canaried three ways, each asserting its target string was present before mutating and
  reverted from a file backup: the finding rule inverted (8 fail), the negative-clause skip
  removed (4 fail), `discharged` forced to always claim (2 fail).
- `ruff check` and `ruff format --check` clean; `pyright` 0 errors; full `tests/ci`
  **1210 passed**.
