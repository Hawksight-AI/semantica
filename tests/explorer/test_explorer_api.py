"""Integration tests for the explorer API."""

import json
from pathlib import Path
import uuid

import networkx as nx
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

    graph.add_node(
        "python",
        node_type="language",
        content="Python programming language",
        popularity="high",
        x=10,
        y=15,
        tags=["lang", "featured"],
    )
    graph.add_node("javascript", node_type="language", content="JavaScript programming language", x=100, y=120)
    graph.add_node("web_dev", node_type="concept", content="Web Development", x=24, y=30)
    graph.add_node("ml", node_type="concept", content="Machine Learning", x=45, y=60)
    graph.add_node(
        "metformin",
        node_type="drug",
        content="Metformin",
        aliases=["Glucophage"],
        confidence="0.97",
        tags=["drug", "featured"],
        x=22,
        y=33,
    )
    graph.add_node(
        "decision_1",
        node_type="decision",
        content="Approve ML framework",
        category="tech",
        scenario="Choosing ML framework",
        outcome="approved",
        confidence="0.9",
        reasoning="Best performance",
        x=60,
        y=80,
    )
    graph.add_node(
        "decision_2",
        node_type="decision",
        content="Reject legacy stack",
        category="tech",
        scenario="Choosing ML framework alternative",
        outcome="rejected",
        confidence="0.4",
        reasoning="Outdated",
        x=64,
        y=86,
    )
    graph.add_node(
        "temporal_node",
        node_type="event",
        content="Conference talk",
        valid_from="2025-01-01T00:00:00",
        valid_until="2025-12-31T23:59:59",
        x=12,
        y=18,
    )

    graph.add_edge("python", "ml", edge_type="used_in", weight=0.9, color="#58a6ff")
    graph.add_edge("javascript", "web_dev", edge_type="used_in", weight=0.8)
    graph.add_edge("python", "web_dev", edge_type="used_in", weight=0.5)
    graph.add_edge("decision_1", "ml", edge_type="about")

    return graph


@pytest.fixture(scope="module")
def client():
    session = GraphSession(_build_sample_graph())
    app = create_app(session=session)
    with TestClient(app) as test_client:
        yield test_client


class TestHealthInfo:
    def test_root_without_frontend_bundle_shows_diagnostic(self, tmp_path, monkeypatch, client):
        from semantica.explorer import app as app_module

        package_dir = tmp_path / "semantica"
        (package_dir / "explorer").mkdir(parents=True)

        class FakeAppPath:
            def __init__(self, *_args, **_kwargs):
                self.path = package_dir / "explorer" / "app.py"

            def resolve(self):
                return self.path.resolve()

        monkeypatch.setattr(app_module, "Path", FakeAppPath)

        response = client.get("/")

        assert response.status_code == 200
        assert "Explorer UI not available" in response.text
        assert "frontend bundle was not found" in response.text
        assert "/docs" in response.text

    def test_root_serves_built_spa_when_bundle_exists(self, tmp_path, monkeypatch):
        from starlette.testclient import TestClient
        from semantica.explorer import app as app_module
        from semantica.explorer.app import create_app

        package_dir = tmp_path / "semantica"
        static_dir = package_dir / "static"
        static_dir.mkdir(parents=True)
        (static_dir / "index.html").write_text(
            '<!doctype html><html><body><div id="root"></div><script src="/assets/app.js"></script></body></html>',
            encoding="utf-8",
        )

        class FakeAppPath:
            def __init__(self, *_args, **_kwargs):
                self.path = package_dir / "explorer" / "app.py"

            def resolve(self):
                return self.path.resolve()

        monkeypatch.setattr(app_module, "Path", FakeAppPath)

        with TestClient(create_app()) as test_client:
            response = test_client.get("/")

        assert response.status_code == 200
        assert '<div id="root"></div>' in response.text
        assert '<script src="/assets/app.js"></script>' in response.text

    def test_health(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_info(self, client):
        response = client.get("/api/info")
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "Semantica Knowledge Explorer"
        assert payload["status"] == "active"
        assert payload["version"]


class TestGraphNodes:
    def test_list_nodes(self, client):
        response = client.get("/api/graph/nodes")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] >= 7
        assert len(payload["nodes"]) <= payload["total"]
        assert payload["has_more"] in {True, False}

    def test_list_nodes_filter_type(self, client):
        response = client.get("/api/graph/nodes?type=language")
        assert response.status_code == 200
        assert all(node["type"] == "language" for node in response.json()["nodes"])

    def test_list_nodes_search(self, client):
        response = client.get("/api/graph/nodes?search=python")
        assert response.status_code == 200
        payload = response.json()
        assert any(node["id"] == "python" for node in payload["nodes"])
        assert all(node["properties"].get("content") for node in payload["nodes"])

    def test_list_nodes_cursor_pagination(self, client):
        first_page = client.get("/api/graph/nodes?limit=2")
        assert first_page.status_code == 200
        first_payload = first_page.json()
        assert len(first_payload["nodes"]) == 2
        assert first_payload["next_cursor"]

        second_page = client.get(f"/api/graph/nodes?limit=2&cursor={first_payload['next_cursor']}")
        assert second_page.status_code == 200
        second_payload = second_page.json()
        first_ids = {node["id"] for node in first_payload["nodes"]}
        second_ids = {node["id"] for node in second_payload["nodes"]}
        assert first_ids.isdisjoint(second_ids)

    def test_list_nodes_bbox_filter(self, client):
        response = client.get("/api/graph/nodes?bbox=0,0,30,40")
        assert response.status_code == 200
        payload = response.json()
        ids = {node["id"] for node in payload["nodes"]}
        assert "python" in ids
        assert "web_dev" in ids
        assert "javascript" not in ids

    def test_get_node(self, client):
        response = client.get("/api/graph/node/python")
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "python"
        assert payload["properties"]["content"] == "Python programming language"

    def test_get_neighbors(self, client):
        response = client.get("/api/graph/node/python/neighbors?depth=2")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) >= 1
        assert any(item["id"] in {"ml", "web_dev"} for item in payload)


