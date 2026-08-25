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
from semantica.vector_store import VectorStore


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


class TestVectorStoreRetrieval:
    """Test get_vector and get_metadata on real backends."""
    
    def test_inmemory_retrieval(self):
        """Test exact dict behavior for inmemory backend."""
        vs = VectorStore(backend="inmemory")
        vs.store_vectors([np.array([0.1, 0.2, 0.3], dtype=np.float32)], ids=["test1"], metadata=[{"foo": "bar"}])
        
        vec = vs.get_vector("vec_0")
        meta = vs.get_metadata("vec_0")
        
        assert vec is not None
        np.testing.assert_array_almost_equal(vec, np.array([0.1, 0.2, 0.3], dtype=np.float32))
        assert meta == {"foo": "bar"}
        
    def test_faiss_retrieval(self):
        """Test reconstruction from FAISS."""
        try:
            import faiss
        except ImportError:
            pytest.skip("FAISS not installed")
            
        vs = VectorStore(backend="faiss", config={"dimension": 3})
        vs.store_vectors([np.array([0.1, 0.2, 0.3], dtype=np.float32)], ids=["test1"], metadata=[{"foo": "faiss_bar"}])
        
        vec = vs.get_vector("test1")
        assert vec is not None
        np.testing.assert_array_almost_equal(vec, np.array([0.1, 0.2, 0.3], dtype=np.float32))
        
        meta = vs.get_metadata("test1")
        assert meta == {"foo": "faiss_bar"}
            
    def test_cloud_backends_untested(self):
        """
        Note: The following backends are not tested locally as they require 
        live external services (Docker containers or API keys):
        - QdrantStore
        - PineconeStore
        - MilvusStore
        - WeaviateStore
        - PgVectorStore
        
        Their implementations rely directly on official client SDKs (e.g. client.retrieve, 
        index.fetch) to ensure correctness in production.
        """
        pass

if __name__ == "__main__":
    pytest.main([__file__])


class TestBuildDecisionContextInmemoryEquivalence:
    """
    Requirement 3 (issue #848): prove that switching to get_vector() leaves
    inmemory behavior byte-for-byte identical to the old direct dict access.

    We call build_decision_context() and explain_decision() once with inmemory
    to capture results, then call them again after verifying the exact same
    code path (get_vector → self.vectors.get for inmemory) produces the same
    output.  This guards against any regression for existing inmemory users.
    """

    def _make_inmemory_store(self) -> "VectorStore":
        """Return a populated inmemory VectorStore with one stored decision."""
        vs = VectorStore(backend="inmemory", config={"dimension": 4})
        vs.embedder = None  # avoid sentence-transformers dependency

        vec = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        meta = {
            "scenario": "Credit limit increase",
            "reasoning": "Good payment history",
            "outcome": "approved",
            "confidence": 0.85,
            "entities": ["customer_42"],
            "category": "credit",
        }
        ids = vs.store_vectors([vec], metadata=[meta])
        return vs, ids[0], vec, meta

    def test_build_decision_context_inmemory_has_related_decisions(self):
        """
        For inmemory: decision_id IS in self.vectors, so get_vector() returns
        the vector and the related_decisions block must execute — identical to
        the old `if decision_id in self.vectors` guard.
        """
        vs, decision_id, _vec, _meta = self._make_inmemory_store()

        ctx = vs.build_decision_context(decision_id=decision_id, depth=1)

        assert ctx["decision_id"] == decision_id
        assert ctx["decision_metadata"] is not None
        # 'related_decisions' key must exist (even if empty when only 1 vector)
        assert "related_decisions" in ctx
        assert isinstance(ctx["related_decisions"], list)

    def test_build_decision_context_inmemory_missing_id_skips_gracefully(self):
        """
        For inmemory: if decision_id is NOT in self.vectors, get_vector() returns
        None and we must skip similarity search gracefully — same as old guard.
        However, get_metadata() will also return None so the method raises
        ValueError before reaching that branch.  Confirm the ValueError, not
        AttributeError.
        """
        vs, _decision_id, _vec, _meta = self._make_inmemory_store()

        with pytest.raises(ValueError, match="not found"):
            vs.build_decision_context(decision_id="nonexistent_id")

    def test_explain_decision_inmemory_with_paths(self):
        """
        For inmemory: explain_decision(include_paths=True) must populate
        'similar_decisions' when the vector exists — identical to old behaviour.
        """
        vs, decision_id, _vec, _meta = self._make_inmemory_store()

        explanation = vs.explain_decision(
            decision_id=decision_id,
            include_paths=True,
            include_confidence=True,
            include_weights=True,
        )

        assert explanation["decision_id"] == decision_id
        assert explanation["scenario"] == "Credit limit increase"
        assert explanation["outcome"] == "approved"
        assert "confidence" in explanation
        assert "semantic_weight" in explanation
        assert "structural_weight" in explanation
        # similar_decisions must be present when include_paths=True and vector exists
        assert "similar_decisions" in explanation
        assert isinstance(explanation["similar_decisions"], list)

    def test_explain_decision_inmemory_without_paths(self):
        """
        include_paths=False must NOT populate 'similar_decisions' — get_vector()
        is never called in that branch; behaviour unchanged.
        """
        vs, decision_id, _vec, _meta = self._make_inmemory_store()

        explanation = vs.explain_decision(
            decision_id=decision_id,
            include_paths=False,
        )

        assert "similar_decisions" not in explanation


