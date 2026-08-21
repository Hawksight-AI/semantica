"""
Policy Engine Module

This module provides the PolicyEngine class for policy management,
versioning, compliance checking, and impact analysis.

Core Features:
    - Policy management with versioning and change tracking
    - Compliance checking and violation detection
    - Policy impact analysis and assessment
    - Rule-based decision validation
    - Policy exception handling and management

Policy Management Features:
    - Policy Creation: Create and manage decision policies
    - Version Control: Track policy versions and changes
    - Rule Definition: Define policy rules and constraints
    - Policy Hierarchy: Manage policy relationships and dependencies
    - Lifecycle Management: Policy activation, deactivation, and retirement

Compliance and Validation:
    - Compliance Checking: Verify decision compliance with policies
    - Violation Detection: Identify policy violations and exceptions
    - Rule Evaluation: Evaluate complex policy rules
    - Constraint Validation: Validate decision constraints
    - Audit Reporting: Generate compliance audit reports

Advanced Analytics:
    - Impact Analysis: Analyze policy impact on decisions
    - Coverage Analysis: Assess policy coverage and gaps
    - Performance Metrics: Track policy performance metrics
    - Trend Analysis: Analyze policy compliance trends
    - Risk Assessment: Assess policy-related risks

Policy Engine Methods:
    - create_policy(): Create new policies with rules
    - update_policy(): Update existing policies
    - check_compliance(): Check decision compliance
    - analyze_impact(): Analyze policy impact
    - get_violations(): Get policy violations
    - audit_decisions(): Audit decisions against policies

Rule Engine Features:
    - Complex Rules: Support complex rule definitions
    - Conditional Logic: Handle conditional rule logic
    - Rule Chaining: Chain multiple rules together
    - Exception Handling: Handle rule exceptions
    - Performance Optimization: Optimized rule evaluation

Example Usage:
    >>> from semantica.context import PolicyEngine
    >>> engine = PolicyEngine(graph_store=kg)
    >>> policy_id = engine.create_policy(
    ...     name="Lending Policy",
    ...     rules={"max_loan_amount": 500000, "min_credit_score": 650},
    ...     category="lending"
    ... )
    >>> compliance = engine.check_compliance(decision_id, policy_id)
    >>> violations = engine.get_violations(decision_id)
    >>> impact = engine.analyze_impact(policy_id, time_range="30d")

Production Use Cases:
    - Banking: Lending policies, risk management policies
    - Healthcare: Treatment protocols, clinical guidelines
    - Legal: Compliance policies, regulatory requirements
    - Government: Policy enforcement, regulatory compliance
    - Insurance: Underwriting policies, claim processing rules
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import uuid

from ..graph_store import GraphStore
from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from .decision_models import Decision, Policy, PolicyException


class PolicyEngine:
    """
    Policy engine with versioning and change tracking.
    
    This class manages policies, tracks versions, checks compliance,
    records exceptions, and analyzes policy impact.
    """
    
    def __init__(self, graph_store: Any):
        """
        Initialize PolicyEngine.
        
        Args:
            graph_store: Graph database instance for storing policies
        """
        self.graph_store = graph_store
        self.logger = get_logger(__name__)
        self._supports_cypher = hasattr(graph_store, "execute_query")
    
    def add_policy(self, policy: Policy) -> str:
        """
        Store policy with versioning.
        
        Args:
            policy: Policy object to store
            
        Returns:
            Policy ID
        """
        try:
            if self._supports_cypher:
                # Check for duplicate policy ID
                if policy.policy_id:
                    check_query = "MATCH (p:Policy {policy_id: $policy_id}) RETURN p.policy_id LIMIT 1"
                    existing = self.graph_store.execute_query(check_query, {"policy_id": policy.policy_id})
                    if existing:
                        raise ValueError("Policy with this ID already exists")
                query = """
                CREATE (p:Policy {
                    policy_id: $policy_id,
                    name: $name,
                    description: $description,
                    rules: $rules,
                    category: $category,
                    version: $version,
                    created_at: $created_at,
                    updated_at: $updated_at,
                    metadata: $metadata
                })
                """
                self.graph_store.execute_query(query, {
                    "policy_id": policy.policy_id,
                    "name": policy.name,
                    "description": policy.description,
                    "rules": policy.rules,
                    "category": policy.category,
                    "version": policy.version,
                    "created_at": policy.created_at,
                    "updated_at": policy.updated_at,
                    "metadata": policy.metadata
                })
                self.logger.info(f"Added policy: {policy.policy_id} version {policy.version}")
                return policy.policy_id

            if not hasattr(self.graph_store, "add_node"):
                raise RuntimeError("Graph backend does not support policy storage")

            node_id = f"{policy.policy_id}:{policy.version}"
            self.graph_store.add_node(
                node_id=node_id,
                node_type="Policy",
                content=policy.name or policy.policy_id,
                policy_id=policy.policy_id,
                name=policy.name,
                description=policy.description,
                rules=policy.rules,
                category=policy.category,
                version=policy.version,
                created_at=policy.created_at.isoformat() if hasattr(policy.created_at, "isoformat") else str(policy.created_at),
                updated_at=policy.updated_at.isoformat() if hasattr(policy.updated_at, "isoformat") else str(policy.updated_at),
                metadata=policy.metadata or {}
            )
            self.logger.info(f"Added policy: {policy.policy_id} version {policy.version}")
            return policy.policy_id
        except Exception as e:
            self.logger.exception("Failed to add policy")
            raise
    
    def update_policy(
        self,
        policy_id: str,
        rules: Dict[str, Any],
        change_reason: str,
        new_version: Optional[str] = None
    ) -> str:
        """
        Update policy and create new version.
        
        Args:
            policy_id: Policy ID to update
            rules: New policy rules
            change_reason: Reason for the change
            new_version: Optional new version (auto-generated if not provided)
            
        Returns:
            New version string
        """
        try:
            # Get current policy
            current_policy = self.get_policy(policy_id)
            if not current_policy:
                raise ValueError(f"Policy {policy_id} not found")
            
            # Generate new version if not provided
            if not new_version:
                new_version = self._generate_next_version(current_policy.version)
            
            # Create new policy version
            updated_policy = Policy(
                policy_id=policy_id,
                name=current_policy.name,
                description=current_policy.description,
                rules=rules,
                category=current_policy.category,
                version=new_version,
                created_at=current_policy.created_at,
                updated_at=datetime.now(),
                metadata={
                    **current_policy.metadata,
                    "change_reason": change_reason,
                    "previous_version": current_policy.version
                }
            )
            
            # Store new version
            self.add_policy(updated_policy)
            
            if self._supports_cypher:
                query = """
                MATCH (old:Policy {policy_id: $policy_id, version: $old_version})
                MATCH (new:Policy {policy_id: $policy_id, version: $new_version})
                MERGE (old)-[:VERSION_OF]->(new)
                """
                self.graph_store.execute_query(query, {
                    "policy_id": policy_id,
                    "old_version": current_policy.version,
                    "new_version": new_version
                })
            else:
                if hasattr(self.graph_store, "add_edge"):
                    self.graph_store.add_edge(
                        f"{policy_id}:{current_policy.version}",
                        f"{policy_id}:{new_version}",
                        edge_type="VERSION_OF",
                        changed_at=datetime.now().isoformat(),
                        change_reason=change_reason
                    )
            
            self.logger.info(f"Updated policy {policy_id} to version {new_version}")
            return policy_id
            
        except Exception as e:
            self.logger.exception("Failed to update policy")
            raise
    
    def get_applicable_policies(
        self,
        category: str,
        entities: Optional[List[str]] = None
    ) -> List[Policy]:
        """
        Get policies for category/entities.
        
        Args:
            category: Policy category
            entities: Optional list of entity IDs for entity-specific policies
            
        Returns:
            List of applicable policies (latest versions)
        """
        try:
            if self._supports_cypher:
            # Get latest policies for category
                query = """
                MATCH (p:Policy {category: $category})
                WHERE NOT (p)-[:VERSION_OF]->(:Policy)
                RETURN p
                ORDER BY p.updated_at DESC
                """
                results = self.graph_store.execute_query(query, {"category": category})
                records = self._extract_records(results)

                policies = []
                for record in records:
                    policy_data = record.get("p") if isinstance(record, dict) else None
                    if not isinstance(policy_data, dict):
                        policy_data = record if isinstance(record, dict) else {}
                    if not isinstance(policy_data, dict) or not policy_data.get("policy_id"):
                        self.logger.debug(
                            "Skipping malformed policy record in get_applicable_policies: "
                            f"{record}"
                        )
                        continue
                    policy = self._dict_to_policy(policy_data)
                    if self._policy_matches_entities(policy, entities):
                        policies.append(policy)

                self.logger.info(f"Found {len(policies)} applicable policies for category {category}")
                return policies

            if not hasattr(self.graph_store, "find_nodes"):
                return []

            latest_by_policy_id: Dict[str, Dict[str, Any]] = {}
            for node in self.graph_store.find_nodes(node_type="Policy"):
                data = node.get("metadata", {}) or {}
                if data.get("category") != category:
                    continue
                pid = data.get("policy_id")
                if not pid:
                    continue
                updated_at = data.get("updated_at") or ""
                prev = latest_by_policy_id.get(pid)
                if not prev:
                    latest_by_policy_id[pid] = data
                else:
                    if str(updated_at) > str(prev.get("updated_at") or ""):
                        latest_by_policy_id[pid] = data

            policies: List[Policy] = []
            for data in latest_by_policy_id.values():
                policy = self._dict_to_policy({
                    "policy_id": data.get("policy_id"),
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "rules": data.get("rules", {}),
                    "category": data.get("category"),
                    "version": data.get("version"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "metadata": data.get("metadata", {})
                })
                if self._policy_matches_entities(policy, entities):
                    policies.append(policy)

            self.logger.info(f"Found {len(policies)} applicable policies for category {category}")
            return policies
            
        except Exception as e:
            self.logger.exception("Failed to get applicable policies")
            raise

    def _extract_records(self, results: Any) -> List[Dict[str, Any]]:
        """Normalize execute_query result shapes to record lists."""
        if isinstance(results, dict):
            records = results.get("records", [])
            if not isinstance(records, list):
                return []

            # FalkorDB shape: {"records": [[...], ...], "header": ["col1", ...]}
            header = results.get("header")
            if (
                isinstance(header, list)
                and records
                and all(isinstance(row, list) for row in records)
            ):
                normalized: List[Dict[str, Any]] = []
                for row in records:
                    row_map: Dict[str, Any] = dict(zip(header, row))
                    normalized.append(row_map)
                return normalized

            return records
        if isinstance(results, list):
            return results
        return []

    def _policy_matches_entities(
        self, policy: Policy, entities: Optional[List[str]]
    ) -> bool:
        """
        Entity scoping for policies.
        If no entity scope is defined on the policy, it is globally applicable.
        """
        if not entities:
            return True

        metadata = policy.metadata or {}
        scoped_entities = (
            metadata.get("entities")
            or metadata.get("entity_ids")
            or metadata.get("applies_to_entities")
            or []
        )
        if not scoped_entities:
            return True

        return bool(set(str(e) for e in scoped_entities).intersection(set(entities)))
    
    def check_compliance(self, decision: Decision, policy_id: str) -> bool:
        """
        Check if decision complies with policy.
        
        Args:
            decision: Decision to check
            policy_id: Policy ID to check against
            
        Returns:
            True if the decision complies with the policy, False otherwise.

        Raises:
            ValueError: If the policy cannot be found.
            ProcessingError: If the compliance check itself fails to execute
                (e.g. malformed rules or metadata). This is deliberately
                distinct from returning ``False``: a returned ``False`` means
                "evaluated and found non-compliant", whereas a raised error
                means "could not determine compliance". Conflating the two
                would let evaluation bugs masquerade as policy violations,
                which is unacceptable in an audit/compliance context.
        """
        try:
            policy = self.get_policy(policy_id)
            if not policy:
                raise ValueError(f"Policy {policy_id} not found")
            return self._evaluate_compliance(decision, policy.rules)
        except ValueError:
            raise
        except Exception as e:
            self.logger.exception("Failed to check compliance")
            raise ProcessingError(
                f"Compliance check failed for policy '{policy_id}': {e}"
            ) from e
    
    def record_policy_application(
        self,
        decision_id: str,
        policy_id: str,
        version: str
    ) -> None:
        """
        Track policy application with version.
        
        Args:
            decision_id: Decision ID
            policy_id: Policy ID
            version: Policy version that was applied
        """
        try:
            if self._supports_cypher:
                query = """
                MATCH (d:Decision {decision_id: $decision_id})
                MATCH (p:Policy {policy_id: $policy_id, version: $version})
                MERGE (d)-[:APPLIED_POLICY]->(p)
                SET d.policy_applied_at = timestamp()
                """
                self.graph_store.execute_query(query, {
                    "decision_id": decision_id,
                    "policy_id": policy_id,
                    "version": version
                })
                self.logger.info(f"Recorded policy application: {policy_id} v{version} to decision {decision_id}")
                return

            if not hasattr(self.graph_store, "add_edge"):
                raise RuntimeError("Graph backend does not support relationships")
            policy_node_id = f"{policy_id}:{version}"
            self.graph_store.add_edge(
                decision_id,
                policy_node_id,
                edge_type="APPLIED_POLICY",
                applied_at=datetime.now().isoformat(),
                policy_id=policy_id,
                version=version
            )
            self.logger.info(f"Recorded policy application: {policy_id} v{version} to decision {decision_id}")
        except Exception as e:
            self.logger.exception("Failed to record policy application")
            raise
    
    def record_exception(
        self,
        decision_id: str,
        policy_id: str,
        reason: str,
        approver: str = "",
        justification: str = ""
    ) -> str:
        """
        Track policy exceptions.

        Args:
            decision_id: Decision ID
            policy_id: Policy ID that was excepted
            reason: Reason for exception
            approver: Approver identifier
            justification: Justification for the exception

        Returns:
            Exception ID
        """
        try:
            exception_id = str(uuid.uuid4())

            if self._supports_cypher:
                query = """
                CREATE (e:Exception {
                    exception_id: $exception_id,
                    decision_id: $decision_id,
                    policy_id: $policy_id,
                    reason: $reason,
                    created_at: datetime()
                })
                """
                self.graph_store.execute_query(query, {
                    "exception_id": exception_id,
                    "decision_id": decision_id,
                    "policy_id": policy_id,
                    "reason": reason
                })

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
                    "exception_id": exception_id
                })

                self.logger.info(f"Recorded policy exception: {exception_id}")
                return exception_id

            if not hasattr(self.graph_store, "add_node") or not hasattr(self.graph_store, "add_edge"):
                raise RuntimeError("Graph backend does not support exceptions")

            self.graph_store.add_node(
                node_id=exception_id,
                node_type="Exception",
                content=reason,
                exception_id=exception_id,
                decision_id=decision_id,
                policy_id=policy_id,
                reason=reason,
                created_at=datetime.now().isoformat()
            )
            self.graph_store.add_edge(decision_id, exception_id, edge_type="GRANTED_EXCEPTION")

            policy = self.get_policy(policy_id)
            if policy:
                self.graph_store.add_edge(exception_id, f"{policy_id}:{policy.version}", edge_type="OVERRIDDEN_POLICY")

            self.logger.info(f"Recorded policy exception: {exception_id}")
            return exception_id
        except Exception as e:
            self.logger.exception("Failed to record exception")
            raise
    
    def get_policy_history(self, policy_id: str) -> List[Policy]:
        """
        Get version history for a policy.
        
        Args:
            policy_id: Policy ID
            
        Returns:
            List of policy versions
        """
        try:
            if self._supports_cypher:
                query = """
                MATCH (p:Policy {policy_id: $policy_id})
                OPTIONAL MATCH (p)-[:VERSION_OF*]->(future:Policy)
                WITH collect(p) + collect(future) as all_versions
                UNWIND all_versions as version
                RETURN DISTINCT version
                ORDER BY version.updated_at
                """
                results = self.graph_store.execute_query(query, {"policy_id": policy_id})
            
                policies = []
                for record in results:
                    version_val = record.get("version") if isinstance(record, dict) else None
                    if isinstance(version_val, dict):
                        policy_data = version_val
                    elif isinstance(record, dict) and "policy_id" in record:
                        policy_data = record  # Flat dict result
                    else:
                        continue
                    policies.append(self._dict_to_policy(policy_data))
            
                self.logger.info(f"Found {len(policies)} versions for policy {policy_id}")
                return policies

            if not hasattr(self.graph_store, "find_nodes"):
                return []
            versions: List[Policy] = []
            for node in self.graph_store.find_nodes(node_type="Policy"):
                data = node.get("metadata", {}) or {}
                if data.get("policy_id") != policy_id:
                    continue
                versions.append(self._dict_to_policy({
                    "policy_id": data.get("policy_id"),
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "rules": data.get("rules", {}),
                    "category": data.get("category"),
                    "version": data.get("version"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "metadata": data.get("metadata", {})
                }))
            versions.sort(key=lambda p: str(p.updated_at))
            return versions
            
        except Exception as e:
            self.logger.exception("Failed to get policy history")
            raise
    
    def get_affected_decisions(
        self,
        policy_id: str,
        from_version: str,
        to_version: str
    ) -> List[Dict[str, Any]]:
        """
        Find decisions affected by policy change.
        
        Args:
            policy_id: Policy ID
            from_version: Previous version
            to_version: New version
            
        Returns:
            List of affected decisions with readable metadata
        """
        try:
            if self._supports_cypher:
                query = """
                MATCH (d:Decision)-[:APPLIED_POLICY]->(p:Policy {
                    policy_id: $policy_id,
                    version: $from_version
                })
                RETURN d.decision_id as decision_id,
                       d.scenario as scenario,
                       d.category as category,
                       d.outcome as outcome,
                       d.confidence as confidence
                """
                results = self._extract_records(self.graph_store.execute_query(query, {
                    "policy_id": policy_id,
                    "from_version": from_version
                }))

                decisions = [
                    self._enrich_affected_decision(
                        record if isinstance(record, dict) else {"decision_id": record}
                    )
                    for record in results
                ]

                self.logger.info(f"Found {len(decisions)} decisions affected by policy change")
                return decisions

            if not hasattr(self.graph_store, "find_edges"):
                return []
            policy_node_id = f"{policy_id}:{from_version}"
            decisions: List[Dict[str, Any]] = []
            for edge in self.graph_store.find_edges(edge_type="APPLIED_POLICY"):
                if edge.get("target") == policy_node_id:
                    decisions.append(
                        self._enrich_affected_decision(
                            {"decision_id": edge.get("source")}
                        )
                    )
            return decisions
            
        except Exception as e:
            self.logger.exception("Failed to get affected decisions")
            raise

    def _enrich_affected_decision(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize an affected decision record with readable fields."""
        decision_id = record.get("decision_id") or record.get("source") or ""
        node_record = self._get_decision_node_record(decision_id)

        enriched = {
            "decision_id": decision_id,
            "scenario": record.get("scenario", node_record.get("scenario", "")),
            "category": record.get("category", node_record.get("category", "")),
            "outcome": record.get("outcome", node_record.get("outcome", "")),
            "confidence": record.get("confidence", node_record.get("confidence", 0.0)),
        }

        for key, value in record.items():
            if key not in enriched:
                enriched[key] = value

        return enriched

    def _get_decision_node_record(self, decision_id: str) -> Dict[str, Any]:
        """Best-effort lookup of a decision node from the backing graph store."""
        if not decision_id:
            return {}

        if hasattr(self.graph_store, "nodes"):
            nodes = getattr(self.graph_store, "nodes", {})
            if isinstance(nodes, dict):
                node = nodes.get(decision_id)
                if node:
                    properties = getattr(node, "properties", {}) or {}
                    content = getattr(node, "content", "") or ""
                    return {
                        "scenario": properties.get("scenario", content),
                        "category": properties.get("category", ""),
                        "outcome": properties.get("outcome", ""),
                        "confidence": properties.get("confidence", 0.0),
                    }

        get_node = getattr(self.graph_store, "get_node", None)
        if callable(get_node):
            try:
                node = get_node(decision_id)
            except Exception:
                return {}

            if isinstance(node, dict):
                properties = node.get("properties", {}) or {}
                return {
                    "scenario": (
                        properties.get("scenario")
                        or node.get("content")
                        or node.get("scenario", "")
                    ),
                    "category": properties.get("category", node.get("category", "")),
                    "outcome": properties.get("outcome", node.get("outcome", "")),
                    "confidence": properties.get("confidence", node.get("confidence", 0.0)),
                }

        return {}
    
    def analyze_policy_impact(
        self,
        policy_id: str,
        proposed_rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        "What-if" scenarios for policy updates.
        
        Args:
            policy_id: Policy ID to analyze
            proposed_rules: Proposed new rules
            
        Returns:
            Impact analysis results
        """
        try:
            current_policy = self.get_policy(policy_id)
            if not current_policy:
                raise ValueError(f"Policy {policy_id} not found")

            results: List[Dict[str, Any]] = []
            if self._supports_cypher:
                query = """
                MATCH (d:Decision)-[:APPLIED_POLICY]->(p:Policy {policy_id: $policy_id})
                RETURN d.decision_id as decision_id, d.confidence as confidence,
                       d.outcome as outcome, d.category as category
                """
                results = self.graph_store.execute_query(query, {"policy_id": policy_id})
            else:
                if hasattr(self.graph_store, "find_edges") and hasattr(self.graph_store, "nodes"):
                    for edge in self.graph_store.find_edges(edge_type="APPLIED_POLICY"):
                        target = edge.get("target")
                        if not target or not isinstance(target, str):
                            continue
                        policy_node = self.graph_store.nodes.get(target)
                        if not policy_node:
                            continue
                        props = getattr(policy_node, "properties", {}) or {}
                        if props.get("policy_id") != policy_id:
                            continue
                        decision_node = self.graph_store.nodes.get(edge.get("source"))
                        if not decision_node:
                            continue
                        dprops = getattr(decision_node, "properties", {}) or {}
                        results.append({
                            "decision_id": edge.get("source"),
                            "confidence": dprops.get("confidence", 0.0),
                            "outcome": dprops.get("outcome", ""),
                            "category": dprops.get("category", "")
                        })

            affected_decisions = [
                {
                    "decision_id": r.get("decision_id", ""),
                    "compliance_score": r.get("confidence", 0.0)
                }
                for r in (results if isinstance(results, list) else [])
            ]

            impact_analysis = self._calculate_impact_metrics(
                current_policy.rules, proposed_rules, affected_decisions
            )

            self.logger.info(f"Analyzed policy impact for {policy_id}")
            return impact_analysis
            
        except Exception as e:
            self.logger.exception("Failed to analyze policy impact")
            raise
    
    def get_policy(self, policy_id: str, version: Optional[str] = None) -> Optional[Policy]:
        """
        Get policy by ID and optional version.
        
        Args:
            policy_id: Policy ID
            version: Optional version (latest if not specified)
            
        Returns:
            Policy object or None
        """
        try:
            if self._supports_cypher:
                if version:
                    query = """
                    MATCH (p:Policy {policy_id: $policy_id, version: $version})
                    RETURN p
                    """
                    params = {"policy_id": policy_id, "version": version}
                else:
                    query = """
                    MATCH (p:Policy {policy_id: $policy_id})
                    WHERE NOT (p)-[:VERSION_OF]->(:Policy)
                    RETURN p
                    """
                    params = {"policy_id": policy_id}

                results = self.graph_store.execute_query(query, params)

                if results:
                    record = results[0]
                    # Handle both nested {"p": {...}} and flat dict results
                    if isinstance(record, dict) and "p" in record:
                        policy_data = record["p"]
                    elif isinstance(record, dict):
                        policy_data = record
                    else:
                        policy_data = {}
                    if policy_data:
                        return self._dict_to_policy(policy_data)
                return None

            if not hasattr(self.graph_store, "find_nodes"):
                return None

            candidates: List[Dict[str, Any]] = []
            for node in self.graph_store.find_nodes(node_type="Policy"):
                data = node.get("metadata", {}) or {}
                if data.get("policy_id") != policy_id:
                    continue
                if version and data.get("version") != version:
                    continue
                candidates.append(data)

            if not candidates:
                return None

            if version:
                data = candidates[0]
            else:
                # Prefer highest semantic version if available, fallback to updated_at
                def _version_key(v: str) -> tuple:
                    try:
                        parts = [int(p) for p in str(v).split(".")]
                        # Normalize length for comparison
                        while len(parts) < 3:
                            parts.append(-1)
                        return tuple(parts[:3])
                    except Exception:
                        return (-1, -1, -1)

                try:
                    data = max(
                        candidates,
                        key=lambda d: (_version_key(d.get("version")), str(d.get("updated_at") or "")),
                    )
                except Exception:
                    data = max(candidates, key=lambda d: str(d.get("updated_at") or ""))

            return self._dict_to_policy({
                "policy_id": data.get("policy_id"),
                "name": data.get("name"),
                "description": data.get("description"),
                "rules": data.get("rules", {}),
                "category": data.get("category"),
                "version": data.get("version"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "metadata": data.get("metadata", {})
            })
        except Exception as e:
            self.logger.exception("Failed to get policy")
            raise
    
    def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy by ID. Raises ValueError if not found."""
        policy = self.get_policy(policy_id)
        if not policy:
            raise ValueError(f"Policy {policy_id} not found")
        if self._supports_cypher:
            query = "MATCH (p:Policy {policy_id: $policy_id}) DETACH DELETE p"
            self.graph_store.execute_query(query, {"policy_id": policy_id})
        self.logger.info(f"Deleted policy {policy_id}")
        return True

    def _get_metadata_field(self, metadata: Dict[str, Any], decision, field: str):
        """Look up a field in metadata, falling back to suffix match then decision attributes."""
        if field in metadata:
            return metadata[field]
        # Try suffix match: "status" matches "verification_status", "documents" matches "submitted_documents"
        for key in metadata:
            if key.endswith("_" + field):
                return metadata[key]
        return getattr(decision, field, None)

    def _evaluate_compliance(self, decision: Decision, rules: Dict[str, Any]) -> bool:
        """Evaluate decision compliance against policy rules."""
        metadata = decision.metadata or {}

        for rule_key, rule_value in rules.items():
            # min_X → metadata["X"] >= rule_value
            if rule_key.startswith("min_"):
                field = rule_key[4:]
                field_value = self._get_metadata_field(metadata, decision, field)
                if field_value is None:
                    return False
                if field_value < rule_value:
                    return False
            # max_X → metadata["X"] <= rule_value
            elif rule_key.startswith("max_"):
                field = rule_key[4:]
                field_value = self._get_metadata_field(metadata, decision, field)
                if field_value is None:
                    return False
                # For strings use lexicographic comparison
                if field_value > rule_value:
                    return False
            # required_X → metadata["X"] contains all items in rule_value (list) or equals (str)
            elif rule_key.startswith("required_"):
                field = rule_key[9:]
                field_value = self._get_metadata_field(metadata, decision, field)
                if field_value is None:
                    return False
                if isinstance(rule_value, list):
                    if not all(item in field_value for item in rule_value):
                        return False
                elif field_value != rule_value:
                    return False
            # Direct checks from _check_compliance_with_rules
            elif rule_key in {"min_confidence", "allowed_outcomes", "required_categories"}:
                decision_data = {"confidence": decision.confidence, "outcome": decision.outcome,
                                 "category": decision.category}
                if not self._check_compliance_with_rules(decision_data, {rule_key: rule_value}):
                    return False
            else:
                # Unknown rule key — check if field is present in metadata
                if rule_key not in metadata:
                    return False
        return True

    def _calculate_impact_metrics(
        self,
        current_rules: Dict[str, Any],
        proposed_rules: Dict[str, Any],
        affected_decisions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate impact metrics for a proposed rule change."""
        rule_changes = {
            k: {"old": current_rules.get(k), "new": proposed_rules.get(k)}
            for k in set(list(current_rules.keys()) + list(proposed_rules.keys()))
            if current_rules.get(k) != proposed_rules.get(k)
        }
        num_affected = len(affected_decisions)
        avg_compliance = (
            sum(d.get("compliance_score", 0) for d in affected_decisions) / num_affected
            if num_affected else 0.0
        )
        return {
            "affected_decisions": num_affected,
            "compliance_impact": avg_compliance - 1.0,
            "risk_increase": max(0.0, 1.0 - avg_compliance) * 0.5,
            "rule_changes": rule_changes,
            "total_rule_changes": len(rule_changes),
        }

    def _validate_policy_rules(self, rules: Dict[str, Any]) -> None:
        """Validate policy rules structure. Raises ValueError if invalid."""
        errors = []
        for key, value in rules.items():
            if key.startswith("min_") or key.startswith("max_"):
                if not isinstance(value, (int, float)):
                    errors.append(f"Rule '{key}' must be numeric, got {type(value).__name__}")
            if key.endswith("_ratio") and isinstance(value, float) and not (0 <= value <= 1):
                errors.append(f"Rule '{key}' ratio must be between 0 and 1")
            if key.endswith("_documents") or key.endswith("_categories") or key.endswith("_list"):
                if not isinstance(value, list):
                    errors.append(f"Rule '{key}' must be a list, got {type(value).__name__}")
        if errors:
            raise ValueError(f"Invalid policy rules: {'; '.join(errors)}")

    def _validate_version_format(self, version: str) -> None:
        """Validate version string format (semantic versioning). Raises ValueError if invalid."""
        import re
        # Require at least major.minor (e.g. "1.0"), optionally more parts and a pre-release label
        if not version or not re.match(r'^\d+\.\d+(\.\d+)*(-[a-zA-Z0-9]+)?$', version):
            raise ValueError(f"Invalid version format: '{version}'")

    def _generate_next_version(self, current_version: str) -> str:
        """Generate next version number."""
        try:
            # Simple semantic versioning
            parts = current_version.split(".")
            if len(parts) >= 2:
                patch = int(parts[-1]) + 1
                parts[-1] = str(patch)
                return ".".join(parts)
            else:
                return f"{current_version}.1"
        except Exception:
            return f"{current_version}.1"
    
    def _check_compliance_with_rules(
        self,
        decision_data: Dict[str, Any],
        rules: Dict[str, Any]
    ) -> bool:
        """Check compliance with given rules."""
        try:
            if "min_confidence" in rules:
                if decision_data.get("confidence", 0) < rules["min_confidence"]:
                    return False
            
            if "allowed_outcomes" in rules:
                if decision_data.get("outcome", "") not in rules["allowed_outcomes"]:
                    return False
            
            if "required_categories" in rules:
                if decision_data.get("category", "") not in rules["required_categories"]:
                    return False
            
            return True
            
        except Exception:
            return False
    
    def _dict_to_policy(self, data: Dict[str, Any]) -> Policy:
        """Convert dictionary to Policy object."""
        # Handle timestamp conversion
        for field in ["created_at", "updated_at"]:
            if isinstance(data.get(field), str):
                data[field] = datetime.fromisoformat(data[field])
        
        return Policy(
            policy_id=data["policy_id"],  # Required field
            name=data.get("name", ""),
            description=data.get("description", ""),
            rules=data.get("rules", {}),
            category=data.get("category", ""),
            version=data.get("version", ""),
            created_at=data.get("created_at", datetime.now()),
            updated_at=data.get("updated_at", datetime.now()),
            metadata=data.get("metadata", {})
        )
