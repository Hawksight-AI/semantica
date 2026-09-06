"""Tests for Ontology Hub subissue 3 APIs."""

from unittest.mock import patch
from urllib.parse import quote

import pytest

from semantica.context.context_graph import ContextGraph
# fastapi ships in the optional `explorer` extra, not in `dev`, so this module
# must skip rather than fail collection when it is absent. The guard has to sit
# above the import below, which pulls fastapi in transitively.
pytest.importorskip("fastapi")

from semantica.explorer.app import create_app  # noqa: E402
from semantica.explorer.routes.ontology import (  # noqa: E402
    _MAX_ANALYSIS_NODES,
    OntologyEntry,
    _convert_ontology_to_graph,
    _node_belongs_to_ontology,
)
from semantica.explorer.session import GraphSession  # noqa: E402

from starlette.testclient import TestClient  # noqa: E402


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


def test_ontology_graph_returns_editable_schema_nodes_and_edges(client):
    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org/onto-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    node_ids = {node["id"] for node in payload["nodes"]}
    assert "http://example.org/onto-a" in node_ids
    assert "http://example.org/onto-a#Person" in node_ids
    assert "http://example.org/onto-a#name" in node_ids
    assert any(
        edge["source"] == "http://example.org/onto-a#name"
        and edge["target"] == "http://example.org/onto-a#Person"
        and edge["type"] == "rdfs:domain"
        for edge in payload["edges"]
    )


def test_ontology_graph_rejects_unregistered_namespace(client):
    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org"},
    )

    assert response.status_code == 404


def test_ontology_graph_excludes_separately_registered_nested_ontology(client):
    graph = client.app.state.session.graph
    nested = "http://example.org/onto-a/nested"
    nested_class = f"{nested}#PrivateClass"
    graph.add_node(nested, node_type="owl:Ontology", content="Nested Ontology")
    graph.add_node(nested_class, node_type="owl:Class", content="Private Class")

    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org/onto-a"},
    )

    assert response.status_code == 200
    node_ids = {node["id"] for node in response.json()["nodes"]}
    assert nested not in node_ids
    assert nested_class not in node_ids


def test_ontology_graph_prefers_explicit_ownership_over_uri_namespace(client):
    graph = client.app.state.session.graph
    explicit_member = "http://unrelated.example/Person"
    graph.add_node(
        explicit_member,
        node_type="owl:Class",
        content="Explicit Member",
        scheme_uri="http://example.org/onto-a",
    )

    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org/onto-a"},
    )

    assert response.status_code == 200
    assert explicit_member in {node["id"] for node in response.json()["nodes"]}


def test_ontology_graph_excludes_inward_edges_from_other_ontologies(client):
    graph = client.app.state.session.graph
    foreign_prop = "http://example.org/onto-b#recordOf"
    graph.add_node(
        foreign_prop,
        node_type="owl:ObjectProperty",
        content="record of",
        scheme_uri="http://example.org/onto-b",
    )
    # onto-b's property points its domain at onto-a's class: an inward
    # reference that must not pull the foreign property into onto-a's graph.
    graph.add_edge(foreign_prop, "http://example.org/onto-a#Person", edge_type="rdfs:domain")

    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org/onto-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert foreign_prop not in {node["id"] for node in payload["nodes"]}
    assert all(edge["source"] != foreign_prop for edge in payload["edges"])


def test_ontology_graph_excludes_unregistered_nested_namespace(client):
    graph = client.app.state.session.graph
    nested_class = "http://example.org/onto-a/vocab#Term"
    graph.add_node(nested_class, node_type="owl:Class", content="Nested Term")

    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org/onto-a"},
    )

    assert response.status_code == 200
    assert nested_class not in {node["id"] for node in response.json()["nodes"]}


