"""
Graph Validator Module

This module provides comprehensive validation capabilities for knowledge graphs in the
Semantica framework. It ensures graph integrity, schema compliance, and structural consistency.

Key Features:
    - Schema validation (required fields, data types)
    - Structural integrity (dangling edges, self-loops)
    - Type checking (entity and relationship types)
    - Cycle detection
    - Orphan node detection
    - detailed validation reporting

Main Classes:
    - GraphValidator: Main validation engine

Example Usage:
    >>> from semantica.kg import GraphValidator
    >>> validator = GraphValidator()
    >>> result = validator.validate(kg)
    >>> if not result.is_valid:
    ...     print(result.issues)

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Set, Union
from dataclasses import dataclass, field
from enum import Enum
import networkx as nx

from ..utils.logging import get_logger

class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class ValidationIssue:
    """Represents a single validation issue."""
    code: str
    message: str
    severity: ValidationSeverity
    element_id: Optional[str] = None
    element_type: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "element_id": self.element_id,
            "element_type": self.element_type,
            "details": self.details
        }

@dataclass
class ValidationResult:
    """Container for validation results."""
    is_valid: bool
    issues: List[ValidationIssue]
    stats: Dict[str, int] = field(default_factory=dict)

    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Filter issues by severity."""
        return [i for i in self.issues if i.severity == severity]

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "is_valid": self.is_valid,
            "issues": [i.to_dict() for i in self.issues],
            "stats": self.stats
        }

