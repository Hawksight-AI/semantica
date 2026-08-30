"""
Tests for ProvenanceManager wiring into Explorer routes and application startup.
"""

from unittest.mock import patch

import pytest
# fastapi ships in the optional `explorer` extra, not in `dev`, so this module
# must skip rather than fail collection when it is absent. The guard has to sit
# above the starlette/explorer imports below, which need that extra.
pytest.importorskip("fastapi")

from starlette.testclient import TestClient  # noqa: E402

from semantica.context.context_graph import ContextGraph  # noqa: E402
from semantica.explorer.app import create_app  # noqa: E402
from semantica.explorer.session import GraphSession  # noqa: E402
from semantica.provenance import ProvenanceManager  # noqa: E402
from semantica.provenance.storage import SQLiteStorage  # noqa: E402


@pytest.fixture
def session():
    sess = GraphSession(ContextGraph(advanced_analytics=False))
    return sess


@pytest.fixture
def client(session):
    app = create_app(session=session)
    with TestClient(app) as tc:
        yield tc


def test_provenance_manager_wiring_audit_path(client, session):
    """Test that a multi-hop track_entity chain is returned from /api/provenance with source='audit'."""
    pm = session.provenance_manager
    pm.track_entity(entity_id="grandparent", source="doc_1", entity_type="document")
    pm.track_entity(
        entity_id="parent",
        source="doc_1",
        metadata={"derived_from": "grandparent"},
        entity_type="chunk",
    )
    pm.track_entity(
        entity_id="child",
        source="doc_1",
        metadata={"derived_from": "parent"},
        entity_type="named_entity",
    )

    response = client.get("/api/provenance", params={"node_id": "child"})
    assert response.status_code == 200
    data = response.json()

    assert data.get("source") == "audit"
    node_ids = {n["id"] for n in data["nodes"]}
    assert {"grandparent", "parent", "child"}.issubset(node_ids)
    edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
    assert ("grandparent", "parent") in edge_pairs
    assert ("parent", "child") in edge_pairs
    assert all(e["direction"] == "upstream" for e in data["edges"])

    # Confirm /api/provenance/report also uses audit path
    rep_response = client.get("/api/provenance/report", params={"node_id": "child"})
    assert rep_response.status_code == 200
    report_data = rep_response.json()
    assert report_data.get("source") == "audit"
    assert report_data["lineage"].get("source") == "audit"

    # Confirm markdown export classifies multi-hop ancestor edges under Upstream, not Lateral
    md_response = client.get(
        "/api/provenance/report", params={"node_id": "child", "format": "markdown"}
    )
    assert md_response.status_code == 200
    md_text = md_response.text
    assert "## Upstream" in md_text
    assert "grandparent" in md_text and "parent" in md_text
    assert "## Lateral" not in md_text


def test_provenance_manager_wiring_fallback_no_records(client, session):
    """Test that a node with no audit records falls back cleanly to source='graph_traversal'."""
    session.add_node("orphan_node", content="Orphan Node Content", node_type="entity")

    response = client.get("/api/provenance", params={"node_id": "orphan_node"})
    assert response.status_code == 200
    data = response.json()

    assert data.get("source") == "graph_traversal"
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "orphan_node"


def test_provenance_manager_wiring_error_graceful_degradation(client, session):
    """Test that a simulated ProvenanceManager error degrades gracefully to naive traversal (200, not 500)."""
    session.add_node("some_node", content="Some Node", node_type="entity")

    with patch.object(
        session.provenance_manager,
        "get_lineage",
        side_effect=RuntimeError("Simulated storage failure"),
    ):
        response = client.get("/api/provenance", params={"node_id": "some_node"})
        assert response.status_code == 200
        data = response.json()
        assert data.get("source") == "graph_traversal"
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "some_node"


def test_create_app_provenance_storage_path_wiring(tmp_path):
    """Test that create_app(provenance_storage_path=...) sets per-instance storage without global mutation."""
    test_path = str(tmp_path / "test_explorer_prov.db")
    app = create_app(provenance_storage_path=test_path)

    with TestClient(app):
        assert app.state.session._provenance_storage_path == test_path
        assert isinstance(app.state.session.provenance_manager.storage, SQLiteStorage)


