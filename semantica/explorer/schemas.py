"""
Shared Pydantic schemas for the Semantica Knowledge Explorer API.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class ErrorResponse(BaseModel):
    detail: str
    status_code: int = 500


class NodeResponse(BaseModel):
    id: str
    type: str
    content: str = ""
    properties: Dict[str, Any] = Field(default_factory=dict)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None


class EdgeResponse(BaseModel):
    id: str
    familyId: str
    source: str
    target: str
    type: str
    weight: float = 1.0
    properties: Dict[str, Any] = Field(default_factory=dict)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None


class NodeListResponse(BaseModel):
    nodes: List[NodeResponse]
    total: int
    skip: int = 0
    limit: int = 100
    next_cursor: Optional[str] = None
    has_more: bool = False


class EdgeListResponse(BaseModel):
    edges: List[EdgeResponse]
    total: int
    skip: int = 0
    limit: int = 100
    next_cursor: Optional[str] = None
    has_more: bool = False


class NeighborResponse(BaseModel):
    id: str
    type: str
    content: str = ""
    relationship: str = ""
    weight: float = 1.0
    hop: int = 1


class PathResponse(BaseModel):
    source: str
    target: str
    algorithm: str
    path: List[str]
    edge_ids: List[str] = Field(default_factory=list)
    total_weight: float = 0.0
    directed: bool = True
    hop_count: int = 0
    distance_band: str = "direct"
    # FR-4 enrichment fields — all optional; existing callers unaffected
    semantic_similarity: Optional[float] = None
    path_coherence_score: Optional[float] = None
    confidence_decay: Optional[float] = None
    bottleneck_node: Optional[str] = None
    alternative_path_count: int = 0
    interpretation: str = ""


class GraphStatsResponse(BaseModel):
    node_count: int
    edge_count: int
    node_types: Dict[str, int] = Field(default_factory=dict)
    edge_types: Dict[str, int] = Field(default_factory=dict)
    density: float = 0.0


class SearchRequest(BaseModel):
    query: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=200)
    # FR-7 proximity constraint fields
    anchor_node: Optional[str] = None
    max_hops: Optional[int] = None
    min_semantic_similarity: Optional[float] = None
    rank_by: Literal["relevance", "proximity", "hybrid"] = "relevance"


class SearchResultItem(BaseModel):
    node: NodeResponse
    score: float = 0.0
    # FR-7 distance metadata
    hop_distance: Optional[int] = None
    semantic_similarity: Optional[float] = None


class SearchResultResponse(BaseModel):
    results: List[SearchResultItem]
    total: int
    query: str


class AnalyticsResponse(BaseModel):
    centrality: Optional[Dict[str, Any]] = None
    community: Optional[Dict[str, Any]] = None
    connectivity: Optional[Dict[str, Any]] = None


class ValidationIssue(BaseModel):
    severity: str
    message: str
    node_id: Optional[str] = None
    edge_source: Optional[str] = None
    edge_target: Optional[str] = None


class ValidationReportResponse(BaseModel):
    valid: bool
    error_count: int = 0
    warning_count: int = 0
    issues: List[ValidationIssue] = Field(default_factory=list)


class DecisionResponse(BaseModel):
    decision_id: str
    category: str = ""
    scenario: str = ""
    reasoning: str = ""
    outcome: str = ""
    confidence: float = 0.0
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(cls, value: Any) -> Optional[str]:
        """Accept the epoch floats ContextGraph.record_decision() writes.

        Decision nodes store ``timestamp`` as ``datetime.now().timestamp()``, a
        float, so passing the stored value through unconverted fails validation
        and turns every decision route into a 500. Normalize to ISO-8601 here so
        the wire format stays a single string type whatever the producer wrote.
        """
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            import math
            if not math.isfinite(value):
                raise ValueError(
                    f"timestamp must be a finite number, got {value!r}"
                )
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
            except (OverflowError, OSError) as exc:
                raise ValueError(
                    f"timestamp {value!r} is out of the representable epoch range"
                ) from exc
        raise ValueError(
            f"timestamp must be None, a string, a datetime, or a numeric epoch; "
            f"got {type(value).__name__!r}"
        )


class CausalChainResponse(BaseModel):
    decision_id: str
    chain: List[Dict[str, Any]] = Field(default_factory=list)


class ComplianceResponse(BaseModel):
    decision_id: str
    compliant: bool = True
    violations: List[Dict[str, Any]] = Field(default_factory=list)


class TemporalSnapshotResponse(BaseModel):
    timestamp: str
    active_nodes: List[NodeResponse]
    active_node_count: int


class TemporalDiffResponse(BaseModel):
    from_time: str
    to_time: str
    added_nodes: List[str] = Field(default_factory=list)
    removed_nodes: List[str] = Field(default_factory=list)


class TemporalPatternResponse(BaseModel):
    patterns: List[Dict[str, Any]] = Field(default_factory=list)


class EnrichExtractRequest(BaseModel):
    # 10 000 characters is sufficient for a substantial document paragraph while
    # preventing unbounded spaCy NLP processing on arbitrarily large payloads.
    text: str = Field(..., max_length=10_000)


class EnrichExtractResponse(BaseModel):
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    relations: List[Dict[str, Any]] = Field(default_factory=list)


class LinkPredictionRequest(BaseModel):
    node_id: str
    top_n: int = Field(default=10, ge=1, le=200)
    candidate_type: Optional[str] = None
    min_score: float = Field(default=0.0, ge=0.0)


class LinkPredictionResponse(BaseModel):
    node_id: str
    predictions: List[Dict[str, Any]] = Field(default_factory=list)


class DedupRequest(BaseModel):
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class DedupResponse(BaseModel):
    duplicates: List[Dict[str, Any]] = Field(default_factory=list)
    total_flagged: int = 0


class ReasoningRequest(BaseModel):
    facts: List[str]
    rules: List[str]
    mode: str = "forward"
    apply_to_graph: bool = False
    inferred_edge_type: Optional[str] = None


class ReasoningResponse(BaseModel):
    inferred_facts: List[str] = Field(default_factory=list)
    rules_fired: int = 0
    added_edges: int = 0
    mutated: bool = False


class ExportRequest(BaseModel):
    format: str = "json"
    node_ids: Optional[List[str]] = None


class ExportResponse(BaseModel):
    format: str
    content_type: str
    filename: str
    size_bytes: int = 0


class ImportResponse(BaseModel):
    status: str = "success"
    message: str = "Import successful"
    nodes_added: int = 0
    edges_added: int = 0
    nodes_imported: Optional[int] = None
    edges_imported: Optional[int] = None


class StandardMessageResponse(BaseModel):
    status: str
    message: str


class AnnotationCreate(BaseModel):
    node_id: str
    content: str
    tags: List[str] = Field(default_factory=list)
    visibility: str = "public"


class AnnotationResponse(BaseModel):
    annotation_id: str
    node_id: str
    content: str
    tags: List[str] = Field(default_factory=list)
    visibility: str = "public"
    created_at: str = ""


class VocabularyScheme(BaseModel):
    uri: str
    label: str
    description: Optional[str] = None


class ConceptSummary(BaseModel):
    uri: str
    pref_label: str
    alt_labels: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    notation: Optional[str] = None
    scheme_uri: Optional[str] = None
    parent_uri: Optional[str] = None


class ConceptNode(BaseModel):
    uri: str
    pref_label: str
    alt_labels: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    notation: Optional[str] = None
    scheme_uri: Optional[str] = None
    parent_uri: Optional[str] = None
    children: Optional[List["ConceptNode"]] = None


class VocabularyImportResponse(BaseModel):
    status: str = "success"
    filename: Optional[str] = None
    nodes_added: int = 0
    edges_added: int = 0
    format: str


class MergeRequest(BaseModel):
    primary_id: str
    duplicate_ids: List[str]


class MergeResponse(BaseModel):
    merged_into: str
    removed_ids: List[str]
    edges_updated: int


class ProvenanceNode(BaseModel):
    id: str
    label: str
    prov_type: str
    parent_id: Optional[str] = None
    source_document: Optional[str] = None
    source_location: Optional[str] = None
    source_quote: Optional[str] = None
    confidence: Optional[float] = None
    checksum: Optional[str] = None


class ProvenanceEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    direction: str


class ProvenanceResponse(BaseModel):
    nodes: List[ProvenanceNode]
    edges: List[ProvenanceEdge]
    source: Optional[str] = None


# ---------------------------------------------------------------------------
# FR-6 — Distance Matrix API
# ---------------------------------------------------------------------------

class DistanceMatrixRequest(BaseModel):
    node_ids: List[str]
    metric: Literal["hops", "weighted", "semantic"] = "hops"


class DistanceMatrixResponse(BaseModel):
    nodes: List[str]
    metric: str
    matrix: List[List[Optional[float]]]
    unreachable_pairs: List[Tuple[str, str]] = Field(default_factory=list)
    computation_time_ms: float


# ---------------------------------------------------------------------------
# FR-3 backend — Semantic Neighborhood
# ---------------------------------------------------------------------------

class SemanticNeighborItem(BaseModel):
    id: str
    type: str
    content: str = ""
    similarity: float
    hop_distance: Optional[int] = None


class SemanticNeighborhoodResponse(BaseModel):
    anchor_node: str
    neighbors: List[SemanticNeighborItem]
    total: int


# ---------------------------------------------------------------------------
# FR-8 — Causal Distance Report
# ---------------------------------------------------------------------------

class CausalDistanceReport(BaseModel):
    source_id: str
    target_id: str
    causal_path: List[str]
    causal_hop_count: int
    intermediate_decisions: List[str]
    confidence_decay: float
    weakest_link: Optional[Dict[str, Any]] = None
    interpretation: str


# ---------------------------------------------------------------------------
# FR-9 — Temporal Distance Alerts
# ---------------------------------------------------------------------------

class DistanceSnapshot(BaseModel):
    timestamp: datetime
    hop_count: Optional[int] = None
    distance_band: str


class DistanceEvent(BaseModel):
    timestamp: datetime
    event_type: Literal["convergence", "divergence", "disconnected", "reconnected"]
    hop_count_before: Optional[int] = None
    hop_count_after: Optional[int] = None
    description: str


class DistanceHistoryResponse(BaseModel):
    source_id: str
    target_id: str
    metric: str
    history: List[DistanceSnapshot]
    events: List[DistanceEvent]


# ---------------------------------------------------------------------------
# FR-10 — Distance-Enriched Export
# ---------------------------------------------------------------------------

class DistanceExportRequest(BaseModel):
    format: Literal["csv", "jsonl"] = "csv"
    node_subset: Optional[List[str]] = None
    include: List[str] = Field(
        default_factory=lambda: ["source_id", "target_id", "hop_count", "distance_band"],
    )
