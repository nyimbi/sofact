"""Orchestration: the only module that both reads the log and reaches the network.

Everything above this is pure (models, fold, gates); everything below is a
presentation adapter. Keeping the composition here means the CLI holds no policy —
it prints what the service decides.

Home resolution is explicit and hermetic. There is no implicit global state
directory: unset, SoFact writes to ``./.sofact``, and ``SOFACT_HOME`` overrides it.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

from sofact._uuid7 import uuid7str
from sofact.contract import ground_truth_debt, suggest_oracle
from sofact.decomposition import approve, gate, propose
from sofact.elicitation import (
	DimensionSpec,
	advise_prompt,
	assess,
	draft_stems,
	next_open,
	spec_for,
)
from sofact.execution import DEFAULT_TIMEOUT_SECONDS as DEFAULT_ORACLE_TIMEOUT_SECONDS
from sofact.execution import OracleRunner, digest_tree
from sofact.git import ensure_module_branch, seal_branch
from sofact.harness import (
	DEFAULT_PROBE_GOAL,
	DEFAULT_PROBE_TIMEOUT_SECONDS,
	DEFAULT_STDERR_TAIL_BYTES,
	DEFAULT_TOOLS,
	SPECS,
	ConfiguredHarnessAdapter,
	HarnessSpec,
)
from sofact.harness import (
	spec_for as harness_spec_for,
)
from sofact.integration import integrate
from sofact.ledger import LEDGER_FILENAME, LOCK_FILENAME, Ledger, LedgerEntry
from sofact.llm import DEFAULT_MODEL, LlmClient, LlmUnavailable
from sofact.planner import (
	DEFAULT_REPAIR_ATTEMPTS,
	check_integrity,
	compile_plan,
	refutation_diagnosis,
	revised_plan,
)
from sofact.state import fold
from sofact.verification import verdict_cache_key, verify
from sofact.views import (
	PHASE_GATE,
	PHASE_SEQUENCE,
	Advice,
	ChainStatus,
	Clause,
	ClauseVerdict,
	CompletionClaim,
	Contract,
	DeclarationPrecision,
	Decomposition,
	DecompositionGate,
	DispatchRecord,
	ElicitationAnswer,
	ElicitationDimension,
	Evidence,
	GateCheck,
	Goal,
	GoalPlan,
	GoalStep,
	GoalStyle,
	HarnessProfile,
	IntegrationReport,
	IntegrityCheck,
	LedgerKind,
	OracleDeclaration,
	Phase,
	PhaseAdvance,
	PhaseStatus,
	ProjectState,
	Readiness,
	RepairAttempt,
	RepairOutcome,
	ResearchMode,
	ResearchRecord,
	SpecificationDraft,
	StepBudget,
	StepOutcome,
	VerdictOutcome,
	VerificationReport,
	now,
)

__all__ = [
	"DEFAULT_HARNESS",
	"DEFAULT_HOME_DIRNAME",
	"FactoryService",
	"latest_run_id",
	"refuted_steps",
	"resolve_home",
	"resolve_tools",
]

DEFAULT_HOME_DIRNAME = ".sofact"

DEFAULT_HARNESS = "pi"
DEFAULT_RESEARCH_HARNESS = "pi-research"

RESEARCH_TIMEOUT_SECONDS: Final = 900.0
"""Wall clock for one research dispatch. The extension's own loop timeout (240 s deep,
360 s super) is the tighter bound on a local model; this is the outer session's ceiling."""


research_url_pattern = re.compile(r"https?://[^\s()>]+")


def extract_source_urls(text: str) -> tuple[str, ...]:
	"""URLs cited in a research report, deduplicated in order of first appearance."""
	seen: list[str] = []
	for raw in research_url_pattern.findall(text):
		cleaned = raw.rstrip(".,;:")
		if cleaned and cleaned not in seen:
			seen.append(cleaned)
	return tuple(seen)


def research_goal(query: str, *, mode: ResearchMode) -> str:
	"""The research session's goal, authored with zero model involvement (FR-167).

	SoFact writes the prompt; the model performs the research. The goal names the tool,
	the exact query, and the two files the workspace must end up holding, because the
	artefact protocol — not the producer's honesty — is what makes the run observable.
	"""
	assert query.strip(), "a research query must not be empty"
	tool = "super_deep_research" if mode is ResearchMode.SUPER else "deep_research"
	return (
		f"Research the following subject using the {tool} tool.\n\n"
		f"Subject: {query}\n\n"
		f"Call the {tool} tool exactly once, with the query: {query}\n\n"
		"When the tool finishes: write the full report text it returned, verbatim and "
		"unchanged, to research-report.md in the working directory; then copy the file "
		"~/.forecastx-reports/<the report id the tool reported>/meta.json to "
		"research-meta.json in the working directory. Change the content of neither "
		"file. Then reply DONE."
	)


"""The harness used when ``SOFACT_HARNESS`` is unset.

``pi`` rather than ``dsh`` because it is the one whose dispatch argv has actually been
witnessed end to end ([S19], measured). ``dsh`` is the better harness on capability —
it is the only one of the two with a structured completion signal — but its
non-interactive argv is unverified (``--profile headless`` is broken in 0.1.5rc1), and
defaulting to an argv nobody has run would make the first dispatch a debugging session
rather than a build.
"""


def latest_run_id(contract: Contract, evidence: Iterable[Evidence]) -> str | None:
	"""The run that most recently observed this contract, by log order.

	``None`` when nothing has observed it yet, or when the observations carry no run
	identity at all — a log written before run ids existed, or evidence recorded by
	hand. Both cases mean "undifferentiated", which is the same meaning the absence of a
	run has everywhere else, so the degenerate case needs no separate branch.
	"""
	clause_ids = {clause.id for clause in contract.clauses}
	identified = [
		item.run_id for item in evidence if item.run_id is not None and item.clause_id in clause_ids
	]
	return identified[-1] if identified else None


def refuted_steps(plan: GoalPlan, report: VerificationReport | None) -> tuple[str, ...]:
	"""Steps whose own clauses the latest verdict **refutes** (FR-142).

	The distinction between a refutation and a gap is the whole point. ``VIOLATED`` is
	evidence that the step's clauses do not hold, so a dependent must not build on it.
	``INSUFFICIENT`` is the absence of an oracle, which grants no autonomy (FR-109) but
	is not a refutation — halting on it would make Mode G, whose oracles are weaker by
	construction, unbuildable. A step covering no clause is never refuted: there is
	nothing to refute, and a bootstrap step would otherwise block the build forever.
	"""
	if report is None:
		return ()
	verdicts = {verdict.clause_id: verdict.outcome for verdict in report.verdicts}
	return tuple(
		step.id
		for step in plan.steps
		if any(verdicts.get(clause_id) is VerdictOutcome.VIOLATED for clause_id in step.clause_ids)
	)


def resolve_home(home: Path | None = None) -> Path:
	"""Where this instance keeps its log.

	Precedence: explicit argument, then ``SOFACT_HOME``, then ``./.sofact``.
	"""
	if home is not None:
		return Path(home).expanduser()
	from_env = os.environ.get("SOFACT_HOME")
	if from_env:
		return Path(from_env).expanduser()
	return Path.cwd() / DEFAULT_HOME_DIRNAME


def resolve_tools(tools: str | None = None) -> str:
	"""Which tools a dispatch hands the harness: explicit, then ``SOFACT_TOOLS``, then default.

	Operator-tunable rather than baked into the adapter, because which tools a producer may
	use is the operator's decision and the CLI is where the operator already is (FR-156).
	An empty value is refused rather than forwarded: ``--tools ""`` renders an empty
	allowlist, which disables every tool, and a producer that silently cannot write is
	indistinguishable from one that failed.
	"""
	if tools is None:
		tools = os.environ.get("SOFACT_TOOLS")
	if tools is None:
		return DEFAULT_TOOLS
	if not tools.strip():
		raise ValueError(
			"the tool set is empty; an empty allowlist disables every tool, so a producer "
			"given it cannot write rather than failing"
		)
	return tools