class GraphValidator:
    """
    Comprehensive Knowledge Graph Validator.
    
    Validates graph structure, schema compliance, and data integrity.
    """

    def __init__(self, schema: Optional[Dict[str, Any]] = None, strict: bool = False):
        """
        Initialize the validator.

        Args:
            schema: Optional schema definition to validate against.
                   Should contain 'entity_types' and 'relationship_types'.
            strict: If True, treats warnings as errors.
        """
        self.logger = get_logger("graph_validator")
        self.schema = schema or {}
        self.strict = strict
        
        # Default required fields
        self.required_entity_fields = {"id", "type", "name"}
        self.required_rel_fields = {"source", "target", "type"}

    def validate(self, graph: Dict[str, Any]) -> ValidationResult:
        """
        Run all validation checks on the graph.

        Args:
            graph: The knowledge graph dictionary (must contain 'entities' and 'relationships').

        Returns:
            ValidationResult object containing success status and list of issues.
        """
        issues: List[ValidationIssue] = []
        
        # 1. Basic Structure Check
        if not isinstance(graph, dict):
            issues.append(ValidationIssue(
                code="INVALID_FORMAT",
                message="Graph must be a dictionary.",
                severity=ValidationSeverity.CRITICAL
            ))
            return ValidationResult(False, issues)

        entities = graph.get("entities", [])
        relationships = graph.get("relationships", [])
        
        if not isinstance(entities, list):
             issues.append(ValidationIssue(
                code="INVALID_ENTITIES",
                message="'entities' must be a list.",
                severity=ValidationSeverity.CRITICAL
            ))
             return ValidationResult(False, issues)
             
        if not isinstance(relationships, list):
             issues.append(ValidationIssue(
                code="INVALID_RELATIONSHIPS",
                message="'relationships' must be a list.",
                severity=ValidationSeverity.CRITICAL
            ))
             return ValidationResult(False, issues)

        # 2. Entity Validation
        entity_ids = set()
        for entity in entities:
            # Check required fields
            missing = self.required_entity_fields - set(entity.keys())
            if missing:
                issues.append(ValidationIssue(
                    code="MISSING_FIELD",
                    message=f"Entity missing required fields: {missing}",
                    severity=ValidationSeverity.ERROR,
                    element_id=entity.get("id", "unknown"),
                    element_type="entity"
                ))
            
            # Check ID uniqueness
            eid = entity.get("id")
            if eid:
                if eid in entity_ids:
                    issues.append(ValidationIssue(
                        code="DUPLICATE_ID",
                        message=f"Duplicate entity ID found: {eid}",
                        severity=ValidationSeverity.CRITICAL,
                        element_id=eid,
                        element_type="entity"
                    ))
                entity_ids.add(eid)
            
            # Schema Check (if schema provided)
            if self.schema and "entity_types" in self.schema:
                etype = entity.get("type")
                if etype and etype not in self.schema["entity_types"]:
                    issues.append(ValidationIssue(
                        code="INVALID_TYPE",
                        message=f"Unknown entity type: {etype}",
                        severity=ValidationSeverity.WARNING,
                        element_id=eid,
                        element_type="entity"
                    ))

        # 3. Relationship Validation
        for i, rel in enumerate(relationships):
            # Endpoints may use either the legacy ``source``/``target`` keys or
            # the canonical ``source_id``/``target_id`` keys emitted by
            # ``ContextGraph.to_kg_dict()``. Accept either variant so both
            # representations validate consistently.
            src = rel.get("source")
            if src is None:
                src = rel.get("source_id")
            tgt = rel.get("target")
            if tgt is None:
                tgt = rel.get("target_id")

            # Check required fields: ``type`` plus a resolvable source/target.
            missing = set()
            if "type" not in rel:
                missing.add("type")
            if src is None:
                missing.add("source")
            if tgt is None:
                missing.add("target")
            if missing:
                issues.append(ValidationIssue(
                    code="MISSING_FIELD",
                    message=f"Relationship missing required fields: {missing}",
                    severity=ValidationSeverity.ERROR,
                    element_type="relationship",
                    details={"index": i}
                ))
                continue
            
            # Check Dangling Edges
            def is_valid_id(node_id):
                if node_id is None:
                    return False
                try:
                    return node_id in entity_ids
                except TypeError:
                    # Not hashable, so it can't be in the set of string IDs
                    return False

            if not is_valid_id(src):
                issues.append(ValidationIssue(
                    code="DANGLING_EDGE",
                    message=f"Source entity ID not found or invalid: {src}",
                    severity=ValidationSeverity.ERROR,
                    element_id=f"{src}->{tgt}",
                    element_type="relationship",
                    details={"source_id": str(src)}
                ))
            if not is_valid_id(tgt):
                issues.append(ValidationIssue(
                    code="DANGLING_EDGE",
                    message=f"Target entity ID not found or invalid: {tgt}",
                    severity=ValidationSeverity.ERROR,
                    element_id=f"{src}->{tgt}",
                    element_type="relationship",
                    details={"target_id": str(tgt)}
                ))

            # Check Self-Loops (Warning)
            if src == tgt:
                issues.append(ValidationIssue(
                    code="SELF_LOOP",
                    message=f"Self-loop detected on entity: {src}",
                    severity=ValidationSeverity.INFO,
                    element_id=src,
                    element_type="relationship"
                ))

        # 4. Structural Analysis (Cycles, connectivity)
        # Only run if graph is small enough or requested? 
        # For now, let's do a quick cycle check using NetworkX
        try:
            nx_graph = nx.DiGraph()
            nx_graph.add_nodes_from(entity_ids)
            nx_graph.add_edges_from([(r["source"], r["target"]) for r in relationships if r.get("source") in entity_ids and r.get("target") in entity_ids])
            
            # Check for cycles
            try:
                cycles = list(nx.simple_cycles(nx_graph))
                if cycles:
                     issues.append(ValidationIssue(
                        code="CYCLE_DETECTED",
                        message=f"Graph contains {len(cycles)} cycles.",
                        severity=ValidationSeverity.INFO, # Cycles aren't always bad
                        details={"count": len(cycles)}
                    ))
            except Exception:
                pass # Skip if too complex

            # Check for Orphans (Isolated nodes)
            isolates = list(nx.isolates(nx_graph))
            if isolates:
                 issues.append(ValidationIssue(
                    code="ORPHAN_NODES",
                    message=f"Found {len(isolates)} orphan nodes (no relationships).",
                    severity=ValidationSeverity.WARNING,
                    details={"count": len(isolates), "ids": isolates[:10]} # Limit output
                ))

        except Exception as e:
            self.logger.warning(f"Structural validation failed: {e}")

        # Determine Validity
        error_count = len([i for i in issues if i.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]])
        if self.strict:
            warning_count = len([i for i in issues if i.severity == ValidationSeverity.WARNING])
            is_valid = (error_count + warning_count) == 0
        else:
            is_valid = error_count == 0

        stats = {
            "total_entities": len(entities),
            "total_relationships": len(relationships),
            "issues_found": len(issues),
            "errors": error_count
        }

        return ValidationResult(is_valid, issues, stats)
