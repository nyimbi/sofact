# 0078 — A clause's confidence is derived from its oracle, and the wish half was already built

- **Status:** Accepted
- **Date:** 2026-10-17
- **Related:** FR-067, FR-103, FR-108, FR-139, FR-140, §2.3;
  [ADR-0007](0007-the-elicitation-gate-is-deterministic.md),
  [ADR-0011](0011-the-factory-refuses-to-claim-maintainability.md),
  [ADR-0077](0077-the-interrogation-asks-eight-dimensions-and-scale-is-one-of-them.md)

## Context

**FR-067** is one sentence with two halves:

> Ambiguity must be **quantified**: each intent clause carries a `confidence` and a
> `verification_method` (how we will know it was satisfied). A clause with no
> verification method is not a clause; it is a wish and must be returned to the operator.

The roadmap row recorded it **Partly**: "`Clause` (`views.py:351`) carries **neither**;
ambiguity is not quantified per clause. `test_confidence_is_not_an_oracle`
(`test_elicitation.py:160`) asserts the *opposite* rule."

**Every particular of that row was wrong, and establishing that is most of this record.**

- **The citations were stale.** `Clause` is at `views.py:2115`; line `351` is `L5 = 5` in
  `AutonomyLevel`, an unrelated constant the citation had been pointing at.
  `test_confidence_is_not_an_oracle` is at `test_elicitation.py:229`, not `160`.
- **The test does not assert the opposite rule.** It asserts that a *statement* of
  confidence is not a **substitute for** an oracle: an ORACLE answer of "I will know it
  works because the operator will tell me it feels right" is refused with "does not name a
  checking mechanism" **and** "confidence is not an oracle". It says nothing about whether
  a clause may *carry* a confidence. The row read the test's name and inferred the
  negation of its content.
- **"A clause with no verification method is not a clause" was already built.**
  `Clause.oracle` is required and non-nullable, and `Contract.from_draft`
  (`views.py:2286-2303`) **raises** naming the offending stems — `"{n} clause stem(s) have
  no oracle, so no contract exists: …"`. No wish can reach a `Clause`, so there is nothing
  to return to the operator. The second half of FR-067 was discharged before this unit.
- **`verification_method` is deliberately *not* a `Clause` column, and the spec says so.**
  `docs/spec/product-spec.md:457-458`: "`ORACLE` carries FR-067's `verification_method` as
  its own question rather than a column on a clause." The P2 `Requirement` holds it
  (`views.py:2792`), derived in `specification.py`, rendered per requirement in
  `specdoc.py`. Adding it to `Clause` would state one fact twice and the two would drift
  the first time an oracle was replaced.

So the row was Partly on **one** half, not two, and the missing half was `confidence`.

### What `confidence` must not be

This is why the change is not a field addition. Everywhere in this tree a self-reported or
model-authored judgement is refused:

- `elicitation.py:122`, `:255` — "confidence is not an oracle".
- ADR-0007/0008 — the floors are "a filter against non-answers, not a measure of quality".
- `manufacture.py:6,32` — an oracle satisfiable without the invariant "manufactures false
  confidence" and is "a worse defect than a missing test".

A `confidence: float` a producer fills in would be the manufactured judge with a decimal
point on it, and FR-140 makes the producer's own account of its work inadmissible.

### The two designs refused, and why

**A stored field is refused on doctrine and on ledger integrity.** The repo's own words,
`OracleDeclaration.held_out` (`views.py:2082`): "a property rather than a stored flag on
purpose. A field defaulting to `False` would leave the leak open on every oracle built
without it — a control that exists and is never applied — whereas a derivation from the
class is correct at every site that reads it." A stored field also moves
`Contract.content_hash` (`content_hash([c.model_dump(mode="json") for c in self.clauses])`,
`views.py:2200`), which is FR-139's pinned integrity subject and `DispatchRecord`'s
`contract_hash`.

**The honest caveat, verified: nothing in the suite would have failed.** There was no
literal pinned hash anywhere in `tests/ci/` — every hash assertion was self-comparing — and
`test_manufacture.py:234`'s form compares `model_dump` against `model_fields`, which a
stored field **satisfies** and only a `@computed_field` breaks. So a stored field would
have silently invalidated the `contract_hash` in every existing ledger row and turned
FR-139's integrity check red on a real project while the suite stayed green. That is the
argument, stated rather than dressed as a red suite that would not have happened. The
`content_hash` assertion this unit adds is therefore **new coverage, not a restatement**.

