"""Internal graph view helpers shared by KG analytics modules."""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


@dataclass
class GraphView:
    """Normalized node and edge view used by graph analytics."""

    nodes: List[Any]
    edges: List[Tuple[Any, Any]]


def build_graph_view(graph: Any) -> GraphView:
    """Build a graph view without dropping explicitly declared nodes.

    Graph analytics accepts graph dictionaries, ContextGraph-like objects, and
    NetworkX graphs. Nodes declared without an incident edge remain in the
    returned view so callers can choose how to handle isolated nodes.
    """
    nodes: List[Any] = []
    edges: List[Tuple[Any, Any]] = []
    seen_nodes: Set[Any] = set()
    seen_edges: Set[Tuple[Any, Any]] = set()

    def add_node(value: Any) -> Optional[Any]:
        node_id = _node_id(value)
        if node_id is None or node_id == "":
            return None
        if node_id not in seen_nodes:
            seen_nodes.add(node_id)
            nodes.append(node_id)
        return node_id

    for node in _extract_nodes(graph):
        add_node(node)

    for raw_edge in _extract_edges(graph):
        edge = _edge_endpoints(raw_edge)
        if edge is None:
            continue
        source, target = edge
        source = add_node(source)
        target = add_node(target)
        if source is None or target is None:
            continue
        if (source, target) not in seen_edges:
            seen_edges.add((source, target))
            edges.append((source, target))

    return GraphView(nodes=nodes, edges=edges)


def build_adjacency(graph: Any, directed: bool = False) -> Dict[Any, List[Any]]:
    """Build an adjacency list while preserving isolated graph nodes."""
    view = build_graph_view(graph)
    adjacency: Dict[Any, List[Any]] = {node: [] for node in view.nodes}

    for source, target in view.edges:
        if target not in adjacency[source]:
            adjacency[source].append(target)
        if not directed and source not in adjacency[target]:
            adjacency[target].append(source)

    return adjacency


def _extract_nodes(graph: Any) -> Iterable[Any]:
    if isinstance(graph, dict):
        raw_nodes: List[Any] = []
        for key in ("entities", "nodes"):
            values = graph.get(key, [])
            if isinstance(values, dict):
                raw_nodes.extend(values.keys())
            elif values:
                raw_nodes.extend(values)
        return raw_nodes

    raw_nodes = getattr(graph, "nodes", None)
    if callable(raw_nodes):
        return raw_nodes()
    if isinstance(raw_nodes, dict):
        return raw_nodes.keys()
    if raw_nodes is not None:
        return raw_nodes

    get_nodes = getattr(graph, "get_nodes", None)
    if callable(get_nodes):
        return get_nodes()
    return []


def _extract_edges(graph: Any) -> Iterable[Any]:
    if isinstance(graph, dict):
        raw_edges: List[Any] = []
        for key in ("relationships", "edges"):
            values = graph.get(key, [])
            if values:
                raw_edges.extend(values)
        return raw_edges

    raw_edges: List[Any] = []
    relationships = getattr(graph, "relationships", None)
    if relationships is not None:
        raw_edges.extend(relationships)
    edges = getattr(graph, "edges", None)
    if callable(edges):
        raw_edges.extend(edges())
    elif edges is not None:
        raw_edges.extend(edges)
    if raw_edges:
        return raw_edges

    get_relationships = getattr(graph, "get_relationships", None)
    if callable(get_relationships):
        return get_relationships()
    return []


def _edge_endpoints(edge: Any) -> Optional[Tuple[Any, Any]]:
    if isinstance(edge, (tuple, list)) and len(edge) >= 2:
        return edge[0], edge[1]

    if isinstance(edge, dict):
        source = _first_value(
            edge,
            "source",
            "source_id",
            "subject",
            "start",
            "start_id",
            "from",
            "src",
            "START_ID",
            ":START_ID",
        )
        target = _first_value(
            edge,
            "target",
            "target_id",
            "object",
            "end",
            "end_id",
            "to",
            "dst",
            "END_ID",
            ":END_ID",
        )
    else:
        source = _first_attribute(
            edge,
            "source_id",
            "source",
            "subject",
            "start",
            "start_id",
            "from_id",
        )
        target = _first_attribute(
            edge,
            "target_id",
            "target",
            "object",
            "end",
            "end_id",
            "to_id",
        )

    if source is None or target is None:
        return None
    return source, target


def _node_id(value: Any) -> Any:
    if isinstance(value, dict):
        value = _first_value(
            value, "id", "node_id", "entity_id", "key", "name", "text"
        )
    elif not isinstance(value, (str, int, float, bool, bytes, tuple)):
        value = _first_attribute(
            value, "node_id", "id", "entity_id", "key", "name", "text"
        )

    if value is None:
        return None
    try:
        hash(value)
    except TypeError:
        return str(value)
    return value


def _first_value(mapping: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _first_attribute(value: Any, *names: str) -> Any:
    for name in names:
        attribute = getattr(value, name, None)
        if attribute not in (None, ""):
            return attribute
    return None
