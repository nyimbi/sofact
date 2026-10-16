"""The front door: one verb that carries a goal as far as a human lets it go (FR-172).

The operator asked to describe a system, have it researched, specified, planned, built,
verified, and be told when it is built. This module is the loop that does the machine
half of that — and it **stops at every gate**, because FR-061 makes a gate a hard stop and
:meth:`~sofact.service.FactoryService.advance_phase` has no path that passes one.

Three properties are the whole design, and each is a refusal rather than a feature:

**It is a loop over the ledger, not a held process.** Every iteration re-reads the folded
state and asks what the next thing that can be done is. So ``--resume`` is the same code
path as a cold start, and a driver killed mid-run resumes correctly because the ledger is
the only state. Nothing is held in memory across a stop.

**It is idempotent, and idempotency is asserted on the log rather than on the outcome.**
Every step checks whether the log already holds the thing it would produce: a plan that
exists is not recompiled, a sealed dispatch is not re-dispatched, a rendered delivery is
not re-rendered. Running the verb twice must append nothing the second time, and the test
that proves it compares ledger *lengths* — an outcome comparison passes when the second
run silently redoes the work and lands on the same answer.

**Terminal state is reported, never assumed.** :class:`~sofact.views.DriverTerminal` has
no member for "still going": every run ends, and ends in a named state.
:attr:`~sofact.views.DriverRun.claims_built` is true for ``DELIVERED`` alone, so nothing
downstream can compose "built" out of a run that stopped at a gate.

This module imports no model client and opens no socket. It calls
:class:`~sofact.service.FactoryService`, which is not an authorship root, so the
authorship closures ADR-0064 measures are unaffected by its existence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

from sofact._uuid7 import uuid7str
from sofact.service import FactoryService
from sofact.views import (
	GATE_APPROVE_VERB,
	PHASE_GATE,
	PHASE_PRODUCER_VERB,
	PHASE_SEQUENCE,
	DeliveryReport,
	DriverOutcome,
	DriverRun,
	DriverStep,
	DriverTerminal,
	GateCheck,
	Phase,
	PhaseStatus,
	ProjectState,
	now,
)

__all__ = [
	"DRIVER_ACTIONS",
	"DriverAction",
	"DriverRefusal",
	"run_goal",
]


class DriverRefusal(Exception):
	"""The driver cannot start, and says why rather than recording a run (FR-172).

	Raised only when there is no goal at all. Every other stopping condition is a recorded
	:class:`~sofact.views.DriverRun`, because those are runs that happened and stopped;
	this is a request that never became one.
	"""


RESUME_VERB: Final = "sofact build --resume"
"""What the operator types to continue a run, named in the halt and the notification."""


@dataclass(frozen=True, slots=True)
class DriverAction:
	"""One thing the driver can do next, and the guard that says whether it may (FR-172).

	``name`` is a stable identifier rather than a sentence, because it reaches the
	notification body and the ``--verbose`` output and a reader comparing two runs should
	be comparing the same string. ``detail`` is the sentence.

	``presents`` marks the action that opens its phase's gate, and it is a field rather
	than a positional rule because **two actions can share a phase**: ``contract`` and
	``specify`` are both P2, and the action that opens P2's gate is the second of them. A
	run resumed against an already-open gate has no steps of its own to read the halting
	action off, so it falls back to naming one from the phase — and "the first action with
	that phase" named ``contract`` for a run that halted at a gate ``specify`` had opened.
	The step a run stopped on is the thing an operator acts on, so it may not be a guess
	about list order.
	"""

	name: str
	detail: str
	phase: Phase
	presents: bool = False


DRIVER_ACTIONS: Final[tuple[DriverAction, ...]] = (
	DriverAction("propose-answers", "draft the open elicitation dimensions", Phase.ELICIT),
	DriverAction("draft", "draft clause stems from the resolved elicitation", Phase.ELICIT),
	DriverAction("research", "dispatch P1 and record what it left behind", Phase.RESEARCH),
	DriverAction("contract", "assign an oracle to every clause stem", Phase.SPECIFY),
	DriverAction(
		"specify",
		"propose the specification and present its gate",
		Phase.SPECIFY,
		presents=True,
	),
	DriverAction(
		"decompose",
		"propose modules and present the decomposition gate",
		Phase.DECOMPOSE,
		presents=True,
	),
	DriverAction(
		"plan",
		"compile the plan, audit the oracles, present the sample gate",
		Phase.CONTRACT,
		presents=True,
	),
	DriverAction("build", "dispatch the plan's steps", Phase.BUILD),
	DriverAction("verify", "run P6 over what the dispatches left", Phase.VERIFY),
	DriverAction("integrate", "check the integration across modules", Phase.INTEGRATE),
	DriverAction(
		"deliver",
		"render the delivery report and present the deploy gate",
		Phase.DELIVER,
		presents=True,
	),
)
"""Every action, in the order the pipeline permits them (FR-172).

