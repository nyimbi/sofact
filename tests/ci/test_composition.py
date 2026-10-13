"""FR-154-156 — the frozen plugin composition, and the deletion test that admits into it.

§8.7 answers "is SoFact a `dsh` plugin?" with no, and the reason is structural rather than
aesthetic: the plugin set is **mutable at runtime by the agent** ([S22]), so an in-process
verifier is reachable by the party it verifies. FR-154 freezes the composition, FR-155
admits a plugin into it only if SoFact's verdict is unchanged without it, and FR-156
prefers a setting to a dependency.

The corpus is the spec's own. §8.7 works the deletion test over eight measured rows (two of
which name several plugins each) and reaches four distinct verdicts, and the first class
below transcribes that table and asserts the type accepts it — which is the only check that
the four verdicts are the right four. The remaining classes test what makes the table
*enforceable* rather than merely written down: the freeze is derived from the argv rather
than declared, an admission that does not mean what it says is refused, and the vacuous case
— a composition that considered nothing — reports FR-155 as open instead of printing a clean
filter.

The one thing this module does not test is the deletion test's *answer*. Whether removing
`dsh-budget` changes SoFact's budget verdict is a question about a running system, and a
test that answered it from a table would be asserting the thing it claims to check. What is
under test is that the answer is written down in a form a machine can check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sofact.cli import app
from sofact.composition import composition_for, load_composition, verify_composition
from sofact.harness import CLAUDE_SPEC, DSH_SPEC, PI_RESEARCH_SPEC, PI_SPEC, SPECS, HarnessSpec
from sofact.views import (
	COMPOSITION_REQUIREMENTS,
	VERDICT_SURFACES,
	PluginAdmission,
	PluginComposition,
	PluginVerdict,
	content_hash,
	now,
)

RUNNER = CliRunner()

ALL_HELD = frozenset(VERDICT_SURFACES)
"""Every surface held — the state an admissible plugin is in and a refused one is not."""

# §8.7's worked table, transcribed. Each row is (plugin, verdict, surfaces held without it,
# the requirement's own reason, and the superseding setting where there is one).
#
# The *Test* column names the decision the plugin takes over; `surfaces_held` is that
# decision removed from FR-155's five, and each row's comment names the correspondence so a
# reader can check the mapping against the spec rather than take it. Where the spec's row
# names several plugins (`dsh-completion-guard`, `beforedone`, `stalegreen`,
# `dsh-evidence-gate`, `reliability-governor`; `dsh-plugin-agent-budget`, `dsh-budget`) one
# representative stands for the row, because the row is the finding and the names are its
# instances.
ECOSYSTEM_AUDIT: tuple[tuple[str, PluginVerdict, frozenset[str], str, str | None], ...] = (
	(
		"dsh-completion-guard",
		PluginVerdict.REFUSED,
		# "deleting it changes SoFact's completion verdict" — completion.
		ALL_HELD - {"completion"},
		"fails deletion: deleting it changes SoFact's completion verdict (FR-155)",
		None,
	),
	(
		"dsh-plugin-agent-budget",
		PluginVerdict.REFUSED,
		# "budget is SoFact's authority" — budget.
		ALL_HELD - {"budget"},
		"fails deletion: budget is SoFact's authority (FR-140)",
		None,
	),
	(
		"dsh-plugin-kit",
		PluginVerdict.REFUSED,
		# "it *is* the gate" — a gate decides whether work is accepted, so completion.
		ALL_HELD - {"completion"},
		"fails deletion: it *is* the gate, and gates are the human's (FR-140)",
		None,
	),
	(
		"dsh-research-container",
		PluginVerdict.REFUSED,
		# "an in-process guard cannot be the boundary of the process it guards" — egress.
		ALL_HELD - {"egress"},
		"fails deletion: an in-process guard cannot be the boundary of the process it "
		"guards (FR-019/FR-152, D9)",
		None,
	),
	(
		"LongHorizon-Harness",
		PluginVerdict.REFUSED,
		# "it is an outer loop, i.e. §8's subject" — it would own the loop that decides
		# whether the work is done, which is completion.
		ALL_HELD - {"completion"},
		"fails deletion: it is an outer loop, which is §8's subject rather than a plugin",
		None,
	),
	(
		"dsh-git-worktree",
		PluginVerdict.BUILT_HERE,
		# "Passes deletion" — the row the verdict set was missing a word for.
		ALL_HELD,
		"passes deletion, and FR-141 is no longer deferred: the integration line, the "
		"per-wave merge order and the conflict record are the part a wrapper cannot see "
		"(ADR-0033)",
		None,
	),
	(
		"dsh-telemetry-redactor",
		PluginVerdict.SUPERSEDED,
		# "Passes deletion, but is superseded by config" — FR-156's own case.
		ALL_HELD,
		"passes deletion, but disabling the exporter removes the path instead of guarding "
		"it (FR-156)",
		"disable the session-telemetry-otel exporter",
	),
	(
		"upstream-radar",
		PluginVerdict.ADMISSIBLE,
		# "Passes deletion" and the only row §8.7 admits.
		ALL_HELD,
		"passes deletion, and its existence is evidence R28 is a real, already-productised problem",
		None,
	),
)


def admission(row: tuple[str, PluginVerdict, frozenset[str], str, str | None]) -> PluginAdmission:
	"""One §8.7 row as an admission, with the licence an installed plugin must carry."""
	plugin, verdict, held, rationale, superseded_by = row
	return PluginAdmission(
		plugin=plugin,
		verdict=verdict,
		surfaces_held=held,
		superseded_by=superseded_by,
		licence="MIT" if verdict is PluginVerdict.ADMISSIBLE else None,
		rationale=rationale,
	)


def composition(
	*,
	spec: HarnessSpec = PI_SPEC,
	pins: tuple[tuple[str, str], ...] = (),
	admissions: tuple[PluginAdmission, ...] = (),
	argv_frozen: bool | None = None,
) -> PluginComposition:
	"""A composition with the freeze read off its spec, or overridden to vary one field."""
	return PluginComposition(
		id="01920000-0000-7000-8000-000000000001",
		harness=spec.name,
		created_at=now(),
		pins=pins,
		admissions=admissions,
		argv_frozen=spec.composition_frozen if argv_frozen is None else argv_frozen,
	)


def write(tmp_path: Path, body: object) -> Path:
	path = tmp_path / "composition.json"
	path.write_text(json.dumps(body), encoding="utf-8")
	return path


class TestTheDeletionTestOnTheMeasuredEcosystem:
	"""§8.7's table, which is the only check that the four verdicts are the right four.

	A type with four verdicts is underdetermined by its own docstring: nothing in
	``PluginVerdict`` says that a budget plugin is *refused* rather than *superseded*, and
	nothing says that a worktree wrapper that passes the deletion test is not admitted. The
	spec's worked table is the oracle for that, and transcribing it here means a later
	change to the verdict set has to disagree with §8.7 out loud.
	"""

	def test_every_row_is_constructible(self) -> None:
		admissions = [admission(row) for row in ECOSYSTEM_AUDIT]
		assert len(admissions) == 8, (
			"§8.7 works eight rows; the two rows that name several plugins each are one "
			"finding, so a ninth row would be a second instance of one already here"
		)

	def test_the_four_verdicts_are_all_exercised(self) -> None:
		"""A table that used one verdict would pass every other test in this class."""
		seen = {row[1] for row in ECOSYSTEM_AUDIT}
		assert seen == set(PluginVerdict), (
			"§8.7 reaches four distinct verdicts and the corpus must exercise all four, or "
			"the transcription proves nothing about the ones it skipped"
		)

	def test_only_the_plugin_that_passes_deletion_is_admitted(self) -> None:
		admitted = [row[0] for row in ECOSYSTEM_AUDIT if row[1] is PluginVerdict.ADMISSIBLE]
		assert admitted == ["upstream-radar"], (
			"§8.7 admits exactly one measured plugin, and it is the one whose deletion "
			"changes nothing"
		)

	def test_a_refused_row_names_the_surface_the_plugin_took_over(self) -> None:
		"""The refused rows are the ones with a missing surface, not merely a verdict."""
		for row in ECOSYSTEM_AUDIT:
			plugin, verdict, held, _, _ = row
			if verdict is PluginVerdict.REFUSED:
				assert held != ALL_HELD, f"{plugin} is refused with every surface held"

	def test_the_whole_table_is_one_composition(self) -> None:
		"""All eight rows in one freeze: a refusal is recorded beside the admission."""
		admissions = tuple(admission(row) for row in ECOSYSTEM_AUDIT)
		pins = (("upstream-radar", "sha256:9f2c"),)
		built = composition(pins=pins, admissions=admissions)

		assert built.admitted == ("upstream-radar",)
		assert built.frozen and built.minimal
		assert len(built.refused) == 5
		assert len(built.superseded) == 1
		assert len(built.built_here) == 1
		assert built.discharged == COMPOSITION_REQUIREMENTS
		assert built.not_implemented == ()


class TestTheFreezeIsDerivedFromTheArgv:
	"""FR-154's freeze has two halves and only one of them is a list.

	A composition is frozen when the argv refuses to auto-load installed plugins, or when
	the plugins are enumerated and pinned. Deriving the first from
	:attr:`HarnessSpec.argv` rather than declaring it is what stops a spec asserting a
	freeze the command line does not enforce — and the project's recurring defect is exactly
	a declaration that drifts from the thing it describes.
	"""

	def test_pi_freezes_by_argv(self) -> None:
		assert PI_SPEC.composition_frozen
		assert "--no-extensions" in PI_SPEC.argv, (
			"the property reads this flag; if the argv dropped it the property must go false"
		)
		assert composition_for(PI_SPEC).frozen

	def test_a_spec_that_drops_the_flag_is_not_frozen(self) -> None:
		"""`pi-research` drops it because the research loop *is* an installed extension.

		The same declaration computes differently against a different argv, which is the
		whole reason the field is a flag list and not a boolean.
		"""
		assert PI_RESEARCH_SPEC.freezing_flags == PI_SPEC.freezing_flags
		assert "--no-extensions" not in PI_RESEARCH_SPEC.argv
		assert not PI_RESEARCH_SPEC.composition_frozen
		assert not composition_for(PI_RESEARCH_SPEC).frozen

	def test_dsh_is_not_frozen_and_that_is_the_finding(self) -> None:
		"""§8.7's hazard, in one assertion: the composition is mutable at runtime."""
		assert not DSH_SPEC.composition_frozen
		empty = composition_for(DSH_SPEC)
		assert not empty.frozen
		assert empty.discharged == ("FR-156",), (
			"an unfrozen harness leaves FR-154 open even with nothing installed"
		)
		assert "FR-154" in empty.not_implemented

	def test_a_declaration_cannot_assert_its_own_freeze(self, tmp_path: Path) -> None:
		"""`argv_frozen` is refused as a field, so a file cannot claim what it does not do."""
		path = write(
			tmp_path,
			{"compositions": {"claude": {"argv_frozen": True, "pins": []}}},
		)
		with pytest.raises(ValueError, match="unknown field"):
			load_composition(path, SPECS)

	def test_pinning_freezes_a_harness_whose_argv_does_not(self) -> None:
		"""The other half of the freeze, and it is sufficient on its own."""
		pinned = composition(spec=DSH_SPEC, pins=(("upstream-radar", "sha256:9f2c"),))
		assert not pinned.argv_frozen
		assert pinned.frozen, "a pinned composition is frozen even without a flag"
		assert "FR-154" not in pinned.not_implemented

	def test_the_hash_moves_when_the_freeze_half_moves(self) -> None:
		"""Two builds can pin the same plugins and differ in whether the argv also froze.

		The same harness and the same pins, so the flag is the only thing that varies — a
		hash over the pins alone would call these two compositions the same, which is the
		drift FR-154's "hash-verified" exists to catch.
		"""
		pins = (("upstream-radar", "sha256:9f2c"),)
		flag_frozen = composition(pins=pins, argv_frozen=True)
		not_frozen = composition(pins=pins, argv_frozen=False)
		assert flag_frozen.harness == not_frozen.harness
		assert flag_frozen.pins == not_frozen.pins
		assert flag_frozen.pinned_content != not_frozen.pinned_content


