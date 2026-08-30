"""
Named Entity Recognition Module

This module provides comprehensive named entity recognition capabilities for
extracting and classifying entities from text with confidence scoring and
custom type support. Uses NERExtractor internally with method parameter support.

Supported Methods (passed to NERExtractor):
    - "pattern": Pattern-based extraction using simple regex patterns
    - "regex": Advanced regex-based extraction with custom patterns
    - "rules": Rule-based extraction using linguistic rules
    - "ml": ML-based extraction using spaCy (default)
    - "huggingface": Custom HuggingFace NER models
    - "llm": LLM-based extraction using various providers (OpenAI, Gemini, Groq, etc.)

Algorithms Used:
    - Entity Classification: Rule-based and ML-based entity type classification
    - Confidence Scoring: Statistical and model-based confidence calculation
    - Entity Disambiguation: Context-aware entity disambiguation algorithms
    - Batch Processing: Parallel and sequential batch processing algorithms
    - Custom Entity Detection: Pattern-based custom entity type detection

Key Features:
    - Multi-type entity recognition (PERSON, ORG, GPE, DATE, etc.)
    - Entity classification and categorization
    - Entity confidence scoring
    - Custom entity type support
    - Batch entity processing
    - Entity disambiguation

Main Classes:
    - NamedEntityRecognizer: Main NER coordinator
    - EntityClassifier: Entity classification engine
    - EntityConfidenceScorer: Confidence scoring system
    - CustomEntityDetector: Custom entity detection

Example Usage:
    >>> from semantica.semantic_extract import NamedEntityRecognizer
    >>> ner = NamedEntityRecognizer()
    >>> entities = ner.extract_entities("Steve Jobs founded Apple in 1976.")
    >>> classified = ner.classify_entities(entities)
    >>> scored = ner.score_confidence(entities)

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .ner_extractor import Entity, NERExtractor
from .types import CONFIDENCE_SOURCE_HEURISTIC, CONFIDENCE_SOURCE_KEY


class NamedEntityRecognizer:
    """
    Named entity recognition handler.

    • Extracts named entities from text
    • Classifies entities by type and category
    • Provides confidence scores for entities
    • Supports custom entity types
    • Handles multiple languages and domains
    • Processes batch text collections
    """
    def __init__(
        self,
        methods: Optional[List[str]] = None,
        confidence_threshold: float = 0.5,
        merge_overlapping: bool = True,
        include_standard_types: bool = True,
        method=None,
        config=None,
        **kwargs
    ):
        """
        Initialize named entity recognizer.

        Args:
            methods: Extraction methods to use (e.g., ["spacy", "rule-based"])
            confidence_threshold: Minimum confidence score (0.0-1.0)
            merge_overlapping: Whether to merge overlapping entities
            include_standard_types: Include standard types (Person, Org, Location)
            method: Extraction method(s) - passed to NERExtractor (legacy)
            config: Legacy config dict (deprecated, use kwargs)
            **kwargs: Additional configuration options passed to NERExtractor
        """
        self.logger = get_logger("named_entity_recognizer")
        self.config = config or {}
        self.config.update(kwargs)
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Store parameters
        self.methods = methods or ["spacy"]
        self.confidence_threshold = confidence_threshold
        self.merge_overlapping = merge_overlapping
        self.include_standard_types = include_standard_types

        # Use NERExtractor for actual extraction
        ner_config = self.config.get("ner", {})
        ner_config["confidence_threshold"] = confidence_threshold
        ner_config["min_confidence"] = confidence_threshold
        ner_config["merge_overlapping"] = merge_overlapping
        if method is not None:
            ner_config["method"] = method
        elif methods:
            ner_config["method"] = methods[0] if len(methods) == 1 else methods
        self.ner_extractor = NERExtractor(**ner_config, **self.config)
        self.entity_classifier = EntityClassifier(**self.config.get("classifier", {}))
        self.confidence_scorer = EntityConfidenceScorer(**self.config.get("scorer", {}))


    def extract_entities(self, text: str, **options) -> List[Entity]:
        """
        Extract named entities from text.

        Args:
            text: Input text
            **options: Extraction options

        Returns:
            list: List of extracted entities
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="semantic_extract",
            submodule="NamedEntityRecognizer",
            message="Extracting named entities",
        )

        try:
            entities = self.ner_extractor.extract_entities(text, **options)
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Extracted {len(entities)} entities",
            )
            return entities
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def classify_entities(
        self, entities: List[Entity], **context
    ) -> Dict[str, List[Entity]]:
        """
        Classify entities by type and category.

        Args:
            entities: List of entities
            **context: Context information

        Returns:
            dict: Entities grouped by type
        """
        return self.entity_classifier.classify_entities(entities, **context)

    def score_confidence(self, entities: List[Entity], **options) -> List[Entity]:
        """
        Calculate confidence scores for entities.

        Args:
            entities: List of entities
            **options: Scoring options

        Returns:
            list: Entities with confidence scores
        """
        return self.confidence_scorer.score_entities(entities, **options)

    def process_batch(self, texts: List[str], **options) -> List[List[Entity]]:
        """
        Process multiple texts for entity extraction.

        Args:
            texts: List of input texts
            **options: Processing options

        Returns:
            list: List of entity lists for each text
        """
        return self.ner_extractor.extract_entities_batch(texts, **options)


