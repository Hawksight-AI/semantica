"""Caller data must never expand into the Semantica namespace (#1146).

``@vocab`` used to sit in every JSON-LD context pointing at ``ns#``, so every
bare term in caller data expanded into it: an extracted type like ``"ORG"``
became ``ns#ORG`` (a term the vocabulary does not define), and a metadata key
like ``"source"`` collided with the real ``sem:source`` object property,
attaching a plain string to a property whose range is a resource. The fix
removes ``@vocab`` outright: only explicit ``semantica:``-prefixed terms
resolve, caller type labels travel as ``semantica:type`` strings, and caller
metadata survives as one ``rdf:JSON`` literal.
"""

import json

from rdflib import RDF, Graph, Literal, URIRef

from semantica.export.json_exporter import JSONExporter
from semantica.export.rdf_exporter import RDFExporter, SEMANTICA_NS

NS = SEMANTICA_NS
E1 = "https://example.org/e1"

KG = {
    "entities": [
        {
            "id": E1,
            "text": "Acme",
            "type": "ORG",
            "metadata": {"source": "crm_export_2024"},
        }
    ],
    "relationships": [
        {
            "source_id": E1,
            "target_id": "https://example.org/e2",
            "type": "employs",
        }
    ],
}


def _jsonld_file(exporter, kind, tmp_path, name):
    path = tmp_path / name
    if kind == "knowledge_graph":
        exporter.export_knowledge_graph(KG, path, format="json-ld")
    elif kind == "entities":
        exporter.export_entities(KG["entities"], path, format="json-ld")
    elif kind == "relationships":
        exporter.export_relationships(KG["relationships"], path, format="json-ld")
    elif kind == "generic":
        exporter.export({"note": "plain payload, no @id"}, path, format="json-ld")
    else:
        raise AssertionError(kind)
    return json.loads(path.read_text())


def test_no_jsonld_context_declares_a_vocab(tmp_path):
    exporter = JSONExporter()
    for kind in ("knowledge_graph", "entities", "relationships", "generic"):
        context = _jsonld_file(exporter, kind, tmp_path, f"{kind}.jsonld")[
            "@context"
        ]
        assert "@vocab" not in context, f"{kind}: @vocab expands caller data"

    context = json.loads(RDFExporter().export_to_rdf(KG, format="jsonld"))[
        "@context"
    ]
    assert "@vocab" not in context


def test_extracted_type_labels_stay_out_of_the_namespace(tmp_path):
    path = tmp_path / "kg.jsonld"
    JSONExporter().export_knowledge_graph(KG, path, format="json-ld")

    graph = Graph()
    graph.parse(str(path), format="json-ld")

    assert (None, RDF.type, URIRef(NS + "ORG")) not in graph, (
        "the caller's type label was minted as a class in ns#"
    )
    assert (URIRef(E1), RDF.type, URIRef(NS + "Entity")) in graph
    assert (URIRef(E1), URIRef(NS + "type"), Literal("ORG")) in graph, (
        "the label itself must survive, as a string"
    )


def test_metadata_keys_stay_out_of_the_namespace(tmp_path):
    path = tmp_path / "kg.jsonld"
    JSONExporter().export_knowledge_graph(KG, path, format="json-ld")

    graph = Graph()
    graph.parse(str(path), format="json-ld")

    assert (None, URIRef(NS + "source"), Literal("crm_export_2024")) not in (
        graph
    ), "caller metadata value attached to the real sem:source object property"
    for _, _, o in graph.triples((None, URIRef(NS + "source"), None)):
        assert not isinstance(o, Literal), (
            "sem:source has a resource range but received a plain literal"
        )

    literals = [
        o
        for o in graph.objects(None, URIRef(NS + "metadata"))
        if isinstance(o, Literal)
    ]
    assert literals, "the metadata dict was dropped instead of preserved"
    assert literals[0].datatype == RDF.JSON
    assert json.loads(str(literals[0])) == {"source": "crm_export_2024"}


def test_rdf_exporter_jsonld_keeps_type_labels_out_of_the_namespace():
    graph = Graph()
    graph.parse(
        data=RDFExporter().export_to_rdf(KG, format="jsonld"), format="json-ld"
    )

    assert (None, RDF.type, URIRef(NS + "ORG")) not in graph
    assert (URIRef(E1), RDF.type, URIRef(NS + "Entity")) in graph
    assert (URIRef(E1), URIRef(NS + "type"), Literal("ORG")) in graph
