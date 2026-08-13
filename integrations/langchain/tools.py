"""
SemanticaKGTool / SemanticaDecisionTool — LangChain ``StructuredTool`` adapters
for LangChain / LangGraph agents.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from semantica.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: LangChain core
# ---------------------------------------------------------------------------
LANGCHAIN_AVAILABLE = False
LANGCHAIN_IMPORT_ERROR: Optional[str] = None

_StructuredTool: Any = None


try:
    from langchain_core.tools import StructuredTool as _StructuredTool  # type: ignore

    LANGCHAIN_AVAILABLE = True
except ImportError as exc:  # pragma: no cover
    LANGCHAIN_IMPORT_ERROR = (
        "langchain-core is not installed. Install with: pip install langchain-core"
    )
    logger.debug(LANGCHAIN_IMPORT_ERROR)


def _run_or_raise(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a Semantica call so missing langchain raises a clear error."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not LANGCHAIN_AVAILABLE:
            raise RuntimeError(
                LANGCHAIN_IMPORT_ERROR or "langchain-core not installed"
            )
        return fn(*args, **kwargs)

    return wrapper


def _graph_query(graph: Any, query: str) -> str:
    """Best-effort natural-language / keyword query over the graph."""
    for method in ("search_nodes", "query", "search"):
        fn = getattr(graph, method, None)
        if fn is None:
            continue
        try:
            result = fn(query, limit=10) if method == "search_nodes" else fn(query)
            return json.dumps(result, default=str, ensure_ascii=False)[:4000]
        except TypeError:
            continue
        except Exception as exc:
            return f"error: {exc}"
    return "{}"


class SemanticaKGTool:
    """Build a LangChain StructuredTool for knowledge-graph operations.

    Args:
        graph: A semantica.context.ContextGraph instance.

    Example:
        >>> tool = SemanticaKGTool(graph).build()
        >>> agent = create_react_agent(model, tools=[tool])
    """

    def __init__(self, graph: Any) -> None:
        self.graph = graph

    def build(self) -> Any:
        """Return a ``langchain_core.tools.StructuredTool`` (or None if
        langchain-core is missing)."""
        if not LANGCHAIN_AVAILABLE:
            return None

        def query_graph(query: str, limit: int = 10) -> str:
            """Search the shared context graph for entities relevant to a query."""
            try:
                return json.dumps(
                    self.graph.search_nodes(query, limit=limit),
                    default=str,
                    ensure_ascii=False,
                )[:4000]
            except Exception as exc:
                return f"error: {exc}"

        def add_entity(name: str, entity_type: str = "entity", **attrs: Any) -> str:
            """Add an entity node to the context graph."""
            try:
                node = self.graph.add_node(
                    name=name, node_type=entity_type, attributes=attrs or None
                )
                return json.dumps(node, default=str)[:2000]
            except Exception as exc:
                return f"error: {exc}"

        return _StructuredTool.from_function(
            func=query_graph,
            name="semantica_query_graph",
            description=(
                "Query Semantica's shared context graph with a natural-language "
                "keyword query. Returns matching entities and relationships."
            ),
        )


class SemanticaDecisionTool:
    """Build a LangChain StructuredTool exposing decision-intelligence tools.

    Args:
        graph: A semantica.context.ContextGraph instance.
    """

    def __init__(self, graph: Any) -> None:
        self.graph = graph

    def build(self) -> Any:
        """Return a ``langchain_core.tools.StructuredTool`` (or None if
        langchain-core is missing)."""
        if not LANGCHAIN_AVAILABLE:
            return None

        def query_decisions(query: str, limit: int = 10) -> str:
            """Search recorded decisions and their rationale in Semantica."""
            try:
                return json.dumps(
                    self.graph.search_decisions(query, limit=limit),
                    default=str,
                    ensure_ascii=False,
                )[:4000]
            except Exception as exc:
                return f"error: {exc}"

        return _StructuredTool.from_function(
            func=query_decisions,
            name="semantica_query_decisions",
            description=(
                "Search Semantica's recorded decision log with a keyword query. "
                "Returns decisions, rationale, and context."
            ),
        )
