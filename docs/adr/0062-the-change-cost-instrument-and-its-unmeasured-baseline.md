# 0062 — The change-cost instrument is built, and its baseline is unmeasured

- **Status:** Accepted (resolves D18)
- **Date:** 2026-10-14
- **Related:** FR-158, FR-159, FR-160, NFR-024, D18, ADR-0054, ADR-0011, ADR-0061

## Context

FR-158 makes two things structural. The **evolvability debt is 1.0 for every module by
construction**, and **Mode M is capped at L1**, because no oracle in O1–O8 observes what a
change costs. That is the honest state of a factory whose whole claim is that it verifies
rather than asserts, and FR-158's own text says the value "is the correct value rather than
a measurement failure".

D18 asked whether it must be the permanent one:

> **Adopt a change-amplification instrument (FR-159), or declare the entire evolvability
> class out of scope?** … This is the one place [S24] leaves SoFact a path that needs no
> new model capability, so it is the highest-value cheap decision open. … **Adopt — but
> only after M0.**

The recommendation is *adopt*, and the condition is *after M0*. Two things are therefore
true at once and both matter: the decision is made, and the condition attached to it has
not been met. A record that reported "D18 resolved, instrument built" without the second
half would be the exact over-claim FR-159's own text warns against — it says the boundaries
are "stated because over-claiming here would repeat the error being corrected".

**What FR-159 specifies, in its own words.** "For a pinned set of change units held out
from the producer, record the mechanical diff footprint per unit (files touched, hunks,
lines changed, modules crossed) and track it across the codebase's history. A rising
footprint on comparable change units is Fowler's shotgun surgery observed rather than
asserted." Its boundaries are equally explicit: it "is a **proxy** (NFR-024 applies, and it
must be declared as one); it measures change *cost*, not design *quality* … and it is
admissible only as a **trend alarm** and a Mode M ceiling input, never as a verdict."

**ADR-0054 is the precedent, and it is exact.** The escape instrument was built, its
mechanism became real, and its **baseline** was reported as *unmeasured* rather than clean,
because a rate needs a deployment and §20.3 item 4 records that none exists until there has
been one. FR-159's baseline needs a codebase history the same way.

## Decision

### The instrument is built to the shape the spec gives it

`sofact.changecost` measures, per pinned unit, the mechanical diff footprint of
`base..head` read from git: files touched, hunks, lines added and removed, modules crossed.
`sofact.git` gains `diff_footprint`, because that module is the one place SoFact touches
git and a second path to `git diff` would be a second place for the arguments to drift.

Three details are load-bearing and each was **measured** against a real repository rather
than reasoned about (2026-10-15):

- **A rename is one file, and the tell is the empty *path*, not empty counts.** `--numstat
  -z` writes a rename as `0\t0\t` followed by an empty path field, then the old and new
  names as their own NUL-separated fields. A reader keyed on the counts treats the rename
  as an ordinary file with no name: it gets the file count right *by luck* — the two bare
  name fields are skipped by the field-count guard — while filing the rename under a module
  called `""`. Canaried: with the rename's own package also carrying an ordinary edit, the
  counts-keyed reader reports two modules where there is one, and the test fails.
- **A binary path is named, not zeroed.** `--numstat` reports `-` for both counts on a
  binary file, and reading that as zero would let a unit that added a 40 MB artefact report
  the footprint of a comment.
- **Modules crossed is the package, not the layout.** `src/sofact/git.py` and
  `src/sofact/views.py` are one module; a reader taking the first path segment would call
  both `src` and count every change to the tree as crossing one module.

### The unit is pinned before the work

`pin_unit` is a function rather than a constructor call at the measurement site, and the
`base_commit`/`head_commit` are stored as **shas** rather than defaulting to `HEAD`. FR-159
says the units are "held out from the producer": a unit declared after its diff is a unit
whose scope was chosen to make the diff look comparable, and a unit that read `HEAD` at
measurement time would measure whatever had landed since.

### The comparison is per declared scope, and the baseline is earlier units only

Two units are comparable when they **declared** the same scope. A grouping derived from the
diff would put every unit in a group of its own — a trend over one point — and a trend line
pooled over all units moves when the *mix* of work changes, so a quarter of small fixes
would read as an improvement whether or not anything got cheaper to change.

The baseline is the **median of the scope's earlier units, in declaration order**. Earlier,
because a baseline including the unit itself would move with the unit it is judging: a large
change would raise its own bar and shrink its own ratio, which is the measurement quietly
excusing the thing it was built to notice. Median rather than mean, so one pathological unit
does not set the bar for its scope.

### The baseline is reported unmeasured, and that is the point

A scope with fewer than two measured units has **no trend**, and the report says so by
name. `ChangeCostRow.measured` is `False` for a unit with no recorded range, and
`unmeasured_because` names why — a unit with no range, a repository that is not there, or a
diff that could not be read. `ChangeCostReport.discharged` returns `()` when no scope has
two units, which is NFR-024 discharged by refusal rather than by a number.

This is ADR-0054's shape applied to the second instrument that needs a history: **"no trend
observed" and "not enough history to observe one" are different statements and must not
print the same line.**

