"""
Graph Store Methods Module

This module provides all graph store methods as simple, reusable functions for
creating nodes, relationships, querying, and running analytics. It supports
multiple approaches and integrates with the method registry for extensibility.

Supported Methods:

Node Operations:
    - "default": Default node creation using GraphStore
    - "batch": Batch node creation
    - "validated": Validated node creation with schema checking

Relationship Operations:
    - "default": Default relationship creation
    - "batch": Batch relationship creation

Query Operations:
    - "default": Default Cypher query execution
    - "cached": Cached query execution
    - "optimized": Optimized query execution

Analytics Operations:
    - "shortest_path": Shortest path algorithm
    - "neighbors": Neighbor traversal
    - "centrality": Centrality calculations

Key Features:
    - Multiple graph store operation methods
    - Node and relationship operations with method dispatch
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - create_node: Node creation wrapper
    - create_nodes: Batch node creation wrapper
    - create_relationship: Relationship creation wrapper
    - create_relationships: Batch relationship creation wrapper
    - get_nodes: Get nodes wrapper
    - get_relationships: Get relationships wrapper
    - update_node: Update node wrapper
    - update_relationship: Update relationship wrapper
    - delete_node: Delete node wrapper
    - delete_relationship: Delete relationship wrapper
    - execute_query: Query execution wrapper
    - shortest_path: Shortest path wrapper
    - get_neighbors: Get neighbors wrapper
    - run_analytics: Run analytics wrapper
    - get_graph_store_method: Get graph store method by task and name
    - list_available_methods: List registered methods

Example Usage:
    >>> from semantica.graph_store.methods import create_node, create_relationship, execute_query
    >>> node_id = create_node(labels=["Person"], properties={"name": "Alice"})
    >>> rel = create_relationship(start_id=node1_id, end_id=node2_id, rel_type="KNOWS")
    >>> results = execute_query("MATCH (p:Person) RETURN p.name")
"""

from typing import Any, Dict, List, Optional, Union

from .config import graph_store_config
from .graph_store import GraphAnalytics, GraphStore, NodeManager, QueryEngine, RelationshipManager
from .query_sanitize import sanitize_identifier
from .registry import method_registry

# Global store instance
_global_store: Optional[GraphStore] = None


def _get_store() -> GraphStore:
    """Get or create global GraphStore instance."""
    global _global_store
    if _global_store is None:
        config = graph_store_config.get_all()
        backend = config.get("default_backend", "neo4j")
        _global_store = GraphStore(backend=backend, **config)
    return _global_store


def _reset_store() -> None:
    """Reset the global store instance."""
    global _global_store
    if _global_store is not None:
        _global_store.close()
        _global_store = None


# Node Operations

def create_node(
    labels: List[str],
    properties: Dict[str, Any],
    method: str = "default",
    **options,
) -> Dict[str, Any]:
    """
    Create a node in the graph.

    Args:
        labels: Node labels
        properties: Node properties
        method: Creation method name (default: "default")
        **options: Additional options

    Returns:
        Created node information including ID
    """
    # Check registry for custom method
    custom_method = method_registry.get("node", method)
    if custom_method:
        return custom_method(labels, properties, **options)

    # Default implementation
    store = _get_store()
    return store.create_node(labels, properties, **options)


def create_nodes(
    nodes: List[Dict[str, Any]],
    method: str = "default",
    **options,
) -> List[Dict[str, Any]]:
    """
    Create multiple nodes in batch.

    Args:
        nodes: List of node dictionaries with 'labels' and 'properties'
        method: Creation method name (default: "default")
        **options: Additional options

    Returns:
        List of created node information
    """
    # Check registry for custom method
    custom_method = method_registry.get("node", method)
    if custom_method:
        return custom_method(nodes, **options)

    # Default implementation
    store = _get_store()
    return store.create_nodes(nodes, **options)


def get_nodes(
    labels: Optional[List[str]] = None,
    properties: Optional[Dict[str, Any]] = None,
    limit: int = 100,
    method: str = "default",
    **options,
) -> List[Dict[str, Any]]:
    """
    Get nodes matching criteria.

    Args:
        labels: Filter by labels
        properties: Filter by properties
        limit: Maximum number of nodes
        method: Retrieval method name (default: "default")
        **options: Additional options

    Returns:
        List of matching nodes
    """
    # Check registry for custom method
    custom_method = method_registry.get("node", method)
    if custom_method:
        return custom_method(labels=labels, properties=properties, limit=limit, **options)

    # Default implementation
    store = _get_store()
    return store.get_nodes(labels, properties, limit, **options)


