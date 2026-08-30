"""
Extraction Validator Module

This module provides comprehensive quality validation for semantic extractions,
ensuring accuracy, consistency, and reliability of extracted entities and relations.
Supports method parameter for future extensibility with method-specific validation.

Supported Methods (for future extensibility):
    - Method parameter reserved for method-specific validation strategies
    - Currently supports general validation for all extraction methods
    - Future: Method-specific validation rules (e.g., "llm", "ml", "pattern")

Algorithms Used:
    - Confidence Thresholding: Statistical threshold-based filtering
    - Duplicate Detection: (Removed - handled by external module)
    - Consistency Checking: (Removed - handled by external module)
    - Quality Scoring: Weighted scoring algorithms for extraction quality
    - Validation Metrics: Precision, recall, F1-score calculations
    - Boundary Validation: Character position and text boundary checking

Key Features:
    - Entity validation with confidence checking
    - Relation validation and consistency checking
    - Quality scoring and metrics calculation
    - Confidence-based filtering
    - Validation result reporting
    - Method parameter support for future method-specific validation

Main Classes:
    - ExtractionValidator: Main validation coordinator
    - ValidationResult: Validation result representation dataclass

Example Usage:
    >>> from semantica.semantic_extract import ExtractionValidator
    >>> # Using default validation
    >>> validator = ExtractionValidator()
    >>> result = validator.validate_entities(entities)
    >>> if result.valid:
    ...     print(f"Quality score: {result.score}")
    >>> 
    >>> # Using method-specific validation (future extensibility)
    >>> validator = ExtractionValidator(method="llm")
    >>> filtered = validator.filter_by_confidence(entities, min_confidence=0.8)

Author: Semantica Contributors
License: MIT
"""

from typing import List, Dict, Any, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import re

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .ner_extractor import Entity
from .types import meets_confidence_threshold
from .relation_extractor import Relation


