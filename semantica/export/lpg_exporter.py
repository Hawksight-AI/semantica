"""
LPG (Labeled Property Graph) Export Module

This module provides comprehensive LPG export capabilities for the Semantica framework,
enabling export to graph databases like Neo4j, Memgraph, and similar systems.

Key Features:
    - LPG format export for Neo4j, Memgraph, and similar databases
    - Cypher query generation for graph database import
    - Node label assignment from entity types
    - Relationship type mapping
    - Property serialization
    - Batch export processing
    - Index and constraint generation

Example Usage:
    >>> from semantica.export import LPGExporter
    >>> exporter = LPGExporter()
    >>> exporter.export_knowledge_graph(kg, "output.cypher")
    >>> exporter.export_to_neo4j(kg, uri="bolt://localhost:7687", username="neo4j", password="password")
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import _require_mapping, ensure_directory, normalize_graph_payload
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class LPGExporter:
    """
    LPG exporter for knowledge graphs and graph databases.

    This class provides comprehensive LPG export functionality for knowledge graphs,
    supporting export to Neo4j, Memgraph, and similar graph databases via Cypher queries.

    Features:
        - Cypher query generation for graph database import
        - Node label assignment from entity types
        - Relationship type mapping
        - Property serialization
        - Batch export processing
        - Index and constraint generation

    Example Usage:
        >>> exporter = LPGExporter()
        >>> exporter.export_knowledge_graph(kg, "output.cypher")
    """

    def __init__(
        self,
        batch_size: int = 1000,
        include_indexes: bool = True,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize LPG exporter.

        Sets up the exporter with batch size and index generation options.

        Args:
            batch_size: Batch size for Cypher queries (default: 1000)
            include_indexes: Whether to generate indexes and constraints (default: True)
            config: Optional configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("lpg_exporter")
        self.config = config or {}
        self.config.update(kwargs)

        # LPG export configuration
        self.batch_size = batch_size
        self.include_indexes = include_indexes

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug(
            f"LPG exporter initialized: batch_size={batch_size}, "
            f"include_indexes={include_indexes}"
        )

    def export(
        self, knowledge_graph: Dict[str, Any], file_path: Union[str, Path], **options
    ) -> None:
        """
        Export knowledge graph to LPG format (Cypher queries).

        This method exports a knowledge graph to Cypher CREATE statements that can
        be imported into Neo4j, Memgraph, or similar graph databases.

        Args:
            knowledge_graph: Knowledge graph dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - nodes: List of node dictionaries (optional)
                - edges: List of edge dictionaries (optional)
            file_path: Output Cypher file path
            **options: Additional export options

        Example:
            >>> kg = {
            ...     "entities": [...],
            ...     "relationships": [...]
            ... }
            >>> exporter.export(kg, "graph.cypher")
        """
        file_path = Path(file_path)
        ensure_directory(file_path.parent)

        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="export",
            submodule="LPGExporter",
            message=f"Exporting knowledge graph to LPG format: {file_path}",
        )

        try:
            # Generate Cypher queries
            cypher_queries = self._generate_cypher_queries(knowledge_graph, **options)

            # Write to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(cypher_queries))

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Exported {len(cypher_queries)} Cypher queries",
            )
            self.logger.info(f"Exported knowledge graph to LPG format: {file_path}")

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _generate_cypher_queries(
        self, knowledge_graph: Dict[str, Any], **options
    ) -> List[str]:
        """
        Generate Cypher CREATE queries from knowledge graph.

        Args:
            knowledge_graph: Knowledge graph dictionary
            **options: Additional options

        Returns:
            List of Cypher query strings
        """
        queries = []

        # A non-mapping payload cannot reach normalize_graph_payload(): it
        # raises ValidationError for that case, which would leave this
        # exporter alone in raising a different exception type than the YAML
        # and Neo4j exporters raise for the identical mistake.
        _require_mapping(
            knowledge_graph, ("entities", "relationships", "nodes", "edges")
        )

        # Accept either vocabulary. Reading 'nodes' with 'entities' as the
        # default dropped every entity when 'nodes' was present but empty --
        # the shape JSONExporter emits -- so resolution is centralized.
        normalized = normalize_graph_payload(knowledge_graph)
        nodes = normalized["entities"]
        edges = normalized["relationships"]

        # Generate indexes if requested. Fed the normalized entities so index
        # generation sees the same records as node generation; reading
        # 'entities' directly here skipped indexes for nodes/edges payloads.
        if self.include_indexes:
            queries.extend(self._generate_indexes(nodes))

        # Generate node creation queries
        node_queries = self._generate_node_queries(nodes)
        queries.extend(node_queries)

        # Generate relationship creation queries
        rel_queries = self._generate_relationship_queries(edges)
        queries.extend(rel_queries)

        return queries

    def _generate_indexes(self, entities: List[Dict[str, Any]]) -> List[str]:
        """Generate Cypher index and constraint creation queries.

        Args:
            entities: Entity records, already resolved from whichever
                vocabulary the caller supplied.
        """
        indexes = []

        # Get unique entity types for labels
        entity_types = set()
        for entity in entities:
            entity_type = entity.get("type") or entity.get("entity_type")
            if entity_type:
                entity_types.add(entity_type)

        # Create indexes on common properties
        for entity_type in entity_types:
            # Index on id property
            indexes.append(
                f"CREATE INDEX IF NOT EXISTS FOR (n:{entity_type}) ON (n.id);"
            )
            # Index on name property if exists
            indexes.append(
                f"CREATE INDEX IF NOT EXISTS FOR (n:{entity_type}) ON (n.name);"
            )

        return indexes

    def _generate_node_queries(self, nodes: List[Dict[str, Any]]) -> List[str]:
        """Generate Cypher node creation queries."""
        queries = []

        # Process nodes in batches
        for i in range(0, len(nodes), self.batch_size):
            batch = nodes[i : i + self.batch_size]
            batch_query = self._create_nodes_batch(batch)
            queries.append(batch_query)

        return queries

    def _create_nodes_batch(self, nodes: List[Dict[str, Any]]) -> str:
        """Create a batch of nodes in a single Cypher query."""
        if not nodes:
            return ""

        lines = []
        for idx, node in enumerate(nodes):
            node_id = node.get("id") or node.get("entity_id", f"node_{idx}")
            node_type = node.get("type") or node.get("entity_type", "Entity")
            label = node.get("label") or node.get("name") or node.get("text", "")

            # Escape special characters
            node_id_escaped = self._escape_cypher_string(str(node_id))
            label_escaped = self._escape_cypher_string(str(label))

            # Build properties
            properties = {"id": node_id_escaped, "name": label_escaped}

            # Add other properties
            for key, value in node.items():
                if key not in [
                    "id",
                    "entity_id",
                    "type",
                    "entity_type",
                    "label",
                    "name",
                    "text",
                ]:
                    if isinstance(value, (str, int, float, bool)):
                        properties[key] = self._format_cypher_value(value)

            # Format properties
            props_str = ", ".join([f"{k}: {v}" for k, v in properties.items()])

            # Create node
            lines.append(f"CREATE (n{idx}:{node_type} {{{props_str}}});")

        return "\n".join(lines)

    def _generate_relationship_queries(self, edges: List[Dict[str, Any]]) -> List[str]:
        """Generate Cypher relationship creation queries."""
        queries = []

        # Process edges in batches
        for i in range(0, len(edges), self.batch_size):
            batch = edges[i : i + self.batch_size]
            batch_query = self._create_relationships_batch(batch)
            queries.append(batch_query)

        return queries

    def _create_relationships_batch(self, edges: List[Dict[str, Any]]) -> str:
        """Create a batch of relationships in a single Cypher query."""
        if not edges:
            return ""

        lines = []
        for idx, edge in enumerate(edges):
            source_id = edge.get("source") or edge.get("source_id")
            target_id = edge.get("target") or edge.get("target_id")
            rel_type = edge.get("type") or edge.get("relationship_type", "RELATED_TO")

            if not source_id or not target_id:
                continue

            # Escape special characters
            source_escaped = self._escape_cypher_string(str(source_id))
            target_escaped = self._escape_cypher_string(str(target_id))
            rel_type_escaped = rel_type.upper().replace(" ", "_")

            # Build properties
            properties = {}
            for key, value in edge.items():
                if key not in [
                    "source",
                    "source_id",
                    "target",
                    "target_id",
                    "type",
                    "relationship_type",
                ]:
                    if isinstance(value, (str, int, float, bool)):
                        properties[key] = self._format_cypher_value(value)

            # Format properties
            if properties:
                props_str = ", ".join([f"{k}: {v}" for k, v in properties.items()])
                props_str = f" {{{props_str}}}"
            else:
                props_str = ""

            # Create relationship
            lines.append(
                f"MATCH (a {{id: '{source_escaped}'}}), (b {{id: '{target_escaped}'}}) "
                f"CREATE (a)-[r:{rel_type_escaped}{props_str}]->(b);"
            )

        return "\n".join(lines)

    def _escape_cypher_string(self, value: str) -> str:
        """Escape special characters in Cypher strings."""
        return value.replace("'", "\\'").replace("\\", "\\\\")

    def _format_cypher_value(self, value: Any) -> str:
        """Format a value for Cypher query."""
        if isinstance(value, str):
            escaped = self._escape_cypher_string(value)
            return f"'{escaped}'"
        elif isinstance(value, bool):
            return str(value).lower()
        else:
            return str(value)

    def export_knowledge_graph(
        self, knowledge_graph: Dict[str, Any], file_path: Union[str, Path], **options
    ) -> None:
        """
        Export knowledge graph to LPG format.

        Convenience method that calls export().

        Args:
            knowledge_graph: Knowledge graph dictionary
            file_path: Output file path
            **options: Additional export options
        """
        self.export(knowledge_graph, file_path, **options)