class TestAnAdmissionThatDoesNotMeanWhatItSays:
	"""The four refusals, which are the API being hard to get wrong.

	Each is a row that *reads* as a finding and is not one. They are the failure modes the
	project keeps finding in its own gates: a verdict that does not follow from the set
	beside it, and a set that answers a question the requirement did not ask.
	"""

	def test_an_admissible_plugin_missing_a_surface_is_refused(self) -> None:
		with pytest.raises(ValueError, match="does not reach the same verdict"):
			PluginAdmission(
				plugin="dsh-completion-guard",
				verdict=PluginVerdict.ADMISSIBLE,
				surfaces_held=ALL_HELD - {"completion"},
				licence="MIT",
				rationale="looks like it saves work",
			)

	def test_a_refused_plugin_holding_every_surface_is_refused(self) -> None:
		with pytest.raises(ValueError, match="refusal with no defect behind it"):
			PluginAdmission(
				plugin="some-plugin",
				verdict=PluginVerdict.REFUSED,
				surfaces_held=ALL_HELD,
				rationale="we did not like it",
			)

	def test_a_superseded_plugin_that_names_no_setting_is_refused(self) -> None:
		with pytest.raises(ValueError, match="indistinguishable from a plugin nobody looked at"):
			PluginAdmission(
				plugin="dsh-telemetry-redactor",
				verdict=PluginVerdict.SUPERSEDED,
				surfaces_held=ALL_HELD,
				rationale="config is better",
			)

	def test_an_admitted_plugin_with_no_licence_is_refused(self) -> None:
		"""R28's third failure mode, checked where it can still be acted on."""
		with pytest.raises(ValueError, match="no licence recorded"):
			PluginAdmission(
				plugin="upstream-radar",
				verdict=PluginVerdict.ADMISSIBLE,
				surfaces_held=ALL_HELD,
				rationale="passes deletion",
			)

	def test_a_surface_outside_the_requirement_is_refused(self) -> None:
		"""FR-155 names five surfaces; a sixth would answer a question it does not ask."""
		with pytest.raises(ValueError, match="unknown verdict surface"):
			PluginAdmission(
				plugin="some-plugin",
				verdict=PluginVerdict.REFUSED,
				surfaces_held=frozenset({"completion", "latency"}),
				rationale="invented a sixth surface",
			)

	def test_four_of_five_surfaces_is_not_full_coverage(self) -> None:
		"""The subset rule, stated as the case it protects against.

		A check that admitted a plugin holding four of FR-155's five surfaces would be
		satisfied by naming all but the one the plugin actually took over.
		"""
		four = frozenset(sorted(VERDICT_SURFACES)[:4])
		assert four != ALL_HELD
		with pytest.raises(ValueError, match="does not reach the same verdict"):
			PluginAdmission(
				plugin="almost",
				verdict=PluginVerdict.ADMISSIBLE,
				surfaces_held=four,
				licence="MIT",
				rationale="four of five",
			)


