"""
Tests for Vector Store Backward Compatibility

This module contains comprehensive tests to ensure that all existing VectorStore
functionality works unchanged after adding decision tracking features.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch

from semantica.vector_store import VectorStore


class TestVectorStoreBackwardCompatibility:
    """Test cases for VectorStore backward compatibility."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create vector store with default configuration
        self.vector_store = VectorStore(backend="inmemory", dimension=384)
        
        # Sample vectors and metadata
        self.sample_vectors = [
            np.array([0.1, 0.2, 0.3, 0.4]),
            np.array([0.2, 0.3, 0.4, 0.5]),
            np.array([0.3, 0.4, 0.5, 0.6])
        ]
        
        self.sample_metadata = [
            {"type": "document", "title": "Doc 1"},
            {"type": "document", "title": "Doc 2"},
            {"type": "document", "title": "Doc 3"}
        ]
    
    def test_basic_initialization(self):
        """Test basic vector store initialization unchanged."""
        store = VectorStore(backend="inmemory", dimension=768)
        
        assert store.backend == "inmemory"
        assert store.dimension == 768
        assert hasattr(store, 'vectors')
        assert hasattr(store, 'metadata')
        assert hasattr(store, 'indexer')
        assert hasattr(store, 'retriever')
    
    def test_store_vectors_unchanged(self):
        """Test store_vectors method unchanged."""
        vector_ids = self.vector_store.store_vectors(self.sample_vectors, self.sample_metadata)
        
        assert len(vector_ids) == 3
        assert all(isinstance(vid, str) for vid in vector_ids)
        assert len(self.vector_store.vectors) == 3
        assert len(self.vector_store.metadata) == 3
    
    def test_store_convenience_method_unchanged(self):
        """Test store convenience method unchanged."""
        vector_ids = self.vector_store.store(
            vectors=self.sample_vectors,
            metadata=self.sample_metadata
        )
        
        assert len(vector_ids) == 3
        assert len(self.vector_store.vectors) == 3
    
    def test_search_vectors_unchanged(self):
        """Test search_vectors method unchanged."""
        # Store some vectors first
        self.vector_store.store_vectors(self.sample_vectors, self.sample_metadata)
        
        # Search
        query_vector = np.array([0.15, 0.25, 0.35, 0.45])
        results = self.vector_store.search_vectors(query_vector, k=2)
        
        assert len(results) == 2
        assert all("id" in result for result in results)
        assert all("score" in result for result in results)
        assert all("vector" in result for result in results)
        assert all("metadata" in result for result in results)
        assert all(isinstance(result["metadata"], dict) for result in results)
    
    def test_search_method_unchanged(self):
        """Test search method unchanged."""
        # Store some vectors first
        self.vector_store.store_vectors(self.sample_vectors, self.sample_metadata)
        
        # Mock embed method
        with patch.object(self.vector_store, 'embed', return_value=np.array([0.1, 0.2, 0.3, 0.4])):
            results = self.vector_store.search("test query", limit=2)
        
        assert len(results) <= 2
        assert all("id" in result for result in results)
        assert all("score" in result for result in results)
    
    def test_update_vectors_unchanged(self):
        """Test update_vectors method unchanged."""
        # Store vectors first
        vector_ids = self.vector_store.store_vectors(self.sample_vectors, self.sample_metadata)
        
        # Update vectors
        new_vectors = [
            np.array([0.9, 0.8, 0.7, 0.6]),
            np.array([0.8, 0.7, 0.6, 0.5]),
            np.array([0.7, 0.6, 0.5, 0.4])
        ]
        
        success = self.vector_store.update_vectors(vector_ids, new_vectors)
        assert success == True
        
        # Verify updates
        for vid in vector_ids:
            assert vid in self.vector_store.vectors
    
    def test_delete_vectors_unchanged(self):
        """Test delete_vectors method unchanged."""
        # Store vectors first
        vector_ids = self.vector_store.store_vectors(self.sample_vectors, self.sample_metadata)
        
        # Delete vectors
        success = self.vector_store.delete_vectors(vector_ids[:2])
        assert success == True
        
        # Verify deletions
        assert len(self.vector_store.vectors) == 1
        assert len(self.vector_store.metadata) == 1
    
    def test_get_vector_unchanged(self):
        """Test get_vector method unchanged."""
        # Store vectors first
        vector_ids = self.vector_store.store_vectors(self.sample_vectors, self.sample_metadata)
        
        # Get vector
        vector = self.vector_store.get_vector(vector_ids[0])
        assert vector is not None
        assert isinstance(vector, np.ndarray)
        assert np.array_equal(vector, self.sample_vectors[0])
    
    def test_get_metadata_unchanged(self):
        """Test get_metadata method unchanged."""
        # Store vectors first
        vector_ids = self.vector_store.store_vectors(self.sample_vectors, self.sample_metadata)
        
        # Get metadata
        metadata = self.vector_store.get_metadata(vector_ids[0])
        assert metadata is not None
        assert metadata["type"] == "document"
        assert metadata["title"] == "Doc 1"
    
    def test_add_documents_unchanged(self):
        """Test add_documents method unchanged."""
        documents = ["Document 1 content", "Document 2 content"]
        metadata = [{"source": "web"}, {"source": "file"}]
        
        # Mock embed_batch method
        with patch.object(self.vector_store, 'embed_batch', return_value=self.sample_vectors[:2]):
            vector_ids = self.vector_store.add_documents(documents, metadata)
        
        assert len(vector_ids) == 2
        assert len(self.vector_store.vectors) == 2
    
    def test_save_load_unchanged(self):
        """Test save and load methods unchanged."""
        # Store some data
        self.vector_store.store_vectors(self.sample_vectors, self.sample_metadata)
        
        # Save
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as temp_dir:
            self.vector_store.save(temp_dir)
            
            # Create new store and load
            new_store = VectorStore(backend="inmemory", dimension=384)
            new_store.load(temp_dir)
            
            # Verify loaded data
            assert len(new_store.vectors) == len(self.vector_store.vectors)
            assert len(new_store.metadata) == len(self.vector_store.metadata)
    
    def test_embed_method_unchanged(self):
        """Test embed method unchanged."""
        # Mock embedder
        with patch.object(self.vector_store.embedder, 'generate_embeddings', return_value=np.array([0.1, 0.2, 0.3, 0.4])):
            embedding = self.vector_store.embed("test text")
        
        assert isinstance(embedding, np.ndarray)
        assert len(embedding) > 0
    
    def test_embed_batch_method_unchanged(self):
        """Test embed_batch method unchanged."""
        texts = ["text 1", "text 2", "text 3"]
        
        # Mock embedder
        with patch.object(self.vector_store.embedder, 'generate_embeddings', return_value=self.sample_vectors):
            embeddings = self.vector_store.embed_batch(texts)
        
        assert len(embeddings) == 3
        assert all(isinstance(emb, np.ndarray) for emb in embeddings)
    
    def test_indexer_and_retriever_unchanged(self):
        """Test indexer and retriever unchanged."""
        assert hasattr(self.vector_store, 'indexer')
        assert hasattr(self.vector_store, 'retriever')
        
        # Test indexer
        vectors = [np.array([0.1, 0.2]), np.array([0.3, 0.4])]
        ids = ["vec1", "vec2"]
        
        index = self.vector_store.indexer.create_index(vectors, ids)
        assert index is not None
        
        # Test retriever
        query_vector = np.array([0.2, 0.3])
        results = self.vector_store.retriever.search_similar(
            query_vector, vectors, ids, k=2
        )
        
        assert len(results) == 2
        assert all("id" in result for result in results)
    
    def test_configuration_unchanged(self):
        """Test configuration handling unchanged."""
        config = {"dimension": 512, "custom_param": "test"}
        store = VectorStore(backend="inmemory", config=config)
        
        assert store.dimension == 512
        assert store.config["custom_param"] == "test"
    
    def test_error_handling_unchanged(self):
        """Test error handling unchanged."""
        # Test invalid backend
        with pytest.raises(ValueError, match="Unsupported backend"):
            VectorStore(backend="invalid_backend")
        
        # Test empty vectors
        results = self.vector_store.search_vectors(np.array([0.1, 0.2]), k=5)
        assert results == []
    
    def test_progress_tracking_unchanged(self):
        """Test progress tracking unchanged."""
        assert hasattr(self.vector_store, 'progress_tracker')
        assert self.vector_store.progress_tracker.enabled == True
    
    def test_logging_unchanged(self):
        """Test logging unchanged."""
        assert hasattr(self.vector_store, 'logger')
        # Logger name may include module prefix, so check it contains expected name
        assert "vector_store" in self.vector_store.logger.name


