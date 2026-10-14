"""FR-103, FR-105, FR-106, FR-107: manufacturing earns a hint, or refuses by name.

The defect this closes is the one ``contract.py`` names in its own docstring: "a
fabricated ``command_hint`` would be a lie that :mod:`sofact.execution` would later
faithfully execute". Abstention was the old answer and it cost a contract its
executability. Manufacturing is the new one, and it is only honest while two things
hold — the artefact the hint names is the artefact that was written, and the check
fails against a tree holding nothing but itself.

So the substance here is the *refusals*, not the successes. A suite that only showed
three languages building three artefacts would pass against a seam that declared a
hint for a file nobody wrote. Every refusal below is a real object implementing
:class:`~sofact.manufacture.ManufactureBackend` — no mocks, because the thing under
test is the seam's verdict and a mock would let a test assert on its own call record
instead.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from sofact._uuid7 import uuid7str
from sofact.audit import audit_oracles
from sofact.execution import OracleRunner, digest_tree
from sofact.manufacture import (
	BACKENDS,
	MANUFACTURE_SPECS,
	ConfiguredManufactureAdapter,
	ManufactureRefusal,
	ManufactureRefusalReason,
	ManufactureRequest,
	ManufactureSpec,
	ManufacturedOracle,
	artefact_index,
	backends_for,
	copy_artefacts,
	load_manufacture_specs,
	manufacture_declarations,
	manufacture_spec_for,
	place_artefacts,
	render_argv,
	slug,
)
from sofact.verification import verify
from sofact.views import (
	Clause,
	ClauseKind,
	Contract,
	Evidence,
	EvidenceKind,
	InterfaceMember,
	InterfaceMemberKind,
	OracleClass,
	OracleDeclaration,
	VerdictOutcome,
	now,
)

MODULE = "widget"

MODULES: dict[str, str] = {
	"python": (
		'"""A module with a declared surface."""\n'
		"\n"
		"LIMIT = 10\n"
		"\n"
		"\n"
		"def tally(items, limit):\n"
		"\treturn len(items) + limit\n"
	),
	"typescript": (
		"export const LIMIT = 10;\n"
		"\n"
		"export function tally(items: number[], limit: number): number {\n"
		"\treturn items.length + limit;\n"
		"}\n"
	),
	"rust": (
		"pub const LIMIT: i64 = 10;\n"
		"\n"
		"pub fn tally(items: Vec<i64>, limit: i64) -> i64 {\n"
		"\titems.len() as i64 + limit\n"
		"}\n"
	),
}

SUFFIXES: dict[str, str] = {"python": ".py", "typescript": ".ts", "rust": ".rs"}

SURFACE: tuple[InterfaceMember, ...] = (
	InterfaceMember(name="tally", kind=InterfaceMemberKind.FUNCTION, parameters=("items", "limit")),
	InterfaceMember(name="LIMIT", kind=InterfaceMemberKind.CONSTANT),
)

MANUFACTURABLE: tuple[tuple[str, OracleClass], ...] = (
	("python", OracleClass.PROPERTY),
	("python", OracleClass.CONTRACT),
	("python", OracleClass.SCHEMA),
	("typescript", OracleClass.CONTRACT),
	("typescript", OracleClass.SCHEMA),
	("rust", OracleClass.CONTRACT),
)
"""Every (language, rank) pair this build claims to build. The parameterisation is the claim."""


def workspace_for(
	tmp_path: Path, language: str, *, surface: tuple[InterfaceMember, ...] = SURFACE
) -> Path:
	"""A real workspace holding the module, laid out the way the spec says to find it."""
	root = tmp_path / f"ws-{language}"
	root.mkdir(parents=True, exist_ok=True)
	(root / f"{MODULE}{SUFFIXES[language]}").write_text(MODULES[language], encoding="utf-8")
	assert surface, "a manufacturable request declares a surface"
	return root


CLAUSE_ID = uuid7str()
"""The clause every request in this module is about.

