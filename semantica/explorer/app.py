"""
Semantica Explorer FastAPI application factory.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from .session import GraphSession
from .ws import ConnectionManager


def _install_mutation_bridge(app: FastAPI, session: GraphSession) -> None:
    previous_callback = getattr(session.graph, "mutation_callback", None)

    def on_mutation(event_type: str, entity_id: str, payload: dict) -> None:
        session.handle_graph_mutation(event_type, entity_id, payload)
        if callable(previous_callback):
            previous_callback(event_type, entity_id, payload)
        loop = getattr(app.state, "event_loop", None)
        manager = getattr(app.state, "ws_manager", None)
        if loop is None or manager is None or loop.is_closed():
            return
        message = {
            "event_type": event_type,
            "entity_id": entity_id,
            "payload": payload,
        }
        asyncio.run_coroutine_threadsafe(
            manager.broadcast("graph_mutation", message),
            loop,
        )

    session.graph.mutation_callback = on_mutation


def create_app(session: Optional[GraphSession] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.event_loop = asyncio.get_running_loop()
        app.state.ws_manager = ConnectionManager()
        if session is not None:
            app.state.session = session
            _install_mutation_bridge(app, session)
        yield

    app = FastAPI(
        title="Semantica Knowledge Explorer",
        description="Interactive dashboard API for exploring Semantica knowledge graphs.",
        version=__version__,
        lifespan=lifespan,
    )

    _raw_origins = os.environ.get(
        "EXPLORER_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    _cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
    # allow_credentials lets browsers send cookies/auth headers cross-origin.
    # The Explorer has no authentication, so credentials serve no purpose and
    # enabling them when origins are broadened creates cross-site request risk.
    # Set EXPLORER_CORS_CREDENTIALS=true explicitly to opt in (e.g. for a
    # reverse-proxy setup that injects its own auth layer).
    _allow_credentials = os.environ.get("EXPLORER_CORS_CREDENTIALS", "false").lower() == "true"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_allow_credentials,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )

    import logging as _logging
    _logger = _logging.getLogger(__name__)

    @app.exception_handler(KeyError)
    async def key_error_handler(_request: Request, exc: KeyError):
        _logger.warning("KeyError: %s", exc)
        return JSONResponse(status_code=404, content={"detail": "Resource not found"})

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        _logger.warning("ValueError: %s", exc)
        return JSONResponse(status_code=422, content={"detail": "Invalid input"})

    @app.exception_handler(Exception)
    async def generic_error_handler(_request: Request, exc: Exception):
        if isinstance(exc, HTTPException):
            raise exc
        _logger.exception("Unhandled exception")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    from .routes.analytics import router as analytics_router
    from .routes.annotations import router as annotations_router
    from .routes.decisions import router as decisions_router
    from .routes.enrich import router as enrich_router
    from .routes.export_import import router as export_import_router
    from .routes.graph import router as graph_router
    from .routes.ontology import router as ontology_router
    from .routes.provenance import router as provenance_router
    from .routes.sparql import router as sparql_router
    from .routes.temporal import router as temporal_router
    from .routes.vocabulary import router as vocabulary_router

    app.include_router(graph_router)
    app.include_router(analytics_router)
    app.include_router(decisions_router)
    app.include_router(temporal_router)
    app.include_router(enrich_router)
    app.include_router(export_import_router)
    app.include_router(annotations_router)
    app.include_router(sparql_router)
    app.include_router(provenance_router)
    app.include_router(vocabulary_router)
    app.include_router(ontology_router)

    _WS_MAX_MESSAGE_BYTES = 64 * 1024  # 64 KB — control messages only

    @app.websocket("/ws/graph-updates")
    async def websocket_endpoint(websocket: WebSocket):
        manager: ConnectionManager = app.state.ws_manager
        await manager.connect(websocket)
        await manager.send_personal(websocket, "connection_ack", {"connected": True})
        try:
            while True:
                message = await websocket.receive_text()
                if len(message) > _WS_MAX_MESSAGE_BYTES:
                    await websocket.close(code=1009)  # 1009 = message too big
                    break
                if message.strip().lower() == "ping":
                    await manager.send_personal(websocket, "pong", {"ok": True})
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @app.get("/", include_in_schema=False)
    async def root():
        index_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        _logger.warning(
            "Explorer frontend bundle not found — UI unavailable. "
            "Install the package via pip to get the pre-built bundle, "
            "or run `cd explorer && npm ci && npm run build` from the repo root."
        )
        return HTMLResponse(
            '<!doctype html><html lang="en"><head><meta charset="UTF-8">'
            '<title>Semantica Knowledge Explorer</title>'
            '<style>body{font-family:sans-serif;padding:2rem;max-width:600px;margin:auto}'
            'code{background:#f4f4f4;padding:2px 6px;border-radius:3px}</style></head>'
            "<body><h2>Explorer UI not available</h2>"
            "<p>The frontend bundle was not found. This usually means the package was "
            "installed from source without building the frontend first.</p>"
            "<p><strong>To fix:</strong> reinstall via "
            "<code>pip install semantica[explorer]</code>, or build from source with "
            "<code>cd explorer &amp;&amp; npm ci &amp;&amp; npm run build</code> "
            "then restart the server.</p>"
            '<p>The REST API is still fully available at <a href="/docs">/docs</a>.</p>'
            "</body></html>",
            status_code=200,
        )

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/info")
    async def info():
        return {
            "name": "Semantica Knowledge Explorer",
            "version": __version__,
            "status": "active",
        }

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")
            index_path = static_dir / "index.html"
            if index_path.is_file():
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="Frontend build missing")

    return app


# Module-level app instance used by uvicorn and Docker CMD.
app = create_app()
