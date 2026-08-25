"""
W3C PROV-O Compliant Provenance Schemas

This module provides dataclasses for provenance tracking that comply with
W3C PROV-O (Provenance Ontology) standards while consolidating functionality
from existing Semantica provenance trackers.

Consolidates:
    - kg.ProvenanceTracker: Entity/relationship tracking with temporal info
    - split.ProvenanceInfo: Chunk tracking with parent-child relationships
    - conflicts.SourceReference: Source tracking with credibility scores

W3C PROV-O Mapping:
    - ProvenanceEntry.entity_id → prov:Entity
    - ProvenanceEntry.activity_id → prov:Activity
    - ProvenanceEntry.agent_id / agent_type → prov:Agent (Person|SoftwareAgent|Organization)
    - ProvenanceEntry.role → prov:hadRole (via prov:qualifiedAssociation)
    - ProvenanceEntry.parent_entity_id → prov:wasDerivedFrom (legacy combined field)
    - ProvenanceEntry.derived_from_id → prov:wasDerivedFrom (true cross-source derivation)
    - ProvenanceEntry.previous_version_id → prior version of the same fact (correction/versioning)
    - ProvenanceEntry.used_entities → prov:used
    - ProvenanceEntry.timestamp → prov:generatedAtTime
    - ProvenanceEntry.invalidated* → prov:Invalidation (tombstone, not a hard delete)

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..utils.helpers import utc_now_iso


@dataclass
class ProvenanceEntry:
    """
    W3C PROV-O compliant provenance entry.
    
    This unified schema consolidates provenance tracking from:
    - kg.ProvenanceTracker (entity/relationship tracking)
    - split.ProvenanceInfo (chunk tracking)
    - conflicts.SourceReference (source tracking)
    
    Attributes:
        entity_id: Unique identifier for the entity (prov:Entity)
        entity_type: Type of entity (entity, chunk, relationship, property, etc.)
        activity_id: Activity that generated this entity (prov:Activity)
        agent_id: Agent responsible for the activity (prov:Agent)
        source_document: Source document identifier (DOI, file path, URL)
        source_location: Location within source (page, figure, char range)
        source_quote: Direct quote from source (for audit trail)
        timestamp: When this provenance entry was created (prov:generatedAtTime)
        first_seen: When entity was first tracked (from kg.ProvenanceTracker)
        last_updated: When entity was last updated (from kg.ProvenanceTracker)
        confidence: Confidence score for this provenance entry (0.0-1.0)
        checksum: SHA-256 checksum for integrity verification
        parent_entity_id: Parent entity ID (prov:wasDerivedFrom)
        used_entities: List of entities used to create this entity (prov:used)
        start_index: Start character index (from split.ProvenanceInfo)
        end_index: End character index (from split.ProvenanceInfo)
        credibility: Source credibility score (from conflicts.SourceTracker)
        metadata: Additional metadata dictionary
        version: Provenance schema version
    
    Example:
        >>> entry = ProvenanceEntry(
        ...     entity_id="entity_123",
        ...     entity_type="named_entity",
        ...     activity_id="ner_extraction",
        ...     source_document="DOI:10.1371/journal.pone.0023601",
        ...     source_location="Figure 2",
        ...     source_quote="Total fish biomass increased by 463%",
        ...     confidence=0.92
        ... )
    """
    
    # W3C PROV-O core entities
    entity_id: str
    entity_type: str
    activity_id: str
    agent_id: str = "semantica"

    # Accountability-scoped agent typing (issue #825, Part A item 3)
    agent_type: str = "software_agent"  # "person" | "software_agent" | "organization"
    is_automated: bool = True
    role: Optional[str] = None  # prov:hadRole, e.g. "generator", "approver", "reviewer"

    # Audit-grade source tracking
    source_document: str = ""
    source_location: Optional[str] = None
    source_quote: Optional[str] = None

    # Temporal tracking (from kg.ProvenanceTracker)
    timestamp: str = field(default_factory=lambda: utc_now_iso())
    first_seen: Optional[str] = None
    last_updated: Optional[str] = None

    # Quality metrics
    confidence: float = 1.0
    checksum: Optional[str] = None

    # Hash-chain linkage (issue #825, Part A item 2): previous_checksum links
    # this entry to the prior entry in global insertion order (sequence_id),
    # so wholesale row deletion breaks the chain and becomes detectable via
    # ProvenanceManager.verify_chain().
    sequence_id: Optional[int] = None
    previous_checksum: Optional[str] = None

    # Chain of custody (W3C PROV-O) — kept for backward compatibility.
    parent_entity_id: Optional[str] = None
    used_entities: List[str] = field(default_factory=list)

    # Versioning vs. derivation (issue #825, Part A item 4): previous_version_id
    # is "this corrects/replaces a prior version of the same fact"
    # (prov:specializationOf-flavored); derived_from_id is "this fact was
    # derived from a different source entity" (prov:wasDerivedFrom). Both are
    # additive alongside parent_entity_id, which remains the legacy combined
    # field for existing readers.
    previous_version_id: Optional[str] = None
    derived_from_id: Optional[str] = None

    # Typed Activity (issue #825, Part B Tier 1): prov:startedAtTime/endedAtTime
    # for the activity that generated this entry.
    activity_started_at_time: Optional[str] = None
    activity_ended_at_time: Optional[str] = None

    # prov:actedOnBehalfOf / prov:wasInformedBy (issue #825, Part B Tier 2)
    acted_on_behalf_of: Optional[str] = None
    informed_by_activities: List[str] = field(default_factory=list)

    # Bitemporal fields merged from the deprecated kg.ProvenanceTracker
    # (issue #825, Part B Tier 3) — in the deprecated tracker these were
    # always caller-supplied optional metadata keys, never auto-computed;
    # same contract here. valid_from/valid_until express the fact's own
    # asserted validity window (domain/business time), independent of
    # sequence_id/timestamp which track when the system recorded it.
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    revision_type: Optional[str] = None
    supersedes: Optional[str] = None

    # prov:Collection / prov:Bundle membership (issue #825, Part B Tier 3):
    # partitions provenance by source/dataset/ingestion-run.
    bundle_id: Optional[str] = None

    # Invalidation / tombstone tracking (issue #825, Part A item 1): set via
    # ProvenanceManager.invalidate() instead of deleting the row, so an audit
    # can prove a fact existed, was reviewed, and was retracted/corrected.
    invalidated: bool = False
    invalidated_at_time: Optional[str] = None
    invalidated_by: Optional[str] = None
    invalidation_reason: Optional[str] = None

    # Chunk-specific fields (from split.ProvenanceInfo)
    start_index: Optional[int] = None
    end_index: Optional[int] = None

    # Source credibility (from conflicts.SourceTracker)
    credibility: Optional[float] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert provenance entry to dictionary.
        
        Returns:
            Dictionary representation of provenance entry
        """
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "activity_id": self.activity_id,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "is_automated": self.is_automated,
            "role": self.role,
            "source_document": self.source_document,
            "source_location": self.source_location,
            "source_quote": self.source_quote,
            "timestamp": self.timestamp,
            "first_seen": self.first_seen,
            "last_updated": self.last_updated,
            "confidence": self.confidence,
            "checksum": self.checksum,
            "sequence_id": self.sequence_id,
            "previous_checksum": self.previous_checksum,
            "parent_entity_id": self.parent_entity_id,
            "used_entities": self.used_entities,
            "previous_version_id": self.previous_version_id,
            "derived_from_id": self.derived_from_id,
            "activity_started_at_time": self.activity_started_at_time,
            "activity_ended_at_time": self.activity_ended_at_time,
            "acted_on_behalf_of": self.acted_on_behalf_of,
            "informed_by_activities": self.informed_by_activities,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "revision_type": self.revision_type,
            "supersedes": self.supersedes,
            "bundle_id": self.bundle_id,
            "invalidated": self.invalidated,
            "invalidated_at_time": self.invalidated_at_time,
            "invalidated_by": self.invalidated_by,
            "invalidation_reason": self.invalidation_reason,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "credibility": self.credibility,
            "metadata": self.metadata,
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProvenanceEntry":
        """
        Create provenance entry from dictionary.
        
        Args:
            data: Dictionary containing provenance data
            
        Returns:
            ProvenanceEntry instance
        """
        return cls(**data)


