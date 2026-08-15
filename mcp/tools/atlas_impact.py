"""MCP tools — Atlas impact / coverage / risk / assumption queries over per-workspace graphs (atlas #618).

Every tool is **workspace-scoped** (multi-tenant): the caller passes ``workspace_id`` and the handler
only ever touches that tenant's namespace. Wire these into the MCP server by registering ``TOOLS``
alongside the existing tool groups (decisions/graph/reasoning/…); each value is a
``handler(args: dict) -> dict``.

Note: these build the workspace graph on demand from Atlas Postgres (``ATLAS_DATABASE_URL``). For hot
paths, point them at the persisted per-workspace FalkorDB graph the worker writes instead of re-extracting.
"""
from __future__ import annotations

from typing import Any, Dict


def _workspace_graph(workspace_id: str):
    from integrations.atlas.atlas_adapter import AtlasSemanticaAdapter
    return AtlasSemanticaAdapter().extract(workspace_id)


def _need(args: dict, *keys):
    for k in keys:
        if not str((args or {}).get(k, "")).strip():
            return {"error": f"{k} is required"}
    return None


def handle_atlas_if_removed(args: Dict[str, Any]) -> Dict[str, Any]:
    """"If we remove <node_id>, what's affected?" — directional blast radius, grouped by type."""
    err = _need(args, "workspace_id", "node_id")
    if err:
        return err
    return {"affected": _workspace_graph(args["workspace_id"]).if_removed(str(args["node_id"]))}


def handle_atlas_coverage_gaps(args: Dict[str, Any]) -> Dict[str, Any]:
    """ACs w/o test, sections w/o AC, closed issues w/o PR, decisions w/o run."""
    err = _need(args, "workspace_id")
    if err:
        return err
    return {"coverage_gaps": _workspace_graph(args["workspace_id"]).coverage_gaps()}


def handle_atlas_unvalidated_assumptions(args: Dict[str, Any]) -> Dict[str, Any]:
    """Which requirements rest on assumptions whose status != 'validated'."""
    err = _need(args, "workspace_id")
    if err:
        return err
    return {"requirements_on_unvalidated_assumptions":
            _workspace_graph(args["workspace_id"]).unvalidated_assumptions()}


def handle_atlas_risk_hotspots(args: Dict[str, Any]) -> Dict[str, Any]:
    """Most load-bearing specs/decisions/components by betweenness centrality."""
    err = _need(args, "workspace_id")
    if err:
        return err
    try:
        top_n = int(args.get("top_n", 10) or 10)
    except (TypeError, ValueError):
        top_n = 10
    return {"risk_hotspots": _workspace_graph(args["workspace_id"]).risk_hotspots(top_n)}


TOOLS = {
    "atlas_if_removed": handle_atlas_if_removed,
    "atlas_coverage_gaps": handle_atlas_coverage_gaps,
    "atlas_unvalidated_assumptions": handle_atlas_unvalidated_assumptions,
    "atlas_risk_hotspots": handle_atlas_risk_hotspots,
}

# Minimal JSON-schema hints for the MCP server's tool registry.
SCHEMAS = {
    "atlas_if_removed": {
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string", "description": "Atlas workspace (tenant) id"},
            "node_id": {"type": "string", "description": "Node to test removal of (e.g. a spec/section id)"},
        },
        "required": ["workspace_id", "node_id"],
    },
    "atlas_coverage_gaps": {
        "type": "object",
        "properties": {"workspace_id": {"type": "string"}},
        "required": ["workspace_id"],
    },
    "atlas_unvalidated_assumptions": {
        "type": "object",
        "properties": {"workspace_id": {"type": "string"}},
        "required": ["workspace_id"],
    },
    "atlas_risk_hotspots": {
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string"},
            "top_n": {"type": "integer", "description": "How many hotspots to return (default 10)"},
        },
        "required": ["workspace_id"],
    },
}