class TestTheCompositionRefusesTwoStates:
	"""FR-154's "must never be the operator's own profile", and the two incoherent builds."""

	def test_the_operators_own_profile_is_refused(self) -> None:
		with pytest.raises(ValueError, match="must never be the operator's own profile"):
			PluginComposition(
				id="01920000-0000-7000-8000-000000000002",
				harness="dsh",
				created_at=now(),
				operator_profile=True,
			)

	def test_an_admitted_plugin_with_no_pin_is_refused(self) -> None:
		with pytest.raises(ValueError, match="carry no pin"):
			composition(admissions=(admission(ECOSYSTEM_AUDIT[7]),))

	def test_a_refused_plugin_installed_anyway_is_refused(self) -> None:
		"""The row and the pin have to name the same plugin, or the check never fires."""
		plugin = ECOSYSTEM_AUDIT[1][0]
		with pytest.raises(ValueError, match="installed anyway"):
			composition(
				pins=((plugin, "sha256:aaa"),),
				admissions=(admission(ECOSYSTEM_AUDIT[1]),),
			)

	def test_the_same_plugin_pinned_twice_is_refused(self) -> None:
		with pytest.raises(ValueError, match="one pin per name"):
			composition(pins=(("a", "sha256:1"), ("a", "sha256:2")))

	def test_minimal_is_about_refusals_not_about_count(self) -> None:
		"""A composition with many admitted plugins is still minimal; a leaky one is not."""
		pins = (("a", "sha256:1"), ("b", "sha256:2"))
		many = composition(
			pins=pins,
			admissions=tuple(
				PluginAdmission(
					plugin=name,
					verdict=PluginVerdict.ADMISSIBLE,
					surfaces_held=ALL_HELD,
					licence="MIT",
					rationale="passes deletion",
				)
				for name in ("a", "b")
			),
		)
		assert many.minimal, "two admitted plugins is not the same as a non-minimal one"


