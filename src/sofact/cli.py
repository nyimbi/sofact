"""Command-line surface.

A presentation adapter and nothing more: it prints what the service decided and
holds no policy of its own. The interactive path is the product — ``sofact`` with no
arguments starts or resumes the interrogation.

The loop is synchronous and drives the async service with ``asyncio.run`` per
interaction rather than per conversation. An interactive prompt is a blocking read
that spends essentially all of its wall time waiting for a human, so a single
long-lived event loop would buy nothing and would complicate Ctrl-C.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path

import typer
from pydantic import ValidationError

from sofact import __version__
from sofact._uuid7 import uuid7str
from sofact.contract import ground_truth_debt, unexecutable_clauses
from sofact.elicitation import DIMENSIONS
from sofact.envelope import load_envelope, measure
from sofact.harness import HarnessBinaryMissing, HarnessSpec, load_specs
from sofact.llm import LlmClient
from sofact.service import (
	FactoryService,
	refuted_steps,
	resolve_tools,
)
from sofact.views import (
	PHASE_GATE,
	PHASE_SEQUENCE,
	TOPOLOGY_ISOLATION,
	TOPOLOGY_MODIFIER,
	UNPRODUCIBLE_KINDS,
	Assumption,
	ClaimKind,
	ClauseKind,
	Contract,
	Decomposition,
	DecompositionGate,
	DeliveryEnvelope,
	DeploymentTopology,
	DispatchRecord,
	EnvelopeDimension,
	GoalPlan,
	GoalStyle,
	HarnessProfile,
	IntegrityOutcome,
	Phase,
	PhaseStatus,
	ProbeOutcome,
	RepairOutcome,
	ResearchBudget,
	ResearchClassification,
	ResearchMode,
	ResearchRecord,
	ResearchVerdict,
	SourceLedger,
	Specification,
	SpecificationDraft,
	SpecificationGate,
	StepOutcome,
	SystemCriterion,
	SystemEntity,
	SystemModel,
	ValueHypothesis,
	VerdictOutcome,
	VerificationReport,
)

app = typer.Typer(
	add_completion=False,
	no_args_is_help=False,
	help="SoFact — turn an imagined product into a verifiable one.",
)

_HOME_OPTION = typer.Option(
	None, "--home", help="State directory (default: ./.sofact or $SOFACT_HOME)."
)

_ENTITY_OPTION = typer.Option(
	None,
	"--entity",
	help="A system-model entity, as NAME:CLAUSE-INDEX. Repeatable (FR-078).",
)
_ASSUMPTION_OPTION = typer.Option(
	None,
	"--assumption",
	help="An assumption, as STATEMENT | REFUTED-BY. Repeatable (FR-079).",
)
_VALUE_OPTION = typer.Option(
	None,
	"--value",
	help="The value hypothesis, as EFFECT | BENEFICIARY | REFUTING-INSTRUMENT (FR-085).",
)
_CRITERION_OPTION = typer.Option(
	None,
	"--criterion",
	help=(
		"A system-level criterion, as STATEMENT | CRITERION | CLAUSE-INDEX,CLAUSE-INDEX. "
		"Repeatable; at least two clauses (FR-116)."
	),
)

# Hoisted rather than written inline: ruff's B008 rejects a call in an argument
# default, and this matches the _HOME_OPTION pattern already in use.
_COMMAND_OPTION = typer.Option(
	None,
	"--command",
	help="Shell command to attach to every clause (single-obligation contracts only).",
)
_WORKSPACE_OPTION = typer.Option(None, "--workspace", help="Directory to run oracles in.")
_TIMEOUT_OPTION = typer.Option(300.0, "--timeout", help="Seconds per oracle.")
_BY_OPTION = typer.Option("producer", "--by", help="Who is declaring completion.")
_NOTE_OPTION = typer.Option(None, "--note", help="Optional free-text note.")
_VERSION_OPTION = typer.Option(False, "--version", help="Show the version and exit.", is_eager=True)
_HARNESS_OPTION = typer.Option(
	None, "--harness", help="Harness to drive: pi or dsh (default: $SOFACT_HARNESS, else pi)."
)
_MODEL_OPTION = typer.Option(None, "--model", help="Model id to hand the harness.")
_TOOLS_OPTION = typer.Option(
	None,
	"--tools",
	help="Comma-separated tool allowlist for the producer (default: $SOFACT_TOOLS, else the spec's set).",
)
_STYLE_OPTION = typer.Option(
	"labelled", "--style", help="Goal rendering: labelled (default) or objective."
)
_PROBE_TIMEOUT_OPTION = typer.Option(
	None, "--timeout", help="Seconds to allow the capability probe."
)
_QUICK_OPTION = typer.Option(
	False,
	"--quick",
	help="Skip the probe rows that need a second child. Faster, and less covered.",
)
_STEP_OPTION = typer.Option(
	None, "--step", help="Dispatch one step by ordinal or id instead of the whole plan."
)
_ALL_OPTION = typer.Option(False, "--all", help="Dispatch every wave, stopping at the first stall.")
_MAX_STEPS_OPTION = typer.Option(None, "--max-steps", help="Cap how many steps `--all` may start.")
_CONCURRENT_OPTION = typer.Option(
	False,
	"--concurrent",
	help=(
		"Run each wave's steps at once, each in a worktree of its own (FR-141). A wave "
		"that cannot be given one worktree per step runs sequentially."
	),
)
_FRESH_OPTION = typer.Option(
	False,
	"--fresh",
	help="Re-run the oracles even when the artefact and oracle set are unchanged (FR-006).",
)
_NOT_IMPLEMENTED_WHY = (
	"A green line above is not a claim about these. FR-112 needs a module to declare a "
	"machine-readable surface before its public-API diff has two sides; FR-115 and "
	"FR-116 need an approved specification that declares a system model and criteria "
	"spanning more than one clause, so a project that described no system reports them "
	"here rather than passing them."
)
_DELIVERY_ROOT_OPTION = typer.Option(
	None,
	"--root",
	help="Where to write the FR-117 artefacts the factory owes, and where it looks for all four.",
)
_SYSTEM_OPTION = typer.Option(
	None, "--system", help="What was delivered, named for the Mode M handover."
)
_ENTRY_POINT_OPTION = typer.Option(
	None, "--entry-point", help="Where a Mode M maintenance run begins (FR-121)."
)
_TOPOLOGY_OVERRIDE_OPTION = typer.Option(
	None,
	"--override-topology",
	help=(
		"Who accepts running a class FR-031 refuses at this topology. A name, not a flag: "
		"an unnamed override is the silent downgrade the requirement forbids."
	),
)
_REPORT_ID_ARGUMENT = typer.Argument(None, help="The delivery report to gate.")
_APPROVE_OPTION = typer.Option(None, "--approve", help="Pass the gate for this report, naming it.")
_GATE_BY_OPTION = typer.Option("operator", "--by", help="Who is passing the gate (FR-119).")
_GATE_NOTE_OPTION = typer.Option(None, "--note", help="Why, recorded with the decision.")
_MAX_ATTEMPTS_OPTION = typer.Option(
	2,
	"--max-attempts",
	help="How many times one refuted clause may be handed back before it is called exhausted.",
)
_TO_OPTION = typer.Option(
	...,
	"--to",
	help="The entry index to read the project as of, inclusive (FR-094).",
)
_CUT_BY_OPTION = typer.Option("operator", "--by", help="Who is rolling back.")
_REASON_OPTION = typer.Option(
	...,
	"--reason",
	help="Why. Recorded in the log, because an unexplained gap reads as a bug.",
)


def _service(home: Path | None) -> FactoryService:
	return FactoryService(
		home=home,
		llm=LlmClient(),
		specs=_configured_specs(),
		envelope=_configured_envelope(),
		topology=_configured_topology(),
	)


def _configured_envelope() -> DeliveryEnvelope | None:
	"""The §1.3 envelope this deployment configured, if it configured one (NFR-025).

	``None`` means "no envelope", which is not the same as "the defaults": NFR-025 makes
	the envelope configuration and calls it "a hypothesis under test", so a factory that
	applied §1.3's numbers without anyone choosing them would report actuals against a
	hypothesis its operator never adopted — and P3's FR-057 check would refuse
	over-scoped goals against numbers nobody set.
	"""
	configured = os.environ.get("SOFACT_ENVELOPE")
	if not configured:
		return None
	try:
		return load_envelope(Path(configured))
	except ValueError as exc:
		typer.secho(f"cannot read SOFACT_ENVELOPE: {exc}", fg="red")
		raise typer.Exit(code=1) from exc


def _configured_topology() -> DeploymentTopology | None:
	"""The §5.4 topology this deployment declared, if it declared one (FR-124, FR-042).

	``None`` means *no topology was declared*, which is not the same as "T1". Both report
	T1 — the degraded configuration, because a ceiling must not fail open — but FR-042
	requires the report to say which happened: "the dev instance (T1) must be runnable, and
	must report its degraded ceiling rather than silently behaving as if it were T2". A
	factory that never said where it runs is not a factory running on a dev machine; it is
	a missing setting, and the report says so.

	A malformed value is refused rather than defaulted. Defaulting on a typo would put a
	deployment that meant T3 on T1's ceilings with no error, and the operator would have
	no way to tell the typo from a deliberate T1.
	"""
	configured = os.environ.get("SOFACT_TOPOLOGY")
	if not configured:
		return None
	try:
		return DeploymentTopology(configured.strip().upper())
	except ValueError as exc:
		known = ", ".join(t.value for t in DeploymentTopology)
		typer.secho(
			f"cannot read SOFACT_TOPOLOGY: {configured!r} is not one of {known} (§5.4)",
			fg="red",
		)
		raise typer.Exit(code=1) from exc


def _configured_specs() -> Mapping[str, HarnessSpec] | None:
	"""The harness table this deployment configured, if it configured one (FR-156).

	``None`` means "use the built-in table", which is not the same as an empty one: an
	empty table leaves no harness to choose a default from, so a misspelled path would
	otherwise surface as "no default harness" rather than "no such file".
	"""
	configured = os.environ.get("SOFACT_HARNESS_SPECS")
	if not configured:
		return None
	try:
		return load_specs(Path(configured))
	except ValueError as exc:
		typer.secho(f"cannot read SOFACT_HARNESS_SPECS: {exc}", fg="red")
		raise typer.Exit(code=1) from exc


def _require_tools(tools: str | None) -> str:
	"""Resolve the tool set, refusing an empty one *before* a session starts.

	An empty allowlist is not "no tools configured": it is a producer handed no way to
	write, whose failure would surface later as a failed step with no cause attached.
	"""
	try:
		return resolve_tools(tools)
	except ValueError as exc:
		typer.secho(f"cannot use that tool set: {exc}", fg="red")
		raise typer.Exit(code=1) from exc


def _require_known(svc: FactoryService, harness: str | None) -> str:
	"""Resolve a harness name, refusing one this deployment has not configured.

		Without this an unknown name reaches ``spec_for`` and leaves the command as a
	traceback. ``harness_name`` can also refuse on its own — a table holding several
		harnesses and no default is ambiguous — and that refusal is an operator error too.
	"""
	try:
		resolved = svc.harness_name(harness)
	except KeyError as exc:
		typer.secho(f"cannot choose a harness: {exc.args[0]}", fg="red")
		raise typer.Exit(code=1) from exc
	table = svc.harness_table()
	if resolved not in table:
		known = ", ".join(sorted(table)) or "none"
		typer.secho(f"unknown harness {resolved!r}; configured harnesses: {known}", fg="red")
		raise typer.Exit(code=1)
	return resolved


def _home_of(ctx: typer.Context, override: Path | None = None) -> Path | None:
	"""State directory for a subcommand.

	``sofact --home X`` lands on the root callback; ``sofact status --home X`` lands
	on the subcommand. Both are honoured. Without this the two spellings disagree
	silently: the first would write to ``X`` while the second read ``./.sofact``, and
	the only symptom is "no goal yet" against a goal that plainly exists.
	"""
	if override is not None:
		return override
	return ctx.obj if isinstance(ctx.obj, Path) else None


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def _print_draft(draft: SpecificationDraft) -> None:
	typer.secho(f"\nspecification draft {draft.id}", fg="cyan", bold=True)
	typer.secho(
		f"  {len(draft.stems)} clause stems, no oracles assigned",
		fg="bright_black",
	)
	for kind, label in (
		(ClauseKind.POSITIVE, "must hold"),
		(ClauseKind.NEGATIVE, "must not happen"),
	):
		selected = [s for s in draft.stems if s.kind == kind]
		if not selected:
			continue
		typer.secho(f"\n  {label}", fg="white", bold=True)
		for stem in selected:
			typer.echo(f"    [{stem.derived_from.value}] {stem.statement}")
	typer.secho(
		"\nNo contract can be built from this yet: every stem needs an oracle "
		"(spec FR-001 — no oracle, no autonomy).",
		fg="yellow",
	)


_OUTCOME_STYLE: dict[VerdictOutcome, str] = {
	VerdictOutcome.SATISFIED: "green",
	VerdictOutcome.VIOLATED: "red",
	VerdictOutcome.INSUFFICIENT: "yellow",
}

# REPAIRED is green because the *session* succeeded; whether the clause now holds is
# the verdict's question, printed separately. Colouring this by the contract would make
# the two lines say the same thing twice and hide which one moved.
_REPAIR_STYLE: dict[RepairOutcome, str] = {
	RepairOutcome.REPAIRED: "green",
	RepairOutcome.STILL_REFUTED: "red",
	RepairOutcome.NOT_COMPLETED: "yellow",
	RepairOutcome.EXHAUSTED: "red",
}

_OUTCOME_MARK: dict[VerdictOutcome, str] = {
	VerdictOutcome.SATISFIED: "✓",
	VerdictOutcome.VIOLATED: "✗",
	VerdictOutcome.INSUFFICIENT: "?",
}


def _print_report(report: VerificationReport) -> None:
	typer.secho(
		f"\nverdict {report.outcome.value.upper()}",
		fg=_OUTCOME_STYLE[report.outcome],
		bold=True,
	)
	typer.secho(
		f"  contract {report.contract_id} @ {report.contract_hash[:12]}",
		fg="bright_black",
	)
	typer.secho(
		f"  ceiling {report.ceiling.name} from weakest oracle rank {report.weakest_oracle_rank}",
		fg="bright_black",
	)
	if report.reused_from is not None:
		typer.secho(
			f"  reused from the check at {report.reused_from.isoformat()} -- the artefact and "
			"the oracle set are unchanged, so the oracles did not run again (FR-006).",
			fg="bright_black",
		)
	for verdict in report.verdicts:
		typer.secho(
			f"  {_OUTCOME_MARK[verdict.outcome]} {verdict.statement}",
			fg=_OUTCOME_STYLE[verdict.outcome],
		)
		typer.secho(f"      {verdict.reason}", fg="bright_black")
	if not report.is_clean:
		typer.secho(
			"\nNot verified. Only an all-satisfied report grants autonomy — an unrun "
			"oracle is not a passing one.",
			fg="yellow",
		)


# --------------------------------------------------------------------------- #
# the conversation
# --------------------------------------------------------------------------- #


async def _chat(svc: FactoryService) -> None:
	typer.secho("SoFact", fg="cyan", bold=True)
	typer.secho(f"  state: {svc.home}", fg="bright_black")

	if svc.llm is not None and await svc.llm.available():
		typer.secho(f"  advisor: {svc.llm.config.model}", fg="bright_black")
	else:
		model = svc.llm.config.model if svc.llm else "none"
		typer.secho(
			f"  advisor: {model} unreachable — continuing with the plain questionnaire",
			fg="yellow",
		)

	goal = await svc.current_goal()
	if goal is None:
		try:
			statement = (
				await asyncio.to_thread(typer.prompt, "\nWhat do you want to build?")
			).strip()
		except (EOFError, KeyboardInterrupt, typer.Abort):
			# `click` turns EOF into its own Abort rather than letting EOFError out, so
			# a piped run ends here unless this is caught. Nothing has been asked yet, so
			# this is not lost progress.
			typer.secho("\nnothing to interrogate.", fg="yellow")
			return
		if not statement:
			typer.secho("nothing to interrogate.", fg="yellow")
			return
		goal = await svc.start(statement)
	else:
		typer.secho(f"\nresuming goal {goal.id}", fg="bright_black")
		typer.secho(f"  {goal.statement}", fg="white")

	await _interrogate(svc, goal.id)


async def _interrogate(svc: FactoryService, goal_id: str) -> None:
	while True:
		pending = await svc.open_question(goal_id)
		if pending is None:
			break
		dimension, spec = pending
		done, total = (await svc.readiness(goal_id)).progress

		typer.secho(f"\n[{done + 1}/{total}] {dimension.value}", fg="cyan", bold=True)
		typer.echo(f"  {spec.question}")
		typer.secho(f"  ↳ {spec.rationale}", fg="bright_black")

		try:
			text = await asyncio.to_thread(typer.prompt, "  ")
		except (EOFError, KeyboardInterrupt, typer.Abort):
			# EOF arrives as `typer.Abort`, not `EOFError`: the documented resume path
			# has to be reachable from a pipe, not only from a person typing.
			typer.secho("\nstopped. Progress is in the log; run `sofact` to resume.", fg="yellow")
			return
		if not text.strip():
			continue

		await svc.answer(goal_id, dimension, text)
		readiness = await svc.readiness(goal_id)
		status = next(s for s in readiness.statuses if s.dimension == dimension)

		if status.resolved:
			typer.secho("  ✓ resolved", fg="green")
			continue

		for reason in status.reasons:
			typer.secho(f"  ✗ {reason}", fg="yellow")
		advice = await svc.advise(goal_id, dimension)
		if advice.text is not None and advice.text.strip().upper() != "ADEQUATE":
			typer.secho(f"\n  advisor: {advice.text.strip()}", fg="magenta")
		typer.secho("  (answer again to replace it)", fg="bright_black")

	readiness = await svc.readiness(goal_id)
	if not readiness.is_ready:  # pragma: no cover - the loop above exits only when ready
		typer.secho("interrogation ended with dimensions still open.", fg="red")
		return

	typer.secho("\n✓ every dimension resolved", fg="green", bold=True)
	_print_draft(await svc.draft(goal_id))


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #


@app.callback(invoke_without_command=True)
def root(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	version: bool = _VERSION_OPTION,
) -> None:
	"""Start or resume an interrogation when invoked with no subcommand."""
	if version:
		typer.echo(f"sofact {__version__}")
		raise typer.Exit
	ctx.obj = home
	if ctx.invoked_subcommand is None:
		svc = _service(home)
		try:
			asyncio.run(_chat(svc))
		except KeyboardInterrupt:  # pragma: no cover - interactive only
			typer.secho("\ninterrupted.", fg="yellow")


@app.command()
def status(ctx: typer.Context, home: Path | None = _HOME_OPTION) -> None:
	"""Show the current goal and how far the interrogation has got."""
	asyncio.run(_status(_service(_home_of(ctx, home))))


async def _status(svc: FactoryService) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho(f"no goal yet in {svc.home}. Run `sofact` to start one.", fg="yellow")
		return
	typer.secho(f"goal {goal.id}", fg="cyan", bold=True)
	typer.echo(f"  {goal.statement}")

	state = await svc.state()
	current = state.current_phase
	stopped = state.open_gate
	line = f"\nphase {current.value}"
	if stopped is not None:
		line += f" — stopped at the {PHASE_GATE[stopped.phase].value} gate"
	typer.secho(line, fg="yellow" if stopped is not None else "white", bold=True)

	# Printed before the readiness loop, which rebinds `state` to each dimension's
	# status. A cut changes what every other line here means — the phase, the
	# readiness, the draft are all read under it — so a reader who did not know one
	# was in force would be reading a rolled-back project as the current one.
	cut = state.cut
	if cut is not None:
		typer.secho(
			f"\nrolled back to entry {cut.target_index} by {cut.by}: {cut.reason}",
			fg="magenta",
			bold=True,
		)
		typer.secho(
			"  the phase above and everything below are read under it; the log keeps what it hid",
			fg="bright_black",
		)

	readiness = await svc.readiness(goal.id)
	done, total = readiness.progress
	typer.secho(f"\nreadiness {done}/{total}", fg="white", bold=True)
	for state in readiness.statuses:
		mark = typer.style("✓", fg="green") if state.resolved else typer.style("✗", fg="yellow")
		typer.echo(f"  {mark} {state.dimension.value}")
		for reason in state.reasons:
			typer.secho(f"      {reason}", fg="bright_black")

	draft = await svc.latest_draft(goal.id)
	if draft is not None:
		typer.secho(f"\nlatest draft {draft.id}: {len(draft.stems)} stems", fg="bright_black")

	chain = await svc.verify_ledger()
	typer.secho(
		f"\nledger: {chain.length} entries, chain {'intact' if chain.ok else 'BROKEN'}",
		fg="green" if chain.ok else "red",
	)


@app.command(name="ledger")
def show_ledger(ctx: typer.Context, home: Path | None = _HOME_OPTION) -> None:
	"""Print the append-only event log."""
	for entry in asyncio.run(_service(_home_of(ctx, home)).entries()):
		typer.secho(
			f"{entry.index:>4}  {entry.at.isoformat()}  {entry.kind.value}", fg="cyan", nl=False
		)
		typer.echo(f"  {entry.entry_hash[:12]}")


@app.command(name="verify-ledger")
def verify_ledger(ctx: typer.Context, home: Path | None = _HOME_OPTION) -> None:
	"""Recompute the hash chain. Exit code 1 if it does not verify."""
	chain = asyncio.run(_service(_home_of(ctx, home)).verify_ledger())
	if chain.ok:
		typer.secho(f"intact: {chain.length} entries", fg="green")
		return
	typer.secho(f"BROKEN at entry {chain.broken_at}: {chain.reason}", fg="red")
	raise typer.Exit(code=1)


@app.command(name="rollback")
def rollback(
	ctx: typer.Context,
	to: int = _TO_OPTION,
	by: str = _CUT_BY_OPTION,
	reason: str = _REASON_OPTION,
	home: Path | None = _HOME_OPTION,
) -> None:
	"""Read the project as of entry ``--to``, and record why (FR-094, FR-003)."""
	asyncio.run(_rollback(_service(_home_of(ctx, home)), to=to, by=by, reason=reason))


async def _rollback(svc: FactoryService, *, to: int, by: str, reason: str) -> None:
	before = await svc.entries()
	try:
		record = await svc.cut(to, by=by, reason=reason)
	except ValueError as exc:
		typer.secho(str(exc), fg="red")
		raise typer.Exit(code=1) from exc
	hidden = before[-1].index - to
	typer.secho(f"rolled back to entry {to}", fg="cyan", bold=True)
	typer.echo(f"  {hidden} entr{'y' if hidden == 1 else 'ies'} hidden, none deleted")
	typer.secho(f"  by {record.by}: {record.reason}", fg="bright_black")


@app.command()
def phase(ctx: typer.Context, home: Path | None = _HOME_OPTION) -> None:
	"""Show where the pipeline is, and stop if a gate is open (FR-060)."""
	asyncio.run(_phase(_service(_home_of(ctx, home))))


async def _phase(svc: FactoryService) -> None:
	"""Print the phase machine's current position.

	The exit code answers one question: is machine work permitted right now? An open
	gate is a stop, because FR-061 makes it one — a script that drives the pipeline can
	check this verb rather than re-deriving the gate table from the phase.
	"""
	state = await svc.state()
	current = state.current_phase
	typer.secho(f"phase {current.value}", fg="cyan", bold=True)

	for entry in PHASE_SEQUENCE:
		status = state.phase_status(entry)
		mark = {
			PhaseStatus.COMPLETE: typer.style("✓", fg="green"),
			PhaseStatus.ACTIVE: typer.style("▶", fg="cyan"),
			PhaseStatus.AWAITING_GATE: typer.style("‖", fg="yellow"),
			PhaseStatus.PENDING: typer.style("·", fg="bright_black"),
		}[status]
		gate = PHASE_GATE.get(entry)
		label = f"{entry.value} {entry.name.lower()}"
		if gate is not None:
			label += f"  [{gate.value}]"
		typer.echo(f"  {mark} {label:<28} {status.value}")

	open_gate = state.open_gate
	if open_gate is not None:
		gate = PHASE_GATE[open_gate.phase]
		typer.secho(
			f"\n  stopped at the {gate.value} gate. No machine work downstream of an "
			f"unapproved gate (FR-061).",
			fg="yellow",
		)
		for check in open_gate.checks:
			mark = typer.style("✓", fg="green") if check.passed else typer.style("✗", fg="red")
			typer.echo(f"    {mark} {check.name}: {check.detail}")
		if not open_gate.checks:
			typer.secho(
				"    nothing has been presented to approve yet: run the phase that "
				"produces the artefact first (FR-080).",
				fg="bright_black",
			)
		else:
			typer.secho(
				f"    approve with: sofact gate --approve {open_gate.phase.value}",
				fg="bright_black",
			)
		raise typer.Exit(code=1)


@app.command()
def gate(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	approve: str | None = typer.Option(
		None, "--approve", help="The phase whose gate to pass, e.g. P2."
	),
	present: str | None = typer.Option(
		None, "--present", help="Record that a phase's machine checks are ready, e.g. P2."
	),
	cost: str | None = typer.Option(
		None,
		"--cost",
		help="Record what a gate cost, as MINUTES[:REWORK], e.g. 90:0.25 (FR-160).",
	),
	by: str = typer.Option("operator", help="Who is deciding. Recorded, not verified."),
) -> None:
	"""Present or approve a gate, or record what one cost (FR-061, FR-160).

	``--cost`` takes ``MINUTES[:REWORK]``, where the rework fraction is the share of the
	slice the operator sent back — ``90:0.25`` is ninety minutes and a quarter of the
	artefact returned. It is recorded against the phase's gate, which must already have
	been passed: a cost for a gate nobody sat at is a measurement of nothing.
	"""
	asyncio.run(_gate(_service(_home_of(ctx, home)), approve, present, cost, by))


def _gate_cost(cost: str, phase: Phase) -> tuple[float, float]:
	"""Parse ``MINUTES[:REWORK]``, naming the gate in any refusal (FR-160).

	The fraction defaults to ``0.0`` — a slice accepted whole — rather than being
	required, because the common case is a gate that cost time and sent nothing back,
	and a verb that made an operator type ``0`` every time would be one they stop using.
	"""
	minutes_text, _, rework_text = cost.partition(":")
	try:
		minutes = float(minutes_text)
		rework = float(rework_text) if rework_text else 0.0
	except ValueError as exc:
		raise ValueError(f"not a cost: {cost!r}. Expected MINUTES[:REWORK], e.g. 90:0.25") from exc
	if phase not in PHASE_GATE:
		raise ValueError(f"{phase.value} has no gate to cost (FR-061)")
	return minutes, rework


async def _gate(
	svc: FactoryService,
	approve: str | None,
	present: str | None,
	cost: str | None,
	by: str,
) -> None:
	if len([x for x in (approve, present, cost) if x is not None]) != 1:
		typer.secho("name exactly one of --present, --approve or --cost.", fg="yellow")
		raise typer.Exit(code=1)
	named_text = approve or present or cost
	assert named_text is not None, "exactly one of the three was named, checked above"
	try:
		named = Phase(named_text.split(":", 1)[0])
	except ValueError as exc:
		choices = ", ".join(p.value for p in PHASE_SEQUENCE)
		typer.secho(f"not a phase: {named_text!r}. One of: {choices}", fg="yellow")
		raise typer.Exit(code=1) from exc

	if cost is not None:
		# FR-160. The phase is named first and the measurement second, so
		# ``--cost P2:90:0.25`` reads as "what P2's gate cost", which is the order an
		# operator would say it in.
		_, _, measurement = cost.partition(":")
		try:
			minutes, rework = _gate_cost(measurement, named)
			recorded = await svc.record_gate_cost(
				PHASE_GATE[named], human_minutes=minutes, rework_fraction=rework, by=by
			)
		except (ValueError, KeyError) as exc:
			typer.secho(f"cannot record cost: {exc}", fg="red")
			raise typer.Exit(code=1) from exc
		typer.secho(
			f"\n{recorded.gate.value} cost {recorded.human_minutes:g} human-minute(s), "
			f"{recorded.rework_fraction:.0%} of the slice returned to the producer "
			f"(FR-160). §1.3's 180-600 is a budget; this is what the humans spent.",
			fg="cyan",
		)
		return

	if present is not None:
		# The machine half. Checks are empty here because this verb records that the
		# phase's artefact is ready to be looked at; the phase's own command is where
		# machine checks are computed, and it calls the service directly.
		try:
			advance = await svc.advance_phase(named, PhaseStatus.AWAITING_GATE, checks=(), by=by)
		except ValueError as exc:
			typer.secho(f"cannot present: {exc}", fg="yellow")
			raise typer.Exit(code=1) from exc
		gate_name = PHASE_GATE.get(named)
		typer.secho(
			f"\n{named.value} presented"
			+ (f" at the {gate_name.value} gate" if gate_name is not None else "")
			+ f" ({len(advance.checks)} machine check(s)).",
			fg="cyan",
		)
		return

	try:
		approved = await svc.approve_gate(named, by=by)
	except ValueError as exc:
		typer.secho(f"cannot approve: {exc}", fg="red")
		raise typer.Exit(code=1) from exc
	typer.secho(
		f"\n{named.value} approved by {approved.approved_by} at {approved.approved_at}. "
		f"Pipeline is now in {await svc.current_phase()}.",
		fg="green",
	)


@app.command()
def draft(ctx: typer.Context, home: Path | None = _HOME_OPTION) -> None:
	"""Draft clause stems from the current goal, if it is ready."""
	asyncio.run(_draft(_service(_home_of(ctx, home))))


async def _draft(svc: FactoryService) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	try:
		_print_draft(await svc.draft(goal.id))
	except ValueError as exc:
		typer.secho(f"not ready: {exc}", fg="yellow")
		raise typer.Exit(code=1) from exc


@app.command(name="specify")
def specify(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	entity: list[str] | None = _ENTITY_OPTION,
	assumption: list[str] | None = _ASSUMPTION_OPTION,
	value: str | None = _VALUE_OPTION,
	criterion: list[str] | None = _CRITERION_OPTION,
	approve: bool = typer.Option(
		False,
		"--approve",
		help="Record the operator's approval of the proposed specification (FR-080).",
	),
	by: str = typer.Option("operator", "--by", help="Who is approving. Required with --approve."),
) -> None:
	"""Propose a specification for the current contract, and gate it (FR-076).

	Without ``--approve`` this proposes and reports the machine checks — traceability,
	criteria, the system model, the value hypothesis. §3.3 places a gate here because
	"no oracle exists for 'this specification expresses your actual intent'", so the
	other half is the operator's, and it is a separate act rather than something a
	passing check implies.

	``--entity``, ``--assumption``, ``--value`` and ``--criterion`` carry the parts of the
	specification that are the *operator's own statements* rather than derivations.
	FR-078, FR-079, FR-085 and FR-116 make them requirements, and a verb that could not
	accept them would be a verb whose gate could never pass — which is a gate that has
	been disabled while still reporting itself as one.
	"""
	asyncio.run(
		_specify(
			_service(_home_of(ctx, home)),
			entities=tuple(entity or ()),
			assumptions=tuple(assumption or ()),
			value=value,
			criteria=tuple(criterion or ()),
			approve=approve,
			by=by,
		)
	)


def _entity_option(raw: str, contract: Contract) -> SystemEntity:
	"""Parse ``NAME:CLAUSE-INDEX`` into an entity linked to that clause (FR-081).

	By *index* rather than by clause id because the operator reads a numbered clause list,
	and asking them to paste a UUID would make declaring a model an exercise in copying
	identifiers. The index is 1-based to match what ``sofact contract`` prints.
	"""
	name, _, index_text = raw.partition(":")
	if not name.strip() or not index_text.strip():
		raise ValueError(f"--entity wants NAME:CLAUSE-INDEX, got {raw!r}")
	try:
		index = int(index_text)
	except ValueError as exc:
		raise ValueError(f"--entity clause index must be a number, got {index_text!r}") from exc
	if not 1 <= index <= len(contract.clauses):
		raise ValueError(
			f"--entity names clause {index}, but the contract has {len(contract.clauses)} clause(s)"
		)
	clause = contract.clauses[index - 1]
	return SystemEntity(name=name.strip(), description=clause.statement, clause_ids=(clause.id,))


def _assumption_option(raw: str) -> Assumption:
	"""Parse ``STATEMENT | REFUTED-BY`` into an assumption (FR-079)."""
	statement, sep, refuted_by = raw.partition("|")
	if not sep or not statement.strip() or not refuted_by.strip():
		raise ValueError(
			f"--assumption wants STATEMENT | REFUTED-BY, got {raw!r}. An assumption "
			"without a refuting observation is a belief, not a declared uncertainty "
			"(FR-079)"
		)
	return Assumption(id=uuid7str(), statement=statement.strip(), refuted_by=refuted_by.strip())


def _value_option(raw: str) -> ValueHypothesis:
	"""Parse ``EFFECT | BENEFICIARY | INSTRUMENT`` into a value hypothesis (FR-085)."""
	parts = [p.strip() for p in raw.split("|")]
	if len(parts) != 3 or not all(parts):
		raise ValueError(
			f"--value wants EFFECT | BENEFICIARY | REFUTING-INSTRUMENT, got {raw!r} (FR-085)"
		)
	return ValueHypothesis(effect=parts[0], beneficiary=parts[1], refuting_instrument=parts[2])


def _criterion_option(raw: str, contract: Contract) -> SystemCriterion:
	"""Parse ``STATEMENT | CRITERION | INDEX,INDEX`` into a system-level criterion (FR-116).

	By clause *index* for the same reason ``--entity`` is: the operator reads a numbered
	clause list, and pasting UUIDs into a criterion would make declaring one an exercise
	in copying identifiers.

	Two indexes are the minimum and the type enforces it. A criterion over one clause is
	that clause's module's job, and FR-116 asks for the criteria *no single module can
	satisfy* — so a one-clause criterion is not a weaker system criterion, it is a
	different thing wearing the name.
	"""
	statement, sep, rest = raw.partition("|")
	criterion, sep2, indexes = rest.partition("|")
	if not sep or not sep2 or not statement.strip() or not criterion.strip():
		raise ValueError(
			f"--criterion wants STATEMENT | CRITERION | CLAUSE-INDEX,CLAUSE-INDEX, got {raw!r}"
		)
	clause_ids: list[str] = []
	for piece in indexes.split(","):
		text = piece.strip()
		try:
			index = int(text)
		except ValueError as exc:
			raise ValueError(
				f"--criterion clause index must be a number, got {text!r}. It takes the "
				"1-based indexes `sofact contract` prints"
			) from exc
		if not 1 <= index <= len(contract.clauses):
			raise ValueError(
				f"--criterion names clause {index}, but the contract has "
				f"{len(contract.clauses)} clause(s)"
			)
		clause_ids.append(contract.clauses[index - 1].id)
	return SystemCriterion(
		id=uuid7str(),
		statement=statement.strip(),
		criterion=criterion.strip(),
		clause_ids=tuple(clause_ids),
	)


async def _specify(
	svc: FactoryService,
	*,
	entities: tuple[str, ...],
	assumptions: tuple[str, ...],
	value: str | None,
	criteria: tuple[str, ...],
	approve: bool,
	by: str,
) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	try:
		model = SystemModel(entities=tuple(_entity_option(e, built) for e in entities))
		declared = tuple(_assumption_option(a) for a in assumptions)
		hypothesis = _value_option(value) if value is not None else None
		system_criteria = tuple(_criterion_option(c, built) for c in criteria)
	except ValueError as exc:
		typer.secho(f"bad option: {exc}", fg="red")
		raise typer.Exit(code=1) from exc
	proposal = await svc.specify(
		built.id,
		system_model=model,
		assumptions=declared,
		value_hypothesis=hypothesis,
		system_criteria=system_criteria,
	)
	_print_specification(proposal, await svc.specification_gate(proposal.id))
	if not approve:
		return
	try:
		result = await svc.approve_specification(proposal.id, by=by)
	except ValueError as exc:
		typer.secho(f"cannot approve: {exc}", fg="red")
		raise typer.Exit(code=1) from exc
	typer.secho(f"\napproved by {result.approved_by}", fg="green")


def _print_specification(proposal: Specification, result: SpecificationGate) -> None:
	typer.secho(f"\nspecification {proposal.id}", fg="cyan", bold=True)
	typer.echo(
		f"  {len(proposal.requirements)} requirement(s) over {len(proposal.clause_ids)} clause(s)"
	)
	# The human-verified count is printed first among the counts because it is the one
	# FR-082 makes cost something: a requirement a person must check is not a defect, but
	# it is the number that decides whether the gate is affordable.
	human = proposal.human_verified
	typer.secho(
		f"  {len(proposal.requirements) - len(human)} machine-checkable, "
		f"{len(human)} human-verified (FR-082)",
		fg="yellow" if human else "green",
	)
	for requirement in proposal.requirements:
		mark = "oracle" if requirement.is_machine_checkable else "human "
		typer.secho(f"    [{mark}] {requirement.statement}", fg="cyan")
		typer.secho(f"        criterion: {requirement.criterion}", fg="bright_black")
	model = proposal.system_model
	if not model.is_empty:
		typer.secho(
			f"  model: {len(model.entities)} entity(ies), "
			f"{len(model.relationships)} relationship(s), "
			f"{len(model.invariants)} invariant(s)",
			fg="cyan",
		)
	if proposal.non_goals:
		typer.secho("  non-goals", fg="cyan")
		for non_goal in proposal.non_goals:
			typer.echo(f"    - {non_goal.statement}")
	if proposal.system_criteria:
		typer.secho("  system-level criteria (FR-116)", fg="cyan")
		for criterion in proposal.system_criteria:
			typer.echo(f"    - {criterion.statement}")
			typer.secho(
				f"        checked by {criterion.criterion}, over "
				f"{len(criterion.clause_ids)} clause(s)",
				fg="bright_black",
			)
	if proposal.assumptions:
		typer.secho("  assumptions", fg="cyan")
		for assumption in proposal.assumptions:
			typer.echo(f"    - {assumption.statement}")
			typer.secho(f"        refuted by {assumption.refuted_by}", fg="bright_black")
	if proposal.value_hypothesis is not None:
		value = proposal.value_hypothesis
		typer.secho("  value hypothesis (declared, never certified -- FR-086)", fg="cyan")
		typer.echo(f"    - {value.effect} for {value.beneficiary}")
		typer.secho(f"        refuted by {value.refuting_instrument}", fg="bright_black")
	typer.secho("\n  gate", fg="cyan", bold=True)
	for check in result.checks:
		mark = "ok  " if check.passed else "FAIL"
		colour = "green" if check.passed else "red"
		typer.secho(f"    [{mark}] {check.name}: {check.detail}", fg=colour)
	typer.secho(
		"  approved" if result.is_approved else "  NOT approved: P2 is a human gate (FR-080)",
		fg="green" if result.is_approved else "yellow",
	)


@app.command(name="decompose")
def decompose(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	approve: bool = typer.Option(
		False,
		"--approve",
		help="Record the operator's approval of the proposed decomposition (FR-087).",
	),
	by: str = typer.Option("operator", "--by", help="Who is approving. Required with --approve."),
) -> None:
	"""Propose modules for the current contract, and gate the proposal (FR-087).

	Without ``--approve`` this proposes and reports the machine checks, which is the
	half a machine can do. FR-087's other half is the operator's, because §7.1 says no
	oracle covers "this is the right architecture" — so approval is a separate, explicit
	act rather than something a passing check implies.
	"""
	asyncio.run(_decompose(_service(_home_of(ctx, home)), approve=approve, by=by))


async def _decompose(svc: FactoryService, *, approve: bool, by: str) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	proposal = await svc.decompose(built.id)
	_print_decomposition(proposal, await svc.decomposition_gate(proposal.id))
	if not approve:
		return
	try:
		result = await svc.approve_decomposition(proposal.id, by=by)
	except ValueError as exc:
		typer.secho(f"cannot approve: {exc}", fg="red")
		raise typer.Exit(code=1) from exc
	typer.secho(f"\napproved by {result.approved_by}", fg="green")


def _print_decomposition(proposal: Decomposition, result: DecompositionGate) -> None:
	typer.secho(f"\ndecomposition {proposal.id}", fg="cyan", bold=True)
	typer.echo(
		f"  {proposal.interface_count} module(s); "
		f"G1-G2 share {proposal.target_class_share:.0%} (FR-125)"
	)
	order = proposal.build_order()
	typer.secho("  build order: " + " -> ".join(m.name for m in order), fg="bright_black")
	for module in order:
		typer.secho(f"    {module.name} [{module.module_class.value}]", fg="cyan")
		typer.echo(f"        {module.interface}")
		# FR-097: the bound is printed with the module it binds, because an operator
		# approving at P3 is approving this number. Hiding it in the gate's detail line
		# would put it where the review happens rather than where the decision is made.
		typer.secho(
			f"        budget {module.budget.max_files} file(s), "
			f"{module.budget.max_loc} line(s), {module.budget.reasoning_class.value}",
			fg="bright_black",
		)
		for criterion in module.completion_criteria:
			typer.secho(f"        done when: {criterion}", fg="bright_black")
		if module.depends_on:
			names = ", ".join(
				d.name for d in (proposal.module(i) for i in module.depends_on) if d is not None
			)
			typer.secho(f"        depends on {names}", fg="bright_black")
	typer.secho("\n  gate", fg="cyan", bold=True)
	for check in result.checks:
		mark = "ok  " if check.passed else "FAIL"
		colour = "green" if check.passed else "red"
		typer.secho(f"    [{mark}] {check.name}: {check.detail}", fg=colour)
	typer.secho(
		"  approved" if result.is_approved else "  NOT approved: P3 is a human gate (FR-087)",
		fg="green" if result.is_approved else "yellow",
	)


@app.command(name="plan")
def show_plan(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	style: str = _STYLE_OPTION,
) -> None:
	"""Compile the current contract into ordered goal sessions (FR-136)."""
	asyncio.run(_show_plan(_service(_home_of(ctx, home)), style))


async def _show_plan(svc: FactoryService, style: str) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	try:
		plan = await svc.compile_plan(built.id, goal_style=GoalStyle(style))
	except ValueError as exc:
		typer.secho(f"cannot compile: {exc}", fg="red")
		raise typer.Exit(code=1) from exc
	_print_plan(plan)


def _print_plan(plan: GoalPlan) -> None:
	typer.secho(f"\nplan {plan.id}", fg="cyan", bold=True)
	typer.echo(f"  {len(plan.steps)} step(s) over {len(plan.waves())} wave(s)")
	typer.echo(f"  {len(plan.covered_clause_ids)} clause(s) covered; style {plan.goal_style.value}")
	typer.echo(f"  wall-clock cap {plan.total_wall_clock_cap / 3600:.1f} h across all steps")
	for index, wave in enumerate(plan.waves()):
		typer.secho(f"\n  wave {index}: {len(wave)} concurrent", fg="bright_black")
		for step in wave:
			typer.secho(f"    [{step.ordinal}] {step.kind.value}", fg="cyan")
			typer.echo(f"        {step.goal.outcome}")
			typer.secho(
				f"        exit when {len(step.exit_evidence)} of: " + "; ".join(step.exit_evidence),
				fg="bright_black",
			)
			if step.clause_ids:
				typer.secho(f"        covers {len(step.clause_ids)} clause(s)", fg="bright_black")


@app.command()
def probe(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	harness: str | None = _HARNESS_OPTION,
	model: str | None = _MODEL_OPTION,
	tools: str | None = _TOOLS_OPTION,
	timeout: float | None = _PROBE_TIMEOUT_OPTION,
	quick: bool = _QUICK_OPTION,
) -> None:
	"""Attempt a harness and record what was actually observed (FR-148)."""
	asyncio.run(
		_probe(
			_service(_home_of(ctx, home)),
			harness,
			model,
			timeout,
			tools=tools,
			deep=not quick,
		)
	)


async def _probe(
	svc: FactoryService,
	harness: str | None,
	model: str | None,
	timeout: float | None,
	*,
	tools: str | None = None,
	deep: bool = True,
) -> None:
	_require_known(svc, harness)
	resolved_tools = _require_tools(tools)
	workdir = svc.home / "workspace"
	workdir.mkdir(parents=True, exist_ok=True)
	try:
		profile = await svc.probe_harness(
			harness,
			workspace=workdir,
			model=model,
			tools=resolved_tools,
			timeout=timeout,
			deep=deep,
		)
	except HarnessBinaryMissing as exc:
		typer.secho(f"cannot probe: {exc}", fg="red")
		raise typer.Exit(code=1) from exc
	_print_profile(profile, tools=resolved_tools)
	if not profile.is_usable:
		typer.secho(
			"\n  this harness cannot run unattended; dispatching to it would hang "
			"an unattended build (FR-145).",
			fg="red",
		)
		raise typer.Exit(code=1)
	if profile.model_resolved is ProbeOutcome.ABSENT:
		typer.secho(
			f"\n  the harness cannot resolve the model {profile.model!r}, so every dispatch "
			"would fail before any work started -- fix SOFACT_MODEL (or --model) and probe "
			"again (FR-148).",
			fg="red",
		)
		raise typer.Exit(code=1)


def _print_profile(profile: HarnessProfile, *, tools: str) -> None:
	colours = {
		ProbeOutcome.CONFIRMED: "green",
		ProbeOutcome.ABSENT: "red",
		ProbeOutcome.INCONCLUSIVE: "yellow",
	}
	typer.secho(f"\n{profile.name} probe @ {profile.command[0]}", fg="cyan", bold=True)
	typer.echo(f"  version {profile.version or 'unknown'}")
	typer.echo(f"  model   {profile.model or 'unrecorded'}")
	typer.echo(f"  tools   {tools}")
	for finding in profile.findings:
		typer.secho(
			f"  {finding.outcome.value:<13} {finding.capability.value}",
			fg=colours[finding.outcome],
		)
		typer.secho(f"                attempted: {finding.attempted}", fg="bright_black")
		typer.secho(f"                observed:  {finding.observed}", fg="bright_black")
	tone = "green" if profile.supports_goal_dispatch else "yellow"
	typer.secho(
		f"\n  usable={profile.is_usable} goal-mode={profile.goal_mode.value} "
		f"→ {'goal' if profile.supports_goal_dispatch else 'single-shot'} dispatch",
		fg=tone,
	)


@app.command()
def dispatch(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	harness: str | None = _HARNESS_OPTION,
	model: str | None = _MODEL_OPTION,
	tools: str | None = _TOOLS_OPTION,
	workspace: Path | None = _WORKSPACE_OPTION,
	step: str | None = _STEP_OPTION,
	all_steps: bool = _ALL_OPTION,
	max_steps: int | None = _MAX_STEPS_OPTION,
	fresh: bool = _FRESH_OPTION,
	concurrent: bool = _CONCURRENT_OPTION,
) -> None:
	"""Send plan steps to the harness as out-of-process sessions (FR-058)."""
	asyncio.run(
		_dispatch(
			_service(_home_of(ctx, home)),
			harness,
			model,
			workspace,
			step,
			all_steps,
			max_steps,
			tools=tools,
			fresh=fresh,
			concurrent=concurrent,
		),
	)


async def _dispatch(
	svc: FactoryService,
	harness: str | None,
	model: str | None,
	workspace: Path | None,
	step: str | None,
	all_steps: bool,
	max_steps: int | None,
	*,
	tools: str | None = None,
	fresh: bool = False,
	concurrent: bool = False,
) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	plan = await svc.latest_plan(built.id)
	if plan is None:
		typer.secho("no plan yet. Run `sofact plan` first.", fg="yellow")
		raise typer.Exit(code=1)

	resolved = _require_known(svc, harness)
	resolved_tools = _require_tools(tools)
	profile = await svc.latest_profile(harness)
	if profile is None:
		typer.secho(
			f"{resolved} has never been probed here. Run `sofact probe` first: "
			"dispatching against an assumed capability is what FR-148 forbids.",
			fg="yellow",
		)
		raise typer.Exit(code=1)
	if not profile.is_usable:
		typer.secho(f"{resolved} is not usable unattended (FR-145).", fg="red")
		raise typer.Exit(code=1)
	if not profile.supports_goal_dispatch:
		typer.secho(
			f"{resolved} does not force goal mode (FR-144): each step will run "
			"single-shot, and every record will say so.",
			fg="yellow",
		)
	if profile.model_resolved is ProbeOutcome.ABSENT:
		typer.secho(
			f"{resolved} cannot resolve the model {profile.model!r}: this is a "
			"model-resolution failure and not a producer failure, so every step would be "
			"refused rather than dispatched. Fix SOFACT_MODEL (or --model) and probe again.",
			fg="red",
		)
		raise typer.Exit(code=1)

	if not all_steps and step is None:
		typer.secho(
			"nothing selected. Pass --step <ordinal|id> for one step, or --all for the "
			"whole plan, wave by wave.",
			fg="yellow",
		)
		_print_plan(plan)
		return

	workdir = workspace or (svc.home / "workspace")
	if not workdir.is_dir():
		typer.secho(f"workspace does not exist: {workdir}", fg="red")
		raise typer.Exit(code=1)

	if step is not None:
		chosen = plan.step_by_id(step) or next(
			(s for s in plan.steps if str(s.ordinal) == step), None
		)
		if chosen is None:
			typer.secho(f"no step {step!r} in plan {plan.id}", fg="red")
			raise typer.Exit(code=1)
		records = (
			await svc.dispatch_step(
				plan.id,
				chosen.id,
				name=harness,
				workspace=workdir,
				model=model,
				tools=resolved_tools,
				fresh=fresh,
			),
		)
	else:
		if concurrent:
			# FR-141's one precondition, stated where the operator can act on it. A worktree
			# is per *module*, so a wave is isolated only when every step in it is owned by
			# a distinct module -- a module-less step has no worktree to be given, and two
			# steps of one module would share a branch and therefore one directory. Either
			# way the wave runs sequentially, and saying so here means the operator is not
			# left reading a speedup that did not happen.
			typer.secho(
				"  --concurrent: each wave runs in per-module worktrees; a wave that cannot "
				"be given one worktree per step runs sequentially (FR-141).",
				fg="bright_black",
			)
		records = await svc.dispatch_plan(
			plan.id,
			name=harness,
			workspace=workdir,
			model=model,
			tools=resolved_tools,
			max_steps=max_steps,
			fresh=fresh,
			concurrent=concurrent,
		)

	for record in records:
		_print_dispatch(record)

	# The exit code answers one question: did anything this run was responsible for break?
	# A step that failed, a step whose own clauses the oracles now refute, or a plan that
	# ran to the end with the contract not clean — each is a red light. A run the operator
	# capped on purpose is not: it stopped early by request, so progress exits 0, the
	# refutation check still applies, and the contract line above says how much holds.
	report = await svc.latest_report(plan.contract_id)
	if report is None:
		typer.secho(
			"\n  no verdict: no session completed, so no oracle ran. An unrun contract is "
			"not a passing one (FR-001).",
			fg="red",
		)
		raise typer.Exit(code=1)
	typer.secho(
		f"\n  contract {report.outcome.value}: "
		f"{len(report.satisfied)} of {len(report.verdicts)} clauses hold "
		"(FR-138: a declaration can trigger verification, it can never satisfy it).",
		fg=_OUTCOME_STYLE[report.outcome],
	)
	if report.reused_from is not None:
		typer.secho(
			f"  reused from the check at {report.reused_from.isoformat()} -- the artefact "
			"and the oracle set are unchanged, so the oracles did not run again (FR-006).",
			fg="bright_black",
		)
	refuted = refuted_steps(plan, report)
	ran_the_whole_plan = step is None and max_steps is None and len(records) == len(plan.steps)
	if any(record.step_id in refuted for record in records):
		typer.secho(
			"  a step was refuted: a clause it covers does not hold after its own session.",
			fg="red",
		)
		raise typer.Exit(code=1)
	if not report.is_clean and not ran_the_whole_plan:
		typer.secho(
			f"  stopped after {len(records)} of {len(plan.steps)} step(s); the contract does "
			"not hold yet, and nothing that ran was refuted.",
			fg="yellow",
		)
	if ran_the_whole_plan and not report.is_clean:
		raise typer.Exit(code=1)
	if any(r.outcome is not StepOutcome.COMPLETED for r in records):
		raise typer.Exit(code=1)


def _print_dispatch(record: DispatchRecord) -> None:
	colour = "green" if record.outcome is StepOutcome.COMPLETED else "red"
	typer.secho(
		f"\n  [{record.step_ordinal}] {record.outcome.value} in "
		f"{record.wall_clock_seconds:.1f}s ({record.mode.value})",
		fg=colour,
	)
	typer.secho(f"      argv: {' '.join(record.argv[:6])} …", fg="bright_black")
	if record.note:
		# The note is where a record states what it could not witness, so it is printed
		# whatever the outcome. Printing it only for ``NOT_DISPATCHED`` was a real defect:
		# a session that exited 0 and left no record read as `completed` in green with
		# "its artefact was checked" underneath, while the one sentence saying nothing was
		# witnessed sat unprinted in this field. A caveat the operator cannot see is a
		# caveat that does not exist, and this one contradicts the line above it.
		typer.secho(
			f"      {record.note}",
			fg="red" if record.outcome is StepOutcome.NOT_DISPATCHED else "yellow",
		)
	if record.tokens_observed is not None:
		typer.echo(f"      output tokens: {record.tokens_observed}")
	if record.capability_loss is not None:
		typer.secho(f"      {record.capability_loss}", fg="yellow")
	if record.budget_violations:
		typer.secho(
			f"      budget exceeded: {', '.join(record.budget_violations)}",
			fg="red",
		)
	if record.stderr_tail:
		typer.secho(f"      stderr: {record.stderr_tail.strip()[:300]}", fg="red")
	if record.declared_complete:
		typer.secho(
			f"      declared complete: {record.declaration_note or '(no note)'}",
			fg="magenta",
		)
		typer.secho(
			"      a declaration is not a finding; the oracles decide, and they have run.",
			fg="bright_black",
		)
	elif record.outcome is StepOutcome.COMPLETED:
		typer.secho(
			"      the session completed, so its artefact was checked (FR-163); the verdict "
			"is below.",
			fg="bright_black",
		)
	elif record.outcome is StepOutcome.NOT_DISPATCHED:
		typer.secho(
			"      nothing ran, so there is no artefact and nothing to check.",
			fg="bright_black",
		)
	else:
		typer.secho(
			"      not checked: an incomplete session asserts nothing about the artefact.",
			fg="bright_black",
		)


@app.command()
def integrity(ctx: typer.Context, home: Path | None = _HOME_OPTION) -> None:
	"""Re-verify the pinned contract, oracle-set and goal-text hashes (FR-139)."""
	asyncio.run(_integrity(_service(_home_of(ctx, home))))


async def _integrity(svc: FactoryService) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	plan = await svc.latest_plan(built.id)
	if plan is None:
		typer.secho("no plan yet. Run `sofact plan` first.", fg="yellow")
		raise typer.Exit(code=1)

	checks = await svc.check_integrity(plan.id)
	colours = {
		IntegrityOutcome.INTACT: "green",
		IntegrityOutcome.MODIFIED: "red",
		IntegrityOutcome.UNKNOWN: "yellow",
	}
	typer.secho(f"\nintegrity of plan {plan.id}", fg="cyan", bold=True)
	for check in checks:
		typer.secho(
			f"  {check.outcome.value:<8} {check.subject.value:<10} {check.detail}",
			fg=colours[check.outcome],
		)
	if any(c.outcome is IntegrityOutcome.MODIFIED for c in checks):
		typer.secho(
			"\n  a producer edited its own completion criteria; the work is rejected, "
			"not merely suspect (FR-139).",
			fg="red",
		)
		raise typer.Exit(code=1)


@app.command(name="integrate")
def integrate_command(ctx: typer.Context, home: Path | None = _HOME_OPTION) -> None:
	"""Run P7 over the current plan's dispatched work (FR-111 - FR-116)."""
	asyncio.run(_integrate(_service(_home_of(ctx, home))))


