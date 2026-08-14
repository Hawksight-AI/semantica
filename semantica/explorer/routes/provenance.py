"""
Provenance routes for lineage visualization and exportable reports.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import networkx as nx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response

from ..dependencies import get_session
from ..schemas import ProvenanceEdge, ProvenanceNode, ProvenanceResponse
from ..session import GraphSession
from ...provenance.integrity import verify_checksum

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provenance", tags=["Power User Tools"])

# SECURITY: Strip characters that could break out of a Content-Disposition
# filename= value and inject new HTTP response headers (CWE-113 / CRLF injection).
# \r, \n, \x00 are the primary header-splitting vectors; " and \ would close
# or escape the filename attribute.
_UNSAFE_FILENAME_CHARS = re.compile(r'[\r\n\x00"\\]')
_MAX_FILENAME_ID_LEN = 128


def _safe_content_disposition_filename(node_id: str, suffix: str) -> str:
    """Return a sanitized Content-Disposition filename for the given node_id.

    Strips CR, LF, NUL, double-quotes, and backslashes that could split HTTP
    response headers or escape the filename attribute, then length-caps the
    result so it never produces an excessively long header value.
    """
    sanitized = _UNSAFE_FILENAME_CHARS.sub("_", str(node_id))[:_MAX_FILENAME_ID_LEN]
    return f"{sanitized}{suffix}"

_AGENT_TYPES = {"person", "organization", "system", "agent"}
_ACTIVITY_TYPES = {"action", "event", "process", "activity", "decision", "publication"}


def _classify_prov(node_type: str) -> tuple[str, str]:
    lowered = node_type.lower()
    if lowered in _AGENT_TYPES:
        return "Agent", "group_agent"
    if lowered in _ACTIVITY_TYPES:
        return "Activity", "group_activity"
    return "Entity", "group_entity"


def _add_chain_nodes(chain: List[Any], nodes: List[Dict[str, Any]], seen_nodes: set) -> None:
    for entry in chain:
        if not isinstance(entry, dict):
            continue
        eid = str(entry.get("entity_id") or "")
        if not eid or eid in seen_nodes:
            continue
        seen_nodes.add(eid)
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        label = str(metadata.get("title") or metadata.get("label") or eid)
        prov_type, parent_id = _classify_prov(str(entry.get("entity_type", "entity")))
        nodes.append({
            "id": eid,
            "label": label,
            "prov_type": prov_type,
            "parent_id": parent_id,
            "source_document": entry.get("source_document") or None,
            "source_location": entry.get("source_location") or None,
            "source_quote": entry.get("source_quote") or None,
            "confidence": entry.get("confidence"),
            "checksum": entry.get("checksum") or None,
        })


def _add_chain_edges(
    chain: List[Any], edges: List[Dict[str, Any]], seen_edges: set, direction: str
) -> None:
    for entry in chain:
        if not isinstance(entry, dict):
            continue
        eid = str(entry.get("entity_id") or "")
        if not eid:
            continue
        parents = []
        if entry.get("parent_entity_id"):
            parents.append(str(entry.get("parent_entity_id")))
        used = entry.get("used_entities")
        if isinstance(used, list):
            for u in used:
                if u and str(u) not in parents:
                    parents.append(str(u))

        activity = str(entry.get("activity_id") or "wasDerivedFrom")
        for src in parents:
            edge_key = (src, eid, direction)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            edges.append({
                # Includes direction to match the seen_edges uniqueness key
                # above: the same (src, eid) pair can legitimately appear in
                # both directions (e.g. cycles/overlap between the ancestor
                # and descendant chains), and without this the two edges
                # would collide on the same id.
                "id": f"{src}-{eid}-{direction}",
                "source": src,
                "target": eid,
                "label": activity,
                "direction": direction,
            })


def _transform_audit_lineage(
    lineage: Dict[str, Any],
    node_id: str,
    descendants: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # Mapping decision (W3C PROV-O to frontend swim-lanes):
    # Every ProvenanceEntry maps to a node classified by _classify_prov(entry["entity_type"]),
    # placing documents/chunks/entities in 'group_entity' (prov_type='Entity'), persons/systems
    # in 'group_agent', and actions/processes in 'group_activity'.
    # For derivation relationships (parent_entity_id and used_entities), we connect
    # parent -> child directly with edge label set to activity_id (or 'wasDerivedFrom'),
    # keeping the lineage graph scannable without cluttering it with intermediate activity
    # nodes when activity_id is an operational label.
    #
    # Upstream edges come from lineage's ancestor chain (parent_entity_id/
    # used_entities, via ProvenanceManager.get_lineage()); downstream edges
    # come from ProvenanceManager.get_descendants()'s descendant chain (issue
    # #825, Part A item 5). Previously 'direction="downstream"' was dead code
    # here since no reverse lookup existed.
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen_nodes: set = set()
    seen_edges: set = set()

    ancestor_chain = lineage.get("lineage_chain") or lineage.get("entries") or []
    descendant_chain = (
        (descendants or {}).get("descendant_chain")
        or (descendants or {}).get("entries")
        or []
    )

    _add_chain_nodes(ancestor_chain, nodes, seen_nodes)
    _add_chain_nodes(descendant_chain, nodes, seen_nodes)

    _add_chain_edges(ancestor_chain, edges, seen_edges, "upstream")
    _add_chain_edges(descendant_chain, edges, seen_edges, "downstream")

    for edge in edges:
        for endpoint in (edge["source"], edge["target"]):
            if endpoint not in seen_nodes:
                seen_nodes.add(endpoint)
                prov_type, parent_id = _classify_prov("entity")
                nodes.append({
                    "id": endpoint,
                    "label": endpoint,
                    "prov_type": prov_type,
                    "parent_id": parent_id,
                    "source_document": None,
                    "source_location": None,
                    "source_quote": None,
                    "confidence": None,
                    "checksum": None,
                })

    return {"nodes": nodes, "edges": edges, "source": "audit"}


def _build_provenance(session: GraphSession, node_id: Optional[str] = None) -> dict:
    """Build provenance lineage for a node, attempting the audit-grade store first.

    Combines ProvenanceManager.get_lineage() (upstream ancestors) with
    get_descendants() (downstream — issue #825, Part A item 5) so both
    directions are populated from the audit-grade store, not just upstream.
    """
    if not node_id:
        return {"nodes": [], "edges": [], "source": "graph_traversal"}

    try:
        manager = getattr(session, "provenance_manager", None)
        if manager is not None:
            lineage = manager.get_lineage(node_id)
            if lineage and lineage.get("entity_count", 0) > 0:
                integrity_ok = lineage.get("integrity_verified")
                if integrity_ok is None:
                    entries = lineage.get("lineage_chain") or lineage.get("entries") or []
                    integrity_ok = all(verify_checksum(entry) for entry in entries)
                if integrity_ok:
                    descendants = {}
                    try:
                        descendants = manager.get_descendants(node_id) or {}
                    except Exception as exc:
                        logger.warning(
                            f"ProvenanceManager get_descendants failed for {node_id}: {exc}"
                        )
                    return _transform_audit_lineage(lineage, node_id, descendants)
                logger.warning(
                    f"Provenance integrity verification failed for {node_id}, falling back to graph traversal"
                )
    except Exception as exc:
        logger.warning(
            f"ProvenanceManager get_lineage failed for {node_id}, falling back to graph traversal: {exc}"
        )

    if node_id not in session.graph.nodes:
        return {"nodes": [], "edges": [], "source": "graph_traversal"}

    graph = nx.DiGraph()
    graph.add_node(node_id)

    hop_nodes = {node_id}
    for edge in session.graph.edges:
        if edge.source_id == node_id or edge.target_id == node_id:
            graph.add_edge(edge.source_id, edge.target_id, label=edge.edge_type)
            hop_nodes.add(edge.source_id)
            hop_nodes.add(edge.target_id)

    for edge in session.graph.edges:
        if edge.source_id in hop_nodes or edge.target_id in hop_nodes:
            graph.add_edge(edge.source_id, edge.target_id, label=edge.edge_type)

    subgraph = nx.ego_graph(graph, node_id, radius=2, undirected=True)
    provenance_nodes: List[Dict[str, Any]] = []
    for graph_node_id in subgraph.nodes():
        node = session.graph.nodes.get(graph_node_id)
        if node is None:
            continue
        prov_type, parent_id = _classify_prov(node.node_type)
        provenance_nodes.append(
            {
                "id": graph_node_id,
                "label": node.content or graph_node_id,
                "prov_type": prov_type,
                "parent_id": parent_id,
            }
        )

    provenance_edges: List[Dict[str, Any]] = []
    for source, target, data in subgraph.edges(data=True):
        if target == node_id:
            direction = "upstream"
        elif source == node_id:
            direction = "downstream"
        else:
            direction = "lateral"
        provenance_edges.append(
            {
                "id": f"{source}-{target}",
                "source": source,
                "target": target,
                "label": data.get("label", "related_to"),
                "direction": direction,
            }
        )

    return {"nodes": provenance_nodes, "edges": provenance_edges, "source": "graph_traversal"}


def _build_report(session: GraphSession, node_id: str) -> Dict[str, Any]:
    node = session.get_node(node_id)
    provenance = _build_provenance(session, node_id)
    return {
        "node_id": node_id,
        "label": node.get("content", node_id) if node else node_id,
        "type": node.get("type", "entity") if node else "entity",
        "properties": node.get("metadata", node.get("properties", {})) if node else {},
        "lineage": provenance,
        "source": provenance.get("source", "graph_traversal"),
    }


def _render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# Provenance Report: {report['label']}",
        "",
        f"- Node ID: `{report['node_id']}`",
        f"- Type: `{report['type']}`",
        "",
        "## Properties",
    ]
    properties = report.get("properties", {})
    if properties:
        for key, value in properties.items():
            lines.append(f"- **{key}**: {value}")
    else:
        lines.append("- No properties recorded")

    lines.extend(["", "## Lineage Nodes"])
    for node in report.get("lineage", {}).get("nodes", []):
        line = f"- `{node['id']}` ({node['prov_type']}): {node['label']}"
        if node.get("source_document"):
            line += f" [source: {node['source_document']}]"
        if node.get("confidence") is not None:
            line += f" (confidence: {node['confidence']})"
        if node.get("checksum"):
            line += f" (checksum: {node['checksum'][:8]}...)"
        lines.append(line)

    edges = report.get("lineage", {}).get("edges", [])
    grouped_edges: Dict[str, List] = {"upstream": [], "downstream": [], "lateral": []}
    for edge in edges:
        direction = edge.get("direction", "lateral")
        if direction not in grouped_edges:
            direction = "lateral"
        grouped_edges[direction].append(edge)

    if grouped_edges["upstream"]:
        lines.extend(["", "## Upstream"])
        for edge in grouped_edges["upstream"]:
            lines.append(f"- `{edge['source']}` -[{edge['label']}]-> `{edge['target']}`")

    if grouped_edges["downstream"]:
        lines.extend(["", "## Downstream"])
        for edge in grouped_edges["downstream"]:
            lines.append(f"- `{edge['source']}` -[{edge['label']}]-> `{edge['target']}`")

    if grouped_edges["lateral"]:
        lines.extend(["", "## Lateral"])
        for edge in grouped_edges["lateral"]:
            lines.append(f"- `{edge['source']}` -[{edge['label']}]-> `{edge['target']}`")

    return "\n".join(lines)


@router.get("", response_model=ProvenanceResponse)
@router.get("/", response_model=ProvenanceResponse, include_in_schema=False)
async def get_provenance_lineage(
    node_id: Optional[str] = None,
    session: GraphSession = Depends(get_session),
):
    data = await asyncio.to_thread(_build_provenance, session, node_id)
    return ProvenanceResponse(
        nodes=[ProvenanceNode(**node) for node in data["nodes"]],
        edges=[ProvenanceEdge(**edge) for edge in data["edges"]],
        source=data.get("source", "graph_traversal"),
    )


@router.get("/report")
async def export_provenance_report(
    node_id: str = Query(..., description="Node ID to export"),
    format: str = Query("json", description="json or markdown"),
    session: GraphSession = Depends(get_session),
):
    report = await asyncio.to_thread(_build_report, session, node_id)
    if format.lower() in {"md", "markdown"}:
        content = _render_markdown(report)
        return PlainTextResponse(
            content,
            headers={"Content-Disposition": f'attachment; filename="{_safe_content_disposition_filename(node_id, "_provenance.md")}"'},
        )

    content = json.dumps(report, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{_safe_content_disposition_filename(node_id, "_provenance.json")}"'},
    )
