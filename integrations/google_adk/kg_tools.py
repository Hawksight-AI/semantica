
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

try:
    from google.adk.tools import FunctionTool

    ADK_AVAILABLE = True
except ImportError:
    FunctionTool = None  # type: ignore
    ADK_AVAILABLE = False



_graph_locks_guard = threading.Lock()
_graph_locks: Dict[int, threading.RLock] = {}


def _graph_lock(graph: Any) -> threading.RLock:
    """Return the mutation lock associated with a ContextGraph instance."""
    key = id(graph)

    with _graph_locks_guard:
        lock = _graph_locks.get(key)

        if lock is None:
            lock = threading.RLock()
            _graph_locks[key] = lock

        return lock


def _get_default_graph() -> Any:
    """Create a default Semantica ContextGraph."""
    from semantica.context import ContextGraph

    return ContextGraph()


def _get_ner_extractor() -> Any:
    """Create Semantica default NER extractor."""
    from semantica.semantic_extract import NERExtractor

    return NERExtractor()


def _get_relation_extractor() -> Any:
    """Create Semantica default relation extractor."""
    from semantica.semantic_extract import RelationExtractor

    return RelationExtractor()



def _first_string(obj: Any, attributes: tuple[str, ...]) -> str:
    """Return the first non-empty string from an object or dictionary."""
    if obj is None:
        return ""

    if isinstance(obj, dict):
        for attribute in attributes:
            value = obj.get(attribute)

            if isinstance(value, str) and value.strip():
                return value.strip()

        return ""

    for attribute in attributes:
        value = getattr(obj, attribute, None)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _entity_name(entity: Any) -> str:
    """Return a best-effort name for an extracted entity."""
    return _first_string(
        entity,
        (
            "name",
            "text",
            "label",
            "node_id",
            "id",
        ),
    )


def _entity_type(entity: Any) -> str:
    """Return a best-effort type for an extracted entity."""
    return (
        _first_string(
            entity,
            (
                "type",
                "label",
            ),
        )
        or "Entity"
    )


def _entity_confidence(entity: Any) -> float:
    """Normalize an entity confidence value."""
    try:
        confidence = (
            entity.get("confidence")
            if isinstance(entity, dict)
            else getattr(entity, "confidence", None)
        )

        if confidence is None:
            return 1.0

        return round(float(confidence), 4)

    except (TypeError, ValueError):
        return 1.0


def _relation_source(relation: Any) -> str:
    """Return the source entity of an extracted relation."""
    source = _first_string(
        relation,
        (
            "source",
            "source_id",
        ),
    )

    if source:
        return source

    if isinstance(relation, dict):
        return _entity_name(relation.get("subject"))

    return _entity_name(getattr(relation, "subject", None))


def _relation_target(relation: Any) -> str:
    """Return the target entity of an extracted relation."""
    target = _first_string(
        relation,
        (
            "target",
            "target_id",
        ),
    )

    if target:
        return target

    if isinstance(relation, dict):
        return _entity_name(relation.get("object"))

    return _entity_name(getattr(relation, "object", None))


def _relation_type(relation: Any) -> str:
    """Return the relation predicate/type."""
    return (
        _first_string(
            relation,
            (
                "type",
                "relation",
                "predicate",
            ),
        )
        or "related_to"
    )


def _json_safe(value: Any) -> Any:
    """
    Convert common Semantica objects into values suitable for ADK tool output.

    ADK tools should return values that can be serialized into the tool
    response sent back to the model.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass

    if hasattr(value, "model_dump"):
        try:
            return _json_safe(value.model_dump())
        except Exception:
            pass

    return str(value)



def extract_entities(text: str) -> dict:
    """Extract named entities from text using Semantica's NER pipeline."""
    if not isinstance(text, str):
        return {
            "entities": [],
            "count": 0,
            "error": "text must be a string",
        }

    try:
        extractor = _get_ner_extractor()
        raw_entities = extractor.extract_entities(text) or []

        entities: List[Dict[str, Any]] = []

        for entity in raw_entities:
            name = _entity_name(entity)

            if not name:
                continue

            entities.append(
                {
                    "name": name,
                    "type": _entity_type(entity),
                    "confidence": _entity_confidence(entity),
                }
            )

        return {
            "entities": entities,
            "count": len(entities),
        }

    except Exception as exc:
        return {
            "entities": [],
            "count": 0,
            "error": str(exc),
        }


