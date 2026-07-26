"""Tests for Ontology Hub subissue 3 APIs."""

from unittest.mock import patch

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


def _build_ontology_graph() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    onto_a = "http://example.org/onto-a"
    onto_b = "http://example.org/onto-b"
    person_a = "http://example.org/onto-a#Person"
    person_b = "http://example.org/onto-b#PersonRecord"
    name_a = "http://example.org/onto-a#name"

    graph.add_node(
        onto_a,
        node_type="owl:Ontology",
        content="Ontology A",
        **{"rdfs:label": "Ontology A", "rdfs:comment": "Primary ontology", "version": "1.0.0"},
    )
    graph.add_node(
        onto_b,
        node_type="owl:Ontology",
        content="Ontology B",
        **{"rdfs:label": "Ontology B", "rdfs:comment": "Partner ontology", "version": "1.0.0"},
    )
    graph.add_node(
        person_a,
        node_type="owl:Class",
        content="Person",
        scheme_uri=onto_a,
        **{"rdfs:label": "Person", "rdfs:comment": "A person", "skos:definition": "Human actor"},
    )
    graph.add_node(
        name_a,
        node_type="owl:DatatypeProperty",
        content="name",
        scheme_uri=onto_a,
        **{"rdfs:label": "name", "rdfs:comment": "Display name"},
    )
    graph.add_node(
        person_b,
        node_type="owl:Class",
        content="Person Record",
        scheme_uri=onto_b,
        **{"rdfs:label": "Person Record", "rdfs:comment": "A person profile"},
    )
    graph.add_edge(name_a, person_a, edge_type="rdfs:domain")
    return graph


@pytest.fixture()
def client():
    app = create_app(session=GraphSession(_build_ontology_graph()))
    with TestClient(app) as test_client:
        yield test_client


def test_alignment_round_trip(client):
    payload = {
        "source_uri": "http://example.org/onto-a#Person",
        "target_uri": "http://example.org/onto-b#PersonRecord",
        "relation": "owl:equivalentClass",
        "confidence": 0.91,
        "provenance": "Reviewed from source mapping table",
        "source": "test",
        "reviewer": "qa",
    }
    created = client.post("/api/ontology/alignments", json=payload)
    assert created.status_code == 200
    alignment = created.json()
    assert alignment["confidence"] == 0.91
    assert alignment["provenance"] == "Reviewed from source mapping table"

    listed = client.get("/api/ontology/alignments")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [alignment["id"]]

    removed = client.delete(f"/api/ontology/alignments?id={alignment['id']}")
    assert removed.status_code == 200
    assert client.get("/api/ontology/alignments").json() == []


def test_alignment_suggestions_are_ranked(client):
    response = client.post(
        "/api/ontology/suggest-alignments",
        json={
            "source_ontology_uri": "http://example.org/onto-a",
            "target_ontology_uri": "http://example.org/onto-b",
            "threshold": 0.35,
            "limit": 5,
        },
    )
    assert response.status_code == 200
    suggestions = response.json()
    assert suggestions
    # Top suggestion should be the Person→PersonRecord pair (highest label similarity).
    top = suggestions[0]
    assert "Person" in top["source_label"]
    assert "Person" in top["target_label"]
    # Results must be sorted descending by score.
    assert suggestions == sorted(suggestions, key=lambda item: item["score"], reverse=True)


def test_health_returns_dimensions_and_issues(client):
    response = client.get("/api/ontology/health?uri=http%3A%2F%2Fexample.org%2Fonto-a")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_score"] >= 0
    assert {dimension["key"] for dimension in payload["dimensions"]} == {
        "completeness",
        "consistency",
        "shacl",
        "alignment",
        "documentation",
    }
    assert isinstance(payload["issues"], list)