def update_node(
    node_id: Union[int, str],
    properties: Dict[str, Any],
    merge: bool = True,
    method: str = "default",
    **options,
) -> Dict[str, Any]:
    """
    Update a node's properties.

    Args:
        node_id: Node ID
        properties: Properties to update
        merge: If True, merge properties; if False, replace
        method: Update method name (default: "default")
        **options: Additional options

    Returns:
        Updated node information
    """
    # Check registry for custom method
    custom_method = method_registry.get("node", method)
    if custom_method:
        return custom_method(node_id, properties, merge=merge, **options)

    # Default implementation
    store = _get_store()
    return store.update_node(node_id, properties, merge, **options)


def delete_node(
    node_id: Union[int, str],
    detach: bool = True,
    method: str = "default",
    **options,
) -> bool:
    """
    Delete a node.

    Args:
        node_id: Node ID
        detach: If True, delete relationships as well
        method: Deletion method name (default: "default")
        **options: Additional options

    Returns:
        True if deleted successfully
    """
    # Check registry for custom method
    custom_method = method_registry.get("node", method)
    if custom_method:
        return custom_method(node_id, detach=detach, **options)

    # Default implementation
    store = _get_store()
    return store.delete_node(node_id, detach, **options)


# Relationship Operations

def create_relationship(
    start_id: Union[int, str],
    end_id: Union[int, str],
    rel_type: str,
    properties: Optional[Dict[str, Any]] = None,
    method: str = "default",
    **options,
) -> Dict[str, Any]:
    """
    Create a relationship between two nodes.

    Args:
        start_id: Start node ID
        end_id: End node ID
        rel_type: Relationship type
        properties: Relationship properties
        method: Creation method name (default: "default")
        **options: Additional options

    Returns:
        Created relationship information
    """
    # Check registry for custom method
    custom_method = method_registry.get("relationship", method)
    if custom_method:
        return custom_method(start_id, end_id, rel_type, properties=properties, **options)

    # Default implementation
    store = _get_store()
    return store.create_relationship(start_id, end_id, rel_type, properties, **options)


def create_relationships(
    relationships: List[Dict[str, Any]],
    method: str = "default",
    **options,
) -> List[Dict[str, Any]]:
    """
    Create multiple relationships in batch.

    Args:
        relationships: List of relationship dictionaries with 'start_id', 'end_id', 'type', and optional 'properties'
        method: Creation method name (default: "default")
        **options: Additional options

    Returns:
        List of created relationship information
    """
    # Check registry for custom method
    custom_method = method_registry.get("relationship", method)
    if custom_method:
        return custom_method(relationships, **options)

    # Default implementation
    store = _get_store()
    created = []
    for rel in relationships:
        result = store.create_relationship(
            rel["start_id"],
            rel["end_id"],
            rel["type"],
            rel.get("properties"),
            **options,
        )
        created.append(result)
    return created


def get_relationships(
    node_id: Optional[Union[int, str]] = None,
    rel_type: Optional[str] = None,
    direction: str = "both",
    limit: int = 100,
    method: str = "default",
    **options,
) -> List[Dict[str, Any]]:
    """
    Get relationships matching criteria.

    Args:
        node_id: Filter by node ID
        rel_type: Filter by relationship type
        direction: Direction ("in", "out", "both")
        limit: Maximum number of relationships
        method: Retrieval method name (default: "default")
        **options: Additional options

    Returns:
        List of matching relationships
    """
    # Check registry for custom method
    custom_method = method_registry.get("relationship", method)
    if custom_method:
        return custom_method(node_id=node_id, rel_type=rel_type, direction=direction, limit=limit, **options)

    # Default implementation
    store = _get_store()
    return store.get_relationships(node_id, rel_type, direction, limit, **options)


def update_relationship(
    rel_id: Union[int, str],
    properties: Dict[str, Any],
    method: str = "default",
    **options,
) -> Dict[str, Any]:
    """
    Update a relationship's properties.

    Args:
        rel_id: Relationship ID
        properties: Properties to update
        method: Update method name (default: "default")
        **options: Additional options

    Returns:
        Updated relationship information
    """
    # Check registry for custom method
    custom_method = method_registry.get("relationship", method)
    if custom_method:
        return custom_method(rel_id, properties, **options)

    # Default implementation - execute update query
    store = _get_store()
    safe_keys = [sanitize_identifier(k, "property key") for k in properties.keys()]
    set_parts = ", ".join(f"r.{k} = ${k}" for k in safe_keys)
    query = f"MATCH ()-[r]->() WHERE id(r) = $rel_id SET {set_parts} RETURN id(r) as id, type(r) as type, r"
    params = {"rel_id": rel_id, **properties}
    result = store.execute_query(query, params)

    if result.get("records"):
        record = result["records"][0]
        return {
            "id": record.get("id"),
            "type": record.get("type"),
            "properties": properties,
        }
    raise ValueError(f"Relationship with ID {rel_id} not found")