### The instrument is wired, because one that only its own tests can reach is not built

The declaration is a file named by ``SOFACT_CHANGE_UNITS`` (``load_change_units``, refused
by name when malformed), the measurement is ``sofact deliver --change-cost``, and the trend
is printed beside FR-158's debt with its three caveats. Two of the loader's refusals are
load-bearing rather than tidy: ``id`` and ``declared_at`` are **refused** rather than read,
because a file that could set ``declared_at`` could backdate a unit into an earlier
baseline, which is the comparison chosen by the thing being compared; and an unknown field
is refused by name, because a misspelled ``base_commit`` would otherwise load as a unit with
no range — which measures as *unmeasured* and reads as work that has not landed.

The refusal fires at **service construction** rather than at the render, so a malformed
declaration stops every verb. That is deliberate and is the sibling readers' behaviour: a
refusal that only fired when the instrument was asked for would let an operator run a whole
pipeline against a declaration the factory could not read.

### The two constants do not move

`EVOLVABILITY_DEBT` stays `1.0` and `MODE_M_CEILING` stays `L1`. The delivery report gains
a `change_cost` field, and **nothing in the render reads it**: FR-159 is admissible as a
Mode M ceiling *input*, and the input is read by a human deciding D18's question, not by a
report deciding it for them.

`MAINTAINABILITY_NOT_VERIFIED` is **extended and not softened**. It gains a clause naming
the instrument and its proxy status, and its first sentence is still "Maintainability was
not verified." That edit is the one this record exists to constrain: an instrument landing
is precisely the event that tempts a report to promote its own proxy, and the failure mode
is not a report that omits the sentence — it is a report that says something adjacent and
flattering.

## Evidence

Measured on 2026-10-14/15 against this host and a real repository:

1. `git diff --numstat -z HEAD~1..HEAD` for a rename plus an ordinary edit in the same
   package returns `'1\t0\tother/two.py\x000\t0\t\x00src/pkg/one.py\x00src/pkg/renamed.py\x00'`
   — the counts are present and zero, the path is empty, the names follow. A reader keyed
   on `left == "" and right == ""` never enters the rename branch.
2. The rename gate canaries: with the counts-keyed reader in place,
   `test_a_rename_is_one_file_and_no_lines` **fails** (two modules where there is one).
   Reverted from a file backup; `cmp -s` confirmed byte-identical.
3. Four further gates canaried and watched failing: the earlier-units-only baseline, the
   rise predicate, the binary-path branch, and the unreadable-range branch.
4. `uv run pyright` over the tree: 0 errors, 0 warnings, 0 informations.
5. Three further gates canaried on the wiring and watched failing: the ``_repository_of``
   root branch, its two-workspace refusal, and the ``--change-cost`` flag reaching the
   render. The first attempt at the CLI-seam canary **passed**, which is the tell that the
   gate did not exist: nothing asserted that ``_service`` threads the declaration into the
   factory, so a reader could parse the file while the instrument measured nothing. The
   test was written and the canary then failed correctly.

## Consequences

1. **D18 is resolved and its condition is recorded as unmet.** The instrument exists; the
   "after M0" clause in D18's recommendation is about the *ceiling decision*, and that
   decision is still open. The D18 row in the spec says both.
2. **FR-159 moves from Not built to Partly.** The instrument, the trend, the alarm and the
   unmeasured baseline are built. What is not built is a *baseline* — which needs a
   codebase history no single delivery has, and is not a missing feature.
3. **A unit with no recorded change reports unmeasured, not clean.** The failure this
   closes is the report that prints "no trend" over one unit and is read as "stable".
4. **The proxy declaration is a constant.** A declaration left to each report's author
   survives until the report that would rather not make it.
5. **`MODE_M_CEILING` remains L1 and `EVOLVABILITY_DEBT` remains 1.0**, so every FR-158
   test passes unchanged. A change that moved either would be the promotion this record
   refuses.
6. **The instrument is opt-in at the render** (`measure_change_cost=False`), for
   `measured_strength`'s reason plus one of its own: reading a footprint launches `git` per
   unit, and a report is not the thing that decides whether the ceiling may rise.
7. **`git.py` gains `head_commit` as a public read**, because a caller pinning a unit needs
   the sha at the moment it pins and reaching for the private helper would be a second
   convention.

## What this does not do

1. **It does not raise the Mode M ceiling.** That is D18's ceiling question, and the answer
   requires a trend a deployment has actually produced. A deployment that raised it on the
   strength of this record would be claiming a measurement it never took (NFR-024).
2. **It does not substitute for the θ gate.** FR-159's own text says the instrument measures
   change *cost* and not design *quality*, and FR-158's text says explicitly not to
   "substitute mutation score (FR-157) for it". The same refusal applies here in the other
   direction: a flat change-cost trend is not a verification, and
   `CHANGE_COST_NOT_A_VERIFICATION` says so on every report.
3. **It does not measure a codebase's history on its own.** The caller supplies the pinned
   units and their commit ranges. Automatically discovering "the pinned set" from a
   repository's log would be choosing the units after seeing the diffs, which is the one
   thing pinning exists to prevent.