def test_shacl_generate_and_shapes(client):
    response = client.post(
        "/api/ontology/shacl/generate",
        json={"uri": "http://example.org/onto-a", "quality_tier": "strict"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "sh:NodeShape" in payload["shacl_turtle"]
    assert payload["shape_count"] >= 1

    shapes = client.get("/api/ontology/shacl/shapes?uri=http%3A%2F%2Fexample.org%2Fonto-a")
    assert shapes.status_code == 200
    assert shapes.json()["shapes"]


def test_shacl_validate_returns_unavailable(client):
    response = client.post(
        "/api/ontology/shacl/validate",
        json={
            "shacl_turtle": "@prefix sh: <http://www.w3.org/ns/shacl#> .",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["conforms"] is False
    assert isinstance(payload["violations"], list)

    with patch.dict("sys.modules", {"pyshacl": None}):
        res_no_pyshacl = client.post(
            "/api/ontology/shacl/validate",
            json={
                "uri": "http://example.org/onto-a",
                "shacl_turtle": "@prefix sh: <http://www.w3.org/ns/shacl#> .",
            },
        )
        assert res_no_pyshacl.status_code == 200
        payload_no_pyshacl = res_no_pyshacl.json()
        assert payload_no_pyshacl["status"] == "unavailable"
        assert payload_no_pyshacl["conforms"] is False
        assert isinstance(payload_no_pyshacl["violations"], list)


def test_shacl_validate_rejects_empty_turtle(client):
    response = client.post(
        "/api/ontology/shacl/validate",
        json={"uri": "http://example.org/onto-a", "shacl_turtle": "   "},
    )
    assert response.status_code == 422


def test_shacl_validate_detects_missing_required_property(client):
    graph = client.app.state.session.graph
    onto_uri = "http://example.org/onto-a"
    person_a = "http://example.org/onto-a#Person"
    person_inst = "http://example.org/onto-a#person-no-name"
    graph.add_node(
        person_inst,
        node_type="owl:NamedIndividual",
        content="Person Without Name",
        scheme_uri=onto_uri,
        **{
            "rdf:type": person_a,
            "rdfs:label": "Person Without Name",
        },
    )

    shacl_turtle = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix onto: <http://example.org/onto-a#> .

onto:PersonNameShape a sh:NodeShape ;
    sh:targetClass onto:Person ;
    sh:property [
        sh:path onto:name ;
        sh:minCount 1 ;
        sh:severity sh:Violation ;
        sh:message "Person must have a name." ;
    ] .
"""

    response = client.post(
        "/api/ontology/shacl/validate",
        json={
            "uri": onto_uri,
            "shacl_turtle": shacl_turtle,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["conforms"] is False
    assert len(payload["violations"]) >= 1
    violation = payload["violations"][0]
    assert violation["severity"] == "Violation"
    assert "person-no-name" in str(violation["focus_node"]) or "person-no-name" in str(violation["node"])


def test_health_returns_404_for_unknown_ontology(client):
    response = client.get("/api/ontology/health?uri=http%3A%2F%2Fnot-loaded.example%2Fonto")
    assert response.status_code == 404


def test_health_shacl_dimension_is_zero_when_unavailable(client):
    with patch.dict("sys.modules", {"pyshacl": None}):
        payload = client.get("/api/ontology/health?uri=http%3A%2F%2Fexample.org%2Fonto-a").json()
        shacl_dim = next(d for d in payload["dimensions"] if d["key"] == "shacl")
        assert shacl_dim["status"] == "unavailable"
        assert shacl_dim["score"] == 0.0
        # Total score must NOT include the unavailable dimension in its average.
        scoreable = [d for d in payload["dimensions"] if d["status"] != "unavailable"]
        expected_total = round(sum(d["score"] for d in scoreable) / len(scoreable), 1)
        assert payload["total_score"] == expected_total


def test_delete_unknown_alignment_returns_404(client):
    response = client.delete("/api/ontology/alignments?id=does-not-exist")
    assert response.status_code == 404


def test_alignment_upsert_is_idempotent(client):
    payload = {
        "source_uri": "http://example.org/onto-a#Person",
        "target_uri": "http://example.org/onto-b#PersonRecord",
        "relation": "owl:equivalentClass",
        "confidence": 0.80,
    }
    first = client.post("/api/ontology/alignments", json=payload).json()
    updated_payload = {**payload, "confidence": 0.95}
    second = client.post("/api/ontology/alignments", json=updated_payload).json()
    assert first["id"] == second["id"], "upsert must reuse the same deterministic ID"
    assert second["confidence"] == 0.95
    assert second["created_at"] == first["created_at"], "created_at must not change on update"
    listed = client.get("/api/ontology/alignments").json()
    assert len(listed) == 1


def test_alignment_accepts_external_uri(client):
    payload = {
        "source_uri": "http://example.org/onto-a#Person",
        "target_uri": "http://schema.org/Person",  # not in local graph
        "relation": "owl:equivalentClass",
        "confidence": 0.75,
    }
    response = client.post("/api/ontology/alignments", json=payload)
    assert response.status_code == 200
    alignment = response.json()
    assert alignment["target_label"] == "Person"  # derived from URI fragment


def test_suggest_alignments_returns_embedding_similarity(client):
    response = client.post(
        "/api/ontology/suggest-alignments",
        json={
            "source_ontology_uri": "http://example.org/onto-a",
            "target_ontology_uri": "http://example.org/onto-b",
            "threshold": 0.20,
            "limit": 10,
        },
    )
    assert response.status_code == 200
    suggestions = response.json()
    assert suggestions
    # When sklearn is available, embedding_similarity should be populated.
    top = suggestions[0]
    assert top["embedding_similarity"] is not None, (
        "TF-IDF embedding similarity must be returned when sklearn is installed"
    )
    # Combined score must be a weighted blend, not purely the label score.
    assert top["score"] != top["label_similarity"] or top["embedding_similarity"] == top["label_similarity"]


def test_shacl_validate_rejects_invalid_turtle_syntax(client):
    response = client.post(
        "/api/ontology/shacl/validate",
        json={
            "uri": "http://example.org/onto-a",
            "shacl_turtle": "this is not valid turtle !!!",
        },
    )
    assert response.status_code == 422


def test_health_alignment_coverage_uses_set_lookup(client):
    # Create an alignment first so coverage score can be non-zero.
    client.post("/api/ontology/alignments", json={
        "source_uri": "http://example.org/onto-a#Person",
        "target_uri": "http://example.org/onto-b#PersonRecord",
        "relation": "owl:equivalentClass",
        "confidence": 0.9,
    })
    payload = client.get("/api/ontology/health?uri=http%3A%2F%2Fexample.org%2Fonto-a").json()
    alignment_dim = next(d for d in payload["dimensions"] if d["key"] == "alignment")
    assert alignment_dim["score"] > 0.0, "alignment coverage must be non-zero after recording an alignment"


def test_suggest_alignments_unaffected_by_individuals(client):
    graph = client.app.state.session.graph
    graph.add_node(
        "http://example.org/onto-a#individual-person",
        node_type="owl:NamedIndividual",
        content="Person",
        scheme_uri="http://example.org/onto-a",
        **{"rdf:type": "http://example.org/onto-a#Person", "rdfs:label": "Person"},
    )
    response = client.post(
        "/api/ontology/suggest-alignments",
        json={
            "source_ontology_uri": "http://example.org/onto-a",
            "target_ontology_uri": "http://example.org/onto-b",
            "threshold": 0.35,
            "limit": 5,
        },
    )
    assert response.status_code == 200
    suggestions = response.json()
    assert suggestions
    for s in suggestions:
        assert "individual-person" not in s["source_uri"]
        assert "individual-person" not in s["target_uri"]


def test_health_shacl_dimension_degrades_gracefully_on_real_error(client):
    import semantica.explorer.routes.ontology as ont_mod
    with patch.object(ont_mod, "_data_graph_turtle_for_uri", side_effect=RuntimeError("boom")):
        response = client.get("/api/ontology/health?uri=http%3A%2F%2Fexample.org%2Fonto-a")
    assert response.status_code == 200
    payload = response.json()
    shacl_dim = next(d for d in payload["dimensions"] if d["key"] == "shacl")
    assert shacl_dim["status"] == "critical"
    assert "boom" in shacl_dim["detail"]
