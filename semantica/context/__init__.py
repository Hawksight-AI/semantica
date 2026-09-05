"""
Context Engineering Module

Comprehensive context engineering infrastructure for agents with RAG, knowledge
graphs, and advanced decision tracking integration.

Core Features:
    - High-level interface (AgentContext) for easy use
    - Context graph construction from entities and conversations
    - Agent memory management with RAG integration
    - Entity linking across sources with URI assignment
    - Hybrid context retrieval (vector + graph + memory)
    - Conversation history management

Advanced Decision Tracking:
    - Complete decision lifecycle management
    - Hybrid precedent search (semantic + structural + vector)
    - Causal chain analysis and decision influence tracing
    - Policy engine for governance and compliance
    - Explainable AI with decision path tracing
    - Advanced analytics with KG algorithm integration

KG Algorithm Integration:
    - Centrality Analysis: Degree, betweenness, closeness, eigenvector centrality
    - Community Detection: Modularity-based community identification
    - Node Embeddings: Node2Vec embeddings for similarity analysis
    - Path Finding: Shortest path and advanced path algorithms
    - Link Prediction: Relationship prediction between entities
    - Similarity Calculation: Multi-type similarity measures
    - Graph Analytics: Comprehensive graph structure analysis

Vector Store Integration:
    - Hybrid Search: Semantic + structural similarity
    - Custom Similarity Weights: Configurable scoring
    - Advanced Precedent Search: KG-enhanced similarity
    - Multi-Embedding Support: Multiple embedding types
    - Metadata Filtering: Advanced filtering capabilities

Enhanced Analytics:
    - Decision Influence Analysis: Centrality-based influence scoring
    - Relationship Prediction: Link prediction for decisions
    - Context Insights: Comprehensive system analytics
    - Entity Similarity: Advanced entity similarity search
    - Graph Analytics: Node centrality, community detection, embeddings
    - Cross-Departmental Analysis: Multi-domain decision analysis

Main Classes:
    - AgentContext: High-level interface with KG integration
    - ContextGraph: In-memory graph store with KG algorithm support and comprehensive decision management
    - ContextNode/ContextEdge: Graph data structures
    - AgentMemory: Persistent agent memory with RAG
    - MemoryItem: Memory item data structure
    - EntityLinker: Links entities across sources with URIs
    - ContextRetriever: Retrieves relevant context from multiple sources

Decision Tracking Classes:
    - Decision: Decision data structure with metadata and embeddings
    - DecisionRecorder: Records decisions with context and metadata
    - DecisionQuery: Advanced decision querying with KG and vector store
    - CausalChainAnalyzer: Traces decision causality and influence
    - PolicyEngine: Manages decision policies and compliance
    - DecisionContext: High-level decision tracking interface
    - Policy/Precedent/PolicyException: Decision tracking data structures

Example Usage:
    >>> from semantica.context import AgentContext, ContextGraph
    >>> # Simple AgentContext with decision tracking
    >>> context = AgentContext(vector_store=vs, knowledge_graph=kg, 
    ...                       decision_tracking=True,
    ...                       advanced_analytics=True,
    ...                       kg_algorithms=True,
    ...                       vector_store_features=True)
    >>> memory_id = context.store("User asked about Python", conversation_id="conv1")
    >>> results = context.retrieve("Python programming")
    >>> decision_id = context.record_decision(category="approval", 
    ...                                      scenario="Loan application",
    ...                                      reasoning="Good credit score",
    ...                                      outcome="approved",
    ...                                      confidence=0.95)
    >>> precedents = context.find_precedents_advanced("Loan application", 
    ...                                               category="approval",
    ...                                               use_kg_features=True)
    >>> influence = context.analyze_decision_influence(decision_id)
    >>> insights = context.get_context_insights()
    
    >>> # Comprehensive ContextGraph with all decision features
    >>> graph = ContextGraph(advanced_analytics=True, enable_causality=True)
    >>> decision_id = graph.record_decision(
    ...     category="loan_approval",
    ...     scenario="First-time homebuyer",
    ...     reasoning="Good credit score and stable income",
    ...     outcome="approved",
    ...     confidence=0.95,
    ...     entities=["customer_123", "property_456"]
    ... )
    >>> precedents = graph.find_precedents("loan_approval", limit=5)
    >>> influence = graph.analyze_decision_influence(decision_id)
    >>> insights = graph.get_decision_insights()
    >>> causality = graph.trace_decision_causality(decision_id)

Production Examples:
    - Banking: Mortgage approvals, credit decisions, risk assessment
    - Healthcare: Treatment approvals, diagnostic decisions, policy compliance
    - E-commerce: Personalization decisions, recommendation systems
    - Legal: Case precedent analysis, decision consistency
"""

from .agent_context import AgentContext
from .agent_memory import AgentMemory, MemoryItem
from .context_graph import ContextEdge, ContextGraph, ContextNode
from .context_retriever import ContextRetriever, RetrievedContext, TemporalGraphRetriever
from .decision_context import DecisionContext
from .entity_linker import EntityLink, EntityLinker, LinkedEntity
from .erasure import ErasureCoordinator, ErasureReceipt

# Decision tracking imports
from .decision_models import (
    Decision, DecisionContext as DecisionContextModel, Policy, 
    PolicyException, Precedent, ApprovalChain
)
from .decision_recorder import DecisionRecorder
from .decision_query import DecisionQuery
from .causal_analyzer import CausalChainAnalyzer
from .policy_engine import PolicyEngine
from .decision_methods import (
    record_decision, find_precedents, get_causal_chain, get_applicable_policies,
    multi_hop_query, capture_decision_trace, find_exception_precedents,
    analyze_decision_impact, create_policy_with_versioning, check_decision_compliance,
    get_decision_statistics, setup_decision_tracking
)
from .graph_schema import setup_decision_schema, verify_schema, get_schema_info

__all__ = [
    # High-level interface
    "AgentContext",
    "DecisionContext",
    # Main classes
    "ContextGraph",
    "ContextNode",
    "ContextEdge",
    "EntityLinker",
    "EntityLink",
    "LinkedEntity",
    "AgentMemory",
    "MemoryItem",
    "ContextRetriever",
    "RetrievedContext",
    "TemporalGraphRetriever",
    # Cross-store erasure
    "ErasureCoordinator",
    "ErasureReceipt",
    # Decision tracking models
    "Decision",
    "DecisionContextModel", 
    "Policy",
    "PolicyException",
    "Precedent",
    "ApprovalChain",
    # Decision tracking classes
    "DecisionRecorder",
    "DecisionQuery",
    "CausalChainAnalyzer",
    "PolicyEngine",
    # Decision tracking convenience functions
    "record_decision",
    "find_precedents",
    "get_causal_chain",
    "get_applicable_policies",
    "multi_hop_query",
    "capture_decision_trace",
    "find_exception_precedents",
    "analyze_decision_impact",
    "create_policy_with_versioning",
    "check_decision_compliance",
    "get_decision_statistics",
    "setup_decision_tracking",
    # Schema utilities
    "setup_decision_schema",
    "verify_schema",
    "get_schema_info",
]

# Backward compatibility alias
ContextGraphBuilder = ContextGraph
