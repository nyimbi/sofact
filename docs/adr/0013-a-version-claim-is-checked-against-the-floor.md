# 13. A version claim is checked against the minimum supported version

* Status: Accepted
* Date: 2026-09-12
* Deciders: operator
* Supersedes: none
* Related: [ADR-0001](0001-record-architecture-decisions.md)

## Context

`pyproject.toml` declares `requires-python = ">=3.12"`. The development virtualenv on
this machine is 3.13.11. Three configuration defects followed from that asymmetry, and
they were found together because the second and third only surfaced while verifying the
first.

1. **`pyrightconfig.json` said `"pythonVersion": "3.13"`** — the interpreter in the
   venv, not the floor in the metadata. The type checker was therefore validating the
   source against a claim no user had been given. 3.13-only syntax (a new generic
   syntax, a stdlib addition, a `typing` shortcut) type-checks clean under this setting
   while the package simultaneously advertises 3.12 support. The violation is invisible
   to the person who introduces it and appears instead as an `ImportError` on a
   supported interpreter. The checker was answering the wrong question, and answering
   it confidently.
2. **`pyproject.toml` carried a `[tool.pyright]` table.** pyright prefers
   `pyrightconfig.json` when both exist, so that table was inert — and it had drifted:
   the file that was actually read and the file that looked authoritative disagreed.
   A setting that looks authoritative and is not is worse than no setting, because it
   is the one a reader will trust.
3. **`extraPaths` listed `.venv/lib/python3.13/site-packages`.** `uv run --python 3.12`
   replaces `.venv` in place, so after the 3.12 verification run that path pointed at a
   directory that no longer existed, and the editor lost resolution of every
   third-party import. This was observed live, not hypothesised.

The first defect is the substantive one; the other two are the same mistake in a
different register — trusting the environment's state instead of the package's claim.

## Decision

**Every version-sensitive tool is configured against the minimum supported version, and
each tool has exactly one source of truth.**

1. **The checker's floor is the package's floor.** pyright
   `pythonVersion = "3.12"`, matching `requires-python = ">=3.12"`. `ruff`'s
   `target-version = "py312"` for the same reason: a linter that permits 3.13-only
   constructs is a linter that permits breaking the declared floor.
2. **One source of truth per tool.** `pyrightconfig.json` is the pyright
   configuration; the `[tool.pyright]` table was deleted rather than synchronised.
   Two files that must agree are one file that can disagree.
3. **Never hardcode the venv's `site-packages` path.** `venvPath` + `venv` let the
   tool resolve the environment, so replacing or re-creating the venv cannot leave a
   dangling path behind.
4. **The floor stays at 3.12 because it is verified, not because it is convenient.**
   The verification is to run the suite against the floor interpreter, not to assert
   the floor in prose.

## Consequences

* A 3.13-only construct now fails locally, before CI, instead of reaching a user on
  the supported floor. This is the whole point of the change.
* When the floor moves, exactly one file changes per tool, and the change is visible
  as a single decision rather than two files drifting apart.
* The dev loop gains one obligation: the floor claim is re-verified by running the
  suite under the floor interpreter (`uv run --python 3.12 pytest -q tests/ci`, then
  `uv sync --python 3.13` to restore the venv). It is recorded here because a verified
  claim that nobody re-verifies silently becomes an unverified claim.
* The `requires-python` floor remains `>=3.12` rather than being raised to match the
  venv. Raising it would have made the mismatch disappear without making the package
  work on the interpreters it claims, which is the same error with the sign flipped.

## Evidence

* The three configuration changes are in commit `94fce9a` ("Align the Python-version
  claim with what is verified"): `pyrightconfig.json` `pythonVersion` 3.13 → 3.12, the
  `[tool.pyright]` table removed from `pyproject.toml`, and the hardcoded
  `.venv/lib/python3.13/site-packages` entry dropped from `extraPaths`.
* `pyrightconfig.json` now reads `"pythonVersion": "3.12"` with `"venvPath": "."` and
  `"venv": ".venv"`, and `extraPaths` contains only `src` and `tests/ci`.
* `pyproject.toml` carries `requires-python = ">=3.12"` and
  `[tool.ruff] target-version = "py312"`; it contains no pyright configuration.
* **Measured, not asserted:** the full suite passes under Python 3.12.9 *and* under
  3.13.11 — 328 tests at the time of that measurement, 409 after the coverage work in
  `b658b90`. The floor claim is therefore verified against the floor interpreter.
* **Observed failure that motivated item 3:** replacing `.venv` with a 3.12
  environment left the hardcoded `site-packages` path pointing at a directory that no
  longer existed, which is exactly the class of breakage that `venvPath`/`venv`
  resolution does not have.
* pyright reports `0 errors, 0 warnings, 0 informations` under the corrected
  configuration, so the stricter floor did not require code changes — the source was
  already 3.12-compatible and the setting had simply not been checking it.
