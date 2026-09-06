"""
Ontology Hub routes: registry, URL/file loading, preview, creation, entity search, and SKOS.
"""

import os
import asyncio
import ipaddress
import logging
import socket
import uuid
from datetime import datetime, UTC
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from typing_extensions import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..session import GraphSession
from ..dependencies import get_session
from ..utils.rdf_parser import _safe_parse_rdf
try:
    from rdflib.namespace import DCT, DC
except ImportError:
    # Fallback if DCT/DC not available
    DCT = None
    DC = None

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/ontology", tags=["ontology"])

_MAX_FETCH_BYTES = 20 * 1024 * 1024  # 20 MB
_MAX_ANALYSIS_NODES = 5_000   # cap for health/suggest/shacl node scans to avoid OOM
_MAX_ENTITIES_PER_SIDE = 500  # per-ontology cap for the O(n²) pairwise suggestion loop
_GRAPH_TOO_LARGE_DETAIL = (
    "Ontology editor graph exceeds the maximum size "
    f"({_MAX_ANALYSIS_NODES} nodes or edges)."
)


class GraphTruncationError(Exception):
    """Raised when a graph exceeds _MAX_ANALYSIS_NODES so analysis would be truncated."""
    pass


_CLASS_TYPES = frozenset({
    "owl:Class", "rdfs:Class",
    "http://www.w3.org/2002/07/owl#Class",
    "http://www.w3.org/2000/01/rdf-schema#Class",
})
_PROPERTY_TYPES = frozenset({
    "owl:ObjectProperty", "owl:DatatypeProperty", "owl:AnnotationProperty",
    "rdfs:Property",
    "http://www.w3.org/2002/07/owl#ObjectProperty",
    "http://www.w3.org/2002/07/owl#DatatypeProperty",
    "http://www.w3.org/2002/07/owl#AnnotationProperty",
})
_INDIVIDUAL_TYPES = frozenset({
    "owl:NamedIndividual",
    "http://www.w3.org/2002/07/owl#NamedIndividual",
})
_CONCEPT_TYPES = frozenset({
    "skos:Concept",
    "http://www.w3.org/2004/02/skos/core#Concept",
})
_SCHEME_TYPES = frozenset({
    "skos:ConceptScheme",
    "http://www.w3.org/2004/02/skos/core#ConceptScheme",
})
_ONTOLOGY_TYPES = frozenset({
    "owl:Ontology",
    "http://www.w3.org/2002/07/owl#Ontology",
}) | _SCHEME_TYPES

_SEARCHABLE_TYPES = _CLASS_TYPES | _PROPERTY_TYPES | _INDIVIDUAL_TYPES | _CONCEPT_TYPES | _SCHEME_TYPES
_SCHEMA_NODE_TYPES = _CLASS_TYPES | _PROPERTY_TYPES | _CONCEPT_TYPES | _ONTOLOGY_TYPES
_STRUCTURE_EDGE_TYPES = frozenset({
    "rdf:type",
    "rdfs:subClassOf",
    "rdfs:domain",
    "rdfs:range",
    "owl:disjointWith",
    "owl:equivalentClass",
    "owl:equivalentProperty",
    "owl:inverseOf",
    "skos:broader",
    "skos:narrower",
    "skos:related",
})

_URI_PREFIX_MAP = {
    "http://www.w3.org/2002/07/owl#": "owl:",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://www.w3.org/2004/02/skos/core#": "skos:",
    "http://purl.org/dc/terms/": "dcterms:",
    "http://purl.org/dc/elements/1.1/": "dc:",
    "http://schema.org/": "schema:",
    "http://www.w3.org/ns/shacl#": "sh:",
}

_FORMAT_ALIASES: Dict[str, str] = {
    "ttl": "turtle",
    "rdf": "xml",
    "owl": "xml",
    "jsonld": "json-ld",
    "json": "json-ld",
}

_ALIGNMENT_RELATIONS: Dict[str, str] = {
    "owl:equivalentClass": "http://www.w3.org/2002/07/owl#equivalentClass",
    "owl:equivalentProperty": "http://www.w3.org/2002/07/owl#equivalentProperty",
    "skos:exactMatch": "http://www.w3.org/2004/02/skos/core#exactMatch",
    "skos:closeMatch": "http://www.w3.org/2004/02/skos/core#closeMatch",
    "skos:broadMatch": "http://www.w3.org/2004/02/skos/core#broadMatch",
    "skos:narrowMatch": "http://www.w3.org/2004/02/skos/core#narrowMatch",
    "skos:relatedMatch": "http://www.w3.org/2004/02/skos/core#relatedMatch",
}

_INGEST_FORMAT_SUFFIXES: Dict[str, str] = {
    "turtle": ".ttl",
    "xml": ".rdf",
    "json-ld": ".jsonld",
    "nt": ".nt",
    "n3": ".n3",
    "trig": ".trig",
    "nquads": ".nq",
}


# ---------------------------------------------------------------------------
# SHACL Validation Resource Guardrails
# ---------------------------------------------------------------------------
_MAX_SHACL_TURTLE_BYTES: int = int(
    os.environ.get("SEMANTICA_MAX_SHACL_TURTLE_BYTES", "262144")
)  # 256 KB
_MAX_SHACL_TRIPLES: int = int(
    os.environ.get("SEMANTICA_MAX_SHACL_TRIPLES", "1000")
)  # 1,000 triples
_MAX_SHACL_TIMEOUT_SECONDS: float = float(
    os.environ.get("SEMANTICA_MAX_SHACL_TIMEOUT", "15.0")
)
_MAX_SHACL_CONCURRENCY: int = int(
    os.environ.get("SEMANTICA_MAX_SHACL_CONCURRENCY", "4")
)
_shacl_validation_semaphore: Optional[
    Tuple[asyncio.AbstractEventLoop, asyncio.Semaphore]
] = None


def _get_shacl_semaphore() -> asyncio.Semaphore:
    global _shacl_validation_semaphore
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if (
        _shacl_validation_semaphore is None
        or _shacl_validation_semaphore[0] != current_loop
    ):
        _shacl_validation_semaphore = (
            current_loop,
            asyncio.Semaphore(_MAX_SHACL_CONCURRENCY),
        )
    return _shacl_validation_semaphore[1]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class OntologyEntry(BaseModel):
    uri: str
    name: str
    description: Optional[str] = None
    format: str = "unknown"
    status: Literal["published", "draft", "external"] = "external"
    source_url: Optional[str] = None
    version: Optional[str] = None
    class_count: int = 0
    concept_count: int = 0
    property_count: int = 0
    loaded_at: str = ""
    enabled: bool = True
    tags: List[str] = Field(default_factory=list)


class OntologyPreview(BaseModel):
    uri: str
    name: str
    description: Optional[str] = None
    namespace: Optional[str] = None
    version: Optional[str] = None
    license: Optional[str] = None
    format: str
    estimated_triples: int = 0
    source_url: Optional[str] = None


class LoadOntologyRequest(BaseModel):
    url: Optional[str] = None
    content: Optional[str] = None
    format: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class PreviewOntologyRequest(BaseModel):
    url: Optional[str] = None
    content: Optional[str] = None
    format: Optional[str] = None


class CreateOntologyRequest(BaseModel):
    mode: Literal["scratch", "data", "text"] = "scratch"
    namespace: str
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    sample_data: Optional[str] = None
    schema_text: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class OntologySearchResult(BaseModel):
    uri: str
    label: str
    type: str
    entity_type: str
    definition: Optional[str] = None
    source_ontology: Optional[str] = None
    namespace_prefix: Optional[str] = None


class EntityDetailResponse(BaseModel):
    uri: str
    label: str
    type: str
    entity_type: str
    definition: Optional[str] = None
    source_ontology: Optional[str] = None
    superclasses: List[str] = Field(default_factory=list)
    subclasses: List[str] = Field(default_factory=list)
    domain: List[str] = Field(default_factory=list)
    range: List[str] = Field(default_factory=list)
    instance_count: int = 0
    properties: Dict[str, Any] = Field(default_factory=dict)


class OntologyGraphResponse(BaseModel):
    uri: str
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class SKOSScheme(BaseModel):
    uri: str
    title: str
    description: Optional[str] = None
    concept_count: int = 0


class SKOSConceptDetail(BaseModel):
    uri: str
    pref_label: str
    alt_labels: List[str] = Field(default_factory=list)
    hidden_labels: List[str] = Field(default_factory=list)
    definition: Optional[str] = None
    scope_note: Optional[str] = None
    editorial_note: Optional[str] = None
    broader: List[str] = Field(default_factory=list)
    narrower: List[str] = Field(default_factory=list)
    related: List[str] = Field(default_factory=list)
    exact_match: List[str] = Field(default_factory=list)
    close_match: List[str] = Field(default_factory=list)
    broad_match: List[str] = Field(default_factory=list)
    narrow_match: List[str] = Field(default_factory=list)
    scheme_uri: Optional[str] = None


class SKOSConceptSearchRequest(BaseModel):
    query: str
    scheme_uri: Optional[str] = None


class LoadOntologyResponse(BaseModel):
    status: str = "success"
    uri: str
    name: str
    nodes_added: int = 0
    edges_added: int = 0
    format: str = "unknown"


class ToggleResponse(BaseModel):
    uri: str
    enabled: bool


class RefreshResponse(BaseModel):
    status: str = "success"
    uri: str
    nodes_added: int = 0
    edges_added: int = 0


AlignmentRelation = Literal[
    "owl:equivalentClass",
    "owl:equivalentProperty",
    "skos:exactMatch",
    "skos:closeMatch",
    "skos:broadMatch",
    "skos:narrowMatch",
    "skos:relatedMatch",
]


class OntologyAlignment(BaseModel):
    id: str
    source_uri: str
    source_label: str = ""
    target_uri: str
    target_label: str = ""
    relation: AlignmentRelation
    predicate_uri: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Optional[str] = None
    source: Optional[str] = None
    reviewer: Optional[str] = None
    created_at: str
    updated_at: str


class OntologyAlignmentRequest(BaseModel):
    source_uri: str
    source_label: Optional[str] = None  # override for external/unloaded URIs
    target_uri: str
    target_label: Optional[str] = None  # override for external/unloaded URIs
    relation: AlignmentRelation
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Optional[str] = None
    source: Optional[str] = None
    reviewer: Optional[str] = None


class AlignmentSuggestionRequest(BaseModel):
    source_ontology_uri: Optional[str] = None
    target_ontology_uri: Optional[str] = None
    threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    limit: int = Field(default=25, ge=1, le=100)


class AlignmentSuggestion(BaseModel):
    source_uri: str
    source_label: str
    target_uri: str
    target_label: str
    relation: AlignmentRelation
    score: float
    label_similarity: float
    embedding_similarity: Optional[float] = None
    reason: str


class HealthDimension(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0.0, le=100.0)
    status: Literal["ok", "warning", "critical", "unavailable"] = "ok"
    detail: str


class HealthIssue(BaseModel):
    id: str
    severity: Literal["info", "warning", "critical"] = "warning"
    category: str
    entity_uri: Optional[str] = None
    entity_label: Optional[str] = None
    message: str
    action: Optional[str] = None


class OntologyHealthResponse(BaseModel):
    uri: str
    name: str
    total_score: float = Field(ge=0.0, le=100.0)
    dimensions: List[HealthDimension]
    issues: List[HealthIssue] = Field(default_factory=list)
    generated_at: str


class ShaclGenerateRequest(BaseModel):
    uri: str
    quality_tier: Literal["standard", "strict"] = "strict"


class ShaclValidateRequest(BaseModel):
    uri: Optional[str] = None
    shacl_turtle: str


class ShaclViolation(BaseModel):
    node: Optional[str] = None
    path: Optional[str] = None
    severity: str = "Violation"
    message: str
    focus_node: Optional[str] = None
    source_shape: Optional[str] = None


class ShaclShapeSummary(BaseModel):
    id: str
    target_class: Optional[str] = None
    constraint_count: int = 0
    constraints: List[str] = Field(default_factory=list)
    violation_count: int = 0


class ShaclGenerateResponse(BaseModel):
    uri: str
    shacl_turtle: str
    shape_count: int
    generated_at: str


class ShaclShapesResponse(BaseModel):
    uri: str
    shapes: List[ShaclShapeSummary]
    shacl_turtle: str
    generated_at: str


class ShaclValidationResponse(BaseModel):
    uri: Optional[str] = None
    conforms: bool
    status: Literal["success", "unavailable", "error"] = "success"
    message: str
    violations: List[ShaclViolation] = Field(default_factory=list)
    report_text: Optional[str] = None


# ---------------------------------------------------------------------------
# Draft, Proposal, and Version Schemas
# ---------------------------------------------------------------------------

class DraftDiff(BaseModel):
    added_classes: List[str] = Field(default_factory=list)
    removed_classes: List[str] = Field(default_factory=list)
    modified_classes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    added_properties: List[str] = Field(default_factory=list)
    removed_properties: List[str] = Field(default_factory=list)
    modified_properties: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    added_restrictions: List[Dict[str, Any]] = Field(default_factory=list)
    removed_restrictions: List[Dict[str, Any]] = Field(default_factory=list)
    added_axioms: List[Dict[str, Any]] = Field(default_factory=list)
    removed_axioms: List[Dict[str, Any]] = Field(default_factory=list)
    annotation_changes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class DraftRequest(BaseModel):
    ontology_uri: str
    diff: DraftDiff
    author: str
    summary: Optional[str] = None
    timestamp: Optional[str] = None


class DraftResponse(BaseModel):
    draft_id: str
    ontology_uri: str
    diff: DraftDiff
    author: str
    summary: Optional[str] = None
    created_at: str
    updated_at: str


class ProposalRequest(BaseModel):
    draft_id: str
    ontology_uri: str
    summary: str
    reviewer: Optional[str] = None


class ProposalResponse(BaseModel):
    proposal_id: str
    draft_id: str
    ontology_uri: str
    summary: str
    author: str
    reviewer: Optional[str] = None
    state: Literal["draft", "proposed", "approved", "published", "rejected"]
    impact_analysis: Dict[str, Any] = Field(default_factory=dict)
    shacl_validation: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    comments: List[Dict[str, Any]] = Field(default_factory=list)


class CommentRequest(BaseModel):
    element_uri: str
    text: str
    author: str


class VersionEntry(BaseModel):
    version_id: str
    ontology_uri: str
    state: Literal["draft", "published"]
    author: str
    date: str
    diff_summary: Dict[str, Any] = Field(default_factory=dict)


class VersionCompareRequest(BaseModel):
    version1: str
    version2: str


class VersionCompareResponse(BaseModel):
    version1: str
    version2: str
    metadata_changes: Dict[str, Any] = Field(default_factory=dict)
    class_changes: Dict[str, Any] = Field(default_factory=dict)
    property_changes: Dict[str, Any] = Field(default_factory=dict)
    restriction_changes: Dict[str, Any] = Field(default_factory=dict)
    axiom_changes: Dict[str, Any] = Field(default_factory=dict)


class AlignmentRequest(BaseModel):
    source_uri: str
    target_uri: str
    predicate: str


class AlignmentResponse(BaseModel):
    source: str
    predicate: str
    target: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_registry(request: Request) -> Dict[str, OntologyEntry]:
    if not hasattr(request.app.state, "ontology_registry"):
        request.app.state.ontology_registry = {}
    return request.app.state.ontology_registry


