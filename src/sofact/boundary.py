"""What actually confines a child, measured rather than asserted (FR-019, FR-016-020).

FR-019 requires isolation "enforced by the deployment boundary **where one exists**",
and calls same-host, same-filesystem execution the *degraded* configuration that "must
**lower autonomy ceilings**". Every word of that is conditional, and the condition is a
measurement: does a boundary exist here, and does it hold? R2 names the failure of
skipping it — "autonomy depends on isolation (FR-019) that is asserted but never
verified" — and this module is the verification.

The instrument is one real child that writes inside the directory it was given and then
tries to write one level above it. That is :meth:`ConfiguredHarnessAdapter._probe_sandboxable`'s
shape (``harness.py``), reused rather than reinvented: a boundary that is only *claimed*
leaves the escape file, and a child that did no work at all leaves neither marker, which
is why the inside marker gates both verdicts. An escape that was never attempted cannot
be read as an escape that was prevented.

**Profiles are built from the resolved path, and that is not a detail.** Measured on
darwin 2026-10-14: a profile denying writes under ``/tmp`` did not deny them, because
``/tmp`` is a symlink to ``/private/tmp`` and the kernel matches the path it is handed
rather than the one the operator typed. The same profile naming the realpath denied the
write. A detector that passed the unresolved path would report ``enforced`` for a
mechanism that confined nothing, which is the one answer this module must never give.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .views import (
	BoundaryMechanism,
	DeploymentBoundary,
)

PROBE_TIMEOUT_SECONDS = 20.0
"""Long enough for a container to start on a cold host, short enough not to hang a build."""

INSIDE_MARKER = "inside-marker.txt"
ESCAPE_MARKER = "escape-marker.txt"
PROFILE_NAME = "sofact-boundary.sb"

SEATBELT = "/usr/bin/sandbox-exec"
"""Absolute, because the detector must not be steered by a caller's ``PATH``.