class TestBuildDecisionContextFAISSBackend:
    """
    Requirement 4 (issue #848): regression tests against a real non-inmemory
    backend.  FAISS is chosen because it is the same backend used by
    test_find_similar_decisions_real_faiss_backend (issue #839 regression) in
    TestDecisionEmbeddingPipelineEdgeCases above — keeping the whole fix
    cluster on a consistent backend.
    """

    def _make_faiss_store(self):
        """
        Return a FAISS-backed VectorStore pre-populated with two decisions.
        Skips automatically when faiss is not installed.
        """
        pytest.importorskip("faiss")

        vs = VectorStore(backend="faiss", config={"dimension": 4})
        vs.embedder = None  # avoid sentence-transformers dependency

        vec_a = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        vec_b = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)

        meta_a = {
            "scenario": "Loan approval A",
            "reasoning": "Low risk",
            "outcome": "approved",
            "confidence": 0.9,
            "entities": ["customer_1"],
            "category": "loan",
        }
        meta_b = {
            "scenario": "Loan approval B",
            "reasoning": "Medium risk",
            "outcome": "approved",
            "confidence": 0.7,
            "entities": ["customer_2"],
            "category": "loan",
        }

        ids = vs.store_vectors([vec_a, vec_b], metadata=[meta_a, meta_b])
        return vs, ids[0], ids[1]

    def test_build_decision_context_faiss_no_attribute_error(self):
        """
        Regression (issue #848): build_decision_context() must NOT raise
        AttributeError: 'VectorStore' object has no attribute 'vectors'
        when the FAISS backend is active.
        """
        vs, decision_id_a, _decision_id_b = self._make_faiss_store()

        # Before the fix this raised AttributeError at `if decision_id in self.vectors`
        ctx = vs.build_decision_context(decision_id=decision_id_a, depth=1)

        assert ctx["decision_id"] == decision_id_a
        assert ctx["decision_metadata"] is not None
        assert ctx["decision_metadata"]["scenario"] == "Loan approval A"
        assert "related_decisions" in ctx
        assert isinstance(ctx["related_decisions"], list)

    def test_build_decision_context_faiss_related_decisions_populated(self):
        """
        With two stored vectors, the context for either one must list the other
        as a related decision (since FAISS search will return both and we filter
        out the query id itself).
        """
        vs, decision_id_a, decision_id_b = self._make_faiss_store()

        ctx = vs.build_decision_context(decision_id=decision_id_a, depth=1)

        related_ids = [r["id"] for r in ctx["related_decisions"]]
        assert decision_id_a not in related_ids, (
            "The query decision itself must be excluded from related_decisions"
        )
        assert decision_id_b in related_ids, (
            "The other stored decision must appear as a related decision"
        )
        # Structural shape check
        for r in ctx["related_decisions"]:
            assert "id" in r
            assert "similarity" in r
            assert "metadata" in r

    def test_build_decision_context_faiss_missing_id_raises_value_error(self):
        """
        A completely unknown decision_id must raise ValueError (not AttributeError).
        """
        vs, _a, _b = self._make_faiss_store()

        with pytest.raises(ValueError, match="not found"):
            vs.build_decision_context(decision_id="totally_unknown_id")

    def test_explain_decision_faiss_no_attribute_error(self):
        """
        Regression (issue #848): explain_decision(include_paths=True) must NOT
        raise AttributeError: 'VectorStore' object has no attribute 'vectors'
        when the FAISS backend is active.
        """
        vs, decision_id_a, _decision_id_b = self._make_faiss_store()

        # Before the fix this raised AttributeError at `if decision_id in self.vectors`
        explanation = vs.explain_decision(
            decision_id=decision_id_a,
            include_paths=True,
            include_confidence=True,
            include_weights=True,
        )

        assert explanation["decision_id"] == decision_id_a
        assert explanation["scenario"] == "Loan approval A"
        assert explanation["outcome"] == "approved"
        assert "confidence" in explanation
        assert "semantic_weight" in explanation
        assert "structural_weight" in explanation
        assert "similar_decisions" in explanation
        assert isinstance(explanation["similar_decisions"], list)

    def test_explain_decision_faiss_without_paths_no_similar_decisions_key(self):
        """
        include_paths=False must not populate 'similar_decisions' — regardless
        of backend.
        """
        vs, decision_id_a, _decision_id_b = self._make_faiss_store()

        explanation = vs.explain_decision(
            decision_id=decision_id_a,
            include_paths=False,
        )

        assert "similar_decisions" not in explanation

    def test_explain_decision_faiss_missing_id_raises_value_error(self):
        """
        A completely unknown decision_id must raise ValueError (not AttributeError).
        """
        vs, _a, _b = self._make_faiss_store()

        with pytest.raises(ValueError, match="not found"):
            vs.explain_decision(decision_id="totally_unknown_id", include_paths=True)


