"""
Temporal Query Module
"""

import copy
import warnings
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from ..utils.progress_tracker import get_progress_tracker
from .temporal_model import (
    BiTemporalFact,
    TemporalBound,
    deserialize_relationship_temporal_fields,
    parse_temporal_bound,
    parse_temporal_value,
    relationship_to_json_ready,
    serialize_temporal_value,
    temporal_structure_to_json_ready,
)
from .temporal_reasoning import IntervalRelation, TemporalInterval, TemporalReasoningEngine
from ..utils.exceptions import ProcessingError, TemporalValidationError


@dataclass
class TemporalConsistencyIssue:
    message: str
    fact_id: str
    issue_type: str


@dataclass
class TemporalConsistencyReport:
    errors: List[Dict[str, str]]
    warnings: List[Dict[str, str]]


class TemporalGraphQuery:
    """
    Temporal knowledge graph query engine.

    This class provides time-aware querying capabilities for knowledge graphs
    with temporal information, enabling queries at specific time points, within
    time ranges, and temporal pattern detection.

    Features:
        - Time-point queries (filter relationships valid at specific time)
        - Time-range queries (filter relationships valid within range)
        - Temporal pattern detection (sequences, cycles, trends)
        - Graph evolution analysis
        - Temporal path finding (paths considering temporal validity)

    Example Usage:
        >>> query_engine = TemporalGraphQuery()
        >>> result = query_engine.query_at_time(graph, query, at_time="2024-01-01")
        >>> range_result = query_engine.query_time_range(graph, query, start_time, end_time)
        >>> evolution = query_engine.analyze_evolution(graph)
    """

    def __init__(
        self,
        enable_temporal_reasoning: bool = True,
        temporal_granularity: str = "day",
        max_temporal_depth: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize temporal query engine.

        Sets up the query engine with temporal reasoning configuration and
        pattern detector.

        Args:
            enable_temporal_reasoning: Enable temporal reasoning capabilities
                                    (default: True)
            temporal_granularity: Time granularity for queries
                                (default: "day", options: "second", "minute",
                                "hour", "day", "week", "month", "year")
            max_temporal_depth: Maximum depth for temporal queries (optional)
            **kwargs: Additional configuration options:
                - pattern_detection: Configuration for pattern detector (optional)
        """
        self.enable_temporal_reasoning = enable_temporal_reasoning
        self.temporal_granularity = temporal_granularity
        self.max_temporal_depth = max_temporal_depth

        # Initialize temporal query engine
        from ..utils.logging import get_logger

        self.logger = get_logger("temporal_query")

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Initialize pattern detector
        self.pattern_detector = TemporalPatternDetector(
            **kwargs.get("pattern_detection", {})
        )
        self.reasoning_engine = TemporalReasoningEngine()

    def query_at_time(
        self,
        graph: Any,
        query: str,
        at_time: Any,
        include_history: bool = False,
        temporal_precision: Optional[str] = None,
        time_axis: str = "valid",
        **options,
    ) -> Dict[str, Any]:
        """
        Query graph at specific time point.

        This method filters the knowledge graph to only include relationships
        that are valid at the specified time point, based on valid_from and
        valid_until fields in relationships.

        Args:
            graph: Knowledge graph to query (dict with "entities" and "relationships")
            query: Query string (currently unused, reserved for future query parsing)
            at_time: Time point (datetime object, timestamp, or ISO format string)
            include_history: Whether to include all relationships with temporal
                           information (default: False, only valid relationships)
            temporal_precision: Precision for time matching (optional, unused)
            **options: Additional query options (unused)

        Returns:
            dict: Query results containing:
                - query: Original query string
                - at_time: Parsed time point
                - entities: All entities (not filtered by time)
                - relationships: Relationships valid at specified time
                - num_entities: Number of entities
                - num_relationships: Number of valid relationships
        """
        self.logger.info(f"Querying graph at time: {at_time}")

        # Parse time
        query_time = self._parse_time(at_time)
        reconstructed_graph = self.reconstruct_at_time(
            graph,
            query_time,
            time_axis=time_axis,
        )

        # Get entities
        entities = reconstructed_graph.get("entities", [])
        relationships = reconstructed_graph.get("relationships", [])

        # Include history if requested
        if include_history:
            # Add all relationships with temporal information
            relationships = graph.get("relationships", [])

        return {
            "query": query,
            "at_time": query_time,
            "entities": entities,
            "relationships": relationships,
            "num_entities": len(entities),
            "num_relationships": len(relationships),
        }

    def reconstruct_at_time(
        self,
        graph: Any,
        at_time: Any,
        *,
        time_axis: str = "valid",
    ) -> Dict[str, Any]:
        """Return a self-consistent subgraph for a single point in time."""
        query_time = at_time if isinstance(at_time, datetime) else self._parse_time(at_time)
        reconstructed = copy.deepcopy(graph)
        entity_list = graph.get("entities", [])

        if not entity_list:
            reconstructed["entities"] = []
            reconstructed["relationships"] = [
                copy.deepcopy(relationship)
                for relationship in graph.get("relationships", [])
                if self._relationship_active_at_time(relationship, query_time, time_axis=time_axis)
            ]
            return reconstructed

        entity_index = {
            self._entity_id(entity): entity
            for entity in entity_list
            if self._entity_active_at_time(entity, query_time, time_axis=time_axis)
        }

        relationships = []
        for relationship in graph.get("relationships", []):
            if not self._relationship_active_at_time(relationship, query_time, time_axis=time_axis):
                continue
            source = self._entity_id({"id": relationship.get("source")})
            target = self._entity_id({"id": relationship.get("target")})
            if source not in entity_index or target not in entity_index:
                continue
            relationships.append(copy.deepcopy(relationship))

        reconstructed["entities"] = list(entity_index.values())
        reconstructed["relationships"] = relationships
        return reconstructed

    def validate_temporal_consistency(self, graph: Any) -> TemporalConsistencyReport:
        errors: List[Dict[str, str]] = []
        warnings_list: List[Dict[str, str]] = []

        entities = {
            self._entity_id(entity): entity
            for entity in graph.get("entities", [])
        }
        rel_groups: Dict[tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

        for relationship in graph.get("relationships", []):
            rel_id = relationship.get("id") or self._relationship_key(relationship)
            rel_groups[
                (
                    relationship.get("source", ""),
                    relationship.get("type", relationship.get("relationship", "")),
                    relationship.get("target", ""),
                )
            ].append(relationship)

            try:
                start, end = self._get_axis_bounds(relationship, "valid")
            except TemporalValidationError as exc:
                errors.append(
                    asdict(
                        TemporalConsistencyIssue(
                            message=f"Unable to parse temporal fields: {exc}",
                            fact_id=rel_id,
                            issue_type="invalid_temporal_fields",
                        )
                    )
                )
                continue
            if start and isinstance(end, datetime) and self._compare_times(start, end) > 0:
                errors.append(
                    asdict(
                        TemporalConsistencyIssue(
                            message="Relationship has an inverted validity interval.",
                            fact_id=rel_id,
                            issue_type="inverted_interval",
                        )
                    )
                )

            for endpoint in ("source", "target"):
                entity = entities.get(relationship.get(endpoint))
                if entity is None:
                    errors.append(
                        asdict(
                            TemporalConsistencyIssue(
                                message=f"Relationship references missing {endpoint} entity.",
                                fact_id=rel_id,
                                issue_type=f"missing_{endpoint}_entity",
                            )
                        )
                    )
                    continue
                try:
                    within_lifetime = self._window_within_entity_lifetime(entity, start, end)
                except TemporalValidationError as exc:
                    errors.append(
                        asdict(
                            TemporalConsistencyIssue(
                                message=f"Unable to parse {endpoint} entity lifetime: {exc}",
                                fact_id=rel_id,
                                issue_type=f"invalid_{endpoint}_temporal_fields",
                            )
                        )
                    )
                    continue
                if not within_lifetime:
                    errors.append(
                        asdict(
                            TemporalConsistencyIssue(
                                message=f"Relationship validity falls outside {endpoint} entity lifetime.",
                                fact_id=rel_id,
                                issue_type=f"{endpoint}_lifetime_mismatch",
                            )
                        )
                    )
        for relationships in rel_groups.values():
            safe_relationships = []
            for relationship in relationships:
                rel_id = relationship.get("id") or self._relationship_key(relationship)
                try:
                    start, end = self._get_axis_bounds(relationship, "valid")
                except TemporalValidationError as exc:
                    errors.append(
                        asdict(
                            TemporalConsistencyIssue(
                                message=f"Unable to parse temporal fields: {exc}",
                                fact_id=rel_id,
                                issue_type="invalid_temporal_fields",
                            )
                        )
                    )
                    continue
                safe_relationships.append((relationship, start, end))
            ordered = sorted(
                safe_relationships,
                key=lambda item: self._sort_key(item[1]),
            )
            for index, (current, current_start, current_end) in enumerate(ordered):
                current_id = current.get("id") or self._relationship_key(current)
                if index > 0:
                    _, previous_start, previous_end = ordered[index - 1]
                    if self._range_overlaps_bounds(
                        current_start or datetime.min.replace(tzinfo=timezone.utc),
                        current_end if isinstance(current_end, datetime) else datetime.max.replace(tzinfo=timezone.utc),
                        previous_start,
                        previous_end,
                    ):
                        warnings_list.append(
                            asdict(
                                TemporalConsistencyIssue(
                                    message="Relationship overlaps another relationship with the same edge and type.",
                                    fact_id=current_id,
                                    issue_type="overlapping_same_edge",
                                )
                            )
                        )
                    elif (
                        isinstance(previous_end, datetime)
                        and current_start
                        and self._compare_times(current_start, previous_end) > 0
                    ):
                        warnings_list.append(
                            asdict(
                                TemporalConsistencyIssue(
                                    message="Relationship restarts after a temporal gap.",
                                    fact_id=current_id,
                                    issue_type="gap_after_restart",
                                )
                            )
                        )
                    elif current_start and previous_start and self._compare_times(current_start, previous_start) == 0:
                        warnings_list.append(
                            asdict(
                                TemporalConsistencyIssue(
                                    message="Relationship interval overlaps another interval on the same edge.",
                                    fact_id=current_id,
                                    issue_type="overlapping_same_edge",
                                )
                            )
                        )

        return TemporalConsistencyReport(errors=errors, warnings=warnings_list)

    def query_time_range(
        self,
        graph: Any,
        query: str,
        start_time: Any,
        end_time: Any,
        temporal_aggregation: str = "union",
        include_intervals: bool = True,
        time_axis: str = "valid",
        **options,
    ) -> Dict[str, Any]:
        """
        Query graph within time range.

        This method filters relationships that are valid within the specified
        time range, with different aggregation strategies.

        Args:
            graph: Knowledge graph to query
            query: Query string (currently unused, reserved for future)
            start_time: Start of time range (datetime, timestamp, or ISO string)
            end_time: End of time range (datetime, timestamp, or ISO string)
            temporal_aggregation: Aggregation strategy:
                - "union": Include all relationships overlapping with range (default)
                - "intersection": Only relationships valid throughout entire range
                - "evolution": Group relationships by time periods
            include_intervals: Include partial matches within range (default: True)
            **options: Additional query options (unused)

        Returns:
            dict: Query results containing:
                - query: Original query string
                - start_time: Parsed start time
                - end_time: Parsed end time
                - relationships: Filtered relationships
                - num_relationships: Number of relationships
                - aggregation: Aggregation strategy used
        """
        self.logger.info(f"Querying graph in time range: {start_time} to {end_time}")

        # Parse times
        normalized_range = self.reasoning_engine.normalize_interval(
            start_time,
            end_time,
            self.temporal_granularity,
        )
        start = normalized_range.start
        end = normalized_range.end

        # Filter relationships valid in time range
        relationships = []
        relationship_buckets = None
        if "relationships" in graph:
            for rel in graph.get("relationships", []):
                if self._relationship_overlaps_range(
                    rel,
                    start,
                    end,
                    time_axis=time_axis,
                ):
                    relationships.append(rel)

        # Aggregate based on strategy
        if temporal_aggregation == "intersection":
            # Only relationships valid throughout the entire range
            relationships = [
                rel
                for rel in relationships
                if self._relationship_covers_range(rel, start, end, time_axis=time_axis)
            ]
        elif temporal_aggregation == "evolution":
            # Group by time periods
            relationship_buckets = self._group_by_time_periods(relationships, start, end)

        return {
            "query": query,
            "start_time": start,
            "end_time": end,
            "relationships": relationships,
            "relationship_buckets": relationship_buckets,
            "num_relationships": len(relationships),
            "aggregation": temporal_aggregation,
        }

    def query_temporal_pattern(
        self,
        graph: Any,
        pattern: str,
        time_window: Optional[Any] = None,
        min_support: int = 1,
        **options,
    ) -> Dict[str, Any]:
        """
        Query for temporal patterns in graph.

        This method detects temporal patterns (sequences, cycles, trends) in
        the knowledge graph using the temporal pattern detector.

        Args:
            graph: Knowledge graph to query
            pattern: Pattern type to search for ("sequence", "cycle", "trend", "anomaly")
            time_window: Time window for pattern matching (optional)
            min_support: Minimum frequency/support for pattern (default: 1)
            **options: Additional pattern query options

        Returns:
            dict: Pattern query results containing:
                - pattern: Pattern type searched
                - patterns: List of detected patterns
                - num_patterns: Number of patterns found
        """
        self.logger.info(f"Querying temporal patterns: {pattern}")

        # Use pattern detector
        patterns = self.pattern_detector.detect_temporal_patterns(
            graph,
            pattern_type=pattern,
            min_frequency=min_support,
            time_window=time_window,
            **options,
        )

        return {
            "pattern": pattern,
            "patterns": patterns,
            "num_patterns": len(patterns) if isinstance(patterns, list) else 0,
        }

    def analyze_evolution(
        self,
        graph: Any,
        entity: Optional[str] = None,
        relationship: Optional[str] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        metrics: Optional[List[str]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Analyze graph evolution over time.

        This method analyzes how the knowledge graph (or specific entities/relationships)
        evolves over a time period, calculating various evolution metrics.

        Args:
            graph: Knowledge graph to analyze
            entity: Specific entity ID to track (optional, None for entire graph)
            relationship: Specific relationship type to track (optional, None for all)
            start_time: Start of analysis period (optional)
            end_time: End of analysis period (optional)
            metrics: List of metrics to calculate (default: ["count", "diversity", "stability"])
                    - "count": Number of relationships
                    - "diversity": Number of unique relationship types
                    - "stability": Relationship duration/stability measure
            **options: Additional analysis options (unused)

        Returns:
            dict: Evolution analysis results containing:
                - entity: Entity ID tracked (if specified)
                - relationship: Relationship type tracked (if specified)
                - time_range: Dictionary with start and end times
                - num_relationships: Number of relationships in period
                - count: Relationship count (if "count" in metrics)
                - diversity: Relationship type diversity (if "diversity" in metrics)
                - stability: Stability measure (if "stability" in metrics)
        """
        self.logger.info("Analyzing graph evolution")

        # Set default metrics if None
        if metrics is None:
            metrics = ["count", "diversity", "stability"]

        # Filter relationships
        relationships = graph.get("relationships", [])

        if entity:
            relationships = [
                rel
                for rel in relationships
                if (rel.get("source") or rel.get("source_id")) == entity
                or (rel.get("target") or rel.get("target_id")) == entity
            ]

        if relationship:
            relationships = [
                rel for rel in relationships if rel.get("type") == relationship
            ]

        # Filter by time range
        if start_time or end_time:
            start = self._parse_time(start_time) if start_time else None
            end = self._parse_time(end_time) if end_time else None

            filtered = []
            for rel in relationships:
                valid_from = self._parse_time(rel.get("valid_from"))
                valid_until = self._parse_time(rel.get("valid_until"))

                if (
                    start
                    and valid_until
                    and self._compare_times(valid_until, start) < 0
                ):
                    continue
                if end and valid_from and self._compare_times(valid_from, end) > 0:
                    continue

                filtered.append(rel)
            relationships = filtered

        # Calculate metrics
        result = {
            "entity": entity,
            "relationship": relationship,
            "time_range": {"start": start_time, "end": end_time},
            "num_relationships": len(relationships),
        }

        if "count" in metrics:
            result["count"] = len(relationships)

        if "diversity" in metrics:
            rel_types = set(rel.get("type") for rel in relationships)
            result["diversity"] = len(rel_types)

        if "stability" in metrics:
            # Calculate stability based on relationship duration
            durations = []
            for rel in relationships:
                valid_from = self._parse_time(rel.get("valid_from"))
                valid_until = self._parse_time(rel.get("valid_until"))
                if valid_from and valid_until:
                    # Simplified duration calculation
                    durations.append(1)  # Placeholder
            result["stability"] = sum(durations) / len(durations) if durations else 0

        return result

    def find_temporal_paths(
        self,
        graph: Any,
        source: str,
        target: str,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        max_path_length: Optional[int] = None,
        temporal_constraints: Optional[Dict[str, Any]] = None,
        enforce_causal_ordering: bool = True,
        ordering_strategy: Literal["strict", "overlap", "loose"] = "strict",
        **options,
    ) -> Dict[str, Any]:
        """
        Find paths between entities considering temporal validity.

        This method finds paths between source and target entities, considering
        only relationships that are temporally valid within the specified
        time range. Uses BFS for path finding.

        Args:
            graph: Knowledge graph to search
            source: Source entity ID
            target: Target entity ID
            start_time: Start time for path validity (optional)
            end_time: End time for path validity (optional)
            max_path_length: Maximum path length in edges (optional)
            temporal_constraints: Additional temporal constraints (optional, unused)
            **options: Additional path finding options (unused)

        Returns:
            dict: Temporal path results containing:
                - source: Source entity ID
                - target: Target entity ID
                - paths: List of path dictionaries, each containing:
                    - path: List of node IDs forming the path
                    - edges: List of relationship dictionaries
                    - length: Path length in edges
                - num_paths: Total number of paths found
        """
        self.logger.info(f"Finding temporal paths from {source} to {target}")

        # Build adjacency with temporal constraints
        adjacency = {}
        relationships = graph.get("relationships", [])
        parsed_start_time = self._parse_time(start_time) if start_time else None
        parsed_end_time = self._parse_time(end_time) if end_time else None

        for rel in relationships:
            # Accept both the legacy ``source``/``target`` keys and the
            # canonical ``source_id``/``target_id`` keys from ``to_kg_dict()``.
            s = rel.get("source")
            if s is None:
                s = rel.get("source_id")
            t = rel.get("target")
            if t is None:
                t = rel.get("target_id")

            # Check temporal validity
            if start_time or end_time:
                valid_from = self._parse_time(rel.get("valid_from"))
                valid_until = self._parse_time(rel.get("valid_until"))

                if (
                    parsed_start_time
                    and valid_until
                    and self._compare_times(valid_until, parsed_start_time) < 0
                ):
                    continue
                if (
                    parsed_end_time
                    and valid_from
                    and self._compare_times(valid_from, parsed_end_time) > 0
                ):
                    continue

            if s not in adjacency:
                adjacency[s] = []
            adjacency[s].append((t, rel))

        # BFS to find paths
        from collections import deque

        paths = []
        queue = deque([(source, [source], [])])
        visited = set()
        max_length = max_path_length or float("inf")

        while queue:
            node, path, edges = queue.popleft()

            if len(path) > max_length:
                continue

            if node == target:
                paths.append({"path": path, "edges": edges, "length": len(path) - 1})
                continue

            if node in visited:
                continue
            visited.add(node)

            for neighbor, rel in adjacency.get(node, []):
                if neighbor not in path:  # Avoid cycles
                    next_edges = edges + [rel]
                    if self._path_respects_causal_order(
                        next_edges,
                        enforce_causal_ordering=enforce_causal_ordering,
                        ordering_strategy=ordering_strategy,
                    ):
                        queue.append((neighbor, path + [neighbor], next_edges))

        return {
            "source": source,
            "target": target,
            "paths": paths,
            "num_paths": len(paths),
        }

    def _parse_time(self, time_value):
        """Parse time value into a UTC-normalized datetime."""
        if time_value in (None, TemporalBound.OPEN, TemporalBound.OPEN.value):
            return None
        try:
            return parse_temporal_value(time_value)
        except TemporalValidationError:
            raise
        except Exception as exc:
            raise TemporalValidationError(
                "Invalid temporal value",
                temporal_context={"value": time_value},
            ) from exc

    def _compare_times(self, time1, time2):
        """Compare two UTC datetimes after granularity truncation."""
        if time1 is None or time2 is None:
            return 0
        time1 = self._truncate_to_granularity(time1)
        time2 = self._truncate_to_granularity(time2)
        return (time1 > time2) - (time1 < time2)

    def _truncate_to_granularity(self, value: datetime) -> datetime:
        granularity = getattr(self, "temporal_granularity", "second")
        return self.reasoning_engine.normalize_timestamp(value, granularity)

    def _get_axis_bounds(self, relationship: Dict[str, Any], axis: str):
        normalized = deserialize_relationship_temporal_fields(relationship)
        fact = BiTemporalFact.from_relationship(normalized)
        if axis == "valid":
            return fact.valid_from, fact.valid_until
        if axis == "transaction":
            return fact.recorded_at, fact.superseded_at
        raise ValueError(f"Unsupported time axis: {axis}")

    def _is_point_in_bounds(self, point: datetime, start: Optional[datetime], end: Optional[datetime | TemporalBound]) -> bool:
        if start is None:
            start = datetime.min.replace(tzinfo=timezone.utc)
        return self.reasoning_engine.active_at(
            TemporalInterval(start=start, end=end or TemporalBound.OPEN),
            point,
            granularity=self.temporal_granularity,
        )

    def _range_overlaps_bounds(self, query_start: datetime, query_end: datetime | TemporalBound, start: Optional[datetime], end: Optional[datetime | TemporalBound]) -> bool:
        query_end_value = datetime.max.replace(tzinfo=timezone.utc) if query_end is TemporalBound.OPEN else query_end
        if query_end_value < query_start:
            return False
        if isinstance(end, datetime) and start is not None and end < start:
            return False
        candidate = TemporalInterval(
            start=start or datetime.min.replace(tzinfo=timezone.utc),
            end=end or TemporalBound.OPEN,
        )
        query_interval = TemporalInterval(start=query_start, end=query_end)
        relation = self.reasoning_engine.relation(candidate, query_interval)
        return relation not in {
            IntervalRelation.BEFORE,
            IntervalRelation.AFTER,
        }

    def _range_covered_by_bounds(self, query_start: datetime, query_end: datetime | TemporalBound, start: Optional[datetime], end: Optional[datetime | TemporalBound]) -> bool:
        query_end_value = datetime.max.replace(tzinfo=timezone.utc) if query_end is TemporalBound.OPEN else query_end
        if query_end_value < query_start:
            return False
        if isinstance(end, datetime) and start is not None and end < start:
            return False
        candidate = TemporalInterval(
            start=start or datetime.min.replace(tzinfo=timezone.utc),
            end=end or TemporalBound.OPEN,
        )
        return self.reasoning_engine.contains(candidate, TemporalInterval(start=query_start, end=query_end))

    def _relationship_active_at_time(self, relationship: Dict[str, Any], query_time: datetime, *, time_axis: str) -> bool:
        axes = ["valid", "transaction"] if time_axis == "both" else [time_axis]
        return all(
            self._is_point_in_bounds(query_time, *self._get_axis_bounds(relationship, axis))
            for axis in axes
        )

    def _relationship_overlaps_range(self, relationship: Dict[str, Any], start: datetime, end: datetime | TemporalBound, *, time_axis: str) -> bool:
        axes = ["valid", "transaction"] if time_axis == "both" else [time_axis]
        return all(
            self._range_overlaps_bounds(start, end, *self._get_axis_bounds(relationship, axis))
            for axis in axes
        )

    def _relationship_covers_range(self, relationship: Dict[str, Any], start: datetime, end: datetime | TemporalBound, *, time_axis: str) -> bool:
        axes = ["valid", "transaction"] if time_axis == "both" else [time_axis]
        return all(
            self._range_covered_by_bounds(start, end, *self._get_axis_bounds(relationship, axis))
            for axis in axes
        )

    def _entity_id(self, entity: Dict[str, Any]) -> str:
        return str(entity.get("id", entity.get("name", "")))

    def _entity_active_at_time(self, entity: Dict[str, Any], query_time: datetime, *, time_axis: str) -> bool:
        relationship_like = {
            "valid_from": entity.get("valid_from"),
            "valid_until": entity.get("valid_until", TemporalBound.OPEN),
            "recorded_at": entity.get("recorded_at", entity.get("valid_from")),
            "superseded_at": entity.get("superseded_at", TemporalBound.OPEN),
        }
        return self._relationship_active_at_time(relationship_like, query_time, time_axis=time_axis)

    def _window_within_entity_lifetime(
        self,
        entity: Dict[str, Any],
        rel_start: Optional[datetime],
        rel_end: Optional[datetime | TemporalBound],
    ) -> bool:
        entity_start = self._parse_time(entity.get("valid_from")) if entity.get("valid_from") is not None else None
        entity_end = parse_temporal_bound(entity.get("valid_until"), default=TemporalBound.OPEN)
        if rel_start and entity_start and self._compare_times(rel_start, entity_start) < 0:
            return False
        if isinstance(entity_end, datetime):
            if rel_start and self._compare_times(rel_start, entity_end) > 0:
                return False
            if isinstance(rel_end, datetime) and self._compare_times(rel_end, entity_end) > 0:
                return False
            if rel_end is TemporalBound.OPEN:
                return False
        return True

    def _sort_key(self, value: Optional[datetime]) -> datetime:
        return value or datetime.min.replace(tzinfo=timezone.utc)

    def _period_floor(self, value: datetime) -> datetime:
        return self._truncate_to_granularity(value)

    def _next_period(self, value: datetime) -> datetime:
        if self.temporal_granularity == "day":
            return value + timedelta(days=1)
        if self.temporal_granularity == "week":
            return value + timedelta(weeks=1)
        if self.temporal_granularity == "month":
            if value.month == 12:
                return value.replace(year=value.year + 1, month=1)
            return value.replace(month=value.month + 1)
        if self.temporal_granularity == "year":
            return value.replace(year=value.year + 1)
        return value + timedelta(days=1)

    def _period_label(self, value: datetime) -> str:
        if self.temporal_granularity == "week":
            return f"{value.isocalendar().year}-W{value.isocalendar().week:02d}"
        if self.temporal_granularity == "month":
            return value.strftime("%Y-%m")
        if self.temporal_granularity == "year":
            return value.strftime("%Y")
        return value.strftime("%Y-%m-%d")

    def _path_respects_causal_order(
        self,
        edges: List[Dict[str, Any]],
        *,
        enforce_causal_ordering: bool,
        ordering_strategy: Literal["strict", "overlap", "loose"],
    ) -> bool:
        if not enforce_causal_ordering or ordering_strategy == "loose" or len(edges) < 2:
            return True

        previous = edges[-2]
        current = edges[-1]
        previous_start, previous_end = self._get_axis_bounds(previous, "valid")
        current_start, _ = self._get_axis_bounds(current, "valid")

        if ordering_strategy == "strict":
            if previous_start and current_start and self._compare_times(current_start, previous_start) < 0:
                return False
            return True
        if ordering_strategy == "overlap":
            if current_start is None:
                return True
            if isinstance(previous_end, datetime):
                return self._compare_times(current_start, previous_end) <= 0
            return True
        return True

    def _group_by_time_periods(self, relationships, start, end):
        """Group relationships into calendar-aligned buckets."""
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        current = self._period_floor(start)
        end_bound = self._period_floor(end)

        while current <= end_bound:
            bucket_end = self._next_period(current)
            label = self._period_label(current)
            for relationship in relationships:
                if self._relationship_overlaps_range(
                    relationship,
                    current,
                    bucket_end,
                    time_axis="valid",
                ):
                    buckets[label].append(relationship)
            current = bucket_end

        return dict(buckets)


class TemporalPatternDetector:
    """
    Temporal pattern detection engine.

    This class provides temporal pattern detection capabilities for knowledge
    graphs, identifying recurring patterns, sequences, cycles, and trends in
    temporal data.

    Features:
        - Sequence pattern detection
        - Cycle pattern detection
        - Trend analysis
        - Anomaly detection (planned)

    Example Usage:
        >>> detector = TemporalPatternDetector()
        >>> patterns = detector.detect_temporal_patterns(
        ...     graph, pattern_type="sequence", min_frequency=2
        ... )
    """

    def __init__(self, **config):
        """
        Initialize temporal pattern detector.

        Sets up the detector with configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        from ..utils.logging import get_logger

        self.logger = get_logger("temporal_pattern_detector")
        self.config = config

        self.logger.debug("Temporal pattern detector initialized")

    def detect_temporal_patterns(
        self,
        graph: Any,
        pattern_type: str = "sequence",
        min_frequency: int = 2,
        time_window: Optional[Any] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Detect temporal patterns in graph.

        This method detects various types of temporal patterns in the knowledge
        graph, including sequences and cycles.

        Args:
            graph: Knowledge graph to analyze
            pattern_type: Type of pattern to detect:
                - "sequence": Sequential relationship patterns
                - "cycle": Cyclic relationship patterns
                - "trend": Trend patterns (planned)
                - "anomaly": Anomaly patterns (planned)
            min_frequency: Minimum frequency/support for pattern (default: 2)
            time_window: Time window for pattern detection (optional)
            **options: Additional detection options (unused)

        Returns:
            list: List of detected pattern dictionaries
        """
        self.logger.info(f"Detecting temporal patterns: {pattern_type}")
        if "gap_tolerance" in options:
            self.config["gap_tolerance"] = options["gap_tolerance"]

        relationships = graph.get("relationships", [])

        # Simple pattern detection
        patterns = []

        if pattern_type == "sequence":
            # Find sequential relationships
            sequences = self._find_sequences(relationships, min_frequency)
            patterns.extend(sequences)
        elif pattern_type == "cycle":
            # Find cyclic patterns
            cycles = self._find_cycles(relationships, min_frequency)
            patterns.extend(cycles)

        return patterns

    def _find_sequences(self, relationships, min_frequency):
        """Find sequential patterns."""
        # Pattern output design:
        # - sequences return dicts with pattern_type/signature/frequency/occurrences
        # - each occurrence stores ordered nodes, ordered edges, and start/end timestamps
        gap_tolerance = self._resolve_gap_tolerance()
        outgoing: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for relationship in relationships:
            outgoing[relationship.get("source")].append(relationship)

        occurrences = defaultdict(list)
        for relationship in relationships:
            sequence = [relationship]
            current = relationship
            while True:
                next_candidates = []
                _, current_end = self._get_axis_bounds(current)
                if current_end is TemporalBound.OPEN:
                    break
                for candidate in outgoing.get(current.get("target"), []):
                    if candidate is current:
                        continue
                    candidate_start, _ = self._get_axis_bounds(candidate)
                    if not isinstance(current_end, datetime) or candidate_start is None:
                        continue
                    gap = candidate_start - current_end
                    if gap < timedelta(0) or gap > gap_tolerance:
                        continue
                    next_candidates.append((candidate_start, candidate))
                if not next_candidates:
                    break
                next_candidates.sort(key=lambda item: item[0])
                current = next_candidates[0][1]
                sequence.append(current)

            if len(sequence) < 2:
                continue

            signature = tuple(
                [sequence[0].get("source")] + [edge.get("target") for edge in sequence]
            )
            occurrences[signature].append(
                {
                    "nodes": list(signature),
                    "edges": [copy.deepcopy(edge) for edge in sequence],
                    "start_time": serialize_temporal_value(self._get_axis_bounds(sequence[0])[0]),
                    "end_time": serialize_temporal_value(self._sequence_end(sequence)),
                }
            )

        return [
            {
                "pattern_type": "sequence",
                "signature": signature,
                "frequency": len(items),
                "occurrences": items,
            }
            for signature, items in occurrences.items()
            if len(items) >= min_frequency
        ]

    def _find_cycles(self, relationships, min_frequency):
        """Find cyclic patterns."""
        # Pattern output design mirrors sequences:
        # - cycles return pattern_type/signature/frequency/occurrences
        # - each occurrence records the ordered cycle nodes, edges, and time span
        outgoing: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for relationship in relationships:
            outgoing[relationship.get("source")].append(relationship)

        occurrences = defaultdict(list)
        for relationship in relationships:
            start_node = relationship.get("source")
            path_edges = [relationship]
            visited_nodes = [start_node, relationship.get("target")]
            current = relationship

            while len(path_edges) <= 6:
                if visited_nodes[-1] == start_node:
                    signature = tuple(visited_nodes)
                    occurrences[signature].append(
                        {
                            "nodes": visited_nodes[:],
                            "edges": [copy.deepcopy(edge) for edge in path_edges],
                            "start_time": serialize_temporal_value(self._get_axis_bounds(path_edges[0])[0]),
                            "end_time": serialize_temporal_value(self._sequence_end(path_edges)),
                        }
                    )
                    break

                next_candidates = []
                _, current_end = self._get_axis_bounds(current)
                for candidate in outgoing.get(visited_nodes[-1], []):
                    candidate_start, _ = self._get_axis_bounds(candidate)
                    if isinstance(current_end, datetime) and candidate_start and self._compare_times(candidate_start, current_end) < 0:
                        continue
                    next_candidates.append((self._sort_key(candidate_start), candidate))
                if not next_candidates:
                    break
                next_candidates.sort(key=lambda item: item[0])
                current = next_candidates[0][1]
                next_target = current.get("target")
                if next_target in visited_nodes[1:-1] and next_target != start_node:
                    break
                path_edges.append(current)
                visited_nodes.append(next_target)

        return [
            {
                "pattern_type": "cycle",
                "signature": signature,
                "frequency": len(items),
                "occurrences": items,
            }
            for signature, items in occurrences.items()
            if len(items) >= min_frequency
        ]

    def _resolve_gap_tolerance(self) -> timedelta:
        gap_tolerance = self.config.get("gap_tolerance", timedelta(days=0))
        if isinstance(gap_tolerance, timedelta):
            return gap_tolerance
        if isinstance(gap_tolerance, (int, float)):
            return timedelta(days=gap_tolerance)
        return timedelta(days=0)

    def _sequence_end(self, edges: List[Dict[str, Any]]) -> Optional[datetime]:
        last_start, last_end = self._get_axis_bounds(edges[-1])
        if isinstance(last_end, datetime):
            return last_end
        return last_start

    def _get_axis_bounds(self, relationship: Dict[str, Any]) -> tuple[Optional[datetime], Optional[datetime | TemporalBound]]:
        normalized = deserialize_relationship_temporal_fields(relationship)
        fact = BiTemporalFact.from_relationship(normalized)
        return fact.valid_from, fact.valid_until

    def _compare_times(self, time1: Optional[datetime], time2: Optional[datetime]) -> int:
        if time1 is None or time2 is None:
            return 0
        return (time1 > time2) - (time1 < time2)

    def _sort_key(self, value: Optional[datetime]) -> datetime:
        return value or datetime.min.replace(tzinfo=timezone.utc)


class TemporalVersionManager:
    """
    Enhanced temporal version management engine with persistent storage.

    This class provides comprehensive version/snapshot management capabilities for knowledge
    graphs, including persistent storage, detailed change tracking, and audit trails.

    Features:
        - Persistent snapshot storage (SQLite or in-memory)
        - Detailed change tracking with entity-level diffs
        - SHA-256 checksums for data integrity
        - Standardized metadata with author attribution
        - Version comparison with backward compatibility
        - Input validation and security features

    Example Usage:
        >>> # In-memory storage
        >>> manager = TemporalVersionManager()
        >>> # Persistent storage
        >>> manager = TemporalVersionManager(storage_path="versions.db")
        >>> snapshot = manager.create_snapshot(graph, "v1.0", 
        ...     author="alice@company.com", description="Initial release")
        >>> versions = manager.list_versions()
        >>> diff = manager.compare_versions("v1.0", "v1.1")
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        snapshot_interval: Optional[int] = None,
        auto_snapshot: bool = False,
        version_strategy: str = "timestamp",
        **config,
    ):
        """
        Initialize enhanced temporal version manager.

        Sets up the version manager with storage backend, snapshot configuration,
        and versioning strategy.

        Args:
            storage_path: Path to SQLite database file for persistent storage.
                         If None, uses in-memory storage (default: None)
            snapshot_interval: Interval for automatic snapshots in seconds
                             (optional, auto_snapshot must be True)
            auto_snapshot: Enable automatic snapshots (default: False)
            version_strategy: Versioning strategy:
                - "timestamp": Use timestamps for version labels (default)
                - "incremental": Use incremental version numbers (planned)
                - "semantic": Use semantic versioning (planned)
            **config: Additional configuration options
        """
        from semantica.change_management import ChangeLogEntry, VersionStorage, InMemoryVersionStorage, SQLiteVersionStorage
        from ..utils.logging import get_logger
        
        self.snapshot_interval = snapshot_interval
        self.auto_snapshot = auto_snapshot
        self.version_strategy = version_strategy
        self.logger = get_logger("temporal_version_manager")
        
        # Initialize storage backend
        if storage_path:
            self.storage = SQLiteVersionStorage(storage_path)
            self.logger.info(f"Initialized with SQLite storage: {storage_path}")
        else:
            self.storage = InMemoryVersionStorage()
            self.logger.info("Initialized with in-memory storage")

    def create_version(
        self,
        graph: Any,
        version_label: Optional[str] = None,
        timestamp: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Create version snapshot of graph.

        This method creates a snapshot/version of the knowledge graph at a
        specific point in time, copying entities and relationships.

        Args:
            graph: Knowledge graph to version (dict with "entities" and "relationships")
            version_label: Optional version label (defaults to "version_{timestamp}")
            timestamp: Timestamp for version (defaults to current time)
            metadata: Additional version metadata dictionary (optional)
            **options: Additional version options (unused)

        Returns:
            dict: Version snapshot containing:
                - label: Version label
                - timestamp: ISO format timestamp
                - entities: Copy of entities list
                - relationships: Copy of relationships list
                - metadata: Version metadata dictionary
        """
        from datetime import datetime

        version_time = timestamp or datetime.now().isoformat()

        version = {
            "label": version_label or f"version_{version_time}",
            "timestamp": version_time,
            "entities": graph.get("entities", []).copy(),
            "relationships": graph.get("relationships", []).copy(),
            "metadata": metadata or {},
        }

        return version

    def compare_versions(
        self,
        v1_label_or_dict,
        v2_label_or_dict,
        comparison_metrics: Optional[List[str]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Compare two graph versions with detailed entity-level differences.

        This method compares two version snapshots and calculates detailed differences
        in entities and relationships, maintaining backward compatibility.

        Args:
            v1_label_or_dict: First version (label string or snapshot dict)
            v2_label_or_dict: Second version (label string or snapshot dict)
            comparison_metrics: List of metrics to calculate (optional, unused)
            **options: Additional comparison options (unused)

        Returns:
            dict: Detailed version comparison results containing:
                - summary: Backward-compatible summary counts
                - entities_added: List of added entities
                - entities_removed: List of removed entities  
                - entities_modified: List of modified entities with changes
                - relationships_added: List of added relationships
                - relationships_removed: List of removed relationships
                - relationships_modified: List of modified relationships
        """
        from ..utils.exceptions import ValidationError
        
        # Handle both label strings and snapshot dictionaries
        if isinstance(v1_label_or_dict, str):
            version1 = self.storage.get(v1_label_or_dict)
            if not version1:
                raise ValidationError(f"Version not found: {v1_label_or_dict}")
        else:
            version1 = v1_label_or_dict
            
        if isinstance(v2_label_or_dict, str):
            version2 = self.storage.get(v2_label_or_dict)
            if not version2:
                raise ValidationError(f"Version not found: {v2_label_or_dict}")
        else:
            version2 = v2_label_or_dict
        
        # Compute detailed diff
        detailed_diff = self._compute_detailed_diff(version1, version2)
        
        # Maintain backward compatibility with summary
        summary = {
            "entities_added": len(detailed_diff["entities_added"]),
            "entities_removed": len(detailed_diff["entities_removed"]),
            "entities_modified": len(detailed_diff["entities_modified"]),
            "relationships_added": len(detailed_diff["relationships_added"]),
            "relationships_removed": len(detailed_diff["relationships_removed"]),
            "relationships_modified": len(detailed_diff["relationships_modified"])
        }
        
        return {
            "version1": version1.get("label", "unknown"),
            "version2": version2.get("label", "unknown"),
            "summary": summary,
            **detailed_diff
        }

    def create_snapshot(
        self, 
        graph: Dict[str, Any], 
        version_label: str, 
        author: str, 
        description: str,
        **options
    ) -> Dict[str, Any]:
        """
        Create and store snapshot with checksum and metadata.
        
        Args:
            graph: Knowledge graph dict with "entities" and "relationships"
            version_label: Version string (e.g., "v1.0")
            author: Email address of the change author
            description: Change description (max 500 chars)
            **options: Additional options
            
        Returns:
            dict: Snapshot with metadata and checksum
            
        Raises:
            ValidationError: If input validation fails
            ProcessingError: If storage operation fails
        """
        from ..change_management import ChangeLogEntry, compute_checksum
        from datetime import datetime
        
        # Validate inputs
        change_entry = ChangeLogEntry(
            timestamp=datetime.now().isoformat(),
            author=author,
            description=description
        )
        
        # Create snapshot
        snapshot = {
            "format_version": "1.0",
            "label": version_label,
            "timestamp": change_entry.timestamp,
            "author": change_entry.author,
            "description": change_entry.description,
            "entities": graph.get("entities", []).copy(),
            "relationships": [
                relationship_to_json_ready(rel)
                for rel in graph.get("relationships", []).copy()
            ],
            "metadata": options.get("metadata", {})
        }
        
        # Compute and add checksum
        snapshot["checksum"] = compute_checksum(snapshot)
        
        # Store snapshot
        try:
            self.storage.save(snapshot)
        except Exception as exc:
            raise ProcessingError(
                "Failed to persist snapshot",
                processing_context={"label": version_label, "author": author},
            ) from exc
        
        self.logger.info(f"Created snapshot '{version_label}' by {author}")
        return snapshot

    def apply_revision(self, snapshot: Dict[str, Any], revision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a temporal revision without deleting the original facts.

        Design note:
        Overlapping retroactive revisions against the same fact are handled by
        superseding the latest matching version and emitting a warning when the
        newly requested valid window overlaps a sibling fact on the same edge
        and relationship type. This preserves all prior versions instead of
        trying to collapse them into a single mutable record.
        """
        from ..change_management import compute_checksum

        revision_time = datetime.now(timezone.utc)
        revision_suffix = self._generate_revision_suffix(revision_time)
        relationships = copy.deepcopy(snapshot.get("relationships", []))
        fact_ids = set(revision.get("fact_ids", []))
        new_valid_from = parse_temporal_value(revision.get("new_valid_from"))
        new_valid_until = parse_temporal_bound(revision.get("new_valid_until"), default=TemporalBound.OPEN)
        revision_type = revision.get("revision_type", "correction")

        revised_relationships = []
        provenance_event = {
            "type": "temporal_revision",
            "revision_type": revision_type,
            "author": revision.get("author"),
            "reason": revision.get("reason"),
            "recorded_at": serialize_temporal_value(revision_time),
            "fact_ids": list(fact_ids),
        }

        for rel in relationships:
            rel_id = rel.get("id") or self._relationship_key(rel)
            if rel_id not in fact_ids:
                revised_relationships.append(rel)
                continue

            original = deserialize_relationship_temporal_fields(rel)
            original["id"] = rel_id
            original["superseded_at"] = serialize_temporal_value(revision_time)
            original.setdefault("provenance", []).append(
                {
                    **provenance_event,
                    "role": "superseded",
                }
            )
            revised_relationships.append(original)

            replacement = copy.deepcopy(rel)
            replacement["id"] = f"{rel_id}__rev__{revision_suffix}"
            replacement["valid_from"] = serialize_temporal_value(new_valid_from)
            replacement["valid_until"] = (
                TemporalBound.OPEN if new_valid_until is TemporalBound.OPEN else serialize_temporal_value(new_valid_until)
            )
            replacement["recorded_at"] = serialize_temporal_value(revision_time)
            replacement["superseded_at"] = TemporalBound.OPEN
            replacement.setdefault("provenance", []).append(
                {
                    **provenance_event,
                    "role": "replacement",
                    "replaces": rel_id,
                }
            )
            self._warn_on_retroactive_overlap(replacement, relationships, revision_type)
            revised_relationships.append(replacement)

        revised_snapshot = copy.deepcopy(snapshot)
        revised_snapshot["relationships"] = [
            relationship_to_json_ready(rel) for rel in revised_relationships
        ]
        base_label = snapshot.get("label", "snapshot")
        original_label = base_label
        revised_label = f"{base_label}__revision__{revision_suffix}"

        original_snapshot = copy.deepcopy(snapshot)
        original_snapshot["label"] = original_label
        original_snapshot_inserted = False
        if self.storage.get(original_label) is None:
            original_snapshot["checksum"] = compute_checksum(
                {k: v for k, v in original_snapshot.items() if k != "checksum"}
            )
            self.storage.save(original_snapshot)
            original_snapshot_inserted = True

        revised_snapshot["label"] = revised_label
        revised_snapshot.setdefault("metadata", {})["revision_event"] = temporal_structure_to_json_ready(provenance_event)
        revised_snapshot["checksum"] = compute_checksum(
            {k: v for k, v in revised_snapshot.items() if k != "checksum"}
        )
        try:
            self.storage.save(revised_snapshot)
        except Exception as exc:
            if original_snapshot_inserted:
                self.storage.delete(original_label)
            raise ProcessingError(
                "Failed to persist revised snapshot",
                processing_context={"original_label": original_label, "revised_label": revised_label},
            ) from exc
        return revised_snapshot
    
    def list_versions(self) -> List[Dict[str, Any]]:
        """
        List all version snapshots.
        
        Returns:
            List of version metadata dictionaries
        """
        return self.storage.list_all()
    
    def get_version(self, label: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve specific version by label.
        
        Args:
            label: Version label to retrieve
            
        Returns:
            Snapshot dictionary or None if not found
        """
        return self.storage.get(label)
    
    def validate_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """
        Validate a snapshot against the v1.0 JSON Schema.

        Returns True when valid. Returns False (never raises) when one or more
        required fields are missing or have the wrong type. Structured error
        details are logged at DEBUG level.

        Required fields: format_version, label, timestamp, author, description,
                         entities, relationships, checksum.
        """
        import json
        import logging
        import os

        required = {
            "format_version": str,
            "label": str,
            "timestamp": str,
            "author": str,
            "description": str,
            "entities": list,
            "relationships": list,
            "checksum": str,
        }

        errors = []
        for field, expected_type in required.items():
            if field not in snapshot:
                errors.append({"field": field, "error": "missing"})
            elif not isinstance(snapshot[field], expected_type):
                errors.append({
                    "field": field,
                    "error": "wrong_type",
                    "expected": expected_type.__name__,
                    "got": type(snapshot[field]).__name__,
                })

        if errors:
            self.logger.debug(f"validate_snapshot failed: {errors}")
            return False
        return True

    def migrate_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upgrade an old-format snapshot (no format_version) to v1.0.

        - Snapshots already at format_version "1.0" are returned unchanged.
        - Missing required fields are populated with None.
        - No data is lost; existing fields are preserved.
        """
        import copy

        result = copy.deepcopy(snapshot)
        if result.get("format_version") == "1.0":
            return result

        result["format_version"] = "1.0"

        optional_defaults = {
            "label": None,
            "timestamp": None,
            "author": None,
            "description": None,
            "entities": None,
            "relationships": None,
            "checksum": None,
        }
        for field, default in optional_defaults.items():
            if field not in result:
                result[field] = default

        return result

    def verify_checksum(self, snapshot: Dict[str, Any]) -> bool:
        """
        Verify the integrity of a snapshot using its checksum.
        
        Args:
            snapshot: Snapshot dictionary with checksum field
            
        Returns:
            True if checksum is valid, False otherwise
        """
        from ..change_management import verify_checksum
        return verify_checksum(snapshot)

    def _compute_detailed_diff(self, version1: Dict[str, Any], version2: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute detailed entity and relationship differences between versions.
        
        Args:
            version1: First version snapshot
            version2: Second version snapshot
            
        Returns:
            Dict with detailed diff information
        """
        entities1 = {e.get("id", str(i)): e for i, e in enumerate(version1.get("entities", []))}
        entities2 = {e.get("id", str(i)): e for i, e in enumerate(version2.get("entities", []))}
        
        relationships1 = {self._relationship_key(r): r for r in version1.get("relationships", [])}
        relationships2 = {self._relationship_key(r): r for r in version2.get("relationships", [])}
        
        # Entity differences
        entity_ids1 = set(entities1.keys())
        entity_ids2 = set(entities2.keys())
        
        entities_added = [entities2[eid] for eid in entity_ids2 - entity_ids1]
        entities_removed = [entities1[eid] for eid in entity_ids1 - entity_ids2]
        
        entities_modified = []
        for eid in entity_ids1 & entity_ids2:
            if entities1[eid] != entities2[eid]:
                changes = self._compute_entity_changes(entities1[eid], entities2[eid])
                entities_modified.append({
                    "id": eid,
                    "before": entities1[eid],
                    "after": entities2[eid],
                    "changes": changes
                })
        
        # Relationship differences
        rel_keys1 = set(relationships1.keys())
        rel_keys2 = set(relationships2.keys())
        
        relationships_added = [relationships2[key] for key in rel_keys2 - rel_keys1]
        relationships_removed = [relationships1[key] for key in rel_keys1 - rel_keys2]
        
        relationships_modified = []
        for key in rel_keys1 & rel_keys2:
            if relationships1[key] != relationships2[key]:
                changes = self._compute_relationship_changes(relationships1[key], relationships2[key])
                relationships_modified.append({
                    "key": key,
                    "before": relationships1[key],
                    "after": relationships2[key],
                    "changes": changes
                })
        
        return {
            "entities_added": entities_added,
            "entities_removed": entities_removed,
            "entities_modified": entities_modified,
            "relationships_added": relationships_added,
            "relationships_removed": relationships_removed,
            "relationships_modified": relationships_modified
        }
    
    def _relationship_key(self, relationship: Dict[str, Any]) -> str:
        """
        Generate a unique key for a relationship.
        
        Args:
            relationship: Relationship dictionary
            
        Returns:
            Unique string key for the relationship
        """
        source = relationship.get("source", "")
        target = relationship.get("target", "")
        rel_type = relationship.get("type", relationship.get("relationship", ""))
        return f"{source}|{rel_type}|{target}"

    def _generate_revision_suffix(self, revision_time: datetime) -> str:
        timestamp_part = revision_time.strftime("%Y%m%dT%H%M%S%fZ")
        return f"{timestamp_part}_{uuid4().hex[:8]}"

    def _warn_on_retroactive_overlap(
        self,
        replacement: Dict[str, Any],
        relationships: List[Dict[str, Any]],
        revision_type: str,
    ) -> None:
        if revision_type != "retroactive":
            return

        query = TemporalGraphQuery(temporal_granularity="second")
        candidate_start, candidate_end = query._get_axis_bounds(replacement, "valid")
        for sibling in relationships:
            if sibling.get("source") != replacement.get("source"):
                continue
            if sibling.get("target") != replacement.get("target"):
                continue
            if sibling.get("type") != replacement.get("type"):
                continue
            sibling_start, sibling_end = query._get_axis_bounds(sibling, "valid")
            if query._range_overlaps_bounds(
                candidate_start or datetime.min.replace(tzinfo=timezone.utc),
                candidate_end if isinstance(candidate_end, datetime) else datetime.max.replace(tzinfo=timezone.utc),
                sibling_start,
                sibling_end,
            ):
                warnings.warn(
                    "Retroactive revision overlaps an existing fact on the same edge.",
                    UserWarning,
                    stacklevel=2,
                )
                return
    
    def _compute_entity_changes(self, entity1: Dict[str, Any], entity2: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute changes between two entity versions.
        
        Args:
            entity1: Original entity
            entity2: Modified entity
            
        Returns:
            Dictionary of changes
        """
        changes = {}
        
        # Check all keys from both entities
        all_keys = set(entity1.keys()) | set(entity2.keys())
        
        for key in all_keys:
            val1 = entity1.get(key)
            val2 = entity2.get(key)
            
            if val1 != val2:
                changes[key] = {"from": val1, "to": val2}
        
        return changes
    
    def _compute_relationship_changes(self, rel1: Dict[str, Any], rel2: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute changes between two relationship versions.
        
        Args:
            rel1: Original relationship
            rel2: Modified relationship
            
        Returns:
            Dictionary of changes
        """
        changes = {}
        
        # Check all keys from both relationships
        all_keys = set(rel1.keys()) | set(rel2.keys())
        
        for key in all_keys:
            val1 = rel1.get(key)
            val2 = rel2.get(key)
            
            if val1 != val2:
                changes[key] = {"from": val1, "to": val2}
        
        return changes


def validate_temporal_consistency(graph: Any) -> TemporalConsistencyReport:
    """Module-level validator entry point required by the temporal query API."""
    return TemporalGraphQuery().validate_temporal_consistency(graph)
