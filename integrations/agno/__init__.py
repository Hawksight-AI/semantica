"""
Semantica × Agno Integration
=============================

First-class integration between the Semantica semantic intelligence stack and
the `Agno <https://github.com/agno-agi/agno>`_ agentic framework (v2 API).

Public surface
--------------
AgnoContextStore   — Graph-backed ``BaseDb`` (drop-in for ``Agent(db=…, update_memory_on_run=True)``)
AgnoKnowledgeGraph — Relational ``Knowledge`` with multi-hop GraphRAG
AgnoDecisionKit    — Agno ``Toolkit`` exposing decision-intelligence tools
AgnoKGToolkit      — Agno ``Toolkit`` exposing KG construction/query tools
AgnoSharedContext  — Team-level shared ``ContextGraph`` with per-agent scoping

Quick start
-----------
    pip install semantica[agno]

    >>> from integrations.agno import (
    ...     AgnoContextStore,
    ...     AgnoKnowledgeGraph,
    ...     AgnoDecisionKit,
    ...     AgnoKGToolkit,
    ...     AgnoSharedContext,
    ... )

Compatibility
-------------
Requires ``agno >= 2.9`` (the v2 API — agno v1 is **not** supported).  All
five classes degrade gracefully when ``agno`` is not installed — they are
still importable and carry the full Semantica API, but cannot be passed
directly to Agno ``Agent`` / ``Team`` constructors.
"""

from ._availability import AGNO_AVAILABLE, AGNO_IMPORT_ERROR
from .context_store import AgnoContextStore
from .decision_kit import AgnoDecisionKit
from .kg_toolkit import AgnoKGToolkit
from .knowledge_graph import AgnoKnowledgeGraph
from .shared_context import AgnoSharedContext

__all__ = [
    "AgnoContextStore",
    "AgnoKnowledgeGraph",
    "AgnoDecisionKit",
    "AgnoKGToolkit",
    "AgnoSharedContext",
    "AGNO_AVAILABLE",
    "AGNO_IMPORT_ERROR",
]

__version__ = "1.0.0"