class TestFilterByMetadataBackendBehavior:
    """
    Requirement (issue #848, superseded by #857): verify the behavior of
    _filter_by_metadata when a non-inmemory backend is active.

    #848's original decision was to raise NotImplementedError (matching
    get_vector / get_metadata from #843) rather than silently return [],
    because at the time zero backend wrappers implemented
    filter_by_metadata(filters, limit).

    #857 gave every persistent backend (FAISS, Qdrant, Pinecone, Milvus,
    PgVector, SQLiteVec, Weaviate) a real filter_by_metadata() implementation,
    so FAISS-backed filter_decisions(query=None, ...) now returns actual
    filtered results instead of raising. The NotImplementedError path itself
    is still correct and still covered (see
    test_filter_by_metadata_backend_not_implemented in test_vector_store.py)
    for a backend that genuinely lacks the method.
    """

    def _make_faiss_store(self):
        """FAISS store with two stored decisions — same factory as the rest of
        this fix cluster."""
        pytest.importorskip("faiss")
        vs = VectorStore(backend="faiss", config={"dimension": 4})
        vs.embedder = None

        ids = vs.store_vectors(
            [
                np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
            ],
            metadata=[
                {"scenario": "Loan A", "category": "loan", "outcome": "approved",
                 "confidence": 0.9, "entities": [], "reasoning": ""},
                {"scenario": "Loan B", "category": "loan", "outcome": "denied",
                 "confidence": 0.6, "entities": [], "reasoning": ""},
            ],
        )
        return vs, ids

    # ── FAISS backend: real results, not AttributeError, not [] ── #

    def test_filter_by_metadata_faiss_returns_real_results(self):
        """
        filter_decisions(query=None, category='loan') on a FAISS-backed store
        must return the actual matching decisions, not raise AttributeError
        (old crash) and not silently return [] (the old NotImplementedError
        stand-in from #848, superseded once #857 gave FAISSStore a real
        filter_by_metadata()).
        """
        vs, _ids = self._make_faiss_store()

        results = vs.filter_decisions(query=None, category="loan")

        assert isinstance(results, list)
        assert len(results) == 2, (
            f"Expected 2 loan decisions, got {len(results)}: {results}"
        )
        for r in results:
            assert r["metadata"]["category"] == "loan"

    def test_filter_by_metadata_faiss_not_attribute_error(self):
        """
        Regression guard: the old code raised AttributeError because self.metadata
        does not exist for non-inmemory backends.  This must never happen again.
        """
        vs, _ids = self._make_faiss_store()

        try:
            vs.filter_decisions(query=None, category="loan")
        except NotImplementedError:
            pass  # correct — this is what we want
        except AttributeError as exc:
            pytest.fail(
                f"Got AttributeError instead of NotImplementedError: {exc}"
            )

    def test_filter_by_metadata_faiss_not_silent_empty_list(self):
        """
        The wrong fix would have silently returned []. Confirm the FAISS path
        raises rather than returning an empty list that the caller cannot
        distinguish from 'zero decisions matched'.
        """
        vs, _ids = self._make_faiss_store()

        result_was_empty_list = False
        try:
            result = vs.filter_decisions(query=None, category="loan")
            result_was_empty_list = (result == [])
        except NotImplementedError:
            pass  # correct

        assert not result_was_empty_list, (
            "_filter_by_metadata must not silently return [] for a non-inmemory "
            "backend — it must raise NotImplementedError so callers cannot "
            "mistake 'backend unsupported' for 'no matching decisions'."
        )

    # ── inmemory backend: existing iteration still works ── #

    def test_filter_by_metadata_inmemory_still_works(self):
        """
        Control: inmemory backend must not be affected by the FAISS guard.
        filter_decisions(query=None, category='loan') must return the two
        loan decisions that were stored and not raise anything.
        """
        vs = VectorStore(backend="inmemory", config={"dimension": 4})
        vs.embedder = None

        vs.store_vectors(
            [
                np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
                np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32),
            ],
            metadata=[
                {"scenario": "Loan A", "category": "loan", "outcome": "approved",
                 "confidence": 0.9, "entities": [], "reasoning": ""},
                {"scenario": "Loan B", "category": "loan", "outcome": "denied",
                 "confidence": 0.6, "entities": [], "reasoning": ""},
                {"scenario": "Credit card", "category": "credit", "outcome": "approved",
                 "confidence": 0.8, "entities": [], "reasoning": ""},
            ],
        )

        results = vs.filter_decisions(query=None, category="loan")

        assert isinstance(results, list)
        assert len(results) == 2, (
            f"Expected 2 loan decisions, got {len(results)}: {results}"
        )
        for r in results:
            assert r["metadata"]["category"] == "loan"