class TestGraphEdges:
    def test_list_edges(self, client):
        response = client.get("/api/graph/edges")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] >= 4
        assert all(edge["source"] and edge["target"] and edge["type"] for edge in payload["edges"])

    def test_list_edges_filter_source_target(self, client):
        response = client.get("/api/graph/edges?source=python&target=ml")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["edges"]) == 1
        assert payload["edges"][0]["type"] == "used_in"

    def test_list_edges_cursor_pagination(self, client):
        first_page = client.get("/api/graph/edges?limit=2")
        assert first_page.status_code == 200
        first_payload = first_page.json()
        assert len(first_payload["edges"]) == 2
        assert first_payload["next_cursor"]

        second_page = client.get(f"/api/graph/edges?limit=2&cursor={first_payload['next_cursor']}")
        assert second_page.status_code == 200
        second_payload = second_page.json()
        assert {json.dumps(edge, sort_keys=True) for edge in first_payload["edges"]}.isdisjoint(
            {json.dumps(edge, sort_keys=True) for edge in second_payload["edges"]}
        )

    def test_list_edges_repeated_request_is_stable(self, client):
        first_response = client.get("/api/graph/edges?limit=20")
        second_response = client.get("/api/graph/edges?limit=20")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert first_response.json() == second_response.json()

    def test_list_edges_pagination_union_matches_total(self, client):
        cursor = None
        seen_ids: set[str] = set()
        seen_rows: set[str] = set()
        total = None

        while True:
            url = "/api/graph/edges?limit=2"
            if cursor:
                url = f"{url}&cursor={cursor}"
            response = client.get(url)
            assert response.status_code == 200
            payload = response.json()
            total = payload["total"] if total is None else total

            for edge in payload["edges"]:
                row_key = json.dumps(edge, sort_keys=True)
                assert row_key not in seen_rows
                seen_rows.add(row_key)
                assert edge["id"] not in seen_ids
                seen_ids.add(edge["id"])

            cursor = payload["next_cursor"]
            if not cursor:
                break

        assert total is not None
        assert len(seen_ids) == total