def test_provenance_storage_isolation_between_sessions(tmp_path):
    """Test that two GraphSessions with different storage paths do not leak state across instances."""
    path1 = str(tmp_path / "session1.db")
    path2 = str(tmp_path / "session2.db")
    sess1 = GraphSession(ContextGraph(advanced_analytics=False), provenance_storage_path=path1)
    sess2 = GraphSession(ContextGraph(advanced_analytics=False), provenance_storage_path=path2)

    pm1 = sess1.provenance_manager
    pm2 = sess2.provenance_manager

    assert pm1.storage.db_path == path1
    assert pm2.storage.db_path == path2
    assert pm1 is not pm2
    assert pm1.storage is not pm2.storage

    # Write an entity to sess1 and confirm it does NOT appear in sess2
    pm1.track_entity(entity_id="node_in_1", source="doc_A", entity_type="entity")
    assert pm1.storage.retrieve("node_in_1") is not None
    assert pm2.storage.retrieve("node_in_1") is None


def test_create_app_rejects_conflicting_provenance_storage_path(tmp_path):
    """Test that create_app raises ValueError when given a session with a conflicting preconfigured path."""
    path1 = str(tmp_path / "orig.db")
    path2 = str(tmp_path / "conflict.db")
    sess = GraphSession(ContextGraph(advanced_analytics=False), provenance_storage_path=path1)
    with pytest.raises(ValueError, match="Conflicting provenance_storage_path"):
        create_app(session=sess, provenance_storage_path=path2)


def test_create_app_rejects_path_when_manager_already_initialized(tmp_path):
    """Test that create_app raises ValueError when given a session whose manager was already constructed."""
    sess = GraphSession(ContextGraph(advanced_analytics=False))
    _ = sess.provenance_manager  # construct and cache
    with pytest.raises(ValueError, match="provenance_manager is already initialized"):
        create_app(session=sess, provenance_storage_path=str(tmp_path / "late.db"))


def test_create_app_allows_matching_provenance_storage_path(tmp_path):
    """Test that create_app succeeds when the supplied path matches the session's existing path."""
    path1 = str(tmp_path / "same.db")
    sess = GraphSession(ContextGraph(advanced_analytics=False), provenance_storage_path=path1)
    app = create_app(session=sess, provenance_storage_path=path1)
    with TestClient(app):
        assert app.state.session._provenance_storage_path == path1


def test_provenance_manager_wiring_checksum_failure_falls_back(client, session):
    """Test that if any lineage entry fails checksum verification, Explorer falls back to graph traversal."""
    pm = session.provenance_manager
    entry = pm.track_entity(entity_id="tampered_node", source="doc_1", entity_type="entity")
    # Simulate tampering by altering confidence in storage without updating checksum
    entry.confidence = 0.1
    pm.storage.store(entry)

    session.add_node("tampered_node", content="Tampered Node", node_type="entity")

    response = client.get("/api/provenance", params={"node_id": "tampered_node"})
    assert response.status_code == 200
    data = response.json()
    assert data.get("source") == "graph_traversal"
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "tampered_node"


def test_provenance_audit_evidence_fields_preserved(client, session):
    """Test that audit evidence fields (source_document, confidence, checksum) are preserved in JSON and markdown."""
    pm = session.provenance_manager
    pm.track_entity(entity_id="ev_node", source="DOI:10.1234/test", entity_type="entity", metadata={"label": "Evidence Node"})

    response = client.get("/api/provenance", params={"node_id": "ev_node"})
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "audit"
    assert len(data["nodes"]) == 1
    node = data["nodes"][0]
    assert node["source_document"] == "DOI:10.1234/test"
    assert node["confidence"] == 1.0
    assert node["checksum"] is not None

    rep_json = client.get("/api/provenance/report", params={"node_id": "ev_node", "format": "json"}).json()
    assert rep_json["lineage"]["nodes"][0]["source_document"] == "DOI:10.1234/test"

    rep_md = client.get("/api/provenance/report", params={"node_id": "ev_node", "format": "markdown"}).text
    assert "[source: DOI:10.1234/test]" in rep_md
    assert "(confidence: 1.0)" in rep_md
