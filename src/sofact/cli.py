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

from sofact import __version__
from sofact.contract import ground_truth_debt, unexecutable_clauses
from sofact.elicitation import DIMENSIONS
from sofact.harness import HarnessBinaryMissing, HarnessSpec, load_specs
from sofact.llm import LlmClient
from sofact.service import FactoryService, refuted_steps, resolve_tools
from sofact.views import (
	ClauseKind,
	DispatchRecord,
	GoalPlan,
	GoalStyle,
	HarnessProfile,
	IntegrityOutcome,
	ProbeOutcome,
	SpecificationDraft,
	StepOutcome,
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


def _service(home: Path | None) -> FactoryService:
	return FactoryService(home=home, llm=LlmClient(), specs=_configured_specs())


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
			),
		)
	else:
		records = await svc.dispatch_plan(
			plan.id,
			name=harness,
			workspace=workdir,
			model=model,
			tools=resolved_tools,
			max_steps=max_steps,
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
	if record.note and record.outcome is StepOutcome.NOT_DISPATCHED:
		# For a step that never ran, the note *is* the fact: without it the operator sees
		# `not_dispatched` and no reason, and a refusal whose reason is invisible is
		# indistinguishable from a bug.
		typer.secho(f"      {record.note}", fg="red")
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


def main() -> None:
	"""Console-script entry point."""
	app()


if __name__ == "__main__":  # pragma: no cover
	main()
