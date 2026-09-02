"""
Class Inference Module

This module provides automatic class discovery and inference from extracted entities
and data patterns. It analyzes entity types, properties, and relationships to infer
ontology classes with proper naming conventions and hierarchical structures.

Key Features:
    - Automatic class discovery from entities
    - Pattern-based class inference
    - Hierarchical class structure building
    - Class validation and consistency checking
    - Multi-domain class support
    - Circular hierarchy detection
    - Performance optimization

Main Classes:
    - ClassInferrer: Class inference engine for ontology generation

Example Usage:
    >>> from semantica.ontology import ClassInferrer
    >>> inferrer = ClassInferrer(min_occurrences=2)
    >>> classes = inferrer.infer_classes(entities, build_hierarchy=True)
    >>> hierarchical = inferrer.build_class_hierarchy(classes)
    >>> validation = inferrer.validate_classes(classes)

Author: Semantica Contributors
License: MIT
"""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .naming_conventions import NamingConventions


class ClassInferrer:
    """
    Class inference engine for ontology generation.

    This class provides automatic discovery and inference of ontology classes from
    entity data, building hierarchical structures and validating class definitions.

    Features:
        - Automatic class discovery from entities
        - Pattern-based class inference
        - Hierarchical class structure building
        - Class validation and consistency checking
        - Multi-domain class support
        - Circular hierarchy detection
        - Performance optimization

    Example:
        ```python
        inferrer = ClassInferrer(min_occurrences=2, similarity_threshold=0.8)
        classes = inferrer.infer_classes(entities)
        ```
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize class inferrer.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - min_occurrences: Minimum occurrences for class inference (default: 2)
                - similarity_threshold: Similarity threshold for class merging (default: 0.8)
                - namespace_manager: Optional namespace manager instance

        Example:
            ```python
            inferrer = ClassInferrer(
                min_occurrences=3,
                similarity_threshold=0.85
            )
            ```
        """
        self.logger = get_logger("class_inferrer")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.naming_conventions = NamingConventions(**self.config)
        self.min_occurrences = self.config.get("min_occurrences", 2)
        self.similarity_threshold = self.config.get("similarity_threshold", 0.8)

    def infer_classes(
        self, entities: List[Dict[str, Any]], **options
    ) -> List[Dict[str, Any]]:
        """
        Infer classes from entities.

        Analyzes a list of entities and infers ontology classes based on entity types
        and common properties. Groups entities by type and creates class definitions
        for types that meet the minimum occurrence threshold.

        Args:
            entities: List of entity dictionaries, each containing at least:
                - type or entity_type: Entity type name
                - Additional properties that will be analyzed
            **options: Additional options:
                - build_hierarchy: Whether to build class hierarchy (default: True)
                - namespace_manager: Optional namespace manager for URI generation

        Returns:
            List of inferred class definition dictionaries, each containing:
                - name: Normalized class name
                - uri: Class URI (if namespace_manager provided)
                - label: Class label
                - comment: Class description
                - properties: List of common property names
                - entity_count: Number of entities of this type
                - metadata: Additional metadata

        Example:
            ```python
            entities = [
                {"type": "Person", "name": "John", "age": 30},
                {"type": "Person", "name": "Jane", "age": 25},
                {"type": "Organization", "name": "Acme Corp"}
            ]

            classes = inferrer.infer_classes(entities, build_hierarchy=True)
            ```
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="ontology",
            submodule="ClassInferrer",
            message=f"Inferring classes from {len(entities)} entities",
        )

        try:
            self.progress_tracker.update_tracking(
                tracking_id, message="Grouping entities by type..."
            )
            # Group entities by type
            entity_types = defaultdict(list)
            for entity in entities:
                entity_type = entity.get("type") or entity.get("entity_type", "Entity")
                entity_types[entity_type].append(entity)

            normalized_types = defaultdict(list)
            for entity_type, type_entities in entity_types.items():
                if len(type_entities) >= self.min_occurrences:
                    normalized_name = self.naming_conventions.normalize_class_name(
                        str(entity_type)
                    )
                    normalized_types[normalized_name].append(str(entity_type))

            collisions = {
                normalized_name: source_types
                for normalized_name, source_types in normalized_types.items()
                if len(source_types) > 1
            }
            if collisions:
                raise ValidationError(
                    "Entity types normalize to duplicate class names; "
                    "rename the source types or provide an explicit mapping.",
                    validation_context={"normalized_type_collisions": collisions},
                )

            # Infer classes from entity types
            self.progress_tracker.update_tracking(
                tracking_id,
                message=f"Inferring classes from {len(entity_types)} entity types...",
            )
            classes = []
            for entity_type, type_entities in entity_types.items():
                if len(type_entities) >= self.min_occurrences:
                    class_def = self._create_class_from_entities(
                        entity_type, type_entities, **options
                    )
                    classes.append(class_def)

            # Build hierarchy
            if options.get("build_hierarchy", True):
                self.progress_tracker.update_tracking(
                    tracking_id, message="Building class hierarchy..."
                )
                classes = self.build_class_hierarchy(classes, **options)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Inferred {len(classes)} classes",
            )
            return classes

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def build_class_hierarchy(
        self, classes: List[Dict[str, Any]], **options
    ) -> List[Dict[str, Any]]:
        """
        Build class hierarchy from classes.

        Analyzes class names and relationships to infer parent-child relationships,
        building a taxonomic hierarchy. Uses naming patterns and common parent classes
        to establish subClassOf relationships.

        Args:
            classes: List of class definition dictionaries
            **options: Additional options (currently unused)

        Returns:
            List of class definitions with hierarchy information added:
                - subClassOf: Parent class name (if found)
                - parent: Alias for subClassOf

        Example:
            ```python
            classes = [
                {"name": "Person"},
                {"name": "Employee"},
                {"name": "Manager"}
            ]

            hierarchical = inferrer.build_class_hierarchy(classes)
            # Manager may have subClassOf: "Employee"
            ```
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="ontology",
            submodule="ClassInferrer",
            message=f"Building hierarchy for {len(classes)} classes",
        )

        try:
            self.progress_tracker.update_tracking(
                tracking_id, message="Creating class map..."
            )
            # Create class map
            class_map = {cls["name"]: cls for cls in classes}

            # Infer parent-child relationships
            self.progress_tracker.update_tracking(
                tracking_id, message="Inferring parent-child relationships..."
            )
            for cls in classes:
                if "parent" not in cls:
                    # Try to find parent based on naming patterns
                    parent = self._find_parent_class(cls["name"], class_map)
                    if parent:
                        cls["subClassOf"] = parent
                        cls["parent"] = parent

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Built hierarchy for {len(classes)} classes",
            )
            return classes

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _create_class_from_entities(
        self, entity_type: str, entities: List[Dict[str, Any]], **options
    ) -> Dict[str, Any]:
        """Create class definition from entities."""
        # Normalize class name
        class_name = self.naming_conventions.normalize_class_name(entity_type)

        # Extract common properties
        properties = self._extract_common_properties(entities)

        # Create class definition
        class_def = {
            "name": class_name,
            "uri": options.get("namespace_manager", None).generate_class_iri(class_name)
            if options.get("namespace_manager")
            else None,
            "label": class_name,
            "comment": f"Class representing {class_name.lower()} entities",
            "properties": properties,
            "entity_count": len(entities),
            "metadata": {"inferred_from": entity_type, "inferred_count": len(entities)},
        }

        return class_def

    def _extract_common_properties(self, entities: List[Dict[str, Any]]) -> List[str]:
        """Extract common properties from entities."""
        # Count property occurrences
        property_counts = Counter()

        for entity in entities:
            # Count properties in entity
            for key in entity.keys():
                if key not in [
                    "id",
                    "type",
                    "entity_type",
                    "text",
                    "label",
                    "confidence",
                ]:
                    property_counts[key] += 1

        # Return properties that appear in at least 50% of entities
        threshold = len(entities) * 0.5
        common_properties = [
            prop for prop, count in property_counts.items() if count >= threshold
        ]

        return common_properties

    def _find_parent_class(
        self, class_name: str, class_map: Dict[str, Dict[str, Any]]
    ) -> Optional[str]:
        """Find parent class based on naming patterns."""
        # Simple heuristic: look for more general class names
        words = class_name.split()

        # Try to find parent by removing words
        for i in range(len(words) - 1, 0, -1):
            parent_candidate = "".join(words[:i])
            if parent_candidate in class_map:
                return parent_candidate

        # Check for common parent classes
        common_parents = ["Entity", "Thing", "Resource"]
        for parent in common_parents:
            if parent in class_map:
                return parent

        return None

    def validate_classes(
        self, classes: List[Dict[str, Any]], **criteria
    ) -> Dict[str, Any]:
        """
        Validate inferred classes.

        Validates class definitions for naming conventions, duplicate names,
        and circular hierarchies. Provides suggestions for improvements.

        Args:
            classes: List of class definition dictionaries
            **criteria: Validation criteria (currently unused)

        Returns:
            Dictionary with validation results:
                - valid: Boolean indicating if validation passed
                - errors: List of error messages
                - warnings: List of warning messages with suggestions

        Example:
            ```python
            validation = inferrer.validate_classes(classes)
            if not validation["valid"]:
                print(f"Errors: {validation['errors']}")
            if validation["warnings"]:
                print(f"Warnings: {validation['warnings']}")
            ```
        """
        errors = []
        warnings = []

        # Check for duplicate class names
        class_names = [cls["name"] for cls in classes]
        duplicates = [name for name, count in Counter(class_names).items() if count > 1]

        if duplicates:
            errors.append(f"Duplicate class names found: {duplicates}")

        # Validate naming conventions
        for cls in classes:
            is_valid, suggestion = self.naming_conventions.validate_class_name(
                cls["name"]
            )
            if not is_valid:
                warnings.append(
                    f"Class '{cls['name']}' doesn't follow conventions. Suggested: {suggestion}"
                )

        # Check for circular hierarchies
        hierarchy_errors = self._check_circular_hierarchy(classes)
        errors.extend(hierarchy_errors)

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def _check_circular_hierarchy(self, classes: List[Dict[str, Any]]) -> List[str]:
        """Check for circular inheritance."""
        errors = []

        # Build parent map
        parent_map = {}
        for cls in classes:
            if "subClassOf" in cls or "parent" in cls:
                parent = cls.get("subClassOf") or cls.get("parent")
                if parent:
                    parent_map[cls["name"]] = parent

        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            if node in parent_map:
                parent = parent_map[node]
                if parent in rec_stack:
                    return True
                if parent not in visited and has_cycle(parent):
                    return True

            rec_stack.remove(node)
            return False

        for cls in classes:
            if cls["name"] not in visited:
                if has_cycle(cls["name"]):
                    errors.append(
                        f"Circular hierarchy detected involving class: {cls['name']}"
                    )

        return errors
