"""
Graph Schema Setup for Decision Tracking

This module provides schema setup utilities for decision tracking,
including node labels, relationship types, and indexes for graph databases.
"""

import json
import warnings
from typing import Dict, Any, List

from ..graph_store import GraphStore
from ..utils.logging import get_logger


def setup_decision_schema(graph_store: GraphStore) -> None:
    """
    Create decision tracking schema in graph database.
    
    Args:
        graph_store: Graph database instance
    """
    logger = get_logger(__name__)
    
    try:
        # Create node labels and constraints
        create_decision_constraints(graph_store)
        
        # Create indexes
        create_decision_indexes(graph_store)
        
        logger.info("Decision tracking schema setup completed")
        
    except Exception as e:
        logger.error(f"Failed to setup decision schema: {e}")
        raise


def create_decision_constraints(graph_store: GraphStore) -> None:
    """
    Create constraints for decision tracking nodes.
    
    Args:
        graph_store: Graph database instance
    """
    constraints = [
        # Decision nodes
        "CREATE CONSTRAINT decision_id_unique IF NOT EXISTS FOR (d:Decision) REQUIRE d.decision_id IS UNIQUE",

        # Exception nodes
        "CREATE CONSTRAINT exception_id_unique IF NOT EXISTS FOR (e:Exception) REQUIRE e.exception_id IS UNIQUE",

        # ApprovalChain nodes
        "CREATE CONSTRAINT approval_id_unique IF NOT EXISTS FOR (a:ApprovalChain) REQUIRE a.approval_id IS UNIQUE",

        # DecisionContext nodes
        "CREATE CONSTRAINT context_id_unique IF NOT EXISTS FOR (c:DecisionContext) REQUIRE c.context_id IS UNIQUE",

        # Precedent nodes
        "CREATE CONSTRAINT precedent_id_unique IF NOT EXISTS FOR (pr:Precedent) REQUIRE pr.precedent_id IS UNIQUE",

        # Immutable trace nodes
        "CREATE CONSTRAINT decision_trace_id_unique IF NOT EXISTS FOR (t:DecisionTraceEvent) REQUIRE t.trace_id IS UNIQUE",
    ]

    # Policy versioning needs (policy_id, version) identity. Keep legacy fallback for old backends.
    try:
        # Drop legacy constraint when possible so versioned policies can coexist.
        graph_store.execute_query("DROP CONSTRAINT policy_id_unique IF EXISTS")
    except Exception as e:
        get_logger(__name__).warning(
            "Failed to drop legacy policy_id_unique constraint before policy "
            f"versioning migration: {e}"
        )

    try:
        graph_store.execute_query(
            "CREATE CONSTRAINT policy_identity_unique IF NOT EXISTS "
            "FOR (p:Policy) REQUIRE (p.policy_id, p.version) IS UNIQUE"
        )
    except Exception as e:
        get_logger(__name__).warning(
            "Composite policy constraint not supported; falling back to legacy "
            "policy_id uniqueness (policy versioning may be limited)"
        )
        try:
            graph_store.execute_query(
                "CREATE CONSTRAINT policy_id_unique IF NOT EXISTS FOR (p:Policy) REQUIRE p.policy_id IS UNIQUE"
            )
        except Exception as fallback_error:
            get_logger(__name__).debug(
                f"Policy constraint creation failed (may already exist): {fallback_error}"
            )
    
    for constraint in constraints:
        try:
            graph_store.execute_query(constraint)
        except Exception as e:
            # Constraint might already exist, continue
            get_logger(__name__).debug(f"Constraint creation failed (may already exist): {e}")


