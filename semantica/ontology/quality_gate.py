"""Deterministic quality checks for ontology and KG pipelines."""

import copy
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from ..kg.graph_validator import GraphValidator
from .ontology_evaluator import OntologyEvaluator
from .ontology_validator import OntologyValidator


class QualitySeverity(str, Enum):
    """Severity assigned to a quality finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class QualityIssue:
    """A single machine-readable ontology quality finding."""

    code: str
    message: str
    severity: QualitySeverity
    element_id: Optional[str] = None
    element_type: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly representation of the issue."""
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "element_id": self.element_id,
            "element_type": self.element_type,
            "details": self.details,
        }


@dataclass
class OntologyQualityReport:
    """Result returned by :class:`OntologyQualityGate`."""

    passed: bool
    issues: List[QualityIssue] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    thresholds: Dict[str, Optional[float]] = field(default_factory=dict)
    threshold_failures: List[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Number of error and critical findings."""
        return sum(
            issue.severity in (QualitySeverity.ERROR, QualitySeverity.CRITICAL)
            for issue in self.issues
        )

    @property
    def warning_count(self) -> int:
        """Number of warning findings."""
        return sum(issue.severity == QualitySeverity.WARNING for issue in self.issues)

    @property
    def info_count(self) -> int:
        """Number of informational findings."""
        return sum(issue.severity == QualitySeverity.INFO for issue in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly representation of the report."""
        return {
            "passed": self.passed,
            "issues": [issue.to_dict() for issue in self.issues],
            "stats": {
                **self.stats,
                "issues": len(self.issues),
                "errors": self.error_count,
                "warnings": self.warning_count,
                "infos": self.info_count,
            },
            "metrics": self.metrics,
            "thresholds": self.thresholds,
            "threshold_failures": self.threshold_failures,
        }


class OntologyQualityGate:
    """Run deterministic, CI-friendly ontology quality checks."""

    DEFAULT_THRESHOLDS: Dict[str, Optional[float]] = {
        "min_coverage": 0.0,
        "max_errors": 0.0,
        "max_warnings": None,
    }
    _DATA_PROPERTY_TYPES = {"data", "datatype", "data_property", "literal"}
    _OBJECT_PROPERTY_TYPES = {"object", "object_property", "relationship"}
    _KNOWN_DATATYPES = {
        "string",
        "boolean",
        "decimal",
        "float",
        "double",
        "integer",
        "int",
        "long",
        "short",
        "byte",
        "date",
        "datetime",
        "datetimestamp",
        "time",
        "duration",
        "anyuri",
    }
    _BUILTIN_CLASSES = {
        "owl:thing",
        "rdfs:resource",
        "http://www.w3.org/2002/07/owl#thing",
        "http://www.w3.org/2000/01/rdf-schema#resource",
    }

    def __init__(
        self,
        validator: Optional[OntologyValidator] = None,
        evaluator: Optional[OntologyEvaluator] = None,
        thresholds: Optional[Mapping[str, Optional[float]]] = None,
        fail_on_warnings: bool = False,
    ) -> None:
        self.validator = validator or OntologyValidator()
        self.evaluator = evaluator or OntologyEvaluator()
        self.thresholds = dict(self.DEFAULT_THRESHOLDS)
        if thresholds:
            self.thresholds.update(thresholds)
        self.fail_on_warnings = fail_on_warnings

    def check(
        self,
        ontology: Any,
        graph_data: Optional[Dict[str, Any]] = None,
        *,
        thresholds: Optional[Mapping[str, Optional[float]]] = None,
        fail_on_warnings: Optional[bool] = None,
        competency_questions: Optional[List[str]] = None,
    ) -> OntologyQualityReport:
        """Check an ontology and optionally its instance graph.

        ``graph_data`` is optional because an ontology can be checked before
        instances are available. When omitted, embedded ``entities`` and
        ``relationships`` are checked when present.
        """
        active_thresholds = dict(self.thresholds)
        if thresholds:
            active_thresholds.update(thresholds)
        min_coverage, max_errors, max_warnings = self._validate_thresholds(
            active_thresholds
        )
        should_fail_on_warnings = (
            self.fail_on_warnings if fail_on_warnings is None else fail_on_warnings
        )
        issues: List[QualityIssue] = []

        if not isinstance(ontology, dict):
            self._add_issue(
                issues,
                "INVALID_ONTOLOGY",
                "Ontology must be a dictionary.",
                QualitySeverity.CRITICAL,
                element_type="ontology",
            )
            return self._build_report(
                issues,
                classes=0,
                properties=0,
                entities=0,
                relationships=0,
                metrics={
                    "coverage": 0.0,
                    "class_coverage": 0.0,
                    "property_coverage": 0.0,
                },
                thresholds=active_thresholds,
                min_coverage=min_coverage,
                max_errors=max_errors,
                max_warnings=max_warnings,
                fail_on_warnings=should_fail_on_warnings,
            )

        validation = self.validator.validate(ontology)
        for message in getattr(validation, "errors", []) or []:
            self._add_issue(
                issues,
                "VALIDATOR_ERROR",
                str(message),
                QualitySeverity.ERROR,
                element_type="ontology",
            )
        for message in getattr(validation, "warnings", []) or []:
            self._add_issue(
                issues,
                "VALIDATOR_WARNING",
                str(message),
                QualitySeverity.WARNING,
                element_type="ontology",
            )

        classes = self._read_collection(ontology, "classes", issues)
        properties = self._read_collection(ontology, "properties", issues)
        class_aliases, class_ids = self._index_elements(
            classes, "class", "MISSING_CLASS_ID", issues
        )
        referenced_classes: Set[str] = set()
        self._mark_hierarchy(classes, class_aliases, referenced_classes)

        property_with_endpoints = 0
        for index, prop in enumerate(properties):
            if not isinstance(prop, dict):
                self._add_issue(
                    issues,
                    "INVALID_PROPERTY",
                    f"Property at index {index} must be a dictionary.",
                    QualitySeverity.ERROR,
                    element_type="property",
                    details={"index": index},
                )
                continue

            prop_id = self._identifier(prop)
            if prop_id is None:
                prop_id = f"property[{index}]"
                self._add_issue(
                    issues,
                    "MISSING_PROPERTY_ID",
                    f"Property at index {index} has no name or URI.",
                    QualitySeverity.ERROR,
                    element_type="property",
                    details={"index": index},
                )

            raw_prop_type = prop.get("type")
            prop_type = (
                str(raw_prop_type).strip().lower() if raw_prop_type is not None else ""
            )
            if not prop_type:
                self._add_issue(
                    issues,
                    "MISSING_PROPERTY_TYPE",
                    f"Property '{prop_id}' has no type.",
                    QualitySeverity.ERROR,
                    element_id=prop_id,
                    element_type="property",
                )
            elif (
                prop_type not in self._DATA_PROPERTY_TYPES | self._OBJECT_PROPERTY_TYPES
            ):
                self._add_issue(
                    issues,
                    "UNKNOWN_PROPERTY_TYPE",
                    f"Property '{prop_id}' has unknown type '{prop_type}'.",
                    QualitySeverity.WARNING,
                    element_id=prop_id,
                    element_type="property",
                )

            domains = self._values(prop, "domain")
            ranges = self._values(prop, "range")
            if domains or ranges:
                property_with_endpoints += 1
            else:
                self._add_issue(
                    issues,
                    "ORPHAN_PROPERTY",
                    f"Property '{prop_id}' has no domain or range.",
                    QualitySeverity.WARNING,
                    element_id=prop_id,
                    element_type="property",
                )
            if not domains:
                self._add_issue(
                    issues,
                    "MISSING_DOMAIN",
                    f"Property '{prop_id}' has no domain.",
                    QualitySeverity.WARNING,
                    element_id=prop_id,
                    element_type="property",
                )
            for domain in domains:
                matched = self._match_class(domain, class_aliases)
                if matched:
                    referenced_classes.add(matched)
                elif not self._is_builtin_class(domain):
                    self._add_issue(
                        issues,
                        "UNKNOWN_DOMAIN",
                        f"Property '{prop_id}' references unknown domain '{domain}'.",
                        QualitySeverity.ERROR,
                        element_id=prop_id,
                        element_type="property",
                        details={"domain": domain},
                    )

            if not ranges:
                self._add_issue(
                    issues,
                    "MISSING_RANGE",
                    f"Property '{prop_id}' has no range.",
                    QualitySeverity.WARNING,
                    element_id=prop_id,
                    element_type="property",
                )
            for range_value in ranges:
                matched = self._match_class(range_value, class_aliases)
                if matched:
                    referenced_classes.add(matched)
                self._check_range(
                    prop_id,
                    prop_type,
                    range_value,
                    matched is not None,
                    issues,
                )

        graph = graph_data
        if graph is None and ("entities" in ontology or "relationships" in ontology):
            graph = ontology
        graph_entities, graph_relationships = self._read_graph(graph, issues)
        if self._has_valid_graph_shape(graph):
            self._check_graph(graph, issues)
            self._mark_graph_types(graph_entities, class_aliases, referenced_classes)

        for class_id in class_ids:
            if class_id not in referenced_classes:
                self._add_issue(
                    issues,
                    "ORPHAN_CLASS",
                    f"Class '{class_id}' is not connected to a property, hierarchy, or graph entity type.",
                    QualitySeverity.WARNING,
                    element_id=class_id,
                    element_type="class",
                )

        class_coverage = (
            len(referenced_classes & set(class_ids)) / len(class_ids)
            if class_ids
            else 0.0
        )
        property_coverage = (
            property_with_endpoints / len(properties) if properties else 1.0
        )
        metrics: Dict[str, float] = {
            "coverage": (
                (class_coverage + property_coverage) / 2
                if classes or properties
                else 0.0
            ),
            "class_coverage": class_coverage,
            "property_coverage": property_coverage,
            "validator_valid": 1.0 if getattr(validation, "valid", True) else 0.0,
        }
        if competency_questions is not None:
            evaluation_ontology = self._prepare_for_evaluation(
                ontology, classes, properties
            )
            evaluation = self._evaluate_competency_questions(
                evaluation_ontology, competency_questions=competency_questions
            )
            metrics["competency_question_coverage"] = evaluation.coverage_score
            metrics["completeness"] = evaluation.completeness_score

        return self._build_report(
            issues,
            classes=len(classes),
            properties=len(properties),
            entities=len(graph_entities),
            relationships=len(graph_relationships),
            metrics=metrics,
            thresholds=active_thresholds,
            min_coverage=min_coverage,
            max_errors=max_errors,
            max_warnings=max_warnings,
            fail_on_warnings=should_fail_on_warnings,
        )

    def _check_range(
        self,
        prop_id: str,
        prop_type: str,
        range_value: Any,
        is_class: bool,
        issues: List[QualityIssue],
    ) -> None:
        if prop_type in self._DATA_PROPERTY_TYPES:
            if not self._is_known_datatype(range_value):
                self._add_issue(
                    issues,
                    "INVALID_DATATYPE_RANGE",
                    f"Data property '{prop_id}' has invalid range '{range_value}'.",
                    QualitySeverity.ERROR,
                    element_id=prop_id,
                    element_type="property",
                    details={"range": range_value},
                )
        elif prop_type in self._OBJECT_PROPERTY_TYPES:
            if not is_class and not self._is_builtin_class(range_value):
                self._add_issue(
                    issues,
                    "UNKNOWN_RANGE",
                    f"Object property '{prop_id}' references unknown range '{range_value}'.",
                    QualitySeverity.ERROR,
                    element_id=prop_id,
                    element_type="property",
                    details={"range": range_value},
                )
        elif (
            not is_class
            and not self._is_builtin_class(range_value)
            and not self._is_known_datatype(range_value)
        ):
            self._add_issue(
                issues,
                "UNKNOWN_RANGE",
                f"Property '{prop_id}' references unknown range '{range_value}'.",
                QualitySeverity.ERROR,
                element_id=prop_id,
                element_type="property",
                details={"range": range_value},
            )

    def _build_report(
        self,
        issues: List[QualityIssue],
        *,
        classes: int,
        properties: int,
        entities: int,
        relationships: int,
        metrics: Dict[str, float],
        thresholds: Dict[str, Optional[float]],
        min_coverage: float,
        max_errors: float,
        max_warnings: Optional[float],
        fail_on_warnings: bool,
    ) -> OntologyQualityReport:
        failures: List[str] = []
        error_count = sum(
            issue.severity in (QualitySeverity.ERROR, QualitySeverity.CRITICAL)
            for issue in issues
        )
        warning_count = sum(
            issue.severity == QualitySeverity.WARNING for issue in issues
        )
        if error_count > max_errors:
            failures.append("max_errors")
        if max_warnings is not None and warning_count > max_warnings:
            failures.append("max_warnings")
        if fail_on_warnings and warning_count:
            failures.append("fail_on_warnings")
        if metrics.get("coverage", 0.0) < min_coverage:
            failures.append("min_coverage")
        return OntologyQualityReport(
            passed=not failures,
            issues=issues,
            stats={
                "classes": classes,
                "properties": properties,
                "entities": entities,
                "relationships": relationships,
            },
            metrics=metrics,
            thresholds=thresholds,
            threshold_failures=failures,
        )

    @staticmethod
    def _validate_thresholds(
        thresholds: Mapping[str, Optional[float]],
    ) -> Tuple[float, float, Optional[float]]:
        min_coverage = float(thresholds.get("min_coverage", 0.0) or 0.0)
        max_errors = float(thresholds.get("max_errors", 0.0) or 0.0)
        warning_value = thresholds.get("max_warnings")
        max_warnings = None if warning_value is None else float(warning_value)
        if not all(
            math.isfinite(value)
            for value in (min_coverage, max_errors)
            if value is not None
        ) or (max_warnings is not None and not math.isfinite(max_warnings)):
            raise ValueError("quality thresholds must be finite numbers")
        if not 0.0 <= min_coverage <= 1.0:
            raise ValueError("min_coverage must be between 0.0 and 1.0")
        if max_errors < 0 or (max_warnings is not None and max_warnings < 0):
            raise ValueError("error and warning thresholds cannot be negative")
        return min_coverage, max_errors, max_warnings

    @classmethod
    def _prepare_for_evaluation(
        cls,
        ontology: Dict[str, Any],
        classes: Iterable[Any],
        properties: Iterable[Any],
    ) -> Dict[str, Any]:
        """Make a shallow, evaluator-safe view without changing caller data."""
        prepared = dict(ontology)
        prepared["classes"] = [
            cls._prepare_element(element)
            for element in classes
            if isinstance(element, dict)
        ]
        prepared["properties"] = [
            cls._prepare_element(element)
            for element in properties
            if isinstance(element, dict)
        ]
        return prepared

    @classmethod
    def _prepare_element(cls, element: Dict[str, Any]) -> Dict[str, Any]:
        prepared = dict(element)
        identifier = cls._identifier(prepared)
        if identifier is not None and not str(prepared.get("name", "")).strip():
            prepared["name"] = identifier
        return prepared

    def _evaluate_competency_questions(
        self, ontology: Dict[str, Any], competency_questions: List[str]
    ) -> Any:
        """Evaluate with an isolated question manager for repeatable checks."""
        evaluator = copy.copy(self.evaluator)
        manager = getattr(self.evaluator, "competency_questions_manager", None)
        if manager is not None and hasattr(manager, "questions"):
            isolated_manager = copy.copy(manager)
            isolated_manager.questions = []
            evaluator.competency_questions_manager = isolated_manager
        return evaluator.evaluate_ontology(
            ontology, competency_questions=competency_questions
        )

    @classmethod
    def _read_collection(
        cls, ontology: Dict[str, Any], key: str, issues: List[QualityIssue]
    ) -> List[Any]:
        if key not in ontology:
            cls._add_issue(
                issues,
                f"MISSING_{key.upper()}",
                f"Ontology has no {key} defined.",
                QualitySeverity.WARNING,
                element_type="ontology",
            )
            return []
        value = ontology[key]
        if not isinstance(value, list):
            cls._add_issue(
                issues,
                f"INVALID_{key.upper()}",
                f"Ontology '{key}' must be a list.",
                QualitySeverity.ERROR,
                element_type="ontology",
            )
            return []
        return value

    @classmethod
    def _index_elements(
        cls,
        elements: Iterable[Any],
        element_type: str,
        missing_code: str,
        issues: List[QualityIssue],
    ) -> Tuple[Dict[str, str], List[str]]:
        aliases: Dict[str, str] = {}
        identifiers: List[str] = []
        for index, element in enumerate(elements):
            identifier = cls._identifier(element)
            if identifier is None:
                cls._add_issue(
                    issues,
                    missing_code,
                    f"{element_type.title()} at index {index} has no name or URI.",
                    QualitySeverity.ERROR,
                    element_type=element_type,
                    details={"index": index},
                )
                continue
            identifiers.append(identifier)
            aliases_for_element: Set[str] = set()
            for candidate in cls._identifiers(element):
                aliases_for_element.update(cls._term_aliases(candidate))
            for alias in sorted(aliases_for_element):
                aliases.setdefault(alias, identifier)
        return aliases, identifiers

    @classmethod
    def _mark_hierarchy(
        cls,
        classes: Iterable[Any],
        aliases: Mapping[str, str],
        referenced: Set[str],
    ) -> None:
        for class_entry in classes:
            if not isinstance(class_entry, dict):
                continue
            identifier = cls._identifier(class_entry)
            for key in (
                "subClassOf",
                "subclassOf",
                "parent",
                "superclass",
                "superclasses",
            ):
                parents = cls._values(class_entry, key)
                if parents and identifier:
                    referenced.add(identifier)
                for parent in parents:
                    matched = cls._match_class(parent, aliases)
                    if matched:
                        referenced.add(matched)

    @classmethod
    def _mark_graph_types(
        cls,
        entities: Iterable[Any],
        aliases: Mapping[str, str],
        referenced: Set[str],
    ) -> None:
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_type = entity.get("type") or entity.get("entity_type")
            matched = cls._match_class(entity_type, aliases)
            if matched:
                referenced.add(matched)

    @classmethod
    def _check_graph(cls, graph: Dict[str, Any], issues: List[QualityIssue]) -> None:
        safe_graph = cls._prepare_graph_for_validation(graph, issues)
        result = GraphValidator().validate(safe_graph)
        code_map = {
            "DANGLING_EDGE": "UNRESOLVED_RELATIONSHIP_ENDPOINT",
            "ORPHAN_NODES": "ORPHAN_ENTITY",
        }
        severity_map = {
            "info": QualitySeverity.INFO,
            "warning": QualitySeverity.WARNING,
            "error": QualitySeverity.ERROR,
            "critical": QualitySeverity.CRITICAL,
        }
        for graph_issue in result.issues:
            severity = severity_map.get(
                graph_issue.severity.value, QualitySeverity.ERROR
            )
            details = dict(graph_issue.details or {})
            if graph_issue.code == "ORPHAN_NODES" and "ids" in details:
                details["ids"] = sorted(details["ids"], key=str)
            cls._add_issue(
                issues,
                code_map.get(graph_issue.code, graph_issue.code),
                graph_issue.message,
                severity,
                element_id=graph_issue.element_id,
                element_type=graph_issue.element_type,
                details=details,
            )

    @classmethod
    def _prepare_graph_for_validation(
        cls, graph: Dict[str, Any], issues: List[QualityIssue]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Normalize supported graph aliases and isolate malformed members."""
        entities: List[Dict[str, Any]] = []
        raw_entities = graph.get("entities", [])
        raw_relationships = graph.get("relationships", [])
        for index, entity in enumerate(
            raw_entities if isinstance(raw_entities, list) else []
        ):
            if not isinstance(entity, dict):
                cls._add_issue(
                    issues,
                    "INVALID_ENTITY",
                    f"Entity at index {index} must be a dictionary.",
                    QualitySeverity.ERROR,
                    element_type="entity",
                    details={"index": index},
                )
                continue
            normalized = dict(entity)
            if not normalized.get("name") and normalized.get("text") is not None:
                normalized["name"] = normalized["text"]
            entities.append(normalized)

        relationships: List[Dict[str, Any]] = []
        for index, relationship in enumerate(
            raw_relationships if isinstance(raw_relationships, list) else []
        ):
            if not isinstance(relationship, dict):
                cls._add_issue(
                    issues,
                    "INVALID_RELATIONSHIP",
                    f"Relationship at index {index} must be a dictionary.",
                    QualitySeverity.ERROR,
                    element_type="relationship",
                    details={"index": index},
                )
                continue
            relationships.append(dict(relationship))

        return {"entities": entities, "relationships": relationships}

    @classmethod
    def _read_graph(
        cls, graph: Optional[Dict[str, Any]], issues: List[QualityIssue]
    ) -> Tuple[List[Any], List[Any]]:
        if graph is None:
            return [], []
        if not isinstance(graph, dict):
            cls._add_issue(
                issues,
                "INVALID_GRAPH",
                "Graph data must be a dictionary.",
                QualitySeverity.ERROR,
                element_type="graph",
            )
            return [], []
        entities = graph.get("entities", [])
        relationships = graph.get("relationships", [])
        if not isinstance(entities, list) or not isinstance(relationships, list):
            cls._add_issue(
                issues,
                "INVALID_GRAPH",
                "Graph entities and relationships must be lists.",
                QualitySeverity.ERROR,
                element_type="graph",
            )
            return [], []
        return entities, relationships

    @staticmethod
    def _has_valid_graph_shape(graph: Optional[Dict[str, Any]]) -> bool:
        return bool(
            isinstance(graph, dict)
            and isinstance(graph.get("entities", []), list)
            and isinstance(graph.get("relationships", []), list)
        )

    @staticmethod
    def _identifier(element: Any) -> Optional[str]:
        identifiers = OntologyQualityGate._identifiers(element)
        return identifiers[0] if identifiers else None

    @staticmethod
    def _identifiers(element: Any) -> List[str]:
        if isinstance(element, dict):
            values = []
            for key in ("name", "uri", "id", "@id"):
                value = element.get(key)
                if value is not None and str(value).strip():
                    values.append(str(value).strip())
            return values
        if isinstance(element, str) and element.strip():
            return [element.strip()]
        return []

    @staticmethod
    def _values(element: Dict[str, Any], key: str) -> List[Any]:
        value = element.get(key)
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            values = [item for item in value if item is not None and str(item).strip()]
            return sorted(values, key=str) if isinstance(value, set) else values
        return [value] if str(value).strip() else []

    @classmethod
    def _term_aliases(cls, value: Any) -> Set[str]:
        if isinstance(value, dict):
            value = cls._identifier(value)
        if value is None:
            return set()
        text = str(value).strip().strip("<>")
        if not text:
            return set()
        aliases = {text, text.lower()}
        for separator in ("#", "/"):
            if separator in text:
                local = text.rstrip("/").rsplit(separator, 1)[-1]
                aliases.update({local, local.lower()})
        if ":" in text and not text.startswith(("http://", "https://")):
            local = text.rsplit(":", 1)[-1]
            aliases.update({local, local.lower()})
        return aliases

    @classmethod
    def _match_class(cls, value: Any, aliases: Mapping[str, str]) -> Optional[str]:
        for alias in sorted(cls._term_aliases(value)):
            if alias in aliases:
                return aliases[alias]
        return None

    @classmethod
    def _is_builtin_class(cls, value: Any) -> bool:
        return any(alias in cls._BUILTIN_CLASSES for alias in cls._term_aliases(value))

    @classmethod
    def _is_known_datatype(cls, value: Any) -> bool:
        return any(alias in cls._KNOWN_DATATYPES for alias in cls._term_aliases(value))

    @staticmethod
    def _add_issue(
        issues: List[QualityIssue],
        code: str,
        message: str,
        severity: QualitySeverity,
        *,
        element_id: Optional[str] = None,
        element_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        issues.append(
            QualityIssue(
                code=code,
                message=message,
                severity=severity,
                element_id=element_id,
                element_type=element_type,
                details=details or {},
            )
        )


def ontology_quality_check(
    ontology: Any,
    graph_data: Optional[Dict[str, Any]] = None,
    *,
    thresholds: Optional[Mapping[str, Optional[float]]] = None,
    fail_on_warnings: bool = False,
    competency_questions: Optional[List[str]] = None,
    validator: Optional[OntologyValidator] = None,
    evaluator: Optional[OntologyEvaluator] = None,
) -> OntologyQualityReport:
    """Convenience wrapper around :class:`OntologyQualityGate`."""
    gate = OntologyQualityGate(
        validator=validator,
        evaluator=evaluator,
        thresholds=thresholds,
        fail_on_warnings=fail_on_warnings,
    )
    return gate.check(
        ontology,
        graph_data=graph_data,
        competency_questions=competency_questions,
    )
