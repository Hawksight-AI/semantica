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

# Tracks whether the last graph initialisation successfully loaded the
# configured SEMANTICA_KG_PATH file.  When True (or no path was configured)
# mutation handlers are allowed to save.  When False an existing file failed
# to load; saving would overwrite the original data with an empty graph, so
# persistence is blocked until the process is restarted with a readable file.
_load_ok: bool = True


def get_graph() -> Any:
    """
    Return the shared ContextGraph instance, creating it on first call.

    The graph is created with advanced_analytics=True so all centrality,
    community-detection, and embedding features are available.
    """
    global _graph, _load_ok
    if _graph is None:
        from semantica.context import ContextGraph

        _graph = ContextGraph(advanced_analytics=True)
        _load_ok = True  # default: safe to persist

        kg_path = os.environ.get("SEMANTICA_KG_PATH", "").strip()
        if kg_path and os.path.exists(kg_path):
            # Only attempt to load if the file has content.  An empty file
            # means the path was just created (e.g. a fresh tempfile) and
            # should be treated as "start with empty graph" rather than a
            # corrupt-file failure.
            if os.path.getsize(kg_path) > 0:
                try:
                    _graph.load_from_file(kg_path)
                    log.info("Graph loaded from %s", kg_path)
                except Exception as exc:
                    log.warning(
                        "Could not load graph from %s: %s — persistence disabled "
                        "to protect existing data; restart the server to retry.",
                        kg_path, exc,
                    )
                    _load_ok = False  # do not overwrite the original file

    return _graph


def is_persistence_safe() -> bool:
    """Return True when it is safe to write mutations back to SEMANTICA_KG_PATH.

    Returns False after a failed load so that mutation handlers do not
    overwrite the original (possibly intact) file with a fresh empty graph.
    """
    return _load_ok


def reset_graph() -> None:
    """Reset the singleton (mainly useful in tests)."""
    global _graph, _load_ok
    _graph = None
    _load_ok = True
