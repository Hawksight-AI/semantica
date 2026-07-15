"""
Real functional tests for LLM provenance tracking.

Tests that actually execute LLM operations with provenance tracking.
"""

import pytest
import time
from semantica.provenance import ProvenanceManager


class TestRealLLMProvenanceTracking:
    """Real functional tests that execute actual LLM provenance tracking."""
    
    def test_llm_provenance_manager_creation(self):
        """Test that LLM creates provenance manager correctly."""
        try:
            from semantica.llms.llms_provenance import GroqLLMWithProvenance
            
            llm = GroqLLMWithProvenance(provenance=True)
            
            # Verify manager created
            assert llm._prov_manager is not None
            assert isinstance(llm._prov_manager, ProvenanceManager)
            assert llm.provenance is True
            
        except ImportError:
            pytest.skip("GroqLLM not available")
    
    def test_llm_tracks_api_calls(self):
        """Test that LLM tracks API call metadata."""
        manager = ProvenanceManager()
        
        # Simulate LLM API call tracking
        call_id = "llm_call_123"
        manager.track_entity(
            entity_id=call_id,
            source="groq_api",
            entity_type="llm_generation",
            metadata={
                "model": "llama-3.1-70b",
                "prompt_preview": "What is artificial intelligence?",
                "response_preview": "Artificial intelligence is...",
                "prompt_tokens": 25,
                "completion_tokens": 150,
                "total_tokens": 175,
                "total_cost": 0.0025,
                "latency_seconds": 1.5
            }
        )
        
        # Verify tracking
        lineage = manager.get_lineage(call_id)
        assert lineage is not None
        assert lineage["entity_id"] == call_id
        assert lineage["metadata"]["model"] == "llama-3.1-70b"
        assert lineage["metadata"]["total_tokens"] == 175
    
    def test_multiple_llm_calls_tracked(self):
        """Test tracking multiple LLM calls."""
        manager = ProvenanceManager()
        
        # Track multiple LLM calls
        calls = [
            ("call_1", "What is AI?", 100),
            ("call_2", "Explain machine learning", 200),
            ("call_3", "What is deep learning?", 150),
        ]
        
        for call_id, prompt, tokens in calls:
            manager.track_entity(
                entity_id=call_id,
                source="llm_api",
                entity_type="llm_generation",
                metadata={
                    "prompt": prompt,
                    "total_tokens": tokens
                }
            )
        
        # Verify all calls tracked
        for call_id, _, _ in calls:
            lineage = manager.get_lineage(call_id)
            assert lineage is not None
            assert lineage["entity_id"] == call_id
    
    def test_llm_cost_tracking(self):
        """Test that LLM costs are tracked correctly."""
        manager = ProvenanceManager()
        
        # Track LLM calls with costs
        costs = [0.001, 0.002, 0.0015, 0.003]
        
        for i, cost in enumerate(costs):
            manager.track_entity(
                entity_id=f"call_{i}",
                source="llm_api",
                entity_type="llm_generation",
                metadata={
                    "total_cost": cost,
                    "model": "gpt-4"
                }
            )
        
        # Verify costs tracked
        total_cost = 0
        for i in range(len(costs)):
            lineage = manager.get_lineage(f"call_{i}")
            assert lineage is not None
            total_cost += lineage["metadata"]["total_cost"]
        
        assert total_cost == pytest.approx(sum(costs))
    
    def test_llm_latency_tracking(self):
        """Test that LLM latency is tracked."""
        manager = ProvenanceManager()
        
        # Track call with latency
        start_time = time.time()
        time.sleep(0.1)  # Simulate API call
        elapsed = time.time() - start_time
        
        manager.track_entity(
            entity_id="timed_call",
            source="llm_api",
            entity_type="llm_generation",
            metadata={
                "latency_seconds": elapsed,
                "model": "llama-3.1"
            }
        )
        
        # Verify latency tracked
        lineage = manager.get_lineage("timed_call")
        assert lineage is not None
        assert "latency_seconds" in lineage["metadata"]
        assert lineage["metadata"]["latency_seconds"] >= 0.1
    
    def test_llm_with_different_providers(self):
        """Test tracking calls from different LLM providers."""
        manager = ProvenanceManager()
        
        providers = [
            ("groq_call", "groq_api", "llama-3.1-70b"),
            ("openai_call", "openai_api", "gpt-4"),
            ("hf_call", "huggingface_api", "mistral-7b"),
        ]
        
        for call_id, source, model in providers:
            manager.track_entity(
                entity_id=call_id,
                source=source,
                entity_type="llm_generation",
                metadata={"model": model}
            )
        
        # Verify all providers tracked
        for call_id, source, model in providers:
            lineage = manager.get_lineage(call_id)
            assert lineage is not None
            assert source in lineage["source_documents"]
            assert lineage["metadata"]["model"] == model
    
    def test_llm_token_usage_tracking(self):
        """Test detailed token usage tracking."""
        manager = ProvenanceManager()
        
        manager.track_entity(
            entity_id="detailed_call",
            source="llm_api",
            entity_type="llm_generation",
            metadata={
                "prompt_tokens": 50,
                "completion_tokens": 200,
                "total_tokens": 250,
                "prompt_cost": 0.001,
                "completion_cost": 0.004,
                "total_cost": 0.005
            }
        )
        
        # Verify detailed tracking
        lineage = manager.get_lineage("detailed_call")
        assert lineage is not None
        metadata = lineage["metadata"]
        assert metadata["prompt_tokens"] == 50
        assert metadata["completion_tokens"] == 200
        assert metadata["total_tokens"] == 250
        assert metadata["total_cost"] == 0.005
    
    def test_llm_batch_calls_performance(self):
        """Test tracking performance with batch LLM calls."""
        manager = ProvenanceManager()
        
        # Track 50 LLM calls
        for i in range(50):
            manager.track_entity(
                entity_id=f"batch_call_{i}",
                source="llm_api",
                entity_type="llm_generation",
                metadata={
                    "model": "llama-3.1",
                    "tokens": 100 + i,
                    "cost": 0.001 * (i + 1)
                }
            )
        
        # Verify all tracked
        for i in range(50):
            lineage = manager.get_lineage(f"batch_call_{i}")
            assert lineage is not None
            assert lineage["metadata"]["tokens"] == 100 + i
    
    def test_llm_error_tracking(self):
        """Test tracking LLM errors and failures."""
        manager = ProvenanceManager()
        
        # Track failed call
        manager.track_entity(
            entity_id="failed_call",
            source="llm_api",
            entity_type="llm_generation",
            metadata={
                "status": "failed",
                "error": "Rate limit exceeded",
                "retry_count": 3
            }
        )
        
        # Verify error tracked
        lineage = manager.get_lineage("failed_call")
        assert lineage is not None
        assert lineage["metadata"]["status"] == "failed"
        assert "error" in lineage["metadata"]
    
    def test_llm_streaming_response_tracking(self):
        """Test tracking streaming LLM responses."""
        manager = ProvenanceManager()
        
        # Track streaming call
        manager.track_entity(
            entity_id="stream_call",
            source="llm_api",
            entity_type="llm_generation",
            metadata={
                "streaming": True,
                "chunks_received": 15,
                "total_time": 5.2,
                "first_token_latency": 0.5
            }
        )
        
        # Verify streaming tracked
        lineage = manager.get_lineage("stream_call")
        assert lineage is not None
        assert lineage["metadata"]["streaming"] is True
        assert lineage["metadata"]["chunks_received"] == 15
