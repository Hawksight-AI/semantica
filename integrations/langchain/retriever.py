"""
SemanticaRetriever — LangChain ``BaseRetriever`` with multi-hop GraphRAG.

Hybrid search seeds the retrieval, then graph edges are walked for ``hops``
steps so results go beyond flat vector similarity.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from semantica.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: LangChain core
# ---------------------------------------------------------------------------
LANGCHAIN_AVAILABLE = False
LANGCHAIN_IMPORT_ERROR: Optional[str] = None

_BaseRetriever: Any = object
_Document: Any = None


def _get_document(**kwargs: Any) -> Any:
    """Instantiate a langchain Document lazily (keeps the import optional)."""
    if _Document is None:  # pragma: no cover - exercised only with langchain
        raise RuntimeError(
            LANGCHAIN_IMPORT_ERROR or "langchain-core not installed"
        )
    return _Document(**kwargs)


try:
    from langchain_core.documents import Document as _Document  # type: ignore
    from langchain_core.retrievers import BaseRetriever as _BaseRetriever  # type: ignore

    LANGCHAIN_AVAILABLE = True
except ImportError as exc:  # pragma: no cover - exercised only without langchain
    LANGCHAIN_IMPORT_ERROR = (
        "langchain-core is not installed. Install with: pip install langchain-core"
    )
    logger.debug(LANGCHAIN_IMPORT_ERROR)


class SemanticaRetriever(_BaseRetriever):  # type: ignore[misc]
    """GraphRAG-style retriever over a Semantica ``ContextGraph``.

    Args:
        graph: A semantica.context.ContextGraph instance.
        hybrid: A semantica.vector_store.HybridSearch instance used to seed
            retrieval. If omitted, a best-effort keyword search on the graph
            is used.
        hops: Number of graph-edge expansion hops (default 2).
        top_k: Number of seed hits (default 10).
        graph_weight: Blending weight for graph-expanded results (0-1).
    """

    graph: Any
    hybrid: Any = None
    hops: int = 2
    top_k: int = 10
    graph_weight: float = 0.5

    def _get_relevant_documents(self, query: str, **kwargs: Any) -> List[Any]:
        """LangChain BaseRetriever entry point."""
        seed = self._seed_results(query)
        if not seed:
            return []

        # Expand each seed node through the graph
        expanded: Dict[str, Dict[str, Any]] = {}
        for hit in seed:
            node_id = hit.get("node_id") or hit.get("id")
            if not node_id:
                continue
            expanded[node_id] = {
                "content": hit.get("content") or hit.get("text") or str(node_id),
                "node_type": hit.get("node_type") or hit.get("type") or "node",
                "score": float(hit.get("score") or hit.get("distance") or 1.0),
            }
            try:
                neighbors = self.graph.get_neighbors(node_id, hops=self.hops)
                for neighbor in neighbors:
                    nid = neighbor.get("node_id") or neighbor.get("id")
                    if nid and nid not in expanded:
                        expanded[nid] = {
                            "content": neighbor.get("content")
                            or neighbor.get("text")
                            or neighbor.get("name")
                            or str(nid),
                            "node_type": neighbor.get("node_type")
                            or neighbor.get("type")
                            or "node",
                            "score": float(neighbor.get("weight") or 0.5),
                        }
            except Exception as exc:  # graph expansion is best-effort
                logger.debug("graph expansion failed for %s: %s", node_id, exc)

        # Order: seed hits first (they have real scores), then neighbors
        ordered = []
        seen = set()
        for hit in seed:
            nid = hit.get("node_id") or hit.get("id")
            if nid and nid in expanded and nid not in seen:
                ordered.append(expanded[nid])
                seen.add(nid)
        for nid, item in expanded.items():
            if nid not in seen:
                ordered.append(item)
                seen.add(nid)

        return [
            _get_document(
                page_content=item["content"],
                metadata={
                    "node_id": nid,
                    "node_type": item["node_type"],
                    "score": item["score"],
                },
            )
            for nid, item in zip(seen, ordered)
        ]

    def _seed_results(self, query: str) -> List[Dict[str, Any]]:
        """Get seed results from hybrid search or a graph keyword scan."""
        if self.hybrid is not None:
            try:
                return self.hybrid.search(query, k=self.top_k)
            except Exception as exc:
                logger.debug("hybrid search failed, falling back: %s", exc)
        # Best-effort keyword scan over graph nodes
        try:
            return self.graph.search_nodes(query, limit=self.top_k)
        except Exception:
            return []