class TestTheVacuousComposition:
	"""A composition that considered nothing has applied the deletion test to nothing.

	The rule ``EscapeReport`` and ``OracleAuditReport`` keep: the absence of a measurement
	is not a measurement. FR-156 is the floor an empty composition always carries — config is
	not a dependency, and zero plugins is its strongest form — and FR-154 rides along only
	when the argv actually freezes. The two are independent, so the tests below separate
	them: a harness can be frozen with nothing to admit, and it can be unfrozen with nothing
	to admit either.
	"""

	def test_an_empty_composition_leaves_the_deletion_test_open(self) -> None:
		"""`pi` with nothing declared: frozen by its argv, and nothing considered.

		The freeze half is carried — ``--no-extensions`` is on the command line — and the
		deletion test is not, because there was nothing to apply it to. That is the vacuous
		pass stated precisely: a composition can carry FR-154 and leave FR-155 open.
		"""
		empty = composition_for(PI_SPEC)
		assert empty.admissions == ()
		assert empty.frozen
		assert empty.discharged == ("FR-154", "FR-156")
		assert empty.not_implemented == ("FR-155",)

	def test_an_unfrozen_empty_composition_leaves_the_freeze_open_too(self) -> None:
		"""`dsh` with nothing declared: not frozen, and nothing considered. Two gaps."""
		empty = composition_for(DSH_SPEC)
		assert set(empty.not_implemented) == set(COMPOSITION_REQUIREMENTS) - {"FR-156"}

	def test_the_cli_exits_non_zero_on_an_unfrozen_harness(self, tmp_path: Path) -> None:
		result = RUNNER.invoke(
			app, ["composition", "--home", str(tmp_path / "state"), "--harness", "dsh"]
		)
		assert result.exit_code == 1, result.output
		assert "NOT frozen" in result.output
		assert "FR-154" in result.output

	def test_the_cli_reports_the_open_rows_and_exits_non_zero(self, tmp_path: Path) -> None:
		"""`pi` is frozen and considered no plugin, so FR-155 is the only open row."""
		result = RUNNER.invoke(
			app, ["composition", "--home", str(tmp_path / "state"), "--harness", "pi"]
		)
		assert result.exit_code == 1, result.output
		assert "frozen" in result.output
		assert "FR-155" in result.output
		assert "FR-154" not in result.output.split("not implemented")[-1], (
			"the freeze is carried, and only the deletion test is open"
		)