A real UUID7 rather than a readable placeholder, because the refusal is the *recordable*
form of the seam's verdict — :class:`~sofact.views.ManufactureRefusal` carries
``clause_id: UUID7``, which is the shape a ledger clause id has. A fixture handing the
seam ``"clause-1"`` would be exercising a shape the factory cannot produce.
"""


def request_for(
	workspace: Path,
	oracle_class: OracleClass,
	*,
	surface: tuple[InterfaceMember, ...] = SURFACE,
	module: str = MODULE,
) -> ManufactureRequest:
	return ManufactureRequest(
		clause_id=CLAUSE_ID,
		statement="Every tally reports the items counted plus the limit.",
		kind=ClauseKind.POSITIVE,
		oracle_class=oracle_class,
		module_name=module,
		surface=surface,
		workspace=workspace,
	)


def adapter_for(language: str, workspace: Path) -> ConfiguredManufactureAdapter:
	"""The seam for one language, with no boundary — the host's default in a test."""
	return ConfiguredManufactureAdapter(manufacture_spec_for(language), workspace=workspace)


# --------------------------------------------------------------------------- #
# the earned hint
# --------------------------------------------------------------------------- #


class TestTheHintIsEarnedNotFabricated:
	"""``contract.py``'s invariant, kept by manufacturing rather than by abstaining."""

	@pytest.mark.parametrize(("language", "oracle_class"), MANUFACTURABLE)
	async def test_a_manufactured_hint_names_a_file_that_exists(
		self, tmp_path: Path, language: str, oracle_class: OracleClass
	) -> None:
		"""The one property that makes the hint a fact rather than a claim.

		Asserted against the *filesystem*, not against the backend's return value: a
		backend that returned a plausible path and wrote nothing is exactly the failure
		this closes, and a test that trusted the return value would report it as a pass.
		"""
		workspace = workspace_for(tmp_path, language)
		outcome = await adapter_for(language, workspace).manufacture(
			request_for(workspace, oracle_class)
		)

		assert isinstance(outcome, ManufacturedOracle), outcome
		written = outcome.path if outcome.path.is_absolute() else workspace / outcome.path
		assert written.is_file(), f"{language} declared {written} and did not write it"
		named = Path(outcome.argv[outcome.artefact_argument])
		resolved = named if named.is_absolute() else workspace / named
		assert resolved.resolve() == written.resolve(), (
			"the command must name the artefact that was written, or the check that runs "
			"is not the check that was built"
		)
		assert outcome.observed_exit_code == 0, (
			f"{language}'s check must hold against the module it was built from"
		)

	@pytest.mark.parametrize(("language", "oracle_class"), MANUFACTURABLE)
	async def test_a_real_runner_runs_the_artefact_and_satisfies_the_clause(
		self, tmp_path: Path, language: str, oracle_class: OracleClass
	) -> None:
		"""The end of the chain: the hint reaches ``OracleRunner`` and comes back green.

		Through the real runner and the real verifier, because a manufactured command is
		only worth anything if the component that executes it agrees — and the seam's own
		run is not that component.
		"""
		workspace = workspace_for(tmp_path, language)
		outcome = await adapter_for(language, workspace).manufacture(
			request_for(workspace, oracle_class)
		)
		assert isinstance(outcome, ManufacturedOracle), outcome
		clause = Clause(
			id=uuid7str(),
			statement="Every tally reports the items counted plus the limit.",
			kind=ClauseKind.POSITIVE,
			oracle=OracleDeclaration(
				oracle_class=oracle_class,
				description="manufactured",
				command_hint=outcome.command_hint,
			),
		)
		evidence = await OracleRunner(workspace, timeout=180.0).run(clause)
		verdict = verify(_one_clause_contract(clause), (evidence,)).verdicts[0]

		assert verdict.outcome is VerdictOutcome.SATISFIED, verdict.reason

	async def test_the_backend_name_is_never_written_to_the_ledger(self, tmp_path: Path) -> None:
		"""FR-156: the language is *data about an artefact*, not a field on a declaration.

		Asserted as a field set rather than by searching a rendered string, because the
		interpreter's own name (``tsc``, ``rustc``) legitimately appears in the command —
		what must not appear is a *policy* field saying which backend produced it.
		"""
		workspace = workspace_for(tmp_path, "python")
		oracles, refusals = await manufacture_declarations(
			adapter_for("python", workspace),
			[(request_for(workspace, OracleClass.CONTRACT), _suggestion())],
		)

		assert refusals == ()
		declaration = oracles[CLAUSE_ID]
		assert set(declaration.model_dump(mode="json")) == set(OracleDeclaration.model_fields)
		assert "backend" not in OracleDeclaration.model_fields, (
			"a backend field would put a deployment's language choice into the contract, "
			"which FR-156 keeps out of the ledger"
		)
		assert declaration.command_hint is not None