async def _integrate(svc: FactoryService) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	plan = await svc.latest_plan(built.id)
	if plan is None:
		typer.secho("no plan yet. Run `sofact plan` first.", fg="yellow")
		raise typer.Exit(code=1)
	try:
		report = await svc.check_integration(plan.id)
	except ValueError as exc:
		typer.secho(f"cannot integrate: {exc}", fg="red")
		raise typer.Exit(code=1) from exc

	typer.secho(f"\nintegration of plan {report.plan_id}", fg="cyan", bold=True)
	typer.secho("  build order: " + " -> ".join(report.build_order), fg="bright_black")
	typer.echo(f"  built: {', '.join(report.modules_built) or 'nothing'}")
	for check in report.checks:
		mark = "ok  " if check.passed else "FAIL"
		typer.secho(
			f"  [{mark}] {check.name} ({', '.join(check.requirements)}): {check.detail}",
			fg="green" if check.passed else "red",
		)
		for line in check.uncovered:
			typer.secho(f"         not covered: {line}", fg="bright_black")
	for finding in report.findings:
		typer.secho(f"  {finding.kind.value}: {finding.detail}", fg="red")
		typer.secho(
			f"         repair scope (FR-114): {', '.join(finding.modules)}", fg="bright_black"
		)
		for line in finding.evidence:
			typer.secho(f"         {line}", fg="bright_black")
	if report.not_implemented:
		typer.secho(
			"\n  not implemented: "
			+ ", ".join(report.not_implemented)
			+ ". "
			+ _NOT_IMPLEMENTED_WHY,
			fg="yellow",
		)
	if not report.passed:
		typer.secho(
			"\n  integration failed. Repair is scoped to the modules named above, never "
			"to the platform (FR-114).",
			fg="red",
		)
		raise typer.Exit(code=1)


