"""FR-053, FR-055 and FR-134 — what the factory must not be able to reach.

Three requirements, one shape, and the shape is the reason they are one module rather than
three: each is a claim that the factory **cannot** do something, and a claim of that kind
cannot be verified by looking for a call. A call-site check passes the moment someone adds
one; it is a statement about today's code wearing a statement about the design's clothes.

**The claim measured here is reachability.** FR-134 says a fine-tuned model "must not
author contracts", FR-053 says one "must never be an oracle", and FR-055 says the factory
must not "set prices, accept customers, sign agreements, move money, or make commitments".
In every case the durable form of the claim is that the code path in question cannot get
to the capability at all — so the instrument walks the **transitive import closure** of
each authoring surface and reports whether anything in it can talk to a model.

That is a stronger check than it first looks and a weaker one than it could be, and both
halves are worth stating.

*Stronger*, because transitivity is the whole point: the factory's own module graph is what
decides reachability, so a helper three imports down that imports :mod:`sofact.llm` is
reported even though the surface's own file names no model. A direct-import check would
call that clean.

*Weaker*, because it establishes the **structural** half and not the identity half. FR-053
and FR-134 are about a *fine-tuned* model specifically, and this build holds no tuning
capability (FR-052 makes the target a deployment's choice, and FR-054 says the product
ships a recipe rather than weights). So there is no tuned model to name, and a check that
claimed "no tuned model is an oracle" would be a claim about a thing that does not exist.
:data:`~sofact.views.TUNED_MODEL_UNREACHABLE` is the sentence that says so, and every
report prints it beside the verdict rather than in a footnote.

**Why the closure is computed rather than asserted.** The claim "the contract-authoring
path does not import the model client" is checkable by reading one file, and it is true
today. It is also the kind of fact that rots silently — an import added at P2 for an
unrelated reason makes it false, no test fails, and the report keeps saying the surfaces
are clean. Deriving it from the tree on every run is what makes the report a measurement
instead of a comment.

**Nothing here reads the network or a file other than the package's own source.** The
instrument's subject is this package, which is the only tree whose import graph the factory
controls; a deployment's own modules are its business.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Final

from sofact.views import LedgerKind

__all__ = [
	"AUTHORSHIP_SURFACES",
	"COMMERCIAL_INTERFACES",
	"GOVERNANCE_ABSENT_REASON",
	"MODEL_REACHING_MODULES",
	"PACKAGE",
	"commercial_kinds",
	"detect_authorship",
	"governance_is_absent",
	"import_closure",
	"installed_package_root",
]

PACKAGE: Final[str] = "sofact"
"""The package whose import graph is the instrument's subject."""


def installed_package_root() -> Path:
	"""The directory of the package that is *running*, not the one in the working tree.

	Read from this module's own ``__file__``, which is the only source that cannot
	disagree with the interpreter: a check that resolved the root from the process's
	working directory would measure a checkout the factory is not executing, and report
	that tree's closures as if they were this build's. The distinction matters because
	the whole claim is about the code that would author a contract, and code that is not
	imported cannot author anything.
	"""
	return Path(__file__).resolve().parent


MODEL_REACHING_MODULES: Final[frozenset[str]] = frozenset(
	{
		"sofact.llm",
		"httpx",
		"socket",
		"ssl",
		"http",
		"urllib",
		"urllib3",
		"requests",
		"aiohttp",
		"ftplib",
		"smtplib",
		"telnetlib",
		"xmlrpc",
	}
)
"""Modules that mean *this code can talk to something outside the process*.

A named set rather than a predicate, for the reason :data:`~sofact.mutation.OPERATORS` is
a closed set: the finding is a statement about *which* module opened the door, and a
predicate that grew at run time would make two reports incomparable without saying so.

``sofact.llm`` is the factory's own client and the other entries are the standard and
third-party ways to reach a network. The set is deliberately wider than "the model
client", because the claim being measured is that the surface cannot reach a *model* —
and a module that opened a socket to something else could reach one through it.
"""

