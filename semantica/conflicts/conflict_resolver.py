"""
Conflict Resolver

This module provides comprehensive conflict resolution capabilities for the
Semantica framework, offering multiple strategies for resolving detected conflicts
including voting mechanisms, credibility-based resolution, and expert review.
The module includes granular progress tracking for large conflict sets.

Algorithms Used:

Voting Algorithm:
    - Majority Value Selection: Uses Counter-based frequency counting to select
      the most frequently occurring value across sources
    - Tie Breaking: Handles ties by selecting first value or using confidence scores

Credibility Weighted Resolution:
    - Weighted Average Calculation: Calculates weighted average of values based on
      source credibility scores
    - Credibility Scoring: Uses source credibility from SourceTracker
    - Value Weight Calculation: Combines value frequency with source credibility

Temporal Selection:
    - Most Recent: Timestamp-based selection of newest value
    - First Seen: Temporal-based selection of oldest value
    - Timestamp Comparison: Compares source timestamps to determine temporal order

Confidence Selection:
    - Maximum Confidence: Selects value from source with highest confidence score
    - Confidence Comparison: Compares source confidence values

Manual/Expert Review:
    - Conflict Flagging: Flags conflicts for human review workflow
    - Review Queue Management: Manages conflicts requiring manual intervention

Key Features:
    - Automatic conflict resolution strategies
    - Voting-based resolution from multiple sources
    - Credibility-weighted conflict resolution
    - Manual conflict resolution workflow
    - Resolution rule configuration
    - Conflict resolution history tracking
    - Multiple resolution strategies (voting, credibility, recency, confidence)

Main Classes:
    - ResolutionStrategy: Conflict resolution strategy enumeration
    - ResolutionResult: Conflict resolution result data structure
    - ConflictResolver: Conflict resolver with multiple resolution strategies

Example Usage:
    >>> from semantica.conflicts import ConflictResolver
    >>> resolver = ConflictResolver()
    >>> result = resolver.resolve_conflict(conflict, strategy="voting")
    >>> results = resolver.resolve_conflicts(conflicts, strategy="voting")

Author: Semantica Contributors
License: MIT
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .conflict_detector import Conflict
from .source_tracker import SourceTracker


def _hashable_key(value: Any) -> Any:
    """Return a stable, hashable key for a conflicting value.

    Conflicting values may be unhashable (e.g. ``dict`` or ``list``), which
    breaks :class:`collections.Counter` and dict-key based aggregation used by
    the voting and credibility-weighted strategies.

    The key is *type-tagged* so that a serialized structure can never alias a
    scalar value: e.g. the dict ``{"a": 1}`` and the string ``'{"a": 1}'`` map
    to distinct keys instead of colliding. Hashable values keep their original
    identity within the ``"h"`` tag (so equal scalars still aggregate together);
    unhashable values are serialized to a stable JSON string under the ``"j"``
    tag, falling back to ``repr()`` under the ``"r"`` tag when JSON fails.
    """
    try:
        hash(value)
        return ("h", type(value).__name__, value)
    except TypeError:
        try:
            return ("j", json.dumps(value, sort_keys=True, default=str))
        except (TypeError, ValueError):
            return ("r", repr(value))


class ResolutionStrategy(str, Enum):
    """Conflict resolution strategy."""

    VOTING = "voting"
    CREDIBILITY_WEIGHTED = "credibility_weighted"
    MOST_RECENT = "most_recent"
    FIRST_SEEN = "first_seen"
    HIGHEST_CONFIDENCE = "highest_confidence"
    MANUAL_REVIEW = "manual_review"
    EXPERT_REVIEW = "expert_review"


@dataclass
class ResolutionResult:
    """Conflict resolution result."""

    conflict_id: str
    resolved: bool
    resolved_value: Any = None
    resolution_strategy: Optional[str] = None
    confidence: float = 0.0
    sources_used: List[str] = field(default_factory=list)
    resolution_notes: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConflictResolver:
    """
    Conflict resolver with multiple resolution strategies.

    • Automatic conflict resolution strategies
    • Voting-based resolution from multiple sources
    • Credibility-weighted conflict resolution
    • Manual conflict resolution workflow
    • Resolution rule configuration
    • Conflict resolution history tracking
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize conflict resolver.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - default_strategy: Default resolution strategy
                - source_tracker: Source tracker instance
                - resolution_rules: Custom resolution rules
        """
        self.logger = get_logger("conflict_resolver")
        self.config = config or {}
        self.config.update(kwargs)

        self.source_tracker = self.config.get("source_tracker") or SourceTracker()
        self.default_strategy = ResolutionStrategy(
            self.config.get("default_strategy", "voting")
        )
        self.resolution_rules: Dict[str, ResolutionStrategy] = self.config.get(
            "resolution_rules", {}
        )

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.resolution_history: List[ResolutionResult] = []

    def set_source_tracker(self, source_tracker: SourceTracker) -> None:
        """
        Set the source tracker instance.

        Args:
            source_tracker: Source tracker instance
        """
        self.source_tracker = source_tracker

    def _normalize_strategy(
        self, strategy: Union[str, ResolutionStrategy, None]
    ) -> ResolutionStrategy:
        """
        Normalize strategy to ResolutionStrategy enum.

        Args:
            strategy: Strategy as string, ResolutionStrategy enum, or None

        Returns:
            ResolutionStrategy enum

        Raises:
            ValueError: If string strategy is invalid
            TypeError: If strategy is not str, ResolutionStrategy, or None
        """
        if strategy is None:
            return self.default_strategy
        if isinstance(strategy, ResolutionStrategy):
            return strategy
        if isinstance(strategy, str):
            try:
                return ResolutionStrategy(strategy)
            except ValueError:
                valid_strategies = [s.value for s in ResolutionStrategy]
                raise ValueError(
                    f"Invalid strategy: {strategy}. "
                    f"Valid strategies: {valid_strategies}"
                )
        raise TypeError(
            f"Strategy must be str or ResolutionStrategy, got {type(strategy)}"
        )

    def resolve_conflict(
        self, conflict: Conflict, strategy: Union[str, ResolutionStrategy, None] = None
    ) -> ResolutionResult:
        """
        Resolve a conflict using specified strategy.

        Args:
            conflict: Conflict to resolve
            strategy: Resolution strategy as string (e.g., "voting"),
                     ResolutionStrategy enum, or None (uses default).
                     Valid strings: "voting", "credibility_weighted",
                     "most_recent", "first_seen", "highest_confidence",
                     "manual_review", "expert_review"

        Returns:
            Resolution result

        Examples:
            >>> resolver = ConflictResolver()
            >>> result = resolver.resolve_conflict(conflict, strategy="voting")
        """
        # Track conflict resolution
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="conflicts",
            submodule="ConflictResolver",
            message=f"Resolving conflict: {conflict.conflict_id}",
        )

        try:
            # Normalize strategy (handles None, string, or enum)
            normalized_strategy = self._normalize_strategy(strategy)

            # Check for property-specific rule if strategy was None
            if strategy is None:
                if conflict.property_name:
                    rule_key = f"{conflict.entity_id}.{conflict.property_name}"
                    if rule_key in self.resolution_rules:
                        normalized_strategy = self.resolution_rules[rule_key]

            strategy = normalized_strategy

            self.logger.info(
                (
                    f"Resolving conflict {conflict.conflict_id} using strategy: "
                    f"{strategy.value}"
                )
            )

            if strategy == ResolutionStrategy.VOTING:
                result = self._resolve_by_voting(conflict)
            elif strategy == ResolutionStrategy.CREDIBILITY_WEIGHTED:
                result = self._resolve_by_credibility(conflict)
            elif strategy == ResolutionStrategy.MOST_RECENT:
                result = self._resolve_by_recency(conflict)
            elif strategy == ResolutionStrategy.FIRST_SEEN:
                result = self._resolve_by_first_seen(conflict)
            elif strategy == ResolutionStrategy.HIGHEST_CONFIDENCE:
                result = self._resolve_by_confidence(conflict)
            elif strategy == ResolutionStrategy.MANUAL_REVIEW:
                result = self._flag_for_manual_review(conflict)
            elif strategy == ResolutionStrategy.EXPERT_REVIEW:
                result = self._flag_for_expert_review(conflict)
            else:
                result = self._resolve_by_voting(conflict)

            result.resolution_strategy = strategy.value
            conflict_type = (
                conflict.conflict_type.value
                if hasattr(conflict.conflict_type, "value")
                else conflict.conflict_type
            )
            result.metadata.setdefault("conflict_type", conflict_type)
            result.metadata.setdefault("entity_id", conflict.entity_id)
            result.metadata.setdefault("property_name", conflict.property_name)
            result.metadata.setdefault("relationship_id", conflict.relationship_id)
            if conflict.metadata:
                result.metadata.setdefault("conflict_metadata", conflict.metadata)
            self.resolution_history.append(result)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Resolved conflict using {strategy.value}",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def resolve_conflicts(
        self,
        conflicts: List[Conflict],
        strategy: Union[str, ResolutionStrategy, None] = None,
    ) -> List[ResolutionResult]:
        """
        Resolve multiple conflicts.

        Args:
            conflicts: List of conflicts to resolve
            strategy: Resolution strategy as string (e.g., "voting"),
                     ResolutionStrategy enum, or None (uses default).
                     Valid strings: "voting", "credibility_weighted",
                     "most_recent", "first_seen", "highest_confidence",
                     "manual_review", "expert_review"

        Returns:
            List of resolution results

        Examples:
            >>> resolver = ConflictResolver()
            >>> results = resolver.resolve_conflicts(conflicts, strategy="voting")
        """
        # Track conflict resolution
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="conflicts",
            submodule="ConflictResolver",
            message=f"Resolving {len(conflicts)} conflicts",
        )

        try:
            results = []
            total_conflicts = len(conflicts)
            if total_conflicts <= 10:
                update_interval = 1  # Update every item for small datasets
            else:
                update_interval = max(1, min(10, total_conflicts // 100))
            
            # Initial progress update
            remaining = total_conflicts
            self.progress_tracker.update_progress(
                tracking_id,
                processed=0,
                total=total_conflicts,
                message=f"Resolving conflicts... 0/{total_conflicts} (remaining: {remaining})"
            )

            for i, conflict in enumerate(conflicts):
                result = self.resolve_conflict(conflict, strategy)
                results.append(result)
                
                remaining = total_conflicts - (i + 1)
                # Update progress: always update for small datasets, or at intervals for large ones
                should_update = (
                    (i + 1) % update_interval == 0 or 
                    (i + 1) == total_conflicts or 
                    i == 0 or
                    total_conflicts <= 10  # Always update for small datasets
                )
                if should_update:
                    self.progress_tracker.update_progress(
                        tracking_id,
                        processed=i + 1,
                        total=total_conflicts,
                        message=f"Resolving conflicts... {i + 1}/{total_conflicts} (remaining: {remaining})"
                    )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Resolved {len(results)} conflicts",
            )
            return results

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _resolve_by_voting(self, conflict: Conflict) -> ResolutionResult:
        """Resolve conflict by voting (most common value wins)."""
        if not conflict.conflicting_values:
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                resolved=False,
                resolution_notes="No conflicting values to resolve",
            )

        # Count value occurrences (using stable hashable keys so that
        # unhashable values such as dict/list do not break Counter)
        key_to_value: Dict[Any, Any] = {}
        keys: List[Any] = []
        for value in conflict.conflicting_values:
            key = _hashable_key(value)
            key_to_value.setdefault(key, value)
            keys.append(key)

        value_counts = Counter(keys)
        most_common_key, count = value_counts.most_common(1)[0]
        most_common_value = key_to_value[most_common_key]

        # Calculate confidence based on vote ratio
        total_votes = len(conflict.conflicting_values)
        confidence = count / total_votes if total_votes > 0 else 0.0

        sources_used = [s.get("document", "unknown") for s in conflict.sources]

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            resolved=True,
            resolved_value=most_common_value,
            confidence=confidence,
            sources_used=sources_used,
            resolution_notes=(
                f"Resolved by voting: {count}/{total_votes} votes for this value"
            ),
        )

    def _resolve_by_credibility(self, conflict: Conflict) -> ResolutionResult:
        """Resolve conflict by credibility-weighted voting."""
        if not conflict.conflicting_values or not conflict.sources:
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                resolved=False,
                resolution_notes="Insufficient data for credibility-based resolution",
            )

        # Weight values by source credibility (keyed by stable hashable keys so
        # that unhashable values such as dict/list can be used as map keys)
        value_weights: Dict[Any, float] = {}
        key_to_value: Dict[Any, Any] = {}

        for i, value in enumerate(conflict.conflicting_values):
            source = conflict.sources[i] if i < len(conflict.sources) else {}
            document = source.get("document", "unknown")
            source_confidence = source.get("confidence", 0.5)
            credibility = self.source_tracker.get_source_credibility(document)

            weight = source_confidence * credibility

            key = _hashable_key(value)
            key_to_value.setdefault(key, value)
            if key not in value_weights:
                value_weights[key] = 0.0
            value_weights[key] += weight

        # Get value with highest weight
        if not value_weights:
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                resolved=False,
                resolution_notes="Could not calculate credibility weights",
            )

        resolved_key = max(value_weights.items(), key=lambda x: x[1])[0]
        resolved_value = key_to_value[resolved_key]
        total_weight = sum(value_weights.values())
        confidence = (
            value_weights[resolved_key] / total_weight if total_weight > 0 else 0.0
        )

        sources_used = [s.get("document", "unknown") for s in conflict.sources]

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            resolved=True,
            resolved_value=resolved_value,
            confidence=confidence,
            sources_used=sources_used,
            resolution_notes=(
                "Resolved by credibility-weighted voting "
                f"(weight: {value_weights[resolved_key]:.2f})"
            ),
        )

    def _resolve_by_recency(self, conflict: Conflict) -> ResolutionResult:
        """Resolve conflict by using most recent value."""
        if not conflict.sources:
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                resolved=False,
                resolution_notes="No source timestamps available",
            )

        # Find most recent source (by timestamp if available)
        most_recent_idx = 0
        most_recent_time = None

        for i, source in enumerate(conflict.sources):
            # Check metadata for timestamp
            timestamp = source.get("metadata", {}).get("timestamp")
            if timestamp:
                if not most_recent_time or timestamp > most_recent_time:
                    most_recent_time = timestamp
                    most_recent_idx = i

        resolved_value = conflict.conflicting_values[most_recent_idx]
        sources_used = [conflict.sources[most_recent_idx].get("document", "unknown")]

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            resolved=True,
            resolved_value=resolved_value,
            confidence=0.8,
            sources_used=sources_used,
            resolution_notes="Resolved by most recent value",
        )

    def _resolve_by_first_seen(self, conflict: Conflict) -> ResolutionResult:
        """Resolve conflict by using first seen value."""
        if not conflict.conflicting_values:
            return ResolutionResult(conflict_id=conflict.conflict_id, resolved=False)

        resolved_value = conflict.conflicting_values[0]
        sources_used = (
            [conflict.sources[0].get("document", "unknown")] if conflict.sources else []
        )

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            resolved=True,
            resolved_value=resolved_value,
            confidence=0.7,
            sources_used=sources_used,
            resolution_notes="Resolved by first seen value",
        )

    def _resolve_by_confidence(self, conflict: Conflict) -> ResolutionResult:
        """Resolve conflict by using value with highest confidence."""
        if not conflict.sources:
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                resolved=False,
                resolution_notes="No source confidence data available",
            )

        # Find source with highest confidence
        max_confidence = 0.0
        best_idx = 0

        for i, source in enumerate(conflict.sources):
            confidence = source.get("confidence", 0.0)
            if confidence > max_confidence:
                max_confidence = confidence
                best_idx = i

        resolved_value = conflict.conflicting_values[best_idx]
        sources_used = [conflict.sources[best_idx].get("document", "unknown")]

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            resolved=True,
            resolved_value=resolved_value,
            confidence=max_confidence,
            sources_used=sources_used,
            resolution_notes=f"Resolved by highest confidence ({max_confidence:.2f})",
        )

    def _flag_for_manual_review(self, conflict: Conflict) -> ResolutionResult:
        """Flag conflict for manual review."""
        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            resolved=False,
            resolution_notes="Flagged for manual review",
            metadata={"requires_manual_review": True, "severity": conflict.severity},
        )

    def _flag_for_expert_review(self, conflict: Conflict) -> ResolutionResult:
        """Flag conflict for expert review."""
        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            resolved=False,
            resolution_notes="Flagged for expert review",
            metadata={"requires_expert_review": True, "severity": conflict.severity},
        )

    def set_resolution_rule(
        self,
        entity_id: str,
        property_name: str,
        strategy: Union[str, ResolutionStrategy],
    ) -> bool:
        """
        Set custom resolution rule for specific property.

        Args:
            entity_id: Entity identifier
            property_name: Property name
            strategy: Resolution strategy as string (e.g., "voting") or
                     ResolutionStrategy enum

        Returns:
            True if rule set successfully

        Examples:
            >>> resolver.set_resolution_rule("entity_1", "name", "voting")
        """
        rule_key = f"{entity_id}.{property_name}"
        normalized_strategy = self._normalize_strategy(strategy)
        self.resolution_rules[rule_key] = normalized_strategy
        self.logger.info(
            f"Set resolution rule: {rule_key} -> {normalized_strategy.value}"
        )
        return True

    def get_resolution_history(self) -> List[ResolutionResult]:
        """
        Get conflict resolution history.

        Returns:
            List of resolution results
        """
        return self.resolution_history.copy()
