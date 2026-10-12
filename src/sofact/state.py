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
	CompletionClaim,
	Contract,
	Decomposition,
	DecompositionGate,
	DispatchRecord,
	ElicitationAnswer,
	Evidence,
	Goal,
	GoalPlan,
	HarnessProfile,
	IntegrityCheck,
	LedgerEntry,
	LedgerKind,
	ProjectState,
	RepairAttempt,
	ResearchRecord,
	SpecificationDraft,
	VerificationReport,
)

__all__ = ["fold"]


def fold(entries: Iterable[LedgerEntry]) -> ProjectState:
	"""Derive :class:`ProjectState` by replaying ``entries`` in order."""
	goals: list[Goal] = []
	answers: list[ElicitationAnswer] = []
	drafts: list[SpecificationDraft] = []
	contracts: list[Contract] = []
	evidence: list[Evidence] = []
	reports: list[VerificationReport] = []
	claims: list[CompletionClaim] = []
	notes: list[str] = []
	plans: list[GoalPlan] = []
	decompositions: list[Decomposition] = []
	gates: list[DecompositionGate] = []
	dispatches: list[DispatchRecord] = []
	profiles: list[HarnessProfile] = []
	integrity: list[IntegrityCheck] = []
	research: list[ResearchRecord] = []
	# Repair attempts are keyed by id with last-write-wins, like a re-answered
	# elicitation dimension (ADR-0007): an attempt is written when its session ends and
	# *settled* later against the verdict that session's check rendered, so the same
	# attempt appears twice and only its final outcome is current. The full history stays
	# in the log; the fold reports the settled value.
	repairs: dict[str, RepairAttempt] = {}

	for entry in entries:
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
			case LedgerKind.REPAIR_ATTEMPTED:
				settled = RepairAttempt.model_validate(payload["repair"])
				repairs[settled.id] = settled
			case LedgerKind.CLAIM_DECLARED:
				claims.append(CompletionClaim.model_validate(payload["claim"]))
			case LedgerKind.ADVISOR_NOTE:
				notes.append(str(payload["text"]))
			case LedgerKind.PLAN_COMPILED:
				plans.append(GoalPlan.model_validate(payload["plan"]))
			case LedgerKind.DECOMPOSITION_PROPOSED:
				decompositions.append(Decomposition.model_validate(payload["decomposition"]))
			case LedgerKind.DECOMPOSITION_GATED:
				gates.append(DecompositionGate.model_validate(payload["gate"]))
			case LedgerKind.CAPABILITY_PROBED:
				profiles.append(HarnessProfile.model_validate(payload["profile"]))
			case LedgerKind.STEP_DISPATCHED:
				dispatches.append(DispatchRecord.model_validate(payload["dispatch"]))
			case LedgerKind.INTEGRITY_CHECKED:
				integrity.append(IntegrityCheck.model_validate(payload["check"]))

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
		decompositions=tuple(decompositions),
		gates=tuple(gates),
		dispatches=tuple(dispatches),
		profiles=tuple(profiles),
		integrity=tuple(integrity),
		research=tuple(research),
		repairs=tuple(repairs.values()),
	)
	assert len(state.goals) == len(goals), "fold lost a goal"
	return state
