"""
Decision Recorder Module

This module provides the DecisionRecorder class for recording decisions
with full context, policy applications, exceptions, and provenance tracking.

Core Features:
    - Decision recording with full context and metadata
    - Policy application and compliance checking
    - Exception handling and approval chains
    - Provenance tracking and audit trails
    - Cross-system context integration

Decision Recording Features:
    - Complete Decision Lifecycle: Record from creation to completion
    - Context Capture: Capture full decision context and relationships
    - Metadata Storage: Store decision metadata and embeddings
    - Policy Integration: Apply and enforce decision policies
    - Exception Management: Handle decision exceptions and appeals

Policy and Compliance:
    - Policy Application: Apply relevant policies to decisions
    - Compliance Checking: Verify decision compliance with rules
    - Approval Chains: Manage multi-level approval processes
    - Exception Handling: Handle policy exceptions and waivers
    - Audit Trail: Maintain complete audit trails

Provenance and Tracking:
    - Source Tracking: Track decision sources and origins
    - Lineage Management: Maintain decision lineage and history
    - Change Tracking: Track decision changes and modifications
    - Attribution: Record decision makers and contributors
    - Timestamp Management: Maintain accurate temporal records

Advanced Features:
    - Embedding Generation: Generate decision embeddings for similarity
    - Cross-System Context: Integrate with external systems
    - Relationship Mapping: Map decision relationships
    - Impact Assessment: Assess decision impact scope
    - Analytics Integration: Support decision analytics

Recording Methods:
    - record_decision(): Record decisions with full context
    - apply_policy(): Apply policies to decisions
    - handle_exception(): Handle decision exceptions
    - create_approval_chain(): Create approval workflows
    - track_provenance(): Track decision provenance
    - update_decision(): Update existing decisions

Example Usage:
    >>> from semantica.context import DecisionRecorder
    >>> recorder = DecisionRecorder(graph_store=kg, vector_store=vs)
    >>> decision_id = recorder.record_decision(
    ...     category="loan_approval",
    ...     scenario="Mortgage application",
    ...     reasoning="Good credit score",
    ...     outcome="approved",
    ...     confidence=0.95,
    ...     decision_maker="loan_officer",
    ...     entities=["customer_123", "property_456"]
    ... )
    >>> recorder.apply_policy(decision_id, policy_id="lending_policy_001")
    >>> approval_chain = recorder.create_approval_chain(decision_id, approvers=["manager", "director"])

Production Use Cases:
    - Banking: Loan approvals, credit decisions, risk assessments
    - Healthcare: Treatment approvals, diagnostic decisions
    - Legal: Legal decisions, case management
    - Government: Policy decisions, regulatory compliance
    - Insurance: Claim decisions, underwriting processes
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import uuid

from ..embeddings import EmbeddingGenerator
from ..graph_store import GraphStore
from ..provenance import ProvenanceManager
from ..utils.logging import get_logger
from .decision_models import (
    Decision, DecisionContext, Policy, PolicyException, 
    Precedent, ApprovalChain
)
from .context_graph import ContextGraph


class DecisionRecorder:
    """
    Records decisions with full context, policy applications, and provenance.
    
    This class handles the recording of decisions, linking them to entities,
    applying policies, recording exceptions, and tracking provenance.
    """
    
    def __init__(
        self,
        graph_store: GraphStore,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        provenance_manager: Optional[ProvenanceManager] = None,
        evaluators: Optional[List[str]] = None,
        eval_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize DecisionRecorder.

        Args:
            graph_store: Graph database instance for storing decisions
            embedding_generator: Optional embedding generator for semantic embeddings
            provenance_manager: Optional provenance manager for W3C PROV-O tracking
            evaluators: Optional list of semantica.evals evaluator names to run
                automatically on every recorded decision (e.g. ["decision_scores"]).
                When omitted, record_decision() behaves exactly as before.
            eval_config: Optional config dict passed to semantica.evals.evaluate(),
                keyed by evaluator name
                (e.g. {"decision_scores": {"policy_engine": pe}})

        Example Usage:
            >>> recorder = DecisionRecorder(
            ...     graph_store=graph,
            ...     evaluators=["decision_scores"],
            ...     eval_config={"decision_scores": {"expected_outcome": "approved"}},
            ... )
            >>> recorder.record_decision(decision, entities=[], source_documents=[])
            >>> decision.metadata["eval_score"], decision.metadata["eval_passed"]
        """
        self.graph_store = graph_store
        self.embedding_generator = embedding_generator
        self.provenance_manager = provenance_manager
        self.evaluators = evaluators
        self.eval_config = eval_config or {}
        self.logger = get_logger(__name__)

    def _evaluate_and_enrich_decision(self, decision: Decision) -> None:
        """
        Run configured semantica.evals evaluators over a decision and store the
        result in its metadata. No-op when no evaluators are configured.

        Args:
            decision: Decision to evaluate; mutated in place (decision.metadata).
        """
        if not self.evaluators:
            return

        # Decision.metadata defaults to {} but callers may pass metadata=None
        # explicitly; normalize before writing eval_* keys below so recording
        # never crashes on that (mirrors record_decision()'s own tolerance
        # for a missing metadata dict).
        if decision.metadata is None:
            decision.metadata = {}

        case = {"id": decision.decision_id, "actual": decision}
        try:
            # Lazy import: semantica.evals is only exercised when evaluators=
            # is configured, and resolving it here (rather than at module
            # import time) lets callers/tests monkeypatch semantica.evals.evaluate.
            from ..evals import evaluate

            summary = evaluate(
                [case], evaluators=self.evaluators, config=self.eval_config
            )
        except Exception as exc:
            # Deliberate, narrow exception to this module's "log and re-raise"
            # pattern: evaluation is an optional quality check, and a broken
            # evaluator must never prevent the decision itself from being
            # recorded. (Per-evaluator failures are already converted to
            # CaseResult(status="error") inside evaluate(); reaching here
            # means evaluate() itself failed outright.)
            self.logger.warning(
                f"Decision evaluation failed for {decision.decision_id}: {exc}"
            )
            return

        case_result = summary.cases[0]
        scores = [metric.score for metric in case_result.metrics.values()]
        decision.metadata["eval_score"] = sum(scores) / len(scores) if scores else 0.0
        decision.metadata["eval_passed"] = case_result.status == "pass"
        decision.metadata["eval_details"] = {
            name: {"score": metric.score, "passed": metric.passed, "meta": metric.meta}
            for name, metric in case_result.metrics.items()
        }

    def record_decision(
        self,
        decision: Decision,
        entities: List[str],
        source_documents: List[str]
    ) -> str:
        """
        Record decision with full context.

        Args:
            decision: Decision object to record
            entities: List of entity IDs linked to this decision
            source_documents: List of source document identifiers

        Returns:
            Decision ID
        """
        try:
            # Generate embeddings if available
            if self.embedding_generator and not decision.reasoning_embedding:
                decision.reasoning_embedding = self.embedding_generator.generate(
                    decision.reasoning
                )

            # Run configured evaluators (opt-in) before persisting, so
            # eval_score/eval_passed/eval_details are stored with the decision.
            if self.evaluators:
                self._evaluate_and_enrich_decision(decision)

            # Store decision in graph database
            self._store_decision_node(decision)
            
            # Link to entities
            self.link_entities(decision.decision_id, entities)
            
            # Track provenance
            if self.provenance_manager:
                self._track_decision_provenance(decision, source_documents)
            
            self.logger.info(f"Recorded decision: {decision.decision_id} | Actor: {decision.decision_maker} | Timestamp: {decision.timestamp} | Outcome: {decision.outcome} | Category: {decision.category}")
            return decision.decision_id
            
        except Exception as e:
            self.logger.exception("Failed to record decision")
            raise
    
    def link_entities(self, decision_id: str, entities: List[str]) -> None:
        """
        Link decision to entities.
        
        Args:
            decision_id: Decision ID
            entities: List of entity IDs to link
        """
        try:
            if type(self.graph_store) is ContextGraph:
                for entity_id in entities:
                    self.graph_store.add_node(node_id=entity_id, node_type="Entity")
                    self.graph_store.add_edge(source_id=decision_id, target_id=entity_id, edge_type="ABOUT")
                self.logger.info(f"Linked decision {decision_id} to {len(entities)} entities")
                return

            for entity_id in entities:
                # Create ABOUT relationship between decision and entity
                query = """
                MATCH (d:Decision {decision_id: $decision_id})
                MATCH (e) WHERE e.id = $entity_id OR e.entity_id = $entity_id
                MERGE (d)-[:ABOUT]->(e)
                """
                self.graph_store.execute_query(query, {
                    "decision_id": decision_id,
                    "entity_id": entity_id
                })
            
            self.logger.info(f"Linked decision {decision_id} to {len(entities)} entities")
            
        except Exception as e:
            self.logger.exception("Failed to link entities")
            raise
    
    def apply_policies(
        self,
        decision_id: str,
        policy_ids: List[Union[str, Dict[str, str]]],
    ) -> List[Dict[str, str]]:
        """
        Track policy applications for a decision.
        
        Args:
            decision_id: Decision ID
            policy_ids: List of policy IDs or policy refs with explicit version

        Returns:
            Applied policy references with resolved versions
        """
        try:
            applied: List[Dict[str, str]] = []

            for policy_ref in policy_ids:
                if isinstance(policy_ref, dict):
                    policy_id = str(policy_ref.get("policy_id", ""))
                    policy_version = (
                        str(policy_ref.get("version"))
                        if policy_ref.get("version") is not None
                        else None
                    )
                else:
                    policy_id = str(policy_ref)
                    policy_version = None

                if not policy_id:
                    continue

                # Resolve exactly one policy node:
                # - explicit version when provided
                # - latest available version for legacy callers
                query = """
                MATCH (d:Decision {decision_id: $decision_id})
                MATCH (p:Policy {policy_id: $policy_id})
                WHERE $policy_version IS NULL OR p.version = $policy_version
                WITH d, p
                ORDER BY p.updated_at DESC, p.version DESC
                LIMIT 1
                MERGE (d)-[r:APPLIED_POLICY]->(p)
                SET r.policy_id = $policy_id,
                    r.policy_version = p.version,
                    d.applied_at = timestamp()
                RETURN p.policy_id as policy_id, p.version as version
                """
                result = self.graph_store.execute_query(query, {
                    "decision_id": decision_id,
                    "policy_id": policy_id,
                    "policy_version": policy_version,
                })

                records = (
                    result.get("records", [])
                    if isinstance(result, dict)
                    else (result if isinstance(result, list) else [])
                )
                if records:
                    record = records[0]
                    applied.append(
                        {
                            "policy_id": str(record.get("policy_id", policy_id)),
                            "version": str(record.get("version", policy_version or "")),
                        }
                    )
                else:
                    self.logger.warning(
                        f"No policy match found for {policy_id}"
                        + (f" version {policy_version}" if policy_version else "")
                    )
            
            self.logger.info(f"Applied {len(applied)} policies to decision {decision_id}")
            return applied
            
        except Exception as e:
            self.logger.exception("Failed to apply policies")
            raise
    
    def record_exception(
        self,
        decision_id: str,
        policy_id: str,
        reason: str,
        approver: str,
        approval_method: str,
        justification: str
    ) -> str:
        """
        Record policy exception with approval chain.
        
        Args:
            decision_id: Decision ID
            policy_id: Policy ID that was excepted
            reason: Reason for exception
            approver: Person who approved exception
            approval_method: Method of approval (slack_dm, zoom_call, email, system)
            justification: Justification for the exception
            
        Returns:
            Exception ID
        """
        try:
            exception = PolicyException(
                exception_id=str(uuid.uuid4()),
                decision_id=decision_id,
                policy_id=policy_id,
                reason=reason,
                approver=approver,
                approval_timestamp=datetime.now(),
                justification=justification
            )
            
            # Store exception in graph
            self._store_exception_node(exception)
            
            if type(self.graph_store) is ContextGraph:
                self.graph_store.add_node(node_id=policy_id, node_type="Policy")
                self.graph_store.add_edge(source_id=decision_id, target_id=exception.exception_id, edge_type="GRANTED_EXCEPTION")
                self.graph_store.add_edge(source_id=exception.exception_id, target_id=policy_id, edge_type="OVERRIDDEN_POLICY")
                self.logger.info(f"Recorded exception: {exception.exception_id}")
                return exception.exception_id

            # Create relationships
            query = """
            MATCH (d:Decision {decision_id: $decision_id})
            MATCH (p:Policy {policy_id: $policy_id})
            MATCH (e:Exception {exception_id: $exception_id})
            MERGE (d)-[:GRANTED_EXCEPTION]->(e)
            MERGE (e)-[:OVERRIDDEN_POLICY]->(p)
            """
            self.graph_store.execute_query(query, {
                "decision_id": decision_id,
                "policy_id": policy_id,
                "exception_id": exception.exception_id
            })
            
            self.logger.info(f"Recorded exception: {exception.exception_id}")
            return exception.exception_id
            
        except Exception as e:
            self.logger.exception("Failed to record exception")
            raise
    
    def capture_cross_system_context(
        self,
        decision_id: str,
        system_inputs: Dict[str, Any]
    ) -> None:
        """
        Capture cross-system context synthesis.
        
        Args:
            decision_id: Decision ID
            system_inputs: Dictionary of system inputs and their contexts
        """
        try:
            for system_name, context_data in system_inputs.items():
                # Create cross-system context node
                context_id = str(uuid.uuid4())
                query = """
                CREATE (c:CrossSystemContext {
                    context_id: $context_id,
                    system_name: $system_name,
                    context_data: $context_data,
                    created_at: datetime()
                })
                WITH c
                MATCH (d:Decision {decision_id: $decision_id})
                MERGE (d)-[:CONTEXT_FROM]->(c)
                """
                self.graph_store.execute_query(query, {
                    "context_id": context_id,
                    "system_name": system_name,
                    "context_data": context_data,
                    "decision_id": decision_id
                })
            
            self.logger.info(f"Captured cross-system context for decision {decision_id}")
            
        except Exception as e:
            self.logger.exception("Failed to capture cross-system context")
            raise
    
    def record_approval_chain(
        self,
        decision_id: str,
        approvers: List[str],
        methods: List[str],
        contexts: List[str]
    ) -> None:
        """
        Record approval chains that happen outside systems.
        
        Args:
            decision_id: Decision ID
            approvers: List of approver names
            methods: List of approval methods
            contexts: List of approval contexts
        """
        try:
            if len(approvers) != len(methods) or len(approvers) != len(contexts):
                raise ValueError("Approvers, methods, and contexts must have same length")
            
            for i, (approver, method, context) in enumerate(zip(approvers, methods, contexts)):
                approval = ApprovalChain(
                    approval_id=str(uuid.uuid4()),
                    decision_id=decision_id,
                    approver=approver,
                    approval_method=method,
                    approval_context=context,
                    timestamp=datetime.now()
                )
                
                # Store approval node
                self._store_approval_node(approval)
                
                # Create relationship
                query = """
                MATCH (d:Decision {decision_id: $decision_id})
                MATCH (a:ApprovalChain {approval_id: $approval_id})
                MERGE (d)-[:APPROVED_BY]->(a)
                """
                self.graph_store.execute_query(query, {
                    "decision_id": decision_id,
                    "approval_id": approval.approval_id
                })
            
            self.logger.info(f"Recorded approval chain with {len(approvers)} approvers")
            
        except Exception as e:
            self.logger.exception("Failed to record approval chain")
            raise
    
    def link_precedents(
        self,
        decision_id: str,
        precedent_ids: List[str],
        relationship_types: List[str]
    ) -> None:
        """
        Link decision to precedents.
        
        Args:
            decision_id: Decision ID
            precedent_ids: List of precedent decision IDs
            relationship_types: List of relationship types
        """
        try:
            if len(precedent_ids) != len(relationship_types):
                raise ValueError("Precedent IDs and relationship types must have same length")
            
            if type(self.graph_store) is ContextGraph:
                for precedent_id, relationship_type in zip(precedent_ids, relationship_types):
                    self.graph_store.add_edge(source_id=decision_id, target_id=precedent_id, edge_type=relationship_type)
                self.logger.info(f"Linked {len(precedent_ids)} precedents to decision {decision_id}")
                return

            for precedent_id, relationship_type in zip(precedent_ids, relationship_types):
                # Create precedent relationship
                query = """
                MATCH (d:Decision {decision_id: $decision_id})
                MATCH (p:Decision {decision_id: $precedent_id})
                MERGE (d)-[:PRECEDENT_FOR {type: $relationship_type}]->(p)
                """
                self.graph_store.execute_query(query, {
                    "decision_id": decision_id,
                    "precedent_id": precedent_id,
                    "relationship_type": relationship_type
                })
            
            self.logger.info(f"Linked {len(precedent_ids)} precedents to decision {decision_id}")
            
        except Exception as e:
            self.logger.exception("Failed to link precedents")
            raise
    
    def _store_decision_node(self, decision: Decision) -> None:
        """Store decision node in graph database."""
        metadata = decision.metadata.copy() if decision.metadata else {}
        metadata.update({
            "category": decision.category,
            "scenario": decision.scenario,
            "reasoning": decision.reasoning,
            "outcome": decision.outcome,
            "confidence": decision.confidence,
            "timestamp": decision.timestamp.isoformat() if decision.timestamp else None,
            "decision_maker": decision.decision_maker,
            "reasoning_embedding": decision.reasoning_embedding,
            "node2vec_embedding": decision.node2vec_embedding
        })
        
        if type(self.graph_store) is ContextGraph:
            self.graph_store.add_node(
                node_id=decision.decision_id,
                node_type="Decision",
                **metadata
            )
            return

        query = """
        CREATE (d:Decision {
            decision_id: $decision_id,
            category: $category,
            scenario: $scenario,
            reasoning: $reasoning,
            outcome: $outcome,
            confidence: $confidence,
            timestamp: $timestamp,
            decision_maker: $decision_maker,
            reasoning_embedding: $reasoning_embedding,
            node2vec_embedding: $node2vec_embedding,
            metadata: $metadata
        })
        """
        self.graph_store.execute_query(query, {
            "decision_id": decision.decision_id,
            "category": decision.category,
            "scenario": decision.scenario,
            "reasoning": decision.reasoning,
            "outcome": decision.outcome,
            "confidence": decision.confidence,
            "timestamp": decision.timestamp,
            "decision_maker": decision.decision_maker,
            "reasoning_embedding": decision.reasoning_embedding,
            "node2vec_embedding": decision.node2vec_embedding,
            "metadata": decision.metadata
        })
    
    def _store_exception_node(self, exception: PolicyException) -> None:
        """Store exception node in graph database."""
        metadata = exception.metadata.copy() if exception.metadata else {}
        metadata.update({
            "decision_id": exception.decision_id,
            "policy_id": exception.policy_id,
            "reason": exception.reason,
            "approver": exception.approver,
            "approval_timestamp": exception.approval_timestamp.isoformat() if exception.approval_timestamp else None,
            "justification": exception.justification
        })
        
        if type(self.graph_store) is ContextGraph:
            self.graph_store.add_node(
                node_id=exception.exception_id,
                node_type="Exception",
                **metadata
            )
            return

        query = """
        CREATE (e:Exception {
            exception_id: $exception_id,
            decision_id: $decision_id,
            policy_id: $policy_id,
            reason: $reason,
            approver: $approver,
            approval_timestamp: $approval_timestamp,
            justification: $justification,
            metadata: $metadata
        })
        """
        self.graph_store.execute_query(query, {
            "exception_id": exception.exception_id,
            "decision_id": exception.decision_id,
            "policy_id": exception.policy_id,
            "reason": exception.reason,
            "approver": exception.approver,
            "approval_timestamp": exception.approval_timestamp,
            "justification": exception.justification,
            "metadata": exception.metadata
        })
    
    def _store_approval_node(self, approval: ApprovalChain) -> None:
        """Store approval node in graph database."""
        query = """
        CREATE (a:ApprovalChain {
            approval_id: $approval_id,
            decision_id: $decision_id,
            approver: $approver,
            approval_method: $approval_method,
            approval_context: $approval_context,
            timestamp: $timestamp,
            metadata: $metadata
        })
        """
        self.graph_store.execute_query(query, {
            "approval_id": approval.approval_id,
            "decision_id": approval.decision_id,
            "approver": approval.approver,
            "approval_method": approval.approval_method,
            "approval_context": approval.approval_context,
            "timestamp": approval.timestamp,
            "metadata": approval.metadata
        })
    
    def _track_decision_provenance(
        self,
        decision: Decision,
        source_documents: List[str]
    ) -> None:
        """Track decision provenance using ProvenanceManager."""
        if not self.provenance_manager:
            return
        
        try:
            # Track decision as entity
            self.provenance_manager.track_entity(
                entity_id=decision.decision_id,
                entity_type="decision",
                activity_id="decision_making_process",
                agent_id=decision.decision_maker,
                source_documents=source_documents,
                confidence=decision.confidence
            )
            
            # Track decision-making activity
            self.provenance_manager.track_activity(
                activity_id=f"decision_{decision.decision_id}",
                activity_type="decision_making",
                agent_id=decision.decision_maker,
                used_entities=[decision.decision_id],
                started_at=decision.timestamp,
                ended_at=decision.timestamp
            )
            
        except Exception as e:
            self.logger.exception("Failed to track provenance")