@app.command()
def precision(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	harness: str | None = _HARNESS_OPTION,
) -> None:
	"""How often a producer's completion declaration survived verification (FR-143)."""
	asyncio.run(_precision(_service(_home_of(ctx, home)), harness))


async def _precision(svc: FactoryService, harness: str | None) -> None:
	name = _require_known(svc, harness)
	measured = await svc.declaration_precision(name)
	value = measured.precision
	typer.secho(f"\ndeclaration precision of {name}", fg="cyan", bold=True)
	if value is None:
		typer.secho(
			"  unmeasured: this harness never declared completion. That is not zero — "
			"an absent signal is not a wrong answer (NFR-024).",
			fg="yellow",
		)
		return
	typer.echo(f"  {measured.corroborated}/{measured.declarations} = {value:.0%}")
	typer.secho(
		"  corroboration is clause-level and comes from `sofact verify`, never from "
		"the dispatch itself.",
		fg="bright_black",
	)


@app.command()
def repair(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	harness: str | None = _HARNESS_OPTION,
	model: str | None = _MODEL_OPTION,
	tools: str | None = _TOOLS_OPTION,
	workspace: Path | None = _WORKSPACE_OPTION,
	max_attempts: int = _MAX_ATTEMPTS_OPTION,
	fresh: bool = _FRESH_OPTION,
) -> None:
	"""Hand each refuted clause back to the producer, until clean or out of attempts."""
	asyncio.run(
		_repair(
			_service(_home_of(ctx, home)),
			harness,
			model,
			workspace,
			max_attempts=max_attempts,
			tools=tools,
			fresh=fresh,
		)
	)