class TestSearchAndStats:
    def test_search(self, client):
        response = client.post(
            "/api/graph/search",
            json={"query": "programming", "filters": {"type": "language"}, "limit": 5},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["query"] == "programming"
        assert payload["total"] >= 1
        assert all(item["node"]["type"] == "language" for item in payload["results"])

    def test_search_exact_and_prefix(self, client):
        exact_response = client.post(
            "/api/graph/search",
            json={"query": "Metformin", "limit": 5},
        )
        assert exact_response.status_code == 200
        exact_payload = exact_response.json()
        assert exact_payload["results"][0]["node"]["id"] == "metformin"

        prefix_response = client.post(
            "/api/graph/search",
            json={"query": "metf", "limit": 5},
        )
        assert prefix_response.status_code == 200
        prefix_payload = prefix_response.json()
        assert any(item["node"]["id"] == "metformin" for item in prefix_payload["results"])

    def test_search_filters_and_cache_stability(self, client):
        body = {
            "query": "framework",
            "filters": {"type": "decision", "min_confidence": 0.8},
            "limit": 5,
        }
        first_response = client.post("/api/graph/search", json=body)
        second_response = client.post("/api/graph/search", json=body)

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert first_response.json() == second_response.json()
        results = first_response.json()["results"]
        assert [item["node"]["id"] for item in results] == ["decision_1"]

    def test_search_sees_new_nodes_after_mutation(self, client):
        session = client.app.state.session
        assert session.add_node(
            "metformin_hcl",
            "drug",
            content="Metformin Hydrochloride",
            aliases=["Glucophage XR"],
            confidence="0.93",
        )

        response = client.post(
            "/api/graph/search",
            json={"query": "glucophage", "limit": 10},
        )
        assert response.status_code == 200
        result_ids = [item["node"]["id"] for item in response.json()["results"]]
        assert "metformin" in result_ids
        assert "metformin_hcl" in result_ids

    def test_search_secondary_scan_fallback_matches_non_curated_properties(self, client):
        session = client.app.state.session
        assert session.add_node(
            "fallback_node",
            "entity",
            content="Alpha",
            description="rareterm",
        )

        response = client.post(
            "/api/graph/search",
            json={"query": "rareterm", "limit": 10},
        )
        assert response.status_code == 200
        result_ids = [item["node"]["id"] for item in response.json()["results"]]
        assert "fallback_node" in result_ids

    def test_stats(self, client):
        response = client.get("/api/graph/stats")
        assert response.status_code == 200
        payload = response.json()
        assert payload["node_count"] >= 7
        assert payload["edge_count"] >= 4
        assert payload["density"] >= 0


class TestDecisions:
    def test_list_decisions(self, client):
        response = client.get("/api/decisions")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) >= 2
        assert all("decision_id" in item for item in payload)

    def test_get_decision(self, client):
        response = client.get("/api/decisions/decision_1")
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision_id"] == "decision_1"
        assert payload["outcome"] == "approved"

    def test_precedents(self, client):
        response = client.get("/api/decisions/decision_1/precedents")
        assert response.status_code == 200
        ids = {item["decision_id"] for item in response.json()}
        assert "decision_2" in ids

    def test_compliance(self, client):
        response = client.get("/api/decisions/decision_1/compliance")
        assert response.status_code == 200
        assert response.json()["compliant"] is True

        client.app.state.session.graph.add_node("policy_1", node_type="policy", content="Data policy")
        client.app.state.session.graph.add_edge("decision_1", "policy_1", edge_type="violates")
        violation_response = client.get("/api/decisions/decision_1/compliance")
        assert violation_response.status_code == 200
        assert violation_response.json()["compliant"] is False


class TestTemporal:
    def test_snapshot_now(self, client):
        response = client.get("/api/temporal/snapshot")
        assert response.status_code == 200
        payload = response.json()
        assert payload["active_node_count"] >= 1
        assert isinstance(payload["active_node_ids"], list)

    def test_snapshot_at(self, client):
        active_response = client.get("/api/temporal/snapshot?at=2025-06-15T00:00:00")
        assert active_response.status_code == 200
        assert "temporal_node" in active_response.json()["active_node_ids"]

        inactive_response = client.get("/api/temporal/snapshot?at=2026-01-01T00:00:00")
        assert inactive_response.status_code == 200
        assert "temporal_node" not in inactive_response.json()["active_node_ids"]

    def test_diff(self, client):
        response = client.get(
            "/api/temporal/diff?from_time=2024-01-01T00:00:00&to_time=2025-06-15T00:00:00"
        )
        assert response.status_code == 200
        payload = response.json()
        assert "temporal_node" in payload["added_nodes"]

    def test_patterns(self, client):
        response = client.get("/api/temporal/patterns")
        assert response.status_code == 200
        assert "patterns" in response.json()

    def test_bounds(self, client):
        response = client.get("/api/temporal/bounds")
        assert response.status_code == 200
        payload = response.json()
        assert "min" in payload
        assert "max" in payload


