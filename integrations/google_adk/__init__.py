"""
Google ADK integration for Semantica.

Google ADK is an optional dependency. The integration can be imported
without google-adk installed, but ADK-specific functionality requires it.
"""

from __future__ import annotations

try:
    import google.adk  # noqa: F401

    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False


from .kg_tools import (
    extract_entities,
    extract_relations,
    add_to_graph,
    query_graph,
    semantica_kg_tools,
)

from .decision_tools import (
    record_decision,
    query_decisions,
    semantica_decision_tools,
)

from .session_service import SemanticaSessionService


__version__ = "0.1.0"


__all__ = [
    "ADK_AVAILABLE",
    "__version__",
    "extract_entities",
    "extract_relations",
    "add_to_graph",
    "query_graph",
    "semantica_kg_tools",
    "record_decision",
    "query_decisions",
    "semantica_decision_tools",
    "SemanticaSessionService",
]