A boundary that a session can disable by editing its own environment is not a boundary,
and the session runs with the factory's environment (``_child_env``).
"""


def seatbelt_profile(
	workspace: Path,
	*,
	deny_read: Sequence[Path] = (),
	writable: Sequence[Path] = (),
) -> str:
	"""A Seatbelt profile that permits reads and execution everywhere and writes only here.

	Execution is global on purpose. A child needs the interpreter, its standard library
	and the dynamic loader, and a profile that denied them would fail to start rather than
	fail to escape — measuring nothing while looking like confinement. Writes are the thing
	FR-019 bounds: a session that can write into a sibling module's worktree or the
	operator's home is the blast radius the ceiling is priced against.

	``writable`` names directories the child may write *besides* the workspace, and a
	dispatch has exactly one: its session store. Measured 2026-10-14 — a profile granting
	writes under the workspace alone denies ``touch <session_dir>/record.jsonl`` with
	``Operation not permitted``, and every harness writes its record there, so the profile
	as it stood broke every wrapped dispatch rather than confining it. A boundary that
	breaks the session is a boundary an operator turns off within a day, and a boundary
	nobody runs is not a boundary.

	The grants are emitted *after* the denies, which is what makes the factory's layout
	expressible at all: the home is denied and the two directories inside it that a
	producer legitimately owns — its workspace and its session store — are carved back
	out. Seatbelt is last-match-wins, so emitting a grant before the deny that covers it
	would leave the session denied the directory the line appears to permit.

	``deny_read`` names subtrees the child must not *read*, and it is FR-059 rather than
	FR-019: "the harness must run inside the lane's sandbox with no access to the oracle
	corpus, holdout scenarios, or factory credentials". Writes alone do not bound that —
	a producer that can read the holdout has the answer whatever it can write — so a
	boundary that only confined writes would report isolation for a session that could
	read its own exam. Seatbelt's rules are last-match-wins, so these are emitted *after*
	the blanket read allowance and before the workspace re-allowance, which is what makes
	"deny the factory home, allow the workspace inside it" expressible.

	A subtree *containing* the workspace is therefore the normal case rather than an error:
	the factory's home holds the ledger and the holdout and the workspace sits inside it,
	and the trailing re-allowance is what carves the workspace back out. A denied subtree
	equal to the workspace itself is dropped instead — it would be re-allowed a line later,
	so emitting it would put a rule in the profile that says the opposite of what it looks
	like it says.

	``Path.resolve()`` is load-bearing; see the module docstring. Paths are embedded
	rather than interpolated from user text, and quotes are stripped, so a workspace whose
	name contains a quote cannot close the form early and inject a rule.

	``/dev/null`` is permitted explicitly, and it is not a convenience. Measured: with a
	bare ``(deny default)`` the shell failed to open ``/dev/null`` and reported
	``/bin/sh: /dev/null: Operation not permitted`` — so the probe child never ran its
	commands and the detector read that as "the mechanism did not confine", which is the
	wrong verdict for the right reason. A dispatch is launched with ``stdin=DEVNULL``
	(``harness.py``), so a profile without this line would break every wrapped session
	rather than confine it.
	"""
	resolved = workspace.resolve()
	granted: list[Path] = [resolved]
	for path in writable:
		candidate = path.resolve()
		if candidate not in granted:
			granted.append(candidate)
	# A denied subtree that is also granted is dropped rather than emitted: it would be
	# re-allowed a few lines later, so the rule would say the opposite of what it looks
	# like it says.
	denied = "".join(
		f'(deny file-read* (subpath "{str(path.resolve()).replace(chr(34), "")}"))\n'
		for path in deny_read
		if path.resolve() not in granted
	)
	# Both halves per granted root, and the read half is not optional: a harness reads its
	# own store back (pi resolves a model registry from its config directory, claude reads
	# the record it just wrote), so a write-only grant would leave the child able to write
	# a record it cannot then read.
	allowance = "".join(
		f'(allow file-write* (subpath "{str(root).replace(chr(34), "")}"))\n'
		f'(allow file-read* (subpath "{str(root).replace(chr(34), "")}"))\n'
		for root in granted
	)
	return (
		"(version 1)\n"
		"(deny default)\n"
		"(allow file-read*)\n" + denied + "(allow process-exec*)\n"
		"(allow process-fork)\n"
		"(allow sysctl-read)\n"
		'(allow file-write* (literal "/dev/null") (literal "/dev/stdout") '
		'(literal "/dev/stderr"))\n' + allowance
	)


def _seatbelt_argv(
	workspace: Path,
	script: str,
	*,
	deny_read: Sequence[Path] = (),
	writable: Sequence[Path] = (),
) -> tuple[str, ...]:
	"""``sandbox-exec`` running ``script`` under the profile for ``workspace``.

	``-p`` takes the profile as text, so no profile file is written into the workspace
	being measured — a detector that wrote its own input into the thing it is measuring
	would change what it observes, and would leave a file behind in the module tree.
	"""
	return (
		SEATBELT,
		"-p",
		seatbelt_profile(workspace, deny_read=deny_read, writable=writable),
		"/bin/sh",
		"-c",
		script,
	)


READ_MARKER = "sofact-read-probe.txt"
"""The file the detector plants in each subtree it means to deny (FR-059).

Planting a canary is what makes the read half a *measurement*. Asserting the rule was
written would report the profile's text rather than the kernel's behaviour, and on this
host the two came apart for writes — an unresolved subpath silently matched nothing — so
the same trap is assumed present for reads until a child has been watched failing to
open a file that is really there. Dot-free and factory-named, so a stray one left by a
crashed detector is attributable rather than mysterious.
"""

READ_REPORT = ".sofact-read-report.txt"
"""Where the confined child lists the canaries it *could* read. Inside the workspace.

