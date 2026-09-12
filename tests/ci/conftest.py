"""Shared fixtures.

No mocks: every fixture is a real object on a real filesystem. The one boundary that
is allowed to be faked is the LLM, and even there the fake is a real HTTP server
(:mod:`pytest_httpserver`) behind the real client, so the request the client builds
is the request under test.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sofact._uuid7 import uuid7str
from sofact.elicitation import DIMENSIONS
from sofact.service import FactoryService
from sofact.views import (
	ClauseKind,
	ClauseStem,
	Contract,
	ElicitationDimension,
	OracleClass,
	OracleDeclaration,
	SpecificationDraft,
	now,
)

GOOD_ANSWERS: dict[ElicitationDimension, str] = {
	ElicitationDimension.OUTCOME: (
		"Every scheduled reminder appears in the user dashboard within five seconds "
		"of its scheduled time."
	),
	ElicitationDimension.CONSUMER: (
		"The end user opens the web dashboard in a browser and reads the reminders there."
	),
	ElicitationDimension.BOUNDARY: "No mobile apps, no SMS delivery, no timezone database maintenance.",
	ElicitationDimension.ORACLE: (
		"A pytest test asserts the reminder row exists in the store, and an HTTP GET of "
		"/reminders returns it with status 200."
	),
	ElicitationDimension.CONSTRAINT: (
		"Python 3.12, no external scheduler daemon, must run inside a 1 GB container."
	),
	ElicitationDimension.FAILURE: (
		"A reminder must never be delivered twice, and no PII may appear in the logs."
	),
}
"""Answers that clear every dimension's floor on the first attempt."""


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Point the advisor at a closed port for every test by default.

	SoFact's default model lives on Ollama's cloud, so an unconfigured test run would
	reach the network and depend on someone else's uptime. Port 9 (discard) refuses
	immediately, which also keeps the unavailability path fast.
	"""
	monkeypatch.setenv("SOFACT_BASE_URL", "http://127.0.0.1:9/v1")
	monkeypatch.setenv("SOFACT_LLM_TIMEOUT", "2")


@pytest.fixture
def home(tmp_path: Path) -> Path:
	"""An isolated SoFact state directory."""
	return tmp_path / "sofact-state"


@pytest.fixture
def service(home: Path) -> FactoryService:
	"""A service with no model attached — the deterministic path."""
	return FactoryService(home=home, llm=None)


async def answer_everything(service: FactoryService, goal_id: str) -> None:
	"""Walk the interrogation to completion, in the service's own question order."""
	assert len(DIMENSIONS) == len(GOOD_ANSWERS), "fixture answers must cover every dimension"
	for _ in range(len(DIMENSIONS)):
		pending = await service.open_question(goal_id)
		if pending is None:
			return
		dimension, _ = pending
		await service.answer(goal_id, dimension, GOOD_ANSWERS[dimension])
	# Answering every dimension is not the same as resolving every dimension: the
	# loop above exits after the last answer, so readiness needs one more look.
	if (await service.open_question(goal_id)) is not None:
		raise AssertionError("interrogation did not terminate")


# --------------------------------------------------------------------------- #
# builders — offered as fixtures so a test never has to construct a contract
# by hand, and so the construction rules live in exactly one place.
# --------------------------------------------------------------------------- #


@pytest.fixture
def make_oracle() -> Callable[..., OracleDeclaration]:
	"""Build an oracle declaration, executable when given a command."""

	def _make(
		command: str | None = None,
		*,
		oracle_class: OracleClass = OracleClass.CONTRACT,
		expect_exit_code: int = 0,
		expect_stdout_contains: str | None = None,
	) -> OracleDeclaration:
		return OracleDeclaration(
			oracle_class=oracle_class,
			description=f"check: {command}" if command else "declared, but not executable",
			command_hint=command,
			expect_exit_code=expect_exit_code,
			expect_stdout_contains=expect_stdout_contains,
		)

	return _make


@pytest.fixture
def make_contract() -> Callable[..., Contract]:
	"""Build a contract from ``(statement, oracle)`` pairs, bypassing elicitation.

	P0 is exercised on its own terms elsewhere; contract and verification tests
	should not have to run a conversation to obtain a clause.
	"""

	def _make(*pairs: tuple[str, OracleDeclaration]) -> Contract:
		assert pairs, "a contract needs at least one clause"
		stems = tuple(
			ClauseStem(
				id=uuid7str(),
				statement=statement,
				kind=ClauseKind.POSITIVE,
				derived_from=ElicitationDimension.OUTCOME,
			)
			for statement, _ in pairs
		)
		draft = SpecificationDraft(
			id=uuid7str(),
			goal_id=uuid7str(),
			created_at=now(),
			stems=stems,
		)
		oracles = {stem.id: oracle for stem, (_, oracle) in zip(stems, pairs, strict=True)}
		return Contract.from_draft(draft, oracles)

	return _make
