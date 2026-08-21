"""
JSON Exporter Module

This module provides comprehensive JSON and JSON-LD export capabilities for the
Semantica framework, enabling structured data export for knowledge graphs and
semantic information.

Key Features:
    - JSON and JSON-LD format export
    - Knowledge graph serialization
    - Entity and relationship export
    - Metadata and provenance tracking
    - Configurable indentation and encoding
    - JSON-LD context management

Example Usage:
    >>> from semantica.export import JSONExporter
    >>> exporter = JSONExporter(indent=2, format="json-ld")
    >>> exporter.export_knowledge_graph(kg, "output.json")
    >>> exporter.export_entities(entities, "entities.json")

Author: Semantica Contributors
License: MIT
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import ensure_directory, utc_now_iso, write_json_file
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .rdf_exporter import SEMANTICA_NS, mint_entity_iri, mint_relationship_iri


class JSONExporter:
    """
    JSON exporter for knowledge graphs and semantic data.

    This class provides comprehensive JSON and JSON-LD export functionality for
    entities, relationships, and knowledge graphs. Supports both standard JSON
    and JSON-LD formats with configurable formatting.

    Features:
        - JSON and JSON-LD format export
        - Knowledge graph serialization
        - Entity and relationship export
        - Metadata and provenance tracking
        - Configurable indentation and encoding
        - JSON-LD context management

    Example Usage:
        >>> exporter = JSONExporter(
        ...     indent=2,
        ...     ensure_ascii=False,
        ...     format="json-ld"
        ... )
        >>> exporter.export_knowledge_graph(kg, "output.json")
    """

    def __init__(
        self,
        indent: int = 2,
        ensure_ascii: bool = False,
        format: str = "json",
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize JSON exporter.

        Sets up the exporter with specified JSON formatting options.

        Args:
            indent: JSON indentation level (default: 2)
            ensure_ascii: Whether to escape non-ASCII characters (default: False)
            format: Export format - 'json' or 'json-ld' (default: 'json')
            config: Optional configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("json_exporter")
        self.config = config or {}
        self.config.update(kwargs)

        # JSON configuration
        self.indent = indent
        self.ensure_ascii = ensure_ascii
        self.format = format

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug(
            f"JSON exporter initialized: indent={indent}, "
            f"ensure_ascii={ensure_ascii}, format={format}"
        )

    def export(
        self,
        data: Any,
        file_path: Union[str, Path],
        format: Optional[str] = None,
        include_metadata: bool = True,
        include_provenance: bool = True,
        **options,
    ) -> None:
        """
        Export data to JSON file.

        This method exports data to JSON or JSON-LD format, with optional
        metadata and provenance information.

        Args:
            data: Data to export (dict, list, or any JSON-serializable value)
            file_path: Output JSON file path
            format: Export format - 'json' or 'json-ld' (default: self.format)
            include_metadata: Whether to include metadata in export (default: True)
            include_provenance: Whether to include provenance information (default: True)
            **options: Additional options passed to conversion methods

        Example:
            >>> exporter.export(
            ...     {"entities": [...], "relationships": [...]},
            ...     "output.json",
            ...     format="json-ld"
            ... )
        """
        # Track JSON export
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="export",
            submodule="JSONExporter",
            message=f"Exporting data to JSON: {file_path}",
        )

        try:
            file_path = Path(file_path)
            ensure_directory(file_path.parent)

            export_format = format or self.format

            self.logger.debug(
                f"Exporting data to JSON ({export_format}): {file_path}, "
                f"include_metadata={include_metadata}, include_provenance={include_provenance}"
            )

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Converting to {export_format} format..."
            )
            # Convert data to appropriate format
            if export_format == "json-ld":
                json_data = self._convert_to_jsonld(
                    data,
                    include_metadata=include_metadata,
                    include_provenance=include_provenance,
                    **options,
                )
            else:
                json_data = self._convert_to_json(
                    data,
                    include_metadata=include_metadata,
                    include_provenance=include_provenance,
                    **options,
                )

            self.progress_tracker.update_tracking(
                tracking_id, message="Writing JSON file..."
            )
            # Write JSON file
            write_json_file(
                json_data, file_path, indent=self.indent, ensure_ascii=self.ensure_ascii
            )

            self.logger.info(f"Exported JSON ({export_format}) to: {file_path}")
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Exported JSON ({export_format}) to: {file_path}",
            )

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def export_knowledge_graph(
        self,
        knowledge_graph: Dict[str, Any],
        file_path: Union[str, Path],
        format: Optional[str] = None,
        **options,
    ) -> None:
        """
        Export knowledge graph to JSON or JSON-LD format.

        This method exports a complete knowledge graph with entities, relationships,
        nodes, edges, and metadata to JSON or JSON-LD format.

        Args:
            knowledge_graph: Knowledge graph dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - nodes: List of node dictionaries (optional)
                - edges: List of edge dictionaries (optional)
                - metadata: Metadata dictionary (optional)
                - statistics: Statistics dictionary (optional)
            file_path: Output JSON file path
            format: Export format - 'json' or 'json-ld' (default: self.format)
            **options: Additional options passed to conversion methods

        Example:
            >>> kg = {
            ...     "entities": [...],
            ...     "relationships": [...],
            ...     "metadata": {...}
            ... }
            >>> exporter.export_knowledge_graph(kg, "kg.json", format="json-ld")
        """
        export_format = format or self.format

        self.logger.debug(f"Exporting knowledge graph to {export_format}: {file_path}")

        # Convert knowledge graph to appropriate format
        if export_format == "json-ld":
            json_data = self._convert_kg_to_jsonld(knowledge_graph, **options)
        else:
            json_data = self._convert_kg_to_json(knowledge_graph, **options)

        # Export using main export method
        self.export(json_data, file_path, format=export_format, **options)

    def export_entities(
        self, entities: List[Dict[str, Any]], file_path: Union[str, Path], **options
    ) -> None:
        """
        Export entities to JSON file.

        This method exports a list of entities to JSON format with JSON-LD context
        and metadata including export timestamp and entity count.

        Args:
            entities: List of entity dictionaries to export
            file_path: Output JSON file path
            **options: Additional options:
                - metadata: Additional metadata to include in export

        Example:
            >>> entities = [
            ...     {"id": "e1", "text": "Entity 1", "type": "PERSON"},
            ...     {"id": "e2", "text": "Entity 2", "type": "ORG"}
            ... ]
            >>> exporter.export_entities(entities, "entities.json")
        """
        if not entities:
            self.logger.warning("No entities provided for export")

        self.logger.debug(f"Exporting {len(entities)} entity(ies) to JSON")

        # Build JSON data with JSON-LD context
        json_data = {
            "@context": {
                "@vocab": "https://semantica.dev/vocab/",
                "semantica": SEMANTICA_NS,
                "entities": {"@id": "semantica:entities", "@container": "@list"},
            },
            "entities": entities,
            "metadata": {
                "exported_at": utc_now_iso(),
                "entity_count": len(entities),
                **options.get("metadata", {}),
            },
        }

        self.export(json_data, file_path, **options)

    def export_relationships(
        self,
        relationships: List[Dict[str, Any]],
        file_path: Union[str, Path],
        **options,
    ) -> None:
        """
        Export relationships to JSON.

        Args:
            relationships: List of relationship dictionaries
            file_path: Output file path
            **options: Additional options
        """
        json_data = {
            "@context": {
                "@vocab": "https://semantica.dev/vocab/",
                "semantica": SEMANTICA_NS,
                "relationships": {
                    "@id": "semantica:relationships",
                    "@container": "@list",
                },
            },
            "relationships": relationships,
            "metadata": {
                "exported_at": utc_now_iso(),
                "relationship_count": len(relationships),
                **options.get("metadata", {}),
            },
        }

        self.export(json_data, file_path, **options)

    def _convert_to_json(
        self,
        data: Any,
        include_metadata: bool = True,
        include_provenance: bool = True,
        **options,
    ) -> Dict[str, Any]:
        """
        Convert data to JSON format.

        This method converts various data types to a standardized JSON structure
        with optional metadata and provenance information.

        Args:
            data: Data to convert (dict, list, or any value)
            include_metadata: Whether to include metadata (default: True)
            include_provenance: Whether to include provenance (default: True)
            **options: Additional options:
                - metadata: Additional metadata to include

        Returns:
            Dictionary in JSON format with data and optional metadata
        """
        if isinstance(data, dict):
            result = dict(data)

            # Add metadata if requested
            if include_metadata:
                if "metadata" not in result:
                    result["metadata"] = {}
                result["metadata"]["exported_at"] = utc_now_iso()
                if include_provenance:
                    result["metadata"]["format"] = "json"

            return result
        elif isinstance(data, list):
            return {
                "data": data,
                "count": len(data),
                "metadata": {
                    "exported_at": utc_now_iso(),
                    "format": "json" if include_provenance else None,
                    **options.get("metadata", {}),
                },
            }
        else:
            # Single value
            return {
                "value": data,
                "metadata": {"exported_at": utc_now_iso()}
                if include_metadata
                else {},
            }

    def _convert_to_jsonld(
        self,
        data: Any,
        include_metadata: bool = True,
        include_provenance: bool = True,
        **options,
    ) -> Dict[str, Any]:
        """
        Convert data to JSON-LD format.

        This method converts various data types to JSON-LD format with proper
        context, graph structure, and metadata.

        Args:
            data: Data to convert (dict, list, or any value)
            include_metadata: Whether to include metadata (default: True)
            include_provenance: Whether to include provenance (default: True)
            **options: Additional options passed to knowledge graph conversion

        Returns:
            Dictionary in JSON-LD format with @context, @graph/@value, and metadata
        """
        # Initialize JSON-LD structure with context
        jsonld = {
            "@context": {
                "@vocab": "https://semantica.dev/vocab/",
                "semantica": "https://semantica.dev/ns#",
            }
        }

        # Convert data based on type
        if isinstance(data, dict):
            if "entities" in data or "relationships" in data:
                # Knowledge graph structure - use specialized conversion
                jsonld.update(self._convert_kg_to_jsonld(data, **options))
            else:
                # Generic dictionary - wrap in @graph
                jsonld["@graph"] = [data]
        elif isinstance(data, list):
            # List - use @graph
            jsonld["@graph"] = data
        else:
            # Single value - use @value
            jsonld["@value"] = data

        # Add metadata and provenance if requested
        if include_metadata:
            jsonld["@id"] = f"https://semantica.dev/data/{utc_now_iso()}"
            if include_provenance:
                jsonld["semantica:exportedAt"] = utc_now_iso()
                jsonld["semantica:format"] = "json-ld"

        return jsonld

    def _convert_kg_to_json(self, kg: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Convert knowledge graph to JSON format.

        This method converts a knowledge graph dictionary to a standardized JSON
        structure with entities, relationships, nodes, edges, metadata, and statistics.

        Args:
            kg: Knowledge graph dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - nodes: List of node dictionaries (optional)
                - edges: List of edge dictionaries (optional)
                - metadata: Metadata dictionary (optional)
                - statistics: Statistics dictionary (optional)
            **options: Additional options:
                - metadata: Additional metadata to merge

        Returns:
            Dictionary in JSON format with all knowledge graph components
        """
        result = {
            "entities": kg.get("entities", []),
            "relationships": kg.get("relationships", []),
            "nodes": kg.get("nodes", []),
            "edges": kg.get("edges", []),
            "metadata": {
                "exported_at": utc_now_iso(),
                **kg.get("metadata", {}),
                **options.get("metadata", {}),
            },
        }

        # Add statistics if available
        if "statistics" in kg:
            result["statistics"] = kg["statistics"]

        return result

    def _convert_kg_to_jsonld(self, kg: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Convert knowledge graph to JSON-LD format.

        This method converts a knowledge graph to JSON-LD format with proper
        RDF context, entity and relationship conversion, and metadata.

        Args:
            kg: Knowledge graph dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - metadata: Metadata dictionary (optional)
            **options: Additional options (unused)

        Returns:
            Dictionary in JSON-LD format with @context, @id, @type, and graph data
        """
        # Initialize JSON-LD structure with RDF context
        jsonld = {
            "@context": {
                "@vocab": "https://semantica.dev/vocab/",
                "semantica": "https://semantica.dev/ns#",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            },
            "@id": f"https://semantica.dev/graph/{utc_now_iso()}",
            "@type": "semantica:KnowledgeGraph",
        }

        # Convert entities to JSON-LD format
        entities = kg.get("entities", [])
        if entities:
            jsonld["semantica:entities"] = [self._entity_to_jsonld(e) for e in entities]
            self.logger.debug(f"Converted {len(entities)} entity(ies) to JSON-LD")

        # Convert relationships to JSON-LD format
        relationships = kg.get("relationships", [])
        if relationships:
            jsonld["semantica:relationships"] = [
                self._relationship_to_jsonld(r, index)
                for index, r in enumerate(relationships)
            ]
            self.logger.debug(
                f"Converted {len(relationships)} relationship(s) to JSON-LD"
            )

        # Add metadata
        jsonld["semantica:exportedAt"] = utc_now_iso()
        if "metadata" in kg:
            jsonld["semantica:metadata"] = kg["metadata"]

        return jsonld

    def _entity_to_jsonld(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert entity to JSON-LD format.

        This method converts an entity dictionary to JSON-LD format with proper
        @id, @type, and semantic properties.

        Args:
            entity: Entity dictionary with fields:
                - id: Entity identifier (optional)
                - text/label: Entity text/label
                - type: Entity type (optional)
                - confidence: Confidence score (optional)
                - metadata: Metadata dictionary (optional)

        Returns:
            Dictionary in JSON-LD format representing the entity
        """
        # Generate @id if not provided. Minted exactly as the RDF serializers
        # mint it (#1101), so the JSON-LD and Turtle exports of one knowledge
        # graph name the same entity with the same IRI. Interpolating the raw
        # text into f"semantica:entity/{text}" produced an invalid IRI for any
        # text containing a space, and a JSON-LD parser dropped the whole node.
        entity_text = entity.get("text") or entity.get("label", "unknown")
        entity_id = entity.get("id") or mint_entity_iri(entity_text)

        jsonld = {
            "@id": entity_id,
            "@type": entity.get("type") or "semantica:Entity",
            "semantica:text": entity.get("text") or entity.get("label", ""),
            "semantica:confidence": entity.get("confidence", 1.0),
        }

        # Add metadata if present
        if "metadata" in entity:
            jsonld["semantica:metadata"] = entity["metadata"]

        return jsonld

    def _relationship_to_jsonld(
        self, rel: Dict[str, Any], index: int = 0
    ) -> Dict[str, Any]:
        """
        Convert relationship to JSON-LD format.

        This method converts a relationship dictionary to JSON-LD format with
        proper @id, @type, source, target, and semantic properties.

        Args:
            rel: Relationship dictionary with fields:
                - id: Relationship identifier (optional)
                - source_id/source: Source entity identifier
                - target_id/target: Target entity identifier
                - type: Relationship type (optional)
                - confidence: Confidence score (optional)
                - metadata: Metadata dictionary (optional)
            index: Position of the relationship in the exported list, used when
                minting an IRI for a relationship that arrived without an id

        Returns:
            Dictionary in JSON-LD format representing the relationship
        """
        # Generate @id if not provided, from the same mint the RDF serializers
        # use, including the list index that separates two relationships
        # sharing a pair of endpoints (#1101).
        source_id = rel.get("source_id") or rel.get("source", "")
        target_id = rel.get("target_id") or rel.get("target", "")
        rel_id = rel.get("id") or mint_relationship_iri(index, source_id, target_id)

        jsonld = {
            "@id": rel_id,
            "@type": "semantica:Relationship",
            "semantica:type": rel.get("type", "related_to"),
            "semantica:source": {"@id": rel.get("source_id") or rel.get("source")},
            "semantica:target": {"@id": rel.get("target_id") or rel.get("target")},
            "semantica:confidence": rel.get("confidence", 1.0),
        }

        # Add metadata if present
        if "metadata" in rel:
            jsonld["semantica:metadata"] = rel["metadata"]

        return jsonld
