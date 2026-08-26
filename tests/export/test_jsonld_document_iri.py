"""The document IRI of a JSON-LD export must depend on content, not the clock
(issue #1147).

``_convert_kg_to_jsonld`` minted the graph's ``@id`` from ``utc_now_iso()``,
and the generic ``_attach_document_metadata`` path did the same for a plain
document ``@id``. Exporting an unchanged graph therefore produced a new
subject every time: three exports of one one-entity graph merged into 3
``semantica:KnowledgeGraph`` nodes and 15 triples for what should have been a
single graph. Neither identifier resolves and the timestamp is already
recorded correctly in ``semantica:exportedAt``, so the fix mints the IRI from
the exported content instead (mirroring ``mint_entity_iri``, #1109), with an
optional caller-supplied override for callers who already name their graphs.
"""

import json

from rdflib import RDF, Graph, URIRef

from semantica.export.json_exporter import JSONExporter

KG = {
    "entities": [{"id": "https://example.org/e1", "text": "Acme Corp", "type": "ORG"}],
    "relationships": [],
}

OTHER_KG = {
    "entities": [
        {"id": "https://example.org/e1", "text": "Acme Corp Renamed", "type": "ORG"}
    ],
    "relationships": [],
}


def _export(kg, tmp_path, name="out.jsonld", **options):
    path = tmp_path / name
    JSONExporter().export_knowledge_graph(kg, path, format="json-ld", **options)
    return path


def test_reexporting_an_unchanged_graph_is_idempotent(tmp_path):
    """The whole point of an identifier: same content, same @id."""
    first = json.loads(_export(KG, tmp_path, "a.jsonld").read_text())
    second = json.loads(_export(KG, tmp_path, "b.jsonld").read_text())

    assert first["@id"] == second["@id"]


def test_a_changed_graph_gets_a_different_id(tmp_path):
    unchanged = json.loads(_export(KG, tmp_path, "a.jsonld").read_text())
    changed = json.loads(_export(OTHER_KG, tmp_path, "b.jsonld").read_text())

    assert unchanged["@id"] != changed["@id"]


def test_merging_repeated_exports_yields_one_graph_node(tmp_path):
    """Regression for the exact repro in #1147: churn no longer multiplies nodes."""
    merged = Graph()
    for i in range(3):
        path = _export(KG, tmp_path, f"churn{i}.jsonld")
        merged.parse(str(path), format="json-ld")

    # Exactly one subject typed as a KnowledgeGraph, regardless of how many
    # times the unchanged graph was exported and merged.
    kg_nodes = set(
        merged.subjects(RDF.type, URIRef("https://semantica.dev/ns#KnowledgeGraph"))
    )
    assert len(kg_nodes) == 1

    entity_nodes = set(
        merged.subjects(RDF.type, URIRef("https://semantica.dev/vocab/ORG"))
    )
    assert len(entity_nodes) == 1


def test_exported_at_still_varies_between_exports(tmp_path):
    """Identity is now content-derived, but provenance still records each run."""
    first = json.loads(_export(KG, tmp_path, "a.jsonld").read_text())
    second = json.loads(_export(KG, tmp_path, "b.jsonld").read_text())

    assert first["@id"] == second["@id"]
    assert first["semantica:exportedAt"] != second["semantica:exportedAt"]


def test_caller_supplied_graph_uri_is_honored(tmp_path):
    path = _export(KG, tmp_path, graph_uri="https://example.org/my-graph")
    document = json.loads(path.read_text())

    assert document["@id"] == "https://example.org/my-graph"


def _document_node_id(document):
    """The generic (non-knowledge-graph) path hangs its own @id off a member
    of @graph rather than the top level, to avoid re-creating the named-graph
    bug fixed by #1145. Find that member and return its @id."""
    for node in document["@graph"]:
        if "semantica:exportedAt" in node:
            return node["@id"]
    raise AssertionError(f"no document metadata node in @graph: {document}")


def test_caller_supplied_document_uri_is_honored_for_a_generic_export(tmp_path):
    payload = {"note": "no entities or relationships here"}
    path = tmp_path / "generic.jsonld"
    JSONExporter().export(
        payload, path, format="json-ld", document_uri="https://example.org/my-doc"
    )
    document = json.loads(path.read_text())

    assert _document_node_id(document) == "https://example.org/my-doc"


def test_generic_document_id_is_also_content_derived(tmp_path):
    """The non-knowledge-graph path (_attach_document_metadata) gets the same fix."""
    payload = {"note": "plain data, no @id of its own"}

    first = tmp_path / "a.jsonld"
    second = tmp_path / "b.jsonld"
    JSONExporter().export(payload, first, format="json-ld")
    JSONExporter().export(dict(payload), second, format="json-ld")

    first_id = _document_node_id(json.loads(first.read_text()))
    second_id = _document_node_id(json.loads(second.read_text()))
    assert first_id == second_id


def test_document_id_still_differs_for_different_generic_payloads(tmp_path):
    a = tmp_path / "a.jsonld"
    b = tmp_path / "b.jsonld"
    JSONExporter().export({"note": "one"}, a, format="json-ld")
    JSONExporter().export({"note": "two"}, b, format="json-ld")

    a_id = _document_node_id(json.loads(a.read_text()))
    b_id = _document_node_id(json.loads(b.read_text()))
    assert a_id != b_id
