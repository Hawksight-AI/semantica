"""
Unified Provenance Manager

This module provides the central ProvenanceManager class that consolidates
provenance tracking from multiple Semantica modules:
    - kg.ProvenanceTracker (entity/relationship tracking)
    - split.ProvenanceTracker (chunk tracking)
    - conflicts.SourceTracker (source tracking)

The ProvenanceManager provides a unified API for all provenance operations
while maintaining backward compatibility with existing tracker interfaces.

Features:
    - W3C PROV-O compliant tracking
    - Entity and relationship tracking
    - Chunk provenance tracking
    - Source and property tracking
    - Complete lineage tracing
    - Multiple storage backends
    - Integrity verification
    - Batch operations

Author: Semantica Contributors
License: MIT
"""

from typing import Optional, List, Dict, Any, Union
from collections.abc import Mapping
from datetime import datetime
from contextlib import contextmanager
import copy
import json
import threading

from .schemas import ProvenanceEntry, SourceReference
from .storage import ProvenanceStorage, InMemoryStorage, SQLiteStorage
from .integrity import compute_checksum, verify_checksum


@contextmanager
def default_storage_path(path: Optional[str]):
    """
    Context manager for temporarily setting ProvenanceManager._default_storage_path.
    Guarantees restoration to the previous value on exit (safe for tests).
    """
    with ProvenanceManager.default_storage_path(path):
        yield