async def _repair(
	svc: FactoryService,
	harness: str | None,
	model: str | None,
	workspace: Path | None,
	*,
	max_attempts: int,
	tools: str | None = None,
	fresh: bool = False,
) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	plan = await svc.latest_plan(built.id)
	if plan is None:
		typer.secho("no plan yet. Run `sofact plan` first.", fg="yellow")
		raise typer.Exit(code=1)

	# Same gates as `dispatch`, for the same reason: a repair is a session like any
	# other, so it needs the same evidence that this harness can run one unattended.
	# Skipping them here would make the repair path the way around FR-148.
	resolved = _require_known(svc, harness)
	resolved_tools = _require_tools(tools)
	profile = await svc.latest_profile(harness)
	if profile is None:
		typer.secho(
			f"{resolved} has never been probed here. Run `sofact probe` first: dispatching "
			"against an assumed capability is what FR-148 forbids.",
			fg="yellow",
		)
		raise typer.Exit(code=1)
	if not profile.is_usable:
		typer.secho(f"{resolved} is not usable unattended (FR-145).", fg="red")
		raise typer.Exit(code=1)
	if not profile.supports_goal_dispatch:
		typer.secho(
			f"{resolved} does not force goal mode (FR-144): each repair will run "
			"single-shot, and every record will say so.",
			fg="yellow",
		)

	report = await svc.latest_report(built.id)
	if report is None:
		typer.secho(
			"no verdict yet. Run `sofact verify` first: a repair authored from nothing "
			"would be guessing, and the diagnosis has to come from the verifier.",
			fg="yellow",
		)
		raise typer.Exit(code=1)
	if report.is_clean:
		typer.secho(
			f"\n  contract {report.outcome.value}: nothing is refuted, so there is nothing "
			"to repair. A repair run against a clean contract must not invent work.",
			fg="green",
		)
		return

	workdir = workspace or (svc.home / "workspace")
	if not workdir.is_dir():
		typer.secho(f"workspace does not exist: {workdir}", fg="red")
		raise typer.Exit(code=1)

	typer.secho(
		f"\nrepairing plan {plan.id} against {len(report.violated)} refuted clause(s), "
		f"at most {max_attempts} attempt(s) each.",
		fg="cyan",
		bold=True,
	)
	attempts = await svc.repair_plan(
		plan.id,
		name=harness,
		workspace=workdir,
		model=model,
		tools=resolved_tools,
		max_attempts=max_attempts,
		fresh=fresh,
	)
	if not attempts:
		typer.secho("  no attempt was made.", fg="yellow")
		raise typer.Exit(code=1)
	for attempt in attempts:
		_style = _REPAIR_STYLE[attempt.outcome]
		typer.secho(f"\n  attempt {attempt.attempt} — {attempt.outcome.value}", fg=_style)
		typer.echo(f"      {len(attempt.clause_ids)} clause(s), goal {attempt.goal_hash[:12]}")
		typer.secho(f"      diagnosis: {attempt.diagnosis}", fg="bright_black")

	# The verdict is re-read rather than inferred from the outcomes: an attempt that
	# completed is not an attempt that worked, and only the oracles say which. The
	# outcomes above describe what the producer did; this line describes what holds.
	final = await svc.latest_report(built.id)
	assert final is not None, "a repair ran, so a verdict exists"
	typer.secho(
		f"\n  contract {final.outcome.value}: "
		f"{len(final.satisfied)} of {len(final.verdicts)} clauses hold.",
		fg=_OUTCOME_STYLE[final.outcome],
	)
	exhausted = [a for a in attempts if a.outcome is RepairOutcome.EXHAUSTED]
	if exhausted:
		typer.secho(
			f"  {len(exhausted)} clause(s) ran out of attempts. That is a producer that "
			"cannot do the work, not a factory that stopped trying (FR-101).",
			fg="red",
		)
	if not final.is_clean:
		raise typer.Exit(code=1)