class TestTheLoader:
	"""FR-156 reaches the declaration itself: a composition is a file, not a code edit."""

	def test_the_audit_loads_through_the_real_loader(self, tmp_path: Path) -> None:
		path = write(
			tmp_path,
			{
				"compositions": {
					"pi": {
						"pins": [["upstream-radar", "sha256:9f2c"]],
						"admissions": [
							{
								"plugin": row[0],
								"verdict": row[1].value,
								"surfaces_held": sorted(row[2]),
								"superseded_by": row[4],
								"licence": ("MIT" if row[1] is PluginVerdict.ADMISSIBLE else None),
								"rationale": row[3],
							}
							for row in ECOSYSTEM_AUDIT
						],
					}
				}
			},
		)
		loaded = load_composition(path, SPECS)["pi"]
		assert loaded.frozen, "the freeze is derived from PI_SPEC, not declared in the file"
		assert loaded.admitted == ("upstream-radar",)
		assert len(loaded.refused) == 5

	def test_a_bare_object_is_accepted_like_the_other_loaders(self, tmp_path: Path) -> None:
		path = write(tmp_path, {"pi": {"pins": [], "admissions": []}})
		assert set(load_composition(path, SPECS)) == {"pi"}

	def test_an_unregistered_harness_is_refused(self, tmp_path: Path) -> None:
		"""The freeze cannot be derived for a harness this deployment does not run."""
		path = write(tmp_path, {"nonexistent": {"pins": [], "admissions": []}})
		with pytest.raises(ValueError, match="not a harness this deployment registers"):
			load_composition(path, SPECS)

	def test_an_admission_with_no_rationale_is_refused(self, tmp_path: Path) -> None:
		"""A verdict with no reason attached is re-litigated at the next plugin."""
		path = write(
			tmp_path,
			{"pi": {"admissions": [{"plugin": "x", "verdict": "refused"}]}},
		)
		with pytest.raises(ValueError, match="states no rationale"):
			load_composition(path, SPECS)

	def test_a_missing_surfaces_list_is_refused_rather_than_defaulted(self, tmp_path: Path) -> None:
		"""Defaulting to "all held" would make every forgotten field admissible."""
		path = write(
			tmp_path,
			{"pi": {"admissions": [{"plugin": "x", "verdict": "admissible", "rationale": "r"}]}},
		)
		with pytest.raises(ValueError, match="must be an array of FR-155's surface names"):
			load_composition(path, SPECS)

	def test_an_empty_file_is_refused(self, tmp_path: Path) -> None:
		path = write(tmp_path, {"compositions": {}})
		with pytest.raises(ValueError, match="no harnesses"):
			load_composition(path, SPECS)