def extract_relations(text: str) -> dict:
    """Extract relationships between entities from text using Semantica."""
    if not isinstance(text, str):
        return {
            "relations": [],
            "count": 0,
            "error": "text must be a string",
        }

    try:
        extractor = _get_relation_extractor()
        raw_relations = extractor.extract_relations(text) or []

        relations: List[Dict[str, Any]] = []

        for relation in raw_relations:
            source = _relation_source(relation)
            target = _relation_target(relation)

            if not source or not target:
                continue

            relations.append(
                {
                    "source": source,
                    "relation": _relation_type(relation),
                    "target": target,
                    "confidence": _entity_confidence(relation),
                }
            )

        return {
            "relations": relations,
            "count": len(relations),
        }

    except Exception as exc:
        return {
            "relations": [],
            "count": 0,
            "error": str(exc),
        }


def add_to_graph(text: str) -> dict:
    """
    Extract entities and relationships from text and add them to a ContextGraph.

    This standalone function uses a process-local default graph. For a shared
    graph across ADK agents, use ``semantica_kg_tools(graph=shared_graph)``.
    """
    return _add_to_graph(text, _get_default_graph())


def query_graph(query: str) -> dict:
    """
    Query the shared Semantica knowledge graph by keyword.

    This standalone function uses a process-local default graph. For a shared
    graph, use ``semantica_kg_tools(graph=shared_graph)``.
    """
    return _query_graph(query, _get_default_graph())


def _add_to_graph(text: str, graph: Any) -> dict:
    """Internal graph mutation implementation."""
    if not isinstance(text, str):
        return {
            "nodes_added": 0,
            "edges_added": 0,
            "error": "text must be a string",
        }

    try:
        ner_extractor = _get_ner_extractor()
        relation_extractor = _get_relation_extractor()

        nodes_added = 0
        edges_added = 0

        with _graph_lock(graph):
            existing_nodes = set()

            for node in graph.find_nodes() or []:
                if isinstance(node, dict):
                    node_id = node.get("id") or node.get("node_id")
                else:
                    node_id = getattr(
                        node,
                        "id",
                        getattr(node, "node_id", None),
                    )

                if node_id:
                    existing_nodes.add(str(node_id))

            existing_edges = set()

            for edge in graph.find_edges() or []:
                if isinstance(edge, dict):
                    source = edge.get("source") or edge.get("source_id")
                    target = edge.get("target") or edge.get("target_id")
                    edge_type = edge.get("type") or edge.get("edge_type")
                else:
                    source = getattr(
                        edge,
                        "source_id",
                        getattr(edge, "source", None),
                    )
                    target = getattr(
                        edge,
                        "target_id",
                        getattr(edge, "target", None),
                    )
                    edge_type = getattr(
                        edge,
                        "edge_type",
                        getattr(edge, "type", None),
                    )

                if source and target:
                    existing_edges.add(
                        (
                            str(source),
                            str(edge_type or "related_to"),
                            str(target),
                        )
                    )

            raw_entities = ner_extractor.extract_entities(text) or []

            entities: List[Any] = []
            seen_entities = set()

            for entity in raw_entities:
                name = _entity_name(entity)
                entity_type = _entity_type(entity)

                if not name or name in seen_entities:
                    continue

                seen_entities.add(name)
                entities.append(entity)

                if name in existing_nodes:
                    continue

                try:
                    added = graph.add_node(
                        node_id=name,
                        node_type=entity_type,
                    )

                    if added:
                        nodes_added += 1
                        existing_nodes.add(name)

                except Exception:
                    # Do not fail the entire tool because one node could not
                    # be inserted.
                    continue

            try:
                raw_relations = relation_extractor.extract_relations(
                    text,
                    entities=entities,
                ) or []
            except TypeError:
                # Compatibility with extractors that do not accept entities=.
                raw_relations = relation_extractor.extract_relations(text) or []

            for relation in raw_relations:
                source = _relation_source(relation)
                target = _relation_target(relation)
                relation_type = _relation_type(relation)

                if not source or not target:
                    continue

                edge_key = (
                    source,
                    relation_type,
                    target,
                )

                if edge_key in existing_edges:
                    continue

                try:
                    added = graph.add_edge(
                        source_id=source,
                        target_id=target,
                        edge_type=relation_type,
                    )

                    if added:
                        edges_added += 1
                        existing_edges.add(edge_key)

                except Exception:
                    continue

        return {
            "nodes_added": nodes_added,
            "edges_added": edges_added,
        }

    except Exception as exc:
        return {
            "nodes_added": 0,
            "edges_added": 0,
            "error": str(exc),
        }


