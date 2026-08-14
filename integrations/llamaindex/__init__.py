"""
Semantica × LlamaIndex Integration
==================================

First-class integration between the Semantica semantic intelligence stack and
the `LlamaIndex <https://github.com/run-llama/llama_index>`_ framework.

Provides:

- ``SemanticaPropertyGraphStore`` — a LlamaIndex ``PropertyGraphStore`` backed
  by ``semantica.context.ContextGraph`` (hybrid vector + graph retrieval).
- ``SemanticaRetriever`` — a LlamaIndex ``BaseRetriever`` combining vector
  similarity with multi-hop graph expansion.
- ``semantica_kg_tools()`` — ``FunctionTool`` adapters (KG query / decision
  recording) for ``FunctionAgent`` / ``ReActAgent``.

The package degrades gracefully: if ``llama-index-core`` is not installed,
classes remain importable but ``build``-style helpers return ``None``.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"

try:  # pragma: no cover - exercised with/without llama-index-core
    import llama_index.core  # type: ignore[import-not-found]  # noqa: F401

    LLAMAINDEX_AVAILABLE = True
except Exception:  # pragma: no cover - import may raise on missing deps
    LLAMAINDEX_AVAILABLE = False

__all__ = [
    "LLAMAINDEX_AVAILABLE",
    "SemanticaPropertyGraphStore",
    "SemanticaRetriever",
    "semantica_kg_tools",
    "__version__",
]


def __getattr__(name: str) -> Any:
    """Lazy, optional imports so the package works without llama-index-core."""
    if name in ("SemanticaPropertyGraphStore", "SemanticaRetriever", "semantica_kg_tools"):
        if not LLAMAINDEX_AVAILABLE:
            raise ImportError(
                "llama-index-core is required for the Semantica×LlamaIndex "
                "integration. Install with: pip install semantica[llamaindex]"
            )
        from . import graph_store, retriever, tools

        return {
            "SemanticaPropertyGraphStore": graph_store.SemanticaPropertyGraphStore,
            "SemanticaRetriever": retriever.SemanticaRetriever,
            "semantica_kg_tools": tools.semantica_kg_tools,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