@app.command(name="contract")
def build_contract(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	command: str | None = _COMMAND_OPTION,
) -> None:
	"""Assign an oracle to every clause stem and build the contract."""
	asyncio.run(_contract(_service(_home_of(ctx, home)), command))


async def _contract(svc: FactoryService, command: str | None) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	try:
		built = await svc.contract(goal.id, commands=command)
	except ValueError as exc:
		typer.secho(f"cannot contract: {exc}", fg="yellow")
		raise typer.Exit(code=1) from exc

	typer.secho(f"\ncontract {built.id} v{built.version}", fg="cyan", bold=True)
	typer.echo(f"  {len(built.clauses)} clause(s)")
	typer.echo(f"  weakest oracle rank {built.weakest_oracle_rank} → ceiling {built.ceiling.name}")
	debt = ground_truth_debt(built)
	typer.secho(
		f"  ground-truth debt {debt:.0%}",
		fg="green" if debt == 0 else "yellow",
	)
	unexecutable = unexecutable_clauses(built)
	if unexecutable:
		typer.secho("\n  these clauses name no command, so nothing can run them:", fg="yellow")
		for clause in unexecutable:
			typer.secho(
				f"    [{clause.oracle.oracle_class.value}] {clause.statement}",
				fg="bright_black",
			)