def _query_graph(query: str, graph: Any) -> dict:
    """Internal graph query implementation."""
    if not isinstance(query, str):
        return {
            "query": query,
            "results": [],
            "count": 0,
            "error": "query must be a string",
        }

    query = query.strip()

    if not query:
        return {
            "query": query,
            "results": [],
            "count": 0,
        }

    try:
        results: List[Dict[str, Any]] = []
        seen = set()

        # Prefer ContextGraph.query() when available because it can provide
        # richer semantic/structural results.
        query_method = getattr(graph, "query", None)

        if callable(query_method):
            try:
                matches = query_method(query) or []

                for match in matches:
                    if not isinstance(match, dict):
                        continue

                    node = match.get("node") or {}

                    if not isinstance(node, dict):
                        node = _json_safe(node)

                    node_id = (
                        node.get("id")
                        or node.get("node_id")
                        or match.get("id")
                    )

                    if not node_id:
                        continue

                    node_id = str(node_id)

                    if node_id in seen:
                        continue

                    seen.add(node_id)

                    results.append(
                        {
                            "id": node_id,
                            "type": (
                                node.get("type")
                                or node.get("node_type")
                                or ""
                            ),
                            "content": str(
                                match.get("content")
                                or node.get("content")
                                or (
                                    node.get("properties") or {}
                                ).get("content", "")
                            )[:500],
                            "score": round(
                                float(match.get("score") or 0.0),
                                4,
                            ),
                        }
                    )

            except Exception:
                # Fall back to deterministic keyword search below.
                pass

        # Deterministic fallback/search enrichment.
        query_lower = query.lower()

        for node in graph.find_nodes() or []:
            if isinstance(node, dict):
                node_id = (
                    node.get("id")
                    or node.get("node_id")
                    or ""
                )
                node_type = (
                    node.get("type")
                    or node.get("node_type")
                    or ""
                )

                properties = node.get("properties") or {}

                content = (
                    node.get("content")
                    or properties.get("content")
                    or ""
                )

            else:
                node_id = getattr(
                    node,
                    "id",
                    getattr(node, "node_id", ""),
                )
                node_type = getattr(
                    node,
                    "node_type",
                    getattr(node, "type", ""),
                )
                content = getattr(node, "content", "")

            node_id = str(node_id or "")
            node_type = str(node_type or "")
            content = str(content or "")

            if not node_id or node_id in seen:
                continue

            haystack = " ".join(
                (
                    node_id,
                    node_type,
                    content,
                )
            ).lower()

            if query_lower in haystack:
                seen.add(node_id)

                results.append(
                    {
                        "id": node_id,
                        "type": node_type,
                        "content": content[:500],
                        "score": 1.0,
                    }
                )

        return {
            "query": query,
            "results": results,
            "count": len(results),
        }

    except Exception as exc:
        return {
            "query": query,
            "results": [],
            "count": 0,
            "error": str(exc),
        }



def semantica_kg_tools(
    graph: Optional[Any] = None,
) -> List[Any]:
    """
    Return Google ADK FunctionTools bound to a shared ContextGraph instance.

    Args:
        graph:
            Optional Semantica ContextGraph. When supplied, all returned tools
            operate on this same graph instance.

    Returns:
        A list containing FunctionTools for:
            - extract_entities
            - extract_relations
            - add_to_graph
            - query_graph

    Raises:
        ImportError:
            If google-adk is not installed.
    """
    if not ADK_AVAILABLE or FunctionTool is None:
        raise ImportError(
            "Google ADK is required for semantica_kg_tools(). "
            "Install it with: pip install semantica[google-adk]"
        )

    shared_graph = graph if graph is not None else _get_default_graph()

    def add_to_shared_graph(text: str) -> dict:
        """Extract entities and relationships from text and add them to the shared Semantica graph."""
        return _add_to_graph(text, shared_graph)

    def query_shared_graph(query: str) -> dict:
        """Query the shared Semantica knowledge graph by keyword."""
        return _query_graph(query, shared_graph)

    # FunctionTool derives the tool name/schema from the wrapped callable and
    # its docstring, which is exactly the ADK convention we want.
    return [
        FunctionTool(extract_entities),
        FunctionTool(extract_relations),
        FunctionTool(add_to_shared_graph),
        FunctionTool(query_shared_graph),
    ]


__all__ = [
    "ADK_AVAILABLE",
    "extract_entities",
    "extract_relations",
    "add_to_graph",
    "query_graph",
    "semantica_kg_tools",
]