class FactoryService:
	"""Intent front end: start a goal, interrogate it, draft a specification."""

	def __init__(
		self,
		home: Path | None = None,
		llm: LlmClient | None = None,
		*,
		specs: Mapping[str, HarnessSpec] | None = None,
	) -> None:
		"""``specs`` is the harness table this instance may dispatch to.

		It defaults to the two SoFact ships. A deployment that wants a third harness
		passes one here rather than patching module state (FR-156); an operator who can
		name a harness without editing code is also an operator who can be told which
		harnesses exist, which is what :meth:`harness_table` reports.
		"""
		self.home = resolve_home(home)
		self.ledger = Ledger(self.home / LEDGER_FILENAME)
		self.llm = llm
		self._specs: Mapping[str, HarnessSpec] = SPECS if specs is None else dict(specs)
		self._state: ProjectState | None = None

	def __repr__(self) -> str:
		return f"FactoryService(home={self.home}, entries={len(self.ledger)})"

	# ------------------------------------------------------------------ state

	async def state(self) -> ProjectState:
		"""Current state, folded from the log and cached until the next append.

		The chain is re-verified before the fold is trusted: deriving state from a
		log that may have been edited would launder the edit into a plausible-looking
		answer.
		"""
		if self._state is None:
			self.ledger.require_intact()
			self._state = fold(self.ledger.entries())
		return self._state

	async def verify_ledger(self) -> ChainStatus:
		"""Re-check the chain. Exposed because the audit trail is a deliverable."""
		return self.ledger.verify_chain()

	async def entries(self) -> tuple[LedgerEntry, ...]:
		"""The raw log, oldest first."""
		return self.ledger.entries()

	def _commit(self, kind: LedgerKind, payload: dict[str, Any]) -> LedgerEntry:
		"""Append an event and invalidate the derived-state cache."""
		entry = self.ledger.append(kind, payload)
		self._state = None
		return entry

	# ------------------------------------------------------- the phase machine

	async def current_phase(self) -> Phase:
		"""The phase the pipeline is in (FR-060)."""
		return (await self.state()).current_phase

	async def phase_status(self, phase: Phase) -> PhaseStatus:
		"""Where ``phase`` stands, ``PENDING`` if no transition has named it."""
		return (await self.state()).phase_status(phase)

	async def open_gate(self) -> PhaseAdvance | None:
		"""The gate the pipeline is stopped at, or ``None`` (FR-061).

		The one question a scheduler must ask before doing machine work. It is a method
		rather than a field so that no caller can hold a stale answer across an append.
		"""
		return (await self.state()).open_gate

	async def advance_phase(
		self,
		phase: Phase,
		status: PhaseStatus,
		*,
		by: str = "factory",
		checks: tuple[GateCheck, ...] = (),
		note: str | None = None,
	) -> PhaseAdvance:
		"""Record a phase transition (FR-060).

		Deliberately *not* the way a gate is passed. This is the machine half: it can
		move an ungated phase, and it can move a gated phase to
		:attr:`~sofact.views.PhaseStatus.AWAITING_GATE`, but
		:class:`~sofact.views.PhaseAdvance` refuses to construct a completed gate phase
		with no approver — so there is no call to this method, with any arguments, that
		could pass a gate. The human half is :meth:`approve_gate`, and FR-061's hard stop
		is the type boundary between them rather than a check either one performs.
		"""
		state = await self.state()
		previous = state.phase_status(phase)
		if previous is PhaseStatus.COMPLETE:
			raise ValueError(
				f"{phase.value} is already complete; a phase is not re-entered by "
				"advancing it again (FR-060)"
			)
		if status is PhaseStatus.COMPLETE and phase in PHASE_GATE:
			raise ValueError(
				f"{phase.value} is a gate phase: use approve_gate, which names the human "
				f"who passed {PHASE_GATE[phase].value} (FR-061)"
			)
		order = PHASE_SEQUENCE.index(phase)
		# Every earlier phase must be complete. This single check is what makes FR-061
		# structural: the only route to P5 runs through P2 and P3, so there is no
		# configuration in which the factory reaches machine work past an unapproved
		# gate. It also subsumes ordering — a later phase cannot have been worked while
		# an earlier one is incomplete, because reaching the later one required the
		# earlier one to complete first. An explicit "is a later phase already done"
		# guard was written here first and then removed as unreachable: a guard that
		# cannot fire is a claim about behaviour that nothing tests.
		behind = [
			p.value
			for p in PHASE_SEQUENCE[:order]
			if state.phase_status(p) is not PhaseStatus.COMPLETE
		]
		if behind:
			raise ValueError(
				f"{phase.value} cannot start while {behind[0]} is not complete: every "
				"earlier phase must finish, so no phase can be reached without passing "
				"the gates before it (FR-061, NFR-028)"
			)
		if status is PhaseStatus.AWAITING_GATE and phase not in PHASE_GATE:
			raise ValueError(f"{phase.value} has no gate to await (FR-061)")
		if status is PhaseStatus.ACTIVE:
			blocking = state.open_gate
			if blocking is not None:
				raise ValueError(
					f"{blocking.phase.value} is awaiting {PHASE_GATE[blocking.phase].value}: "
					"no machine work downstream of an unapproved gate (FR-061)"
				)
		advance = PhaseAdvance(
			phase=phase,
			status=status,
			at=now(),
			by=by,
			checks=checks,
			note=note,
		)
		self._commit(LedgerKind.PHASE_ADVANCED, {"advance": advance.model_dump(mode="json")})
		return advance

	async def approve_gate(self, phase: Phase, *, by: str) -> PhaseAdvance:
		"""Pass ``phase``'s gate, naming who did (FR-061, FR-087).

		The only path to a completed gate phase. It refuses when the machine half has
		not been presented — a gate nobody has been shown is not a gate that was passed
		— and it refuses a failed check for the same reason
		:class:`~sofact.views.DecompositionGate` does: approval cannot make an unsound
		artefact sound.
		"""
		assert by.strip(), "a gate approval names who approved it"
		state = await self.state()
		gate = PHASE_GATE.get(phase)
		if gate is None:
			raise ValueError(f"{phase.value} has no gate to approve (FR-061)")
		if state.phase_status(phase) is PhaseStatus.COMPLETE:
			raise ValueError(f"{phase.value} is already complete")
		pending = state.phase_advance(phase)
		if pending is None or pending.status is not PhaseStatus.AWAITING_GATE:
			raise ValueError(
				f"{phase.value} is not awaiting {gate.value}; there is nothing to approve "
				"until the phase has presented its machine checks (FR-080)"
			)
		failed = tuple(c for c in pending.checks if not c.passed)
		if failed:
			names = ", ".join(c.name for c in failed)
			raise ValueError(
				f"{gate.value} has failed machine checks ({names}); approval cannot make "
				"an unsound artefact sound (FR-061)"
			)
		approved = pending.model_copy(
			update={
				"status": PhaseStatus.COMPLETE,
				"approved_by": by,
				"approved_at": now(),
				"by": by,
			}
		)
		self._commit(LedgerKind.PHASE_ADVANCED, {"advance": approved.model_dump(mode="json")})
		return approved

	# --------------------------------------------------------------- P0: goals

	async def start(self, statement: str, *, by: str = "operator") -> Goal:
		"""Create a goal from a stated intent.

		No interrogation happens here. The statement is recorded verbatim and
		immediately suspect — it is the thing being interrogated, not a requirement.
		"""
		assert statement.strip(), "a goal needs a statement"
		goal = Goal(id=uuid7str(), statement=statement.strip(), created_at=now())
		self._commit(LedgerKind.GOAL_CREATED, {"goal": goal.model_dump(mode="json"), "by": by})
		return goal

	async def current_goal(self) -> Goal | None:
		"""The most recently created goal, or ``None``."""
		state = await self.state()
		return state.latest_goal()

	async def goal(self, goal_id: str) -> Goal:
		"""Fetch a goal by id, raising if it is unknown."""
		state = await self.state()
		found = state.goal(goal_id)
		if found is None:
			raise KeyError(f"no such goal: {goal_id}")
		return found

	# -------------------------------------------------------- P0: interrogation

	async def answer(
		self,
		goal_id: str,
		dimension: ElicitationDimension,
		text: str,
		*,
		by: str = "operator",
	) -> ElicitationAnswer:
		"""Record an answer. Never rejects one.

		Thin answers are recorded and reported as unresolved rather than refused.
		Refusing would discard the operator's words, and the words are the only thing
		the draft is allowed to be made of.
		"""
		assert text.strip(), "an answer needs text"
		await self.goal(goal_id)
		answer = ElicitationAnswer(
			id=uuid7str(),
			goal_id=goal_id,
			dimension=dimension,
			text=text.strip(),
			answered_by=by,
			at=now(),
		)
		self._commit(
			LedgerKind.ANSWER_RECORDED,
			{"answer": answer.model_dump(mode="json")},
		)
		return answer

	async def readiness(self, goal_id: str) -> Readiness:
		"""The gate's verdict on ``goal_id``."""
		state = await self.state()
		return assess(goal_id, state.answers_for(goal_id))

	async def open_question(
		self,
		goal_id: str,
	) -> tuple[ElicitationDimension, DimensionSpec] | None:
		"""The next dimension to ask about, or ``None`` when the goal is ready."""
		readiness = await self.readiness(goal_id)
		dimension = next_open(readiness)
		return None if dimension is None else (dimension, spec_for(dimension))

	async def advise(self, goal_id: str, dimension: ElicitationDimension) -> Advice:
		"""Ask the model what the latest answer for ``dimension`` leaves unverifiable.

		Advisory only, and never fatal. Unavailability is returned as a value rather
		than raised so that the deterministic questionnaire is always usable on its
		own — the model is an accelerant, not a dependency.
		"""
		state = await self.state()
		latest = [a for a in state.answers_for(goal_id) if a.dimension == dimension]
		if not latest:
			return Advice(dimension=dimension, unavailable="nothing answered yet")
		if self.llm is None:
			return Advice(dimension=dimension, unavailable="no model configured")

		system, user = advise_prompt(spec_for(dimension), latest[-1].text)
		try:
			text = await self.llm.complete(system=system, user=user)
		except LlmUnavailable as exc:
			return Advice(dimension=dimension, unavailable=str(exc))

		self._commit(LedgerKind.ADVISOR_NOTE, {"dimension": dimension.value, "text": text})
		return Advice(dimension=dimension, text=text)

	# ------------------------------------------------------------ P2: drafting

	async def draft(self, goal_id: str) -> SpecificationDraft:
		"""Draft clause stems from a fully resolved elicitation.

		Raises :class:`ValueError` if the goal is not ready. The draft is recorded,
		so a specification can be traced back through the answers to the statement
		that produced it.
		"""
		state = await self.state()
		draft = draft_stems(goal_id, state.answers_for(goal_id))
		self._commit(LedgerKind.DRAFT_CREATED, {"draft": draft.model_dump(mode="json")})
		return draft

	async def latest_draft(self, goal_id: str) -> SpecificationDraft | None:
		"""Most recent draft for a goal, if one exists."""
		state = await self.state()
		matching = [d for d in state.drafts if d.goal_id == goal_id]
		return matching[-1] if matching else None

	# ---------------------------------------------------- P2: oracles, contract

	async def contract(
		self,
		goal_id: str,
		*,
		commands: str | None = None,
		version: int = 1,
	) -> Contract:
		"""Assign an oracle to every clause stem, or refuse.

		Without ``commands``, every stem gets a *suggested* oracle that names no
		command. That is deliberate: SoFact does not know how to run the operator's
		system, and inventing a command would yield a real green result meaning
		nothing. The contract is then honest about being unexecutable, and
		:func:`sofact.contract.ground_truth_debt` measures exactly that.

		With ``commands``, one shell command is attached to every clause. That is only
		meaningful for a contract expressing a single obligation; it exists so the
		whole pipeline can be exercised end to end without pretending the assignment
		is clever.
		"""
		draft = await self.latest_draft(goal_id)
		if draft is None:
			raise ValueError(f"no draft for goal {goal_id}; draft one first")
		# An untyped caller can hand this a list, and ``model_copy`` would store it
		# without validating: the ledger would then hold an entry that cannot fold,
		# because the replay validates what the write did not. Constructing through
		# validation makes the refusal happen here, where the message can name the
		# parameter, instead of at the next read of the log.
		assert commands is None or isinstance(commands, str), (
			f"commands must be one shell command, got {type(commands).__name__}"
		)

		oracles: dict[str, OracleDeclaration] = {}
		for stem in draft.stems:
			suggested = suggest_oracle(stem)
			oracles[stem.id] = (
				suggested
				if commands is None
				else OracleDeclaration.model_validate(
					{**suggested.model_dump(mode="python"), "command_hint": commands},
				)
			)

		built = Contract.from_draft(draft, oracles, version=version)
		self._commit(
			LedgerKind.CONTRACT_CREATED,
			{"contract": built.model_dump(mode="json"), "debt": ground_truth_debt(built)},
		)
		return built

	async def latest_contract(self, goal_id: str) -> Contract | None:
		"""Most recent contract for a goal, if one exists."""
		state = await self.state()
		return state.latest_contract(goal_id)

	async def contract_by_id(self, contract_id: str) -> Contract:
		"""Fetch a contract by id, raising if it is unknown."""
		state = await self.state()
		found = state.contract(contract_id)
		if found is None:
			raise KeyError(f"no such contract: {contract_id}")
		return found

	# ------------------------------------------------------------ P6: execution

	async def run(
		self,
		contract_id: str,
		*,
		workspace: Path | None = None,
		timeout: float = DEFAULT_ORACLE_TIMEOUT_SECONDS,
	) -> tuple[Evidence, ...]:
		"""Execute the contract's executable oracles and record the observations.

		Nothing here concludes anything. Observations are appended with their payload
		hash; :meth:`verify_contract` judges them, in a different module.
		"""
		contract = await self.contract_by_id(contract_id)
		workdir = workspace or (self.home / "workspace")
		assert workdir.is_dir(), f"workspace does not exist: {workdir}"
		produced = await OracleRunner(
			workdir,
			timeout=timeout,
			run_id=uuid7str(),
		).run_all(contract)
		for item in produced:
			self._commit(
				LedgerKind.EVIDENCE_RECORDED,
				{"evidence": item.model_dump(mode="json")},
			)
		return produced

	# ------------------------------------------------------------ P6: the verdict

	async def verify_contract(
		self,
		contract_id: str,
		*,
		run_id: str | None = None,
	) -> VerificationReport:
		"""Render a verdict for every clause, from the evidence in the log.

		Distinct from :meth:`verify_ledger`: this judges the *artefact*, that one
		judges the *record*. Conflating them would let a tampered log masquerade as a
		passing build.

		Scoped to the most recent *run* of this contract's oracles unless one is named
		(FR-006: a result older than the change under test is invalid). A verdict that
		weighed the entire history would answer "has this clause ever failed?" and would
		leave a repaired clause permanently refuted — an unrepairable build reported as a
		dishonest producer.
		"""
		contract = await self.contract_by_id(contract_id)
		state = await self.state()
		selected = run_id if run_id is not None else latest_run_id(contract, state.evidence)
		report = verify(contract, state.evidence, run_id=selected)
		self._commit(
			LedgerKind.VERDICT_RENDERED,
			{"report": report.model_dump(mode="json")},
		)
		return report

	async def check_dispatch(
		self,
		plan_id: str,
		dispatch_id: str,
		*,
		timeout: float = DEFAULT_ORACLE_TIMEOUT_SECONDS,
		reuse: bool = True,
	) -> VerificationReport | None:
		"""Run P6 over the workspace a **completed** dispatch leaves behind (FR-163).

		The trigger is the session's own outcome, never the producer's word: a declaration
		is recorded as its own row and is not an input, because the verdict comes from
		:func:`sofact.verification.verify`, whose signature has nowhere to put a claim.
		Gating this on a declaration made the *default* harness unverifiable — ``pi`` has no
		completion event, so nothing was ever checked while ``dispatch`` still exited 0.

		The verdict is **keyed, then reused** (FR-006): before any oracle runs, the workspace
		is digested and combined with the contract and oracle-set hashes. A previous verdict
		rendered against the same key holds without re-running, because every input it weighed
		is bit-for-bit present — a nine-step plan through one workspace re-runs the oracles
		only when a step actually changed the tree. ``reuse=False`` re-runs regardless; the
		reused verdict is committed as its own row (``verdict.reused``) and names the moment
		of the verdict it stands in for, so the log shows a reuse as a reuse and not as a
		second measurement.

		Returns ``None`` when the session did not complete. A failed or budget-exhausted
		dispatch was still changing the tree, and a verdict on a half-built artefact is a
		manufactured signal — the run's own outcome already says what happened.

		The oracles run in the *dispatch's* workspace, because that is where the session
		worked; checking a different tree would produce a verdict about an artefact no
		session wrote. A contract whose clauses are all unexecutable runs zero commands and
		still renders a verdict, all ``INSUFFICIENT`` — the absence of a report and a report
		that corroborates nothing are different facts, and ``declaration_precision`` must be
		able to tell them apart.
		"""
		plan = await self.plan_by_id(plan_id)
		state = await self.state()
		record = state.dispatch(dispatch_id)
		if record is None or record.plan_id != plan.id:
			raise KeyError(f"plan {plan_id} has no dispatch {dispatch_id}")
		if record.outcome is not StepOutcome.COMPLETED:
			return None

		contract = await self.contract_by_id(plan.contract_id)
		workdir = Path(record.workspace)
		assert workdir.is_dir(), f"dispatch workspace does not exist: {workdir}"
		artefact = digest_tree(workdir)
		key = verdict_cache_key(contract, artefact)
		state = await self.state()
		if reuse:
			for prior in reversed(state.reports):
				if prior.contract_id != contract.id or prior.cache_key != key:
					continue
				reused = VerificationReport(
					contract_id=prior.contract_id,
					contract_hash=prior.contract_hash,
					weakest_oracle_rank=prior.weakest_oracle_rank,
					ceiling=prior.ceiling,
					verdicts=prior.verdicts,
					at=now(),
					run_id=prior.run_id,
					cache_key=prior.cache_key,
					reused_from=prior.at,
				)
				self._commit(
					LedgerKind.VERDICT_REUSED,
					{"report": reused.model_dump(mode="json")},
				)
				return reused
		run_id = uuid7str()
		produced = await OracleRunner(
			workdir,
			timeout=timeout,
			run_id=run_id,
		).run_all(contract)
		for item in produced:
			self._commit(
				LedgerKind.EVIDENCE_RECORDED,
				{"evidence": item.model_dump(mode="json")},
			)
		report = verify(contract, produced, run_id=run_id, cache_key=key)
		self._commit(
			LedgerKind.VERDICT_RENDERED,
			{"report": report.model_dump(mode="json")},
		)
		return report

	async def latest_report(self, contract_id: str) -> VerificationReport | None:
		"""Most recent verdict rendered for a contract, if any."""
		state = await self.state()
		return state.latest_report(contract_id)

	# ------------------------------------------------------------- producer claims

	async def declare_completion(
		self,
		goal_id: str,
		*,
		by: str,
		note: str | None = None,
	) -> CompletionClaim:
		"""Record a producer's assertion that it is finished.

		Recorded, and deliberately never consulted by :meth:`verify_contract`. This
		method exists so the boundary is visible in the API and not only in the types:
		declaring completion is something a producer may do, and it changes no verdict
		(FR-138).
		"""
		assert by.strip(), "a claim needs an author"
		await self.goal(goal_id)
		claim = CompletionClaim(
			id=uuid7str(),
			goal_id=goal_id,
			declared_by=by.strip(),
			note=note,
			at=now(),
		)
		self._commit(LedgerKind.CLAIM_DECLARED, {"claim": claim.model_dump(mode="json")})
		return claim

	# ------------------------------------------------- P3: contract to goal plan

	# ------------------------------------------------------- P3: decomposition

	async def decompose(self, contract_id: str) -> Decomposition:
		"""Propose modules for a contract, and gate the proposal (FR-087).

		Proposing and gating are one call because a proposal nobody gated is not an
		artefact the factory can act on, and recording the proposal without its checks
		would leave the log showing an ungated architecture with no reason why. The gate
		result is recorded *unapproved*: FR-087's human half is
		:meth:`approve_decomposition`, and no code path here can set it.
		"""
		contract = await self.contract_by_id(contract_id)
		proposal = propose(contract)
		self._commit(
			LedgerKind.DECOMPOSITION_PROPOSED,
			{"decomposition": proposal.model_dump(mode="json")},
		)
		result = gate(proposal, contract)
		self._commit(
			LedgerKind.DECOMPOSITION_GATED,
			{"gate": result.model_dump(mode="json")},
		)
		return proposal

	async def latest_decomposition(self, contract_id: str) -> Decomposition | None:
		"""Most recent proposal for a contract, if any (FR-094: revisions are normal)."""
		state = await self.state()
		return state.latest_decomposition(contract_id)

	async def decomposition_gate(self, decomposition_id: str) -> DecompositionGate:
		"""The gate result for a decomposition, raising if it was never gated."""
		state = await self.state()
		found = state.latest_gate(decomposition_id)
		if found is None:
			raise KeyError(f"decomposition {decomposition_id} was never gated")
		return found

	async def approve_decomposition(
		self,
		decomposition_id: str,
		*,
		by: str,
	) -> DecompositionGate:
		"""Record the operator's approval of a decomposition (FR-087).

		Refuses when the machine half failed, and refuses when the decomposition is not
		the one that was gated. An approval is the operator's judgement about
		architecture — the one thing §7.1 says no oracle covers — so it may not be
		recorded against a proposal the operator did not see.
		"""
		state = await self.state()
		found = state.decomposition(decomposition_id)
		if found is None:
			raise KeyError(f"no such decomposition: {decomposition_id}")
		contract = await self.contract_by_id(found.contract_id)
		latest = state.latest_decomposition(found.contract_id)
		if latest is not None and latest.id != found.id:
			raise ValueError(
				f"decomposition {decomposition_id} has been superseded by {latest.id}; "
				"approving a revision that is no longer current would approve a proposal "
				"the operator cannot be looking at (FR-094)"
			)
		# Recomputed rather than read from the log: the log holds the gate as it was
		# rendered, and approving must be decided against the decomposition as it *is*.
		# A stale gate row would otherwise let a revision be approved on an earlier
		# revision's passing checks.
		approved = approve(gate(found, contract), by=by)
		self._commit(
			LedgerKind.DECOMPOSITION_GATED,
			{"gate": approved.model_dump(mode="json")},
		)
		return approved

	async def require_approved_decomposition(self, contract_id: str) -> Decomposition:
		"""The contract's approved decomposition, or a refusal (FR-061).

		The hard stop. Planning a contract whose decomposition is unapproved is machine
		work downstream of an unapproved gate, which FR-061 forbids under every
		configuration — so the refusal is here, at the one call site that could proceed,
		rather than in a caller's discipline.
		"""
		state = await self.state()
		proposal = state.latest_decomposition(contract_id)
		if proposal is None:
			raise ValueError(
				f"contract {contract_id} has no decomposition; P3 is a gate and must be "
				"proposed and approved before anything is planned (FR-087)"
			)
		result = state.latest_gate(proposal.id)
		if result is None:
			raise ValueError(f"decomposition {proposal.id} was never gated")
		if not result.is_satisfied:
			reasons = "; ".join(f"{c.name}: {c.detail}" for c in result.failed)
			raise ValueError(
				"cannot proceed past P3: "
				+ ("the operator has not approved it (FR-087)" if not result.is_approved else "")
				+ (f" machine checks failed -- {reasons}" if reasons else "")
			)
		return proposal

	async def compile_plan(
		self,
		contract_id: str,
		*,
		budget: StepBudget | None = None,
		goal_style: GoalStyle = GoalStyle.LABELLED,
		require_approval: bool = True,
	) -> GoalPlan:
		"""Compile a contract into ordered goal sessions (FR-136).

		Deterministic and model-free: no prompt here is drafted by an LLM, because a
		compiler that let a model write the goal would make FR-139's "did the producer
		rewrite its own objective?" check a comparison of the compiler against itself.

		``require_approval`` defaults to **true**, because FR-061 says there must be no
		configuration under which the factory proceeds past an unapproved gate. The flag
		exists only so a test or a demonstration can compile a plan without first
		standing up an operator, and it is named for what it turns off rather than for
		what it turns on.
		"""
		contract = await self.contract_by_id(contract_id)
		if require_approval:
			await self.require_approved_decomposition(contract_id)
		plan = compile_plan(contract, budget=budget, goal_style=goal_style)
		self._commit(
			LedgerKind.PLAN_COMPILED,
			{"plan": plan.model_dump(mode="json")},
		)
		return plan

	async def latest_plan(self, contract_id: str) -> GoalPlan | None:
		"""Most recent plan compiled from a contract, if any."""
		state = await self.state()
		return state.latest_plan(contract_id)

	async def plan_by_id(self, plan_id: str) -> GoalPlan:
		"""Fetch a plan by id, raising if it is unknown."""
		state = await self.state()
		found = state.plan(plan_id)
		if found is None:
			raise KeyError(f"no such plan: {plan_id}")
		return found

	# ------------------------------------------------ FR-058: harness discovery

	def harness_name(self, override: str | None) -> str:
		"""Which harness to use: explicit, then ``SOFACT_HARNESS``, then a default.

		The default is :data:`DEFAULT_HARNESS` when the configured table contains it. A
		table that does not would otherwise be unusable without also exporting a variable:
		the default was hardcoded to a harness the deployment never registered, so the
		injected table was ignored on every path that took the default (FR-156). When the
		default is absent a table with exactly one entry names itself; an ambiguous table
		is an error, because silently picking one would dispatch to an arbitrary harness.
		"""
		explicit = override or os.environ.get("SOFACT_HARNESS")
		if explicit is not None:
			return explicit
		if DEFAULT_HARNESS in self._specs:
			return DEFAULT_HARNESS
		if len(self._specs) == 1:
			return next(iter(self._specs))
		known = ", ".join(sorted(self._specs)) or "none"
		raise KeyError(
			f"no default harness: {DEFAULT_HARNESS!r} is not among the configured "
			f"harnesses ({known}); name one explicitly"
		)

	def harness_table(self) -> Mapping[str, HarnessSpec]:
		"""The harnesses this instance is allowed to dispatch to, by name."""
		return dict(self._specs)

	def adapter(
		self,
		name: str | None = None,
		*,
		workspace: Path | None = None,
		model: str | None = None,
		tools: str | None = None,
	) -> ConfiguredHarnessAdapter:
		"""Build the adapter for one harness. Configuration, never a ledger event.

		Sessions and the workspace live under the SoFact home rather than in the
		operator's checkout: a factory that wrote agent sessions into whatever
		directory it happened to be run from would put its own debris in the repository
		it was asked to build.
		"""
		resolved = self.harness_name(name)
		spec = harness_spec_for(resolved, self._specs)
		workdir = Path(workspace) if workspace is not None else (self.home / "workspace")
		sessions = self.home / "sessions" / resolved
		sessions.mkdir(parents=True, exist_ok=True)
		workdir.mkdir(parents=True, exist_ok=True)
		return ConfiguredHarnessAdapter(
			spec,
			workspace=workdir,
			session_dir=sessions,
			model=model or os.environ.get("SOFACT_MODEL") or DEFAULT_MODEL,
			tools=resolve_tools(tools),
			probe_timeout=DEFAULT_PROBE_TIMEOUT_SECONDS,
		)

	async def probe_harness(
		self,
		name: str | None = None,
		*,
		workspace: Path | None = None,
		model: str | None = None,
		tools: str | None = None,
		timeout: float | None = None,
		goal_text: str | None = None,
		deep: bool = True,
	) -> HarnessProfile:
		"""Attempt a harness and record what was observed (FR-148).

		Raises :class:`~sofact.harness.HarnessBinaryMissing` when the executable is
		absent — that is a fact about this machine, not about the harness, and recording
		it as an unprobed capability would libel the harness.

		``deep=False`` (``--quick``) skips the rows that need a second child. That is a
		deliberate trade of coverage for time, and it is recorded as such: the skipped rows
		say they were skipped rather than pretending they were looked at.
		"""
		adapter = self.adapter(name, workspace=workspace, model=model, tools=tools)
		profile = await adapter.probe(
			goal_text=goal_text or DEFAULT_PROBE_GOAL,
			timeout=timeout,
			deep=deep,
		)
		self._commit(
			LedgerKind.CAPABILITY_PROBED,
			{"profile": profile.model_dump(mode="json")},
		)
		return profile

	async def latest_profile(self, name: str | None = None) -> HarnessProfile | None:
		"""Most recent probe of a harness, if it has ever been probed."""
		state = await self.state()
		return state.profile(self.harness_name(name))

	# --------------------------------------------------- FR-058/FR-140: dispatch

	def _unowned_paths(self, workspace: Path) -> tuple[str, ...]:
		"""SoFact's own files inside ``workspace``, as pathspecs git must not commit.

		The default workspace is ``<home>/workspace`` and the ledger and sessions live
		beside it, so nothing nests. An operator who points ``--workspace`` at the SoFact
		home does nest them, and a ``git add --all`` would then commit the factory's
		ledger into the module being built. Sealing excludes them instead, because
		SoFact's account of the run is not the run's product.
		"""
		home = self.home.resolve()
		resolved = workspace.resolve()
		if resolved != home and home not in resolved.parents:
			return ()
		unowned = (LEDGER_FILENAME, LOCK_FILENAME, "sessions")
		return tuple(name for name in unowned if (resolved / name).exists())

	async def _module_for(self, plan: GoalPlan, clause_ids: tuple[str, ...]) -> str | None:
		"""The name of the module a step's clauses belong to, when exactly one owns them.

		FR-100 wants the branch per module and FR-136 forbids a session per module, so the
		branch is resolved here: every step whose clauses belong to one module lands on
		that module's branch, and several steps therefore share it.

		Read from the *approved* decomposition, because that is the architecture the
		operator agreed to build. A step that names no clause (bootstrap) or whose clauses
		span two modules belongs to neither, and gets a branch named from the step instead.
		"""
		if not clause_ids:
			return None
		state = await self.state()
		approved = state.latest_decomposition(plan.contract_id)
		if approved is None:
			return None
		found = approved.module_for_clauses(clause_ids)
		return found.name if found is not None else None

	async def dispatch_step(
		self,
		plan_id: str,
		step_id: str,
		*,
		name: str | None = None,
		workspace: Path | None = None,
		model: str | None = None,
		tools: str | None = None,
		session_id: str | None = None,
		fresh: bool = False,
	) -> DispatchRecord:
		"""Run one plan step as one out-of-process session.

		The profile is read from the log rather than passed in, so a dispatch always
		runs against the *recorded* capability finding. A caller that could supply its own
		profile could supply an optimistic one, and FR-148 exists precisely so that
		capability is a measurement rather than a wish.

		``fresh`` re-runs the oracles even when the workspace and the oracle set are
		unchanged since a previous verdict (FR-006); the default reuses instead.
		"""
		plan = await self.plan_by_id(plan_id)
		step = plan.step_by_id(step_id)
		if step is None:
			raise KeyError(f"plan {plan_id} has no step {step_id}")
		adapter = self.adapter(name, workspace=workspace, model=model, tools=tools)
		# FR-100: the branch is established *before* the session starts, so the producer
		# builds on it rather than in place. Refusing here rather than dispatching
		# unbranched is the point -- a session that ran in place has already done the
		# thing the requirement forbids by the time anyone could notice.
		#
		# The module is resolved from the approved decomposition rather than from the
		# step, because FR-136 forbids one session per module: a module's work spans
		# several steps, and those steps share its branch. A step no single module owns
		# (bootstrap; a step spanning two) falls back to its own ordinal and kind.
		checkout = await ensure_module_branch(
			adapter.workspace,
			step.ordinal,
			step.kind.value,
			module=await self._module_for(plan, step.clause_ids),
		)
		record = await adapter.dispatch(
			step,
			plan,
			profile=await self.latest_profile(name),
			session_id=session_id,
			checkout=checkout,
		)
		# FR-100: the branch becomes a boundary only once it has a commit, and sealing is
		# SoFact's job (FR-140) -- a producer asked to commit can decline, and the next
		# step would then branch from an unborn HEAD onto a shared working tree.
		sealed = await seal_branch(
			checkout,
			adapter.workspace,
			note=f"{step.kind.value} step {step.ordinal}: {record.outcome.value}",
			exclude=self._unowned_paths(adapter.workspace),
		)
		record = record.model_copy(update={"checkout": sealed})
		self._commit(
			LedgerKind.STEP_DISPATCHED,
			{"dispatch": record.model_dump(mode="json")},
		)
		if record.declared_complete:
			self._commit(
				LedgerKind.CLAIM_DECLARED,
				{
					"claim": CompletionClaim(
						id=uuid7str(),
						goal_id=record.goal_id,
						declared_by=f"{record.harness}:{record.id}",
						note=record.declaration_note,
						at=now(),
					).model_dump(mode="json"),
				},
			)
		# FR-138 keeps the two signals apart: the claim is written down as its own row, so a
		# disagreement between the producer's word and the artefact's behaviour stays legible
		# rather than being resolved by whichever ran last. FR-163 is what makes a verdict
		# happen at all — the trigger is the session *completing*, because the default
		# harness has no way to declare anything.
		if record.outcome is StepOutcome.COMPLETED:
			await self.check_dispatch(plan.id, record.id, reuse=not fresh)
		return record

	async def dispatch_plan(
		self,
		plan_id: str,
		*,
		name: str | None = None,
		workspace: Path | None = None,
		model: str | None = None,
		tools: str | None = None,
		max_steps: int | None = None,
		concurrent: bool = False,
		fresh: bool = False,
	) -> tuple[DispatchRecord, ...]:
		"""Dispatch a plan wave by wave, stopping at the first wave that stalls (FR-142).

		A step may start only once every step it depends on has *completed* **and** not been
		refuted by a verdict: FR-142 says a dependent must not start on an "unverified"
		dependency, and a completed session is checked for exactly that reason. A wave also
		ends the run when a step did not complete. ``concurrent`` is
		off by default and is not a performance setting: two sessions editing one workspace
		is a merge conflict, and whether a wave may run together is a question about
		worktrees (FR-141) that the operator owns, not the scheduler. ``fresh`` is FR-006's
		bypass, threaded to every step's check.
		"""
		assert max_steps is None or max_steps > 0, "max_steps must be positive"
		plan = await self.plan_by_id(plan_id)
		produced: list[DispatchRecord] = []
		for wave in plan.waves():
			if max_steps is not None and len(produced) >= max_steps:
				break
			if concurrent and len(wave) > 1:
				records = list(
					await asyncio.gather(
						*(
							self.dispatch_step(
								plan_id,
								step.id,
								name=name,
								workspace=workspace,
								model=model,
								tools=tools,
								fresh=fresh,
							)
							for step in wave
						),
					),
				)
			else:
				records = [
					await self.dispatch_step(
						plan_id,
						step.id,
						name=name,
						workspace=workspace,
						model=model,
						tools=tools,
						fresh=fresh,
					)
					for step in wave
				]
			produced.extend(records)
			if any(record.outcome is not StepOutcome.COMPLETED for record in records):
				break
			state = await self.state()
			refuted = refuted_steps(plan, state.latest_report(plan.contract_id))
			if any(record.step_id in refuted for record in records):
				break
			if max_steps is not None and len(produced) >= max_steps:
				break
		return tuple(produced)

	# ------------------------------------------------- FR-101: the repair loop

	async def repair_plan(
		self,
		plan_id: str,
		*,
		name: str | None = None,
		workspace: Path | None = None,
		model: str | None = None,
		tools: str | None = None,
		max_attempts: int = DEFAULT_REPAIR_ATTEMPTS,
		fresh: bool = False,
	) -> tuple[RepairAttempt, ...]:
		"""Turn a refuted verdict into another session, until clean or out of attempts.

		This is the difference between a factory that stops and one that finishes.
		:meth:`dispatch_plan` halts at the first refuted wave, which is right — a
		dependent must not build on an unverified dependency (FR-142). What it left
		undone is the next move: the refutation is *information*, and information about
		which obligation does not hold is exactly what a repair session needs.

		The loop is bounded twice over, and both bounds are FR-101's answer to the most
		expensive failure mode an unattended factory has — wall clock. ``max_attempts``
		caps how many times one clause may be handed back; the clause set being finite
		bounds the whole run. When the cap is reached the attempt is recorded as
		``EXHAUSTED`` rather than the loop quietly ending, because "ran out of attempts"
		and "nothing to repair" must not look the same in the log.

		Each round authors a **new plan revision** rather than mutating the existing one.
		The plan is what FR-139 pins hashes against; an edited plan would make the
		integrity check compare the plan with itself. A revision keeps every prior step's
		id, ordinal and goal hash, so the log's ordinals stay stable and only the tail
		grows.

		Nothing here touches the oracle, the contract, or the pinned goal text. The
		producer is asked to make the refutation stop reproducing, and a producer that
		edits its own completion criteria is caught by the hash check, not by this
		method's good intentions.
		"""
		assert max_attempts >= 1, f"max_attempts must be >= 1, got {max_attempts}"
		plan = await self.plan_by_id(plan_id)
		origin_id = plan.id
		contract = await self.contract_by_id(plan.contract_id)
		by_clause = {clause.id: clause for clause in contract.clauses}
		attempts: list[RepairAttempt] = []

		while True:
			state = await self.state()
			report = state.latest_report(contract.id)
			if report is None:
				# Nothing has been verified, so there is nothing to repair. Authoring a
				# repair goal from an absent verdict would be inventing a refutation.
				break
			grouped = self._group_refutations(plan, tuple(report.violated))
			if not grouped:
				# Clean, or refuted only on clauses no step owns — which the compiler
				# asserts cannot happen, so it is not this method's to repair.
				break
			acted = False
			for step, verdicts in grouped:
				clauses = tuple(by_clause[v.clause_id] for v in verdicts)
				spent = max(
					(len(state.attempts_at_clause(clause.id)) for clause in clauses),
					default=0,
				)
				diagnosis = refutation_diagnosis(verdicts)
				if spent >= max_attempts:
					# The bound FR-101 requires, made visible. Recording EXHAUSTED rather
					# than stopping quietly is what keeps "out of attempts" distinguishable
					# from "nothing to repair" — the same distinction an unrun oracle must
					# keep from a satisfied one.
					attempts.append(
						self._record_repair(
							origin_id=origin_id,
							plan=plan,
							step=step,
							clauses=clauses,
							diagnosis=diagnosis,
							attempt=max_attempts,
							outcome=RepairOutcome.EXHAUSTED,
						),
					)
					continue
				attempt = spent + 1
				plan = revised_plan(
					plan,
					contract,
					clauses,
					diagnosis=diagnosis,
					attempt=attempt,
					max_attempts=max_attempts,
				)
				self._commit(
					LedgerKind.PLAN_COMPILED,
					{"plan": plan.model_dump(mode="json")},
				)
				repair_step = plan.steps[-1]
				record = await self.dispatch_step(
					plan.id,
					repair_step.id,
					name=name,
					workspace=workspace,
					model=model,
					tools=tools,
					fresh=fresh,
				)
				# The row is written when the session ends, so a crash still leaves a
				# record; whether the repair *worked* is settled below, from the verdict
				# the session's own check rendered. An exit code is not a verdict (FR-138).
				attempts.append(
					self._record_repair(
						origin_id=origin_id,
						plan=plan,
						step=repair_step,
						clauses=clauses,
						diagnosis=diagnosis,
						attempt=attempt,
						outcome=(
							RepairOutcome.REPAIRED
							if record.outcome is StepOutcome.COMPLETED
							else RepairOutcome.NOT_COMPLETED
						),
						dispatch_id=record.id,
					),
				)
				acted = True
			if not acted:
				# Every refuted clause is out of attempts. Looping again would be the
				# unbounded retry FR-101 forbids, so this is where the loop ends.
				break
			await self._settle_repairs(plan, attempts)

		await self._settle_repairs(plan, attempts)
		return tuple(attempts)

	def _group_refutations(
		self,
		plan: GoalPlan,
		refuted: tuple[ClauseVerdict, ...],
	) -> list[tuple[GoalStep, tuple[ClauseVerdict, ...]]]:
		"""Bucket refuted clauses by the step that owns them, in plan order.

		Grouping by owning step rather than repairing clause-by-clause keeps the repair
		goal the same size as the step that failed: a step covering one invariant gets a
		one-clause repair, and a step whose clauses all failed is repaired as one session
		rather than three sessions that each half-fix the same file.

		A clause no step covers is skipped here — it cannot happen for a plan the compiler
		produced (it asserts non-omission), and inventing a step for it would hide a
		compiler defect behind a repair.
		"""
		buckets: dict[str, list[ClauseVerdict]] = {}
		order: list[str] = []
		for verdict in refuted:
			for step in plan.steps:
				if verdict.clause_id in step.clause_ids:
					if step.id not in buckets:
						buckets[step.id] = []
						order.append(step.id)
					buckets[step.id].append(verdict)
					break
		return [
			(step, tuple(buckets[step.id]))
			for step in (plan.step_by_id(step_id) for step_id in order)
			if step is not None
		]

	def _record_repair(
		self,
		*,
		origin_id: str,
		plan: GoalPlan,
		step: GoalStep,
		clauses: tuple[Clause, ...],
		diagnosis: str,
		attempt: int,
		outcome: RepairOutcome,
		dispatch_id: str | None = None,
	) -> RepairAttempt:
		"""Write one repair attempt to the log and return it.

		``origin_id`` is the plan the caller asked to repair; ``plan`` is the revision
		the step lives in. Both are recorded so a repair is findable by the id the
		operator holds as well as by the id that locates the step.
		"""
		repair = RepairAttempt(
			id=uuid7str(),
			plan_id=origin_id,
			revision_id=plan.id,
			step_id=step.id,
			clause_ids=tuple(clause.id for clause in clauses),
			attempt=attempt,
			diagnosis=diagnosis,
			goal_hash=step.goal_hash,
			outcome=outcome,
			dispatch_id=dispatch_id,
			at=now(),
		)
		self._commit(
			LedgerKind.REPAIR_ATTEMPTED,
			{"repair": repair.model_dump(mode="json")},
		)
		return repair

	async def _settle_repairs(
		self,
		plan: GoalPlan,
		attempts: list[RepairAttempt],
	) -> None:
		"""Re-label completed attempts against the verdict their own session rendered.

		A repair dispatch that completed is not yet a repair that worked: the session's
		check renders a verdict, and only that verdict says whether the refutation
		stopped reproducing. The row is written when the session ends (so a crash still
		leaves a record) and settled here, which is why ``REPAIRED`` is decided by a
		verdict rather than by an exit code.

		Settling is idempotent: an attempt already carrying a terminal outcome is left
		alone, so calling this twice cannot rewrite history into something more
		flattering.
		"""
		state = await self.state()
		report = state.latest_report(plan.contract_id)
		if report is None:
			return
		verdicts = {v.clause_id: v.outcome for v in report.verdicts}
		for position, attempt in enumerate(attempts):
			if attempt.outcome is not RepairOutcome.REPAIRED:
				continue
			if attempt.dispatch_id is None:
				continue
			settled = all(
				verdicts.get(clause_id) is not VerdictOutcome.VIOLATED
				for clause_id in attempt.clause_ids
			)
			if settled:
				continue
			attempts[position] = attempt.model_copy(
				update={"outcome": RepairOutcome.STILL_REFUTED},
			)
			self._commit(
				LedgerKind.REPAIR_ATTEMPTED,
				{"repair": attempts[position].model_dump(mode="json")},
			)

	# ------------------------------------------------------------ P1: research

	async def research(
		self,
		query: str | None = None,
		*,
		name: str | None = None,
		model: str | None = None,
		tools: str | None = None,
		mode: ResearchMode = ResearchMode.DEEP,
		timeout: float = RESEARCH_TIMEOUT_SECONDS,
	) -> ResearchRecord:
		"""Dispatch one research run and record what it left behind (FR-167).

		SoFact performs no research of its own: it authors the session's goal
		deterministically — zero model involvement, the same discipline as a build
		step — and sends it to a harness whose *research* spec is a deliberate
		composition rather than an ambient one. The report is the producer's word
		(ADR-0008); what SoFact records are the artefacts: the report's size, the
		loop's own search count from ``research-meta.json``, and the source URLs the
		report and the meta cite. A report with no sources is recorded as exactly
		that, never rounded into research that happened (NFR-024).

		The harness resolves from the configured table like any other: explicit name,
		then :data:`DEFAULT_RESEARCH_HARNESS` if the table contains it. Unlike a build
		dispatch this does **not** require a probe — its capability claims are the
		report artefacts themselves, which this method measures directly, and a
		research session that cannot run is one failed artefact rather than an
		assumed one.
		"""
		goal = await self.current_goal()
		if goal is None:
			raise KeyError("no goal yet; research refines a goal, so start one first")
		resolved_query = (query or goal.statement).strip()
		assert resolved_query, "a research query must not be empty"
		if name is None:
			if DEFAULT_RESEARCH_HARNESS not in self._specs:
				known = ", ".join(sorted(self._specs)) or "none"
				raise KeyError(
					f"no research harness: {DEFAULT_RESEARCH_HARNESS!r} is not among the "
					f"configured harnesses ({known}); add it to the table or pass --harness"
				)
			resolved = DEFAULT_RESEARCH_HARNESS
		else:
			resolved = self.harness_name(name)
		workdir = self.home / "research" / goal.id / uuid7str()[:8]
		# The research spec names the extension's tools; the producer's allowlist must
		# carry them or the loop cannot be called at all -- measured: without this the
		# producer spent its wall clock hand-rolling a recursive pi (2026-09-12).
		resolved_tools = resolve_tools(tools)
		research_spec = harness_spec_for(resolved, self._specs)
		if research_spec.research_tools:
			declared = resolved_tools.split(",")
			missing = [name for name in research_spec.research_tools if name not in declared]
			if missing:
				resolved_tools = ",".join([*declared, *missing])
		adapter = self.adapter(resolved, workspace=workdir, model=model, tools=resolved_tools)
		session_id = uuid7str()
		goal_text = research_goal(resolved_query, mode=mode)
		argv = adapter.build_argv(goal_text, session_id)
		started = now()
		exit_code, _stdout, stderr, timed_out, session_path, tokens = await adapter.invoke(
			argv, timeout=timeout, session_id=session_id
		)
		ended = now()

		if timed_out:
			outcome = StepOutcome.BUDGET_EXHAUSTED
			note = f"the research session did not finish within {timeout:.0f}s"
		elif exit_code != 0:
			outcome = StepOutcome.FAILED
			note = f"the research session exited {exit_code}"
		else:
			outcome = StepOutcome.COMPLETED
			note = None

		report = workdir / "research-report.md"
		report_chars = 0
		urls: list[str] = []
		searches: int | None = None
		if report.is_file():
			report_text = report.read_text(encoding="utf-8", errors="replace")
			report_chars = len(report_text)
			urls = list(extract_source_urls(report_text))
		meta_path = workdir / "research-meta.json"
		if meta_path.is_file():
			try:
				loaded: object = json.loads(meta_path.read_text(encoding="utf-8"))
			except json.JSONDecodeError:
				loaded = None
			# ``isinstance`` on a JSON value would narrow to ``dict[Unknown, Unknown]``;
			# the cast keeps the mapping's value type explicit, which is what the
			# narrowing below needs to mean anything.
			meta = cast("dict[str, object] | None", loaded if isinstance(loaded, dict) else None)
			if meta is not None:
				stats_raw = meta.get("stats")
				stats = (
					cast("dict[str, object]", stats_raw) if isinstance(stats_raw, dict) else None
				)
				if stats is not None:
					observed = stats.get("searches")
					if isinstance(observed, int) and not isinstance(observed, bool):
						searches = observed
				sources_raw = meta.get("sources")
				if isinstance(sources_raw, list):
					for source in cast("list[object]", sources_raw):
						if isinstance(source, dict):
							url = cast("dict[str, object]", source).get("url")
							if isinstance(url, str) and url and url not in urls:
								urls.append(url)
		record = ResearchRecord(
			id=uuid7str(),
			goal_id=goal.id,
			query=resolved_query,
			harness=resolved,
			mode=mode,
			argv=argv,
			workspace=str(workdir),
			started_at=started,
			ended_at=ended,
			wall_clock_seconds=max(0.0, (ended - started).total_seconds()),
			outcome=outcome,
			exit_code=exit_code,
			tokens_observed=tokens,
			session_path=str(session_path) if session_path is not None else None,
			stderr_tail=stderr[-DEFAULT_STDERR_TAIL_BYTES:] or None,
			report_path=str(report) if report.is_file() else None,
			report_chars=report_chars,
			searches_observed=searches,
			source_urls=tuple(urls),
			note=note,
		)
		self._commit(LedgerKind.RESEARCH_RUN, {"research": record.model_dump(mode="json")})
		return record

	# --------------------------------------------------- FR-139: integrity at end

	async def check_integrity(self, plan_id: str) -> tuple[IntegrityCheck, ...]:
		"""Re-verify the pinned hashes at *completion* (FR-139).

		The contract is re-read from the log rather than taken from the caller, because
		the thing being checked is whether the artefacts still match what the plan pinned,
		and a caller-supplied contract would be the check grading its own input.
		"""
		plan = await self.plan_by_id(plan_id)
		contract = await self.contract_by_id(plan.contract_id)
		state = await self.state()
		checks = check_integrity(plan, contract, state.dispatches_for(plan_id))
		for check in checks:
			self._commit(
				LedgerKind.INTEGRITY_CHECKED,
				{"check": check.model_dump(mode="json")},
			)
		return checks

	# ------------------------------------------------------- P7: FR-111 - FR-116

	async def check_integration(self, plan_id: str) -> IntegrationReport:
		"""Run P7 over a plan's dispatched work, and record the report (FR-111 - FR-116).

		Reads the plan, the *approved* decomposition and the dispatches from the log rather
		than taking any of them from the caller. Integration is a statement about the
		system as built, and a caller that could supply the module graph could supply one
		whose declared dependencies happen to match the imports it is about to check.

		The decomposition is required rather than optional: without one there is no module
		graph, so "no module reaches another's internals" has nothing to be a violation
		*of*. A plan whose contract has no approved decomposition is refused by
		``require_approved_decomposition`` for the same reason planning is (FR-061).
		"""
		plan = await self.plan_by_id(plan_id)
		decomposition = await self.require_approved_decomposition(plan.contract_id)
		state = await self.state()
		dispatches = state.dispatches_for(plan_id)
		workspaces = {record.workspace for record in dispatches if record.workspace}
		root = Path(next(iter(workspaces))) if len(workspaces) == 1 else None
		report = integrate(plan, decomposition, dispatches, root=root)
		self._commit(
			LedgerKind.INTEGRATION_CHECKED,
			{"integration": report.model_dump(mode="json")},
		)
		return report

	# --------------------------------------------------------- FR-143: precision

	async def declaration_precision(
		self,
		name: str | None = None,
	) -> DeclarationPrecision:
		"""How often a producer's completion declaration survived verification.

		Corroboration is clause-level and comes from the *verifier's* report, never from
		the dispatch: a declaration is corroborated only when every clause the step
		covered carries a ``SATISFIED`` verdict in the latest report for its contract.
		A step covering no clause is never corroborated — a bootstrap step has no clause
		verdict to confirm it, and counting vacuous truth as corroboration would give the
		least checkable step the best score.
		"""
		harness = self.harness_name(name)
		state = await self.state()
		declarations = 0
		corroborated = 0
		for record in state.dispatches:
			if record.harness != harness or not record.declared_complete:
				continue
			declarations += 1
			plan = state.plan(record.plan_id)
			step = None if plan is None else plan.step_by_id(record.step_id)
			if plan is None or step is None or not step.clause_ids:
				continue
			report = state.latest_report(plan.contract_id)
			if report is None:
				continue
			verdicts = {v.clause_id: v.outcome for v in report.verdicts}
			if all(
				verdicts.get(clause_id) is VerdictOutcome.SATISFIED for clause_id in step.clause_ids
			):
				corroborated += 1
		return DeclarationPrecision(
			declarations=declarations,
			corroborated=corroborated,
			at=now(),
		)
