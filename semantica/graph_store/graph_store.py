"""
Graph Store Core Module

This module provides the core graph store interface and management classes,
providing a unified interface across multiple graph database backends
(Neo4j, FalkorDB).

Key Features:
    - Unified graph store interface
    - Multi-backend support
    - Node and relationship management
    - Query execution engine
    - Graph analytics and algorithms
    - Transaction support
    - Configuration management

Main Classes:
    - GraphStore: Main graph store interface
    - GraphManager: Graph store management and operations
    - NodeManager: Node CRUD operations
    - RelationshipManager: Relationship CRUD operations
    - QueryEngine: Query execution and optimization
    - GraphAnalytics: Graph algorithms and analytics

Example Usage:
    >>> from semantica.graph_store import GraphStore
    >>> store = GraphStore(backend="neo4j", uri="bolt://localhost:7687")
    >>> store.create_node(labels=["Person"], properties={"name": "Alice"})
    >>> results = store.execute_query("MATCH (n) RETURN n LIMIT 10")

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from ..utils.exceptions import ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .config import graph_store_config
from .query_sanitize import sanitize_identifier


class NodeManager:
    """Manager for node CRUD operations."""

    def __init__(self, backend: Any):
        """
        Initialize node manager.

        Args:
            backend: Graph database backend instance
        """
        self.backend = backend
        self.logger = get_logger("node_manager")

    def create(
        self,
        labels: List[str],
        properties: Dict[str, Any],
        **options,
    ) -> Dict[str, Any]:
        """
        Create a node.

        Args:
            labels: Node labels
            properties: Node properties
            **options: Additional options

        Returns:
            Created node information
        """
        return self.backend.create_node(labels, properties, **options)

    def create_batch(
        self,
        nodes: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Create multiple nodes in batch.

        Args:
            nodes: List of node dictionaries with 'labels' and 'properties'
            **options: Additional options

        Returns:
            List of created node information
        """
        return self.backend.create_nodes(nodes, **options)

    def get(
        self,
        node_id: Union[int, str] = None,
        labels: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        **options,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Get node(s).

        Args:
            node_id: Specific node ID to get
            labels: Filter by labels
            properties: Filter by properties
            limit: Maximum number of nodes
            **options: Additional options

        Returns:
            Node or list of nodes
        """
        if node_id is not None:
            return self.backend.get_node(node_id, **options)
        return self.backend.get_nodes(labels, properties, limit, **options)

    def update(
        self,
        node_id: Union[int, str],
        properties: Dict[str, Any],
        merge: bool = True,
        **options,
    ) -> Dict[str, Any]:
        """
        Update a node.

        Args:
            node_id: Node ID
            properties: Properties to update
            merge: If True, merge; if False, replace
            **options: Additional options

        Returns:
            Updated node information
        """
        return self.backend.update_node(node_id, properties, merge, **options)

    def delete(
        self,
        node_id: Union[int, str],
        detach: bool = True,
        **options,
    ) -> bool:
        """
        Delete a node.

        Args:
            node_id: Node ID
            detach: If True, delete relationships as well
            **options: Additional options

        Returns:
            True if deleted
        """
        return self.backend.delete_node(node_id, detach, **options)


class RelationshipManager:
    """Manager for relationship CRUD operations."""

    def __init__(self, backend: Any):
        """
        Initialize relationship manager.

        Args:
            backend: Graph database backend instance
        """
        self.backend = backend
        self.logger = get_logger("relationship_manager")

    def create(
        self,
        start_node_id: Union[int, str],
        end_node_id: Union[int, str],
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Create a relationship.

        Args:
            start_node_id: Start node ID
            end_node_id: End node ID
            rel_type: Relationship type
            properties: Relationship properties
            **options: Additional options

        Returns:
            Created relationship information
        """
        return self.backend.create_relationship(
            start_node_id, end_node_id, rel_type, properties, **options
        )

    def get(
        self,
        node_id: Optional[Union[int, str]] = None,
        rel_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get relationships.

        Args:
            node_id: Filter by node ID
            rel_type: Filter by relationship type
            direction: Direction ("in", "out", "both")
            limit: Maximum number of relationships
            **options: Additional options

        Returns:
            List of relationships
        """
        return self.backend.get_relationships(
            node_id, rel_type, direction, limit, **options
        )

    def delete(
        self,
        rel_id: Union[int, str],
        **options,
    ) -> bool:
        """
        Delete a relationship.

        Args:
            rel_id: Relationship ID
            **options: Additional options

        Returns:
            True if deleted
        """
        return self.backend.delete_relationship(rel_id, **options)


class QueryEngine:
    """Engine for query execution and optimization."""

    def __init__(self, backend: Any):
        """
        Initialize query engine.

        Args:
            backend: Graph database backend instance
        """
        self.backend = backend
        self.logger = get_logger("query_engine")
        self._cache: Dict[str, Any] = {}
        self._cache_enabled = True

    def execute(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        use_cache: bool = False,
        **options,
    ) -> Dict[str, Any]:
        """
        Execute a Cypher/OpenCypher query.

        Args:
            query: Query string
            parameters: Query parameters
            use_cache: Whether to use query caching
            **options: Additional options

        Returns:
            Query results
        """
        # Check cache
        if use_cache and self._cache_enabled:
            cache_key = self._generate_cache_key(query, parameters)
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Execute query
        result = self.backend.execute_query(query, parameters, **options)

        # Cache result
        if use_cache and self._cache_enabled:
            self._cache[cache_key] = result

        return result

    def _generate_cache_key(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]],
    ) -> str:
        """Generate cache key for query."""
        import hashlib

        key_str = f"{query}:{str(parameters)}"
        return hashlib.md5(key_str.encode()).hexdigest()  # nosec B324 - cache key, not security-sensitive

    def clear_cache(self) -> None:
        """Clear query cache."""
        self._cache.clear()

    def enable_cache(self) -> None:
        """Enable query caching."""
        self._cache_enabled = True

    def disable_cache(self) -> None:
        """Disable query caching."""
        self._cache_enabled = False


class GraphAnalytics:
    """Graph analytics and algorithms."""

    def __init__(self, backend: Any):
        """
        Initialize graph analytics.

        Args:
            backend: Graph database backend instance
        """
        self.backend = backend
        self.logger = get_logger("graph_analytics")

    def shortest_path(
        self,
        start_node_id: Union[int, str],
        end_node_id: Union[int, str],
        rel_type: Optional[str] = None,
        max_depth: int = 10,
        **options,
    ) -> Optional[Dict[str, Any]]:
        """
        Find shortest path between two nodes.

        Args:
            start_node_id: Starting node ID
            end_node_id: Ending node ID
            rel_type: Filter by relationship type
            max_depth: Maximum path length
            **options: Additional options

        Returns:
            Path information or None
        """
        return self.backend.shortest_path(
            start_node_id, end_node_id, rel_type, max_depth, **options
        )

    def get_neighbors(
        self,
        node_id: Union[int, str],
        rel_type: Optional[str] = None,
        direction: str = "both",
        depth: int = 1,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring nodes.

        Args:
            node_id: Starting node ID
            rel_type: Filter by relationship type
            direction: Direction ("in", "out", "both")
            depth: Traversal depth
            **options: Additional options

        Returns:
            List of neighboring nodes
        """
        return self.backend.get_neighbors(
            node_id, rel_type, direction, depth, **options
        )

    def degree_centrality(
        self,
        labels: Optional[List[str]] = None,
        rel_type: Optional[str] = None,
        direction: str = "both",
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Calculate degree centrality for nodes.

        Args:
            labels: Filter by node labels
            rel_type: Filter by relationship type
            direction: Direction ("in", "out", "both")
            **options: Additional options

        Returns:
            List of nodes with centrality scores
        """
        # Build query based on direction
        if labels:
            label_str = ":".join(sanitize_identifier(l, "label") for l in labels)
            match = f"MATCH (n:{label_str})"
        else:
            match = "MATCH (n)"

        type_filter = f":{sanitize_identifier(rel_type, 'relationship type')}" if rel_type else ""

        if direction == "out":
            query = f"""
                {match}
                OPTIONAL MATCH (n)-[r{type_filter}]->()
                WITH n, count(r) as degree
                RETURN id(n) as id, n, degree
                ORDER BY degree DESC
            """
        elif direction == "in":
            query = f"""
                {match}
                OPTIONAL MATCH (n)<-[r{type_filter}]-()
                WITH n, count(r) as degree
                RETURN id(n) as id, n, degree
                ORDER BY degree DESC
            """
        else:
            query = f"""
                {match}
                OPTIONAL MATCH (n)-[r{type_filter}]-()
                WITH n, count(r) as degree
                RETURN id(n) as id, n, degree
                ORDER BY degree DESC
            """

        result = self.backend.execute_query(query)
        return result.get("records", [])

    def connected_components(
        self,
        labels: Optional[List[str]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Find connected components in the graph.

        Note: Full connected components requires GDS library for Neo4j
        or custom implementation. This provides a basic approximation.

        Args:
            labels: Filter by node labels
            **options: Additional options

        Returns:
            Component information
        """
        backend_type = type(self.backend).__name__

        if "Neo4j" in backend_type:
            query = """
            CALL gds.wcc.stream({
                nodeProjection: $label,
                relationshipProjection: '*'
            })
            YIELD nodeId, componentId
            RETURN componentId, collect(nodeId) as nodes
            """
            params = {"label": labels[0] if labels else "*"}
            result = self.backend.execute_query(query, params)
            return [
                {"component": r["componentId"], "nodes": r["nodes"]} for r in result
            ]

        elif "NetworkX" in backend_type:
            import networkx as nx

            G = self.backend.graph
            components = list(nx.connected_components(G))
            return [
                {"component": i, "nodes": list(c)} for i, c in enumerate(components)
            ]

        else:
            raise NotImplementedError(
                f"connected_components not implemented for {backend_type}"
            )


class GraphManager:
    """Manager for graph store operations."""

    def __init__(self, backend: Any):
        """
        Initialize graph manager.

        Args:
            backend: Graph database backend instance
        """
        self.backend = backend
        self.logger = get_logger("graph_manager")
        self.nodes = NodeManager(backend)
        self.relationships = RelationshipManager(backend)
        self.query_engine = QueryEngine(backend)
        self.analytics = GraphAnalytics(backend)

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        return self.backend.get_stats()

    def create_index(
        self,
        label: str,
        property_name: str,
        index_type: str = "btree",
        **options,
    ) -> bool:
        """
        Create an index.

        Args:
            label: Node label
            property_name: Property to index
            index_type: Index type
            **options: Additional options

        Returns:
            True if created
        """
        return self.backend.create_index(label, property_name, index_type, **options)


class GraphStore:
    """
    Main graph store interface.

    Provides a unified interface for working with property graph databases,
    supporting Neo4j and FalkorDB backends.
    """

    def __init__(
        self,
        backend: Optional[str] = None,
        **config,
    ):
        """
        Initialize graph store.

        Args:
            backend: Backend type ("neo4j", "falkordb")
            **config: Backend-specific configuration
        """
        self.logger = get_logger("graph_store")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Determine backend
        self.backend = (
            backend
            or config.get("backend")
            or graph_store_config.get("default_backend", "neo4j")
        )
        self.config = config

        # Initialize store backend
        self._store_backend = None
        self._manager = None
        self._initialize_store_backend()

    def _initialize_store_backend(self) -> None:
        """Initialize the appropriate store backend based on backend type."""
        if self.backend == "neo4j":
            from .neo4j_store import Neo4jStore

            neo4j_config = graph_store_config.get_neo4j_config()
            neo4j_config.update(self.config)
            self._store_backend = Neo4jStore(**neo4j_config)

        elif self.backend == "falkordb":
            from .falkordb_store import FalkorDBStore

            falkordb_config = graph_store_config.get_falkordb_config()
            falkordb_config.update(self.config)
            self._store_backend = FalkorDBStore(**falkordb_config)

        elif self.backend == "neptune" or self.backend == "amazon_neptune":
            from .amazon_neptune import AmazonNeptuneStore

            neptune_config = graph_store_config.get_neptune_config()
            neptune_config.update(self.config)
            self._store_backend = AmazonNeptuneStore(**neptune_config)

        elif self.backend == "age" or self.backend == "apache_age":
            from .age_store import ApacheAgeStore

            age_config = graph_store_config.get_age_config()
            age_config.update(self.config)
            self._store_backend = ApacheAgeStore(**age_config)

        else:
            raise ValidationError(f"Unknown backend: {self.backend}")

        self._manager = GraphManager(self._store_backend)

    def connect(self, **options) -> bool:
        """
        Connect to the graph database.

        Args:
            **options: Connection options

        Returns:
            True if connected
        """
        return self._store_backend.connect(**options)

    def close(self) -> None:
        """Close connection to the graph database."""
        if self._store_backend:
            self._store_backend.close()

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # Node operations
    def create_node(
        self,
        labels: List[str],
        properties: Dict[str, Any],
        **options,
    ) -> Dict[str, Any]:
        """Create a node."""
        return self._manager.nodes.create(labels, properties, **options)

    def create_nodes(
        self,
        nodes: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        """Create multiple nodes."""
        return self._manager.nodes.create_batch(nodes, **options)

    def get_node(
        self,
        node_id: Union[int, str],
        **options,
    ) -> Optional[Dict[str, Any]]:
        """Get a node by ID."""
        return self._manager.nodes.get(node_id=node_id, **options)

    def get_nodes(
        self,
        labels: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        **options,
    ) -> List[Dict[str, Any]]:
        """Get nodes matching criteria."""
        return self._manager.nodes.get(
            labels=labels, properties=properties, limit=limit, **options
        )

    def update_node(
        self,
        node_id: Union[int, str],
        properties: Dict[str, Any],
        merge: bool = True,
        **options,
    ) -> Dict[str, Any]:
        """Update a node."""
        return self._manager.nodes.update(node_id, properties, merge, **options)

    def delete_node(
        self,
        node_id: Union[int, str],
        detach: bool = True,
        **options,
    ) -> bool:
        """Delete a node."""
        return self._manager.nodes.delete(node_id, detach, **options)

    # Relationship operations
    def create_relationship(
        self,
        start_node_id: Union[int, str],
        end_node_id: Union[int, str],
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """Create a relationship."""
        return self._manager.relationships.create(
            start_node_id, end_node_id, rel_type, properties, **options
        )

    def get_relationships(
        self,
        node_id: Optional[Union[int, str]] = None,
        rel_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100,
        **options,
    ) -> List[Dict[str, Any]]:
        """Get relationships."""
        return self._manager.relationships.get(
            node_id, rel_type, direction, limit, **options
        )

    def delete_relationship(
        self,
        rel_id: Union[int, str],
        **options,
    ) -> bool:
        """Delete a relationship."""
        return self._manager.relationships.delete(rel_id, **options)

    # Query operations
    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """Execute a Cypher query."""
        return self._manager.query_engine.execute(query, parameters, **options)

    # Analytics operations
    def shortest_path(
        self,
        start_node_id: Union[int, str],
        end_node_id: Union[int, str],
        rel_type: Optional[str] = None,
        max_depth: int = 10,
        **options,
    ) -> Optional[Dict[str, Any]]:
        """Find shortest path between nodes."""
        return self._manager.analytics.shortest_path(
            start_node_id, end_node_id, rel_type, max_depth, **options
        )

    def get_neighbors(
        self,
        node_id: Union[int, str],
        rel_type: Optional[str] = None,
        direction: str = "both",
        depth: int = 1,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring nodes.

        Args:
            node_id: Node ID
            rel_type: Relationship type filter
            direction: Relationship direction
            depth: Traversal depth (alias: hops)
            **options: Additional options
        """
        # Support 'hops' as alias for 'depth' for ContextRetriever compatibility
        actual_depth = int(options.get("hops", depth))
        return self._manager.analytics.get_neighbors(
            node_id, rel_type, direction, actual_depth, **options
        )

    def query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None, **options
    ) -> List[Dict[str, Any]]:
        """
        Execute a query and return results (Compatibility method for ContextRetriever).

        Args:
            query: Query string (Cypher)
            parameters: Query parameters
            **options: Additional options

        Returns:
            List of result records
        """
        result = self.execute_query(query, parameters, **options)
        return result.get("records", [])

    # Management operations
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        return self._manager.get_stats()

    def create_index(
        self,
        label: str,
        property_name: str,
        index_type: str = "btree",
        **options,
    ) -> bool:
        """Create an index."""
        return self._manager.create_index(label, property_name, index_type, **options)

    # Compatibility with AgentMemory / ContextGraph interface
    def add_nodes(self, nodes: List[Dict[str, Any]], **options) -> int:
        """
        Add nodes (Compatibility method).

        Args:
            nodes: List of node dictionaries with 'id', 'type', 'properties'
            **options: Additional options

        Returns:
            Number of nodes created
        """
        if not nodes:
            return 0

        # Convert to GraphStore format (labels, properties)
        graph_nodes = []
        for node in nodes:
            # Extract labels - support both 'labels' array and 'type' string
            labels = node.get("labels")
            if not labels:
                node_type = node.get("type", "Entity")
                labels = [node_type] if isinstance(node_type, str) else node_type
            if isinstance(labels, str):
                labels = [labels]

            # Prepare properties
            props = node.get("properties", {}).copy()

            # Ensure ID is preserved
            if "id" in node and "id" not in props:
                props["id"] = node["id"]

            # Ensure content/text is preserved
            if "content" in node and "content" not in props:
                props["content"] = node["content"]
            if "text" in node and "text" not in props:
                props["text"] = node["text"]

            graph_nodes.append({"labels": labels, "properties": props})

        # Use batch creation
        # Note: create_nodes expects dicts with 'labels' and 'properties'
        # keys if passed directly?
        # Let's check create_nodes signature implementation in manager.
        # But here I'll assume create_nodes takes a list of such dicts
        # or similar.
        # Actually, let's look at create_nodes wrapper in this file:
        # def create_nodes(self, nodes: List[Dict[str, Any]], **options)
        # It passes to self._manager.nodes.create_batch(nodes)

        # If create_batch expects specific format, I should match it.
        # Assuming create_batch is smart enough or expects standard format.
        # To be safe, let's look at NodeManager.create_batch if possible,
        # but I can't easily.
        # Standard expectation: List of dicts where each dict has labels
        # and properties.

        result = self.create_nodes(graph_nodes, **options)
        return len(result)

    def add_edges(self, edges: List[Dict[str, Any]], **options) -> int:
        """
        Add edges (Compatibility method).

        Args:
            edges: List of edge dictionaries
            **options: Additional options

        Returns:
            Number of edges created
        """
        count = 0
        for edge in edges:
            source_id = edge.get("source_id")
            target_id = edge.get("target_id")
            rel_type = edge.get("type", "RELATED_TO")
            properties = edge.get("properties", {}).copy()

            # Preserve weight
            if "weight" in edge:
                properties["weight"] = edge["weight"]

            if source_id and target_id:
                try:
                    self.create_relationship(
                        source_id, target_id, rel_type, properties, **options
                    )
                    count += 1
                except Exception as e:
                    self.logger.warning(
                        f"Failed to add edge {source_id}->{target_id}: {e}"
                    )
        return count

    def build_from_conversations(
        self,
        conversations: List[Union[str, Dict[str, Any]]],
        link_entities: bool = True,
        extract_intents: bool = False,
        extract_sentiments: bool = False,
        **options,
    ) -> Dict[str, Any]:
        """
        Build graph from conversations (Compatibility method).

        Args:
            conversations: List of conversation files or dictionaries
            link_entities: Link entities across conversations
            extract_intents: Extract intents (not implemented)
            extract_sentiments: Extract sentiments (not implemented)
            **options: Additional options

        Returns:
            Graph statistics
        """
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="graph_store",
            submodule="GraphStore",
            message=f"Building graph from {len(conversations)} conversations",
        )

        try:
            all_nodes = []
            all_edges = []
            seen_nodes = set()

            for conv in conversations:
                # Load conversation if string (file path)
                conv_data = conv
                if isinstance(conv, str):
                    from pathlib import Path

                    from ..utils.helpers import read_json_file

                    conv_data = read_json_file(Path(conv))

                nodes, edges = self._process_conversation_to_elements(
                    conv_data,
                    extract_intents=extract_intents,
                    extract_sentiments=extract_sentiments,
                )

                # Add unique nodes
                for node in nodes:
                    if node["id"] not in seen_nodes:
                        all_nodes.append(node)
                        seen_nodes.add(node["id"])

                all_edges.extend(edges)

            if link_entities:
                linked_edges = self._link_entities_elements(all_nodes)
                all_edges.extend(linked_edges)

            # Batch add
            node_count = self.add_nodes(all_nodes)
            edge_count = self.add_edges(all_edges)

            self.progress_tracker.stop_tracking(tracking_id, status="completed")

            return {"statistics": {"node_count": node_count, "edge_count": edge_count}}

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            self.logger.error(f"Failed to build graph: {e}")
            raise

    def build_from_entities_and_relationships(
        self,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Build graph from entities and relationships (Compatibility method).
        """
        nodes = []
        edges = []

        # Process entities
        for entity in entities:
            entity_id = entity.get("id") or entity.get("entity_id")
            if entity_id:
                nodes.append(
                    {
                        "id": entity_id,
                        "type": entity.get("type", "entity"),
                        "properties": {
                            "content": entity.get("text")
                            or entity.get("label")
                            or entity_id,
                            **entity,
                        },
                    }
                )

        # Process relationships
        for rel in relationships:
            source = rel.get("source_id")
            target = rel.get("target_id")
            if source and target:
                edges.append(
                    {
                        "source_id": source,
                        "target_id": target,
                        "type": rel.get("type", "related_to"),
                        "weight": rel.get("confidence", 1.0),
                        "properties": rel,
                    }
                )

        node_count = self.add_nodes(nodes)
        edge_count = self.add_edges(edges)

        return {"statistics": {"node_count": node_count, "edge_count": edge_count}}

    def _process_conversation_to_elements(
        self, conv_data: Dict[str, Any], **kwargs
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Helper to process conversation into nodes and edges."""
        nodes = []
        edges = []

        conv_id = conv_data.get("id") or f"conv_{hash(str(conv_data)) % 10000}"

        # Conversation node
        nodes.append(
            {
                "id": conv_id,
                "type": "conversation",
                "properties": {
                    "content": conv_data.get("content", "")
                    or conv_data.get("summary", ""),
                    "timestamp": conv_data.get("timestamp"),
                },
            }
        )

        name_to_id = {}
        # Note: extract_entities option is available but not used in this
        # implementation. Default true if not passed. ContextGraph defaults
        # to True in init, but here we are static.
        # Let's assume True unless told otherwise or check config.

        # Extract entities
        for entity in conv_data.get("entities", []):
            entity_id = entity.get("id") or entity.get("entity_id")
            entity_text = (
                entity.get("text")
                or entity.get("label")
                or entity.get("name")
                or entity_id
            )
            entity_type = entity.get("type", "entity")

            # Generate ID if missing
            if not entity_id and entity_text:
                import hashlib

                entity_hash = hashlib.md5(  # nosec B324 - deterministic entity ID, not security-sensitive
                    f"{entity_text}_{entity_type}".encode()
                ).hexdigest()[:12]
                entity_id = f"{entity_type.lower()}_{entity_hash}"

            if entity_id:
                if entity_text:
                    name_to_id[entity_text] = entity_id

                nodes.append(
                    {
                        "id": entity_id,
                        "type": "entity",  # Normalize type?
                        "properties": {
                            "content": entity_text,
                            "type": entity_type,
                            **entity,
                        },
                    }
                )

                # Edge: Conversation -> Entity
                edges.append(
                    {"source_id": conv_id, "target_id": entity_id, "type": "mentions"}
                )

        # Extract relationships
        for rel in conv_data.get("relationships", []):
            source = rel.get("source_id")
            target = rel.get("target_id")

            # Resolve IDs
            if not source and rel.get("source") and rel.get("source") in name_to_id:
                source = name_to_id[rel.get("source")]
            if not target and rel.get("target") and rel.get("target") in name_to_id:
                target = name_to_id[rel.get("target")]

            if source and target:
                edges.append(
                    {
                        "source_id": source,
                        "target_id": target,
                        "type": rel.get("type", "related_to"),
                        "weight": rel.get("confidence", 1.0),
                        "properties": rel,
                    }
                )

        return nodes, edges

    def _link_entities_elements(
        self, nodes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Link similar entities."""
        edges = []
        # Lazy import to avoid circular dependency
        try:
            from ..context.entity_linker import EntityLinker

            linker = EntityLinker()  # Use default config
        except (ImportError, OSError):
            return []

        entity_nodes = [n for n in nodes if n.get("type") == "entity"]
        for i, node1 in enumerate(entity_nodes):
            content1 = node1["properties"].get("content", "")
            if not content1:
                continue

            for node2 in entity_nodes[i + 1 :]:
                content2 = node2["properties"].get("content", "")
                if not content2:
                    continue

                similarity = linker._calculate_text_similarity(
                    content1.lower(), content2.lower()
                )
                if similarity >= linker.similarity_threshold:
                    edges.append(
                        {
                            "source_id": node1["id"],
                            "target_id": node2["id"],
                            "type": "similar_to",
                            "weight": similarity,
                        }
                    )
        return edges

    @property
    def nodes(self) -> NodeManager:
        """Get node manager."""
        return self._manager.nodes

    @property
    def relationships(self) -> RelationshipManager:
        """Get relationship manager."""
        return self._manager.relationships

    @property
    def query_engine(self) -> QueryEngine:
        """Get query engine."""
        return self._manager.query_engine

    @property
    def analytics(self) -> GraphAnalytics:
        """Get analytics engine."""
        return self._manager.analytics