class TestTheArtefactTravelsToWhereTheSessionWorks:
	"""FR-141: a check left in the shared tree is a check the worktree cannot run.

	Under ``isolate`` the session works in a worktree, and ``OracleRunner`` runs
	``cwd=self.workspace`` — so a command naming an artefact that only exists in the
	shared tree finds nothing and reports a failure of the *module*. The defect this
	closes is a green suite over a P5 that never places anything.
	"""

	@pytest.mark.parametrize(("language", "oracle_class"), MANUFACTURABLE)
	async def test_placement_finds_the_artefact_the_command_names(
		self, tmp_path: Path, language: str, oracle_class: OracleClass
	) -> None:
		"""Every manufacturable pair, read out of the command rather than assumed."""
		workspace = workspace_for(tmp_path, language)
		outcome = await adapter_for(language, workspace).manufacture(
			request_for(workspace, oracle_class)
		)
		assert isinstance(outcome, ManufacturedOracle), outcome
		declaration = OracleDeclaration(
			oracle_class=oracle_class,
			description="manufactured",
			command_hint=outcome.command_hint,
		)

		found = place_artefacts(declaration, workspace=workspace)

		assert found, (
			f"the {language} command names no file in its own workspace, so a dispatch "
			"into a worktree would run it against nothing"
		)
		for relative in found:
			assert (workspace / relative).is_file(), relative

	async def test_the_copied_artefact_runs_in_a_tree_that_never_saw_it(
		self, tmp_path: Path
	) -> None:
		"""The whole point: the copy is what makes the command executable elsewhere.

		A real ``OracleRunner`` in the destination, with the source tree untouched — so a
		placement that copied nothing would fail here rather than pass on the source's
		own file.
		"""
		source = workspace_for(tmp_path, "python")
		outcome = await adapter_for("python", source).manufacture(
			request_for(source, OracleClass.CONTRACT)
		)
		assert isinstance(outcome, ManufacturedOracle), outcome
		declaration = OracleDeclaration(
			oracle_class=OracleClass.CONTRACT,
			description="manufactured",
			command_hint=outcome.command_hint,
		)
		destination = tmp_path / "worktree"
		destination.mkdir()
		(destination / f"{MODULE}.py").write_text(MODULES["python"], encoding="utf-8")

		written = copy_artefacts(
			place_artefacts(declaration, workspace=source),
			source=source,
			target=destination,
		)

		assert written, "nothing was placed, so the destination cannot run the check"
		clause = Clause(
			id=uuid7str(),
			statement="Every tally reports the items counted plus the limit.",
			kind=ClauseKind.POSITIVE,
			oracle=declaration,
		)
		evidence = await OracleRunner(destination, timeout=180.0).run(clause)
		verdict = verify(_one_clause_contract(clause), (evidence,)).verdicts[0]

		assert verdict.outcome is VerdictOutcome.SATISFIED, verdict.reason

	async def test_a_command_naming_nothing_in_the_workspace_places_nothing(
		self, tmp_path: Path
	) -> None:
		"""The negative half, so the predicate is not "every element is a path".

		``python3`` is an element of every python argv and is not a file in the workspace;
		a predicate that accepted it would copy an interpreter, or raise, at every dispatch.
		"""
		workspace = workspace_for(tmp_path, "python")
		declaration = OracleDeclaration(
			oracle_class=OracleClass.CONTRACT,
			description="the operator's own command",
			command_hint="python3 -c 'import sys; sys.exit(0)'",
		)

		assert place_artefacts(declaration, workspace=workspace) == ()

	async def test_an_artefact_missing_from_the_source_is_refused(self, tmp_path: Path) -> None:
		"""A copy that silently placed nothing would report a module failure later.

		The state this names is real: the contract was built against a different workspace
		than the one being dispatched into, and the honest answer is to say so where the
		cause is legible rather than at the oracle's exit code.
		"""
		source = tmp_path / "source"
		source.mkdir()
		destination = tmp_path / "destination"
		destination.mkdir()

		with pytest.raises(FileNotFoundError, match="not in"):
			copy_artefacts((Path(".sofact-oracles/absent.py"),), source=source, target=destination)


