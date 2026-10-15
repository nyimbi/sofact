"""FR-019: the deployment boundary is measured, and the ceiling follows the measurement.

R2 names the defect this closes — "autonomy depends on isolation (FR-019) that is
asserted but never verified" — so the tests that matter here are the ones that show the
detector *discriminating*: reporting confinement when it holds and reporting none when it
does not. A detector that always answered ``enforced`` would pass a test that only
asserted a boundary was found, which is why the negative cases are the substance.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sofact.boundary import (
	ESCAPE_MARKER,
	INSIDE_MARKER,
	READ_MARKER,
	READ_REPORT,
	SEATBELT,
	detect_boundary,
	seatbelt_profile,
	wrap_argv,
)
from sofact.views import (
	TOPOLOGY_MODIFIER,
	AutonomyLevel,
	BoundaryMechanism,
	DeploymentBoundary,
	DeploymentTopology,
	topology_ceiling,
)


def _boundary(*, enforced: bool) -> DeploymentBoundary:
	"""A measured boundary with a real shape, so the arithmetic is tested not the probe."""
	return DeploymentBoundary(
		mechanism=BoundaryMechanism.SEATBELT if enforced else BoundaryMechanism.NONE,
		enforced=enforced,
		attempted="ran one child told to escape its directory",
		observed="measured for this test",
		probed_at=datetime.now(UTC),
	)


class TestTheBoundaryIsMeasured:
	"""FR-019's condition is a measurement, so these run a real child."""

	def test_the_detector_confines_a_child_and_reports_which_mechanism(self) -> None:
		"""On a host offering Seatbelt the probe must find it *enforcing*, not merely
		present. The two came apart on this very host — see the realpath test below — so
		"the tool exists" is not the claim being made."""

		async def measure() -> DeploymentBoundary:
			with tempfile.TemporaryDirectory() as home:
				workspace = Path(home) / "ws"
				workspace.mkdir()
				return await detect_boundary(workspace)

		if not Path(SEATBELT).exists():
			return  # The host offers no Seatbelt; the degradation path is tested below.
		measured = asyncio.run(measure())
		assert measured.enforced, measured.observed
		assert measured.mechanism is BoundaryMechanism.SEATBELT
		assert not measured.degraded

	def test_the_probe_leaves_no_marker_behind(self) -> None:
		"""A detector that wrote into the thing it measures would change what it observes
		and leave files in the module tree — and the *escape* marker it plants is exactly
		the artefact a later check might read as a real escape."""

		async def measure() -> tuple[Path, DeploymentBoundary]:
			with tempfile.TemporaryDirectory() as home:
				workspace = Path(home) / "ws"
				workspace.mkdir()
				return workspace, await detect_boundary(workspace)

		workspace, _ = asyncio.run(measure())
		assert not (workspace / INSIDE_MARKER).exists()
		assert not (workspace.parent / ESCAPE_MARKER).exists()

	def test_a_profile_naming_an_unresolved_path_does_not_confine(self) -> None:
		"""The measured trap, asserted rather than commented: ``/tmp`` is a symlink to
		``/private/tmp`` on darwin and the kernel matches the path it is handed. This is
		why :func:`seatbelt_profile` resolves, and the test states the failure mode so a
		future edit that drops the ``resolve()`` fails here rather than in production."""
		with tempfile.TemporaryDirectory() as home:
			real = Path(home) / "real"
			real.mkdir()
			link_parent = Path(tempfile.mkdtemp())
			link = link_parent / "linkws"
			os.symlink(real, link)
			profile = seatbelt_profile(link)
			assert str(real.resolve()) in profile, (
				"the profile must name the resolved path; naming the symlink leaves the "
				"confinement rule matching a path the kernel never sees"
			)

	def test_a_host_with_no_mechanism_reports_the_degraded_configuration(self) -> None:
		"""FR-019 calls same-host, same-filesystem execution *degraded*, and a degraded
		configuration must be reportable rather than indistinguishable from an unmeasured
		one. ``NONE`` is a finding; ``None`` is the absence of one."""

		async def measure() -> DeploymentBoundary:
			with tempfile.TemporaryDirectory() as home:
				workspace = Path(home) / "ws"
				workspace.mkdir()
				return await detect_boundary(workspace)

		measured = asyncio.run(measure())
		assert measured.attempted, "a degraded verdict must say what was attempted"
		assert measured.observed, "and what was observed"
		if not measured.enforced:
			assert measured.mechanism is BoundaryMechanism.NONE
			assert measured.degraded