@app.command()
def run(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	workspace: Path | None = _WORKSPACE_OPTION,
	timeout: float = _TIMEOUT_OPTION,
) -> None:
	"""Execute the current contract's oracles and record the observations."""
	asyncio.run(_run(_service(_home_of(ctx, home)), workspace, timeout))


async def _run(svc: FactoryService, workspace: Path | None, timeout: float) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)

	workdir = workspace or (svc.home / "workspace")
	if not workdir.is_dir():
		typer.secho(f"workspace does not exist: {workdir}", fg="red")
		raise typer.Exit(code=1)

	produced = await svc.run(built.id, workspace=workdir, timeout=timeout)
	if not produced:
		typer.secho(
			"no executable oracles in this contract; nothing was run (debt is total).",
			fg="yellow",
		)
		return
	for item in produced:
		# ``isinstance`` before truthiness, not after: the payload is JSON-derived, and
		# a string ``"false"`` is truthy. Only a real boolean counts as timed out.
		observed_timeout = item.payload.get("timed_out")
		timed_out = isinstance(observed_timeout, bool) and observed_timeout
		shown = "timed out" if timed_out else f"exit {item.payload.get('exit_code')}"
		typer.secho(f"  ran {item.payload.get('command')!r} → {shown}", fg="bright_black")


@app.command(name="research")
def research(
	ctx: typer.Context,
	query: str | None = typer.Argument(None, help="Defaults to the current goal's statement."),
	home: Path | None = _HOME_OPTION,
	harness: str | None = _HARNESS_OPTION,
	model: str | None = _MODEL_OPTION,
	tools: str | None = _TOOLS_OPTION,
	super_mode: bool = typer.Option(
		False,
		"--super",
		help="Ask for the multi-phase research loop instead of the single deep one.",
	),
	timeout: float | None = typer.Option(
		None,
		"--timeout",
		help="Override the budget's scaled wall clock for this run (FR-072).",
	),
	max_sources: int | None = typer.Option(
		None,
		"--max-sources",
		help="Sources per intent clause. Default 5, the research loop's own floor.",
	),
	max_calls: int | None = typer.Option(
		None,
		"--max-calls",
		help="Model calls per intent clause. Default 5, read from the loop's own meta.",
	),
	seconds: float | None = typer.Option(
		None,
		"--seconds",
		help="Wall clock per intent clause. Default 300, above the loop's own ceiling.",
	),
) -> None:
	"""Dispatch a research run on the current goal and record what it left (FR-167, FR-072)."""
	asyncio.run(
		_research(
			_service(_home_of(ctx, home)),
			query,
			harness,
			model,
			tools,
			super_mode,
			timeout,
			max_sources,
			max_calls,
			seconds,
		),
	)


async def _research(
	svc: FactoryService,
	query: str | None,
	harness: str | None,
	model: str | None,
	tools: str | None,
	super_mode: bool,
	timeout: float | None,
	max_sources: int | None,
	max_calls: int | None,
	seconds: float | None,
) -> None:
	resolved_tools = _require_tools(tools)
	# Built field by field rather than from a dict comprehension: the three overrides
	# have different types, and a comprehension erases which value belongs to which
	# parameter -- so a swapped pair would type-check and silently bound the wrong thing.
	defaults = ResearchBudget()
	try:
		budget = ResearchBudget(
			max_sources_per_clause=(
				defaults.max_sources_per_clause if max_sources is None else max_sources
			),
			max_model_calls_per_clause=(
				defaults.max_model_calls_per_clause if max_calls is None else max_calls
			),
			max_wall_clock_seconds_per_clause=(
				defaults.max_wall_clock_seconds_per_clause if seconds is None else seconds
			),
		)
	except ValidationError as exc:
		typer.secho(f"bad research budget: {exc.errors()[0]['msg']}", fg="red")
		raise typer.Exit(code=1) from exc
	try:
		record = await svc.research(
			query,
			name=harness,
			model=model,
			tools=resolved_tools,
			mode=ResearchMode.SUPER if super_mode else ResearchMode.DEEP,
			budget=budget,
			timeout=timeout,
		)
	except KeyError as exc:
		typer.secho(str(exc.args[0] if exc.args else exc), fg="yellow")
		raise typer.Exit(code=1) from exc
	_print_research(record)


def _print_research(record: ResearchRecord) -> None:
	style = (
		"green"
		if record.outcome is StepOutcome.COMPLETED
		else ("yellow" if record.outcome is StepOutcome.BUDGET_EXHAUSTED else "red")
	)
	typer.secho(
		f"\nresearch {record.id} @ {record.harness} ({record.mode.value})",
		fg=style,
		bold=True,
	)
	typer.secho(f"  query   {record.query}", fg="bright_black")
	if record.allowance is not None:
		allowance = record.allowance
		typer.secho(
			f"  budget  {allowance.max_sources} source(s), {allowance.max_model_calls} "
			f"call(s), {allowance.max_wall_clock_seconds:.0f}s "
			f"({allowance.intent_clauses} intent clause(s), FR-072)",
			fg="bright_black",
		)
	typer.secho(
		f"  {record.outcome.value}"
		+ (f" after {record.wall_clock_seconds:.0f}s" if record.wall_clock_seconds else ""),
		fg=style,
	)
	if record.note is not None:
		typer.secho(f"  {record.note}", fg="yellow")
	if record.budget_violations:
		# FR-072's three caps are not enforced alike, and the message says which is
		# which: wall clock was killed by SoFact, the other two were read off the
		# artefacts afterwards. Printing them together without that distinction would
		# make an observed overspend look like a bound that held.
		for violation in record.budget_violations:
			typer.secho(f"  over budget: {violation}", fg="red")
	if record.report_path is not None:
		typer.secho(
			f"  report  {record.report_path} ({record.report_chars} characters)",
			fg="bright_black",
		)
		if record.searches_observed is not None:
			typer.secho(f"  searches {record.searches_observed}", fg="bright_black")
		if record.model_calls_observed is not None:
			typer.secho(f"  calls    {record.model_calls_observed}", fg="bright_black")
		else:
			typer.secho(
				"  calls    unmeasured: the loop's meta carried no turn count, so the "
				"model-call cap was not checked either way (NFR-024).",
				fg="yellow",
			)
		if record.source_urls:
			typer.secho(f"  sources {len(record.source_urls)}", fg="bright_black")
			for url in record.source_urls:
				typer.echo(f"    {url}")
		else:
			typer.secho(
				"  no source URLs were recorded; a report without sources is unmeasured "
				"research, not research that found nothing (NFR-024).",
				fg="yellow",
			)
	else:
		typer.secho(
			"  the session left no research-report.md, so nothing was learned that a "
			"later phase could cite (FR-001's discipline, applied to research).",
			fg="red",
		)
	if record.outcome is not StepOutcome.COMPLETED:
		raise typer.Exit(code=1)
	if record.report_path is None:
		raise typer.Exit(code=1)


