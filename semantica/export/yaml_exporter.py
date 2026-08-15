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

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ValidationError
from ..utils.helpers import (
    _require_mapping,
    _require_nothing_dropped,
    _require_recognized_keys,
    ensure_directory,
    normalize_graph_payload,
)
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Keys YAMLSchemaExporter.export_ontology_schema reads. Graph payloads use the
# recognized set owned by normalize_graph_payload() instead; schemas are a
# separate vocabulary with no aliasing, so the set lives here.
_SCHEMA_KEYS = (
    "classes",
    "properties",
    "namespaces",
    "uri",
    "title",
    "description",
    "version",
)


def _require_usable_schema(ontology: Mapping) -> None:
    """Reject a schema mapping this exporter cannot read.

    Two ways an ontology mapping produces an empty file: it shares no key with
    the recognized set at all, or it names a recognized key that is empty
    while the real records sit under a key this exporter does not read
    (``{"classes": [], "nodes": [...]}``). Both are refused, using the same
    checks the graph payloads go through, so the two vocabularies cannot drift
    apart in what they consider a silent-empty export.

    An empty mapping is allowed through: it carries nothing that could be
    lost, and an empty export is a legitimate result.

    Note the deliberate split in exception types, which the codebase already
    makes: a wrong *type* cannot be exported at all and raises
    ProcessingError, matching ``Neo4jCSVExporter._normalize_graph``; a mapping
    whose *contents* are unusable raises ValidationError, matching
    ``normalize_graph_payload``.

    Args:
        ontology: Mapping already checked by :func:`_require_mapping`.

    Raises:
        ValidationError: if the mapping shares no key with ``_SCHEMA_KEYS``,
            or resolves to nothing while an unread key still holds records.
    """
    _require_recognized_keys(ontology, _SCHEMA_KEYS, what="Ontology schema")
    # Only non-empty list/tuple values from recognized schema keys count as
    # evidence that records survived export.  Scalar metadata fields such as
    # 'uri', 'title', 'description', and 'version' are truthy strings, but
    # their presence does not mean the caller's record collections were
    # exported -- passing them as ``resolved`` would let any scalar value
    # short-circuit the dropped-records check and silently discard a list
    # under an unread key alongside e.g. {"version": "1.0", "nodes": [...]}.
    resolved = [
        v
        for key in _SCHEMA_KEYS
        for v in (ontology.get(key),)
        if isinstance(v, (list, tuple)) and v
    ]
    _require_nothing_dropped(
        ontology,
        _SCHEMA_KEYS,
        resolved,
        what="Ontology schema",
    )


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

    def export_semantic_network(
        self, semantic_network: Dict[str, Any], **options
    ) -> str:
        """
        Export semantic network to YAML string.

        This method converts a semantic network (entities, relationships, triplets)
        to YAML format with metadata and provenance information.

        Args:
            semantic_network: Semantic network dictionary containing:
                - entities: List of entity dictionaries (alias: 'nodes')
                - relationships: List of relationship dictionaries
                  (alias: 'edges')
                - triplets: List of triplet dictionaries (optional)
                - metadata: Metadata dictionary (optional)

                Key resolution is delegated to
                :func:`~semantica.utils.helpers.normalize_graph_payload`, so
                ``ContextGraph.to_dict()`` output ('nodes'/'edges') exports
                directly.
            **options: Additional export options (unused)

        Returns:
            String containing YAML representation of semantic network

        Raises:
            ProcessingError: if ``semantic_network`` is not a mapping. A bare
                list of records cannot be exported here because this format
                distinguishes entities, relationships, and triplets, and
                guessing which one a list represents would silently mislabel
                it.
            ValidationError: if the mapping carries both spellings of a
                collection with different contents; if it is non-empty and
                shares no key with the recognized set; or if it resolves to
                nothing while an unread key still holds records
                (``{"entities": [], "data": [...]}``). Each previously
                serialized to a file with every collection empty while the log
                reported success. An empty mapping is still accepted -- it has
                no records to lose. Note that 'metadata' alone is not a
                recognized key: an ``export_json`` envelope carries one, and
                accepting it would readmit the silent-empty export it is the
                most likely source of.

        Example:
            >>> network = {
            ...     "entities": [...],
            ...     "relationships": [...],
            ...     "triplets": [...]
            ... }
            >>> yaml_str = exporter.export_semantic_network(network)
        """
        _require_mapping(semantic_network, ("entities", "relationships", "triplets"))

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
            records = normalize_graph_payload(semantic_network)
            yaml_data = {
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "version": "1.0",
                    **semantic_network.get("metadata", {}),
                },
                **records,
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
                message="Serialized semantic network to YAML",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def export(
        self, data: Dict[str, Any], file_path: Union[str, Path], **options
    ) -> None:
        """
        Export data to YAML file.

        Args:
            data: Data to export
            file_path: Output file path
            **options: Additional options

        Raises:
            ProcessingError: if ``data`` is not a mapping.
            ValidationError: on the mappings :meth:`export_semantic_network`
                rejects. Serialization runs before the output directory is
                created, so a rejected export leaves nothing behind.
            OSError: if the file cannot be written. The write is tracked
                separately from serialization, so no progress entry reports a
                completed export until the bytes are on disk.
        """
        file_path = Path(file_path)
        yaml_content = self.export_semantic_network(data, **options)

        # Serialization reports its own completion, but it says nothing about
        # the file: without this second span, a failing write would leave the
        # tracker showing a completed export and no output.
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="export",
            submodule="SemanticNetworkYAMLExporter",
            message=f"Writing YAML to {file_path}",
        )

        try:
            ensure_directory(file_path.parent)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            self.logger.info(f"Exported YAML to: {file_path}")
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Exported YAML to: {file_path}",
            )

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

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

        Args:
            extracted_data: Semantic network mapping, read through
                :func:`~semantica.utils.helpers.normalize_graph_payload` on
                the same terms as :meth:`export_semantic_network`.
            pipeline_stage: Stage number recorded in the output.
            **options: Additional export options (unused)

        Returns:
            Pipeline-ready YAML string.

        Raises:
            ProcessingError: if ``extracted_data`` is not a mapping.
            ValidationError: on the same mappings as
                :meth:`export_semantic_network` -- this method built its
                nested semantic network from the same defaulted lookups and
                so had the same silent-empty failure.
        """
        _require_mapping(extracted_data, ("entities", "relationships", "triplets"))

        semantic_network = normalize_graph_payload(extracted_data)
        yaml_data = {
            "pipeline_stage": pipeline_stage,
            "metadata": {
                "extracted_at": datetime.now().isoformat(),
                **extracted_data.get("metadata", {}),
            },
            "semantic_network": semantic_network,
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

    def export_ontology_schema(self, ontology: Dict[str, Any], **options) -> str:
        """
        Export ontology schema to YAML.

        • Format classes and properties
        • Include hierarchies and constraints
        • Structure for easy editing
        • Return YAML schema

        Args:
            ontology: Ontology mapping keyed by any of 'classes',
                'properties', 'namespaces', 'uri', 'title', 'description',
                'version'.
            **options: Additional export options (unused)

        Returns:
            YAML schema string.

        Raises:
            ProcessingError: if ``ontology`` is not a mapping.
            ValidationError: if ``ontology`` is a non-empty mapping sharing
                no key with the recognized set, or resolves to nothing while
                an unread key still holds records
                (``{"classes": [], "nodes": [...]}``) -- each previously
                produced a file with empty 'classes', 'properties' and
                'namespaces' and no indication anything was dropped. An empty
                mapping is still accepted.
        """
        _require_mapping(ontology, ("classes", "properties"))
        _require_usable_schema(ontology)

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