class TestTheCeilingFollowsTheMeasurement:
	"""§5.4's modifier, now keyed to what was measured rather than what was declared."""

	def test_a_measured_boundary_restores_the_baseline_a_degraded_declaration_gave_up(
		self,
	) -> None:
		"""The whole of A2's arithmetic. T1 is the degraded declaration and lowers L4 to
		L3; a deployment *measured* to confine its children is not degraded, so charging
		it T1's penalty would be the same conflation R2 names, in the other direction."""
		assert topology_ceiling(AutonomyLevel.L4, DeploymentTopology.T1).name == "L3", (
			"the undeclared T1 case must be unchanged"
		)
		assert (
			topology_ceiling(
				AutonomyLevel.L4, DeploymentTopology.T1, boundary=_boundary(enforced=True)
			).name
			== "L4"
		)

	def test_no_boundary_measured_leaves_the_declared_modifier_alone(self) -> None:
		"""``None`` is "never measured" and must behave exactly as before, or every
		existing call site and fixture would change meaning."""
		assert (
			topology_ceiling(AutonomyLevel.L4, DeploymentTopology.T1).name
			== topology_ceiling(AutonomyLevel.L4, DeploymentTopology.T1, boundary=None).name
		)

	def test_a_boundary_that_did_not_hold_does_not_raise_the_ceiling(self) -> None:
		"""Measured-and-absent is the degraded case, and it must price as degraded. A
		detector that returned a boundary object for a mechanism that failed would
		otherwise hand out T2's ceiling for T1's isolation."""
		assert (
			topology_ceiling(
				AutonomyLevel.L4, DeploymentTopology.T1, boundary=_boundary(enforced=False)
			).name
			== "L3"
		)

	def test_no_boundary_can_raise_a_level_above_the_ladder(self) -> None:
		"""The guard :data:`HIGHEST_GRANTABLE` exists for, kept in force. A measured
		boundary's modifier is capped at 0 by §5.4's own table, so nothing here can lift a
		level past L4 — and the assertion still fires rather than silently capping."""
		raised = _boundary(enforced=True)
		assert raised.modifier == 0
		assert TOPOLOGY_MODIFIER[DeploymentTopology.T1] == -1
		for topology in DeploymentTopology:
			assert topology_ceiling(AutonomyLevel.L4, topology, boundary=raised).name == "L4", (
				f"{topology.value} must not exceed L4 with a measured boundary"
			)

	def test_the_declared_table_is_unchanged(self) -> None:
		"""§5.4's table is read back by another test and must not have been edited to make
		A2 work. The boundary is an *override* at the call site, not a change to the table."""
		assert TOPOLOGY_MODIFIER[DeploymentTopology.T1] == -1
		assert all(modifier <= 0 for modifier in TOPOLOGY_MODIFIER.values())

	def test_the_l0_clamp_still_holds_with_a_boundary(self) -> None:
		"""§5.4's modifier is one level and the ladder's floor is L0, so a module class at
		L1 computes L0-1 = -1 without the clamp. The boundary path must not lose it."""
		assert (
			topology_ceiling(
				AutonomyLevel.L1, DeploymentTopology.T1, boundary=_boundary(enforced=False)
			).name
			== "L0"
		)


