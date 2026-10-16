"""Fold the event log into current state.

State is a *derived* value, never a stored one. :func:`fold` is pure: same entries
in, same :class:`~sofact.views.ProjectState` out, no I/O, no clock, no ordering
dependence beyond the log's own order. That purity is what makes replay meaningful —
if state could be assembled by anything other than the log, the log would not be the
record of what happened.

An unknown event kind cannot reach this function. ``LedgerEntry.kind`` is typed
``LedgerKind``, so a line naming a kind this build does not know fails pydantic
validation inside :meth:`~sofact.ledger.Ledger.entries` and surfaces as
``LedgerCorruptError`` — the log from a newer SoFact is refused at parse, which is
earlier and louder than a skip here would be. That is why the ``match`` below has no
``case _`` arm: the type system proves it total, and a guard that can never fire is a
claim about behaviour that nothing tests.
"""

from __future__ import annotations

from collections.abc import Iterable

from sofact.views import (
	AdversarialAuditReport,
	AuthorshipCheck,
	CompetitiveLandscape,
	CompletionClaim,
	Contract,
	Cut,
	Decomposition,
	DecompositionGate,
	DeliveryReport,
	DeployRecord,
	DiffReview,
	DispatchRecord,
	DriverRun,
	ElicitationAnswer,
	ElicitationAttestation,
	EscapeEvent,
	EscapeOverride,
	Evidence,
	ExceedsClaim,
	GateCost,
	Goal,
	GoalPlan,
	HarnessProfile,
	IntegrationReport,
	IntegrityCheck,
	LedgerEntry,
	LedgerKind,
	Notification,
	OracleAuditReport,
	PhaseAdvance,
	ProductSpecificationDocument,
	ProjectState,
	RepairAttempt,
	ResearchClassification,
	ResearchRecord,
	SearchScan,
	SourceLedger,
	Specification,
	SpecificationDraft,
	SpecificationGate,
	Transcript,
	VerificationReport,
)

__all__ = ["fold"]


def _cut_rows(entries: tuple[LedgerEntry, ...]) -> tuple[LedgerEntry, ...]:
	"""Every cut row the log holds, oldest first — including the superseded ones.

	Read from the whole log rather than from what survives the cut, because a cut that a
	later one supersedes is still a decision the log records, and a field that collected
	only the survivors would make the log's own history depend on its last line.
	"""
	return tuple(entry for entry in entries if entry.kind is LedgerKind.CUT_RECORDED)


def _hidden_by_latest_cut(entries: tuple[LedgerEntry, ...]) -> frozenset[int]:
	"""Indices the latest cut hides: everything after its target and before itself.

	Only the latest cut's rule applies. Two cuts whose skips composed would make the
	current state depend on the *history* of rollback decisions rather than on one
	decision, and "read as of entry M" is not a statement that should stack — the
	operator who cuts twice to successively later entries means the later one, and one
	who cuts backwards means to hide more. Both readings are served by taking the last.

	**A cut row is never hidden, and neither is the latest one's own row.** The skip
	exists to un-do *work*, and a cut is not work — it is the record of a decision about
	how to read the log. Hiding one would make the log's account of its own reading rules
	depend on the most recent reading rule, so an operator who rolled back furthest would
	see the least of their rollback history, which is backwards: the reason an earlier
	cut was taken is exactly what the operator re-cutting needs. It would also let the
	skip swallow the *reason* for a rollback, leaving the unexplained gap the cut's own
	docstring says must not exist. Leaving the rows visible costs nothing, because a cut
	row contributes no state of its own — its whole effect is this function's return
	value, computed from the full log before the fold's loop runs.
	"""
	rows = _cut_rows(entries)
	if not rows:
		return frozenset()
	latest = rows[-1]
	cut = Cut.model_validate(latest.payload["cut"])
	assert cut.target_index < latest.index, (
		f"a cut at entry {latest.index} targets {cut.target_index}, which is not before it: "
		"a cut can only roll back to what has already happened"
	)
	hidden = set(range(cut.target_index + 1, latest.index))
	hidden.difference_update(row.index for row in rows)
	return frozenset(hidden)


