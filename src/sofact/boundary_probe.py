"""The boundary as *measured*: one real child, watched, against a listener we own.

R2 names the defect this closes — "autonomy depends on isolation (FR-019) that is
asserted but never verified" — and this module is the verification. FR-019 calls
same-host, same-filesystem execution the *degraded* configuration that "must **lower
autonomy ceilings**", so every word of the requirement is conditional on a measurement:
does a boundary exist here, and does it hold?

The instrument is one real child that writes inside the directory it was given and then
tries to write one level above it. That is :meth:`ConfiguredHarnessAdapter._probe_sandboxable`'s
shape (``harness.py``), reused rather than reinvented: a boundary that is only *claimed*
leaves the escape file, and a child that did no work at all leaves neither marker, which
is why the inside marker gates both verdicts. An escape that was never attempted cannot
be read as an escape that was prevented.

**The egress half is a second launch against a loopback listener this process owns**, and
that is why this module imports ``socket`` while ``boundary.py`` does not. A listener bound
here answers deterministically on a host with no network, so "denied" and "nothing was
routable" cannot be confused; a public address would need the internet to run at all, would
need DNS that the profile also governs, and would send a packet to a third party every time
a factory measured itself.

**The socket is the reason this is a module rather than a section of ``boundary.py``.** The
detector is a host measurement; applying a boundary is a pure string transformation. They
were one module until the egress probe was added, and that put ``socket`` inside the
transitive import closure of the ``oracle_authoring`` surface — which ``sofact.manufacture``
roots, and which ADR-0064 measures precisely so that a surface cannot reach a model. The
closure instrument reported the new edge, which is the instrument working. See ADR-0067.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .boundary import SEATBELT, container_prefix, seatbelt_profile
from .views import BoundaryMechanism, DeploymentBoundary, ProbeOutcome

PROBE_TIMEOUT_SECONDS = 20.0
"""Long enough for a container to start on a cold host, short enough not to hang a build."""


INSIDE_MARKER = "inside-marker.txt"
ESCAPE_MARKER = "escape-marker.txt"


EGRESS_HOST = "127.0.0.1"
"""The loopback address the egress probe connects to (FR-019, FR-152).

Loopback rather than a public address, and that is the whole design of the probe: a
listener this process owns answers deterministically on a host with no network, so
"denied" and "nothing was routable" cannot be confused. The connect is a real syscall
against a real listening socket, which is what makes the denial a measurement.
"""


EGRESS_TIMEOUT_SECONDS = 3.0
"""Short, because a permitted connect to a loopback listener returns immediately.