class TestAnalytics:
    def test_analytics(self, client):
        response = client.get("/api/analytics?metrics=centrality")
        assert response.status_code == 200
        assert "centrality" in response.json()

    def test_validation(self, client):
        response = client.get("/api/analytics/validation")
        assert response.status_code == 200
        payload = response.json()
        assert "valid" in payload
        assert "issues" in payload


class TestEnrichment:
    def test_reasoning(self, client):
        response = client.post(
            "/api/reason",
            json={
                "facts": ["Person(Alice)", "Knows(Alice, Bob)"],
                "rules": ["IF Knows(?x, ?y) THEN Connected(?x, ?y)"],
                "mode": "forward",
            },
        )
        assert response.status_code in (200, 422)

    def test_reasoning_apply_to_graph_fallback(self, client):
        response = client.post(
            "/api/reason",
            json={
                "facts": ["inhibits(Metformin, mTOR)", "causes(mTOR, Neurodegeneration)"],
                "rules": [
                    "IF inhibits(Metformin, mTOR) AND causes(mTOR, Neurodegeneration) THEN candidate(Metformin, Alzheimer's)"
                ],
                "mode": "forward",
                "apply_to_graph": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert "candidate(Metformin, Alzheimer's)" in payload["inferred_facts"]
        assert payload["added_edges"] >= 1

        edge_lookup = client.get("/api/graph/edges?source=Metformin&target=Alzheimer%27s")
        assert edge_lookup.status_code == 200
        assert edge_lookup.json()["edges"][0]["properties"]["inferred"] is True

    def test_extract(self, client):
        response = client.post("/api/enrich/extract", json={"text": "Alice works at Acme Corp."})
        assert response.status_code in (200, 422, 503)

    def test_link_prediction(self, client):
        response = client.post("/api/enrich/links", json={"node_id": "python", "top_n": 5})
        assert response.status_code in (200, 422)

    def test_dedup(self, client):
        response = client.post("/api/enrich/dedup", json={"threshold": 0.8})
        assert response.status_code in (200, 422)


class TestAnnotations:
    def test_create_list_delete(self, client):
        created = client.post(
            "/api/annotations",
            json={"node_id": "python", "content": "Great language!", "tags": ["fav"]},
        )
        assert created.status_code == 201
        annotation = created.json()
        annotation_id = annotation["annotation_id"]

        listed = client.get("/api/annotations?node_id=python")
        assert listed.status_code == 200
        assert any(item["annotation_id"] == annotation_id for item in listed.json())

        deleted = client.delete(f"/api/annotations/{annotation_id}")
        assert deleted.status_code == 204


class TestImportExport:
    def test_export_json(self, client):
        response = client.post("/api/export", json={"format": "json"})
        assert response.status_code == 200
        payload = response.json()
        assert "entities" in payload
        assert "relationships" in payload

    def test_export_csv(self, client):
        response = client.post("/api/export", json={"format": "csv"})
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"].lower()

    def test_import_json_with_edge_metadata(self, client):
        payload = json.dumps(
            {
                "nodes": [
                    {"id": "meta_src", "type": "test", "properties": {"content": "src"}},
                    {"id": "meta_tgt", "type": "test", "properties": {"content": "tgt"}},
                ],
                "edges": [
                {
                    "id": "meta-edge-1",
                    "familyId": "meta-family",
                    "source": "meta_src",
                    "target": "meta_tgt",
                    "type": "tagged",
                    "metadata": {"label": "important", "weight": 0.7},
                }
                ],
            }
        )
        response = client.post(
            "/api/import",
            files={"file": ("graph.json", payload, "application/json")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["nodes_added"] == body["nodes_imported"]
        assert body["edges_added"] == body["edges_imported"]

        edge_lookup = client.get("/api/graph/edges?source=meta_src&target=meta_tgt")
        assert edge_lookup.status_code == 200
        edge_payload = edge_lookup.json()["edges"][0]
        props = edge_payload["properties"]
        assert edge_payload["id"] == "meta-edge-1"
        assert edge_payload["familyId"] == "meta-family"
        assert props["label"] == "important"

    def test_import_csv(self, client):
        payload = "id,type,content\nnode_csv,entity,Hello CSV\n"
        response = client.post(
            "/api/import",
            files={"file": ("graph.csv", payload, "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["nodes_added"] >= 1

    def test_provenance_report_json(self, client):
        response = client.get("/api/provenance/report?node_id=python&format=json")
        assert response.status_code == 200
        payload = response.json()
        assert payload["node_id"] == "python"
        assert "lineage" in payload

    def test_provenance_report_markdown(self, client):
        response = client.get("/api/provenance/report?node_id=python&format=markdown")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"].lower()
        assert "Provenance Report" in response.text


class TestRealtimeUpdates:
    def test_websocket_receives_graph_mutation(self, client):
        with client.websocket_connect("/ws/graph-updates") as websocket:
            ack = websocket.receive_json()
            assert ack["event"] == "connection_ack"
            client.app.state.session.graph.add_node("ws_node", node_type="entity", content="WebSocket Node")
            event = websocket.receive_json()
            assert event["event"] == "graph_mutation"
            assert event["data"]["event_type"] == "ADD_NODE"
            assert event["data"]["entity_id"] == "ws_node"


class TestGenericGraphFileLoading:
    @staticmethod
    def _write_graph_payload(payload):
        tmp_dir = Path("tests") / "explorer" / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        graph_path = tmp_dir / f"{uuid.uuid4().hex}.json"
        graph_path.write_text(json.dumps(payload), encoding="utf-8")
        return graph_path

    def test_file_loader_accepts_label_and_source_target_shape(self):
        payload = {
            "metadata": {"dataset": "demo"},
            "nodes": [
                {"id": "drug::metformin", "type": "drug", "label": "Metformin", "properties": {"source": "PrimeKG"}},
                {"id": "gene::mtor", "type": "gene", "label": "mTOR", "properties": {"source": "NCBI"}},
            ],
            "edges": [
                {
                    "id": "drug::metformin::inhibits::gene::mtor",
                    "source": "drug::metformin",
                    "target": "gene::mtor",
                    "type": "inhibits",
                    "label": "inhibits",
                    "properties": {"confidence": 0.92},
                }
            ],
        }
        graph_path = self._write_graph_payload(payload)

        session = GraphSession.from_file(str(graph_path))
        assert None not in session.graph.nodes

        metformin = session.get_node("drug::metformin")
        assert metformin is not None
        assert metformin["content"] == "Metformin"

        edges, total = session.get_edges(limit=10)
        assert total == 1
        assert edges[0]["source"] == "drug::metformin"
        assert edges[0]["target"] == "gene::mtor"

    def test_generic_file_loading_keeps_temporal_endpoints_stable(self):
        payload = {
            "nodes": [
                {
                    "id": "drug::metformin",
                    "type": "drug",
                    "label": "Metformin",
                    "properties": {
                        "valid_from": "2020-01-01T00:00:00",
                        "valid_until": "2024-12-31T23:59:59",
                    },
                },
                {"id": "disease::alz", "type": "disease", "label": "Alzheimer disease"},
            ],
            "edges": [
                {"source": "drug::metformin", "target": "disease::alz", "type": "candidate"},
                {"target": "disease::alz", "type": "broken_edge_should_be_ignored"},
            ],
        }
        graph_path = self._write_graph_payload(payload)

        session = GraphSession.from_file(str(graph_path))
        app = create_app(session=session)
        with TestClient(app) as test_client:
            bounds = test_client.get("/api/temporal/bounds")
            assert bounds.status_code == 200
            assert bounds.json()["min"] == "2020-01-01T00:00:00"

            edges = test_client.get("/api/graph/edges?limit=10")
            assert edges.status_code == 200
            payload = edges.json()
            assert payload["total"] == 1
            assert payload["edges"][0]["type"] == "candidate"

    def test_generic_file_loading_assigns_stable_legacy_edge_ids(self):
        payload = {
            "nodes": [
                {"id": "legacy_src", "type": "entity", "properties": {"content": "Legacy source"}},
                {"id": "legacy_tgt", "type": "entity", "properties": {"content": "Legacy target"}},
            ],
            "edges": [
                {
                    "source": "legacy_src",
                    "target": "legacy_tgt",
                    "type": "related_to",
                    "weight": 0.75,
                    "metadata": {"evidence": "legacy"},
                }
            ],
        }
        graph_path = self._write_graph_payload(payload)

        session_one = GraphSession.from_file(str(graph_path))
        session_two = GraphSession.from_file(str(graph_path))

        edges_one, total_one = session_one.get_edges(limit=10)
        edges_two, total_two = session_two.get_edges(limit=10)

        assert total_one == 1
        assert total_two == 1
        assert edges_one[0]["id"] == edges_two[0]["id"]
        assert edges_one[0]["familyId"] == edges_two[0]["familyId"]

    def test_multi_edges_same_pair_paginate_as_distinct_stable_edges(self):
        graph = ContextGraph(advanced_analytics=False)
        graph.add_node("shared_src", node_type="entity", content="Shared source")
        graph.add_node("shared_tgt", node_type="entity", content="Shared target")
        graph.add_edges(
            [
                {
                    "id": "edge-alpha",
                    "familyId": "family-shared",
                    "source_id": "shared_src",
                    "target_id": "shared_tgt",
                    "type": "supports",
                    "weight": 0.9,
                    "properties": {"provenance": "paper-a"},
                },
                {
                    "id": "edge-beta",
                    "familyId": "family-shared",
                    "source_id": "shared_src",
                    "target_id": "shared_tgt",
                    "type": "contradicts",
                    "weight": 0.6,
                    "properties": {"provenance": "paper-b"},
                },
            ]
        )

        app = create_app(session=GraphSession(graph))
        with TestClient(app) as test_client:
            first = test_client.get("/api/graph/edges?source=shared_src&target=shared_tgt&limit=1")
            assert first.status_code == 200
            first_payload = first.json()
            assert first_payload["total"] == 2
            assert len(first_payload["edges"]) == 1
            assert first_payload["edges"][0]["familyId"] == "family-shared"

            second = test_client.get(
                f"/api/graph/edges?source=shared_src&target=shared_tgt&limit=1&cursor={first_payload['next_cursor']}"
            )
            assert second.status_code == 200
            second_payload = second.json()
            assert len(second_payload["edges"]) == 1
            assert first_payload["edges"][0]["id"] != second_payload["edges"][0]["id"]

            repeat = test_client.get("/api/graph/edges?source=shared_src&target=shared_tgt&limit=10")
            assert repeat.status_code == 200
            repeat_ids = [edge["id"] for edge in repeat.json()["edges"]]
            assert repeat_ids == ["edge-alpha", "edge-beta"]


# ---------------------------------------------------------------------------
# Bidirectional path-finding tests (issue #469)
# ---------------------------------------------------------------------------

def _make_path_session() -> GraphSession:
    """Return a GraphSession whose build_graph_dict yields an nx.DiGraph with A→B only.

    GraphSession wraps a ContextGraph (required by create_app), but we patch
    build_graph_dict so PathFinder receives an actual NetworkX DiGraph — the
    graph type the Explorer is designed to traverse for path queries.
    """
    cg = ContextGraph(advanced_analytics=False)
    cg.add_node("A", node_type="entity", content="Node A")
    cg.add_node("B", node_type="entity", content="Node B")
    cg.add_node("gene/protein:6164", node_type="gene/protein", content="RPL34")
    cg.add_node("disease/term:1", node_type="disease", content="Slash target")
    cg.add_edge("A", "B", edge_type="connects")
    cg.add_edge("gene/protein:6164", "disease/term:1", edge_type="connects")

    session = GraphSession(cg)

    # Patch build_graph_dict to return the directed NetworkX graph that
    # PathFinder needs.  The ContextGraph dict format is not traversable by
    # PathFinder; this mimics how a KG-backed session would expose the graph.
    digraph = nx.DiGraph()
    digraph.add_edge("A", "B")
    digraph.add_edge("gene/protein:6164", "disease/term:1")
    session.build_graph_dict = lambda node_ids=None: digraph  # type: ignore[method-assign]

    return session


@pytest.fixture
def path_client():
    session = _make_path_session()
    app = create_app(session=session)
    with TestClient(app) as c:
        yield c


class TestBidirectionalPathRoute:
    """API-level tests for directed=true/false on GET /api/graph/node/{id}/path."""

    # ------------------------------------------------------------------
    # directed=true (default) — existing directed-only behaviour
    # ------------------------------------------------------------------

    def test_directed_true_forward_path_found(self, path_client):
        """A→B exists: forward query with directed=true must succeed."""
        resp = path_client.get("/api/graph/node/A/path?target=B&directed=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == ["A", "B"]
        assert body["directed"] is True

    def test_directed_true_reverse_returns_404(self, path_client):
        """Only A→B exists: reverse query with directed=true must return 404."""
        resp = path_client.get("/api/graph/node/B/path?target=A&directed=true")
        assert resp.status_code == 404

    def test_default_param_reverse_returns_404(self, path_client):
        """Omitting directed= must preserve current directed behaviour (404 for reverse)."""
        resp = path_client.get("/api/graph/node/B/path?target=A")
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # directed=false — new undirected traversal
    # ------------------------------------------------------------------

    def test_directed_false_reverse_path_found(self, path_client):
        """directed=false must find B→A even though only A→B exists."""
        resp = path_client.get("/api/graph/node/B/path?target=A&directed=false")
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == ["B", "A"]
        assert body["directed"] is False

    def test_query_path_route_supports_slash_node_ids(self, path_client):
        """Query-param path route must support arbitrary graph ids with slashes."""
        resp = path_client.get(
            "/api/graph/path",
            params={
                "source": "gene/protein:6164",
                "target": "disease/term:1",
                "algorithm": "dijkstra",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == ["gene/protein:6164", "disease/term:1"]
        assert body["source"] == "gene/protein:6164"
        assert body["target"] == "disease/term:1"

    def test_directed_false_forward_path_found(self, path_client):
        """directed=false must not break the natural A→B direction."""
        resp = path_client.get("/api/graph/node/A/path?target=B&directed=false")
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == ["A", "B"]
        assert body["directed"] is False

    # ------------------------------------------------------------------
    # Algorithm variants
    # ------------------------------------------------------------------

    def test_dijkstra_directed_false_reverse(self, path_client):
        resp = path_client.get(
            "/api/graph/node/B/path?target=A&algorithm=dijkstra&directed=false"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == ["B", "A"]
        assert body["algorithm"] == "dijkstra"
        assert body["directed"] is False

    def test_dijkstra_directed_true_reverse_returns_404(self, path_client):
        resp = path_client.get(
            "/api/graph/node/B/path?target=A&algorithm=dijkstra&directed=true"
        )
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # PathResponse schema
    # ------------------------------------------------------------------

    def test_response_schema_includes_directed_field(self, path_client):
        """PathResponse must always include the directed field."""
        resp = path_client.get("/api/graph/node/A/path?target=B")
        assert resp.status_code == 200
        body = resp.json()
        assert "directed" in body

    def test_response_directed_reflects_query_param(self, path_client):
        resp_true = path_client.get("/api/graph/node/A/path?target=B&directed=true")
        resp_false = path_client.get("/api/graph/node/A/path?target=B&directed=false")
        assert resp_true.json()["directed"] is True
        assert resp_false.json()["directed"] is False

    # ------------------------------------------------------------------
    # hop_count and distance_band — issue #472
    # ------------------------------------------------------------------

    def test_response_includes_hop_count_and_distance_band(self, path_client):
        """PathResponse must include hop_count and distance_band fields."""
        resp = path_client.get("/api/graph/node/A/path?target=B")
        assert resp.status_code == 200
        body = resp.json()
        assert "hop_count" in body
        assert "distance_band" in body

    def test_one_hop_path_is_direct(self, path_client):
        """A single-edge path (1 hop) must return distance_band='direct'."""
        resp = path_client.get("/api/graph/node/A/path?target=B")
        assert resp.status_code == 200
        body = resp.json()
        assert body["hop_count"] == 1
        assert body["distance_band"] == "direct"


# ---------------------------------------------------------------------------
# _classify_distance unit tests — issue #472
# ---------------------------------------------------------------------------

from semantica.utils.helpers import classify_path_distance


class _FakeSimilarity:
    """Minimal similarity stub shared by slash-safe distance route tests.

    Expects embeddings keyed on 'gene/protein:6164' with query vector [1, 0, 0]
    and returns a single neighbor result.  Tests that need different behaviour
    can assign a lambda to instance.find_most_similar after construction.
    """

    def find_most_similar(self, embeddings, query_embedding, top_k=10):
        assert "gene/protein:6164" in embeddings
        assert query_embedding == [1.0, 0.0, 0.0]
        return [("disease/term:1", 0.74)]


def _make_slash_node_session(*, with_embeddings: bool = True) -> GraphSession:
    """Return an isolated GraphSession with slash-containing node IDs."""
    graph = ContextGraph(advanced_analytics=False)
    kwargs = {"embedding": [1.0, 0.0, 0.0]} if with_embeddings else {}
    graph.add_node("gene/protein:6164", node_type="gene/protein", content="RPL34", **kwargs)
    graph.add_node(
        "disease/term:1",
        node_type="disease",
        content="Slash target",
        **({"embedding": [0.7, 0.2, 0.1]} if with_embeddings else {}),
    )
    session = GraphSession(graph)
    session._similarity = _FakeSimilarity()
    return session


class TestSlashSafeDistanceRoutes:
    def test_query_semantic_neighborhood_supports_slash_node_ids(self):
        session = _make_slash_node_session(with_embeddings=True)
        app = create_app(session=session)
        with TestClient(app) as test_client:
            resp = test_client.get(
                "/api/graph/semantic-neighborhood",
                params={"node_id": "gene/protein:6164", "top_k": 50},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["anchor_node"] == "gene/protein:6164"
        assert body["neighbors"][0]["id"] == "disease/term:1"
        assert body["neighbors"][0]["similarity"] == 0.74

    def test_legacy_semantic_neighborhood_still_works_for_simple_ids(self):
        """Legacy path-segment route must still return 200 for slash-free node IDs."""
        graph = ContextGraph(advanced_analytics=False)
        graph.add_node(
            "semantic_anchor",
            node_type="entity",
            content="Semantic anchor",
            embedding=[1.0, 0.0, 0.0],
        )
        graph.add_node(
            "semantic_neighbor",
            node_type="entity",
            content="Semantic neighbor",
            embedding=[0.8, 0.2, 0.0],
        )
        session = GraphSession(graph)
        fake = _FakeSimilarity()
        fake.find_most_similar = (
            lambda embeddings, query_embedding, top_k=10: [("semantic_neighbor", 0.8)]
        )
        session._similarity = fake
        app = create_app(session=session)
        with TestClient(app) as test_client:
            resp = test_client.get(
                "/api/graph/node/semantic_anchor/semantic-neighborhood?top_k=10"
            )

        assert resp.status_code == 200
        assert resp.json()["anchor_node"] == "semantic_anchor"

    def test_query_semantic_neighborhood_missing_node_returns_404(self, client):
        resp = client.get(
            "/api/graph/semantic-neighborhood",
            params={"node_id": "gene/protein:missing"},
        )
        assert resp.status_code == 404

    def test_query_semantic_neighborhood_without_embeddings_returns_503(self):
        session = _make_slash_node_session(with_embeddings=False)
        app = create_app(session=session)
        with TestClient(app) as test_client:
            resp = test_client.get(
                "/api/graph/semantic-neighborhood",
                params={"node_id": "gene/protein:6164", "top_k": 50},
            )

        assert resp.status_code == 503


class TestClassifyDistance:
    """Unit tests covering all four band boundaries."""

    def test_zero_hops_is_direct(self):
        assert classify_path_distance(0) == "direct"

    def test_one_hop_is_direct(self):
        assert classify_path_distance(1) == "direct"

    def test_two_hops_is_near(self):
        assert classify_path_distance(2) == "near"

    def test_three_hops_is_near(self):
        assert classify_path_distance(3) == "near"

    def test_four_hops_is_mid_range(self):
        assert classify_path_distance(4) == "mid-range"

    def test_six_hops_is_mid_range(self):
        assert classify_path_distance(6) == "mid-range"

    def test_seven_hops_is_distant(self):
        assert classify_path_distance(7) == "distant"

    def test_large_hop_count_is_distant(self):
        assert classify_path_distance(20) == "distant"
