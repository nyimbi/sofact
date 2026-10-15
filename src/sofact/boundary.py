"""The boundary as *applied*: the argv and environment a confined child runs under.

FR-019 requires isolation "enforced by the deployment boundary **where one exists**", and
the enforcement half of that requirement is this module. :func:`wrap_argv` is the one
wrapper both process-launch points route through — the dispatch (``harness.py``) and the
oracle command (``execution.py``) — so the control is applied at *every* launch rather than
at the one that was convenient. :func:`boundary_env` is its required pair: it points the
child's ``TMPDIR`` inside the workspace the profile permits rather than widening the
profile to admit the host's.

**Measuring a boundary and applying one are different jobs, and one of them opens a
socket.** The detector — :mod:`sofact.boundary_probe` — binds a loopback listener and runs
a child against it to find out whether a mechanism holds. That is a host measurement,
performed once per service. This module is the pure half: it takes an already-measured
:class:`~sofact.views.DeploymentBoundary` and returns strings, importing neither ``socket``
nor ``asyncio``. ``sofact.manufacture`` needs the strings and never the socket, and it
roots the ``oracle_authoring`` surface whose transitive import closure ADR-0064 measures to
prove that surface cannot reach a model. One module holding both jobs put ``socket`` inside
that closure the moment the egress probe was added. See ADR-0067.

**Profiles are built from the resolved path, and that is not a detail.** Measured on
darwin 2026-10-14: a profile denying writes under ``/tmp`` did not deny them, because
``/tmp`` is a symlink to ``/private/tmp`` and the kernel matches the path it is handed
rather than the one the operator typed. The same profile naming the realpath denied the
write. A profile that passed the unresolved path would report ``enforced`` for a mechanism
that confined nothing, which is the one answer this module must never give.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from .views import BoundaryMechanism, DeploymentBoundary

SEATBELT = "/usr/bin/sandbox-exec"
"""Absolute, because neither the detector nor the wrapper may be steered by a caller's ``PATH``.

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


CONTAINER_IMAGE_ENV = "SOFACT_BOUNDARY_IMAGE"
"""The image a dispatch is run inside, when a container is the boundary (FR-019).

Wrapping a *dispatch* in a container is not the same act as wrapping an oracle command:
the child is a harness binary, and it has to exist inside the image. So the image is
configuration rather than a constant — the factory cannot know which harness a deployment
runs — and its absence is why a container is not reported as an enforced boundary for
dispatch (see :func:`container_prefix`). Measuring the container and *applying* it are
one fact here on purpose: a boundary reported as enforced while dispatch ran unwrapped
would price the ceiling against isolation the session never had, which is R2 inverted.
"""


def container_prefix(workspace: Path) -> tuple[str, ...] | None:
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
		prefix = container_prefix(workspace)
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
