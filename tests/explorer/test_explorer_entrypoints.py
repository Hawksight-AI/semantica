import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from semantica.context.context_graph import ContextGraph  # noqa: E402
from semantica.explorer.runtime import install_mutation_bridge  # noqa: E402
from semantica.explorer.session import GraphSession  # noqa: E402


def test_mutation_bridge_supports_multiple_apps_for_one_graph(monkeypatch):
    graph = ContextGraph(advanced_analytics=False)
    first_session = GraphSession(graph)
    second_session = GraphSession(graph)
    received = []
    graph.mutation_callback = lambda *event: received.append(("original", event))

    monkeypatch.setattr(
        first_session,
        "handle_graph_mutation",
        lambda *event: received.append(("first", event)),
    )
    monkeypatch.setattr(
        second_session,
        "handle_graph_mutation",
        lambda *event: received.append(("second", event)),
    )

    first_app = FastAPI()
    first_app.state.event_loop = None
    first_app.state.ws_manager = None
    second_app = FastAPI()
    second_app.state.event_loop = None
    second_app.state.ws_manager = None

    install_mutation_bridge(first_app, first_session)
    install_mutation_bridge(second_app, second_session)
    graph.mutation_callback("UPDATE_NODE", "node-1", {"content": "Updated"})

    assert [receiver for receiver, _ in received] == ["second", "first", "original"]


def test_mutation_bridge_is_idempotent_for_one_app(monkeypatch):
    graph = ContextGraph(advanced_analytics=False)
    session = GraphSession(graph)
    received = []
    monkeypatch.setattr(
        session,
        "handle_graph_mutation",
        lambda *event: received.append(event),
    )
    app = FastAPI()
    app.state.event_loop = None
    app.state.ws_manager = None

    install_mutation_bridge(app, session)
    install_mutation_bridge(app, session)
    graph.mutation_callback("UPDATE_NODE", "node-1", {"content": "Updated"})

    assert len(received) == 1


def test_legacy_server_mounts_editable_markdown_routes(monkeypatch):
    monkeypatch.setenv("SEMANTICA_ALLOW_ANONYMOUS", "true")

    from semantica import server

    paths = {route.path for route in server.app.routes}
    assert "/api/markdown/{kind}/{resource_id:path}" in paths
    assert "/api/memories" in paths
    assert "/ws/graph-updates" in paths

    with TestClient(server.app) as client:
        with client.websocket_connect("/ws/graph-updates") as websocket:
            acknowledgement = websocket.receive_json()
            assert acknowledgement["event"] == "connection_ack"
            assert acknowledgement["data"] == {"connected": True}
            assert acknowledgement["timestamp"]
        info = client.get("/api/info")
        memories = client.get("/api/memories")
        server.app.state.session.graph.add_node(
            "server-node",
            "Note",
            "Original server content",
        )
        current = client.get("/api/markdown/context-node/server-node").json()
        saved = client.put(
            "/api/markdown/context-node/server-node",
            json={
                "markdown": current["source"].replace(
                    "Original server content",
                    "Updated server content",
                ),
                "expected_revision": current["revision"],
            },
        )

    assert info.json()["capabilities"]["agent_memory"] is False
    assert memories.status_code == 503
    assert memories.json()["detail"] == (
        "AgentMemory is not configured for this Explorer instance."
    )
    assert saved.status_code == 200
    assert saved.json()["body"] == "Updated server content"
