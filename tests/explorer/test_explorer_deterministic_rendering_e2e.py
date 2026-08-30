"""
End-to-end integration test for deterministic Explorer rendering (Issue #1037).

Validates:
1. Building the canonical 4-node, 3-edge graph using ContextGraph.
2. Serialization via save_to_file().
3. Reloading via load_from_file() and GraphSession.from_file() without mutation.
4. Explorer HTTP API serving exact nodes, edges, edge types, and connectivity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# fastapi ships in the optional `explorer` extra, not in `dev`, so this module
# must skip rather than fail collection when it is absent. The guard has to sit
# above the explorer imports below, which pull fastapi in transitively.
pytest.importorskip("fastapi")

from semantica.context.context_graph import ContextGraph  # noqa: E402
from semantica.explorer.app import create_app  # noqa: E402
from semantica.explorer.session import GraphSession  # noqa: E402

try:
    from starlette.testclient import TestClient
except ImportError:
    pytest.skip(
        "starlette TestClient required. Install semantica[explorer].",
        allow_module_level=True,
    )


def _build_deterministic_graph() -> ContextGraph:
    """Build the exact graph requested in Semantica #1037."""
    graph = ContextGraph(advanced_analytics=False)

    graph.add_node("alice", "Person", content="Alice")
    graph.add_node("bob", "Person", content="Bob")
    graph.add_node("acme", "Organization", content="Acme")
    graph.add_node("new_york", "Location", content="New York")

    graph.add_edge("alice", "acme", edge_type="WORKS_AT")
    graph.add_edge("bob", "alice", edge_type="KNOWS")
    graph.add_edge("acme", "new_york", edge_type="LOCATED_IN")

    return graph


