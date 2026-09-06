from __future__ import annotations

import threading
from typing import Any, Dict

# Shared between kg_tools.py and decision_tools.py so that a ContextGraph
# passed to both semantica_kg_tools() and semantica_decision_tools() (the
# combined-tools use case documented in the README) is locked and defaulted
# consistently across both tool sets rather than each module keeping its
# own independent registry.

_graph_locks_guard = threading.Lock()
_graph_locks: Dict[int, threading.RLock] = {}


def graph_lock(graph: Any) -> threading.RLock:
    """Return the mutation lock associated with a ContextGraph instance."""
    key = id(graph)

    with _graph_locks_guard:
        lock = _graph_locks.get(key)

        if lock is None:
            lock = threading.RLock()
            _graph_locks[key] = lock

        return lock


_default_graph: Any = None
_default_graph_lock = threading.Lock()


def get_default_graph() -> Any:
    """Create or return the cached process-local default ContextGraph."""
    global _default_graph

    if _default_graph is None:
        with _default_graph_lock:
            if _default_graph is None:
                from semantica.context import ContextGraph

                _default_graph = ContextGraph()

    return _default_graph
