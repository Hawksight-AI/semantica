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
_embedder: Optional[Any] = None
_vector_store: Optional[Any] = None


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
                _graph.load(kg_path)
                log.info("Graph loaded from %s", kg_path)
            except Exception as exc:
                log.warning("Could not load graph from %s: %s", kg_path, exc)

    return _graph


def get_embedder() -> Any:
    """
    Return the shared EmbeddingGenerator instance, creating it on first call.

    Used by the semantic retrieval tools (#1235) to embed documents and
    queries with one consistent model, so stored vectors and query
    vectors always share the same dimensionality.
    """
    global _embedder
    if _embedder is None:
        from semantica.embeddings import EmbeddingGenerator

        _embedder = EmbeddingGenerator()
        log.info(
            "Embedding generator initialised (method=%s)",
            _embedder.get_text_method(),
        )
    return _embedder


def get_vector_store() -> Any:
    """
    Return the shared VectorStore instance, creating it on first call.

    Backend selection:

    • ``SEMANTICA_VECTOR_BACKEND`` — one of VectorStore.SUPPORTED_BACKENDS
      (default: ``inmemory``).  The ``sqlite`` backend additionally
      requires ``SEMANTICA_VECTOR_DB_PATH``.
    • ``SEMANTICA_VECTOR_PATH`` — a *directory* previously written by
      ``VectorStore.save()``.  If it exists, the store is loaded from it
      on start.  Note this is a directory, unlike SEMANTICA_KG_PATH which
      is a single JSON file.
    """
    global _vector_store
    if _vector_store is None:
        from semantica.vector_store import VectorStore

        backend = os.environ.get("SEMANTICA_VECTOR_BACKEND", "inmemory").strip().lower()
        config: dict = {}
        if backend == "sqlite":
            db_path = os.environ.get("SEMANTICA_VECTOR_DB_PATH", "").strip()
            if not db_path:
                raise ValueError(
                    "SEMANTICA_VECTOR_BACKEND=sqlite requires "
                    "SEMANTICA_VECTOR_DB_PATH to point at the database file"
                )
            config["db_path"] = db_path
        if backend in ("inmemory", "sqlite", "faiss", "pgvector"):
            # These backends need an explicit dimension; VectorStore
            # defaults to 768, which does not match the default embedding
            # model (all-MiniLM-L6-v2 = 384, hash fallback = 128).  Always
            # derive it from the embedder so store and queries stay
            # consistent.
            config["dimension"] = get_embedder().text_embedder.get_embedding_dimension()

        store = VectorStore(backend=backend, config=config)

        vector_path = os.environ.get("SEMANTICA_VECTOR_PATH", "").strip()
        if vector_path and os.path.isdir(vector_path):
            try:
                store.load(vector_path)
                log.info("Vector store loaded from %s", vector_path)
            except Exception as exc:
                log.warning("Could not load vector store from %s: %s", vector_path, exc)

        _vector_store = store
        log.info("Vector store initialised (backend=%s)", backend)
    return _vector_store


def reset_vector_store() -> None:
    """Reset the vector store singleton (mainly useful in tests)."""
    global _vector_store
    _vector_store = None


def reset_graph() -> None:
    """Reset the singleton (mainly useful in tests)."""
    global _graph
    _graph = None
