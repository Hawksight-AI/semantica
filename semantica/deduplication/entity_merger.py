"""
Entity Merger Module

This module provides entity merging capabilities for the Semantica framework,
performing semantic deduplication to merge semantically similar entities and
maintain knowledge graph cleanliness.

Algorithms Used:
    - Strategy Pattern: Multiple merge strategies (keep_first, keep_last, keep_most_complete, etc.)
    - Conflict Resolution: Voting, credibility-weighted, temporal, confidence-based resolution
    - Property Merging: Rule-based property combination with custom rules and priorities
    - Relationship Preservation: Union of relationship sets during merges
    - Provenance Tracking: Metadata preservation during merges with source tracking
    - Merge Quality Validation: Validation of merged entities for completeness and consistency

Key Features:
    - Merge duplicate entities using configurable strategies with group-level progress tracking
    - Preserve provenance information during merges (tracks merged entity sources)
    - Incremental merging of new entities with existing ones
    - Conflict resolution for property and relationship merging
    - Merge history tracking and quality validation
    - Automatic duplicate detection and grouping before merging
    - Support for custom merge strategies and conflict resolution functions

Main Classes:
    - EntityMerger: Main entity merging engine
    - MergeOperation: Entity merge operation representation with metadata

Example Usage:
    >>> from semantica.deduplication import EntityMerger, MergeStrategy
    >>> merger = EntityMerger(preserve_provenance=True)
    >>> operations = merger.merge_duplicates(
    ...     entities,
    ...     strategy="keep_most_complete"
    ... )
    >>> history = merger.get_merge_history()
    >>> 
    >>> # Access merged entities
    >>> merged = [op.merged_entity for op in operations]

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from ..utils.entity_ids import get_entity_id
from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .duplicate_detector import DuplicateDetector, DuplicateGroup
from .merge_strategy import MergeResult, MergeStrategy, MergeStrategyManager


@dataclass
class MergeOperation:
    """Entity merge operation representation."""

    source_entities: List[Dict[str, Any]]
    merged_entity: Dict[str, Any]
    merge_result: MergeResult
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = None


class EntityMerger:
    """
    Entity merging engine for knowledge graphs.

    This class provides comprehensive entity merging capabilities, detecting duplicates,
    applying merge strategies, resolving conflicts, and preserving provenance information.

    Features:
        - Automatic duplicate detection and grouping
        - Configurable merge strategies (keep_first, keep_most_complete, etc.)
        - Property and relationship merging with conflict resolution
        - Provenance preservation (tracks merged entities)
        - Incremental merging for new entities
        - Merge history tracking and quality validation

    Example Usage:
        >>> merger = EntityMerger(preserve_provenance=True)
        >>> operations = merger.merge_duplicates(entities, strategy="keep_most_complete")
        >>> history = merger.get_merge_history()
    """

    def __init__(
        self,
        preserve_provenance: bool = True,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize entity merger.

        Sets up the merger with duplicate detector and merge strategy manager,
        configured according to the provided options.

        Args:
            preserve_provenance: Whether to preserve provenance information in merged entities
                                (default: True). When True, merged entities will contain
                                metadata about which entities were merged.
            config: Configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration options:
                - detector: Configuration for DuplicateDetector
                - strategy: Configuration for MergeStrategyManager
        """
        self.logger = get_logger("entity_merger")

        # Merge configuration
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize components
        detector_config = self.config.get("detector", {})
        strategy_config = self.config.get("strategy", {})

        self.duplicate_detector = DuplicateDetector(**detector_config)
        self.merge_strategy_manager = MergeStrategyManager(**strategy_config)

        # Merge history tracking
        self.merge_history: List[MergeOperation] = []
        self.preserve_provenance = preserve_provenance

        # Initialize progress tracker and ensure it's enabled
        self.progress_tracker = get_progress_tracker()
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug(
            f"Entity merger initialized (preserve_provenance: {preserve_provenance})"
        )

    def merge_duplicates(
        self,
        entities: List[Dict[str, Any]],
        strategy: Optional[Union[MergeStrategy, str]] = None,
        **options,
    ) -> List[MergeOperation]:
        """
        Merge duplicate entities from a list.

        This method detects duplicate groups, merges each group using the specified
        strategy, and returns a list of merge operations. Provenance information
        is preserved if enabled.

        Process:
            1. Detect duplicate groups using similarity thresholds
            2. For each group with 2+ entities:
               - Apply merge strategy to combine entities
               - Resolve property and relationship conflicts
               - Add provenance information (if enabled)
            3. Track merge operations in history

        Args:
            entities: List of entity dictionaries to merge. Entities should have
                     at least "id" or "name" fields.
            strategy: Merge strategy to use (default: strategy manager's default).
                     Options: "keep_first", "keep_last", "keep_most_complete",
                     "keep_highest_confidence", "merge_all" or MergeStrategy Enum.
            **options: Additional merge options passed to duplicate detector and
                      merge strategy manager:
                - threshold: Similarity threshold for duplicate detection
                - preserve_relationships: Whether to preserve all relationships

        Returns:
            List of MergeOperation objects, each containing:
                - source_entities: Original entities that were merged
                - merged_entity: Resulting merged entity
                - merge_result: Detailed merge result with conflicts
                - metadata: Group confidence and similarity scores

        Example:
            >>> entities = [
            ...     {"id": "1", "name": "Apple Inc.", "type": "Company"},
            ...     {"id": "2", "name": "Apple", "type": "Company"}
            ... ]
            >>> operations = merger.merge_duplicates(
            ...     entities,
            ...     strategy="keep_most_complete"
            ... )
            >>> merged = operations[0].merged_entity
        """
        # Track entity merging
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="deduplication",
            submodule="EntityMerger",
            message=f"Merging duplicates from {len(entities)} entities",
        )

        try:
            self.logger.info(f"Merging duplicates from {len(entities)} entities")

            # Initial progress update
            self.progress_tracker.update_tracking(
                tracking_id, 
                status="running",
                message=f"Starting merge process for {len(entities)} entities..."
            )
            
            self.progress_tracker.update_tracking(
                tracking_id, message="Detecting duplicate groups..."
            )
            # Detect duplicate groups using similarity
            duplicate_groups = self.duplicate_detector.detect_duplicate_groups(
                entities, **options
            )

            self.logger.debug(f"Found {len(duplicate_groups)} duplicate group(s)")

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Merging {len(duplicate_groups)} groups..."
            )
            merge_operations = []
            
            # Filter groups with 2+ entities (actual duplicates)
            mergeable_groups = [g for g in duplicate_groups if len(g.entities) >= 2]
            total_groups = len(mergeable_groups)
            # Update more frequently: every item if small, or every 1% if large
            if total_groups <= 10:
                update_interval = 1  # Update every item for small datasets
            else:
                update_interval = max(1, min(5, total_groups // 100))
            
            # Initial progress update - ALWAYS show this
            remaining = total_groups
            self.progress_tracker.update_progress(
                tracking_id,
                processed=0,
                total=total_groups,
                message=f"Starting merge operations... 0/{total_groups} (remaining: {remaining})"
            )

            # Merge each duplicate group
            for i, group in enumerate(mergeable_groups):
                self.logger.debug(
                    f"Merging group of {len(group.entities)} entities "
                    f"(confidence: {group.confidence:.2f})"
                )

                # Apply merge strategy to combine entities
                merge_result = self.merge_strategy_manager.merge_entities(
                    group.entities, strategy=strategy, **options
                )

                # Add provenance information if enabled
                if self.preserve_provenance:
                    merge_result.merged_entity = self._add_provenance(
                        merge_result.merged_entity, group.entities
                    )

                # Create merge operation record
                operation = MergeOperation(
                    source_entities=group.entities,
                    merged_entity=merge_result.merged_entity,
                    merge_result=merge_result,
                    metadata={
                        "group_confidence": group.confidence,
                        "similarity_scores": group.similarity_scores,
                        "strategy": merge_result.metadata.get("strategy", "default"),
                    },
                )

                merge_operations.append(operation)
                self.merge_history.append(operation)
                
                remaining = total_groups - (i + 1)
                # Update progress: always update for small datasets, or at intervals for large ones
                should_update = (
                    (i + 1) % update_interval == 0 or 
                    (i + 1) == total_groups or 
                    i == 0 or
                    total_groups <= 10  # Always update for small datasets
                )
                if should_update:
                    self.progress_tracker.update_progress(
                        tracking_id,
                        processed=i + 1,
                        total=total_groups,
                        message=f"Merging groups... {i + 1}/{total_groups} (remaining: {remaining})"
                    )

            self.logger.info(
                f"Completed merging: {len(merge_operations)} merge operation(s) performed"
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Completed {len(merge_operations)} merge operations",
            )
            return merge_operations

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def merge_entity_group(
        self,
        entities: List[Dict[str, Any]],
        strategy: Optional[Union[MergeStrategy, str]] = None,
        **options,
    ) -> MergeOperation:
        """
        Merge a specific group of entities.

        This method merges a pre-determined group of entities (typically from
        a duplicate group) using the specified merge strategy. Unlike
        merge_duplicates(), this method does not perform duplicate detection.

        Args:
            entities: List of entity dictionaries to merge (must have at least 2)
            strategy: Merge strategy to use (default: strategy manager's default)
            **options: Additional merge options passed to merge strategy manager

        Returns:
            MergeOperation object containing:
                - source_entities: Original entities that were merged
                - merged_entity: Resulting merged entity
                - merge_result: Detailed merge result with conflicts
                - metadata: Merge metadata

        Raises:
            ValidationError: If less than 2 entities provided

        Example:
            >>> entities = [
            ...     {"id": "1", "name": "Apple Inc."},
            ...     {"id": "2", "name": "Apple"}
            ... ]
            >>> operation = merger.merge_entity_group(
            ...     entities,
            ...     strategy="keep_most_complete"
            ... )
            >>> merged = operation.merged_entity
        """
        if len(entities) < 2:
            raise ValidationError(
                f"Need at least 2 entities to merge, got {len(entities)}"
            )

        # Get strategy value safely for logging
        strategy_val = "default"
        if strategy:
            strategy_val = strategy.value if hasattr(strategy, "value") else str(strategy)

        self.logger.debug(
            f"Merging group of {len(entities)} entities "
            f"(strategy: {strategy_val})"
        )

        # Apply merge strategy
        merge_result = self.merge_strategy_manager.merge_entities(
            entities, strategy=strategy, **options
        )

        # Add provenance information if enabled
        if self.preserve_provenance:
            merge_result.merged_entity = self._add_provenance(
                merge_result.merged_entity, entities
            )

        # Create merge operation record
        operation = MergeOperation(
            source_entities=entities,
            merged_entity=merge_result.merged_entity,
            merge_result=merge_result,
            metadata={
                "strategy": merge_result.metadata.get("strategy", "default"),
                "conflicts": len(merge_result.conflicts),
            },
        )

        # Track in history
        self.merge_history.append(operation)

        self.logger.info(
            f"Successfully merged {len(entities)} entities "
            f"({len(merge_result.conflicts)} conflict(s))"
        )

        return operation

    def incremental_merge(
        self,
        new_entities: List[Dict[str, Any]],
        existing_entities: List[Dict[str, Any]],
        **options,
    ) -> List[MergeOperation]:
        """
        Incremental merge of new entities with existing ones.

        This method efficiently merges new entities with an existing set by detecting
        duplicates between them and merging matching pairs. Useful for streaming
        or incremental data processing where new entities are added over time.

        Process:
            1. Detect duplicates between new and existing entities
            2. For each duplicate pair:
               - Merge the two entities
               - Track which entities have been processed
               - Avoid duplicate merges
            3. Return list of merge operations

        Args:
            new_entities: List of new entity dictionaries to merge
            existing_entities: List of existing entity dictionaries to merge with
            **options: Additional merge options:
                - threshold: Similarity threshold for duplicate detection
                - strategy: Merge strategy to use

        Returns:
            List of MergeOperation objects, one for each merged pair.
            Entities that don't have duplicates remain unmerged.

        Example:
            >>> new = [{"id": "3", "name": "Apple Corp"}]
            >>> existing = [{"id": "1", "name": "Apple Inc."}]
            >>> operations = merger.incremental_merge(new, existing)
            >>> # Returns merge operation if Apple Corp and Apple Inc. are duplicates
        """
        self.logger.info(
            f"Incremental merge: {len(new_entities)} new entities vs "
            f"{len(existing_entities)} existing entities"
        )

        # Detect duplicates between new and existing entities
        candidates = self.duplicate_detector.incremental_detect(
            new_entities, existing_entities, **options
        )

        self.logger.debug(f"Found {len(candidates)} duplicate candidate(s)")

        merge_operations = []
        processed_new = set()  # Track processed new entity IDs
        processed_existing = set()  # Track processed existing entity IDs

        # Merge each duplicate pair
        for candidate in candidates:
            new_entity_id = candidate.entity1.get("id") or id(candidate.entity1)
            existing_entity_id = candidate.entity2.get("id") or id(candidate.entity2)

            # Skip if either entity already processed (avoid duplicate merges)
            if (
                new_entity_id in processed_new
                or existing_entity_id in processed_existing
            ):
                self.logger.debug(
                    f"Skipping merge: entity already processed "
                    f"(new: {new_entity_id}, existing: {existing_entity_id})"
                )
                continue

            # Merge the duplicate pair
            operation = self.merge_entity_group(
                [candidate.entity1, candidate.entity2], **options
            )

            merge_operations.append(operation)

            # Mark entities as processed
            processed_new.add(new_entity_id)
            processed_existing.add(existing_entity_id)

        self.logger.info(
            f"Incremental merge completed: {len(merge_operations)} merge operation(s)"
        )

        return merge_operations

    def _add_provenance(
        self, merged_entity: Dict[str, Any], source_entities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Add provenance information to merged entity.

        This method adds metadata about which entities were merged to create
        the merged entity, preserving the history of the merge operation.

        Provenance Structure:
            metadata.provenance:
                - merged_from: List of source entity information (id, name, source)
                - merge_count: Number of entities that were merged

        Args:
            merged_entity: The merged entity dictionary to add provenance to
            source_entities: List of source entities that were merged

        Returns:
            Merged entity dictionary with provenance information added
        """
        # Ensure metadata structure exists
        if "metadata" not in merged_entity:
            merged_entity["metadata"] = {}

        if "provenance" not in merged_entity["metadata"]:
            merged_entity["metadata"]["provenance"] = {}

        provenance = merged_entity["metadata"]["provenance"]

        # Record source entities
        provenance["merged_from"] = [
            {
                "id": get_entity_id(e),
                "name": self._get_entity_value(e, "name"),
                "source": self._get_entity_value(e, "metadata", {}).get("source") if hasattr(e, "metadata") or isinstance(e, dict) else None,
            }
            for e in source_entities
        ]
        provenance["merge_count"] = len(source_entities)

        self.logger.debug(
            f"Added provenance for merge of {len(source_entities)} entity(ies)"
        )

        return merged_entity

    def get_merge_history(self) -> List[MergeOperation]:
        """
        Get merge operation history.

        Returns a list of all merge operations that have been performed by this
        merger instance, in chronological order.

        Returns:
            List of MergeOperation objects representing all merges performed.
            Each operation contains source entities, merged entity, and metadata.

        Example:
            >>> history = merger.get_merge_history()
            >>> print(f"Total merges: {len(history)}")
            >>> for op in history:
            ...     print(f"Merged {len(op.source_entities)} entities")
        """
        return self.merge_history.copy()  # Return copy to prevent external modification

    def validate_merge_quality(self, merge_operation: MergeOperation) -> Dict[str, Any]:
        """
        Validate quality of a merge operation.

        This method checks the quality of a merge operation by validating the
        merged entity and checking for issues like missing required fields or
        unresolved conflicts.

        Args:
            merge_operation: MergeOperation object to validate

        Returns:
            Dictionary containing validation results:
                - valid: Whether merge is valid (bool)
                - issues: List of validation issues found
                - quality_score: Quality score (0.0 to 1.0)

        Example:
            >>> operation = merger.merge_entity_group(entities)
            >>> validation = merger.validate_merge_quality(operation)
            >>> if not validation["valid"]:
            ...     print(f"Issues: {validation['issues']}")
        """
        return self.merge_strategy_manager.validate_merge(merge_operation.merge_result)

    def _get_entity_value(self, entity: Any, key: str, default: Any = None) -> Any:
        """Get value from entity dictionary or object safely."""
        if hasattr(entity, "__dict__"):
            # For Entity objects, map 'name' to 'text' and 'type' to 'label'
            if key == "name":
                return getattr(entity, "text", default)
            if key == "type":
                return getattr(entity, "label", default)
            if key == "properties":
                # Check metadata for properties
                metadata = getattr(entity, "metadata", {})
                return metadata.get("properties", {})
            return getattr(entity, key, default)
        elif isinstance(entity, dict):
            return entity.get(key, default)
        return default