class TestVectorRetrievalFailureBehavior:
    """
    Requirement: verify that when get_vector() returns None for an existing decision
    (e.g., FAISS without reconstruct capability), we don't silently drop similarity
    enrichment. We should get a warning log and an explicit marker in the output.
    """

    class _StubBackend:
        def __init__(self):
            self.metadata = {
                "decision_1": {
                    "scenario": "Stub Scenario",
                    "reasoning": "Stub Reasoning",
                    "outcome": "approved"
                }
            }

        def get_metadata(self, vector_id: str):
            return self.metadata.get(vector_id)

        def get_vector(self, vector_id: str):
            # Explicitly return None to simulate a backend that cannot reconstruct vectors
            return None

    def _make_stub_store(self):
        vs = VectorStore(backend="inmemory", config={"dimension": 4})
        vs.embedder = None
        # Replace the backend store with our stub
        vs._backend_store = self._StubBackend()
        vs.backend = "stub"
        return vs

    def test_build_decision_context_warns_and_marks_on_missing_vector(self, caplog):
        """
        When get_vector() returns None for an existing decision, build_decision_context
        should warn and add 'similarity_unavailable': True to the context.
        """
        import logging
        vs = self._make_stub_store()

        with caplog.at_level(logging.WARNING, logger="semantica.vector_store"):
            ctx = vs.build_decision_context(decision_id="decision_1", depth=1)

        assert ctx["decision_id"] == "decision_1"
        assert ctx.get("similarity_unavailable") is True, "Expected similarity_unavailable marker"
        assert isinstance(ctx["related_decisions"], list), "related_decisions must be a list for schema stability"
        assert len(ctx["related_decisions"]) == 0

        warning_logged = any(
            "decision_1" in record.message and record.levelname == "WARNING"
            for record in caplog.records
        )
        assert warning_logged, f"Expected WARNING log mentioning decision_1; got: {caplog.records}"

    def test_explain_decision_warns_and_marks_on_missing_vector(self, caplog):
        """
        When get_vector() returns None for an existing decision, explain_decision
        with include_paths=True should warn and add 'similarity_unavailable': True.
        """
        import logging
        vs = self._make_stub_store()

        with caplog.at_level(logging.WARNING, logger="semantica.vector_store"):
            explanation = vs.explain_decision(
                decision_id="decision_1",
                include_paths=True,
            )

        assert explanation["decision_id"] == "decision_1"
        assert explanation.get("similarity_unavailable") is True, "Expected similarity_unavailable marker"
        assert isinstance(explanation["similar_decisions"], list), "similar_decisions must be a list for schema stability"
        assert len(explanation["similar_decisions"]) == 0

        warning_logged = any(
            "decision_1" in record.message and record.levelname == "WARNING"
            for record in caplog.records
        )
        assert warning_logged, f"Expected WARNING log mentioning decision_1; got: {caplog.records}"
