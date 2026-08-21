"""
Tests for Policy Engine

This module tests the PolicyEngine class and its methods
for policy management, versioning, and compliance checking.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from typing import List, Dict, Any

from semantica.context.decision_models import Policy, PolicyException
from semantica.context.policy_engine import PolicyEngine


class TestPolicyEngine:
    """Test PolicyEngine class."""
    
    @pytest.fixture
    def mock_graph_store(self):
        """Mock graph store for testing."""
        mock_store = Mock()
        mock_store.execute_query = Mock()
        return mock_store
    
    @pytest.fixture
    def policy_engine(self, mock_graph_store):
        """Create PolicyEngine instance with mocked dependencies."""
        return PolicyEngine(graph_store=mock_graph_store)
    
    @pytest.fixture
    def sample_policy(self):
        """Create sample policy for testing."""
        return Policy(
            policy_id="policy_001",
            name="Credit Approval Policy",
            description="Standard credit approval rules and guidelines",
            rules={
                "min_credit_score": 650,
                "max_debt_ratio": 0.4,
                "max_credit_limit": 50000,
                "required_documents": ["income_verification", "employment_verification"]
            },
            category="credit_approval",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"department": "risk_management", "effective_date": "2024-01-01"}
        )
    
    def test_policy_engine_initialization(self, mock_graph_store):
        """Test PolicyEngine initialization."""
        engine = PolicyEngine(graph_store=mock_graph_store)
        
        assert engine.graph_store == mock_graph_store
    
    def test_add_policy_success(self, policy_engine, sample_policy, mock_graph_store):
        """Test successful policy addition."""
        # Mock graph query result
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(sample_policy)
        
        assert policy_id == sample_policy.policy_id
        
        # Verify graph store was called
        assert mock_graph_store.execute_query.called
    
    def test_add_policy_auto_id(self, policy_engine, mock_graph_store):
        """Test policy addition with auto-generated ID."""
        policy = Policy(
            policy_id="",  # Empty ID for auto-generation
            name="Test Policy",
            description="Test description",
            rules={"test": "rule"},
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(policy)
        
        assert policy_id != ""
        assert len(policy_id) > 0
    
    def test_add_policy_duplicate_id(self, policy_engine, sample_policy, mock_graph_store):
        """Test policy addition with duplicate ID."""
        # Mock existing policy
        mock_graph_store.execute_query.return_value = [{"policy_id": sample_policy.policy_id}]
        
        with pytest.raises(ValueError, match="Policy with this ID already exists"):
            policy_engine.add_policy(sample_policy)
    
    def test_update_policy_success(self, policy_engine, mock_graph_store):
        """Test successful policy update."""
        policy_id = "policy_001"
        new_rules = {"min_credit_score": 680, "max_debt_ratio": 0.35}
        change_reason = "Regulatory update - stricter requirements"
        new_version = "2.0"

        # Provide enough side_effects: get_policy, duplicate check in add_policy, CREATE, VERSION_OF
        mock_graph_store.execute_query.side_effect = [
            [{"policy_id": policy_id, "version": "1.0"}],  # get_policy
            [],   # add_policy duplicate check (no duplicate)
            [],   # add_policy CREATE
            [],   # VERSION_OF merge
        ]

        updated_policy_id = policy_engine.update_policy(
            policy_id, new_rules, change_reason, new_version
        )

        assert updated_policy_id == policy_id
        assert mock_graph_store.execute_query.call_count >= 2
    
    def test_update_policy_not_found(self, policy_engine, mock_graph_store):
        """Test policy update when policy not found."""
        policy_id = "nonexistent_policy"
        new_rules = {"test": "rule"}
        change_reason = "Test update"
        
        # Mock no existing policy
        mock_graph_store.execute_query.return_value = []
        
        with pytest.raises(ValueError, match="Policy.*not found"):
            policy_engine.update_policy(policy_id, new_rules, change_reason)
    
    def test_get_applicable_policies_success(self, policy_engine, mock_graph_store):
        """Test getting applicable policies."""
        category = "credit_approval"
        entities = ["customer:jessica_norris", "product:credit_card"]
        
        # Mock applicable policies
        mock_graph_store.execute_query.return_value = [
            {
                "policy_id": "policy_001",
                "name": "Credit Approval Policy",
                "description": "Standard credit approval rules",
                "rules": {"min_score": 650},
                "category": "credit_approval",
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "metadata": {"department": "risk"}
            },
            {
                "policy_id": "policy_002",
                "name": "High-Risk Customer Policy",
                "description": "Additional checks for high-risk customers",
                "rules": {"additional_review": True},
                "category": "credit_approval",
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "metadata": {"risk_level": "high"}
            }
        ]
        
        policies = policy_engine.get_applicable_policies(category, entities)
        
        assert len(policies) == 2
        assert policies[0].policy_id == "policy_001"
        assert policies[1].policy_id == "policy_002"
        assert all(p.category == category for p in policies)
    
    def test_get_applicable_policies_no_entities(self, policy_engine, mock_graph_store):
        """Test getting applicable policies without entities."""
        category = "credit_approval"
        
        mock_graph_store.execute_query.return_value = [
            {
                "policy_id": "policy_001",
                "name": "Credit Approval Policy",
                "description": "Standard credit approval rules",
                "rules": {"min_score": 650},
                "category": "credit_approval",
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "metadata": {}
            }
        ]
        
        policies = policy_engine.get_applicable_policies(category, None)
        
        assert len(policies) == 1
        assert policies[0].category == category

    def test_get_applicable_policies_falkordb_row_shape(self, policy_engine, mock_graph_store):
        """Test policy parsing when backend returns FalkorDB list rows + header."""
        category = "credit_approval"
        mock_graph_store.execute_query.return_value = {
            "records": [
                [
                    {
                        "policy_id": "policy_001",
                        "name": "Credit Approval Policy",
                        "description": "Standard credit approval rules",
                        "rules": {"min_score": 650},
                        "category": "credit_approval",
                        "version": "1.0",
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat(),
                        "metadata": {},
                    }
                ]
            ],
            "header": ["p"],
        }

        policies = policy_engine.get_applicable_policies(category, None)

        assert len(policies) == 1
        assert policies[0].policy_id == "policy_001"

    def test_get_applicable_policies_skips_malformed_record(self, policy_engine, mock_graph_store):
        """Test malformed policy records are skipped instead of crashing."""
        category = "credit_approval"
        mock_graph_store.execute_query.return_value = [{"unexpected": "shape"}]

        policies = policy_engine.get_applicable_policies(category, None)

        assert policies == []

    def test_get_applicable_policies_context_graph_fallback_respects_entities(self):
        """Test entity scoping is applied in find_nodes() fallback path."""
        category = "credit_approval"
        entities = ["customer:target"]

        class _ContextGraphLike:
            def find_nodes(self, node_type=None):
                if node_type != "Policy":
                    return []
                return [
                    {
                        "metadata": {
                            "policy_id": "policy_match",
                            "name": "Scoped policy",
                            "description": "Applies to target customer",
                            "rules": {},
                            "category": "credit_approval",
                            "version": "1.0",
                            "created_at": datetime.now().isoformat(),
                            "updated_at": datetime.now().isoformat(),
                            "metadata": {"entities": ["customer:target"]},
                        }
                    },
                    {
                        "metadata": {
                            "policy_id": "policy_other",
                            "name": "Other scoped policy",
                            "description": "Applies elsewhere",
                            "rules": {},
                            "category": "credit_approval",
                            "version": "1.0",
                            "created_at": datetime.now().isoformat(),
                            "updated_at": datetime.now().isoformat(),
                            "metadata": {"entities": ["customer:other"]},
                        }
                    },
                ]

        engine = PolicyEngine(graph_store=_ContextGraphLike())
        policies = engine.get_applicable_policies(category, entities)

        assert len(policies) == 1
        assert policies[0].policy_id == "policy_match"
    
    def test_check_compliance_success(self, policy_engine, mock_graph_store):
        """Test successful compliance checking."""
        from semantica.context.decision_models import Decision
        
        decision = Decision(
            decision_id="decision_001",
            category="credit_approval",
            scenario="Credit limit increase",
            reasoning="Customer meets all criteria",
            outcome="approved",
            confidence=0.9,
            timestamp=datetime.now(),
            decision_maker="ai_agent_001"
        )
        
        policy_id = "policy_001"
        
        # Mock policy rules
        mock_graph_store.execute_query.return_value = [
            {
                "policy_id": policy_id,
                "rules": {"min_credit_score": 650, "max_debt_ratio": 0.4}
            }
        ]
        
        # Mock compliance check logic
        with patch.object(policy_engine, '_evaluate_compliance', return_value=True):
            is_compliant = policy_engine.check_compliance(decision, policy_id)
        
        assert is_compliant is True
    
    def test_check_compliance_failure(self, policy_engine, mock_graph_store):
        """Test compliance checking failure."""
        from semantica.context.decision_models import Decision
        
        decision = Decision(
            decision_id="decision_001",
            category="credit_approval",
            scenario="Credit limit increase",
            reasoning="Customer has low credit score",
            outcome="rejected",
            confidence=0.7,
            timestamp=datetime.now(),
            decision_maker="ai_agent_001"
        )
        
        policy_id = "policy_001"
        
        # Mock policy rules
        mock_graph_store.execute_query.return_value = [
            {
                "policy_id": policy_id,
                "rules": {"min_credit_score": 650, "max_debt_ratio": 0.4}
            }
        ]
        
        # Mock compliance check logic
        with patch.object(policy_engine, '_evaluate_compliance', return_value=False):
            is_compliant = policy_engine.check_compliance(decision, policy_id)
        
        assert is_compliant is False
    
    def test_check_compliance_policy_not_found(self, policy_engine, mock_graph_store):
        """Test compliance checking when policy not found."""
        from semantica.context.decision_models import Decision
        
        decision = Decision(
            decision_id="decision_001",
            category="test",
            scenario="test",
            reasoning="test",
            outcome="test",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test"
        )
        
        # Mock no policy found
        mock_graph_store.execute_query.return_value = []
        
        with pytest.raises(ValueError, match="Policy.*not found"):
            policy_engine.check_compliance(decision, "nonexistent_policy")

    def test_check_compliance_raises_on_evaluation_error(
        self, policy_engine, mock_graph_store
    ):
        """A failure while evaluating compliance must raise, not return False.

        Returning False would conflate "checked and found non-compliant" with
        "the check itself failed", which is dangerous in an audit/compliance
        context. The engine must surface such failures as ProcessingError.
        """
        from semantica.context.decision_models import Decision
        from semantica.utils.exceptions import ProcessingError

        decision = Decision(
            decision_id="decision_001",
            category="credit_approval",
            scenario="Credit limit increase",
            reasoning="Customer meets all criteria",
            outcome="approved",
            confidence=0.9,
            timestamp=datetime.now(),
            decision_maker="ai_agent_001",
        )

        policy_id = "policy_001"

        mock_graph_store.execute_query.return_value = [
            {
                "policy_id": policy_id,
                "rules": {"min_credit_score": 650, "max_debt_ratio": 0.4},
            }
        ]

        with patch.object(
            policy_engine,
            "_evaluate_compliance",
            side_effect=RuntimeError("unexpected evaluation failure"),
        ):
            with pytest.raises(ProcessingError, match="Compliance check failed"):
                policy_engine.check_compliance(decision, policy_id)
    
    def test_record_policy_application_success(self, policy_engine, mock_graph_store):
        """Test successful policy application recording."""
        decision_id = "decision_001"
        policy_id = "policy_001"
        version = "1.0"
        
        mock_graph_store.execute_query.return_value = []
        
        policy_engine.record_policy_application(decision_id, policy_id, version)
        
        # Verify graph store was called
        assert mock_graph_store.execute_query.called
    
    def test_record_exception_success(self, policy_engine, mock_graph_store):
        """Test successful exception recording."""
        decision_id = "decision_001"
        policy_id = "policy_001"
        reason = "Customer is VIP with special arrangements"
        approver = "manager_001"
        justification = "Long-term valuable customer"
        
        mock_graph_store.execute_query.return_value = []
        
        exception_id = policy_engine.record_exception(
            decision_id, policy_id, reason, approver, justification
        )
        
        assert exception_id is not None
        assert len(exception_id) > 0
        
        # Verify graph store was called multiple times
        assert mock_graph_store.execute_query.call_count >= 2
    
    def test_get_policy_history_success(self, policy_engine, mock_graph_store):
        """Test getting policy version history."""
        policy_id = "policy_001"
        
        # Mock policy history
        mock_graph_store.execute_query.return_value = [
            {
                "policy_id": policy_id,
                "name": "Credit Approval Policy",
                "description": "Standard credit approval rules",
                "rules": {"min_score": 650},
                "category": "credit_approval",
                "version": "1.0",
                "created_at": (datetime.now() - timedelta(days=30)).isoformat(),
                "updated_at": (datetime.now() - timedelta(days=30)).isoformat(),
                "metadata": {"change_reason": "Initial version"}
            },
            {
                "policy_id": policy_id,
                "name": "Credit Approval Policy",
                "description": "Updated credit approval rules",
                "rules": {"min_score": 680},
                "category": "credit_approval",
                "version": "2.0",
                "created_at": (datetime.now() - timedelta(days=7)).isoformat(),
                "updated_at": (datetime.now() - timedelta(days=7)).isoformat(),
                "metadata": {"change_reason": "Regulatory update"}
            }
        ]
        
        history = policy_engine.get_policy_history(policy_id)
        
        assert len(history) == 2
        assert history[0].version == "1.0"
        assert history[1].version == "2.0"
        assert history[1].created_at > history[0].created_at
    
    def test_get_policy_history_not_found(self, policy_engine, mock_graph_store):
        """Test getting policy history when policy not found."""
        mock_graph_store.execute_query.return_value = []
        
        history = policy_engine.get_policy_history("nonexistent_policy")
        
        assert len(history) == 0
    
    def test_get_affected_decisions_success(self, policy_engine, mock_graph_store):
        """Test getting decisions affected by policy change."""
        policy_id = "policy_001"
        from_version = "1.0"
        to_version = "2.0"
        
        # Mock affected decisions
        mock_graph_store.execute_query.return_value = [
            {
                "decision_id": "decision_001",
                "applied_policy_version": "1.0",
                "timestamp": (datetime.now() - timedelta(days=5)).isoformat(),
                "impact_score": 0.8
            },
            {
                "decision_id": "decision_002",
                "applied_policy_version": "1.0",
                "timestamp": (datetime.now() - timedelta(days=3)).isoformat(),
                "impact_score": 0.6
            }
        ]
        
        affected_decisions = policy_engine.get_affected_decisions(
            policy_id, from_version, to_version
        )
        
        assert len(affected_decisions) == 2
        assert affected_decisions[0]["decision_id"] == "decision_001"
        assert affected_decisions[0]["applied_policy_version"] == from_version
        assert "scenario" in affected_decisions[0]
        assert "category" in affected_decisions[0]
        assert "outcome" in affected_decisions[0]
        assert "confidence" in affected_decisions[0]
    
    def test_analyze_policy_impact_success(self, policy_engine, mock_graph_store):
        """Test policy impact analysis."""
        policy_id = "policy_001"
        proposed_rules = {"min_credit_score": 700, "max_debt_ratio": 0.3}
        
        # Mock current policy and affected decisions
        mock_graph_store.execute_query.side_effect = [
            [{"policy_id": policy_id, "rules": {"min_score": 650, "max_debt_ratio": 0.4}}],  # Current policy
            [  # Affected decisions
                {"decision_id": "decision_001", "compliance_score": 0.8},
                {"decision_id": "decision_002", "compliance_score": 0.6}
            ]
        ]
        
        # Mock impact analysis
        with patch.object(policy_engine, '_calculate_impact_metrics', return_value={
            "affected_decisions": 2,
            "compliance_impact": -0.2,
            "risk_increase": 0.15
        }):
            impact_analysis = policy_engine.analyze_policy_impact(policy_id, proposed_rules)
        
        assert "affected_decisions" in impact_analysis
        assert "compliance_impact" in impact_analysis
        assert "risk_increase" in impact_analysis
    
    def test_analyze_policy_impact_policy_not_found(self, policy_engine, mock_graph_store):
        """Test policy impact analysis when policy not found."""
        mock_graph_store.execute_query.return_value = []
        
        with pytest.raises(ValueError, match="Policy.*not found"):
            policy_engine.analyze_policy_impact("nonexistent_policy", {"test": "rule"})
    
    def test_get_policy_success(self, policy_engine, mock_graph_store):
        """Test getting a specific policy."""
        policy_id = "policy_001"
        
        # Mock policy result
        mock_graph_store.execute_query.return_value = [
            {
                "policy_id": policy_id,
                "name": "Credit Approval Policy",
                "description": "Standard credit approval rules",
                "rules": {"min_score": 650},
                "category": "credit_approval",
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "metadata": {}
            }
        ]
        
        policy = policy_engine.get_policy(policy_id)
        
        assert policy is not None
        assert policy.policy_id == policy_id
        assert policy.name == "Credit Approval Policy"
    
    def test_get_policy_not_found(self, policy_engine, mock_graph_store):
        """Test getting a policy when not found."""
        mock_graph_store.execute_query.return_value = []
        
        policy = policy_engine.get_policy("nonexistent_policy")
        
        assert policy is None
    
    def test_delete_policy_success(self, policy_engine, mock_graph_store):
        """Test successful policy deletion."""
        policy_id = "policy_001"

        # get_policy call (to verify exists), then delete query
        mock_graph_store.execute_query.side_effect = [
            [{"policy_id": policy_id}],  # get_policy: policy exists
            [],  # DETACH DELETE
        ]

        success = policy_engine.delete_policy(policy_id)

        assert success is True
        assert mock_graph_store.execute_query.call_count >= 1
    
    def test_delete_policy_not_found(self, policy_engine, mock_graph_store):
        """Test policy deletion when policy not found."""
        mock_graph_store.execute_query.return_value = []
        
        with pytest.raises(ValueError, match="Policy.*not found"):
            policy_engine.delete_policy("nonexistent_policy")
    
    def test_evaluate_compliance_numeric_rules(self, policy_engine):
        """Test compliance evaluation with numeric rules."""
        from semantica.context.decision_models import Decision
        
        decision = Decision(
            decision_id="decision_001",
            category="credit_approval",
            scenario="Credit application",
            reasoning="Customer score 700, debt ratio 0.3",
            outcome="approved",
            confidence=0.9,
            timestamp=datetime.now(),
            decision_maker="ai_agent",
            metadata={"credit_score": 700, "debt_ratio": 0.3}
        )
        
        rules = {"min_credit_score": 650, "max_debt_ratio": 0.4}
        
        is_compliant = policy_engine._evaluate_compliance(decision, rules)
        
        assert is_compliant is True
    
    def test_evaluate_compliance_string_rules(self, policy_engine):
        """Test compliance evaluation with string rules."""
        from semantica.context.decision_models import Decision
        
        decision = Decision(
            decision_id="decision_001",
            category="fraud_detection",
            scenario="Fraud check",
            reasoning="Customer passed all verification",
            outcome="approved",
            confidence=0.9,
            timestamp=datetime.now(),
            decision_maker="ai_agent",
            metadata={"verification_status": "passed", "risk_level": "low"}
        )
        
        rules = {"required_status": "passed", "max_risk_level": "medium"}
        
        is_compliant = policy_engine._evaluate_compliance(decision, rules)
        
        assert is_compliant is True
    
    def test_evaluate_compliance_list_rules(self, policy_engine):
        """Test compliance evaluation with list rules."""
        from semantica.context.decision_models import Decision
        
        decision = Decision(
            decision_id="decision_001",
            category="credit_approval",
            scenario="Credit application",
            reasoning="All required documents submitted",
            outcome="approved",
            confidence=0.9,
            timestamp=datetime.now(),
            decision_maker="ai_agent",
            metadata={"submitted_documents": ["income_proof", "employment_proof", "id_proof"]}
        )
        
        rules = {"required_documents": ["income_proof", "employment_proof"]}
        
        is_compliant = policy_engine._evaluate_compliance(decision, rules)
        
        assert is_compliant is True
    
    def test_calculate_impact_metrics(self, policy_engine):
        """Test impact metrics calculation."""
        current_rules = {"min_score": 650}
        proposed_rules = {"min_score": 700}
        affected_decisions = [
            {"decision_id": "decision_001", "compliance_score": 0.8},
            {"decision_id": "decision_002", "compliance_score": 0.6}
        ]
        
        metrics = policy_engine._calculate_impact_metrics(
            current_rules, proposed_rules, affected_decisions
        )
        
        assert "affected_decisions" in metrics
        assert "compliance_impact" in metrics
        assert "rule_changes" in metrics
        assert metrics["affected_decisions"] == 2
    
    def test_validate_policy_rules_valid(self, policy_engine):
        """Test validation of valid policy rules."""
        valid_rules = {
            "min_credit_score": 650,
            "max_debt_ratio": 0.4,
            "required_documents": ["income_proof", "employment_proof"],
            "risk_categories": ["low", "medium", "high"]
        }
        
        # Should not raise exception
        policy_engine._validate_policy_rules(valid_rules)
    
    def test_validate_policy_rules_invalid(self, policy_engine):
        """Test validation of invalid policy rules."""
        invalid_rules = {
            "min_credit_score": "invalid_type",  # Should be numeric
            "max_debt_ratio": 1.5,  # Should be <= 1
            "required_documents": "not_a_list"  # Should be a list
        }
        
        with pytest.raises(ValueError, match="Invalid policy rules"):
            policy_engine._validate_policy_rules(invalid_rules)
    
    def test_query_execution_error_handling(self, policy_engine, mock_graph_store):
        """Test error handling during query execution."""
        mock_graph_store.execute_query.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            policy_engine.get_policy("policy_001")
    
    def test_malformed_query_results(self, policy_engine, mock_graph_store):
        """Test handling of partial query results — succeeds with defaults."""
        mock_graph_store.execute_query.return_value = [
            {"policy_id": "test"}  # Minimal dict handled gracefully
        ]

        policy = policy_engine.get_policy("test_policy")
        assert policy is not None
        assert policy.policy_id == "test"
    
    def test_concurrent_policy_operations(self, policy_engine, mock_graph_store):
        """Test concurrent policy operations."""
        import threading
        import time
        
        results = []
        errors = []
        
        def add_policy_thread(policy_name):
            try:
                mock_graph_store.execute_query.return_value = []
                policy = Policy(
                    policy_id=f"policy_{policy_name}",
                    name=policy_name,
                    description="Test policy",
                    rules={"test": "rule"},
                    category="test",
                    version="1.0",
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                policy_id = policy_engine.add_policy(policy)
                results.append(policy_id)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=add_policy_thread, args=(f"policy_{i}",))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        assert len(errors) == 0
        assert len(results) == 5


class TestPolicyEngineEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def mock_graph_store(self):
        """Mock graph store for testing."""
        mock_store = Mock()
        mock_store.execute_query = Mock(return_value=[])
        return mock_store

    @pytest.fixture
    def policy_engine(self, mock_graph_store):
        """Create PolicyEngine with minimal dependencies."""
        return PolicyEngine(graph_store=mock_graph_store)
    
    def test_empty_policy_rules(self, policy_engine, mock_graph_store):
        """Test policy with empty rules."""
        policy = Policy(
            policy_id="policy_001",
            name="Empty Policy",
            description="Policy with no rules",
            rules={},  # Empty rules
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(policy)
        
        assert policy_id == "policy_001"
    
    def test_very_large_policy_rules(self, policy_engine, mock_graph_store):
        """Test policy with very large rules."""
        large_rules = {
            f"rule_{i}": f"value_{i}" for i in range(1000)
        }
        
        policy = Policy(
            policy_id="policy_001",
            name="Large Policy",
            description="Policy with many rules",
            rules=large_rules,
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(policy)
        
        assert policy_id == "policy_001"
    
    def test_policy_with_special_characters(self, policy_engine, mock_graph_store):
        """Test policy with special characters in fields."""
        policy = Policy(
            policy_id="policy_001",
            name="Policy with special chars: @#$%^&*()",
            description="Description with unicode: café résumé",
            rules={"special_field": "value with quotes: 'test'"},
            category="test_category",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"unicode": "测试", "emoji": "🚀"}
        )
        
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(policy)
        
        assert policy_id == "policy_001"
    
    def test_policy_version_format_validation(self, policy_engine):
        """Test policy version format validation."""
        # Valid versions
        valid_versions = ["1.0", "2.1.3", "10.0.0", "1.0-beta", "2.0.1-rc1"]
        
        for version in valid_versions:
            # Should not raise exception
            policy_engine._validate_version_format(version)
        
        # Invalid versions
        invalid_versions = ["", "not_a_version", "1", "1.", ".1", "a.b.c"]
        
        for version in invalid_versions:
            with pytest.raises(ValueError, match="Invalid version format"):
                policy_engine._validate_version_format(version)
    
    def test_policy_with_future_timestamps(self, policy_engine, mock_graph_store):
        """Test policy with future timestamps."""
        future_time = datetime.now() + timedelta(days=1)
        
        policy = Policy(
            policy_id="policy_001",
            name="Future Policy",
            description="Policy with future timestamp",
            rules={"test": "rule"},
            category="test",
            version="1.0",
            created_at=future_time,
            updated_at=future_time
        )
        
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(policy)
        
        assert policy_id == "policy_001"
    
    def test_policy_with_null_metadata(self, policy_engine, mock_graph_store):
        """Test policy with null metadata."""
        policy = Policy(
            policy_id="policy_001",
            name="Null Metadata Policy",
            description="Policy with null metadata",
            rules={"test": "rule"},
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata=None  # Null metadata
        )
        
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(policy)
        
        assert policy_id == "policy_001"
    
    def test_compliance_evaluation_with_missing_metadata(self, policy_engine):
        """Test compliance evaluation when decision metadata is missing."""
        from semantica.context.decision_models import Decision
        
        decision = Decision(
            decision_id="decision_001",
            category="test",
            scenario="test",
            reasoning="test",
            outcome="test",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test"
            # No metadata
        )
        
        rules = {"required_field": "value"}
        
        # Should handle missing metadata gracefully
        is_compliant = policy_engine._evaluate_compliance(decision, rules)
        
        assert is_compliant is False  # Should be non-compliant when required data is missing
    
    def test_very_long_policy_descriptions(self, policy_engine, mock_graph_store):
        """Test policy with very long descriptions."""
        long_description = "test " * 10000  # Very long description
        
        policy = Policy(
            policy_id="policy_001",
            name="Long Description Policy",
            description=long_description,
            rules={"test": "rule"},
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(policy)
        
        assert policy_id == "policy_001"
    
    def test_policy_with_nested_rules(self, policy_engine, mock_graph_store):
        """Test policy with nested rule structures."""
        nested_rules = {
            "credit_criteria": {
                "min_score": 650,
                "max_debt_ratio": 0.4,
                "sub_criteria": {
                    "employment_history": {"min_months": 6},
                    "residence_history": {"min_months": 12}
                }
            },
            "risk_assessment": {
                "factors": ["credit_score", "debt_ratio", "employment"],
                "weights": [0.4, 0.3, 0.3]
            }
        }
        
        policy = Policy(
            policy_id="policy_001",
            name="Nested Rules Policy",
            description="Policy with nested rule structures",
            rules=nested_rules,
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        mock_graph_store.execute_query.return_value = []
        
        policy_id = policy_engine.add_policy(policy)
        
        assert policy_id == "policy_001"


if __name__ == "__main__":
    pytest.main([__file__])