A constant rather than a chain of ``if``s in the loop, so the *set* of things the driver
can do is readable in one place — the driver is the one verb an operator runs unattended,
and "what will it do" must be answerable without reading the control flow.

**``research`` is in the list because P1 cannot honestly be skipped.** Every phase before
a gate must be :attr:`~sofact.views.PhaseStatus.COMPLETE` before the gate can be presented,
so a driver that went from ``draft`` to ``specify`` would have to *mark* P1 complete — and
the operator asked for deep research as one of the seven things this verb is for. Marking
the research phase done with an empty log is the factory asserting research happened, which
is the one claim a ledger that holds no ``research.run`` row cannot support.

**Search is deliberately not in the list.** SoFact's own web search (FR-174) is a verb and a
recorded scan, and a deployment ships no provider: requiring one here would make the front
door refuse on every default installation for a capability that *widens* what P1 can cite
rather than being P1. ``sofact search`` records the scan, and the ledger gate reads it.
"""

_ACTION: Final[dict[str, DriverAction]] = {action.name: action for action in DRIVER_ACTIONS}
"""The actions by name, so a selection names the step instead of counting to it.

An index into :data:`DRIVER_ACTIONS` is a position in a list that gains members, and
``DRIVER_ACTIONS[3]`` silently becomes a different action the day one is inserted above it.
The failure is invisible — the driver still does *something*, just not the thing the line
says — which is why every selection below is by name.
"""


@dataclass
class _Steps:
	"""The steps one run took, accumulated as it goes."""

	taken: list[DriverStep] = field(default_factory=list[DriverStep])

	def record(self, action: DriverAction, outcome: DriverOutcome, detail: str) -> None:
		self.taken.append(
			DriverStep(
				id=uuid7str(),
				phase=action.phase,
				action=action.name,
				outcome=outcome,
				detail=detail,
				at=now(),
			)
		)


def _next_action(
	state: ProjectState,
	*,
	has_draft: bool,
	has_research: bool,
	ready: bool,
) -> DriverAction | None:
	"""What the driver can do next, or ``None`` when every action is discharged (FR-172).

	Read purely off the folded state, so this is the whole of the resumability: there is
	no cursor, no in-memory position and no session file, and a run resumed in a new
	process computes the same answer from the same log.

	The first action whose work the log does not already hold wins. Each check is against
	a *recorded artefact* rather than against a phase status, because a phase can be
	active with its artefact already produced — a run interrupted between two appends —
	and re-doing work that is done is the defect idempotency exists to prevent.

	``has_draft`` and ``has_research`` are the two facts the folded state does not expose
	as one field, and both are read from the log rather than from a phase status for that
	reason: a phase that is complete with no artefact behind it is exactly the state this
	function must not treat as discharged.
	"""
	if state.open_gate is not None:
		# A gate is open, so no action downstream of it may run. The loop reports this
		# rather than selecting an action: FR-061 makes the stop the correct behaviour,
		# not an obstacle to route around.
		return None
	goal = state.latest_goal()
	if goal is None:
		return None
	contract = state.latest_contract(goal.id)
	if contract is None:
		if not has_draft:
			# P0's own gate, and the reason this reads ``ready`` rather than "has an
			# answer for every dimension": a model-proposed answer nobody attested is
			# reported as *open* (FR-173), so the count of answers is not the question.
			#
			# ``readiness`` cannot separate the two ways a dimension is open — "nobody
			# has answered" and "a model proposed and nobody attested" are both open, with
			# different reason strings — so this selects ``propose-answers`` for either.
			# On a reachable model the first iteration drafts all six, the second selects
			# this again and proposes nothing, and the run stops with the *action's own*
			# message naming the verb that actually continues it (``attest``). Reading the
			# reason strings to tell the two apart would be parsing prose to make a control
			# decision; the state exposes the distinction as data and a future revision
			# should read it from there rather than from ``ready``.
			return _ACTION["draft"] if ready else _ACTION["propose-answers"]
		if not has_research:
			# P1 sits between the draft and the contract, and that is where the pipeline
			# puts it: ``research_goal`` writes the draft's own clause ids into the
			# session's goal, so the research cannot run before there is a draft, and
			# ``specify`` proposes a specification *for* a contract whose premises the
			# research was supposed to have tested — FR-068's classification is what says
			# whether a premise was invalidated. A contract written before P1 has run is a
			# contract over untested premises.
			return _ACTION["research"]
		return _ACTION["contract"]
	specification = state.latest_specification(contract.id)
	if specification is None:
		return _ACTION["specify"]
	decomposition = state.latest_decomposition(contract.id)
	if decomposition is None:
		return _ACTION["decompose"]
	plan = state.latest_plan(contract.id)
	if plan is None or state.latest_oracle_audit(contract.id) is None:
		# FR-107's audit is what P4's sampled gate presents: "this oracle measures the
		# right thing" is the thing no oracle can decide, and the machine half that gets
		# as close as it can is an oracle run against an empty workspace. The two are one
		# action because the audit needs the plan's tree and the gate needs the audit's
		# findings, and splitting them would leave a plan compiled and a gate unshown.
		return _ACTION["plan"]
	if not state.dispatches_for(plan.id):
		# **Dispatched, not sealed.** The guard reads the dispatch rows rather than
		# :attr:`~sofact.views.ProjectState.sealed_dispatches`, and the difference is the
		# difference between "the step ran" and "SoFact sealed a diff a human could
		# review". ``sealed_dispatches`` filters on ``checkout.sealed_commit is not None``,
		# which is ``None`` for a producer that commits its own work — an accepted limit
		# of the coverage denominator, and the wrong fact here. Read that way, a plan
		# dispatched to a producer that commits left the set empty, so ``build`` was
		# selected again on every iteration: the driver re-dispatched the whole plan until
		# the iteration bound, and reported ``exhausted`` on a build that had in fact
		# completed every step. Idempotency is about the work, not about reviewability.
		return _ACTION["build"]
	if state.latest_report(contract.id) is None:
		return _ACTION["verify"]
	if state.latest_integration(plan.id) is None:
		return _ACTION["integrate"]
	if state.delivery is None:
		return _ACTION["deliver"]
	return None


def _proposals_waiting(state: ProjectState, goal_id: str) -> bool:
	"""Whether the goal holds a model's proposal that no person has confirmed (FR-173).

	The fact that separates P0's two waits, and it is a *read of the log* rather than a
	re-derivation of the gate: a model-proposed answer exists and is unattested. That is
	exactly the state in which ``propose-answers`` has nothing left to do — it skips
	dimensions that already hold an answer, so it returns an empty tuple and the run
	stops — and exactly the state in which the operator's next command is ``attest``
	rather than a resume.

	Deliberately not "readiness reports the dimension open with a proposal reason": that
	would be parsing a human-readable string to make a control decision, and the state
	already exposes the two facts this needs as data.
	"""
	attested = state.attested_answer_ids()
	return any(
		a.goal_id == goal_id and a.is_model_proposed and a.id not in attested for a in state.answers
	)


async def run_goal(
	service: FactoryService,
	*,
	root: Path | None = None,
	notify: bool = True,
	timeout: float = 900.0,
	harness: str | None = None,
	research_harness: str | None = None,
	on_step: Callable[[DriverStep], None] | None = None,
) -> DriverRun:
	"""Carry the current goal as far as the gates allow, and record the run (FR-172).

	One call does as much as it can and then stops — at a gate, at a failure, or at a
	completed delivery. It never waits in-process for an approval: an approval comes from
	another terminal (``sofact gate --approve P2 --by you``) and the way to pick it up is
	to run this again, which re-reads the log and continues. That is what makes the stop
	a stop rather than a poll.

	``notify`` sends one notification when the run ends, composed from the terminal state
	and nothing else — see :func:`sofact.notify.render_subject`. It defaults to on
	because the operator's request is to *be told* when it is built, and a driver that
	had to be asked twice would be a driver whose default is silence.

	``harness`` and ``research_harness`` name the two harnesses the run dispatches to, and
	they are separate parameters because the two are separate specs: a build dispatch
	needs a probed harness whose composition matches the step, and P1 needs one whose
	``research_tools`` carry the extension's allowlist. A deployment that configures more
	than one of either — which is the ordinary case, and the whole point of the table —
	could not be driven at all without them: ``harness_name`` refuses an ambiguous table
	rather than picking one, so the driver reported a ``KeyError`` naming a harness the
	operator had never been asked to choose.
	"""
	state = await service.state()
	goal = state.latest_goal()
	started = now()
	steps = _Steps()
	if goal is None:
		# A refusal, raised rather than recorded, and this is the one place the driver
		# does not write a row. `DriverRun.goal_id` is required because a run is a run
		# *of* something: recording one against no goal would need the field to be
		# optional, and every later reader would then have to handle a driver run that
		# belongs to nothing. There is no machine work to report and no run to name, so
		# the operator gets a sentence and the log stays honest about what it holds.
		raise DriverRefusal(
			"no goal in this log: run `sofact build --statement <text>` or "
			"`sofact speak <audio>` first, then `sofact build` (FR-172)"
		)
	for _ in range(_MAX_ITERATIONS):
		state = await service.state()
		gate = state.open_gate
		if gate is not None:
			# The step that *opened* the gate is the one that halted, and it was recorded
			# as ADVANCED when it ran: proposing a specification is work that succeeded,
			# and the gate is what it produced. Recording `DRIVER_ACTIONS[0]` here instead
			# would name the driver's first action as the thing that stopped — a step that
			# never ran — and a run that halted at P2 would print "propose-answers halted".
			# So the halting step is read off the last step actually taken, and only when
			# there is none (a gate already open when the run began) does it fall back to
			# the action that presents the gate's own phase.
			#
			# The fallback reads the ``presents`` flag rather than taking the first action
			# whose phase matches, because a phase can carry more than one action and only
			# one of them opens the gate. ``contract`` and ``specify`` are both P2, and a
			# run resumed against an already-open P2 gate named ``contract`` — a step that
			# does not present a gate at all — so the operator was told the run stopped on
			# the wrong one.
			last = steps.taken[-1].action if steps.taken else None
			opened_by = next(
				(action for action in DRIVER_ACTIONS if action.name == last),
				next(
					(
						action
						for action in DRIVER_ACTIONS
						if action.presents and action.phase is gate.phase
					),
					DRIVER_ACTIONS[0],
				),
			)
			# FR-061: a gate whose machine half *failed* is not passed with `gate --approve`
			# — that verb refuses a failed check, and correctly, since approval cannot make
			# an unsound artefact sound. Reporting the stop without saying so sent the
			# operator to a command that could only refuse them, which turns a hard stop
			# into a dead end. The failures are recorded so `next_human_verb` names the
			# phase's producer verb instead, and the detail says the same in words.
			#
			# The failures are recomputed from the artefact as it is, not read off the
			# presented row, because the row is a record of what was *shown* and the
			# artefact can have been revised since — which is the ordinary course of a gate
			# the machine half failed. `approve_gate` already decides on the recomputation;
			# a driver reading the frozen row would report failures that no longer exist
			# and send an operator whose repair passed every check to re-produce the
			# artefact anyway, while `gate --approve` would have accepted it.
			current = await service.current_gate_checks(gate.phase)
			checks = current if current is not None else gate.checks
			failed = tuple(c.name for c in checks if not c.passed)
			steps.record(
				opened_by,
				DriverOutcome.HALTED,
				f"{gate.phase.value} is awaiting {PHASE_GATE[gate.phase].value}"
				+ (
					f"; {len(failed)} machine check(s) failed: {', '.join(failed)}"
					if failed
					else ""
				),
			)
			if failed:
				producer = PHASE_PRODUCER_VERB.get(gate.phase)
				detail = (
					f"{gate.phase.value} awaits {PHASE_GATE[gate.phase].value}, and "
					f"{len(failed)} machine check(s) failed ({', '.join(failed)}). Approval "
					f"cannot make an unsound artefact sound, so `{GATE_APPROVE_VERB}` will refuse: "
					f"supply what the checks found missing with "
					f"`sofact {producer}` and run `{RESUME_VERB}` (FR-061, FR-172)"
					if producer is not None
					else (
						f"{gate.phase.value} awaits {PHASE_GATE[gate.phase].value}, and "
						f"{len(failed)} machine check(s) failed ({', '.join(failed)})"
					)
				)
			else:
				detail = (
					f"{gate.phase.value} awaits {PHASE_GATE[gate.phase].value}: "
					f"approve it with `{GATE_APPROVE_VERB} {gate.phase.value} --by <you>` "
					f"and run `{RESUME_VERB}`"
				)
			return await _finish(
				service,
				goal_id=goal.id,
				started=started,
				steps=steps,
				terminal=DriverTerminal.GATE_OPEN,
				detail=detail,
				open_gate=gate.phase,
				gate_failures=failed,
				notify=notify,
			)
		action = _next_action(
			state,
			has_draft=await service.latest_draft(goal.id) is not None,
			has_research=any(r.goal_id == goal.id for r in state.research),
			ready=(await service.readiness(goal.id)).is_ready,
		)
		if action is None:
			break
		before = len(service.ledger)
		try:
			detail = await _perform(
				service,
				action,
				state,
				root=root,
				timeout=timeout,
				harness=harness,
				research_harness=research_harness,
			)
		except Exception as exc:
			# A named terminal state rather than a propagating exception, and the
			# catch is broad on purpose: the operator asked to be told when the build
			# finishes, and a traceback on their terminal is not being told. The
			# message is the harness's or the validator's own words, not a summary.
			steps.record(action, DriverOutcome.REFUSED, f"{type(exc).__name__}: {exc}")
			return await _finish(
				service,
				goal_id=goal.id,
				started=started,
				steps=steps,
				terminal=DriverTerminal.FAILED,
				detail=f"{action.name}: {exc}",
				open_gate=None,
				notify=notify,
			)
		if len(service.ledger) == before:
			# The action ran and the log did not grow, which is the definition of an action
			# that did nothing. It is a **waiting** state, not a failure and not a success:
			# `propose-answers` with no reachable model leaves every dimension open for a
			# person, so the next thing that has to happen is `sofact` alone — and looping
			# would re-select the same action forever, which is why this stops rather than
			# `continue`s. Recorded as SKIPPED so the run says what it waited on instead of
			# reporting a step that advanced nothing as ADVANCED.
			steps.record(action, DriverOutcome.SKIPPED, detail)
			return await _finish(
				service,
				goal_id=goal.id,
				started=started,
				steps=steps,
				terminal=DriverTerminal.EXHAUSTED,
				detail=detail,
				open_gate=None,
				notify=notify,
				# Read after the action ran, because that is when the proposals exist:
				# on a reachable model the *first* iteration drafts them and the second
				# finds nothing left to propose, so the flag describes the state this
				# run left behind rather than the one it started in.
				awaiting_attestation=_proposals_waiting(state, goal.id),
			)
		steps.record(action, DriverOutcome.ADVANCED, detail)
		if on_step is not None:
			on_step(steps.taken[-1])
	else:  # pragma: no cover - the bound is a guard against a future non-advancing action
		return await _finish(
			service,
			goal_id=goal.id,
			started=started,
			steps=steps,
			terminal=DriverTerminal.EXHAUSTED,
			detail=f"stopped after {_MAX_ITERATIONS} steps without reaching a terminal state",
			open_gate=None,
			notify=notify,
		)
	state = await service.state()
	delivered = state.delivery
	if delivered is None:
		return await _finish(
			service,
			goal_id=goal.id,
			started=started,
			steps=steps,
			terminal=DriverTerminal.EXHAUSTED,
			detail=(
				"every machine action is discharged and no delivery report exists; the "
				"pipeline is waiting on something this loop does not do"
			),
			open_gate=None,
			notify=notify,
		)
	return await _finish(
		service,
		goal_id=goal.id,
		started=started,
		steps=steps,
		terminal=DriverTerminal.DELIVERED,
		detail=_delivery_detail(delivered),
		open_gate=None,
		notify=notify,
	)


def _delivery_detail(delivered: DeliveryReport) -> str:
	"""One sentence saying what was delivered and what remains open (FR-172).

	The unverified clause count is named because FR-118 makes it the number that decides
	whether a delivery is done, and a terminal state that said only "delivered" would let
	a report with open clauses read as a finished build.
	"""
	unverified = delivered.unverified
	if unverified:
		return f"delivered with {len(unverified)} clause(s) unverified; see the delivery report"
	return "delivered: every clause the contract carries is verified"


async def _perform(
	service: FactoryService,
	action: DriverAction,
	state: ProjectState,
	*,
	root: Path | None,
	timeout: float,
	harness: str | None,
	research_harness: str | None,
) -> str:
	"""Do one action and return a sentence describing what happened (FR-172).

	Each branch is guarded by the same condition :func:`_next_action` used to select it,
	so the two are one rule read twice rather than two rules that could disagree. The
	work itself is all in :class:`~sofact.service.FactoryService`; the driver decides
	*when*, never *what*.

	``harness`` and ``research_harness`` are passed to the two branches that launch a
	child process and to no others: the names are configuration for a dispatch, and
	threading them through the phases that dispatch nothing would suggest they matter
	there.
	"""
	goal = state.latest_goal()
	assert goal is not None, "an action was selected with no goal"
	contract = state.latest_contract(goal.id)
	if action.name == "propose-answers":
		# A model-less deployment is not a failed run. P0 is a deterministic interrogation
		# and the operator is its author, so the driver's job here is to *try* to help and
		# then get out of the way: no model configured, or a model that will not answer,
		# leaves the dimensions open for the questionnaire and `sofact attest`, and the run
		# continues on the next `--resume` once a person has answered. Treating this as
		# FAILED would make the one verb that exists to carry a goal to its first gate
		# refuse to start on every deployment without a reachable endpoint — which is the
		# configuration, not a fault in the goal.
		from sofact.llm import LlmUnavailable

		try:
			proposals = await service.propose_answers(goal.id)
		except LlmUnavailable as exc:
			return (
				f"no proposal: {exc}. Answer the open dimensions by running `sofact`, then "
				f"`{RESUME_VERB}` (FR-173)"
			)
		if not proposals:
			# An empty tuple is not "the model had nothing to say": it means every open
			# dimension already holds a proposal, so this action was selected by a reading
			# of the log that cannot tell "unanswered" from "proposed and unattested" —
			# both are open to ``readiness`` (FR-173), and only the first is a model's to
			# close. Saying "drafted 0 proposal(s)" would report work, and the loop's
			# ledger check would then see no growth and stop anyway, but with a detail
			# describing a draft nobody made.
			#
			# **The verb here is `attest`, not a resume.** This message used to name
			# ``RESUME_VERB``, and that was wrong in the one case that actually reaches it:
			# the ordinary first run on a reachable model drafts all six dimensions, the
			# next iteration selects this action again, and the operator was told to
			# ``build --resume`` — a command that re-selects this same action, proposes
			# nothing again, and prints the same sentence. The run was not waiting on a
			# resume; it was waiting on a person. The line beneath it in the same output
			# already said so (``next_human_verb`` reads ``stopped_on`` and names the
			# questionnaire), so the two halves of one report contradicted each other.
			return (
				"every open dimension already holds a proposal and a person has attested "
				"none of them: read them with `sofact` and confirm the ones you agree with "
				f"using `sofact attest <answer-id> --by <you>`, then `{RESUME_VERB}`. A "
				"resume alone re-selects this action and changes nothing (FR-173)"
			)
		return f"drafted {len(proposals)} proposal(s); a person must attest them"
	if action.name == "draft":
		draft = await service.draft(goal.id)
		return f"drafted {len(draft.stems)} clause stem(s)"
	if action.name == "research":
		# P1 dispatched, then read back. The three calls are in this order and not
		# merged because each records a *different* artefact from the same run's
		# workspace: the run row, the source ledger, and FR-068's per-clause verdicts.
		# A run that left no ledger is refused by ``ledger_from`` with the file it
		# looked for, which is the honest failure — an empty ledger would report that
		# the producer was asked and had nothing to say, which is a different finding.
		record = await service.research(name=research_harness, timeout=timeout)
		ledger = await service.ledger_from(record)
		classification = await service.classification_from(record)
		return (
			f"researched: {len(ledger.sources)} source(s), "
			f"{len(classification.classifications)} clause verdict(s)"
		)
	if contract is None:
		contract = await service.contract(goal.id)
		return f"contracted {len(contract.clauses)} clause(s)"
	if action.name == "specify":
		proposal = await service.specify(contract.id)
		# The document is rendered *before* the gate is presented, because it is what the
		# gate is a gate *on*: ADR-0071 makes P2's artefact the annotated specification, and
		# a driver that opened the gate without writing it would ask a person to approve a
		# structure while the prose that qualifies it was still nowhere on disk. Rendered
		# rather than required, so a run whose ``--root`` is not writable still reaches its
		# gate — with the document recorded in the ledger and the write named as the thing
		# that failed, which is the honest order.
		document = await service.write_specification(contract.id, root=root)
		await _present(
			service, Phase.SPECIFY, (await service.specification_gate(proposal.id)).checks
		)
		open_checks = len(document.gate_failures)
		return (
			f"proposed specification {proposal.id} and rendered {document.id}; its gate is "
			f"now open with {open_checks} machine check(s) outstanding"
		)
	if action.name == "decompose":
		proposal = await service.decompose(contract.id)
		await _present(
			service, Phase.DECOMPOSE, (await service.decomposition_gate(proposal.id)).checks
		)
		return f"proposed decomposition {proposal.id}; its gate is now open"
	if action.name == "plan":
		plan = await service.compile_plan(contract.id)
		# FR-107's audit runs before the gate is presented, so the checks the operator is
		# shown include what the oracles did against an empty workspace. Presenting the
		# gate first and auditing after would show a passing sample gate for a contract
		# whose oracles are satisfied by nothing — the one finding P4 exists to surface.
		audit = await service.audit_oracles(contract.id, timeout=timeout)
		checks = await service.audit_gate_checks(contract.id)
		assert checks is not None, "the audit that just ran left no gate checks"
		await _present(service, Phase.CONTRACT, checks)
		return (
			f"compiled plan {plan.id} with {len(plan.steps)} step(s); "
			f"audited {len(audit.probed)} oracle(s), {len(audit.findings)} satisfied by nothing"
		)
	if action.name == "build":
		plan = state.latest_plan(contract.id)
		assert plan is not None, "build selected with no plan"
		dispatches = await service.dispatch_plan(plan.id, name=harness)
		return f"dispatched {len(dispatches)} step(s)"
	if action.name == "verify":
		plan = state.latest_plan(contract.id)
		assert plan is not None, "verify selected with no plan"
		# The observations first, then the verdict: `run` executes the contract's
		# oracles and records evidence, `verify_contract` judges it. Doing only the
		# second would render a verdict over evidence nobody produced (FR-163).
		await service.run(contract.id, timeout=timeout)
		report = await service.verify_contract(contract.id)
		return f"verified {len(report.verdicts)} clause(s)"
	if action.name == "integrate":
		plan = state.latest_plan(contract.id)
		assert plan is not None, "integrate selected with no plan"
		report = await service.check_integration(plan.id)
		return f"integration checked over {len(report.checks)} check(s)"
	if action.name == "deliver":
		plan = state.latest_plan(contract.id)
		assert plan is not None, "deliver selected with no plan"
		delivered = await service.render_delivery(plan.id, root=root)
		# P8 is a gate like the other three, and it is the one the operator's request
		# ends on: "notify me when it is built". Presenting it here means the run stops
		# with the deploy gate open rather than reporting a delivery nobody approved —
		# and FR-119 makes that approval human and permanent, so there is nothing this
		# loop could do with the gate but show it.
		gate = await service.delivery_gate(delivered.id)
		await _present(service, Phase.DELIVER, gate.checks)
		return _delivery_detail(delivered)
	raise ValueError(f"unknown driver action {action.name!r} (FR-172)")


async def _present(
	service: FactoryService,
	phase: Phase,
	checks: tuple[GateCheck, ...],
) -> None:
	"""Record that ``phase``'s machine half is done and a human has something to look at.

	The machine half of FR-061 and the *only* half this module may call: it moves the
	phase to :attr:`~sofact.views.PhaseStatus.AWAITING_GATE`, which is what makes
	:attr:`~sofact.views.ProjectState.open_gate` non-``None`` and what stops the loop.
	Passing the gate is :meth:`~sofact.service.FactoryService.approve_gate`, and there is
	no call to it anywhere in this file.

	Every phase before ``phase`` is completed first, and that is not bookkeeping:
	:meth:`~sofact.service.FactoryService.advance_phase` refuses a phase whose predecessors
	are incomplete, so a driver that did not close the phases its own work discharged would
	refuse at its own gate. The closure is *derived* from the phase sequence rather than
	written out, so a phase inserted into the pipeline is closed here without an edit —
	the same rule ``test_phase.walk_to`` follows, for the same reason.

	The checks are taken from the gate the service just recorded rather than recomputed
	here. Recomputing would be a second implementation of P2's, P3's and P4's check sets,
	and the two would agree only until one of them was edited — the operator would then be
	shown a checklist that is not the one the approval is decided against.
	"""
	assert checks, (
		f"{phase.value}'s gate carries no machine checks: presenting an empty checklist "
		"would ask a human to approve an artefact the factory never looked at (FR-080)"
	)
	await _close_predecessors(service, phase)
	await service.advance_phase(
		phase,
		PhaseStatus.AWAITING_GATE,
		checks=checks,
		by="factory",
	)


async def _close_predecessors(service: FactoryService, phase: Phase) -> None:
	"""Complete every ungated phase before ``phase``, leaving the gated ones approved.

	A gated predecessor is already ``COMPLETE`` — that is what passing its gate did — so
	the loop skips it rather than re-advancing it, which ``advance_phase`` refuses by
	name ("a phase is not re-entered by advancing it again"). An ungated predecessor is
	the work this run has just done, and marking it complete is the record of that.
	"""
	state = await service.state()
	for earlier in PHASE_SEQUENCE:
		if earlier is phase:
			return
		if earlier in PHASE_GATE:
			continue
		if state.phase_status(earlier) is PhaseStatus.COMPLETE:
			continue
		await service.advance_phase(earlier, PhaseStatus.COMPLETE, by="factory")


async def _finish(
	service: FactoryService,
	*,
	goal_id: str,
	started: datetime,
	steps: _Steps,
	terminal: DriverTerminal,
	detail: str,
	open_gate: Phase | None,
	notify: bool,
	gate_failures: tuple[str, ...] = (),
	awaiting_attestation: bool = False,
) -> DriverRun:
	"""Record the run, notify, and return it (FR-172).

	The notification is composed from the run and the goal statement, and
	:func:`sofact.notify.render_subject` reads ``claims_built`` — so a run that stopped at
	a gate cannot produce a message reading "built", whatever this function is passed.

	One :class:`~sofact.views.DriverRun` is built and reused rather than constructed twice.
	It was built twice — once to compose the notification and once to record — and the two
	copies drifted the moment a field was added to one and not the other: the notification
	would read a run missing ``gate_failures``, so a message about a gate whose checks
	failed would name the verb that refuses it. Two constructions of one object is two
	places for a field to be left out, and the second place is invisible.
	"""
	run_id = uuid7str()
	notification_id: str | None = None
	run = DriverRun(
		id=run_id,
		goal_id=goal_id,
		started_at=started,
		ended_at=now(),
		steps=tuple(steps.taken),
		terminal=terminal,
		terminal_detail=detail,
		open_gate=open_gate,
		gate_failures=gate_failures,
		awaiting_attestation=awaiting_attestation,
	)
	if notify:
		statement = await _statement_of(service, goal_id)
		subject = _render_subject(run, statement)
		record = await service.notify(subject, _body(run, detail), goal_id=goal_id, run_id=run_id)
		notification_id = record.id
		run = run.model_copy(update={"notification_id": notification_id})
	await service.record_driver_run(run)
	return run


def _render_subject(run: DriverRun, statement: str) -> str:
	"""The notification's subject, imported lazily to keep this module's imports flat."""
	from sofact.notify import render_subject

	return render_subject(run, statement)


def _body(run: DriverRun, detail: str) -> str:
	"""The notification's body: the terminal state, the detail, and the next verb (FR-172).

	The next human verb is included because a run that stopped without saying what to
	type next reads as a dead one. :attr:`~sofact.views.DriverRun.next_human_verb` derives
	it from the terminal state, so this cannot print a verb for a finished run.
	"""
	lines = [
		f"terminal: {run.terminal.value}",
		detail,
	]
	next_verb = run.next_human_verb
	if next_verb is not None:
		lines.append(f"next: {next_verb}")
	return "\n".join(lines)


async def _statement_of(service: FactoryService, goal_id: str) -> str:
	"""The goal's statement, or a placeholder if it is gone (FR-172)."""
	try:
		return (await service.goal(goal_id)).statement
	except KeyError:  # pragma: no cover - a goal_id from the log is a goal in the log
		return "(goal not found)"


_MAX_ITERATIONS: Final = 64
"""A bound on the loop, so a future action that does not advance cannot spin forever.

Large enough that no legitimate run reaches it — a full pipeline is ten actions plus four
gate stops — and its only purpose is to turn a non-advancing action into an
``EXHAUSTED`` terminal state rather than a hang.
"""
