"""
Semantica MCP — Streamable HTTP bridge.

Exposes the stdio-only `semantica.mcp_server` (JSON-RPC 2.0) over the
Model Context Protocol **Streamable HTTP** transport, so any MCP client
(Claude Code, Cursor, Cline, etc.) can reach it remotely via HTTP.

Endpoints
---------
  GET  /          -> server info
  GET  /health    -> liveness probe
  POST /mcp       -> Streamable HTTP endpoint (JSON or SSE response)

Run
---
  uvicorn mcp_http_bridge:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request, Response

from semantica import __version__ as _SEMANTICA_VERSION
from semantica.mcp_server import _handle

log = logging.getLogger("semantica.mcp.http_bridge")

APP_NAME = "semantica-mcp"
PROTOCOL_VERSION = "2024-11-05"

app = FastAPI(title=APP_NAME, version=_SEMANTICA_VERSION)


@app.get("/")
async def root() -> dict:
    return {
        "name": APP_NAME,
        "version": _SEMANTICA_VERSION,
        "transport": "streamable-http",
        "endpoint": "/mcp",
        "protocolVersion": PROTOCOL_VERSION,
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": APP_NAME}


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> Response:
    """Streamable HTTP MCP endpoint — JSON-RPC 2.0 (single or batch)."""
    accept = request.headers.get("accept", "")
    want_sse = "text/event-stream" in accept

    try:
        body = await request.body()
        req = json.loads(body) if body else {}
    except Exception as exc:  # noqa: BLE001
        return _json_response(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            },
            want_sse=want_sse,
            status_code=400,
        )

    # Batch request
    if isinstance(req, list):
        responses = [r for sub in req if (r := _handle(sub)) is not None]
        if not responses:
            return Response(status_code=202)  # all notifications
        return _json_response(responses, want_sse=want_sse)

    resp = _handle(req)
    if resp is None:
        # Notification — acknowledge silently (202 Accepted)
        return Response(status_code=202)

    return _json_response(resp, want_sse=want_sse)


def _json_response(payload: dict | list, *, want_sse: bool, status_code: int = 200) -> Response:
    text = json.dumps(payload, ensure_ascii=False)
    headers = {
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "Cache-Control": "no-store",
    }
    if want_sse:
        sse_body = f"event: message\ndata: {text}\n\n"
        return Response(
            content=sse_body,
            media_type="text/event-stream",
            headers=headers,
            status_code=status_code,
        )
    return Response(
        content=text,
        media_type="application/json",
        headers=headers,
        status_code=status_code,
    )
