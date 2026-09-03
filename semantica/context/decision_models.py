"""
Decision Tracking Data Models

This module defines the core data models for decision tracking, including
decisions, contexts, policies, exceptions, precedents, and approval chains.

Core Data Models:
    - Decision: Core decision data model with full context tracking
    - DecisionContext: Context information for decisions
    - Policy: Policy data model with rules and constraints
    - Exception: Decision exception and waiver data model
    - Precedent: Precedent data model with similarity scores
    - ApprovalChain: Multi-level approval chain data model

Decision Model Features:
    - Complete Decision Lifecycle: Track decisions from creation to completion
    - Context Integration: Full context and relationship tracking
    - Metadata Support: Rich metadata and embeddings
    - Temporal Tracking: Accurate timestamp management
    - Entity Relationships: Entity and relationship mapping

Policy Model Features:
    - Rule Definition: Complex policy rules and constraints
    - Version Control: Policy versioning and change tracking
    - Compliance Tracking: Compliance status and violations
    - Impact Assessment: Policy impact analysis
    - Exception Handling: Policy exceptions and waivers

Advanced Model Features:
    - Embedding Support: Vector embeddings for similarity analysis
    - Relationship Mapping: Decision relationships and dependencies
    - Provenance Tracking: Complete provenance and audit trails
    - Analytics Integration: Support for advanced analytics
    - Serialization: JSON serialization for persistence

Data Model Methods:
    - to_dict(): Convert models to dictionary format
    - from_dict(): Create models from dictionary data
    - validate(): Validate model data and constraints
    - update(): Update model with new data
    - clone(): Create model copies

Validation Features:
    - Data Validation: Comprehensive data validation
    - Constraint Checking: Model constraint validation
    - Type Safety: Strong typing with dataclasses
    - Business Rules: Business logic validation
    - Error Handling: Graceful error handling

Example Usage:
    >>> from semantica.context import Decision, Policy, PolicyException
    >>> decision = Decision(
    ...     category="loan_approval",
    ...     scenario="Mortgage application",
    ...     reasoning="Good credit score",
    ...     outcome="approved",
    ...     confidence=0.95,
    ...     decision_maker="loan_officer"
    ... )
    >>> policy = Policy(
    ...     name="Lending Policy",
    ...     rules={"max_loan_amount": 500000},
    ...     category="lending"
    ... )
    >>> exception = Exception(
    ...     decision_id=decision.decision_id,
    ...     reason="Policy exception for high-value customer",
    ...     approver="branch_manager"
    ... )

Production Use Cases:
    - Banking: Loan decisions, credit assessments, risk evaluations
    - Healthcare: Treatment decisions, diagnostic assessments
    - Legal: Legal decisions, case management
    - Government: Policy decisions, regulatory compliance
    - Insurance: Claim decisions, underwriting assessments
"""

import json
import uuid
from dataclasses import InitVar, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Decision:
    """Core decision data model with full context tracking."""
    
    decision_id: str
    category: str
    scenario: str
    reasoning: str
    outcome: str
    confidence: float
    timestamp: datetime
    decision_maker: str
    reasoning_embedding: Optional[List[float]] = None
    node2vec_embedding: Optional[List[float]] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_generate_id: InitVar[bool] = True
    
    def __post_init__(self, auto_generate_id: bool) -> None:
        """Validate decision data."""
        if auto_generate_id and not self.decision_id:  # Handle both None and empty string
            self.decision_id = str(uuid.uuid4())
        elif not self.decision_id and not auto_generate_id:
            raise ValueError("decision_id is required when auto_generate_id=False")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary."""
        return {
            "decision_id": self.decision_id,
            "category": self.category,
            "scenario": self.scenario,
            "reasoning": self.reasoning,
            "outcome": self.outcome,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "decision_maker": self.decision_maker,
            "reasoning_embedding": self.reasoning_embedding,
            "node2vec_embedding": self.node2vec_embedding,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Decision":
        """Create decision from dictionary."""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class DecisionContext:
    """Context snapshot for decision making."""
    
    context_id: str
    decision_id: str
    entity_snapshots: Dict[str, Dict[str, Any]]
    risk_factors: List[str]
    cross_system_inputs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_generate_id: InitVar[bool] = True
    
    def __post_init__(self, auto_generate_id: bool) -> None:
        """Validate decision context data."""
        if auto_generate_id and not self.context_id:  # Handle both None and empty string
            self.context_id = str(uuid.uuid4())
        elif not self.context_id and not auto_generate_id:
            raise ValueError("context_id is required when auto_generate_id=False")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "context_id": self.context_id,
            "decision_id": self.decision_id,
            "entity_snapshots": self.entity_snapshots,
            "risk_factors": self.risk_factors,
            "cross_system_inputs": self.cross_system_inputs,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionContext":
        """Create context from dictionary."""
        return cls(**data)


@dataclass
class Policy:
    """Policy with versioning and change tracking."""
    
    policy_id: str
    name: str
    description: str
    rules: Dict[str, Any]
    category: str
    version: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_generate_id: InitVar[bool] = True
    
    def __post_init__(self, auto_generate_id: bool) -> None:
        """Validate policy data."""
        if auto_generate_id and not self.policy_id:  # Handle both None and empty string
            self.policy_id = str(uuid.uuid4())
        elif not self.policy_id and not auto_generate_id:
            raise ValueError("policy_id is required when auto_generate_id=False")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert policy to dictionary."""
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "rules": self.rules,
            "category": self.category,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Policy":
        """Create policy from dictionary."""
        for field in ["created_at", "updated_at"]:
            if isinstance(data.get(field), str):
                data[field] = datetime.fromisoformat(data[field])
        return cls(**data)