def _get_alignment_store(request: Request) -> Dict[str, OntologyAlignment]:
    if not hasattr(request.app.state, "ontology_alignments"):
        request.app.state.ontology_alignments = {}
    return request.app.state.ontology_alignments


def _get_drafts(request: Request) -> Dict[str, DraftResponse]:
    if not hasattr(request.app.state, "ontology_drafts"):
        request.app.state.ontology_drafts = {}
    return request.app.state.ontology_drafts


def _get_proposals(request: Request) -> Dict[str, ProposalResponse]:
    if not hasattr(request.app.state, "ontology_proposals"):
        request.app.state.ontology_proposals = {}
    return request.app.state.ontology_proposals


def _get_versions(request: Request) -> Dict[str, List[VersionEntry]]:
    if not hasattr(request.app.state, "ontology_versions"):
        request.app.state.ontology_versions = {}
    return request.app.state.ontology_versions


def _alignment_key(source: str, predicate: str, target: str) -> str:
    return f"{source}::{predicate}::{target}"


def _coerce_alignment(raw: Any) -> Optional[AlignmentResponse]:
    if isinstance(raw, AlignmentResponse):
        return raw
    if isinstance(raw, dict):
        source = raw.get("source") or raw.get("source_uri")
        target = raw.get("target") or raw.get("target_uri")
        predicate = raw.get("predicate") or raw.get("relation")
        if source and target and predicate:
            return AlignmentResponse(source=source, predicate=predicate, target=target)
    return None


def _version_field(version: Any, field: str, default: Any = None) -> Any:
    if isinstance(version, VersionEntry):
        return getattr(version, field)
    if isinstance(version, dict):
        return version.get(field, default)
    return default


def _uri_to_prefix(uri: str) -> str:
    for base, prefix in _URI_PREFIX_MAP.items():
        if uri.startswith(base):
            return prefix + uri[len(base):]
    return uri


def _classify_node_type(node_type: str) -> str:
    if node_type in _CLASS_TYPES:
        return "class"
    if node_type in _PROPERTY_TYPES:
        return "property"
    if node_type in _INDIVIDUAL_TYPES:
        return "individual"
    if node_type in _CONCEPT_TYPES:
        return "concept"
    if node_type in _SCHEME_TYPES:
        return "scheme"
    if node_type in _ONTOLOGY_TYPES:
        return "ontology"
    return "unknown"


def _node_label(node: Dict[str, Any]) -> str:
    props = node.get("properties", {})
    return (
        props.get("pref_label")
        or props.get("rdfs:label")
        or props.get("skos:prefLabel")
        or props.get("label")
        or props.get("content")
        or node.get("content", "")
        or node.get("id", "")
    )


def _as_uri_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        result = []
        for item in value:
            if item is None or item == "":
                continue
            if isinstance(item, dict):
                uri = item.get("uri") or item.get("id") or item.get("@id")
                if uri:
                    result.append(str(uri))
            else:
                result.append(str(item))
        return result
    if isinstance(value, dict):
        uri = value.get("uri") or value.get("id") or value.get("@id")
        return [str(uri)] if uri else []
    return [str(value)]


def _convert_ontology_to_graph(ontology_dict: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Convert OntologyIngestor ontology dict to graph nodes and edges."""
    nodes = []
    edges = []
    
    # Add ontology node
    ontology_uri = ontology_dict.get("uri", f"temp:{uuid.uuid4().hex[:12]}")
    nodes.append({
        "id": ontology_uri,
        "type": "owl:Ontology",
        "content": ontology_dict.get("name", "Ontology"),
        "properties": {
            "rdfs:label": ontology_dict.get("name", "Ontology"),
            "rdfs:comment": ontology_dict.get("description", ""),
            "uri": ontology_uri,
        },
    })
    
    # Add class nodes
    for cls in ontology_dict.get("classes", []):
        cls_uri = cls.get("uri", f"temp:class:{uuid.uuid4().hex[:12]}")
        node = {
            "id": cls_uri,
            "type": "owl:Class",
            "content": cls.get("name", cls.get("label", "")),
            "properties": {
                "rdfs:label": cls.get("label", cls.get("name", "")),
                "rdfs:comment": cls.get("description", ""),
                "uri": cls_uri,
                "scheme_uri": ontology_uri,
            },
        }
        nodes.append(node)
        
        # Add subclass edges
        for parent in cls.get("parents", []):
            edges.append({
                "source": cls_uri,
                "target": parent,
                "type": "rdfs:subClassOf",
                "weight": 1.0,
            })
    
    # Add property nodes and edges
    for prop in ontology_dict.get("properties", []):
        prop_uri = prop.get("uri", f"temp:prop:{uuid.uuid4().hex[:12]}")
        property_type = {
            "object": "owl:ObjectProperty",
            "data": "owl:DatatypeProperty",
            "datatype": "owl:DatatypeProperty",
            "annotation": "owl:AnnotationProperty",
        }.get(str(prop.get("type", "object")).lower(), "owl:ObjectProperty")
        node = {
            "id": prop_uri,
            "type": property_type,
            "content": prop.get("name", prop.get("label", "")),
            "properties": {
                "rdfs:label": prop.get("label", prop.get("name", "")),
                "rdfs:comment": prop.get("description", ""),
                "uri": prop_uri,
                "scheme_uri": ontology_uri,
            },
        }
        nodes.append(node)
        
        # Add domain and range edges
        for domain_uri in _as_uri_list(prop.get("domain")):
            edges.append({
                "source": prop_uri,
                "target": domain_uri,
                "type": "rdfs:domain",
                "weight": 1.0,
            })
        for range_uri in _as_uri_list(prop.get("range")):
            edges.append({
                "source": prop_uri,
                "target": range_uri,
                "type": "rdfs:range",
                "weight": 1.0,
            })
    
    return nodes, edges


def _extract_namespace(uri: str) -> Optional[str]:
    if "#" in uri:
        return uri.rsplit("#", 1)[0] + "#"
    if "/" in uri:
        return uri.rsplit("/", 1)[0] + "/"
    return None


def _ontology_namespace(uri: str) -> str:
    if "#" in uri:
        return uri.rsplit("#", 1)[0] + "#"
    if uri.endswith("/"):
        return uri
    return uri.rstrip("#/") + "#"


def _alignment_id(source_uri: str, relation: str, target_uri: str) -> str:
    key = f"{source_uri}|{relation}|{target_uri}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, key))


def _label_from_uri(uri: str) -> str:
    """Derive a readable label from a URI when no graph node is present (e.g. external vocabularies)."""
    fragment = uri.rsplit("#", 1)[-1] if "#" in uri else uri.rsplit("/", 1)[-1]
    return fragment or uri


def _node_source_ontology(node: Dict[str, Any]) -> Optional[str]:
    props = node.get("properties", {})
    return (
        props.get("scheme_uri")
        or props.get("source_ontology")
        or props.get("ontology_uri")
        or props.get("ontology")
    )


def _node_belongs_to_ontology(
    node: Dict[str, Any],
    ontology_uri: str,
    known_ontology_uris: Optional[set[str]] = None,
) -> bool:
    nid = node.get("id", "")
    if nid == ontology_uri:
        return True
    owner = _node_source_ontology(node)
    if owner:
        return owner == ontology_uri
    if known_ontology_uris:
        namespace_owners = [
            candidate
            for candidate in known_ontology_uris
            if nid == candidate
            or nid.startswith(
                (candidate.rstrip("#/") + "#", candidate.rstrip("#/") + "/")
            )
        ]
        if namespace_owners and max(namespace_owners, key=len) != ontology_uri:
            return False
    stem = ontology_uri.rstrip("#/")
    if not nid.startswith((stem + "#", stem + "/")):
        return False
    # Prefix ownership only extends to names minted directly in the
    # ontology's namespace (<stem>#Term or <stem>/Term). Any further
    # delimiter marks a nested vocabulary (<stem>/child#Term,
    # <stem>/child/Term), which must not be absorbed into the parent
    # until it is registered or carries an explicit owner.
    local_name = nid[len(stem) + 1 :]
    return "#" not in local_name and "/" not in local_name


def _is_ontology_entity(node: Dict[str, Any]) -> bool:
    return _classify_node_type(node.get("type", "")) in {"class", "property", "concept", "scheme"}


def _entity_description(node: Dict[str, Any]) -> Optional[str]:
    props = node.get("properties", {})
    return (
        props.get("rdfs:comment")
        or props.get("skos:definition")
        or props.get("definition")
        or props.get("description")
    )


def _entity_definition(node: Dict[str, Any]) -> Optional[str]:
    props = node.get("properties", {})
    return props.get("skos:definition") or props.get("definition")


def _label_similarity(left: str, right: str) -> float:
    left_norm = " ".join(left.lower().replace("_", " ").replace("-", " ").split())
    right_norm = " ".join(right.lower().replace("_", " ").replace("-", " ").split())
    if not left_norm or not right_norm:
        return 0.0
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    token_score = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    return round(max(sequence, token_score), 4)


def _token_set(label: str) -> frozenset:
    return frozenset(label.lower().replace("_", " ").replace("-", " ").split())


def _tfidf_embedding_vectors(labels: List[str]) -> Optional[Dict[str, List[float]]]:
    """Build character-ngram TF-IDF vectors from entity labels (sklearn-based, no gensim needed)."""
    if len(labels) < 2:
        return None
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        normed = [" ".join(l.lower().replace("_", " ").replace("-", " ").split()) for l in labels]
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        matrix = vec.fit_transform(normed)
        return {label: matrix[i].toarray().flatten().tolist() for i, label in enumerate(labels)}
    except Exception:
        return None


def _cosine_sim(v1: List[float], v2: List[float]) -> float:
    try:
        from ...kg import SimilarityCalculator
        return SimilarityCalculator().cosine_similarity(v1, v2)
    except Exception:
        import math
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        return dot / (n1 * n2) if n1 and n2 else 0.0


def _candidate_relation(source: Dict[str, Any], target: Dict[str, Any]) -> AlignmentRelation:
    source_type = _classify_node_type(source.get("type", ""))
    target_type = _classify_node_type(target.get("type", ""))
    if source_type == "class" and target_type == "class":
        return "owl:equivalentClass"
    if source_type == "property" and target_type == "property":
        return "owl:equivalentProperty"
    if source_type == "concept" and target_type == "concept":
        return "skos:exactMatch"
    return "skos:closeMatch"


def _ontology_entities(nodes: List[Dict[str, Any]], ontology_uri: Optional[str] = None) -> List[Dict[str, Any]]:
    result = []
    for node in nodes:
        if not _is_ontology_entity(node):
            continue
        if ontology_uri and not _node_belongs_to_ontology(node, ontology_uri):
            continue
        result.append(node)
    return result


def _data_graph_entities(nodes: List[Dict[str, Any]], ontology_uri: Optional[str] = None) -> List[Dict[str, Any]]:
    result = []
    for node in nodes:
        if _classify_node_type(node.get("type", "")) not in {"class", "property", "individual", "concept", "scheme"}:
            continue
        if ontology_uri and not _node_belongs_to_ontology(node, ontology_uri):
            continue
        result.append(node)
    return result


def _ontology_dict_from_nodes(uri: str, name: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    classes = []
    properties = []
    for node in nodes:
        entity_type = _classify_node_type(node.get("type", ""))
        label = _node_label(node) or node.get("id", "")
        item = {
            "name": label,
            "uri": node.get("id", ""),
            "label": label,
            "description": _entity_description(node) or "",
        }
        if entity_type == "class":
            classes.append(item)
        elif entity_type == "property":
            domain = [
                edge.get("target", "")
                for edge in edges
                if edge.get("source") == node.get("id") and edge.get("type") == "rdfs:domain"
            ]
            range_ = [
                edge.get("target", "")
                for edge in edges
                if edge.get("source") == node.get("id") and edge.get("type") == "rdfs:range"
            ]
            item.update({
                "type": "object" if "ObjectProperty" in node.get("type", "") else "datatype",
                "domain": domain,
                "range": range_,
                "required": False,
            })
            properties.append(item)

    return {
        "name": name,
        "namespace": _ontology_namespace(uri),
        "classes": classes,
        "properties": properties,
    }


def _basic_shacl_turtle(uri: str, name: str, nodes: List[Dict[str, Any]]) -> str:
    namespace = _ontology_namespace(uri)
    lines = [
        "@prefix sh: <http://www.w3.org/ns/shacl#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        f"@prefix onto: <{namespace}> .",
        "",
    ]
    class_nodes = [n for n in nodes if _classify_node_type(n.get("type", "")) == "class"]
    for index, node in enumerate(class_nodes or nodes[:1], start=1):
        label = (_node_label(node) or f"{name}Shape").replace(" ", "")
        target = node.get("id") or uri
        lines.extend([
            f"onto:{label}Shape a sh:NodeShape ;",
            f"  sh:targetClass <{target}> ;",
            "  sh:severity sh:Violation .",
            "",
        ])
    return "\n".join(lines)


def _summarize_shapes(shacl_turtle: str, violations: Optional[List[ShaclViolation]] = None) -> List[ShaclShapeSummary]:
    violations = violations or []
    normalised = shacl_turtle.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in normalised.split(".\n") if "sh:NodeShape" in block]
    summaries: List[ShaclShapeSummary] = []
    for index, block in enumerate(blocks, start=1):
        first = block.splitlines()[0].strip()
        shape_id = first.split()[0] if first else f"shape-{index}"
        target_class = None
        constraints: List[str] = []
        for token in ("sh:targetClass", "sh:path", "sh:minCount", "sh:maxCount", "sh:datatype", "sh:class"):
            if token in block:
                constraints.append(token.replace("sh:", ""))
        if "sh:targetClass" in block:
            after = block.split("sh:targetClass", 1)[1].strip()
            target_class = after.split()[0].strip(" ;")
        violation_count = sum(
            1
            for violation in violations
            if violation.source_shape == shape_id or (target_class and violation.node == target_class)
        )
        summaries.append(ShaclShapeSummary(
            id=shape_id,
            target_class=target_class,
            constraint_count=max(0, len(constraints) - 1),
            constraints=constraints,
            violation_count=violation_count,
        ))
    return summaries


async def _registry_entries(request: Request, session: GraphSession) -> List[OntologyEntry]:
    return await list_registry(request=request, q=None, status=None, format=None, session=session)


def _detect_format(content: str) -> str:
    stripped = content.strip()[:500]
    if stripped.startswith("{") or stripped.startswith("["):
        return "json-ld"
    if stripped.startswith("<"):
        return "xml"
    if "@prefix" in stripped or "@base" in stripped:
        return "turtle"
    # N-Triples blank-node subject: "_:word <predicate-uri> ..."
    # URI-subject N-Triples ("<uri> <uri>") are already caught by the XML
    # branch above, so only the blank-node form needs to be checked here.
    # Plain string ops avoid the polynomial regex that CodeQL flags (py/polynomial-redos).
    if stripped.startswith("_:") and " <" in stripped:
        return "nt"
    return "turtle"


def _normalize_format(fmt: Optional[str]) -> str:
    if not fmt:
        return "turtle"
    lower = fmt.strip().lower()
    return _FORMAT_ALIASES.get(lower, lower)


def _validate_fetch_url(url: str) -> List[str]:
    """Reject non-HTTP(S) schemes and private/loopback/link-local targets.

    Returns every resolved, validated IP address (deduplicated, in
    resolution order) so the caller can pin the actual connection to them
    (see _make_pinned_session) with fallback across all of them — not just
    the first — since a hostname can have multiple A/AAAA records and the
    first one isn't guaranteed reachable. Resolving the hostname again at
    connect time would open a DNS check-then-use window (a low-TTL or
    rebinding DNS answer could differ between this check and the client's
    own lookup), which is what pinning to these specific addresses avoids.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="Only http and https URLs are allowed.")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=422, detail="Invalid URL: missing hostname.")
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail=f"Cannot resolve hostname '{hostname}': {exc}") from exc
    validated_ips: List[str] = []
    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(
                status_code=422,
                detail="Fetching from private, loopback, or reserved network addresses is not allowed.",
            )
        if sockaddr[0] not in validated_ips:
            validated_ips.append(sockaddr[0])
    if not validated_ips:
        raise HTTPException(status_code=422, detail=f"Cannot resolve hostname '{hostname}' to a usable address.")
    return validated_ips


