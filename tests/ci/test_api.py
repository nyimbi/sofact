"""FR-120's machine surface: one dispatch, one envelope, reads only.

What is under test is not the JSON — that is a serialisation — but the three claims the
surface makes about itself. It is **closed**: the table is the surface, every operation
in it has a branch, and an operation added without one raises rather than being answered
with another operation's data. It is **read-only**: no operation appends to the log, and
the test that matters asserts that across the whole table rather than per entry, because
the failure mode is an operation added later that quietly writes. And its **refusals are
facts about the factory rather than gaps in a table**: the four human gates are named,
recognised specifically, and answered with the human verb to use, which is a different
answer from the one an unpublished name gets.

The envelope's own invariant is tested as a property rather than a field: ``ok`` is
derived from ``error``, and a response carrying both an error and a result is refused at
construction, so a caller cannot read a partial answer past a refusal.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from synthetic import gated_contract, synthetic_service
from typer.testing import CliRunner

from sofact.api import (
	GATE_PREFIX,
	HUMAN_GATE_INVARIANT,
	HUMAN_GATE_OPERATIONS,
	MACHINE_OPERATIONS,
	READ_ONLY_INVARIANT,
	MachineRefusal,
	dispatch,
	operations,
	payload_for,
	resolve_operation,
	surface,
)
from sofact.cli import app
from sofact.service import FactoryService
from sofact.views import (
	MACHINE_API_VERSION,
	MachineEnvelope,
	MachineRequest,
	PhaseGate,
)

HUMAN_ACTS = tuple(GATE_PREFIX + gate.value for gate in PhaseGate)
"""The four gates §3.3 makes human, **read off the phase machine** rather than retyped.

