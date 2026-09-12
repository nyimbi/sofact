"""Orchestration: the only module that both reads the log and reaches the network.

Everything above this is pure (models, fold, gates); everything below is a
presentation adapter. Keeping the composition here means the CLI holds no policy —
it prints what the service decides.

Home resolution is explicit and hermetic. There is no implicit global state
directory: unset, SoFact writes to ``./.sofact``, and ``SOFACT_HOME`` overrides it.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from sofact._uuid7 import uuid7str
from sofact.contract import ground_truth_debt, suggest_oracle
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
from sofact.harness import (
	DEFAULT_PROBE_GOAL,
	DEFAULT_PROBE_TIMEOUT_SECONDS,
	DEFAULT_TOOLS,
	SPECS,
	ConfiguredHarnessAdapter,
	HarnessSpec,
)
from sofact.harness import (
	spec_for as harness_spec_for,
)
from sofact.ledger import LEDGER_FILENAME, Ledger, LedgerEntry
from sofact.llm import DEFAULT_MODEL, LlmClient, LlmUnavailable
from sofact.planner import check_integrity, compile_plan
from sofact.state import fold
from sofact.verification import verdict_cache_key, verify
from sofact.views import (
	Advice,
	ChainStatus,
	CompletionClaim,
	Contract,
	DeclarationPrecision,
	DispatchRecord,
	ElicitationAnswer,
	ElicitationDimension,
	Evidence,
	Goal,
	GoalPlan,
	GoalStyle,
	HarnessProfile,
	IntegrityCheck,
	LedgerKind,
	OracleDeclaration,
	ProjectState,
	Readiness,
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

	async def compile_plan(
		self,
		contract_id: str,
		*,
		budget: StepBudget | None = None,
		goal_style: GoalStyle = GoalStyle.LABELLED,
	) -> GoalPlan:
		"""Compile a contract into ordered goal sessions (FR-136).

		Deterministic and model-free: no prompt here is drafted by an LLM, because a
		compiler that let a model write the goal would make FR-139's "did the producer
		rewrite its own objective?" check a comparison of the compiler against itself.
		"""
		contract = await self.contract_by_id(contract_id)
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
		record = await adapter.dispatch(
			step,
			plan,
			profile=await self.latest_profile(name),
			session_id=session_id,
		)
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