@app.command(name="sources")
def sources(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	from_run: str | None = typer.Option(
		None,
		"--from-run",
		help="Read the ledger out of this research run's workspace instead of printing it.",
	),
) -> None:
	"""Print the current source ledger, or read one out of a research run (FR-070)."""
	asyncio.run(_sources(_service(_home_of(ctx, home)), from_run))


async def _sources(svc: FactoryService, from_run: str | None) -> None:
	if from_run is not None:
		runs = [r for r in (await svc.state()).research if r.id == from_run]
		if not runs:
			typer.secho(f"no research run {from_run} in this log.", fg="yellow")
			raise typer.Exit(code=1)
		try:
			recorded = await svc.ledger_from(runs[0])
		except (ValueError, OSError) as exc:
			typer.secho(f"cannot read the ledger: {exc}", fg="red")
			raise typer.Exit(code=1) from exc
		typer.secho(
			f"\nrecorded ledger v{recorded.version} from run {from_run}", fg="green", bold=True
		)
	ledger = await svc.current_ledger()
	if ledger is None:
		typer.secho(
			"no source ledger yet: run `sofact research`, then "
			"`sofact sources --from-run <id>` (FR-070).",
			fg="yellow",
		)
		raise typer.Exit(code=1)
	_print_ledger(ledger)
	checks = await svc.ledger_gate()
	failed = [check for check in checks if not check.passed]
	if failed:
		raise typer.Exit(code=1)


@app.command(name="classify")
def classify(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	from_run: str | None = typer.Option(
		None,
		"--from-run",
		help="Read the conclusions out of this research run's workspace instead of printing them.",
	),
) -> None:
	"""Print FR-068's verdict on every intent clause, or read one out of a run."""
	asyncio.run(_classify(_service(_home_of(ctx, home)), from_run))


async def _classify(svc: FactoryService, from_run: str | None) -> None:
	if from_run is not None:
		runs = [r for r in (await svc.state()).research if r.id == from_run]
		if not runs:
			typer.secho(f"no research run {from_run} in this log.", fg="yellow")
			raise typer.Exit(code=1)
		try:
			recorded = await svc.classification_from(runs[0])
		except (ValueError, OSError) as exc:
			typer.secho(f"cannot read the classification: {exc}", fg="red")
			raise typer.Exit(code=1) from exc
		typer.secho(
			f"\nrecorded classification v{recorded.version} from run {from_run}",
			fg="green",
			bold=True,
		)
	classification = await svc.current_classification()
	if classification is None:
		typer.secho(
			"no classification yet: run `sofact research`, then "
			"`sofact classify --from-run <id>` (FR-068).",
			fg="yellow",
		)
		raise typer.Exit(code=1)
	_print_classification(classification)
	checks = await svc.classification_gate()
	for check in checks:
		mark = typer.style("✓", fg="green") if check.passed else typer.style("✗", fg="red")
		typer.echo(f"  {mark} {check.name}: {check.detail}")
	if any(not check.passed for check in checks):
		raise typer.Exit(code=1)


_VERDICT_COLOUR: dict[ResearchVerdict, str] = {
	ResearchVerdict.VALIDATED: "green",
	ResearchVerdict.INVALIDATED: "red",
	ResearchVerdict.UNVERIFIABLE: "yellow",
	ResearchVerdict.DEEPENED: "magenta",
}
"""One colour per verdict, so a reader scanning the output sees the *action* class
before the word: red is the verdict that stops the pipeline (FR-068)."""


def _print_classification(classification: ResearchClassification) -> None:
	"""FR-068's verdicts, each with its action, its evidence and its rationale.

	The action is printed beside every verdict rather than summarised once at the end,
	because the spec's table gives each verdict a different one and a summary is exactly
	where "Invalidated means do not build" gets folded into "some clauses had findings".
	"""
	typer.secho(
		f"\nclassification v{classification.version} for {classification.query!r}",
		fg="cyan",
		bold=True,
	)
	typer.secho(
		f"  {len(classification.classifications)} clause(s) classified; "
		f"{len(classification.invalidated)} invalidated, "
		f"{len(classification.deepened)} deepened, "
		f"{len(classification.unverifiable)} unverifiable (FR-068)",
		fg="bright_black",
	)
	for entry in classification.classifications:
		typer.secho(
			f"  [{entry.verdict.value}] {entry.statement}",
			fg=_VERDICT_COLOUR[entry.verdict],
			bold=True,
		)
		typer.echo(f"      action: {entry.action}")
		typer.secho(f"      why: {entry.rationale}", fg="bright_black")
		if entry.evidence:
			typer.secho(f"      evidence: {', '.join(entry.evidence)}", fg="bright_black")
		if entry.settled_by is not None:
			typer.secho(f"      settled by: {entry.settled_by}", fg="bright_black")
	flagged = classification.flagged_assumptions
	if flagged:
		typer.secho(
			"\n  carried into P2 as flagged assumptions (FR-068, FR-079)",
			fg="yellow",
			bold=True,
		)
		for assumption in flagged:
			typer.echo(f"    - {assumption.statement}")
			typer.secho(f"        refuted by {assumption.refuted_by}", fg="bright_black")
	stopped = classification.returns_to_p0
	if stopped:
		typer.secho(
			f"\n  {len(stopped)} clause(s) return the pipeline to P0: FR-068's action for "
			"invalidated and deepened is to revise the clauses, not to build on them.",
			fg="red",
			bold=True,
		)


def _print_ledger(ledger: SourceLedger) -> None:
	"""The ledger, its measurements, and what a machine could check about it.

	The disconfirming count is printed as a **measurement** and never as a check
	(FR-071): a zero is the finding that the research found no argument against the
	premise, which is exactly what an operator needs to see, and a gate that failed
	there would pay a producer for inventing one.
	"""
	typer.secho(
		f"\nsource ledger v{ledger.version} for {ledger.query!r}",
		fg="cyan",
		bold=True,
	)
	typer.secho(
		f"  {len(ledger.sources)} source(s), {len(ledger.claims)} claim(s); "
		f"{len(ledger.disconfirming)} disconfirming, "
		f"{len(ledger.contradictions)} contradiction(s) (FR-071, FR-073)",
		fg="bright_black",
	)
	for source in ledger.sources:
		superseded = f" [superseded by {source.superseded_by}]" if source.superseded_by else ""
		typer.secho(
			f"  [{source.id}] {source.title}{superseded}",
			fg="cyan" if source.superseded_by is None else "bright_black",
		)
		typer.echo(
			f"      {source.type} · {source.verification.value} · "
			f"{source.confidence} · {source.posture.value}"
		)
		if source.url:
			typer.secho(f"      {source.url}", fg="bright_black")
		claims = ledger.resting_on(source.id)
		if claims:
			typer.secho(
				f"      rests on it: {', '.join(claim.id for claim in claims)}",
				fg="bright_black",
			)
	if ledger.claims:
		typer.secho("\n  claims", fg="cyan", bold=True)
		for claim in ledger.claims:
			mark = {
				ClaimKind.SUPPORTING: "supports",
				ClaimKind.DISCONFIRMING: "DISCONFIRMS",
				ClaimKind.REFUTED: "refuted",
			}[claim.kind]
			colour = "yellow" if claim.kind is ClaimKind.DISCONFIRMING else "bright_black"
			sources_text = ", ".join(claim.source_ids) if claim.source_ids else "no source"
			opinion = " (opinion)" if claim.opinion else ""
			typer.secho(
				f"    [{claim.id}] {mark}{opinion}: {claim.statement} — {sources_text}",
				fg=colour,
			)
	if ledger.contradictions:
		typer.secho(
			"\n  contradictions (the operator's to settle — FR-073)",
			fg="cyan",
			bold=True,
		)
		for found in ledger.contradictions:
			state = f"resolved: {found.resolution}" if found.resolution else "UNRESOLVED"
			typer.secho(
				f"    [{found.id}] {found.statement} — {', '.join(found.source_ids)} — {state}",
				fg="green" if found.resolution else "yellow",
			)
	unbacked = ledger.unbacked_decisions
	if unbacked:
		typer.secho(
			"\n  recorded but not allowed to decide anything on their own (FR-069, FR-074)",
			fg="yellow",
			bold=True,
		)
		for claim in unbacked:
			typer.echo(f"    [{claim.id}] {claim.statement}")


@app.command(name="verify")
def verify_contract(ctx: typer.Context, home: Path | None = _HOME_OPTION) -> None:
	"""Render a verdict on the current contract from the recorded evidence."""
	asyncio.run(_verify(_service(_home_of(ctx, home))))


async def _verify(svc: FactoryService) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	report = await svc.verify_contract(built.id)
	_print_report(report)
	if not report.is_clean:
		raise typer.Exit(code=1)


@app.command()
def claim(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	by: str = _BY_OPTION,
	note: str | None = _NOTE_OPTION,
) -> None:
	"""Record a producer's completion claim. Changes no verdict."""
	asyncio.run(_claim(_service(_home_of(ctx, home)), by, note))


async def _claim(svc: FactoryService, by: str, note: str | None) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	recorded = await svc.declare_completion(goal.id, by=by, note=note)
	typer.secho(f"\nrecorded claim {recorded.id} by {recorded.declared_by}", fg="magenta")
	typer.secho(
		"  A claim is not evidence. Re-run `sofact verify` — the verdict will be "
		"identical (FR-138: termination is not verification).",
		fg="bright_black",
	)


@app.command()
def dimensions() -> None:
	"""List the interrogation dimensions and why each exists."""
	for spec in DIMENSIONS:
		typer.secho(spec.dimension.value, fg="cyan", bold=True)
		typer.echo(f"  {spec.question}")
		typer.secho(f"  ↳ {spec.rationale}", fg="bright_black")


@app.command(name="envelope")
def show_envelope(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	show_defaults: bool = typer.Option(
		False,
		"--defaults",
		help="Print §1.3's own numbers, whether or not this deployment configured any.",
	),
) -> None:
	"""Show the §1.3 envelope, and the actuals this project measures against it (NFR-025)."""
	asyncio.run(_envelope(_service(_home_of(ctx, home)), defaults=show_defaults))


async def _envelope(svc: FactoryService, *, defaults: bool) -> None:
	configured = svc.envelope()
	if configured is None:
		typer.secho(
			"no envelope configured. §1.3's numbers are a hypothesis under test "
			"(NFR-025), so they are not applied until someone adopts them: point "
			"SOFACT_ENVELOPE at a JSON file of dimensions.",
			fg="yellow",
		)
		if not defaults:
			raise typer.Exit(code=1)
		configured = DeliveryEnvelope()
		typer.secho("\n§1.3's defaults, for reference:", fg="bright_black")
	for dimension in EnvelopeDimension:
		bound = configured.bound(dimension)
		typer.secho(f"  {dimension.value:<22} {bound.stated()}", fg="cyan")

	goal = await svc.current_goal()
	built = None if goal is None else await svc.latest_contract(goal.id)
	decomposition = None if built is None else await svc.latest_decomposition(built.id)
	specification = None if built is None else await svc.latest_specification(built.id)
	actuals = measure(
		configured,
		decomposition,
		value_hypothesis_declared=(
			None if specification is None else specification.value_hypothesis is not None
		),
		# FR-160: what the gates cost, summed over the ones that were measured.
		human_minutes=(await svc.state()).total_human_minutes,
	)
	typer.secho("\n  actuals (NFR-025)", fg="cyan", bold=True)
	for measurement in actuals.measurements:
		if measurement.actual is None:
			colour = "bright_black"
		else:
			colour = "green" if measurement.within else "red"
		typer.secho(f"    {measurement.statement}", fg=colour)
	if actuals.unmeasured:
		typer.secho(
			f"\n  {len(actuals.unmeasured)} of {len(actuals.measurements)} dimension(s) are "
			"unmeasured. Each names what would have to exist before anything could be "
			"counted; none of them is counted as satisfied.",
			fg="yellow",
		)
	if actuals.exceeded:
		typer.secho(
			"\n  over the envelope. FR-057 makes an over-scoped goal the operator's to "
			"split, not the factory's to attempt.",
			fg="red",
		)
		raise typer.Exit(code=1)