A hand-written list here would be a second vocabulary that could drift from
:class:`~sofact.views.PhaseGate` — and the drift would be silent, because a gate missing
from both the table and this tuple looks exactly like a factory with three gates.
"""

RUNNER = CliRunner()


def an_envelope(**overrides: Any) -> MachineEnvelope:
	"""A valid envelope, so a test can vary one field without restating the rest."""
	fields: dict[str, Any] = {
		"id": "01920000-0000-7000-8000-000000000001",
		"api_version": MACHINE_API_VERSION,
		"operation": "status",
		"invariant": READ_ONLY_INVARIANT,
	}
	fields.update(overrides)
	return MachineEnvelope(**fields)


# --------------------------------------------------------------------------- #
# the table is the surface
# --------------------------------------------------------------------------- #


class TestTheTableIsTheSurface:
	def test_the_table_is_not_empty(self) -> None:
		assert MACHINE_OPERATIONS, "an empty surface is not a surface"
		assert len(operations()) == len(MACHINE_OPERATIONS)

	def test_every_key_is_the_operation_name(self) -> None:
		for key, operation in MACHINE_OPERATIONS.items():
			assert key == operation.name, (
				f"{key!r} keys an operation called {operation.name!r}: a caller looking up "
				"a name would find an operation that answers to a different one"
			)

	def test_the_names_are_unique(self) -> None:
		names = [op.name for op in operations()]
		assert len(names) == len(set(names)), "two operations share a name"

	def test_the_order_is_declaration_order(self) -> None:
		assert [op.name for op in operations()] == list(MACHINE_OPERATIONS), (
			"the listing must be deterministic, or a diff of two listings is useless"
		)

	def test_every_operation_declares_what_it_returns(self) -> None:
		for operation in operations():
			assert operation.summary, operation.name
			assert operation.returns, operation.name
			assert operation.invariant, operation.name

	def test_the_surface_document_lists_every_operation(self) -> None:
		document = surface()
		assert document["api_version"] == MACHINE_API_VERSION
		listed = {entry["name"] for entry in document["operations"]}
		assert listed == set(MACHINE_OPERATIONS), (
			"a listing that omits an operation is a caller relying on the docs"
		)

	def test_the_surface_document_names_the_human_gates(self) -> None:
		document = surface()
		assert set(document["human_gates"]) == set(HUMAN_ACTS)
		assert document["human_gate_invariant"] == HUMAN_GATE_INVARIANT

	def test_the_gate_names_are_the_phase_machine_s(self) -> None:
		"""The table is keyed by ``PhaseGate``'s values, not a second vocabulary.

		A fifth gate added to §3.3 would fail here rather than being silently
		unreachable through the machine surface — which is the failure that looks
		identical to a factory with fewer gates.
		"""
		assert set(HUMAN_GATE_OPERATIONS) == {GATE_PREFIX + gate.value for gate in PhaseGate}
		assert len(PhaseGate) == 4, "§3.3 places four gates, and adding one is a decision"

	def test_a_gate_that_shares_a_name_with_a_read_is_still_distinguishable(self) -> None:
		"""``decomposition`` is both a gate and a read, and the read must win the bare name.

		The collision is not hypothetical — it was found by running the surface. A gate
		reachable as ``decomposition`` would shadow the operation the table publishes, and
		the caller asking what the decomposition *is* would be told to go and approve one.
		"""
		assert "decomposition" in MACHINE_OPERATIONS
		assert GATE_PREFIX + "decomposition" in HUMAN_GATE_OPERATIONS
		assert not set(HUMAN_GATE_OPERATIONS) & set(MACHINE_OPERATIONS), (
			"a gate and a read cannot share a name: the lookup would decide the meaning"
		)


# --------------------------------------------------------------------------- #
# read-only, asserted of the table rather than of each entry
# --------------------------------------------------------------------------- #


class TestReadOnly:
	def test_every_operation_carries_the_read_only_invariant(self) -> None:
		offenders = [op.name for op in operations() if op.invariant != READ_ONLY_INVARIANT]
		assert not offenders, (
			f"{offenders} do not declare {READ_ONLY_INVARIANT!r}: the invariant is what a caller "
			"reads to know this surface cannot mutate anything"
		)

	def test_no_operation_appends_to_the_log(self, home: Path, tmp_path: Path) -> None:
		service = synthetic_service(home, tmp_path, "complete")

		async def run() -> None:
			await gated_contract(service)
			before = len(await service.entries())
			assert before, "the fixture must have written something to compare against"
			for name in MACHINE_OPERATIONS:
				envelope = await dispatch(service, MachineRequest(operation=name))
				assert envelope.ok, f"{name} refused: {envelope.error}"
			after = len(await service.entries())
			assert after == before, (
				f"{after - before} entr(ies) appeared: an operation in the table writes, "
				"and a machine surface that mutates is one a caller cannot re-read safely"
			)

		asyncio.run(run())

	def test_every_operation_in_the_table_has_a_branch(self, home: Path, tmp_path: Path) -> None:
		"""The dispatch has no default, so a table entry without a branch raises.

		This is the property that makes the table and the payload one thing: adding an
		operation to ``MACHINE_OPERATIONS`` without teaching ``_payload`` what it returns
		fails here rather than being answered with another operation's data.
		"""
		service = synthetic_service(home, tmp_path, "complete")

		async def run() -> None:
			for name in MACHINE_OPERATIONS:
				await payload_for(service, name)
			with pytest.raises(AssertionError, match="has no branch"):
				await payload_for(service, "not-an-operation")

		asyncio.run(run())


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #


class TestRefusals:
	def test_the_human_gates_are_recognised_specifically(self) -> None:
		for name in HUMAN_ACTS:
			with pytest.raises(MachineRefusal) as caught:
				resolve_operation(MachineRequest(operation=name))
			assert caught.value.invariant == HUMAN_GATE_INVARIANT, (
				f"{name} was refused as an unknown name rather than as a human act"
			)
			assert caught.value.detail == HUMAN_GATE_OPERATIONS[name]

	def test_a_gate_refusal_names_the_human_verb(self) -> None:
		for name, verb in HUMAN_GATE_OPERATIONS.items():
			with pytest.raises(MachineRefusal) as caught:
				resolve_operation(MachineRequest(operation=name))
			assert "sofact" in caught.value.detail, (
				f"the refusal for {name!r} does not name a verb to use, so the caller "
				"retries instead of stopping"
			)
			assert caught.value.detail == verb

	def test_an_unpublished_name_is_a_different_refusal(self) -> None:
		with pytest.raises(MachineRefusal) as caught:
			resolve_operation(MachineRequest(operation="sudo"))
		assert caught.value.invariant != HUMAN_GATE_INVARIANT, (
			"an unpublished name is a gap in the table, not a fact about the gates"
		)
		assert "unknown operation" in caught.value.detail

	def test_no_gate_is_reachable_through_the_table(self) -> None:
		assert not set(HUMAN_ACTS) & set(MACHINE_OPERATIONS), (
			"a human gate in the dispatch table is a machine passing a human gate"
		)

	@pytest.mark.parametrize("name", HUMAN_ACTS)
	def test_a_refused_request_returns_an_envelope_not_an_exception(self, name: str) -> None:
		"""The caller is a program: a refusal is a fact to branch on, not a traceback."""

		async def run() -> MachineEnvelope:
			service = FactoryService(home=None, llm=None)
			return await dispatch(service, MachineRequest(operation=name))

		envelope = asyncio.run(run())
		assert not envelope.ok
		assert envelope.error == HUMAN_GATE_OPERATIONS[name]
		assert envelope.invariant == HUMAN_GATE_INVARIANT
		assert envelope.result is None, "a refusal that carries a result is an answer"
		assert envelope.api_version == MACHINE_API_VERSION


# --------------------------------------------------------------------------- #
# the envelope is closed
# --------------------------------------------------------------------------- #


class TestTheEnvelopeIsClosed:
	def test_ok_is_derived_from_the_error(self) -> None:
		assert an_envelope().ok is True
		assert an_envelope(error="nope").ok is False

	def test_ok_is_not_a_field(self) -> None:
		assert "ok" not in MachineEnvelope.model_fields, (
			"a stored ok can disagree with the error beside it"
		)

	def test_ok_survives_serialisation(self) -> None:
		"""Derived *and* emitted. A plain property is absent from the JSON.

		This is the one that failed first: ``ok`` was a property, the CLI printed the
		envelope with ``model_dump``, and the single field a machine caller branches on
		was missing from the document it reads. Computed rather than stored keeps the
		derivation while putting it in the payload.
		"""
		payload = an_envelope(result={"entries": []}).model_dump(mode="json")
		assert payload["ok"] is True
		assert an_envelope(error="nope").model_dump(mode="json")["ok"] is False

	def test_ok_cannot_be_supplied(self) -> None:
		with pytest.raises(ValidationError):
			an_envelope(ok=True)  # type: ignore[call-arg]

	def test_a_refusal_cannot_carry_a_result(self) -> None:
		with pytest.raises(ValidationError, match="cannot also carry a result"):
			an_envelope(error="nope", result={"partial": True})

	def test_a_successful_envelope_carries_the_operation_and_invariant(self) -> None:
		operation = MACHINE_OPERATIONS["ledger"]
		envelope = an_envelope(
			operation=operation.name, invariant=operation.invariant, result={"entries": []}
		)
		assert envelope.ok
		assert envelope.invariant == operation.invariant


# --------------------------------------------------------------------------- #
# the operations answer
# --------------------------------------------------------------------------- #


class TestTheOperationsAnswer:
	def test_status_answers_on_an_empty_project(self, home: Path, tmp_path: Path) -> None:
		service = synthetic_service(home, tmp_path, "complete")

		async def run() -> MachineEnvelope:
			return await dispatch(service, MachineRequest(operation="status"))

		envelope = asyncio.run(run())
		assert envelope.ok, envelope.error
		assert envelope.result["goal"] is None, "a fresh project has no goal, not a traceback"

	def test_the_goal_scoped_operations_follow_the_log(self, home: Path, tmp_path: Path) -> None:
		"""``plan`` and ``decomposition`` are the *latest* one, in log order.

		The chain is walked goal → contract → plan here exactly as the service's own
		accessors do, so the operation answers about the same plan a human reading
		``sofact status`` would be reading about.
		"""

		async def run() -> dict[str, MachineEnvelope]:
			service = synthetic_service(home, tmp_path, "complete")
			await gated_contract(service)
			return {
				name: await dispatch(service, MachineRequest(operation=name))
				for name in ("contract", "plan", "decomposition", "harnesses")
			}

		answers = asyncio.run(run())
		for name, envelope in answers.items():
			assert envelope.ok, f"{name}: {envelope.error}"
		assert answers["contract"].result["contract"]["id"]
		assert answers["contract"].result["ground_truth_debt"] is not None
		assert answers["decomposition"].result["id"]
		assert "synthetic" in answers["harnesses"].result["harnesses"]

	def test_a_harness_spec_serialises_without_a_model_dump(
		self, home: Path, tmp_path: Path
	) -> None:
		"""``HarnessSpec`` is a dataclass, so the operation must not assume Pydantic.

		The field that would be silently lost by a hand-written mapping is ``argv``, and
		it is the one a caller needs to reproduce a dispatch.
		"""

		async def run() -> MachineEnvelope:
			service = synthetic_service(home, tmp_path, "complete")
			return await dispatch(service, MachineRequest(operation="harnesses"))

		envelope = asyncio.run(run())
		assert envelope.ok, envelope.error
		spec = envelope.result["harnesses"]["synthetic"]
		assert spec["argv"], "a spec with no argv is a spec a caller cannot run"
		assert spec["name"] == "synthetic"


# --------------------------------------------------------------------------- #
# the verb
# --------------------------------------------------------------------------- #


class TestTheVerb:
	def test_the_listing_is_json_and_exits_zero(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["api", "--list", "--home", str(home)])
		assert result.exit_code == 0, result.output
		document = json.loads(result.output)
		assert {op["name"] for op in document["operations"]} == set(MACHINE_OPERATIONS)

	def test_an_answered_operation_exits_zero(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["api", "status", "--home", str(home)])
		assert result.exit_code == 0, result.output
		assert json.loads(result.output)["ok"] is True

	def test_a_refusal_exits_non_zero_with_a_parseable_envelope(self, home: Path) -> None:
		"""The exit code is for a shell; the envelope is for the caller.

		A refusal that exited zero would let a script chain past a human gate without
		reading the body, which is the whole failure this verb could have.
		"""
		result = RUNNER.invoke(app, ["api", "gate:deploy", "--home", str(home)])
		assert result.exit_code == 1, result.output
		envelope = json.loads(result.output)
		assert envelope["ok"] is False
		assert envelope["error"] == HUMAN_GATE_OPERATIONS["gate:deploy"]
		assert envelope["result"] is None

	def test_naming_no_operation_is_a_usage_error(self, home: Path) -> None:
		result = RUNNER.invoke(app, ["api", "--home", str(home)])
		assert result.exit_code == 2, result.output