COMMERCIAL_INTERFACES: Final[frozenset[str]] = frozenset(
	{
		"stripe",
		"paypal",
		"braintree",
		"adyen",
		"squareup",
		"plaid",
		"docusign",
		"hellosign",
		"paddle",
		"chargebee",
		"recurly",
		"x402",
		"web3",
		"eth_account",
		"coinbase",
		"binance",
	}
)
"""Libraries that would mean the factory can move money or sign an agreement.

The spec names ``x402`` itself (§11.3's metered row, "x402-optional"), which is why it is
here rather than being assumed absent: a requirement that names a protocol is a requirement
whose implementation someone might reasonably add, and the check should say so on the day
they do.

**Deliberately not a substring match.** The names are matched as whole import roots, and
the marker list for :data:`_COMMERCIAL_ACT_MARKERS` is separate, because a substring rule
over module names would flag ``sofact.escape`` (which contains "pay" backwards? no — but
``sofact.specification`` contains "spec" and a careless rule over acts would flag it) and
the whole point of FR-055's check is that it fires on the five named acts and nothing else.
A gate that flags the product's own core vocabulary is a gate an operator disables.
"""

_COMMERCIAL_ACT_MARKERS: Final[tuple[str, ...]] = (
	"price",
	"pricing",
	"invoice",
	"billing",
	"customer",
	"payment",
	"payee",
	"payer",
	"subscription",
	"purchase",
	"quotation",
	"agreement",
	"revenue",
	"receipt",
	"refund",
	"checkout",
	"money",
)
"""Words that would make a ledger kind one of FR-055's five acts.

**``contract`` is absent on purpose and its absence is the load-bearing decision.** SoFact's
contract is a *verification* contract — a draft whose every stem has an oracle — and it is
the product's central artifact. A marker list containing "contract" would flag
``LedgerKind.CONTRACT_CREATED``, which is the factory doing exactly what it exists to do,
and the check would fail on every project. That is the failure mode the standing rule names:
a check scoped wider than its jurisdiction fails for reasons its operator cannot act on, and
the pressure that creates is to disable it.

``cost`` is absent for the same reason one step down: ``GATE_COST_RECORDED`` is the §1.3
envelope's token and wall-clock accounting, which is what the factory *spends*, not what it
*charges*. The two are different quantities that share a word.
"""


GOVERNANCE_ABSENT_REASON: Final[str] = (
	"no module in this tree imports a payment, e-signature or settlement provider, "
	"and the ledger's kinds are the factory's whole vocabulary of acts: goal, answer, "
	"draft, contract, evidence, verdict, claim, note, plan, capability, dispatch, "
	"integrity, integration, reuse, research, classification, source, repair, "
	"decomposition, specification, phase, cut, delivery, deploy, cost, audit, escape. "
	"FR-055's five acts — set prices, accept customers, sign agreements, move money, make "
	"commitments — have no representation, so the factory cannot perform one by any code "
	"path. This is a finding about the *absence* of a capability rather than a guard that "
	"refuses one, and the two are not the same claim: a guard can be bypassed and an "
	"absent interface cannot be called"
)
"""FR-055's finding, stated as the tree's own vocabulary rather than as a promise.

The ledger kinds are named because they *are* the factory's vocabulary of acts — FR-002
makes the log the only mutable thing in the system, so a capability the log cannot record
is a capability the factory does not have. That is a checkable statement about this tree,
which a sentence promising restraint would not be.
"""


def _module_name(path: Path, package_root: Path) -> str | None:
	"""The dotted module name for a source file, or ``None`` when it is not in the package."""
	relative = path.relative_to(package_root).with_suffix("")
	parts = [p for p in relative.parts if p != "__init__"]
	if not parts:
		return PACKAGE
	return ".".join((PACKAGE, *parts))


