"""SoFact — an intent-to-platform software factory.

Public surface is deliberately tiny: the service, the value objects, and the ledger.
Anything else is internal and may move.
"""

from __future__ import annotations

from sofact.ledger import Ledger, LedgerCorruptError
from sofact.llm import LlmClient, LlmConfig, LlmUnavailable
from sofact.service import FactoryService, resolve_home
from sofact.views import ElicitationDimension, Goal, ProjectState, Readiness

__version__ = "0.1.0"

__all__ = [
	"ElicitationDimension",
	"FactoryService",
	"Goal",
	"Ledger",
	"LedgerCorruptError",
	"LlmClient",
	"LlmConfig",
	"LlmUnavailable",
	"ProjectState",
	"Readiness",
	"__version__",
	"resolve_home",
]