@app.command(name="deliver")
def deliver_command(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	root: Path | None = _DELIVERY_ROOT_OPTION,
	system: str | None = _SYSTEM_OPTION,
	entry_point: str | None = _ENTRY_POINT_OPTION,
	override_topology: str | None = _TOPOLOGY_OVERRIDE_OPTION,
) -> None:
	"""Render P8's delivery report (FR-117, FR-118)."""
	asyncio.run(
		_deliver(
			_service(_home_of(ctx, home)),
			root=root,
			system=system,
			entry_point=entry_point,
			override_topology=override_topology,
		)
	)


async def _deliver(
	svc: FactoryService,
	*,
	root: Path | None,
	system: str | None,
	entry_point: str | None,
	override_topology: str | None,
) -> None:
	goal = await svc.current_goal()
	if goal is None:
		typer.secho("no goal yet.", fg="yellow")
		raise typer.Exit(code=1)
	built = await svc.latest_contract(goal.id)
	if built is None:
		typer.secho("no contract yet. Run `sofact contract` first.", fg="yellow")
		raise typer.Exit(code=1)
	plan = await svc.latest_plan(built.id)
	if plan is None:
		typer.secho("no plan yet. Run `sofact plan` first.", fg="yellow")
		raise typer.Exit(code=1)
	if root is None:
		# Required rather than defaulted, because the two artefacts the factory owes are
		# the delivery, and a default would put them wherever the operator happened to be
		# standing. This is also where FR-117's fourth artefact kind gets the *declared
		# artefact root* the envelope names as the precondition for counting delivered
		# lines: before this flag there was no place a delivery was declared to be.
		typer.secho(
			"no delivery root. The factory writes the two artefacts FR-117 names that it "
			"owes (RUNBOOK.md, DELIVERY.md), so it needs to know where: pass `--root <dir>`.",
			fg="yellow",
		)
		raise typer.Exit(code=1)
	report = await svc.render_delivery(
		plan.id,
		root=root,
		system=system,
		entry_point=entry_point,
		topology_override=override_topology,
	)

	typer.secho(f"\ndelivery report {report.id}", fg="cyan", bold=True)
	typer.secho(
		f"  autonomy: {report.autonomy.name} — the delivery's, and FR-123 caps a Mode G "
		"delivery at L2 because P2, P3 and P8 are human gates",
		fg="bright_black",
	)
	typer.secho(
		f"  modules:  {report.module_autonomy.name} — what the modules sustain internally "
		"(FR-122), before that cap. Autonomous module construction inside a "
		"human-validated architecture.",
		fg="bright_black",
	)
	typer.secho(
		f"  topology: {report.topology.value} — {TOPOLOGY_ISOLATION[report.topology]}; "
		f"ceiling modifier {TOPOLOGY_MODIFIER[report.topology]:+d} (FR-019, FR-030, FR-124)",
		fg="bright_black" if report.topology_configured else "yellow",
	)
	if not report.topology_configured:
		typer.secho(
			"    no topology was declared, so the degraded T1 ceiling is in use rather "
			"than silently behaving as if it were T2 (FR-042). Set SOFACT_TOPOLOGY to "
			"T2/T3/T4, or accept the lower number deliberately.",
			fg="yellow",
		)
	typer.secho("\n  artefacts (FR-117)", fg="cyan")
	for artifact in report.artifacts:
		if artifact.present:
			typer.secho(f"    [ok  ] {artifact.kind.value}: {artifact.path}", fg="green")
		elif artifact.kind in UNPRODUCIBLE_KINDS:
			# Not a failure and not an oversight: a decision this gate is where to take.
			# Printed apart from the missing ones because the two need different responses.
			typer.secho(
				f"    [you ] {artifact.kind.value}: {artifact.missing_because}", fg="yellow"
			)
		else:
			typer.secho(f"    [MISS] {artifact.kind.value}: {artifact.missing_because}", fg="red")
	if report.undecided_artifacts:
		typer.secho(
			f"    ({len(report.undecided_artifacts)} of FR-117's four are decisions SoFact "
			"does not take: a packaging decision and a named target environment. They are "
			"reported, not failed — a check that could never pass is one you would learn "
			"to bypass.)",
			fg="bright_black",
		)

	whole = len(report.chain) - len(report.broken_links)
	typer.secho(
		f"\n  traceability (FR-117): {whole} of {len(report.chain)} clause(s) trace to a "
		"module and the step that built it",
		fg="cyan",
	)
	for link in report.broken_links:
		typer.secho(f"    gap: {link.rendered}", fg="yellow")

	typer.secho(f"\n  verified (FR-118): {len(report.verified)} clause(s)", fg="cyan")
	for clause in report.verified:
		typer.secho(f"    {clause.rendered}", fg="green")
	typer.secho(f"\n  unverified (FR-118): {len(report.unverified)} clause(s)", fg="cyan")
	for clause in report.unverified:
		typer.secho(f"    {clause.rendered}", fg="yellow")

	typer.secho(
		f"\n  unvalidated assumptions (FR-118): {len(report.unvalidated_assumptions)}",
		fg="cyan",
	)
	for assumption in report.unvalidated_assumptions:
		typer.secho(f"    {assumption.statement}", fg="yellow")
		typer.secho(f"      refuted by: {assumption.refuted_by}", fg="bright_black")

	typer.secho(f"\n  {report.value_statement}", fg="magenta", bold=True)

	typer.secho("\n  envelope actuals (FR-118, NFR-025)", fg="cyan")
	if report.envelope_actuals is None:
		typer.secho(
			"    no envelope is configured for this deployment, so nothing was measured "
			"against one. This is not the same statement as every dimension being within "
			"bounds.",
			fg="yellow",
		)
	else:
		for measurement in report.envelope_actuals.measurements:
			colour = (
				"bright_black"
				if measurement.actual is None
				else ("green" if measurement.within else "red")
			)
			typer.secho(f"    {measurement.statement}", fg=colour)

	typer.secho("\n  gate cost (FR-160)", fg="cyan")
	if not report.gate_costs:
		typer.secho(
			"    no gate has recorded what it cost, so the reviewer's budget is "
			"unmeasured rather than zero. `sofact gate --cost P2:MINUTES[:REWORK]` "
			"records one.",
			fg="yellow",
		)
	else:
		for cost in report.gate_costs:
			typer.secho(
				f"    {cost.gate.value}: {cost.human_minutes:g} human-minute(s), "
				f"{cost.rework_fraction:.0%} of the slice returned to the producer "
				f"(recorded by {cost.recorded_by})",
				fg="bright_black",
			)
		typer.secho(
			f"    total {sum(c.human_minutes for c in report.gate_costs):g} human-minute(s) "
			f"across {len(report.gate_costs)} measured gate(s); mean rework fraction "
			f"{report.rework_fraction:.3f}. §1.3's 180-600 is the budget this is measured "
			"against.",
			fg="cyan",
		)

	typer.secho("\n  checks", fg="cyan")
	for check in report.checks:
		mark = "ok  " if check.passed else "FAIL"
		typer.secho(
			f"  [{mark}] {check.name}: {check.detail}",
			fg="green" if check.passed else "red",
		)

	handed = report.handover
	typer.secho(
		f"\n  maintenance handover (FR-121): {len(handed.lanes)} lane(s), "
		f"{len(handed.inherited_oracles)} inherited oracle(s) "
		f"({len(handed.unmaintainable)} without a command)",
		fg="cyan",
	)
	# FR-158: the maintenance claim is capped at L1 and the reader is told why, on the
	# same screen as the lanes whose §13 levels are higher. Printing the lanes alone would
	# show an operator L01 at L4 and leave the cap to be discovered at the gate. The debt
	# is printed as its own number for FR-158(b): one debt figure would be read as the
	# measurable one (FR-108), and it is the unmeasurable half that bounds the claim.
	typer.secho(
		f"    evolvability debt {report.evolvability_debt:g} (FR-158, unmeasured by construction)",
		fg="yellow",
	)
	typer.secho(f"    {report.maintainability_statement}", fg="yellow")
	for lane in handed.lanes:
		typer.secho(
			f"    {lane.lane} ({lane.ceiling.name}): {lane.description} — "
			f"{len(lane.inherited_oracles)} oracle(s)",
			fg="bright_black",
		)
	typer.secho(f"    entry point: {handed.entry_point}", fg="bright_black")

	if not report.passed:
		typer.secho(
			"\n  the report has failed machine checks. FR-119 makes the deploy gate human; "
			"it cannot be passed over a failed check.",
			fg="red",
		)
		raise typer.Exit(code=1)
	typer.secho(
		f"\n  ready for the deploy gate. Run `sofact deploy --approve {report.id} --by <you>` "
		"when you have decided (FR-119).",
		fg="green",
	)


@app.command(name="deploy")
def deploy_command(
	ctx: typer.Context,
	home: Path | None = _HOME_OPTION,
	report_id: str | None = _REPORT_ID_ARGUMENT,
	approve: str | None = _APPROVE_OPTION,
	by: str = _GATE_BY_OPTION,
	note: str | None = _GATE_NOTE_OPTION,
) -> None:
	"""Present or pass the deploy gate (FR-119). Deploy is never automatic."""
	asyncio.run(
		_deploy(_service(_home_of(ctx, home)), report_id, approve=approve, by=by, note=note)
	)


async def _deploy(
	svc: FactoryService,
	report_id: str | None,
	*,
	approve: str | None,
	by: str,
	note: str | None,
) -> None:
	target = approve or report_id
	if target is None:
		report = await svc.current_delivery()
		if report is None:
			typer.secho("no delivery report yet. Run `sofact deliver` first.", fg="yellow")
			raise typer.Exit(code=1)
		target = report.id
	try:
		gate = await svc.delivery_gate(target)
	except KeyError as exc:
		typer.secho(f"cannot find that report: {exc}", fg="red")
		raise typer.Exit(code=1) from exc

	if approve is None:
		typer.secho(f"\ndeploy gate for report {gate.report_id}", fg="cyan", bold=True)
		for check in gate.checks:
			mark = "ok  " if check.passed else "FAIL"
			typer.secho(
				f"  [{mark}] {check.name}: {check.detail}",
				fg="green" if check.passed else "red",
			)
		typer.secho(f"\n  {gate.report.value_statement}", fg="magenta")
		typer.secho(
			f"\n  {len(gate.report.unverified)} clause(s) unverified and "
			f"{len(gate.report.missing_artifacts)} artefact(s) missing — stated above, and "
			"yours to weigh. FR-119 makes this a human decision, not a check.",
			fg="yellow",
		)
		if gate.failed:
			typer.secho(
				"\n  the gate cannot be passed: a failed machine check is not waivable by "
				"approval.",
				fg="red",
			)
			raise typer.Exit(code=1)
		typer.secho(
			f"\n  run `sofact deploy --approve {gate.report_id} --by <you>` to record the "
			"decision.",
			fg="bright_black",
		)
		return

	try:
		record = await svc.approve_deploy(target, by=by, note=note)
	except ValueError as exc:
		typer.secho(f"cannot approve: {exc}", fg="red")
		raise typer.Exit(code=1) from exc
	typer.secho(
		f"deploy gate for {record.report_id} passed by {record.deployed_by} at "
		f"{record.deployed_at.isoformat()}",
		fg="green",
	)
	typer.secho(
		"  recorded, not performed: §1.5 makes deploy never automatic, so this is the "
		"evidence of a human decision rather than a release SoFact carried out.",
		fg="bright_black",
	)


def main() -> None:
	"""Console-script entry point."""
	app()


if __name__ == "__main__":  # pragma: no cover
	main()
