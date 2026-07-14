"""
Context Graph Implementation

In-memory GraphStore implementation for building and querying context graphs
from conversations and entities with advanced analytics integration.

Core Features:
    - In-memory GraphStore implementation
    - Entity and relationship extraction from conversations
    - BFS-based neighbor discovery
    - Type-based indexing
    - Export to dictionary format
    - Decision tracking integration

Comprehensive Decision Management:
    - Decision Recording: Store decisions with full context and metadata
    - Precedent Search: Find similar decisions using hybrid search algorithms
    - Influence Analysis: Analyze decision impact and relationships
    - Causal Analysis: Trace decision causality chains
    - Policy Enforcement: Built-in policy compliance checking
    - Advanced Analytics: Comprehensive decision insights

KG Algorithm Integration:
    - Centrality Analysis: Degree, betweenness, closeness, eigenvector centrality
    - Community Detection: Modularity-based community identification
    - Node Embeddings: Node2Vec embeddings for similarity analysis
    - Path Finding: Shortest path and advanced path algorithms
    - Link Prediction: Relationship prediction between entities
    - Similarity Calculation: Multi-type similarity measures

Vector Store Integration:
    - Hybrid Search: Semantic + structural similarity
    - Custom Similarity Weights: Configurable scoring
    - Advanced Precedent Search: KG-enhanced similarity
    - Multi-Embedding Support: Multiple embedding types

Advanced Graph Analytics:
    - Node Centrality Analysis: Multiple centrality measures
    - Community Detection: Identify clusters and communities
    - Node Similarity: Content and structural similarity
    - Graph Structure Analysis: Comprehensive metrics
    - Path Analysis: Find paths and connectivity
    - Embedding Generation: Node embeddings for ML

Decision Tracking Integration:
    - Decision Storage: Store decisions with full context
    - Precedent Search: Find similar decisions using graph traversal
    - Causal Analysis: Trace decision influence
    - Decision Analytics: Analyze decision patterns
    - Influence Analysis: Decision influence scoring and analysis
    - Policy Engine: Policy enforcement and compliance checking
    - Relationship Mapping: Map decision dependencies

Enhanced Methods:
    - analyze_graph_with_kg(): Comprehensive graph analysis
    - get_node_centrality(): Get centrality measures for nodes
    - find_similar_nodes(): Find similar nodes with advanced similarity
    - record_decision(): Add decisions with context integration
    - find_precedents(): Find decision precedents
    - analyze_decision_influence(): Analyze decision influence
    - get_decision_insights(): Get comprehensive decision analytics
    - trace_decision_causality(): Trace decision causality
    - enforce_decision_policy(): Enforce decision policies
    - get_graph_metrics(): Get comprehensive statistics
    - export_graph(): Export graph in various formats

Example Usage:
    >>> from semantica.context import ContextGraph
    >>> graph = ContextGraph(advanced_analytics=True,
    ...                    centrality_analysis=True,
    ...                    community_detection=True,
    ...                    node_embeddings=True)
    >>> 
    >>> # Basic graph operations
    >>> graph.add_node("Python", type="language", properties={"popularity": "high"})
    >>> graph.add_node("Programming", type="concept")
    >>> graph.add_edge("Python", "Programming", type="related_to")
    >>> centrality = graph.get_node_centrality("Python")
    >>> similar = graph.find_similar_nodes("Python", similarity_type="content")
    >>> analysis = graph.analyze_graph_with_kg()
    >>> 
    >>> # Decision management
    >>> decision_id = graph.record_decision(
    ...     category="loan_approval",
    ...     scenario="First-time homebuyer",
    ...     reasoning="Good credit score",
    ...     outcome="approved",
    ...     confidence=0.95,
    ...     entities=["customer_123", "property_456"]
    ... )
    >>> precedents = graph.find_precedents("loan_approval", limit=5)
    >>> influence = graph.analyze_decision_influence(decision_id)
    >>> insights = graph.get_decision_insights()
    >>> causality = graph.trace_decision_causality(decision_id)

Production Use Cases:
    - Knowledge Management: Build and analyze knowledge graphs
    - Decision Support: Context graphs for decision making
    - Recommendation Systems: Graph-based recommendations
    - Social Networks: Analyze connections and influence
    - Research Networks: Map collaborations and citations
    - Financial Services: Loan approvals, fraud detection, risk assessment
    - Healthcare: Treatment decisions, policy compliance, clinical pathways
    - Legal: Case precedent analysis, decision consistency
    - Business: Workflow decisions, policy compliance, audit trails
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import threading
import itertools
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from ..utils.helpers import classify_path_distance
from .entity_linker import EntityLinker

# Optional imports for advanced features
try:
    from ..kg import (
        GraphBuilder, GraphAnalyzer, CentralityCalculator, CommunityDetector,
        PathFinder, NodeEmbedder, SimilarityCalculator, LinkPredictor,
        ConnectivityAnalyzer
    )
    KG_AVAILABLE = True
except ImportError:
    KG_AVAILABLE = False


class _CausalChain(dict):
    """Dict response that still iterates over hops for legacy callers."""

    def __iter__(self):
        return iter(self.get("hops", []))


def _parse_iso_dt(value: str) -> Optional[datetime]:
    """Parse an ISO datetime string into a tz-naive UTC datetime.

    Supported formats (in priority order):
        - Year-only shorthand:  "1990"  → "1990-01-01"
        - Date-only:            "1990-06-15"
        - Full ISO (with tz):   "1990-06-15T00:00:00+00:00" / "...Z"
        - Full ISO (naive):     "1990-06-15T00:00:00"

    Returns None on failure; callers must treat the node as Always-Active.
    """
    import logging
    import re as _re
    if not value:
        return None
    s = str(value).strip()
    if _re.fullmatch(r"\d{4}", s):
        s = f"{s}-01-01"
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, AttributeError) as e:
        logging.getLogger("semantica.context").warning(
            "Malformed temporal value %r — treating node as Always-Active. (%s)", value, e
        )
        return None


def _normalize_temporal_input(value: Optional[Union[str, int, float, datetime]]) -> Optional[str]:
    """Normalize supported temporal inputs to ISO strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None).isoformat()
    if isinstance(value, str):
        parsed = _parse_iso_dt(value)
        if parsed is None:
            raise ValueError(f"Temporal value {value!r} is not a valid ISO datetime string")
        return parsed.isoformat()
    raise ValueError("Temporal values must be datetime, epoch seconds, ISO strings, or None")


