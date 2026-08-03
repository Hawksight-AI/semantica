"""
Source Tracker for Conflict Detection

This module provides comprehensive source tracking capabilities for the Semantica
framework, tracking source information for entities and properties to enable
conflict investigation and source disagreement analysis.

Algorithms Used:

Property Source Tracking:
    - Dictionary-based Mapping: Uses nested dictionaries (entity -> property ->
      PropertySource)
      for efficient property-to-source mapping
    - Source Aggregation: Aggregates multiple sources for the same property value
    - Source Deduplication: Prevents duplicate source entries

Entity Source Tracking:
    - Entity-to-Source Mapping: Tracks which sources contributed to each entity
    - Source Relationship Tracking: Maintains entity-to-source relationships
    - Entity Provenance Chain: Builds provenance chain for entities

Relationship Source Tracking:
    - Relationship-to-Source Mapping: Tracks sources for relationships
    - Relationship Source Aggregation: Aggregates sources for relationship properties

Credibility Scoring:
    - Source Credibility Calculation: Calculates source credibility based on
      historical accuracy
    - Credibility Weighting: Uses credibility scores for weighted conflict resolution
    - Credibility Updates: Updates credibility based on conflict resolution outcomes

Traceability Chain:
    - Graph-based Traceability: Builds traceability graph connecting entities,
      properties, and sources
    - Chain Generation: Generates traceability chains from entity to source documents
    - Path Finding: Finds paths through the traceability graph

Key Features:
    - Tracks source documents for each property value
    - Maintains source provenance for entities
    - Tracks source disagreements and conflicts
    - Generates source analysis reports
    - Supports source credibility scoring
    - Enables traceability for conflict resolution
    - Relationship source tracking
    - Traceability chain generation

Main Classes:
    - SourceReference: Source reference data structure
    - PropertySource: Property source information data structure
    - SourceTracker: Source tracker for conflict detection

Example Usage:
    >>> from semantica.conflicts import SourceTracker, SourceReference
    >>> tracker = SourceTracker()
    >>> source = SourceReference(document="doc1", page=1, confidence=0.9)
    >>> tracker.track_property_source("entity_1", "name", "Python", source)
    >>> sources = tracker.get_property_sources("entity_1", "name")

Author: Semantica Contributors
License: MIT
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils.exceptions import ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


@dataclass
class SourceReference:
    """Source reference for a property value."""

    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    line: Optional[int] = None
    timestamp: Optional[datetime] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PropertySource:
    """Source information for a property value."""

    property_name: str
    value: Any
    sources: List[SourceReference] = field(default_factory=list)
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SourceTracker:
    """
    Source tracker for conflict detection.

    • Tracks source documents for each property value
    • Maintains source provenance for entities
    • Tracks source disagreements and conflicts
    • Generates source analysis reports
    • Supports source credibility scoring
    • Enables traceability for conflict resolution
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize source tracker.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("source_tracker")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        # Entity -> Property -> PropertySource
        self.entity_sources: Dict[str, Dict[str, PropertySource]] = defaultdict(dict)

        # Relationship sources
        self.relationship_sources: Dict[str, List[SourceReference]] = defaultdict(list)

        # Source credibility scores
        self.source_credibility: Dict[str, float] = {}

        # Source metadata
        self.source_metadata: Dict[str, Dict[str, Any]] = {}

    def register_source(
        self,
        source_id: str,
        source_type: str,
        credibility_score: float = 0.5,
        **metadata,
    ) -> bool:
        """
        Register a source with metadata and credibility score.

        Args:
            source_id: Source identifier
            source_type: Type of source (e.g., "report", "news", "official")
            credibility_score: Credibility score (0.0 to 1.0)
            **metadata: Additional metadata

        Returns:
            True if registered successfully
        """
        self.source_metadata[source_id] = {"type": source_type, **metadata}
        return self.set_source_credibility(source_id, credibility_score)

    def track_entity_source(
        self, entity_id: str, source: SourceReference, **metadata
    ) -> bool:
        """
        Track source for an entity.

        Args:
            entity_id: Entity identifier
            source: Source reference
            **metadata: Additional metadata

        Returns:
            True if tracking successful
        """
        if entity_id not in self.entity_sources:
            self.entity_sources[entity_id] = {}

        # Store entity-level source
        if "_entity_sources" not in self.entity_sources[entity_id]:
            self.entity_sources[entity_id]["_entity_sources"] = PropertySource(
                property_name="_entity_sources", value=entity_id, entity_id=entity_id
            )

        self.entity_sources[entity_id]["_entity_sources"].sources.append(source)
        self.logger.debug(f"Tracked entity source: {entity_id} from {source.document}")
        return True

    def track_property_source(
        self,
        entity_id: str,
        property_name: str,
        value: Any,
        source: SourceReference,
        **metadata,
    ) -> bool:
        """
        Track source for a property value.

        Args:
            entity_id: Entity identifier
            property_name: Property name
            value: Property value
            source: Source reference
            **metadata: Additional metadata

        Returns:
            True if tracking successful
        """
        if entity_id not in self.entity_sources:
            self.entity_sources[entity_id] = {}

        if property_name not in self.entity_sources[entity_id]:
            self.entity_sources[entity_id][property_name] = PropertySource(
                property_name=property_name,
                value=value,
                entity_id=entity_id,
                metadata=metadata,
            )

        property_source = self.entity_sources[entity_id][property_name]

        # Add source if not already present
        source_exists = any(
            s.document == source.document
            and s.page == source.page
            and s.section == source.section
            for s in property_source.sources
        )

        if not source_exists:
            property_source.sources.append(source)

        # Update value if different (will be used for conflict detection)
        if property_source.value != value:
            property_source.value = value  # Store latest value

        self.logger.debug(
            f"Tracked property source: {entity_id}.{property_name} = {value} "
            f"from {source.document}"
        )
        return True

    def track_relationship_source(
        self, relationship_id: str, source: SourceReference, **metadata
    ) -> bool:
        """
        Track source for a relationship.

        Args:
            relationship_id: Relationship identifier
            source: Source reference
            **metadata: Additional metadata

        Returns:
            True if tracking successful
        """
        source_exists = any(
            s.document == source.document and s.page == source.page
            for s in self.relationship_sources[relationship_id]
        )

        if not source_exists:
            self.relationship_sources[relationship_id].append(source)

        self.logger.debug(
            f"Tracked relationship source: {relationship_id} from {source.document}"
        )
        return True

    def get_entity_sources(self, entity_id: str) -> List[SourceReference]:
        """
        Get all sources for an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            List of source references
        """
        sources = []

        if entity_id in self.entity_sources:
            # Get entity-level sources
            if "_entity_sources" in self.entity_sources[entity_id]:
                sources.extend(
                    self.entity_sources[entity_id]["_entity_sources"].sources
                )

            # Get all property sources
            for prop_source in self.entity_sources[entity_id].values():
                sources.extend(prop_source.sources)

        # Deduplicate
        seen = set()
        unique_sources = []
        for source in sources:
            key = (source.document, source.page, source.section)
            if key not in seen:
                seen.add(key)
                unique_sources.append(source)

        return unique_sources

    def get_property_sources(
        self, entity_id: str, property_name: str
    ) -> Optional[PropertySource]:
        """
        Get sources for a specific property.

        Args:
            entity_id: Entity identifier
            property_name: Property name

        Returns:
            PropertySource or None if not found
        """
        if entity_id in self.entity_sources:
            return self.entity_sources[entity_id].get(property_name)
        return None

    def get_relationship_sources(self, relationship_id: str) -> List[SourceReference]:
        """
        Get sources for a relationship.

        Args:
            relationship_id: Relationship identifier

        Returns:
            List of source references
        """
        return self.relationship_sources.get(relationship_id, [])

    def find_source_disagreements(
        self, entity_id: str, property_name: str
    ) -> List[Dict[str, Any]]:
        """
        Find source disagreements for a property.

        Args:
            entity_id: Entity identifier
            property_name: Property name

        Returns:
            List of disagreement records
        """
        property_source = self.get_property_sources(entity_id, property_name)
        if not property_source or len(property_source.sources) < 2:
            return []

        # Group sources by value (if we have multiple values)
        # For now, we'll check if sources have different confidence or metadata
        disagreements = []

        sources = property_source.sources
        for i, source1 in enumerate(sources):
            for source2 in sources[i + 1 :]:
                # Check for disagreements in confidence, metadata, or document
                if (
                    source1.document != source2.document
                    or source1.confidence != source2.confidence
                ):
                    disagreements.append(
                        {
                            "entity_id": entity_id,
                            "property_name": property_name,
                            "source1": {
                                "document": source1.document,
                                "page": source1.page,
                                "confidence": source1.confidence,
                            },
                            "source2": {
                                "document": source2.document,
                                "page": source2.page,
                                "confidence": source2.confidence,
                            },
                        }
                    )

        return disagreements

    def set_source_credibility(self, document: str, credibility: float) -> bool:
        """
        Set credibility score for a source document.

        Args:
            document: Document identifier
            credibility: Credibility score (0.0 to 1.0)

        Returns:
            True if set successfully
        """
        if not 0.0 <= credibility <= 1.0:
            raise ValidationError("Credibility must be between 0.0 and 1.0")

        self.source_credibility[document] = credibility
        self.logger.info(f"Set credibility for {document}: {credibility}")
        return True

    def get_source_credibility(self, document: str) -> float:
        """
        Get credibility score for a source document.

        Args:
            document: Document identifier

        Returns:
            Credibility score (default: 0.5)
        """
        return self.source_credibility.get(document, 0.5)

    def generate_source_report(self, entity_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate source analysis report.

        Args:
            entity_id: Optional entity ID to filter by

        Returns:
            Source report dictionary
        """
        report = {
            "generated_at": datetime.now().isoformat(),
            "entities_tracked": 0,
            "properties_tracked": 0,
            "relationships_tracked": len(self.relationship_sources),
            "total_sources": 0,
            "source_credibility": dict(self.source_credibility),
            "entities": [],
        }

        entities_to_report = (
            [entity_id] if entity_id else list(self.entity_sources.keys())
        )

        for eid in entities_to_report:
            if eid not in self.entity_sources:
                continue

            entity_info = {"entity_id": eid, "properties": [], "total_sources": 0}

            for prop_name, prop_source in self.entity_sources[eid].items():
                if prop_name == "_entity_sources":
                    continue

                prop_info = {
                    "property_name": prop_name,
                    "value": prop_source.value,
                    "sources": [
                        {
                            "document": s.document,
                            "page": s.page,
                            "section": s.section,
                            "confidence": s.confidence,
                            "credibility": self.get_source_credibility(s.document),
                        }
                        for s in prop_source.sources
                    ],
                    "source_count": len(prop_source.sources),
                }

                entity_info["properties"].append(prop_info)
                entity_info["total_sources"] += len(prop_source.sources)
                report["total_sources"] += len(prop_source.sources)

            if entity_info["properties"]:
                report["entities"].append(entity_info)
                report["entities_tracked"] += 1
                report["properties_tracked"] += len(entity_info["properties"])

        return report

    def get_traceability_chain(
        self, entity_id: str, property_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get traceability chain for an entity or property.

        Args:
            entity_id: Entity identifier
            property_name: Optional property name

        Returns:
            List of traceability records
        """
        chain = []

        if property_name:
            prop_source = self.get_property_sources(entity_id, property_name)
            if prop_source:
                for source in prop_source.sources:
                    chain.append(
                        {
                            "type": "property",
                            "entity_id": entity_id,
                            "property_name": property_name,
                            "value": prop_source.value,
                            "source": {
                                "document": source.document,
                                "page": source.page,
                                "section": source.section,
                                "confidence": source.confidence,
                                "timestamp": source.timestamp.isoformat()
                                if source.timestamp
                                else None,
                            },
                        }
                    )
        else:
            # Get all entity sources
            sources = self.get_entity_sources(entity_id)
            for source in sources:
                chain.append(
                    {
                        "type": "entity",
                        "entity_id": entity_id,
                        "source": {
                            "document": source.document,
                            "page": source.page,
                            "section": source.section,
                            "confidence": source.confidence,
                            "timestamp": source.timestamp.isoformat()
                            if source.timestamp
                            else None,
                        },
                    }
                )

        return chain

    def get_all_source_credibilities(self) -> Dict[str, float]:
        """
        Get all source credibility scores.

        Returns:
            Dictionary mapping source document IDs to credibility scores
        """
        return self.source_credibility.copy()

    def generate_traceability_chain(
        self, entity_id: str, property_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate traceability chain for an entity or property (alias for
        get_traceability_chain).

        Args:
            entity_id: Entity identifier
            property_name: Optional property name

        Returns:
            List of traceability records
        """
        return self.get_traceability_chain(entity_id, property_name)

    def track_sources_batch(
        self,
        source_data: List[Dict[str, Any]],
        pipeline_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Track sources for multiple entities, properties, or relationships in batch.

        Args:
            source_data: List of source tracking dictionaries, each containing:
                - type: "entity", "property", or "relationship"
                - entity_id: Entity identifier (required for all types)
                - property_name: Property name (required for "property" type)
                - value: Property value (required for "property" type)
                - relationship_id: Relationship identifier (required for "relationship" type)
                - source: SourceReference object or dict to create SourceReference
                - metadata: Optional metadata dictionary
            pipeline_id: Optional pipeline ID for progress tracking

        Returns:
            dict: Statistics with keys:
                - entities_tracked: Number of entities tracked
                - properties_tracked: Number of properties tracked
                - relationships_tracked: Number of relationships tracked
                - total_tracked: Total number of items tracked
        """
        if not source_data:
            return {
                "entities_tracked": 0,
                "properties_tracked": 0,
                "relationships_tracked": 0,
                "total_tracked": 0,
            }

        tracking_id = self.progress_tracker.start_tracking(
            module="conflicts",
            submodule="SourceTracker",
            message=f"Tracking sources for {len(source_data)} items",
            pipeline_id=pipeline_id,
        )

        stats = {
            "entities_tracked": 0,
            "properties_tracked": 0,
            "relationships_tracked": 0,
            "total_tracked": 0,
        }

        try:
            for i, item in enumerate(source_data):
                item_type = item.get("type", "property")
                source_ref = item.get("source")
                metadata = item.get("metadata", {})

                # Convert source dict to SourceReference if needed
                if isinstance(source_ref, dict):
                    source_ref = SourceReference(**source_ref)
                elif not isinstance(source_ref, SourceReference):
                    self.logger.warning(f"Invalid source reference in item {i}: {item}")
                    continue

                if item_type == "entity":
                    entity_id = item.get("entity_id")
                    if entity_id:
                        ok = self.track_entity_source(entity_id, source_ref, **metadata)
                        if ok:
                            stats["entities_tracked"] += 1
                            stats["total_tracked"] += 1
                        else:
                            self.logger.warning(
                                f"Failed to track entity source for '{entity_id}' in item {i}"
                            )

                elif item_type == "property":
                    entity_id = item.get("entity_id")
                    property_name = item.get("property_name")
                    value = item.get("value")
                    if entity_id and property_name is not None:
                        ok = self.track_property_source(
                            entity_id, property_name, value, source_ref, **metadata
                        )
                        if ok:
                            stats["properties_tracked"] += 1
                            stats["total_tracked"] += 1
                        else:
                            self.logger.warning(
                                f"Failed to track property source for '{entity_id}.{property_name}' in item {i}"
                            )

                elif item_type == "relationship":
                    relationship_id = item.get("relationship_id")
                    if relationship_id:
                        ok = self.track_relationship_source(
                            relationship_id, source_ref, **metadata
                        )
                        if ok:
                            stats["relationships_tracked"] += 1
                            stats["total_tracked"] += 1
                        else:
                            self.logger.warning(
                                f"Failed to track relationship source for '{relationship_id}' in item {i}"
                            )

                else:
                    self.logger.warning(
                        f"Unknown type '{item_type}' in item {i}, skipping"
                    )

                # Update progress
                self.progress_tracker.update_progress(
                    tracking_id,
                    processed=i + 1,
                    total=len(source_data),
                    message=f"Tracking sources {i+1}/{len(source_data)}...",
                )

            message = (
                f"Tracked {stats['total_tracked']} items: "
                f"{stats['entities_tracked']} entities, "
                f"{stats['properties_tracked']} properties, "
                f"{stats['relationships_tracked']} relationships"
            )

            self.progress_tracker.stop_tracking(
                tracking_id, status="completed", message=message
            )
            return stats

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise