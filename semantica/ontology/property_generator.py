"""
Property Generation Module

This module provides property inference and generation for ontology classes and
relationships. It analyzes entity attributes and relationships to infer object
and data properties with appropriate domains, ranges, and types.

Key Features:
    - Property inference from data patterns
    - Relationship property generation
    - Property type inference and validation
    - Domain and range specification
    - Property hierarchy management
    - Multi-language property support
    - Automatic XSD type detection

Main Classes:
    - PropertyGenerator: Generator for ontology properties

Example Usage:
    >>> from semantica.ontology import PropertyGenerator
    >>> generator = PropertyGenerator()
    >>> properties = generator.infer_properties(entities, relationships, classes)
    >>> validation = generator.validate_properties(properties)

Author: Semantica Contributors
License: MIT
"""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .naming_conventions import NamingConventions


class PropertyGenerator:
    """
    Property generation engine for ontologies.

    • Property inference from data patterns
    • Relationship property generation
    • Property type inference and validation
    • Domain and range specification
    • Property hierarchy management
    • Multi-language property support
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize property generator.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("property_generator")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.naming_conventions = NamingConventions(**self.config)

    def infer_properties(
        self,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        classes: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Infer properties from entities and relationships.

        Args:
            entities: List of entity dictionaries
            relationships: List of relationship dictionaries
            classes: List of class definitions
            **options: Additional options

        Returns:
            List of inferred property definitions
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="ontology",
            submodule="PropertyGenerator",
            message=f"Inferring properties from {len(entities)} entities and {len(relationships)} relationships",
        )
        
        # Merge config into options
        for key, value in self.config.items():
            if key not in options:
                options[key] = value

        try:
            properties = []

            # Infer object properties from relationships
            self.progress_tracker.update_tracking(
                tracking_id, message="Inferring object properties from relationships..."
            )
            object_properties = self._infer_object_properties(
                relationships, classes, **options
            )
            properties.extend(object_properties)

            # Infer data properties from entity attributes
            self.progress_tracker.update_tracking(
                tracking_id, message="Inferring data properties from entities..."
            )
            data_properties = self._infer_data_properties(entities, classes, **options)
            properties.extend(data_properties)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Inferred {len(properties)} properties ({len(object_properties)} object, {len(data_properties)} data)",
            )
            return properties

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _infer_object_properties(
        self,
        relationships: List[Dict[str, Any]],
        classes: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        """Infer object properties from relationships."""
        # Group relationships by type
        rel_types = defaultdict(list)
        for rel in relationships:
            rel_type = rel.get("type") or rel.get("relationship_type", "relatedTo")
            rel_types[rel_type].append(rel)

        # Create class map
        class_map = {cls["name"]: cls for cls in classes}

        properties = []
        for rel_type, rels in rel_types.items():
            if len(rels) >= options.get("min_occurrences", 2):
                # Infer domain and range
                domains = set()
                ranges = set()

                for rel in rels:
                    source_type = rel.get(
                        "source_type"
                    ) or self._infer_class_from_entity(rel.get("source_id"), classes)
                    target_type = rel.get(
                        "target_type"
                    ) or self._infer_class_from_entity(rel.get("target_id"), classes)

                    if source_type:
                        domains.add(source_type)
                    if target_type:
                        ranges.add(target_type)

                # Normalize property name
                prop_name = self.naming_conventions.normalize_property_name(
                    rel_type, "object"
                )

                property_def = {
                    "name": prop_name,
                    "type": "object",
                    "uri": options.get("namespace_manager", None).generate_property_iri(
                        prop_name
                    )
                    if options.get("namespace_manager")
                    else None,
                    "label": prop_name,
                    "comment": f"Object property representing {rel_type} relationships",
                    "domain": list(domains) if domains else ["owl:Thing"],
                    "range": list(ranges) if ranges else ["owl:Thing"],
                    "metadata": {
                        "inferred_from": rel_type,
                        "occurrence_count": len(rels),
                    },
                }

                properties.append(property_def)

        return properties

    def _infer_data_properties(
        self, entities: List[Dict[str, Any]], classes: List[Dict[str, Any]], **options
    ) -> List[Dict[str, Any]]:
        """Infer data properties from entity attributes."""
        # Group entities by their inferred class so normalized class names remain
        # aligned with the class definitions emitted by ClassInferrer.
        class_entities = defaultdict(list)
        class_lookup = self._build_class_type_lookup(classes)
        for entity in entities:
            entity_type = entity.get("type") or entity.get("entity_type", "Entity")
            class_def = self._find_class_for_entity_type(entity_type, class_lookup)
            if not class_def:
                continue
            class_name = class_def["name"]
            class_entities[class_name].append(entity)

        # Extract data properties for each class
        properties = []

        for class_name, type_entities in class_entities.items():
            # Extract data properties
            data_props = self._extract_data_properties(type_entities)

            for prop_name, prop_type in data_props.items():
                # Normalize property name
                normalized_name = self.naming_conventions.normalize_property_name(
                    prop_name, "data"
                )

                property_def = {
                    "name": normalized_name,
                    "type": "data",
                    "uri": options.get("namespace_manager", None).generate_property_iri(
                        normalized_name
                    )
                    if options.get("namespace_manager")
                    else None,
                    "label": normalized_name,
                    "comment": f"Data property for {prop_name}",
                    "domain": [class_name],
                    "range": prop_type,
                    "metadata": {"inferred_from": prop_name},
                }

                properties.append(property_def)

        return properties

    def _build_class_type_lookup(
        self, classes: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Build a lookup for raw, normalized, and recorded source type names."""
        lookup: Dict[str, Dict[str, Any]] = {}
        for class_def in classes:
            class_name = class_def.get("name")
            if class_name:
                lookup.setdefault(str(class_name), class_def)
                lookup.setdefault(
                    self.naming_conventions.normalize_class_name(str(class_name)),
                    class_def,
                )

            inferred_from = class_def.get("metadata", {}).get("inferred_from")
            if inferred_from is not None:
                lookup.setdefault(str(inferred_from), class_def)
                lookup.setdefault(
                    self.naming_conventions.normalize_class_name(str(inferred_from)),
                    class_def,
                )

        return lookup

    def _find_class_for_entity_type(
        self, entity_type: Any, class_lookup: Dict[str, Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find a class using the precomputed type lookup."""
        raw_type = str(entity_type)
        normalized_type = self.naming_conventions.normalize_class_name(raw_type)
        return class_lookup.get(raw_type) or class_lookup.get(normalized_type)

    def _extract_data_properties(
        self, entities: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Extract data properties from entities."""
        properties = {}

        for entity in entities:
            for key, value in entity.items():
                if key in ["id", "type", "entity_type", "text", "label", "confidence"]:
                    continue

                # Infer type
                prop_type = self._infer_property_type(value)

                if key not in properties:
                    properties[key] = prop_type
                elif properties[key] != prop_type:
                    # Use more general type
                    properties[key] = self._get_more_general_type(
                        properties[key], prop_type
                    )

        return properties

    def _infer_property_type(self, value: Any) -> str:
        """Infer property type from value."""
        if isinstance(value, bool):
            return "xsd:boolean"
        elif isinstance(value, int):
            return "xsd:integer"
        elif isinstance(value, float):
            return "xsd:double"
        elif isinstance(value, str):
            # Check if it's a date
            if self._is_date(value):
                return "xsd:date"
            elif self._is_datetime(value):
                return "xsd:dateTime"
            else:
                return "xsd:string"
        else:
            return "xsd:string"

    def _is_date(self, value: str) -> bool:
        """Check if value is a date."""
        import re

        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"\d{2}-\d{2}-\d{4}",
        ]
        return any(re.match(pattern, value) for pattern in date_patterns)

    def _is_datetime(self, value: str) -> bool:
        """Check if value is a datetime."""
        import re

        datetime_patterns = [
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
        ]
        return any(re.search(pattern, value) for pattern in datetime_patterns)

    def _get_more_general_type(self, type1: str, type2: str) -> str:
        """Get more general type between two types."""
        # Type hierarchy
        hierarchy = {
            "xsd:boolean": 0,
            "xsd:integer": 1,
            "xsd:double": 2,
            "xsd:date": 3,
            "xsd:dateTime": 4,
            "xsd:string": 5,
        }

        level1 = hierarchy.get(type1, 5)
        level2 = hierarchy.get(type2, 5)

        return type1 if level1 >= level2 else type2

    def _infer_class_from_entity(
        self, entity_id: str, classes: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Infer class from entity ID (heuristic)."""
        # This is a placeholder - in practice, you'd look up the entity
        return None

    def infer_domains_and_ranges(
        self, properties: List[Dict[str, Any]], classes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Infer property domains and ranges.

        Args:
            properties: List of property definitions
            classes: List of class definitions

        Returns:
            Properties with inferred domains and ranges
        """
        class_map = {cls["name"]: cls for cls in classes}

        for prop in properties:
            if "domain" not in prop or not prop["domain"]:
                prop["domain"] = ["owl:Thing"]

            if prop["type"] == "object" and ("range" not in prop or not prop["range"]):
                prop["range"] = ["owl:Thing"]

        return properties

    def validate_properties(
        self, properties: List[Dict[str, Any]], **criteria
    ) -> Dict[str, Any]:
        """
        Validate inferred properties.

        Args:
            properties: List of property definitions
            **criteria: Validation criteria

        Returns:
            Validation results
        """
        errors = []
        warnings = []

        # Check for duplicate property names
        prop_names = [prop["name"] for prop in properties]
        duplicates = [name for name, count in Counter(prop_names).items() if count > 1]

        if duplicates:
            errors.append(f"Duplicate property names found: {duplicates}")

        # Validate naming conventions
        for prop in properties:
            prop_type = prop.get("type", "object")
            is_valid, suggestion = self.naming_conventions.validate_property_name(
                prop["name"], prop_type
            )
            if not is_valid:
                warnings.append(
                    f"Property '{prop['name']}' doesn't follow conventions. Suggested: {suggestion}"
                )

        # Validate domains and ranges
        for prop in properties:
            if prop["type"] == "object":
                if "range" not in prop or not prop["range"]:
                    errors.append(f"Object property '{prop['name']}' missing range")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}
