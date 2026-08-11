"""
Import and export routes for graph datasets.
"""

import csv
import io
import json
import logging
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..dependencies import get_session
from ..schemas import DistanceExportRequest, ExportRequest, ImportResponse
from ..session import GraphSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Export / Import"])

_IMPORT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
# Only formats that the import handler actually parses.
# Do not add extensions here unless a corresponding parsing branch exists below.
_ALLOWED_IMPORT_EXTENSIONS = frozenset({".json", ".csv"})

# SECURITY: Strip characters from imported node IDs that would enable stored
# HTTP response header injection (CWE-20 / CWE-113).  These IDs are later
# reflected verbatim into Content-Disposition filename= headers by the
# provenance report endpoint -- CRLF sequences in an ID can split the HTTP
# response and inject arbitrary headers (Set-Cookie, Content-Type, etc.).
# NUL bytes truncate filenames on POSIX and some Windows APIs.
_UNSAFE_ID_CHARS = re.compile(r'[\r\n\x00"\\]')
_MAX_IMPORT_NODE_ID_LEN = 512


def _sanitize_import_node_id(raw: object) -> str:
    """Sanitize a node ID arriving from an uploaded CSV or JSON file.

    Strips CR, LF, NUL, double-quotes, and backslashes, then length-caps the
    result. These are the characters that enable CRLF header injection when
    the ID is later used in a Content-Disposition filename= parameter.
    """
    if raw is None:
        return ""
    cleaned = _UNSAFE_ID_CHARS.sub("_", str(raw).strip())
    if len(cleaned) > _MAX_IMPORT_NODE_ID_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Node ID exceeds maximum length of {_MAX_IMPORT_NODE_ID_LEN} characters.",
        )
    return cleaned


