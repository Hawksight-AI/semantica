"""
SemanticaRetriever — GraphRAG-style retrieval over ContextGraph or AgentContext.
"""

from __future__ import annotations

import logging
from typing import Any, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional: LangChain Retriever base class
# ---------------------------------------------------------------------------
LANGCHAIN_AVAILABLE = False
_RetrieverBase: Any = object

try:
    from langchain_core.retrievers import BaseRetriever as _LCBaseRetriever
    from langchain_core.documents import Document as LCDocument

    _RetrieverBase = _LCBaseRetriever
    LANGCHAIN_AVAILABLE = True
except ImportError:
    # Minimal stand-in for Document when langchain is absent
    class LCDocument:  # type: ignore
        def __init__(self, page_content: str, metadata: dict | None = None) -> None:
            self.page_content = page_content
            self.metadata = metadata or {}


class SemanticaRetriever(_RetrieverBase):  # type: ignore[misc]
    """
    SemanticaRetriever integrates Semantica's GraphRAG intelligence into LangChain.

    Parameters
    ----------
    graph:
        An instance of ``semantica.context.ContextGraph`` or ``semantica.context.AgentContext``.
    hops:
        Maximum hops to walk the graph starting from seed nodes (default: 2).
    top_k:
        Number of seed nodes/results to retrieve from initial search (default: 10).
    """

    graph: Any
    hops: int = 2
    top_k: int = 10

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[LCDocument]:
        """
        Retrieve relevant documents using GraphRAG strategy.

        1. Perform search (via retrieve, query, etc.) to get seed nodes.
        2. Expand via graph neighbors traversal.
        3. Map each result node to a LangChain Document.
        """
        # Resolve ContextGraph instance
        kg = self.graph
        if hasattr(self.graph, "knowledge_graph") and self.graph.knowledge_graph is not None:
            kg = self.graph.knowledge_graph

        seed_nodes = []

        # 1. Retrieve seed nodes using the most advanced query method available
        if hasattr(self.graph, "retrieve"):
            try:
                retrieved = self.graph.retrieve(query, max_results=self.top_k)
                for item in retrieved:
                    if isinstance(item, dict):
                        node_id = (
                            item.get("id")
                            or item.get("metadata", {}).get("node_id")
                            or item.get("metadata", {}).get("id")
                        )
                        content = item.get("content", "")
                    else:
                        node_id = getattr(item, "id", str(item))
                        content = getattr(item, "content", str(item))
                    if node_id:
                        seed_nodes.append((node_id, content))
            except Exception as exc:
                logger.debug("Retrieval on graph failed: %s", exc)

        if not seed_nodes and hasattr(kg, "query"):
            try:
                retrieved = kg.query(query, limit=self.top_k)
                for item in retrieved:
                    node = item.get("node", {})
                    node_id = node.get("id")
                    content = node.get("content", "")
                    if node_id:
                        seed_nodes.append((node_id, content))
            except Exception as exc:
                logger.debug("Query on kg failed: %s", exc)

        if not seed_nodes and hasattr(kg, "find_nodes"):
            try:
                nodes = kg.find_nodes(limit=self.top_k)
                q_lower = query.lower()
                for node in nodes:
                    node_id = node.get("id", "")
                    content = node.get("content", "")
                    if q_lower in node_id.lower() or q_lower in content.lower():
                        seed_nodes.append((node_id, content))
            except Exception as exc:
                logger.debug("find_nodes on kg failed: %s", exc)

        # 2. Expand via graph neighbors
        expanded_docs = []
        visited = set()

        for node_id, content in seed_nodes:
            if node_id not in visited:
                visited.add(node_id)
                node_type = "Entity"
                if hasattr(kg, "find_node"):
                    node_info = kg.find_node(node_id)
                    if node_info:
                        node_type = node_info.get("type", "Entity")

                expanded_docs.append(
                    LCDocument(
                        page_content=content or node_id,
                        metadata={"node_id": node_id, "node_type": node_type},
                    )
                )

            if hasattr(kg, "get_neighbors"):
                try:
                    neighbors = kg.get_neighbors(node_id, hops=self.hops)
                    for neighbor in neighbors:
                        neighbor_id = neighbor.get("id")
                        if neighbor_id and neighbor_id not in visited:
                            visited.add(neighbor_id)
                            neighbor_content = neighbor.get("content", neighbor_id)
                            neighbor_type = neighbor.get("type", "Entity")
                            expanded_docs.append(
                                LCDocument(
                                    page_content=neighbor_content,
                                    metadata={"node_id": neighbor_id, "node_type": neighbor_type},
                                )
                            )
                except Exception as exc:
                    logger.debug("Failed walking neighbors from %s: %s", node_id, exc)

        return expanded_docs
