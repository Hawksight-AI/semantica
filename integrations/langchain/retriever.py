"""
SemanticaRetriever — LangChain ``BaseRetriever`` with multi-hop GraphRAG.

Hybrid search seeds the retrieval, then graph edges are walked for ``hops``
steps so results go beyond flat vector similarity.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
        raise RuntimeError(LANGCHAIN_IMPORT_ERROR or "langchain-core not installed")
    return _Document(**kwargs)


try:
    from langchain_core.documents import Document as _Document  # type: ignore
    from langchain_core.retrievers import (
        BaseRetriever as _BaseRetriever,  # type: ignore
    )

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without langchain
    LANGCHAIN_IMPORT_ERROR = (
        "langchain-core is not installed. Install with: pip install langchain-core"
    )
    logger.debug(LANGCHAIN_IMPORT_ERROR)


def _hit_layers(hit: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Nested HybridSearch metadata and ContextGraph.query node, if present."""
    metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
    node = hit.get("node") if isinstance(hit.get("node"), dict) else {}
    return metadata, node


def _hit_id(hit: Dict[str, Any]) -> Optional[str]:
    """Graph node id, preferring metadata over a HybridSearch vector id."""
    metadata, node = _hit_layers(hit)
    return (
        hit.get("node_id")
        or metadata.get("node_id")
        or node.get("id")
        or node.get("node_id")
        or hit.get("id")
    )


def _hit_content(hit: Dict[str, Any], fallback: str = "") -> str:
    metadata, node = _hit_layers(hit)
    props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    return (
        hit.get("content")
        or hit.get("text")
        or metadata.get("content")
        or metadata.get("text")
        or props.get("content")
        or fallback
    )


def _hit_type(hit: Dict[str, Any]) -> str:
    metadata, node = _hit_layers(hit)
    return (
        hit.get("node_type")
        or hit.get("type")
        or metadata.get("node_type")
        or metadata.get("type")
        or node.get("type")
        or node.get("node_type")
        or "node"
    )


def _hit_score(hit: Dict[str, Any], default: float = 1.0) -> float:
    return float(hit.get("score") if hit.get("score") is not None else hit.get("distance") or default)


class SemanticaRetriever(_BaseRetriever):  # type: ignore[misc]
    """GraphRAG-style retriever over a Semantica ``ContextGraph``.

    Args:
        graph: A semantica.context.ContextGraph instance.
        hybrid: A semantica.vector_store.HybridSearch instance used to seed
            retrieval. If omitted, a best-effort keyword search on the graph
            is used.
        hops: Number of graph-edge expansion hops (default 2).
        top_k: Number of seed hits (default 10).
    """

    graph: Any
    hybrid: Any = None
    hops: int = 2
    top_k: int = 10

    def __init__(
        self,
        graph: Any,
        hybrid: Any = None,
        hops: int = 2,
        top_k: int = 10,
        **kwargs: Any,
    ) -> None:
        """Explicit init so the retriever works with and without langchain."""
        if LANGCHAIN_AVAILABLE:
            # BaseRetriever is a Pydantic model: pass the declared fields
            # through so validation succeeds.
            super().__init__(
                graph=graph,
                hybrid=hybrid,
                hops=hops,
                top_k=top_k,
                **kwargs,
            )
        else:
            # Without langchain-core, BaseRetriever is a plain object
            super().__init__()  # type: ignore[call-arg]
            self.graph = graph
            self.hybrid = hybrid
            self.hops = hops
            self.top_k = top_k

    def _get_relevant_documents(self, query: str, **kwargs: Any) -> List[Any]:
        """LangChain BaseRetriever entry point."""
        seed = self._seed_results(query)
        if not seed:
            return []

        # Expand each seed node through the graph
        expanded: Dict[str, Dict[str, Any]] = {}
        for hit in seed:
            node_id = _hit_id(hit)
            if not node_id:
                continue
            metadata, _ = _hit_layers(hit)
            expanded[node_id] = {
                "content": _hit_content(hit, fallback=str(node_id)),
                "node_type": _hit_type(hit),
                "score": _hit_score(hit),
                "metadata": metadata,
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
                            "metadata": {},
                        }
            except Exception as exc:  # graph expansion is best-effort
                logger.debug("graph expansion failed for %s: %s", node_id, exc)

        # Order: seed hits first (they have real scores), then neighbors.
        # Keep a deterministic id->payload list (sets are unordered — see Qodo).
        ordered_pairs: List[tuple] = []
        seen_ids = set()
        for hit in seed:
            nid = _hit_id(hit)
            if nid and nid in expanded and nid not in seen_ids:
                ordered_pairs.append((nid, expanded[nid]))
                seen_ids.add(nid)
        for nid, item in expanded.items():
            if nid not in seen_ids:
                ordered_pairs.append((nid, item))
                seen_ids.add(nid)

        return [
            _get_document(
                page_content=item["content"],
                metadata={
                    **item["metadata"],
                    "node_id": nid,
                    "node_type": item["node_type"],
                    "score": item["score"],
                },
            )
            for nid, item in ordered_pairs
        ]

    def _seed_results(self, query: str) -> List[Dict[str, Any]]:
        """Get seed results from hybrid search or a graph keyword scan."""
        if self.hybrid is not None:
            try:
                return self.hybrid.search(query, k=self.top_k)
            except Exception as exc:
                logger.debug("hybrid search failed, falling back: %s", exc)
        # Best-effort keyword scan over graph nodes (ContextGraph.query)
        try:
            return self.graph.query(query, limit=self.top_k)
        except Exception:
            return []