class TestTheBoundaryWrapsEveryLaunch:
	"""The wrapper both process-launch points route through, so a control applied at one
	call site and not another cannot happen — the failure ``resolve_sensitivity`` had."""

	def test_a_measured_boundary_wraps_the_argv(self) -> None:
		with tempfile.TemporaryDirectory() as home:
			workspace = Path(home) / "ws"
			workspace.mkdir()
			wrapped = wrap_argv(("echo", "hi"), _boundary(enforced=True), workspace)
			assert wrapped[0] == SEATBELT
			assert wrapped[-2:] == ("echo", "hi"), "the command must survive the wrap"

	def test_a_degraded_boundary_leaves_the_argv_alone(self) -> None:
		with tempfile.TemporaryDirectory() as home:
			workspace = Path(home) / "ws"
			workspace.mkdir()
			argv = ("echo", "hi")
			assert wrap_argv(argv, _boundary(enforced=False), workspace) == argv
			assert wrap_argv(argv, None, workspace) == argv

	def test_the_wrapper_rebuilds_the_read_rules_the_probe_measured(self) -> None:
		"""The profile a dispatch runs under must be the profile the detector measured.

		Rebuilding a *weaker* one at enforcement time — writes confined, reads global —
		would leave the delivery reporting an FR-059 guarantee no session had, which is the
		same defect as reporting an unmeasured boundary as enforced. So the deny rules have
		to survive the round trip through ``deny_read``.
		"""
		with tempfile.TemporaryDirectory() as home:
			workspace = Path(home) / "ws"
			workspace.mkdir()
			secret = Path(home) / "holdout"
			secret.mkdir()
			measured = _boundary(enforced=True).model_copy(
				update={"deny_read": (str(secret.resolve()),)}
			)
			wrapped = wrap_argv(("echo", "hi"), measured, workspace)
			profile = wrapped[2]
			assert f'(deny file-read* (subpath "{secret.resolve()}"))' in profile, (
				"the enforcement profile dropped the read denies the measurement recorded"
			)