@dataclass
class ValidationResult:
    """Validation result representation."""

    valid: bool
    score: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExtractionValidator:
    """Validator for semantic extractions."""

    def __init__(self, method: Optional[str] = None, **config):
        """
        Initialize extraction validator.

        Args:
            method: Validation method (for future extensibility, currently unused)
            **config: Configuration options:
                - min_confidence: Minimum confidence threshold (default: 0.5)
        """
        self.logger = get_logger("extraction_validator")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.method = method  # Reserved for future method-based validation
        self.min_confidence = config.get("min_confidence", 0.5)

    def validate_entities(self, entities: Union[List[Entity], List[List[Entity]]], **options) -> Union[ValidationResult, List[ValidationResult]]:
        """
        Validate extracted entities.
        Handles both single list and batch list of entities.

        Args:
            entities: List of entities or list of list of entities
            **options: Validation options

        Returns:
            ValidationResult or List[ValidationResult]: Validation result(s)
        """
        # Handle batch validation
        if entities and isinstance(entities, list) and len(entities) > 0 and isinstance(entities[0], list):
            results = []
            for idx, batch_entities in enumerate(entities):
                res = self.validate_entities(batch_entities, **options)
                # Ensure metadata has batch index
                if "batch_index" not in res.metadata:
                    res.metadata["batch_index"] = idx
                results.append(res)
            return results

        tracking_id = self.progress_tracker.start_tracking(
            module="semantic_extract",
            submodule="ExtractionValidator",
            message=f"Validating {len(entities)} entities",
        )

        try:
            errors = []
            warnings = []
            metrics = {}

            min_confidence = options.get("min_confidence", self.min_confidence)

            # Check confidence scores
            self.progress_tracker.update_tracking(
                tracking_id, message="Checking confidence scores..."
            )
            scored = [e for e in entities if e.confidence is not None]
            low_confidence = [e for e in scored if e.confidence < min_confidence]
            if low_confidence:
                warnings.append(
                    f"{len(low_confidence)} entities below confidence threshold"
                )


            # Check for empty entities
            empty_entities = [e for e in entities if not e.text.strip()]
            if empty_entities:
                errors.append(f"{len(empty_entities)} empty entities found")

            # Calculate metrics (entities with unknown confidence are counted
            # separately and excluded from the score buckets and average)
            metrics = {
                "total_entities": len(entities),
                "high_confidence": len([e for e in scored if e.confidence >= 0.8]),
                "medium_confidence": len(
                    [e for e in scored if min_confidence <= e.confidence < 0.8]
                ),
                "low_confidence": len(low_confidence),
                "unscored": len(entities) - len(scored),
                "unique_entities": len(set(e.text for e in entities)),
                "entity_types": len(set(e.label for e in entities)),
                "average_confidence": sum(e.confidence for e in scored)
                / len(scored)
                if scored
                else None,
            }

            # Calculate score
            score = self._calculate_entity_score(entities, metrics)

            valid = len(errors) == 0

            # Collect metadata from entities
            metadata = {}
            if entities:
                first = entities[0]
                if hasattr(first, "metadata") and first.metadata:
                    if "batch_index" in first.metadata:
                        metadata["batch_index"] = first.metadata["batch_index"]
                    if "document_id" in first.metadata:
                        metadata["document_id"] = first.metadata["document_id"]

            result = ValidationResult(
                valid=valid,
                score=score,
                errors=errors,
                warnings=warnings,
                metrics=metrics,
                metadata=metadata,
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Validation complete: {len(errors)} errors, {len(warnings)} warnings",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def validate_relations(
        self, relations: Union[List[Relation], List[List[Relation]]], **options
    ) -> Union[ValidationResult, List[ValidationResult]]:
        """
        Validate extracted relations.
        Handles both single list and batch list of relations.

        Args:
            relations: List of relations or list of list of relations
            **options: Validation options

        Returns:
            ValidationResult or List[ValidationResult]: Validation result(s)
        """
        # Handle batch validation
        if relations and isinstance(relations, list) and len(relations) > 0 and isinstance(relations[0], list):
            results = []
            for idx, batch_relations in enumerate(relations):
                res = self.validate_relations(batch_relations, **options)
                # Ensure metadata has batch index
                if "batch_index" not in res.metadata:
                    res.metadata["batch_index"] = idx
                results.append(res)
            return results

        errors = []
        warnings = []
        metrics = {}

        min_confidence = options.get("min_confidence", self.min_confidence)

        # Check confidence scores
        low_confidence = [r for r in relations if r.confidence < min_confidence]
        if low_confidence:
            warnings.append(
                f"{len(low_confidence)} relations below confidence threshold"
            )

        # Check for valid subject and object
        invalid_relations = [
            r
            for r in relations
            if not r.subject or not r.object or r.subject.text == r.object.text
        ]
        if invalid_relations:
            errors.append(f"{len(invalid_relations)} invalid relations found")

        # Calculate metrics
        metrics = {
            "total_relations": len(relations),
            "high_confidence": len([r for r in relations if r.confidence >= 0.8]),
            "medium_confidence": len(
                [r for r in relations if min_confidence <= r.confidence < 0.8]
            ),
            "low_confidence": len(low_confidence),
            "relation_types": len(set(r.predicate for r in relations)),
            "average_confidence": sum(r.confidence for r in relations) / len(relations)
            if relations
            else 0.0,
            "invalid_relations": len(invalid_relations),
        }

        # Calculate score
        score = self._calculate_relation_score(relations, metrics)

        valid = len(errors) == 0

        # Collect metadata from relations
        metadata = {}
        if relations:
            first = relations[0]
            if hasattr(first, "metadata") and first.metadata:
                if "batch_index" in first.metadata:
                    metadata["batch_index"] = first.metadata["batch_index"]
                if "document_id" in first.metadata:
                    metadata["document_id"] = first.metadata["document_id"]

        return ValidationResult(
            valid=valid, 
            score=score, 
            errors=errors, 
            warnings=warnings, 
            metrics=metrics,
            metadata=metadata
        )

    def _calculate_entity_score(
        self, entities: List[Entity], metrics: Dict[str, Any]
    ) -> float:
        """Calculate entity validation score."""
        if not entities:
            return 0.0

        score = 1.0

        # Confidence penalty
        low_conf_ratio = metrics.get("low_confidence", 0) / metrics.get(
            "total_entities", 1
        )
        score *= 1.0 - low_conf_ratio * 0.5

        # Duplicate penalty
        dup_ratio = metrics.get("duplicates", 0) / metrics.get("total_entities", 1)
        score *= 1.0 - dup_ratio * 0.3

        # Average confidence factor (skipped when no entity carries a
        # measured confidence: unknown is neutral, not zero)
        avg_confidence = metrics.get("average_confidence")
        if avg_confidence is not None:
            score *= 0.5 + avg_confidence * 0.5

        return max(0.0, min(1.0, score))

    def _calculate_relation_score(
        self, relations: List[Relation], metrics: Dict[str, Any]
    ) -> float:
        """Calculate relation validation score."""
        if not relations:
            return 0.0

        score = 1.0

        # Confidence penalty
        low_conf_ratio = metrics.get("low_confidence", 0) / metrics.get(
            "total_relations", 1
        )
        score *= 1.0 - low_conf_ratio * 0.5

        # Invalid relation penalty
        invalid_ratio = metrics.get("invalid_relations", 0) / metrics.get(
            "total_relations", 1
        )
        score *= 1.0 - invalid_ratio * 0.7

        # Average confidence factor
        avg_confidence = metrics.get("average_confidence", 0.0)
        score *= 0.5 + avg_confidence * 0.5

        return max(0.0, min(1.0, score))

    def filter_by_confidence(
        self, entities: List[Entity], min_confidence: Optional[float] = None
    ) -> List[Entity]:
        """
        Filter entities by confidence.

        Args:
            entities: List of entities
            min_confidence: Minimum confidence (uses default if None)

        Returns:
            list: Filtered entities (entities with unknown confidence pass)
        """
        threshold = (
            min_confidence if min_confidence is not None else self.min_confidence
        )
        return [
            e
            for e in entities
            if meets_confidence_threshold(e.confidence, threshold)
        ]

    def filter_relations_by_confidence(
        self, relations: List[Relation], min_confidence: Optional[float] = None
    ) -> List[Relation]:
        """
        Filter relations by confidence.

        Args:
            relations: List of relations
            min_confidence: Minimum confidence (uses default if None)

        Returns:
            list: Filtered relations
        """
        threshold = (
            min_confidence if min_confidence is not None else self.min_confidence
        )
        return [r for r in relations if r.confidence >= threshold]
