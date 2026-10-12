"""A real, tiny harness program, shared by the suites that need one.

This is not a test module: it holds no tests. It exists so the suites that drive the
FR-058 adapter against a real child process — ``test_harness.py`` for the wire-format
matrix, ``test_service.py`` for the dispatch and claim bookkeeping — and the suites
that need a *fully exercised* service — ``test_state.py`` for the fold — agree on what
that child *is*, rather than each growing a slightly different one.

The program is deliberately a real Python file executed by a real interpreter: the
project forbids mocks, so "the harness" has to be something the OS can schedule. The
only synthetic thing is the wire format, which is the point — a
:class:`~sofact.harness.HarnessSpec` is a declarative claim about a wire format, and the
mapping from bytes on disk back to observations is what needs checking.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from conftest import answer_everything

from sofact._uuid7 import uuid7str
from sofact.harness import HarnessSpec
from sofact.service import FactoryService
from sofact.views import (
	Assumption,
	Contract,
	GoalEntry,
	GoalPlan,
	SystemEntity,
	SystemModel,
	ValueHypothesis,
)

__all__ = [
	"SCRIPT",
	"SCRIPT_NAME",
	"a_model_for",
	"base_spec",
	"db_spec",
	"decompose_and_approve",
	"elicitation_to_contract",
	"gated_contract",
	"kinds",
	"plan_and_service",
	"reset_calls",
	"seed_store",
	"spec_json",
	"specify_and_approve",
	"synthetic_service",
	"write_script",
]

SCRIPT_NAME = "synthetic_harness.py"

SCRIPT = '''\
"""A real harness: writes a session record into the session dir, then exits."""

import json
import os
import pathlib
import re
import subprocess
import sys
import time

session_dir, session_id, mode = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
tools = sys.argv[4] if len(sys.argv) > 4 else ""
goal = sys.argv[-1]
target = session_dir / f"{session_id}.jsonl"

if mode == "export" or mode.startswith("export-"):
	# The record-source *command*: this is what a `session_command` spec names, and its
	# stdout is the record. A harness that keeps its history in a database has no file
	# for a glob to find, so the document is printed on demand instead. The three modes
	# are the three ways a command can fail to hand one over -- it refuses, it prints
	# nothing, or it prints a document that says the session failed.
	private = session_dir / "private"
	store = private / f"{session_id}.db"
	if mode == "export-refuse":
		print(f"no such session: {session_id}", file=sys.stderr)
		sys.exit(1)
	if mode == "export-silent":
		sys.exit(0)
	if not store.exists():
		print(f"no such session: {session_id}", file=sys.stderr)
		sys.exit(1)
	document = json.loads(store.read_text(encoding="utf-8"))
	if mode == "export-failed":
		document["info"]["outcome"] = "failed"
	# Indented, as `opencode session export` prints it. This is load-bearing for the
	# test, not cosmetics: compact JSON is one line, which a line-oriented reader
	# parses happily, so a fixture that printed it could not tell a whole-document
	# reader from a JSONL one. Measured output is pretty-printed.
	print(json.dumps(document, indent=2))
	sys.exit(0)

if mode.startswith("db"):
	# A harness whose history is its own store rather than a file in the session
	# directory: the record lands under private/, where no glob for a session record
	# would look, and only the export command above can produce it.
	private = session_dir / "private"
	private.mkdir(parents=True, exist_ok=True)
	(private / f"{session_id}.db").write_text(
		json.dumps(
			{
				"info": {
					"id": session_id,
					"outcome": "failed" if "fail" in mode else "succeeded",
					"tokens": {"input": 900, "output": 120, "reasoning": 0},
				},
				"messages": [{"role": "assistant", "content": "done"}],
			}
		),
		encoding="utf-8",
	)
	sys.exit(7 if "fail" in mode else 0)

if mode.startswith("shared"):
	# One fixed record path for every session: a harness whose records collide when two
	# steps run at once. It has to be a real file on disk for the probe to observe the
	# collision at all, and the mode is the negative of the CONCURRENT row.
	target = session_dir / "shared.jsonl"

if mode.startswith("badmodel"):
	# The harness's own registry rejects the identifier and it exits before writing any
	# record -- which is what a real harness does, and what makes the failure look like a
	# producer failure unless the refusal is attributed. `badmodel-once` refuses only on
	# the first call, so a *probe* can measure the refusal and the dispatch that follows
	# still has a working child to prove that nothing ran.
	counter = session_dir / ".calls"
	seen = int(counter.read_text()) if counter.exists() else 0
	counter.write_text(str(seen + 1))
	if seen == 0 or mode.startswith("badmodel-always"):
		print(
			'Error: Model "synthetic-nonesuch:latest" not found.'
			' Use --list-models to see available models.',
			file=sys.stderr,
		)
		sys.exit(1)

if mode.startswith("slow"):
	if mode.startswith("slow-after-first"):
		counter = session_dir / ".calls"
		seen = int(counter.read_text()) if counter.exists() else 0
		counter.write_text(str(seen + 1))
		if seen == 0:
			sys.exit(0)
	time.sleep(30)
	sys.exit(0)

if mode.startswith("quiet-after-first"):
	# Clean and record-writing on the first call, then slow. This is what lets a probe
	# watch a *primary* run succeed and an *extra* run fail to finish, which is the only
	# way to reach the branch where a child did no work at all.
	counter = session_dir / ".calls"
	seen = int(counter.read_text()) if counter.exists() else 0
	counter.write_text(str(seen + 1))
	if seen > 0:
		time.sleep(30)

if mode.startswith("malformed"):
	target.write_text('{"seq": 1, "type": "session"\\n not json\\n', encoding="utf-8")
	sys.exit(0)

if mode.startswith("notobject"):
	target.write_text("[1, 2, 3]\\n", encoding="utf-8")
	sys.exit(0)

if mode.startswith("silent"):
	# Exit cleanly having written nothing: a harness that reports success but leaves no
	# record is not a capability, and its exit code must not be read as one.
	sys.exit(0)

if "-nap-" in mode:
	# Sleep long enough that a *concurrent* wave is observably faster than a
	# sequential one. Timing is the only observable that separates the two.
	time.sleep(float(mode.split("-nap-", 1)[1]))

if "writes-work" in mode:
	# A producer that leaves real work in the working tree and never commits it, which
	# is the ordinary case: FR-100's branch is only a boundary if something commits what
	# the session left, and a mode that writes nothing cannot tell sealing from no-op.
	pathlib.Path("produced.py").write_text("VALUE = 1\\n", encoding="utf-8")

if "inside-marker.txt" in goal:
	# The sandbox goal: work inside the directory, then *attempt* an escape. Whether the
	# escape happens is decided by the tool set this child was handed, which is exactly how
	# a real harness confines a producer -- so it refuses for the reason a real one would,
	# rather than for a synthetic one.
	pathlib.Path("inside-marker.txt").write_text("INSIDE", encoding="utf-8")
	if "escape-marker.txt" in goal:
		if "bash" in tools:
			try:
				pathlib.Path("..", "escape-marker.txt").write_text("ESCAPED", encoding="utf-8")
			except OSError:
				pass
		else:
			print(
				f"refused: {tools!r} holds no tool that writes outside the working directory",
				file=sys.stderr,
			)

if "repair" in mode:
	# The repair loop needs a tree that changes *because a repair session ran*, and the
	# discriminator has to be something only a repair goal carries. It cannot be the
	# oracle command: every goal's verification surface names the oracle it will be
	# judged by, so keying on the command would make the *operation* step write the
	# marker and the loop would look like it converged without repairing anything.
	# "Repair N refuted clause(s)" is in the repair goal's outcome and nowhere else, so
	# it is the honest signal -- the same one an operator reading the goal would use.
	# `repair-never` is the negative: the repair session runs and leaves the tree as it
	# found it, which is what makes STILL_REFUTED and EXHAUSTED testable rather than
	# assumed.
	if "Repair" in goal and "refuted" in goal and "repair-never" not in mode:
		pathlib.Path("repair-marker.txt").write_text("REPAIRED", encoding="utf-8")

if "store-marker.txt" in goal:
	# The store-isolation differential. A harness keeps its own state somewhere, and
	# SoFact's specs redirect that somewhere with an environment variable -- which is
	# exactly the claim under test, because an isolation variable that nothing measures
	# is not a boundary. Here the variable is SYNTHETIC_HOME: set, the private store
	# goes there; unset, it falls back to the operator's HOME, which is what a real
	# harness does and what makes the control arm a live variable rather than a dud.
	# `nostore` is the harness that keeps nothing under HOME at all -- the case the
	# control arm exists to catch, where an empty HOME means the instrument is blind
	# rather than the store contained.
	pathlib.Path("store-marker.txt").write_text("STORE", encoding="utf-8")
	if "nostore" not in mode:
		private = os.environ.get("SYNTHETIC_HOME")
		if private:
			store = pathlib.Path(private) / "synthetic-store"
		else:
			store = pathlib.Path(os.environ.get("HOME", ".")) / ".synthetic"
		store.mkdir(parents=True, exist_ok=True)
		(store / f"{session_id}.json").write_text("{}", encoding="utf-8")

if "budget-marker.txt" in goal:
	# A cap is honoured when the harness was handed one and does not ignore it. The
	# uncapped run and the flag-ignoring run both do the work, which is what makes the
	# capped run's silence mean something.
	capped_and_honoured = "--cap" in sys.argv and not mode.startswith("budget-ignore")
	if not capped_and_honoured:
		pathlib.Path("budget-marker.txt").write_text("WORK", encoding="utf-8")

if "research-report.md" in goal:
	# The research protocol: the report is the artefact, and the meta carries the
	# loop's own counts. The stub variant is the measured truncation case -- a real
	# run that hit its timeout mid-loop and left a report with no sources behind.
	# No newline escapes here: inside the generated script they would be real
	# newlines, and a string literal split across lines is a SyntaxError.
	if mode.startswith("research-stub"):
		pathlib.Path("research-report.md").write_text(
			"partial: the loop was cut before any search completed", encoding="utf-8"
		)
		# No `turns` key: the truncated meta the real loop wrote carried counts for the
		# searches it managed and nothing for the model calls, so the FR-072 call cap
		# must read as *unmeasured* here rather than as zero.
		pathlib.Path("research-meta.json").write_text(
			json.dumps({"stats": {"searches": 2}, "sources": []}), encoding="utf-8"
		)
	else:
		pathlib.Path("research-report.md").write_text(
			"# report .. finding one .. ## Sources .. - https://example.com/one .. "
			"- https://example.com/two.",
			encoding="utf-8",
		)
		# `turns` is the loop's own model-call count ([S25]); `research-greedy` reports
		# more of them than any default per-clause cap allows, which is the FR-072
		# overspend case -- an artefact that says the run cost more than it was allowed.
		turns = 9 if mode.startswith("research-greedy") else 3
		pathlib.Path("research-meta.json").write_text(
			json.dumps(
				{
					"stats": {"searches": 5, "turns": turns},
					"sources": [
						{"id": 1, "title": "one", "url": "https://example.com/one"},
						{"id": 2, "title": "two", "url": "https://example.com/three"},
					],
				}
			),
			encoding="utf-8",
		)
	if "research-sources" in goal and not mode.startswith("research-stub"):
		# The FR-070 ledger: one document per source, plus the machine-readable claims.
		# Two sources, one of them vendor positioning, so the ledger exercises both the
		# posture classification and the claim-to-source edge. The listing variant
		# writes the front-matter as block lists rather than inline ones, because both
		# spellings occur in the hand-built reference ledger and only one of them is
		# what a reader would guess.
		ledger_dir = pathlib.Path("research-sources")
		ledger_dir.mkdir(exist_ok=True)
		tags = "\\n  - harness\\n  - research" if "research-sources-list" in mode else "[harness, research]"
		(ledger_dir / "s01-measured-paper.md").write_text(
			"---\\n"
			"id: S01\\n"
			"slug: measured-paper\\n"
			"title: \\"A measured paper\\"\\n"
			"type: paper\\n"
			"url: https://example.com/paper\\n"
			"retrieved: 2026-09-12\\n"
			"verification: content-verified\\n"
			"confidence: medium\\n"
			"tags: " + tags + "\\n"
			"---\\n\\n"
			"## Precis\\n\\nThe paper measures a thing and reports the number.\\n\\n"
			"## Key claims\\n\\n- the number is 42\\n\\n"
			"## Concerns / information quality\\n\\nPreprint; not peer reviewed.\\n",
			encoding="utf-8",
		)
		(ledger_dir / "s02-vendor-doc.md").write_text(
			"---\\n"
			"id: S02\\n"
			"slug: vendor-doc\\n"
			"title: \\"A vendor page\\"\\n"
			"type: product-doc\\n"
			"url: https://example.com/vendor\\n"
			"retrieved: 2026-09-12\\n"
			"verification: url-verified\\n"
			"confidence: low\\n"
			"posture: positioning\\n"
			"---\\n\\n"
			"## Precis\\n\\nThe vendor says its product does the thing.\\n\\n"
			"## Concerns / information quality\\n\\nMarketing: no measurement, no method.\\n",
			encoding="utf-8",
		)
		pathlib.Path("research-claims.json").write_text(
			json.dumps(
				{
					"claims": [
						{
							"id": "C1",
							"statement": "the mechanism works as specified",
							"kind": "supporting",
							"source_ids": ["S01"],
						},
						{
							"id": "C2",
							"statement": "the mechanism does not hold at scale",
							"kind": "disconfirming",
							"source_ids": ["S01"],
						},
						{
							"id": "C3",
							"statement": "the product is the market leader",
							"kind": "supporting",
							"source_ids": ["S02"],
						},
						{
							"id": "C4",
							"statement": "operators will accept a machine gate",
							"opinion": True,
						},
					],
					"contradictions": [
						{
							"id": "X1",
							"statement": "whether the mechanism holds at scale",
							"source_ids": ["S01", "S02"],
						}
					],
				}
			),
			encoding="utf-8",
		)
	if "research-classification.json" in goal and not mode.startswith("research-stub"):
		# FR-068: one verdict per intent clause. The clause ids come out of the goal
		# text, which is where SoFact puts them -- a producer that invented its own
		# subject list would make "every clause is classified" a check of the producer
		# against itself, so the ids here are read back rather than made up.
		listed = re.findall(r"^- ([0-9a-f-]{36}): (.*)$", goal, re.MULTILINE)
		if mode.startswith("research-classify-partial"):
			# Only the first clause, which is the "producer answered a smaller question
			# than it was asked" case.
			listed = listed[:1]
		entries: list[dict[str, object]] = []
		for index, (clause_id, statement) in enumerate(listed):
			# One variant per mode, chosen by position, so a single run exercises the
			# whole table: the four verdicts and the dangling citation.
			if mode.startswith("research-classify-invalidated") and index == 0:
				entries.append(
					{
						"clause_id": clause_id,
						"statement": statement,
						"verdict": "invalidated",
						"rationale": "the measured paper contradicts the premise",
						"evidence": ["S01"],
					}
				)
			elif mode.startswith("research-classify-deepened") and index == 0:
				entries.append(
					{
						"clause_id": clause_id,
						"statement": statement,
						"verdict": "deepened",
						"rationale": "the evidence reframes the problem as a different one",
						"evidence": ["S01"],
					}
				)
			elif mode.startswith("research-classify-unverifiable") and index == 0:
				entries.append(
					{
						"clause_id": clause_id,
						"statement": statement,
						"verdict": "unverifiable",
						"rationale": "no source addresses this either way",
						"settled_by": "a benchmark run of our own on the target corpus",
					}
				)
			elif mode.startswith("research-classify-dangling") and index == 0:
				entries.append(
					{
						"clause_id": clause_id,
						"statement": statement,
						"verdict": "validated",
						"rationale": "a source supports it, but not one this ledger holds",
						"evidence": ["S99"],
					}
				)
			else:
				entries.append(
					{
						"clause_id": clause_id,
						"statement": statement,
						"verdict": "validated",
						"rationale": "the measured paper supports the premise",
						"evidence": ["S01"],
					}
				)
		pathlib.Path("research-classification.json").write_text(
			json.dumps({"classifications": entries}), encoding="utf-8"
		)

records = [{"seq": 1, "type": "session", "data": {}}]
records.append({"seq": 2, "type": "turn/start", "data": {"turn": 1}})
records.append({"seq": 3, "type": "assistant/message", "data": {"usage": {"outputTokens": 120}}})
if mode.startswith("complete") or mode.startswith("fail-after-first"):
	records.append({"seq": 4, "type": "turn/end", "data": {"reason": {"kind": "completed"}}})
elif mode.startswith("goal"):
	records.append({"seq": 4, "type": "goal/created", "data": {}})
	records.append({"seq": 5, "type": "turn/end", "data": {"reason": {"kind": "completed"}}})
elif mode.startswith("aborted"):
	records.append({"seq": 4, "type": "turn/end", "data": {"reason": {"kind": "aborted"}}})
elif mode.startswith("compact"):
	records.append({"seq": 4, "type": "compaction", "data": {}})
	records.append({"seq": 5, "type": "turn/end", "data": {"reason": {"kind": "completed"}}})

target.write_text("".join(json.dumps(r) + "\\n" for r in records), encoding="utf-8")
if mode.endswith("-zstd") or mode.endswith("-zst"):
	subprocess.run(["zstd", "-q", "-f", str(target)], check=True)
	if mode.endswith("-zstd"):
		# zstd >= 1.5 names its output ".zst"; the spec glob promises ".jsonl.zstd",
		# because dsh names its own record and the glob must match the producer.
		compressed = target.with_suffix(target.suffix + ".zst")
		compressed.rename(target.with_suffix(target.suffix + ".zstd"))

if mode.startswith("fail-after-first"):
	# Succeed once, then fail: the only way to make a *later* wave stall, which is
	# what wave scheduling is supposed to notice (FR-142).
	counter = session_dir / ".calls"
	seen = int(counter.read_text()) if counter.exists() else 0
	counter.write_text(str(seen + 1))
	sys.exit(0 if seen == 0 else 7)

sys.exit(7 if "fail" in mode else 0)
'''


def write_script(directory: Path) -> Path:
	"""Materialise the harness inside ``directory`` and return its path."""
	script = directory / SCRIPT_NAME
	if not script.exists():
		script.write_text(SCRIPT, encoding="utf-8")
	return script


def reset_calls(session_dir: Path) -> None:
	"""Forget how many times the stateful script has run (see ``slow-after-first``).

	The counter lives in the session directory, so a probe consumes a call exactly as a
	dispatch does. A test that wants the *first dispatch* to be the first call has to say
	so, rather than assuming the probe was free.
	"""
	counter = session_dir / ".calls"
	if counter.exists():
		counter.unlink()


def base_spec(
	tmp_path: Path,
	mode: str,
	*,
	name: str = "synthetic",
	zstd: bool = False,
	zstd_ext: str = "zstd",
) -> HarnessSpec:
	"""A spec describing the shared script, with the mode baked into the child's argv.

	The glob is narrowed to the record this child actually writes, so a test can never
	pass by accidentally finding another test's session file.
	"""
	script = write_script(tmp_path)
	suffix = f"{mode}-{zstd_ext}" if zstd else mode
	glob = f"**/*{{session_id}}*.jsonl.{zstd_ext}" if zstd else "**/*{session_id}*.jsonl"
	return HarnessSpec(
		name=name,
		argv=(sys.executable, str(script), "{session_dir}", "{session_id}", suffix, "{tools}"),
		env=(("SYNTHETIC_HOME", "{session_dir}"),),
		isolation_env=("SYNTHETIC_HOME",),
		session_glob=glob,
		session_is_zstd=zstd,
		version_argv=(sys.executable, "-c", "print('synthetic 1.2.3')"),
		completion_event="turn/end",
		completion_reason_path=("data", "reason", "kind"),
		completion_reason_value="completed",
		usage_path=("data", "usage", "outputTokens"),
		usage_reduce="sum",
		goal_event_types=("goal/created",),
		goal_entry=GoalEntry.PROMPT,
		supports_context_file_flag=True,
		model_error_pattern="not found. Use --list-models",
		# Confinement by tool allowlist, exactly as the default harness confines a producer:
		# the child cannot write outside its directory without a tool that writes freely, and
		# this set has none.
		confinement_tools="read,write,edit",
		compaction_event="compaction",
		notes="a real subprocess, not a mock",
	)


def db_spec(
	tmp_path: Path,
	mode: str,
	*,
	name: str = "synthetic-db",
	command: str | None = "export",
) -> HarnessSpec:
	"""A harness whose record is a *command's stdout*, not a file it wrote.

	The glob is deliberately one that matches nothing: this spec proves the
	``session_command`` seam by making the file-shaped source unavailable, so a test
	that passes cannot be passing because a glob happened to find something.
	"""
	script = write_script(tmp_path)
	return HarnessSpec(
		name=name,
		argv=(sys.executable, str(script), "{session_dir}", "{session_id}", mode, "{tools}"),
		env=(("SYNTHETIC_HOME", "{session_dir}"),),
		session_glob="**/nothing-matches-this.jsonl",
		record_format="json",
		session_command=(
			(sys.executable, str(script), "{session_dir}", "{session_id}", command)
			if command is not None
			else ()
		),
		version_argv=(sys.executable, "-c", "print('synthetic-db 1.0.0')"),
		# No completion_event: one exported document is the session, so there is no
		# per-event envelope to name -- the same shape opencode's export has.
		completion_event=None,
		completion_reason_path=("info", "outcome"),
		completion_reason_value="succeeded",
		usage_path=("info", "tokens", "output"),
		usage_reduce="sum",
		goal_event_types=(),
		goal_entry=GoalEntry.PROMPT,
		notes="a record that arrives as a command's stdout",
	)


def seed_store(
	session_dir: Path,
	session_id: str,
	*,
	outcome: str = "succeeded",
	output_tokens: int = 120,
) -> Path:
	"""Arrange the synthetic harness's *private* store, as a real run would leave it.

	The store is the harness's own state, not SoFact's, and it lives where no record
	glob would look -- so a test of the export seam has to put it there rather than
	expecting a file. Returns the path it wrote.
	"""
	private = session_dir / "private"
	private.mkdir(parents=True, exist_ok=True)
	store = private / f"{session_id}.db"
	store.write_text(
		json.dumps(
			{
				"info": {
					"id": session_id,
					"outcome": outcome,
					"tokens": {"input": 900, "output": output_tokens, "reasoning": 0},
				},
				"messages": [{"role": "assistant", "content": "done"}],
			}
		),
		encoding="utf-8",
	)
	return store


def synthetic_service(
	home: Path,
	tmp_path: Path,
	mode: str,
	*,
	name: str = "synthetic",
) -> FactoryService:
	"""A service whose only configured harness is the shared real script."""
	spec = base_spec(tmp_path, mode, name=name)
	return FactoryService(home=home, llm=None, specs={name: spec})


async def elicitation_to_contract(
	service: FactoryService, *, commands: str | None = None
) -> tuple[str, str]:
	"""Run P0 to completion and produce a contract. Returns ``(goal_id, contract_id)``.

	``commands`` attaches one executable oracle to every clause stem. Without it every
	oracle is a *suggestion* naming no command, so there is nothing to run — the right
	default for tests about planning, and the wrong one for tests about verification.
	"""
	goal = await service.start("Ship a reminder dashboard.")
	await answer_everything(service, goal.id)
	await service.draft(goal.id)
	contract = await service.contract(goal.id, commands=commands)
	return goal.id, contract.id


def a_model_for(contract: Contract) -> SystemModel:
	"""The system model an operator would declare for the synthetic contract.

	One entity per clause, each linked to the clause it came from, so the FR-081
	reference check has a real one-to-one link to compare rather than a set that happens
	to intersect. This is not the machine inventing a model — the model is an operator
	artefact (FR-078) and this helper stands in for the operator — but it is *derived*
	rather than hand-written so it cannot drift out of step with the contract it is a
	model of, which is the drift FR-084 exists to prevent.
	"""
	entities = tuple(
		SystemEntity(
			name=_entity_name(clause.statement, index),
			description=clause.statement,
			clause_ids=(clause.id,),
		)
		for index, clause in enumerate(contract.clauses)
	)
	return SystemModel(entities=entities)


def _entity_name(statement: str, index: int) -> str:
	"""A stable, unique entity name taken from a clause's own opening words.

	Uniqueness is by index rather than by hope: two clauses opening with the same three
	words would otherwise collide, and a model with two entities of one name is a model
	whose references cannot be told apart.
	"""
	words = [w.strip(".,;:") for w in statement.split()[:3]]
	return f"{'-'.join(w for w in words if w) or 'entity'}-{index}"


async def specify_and_approve(
	service: FactoryService,
	contract_id: str,
	*,
	by: str = "operator",
) -> str:
	"""Take a contract through the P2 gate honestly. Returns the specification id.

	Every test that wants a decomposition has to come through here, because
	``decompose`` refuses downstream of an unapproved specification (FR-061) and the
	alternative — a test-only bypass — would leave the suite exercising a path
	production does not have.

	The operator-supplied halves — the model, one assumption, the value hypothesis — are
	supplied here rather than left empty, because FR-079 and FR-085 make them
	requirements and the gate fails without them. A helper that omitted them would make
	every downstream test a test of the refusal, and the refusal is what
	``test_specification.py`` is for.
	"""
	contract = await service.contract_by_id(contract_id)
	proposal = await service.specify(
		contract_id,
		system_model=a_model_for(contract),
		assumptions=(
			Assumption(
				id=uuid7str(),
				statement="Reminders are scheduled by the client, not by the server.",
				refuted_by="A server-side scheduler process appearing in the deployment.",
			),
		),
		value_hypothesis=ValueHypothesis(
			effect="Operators stop missing scheduled reminders.",
			beneficiary="The end user reading the dashboard.",
			refuting_instrument="Dashboard session logs showing reminders read late.",
		),
	)
	await service.approve_specification(proposal.id, by=by)
	return proposal.id


async def gated_contract(
	service: FactoryService,
	*,
	commands: str | None = None,
	by: str = "operator",
) -> tuple[str, str]:
	"""P0 through P3: a contract, specified, decomposed and approved.

	Returns ``(goal_id, contract_id)``.

	The default entry point for any test that wants to *build* something, because
	planning requires an approved decomposition (FR-061) and a test that skipped the gate
	would exercise a path production does not have. Tests about the gate itself use
	:func:`elicitation_to_contract` and assert on the refusal.
	"""
	goal_id, contract_id = await elicitation_to_contract(service, commands=commands)
	await specify_and_approve(service, contract_id, by=by)
	await decompose_and_approve(service, contract_id, by=by)
	return goal_id, contract_id


async def decompose_and_approve(
	service: FactoryService,
	contract_id: str,
	*,
	by: str = "operator",
) -> str:
	"""Take a contract through the P3 gate honestly. Returns the decomposition id.

	Every test that wants a plan has to come through here, because FR-061 forbids
	planning downstream of an unapproved gate and ``compile_plan`` enforces it. The
	alternative — a test-only bypass — would leave the whole suite exercising a path
	production does not have, which is how a gate ends up green and unused.
	"""
	proposal = await service.decompose(contract_id)
	await service.approve_decomposition(proposal.id, by=by)
	return proposal.id


async def plan_and_service(
	home: Path,
	tmp_path: Path,
	mode: str,
	*,
	commands: str | None = None,
) -> tuple[FactoryService, GoalPlan]:
	"""A probed service plus its compiled plan. Returns ``(service, plan)``."""
	registered = synthetic_service(home, tmp_path, mode)
	await registered.probe_harness(None)
	_, contract_id = await gated_contract(registered, commands=commands)
	return registered, await registered.compile_plan(contract_id)


def kinds(service: FactoryService) -> list[str]:
	"""Ledger kinds in append order, for asserting what got written down."""
	return [entry.kind.value for entry in service.ledger.entries()]


def spec_json(spec: HarnessSpec) -> dict[str, object]:
	"""The spec as a JSON-shaped mapping, for suites that configure a table from a file.

	Derived from the real spec rather than transcribed, so what a test writes is whatever
	:class:`~sofact.harness.HarnessSpec` actually holds: a field added to the dataclass
	cannot be silently left out of the writer, and the round trip through
	``HarnessSpec.from_mapping`` is then a real round trip.
	"""
	payload = asdict(spec)
	payload["goal_entry"] = spec.goal_entry.value
	return payload