class TestTheReadHalfIsMeasuredToo:
	"""FR-059: the harness must reach neither the oracle corpus, the holdout, nor the
	credentials. FR-019 bounds writes and that is a different claim — a producer that can
	read the holdout has the answer whatever it can write, so a boundary credited on the
	write half alone would raise a ceiling against isolation the session did not have."""

	def test_a_subtree_the_child_could_read_is_not_credited(self) -> None:
		"""The negative case, and the one that makes the instrument an instrument.

		A subtree equal to the workspace is dropped from the profile — it would be
		re-allowed a line later — so a canary planted there *is* readable. A detector that
		reported confinement anyway would be asserting the rule it wrote rather than the
		behaviour it observed, which is exactly the trap the unresolved-path test above
		states for writes. The write half holds here; only the read half fails, so this
		also shows the two halves are separately decisive.
		"""

		async def measure() -> DeploymentBoundary:
			with tempfile.TemporaryDirectory() as home:
				workspace = Path(home) / "ws"
				workspace.mkdir()
				return await detect_boundary(workspace, deny_read=(workspace,))

		if not Path(SEATBELT).exists():
			return  # The host offers no Seatbelt; the degradation path is tested elsewhere.
		measured = asyncio.run(measure())
		assert not measured.enforced, measured.observed
		assert "read" in measured.observed
		assert measured.deny_read == (), "a canary the child read is not a denied subtree"

	def test_a_confined_child_reads_none_of_the_planted_canaries(self) -> None:
		"""The positive case: a subtree the profile really denies, with a canary in it that
		is really there. The canary is planted by the detector, so "denied" means a child
		was watched failing to open a file that exists — not that a rule was written."""

		async def measure() -> DeploymentBoundary:
			with tempfile.TemporaryDirectory() as home:
				workspace = Path(home) / "ws"
				workspace.mkdir()
				holdout = Path(home) / "holdout"
				holdout.mkdir()
				return await detect_boundary(workspace, deny_read=(holdout,))

		if not Path(SEATBELT).exists():
			return
		measured = asyncio.run(measure())
		assert measured.enforced, measured.observed
		assert len(measured.deny_read) == 1
		assert measured.deny_read[0].endswith("holdout"), (
			"the record names the denied subtree, not the canary inside it — enforcement "
			"rebuilds the profile from this and a file-level deny would leave the subtree "
			"readable"
		)

	def test_the_read_half_is_reported_unmeasured_when_no_subtree_is_named(self) -> None:
		"""Unmeasured is not open. A deployment that named no subtree has no finding about
		reads, and the record has to say so rather than implying the half held."""

		async def measure() -> DeploymentBoundary:
			with tempfile.TemporaryDirectory() as home:
				workspace = Path(home) / "ws"
				workspace.mkdir()
				return await detect_boundary(workspace)

		if not Path(SEATBELT).exists():
			return
		measured = asyncio.run(measure())
		assert measured.enforced, measured.observed
		assert measured.deny_read == ()
		assert "not measured" in measured.observed

	def test_the_read_probe_leaves_no_canary_behind(self) -> None:
		"""The canary is a file the detector writes into a subtree it does not own. Leaving
		one behind would be the detector polluting the holdout it just proved unreadable."""

		async def measure() -> tuple[Path, Path]:
			with tempfile.TemporaryDirectory() as home:
				workspace = Path(home) / "ws"
				workspace.mkdir()
				holdout = Path(home) / "holdout"
				holdout.mkdir()
				await detect_boundary(workspace, deny_read=(holdout,))
				return workspace, holdout

		if not Path(SEATBELT).exists():
			return
		workspace, holdout = asyncio.run(measure())
		assert not (holdout / READ_MARKER).exists()
		assert not (workspace / READ_REPORT).exists()

	def test_the_profile_denies_reads_after_the_allowance_and_before_the_workspace(
		self,
	) -> None:
		"""Seatbelt's rules are last-match-wins, so *where* the deny sits is the whole
		mechanism. Emitted before ``(allow file-read*)`` it would be overridden; emitted
		after the workspace re-allowance it would lock the session out of its own
		directory. This asserts the position rather than the presence."""

		with tempfile.TemporaryDirectory() as home:
			workspace = Path(home) / "ws"
			workspace.mkdir()
			secret = Path(home) / "holdout"
			secret.mkdir()
			profile = seatbelt_profile(workspace, deny_read=(secret,))
			allow_all = profile.index("(allow file-read*)")
			deny = profile.index(f'(deny file-read* (subpath "{secret.resolve()}"))')
			reallow = profile.rindex(f'(allow file-read* (subpath "{workspace.resolve()}"))')
			assert allow_all < deny < reallow, (
				"the deny must sit between the blanket allowance and the workspace "
				"re-allowance, or it either does nothing or locks the session out"
			)

	def test_a_denied_subtree_equal_to_the_workspace_is_not_emitted(self) -> None:
		"""It would be re-allowed a line later, so emitting it would put a rule in the
		profile that says the opposite of what it looks like it says."""

		with tempfile.TemporaryDirectory() as home:
			workspace = Path(home) / "ws"
			workspace.mkdir()
			profile = seatbelt_profile(workspace, deny_read=(workspace,))
			assert f'(deny file-read* (subpath "{workspace.resolve()}"))' not in profile


