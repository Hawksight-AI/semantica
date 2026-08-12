"""
FalkorDB Store Module

This module provides FalkorDB integration for ultra-fast property graph storage and
OpenCypher querying in the Semantica framework. FalkorDB is a high-performance
knowledge graph database built on Redis, using sparse matrices for adjacency
representation and linear algebra for query execution.

Key Features:
    - Ultra-fast graph operations using sparse matrices
    - Full OpenCypher query language support
    - Redis-based storage (requires Redis server or Docker)
    - Multi-tenant graph support
    - Linear algebra based querying
    - Node and relationship CRUD operations
    - Graph algorithms and analytics
    - Batch operations with progress tracking
    - Optional dependency handling

Main Classes:
    - FalkorDBStore: Main FalkorDB store for graph operations
    - FalkorDBClient: FalkorDB client wrapper
    - FalkorDBGraph: Graph wrapper with operations
    - FalkorDBQuery: Query execution wrapper

Example Usage:
    >>> from semantica.graph_store import FalkorDBStore
    >>> store = FalkorDBStore(host="localhost", port=6379)
    >>> store.connect()
    >>> graph = store.select_graph("MotoGP")
    >>> store.create_node(["Rider"], {"name": "Valentino Rossi"})
    >>> results = store.execute_query("MATCH (r:Rider) RETURN r.name")
    >>> store.close()

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .query_sanitize import sanitize_identifier

# Optional FalkorDB import
try:
    from falkordb import FalkorDB

    FALKORDB_AVAILABLE = True
except (ImportError, OSError):
    FALKORDB_AVAILABLE = False
    FalkorDB = None


class FalkorDBClient:
    """FalkorDB client wrapper."""

    def __init__(self, client: Any):
        """Initialize FalkorDB client wrapper."""
        self.client = client
        self.logger = get_logger("falkordb_client")

    def select_graph(self, graph_name: str) -> "FalkorDBGraph":
        """
        Select or create a graph.

        Args:
            graph_name: Name of the graph

        Returns:
            FalkorDBGraph instance
        """
        if not FALKORDB_AVAILABLE:
            raise ProcessingError("FalkorDB not available")

        try:
            graph = self.client.select_graph(graph_name)
            return FalkorDBGraph(graph, graph_name)
        except Exception as e:
            raise ProcessingError(f"Failed to select graph: {str(e)}")

    def list_graphs(self) -> List[str]:
        """List all available graphs."""
        if not FALKORDB_AVAILABLE:
            raise ProcessingError("FalkorDB not available")

        try:
            return self.client.list_graphs()
        except Exception as e:
            raise ProcessingError(f"Failed to list graphs: {str(e)}")


class FalkorDBGraph:
    """FalkorDB graph wrapper."""

    def __init__(self, graph: Any, name: str):
        """Initialize FalkorDB graph wrapper."""
        self.graph = graph
        self.name = name
        self.logger = get_logger("falkordb_graph")

    def query(self, query: str, params: Optional[Dict[str, Any]] = None) -> "FalkorDBQuery":
        """
        Execute an OpenCypher query.

        Args:
            query: OpenCypher query string
            params: Query parameters

        Returns:
            FalkorDBQuery result wrapper
        """
        if not FALKORDB_AVAILABLE:
            raise ProcessingError("FalkorDB not available")

        try:
            if params:
                result = self.graph.query(query, params)
            else:
                result = self.graph.query(query)
            return FalkorDBQuery(result)
        except Exception as e:
            raise ProcessingError(f"Query execution failed: {str(e)}")

    def delete(self) -> bool:
        """Delete the graph."""
        if not FALKORDB_AVAILABLE:
            raise ProcessingError("FalkorDB not available")

        try:
            self.graph.delete()
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to delete graph: {str(e)}")


class FalkorDBQuery:
    """FalkorDB query result wrapper."""

    def __init__(self, result: Any):
        """Initialize FalkorDB query result wrapper."""
        self.result = result
        self.logger = get_logger("falkordb_query")

    @property
    def result_set(self) -> List[List[Any]]:
        """Get the result set as a list of rows."""
        if self.result:
            return self.result.result_set
        return []

    @property
    def header(self) -> List[str]:
        """Get column headers."""
        if self.result and hasattr(self.result, "header"):
            return self.result.header
        return []

    @property
    def statistics(self) -> Dict[str, Any]:
        """Get query statistics."""
        if self.result:
            stats = {}
            if hasattr(self.result, "nodes_created"):
                stats["nodes_created"] = self.result.nodes_created
            if hasattr(self.result, "relationships_created"):
                stats["relationships_created"] = self.result.relationships_created
            if hasattr(self.result, "nodes_deleted"):
                stats["nodes_deleted"] = self.result.nodes_deleted
            if hasattr(self.result, "relationships_deleted"):
                stats["relationships_deleted"] = self.result.relationships_deleted
            if hasattr(self.result, "properties_set"):
                stats["properties_set"] = self.result.properties_set
            if hasattr(self.result, "run_time_ms"):
                stats["run_time_ms"] = self.result.run_time_ms
            return stats
        return {}


class FalkorDBStore:
    """
    FalkorDB store for ultra-fast property graph storage and OpenCypher querying.

    • FalkorDB connection and authentication
    • Multi-graph support
    • Node and relationship CRUD operations
    • OpenCypher query execution
    • Sparse matrix based graph representation
    • Linear algebra query optimization
    • Performance optimization
    • Error handling and recovery
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        graph_name: Optional[str] = None,
        **config,
    ):
        """
        Initialize FalkorDB store.

        Args:
            host: FalkorDB/Redis host
            port: FalkorDB/Redis port
            password: Redis password (if required)
            graph_name: Default graph name
            **config: Additional configuration options
        """
        self.logger = get_logger("falkordb_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.host = host or config.get("host", "localhost")
        self.port = port or config.get("port", 6379)
        self.password = password or config.get("password")
        self.default_graph_name = graph_name or config.get("graph_name", "default")

        self._client: Optional[FalkorDBClient] = None
        self._graph: Optional[FalkorDBGraph] = None

        # Check FalkorDB availability
        if not FALKORDB_AVAILABLE:
            self.logger.warning(
                "FalkorDB not available. Install with: pip install falkordb"
            )

    def connect(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        **options,
    ) -> bool:
        """
        Connect to FalkorDB server.

        Args:
            host: FalkorDB/Redis host
            port: FalkorDB/Redis port
            password: Redis password
            **options: Connection options

        Returns:
            True if connected successfully
        """
        if not FALKORDB_AVAILABLE:
            raise ProcessingError(
                "FalkorDB is not available. Install it with: pip install falkordb"
            )

        host = host or self.host
        port = port or self.port
        password = password or self.password

        try:
            if password:
                db = FalkorDB(host=host, port=port, password=password)
            else:
                db = FalkorDB(host=host, port=port)

            self._client = FalkorDBClient(db)
            self.logger.info(f"Connected to FalkorDB at {host}:{port}")
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to connect to FalkorDB: {str(e)}")

    def close(self) -> None:
        """Close connection to FalkorDB."""
        self._graph = None
        self._client = None
        self.logger.info("Disconnected from FalkorDB")

    def _ensure_client(self) -> FalkorDBClient:
        """Ensure client is connected."""
        if self._client is None:
            self.connect()
        return self._client

    def select_graph(self, graph_name: Optional[str] = None) -> FalkorDBGraph:
        """
        Select or create a graph.

        Args:
            graph_name: Name of the graph

        Returns:
            FalkorDBGraph instance
        """
        client = self._ensure_client()
        graph_name = graph_name or self.default_graph_name
        self._graph = client.select_graph(graph_name)
        return self._graph

    def _ensure_graph(self) -> FalkorDBGraph:
        """Ensure a graph is selected."""
        if self._graph is None:
            self.select_graph()
        return self._graph

    def create_node(
        self,
        labels: List[str],
        properties: Dict[str, Any],
        **options,
    ) -> Dict[str, Any]:
        """
        Create a node in the graph.

        Args:
            labels: Node labels
            properties: Node properties
            **options: Additional options

        Returns:
            Created node information
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="FalkorDBStore",
            message=f"Creating node with labels {labels}",
        )

        try:
            graph = self._ensure_graph()

            label_str = ":".join(sanitize_identifier(l, "label") for l in labels)

            # Build property string for Cypher
            props_str = ", ".join(
                f"{sanitize_identifier(k, 'property key')}: ${k}" for k in properties.keys()
            )

            query = f"CREATE (n:{label_str} {{{props_str}}}) RETURN id(n) as id, n"
            result = graph.query(query, properties)

            node_data = {
                "labels": labels,
                "properties": properties,
            }

            if result.result_set and len(result.result_set) > 0:
                row = result.result_set[0]
                if len(row) > 0:
                    node_data["id"] = row[0]

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created node with labels {labels}",
            )
            return node_data

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create node: {str(e)}")

    def create_nodes(
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
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="FalkorDBStore",
            message=f"Creating {len(nodes)} nodes in batch",
        )

        try:
            graph = self._ensure_graph()
            created_nodes = []

            for node in nodes:
                labels = node.get("labels", [])
                properties = node.get("properties", {})

                label_str = ":".join(sanitize_identifier(l, "label") for l in labels) if labels else "Node"
                props_str = ", ".join(
                    f"{sanitize_identifier(k, 'property key')}: ${k}" for k in properties.keys()
                )

                query = f"CREATE (n:{label_str} {{{props_str}}}) RETURN id(n) as id"
                result = graph.query(query, properties)

                node_data = {
                    "labels": labels,
                    "properties": properties,
                }

                if result.result_set and len(result.result_set) > 0:
                    node_data["id"] = result.result_set[0][0]

                created_nodes.append(node_data)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created {len(created_nodes)} nodes",
            )
            return created_nodes

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create nodes: {str(e)}")

    def get_nodes(
        self,
        labels: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get nodes matching criteria.

        Args:
            labels: Filter by labels
            properties: Filter by properties
            limit: Maximum number of nodes
            **options: Additional options

        Returns:
            List of matching nodes
        """
        try:
            graph = self._ensure_graph()

            # Build query
            if labels:
                label_str = ":".join(sanitize_identifier(l, "label") for l in labels)
                query = f"MATCH (n:{label_str})"
            else:
                query = "MATCH (n)"

            # Add property filters
            if properties:
                conditions = []
                for key in properties.keys():
                    safe_key = sanitize_identifier(key, "property key")
                    conditions.append(f"n.{safe_key} = ${safe_key}")
                query += " WHERE " + " AND ".join(conditions)

            query += f" RETURN id(n) as id, n, labels(n) as labels LIMIT {limit}"

            result = graph.query(query, properties or {})

            nodes = []
            for row in result.result_set:
                if len(row) >= 2:
                    node_data = {
                        "id": row[0],
                        "properties": dict(row[1]) if hasattr(row[1], "__iter__") else {},
                    }
                    if len(row) >= 3:
                        node_data["labels"] = row[2] if isinstance(row[2], list) else []
                    nodes.append(node_data)

            return nodes

        except Exception as e:
            raise ProcessingError(f"Failed to get nodes: {str(e)}")

    def update_node(
        self,
        node_id: int,
        properties: Dict[str, Any],
        merge: bool = True,
        **options,
    ) -> Dict[str, Any]:
        """
        Update a node's properties.

        Args:
            node_id: Node ID
            properties: Properties to update
            merge: If True, merge properties; if False, replace
            **options: Additional options

        Returns:
            Updated node information
        """
        try:
            graph = self._ensure_graph()

            # Build SET clause
            set_parts = []
            for key in properties.keys():
                safe_key = sanitize_identifier(key, "property key")
                set_parts.append(f"n.{safe_key} = ${safe_key}")

            if merge:
                query = f"MATCH (n) WHERE id(n) = $node_id SET {', '.join(set_parts)} RETURN id(n) as id, n, labels(n) as labels"
            else:
                query = f"MATCH (n) WHERE id(n) = $node_id SET n = $props RETURN id(n) as id, n, labels(n) as labels"

            params = {"node_id": node_id, **properties}
            if not merge:
                params["props"] = properties

            result = graph.query(query, params)

            if result.result_set and len(result.result_set) > 0:
                row = result.result_set[0]
                return {
                    "id": row[0],
                    "properties": dict(row[1]) if len(row) > 1 else properties,
                    "labels": row[2] if len(row) > 2 else [],
                }
            else:
                raise ProcessingError(f"Node with ID {node_id} not found")

        except Exception as e:
            raise ProcessingError(f"Failed to update node: {str(e)}")

    def delete_node(
        self,
        node_id: int,
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
            True if deleted successfully
        """
        try:
            graph = self._ensure_graph()

            if detach:
                query = "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n"
            else:
                query = "MATCH (n) WHERE id(n) = $node_id DELETE n"

            graph.query(query, {"node_id": node_id})
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to delete node: {str(e)}")

    def create_relationship(
        self,
        start_node_id: int,
        end_node_id: int,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Create a relationship between two nodes.

        Args:
            start_node_id: Start node ID
            end_node_id: End node ID
            rel_type: Relationship type
            properties: Relationship properties
            **options: Additional options

        Returns:
            Created relationship information
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="FalkorDBStore",
            message=f"Creating relationship [{rel_type}]",
        )

        try:
            graph = self._ensure_graph()
            properties = properties or {}

            safe_rel_type = sanitize_identifier(rel_type, "relationship type")

            # Build property string
            if properties:
                props_str = ", ".join(
                    f"{sanitize_identifier(k, 'property key')}: ${k}" for k in properties.keys()
                )
                props_str = f" {{{props_str}}}"
            else:
                props_str = ""

            query = f"""
                MATCH (a), (b)
                WHERE id(a) = $start_id AND id(b) = $end_id
                CREATE (a)-[r:{safe_rel_type}{props_str}]->(b)
                RETURN id(r) as id, type(r) as type
            """

            params = {"start_id": start_node_id, "end_id": end_node_id, **properties}
            result = graph.query(query, params)

            rel_data = {
                "type": rel_type,
                "start_node_id": start_node_id,
                "end_node_id": end_node_id,
                "properties": properties,
            }

            if result.result_set and len(result.result_set) > 0:
                row = result.result_set[0]
                rel_data["id"] = row[0]

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created relationship [{rel_type}]",
            )
            return rel_data

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to create relationship: {str(e)}")

    def get_relationships(
        self,
        node_id: Optional[int] = None,
        rel_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Get relationships matching criteria.

        Args:
            node_id: Filter by node ID
            rel_type: Filter by relationship type
            direction: Direction ("in", "out", "both")
            limit: Maximum number of relationships
            **options: Additional options

        Returns:
            List of matching relationships
        """
        try:
            graph = self._ensure_graph()
            type_filter = f":{sanitize_identifier(rel_type, 'relationship type')}" if rel_type else ""

            if node_id is not None:
                if direction == "out":
                    query = f"""
                        MATCH (a)-[r{type_filter}]->(b)
                        WHERE id(a) = $node_id
                        RETURN id(r) as id, type(r) as type, id(a) as start_id, id(b) as end_id, r
                        LIMIT {limit}
                    """
                elif direction == "in":
                    query = f"""
                        MATCH (a)<-[r{type_filter}]-(b)
                        WHERE id(a) = $node_id
                        RETURN id(r) as id, type(r) as type, id(b) as start_id, id(a) as end_id, r
                        LIMIT {limit}
                    """
                else:
                    query = f"""
                        MATCH (a)-[r{type_filter}]-(b)
                        WHERE id(a) = $node_id
                        RETURN id(r) as id, type(r) as type, id(startNode(r)) as start_id, id(endNode(r)) as end_id, r
                        LIMIT {limit}
                    """
                result = graph.query(query, {"node_id": node_id})
            else:
                query = f"""
                    MATCH (a)-[r{type_filter}]->(b)
                    RETURN id(r) as id, type(r) as type, id(a) as start_id, id(b) as end_id, r
                    LIMIT {limit}
                """
                result = graph.query(query)

            relationships = []
            for row in result.result_set:
                if len(row) >= 4:
                    rel_data = {
                        "id": row[0],
                        "type": row[1],
                        "start_node_id": row[2],
                        "end_node_id": row[3],
                    }
                    if len(row) > 4:
                        rel_data["properties"] = dict(row[4]) if hasattr(row[4], "__iter__") else {}
                    relationships.append(rel_data)

            return relationships

        except Exception as e:
            raise ProcessingError(f"Failed to get relationships: {str(e)}")

    def delete_relationship(
        self,
        rel_id: int,
        **options,
    ) -> bool:
        """
        Delete a relationship.

        Args:
            rel_id: Relationship ID
            **options: Additional options

        Returns:
            True if deleted successfully
        """
        try:
            graph = self._ensure_graph()
            query = "MATCH ()-[r]->() WHERE id(r) = $rel_id DELETE r"
            graph.query(query, {"rel_id": rel_id})
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to delete relationship: {str(e)}")

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Execute an OpenCypher query.

        Args:
            query: OpenCypher query string
            parameters: Query parameters
            **options: Additional options

        Returns:
            Query results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="FalkorDBStore",
            message="Executing OpenCypher query",
        )

        try:
            graph = self._ensure_graph()
            result = graph.query(query, parameters or {})

            records = []
            for row in result.result_set:
                # Convert row to dictionary or list
                records.append(list(row))

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Query returned {len(records)} records",
            )

            return {
                "success": True,
                "records": records,
                "header": result.header,
                "statistics": result.statistics,
                "metadata": {"query": query},
            }

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Query execution failed: {str(e)}")

    def get_neighbors(
        self,
        node_id: int,
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
        try:
            graph = self._ensure_graph()
            type_filter = f":{sanitize_identifier(rel_type, 'relationship type')}" if rel_type else ""
            depth = int(depth)

            if direction == "out":
                pattern = f"-[r{type_filter}*1..{depth}]->"
            elif direction == "in":
                pattern = f"<-[r{type_filter}*1..{depth}]-"
            else:
                pattern = f"-[r{type_filter}*1..{depth}]-"

            query = f"""
                MATCH (start){pattern}(neighbor)
                WHERE id(start) = $node_id
                RETURN DISTINCT id(neighbor) as id, neighbor, labels(neighbor) as labels
            """

            result = graph.query(query, {"node_id": node_id})

            neighbors = []
            for row in result.result_set:
                if len(row) >= 2:
                    neighbors.append({
                        "id": row[0],
                        "properties": dict(row[1]) if hasattr(row[1], "__iter__") else {},
                        "labels": row[2] if len(row) > 2 else [],
                    })

            return neighbors

        except Exception as e:
            raise ProcessingError(f"Failed to get neighbors: {str(e)}")

    def shortest_path(
        self,
        start_node_id: int,
        end_node_id: int,
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
            Shortest path information or None if not found
        """
        try:
            graph = self._ensure_graph()
            type_filter = f":{sanitize_identifier(rel_type, 'relationship type')}" if rel_type else ""
            max_depth = int(max_depth)

            query = f"""
                MATCH path = shortestPath((start)-[r{type_filter}*..{max_depth}]-(end))
                WHERE id(start) = $start_id AND id(end) = $end_id
                RETURN path, length(path) as length
            """

            result = graph.query(query, {
                "start_id": start_node_id,
                "end_id": end_node_id,
            })

            if result.result_set and len(result.result_set) > 0:
                row = result.result_set[0]
                path = row[0]

                # Extract path information
                nodes = []
                relationships = []

                if hasattr(path, "nodes"):
                    for node in path.nodes():
                        nodes.append({
                            "id": node.id if hasattr(node, "id") else None,
                            "labels": list(node.labels) if hasattr(node, "labels") else [],
                            "properties": dict(node.properties) if hasattr(node, "properties") else {},
                        })

                if hasattr(path, "edges"):
                    for rel in path.edges():
                        relationships.append({
                            "id": rel.id if hasattr(rel, "id") else None,
                            "type": rel.relation if hasattr(rel, "relation") else None,
                            "properties": dict(rel.properties) if hasattr(rel, "properties") else {},
                        })

                return {
                    "length": row[1] if len(row) > 1 else len(relationships),
                    "nodes": nodes,
                    "relationships": relationships,
                }

            return None

        except Exception as e:
            raise ProcessingError(f"Failed to find shortest path: {str(e)}")

    def create_index(
        self,
        label: str,
        property_name: str,
        index_type: str = "range",
        **options,
    ) -> bool:
        """
        Create an index on a property.

        Args:
            label: Node label
            property_name: Property to index
            index_type: Index type (range, fulltext)
            **options: Additional options

        Returns:
            True if index created successfully
        """
        try:
            graph = self._ensure_graph()
            safe_label = sanitize_identifier(label, "label")
            safe_property = sanitize_identifier(property_name, "property key")

            if index_type == "fulltext":
                query = f"CALL db.idx.fulltext.createNodeIndex('{safe_label}', '{safe_property}')"
            else:
                query = f"CREATE INDEX FOR (n:{safe_label}) ON (n.{safe_property})"

            graph.query(query)
            self.logger.info(f"Created {index_type} index on {label}.{property_name}")
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to create index: {str(e)}")

    def list_graphs(self) -> List[str]:
        """List all available graphs."""
        client = self._ensure_client()
        return client.list_graphs()

    def delete_graph(self, graph_name: Optional[str] = None) -> bool:
        """
        Delete a graph.

        Args:
            graph_name: Graph name (uses default if not provided)

        Returns:
            True if deleted successfully
        """
        try:
            client = self._ensure_client()
            graph = client.select_graph(graph_name or self.default_graph_name)
            graph.delete()
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to delete graph: {str(e)}")

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        try:
            graph = self._ensure_graph()

            stats = {
                "graph_name": self._graph.name if self._graph else "unknown",
            }

            # Node count
            result = graph.query("MATCH (n) RETURN count(n) as count")
            if result.result_set and len(result.result_set) > 0:
                stats["node_count"] = result.result_set[0][0]

            # Relationship count
            result = graph.query("MATCH ()-[r]->() RETURN count(r) as count")
            if result.result_set and len(result.result_set) > 0:
                stats["relationship_count"] = result.result_set[0][0]

            # Label counts
            result = graph.query("""
                MATCH (n)
                UNWIND labels(n) as label
                RETURN label, count(*) as count
                ORDER BY count DESC
            """)
            stats["label_counts"] = {
                row[0]: row[1] for row in result.result_set
            }

            # Relationship type counts
            result = graph.query("""
                MATCH ()-[r]->()
                RETURN type(r) as type, count(*) as count
                ORDER BY count DESC
            """)
            stats["relationship_type_counts"] = {
                row[0]: row[1] for row in result.result_set
            }

            return stats

        except Exception as e:
            self.logger.warning(f"Failed to get stats: {str(e)}")
            return {"status": "error", "message": str(e)}

