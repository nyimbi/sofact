"""FR-127 — the intent traceability graph.

"must be a first-class component, not a derived report. It is the only mechanism by which
an escape (§9.6) can be attributed back to the intent clause that was misunderstood — and
per §2.3 that attribution is the single most valuable learning signal the product
produces."

§2.3 states the risk this graph answers: ground-truth debt, where "if the criteria are
wrong, every check passes and the platform is wrong — and it is wrong in a way that looks
maximally verified". The only closure §2.3 admits is the operator's reading of the
specification at P2, and a reading needs the right clause in front of the right person.
Forward, the traceability chain answers "what was built for this clause", which is what a
deploy gate approves. The question after an escape is the *other* direction — "which
clause was misunderstood" — and there is no route to it except from the module that broke
back to the clauses that cite it.

**Why a graph and not a better chain.** The three relations FR-117 prints as a chain are
not a chain in the log. A clause cites its requirement (P2) and its module (P3)
independently, so requirement and module are sibling branches off the clause rather than
consecutive hops, and only the module reaches a step (P5). A linear rendering is what a
report must produce and it is not what the log holds. Holding the relations as directed
edges is what makes the backward walk a hop instead of a search — and it is also what
makes the report a *projection* of one structure rather than a second walk that agrees
with the first until someone edits one of them.

**The honest limit.** Every edge here is a declaration a phase made, so the graph is as
trustworthy as the phases and no more. It can say "the module built for this clause is the
one that got reverted"; it cannot say the clause was ambiguous or that the operator meant
something else. §2.3 makes the operator the only ground truth there is, so the graph's job
is to put the clause in front of them, and the judgement stays theirs. A clause the graph
cannot walk — one the decomposition dropped — is reported as a gap, and it is a worse
finding than an escape: nothing was built for it, so no escape can ever be attributed to
it at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from sofact._uuid7 import uuid7str
from sofact.views import (
	Contract,
	Decomposition,
	EscapeAttribution,
	EscapeEvent,
	GoalPlan,
	IntentEdge,
	IntentGraph,
	IntentHop,
	IntentNode,
	IntentNodeKind,
	Specification,
	now,
)

__all__ = ["attributions_for", "build_graph", "requirement_map"]


def requirement_map(specification: Specification | None) -> dict[str, str]:
	"""Clause to the requirement that cites it (P2's declaration).

	The inverse of ``Requirement.clause_ids``, which is how the requirement states it: a
	requirement names the clauses it traces to, and a graph edge runs from the clause to
	the requirement so the walk can go backwards. Several requirements may cite one clause
	— P2 does not forbid it — and the first is taken, so the answer is stable across reads
	rather than dependent on dictionary order.
	"""
	if specification is None:
		return {}
	by_clause: dict[str, str] = {}
	for requirement in specification.requirements:
		for clause_id in requirement.clause_ids:
			by_clause.setdefault(clause_id, requirement.id)
	return by_clause


def build_graph(
	contract: Contract,
	decomposition: Decomposition | None,
	plan: GoalPlan | None,
	specification: Specification | None = None,
	*,
	requirement_for_clause: Mapping[str, str] | None = None,
	built_at: datetime | None = None,
) -> IntentGraph:
	"""Build FR-127's graph from the declarations the phases made.

	Pure: every input is a record the caller already read, and nothing here opens a file or
	derives a fact no phase wrote down. Four phases declare into it — P2 the requirement,
	P3 the module, P5 the step, and the contract the clause — and each contributes exactly
	one kind of vertex and one kind of edge.

	``requirement_for_clause`` overrides the map derived from ``specification``, for the
	caller that holds the mapping without the specification — which is how
	:func:`sofact.delivery.report` reaches here from a log whose specification it reads
	separately. Passing both is not an error: the explicit map wins, because a caller that
	computed one has already decided what it means.

	A phase that produced nothing contributes no vertices, and the clauses it would have
	reached stay in the graph with the hop missing. That is deliberate: the graph is the
	place a project's traceability *gaps* are visible, and dropping an unwalkable clause
	would make an incomplete graph indistinguishable from a complete one over a smaller
	contract.
	"""
	assert contract.clauses, "cannot build an intent graph over a contract with no clauses"
	requirement_of = (
		dict(requirement_for_clause)
		if requirement_for_clause is not None
		else requirement_map(specification)
	)

	nodes: list[IntentNode] = [
		IntentNode(id=clause.id, kind=IntentNodeKind.CLAUSE, label=clause.statement)
		for clause in contract.clauses
	]
	edges: list[IntentEdge] = []

	if specification is not None:
		for requirement in specification.requirements:
			nodes.append(
				IntentNode(
					id=requirement.id,
					kind=IntentNodeKind.REQUIREMENT,
					label=requirement.statement,
				)
			)
	for clause_id, requirement_id in requirement_of.items():
		# A requirement the specification did not supply still gets a vertex, and the edge
		# with it. The first version minted vertices only from the specification, so a
		# caller holding the map alone lost the clause-to-requirement hop silently — the
		# projection test caught it as a requirement id that appeared in one build and not
		# the other. Dropping the edge would be worse than labelling it thinly: the
		# relation is the *id*, and only the label needs the statement.
		if not any(node.id == requirement_id for node in nodes):
			nodes.append(
				IntentNode(id=requirement_id, kind=IntentNodeKind.REQUIREMENT, label=requirement_id)
			)
		edges.append(
			IntentEdge(
				source=clause_id,
				target=requirement_id,
				hop=IntentHop.CLAUSE_TO_REQUIREMENT,
			)
		)

	if decomposition is not None:
		for module in decomposition.modules:
			nodes.append(
				IntentNode(
					id=module.id,
					kind=IntentNodeKind.MODULE,
					label=module.name,
					module_class=module.module_class,
				)
			)
			for clause_id in module.clause_ids:
				edges.append(
					IntentEdge(
						source=clause_id,
						target=module.id,
						hop=IntentHop.CLAUSE_TO_MODULE,
					)
				)

	if decomposition is not None and plan is not None:
		for step in plan.steps:
			nodes.append(IntentNode(id=step.id, kind=IntentNodeKind.STEP, label=str(step.ordinal)))
			module = decomposition.module_for_clauses(step.clause_ids)
			if module is not None:
				edges.append(
					IntentEdge(
						source=module.id,
						target=step.id,
						hop=IntentHop.MODULE_TO_STEP,
					)
				)

	return IntentGraph(
		id=uuid7str(),
		contract_id=contract.id,
		goal_id=contract.goal_id,
		built_at=now() if built_at is None else built_at,
		nodes=tuple(nodes),
		edges=tuple(edges),
		contract_hash=contract.content_hash,
	)


def attributions_for(
	graph: IntentGraph, escapes: Sequence[EscapeEvent]
) -> tuple[EscapeAttribution, ...]:
	"""Every escape in the log traced back to the clause(s) it implicates (FR-127).

	In log order, and an escape that attributes to nothing contributes nothing rather than
	a placeholder row: it means the escape names a lane this graph holds no module for,
	which is a gap in the graph and not an attribution. A caller that needs to see those
	compares the escape list against the attributions it got back — the count difference is
	the gap, and inventing a row here would hide it.
	"""
	return tuple(attribution for escape in escapes for attribution in graph.attribute(escape))