Inside, because the child is allowed to write there and nowhere else, and because the
file's absence is then a readable signal: the detector can tell "the child read nothing"
from "the read probe never ran" by whether the report exists at all. Writing it to stdout
would fold it into the same pipe as the shell's own noise and lose that distinction.
"""


def _escape_target(workspace: Path, granted: Sequence[Path]) -> Path:
	"""A directory outside every granted root, to attempt the escape into.

	``workspace.parent`` is the target, and the assert is what keeps it a valid one. A
	grant that *contains* the escape target would let the child write the escape marker
	legitimately, and the detector would read its own grant as a mechanism that failed to
	confine — reporting no boundary where one holds. The factory's layout does not hit
	this: the workspace is ``<home>/workspace`` and the session store is
	``<home>/sessions``, so the escape target is ``<home>``, which neither grants.

	An *existing* directory is required, and that is not tidiness. ``touch`` into a path
	whose parent is absent fails ``ENOENT``, which the probe swallows exactly as it
	swallows ``EPERM`` — so a walk up to a directory that is not there would produce no
	escape marker and be credited as confinement the profile never demonstrated.
	"""
	escape = workspace.resolve().parent
	assert not any(root == escape or root in escape.parents for root in granted), (
		f"the escape target {escape} is inside a granted root, so the write probe would be void"
	)
	assert escape.is_dir(), (
		f"the escape target {escape} does not exist, so a failed touch proves nothing"
	)
	return escape


def _probe_script(
	workspace: Path,
	*,
	deny_read: Sequence[Path] = (),
	escape: Path | None = None,
) -> str:
	"""Write inside, try to write above, and try to read each denied canary.

	One child for both halves, because they are two facts about one confinement and a
	second launch would be a second measurement that could disagree with the first for
	reasons neither reports.

	Every branch exits 0. The instrument is the markers the child leaves, never its exit
	status: a *confined* child is supposed to fail these operations, so reading a non-zero
	exit as the verdict would make the profile working indistinguishable from the shell
	failing to start.
	"""
	resolved = workspace.resolve()
	target = resolved.parent if escape is None else escape
	lines = [
		f"touch {_quote(resolved / INSIDE_MARKER)} 2>/dev/null",
		f"touch {_quote(target / ESCAPE_MARKER)} 2>/dev/null",
	]
	if deny_read:
		report = resolved / READ_REPORT
		lines.append(f": > {_quote(report)} 2>/dev/null")
		for root in deny_read:
			canary = root.resolve() / READ_MARKER
			lines.append(
				f"if cat {_quote(canary)} >/dev/null 2>&1; then "
				f"printf '%s\\n' {_quote(canary)} >> {_quote(report)}; fi"
			)
	lines.append("exit 0")
	return "; ".join(lines)


def _quote(path: Path) -> str:
	"""Single-quote a path for ``/bin/sh``, so a space or a ``$`` cannot break the probe."""
	return "'" + str(path).replace("'", "'\\''") + "'"


async def _run(argv: tuple[str, ...], *, cwd: Path) -> tuple[int | None, str]:
	"""Run one child, returning its exit code and any stderr. Never raises on failure."""
	try:
		process = await asyncio.create_subprocess_exec(
			*argv,
			cwd=cwd,
			stdin=asyncio.subprocess.DEVNULL,
			stdout=asyncio.subprocess.DEVNULL,
			stderr=asyncio.subprocess.PIPE,
		)
	except OSError as exc:
		return None, str(exc)
	try:
		_, stderr = await asyncio.wait_for(process.communicate(), timeout=PROBE_TIMEOUT_SECONDS)
	except TimeoutError:
		process.kill()
		await process.wait()
		return None, "the probe child did not finish inside its cap"
	return process.returncode, stderr.decode("utf-8", errors="replace")


async def _measure(
	mechanism: BoundaryMechanism,
	argv: tuple[str, ...],
	workspace: Path,
	*,
	attempted: str,
	deny_read: Sequence[Path] = (),
	escape: Path | None = None,
	writable: Sequence[Path] = (),
) -> DeploymentBoundary:
	"""Run one mechanism's probe and read the markers it left.

	The write verdict is :meth:`_probe_sandboxable`'s, and it is two-sided for the same
	reason: ``enforced`` requires the inside marker to have appeared **and** the escape
	marker not to have. Without the first, a mechanism that failed to launch anything
	would report confinement it never tested.

	The read half (FR-059) is measured the same way — the child tries to open a canary
	that is really there, and the canary's path appears in the report only when the open
	succeeded. A requested subtree that turned out readable makes the whole boundary
	``enforced=False``, and that direction is deliberate: FR-019's ceiling exists to price
	what a producer can *do*, and a producer that can read the holdout has the answer
	whatever it can write. Crediting write confinement while the answer key stayed legible
	would raise the ceiling on the strength of half a property.

	Unmeasured is not failed. When no subtree was named there is nothing to read, the
	canaries are never planted, and the read half is recorded as not measured rather than
	as open — the same distinction ``None`` makes one level up.
	"""
	resolved = workspace.resolve()
	inside = resolved / INSIDE_MARKER
	escape_marker = (resolved.parent if escape is None else escape) / ESCAPE_MARKER
	report = resolved / READ_REPORT
	roots = [root.resolve() for root in deny_read]
	for path in (inside, escape_marker, report):
		path.unlink(missing_ok=True)
	planted: list[Path] = []
	for root in roots:
		canary = root / READ_MARKER
		try:
			canary.write_text(f"{canary}\n", encoding="utf-8")
		except OSError:
			# A canary that cannot be planted cannot be read either, so this subtree is
			# unmeasurable and is dropped rather than counted as denied. Crediting it would
			# be reporting a rule that was never tried.
			continue
		planted.append(root)

	code, stderr = await _run(argv, cwd=workspace)
	wrote_inside = inside.exists()
	wrote_outside = escape_marker.exists()
	readable: set[str] = (
		set(report.read_text(encoding="utf-8").split()) if report.exists() else set()
	)
	for path in (inside, escape_marker, report):
		path.unlink(missing_ok=True)
	for root in planted:
		(root / READ_MARKER).unlink(missing_ok=True)

	# The roots that were denied, not the canaries: enforcement rebuilds a profile from
	# this tuple, and a profile denying one planted file would leave the subtree it sits in
	# readable — a weaker rule than the one measured, reported as though it were the same.
	denied = tuple(str(root) for root in planted if str(root / READ_MARKER) not in readable)
	read_failed = bool(readable)

	if wrote_outside:
		enforced = False
		observed = (
			f"the child wrote {ESCAPE_MARKER} outside the directory it was given, so "
			f"{mechanism.value} did not confine it. A session that wandered would write "
			"into the checkout, the home directory, or a sibling module's worktree (FR-141)"
		)
	elif read_failed:
		enforced = False
		observed = (
			f"the child was confined to {resolved} for writes but read "
			+ ", ".join(sorted(readable))
			+ " — the oracle corpus, the holdout scenarios or the credentials, which FR-059 "
			"requires it not to reach. A producer that can read the holdout has the answer "
			"whatever it can write, so the boundary is not credited"
		)
	elif wrote_inside:
		enforced = True
		observed = (
			f"the child did the work inside its directory, left no {ESCAPE_MARKER} above "
			f"it, and read none of the {len(planted)} planted canaries outside it, so "
			f"{mechanism.value} confines it for writes and for reads. The escape was "
			"attempted rather than omitted, because the probe asked for it"
			if planted
			else (
				f"the child did the work inside its directory and left no {ESCAPE_MARKER} "
				f"above it, so {mechanism.value} confines it for writes. The read half "
				"(FR-059) was **not measured** here — no subtree outside the workspace was "
				"named to deny — which is not the same as measured and open"
			)
		)
	else:
		enforced = False
		observed = (
			f"neither {INSIDE_MARKER} nor {ESCAPE_MARKER} appeared (exit {code}), so the "
			f"child did no work and {mechanism.value}'s confinement was never witnessed"
			+ (f"; stderr said {stderr.strip()[:200]!r}" if stderr.strip() else "")
		)
	return DeploymentBoundary(
		mechanism=mechanism,
		enforced=enforced,
		attempted=attempted,
		observed=observed,
		probed_at=datetime.now(UTC),
		writes_confined=wrote_inside and not wrote_outside,
		deny_read=denied,
		writable=tuple(str(root.resolve()) for root in writable),
	)


CONTAINER_IMAGE_ENV = "SOFACT_BOUNDARY_IMAGE"
"""The image a dispatch is run inside, when a container is the boundary (FR-019).