def _one_clause_contract(clause: Clause) -> Contract:
	"""A one-clause contract, so the verifier weighs exactly this observation."""
	body = {
		"id": uuid7str(),
		"goal_id": uuid7str(),
		"version": 1,
		"created_at": now(),
		"clauses": [clause],
	}
	return Contract.model_validate(body)


def _suggestion() -> OracleDeclaration:
	"""What ``suggest_oracle`` would have produced: prose, and no command."""
	return OracleDeclaration(
		oracle_class=OracleClass.CONTRACT,
		description="Every tally reports the items counted plus the limit.",
	)


# --------------------------------------------------------------------------- #
# the refusals
# --------------------------------------------------------------------------- #


class _LyingBackend:
	"""A real backend that is wrong in exactly one way, chosen by the caller.

	Implements :class:`~sofact.manufacture.ManufactureBackend` structurally, so the seam
	consults it exactly as it consults a shipped one — the seam's refusal is the subject,
	and a mock would let a test assert on its own call record instead.

	Three fields, because the seam checks three separate things and a fake has to be able
	to fail each one alone: ``writes`` is where the file is actually put (``None``:
	nowhere), ``reports`` is the ``path`` on the returned artefact (``None``: ``writes``),
	and ``commands`` is what the argv names (``None``: ``reports``). Collapsing any two of
	them makes a refusal unreachable — which is how this object was first written, and the
	test that could not fail is what said so.
	"""

	def __init__(
		self,
		spec: ManufactureSpec,
		*,
		writes: Path | None,
		reports: Path | None = None,
		commands: Path | None = None,
	) -> None:
		self.spec = spec
		self.writes = writes
		self.reports = writes if reports is None else reports
		self.commands = self.reports if commands is None else commands

	@property
	def language(self) -> str:
		return self.spec.language

	def supports(self, oracle_class: OracleClass) -> bool:
		return True

	async def manufacture(self, request: ManufactureRequest) -> ManufacturedOracle:
		if self.writes is not None:
			target = self.writes if self.writes.is_absolute() else request.workspace / self.writes
			target.parent.mkdir(parents=True, exist_ok=True)
			target.write_text("print('written')\n", encoding="utf-8")
		assert self.reports is not None and self.commands is not None
		return ManufacturedOracle(
			path=self.reports,
			argv=render_argv(self.spec, self.commands),
			artefact_argument=artefact_index(self.spec),
			provenance="a hint that may not describe what was written",
		)