class TestTheFreezeIsVerifiable:
	"""FR-154's word is **hash-verified**, and a pin nobody re-checks is a name with a digest.

	Nothing here reads the filesystem: what is installed is a fact about a machine, and
	the check is a pure function of what it is handed.
	"""

	def test_a_matching_set_reports_nothing(self) -> None:
		built = composition(pins=(("upstream-radar", "sha256:9f2c"),))
		assert verify_composition(built, pins={"upstream-radar": "sha256:9f2c"}) == ()

	def test_a_moved_digest_is_reported(self) -> None:
		built = composition(pins=(("upstream-radar", "sha256:9f2c"),))
		assert verify_composition(built, pins={"upstream-radar": "sha256:beef"}) == (
			"upstream-radar",
		)

	def test_an_uninstalled_member_is_a_change_too(self) -> None:
		"""A build pinned to a hash it can no longer reproduce is what the freeze detects."""
		built = composition(pins=(("upstream-radar", "sha256:9f2c"),))
		assert verify_composition(built, pins={}) == ("upstream-radar",)

	def test_the_cli_reports_drift_and_exits_non_zero(self, tmp_path: Path) -> None:
		home = tmp_path / "state"
		path = write(
			tmp_path,
			{"compositions": {"pi": {"pins": [["upstream-radar", "sha256:9f2c"]]}}},
		)
		result = RUNNER.invoke(
			app,
			[
				"composition",
				"--home",
				str(home),
				"--harness",
				"pi",
				"--verify",
				"upstream-radar=sha256:beef",
			],
			env={"SOFACT_COMPOSITION": str(path)},
		)
		assert result.exit_code == 1, result.output
		assert "does NOT hold" in result.output
		assert "upstream-radar" in result.output

	def test_a_malformed_verify_pair_is_refused_not_skipped(self, tmp_path: Path) -> None:
		"""A pair that dropped out of the comparison would leave its plugin unverified."""
		result = RUNNER.invoke(
			app,
			["composition", "--home", str(tmp_path / "state"), "--verify", "nonsense"],
		)
		assert result.exit_code == 1, result.output
		assert "NAME=DIGEST" in result.output