def test_node_belongs_to_ontology_nested_namespace_matrix():
    parent = "http://example.org/onto-a"
    child = "http://example.org/onto-a/nested"

    def node(node_id):
        return {"id": node_id, "properties": {}}

    assert _node_belongs_to_ontology(node(f"{parent}#Person"), parent, {parent})
    assert _node_belongs_to_ontology(node(f"{parent}/Person"), parent, {parent})
    # An unregistered nested namespace is not absorbed into the parent,
    # whether fragment-based or path-based
    assert not _node_belongs_to_ontology(node(f"{child}#Term"), parent, {parent})
    assert not _node_belongs_to_ontology(node(f"{child}/Term"), parent, {parent})
    # Once registered, the nested namespace owns its nodes
    assert not _node_belongs_to_ontology(node(f"{child}#Term"), parent, {parent, child})
    assert _node_belongs_to_ontology(node(f"{child}#Term"), child, {parent, child})
    assert _node_belongs_to_ontology(node(f"{child}/Term"), child, {parent, child})


def test_load_fallback_import_without_declaration_is_editable(client):
    turtle = """
@prefix ex: <http://data.example.org/people#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Employee a rdfs:Class ;
    rdfs:label "Employee" .
ex:manager a rdf:Property ;
    rdfs:label "manager" .
"""
    with patch(
        "semantica.ingest.ontology_ingestor.OntologyIngestor.ingest_ontology",
        side_effect=RuntimeError("force fallback parser"),
    ):
        loaded = client.post(
            "/api/ontology/load",
            json={"content": turtle, "format": "turtle"},
        )
    assert loaded.status_code == 200
    uri = loaded.json()["uri"]
    assert uri.startswith("urn:semantica:onto:")

    response = client.get("/api/ontology/graph", params={"uri": uri})
    assert response.status_code == 200
    payload = response.json()
    node_ids = {node["id"] for node in payload["nodes"]}
    assert uri in node_ids
    assert "http://data.example.org/people#Employee" in node_ids


def test_ontology_graph_ignores_unrelated_data_when_enforcing_size_limit(client):
    graph = client.app.state.session.graph
    for index in range(5_001):
        graph.add_node(
            f"urn:unrelated:{index}",
            node_type="owl:Class",
            content="Unrelated",
            scheme_uri="http://example.org/onto-b",
        )

    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org/onto-a"},
    )

    assert response.status_code == 200
    assert "http://example.org/onto-a#Person" in {
        node["id"] for node in response.json()["nodes"]
    }


def test_ontology_graph_rejects_oversized_core_and_stops_scanning(client, monkeypatch):
    graph = client.app.state.session.graph
    for index in range(5_001):
        graph.add_node(
            f"http://example.org/onto-a#Bulk{index:05d}",
            node_type="owl:Class",
            content="Bulk",
            scheme_uri="http://example.org/onto-a",
        )
    for index in range(3_000):
        graph.add_node(
            f"urn:unrelated:{index}",
            node_type="owl:Class",
            content="Unrelated",
            scheme_uri="http://example.org/onto-b",
        )

    streamed = 0
    original_iter_nodes = GraphSession.iter_nodes

    def counting_iter_nodes(self, node_type=None):
        nonlocal streamed
        for node in original_iter_nodes(self, node_type=node_type):
            streamed += 1
            yield node

    monkeypatch.setattr(GraphSession, "iter_nodes", counting_iter_nodes)

    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org/onto-a"},
    )

    assert response.status_code == 413
    assert str(_MAX_ANALYSIS_NODES) in response.json()["detail"]
    # The graph holds 8,001 owl:Class nodes and onto-a's own sort first, so a
    # scan that abandons at the cap sees far fewer than the whole type.
    assert streamed < 6_000


def test_ontology_graph_hydrates_external_edge_targets_in_sorted_order(client):
    graph = client.app.state.session.graph
    external = "http://external.example/Thing"
    also_external = "http://external.example/Aardvark"
    graph.add_node(external, node_type="owl:Class", content="External Thing")
    graph.add_node(also_external, node_type="owl:Class", content="External Aardvark")
    graph.add_edge("http://example.org/onto-a#name", external, edge_type="rdfs:range")
    graph.add_edge("http://example.org/onto-a#name", also_external, edge_type="rdfs:range")

    response = client.get(
        "/api/ontology/graph",
        params={"uri": "http://example.org/onto-a"},
    )

    assert response.status_code == 200
    node_ids = [node["id"] for node in response.json()["nodes"]]
    assert {external, also_external} <= set(node_ids)
    assert node_ids == sorted(node_ids)


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