def create_decision_indexes(graph_store: GraphStore) -> None:
    """
    Create indexes for decision tracking performance.
    
    Args:
        graph_store: Graph database instance
    """
    indexes = [
        # Explicit identity indexes (helps verification and non-constraint lookups)
        "CREATE INDEX decision_id_index IF NOT EXISTS FOR (d:Decision) ON (d.decision_id)",
        "CREATE INDEX policy_id_index IF NOT EXISTS FOR (p:Policy) ON (p.policy_id)",
        "CREATE INDEX exception_id_index IF NOT EXISTS FOR (e:Exception) ON (e.exception_id)",
        "CREATE INDEX approval_id_index IF NOT EXISTS FOR (a:ApprovalChain) ON (a.approval_id)",
        "CREATE INDEX context_id_index IF NOT EXISTS FOR (c:DecisionContext) ON (c.context_id)",
        "CREATE INDEX precedent_id_index IF NOT EXISTS FOR (pr:Precedent) ON (pr.precedent_id)",
        "CREATE INDEX decision_trace_id_index IF NOT EXISTS FOR (t:DecisionTraceEvent) ON (t.trace_id)",

        # Decision indexes
        "CREATE INDEX decision_category_index IF NOT EXISTS FOR (d:Decision) ON (d.category)",
        "CREATE INDEX decision_timestamp_index IF NOT EXISTS FOR (d:Decision) ON (d.timestamp)",
        "CREATE INDEX decision_outcome_index IF NOT EXISTS FOR (d:Decision) ON (d.outcome)",
        "CREATE INDEX decision_confidence_index IF NOT EXISTS FOR (d:Decision) ON (d.confidence)",
        "CREATE INDEX decision_maker_index IF NOT EXISTS FOR (d:Decision) ON (d.decision_maker)",
        
        # Policy indexes
        "CREATE INDEX policy_category_index IF NOT EXISTS FOR (p:Policy) ON (p.category)",
        "CREATE INDEX policy_version_index IF NOT EXISTS FOR (p:Policy) ON (p.version)",
        "CREATE INDEX policy_name_index IF NOT EXISTS FOR (p:Policy) ON (p.name)",
        "CREATE INDEX policy_created_at_index IF NOT EXISTS FOR (p:Policy) ON (p.created_at)",
        
        # Exception indexes
        "CREATE INDEX exception_reason_index IF NOT EXISTS FOR (e:Exception) ON (e.reason)",
        "CREATE INDEX exception_approver_index IF NOT EXISTS FOR (e:Exception) ON (e.approver)",
        "CREATE INDEX exception_approval_timestamp_index IF NOT EXISTS FOR (e:Exception) ON (e.approval_timestamp)",
        
        # ApprovalChain indexes
        "CREATE INDEX approval_method_index IF NOT EXISTS FOR (a:ApprovalChain) ON (a.approval_method)",
        "CREATE INDEX approval_approver_index IF NOT EXISTS FOR (a:ApprovalChain) ON (a.approver)",
        "CREATE INDEX approval_timestamp_index IF NOT EXISTS FOR (a:ApprovalChain) ON (a.timestamp)",
        
        # DecisionContext indexes
        "CREATE INDEX context_decision_id_index IF NOT EXISTS FOR (c:DecisionContext) ON (c.decision_id)",
        
        # Precedent indexes
        "CREATE INDEX precedent_source_index IF NOT EXISTS FOR (pr:Precedent) ON (pr.source_decision_id)",
        "CREATE INDEX precedent_similarity_index IF NOT EXISTS FOR (pr:Precedent) ON (pr.similarity_score)",
        "CREATE INDEX precedent_type_index IF NOT EXISTS FOR (pr:Precedent) ON (pr.relationship_type)",
        
        # Cross-system context indexes
        "CREATE INDEX cross_system_name_index IF NOT EXISTS FOR (c:CrossSystemContext) ON (c.system_name)",
        "CREATE INDEX cross_system_created_at_index IF NOT EXISTS FOR (c:CrossSystemContext) ON (c.created_at)",

        # Decision trace indexes
        "CREATE INDEX decision_trace_event_index IF NOT EXISTS FOR (t:DecisionTraceEvent) ON (t.event_index)",
        "CREATE INDEX decision_trace_type_index IF NOT EXISTS FOR (t:DecisionTraceEvent) ON (t.event_type)",
        "CREATE INDEX decision_trace_timestamp_index IF NOT EXISTS FOR (t:DecisionTraceEvent) ON (t.event_timestamp)",
        
        # Entity type indexes for general graph operations
        "CREATE INDEX entity_type_index IF NOT EXISTS FOR (n) ON (n.type)",
        "CREATE INDEX entity_id_index IF NOT EXISTS FOR (n) ON (n.id)",
        
        # Relationship strength indexes
        "CREATE INDEX relationship_strength_index IF NOT EXISTS FOR ()-[r]-() ON (r.strength)",
        
        # Temporal indexes for time-based queries
        "CREATE INDEX temporal_before_index IF NOT EXISTS FOR ()-[r:BEFORE]-() ON (r.timestamp)",
        "CREATE INDEX temporal_after_index IF NOT EXISTS FOR ()-[r:AFTER]-() ON (r.timestamp)",
        "CREATE INDEX temporal_during_index IF NOT EXISTS FOR ()-[r:DURING]-() ON (r.timestamp)"
    ]
    
    for index in indexes:
        try:
            graph_store.execute_query(index)
        except Exception as e:
            # Index might already exist, continue
            get_logger(__name__).debug(f"Index creation failed (may already exist): {e}")


