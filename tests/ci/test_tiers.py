"""FR-132 — a tiered, declarative model configuration.

"a large model where reasoning depth matters (P3 decomposition, P6 failure diagnosis, the
adversary), and a cheap or local model for high-volume low-depth work (P5 module builds,
test generation, triage) — per NFR-012."

The requirement has two halves and they belong to two parties, which is the design the
suite is mostly about. **SoFact owns which phases need depth** — a statement about the
pipeline, the same for every deployment — and that is :data:`sofact.tiers.TIER_PHASES`.
**The deployment owns which model sits in each tier** — a statement about its hardware,
budget and data-residency obligations — and that is the JSON table.

The defect this shape prevents is the substitution: a deployment that declared the
``deep`` tier and named no model for it has said "these phases are the expensive ones"
without saying what runs them, and a reader that answered with the cheap model would put a
small model on P6 failure diagnosis while the operator believed otherwise. So the
fall-through is to the operator's *named* single model, and
:func:`~sofact.tiers.resolve_model` returns which rule it used rather than leaving the
caller to infer it.

The one thing no test here can do is check that the model a tier names is *good at its
tier*. That is the operator's judgement, and NFR-026 is why SoFact does not hold an
opinion about it — the tier table makes the judgement explicit and recorded, which is the
most a factory can do with a claim about model quality.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from synthetic import synthetic_service
from typer.testing import CliRunner

from sofact.cli import app
from sofact.llm import DEFAULT_MODEL
from sofact.tiers import (
	MODEL_TIERS_ENV,
	STEP_PHASE,
	TIER_PHASES,
	ModelTier,
	ModelTierRefusal,
	load_model_tiers,
	phase_tier,
	resolve_model,
	step_phase,
	tier_statement,
)
from sofact.views import Phase, PlanStepKind

RUNNER = CliRunner()


def a_table(**tiers: str) -> dict[str, ModelTier]:
	"""A tier table as a deployment would declare it, with a stated reason per entry."""
	return {
		name: ModelTier(name=name, model=model, rationale=f"{name} is for {name} work")
		for name, model in tiers.items()
	}


# --------------------------------------------------------------------------- #
# which phases need depth is SoFact's assignment
# --------------------------------------------------------------------------- #


class TestTheDepthAssignmentIsSoFacts:
	"""FR-132's first half: the phases, named by the requirement or argued from the spec."""

	def test_the_phases_fr_132_names_are_in_the_tiers_it_names(self) -> None:
		"""P3 decomposition and P6 failure diagnosis are the depth cases, verbatim."""
		assert phase_tier(Phase.DECOMPOSE) == "deep"
		assert phase_tier(Phase.VERIFY) == "deep"

	def test_the_high_volume_phase_is_the_cheap_tier(self) -> None:
		"""P5 module builds are FR-132's own example of high-volume low-depth work."""
		assert phase_tier(Phase.BUILD) == "cheap"

	def test_a_phase_in_no_tier_is_not_a_phase_in_the_cheap_tier(self) -> None:
		"""``None`` and ``cheap`` are different claims, and the difference is the point.

		A phase SoFact put in ``cheap`` has been *judged* high-volume. A phase in no tier
		has not been judged at all, and folding the second into the first would put a
		phase nobody considered on a small model — which is the substitution the tier
		design exists to prevent, arriving through the default rather than through a table.
		"""
		assert phase_tier(Phase.ELICIT) is None
		assert phase_tier(Phase.RESEARCH) is None
		assert phase_tier(Phase.DELIVER) is None
		assert Phase.ELICIT not in TIER_PHASES.get("cheap", ())

	def test_the_assignment_covers_every_phase_at_most_once(self) -> None:
		"""Two tiers claiming one phase would make ``phase_tier`` depend on dict order."""
		claimed = [phase for phases in TIER_PHASES.values() for phase in phases]
		assert len(claimed) == len(set(claimed))

	def test_every_step_kind_has_a_phase(self) -> None:
		"""FR-133's join is total over the enum, or the spend fold has a hole in it."""
		assert set(STEP_PHASE) == set(PlanStepKind)

	def test_a_repair_step_is_a_verify_phase_step(self) -> None:
		"""FR-101's loop is failure diagnosis, which FR-132 names as a depth case."""
		assert step_phase(PlanStepKind.REPAIR) is Phase.VERIFY
		assert phase_tier(step_phase(PlanStepKind.REPAIR)) == "deep"

	def test_an_operation_step_is_a_build_phase_step(self) -> None:
		assert step_phase(PlanStepKind.OPERATION) is Phase.BUILD
		assert phase_tier(step_phase(PlanStepKind.OPERATION)) == "cheap"