def _imports_of(source: str, *, module: str, is_package: bool) -> Iterator[str]:
	"""Every module name ``source`` imports, absolute and relative, one per yield.

	``ast`` rather than a text search, for the reason
	:func:`tests.ci.test_verification.test_verifier_cannot_reach_the_executor` gives: a
	docstring that *names* a module in order to explain why it is never imported would
	match a text search, and the module doing the documenting would be reported as the
	module doing the importing.

	**``from sofact import api`` yields two names, not one.** ``ast`` records that form as
	``module="sofact"`` with ``api`` among the aliases, so yielding ``node.module`` alone
	names the package initialiser and loses the submodule — and ``cli.py`` imports
	``sofact.api`` exactly that way. The closure would then stop at ``sofact/__init__.py``
	and report everything under the real submodule as unreachable, which is the fail-open
	direction on the one form that hides it. Yielding ``sofact.api`` as well costs nothing:
	:func:`_internal` resolves whichever name is a module in the index and discards the
	rest, and the discarded rest is precisely ``from sofact.views import Clause``, whose
	``sofact.views.Clause`` is not a module.

	**The relative form resolves against the importing module's own package**, which is why
	``module`` and ``is_package`` are parameters: ``from .views import X`` means
	``sofact.views`` in ``sofact/boundary.py`` and ``sofact.sub.views`` in
	``sofact/sub/thing.py``, and a scanner that assumed the top level would report a nested
	package's closure as reaching whatever ``sofact`` reaches. ``is_package`` is needed
	because ``.`` in a package's own ``__init__`` denotes the package itself rather than its
	parent.
	"""
	tree = ast.parse(source)
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			yield from (alias.name for alias in node.names)
		elif isinstance(node, ast.ImportFrom):
			if node.level:
				parts = module.split(".")
				containing = parts if is_package else parts[:-1]
				drop = node.level - 1
				base = ".".join(containing[: len(containing) - drop] if drop else containing)
			else:
				base = node.module or ""
			named = f"{base}.{node.module}" if node.level and node.module else base
			if named:
				yield named
				yield from (f"{named}.{alias.name}" for alias in node.names)
			else:
				yield from (alias.name for alias in node.names)


def _source_index(package_root: Path) -> dict[str, tuple[str, bool]]:
	"""Every module in the package, by dotted name: its source and whether it is a package."""
	index: dict[str, tuple[str, bool]] = {}
	for path in sorted(package_root.rglob("*.py")):
		name = _module_name(path, package_root)
		if name is not None:
			index[name] = (path.read_text(encoding="utf-8"), path.name == "__init__.py")
	return index


def _internal(name: str, index: dict[str, tuple[str, bool]]) -> str | None:
	"""The package module ``name`` denotes, or ``None`` when it is external."""
	return name if name in index else None