class TestADispatchOwnsTwoWritableDirectories:
	"""The defect the first version of this boundary had, pinned so it cannot come back.

	A dispatch is handed a workspace *and* a session store, and every harness writes its
	record into the second. A profile granting writes under the workspace alone denied
	``touch <session_dir>/record.jsonl`` with ``Operation not permitted``, and the run then
	reported "no session completed, so no oracle ran" for a session that was never
	permitted to write one — a boundary that broke the dispatch while looking like
	confinement. Measured 2026-10-14 on the real dispatch path, not inferred."""

	def test_the_session_store_is_granted_beside_the_workspace(self) -> None:
		with tempfile.TemporaryDirectory() as home:
			workspace = Path(home) / "ws"
			workspace.mkdir()
			sessions = Path(home) / "sessions"
			sessions.mkdir()
			profile = seatbelt_profile(workspace, writable=(sessions,))
			assert f'(allow file-write* (subpath "{sessions.resolve()}"))' in profile, (
				"the store a harness writes its record into must be writable, or every "
				"wrapped dispatch exits having produced no session"
			)
			assert f'(allow file-read* (subpath "{sessions.resolve()}"))' in profile, (
				"and readable, because a harness reads its own store back"
			)

	def test_a_confined_child_writes_its_record_and_is_still_denied_the_sibling(self) -> None:
		"""Both halves in one real child, because a grant that widened the profile would
		pass the first half alone.

		The store must be writable — that is the defect. The *sibling* directory must not
		be, or the grant would have turned the profile into a no-op and the detector would
		be reporting confinement it had given away. Run as one child so the two are facts
		about the same profile rather than about two profiles that might differ.
		"""

		if not Path(SEATBELT).exists():
			return
		with tempfile.TemporaryDirectory() as home:
			workspace = Path(home) / "ws"
			workspace.mkdir()
			sessions = Path(home) / "sessions"
			sessions.mkdir()
			sibling = Path(home) / "sibling"
			sibling.mkdir()
			profile = seatbelt_profile(workspace, writable=(sessions,))
			# `subprocess` rather than the module's own `_run`: a test that reached for
			# the private helper would be asserting against the same wrapper it is
			# checking, and the point here is what the *kernel* does with the profile.
			completed = subprocess.run(
				[
					SEATBELT,
					"-p",
					profile,
					"/bin/sh",
					"-c",
					f"touch {sessions / 'record.jsonl'} 2>/dev/null; "
					f"touch {sibling / 'stolen.txt'} 2>/dev/null; exit 0",
				],
				cwd=workspace,
				capture_output=True,
				check=False,
			)
			assert completed.returncode == 0, (
				f"the probe child must run, or neither marker means anything: "
				f"{completed.stderr.decode(errors='replace')}"
			)
			assert (sessions / "record.jsonl").exists(), (
				"a dispatch must be able to write its own session record"
			)
			assert not (sibling / "stolen.txt").exists(), (
				"the grant widened the profile: a sibling directory became writable"
			)

	def test_a_grant_containing_the_escape_target_is_refused(self) -> None:
		"""A grant containing the escape target would let the child write the escape marker
		legitimately, and the detector would read its own grant as a mechanism that failed
		to confine — reporting no boundary where one holds. The guard is an assert rather
		than a comment because the failure is silent and points the wrong way.

		Driven through ``detect_boundary`` rather than by importing ``_escape_target``: a
		test that reaches a private helper pins the helper's name, while this pins the
		property — a grant that would void the probe is refused at the public seam.
		"""

		async def measure() -> DeploymentBoundary:
			with tempfile.TemporaryDirectory() as home:
				workspace = Path(home) / "ws"
				workspace.mkdir()
				# The whole home is granted, so the escape target (the workspace's parent)
				# is inside a granted root.
				return await detect_boundary(workspace, writable=(Path(home),))

		with pytest.raises(AssertionError, match="inside a granted root"):
			asyncio.run(measure())

	def test_the_grant_survives_the_round_trip_through_the_record(self) -> None:
		"""``wrap_argv`` rebuilds the profile from the boundary record, so a rebuild that
		dropped the grant would run a dispatch under a *narrower* profile than the one
		measured — the mirror of the defect, and just as invisible."""

		with tempfile.TemporaryDirectory() as home:
			workspace = Path(home) / "ws"
			workspace.mkdir()
			sessions = Path(home) / "sessions"
			sessions.mkdir()
			measured = _boundary(enforced=True).model_copy(
				update={"writable": (str(sessions.resolve()),)}
			)
			wrapped = wrap_argv(("echo", "hi"), measured, workspace)
			assert f'(allow file-write* (subpath "{sessions.resolve()}"))' in wrapped[2], (
				"the enforcement profile dropped the store grant the measurement recorded"
			)
