"""
Resource handlers for Semantica MCP resources.

Each resource maps a semantica:// URI to a callable that returns
{"uri": ..., "mimeType": ..., "text": ...}.
"""

from __future__ import annotations

import json
import logging

from mcp import __version__
from mcp.session import get_graph

log = logging.getLogger("semantica.mcp.resources")


def _read_graph_summary(uri: str) -> dict:
    try:
        graph = get_graph()
        all_nodes = list(graph.find_nodes())
        node_types: dict[str, int] = {}
        for n in all_nodes:
            t = str(n.get("type", "Unknown"))
            node_types[t] = node_types.get(t, 0) + 1
        edge_count = 0
        if hasattr(graph, "edge_count"):
            try:
                edge_count = graph.edge_count()
            except Exception as exc:
                log.debug("Unable to read graph edge_count(); defaulting to 0: %s", exc)
        data = {
            "node_count": len(all_nodes),
            "edge_count": edge_count,
            "node_types": node_types,
        }
    except Exception as exc:
        data = {"error": str(exc)}
    return {"uri": uri, "mimeType": "application/json", "text": json.dumps(data, indent=2)}


def _read_decisions_list(uri: str) -> dict:
    try:
        graph = get_graph()
        nodes = list(graph.find_nodes(node_type="decision"))
        decisions = [
            {
                "id": n.get("id"),
                "category": n.get("category"),
                "outcome": n.get("outcome"),
                "scenario": str(n.get("scenario", ""))[:120],
            }
            for n in nodes[:50]
        ]
        data = {"decisions": decisions, "count": len(decisions)}
    except Exception as exc:
        data = {"error": str(exc), "decisions": []}
    return {"uri": uri, "mimeType": "application/json", "text": json.dumps(data, indent=2)}


def _read_schema_info(uri: str) -> dict:
    info = {
        "version": __version__,
        "node_types": [
            "Entity", "decision", "Decision", "Event", "Concept",
            "Person", "Organisation", "Location",
        ],
        "edge_types": [
            "RELATED_TO", "CAUSED_BY", "LEADS_TO", "PART_OF",
            "INSTANCE_OF", "SIMILAR_TO",
        ],
        "tools": [
            "extract_entities", "extract_relations", "extract_all",
            "record_decision", "query_decisions", "find_precedents",
            "get_causal_chain", "analyze_decision_impact",
            "add_entity", "add_relationship", "search_graph",
            "get_graph_summary", "get_graph_analytics",
            "run_reasoning", "abductive_reasoning",
            "export_graph", "get_provenance",
        ],
    }
    return {"uri": uri, "mimeType": "application/json", "text": json.dumps(info, indent=2)}


def _read_ontology_schema(uri: str) -> dict:
    try:
        graph = get_graph()
        try:
            from semantica.ontology import OntologyManager
            mgr = OntologyManager(graph_store=graph)
            schema = mgr.get_schema()
            text = json.dumps(schema, indent=2) if isinstance(schema, dict) else str(schema)
        except (ImportError, AttributeError):
            text = json.dumps({"message": "Ontology manager not available"}, indent=2)
    except Exception as exc:
        text = json.dumps({"error": str(exc)}, indent=2)
    return {"uri": uri, "mimeType": "application/json", "text": text}


# Map URI → handler
_HANDLERS: dict[str, object] = {
    "semantica://graph/summary": _read_graph_summary,
    "semantica://decisions/list": _read_decisions_list,
    "semantica://schema/info": _read_schema_info,
    "semantica://ontology/schema": _read_ontology_schema,
}

RESOURCE_DEFINITIONS = [
    {
        "uri": "semantica://graph/summary",
        "name": "Graph Summary",
        "description": "High-level summary of the current knowledge graph: node/edge counts and type breakdown.",
        "mimeType": "application/json",
    },
    {
        "uri": "semantica://decisions/list",
        "name": "Decision List",
        "description": "Most recent decisions recorded in the knowledge graph (up to 50).",
        "mimeType": "application/json",
    },
    {
        "uri": "semantica://schema/info",
        "name": "Schema Info",
        "description": "Semantica schema version, supported node/edge types, and available tool names.",
        "mimeType": "application/json",
    },
    {
        "uri": "semantica://ontology/schema",
        "name": "Ontology Schema",
        "description": "Full ontology schema from the OntologyManager (concept hierarchy and constraints).",
        "mimeType": "application/json",
    },
]


def handle_resource_read(uri: str) -> dict:
    """Dispatch a resources/read request to the appropriate handler."""
    handler = _HANDLERS.get(uri)
    if handler is None:
        return {
            "uri": uri,
            "mimeType": "application/json",
            "text": json.dumps({"error": f"Unknown resource URI: {uri}"}),
        }
    try:
        return handler(uri)  # type: ignore[call-arg]
    except Exception as exc:
        log.exception("resource_read failed for %s", uri)
        return {
            "uri": uri,
            "mimeType": "application/json",
            "text": json.dumps({"error": str(exc)}),
        }
