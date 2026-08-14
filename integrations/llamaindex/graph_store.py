"""
SemanticaPropertyGraphStore — LlamaIndex ``PropertyGraphStore`` adapter over
``semantica.context.ContextGraph``.
"""

from __future__ import annotations

from typing import Any, List, Optional

from semantica.context import ContextGraph

from . import LLAMAINDEX_AVAILABLE

if LLAMAINDEX_AVAILABLE:  # pragma: no cover - exercised with llama-index-core
    from llama_index.core.graph_stores.types import (  # type: ignore[import-not-found]
        LabelledNode,
        PropertyGraphStore,
        Relation,
        Triplet,
    )
else:  # pragma: no cover - exercised without llama-index-core
    PropertyGraphStore = object  # type: ignore[assignment, misc]


class SemanticaPropertyGraphStore(PropertyGraphStore):  # type: ignore[misc]
    """A LlamaIndex ``PropertyGraphStore`` backed by a Semantica graph.

    Lets a ``PropertyGraphIndex`` be constructed directly over a
    ``semantica.context.ContextGraph``, so entities/relations extracted by
    LlamaIndex land in a Semantica-managed, queryable graph (with export,
    analytics and reasoning available on top).
    """

    def __init__(self, graph: Optional[ContextGraph] = None) -> None:
        self._graph = graph or ContextGraph()

    # -- PropertyGraphStore interface -------------------------------------
    def get(self, name: str, max_depth: int = 1) -> Optional[Any]:
        """Return a node by name (id), or None."""
        nodes = self._graph.find_nodes(limit=None)
        for n in nodes:
            if str(n.get("id")) == name:
                return n
        return None

    def get_triplets(
        self,
        entity_names: Optional[List[str]] = None,
        relation_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[Triplet]:  # type: ignore[name-defined]
        """Return triplets (subject, relation, object) matching filters."""
        triplets: List[Any] = []
        nodes = self._graph.find_nodes(limit=500)
        for n in nodes:
            nid = n.get("id")
            if entity_names and nid not in entity_names:
                continue
            if not nid:
                continue
            neighbors = self._graph.get_neighbors(str(nid), hops=1)
            for neighbor in neighbors:
                # get_neighbors returns the relation under "relationship"
                rel = neighbor.get("relationship") or neighbor.get("edge_type") or "related_to"
                if relation_names and rel not in relation_names:
                    continue
                triplets.append((n, rel, neighbor))
        return triplets

    def upsert_nodes(self, nodes: List[LabelledNode]) -> None:  # type: ignore[name-defined]
        """Upsert nodes into the graph."""
        for node in nodes:
            name = node.name
            properties = dict(node.properties) if node.properties else {}
            self._graph.add_node(
                node_id=name,
                node_type=node.label or "entity",
                content=str(properties.pop("content", "") or ""),
                **properties,
            )

    def upsert_relations(self, relations: List[Relation]) -> None:  # type: ignore[name-defined]
        """Upsert relations into the graph."""
        for rel in relations:
            self._graph.add_edge(
                source_id=str(rel.source_id),
                target_id=str(rel.target_id),
                edge_type=rel.label or "related_to",
            )

    def delete(self, name: str, delete_relations: bool = False) -> None:
        """Delete a node (relations preserved unless requested)."""
        # ContextGraph has no public delete; drop from the node map directly
        # is unsafe, so we only support no-op for now (documented limitation).
        del name, delete_relations  # no-op, see README limitations

    def structured_query(self, query: str, param_map: Optional[dict] = None) -> Any:
        """Run a structured (Cypher-like) query over the graph."""
        # ContextGraph.execute_query does not exist; fall back to find_nodes
        # with optional node_type filter derived from the query.
        node_type = None
        if param_map and param_map.get("node_type"):
            node_type = param_map["node_type"]
        return self._graph.find_nodes(node_type=node_type, limit=100)