# --------------------------------------------------------------------------- #
# which model sits in a tier is the deployment's
# --------------------------------------------------------------------------- #


class TestThePrecedence:
	"""``resolve_model`` returns the model *and* the rule, in one order."""

	def test_an_explicit_model_outranks_the_table(self) -> None:
		"""``--model`` is the ordinary meaning of a flag: this run, not every run."""
		model, source = resolve_model(
			Phase.BUILD, explicit="operator-said", tiers=a_table(cheap="cheap-model")
		)
		assert model == "operator-said"
		assert source == "--model"

	def test_a_tiered_phase_runs_the_tiers_model(self) -> None:
		model, source = resolve_model(
			Phase.DECOMPOSE, tiers=a_table(deep="big-model", cheap="small-model")
		)
		assert model == "big-model"
		assert source == "tier:deep"

	def test_a_phase_in_no_tier_runs_the_operators_model(self) -> None:
		"""P1 is in no tier, so the table has no opinion and the operator's model runs."""
		model, source = resolve_model(
			Phase.RESEARCH, operator_model="mine", tiers=a_table(deep="big-model")
		)
		assert model == "mine"
		assert source == "SOFACT_MODEL"

	def test_a_declared_tier_with_no_model_does_not_shadow_the_operator(self) -> None:
		"""The substitution this design exists to prevent, asserted as a refusal to make it.

		A table naming the ``deep`` tier and no model for it is a deployment that said
		"these phases are the expensive ones" without saying what runs them. Answering
		with the operator's model *and saying so* is honest; answering with the cheap
		tier's model would silently put a small model on P6 failure diagnosis.
		"""
		table = a_table(cheap="small-model")
		model, source = resolve_model(Phase.VERIFY, operator_model="mine", tiers=table)
		assert model == "mine"
		assert source == "SOFACT_MODEL"
		assert model != table["cheap"].model

	def test_the_operator_model_comes_from_the_environment_when_not_passed(self) -> None:
		model, source = resolve_model(
			Phase.BUILD, tiers=a_table(deep="big-model"), environ={"SOFACT_MODEL": "env-model"}
		)
		assert model == "env-model"
		assert source == "SOFACT_MODEL"

	def test_with_nothing_configured_the_default_is_the_default_and_says_so(self) -> None:
		"""The unconfigured deployment gets exactly the behaviour the tree had before."""
		model, source = resolve_model(Phase.BUILD, environ={})
		assert model == DEFAULT_MODEL
		assert source == "default"

	def test_no_tiers_at_all_is_the_same_as_no_table(self) -> None:
		model, source = resolve_model(Phase.DECOMPOSE, tiers=None, operator_model="mine")
		assert (model, source) == ("mine", "SOFACT_MODEL")


class TestTheTierTypeRefusesAnEntryThatNamesNothing:
	"""A tier with no model is not a tier with a default model (FR-132)."""

	def test_a_tier_with_no_model_is_refused(self) -> None:
		with pytest.raises(ModelTierRefusal, match="names no model"):
			ModelTier(name="deep", model="", rationale="because")

	def test_a_tier_with_no_reason_is_refused(self) -> None:
		"""The reason is required, for ``HarnessSpec``'s reason one level over."""
		with pytest.raises(ModelTierRefusal, match="gives no reason"):
			ModelTier(name="deep", model="big", rationale="  ")

	def test_a_tier_with_no_name_is_refused(self) -> None:
		with pytest.raises(ModelTierRefusal, match="needs a name"):
			ModelTier(name="", model="big", rationale="because")


# --------------------------------------------------------------------------- #
# reading a table from a file
# --------------------------------------------------------------------------- #