class TestTheSeamRefusesADishonestBackend:
	"""Four refusals, each a different defect with a different remedy."""

	async def test_a_hint_for_a_path_that_was_never_written_is_refused(
		self, tmp_path: Path
	) -> None:
		"""The central case. A backend that names a path and writes nothing would give
		``sofact.execution`` a command that fails for a reason saying nothing about the
		module — FR-105's defect, manufactured rather than discovered."""
		workspace = workspace_for(tmp_path, "python")
		adapter = adapter_for("python", workspace)
		adapter.backend = _LyingBackend(
			adapter.spec, writes=None, reports=Path(".sofact-oracles") / "never_written.py"
		)

		outcome = await adapter.manufacture(request_for(workspace, OracleClass.CONTRACT))

		assert isinstance(outcome, ManufactureRefusal), outcome
		assert outcome.reason is ManufactureRefusalReason.ARTEFACT_MISSING
		assert not (workspace / ".sofact-oracles" / "never_written.py").exists()

	async def test_a_command_naming_a_different_file_is_refused(self, tmp_path: Path) -> None:
		"""The write happened and the *command* points elsewhere. Distinct from a missing
		write, because every artefact on disk looks correct while the spec's run argv is
		wrong — so the refusal has to name the mismatch rather than the absence."""
		workspace = workspace_for(tmp_path, "python")
		adapter = adapter_for("python", workspace)
		# The artefact is written where the seam will find it; the *argv* points elsewhere.
		adapter.backend = _LyingBackend(
			adapter.spec,
			writes=Path(".sofact-oracles") / "written.py",
			commands=Path(".sofact-oracles") / "named.py",
		)

		outcome = await adapter.manufacture(request_for(workspace, OracleClass.CONTRACT))

		assert isinstance(outcome, ManufactureRefusal), outcome
		assert outcome.reason is ManufactureRefusalReason.COMMAND_NAMES_ANOTHER_FILE
		assert (workspace / ".sofact-oracles" / "written.py").exists(), (
			"the write happened, which is what separates this refusal from a missing artefact"
		)

	async def test_a_path_outside_the_workspace_is_refused(self, tmp_path: Path) -> None:
		"""FR-059: a check the producer can reach and rewrite is not a check.

		The path is outside the module's workspace, which is where the producer works —
		so an artefact there is one the producer could edit to pass.
		"""
		workspace = workspace_for(tmp_path, "python")
		outside = tmp_path / "outside.py"
		outside.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
		adapter = adapter_for("python", workspace)
		adapter.backend = _LyingBackend(adapter.spec, writes=outside)

		outcome = await adapter.manufacture(request_for(workspace, OracleClass.CONTRACT))

		assert isinstance(outcome, ManufactureRefusal), outcome
		assert outcome.reason is ManufactureRefusalReason.ARTEFACT_OUTSIDE_WORKSPACE

	async def test_a_command_that_never_terminates_is_refused(self, tmp_path: Path) -> None:
		"""``None`` is not an exit code. A check that hung established nothing about the
		module, and reporting it as a failure of the module would be a verdict the factory
		never measured."""
		workspace = workspace_for(tmp_path, "python")
		adapter = ConfiguredManufactureAdapter(
			manufacture_spec_for("python"), workspace=workspace, timeout=0.5
		)
		adapter.backend = _SleepingBackend(adapter.spec)

		outcome = await adapter.manufacture(request_for(workspace, OracleClass.CONTRACT))

		assert isinstance(outcome, ManufactureRefusal), outcome
		assert outcome.reason is ManufactureRefusalReason.COMMAND_DID_NOT_RUN

	async def test_a_check_that_passes_on_an_empty_tree_is_refused(self, tmp_path: Path) -> None:
		"""FR-107, and the refusal that matters: "a manufactured oracle that can be
		satisfied without implementing the invariant is a worse defect than a missing
		test, because it manufactures false confidence."

		The artefact here is a real file that really exits 0. It is written to the path
		its command names, so every other assertion passes — which is what makes the
		vacuity audit the *only* thing standing between this and a declared oracle.
		"""
		workspace = workspace_for(tmp_path, "python")
		adapter = adapter_for("python", workspace)
		adapter.backend = _TrivialBackend(adapter.spec)

		outcome = await adapter.manufacture(request_for(workspace, OracleClass.CONTRACT))

		assert isinstance(outcome, ManufactureRefusal), outcome
		assert outcome.reason is ManufactureRefusalReason.VACUOUS
		assert "empty tree" in outcome.detail or "nothing but itself" in outcome.detail


class _SleepingBackend:
	"""A real backend whose artefact sleeps past the seam's timeout."""

	def __init__(self, spec: ManufactureSpec) -> None:
		self.spec = spec

	@property
	def language(self) -> str:
		return self.spec.language

	def supports(self, oracle_class: OracleClass) -> bool:
		return True

	async def manufacture(self, request: ManufactureRequest):
		target = Path(self.spec.artefact_directory) / "sleeping.py"
		absolute = request.workspace / target
		absolute.parent.mkdir(parents=True, exist_ok=True)
		absolute.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
		return ManufacturedOracle(
			path=target,
			argv=render_argv(self.spec, target),
			artefact_argument=artefact_index(self.spec),
			provenance="a check that does not finish",
		)


class _TrivialBackend:
	"""A real backend whose artefact exits 0 having checked nothing."""

	def __init__(self, spec: ManufactureSpec) -> None:
		self.spec = spec

	@property
	def language(self) -> str:
		return self.spec.language

	def supports(self, oracle_class: OracleClass) -> bool:
		return True

	async def manufacture(self, request: ManufactureRequest):
		target = Path(self.spec.artefact_directory) / "trivial.py"
		absolute = request.workspace / target
		absolute.parent.mkdir(parents=True, exist_ok=True)
		absolute.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
		return ManufacturedOracle(
			path=target,
			argv=render_argv(self.spec, target),
			artefact_argument=artefact_index(self.spec),
			provenance="a check satisfied by nothing",
		)