def _pick_first(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _default_edge_id(
    source_id: str,
    target_id: str,
    edge_type: str,
    weight: float,
    metadata: Dict[str, Any],
    valid_from: Optional[str],
    valid_until: Optional[str],
) -> str:
    payload = json.dumps(
        {
            "source": source_id,
            "target": target_id,
            "type": edge_type,
            "weight": weight,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "metadata": metadata,
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, payload))


def _resolve_edge_identity(
    *,
    source_id: str,
    target_id: str,
    edge_type: str,
    weight: float,
    metadata: Dict[str, Any],
    valid_from: Optional[str],
    valid_until: Optional[str],
    edge_id: Any = None,
    family_id: Any = None,
) -> Tuple[str, str]:
    resolved_edge_id = str(
        _pick_first(
            edge_id,
            _default_edge_id(
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                weight=weight,
                metadata=metadata,
                valid_from=valid_from,
                valid_until=valid_until,
            ),
        )
    )
    resolved_family_id = str(_pick_first(family_id, resolved_edge_id))
    return resolved_edge_id, resolved_family_id


def _coerce_metadata_map(*values: Any) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for value in values:
        if isinstance(value, dict):
            merged.update(value)
    return merged


def _coerce_node_id(raw_node: Dict[str, Any]) -> Optional[str]:
    value = _pick_first(
        raw_node.get("id"),
        raw_node.get("node_id"),
        raw_node.get("_id"),
        raw_node.get("uri"),
        raw_node.get("key"),
    )
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_edge_endpoint(raw_edge: Dict[str, Any], prefix: str) -> Optional[str]:
    prefix = prefix.lower()
    candidates = {
        "source": ["source_id", "source", "start", "start_id", "from", "src", "START_ID", ":START_ID"],
        "target": ["target_id", "target", "end", "end_id", "to", "dst", "END_ID", ":END_ID"],
    }[prefix]
    value = _pick_first(*(raw_edge.get(candidate) for candidate in candidates))
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any, default: float = 1.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class ContextNode:
    """Context graph node (Internal implementation)."""

    node_id: str
    node_type: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    properties: Dict[str, Any] = field(default_factory=dict)
    valid_from: Optional[str] = None  
    valid_until: Optional[str] = None  

    def is_active(self, at_time: Optional[datetime] = None) -> bool:
        """Return True if this node is active at the given time (defaults to now).

        Both ``at_time`` and stored bounds are normalized to tz-naive UTC so that
        callers may pass either aware or naive datetimes without raising TypeError.
        """
        if self.valid_from is None and self.valid_until is None:
            return True
        now = at_time if at_time is not None else datetime.utcnow()
        if now.tzinfo is not None:
            now = now.astimezone(timezone.utc).replace(tzinfo=None)
        start = _parse_iso_dt(self.valid_from) if self.valid_from is not None else None
        end = _parse_iso_dt(self.valid_until) if self.valid_until is not None else None
        if start is not None and now < start:
            return False
        if end is not None and now > end:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        props = self.properties.copy()
        props.update(self.metadata)
        props["content"] = self.content
        if self.valid_from is not None:
            props["valid_from"] = self.valid_from
        if self.valid_until is not None:
            props["valid_until"] = self.valid_until
        return {"id": self.node_id, "type": self.node_type, "properties": props}


@dataclass
class ContextEdge:
    """Context graph edge (Internal implementation)."""

    source_id: str
    target_id: str
    edge_type: str
    edge_id: str = ""
    weight: float = 1.0
    family_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    valid_from: Optional[str] = None  
    valid_until: Optional[str] = None  

    def __post_init__(self) -> None:
        self.source_id = str(self.source_id)
        self.target_id = str(self.target_id)
        self.edge_type = str(self.edge_type or "related_to")
        self.weight = _coerce_float(self.weight, default=1.0)
        if not isinstance(self.metadata, dict):
            self.metadata = {}
        self.edge_id, self.family_id = _resolve_edge_identity(
            source_id=self.source_id,
            target_id=self.target_id,
            edge_type=self.edge_type,
            weight=self.weight,
            metadata=self.metadata,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            edge_id=self.edge_id,
            family_id=self.family_id,
        )
    def is_active(self, at_time: Optional[datetime] = None) -> bool:
        """Return True if this edge is active at the given time (defaults to now).

        Both ``at_time`` and stored bounds are normalized to tz-naive UTC so that
        callers may pass either aware or naive datetimes without raising TypeError.
        """
        if self.valid_from is None and self.valid_until is None:
            return True
        now = at_time if at_time is not None else datetime.utcnow()
        if now.tzinfo is not None:
            now = now.astimezone(timezone.utc).replace(tzinfo=None)
        start = _parse_iso_dt(self.valid_from) if self.valid_from is not None else None
        end = _parse_iso_dt(self.valid_until) if self.valid_until is not None else None
        if start is not None and now < start:
            return False
        if end is not None and now > end:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        d = {
            "id": self.edge_id,
            "familyId": self.family_id or self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.edge_type,
            "weight": self.weight,
            "properties": self.metadata,
        }
        if self.valid_from is not None:
            d["valid_from"] = self.valid_from
        if self.valid_until is not None:
            d["valid_until"] = self.valid_until
        return d


class ContextGraph:
    """
    Easy-to-Use Context Graph with All Advanced Features.
    
    This class provides simple methods for:
    - Building knowledge graphs
    - Recording and analyzing decisions
    - Finding precedents and patterns
    - Causal analysis and policy enforcement
    - Advanced graph analytics
    
    Perfect for building intelligent AI agents that can learn from decisions!
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize context graph with optional advanced features.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - extract_entities: Extract entities from content (default: True)
                - extract_relationships: Extract relationships (default: True)
                - entity_linker: Entity linker instance
                - advanced_analytics: Enable KG algorithms (default: True)
                - centrality_analysis: Enable centrality measures (default: True)
                - community_detection: Enable community detection (default: True)
                - node_embeddings: Enable Node2Vec embeddings (default: True)
        """
        self.logger = get_logger("context_graph")
        self.config = config or {}
        self.config.update(kwargs)

        self.extract_entities = self.config.get("extract_entities", True)
        self.extract_relationships = self.config.get("extract_relationships", True)

        self.entity_linker = self.config.get("entity_linker") or EntityLinker()


        self._lock = threading.RLock()

        self.graph_id: str = str(uuid.uuid4())

        self.nodes: Dict[str, ContextNode] = {}
        self.edges: List[ContextEdge] = []

        self._adjacency: Dict[str, List[ContextEdge]] = defaultdict(list)


        self.node_type_index: Dict[str, Set[str]] = defaultdict(set)
        self.edge_type_index: Dict[str, List[ContextEdge]] = defaultdict(list)

        self._linked_graphs: Dict[str, Tuple["ContextGraph", str, str]] = {}

        self._unresolved_links: Dict[str, Dict[str, str]] = {}

  
        self.progress_tracker = get_progress_tracker()
  
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True
        
   
        self.kg_components = {}
        self._analytics_cache = {}
        
        self.mutation_callback = self.config.get("mutation_callback", None)
        self._suspend_mutation_callback = False
        
        enable_advanced = self.config.get("advanced_analytics", True)
        
        if KG_AVAILABLE and enable_advanced:
            try:
                if self.config.get("centrality_analysis", True):
                    self.kg_components["centrality_calculator"] = CentralityCalculator()
                if self.config.get("community_detection", True):
                    self.kg_components["community_detector"] = CommunityDetector()
                if self.config.get("node_embeddings", True):
                    self.kg_components["node_embedder"] = NodeEmbedder()
                self.kg_components["path_finder"] = PathFinder()
                self.kg_components["similarity_calculator"] = SimilarityCalculator()
                self.kg_components["connectivity_analyzer"] = ConnectivityAnalyzer()
                
                self.logger.info("Advanced KG components initialized successfully")
            except Exception as e:
                self.logger.warning(f"Failed to initialize KG components: {e}")
                self.kg_components = {}



    def add_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """
        Add nodes to graph.

        Args:
            nodes: List of nodes to add (dicts with id, type, properties)

        Returns:
            Number of nodes added
        """
        count = 0
        with self._lock:
            for raw_node in nodes:
                if not isinstance(raw_node, dict):
                    continue

                node_id = _coerce_node_id(raw_node)
                if node_id is None:
                    self.logger.warning("Skipping node without a usable id: %r", raw_node)
                    continue

                node_props = _coerce_metadata_map(
                    raw_node.get("metadata"),
                    raw_node.get("properties"),
                )
                node_type = _pick_first(
                    raw_node.get("type"),
                    raw_node.get("node_type"),
                    raw_node.get("category"),
                    raw_node.get(":LABEL"),
                    node_props.get("type"),
                    "entity",
                )
                content = _pick_first(
                    raw_node.get("content"),
                    raw_node.get("text"),
                    raw_node.get("label"),
                    raw_node.get("name"),
                    raw_node.get("title"),
                    raw_node.get("pref_label"),
                    node_props.get("content"),
                    node_props.get("text"),
                    node_props.get("label"),
                    node_props.get("name"),
                    node_props.get("title"),
                    node_props.get("pref_label"),
                    node_id,
                )

                valid_from = _pick_first(
                    raw_node.get("valid_from"),
                    node_props.get("valid_from"),
                )
                valid_until = _pick_first(
                    raw_node.get("valid_until"),
                    node_props.get("valid_until"),
                )
                metadata = {
                    k: v
                    for k, v in node_props.items()
                    if k not in ("content", "text", "valid_from", "valid_until")
                }

                internal_node = ContextNode(
                    node_id=node_id,
                    node_type=str(node_type or "entity"),
                    content=str(content or node_id),
                    metadata=metadata,
                    properties=node_props,
                    valid_from=valid_from,
                    valid_until=valid_until,
                )

                if self._add_internal_node(internal_node):
                    count += 1
        return count

    def add_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        Add edges to graph.

        Args:
            edges: List of edges to add (dicts with source_id, target_id, type,
                weight, properties)

        Returns:
            Number of edges added
        """
        count = 0
        with self._lock:
            for raw_edge in edges:
                if not isinstance(raw_edge, dict):
                    continue

                source_id = _coerce_edge_endpoint(raw_edge, "source")
                target_id = _coerce_edge_endpoint(raw_edge, "target")
                if source_id is None or target_id is None:
                    self.logger.warning("Skipping edge without usable endpoints: %r", raw_edge)
                    continue

                edge_props = _coerce_metadata_map(
                    raw_edge.get("metadata"),
                    raw_edge.get("properties"),
                )
                edge_type = _pick_first(
                    raw_edge.get("type"),
                    raw_edge.get("edge_type"),
                    raw_edge.get("relationship"),
                    raw_edge.get("predicate"),
                    raw_edge.get("relation"),
                    raw_edge.get(":TYPE"),
                    edge_props.get("type"),
                    "related_to",
                )

                valid_from = _pick_first(raw_edge.get("valid_from"), edge_props.get("valid_from"))
                valid_until = _pick_first(raw_edge.get("valid_until"), edge_props.get("valid_until"))
                weight = _coerce_float(_pick_first(raw_edge.get("weight"), edge_props.get("weight")), default=1.0)
                explicit_edge_id = _pick_first(
                    raw_edge.get("id"),
                    raw_edge.get("edge_id"),
                    edge_props.pop("id", None),
                    edge_props.pop("edge_id", None),
                )
                explicit_family_id = _pick_first(
                    raw_edge.get("familyId"),
                    raw_edge.get("family_id"),
                    edge_props.pop("familyId", None),
                    edge_props.pop("family_id", None),
                )
                edge_id, family_id = _resolve_edge_identity(
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=str(edge_type or "related_to"),
                    weight=weight,
                    metadata=edge_props,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    edge_id=explicit_edge_id,
                    family_id=explicit_family_id,
                )
                internal_edge = ContextEdge(
                    edge_id=edge_id,
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=str(edge_type or "related_to"),
                    family_id=str(family_id) if family_id is not None else edge_id,
                    weight=weight,
                    metadata=edge_props,
                    valid_from=valid_from,
                    valid_until=valid_until,
                )

                if self._add_internal_edge(internal_edge):
                    count += 1
        return count

    def __contains__(self, node_id: object) -> bool:
        if not isinstance(node_id, str):
            return False
        with self._lock:
            return node_id in self.nodes

    def has_node(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self.nodes

    def neighbors(self, node_id: str) -> List[Dict[str, Any]]:
        return self.get_neighbors(node_id, hops=1)

    def get_neighbor_ids(
        self,
        node_id: str,
        relationship_types: Optional[List[str]] = None,
    ) -> List[str]:
        with self._lock:
            if node_id not in self.nodes:
                return []

            rel_filter = set(relationship_types) if relationship_types else None
            neighbor_ids: List[str] = []
            for edge in self._adjacency.get(node_id, []):
                if rel_filter is None or edge.edge_type in rel_filter:
                    neighbor_ids.append(edge.target_id)
            return neighbor_ids

    def get_nodes_by_label(self, label: str) -> List[Dict[str, Any]]:
        result = []
        with self._lock:
            for nid in self.node_type_index.get(label, set()):
                node = self.nodes.get(nid)
                if node:
                    result.append({
                        "id": node.node_id,
                        "content": node.content,
                        "type": node.node_type,
                        "metadata": (node.properties or {}).copy(),
                    })
        return result

    def get_node_property(self, node_id: str, property_name: str) -> Any:
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return None
            return node.properties.get(property_name)

    def get_node_attributes(self, node_id: str) -> Dict[str, Any]:
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return {}
            return node.properties.copy()

    def add_node_attribute(self, node_id: str, attributes: Dict[str, Any]) -> None:
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return
            node.properties.update(attributes)
            node.metadata.update(attributes)


        if getattr(self, "mutation_callback", None) and not getattr(
            self, "_suspend_mutation_callback", False
        ):
            self.mutation_callback("UPDATE_NODE", node_id, node.to_dict())

    def get_edge_data(self, source_id: str, target_id: str) -> Dict[str, Any]:
        with self._lock:
            for edge in self._adjacency.get(source_id, []):
                if edge.target_id == target_id:
                    data = edge.metadata.copy()
                    data["id"] = edge.edge_id
                    data["familyId"] = edge.family_id or edge.edge_id
                    data["type"] = edge.edge_type
                    data["weight"] = edge.weight
                    return data
        return {}

    def get_neighbors(
        self,
        node_id: str,
        hops: int = 1,
        relationship_types: Optional[List[str]] = None,
        min_weight: float = 0.0,
        skip: int = 0,
        limit: Optional[int] = None,
        include_distance_metadata: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get neighbors of a node.

        Args:
            node_id: Starting node ID.
            hops: Maximum number of hops to traverse (BFS depth).
            relationship_types: Optional whitelist of edge types to follow.
            min_weight: Minimum edge weight required to traverse an edge (default 0.0
                means all edges pass). Use e.g. ``min_weight=0.5`` to follow only
                strong/high-confidence relationships.
            skip: Number of items to skip for pagination.
            limit: Maximum items to return.

        Returns:
            List of dicts with neighbor info (id, type, content, relationship, weight, hop).
        """
        with self._lock:
            if node_id not in self.nodes:
                return []

            neighbors: List[Dict[str, Any]] = []
            visited = {node_id}
            queue = deque([(node_id, 0, [node_id], 1.0)])
            rel_filter = set(relationship_types) if relationship_types else None

            while queue:
                current_id, current_hop, path_so_far, decay_so_far = queue.popleft()
                if current_hop >= hops:
                    continue

                outgoing_edges = self._adjacency.get(current_id, [])
                for edge in outgoing_edges:
                    if rel_filter is not None and edge.edge_type not in rel_filter:
                        continue
                    if edge.weight < min_weight:
                        continue
                    neighbor_id = edge.target_id
                    if neighbor_id in visited:
                        continue
                    visited.add(neighbor_id)
                    next_hop = current_hop + 1
                    next_decay = decay_so_far * edge.weight
                    next_path = path_so_far + [neighbor_id]
                    queue.append((neighbor_id, next_hop, next_path, next_decay))

                    node = self.nodes.get(neighbor_id)
                    if not node:
                        continue
                    entry: Dict[str, Any] = {
                        "id": node.node_id,
                        "type": node.node_type,
                        "content": node.content,
                        "relationship": edge.edge_type,
                        "weight": edge.weight,
                        "hop": next_hop,
                    }
                    if include_distance_metadata:
                        entry["distance_band"] = classify_path_distance(next_hop)
                        entry["confidence_decay"] = next_decay
                        entry["path_to_anchor"] = next_path
                    neighbors.append(entry)

            if limit is not None:
                return neighbors[skip: skip + limit]
            return neighbors[skip:]

    def get_neighbor_distances(
        self,
        node_id: str,
        hops: int = 3,
        relationship_types: Optional[List[str]] = None,
        min_confidence: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Return neighbors with distance metadata, filtered by confidence decay.

        Results are ordered by nearest hop first, then by strongest path confidence.
        """
        neighbors = self.get_neighbors(
            node_id,
            hops=hops,
            relationship_types=relationship_types,
            include_distance_metadata=True,
        )
        filtered = [
            item for item in neighbors
            if item.get("confidence_decay", 0.0) >= min_confidence
        ]
        return sorted(
            filtered,
            key=lambda item: (item.get("hop", 0), -item.get("confidence_decay", 0.0)),
        )

    def query(
        self, query: str, skip: int = 0, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a simple keyword search query on the graph nodes.

        Args:
            query: Keyword query string
            skip: Items to skip
            limit: Max items to return

        Returns:
            List of matching node dicts
        """
        results = []
        query_lower = query.lower().split()

        with self._lock:
            for node in self.nodes.values():
                content_lower = node.content.lower()
                if any(word in content_lower for word in query_lower):
                    # Calculate simple score
                    overlap = sum(1 for word in query_lower if word in content_lower)
                    score = overlap / len(query_lower) if query_lower else 0.0

                    results.append(
                        {
                            "node": node.to_dict(),
                            "score": score,
                            "content": node.content,
                        }
                    )

        sorted_res = sorted(results, key=lambda x: x["score"], reverse=True)
        if limit is not None:
            return sorted_res[skip: skip + limit]
        return sorted_res[skip:]

    def add_node(
        self,
        node_id: str,
        node_type: str,
        content: Optional[str] = None,
        **properties,
    ) -> bool:
        """
        Add a single node to the graph.

        Args:
            node_id: Unique identifier
            node_type: Node type (e.g., 'entity', 'concept')
            content: Node content/label
            **properties: Additional properties. Use `valid_from` and `valid_until`
                (ISO datetime strings) to define a temporal validity window.
        """
        content = content or node_id
        valid_from = properties.pop("valid_from", None)
        valid_until = properties.pop("valid_until", None)
        with self._lock:
            return self._add_internal_node(
                ContextNode(
                    node_id=node_id,
                    node_type=node_type,
                    content=content,
                    metadata=properties,
                    properties=properties,
                    valid_from=valid_from,
                    valid_until=valid_until,
                )
            )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "related_to",
        weight: float = 1.0,
        **properties,
    ) -> bool:
        """
        Add a single edge to the graph.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Relationship type
            weight: Edge weight
            **properties: Additional properties. Use `valid_from` and `valid_until`
                (ISO datetime strings) to define a temporal validity window.
        """
        valid_from = properties.pop("valid_from", None)
        valid_until = properties.pop("valid_until", None)
        explicit_edge_id = properties.pop("id", properties.pop("edge_id", None))
        explicit_family_id = properties.pop("familyId", properties.pop("family_id", None))
        edge_id, family_id = _resolve_edge_identity(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            metadata=properties,
            valid_from=valid_from,
            valid_until=valid_until,
            edge_id=explicit_edge_id,
            family_id=explicit_family_id,
        )
        with self._lock:
            return self._add_internal_edge(
                ContextEdge(
                    edge_id=edge_id,
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=edge_type,
                    family_id=str(family_id) if family_id is not None else edge_id,
                    weight=weight,
                    metadata=properties,
                    valid_from=valid_from,
                    valid_until=valid_until,
                )
            )

    def save_to_file(self, path: str) -> None:
        """
        Save context graph to file (JSON format).

        Args:
            path: File path to save to
        """
        import json

        with self._lock:
    
            links_data = []
            for link_id, (other_graph, source_node_id, target_node_id) in self._linked_graphs.items():
                links_data.append(
                    {
                        "link_id": link_id,
                        "source_node_id": source_node_id,
                        "target_node_id": target_node_id,
                        "other_graph_id": other_graph.graph_id,
                    }
                )

            data = {
                "graph_id": self.graph_id,
                "nodes": [node.to_dict() for node in self.nodes.values()],
                "edges": [edge.to_dict() for edge in self.edges],
                "links": links_data,
            }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved context graph to {path}")

    def load_from_file(self, path: str) -> None:
        """
        Load context graph from file (JSON format).

        Args:
            path: File path to load from
        """
        import json
        import os

        if not os.path.exists(path):
            self.logger.warning(f"File not found: {path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            if data and isinstance(data[0], dict) and any(
                key in data[0]
                for key in ("source", "source_id", "target", "target_id", "START_ID", ":START_ID")
            ):
                data = {"edges": data, "nodes": []}
            else:
                data = {"nodes": data, "edges": []}
        elif not isinstance(data, dict):
            raise ValueError("Graph file must contain a JSON object or array payload")

        with self._lock:
            # Clear existing
            self.nodes.clear()
            self.edges.clear()
            self._adjacency.clear()
            self.node_type_index.clear()
            self.edge_type_index.clear()
            self._linked_graphs.clear()
            self._unresolved_links.clear()

            if "graph_id" in data:
                self.graph_id = data["graph_id"]

    
            nodes = data.get("nodes")
            if nodes is None:
                nodes = data.get("entities")
            if nodes is None:
                nodes = data.get("vertices")
            if nodes is None:
                nodes = []
            self.add_nodes(nodes)

            edges = data.get("edges")
            if edges is None:
                edges = data.get("relationships")
            if edges is None:
                edges = data.get("links")
            if edges is None:
                edges = []
            self.add_edges(edges)

        
            for link_meta in data.get("links", []):
                link_id = link_meta.get("link_id")
                if link_id:
                    self._unresolved_links[link_id] = link_meta

        self.logger.info(f"Loaded context graph from {path}")

    def find_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Find a node by ID."""
        with self._lock:
            node = self.nodes.get(node_id)
            if node:
                merged_metadata = {}
                merged_metadata.update(getattr(node, "metadata", {}) or {})
                merged_metadata.update(getattr(node, "properties", {}) or {})
                return {
                    "id": node.node_id,
                    "type": node.node_type,
                    "content": node.content,
                    "metadata": merged_metadata,
                }
            return None

    def find_nodes(
        self, node_type: Optional[str] = None, skip: int = 0, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Find nodes lazily"""
        with self._lock:
            if node_type:
                # Sets are unordered, sort IDs for deterministic pagination
                raw_ids = sorted(
                    (node_id for node_id in self.node_type_index.get(node_type, set()) if node_id is not None),
                    key=lambda value: str(value),
                )
                source = (self.nodes[nid] for nid in raw_ids if nid in self.nodes)
            else:
                source = self.nodes.values()

            gen = (
                {
                    "id": n.node_id,
                    "type": n.node_type or "entity",
                    "content": n.content or "",
                    "metadata": {**(getattr(n, "metadata", {}) or {}), **(getattr(n, "properties", {}) or {})},
                }
                for n in source if n.node_id
            )
            stop = skip + limit if limit is not None else None
    
            return list(itertools.islice(gen, skip, stop))

    def find_active_nodes(
        self,
        node_type: Optional[str] = None,
        at_time: Optional[datetime] = None,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find active nodes lazily."""
        now = at_time or datetime.utcnow()
        with self._lock:
            if node_type:
                raw_ids = sorted(
                    (node_id for node_id in self.node_type_index.get(node_type, set()) if node_id is not None),
                    key=lambda value: str(value),
                )
                source = (self.nodes[nid] for nid in raw_ids if nid in self.nodes)
            else:
                source = self.nodes.values()

            def _active(nodes_iter):
                for n in nodes_iter:
                    if n.node_id and n.is_active(now):
                        yield {
                            "id": n.node_id,
                            "type": n.node_type or "entity",
                            "content": n.content or "",
                            "metadata": {
                                **(getattr(n, "metadata", {}) or {}),
                                **(getattr(n, "properties", {}) or {}),
                            },
                        }

            stop = skip + limit if limit is not None else None
            return list(itertools.islice(_active(source), skip, stop))

    def link_graph(
        self,
        other_graph: "ContextGraph",
        source_node_id: str,
        target_node_id: str,
        link_type: str = "CROSS_GRAPH",
    ) -> str:
        """
        Create a navigable link from a node in this graph to a node in another graph.

        This enables cross-graph navigation: separate ContextGraph instances can be
        linked hierarchically, allowing agents to traverse from one problem space into
        a related one without merging the graphs (like "a dream within a dream").

        Args:
            other_graph: The target ContextGraph instance.
            source_node_id: Node ID in *this* graph that serves as the exit point.
            target_node_id: Node ID in *other_graph* that serves as the entry point.
            link_type: Edge type label for the cross-graph bridge (default "CROSS_GRAPH").

        Returns:
            A unique link ID that can be passed to :meth:`navigate_to`.

        Raises:
            KeyError: If source_node_id is not in this graph or target_node_id is not
                in other_graph.
        """
        with self._lock:
            if source_node_id not in self.nodes:
                raise KeyError(f"Source node '{source_node_id}' not found in this graph")
            if target_node_id not in other_graph.nodes:
                raise KeyError(f"Target node '{target_node_id}' not found in other_graph")

            link_id = str(uuid.uuid4())
            self._linked_graphs[link_id] = (other_graph, source_node_id, target_node_id)

            marker_node_id = f"__cross_graph_{link_id}"
            self._add_internal_node(
                ContextNode(
                    node_id=marker_node_id,
                    node_type="cross_graph_link",
                    content=f"Cross-graph link → {target_node_id}",
                    metadata={"cross_graph": True, "link_id": link_id, "target_node_id": target_node_id},
                    properties={},
                )
            )

            self._add_internal_edge(
                ContextEdge(
                    source_id=source_node_id,
                    target_id=marker_node_id,
                    edge_type=link_type,
                    weight=1.0,
                    metadata={"cross_graph": True, "link_id": link_id},
                )
            )
            return link_id

    def navigate_to(self, link_id: str) -> Tuple["ContextGraph", str]:
        """
        Navigate to the target graph and entry node for a cross-graph link.

        Args:
            link_id: Link ID returned by :meth:`link_graph`.

        Returns:
            Tuple of ``(other_graph, target_node_id)``.

        Raises:
            KeyError: If link_id is not registered on this graph.
        """
        if link_id not in self._linked_graphs:
            if link_id in self._unresolved_links:
                meta = self._unresolved_links[link_id]
                raise KeyError(
                    f"Cross-graph link '{link_id}' exists but its target graph "
                    f"(graph_id={meta.get('other_graph_id')!r}) has not been reconnected. "
                    "Call resolve_links({graph_id: graph_instance, ...}) to restore navigation."
                )
            raise KeyError(
                f"No cross-graph link '{link_id}' found. "
                "Call link_graph() first to create the link."
            )
        other_graph, _, target_node_id = self._linked_graphs[link_id]
        return other_graph, target_node_id

    def cross_graph_path(
        self,
        source_node_id: str,
        target_graph: "ContextGraph",
        target_node_id: str,
        max_hops: int = 10,
    ) -> Dict[str, Any]:
        """
        Find the shortest path across linked ContextGraph instances.
        """
        start = (self.graph_id, source_node_id)
        goal = (target_graph.graph_id, target_node_id)
        if source_node_id not in self.nodes or target_node_id not in target_graph.nodes:
            return {
                "path": [],
                "hop_count": 0,
                "cross_graph_links_used": 0,
                "confidence_decay": 0.0,
                "distance_band": classify_path_distance(max_hops + 1),
                "reachable": False,
            }

        queue = deque([(self, source_node_id, [start], 0, 1.0, 0)])
        visited = {start}

        while queue:
            graph, current_id, path, hop_count, decay, links_used = queue.popleft()
            current_key = (graph.graph_id, current_id)
            if current_key == goal:
                return {
                    "path": path,
                    "hop_count": hop_count,
                    "cross_graph_links_used": links_used,
                    "confidence_decay": decay,
                    "distance_band": classify_path_distance(hop_count),
                    "reachable": True,
                }
            if hop_count >= max_hops:
                continue

            with graph._lock:
                outgoing_edges = list(graph._adjacency.get(current_id, []))

            for edge in outgoing_edges:
                marker = graph.nodes.get(edge.target_id)
                link_id = None
                if marker and marker.node_type == "cross_graph_link":
                    link_id = marker.metadata.get("link_id")

                if link_id:
                    try:
                        next_graph, next_node_id = graph.navigate_to(link_id)
                    except KeyError:
                        continue
                    next_key = (next_graph.graph_id, next_node_id)
                    next_links_used = links_used + 1
                else:
                    next_graph, next_node_id = graph, edge.target_id
                    next_key = (graph.graph_id, edge.target_id)
                    next_links_used = links_used

                if next_key in visited:
                    continue
                visited.add(next_key)
                queue.append(
                    (
                        next_graph,
                        next_node_id,
                        path + [next_key],
                        hop_count + 1,
                        decay * edge.weight,
                        next_links_used,
                    )
                )

        return {
            "path": [],
            "hop_count": 0,
            "cross_graph_links_used": 0,
            "confidence_decay": 0.0,
            "distance_band": classify_path_distance(max_hops + 1),
            "reachable": False,
        }

    def resolve_links(self, graphs: Dict[str, "ContextGraph"]) -> int:
        """
        Reconnect cross-graph links after a :meth:`load_from_file` call.

        Since ``other_graph`` object references cannot be serialised, links are stored
        as metadata only (``other_graph_id``).  Call this method with a mapping of
        ``{graph_id: graph_instance}`` to restore live navigation.

        Args:
            graphs: Mapping of graph_id strings to ContextGraph instances.

        Returns:
            Number of links successfully resolved.

        Example::

            g1.save_to_file("g1.json")
            g2.save_to_file("g2.json")

            g1b, g2b = ContextGraph(), ContextGraph()
            g1b.load_from_file("g1.json")
            g2b.load_from_file("g2.json")
            resolved = g1b.resolve_links({g2b.graph_id: g2b})
        """
        resolved = 0
        with self._lock:
            for link_id, meta in list(self._unresolved_links.items()):
                other_graph_id = meta.get("other_graph_id")
                if other_graph_id in graphs:
                    other_graph = graphs[other_graph_id]
                    source_node_id = meta["source_node_id"]
                    target_node_id = meta["target_node_id"]
                    # Validate target node still exists in the restored graph
                    if target_node_id in other_graph.nodes:
                        self._linked_graphs[link_id] = (other_graph, source_node_id, target_node_id)
                        del self._unresolved_links[link_id]
                        resolved += 1
                    else:
                        self.logger.warning(
                            f"resolve_links: target node '{target_node_id}' not found in "
                            f"graph '{other_graph_id}' for link '{link_id}'"
                        )
        return resolved

    def find_edges(
        self, edge_type: Optional[str] = None, skip: int = 0, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Find edges lazily."""
        with self._lock:
            source = self.edge_type_index.get(edge_type, []) if edge_type else self.edges
            
            gen = (
                {
                    "id": e.edge_id,
                    "familyId": e.family_id or e.edge_id,
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type,
                    "weight": e.weight,
                    "metadata": e.metadata,
                    "valid_from": e.valid_from,
                    "valid_until": e.valid_until,
                }
                for e in source if e.source_id and e.target_id
            )
            stop = skip + limit if limit is not None else None
            return list(itertools.islice(gen, skip, stop))

    def stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        with self._lock:
            # Count only items that find_nodes/find_edges can return, so pagination
            # totals reported to callers match what the methods actually yield.
            node_count = sum(1 for n in self.nodes.values() if n.node_id)
            edge_count = sum(1 for e in self.edges if e.source_id and e.target_id)
            node_types = {
                k: sum(
                    1 for nid in v
                    if isinstance(nid, str) and nid in self.nodes and self.nodes[nid].node_id
                )
                for k, v in self.node_type_index.items()
            }
            edge_types = {
                k: sum(1 for e in v if e.source_id and e.target_id)
                for k, v in self.edge_type_index.items()
            }
            return {
                "node_count": node_count,
                "edge_count": edge_count,
                "node_types": node_types,
                "edge_types": edge_types,
                "density": self.density(),
            }

    def density(self) -> float:
        """Calculate graph density."""
        with self._lock:
            n = len(self.nodes)
            if n < 2:
                return 0.0
            max_edges = n * (n - 1) 
            return len(self.edges) / max_edges

    def clear(self) -> None:
        """Fully reset the graph state and indexes."""
        with self._lock:
            self.nodes.clear()
            self.edges.clear()
            self._adjacency.clear()
            self.node_type_index.clear()
            self.edge_type_index.clear()
            self._linked_graphs.clear()
            self._unresolved_links.clear()
        self.logger.debug("Graph state fully cleared.")

    # --- Internal Helpers ---

    def _normalize_timestamp(self, timestamp_value) -> datetime:
        """
        Normalize timestamp value to datetime object.
        
        Handles various timestamp formats:
        - datetime: returns as-is
        - int/float: converts from epoch seconds
        - str: parses ISO format (with optional Z)
        - None/invalid: returns current datetime
        
        Args:
            timestamp_value: Timestamp value in various formats
            
        Returns:
            datetime: Normalized datetime object
        """
        from datetime import datetime
        
        if isinstance(timestamp_value, datetime):
            return timestamp_value
        elif isinstance(timestamp_value, (int, float)):
            return datetime.fromtimestamp(timestamp_value)
        elif isinstance(timestamp_value, str):
            # Handle ISO format with optional Z suffix
            timestamp_str = timestamp_value.rstrip('Z')  #
            try:
                return datetime.fromisoformat(timestamp_str)
            except ValueError:
                # Fallback to current datetime if parsing fails
                return datetime.now()
        else:
            # Fallback for None or other types
            return datetime.now()

    def _add_internal_node(self, node: ContextNode) -> bool:
        """Internal method to add a node."""
        if node.node_id is None or (isinstance(node.node_id, str) and not node.node_id.strip()):
            self.logger.warning("Skipping internal node with invalid id: %r", node)
            return False
        with self._lock:
            self.nodes[node.node_id] = node
            # Handle edge case where node_type might be None or not a string
            if hasattr(node, 'node_type') and isinstance(node.node_type, str):
                self.node_type_index[node.node_type].add(node.node_id)
            else:
                # Use 'unknown' as fallback for invalid node_type
                self.node_type_index['unknown'].add(node.node_id)

        if getattr(self, "mutation_callback", None) and not getattr(
            self, "_suspend_mutation_callback", False
        ):
            try:
                self.mutation_callback("ADD_NODE", node.node_id, node.to_dict())
            except Exception as e:
                self.logger.warning(f"Audit trail callback failed for node {node.node_id}: {e}")
        return True
    
    def _add_internal_edge(self, edge: ContextEdge) -> bool:
        """Internal method to add an edge."""
        if edge.source_id is None or edge.target_id is None:
            self.logger.warning("Skipping internal edge with invalid endpoints: %r", edge)
            return False
        with self._lock:
            # Ensure nodes exist
            if edge.source_id not in self.nodes:
                self._add_internal_node(
                    ContextNode(edge.source_id, "entity", edge.source_id)
                )
            if edge.target_id not in self.nodes:
                self._add_internal_node(
                    ContextNode(edge.target_id, "entity", edge.target_id)
                )

            self.edges.append(edge)
            self.edge_type_index[edge.edge_type].append(edge)
            self._adjacency[edge.source_id].append(edge)

        if getattr(self, "mutation_callback", None) and not getattr(
            self, "_suspend_mutation_callback", False
        ):
            try:
                self.mutation_callback("ADD_EDGE", edge.edge_id, edge.to_dict())
            except Exception as e:
                self.logger.warning(
                    f"Audit trail callback failed for edge {edge.edge_id}: {e}"
                )
        return True

    # --- Builder Methods (Legacy/Utility) ---

    def build_from_conversations(
        self,
        conversations: List[Union[str, Dict[str, Any]]],
        link_entities: bool = True,
        extract_intents: bool = False,
        extract_sentiments: bool = False,
        **options,
    ) -> Dict[str, Any]:
        """
        Build context graph from conversations and return dict representation.

        Args:
            conversations: List of conversation files or dictionaries
            ...

        Returns:
            Graph dictionary (nodes, edges)
        """
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="context",
            submodule="ContextGraph",
            message=f"Building graph from {len(conversations)} conversations",
        )

        try:
            for conv in conversations:
                conv_data = (
                    conv if isinstance(conv, dict) else self._load_conversation(conv)
                )
                self._process_conversation(
                    conv_data,
                    extract_intents=extract_intents,
                    extract_sentiments=extract_sentiments,
                )

            if link_entities:
                self._link_entities()

            self.progress_tracker.stop_tracking(tracking_id, status="completed")
            return self.to_dict()

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def build_from_entities_and_relationships(
        self,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Build graph from entities and relationships.

        Args:
            entities: List of entity dictionaries
            relationships: List of relationship dictionaries
            **kwargs: Additional options

        Returns:
            Graph dictionary (nodes, edges)
        """
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="context",
            submodule="ContextGraph",
            message=(
                f"Building graph from {len(entities)} entities and "
                f"{len(relationships)} relationships"
            ),
        )

        try:
            # Add entities
            for entity in entities:
                entity_id = entity.get("id") or entity.get("entity_id")
                if entity_id:
                    self._add_internal_node(
                        ContextNode(
                            node_id=entity_id,
                            node_type=entity.get("type", "entity"),
                            content=entity.get("text")
                            or entity.get("label")
                            or entity_id,
                            metadata=entity,
                            properties=entity,
                        )
                    )

            # Add relationships
            for rel in relationships:
                source = rel.get("source_id")
                target = rel.get("target_id")
                if source and target:
                    self._add_internal_edge(
                        ContextEdge(
                            source_id=source,
                            target_id=target,
                            edge_type=rel.get("type", "related_to"),
                            weight=rel.get("confidence", 1.0),
                            metadata=rel,
                        )
                    )

            self.progress_tracker.stop_tracking(tracking_id, status="completed")
            return self.to_dict()

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _process_conversation(self, conv_data: Dict[str, Any], **kwargs) -> None:
        """Process a single conversation."""
        conv_id = conv_data.get("id") or f"conv_{hash(str(conv_data)) % 10000}"

        # Add conversation node
        self._add_internal_node(
            ContextNode(
                node_id=conv_id,
                node_type="conversation",
                content=conv_data.get("content", "") or conv_data.get("summary", ""),
                metadata={"timestamp": conv_data.get("timestamp")},
            )
        )

        # Track name to ID mapping for relationship resolution
        name_to_id = {}

        # Extract entities
        if self.extract_entities:
            for entity in conv_data.get("entities", []):
                entity_id = entity.get("id") or entity.get("entity_id")
                entity_text = (
                    entity.get("text")
                    or entity.get("label")
                    or entity.get("name")
                    or entity_id
                )
                entity_type = entity.get("type", "entity")

                # Generate ID if missing
                if not entity_id and entity_text and self.entity_linker:
                    # Use EntityLinker to generate ID
                    if hasattr(self.entity_linker, "_generate_entity_id"):
                        entity_id = self.entity_linker._generate_entity_id(
                            entity_text, entity_type
                        )
                    else:
                        # Fallback ID generation
                        import hashlib

                        entity_hash = hashlib.md5(
                            f"{entity_text}_{entity_type}".encode()
                        ).hexdigest()[:12]
                        entity_id = f"{entity_type.lower()}_{entity_hash}"

                if entity_id:
                    if entity_text:
                        name_to_id[entity_text] = entity_id

                    self._add_internal_node(
                        ContextNode(
                            node_id=entity_id,
                            node_type="entity",
                            content=entity_text,
                            metadata={"type": entity_type, **entity},
                        )
                    )
                    self._add_internal_edge(
                        ContextEdge(
                            source_id=conv_id,
                            target_id=entity_id,
                            edge_type="mentions",
                        )
                    )

        # Extract relationships
        if self.extract_relationships:
            for rel in conv_data.get("relationships", []):
                source = rel.get("source_id")
                target = rel.get("target_id")

                # Resolve IDs from names if missing
                if not source and rel.get("source") and rel.get("source") in name_to_id:
                    source = name_to_id[rel.get("source")]

                if not target and rel.get("target") and rel.get("target") in name_to_id:
                    target = name_to_id[rel.get("target")]

                if source and target:
                    self._add_internal_edge(
                        ContextEdge(
                            source_id=source,
                            target_id=target,
                            edge_type=rel.get("type", "related_to"),
                            weight=rel.get("confidence", 1.0),
                        )
                    )

    def _link_entities(self) -> None:
        """Link similar entities using EntityLinker."""
        if not self.entity_linker:
            return

        entity_nodes = [n for n in self.nodes.values() if n.node_type == "entity"]
        for i, node1 in enumerate(entity_nodes):
            for node2 in entity_nodes[i + 1 :]:
                similarity = self.entity_linker._calculate_text_similarity(
                    node1.content.lower(), node2.content.lower()
                )
                if similarity >= self.entity_linker.similarity_threshold:
                    self._add_internal_edge(
                        ContextEdge(
                            source_id=node1.node_id,
                            target_id=node2.node_id,
                            edge_type="similar_to",
                            weight=similarity,
                        )
                    )

    def _load_conversation(self, file_path: str) -> Dict[str, Any]:
        """Load conversation from file."""
        from ..utils.helpers import read_json_file
        from pathlib import Path

        return read_json_file(Path(file_path))

    def to_dict(self) -> Dict[str, Any]:
        """Export graph to dictionary format."""
        nodes_out = []
        for n in self.nodes.values():
            entry: Dict[str, Any] = {
                "id": n.node_id,
                "type": n.node_type,
                "content": n.content,
                "properties": n.properties,
                "metadata": n.metadata,
            }
            if n.valid_from is not None:
                entry["valid_from"] = n.valid_from
            if n.valid_until is not None:
                entry["valid_until"] = n.valid_until
            nodes_out.append(entry)

        edges_out = []
        for e in self.edges:
            entry = {
                "id": e.edge_id,
                "familyId": e.family_id or e.edge_id,
                "source": e.source_id,
                "target": e.target_id,
                "type": e.edge_type,
                "weight": e.weight,
            }
            if e.metadata:
                entry["metadata"] = e.metadata
            if e.valid_from is not None:
                entry["valid_from"] = e.valid_from
            if e.valid_until is not None:
                entry["valid_until"] = e.valid_until
            edges_out.append(entry)

        return {
            "nodes": nodes_out,
            "edges": edges_out,
            "statistics": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
            },
        }

    def from_dict(self, graph_dict: Dict[str, Any]) -> None:
        """Load graph from dictionary format."""
        # Clear existing graph
        self.clear()

        # Add nodes — restore validity windows if present
        for node_data in graph_dict.get("nodes", []):
            node_props = node_data.get("properties", {})
            node = ContextNode(
                node_id=node_data["id"],
                node_type=node_data["type"],
                content=node_data.get("content", ""),
                properties=node_props,
                metadata=node_data.get("metadata", {}),
                valid_from=node_data.get("valid_from") or node_props.get("valid_from"),
                valid_until=node_data.get("valid_until") or node_props.get("valid_until"),
            )
            self._add_internal_node(node)

        # Add edges — restore validity windows if present
        for edge_data in graph_dict.get("edges", []):
            edge_metadata = edge_data.get("metadata", edge_data.get("properties", {})) or {}
            edge_weight = edge_data.get("weight", 1.0)
            edge_id, family_id = _resolve_edge_identity(
                source_id=edge_data["source"],
                target_id=edge_data["target"],
                edge_type=edge_data["type"],
                weight=edge_weight,
                metadata=edge_metadata,
                valid_from=edge_data.get("valid_from"),
                valid_until=edge_data.get("valid_until"),
                edge_id=edge_data.get("id", edge_data.get("edge_id")),
                family_id=edge_data.get("familyId", edge_data.get("family_id")),
            )
            edge = ContextEdge(
                edge_id=edge_id,
                source_id=edge_data["source"],
                target_id=edge_data["target"],
                edge_type=edge_data["type"],
                weight=edge_weight,
                family_id=family_id,
                metadata=edge_metadata,
                valid_from=edge_data.get("valid_from"),
                valid_until=edge_data.get("valid_until"),
            )
            self._add_internal_edge(edge)

    def state_at(self, timestamp: Union[str, int, float, datetime]) -> Dict[str, Any]:
        """Return a serializable snapshot of graph state valid at the given time."""
        at_time = self._normalize_timestamp(timestamp)
        with self._lock:
            active_nodes = [node for node in self.nodes.values() if node.is_active(at_time)]
            active_node_ids = {node.node_id for node in active_nodes}
            active_edges = [
                edge for edge in self.edges
                if edge.is_active(at_time)
                and edge.source_id in active_node_ids
                and edge.target_id in active_node_ids
            ]

        nodes_payload = [node.to_dict() for node in active_nodes]
        edges_payload = [edge.to_dict() for edge in active_edges]
        decisions_payload = [
            {
                "id": node.node_id,
                "category": node.properties.get("category", ""),
                "scenario": node.properties.get("scenario", node.content),
                "reasoning": node.properties.get("reasoning", ""),
                "outcome": node.properties.get("outcome", ""),
                "confidence": node.properties.get("confidence", 0.0),
                "timestamp": node.properties.get("timestamp"),
                "decision_maker": node.properties.get("decision_maker"),
                "entities": node.properties.get("entities", []),
                "valid_from": node.valid_from,
                "valid_until": node.valid_until,
                "metadata": dict(node.properties.get("metadata", {}) or {}),
            }
            for node in active_nodes
            if isinstance(node.node_type, str) and node.node_type.lower() == "decision"
        ]

        return {
            "timestamp": at_time.isoformat(),
            "nodes": nodes_payload,
            "edges": edges_payload,
            "entities": nodes_payload,
            "relationships": edges_payload,
            "decisions": decisions_payload,
        }

    # Decision Support Methods
    def add_decision(
        self,
        decision: "Decision" = None,
        *,
        category: str = None,
        scenario: str = None,
        reasoning: str = None,
        outcome: str = None,
        confidence: float = 0.5,
        entities: Optional[List[str]] = None,
        decision_maker: Optional[str] = "system",
        valid_from=None,
        valid_until=None,
        **kwargs,
    ) -> str:
        """
        Add decision node to graph.

        Accepts either a Decision object or keyword arguments:

            # From a Decision object
            graph.add_decision(Decision(category="x", scenario="y", ...))

            # From keyword arguments (convenience form)
            graph.add_decision(category="x", scenario="y", reasoning="z",
                               outcome="o", confidence=0.9)

        Args:
            decision: Decision object to add (mutually exclusive with kwargs)
            category: Decision category
            scenario: Decision scenario description
            reasoning: Reasoning behind the decision
            outcome: Decision outcome
            confidence: Confidence score (0.0–1.0)
            entities: Related entity labels
            decision_maker: Who made the decision
            valid_from: Start of validity window (ISO string or datetime)
            valid_until: End of validity window (ISO string or datetime)
            **kwargs: Extra metadata stored on the decision node

        Returns:
            Decision ID
        """
        from .decision_models import Decision

        if decision is not None and (
            any(v is not None for v in (
                category, scenario, reasoning, outcome, entities, valid_from, valid_until,
            )) or kwargs
        ):
            raise ValueError(
                "Pass either a Decision object or keyword arguments, not both."
            )

        if decision is None:
            # Build from kwargs — delegate to record_decision which handles ID gen
            return self.record_decision(
                category=category,
                scenario=scenario,
                reasoning=reasoning,
                outcome=outcome,
                confidence=confidence,
                entities=entities,
                decision_maker=decision_maker,
                valid_from=valid_from,
                valid_until=valid_until,
                metadata=kwargs,
            )

        # Handle empty decision ID by generating UUID for both None and empty string
        # This ensures consistent behavior with Decision model's __post_init__ method
        node_id = decision.decision_id if decision.decision_id else str(uuid.uuid4())

        # Handle None metadata
        metadata = decision.metadata or {}

        # Normalize timestamp to ensure consistent storage format
        normalized_timestamp = self._normalize_timestamp(decision.timestamp)

        node = ContextNode(
            node_id=node_id,
            node_type="Decision",
            content=decision.scenario,
            properties={
                "category": decision.category,
                "reasoning": decision.reasoning,
                "outcome": decision.outcome,
                "confidence": decision.confidence,
                "timestamp": normalized_timestamp.isoformat(),
                "decision_maker": decision.decision_maker,
                "reasoning_embedding": decision.reasoning_embedding,
                "node2vec_embedding": decision.node2vec_embedding,
                **metadata
            },
            valid_from=decision.valid_from,
            valid_until=decision.valid_until,
        )
        self._add_internal_node(node)
        return node_id

    def add_causal_relationship(
        self,
        source_decision_id: str,
        target_decision_id: str,
        relationship_type: str
    ) -> None:
        """
        Add causal relationship between decisions.
        
        Args:
            source_decision_id: Source decision ID
            target_decision_id: Target decision ID
            relationship_type: Type of relationship (CAUSED, INFLUENCED, PRECEDENT_FOR)
        """
        valid_types = ["CAUSED", "INFLUENCED", "PRECEDENT_FOR"]
        if relationship_type not in valid_types:
            raise ValueError(f"Relationship type must be one of: {valid_types}")
        
        # Check if decisions exist - if not, skip adding relationship
        if source_decision_id not in self.nodes or target_decision_id not in self.nodes:
            return
        
        # Check if nodes are decision nodes - if not, skip adding relationship
        source_node = self.nodes[source_decision_id]
        target_node = self.nodes[target_decision_id]
        if (not hasattr(source_node, 'node_type') or not isinstance(source_node.node_type, str) or
            not hasattr(target_node, 'node_type') or not isinstance(target_node.node_type, str) or
            source_node.node_type.lower() != "decision" or 
            target_node.node_type.lower() != "decision"):
            return
        
        edge = ContextEdge(
            source_id=source_decision_id,
            target_id=target_decision_id,
            edge_type=relationship_type,
            weight=1.0,
            metadata={"recorded_at": datetime.utcnow().isoformat()},
        )
        self._add_internal_edge(edge)

    def get_causal_chain(
        self,
        decision_id: str,
        direction: str = "upstream",
        max_depth: int = 10
    ) -> List["Decision"]:
        """
        Get causal chain from graph.
        
        Args:
            decision_id: Starting decision ID
            direction: "upstream" or "downstream"
            max_depth: Maximum traversal depth
            
        Returns:
            List of decisions in causal chain
        """
        from .decision_models import Decision
        
        if direction not in ["upstream", "downstream"]:
            raise ValueError("Direction must be 'upstream' or 'downstream'")
        
        # BFS traversal
        visited = set()
        queue = deque([(decision_id, 0)])
        decisions = []
        
        while queue:
            current_id, depth = queue.popleft()
            
            if current_id in visited or depth > max_depth:
                continue
            
            visited.add(current_id)
            
            # Skip the starting decision - only add connected decisions
            if current_id != decision_id:
                # Get decision node
                if current_id in self.nodes:
                    node = self.nodes[current_id]
                    if (hasattr(node, 'node_type') and isinstance(node.node_type, str) and
                        node.node_type.lower() == "decision"):
                        decision_data = node.properties
                        timestamp = self._normalize_timestamp(decision_data.get("timestamp"))
                        decision = Decision(
                            decision_id=current_id,
                            category=decision_data.get("category", ""),
                            scenario=decision_data.get("scenario", node.content),
                            reasoning=decision_data.get("reasoning", ""),
                            outcome=decision_data.get("outcome", ""),
                            confidence=decision_data.get("confidence", 0.0),
                            timestamp=timestamp,
                            decision_maker=decision_data.get("decision_maker", ""),
                            reasoning_embedding=decision_data.get("reasoning_embedding"),
                            node2vec_embedding=decision_data.get("node2vec_embedding"),
                            valid_from=node.valid_from,
                            valid_until=node.valid_until,
                            metadata={k: v for k, v in decision_data.items() if k not in [
                                "category", "scenario", "reasoning", "outcome", "confidence", 
                                "timestamp", "decision_maker", "reasoning_embedding", "node2vec_embedding"
                            ]}
                        )
                        decision.metadata["causal_distance"] = depth
                        decisions.append(decision)
            
            # Find connected decisions
            for edge in self.edges:
                if direction == "upstream":
                    if edge.target_id == current_id and edge.edge_type in ["CAUSED", "INFLUENCED", "PRECEDENT_FOR"]:
                        if edge.source_id not in visited and depth < max_depth:
                            queue.append((edge.source_id, depth + 1))
                else:  # downstream
                    if edge.source_id == current_id and edge.edge_type in ["CAUSED", "INFLUENCED", "PRECEDENT_FOR"]:
                        if edge.target_id not in visited and depth < max_depth:
                            queue.append((edge.target_id, depth + 1))
        
        # Sort by depth for upstream (most distant first) and downstream (closest first)
        if direction == "upstream":
            decisions.sort(key=lambda d: d.metadata.get("causal_distance", 0), reverse=True)
        else:
            decisions.sort(key=lambda d: d.metadata.get("causal_distance", 0))
        
        return decisions

    def find_precedents(self, decision_id: str, limit: int = 10) -> List["Decision"]:
        """
        Find precedent decisions.
        
        Args:
            decision_id: Decision ID to find precedents for
            limit: Maximum number of results
            
        Returns:
            List of precedent decisions
        """
        # Find decisions connected via PRECEDENT_FOR relationships
        precedent_ids = []
        for edge in self.edges:
            if edge.target_id == decision_id and edge.edge_type == "PRECEDENT_FOR":
                precedent_ids.append(edge.source_id)
        
        # Convert to Decision objects
        decisions = []
        for pid in precedent_ids[:limit]:
            if pid in self.nodes:
                node = self.nodes[pid]
                if (hasattr(node, 'node_type') and isinstance(node.node_type, str) and
                    node.node_type.lower() == "decision"):
                    decision_data = node.properties
                    from .decision_models import Decision
                    timestamp = self._normalize_timestamp(decision_data.get("timestamp"))
                    decision = Decision(
                        decision_id=pid,
                        category=decision_data.get("category", ""),
                        scenario=decision_data.get("scenario", node.content),
                        reasoning=decision_data.get("reasoning", ""),
                        outcome=decision_data.get("outcome", ""),
                        confidence=decision_data.get("confidence", 0.0),
                        timestamp=timestamp,
                        decision_maker=decision_data.get("decision_maker", ""),
                        reasoning_embedding=decision_data.get("reasoning_embedding"),
                        node2vec_embedding=decision_data.get("node2vec_embedding"),
                        valid_from=node.valid_from,
                        valid_until=node.valid_until,
                        metadata={k: v for k, v in decision_data.items() if k not in [
                            "category", "scenario", "reasoning", "outcome", "confidence", 
                            "timestamp", "decision_maker", "reasoning_embedding", "node2vec_embedding"
                        ]}
                    )
                    decisions.append(decision)
        
        return decisions
    
    # Enhanced methods for comprehensive context graphs
    def analyze_graph_with_kg(self) -> Dict[str, Any]:
        """
        Analyze the context graph using advanced KG algorithms.
        
        Returns:
            Comprehensive graph analysis results
        """
        if not self.kg_components:
            self.logger.warning("KG components not available")
            return {"error": "Advanced features not available"}
        
        try:
            analysis = {
                "graph_metrics": {},
                "centrality_analysis": {},
                "community_analysis": {},
                "connectivity_analysis": {},
                "node_embeddings": {},
                "timestamp": datetime.now().isoformat()
            }
            
            # Convert to KG-compatible format
            kg_graph = self._to_kg_format()
            
            # Basic graph metrics
            analysis["graph_metrics"] = {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "node_types": self._get_node_type_distribution(),
                "edge_types": self._get_edge_type_distribution()
            }
            
            # Centrality analysis
            if "centrality_calculator" in self.kg_components:
                centrality = self.kg_components["centrality_calculator"].calculate_all_centrality(kg_graph)
                analysis["centrality_analysis"] = centrality
            
            # Community detection
            if "community_detector" in self.kg_components:
                communities = self.kg_components["community_detector"].detect_communities(kg_graph)
                analysis["community_analysis"] = {
                    "communities": communities,
                    "num_communities": len(communities),
                    "modularity": self._calculate_modularity(communities)
                }
            
            # Connectivity analysis
            if "connectivity_analyzer" in self.kg_components:
                connectivity = self.kg_components["connectivity_analyzer"].analyze_connectivity(kg_graph)
                analysis["connectivity_analysis"] = connectivity
            
            # Node embeddings
            if "node_embedder" in self.kg_components:
                node_labels = list(self.node_type_index.keys())
                relationship_types = list(self.edge_type_index.keys())
                if node_labels:
                    embeddings = self.kg_components["node_embedder"].compute_embeddings(
                        graph_store=self,
                        node_labels=node_labels,
                        relationship_types=relationship_types,
                    )
                    analysis["node_embeddings"] = embeddings
            
            self.logger.info("Completed comprehensive graph analysis")
            return analysis
            
        except AttributeError as e:
            # A broken internal method call (e.g. calling a method that doesn't
            # exist on one of the kg_components) is a programming error, not a
            # legitimate empty-analysis result. Log it distinctly and re-raise
            # rather than masking it under the generic message below.
            self.logger.error(f"Graph analysis failed due to a broken internal method call: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to analyze graph with KG: {e}")
            return {"error": "Graph analysis failed due to an internal error"}
    
    def get_node_centrality(self, node_id: str) -> Dict[str, float]:
        """
        Get centrality measures for a specific node.
        
        Args:
            node_id: Node ID to analyze
            
        Returns:
            Dictionary of centrality measures
        """
        if "centrality_calculator" not in self.kg_components:
            return {"error": "Centrality calculator not available"}
        
        if node_id not in self.nodes:
            return {"error": "Node not found"}
        
        # Check cache first
        cache_key = f"centrality_{node_id}"
        if cache_key in self._analytics_cache:
            return self._analytics_cache[cache_key]
        
        try:
            # Get subgraph around the node
            subgraph = self._get_node_subgraph(node_id, max_depth=2)
            
            # Calculate centrality
            centrality = self.kg_components["centrality_calculator"].calculate_all_centrality(subgraph)
            
            # Cache result
            self._analytics_cache[cache_key] = centrality.get(node_id, {})
            
            return centrality.get(node_id, {})
            
        except Exception as e:
            self.logger.error(f"Failed to get node centrality: {e}")
            return {"error": "Node centrality calculation failed due to an internal error"}
    
    def find_similar_nodes(
        self, node_id: str, similarity_type: str = "content", top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find similar nodes using various similarity measures.
        
        Args:
            node_id: Reference node ID
            similarity_type: Type of similarity ("embedding", "structural", "content")
            top_k: Number of similar nodes to return
            
        Returns:
            List of dicts with node ID, type, content, and similarity score
        """
        if node_id not in self.nodes:
            return []
        
        similar_nodes = []
        reference_node = self.nodes[node_id]
        
        try:
            for other_id, other_node in self.nodes.items():
                if other_id != node_id:
                    if similarity_type == "content":
                        similarity = self._calculate_content_similarity(reference_node, other_node)
                    elif similarity_type == "structural":
                        similarity = self._calculate_structural_similarity(reference_node, other_node)
                    else:
                        similarity = self._calculate_content_similarity(reference_node, other_node)
                    
                    similar_nodes.append({
                        "id": other_id,
                        "content": other_node.content,
                        "type": other_node.node_type,
                        "score": similarity,
                    })

            # Sort by similarity and return top_k
            similar_nodes.sort(key=lambda x: x["score"], reverse=True)
            return similar_nodes[:top_k]
            
        except Exception as e:
            self.logger.error(f"Failed to find similar nodes: {e}")
            return []
    
    # Helper methods for KG integration
    def _to_kg_format(self) -> Dict[str, Any]:
        """Convert context graph to KG-compatible format."""
        nodes = []
        edges = []
        relationships = []
        
        # Convert nodes
        for node_id, node in self.nodes.items():
            nodes.append({
                "id": node_id,
                "type": node.node_type,
                "properties": node.properties,
                "content": node.content
            })
        
        # Convert edges
        for edge in self.edges:
            edge_data = {
                "source": edge.source_id,
                "target": edge.target_id,
                "type": edge.edge_type,
                "weight": edge.weight,
                "properties": edge.metadata
            }
            edges.append(edge_data)
            relationships.append(edge_data)
        
        return {
            "nodes": nodes, 
            "edges": edges,
            "relationships": relationships  # KG algorithms expect this key
        }
    
    def _get_node_type_distribution(self) -> Dict[str, int]:
        """Get distribution of node types."""
        from collections import defaultdict
        distribution = defaultdict(int)
        for node in self.nodes.values():
            distribution[node.node_type] += 1
        return dict(distribution)
    
    def _get_edge_type_distribution(self) -> Dict[str, int]:
        """Get distribution of edge types."""
        from collections import defaultdict
        distribution = defaultdict(int)
        for edge in self.edges:
            distribution[edge.edge_type] += 1
        return dict(distribution)
    
    def _calculate_modularity(self, communities: Dict) -> float:
        """Calculate modularity for communities (simplified)."""
        # Placeholder for modularity calculation
        return 0.5
    
    def _get_node_subgraph(self, node_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """Get subgraph around a node."""
        neighbors = self.get_neighbors(node_id, hops=max_depth)
        
        subgraph_nodes = {node_id}
        subgraph_edges = []
        
        for neighbor in neighbors:
            neighbor_id = neighbor["id"]
            subgraph_nodes.add(neighbor_id)
        
        # Add edges between nodes in subgraph
        for edge in self.edges:
            if edge.source_id in subgraph_nodes and edge.target_id in subgraph_nodes:
                subgraph_edges.append({
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "type": edge.edge_type,
                    "weight": edge.weight
                })
        
        return {
            "nodes": [{"id": nid} for nid in subgraph_nodes],
            "edges": subgraph_edges
        }
    
    def _calculate_structural_similarity(self, node1: ContextNode, node2: ContextNode) -> float:
        """Calculate structural similarity between two nodes."""
        # Simple structural similarity based on node types and connections
        if node1.node_type != node2.node_type:
            return 0.0
        
        # Count connections
        connections1 = len(self._adjacency.get(node1.node_id, []))
        connections2 = len(self._adjacency.get(node2.node_id, []))
        
        # Similarity based on connection count similarity
        max_connections = max(connections1, connections2, 1)
        return 1.0 - abs(connections1 - connections2) / max_connections
    
    def _calculate_content_similarity(self, node1: ContextNode, node2: ContextNode) -> float:
        """Calculate content similarity between two nodes."""
        words1 = set(node1.content.lower().split())
        words2 = set(node2.content.lower().split())
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    # --- Comprehensive Decision Management Features ---
    
    def record_decision(
        self,
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float,
        entities: Optional[List[str]] = None,
        decision_maker: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        valid_from: Optional[Union[str, int, float, datetime]] = None,
        valid_until: Optional[Union[str, int, float, datetime]] = None,
        **kwargs
    ) -> str:
        """
        Record a decision with full context and analytics.
        
        Args:
            category: Decision category (e.g., "loan_approval")
            scenario: Decision scenario description
            reasoning: Decision reasoning explanation
            outcome: Decision outcome
            confidence: Confidence score (0.0 to 1.0)
            entities: Related entities
            decision_maker: Who made the decision
            metadata: Additional metadata
            **kwargs: Additional decision data
            
        Returns:
            Decision ID for reference
        """
        import uuid
        from datetime import datetime
        
        # Input validation
        if not isinstance(category, str) or not category.strip():
            raise ValueError("Category must be a non-empty string")
        if len(category.strip()) > 100:
            raise ValueError("Category must be 100 characters or less")
        
        if not isinstance(scenario, str) or not scenario.strip():
            raise ValueError("Scenario must be a non-empty string")
        if len(scenario.strip()) > 5000:
            raise ValueError("Scenario must be 5000 characters or less")
        
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise ValueError("Reasoning must be a non-empty string")
        if len(reasoning.strip()) > 10000:
            raise ValueError("Reasoning must be 10000 characters or less")
        
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError("Outcome must be a non-empty string")
        if len(outcome.strip()) > 1000:
            raise ValueError("Outcome must be 1000 characters or less")
        
        if not isinstance(confidence, (int, float)):
            raise ValueError("Confidence must be a number")
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        
        if entities is not None:
            if not isinstance(entities, list):
                raise ValueError("Entities must be a list of strings")
            for entity in entities:
                if not isinstance(entity, str) or not entity.strip():
                    raise ValueError("Each entity must be a non-empty string")
                if len(entity.strip()) > 200:
                    raise ValueError("Each entity must be 200 characters or less")
        
        if decision_maker is not None:
            if not isinstance(decision_maker, str) or not decision_maker.strip():
                raise ValueError("Decision maker must be a non-empty string")
            if len(decision_maker.strip()) > 200:
                raise ValueError("Decision maker must be 200 characters or less")
        
        if metadata is not None:
            if not isinstance(metadata, dict):
                raise ValueError("Metadata must be a dictionary")
            for key, value in metadata.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError("Metadata keys must be non-empty strings")
                if len(key.strip()) > 100:
                    raise ValueError("Metadata keys must be 100 characters or less")
                if len(str(value)) > 1000:
                    raise ValueError("Metadata values must be 1000 characters or less")
        
        # Validate kwargs
        for key, value in kwargs.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Additional field names must be non-empty strings")
            if len(key.strip()) > 100:
                raise ValueError("Additional field names must be 100 characters or less")
            if len(str(value)) > 1000:
                raise ValueError("Additional field values must be 1000 characters or less")
        
        decision_id = str(uuid.uuid4())
        timestamp = datetime.now().timestamp()
        
        # Sanitize inputs
        category = category.strip()
        scenario = scenario.strip()
        reasoning = reasoning.strip()
        outcome = outcome.strip()
        confidence = float(confidence)
        entities = [entity.strip() for entity in (entities or []) if entity.strip()]
        decision_maker = decision_maker.strip() if decision_maker else None
        normalized_valid_from = _normalize_temporal_input(valid_from)
        normalized_valid_until = _normalize_temporal_input(valid_until)
        
        # Create decision record
        decision = {
            "id": decision_id,
            "category": category,
            "scenario": scenario,
            "reasoning": reasoning,
            "outcome": outcome,
            "confidence": confidence,
            "entities": entities,
            "decision_maker": decision_maker,
            "timestamp": timestamp,
            "recorded_at": datetime.utcnow().isoformat(),
            "valid_from": normalized_valid_from,
            "valid_until": normalized_valid_until,
            "metadata": metadata or {},
            **kwargs
        }
        
        # Store decision in graph
        self._add_decision_to_graph(decision)
        
        # Store in internal decision storage
        if not hasattr(self, '_decisions'):
            self._decisions = {}
            self._decision_index = defaultdict(set)
            self._entity_index = defaultdict(set)
            self._temporal_index = []
        
        self._decisions[decision_id] = decision
        self._decision_index[category].add(decision_id)
        
        for entity in entities or []:
            self._entity_index[entity].add(decision_id)
        
        self._temporal_index.append((decision_id, timestamp))
        self._temporal_index.sort(key=lambda x: x[1], reverse=True)
        
        self.logger.info(f"Recorded decision {decision_id} in category {category}")
        return decision_id
    
    def find_precedents_by_scenario(
        self,
        scenario: str,
        category: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.5,
        use_semantic_search: bool = True,
        include_superseded: bool = False,
        as_of: Optional[Union[str, int, float, datetime]] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Find similar decisions (precedents) using hybrid search.
        
        Args:
            scenario: Scenario to find precedents for
            category: Filter by decision category
            limit: Maximum number of precedents
            similarity_threshold: Minimum similarity score
            use_semantic_search: Use vector embeddings for search
            **filters: Additional filters
            
        Returns:
            List of similar decisions with similarity scores
        """
        if not hasattr(self, '_decisions') or not self._decisions:
            return []
        as_of_time = self._normalize_timestamp(as_of) if as_of is not None else None
        
        candidates = set()
        
        # Get candidates by category
        if category:
            candidates.update(self._decision_index.get(category, set()))
        else:
            candidates.update(self._decisions.keys())
        
        # Filter by entities if provided
        if "entities" in filters:
            entity_candidates = set()
            for entity in filters["entities"]:
                entity_candidates.update(self._entity_index.get(entity, set()))
            candidates = candidates.intersection(entity_candidates)
        
        # Calculate similarities
        precedents = []
        for decision_id in candidates:
            decision = self._decisions[decision_id]
            if not self._decision_matches_temporal_filters(
                decision,
                include_superseded=include_superseded,
                as_of=as_of_time,
            ):
                continue
            
            # Content similarity
            content_sim = self._calculate_decision_content_similarity(scenario, decision)
            
            # Structural similarity (graph-based)
            structural_sim = 0.0
            if self.config.get("advanced_analytics"):
                structural_sim = self._calculate_structural_similarity_for_decision(decision_id, scenario)
            
            # Combined similarity
            combined_sim = 0.7 * content_sim + 0.3 * structural_sim
            
            if combined_sim >= similarity_threshold:
                precedents.append({
                    "decision": decision,
                    "similarity": combined_sim,
                    "content_similarity": content_sim,
                    "structural_similarity": structural_sim
                })
        
        # Sort by similarity and limit
        precedents.sort(key=lambda x: x["similarity"], reverse=True)
        return precedents[:limit]
    
    def analyze_decision_influence(
        self,
        decision_id: str,
        max_depth: int = 3,
        include_indirect: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze decision influence and impact.
        
        Args:
            decision_id: Decision to analyze
            max_depth: Maximum depth for influence analysis
            include_indirect: Include indirect influences
            
        Returns:
            Influence analysis results
        """
        if not hasattr(self, '_decisions') or decision_id not in self._decisions:
            raise ValueError(f"Decision {decision_id} not found")
        
        decision = self._decisions[decision_id]
        
        # Direct influence (same entities, category)
        direct_influence = set()
        for entity in decision["entities"]:
            direct_influence.update(self._entity_index.get(entity, set()))
        direct_influence.discard(decision_id)
        direct_influence.update(self._decision_index.get(decision["category"], set()))
        direct_influence.discard(decision_id)
        
        # Indirect influence (through graph relationships)
        indirect_influence = set()
        if include_indirect and self.config.get("advanced_analytics"):
            indirect_influence = self._find_indirect_decision_influence(decision_id, max_depth)
        
        # Calculate influence scores
        influence_scores = {}
        for influenced_id in direct_influence | indirect_influence:
            influence_scores[influenced_id] = self._calculate_decision_influence_score(
                decision_id, influenced_id
            )
        
        # Sort by influence score
        sorted_influence = sorted(
            influence_scores.items(),
            key=lambda x: x[1].get("score", 0.0),
            reverse=True
        )
        
        def _enrich(did: str) -> Dict[str, Any]:
            dec = self._decisions.get(did, {})
            return {
                "decision_id": did,
                "scenario": dec.get("scenario", ""),
                "outcome": dec.get("outcome", ""),
                "category": dec.get("category", ""),
            }

        return {
            "decision_id": decision_id,
            "direct_influence": [_enrich(did) for did in direct_influence],
            "indirect_influence": [_enrich(did) for did in indirect_influence],
            "influence_scores": [
                {
                    **_enrich(did),
                    "score": details.get("score", 0.0),
                    "score_breakdown": {
                        "entity_overlap": details.get("entity_score", 0.0),
                        "category_match": details.get("category_score", 0.0),
                        "temporal_proximity": details.get("time_score", 0.0),
                    },
                    "is_direct": did in direct_influence,
                }
                for did, details in sorted_influence
            ],
            "total_influenced": len(influence_scores),
            "max_influence_score": max(
                details.get("score", 0.0) for details in influence_scores.values()
            ) if influence_scores else 0.0
        }
    
    def get_decision_insights(self) -> Dict[str, Any]:
        """
        Get comprehensive insights about all decisions.
        
        Returns:
            Comprehensive analytics and insights
        """
        if not hasattr(self, '_decisions') or not self._decisions:
            return {"message": "No decisions recorded yet"}
        
        # Basic statistics
        total_decisions = len(self._decisions)
        categories = {}
        outcomes = {}
        confidence_scores = []
        
        for decision in self._decisions.values():
            # Category distribution
            categories[decision["category"]] = categories.get(decision["category"], 0) + 1
            
            # Outcome distribution
            outcomes[decision["outcome"]] = outcomes.get(decision["outcome"], 0) + 1
            
            # Confidence scores
            confidence_scores.append(decision["confidence"])
        
        # Advanced analytics (if available)
        advanced_insights = {}
        if self.config.get("advanced_analytics"):
            advanced_insights = self.analyze_graph_with_kg()
        
        # Temporal analysis
        temporal_insights = self._get_decision_temporal_analysis()
        
        # Entity analysis
        entity_insights = self._get_decision_entity_analysis()
        
        return {
            "total_decisions": total_decisions,
            "categories": categories,
            "outcomes": outcomes,
            "confidence_stats": {
                "mean": sum(confidence_scores) / len(confidence_scores),
                "min": min(confidence_scores),
                "max": max(confidence_scores),
                "median": sorted(confidence_scores)[len(confidence_scores) // 2]
            },
            "advanced_analytics": advanced_insights,
            "temporal_analysis": temporal_insights,
            "entity_analysis": entity_insights,
            "graph_metrics": self.get_graph_metrics() if hasattr(self, 'get_graph_metrics') else {}
        }
    
    def trace_decision_causality(
        self,
        decision_id: str,
        max_depth: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Trace causal chain for a decision.
        
        Args:
            decision_id: Decision to trace
            max_depth: Maximum depth for causal analysis
            
        Returns:
            Causal chain as list of decision relationships
        """
        if not hasattr(self, '_decisions') or decision_id not in self._decisions:
            raise ValueError(f"Decision {decision_id} not found")
        
        try:
            # Use graph traversal to find causal relationships
            causal_chain = []
            visited = set()
            
            def trace_recursive(current_id, depth, path):
                if depth >= max_depth or current_id in visited:
                    return
                
                visited.add(current_id)
                current_decision = self._decisions[current_id]
                
                # Find potential causes (decisions that influenced this one)
                potential_causes = []
                for entity in current_decision["entities"]:
                    for other_decision_id in self._entity_index.get(entity, set()):
                        if other_decision_id != current_id:
                            other_decision = self._decisions[other_decision_id]
                            if other_decision["timestamp"] < current_decision["timestamp"]:
                                potential_causes.append(other_decision_id)
                
                for cause_id in potential_causes:
                    cause_dec = self._decisions.get(cause_id, {})
                    edge_weight = float(cause_dec.get("confidence", 1.0))
                    hop = {
                        "from": cause_id,
                        "from_scenario": cause_dec.get("scenario", ""),
                        "to": current_id,
                        "to_scenario": current_decision.get("scenario", ""),
                        "type": "influences",
                        "edge_weight": edge_weight,
                    }
                    cause_path = path + [hop]
                    causal_chain.append(self._build_causal_chain_report(list(reversed(cause_path))))
                    trace_recursive(cause_id, depth + 1, cause_path)
            
            trace_recursive(decision_id, 0, [])
            return causal_chain
            
        except Exception as e:
            self.logger.error(f"Causal analysis failed: {e}")
            return [{"error": "Causal analysis failed due to an internal error"}]
    
    def enforce_decision_policy(
        self,
        decision_data: Dict[str, Any],
        policy_rules: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enforce policies on decision data.
        
        Args:
            decision_data: Decision data to check
            policy_rules: Policy rules to enforce
            
        Returns:
            Policy enforcement results
        """
        # Simple policy enforcement implementation
        violations = []
        warnings = []
        
        # Default policy rules
        default_rules = {
            "min_confidence": 0.7,
            "required_outcomes": ["approved", "rejected", "flagged"],
            "required_metadata": ["decision_maker"],
            "max_reasoning_length": 1000
        }
        
        rules = policy_rules or default_rules
        
        # Check confidence
        if decision_data.get("confidence", 0) < rules.get("min_confidence", 0.7):
            violations.append(f"Confidence too low: {decision_data.get('confidence', 0)}")
        
        # Check outcome
        if decision_data.get("outcome") not in rules.get("required_outcomes", []):
            violations.append(f"Invalid outcome: {decision_data.get('outcome')}")
        
        # Check required metadata
        for required_field in rules.get("required_metadata", []):
            if not decision_data.get(required_field):
                violations.append(f"Missing required field: {required_field}")
        
        # Check reasoning length
        reasoning = decision_data.get("reasoning", "")
        if len(reasoning) > rules.get("max_reasoning_length", 1000):
            warnings.append(f"Reasoning too long: {len(reasoning)} characters")
        
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "policy_rules": rules
        }
    
    # --- Private helper methods for decision management ---
    
    def _add_decision_to_graph(self, decision: Dict[str, Any]) -> None:
        """Add decision to context graph."""
        try:
            protected_properties = {
                "category",
                "scenario",
                "reasoning",
                "outcome",
                "confidence",
                "timestamp",
                "decision_maker",
            }
            safe_metadata = {
                key: value
                for key, value in (decision.get("metadata") or {}).items()
                if key not in protected_properties
            }
            extra_properties = {
                key: value
                for key, value in decision.items()
                if key not in {
                    "id",
                    "category",
                    "scenario",
                    "reasoning",
                    "outcome",
                    "confidence",
                    "entities",
                    "decision_maker",
                    "timestamp",
                    "recorded_at",
                    "valid_from",
                    "valid_until",
                    "metadata",
                }
            }
            # Add decision node
            self.add_node(
                decision["id"],
                "decision",
                content=decision["scenario"],
                valid_from=decision.get("valid_from"),
                valid_until=decision.get("valid_until"),
                category=decision["category"],
                outcome=decision["outcome"],
                confidence=decision["confidence"],
                timestamp=decision["timestamp"],
                scenario=decision["scenario"],
                decision_maker=decision.get("decision_maker", ""),
                reasoning=decision["reasoning"],
                **safe_metadata,
                **extra_properties,
            )
            
            # Add entity nodes and relationships
            for entity in decision["entities"]:
                # Add entity node if not exists
                if not self.find_node(entity):
                    self.add_node(
                        entity,
                        "entity",
                        name=entity
                    )
                
                # Add relationship
                self.add_edge(
                    decision["id"],
                    entity,
                    "involves",
                    confidence=decision["confidence"]
                )
            
            # Add category node and relationship
            category_id = f"category_{decision['category']}"
            if not self.find_node(category_id):
                self.add_node(
                    category_id,
                    "category",
                    name=decision["category"]
                )
            
            self.add_edge(
                decision["id"],
                category_id,
                "belongs_to"
            )
            
            # Add decision maker node if provided
            if decision.get("decision_maker"):
                maker_id = f"maker_{decision['decision_maker']}"
                if not self.find_node(maker_id):
                    self.add_node(
                        maker_id,
                        "decision_maker",
                        name=decision["decision_maker"]
                    )
                
                self.add_edge(
                    decision["id"],
                    maker_id,
                    "made_by"
                )
            
        except Exception as e:
            self.logger.exception("Failed to add decision to graph")

    def _decision_matches_temporal_filters(
        self,
        decision: Dict[str, Any],
        include_superseded: bool = False,
        as_of: Optional[datetime] = None,
    ) -> bool:
        """Return True when a decision matches temporal filter rules."""
        valid_from = _parse_iso_dt(decision.get("valid_from")) if decision.get("valid_from") else None
        valid_until = _parse_iso_dt(decision.get("valid_until")) if decision.get("valid_until") else None
        reference_time = as_of or datetime.utcnow()

        if as_of is not None:
            if valid_from is not None and reference_time < valid_from:
                return False
            if valid_until is not None and reference_time > valid_until:
                return False
            return True

        if include_superseded:
            return True

        if valid_until is not None and reference_time > valid_until:
            return False
        return True
    
    def _calculate_decision_content_similarity(self, scenario: str, decision: Dict[str, Any]) -> float:
        """Calculate content similarity between scenario and decision."""
        try:
            # Simple word-based similarity
            scenario_words = set(scenario.lower().split())
            decision_text = f"{decision['scenario']} {decision['reasoning']} {' '.join(decision['entities'])}"
            decision_words = set(decision_text.lower().split())
            
            intersection = scenario_words.intersection(decision_words)
            union = scenario_words.union(decision_words)
            
            return len(intersection) / len(union) if union else 0.0
            
        except Exception as e:
            self.logger.exception("Content similarity calculation failed")
            return 0.0
    
    def _calculate_structural_similarity_for_decision(self, decision_id: str, scenario: str) -> float:
        """Calculate structural similarity using graph algorithms."""
        try:
            if not self.config.get("advanced_analytics"):
                return 0.0
            
            # Use graph similarity algorithms
            similar_nodes = self.find_similar_nodes(
                decision_id,
                similarity_type="structural",
                top_k=5
            )
            
            if similar_nodes:
                return max(
                    item.get("score", 0.0)
                    for item in similar_nodes
                    if isinstance(item, dict)
                )
            
        except Exception as e:
            self.logger.exception("Structural similarity calculation failed")
        
        return 0.0
    
    def _find_indirect_decision_influence(self, decision_id: str, max_depth: int) -> Set[str]:
        """Find indirect influences using graph traversal."""
        try:
            influenced = set()
            
            # Get neighbors in graph
            neighbors = self.get_neighbors(decision_id, hops=max_depth)
            
            for neighbor in neighbors:
                if neighbor.get("type") == "decision":
                    influenced.add(neighbor["id"])
            
            return influenced
            
        except Exception as e:
            self.logger.warning(f"Indirect influence analysis failed: {e}")
            return set()
    
    def _build_causal_chain_report(self, hops: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build an auditable causal-chain response from hop records."""
        hop_count = len(hops)
        confidence_decay = 1.0
        weakest_link = None
        for hop in hops:
            edge_weight = float(hop.get("edge_weight", 1.0))
            confidence_decay *= edge_weight
            if weakest_link is None or edge_weight < float(weakest_link.get("edge_weight", 1.0)):
                weakest_link = hop

        if hop_count <= 1:
            interpretation = f"Direct influence with confidence {confidence_decay:.2f}."
        elif confidence_decay > 0.7:
            interpretation = (
                f"Mediated through {hop_count - 1} step(s) with high confidence "
                f"({confidence_decay:.2f})."
            )
        elif confidence_decay > 0.4:
            interpretation = (
                f"Mediated through {hop_count - 1} step(s) - confidence decays "
                f"to {confidence_decay:.2f}."
            )
        else:
            interpretation = (
                f"Distal influence across {hop_count} causal steps; confidence "
                f"{confidence_decay:.2f} is weak evidence."
            )

        return _CausalChain({
            "hops": hops,
            "hop_count": hop_count,
            "confidence_decay": confidence_decay,
            "weakest_link": weakest_link,
            "distance_band": classify_path_distance(hop_count),
            "interpretation": interpretation,
        })

    def _calculate_decision_influence_score(self, source_id: str, target_id: str) -> Dict[str, float]:
        """Calculate influence score between two decisions."""
        try:
            if not hasattr(self, '_decisions'):
                return {"score": 0.0, "entity_score": 0.0, "category_score": 0.0, "time_score": 0.0}
                
            source_decision = self._decisions[source_id]
            target_decision = self._decisions[target_id]
            
            # Base score from shared entities
            shared_entities = set(source_decision["entities"]) & set(target_decision["entities"])
            entity_score = len(shared_entities) / max(len(source_decision["entities"]), 1)
            
            # Category similarity
            category_score = 1.0 if source_decision["category"] == target_decision["category"] else 0.0
            
            # Temporal proximity (more recent decisions have higher influence)
            time_diff = abs(source_decision["timestamp"] - target_decision["timestamp"])
            time_score = max(0.0, 1.0 - time_diff / (30 * 24 * 3600))  # 30 days window
            
            # Combined score
            combined_score = 0.5 * entity_score + 0.3 * category_score + 0.2 * time_score
            
            return {
                "score": combined_score,
                "entity_score": entity_score,
                "category_score": category_score,
                "time_score": time_score,
            }
            
        except Exception as e:
            self.logger.warning(f"Influence score calculation failed: {e}")
            return {"score": 0.0, "entity_score": 0.0, "category_score": 0.0, "time_score": 0.0}
    
    def _get_decision_temporal_analysis(self) -> Dict[str, Any]:
        """Get temporal analysis of decisions."""
        try:
            if not hasattr(self, '_temporal_index') or not self._temporal_index:
                return {}
            
            # Group decisions by time periods
            recent_decisions = [did for did, ts in self._temporal_index[:10]]
            
            return {
                "recent_decisions": len(recent_decisions),
                "oldest_decision": min(ts for _, ts in self._temporal_index),
                "newest_decision": max(ts for _, ts in self._temporal_index),
                "time_span": max(ts for _, ts in self._temporal_index) - min(ts for _, ts in self._temporal_index)
            }
            
        except Exception as e:
            self.logger.warning(f"Temporal analysis failed: {e}")
            return {}
    
    def _get_decision_entity_analysis(self) -> Dict[str, Any]:
        """Get entity analysis from decisions."""
        try:
            if not hasattr(self, '_decisions'):
                return {}
                
            entity_counts = {}
            for decision in self._decisions.values():
                for entity in decision["entities"]:
                    entity_counts[entity] = entity_counts.get(entity, 0) + 1
            
            # Get top entities
            top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            
            return {
                "total_entities": len(entity_counts),
                "top_entities": top_entities,
                "avg_entities_per_decision": sum(len(d["entities"]) for d in self._decisions.values()) / len(self._decisions)
            }
            
        except Exception as e:
            self.logger.warning(f"Entity analysis failed: {e}")
            return {}
    
    # --- Easy-to-Use Convenience Methods ---
    
    def add_decision_simple(
        self,
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float = 0.5,
        entities: Optional[List[str]] = None,
        decision_maker: Optional[str] = "system",
        **kwargs
    ) -> str:
        """
        Easy way to record a decision.
        
        Args:
            category: Decision category (e.g., "loan_approval")
            scenario: What was the situation
            reasoning: Why was this decision made
            outcome: What was decided
            confidence: How confident (0.0 to 1.0)
            entities: Related entities (people, items, etc.)
            decision_maker: Who made the decision
            **kwargs: Additional information
            
        Returns:
            Decision ID for reference
        """
        return self.record_decision(
            category=category,
            scenario=scenario,
            reasoning=reasoning,
            outcome=outcome,
            confidence=confidence,
            entities=entities,
            decision_maker=decision_maker,
            metadata=kwargs
        )
    
    def find_similar_decisions(
        self,
        scenario: str,
        category: Optional[str] = None,
        max_results: int = 10,
        min_similarity: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Easy way to find similar past decisions.
        
        Args:
            scenario: What situation are you looking for
            category: Filter by decision type
            max_results: Maximum results to return
            min_similarity: Minimum similarity score
            
        Returns:
            List of similar decisions with similarity scores
        """
        return self.find_precedents_by_scenario(
            scenario=scenario,
            category=category,
            limit=max_results,
            similarity_threshold=min_similarity
        )
    
    def analyze_decision_impact(
        self,
        decision_id: str,
        include_indirect: bool = True
    ) -> Dict[str, Any]:
        """
        Easy way to analyze how a decision impacts others.
        
        Args:
            decision_id: Decision to analyze
            include_indirect: Include indirect impacts
            
        Returns:
            Impact analysis results
        """
        return self.analyze_decision_influence(
            decision_id=decision_id,
            max_depth=3,
            include_indirect=include_indirect
        )
    
    def get_decision_summary(self) -> Dict[str, Any]:
        """
        Easy way to get a summary of all decisions.
        
        Returns:
            Summary statistics and insights
        """
        return self.get_decision_insights()
    
    def trace_decision_chain(
        self,
        decision_id: str,
        max_steps: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Easy way to trace how decisions are connected.
        
        Args:
            decision_id: Starting decision
            max_steps: Maximum steps to trace
            
        Returns:
            Decision chain connections
        """
        return self.trace_decision_causality(
            decision_id=decision_id,
            max_depth=max_steps
        )
    
    def check_decision_rules(
        self,
        decision_data: Dict[str, Any],
        rules: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Easy way to check if a decision follows the rules.
        
        Args:
            decision_data: Decision to check
            rules: Custom rules (uses default if None)
            
        Returns:
            Compliance check results
        """
        return self.enforce_decision_policy(
            decision_data=decision_data,
            policy_rules=rules
        )
    
    def get_graph_summary(self) -> Dict[str, Any]:
        """
        Easy way to get graph statistics.
        
        Returns:
            Graph summary information
        """
        if hasattr(self, 'get_graph_metrics'):
            return self.get_graph_metrics()
        else:
            return {
                "nodes": len(self.nodes),
                "edges": len(self.edges),
                "node_types": self._get_node_type_distribution(),
                "edge_types": self._get_edge_type_distribution()
            }
    
    def find_related_nodes(
        self,
        node_id: str,
        how_many: int = 10,
        similarity_type: str = "content"
    ) -> List[Dict[str, Any]]:
        """
        Easy way to find nodes similar to a given node.
        
        Args:
            node_id: Reference node
            how_many: How many similar nodes to find
            similarity_type: Type of similarity ("content", "structural")
            
        Returns:
            List of dicts with node ID, type, content, and similarity score
        """
        return self.find_similar_nodes(
            node_id=node_id,
            similarity_type=similarity_type,
            top_k=how_many
        )
    
    def get_node_importance(
        self,
        node_id: str
    ) -> Dict[str, float]:
        """
        Easy way to get how important a node is in the graph.
        
        Args:
            node_id: Node to analyze
            
        Returns:
            Centrality measures (importance scores)
        """
        return self.get_node_centrality(node_id)
    
    def analyze_connections(self) -> Dict[str, Any]:
        """
        Easy way to analyze the entire graph structure.
        
        Returns:
            Graph analysis results
        """
        return self.analyze_graph_with_kg()


# For backward compatibility
ContextGraphBuilder = ContextGraph
