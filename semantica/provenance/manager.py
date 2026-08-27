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
from datetime import datetime, timezone
from contextlib import contextmanager
import copy
import inspect
import json
import threading

from .schemas import ProvenanceEntry, SourceReference, AgentRecord, ActivityRecord
from .storage import ProvenanceStorage, InMemoryStorage, SQLiteStorage
from .integrity import compute_checksum, verify_checksum
from ..utils.helpers import to_utc_datetime, utc_now_iso
from ..utils.logging import get_logger

#: Sort key for an entry whose timestamp cannot be read as one, so an
#: unreadable value orders first instead of raising during a sort.
_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)

# Issue #825, Part B Tier 3 — configurable base URI for export_prov(), shared
# with RDFExporter's NamespaceManager "semantica" entry (semantica/export/
# rdf_exporter.py) so KG-exported and PROV-exported URIs for the same
# entity_id co-resolve to the same namespace instead of two different
# placeholder domains.
DEFAULT_BASE_URI = "https://semantica.dev/ns#"


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
        self.logger = get_logger("provenance_manager")
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

    def _save_entry(
        self,
        entry: ProvenanceEntry,
        _conn: Optional[Any] = None,
        _raise_on_error: bool = False,
    ) -> Optional[ProvenanceEntry]:
        """Compute checksum, store entry persistently, and log/handle storage errors (#783)."""
        # Hash-chain linkage (issue #825, Part A item 2): link this entry to
        # the previous entry in global insertion order before hashing, so
        # deleting a row later breaks the chain for whatever followed it.
        try:
            head = self.storage.get_chain_head(_conn)
        except Exception:
            head = None
        entry.sequence_id = (head[0] + 1) if head else 1
        entry.previous_checksum = head[1] if head else None

        entry.checksum = compute_checksum(entry)

        try:
            if _conn is not None:
                self.storage._store_with_conn(_conn, entry)
            else:
                self.storage.store(entry)
        except Exception as e:
            self.logger.error(
                "Failed to save provenance entry for entity '%s': %s",
                entry.entity_id,
                e,
                exc_info=True,
            )
            # Propagate when called from a batch's shared transaction so the
            # caller's per-item try/except can skip counting this item instead
            # of reporting an unpersisted entry as tracked (#807).
            if _raise_on_error:
                raise
            return None  # Graceful failure - don't return unpersisted entry (#783)

        return entry
    
    @contextmanager
    def _get_or_create_transaction(self, _conn=None):
        """Helper to use an existing transaction connection or open a new one."""
        if _conn is not None:
            yield _conn
        else:
            with self.storage.transaction() as conn:
                yield conn

    # Recognized typed kwargs for track_entity, used both directly and to
    # split track_entities_batch's **metadata into real kwargs vs. free-form
    # metadata (issue #825, Part A item 3 — fixes a bug where agent_id/
    # entity_type/activity_id passed to track_entities_batch were silently
    # absorbed into the opaque metadata blob instead of populating fields).
    _TRACK_ENTITY_KWARGS = frozenset({
        "entity_type", "activity_id", "agent_id", "agent_type", "is_automated",
        "role", "agent", "source_location", "source_quote", "confidence",
        "parent_entity_id", "used_entities",
        # Part B Tier 1/2/3 (issue #825)
        "activity", "activity_started_at_time", "activity_ended_at_time",
        "acted_on_behalf_of", "informed_by", "valid_from", "valid_until",
        "revision_type", "supersedes", "bundle_id",
    })

    @staticmethod
    def _resolve_agent_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve agent_id/agent_type/is_automated/role from kwargs.

        Accepts either an `agent=AgentRecord(...)` kwarg (takes precedence)
        or individual `agent_id`/`agent_type`/`is_automated` scalar kwargs.
        Fixes issue #825's dead agent_id field: previously no track_*
        method read agent_id from kwargs at all, so it was always the
        dataclass default "semantica" regardless of what callers passed.
        """
        agent = kwargs.get("agent")
        if isinstance(agent, AgentRecord):
            return {
                "agent_id": agent.id,
                "agent_type": agent.agent_type,
                "is_automated": agent.is_automated,
                "role": kwargs.get("role"),
            }
        return {
            "agent_id": kwargs.get("agent_id", "semantica"),
            "agent_type": kwargs.get("agent_type", "software_agent"),
            "is_automated": kwargs.get("is_automated", True),
            "role": kwargs.get("role"),
        }

    @staticmethod
    def _resolve_activity_kwargs(kwargs: Dict[str, Any], default_activity_id: str) -> Dict[str, Any]:
        """
        Resolve activity_id/activity_started_at_time/activity_ended_at_time
        from kwargs (issue #825, Part B Tier 1 — typed Activity).

        Accepts either an `activity=ActivityRecord(...)` kwarg (takes
        precedence) or individual scalar kwargs.
        """
        activity = kwargs.get("activity")
        if isinstance(activity, ActivityRecord):
            return {
                "activity_id": activity.id,
                "activity_started_at_time": activity.started_at_time,
                "activity_ended_at_time": activity.ended_at_time,
            }
        return {
            "activity_id": kwargs.get("activity_id", default_activity_id),
            "activity_started_at_time": kwargs.get("activity_started_at_time"),
            "activity_ended_at_time": kwargs.get("activity_ended_at_time"),
        }

    # === Entity Tracking (from kg.ProvenanceTracker) ===
    
    def track_entity(
        self,
        entity_id: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        _conn: Optional[Any] = None,
        **kwargs
    ) -> Optional[ProvenanceEntry]:
        """
        Track entity provenance (kg.ProvenanceTracker compatible).
        
        Args:
            entity_id: Entity identifier
            source: Source identifier (document ID, DOI, file path)
            metadata: Optional metadata dictionary
            **kwargs: Additional fields (confidence, source_location, etc.)
            
        Returns:
            Optional[ProvenanceEntry]: ProvenanceEntry on success, deepcopy of existing
            entry if update fails, or None if brand-new entity storage fails
            
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
        
        # Atomic tracking transaction (#807):
        # We scope one connection to the full duration of track_entity so all
        # retrieve and store operations share a single transaction. With BEGIN IMMEDIATE,
        # concurrent calls serialize during retrieval so no intervening versions are lost.
        # If any step raises, the whole operation rolls back.
        existing = None
        entry = None
        try:
            with self._get_or_create_transaction(_conn) as conn:
                existing = self.storage._retrieve_with_conn(conn, entity_id)
                parent_id = kwargs.get("parent_entity_id")

                if not parent_id and metadata and isinstance(metadata, Mapping):
                    derived_from = metadata.get("derived_from")
                    if derived_from and isinstance(derived_from, str):
                        parent_id = derived_from

                if not parent_id and source and isinstance(source, str):
                    try:
                        source_entity = self.storage._retrieve_with_conn(conn, source)
                        if source_entity:
                            parent_id = source
                    except Exception:
                        pass

                explicit_parent_supplied = parent_id is not None

                archived_history_id = None
                if existing:
                    history_entry = copy.deepcopy(existing)
                    base_history_id = f"{entity_id}:v:{existing.last_updated}"
                    history_id = base_history_id
                    counter = 1
                    while self.storage._retrieve_with_conn(conn, history_id):
                        history_id = f"{base_history_id}:{counter}"
                        counter += 1

                    history_entry.entity_id = history_id

                    # Pure relabel: checksum/sequence_id/previous_checksum are
                    # left exactly as they were. compute_checksum() excludes
                    # entity_id specifically so this is safe — recomputing it
                    # here (or assigning a fresh sequence slot) would either
                    # invalidate any later entry that already chained from
                    # this row's checksum, or strand the original sequence
                    # position and make verify_chain() see a phantom gap
                    # (issue #825: an archival relabel is not tampering and
                    # must not look like it to the hash chain).
                    self.storage._store_with_conn(conn, history_entry)
                    archived_history_id = history_id
                    if not explicit_parent_supplied:
                        parent_id = history_id

                agent_info = self._resolve_agent_kwargs(kwargs)
                activity_info = self._resolve_activity_kwargs(kwargs, "entity_tracking")

                entry = ProvenanceEntry(
                    entity_id=entity_id,
                    entity_type=kwargs.get("entity_type", "entity"),
                    activity_id=activity_info["activity_id"],
                    agent_id=agent_info["agent_id"],
                    agent_type=agent_info["agent_type"],
                    is_automated=agent_info["is_automated"],
                    role=agent_info["role"],
                    source_document=source,
                    source_location=kwargs.get("source_location"),
                    source_quote=kwargs.get("source_quote"),
                    confidence=kwargs.get("confidence", 1.0),
                    metadata=metadata or {},
                    first_seen=existing.first_seen if existing else utc_now_iso(),
                    last_updated=utc_now_iso(),
                    parent_entity_id=parent_id,
                    used_entities=list(kwargs.get("used_entities", [])),
                    activity_started_at_time=activity_info["activity_started_at_time"],
                    activity_ended_at_time=activity_info["activity_ended_at_time"],
                    acted_on_behalf_of=kwargs.get("acted_on_behalf_of"),
                    informed_by_activities=list(kwargs.get("informed_by", [])),
                    valid_from=kwargs.get("valid_from"),
                    valid_until=kwargs.get("valid_until"),
                    revision_type=kwargs.get("revision_type"),
                    supersedes=kwargs.get("supersedes"),
                    bundle_id=kwargs.get("bundle_id"),
                )

                # Versioning vs. derivation (issue #825, Part A item 4):
                # previous_version_id always captures "this corrects a prior
                # version of the same fact" when one was archived, independent
                # of whether an explicit cross-source parent was also given.
                # derived_from_id captures "this fact was derived from a
                # different source entity" — only set when a parent was
                # explicitly resolved (kwarg/metadata['derived_from']/source
                # heuristic), never from the automatic archival link.
                entry.previous_version_id = archived_history_id
                if explicit_parent_supplied:
                    entry.derived_from_id = parent_id

                if archived_history_id and explicit_parent_supplied:
                    entry.used_entities.append(archived_history_id)

                self._save_entry(entry, _conn=conn, _raise_on_error=True)
        except Exception as e:
            # When called from a batch's shared transaction (_conn is not None),
            # propagate so the caller's per-item try/except can skip counting
            # this item instead of reporting an unpersisted entry as tracked (#807).
            if _conn is not None:
                raise
            self.logger.error(
                "Failed to track entity '%s' (transaction rolled back): %s. "
                "Returning pre-failure state (%s).",
                entity_id,
                e,
                "existing entry" if existing else "None (no prior entry existed)",
                exc_info=True,
            )
            if existing is not None:
                return copy.deepcopy(existing)
            return None

        return entry
    
    def track_relationship(
        self,
        relationship_id: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Optional[ProvenanceEntry]:
        """
        Track relationship provenance (kg.ProvenanceTracker compatible).
        
        Args:
            relationship_id: Relationship identifier
            source: Source identifier
            metadata: Optional metadata dictionary
            **kwargs: Additional fields
            
        Returns:
            Optional[ProvenanceEntry]: ProvenanceEntry on success, or None if storage fails
            
        Example:
            >>> prov_mgr.track_relationship(
            ...     relationship_id="rel_1",
            ...     source="doc_1",
            ...     metadata={"type": "founded"}
            ... )
        """
        agent_info = self._resolve_agent_kwargs(kwargs)
        activity_info = self._resolve_activity_kwargs(kwargs, "relationship_tracking")

        entry = ProvenanceEntry(
            entity_id=relationship_id,
            entity_type="relationship",
            activity_id=activity_info["activity_id"],
            agent_id=agent_info["agent_id"],
            agent_type=agent_info["agent_type"],
            is_automated=agent_info["is_automated"],
            role=agent_info["role"],
            source_document=source,
            source_location=kwargs.get("source_location"),
            confidence=kwargs.get("confidence", 1.0),
            metadata=metadata or {},
            first_seen=utc_now_iso(),
            last_updated=utc_now_iso(),
            activity_started_at_time=activity_info["activity_started_at_time"],
            activity_ended_at_time=activity_info["activity_ended_at_time"],
            acted_on_behalf_of=kwargs.get("acted_on_behalf_of"),
            informed_by_activities=list(kwargs.get("informed_by", [])),
            valid_from=kwargs.get("valid_from"),
            valid_until=kwargs.get("valid_until"),
            revision_type=kwargs.get("revision_type"),
            supersedes=kwargs.get("supersedes"),
            bundle_id=kwargs.get("bundle_id"),
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
        _conn: Optional[Any] = None,
        **metadata
    ) -> Optional[ProvenanceEntry]:
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
            Optional[ProvenanceEntry]: ProvenanceEntry on success, or None if storage fails
            
        Example:
            >>> prov_mgr.track_chunk(
            ...     chunk_id="chunk_1",
            ...     source_document="doc_1",
            ...     source_path="/path/to/doc.pdf",
            ...     start_index=0,
            ...     end_index=500
            ... )
        """
        agent_info = self._resolve_agent_kwargs(metadata)
        activity_info = self._resolve_activity_kwargs(metadata, "chunking")
        for key in (
            "agent_id", "agent_type", "is_automated", "role", "agent",
            "activity", "activity_started_at_time", "activity_ended_at_time",
        ):
            metadata.pop(key, None)

        entry = ProvenanceEntry(
            entity_id=chunk_id,
            entity_type="chunk",
            activity_id=activity_info["activity_id"],
            agent_id=agent_info["agent_id"],
            agent_type=agent_info["agent_type"],
            is_automated=agent_info["is_automated"],
            role=agent_info["role"],
            source_document=source_document,
            source_location=source_path,
            start_index=start_index,
            end_index=end_index,
            parent_entity_id=parent_chunk_id,
            # A chunk split from a parent chunk is a derivation (a new entity
            # produced from an existing one), not a correction of the same
            # fact — see track_entity's previous_version_id/derived_from_id
            # split (issue #825, Part A item 4).
            derived_from_id=parent_chunk_id,
            metadata=metadata,
            timestamp=utc_now_iso(),
            activity_started_at_time=activity_info["activity_started_at_time"],
            activity_ended_at_time=activity_info["activity_ended_at_time"],
        )

        return self._save_entry(entry, _conn=_conn, _raise_on_error=(_conn is not None))
    
    # === Source Tracking (from conflicts.SourceTracker) ===
    
    def track_property_source(
        self,
        entity_id: str,
        property_name: str,
        value: Any,
        source: SourceReference,
        **metadata
    ) -> Optional[ProvenanceEntry]:
        """
        Track property source (conflicts.SourceTracker compatible).
        
        Args:
            entity_id: Entity identifier
            property_name: Property name
            value: Property value
            source: SourceReference object
            **metadata: Additional metadata
            
        Returns:
            Optional[ProvenanceEntry]: ProvenanceEntry on success, or None if storage fails
            
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
        agent_info = self._resolve_agent_kwargs(metadata)
        activity_info = self._resolve_activity_kwargs(metadata, "property_tracking")
        for key in (
            "agent_id", "agent_type", "is_automated", "role", "agent",
            "activity", "activity_started_at_time", "activity_ended_at_time",
        ):
            metadata.pop(key, None)

        entry = ProvenanceEntry(
            entity_id=f"{entity_id}_{property_name}",
            entity_type="property",
            activity_id=activity_info["activity_id"],
            agent_id=agent_info["agent_id"],
            agent_type=agent_info["agent_type"],
            is_automated=agent_info["is_automated"],
            role=agent_info["role"],
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
            timestamp=utc_now_iso(),
            activity_started_at_time=activity_info["activity_started_at_time"],
            activity_ended_at_time=activity_info["activity_ended_at_time"],
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
        batch_size = 1000  # Justification (#807): 1,000 items per transaction bounds SQLite WAL frame growth and reduces lock contention during multi-thousand-row imports while achieving a 1000x reduction in connection/commit overhead.

        # Split batch-level **metadata into recognized typed track_entity
        # kwargs (entity_type, activity_id, agent_id, ...) vs. free-form data.
        # Previously ALL of **metadata was merged into the metadata dict and
        # passed as track_entity's positional `metadata` arg, so typed kwargs
        # like agent_id/entity_type/activity_id were silently absorbed into
        # the opaque metadata JSON blob instead of populating real fields
        # (issue #825, Part A item 3 — this is what made agent_id a "dead"
        # field for every batch caller, including the documented example in
        # docs/guides/provenance.md).
        batch_kwargs = {k: v for k, v in metadata.items() if k in self._TRACK_ENTITY_KWARGS}
        free_metadata = {k: v for k, v in metadata.items() if k not in self._TRACK_ENTITY_KWARGS}

        for i in range(0, len(entities), batch_size):
            batch = entities[i : i + batch_size]
            batch_count = 0
            try:
                with self.storage.transaction() as conn:
                    for entity in batch:
                        entity_id = entity.get("id") or entity.get("entity_id")
                        if not entity_id:
                            continue

                        entity_metadata = {**free_metadata, **entity.get("metadata", {})}

                        try:
                            with self.storage.savepoint(conn):
                                self.track_entity(
                                    entity_id, source, entity_metadata, _conn=conn, **batch_kwargs
                                )
                            batch_count += 1
                        except Exception:
                            pass  # Continue with other entities in this batch
                # Add batch_count to tracked_count only after the transaction context
                # exits successfully and commits (#807).
                tracked_count += batch_count
            except Exception as e:
                self.logger.error(
                    "Block-level storage transaction failed in track_entities_batch: %s",
                    e,
                    exc_info=True,
                )
        
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
        batch_size = 1000  # Justification (#807): 1,000 items per transaction bounds SQLite WAL frame growth and reduces lock contention during multi-thousand-row imports while achieving a 1000x reduction in connection/commit overhead.
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            batch_count = 0
            try:
                with self.storage.transaction() as conn:
                    for chunk in batch:
                        chunk_id = chunk.get("id") or chunk.get("chunk_id")
                        if not chunk_id:
                            continue
                        
                        try:
                            with self.storage.savepoint(conn):
                                self.track_chunk(
                                    chunk_id=chunk_id,
                                    source_document=source_document,
                                    source_path=source_path,
                                    start_index=chunk.get("start_index", 0),
                                    end_index=chunk.get("end_index", 0),
                                    parent_chunk_id=chunk.get("parent_chunk_id"),
                                    _conn=conn,
                                    **{**metadata, **chunk.get("metadata", {})}
                                )
                            batch_count += 1
                        except Exception:
                            pass
                # Add batch_count to tracked_count only after the transaction context
                # exits successfully and commits (#807).
                tracked_count += batch_count
            except Exception as e:
                self.logger.error(
                    "Block-level storage transaction failed in track_chunks_batch: %s",
                    e,
                    exc_info=True,
                )
        
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
    
    def trace_lineage(self, entity_id: str, max_depth: Optional[int] = None) -> List[ProvenanceEntry]:
        """
        Trace complete lineage and return raw entries.
        
        Args:
            entity_id: Entity identifier
            max_depth: Optional maximum BFS depth
            
        Returns:
            List of ProvenanceEntry objects
        """
        if max_depth is None:
            return self.storage.trace_lineage(entity_id)
        try:
            sig = inspect.signature(self.storage.trace_lineage)
            supports_max_depth = "max_depth" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
        except (ValueError, TypeError):
            supports_max_depth = True
        if supports_max_depth:
            return self.storage.trace_lineage(entity_id, max_depth=max_depth)
        return self.storage.trace_lineage(entity_id)

    def trace_descendants(
        self, entity_id: str, max_depth: Optional[int] = None
    ) -> List[ProvenanceEntry]:
        """
        Trace downstream descendants (reverse lineage) and return raw entries.

        This is the counterpart to trace_lineage()/get_lineage(), which only
        ever trace upstream ancestors via parent_entity_id/used_entities.
        Downstream traceability answers the incident-response question "entity
        X was wrong — what downstream facts used it?" (issue #825, Part A
        item 5).

        Args:
            entity_id: Entity identifier
            max_depth: Optional maximum BFS depth

        Returns:
            List of ProvenanceEntry objects that (transitively) reference
            entity_id, in BFS order.
        """
        return self.storage.trace_descendants(entity_id, max_depth=max_depth)

    def get_descendants(self, entity_id: str) -> Dict[str, Any]:
        """
        Get downstream descendants for an entity, mirroring get_lineage()'s
        return shape but for the reverse direction.

        Args:
            entity_id: Entity identifier

        Returns:
            Dictionary containing descendant entries, or {} if none found.
        """
        descendant_entries = self.trace_descendants(entity_id)

        if not descendant_entries:
            return {}

        integrity_verified = all(verify_checksum(entry) for entry in descendant_entries)
        chain_dicts = [entry.to_dict() for entry in descendant_entries]
        return {
            "entity_id": entity_id,
            "descendant_chain": chain_dicts,
            "entries": chain_dicts,
            "entity_count": len(descendant_entries),
            "integrity_verified": integrity_verified,
        }

    def revision_history(self, entity_id: str) -> List[Dict[str, Any]]:
        """
        Return the version history for entity_id in ascending order.

        Issue #825, Part B Tier 3 — closes the "no direct equivalent yet"
        gap for kg.ProvenanceTracker.revision_history() documented in
        docs/migration/kg-provenance-tracker.md.

        Walks the entity's own previous_version_id chain (not the full
        upstream lineage via get_lineage(), which also pulls in unrelated
        derived_from_id/used_entities links from other source entities).

        Args:
            entity_id: Entity identifier

        Returns:
            List of {version, valid_from, valid_until, recorded_at, author,
            revision_type, supersedes} dicts, oldest first. valid_from/
            valid_until use the entry's own explicit fields when set (the
            fact's asserted validity window); otherwise valid_from defaults
            to when this version was recorded, and valid_until to the next
            version's timestamp (None for the current/most recent version).
            Empty list if entity_id was never tracked.
        """
        current = self.storage.retrieve(entity_id)
        if current is None:
            return []

        chain: List[ProvenanceEntry] = [current]
        visited = {entity_id}
        cursor = current
        while getattr(cursor, "previous_version_id", None):
            prev_id = cursor.previous_version_id
            if prev_id in visited:
                break
            prev_entry = self.storage.retrieve(prev_id)
            if prev_entry is None:
                break
            chain.append(prev_entry)
            visited.add(prev_id)
            cursor = prev_entry

        chain.reverse()  # oldest first

        history = []
        for i, entry in enumerate(chain):
            default_valid_until = chain[i + 1].timestamp if i + 1 < len(chain) else None
            version_dict: Dict[str, Any] = {
                "version": i + 1,
                "valid_from": entry.valid_from or entry.timestamp,
                "valid_until": entry.valid_until or default_valid_until,
                "recorded_at": entry.timestamp,
                "author": entry.agent_id,
            }
            if entry.revision_type:
                version_dict["revision_type"] = entry.revision_type
            if entry.supersedes:
                version_dict["supersedes"] = entry.supersedes
            history.append(version_dict)
        return history

    def query_recorded_between(self, start: str, end: str) -> List[Dict[str, Any]]:
        """
        Return all provenance entries whose timestamp falls within [start, end].

        Issue #825, Part B Tier 3 — closes the "no direct equivalent yet"
        gap for kg.ProvenanceTracker.query_recorded_between() documented in
        docs/migration/kg-provenance-tracker.md.

        Args:
            start: Start of range, ISO 8601 string (inclusive)
            end: End of range, ISO 8601 string (inclusive)

        Returns:
            List of matching entries as dicts, sorted by timestamp ascending.
        """
        # Compare instants, not spellings. Since #1114 new entries carry a
        # +00:00 offset while entries written earlier do not, and a raw string
        # comparison orders those two by length: an inclusive naive bound equal
        # to a stored offset-bearing timestamp would sort below it and drop the
        # record. A bound in another offset was mis-ordered the same way.
        start_at = to_utc_datetime(start)
        end_at = to_utc_datetime(end)
        entries = [e for e in self.storage.retrieve_all() if e.timestamp]

        if start_at is None or end_at is None:
            # A bound this module cannot read as a timestamp keeps the historical
            # string comparison rather than raising on a call that used to work.
            matches = [e for e in entries if start <= e.timestamp <= end]
        else:
            matches = [
                e for e in entries
                if (at := to_utc_datetime(e.timestamp)) is not None
                and start_at <= at <= end_at
            ]

        matches.sort(key=lambda e: (to_utc_datetime(e.timestamp) or _EPOCH, e.timestamp))
        return [e.to_dict() for e in matches]

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

    # === Invalidation (tombstone, not hard delete) ===

    def invalidate(
        self,
        entity_id: str,
        agent_id: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceEntry:
        """
        Mark a tracked entity as invalidated instead of deleting it
        (issue #825, Part A item 1 — prov:Invalidation).

        An audit needs "this was deleted/corrected, by whom, when, why" to
        itself be provable. Rather than mutating the row in place, this
        archives the pre-invalidation state under a stable versioned key
        (the same pattern track_entity() uses for corrections) and then
        writes the invalidated entry as a fresh, chained append. Mutating
        the existing row's checksum in place would silently invalidate any
        later entry that had already chained its previous_checksum from
        this row's pre-invalidation value — turning a legitimate
        invalidation into a false-positive "broken chain" report.

        The entry remains visible via retrieve()/retrieve_all()/lineage
        traversal, but callers can filter on `invalidated` to exclude
        retracted facts.

        Args:
            entity_id: Entity identifier to invalidate
            agent_id: Agent responsible for the invalidation (prov:Agent)
            reason: Optional human-readable reason
            metadata: Optional metadata to merge into the entry

        Returns:
            The updated (invalidated) ProvenanceEntry

        Raises:
            ValueError: If no provenance entry exists for entity_id

        Example:
            >>> prov_mgr.invalidate("entity_1", agent_id="reviewer_jane",
            ...                     reason="Source document retracted")
        """
        with self.storage.transaction() as conn:
            existing = self.storage._retrieve_with_conn(conn, entity_id)
            if existing is None:
                raise ValueError(
                    f"Cannot invalidate: no provenance entry found for entity_id={entity_id!r}"
                )

            # Archive the pre-invalidation state under a stable key — a pure
            # relabel (see track_entity's identical pattern), so its
            # checksum/sequence_id/previous_checksum are left untouched.
            history_entry = copy.deepcopy(existing)
            base_history_id = f"{entity_id}:v:{existing.last_updated}"
            history_id = base_history_id
            counter = 1
            while self.storage._retrieve_with_conn(conn, history_id):
                history_id = f"{base_history_id}:{counter}"
                counter += 1
            history_entry.entity_id = history_id
            self.storage._store_with_conn(conn, history_entry)

            entry = copy.deepcopy(existing)
            entry.invalidated = True
            entry.invalidated_at_time = utc_now_iso()
            entry.invalidated_by = agent_id
            entry.invalidation_reason = reason
            entry.previous_version_id = history_id
            if metadata:
                entry.metadata = {**entry.metadata, **metadata}

            self._save_entry(entry, _conn=conn, _raise_on_error=True)

        return entry

    # === Utility Methods ===

    def clear(self) -> int:
        """
        Clear all provenance data.

        Note: this is a bulk storage reset (used for dev/test teardown), not
        a single-fact retraction — use invalidate() to retract/correct an
        individual tracked entity while preserving its audit trail.

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
            since_at = to_utc_datetime(since)
            if since_at is None:
                entries = [e for e in entries
                           if getattr(e, "timestamp", "") >= since]
            else:
                entries = [
                    e for e in entries
                    if (at := to_utc_datetime(getattr(e, "timestamp", None)))
                    is not None and at >= since_at
                ]
        entries.sort(
            key=lambda e: (
                to_utc_datetime(getattr(e, "timestamp", None)) or _EPOCH,
                getattr(e, "timestamp", ""),
            )
        )

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

    # Agent-type refinement for export_prov (issue #825, Part A item 6 —
    # cheap, opportunistic PROV-O typing on top of the generic prov:Agent).
    _AGENT_TYPE_PROV_CLASS = {
        "person": "Person",
        "software_agent": "SoftwareAgent",
        "organization": "Organization",
    }

    def export_prov(self, format: str = "turtle", base_uri: Optional[str] = None) -> str:
        """
        Export provenance as W3C PROV-O RDF.

        Args:
            format: RDF format ('turtle', 'ntriples', 'jsonld')
            base_uri: Namespace URI entities/agents/activities are minted
                under (issue #825, Part B Tier 3). Defaults to
                DEFAULT_BASE_URI, which matches RDFExporter's NamespaceManager
                "semantica" entry so KG-exported and PROV-exported URIs for
                the same entity_id co-resolve.

        Returns:
            Serialized RDF string
        """
        from rdflib import BNode, Graph, Literal, Namespace, URIRef
        from rdflib.namespace import RDF, XSD

        PROV = Namespace("http://www.w3.org/ns/prov#")
        EX = Namespace(base_uri or DEFAULT_BASE_URI)

        g = Graph()
        g.bind("prov", PROV)
        g.bind("ex", EX)

        def uri(entity_id: Any) -> URIRef:
            return URIRef(EX[str(entity_id)])

        for e in self.storage.retrieve_all():
            ent_uri = uri(e.entity_id)
            g.add((ent_uri, RDF.type, PROV.Entity))

            if getattr(e, "timestamp", None):
                g.add(
                    (
                        ent_uri,
                        PROV.generatedAtTime,
                        Literal(e.timestamp, datatype=XSD.dateTime),
                    )
                )

            ag_uri = None
            if getattr(e, "agent_id", None) and e.agent_id != "unknown":
                ag_uri = uri(e.agent_id)
                g.add((ag_uri, RDF.type, PROV.Agent))
                prov_subclass = self._AGENT_TYPE_PROV_CLASS.get(
                    getattr(e, "agent_type", None)
                )
                if prov_subclass:
                    g.add((ag_uri, RDF.type, PROV[prov_subclass]))
                g.add((ent_uri, PROV.wasAttributedTo, ag_uri))

                # Qualified Association with hadRole (issue #825, Part A item
                # 6): distinguishes "approved by" from "generated by" from
                # "reviewed by" for the same agent/entity pair, which the
                # plain wasAttributedTo triple above cannot express.
                association = BNode()
                g.add((ent_uri, PROV.qualifiedAssociation, association))
                g.add((association, RDF.type, PROV.Association))
                g.add((association, PROV.agent, ag_uri))
                role = getattr(e, "role", None) or "generator"
                g.add((association, PROV.hadRole, uri(f"role_{role}")))

                # prov:actedOnBehalfOf (issue #825, Part B Tier 2) — agent
                # delegation, e.g. an automated agent acting on behalf of the
                # human/organization that authorized it.
                delegate_id = getattr(e, "acted_on_behalf_of", None)
                if delegate_id:
                    delegate_uri = uri(delegate_id)
                    g.add((delegate_uri, RDF.type, PROV.Agent))
                    g.add((ag_uri, PROV.actedOnBehalfOf, delegate_uri))

            act_uri = None
            if getattr(e, "activity_id", None) and e.activity_id != "unknown":
                act_uri = uri(e.activity_id)
                g.add((act_uri, RDF.type, PROV.Activity))
                g.add((ent_uri, PROV.wasGeneratedBy, act_uri))

                # Typed Activity timing (issue #825, Part B Tier 1)
                if getattr(e, "activity_started_at_time", None):
                    g.add((act_uri, PROV.startedAtTime,
                           Literal(e.activity_started_at_time, datatype=XSD.dateTime)))
                if getattr(e, "activity_ended_at_time", None):
                    g.add((act_uri, PROV.endedAtTime,
                           Literal(e.activity_ended_at_time, datatype=XSD.dateTime)))

                # Qualified Generation (issue #825, Part B Tier 1)
                generation = BNode()
                g.add((ent_uri, PROV.qualifiedGeneration, generation))
                g.add((generation, RDF.type, PROV.Generation))
                g.add((generation, PROV.activity, act_uri))
                if getattr(e, "timestamp", None):
                    g.add((generation, PROV.atTime, Literal(e.timestamp, datatype=XSD.dateTime)))

                # prov:wasAssociatedWith (issue #825, Part B Tier 2) — direct
                # Activity->Agent link, distinct from the Entity->Agent
                # wasAttributedTo/qualifiedAssociation triples above.
                if ag_uri is not None:
                    g.add((act_uri, PROV.wasAssociatedWith, ag_uri))

                # prov:wasInformedBy (issue #825, Part B Tier 2) — chains this
                # activity to prior activities it was informed by (e.g. a
                # pipeline stage informed by the stage before it).
                for informing_id in getattr(e, "informed_by_activities", []):
                    g.add((act_uri, PROV.wasInformedBy, uri(informing_id)))

            def emit_derivation(source_id: Any) -> None:
                """Emit plain + qualified wasDerivedFrom for a source entity."""
                s_uri = uri(source_id)
                g.add((ent_uri, PROV.wasDerivedFrom, s_uri))
                derivation = BNode()
                g.add((ent_uri, PROV.qualifiedDerivation, derivation))
                g.add((derivation, RDF.type, PROV.Derivation))
                g.add((derivation, PROV.entity, s_uri))
                if act_uri is not None:
                    g.add((derivation, PROV.hadActivity, act_uri))

            if getattr(e, "parent_entity_id", None):
                emit_derivation(e.parent_entity_id)

            for u_id in getattr(e, "used_entities", []):
                u_uri = uri(u_id)
                # Emit wasDerivedFrom only when this used entity is not the same
                # as parent_entity_id — which already carries that triple above.
                if u_id != getattr(e, "parent_entity_id", None):
                    emit_derivation(u_id)
                if act_uri is not None:
                    g.add((act_uri, PROV.used, u_uri))
                    # Qualified Usage (issue #825, Part B Tier 1)
                    usage = BNode()
                    g.add((act_uri, PROV.qualifiedUsage, usage))
                    g.add((usage, RDF.type, PROV.Usage))
                    g.add((usage, PROV.entity, u_uri))

            # Qualified Invalidation (issue #825, Part A item 1): records the
            # tombstone as provable RDF rather than a silent hard delete.
            if getattr(e, "invalidated", False):
                invalidation = BNode()
                g.add((ent_uri, PROV.qualifiedInvalidation, invalidation))
                g.add((invalidation, RDF.type, PROV.Invalidation))
                if getattr(e, "invalidated_at_time", None):
                    g.add(
                        (
                            invalidation,
                            PROV.invalidatedAtTime,
                            Literal(e.invalidated_at_time, datatype=XSD.dateTime),
                        )
                    )
                if getattr(e, "invalidated_by", None):
                    inv_ag_uri = uri(e.invalidated_by)
                    g.add((inv_ag_uri, RDF.type, PROV.Agent))
                    g.add((invalidation, PROV.agent, inv_ag_uri))

            # prov:Collection / prov:Bundle membership (issue #825, Part B
            # Tier 3) — partitions provenance by source/dataset/ingestion-run.
            # Membership triples, not true RDF named-graph partitioning.
            if getattr(e, "bundle_id", None):
                bundle_uri = uri(f"bundle_{e.bundle_id}")
                g.add((bundle_uri, RDF.type, PROV.Bundle))
                g.add((bundle_uri, PROV.hadMember, ent_uri))

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
        all_activity_ids = {e.activity_id for e in entries if getattr(e, "activity_id", None)}

        missing_refs = []
        for e in entries:
            if getattr(e, "parent_entity_id", None):
                if e.parent_entity_id not in all_ids:
                    missing_refs.append(f"{e.entity_id} -> {e.parent_entity_id}")
            for u_id in getattr(e, "used_entities", []):
                if u_id not in all_ids:
                    missing_refs.append(f"{e.entity_id} -> {u_id}")
            for ref_id in (
                getattr(e, "previous_version_id", None),
                getattr(e, "derived_from_id", None),
                getattr(e, "supersedes", None),
            ):
                if ref_id and ref_id not in all_ids:
                    missing_refs.append(f"{e.entity_id} -> {ref_id}")
            # informed_by_activities references activity_ids, a distinct
            # ID space from entity_id (issue #825, Part B Tier 2).
            for act_id in getattr(e, "informed_by_activities", []):
                if act_id not in all_activity_ids:
                    missing_refs.append(f"{e.entity_id} (activity) -> {act_id}")

        valid = len(missing_refs) == 0
        errors = len(missing_refs)
        invalidated_count = sum(1 for e in entries if getattr(e, "invalidated", False))

        return {
            "valid": valid,
            "total_entries": len(entries),
            "missing_references": missing_refs,
            "invalidated_count": invalidated_count,
            "strict": strict,
            "errors": errors,
        }

    def verify_chain(self) -> Dict[str, Any]:
        """
        Verify the hash chain across all provenance entries (issue #825,
        Part A item 2).

        Sorts entries by sequence_id (global insertion order) and checks
        three things: each entry's own checksum matches its content; each
        entry's previous_checksum matches the checksum of the entry that
        precedes it; and sequence_id is exactly the predecessor's plus one
        (no gap, no duplicate). Every _save_entry() call assigns
        head_sequence + 1, and archival relabels (see track_entity's
        versioning and invalidate()) always preserve their existing
        sequence_id rather than consuming a new one — so under this design,
        the full set of currently-existing sequence_id values is always
        exactly {1..N} with nothing missing, unless a row was hard-deleted.
        A surviving entry whose previous_checksum doesn't match its
        predecessor, or whose sequence_id isn't predecessor+1, is exactly
        what wholesale row deletion produces; checking both signals also
        guards against the narrow case where two distinct rows happen to
        share a checksum (compute_checksum() deliberately excludes entity_id,
        see integrity.py), which alone would let a checksum-only check miss
        a gap that the sequence check still catches.

        Returns:
            Dictionary with "valid", "total_entries", and "broken_links"
            (list of {"entity_id", "sequence_id", "reason"} dicts).
        """
        entries = sorted(
            (e for e in self.storage.retrieve_all() if e.sequence_id is not None),
            key=lambda e: e.sequence_id,
        )

        broken_links: List[Dict[str, Any]] = []
        expected_previous: Optional[str] = None
        expected_sequence: Optional[int] = None
        for entry in entries:
            if not verify_checksum(entry):
                broken_links.append({
                    "entity_id": entry.entity_id,
                    "sequence_id": entry.sequence_id,
                    "reason": "checksum_mismatch",
                })
            else:
                sequence_gap = (
                    expected_sequence is not None
                    and entry.sequence_id != expected_sequence + 1
                )
                checksum_break = entry.previous_checksum != expected_previous
                if sequence_gap or checksum_break:
                    broken_links.append({
                        "entity_id": entry.entity_id,
                        "sequence_id": entry.sequence_id,
                        "reason": "chain_break",
                        "expected_previous_checksum": expected_previous,
                        "actual_previous_checksum": entry.previous_checksum,
                        "expected_sequence_id": (
                            expected_sequence + 1 if expected_sequence is not None else None
                        ),
                    })

            # Advance state from this entry's own stored fields regardless of
            # whether it was flagged above, so a single corrupted entry
            # doesn't cascade into spurious breaks for every entry after it.
            expected_previous = entry.checksum
            expected_sequence = entry.sequence_id

        return {
            "valid": len(broken_links) == 0,
            "total_entries": len(entries),
            "broken_links": broken_links,
        }