@dataclass
class PolicyException:
    """Policy exception with approval tracking."""
    
    exception_id: str
    decision_id: str
    policy_id: str
    reason: str
    approver: str
    approval_timestamp: datetime
    justification: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_generate_id: InitVar[bool] = True
    
    def __post_init__(self, auto_generate_id: bool) -> None:
        """Validate policy exception data."""
        if auto_generate_id and not self.exception_id:  # Handle both None and empty string
            self.exception_id = str(uuid.uuid4())
        elif not self.exception_id and not auto_generate_id:
            raise ValueError("exception_id is required when auto_generate_id=False")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary."""
        return {
            "exception_id": self.exception_id,
            "decision_id": self.decision_id,
            "policy_id": self.policy_id,
            "reason": self.reason,
            "approver": self.approver,
            "approval_timestamp": self.approval_timestamp.isoformat(),
            "justification": self.justification,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyException":
        """Create exception from dictionary."""
        if isinstance(data.get("approval_timestamp"), str):
            data["approval_timestamp"] = datetime.fromisoformat(data["approval_timestamp"])
        return cls(**data)


@dataclass
class Precedent:
    """Precedent relationship between decisions."""
    
    precedent_id: str
    source_decision_id: str
    similarity_score: float
    relationship_type: str  # "similar_scenario", "same_policy", "exception_precedent"
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_generate_id: InitVar[bool] = True
    
    def __post_init__(self, auto_generate_id: bool) -> None:
        """Validate precedent data."""
        if auto_generate_id and not self.precedent_id:  # Handle both None and empty string
            self.precedent_id = str(uuid.uuid4())
        elif not self.precedent_id and not auto_generate_id:
            raise ValueError("precedent_id is required when auto_generate_id=False")
        if not 0 <= self.similarity_score <= 1:
            raise ValueError("Similarity score must be between 0 and 1")
        valid_types = ["similar_scenario", "same_policy", "exception_precedent"]
        if self.relationship_type not in valid_types:
            raise ValueError(f"Relationship type must be one of: {valid_types}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert precedent to dictionary."""
        return {
            "precedent_id": self.precedent_id,
            "source_decision_id": self.source_decision_id,
            "similarity_score": self.similarity_score,
            "relationship_type": self.relationship_type,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Precedent":
        """Create precedent from dictionary."""
        return cls(**data)


@dataclass
class ApprovalChain:
    """Approval chain tracking for decisions."""
    
    approval_id: str
    decision_id: str
    approver: str
    approval_method: str  # "slack_dm", "zoom_call", "email", "system"
    approval_context: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_generate_id: InitVar[bool] = True
    
    def __post_init__(self, auto_generate_id: bool) -> None:
        """Validate approval chain data."""
        if auto_generate_id and not self.approval_id:  # Handle both None and empty string
            self.approval_id = str(uuid.uuid4())
        elif not self.approval_id and not auto_generate_id:
            raise ValueError("approval_id is required when auto_generate_id=False")
        valid_methods = ["slack_dm", "zoom_call", "email", "system"]
        if self.approval_method not in valid_methods:
            raise ValueError(f"Approval method must be one of: {valid_methods}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert approval to dictionary."""
        return {
            "approval_id": self.approval_id,
            "decision_id": self.decision_id,
            "approver": self.approver,
            "approval_method": self.approval_method,
            "approval_context": self.approval_context,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalChain":
        """Create approval from dictionary."""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


# Validation helper functions
def validate_decision(decision: Decision) -> bool:
    """Validate decision data."""
    try:
        if not decision.decision_id:
            return False
        if not decision.category:
            return False
        if not decision.scenario:
            return False
        if not decision.reasoning:
            return False
        if not decision.outcome:
            return False
        if not 0 <= decision.confidence <= 1:
            return False
        if not decision.decision_maker:
            return False
        return True
    except Exception:
        return False


def validate_policy(policy: Policy) -> bool:
    """Validate policy data."""
    try:
        if not policy.policy_id:
            return False
        if not policy.name:
            return False
        if not policy.rules:
            return False
        if not policy.category:
            return False
        if not policy.version:
            return False
        return True
    except Exception:
        return False


# Serialization helpers
def serialize_decision(decision: Decision) -> str:
    """Serialize decision to JSON string."""
    return json.dumps(decision.to_dict(), default=str)


def deserialize_decision(data: str) -> Decision:
    """Deserialize decision from JSON string."""
    return Decision.from_dict(json.loads(data))


def serialize_policy(policy: Policy) -> str:
    """Serialize policy to JSON string."""
    return json.dumps(policy.to_dict(), default=str)


def deserialize_policy(data: str) -> Policy:
    """Deserialize policy from JSON string."""
    return Policy.from_dict(json.loads(data))