def _safe_float(val: object, default: float = 1.0) -> float:
    """Safely convert weight or numeric fields to float with default fallback."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _extract_raw_node_id(raw_node: dict) -> object | None:
    """Extract raw node ID from dict checking root and properties fields."""
    raw_id = (
        raw_node.get("id")
        or raw_node.get("_id")
        or raw_node.get("node_id")
        or raw_node.get("uri")
        or raw_node.get("key")
    )
    if raw_id is None and isinstance(raw_node.get("properties"), dict):
        raw_id = (
            raw_node["properties"].get("id")
            or raw_node["properties"].get("_id")
            or raw_node["properties"].get("node_id")
        )
    return raw_id


def _extract_raw_edge_endpoints(raw_edge: dict) -> tuple[object | None, object | None]:
    """Extract raw source and target identifiers checking alternative key names."""
    raw_source = (
        raw_edge.get("source")
        or raw_edge.get("source_id")
        or raw_edge.get("start")
        or raw_edge.get("start_id")
        or raw_edge.get("START_ID")
        or raw_edge.get(":START_ID")
        or raw_edge.get("from")
        or raw_edge.get("src")
    )
    raw_target = (
        raw_edge.get("target")
        or raw_edge.get("target_id")
        or raw_edge.get("end")
        or raw_edge.get("end_id")
        or raw_edge.get("END_ID")
        or raw_edge.get(":END_ID")
        or raw_edge.get("to")
        or raw_edge.get("dst")
    )
    return raw_source, raw_target


def _import_response(nodes_added: int, edges_added: int, message: str = "Import successful") -> ImportResponse:
    return ImportResponse(
        status="success",
        message=message,
        nodes_added=nodes_added,
        edges_added=edges_added,
        nodes_imported=nodes_added,
        edges_imported=edges_added,
    )


@router.post("/api/import", response_model=ImportResponse)
async def import_file(
    file: UploadFile = File(...),
    session: GraphSession = Depends(get_session),
):
    import os as _os
    filename = (file.filename or "").lower()
    ext = _os.path.splitext(filename)[1]
    if ext not in _ALLOWED_IMPORT_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_IMPORT_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > _IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds the {_IMPORT_MAX_BYTES // (1024 * 1024)} MB limit.",
        )

    if filename.endswith(".json"):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON file: {exc}") from exc

        if isinstance(data, list):
            if data and isinstance(data[0], dict) and any(
                key in data[0]
                for key in {"source", "source_id", "target", "target_id", "START_ID", "END_ID", "start", "end", "from", "to"}
            ):
                raw_nodes = []
                raw_edges = data
            else:
                raw_nodes = data
                raw_edges = []
        elif isinstance(data, dict):
            raw_nodes = data.get("nodes", data.get("entities", []))
            raw_edges = data.get("edges", data.get("relationships", []))
        else:
            raise HTTPException(status_code=422, detail="JSON import expects an object or array payload")

        nodes = []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                continue
            raw_id = _extract_raw_node_id(raw_node)
            sanitized_id = _sanitize_import_node_id(raw_id) if raw_id is not None else ""

            if "properties" in raw_node:
                node_dict = dict(raw_node)
                if sanitized_id:
                    node_dict["id"] = sanitized_id
                    if isinstance(node_dict.get("properties"), dict) and "id" in node_dict["properties"]:
                        node_dict["properties"]["id"] = sanitized_id
                nodes.append(node_dict)
            else:
                metadata = raw_node.get("metadata", {}) or {}
                if not isinstance(metadata, dict):
                    metadata = {}
                content_text = raw_node.get("text") or raw_node.get("content") or raw_node.get("label") or raw_node.get("name") or sanitized_id
                nodes.append(
                    {
                        "id": sanitized_id,
                        "type": raw_node.get("type", raw_node.get("label", "entity")),
                        "properties": {
                            "content": content_text,
                            **metadata,
                        },
                    }
                )

        edges = []
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, dict):
                continue
            raw_source, raw_target = _extract_raw_edge_endpoints(raw_edge)
            if not raw_source or not raw_target:
                continue

            source_id = _sanitize_import_node_id(raw_source)
            target_id = _sanitize_import_node_id(raw_target)
            if not source_id or not target_id:
                continue

            raw_edge_id = raw_edge.get("id") or raw_edge.get("edge_id")
            edge_id = _sanitize_import_node_id(raw_edge_id) if raw_edge_id is not None else None

            raw_family_id = raw_edge.get("familyId") or raw_edge.get("family_id")
            family_id = _sanitize_import_node_id(raw_family_id) if raw_family_id is not None else None

            edge_properties = raw_edge.get("metadata", raw_edge.get("properties", {})) or {}
            if not isinstance(edge_properties, dict):
                edge_properties = {}

            weight = _safe_float(raw_edge.get("weight", 1.0))

            edges.append(
                {
                    "id": edge_id,
                    "familyId": family_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    "type": raw_edge.get("type", raw_edge.get("relationship", "related_to")),
                    "weight": weight,
                    "properties": edge_properties,
                    "valid_from": raw_edge.get("valid_from", edge_properties.get("valid_from")),
                    "valid_until": raw_edge.get("valid_until", edge_properties.get("valid_until")),
                }
            )

        try:
            nodes_added, edges_added = session.add_nodes_and_edges(nodes, edges)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _import_response(nodes_added, edges_added)

    if filename.endswith(".csv"):
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="CSV file must be UTF-8 encoded") from exc

        reader = csv.DictReader(io.StringIO(decoded))
        nodes = []
        edges = []
        for row in reader:
            raw_source, raw_target = _extract_raw_edge_endpoints(row)
            raw_node_id = (
                row.get("id")
                or row.get("node_id")
                or row.get(":ID")
                or row.get("_id")
                or row.get("ID")
                or row.get("uri")
                or row.get("key")
            )

            if raw_source and raw_target:
                source_id = _sanitize_import_node_id(raw_source)
                target_id = _sanitize_import_node_id(raw_target)
                if not source_id or not target_id:
                    continue

                raw_edge_id = row.get("id") or row.get("edge_id")
                edge_id = _sanitize_import_node_id(raw_edge_id) if raw_edge_id else None

                raw_family_id = row.get("familyId") or row.get("family_id")
                family_id = _sanitize_import_node_id(raw_family_id) if raw_family_id else None

                edge_props = {
                    key: value
                    for key, value in row.items()
                    if key not in {
                        "id",
                        "edge_id",
                        "familyId",
                        "family_id",
                        "source",
                        "source_id",
                        "target",
                        "target_id",
                        "type",
                        "relationship",
                        "weight",
                        ":START_ID",
                        "START_ID",
                        ":END_ID",
                        "END_ID",
                        ":TYPE",
                        "from",
                        "src",
                        "to",
                        "dst",
                    }
                    and value is not None
                }
                weight = _safe_float(row.get("weight", 1.0))

                edges.append(
                    {
                        "id": edge_id,
                        "familyId": family_id,
                        "source_id": source_id,
                        "target_id": target_id,
                        "type": row.get("type") or row.get("relationship") or row.get(":TYPE") or "related_to",
                        "weight": weight,
                        "properties": edge_props,
                    }
                )
            elif raw_node_id:
                sanitized_node_id = _sanitize_import_node_id(raw_node_id)
                if not sanitized_node_id:
                    continue
                node_props = {
                    key: value
                    for key, value in row.items()
                    if key not in {"id", "node_id", "type", "label", ":ID", "_id", "ID", ":LABEL", "uri", "key"}
                    and value is not None
                }
                nodes.append(
                    {
                        "id": sanitized_node_id,
                        "type": row.get("type") or row.get("label") or row.get(":LABEL") or "entity",
                        "properties": node_props,
                    }
                )

        if not nodes and not edges:
            raise HTTPException(
                status_code=422,
                detail="No valid nodes or edges could be parsed from the CSV payload.",
            )

        try:
            nodes_added, edges_added = session.add_nodes_and_edges(nodes, edges)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _import_response(nodes_added, edges_added)

    raise HTTPException(
        status_code=422,
        detail=f"Unsupported file type '{_os.path.splitext(filename)[1]}'. Allowed: {sorted(_ALLOWED_IMPORT_EXTENSIONS)}",
    )


@router.post("/api/export")
async def export_graph(
    body: ExportRequest,
    session: GraphSession = Depends(get_session),
):
    fmt = body.format.lower()
    graph_dict = session.build_graph_dict(body.node_ids)

    if fmt == "json":
        content = json.dumps(graph_dict, indent=2, default=str)
        media_type = "application/json"
        extension = "json"
    elif fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["kind", "id", "familyId", "type", "content", "source", "target", "weight"])
        for node in graph_dict.get("entities", []):
            writer.writerow(["node", node.get("id"), "", node.get("type"), node.get("text"), "", "", ""])
        for edge in graph_dict.get("relationships", []):
            writer.writerow([
                "edge",
                edge.get("id"),
                edge.get("familyId"),
                edge.get("type"),
                "",
                edge.get("source"),
                edge.get("target"),
                edge.get("metadata", {}).get("weight", edge.get("weight", "")),
            ])

        content = output.getvalue()
        media_type = "text/csv"
        extension = "csv"
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported export format '{fmt}'")

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="semantica_export.{extension}"'},
    )


_DISTANCE_EXPORT_MAX_NODES = 200


@router.post("/api/export/distance-enriched")
async def export_distance_enriched(
    body: DistanceExportRequest,
    session: GraphSession = Depends(get_session),
):
    """FR-10 — Export pairwise distance metrics as CSV or JSONL for ML pipelines."""
    if not body.node_subset:
        raise HTTPException(
            status_code=422,
            detail=(
                f"node_subset is required; provide up to {_DISTANCE_EXPORT_MAX_NODES} node IDs to export."
            ),
        )
    if len(body.node_subset) > _DISTANCE_EXPORT_MAX_NODES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"node_subset exceeds limit: {len(body.node_subset)} nodes requested; "
                f"maximum is {_DISTANCE_EXPORT_MAX_NODES}."
            ),
        )

    import asyncio

    from ...export.distance_exporter import DistanceExporter

    exporter = DistanceExporter(session.graph)

    if body.format == "csv":
        content = await asyncio.to_thread(
            exporter.to_csv_string,
            include=body.include,
            node_subset=body.node_subset,
        )
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="distances.csv"'},
        )
    else:
        content = await asyncio.to_thread(
            exporter.to_jsonl_string,
            include=body.include,
            node_subset=body.node_subset,
        )
        return Response(
            content=content,
            media_type="application/x-ndjson",
            headers={"Content-Disposition": 'attachment; filename="distances.jsonl"'},
        )
