"""
Shared graph session — lazy singleton across all tool handlers.

The graph is initialised once on first access and shared for the
lifetime of the MCP server process.  Set SEMANTICA_KG_PATH to
automatically load a persisted graph on start.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

log = logging.getLogger("semantica.mcp.session")

_graph: Optional[Any] = None


def get_graph() -> Any:
    """
    Return the shared ContextGraph instance, creating it on first call.

    The graph is created with advanced_analytics=True so all centrality,
    community-detection, and embedding features are available.
    """
    global _graph
    if _graph is None:
        from semantica.context import ContextGraph

        _graph = ContextGraph(advanced_analytics=True)

        kg_path = os.environ.get("SEMANTICA_KG_PATH", "").strip()
        if kg_path and os.path.exists(kg_path):
            try:
                _graph.load_from_file(kg_path)
                log.info("Graph loaded from %s", kg_path)
            except Exception as exc:
                log.warning("Could not load graph from %s: %s", kg_path, exc)

    return _graph


def reset_graph() -> None:
    """Reset the singleton (mainly useful in tests)."""
    global _graph
    _graph = None