def _make_pinned_session(pinned_ips: List[str], url: str):
    """Build a requests.Session whose connection is pinned to pinned_ips
    (tried in order, falling back on connection failure), regardless of
    what url's hostname resolves to at connect time.

    _validate_fetch_url() resolves and validates the hostname once; letting
    the HTTP client resolve it again independently at connect time reopens
    the exact gap that validation exists to close — a low-TTL or rebinding
    DNS answer can differ between the two lookups. This pins the pool's
    connect target to the already-validated addresses directly (bypassing
    DNS resolution for the connection entirely), while keeping the original
    hostname as the outgoing HTTP Host header and, for HTTPS, the TLS SNI
    server_hostname / assert_hostname — otherwise the connection would
    reach the right IP but present the wrong identity, breaking name-based
    virtual hosting and (for HTTPS) certificate hostname verification.

    Falls back across every validated address (not just the first) so a
    hostname with multiple A/AAAA records doesn't fail outright just
    because the first-returned address happens to be unreachable.

    Note: urllib3's Connection.host is a property that reads/writes the
    same underlying value as `_dns_host` in this version — it is NOT the
    separate "presented identity" field it is in some older releases, so
    overriding just `_dns_host` post-construction (as an earlier version of
    this fix did) actually changes the Host header too. Pinning the pool's
    `host` directly and restoring the real hostname via an explicit Host
    header (+ SNI params for HTTPS) is the correct mechanism here.
    """
    import requests as _req
    import urllib3.util.connection as _u3_connection
    from urllib3.exceptions import NewConnectionError

    parsed = urlparse(url)
    hostname = parsed.hostname
    port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80
    host_header = hostname if port in (None, default_port) else f"{hostname}:{port}"

    class _MultiIPConnectionMixin:
        """Overrides _new_conn to fall back across every pinned IP in
        order, instead of urllib3's default single-host connect."""

        def _new_conn(self):
            last_exc: Optional[BaseException] = None
            for ip in pinned_ips:
                try:
                    return _u3_connection.create_connection(
                        (ip, self.port),
                        self.timeout,
                        source_address=self.source_address,
                        socket_options=self.socket_options,
                    )
                except OSError as exc:
                    last_exc = exc
                    continue
            raise NewConnectionError(
                self, f"Failed to establish a connection to any of {pinned_ips}: {last_exc}"
            )

    class _PinnedIPHTTPAdapter(_req.adapters.HTTPAdapter):
        def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
            # A proxy would perform its own DNS resolution of the target
            # host on this process's behalf — a resolution outside this
            # process's visibility or control, so there is no client-side
            # pin that closes that race. Proxies are disabled outright for
            # this SSRF-sensitive fetcher (session.trust_env=False below),
            # so this should be unreachable via environment proxies; fail
            # closed rather than silently skip pinning if a proxy is
            # somehow still configured (e.g. passed explicitly in the
            # future). _validate_fetch_url's destination classification is
            # a separate, always-enforced check — this only guards the
            # secondary DNS-pinning hardening.
            if _req.utils.select_proxy(request.url, proxies):
                raise HTTPException(
                    status_code=502,
                    detail="Proxied requests are not supported for ontology URL fetching.",
                )
            host_params, pool_kwargs = self.build_connection_pool_key_attributes(request, verify, cert)
            if host_params.get("scheme") == "https":
                pool_kwargs.setdefault("assert_hostname", hostname)
                pool_kwargs.setdefault("server_hostname", hostname)
            host_params["host"] = pinned_ips[0]
            pool = self.poolmanager.connection_from_host(**host_params, pool_kwargs=pool_kwargs)
            base_connection_cls = pool.ConnectionCls
            if not issubclass(base_connection_cls, _MultiIPConnectionMixin):
                pool.ConnectionCls = type(
                    "_PinnedConnection", (_MultiIPConnectionMixin, base_connection_cls), {}
                )
            return pool

    session = _req.Session()
    # Never honor HTTP_PROXY/HTTPS_PROXY/NO_PROXY env vars for this
    # SSRF-sensitive fetcher: a configured proxy would perform its own DNS
    # resolution of the target host outside this process's control,
    # silently reopening the DNS check-then-use race pinning exists to
    # close. See _PinnedIPHTTPAdapter.get_connection_with_tls_context for
    # the fail-closed backstop if a proxy is somehow still configured.
    session.trust_env = False
    session.headers["Host"] = host_header
    adapter = _PinnedIPHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _fetch_url_sync(url: str) -> bytes:
    pinned_ips = _validate_fetch_url(url)
    _MAX_REDIRECTS = 5
    current_url = url
    try:
        for _ in range(_MAX_REDIRECTS + 1):
            session = _make_pinned_session(pinned_ips, current_url)
            try:
                resp = session.get(
                    current_url,
                    headers={"Accept": "text/turtle, application/rdf+xml, application/ld+json, */*;q=0.1"},
                    timeout=30,
                    stream=True,
                    allow_redirects=False,  # SECURITY: follow redirects manually
                )
                if resp.is_redirect or resp.is_permanent_redirect:
                    redirect_url = resp.headers.get("Location")
                    resp.close()  # Release the streamed connection before following the redirect
                    if not redirect_url:
                        raise HTTPException(status_code=502, detail="Redirect without Location header.")
                    # Resolve relative redirects (e.g. /ontology.ttl) against the current URL
                    redirect_url = urljoin(current_url, redirect_url)
                    # Re-validate the redirect target to prevent SSRF via
                    # open-redirect to internal/cloud-metadata endpoints, and
                    # get fresh pins for the new host.
                    pinned_ips = _validate_fetch_url(redirect_url)
                    current_url = redirect_url
                    continue
                try:
                    resp.raise_for_status()
                    chunks: List[bytes] = []
                    total = 0
                    for chunk in resp.iter_content(65536):
                        total += len(chunk)
                        if total > _MAX_FETCH_BYTES:
                            raise HTTPException(status_code=413, detail="Remote resource exceeds 20 MB limit.")
                        chunks.append(chunk)
                    return b"".join(chunks)
                finally:
                    resp.close()  # Release the streamed connection once fully read (or on error)
            finally:
                session.close()
        raise HTTPException(status_code=502, detail=f"Too many redirects (max {_MAX_REDIRECTS}).")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch {url}: {exc}") from exc


def _parse_rdf_sync(content: bytes, fmt: str) -> tuple:
    """Return (nodes, edges, metadata). Raises HTTPException on failure."""
    try:
        import rdflib
    except ImportError:
        raise HTTPException(status_code=501, detail="rdflib is not installed.")

    fmt_map = {
        "turtle": "turtle", "xml": "xml", "nt": "nt",
        "json-ld": "json-ld", "n3": "n3",
    }
    parse_fmt = fmt_map.get(fmt, "turtle")

    g = rdflib.Graph()
    try:
        _safe_parse_rdf(g, content, parse_fmt)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"RDF parse error: {exc}") from exc

    OWL = rdflib.Namespace("http://www.w3.org/2002/07/owl#")
    RDF = rdflib.RDF
    RDFS = rdflib.RDFS
    SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")
    DCT = rdflib.Namespace("http://purl.org/dc/terms/")
    DC = rdflib.Namespace("http://purl.org/dc/elements/1.1/")

    metadata: Dict[str, Any] = {}

    for subj in g.subjects(RDF.type, OWL.Ontology):
        metadata["uri"] = str(subj)
        for pred, obj in g.predicate_objects(subj):
            p = str(pred)
            if p in {str(RDFS.label), str(DCT.title), str(DC.title)}:
                metadata.setdefault("name", str(obj))
            elif p in {str(RDFS.comment), str(DCT.description), str(DC.description)}:
                metadata.setdefault("description", str(obj))
            elif p == str(OWL.versionInfo):
                metadata.setdefault("version", str(obj))
            elif p in {str(DCT.license), str(DC.rights)}:
                metadata.setdefault("license", str(obj))
        break

    if "uri" not in metadata:
        for subj in g.subjects(RDF.type, SKOS.ConceptScheme):
            metadata["uri"] = str(subj)
            for pred, obj in g.predicate_objects(subj):
                p = str(pred)
                if p in {str(SKOS.prefLabel), str(DCT.title), str(DC.title)}:
                    metadata.setdefault("name", str(obj))
                elif p in {str(SKOS.definition), str(DCT.description)}:
                    metadata.setdefault("description", str(obj))
            break

    synthetic_uri = "uri" not in metadata
    if synthetic_uri:
        metadata["uri"] = f"urn:semantica:onto:{uuid.uuid4().hex[:8]}"
    metadata.setdefault("name", metadata["uri"].rsplit("/", 1)[-1].rsplit("#", 1)[-1] or "Unnamed")
    metadata["triple_count"] = len(g)

    # Collect literal properties per subject
    literal_props: Dict[str, Dict[str, str]] = {}
    for subj, pred, obj in g:
        if isinstance(subj, rdflib.BNode) or not isinstance(obj, rdflib.Literal):
            continue
        sid = str(subj)
        pk = _uri_to_prefix(str(pred))
        literal_props.setdefault(sid, {})[pk] = str(obj)

    # Build nodes from rdf:type statements
    seen_ids: set = set()
    nodes: List[Dict[str, Any]] = []
    for subj, _, type_obj in g.triples((None, RDF.type, None)):
        if isinstance(subj, rdflib.BNode):
            continue
        sid = str(subj)
        ntype = _uri_to_prefix(str(type_obj))
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        props = dict(literal_props.get(sid, {}))
        props["uri"] = sid
        label = (
            props.get("rdfs:label")
            or props.get("skos:prefLabel")
            or props.get("dcterms:title")
            or sid.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        )
        nodes.append({"id": sid, "type": ntype, "content": label, "properties": props})

    # Build edges from non-literal object statements
    edges: List[Dict[str, Any]] = []
    for subj, pred, obj in g:
        if isinstance(subj, rdflib.BNode) or isinstance(obj, (rdflib.Literal, rdflib.BNode)):
            continue
        edges.append({
            "source": str(subj),
            "target": str(obj),
            "type": _uri_to_prefix(str(pred)),
            "weight": 1.0,
        })

    if synthetic_uri:
        # No owl:Ontology / skos:ConceptScheme declaration exists, so the
        # synthetic registry URI shares no namespace with any node. Ownership
        # must be recorded explicitly, and the editor needs a matching graph
        # node, or the registered ontology resolves to an empty core and 404s.
        for node in nodes:
            node["properties"].setdefault("scheme_uri", metadata["uri"])
        nodes.append({
            "id": metadata["uri"],
            "type": "owl:Ontology",
            "content": metadata["name"],
            "properties": {"rdfs:label": metadata["name"], "uri": metadata["uri"]},
        })

    return nodes, edges, metadata


# ---------------------------------------------------------------------------
# Registry endpoints (all specific paths before wildcard)
# ---------------------------------------------------------------------------

@router.get("/registry", response_model=List[OntologyEntry])
async def list_registry(
    request: Request,
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    session: GraphSession = Depends(get_session),
):
    registry = _get_registry(request)

    # Discover ontology-type nodes from live graph not yet registered
    all_nodes, _ = await asyncio.to_thread(session.get_nodes, skip=0, limit=999_999)

    # Count entity types per ontology URI via scheme_uri property
    class_counts: Dict[str, int] = {}
    concept_counts: Dict[str, int] = {}
    prop_counts: Dict[str, int] = {}
    implicit: Dict[str, Dict[str, Any]] = {}

    for node in all_nodes:
        ntype = node.get("type", "")
        nid = node.get("id", "")
        etype = _classify_node_type(ntype)
        scheme_uri = node.get("properties", {}).get("scheme_uri") or node.get("properties", {}).get("uri")

        if etype == "ontology" or etype == "scheme":
            if nid and nid not in registry:
                implicit[nid] = node
        elif scheme_uri:
            if etype == "class":
                class_counts[scheme_uri] = class_counts.get(scheme_uri, 0) + 1
            elif etype == "concept":
                concept_counts[scheme_uri] = concept_counts.get(scheme_uri, 0) + 1
            elif etype == "property":
                prop_counts[scheme_uri] = prop_counts.get(scheme_uri, 0) + 1

    result: List[OntologyEntry] = []

    def _matches(name: str, uri: str, desc: str) -> bool:
        if not q:
            return True
        ql = q.lower()
        return any(ql in t.lower() for t in [name, uri, desc] if t)

    for entry in registry.values():
        if status and entry.status != status:
            continue
        if format and entry.format.lower() != format.lower():
            continue
        if not _matches(entry.name, entry.uri, entry.description or ""):
            continue
        updated = entry.model_copy(update={
            "class_count": class_counts.get(entry.uri, entry.class_count),
            "concept_count": concept_counts.get(entry.uri, entry.concept_count),
            "property_count": prop_counts.get(entry.uri, entry.property_count),
        })
        result.append(updated)

    for nid, node in implicit.items():
        props = node.get("properties", {})
        name = _node_label(node) or nid
        if not _matches(name, nid, props.get("description", "")):
            continue
        result.append(OntologyEntry(
            uri=nid,
            name=name,
            description=props.get("description"),
            format=props.get("format", "unknown"),
            status="external",
            version=props.get("version") or props.get("owl:versionInfo"),
            class_count=class_counts.get(nid, 0),
            concept_count=concept_counts.get(nid, 0),
            property_count=prop_counts.get(nid, 0),
            loaded_at=props.get("loaded_at", ""),
            enabled=True,
        ))

    return result