def test_shacl_validate_surfaces_warning_severity_results(client):
    graph = client.app.state.session.graph
    onto_uri = "http://example.org/onto-a"
    person_a = "http://example.org/onto-a#Person"
    person_inst = "http://example.org/onto-a#person-no-email"
    graph.add_node(
        person_inst,
        node_type="owl:NamedIndividual",
        content="Person Without Email",
        scheme_uri=onto_uri,
        **{
            "rdf:type": person_a,
            "rdfs:label": "Person Without Email",
        },
    )

    shacl_turtle = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix onto: <http://example.org/onto-a#> .

onto:PersonEmailShape a sh:NodeShape ;
    sh:targetClass onto:Person ;
    sh:property [
        sh:path onto:email ;
        sh:minCount 1 ;
        sh:severity sh:Warning ;
        sh:message "Person should have an email." ;
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
    # pySHACL flips conforms=False for any result regardless of severity, but
    # previously the response body gave no explanation for that: violations
    # was always populated from report.violations only, so a report that was
    # "non-conforming" purely due to a Warning-severity result rendered as
    # conforms=False with an empty violations list. Warnings/infos are now
    # folded into the violations array so the response is self-explanatory.
    assert payload["conforms"] is False
    assert len(payload["violations"]) >= 1
    warning = payload["violations"][0]
    assert warning["severity"] == "Warning"
    assert "warning" in payload["message"].lower()


def test_health_dedupes_node_edge_fetch(client):
    import semantica.explorer.routes.ontology as ont_mod

    with patch.object(
        ont_mod, "_fetch_analysis_graph", wraps=ont_mod._fetch_analysis_graph
    ) as fetch_spy:
        response = client.get("/api/ontology/health?uri=http%3A%2F%2Fexample.org%2Fonto-a")
    assert response.status_code == 200
    # /health needs both the generated SHACL shapes and the data graph for the
    # same uri; both used to independently re-fetch nodes/edges from the
    # session. They now share a single fetch.
    assert fetch_spy.call_count == 1


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


@pytest.mark.asyncio
async def test_data_graph_turtle_resolves_onto_prefix_and_unknown_curies(client):
    from unittest.mock import MagicMock
    from semantica.explorer.routes.ontology import _data_graph_turtle_for_uri

    graph = client.app.state.session.graph
    onto_uri = "http://example.org/onto-a"
    person_a = "http://example.org/onto-a#Person"
    person_inst = "http://example.org/onto-a#person-with-name"
    graph.add_node(
        person_inst,
        node_type="owl:NamedIndividual",
        content="Person With Name",
        scheme_uri=onto_uri,
        **{
            "rdf:type": person_a,
            "onto:name": "Alice",
            "custom:prop": "http://custom.example/val",
        },
    )

    ttl = await _data_graph_turtle_for_uri(MagicMock(), client.app.state.session, onto_uri)
    assert "http://example.org/onto-a#name" in ttl or "onto:name" in ttl
    assert "http://example.org/#onto:name" not in ttl
    assert "http://example.org/onto-a#custom:prop" not in ttl


def test_ontology_namespace_helper_handles_all_uri_forms():
    from semantica.explorer.routes.ontology import _ontology_namespace

    assert _ontology_namespace("http://example.org/onto-a") == "http://example.org/onto-a#"
    assert _ontology_namespace("http://example.org/onto-a/") == "http://example.org/onto-a/"
    assert _ontology_namespace("http://example.org/onto-a#") == "http://example.org/onto-a#"
    assert _ontology_namespace("http://example.org/onto-a#schema") == "http://example.org/onto-a#"


@pytest.mark.asyncio
async def test_data_graph_turtle_preserves_slash_namespace_for_local_terms(client):
    from semantica.explorer.routes.ontology import _data_graph_turtle_for_uri
    from unittest.mock import MagicMock

    graph = client.app.state.session.graph
    onto_uri = "http://example.org/onto-slash/"
    graph.add_node(
        onto_uri,
        node_type="owl:Ontology",
        content="Slash Ontology",
        **{"rdfs:label": "Slash Ontology", "uri": onto_uri},
    )
    person_a = "http://example.org/onto-slash/Person"
    person_inst = "http://example.org/onto-slash/person-1"
    graph.add_node(
        person_inst,
        node_type="owl:NamedIndividual",
        content="Person 1",
        scheme_uri=onto_uri,
        **{
            "rdf:type": person_a,
            "onto:name": "Alice",
            "name": "Alice Unprefixed",
        },
    )

    ttl = await _data_graph_turtle_for_uri(MagicMock(), client.app.state.session, onto_uri)
    assert "http://example.org/onto-slash/name" in ttl or "onto:name" in ttl
    assert "http://example.org/onto-slash#name" not in ttl
    assert "http://example.org/onto-slash/Person" in ttl or "onto:Person" in ttl
    assert "http://example.org/onto-slash#Person" not in ttl


@pytest.mark.asyncio
async def test_data_graph_turtle_serializes_list_of_dicts_as_uri_references(client):
    from semantica.explorer.routes.ontology import _data_graph_turtle_for_uri
    from unittest.mock import MagicMock

    graph = client.app.state.session.graph
    onto_uri = "http://example.org/onto-jsonld/"
    graph.add_node(
        onto_uri,
        node_type="owl:Ontology",
        content="JSON-LD Ontology",
        **{"rdfs:label": "JSON-LD Ontology", "uri": onto_uri},
    )
    node_inst = "http://example.org/onto-jsonld/item-1"
    graph.add_node(
        node_inst,
        node_type="owl:Class",
        content="Item 1",
        scheme_uri=onto_uri,
        **{
            "rdfs:seeAlso": [
                {"@id": "http://example.org/external/ref1"},
                {"uri": "http://example.org/external/ref2"},
            ],
        },
    )

    ttl = await _data_graph_turtle_for_uri(MagicMock(), client.app.state.session, onto_uri)
    assert "<http://example.org/external/ref1>" in ttl
    assert "<http://example.org/external/ref2>" in ttl
    assert "{'" not in ttl and "'@id'" not in ttl




def test_validate_shacl_rejects_oversized_turtle(client):
    shacl_turtle = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix onto: <http://example.org/onto-a#> .

onto:PersonShape a sh:NodeShape ;
    sh:targetClass onto:Person .
"""
    with patch("semantica.explorer.routes.ontology._MAX_SHACL_TURTLE_BYTES", 20):
        response = client.post(
            "/api/ontology/shacl/validate",
            json={
                "uri": "http://example.org/onto-a",
                "shacl_turtle": shacl_turtle,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "error"
        assert "exceeds maximum allowed size" in payload["message"]
        assert "SEMANTICA_MAX_SHACL_TURTLE_BYTES" in payload["message"]


def test_validate_shacl_rejects_too_many_triples(client):
    shacl_turtle = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix onto: <http://example.org/onto-a#> .

onto:PersonShape a sh:NodeShape ;
    sh:targetClass onto:Person .
"""
    with patch("semantica.explorer.routes.ontology._MAX_SHACL_TRIPLES", 1):
        response = client.post(
            "/api/ontology/shacl/validate",
            json={
                "uri": "http://example.org/onto-a",
                "shacl_turtle": shacl_turtle,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "error"
        assert "exceeds maximum allowed limit" in payload["message"]
        assert "SEMANTICA_MAX_SHACL_TRIPLES" in payload["message"]


def test_validate_shacl_handles_timeout(client):
    shacl_turtle = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix onto: <http://example.org/onto-a#> .

onto:PersonShape a sh:NodeShape ;
    sh:targetClass onto:Person .
"""
    import time

    def slow_validate(*args, **kwargs):
        time.sleep(0.3)
        return MagicMock(conforms=True, violations=[])

    with patch("semantica.explorer.routes.ontology._MAX_SHACL_TIMEOUT_SECONDS", 0.05), \
         patch("semantica.ontology.OntologyEngine.validate_graph", side_effect=slow_validate):
        response = client.post(
            "/api/ontology/shacl/validate",
            json={
                "uri": "http://example.org/onto-a",
                "shacl_turtle": shacl_turtle,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "error"
        assert "timed out" in payload["message"]
        assert "SEMANTICA_MAX_SHACL_TIMEOUT" in payload["message"]


def test_validate_shacl_returns_unavailable_for_truncated_graph(client):
    shacl_turtle = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix onto: <http://example.org/onto-a#> .

onto:PersonShape a sh:NodeShape ;
    sh:targetClass onto:Person .
"""
    with patch("semantica.explorer.routes.ontology._MAX_ANALYSIS_NODES", 0):
        response = client.post(
            "/api/ontology/shacl/validate",
            json={
                "uri": "http://example.org/onto-a",
                "shacl_turtle": shacl_turtle,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "unavailable"
        assert "exceeds maximum analysis limit" in payload["message"]
        assert payload["conforms"] is False


def test_health_shacl_dimension_returns_critical_for_truncated_graph(client):
    with patch("semantica.explorer.routes.ontology._MAX_ANALYSIS_NODES", 0):
        payload = client.get("/api/ontology/health?uri=http%3A%2F%2Fexample.org%2Fonto-a").json()
        shacl_dim = next(d for d in payload["dimensions"] if d["key"] == "shacl")
        assert shacl_dim["status"] == "critical"
        assert "exceeds maximum analysis limit" in shacl_dim["detail"]


def test_ontology_load_rejects_cyclic_skos_hierarchy(client):
    cyclic_ttl = """
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex:   <http://example.org/> .
ex:S a skos:ConceptScheme ; skos:prefLabel "Scheme" .
ex:A a skos:Concept ; skos:prefLabel "Alpha" ; skos:inScheme ex:S ; skos:broader ex:B .
ex:B a skos:Concept ; skos:prefLabel "Beta" ; skos:inScheme ex:S ; skos:broader ex:A .
"""
    response = client.post(
        "/api/ontology/load",
        json={
            "content": cyclic_ttl,
            "format": "turtle",
        },
    )
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()


def test_ontology_load_does_not_swallow_422_from_ingestor_success_path(client):
    """A ValueError raised by add_nodes_and_edges() after OntologyIngestor
    succeeds must surface as its own 422, not be masked by the broad
    `except Exception` fallback-to-basic-parsing handler and silently
    retried under a different parser."""
    from semantica.ingest.ontology_ingestor import OntologyData

    fake_data = OntologyData(
        data={
            "uri": "http://example.org/onto-fake",
            "name": "Fake Ontology",
            "classes": [{"uri": "http://example.org/onto-fake#A", "name": "A"}],
            "properties": [],
        },
        source_path="fake.ttl",
        format="turtle",
    )

    with patch(
        "semantica.ingest.ontology_ingestor.OntologyIngestor.ingest_ontology",
        return_value=fake_data,
    ), patch(
        "semantica.explorer.session.GraphSession.add_nodes_and_edges",
        side_effect=ValueError("SKOS hierarchy contains a cycle involving 'A'."),
    ), patch(
        "semantica.explorer.routes.ontology._parse_rdf_sync"
    ) as fallback_parse:
        response = client.post(
            "/api/ontology/load",
            json={"content": "@prefix ex: <http://example.org/> . ex:A a ex:Thing .", "format": "turtle"},
        )

    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()
    fallback_parse.assert_not_called()


def test_convert_ontology_uses_standard_property_types_and_scheme_uri():
    ontology_uri = "http://example.org/onto"
    nodes, _ = _convert_ontology_to_graph(
        {
            "uri": ontology_uri,
            "name": "Example Ontology",
            "classes": [
                {"uri": f"{ontology_uri}#Person", "name": "Person"},
            ],
            "properties": [
                {"uri": f"{ontology_uri}#name", "name": "name", "type": "data"},
                {"uri": f"{ontology_uri}#knows", "name": "knows", "type": "object"},
            ],
        }
    )

    by_id = {node["id"]: node for node in nodes}
    assert by_id[f"{ontology_uri}#Person"]["properties"]["scheme_uri"] == ontology_uri
    assert by_id[f"{ontology_uri}#name"]["type"] == "owl:DatatypeProperty"
    assert by_id[f"{ontology_uri}#knows"]["type"] == "owl:ObjectProperty"
    assert by_id[f"{ontology_uri}#name"]["properties"]["scheme_uri"] == ontology_uri


# ---------------------------------------------------------------------------
# refresh_ontology — single combined add_nodes_and_edges() coverage (#775)
# ---------------------------------------------------------------------------

_REFRESH_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/refresh-onto#> .
<http://example.org/refresh-onto> a owl:Ontology .
ex:Widget a owl:Class ; rdfs:label "Widget" .
ex:Gadget a owl:Class ; rdfs:label "Gadget" ; rdfs:subClassOf ex:Widget .
"""

_REFRESH_CYCLIC_TTL = """
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex:   <http://example.org/refresh-onto#> .
ex:S a skos:ConceptScheme ; skos:prefLabel "Scheme" .
ex:A a skos:Concept ; skos:prefLabel "Alpha" ; skos:inScheme ex:S ; skos:broader ex:B .
ex:B a skos:Concept ; skos:prefLabel "Beta" ; skos:inScheme ex:S ; skos:broader ex:A .
"""


def _register_refresh_entry(client, uri="http://example.org/refresh-onto", source_url="http://example.org/refresh-onto.ttl"):
    entry = OntologyEntry(
        uri=uri,
        name="Refresh Ontology",
        format="turtle",
        status="external",
        source_url=source_url,
        loaded_at="2024-01-01T00:00:00+00:00",
    )
    # Registry is created lazily on app.state by _get_registry; seed it directly.
    if not hasattr(client.app.state, "ontology_registry"):
        client.app.state.ontology_registry = {}
    client.app.state.ontology_registry[uri] = entry
    return entry


def test_refresh_ontology_success_adds_nodes_and_edges(client):
    entry = _register_refresh_entry(client)
    encoded_uri = quote(entry.uri, safe="")

    with patch(
        "semantica.explorer.routes.ontology._fetch_url_sync",
        return_value=_REFRESH_TTL.encode("utf-8"),
    ):
        response = client.post(f"/api/ontology/{encoded_uri}/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["uri"] == entry.uri
    assert payload["nodes_added"] >= 2   # Widget, Gadget (+ ontology node depending on parser)
    assert payload["edges_added"] >= 1   # Gadget rdfs:subClassOf Widget


def test_refresh_ontology_rejects_cyclic_skos_hierarchy_without_partial_write(client):
    entry = _register_refresh_entry(client)
    encoded_uri = quote(entry.uri, safe="")

    graph = client.app.state.session.graph
    nodes_before = len(graph.nodes)

    with patch(
        "semantica.explorer.routes.ontology._fetch_url_sync",
        return_value=_REFRESH_CYCLIC_TTL.encode("utf-8"),
    ), patch(
        "semantica.explorer.session.GraphSession.add_nodes_and_edges",
        wraps=client.app.state.session.add_nodes_and_edges,
    ) as spy:
        response = client.post(f"/api/ontology/{encoded_uri}/refresh")

    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()
    # A single combined add_nodes_and_edges() call was made — not separate
    # add_nodes()/add_edges() calls — so the upfront SKOS validation runs
    # before either write and the cyclic edges leave no nodes behind in the
    # graph. add_nodes_and_edges() provides pre-write validation and
    # lock-based mutual exclusion, not general transactional rollback.
    spy.assert_called_once()
    assert len(graph.nodes) == nodes_before


def test_refresh_ontology_unknown_uri_returns_404(client):
    response = client.post("/api/ontology/http%3A%2F%2Fexample.org%2Fnot-registered/refresh")
    assert response.status_code == 404


def test_refresh_ontology_missing_source_url_returns_422(client):
    entry = _register_refresh_entry(client, uri="http://example.org/refresh-onto-nosrc", source_url=None)
    encoded_uri = quote(entry.uri, safe="")
    response = client.post(f"/api/ontology/{encoded_uri}/refresh")
    assert response.status_code == 422
    assert "source url" in response.json()["detail"].lower()