def fold(entries: Iterable[LedgerEntry]) -> ProjectState:
	"""Derive :class:`ProjectState` by replaying ``entries`` in order.

	An operator's :class:`~sofact.views.Cut` is applied here rather than by truncating
	the file: FR-003 makes the log append-only, and a rollback that deleted the rows it
	rolled back would destroy the evidence that the work happened — which is what an
	operator rolling back most needs to keep. The rule is the latest cut's: read through
	its ``target_index``, skip everything between that target and the cut row itself,
	then fold whatever follows normally. So a cut is "the state as of entry N, plus
	whatever I have done since deciding that", and a second cut to a later entry
	un-does the first.
	"""
	ordered = tuple(entries)
	hidden = _hidden_by_latest_cut(ordered)
	goals: list[Goal] = []
	answers: list[ElicitationAnswer] = []
	drafts: list[SpecificationDraft] = []
	contracts: list[Contract] = []
	evidence: list[Evidence] = []
	reports: list[VerificationReport] = []
	claims: list[CompletionClaim] = []
	notes: list[str] = []
	plans: list[GoalPlan] = []
	specifications: list[Specification] = []
	specification_gates: list[SpecificationGate] = []
	decompositions: list[Decomposition] = []
	gates: list[DecompositionGate] = []
	dispatches: dict[str, DispatchRecord] = {}
	profiles: list[HarnessProfile] = []
	integrity: list[IntegrityCheck] = []
	integrations: list[IntegrationReport] = []
	research: list[ResearchRecord] = []
	ledgers: list[SourceLedger] = []
	classifications: list[ResearchClassification] = []
	phases: list[PhaseAdvance] = []
	# Repair attempts are keyed by id with last-write-wins, like a re-answered
	# elicitation dimension (ADR-0007): an attempt is written when its session ends and
	# *settled* later against the verdict that session's check rendered, so the same
	# attempt appears twice and only its final outcome is current. The full history stays
	# in the log; the fold reports the settled value.
	repairs: dict[str, RepairAttempt] = {}
	cuts: list[Cut] = []
	deliveries: list[DeliveryReport] = []
	deploys: list[DeployRecord] = []
	gate_costs: list[GateCost] = []
	reviews: list[DiffReview] = []
	oracle_audits: list[OracleAuditReport] = []
	adversarial_audits: list[AdversarialAuditReport] = []
	authorship_checks: list[AuthorshipCheck] = []
	escapes: list[EscapeEvent] = []
	escape_overrides: list[EscapeOverride] = []
	transcripts: list[Transcript] = []
	attestations: list[ElicitationAttestation] = []
	landscapes: list[CompetitiveLandscape] = []
	exceeds: list[ExceedsClaim] = []
	product_specs: list[ProductSpecificationDocument] = []
	driver_runs: list[DriverRun] = []
	notifications: list[Notification] = []
	scans: list[SearchScan] = []

	for entry in ordered:
		if entry.index in hidden:
			continue
		payload = entry.payload
		match entry.kind:
			case LedgerKind.GOAL_CREATED:
				goals.append(Goal.model_validate(payload["goal"]))
			case LedgerKind.ANSWER_RECORDED:
				answers.append(ElicitationAnswer.model_validate(payload["answer"]))
			case LedgerKind.DRAFT_CREATED:
				drafts.append(SpecificationDraft.model_validate(payload["draft"]))
			case LedgerKind.CONTRACT_CREATED:
				contracts.append(Contract.model_validate(payload["contract"]))
			case LedgerKind.EVIDENCE_RECORDED:
				evidence.append(Evidence.model_validate(payload["evidence"]))
			case LedgerKind.VERDICT_RENDERED | LedgerKind.VERDICT_REUSED:
				reports.append(VerificationReport.model_validate(payload["report"]))
			case LedgerKind.RESEARCH_RUN:
				research.append(ResearchRecord.model_validate(payload["research"]))
			case LedgerKind.SOURCE_LEDGER_RECORDED:
				# Appended, not keyed: FR-070 makes the ledger *versioned*, so a later run
				# that re-states the ground is a new ledger rather than an edit to the old
				# one. `ProjectState.ledger` derives the operative one from the last row.
				ledgers.append(SourceLedger.model_validate(payload["ledger"]))
			case LedgerKind.RESEARCH_CLASSIFIED:
				# Appended for the same reason the ledger is: FR-068's classification is
				# versioned, and a re-classification after a return to P0 is a new record
				# rather than an edit -- the old one is *why* the pipeline went back.
				classifications.append(
					ResearchClassification.model_validate(payload["classification"])
				)
			case LedgerKind.REPAIR_ATTEMPTED:
				settled = RepairAttempt.model_validate(payload["repair"])
				repairs[settled.id] = settled
			case LedgerKind.CLAIM_DECLARED:
				claims.append(CompletionClaim.model_validate(payload["claim"]))
			case LedgerKind.ADVISOR_NOTE:
				notes.append(str(payload["text"]))
			case LedgerKind.PLAN_COMPILED:
				plans.append(GoalPlan.model_validate(payload["plan"]))
			case LedgerKind.SPECIFICATION_PROPOSED:
				specifications.append(Specification.model_validate(payload["specification"]))
			case LedgerKind.SPECIFICATION_GATED:
				specification_gates.append(SpecificationGate.model_validate(payload["gate"]))
			case LedgerKind.DECOMPOSITION_PROPOSED:
				decompositions.append(Decomposition.model_validate(payload["decomposition"]))
			case LedgerKind.DECOMPOSITION_GATED:
				gates.append(DecompositionGate.model_validate(payload["gate"]))
			case LedgerKind.CAPABILITY_PROBED:
				profiles.append(HarnessProfile.model_validate(payload["profile"]))
			case LedgerKind.STEP_DISPATCHED:
				# Keyed rather than appended, because a dispatch can be written more than once
				# and the later row is the more complete one: FR-141's wave integration merges
				# a worktree back after the session has ended, and the merge is a fact the
				# first write could not know. The log stays append-only (FR-003) -- this is
				# the fold's rule for reading it, not a licence to rewrite a row. Position
				# is the dispatch's first appearance, so log order still means when it
				# started rather than when it was last amended.
				dispatched = DispatchRecord.model_validate(payload["dispatch"])
				dispatches[dispatched.id] = dispatched
			case LedgerKind.INTEGRITY_CHECKED:
				integrity.append(IntegrityCheck.model_validate(payload["check"]))
			case LedgerKind.INTEGRATION_CHECKED:
				integrations.append(IntegrationReport.model_validate(payload["integration"]))
			case LedgerKind.PHASE_ADVANCED:
				phases.append(PhaseAdvance.model_validate(payload["advance"]))
			case LedgerKind.CUT_RECORDED:
				# Collected, and the *effect* is the skip above — applied before this loop
				# ran, from the latest row among the entries being folded. The collection is
				# the log's own record of every cut; `ProjectState.cut` derives the operative
				# one from it, so the two cannot disagree.
				cuts.append(Cut.model_validate(payload["cut"]))
			case LedgerKind.DELIVERY_RENDERED:
				# Appended for the same reason the ledger is (FR-070): a deploy gate
				# approved against a report must stay readable, so re-rendering supersedes
				# without erasing. `ProjectState.delivery` derives the operative one.
				deliveries.append(DeliveryReport.model_validate(payload["delivery"]))
			case LedgerKind.DEPLOY_RECORDED:
				# Appended and never keyed: §1.5 makes deploy a permanent human act, so a
				# second deploy is a second act rather than an amendment of the first, and
				# the history of who deployed what is the point of recording it.
				deploys.append(DeployRecord.model_validate(payload["deploy"]))
			case LedgerKind.ORACLE_AUDITED:
				oracle_audits.append(OracleAuditReport.model_validate(payload["audit"]))
			case LedgerKind.ADVERSARIAL_AUDITED:
				# Appended, never keyed, and for FR-015's reason: the rate is a *trend*, so
				# every pass is a data point. Keying them to the latest would leave the
				# plateau FR-015 warns about unobservable, which is the one thing the rate
				# exists to make visible.
				adversarial_audits.append(AdversarialAuditReport.model_validate(payload["audit"]))
			case LedgerKind.AUTHORSHIP_CHECKED:
				# Appended, never keyed: FR-053 and FR-134 are claims about the *tree*, and
				# the tree moves. A check keyed to the latest would report the current
				# closure while the reader believes it is reading the one that was measured
				# when the contract was authored -- which is the stale-evidence mistake
				# FR-006 refuses one phase over.
				authorship_checks.append(AuthorshipCheck.model_validate(payload["check"]))
			case LedgerKind.GATE_COST_RECORDED:
				# Appended for the same reason: FR-160 measures a human act, and two
				# recordings of one gate are two measurements rather than an edit.
				# `ProjectState.gate_cost` reads the latest per gate, so the sum cannot
				# double-count a gate that was measured twice.
				gate_costs.append(GateCost.model_validate(payload["cost"]))
			case LedgerKind.DIFF_REVIEWED:
				# Appended, `gate_costs`' rule one requirement along: §20.3 item 3
				# measures a human act, and two sittings on one diff are two
				# measurements rather than an edit. `ProjectState.latest_reviews` reads
				# the latest per dispatch, so the total cannot double-count a diff that
				# was reviewed twice.
				reviews.append(DiffReview.model_validate(payload["review"]))
			case LedgerKind.ESCAPE_RECORDED:
				# Appended and never keyed: an escape is an event that happened, so two
				# rows are two events — a revert and then a hotfix. FR-022's numerator
				# collapses them by *defect*, which is where that judgement belongs.
				escapes.append(EscapeEvent.model_validate(payload["escape"]))
			case LedgerKind.ESCAPE_OVERRIDE_RECORDED:
				# Appended, with `ProjectState.latest_escape_override` reading the latest
				# per lane — `gate_cost`'s rule. The history is what makes FR-023's
				# "logged and attributed" checkable after the override is revised.
				escape_overrides.append(EscapeOverride.model_validate(payload["override"]))

			case LedgerKind.TRANSCRIPT_RECORDED:
				# Appended, never keyed: two transcriptions of one recording are two
				# attempts, and the second may be the one that worked. `transcript_for`
				# reads the latest usable one per goal.
				transcripts.append(Transcript.model_validate(payload["transcript"]))

			case LedgerKind.ELICITATION_ATTESTED:
				# Appended, never keyed, and here the reason is the opposite of a
				# measurement's: an attestation is a person's act, so a second one is a
				# second person having read the answer rather than a revision of the first.
				attestations.append(ElicitationAttestation.model_validate(payload["attestation"]))

			case LedgerKind.COMPETITIVE_SCAN_RECORDED:
				# Versioned like the ledger and the classification: a rescan supersedes a
				# landscape rather than replacing it, and the operative one is `landscape`.
				landscapes.append(CompetitiveLandscape.model_validate(payload["landscape"]))

			case LedgerKind.EXCEEDS_DECLARED:
				# Appended, never keyed — `gate_costs`' rule. A declaration and its revision
				# are two claims someone made, and `exceeds_for` reads the latest per
				# requirement while the log keeps what was first declared.
				exceeds.append(ExceedsClaim.model_validate(payload["exceeds"]))

			case LedgerKind.PRODUCT_SPEC_RENDERED:
				# Versioned like the delivery: the document rendered before the P2 approval
				# and the one rendered after it are two different documents, and the first
				# is what the approver was shown.
				product_specs.append(
					ProductSpecificationDocument.model_validate(payload["document"])
				)

			case LedgerKind.DRIVER_ADVANCED:
				# Appended, never keyed. A driver run is one invocation, so two rows are two
				# runs — the resumable loop depends on that, since a resumed run is a second
				# row rather than an amendment of the first.
				driver_runs.append(DriverRun.model_validate(payload["run"]))

			case LedgerKind.NOTIFICATION_SENT:
				# Appended, never keyed, and the row exists whether or not it was delivered:
				# "we told them" and "we meant to tell them" must not print the same line.
				notifications.append(Notification.model_validate(payload["notification"]))

			case LedgerKind.SEARCH_SCAN_RECORDED:
				# Appended, never keyed: a scan is one provider's answers to one set of
				# queries, so a second scan over the same goal is a second measurement
				# rather than a correction — `scans_for` reads them in order.
				scans.append(SearchScan.model_validate(payload["scan"]))

	state = ProjectState(
		goals=tuple(goals),
		answers=tuple(answers),
		drafts=tuple(drafts),
		contracts=tuple(contracts),
		evidence=tuple(evidence),
		reports=tuple(reports),
		claims=tuple(claims),
		notes=tuple(notes),
		plans=tuple(plans),
		specifications=tuple(specifications),
		specification_gates=tuple(specification_gates),
		decompositions=tuple(decompositions),
		gates=tuple(gates),
		dispatches=tuple(dispatches.values()),
		profiles=tuple(profiles),
		integrity=tuple(integrity),
		integrations=tuple(integrations),
		research=tuple(research),
		ledgers=tuple(ledgers),
		classifications=tuple(classifications),
		repairs=tuple(repairs.values()),
		phases=tuple(phases),
		cuts=tuple(cuts),
		deliveries=tuple(deliveries),
		deploys=tuple(deploys),
		gate_costs=tuple(gate_costs),
		reviews=tuple(reviews),
		oracle_audits=tuple(oracle_audits),
		adversarial_audits=tuple(adversarial_audits),
		authorship_checks=tuple(authorship_checks),
		escapes=tuple(escapes),
		escape_overrides=tuple(escape_overrides),
		transcripts=tuple(transcripts),
		attestations=tuple(attestations),
		landscapes=tuple(landscapes),
		exceeds=tuple(exceeds),
		product_specs=tuple(product_specs),
		driver_runs=tuple(driver_runs),
		notifications=tuple(notifications),
		scans=tuple(scans),
	)
	assert len(state.goals) == len(goals), "fold lost a goal"
	return state