class TestTheSeamRefusesBeforeAnyBackendIsConsulted:
	"""Rank 6, and the ranks no backend builds."""

	@pytest.mark.parametrize("language", sorted(MANUFACTURE_SPECS))
	async def test_a_held_out_oracle_is_refused_for_every_language(
		self, tmp_path: Path, language: str
	) -> None:
		"""FR-106's holdout is the operator's example, so the factory manufactures none.

		Refused at the seam rather than in each backend, because a backend able to return
		one would re-open FR-106 by the manufacturing door — and the door has to be
		closed once, not three times.
		"""
		workspace = workspace_for(tmp_path, language)
		adapter = adapter_for(language, workspace)

		assert not adapter.supports(OracleClass.EXAMPLE)
		outcome = await adapter.manufacture(request_for(workspace, OracleClass.EXAMPLE))

		assert isinstance(outcome, ManufactureRefusal), outcome
		assert outcome.reason is ManufactureRefusalReason.HELD_OUT

	@pytest.mark.parametrize(
		("language", "oracle_class"),
		[
			("typescript", OracleClass.PROPERTY),
			("typescript", OracleClass.GOLDEN),
			("typescript", OracleClass.STATE_MACHINE),
			("rust", OracleClass.PROPERTY),
			("rust", OracleClass.SCHEMA),
			("python", OracleClass.GOLDEN),
			("python", OracleClass.METAMORPHIC),
			("python", OracleClass.STATE_MACHINE),
		],
	)
	async def test_a_rank_the_backend_does_not_build_is_refused_by_name(
		self, tmp_path: Path, language: str, oracle_class: OracleClass
	) -> None:
		"""A named refusal, not a plausible-looking weaker check.

		``UNSUPPORTED_RANK`` is what lets the gate report ground-truth debt (FR-108)
		honestly: a rank-7 golden captured before the system exists would be the digest of
		an empty tree blessed as the expected value.
		"""
		workspace = workspace_for(tmp_path, language)
		outcome = await adapter_for(language, workspace).manufacture(
			request_for(workspace, oracle_class)
		)

		assert isinstance(outcome, ManufactureRefusal), outcome
		assert outcome.reason is ManufactureRefusalReason.UNSUPPORTED_RANK
		assert outcome.detail.strip()

	@pytest.mark.parametrize("language", sorted(MANUFACTURE_SPECS))
	async def test_an_empty_declared_surface_is_refused_rather_than_checked(
		self, tmp_path: Path, language: str
	) -> None:
		"""A check over nothing is satisfied by every tree, including an empty one.

		The refusal is what keeps an empty domain from reading as a pass — the same
		subset failure the vacuity audit exists for, caught one step earlier and cheaper.
		"""
		workspace = workspace_for(tmp_path, language)
		outcome = await adapter_for(language, workspace).manufacture(
			request_for(workspace, OracleClass.CONTRACT, surface=())
		)

		assert isinstance(outcome, ManufactureRefusal), outcome
		assert outcome.reason is ManufactureRefusalReason.NO_DECLARED_SURFACE


class TestTheArtefactFailsWhereItShould:
	"""The check is a real check: it can fail, which is what makes it an instrument."""

	async def test_the_python_contract_check_fails_on_a_missing_member(
		self, tmp_path: Path
	) -> None:
		"""A declared member the module does not have must make the artefact exit non-zero.

		Run against a workspace whose module is missing one declared name, so the check
		has something real to disagree with.
		"""
		workspace = workspace_for(tmp_path, "python")
		(workspace / "widget.py").write_text("LIMIT = 10\n", encoding="utf-8")
		adapter = adapter_for("python", workspace)

		outcome = await adapter.manufacture(request_for(workspace, OracleClass.CONTRACT))

		assert isinstance(outcome, ManufacturedOracle), outcome
		assert outcome.observed_exit_code != 0, (
			"a module missing a declared member must fail the completeness check"
		)

	async def test_the_python_property_check_fails_on_an_undeclared_public_name(
		self, tmp_path: Path
	) -> None:
		"""Rank 1's negative shape: nothing public is undeclared (FR-090).

		A module exposing a name its surface never declared is a module whose permitted set
		was exceeded, which is what a NEGATIVE clause bounds.
		"""
		workspace = workspace_for(tmp_path, "python")
		(workspace / "widget.py").write_text(
			"LIMIT = 10\n\n\ndef tally(items, limit):\n\treturn len(items) + limit\n\n\ndef smuggled():\n\treturn 1\n",
			encoding="utf-8",
		)

		outcome = await adapter_for("python", workspace).manufacture(
			request_for(workspace, OracleClass.PROPERTY)
		)

		assert isinstance(outcome, ManufacturedOracle), outcome
		assert outcome.observed_exit_code != 0, (
			"a public name the surface never declared must fail the closed check"
		)

	async def test_the_rust_check_discards_its_build_product(self, tmp_path: Path) -> None:
		"""A compiled binary inside the workspace would be committed by the seal and folded
		into FR-006's cache key — a digest that moved because of a build product would
		invalidate a verdict nothing touched."""
		workspace = workspace_for(tmp_path, "rust")
		outcome = await adapter_for("rust", workspace).manufacture(
			request_for(workspace, OracleClass.CONTRACT)
		)
		assert isinstance(outcome, ManufacturedOracle), outcome

		leftovers = sorted(p.name for p in (workspace / ".sofact-oracles").glob("*.bin*"))
		assert leftovers == [], f"the build product was left behind: {leftovers}"
		digest = digest_tree(workspace)
		assert digest, "the tree must still digest"