**A `@computed_field` is refused too, and it is the trap.** `views.py` imports
`computed_field` and uses it exactly once — `MachineEnvelope.ok` (`views.py:10176`) — with
its reason stated: "the caller here is a *program* reading JSON, and a plain property is
absent from the serialised document." A `@computed_field` **does** enter `model_dump` and
would move `content_hash` exactly as a stored field would. `Clause`'s readers are Python,
so it is a **plain `@property`**.

## Decision

**1. `ClauseConfidence` is derived from the clause's own oracle, as a plain property.**

```python
class ClauseConfidence(StrEnum):
	COVERED = "covered"   # the oracle runs and is strong enough (oracle.covers)
	WEAK = "weak"         # it runs and is too weak — it measures something narrower
	STATED = "stated"     # no command: an intention, and nothing checks it
```

Three values rather than a number, because the states are three and a score would blur the
one that matters: `WEAK` is not a low `COVERED`, it is a *different* defect from `STATED` —
one runs and measures the wrong thing, the other measures nothing — and `0.6` would make
them the same number. The predicate reads `OracleDeclaration.is_executable` and `.covers`;
neither is new, and the trichotomy already exists in `Contract.uncovered_clauses`
(`views.py:2208`), the `because` sentence in `delivery.py`, and `cli.py:3751-3757`. This
names it on the object it is about. `WEAK` is the state those three cannot express, and it
is reachable — probed over the whole `ORACLE_RANK` × `command_hint` grid: ranks 1–5 with a
command are `COVERED`, ranks 6–7 with a command (`EXAMPLE`, `GOLDEN`) are `WEAK` because
`COVERING_ORACLE_MAX_RANK = 5`, and every class with no command is `STATED`.

**2. `verification_method` is not added to `Clause`.** The spec places it on the
`Requirement` and it is already there and already rendered. The row's "carries neither" is
corrected in the docs instead — a field-name count contradicting the design note it claims
to measure.

**3. It is rendered, because a quantified fact nobody prints quantifies nothing.**
`_annotation_lines` gains one line beside `oracle:` and `verification:`, so the annotated
document the operator reads at P2 shows which clauses are established, which merely run,
and which are stated; `## Oracle strength` gains the tally beside the rank range, because
"rank 1 to rank 7 over 7 requirements" reads as strong while three of those seven may be
`STATED`. No heading is added, so `PRODUCT_SPEC_HEADINGS` is untouched.

**4. The confidence is a function of the oracle alone.** A clause whose *statement* claims
high confidence still reports its oracle's state. `test_confidence_is_not_an_oracle` is
left unweakened.

## Consequences

- **What it quantifies is how far the clause is *established*, not how likely it is to be
  what the operator meant.** §2.3's ground-truth question is the operator's reading at P2,
  and nothing here answers it. The ADR says so rather than letting a field named
  `confidence` read as a statement about intent.
- **Nothing is derived from elicitation.** `Clause` cannot see its stem's `derived_from` or
  its answer's attestation without a schema change — which is the stored field the hash
  argument refuses. The authorship half of ambiguity already exists one layer up as
  `RequirementAnnotation.unattested`, where the draft is in hand.
- **The wish refusal is corrected, not credited to this unit.** It was built at
  `Contract.from_draft` before this change.
- **`Requirement.criterion` and FR-077 are unchanged.**

## Verification

Canaried three ways, each watched failing and reverted from a verified backup:

1. `confidence` as a **stored field with a default** (the doctrine's own case, not a
   required field, which fails on `Field required` for the wrong reason) — the literal-set
   assertion and the `content_hash` pin both failed; the hash moved `b4979366…` →
   `ab474558…`.
2. `confidence` as a **`@computed_field`** — both failed; the hash moved to `d1091488…`.
   The probe showed the asymmetry that makes this canary necessary: the field appears in
   `model_dump` and **not** in `model_fields`, so `test_manufacture.py:234`'s form would
   have passed it. The literal-set assertion is what catches it.
3. The **`WEAK` branch removed** — the grid failed on exactly the two weak-but-runnable
   cells (`example`, `golden`) plus the dedicated test.
