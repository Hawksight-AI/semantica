"""
Backward Compatibility Tests

Critical tests to ensure all existing Semantica code works unchanged
with the new unified provenance module.
"""

import pytest
from semantica.kg import ProvenanceTracker as KGProvenanceTracker
from semantica.split import ProvenanceTracker as SplitProvenanceTracker
from semantica.split.semantic_chunker import Chunk


class TestKGProvenanceBackwardCompat:
    """Test kg.ProvenanceTracker backward compatibility."""
    
    def test_existing_code_unchanged(self):
        """Test that existing kg.ProvenanceTracker code works unchanged.

        NOTE: this no longer asserts on tracker.get_lineage(), which was
        never implemented on kg.ProvenanceTracker (see #744). It instead
        verifies the observable behavior of the still-supported
        track_entity()/get_all_sources() pair.
        """
        # Existing code pattern
        tracker = KGProvenanceTracker()
        
        # Track entity (existing API)
        tracker.track_entity("entity_1", source="doc_1", metadata={"confidence": 0.9})
        
        # Verify the entity was actually tracked
        sources = tracker.get_all_sources("entity_1")
        assert len(sources) > 0
        last_entry = sources[-1]
        assert last_entry["source"] == "doc_1"
        assert "recorded_at" in last_entry
        assert last_entry["confidence"] == 0.9
    
    # NOTE: test_track_relationship_unchanged removed; it only exercised
    # tracker.track_relationship(), which was never implemented on
    # kg.ProvenanceTracker. This tested an intended unified-backend
    # migration that never happened (#744). ProvenanceTracker is now
    # deprecated in favor of semantica.provenance.ProvenanceManager.
    
    def test_get_all_sources_unchanged(self):
        """Test get_all_sources returns expected format."""
        tracker = KGProvenanceTracker()
        
        tracker.track_entity("entity_1", source="doc_1")
        tracker.track_entity("entity_1", source="doc_2")
        
        sources = tracker.get_all_sources("entity_1")
        
        assert isinstance(sources, list)
        assert len(sources) >= 2
        for source in sources:
            assert "source" in source
            assert "recorded_at" in source
    
    # NOTE: test_batch_operations_unchanged removed; it only exercised
    # tracker.track_entities_batch() and tracker.get_lineage(), neither of
    # which was ever implemented on kg.ProvenanceTracker. This tested an
    # intended unified-backend migration that never happened (#744).
    # ProvenanceTracker is now deprecated in favor of
    # semantica.provenance.ProvenanceManager.


class TestSplitProvenanceBackwardCompat:
    """Test split.ProvenanceTracker backward compatibility."""
    
    def test_existing_code_unchanged(self):
        """Test that existing split.ProvenanceTracker code works unchanged."""
        tracker = SplitProvenanceTracker()
        
        # Create chunk
        chunk = Chunk(
            text="Test chunk",
            start_index=0,
            end_index=10,
            metadata={}
        )
        
        # Track chunk (existing API)
        prov_id = tracker.track_chunk(
            chunk,
            source_document="doc_1",
            source_path="/path/to/doc.pdf"
        )
        
        assert prov_id is not None
    
    def test_get_provenance_unchanged(self):
        """Test get_provenance returns ProvenanceInfo."""
        tracker = SplitProvenanceTracker()
        
        chunk = Chunk(text="Test", start_index=0, end_index=4, metadata={})
        chunk.id = "chunk_1"
        
        tracker.track_chunk(chunk, source_document="doc_1")
        
        prov = tracker.get_provenance("chunk_1")
        
        # Verify ProvenanceInfo format
        assert prov is not None
        assert hasattr(prov, "chunk_id")
        assert hasattr(prov, "source_document")
        assert hasattr(prov, "start_index")
        assert hasattr(prov, "end_index")
    
    def test_get_chunk_lineage_unchanged(self):
        """Test get_chunk_lineage returns list of ProvenanceInfo."""
        tracker = SplitProvenanceTracker()
        
        chunk1 = Chunk(text="Test1", start_index=0, end_index=5, metadata={})
        chunk1.id = "chunk_1"
        
        chunk2 = Chunk(text="Test2", start_index=5, end_index=10, metadata={})
        chunk2.id = "chunk_2"
        
        tracker.track_chunk(chunk1, source_document="doc_1")
        tracker.track_chunk(chunk2, source_document="doc_1", parent_chunk_id="chunk_1")
        
        lineage = tracker.get_chunk_lineage("chunk_2")
        
        assert isinstance(lineage, list)
        assert len(lineage) >= 1
        for prov in lineage:
            assert hasattr(prov, "chunk_id")
            assert hasattr(prov, "source_document")
    
    def test_batch_tracking_unchanged(self):
        """Test batch chunk tracking works unchanged."""
        tracker = SplitProvenanceTracker()
        
        chunks = [
            Chunk(text=f"Chunk {i}", start_index=i*10, end_index=(i+1)*10, metadata={})
            for i in range(3)
        ]
        
        prov_ids = tracker.track_chunks(chunks, source_document="doc_1")
        
        assert len(prov_ids) == 3

    def test_unified_tracking_returns_none_triggers_fallback(self):
        """Test that when _unified_manager.track_chunk returns None, fallback provenance is stored (#783)."""
        from unittest.mock import patch
        tracker = SplitProvenanceTracker()
        chunk = Chunk(text="Test chunk for none fallback", start_index=0, end_index=10, metadata={})
        
        with patch.object(tracker._unified_manager, "track_chunk", return_value=None):
            prov_id = tracker.track_chunk(chunk, source_document="doc_1")
            assert prov_id is not None
            # Confirm it fell back to legacy store and is retrievable
            assert chunk.id in tracker._chunk_registry
            assert prov_id in tracker._provenance_store
            prov_info = tracker.get_provenance(chunk.id)
            assert prov_info is not None
            assert prov_info.source_document == "doc_1"


