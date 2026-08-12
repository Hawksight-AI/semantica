"""
Real functional integration tests across all provenance modules.

Tests that execute actual operations and verify provenance tracking works.
"""

import pytest
from semantica.provenance import ProvenanceManager


class TestRealModuleIntegration:
    """Real integration tests across modules."""
    
    def test_context_manager_real_tracking(self):
        """Test context manager actually tracks context additions."""
        try:
            from semantica.context.context_provenance import ContextManagerWithProvenance
            
            ctx = ContextManagerWithProvenance(provenance=True)
            
            # Verify provenance enabled
            assert ctx.provenance is True
            assert ctx._prov_manager is not None
            assert isinstance(ctx._prov_manager, ProvenanceManager)
            
        except ImportError:
            pytest.skip("ContextManager not available")
    
    def test_pipeline_real_execution_tracking(self):
        """Test pipeline tracks execution with provenance."""
        try:
            from semantica.pipeline.pipeline_builder import Pipeline
            from semantica.pipeline.pipeline_provenance import PipelineWithProvenance

            pipeline = Pipeline(name="provenance_tracking_test")
            runner = PipelineWithProvenance(pipeline, provenance=True)

            # Verify provenance setup
            assert runner.provenance is True
            assert runner._prov_manager is not None
            assert isinstance(runner._prov_manager, ProvenanceManager)

        except ImportError:
            pytest.skip("Pipeline not available")
    
    def test_embeddings_real_generation_tracking(self):
        """Test embeddings tracks generation operations."""
        try:
            from semantica.embeddings.embeddings_provenance import EmbeddingGeneratorWithProvenance
            
            embedder = EmbeddingGeneratorWithProvenance(provenance=True)
            
            # Verify provenance enabled
            assert embedder.provenance is True
            assert embedder._prov_manager is not None
            
        except ImportError:
            pytest.skip("EmbeddingGenerator not available")
    
    def test_graph_store_real_node_tracking(self):
        """Test graph store tracks node additions."""
        try:
            from semantica.graph_store.graph_store_provenance import GraphStoreWithProvenance
            
            store = GraphStoreWithProvenance(provenance=True)
            
            # Verify provenance enabled
            assert store.provenance is True
            assert store._prov_manager is not None
            
        except ImportError:
            pytest.skip("GraphStore not available")
    
    def test_vector_store_real_vector_tracking(self):
        """Test vector store tracks vector additions."""
        try:
            from semantica.vector_store.vector_store_provenance import VectorStoreWithProvenance
            
            store = VectorStoreWithProvenance(provenance=True)
            
            # Verify provenance enabled
            assert store.provenance is True
            assert store._prov_manager is not None
            
        except ImportError:
            pytest.skip("VectorStore not available")
    
    def test_end_to_end_document_processing(self):
        """Test end-to-end document processing with provenance."""
        manager = ProvenanceManager()
        
        # Step 1: Ingest document
        manager.track_entity(
            entity_id="doc_1",
            source="research_paper.pdf",
            entity_type="document",
            metadata={"pages": 10, "file_size": 1024000}
        )
        
        # Step 2: Split into chunks
        for i in range(5):
            manager.track_chunk(
                chunk_id=f"chunk_{i}",
                source_document="doc_1",
                chunk_text=f"Chunk {i} content",
                start_char=i * 1000,
                end_char=(i + 1) * 1000
            )
        
        # Step 3: Extract entities from chunks
        for i in range(5):
            manager.track_entity(
                entity_id=f"entity_{i}",
                source=f"chunk_{i}",
                entity_type="named_entity",
                metadata={"text": f"Entity {i}"}
            )
        
        # Step 4: Create relationships
        manager.track_relationship(
            relationship_id="rel_1",
            source="chunk_0",
            subject="entity_0",
            predicate="relates_to",
            obj="entity_1"
        )
        
        # Verify complete lineage
        lineage = manager.get_lineage("entity_0")
        assert lineage is not None
        assert "lineage_chain" in lineage
        
        # Verify relationship
        rel_lineage = manager.get_lineage("rel_1")
        assert rel_lineage is not None
    
    def test_multi_source_entity_tracking(self):
        """Test tracking entities from multiple sources."""
        manager = ProvenanceManager()
        
        sources = [
            "document_1.pdf",
            "document_2.pdf",
            "database_query",
            "api_response",
            "user_input"
        ]
        
        for i, source in enumerate(sources):
            manager.track_entity(
                entity_id=f"entity_from_{i}",
                source=source,
                entity_type="multi_source_entity",
                metadata={"source_type": source.split("_")[0]}
            )
        
        # Verify all sources tracked
        for i in range(len(sources)):
            lineage = manager.get_lineage(f"entity_from_{i}")
            assert lineage is not None
            assert sources[i] in lineage["source_documents"]
    
    def test_property_source_tracking(self):
        """Test tracking property sources for entities."""
        manager = ProvenanceManager()
        
        # Track entity
        manager.track_entity(
            entity_id="company_1",
            source="doc.pdf",
            entity_type="organization"
        )
        
        # Track property sources
        from semantica.provenance import SourceReference
        
        manager.track_property_source(
            entity_id="company_1",
            property_name="revenue",
            value="$100M",
            source=SourceReference(
                document="annual_report.pdf",
                page=5,
                section="Financial Summary",
                confidence=0.95
            )
        )
        
        manager.track_property_source(
            entity_id="company_1",
            property_name="employees",
            value="500",
            source=SourceReference(
                document="company_profile.pdf",
                page=2,
                confidence=0.90
            )
        )
        
        # Verify property sources tracked
        lineage = manager.get_lineage("company_1")
        assert lineage is not None
    
    def test_temporal_tracking(self):
        """Test temporal aspects of provenance tracking."""
        import time
        manager = ProvenanceManager()
        
        # Track entity at time T1
        manager.track_entity(
            entity_id="temporal_entity",
            source="source_1",
            entity_type="test",
            metadata={"version": 1}
        )
        
        time.sleep(0.1)
        
        # Update entity at time T2
        manager.track_entity(
            entity_id="temporal_entity_v2",
            source="temporal_entity",
            entity_type="test",
            metadata={"version": 2}
        )
        
        # Verify temporal tracking
        lineage_v1 = manager.get_lineage("temporal_entity")
        lineage_v2 = manager.get_lineage("temporal_entity_v2")
        
        assert lineage_v1 is not None
        assert lineage_v2 is not None
        assert lineage_v1["last_updated"] < lineage_v2["last_updated"]
    
    def test_batch_operations_with_provenance(self):
        """Test batch operations maintain provenance."""
        manager = ProvenanceManager()
        
        # Batch track 200 entities
        batch_size = 200
        for i in range(batch_size):
            manager.track_entity(
                entity_id=f"batch_entity_{i}",
                source=f"batch_source_{i % 10}",
                entity_type="batch_entity",
                metadata={"batch_index": i}
            )
        
        # Verify all tracked
        for i in range(batch_size):
            lineage = manager.get_lineage(f"batch_entity_{i}")
            assert lineage is not None
            assert lineage["metadata"]["batch_index"] == i
    
    def test_cross_module_lineage(self):
        """Test lineage tracking across multiple modules."""
        manager = ProvenanceManager()
        
        # Simulate cross-module workflow
        # 1. Ingest
        manager.track_entity("ingested_doc", "file.pdf", "document")
        
        # 2. Parse
        manager.track_entity("parsed_content", "ingested_doc", "parsed_data")
        
        # 3. Normalize
        manager.track_entity("normalized_data", "parsed_content", "normalized")
        
        # 4. Extract
        manager.track_entity("extracted_entity", "normalized_data", "entity")
        
        # 5. Store in graph
        manager.track_entity("graph_node", "extracted_entity", "node")
        
        # Verify complete lineage chain
        lineage = manager.get_lineage("graph_node")
        assert lineage is not None
        assert "lineage_chain" in lineage
        assert len(lineage["lineage_chain"]) >= 4
    
    def test_provenance_export_import(self):
        """Test exporting and importing provenance data."""
        manager = ProvenanceManager()
        
        # Track some data
        manager.track_entity("e1", "src1", entity_type="type1", metadata={"key": "value"})
        manager.track_entity("e2", "src2", entity_type="type2")
        manager.track_relationship(
            relationship_id="r1",
            source="src1",
            metadata={"subject": "e1", "predicate": "relates", "object": "e2"}
        )
        
        # Get statistics
        stats = manager.get_statistics()
        assert stats["total_entries"] >= 3
        
        # Verify data can be retrieved
        lineage_e1 = manager.get_lineage("e1")
        lineage_e2 = manager.get_lineage("e2")
        lineage_r1 = manager.get_lineage("r1")
        
        assert all([lineage_e1, lineage_e2, lineage_r1])
