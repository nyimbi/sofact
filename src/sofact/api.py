"""FR-120's machine surface: the same facts the CLI prints, as JSON, read-only.

FR-120 asks that the system be **machine-usable** as well as human-usable — "a documented,
stable API surface. A delivered platform that only a human can drive fails the stated
goal." The capability map's reading of it, recorded when the OpenRig comparison was made,
is that the requirement's subject is the *delivered* system and that SoFact's own surface
being CLI-only is the same defect one level up. This module answers the second half.

**One dispatch, not a flag on every verb.** The alternative was ``--json`` on the
twenty-odd ``typer`` commands, and it is the wrong shape for a reason the rest of this
repository already argues: a flag per verb is a schema per verb, each written beside its
human rendering, and the two drift the first time one is edited. ``sofact api <operation>``
carries **one** envelope, one error shape, and one place where the fact "this surface
cannot mutate anything" is enforced. The CLI verbs stay the human surface and gain nothing.

**Reads only, and the refusals are named.** Every operation here folds the log or reads a
record. The four human gates — specification (P2), decomposition (P3), the contract sample
(P4) and deploy (P8) — are the acts §3.3 makes human, and a machine surface that could pass
one would be a machine passing a human gate, which is the thing the gates exist to prevent.
So the gate operations are **absent from the dispatch table rather than unlisted in the
documentation**, and a caller that asks for one is told which invariant refused it and which
human verb to use. An operation missing from a table is a bug; an operation refused by an
invariant is a fact about the factory, and the difference is the difference between a caller
checking the code and a caller trusting the docs.

The gate names are :class:`~sofact.views.PhaseGate`'s own values under a ``gate:`` prefix,
and the prefix is load-bearing: ``decomposition`` is both a gate and a read of the latest
decomposition, so without it the caller asking what the decomposition *is* would be told to
go and approve one.

**The envelope is closed.** :class:`~sofact.views.MachineEnvelope` derives ``ok`` from
``error`` rather than storing it beside, so a response cannot report success and carry an
error at once — the discipline :func:`sofact.delivery.report` applies to its own checks,
one surface along.

**Stability is a claim this module has to keep.** ``MACHINE_OPERATIONS`` is the table and
the operations are named rather than numbered, so a name cannot be reused for a different
meaning. Adding an operation is additive; changing what one returns is a change to a
published surface, which is what FR-120's word "stable" costs.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Final

from sofact._uuid7 import uuid7str
from sofact.contract import ground_truth_debt
from sofact.service import FactoryService
from sofact.views import (
	MACHINE_API_VERSION,
	MachineEnvelope,
	MachineOperation,
	MachineRequest,
	PhaseGate,
)

__all__ = [
	"GATE_PREFIX",
	"HUMAN_GATE_INVARIANT",
	"HUMAN_GATE_OPERATIONS",
	"MACHINE_OPERATIONS",
	"READ_ONLY_INVARIANT",
	"MachineRefusal",
	"dispatch",
	"operations",
	"payload_for",
	"resolve_operation",
	"surface",
]

READ_ONLY_INVARIANT: Final[str] = (
	"FR-120's machine surface is read-only: every operation folds the log or reads a "
	"record, and no operation here appends one"
)
"""The invariant every operation in this module satisfies, stated once so a test can
assert it of the whole table rather than of each entry."""

HUMAN_GATE_INVARIANT: Final[str] = (
	"§3.3 makes the four gates human acts because no oracle decides them: P2's "
	"specification approval, P3's decomposition approval, P4's sampled contract, and P8's "
	"deploy, which §1.5 keeps permanent. A machine surface that could pass one would be a "
	"machine passing a human gate, which is what the gates exist to prevent"
)
"""Why the gate operations are absent. Named as a constant because a caller who asks for
one is told *this* sentence rather than a bare "unknown operation" — the refusal is a fact
about the factory, not a gap in the table."""

GATE_PREFIX: Final[str] = "gate:"
"""How a human gate is named on this surface, and why the prefix is not decoration.

:class:`~sofact.views.PhaseGate` and :data:`MACHINE_OPERATIONS` share one namespace of
names, and ``decomposition`` is in **both**: as a gate a person passes and as a read of the
latest decomposition. A caller asking for ``decomposition`` must get the read — that is what
the table publishes — so the gate needs a name of its own. ``gate:decomposition`` is
unmistakably the act, and the collision is visible in the table rather than being a lookup
order that decides which meaning wins.
"""

HUMAN_GATE_OPERATIONS: Final[dict[str, str]] = {
	GATE_PREFIX + PhaseGate.SPECIFICATION.value: (
		"use `sofact gate --approve P2 --by <name>` (FR-088)"
	),
	GATE_PREFIX + PhaseGate.DECOMPOSITION.value: (
		"use `sofact gate --approve P3 --by <name>` (FR-094)"
	),
	GATE_PREFIX + PhaseGate.CONTRACT_SAMPLE.value: (
		"use `sofact gate --approve P4 --by <name>` (FR-061)"
	),
	GATE_PREFIX + PhaseGate.DEPLOY.value: (
		"use `sofact deploy --approve <report-id> --by <name>` (FR-119)"
	),
}
"""The four human acts, by the name a machine would ask for them, and where the human goes.