def delete_relationship(
    rel_id: Union[int, str],
    method: str = "default",
    **options,
) -> bool:
    """
    Delete a relationship.

    Args:
        rel_id: Relationship ID
        method: Deletion method name (default: "default")
        **options: Additional options

    Returns:
        True if deleted successfully
    """
    # Check registry for custom method
    custom_method = method_registry.get("relationship", method)
    if custom_method:
        return custom_method(rel_id, **options)

    # Default implementation
    store = _get_store()
    return store.delete_relationship(rel_id, **options)


# Query Operations

def execute_query(
    query: str,
    parameters: Optional[Dict[str, Any]] = None,
    method: str = "default",
    **options,
) -> Dict[str, Any]:
    """
    Execute a Cypher/OpenCypher query.

    Args:
        query: Query string
        parameters: Query parameters
        method: Execution method name (default: "default")
        **options: Additional options

    Returns:
        Query results
    """
    # Check registry for custom method
    custom_method = method_registry.get("query", method)
    if custom_method:
        return custom_method(query, parameters=parameters, **options)

    # Default implementation
    store = _get_store()
    return store.execute_query(query, parameters, **options)


# Analytics Operations

def shortest_path(
    start_node_id: Union[int, str],
    end_node_id: Union[int, str],
    rel_type: Optional[str] = None,
    max_depth: int = 10,
    method: str = "default",
    **options,
) -> Optional[Dict[str, Any]]:
    """
    Find shortest path between two nodes.

    Args:
        start_node_id: Starting node ID
        end_node_id: Ending node ID
        rel_type: Filter by relationship type
        max_depth: Maximum path length
        method: Algorithm method name (default: "default")
        **options: Additional options

    Returns:
        Path information or None if not found
    """
    # Check registry for custom method
    custom_method = method_registry.get("traversal", method)
    if custom_method:
        return custom_method(start_node_id, end_node_id, rel_type=rel_type, max_depth=max_depth, **options)

    # Default implementation
    store = _get_store()
    return store.shortest_path(start_node_id, end_node_id, rel_type, max_depth, **options)


def get_neighbors(
    node_id: Union[int, str],
    rel_type: Optional[str] = None,
    direction: str = "both",
    depth: int = 1,
    method: str = "default",
    **options,
) -> List[Dict[str, Any]]:
    """
    Get neighboring nodes.

    Args:
        node_id: Starting node ID
        rel_type: Filter by relationship type
        direction: Direction ("in", "out", "both")
        depth: Traversal depth
        method: Traversal method name (default: "default")
        **options: Additional options

    Returns:
        List of neighboring nodes
    """
    # Check registry for custom method
    custom_method = method_registry.get("traversal", method)
    if custom_method:
        return custom_method(node_id, rel_type=rel_type, direction=direction, depth=depth, **options)

    # Default implementation
    store = _get_store()
    return store.get_neighbors(node_id, rel_type, direction, depth, **options)


def run_analytics(
    algorithm: str,
    method: str = "default",
    **options,
) -> Dict[str, Any]:
    """
    Run a graph analytics algorithm.

    Args:
        algorithm: Algorithm name ("degree_centrality", "connected_components", etc.)
        method: Analytics method name (default: "default")
        **options: Algorithm-specific options

    Returns:
        Analytics results
    """
    # Check registry for custom method
    custom_method = method_registry.get("analytics", method)
    if custom_method:
        return custom_method(algorithm, **options)

    # Default implementation
    store = _get_store()

    if algorithm == "degree_centrality":
        return {
            "algorithm": algorithm,
            "results": store.analytics.degree_centrality(**options),
        }
    elif algorithm == "connected_components":
        return {
            "algorithm": algorithm,
            "results": store.analytics.connected_components(**options),
        }
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


# Utility Functions

def get_graph_store_method(task: str, method_name: str) -> Optional[Any]:
    """
    Get graph store method by task and name.

    Args:
        task: Task type (node, relationship, query, traversal, analytics, bulk)
        method_name: Method name

    Returns:
        Method function or None if not found
    """
    return method_registry.get(task, method_name)


def list_available_methods(task: Optional[str] = None) -> Dict[str, List[str]]:
    """
    List all available graph store methods.

    Args:
        task: Optional task type to filter by

    Returns:
        Dictionary mapping task types to lists of method names
    """
    return method_registry.list_all(task)

