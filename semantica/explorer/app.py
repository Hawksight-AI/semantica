"""
Semantica Explorer FastAPI application factory.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..context.context_graph import ContextGraph
from .dependencies import anonymous_access_allowed, get_expected_api_key, is_valid_api_key, require_auth
from .session import GraphSession
from .ws import ConnectionManager


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _read_explorer_settings() -> dict:
    if "ALLOWED_ORIGINS" in os.environ:
        raw_origins = os.environ["ALLOWED_ORIGINS"]
    elif "EXPLORER_CORS_ORIGINS" in os.environ:
        raw_origins = os.environ["EXPLORER_CORS_ORIGINS"]
    else:
        raw_origins = "http://localhost:5173,http://127.0.0.1:5173"
    return {
        "allowed_origins": [
            origin.strip() for origin in raw_origins.split(",") if origin.strip()
        ],
        # These are read and stored for future use when direct FalkorDB connection
        # support is added to the Explorer. Currently GraphSession uses an in-memory
        # ContextGraph and does not open a network connection to FalkorDB.
        "falkordb_host": os.environ.get("FALKORDB_HOST", "localhost"),
        "falkordb_port": _read_int_env("FALKORDB_PORT", 6379),
        "provenance_storage_path": os.environ.get(
            "SEMANTICA_PROVENANCE_DB",
            os.environ.get("EXPLORER_PROVENANCE_DB"),
        ),
    }


def _install_mutation_bridge(app: FastAPI, session: GraphSession) -> None:
    if getattr(session.graph, "_mutation_bridge_installed", False):
        return
    session.graph._mutation_bridge_installed = True
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


def create_app(
    session: Optional[GraphSession] = None,
    provenance_storage_path: Optional[str] = None,
) -> FastAPI:
    settings = _read_explorer_settings()
    prov_path = provenance_storage_path or settings.get("provenance_storage_path")
    if session is None:
        active_session = GraphSession(
            ContextGraph(advanced_analytics=False),
            provenance_storage_path=prov_path,
        )
    else:
        active_session = session
        if prov_path is not None:
            active_session.set_provenance_storage_path(prov_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import logging as _lifespan_logging
        _lifespan_logger = _lifespan_logging.getLogger(__name__)
        if anonymous_access_allowed():
            _lifespan_logger.warning(
                "Explorer is running with SEMANTICA_ALLOW_ANONYMOUS=true — "
                "all API routes are unauthenticated. Do not expose this "
                "process beyond localhost."
            )
        elif get_expected_api_key():
            _lifespan_logger.info("Explorer API authentication: enabled (SEMANTICA_API_KEY set).")
        else:
            _lifespan_logger.warning(
                "Explorer API authentication: NOT CONFIGURED. All protected "
                "routes will return 503 until SEMANTICA_API_KEY is set."
            )

        app.state.event_loop = asyncio.get_running_loop()
        app.state.ws_manager = ConnectionManager()
        app.state.session = active_session
        _install_mutation_bridge(app, active_session)
        yield

    app = FastAPI(
        title="Semantica Knowledge Explorer",
        description="Interactive dashboard API for exploring Semantica knowledge graphs.",
        version=__version__,
        lifespan=lifespan,
    )

    app.state.explorer_settings = settings

    # allow_credentials lets browsers send cookies/auth headers cross-origin.
    # Credentials aren't needed for the X-API-Key auth scheme below, and
    # enabling them when origins are broadened creates cross-site request
    # risk. Set EXPLORER_CORS_CREDENTIALS=true explicitly to opt in (e.g.
    # for a reverse-proxy setup that injects its own cookie-based auth).
    _allow_credentials = os.environ.get("EXPLORER_CORS_CREDENTIALS", "false").lower() == "true"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings["allowed_origins"],
        allow_credentials=_allow_credentials,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
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

    _auth = [Depends(require_auth)]
    app.include_router(graph_router, dependencies=_auth)
    app.include_router(analytics_router, dependencies=_auth)
    app.include_router(decisions_router, dependencies=_auth)
    app.include_router(temporal_router, dependencies=_auth)
    app.include_router(enrich_router, dependencies=_auth)
    app.include_router(export_import_router, dependencies=_auth)
    app.include_router(annotations_router, dependencies=_auth)
    app.include_router(sparql_router, dependencies=_auth)
    app.include_router(provenance_router, dependencies=_auth)
    app.include_router(vocabulary_router, dependencies=_auth)
    app.include_router(ontology_router, dependencies=_auth)

    _WS_MAX_MESSAGE_BYTES = 64 * 1024  # 64 KB — control messages only

    @app.websocket("/ws/graph-updates")
    async def websocket_endpoint(websocket: WebSocket):
        # CORSMiddleware doesn't cover WebSocket handshakes (Starlette's
        # CORS support only wraps HTTP), so under SEMANTICA_ALLOW_ANONYMOUS
        # the key check below accepts any origin — loopback binding isn't a
        # boundary against a browser, since any page the operator has open
        # can still reach ws://localhost:.../ws/graph-updates directly.
        # Reject a foreign Origin explicitly here, against the same
        # allowlist CORSMiddleware already enforces for HTTP
        # (GHSA-4643-wpgq-w329). Browsers always send Origin on a
        # cross-origin WebSocket handshake; native/CLI clients omit it
        # entirely, so a missing Origin is allowed through — the browser is
        # the only threat this check is closing.
        origin = websocket.headers.get("origin")
        allowed_origins = app.state.explorer_settings["allowed_origins"]
        if origin is not None and origin not in allowed_origins:
            await websocket.close(code=4403)  # forbidden
            return

        # Browsers can't set custom headers on a WebSocket handshake, so
        # accept the key via header (non-browser clients) or query param
        # (browser clients), same SEMANTICA_API_KEY the REST routes check.
        candidate = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
        if not is_valid_api_key(candidate):
            await websocket.close(code=4401)  # unauthorized
            return

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
        return {"status": "ok"}

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
