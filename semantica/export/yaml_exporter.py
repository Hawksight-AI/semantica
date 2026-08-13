"""
YAML Exporter Module

This module provides comprehensive YAML export capabilities for the Semantica
framework, enabling human-readable export of semantic networks and ontologies.

Key Features:
    - Semantic network export to YAML
    - Ontology schema export for human editing
    - Pipeline-ready YAML format
    - Entity, relationship, and triplet export
    - Class and property definition export

Example Usage:
    >>> from semantica.export import SemanticNetworkYAMLExporter
    >>> exporter = SemanticNetworkYAMLExporter()
    >>> exporter.export(semantic_network, "network.yaml")
    >>> exporter.export_for_pipeline(extracted_data, pipeline_stage=2)

Author: Semantica Contributors
License: MIT
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import ensure_directory
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class SemanticNetworkYAMLExporter:
    """
    Exports semantic networks to YAML format.

    This class provides YAML export functionality for semantic networks, enabling
    human-readable representation and intermediate processing in ontology
    generation pipelines.

    Part of the 6-stage ontology generation pipeline:
    1. Document parsing
    2. Semantic network extraction (YAML) ← This module
    3. Definition generation
    4. Type mapping
    5. Hierarchy building
    6. TTL export

    Example Usage:
        >>> exporter = SemanticNetworkYAMLExporter()
        >>> exporter.export(semantic_network, "network.yaml")
    """

    def __init__(self, **config):
        """
        Initialize YAML exporter.

        Sets up the exporter with YAML serialization support.

        Args:
            **config: Configuration options (currently unused)

        Raises:
            ImportError: If PyYAML is not installed
        """
        self.logger = get_logger("yaml_exporter")
        self.config = config or {}

        try:
            import yaml

            self.yaml = yaml
        except (ImportError, OSError):
            raise ImportError("PyYAML not installed. Install with: pip install pyyaml")

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug("Semantic network YAML exporter initialized")

    _SEMANTIC_NETWORK_KEYS = ("entities", "relationships", "triplets", "metadata")

    def _normalize_semantic_network(
        self, semantic_network: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        Normalize exporter input to a semantic network dictionary.

        A bare list of records is treated as the entity collection, matching
        the behavior of the JSON and CSV exporters. A dictionary that contains
        none of the recognized keys still exports, but a warning is logged so
        a silently empty export is never mistaken for success.

        Raises:
            ValidationError: If the input is neither a dict nor a list of dicts
        """
        if isinstance(semantic_network, list):
            if not all(isinstance(item, dict) for item in semantic_network):
                raise ValidationError(
                    "YAML export expects a list of dictionaries; "
                    "found a list containing non-dict items",
                    validation_context={"input_type": "list"},
                )
            return {"entities": semantic_network}

        if not isinstance(semantic_network, dict):
            raise ValidationError(
                "YAML export expects a dict or a list of dicts, "
                f"got {type(semantic_network).__name__}",
                validation_context={"input_type": type(semantic_network).__name__},
            )

        if semantic_network and not any(
            key in semantic_network for key in self._SEMANTIC_NETWORK_KEYS
        ):
            self.logger.warning(
                "YAML export input has none of the recognized keys "
                f"{self._SEMANTIC_NETWORK_KEYS}; the exported file will contain "
                "empty entities/relationships/triplets collections"
            )

        return semantic_network

    def export_semantic_network(
        self,
        semantic_network: Union[Dict[str, Any], List[Dict[str, Any]]],
        **options,
    ) -> str:
        """
        Export semantic network to YAML string.

        This method converts a semantic network (entities, relationships, triplets)
        to YAML format with metadata and provenance information.

        Args:
            semantic_network: Semantic network dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - triplets: List of triplet dictionaries (optional)
                - metadata: Metadata dictionary (optional)
                A bare list of entity dictionaries is also accepted and is
                exported as the entities collection.
            **options: Additional export options (unused)

        Returns:
            String containing YAML representation of semantic network

        Example:
            >>> network = {
            ...     "entities": [...],
            ...     "relationships": [...],
            ...     "triplets": [...]
            ... }
            >>> yaml_str = exporter.export_semantic_network(network)
        """
        # Track YAML export
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="export",
            submodule="SemanticNetworkYAMLExporter",
            message="Exporting semantic network to YAML",
        )

        try:
            self.progress_tracker.update_tracking(
                tracking_id, message="Preparing YAML data..."
            )
            semantic_network = self._normalize_semantic_network(semantic_network)
            yaml_data = {
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "version": "1.0",
                    **semantic_network.get("metadata", {}),
                },
                "entities": semantic_network.get("entities", []),
                "relationships": semantic_network.get("relationships", []),
                "triplets": semantic_network.get("triplets", []),
            }

            self.progress_tracker.update_tracking(
                tracking_id, message="Serializing to YAML..."
            )
            result = self.yaml.dump(
                yaml_data, default_flow_style=False, sort_keys=False
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message="Exported semantic network to YAML",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def export(
        self,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
        file_path: Union[str, Path],
        **options,
    ) -> None:
        """
        Export data to YAML file.

        Args:
            data: Data to export
            file_path: Output file path
            **options: Additional options
        """
        file_path = Path(file_path)
        ensure_directory(file_path.parent)

        yaml_content = self.export_semantic_network(data, **options)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        self.logger.info(f"Exported YAML to: {file_path}")

    def export_entities(
        self, entities: List[Dict[str, Any]], include_metadata: bool = True, **options
    ) -> str:
        """
        Export entities to YAML format.

        • Format entity properties
        • Include entity types and labels
        • Add confidence scores
        • Return YAML representation
        """
        yaml_data = {"entities": entities}

        if include_metadata:
            yaml_data["metadata"] = {
                "exported_at": datetime.now().isoformat(),
                "entity_count": len(entities),
            }

        return self.yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

    def export_relationships(
        self,
        relationships: List[Dict[str, Any]],
        include_properties: bool = True,
        **options,
    ) -> str:
        """
        Export relationships to YAML format.

        • Format relationship triplets
        • Include relationship types
        • Add directional information
        • Return YAML representation
        """
        yaml_data = {"relationships": relationships}

        if include_properties:
            yaml_data["metadata"] = {
                "exported_at": datetime.now().isoformat(),
                "relationship_count": len(relationships),
            }

        return self.yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

    def export_triplets(
        self, triplets: List[Dict[str, Any]], include_confidence: bool = True, **options
    ) -> str:
        """
        Export RDF triplets to YAML format.

        • Format subject-predicate-object triplets
        • Include namespace information
        • Add confidence and provenance
        • Return YAML representation
        """
        yaml_data = {
            "triplets": [
                {
                    "subject": t.get("subject") or t.get("s"),
                    "predicate": t.get("predicate") or t.get("p"),
                    "object": t.get("object") or t.get("o"),
                    **(
                        {"confidence": t.get("confidence")}
                        if include_confidence and "confidence" in t
                        else {}
                    ),
                    **(
                        {"provenance": t.get("provenance")} if "provenance" in t else {}
                    ),
                }
                for t in triplets
            ]
        }

        yaml_data["metadata"] = {
            "exported_at": datetime.now().isoformat(),
            "triplet_count": len(triplets),
        }

        return self.yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

    def export_for_pipeline(
        self, extracted_data: Dict[str, Any], pipeline_stage: int = 2, **options
    ) -> str:
        """
        Export in format suitable for ontology generation pipeline.

        • Format for stage 2 (semantic network extraction)
        • Structure for definition generation
        • Include extraction metadata
        • Return pipeline-ready YAML
        """
        yaml_data = {
            "pipeline_stage": pipeline_stage,
            "metadata": {
                "extracted_at": datetime.now().isoformat(),
                **extracted_data.get("metadata", {}),
            },
            "semantic_network": {
                "entities": extracted_data.get("entities", []),
                "relationships": extracted_data.get("relationships", []),
                "triplets": extracted_data.get("triplets", []),
            },
        }

        return self.yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)


