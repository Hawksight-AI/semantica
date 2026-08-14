"""
Semantica × CrewAI Integration
==============================

First-class integration between the Semantica semantic intelligence stack and
the `CrewAI <https://github.com/crewAIInc/crewAI>`_ agentic framework.

Public surface
--------------
SemanticaKGTool         — CrewAI ``BaseTool`` exposing KG construction/query actions
SemanticaDecisionTool   — CrewAI ``BaseTool`` exposing decision-intelligence actions
SemanticaKnowledgeSource— CrewAI ``BaseKnowledgeSource`` giving crews graph knowledge

Quick start
-----------
    pip install semantica[crewai]

    >>> from integrations.crewai import (
    ...     SemanticaKGTool,
    ...     SemanticaDecisionTool,
    ...     SemanticaKnowledgeSource,
    ... )

Compatibility
-------------
Requires ``crewai >= 0.80.0``.  All three classes degrade gracefully when
``crewai`` is not installed — they are still importable and carry the full
Semantica API, but cannot be passed to ``Crew`` / ``Agent`` constructors.
"""

from ._availability import CREWAI_AVAILABLE, CREWAI_IMPORT_ERROR
from .decision_tool import SemanticaDecisionTool
from .kg_tool import SemanticaKGTool
from .knowledge_source import SemanticaKnowledgeSource

__all__ = [
    "SemanticaKGTool",
    "SemanticaDecisionTool",
    "SemanticaKnowledgeSource",
    "CREWAI_AVAILABLE",
    "CREWAI_IMPORT_ERROR",
]

__version__ = "0.1.0"
