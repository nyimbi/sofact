# 14. Markdown code fences belong to ruff, prose whitespace to markdownlint

* Status: Accepted
* Date: 2026-09-12
* Deciders: operator
* Supersedes: none
* Related: [ADR-0003](0003-the-ledger-is-append-only-and-hash-chained.md)

## Context

The symptom was a lint report that kept coming back. A hook reported
`Auto-fixed 1 issue(s) (markdownlint:1)` against `README.md` and
`docs/sources/s20-deepseek-harness.md`, the working tree showed both files modified, and
after the next `ruff format` the same bytes were rewritten again. Neither report was
wrong. Two tools had been given overlapping jurisdiction over the same bytes with no
stated owner:

* **markdownlint's MD010 (`no-hard-tabs`)** rewrites hard tabs inside fenced code blocks
  to a single space. Its `code_blocks` option defaults to **true**.
* **`ruff format`** also formats fenced Python inside Markdown — and this repo sets
  `[tool.ruff.format] indent-style = "tab"`, so it rewrites those same lines *to* tabs.

Each tool was undoing the other. Left alone the pair oscillates forever, and every turn
ends with a dirty tree that hides the real edits.

**The first diagnosis was wrong, and the way it was wrong is the reason this record
exists.** That diagnosis held that the report was spurious: `markdownlint-cli2` is not
on `PATH`, so nothing could have run, so nothing was written, so the hash "proved" the
file was unchanged. All three links were false:

1. `command -v markdownlint-cli2` failing proves nothing about whether pi-lens can run
   it. pi-lens resolves the tool on demand and was running
   **markdownlint-cli2 v0.23.2 / markdownlint v0.41.1**.
2. The hash was taken *after* the file had already been fixed. **A fix that produces no
   diff and a fix that never ran are indistinguishable from a hash.** The file was
   already in the space-indented state, so a no-op check and a phantom check looked
   identical.
3. `uv run ruff format <file>` subsequently reported `1 file reformatted` and restored
   the tabs, proving ruff does write `.md` fences — which also means the two tools were
   demonstrably fighting.

A second trap sat under the first: **markdownlint-cli2's `--config <file>` is
overridden by the nearest configuration discovered by walking up from the *linted file's*
directory.** Identical bytes linted clean in-repo and dirty under `/tmp`. Any A/B run
with `--config` alone proves nothing about the rule it names; the unit of comparison is
the config the tool actually discovers.

## Decision

**The boundary is drawn by artifact, and written down where it can be enforced.**

1. **Python fences in Markdown belong to `ruff`.** This repo mandates tab indentation,
   so its fenced Python is tab-indented and `ruff format` is the tool that keeps it so.
2. **Prose whitespace belongs to `markdownlint`.** MD010 stays enabled for everything
   that is not a code block.
3. **Implemented in the project config, not in a hook.** `.markdownlint.json` at the
   repository root sets `"MD010": {"code_blocks": false}`. Because a project-level
   config **replaces** pi-lens's bundled fallback rather than merging with it, the same
   file restates `"MD013": false` and `"MD024": {"siblings_only": true}`. A config that
   silently dropped the other two rules would have created three problems while fixing
   one.
4. **A space-indented Python fence in this repo is a real violation.** The correct
   response is to let `ruff format` fix it, never to hand-edit the fence, because the
   next `ruff format` run will revert a hand edit.
5. **The ownership rule is documented in `README.md`** next to the other conventions,
   so that re-enabling MD010 is recognisable as a regression rather than a tidy-up.

## Consequences

* The tools stop rewriting each other's bytes and a turn can end with a clean tree.
* The repo's lint cleanliness now depends on `.markdownlint.json` existing. Deleting it
  reinstates the churn, because pi-lens would fall back to its bundled config, which
  enables MD010 in code blocks. This is the cost of the fix and is recorded rather than
  hidden.
* Documentation conventions were already stricter than the default here — source-ledger
  entries carry no H1 to avoid MD025, which is unrelated to this decision but lives in
  the same file — so the root config is now the single place where Markdown policy for
  the whole repo is stated.
* The general lesson is preserved as a rule of practice: when a tool reports having
  fixed something and the tree looks unchanged, **check whether the file is already in
  the flagged state** before concluding the tool is lying.

## Evidence

* **One-variable A/B.** Same directory, same file, same bytes, only `code_blocks`
  flipped: `false` → `Summary: 0 issues in 0 files`; `true` → `Summary: 9 issues in 1
  file`, reporting `MD010/no-hard-tabs Hard tabs [Column: 1]` at lines 109–118. The A/B
  had to be run against the *discovered* config (a scratch directory, or a copy under
  `/tmp`), for the reason given above.
* **The write is real.** `uv run ruff format docs/sources/s20-deepseek-harness.md`
  reported `1 file reformatted`, after which the file's bytes matched the committed
  revision again — with the tabs restored. That is the oscillation, reproduced on
  demand.
* **The seam.** pi-lens resolves the config through
  `markdownlintConfigArgs(cwd)` at `dist/clients/tool-policy.js:2033`, which is
  `configArgsWithFallback(hasMarkdownlintConfig(cwd), ["--config"],
  "config/markdownlint/core.json")`. The discovered-config list includes
  `.markdownlint.json`. The bundled fallback is
  `{"MD013": false, "MD024": {"siblings_only": true}}` — hence the restatement in item
  3 of the decision. The `--fix` path consumes the same seam, so the project config
  governs both lint and fix.
* **Steady state.** With the config in place, `markdownlint-cli2` over
  `docs/**/*.md` and `README.md` reports `Summary: 0 issues in 0 files`, `ruff format
  --check .` reports every file already formatted, and `git status --porcelain` is
  empty at the end of a turn — the observation that the churn is gone is the observation
  that the tree stays clean without intervention.
* The config and the README paragraph are in commit `febc4ce` ("Stop markdownlint and
  ruff from rewriting each other's Markdown").
