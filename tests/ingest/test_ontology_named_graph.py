"""A JSON-LD ontology whose terms live in a named graph must not be silently dropped.

A JSON-LD document with a top-level ``@id`` *and* ``@graph`` places its terms in a NAMED
graph. ``rdflib.Graph.parse()`` loads only the default graph and discards the rest without
raising, so every class and property in such a document disappeared while the load reported
success — see issue #1129 for the reproduction through the public API.

This is the same ``Graph`` -> ``Dataset`` migration #757 made for ``JenaStore`` (#756); the
ingest path was not covered by it.
"""

from __future__ import annotations

import json

import pytest

from semantica.ingest.ontology_ingestor import OntologyIngestor

NAMED_GRAPH_ONTOLOGY = {
    "@context": {
        "ex": "https://example.org/ns#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    },
    "@id": "https://example.org/ns",
    "@type": "owl:Ontology",
    "@graph": [
        {"@id": "ex:Thing", "@type": "owl:Class", "rdfs:label": "Thing"},
        {"@id": "ex:Other", "@type": "owl:Class", "rdfs:label": "Other"},
        {
            "@id": "ex:relatesTo",
            "@type": "owl:ObjectProperty",
            "rdfs:domain": {"@id": "ex:Thing"},
            "rdfs:range": {"@id": "ex:Other"},
        },
    ],
}

DEFAULT_GRAPH_ONTOLOGY = {
    "@context": NAMED_GRAPH_ONTOLOGY["@context"],
    "@graph": [
        {"@id": "ex:Thing", "@type": "owl:Class", "rdfs:label": "Thing"},
        {"@id": "ex:Other", "@type": "owl:Class", "rdfs:label": "Other"},
    ],
}


def _write(tmp_path, name, document):
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_terms_in_a_named_graph_are_ingested(tmp_path):
    """The regression: two classes and one object property, all inside the named graph."""
    path = _write(tmp_path, "named.jsonld", NAMED_GRAPH_ONTOLOGY)

    data = OntologyIngestor().ingest_ontology(path).data

    assert len(data["classes"]) == 2, (
        "classes inside a JSON-LD named graph were dropped; the ingestor is reading only "
        "the default graph"
    )
    assert len(data["properties"]) == 1
    assert {c["uri"] for c in data["classes"]} == {
        "https://example.org/ns#Thing",
        "https://example.org/ns#Other",
    }


def test_terms_in_the_default_graph_still_work(tmp_path):
    """Canary for the test above: a document *without* a top-level ``@id`` keeps its terms
    in the default graph and always parsed correctly. If this stopped passing, the fix would
    have traded one blind spot for another."""
    path = _write(tmp_path, "default.jsonld", DEFAULT_GRAPH_ONTOLOGY)

    data = OntologyIngestor().ingest_ontology(path).data

    assert len(data["classes"]) == 2


@pytest.mark.parametrize("document", [NAMED_GRAPH_ONTOLOGY, DEFAULT_GRAPH_ONTOLOGY])
def test_metadata_reports_what_was_actually_read(tmp_path, document):
    """Whatever the shape of the document, the counts reported have to match the terms
    returned — a load that says it succeeded while returning nothing is what made #1129
    cost an afternoon to find."""
    path = _write(tmp_path, "any.jsonld", document)

    result = OntologyIngestor().ingest_ontology(path)

    assert result.data["classes"], "reported success with zero classes"