class TestTheAuditAgreesWithTheSeam:
	"""FR-107's audit and the seam's own vacuity check are one rule, applied twice."""

	async def test_a_manufactured_oracle_fails_the_empty_workspace_audit(
		self, tmp_path: Path
	) -> None:
		"""FR-107's interaction with P8: ``audit_oracles`` probes oracles that have a
		command and are POSITIVE, so a manufactured oracle *will* be probed against an
		empty workspace — and must fail there, or it is a finding.

		A green audit over a manufactured oracle is the defect; this asserts the audit
		can see it.
		"""
		workspace = workspace_for(tmp_path, "python")
		outcome = await adapter_for("python", workspace).manufacture(
			request_for(workspace, OracleClass.CONTRACT)
		)
		assert isinstance(outcome, ManufacturedOracle), outcome
		clause = Clause(
			id=uuid7str(),
			statement="Every tally reports the items counted plus the limit.",
			kind=ClauseKind.POSITIVE,
			oracle=OracleDeclaration(
				oracle_class=OracleClass.CONTRACT,
				description="manufactured",
				command_hint=outcome.command_hint,
			),
		)

		report = await audit_oracles(_one_clause_contract(clause), timeout=60.0)

		assert len(report.probed) == 1, "a positive, executable clause must be probed"
		assert report.findings == (), (
			"an oracle that fails against an empty workspace is the good case; a finding "
			"here would mean the manufactured check passes without the module existing"
		)


class TestEvidenceKindIsDerived:
	"""Why the kind is a property and not a field."""

	async def test_a_manufactured_oracle_reports_command_output(self, tmp_path: Path) -> None:
		"""``OracleRunner`` produces ``COMMAND_OUTPUT`` and nothing else, so a backend
		declaring ``PROPERTY_RUN`` would describe evidence no component emits."""
		workspace = workspace_for(tmp_path, "python")
		outcome = await adapter_for("python", workspace).manufacture(
			request_for(workspace, OracleClass.CONTRACT)
		)
		assert isinstance(outcome, ManufacturedOracle), outcome
		assert outcome.evidence_kind is EvidenceKind.COMMAND_OUTPUT

	def test_a_property_run_with_no_cases_is_insufficient(self) -> None:
		"""The rule that makes the derived kind load-bearing rather than cosmetic.

		``PROPERTY_RUN`` treats zero cases as ``INSUFFICIENT`` — a domain nobody quantified
		over demonstrates nothing. A manufactured oracle claiming that kind would be
		claiming a rule that judges it, and this is the rule.
		"""
		clause = Clause(
			id=uuid7str(),
			statement="Every tally reports the items counted plus the limit.",
			kind=ClauseKind.POSITIVE,
			oracle=OracleDeclaration(
				oracle_class=OracleClass.PROPERTY,
				description="a property",
				command_hint="true",
			),
		)
		contract = _one_clause_contract(clause)
		evidence = Evidence.record(
			clause_id=clause.id,
			kind=EvidenceKind.PROPERTY_RUN,
			produced_by="test",
			payload={"cases": 0, "failures": 0},
		)
		verdict = verify(contract, (evidence,)).verdicts[0]

		assert verdict.outcome is VerdictOutcome.INSUFFICIENT
		assert "exercises nothing" in verdict.reason


