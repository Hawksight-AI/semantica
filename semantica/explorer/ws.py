"""
Semantica Explorer : WebSocket Connection Manager

Manages WebSocket connections for real-time graph updates,
import progress events, and mutation broadcasts.
"""

import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .dependencies import is_valid_api_key

_WS_MAX_MESSAGE_BYTES = 64 * 1024


def install_graph_updates_websocket(
    app: FastAPI,
    allowed_origins: Sequence[str],
) -> None:
    """Install the authenticated graph-mutation WebSocket endpoint."""
    allowed_origin_set = frozenset(allowed_origins)

    @app.websocket("/ws/graph-updates")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        # CORSMiddleware does not cover WebSocket handshakes. Reject foreign
        # browser origins against the same allowlist used for HTTP CORS.
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in allowed_origin_set:
            await websocket.close(code=4403)
            return

        # Browser clients pass the API key as a query parameter because the
        # WebSocket API cannot set custom headers.
        candidate = websocket.headers.get("x-api-key") or websocket.query_params.get(
            "api_key"
        )
        if not is_valid_api_key(candidate):
            await websocket.close(code=4401)
            return

        manager: ConnectionManager = app.state.ws_manager
        await manager.connect(websocket)
        await manager.send_personal(websocket, "connection_ack", {"connected": True})
        try:
            while True:
                message = await websocket.receive_text()
                if len(message) > _WS_MAX_MESSAGE_BYTES:
                    await websocket.close(code=1009)
                    break
                if message.strip().lower() == "ping":
                    await manager.send_personal(websocket, "pong", {"ok": True})
        except WebSocketDisconnect:
            manager.disconnect(websocket)


class ConnectionManager:
    """
    Thread-safe WebSocket connection manager.

    Maintains a set of active WebSocket connections and provides
    methods to broadcast events to all connected clients.
    """

    def __init__(self):
        self._active_connections: Set[WebSocket] = set()
        self._lock = threading.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and add it to the active set."""
        await websocket.accept()
        with self._lock:
            self._active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active set."""
        with self._lock:
            self._active_connections.discard(websocket)

    @property
    def active_count(self) -> int:
        """Number of active connections."""
        with self._lock:
            return len(self._active_connections)

    async def broadcast(self, event_type: str, data: Any = None) -> None:
        """
        Broadcast a JSON message to all connected clients.

        Args:
            event_type: Event type string (e.g., "node_added", "import_progress").
            data: Arbitrary JSON-serialisable payload.
        """
        message = json.dumps(
            {
                "event": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            default=str,
        )

        with self._lock:
            connections = set(self._active_connections)

        disconnected: List[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        if disconnected:
            with self._lock:
                for ws in disconnected:
                    self._active_connections.discard(ws)

    async def send_personal(
        self, websocket: WebSocket, event_type: str, data: Any = None
    ) -> None:
        """Send a message to a single client."""
        message = json.dumps(
            {
                "event": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            default=str,
        )
        await websocket.send_text(message)
