"""
Semantica Explorer session helpers.
"""

import base64
import json
import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional

from ..context.context_graph import ContextGraph, _resolve_edge_identity
from .search_index import GraphSearchIndex
from ..utils.skos import is_skos_hierarchy_edge, validate_skos_hierarchy

_KG_AVAILABLE = False
try:
    from ..kg import (
        CentralityCalculator,
        CommunityDetector,
        ConnectivityAnalyzer,
        GraphValidator,
        LinkPredictor,
        NodeEmbedder,
        PathFinder,
        SimilarityCalculator,
    )

    _KG_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)


class GraphSession:
    """Thread-safe session wrapper around a loaded ``ContextGraph``."""

    def __init__(
        self,
        graph: ContextGraph,
        provenance_storage_path: Optional[str] = None,
    ) -> None:
        self.graph = graph
        self._provenance_storage_path = provenance_storage_path
        self._lock = threading.RLock()
        self._search_index = GraphSearchIndex()

        self.annotations: Dict[str, Dict[str, Any]] = {}

        self._centrality: Any = None
        self._community: Any = None
        self._connectivity: Any = None
        self._path_finder: Any = None
        self._node_embedder: Any = None
        self._similarity: Any = None
        self._link_predictor: Any = None
        self._validator: Any = None
        self._provenance_manager: Any = None

        self._graph_revision: int = 0
        self._cached_embeddings: Optional[Dict[str, List[float]]] = None
        self._cached_graph_revision: int = -1
        self.rebuild_search_index()

    @classmethod
    def from_file(cls, path: str) -> "GraphSession":
        graph = ContextGraph()
        graph.load_from_file(path)
        return cls(graph)

    @staticmethod
    def _encode_cursor(value: str) -> str:
        return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")

    @staticmethod
    def _decode_cursor(cursor: Optional[str]) -> Optional[str]:
        if not cursor:
            return None
        try:
            return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        except Exception:
            return None

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _apply_cursor(items: List[str], start_after: Optional[str]) -> int:
        if not start_after:
            return 0
        for index, item in enumerate(items):
            if item == start_after:
                return index + 1
        return 0

    @staticmethod
    def _node_matches_search(node: Dict[str, Any], search: Optional[str]) -> bool:
        if not search:
            return True
        query = search.lower().strip()
        haystacks = [
            str(node.get("id", "")),
            str(node.get("type", "")),
            str(node.get("content", "")),
            json.dumps(node.get("properties", {}), default=str),
        ]
        return any(query in haystack.lower() for haystack in haystacks)

    def _node_matches_bbox(
        self,
        node: Dict[str, Any],
        bbox: Optional[tuple[float, float, float, float]],
    ) -> bool:
        if bbox is None:
            return True
        x = self._coerce_float(node.get("properties", {}).get("x"))
        y = self._coerce_float(node.get("properties", {}).get("y"))
        if x is None or y is None:
            return False
        min_x, min_y, max_x, max_y = bbox
        return min_x <= x <= max_x and min_y <= y <= max_y

    @property
    def centrality(self) -> Any:
        with self._lock:
            if self._centrality is None and _KG_AVAILABLE:
                self._centrality = CentralityCalculator()
            return self._centrality

    @property
    def community(self) -> Any:
        with self._lock:
            if self._community is None and _KG_AVAILABLE:
                self._community = CommunityDetector()
            return self._community

    @property
    def connectivity(self) -> Any:
        with self._lock:
            if self._connectivity is None and _KG_AVAILABLE:
                self._connectivity = ConnectivityAnalyzer()
            return self._connectivity

    @property
    def path_finder(self) -> Any:
        with self._lock:
            if self._path_finder is None and _KG_AVAILABLE:
                self._path_finder = PathFinder()
            return self._path_finder

    @property
    def node_embedder(self) -> Any:
        with self._lock:
            if self._node_embedder is None and _KG_AVAILABLE:
                self._node_embedder = NodeEmbedder()
            return self._node_embedder

    @property
    def similarity(self) -> Any:
        with self._lock:
            if self._similarity is None and _KG_AVAILABLE:
                self._similarity = SimilarityCalculator()
            return self._similarity

    @property
    def link_predictor(self) -> Any:
        with self._lock:
            if self._link_predictor is None and _KG_AVAILABLE:
                self._link_predictor = LinkPredictor()
            return self._link_predictor

    @property
    def validator(self) -> Any:
        with self._lock:
            if self._validator is None and _KG_AVAILABLE:
                self._validator = GraphValidator()
            return self._validator

    @property
    def provenance_manager(self) -> Any:
        with self._lock:
            if self._provenance_manager is None:
                from ..provenance import ProvenanceManager
                self._provenance_manager = ProvenanceManager(
                    storage_path=self._provenance_storage_path
                )
            return self._provenance_manager

    def set_provenance_storage_path(self, storage_path: Optional[str]) -> None:
        """Set or reconfigure the provenance storage path for this session.

        Raises a ValueError if a conflicting storage path is already configured or
        if the provenance manager has already been constructed with a different path.
        """
        with self._lock:
            if self._provenance_storage_path == storage_path:
                return
            if self._provenance_manager is not None:
                raise ValueError(
                    f"Cannot change provenance_storage_path to '{storage_path}': "
                    f"provenance_manager is already initialized with "
                    f"'{self._provenance_storage_path}'."
                )
            if self._provenance_storage_path is not None and storage_path is not None:
                raise ValueError(
                    f"Conflicting provenance_storage_path: session is already configured "
                    f"with '{self._provenance_storage_path}', cannot overwrite with '{storage_path}'."
                )
            self._provenance_storage_path = storage_path

    def normalize_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        meta.update(node.get("metadata", {}) or {})
        meta.update(node.get("properties", {}) or {})

        content = node.get("content")
        if content is None:
            content = (
                meta.get("content")
                or meta.get("text")
                or meta.get("label")
                or meta.get("name")
                or node.get("label")
                or node.get("name")
                or node.get("id", "")
            )

        valid_from = node.get("valid_from", meta.get("valid_from"))
        valid_until = node.get("valid_until", meta.get("valid_until"))

        properties = dict(meta)
        properties.setdefault("content", content)
        if valid_from is not None:
            properties["valid_from"] = valid_from
        if valid_until is not None:
            properties["valid_until"] = valid_until

        return {
            "id": str(node.get("id", "")),
            "type": str(node.get("type", "entity")),
            "content": str(content or ""),
            "properties": properties,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }

    def normalize_edge(self, edge: Dict[str, Any]) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        meta.update(edge.get("metadata", {}) or {})
        meta.update(edge.get("properties", {}) or {})

        valid_from = edge.get("valid_from", meta.get("valid_from"))
        valid_until = edge.get("valid_until", meta.get("valid_until"))
        weight = self._coerce_float(edge.get("weight"))
        if weight is None:
            weight = 1.0

        properties = dict(meta)
        if valid_from is not None:
            properties["valid_from"] = valid_from
        if valid_until is not None:
            properties["valid_until"] = valid_until

        edge_id, family_id = _resolve_edge_identity(
            source_id=str(edge.get("source", edge.get("source_id", ""))),
            target_id=str(edge.get("target", edge.get("target_id", ""))),
            edge_type=str(edge.get("type", "related_to")),
            weight=weight,
            metadata=properties,
            valid_from=valid_from,
            valid_until=valid_until,
            edge_id=(
                edge.get("id")
                or edge.get("edge_id")
                or meta.get("id")
                or meta.get("edge_id")
            ),
            family_id=(
                edge.get("familyId")
                or edge.get("family_id")
                or meta.get("familyId")
                or meta.get("family_id")
            ),
        )

        return {
            "id": edge_id,
            "familyId": family_id,
            "source": str(edge.get("source", edge.get("source_id", ""))),
            "target": str(edge.get("target", edge.get("target_id", ""))),
            "type": str(edge.get("type", "related_to")),
            "weight": weight,
            "properties": properties,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            node = self.graph.find_node(node_id)
        if node is None:
            return None
        return self.normalize_node(node)

    def paginate_nodes(
        self,
        node_type: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        cursor: Optional[str] = None,
        bbox: Optional[tuple[float, float, float, float]] = None,
    ) -> tuple[list[dict[str, Any]], int, Optional[str]]:
        with self._lock:
            node_ids: Iterable[str]
            if node_type:
                node_ids = sorted(
                    (node_id for node_id in self.graph.node_type_index.get(node_type, set()) if node_id is not None),
                    key=lambda value: str(value),
                )
            else:
                node_ids = sorted(
                    (node_id for node_id in self.graph.nodes.keys() if node_id is not None),
                    key=lambda value: str(value),
                )

            filtered_ids: List[str] = []
            normalized_by_id: Dict[str, Dict[str, Any]] = {}
            for node_id in node_ids:
                raw = self.graph.find_node(node_id)
                if raw is None:
                    continue
                normalized = self.normalize_node(raw)
                if not self._node_matches_search(normalized, search):
                    continue
                if not self._node_matches_bbox(normalized, bbox):
                    continue
                filtered_ids.append(node_id)
                normalized_by_id[node_id] = normalized

        total = len(filtered_ids)
        start_index = skip
        decoded_cursor = self._decode_cursor(cursor)
        if decoded_cursor:
            start_index = self._apply_cursor(filtered_ids, decoded_cursor)

        page_ids = filtered_ids[start_index : start_index + limit]
        next_cursor = None
        if start_index + limit < total and page_ids:
            next_cursor = self._encode_cursor(page_ids[-1])

        return [normalized_by_id[node_id] for node_id in page_ids], total, next_cursor

    def get_nodes(
        self,
        node_type: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        page, total, _ = self.paginate_nodes(
            node_type=node_type,
            search=search,
            skip=skip,
            limit=limit,
        )
        return page, total

    def iter_nodes(self, node_type: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """Yield matching nodes one at a time, in the same order as ``paginate_nodes``.

        ``paginate_nodes`` normalizes and holds the entire matching set before it
        slices out a page, so a caller that filters the result down itself cannot
        bound its cost by asking for smaller pages — it would re-pay that full
        cost per page. Streaming lets such a caller retain only what it selects
        and stop scanning as soon as it has enough.

        Only the id list is snapshotted under the lock; nodes are read one at a
        time, so a concurrent mutation can be observed mid-iteration and ids that
        disappear are skipped. ``paginate_nodes`` is the atomic alternative.
        """
        with self._lock:
            source_ids = (
                self.graph.node_type_index.get(node_type, set())
                if node_type
                else self.graph.nodes.keys()
            )
            node_ids = sorted(
                (node_id for node_id in source_ids if node_id is not None),
                key=lambda value: str(value),
            )
        for node_id in node_ids:
            with self._lock:
                raw = self.graph.find_node(node_id)
            if raw is None:
                continue
            yield self.normalize_node(raw)

    def iter_edges(self, edge_type: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """Yield matching edges one at a time, in raw graph order.

        Same rationale as ``iter_nodes``. Edge normalization derives an identity
        hash per edge, which ``paginate_edges`` pays for every matching edge (and
        then sorts) before paging; a filtering caller only needs it for the edges
        it keeps. Callers that need a stable order sort the subset they select.
        """
        with self._lock:
            raw_edges = self.graph.find_edges(edge_type=edge_type)
        for edge in raw_edges:
            normalized = self.normalize_edge(edge)
            if not normalized["source"] or not normalized["target"]:
                continue
            yield normalized

    def get_raw_counts(self) -> tuple[int, int]:
        """O(1) node/edge counts from the raw collections, with no per-item
        normalization.

        ``paginate_nodes``/``paginate_edges`` always normalize the *entire*
        matching set before applying ``limit``, so callers that need to reject
        an oversized graph before paying that cost (e.g. link prediction's DoS
        guard) should check this first rather than inspecting the ``total``
        returned by ``get_nodes``/``get_edges`` after the fact.
        """
        with self._lock:
            return len(self.graph.nodes), len(self.graph.edges)

    def paginate_edges(
        self,
        edge_type: Optional[str] = None,
        source: Optional[str] = None,
        target: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int, Optional[str]]:
        with self._lock:
            raw_edges = self.graph.find_edges(edge_type=edge_type)

        normalized_edges: List[Dict[str, Any]] = []
        keys: List[str] = []
        for edge in raw_edges:
            normalized = self.normalize_edge(edge)
            if not normalized["source"] or not normalized["target"]:
                continue
            if source and normalized["source"] != source:
                continue
            if target and normalized["target"] != target:
                continue
            edge_key = str(normalized["id"])
            normalized_edges.append(normalized)
            keys.append(edge_key)

        ordered = sorted(zip(keys, normalized_edges), key=lambda item: item[0])
        ordered_keys = [key for key, _ in ordered]
        ordered_edges = [edge for _, edge in ordered]

        total = len(ordered_edges)
        start_index = skip
        decoded_cursor = self._decode_cursor(cursor)
        if decoded_cursor:
            start_index = self._apply_cursor(ordered_keys, decoded_cursor)

        page_edges = ordered_edges[start_index : start_index + limit]
        next_cursor = None
        if start_index + limit < total and page_edges:
            last = page_edges[-1]
            next_cursor = self._encode_cursor(str(last["id"]))

        return page_edges, total, next_cursor

    def get_edges(
        self,
        edge_type: Optional[str] = None,
        source: Optional[str] = None,
        target: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        page, total, _ = self.paginate_edges(
            edge_type=edge_type,
            source=source,
            target=target,
            skip=skip,
            limit=limit,
        )
        return page, total

    def get_neighbors(self, node_id: str, depth: int = 1) -> List[Dict[str, Any]]:
        with self._lock:
            return self.graph.get_neighbors(node_id, hops=depth)

    def rebuild_search_index(self) -> None:
        with self._lock:
            normalized_nodes = [
                self.normalize_node(node.to_dict())
                for node in self.graph.nodes.values()
                if node is not None
            ]
        self._search_index.rebuild(normalized_nodes)

    def handle_graph_mutation(self, event_type: str, entity_id: str, payload: Dict[str, Any]) -> None:
        normalized_event = str(event_type or "").upper()
        if normalized_event in {
            "ADD_NODE",
            "UPDATE_NODE",
            "REMOVE_NODE",
            "DELETE_NODE",
            "ADD_EDGE",
            "UPDATE_EDGE",
            "REMOVE_EDGE",
            "DELETE_EDGE",
            "RELOAD_GRAPH",
            "RESET_GRAPH",
        }:
            with self._lock:
                self._bump_graph_revision_locked()
        if normalized_event in {"ADD_NODE", "UPDATE_NODE"}:
            normalized_node = self.normalize_node(payload or {})
            if normalized_node.get("id"):
                with self._lock:
                    self._search_index.upsert(normalized_node)
        elif normalized_event in {"REMOVE_NODE", "DELETE_NODE"}:
            with self._lock:
                self._search_index.remove(str(entity_id))
        elif normalized_event in {"RELOAD_GRAPH", "RESET_GRAPH"}:
            self.rebuild_search_index()

    def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        filters = filters or {}
        started_at = time.perf_counter()
        matches, diagnostics = self._search_index.search(query, limit=limit, filters=filters)

        normalized_results: List[Dict[str, Any]] = []
        with self._lock:
            for node_id, score in matches:
                raw_node = self.graph.find_node(node_id)
                if raw_node is None:
                    continue
                node_payload = raw_node.to_dict() if hasattr(raw_node, "to_dict") else raw_node
                normalized_results.append(
                    {
                        "node": self.normalize_node(node_payload),
                        "score": score,
                    }
                )

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.debug(
            "Explorer search query=%r limit=%s cache_hit=%s path=%s candidates=%s duration_ms=%s",
            query,
            limit,
            diagnostics.get("cache_hit"),
            diagnostics.get("path"),
            diagnostics.get("candidates"),
            duration_ms,
        )
        return normalized_results[:limit]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return self.graph.stats()

    def get_active_nodes(
        self, at_time: Optional[datetime] = None, node_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            nodes = self.graph.find_active_nodes(node_type=node_type, at_time=at_time)
        return [self.normalize_node(node) for node in nodes]

    def get_temporal_bounds(self) -> Dict[str, Optional[str]]:
        min_valid_from: Optional[datetime] = None
        max_valid_until: Optional[datetime] = None

        def _coerce_datetime(value: Any) -> Optional[datetime]:
            if value is None:
                return None
            text = str(value).strip().replace("Z", "+00:00")
            if not text:
                return None
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(f"{text}-01-01")
                except ValueError:
                    return None
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(UTC).replace(tzinfo=None)
            return parsed

        with self._lock:
            raw_nodes = list(self.graph.nodes.values())

        for raw_node in raw_nodes:
            if raw_node is None:
                continue
            node = self.normalize_node(self.graph.find_node(raw_node.node_id) or raw_node.to_dict())
            valid_from = _coerce_datetime(node.get("valid_from"))
            valid_until = _coerce_datetime(node.get("valid_until"))
            if valid_from is not None and (min_valid_from is None or valid_from < min_valid_from):
                min_valid_from = valid_from
            if valid_until is not None and (max_valid_until is None or valid_until > max_valid_until):
                max_valid_until = valid_until

        return {
            "min": min_valid_from.isoformat() if min_valid_from is not None else None,
            "max": max_valid_until.isoformat() if max_valid_until is not None else None,
        }

    def add_annotation(self, annotation: Dict[str, Any]) -> str:
        ann_id = str(uuid.uuid4())
        annotation["annotation_id"] = ann_id
        annotation["created_at"] = datetime.now(UTC).isoformat()
        with self._lock:
            self.annotations[ann_id] = annotation
        return ann_id

    def get_annotation(self, annotation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.annotations.get(annotation_id)

    def get_annotations(self, node_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            anns = list(self.annotations.values())
        if node_id:
            anns = [ann for ann in anns if ann.get("node_id") == node_id]
        return anns

    def delete_annotation(self, annotation_id: str) -> bool:
        with self._lock:
            return self.annotations.pop(annotation_id, None) is not None

    def _bump_graph_revision_locked(self) -> None:
        self._graph_revision += 1
        self._cached_embeddings = None
        self._cached_graph_revision = -1

    @staticmethod
    def _coerce_embedding_vector(value: Any) -> Optional[List[float]]:
        if isinstance(value, dict):
            for key in ("embedding", "embeddings", "vector", "values", "node2vec", "semantic"):
                nested = GraphSession._coerce_embedding_vector(value.get(key))
                if nested is not None:
                    return nested
            return None

        if not isinstance(value, (list, tuple)):
            return None

        vector: List[float] = []
        for item in value:
            try:
                vector.append(float(item))
            except (TypeError, ValueError):
                return None

        return vector if vector else None

    def get_cached_embeddings(self, force_refresh: bool = False) -> Dict[str, List[float]]:
        with self._lock:
            current_revision = self._graph_revision
            if (
                not force_refresh
                and self._cached_embeddings is not None
                and self._cached_graph_revision == current_revision
            ):
                return self._cached_embeddings
            raw_nodes = [
                node.to_dict() if hasattr(node, "to_dict") else node
                for node in self.graph.nodes.values()
                if node is not None
            ]

        embedding_keys = (
            "embedding",
            "embeddings",
            "vector",
            "node_embedding",
            "node2vec_embedding",
            "semantic_embedding",
            "reasoning_embedding",
        )

        embeddings: Dict[str, List[float]] = {}
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                continue
            normalized = self.normalize_node(raw)
            node_id = normalized.get("id")
            if not node_id:
                continue
            properties = normalized.get("properties") if isinstance(normalized.get("properties"), dict) else {}
            for key in embedding_keys:
                vector = self._coerce_embedding_vector(normalized.get(key, properties.get(key)))
                if vector is not None:
                    embeddings[str(node_id)] = vector
                    break

        with self._lock:
            if self._graph_revision == current_revision:
                self._cached_embeddings = embeddings
                self._cached_graph_revision = current_revision
            return embeddings

    def invalidate_embedding_cache(self) -> None:
        with self._lock:
            self._cached_embeddings = None
            self._cached_graph_revision = -1

    def build_graph_dict(self, node_ids: Optional[list] = None) -> dict:
        nodes, _ = self.get_nodes(skip=0, limit=999_999)
        edges, _ = self.get_edges(skip=0, limit=999_999)

        if node_ids:
            id_set = set(node_ids)
            nodes = [node for node in nodes if node.get("id") in id_set]
            edges = [
                edge
                for edge in edges
                if edge.get("source") in id_set and edge.get("target") in id_set
            ]

        return {
            "entities": [
                {
                    "id": node.get("id"),
                    "type": node.get("type", "entity"),
                    "text": node.get("content", node.get("id", "")),
                    "metadata": node.get("properties", {}),
                }
                for node in nodes
            ],
            "relationships": [
                {
                    "id": edge.get("id"),
                    "familyId": edge.get("familyId"),
                    "source": edge.get("source"),
                    "target": edge.get("target"),
                    "type": edge.get("type", "related_to"),
                    "weight": edge.get("weight", 1.0),
                    "metadata": edge.get("properties", {}),
                }
                for edge in edges
            ],
        }

    def resolve_path_edge_ids(self, path_nodes: List[str]) -> List[str]:
        if len(path_nodes) < 2:
            return []

        edge_ids: List[str] = []
        with self._lock:
            for index in range(len(path_nodes) - 1):
                source_id = path_nodes[index]
                target_id = path_nodes[index + 1]
                candidates = [
                    edge for edge in self.graph._adjacency.get(source_id, [])
                    if edge.target_id == target_id
                ]
                if not candidates:
                    continue
                candidates.sort(
                    key=lambda edge: (
                        -float(edge.weight),
                        str(edge.edge_type),
                        str(edge.edge_id),
                    )
                )
                edge_ids.append(str(candidates[0].edge_id))
        return edge_ids

    def add_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        with self._lock:
            added = self.graph.add_nodes(nodes)
            has_mutation_callback = callable(getattr(self.graph, "mutation_callback", None))
            if added and not has_mutation_callback:
                self._bump_graph_revision_locked()
        if added and not has_mutation_callback:
            self.rebuild_search_index()
        return added

    def add_edges(self, edges: List[Dict[str, Any]]) -> int:
        with self._lock:
            self.validate_skos_hierarchy(edges)
            added = self.graph.add_edges(edges)
            has_mutation_callback = callable(getattr(self.graph, "mutation_callback", None))
            if added and not has_mutation_callback:
                self._bump_graph_revision_locked()
        if added and not has_mutation_callback:
            self.rebuild_search_index()
        return added

    def validate_skos_hierarchy(self, edges: List[Dict[str, Any]]) -> None:
        """Validate new SKOS hierarchy edges against the current graph."""
        hierarchy_edges = [edge for edge in edges if is_skos_hierarchy_edge(edge)]
        if not hierarchy_edges:
            return
        existing_edges = [
            edge for edge in self.graph.find_edges() if is_skos_hierarchy_edge(edge)
        ]
        validate_skos_hierarchy(hierarchy_edges, existing_edges)

    def add_nodes_and_edges(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> tuple[int, int]:
        """
        Validate SKOS hierarchy edges upfront and add nodes and edges under lock.

        Note: This provides lock-based mutual exclusion and pre-write validation,
        not transactional rollback atomicity.
        """
        with self._lock:
            self.validate_skos_hierarchy(edges)
            nodes_added = self.graph.add_nodes(nodes)
            edges_added = self.graph.add_edges(edges)
            has_mutation_callback = callable(getattr(self.graph, "mutation_callback", None))
            if (nodes_added or edges_added) and not has_mutation_callback:
                self._bump_graph_revision_locked()
        if (nodes_added or edges_added) and not has_mutation_callback:
            self.rebuild_search_index()
        return nodes_added, edges_added

    def add_node(
        self,
        node_id: str,
        node_type: str,
        content: Optional[str] = None,
        **properties: Any,
    ) -> bool:
        with self._lock:
            added = self.graph.add_node(node_id, node_type, content=content, **properties)
            has_mutation_callback = callable(getattr(self.graph, "mutation_callback", None))
            if added and not has_mutation_callback:
                self._bump_graph_revision_locked()
        if added and not has_mutation_callback:
            normalized = self.get_node(node_id)
            if normalized is not None:
                self._search_index.upsert(normalized)
        return added

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "related_to",
        weight: float = 1.0,
        **properties: Any,
    ) -> bool:
        with self._lock:
            self.validate_skos_hierarchy([{"source": source_id, "target": target_id, "type": edge_type}])
            added = self.graph.add_edge(
                source_id,
                target_id,
                edge_type=edge_type,
                weight=weight,
                **properties,
            )
            has_mutation_callback = callable(getattr(self.graph, "mutation_callback", None))
            if added and not has_mutation_callback:
                self._bump_graph_revision_locked()
        return added