def verify_schema(graph_store: GraphStore) -> bool:
    """
    Verify that decision tracking schema exists.
    
    Args:
        graph_store: Graph database instance
        
    Returns:
        True if schema exists, False otherwise
    """
    logger = get_logger(__name__)
    
    try:
        # Check for key indexes
        index_checks = [
            "decision_id_index",
            "decision_category_index", 
            "policy_id_index",
            "policy_category_index",
            "exception_id_index",
            "approval_id_index",
            "decision_trace_id_index",
            "decision_trace_event_index",
            "decision_trace_type_index",
            "decision_trace_timestamp_index",
        ]
        
        for index_name in index_checks:
            try:
                # This query varies by database backend
                result = graph_store.execute_query(f"SHOW INDEXES WHERE name = '{index_name}'")
                if not result:
                    logger.warning(f"Missing index: {index_name}")
                    return False
            except Exception:
                # Fallback check - try a simple query that would use the index
                try:
                    if "decision" in index_name:
                        graph_store.execute_query("MATCH (d:Decision) RETURN d.decision_id LIMIT 1")
                    elif "policy" in index_name:
                        graph_store.execute_query("MATCH (p:Policy) RETURN p.policy_id LIMIT 1")
                    elif "exception" in index_name:
                        graph_store.execute_query("MATCH (e:Exception) RETURN e.exception_id LIMIT 1")
                    elif "approval" in index_name:
                        graph_store.execute_query("MATCH (a:ApprovalChain) RETURN a.approval_id LIMIT 1")
                except Exception as e:
                    logger.warning(f"Schema verification failed for {index_name}: {e}")
                    return False
        
        # Verify policy constraint compatibility:
        # prefer composite (policy_id, version), allow legacy policy_id uniqueness.
        try:
            constraints_result = graph_store.execute_query("SHOW CONSTRAINTS")
            constraint_records = (
                constraints_result.get("records", [])
                if isinstance(constraints_result, dict)
                else constraints_result
            )
            constraint_text = json.dumps(constraint_records, default=str).lower()
            has_composite = "policy_identity_unique" in constraint_text
            has_legacy = "policy_id_unique" in constraint_text
            if not (has_composite or has_legacy):
                logger.warning("Missing policy identity constraint (composite or legacy)")
                return False
        except Exception:
            # Backend may not support SHOW CONSTRAINTS; skip hard failure here.
            pass

        # Check for node labels
        label_checks = [
            "Decision",
            "Policy", 
            "Exception",
            "ApprovalChain",
            "DecisionContext",
            "Precedent",
            "DecisionTraceEvent",
        ]
        
        for label in label_checks:
            try:
                result = graph_store.execute_query(f"MATCH (n:{label}) RETURN count(n) as count LIMIT 1")
                # Query succeeded, label exists
            except Exception as e:
                logger.warning(f"Missing node label: {label}")
                return False
        
        logger.info("Schema verification passed")
        return True
        
    except Exception as e:
        logger.error(f"Schema verification failed: {e}")
        return False


