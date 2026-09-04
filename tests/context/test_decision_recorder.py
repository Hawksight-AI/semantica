"""
Tests for Decision Recorder

This module tests the DecisionRecorder class and its methods
for recording decisions with full context.
"""

import pytest
import json
from datetime import datetime
from unittest.mock import Mock, patch
from typing import Dict, Any

from semantica.context.decision_models import Decision
from semantica.context.decision_recorder import DecisionRecorder


class TestDecisionRecorder:
    """Test DecisionRecorder class."""
    
    @pytest.fixture
    def mock_graph_store(self):
        """Mock graph store for testing."""
        mock_store = Mock()
        mock_store.execute_query = Mock()
        return mock_store
    
    @pytest.fixture
    def mock_embedding_generator(self):
        """Mock embedding generator for testing."""
        mock_generator = Mock()
        mock_generator.generate = Mock(return_value=[0.1, 0.2, 0.3])
        return mock_generator
    
    @pytest.fixture
    def mock_provenance_manager(self):
        """Mock provenance manager for testing."""
        mock_manager = Mock()
        mock_manager.track_entity = Mock()
        mock_manager.track_activity = Mock()
        return mock_manager
    
    @pytest.fixture
    def decision_recorder(self, mock_graph_store, mock_embedding_generator, mock_provenance_manager):
        """Create DecisionRecorder instance with mocked dependencies."""
        return DecisionRecorder(
            graph_store=mock_graph_store,
            embedding_generator=mock_embedding_generator,
            provenance_manager=mock_provenance_manager
        )
    
    @pytest.fixture
    def sample_decision(self):
        """Create sample decision for testing."""
        return Decision(
            decision_id="test_001",
            category="credit_approval",
            scenario="Credit limit increase request",
            reasoning="Customer has excellent payment history",
            outcome="approved",
            confidence=0.85,
            timestamp=datetime.now(),
            decision_maker="ai_agent_001"
        )
    
    def test_decision_recorder_initialization(self, mock_graph_store):
        """Test DecisionRecorder initialization."""
        recorder = DecisionRecorder(graph_store=mock_graph_store)
        
        assert recorder.graph_store == mock_graph_store
        assert recorder.embedding_generator is None
        assert recorder.provenance_manager is None
    
    def test_decision_recorder_with_dependencies(self, mock_graph_store, mock_embedding_generator, mock_provenance_manager):
        """Test DecisionRecorder initialization with all dependencies."""
        recorder = DecisionRecorder(
            graph_store=mock_graph_store,
            embedding_generator=mock_embedding_generator,
            provenance_manager=mock_provenance_manager
        )
        
        assert recorder.graph_store == mock_graph_store
        assert recorder.embedding_generator == mock_embedding_generator
        assert recorder.provenance_manager == mock_provenance_manager
    
    def test_record_decision_success(self, decision_recorder, sample_decision, mock_graph_store):
        """Test successful decision recording."""
        entities = ["customer_001", "credit_card_123"]
        source_documents = ["doc_001", "doc_002"]
        
        decision_id = decision_recorder.record_decision(
            sample_decision, entities, source_documents
        )
        
        assert decision_id == sample_decision.decision_id
        
        # Verify graph store was called
        assert mock_graph_store.execute_query.called
        
        # Verify embedding was generated
        assert sample_decision.reasoning_embedding is not None
    
    def test_record_decision_without_embedding_generator(self, mock_graph_store):
        """Test decision recording without embedding generator."""
        recorder = DecisionRecorder(graph_store=mock_graph_store)
        decision = Decision(
            decision_id="test_001",
            category="test",
            scenario="test scenario",
            reasoning="test reasoning",
            outcome="test outcome",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test_agent"
        )
        
        decision_id = recorder.record_decision(decision, [], [])
        
        assert decision_id == decision.decision_id
        assert mock_graph_store.execute_query.called

    def test_record_decision_serializes_metadata_for_neo4j_properties(self, mock_graph_store):
        """Decision node params must not contain Map-valued Neo4j properties."""
        recorder = DecisionRecorder(graph_store=mock_graph_store)
        decision = Decision(
            decision_id="test_001",
            category="test",
            scenario="test scenario",
            reasoning="test reasoning",
            outcome="test outcome",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test_agent",
            metadata={"tags": ["t"]},
        )

        def reject_map_properties(query, parameters):
            if "CREATE (d:Decision" in query and isinstance(parameters["metadata"], dict):
                raise RuntimeError("Encountered: Map{}")

        mock_graph_store.execute_query.side_effect = reject_map_properties

        decision_id = recorder.record_decision(decision, [], [])

        assert decision_id == decision.decision_id
        params = mock_graph_store.execute_query.call_args_list[0][0][1]
        assert json.loads(params["metadata"]) == {"tags": ["t"]}
    
    def test_record_decision_failure(self, decision_recorder, sample_decision, mock_graph_store):
        """Test decision recording failure."""
        mock_graph_store.execute_query.side_effect = Exception("Database error")
        
        with pytest.raises(Exception):
            decision_recorder.record_decision(sample_decision, [], [])
    
    def test_link_entities(self, decision_recorder, mock_graph_store):
        """Test linking entities to decision."""
        decision_id = "decision_001"
        entities = ["entity_001", "entity_002"]
        
        decision_recorder.link_entities(decision_id, entities)
        
        # Verify graph store was called for each entity
        assert mock_graph_store.execute_query.call_count == len(entities)
    
    def test_apply_policies(self, decision_recorder, mock_graph_store):
        """Test applying policies to decision."""
        decision_id = "decision_001"
        policy_ids = ["policy_001", "policy_002"]
        mock_graph_store.execute_query.return_value = {"records": [{"policy_id": "policy_001", "version": "2.0"}]}
        
        applied = decision_recorder.apply_policies(decision_id, policy_ids)
        
        # Verify graph store was called for each policy
        assert mock_graph_store.execute_query.call_count == len(policy_ids)
        assert isinstance(applied, list)

    def test_apply_policies_with_explicit_version(self, decision_recorder, mock_graph_store):
        """Test applying a specific policy version to avoid ambiguous linking."""
        decision_id = "decision_001"
        policy_refs = [{"policy_id": "policy_001", "version": "3.2"}]
        mock_graph_store.execute_query.return_value = {
            "records": [{"policy_id": "policy_001", "version": "3.2"}]
        }

        applied = decision_recorder.apply_policies(decision_id, policy_refs)

        assert len(applied) == 1
        assert applied[0]["policy_id"] == "policy_001"
        assert applied[0]["version"] == "3.2"
        call = mock_graph_store.execute_query.call_args_list[0]
        assert call[0][1]["policy_version"] == "3.2"
    
    def test_record_exception(self, decision_recorder, mock_graph_store):
        """Test recording policy exception."""
        decision_id = "decision_001"
        policy_id = "policy_001"
        reason = "Customer is VIP"
        approver = "manager_001"
        approval_method = "slack_dm"
        justification = "Long-term customer"
        
        exception_id = decision_recorder.record_exception(
            decision_id, policy_id, reason, approver, approval_method, justification
        )
        
        assert exception_id is not None
        assert len(exception_id) > 0
        
        # Verify graph store was called multiple times (create exception + relationships)
        assert mock_graph_store.execute_query.call_count >= 2
    
    def test_capture_cross_system_context(self, decision_recorder, mock_graph_store):
        """Test capturing cross-system context."""
        decision_id = "decision_001"
        system_inputs = {
            "salesforce": {"customer_tier": "premium"},
            "zendesk": {"open_tickets": 2}
        }
        
        decision_recorder.capture_cross_system_context(decision_id, system_inputs)
        
        # Verify graph store was called for each system
        assert mock_graph_store.execute_query.call_count == len(system_inputs)
    
    def test_record_approval_chain(self, decision_recorder, mock_graph_store):
        """Test recording approval chain."""
        decision_id = "decision_001"
        approvers = ["manager_001", "director_001"]
        methods = ["slack_dm", "email"]
        contexts = ["Approved via Slack", "Approved via email"]
        
        decision_recorder.record_approval_chain(decision_id, approvers, methods, contexts)
        
        # Verify graph store was called for each approver (create + relationship)
        expected_calls = len(approvers) * 2
        assert mock_graph_store.execute_query.call_count == expected_calls
    
    def test_record_approval_chain_mismatched_lengths(self, decision_recorder):
        """Test approval chain with mismatched array lengths."""
        with pytest.raises(ValueError):
            decision_recorder.record_approval_chain(
                "decision_001",
                ["manager_001"],  # 1 approver
                ["slack_dm", "email"],  # 2 methods
                ["context"]  # 1 context
            )
    
    def test_link_precedents(self, decision_recorder, mock_graph_store):
        """Test linking precedents to decision."""
        decision_id = "decision_001"
        precedent_ids = ["prec_001", "prec_002"]
        relationship_types = ["similar_scenario", "same_policy"]
        
        decision_recorder.link_precedents(decision_id, precedent_ids, relationship_types)
        
        # Verify graph store was called for each precedent
        assert mock_graph_store.execute_query.call_count == len(precedent_ids)
    
    def test_link_precedents_mismatched_lengths(self, decision_recorder):
        """Test linking precedents with mismatched array lengths."""
        with pytest.raises(ValueError):
            decision_recorder.link_precedents(
                "decision_001",
                ["prec_001"],  # 1 precedent
                ["similar_scenario", "same_policy"]  # 2 relationship types
            )
    
    def test_store_decision_node(self, decision_recorder, mock_graph_store, sample_decision):
        """Test storing decision node in graph."""
        decision_recorder._store_decision_node(sample_decision)
        
        # Verify graph store was called with correct parameters
        mock_graph_store.execute_query.assert_called_once()
        
        # Get the call arguments
        call_args = mock_graph_store.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]  # positional arg, not kwargs

        assert "CREATE (d:Decision" in query
        assert params["decision_id"] == sample_decision.decision_id
        assert params["category"] == sample_decision.category
        assert params["scenario"] == sample_decision.scenario
    
    def test_store_exception_node(self, decision_recorder, mock_graph_store):
        """Test storing exception node in graph."""
        from semantica.context.decision_models import PolicyException
        
        exception = PolicyException(
            exception_id="exc_001",
            decision_id="decision_001",
            policy_id="policy_001",
            reason="test reason",
            approver="test_approver",
            approval_timestamp=datetime.now(),
            justification="test justification"
        )
        
        decision_recorder._store_exception_node(exception)
        
        # Verify graph store was called
        mock_graph_store.execute_query.assert_called_once()
        
        # Get the call arguments
        call_args = mock_graph_store.execute_query.call_args_list[0]
        query = call_args[0][0]
        params = call_args[0][1]

        assert "CREATE (e:Exception" in query
        assert params["exception_id"] == exception.exception_id
        assert params["decision_id"] == exception.decision_id
    
    def test_store_approval_node(self, decision_recorder, mock_graph_store):
        """Test storing approval node in graph."""
        from semantica.context.decision_models import ApprovalChain
        
        approval = ApprovalChain(
            approval_id="app_001",
            decision_id="decision_001",
            approver="test_approver",
            approval_method="slack_dm",
            approval_context="test context",
            timestamp=datetime.now()
        )
        
        decision_recorder._store_approval_node(approval)
        
        # Verify graph store was called
        mock_graph_store.execute_query.assert_called_once()
        
        # Get the call arguments
        call_args = mock_graph_store.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "CREATE (a:ApprovalChain" in query
        assert params["approval_id"] == approval.approval_id
        assert params["decision_id"] == approval.decision_id
    
    def test_track_decision_provenance(self, decision_recorder, mock_provenance_manager, sample_decision):
        """Test decision provenance tracking."""
        source_documents = ["doc_001", "doc_002"]
        
        decision_recorder._track_decision_provenance(sample_decision, source_documents)
        
        # Verify provenance manager was called
        mock_provenance_manager.track_entity.assert_called_once()
        mock_provenance_manager.track_activity.assert_called_once()
        
        # Check entity tracking call
        entity_call = mock_provenance_manager.track_entity.call_args
        assert entity_call[1]["entity_id"] == sample_decision.decision_id
        assert entity_call[1]["entity_type"] == "decision"
        assert entity_call[1]["source_documents"] == source_documents
        assert entity_call[1]["confidence"] == sample_decision.confidence
    
    def test_track_decision_provenance_no_manager(self, mock_graph_store):
        """Test provenance tracking without provenance manager."""
        recorder = DecisionRecorder(graph_store=mock_graph_store)
        decision = Decision(
            decision_id="test_001",
            category="test",
            scenario="test scenario",
            reasoning="test reasoning",
            outcome="test outcome",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test_agent"
        )
        
        # Should not raise exception
        recorder._track_decision_provenance(decision, [])
    
    def test_logging_on_error(self, decision_recorder, sample_decision, mock_graph_store):
        """Test that errors during record_decision propagate as exceptions."""
        mock_graph_store.execute_query.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            decision_recorder.record_decision(sample_decision, [], [])


if __name__ == "__main__":
    pytest.main([__file__])
