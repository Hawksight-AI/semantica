"""
Semantica MCP Server — JSON-RPC 2.0 over stdio.

Implements the Model Context Protocol so any MCP-compatible AI tool
(Claude Code, Cursor, Windsurf, Cline, Continue, VS Code Copilot, etc.)
can interact with the Semantica knowledge graph.

Run:
    python -m mcp                  # via __main__.py
    python -m mcp.server           # direct
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp import __version__
from mcp.resources import RESOURCE_DEFINITIONS, handle_resource_read
from mcp.tools import TOOL_DEFINITIONS

log = logging.getLogger("semantica.mcp.server")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str, data: Any = None) -> dict:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


# JSON-RPC error codes
_PARSE_ERROR = -32700
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

# ---------------------------------------------------------------------------
# Tool dispatch index
# ---------------------------------------------------------------------------

_TOOL_INDEX: dict[str, dict] = {t["name"]: t for t in TOOL_DEFINITIONS}


# ---------------------------------------------------------------------------
# Request handlers
# ---------------------------------------------------------------------------

def _handle_initialize(req_id: Any, params: dict) -> dict:
    return _ok(req_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {},
            "resources": {},
        },
        "serverInfo": {
            "name": "semantica-mcp",
            "version": __version__,
        },
    })


def _handle_tools_list(req_id: Any, _params: dict) -> dict:
    tools = [
        {
            "name": t["name"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
        }
        for t in TOOL_DEFINITIONS
    ]
    return _ok(req_id, {"tools": tools})


def _handle_tools_call(req_id: Any, params: dict) -> dict:
    name = params.get("name", "")
    args = params.get("arguments", {}) or {}

    tool = _TOOL_INDEX.get(name)
    if tool is None:
        return _err(req_id, _METHOD_NOT_FOUND, f"Unknown tool: {name}")

    try:
        result = tool["_handler"](args)
    except Exception as exc:
        log.exception("Tool %s raised an exception", name)
        # The exception's class name (e.g. "ValidationError", "TimeoutError")
        # is safe to surface — unlike str(exc), it never carries paths,
        # connection strings, or other internal detail — and lets the
        # client distinguish failure kinds without a full message.
        return _err(
            req_id, _INTERNAL_ERROR,
            f"Tool '{name}' failed ({type(exc).__name__}). See server logs for details.",
        )

    # MCP spec: content must be a list of content items
    return _ok(req_id, {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        "isError": "error" in result,
    })


def _handle_resources_list(req_id: Any, _params: dict) -> dict:
    return _ok(req_id, {"resources": RESOURCE_DEFINITIONS})


def _handle_resources_read(req_id: Any, params: dict) -> dict:
    uri = params.get("uri", "").strip()
    if not uri:
        return _err(req_id, _INVALID_PARAMS, "uri is required")
    resource = handle_resource_read(uri)
    return _ok(req_id, {
        "contents": [
            {
                "uri": resource["uri"],
                "mimeType": resource.get("mimeType", "application/json"),
                "text": resource.get("text", ""),
            }
        ]
    })


def _handle_ping(req_id: Any, _params: dict) -> dict:
    return _ok(req_id, {})


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_DISPATCH = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
    "resources/list": _handle_resources_list,
    "resources/read": _handle_resources_read,
    "ping": _handle_ping,
}


# ---------------------------------------------------------------------------
# Main server class
# ---------------------------------------------------------------------------

class SemanticaMCPServer:
    """Semantica MCP server — reads JSON-RPC requests from stdin, writes to stdout."""

    def __init__(self, *, debug: bool = False) -> None:
        level = logging.DEBUG if debug else logging.WARNING
        logging.basicConfig(stream=sys.stderr, level=level,
                            format="%(name)s %(levelname)s %(message)s")

    # ------------------------------------------------------------------
    def dispatch(self, request: dict) -> dict | None:
        """Process one JSON-RPC request and return a response dict (or None for notifications)."""
        req_id = request.get("id")  # None for notifications
        method = request.get("method", "")
        params = request.get("params") or {}

        handler = _DISPATCH.get(method)
        if handler is None:
            if req_id is None:
                return None  # Notification — ignore unknown methods silently
            return _err(req_id, _METHOD_NOT_FOUND, f"Method not found: {method}")

        try:
            return handler(req_id, params)
        except Exception as exc:
            log.exception("Unhandled error in method %s", method)
            if req_id is None:
                return None
            return _err(
                req_id, _INTERNAL_ERROR,
                f"Method '{method}' failed ({type(exc).__name__}). See server logs for details.",
            )

    # ------------------------------------------------------------------
    def run(self) -> None:
        """Start the stdio event loop."""
        log.info("Semantica MCP server starting (stdio)")
        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                request = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                response = _err(None, _PARSE_ERROR, f"Parse error: {exc}")
                _write(response)
                continue

            if isinstance(request, list):
                # Batch request
                responses = []
                for req in request:
                    resp = self.dispatch(req)
                    if resp is not None:
                        responses.append(resp)
                if responses:
                    _write(responses)
            else:
                resp = self.dispatch(request)
                if resp is not None:
                    _write(resp)


def _write(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Semantica MCP Server")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    SemanticaMCPServer(debug=args.debug).run()


if __name__ == "__main__":
    main()