def get_schema_info() -> Dict[str, Any]:
    """
    Get information about the decision tracking schema.
    
    Returns:
        Schema information dictionary
    """
    return {
        "node_labels": {
            "Decision": {
                "properties": [
                    "decision_id", "category", "scenario", "reasoning", 
                    "outcome", "confidence", "timestamp", "decision_maker",
                    "reasoning_embedding", "node2vec_embedding", "metadata"
                ],
                "constraints": ["decision_id_unique"],
                "indexes": ["decision_id_index", "decision_category_index", "decision_timestamp_index"]
            },
            "Policy": {
                "properties": [
                    "policy_id", "name", "description", "rules", "category",
                    "version", "created_at", "updated_at", "metadata"
                ],
                "constraints": ["policy_identity_unique"],
                "indexes": ["policy_id_index", "policy_category_index", "policy_version_index"]
            },
            "Exception": {
                "properties": [
                    "exception_id", "decision_id", "policy_id", "reason",
                    "approver", "approval_timestamp", "justification", "metadata"
                ],
                "constraints": ["exception_id_unique"],
                "indexes": ["exception_id_index", "exception_reason_index", "exception_approver_index"]
            },
            "ApprovalChain": {
                "properties": [
                    "approval_id", "decision_id", "approver", "approval_method",
                    "approval_context", "timestamp", "metadata"
                ],
                "constraints": ["approval_id_unique"],
                "indexes": ["approval_id_index", "approval_method_index", "approval_approver_index"]
            },
            "DecisionContext": {
                "properties": [
                    "context_id", "decision_id", "entity_snapshots", "risk_factors",
                    "cross_system_inputs", "metadata"
                ],
                "constraints": ["context_id_unique"],
                "indexes": ["context_id_index", "context_decision_id_index"]
            },
            "Precedent": {
                "properties": [
                    "precedent_id", "source_decision_id", "similarity_score",
                    "relationship_type", "metadata"
                ],
                "constraints": ["precedent_id_unique"],
                "indexes": ["precedent_id_index", "precedent_source_index", "precedent_similarity_index"]
            },
            "CrossSystemContext": {
                "properties": [
                    "context_id", "system_name", "context_data", "created_at"
                ],
                "indexes": ["cross_system_name_index", "cross_system_created_at_index"]
            },
            "DecisionTraceEvent": {
                "properties": [
                    "trace_id", "decision_id", "event_index", "event_type",
                    "event_timestamp", "event_payload", "previous_hash", "event_hash"
                ],
                "constraints": ["decision_trace_id_unique"],
                "indexes": [
                    "decision_trace_id_index",
                    "decision_trace_event_index",
                    "decision_trace_type_index",
                    "decision_trace_timestamp_index"
                ]
            }
        },
        "relationship_types": {
            "Core decision relationships": [
                "CAUSED", "INFLUENCED", "PRECEDENT_FOR", "ABOUT", "APPLIED_POLICY", "TRIGGERED"
            ],
            "Exception and approval relationships": [
                "GRANTED_EXCEPTION", "OVERRIDDEN_POLICY", "APPROVED_BY", "APPROVAL_METHOD"
            ],
            "Cross-system relationships": [
                "CONTEXT_FROM", "SYNTHESIZED_WITH", "CROSS_SYSTEM_INPUT"
            ],
            "Multi-hop reasoning relationships": [
                "SIMILAR_TO", "RELATED_TO", "DEPENDS_ON", "PART_OF", "WORKED_ON", "RESOLVED_WITH"
            ],
            "Policy and governance relationships": [
                "GOVERNS", "COMPLIES_WITH", "VIOLATES", "VERSION_OF"
            ],
            "Provenance relationships": [
                "DERIVED_FROM", "INFLUENCED_BY", "BASED_ON"
            ],
            "Decision trace relationships": [
                "HAS_TRACE_EVENT", "NEXT_TRACE_EVENT"
            ],
            "Entity and context relationships": [
                "REPORTED_BY", "RELATES_TO", "ESCALATED_TO", "SIMILAR_TO"
            ],
            "Temporal and sequence relationships": [
                "BEFORE", "AFTER", "DURING", "FOLLOWED_BY"
            ]
        },
        "indexes": [
            "decision_id_index", "decision_category_index", "decision_timestamp_index",
            "policy_id_index", "policy_category_index", "policy_version_index",
            "exception_id_index", "exception_reason_index", "exception_approver_index",
            "approval_id_index", "approval_method_index", "approval_approver_index",
            "context_id_index", "context_decision_id_index",
            "precedent_id_index", "precedent_source_index", "precedent_similarity_index",
            "decision_trace_id_index", "decision_trace_event_index", "decision_trace_type_index", "decision_trace_timestamp_index",
            "cross_system_name_index", "cross_system_created_at_index",
            "entity_type_index", "entity_id_index", "relationship_strength_index",
            "temporal_before_index", "temporal_after_index", "temporal_during_index"
        ],
        "constraints": [
            "decision_id_unique", "policy_identity_unique", "exception_id_unique",
            "approval_id_unique", "context_id_unique", "precedent_id_unique",
            "decision_trace_id_unique"
        ]
    }