class TestVectorStoreNewFeaturesCompatibility:
    """Test that new features don't break existing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.vector_store = VectorStore(backend="inmemory", dimension=384)
    
    def test_new_attributes_exist_but_dont_interfere(self):
        """Test that new attributes exist but don't interfere with existing functionality."""
        # New attributes should exist
        assert hasattr(self.vector_store, 'hybrid_calculator')
        assert hasattr(self.vector_store, 'decision_pipeline')
        
        # But existing functionality should work
        vectors = [np.array([0.1, 0.2, 0.3, 0.4])]
        vector_ids = self.vector_store.store_vectors(vectors)
        
        assert len(vector_ids) == 1
        assert vector_ids[0] in self.vector_store.vectors
    
    def test_decision_pipeline_initialization_optional(self):
        """Test that decision pipeline initialization is optional."""
        # Should work without graph store
        store = VectorStore(backend="inmemory", dimension=384)
        
        # Existing functionality should work
        vectors = [np.array([0.1, 0.2, 0.3, 0.4])]
        vector_ids = store.store_vectors(vectors)
        
        assert len(vector_ids) == 1
    
    def test_hybrid_calculator_initialization_optional(self):
        """Test that hybrid calculator initialization is optional."""
        # Should work without any special setup
        store = VectorStore(backend="inmemory", dimension=384)
        
        # Existing functionality should work
        query_vector = np.array([0.1, 0.2, 0.3, 0.4])
        results = store.search_vectors(query_vector)
        
        assert isinstance(results, list)
    
    def test_existing_methods_signatures_unchanged(self):
        """Test that existing method signatures are unchanged."""
        store = VectorStore(backend="inmemory", dimension=384)
        
        # Check method signatures
        import inspect
        
        # store_vectors
        sig = inspect.signature(store.store_vectors)
        params = list(sig.parameters.keys())
        assert 'vectors' in params
        assert 'metadata' in params
        assert 'options' in params
        
        # search_vectors
        sig = inspect.signature(store.search_vectors)
        params = list(sig.parameters.keys())
        assert 'query_vector' in params
        assert 'k' in params
        assert 'options' in params
        
        # update_vectors
        sig = inspect.signature(store.update_vectors)
        params = list(sig.parameters.keys())
        assert 'vector_ids' in params
        assert 'new_vectors' in params
        assert 'options' in params
    
    def test_existing_return_types_unchanged(self):
        """Test that existing method return types are unchanged."""
        store = VectorStore(backend="inmemory", dimension=384)
        
        vectors = [np.array([0.1, 0.2, 0.3, 0.4])]
        metadata = [{"type": "test"}]
        
        # store_vectors should return List[str]
        vector_ids = store.store_vectors(vectors, metadata)
        assert isinstance(vector_ids, list)
        assert all(isinstance(vid, str) for vid in vector_ids)
        
        # search_vectors should return List[Dict[str, Any]]
        query_vector = np.array([0.1, 0.2, 0.3, 0.4])
        results = store.search_vectors(query_vector)
        assert isinstance(results, list)
        assert all(isinstance(result, dict) for result in results)
        
        # update_vectors should return bool
        success = store.update_vectors(vector_ids, vectors)
        assert isinstance(success, bool)
        
        # delete_vectors should return bool
        success = store.delete_vectors(vector_ids)
        assert isinstance(success, bool)
        
        # get_vector should return Optional[np.ndarray]
        vector = store.get_vector(vector_ids[0])
        assert vector is None or isinstance(vector, np.ndarray)
        
        # get_metadata should return Optional[Dict[str, Any]]
        metadata = store.get_metadata(vector_ids[0])
        assert metadata is None or isinstance(metadata, dict)


