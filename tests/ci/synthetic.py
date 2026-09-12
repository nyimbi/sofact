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

import sys
from dataclasses import asdict
from pathlib import Path

from conftest import answer_everything

from sofact.harness import HarnessSpec
from sofact.service import FactoryService
from sofact.views import GoalEntry, GoalPlan

__all__ = [
	"SCRIPT",
	"SCRIPT_NAME",
	"base_spec",
	"elicitation_to_contract",
	"kinds",
	"plan_and_service",
	"reset_calls",
	"spec_json",
	"synthetic_service",
	"write_script",
]

SCRIPT_NAME = "synthetic_harness.py"

SCRIPT = '''\
"""A real harness: writes a session record into the session dir, then exits."""

import json
import pathlib
import subprocess
import sys
import time

session_dir, session_id, mode = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
target = session_dir / f"{session_id}.jsonl"

if mode.startswith("slow"):
	if mode.startswith("slow-after-first"):
		counter = session_dir / ".calls"
		seen = int(counter.read_text()) if counter.exists() else 0
		counter.write_text(str(seen + 1))
		if seen == 0:
			sys.exit(0)
	time.sleep(30)
	sys.exit(0)

if mode.startswith("malformed"):
	target.write_text('{"seq": 1, "type": "session"\\n not json\\n', encoding="utf-8")
	sys.exit(0)

if mode.startswith("notobject"):
	target.write_text("[1, 2, 3]\\n", encoding="utf-8")
	sys.exit(0)

if "-nap-" in mode:
	# Sleep long enough that a *concurrent* wave is observably faster than a
	# sequential one. Timing is the only observable that separates the two.
	time.sleep(float(mode.split("-nap-", 1)[1]))

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
		argv=(sys.executable, str(script), "{session_dir}", "{session_id}", suffix),
		env=(("SYNTHETIC_HOME", "{session_dir}"),),
		session_glob=glob,
		session_is_zstd=zstd,
		version_argv=(sys.executable, "-c", "print('synthetic 1.2.3')"),
		completion_event="turn/end",
		completion_reason_path=("reason", "kind"),
		completion_reason_value="completed",
		usage_path=("usage", "outputTokens"),
		usage_reduce="sum",
		goal_event_types=("goal/created",),
		goal_entry=GoalEntry.PROMPT,
		supports_context_file_flag=True,
		notes="a real subprocess, not a mock",
	)


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


async def elicitation_to_contract(service: FactoryService) -> tuple[str, str]:
	"""Run P0 to completion and produce a contract. Returns ``(goal_id, contract_id)``."""
	goal = await service.start("Ship a reminder dashboard.")
	await answer_everything(service, goal.id)
	await service.draft(goal.id)
	contract = await service.contract(goal.id)
	return goal.id, contract.id


async def plan_and_service(
	home: Path, tmp_path: Path, mode: str
) -> tuple[FactoryService, GoalPlan]:
	"""A probed service plus its compiled plan. Returns ``(service, plan)``."""
	registered = synthetic_service(home, tmp_path, mode)
	await registered.probe_harness(None)
	_, contract_id = await elicitation_to_contract(registered)
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