def create_sample_data(graph_store: GraphStore) -> None:
    """
    Create sample decision tracking data for testing.
    
    Args:
        graph_store: Graph database instance
    """
    logger = get_logger(__name__)
    
    try:
        # Sample decision
        decision_query = """
        CREATE (d:Decision {
            decision_id: 'sample_decision_001',
            category: 'credit_approval',
            scenario: 'Credit limit increase request for high-value customer',
            reasoning: 'Customer has excellent payment history and low credit utilization',
            outcome: 'approved',
            confidence: 0.85,
            timestamp: datetime(),
            decision_maker: 'ai_agent_001',
            metadata: {risk_level: 'low', customer_tier: 'premium'}
        })
        """
        graph_store.execute_query(decision_query)
        
        # Sample policy
        policy_query = """
        CREATE (p:Policy {
            policy_id: 'credit_policy_001',
            name: 'Credit Approval Policy',
            description: 'Standard credit approval rules and guidelines',
            rules: {min_score: 650, max_debt_ratio: 0.4, max_credit_limit: 50000},
            category: 'credit_approval',
            version: '1.0',
            created_at: datetime(),
            updated_at: datetime(),
            metadata: {department: 'risk_management', effective_date: '2024-01-01'}
        })
        """
        graph_store.execute_query(policy_query)
        
        # Link decision to policy
        link_query = """
        MATCH (d:Decision {decision_id: 'sample_decision_001'})
        MATCH (p:Policy {policy_id: 'credit_policy_001'})
        MERGE (d)-[:APPLIED_POLICY]->(p)
        """
        graph_store.execute_query(link_query)
        
        logger.info("Sample decision tracking data created")
        
    except Exception as e:
        logger.error(f"Failed to create sample data: {e}")
        raise


def drop_decision_schema(graph_store: GraphStore) -> None:
    """
    Drop decision tracking schema (for cleanup/testing).
    
    .. deprecated::
        ``drop_decision_schema()`` is deprecated and will be removed in a future
        major version. It has no callers inside Semantica; issue the DROP
        CONSTRAINT / DROP INDEX / DETACH DELETE statements directly against your
        :class:`~semantica.graph_store.GraphStore` instead.

    Args:
        graph_store: Graph database instance
    """
    logger = get_logger(__name__)
    
    warnings.warn(
        "drop_decision_schema() is deprecated and will be removed in a future "
        "major version. Issue the DROP CONSTRAINT / DROP INDEX / DETACH DELETE "
        "statements directly against your GraphStore instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    
    try:
        # Drop constraints
        constraints = [
            "DROP CONSTRAINT decision_id_unique IF EXISTS",
            "DROP CONSTRAINT policy_identity_unique IF EXISTS",
            "DROP CONSTRAINT policy_id_unique IF EXISTS",
            "DROP CONSTRAINT exception_id_unique IF EXISTS",
            "DROP CONSTRAINT approval_id_unique IF EXISTS",
            "DROP CONSTRAINT context_id_unique IF EXISTS",
            "DROP CONSTRAINT precedent_id_unique IF EXISTS",
            "DROP CONSTRAINT decision_trace_id_unique IF EXISTS",
        ]
        
        for constraint in constraints:
            try:
                graph_store.execute_query(constraint)
            except Exception as e:
                logger.debug(f"Constraint drop failed (may not exist): {e}")
        
        # Drop indexes
        indexes = [
            "DROP INDEX decision_id_index IF EXISTS",
            "DROP INDEX decision_category_index IF EXISTS",
            "DROP INDEX decision_timestamp_index IF EXISTS",
            "DROP INDEX policy_id_index IF EXISTS",
            "DROP INDEX policy_category_index IF EXISTS",
            "DROP INDEX policy_version_index IF EXISTS",
            "DROP INDEX exception_id_index IF EXISTS",
            "DROP INDEX exception_reason_index IF EXISTS",
            "DROP INDEX approval_id_index IF EXISTS",
            "DROP INDEX approval_method_index IF EXISTS",
            "DROP INDEX context_id_index IF EXISTS",
            "DROP INDEX precedent_id_index IF EXISTS",
            "DROP INDEX decision_trace_id_index IF EXISTS",
            "DROP INDEX decision_trace_event_index IF EXISTS",
            "DROP INDEX decision_trace_type_index IF EXISTS",
            "DROP INDEX decision_trace_timestamp_index IF EXISTS"
        ]
        
        for index in indexes:
            try:
                graph_store.execute_query(index)
            except Exception as e:
                logger.debug(f"Index drop failed (may not exist): {e}")
        
        # Drop nodes and relationships
        cleanup_query = """
        MATCH (n) WHERE n:Decision OR n:Policy OR n:Exception OR n:ApprovalChain 
                     OR n:DecisionContext OR n:Precedent OR n:CrossSystemContext
                     OR n:DecisionTraceEvent
        DETACH DELETE n
        """
        graph_store.execute_query(cleanup_query)
        
        logger.info("Decision tracking schema dropped")
        
    except Exception as e:
        logger.error(f"Failed to drop decision schema: {e}")
        raise
