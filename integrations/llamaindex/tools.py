"""
semantica_kg_tools() — LlamaIndex ``FunctionTool`` adapters for
``FunctionAgent`` / ``ReActAgent``.
"""

from __future__ import annotations

import json
from typing import Any, List

from semantica.context import ContextGraph

from . import LLAMAINDEX_AVAILABLE

if LLAMAINDEX_AVAILABLE:  # pragma: no cover - exercised with llama-index-core
    from llama_index.core.tools import (  # type: ignore[import-not-found]
        FunctionTool,
    )
else:  # pragma: no cover - exercised without llama-index-core
    FunctionTool = object  # type: ignore[assignment, misc]


def _graph_query(graph: ContextGraph, query: str, limit: int = 10) -> str:
    """Search the shared context graph for entities relevant to a query."""
    try:
        nodes = graph.find_nodes(limit=limit)
        return json.dumps(nodes[:limit], ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - defensive
        return json.dumps({"error": str(exc)})


def _record_decision(
    graph: ContextGraph,
    category: str,
    scenario: str,
    reasoning: str,
    outcome: str,
    confidence: float = 0.8,
) -> str:
    """Record a decision with its rationale for later retrieval."""
    try:
        decision_id = graph.record_decision(
            category=category,
            scenario=scenario,
            reasoning=reasoning,
            outcome=outcome,
            confidence=confidence,
        )
        return json.dumps({"decision_id": decision_id})
    except Exception as exc:  # pragma: no cover - defensive
        return json.dumps({"error": str(exc)})


def semantica_kg_tools(graph: ContextGraph) -> List[FunctionTool]:  # type: ignore[name-defined]
    """Build LlamaIndex FunctionTools over a Semantica graph.

    Returns an empty list when llama-index-core is unavailable (graceful
    degradation).
    """
    if not LLAMAINDEX_AVAILABLE:
        return []
    return [
        FunctionTool.from_defaults(  # type: ignore[attr-defined]
            fn=lambda query, limit=10: _graph_query(graph, query, limit),
            name="semantica_query_graph",
            description=(
                "Query Semantica's shared context graph for entities relevant "
                "to a query. Returns JSON nodes with ids, types and content."
            ),
        ),
        FunctionTool.from_defaults(  # type: ignore[attr-defined]
            fn=lambda category, scenario, reasoning, outcome, confidence=0.8: _record_decision(
                graph, category, scenario, reasoning, outcome, confidence
            ),
            name="semantica_record_decision",
            description=(
                "Record a decision with category, scenario, reasoning and "
                "outcome for later retrieval by Semantica's reasoning layer."
            ),
        ),
    ]
