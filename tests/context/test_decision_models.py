"""
Tests for Decision Tracking Data Models

This module tests the decision tracking data models including
validation, serialization, and deserialization.
"""

from datetime import datetime

import pytest

from semantica.context.decision_models import (
    ApprovalChain,
    Decision,
    DecisionContext,
    Policy,
    PolicyException,
    Precedent,
    deserialize_decision,
    deserialize_policy,
    serialize_decision,
    serialize_policy,
    validate_decision,
    validate_policy,
)


class TestDecision:
    """Test Decision data model."""
    
    def test_decision_creation(self):
        """Test basic decision creation."""
        decision = Decision(
            decision_id="test_001",
            category="credit_approval",
            scenario="Credit limit increase request",
            reasoning="Customer has excellent payment history",
            outcome="approved",
            confidence=0.85,
            timestamp=datetime.now(),
            decision_maker="ai_agent_001"
        )
        
        assert decision.decision_id == "test_001"
        assert decision.category == "credit_approval"
        assert decision.scenario == "Credit limit increase request"
        assert decision.reasoning == "Customer has excellent payment history"
        assert decision.outcome == "approved"
        assert decision.confidence == 0.85
        assert decision.decision_maker == "ai_agent_001"
    
    def test_decision_auto_id(self):
        """Test automatic ID generation."""
        decision = Decision(
            decision_id="",
            category="test",
            scenario="test scenario",
            reasoning="test reasoning",
            outcome="test outcome",
            confidence=0.5,
            timestamp=datetime.now(),
            decision_maker="test_agent"
        )
        
        assert decision.decision_id != ""
        assert len(decision.decision_id) > 0
    
    def test_decision_confidence_validation(self):
        """Test confidence validation."""
        with pytest.raises(ValueError):
            Decision(
                decision_id="test",
                category="test",
                scenario="test",
                reasoning="test",
                outcome="test",
                confidence=1.5,  # Invalid confidence > 1
                timestamp=datetime.now(),
                decision_maker="test"
            )
        
        with pytest.raises(ValueError):
            Decision(
                decision_id="test",
                category="test",
                scenario="test",
                reasoning="test",
                outcome="test",
                confidence=-0.1,  # Invalid confidence < 0
                timestamp=datetime.now(),
                decision_maker="test"
            )
    
    def test_decision_to_dict(self):
        """Test decision serialization to dictionary."""
        decision = Decision(
            decision_id="test_001",
            category="test",
            scenario="test scenario",
            reasoning="test reasoning",
            outcome="test outcome",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test_agent",
            metadata={"key": "value"}
        )
        
        decision_dict = decision.to_dict()
        
        assert decision_dict["decision_id"] == "test_001"
        assert decision_dict["category"] == "test"
        assert decision_dict["scenario"] == "test scenario"
        assert decision_dict["reasoning"] == "test reasoning"
        assert decision_dict["outcome"] == "test outcome"
        assert decision_dict["confidence"] == 0.8
        assert decision_dict["decision_maker"] == "test_agent"
        assert decision_dict["metadata"]["key"] == "value"
        assert isinstance(decision_dict["timestamp"], str)
    
    def test_decision_from_dict(self):
        """Test decision deserialization from dictionary."""
        decision_data = {
            "decision_id": "test_001",
            "category": "test",
            "scenario": "test scenario",
            "reasoning": "test reasoning",
            "outcome": "test outcome",
            "confidence": 0.8,
            "timestamp": datetime.now().isoformat(),
            "decision_maker": "test_agent",
            "metadata": {"key": "value"}
        }
        
        decision = Decision.from_dict(decision_data)
        
        assert decision.decision_id == "test_001"
        assert decision.category == "test"
        assert decision.scenario == "test scenario"
        assert decision.reasoning == "test reasoning"
        assert decision.outcome == "test outcome"
        assert decision.confidence == 0.8
        assert decision.decision_maker == "test_agent"
        assert decision.metadata["key"] == "value"
        assert isinstance(decision.timestamp, datetime)