Wrapping a *dispatch* in a container is not the same act as wrapping an oracle command:
the child is a harness binary, and it has to exist inside the image. So the image is
configuration rather than a constant — the factory cannot know which harness a deployment
runs — and its absence is why a container is not reported as an enforced boundary for
dispatch (see :func:`_container_prefix`). Measuring the container and *applying* it are
one fact here on purpose: a boundary reported as enforced while dispatch ran unwrapped
would price the ceiling against isolation the session never had, which is R2 inverted.
"""


def _container_prefix(workspace: Path) -> tuple[str, ...] | None:
	"""The container invocation that confines a dispatch to ``workspace``, or ``None``.

	``--network=none`` is the egress half of FR-019 and is not optional here: a container
	that shares the host network has bounded the filesystem and left the network open,
	which FR-152 already warns is not the same boundary.

	``None`` in two cases, and both are honest rather than defensive: no container runtime
	on ``PATH``, or a runtime with no image configured to run a dispatch in. The second is
	the case this host is in — ``podman`` is installed and its VM is not started, and even
	started there is no image carrying a harness. Reporting the container as an enforced
	boundary while a dispatch ran unwrapped would be exactly the conflation R2 names.
	"""
	image = os.environ.get(CONTAINER_IMAGE_ENV, "").strip()
	if not image:
		return None
	runtime = shutil.which("podman") or shutil.which("docker")
	if runtime is None:
		return None
	return (
		runtime,
		"run",
		"--rm",
		"--network=none",
		f"--volume={workspace.resolve()}:/workspace",
		"--workdir=/workspace",
		image,
	)


def _container_argv(workspace: Path, script: str) -> tuple[str, ...] | None:
	"""The prefix plus a shell running ``script``, or ``None`` when there is no prefix."""
	prefix = _container_prefix(workspace)
	if prefix is None:
		return None
	return (*prefix, "/bin/sh", "-c", script)


async def detect_boundary(
	workspace: Path,
	*,
	only: Sequence[BoundaryMechanism] | None = None,
	deny_read: Sequence[Path] = (),
	writable: Sequence[Path] = (),
) -> DeploymentBoundary:
	"""Measure what confines a child in ``workspace``, cheapest-falsifying-first (FR-019).

	Ordered so the fastest refutation comes first and the most expensive mechanism last:
	Seatbelt is a local process wrapper, a container runtime is a VM boot. The first
	mechanism that *enforces* is returned; when none does, the returned boundary names
	``NONE`` with the attempts that were made, so a degraded deployment reports the
	measurement rather than the absence of one.

	``only`` restricts which mechanisms are attempted, and it is a *restriction* rather
	than a declaration: naming a mechanism still requires the probe to confirm it holds,
	so no value of ``only`` can raise a ceiling without a measurement behind it. An empty
	sequence measures nothing and returns the degraded verdict, which is how a deployment
	that has decided not to probe says so — it can only lower a ceiling, never lift one.

	``deny_read`` names the subtrees FR-059 requires a producer not to reach — the oracle
	corpus, the holdout scenarios, the credentials — and each is canaried and attempted.
	The caller supplies them because only the caller knows where its factory keeps them;
	the default measures the write half alone and says so, rather than inferring the read
	half from a path it guessed. The two halves are separable in the result for that
	reason: a boundary that confined writes and was never asked about reads is a weaker
	claim than one that was, and the record has to be able to tell them apart.

	``workspace`` must exist and be a directory: the probe writes into it, and a probe
	against a path that is not there would report a mechanism's failure to launch as a
	boundary that did not hold.
	"""
	assert workspace.is_dir(), (
		f"cannot measure a boundary in a workspace that is not one: {workspace}"
	)
	attempt = only if only is not None else tuple(BoundaryMechanism)
	roots = tuple(root.resolve() for root in deny_read)
	grants = tuple(root.resolve() for root in writable)
	escape = _escape_target(workspace, (*grants, workspace.resolve()))
	script = _probe_script(workspace, deny_read=roots, escape=escape)
	refused: DeploymentBoundary | None = None

	if BoundaryMechanism.SEATBELT in attempt and Path(SEATBELT).exists():
		measured = await _measure(
			BoundaryMechanism.SEATBELT,
			_seatbelt_argv(workspace, script, deny_read=roots, writable=grants),
			workspace,
			attempted=(
				f"ran one child under a Seatbelt profile permitting writes only under "
				f"{workspace.resolve()}"
				+ (f" and {', '.join(str(root) for root in grants)}" if grants else "")
				+ f", told to write {INSIDE_MARKER} there and then {ESCAPE_MARKER} in "
				f"{escape}"
				+ (
					f", and to open a planted canary in each of {len(roots)} "
					"subtrees it must not read (FR-059)"
					if roots
					else ""
				)
			),
			deny_read=roots,
			escape=escape,
			writable=grants,
		)
		if measured.enforced:
			return measured
		# Kept when writes were confined and reads were not. Falling through to the generic
		# verdict below would replace a specific finding — "this mechanism bounded the blast
		# radius and left the answer key legible" — with one that says only that nothing
		# confined the child, which is both less true and less useful: the remedies differ,
		# and a reader cannot choose between them from the vaguer report.
		if measured.writes_confined:
			refused = measured

	container = (
		# The read half is not attempted in a container, and the reason is mechanical
		# rather than a gap: the canaries are planted on the host and the container mounts
		# only the workspace, so a canary path inside it resolves to nothing and the child
		# would be reported as denied for having been asked to read a file that is not
		# there. That is the instrument measuring its own mount, not the boundary. The
		# container's read confinement is its filesystem, which is a different fact from
		# Seatbelt's rule and is not measured by this probe.
		_container_argv(workspace, _probe_script(workspace))
		if BoundaryMechanism.CONTAINER in attempt
		else None
	)
	if container is not None:
		measured = await _measure(
			BoundaryMechanism.CONTAINER,
			container,
			workspace,
			attempted=(
				"ran one child in a container with no network and only the workspace "
				f"mounted, told to write {INSIDE_MARKER} there and then {ESCAPE_MARKER} "
				"one directory above (the FR-059 read half is not attempted here — the "
				"container mounts only the workspace, so a host canary would be absent "
				"rather than denied)"
			),
		)
		if measured.enforced:
			return measured

	if not attempt:
		attempted = (
			"attempted no mechanism, because this deployment restricted the probe to none "
			"— so nothing is claimed about confinement, and §5.4's degraded modifier applies"
		)
	else:
		tried = "tried every boundary this host offers"
		if BoundaryMechanism.SEATBELT in attempt and Path(SEATBELT).exists():
			tried += f" ({SEATBELT})"
		if container is not None:
			tried += ", and a container runtime"
		attempted = tried + ", by running a child told to escape its directory"

	if refused is not None:
		return refused

	return DeploymentBoundary(
		mechanism=BoundaryMechanism.NONE,
		enforced=False,
		attempted=attempted,
		observed=(
			"no mechanism confined the child, so this is §5.4's degraded configuration: "
			"shared filesystem, producer and evaluator on one host. FR-019 prices this as "
			"a lower autonomy ceiling rather than refusing the build"
		),
		probed_at=datetime.now(UTC),
	)


def wrap_argv(
	argv: tuple[str, ...],
	boundary: DeploymentBoundary | None,
	workspace: Path,
) -> tuple[str, ...]:
	"""``argv`` run inside the measured boundary, or unchanged when none held (FR-019).

	The one wrapper both process-launch points route through, so the boundary is applied
	at *every* launch rather than at the one that was convenient — a control applied at
	some call sites is the failure ``resolve_sensitivity`` had, correct at 19 of 27 paths.

	``None`` and a non-enforcing boundary both return ``argv`` unchanged. They are
	different *facts* — never measured, versus measured and absent — but not different
	*commands*, and conflating them here would put the distinction where it cannot be
	read. The distinction lives on the record, which is where a reader looks for it.

	Callers must pair this with :func:`boundary_env`. The profile permits writes only
	under ``workspace``, so a child left with the host's ``TMPDIR`` would be denied its
	own scratch directory — measured, not assumed: ``tempfile.mkdtemp()`` outside the
	workspace raises ``PermissionError`` under this profile while the same call inside it
	succeeds. A wrapper that confined a session and broke it would be turned off within a
	day, and a boundary nobody runs is not a boundary.

	The profile rebuilt here carries the boundary's ``deny_read`` subtrees, so the rules a
	dispatch runs under are the rules the probe measured. Rebuilding a *weaker* profile at
	enforcement time — writes confined, reads global — would leave the delivery reporting
	an FR-059 guarantee no session had, which is the same defect as reporting an unmeasured
	boundary as enforced.
	"""
	if boundary is None or not boundary.enforced:
		return argv
	if boundary.mechanism is BoundaryMechanism.SEATBELT:
		deny_read = tuple(Path(entry) for entry in boundary.deny_read)
		writable = tuple(Path(entry) for entry in boundary.writable)
		return (
			SEATBELT,
			"-p",
			seatbelt_profile(workspace, deny_read=deny_read, writable=writable),
			*argv,
		)
	if boundary.mechanism is BoundaryMechanism.CONTAINER:
		prefix = _container_prefix(workspace)
		if prefix is None:
			# The runtime was on PATH when the boundary was measured and is not now. The
			# command runs unwrapped rather than not at all: a build that refused because
			# a tool disappeared would be a refusal for a reason its operator cannot act
			# on, and the record already carries what was measured.
			return argv
		# The child's argv is already absolute, so it needs no shell; `--entrypoint`
		# would collide with the image's own. A bare command after the prefix runs
		# directly, which is what the probe's `/bin/sh -c` also relies on.
		return (*prefix, *argv)
	return argv


TEMP_DIRNAME = ".sofact-tmp"
"""The child's scratch directory, created inside the confined workspace (FR-019).

