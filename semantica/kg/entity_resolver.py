"""
Entity Resolver Module

This module provides entity disambiguation and resolution capabilities for
knowledge graph construction, helping to merge duplicate entities and
maintain entity consistency.

Key Features:
    - Entity deduplication and merging
    - Multiple resolution strategies (fuzzy, exact, semantic)
    - Similarity-based entity matching
    - Entity ID normalization and tracking

Example Usage:
    >>> from semantica.kg import EntityResolver
    >>> resolver = EntityResolver(strategy="fuzzy", similarity_threshold=0.8)
    >>> resolved = resolver.resolve_entities(entities)

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional

from ..deduplication.duplicate_detector import DuplicateDetector, DuplicateGroup
from ..deduplication.entity_merger import EntityMerger
from ..utils.entity_ids import get_entity_id
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class EntityResolver:
    """
    Entity resolver for knowledge graph construction.

    This class provides entity disambiguation and resolution by detecting
    duplicate entities and merging them based on similarity. It supports
    multiple resolution strategies and configurable similarity thresholds.

    Resolution Strategies:
        - "fuzzy": Fuzzy string matching (default)
        - "exact": Exact string matching
        - "semantic": Semantic similarity matching

    Example Usage:
        >>> resolver = EntityResolver(strategy="fuzzy", similarity_threshold=0.8)
        >>> entities = [{"id": "1", "name": "Apple Inc."}, {"id": "2", "name": "Apple"}]
        >>> resolved = resolver.resolve_entities(entities)
    """

    def __init__(
        self, strategy: str = "fuzzy", similarity_threshold: float = 0.7, **config
    ):
        """
        Initialize entity resolver.

        Sets up the resolver with duplicate detection and entity merging
        components configured according to the specified strategy.

        Args:
            strategy: Resolution strategy - "fuzzy", "exact", or "semantic" (default: "fuzzy")
            similarity_threshold: Minimum similarity score for considering entities as duplicates
                                 (0.0 to 1.0, default: 0.7)
            **config: Additional configuration:
                - deduplication: Configuration for duplicate detector
                - merger: Configuration for entity merger
        """
        self.logger = get_logger("entity_resolver")

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True
        self.config = config

        # Resolution strategy and threshold
        self.resolution_strategy = strategy
        self.similarity_threshold = similarity_threshold

        # Initialize deduplication components
        deduplication_config = config.get("deduplication", {})
        merger_config = config.get("merger", {})

        self.duplicate_detector = DuplicateDetector(**deduplication_config)
        self.entity_merger = EntityMerger(**merger_config)

        self.logger.debug(
            f"Entity resolver initialized with strategy: {strategy}, "
            f"threshold: {similarity_threshold}"
        )

    def resolve_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Resolve and disambiguate entities by detecting and merging duplicates.

        This method performs a three-step process:
        1. Detect duplicate entity groups using similarity matching
        2. Merge duplicate groups into single canonical entities
        3. Combine merged entities with non-duplicate entities

        Args:
            entities: List of entity dictionaries to resolve. Each entity should
                     have at least an "id" or "entity_id" field and a "name" field.

        Returns:
            List of resolved entities with duplicates merged. The number of
            returned entities will be less than or equal to the input count.

        Example:
            >>> entities = [
            ...     {"id": "1", "name": "Apple Inc.", "type": "Company"},
            ...     {"id": "2", "name": "Apple", "type": "Company"},
            ...     {"id": "3", "name": "Microsoft", "type": "Company"}
            ... ]
            >>> resolved = resolver.resolve_entities(entities)
            >>> # Returns 2 entities: merged "Apple Inc."/Apple and "Microsoft"
        """
        self.logger.info(
            f"Resolving {len(entities)} entities using {self.resolution_strategy} strategy"
        )

        # Handle empty input
        if not entities:
            self.logger.debug("No entities to resolve")
            return []

        # Track entity resolution
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="kg",
            submodule="EntityResolver",
            message="Resolving entities",
        )

        try:
            # Step 1: Detect duplicate groups
            # Groups entities that are similar enough to be considered duplicates
            self.logger.debug(
                f"Detecting duplicate groups with threshold {self.similarity_threshold}"
            )
            duplicate_groups = self._detect_duplicate_groups(entities)

            self.logger.debug(f"Found {len(duplicate_groups)} duplicate group(s)")

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Found {len(duplicate_groups)} duplicate group(s)"
            )
            # Step 2: Merge duplicates in each group
            merged_entities = []
            processed_entity_ids = set()  # Track which entities have been merged
            processed_entity_objects = set()

            for group in duplicate_groups:
                # Skip groups with less than 2 entities (not duplicates)
                if len(group.entities) < 2:
                    continue

                # Merge the duplicate group into a single canonical entity
                if self.resolution_strategy == "exact":
                    merge_operations = [
                        self.entity_merger.merge_entity_group(
                            group.entities, **self.config
                        )
                    ]
                else:
                    merge_operations = self.entity_merger.merge_duplicates(
                        group.entities, **self.config
                    )

                # Process each merge operation
                for operation in merge_operations:
                    merged_entity = operation.merged_entity
                    merged_entities.append(merged_entity)

                    # Mark all source entities as processed
                    for source_entity in operation.source_entities:
                        entity_id = self._get_entity_id(source_entity)
                        if entity_id is None:
                            processed_entity_objects.add(id(source_entity))
                            continue
                        try:
                            processed_entity_ids.add(entity_id)
                        except TypeError:
                            processed_entity_objects.add(id(source_entity))

            # Step 3: Add non-duplicate entities (entities not in any duplicate group)
            for entity in entities:
                entity_id = self._get_entity_id(entity)
                if entity_id is None:
                    is_unprocessed = id(entity) not in processed_entity_objects
                else:
                    try:
                        is_unprocessed = entity_id not in processed_entity_ids
                    except TypeError:
                        is_unprocessed = id(entity) not in processed_entity_objects
                if is_unprocessed:
                    # This entity was not merged, add it as-is
                    merged_entities.append(entity)

            # Log resolution statistics
            original_count = len(entities)
            resolved_count = len(merged_entities)
            reduction = original_count - resolved_count

            self.logger.info(
                f"Entity resolution complete: {original_count} -> {resolved_count} "
                f"({reduction} duplicate(s) merged)"
            )

            return merged_entities

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _detect_duplicate_groups(
        self, entities: List[Dict[str, Any]]
    ) -> List[DuplicateGroup]:
        """Detect duplicate groups according to the configured strategy."""
        if self.resolution_strategy != "exact":
            return self.duplicate_detector.detect_duplicate_groups(
                entities, threshold=self.similarity_threshold
            )

        groups = {}
        for entity in entities:
            name = self._get_entity_name(entity)
            normalized = str(name).strip() if name is not None else ""
            if normalized:
                groups.setdefault(normalized.casefold(), []).append(entity)

        return [
            DuplicateGroup(entities=group, confidence=1.0)
            for group in groups.values()
            if len(group) > 1
        ]

    @staticmethod
    def _get_entity_id(entity: Any) -> Any:
        """Return an entity ID while supporting dictionary and object inputs."""
        return get_entity_id(entity)

    @staticmethod
    def _get_entity_name(entity: Any) -> Optional[str]:
        """Return an entity name, falling back to text-based entity input."""
        if isinstance(entity, dict):
            name = entity.get("name")
            return (
                name if name is not None and str(name).strip() else entity.get("text")
            )
        name = getattr(entity, "name", None)
        return (
            name
            if name is not None and str(name).strip()
            else getattr(entity, "text", None)
        )

    def merge_duplicates(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge duplicate entities.

        Args:
            entities: List of entities

        Returns:
            Merged entities
        """
        self.logger.info(f"Merging duplicates from {len(entities)} entities")

        merge_operations = self.entity_merger.merge_duplicates(entities, **self.config)

        merged_entities = [op.merged_entity for op in merge_operations]

        # Add non-duplicate entities
        processed_ids = set()
        for op in merge_operations:
            for source_entity in op.source_entities:
                entity_id = get_entity_id(source_entity)
                if entity_id is not None:
                    processed_ids.add(entity_id)

        for entity in entities:
            entity_id = get_entity_id(entity)
            if entity_id is not None and entity_id not in processed_ids:
                merged_entities.append(entity)

        self.logger.info(f"Merged to {len(merged_entities)} entities")
        return merged_entities