class TestVectorStorePerformanceCompatibility:
    """Test that performance characteristics remain compatible."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.vector_store = VectorStore(backend="inmemory", dimension=384)
    
    def test_basic_performance_unchanged(self):
        """Test that basic performance characteristics are unchanged."""
        import time
        
        # Store performance
        vectors = [np.random.rand(384) for _ in range(100)]
        start_time = time.time()
        vector_ids = self.vector_store.store_vectors(vectors)
        store_time = time.time() - start_time
        
        assert len(vector_ids) == 100
        assert store_time < 5.0  # Should be reasonably fast
        
        # Search performance
        query_vector = np.random.rand(384)
        start_time = time.time()
        results = self.vector_store.search_vectors(query_vector, k=10)
        search_time = time.time() - start_time
        
        assert len(results) == 10
        assert search_time < 1.0  # Should be fast
    
    def test_memory_usage_reasonable(self):
        """Test that memory usage is reasonable."""
        import sys
        
        # Store a reasonable number of vectors
        vectors = [np.random.rand(384) for _ in range(1000)]
        self.vector_store.store_vectors(vectors)
        
        # Check that memory usage is reasonable (basic check)
        vector_count = len(self.vector_store.vectors)
        metadata_count = len(self.vector_store.metadata)
        
        assert vector_count == 1000
        assert metadata_count == 1000
        
        # Basic memory check - should not be excessively large
        store_size = sys.getsizeof(self.vector_store.vectors) + sys.getsizeof(self.vector_store.metadata)
        assert store_size < 100_000_000  # Less than 100MB for 1000 vectors


if __name__ == "__main__":
    pytest.main([__file__])
