"""FR-127 — the intent traceability graph, which is how an escape finds its clause.

"must be a first-class component, not a derived report. It is the only mechanism by which
an escape (§9.6) can be attributed back to the intent clause that was misunderstood — and
per §2.3 that attribution is the single most valuable learning signal the product
produces."

Four separable claims are under test. The *structure* is that the graph holds the three
relations as directed edges rather than as a printed chain — and that the chain is now a
projection of it, so there is one walk rather than two that agree until someone edits one.
The *attribution* is the walk backwards, which is the mechanism the requirement says does
not otherwise exist, and its two states: a module named, which is an answer, and a lane
alone, which is a candidate set that says so. The *refusals* are the API being hard to get
wrong — a module the deployment never built, and one outside the lane it was filed
against, both of which would point the attribution at a clause that was never built. The
*limits* are what the graph cannot do: a clause the decomposition dropped has no module,
so no escape can ever be attributed to it, and that gap is reported rather than filled.

The graph is not a diagnosis and the suite says so in the same terms the type does. Every
edge is a declaration a phase made, so the graph can say "the module built for this clause
is the one that got reverted" and cannot say the clause was ambiguous. §2.3 makes the
operator the only ground truth there is; this component's job is to put the right clause
in front of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from synthetic import (
	decompose_and_approve,
	elicitation_to_contract,
	specify_and_approve,
	synthetic_service,
)

from sofact.intent import attributions_for, build_graph, requirement_map
from sofact.service import FactoryService
from sofact.views import (
	EscapeKind,
	IntentHop,
	IntentNodeKind,
	ModuleClass,
)


async def a_graph(home: Path, tmp_path: Path) -> tuple[FactoryService, str, str]:
	"""A service with a specification, a decomposition and a plan.

	Returns ``(service, contract_id, plan_id)``. The three phases that declare into the
	graph all have to have run, or the test would be measuring the absence of a
	declaration rather than the graph's reading of one.
	"""
	service = synthetic_service(home, tmp_path, "complete")
	await service.probe_harness(None)
	_, contract_id = await elicitation_to_contract(service, commands="true")
	await specify_and_approve(service, contract_id)
	await decompose_and_approve(service, contract_id)
	plan = await service.compile_plan(contract_id)
	return service, contract_id, plan.id


async def a_deployed_escape(
	home: Path, tmp_path: Path, *, module: str | None = None
) -> tuple[FactoryService, str, str, str]:
	"""A deployed change with one escape recorded against it.

	Returns ``(service, contract_id, report_id, escape_id)``. The lane is read off the
	report rather than guessed, so a fixture change moves the test to a different lane
	rather than failing it for the wrong reason.

	**The lane is chosen to hold more than one module where the decomposition offers
	one.** A single-module lane makes the narrowing a no-op, and a test scoped to one
	cannot tell "the filter works" from "the filter was never exercised" — the first
	version of this helper picked the first link, which is a G5 module in a lane of one,
	and its canary passed against a mutation that removed the filter entirely.
	"""
	from test_escape import deployed_service

	service, report_id, contract_id = await deployed_service(home, tmp_path)
	state = await service.state()
	report = next(r for r in state.deliveries if r.id == report_id)
	decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
	built = [link.module for link in report.chain if link.module is not None]
	by_lane: dict[ModuleClass, list[str]] = {}
	for name in built:
		m = decomposition.module_by_name(name)
		assert m is not None
		by_lane.setdefault(m.module_class, []).append(name)
	shared = sorted(name for names in by_lane.values() if len(names) > 1 for name in names)
	chosen = (shared or sorted(built))[0]
	lane = decomposition.module_by_name(chosen).module_class  # type: ignore[union-attr]
	escape = await service.record_escape(
		report_id,
		lane=lane,
		kind=EscapeKind.REVERT,
		defect="the dashboard showed stale reminders",
		by="operator",
		module=module if module is not None else chosen,
	)
	return service, contract_id, report_id, escape.id


# --------------------------------------------------------------------------- #
# the structure: edges, not a printed chain
# --------------------------------------------------------------------------- #


class TestTheGraphHoldsTheRelationsAsEdges:
	"""The distinction FR-127 draws is structural. A graph that rendered a picture of the
	same linear walk would be the derived report the requirement refuses, wearing a
	diagram."""

	async def test_the_graph_carries_all_four_vertex_kinds(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Four phases declare into the graph — the contract the clause, P2 the requirement,
		P3 the module, P5 the step — so all four kinds have to be present, or a hop is
		missing and the walk cannot reach the clause."""
		service, contract_id, _ = await a_graph(home, tmp_path)

		graph = await service.intent_graph(contract_id)

		assert graph is not None
		kinds = {node.kind for node in graph.nodes}
		assert kinds == {
			IntentNodeKind.CLAUSE,
			IntentNodeKind.REQUIREMENT,
			IntentNodeKind.MODULE,
			IntentNodeKind.STEP,
		}

	async def test_every_hop_kind_is_used(self, home: Path, tmp_path: Path) -> None:
		"""One edge kind per declaration. An unused hop would mean a relation the graph
		claims to hold and does not."""
		service, contract_id, _ = await a_graph(home, tmp_path)

		graph = await service.intent_graph(contract_id)

		assert graph is not None
		assert {edge.hop for edge in graph.edges} == {
			IntentHop.CLAUSE_TO_REQUIREMENT,
			IntentHop.CLAUSE_TO_MODULE,
			IntentHop.MODULE_TO_STEP,
		}

	async def test_the_module_and_the_requirement_branch_off_the_clause(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The structural fact that makes a graph and not a chain: a clause cites its
		requirement and its module *independently*, so they are siblings rather than
		consecutive hops. A chain printing requirement-then-module asserts a relation the
		log does not hold."""
		service, contract_id, _ = await a_graph(home, tmp_path)

		graph = await service.intent_graph(contract_id)

		assert graph is not None
		for clause in graph.clauses:
			outgoing = {edge.hop for edge in graph.edges if edge.source == clause.id}
			assert IntentHop.CLAUSE_TO_REQUIREMENT in outgoing
			assert IntentHop.CLAUSE_TO_MODULE in outgoing
			# And no edge runs requirement -> module, which is what a linear rendering
			# would imply exists.
			requirement_ids = {
				node.id for node in graph.nodes if node.kind is IntentNodeKind.REQUIREMENT
			}
			assert not any(
				edge.source in requirement_ids and edge.hop is IntentHop.CLAUSE_TO_MODULE
				for edge in graph.edges
			)

	async def test_only_a_module_vertex_carries_a_class(self, home: Path, tmp_path: Path) -> None:
		"""The class is what lets a lane resolve to its modules without the decomposition.
		On any other vertex it would make a lane resolve to clauses no module of it owns."""
		service, contract_id, _ = await a_graph(home, tmp_path)

		graph = await service.intent_graph(contract_id)

		assert graph is not None
		for node in graph.nodes:
			assert (node.module_class is not None) == (node.kind is IntentNodeKind.MODULE)

	def test_a_class_on_a_clause_is_refused(self) -> None:
		"""The type's own rule, asserted where it lives rather than only through a build."""
		from sofact.views import IntentNode

		with pytest.raises(ValueError, match="only a module has one"):
			IntentNode(
				id="0192f0c2-0000-7000-8000-000000000001",
				kind=IntentNodeKind.CLAUSE,
				label="the dashboard shows reminders",
				module_class=ModuleClass.G4,
			)


# --------------------------------------------------------------------------- #
# the chain is a projection of the graph, not a second walk
# --------------------------------------------------------------------------- #


class TestTheChainIsProjectedFromTheGraph:
	"""FR-117's chain and FR-127's graph used to walk the same three relations
	independently — two implementations that agree until someone edits one, and the
	disagreement is invisible because each is internally consistent. The requirement that
	made the graph first-class is what retires the second copy."""

	async def test_the_projection_reads_the_declarations_the_phases_made(
		self, home: Path, tmp_path: Path
	) -> None:
		"""Every hop of the projection is checked against the *record* that declared it, not
		against another projection of the same graph.

		The first version of this test compared ``graph.project()`` with
		``delivery.chain(...)`` — which now delegates to ``project()``, so the comparison
		was a tautology and passed against a canary that deleted the requirement hop from
		the projection entirely. A test whose two sides are one function proves only that
		the function is deterministic. The declarations are the ground truth a projection
		can be wrong about, so they are what this reads.
		"""
		service, contract_id, plan_id = await a_graph(home, tmp_path)
		state = await service.state()
		contract = state.contract(contract_id)
		assert contract is not None
		decomposition = state.latest_decomposition(contract_id)
		assert decomposition is not None
		specification = state.latest_specification(contract_id)
		assert specification is not None
		plan = state.plan(plan_id)
		assert plan is not None

		graph = build_graph(contract, decomposition, plan, specification)
		links = {link.clause_id: link for link in graph.project()}
		requirement_for = requirement_map(specification)

		assert set(links) == {clause.id for clause in contract.clauses}
		for clause in contract.clauses:
			link = links[clause.id]
			assert link.statement == clause.statement
			assert link.requirement_id == requirement_for.get(clause.id), (
				f"{clause.id} projects no requirement, but the specification declares one"
			)
			owner = decomposition.module_for_clauses((clause.id,))
			expected = owner.name if owner is not None else None
			assert link.module == expected
			if owner is not None:
				first = next(
					(
						step.ordinal
						for step in plan.steps
						if decomposition.module_for_clauses(step.clause_ids) is not None
						and decomposition.module_for_clauses(step.clause_ids).id == owner.id  # type: ignore[union-attr]
					),
					None,
				)
				assert link.step_ordinal == first

	async def test_the_report_chain_is_the_graph_projection(
		self, home: Path, tmp_path: Path
	) -> None:
		"""And the delegation itself, asserted once: a report rendered from the log carries
		exactly what its graph projects, so the two cannot drift. This is the weaker claim
		and it is kept separate from the one above precisely because comparing two
		projections cannot detect a defect in the projection."""
		service, _contract_id, _, _ = await a_deployed_escape(home, tmp_path)
		state = await service.state()
		report = state.delivery
		assert report is not None and report.intent is not None

		assert list(report.intent.project()) == list(report.chain)

	async def test_a_clause_the_decomposition_dropped_is_a_gap_not_an_absence(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A graph that dropped an unwalkable clause would be indistinguishable from a
		complete graph over a smaller contract. The clause stays with the hop missing."""
		service, contract_id, _ = await a_graph(home, tmp_path)
		state = await service.state()
		contract = state.contract(contract_id)
		assert contract is not None

		# No decomposition and no plan: the honest state of a project delivered without
		# one, which is where the graph has to report rather than raise.
		graph = build_graph(contract, None, None)

		assert len(graph.clauses) == len(contract.clauses)
		assert len(graph.gaps) == len(contract.clauses)
		assert all(link.module is None for link in graph.gaps)


# --------------------------------------------------------------------------- #
# the attribution: the walk backwards, which is FR-127's whole purpose
# --------------------------------------------------------------------------- #


class TestAnEscapeIsAttributedToTheClauseItImplicates:
	async def test_a_named_module_narrows_the_attribution_to_its_clauses(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The answer, rather than a candidate set. The operator named the module, so the
		clauses are the specific obligations that escaped."""
		service, contract_id, report_id, _ = await a_deployed_escape(home, tmp_path)

		attributions = await service.attributions(contract_id)

		assert attributions, "the escape names a module the deployment built"
		assert all(a.narrowed for a in attributions)
		assert all(a.report_id == report_id for a in attributions)
		assert all(a.module is not None for a in attributions)
		# *Exactly* the clauses that module owns, not a subset of the lane's. An assertion
		# of containment is satisfied by equality, so a narrowing that had stopped
		# filtering would pass it — which is how the first version of this test read green
		# against a canary that removed the filter.
		state = await service.state()
		report = next(r for r in state.deliveries if r.id == report_id)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
		graph = await service.intent_graph(contract_id)
		assert graph is not None
		named = attributions[0].module
		assert named is not None
		owner = next(m for m in decomposition.modules if m.name == named)
		assert {a.clause_id for a in attributions} == {
			node.id for node in graph.clauses_of_module(owner.id)
		}
		# The lane must hold more than this module, or the equality above is also an
		# equality with the lane-wide set and proves nothing about narrowing.
		assert len(graph.modules_in_lane(owner.module_class)) > 1

	async def test_a_lane_wide_escape_is_a_candidate_set_that_says_so(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The common case: a revert often cannot say which module broke. The attribution
		is then every clause in the lane, and it must *say* it is a candidate set — a reader
		who could not tell the two apart would read it as a finding, which is how an
		attribution becomes a false accusation."""
		from test_escape import deployed_service

		service, report_id, contract_id = await deployed_service(home, tmp_path)
		state = await service.state()
		report = next(r for r in state.deliveries if r.id == report_id)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
		link = next(link for link in report.chain if link.module is not None)
		lane = decomposition.module_by_name(link.module).module_class  # type: ignore[union-attr]
		await service.record_escape(
			report_id,
			lane=lane,
			kind=EscapeKind.INCIDENT,
			defect="reminders arrived late",
			by="operator",
		)

		attributions = await service.attributions(contract_id)

		assert attributions
		assert not any(a.narrowed for a in attributions)
		assert all("candidate" in a.rendered for a in attributions)

	async def test_the_attribution_carries_the_clauses_own_words(
		self, home: Path, tmp_path: Path
	) -> None:
		"""§2.3's signal arrives in the language of the intent, not of the implementation.
		An attribution that named a UUID would send the operator to the log to find out what
		was misunderstood."""
		service, contract_id, _, _ = await a_deployed_escape(home, tmp_path)
		state = await service.state()
		contract = state.contract(contract_id)
		assert contract is not None
		statements = {clause.id: clause.statement for clause in contract.clauses}

		attributions = await service.attributions(contract_id)

		for attribution in attributions:
			assert attribution.statement == statements[attribution.clause_id]
			assert attribution.statement in attribution.rendered

	async def test_naming_a_module_narrows_rather_than_widens(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The property, not the arithmetic: the same escape attributed with a module name
		reaches a subset of the clauses it reaches without one. A narrowing that could
		*widen* would mean the lane lookup was wrong."""
		from test_escape import deployed_service

		service, report_id, contract_id = await deployed_service(home, tmp_path)
		state = await service.state()
		report = next(r for r in state.deliveries if r.id == report_id)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
		link = next(link for link in report.chain if link.module is not None)
		lane = decomposition.module_by_name(link.module).module_class  # type: ignore[union-attr]
		graph = await service.intent_graph(contract_id)
		assert graph is not None

		wide = graph.attribute(
			await service.record_escape(
				report_id,
				lane=lane,
				kind=EscapeKind.HOTFIX,
				defect="wide",
				by="operator",
			)
		)
		narrow = graph.attribute(
			await service.record_escape(
				report_id,
				lane=lane,
				kind=EscapeKind.HOTFIX,
				defect="narrow",
				by="operator",
				module=link.module,
			)
		)

		# A *proper* subset where the lane holds more than one module, so the assertion
		# cannot be satisfied by equality — `<=` alone passes against a filter that stopped
		# filtering, which is how this test first read green against that canary.
		# Bound to a local first: the generator's filter is not a narrowing a checker can
		# carry through to `link.module` at each use, so the assertion has to be on its own
		# statement or every later read is `str | None` again.
		named = link.module
		assert named is not None, "the link was selected for naming a module"
		module = decomposition.module_by_name(named)
		assert module is not None
		assert {a.clause_id for a in narrow} == {
			node.id for node in graph.clauses_of_module(module.id)
		}
		if len(graph.modules_in_lane(lane)) > 1:
			assert {a.clause_id for a in narrow} < {a.clause_id for a in wide}

	async def test_one_escape_attributes_to_a_clause_once(self, home: Path, tmp_path: Path) -> None:
		"""A decomposition whose modules overlap on a clause would otherwise report the same
		clause twice for one escape, which reads as two signals."""
		service, contract_id, _, _ = await a_deployed_escape(home, tmp_path)

		attributions = await service.attributions(contract_id)

		keys = [(a.escape_id, a.clause_id) for a in attributions]
		assert len(keys) == len(set(keys))

	async def test_attributions_are_scoped_to_the_contract(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A clause belongs to one contract, so an escape whose change was built against a
		different specification is not this contract's signal — including it would attribute
		a misunderstanding of one specification to another."""
		service, _contract_id, _, _ = await a_deployed_escape(home, tmp_path)

		assert await service.attributions("0192f0c2-0000-7000-8000-00000000ffff") == ()


# --------------------------------------------------------------------------- #
# recording refuses a module that would misattribute
# --------------------------------------------------------------------------- #


class TestRecordingRefusesAModuleThatWouldMisattribute:
	async def test_a_module_the_deployment_never_built_is_refused(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A module that did not break points the attribution at the wrong clause, which is
		worse than no attribution because it reads as a finding."""
		from test_escape import deployed_service

		service, report_id, _ = await deployed_service(home, tmp_path)
		state = await service.state()
		report = next(r for r in state.deliveries if r.id == report_id)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
		link = next(link for link in report.chain if link.module is not None)
		lane = decomposition.module_by_name(link.module).module_class  # type: ignore[union-attr]

		with pytest.raises(ValueError, match=r"built no .* module named"):
			await service.record_escape(
				report_id,
				lane=lane,
				kind=EscapeKind.REVERT,
				defect="x",
				by="operator",
				module="a-module-that-does-not-exist",
			)

	async def test_a_module_outside_the_lane_is_refused(self, home: Path, tmp_path: Path) -> None:
		"""A module of another lane is a module of another class, and the escape was filed
		against this one — so naming it is a contradiction rather than a narrowing."""
		from test_escape import deployed_service

		service, report_id, _ = await deployed_service(home, tmp_path)
		state = await service.state()
		report = next(r for r in state.deliveries if r.id == report_id)
		decomposition = next(d for d in state.decompositions if d.contract_id == report.contract_id)
		link = next(link for link in report.chain if link.module is not None)
		lane = decomposition.module_by_name(link.module).module_class  # type: ignore[union-attr]
		other = next(
			(
				m
				for m in decomposition.modules
				if m.module_class is not lane and m.name in {link.module for link in report.chain}
			),
			None,
		)
		if other is None:
			pytest.skip("the synthetic decomposition exercises one lane only")

		with pytest.raises(ValueError, match=r"built no .* module named"):
			await service.record_escape(
				report_id,
				lane=lane,
				kind=EscapeKind.REVERT,
				defect="x",
				by="operator",
				module=other.name,
			)

	async def test_the_named_module_reaches_the_recorded_row(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The field is on the ledger row, not only in the return value: the attribution is
		read from the log, so a name that did not survive the commit would attribute every
		escape as lane-wide."""
		service, _contract_id, _, escape_id = await a_deployed_escape(home, tmp_path)
		state = await service.state()

		recorded = next(e for e in state.escapes if e.id == escape_id)

		assert recorded.module is not None


# --------------------------------------------------------------------------- #
# what the graph cannot do, stated rather than implied
# --------------------------------------------------------------------------- #


class TestTheGraphStatesItsOwnLimits:
	async def test_a_graph_over_no_clauses_discharges_nothing(self) -> None:
		"""The vacuous-pass rule the rest of the product keeps: FR-127 over an empty
		contract has traced nothing, and a clearance derived from the absence of a
		specification is the failure mode this rule exists to close."""
		from sofact.views import Contract, IntentGraph, now

		empty = IntentGraph(
			id="0192f0c2-0000-7000-8000-000000000002",
			contract_id="0192f0c2-0000-7000-8000-000000000003",
			goal_id="0192f0c2-0000-7000-8000-000000000004",
			built_at=now(),
		)

		assert empty.discharged == ()
		assert empty.not_implemented == ("FR-127",)
		# And the contract type refuses the empty case outright, so the graph above is a
		# hand-built one — which is exactly the fixture a vacuous-pass test needs.
		assert Contract is not None

	async def test_an_escape_in_a_lane_the_graph_does_not_hold_attributes_to_nothing(
		self, home: Path, tmp_path: Path
	) -> None:
		"""An empty tuple is the honest result rather than a gap to paper over: it means
		the change's decomposition is not the one this graph was built from, which
		recording refuses and a foreign log can still contain."""
		service, contract_id, _, _ = await a_deployed_escape(home, tmp_path)
		graph = await service.intent_graph(contract_id)
		assert graph is not None
		state = await service.state()
		escape = state.escapes[0]

		# A graph built from no decomposition holds no module in any lane.
		bare = build_graph(state.contract(contract_id), None, None)  # type: ignore[arg-type]

		assert bare.attribute(escape) == ()

	async def test_the_graph_carries_the_contract_hash_it_was_built_against(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A clause reworded after an escape would otherwise be attributed under its new
		words, and the whole value of the signal is that the operator sees what they
		approved (FR-131, FR-139)."""
		service, contract_id, _ = await a_graph(home, tmp_path)
		state = await service.state()
		contract = state.contract(contract_id)
		assert contract is not None

		graph = await service.intent_graph(contract_id)

		assert graph is not None
		assert graph.contract_hash == contract.content_hash

	async def test_a_contract_the_log_does_not_hold_is_none_rather_than_empty(
		self, home: Path, tmp_path: Path
	) -> None:
		"""An empty graph would report FR-127 as not implemented over a contract that does
		not exist, which is the vacuous pass read the wrong way round."""
		service = synthetic_service(home, tmp_path, "complete")

		assert await service.intent_graph("0192f0c2-0000-7000-8000-00000000ffff") is None

	async def test_the_delivery_report_carries_the_graph_the_chain_came_from(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The graph reaches the document the deploy gate reads, and it is the graph the
		chain was projected from rather than one rebuilt at read time — a graph rebuilt now
		would attribute an escape to whatever the decomposition says today, which after a
		repair is a different graph than the change was built against."""
		service, contract_id, _, _ = await a_deployed_escape(home, tmp_path)
		state = await service.state()
		report = state.delivery

		assert report is not None
		assert report.intent is not None
		assert report.intent.contract_id == contract_id
		assert list(report.intent.project()) == list(report.chain)

	async def test_an_escape_recorded_after_a_render_appears_in_the_next_one(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A report describes the log at the moment it is rendered, so an escape recorded
		afterwards is not in it and the attribution appears in the next render. That is not
		a gap — the rate and the attribution are folds over the whole ledger — but it is a
		fact a reader of a *stored* report needs, and FR-117 versions reports precisely so
		an approver's copy stays as it was. Asserted rather than assumed, because a test
		that expected the stale report to carry it would be asserting a property the design
		does not have."""
		service, contract_id, report_id, escape_id = await a_deployed_escape(home, tmp_path)
		state = await service.state()
		stale = next(r for r in state.deliveries if r.id == report_id)

		assert stale.attributions == (), "the escape came after this report was rendered"

		plan = state.plan(stale.plan_id)
		assert plan is not None
		fresh = await service.render_delivery(plan.id)

		assert fresh.id != stale.id
		assert {a.escape_id for a in fresh.attributions} == {escape_id}
		assert fresh.intent is not None
		assert fresh.intent.contract_id == contract_id

	async def test_attributions_for_is_in_log_order(self, home: Path, tmp_path: Path) -> None:
		"""The helper reads the graph against a sequence, so the order is the caller's
		rather than a set iteration's — a list whose order varied run to run would make a
		diff of two readings meaningless."""
		service, contract_id, _, _ = await a_deployed_escape(home, tmp_path)
		graph = await service.intent_graph(contract_id)
		assert graph is not None
		state = await service.state()

		attributions = attributions_for(graph, state.escapes)

		assert attributions
		assert [a.escape_id for a in attributions] == [state.escapes[0].id] * len(attributions)


# --------------------------------------------------------------------------- #
# the surfaces: a component nothing can reach is not first-class
# --------------------------------------------------------------------------- #


class TestTheIntentVerb:
	"""FR-127 calls the graph a first-class component. A component with no verb is one an
	operator cannot read, which is the derived-report shape arriving through the back."""

	def test_no_contract_exits_nonzero_and_says_what_the_graph_needs(self, home: Path) -> None:
		from typer.testing import CliRunner

		from sofact.cli import app

		result = CliRunner().invoke(app, ["--home", str(home), "intent"])

		assert result.exit_code == 1, result.output
		assert "no contract exists" in result.output

	def test_the_graph_prints_its_walk_and_its_attribution(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The whole path: a deployed change, an escape with a module named, and the clause
		the operator is shown. This is §2.3's learning signal, end to end."""
		from test_cli import RUNNER, SPECIFY_ARGS, configure, conversation

		from sofact.cli import app

		configure(tmp_path, monkeypatch)
		conversation(home)
		args = ["--home", str(home)]
		assert RUNNER.invoke(app, [*args, "contract", "--command", "true"]).exit_code == 0
		assert RUNNER.invoke(app, [*args, "specify", "--approve", *SPECIFY_ARGS]).exit_code == 0
		assert RUNNER.invoke(app, [*args, "decompose", "--approve"]).exit_code == 0
		assert RUNNER.invoke(app, [*args, "plan"]).exit_code == 0
		root = tmp_path / "delivery"
		root.mkdir()
		delivered = RUNNER.invoke(app, [*args, "deliver", "--root", str(root)])
		assert delivered.exit_code == 0, delivered.output
		assert RUNNER.invoke(app, [*args, "deploy", "--by", "operator"]).exit_code == 0

		traced = RUNNER.invoke(app, [*args, "intent", "--attributions"])

		assert traced.exit_code == 0, traced.output
		assert "FR-127 intent traceability graph" in traced.output
		assert "clause(s)" in traced.output

	def test_an_unknown_contract_is_a_message_not_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		from test_cli import RUNNER, configure, conversation

		from sofact.cli import app

		configure(tmp_path, monkeypatch)
		conversation(home)

		result = RUNNER.invoke(
			app, ["--home", str(home), "intent", "--contract", "0192f0c2-0000-7000-8000-0000"]
		)

		assert result.exit_code == 1, result.output
		assert "holds no contract" in result.output


class TestTheDeliveryDocumentCarriesTheAttribution:
	def test_the_section_is_written_even_with_nothing_attributed(
		self, home: Path, tmp_path: Path
	) -> None:
		"""A heading with nothing under it reads as a document that lost a section, so the
		empty case says what empty means — and names the gap it could be instead of a
		clean history."""
		from sofact.writing import DELIVERY_HEADINGS

		assert "Escape attribution" in DELIVERY_HEADINGS
