"""The facts a screen shows, read from the log and rendered by nobody.

The TUI's data layer, and deliberately not part of it. Everything here is a fold over
:class:`~sofact.views.ProjectState` plus the two service reads a fold cannot answer —
readiness, and the gate's machine half. Nothing here imports ``textual``, formats a
colour, or knows what a panel is.

That boundary is the reason this module exists rather than the app reading the service
directly. A snapshot is testable with the ``service`` fixture the rest of the suite uses,
in a test that never starts a terminal; and the app becomes a renderer whose only claims
are about layout. The alternative — an app that folds the log itself — would put the
"what is the operator's next move" logic somewhere no test can reach without a headless
terminal, which is the same defect as a gate whose only exercise is a human looking at it.

**Read-only, and it says so in the type.** :class:`Snapshot` holds no service and no
callback, so no code path from a snapshot to ``approve_gate`` exists. The TUI's whole
mutation surface is the two acts §3.3 keeps human — answering a question, and approving a
gate after reading its checks — and both live in the app, next to the person who performs
them, rather than in the layer that reads.

**The next move is derived, not invented.** :attr:`Snapshot.next_move` reads the same
facts :attr:`~sofact.views.DriverRun.next_human_verb` reads, in the same order, because
an operator who is told one command by the TUI and another by ``sofact build`` is being
told the factory disagrees with itself. Where the two could drift the snapshot defers:
the gate branch asks :attr:`~sofact.views.PhaseAdvance.failed` rather than re-deriving
"the machine half failed", and the closed-gate branch is the driver's own fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sofact.service import FactoryService
from sofact.views import (
	GATE_APPROVE_VERB,
	PHASE_GATE,
	PHASE_PRODUCER_VERB,
	PHASE_SEQUENCE,
	ChainStatus,
	DimensionStatus,
	DriverRun,
	ElicitationDimension,
	GateCheck,
	Goal,
	LedgerEntry,
	Phase,
	PhaseGate,
	PhaseStatus,
)

__all__ = [
	"DASHBOARD_TITLE",
	"GateView",
	"PhaseRow",
	"Snapshot",
	"read_snapshot",
]

DASHBOARD_TITLE: Final = "SoFact"
"""What the header calls the product, so the app and a test name it the same way."""


@dataclass(frozen=True)
class PhaseRow:
	"""One row of the phase machine, as the screen draws it.

	A dataclass rather than the ``PhaseAdvance`` it came from, because the row carries
	three things no single view does: the phase, its status, and the gate it is gated by
	(or ``None``). Assembling that in the renderer would put the gate lookup beside the
	colour lookup, and the gate lookup is a fact about the pipeline.
	"""

	phase: Phase
	status: PhaseStatus
	gate: PhaseGate | None

	@property
	def label(self) -> str:
		"""``P2 specify [specification]`` — the phase, its name, and its gate if any."""
		text = f"{self.phase.value} {self.phase.name.lower()}"
		return text + (f"  [{self.gate.value}]" if self.gate is not None else "")

	@property
	def is_stopped(self) -> bool:
		"""Whether this row is the gate the pipeline is stopped at (FR-061)."""
		return self.status is PhaseStatus.AWAITING_GATE


@dataclass(frozen=True)
class GateView:
	"""An open gate: what the machine checked, and whether a person has approved it.

	``checks`` is the **recomputed** machine half where the service can recompute it,
	falling back to the presented row only when there is no artefact to recompute from.
	That is :meth:`~sofact.service.FactoryService.approve_gate`'s own rule, stated here
	because a screen that showed the frozen row would tell an operator whose repair had
	made every check pass that the gate still failed — the dead end ADR-0070 records.
	"""

	phase: Phase
	gate: PhaseGate
	checks: tuple[GateCheck, ...]

	@property
	def failed(self) -> tuple[GateCheck, ...]:
		"""The checks that did not hold. Approval cannot make an unsound artefact sound."""
		return tuple(c for c in self.checks if not c.passed)

	@property
	def can_approve(self) -> bool:
		"""Whether ``gate --approve`` would be accepted right now.

		``True`` when the machine half passed **and** there is a machine half to have
		passed. An empty check list is ``False``: a gate presented with no checks is one
		nobody has been shown anything at, and FR-080 makes presenting that a defect
		rather than an approval waiting to happen.
		"""
		return bool(self.checks) and not self.failed


@dataclass(frozen=True)
class Snapshot:
	"""Everything one screen needs, read once.

	Frozen, and holding only plain values, so a test can assert on it without a terminal
	and a renderer can diff two of them without asking the log again.
	"""

	home: str
	goal: Goal | None
	phase: Phase
	phases: tuple[PhaseRow, ...]
	gate: GateView | None
	readiness: tuple[DimensionStatus, ...]
	readiness_progress: tuple[int, int]
	ledger_length: int
	chain: ChainStatus
	entries: tuple[LedgerEntry, ...]
	run: DriverRun | None
	question: tuple[ElicitationDimension, str, str] | None
	"""The open dimension, its question and its rationale, or ``None`` when P0 is done."""

	unattested: int
	"""How many model-proposed answers nobody has read (FR-173).

	A count rather than the rows: the screen shows "3 proposals await your reading", and
	the rows themselves are a list the operator opens rather than a number they scan.
	"""

	@property
	def stopped_at_gate(self) -> bool:
		"""Whether machine work is forbidden right now (FR-061)."""
		return self.gate is not None

	@property
	def next_move(self) -> str:
		"""The command that would let the pipeline continue, in the operator's words.

		The order is the driver's own: an open gate first, because it stops everything
		downstream; then the interrogation, because it stops the phase the gate is a gate
		on; then a resume. A gate whose machine half failed names the phase's producer
		verb rather than ``gate --approve``, which could only refuse — the branch ADR-0070
		added after the first version sent operators to a dead end.
		"""
		if self.gate is not None:
			if self.gate.failed:
				producer = PHASE_PRODUCER_VERB.get(self.gate.phase)
				if producer is not None:
					return (
						f"sofact {producer}  (then `{GATE_APPROVE_VERB} "
						f"{self.gate.phase.value} --by <you>` once the checks pass)"
					)
			if self.gate.can_approve:
				return f"{GATE_APPROVE_VERB} {self.gate.phase.value} --by <you>"
			return f"sofact {PHASE_PRODUCER_VERB.get(self.gate.phase, 'build')}  (present the artefact first)"
		if self.question is not None:
			return "sofact   (bare: the questionnaire resumes at the open dimension)"
		if self.unattested:
			return "sofact attest <answer-id> --by <you>  (then `sofact build --resume`)"
		return "sofact build --resume"

	@property
	def is_ready(self) -> bool:
		"""Whether every elicitation dimension is resolved."""
		done, total = self.readiness_progress
		return done == total


async def read_snapshot(svc: FactoryService) -> Snapshot:
	"""Fold the log into everything a screen shows.

	One pass over the state and three service reads that are not folds: ``readiness``,
	``current_gate_checks`` and ``unanswered_proposals``. The gate's checks are recomputed
	rather than taken from the presented row wherever the service can, which is the same
	call ``approve_gate`` makes and therefore the same answer the operator's approval will
	be decided against.
	"""
	state = await svc.state()
	goal = await svc.current_goal()
	entries = await svc.entries()
	chain = await svc.verify_ledger()

	phases = tuple(
		PhaseRow(phase=phase, status=state.phase_status(phase), gate=PHASE_GATE.get(phase))
		for phase in PHASE_SEQUENCE
	)

	open_gate = state.open_gate
	gate: GateView | None = None
	if open_gate is not None:
		gate_name = PHASE_GATE[open_gate.phase]
		recomputed = await svc.current_gate_checks(open_gate.phase)
		gate = GateView(
			phase=open_gate.phase,
			gate=gate_name,
			checks=recomputed if recomputed is not None else open_gate.checks,
		)

	statuses: tuple[DimensionStatus, ...] = ()
	progress: tuple[int, int] = (0, 0)
	question: tuple[ElicitationDimension, str, str] | None = None
	unattested = 0
	if goal is not None:
		readiness = await svc.readiness(goal.id)
		statuses = readiness.statuses
		progress = readiness.progress
		pending = await svc.open_question(goal.id)
		if pending is not None:
			dimension, spec = pending
			question = (dimension, spec.question, spec.rationale)
		unattested = len(await svc.unanswered_proposals(goal.id))

	return Snapshot(
		home=str(svc.home),
		goal=goal,
		phase=state.current_phase,
		phases=phases,
		gate=gate,
		readiness=statuses,
		readiness_progress=progress,
		ledger_length=chain.length,
		chain=chain,
		entries=entries,
		run=state.driver_run,
		question=question,
		unattested=unattested,
	)