class EntityClassifier:
    """Entity classification engine."""

    def __init__(self, **config):
        """Initialize entity classifier."""
        self.logger = get_logger("entity_classifier")
        self.config = config

        # Entity type mappings
        self.type_hierarchy = {
            "PERSON": ["PERSON", "PER"],
            "ORG": ["ORG", "ORGANIZATION"],
            "GPE": ["GPE", "LOCATION", "LOC"],
            "DATE": ["DATE", "TIME"],
            "MONEY": ["MONEY", "CURRENCY"],
            "PERCENT": ["PERCENT", "PERCENTAGE"],
        }

    def classify_entity_type(self, entity: Entity, **context) -> str:
        """
        Classify entity by type.

        Args:
            entity: Entity to classify
            **context: Context information

        Returns:
            str: Entity type
        """
        # Normalize entity type
        label = entity.label.upper()

        # Check type hierarchy
        for canonical_type, variants in self.type_hierarchy.items():
            if label in variants:
                return canonical_type

        return label

    def disambiguate_entity(
        self, entity: Entity, candidates: List[Entity], **context
    ) -> Optional[Entity]:
        """
        Disambiguate entity among candidates.

        Args:
            entity: Entity to disambiguate
            candidates: Candidate entities
            **context: Context information

        Returns:
            Entity: Best matching entity or None
        """
        if not candidates:
            return None

        # Simple disambiguation by type match
        entity_type = entity.label
        matching = [c for c in candidates if c.label == entity_type]

        if matching:
            # Return first match with highest confidence; unknown (None)
            # must not outrank measured scores
            return max(
                matching,
                key=lambda e: e.confidence if e.confidence is not None else -1.0,
            )

        return candidates[0] if candidates else None

    def classify_entities(
        self, entities: List[Entity], **context
    ) -> Dict[str, List[Entity]]:
        """
        Classify entities by type.

        Args:
            entities: List of entities
            **context: Context information

        Returns:
            dict: Entities grouped by type
        """
        classified = {}
        for entity in entities:
            entity_type = self.classify_entity_type(entity, **context)
            if entity_type not in classified:
                classified[entity_type] = []
            classified[entity_type].append(entity)

        return classified


class EntityConfidenceScorer:
    """Confidence scoring system."""

    def __init__(self, **config):
        """Initialize confidence scorer."""
        self.logger = get_logger("entity_confidence_scorer")
        self.config = config

    def score_entities(self, entities: List[Entity], **options) -> List[Entity]:
        """
        Calculate confidence scores for entities.

        Args:
            entities: List of entities
            **options: Scoring options

        Returns:
            list: Entities with updated confidence scores

        Note:
            Only entities without a confidence measurement (``None``) are
            scored; a score supplied by an extraction backend — including a
            genuine 1.0 — is preserved.
        """
        for entity in entities:
            if entity.confidence is None:
                entity.confidence = self._calculate_confidence(entity, **options)
                if entity.metadata is None:
                    entity.metadata = {}
                entity.metadata[CONFIDENCE_SOURCE_KEY] = (
                    CONFIDENCE_SOURCE_HEURISTIC
                )

        return entities

    def _calculate_confidence(self, entity: Entity, **options) -> float:
        """
        Calculate confidence score for entity.

        Args:
            entity: Entity to score
            **options: Scoring options

        Returns:
            float: Confidence score (0-1)
        """
        score = 1.0

        # Length-based scoring
        text_length = len(entity.text)
        if text_length < 2:
            score *= 0.7
        elif text_length > 50:
            score *= 0.9

        # Capitalization check (for PERSON, ORG)
        if entity.label in ["PERSON", "ORG", "GPE"]:
            if not entity.text[0].isupper():
                score *= 0.8

        # Type-specific scoring
        if entity.label == "DATE":
            # Check if looks like date
            if any(char.isdigit() for char in entity.text):
                score *= 1.1  # Boost for date-like patterns

        return min(1.0, max(0.0, score))


class CustomEntityDetector:
    """Custom entity detection."""

    def __init__(self, **config):
        """Initialize custom entity detector."""
        self.logger = get_logger("custom_entity_detector")
        self.config = config

        self.custom_patterns = config.get("patterns", {})

    def detect_custom_entities(self, text: str, entity_type: str) -> List[Entity]:
        """
        Detect custom entities using patterns.

        Args:
            text: Input text
            entity_type: Custom entity type

        Returns:
            list: List of detected entities
        """
        entities = []

        if entity_type in self.custom_patterns:
            import re

            pattern = self.custom_patterns[entity_type]

            for match in re.finditer(pattern, text):
                entities.append(
                    Entity(
                        text=match.group(0),
                        label=entity_type,
                        start_char=match.start(),
                        end_char=match.end(),
                        confidence=0.8,
                        metadata={"extraction_method": "custom_pattern"},
                    )
                )

        return entities