class TestTheSessionRecordsItsComposition:
	"""FR-154's last sentence: "the observed composition hash is recorded with the session".

	A freeze nobody can tie to a run is a policy statement rather than evidence, so the
	dispatch path has to carry the hash onto the record.
	"""

	def test_the_adapter_carries_the_hash_onto_every_record(self, tmp_path: Path) -> None:
		"""The adapter is the one place the hash is bound, so a record cannot disagree."""
		from sofact.harness import ConfiguredHarnessAdapter

		digest = composition_for(PI_SPEC).pinned_content
		adapter = ConfiguredHarnessAdapter(
			PI_SPEC,
			workspace=tmp_path,
			session_dir=tmp_path,
			model="m",
			composition_hash=digest,
		)
		assert adapter.composition_hash == digest
		assert adapter.variant(workspace=tmp_path / "other").composition_hash == digest, (
			"a variant must not silently drop the freeze it inherited"
		)

	def test_the_service_hash_is_the_composition_it_reports(self, tmp_path: Path) -> None:
		"""One source: the digest a session records and the one the verb prints agree."""
		from sofact.service import FactoryService

		service = FactoryService(home=tmp_path / "state", llm=None)
		assert service.composition_hash("pi") == service.composition("pi").pinned_content
		assert service.composition("pi").frozen

	def test_the_hash_is_reproducible_from_the_composition_alone(self) -> None:
		"""A reader recomputes rather than trusting a copy — the ledger's own rule."""
		first = composition_for(PI_SPEC)
		second = composition_for(PI_SPEC)
		assert first.id != second.id, "two compositions are two rows"
		assert first.pinned_content == second.pinned_content, (
			"and the hash covers what was frozen, not when it was frozen"
		)

	def test_an_admission_change_moves_the_hash(self) -> None:
		"""The reasoning is part of the freeze: re-classifying a plugin changes the boundary."""
		before = composition(pins=(("upstream-radar", "sha256:9f2c"),))
		after = composition(
			pins=(("upstream-radar", "sha256:9f2c"),),
			admissions=(admission(ECOSYSTEM_AUDIT[7]),),
		)
		assert before.pinned_content != after.pinned_content

	def test_the_hash_covers_the_verdict_not_only_the_plugin_names(self) -> None:
		"""Two compositions pinning the same plugin with different verdicts are different.

		`upstream-radar` is the plugin §8.7 admits and `dsh-git-worktree` the one it builds
		instead; the same digest pinned under either reading is the case a hash over names
		alone would call identical, and the boundary it describes is not the same boundary.
		"""
		pins = (("upstream-radar", "sha256:1"),)
		admitted = PluginAdmission(
			plugin="upstream-radar",
			verdict=PluginVerdict.ADMISSIBLE,
			surfaces_held=ALL_HELD,
			licence="MIT",
			rationale="passes deletion, and its existence is evidence R28 is real",
		)
		built = PluginAdmission(
			plugin="upstream-radar",
			verdict=PluginVerdict.BUILT_HERE,
			surfaces_held=ALL_HELD,
			rationale="re-classified after a re-measurement: SoFact grew the capability",
		)
		assert (
			composition(pins=pins, admissions=(admitted,)).pinned_content
			!= composition(pins=pins, admissions=(built,)).pinned_content
		)

	def test_the_hash_is_the_documented_content_hash(self) -> None:
		"""The digest is the product's own canonical hash, not a second convention."""
		built = composition_for(CLAUDE_SPEC)
		assert built.pinned_content == content_hash(
			{
				"harness": built.harness,
				"argv_frozen": built.argv_frozen,
				"pins": [],
				"admissions": [],
			}
		)


class TestTheConfigurationSeam:
	"""FR-156: the composition is configuration, and the seam is the environment variable."""

	def test_the_service_reads_a_declared_composition(self, tmp_path: Path) -> None:
		from sofact.service import FactoryService

		path = write(
			tmp_path,
			{"compositions": {"pi": {"pins": [["upstream-radar", "sha256:9f2c"]]}}},
		)
		declared = load_composition(path, SPECS)
		service = FactoryService(home=tmp_path / "state", llm=None, compositions=declared)
		assert service.composition("pi").admitted == ()
		assert service.composition("pi").pins == (("upstream-radar", "sha256:9f2c"),)

	def test_an_undeclared_harness_falls_back_to_its_spec(self, tmp_path: Path) -> None:
		"""`None` is "this deployment declared none", not "no composition exists"."""
		from sofact.service import FactoryService

		service = FactoryService(home=tmp_path / "state", llm=None, compositions={})
		assert service.composition("pi").frozen
		assert service.composition("dsh").frozen is False


def test_the_requirement_set_is_the_three_the_spec_names() -> None:
	"""FR-154, FR-155 and FR-156 are one mechanism; the constant is what says so."""
	assert COMPOSITION_REQUIREMENTS == ("FR-154", "FR-155", "FR-156")
	assert len(VERDICT_SURFACES) == 5, "FR-155 names exactly five verdict surfaces"


def test_a_composition_round_trips_through_json() -> None:
	"""The ledger stores JSON, so the type has to survive it unchanged."""
	built = composition(
		pins=(("upstream-radar", "sha256:9f2c"),),
		admissions=(admission(ECOSYSTEM_AUDIT[7]),),
	)
	again = PluginComposition.model_validate(built.model_dump(mode="json"))
	assert again.pinned_content == built.pinned_content
	assert again.admitted == ("upstream-radar",)
	assert again.admissions[0].surfaces_held == ALL_HELD, (
		"a frozenset survives the JSON round trip as the same set, not as a list"
	)


def test_the_runner_is_wired() -> None:
	"""A CLI test that never ran the app proves nothing; this one asserts it is reachable."""
	result = RUNNER.invoke(app, ["composition", "--help"])
	assert result.exit_code == 0, result.output
	assert "--verify" in result.output