class ProvenanceManager:
    """
    Unified provenance tracking manager.
    
    Consolidates and enhances provenance tracking from:
    - kg.ProvenanceTracker: Entity/relationship tracking with temporal info
    - split.ProvenanceTracker: Chunk tracking with parent-child relationships
    - conflicts.SourceTracker: Source tracking with credibility scores
    
    Example:
        >>> # Basic usage
        >>> prov_mgr = ProvenanceManager()
        >>> prov_mgr.track_entity("entity_1", source="doc_1")
        >>> 
        >>> # With persistent storage
        >>> prov_mgr = ProvenanceManager(storage_path="provenance.db")
        >>> 
        >>> # Trace lineage
        >>> lineage = prov_mgr.get_lineage("entity_1")
    """
    
    _default_storage_path: Optional[str] = None
    _lock = threading.RLock()
    _path_stack: List[Optional[str]] = []

    @classmethod
    def set_default_storage_path(cls, path: Optional[str]) -> None:
        """Set a global default storage path for all new instances."""
        with cls._lock:
            cls._default_storage_path = path

    @classmethod
    @contextmanager
    def default_storage_path(cls, path: Optional[str]):
        """
        Context manager for temporarily setting the global default storage path.
        Guarantees restoration to the previous value on exit (safe for tests).
        """
        cls._lock.acquire()
        try:
            cls._path_stack.append(cls._default_storage_path)
            cls._default_storage_path = path
            yield
        finally:
            cls._default_storage_path = (
                cls._path_stack.pop() if cls._path_stack else None
            )
            cls._lock.release()
    
    def __init__(
        self,
        storage: Optional[ProvenanceStorage] = None,
        storage_path: Optional[str] = None,
        config: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialize provenance manager.
        
        Args:
            storage: Custom storage backend (optional)
            storage_path: Path to SQLite database (optional, uses in-memory if None)
            config: Configuration dictionary or mapping (optional)
        """
        if storage:
            self.storage = storage
            return

        if not storage_path and config:
            if isinstance(config, Mapping):
                prov_config = config.get("provenance", {})
                prov_has_path = (
                    isinstance(prov_config, Mapping)
                    and "storage_path" in prov_config
                )
                if prov_has_path:
                    storage_path = prov_config.get("storage_path")
                elif "storage_path" in config:
                    storage_path = config.get("storage_path")

        if not storage_path:
            with self._lock:
                storage_path = self._default_storage_path

        if storage_path:
            self.storage = SQLiteStorage(storage_path)
        else:
            self.storage = InMemoryStorage()

    def _save_entry(self, entry: ProvenanceEntry) -> ProvenanceEntry:
        """Compute checksum, store entry persistently, and gracefully ignore storage errors."""
        entry.checksum = compute_checksum(entry)
        
        try:
            self.storage.store(entry)
        except Exception:
            pass  # Graceful failure - don't break main functionality
        
        return entry
    
    # === Entity Tracking (from kg.ProvenanceTracker) ===
    
    def track_entity(
        self,
        entity_id: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ProvenanceEntry:
        """
        Track entity provenance (kg.ProvenanceTracker compatible).
        
        Args:
            entity_id: Entity identifier
            source: Source identifier (document ID, DOI, file path)
            metadata: Optional metadata dictionary
            **kwargs: Additional fields (confidence, source_location, etc.)
            
        Returns:
            ProvenanceEntry object
            
        Example:
            >>> prov_mgr.track_entity(
            ...     entity_id="entity_1",
            ...     source="DOI:10.1371/journal.pone.0023601",
            ...     metadata={"confidence": 0.92}
            ... )
        """
        # Validate entity_id
        if entity_id is None:
            raise ValueError("entity_id cannot be None")
        if not isinstance(entity_id, str):
            raise TypeError(f"entity_id must be a string, got {type(entity_id).__name__}")
        
        # Check if entity already exists
        existing = self.storage.retrieve(entity_id)
        parent_id = kwargs.get("parent_entity_id")

        # If caller declared an explicit parent via metadata, honor it
        # (unless parent_entity_id was already passed directly)
        if not parent_id and metadata and isinstance(metadata, Mapping):
            derived_from = metadata.get("derived_from")
            if derived_from and isinstance(derived_from, str):
                parent_id = derived_from

        # If source is a known entity, link it as parent (unless parent already set)
        if not parent_id and source and isinstance(source, str):
            try:
                # Check if source exists in storage
                # trace_lineage is cheaper than retrieve for just checking existence? Or retrieve?
                # retrieve returns the *latest* entry for that ID
                source_entity = self.storage.retrieve(source)
                if source_entity:
                    parent_id = source
            except Exception:
                pass

        # Track whether the caller explicitly supplied a parent link (via
        # parent_entity_id kwarg, metadata["derived_from"], or source-as-
        # known-entity-id resolution) BEFORE the history-preservation block
        # below. If they did, that explicit value should not be silently
        # overwritten by the auto-generated history pointer (#742).
        explicit_parent_supplied = parent_id is not None

        # If entity exists, preserve history by archiving the old state
        archived_history_id = None
        if existing:
            # Create a history entry for the previous state
            # Use timestamp or counter for uniqueness
            history_entry = copy.deepcopy(existing)
            history_id = f"{entity_id}:v:{existing.last_updated}"
            
            # Ensure unique ID if update happens same second
            if self.storage.retrieve(history_id):
                 history_id = f"{history_id}:{datetime.utcnow().microsecond}"
            
            history_entry.entity_id = history_id
            
            # Store the history entry
            try:
                self.storage.store(history_entry)
                archived_history_id = history_id
                # Link new entry to this history entry — but only when the
                # caller didn't explicitly supply a new parent on this call.
                # An explicit parent_entity_id (or derived_from on branches
                # that support it) is an intentional override signal and must
                # not be silently replaced by internal bookkeeping (#742).
                if not explicit_parent_supplied:
                    parent_id = history_id
            except Exception:
                pass # If history archiving fails, proceed with update but lose history (graceful degradation)

        entry = ProvenanceEntry(
            entity_id=entity_id,
            entity_type=kwargs.get("entity_type", "entity"),
            activity_id=kwargs.get("activity_id", "entity_tracking"),
            source_document=source,
            source_location=kwargs.get("source_location"),
            source_quote=kwargs.get("source_quote"),
            confidence=kwargs.get("confidence", 1.0),
            metadata=metadata or {},
            first_seen=existing.first_seen if existing else datetime.utcnow().isoformat(),
            last_updated=datetime.utcnow().isoformat(),
            parent_entity_id=parent_id,  # Link to history or explicit parent
            used_entities=list(kwargs.get("used_entities", [])),
        )

        # Make the archived history entry discoverable via trace_lineage()'s
        # BFS over used_entities — this ensures the previous version remains
        # reachable in the lineage chain when explicit_parent_supplied is True
        # and parent_entity_id points to the caller's explicit parent rather
        # than the history pointer. When no explicit parent was supplied,
        # parent_entity_id already IS archived_history_id, so appending it
        # here too would duplicate the same id in both fields (#742 follow-up).
        if archived_history_id and explicit_parent_supplied:
            entry.used_entities.append(archived_history_id)
        
        return self._save_entry(entry)
    
    def track_relationship(
        self,
        relationship_id: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ProvenanceEntry:
        """
        Track relationship provenance (kg.ProvenanceTracker compatible).
        
        Args:
            relationship_id: Relationship identifier
            source: Source identifier
            metadata: Optional metadata dictionary
            **kwargs: Additional fields
            
        Returns:
            ProvenanceEntry object
            
        Example:
            >>> prov_mgr.track_relationship(
            ...     relationship_id="rel_1",
            ...     source="doc_1",
            ...     metadata={"type": "founded"}
            ... )
        """
        entry = ProvenanceEntry(
            entity_id=relationship_id,
            entity_type="relationship",
            activity_id=kwargs.get("activity_id", "relationship_tracking"),
            source_document=source,
            source_location=kwargs.get("source_location"),
            confidence=kwargs.get("confidence", 1.0),
            metadata=metadata or {},
            first_seen=datetime.utcnow().isoformat(),
            last_updated=datetime.utcnow().isoformat()
        )
        
        return self._save_entry(entry)
    
    # === Chunk Tracking (from split.ProvenanceTracker) ===
    
    def track_chunk(
        self,
        chunk_id: str,
        source_document: str,
        source_path: Optional[str] = None,
        start_index: int = 0,
        end_index: int = 0,
        parent_chunk_id: Optional[str] = None,
        **metadata
    ) -> ProvenanceEntry:
        """
        Track chunk provenance (split.ProvenanceTracker compatible).
        
        Args:
            chunk_id: Chunk identifier
            source_document: Source document identifier
            source_path: Path to source document
            start_index: Start character index
            end_index: End character index
            parent_chunk_id: Parent chunk ID (if chunk was split)
            **metadata: Additional metadata
            
        Returns:
            ProvenanceEntry object
            
        Example:
            >>> prov_mgr.track_chunk(
            ...     chunk_id="chunk_1",
            ...     source_document="doc_1",
            ...     source_path="/path/to/doc.pdf",
            ...     start_index=0,
            ...     end_index=500
            ... )
        """
        entry = ProvenanceEntry(
            entity_id=chunk_id,
            entity_type="chunk",
            activity_id="chunking",
            source_document=source_document,
            source_location=source_path,
            start_index=start_index,
            end_index=end_index,
            parent_entity_id=parent_chunk_id,
            metadata=metadata,
            timestamp=datetime.utcnow().isoformat()
        )
        
        return self._save_entry(entry)
    
    # === Source Tracking (from conflicts.SourceTracker) ===
    
    def track_property_source(
        self,
        entity_id: str,
        property_name: str,
        value: Any,
        source: SourceReference,
        **metadata
    ) -> ProvenanceEntry:
        """
        Track property source (conflicts.SourceTracker compatible).
        
        Args:
            entity_id: Entity identifier
            property_name: Property name
            value: Property value
            source: SourceReference object
            **metadata: Additional metadata
            
        Returns:
            ProvenanceEntry object
            
        Example:
            >>> source = SourceReference(
            ...     document="DOI:10.1038/...",
            ...     page=4,
            ...     confidence=0.92
            ... )
            >>> prov_mgr.track_property_source(
            ...     entity_id="entity_1",
            ...     property_name="biomass_increase",
            ...     value="463%",
            ...     source=source
            ... )
        """
        entry = ProvenanceEntry(
            entity_id=f"{entity_id}_{property_name}",
            entity_type="property",
            activity_id="property_tracking",
            source_document=source.document,
            source_location=f"page_{source.page}" if source.page else source.section,
            confidence=source.confidence,
            credibility=source.metadata.get("credibility"),
            metadata={
                "entity_id": entity_id,
                "property_name": property_name,
                "value": value,
                **metadata,
                **source.metadata
            },
            timestamp=datetime.utcnow().isoformat()
        )
        
        return self._save_entry(entry)
    
    # === Batch Operations ===
    
    def track_entities_batch(
        self,
        entities: List[Dict[str, Any]],
        source: str,
        **metadata
    ) -> int:
        """
        Track multiple entities in batch.
        
        Args:
            entities: List of entity dictionaries with 'id' key
            source: Source identifier
            **metadata: Metadata to apply to all entities
            
        Returns:
            Number of entities tracked
            
        Example:
            >>> entities = [
            ...     {"id": "entity_1", "confidence": 0.9},
            ...     {"id": "entity_2", "confidence": 0.85}
            ... ]
            >>> count = prov_mgr.track_entities_batch(entities, "doc_1")
        """
        tracked_count = 0
        
        for entity in entities:
            entity_id = entity.get("id") or entity.get("entity_id")
            if not entity_id:
                continue
            
            entity_metadata = {**metadata, **entity.get("metadata", {})}
            
            try:
                self.track_entity(entity_id, source, entity_metadata)
                tracked_count += 1
            except Exception:
                pass  # Continue with other entities
        
        return tracked_count
    
    def track_chunks_batch(
        self,
        chunks: List[Dict[str, Any]],
        source_document: str,
        source_path: Optional[str] = None,
        **metadata
    ) -> int:
        """
        Track multiple chunks in batch.
        
        Args:
            chunks: List of chunk dictionaries
            source_document: Source document identifier
            source_path: Path to source document
            **metadata: Metadata to apply to all chunks
            
        Returns:
            Number of chunks tracked
        """
        tracked_count = 0
        
        for chunk in chunks:
            chunk_id = chunk.get("id") or chunk.get("chunk_id")
            if not chunk_id:
                continue
            
            try:
                self.track_chunk(
                    chunk_id=chunk_id,
                    source_document=source_document,
                    source_path=source_path,
                    start_index=chunk.get("start_index", 0),
                    end_index=chunk.get("end_index", 0),
                    parent_chunk_id=chunk.get("parent_chunk_id"),
                    **{**metadata, **chunk.get("metadata", {})}
                )
                tracked_count += 1
            except Exception:
                pass
        
        return tracked_count
    
    # === Lineage Retrieval ===
    
    def get_lineage(self, entity_id: str) -> Dict[str, Any]:
        """
        Get complete lineage for an entity.
        
        Compatible with all existing tracker interfaces.
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            Dictionary containing lineage information including metadata
            
        Example:
            >>> lineage = prov_mgr.get_lineage("entity_1")
            >>> print(lineage["source_documents"])
            ['DOI:10.1371/...', 'doc_2']
            >>> print(lineage["metadata"])
            {'text': 'Apple Inc.', 'label': 'ORG'}
        """
        lineage_entries = self.storage.trace_lineage(entity_id)
        
        if not lineage_entries:
            return {}
        
        # Aggregate metadata from all lineage entries.
        # trace_lineage() is a BFS starting at entity_id, so lineage_entries[0]
        # is always the queried entity itself, followed by its ancestors
        # (parent, grandparent, ...). Apply ancestors first and the queried
        # entity last so its own keys win on conflict, matching the intent
        # that the "most recent"/current entity's metadata takes precedence.
        aggregated_metadata = {}
        for entry in reversed(lineage_entries):
            if entry.metadata:
                meta = entry.metadata
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                if isinstance(meta, dict):
                    aggregated_metadata.update(meta)
        
        integrity_verified = all(verify_checksum(entry) for entry in lineage_entries)
        chain_dicts = [entry.to_dict() for entry in lineage_entries]
        return {
            "entity_id": entity_id,
            "lineage_chain": chain_dicts,
            "entries": chain_dicts,
            "source_documents": list(set(
                e.source_document for e in lineage_entries 
                if e.source_document
            )),
            "first_seen": min(
                (e.first_seen for e in lineage_entries if e.first_seen),
                default=None
            ),
            "last_updated": max(
                (e.last_updated for e in lineage_entries if e.last_updated),
                default=None
            ),
            "entity_count": len(lineage_entries),
            "metadata": aggregated_metadata,
            "integrity_verified": integrity_verified,
        }
    
    def trace_lineage(self, entity_id: str) -> List[ProvenanceEntry]:
        """
        Trace complete lineage and return raw entries.
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            List of ProvenanceEntry objects
        """
        return self.storage.trace_lineage(entity_id)
    
    def get_all_sources(self, entity_id: str) -> List[Dict[str, Any]]:
        """
        Get all sources for an entity (kg.ProvenanceTracker compatible).
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            List of source dictionaries
        """
        lineage_entries = self.storage.trace_lineage(entity_id)
        
        sources = []
        for entry in lineage_entries:
            if entry.source_document:
                sources.append({
                    "source": entry.source_document,
                    "location": entry.source_location,
                    "timestamp": entry.timestamp,
                    "confidence": entry.confidence,
                    "metadata": entry.metadata
                })
        
        return sources
    
    def get_provenance(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get provenance for entity (kg.ProvenanceTracker compatible).
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            Provenance dictionary or None
        """
        entry = self.storage.retrieve(entity_id)
        if entry:
            return entry.to_dict()
        return None
    
    # === Utility Methods ===
    
    def clear(self) -> int:
        """
        Clear all provenance data.
        
        Returns:
            Number of entries cleared
        """
        return self.storage.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get provenance statistics.
        
        Returns:
            Dictionary with statistics
        """
        all_entries = self.storage.retrieve_all()
        
        entity_types = {}
        for entry in all_entries:
            entity_types[entry.entity_type] = entity_types.get(entry.entity_type, 0) + 1
        
        return {
            "total_entries": len(all_entries),
            "entity_types": entity_types,
            "unique_sources": len(set(
                e.source_document for e in all_entries 
                if e.source_document
            ))
        }

    # === CLI Integration Methods ===

    def lineage(self, entity_id: str, depth: int = 3) -> Dict[str, Any]:
        """
        Get lineage information formatted for CLI display.

        Args:
            entity_id: ID of the entity to trace lineage for
            depth: Maximum traversal depth (default: 3)

        Returns:
            Dict containing entity_id, depth, count, lineage entries, and sources
        """
        base_lineage = self.get_lineage(entity_id)
        entries = base_lineage.get("lineage_chain", [])
        if len(entries) > depth:
            entries = entries[:depth]
        sources = self.get_all_sources(entity_id)
        return {
            "entity_id": entity_id,
            "depth": depth,
            "chain_length": len(entries),
            "source_documents": base_lineage.get("source_documents", []),
            "lineage": entries,
            "entries": entries,
            "sources": sources,
            "metadata": base_lineage.get("metadata", {}),
        }

    def audit_log(
        self, since: Optional[str] = None, format: str = "table"
    ) -> Union[str, List[Dict[str, Any]]]:
        """
        Export audit log of provenance entries.

        Args:
            since: Optional ISO 8601 date string filter
            format: Output format ('table', 'csv', 'json')

        Returns:
            Formatted audit log as string or list of dicts
        """
        entries = self.storage.retrieve_all()
        if since:
            entries = [e for e in entries if getattr(e, "timestamp", "") >= since]
        entries.sort(key=lambda e: getattr(e, "timestamp", ""))

        if format == "json":
            return [
                e.to_dict() if hasattr(e, "to_dict") else getattr(e, "__dict__", {})
                for e in entries
            ]
        elif format == "csv":
            lines = ["entity_id,entity_type,activity_id,agent_id,timestamp"]
            for e in entries:
                ts = getattr(e, "timestamp", "")
                lines.append(
                    f"{e.entity_id},{e.entity_type},{e.activity_id},{e.agent_id},{ts}"
                )
            return "\n".join(lines)
        else:
            lines = [
                f"{'ENTITY_ID':<20} {'TYPE':<15} {'ACTIVITY':<15} {'TIMESTAMP':<25}"
            ]
            lines.append("-" * 75)
            for e in entries:
                ts = str(getattr(e, "timestamp", ""))
                lines.append(
                    f"{str(e.entity_id):<20} {str(e.entity_type):<15}"
                    f" {str(e.activity_id):<15} {ts:<25}"
                )
            return "\n".join(lines)

    def export_prov(self, format: str = "turtle") -> str:
        """
        Export provenance as W3C PROV-O RDF.

        Args:
            format: RDF format ('turtle', 'ntriples', 'jsonld')

        Returns:
            Serialized RDF string
        """
        from rdflib import Graph, Literal, Namespace, URIRef
        from rdflib.namespace import RDF, XSD

        PROV = Namespace("http://www.w3.org/ns/prov#")
        EX = Namespace("http://example.org/ns/")

        g = Graph()
        g.bind("prov", PROV)
        g.bind("ex", EX)

        for e in self.storage.retrieve_all():
            ent_uri = URIRef(EX[str(e.entity_id)])
            g.add((ent_uri, RDF.type, PROV.Entity))

            if getattr(e, "timestamp", None):
                g.add(
                    (
                        ent_uri,
                        PROV.generatedAtTime,
                        Literal(e.timestamp, datatype=XSD.dateTime),
                    )
                )

            if getattr(e, "agent_id", None) and e.agent_id != "unknown":
                ag_uri = URIRef(EX[str(e.agent_id)])
                g.add((ag_uri, RDF.type, PROV.Agent))
                g.add((ent_uri, PROV.wasAttributedTo, ag_uri))

            if getattr(e, "activity_id", None) and e.activity_id != "unknown":
                act_uri = URIRef(EX[str(e.activity_id)])
                g.add((act_uri, RDF.type, PROV.Activity))
                g.add((ent_uri, PROV.wasGeneratedBy, act_uri))

            if getattr(e, "parent_entity_id", None):
                p_uri = URIRef(EX[str(e.parent_entity_id)])
                g.add((ent_uri, PROV.wasDerivedFrom, p_uri))

            for u_id in getattr(e, "used_entities", []):
                u_uri = URIRef(EX[str(u_id)])
                # Emit wasDerivedFrom only when this used entity is not the same
                # as parent_entity_id — which already carries that triple above.
                if u_id != getattr(e, "parent_entity_id", None):
                    g.add((ent_uri, PROV.wasDerivedFrom, u_uri))
                if getattr(e, "activity_id", None) and e.activity_id != "unknown":
                    act_uri = URIRef(EX[str(e.activity_id)])
                    g.add((act_uri, PROV.used, u_uri))

        rdf_format = "json-ld" if format == "jsonld" else format
        return g.serialize(format=rdf_format)

    def check(self, strict: bool = False) -> Dict[str, Any]:
        """
        Validate provenance integrity.

        Args:
            strict: Whether to perform strict validation

        Returns:
            Dictionary with validation results
        """
        entries = self.storage.retrieve_all()
        all_ids = {e.entity_id for e in entries}

        missing_refs = []
        for e in entries:
            if getattr(e, "parent_entity_id", None):
                if e.parent_entity_id not in all_ids:
                    missing_refs.append(f"{e.entity_id} -> {e.parent_entity_id}")
            for u_id in getattr(e, "used_entities", []):
                if u_id not in all_ids:
                    missing_refs.append(f"{e.entity_id} -> {u_id}")

        valid = len(missing_refs) == 0
        errors = len(missing_refs)

        return {
            "valid": valid,
            "total_entries": len(entries),
            "missing_references": missing_refs,
            "strict": strict,
            "errors": errors,
        }

