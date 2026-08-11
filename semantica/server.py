"""
Semantica Server Entry Point

This module provides the REST API server for the Semantica framework
using FastAPI and uvicorn.
"""

import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from . import __version__
from .core.orchestrator import Semantica
from .utils.logging import setup_logging

try:
    from .context.context_graph import ContextGraph
    from .explorer.session import GraphSession
    from .explorer.ws import ConnectionManager
    from .explorer.dependencies import anonymous_access_allowed, get_expected_api_key, require_auth
    EXPLORER_AVAILABLE = True
except ImportError:
    EXPLORER_AVAILABLE = False

setup_logging()

STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown events."""
    logging.info("Starting up Semantica API...")

    if EXPLORER_AVAILABLE:
        if anonymous_access_allowed():
            logging.warning(
                "SEMANTICA_ALLOW_ANONYMOUS=true — all Explorer API routes are "
                "unauthenticated. Do not expose this process beyond localhost."
            )
        elif get_expected_api_key():
            logging.info("Explorer API authentication: enabled (SEMANTICA_API_KEY set).")
        else:
            logging.warning(
                "Explorer API authentication: NOT CONFIGURED. Protected routes "
                "will return 503 until SEMANTICA_API_KEY is set."
            )
        try:
            logging.info("Initializing Graph engine and Database connection...")
            graph = ContextGraph()
            app.state.session = GraphSession(graph)
            app.state.ws_manager = ConnectionManager()
            logging.info("Database Session and WebSockets attached to app state.")
        except Exception as e:
            logging.error(f"Failed to initialize GraphSession: {e}")
            app.state.session = None
            app.state.ws_manager = None
    else:
        app.state.session = None
        app.state.ws_manager = None

    yield  

    logging.info("Shutting down Semantica API...")
    if getattr(app.state, "session", None) and hasattr(app.state.session.graph, "close"):
        app.state.session.graph.close()


app = FastAPI(
    title="Semantica API",
    description="REST API for the Semantica Framework",
    version=__version__,
    lifespan=lifespan,
)

# --- CORS -----------------------------------------------------------
# Allow origins from environment (comma-separated); defaults to
# localhost only so production deployments must configure this.
_cors_origins_env = os.environ.get(
    "SEMANTICA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    max_age=600,
)


# --- Security response headers -------------------------------------
class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


app.add_middleware(_SecurityHeadersMiddleware)


# --- Global error handler ------------------------------------------
@app.exception_handler(Exception)
async def _global_error_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    logging.exception("Unhandled server error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


framework = Semantica()

class BuildRequest(BaseModel):
    sources: List[str]
    config: Optional[Dict[str, Any]] = None


@app.get("/api/info")
async def root():
    """Root endpoint returning framework info."""
    return {
        "name": "Semantica API",
        "version": __version__,
        "status": "active"
    }

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.post("/build")
async def build_kb(request: BuildRequest):
    """Initiate knowledge base construction."""
    try:
        # result = framework.build_knowledge_base(sources=request.sources, config=request.config)
        return {"status": "accepted", "message": "Knowledge base construction initiated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if EXPLORER_AVAILABLE:
    try:
        from .explorer.routes import (
            analytics,
            annotations,
            decisions,
            enrich,
            export_import,
            graph,
            ontology,
            temporal,
            vocabulary,
            provenance,
            sparql
        )

        _auth = [Depends(require_auth)]
        app.include_router(analytics.router, dependencies=_auth)
        app.include_router(annotations.router, dependencies=_auth)
        app.include_router(decisions.router, dependencies=_auth)
        app.include_router(enrich.router, dependencies=_auth)
        app.include_router(export_import.router, dependencies=_auth)
        app.include_router(graph.router, dependencies=_auth)
        app.include_router(ontology.router, dependencies=_auth)
        app.include_router(temporal.router, dependencies=_auth)
        app.include_router(vocabulary.router, dependencies=_auth)
        app.include_router(provenance.router, dependencies=_auth)
        app.include_router(sparql.router, dependencies=_auth)

        logging.info("Explorer, Vocabulary, SPARQL, Provenance, and Ontology API routes successfully mounted.")
    except Exception as exc:
        logging.error(f"Failed to mount explorer routes: {exc}")
else:
    logging.warning(
        "Explorer API routes not mounted. To enable the Knowledge Explorer, "
        "install the required dependencies: pip install 'semantica[explorer]'."
    )

# SPA catch all
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    """
    Catch-all route that serves React assets and index.html for React Router.
    """

    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")

    # Root path — serve index.html if built, otherwise a welcome JSON response
    if full_path in ("", "/"):
        index_file = STATIC_DIR / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse({
            "name": "Semantica Knowledge Explorer",
            "version": __version__,
            "message": "Welcome to Semantica. The frontend is not built yet — run `npm run build` inside the explorer/ directory, or open the Vite dev server at http://localhost:5173.",
            "docs": "/docs",
            "health": "/health",
        })

    normalized_path = os.path.normpath(full_path)
    if (
        os.path.isabs(normalized_path)
        or normalized_path == ".."
        or normalized_path.startswith(".." + os.sep)
    ):
        raise HTTPException(status_code=400, detail="Invalid path")

    # Ensure join remains relative to STATIC_DIR even if input includes leading separators
    safe_rel_path = normalized_path.lstrip("/\\")
    rel_parts = Path(safe_rel_path).parts
    if any(part in (".", "..") for part in rel_parts):
        raise HTTPException(status_code=400, detail="Invalid path")

    static_dir_resolved = STATIC_DIR.resolve()
    requested_file = (static_dir_resolved / Path(*rel_parts)).resolve(strict=False)

    # Prevent path traversal: reject any path that escapes STATIC_DIR
    if not requested_file.is_relative_to(static_dir_resolved):
        raise HTTPException(status_code=400, detail="Invalid path")

    if requested_file.is_file():
        return FileResponse(requested_file)

    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)

    raise HTTPException(
        status_code=404,
        detail="Frontend not built. Run `npm run build` in semantica-explorer/ first."
    )

def main():
    """Server entry point.

    Binds to loopback by default; set SEMANTICA_HOST to expose beyond
    localhost (e.g. behind a reverse proxy that terminates auth/TLS).
    """
    host = os.environ.get("SEMANTICA_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=8000)

if __name__ == "__main__":
    main()