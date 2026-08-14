"""
Knowledge Graph Builder Module

This module provides comprehensive knowledge graph construction capabilities
from extracted entities and relationships, with full support for temporal
knowledge graphs and advanced graph operations.

Key Features:
    - Build knowledge graphs from entities and relationships
    - Temporal knowledge graph support with time-aware edges
    - Entity resolution and deduplication
    - Conflict detection and resolution
    - Temporal snapshots and versioning
    - Neo4j integration for graph storage

Example Usage:
    >>> from semantica.kg import GraphBuilder
    >>> builder = GraphBuilder(merge_entities=True, resolve_conflicts=True)
    >>> graph = builder.build(sources=[{"entities": [...], "relationships": [...]}])  # doctest: +SKIP

Author: Semantica Contributors
License: MIT
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
import time


class GraphBuilder:
    """
    Knowledge graph builder with temporal support.

    • Constructs knowledge graphs from entities and relationships
    • Supports temporal knowledge graphs with time-aware edges
    • Manages node and edge creation with temporal annotations
    • Handles graph structure optimization
    • Supports incremental graph building
    • Enables temporal versioning and snapshots

    Attributes:
        • merge_entities: Whether to merge duplicate entities
        • entity_resolution_strategy: Strategy for entity resolution
        • resolve_conflicts: Whether to resolve conflicts
        • enable_temporal: Enable temporal knowledge graph features
        • temporal_granularity: Time granularity (second, minute, hour, day, etc.)
        • track_history: Track historical changes
        • version_snapshots: Create version snapshots

    Methods:
        • build(): Build knowledge graph from sources
        • add_temporal_edge(): Add edge with temporal validity
        • create_temporal_snapshot(): Create temporal snapshot
        • query_temporal(): Query graph at specific time point
    """

    def __init__(
        self,
        merge_entities=False,
        entity_resolution_strategy="fuzzy",
        resolve_conflicts=True,
        enable_temporal=False,
        temporal_granularity="day",
        track_history=False,
        version_snapshots=False,
        graph_store=None,
        **kwargs,
    ):
        """
        Initialize graph builder.

        Args:
            merge_entities: Whether to merge duplicate entities (default: False, set to True to enable)
                          Note: Entity resolution is typically done in conflict resolution step
            entity_resolution_strategy: Strategy for entity resolution ("fuzzy", "exact", "ml-based")
            resolve_conflicts: Whether to resolve conflicts
            enable_temporal: Enable temporal knowledge graph features
            temporal_granularity: Time granularity ("second", "minute", "hour", "day", "week", "month", "year")
            track_history: Track historical changes to entities/relationships
            version_snapshots: Create version snapshots at intervals
            graph_store: Optional GraphStore instance for persistence
            **kwargs: Additional configuration options
        """
        self.merge_entities = merge_entities
        self.entity_resolution_strategy = entity_resolution_strategy
        self.resolve_conflicts = resolve_conflicts
        self.enable_temporal = enable_temporal
        self.temporal_granularity = temporal_granularity
        self.track_history = track_history
        self.version_snapshots = version_snapshots
        self.graph_store = graph_store
        self.config = kwargs  # Store additional config for extractors
        # Extractors are reused across texts: NERExtractor loads its spaCy model
        # eagerly in __init__, so constructing one per text would reload the
        # model on every source in a multi-document build.
        self._extractor_cache: Dict[Tuple[str, Any], Any] = {}
        # build() resets these per run; seed them here so _extract_from_text
        # is usable on its own instead of raising an AttributeError that the
        # broad except in the extraction path silently swallows.
        self._extraction_stats: Dict[str, int] = {
            "extracted_entities": 0,
            "extracted_relations": 0,
            "extracted_triplets": 0,
        }

        # Initialize logging
        from ..utils.logging import get_logger
        from ..utils.progress_tracker import get_progress_tracker

        self.logger = get_logger("graph_builder")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Initialize entity resolver if entity merging is enabled
        # This helps deduplicate and merge similar entities
        if self.merge_entities:
            from .entity_resolver import EntityResolver

            entity_resolution_config = kwargs.get("entity_resolution", {})
            self.entity_resolver = EntityResolver(
                strategy=self.entity_resolution_strategy, **entity_resolution_config
            )
            self.logger.debug(
                f"Entity resolver initialized with strategy: {self.entity_resolution_strategy}"
            )
        else:
            self.entity_resolver = None
            self.logger.debug("Entity merging disabled, skipping entity resolver")

        # Initialize conflict detector if conflict resolution is enabled
        # This helps detect and resolve conflicting information in the graph
        if self.resolve_conflicts:
            from ..conflicts.conflict_detector import ConflictDetector

            conflict_detection_config = kwargs.get("conflict_detection", {})
            self.conflict_detector = ConflictDetector(**conflict_detection_config)
            self.logger.debug("Conflict detector initialized")
        else:
            self.conflict_detector = None
            self.logger.debug("Conflict resolution disabled")

    def _process_item(self, item: Any, all_entities: List[Any], all_relationships: List[Any], **options):
        """Helper to process a single item and add to entities or relationships list."""
        if isinstance(item, str):
            # Treat string as text for extraction
            self._extract_from_text(item, all_entities, all_relationships, **options)
            return

        if hasattr(item, "text") and (hasattr(item, "label") or hasattr(item, "type")):
            # It's likely an Entity object
            entity_dict = {
                "id": getattr(item, "id", getattr(item, "entity_id", item.text)),
                "name": item.text,
                "type": getattr(item, "label", getattr(item, "type", "UNKNOWN")),
                "confidence": getattr(item, "confidence", 1.0),
                "metadata": getattr(item, "metadata", {})
            }
            all_entities.append(entity_dict)
        elif hasattr(item, "subject") and hasattr(item, "predicate") and hasattr(item, "object"):
            # It's likely a Relation object
            subj = item.subject
            obj = item.object
            subj_id = getattr(subj, "id", getattr(subj, "text", str(subj))) if not isinstance(subj, str) else subj
            obj_id = getattr(obj, "id", getattr(obj, "text", str(obj))) if not isinstance(obj, str) else obj
            rel_dict = {
                "source": subj_id,
                "target": obj_id,
                "type": item.predicate,
                "confidence": getattr(item, "confidence", 1.0),
                "metadata": getattr(item, "metadata", {})
            }
            all_relationships.append(rel_dict)
        elif isinstance(item, dict):
            if "source_id" in item and "source" not in item:
                item["source"] = item["source_id"]
            if "target_id" in item and "target" not in item:
                item["target"] = item["target_id"]
            if "subject" in item and "source" not in item:
                item["source"] = item["subject"]
            if "object" in item and "target" not in item:
                item["target"] = item["object"]
            if "source" in item and not isinstance(item["source"], str):
                src = item["source"]
                item["source"] = getattr(src, "id", getattr(src, "text", str(src)))
            if "target" in item and not isinstance(item["target"], str):
                tgt = item["target"]
                item["target"] = getattr(tgt, "id", getattr(tgt, "text", str(tgt)))
            
            processed = False
            found_something = False
            
            if "entities" in item:
                entities_list = item["entities"]
                if entities_list:
                    if isinstance(entities_list, list):
                        for ent in entities_list:
                            self._process_item(ent, all_entities, all_relationships, **options)
                    else:
                        self._process_item(entities_list, all_entities, all_relationships, **options)
                    found_something = True
                    processed = True
            
            if "relationships" in item:
                rels_list = item["relationships"]
                if rels_list:
                    if isinstance(rels_list, list):
                        for rel in rels_list:
                            self._process_item(rel, all_entities, all_relationships, **options)
                    else:
                        self._process_item(rels_list, all_entities, all_relationships, **options)
                    found_something = True
                    processed = True
            
            if not found_something:
                if "source" in item and "target" in item:
                    all_relationships.append(item)
                    found_something = True
                elif "id" in item or "entity_id" in item or "name" in item:
                    all_entities.append(item)
                    found_something = True
                elif "text" in item and "type" in item:
                    # Entity with text and type fields (common format)
                    # Normalize to standard format
                    entity_dict = item.copy()
                    if "name" not in entity_dict:
                        entity_dict["name"] = entity_dict["text"]
                    if "id" not in entity_dict and "entity_id" not in entity_dict:
                        entity_dict["id"] = entity_dict.get("name") or entity_dict.get("text")
                    all_entities.append(entity_dict)
                    found_something = True
                
                # If still nothing found and has 'text', try extraction
                if not found_something and "text" in item:
                    text = item["text"]
                    self._extract_from_text(text, all_entities, all_relationships, **options)
                    found_something = True
        else:
            # Unknown type
            pass

    def _get_extractor(
        self, kind: str, extractor_cls, method: Union[str, List[str]]
    ):
        """Return a cached extractor for this method, building it on first use.

        Extractors hold no per-text state but are expensive to construct —
        ``NERExtractor(method="ml")`` loads a spaCy model in ``__init__``.
        Keying on kind and method is enough because ``self.config`` is fixed
        for the lifetime of the builder.

        Args:
            kind: Extractor role, one of ``"ner"``, ``"relation"``, ``"triplet"``.
            extractor_cls: Extractor class to construct on a cache miss.
            method: A method name, or a list of them for fallback ordering.
                Lists are converted to tuples for the cache key only; the
                extractor still receives the original value.
        """
        key = (kind, tuple(method) if isinstance(method, list) else method)
        if key not in self._extractor_cache:
            self._extractor_cache[key] = extractor_cls(method=method, **self.config)
        return self._extractor_cache[key]

    def _remap_relationship_endpoints(
        self,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
    ) -> int:
        """Rewrite relationship endpoints after entity resolution.

        Entity merging keeps the canonical entity ID and records the IDs of all
        merged inputs in ``merged_from``.  Relationships are collected before
        resolution, so without this remapping they can continue to reference an
        entity that is no longer present in the graph.

        Returns:
            The number of relationship endpoints that were remapped.
        """
        endpoint_map: Dict[Any, Any] = {}

        for entity in entities:
            if not isinstance(entity, dict):
                continue

            canonical_id = entity.get("id")
            if canonical_id is None:
                canonical_id = entity.get("entity_id")
            if canonical_id is None:
                continue

            # Keep canonical IDs stable and map every source ID retained by the
            # merge operation to the surviving entity.
            try:
                endpoint_map[canonical_id] = canonical_id
            except TypeError:
                # Invalid/unhashable IDs are left for graph validation to report
                # rather than making graph construction fail here.
                continue

            merged_from = entity.get("merged_from") or []
            if isinstance(merged_from, (list, tuple, set)):
                for source_id in merged_from:
                    if source_id is not None:
                        try:
                            endpoint_map[source_id] = canonical_id
                        except TypeError:
                            # Skip invalid aliases while preserving valid ones.
                            continue

        remapped_count = 0
        for relationship in relationships:
            if not isinstance(relationship, dict):
                continue

            for endpoint in ("source", "target"):
                endpoint_id = relationship.get(endpoint)
                try:
                    canonical_id = endpoint_map.get(endpoint_id)
                except TypeError:
                    # Invalid/unhashable endpoints are left for graph validation
                    # to report rather than making graph construction fail here.
                    continue

                if canonical_id is not None and canonical_id != endpoint_id:
                    relationship[endpoint] = canonical_id
                    remapped_count += 1

        if remapped_count:
            self.logger.info(
                "Remapped %d relationship endpoint(s) after entity resolution",
                remapped_count,
            )
        return remapped_count

    def _extract_from_text(self, text: str, all_entities: List[Any], all_relationships: List[Any], **options):
        """Helper to extract knowledge from text using configured methods."""
        if not options.get("extract", True):
            return

        from ..semantic_extract.ner_extractor import NERExtractor
        from ..semantic_extract.relation_extractor import RelationExtractor
        from ..semantic_extract.triplet_extractor import TripletExtractor
        
        # Local extractors by default — raw-text build() must not require a
        # provider, API key, or network access. Pass ner_method="llm" (and the
        # relation/triplet equivalents) to opt into LLM extraction.
        ner_method = options.get("ner_method", "ml")
        relation_method = options.get("relation_method", "pattern")
        triplet_method = options.get("triplet_method", "pattern")
        
        self.logger.info(f"Extracting knowledge from text ({len(text)} chars) using {ner_method}...")
        
        # 1. Extract Entities
        ner = self._get_extractor("ner", NERExtractor, ner_method)
        try:
            entities = ner.extract_entities(text, **options)
            extracted_count = len(entities)
            self._extraction_stats["extracted_entities"] += extracted_count
            self.logger.info(f"Extracted {extracted_count} entities")
            for ent in entities:
                self._process_item(ent, all_entities, all_relationships, **options)
        except Exception as e:
            self.logger.error(f"Entity extraction failed: {e}")
            entities = []
        
        # 2. Extract Relations (if requested)
        # Stays None when relation extraction is skipped or fails, which lets
        # TripletExtractor derive its own relations as before. When we do have
        # them, they are forwarded below so triplets reuse the relations
        # extracted with relation_method rather than re-deriving via
        # triplet_method.
        relations = None
        if options.get("extract_relations", False):
            rel_extractor = self._get_extractor(
                "relation", RelationExtractor, relation_method
            )
            try:
                # Pass entities if available to help relation extraction
                relations = rel_extractor.extract_relations(text, entities=entities, **options)
                extracted_count = len(relations)
                self._extraction_stats["extracted_relations"] += extracted_count
                self.logger.info(f"Extracted {extracted_count} relationships")
                for rel in relations:
                    self._process_item(rel, all_entities, all_relationships, **options)
            except Exception as e:
                self.logger.error(f"Relation extraction failed: {e}")

        # 3. Extract Triplets (if requested)
        if options.get("extract_triplets", True):
            trip_extractor = self._get_extractor(
                "triplet", TripletExtractor, triplet_method
            )
            try:
                triplets = trip_extractor.extract_triplets(
                    text, entities=entities, relations=relations, **options
                )
                extracted_count = len(triplets)
                self._extraction_stats["extracted_triplets"] += extracted_count
                self.logger.info(f"Extracted {extracted_count} triplets")
                for trip in triplets:
                    self._process_item(trip, all_entities, all_relationships, **options)
            except Exception as e:
                self.logger.error(f"Triplet extraction failed: {e}")

    def build(
        self,
        sources: Union[List[Any], Any],
        second_arg: Optional[Any] = None,
        pipeline_id: Optional[str] = None,
        **options,
    ) -> Dict[str, Any]:
        """Build a knowledge graph from one or more sources.

        Args:
            sources: A source or list of sources. Sources may be text,
                pre-extracted objects, or dictionaries containing ``entities``
                and ``relationships``.
            second_arg: An optional relationship list or entity resolver kept
                for backward compatibility.
            pipeline_id: Optional pipeline identifier used for progress
                tracking.
            **options: Additional graph-building options:

                - ``extract`` (bool): Whether to run text extraction when a
                  raw string or ``{"text": ...}`` dict is passed as a source
                  (default: ``True``).
                - ``extract_relations`` (bool): Whether to extract relations
                  during text extraction (default: ``False``).
                - ``extract_triplets`` (bool): Whether to extract triplets
                  during text extraction (default: ``True``).
                - ``ner_method`` (str): NER backend used for text extraction
                  (e.g. ``"ml"``, ``"pattern"``, ``"llm"``; default: ``"ml"``).
                - ``relation_method`` (str): Relation-extraction backend
                  (e.g. ``"pattern"``, ``"llm"``; default: ``"pattern"``).
                - ``triplet_method`` (str): Triplet-extraction backend
                  (e.g. ``"pattern"``, ``"llm"``; default: ``"pattern"``).
                - ``entity_resolver``: An :class:`EntityResolver` instance
                  that overrides the one configured on the builder.
                - ``relationships`` (list): An explicit list of relationships
                  to include in addition to those found in *sources*.

            Raw-text extraction uses local extractors by default and needs no
            provider or API key. To use LLM extraction, pass the methods
            explicitly, e.g. ``ner_method="llm"``.

        Returns:
            A dictionary containing the graph's ``entities``,
            ``relationships``, and build ``metadata``.

        Example:
            >>> builder = GraphBuilder(resolve_conflicts=False)
            >>> graph = builder.build(  # doctest: +SKIP
            ...     {"entities": [{"id": "ada"}], "relationships": []}
            ... )
            >>> graph["metadata"]["num_entities"]  # doctest: +SKIP
            1
        """
        # Handle arguments
        entity_resolver = None
        explicit_relationships = None

        # Check if second_arg is entity_resolver or relationships
        if second_arg is not None:
            if hasattr(second_arg, "resolve"): # Duck typing for EntityResolver
                entity_resolver = second_arg
            elif isinstance(second_arg, list):
                explicit_relationships = second_arg
        
        # Also check options for named arguments
        if "entity_resolver" in options:
            entity_resolver = options.pop("entity_resolver")
        if "relationships" in options:
            explicit_relationships = options.pop("relationships")

        # Check if sources is a dict with entities/relationships (common pattern)
        source_dict = None
        if isinstance(sources, dict) and ("entities" in sources or "relationships" in sources):
            source_dict = sources
            sources = [sources]  # Normalize for tracking
        elif isinstance(sources, list) and len(sources) > 0:
            # Check if first item is a dict with entities/relationships
            first_item = sources[0]
            if isinstance(first_item, dict) and ("entities" in first_item or "relationships" in first_item):
                # If all items are dicts with entities/relationships, merge them
                if all(isinstance(item, dict) and ("entities" in item or "relationships" in item) for item in sources):
                    # Merge all sources into one dict
                    source_dict = {
                        "entities": [],
                        "relationships": []
                    }
                    for item in sources:
                        if "entities" in item:
                            if isinstance(item["entities"], list):
                                source_dict["entities"].extend(item["entities"])
                            else:
                                source_dict["entities"].append(item["entities"])
                        if "relationships" in item:
                            if isinstance(item["relationships"], list):
                                source_dict["relationships"].extend(item["relationships"])
                            else:
                                source_dict["relationships"].append(item["relationships"])
        elif not isinstance(sources, list):
            sources = [sources]

        # Count input relationships for warning if all are dropped
        input_relationships_count = 0
        if isinstance(source_dict, dict):
            rels = source_dict.get("relationships", [])
            if isinstance(rels, list):
                input_relationships_count += len(rels)
            elif rels is not None:
                input_relationships_count += 1
        if explicit_relationships:
            for rel_item in explicit_relationships:
                if isinstance(rel_item, list):
                    input_relationships_count += len(rel_item)
                else:
                    input_relationships_count += 1

        # Track graph building
        build_start_time = time.time()
        
        # Initialize extraction statistics for traceability
        self._extraction_stats = {
            "extracted_entities": 0,
            "extracted_relations": 0,
            "extracted_triplets": 0
        }
        
        tracking_id = self.progress_tracker.start_tracking(
            module="kg",
            submodule="GraphBuilder",
            message=f"Knowledge graph from {len(sources)} source(s)",
            pipeline_id=pipeline_id,
        )

        try:
            self.logger.info(f"Building knowledge graph from {len(sources)} source(s)")

            # Use provided resolver or default instance resolver
            resolver_to_use = entity_resolver or self.entity_resolver

            # Extract entities and relationships from all sources
            all_entities = []
            all_relationships = []

            # Handle dict source with entities/relationships
            if source_dict:
                entities_list = source_dict.get("entities", [])
                relationships_list = source_dict.get("relationships", [])
                
                if entities_list or relationships_list:
                    total_items = len(entities_list) + len(relationships_list)
                    self.progress_tracker.update_tracking(
                        tracking_id,
                        message=f"Processing {len(entities_list)} entities, {len(relationships_list)} relationships ({total_items} total)..."
                    )
                
                # Process entities with progress and ETA
                # Optimize: directly append dictionaries instead of processing each item
                if entities_list:
                    # Track entity processing
                    entity_tracking_id = self.progress_tracker.start_tracking(
                        file=None,
                        module="kg",
                        submodule="GraphBuilder",
                        message=f"Processing {len(entities_list)} entities",
                        pipeline_id=pipeline_id,
                    )
                    
                    # Check if entities are already in dictionary format
                    sample_entity = entities_list[0] if entities_list else None
                    is_dict_format = isinstance(sample_entity, dict) and (
                        "id" in sample_entity or "entity_id" in sample_entity or 
                        "name" in sample_entity or "text" in sample_entity
                    ) and not hasattr(sample_entity, "__dict__") # Ensure it's not a class instance
                    
                    if is_dict_format:
                        # Fast path: directly append dictionaries after normalizing
                        batch_size = max(100, len(entities_list) // 20)
                        for i in range(0, len(entities_list), batch_size):
                            batch = entities_list[i:i + batch_size]
                            for item in batch:
                                # Normalize entity dict format
                                if isinstance(item, dict):
                                    # Ensure required fields exist
                                    entity_dict = item.copy()
                                    if "text" in entity_dict and "name" not in entity_dict:
                                        entity_dict["name"] = entity_dict["text"]
                                    if "id" not in entity_dict and "entity_id" not in entity_dict:
                                        entity_dict["id"] = entity_dict.get("name") or entity_dict.get("text") or str(hash(str(item)))
                                    all_entities.append(entity_dict)
                                else:
                                    # Fallback to _process_item for non-dict items
                                    self._process_item(item, all_entities, all_relationships, **options)
                            
                            processed = min(i + batch_size, len(entities_list))
                            
                            # Update progress with ETA
                            self.progress_tracker.update_progress(
                                entity_tracking_id,
                                processed=processed,
                                total=len(entities_list),
                                message=f"Processing entities... {processed}/{len(entities_list)}"
                            )
                    else:
                        # Slow path: use _process_item for complex objects
                        batch_size = max(100, len(entities_list) // 20)
                        for i in range(0, len(entities_list), batch_size):
                            batch = entities_list[i:i + batch_size]
                            for item in batch:
                                self._process_item(item, all_entities, all_relationships, **options)
                            processed = min(i + batch_size, len(entities_list))
                            
                            # Update progress with ETA
                            self.progress_tracker.update_progress(
                                entity_tracking_id,
                                processed=processed,
                                total=len(entities_list),
                                message=f"Processing entities... {processed}/{len(entities_list)}"
                            )
                    
                    self.progress_tracker.stop_tracking(
                        entity_tracking_id,
                        status="completed",
                        message=f"Processed {len(entities_list)} entities",
                    )
                
                # Process relationships with progress and ETA
                # Optimize: directly append dictionaries instead of processing each item
                if relationships_list:
                    # Track relationship processing
                    rel_tracking_id = self.progress_tracker.start_tracking(
                        file=None,
                        module="kg",
                        submodule="GraphBuilder",
                        message=f"Processing {len(relationships_list)} relationships",
                        pipeline_id=pipeline_id,
                    )
                    
                    sample_rel = relationships_list[0] if relationships_list else None
                    is_dict_format = isinstance(sample_rel, dict) and (
                        ("source" in sample_rel and "target" in sample_rel)
                        or ("source_id" in sample_rel and "target_id" in sample_rel)
                        or ("subject" in sample_rel and "object" in sample_rel)
                    ) and not hasattr(sample_rel, "__dict__")
                    
                    if is_dict_format:
                        # Fast path: directly append dictionaries after normalizing source/target
                        batch_size = max(100, len(relationships_list) // 20)
                        for i in range(0, len(relationships_list), batch_size):
                            batch = relationships_list[i:i + batch_size]
                            for item in batch:
                                if isinstance(item, dict):
                                    rel_dict = item.copy()
                                    if "source_id" in rel_dict and "source" not in rel_dict:
                                        rel_dict["source"] = rel_dict["source_id"]
                                    if "target_id" in rel_dict and "target" not in rel_dict:
                                        rel_dict["target"] = rel_dict["target_id"]
                                    if "subject" in rel_dict and "source" not in rel_dict:
                                        rel_dict["source"] = rel_dict["subject"]
                                    if "object" in rel_dict and "target" not in rel_dict:
                                        rel_dict["target"] = rel_dict["object"]
                                    if "source" in rel_dict and not isinstance(rel_dict["source"], str):
                                        src = rel_dict["source"]
                                        rel_dict["source"] = getattr(src, "id", getattr(src, "text", str(src)))
                                    if "target" in rel_dict and not isinstance(rel_dict["target"], str):
                                        tgt = rel_dict["target"]
                                        rel_dict["target"] = getattr(tgt, "id", getattr(tgt, "text", str(tgt)))
                                    all_relationships.append(rel_dict)
                                else:
                                    # Fallback to _process_item for non-dict items
                                    self._process_item(item, all_entities, all_relationships, **options)
                            
                            processed = min(i + batch_size, len(relationships_list))
                            
                            # Update progress with ETA
                            self.progress_tracker.update_progress(
                                rel_tracking_id,
                                processed=processed,
                                total=len(relationships_list),
                                message=f"Processing relationships... {processed}/{len(relationships_list)}"
                            )
                    else:
                        # Slow path: use _process_item for complex objects
                        batch_size = max(100, len(relationships_list) // 20)
                        for i in range(0, len(relationships_list), batch_size):
                            batch = relationships_list[i:i + batch_size]
                            for item in batch:
                                self._process_item(item, all_entities, all_relationships, **options)
                            processed = min(i + batch_size, len(relationships_list))
                            
                            # Update progress with ETA
                            self.progress_tracker.update_progress(
                                rel_tracking_id,
                                processed=processed,
                                total=len(relationships_list),
                                message=f"Processing relationships... {processed}/{len(relationships_list)}"
                            )
                    
                    self.progress_tracker.stop_tracking(
                        rel_tracking_id,
                        status="completed",
                        message=f"Processed {len(relationships_list)} relationships",
                    )
            else:
                # Process sources (which might be entities)
                for source in sources:
                    if isinstance(source, list):
                         # List of items (could be entities, relations, or mixed)
                        for item in source:
                            self._process_item(item, all_entities, all_relationships, **options)
                    else:
                        self._process_item(source, all_entities, all_relationships, **options)

            # Process explicit relationships if provided
            if explicit_relationships:
                for rel_item in explicit_relationships:
                    if isinstance(rel_item, list):
                        for item in rel_item:
                             self._process_item(item, all_entities, all_relationships, **options)
                    else:
                        self._process_item(rel_item, all_entities, all_relationships, **options)

            self.logger.debug(
                f"Extracted {len(all_entities)} entities and "
                f"{len(all_relationships)} relationships from sources"
            )

            # Resolve entities (deduplicate and merge) if resolver is available
            resolved_entities = all_entities
            if resolver_to_use and all_entities:
                # For large entity sets, entity resolution can be slow
                # Show progress and allow skipping if too slow
                if len(all_entities) > 1000:
                    self.logger.info(
                        "Resolving %d entities (this may take a while for large sets)...",
                        len(all_entities),
                    )
                else:
                    self.logger.info("Resolving %d entities...", len(all_entities))
                
                self.logger.info(
                    f"Resolving {len(all_entities)} entities using {self.entity_resolution_strategy} strategy"
                )
                resolution_start = time.time()
                resolved_entities = resolver_to_use.resolve_entities(all_entities)
                resolution_time = time.time() - resolution_start
                self.logger.info(
                    "Resolved to %d unique entities (%.2fs)",
                    len(resolved_entities),
                    resolution_time,
                )
                self.logger.info(
                    f"Entity resolution complete: {len(all_entities)} -> {len(resolved_entities)} unique entities"
                )

            # Relationships were collected before entity resolution. Rewrite
            # endpoints only when resolution produced merged entity IDs.
            if resolver_to_use:
                has_merged_entities = any(
                    isinstance(entity, dict) and entity.get("merged_from")
                    for entity in resolved_entities
                )
                if has_merged_entities:
                    self._remap_relationship_endpoints(resolved_entities, all_relationships)

            if input_relationships_count > 0 and len(all_relationships) == 0:
                warning_msg = (
                    f"All relationships were dropped during graph building: "
                    f"{input_relationships_count} input relationships, 0 in final graph"
                )
                self.logger.warning(warning_msg)

            # Build graph structure
            self.logger.debug("Building graph structure...")
            structure_start = time.time()
            graph = {
                "entities": resolved_entities,
                "relationships": all_relationships,
                "metadata": {
                    "num_entities": len(resolved_entities),
                    "num_relationships": len(all_relationships),
                    "temporal_enabled": self.enable_temporal,
                    "timestamp": self._get_timestamp(),
                    "entity_resolution_applied": resolver_to_use is not None,
                },
            }
            structure_time = time.time() - structure_start
            self.logger.debug("Graph structure built in %.2fs", structure_time)

            # Persist to GraphStore if available
            if self.graph_store:
                self.logger.info("Persisting knowledge graph to GraphStore")
                self.progress_tracker.update_tracking(
                    tracking_id, message="Persisting to GraphStore..."
                )
                
                store_start = time.time()
                # Add nodes
                node_count = self.graph_store.add_nodes(resolved_entities)
                node_time = time.time() - store_start
                self.logger.info("Added %d nodes (%.2fs)", node_count, node_time)
                
                # Prepare edges for add_edges (expects source_id, target_id, type)
                edge_prep_start = time.time()
                formatted_edges = []
                for rel in all_relationships:
                    formatted_edges.append({
                        "source_id": rel.get("source"),
                        "target_id": rel.get("target"),
                        "type": rel.get("type", "RELATED_TO"),
                        "properties": rel.get("metadata", {})
                    })
                edge_prep_time = time.time() - edge_prep_start
                
                edge_start = time.time()
                edge_count = self.graph_store.add_edges(formatted_edges)
                edge_time = time.time() - edge_start
                total_store_time = time.time() - store_start
                self.logger.info("Added %d edges (%.2fs)", edge_count, edge_time)
                self.logger.info(
                    "GraphStore persistence complete in %.2fs — %d nodes, %d edges",
                    total_store_time, node_count, edge_count,
                )

            # Detect and resolve conflicts if conflict detector is available
            if self.conflict_detector:
                self.logger.debug("Detecting conflicts in graph")
                # Pass only entities to detect_conflicts as it expects List[Dict]
                detected_conflicts = self.conflict_detector.detect_conflicts(graph["entities"])

                if detected_conflicts:
                    conflict_count = len(detected_conflicts)
                    self.logger.warning(
                        f"Detected {conflict_count} conflict(s) in graph"
                    )

                    # Attempt to resolve conflicts
                    resolution_result = self.conflict_detector.resolve_conflicts(
                        detected_conflicts
                    )
                    resolved_count = resolution_result.get("resolved_count", 0)

                    if resolved_count > 0:
                        self.logger.info(
                            f"Successfully resolved {resolved_count} out of {conflict_count} conflict(s)"
                        )
                    else:
                        self.logger.warning("No conflicts were automatically resolved")

            # Log final graph statistics
            total_build_time = time.time() - build_start_time
            self.logger.info(
                f"Knowledge graph built successfully: "
                f"{len(resolved_entities)} entities, {len(all_relationships)} relationships"
            )
            
            self.logger.info(
                "Extraction statistics — entities: %d, relationships: %d, triplets: %d",
                self._extraction_stats["extracted_entities"],
                self._extraction_stats["extracted_relations"],
                self._extraction_stats["extracted_triplets"],
            )
            self.logger.info(
                "Knowledge graph build complete — entities: %d, relationships: %d, time: %.2fs",
                len(resolved_entities),
                len(all_relationships),
                total_build_time,
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Built graph with {len(resolved_entities)} entities, {len(all_relationships)} relationships",
            )
            return graph

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def build_single_source(
        self,
        kg_data: Dict[str, Any],
        pipeline_id: Optional[str] = None,
        **options,
    ) -> Dict[str, Any]:
        """Build a knowledge graph from a single source dictionary.

        Args:
            kg_data: Source data containing entities, relationships, or both.
            pipeline_id: Optional pipeline identifier used for progress
                tracking.
            **options: Additional options forwarded to :meth:`build`.

        Returns:
            A dictionary containing the graph's ``entities``,
            ``relationships``, and build ``metadata``.

        Example:
            >>> builder = GraphBuilder(resolve_conflicts=False)
            >>> graph = builder.build_single_source(  # doctest: +SKIP
            ...     {"entities": [{"id": "ada"}], "relationships": []}
            ... )
            >>> len(graph["entities"])  # doctest: +SKIP
            1
        """
        return self.build(kg_data, pipeline_id=pipeline_id, **options)

    def add_temporal_edge(
        self,
        graph,
        source,
        target,
        relationship,
        valid_from=None,
        valid_until=None,
        temporal_metadata=None,
        **kwargs,
    ):
        """Add an edge with temporal validity information to a graph.

        Args:
            graph: Mutable knowledge-graph dictionary to update.
            source: Identifier of the source entity or node.
            target: Identifier of the target entity or node.
            relationship: Relationship type for the edge.
            valid_from: Start of the validity period. Accepts a datetime or
                ISO-formatted string; defaults to the current time.
            valid_until: End of the validity period, or ``None`` for an
                ongoing relationship.
            temporal_metadata: Optional metadata such as timezone or
                precision information.
            **kwargs: Additional properties to include on the edge.

        Returns:
            The temporal edge dictionary appended to the graph's
            ``relationships`` list.

        Example:
            >>> builder = GraphBuilder(resolve_conflicts=False)
            >>> graph = {"entities": [], "relationships": []}
            >>> edge = builder.add_temporal_edge(  # doctest: +SKIP
            ...     graph, "ada", "analytical-engine", "DESIGNED"
            ... )
            >>> edge["type"]  # doctest: +SKIP
            'DESIGNED'
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="kg",
            submodule="GraphBuilder",
            message=f"Adding temporal edge: {source} -{relationship}-> {target}",
        )

        try:
            self.logger.info(
                f"Adding temporal edge: {source} -{relationship}-> {target}"
            )

            # Parse temporal information
            valid_from = self._parse_time(valid_from) or self._get_timestamp()
            valid_until = self._parse_time(valid_until) if valid_until else None

            # Create edge with temporal information
            edge = {
                "source": source,
                "target": target,
                "type": relationship,
                "valid_from": valid_from,
                "valid_until": valid_until,
                "temporal_metadata": temporal_metadata or {},
                **kwargs,
            }

            # Add to graph
            if "relationships" not in graph:
                graph["relationships"] = []
            graph["relationships"].append(edge)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Added temporal edge: {source} -{relationship}-> {target}",
            )
            return edge

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def create_temporal_snapshot(
        self, graph, timestamp=None, snapshot_name=None, **options
    ):
        """Create a snapshot of a graph at a specific point in time.

        Args:
            graph: Knowledge graph whose entities and relationships will be
                copied into the snapshot.
            timestamp: Snapshot time, or ``None`` to use the current time.
            snapshot_name: Optional human-readable snapshot name.
            **options: Additional snapshot options reserved for extensions.

        Returns:
            A snapshot dictionary containing the name, timestamp, all copied
            entities, relationships valid at the timestamp, and summary
            metadata.

        Example:
            >>> builder = GraphBuilder(resolve_conflicts=False)
            >>> snapshot = builder.create_temporal_snapshot(  # doctest: +SKIP
            ...     {"entities": [{"id": "ada"}], "relationships": []},
            ...     timestamp="2026-01-01T00:00:00",
            ...     snapshot_name="new-year",
            ... )
            >>> snapshot["name"]  # doctest: +SKIP
            'new-year'
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="kg",
            submodule="GraphBuilder",
            message=f"Creating temporal snapshot: {snapshot_name or 'unnamed'}",
        )

        try:
            self.logger.info(
                f"Creating temporal snapshot: {snapshot_name or 'unnamed'}"
            )

            snapshot_time = self._parse_time(timestamp) or self._get_timestamp()

            self.progress_tracker.update_tracking(
                tracking_id, message="Filtering entities and relationships..."
            )

            # Filter entities and relationships valid at snapshot time
            entities = []
            relationships = []

            # Get all entities
            if "entities" in graph:
                entities = graph["entities"].copy()

            # Filter relationships valid at snapshot time
            if "relationships" in graph:
                for rel in graph["relationships"]:
                    valid_from = self._parse_time(rel.get("valid_from"))
                    valid_until = self._parse_time(rel.get("valid_until"))

                    # Check if relationship is valid at snapshot time
                    if (
                        valid_from
                        and self._compare_times(snapshot_time, valid_from) < 0
                    ):
                        continue
                    if (
                        valid_until
                        and self._compare_times(snapshot_time, valid_until) > 0
                    ):
                        continue

                    relationships.append(rel)

            snapshot = {
                "name": snapshot_name or f"snapshot_{snapshot_time}",
                "timestamp": snapshot_time,
                "entities": entities,
                "relationships": relationships,
                "metadata": {
                    "num_entities": len(entities),
                    "num_relationships": len(relationships),
                    "snapshot_time": snapshot_time,
                },
            }

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created snapshot with {len(entities)} entities, {len(relationships)} relationships",
            )
            return snapshot

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def query_temporal(
        self,
        graph,
        query,
        at_time=None,
        time_range=None,
        temporal_window=None,
        **options,
    ):
        """Query a graph at a specific time or over a time range.

        Args:
            graph: Knowledge graph to query.
            query: Query text to record in the result. The current
                implementation does not interpret it or filter the graph.
            at_time: Optional point in time at which to query the graph.
            time_range: Optional ``(start, end)`` time range. The graph is
                evaluated at the end of the range.
            temporal_window: Optional temporal-window value reserved for
                query-engine integrations.
            **options: Additional query options reserved for extensions.

        Returns:
            A dictionary containing the query, temporal context, entities and
            relationships from the selected graph or snapshot, and graph
            metadata.

        Example:
            >>> builder = GraphBuilder(resolve_conflicts=False)
            >>> result = builder.query_temporal(  # doctest: +SKIP
            ...     {"entities": [{"id": "ada"}], "relationships": []},
            ...     "MATCH (n) RETURN n",
            ... )
            >>> result["entities"][0]["id"]  # doctest: +SKIP
            'ada'
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="kg",
            submodule="GraphBuilder",
            message=f"Executing temporal query: {query[:50]}...",
        )

        try:
            self.logger.info(f"Executing temporal query: {query[:50]}...")

            self.progress_tracker.update_tracking(
                tracking_id, message="Creating temporal snapshot for query..."
            )

            # Create snapshot for query time
            if at_time:
                snapshot = self.create_temporal_snapshot(graph, timestamp=at_time)
            elif time_range:
                start_time, end_time = time_range
                # Query at end time
                snapshot = self.create_temporal_snapshot(graph, timestamp=end_time)
            else:
                # Use current graph
                snapshot = graph

            self.progress_tracker.update_tracking(
                tracking_id, message="Executing query..."
            )

            # Basic query execution (simplified)
            # In a real implementation, this would use a proper query engine
            results = {
                "query": query,
                "timestamp": at_time or (time_range[1] if time_range else None),
                "entities": snapshot.get("entities", []),
                "relationships": snapshot.get("relationships", []),
                "metadata": snapshot.get("metadata", {}),
            }

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Query executed: {len(results.get('entities', []))} entities, {len(results.get('relationships', []))} relationships",
            )
            return results

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def load_from_neo4j(
        self,
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password",
        database="neo4j",
        enable_temporal=False,
        temporal_property="valid_time",
        **kwargs,
    ):
        """Load a knowledge graph from a Neo4j database.

        Args:
            uri: Neo4j connection URI.
            username: Neo4j username.
            password:
                Authentication credential supplied for the Neo4j user.
            database: Neo4j database name.
            enable_temporal: Whether to read temporal relationship data.
            temporal_property: Relationship property containing temporal
                data.
            **kwargs: Additional connection options reserved for extensions.

        Returns:
            A dictionary containing loaded entities, relationships, and
            source metadata.

        Raises:
            ImportError: If the Neo4j driver is unavailable.

        Example:
            >>> import os
            >>> builder = GraphBuilder(resolve_conflicts=False)
            >>> graph = builder.load_from_neo4j(  # doctest: +SKIP
            ...     "bolt://localhost:7687",
            ...     "neo4j",
            ...     os.environ["NEO4J_PASSWORD"],
            ... )
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="kg",
            submodule="GraphBuilder",
            message=f"Loading graph from Neo4j: {uri}",
        )

        try:
            self.logger.info(f"Loading graph from Neo4j: {uri}")

            from neo4j import GraphDatabase

            self.progress_tracker.update_tracking(
                tracking_id, message="Connecting to Neo4j..."
            )
            driver = GraphDatabase.driver(uri, auth=(username, password))

            with driver.session(database=database) as session:
                # Load nodes
                self.progress_tracker.update_tracking(
                    tracking_id, message="Loading nodes from Neo4j..."
                )
                nodes_result = session.run("MATCH (n) RETURN n")
                entities = []
                for record in nodes_result:
                    node = record["n"]
                    entity = {
                        "id": str(node.id),
                        "type": list(node.labels)[0] if node.labels else "Entity",
                        "properties": dict(node),
                    }
                    entities.append(entity)

                # Load relationships
                self.progress_tracker.update_tracking(
                    tracking_id, message="Loading relationships from Neo4j..."
                )
                rels_result = session.run("MATCH (a)-[r]->(b) RETURN a, r, b")
                relationships = []
                for record in rels_result:
                    source = record["a"]
                    rel = record["r"]
                    target = record["b"]

                    relationship = {
                        "source": str(source.id),
                        "target": str(target.id),
                        "type": rel.type,
                        "properties": dict(rel),
                    }

                    # Add temporal information if enabled
                    if enable_temporal and temporal_property in rel:
                        relationship["valid_from"] = rel[temporal_property]

                    relationships.append(relationship)

            driver.close()

            graph = {
                "entities": entities,
                "relationships": relationships,
                "metadata": {
                    "source": "neo4j",
                    "uri": uri,
                    "database": database,
                    "temporal_enabled": enable_temporal,
                },
            }

            self.logger.info(
                f"Loaded {len(entities)} entities and {len(relationships)} relationships from Neo4j"
            )
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Loaded {len(entities)} entities and {len(relationships)} relationships from Neo4j",
            )
            return graph

        except (ImportError, OSError):
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message="neo4j library not available"
            )
            raise ImportError(
                "neo4j library not available. Install with: pip install neo4j"
            )
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            self.logger.error(f"Error loading from Neo4j: {e}")
            raise

    def _get_timestamp(self) -> str:
        """
        Get current timestamp in ISO format.

        Returns:
            ISO format timestamp string (e.g., "2024-01-15T10:30:00")
        """
        return datetime.now().isoformat()

    def _parse_time(
        self, time_value: Optional[Union[str, datetime, Any]]
    ) -> Optional[str]:
        """
        Parse time value to ISO format string.

        This method handles various time input formats and converts them
        to a standardized ISO format string for temporal operations.

        Args:
            time_value: Time value in various formats:
                - None: Returns None
                - str: ISO format string (returned as-is)
                - datetime: Converted to ISO string
                - Other: Converted to string

        Returns:
            ISO format timestamp string or None
        """
        if time_value is None:
            return None

        # Already a string - assume it's in correct format
        if isinstance(time_value, str):
            return time_value

        # datetime object - convert to ISO string
        if isinstance(time_value, datetime):
            return time_value.isoformat()

        # Other types - convert to string
        return str(time_value)

    def _compare_times(self, time1: Optional[str], time2: Optional[str]) -> int:
        """
        Compare two time strings.

        This method performs lexicographic comparison of ISO format time strings.
        Returns -1 if time1 < time2, 0 if equal, 1 if time1 > time2.

        Args:
            time1: First time string (ISO format)
            time2: Second time string (ISO format)

        Returns:
            Comparison result: -1, 0, or 1
        """
        # Handle None values
        if time1 is None or time2 is None:
            return 0

        # Simple lexicographic comparison works for ISO format strings
        # ISO format: YYYY-MM-DDTHH:MM:SS ensures correct string comparison
        if time1 < time2:
            return -1
        elif time1 > time2:
            return 1
        else:
            return 0