@router.post("/preview", response_model=OntologyPreview)
async def preview_ontology(body: PreviewOntologyRequest):
    if not body.url and not body.content:
        raise HTTPException(status_code=422, detail="Provide either url or content.")

    if body.url:
        raw = await asyncio.to_thread(_fetch_url_sync, body.url)
        content_str = raw.decode("utf-8", errors="replace")
    else:
        content_str = body.content or ""

    fmt = _normalize_format(body.format) if body.format else _detect_format(content_str)

    try:
        _, _, metadata = await asyncio.to_thread(
            _parse_rdf_sync, content_str.encode("utf-8"), fmt
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse ontology: {exc}") from exc

    return OntologyPreview(
        uri=metadata.get("uri", ""),
        name=metadata.get("name", ""),
        description=metadata.get("description"),
        namespace=_extract_namespace(metadata.get("uri", "")),
        version=metadata.get("version"),
        license=metadata.get("license"),
        format=fmt,
        estimated_triples=metadata.get("triple_count", 0),
        source_url=body.url,
    )


@router.post("/load", response_model=LoadOntologyResponse)
async def load_ontology(
    request: Request,
    body: LoadOntologyRequest,
    session: GraphSession = Depends(get_session),
):
    if not body.url and not body.content:
        raise HTTPException(status_code=422, detail="Provide either url or content.")

    if body.url:
        raw = await asyncio.to_thread(_fetch_url_sync, body.url)
        content_str = raw.decode("utf-8", errors="replace")
    else:
        content_str = body.content or ""

    fmt = _normalize_format(body.format) if body.format else _detect_format(content_str)
    suffix = _INGEST_FORMAT_SUFFIXES.get(fmt)
    if suffix is None:
        raise HTTPException(status_code=422, detail=f"Unsupported ontology format: {fmt}")

    try:
        # Try to use OntologyIngestor for proper parsing and conversion
        from ...ingest.ontology_ingestor import OntologyIngestor
        from tempfile import NamedTemporaryFile
        
        ingestor = OntologyIngestor()
        
        # Write content to temporary file for ingestion
        with NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as temp_file:
            temp_file.write(content_str)
            temp_path = temp_file.name
        
        try:
            # Use OntologyIngestor to parse and convert
            ontology_data = await asyncio.to_thread(
                ingestor.ingest_ontology,
                temp_path,
                format=fmt
            )
            if not ontology_data.data.get("classes") and not ontology_data.data.get("properties"):
                raise ValueError("No OWL classes or properties found by OntologyIngestor")
            
            # Convert to graph nodes/edges using ontology data
            nodes, edges = await asyncio.to_thread(
                _convert_ontology_to_graph,
                ontology_data.data
            )
            
            try:
                nodes_added, edges_added = await asyncio.to_thread(
                    session.add_nodes_and_edges, nodes, edges
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            
            # Register in registry
            registry = _get_registry(request)
            ontology_uri = ontology_data.data.get("uri", f"temp:{uuid.uuid4().hex[:12]}")
            registry[ontology_uri] = OntologyEntry(
                uri=ontology_uri,
                name=ontology_data.data.get("name", "Imported Ontology"),
                description=ontology_data.data.get("description"),
                format=fmt,
                status="external",
                version=ontology_data.data.get("version", "1.0"),
                class_count=len([n for n in nodes if n.get("type") in _CLASS_TYPES]),
                concept_count=len([n for n in nodes if n.get("type") in _CONCEPT_TYPES]),
                property_count=len([n for n in nodes if n.get("type") in _PROPERTY_TYPES]),
                loaded_at=datetime.now(UTC).isoformat(),
                enabled=True,
                tags=body.tags,
                source_url=body.url,
            )
            
            return LoadOntologyResponse(
                uri=ontology_uri,
                name=ontology_data.data.get("name", "Imported Ontology"),
                nodes_added=nodes_added,
                edges_added=edges_added,
                format=fmt,
            )
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except OSError as cleanup_exc:
                logger.debug("Failed to remove temporary ontology file: %s", cleanup_exc)
                
    except HTTPException:
        # Re-raise HTTPExceptions we deliberately raised above (e.g. the 422 from
        # SKOS cycle validation) instead of letting the broad `except Exception`
        # below mask them as an ingestor failure and silently retry via the
        # fallback parser.
        raise
    except Exception as ingest_exc:
        logger.warning(f"OntologyIngestor failed, falling back to basic parsing: {ingest_exc}")

        # Fallback to basic parsing
        nodes, edges, metadata = await asyncio.to_thread(
            _parse_rdf_sync, content_str.encode("utf-8"), fmt
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse ontology: {exc}") from exc

    # Fallback path - use basic parsing
    try:
        nodes_added, edges_added = await asyncio.to_thread(
            session.add_nodes_and_edges, nodes, edges
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    registry = _get_registry(request)
    ontology_uri = metadata.get("uri", f"temp:{uuid.uuid4().hex[:12]}")
    registry[ontology_uri] = OntologyEntry(
        uri=ontology_uri,
        name=metadata.get("name", "Imported Ontology"),
        description=metadata.get("description"),
        format=fmt,
        status="external",
        version=metadata.get("version", "1.0"),
        class_count=sum(1 for n in nodes if n.get("type") in _CLASS_TYPES),
        concept_count=sum(1 for n in nodes if n.get("type") in _CONCEPT_TYPES),
        property_count=sum(1 for n in nodes if n.get("type") in _PROPERTY_TYPES),
        loaded_at=datetime.now(UTC).isoformat(),
        enabled=True,
        tags=body.tags,
        source_url=body.url,
    )

    return LoadOntologyResponse(
        uri=ontology_uri,
        name=metadata.get("name", "Imported Ontology"),
        nodes_added=nodes_added,
        edges_added=edges_added,
        format=fmt,
    )


@router.post("/create", response_model=LoadOntologyResponse)
async def create_ontology(
    request: Request,
    body: CreateOntologyRequest,
    session: GraphSession = Depends(get_session),
):
    """Create ontology from scratch, sample data, or text using OntologyEngine."""
    ns = body.namespace.rstrip("/#")
    onto_uri = f"{ns}#ontology"
    
    # Initialize OntologyEngine with session's graph store
    engine_config = {"store": session.graph.store if hasattr(session.graph, "store") else None}
    if body.provider or body.model:
        engine_config["provider"] = body.provider
        engine_config["model"] = body.model
    
    nodes: List[Dict[str, Any]] = [{
        "id": onto_uri,
        "type": "owl:Ontology",
        "content": body.name,
        "properties": {
            "rdfs:label": body.name,
            "rdfs:comment": body.description or "",
            "namespace": body.namespace,
        },
    }]
    edges: List[Dict[str, Any]] = []

    if body.mode == "data" and body.sample_data:
        try:
            from ...ontology import OntologyEngine
            engine = OntologyEngine(**engine_config)
            result = await asyncio.to_thread(engine.from_data, body.sample_data)
            
            # Convert OntologyEngine result to graph nodes/edges
            if isinstance(result, dict):
                for cls in result.get("classes", []):
                    cls_uri = f"{ns}/{cls.get('name', uuid.uuid4().hex[:6])}"
                    nodes.append({
                        "id": cls_uri,
                        "type": "owl:Class",
                        "content": cls.get("name", ""),
                        "properties": {
                            "rdfs:label": cls.get("name", ""),
                            "rdfs:comment": cls.get("description", ""),
                        },
                    })
                
                # Add property edges
                for prop in result.get("properties", []):
                    prop_uri = f"{ns}/{prop.get('name', uuid.uuid4().hex[:6])}"
                    
                    nodes.append({
                        "id": prop_uri,
                        "type": "owl:ObjectProperty",
                        "content": prop.get("name", ""),
                        "properties": {"rdfs:label": prop.get("name", "")},
                    })
                    
                    # Only create domain/range edges if domain/range are specified
                    domain = prop.get('domain')
                    if domain and domain.strip():
                        domain_uri = f"{ns}/{domain}"
                        edges.append({
                            "source": prop_uri,
                            "target": domain_uri,
                            "type": "rdfs:domain",
                            "weight": 1.0,
                        })
                    
                    range_val = prop.get('range')
                    if range_val and range_val.strip():
                        range_uri = f"{ns}/{range_val}"
                        edges.append({
                            "source": prop_uri,
                            "target": range_uri,
                            "type": "rdfs:range",
                            "weight": 1.0,
                        })
                
                # Add subclass edges
                for cls in result.get("classes", []):
                    cls_uri = f"{ns}/{cls.get('name', '')}"
                    for parent in cls.get("superclasses", []):
                        parent_uri = f"{ns}/{parent}"
                        edges.append({
                            "source": cls_uri,
                            "target": parent_uri,
                            "type": "rdfs:subClassOf",
                            "weight": 1.0,
                        })
            
            logger.info(f"Generated ontology from sample data with {len(nodes)} nodes, {len(edges)} edges")
            
        except Exception as exc:
            logger.exception("Failed to generate ontology from sample data; aborting ontology creation.")
            raise HTTPException(status_code=500, detail=f"Ontology generation failed: {exc}") from exc

    elif body.mode == "text" and body.schema_text:
        try:
            from ...ontology import OntologyEngine
            engine = OntologyEngine(**engine_config)
            result = await asyncio.to_thread(engine.from_text, body.schema_text, provider=body.provider, model=body.model)
            
            # Convert OntologyEngine result to graph nodes/edges
            if isinstance(result, dict):
                for cls in result.get("classes", []):
                    cls_uri = f"{ns}/{cls.get('name', uuid.uuid4().hex[:6])}"
                    nodes.append({
                        "id": cls_uri,
                        "type": "owl:Class",
                        "content": cls.get("name", ""),
                        "properties": {
                            "rdfs:label": cls.get("name", ""),
                            "rdfs:comment": cls.get("description", ""),
                        },
                    })
                
                # Add property edges
                for prop in result.get("properties", []):
                    prop_uri = f"{ns}/{prop.get('name', uuid.uuid4().hex[:6])}"
                    
                    nodes.append({
                        "id": prop_uri,
                        "type": "owl:ObjectProperty",
                        "content": prop.get("name", ""),
                        "properties": {"rdfs:label": prop.get("name", "")},
                    })
                    
                    # Only create domain/range edges if domain/range are specified
                    domain = prop.get('domain')
                    if domain and domain.strip():
                        domain_uri = f"{ns}/{domain}"
                        edges.append({
                            "source": prop_uri,
                            "target": domain_uri,
                            "type": "rdfs:domain",
                            "weight": 1.0,
                        })
                    
                    range_val = prop.get('range')
                    if range_val and range_val.strip():
                        range_uri = f"{ns}/{range_val}"
                        edges.append({
                            "source": prop_uri,
                            "target": range_uri,
                            "type": "rdfs:range",
                            "weight": 1.0,
                        })
                
                # Add subclass edges
                for cls in result.get("classes", []):
                    cls_uri = f"{ns}/{cls.get('name', '')}"
                    for parent in cls.get("superclasses", []):
                        parent_uri = f"{ns}/{parent}"
                        edges.append({
                            "source": cls_uri,
                            "target": parent_uri,
                            "type": "rdfs:subClassOf",
                            "weight": 1.0,
                        })
            
            logger.info(f"Generated ontology from text with {len(nodes)} nodes, {len(edges)} edges")
            
        except Exception as exc:
            logger.exception("Failed to generate ontology from schema text; aborting ontology creation.")
            raise HTTPException(status_code=500, detail=f"Ontology generation failed: {exc}") from exc

    try:
        nodes_added, edges_added = await asyncio.to_thread(
            session.add_nodes_and_edges, nodes, edges
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    registry = _get_registry(request)
    registry[onto_uri] = OntologyEntry(
        uri=onto_uri,
        name=body.name,
        description=body.description,
        format="turtle",
        status="draft",
        version="0.1.0",
        class_count=sum(1 for n in nodes if n.get("type") == "owl:Class"),
        loaded_at=datetime.now(UTC).isoformat(),
        enabled=True,
        tags=body.tags,
    )

    return LoadOntologyResponse(
        uri=onto_uri, name=body.name,
        nodes_added=nodes_added, edges_added=edges_added, format="turtle",
    )


@router.get("/search", response_model=List[OntologySearchResult])
async def search_entities(
    q: str = Query(..., min_length=1),
    entity_type: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=200),
    session: GraphSession = Depends(get_session),
):
    # Use the session's indexed search; over-fetch to allow post-filtering by entity type
    raw_hits = await asyncio.to_thread(session.search, q, limit * 6)
    results: List[OntologySearchResult] = []

    for hit in raw_hits:
        node = hit.get("node", hit)  # session.search returns {"node": ..., "score": ...}
        ntype = node.get("type", "")
        if ntype not in _SEARCHABLE_TYPES:
            continue
        etype = _classify_node_type(ntype)
        if entity_type and etype != entity_type:
            continue

        label = _node_label(node)
        props = node.get("properties", {})
        definition = (
            props.get("rdfs:comment")
            or props.get("skos:definition")
            or props.get("description")
        )

        results.append(OntologySearchResult(
            uri=node.get("id", ""),
            label=label,
            type=ntype,
            entity_type=etype,
            definition=definition,
            source_ontology=props.get("scheme_uri"),
            namespace_prefix=_extract_namespace(node.get("id", "")),
        ))
        if len(results) >= limit:
            break

    return results


def _known_ontology_uris(
    session: GraphSession, registry: Dict[str, OntologyEntry]
) -> set[str]:
    known = set(registry)
    for node_type in _ONTOLOGY_TYPES:
        for node in session.iter_nodes(node_type=node_type):
            node_id = str(node.get("id", ""))
            if node_id:
                known.add(node_id)
    return known


def _collect_core_nodes(
    session: GraphSession, uri: str, known_ontology_uris: set[str]
) -> Dict[str, Dict[str, Any]]:
    """Stream schema nodes, keeping only the ones this ontology owns.

    Filtering as each node arrives makes _MAX_ANALYSIS_NODES bound the work and
    not merely the response: foreign nodes are discarded instead of materialized,
    and the scan stops once the owned ones pass the cap. The ownership filter has
    to stay ahead of that check — thousands of *other* ontologies' nodes must
    never make this one too large to open. Requesting pages instead would bound
    nothing: paginate_nodes normalizes the whole matching set on every call.
    """
    core_nodes_by_id: Dict[str, Dict[str, Any]] = {}
    for node_type in _SCHEMA_NODE_TYPES:
        for node in session.iter_nodes(node_type=node_type):
            node_id = str(node.get("id", ""))
            if not node_id or not _node_belongs_to_ontology(
                node, uri, known_ontology_uris
            ):
                continue
            core_nodes_by_id[node_id] = node
            if len(core_nodes_by_id) > _MAX_ANALYSIS_NODES:
                raise GraphTruncationError(_GRAPH_TOO_LARGE_DETAIL)
    return core_nodes_by_id


def _select_structure_edges(
    session: GraphSession, core_node_ids: set[str]
) -> List[Dict[str, Any]]:
    """Stream structural edges, keeping only those leaving a core node.

    The requested ontology may reference outward (e.g. rdfs:range to an external
    vocabulary), but an unrelated ontology's property pointing at a core class
    must not leak inward.
    """
    selected_edges: List[Dict[str, Any]] = []
    for edge_type in _STRUCTURE_EDGE_TYPES:
        for edge in session.iter_edges(edge_type=edge_type):
            if str(edge.get("source", "")) not in core_node_ids:
                continue
            selected_edges.append(edge)
            if len(selected_edges) > _MAX_ANALYSIS_NODES:
                raise GraphTruncationError(_GRAPH_TOO_LARGE_DETAIL)
    return selected_edges


@router.get("/graph", response_model=OntologyGraphResponse)
async def get_ontology_graph(
    request: Request,
    uri: str = Query(..., min_length=1),
    session: GraphSession = Depends(get_session),
):
    """Return the editable schema subgraph for one registered ontology."""
    known_ontology_uris = await asyncio.to_thread(
        _known_ontology_uris, session, _get_registry(request)
    )
    if uri not in known_ontology_uris:
        raise HTTPException(status_code=404, detail="Ontology not found in registry.")

    try:
        core_nodes_by_id = await asyncio.to_thread(
            _collect_core_nodes, session, uri, known_ontology_uris
        )
        if not core_nodes_by_id:
            raise HTTPException(status_code=404, detail="Ontology graph not found.")
        core_node_ids = set(core_nodes_by_id)
        selected_edges = await asyncio.to_thread(
            _select_structure_edges, session, core_node_ids
        )
    except GraphTruncationError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    # Invariant: the helpers raise the moment their accumulation passes
    # _MAX_ANALYSIS_NODES, so core_nodes_by_id and selected_edges are both
    # within the cap here; a post-filter re-check would be unreachable.
    external_node_ids = {
        node_id
        for edge in selected_edges
        for node_id in (str(edge.get("source", "")), str(edge.get("target", "")))
    } - core_node_ids
    external_nodes = await asyncio.gather(
        *(asyncio.to_thread(session.get_node, node_id) for node_id in external_node_ids)
    )

    selected_nodes = list(core_nodes_by_id.values())
    selected_nodes.extend(node for node in external_nodes if node is not None)
    selected_nodes.sort(key=lambda node: str(node.get("id", "")))
    selected_edges.sort(
        key=lambda edge: (
            str(edge.get("source", "")),
            str(edge.get("type", "")),
            str(edge.get("target", "")),
            str(edge.get("id", "")),
        )
    )
    return OntologyGraphResponse(uri=uri, nodes=selected_nodes, edges=selected_edges)


@router.get("/entity/{entity_uri:path}", response_model=EntityDetailResponse)
async def get_entity_detail(
    entity_uri: str,
    session: GraphSession = Depends(get_session),
):
    node = await asyncio.to_thread(session.get_node, entity_uri)
    if node is None:
        raise HTTPException(status_code=404, detail="Entity not found.")

    props = node.get("properties", {})
    ntype = node.get("type", "")
    label = _node_label(node)
    definition = props.get("rdfs:comment") or props.get("skos:definition") or props.get("description")

    out_edges, _ = await asyncio.to_thread(session.get_edges, source=entity_uri, skip=0, limit=9999)
    in_edges, _ = await asyncio.to_thread(session.get_edges, target=entity_uri, skip=0, limit=9999)

    superclasses = [e["target"] for e in out_edges if e.get("type") in {"rdfs:subClassOf", "skos:broader"}]
    subclasses = [e["source"] for e in in_edges if e.get("type") in {"rdfs:subClassOf", "skos:broader"}]
    domain = [e["target"] for e in out_edges if e.get("type") == "rdfs:domain"]
    range_ = [e["target"] for e in out_edges if e.get("type") == "rdfs:range"]

    all_nodes, _ = await asyncio.to_thread(session.get_nodes, skip=0, limit=999_999)
    instance_count = sum(1 for n in all_nodes if n.get("type") == entity_uri)

    return EntityDetailResponse(
        uri=entity_uri, label=label,
        type=ntype, entity_type=_classify_node_type(ntype),
        definition=definition,
        source_ontology=props.get("scheme_uri"),
        superclasses=superclasses, subclasses=subclasses,
        domain=domain, range=range_,
        instance_count=instance_count, properties=props,
    )


@router.get("/skos/schemes", response_model=List[SKOSScheme])
async def list_skos_schemes(session: GraphSession = Depends(get_session)):
    """List SKOS concept schemes using OntologyEngine.list_vocabularies()."""
    try:
        from ...ontology import OntologyEngine
        
        # Initialize OntologyEngine with session's graph store
        engine_config = {"store": session.graph.store if hasattr(session.graph, "store") else None}
        engine = OntologyEngine(**engine_config)
        
        # Use OntologyEngine.list_vocabularies
        vocabularies = await asyncio.to_thread(engine.list_vocabularies)
        
        # Count concepts per scheme
        all_nodes, _ = await asyncio.to_thread(session.get_nodes, skip=0, limit=999_999)
        concept_counts: Dict[str, int] = {}
        for node in all_nodes:
            scheme_uri = node.get("properties", {}).get("scheme_uri")
            if scheme_uri and node.get("type") in _CONCEPT_TYPES:
                concept_counts[scheme_uri] = concept_counts.get(scheme_uri, 0) + 1
        
        return [
            SKOSScheme(
                uri=vocab["uri"],
                title=vocab["label"] or vocab["uri"].rsplit("/", 1)[-1].rsplit("#", 1)[-1],
                description=None,
                concept_count=concept_counts.get(vocab["uri"], 0),
            )
            for vocab in vocabularies
        ]
    except Exception as exc:
        logger.warning(f"OntologyEngine.list_vocabularies failed, falling back to session: {exc}")
        # Fallback to session-based implementation
        nodes, _ = await asyncio.to_thread(
            session.get_nodes, node_type="skos:ConceptScheme", skip=0, limit=999_999
        )
        all_edges, _ = await asyncio.to_thread(session.get_edges, skip=0, limit=999_999)
        concept_counts: Dict[str, int] = {}
        for edge in all_edges:
            if edge.get("type") in {"skos:inScheme", "skos:topConceptOf"}:
                concept_counts[edge["target"]] = concept_counts.get(edge["target"], 0) + 1
            elif edge.get("type") == "skos:hasTopConcept":
                concept_counts[edge["source"]] = concept_counts.get(edge["source"], 0) + 1

        result = []
        for node in nodes:
            props = node.get("properties", {})
            nid = node.get("id", "")
            result.append(SKOSScheme(
                uri=nid,
                title=_node_label(node),
                description=props.get("description") or props.get("skos:definition"),
                concept_count=concept_counts.get(nid, 0),
            ))
        return result


@router.post("/skos/search", response_model=List[OntologySearchResult])
async def search_skos_concepts(
    body: SKOSConceptSearchRequest,
    session: GraphSession = Depends(get_session),
):
    """Search SKOS concepts using OntologyEngine.search_concepts()."""
    try:
        from ...ontology import OntologyEngine
        
        # Initialize OntologyEngine with session's graph store
        engine_config = {"store": session.graph.store if hasattr(session.graph, "store") else None}
        engine = OntologyEngine(**engine_config)
        
        # Use OntologyEngine.search_concepts
        concepts = await asyncio.to_thread(
            engine.search_concepts,
            body.query,
            scheme_uri=body.scheme_uri
        )
        
        return [
            OntologySearchResult(
                uri=concept["uri"],
                label=concept["label"],
                type="skos:Concept",
                entity_type="concept",
                definition=None,
                source_ontology=body.scheme_uri,
                namespace_prefix=_extract_namespace(concept["uri"]),
            )
            for concept in concepts
        ]
    except Exception as exc:
        logger.warning(f"OntologyEngine.search_concepts failed, using fallback: {exc}")
        # Fallback to session-based search
        raw_hits = await asyncio.to_thread(session.search, body.query, 300)
        results: List[OntologySearchResult] = []

        for hit in raw_hits:
            node = hit.get("node", hit)
            ntype = node.get("type", "")
            if ntype not in _CONCEPT_TYPES:
                continue
            if body.scheme_uri:
                scheme = node.get("properties", {}).get("scheme_uri")
                if scheme != body.scheme_uri:
                    continue

            label = _node_label(node)
            props = node.get("properties", {})
            definition = (
                props.get("rdfs:comment")
                or props.get("skos:definition")
                or props.get("description")
            )

            results.append(OntologySearchResult(
                uri=node.get("id", ""),
                label=label,
                type=ntype,
                entity_type="concept",
                definition=definition,
                source_ontology=props.get("scheme_uri"),
                namespace_prefix=_extract_namespace(node.get("id", "")),
            ))
            if len(results) >= 50:
                break

        return results


@router.get("/skos/concept/{concept_uri:path}", response_model=SKOSConceptDetail)
async def get_skos_concept(
    concept_uri: str,
    session: GraphSession = Depends(get_session),
):
    """Get SKOS concept detail using OntologyEngine.list_concepts() and search_concepts()."""
    try:
        from ...ontology import OntologyEngine
        
        # Initialize OntologyEngine with session's graph store
        engine_config = {"store": session.graph.store if hasattr(session.graph, "store") else None}
        engine = OntologyEngine(**engine_config)
        
        # Try to get scheme_uri from node first
        node = await asyncio.to_thread(session.get_node, concept_uri)
        if node is None:
            raise HTTPException(status_code=404, detail="Concept not found.")
        
        scheme_uri = node.get("properties", {}).get("scheme_uri")
        
        # Use OntologyEngine.list_concepts if scheme_uri is known
        if scheme_uri:
            concepts = await asyncio.to_thread(engine.list_concepts, scheme_uri)
            concept_data = next((c for c in concepts if c["uri"] == concept_uri), None)
            
            if concept_data:
                return SKOSConceptDetail(
                    uri=concept_data["uri"],
                    pref_label=concept_data["pref_label"],
                    alt_labels=concept_data.get("alt_labels", []),
                    hidden_labels=[],
                    definition=None,
                    scope_note=None,
                    editorial_note=None,
                    broader=[],
                    narrower=[],
                    related=[],
                    exact_match=[],
                    close_match=[],
                    broad_match=[],
                    narrow_match=[],
                    scheme_uri=scheme_uri,
                )
        
        # Fallback to session-based implementation
        props = node.get("properties", {})
        out_edges, _ = await asyncio.to_thread(session.get_edges, source=concept_uri, skip=0, limit=9999)
        in_edges, _ = await asyncio.to_thread(session.get_edges, target=concept_uri, skip=0, limit=9999)

        def collect_out(rel: str) -> List[str]:
            return [e["target"] for e in out_edges if e.get("type") == rel]

        def collect_in(rel: str) -> List[str]:
            return [e["source"] for e in in_edges if e.get("type") == rel]

        pref_label = props.get("pref_label") or props.get("skos:prefLabel") or _node_label(node)
        alt_labels = props.get("alt_labels") or props.get("skos:altLabel") or []
        if isinstance(alt_labels, str):
            alt_labels = [alt_labels]
        hidden_labels = props.get("skos:hiddenLabel") or []
        if isinstance(hidden_labels, str):
            hidden_labels = [hidden_labels]

        if not scheme_uri:
            candidates = collect_out("skos:inScheme") or collect_out("skos:topConceptOf")
            scheme_uri = candidates[0] if candidates else None

        return SKOSConceptDetail(
            uri=concept_uri,
            pref_label=pref_label,
            alt_labels=list(alt_labels),
            hidden_labels=list(hidden_labels),
            definition=props.get("definition") or props.get("skos:definition"),
            scope_note=props.get("skos:scopeNote"),
            editorial_note=props.get("skos:editorialNote"),
            broader=collect_out("skos:broader") + collect_in("skos:narrower"),
            narrower=collect_out("skos:narrower") + collect_in("skos:broader"),
            related=collect_out("skos:related"),
            exact_match=collect_out("skos:exactMatch"),
            close_match=collect_out("skos:closeMatch"),
            broad_match=collect_out("skos:broadMatch"),
            narrow_match=collect_out("skos:narrowMatch"),
            scheme_uri=scheme_uri,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"OntologyEngine SKOS methods failed, using fallback: {exc}")
        # Fallback to session-based implementation
        node = await asyncio.to_thread(session.get_node, concept_uri)
        if node is None:
            raise HTTPException(status_code=404, detail="Concept not found.")

        props = node.get("properties", {})
        out_edges, _ = await asyncio.to_thread(session.get_edges, source=concept_uri, skip=0, limit=9999)
        in_edges, _ = await asyncio.to_thread(session.get_edges, target=concept_uri, skip=0, limit=9999)

        def collect_out(rel: str) -> List[str]:
            return [e["target"] for e in out_edges if e.get("type") == rel]

        def collect_in(rel: str) -> List[str]:
            return [e["source"] for e in in_edges if e.get("type") == rel]

        pref_label = props.get("pref_label") or props.get("skos:prefLabel") or _node_label(node)
        alt_labels = props.get("alt_labels") or props.get("skos:altLabel") or []
        if isinstance(alt_labels, str):
            alt_labels = [alt_labels]
        hidden_labels = props.get("skos:hiddenLabel") or []
        if isinstance(hidden_labels, str):
            hidden_labels = [hidden_labels]

        scheme_uri = props.get("scheme_uri")
        if not scheme_uri:
            candidates = collect_out("skos:inScheme") or collect_out("skos:topConceptOf")
            scheme_uri = candidates[0] if candidates else None

        return SKOSConceptDetail(
            uri=concept_uri,
            pref_label=pref_label,
            alt_labels=list(alt_labels),
            hidden_labels=list(hidden_labels),
            definition=props.get("definition") or props.get("skos:definition"),
            scope_note=props.get("skos:scopeNote"),
            editorial_note=props.get("skos:editorialNote"),
            broader=collect_out("skos:broader") + collect_in("skos:narrower"),
            narrower=collect_out("skos:narrower") + collect_in("skos:broader"),
            related=collect_out("skos:related"),
            exact_match=collect_out("skos:exactMatch"),
            close_match=collect_out("skos:closeMatch"),
            broad_match=collect_out("skos:broadMatch"),
            narrow_match=collect_out("skos:narrowMatch"),
            scheme_uri=scheme_uri,
        )


# alignments, health, and SHACL studio


@router.get("/alignments", response_model=List[OntologyAlignment])
async def list_alignments(
    request: Request,
    uri: Optional[str] = Query(None),
):
    store = _get_alignment_store(request)
    alignments = list(store.values())
    if uri:
        alignments = [
            item for item in alignments
            if item.source_uri.startswith(uri) or item.target_uri.startswith(uri)
        ]
    return sorted(alignments, key=lambda item: (item.source_label, item.target_label, item.relation))


@router.post("/alignments", response_model=OntologyAlignment)
async def upsert_alignment(
    request: Request,
    body: OntologyAlignmentRequest,
    session: GraphSession = Depends(get_session),
):
    source_node = await asyncio.to_thread(session.get_node, body.source_uri)
    target_node = await asyncio.to_thread(session.get_node, body.target_uri)
    # External vocabulary URIs (e.g. schema.org, DBpedia) are not in the local
    # graph; fall back to a label derived from the URI or the caller-supplied label.
    source_label = (
        body.source_label
        or (_node_label(source_node) if source_node is not None else None)
        or _label_from_uri(body.source_uri)
    )
    target_label = (
        body.target_label
        or (_node_label(target_node) if target_node is not None else None)
        or _label_from_uri(body.target_uri)
    )

    now = datetime.now(UTC).isoformat()
    store = _get_alignment_store(request)
    alignment_id = _alignment_id(body.source_uri, body.relation, body.target_uri)
    existing = store.get(alignment_id)
    alignment = OntologyAlignment(
        id=alignment_id,
        source_uri=body.source_uri,
        source_label=source_label,
        target_uri=body.target_uri,
        target_label=target_label,
        relation=body.relation,
        predicate_uri=_ALIGNMENT_RELATIONS[body.relation],
        confidence=body.confidence,
        provenance=body.provenance,
        source=body.source,
        reviewer=body.reviewer,
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    store[alignment_id] = alignment
    # OntologyEngine.create_alignment() requires a TripletStore (e.g. FalkorDB) which is
    # not configured in the explorer deployment. Alignments are intentionally stored only
    # in request.app.state (session memory). The ephemeral-storage banner in the UI
    # communicates this limitation to users.
    return alignment


@router.delete("/alignments")
async def delete_alignment(request: Request, id: str = Query(...)):
    store = _get_alignment_store(request)
    if id not in store:
        raise HTTPException(status_code=404, detail="Alignment not found.")
    del store[id]
    return {"status": "removed", "id": id}


@router.post("/suggest-alignments", response_model=List[AlignmentSuggestion])
async def suggest_alignments(
    body: AlignmentSuggestionRequest,
    session: GraphSession = Depends(get_session),
):
    nodes, total_count = await asyncio.to_thread(session.get_nodes, skip=0, limit=_MAX_ANALYSIS_NODES)
    if total_count > _MAX_ANALYSIS_NODES:
        logger.warning(
            "suggest-alignments: graph has %d nodes; analysis capped at %d. "
            "Filter by source/target ontology URI for more accurate results.",
            total_count, _MAX_ANALYSIS_NODES,
        )
    source_nodes = _ontology_entities(nodes, body.source_ontology_uri)
    target_nodes = _ontology_entities(nodes, body.target_ontology_uri)
    if not body.source_ontology_uri:
        source_nodes = _ontology_entities(nodes)
    if not body.target_ontology_uri:
        target_nodes = _ontology_entities(nodes)

    # Per-side entity cap to bound the O(n²) comparison loop.
    if len(source_nodes) > _MAX_ENTITIES_PER_SIDE:
        logger.warning("suggest-alignments: source side capped at %d entities.", _MAX_ENTITIES_PER_SIDE)
        source_nodes = source_nodes[:_MAX_ENTITIES_PER_SIDE]
    if len(target_nodes) > _MAX_ENTITIES_PER_SIDE:
        logger.warning("suggest-alignments: target side capped at %d entities.", _MAX_ENTITIES_PER_SIDE)
        target_nodes = target_nodes[:_MAX_ENTITIES_PER_SIDE]

    # Build TF-IDF character-ngram embeddings for all candidate labels.
    all_entities = source_nodes + target_nodes
    all_labels = list({_node_label(n) for n in all_entities if _node_label(n)})
    embeddings: Optional[Dict[str, List[float]]] = await asyncio.to_thread(_tfidf_embedding_vectors, all_labels)
    has_embeddings = embeddings is not None

    # Pre-build token sets for targets to enable O(1) prefiltering (skip zero-overlap pairs).
    target_token_sets: Dict[str, frozenset] = {
        n.get("id", ""): _token_set(_node_label(n)) for n in target_nodes
    }

    suggestions: List[AlignmentSuggestion] = []
    for source_node in source_nodes:
        source_id = source_node.get("id", "")
        source_label = _node_label(source_node)
        source_ontology = _node_source_ontology(source_node)
        source_tokens = _token_set(source_label)
        source_vec = embeddings.get(source_label) if has_embeddings else None

        for target_node in target_nodes:
            target_id = target_node.get("id", "")
            if not source_id or source_id == target_id:
                continue
            target_ontology = _node_source_ontology(target_node)
            if source_ontology and target_ontology and source_ontology == target_ontology:
                continue

            # Token-overlap prefilter: skip pairs with zero shared tokens (Jaccard=0 ⇒ label_sim≈0).
            target_tokens = target_token_sets.get(target_id, frozenset())
            if source_tokens and target_tokens and not (source_tokens & target_tokens):
                continue

            target_label = _node_label(target_node)
            label_score = _label_similarity(source_label, target_label)

            embedding_sim: Optional[float] = None
            if has_embeddings and source_vec is not None:
                target_vec = embeddings.get(target_label)
                if target_vec is not None:
                    try:
                        embedding_sim = round(_cosine_sim(source_vec, target_vec), 4)
                    except Exception:
                        embedding_sim = None

            # Combined score: average label and embedding similarity when both are available.
            if embedding_sim is not None:
                score = round(0.4 * label_score + 0.6 * embedding_sim, 4)
                reason = (
                    f"Label similarity {label_score:.2f}, embedding cosine similarity {embedding_sim:.2f} "
                    f"(TF-IDF character n-gram vectors via SimilarityCalculator)."
                )
            else:
                score = label_score
                reason = f"Label similarity {label_score:.2f}; embedding vectors unavailable."

            if score < body.threshold:
                continue

            relation = _candidate_relation(source_node, target_node)
            suggestions.append(AlignmentSuggestion(
                source_uri=source_id,
                source_label=source_label,
                target_uri=target_id,
                target_label=target_label,
                relation=relation,
                score=score,
                label_similarity=label_score,
                embedding_similarity=embedding_sim,
                reason=reason,
            ))

    suggestions.sort(key=lambda item: item.score, reverse=True)
    return suggestions[:body.limit]


@router.get("/health", response_model=OntologyHealthResponse)
async def ontology_health(
    request: Request,
    uri: str = Query(...),
    session: GraphSession = Depends(get_session),
):
    registry = {entry.uri: entry for entry in await _registry_entries(request, session)}
    entry = registry.get(uri)
    if entry is None:
        raise HTTPException(status_code=404, detail="Ontology not found in registry.")

    nodes, total_nodes = await asyncio.to_thread(session.get_nodes, skip=0, limit=_MAX_ANALYSIS_NODES)
    edges, _ = await asyncio.to_thread(session.get_edges, skip=0, limit=_MAX_ANALYSIS_NODES)
    if total_nodes > _MAX_ANALYSIS_NODES:
        logger.warning("ontology-health: graph has %d nodes; analysis capped at %d.", total_nodes, _MAX_ANALYSIS_NODES)
    entities = _ontology_entities(nodes, uri)
    classes = [node for node in entities if _classify_node_type(node.get("type", "")) == "class"]
    properties = [node for node in entities if _classify_node_type(node.get("type", "")) == "property"]
    assessed = classes + properties

    issues: List[HealthIssue] = []
    total = max(len(assessed), 1)
    with_label = sum(1 for node in assessed if _node_label(node))
    with_comment = sum(1 for node in assessed if _entity_description(node))
    with_definition = sum(1 for node in assessed if _entity_definition(node))
    completeness_score = ((with_label + with_comment + with_definition) / (total * 3)) * 100

    for node in assessed:
        label = _node_label(node)
        if not _entity_description(node):
            issues.append(HealthIssue(
                id=f"doc:{node.get('id')}",
                severity="warning",
                category="Documentation",
                entity_uri=node.get("id"),
                entity_label=label,
                message=f"{label} is missing a comment or definition.",
                action="Add documentation in Editor.",
            ))

    property_range_edges = {
        edge.get("source")
        for edge in edges
        if edge.get("type") == "rdfs:range"
    }
    missing_range = [node for node in properties if node.get("id") not in property_range_edges]
    for node in missing_range[:25]:
        issues.append(HealthIssue(
            id=f"range:{node.get('id')}",
            severity="info",
            category="Consistency",
            entity_uri=node.get("id"),
            entity_label=_node_label(node),
            message="Property has no explicit rdfs:range.",
            action="Review property range in Editor.",
        ))

    consistency_score = max(0.0, 100.0 - (len(missing_range) / max(len(properties), 1)) * 60.0)

    assessed_ids = {node.get("id") for node in assessed if node.get("id")}
    alignments = _get_alignment_store(request).values()
    aligned_sources = {
        item.source_uri for item in alignments if item.source_uri in assessed_ids
    } | {
        item.target_uri for item in alignments if item.target_uri in assessed_ids
    }
    alignment_score = (len(aligned_sources) / total) * 100
    if assessed and not aligned_sources:
        issues.append(HealthIssue(
            id=f"alignment:{uri}",
            severity="warning",
            category="Alignment",
            message="No cross-ontology alignments are recorded for local classes or properties.",
            action="Review suggested alignments.",
        ))

    documentation_score = ((with_comment / total) * 80.0) + (20.0 if entry.version or entry.source_url else 0.0)

    try:
        health_nodes, health_edges = await _fetch_analysis_graph(session, uri, "shacl-health")
        shacl_turtle, _ = await _generated_shacl_for_uri(
            request, session, uri, nodes=health_nodes, edges=health_edges
        )
        data_graph_turtle = await _data_graph_turtle_for_uri(
            request, session, uri, nodes=health_nodes, edges=health_edges
        )
        from ...ontology import OntologyEngine
        engine = OntologyEngine()
        report = await asyncio.to_thread(
            engine.validate_graph,
            data_graph_turtle,
            shacl=shacl_turtle,
            data_graph_format="turtle",
            shacl_format="turtle",
        )
        warning_count = len(report.warnings)
        if not report.conforms:
            shacl_score = max(0.0, 100.0 - (report.violation_count * 20.0))
        elif warning_count:
            shacl_score = max(0.0, 100.0 - (warning_count * 5.0))
        else:
            shacl_score = 100.0
        shacl_status = "ok" if report.conforms and not warning_count else "warning"
        detail_parts = []
        if not report.conforms:
            detail_parts.append(f"{report.violation_count} SHACL violation(s)")
        if warning_count:
            detail_parts.append(f"{warning_count} SHACL warning(s)")
        shacl_detail = (
            "Graph conforms to all generated SHACL constraints."
            if not detail_parts
            else f"Graph has {', '.join(detail_parts)}."
        )
        shacl_dimension = HealthDimension(
            key="shacl",
            label="SHACL Conformance",
            score=round(shacl_score, 1),
            status=shacl_status,
            detail=shacl_detail,
        )
    except GraphTruncationError as exc:
        shacl_dimension = HealthDimension(
            key="shacl",
            label="SHACL Conformance",
            score=0.0,
            status="critical",
            detail=str(exc),
        )
    except ImportError:
        shacl_dimension = HealthDimension(
            key="shacl",
            label="SHACL Conformance",
            score=0.0,
            status="unavailable",
            detail="Live SHACL validation is available in SHACL Studio when optional validation dependencies are installed.",
        )
    except Exception as exc:
        shacl_dimension = HealthDimension(
            key="shacl",
            label="SHACL Conformance",
            score=0.0,
            status="critical",
            detail=f"Live SHACL validation failed: {exc}",
        )

    dimensions = [
        HealthDimension(
            key="completeness",
            label="Completeness",
            score=round(completeness_score, 1),
            status="ok" if completeness_score >= 80 else "warning",
            detail=f"{with_label}/{total} labeled, {with_comment}/{total} documented, {with_definition}/{total} defined.",
        ),
        HealthDimension(
            key="consistency",
            label="Consistency",
            score=round(consistency_score, 1),
            status="ok" if consistency_score >= 80 else "warning",
            detail=f"{len(missing_range)} properties are missing explicit ranges.",
        ),
        shacl_dimension,
        HealthDimension(
            key="alignment",
            label="Alignment Coverage",
            score=round(alignment_score, 1),
            status="ok" if alignment_score >= 50 else "warning",
            detail=f"{len(aligned_sources)}/{total} classes or properties have an alignment.",
        ),
        HealthDimension(
            key="documentation",
            label="Documentation",
            score=round(documentation_score, 1),
            status="ok" if documentation_score >= 75 else "warning",
            detail="Measures comments plus source/version metadata.",
        ),
    ]
    scoreable = [dim for dim in dimensions if dim.status != "unavailable"]
    total_score = sum(dim.score for dim in scoreable) / max(len(scoreable), 1)

    return OntologyHealthResponse(
        uri=uri,
        name=entry.name,
        total_score=round(total_score, 1),
        dimensions=dimensions,
        issues=issues[:100],
        generated_at=datetime.now(UTC).isoformat(),
    )


async def _fetch_analysis_graph(
    session: GraphSession,
    uri: str,
    log_tag: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Fetch nodes/edges for SHACL analysis, raising GraphTruncationError if oversized.

    Shared by `_generated_shacl_for_uri` and `_data_graph_turtle_for_uri` so callers that
    need both (e.g. `/health`) can fetch once and pass the results to both via `nodes=`/`edges=`.
    """
    nodes, total_nodes = await asyncio.to_thread(session.get_nodes, skip=0, limit=_MAX_ANALYSIS_NODES)
    edges, total_edges = await asyncio.to_thread(session.get_edges, skip=0, limit=_MAX_ANALYSIS_NODES)
    if total_nodes > _MAX_ANALYSIS_NODES or total_edges > _MAX_ANALYSIS_NODES:
        logger.warning(
            "%s: graph for %s is too large to analyse (nodes=%d, edges=%d, limit=%d); skipping.",
            log_tag, uri, total_nodes, total_edges, _MAX_ANALYSIS_NODES,
        )
        raise GraphTruncationError(
            f"Graph size (nodes={total_nodes}, edges={total_edges}) exceeds maximum analysis limit ({_MAX_ANALYSIS_NODES}). "
            "SHACL validation is skipped because the graph is too large to validate fully under current limits."
        )
    return nodes, edges


async def _generated_shacl_for_uri(
    request: Request,
    session: GraphSession,
    uri: str,
    quality_tier: str = "strict",
    *,
    nodes: Optional[List[Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
) -> tuple[str, List[ShaclShapeSummary]]:
    registry = {entry.uri: entry for entry in await _registry_entries(request, session)}
    entry = registry.get(uri)
    if entry is None:
        raise HTTPException(status_code=404, detail="Ontology not found in registry.")

    if nodes is None or edges is None:
        nodes, edges = await _fetch_analysis_graph(session, uri, "shacl-generate")
    entities = _ontology_entities(nodes, uri)
    ontology_dict = _ontology_dict_from_nodes(uri, entry.name, entities, edges)

    try:
        from ...ontology import OntologyEngine
        engine = OntologyEngine()
        shacl_turtle = await asyncio.to_thread(
            engine.to_shacl,
            ontology_dict,
            format="turtle",
            quality_tier=quality_tier,
            validate_output=False,
        )
    except Exception as exc:
        logger.debug("OntologyEngine.to_shacl unavailable; using basic generator: %s", exc)
        shacl_turtle = _basic_shacl_turtle(uri, entry.name, entities)

    return shacl_turtle, _summarize_shapes(shacl_turtle)


async def _data_graph_turtle_for_uri(
    request: Request,
    session: GraphSession,
    uri: str,
    *,
    nodes: Optional[List[Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
) -> str:
    try:
        import rdflib
    except ImportError as exc:
        raise ImportError("rdflib is not installed.") from exc

    registry = {entry.uri: entry for entry in await _registry_entries(request, session)}
    if uri not in registry:
        raise HTTPException(status_code=404, detail="Ontology not found in registry.")

    if nodes is None or edges is None:
        nodes, edges = await _fetch_analysis_graph(session, uri, "shacl-data-graph")
    entities = _data_graph_entities(nodes, uri)

    g = rdflib.Graph()
    base_namespace = _ontology_namespace(uri)

    OWL = rdflib.Namespace("http://www.w3.org/2002/07/owl#")
    RDF = rdflib.RDF
    RDFS = rdflib.RDFS
    SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")
    DCT = rdflib.Namespace("http://purl.org/dc/terms/")
    DC = rdflib.Namespace("http://purl.org/dc/elements/1.1/")
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    XSD = rdflib.XSD
    ONTO = rdflib.Namespace(base_namespace)

    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("skos", SKOS)
    g.bind("dct", DCT)
    g.bind("dc", DC)
    g.bind("sh", SH)
    g.bind("xsd", XSD)
    g.bind("onto", ONTO)

    def _resolve_uri(val: str, base_ns: str) -> rdflib.URIRef:
        val_str = str(val).strip()
        if val_str == "a":
            return rdflib.RDF.type
        if val_str.startswith(("http://", "https://", "urn:", "ftp://")):
            return rdflib.URIRef(val_str)
        prefix_map = {
            "owl": "http://www.w3.org/2002/07/owl#",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "dct": "http://purl.org/dc/terms/",
            "dc": "http://purl.org/dc/elements/1.1/",
            "sh": "http://www.w3.org/ns/shacl#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "onto": base_ns,
        }
        if ":" in val_str and not val_str.startswith("/"):
            prefix, _, rest = val_str.partition(":")
            if prefix in prefix_map:
                return rdflib.URIRef(prefix_map[prefix] + rest)
            return rdflib.URIRef(val_str)
        if val_str.startswith("#"):
            val_str = val_str.lstrip("#")
        if base_ns.endswith(("/", "#")):
            return rdflib.URIRef(base_ns + val_str.lstrip("/"))
        return rdflib.URIRef(base_ns + "#" + val_str.lstrip("/"))

    _shorthand_types = {
        "class": "owl:Class",
        "object_property": "owl:ObjectProperty",
        "datatype_property": "owl:DatatypeProperty",
        "annotation_property": "owl:AnnotationProperty",
        "property": "rdf:Property",
        "individual": "owl:NamedIndividual",
        "concept": "skos:Concept",
        "scheme": "skos:ConceptScheme",
        "ontology": "owl:Ontology",
    }
    _uri_predicates = {
        "rdf:type",
        "a",
        "rdfs:subClassOf",
        "rdfs:domain",
        "rdfs:range",
        "owl:equivalentClass",
        "owl:equivalentProperty",
        "owl:sameAs",
        "skos:exactMatch",
        "skos:closeMatch",
        "skos:broadMatch",
        "skos:narrowMatch",
        "skos:relatedMatch",
        "sh:targetClass",
        "sh:targetNode",
    }
    _literal_predicates = {
        "rdfs:label",
        "rdfs:comment",
        "skos:definition",
        "skos:prefLabel",
        "skos:altLabel",
        "dct:description",
        "dct:title",
        "dc:title",
        "dc:description",
        "version",
    }
    _skip_keys = {
        "id",
        "type",
        "content",
        "valid_from",
        "valid_until",
        "scheme_uri",
        "ontology_uri",
        "ontology",
    }

    entity_ids = set()
    for node in entities:
        nid_str = str(node.get("id", "")).strip()
        if not nid_str:
            continue
        entity_ids.add(nid_str)
        subj = _resolve_uri(nid_str, base_namespace)

        node_type = node.get("type", "")
        if node_type:
            for t in _as_uri_list(node_type):
                t_mapped = _shorthand_types.get(str(t).lower(), str(t))
                g.add((subj, rdflib.RDF.type, _resolve_uri(t_mapped, base_namespace)))

        content = str(node.get("content", "")).strip()
        props = node.get("properties", {}) or {}
        if content and "rdfs:label" not in props and "pref_label" not in props and "label" not in props:
            g.add((subj, RDFS.label, rdflib.Literal(content)))

        for key, val in props.items():
            if key in _skip_keys or val is None or val == "":
                continue
            pred = _resolve_uri(str(key), base_namespace)
            for item in _as_uri_list(val) if isinstance(val, (list, dict)) else [val]:
                if item is None or item == "":
                    continue
                if isinstance(item, dict):
                    item = item.get("uri") or item.get("id") or item.get("@id")
                    if not item:
                        continue
                if str(key) in _uri_predicates or (
                    str(key) not in _literal_predicates
                    and str(item).strip().startswith(("http://", "https://", "urn:"))
                ):
                    g.add((subj, pred, _resolve_uri(str(item), base_namespace)))
                else:
                    g.add((subj, pred, rdflib.Literal(str(item))))

    for edge in edges:
        source = str(edge.get("source", edge.get("source_id", ""))).strip()
        target = str(edge.get("target", edge.get("target_id", ""))).strip()
        pred_str = str(edge.get("type", "related_to")).strip()
        if not source or not target:
            continue
        if source in entity_ids or target in entity_ids:
            g.add((
                _resolve_uri(source, base_namespace),
                _resolve_uri(pred_str, base_namespace),
                _resolve_uri(target, base_namespace),
            ))

    return await asyncio.to_thread(g.serialize, format="turtle")


@router.post("/shacl/generate", response_model=ShaclGenerateResponse)
async def generate_shacl(
    request: Request,
    body: ShaclGenerateRequest,
    session: GraphSession = Depends(get_session),
):
    try:
        shacl_turtle, shapes = await _generated_shacl_for_uri(request, session, body.uri, body.quality_tier)
    except GraphTruncationError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return ShaclGenerateResponse(
        uri=body.uri,
        shacl_turtle=shacl_turtle,
        shape_count=len(shapes),
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.get("/shacl/shapes", response_model=ShaclShapesResponse)
async def list_shacl_shapes(
    request: Request,
    uri: str = Query(...),
    session: GraphSession = Depends(get_session),
):
    try:
        shacl_turtle, shapes = await _generated_shacl_for_uri(request, session, uri)
    except GraphTruncationError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return ShaclShapesResponse(
        uri=uri,
        shapes=shapes,
        shacl_turtle=shacl_turtle,
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.post("/shacl/validate", response_model=ShaclValidationResponse)
async def validate_shacl(
    request: Request,
    body: ShaclValidateRequest,
    session: GraphSession = Depends(get_session),
):
    if not body.shacl_turtle.strip():
        raise HTTPException(status_code=422, detail="SHACL Turtle cannot be empty.")

    _shacl_bytes = body.shacl_turtle.encode("utf-8")
    if len(_shacl_bytes) > _MAX_SHACL_TURTLE_BYTES:
        return ShaclValidationResponse(
            uri=body.uri,
            conforms=False,
            status="error",
            message=(
                f"SHACL Turtle size ({len(_shacl_bytes)} bytes) "
                f"exceeds maximum allowed size ({_MAX_SHACL_TURTLE_BYTES} bytes); "
                f"set SEMANTICA_MAX_SHACL_TURTLE_BYTES to raise the limit."
            ),
            violations=[],
        )

    # Syntax-check the submitted Turtle with rdflib before claiming anything about it.
    try:
        import rdflib  # type: ignore
        g = rdflib.Graph()
        await asyncio.to_thread(g.parse, data=body.shacl_turtle, format="turtle")
        if len(g) > _MAX_SHACL_TRIPLES:
            return ShaclValidationResponse(
                uri=body.uri,
                conforms=False,
                status="error",
                message=(
                    f"SHACL graph triple count ({len(g)}) "
                    f"exceeds maximum allowed limit ({_MAX_SHACL_TRIPLES}); "
                    f"set SEMANTICA_MAX_SHACL_TRIPLES to raise the limit."
                ),
                violations=[],
            )
    except ImportError:
        pass  # rdflib unavailable; skip syntax check
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid Turtle syntax: {exc}",
        ) from exc

    if not body.uri:
        return ShaclValidationResponse(
            uri=body.uri,
            conforms=False,
            status="unavailable",
            message=(
                "Turtle parsed successfully. "
                "No target ontology URI was provided — "
                "specify 'uri' to execute live SHACL validation against an ontology data graph."
            ),
            violations=[],
        )

    try:
        data_graph_turtle = await _data_graph_turtle_for_uri(request, session, body.uri)
        from ...ontology import OntologyEngine
        engine = OntologyEngine()
        semaphore = _get_shacl_semaphore()

        async def _run_validation():
            async with semaphore:
                return await asyncio.to_thread(
                    engine.validate_graph,
                    data_graph_turtle,
                    shacl=body.shacl_turtle,
                    data_graph_format="turtle",
                    shacl_format="turtle",
                )

        report = await asyncio.wait_for(
            _run_validation(),
            timeout=_MAX_SHACL_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, TimeoutError):
        return ShaclValidationResponse(
            uri=body.uri,
            conforms=False,
            status="error",
            message=(
                f"SHACL validation timed out after {_MAX_SHACL_TIMEOUT_SECONDS} seconds; "
                f"set SEMANTICA_MAX_SHACL_TIMEOUT to raise the timeout."
            ),
            violations=[],
        )
    except GraphTruncationError as exc:
        return ShaclValidationResponse(
            uri=body.uri,
            conforms=False,
            status="unavailable",
            message=str(exc),
            violations=[],
        )
    except ImportError as exc:
        return ShaclValidationResponse(
            uri=body.uri,
            conforms=False,
            status="unavailable",
            message=(
                "Turtle parsed successfully. "
                f"Live SHACL validation is unavailable: {exc}"
            ),
            violations=[],
        )
    except HTTPException:
        raise
    except Exception as exc:
        return ShaclValidationResponse(
            uri=body.uri,
            conforms=False,
            status="error",
            message=f"SHACL validation error: {exc}",
            violations=[],
        )

    violations = [
        ShaclViolation(
            node=str(v.focus_node) if v.focus_node is not None else None,
            path=str(v.result_path) if v.result_path is not None else None,
            severity=str(v.severity or "Violation"),
            message=str(
                v.message
                or v.explanation
                or f"SHACL constraint violation ({v.constraint}) on {v.focus_node}"
            ),
            focus_node=str(v.focus_node) if v.focus_node is not None else None,
            source_shape=str(v.shape) if v.shape is not None else None,
        )
        for v in [*report.violations, *report.warnings, *report.infos]
    ]
    _result_counts = []
    if report.violations:
        _result_counts.append(f"{len(report.violations)} violation(s)")
    if report.warnings:
        _result_counts.append(f"{len(report.warnings)} warning(s)")
    if report.infos:
        _result_counts.append(f"{len(report.infos)} info result(s)")
    summary_msg = (
        f"SHACL validation found {', '.join(_result_counts)}."
        if _result_counts
        else "Graph conforms to SHACL shapes."
    )
    return ShaclValidationResponse(
        uri=body.uri,
        conforms=report.conforms,
        status="success",
        message=summary_msg,
        violations=violations,
        report_text=report.raw_report,
    )


# ---------------------------------------------------------------------------
# Wildcard management endpoints (must come after specific routes)
# ---------------------------------------------------------------------------

@router.delete("/{ontology_uri:path}")
async def remove_ontology(ontology_uri: str, request: Request):
    registry = _get_registry(request)
    if ontology_uri not in registry:
        raise HTTPException(status_code=404, detail="Ontology not found in registry.")
    del registry[ontology_uri]
    return {"status": "removed", "uri": ontology_uri}


@router.patch("/{ontology_uri:path}/toggle", response_model=ToggleResponse)
async def toggle_ontology(ontology_uri: str, request: Request):
    registry = _get_registry(request)
    if ontology_uri not in registry:
        raise HTTPException(status_code=404, detail="Ontology not found in registry.")
    entry = registry[ontology_uri]
    entry.enabled = not entry.enabled
    return ToggleResponse(uri=ontology_uri, enabled=entry.enabled)


@router.post("/{ontology_uri:path}/refresh", response_model=RefreshResponse)
async def refresh_ontology(
    ontology_uri: str,
    request: Request,
    session: GraphSession = Depends(get_session),
):
    registry = _get_registry(request)
    if ontology_uri not in registry:
        raise HTTPException(status_code=404, detail="Ontology not found in registry.")
    entry = registry[ontology_uri]
    if not entry.source_url:
        raise HTTPException(status_code=422, detail="No source URL to refresh from.")

    raw = await asyncio.to_thread(_fetch_url_sync, entry.source_url)
    content_str = raw.decode("utf-8", errors="replace")

    try:
        nodes, edges, _ = await asyncio.to_thread(
            _parse_rdf_sync, content_str.encode("utf-8"), entry.format
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Refresh parse error: {exc}") from exc

    try:
        nodes_added, edges_added = await asyncio.to_thread(
            session.add_nodes_and_edges, nodes, edges
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry.loaded_at = datetime.now(UTC).isoformat()

    return RefreshResponse(uri=ontology_uri, nodes_added=nodes_added, edges_added=edges_added)


# ---------------------------------------------------------------------------
# Draft endpoints
# ---------------------------------------------------------------------------

@router.patch("/draft", response_model=DraftResponse)
async def save_draft(
    request: Request,
    body: DraftRequest,
):
    """Stage editor diffs as a draft with ChangeLogEntry metadata."""
    drafts = _get_drafts(request)
    draft_id = f"draft_{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()

    # Create ChangeLogEntry for audit trail
    try:
        from ...change_management.change_log import ChangeLogEntry
        ChangeLogEntry.create_now(
            author=body.author,
            description=body.summary or f"Draft changes for {body.ontology_uri}",
            change_id=draft_id
        )
    except Exception as exc:
        logger.warning(f"Failed to create ChangeLogEntry: {exc}")

    draft = DraftResponse(
        draft_id=draft_id,
        ontology_uri=body.ontology_uri,
        diff=body.diff,
        author=body.author,
        summary=body.summary,
        created_at=now,
        updated_at=now,
    )
    drafts[draft_id] = draft
    return draft


@router.get("/drafts/{ontology_uri:path}", response_model=List[DraftResponse])
async def list_drafts(
    ontology_uri: str,
    request: Request,
):
    """Get staged draft diffs for an ontology."""
    drafts = _get_drafts(request)
    return [d for d in drafts.values() if d.ontology_uri == ontology_uri]


@router.get("/draft/{draft_id}", response_model=DraftResponse)
async def get_draft(
    draft_id: str,
    request: Request,
):
    """Get a specific draft by ID."""
    drafts = _get_drafts(request)
    if draft_id not in drafts:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return drafts[draft_id]


# ---------------------------------------------------------------------------
# Proposal endpoints
# ---------------------------------------------------------------------------

@router.post("/propose", response_model=ProposalResponse)
async def submit_proposal(
    request: Request,
    body: ProposalRequest,
    session: GraphSession = Depends(get_session),
):
    """Submit a change proposal with impact analysis and SHACL pre-validation."""
    drafts = _get_drafts(request)
    proposals = _get_proposals(request)

    if body.draft_id not in drafts:
        raise HTTPException(status_code=404, detail="Draft not found.")

    draft = drafts[body.draft_id]
    proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()

    # Compute impact analysis using VersionManager.diff_ontologies and OntologyEngine
    impact_analysis = {}
    shacl_validation = {}

    try:
        from ...ontology import OntologyEngine
        from ...change_management.ontology_version_manager import VersionManager
        
        # Build ontology dicts from draft diff for comparison
        base_ontology = {"uri": body.ontology_uri, "classes": [], "properties": []}
        target_ontology = {
            "uri": body.ontology_uri,
            "classes": [{"uri": uri} for uri in draft.diff.added_classes],
            "properties": [{"uri": uri} for uri in draft.diff.added_properties],
        }
        
        # Use VersionManager.diff_ontologies for structured diff
        version_manager = VersionManager(
            store=session.graph.store if hasattr(session.graph, "store") else None
        )
        diff_result = await asyncio.to_thread(
            version_manager.diff_ontologies,
            base_ontology,
            target_ontology
        )
        
        # Use OntologyEngine for validation and SHACL
        engine_config = {"store": session.graph.store if hasattr(session.graph, "store") else None}
        engine = OntologyEngine(**engine_config)
        
        # Run validation if available
        validation_results = {}
        try:
            val_res = await asyncio.to_thread(engine.validate, target_ontology)
            validation_results = {
                "valid": getattr(val_res, "valid", getattr(val_res, "is_valid", False)),
                "consistent": getattr(val_res, "consistent", True),
                "satisfiable": getattr(val_res, "satisfiable", True),
                "errors": getattr(val_res, "errors", []),
                "warnings": getattr(val_res, "warnings", [])
            }
        except Exception as val_exc:
            logger.warning(f"Validation failed: {val_exc}")
            validation_results = {"error": str(val_exc)}
        
        # SHACL pre-validation using OntologyEngine.validate_graph
        if engine.store:
            try:
                # Generate SHACL from target ontology
                await asyncio.to_thread(
                    engine.to_shacl,
                    target_ontology,
                    format="turtle"
                )
                
                # Validate current graph data against new SHACL shapes
                all_nodes, _ = await asyncio.to_thread(session.get_nodes, skip=0, limit=999_999)
                graph_data = {"nodes": all_nodes}
                
                validation_report = await asyncio.to_thread(
                    engine.validate_graph,
                    graph_data,
                    ontology=target_ontology,
                    explain=True
                )
                
                shacl_validation = {
                    "status": "validated",
                    "conforms": getattr(validation_report, "conforms", True),
                    "violations": [
                        {
                            "message": v.message,
                            "severity": v.severity,
                            "focus_node": v.focus_node,
                        }
                        for v in getattr(validation_report, "violations", [])
                    ]
                }
            except Exception as shacl_exc:
                logger.warning(f"SHACL pre-validation failed: {shacl_exc}")
                shacl_validation = {"status": "error", "error": str(shacl_exc)}
        else:
            shacl_validation = {"status": "skipped", "reason": "No store configured"}
        
        impact_analysis = {
            "diff": diff_result,
            "validation_results": validation_results,
            "class_adds": len(draft.diff.added_classes),
            "class_removals": len(draft.diff.removed_classes),
            "property_changes": len(draft.diff.added_properties) + len(draft.diff.removed_properties),
            "restriction_changes": len(draft.diff.added_restrictions) + len(draft.diff.removed_restrictions),
        }
            
    except Exception as exc:
        logger.warning(f"Impact analysis failed: {exc}")
        impact_analysis = {"error": str(exc)}
        shacl_validation = {"status": "error", "error": str(exc)}

    proposal = ProposalResponse(
        proposal_id=proposal_id,
        draft_id=body.draft_id,
        ontology_uri=body.ontology_uri,
        summary=body.summary,
        author=draft.author,
        reviewer=body.reviewer,
        state="proposed",
        impact_analysis=impact_analysis,
        shacl_validation=shacl_validation,
        created_at=now,
        updated_at=now,
        comments=[],
    )
    proposals[proposal_id] = proposal
    return proposal


@router.get("/proposals", response_model=List[ProposalResponse])
async def list_proposals(
    request: Request,
    ontology_uri: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """List proposals with optional filters."""
    proposals = _get_proposals(request)
    result = list(proposals.values())

    if ontology_uri:
        result = [p for p in result if p.ontology_uri == ontology_uri]
    if state:
        result = [p for p in result if p.state == state]

    return result


@router.get("/proposals/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: str,
    request: Request,
):
    """Get proposal detail."""
    proposals = _get_proposals(request)
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return proposals[proposal_id]


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    request: Request,
):
    """Approve a proposal."""
    proposals = _get_proposals(request)
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    proposal = proposals[proposal_id]
    proposal.state = "approved"
    proposal.updated_at = datetime.now(UTC).isoformat()
    return {"status": "approved", "proposal_id": proposal_id}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    request: Request,
):
    """Reject a proposal (can return to draft)."""
    proposals = _get_proposals(request)
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    proposal = proposals[proposal_id]
    proposal.state = "rejected"
    proposal.updated_at = datetime.now(UTC).isoformat()
    return {"status": "rejected", "proposal_id": proposal_id}


@router.post("/proposals/{proposal_id}/publish")
async def publish_proposal(
    proposal_id: str,
    request: Request,
    session: GraphSession = Depends(get_session),
):
    """Publish an approved proposal using VersionManager.create_version()."""
    proposals = _get_proposals(request)
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    proposal = proposals[proposal_id]

    if proposal.state != "approved":
        raise HTTPException(status_code=400, detail="Only approved proposals can be published.")

    drafts = _get_drafts(request)
    if proposal.draft_id not in drafts:
        raise HTTPException(status_code=404, detail="Draft not found.")
    draft = drafts[proposal.draft_id]

    # Build ontology dict for version creation
    ontology_dict = {
        "uri": proposal.ontology_uri,
        "classes": [{"uri": uri} for uri in draft.diff.added_classes],
        "properties": [{"uri": uri} for uri in draft.diff.added_properties],
        "diff": draft.diff.model_dump(),
    }

    # Create version record using VersionManager
    try:
        from ...change_management.ontology_version_manager import VersionManager
        from ...ontology import OntologyEngine
        
        # Initialize VersionManager with proper config
        version_manager = VersionManager(
            store=session.graph.store if hasattr(session.graph, "store") else None
        )
        
        # Generate version string based on existing versions
        versions = _get_versions(request)
        existing_versions = versions.get(proposal.ontology_uri, [])
        version_num = len(existing_versions) + 1
        version_str = f"1.{version_num}.0"
        
        version_manager.create_version(
            version=version_str,
            ontology=ontology_dict,
            changes=[proposal.summary],
        )
        
        # Store version in app state
        if proposal.ontology_uri not in versions:
            versions[proposal.ontology_uri] = []
        
        versions[proposal.ontology_uri].append(
            VersionEntry(
                version_id=version_str,
                ontology_uri=proposal.ontology_uri,
                state="published",
                author=proposal.author,
                date=datetime.now(UTC).isoformat(),
                diff_summary=draft.diff.model_dump(),
            )
        )
        
        logger.info(f"Created version {version_str} for ontology {proposal.ontology_uri}")
        
    except Exception as exc:
        logger.warning(f"VersionManager.create_version failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Version creation failed: {exc}") from exc

    # Apply additions only after version creation succeeds so failed publishes do not
    # leave a partially mutated live graph.
    nodes_added = 0
    edges_added = 0

    class_nodes = []
    for class_uri in draft.diff.added_classes:
        label = class_uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        class_nodes.append({
            "id": class_uri,
            "type": "owl:Class",
            "content": label,
            "properties": {"rdfs:label": label},
        })
    if class_nodes:
        nodes_added += await asyncio.to_thread(session.add_nodes, class_nodes)

    property_nodes = []
    for prop_uri in draft.diff.added_properties:
        label = prop_uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        property_nodes.append({
            "id": prop_uri,
            "type": "owl:ObjectProperty",
            "content": label,
            "properties": {"rdfs:label": label},
        })
    if property_nodes:
        nodes_added += await asyncio.to_thread(session.add_nodes, property_nodes)

    proposal.state = "published"
    proposal.updated_at = datetime.now(UTC).isoformat()

    return {
        "status": "published",
        "proposal_id": proposal_id,
        "version": version_str,
        "nodes_added": nodes_added,
        "edges_added": edges_added,
    }


@router.post("/proposals/{proposal_id}/comment")
async def add_comment(
    proposal_id: str,
    body: CommentRequest,
    request: Request,
):
    """Add inline comment to a proposal."""
    proposals = _get_proposals(request)
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    proposal = proposals[proposal_id]
    comment = {
        "id": f"comment_{uuid.uuid4().hex[:8]}",
        "element_uri": body.element_uri,
        "text": body.text,
        "author": body.author,
        "created_at": datetime.now(UTC).isoformat(),
    }
    proposal.comments.append(comment)
    proposal.updated_at = datetime.now(UTC).isoformat()
    return {"status": "commented", "comment_id": comment["id"]}


# ---------------------------------------------------------------------------
# Version endpoints
# ---------------------------------------------------------------------------

@router.get("/versions/{ontology_uri:path}", response_model=List[VersionEntry])
async def list_versions(
    ontology_uri: str,
    request: Request,
):
    """List version history for an ontology."""
    versions = _get_versions(request)
    return versions.get(ontology_uri, [])


@router.post("/versions/{ontology_uri:path}/compare", response_model=VersionCompareResponse)
async def compare_versions(
    ontology_uri: str,
    body: VersionCompareRequest,
    request: Request,
    session: GraphSession = Depends(get_session),
):
    """Compare two ontology versions using VersionManager.compare_versions()."""
    try:
        from ...change_management.ontology_version_manager import VersionManager
        
        # Initialize VersionManager with session's graph store
        version_manager = VersionManager(
            store=session.graph.store if hasattr(session.graph, "store") else None
        )
        
        # Get version data from app state
        versions = _get_versions(request)
        ontology_versions = versions.get(ontology_uri, [])
        
        # Find version records. Older in-memory state may contain plain dicts, while
        # new publishes store VersionEntry models.
        v1_record = next((v for v in ontology_versions if _version_field(v, "version_id") == body.version1), None)
        v2_record = next((v for v in ontology_versions if _version_field(v, "version_id") == body.version2), None)
        
        if not v1_record or not v2_record:
            raise HTTPException(status_code=404, detail="One or both versions not found.")
        
        # Build ontology dicts from version records
        v1_dict = {
            "uri": ontology_uri,
            "version": body.version1,
            "classes": [],
            "properties": [],
            "diff": _version_field(v1_record, "diff_summary", {}),
        }
        v2_dict = {
            "uri": ontology_uri,
            "version": body.version2,
            "classes": [],
            "properties": [],
            "diff": _version_field(v2_record, "diff_summary", {}),
        }
        
        # Use VersionManager.diff_ontologies for structured comparison
        diff_result = await asyncio.to_thread(
            version_manager.diff_ontologies,
            v1_dict,
            v2_dict
        )
        
        metadata_changes = {
            "version_id": {"from": body.version1, "to": body.version2},
            "author": {
                "from": _version_field(v1_record, "author"),
                "to": _version_field(v2_record, "author"),
            },
            "date": {
                "from": _version_field(v1_record, "date"),
                "to": _version_field(v2_record, "date"),
            },
            "state": {
                "from": _version_field(v1_record, "state"),
                "to": _version_field(v2_record, "state"),
            },
        }
        
        return VersionCompareResponse(
            version1=body.version1,
            version2=body.version2,
            metadata_changes=metadata_changes,
            class_changes={
                "added": diff_result.get("added_classes", []),
                "removed": diff_result.get("removed_classes", []),
                "changed": diff_result.get("changed_classes", []),
            },
            property_changes={
                "added": diff_result.get("added_properties", []),
                "removed": diff_result.get("removed_properties", []),
                "changed": diff_result.get("changed_properties", []),
            },
            restriction_changes={
                "added": diff_result.get("added_axioms", []),
                "removed": diff_result.get("removed_axioms", []),
                "changed": diff_result.get("changed_axioms", []),
            },
            axiom_changes={
                "added": diff_result.get("added_axioms", []),
                "removed": diff_result.get("removed_axioms", []),
                "changed": diff_result.get("changed_axioms", []),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Version comparison failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Version comparison failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Alignment endpoints using OntologyEngine
# ---------------------------------------------------------------------------

@router.post("/alignments", response_model=AlignmentResponse)
async def create_alignment(
    body: AlignmentRequest,
    request: Request,
    session: GraphSession = Depends(get_session),
):
    """Create an alignment between two ontology entities using OntologyEngine.create_alignment."""
    response = AlignmentResponse(
        source=body.source_uri,
        predicate=body.predicate,
        target=body.target_uri,
    )
    try:
        from ...ontology import OntologyEngine
        
        # Initialize OntologyEngine with session's graph store
        engine_config = {"store": session.graph.store if hasattr(session.graph, "store") else None}
        engine = OntologyEngine(**engine_config)
        
        # Use OntologyEngine.create_alignment
        await asyncio.to_thread(
            engine.create_alignment,
            body.source_uri,
            body.target_uri,
            body.predicate
        )
    except Exception as exc:
        logger.info("OntologyEngine alignment store unavailable; using route-level store: %s", exc)

    alignment_store = _get_alignment_store(request)
    alignment_store[_alignment_key(response.source, response.predicate, response.target)] = response
    return response


@router.get("/alignments/{entity_uri:path}", response_model=List[AlignmentResponse])
async def get_alignments(
    entity_uri: str,
    request: Request,
    session: GraphSession = Depends(get_session),
):
    """Get all alignments for an entity using OntologyEngine.get_alignments."""
    route_alignments = [
        alignment
        for alignment in _get_alignment_store(request).values()
        if alignment.source == entity_uri or alignment.target == entity_uri
    ]
    try:
        from ...ontology import OntologyEngine
        
        # Initialize OntologyEngine with session's graph store
        engine_config = {"store": session.graph.store if hasattr(session.graph, "store") else None}
        engine = OntologyEngine(**engine_config)
        
        # Use OntologyEngine.get_alignments
        alignments = await asyncio.to_thread(engine.get_alignments, entity_uri)
        
        engine_alignments = [
            alignment
            for alignment in (_coerce_alignment(align) for align in alignments)
            if alignment is not None
        ]
        merged = {
            _alignment_key(alignment.source, alignment.predicate, alignment.target): alignment
            for alignment in route_alignments + engine_alignments
        }
        return list(merged.values())
    except Exception as exc:
        logger.info("OntologyEngine alignment lookup unavailable; using route-level store: %s", exc)
        return route_alignments


@router.get("/alignments", response_model=List[AlignmentResponse])
async def list_alignments(
    request: Request,
    ontology_uri: Optional[str] = Query(None),
    session: GraphSession = Depends(get_session),
):
    """List all alignments, optionally filtered by ontology URI using OntologyEngine.list_alignments."""
    route_alignments = list(_get_alignment_store(request).values())
    if ontology_uri:
        route_alignments = [
            alignment for alignment in route_alignments
            if ontology_uri in alignment.source or ontology_uri in alignment.target
        ]
    try:
        from ...ontology import OntologyEngine
        
        # Initialize OntologyEngine with session's graph store
        engine_config = {"store": session.graph.store if hasattr(session.graph, "store") else None}
        engine = OntologyEngine(**engine_config)
        
        # Use OntologyEngine.list_alignments
        alignments = await asyncio.to_thread(engine.list_alignments, ontology_uri=ontology_uri)
        
        engine_alignments = [
            alignment
            for alignment in (_coerce_alignment(align) for align in alignments)
            if alignment is not None
        ]
        merged = {
            _alignment_key(alignment.source, alignment.predicate, alignment.target): alignment
            for alignment in route_alignments + engine_alignments
        }
        return list(merged.values())
    except Exception as exc:
        logger.info("OntologyEngine alignment listing unavailable; using route-level store: %s", exc)
        return route_alignments