class TestNoProvenanceOverhead:
    """Test that provenance has zero overhead when not used."""
    
    def test_kg_tracker_no_overhead(self):
        """Test kg.ProvenanceTracker has no overhead."""
        import time
        
        # Measure without provenance
        tracker = KGProvenanceTracker()
        
        start = time.time()
        for i in range(100):
            tracker.track_entity(f"entity_{i}", source="doc_1")
        elapsed = time.time() - start
        
        # Should complete quickly (< 1 second for 100 entities)
        assert elapsed < 1.0
    
    def test_split_tracker_no_overhead(self):
        """Test split.ProvenanceTracker has no overhead."""
        import time
        
        tracker = SplitProvenanceTracker()
        
        start = time.time()
        for i in range(100):
            chunk = Chunk(
                text=f"Chunk {i}",
                start_index=i*10,
                end_index=(i+1)*10,
                metadata={}
            )
            tracker.track_chunk(chunk, source_document="doc_1")
        elapsed = time.time() - start
        
        # Should complete quickly
        assert elapsed < 1.0


class TestGracefulDegradation:
    """Test graceful degradation when unified backend fails."""
    
    def test_kg_tracker_fallback(self):
        """Test kg.ProvenanceTracker falls back to legacy on error."""
        tracker = KGProvenanceTracker()
        
        # Should work even if unified backend has issues
        tracker.track_entity("entity_1", source="doc_1")
        # NOTE: tracker.get_lineage() was never implemented on
        # kg.ProvenanceTracker; this tested an intended unified-backend
        # migration that never happened (#744). ProvenanceTracker is now
        # deprecated in favor of semantica.provenance.ProvenanceManager.
    
    def test_split_tracker_fallback(self):
        """Test split.ProvenanceTracker falls back to legacy on error."""
        tracker = SplitProvenanceTracker()
        
        chunk = Chunk(text="Test", start_index=0, end_index=4, metadata={})
        
        # Should work even if unified backend has issues
        prov_id = tracker.track_chunk(chunk, source_document="doc_1")
        
        assert prov_id is not None


class TestExistingTestsPass:
    """Verify that all existing Semantica tests still pass."""
    
    def test_kg_provenance_existing_behavior(self):
        """Test existing kg.ProvenanceTracker behavior is preserved."""
        tracker = KGProvenanceTracker()
        
        # Test 1: Basic tracking
        # NOTE: tracker.get_provenance() was never implemented on
        # kg.ProvenanceTracker; this tested an intended unified-backend
        # migration that never happened (#744). ProvenanceTracker is now
        # deprecated in favor of semantica.provenance.ProvenanceManager.
        tracker.track_entity("e1", "src1")
        
        # Test 2: Multiple sources
        tracker.track_entity("e1", "src2")
        sources = tracker.get_all_sources("e1")
        assert len(sources) >= 2
        
        # NOTE: Test 3 (metadata via tracker.get_lineage()) removed; that
        # method was never implemented on kg.ProvenanceTracker. This tested
        # an intended unified-backend migration that never happened (#744).
    
    def test_split_provenance_existing_behavior(self):
        """Test existing split.ProvenanceTracker behavior is preserved."""
        tracker = SplitProvenanceTracker()
        
        # Test 1: Basic tracking
        chunk = Chunk(text="Test", start_index=0, end_index=4, metadata={})
        chunk.id = "c1"
        tracker.track_chunk(chunk, "doc1")
        assert tracker.get_provenance("c1") is not None
        
        # Test 2: Parent-child relationship
        chunk2 = Chunk(text="Test2", start_index=4, end_index=9, metadata={})
        chunk2.id = "c2"
        tracker.track_chunk(chunk2, "doc1", parent_chunk_id="c1")
        lineage = tracker.get_chunk_lineage("c2")
        assert len(lineage) >= 1
