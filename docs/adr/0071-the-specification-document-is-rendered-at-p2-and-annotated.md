# 0071 — The specification document is rendered at P2 and every requirement is annotated

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** FR-068, FR-069, FR-070, FR-074, FR-169, FR-170, FR-171, NFR-024;
  [ADR-0021](0021-research-is-dispatched-and-not-performed.md),
  [ADR-0070](0070-the-front-door-stops-at-every-gate-and-a-model-answer-is-not-an-answer.md)

## Context

The operator asked for a "detailed and annotated product specification document", and asked
SoFact to "specify capabilities that exceed" the best systems in the world. Three things were
missing: any document at all (`writing.py` writes only `DELIVERY.md` and `RUNBOOK.md`, and
only at P8), any competitive research, and any representation of an exceedance.

Two of the three are refusals rather than features, and the refusals are the design.

## Decision

**SoFact cannot name the best systems in the world for an arbitrary domain, and pretending
to would be the machine writing the claim it then measures.** So the producer identifies them
— under a criterion SoFact writes into the research goal — and the identification is an
artefact with its own evidence, parsed fail-closed. Three refusals carry it: a rival with no
source is refused outright, because a system nobody can look up is a name rather than a
baseline; a capability with no source is refused outright, because an uncited capability
cannot be the baseline an exceedance is declared against; and a landscape whose `subject`
differs from the query SoFact authored is refused, because the producer echoes the subject
rather than choosing it. **A scan that found nothing is a measurement, not a failure** — a
domain with no comparable system is a real finding, and treating it as an error would push a
producer toward inventing rivals to avoid one.

**No oracle in O1–O7 compares two systems**, and the authorship closure would not survive
putting one that reads a competitor's behaviour inside the authoring path. So an exceedance
is a *declaration* against a cited baseline: `ExceedsClaim` requires a non-empty
`baseline_source_ids` — a claim to exceed nothing is a wish — and non-empty `clause_ids`, so
it traces to something the operator actually asked for. `measured_margin` returns `None`
always, and the delivery check reports `N declared, 0 verified by oracle` with `passed=True`,
modelled on `machine_surface_not_verified`: the obligation stays in `DELIVERY_REQUIREMENTS`
rather than being dropped. **Nothing may print an exceedance as a verified capability.**

**The document is rendered at P2, not at P8.** P2 is the artefact the first gate is a gate
*on*, and a specification nobody can read is not gated by anything a human did. Rendering it
at delivery would mean the gate approved a structure while the prose arrived four phases
later.

**And rendered *before* the approval, not after it — which the first version got wrong.**
`write_specification` called `require_approved_specification`, so the only way to render the
annotated document was to have passed the gate already. The document could therefore only
ever be shown to someone who had decided, and `sofact spec-doc --approve` was unreachable:
the render it performs refused before the approval it needs. The ordering is the feature —
the annotation exists to be *read in order to decide* — so the requirement is now that the
specification has been **gated** (there is a checklist to render against) and not that it was
approved.

The gate as it stood is carried on the document as `gate_failures`, and it is a field rather
than a derivation because it is a reading of a *moment*: the gate is recomputed on every
approval, so a document that looked the state up afterwards would report the gate that was
finally passed instead of the one the approver was shown. The two differ by exactly the
operator's own answers, which is the state the document exists to make visible.

Three ordering defects followed from the same root and are fixed together: the driver opened
P2's gate without rendering its artefact, so an operator driven by `sofact build` was asked
to approve a specification with no document on disk; `approve_specification_document` set
`approved_by` in the ledger and left the file it had already written saying "not yet", so the
artefact a person holds contradicted the record; and the CLI test that should have caught the
first ran `specify --approve` before `spec-doc`, which is exactly the sequence the defect
forced on anyone using the product.

**"Annotated" is the whole content of the feature.** Every requirement carries its
provenance as a `RequirementAnnotation`, which *holds* its `Requirement` rather than naming
one — pyright found the original design gap: the document carried annotations but not the
requirements they annotated, so it could never render the requirement text. Fixing the type
rather than the call site makes the divergence unrepresentable. Each annotation carries the
clause stem it descends from, that stem's elicitation dimension, the `ElicitationAnswer` and
whether it was operator-authored or model-proposed **and whether a human attested it**, the
research verdict and its evidence source ids, the competitor capabilities it is positioned
against, the exceedance it belongs to, and the oracle's class and rank.

Two consequences follow and both are the point. **An unattested requirement is visibly
unattested**, and the marker is derived from the ledger rather than passed in, so the
document cannot be rendered clean over a specification whose answers nobody read. And **an
unoracled requirement prints as unverified**, with its `VerificationMethod`, so the document
cannot read as stronger than the contract it renders.

**The annotation joins the contract to the elicitation, which is not otherwise derivable.**
`ClauseStem.derived_from` survives `Contract.from_draft` — the clause id *is* the stem id —
but the draft's stems are not on the contract, so the renderer reads the draft from the log
by `goal_id` and matches on clause id. That read is stated in the code rather than assumed.

`specdoc.py` follows `writing.py` exactly: deterministic, model-free, two renders of one
input byte-identical, with a `PRODUCT_SPEC_HEADINGS` constant asserted against the render so
a dropped section fails rather than reads.

## Consequences

The document cannot claim more than the ledger holds, and it cannot claim an exceedance is
verified. What it can do is put the whole provenance chain in front of the approver at the
gate where the decision is actually made.

A competitive baseline is recorded as producer-chosen, under a criterion SoFact wrote, with
the count of unsourced systems carried — SoFact records that and does not claim the set is
the best in the world.