class TestExplorerDeterministicRenderingE2E:
    """E2E suite for deterministic graph rendering and session loading."""

    def test_build_and_in_memory_structure(self):
        graph = _build_deterministic_graph()

        assert len(graph.nodes) == 4
        assert len(graph.edges) == 3

        node_map = {
            nid: (node.node_type, node.content) for nid, node in graph.nodes.items()
        }
        assert node_map["alice"] == ("Person", "Alice")
        assert node_map["bob"] == ("Person", "Bob")
        assert node_map["acme"] == ("Organization", "Acme")
        assert node_map["new_york"] == ("Location", "New York")

        edge_tuples = {(e.source_id, e.target_id, e.edge_type) for e in graph.edges}
        assert edge_tuples == {
            ("alice", "acme", "WORKS_AT"),
            ("bob", "alice", "KNOWS"),
            ("acme", "new_york", "LOCATED_IN"),
        }

    def test_serialization_and_deserialization(self, tmp_path: Path):
        graph = _build_deterministic_graph()
        output_file = tmp_path / "explorer_deterministic_graph.json"

        graph.save_to_file(str(output_file))
        assert output_file.exists()

        # Validate JSON structure
        with open(output_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        assert "nodes" in raw_data
        assert "edges" in raw_data
        assert len(raw_data["nodes"]) == 4
        assert len(raw_data["edges"]) == 3

        # Reload with ContextGraph.load_from_file
        reloaded_graph = ContextGraph(advanced_analytics=False)
        reloaded_graph.load_from_file(str(output_file))

        assert len(reloaded_graph.nodes) == 4
        assert len(reloaded_graph.edges) == 3
        reloaded_nodes = {
            nid: (node.node_type, node.content)
            for nid, node in reloaded_graph.nodes.items()
        }
        assert reloaded_nodes["alice"] == ("Person", "Alice")
        assert reloaded_nodes["bob"] == ("Person", "Bob")
        assert reloaded_nodes["acme"] == ("Organization", "Acme")
        assert reloaded_nodes["new_york"] == ("Location", "New York")

        reloaded_edges = {
            (e.source_id, e.target_id, e.edge_type) for e in reloaded_graph.edges
        }
        assert reloaded_edges == {
            ("alice", "acme", "WORKS_AT"),
            ("bob", "alice", "KNOWS"),
            ("acme", "new_york", "LOCATED_IN"),
        }

    def test_session_loading_and_stats(self, tmp_path: Path):
        graph = _build_deterministic_graph()
        output_file = tmp_path / "explorer_deterministic_graph.json"
        graph.save_to_file(str(output_file))

        session = GraphSession.from_file(str(output_file))
        stats = session.get_stats()

        assert stats["node_count"] == 4
        assert stats["edge_count"] == 3

    def test_explorer_api_endpoints_with_deterministic_graph(self, tmp_path: Path):
        graph = _build_deterministic_graph()
        output_file = tmp_path / "explorer_deterministic_graph.json"
        graph.save_to_file(str(output_file))

        session = GraphSession.from_file(str(output_file))
        app = create_app(session=session)

        with TestClient(app) as client:
            # 1. Health & Info
            health = client.get("/api/health")
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}

            info = client.get("/api/info")
            assert info.status_code == 200
            assert info.json()["status"] == "active"

            # 2. Stats
            stats = client.get("/api/graph/stats")
            assert stats.status_code == 200
            stats_data = stats.json()
            assert stats_data["node_count"] == 4
            assert stats_data["edge_count"] == 3

            # 3. Nodes endpoint
            nodes_res = client.get("/api/graph/nodes")
            assert nodes_res.status_code == 200
            nodes_data = nodes_res.json()
            assert nodes_data["total"] == 4
            assert len(nodes_data["nodes"]) == 4

            returned_nodes = {
                n["id"]: (n["type"], n["content"]) for n in nodes_data["nodes"]
            }
            assert returned_nodes["alice"] == ("Person", "Alice")
            assert returned_nodes["bob"] == ("Person", "Bob")
            assert returned_nodes["acme"] == ("Organization", "Acme")
            assert returned_nodes["new_york"] == ("Location", "New York")

            # 4. Individual node lookups
            for node_id in ["alice", "bob", "acme", "new_york"]:
                node_res = client.get(f"/api/graph/node/{node_id}")
                assert node_res.status_code == 200
                assert node_res.json()["id"] == node_id

            # 5. Edges endpoint
            edges_res = client.get("/api/graph/edges")
            assert edges_res.status_code == 200
            edges_data = edges_res.json()
            assert edges_data["total"] == 3
            assert len(edges_data["edges"]) == 3

            returned_edges = {
                (e["source"], e["target"], e["type"]) for e in edges_data["edges"]
            }
            assert returned_edges == {
                ("alice", "acme", "WORKS_AT"),
                ("bob", "alice", "KNOWS"),
                ("acme", "new_york", "LOCATED_IN"),
            }

    def test_deterministic_graph_auth_enforcement(self, tmp_path: Path, monkeypatch):
        graph = _build_deterministic_graph()
        output_file = tmp_path / "explorer_deterministic_graph.json"
        graph.save_to_file(str(output_file))

        session = GraphSession.from_file(str(output_file))
        app = create_app(session=session)

        with TestClient(app) as client:
            # 1. Unconfigured auth (no SEMANTICA_ALLOW_ANONYMOUS, no SEMANTICA_API_KEY) -> 503
            monkeypatch.delenv("SEMANTICA_ALLOW_ANONYMOUS", raising=False)
            monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)
            unconfigured_res = client.get("/api/graph/stats")
            assert unconfigured_res.status_code == 503

            # 2. Configured SEMANTICA_API_KEY without header -> 401
            test_key = "secret-test-key-1037"
            monkeypatch.setenv("SEMANTICA_API_KEY", test_key)
            unauthorized_res = client.get("/api/graph/nodes")
            assert unauthorized_res.status_code == 401

            # 3. Configured SEMANTICA_API_KEY with valid X-API-Key header -> 200
            authorized_res = client.get(
                "/api/graph/nodes",
                headers={"X-API-Key": test_key},
            )
            assert authorized_res.status_code == 200
            assert authorized_res.json()["total"] == 4

            # 4. Explicit local development opt-in: SEMANTICA_ALLOW_ANONYMOUS=true -> 200 without header
            monkeypatch.setenv("SEMANTICA_ALLOW_ANONYMOUS", "true")
            monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)
            anon_res = client.get("/api/graph/edges")
            assert anon_res.status_code == 200
            assert anon_res.json()["total"] == 3

