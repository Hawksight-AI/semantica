"""
Tests for Decision Embedding Pipeline

This module contains comprehensive tests for the decision embedding pipeline
functionality, including decision processing, batch operations, and similarity
search.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from semantica.vector_store.decision_embedding_pipeline import DecisionEmbeddingPipeline


class TestDecisionEmbeddingPipeline:
    """Test cases for DecisionEmbeddingPipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock vector store
        self.mock_vector_store = Mock()
        self.mock_vector_store.embed.return_value = np.array([0.1, 0.2, 0.3, 0.4])
        
        # Mock graph store
        self.mock_graph_store = Mock()
        
        # Create pipeline
        self.pipeline = DecisionEmbeddingPipeline(
            vector_store=self.mock_vector_store,
            graph_store=self.mock_graph_store,
            auto_embed=True
        )
        
        # Sample decision data
        self.sample_decision = {
            "scenario": "Credit limit increase request",
            "reasoning": "Good payment history",
            "outcome": "approved",
            "confidence": 0.85,
            "entities": ["customer_123", "credit_card"],
            "category": "credit_approval"
        }
    
    def test_initialization(self):
        """Test pipeline initialization."""
        assert self.pipeline.vector_store == self.mock_vector_store
        assert self.pipeline.graph_store == self.mock_graph_store
        assert self.pipeline.auto_embed == True
        assert self.pipeline.semantic_weight == 0.7
        assert self.pipeline.structural_weight == 0.3
    
    def test_initialization_without_graph_store(self):
        """Test pipeline initialization without graph store."""
        pipeline = DecisionEmbeddingPipeline(
            vector_store=self.mock_vector_store,
            graph_store=None
        )
        
        assert pipeline.graph_store is None
        assert pipeline.node_embedder is None
    
    def test_process_decision(self):
        """Test processing a single decision."""
        # Mock vector store methods
        self.mock_vector_store.store_vectors.return_value = ["decision_123"]
        
        result = self.pipeline.process_decision(self.sample_decision)
        
        assert "decision_data" in result
        assert "semantic_embedding" in result
        assert "structural_embedding" in result
        assert "combined_embedding" in result
        assert "metadata" in result
        assert "vector_id" in result
        assert "processed_at" in result
        
        assert result["vector_id"] == "decision_123"
        assert isinstance(result["semantic_embedding"], np.ndarray)
        assert result["decision_data"]["scenario"] == self.sample_decision["scenario"]
    
    def test_process_decision_without_graph_store(self):
        """Test processing decision without graph store."""
        pipeline = DecisionEmbeddingPipeline(
            vector_store=self.mock_vector_store,
            graph_store=None
        )
        
        self.mock_vector_store.store_vectors.return_value = ["decision_123"]
        
        result = pipeline.process_decision(self.sample_decision)
        
        assert result["structural_embedding"] is None
        assert result["vector_id"] == "decision_123"
    
    def test_process_decision_batch(self):
        """Test processing multiple decisions in batch."""
        decisions = [
            self.sample_decision,
            {
                "scenario": "Fraud detection alert",
                "reasoning": "Suspicious activity pattern",
                "outcome": "blocked",
                "confidence": 0.95,
                "entities": ["transaction_456"],
                "category": "fraud_detection"
            }
        ]
        
        # Mock vector store methods
        self.mock_vector_store.store_vectors.return_value = ["decision_1", "decision_2"]
        
        results = self.pipeline.process_decision_batch(decisions, batch_size=2)
        
        assert len(results) == 2
        assert all("decision_data" in result for result in results)
        assert all("semantic_embedding" in result for result in results)
        assert all("vector_id" in result for result in results)
    
    def test_process_decision_batch_empty(self):
        """Test processing empty decision batch."""
        results = self.pipeline.process_decision_batch([])
        assert results == []
    
    def test_validate_decision_data(self):
        """Test decision data validation."""
        # Valid decision
        validated = self.pipeline._validate_decision_data(self.sample_decision)
        assert validated["scenario"] == self.sample_decision["scenario"]
        assert "outcome" in validated
        assert "confidence" in validated
        assert "timestamp" in validated
        
        # Missing required field
        invalid_decision = {"reasoning": "test"}
        with pytest.raises(ValueError, match="Missing required field: scenario"):
            self.pipeline._validate_decision_data(invalid_decision)
    
    def test_generate_semantic_embedding(self):
        """Test semantic embedding generation."""
        embedding = self.pipeline._generate_semantic_embedding(self.sample_decision)
        
        assert isinstance(embedding, np.ndarray)
        assert len(embedding) > 0
        
        # Verify vector store embed was called
        self.mock_vector_store.embed.assert_called()
    
    def test_generate_semantic_embedding_fallback(self):
        """Test semantic embedding generation fallback."""
        # Mock embed to raise exception
        self.mock_vector_store.embed.side_effect = Exception("Embedding failed")
        
        embedding = self.pipeline._generate_semantic_embedding(self.sample_decision)
        
        assert isinstance(embedding, np.ndarray)
        assert len(embedding) == self.pipeline.embedding_dimension
    
    def test_generate_structural_embedding(self):
        """Test structural embedding generation."""
        # Mock node embedder
        mock_node_embedder = Mock()
        mock_node_embedder.compute_embeddings.return_value = {
            "customer_123": [0.1, 0.2, 0.3],
            "credit_card": [0.4, 0.5, 0.6]
        }
        self.pipeline.node_embedder = mock_node_embedder
        
        embedding = self.pipeline._generate_structural_embedding(self.sample_decision)
        
        assert isinstance(embedding, np.ndarray)
        assert len(embedding) > 0
    
    def test_generate_structural_embedding_no_entities(self):
        """Test structural embedding without entities."""
        decision_no_entities = {
            "scenario": "Test decision",
            "category": "test"
        }
        
        embedding = self.pipeline._generate_structural_embedding(decision_no_entities)
        
        assert isinstance(embedding, np.ndarray)
        assert len(embedding) == self.pipeline.node_embedding_dimension
    
    def test_generate_structural_embedding_no_graph_store(self):
        """Test structural embedding without graph store."""
        pipeline = DecisionEmbeddingPipeline(
            vector_store=self.mock_vector_store,
            graph_store=None
        )
        
        embedding = pipeline._generate_structural_embedding(self.sample_decision)
        
        assert embedding is None
    
    def test_create_combined_embedding(self):
        """Test combined embedding creation."""
        semantic = np.array([0.1, 0.2, 0.3, 0.4])
        structural = np.array([0.5, 0.6, 0.7, 0.8])
        
        combined = self.pipeline._create_combined_embedding(semantic, structural)
        
        assert isinstance(combined, np.ndarray)
        assert len(combined) == len(semantic)
        assert len(combined) == len(structural)
    
    def test_create_combined_embedding_mismatched_dimensions(self):
        """Test combined embedding with mismatched dimensions."""
        semantic = np.array([0.1, 0.2, 0.3, 0.4])
        structural = np.array([0.5, 0.6, 0.7])
        
        combined = self.pipeline._create_combined_embedding(semantic, structural)
        
        assert isinstance(combined, np.ndarray)
        assert len(combined) == max(len(semantic), len(structural))
    
    def test_create_combined_embedding_no_structural(self):
        """Test combined embedding without structural component."""
        semantic = np.array([0.1, 0.2, 0.3, 0.4])
        
        combined = self.pipeline._create_combined_embedding(semantic, None)
        
        assert np.array_equal(combined, semantic)
    
    def test_enrich_metadata(self):
        """Test metadata enrichment."""
        enriched = self.pipeline._enrich_metadata(self.sample_decision)
        
        assert "pipeline_version" in enriched
        assert "embedding_generated_at" in enriched
        assert "semantic_weight" in enriched
        assert "structural_weight" in enriched
        assert "has_structural_embedding" in enriched
        
        assert enriched["semantic_weight"] == 0.7
        assert enriched["structural_weight"] == 0.3
        assert enriched["has_structural_embedding"] == True
    
    def test_find_similar_decisions(self):
        """Test finding similar decisions."""
        # Mock pipeline methods
        mock_process_result = {
            "semantic_embedding": np.array([0.1, 0.2, 0.3, 0.4]),
            "structural_embedding": np.array([0.5, 0.6, 0.7, 0.8])
        }
        
        with patch.object(self.pipeline, 'process_decision', return_value=mock_process_result):
            with patch.object(self.pipeline, '_get_candidate_embeddings', return_value={
                "embeddings": [
                    (np.array([0.1, 0.2, 0.3, 0.4]), np.array([0.5, 0.6, 0.7, 0.8]))
                ],
                "metadata": [{"category": "credit_approval"}]
            }):
                results = self.pipeline.find_similar_decisions(
                    self.sample_decision, limit=5
                )
        
        assert len(results) <= 5
        assert all("similarity" in result for result in results)
        assert all("metadata" in result for result in results)
    
    def test_find_similar_decisions_semantic_only(self):
        """Test finding similar decisions with semantic search only."""
        # Mock pipeline methods
        mock_process_result = {
            "semantic_embedding": np.array([0.1, 0.2, 0.3, 0.4]),
            "structural_embedding": None
        }
        
        with patch.object(self.pipeline, 'process_decision', return_value=mock_process_result):
            with patch.object(self.pipeline, '_get_candidate_embeddings', return_value={
                "embeddings": [
                    (np.array([0.1, 0.2, 0.3, 0.4]), np.array([0.5, 0.6, 0.7, 0.8]))
                ],
                "metadata": [{"category": "credit_approval"}]
            }):
                results = self.pipeline.find_similar_decisions(
                    self.sample_decision, use_hybrid_search=False
                )
        
        assert len(results) > 0
        assert all("similarity" in result for result in results)
    
    def test_update_weights(self):
        """Test updating similarity weights."""
        self.pipeline.update_weights(0.6, 0.4)
        
        assert self.pipeline.semantic_weight == 0.6
        assert self.pipeline.structural_weight == 0.4
    
    def test_update_weights_invalid(self):
        """Test updating with invalid weights."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            self.pipeline.update_weights(0.8, 0.3)
    
    def test_get_statistics(self):
        """Test getting pipeline statistics."""
        stats = self.pipeline.get_statistics()
        
        assert "total_decisions_processed" in stats
        assert "semantic_weight" in stats
        assert "structural_weight" in stats
        assert "embedding_dimension" in stats
        assert "node_embedding_dimension" in stats
        assert "has_graph_store" in stats
        assert "cached_structural_embeddings" in stats
        
        assert stats["semantic_weight"] == 0.7
        assert stats["structural_weight"] == 0.3
        assert stats["has_graph_store"] == True


class TestDecisionEmbeddingPipelineEdgeCases:
    """Test edge cases for DecisionEmbeddingPipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_vector_store = Mock()
        self.mock_vector_store.embed.return_value = np.array([0.1, 0.2, 0.3, 0.4])
        
        self.pipeline = DecisionEmbeddingPipeline(
            vector_store=self.mock_vector_store,
            graph_store=None
        )
    
    def test_process_decision_minimal_data(self):
        """Test processing decision with minimal data."""
        minimal_decision = {"scenario": "Test scenario"}
        
        self.mock_vector_store.store_vectors.return_value = ["decision_123"]
        
        result = self.pipeline.process_decision(minimal_decision)
        
        assert result["decision_data"]["scenario"] == "Test scenario"
        assert result["decision_data"]["outcome"] == "unknown"
        assert result["decision_data"]["confidence"] == 0.5
        assert result["decision_data"]["entities"] == []
        assert result["decision_data"]["category"] == "general"
    
    def test_process_decision_with_special_characters(self):
        """Test processing decision with special characters."""
        special_decision = {
            "scenario": "Credit limit increase for customer with émojis 🚀",
            "reasoning": "Payment history shows ✅ good behavior",
            "outcome": "approved ✓"
        }
        
        self.mock_vector_store.store_vectors.return_value = ["decision_123"]
        
        result = self.pipeline.process_decision(special_decision)
        
        assert result["decision_data"]["scenario"] == special_decision["scenario"]
        assert result["decision_data"]["reasoning"] == special_decision["reasoning"]
        assert result["decision_data"]["outcome"] == special_decision["outcome"]
    
    def test_process_decision_very_long_text(self):
        """Test processing decision with very long text."""
        long_text = "Test " * 1000  # Very long text
        long_decision = {
            "scenario": long_text,
            "reasoning": long_text,
            "outcome": long_text
        }
        
        self.mock_vector_store.store_vectors.return_value = ["decision_123"]
        
        result = self.pipeline.process_decision(long_decision)
        
        assert result["decision_data"]["scenario"] == long_text
        assert isinstance(result["semantic_embedding"], np.ndarray)
    
    def test_process_decision_batch_with_mixed_data(self):
        """Test processing batch with mixed decision data."""
        decisions = [
            {"scenario": "Simple decision"},
            {
                "scenario": "Complex decision",
                "reasoning": "Detailed reasoning",
                "outcome": "approved",
                "confidence": 0.95,
                "entities": ["entity1", "entity2"],
                "category": "complex"
            },
            {"scenario": "Another simple decision"}
        ]
        
        self.mock_vector_store.store_vectors.return_value = ["d1", "d2", "d3"]
        
        results = self.pipeline.process_decision_batch(decisions)
        
        assert len(results) == 3
        assert all("decision_data" in result for result in results)
        assert all("vector_id" in result for result in results)

    def test_find_similar_decisions_real_faiss_backend(self):
        """Regression test for FAISS backend crashing due to .vectors access (issue #839)"""
        # Skip if faiss is not installed
        pytest.importorskip("faiss")
        
        try:
            from semantica.vector_store import VectorStore
        except ImportError:
            pytest.skip("VectorStore not available")
            
        # Create a real VectorStore with FAISS backend
        vs = VectorStore(backend="faiss", config={"dimension": 384})
        # Force fallback random embeddings of the exact dimension (384) to avoid sentence-transformers 
        # dependency or default 128-d mismatches.
        vs.embedder = None
        vs.initialize_decision_pipeline()
        
        # Store a couple of dummy decisions to ensure index has data
        vs.store_decision(scenario="A test decision 1", category="test")
        vs.store_decision(scenario="A test decision 2", category="test")
        
        # This will call _get_candidate_embeddings without a mock
        # Before the fix, this crashed with AttributeError: 'VectorStore' object has no attribute 'vectors'
        results = vs.search_decisions("test query", limit=2)
        
        # Assert it returns results and doesn't crash
        assert isinstance(results, list)
        assert len(results) <= 2


    def test_find_similar_decisions_real_inmemory_backend(self):
        """Regression test for inmemory backend preserving behavior after issue #839 fix"""
        try:
            from semantica.vector_store import VectorStore
        except ImportError:
            pytest.skip("VectorStore not available")
            
        vs = VectorStore(backend="inmemory", config={"dimension": 384})
        vs.embedder = None
        vs.initialize_decision_pipeline()
        
        vs.store_decision(scenario="Apple product launch", category="tech")
        vs.store_decision(scenario="Microsoft earnings report", category="tech")
        vs.store_decision(scenario="Local bakery opens", category="food")
        
        results = vs.search_decisions("software company", limit=2)
        
        assert isinstance(results, list)
        assert len(results) <= 2
        
        if len(results) > 0:
            assert "similarity" in results[0]
            assert "semantic_similarity" in results[0]
            assert "structural_similarity" in results[0]

    def test_get_candidate_embeddings_returns_partial_matches_when_pool_exhausted(self):
        """Regression test: _get_candidate_embeddings must not discard matches found
        in its final retry iteration when the expand-and-retry loop exhausts max_k
        without ever crossing `limit` matches or getting a short page back."""
        pipeline = DecisionEmbeddingPipeline.__new__(DecisionEmbeddingPipeline)
        pipeline.vector_store = Mock()
        pipeline.embedding_dimension = 384
        pipeline.node_embedding_dimension = 128

        rare_indices = {10, 30, 50, 70}

        def fake_search_vectors(query_vector, k=10, filter=None):
            # Always returns a full page, so the backend never hits the
            # "len(results) < current_k" stop condition.
            return [
                {
                    "id": f"v{i}",
                    "vector": np.random.rand(384),
                    "metadata": {"category": "rare" if i in rare_indices else "common"},
                    "score": 1.0 - i / 1000.0,
                }
                for i in range(k)
            ]

        pipeline.vector_store.search_vectors.side_effect = fake_search_vectors

        result = pipeline._get_candidate_embeddings(
            np.random.rand(384), limit=10, filters={"category": "rare"}
        )

        assert len(result["embeddings"]) == len(rare_indices)
        assert len(result["metadata"]) == len(rare_indices)
        assert len(result["scores"]) == len(rare_indices)


if __name__ == "__main__":
    pytest.main([__file__])
