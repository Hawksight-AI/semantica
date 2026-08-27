"""
Duplicate Detector Module

This module provides comprehensive duplicate detection capabilities for the Semantica
framework, identifying duplicate entities and relationships in knowledge graphs using
similarity thresholds, clustering algorithms, and confidence scoring.

Algorithms Used:
    - Pairwise Comparison: Optimized all-pairs similarity calculation with blocking support
    - Batch Processing: Vectorized similarity calculations for efficiency
    - Union-Find Algorithm: Disjoint set union (DSU) for duplicate group formation
    - Confidence Scoring: Multi-factor confidence calculation combining similarity, name matches, property matches, and type matches
    - Incremental Processing: O(n×m) efficient comparison with individual tracking disabled for speed
    - Representative Selection: Most complete entity selection from duplicate groups

Key Features:
    - Entity duplicate detection using multi-factor similarity metrics
    - Relationship duplicate detection with granular progress tracking
    - Duplicate group formation using union-find algorithm for transitive closure
    - Incremental duplicate detection for new entities (streaming scenarios)
    - Confidence scoring for duplicate candidates with multiple factors
    - Representative entity selection from duplicate groups (most complete)
    - Batch and pairwise detection methods for different use cases

Main Classes:
    - DuplicateDetector: Main duplicate detection engine
    - DuplicateCandidate: Duplicate candidate representation with confidence scores
    - DuplicateGroup: Group of duplicate entities with representative selection

Example Usage:
    >>> from semantica.deduplication import DuplicateDetector
    >>> detector = DuplicateDetector(similarity_threshold=0.8, confidence_threshold=0.7)
    >>> duplicates = detector.detect_duplicates(entities)
    >>> groups = detector.detect_duplicate_groups(entities)
    >>>
    >>> # Incremental detection
    >>> new_candidates = detector.incremental_detect(new_entities, existing_entities)

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .similarity_calculator import SimilarityCalculator, SimilarityResult


@dataclass
class DuplicateCandidate:
    """Duplicate candidate representation."""

    entity1: Dict[str, Any]
    entity2: Dict[str, Any]
    similarity_score: float
    confidence: float
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DuplicateGroup:
    """Group of duplicate entities."""

    entities: List[Dict[str, Any]]
    similarity_scores: Dict[Tuple[str, str], float] = field(default_factory=dict)
    representative: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class DuplicateDetector:
    """
    Duplicate detection engine for knowledge graphs.

    This class provides comprehensive duplicate detection capabilities, identifying
    duplicate entities and relationships using similarity metrics, confidence scoring,
    and group formation algorithms.

    Features:
        - Entity duplicate detection using multi-factor similarity
        - Relationship duplicate detection
        - Duplicate group formation (union-find algorithm)
        - Incremental detection for new entities
        - Confidence scoring with multiple factors
        - Representative entity selection

    Example Usage:
        >>> detector = DuplicateDetector(similarity_threshold=0.8, confidence_threshold=0.7)
        >>> candidates = detector.detect_duplicates(entities)
        >>> groups = detector.detect_duplicate_groups(entities)
    """

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        confidence_threshold: float = 0.6,
        use_clustering: bool = True,
        config: Optional[Dict[str, Any]] = None,
        max_results: Optional[int] = None,
        top_k_per_entity: Optional[int] = None,
        min_similarity: Optional[float] = None,
        sort_by: str = "confidence",
        **kwargs,
    ):
        """
        Initialize duplicate detector.

        Sets up the detector with similarity calculator and configurable thresholds
        for duplicate detection and confidence scoring.

        Args:
            similarity_threshold: Minimum similarity score to consider entities as duplicates
                                (0.0 to 1.0, default: 0.7)
            confidence_threshold: Minimum confidence score for duplicate candidates
                                 (0.0 to 1.0, default: 0.6)
            use_clustering: Whether to use clustering for group formation (default: True)
            config: Configuration dictionary (merged with kwargs)
            max_results: Hard cap on total candidates returned across all entities.
                         Applied after sorting. ``None`` means no limit.
            top_k_per_entity: Keep at most this many candidates per entity (by the
                              sort field). ``None`` means no per-entity limit.
            min_similarity: Additional similarity floor applied on top of
                            ``similarity_threshold``. Candidates whose
                            ``similarity_score`` is below this value are dropped
                            before ranking. ``None`` means no extra floor.
            sort_by: Field used for ranking before limits are applied.
                     ``"confidence"`` (default) or ``"similarity_score"``.
            **kwargs: Additional configuration options:
                - similarity: Configuration for SimilarityCalculator
        """
        self.logger = get_logger("duplicate_detector")

        # Merge configuration
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize similarity calculator
        similarity_config = self.config.get("similarity", {})
        self.similarity_calculator = SimilarityCalculator(**similarity_config)

        # Detection thresholds
        self.similarity_threshold = similarity_threshold
        self.confidence_threshold = confidence_threshold
        self.use_clustering = use_clustering

        # Result limiting / ranking options — validate at construction time
        if max_results is not None and (not isinstance(max_results, int) or max_results < 0):
            raise ValueError(
                f"max_results must be None or a non-negative int, got {max_results!r}"
            )
        if top_k_per_entity is not None and (
            not isinstance(top_k_per_entity, int) or top_k_per_entity < 0
        ):
            raise ValueError(
                f"top_k_per_entity must be None or a non-negative int, got {top_k_per_entity!r}"
            )
        if min_similarity is not None and not (0.0 <= min_similarity <= 1.0):
            raise ValueError(
                f"min_similarity must be None or a float in [0.0, 1.0], got {min_similarity!r}"
            )
        if sort_by not in ("confidence", "similarity_score"):
            raise ValueError(
                f"sort_by must be 'confidence' or 'similarity_score', got {sort_by!r}"
            )
        self.max_results = max_results
        self.top_k_per_entity = top_k_per_entity
        self.min_similarity = min_similarity
        self.sort_by = sort_by

        # Initialize progress tracker and ensure it's enabled
        self.progress_tracker = get_progress_tracker()
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug(
            f"Duplicate detector initialized: similarity_threshold={similarity_threshold}, "
            f"confidence_threshold={confidence_threshold}, max_results={max_results}, "
            f"top_k_per_entity={top_k_per_entity}, min_similarity={min_similarity}, "
            f"sort_by={sort_by!r}"
        )

    def detect_duplicates(
        self,
        entities: List[Dict[str, Any]],
        threshold: Optional[float] = None,
        **options,
    ) -> List[DuplicateCandidate]:
        """
        Detect duplicate entities from a list.

        This method compares all pairs of entities and identifies duplicates based
        on similarity scores and confidence thresholds. Results are filtered and
        ranked by ``_apply_result_limits`` using the instance ``sort_by`` field
        (default: ``"confidence"``), then capped by ``top_k_per_entity`` and
        ``max_results``.

        Args:
            entities: List of entity dictionaries to check for duplicates.
                     Each entity should have at least a "name" field.
            threshold: Minimum similarity threshold (overrides instance default)
            **options: Additional detection options passed to similarity calculator

        Returns:
            List of DuplicateCandidate objects sorted by the ``sort_by`` field
            (highest first, default ``"confidence"``), capped by ``top_k_per_entity``
            and ``max_results``. Each candidate contains:
                - entity1, entity2: The duplicate entity pair
                - similarity_score: Similarity score (0.0 to 1.0)
                - confidence: Confidence score (0.0 to 1.0)
                - reasons: List of reasons why they're considered duplicates
                - metadata: Additional metadata

        Example:
            >>> entities = [
            ...     {"id": "1", "name": "Apple Inc."},
            ...     {"id": "2", "name": "Apple"},
            ...     {"id": "3", "name": "Microsoft"}
            ... ]
            >>> candidates = detector.detect_duplicates(entities, threshold=0.8)
            >>> # Returns candidates for Apple Inc. and Apple
        """
        # Track duplicate detection
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="deduplication",
            submodule="DuplicateDetector",
            message=f"Detecting duplicates in {len(entities)} entities",
        )

        try:
            # Use provided threshold or instance default
            detection_threshold = (
                threshold if threshold is not None else self.similarity_threshold
            )

            self.logger.info(
                f"Detecting duplicates in {len(entities)} entities "
                f"(threshold: {detection_threshold})"
            )

            self.progress_tracker.update_tracking(
                tracking_id, message="Calculating similarities..."
            )
            # Calculate similarity for all entity pairs
            similarities = self.similarity_calculator.batch_calculate_similarity(
                entities, threshold=detection_threshold
            )

            self.logger.debug(
                f"Found {len(similarities)} similar pairs above threshold"
            )

            self.progress_tracker.update_tracking(
                tracking_id, message="Creating duplicate candidates..."
            )
            # Create duplicate candidates from similar pairs
            candidates = []
            total_similarities = len(similarities)
            # Update more frequently: every 1% or at least every 10 items, but always update for small datasets
            if total_similarities <= 10:
                update_interval = 1  # Update every item for small datasets
            else:
                update_interval = max(1, min(10, total_similarities // 100))

            # Initial progress update - ALWAYS show this
            remaining = total_similarities
            self.progress_tracker.update_progress(
                tracking_id,
                processed=0,
                total=total_similarities,
                message=f"Creating duplicate candidates... 0/{total_similarities} (remaining: {remaining})",
            )

            for i, (entity1, entity2, score) in enumerate(similarities):
                candidate = self._create_duplicate_candidate(entity1, entity2, score)

                # Filter by confidence threshold; type mismatches are excluded
                # structurally so no threshold value can admit them.
                if (
                    candidate.confidence >= self.confidence_threshold
                    and "type_mismatch" not in candidate.reasons
                ):
                    candidates.append(candidate)

                remaining = total_similarities - (i + 1)
                # Update progress: always update for small datasets, or at intervals for large ones
                should_update = (
                    (i + 1) % update_interval == 0
                    or (i + 1) == total_similarities
                    or i == 0
                    or total_similarities <= 10  # Always update for small datasets
                )
                if should_update:
                    self.progress_tracker.update_progress(
                        tracking_id,
                        processed=i + 1,
                        total=total_similarities,
                        message=f"Creating duplicate candidates... {i + 1}/{total_similarities} (remaining: {remaining})",
                    )

            # Sort, filter, and cap results
            candidates = self._apply_result_limits(candidates)

            self.logger.info(
                f"Detected {len(candidates)} duplicate candidate(s) "
                f"(confidence >= {self.confidence_threshold})"
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Detected {len(candidates)} duplicate candidates",
            )
            return candidates

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def detect_duplicate_groups(
        self,
        entities: List[Dict[str, Any]],
        threshold: Optional[float] = None,
        **options,
    ) -> List[DuplicateGroup]:
        """
        Detect groups of duplicate entities.

        This method identifies duplicate entities and groups them together using
        a union-find algorithm. Each group represents entities that are duplicates
        of each other, with confidence scores and representative entities.

        Process:
            1. Detect duplicate candidates using similarity
            2. Build groups using union-find (entities in same group are duplicates)
            3. Calculate group confidence scores
            4. Select representative entity for each group

        Args:
            entities: List of entity dictionaries to group
            threshold: Minimum similarity threshold (overrides instance default)
            **options: Additional detection options passed to detect_duplicates()

        Returns:
            List of DuplicateGroup objects, each containing:
                - entities: List of duplicate entities in the group
                - similarity_scores: Dict mapping entity pairs to similarity scores
                - representative: Representative entity (most complete)
                - confidence: Group confidence score (0.0 to 1.0)
                - metadata: Additional group metadata

        Example:
            >>> groups = detector.detect_duplicate_groups(entities, threshold=0.8)
            >>> for group in groups:
            ...     print(f"Group: {len(group.entities)} entities, "
            ...           f"confidence: {group.confidence:.2f}")
        """
        # Track duplicate group detection
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="deduplication",
            submodule="DuplicateDetector",
            message=f"Detecting duplicate groups from {len(entities)} entities",
        )

        try:
            self.logger.info(
                f"Detecting duplicate groups from {len(entities)} entities"
            )

            # Initial progress update
            self.progress_tracker.update_tracking(
                tracking_id,
                status="running",
                message=f"Starting duplicate detection for {len(entities)} entities...",
            )

            # Detect duplicate candidates
            candidates = self.detect_duplicates(
                entities, threshold=threshold, **options
            )

            self.progress_tracker.update_tracking(
                tracking_id, message="Building duplicate groups..."
            )
            # Build groups using union-find approach
            # This connects entities that are duplicates into groups
            groups = self._build_duplicate_groups(candidates)

            self.logger.debug(f"Built {len(groups)} duplicate group(s)")

            self.progress_tracker.update_tracking(
                tracking_id, message="Calculating group metrics..."
            )
            # Calculate group metrics for each group
            total_groups = len(groups)
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
                message=f"Calculating group metrics... 0/{total_groups} (remaining: {remaining})",
            )

            for i, group in enumerate(groups):
                group.confidence = self._calculate_group_confidence(group)
                group.representative = self._select_representative(group)

                remaining = total_groups - (i + 1)
                # Update progress: always update for small datasets, or at intervals for large ones
                should_update = (
                    (i + 1) % update_interval == 0
                    or (i + 1) == total_groups
                    or i == 0
                    or total_groups <= 10  # Always update for small datasets
                )
                if should_update:
                    self.progress_tracker.update_progress(
                        tracking_id,
                        processed=i + 1,
                        total=total_groups,
                        message=f"Calculating group metrics... {i + 1}/{total_groups} (remaining: {remaining})",
                    )

            self.logger.info(
                f"Detected {len(groups)} duplicate group(s) with "
                f"{sum(len(g.entities) for g in groups)} total entities"
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Detected {len(groups)} duplicate groups",
            )
            return groups

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def detect_relationship_duplicates(
        self, relationships: List[Dict[str, Any]], **options
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """
        Detect duplicate relationships using opt-in semantic canonicalization.

        Args:
            relationships: List of relationships
            **options: Detection options

        Returns:
            List of duplicate relationship pairs
        """
        # Track relationship duplicate detection
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="deduplication",
            submodule="DuplicateDetector",
            message=f"Detecting duplicate relationships in {len(relationships)} relations",
        )

        try:
            duplicates = []
            threshold = options.get("threshold", 0.9)
            mode = options.get("relationship_dedup_mode", "legacy")

            canon_sigs = []

            if mode == "semantic_v2":
                synonym_map = options.get("predicate_synonym_map", {})
                norm_enabled = options.get("literal_normalization_enabled", False)

                for rel in relationships:
                    subj = str(rel.get("subject", ""))
                    pred = str(rel.get("predicate", "")).lower()
                    obj = str(rel.get("object", ""))

                    canon_pred = synonym_map.get(pred, pred)
                    if norm_enabled:
                        obj = " ".join(obj.lower().split())

                    sig = hash((subj, canon_pred, obj))
                    canon_sigs.append(sig)

            total_rels = len(relationships)
            total_pairs = total_rels * (total_rels - 1) // 2
            processed = 0
            update_interval = (
                1 if total_pairs <= 10 else max(1, min(100, total_pairs // 100))
            )

            for i in range(len(relationships)):
                for j in range(i + 1, len(relationships)):
                    rel1 = relationships[i]
                    rel2 = relationships[j]

                    is_duplicate = False

                    if mode == "semantic_v2" and canon_sigs[i] == canon_sigs[j]:
                        is_duplicate = True

                    else:
                        is_duplicate = self._relationships_are_duplicates(
                            rel1, rel2, threshold, mode, options
                        )

                    if is_duplicate:
                        duplicates.append((rel1, rel2))

                    processed += 1

                    if processed % update_interval == 0 or processed == total_pairs:
                        self.progress_tracker.update_progress(
                            tracking_id,
                            processed=processed,
                            total=total_pairs,
                            message=f"Checking relationships... {processed}/{total_pairs}",
                        )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Detected {len(duplicates)} duplicate relationships",
            )

            return duplicates

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def incremental_detect(
        self,
        new_entities: List[Dict[str, Any]],
        existing_entities: List[Dict[str, Any]],
        threshold: Optional[float] = None,
        **options,
    ) -> List[DuplicateCandidate]:
        """
        Incremental duplicate detection for new entities.

        This method efficiently detects duplicates between new entities and an
        existing set of entities, avoiding the O(n²) comparison of all pairs.
        Useful for streaming or incremental data processing scenarios.

        Args:
            new_entities: List of new entity dictionaries to check for duplicates
            existing_entities: List of existing entity dictionaries to compare against
            threshold: Minimum similarity threshold (overrides instance default)
            **options: Additional detection options

        Returns:
            List of DuplicateCandidate objects representing duplicates between
            new and existing entities, sorted by the ``sort_by`` field (highest
            first, default ``"confidence"``), capped by ``top_k_per_entity`` and
            ``max_results``.

        Example:
            >>> new_entities = [{"id": "3", "name": "Apple Corp"}]
            >>> existing = [{"id": "1", "name": "Apple Inc."}]
            >>> candidates = detector.incremental_detect(new_entities, existing)
            >>> # Returns candidates if Apple Corp and Apple Inc. are duplicates
        """
        detection_threshold = (
            threshold if threshold is not None else self.similarity_threshold
        )

        # Track incremental detection
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="deduplication",
            submodule="DuplicateDetector",
            message=f"Incremental detection: {len(new_entities)} new vs {len(existing_entities)} existing",
        )

        try:
            self.logger.info(
                f"Incremental detection: {len(new_entities)} new entities vs "
                f"{len(existing_entities)} existing entities"
            )

            candidates = []
            total_comparisons = len(new_entities) * len(existing_entities)
            processed = 0
            # Update more frequently: every 1% or at least every 10 items, but always update for small datasets
            if total_comparisons <= 10:
                update_interval = 1  # Update every item for small datasets
            else:
                update_interval = max(1, min(10, total_comparisons // 100))

            # Initial progress update - ALWAYS show this
            remaining = total_comparisons
            self.progress_tracker.update_progress(
                tracking_id,
                processed=0,
                total=total_comparisons,
                message=f"Starting incremental detection... 0/{total_comparisons} (remaining: {remaining})",
            )

            # Compare each new entity with all existing entities
            for new_entity in new_entities:
                for existing_entity in existing_entities:
                    # Calculate similarity without individual tracking for speed
                    similarity = self.similarity_calculator.calculate_similarity(
                        new_entity, existing_entity, track=False
                    )

                    # Check if above threshold
                    if similarity.score >= detection_threshold:
                        candidate = self._create_duplicate_candidate(
                            new_entity, existing_entity, similarity.score
                        )

                        # Filter by confidence threshold; type mismatches are
                        # excluded structurally regardless of the threshold.
                        if (
                            candidate.confidence >= self.confidence_threshold
                            and "type_mismatch" not in candidate.reasons
                        ):
                            candidates.append(candidate)

                    processed += 1
                    remaining = total_comparisons - processed
                    # Update progress: always update for small datasets, or at intervals for large ones
                    should_update = (
                        processed % update_interval == 0
                        or processed == total_comparisons
                        or processed == 1
                        or total_comparisons <= 10  # Always update for small datasets
                    )
                    if should_update:
                        self.progress_tracker.update_progress(
                            tracking_id,
                            processed=processed,
                            total=total_comparisons,
                            message=f"Comparing entities... {processed}/{total_comparisons} (remaining: {remaining})",
                        )

            # Sort, filter, and cap results
            candidates = self._apply_result_limits(candidates)

            self.logger.info(
                f"Incremental detection found {len(candidates)} duplicate candidate(s)"
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Found {len(candidates)} duplicate candidates",
            )
            return candidates

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _apply_result_limits(
        self, candidates: List[DuplicateCandidate]
    ) -> List[DuplicateCandidate]:
        """
        Apply min_similarity filter, sort, top_k_per_entity, and max_results cap.

        Order of operations:
        1. Drop candidates below ``min_similarity`` (if set).
        2. Sort by ``sort_by`` field descending.
        3. Apply ``top_k_per_entity``: for each entity id keep only the top-k
           candidates in which it appears.
        4. Apply ``max_results`` global cap.
        """
        # 1. min_similarity filter
        if self.min_similarity is not None:
            candidates = [
                c for c in candidates if c.similarity_score >= self.min_similarity
            ]

        # 2. Sort descending by the chosen field
        candidates.sort(key=lambda c: getattr(c, self.sort_by), reverse=True)

        # 3. top_k_per_entity — keep a candidate if *either* entity is still under
        #    quota; once an entity reaches k it no longer sponsors new candidates.
        if self.top_k_per_entity is not None:
            entity_counts: Dict[str, int] = {}
            kept: List[DuplicateCandidate] = []
            for c in candidates:
                nid1 = self._normalize_entity_id(c.entity1)
                nid2 = self._normalize_entity_id(c.entity2)
                count1 = entity_counts.get(nid1, 0)
                count2 = entity_counts.get(nid2, 0)
                if count1 < self.top_k_per_entity or count2 < self.top_k_per_entity:
                    kept.append(c)
                    entity_counts[nid1] = count1 + 1
                    entity_counts[nid2] = count2 + 1
            candidates = kept

        # 4. max_results global cap
        if self.max_results is not None:
            candidates = candidates[: self.max_results]

        return candidates

    def _normalize_entity_id(self, entity: Any) -> str:
        """Return a stable string key for an entity, used as a dict key throughout the class."""
        raw = self._get_entity_value(entity, "id")
        if raw is None:
            raw = id(entity)
        return str(raw)

    def _get_entity_value(self, entity: Any, key: str, default: Any = None) -> Any:
        """Get value from entity dictionary or object safely."""
        if hasattr(entity, "__dict__"):
            # For Entity objects, map 'name' to 'text' and 'type' to 'label'
            if key == "name":
                return getattr(entity, "text", default)
            if key == "type":
                # Entity objects store the type on .type; extraction entities
                # may expose .label. Missing .label never means "no type".
                return getattr(entity, "type", default) or getattr(entity, "label", default)
            if key == "properties":
                # Check metadata for properties
                metadata = getattr(entity, "metadata", {})
                return metadata.get("properties", {})
            return getattr(entity, key, default)
        elif isinstance(entity, dict):
            return entity.get(key, default)
        return default

    def _create_duplicate_candidate(
        self,
        entity1: Dict[str, Any],
        entity2: Dict[str, Any],
        similarity_score: float,
    ) -> DuplicateCandidate:
        """
        Create duplicate candidate from similarity result.

        This method builds a DuplicateCandidate object by analyzing the similarity
        score and additional factors (name match, property matches, type match)
        to calculate a confidence score.

        Args:
            entity1: First entity dictionary or object
            entity2: Second entity dictionary or object
            similarity_score: Base similarity score from similarity calculator

        Returns:
            DuplicateCandidate object with calculated confidence and reasons
        """
        reasons = []
        confidence = similarity_score

        # Check entity type mismatch first: two entities with different
        # explicit types are not duplicates, whatever their similarity.
        entity_type1 = self._get_entity_value(entity1, "type")
        entity_type2 = self._get_entity_value(entity2, "type")
        if entity_type1 and entity_type2 and entity_type1 != entity_type2:
            return DuplicateCandidate(
                entity1=entity1,
                entity2=entity2,
                similarity_score=similarity_score,
                confidence=0.0,
                reasons=["type_mismatch"],
                metadata={
                    "name_match": False,
                    "common_properties": 0,
                    "type_match": False,
                    "type_mismatch": True,
                },
            )

        # Check for exact name match (strong indicator)
        name1 = str(self._get_entity_value(entity1, "name", "")).lower().strip()
        name2 = str(self._get_entity_value(entity2, "name", "")).lower().strip()
        if name1 == name2 and name1:  # Non-empty exact match
            reasons.append("exact_name_match")
            confidence += 0.1

        # Check property value matches
        props1 = self._get_entity_value(entity1, "properties", {})
        props2 = self._get_entity_value(entity2, "properties", {})

        common_props = set(props1.keys()) & set(props2.keys())
        if common_props:
            # Count properties with matching values
            prop_matches = sum(
                1 for prop in common_props if props1.get(prop) == props2.get(prop)
            )
            if prop_matches > 0:
                reasons.append(f"{prop_matches}_property_matches")
                # Boost confidence for each matching property
                confidence += 0.05 * prop_matches

        # Check entity type match (only boosts when types are equal; mismatch
        # is handled above)
        if entity_type1 and entity_type2 and entity_type1 == entity_type2:
            reasons.append("same_type")
            confidence += 0.05

        # Cap confidence at 1.0
        confidence = min(1.0, confidence)

        return DuplicateCandidate(
            entity1=entity1,
            entity2=entity2,
            similarity_score=similarity_score,
            confidence=confidence,
            reasons=reasons,
            metadata={
                "name_match": name1 == name2,
                "common_properties": len(common_props),
                "type_match": entity_type1 == entity_type2,
            },
        )

    def _build_duplicate_groups(
        self, candidates: List[DuplicateCandidate]
    ) -> List[DuplicateGroup]:
        """Build duplicate groups from candidates."""
        # Union-find structure
        entity_to_group = {}
        groups = []

        for candidate in candidates:
            entity1_id = self._normalize_entity_id(candidate.entity1)
            entity2_id = self._normalize_entity_id(candidate.entity2)

            group1 = entity_to_group.get(entity1_id)
            group2 = entity_to_group.get(entity2_id)

            if group1 is None and group2 is None:
                # Create new group
                group = DuplicateGroup(
                    entities=[candidate.entity1, candidate.entity2],
                    similarity_scores={
                        (entity1_id, entity2_id): candidate.similarity_score
                    },
                )
                groups.append(group)
                entity_to_group[entity1_id] = group
                entity_to_group[entity2_id] = group
            elif group1 is not None and group2 is None:
                # Add entity2 to group1
                if candidate.entity2 not in group1.entities:
                    group1.entities.append(candidate.entity2)
                group1.similarity_scores[(entity1_id, entity2_id)] = (
                    candidate.similarity_score
                )
                entity_to_group[entity2_id] = group1
            elif group1 is None and group2 is not None:
                # Add entity1 to group2
                if candidate.entity1 not in group2.entities:
                    group2.entities.append(candidate.entity1)
                group2.similarity_scores[(entity1_id, entity2_id)] = (
                    candidate.similarity_score
                )
                entity_to_group[entity1_id] = group2
            elif group1 != group2:
                # Merge groups
                group1.entities.extend(
                    [e for e in group2.entities if e not in group1.entities]
                )
                group1.similarity_scores.update(group2.similarity_scores)
                group1.similarity_scores[(entity1_id, entity2_id)] = (
                    candidate.similarity_score
                )

                # Update references
                for entity in group2.entities:
                    entity_id = self._normalize_entity_id(entity)
                    entity_to_group[entity_id] = group1

                if group2 in groups:
                    groups.remove(group2)

        return groups

    def _calculate_group_confidence(self, group: DuplicateGroup) -> float:
        """Calculate confidence for duplicate group."""
        if not group.similarity_scores:
            return 0.0

        scores = list(group.similarity_scores.values())
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Boost confidence for larger groups
        size_factor = min(1.0, len(group.entities) / 5.0)

        return avg_score * (0.8 + 0.2 * size_factor)

    def _select_representative(self, group: DuplicateGroup) -> Dict[str, Any]:
        """Select representative entity from group."""
        if not group.entities:
            return None

        # Select entity with most properties/relationships
        best_entity = max(
            group.entities,
            key=lambda e: len(self._get_entity_value(e, "properties", {}))
            + len(self._get_entity_value(e, "relationships", [])),
        )

        return best_entity

    def _relationships_are_duplicates(
        self,
        rel1: Dict[str, Any],
        rel2: Dict[str, Any],
        threshold: float,
        mode: str = "legacy",
        options: Dict = None,
    ) -> bool:
        """Check if two relationships are duplicates."""
        options = options or {}

        def get_rel_val(rel, key):
            if hasattr(rel, "__dict__"):
                return getattr(rel, key, None)
            if isinstance(rel, dict):
                return rel.get(key)
            return None

        subj1 = get_rel_val(rel1, "subject")
        subj2 = get_rel_val(rel2, "subject")
        pred1 = str(get_rel_val(rel1, "predicate") or "")
        pred2 = str(get_rel_val(rel2, "predicate") or "")
        obj1 = str(get_rel_val(rel1, "object") or "")
        obj2 = str(get_rel_val(rel2, "object") or "")

        if mode == "legacy":
            if subj1 == subj2 and pred1 == pred2 and obj1 == obj2:
                return True
            similarity = self.similarity_calculator.calculate_string_similarity(
                pred1, pred2
            )
            return similarity >= threshold

        if subj1 != subj2:
            return False

        synonyms = options.get("predicate_synonym_map", {})
        c_pred1 = synonyms.get(pred1.lower(), pred1.lower())
        c_pred2 = synonyms.get(pred2.lower(), pred2.lower())

        pred_sim = (
            1.0
            if c_pred1 == c_pred2
            else self.similarity_calculator.calculate_string_similarity(
                c_pred1, c_pred2
            )
        )

        if options.get("literal_normalization_enabled", False):
            obj1 = " ".join(obj1.lower().split())
            obj2 = " ".join(obj2.lower().split())

        obj_sim = (
            1.0
            if obj1 == obj2
            else self.similarity_calculator.calculate_string_similarity(obj1, obj2)
        )

        # Weighted composition: Predicate is 60% of the match, Object literal is 40%
        semantic_score = (pred_sim * 0.6) + (obj_sim * 0.4)

        # Metadata explainability
        if semantic_score >= threshold:
            if isinstance(rel1, dict) and isinstance(rel2, dict):
                rel1.setdefault("metadata", {})["semantic_match_score"] = semantic_score
                rel2.setdefault("metadata", {})["semantic_match_score"] = semantic_score

        return semantic_score >= threshold
