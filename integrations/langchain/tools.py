"""
SemanticaKGTool / SemanticaDecisionTool — LangChain ``BaseTool`` adapters
for LangChain / LangGraph agents.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Type

from pydantic import BaseModel, ConfigDict, Field

from semantica.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: LangChain core
# ---------------------------------------------------------------------------
LANGCHAIN_AVAILABLE = False
LANGCHAIN_IMPORT_ERROR: Optional[str] = None

_BaseTool: Any = object


try:
    from langchain_core.tools import BaseTool as _BaseTool  # type: ignore

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover
    LANGCHAIN_IMPORT_ERROR = (
        "langchain-core is not installed. Install with: pip install langchain-core"
    )
    logger.debug(LANGCHAIN_IMPORT_ERROR)


def _json(payload: Any) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


class QueryGraphInput(BaseModel):
    query: str = Field(..., description="Natural-language or keyword graph query")
    limit: int = Field(10, description="Maximum matching nodes to return")


class QueryDecisionsInput(BaseModel):
    category: str = Field(
        "",
        description="Keyword to search recorded decisions; empty returns insights",
    )
    limit: int = Field(10, description="Maximum results when searching by keyword")


class SemanticaKGTool(_BaseTool):  # type: ignore[misc]
    """LangChain tool for querying a Semantica ``ContextGraph``.

    Args:
        graph: A semantica.context.ContextGraph instance.

    Example:
        >>> tool = SemanticaKGTool(graph)
        >>> agent = create_react_agent(model, tools=[tool])
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "semantica_query_graph"
    description: str = (
        "Query Semantica's shared context graph with a natural-language "
        "keyword query. Returns matching entities and relationships."
    )
    args_schema: Type[BaseModel] = QueryGraphInput
    graph: Any = None

    def __init__(self, graph: Any = None, **kwargs: Any) -> None:
        if LANGCHAIN_AVAILABLE:
            super().__init__(graph=graph, **kwargs)
        else:
            super().__init__()
            self.graph = graph

    def build(self) -> Any:
        """Return this tool, or None if langchain-core is missing."""
        return self if LANGCHAIN_AVAILABLE else None

    def _run(self, query: str, limit: int = 10, **kwargs: Any) -> str:
        try:
            return _json(self.graph.query(query, limit=limit))
        except Exception as exc:
            return _json({"error": str(exc)})

    async def _arun(self, query: str, limit: int = 10, **kwargs: Any) -> str:
        return self._run(query, limit=limit)


class SemanticaDecisionTool(_BaseTool):  # type: ignore[misc]
    """LangChain tool for searching Semantica's recorded decision log.

    Args:
        graph: A semantica.context.ContextGraph instance.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "semantica_query_decisions"
    description: str = (
        "Search Semantica's recorded decision log with a keyword query. "
        "Returns decisions, rationale, and context."
    )
    args_schema: Type[BaseModel] = QueryDecisionsInput
    graph: Any = None

    def __init__(self, graph: Any = None, **kwargs: Any) -> None:
        if LANGCHAIN_AVAILABLE:
            super().__init__(graph=graph, **kwargs)
        else:
            super().__init__()
            self.graph = graph

    def build(self) -> Any:
        """Return this tool, or None if langchain-core is missing."""
        return self if LANGCHAIN_AVAILABLE else None

    def _run(self, category: str = "", limit: int = 10, **kwargs: Any) -> str:
        try:
            if category:
                return _json(self.graph.query(category, limit=limit))
            return _json(self.graph.get_decision_insights())
        except Exception as exc:
            return _json({"error": str(exc)})

    async def _arun(self, category: str = "", limit: int = 10, **kwargs: Any) -> str:
        return self._run(category=category, limit=limit)
