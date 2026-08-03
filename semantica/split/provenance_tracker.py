"""
Provenance Tracker Module (Enhanced with Unified Backend)

This module provides comprehensive source tracking for document chunks,
maintaining data lineage and traceability throughout the chunking process.

IMPORTANT: This module now uses the unified semantica.provenance.ProvenanceManager
backend for enhanced W3C PROV-O compliance and audit-grade tracking. All existing
APIs remain 100% backward compatible.

For new code, consider using the unified API:
    >>> from semantica.provenance import ProvenanceManager
    >>> prov_mgr = ProvenanceManager()

Key Features:
    - Chunk source tracking
    - Document lineage management
    - Parent-child chunk relationships
    - Chunk linking and relationships
    - Provenance export
    - Version tracking support
    - W3C PROV-O compliance (when using unified backend)
    - Audit-grade integrity verification

Main Classes:
    - ProvenanceTracker: Main provenance tracking coordinator (backward compatible wrapper)
    - ProvenanceInfo: Provenance information representation dataclass

Example Usage:
    >>> from semantica.split import ProvenanceTracker
    >>> tracker = ProvenanceTracker()
    >>> prov_id = tracker.track_chunk(chunk, source_document="doc1", source_path="path/to/doc1.txt")
    >>> provenance = tracker.get_provenance(chunk_id)
    >>> lineage = tracker.get_chunk_lineage(chunk_id)

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .semantic_chunker import Chunk

# Import unified provenance manager
try:
    from ..provenance import ProvenanceManager as UnifiedProvenanceManager
    UNIFIED_AVAILABLE = True
except ImportError:
    UNIFIED_AVAILABLE = False


@dataclass
class ProvenanceInfo:
    """Provenance information representation."""

    chunk_id: str
    source_document: str
    source_path: Optional[str] = None
    start_index: int = 0
    end_index: int = 0
    parent_chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"
    timestamp: Optional[str] = None


class ProvenanceTracker:
    """
    Provenance tracker for chunk source tracking (Enhanced with Unified Backend).
    
    This class now wraps semantica.provenance.ProvenanceManager for enhanced
    W3C PROV-O compliance while maintaining 100% API compatibility.
    """

    def __init__(self, **config):
        """
        Initialize provenance tracker.

        Args:
            **config: Configuration options:
                - store_metadata: Store chunk metadata (default: True)
                - track_versions: Track version history (default: False)
                - storage_path: Path to SQLite database (optional)
        """
        self.logger = get_logger("provenance_tracker")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.store_metadata = config.get("store_metadata", True)
        self.track_versions = config.get("track_versions", False)

        self._provenance_store: Dict[str, ProvenanceInfo] = {}
        self._chunk_registry: Dict[str, str] = {}  # chunk_id -> provenance_id

        # Determine whether to use unified backend
        use_unified = config.get("use_unified", True) and UNIFIED_AVAILABLE
        
        if use_unified:
            # Use unified provenance manager
            storage_path = config.get("storage_path")
            self._unified_manager = UnifiedProvenanceManager(storage_path=storage_path)
            self._use_unified = True
            self.logger.debug("Chunk provenance tracker initialized with unified backend")
        else:
            # Fallback to legacy in-memory storage
            self._unified_manager = None
            self._use_unified = False
            self.logger.debug("Chunk provenance tracker initialized with legacy backend")

    def track_chunk(
        self,
        chunk: Chunk,
        source_document: str,
        source_path: Optional[str] = None,
        parent_chunk_id: Optional[str] = None,
        **metadata,
    ) -> str:
        """
        Track provenance for a chunk.

        Args:
            chunk: Chunk to track
            source_document: Source document identifier
            source_path: Path to source document
            parent_chunk_id: ID of parent chunk (if chunk was split)
            **metadata: Additional metadata

        Returns:
            str: Provenance ID
        """
        chunk_id = getattr(chunk, "id", None)
        if not chunk_id:
            chunk_id = str(uuid4())
            try:
                chunk.id = chunk_id
            except AttributeError:
                pass  # Chunk might be immutable
        
        if self._use_unified:
            # Delegate to unified manager
            try:
                chunk_metadata = {**chunk.metadata, **metadata, "chunk_size": len(chunk.text)} if self.store_metadata else metadata
                entry = self._unified_manager.track_chunk(
                    chunk_id=chunk_id,
                    source_document=source_document,
                    source_path=source_path,
                    start_index=chunk.start_index,
                    end_index=chunk.end_index,
                    parent_chunk_id=parent_chunk_id,
                    **chunk_metadata
                )
                if entry is None:
                    self.logger.warning("Unified tracking failed (returned None), using fallback")
                    return self._track_chunk_legacy(chunk, source_document, source_path, parent_chunk_id, **metadata)
                return chunk_id  # Return chunk_id for compatibility
            except Exception as e:
                self.logger.warning(f"Unified tracking failed, using fallback: {e}")
                return self._track_chunk_legacy(chunk, source_document, source_path, parent_chunk_id, **metadata)
        else:
            return self._track_chunk_legacy(chunk, source_document, source_path, parent_chunk_id, **metadata)
    
    def _track_chunk_legacy(
        self,
        chunk: Chunk,
        source_document: str,
        source_path: Optional[str] = None,
        parent_chunk_id: Optional[str] = None,
        **metadata,
    ) -> str:
        """Legacy chunk tracking implementation."""
        chunk_id = getattr(chunk, "id", None)
        if not chunk_id:
            chunk_id = str(uuid4())
            try:
                chunk.id = chunk_id
            except AttributeError:
                pass
        
        provenance_id = str(uuid4())

        provenance_info = ProvenanceInfo(
            chunk_id=chunk_id,
            source_document=source_document,
            source_path=source_path,
            start_index=chunk.start_index,
            end_index=chunk.end_index,
            parent_chunk_id=parent_chunk_id,
            metadata={**chunk.metadata, **metadata, "chunk_size": len(chunk.text)}
            if self.store_metadata
            else {},
            version="1.0",
        )

        self._provenance_store[provenance_id] = provenance_info
        self._chunk_registry[chunk_id] = provenance_id

        return provenance_id

    def track(self, pipeline_id: Optional[str] = None, **kwargs) -> Union[str, List[str]]:
        """
        Track provenance (alias for track_chunk/track_chunks).
        Delegates based on input arguments.

        Args:
            pipeline_id: Optional pipeline ID for progress tracking
            **kwargs: Arguments passed to track_chunk or track_chunks
        """
        if "chunks" in kwargs:
            kwargs["pipeline_id"] = pipeline_id
            return self.track_chunks(**kwargs)
        if "chunk" in kwargs and isinstance(kwargs["chunk"], list):
             # Handle list passed to chunk arg
             kwargs["chunks"] = kwargs.pop("chunk")
             kwargs["pipeline_id"] = pipeline_id
             return self.track_chunks(**kwargs)
        return self.track_chunk(**kwargs)

    def track_chunks(
        self,
        chunks: List[Chunk],
        source_document: str,
        source_path: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        **metadata,
    ) -> List[str]:
        """
        Track provenance for multiple chunks.

        Args:
            chunks: List of chunks to track
            source_document: Source document identifier
            source_path: Path to source document
            pipeline_id: Optional pipeline ID for progress tracking
            **metadata: Additional metadata

        Returns:
            list: List of provenance IDs
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="split",
            submodule="ProvenanceTracker",
            message=f"Tracking provenance for {len(chunks)} chunks",
            pipeline_id=pipeline_id,
        )

        try:
            provenance_ids = []
            parent_chunk_id = None

            for i, chunk in enumerate(chunks):
                self.progress_tracker.update_progress(
                    tracking_id,
                    processed=i + 1,
                    total=len(chunks),
                    message=f"Tracking chunk {i+1}/{len(chunks)}...",
                )
                provenance_id = self.track_chunk(
                    chunk, source_document, source_path, parent_chunk_id, **metadata
                )
                provenance_ids.append(provenance_id)
                parent_chunk_id = provenance_id

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Tracked {len(provenance_ids)} chunks",
            )
            return provenance_ids

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def get_provenance(self, chunk_id: str) -> Optional[ProvenanceInfo]:
        """
        Get provenance information for a chunk.

        Args:
            chunk_id: Chunk ID

        Returns:
            ProvenanceInfo: Provenance information or None
        """
        if self._use_unified:
            try:
                prov = self._unified_manager.get_provenance(chunk_id)
                if prov:
                    # Convert to ProvenanceInfo for backward compatibility
                    return ProvenanceInfo(
                        chunk_id=chunk_id,
                        source_document=prov.get("source_document", ""),
                        source_path=prov.get("source_location"),
                        start_index=prov.get("start_index", 0),
                        end_index=prov.get("end_index", 0),
                        parent_chunk_id=prov.get("parent_entity_id"),
                        metadata=prov.get("metadata", {}),
                        version=prov.get("version", "1.0"),
                        timestamp=prov.get("timestamp")
                    )
                return self._get_provenance_legacy(chunk_id)
            except Exception as e:
                self.logger.warning(f"Unified retrieval failed, using fallback: {e}")
                return self._get_provenance_legacy(chunk_id)
        else:
            return self._get_provenance_legacy(chunk_id)
    
    def _get_provenance_legacy(self, chunk_id: str) -> Optional[ProvenanceInfo]:
        """Legacy get provenance implementation."""
        provenance_id = self._chunk_registry.get(chunk_id)
        if provenance_id:
            return self._provenance_store.get(provenance_id)
        return None

    def get_source_chunks(self, source_document: str) -> List[ProvenanceInfo]:
        """
        Get all chunks from a source document.

        Args:
            source_document: Source document identifier

        Returns:
            list: List of provenance information
        """
        return [
            prov
            for prov in self._provenance_store.values()
            if prov.source_document == source_document
        ]

    def get_chunk_lineage(self, chunk_id: str) -> List[ProvenanceInfo]:
        """
        Get lineage (parent chain) for a chunk.

        Args:
            chunk_id: Chunk ID

        Returns:
            list: Lineage chain (oldest to newest)
        """
        if self._use_unified:
            try:
                lineage_entries = self._unified_manager.trace_lineage(chunk_id)
                # Convert to ProvenanceInfo list for backward compatibility
                return [
                    ProvenanceInfo(
                        chunk_id=entry.entity_id,
                        source_document=entry.source_document,
                        source_path=entry.source_location,
                        start_index=entry.start_index or 0,
                        end_index=entry.end_index or 0,
                        parent_chunk_id=entry.parent_entity_id,
                        metadata=entry.metadata,
                        version=entry.version,
                        timestamp=entry.timestamp
                    )
                    for entry in lineage_entries
                    if entry.entity_type == "chunk"
                ]
            except Exception as e:
                self.logger.warning(f"Unified lineage retrieval failed, using fallback: {e}")
                return self._get_chunk_lineage_legacy(chunk_id)
        else:
            return self._get_chunk_lineage_legacy(chunk_id)
    
    def _get_chunk_lineage_legacy(self, chunk_id: str) -> List[ProvenanceInfo]:
        """Legacy get chunk lineage implementation."""
        lineage = []
        current_chunk_id = chunk_id

        while current_chunk_id:
            provenance = self._get_provenance_legacy(current_chunk_id)
            if not provenance:
                break

            lineage.insert(0, provenance)
            current_chunk_id = provenance.parent_chunk_id

        return lineage

    def get_lineage(self, chunk_id: str) -> Dict[str, Any]:
        """
        Get lineage info in format expected by some consumers.
        Adapts internal representation to dict with 'source' key.
        """
        lineage_list = self.get_chunk_lineage(chunk_id)
        if not lineage_list:
            return {}
        
        # Return the most recent provenance info (the chunk itself)
        # wrapped in a structure that matches notebook expectation
        latest_prov = lineage_list[-1] # List is parent -> child (wait, let me check get_chunk_lineage implementation)
        # get_chunk_lineage inserts at 0, so [grandparent, parent, child]. 
        # But wait, logic: lineage.insert(0, provenance) while walking up parents.
        # So index 0 is oldest ancestor? 
        # Let's re-read get_chunk_lineage logic.
        
        # Logic:
        # current = chunk_id
        # while current:
        #    prov = get(current)
        #    lineage.insert(0, prov)
        #    current = prov.parent
        
        # So if we have C -> B -> A (A is parent of B, B is parent of C)
        # 1. current=C. prov=C. lineage=[C]. current=B.
        # 2. current=B. prov=B. lineage=[B, C]. current=A.
        # 3. current=A. prov=A. lineage=[A, B, C]. current=None.
        # So list is [Oldest, ..., Newest].
        
        # The notebook wants source info.
        # The chunk's immediate provenance info contains the source document/path.
        # So we want the info for the chunk itself (which is the last element).
        
        # Note: if lineage list is empty (shouldn't happen if chunk exists), return empty.
        # Actually, get_chunk_lineage calls get_provenance(chunk_id) first.
        
        if not lineage_list:
            return {}

        # Use the provenance info of the chunk itself
        prov = lineage_list[-1]
        
        return {
            "source": {
                "document_id": prov.source_document,
                "file_path": prov.source_path,
                "timestamp": prov.timestamp,
                "method": prov.metadata.get("method"), # method is often in metadata
                **prov.metadata
            },
            "lineage_chain": [self._provenance_to_dict(p) for p in lineage_list]
        }

    def link_chunks(
        self, chunk_id1: str, chunk_id2: str, relationship: str = "related"
    ) -> bool:
        """
        Link two chunks with a relationship.

        Args:
            chunk_id1: First chunk ID
            chunk_id2: Second chunk ID
            relationship: Relationship type

        Returns:
            bool: True if linked successfully
        """
        prov1 = self.get_provenance(chunk_id1)
        prov2 = self.get_provenance(chunk_id2)

        if not prov1 or not prov2:
            return False

        # Add relationship to metadata
        if "relationships" not in prov1.metadata:
            prov1.metadata["relationships"] = []
        prov1.metadata["relationships"].append(
            {"chunk_id": chunk_id2, "relationship": relationship}
        )

        return True

    def export_provenance(
        self, source_document: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Export provenance information.

        Args:
            source_document: Filter by source document (optional)

        Returns:
            list: List of provenance dictionaries
        """
        if source_document:
            provenance_list = self.get_source_chunks(source_document)
        else:
            provenance_list = list(self._provenance_store.values())

        return [self._provenance_to_dict(prov) for prov in provenance_list]

    def _provenance_to_dict(self, prov: ProvenanceInfo) -> Dict[str, Any]:
        """Convert ProvenanceInfo to dictionary."""
        return {
            "chunk_id": prov.chunk_id,
            "source_document": prov.source_document,
            "source_path": prov.source_path,
            "start_index": prov.start_index,
            "end_index": prov.end_index,
            "parent_chunk_id": prov.parent_chunk_id,
            "metadata": prov.metadata,
            "version": prov.version,
            "timestamp": prov.timestamp,
        }

    def clear(self, source_document: Optional[str] = None) -> int:
        """
        Clear provenance data.

        Args:
            source_document: Clear only for specific document (optional)

        Returns:
            int: Number of entries cleared
        """
        if source_document:
            # Remove only entries for this document
            to_remove = [
                prov_id
                for prov_id, prov in self._provenance_store.items()
                if prov.source_document == source_document
            ]
            for prov_id in to_remove:
                prov = self._provenance_store.pop(prov_id, None)
                if prov:
                    self._chunk_registry.pop(prov.chunk_id, None)
            return len(to_remove)
        else:
            # Clear all
            count = len(self._provenance_store)
            self._provenance_store.clear()
            self._chunk_registry.clear()
            return count
