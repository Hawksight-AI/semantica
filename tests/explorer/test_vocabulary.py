"""Tests for vocabulary explorer routes."""

from unittest.mock import MagicMock

import pytest

# fastapi ships in the optional `explorer` extra, not in `dev`, so this module
# must skip rather than fail collection when it is absent. The guard has to sit
# above the import below, which pulls fastapi in transitively.
pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from semantica.explorer.dependencies import get_session  # noqa: E402
from semantica.explorer.routes.vocabulary import router  # noqa: E402
from semantica.utils.skos import validate_skos_hierarchy  # noqa: E402

app = FastAPI()
app.include_router(router)
mock_session = MagicMock()
app.dependency_overrides[get_session] = lambda: mock_session
client = TestClient(app)


MINIMAL_TTL = b"""
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex:   <http://example.org/> .
ex:S a skos:ConceptScheme ; skos:prefLabel \"Scheme\" .
ex:A a skos:Concept ; skos:prefLabel \"Alpha\" ; skos:inScheme ex:S .
"""


MINIMAL_RDF_XML = b"""<?xml version=\"1.0\"?>
<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\"
         xmlns:skos=\"http://www.w3.org/2004/02/skos/core#\"
         xmlns:ex=\"http://example.org/\">
  <skos:ConceptScheme rdf:about=\"http://example.org/SX\">
    <skos:prefLabel xml:lang=\"en\">Scheme X</skos:prefLabel>
  </skos:ConceptScheme>
</rdf:RDF>
"""


CYCLIC_TTL = b"""
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex:   <http://example.org/> .
ex:S a skos:ConceptScheme ; skos:prefLabel \"Scheme\" .
ex:A a skos:Concept ; skos:prefLabel \"Alpha\" ; skos:inScheme ex:S ; skos:broader ex:B .
ex:B a skos:Concept ; skos:prefLabel \"Beta\" ; skos:inScheme ex:S ; skos:broader ex:A .
"""


def setup_function():
    mock_session.reset_mock()


def test_list_schemes_returns_correct_shape():
    mock_session.get_nodes.return_value = ([
        {
            "id": "http://example.org/Scheme1",
            "type": "skos:ConceptScheme",
            "properties": {"content": "My Test Scheme", "description": "A scheme for testing"},
        }
    ], 1)

    response = client.get("/api/vocabulary/schemes")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["uri"] == "http://example.org/Scheme1"
    assert payload[0]["label"] == "My Test Scheme"
    assert payload[0]["description"] == "A scheme for testing"


def test_list_concepts_returns_flat_membership_list():
    mock_session.get_nodes.return_value = ([
        {"id": "http://example.org/A", "type": "skos:Concept", "properties": {"content": "Alpha", "alt_labels": ["A"]}},
        {"id": "http://example.org/B", "type": "skos:Concept", "properties": {"content": "Beta"}},
    ], 2)
    mock_session.get_edges.return_value = ([
        {"source": "http://example.org/A", "target": "http://example.org/S", "type": "skos:inScheme"},
        {"source": "http://example.org/B", "target": "http://example.org/S", "type": "skos:inScheme"},
        {"source": "http://example.org/B", "target": "http://example.org/A", "type": "skos:broader"},
    ], 3)

    response = client.get("/api/vocabulary/concepts?scheme=http://example.org/S")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    alpha = next(item for item in payload if item["uri"] == "http://example.org/A")
    beta = next(item for item in payload if item["uri"] == "http://example.org/B")
    assert alpha["parent_uri"] is None
    assert beta["parent_uri"] == "http://example.org/A"
    assert alpha["alt_labels"] == ["A"]


def test_hierarchy_parent_child_via_broader():
    mock_session.get_nodes.return_value = ([
        {"id": "http://example.org/Parent", "type": "skos:Concept", "properties": {"content": "Parent Node"}},
        {"id": "http://example.org/Child", "type": "skos:Concept", "properties": {"content": "Child Node"}},
    ], 2)
    mock_session.get_edges.return_value = ([
        {"source": "http://example.org/Parent", "target": "http://example.org/Scheme1", "type": "skos:inScheme"},
        {"source": "http://example.org/Child", "target": "http://example.org/Scheme1", "type": "skos:inScheme"},
        {"source": "http://example.org/Child", "target": "http://example.org/Parent", "type": "skos:broader"},
    ], 3)

    response = client.get("/api/vocabulary/hierarchy?scheme=http://example.org/Scheme1")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["uri"] == "http://example.org/Parent"
    assert payload[0]["children"][0]["uri"] == "http://example.org/Child"


def test_hierarchy_cycle_does_not_hang():
    mock_session.get_nodes.return_value = ([
        {"id": "http://example.org/A", "type": "skos:Concept", "properties": {"content": "A"}},
        {"id": "http://example.org/B", "type": "skos:Concept", "properties": {"content": "B"}},
    ], 2)
    mock_session.get_edges.return_value = ([
        {"source": "http://example.org/A", "target": "http://example.org/S", "type": "skos:inScheme"},
        {"source": "http://example.org/B", "target": "http://example.org/S", "type": "skos:inScheme"},
        {"source": "http://example.org/A", "target": "http://example.org/B", "type": "skos:broader"},
        {"source": "http://example.org/B", "target": "http://example.org/A", "type": "skos:broader"},
    ], 4)

    response = client.get("/api/vocabulary/hierarchy?scheme=http://example.org/S")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_import_ttl_success():
    mock_session.add_nodes_and_edges.return_value = (2, 1)

    response = client.post(
        "/api/vocabulary/import",
        files={"file": ("vocab.ttl", MINIMAL_TTL, "text/turtle")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["format"] == "turtle"
    assert payload["nodes_added"] == 2


def test_import_raw_text_success():
    mock_session.add_nodes_and_edges.return_value = (1, 0)

    response = client.post(
        "/api/vocabulary/import",
        data={"text": MINIMAL_TTL.decode("utf-8"), "format": "turtle"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_import_rdf_xml_success():
    mock_session.add_nodes_and_edges.return_value = (1, 0)

    response = client.post(
        "/api/vocabulary/import",
        files={"file": ("vocab.rdf", MINIMAL_RDF_XML, "application/rdf+xml")},
    )
    assert response.status_code == 200
    assert response.json()["format"] == "xml"


def test_import_invalid_file_returns_422():
    response = client.post(
        "/api/vocabulary/import",
        files={"file": ("bad.ttl", b"this is not valid RDF!", "text/turtle")},
    )
    assert response.status_code == 422


def test_import_rejects_cyclic_hierarchy_before_writing_nodes():
    def add_nodes_and_edges(nodes, edges):
        validate_skos_hierarchy(edges)
        return 0, 0

    mock_session.add_nodes_and_edges.side_effect = add_nodes_and_edges

    response = client.post(
        "/api/vocabulary/import",
        files={"file": ("cyclic.ttl", CYCLIC_TTL, "text/turtle")},
    )

    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()
    mock_session.add_nodes_and_edges.assert_called_once()