class TestDecisionContext:
    """Test DecisionContext data model."""
    
    def test_decision_context_creation(self):
        """Test basic decision context creation."""
        context = DecisionContext(
            context_id="ctx_001",
            decision_id="decision_001",
            entity_snapshots={"entity1": {"name": "test", "type": "person"}},
            risk_factors=["high_risk", "new_customer"],
            cross_system_inputs={"salesforce": {"tier": "premium"}},
            metadata={"version": "1.0"}
        )
        
        assert context.context_id == "ctx_001"
        assert context.decision_id == "decision_001"
        assert len(context.entity_snapshots) == 1
        assert context.entity_snapshots["entity1"]["name"] == "test"
        assert context.risk_factors == ["high_risk", "new_customer"]
        assert context.cross_system_inputs["salesforce"]["tier"] == "premium"
        assert context.metadata["version"] == "1.0"
    
    def test_decision_context_auto_id(self):
        """Test automatic ID generation."""
        context = DecisionContext(
            context_id="",
            decision_id="decision_001",
            entity_snapshots={},
            risk_factors=[]
        )
        
        assert context.context_id != ""
        assert len(context.context_id) > 0


class TestPolicy:
    """Test Policy data model."""
    
    def test_policy_creation(self):
        """Test basic policy creation."""
        now = datetime.now()
        policy = Policy(
            policy_id="policy_001",
            name="Credit Approval Policy",
            description="Standard credit approval rules",
            rules={"min_score": 650, "max_debt_ratio": 0.4},
            category="credit_approval",
            version="1.0",
            created_at=now,
            updated_at=now,
            metadata={"department": "risk"}
        )
        
        assert policy.policy_id == "policy_001"
        assert policy.name == "Credit Approval Policy"
        assert policy.description == "Standard credit approval rules"
        assert policy.rules["min_score"] == 650
        assert policy.category == "credit_approval"
        assert policy.version == "1.0"
        assert policy.metadata["department"] == "risk"
    
    def test_policy_auto_id(self):
        """Test automatic ID generation."""
        policy = Policy(
            policy_id="",
            name="Test Policy",
            description="Test description",
            rules={"test": "rule"},
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        assert policy.policy_id != ""
        assert len(policy.policy_id) > 0


class TestPolicyException:
    """Test PolicyException data model."""
    
    def test_policy_exception_creation(self):
        """Test basic policy exception creation."""
        policy_exception = PolicyException(
            exception_id="exc_001",
            decision_id="decision_001",
            policy_id="policy_001",
            reason="Customer is VIP with special arrangements",
            approver="manager_001",
            approval_timestamp=datetime.now(),
            justification="Long-term customer with excellent history",
            metadata={"override_type": "vip_exception"}
        )
        
        assert policy_exception.exception_id == "exc_001"
        assert policy_exception.decision_id == "decision_001"
        assert policy_exception.policy_id == "policy_001"
        assert policy_exception.reason == "Customer is VIP with special arrangements"
        assert policy_exception.approver == "manager_001"
        assert policy_exception.justification == "Long-term customer with excellent history"
        assert policy_exception.metadata["override_type"] == "vip_exception"
    
    def test_policy_exception_auto_id(self):
        """Test automatic ID generation."""
        policy_exception = PolicyException(
            exception_id="",
            decision_id="decision_001",
            policy_id="policy_001",
            reason="test reason",
            approver="test_approver",
            approval_timestamp=datetime.now(),
            justification="test justification"
        )
        
        assert policy_exception.exception_id != ""
        assert len(policy_exception.exception_id) > 0


class TestPrecedent:
    """Test Precedent data model."""
    
    def test_precedent_creation(self):
        """Test basic precedent creation."""
        precedent = Precedent(
            precedent_id="prec_001",
            source_decision_id="decision_001",
            similarity_score=0.85,
            relationship_type="similar_scenario",
            metadata={"matched_features": ["category", "amount"]}
        )
        
        assert precedent.precedent_id == "prec_001"
        assert precedent.source_decision_id == "decision_001"
        assert precedent.similarity_score == 0.85
        assert precedent.relationship_type == "similar_scenario"
        assert precedent.metadata["matched_features"] == ["category", "amount"]
    
    def test_precedent_validation(self):
        """Test precedent validation."""
        # Test invalid similarity score
        with pytest.raises(ValueError):
            Precedent(
                precedent_id="test",
                source_decision_id="test",
                similarity_score=1.5,  # Invalid > 1
                relationship_type="similar_scenario"
            )
        
        # Test invalid relationship type
        with pytest.raises(ValueError):
            Precedent(
                precedent_id="test",
                source_decision_id="test",
                similarity_score=0.8,
                relationship_type="invalid_type"
            )


class TestApprovalChain:
    """Test ApprovalChain data model."""
    
    def test_approval_chain_creation(self):
        """Test basic approval chain creation."""
        approval = ApprovalChain(
            approval_id="app_001",
            decision_id="decision_001",
            approver="manager_001",
            approval_method="slack_dm",
            approval_context="Approved via Slack DM with justification",
            timestamp=datetime.now(),
            metadata={"message_id": "msg_12345"}
        )
        
        assert approval.approval_id == "app_001"
        assert approval.decision_id == "decision_001"
        assert approval.approver == "manager_001"
        assert approval.approval_method == "slack_dm"
        assert approval.approval_context == "Approved via Slack DM with justification"
        assert approval.metadata["message_id"] == "msg_12345"
    
    def test_approval_chain_validation(self):
        """Test approval chain validation."""
        # Test invalid approval method
        with pytest.raises(ValueError):
            ApprovalChain(
                approval_id="test",
                decision_id="test",
                approver="test",
                approval_method="invalid_method",  # Invalid method
                approval_context="test context",
                timestamp=datetime.now()
            )


class TestValidationFunctions:
    """Test validation helper functions."""
    
    def test_validate_decision(self):
        """Test decision validation."""
        # Valid decision
        valid_decision = Decision(
            decision_id="test",
            category="test",
            scenario="test",
            reasoning="test",
            outcome="test",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test"
        )
        assert validate_decision(valid_decision) is True
        
        # Invalid decision (missing required field)
        invalid_decision = Decision(
            decision_id="test",
            category="",  # Empty category
            scenario="test",
            reasoning="test",
            outcome="test",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test"
        )
        assert validate_decision(invalid_decision) is False
    
    def test_validate_policy(self):
        """Test policy validation."""
        # Valid policy
        valid_policy = Policy(
            policy_id="test",
            name="Test Policy",
            description="Test description",
            rules={"test": "rule"},
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        assert validate_policy(valid_policy) is True
        
        # Invalid policy (missing required field)
        invalid_policy = Policy(
            policy_id="test",
            name="Test Policy",
            description="Test description",
            rules={"test": "rule"},
            category="",  # Empty category
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        assert validate_policy(invalid_policy) is False


class TestSerializationFunctions:
    """Test serialization helper functions."""
    
    def test_serialize_deserialize_decision(self):
        """Test decision serialization and deserialization."""
        original_decision = Decision(
            decision_id="test_001",
            category="test",
            scenario="test scenario",
            reasoning="test reasoning",
            outcome="test outcome",
            confidence=0.8,
            timestamp=datetime.now(),
            decision_maker="test_agent",
            metadata={"key": "value"}
        )
        
        # Serialize
        serialized = serialize_decision(original_decision)
        assert isinstance(serialized, str)
        
        # Deserialize
        deserialized = deserialize_decision(serialized)
        
        assert deserialized.decision_id == original_decision.decision_id
        assert deserialized.category == original_decision.category
        assert deserialized.scenario == original_decision.scenario
        assert deserialized.reasoning == original_decision.reasoning
        assert deserialized.outcome == original_decision.outcome
        assert deserialized.confidence == original_decision.confidence
        assert deserialized.decision_maker == original_decision.decision_maker
        assert deserialized.metadata == original_decision.metadata
    
    def test_serialize_deserialize_policy(self):
        """Test policy serialization and deserialization."""
        original_policy = Policy(
            policy_id="policy_001",
            name="Test Policy",
            description="Test description",
            rules={"test": "rule"},
            category="test",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"department": "risk"}
        )
        
        # Serialize
        serialized = serialize_policy(original_policy)
        assert isinstance(serialized, str)
        
        # Deserialize
        deserialized = deserialize_policy(serialized)
        
        assert deserialized.policy_id == original_policy.policy_id
        assert deserialized.name == original_policy.name
        assert deserialized.description == original_policy.description
        assert deserialized.rules == original_policy.rules
        assert deserialized.category == original_policy.category
        assert deserialized.version == original_policy.version
        assert deserialized.metadata == original_policy.metadata


class TestAutoGenerateIdContract:
    """Test the auto_generate_id InitVar contract across all decision models.

    Regression coverage for the InitVar fix: previously ``auto_generate_id``
    was a plain ``__post_init__`` parameter that dataclass-generated ``__init__``
    never forwarded, so the ``auto_generate_id=False`` branch was dead code and
    the "id is required" contract could never fire.
    """

    def _base_kwargs(self, cls):
        now = datetime.now()
        return {
            Decision: dict(
                decision_id="", category="c", scenario="s", reasoning="r",
                outcome="o", confidence=0.5, timestamp=now, decision_maker="m",
            ),
            DecisionContext: dict(
                context_id="", decision_id="d", entity_snapshots={}, risk_factors=[],
            ),
            Policy: dict(
                policy_id="", name="n", description="d", rules={}, category="c",
                version="1", created_at=now, updated_at=now,
            ),
            PolicyException: dict(
                exception_id="", decision_id="d", policy_id="p", reason="r",
                approver="a", approval_timestamp=now, justification="j",
            ),
            Precedent: dict(
                precedent_id="", source_decision_id="d", similarity_score=0.5,
                relationship_type="same_policy",
            ),
            ApprovalChain: dict(
                approval_id="", decision_id="d", approver="a",
                approval_method="email", approval_context="x", timestamp=now,
            ),
        }[cls]

    @pytest.mark.parametrize(
        "cls",
        [Decision, DecisionContext, Policy, PolicyException, Precedent, ApprovalChain],
    )
    def test_auto_generate_id_is_not_a_field(self, cls):
        """auto_generate_id must stay an InitVar, never a real dataclass field."""
        import dataclasses

        names = [f.name for f in dataclasses.fields(cls)]
        assert "auto_generate_id" not in names

    @pytest.mark.parametrize(
        "cls",
        [Decision, DecisionContext, Policy, PolicyException, Precedent, ApprovalChain],
    )
    def test_default_auto_generates_id(self, cls):
        """With defaults, an empty id is auto-populated and stays a non-field."""
        obj = cls(**self._base_kwargs(cls))
        id_field = [f.name for f in __import__("dataclasses").fields(cls)][0]
        assert getattr(obj, id_field)
        assert "auto_generate_id" not in vars(obj)

    @pytest.mark.parametrize(
        "cls",
        [Decision, DecisionContext, Policy, PolicyException, Precedent, ApprovalChain],
    )
    def test_required_id_when_auto_generate_disabled(self, cls):
        """auto_generate_id=False with an empty id must raise ValueError."""
        with pytest.raises(ValueError):
            cls(auto_generate_id=False, **self._base_kwargs(cls))

    def test_explicit_id_honored_with_auto_generate_disabled(self):
        """A provided id is preserved when auto_generate_id=False."""
        kwargs = self._base_kwargs(Decision)
        kwargs["decision_id"] = "fixed-id"
        decision = Decision(auto_generate_id=False, **kwargs)
        assert decision.decision_id == "fixed-id"
        assert "auto_generate_id" not in decision.to_dict()


if __name__ == "__main__":
    pytest.main([__file__])
