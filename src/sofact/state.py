"""Fold the event log into current state.

State is a *derived* value, never a stored one. :func:`fold` is pure: same entries
in, same :class:`~sofact.views.ProjectState` out, no I/O, no clock, no ordering
dependence beyond the log's own order. That purity is what makes replay meaningful —
if state could be assembled by anything other than the log, the log would not be the
record of what happened.

Unknown event kinds raise rather than being skipped. A fold that silently ignores
events it does not understand would report stale state after a downgrade, and stale
state that *looks* current is worse than a crash.
"""

from __future__ import annotations

from collections.abc import Iterable

from sofact.views import (
	CompletionClaim,
	Contract,
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
	dispatches: list[DispatchRecord] = []
	profiles: list[HarnessProfile] = []
	integrity: list[IntegrityCheck] = []
	research: list[ResearchRecord] = []

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
			case LedgerKind.CLAIM_DECLARED:
				claims.append(CompletionClaim.model_validate(payload["claim"]))
			case LedgerKind.ADVISOR_NOTE:
				notes.append(str(payload["text"]))
			case LedgerKind.PLAN_COMPILED:
				plans.append(GoalPlan.model_validate(payload["plan"]))
			case LedgerKind.CAPABILITY_PROBED:
				profiles.append(HarnessProfile.model_validate(payload["profile"]))
			case LedgerKind.STEP_DISPATCHED:
				dispatches.append(DispatchRecord.model_validate(payload["dispatch"]))
			case LedgerKind.INTEGRITY_CHECKED:
				integrity.append(IntegrityCheck.model_validate(payload["check"]))
			case _:  # pragma: no cover - exhaustive by construction; guards future kinds
				raise ValueError(
					f"event {entry.index} has unknown kind {entry.kind!r}; this log was "
					"written by a newer SoFact and cannot be folded safely",
				)

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
		dispatches=tuple(dispatches),
		profiles=tuple(profiles),
		integrity=tuple(integrity),
		research=tuple(research),
	)
	assert len(state.goals) == len(goals), "fold lost a goal"
	return state