**Keyed by :class:`~sofact.views.PhaseGate`'s own values**, so the table and the phase
machine cannot drift: a fifth gate would fail a test rather than being silently
unreachable here, and the names are §3.3's rather than a second vocabulary invented for
this surface.

A mapping rather than a tuple of names because the useful half of the refusal is the second
column: a caller told only "refused" retries, and a caller told which verb to use stops.
"""

MACHINE_OPERATIONS: Final[dict[str, MachineOperation]] = {
	op.name: op
	for op in (
		MachineOperation(
			name="status",
			summary="The current goal, the phase, any open gate and the readiness verdict.",
			returns="{goal, current_phase, open_gate, readiness, cut}",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="ledger",
			summary="The append-only event log, oldest first, with the chain's integrity.",
			returns="{entries: [LedgerEntry], chain: ChainStatus}",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="contract",
			summary="The latest contract and its measured ground-truth debt (FR-108).",
			returns="{contract: Contract, ground_truth_debt: float} or null",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="plan",
			summary="The latest compiled plan (FR-090).",
			returns="GoalPlan or null",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="decomposition",
			summary="The latest decomposition, with each module's declared budget (FR-097).",
			returns="Decomposition or null",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="integration",
			summary="The latest integration report: findings, orphans, unattributed files (FR-111).",
			returns="IntegrationReport or null",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="delivery",
			summary="The latest delivery report (FR-117), carrying both debt terms.",
			returns="DeliveryReport or null",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="harnesses",
			summary="The adapter table and what each probe measured of a harness (FR-161).",
			returns="{harnesses: {name: HarnessSpec}, profiles: [HarnessProfile]}",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="escapes",
			summary="The escape rate per lane and per autonomy level (FR-022).",
			returns="{report: EscapeReport, escapes: [EscapeEvent]}",
			invariant=READ_ONLY_INVARIANT,
		),
		MachineOperation(
			name="sources",
			summary="The source ledger and the claims resting on it (FR-069-FR-075).",
			returns="SourceLedger or null",
			invariant=READ_ONLY_INVARIANT,
		),
	)
}
"""FR-120's published operations, by name.