Dot-prefixed and factory-named so it cannot collide with a producer's own ``tmp/``, and
excluded from :func:`~sofact.execution.digest_tree` and from the branch seal: a directory
whose contents change every run would otherwise move the FR-006 cache key on every step
and be committed onto the module's branch.
"""


def boundary_env(
	boundary: DeploymentBoundary | None,
	workspace: Path,
) -> dict[str, str]:
	"""Environment the confined child needs, or ``{}`` when nothing confines it (FR-019).

	``TMPDIR`` is pointed *inside* the workspace rather than the profile being widened to
	admit the host's temp directory, and the direction matters. Widening the profile would
	hand every confined session the same shared ``/var/folders/.../T`` — so two sessions
	could still read and clobber each other's scratch, and the boundary would have given
	up the property it was measured to have. Redirecting the variable keeps the profile at
	"writes under this workspace and nowhere else" while leaving a child its own scratch
	inside it.

	This also keeps the *probe* valid. The detector's workspace is itself often under the
	host's temp directory, so a profile that admitted ``TMPDIR`` wholesale would admit the
	probe's own escape target and report a boundary that does not hold — the instrument
	would be broken by the convenience meant to make it usable.

	A container needs none of this: its filesystem is the image's, and ``TMPDIR`` is
	already the container's own.

	The scratch directory is created here rather than assumed. ``tempfile`` filters its
	candidate list to directories that exist, so a ``TMPDIR`` naming one that does not
	would be skipped and the child would silently fall back to the host's — the exact
	denial this function exists to prevent, reintroduced by a missing ``mkdir``.
	"""
	if boundary is None or not boundary.enforced:
		return {}
	if boundary.mechanism is BoundaryMechanism.SEATBELT:
		scratch = workspace.resolve() / TEMP_DIRNAME
		scratch.mkdir(parents=True, exist_ok=True)
		return {"TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)}
	return {}