class YAMLSchemaExporter:
    """
    Exports ontology schemas to YAML for human editing.

    Enables domain expert refinement by exporting schemas in
    human-readable YAML format.
    """

    def __init__(self, **config):
        """Initialize schema exporter."""
        self.logger = get_logger("yaml_schema_exporter")
        self.config = config or {}

        try:
            import yaml

            self.yaml = yaml
        except (ImportError, OSError):
            raise ImportError("PyYAML not installed. Install with: pip install pyyaml")

    _SCHEMA_KEYS = (
        "uri",
        "title",
        "description",
        "version",
        "classes",
        "properties",
        "namespaces",
    )

    def export_ontology_schema(
        self, ontology: Union[Dict[str, Any], List[Dict[str, Any]]], **options
    ) -> str:
        """
        Export ontology schema to YAML.

        • Format classes and properties
        • Include hierarchies and constraints
        • Structure for easy editing
        • Return YAML schema

        A bare list of class dictionaries is accepted and exported as the
        classes collection.
        """
        if isinstance(ontology, list):
            if not all(isinstance(item, dict) for item in ontology):
                raise ValidationError(
                    "YAML schema export expects a list of dictionaries; "
                    "found a list containing non-dict items",
                    validation_context={"input_type": "list"},
                )
            ontology = {"classes": ontology}
        elif not isinstance(ontology, dict):
            raise ValidationError(
                "YAML schema export expects a dict or a list of dicts, "
                f"got {type(ontology).__name__}",
                validation_context={"input_type": type(ontology).__name__},
            )
        elif ontology and not any(key in ontology for key in self._SCHEMA_KEYS):
            self.logger.warning(
                "YAML schema export input has none of the recognized keys "
                f"{self._SCHEMA_KEYS}; the exported file will contain empty "
                "classes/properties collections"
            )

        yaml_data = {
            "ontology": {
                "uri": ontology.get("uri", ""),
                "title": ontology.get("title", ""),
                "description": ontology.get("description", ""),
                "version": ontology.get("version", "1.0"),
            },
            "classes": ontology.get("classes", []),
            "properties": ontology.get("properties", []),
            "namespaces": ontology.get("namespaces", {}),
        }

        return self.yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

    def export_class_definitions(
        self, classes: List[Dict[str, Any]], include_hierarchy: bool = True, **options
    ) -> str:
        """Export class definitions to YAML."""
        yaml_data = {"classes": classes}

        if include_hierarchy:
            yaml_data["hierarchy"] = self._extract_hierarchy(classes)

        return self.yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

    def export_property_definitions(
        self,
        properties: List[Dict[str, Any]],
        include_domain_range: bool = True,
        **options,
    ) -> str:
        """Export property definitions to YAML."""
        yaml_data = {"properties": properties}

        if include_domain_range:
            yaml_data["domain_range"] = self._extract_domain_range(properties)

        return self.yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

    def _extract_hierarchy(self, classes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract class hierarchy."""
        hierarchy = {}

        for cls in classes:
            class_id = cls.get("id") or cls.get("uri", "")
            parent = cls.get("parent") or cls.get("subClassOf")

            if class_id:
                hierarchy[class_id] = {
                    "label": cls.get("label", ""),
                    "parent": parent,
                    "children": [],
                }

        # Build children relationships
        for class_id, class_info in hierarchy.items():
            parent = class_info.get("parent")
            if parent and parent in hierarchy:
                hierarchy[parent]["children"].append(class_id)

        return hierarchy

    def _extract_domain_range(self, properties: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract property domain and range."""
        domain_range = {}

        for prop in properties:
            prop_id = prop.get("id") or prop.get("uri", "")
            if prop_id:
                domain_range[prop_id] = {
                    "label": prop.get("label", ""),
                    "domain": prop.get("domain", []),
                    "range": prop.get("range", []),
                }

        return domain_range