def import_closure(
	roots: Sequence[str],
	*,
	package_root: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
	"""The transitive closure of ``roots``, and which of it can reach a model.

	Returns ``(closure, reaching)``, both sorted. The roots are included in the closure:
	"the surface itself imports the client" is the same finding as any other member of the
	closure reaching it, and excluding the roots would make the shortest path invisible.

	External modules are not walked — their own imports are not this package's graph — but
	they *are* tested against :data:`MODEL_REACHING_MODULES`, because an external name is
	exactly where the reach lives. ``httpx`` is external and is the finding; walking into it
	would be reading a dependency's source to answer a question about this one.
	"""
	index = _source_index(package_root)
	assert index, f"no modules found under {package_root}, so nothing could be measured"
	missing = [name for name in roots if name not in index]
	assert not missing, f"authored surface(s) {missing} are not modules in {package_root}"

	seen: set[str] = set()
	reaching: set[str] = set()
	stack = list(roots)
	while stack:
		name = stack.pop()
		if name in seen:
			continue
		seen.add(name)
		if name in MODEL_REACHING_MODULES:
			reaching.add(name)
			continue
		entry = index.get(name)
		if entry is None:
			# External and not model-reaching: a dependency this package may use without
			# the surface being able to call out through it. Not walked, and not a finding.
			continue
		source, is_package = entry
		for imported in _imports_of(source, module=name, is_package=is_package):
			if imported in MODEL_REACHING_MODULES:
				reaching.add(imported)
				continue
			internal = _internal(imported, index)
			if internal is not None:
				stack.append(internal)
			elif imported.split(".")[0] in MODEL_REACHING_MODULES:
				reaching.add(imported.split(".")[0])
	return tuple(sorted(seen)), tuple(sorted(reaching))


AUTHORSHIP_SURFACES: Final[dict[str, tuple[str, ...]]] = {
	"contract_authoring": ("sofact.elicitation", "sofact.contract", "sofact.views"),
	"oracle_authoring": ("sofact.contract", "sofact.manufacture", "sofact.views"),
}
"""The roots of each surface, by the value of :class:`~sofact.views.AuthorshipSurface`.

``views`` is a root of both and that is not padding: the declaration types *are* where a
contract's words and an oracle's class become durable objects, so a module that could reach
a model through ``views`` could write either. Leaving it out would make the closure a
statement about three files rather than about the path.
"""


def commercial_kinds(values: Iterable[str]) -> list[str]:
	"""Which of ``values`` name one of FR-055's five acts.

	Takes the vocabulary as an argument rather than reading :class:`~sofact.views.LedgerKind`
	itself, so the rule can be held against a planted vocabulary. A test that asserted
	"the real enum has no commercial kind" would pass on any marker list at all, including
	an empty one — it is the *rule* that needs checking, and the rule is this function.
	"""
	return [
		value
		for value in values
		if any(marker in value.lower() for marker in _COMMERCIAL_ACT_MARKERS)
	]


def governance_is_absent(*, package_root: Path) -> bool:
	"""Whether nothing in the tree imports a commercial interface or names a commercial act.

	Two halves, because FR-055's five acts have two ways of arriving. The **import** half is
	the capability: a module that imported ``stripe`` could charge a card. The **kind** half
	is the vocabulary: FR-002 makes the ledger the only mutable thing in the system, so a
	:class:`~sofact.views.LedgerKind` named for an act is the factory having the act — a
	factory that can record an accepted agreement has accepted one.

	Both are needed and neither is sufficient. A tree with no payment library but a
	``PRICE_SET`` kind has the act and no implementation; a tree with a payment library and
	no kind has the capability and no place to put it. The requirement says the factory must
	not do the five things, and either half alone is a way it could.
	"""
	index = _source_index(package_root)
	assert index, f"no modules found under {package_root}, so FR-055's absence is vacuous"
	for name, (source, is_package) in index.items():
		for imported in _imports_of(source, module=name, is_package=is_package):
			if imported.split(".")[0] in COMMERCIAL_INTERFACES:
				return False
	flagged = commercial_kinds(kind.value for kind in LedgerKind)
	return not flagged


def detect_authorship(
	*, package_root: Path
) -> tuple[
	tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...],
	bool,
]:
	"""Measure both surfaces, and FR-055's absence, against one tree.

	Returns ``(findings, governance_absent)`` where each finding is
	``(surface, closure, reaching)``. The caller builds the
	:class:`~sofact.views.AuthorshipCheck` from it; this function returns plain tuples so
	the measurement can be taken without constructing a ledger entry, which is what lets a
	test hold the instrument without a project.

	``governance_absent`` is measured rather than asserted, and it is measured the same way:
	a module that imported a payment client would put that client in a closure. The check is
	over the whole package rather than over a surface, because FR-055 constrains the factory
	rather than one path through it.
	"""
	findings: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
	for surface, roots in AUTHORSHIP_SURFACES.items():
		closure, reaching = import_closure(roots, package_root=package_root)
		findings.append((surface, closure, reaching))

	return tuple(findings), governance_is_absent(package_root=package_root)
