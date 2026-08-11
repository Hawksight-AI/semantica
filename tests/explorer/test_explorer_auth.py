"""Tests for the API-key auth dependency added for GHSA-j4mq-hprp-987v
(missing authentication on all Explorer API routes).

Covers: protected routes refuse requests when no key is configured (fail
closed, not fail open), reject wrong/missing keys once a key is
configured, accept the correct key, remain reachable when
SEMANTICA_ALLOW_ANONYMOUS=true is set explicitly, and that health/info/
static routes stay public regardless. Also covers the /ws/graph-updates
handshake, which can't use the same FastAPI Depends() plumbing since
browsers can't set custom headers on a WebSocket handshake.
"""

import pytest

from semantica.context.context_graph import ContextGraph
from semantica.explorer.app import create_app
from semantica.explorer.session import GraphSession

try:
    from starlette.testclient import TestClient
except ImportError:
    pytest.skip(
        "starlette TestClient is required for explorer tests. Install semantica[explorer].",
        allow_module_level=True,
    )


def _build_sample_graph() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("python", node_type="language", content="Python")
    return graph


@pytest.fixture
def client():
    session = GraphSession(_build_sample_graph())
    app = create_app(session=session)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Fail-closed: no SEMANTICA_API_KEY and no explicit anonymous opt-in.
# ---------------------------------------------------------------------------

def test_protected_route_returns_503_when_auth_not_configured(client, monkeypatch):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)

    resp = client.get("/api/graph/nodes")

    assert resp.status_code == 503


def test_write_route_also_refuses_when_auth_not_configured(client, monkeypatch):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)

    resp = client.post("/api/export", json={"format": "json"})

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Configured key: wrong/missing key rejected, correct key accepted.
# ---------------------------------------------------------------------------

def test_protected_route_rejects_missing_key(client, monkeypatch):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("SEMANTICA_API_KEY", "correct-key")

    resp = client.get("/api/graph/nodes")

    assert resp.status_code == 401


def test_protected_route_rejects_wrong_key(client, monkeypatch):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("SEMANTICA_API_KEY", "correct-key")

    resp = client.get("/api/graph/nodes", headers={"X-API-Key": "wrong-key"})

    assert resp.status_code == 401


def test_protected_route_accepts_correct_key(client, monkeypatch):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("SEMANTICA_API_KEY", "correct-key")

    resp = client.get("/api/graph/nodes", headers={"X-API-Key": "correct-key"})

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Explicit opt-in: SEMANTICA_ALLOW_ANONYMOUS=true.
# ---------------------------------------------------------------------------

def test_anonymous_opt_in_allows_requests_without_a_key(client, monkeypatch):
    monkeypatch.setenv("SEMANTICA_ALLOW_ANONYMOUS", "true")
    monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)

    resp = client.get("/api/graph/nodes")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Public routes stay public regardless of auth configuration.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/health", "/api/info"])
def test_public_routes_stay_public_when_auth_not_configured(client, monkeypatch, path):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)

    resp = client.get(path)

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket handshake: header or query-param key, same policy as REST.
# ---------------------------------------------------------------------------

def test_websocket_rejects_connection_without_key_when_configured(client, monkeypatch):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("SEMANTICA_API_KEY", "correct-key")

    with pytest.raises(Exception):
        with client.websocket_connect("/ws/graph-updates"):
            pass


def test_websocket_accepts_connection_with_correct_query_param_key(client, monkeypatch):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("SEMANTICA_API_KEY", "correct-key")

    with client.websocket_connect("/ws/graph-updates?api_key=correct-key") as websocket:
        ack = websocket.receive_json()
    assert ack["event"] == "connection_ack"


def test_websocket_accepts_connection_with_header_key(client, monkeypatch):
    monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("SEMANTICA_API_KEY", "correct-key")

    with client.websocket_connect(
        "/ws/graph-updates", headers={"X-API-Key": "correct-key"}
    ) as websocket:
        ack = websocket.receive_json()
    assert ack["event"] == "connection_ack"