@dataclass
class SourceReference:
    """
    Source reference for provenance tracking.
    
    Compatible with conflicts.SourceReference for backward compatibility.
    
    Attributes:
        document: Document identifier (DOI, file path, URL)
        page: Page number within document
        section: Section identifier within document
        line: Line number within document
        timestamp: When this source was accessed/created
        confidence: Confidence score for this source (0.0-1.0)
        metadata: Additional metadata dictionary
    
    Example:
        >>> source = SourceReference(
        ...     document="DOI:10.1038/s41586-021-03371-z",
        ...     page=4,
        ...     section="Table S4",
        ...     confidence=0.92
        ... )
    """
    
    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    line: Optional[int] = None
    timestamp: Optional[datetime] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert source reference to dictionary.
        
        Returns:
            Dictionary representation of source reference
        """
        return {
            "document": self.document,
            "page": self.page,
            "section": self.section,
            "line": self.line,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceReference":
        """
        Create source reference from dictionary.
        
        Args:
            data: Dictionary containing source reference data
            
        Returns:
            SourceReference instance
        """
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class PropertySource:
    """
    Property source information for conflict tracking.
    
    Compatible with conflicts.PropertySource for backward compatibility.
    
    Attributes:
        property_name: Name of the property
        value: Value of the property
        sources: List of source references
        entity_id: Entity this property belongs to
        metadata: Additional metadata dictionary
    
    Example:
        >>> prop_source = PropertySource(
        ...     property_name="biomass_increase",
        ...     value="463%",
        ...     sources=[source_ref],
        ...     entity_id="cabo_pulmo_mpa"
        ... )
    """
    
    property_name: str
    value: Any
    sources: List[SourceReference] = field(default_factory=list)
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert property source to dictionary.
        
        Returns:
            Dictionary representation of property source
        """
        return {
            "property_name": self.property_name,
            "value": self.value,
            "sources": [s.to_dict() for s in self.sources],
            "entity_id": self.entity_id,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PropertySource":
        """
        Create property source from dictionary.
        
        Args:
            data: Dictionary containing property source data
            
        Returns:
            PropertySource instance
        """
        if "sources" in data:
            data["sources"] = [
                SourceReference.from_dict(s) if isinstance(s, dict) else s
                for s in data["sources"]
            ]
        return cls(**data)


@dataclass
class AgentRecord:
    """
    Minimum-viable typed W3C PROV-O agent (prov:Agent).

    Narrower than the full PROV-O Person/SoftwareAgent/Organization taxonomy —
    just enough to answer "was a human accountable here" for high-stakes
    provenance review. Pass an AgentRecord to ProvenanceManager.track_entity()
    (etc.) via the `agent=` kwarg to set agent_id/agent_type/is_automated
    together.

    Attributes:
        id: Agent identifier (prov:Agent)
        agent_type: One of "person", "software_agent", "organization"
        is_automated: Whether this agent acted without direct human review
        name: Optional human-readable name
        metadata: Additional metadata dictionary

    Example:
        >>> agent = AgentRecord(id="reviewer_jane", agent_type="person", is_automated=False)
        >>> prov_mgr.track_entity("entity_1", source="doc_1", agent=agent, role="approver")
    """

    id: str
    agent_type: str = "software_agent"
    is_automated: bool = True
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert agent record to dictionary."""
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "is_automated": self.is_automated,
            "name": self.name,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentRecord":
        """Create agent record from dictionary."""
        return cls(**data)


@dataclass
class ActivityRecord:
    """
    Minimum-viable typed W3C PROV-O activity (prov:Activity).

    Issue #825, Part B Tier 1 — promotes activity_id from a bare string to
    a typed object carrying start/end timing, mirroring AgentRecord. Pass an
    ActivityRecord to ProvenanceManager.track_entity() (etc.) via the
    `activity=` kwarg to set activity_id/activity_started_at_time/
    activity_ended_at_time together.

    Attributes:
        id: Activity identifier (prov:Activity)
        activity_type: Free-form activity classification (e.g. "process", "extraction")
        started_at_time: prov:startedAtTime, ISO datetime string
        ended_at_time: prov:endedAtTime, ISO datetime string
        metadata: Additional metadata dictionary

    Example:
        >>> activity = ActivityRecord(
        ...     id="bureau_parsing_run_42",
        ...     started_at_time="2026-01-01T00:00:00",
        ...     ended_at_time="2026-01-01T00:00:03",
        ... )
        >>> prov_mgr.track_entity("entity_1", source="doc_1", activity=activity)
    """

    id: str
    activity_type: str = "process"
    started_at_time: Optional[str] = None
    ended_at_time: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert activity record to dictionary."""
        return {
            "id": self.id,
            "activity_type": self.activity_type,
            "started_at_time": self.started_at_time,
            "ended_at_time": self.ended_at_time,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActivityRecord":
        """Create activity record from dictionary."""
        return cls(**data)


@dataclass
class Invalidation:
    """
    W3C PROV-O invalidation record (prov:Invalidation).

    Represents the tombstone for a retracted/corrected provenance entry:
    "this was deleted/corrected, by whom, when, why" — recorded in place of
    a hard delete so the fact that an entity existed remains provable.

    Attributes:
        entity_id: The entity that was invalidated (prov:Entity)
        invalidated_at_time: When invalidation occurred (prov:invalidatedAtTime)
        invalidated_by: Agent responsible for the invalidation (prov:Agent)
        reason: Optional human-readable reason
        metadata: Additional metadata dictionary

    Example:
        >>> Invalidation(
        ...     entity_id="entity_123",
        ...     invalidated_at_time="2026-01-01T00:00:00",
        ...     invalidated_by="reviewer_jane",
        ...     reason="Source document retracted",
        ... )
    """

    entity_id: str
    invalidated_at_time: str
    invalidated_by: str
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert invalidation record to dictionary."""
        return {
            "entity_id": self.entity_id,
            "invalidated_at_time": self.invalidated_at_time,
            "invalidated_by": self.invalidated_by,
            "reason": self.reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Invalidation":
        """Create invalidation record from dictionary."""
        return cls(**data)
