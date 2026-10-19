# 0074 — A module's declared class outranks its phase's tier

- **Status:** Accepted
- **Date:** 2026-10-16
- **Related:** FR-050, FR-097, FR-132, FR-133, NFR-026, §5.1, §10.1, §10.2;
  [ADR-0012](0012-the-harness-table-is-data-not-code.md),
  [ADR-0045](0045-a-topology-is-a-type-and-a-refusal-is-not-a-downgrade.md),
  [ADR-0046](0046-a-module-declares-its-budget-and-p7-measures-the-artefact.md),
  [ADR-0072](0072-the-depth-assignment-is-sofacts-and-the-model-is-the-deployments.md)

## Context

**FR-050** (§10.1) is one sentence about what a lane may name:

> No prompt, lane, or oracle may depend on model-specific behaviour beyond declared
> capability class. Lanes declare the *class* they need (reasoning-depth or throughput),
> not a model name.

**§10.2** names three classes — Throughput for high-volume low-depth work, Reasoning for
planning, failure diagnosis and adversarial hacking, Evaluation which is "ideally
deterministic tooling, not a model" — and **FR-097** makes `reasoning_class` a required
field of every module's `ModuleBudget`. So every decomposition this factory has ever
produced carries the declaration, and `DEFAULT_MODULE_BUDGET` states §7.3's own worked
example (`throughput`) for the modules a proposal does not judge.

ADR-0072 built the other half: FR-132's tier table, `TIER_PHASES`, and `resolve_model`
resolving **phase → tier → model**. What it left is the defect this record is about, and
it is the shape the repo's own lessons name — *a field written and never read*:

```console
$ rg -n 'reasoning_class' src/sofact/ | grep -v '^src/sofact/tiers.py'
src/sofact/planner.py:102:	reasoning_class=ReasoningClass.THROUGHPUT,
src/sofact/cli.py:1836:			f"{module.budget.max_loc} line(s), {module.budget.reasoning_class.value}",
src/sofact/decomposition.py:901:					f"{m.budget.reasoning_class.value}"
src/sofact/views.py:2289:	reasoning_class: ReasoningClass
```

Declaration, construction, and two print statements. A module whose budget said
`reasoning` ran on exactly the model a module saying `throughput` ran on, because nothing
turned the class into a model. The declaration was collected, gated at P3, hashed into
`decomposition_hash` so a revision of it required a fresh approval — and had no effect on
what ran.

## Decision

**`REASONING_CLASS_TIER` maps a class to a tier, and `resolve_model` consults it after
`--model` and before the phase's tier.**

```text
explicit  →  the module's declared class  →  the phase's tier  →  operator  →  default
```

The mapping is SoFact's, on `TIER_PHASES`' own argument one level down: that a
reasoning-class module needs a deeper model than a throughput-class one is a statement
about what the *classes mean*, and §10.2 defines them that way. *Which* model sits in
`deep` remains the deployment's.

`EVALUATION` routes to `deep`. §10.2 marks it "ideally deterministic tooling, not a
model", so a deployment with such tooling configures it there; giving the class its own
tier would be inventing a fourth bucket for a case FR-051 says should not be a model at
all, and routing it to `cheap` would be the worse error of the two — the class exists
precisely for work whose verdict matters.

`class_tier` is total over the enum and **asserts** rather than defaulting, for
`step_phase`'s reason: a class nobody considered landing silently in `cheap` is the
economical default becoming an unexamined one, and it fails toward an unmeasured verdict.

**The class outranks the phase because the two disagree by construction.** Every P5 step
is `BUILD`, which FR-132 puts in `cheap`; a module may declare `reasoning` because *its*
work needs depth. The phase is a statement about the pipeline — P5 is high-volume work in
general — and the module is a statement about *this* module. Reading the phase first makes
the module's declaration unobservable, which is the state this record ends.

A class whose tier the deployment named no model for **falls through to the phase's
tier**, never to another tier's model — ADR-0072's rule that an unnamed tier must not
resolve to a named one.

## Consequences

`FactoryService.dispatch_step` resolves the module **before** the adapter, because the
class it declared is an input to the model choice. `_module_for` already answered which
module a step's clauses belong to; `_module_class_for` is the same lookup returning the
budget's class. A step no single module owns — a bootstrap step, or one spanning two
modules — declared no class, and the phase's tier applies. That is the honest reading
rather than a default class invented for it, and it is asserted in both directions.

The change is visible where an operator looks for it: `DispatchRecord.model_source` reads
`tier:deep` for a reasoning-class module on a P5 step, and `sofact tiers` prints the class
table beside the phase table — because a reader of the phase table alone would conclude
every P5 step is cheap, which is exactly what the code did.

Nothing here routes *within* a tier, measures a model's quality, or reads the serving
model off the record. `{model}` remains an argv slot a spec may not use (ADR-0072's stated
limit), so a harness can accept the tag and serve another model; the table states the
decision rather than witnessing it.

## Evidence

**Three canaries, all caught.**

1. The `reasoning_class` branch deleted from `resolve_model` — 3 of 47 failed: the two-way
   routing test, the end-to-end dispatch, and the `sofact tiers` class table.
2. The call site mutated (`reasoning_class = await self._module_class_for(...)` →
   `reasoning_class = None`) — **1 of 47 failed, and it is the only test that can see it**:
   the dispatch record's own `model_source`. A routing function nothing calls is the same
   defect one layer up, and the unit tests pass under this mutation because they call
   `resolve_model` directly.
3. `class_tier`'s lookup given a `"cheap"` default — 1 of 48 failed, the guard test, and
   nothing else: the totality test checks the *table*, so only a class removed from a
   patched copy of it reaches the assert. The first two canaries ran against the 47-test
   file; the guard test was added after them, which is why this one counts 48.

All three reverted from a `cp` backup with `__pycache__` cleared, per the standing rule that
a canary that did not apply and a canary that passed look identical.