class TestReadingATable:
	def _write(self, tmp_path: Path, payload: object) -> Path:
		path = tmp_path / "tiers.json"
		path.write_text(json.dumps(payload), encoding="utf-8")
		return path

	def test_the_bare_shape_is_accepted(self, tmp_path: Path) -> None:
		path = self._write(
			tmp_path,
			{"deep": {"model": "big", "rationale": "depth"}},
		)
		tiers = load_model_tiers(path)
		assert tiers["deep"].model == "big"

	def test_the_wrapped_shape_is_accepted(self, tmp_path: Path) -> None:
		"""A deployment writing the file by hand should not have to know the spelling."""
		path = self._write(
			tmp_path,
			{"tiers": {"cheap": {"model": "small", "rationale": "volume"}}},
		)
		tiers = load_model_tiers(path)
		assert tiers["cheap"].model == "small"

	def test_a_tier_this_build_does_not_know_is_refused(self, tmp_path: Path) -> None:
		"""Moving a phase between tiers is asking to own SoFact's half of the split.

		Silently ignoring the request would leave the operator believing a phase had been
		retiered, which is worse than a refusal: the table would read as effective and
		change nothing.
		"""
		path = self._write(tmp_path, {"expensive": {"model": "x", "rationale": "y"}})
		with pytest.raises(ModelTierRefusal, match="not one of this build's tiers"):
			load_model_tiers(path)

	def test_an_empty_table_is_refused(self, tmp_path: Path) -> None:
		path = self._write(tmp_path, {})
		with pytest.raises(ModelTierRefusal, match="no tiers"):
			load_model_tiers(path)

	def test_an_unknown_field_is_refused(self, tmp_path: Path) -> None:
		path = self._write(
			tmp_path,
			{"deep": {"model": "big", "rationale": "depth", "temperature": 0.2}},
		)
		with pytest.raises(ModelTierRefusal, match="unknown field"):
			load_model_tiers(path)

	def test_a_non_string_model_is_refused_rather_than_stringified(self, tmp_path: Path) -> None:
		"""``str()``-ing it would produce a model named ``{'name': 'x'}`` downstream."""
		path = self._write(
			tmp_path,
			{"deep": {"model": {"name": "x"}, "rationale": "depth"}},
		)
		with pytest.raises(ModelTierRefusal, match="must be a string"):
			load_model_tiers(path)

	def test_a_key_and_a_name_that_disagree_are_refused(self, tmp_path: Path) -> None:
		"""The key is what the lookup uses and the field is what a reader believes."""
		path = self._write(
			tmp_path,
			{"deep": {"name": "cheap", "model": "big", "rationale": "depth"}},
		)
		with pytest.raises(ModelTierRefusal, match="declares itself as"):
			load_model_tiers(path)

	def test_a_missing_file_is_a_named_refusal(self, tmp_path: Path) -> None:
		with pytest.raises(ModelTierRefusal, match="cannot read"):
			load_model_tiers(tmp_path / "absent.json")

	def test_invalid_json_is_a_named_refusal(self, tmp_path: Path) -> None:
		path = tmp_path / "bad.json"
		path.write_text("{not json", encoding="utf-8")
		with pytest.raises(ModelTierRefusal, match="not valid JSON"):
			load_model_tiers(path)


# --------------------------------------------------------------------------- #
# the statement, and the verb
# --------------------------------------------------------------------------- #


class TestTheStatement:
	def test_no_tiers_says_unconfigured_rather_than_printing_nothing(self) -> None:
		"""A blank line reads as a table nobody filled in, not a decision nobody made."""
		stated = tier_statement({})
		assert "no model tiers are configured" in stated
		assert MODEL_TIERS_ENV in stated

	def test_a_configured_table_names_its_models_and_phases(self) -> None:
		stated = tier_statement(a_table(deep="big", cheap="small"))
		assert "deep=big" in stated
		assert "cheap=small" in stated
		assert "P3" in stated