A dict keyed by name rather than a tuple, so a lookup is a lookup and a duplicate name is
impossible by construction — two operations sharing a name would be a surface whose
behaviour depended on table order.
"""


class MachineRefusal(Exception):
	"""A request this surface will not answer, with the invariant that refused it.

	An exception rather than an error value, because the two failure modes are different
	and a caller has to be able to tell them apart: a request for a *human gate* is a
	correct request for something this factory deliberately does not expose, while an
	*unknown* name is a caller relying on an operation that was never offered. Both become
	an envelope with ``error`` set; the ``invariant`` says which happened.
	"""

	def __init__(self, operation: str, invariant: str, detail: str) -> None:
		super().__init__(f"{operation} refused: {detail}")
		self.operation = operation
		self.invariant = invariant
		self.detail = detail


def operations() -> tuple[MachineOperation, ...]:
	"""The table, in declaration order, for a caller discovering the surface.

	Ordered rather than a set: a caller reading the list is reading the surface, and an
	unordered one would print differently on two runs, which makes a diff of two listings
	useless for the one thing a listing is for.
	"""
	return tuple(MACHINE_OPERATIONS.values())


def surface() -> dict[str, Any]:
	"""The published surface as one document: what a caller may ask, and what it may not.

	The refusals travel *with* the operations rather than being left to the prose, because
	the useful thing a machine caller can do with "these four are human acts" is discover it
	before asking. The mapping is name → the human verb, so a caller that does ask anyway
	gets the same sentence in the refusal envelope it would have read here.
	"""
	return {
		"api_version": MACHINE_API_VERSION,
		"operations": [op.model_dump(mode="json") for op in operations()],
		"read_only": READ_ONLY_INVARIANT,
		"human_gate_invariant": HUMAN_GATE_INVARIANT,
		"human_gates": dict(HUMAN_GATE_OPERATIONS),
	}


def resolve_operation(request: MachineRequest) -> MachineOperation:
	"""The operation, or a refusal that says which invariant is in play."""
	found = MACHINE_OPERATIONS.get(request.operation)
	if found is not None:
		return found
	# The gate names are recognised *specifically*, so the refusal is about the factory
	# rather than about the table. A caller asking for one is asking a question this
	# factory has an answer to, and the answer is no — with the human verb named.
	gate = HUMAN_GATE_OPERATIONS.get(request.operation)
	if gate is not None:
		raise MachineRefusal(request.operation, HUMAN_GATE_INVARIANT, gate)
	raise MachineRefusal(
		request.operation,
		"FR-120 publishes a closed set of operations; an unpublished name is not an "
		"operation this surface has ever offered, so no caller can be relying on it",
		f"unknown operation {request.operation!r}; the surface is "
		+ ", ".join(sorted(MACHINE_OPERATIONS)),
	)


async def payload_for(svc: FactoryService, operation: str) -> Any:
	"""The operation's answer, read from the log.

	There is no ``else`` branch and no default. An operation added to the table without a
	branch here raises rather than being answered with another operation's data, which is
	the failure a default would produce and the one a caller could not detect.
	"""
	state = await svc.state()
	if operation == "status":
		goal = await svc.current_goal()
		return {
			"goal": goal.model_dump(mode="json") if goal is not None else None,
			"current_phase": state.current_phase.value,
			"open_gate": state.open_gate.model_dump(mode="json")
			if state.open_gate is not None
			else None,
			"readiness": (await svc.readiness(goal.id)).model_dump(mode="json")
			if goal is not None
			else None,
			"cut": state.cut.model_dump(mode="json") if state.cut is not None else None,
		}
	if operation == "ledger":
		return {
			"entries": [entry.model_dump(mode="json") for entry in await svc.entries()],
			"chain": (await svc.verify_ledger()).model_dump(mode="json"),
		}
	if operation == "contract":
		goal = await svc.current_goal()
		contract = await svc.latest_contract(goal.id) if goal is not None else None
		if contract is None:
			return None
		return {
			"contract": contract.model_dump(mode="json"),
			"ground_truth_debt": ground_truth_debt(contract),
		}
	if operation == "plan":
		goal = await svc.current_goal()
		contract = await svc.latest_contract(goal.id) if goal is not None else None
		plan = await svc.latest_plan(contract.id) if contract is not None else None
		return plan.model_dump(mode="json") if plan is not None else None
	if operation == "decomposition":
		goal = await svc.current_goal()
		contract = await svc.latest_contract(goal.id) if goal is not None else None
		found = await svc.latest_decomposition(contract.id) if contract is not None else None
		return found.model_dump(mode="json") if found is not None else None
	if operation == "integration":
		goal = await svc.current_goal()
		contract = await svc.latest_contract(goal.id) if goal is not None else None
		plan = await svc.latest_plan(contract.id) if contract is not None else None
		report = state.latest_integration(plan.id) if plan is not None else None
		return report.model_dump(mode="json") if report is not None else None
	if operation == "delivery":
		delivery = await svc.current_delivery()
		return delivery.model_dump(mode="json") if delivery is not None else None
	if operation == "harnesses":
		return {
			"harnesses": {name: asdict(spec) for name, spec in svc.harness_table().items()},
			"profiles": [profile.model_dump(mode="json") for profile in state.profiles],
		}
	if operation == "escapes":
		# The rate *and* the raw events, because FR-021's "tracked forward through deploy"
		# is a lookup a caller does on the events while FR-022's metric is the fold over
		# them: publishing only the rate would make the recording unauditable.
		return {
			"report": (await svc.escape_report()).model_dump(mode="json"),
			"escapes": [e.model_dump(mode="json") for e in state.escapes],
		}
	if operation == "sources":
		ledger = await svc.current_ledger()
		return ledger.model_dump(mode="json") if ledger is not None else None
	raise AssertionError(f"{operation!r} is in the table and has no branch: add one")


async def dispatch(svc: FactoryService, request: MachineRequest) -> MachineEnvelope:
	"""Answer one machine request. Never mutates the project.

	A refusal returns an envelope rather than raising, because this surface's caller is a
	program: an exception crossing a subprocess boundary is a traceback and an exit code,
	while an envelope is a fact the caller can branch on. The exception exists internally so
	the reason travels as data rather than being formatted into a message and re-parsed.
	"""
	assert request.operation, "a request names an operation"
	try:
		operation = resolve_operation(request)
	except MachineRefusal as refusal:
		return MachineEnvelope(
			id=uuid7str(),
			api_version=MACHINE_API_VERSION,
			operation=request.operation,
			invariant=refusal.invariant,
			error=refusal.detail,
		)
	return MachineEnvelope(
		id=uuid7str(),
		api_version=MACHINE_API_VERSION,
		operation=operation.name,
		invariant=operation.invariant,
		result=await payload_for(svc, operation.name),
	)