A connect that has to *time out* means the packet went somewhere that did not answer,
which is not the same as a refusal — and with a listener bound here that case cannot
arise, so a timeout is reported as not measured rather than as confinement.
"""


EGRESS_ALLOWED = "CONNECTED"
EGRESS_DENIED = "DENIED"
"""The two words the egress probe prints, read from stdout rather than an exit status."""


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


def egress_probe(*, port: int | None = None) -> tuple[str, socket.socket | None]:
	"""A loopback listener and the Python source that tries to connect to it (FR-019, FR-152).

	**The egress half is measured against a listener this process owns**, which is what
	makes the probe independent of the host's network, its DNS, and whether anything is
	routable. An earlier draft connected to a public address and that was rejected for
	three separate reasons, each of which would have been a defect: it needs the internet
	to run at all, so an offline host reports "no egress" for a boundary that may not
	hold; it needs DNS, which the profile also governs, so a name-resolution failure and a
	denied connect are indistinguishable in the observation; and it *sends a packet to a
	third party* every time a factory measures itself, which is an egress from the thing
	measuring egress.

	A listener on ``127.0.0.1`` is none of those. Measured on this host 2026-10-14: a bare
	``socket.create_connection(('127.0.0.1', <port>))`` succeeds, and the same call under
	:func:`seatbelt_profile`'s output raises ``PermissionError: [Errno 1] Operation not
	permitted`` — the profile's ``(deny default)`` denies ``network*``, which is also the
	mechanism by which the write half works.

	The source prints one word, and the detector reads it from a file rather than from an
	exit status: every branch exits 0 for the same reason :func:`_probe_script`'s do — a
	confined child is supposed to fail the operation, so an exit code would make a working
	profile indistinguishable from a shell that never started. ``OSError`` is caught rather
	than ``PermissionError`` alone, because the kernel's refusal surfaces as ``EACCES``,
	``EPERM`` or a reset depending on the mechanism, and all three are the same fact.

	The listener is returned open, so the caller can close it in a ``finally``. Leaving it
	to the garbage collector would leak a bound port per measurement on a long-lived
	service, and a probe that quietly consumes a resource eventually changes what it
	measures.

	``None`` as the listener means the port could not be bound, and the caller reads that
	as *not measured* rather than as a boundary that held.
	"""
	if port is None:
		with socket.socket() as placeholder:
			placeholder.bind((EGRESS_HOST, 0))
			port = int(placeholder.getsockname()[1])
	listener: socket.socket | None = None
	try:
		listener = socket.socket()
		listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		listener.bind((EGRESS_HOST, port))
		listener.listen(1)
	except OSError:
		if listener is not None:
			listener.close()
		return "", None
	# Double quotes throughout, because the whole source is single-quoted for the shell
	# and a quote inside it would close the shell's quoting early.
	source = (
		"import socket\n"
		"try:\n"
		f'    socket.create_connection(("{EGRESS_HOST}", {port}), {EGRESS_TIMEOUT_SECONDS})\n'
		"except OSError:\n"
		f'    print("{EGRESS_DENIED}")\n'
		"else:\n"
		f'    print("{EGRESS_ALLOWED}")\n'
	)
	return source, listener


def _python_argv(source: str) -> tuple[str, ...]:
	"""``sys.executable`` running ``source``, so the probe needs no network tool.

	``nc``, ``curl`` and ``wget`` are each present on some hosts and absent on others, and
	a probe that silently does nothing when its tool is missing is the fail-open shape this
	module exists to avoid. The interpreter running the detector is guaranteed to exist by
	the fact that the detector is running, and it is inside the profile's blanket
	``process-exec*`` allowance. It is passed as an absolute path for the reason
	:data:`SEATBELT` is: a child that resolved ``python3`` through ``PATH`` could be
	steered by the environment the session runs with.
	"""
	return (sys.executable, "-c", source)


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


async def _measure_egress(
	mechanism: BoundaryMechanism,
	workspace: Path,
	*,
	deny_read: Sequence[Path] = (),
	writable: Sequence[Path] = (),
	unwrap: bool = False,
) -> tuple[ProbeOutcome, str]:
	"""Whether ``mechanism`` confines network egress, and what the child said (FR-019).

	A *second* launch rather than a branch in the probe script, and the reason is the
	profile's construction: Seatbelt reads its rules last-match-wins, so an
	``(allow network*)`` inserted for this half would be a rule the enforcement profile
	does not carry. Measuring under a profile the dispatch will never run is measuring
	the instrument rather than the boundary. The same profile is rebuilt here — the same
	``deny_read`` subtrees and the same writable grants — so the two launches differ in
	exactly one thing, which is the script they run.

	The listening socket lives in *this* process, which is outside the child's boundary by
	construction. That is what makes the probe decisive: the port is bound and accepting,
	so a child that is refused was refused by its confinement rather than by an absent
	service, and a child that connects did so over a path the boundary permitted.

	``unwrap`` runs the child *outside* the mechanism, and it exists for one purpose: to
	make the ``ABSENT`` branch reachable against a real child rather than only through a
	hand-built record. A canary that stubbed the fold to ``enforced = True`` was **not
	caught**, because no test drove this function to an open verdict at all — the negative
	case was tested only by ``model_copy`` on a finished record, which exercises the
	*renderer* and not the detector. With this flag the control is a genuine measurement:
	the same source, the same listener, no profile, and the fold must then refuse to
	credit the boundary.
	"""
	source, listener = egress_probe()
	if listener is None:
		return (
			ProbeOutcome.INCONCLUSIVE,
			"no loopback port could be bound in the measuring process, so the egress half "
			"was not measured — which is not the same as measured and open (FR-019)",
		)
	try:
		if unwrap:
			argv: tuple[str, ...] = _python_argv(source)
		elif mechanism is BoundaryMechanism.SEATBELT:
			argv = (
				SEATBELT,
				"-p",
				seatbelt_profile(workspace, deny_read=deny_read, writable=writable),
				*_python_argv(source),
			)
		else:
			prefix = container_prefix(workspace)
			if prefix is None:
				return (
					ProbeOutcome.INCONCLUSIVE,
					"the container runtime or its image was unavailable at probe time, so "
					"the egress half was not measured",
				)
			argv = (*prefix, *_python_argv(source))
		# stdout, unlike `_run`: the verdict here *is* a word the child printed, because
		# both branches are a normal completion and the exit status is 0 either way.
		try:
			process = await asyncio.create_subprocess_exec(
				*argv,
				cwd=workspace,
				stdin=asyncio.subprocess.DEVNULL,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
			)
		except OSError as exc:
			return ProbeOutcome.INCONCLUSIVE, f"the egress probe child did not launch: {exc}"
		try:
			stdout, _ = await asyncio.wait_for(process.communicate(), timeout=PROBE_TIMEOUT_SECONDS)
		except TimeoutError:
			process.kill()
			await process.wait()
			return (
				ProbeOutcome.INCONCLUSIVE,
				"the egress probe child did not finish inside its cap, so nothing is "
				"claimed about egress",
			)
		said = stdout.decode("utf-8", errors="replace").strip()
	finally:
		listener.close()

	if EGRESS_DENIED in said:
		return (
			ProbeOutcome.CONFIRMED,
			f"a child under {mechanism.value} was refused a TCP connect to a listener "
			f"this process had bound on {EGRESS_HOST}, so egress is denied rather than "
			"merely unconfigured (FR-019, FR-152)",
		)
	if EGRESS_ALLOWED in said:
		return (
			ProbeOutcome.ABSENT,
			f"a child under {mechanism.value} opened a TCP connection to a listener this "
			f"process had bound on {EGRESS_HOST}, so network egress is **open**. FR-152 "
			"warns that `--offline` is not an egress boundary, and this is the measurement "
			"that says so for this deployment",
		)
	return (
		ProbeOutcome.INCONCLUSIVE,
		f"the egress probe child printed {said[:200]!r} rather than one of its two "
		"verdicts, so the half was not measured",
	)


async def _measure(
	mechanism: BoundaryMechanism,
	argv: tuple[str, ...],
	workspace: Path,
	*,
	attempted: str,
	deny_read: Sequence[Path] = (),
	escape: Path | None = None,
	writable: Sequence[Path] = (),
	egress_unwrapped: bool = False,
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

	# The egress half is measured for every mechanism that got this far, including the
	# ones that failed the filesystem half, because the two are separate findings about
	# one deployment and a report that dropped the second would say less than the probe
	# knows. It is a second launch; see `_measure_egress` for why it cannot be a branch.
	egress, egress_observed = await _measure_egress(
		mechanism, workspace, deny_read=deny_read, writable=writable, unwrap=egress_unwrapped
	)

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
		# The filesystem half held. Egress is folded in only when it was *measured*, and
		# the direction matters: an unmeasured half must not silently join the credit, or
		# a deployment whose probe could not run would report the same boundary as one
		# whose probe watched a connection refused. `INCONCLUSIVE` leaves `enforced` true
		# and records the gap, which is the honest shape — the write half genuinely holds
		# and the network half is genuinely unknown.
		enforced = egress is not ProbeOutcome.ABSENT
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
		if egress is ProbeOutcome.ABSENT:
			observed += ". It is **not credited** as a boundary for egress: " + egress_observed
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
		egress=egress,
		egress_observed=egress_observed,
	)


def _container_argv(workspace: Path, script: str) -> tuple[str, ...] | None:
	"""The prefix plus a shell running ``script``, or ``None`` when there is no prefix."""
	prefix = container_prefix(workspace)
	if prefix is None:
		return None
	return (*prefix, "/bin/sh", "-c", script)


async def detect_boundary(
	workspace: Path,
	*,
	only: Sequence[BoundaryMechanism] | None = None,
	deny_read: Sequence[Path] = (),
	writable: Sequence[Path] = (),
	egress_unwrapped: bool = False,
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

	``egress_unwrapped`` runs the *egress* child outside the mechanism while leaving the
	filesystem probe wrapped, which is the only way to observe the ``ABSENT`` branch
	against a real process. It exists because a canary that blinded the fold went
	uncaught: the negative case had been tested by mutating a finished record, which
	exercises the renderer rather than the detector. A test-only switch on a *detector* is
	a liability — it is a way to make the instrument lie — so it is documented as the
	control it is and it can only ever make the egress half report *less* confinement,
	never more.
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
			egress_unwrapped=egress_unwrapped,
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
