"""
SemanticaRetriever — LlamaIndex ``BaseRetriever`` with multi-hop GraphRAG.

Vector similarity seeds the retrieval, then graph edges are walked so results
go beyond flat similarity (same shape as the LangChain integration).
"""

from __future__ import annotations

from typing import Any, List, Optional

from semantica.context import ContextGraph

from . import LLAMAINDEX_AVAILABLE

if LLAMAINDEX_AVAILABLE:  # pragma: no cover - exercised with llama-index-core
    from llama_index.core.retrievers import (  # type: ignore[import-not-found]
        BaseRetriever,
    )
    from llama_index.core.schema import NodeWithScore  # type: ignore[import-not-found]
    from llama_index.core.schema import TextNode  # type: ignore[import-not-found]
else:  # pragma: no cover - exercised without llama-index-core
    BaseRetriever = object  # type: ignore[assignment, misc]
    NodeWithScore = object  # type: ignore[assignment, misc]
    TextNode = object  # type: ignore[assignment, misc]


class SemanticaRetriever(BaseRetriever):  # type: ignore[misc]
    """Retrieve nodes by hybrid search: vector seed + graph expansion."""

    def __init__(
        self,
        graph: ContextGraph,
        hybrid: Any = None,
        top_k: int = 10,
        hops: int = 2,
    ) -> None:
        self._graph = graph
        self._hybrid = hybrid
        self._top_k = top_k
        self._hops = hops

    def _retrieve(self, query_bundle: Any) -> List[NodeWithScore]:  # type: ignore[name-defined]
        query = str(query_bundle.query_str)
        nodes = self._search(query)
        if not LLAMAINDEX_AVAILABLE:
            # graceful degradation: plain dicts (llama-index-core absent)
            return [dict(n) for n in nodes]  # type: ignore[return-value]
        scored: List[Any] = []
        for i, node in enumerate(nodes):
            text = str(node.get("content") or node.get("id") or "")
            scored.append(
                NodeWithScore(  # type: ignore[attr-defined, call-arg]
                    node=TextNode(  # type: ignore[attr-defined, call-arg]
                        text=text,
                        metadata={
                            "node_id": str(node.get("id", "")),
                            "node_type": str(node.get("type", "entity")),
                            "source": "semantica-graph",
                        },
                    ),
                    score=1.0 / (i + 1),
                )
            )
        return scored

    def _search(self, query: str) -> List[dict]:
        """Seed with hybrid/vector results, then expand via graph hops."""
        seeds: List[dict] = []
        if self._hybrid is not None:
            try:
                results = self._hybrid.search(query, limit=self._top_k)
                if isinstance(results, list):
                    seeds = [r for r in results if isinstance(r, dict)]
            except Exception:
                seeds = []
        if not seeds:
            # fallback: keyword search on the graph itself
            seeds = [
                {"id": n.get("id"), "content": n.get("content")}
                for n in self._graph.find_nodes(limit=self._top_k)
            ]

        ordered: List[dict] = []
        seen: set[str] = set()
        for seed in seeds:
            nid = str(seed.get("node_id") or seed.get("id") or "")
            if not nid or nid in seen:
                continue
            seen.add(nid)
            ordered.append({"id": nid, "content": seed.get("content", "")})
            for hop in range(self._hops):
                try:
                    neighbors = self._graph.get_neighbors(nid, hops=hop + 1, limit=20)
                except Exception:
                    break
                for nb in neighbors:
                    nb_id = str(nb.get("node_id") or nb.get("id") or "")
                    if not nb_id or nb_id in seen:
                        continue
                    seen.add(nb_id)
                    ordered.append({"id": nb_id, "content": nb.get("content", "")})
        return ordered[: self._top_k]