# --------------------------------------------------------------------------- #
# the spec table, read the way a harness spec is read
# --------------------------------------------------------------------------- #


class TestTheSpecIsData:
	"""FR-156: which languages a factory builds in is a deployment's answer."""

	def test_the_built_in_table_names_python_and_registers_every_backend(self) -> None:
		"""D5's ruling, encoded as data: Python is the default and the others sit beside it."""
		assert "python" in MANUFACTURE_SPECS
		assert set(MANUFACTURE_SPECS) == set(BACKENDS)
		for name, spec in MANUFACTURE_SPECS.items():
			assert spec.backend in BACKENDS, f"{name} names an unregistered backend"
			assert "{artefact}" in " ".join(spec.run_argv)

	def test_a_spec_naming_no_artefact_is_refused(self) -> None:
		"""A run argv that never names the artefact cannot be checked against one."""
		with pytest.raises(AssertionError, match="must name the artefact"):
			ManufactureSpec(
				language="nowhere",
				backend="python",
				artefact_directory=".x",
				source_suffixes=(".x",),
				run_argv=("python3", "-c", "pass"),
			)

	def test_an_unknown_field_is_refused_by_name(self) -> None:
		"""A misspelled ``run_arg`` silently defaulted would run the wrong thing, and the
		verdict would then be about something else."""
		payload: dict[str, object] = {
			"language": "python",
			"backend": "python",
			"artefact_directory": ".x",
			"source_suffixes": [".py"],
			"run_argv": ["python3", "{artefact}"],
			"run_arg": ["oops"],
		}
		with pytest.raises(ValueError, match="unknown field"):
			ManufactureSpec.from_mapping("python", payload)

	def test_a_missing_required_field_is_refused_by_name(self) -> None:
		payload: dict[str, object] = {"language": "python", "backend": "python"}
		with pytest.raises(ValueError, match="missing field"):
			ManufactureSpec.from_mapping("python", payload)

	def test_a_table_round_trips_through_a_file(self, tmp_path: Path) -> None:
		"""The seam a deployment actually uses: a JSON file replacing the built-in table."""
		path = tmp_path / "manufacture.json"
		path.write_text(
			json.dumps(
				{
					"languages": {
						"python": {
							"language": "python",
							"backend": "python",
							"artefact_directory": ".checks",
							"source_suffixes": [".py"],
							"run_argv": ["python3.12", "{artefact}"],
						}
					}
				}
			),
			encoding="utf-8",
		)
		loaded = load_manufacture_specs(path)

		assert set(loaded) == {"python"}
		assert loaded["python"].run_argv == ("python3.12", "{artefact}")
		assert loaded["python"].artefact_directory == ".checks"

	def test_an_empty_table_is_refused(self, tmp_path: Path) -> None:
		"""An empty table names nothing to manufacture, and a factory that read it as
		"build nothing" would report every clause as ground-truth debt with no reason."""
		path = tmp_path / "empty.json"
		path.write_text(json.dumps({"languages": {}}), encoding="utf-8")
		with pytest.raises(ValueError, match="no languages"):
			load_manufacture_specs(path)

	def test_an_unknown_language_is_refused_with_the_configured_names(self) -> None:
		with pytest.raises(KeyError, match="unknown manufacturing language"):
			manufacture_spec_for("cobol")

	def test_an_unknown_backend_is_refused_by_name_rather_than_defaulted(self) -> None:
		"""A silent fallback to Python would run a Python check against a Rust module:
		the artefact would exist, the command would run, and every layer would report a
		genuine failure of the module rather than a misconfiguration."""
		spec = replace(MANUFACTURE_SPECS["python"], backend="cobol")
		with pytest.raises(KeyError, match="names backend"):
			backends_for(spec)

	def test_slug_is_lossy_and_says_so(self) -> None:
		"""The slug is what the artefact searches for, so a lossy mapping is recorded
		rather than hidden — and the two-candidate refusal is what catches a collision."""
		assert slug("Widget Ledger") == "widget_ledger"
		assert slug("2fa") == "m_2fa"
		assert slug("  spaced  ") == "spaced"
		assert slug("a-b") == slug("a_b"), "punctuation collapses, which is why two is a refusal"
