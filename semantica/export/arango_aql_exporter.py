"""
ArangoDB AQL Export Module

This module provides comprehensive AQL export capabilities for the Semantica framework,
enabling export to ArangoDB multi-model graph databases.

Key Features:
    - AQL format export for ArangoDB
    - INSERT statement generation for vertex and edge collections
    - Configurable collection names
    - Entity and relationship identifier preservation
    - Batch insert support for performance
    - Proper string escaping and special character handling

Example Usage:
    >>> from semantica.export import ArangoAQLExporter
    >>> exporter = ArangoAQLExporter()
    >>> exporter.export_knowledge_graph(kg, "output.aql")
    >>> # With custom collection names
    >>> exporter = ArangoAQLExporter(
    ...     vertex_collection="nodes",
    ...     edge_collection="links"
    ... )
    >>> exporter.export(kg, "graph.aql")
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.helpers import _require_mapping, ensure_directory, normalize_graph_payload
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class ArangoAQLExporter:
    """
    ArangoDB AQL exporter for knowledge graphs.

    This class provides comprehensive AQL export functionality for knowledge graphs,
    supporting export to ArangoDB multi-model databases via AQL INSERT statements.

    Features:
        - AQL INSERT statement generation for vertices and edges
        - Configurable collection names
        - Entity and relationship identifier preservation
        - Batch insert support for performance
        - Proper string escaping and special character handling
        - Support for nested properties via JSON serialization

    Example Usage:
        >>> exporter = ArangoAQLExporter(
        ...     vertex_collection="entities",
        ...     edge_collection="relationships"
        ... )
        >>> exporter.export_knowledge_graph(kg, "output.aql")
    """

    def __init__(
        self,
        vertex_collection: str = "vertices",
        edge_collection: str = "edges",
        batch_size: int = 1000,
        include_collection_creation: bool = True,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize ArangoDB AQL exporter.

        Sets up the exporter with collection names and batch processing options.

        Args:
            vertex_collection: Name of the vertex collection
                (default: "vertices")
            edge_collection: Name of the edge collection (default: "edges")
            batch_size: Batch size for INSERT operations (default: 1000)
            include_collection_creation: Whether to include collection
                creation statements (default: True)
            config: Optional configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("arango_aql_exporter")
        self.config = config or {}
        self.config.update(kwargs)

        # Validate collection names
        self._validate_collection_name(vertex_collection, "vertex_collection")
        self._validate_collection_name(edge_collection, "edge_collection")

        # AQL export configuration
        self.vertex_collection = vertex_collection
        self.edge_collection = edge_collection
        self.batch_size = batch_size
        self.include_collection_creation = include_collection_creation

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug(
            f"ArangoDB AQL exporter initialized: "
            f"vertex_collection={vertex_collection}, "
            f"edge_collection={edge_collection}, batch_size={batch_size}"
        )

    def export(
        self, knowledge_graph: Dict[str, Any], file_path: Union[str, Path], **options
    ) -> None:
        """
        Export knowledge graph to ArangoDB AQL format.

        This method exports a knowledge graph to AQL INSERT statements that can
        be imported into ArangoDB multi-model databases.

        Args:
            knowledge_graph: Knowledge graph dictionary containing:
                - entities: List of entity dictionaries
                - relationships: List of relationship dictionaries
                - nodes: List of node dictionaries (optional, alternative to
                  entities)
                - edges: List of edge dictionaries (optional, alternative to
                  relationships)
            file_path: Output AQL file path
            **options: Additional export options:
                - vertex_collection: Override default vertex collection name
                - edge_collection: Override default edge collection name

        Example:
            >>> kg = {
            ...     "entities": [...],
            ...     "relationships": [...]
            ... }
            >>> exporter.export(kg, "graph.aql")
        """
        file_path = Path(file_path)
        ensure_directory(file_path.parent)

        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="export",
            submodule="ArangoAQLExporter",
            message=f"Exporting knowledge graph to ArangoDB AQL format: {file_path}",
        )

        try:
            # Override collection names if provided in options
            vertex_collection = options.pop("vertex_collection", self.vertex_collection)
            edge_collection = options.pop("edge_collection", self.edge_collection)

            # Validate overridden collection names
            if vertex_collection != self.vertex_collection:
                self._validate_collection_name(vertex_collection, "vertex_collection")
            if edge_collection != self.edge_collection:
                self._validate_collection_name(edge_collection, "edge_collection")

            # Generate AQL statements
            aql_statements = self._generate_aql_statements(
                knowledge_graph, vertex_collection, edge_collection, **options
            )

            # Write to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(aql_statements))

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Exported {len(aql_statements)} AQL statements",
            )
            self.logger.info(
                f"Exported knowledge graph to ArangoDB AQL format: " f"{file_path}"
            )

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _generate_aql_statements(
        self,
        knowledge_graph: Dict[str, Any],
        vertex_collection: str,
        edge_collection: str,
        **options,
    ) -> List[str]:
        """
        Generate AQL INSERT statements from knowledge graph.

        Args:
            knowledge_graph: Knowledge graph dictionary
            vertex_collection: Vertex collection name
            edge_collection: Edge collection name
            **options: Additional options

        Returns:
            List of AQL statement strings
        """
        statements = []

        # Add collection creation statements if requested
        if self.include_collection_creation:
            statements.extend(
                self._generate_collection_creation(vertex_collection, edge_collection)
            )

        # A non-mapping payload cannot reach normalize_graph_payload(): it
        # raises ValidationError for that case, which would leave this
        # exporter alone in raising a different exception type than the YAML
        # and Neo4j exporters raise for the identical mistake.
        _require_mapping(
            knowledge_graph, ("entities", "relationships", "nodes", "edges")
        )

        # Accept either vocabulary; resolution is centralized so every
        # exporter agrees on what a given payload means.
        normalized = normalize_graph_payload(knowledge_graph)
        entities = normalized["entities"]
        relationships = normalized["relationships"]

        # Generate vertex INSERT statements
        vertex_statements = self._generate_vertex_inserts(entities, vertex_collection)
        statements.extend(vertex_statements)

        # Generate edge INSERT statements
        edge_statements = self._generate_edge_inserts(
            relationships, edge_collection, vertex_collection
        )
        statements.extend(edge_statements)

        return statements

    def _generate_collection_creation(
        self, vertex_collection: str, edge_collection: str
    ) -> List[str]:
        """
        Generate AQL collection creation statements.

        Args:
            vertex_collection: Vertex collection name
            edge_collection: Edge collection name

        Returns:
            List of collection creation statements
        """
        statements = [
            "// Create vertex collection if it doesn't exist",
            f"// db._createDocumentCollection('{vertex_collection}');",
            "",
            "// Create edge collection if it doesn't exist",
            f"// db._createEdgeCollection('{edge_collection}');",
            "",
        ]
        return statements

    def _generate_vertex_inserts(
        self, vertices: List[Dict[str, Any]], collection: str
    ) -> List[str]:
        """
        Generate AQL INSERT statements for vertices.

        Args:
            vertices: List of vertex/entity dictionaries
            collection: Vertex collection name

        Returns:
            List of AQL INSERT statements
        """
        statements = []

        # Add header comment
        statements.append(f"// Inserting {len(vertices)} vertices into {collection}")
        statements.append("")

        # Process vertices in batches
        for i in range(0, len(vertices), self.batch_size):
            batch = vertices[i : i + self.batch_size]
            batch_statement = self._create_vertex_batch_insert(batch, collection)
            statements.append(batch_statement)
            statements.append("")

        return statements

    def _create_vertex_batch_insert(
        self, vertices: List[Dict[str, Any]], collection: str
    ) -> str:
        """
        Create a batch INSERT statement for vertices.

        Args:
            vertices: Batch of vertex dictionaries
            collection: Vertex collection name

        Returns:
            AQL INSERT statement
        """
        if not vertices:
            return ""

        # Build document list
        documents = []
        for idx, vertex in enumerate(vertices):
            doc = self._convert_vertex_to_document(vertex, idx)
            documents.append(doc)

        # Format as AQL
        docs_json = json.dumps(documents, indent=2, ensure_ascii=False)
        statement = f"FOR doc IN {docs_json}\n  INSERT doc INTO {collection}"

        return statement

    def _convert_vertex_to_document(
        self, vertex: Dict[str, Any], idx: int
    ) -> Dict[str, Any]:
        """
        Convert a vertex/entity to an ArangoDB document.

        Additional properties from the input entity are preserved as-is in the
        document root (not flattened or merged). Nested dictionaries and lists
        are preserved as JSON-serializable structures. The 'properties' field,
        if present, is also preserved as-is rather than being flattened into
        the document root.

        Args:
            vertex: Vertex/entity dictionary
            idx: Index for generating fallback IDs

        Returns:
            ArangoDB document dictionary
        """
        document = {}

        # Set _key from id or generate one
        vertex_id = vertex.get("id") or vertex.get("entity_id") or f"vertex_{idx}"
        document["_key"] = self._sanitize_key(str(vertex_id))

        # Add original ID if different from _key
        if str(vertex_id) != document["_key"]:
            document["original_id"] = str(vertex_id)

        # Add type/label information
        vertex_type = vertex.get("type") or vertex.get("entity_type", "Entity")
        document["type"] = vertex_type

        # Add name/label
        label = (
            vertex.get("label")
            or vertex.get("name")
            or vertex.get("text")
            or document["_key"]
        )
        document["name"] = label

        # Add all other properties
        for key, value in vertex.items():
            if key not in [
                "_key",
                "_id",
                "_rev",
                "id",
                "entity_id",
                "type",
                "entity_type",
                "label",
                "name",
                "text",
            ]:
                # Handle nested dictionaries and lists
                if isinstance(value, (dict, list)):
                    document[key] = value
                elif value is not None:
                    document[key] = value

        return document

    def _generate_edge_inserts(
        self, edges: List[Dict[str, Any]], collection: str, vertex_collection: str
    ) -> List[str]:
        """
        Generate AQL INSERT statements for edges.

        Args:
            edges: List of edge/relationship dictionaries
            collection: Edge collection name
            vertex_collection: Vertex collection name for _from/_to references

        Returns:
            List of AQL INSERT statements
        """
        statements = []

        # Add header comment
        statements.append(
            f"// Attempting to insert {len(edges)} edges into {collection}"
        )
        statements.append("")

        # Process edges in batches
        for i in range(0, len(edges), self.batch_size):
            batch = edges[i : i + self.batch_size]
            batch_statement = self._create_edge_batch_insert(
                batch, collection, vertex_collection
            )
            if batch_statement:  # Only add non-empty statements
                statements.append(batch_statement)
                statements.append("")

        return statements

    def _create_edge_batch_insert(
        self, edges: List[Dict[str, Any]], collection: str, vertex_collection: str
    ) -> str:
        """
        Create a batch INSERT statement for edges.

        Args:
            edges: Batch of edge dictionaries
            collection: Edge collection name
            vertex_collection: Vertex collection name for _from/_to references

        Returns:
            AQL INSERT statement
        """
        # Build document list
        documents = []
        for idx, edge in enumerate(edges):
            doc = self._convert_edge_to_document(edge, idx, vertex_collection)
            if doc:  # Only add valid edges
                documents.append(doc)

        if not documents:
            return ""

        # Format as AQL
        docs_json = json.dumps(documents, indent=2, ensure_ascii=False)
        statement = f"FOR doc IN {docs_json}\n  INSERT doc INTO {collection}"

        return statement

    def _convert_edge_to_document(
        self, edge: Dict[str, Any], idx: int, vertex_collection: str
    ) -> Optional[Dict[str, Any]]:
        """
        Convert an edge/relationship to an ArangoDB edge document.

        Args:
            edge: Edge/relationship dictionary
            idx: Index for generating fallback IDs
            vertex_collection: Vertex collection name for _from/_to references

        Returns:
            ArangoDB edge document dictionary, or None if source/target missing
        """
        # Extract source and target
        source_id = edge.get("source") or edge.get("source_id")
        target_id = edge.get("target") or edge.get("target_id")

        if not source_id or not target_id:
            self.logger.warning(
                f"Skipping edge {idx}: missing source or target "
                f"(source={source_id}, target={target_id})"
            )
            return None

        document = {}

        # Set _key from id or generate one
        edge_id = edge.get("id") or edge.get("relationship_id") or f"edge_{idx}"
        document["_key"] = self._sanitize_key(str(edge_id))

        # Set _from and _to (required for edges in ArangoDB)
        document["_from"] = f"{vertex_collection}/{self._sanitize_key(str(source_id))}"
        document["_to"] = f"{vertex_collection}/{self._sanitize_key(str(target_id))}"

        # Add original ID if different from _key
        if str(edge_id) != document["_key"]:
            document["original_id"] = str(edge_id)

        # Add relationship type
        rel_type = edge.get("type") or edge.get("relationship_type", "RELATED_TO")
        document["type"] = rel_type

        # Add all other properties
        for key, value in edge.items():
            if key not in [
                "_key",
                "_id",
                "_rev",
                "_from",
                "_to",
                "id",
                "relationship_id",
                "source",
                "source_id",
                "target",
                "target_id",
                "type",
                "relationship_type",
            ]:
                # Handle nested dictionaries and lists
                if isinstance(value, (dict, list)):
                    document[key] = value
                elif value is not None:
                    document[key] = value

        return document

    def _validate_collection_name(self, name: str, param_name: str) -> None:
        """
        Validate an ArangoDB collection name.

        ArangoDB collection names must:
        - Start with a letter or underscore
        - Contain only alphanumeric characters, hyphens, and underscores
        - Not exceed 256 characters

        Args:
            name: Collection name to validate
            param_name: Parameter name for error messages

        Raises:
            ValueError: If the collection name is invalid
        """
        if not name:
            raise ValueError(f"{param_name} cannot be empty")

        if len(name) > 256:
            raise ValueError(
                f"{param_name} '{name}' exceeds maximum length of 256 characters"
            )

        # Check first character
        if not (name[0].isalpha() or name[0] == "_"):
            raise ValueError(
                f"{param_name} '{name}' must start with a letter or underscore"
            )

        # Check remaining characters
        for char in name:
            if not (char.isalnum() or char in ("-", "_")):
                raise ValueError(
                    f"{param_name} '{name}' contains invalid character "
                    f"'{char}'. Only alphanumeric characters, hyphens, and "
                    "underscores are allowed."
                )

    def _sanitize_key(self, key: str) -> str:
        """
        Sanitize a key for use as ArangoDB _key.

        ArangoDB _key must contain only alphanumeric characters, hyphens,
        and underscores. It cannot start with an underscore (unless it's
        a system collection).

        Args:
            key: Original key string

        Returns:
            Sanitized key string
        """
        # Replace invalid characters with underscores
        sanitized = ""
        for char in key:
            if char.isalnum() or char in ("-", "_"):
                sanitized += char
            else:
                sanitized += "_"

        # Ensure key doesn't start with underscore
        if sanitized.startswith("_"):
            sanitized = "k" + sanitized

        # Ensure key is not empty
        if not sanitized:
            sanitized = "key"

        return sanitized

    def export_knowledge_graph(
        self, knowledge_graph: Dict[str, Any], file_path: Union[str, Path], **options
    ) -> None:
        """
        Export knowledge graph to ArangoDB AQL format.

        Convenience method that calls export().

        Args:
            knowledge_graph: Knowledge graph dictionary
            file_path: Output AQL file path
            **options: Additional export options

        Example:
            >>> kg = {
            ...     "entities": [...],
            ...     "relationships": [...]
            ... }
            >>> exporter.export_knowledge_graph(kg, "output.aql")
        """
        self.export(knowledge_graph, file_path, **options)

    def export_entities(
        self, entities: List[Dict[str, Any]], file_path: Union[str, Path], **options
    ) -> None:
        """
        Export entities to ArangoDB AQL format (vertices only).

        Args:
            entities: List of entity dictionaries
            file_path: Output AQL file path
            **options: Additional export options

        Example:
            >>> entities = [
            ...     {"id": "e1", "type": "Person", "name": "Alice"},
            ...     {"id": "e2", "type": "Organization", "name": "Acme Corp"}
            ... ]
            >>> exporter.export_entities(entities, "entities.aql")
        """
        knowledge_graph = {"entities": entities, "relationships": []}
        self.export(knowledge_graph, file_path, **options)

    def export_relationships(
        self,
        relationships: List[Dict[str, Any]],
        file_path: Union[str, Path],
        **options,
    ) -> None:
        """
        Export relationships to ArangoDB AQL format (edges only).

        Args:
            relationships: List of relationship dictionaries
            file_path: Output AQL file path
            **options: Additional export options

        Example:
            >>> relationships = [
            ...     {"id": "r1", "source": "e1", "target": "e2", "type": "WORKS_FOR"}
            ... ]
            >>> exporter.export_relationships(relationships, "relationships.aql")
        """
        knowledge_graph = {"entities": [], "relationships": relationships}
        self.export(knowledge_graph, file_path, **options)