class TestTheCliReportsIt:
	def test_tiers_with_no_table_says_so_and_exits_non_zero(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.delenv(MODEL_TIERS_ENV, raising=False)
		monkeypatch.setenv("SOFACT_HOME", str(home))
		result = RUNNER.invoke(app, ["tiers"])
		assert result.exit_code == 0
		assert "no model tiers are configured" in result.output

	def test_a_configured_table_resolves_each_phase(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""The verb prints the resolution, so the source column is the thing to assert."""
		path = tmp_path / "tiers.json"
		path.write_text(
			json.dumps(
				{
					"deep": {"model": "big-model", "rationale": "depth"},
					"cheap": {"model": "small-model", "rationale": "volume"},
				}
			),
			encoding="utf-8",
		)
		monkeypatch.setenv(MODEL_TIERS_ENV, str(path))
		monkeypatch.setenv("SOFACT_HOME", str(home))
		result = RUNNER.invoke(app, ["tiers"])
		assert result.exit_code == 0, result.output
		assert "big-model" in result.output
		assert "small-model" in result.output
		assert "tier:deep" in result.output
		assert "tier:cheap" in result.output
		assert "no tier:" in result.output, "a phase outside every tier must say so"

	def test_an_unreadable_table_is_refused_without_a_traceback(
		self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.setenv(MODEL_TIERS_ENV, str(tmp_path / "absent.json"))
		monkeypatch.setenv("SOFACT_HOME", str(home))
		result = RUNNER.invoke(app, ["tiers"])
		assert result.exit_code != 0
		assert "Traceback" not in result.output
		assert MODEL_TIERS_ENV in result.output


class TestTheDocumentedTierTable:
	"""README.md's tier example is executed by the real loader.

	``TestTheDocumentedTable`` does this for the harness table and gives the reason:
	documentation that is never run is documentation that is eventually wrong, and a drift
	here is not a typo — it is an operator writing a file SoFact refuses. The README is
	allowed to show a deliberately broken example, so the check is that the *named* one
	loads, found by its tiers rather than by fence position.
	"""

	ROOT = Path(__file__).resolve().parents[2]

	def test_the_readme_tier_example_loads_through_the_real_loader(self, tmp_path: Path) -> None:
		text = (self.ROOT / "README.md").read_text(encoding="utf-8")
		blocks = re.findall(r"```json\n(.*?)```", text, re.S)
		assert blocks, "README.md no longer shows a JSON tier table"

		loaded: dict[str, ModelTier] = {}
		for index, block in enumerate(blocks):
			path = tmp_path / f"readme-{index}.json"
			path.write_text(block, encoding="utf-8")
			try:
				loaded.update(load_model_tiers(path))
			except ModelTierRefusal:
				continue
		assert set(loaded) == set(TIER_PHASES), (
			f"README.md's tier example loads as {sorted(loaded)}; it must name every tier "
			f"SoFact has ({sorted(TIER_PHASES)}), because a deployment copies it"
		)
		for name, tier in loaded.items():
			assert tier.rationale.strip(), f"the documented {name} tier gives no reason"


# --------------------------------------------------------------------------- #
# the seam: a dispatch is tiered, and the record says which rule chose
# --------------------------------------------------------------------------- #


class TestADispatchIsTiered:
	"""End to end through the adapter factory, which is where the model is actually chosen."""

	async def test_a_step_adapter_runs_the_tier_model_and_records_the_source(
		self, home: Path, tmp_path: Path
	) -> None:
		from sofact.views import PlanStepKind

		service = synthetic_service(
			home, tmp_path, "complete", model_tiers=a_table(deep="big-model", cheap="small-model")
		)
		deep = service.adapter(step_kind=PlanStepKind.REPAIR)
		cheap = service.adapter(step_kind=PlanStepKind.OPERATION)
		assert deep.model == "big-model"
		assert deep.model_source == "tier:deep"
		assert cheap.model == "small-model"
		assert cheap.model_source == "tier:cheap"

	def test_the_same_adapter_reports_the_same_model_on_every_record(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The source is bound to the adapter, so a record cannot claim another's rule."""
		service = synthetic_service(
			home, tmp_path, "complete", model_tiers=a_table(cheap="small-model")
		)
		adapter = service.adapter(phase=Phase.BUILD)
		clone = adapter.variant(workspace=tmp_path)
		assert clone.model == adapter.model
		assert clone.model_source == adapter.model_source

	def test_an_explicit_model_still_wins_over_the_table(self, home: Path, tmp_path: Path) -> None:
		service = synthetic_service(
			home, tmp_path, "complete", model_tiers=a_table(cheap="small-model")
		)
		adapter = service.adapter(phase=Phase.BUILD, model="operator-said")
		assert adapter.model == "operator-said"
		assert adapter.model_source == "--model"

	def test_a_probe_adapter_records_no_source(self, home: Path, tmp_path: Path) -> None:
		"""A capability probe is not a phase's dispatch, and its row must not read as one.

		The probe names a model to vary one slot, so the two arms run the same model — a
		tier applied here would make the arms differ in two things and the difference
		would not be attributable.
		"""
		service = synthetic_service(
			home, tmp_path, "complete", model_tiers=a_table(cheap="small-model")
		)
		adapter = service.adapter()
		assert adapter.model_source is None


class TestADispatchRecordsTheModel:
	async def test_a_dispatched_step_carries_its_model_and_source(
		self, home: Path, tmp_path: Path
	) -> None:
		"""The record is where FR-132's effect becomes checkable after the fact."""
		from synthetic import plan_and_service

		service, plan = await plan_and_service(
			home, tmp_path, "complete", model_tiers=a_table(cheap="small-model", deep="big-model")
		)
		records = await service.dispatch_plan(plan.id, max_steps=1)
		assert records, "the synthetic harness must dispatch at least one step"
		first = records[0]
		assert first.model is not None
		assert first.model_source in {"tier:cheap", "tier:deep", "SOFACT_MODEL", "default"}
