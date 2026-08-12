"""
Neo4j Store Module

This module provides Neo4j graph database integration for property graph storage and
Cypher querying in the Semantica framework, supporting full CRUD operations,
transactions, and graph analytics.

Key Features:
    - Full Cypher query language support
    - Node and relationship CRUD operations
    - Transaction support with rollback
    - Multi-database support
    - Index and constraint management
    - Graph algorithms via GDS library
    - Batch operations with progress tracking
    - Optional dependency handling

Main Classes:
    - Neo4jStore: Main Neo4j store for graph operations
    - Neo4jDriver: Neo4j driver wrapper
    - Neo4jSession: Session management wrapper
    - Neo4jTransaction: Transaction wrapper

Example Usage:
    >>> from semantica.graph_store import Neo4jStore
    >>> store = Neo4jStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    >>> store.connect()
    >>> node_id = store.create_node(labels=["Person"], properties={"name": "Alice"})
    >>> results = store.execute_query("MATCH (p:Person) RETURN p.name")
    >>> store.close()

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .query_sanitize import sanitize_identifier

# Optional Neo4j import
try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import (
        AuthError,
        Neo4jError,
        ServiceUnavailable,
        TransactionError,
    )

    NEO4J_AVAILABLE = True
except (ImportError, OSError):
    NEO4J_AVAILABLE = False
    GraphDatabase = None
    Neo4jError = Exception
    AuthError = Exception
    ServiceUnavailable = Exception
    TransactionError = Exception


class Neo4jDriver:
    """Neo4j driver wrapper."""

    def __init__(self, driver: Any):
        """Initialize Neo4j driver wrapper."""
        self.driver = driver
        self.logger = get_logger("neo4j_driver")

    def session(self, database: Optional[str] = None) -> "Neo4jSession":
        """
        Create a new session.

        Args:
            database: Database name (optional)

        Returns:
            Neo4jSession instance
        """
        if not NEO4J_AVAILABLE:
            raise ProcessingError("Neo4j not available")

        try:
            if database:
                session = self.driver.session(database=database)
            else:
                session = self.driver.session()
            return Neo4jSession(session)
        except Exception as e:
            raise ProcessingError(f"Failed to create session: {str(e)}")

    def verify_connectivity(self) -> bool:
        """Verify connectivity to Neo4j server."""
        if not NEO4J_AVAILABLE:
            return False

        try:
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            self.logger.warning(f"Connectivity check failed: {e}")
            return False

    def close(self) -> None:
        """Close the driver."""
        if self.driver:
            self.driver.close()


class Neo4jSession:
    """Neo4j session wrapper."""

    def __init__(self, session: Any):
        """Initialize Neo4j session wrapper."""
        self.session = session
        self.logger = get_logger("neo4j_session")

    def run(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Any:
        """
        Run a Cypher query.

        Args:
            query: Cypher query string
            parameters: Query parameters

        Returns:
            Query result
        """
        if not NEO4J_AVAILABLE:
            raise ProcessingError("Neo4j not available")

        try:
            result = self.session.run(query, parameters or {})
            return result
        except Exception as e:
            raise ProcessingError(f"Query execution failed: {str(e)}")

    def begin_transaction(self) -> "Neo4jTransaction":
        """Begin a new transaction."""
        if not NEO4J_AVAILABLE:
            raise ProcessingError("Neo4j not available")

        try:
            tx = self.session.begin_transaction()
            return Neo4jTransaction(tx)
        except Exception as e:
            raise ProcessingError(f"Failed to begin transaction: {str(e)}")

    def read_transaction(self, func: Any, **kwargs) -> Any:
        """Execute a read transaction."""
        return self.session.execute_read(func, **kwargs)

    def write_transaction(self, func: Any, **kwargs) -> Any:
        """Execute a write transaction."""
        return self.session.execute_write(func, **kwargs)

    def close(self) -> None:
        """Close the session."""
        if self.session:
            self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class Neo4jTransaction:
    """Neo4j transaction wrapper."""

    def __init__(self, transaction: Any):
        """Initialize Neo4j transaction wrapper."""
        self.transaction = transaction
        self.logger = get_logger("neo4j_transaction")

    def run(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Any:
        """
        Run a Cypher query within the transaction.

        Args:
            query: Cypher query string
            parameters: Query parameters

        Returns:
            Query result
        """
        if not NEO4J_AVAILABLE:
            raise ProcessingError("Neo4j not available")

        try:
            result = self.transaction.run(query, parameters or {})
            return result
        except Exception as e:
            raise ProcessingError(f"Transaction query failed: {str(e)}")

    def commit(self) -> None:
        """Commit the transaction."""
        if self.transaction:
            self.transaction.commit()

    def rollback(self) -> None:
        """Rollback the transaction."""
        if self.transaction:
            self.transaction.rollback()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


class Neo4jStore:
    """
    Neo4j store for property graph storage and Cypher querying.

    • Neo4j connection and authentication
    • Node and relationship CRUD operations
    • Cypher query execution
    • Transaction support
    • Index and constraint management
    • Performance optimization
    • Error handling and recovery
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        **config,
    ):
        """
        Initialize Neo4j store.

        Args:
            uri: Neo4j connection URI (bolt://localhost:7687)
            user: Neo4j username
            password: Neo4j password
            database: Database name
            **config: Additional configuration options
        """
        self.logger = get_logger("neo4j_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.uri = uri or config.get("uri", "bolt://localhost:7687")
        self.user = user or config.get("user", "neo4j")
        self.password = password or config.get("password", "password")
        self.database = database or config.get("database", "neo4j")
        self.encrypted = config.get("encrypted", False)

        self._driver: Optional[Neo4jDriver] = None
        self._session: Optional[Neo4jSession] = None

        # Check Neo4j availability
        if not NEO4J_AVAILABLE:
            self.logger.warning(
                "Neo4j not available. Install with: pip install neo4j"
            )

    def connect(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        **options,
    ) -> bool:
        """
        Connect to Neo4j server.

        Args:
            uri: Neo4j connection URI
            user: Username
            password: Password
            **options: Connection options

        Returns:
            True if connected successfully
        """
        if not NEO4J_AVAILABLE:
            raise ProcessingError(
                "Neo4j is not available. Install it with: pip install neo4j"
            )

        uri = uri or self.uri
        user = user or self.user
        password = password or self.password

        try:
            driver = GraphDatabase.driver(uri, auth=(user, password), **options)
            self._driver = Neo4jDriver(driver)

            # Verify connectivity
            if self._driver.verify_connectivity():
                self.logger.info(f"Connected to Neo4j at {uri}")
                return True
            else:
                raise ProcessingError("Could not verify connectivity to Neo4j")

        except AuthError as e:
            raise ProcessingError(f"Neo4j authentication failed: {str(e)}")
        except ServiceUnavailable as e:
            raise ProcessingError(f"Neo4j service unavailable: {str(e)}")
        except Exception as e:
            raise ProcessingError(f"Failed to connect to Neo4j: {str(e)}")

    def close(self) -> None:
        """Close connection to Neo4j."""
        if self._session:
            self._session.close()
            self._session = None
        if self._driver:
            self._driver.close()
            self._driver = None
        self.logger.info("Disconnected from Neo4j")

    def get_session(self, database: Optional[str] = None) -> Neo4jSession:
        """
        Get or create a session.

        Args:
            database: Database name

        Returns:
            Neo4jSession instance
        """
        if self._driver is None:
            self.connect()

        return self._driver.session(database or self.database)

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
            Created node information including ID
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="Neo4jStore",
            message=f"Creating node with labels {labels}",
        )

        try:
            label_str = ":".join(sanitize_identifier(l, "label") for l in labels)
            query = f"CREATE (n:{label_str} $props) RETURN id(n) as id, n"

            with self.get_session() as session:
                result = session.run(query, {"props": properties})
                record = result.single()

                if record:
                    node_data = {
                        "id": record["id"],
                        "labels": labels,
                        "properties": dict(record["n"]),
                    }

                    self.progress_tracker.stop_tracking(
                        tracking_id,
                        status="completed",
                        message=f"Created node with ID {record['id']}",
                    )
                    return node_data
                else:
                    raise ProcessingError("Failed to create node - no result returned")

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
            submodule="Neo4jStore",
            message=f"Creating {len(nodes)} nodes in batch",
        )

        try:
            created_nodes = []

            with self.get_session() as session:
                for node in nodes:
                    labels = node.get("labels", [])
                    properties = node.get("properties", {})

                    label_str = ":".join(sanitize_identifier(l, "label") for l in labels) if labels else "Node"
                    query = f"CREATE (n:{label_str} $props) RETURN id(n) as id, n"

                    result = session.run(query, {"props": properties})
                    record = result.single()

                    if record:
                        created_nodes.append({
                            "id": record["id"],
                            "labels": labels,
                            "properties": dict(record["n"]),
                        })

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

    def get_node(
        self,
        node_id: int,
        **options,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a node by ID.

        Args:
            node_id: Node ID
            **options: Additional options

        Returns:
            Node information or None if not found
        """
        try:
            query = "MATCH (n) WHERE id(n) = $id RETURN n, labels(n) as labels"

            with self.get_session() as session:
                result = session.run(query, {"id": node_id})
                record = result.single()

                if record:
                    return {
                        "id": node_id,
                        "labels": record["labels"],
                        "properties": dict(record["n"]),
                    }
                return None

        except Exception as e:
            raise ProcessingError(f"Failed to get node: {str(e)}")

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
            limit: Maximum number of nodes to return
            **options: Additional options

        Returns:
            List of matching nodes
        """
        try:
            # Build query
            if labels:
                label_str = ":".join(sanitize_identifier(l, "label") for l in labels)
                query = f"MATCH (n:{label_str})"
            else:
                query = "MATCH (n)"

            # Add property filters
            if properties:
                conditions = []
                for key, value in properties.items():
                    safe_key = sanitize_identifier(key, "property key")
                    conditions.append(f"n.{safe_key} = ${safe_key}")
                query += " WHERE " + " AND ".join(conditions)

            query += f" RETURN id(n) as id, n, labels(n) as labels LIMIT {limit}"

            with self.get_session() as session:
                result = session.run(query, properties or {})

                nodes = []
                for record in result:
                    nodes.append({
                        "id": record["id"],
                        "labels": record["labels"],
                        "properties": dict(record["n"]),
                    })

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
            if merge:
                query = "MATCH (n) WHERE id(n) = $id SET n += $props RETURN id(n) as id, n, labels(n) as labels"
            else:
                query = "MATCH (n) WHERE id(n) = $id SET n = $props RETURN id(n) as id, n, labels(n) as labels"

            with self.get_session() as session:
                result = session.run(query, {"id": node_id, "props": properties})
                record = result.single()

                if record:
                    return {
                        "id": record["id"],
                        "labels": record["labels"],
                        "properties": dict(record["n"]),
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
            if detach:
                query = "MATCH (n) WHERE id(n) = $id DETACH DELETE n"
            else:
                query = "MATCH (n) WHERE id(n) = $id DELETE n"

            with self.get_session() as session:
                session.run(query, {"id": node_id})
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
            submodule="Neo4jStore",
            message=f"Creating relationship [{rel_type}]",
        )

        try:
            properties = properties or {}
            safe_rel_type = sanitize_identifier(rel_type, "relationship type")
            query = f"""
                MATCH (a), (b)
                WHERE id(a) = $start_id AND id(b) = $end_id
                CREATE (a)-[r:{safe_rel_type} $props]->(b)
                RETURN id(r) as id, type(r) as type, r
            """

            with self.get_session() as session:
                result = session.run(query, {
                    "start_id": start_node_id,
                    "end_id": end_node_id,
                    "props": properties,
                })
                record = result.single()

                if record:
                    rel_data = {
                        "id": record["id"],
                        "type": record["type"],
                        "start_node_id": start_node_id,
                        "end_node_id": end_node_id,
                        "properties": dict(record["r"]),
                    }

                    self.progress_tracker.stop_tracking(
                        tracking_id,
                        status="completed",
                        message=f"Created relationship with ID {record['id']}",
                    )
                    return rel_data
                else:
                    raise ProcessingError("Failed to create relationship - nodes not found")

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
            else:
                query = f"""
                    MATCH (a)-[r{type_filter}]->(b)
                    RETURN id(r) as id, type(r) as type, id(a) as start_id, id(b) as end_id, r
                    LIMIT {limit}
                """

            with self.get_session() as session:
                result = session.run(query, {"node_id": node_id})

                relationships = []
                for record in result:
                    relationships.append({
                        "id": record["id"],
                        "type": record["type"],
                        "start_node_id": record["start_id"],
                        "end_node_id": record["end_id"],
                        "properties": dict(record["r"]),
                    })

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
            query = "MATCH ()-[r]->() WHERE id(r) = $id DELETE r"

            with self.get_session() as session:
                session.run(query, {"id": rel_id})
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
        Execute a Cypher query.

        Args:
            query: Cypher query string
            parameters: Query parameters
            **options: Additional options

        Returns:
            Query results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="graph_store",
            submodule="Neo4jStore",
            message="Executing Cypher query",
        )

        try:
            with self.get_session() as session:
                result = session.run(query, parameters or {})

                records = []
                keys = []

                for record in result:
                    if not keys:
                        keys = list(record.keys())

                    row = {}
                    for key in keys:
                        value = record[key]
                        # Convert Neo4j types to Python types
                        if hasattr(value, "__iter__") and not isinstance(value, (str, dict)):
                            row[key] = list(value)
                        elif hasattr(value, "items"):
                            row[key] = dict(value)
                        else:
                            row[key] = value
                    records.append(row)

                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Query returned {len(records)} records",
                )

                return {
                    "success": True,
                    "records": records,
                    "keys": keys,
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
            List of neighboring nodes with path information
        """
        try:
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

            with self.get_session() as session:
                result = session.run(query, {"node_id": node_id})

                neighbors = []
                for record in result:
                    neighbors.append({
                        "id": record["id"],
                        "labels": record["labels"],
                        "properties": dict(record["neighbor"]),
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
            type_filter = f":{sanitize_identifier(rel_type, 'relationship type')}" if rel_type else ""
            max_depth = int(max_depth)

            query = f"""
                MATCH path = shortestPath((start)-[r{type_filter}*..{max_depth}]-(end))
                WHERE id(start) = $start_id AND id(end) = $end_id
                RETURN path, length(path) as length
            """

            with self.get_session() as session:
                result = session.run(query, {
                    "start_id": start_node_id,
                    "end_id": end_node_id,
                })
                record = result.single()

                if record:
                    path = record["path"]
                    nodes = []
                    relationships = []

                    for node in path.nodes:
                        nodes.append({
                            "id": node.id,
                            "labels": list(node.labels),
                            "properties": dict(node),
                        })

                    for rel in path.relationships:
                        relationships.append({
                            "id": rel.id,
                            "type": rel.type,
                            "properties": dict(rel),
                        })

                    return {
                        "length": record["length"],
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
        index_type: str = "btree",
        **options,
    ) -> bool:
        """
        Create an index on a property.

        Args:
            label: Node label
            property_name: Property to index
            index_type: Index type (btree, fulltext, range)
            **options: Additional options

        Returns:
            True if index created successfully
        """
        try:
            safe_label = sanitize_identifier(label, "label")
            safe_property = sanitize_identifier(property_name, "property key")
            index_name = sanitize_identifier(
                options.get("index_name", f"idx_{safe_label}_{safe_property}"),
                "index name",
            )

            if index_type == "fulltext":
                query = f"""
                    CREATE FULLTEXT INDEX {index_name} IF NOT EXISTS
                    FOR (n:{safe_label}) ON EACH [n.{safe_property}]
                """
            else:
                query = f"""
                    CREATE INDEX {index_name} IF NOT EXISTS
                    FOR (n:{safe_label}) ON (n.{safe_property})
                """

            with self.get_session() as session:
                session.run(query)
                self.logger.info(f"Created index {index_name} on {label}.{property_name}")
                return True

        except Exception as e:
            raise ProcessingError(f"Failed to create index: {str(e)}")

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            stats = {}

            with self.get_session() as session:
                # Node count
                result = session.run("MATCH (n) RETURN count(n) as count")
                record = result.single()
                stats["node_count"] = record["count"] if record else 0

                # Relationship count
                result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                record = result.single()
                stats["relationship_count"] = record["count"] if record else 0

                # Label counts
                result = session.run("""
                    MATCH (n)
                    UNWIND labels(n) as label
                    RETURN label, count(*) as count
                    ORDER BY count DESC
                """)
                stats["label_counts"] = {r["label"]: r["count"] for r in result}

                # Relationship type counts
                result = session.run("""
                    MATCH ()-[r]->()
                    RETURN type(r) as type, count(*) as count
                    ORDER BY count DESC
                """)
                stats["relationship_type_counts"] = {r["type"]: r["count"] for r in result}

            return stats

        except Exception as e:
            self.logger.warning(f"Failed to get stats: {str(e)}")
            return {"status": "error", "message": str(e)}

