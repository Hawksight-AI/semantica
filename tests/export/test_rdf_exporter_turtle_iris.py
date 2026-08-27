"""Regression tests for valid Turtle IRI generation (issue #1099)."""

from rdflib import RDF, Graph, URIRef

from semantica.export import RDFExporter
from semantica.kg.graph_builder import GraphBuilder


def test_turtle_normalizes_graph_builder_default_identifiers():
    """Default GraphBuilder labels with spaces become stable absolute IRIs."""
    source = {
        "entities": [
            {
                "id": "Kochi, Kerala",
                "name": "Kochi, Kerala",
                "type": "LOCATION",
            },
            {"id": "Jane Doe", "name": "Jane Doe", "type": "PERSON"},
        ],
        "relationships": [
            {
                "source": "Jane Doe",
                "target": "Kochi, Kerala",
                "type": "located_in",
            },
        ],
    }
    graph_data = GraphBuilder(resolve_conflicts=False).build(sources=[source])

    turtle = RDFExporter().export_to_rdf(graph_data, format="turtle")
    parsed = Graph().parse(data=turtle, format="turtle")
    assert "<Jane Doe>" not in turtle
    assert "<Kochi, Kerala>" not in turtle

    kochi = URIRef("https://semantica.dev/ns#Kochi%2C%20Kerala")
    jane = URIRef("https://semantica.dev/ns#Jane%20Doe")
    assert (
        kochi,
        RDF.type,
        URIRef("https://semantica.dev/ns#LOCATION"),
    ) in parsed
    jane_type = URIRef("https://semantica.dev/ns#PERSON")
    assert (jane, RDF.type, jane_type) in parsed
    assert (
        jane,
        URIRef("https://semantica.dev/ns#located_in"),
        kochi,
    ) in parsed


def test_turtle_preserves_absolute_iris():
    """Already-valid absolute resource IRIs remain unchanged."""
    turtle = RDFExporter().export_to_rdf(
        {
            "entities": [
                {
                    "id": "https://example.org/entities/jane",
                    "text": "Jane",
                    "type": "urn:example:Person",
                }
            ],
            "relationships": [],
        },
        format="turtle",
    )
    parsed = Graph().parse(data=turtle, format="turtle")

    assert (
        URIRef("https://example.org/entities/jane"),
        RDF.type,
        URIRef("urn:example:Person"),
    ) in parsed


def test_turtle_preserves_opaque_absolute_iris_and_encodes_bad_percent_escapes():
    """Opaque schemes remain absolute and malformed percent escapes are encoded."""
    turtle = RDFExporter().export_to_rdf(
        {
            "entities": [
                {"id": "mailto:foo", "type": "isbn:0451450523"},
                {"id": "http://example.org/bad%zz", "type": "PERSON"},
            ],
            "relationships": [],
        },
        format="turtle",
    )
    parsed = Graph().parse(data=turtle, format="turtle")

    assert (
        URIRef("mailto:foo"),
        RDF.type,
        URIRef("isbn:0451450523"),
    ) in parsed
    assert URIRef("http://example.org/bad%25zz") in parsed.all_nodes()


def test_turtle_normalizes_temporal_relationship_endpoints():
    """Temporal relationship metadata uses the same normalized resource IRIs."""
    turtle = RDFExporter().export_to_rdf(
        {
            "entities": [
                {"id": "Jane Doe", "type": "PERSON"},
                {"id": "Kochi, Kerala", "type": "LOCATION"},
            ],
            "relationships": [
                {
                    "source": "Jane Doe",
                    "target": "Kochi, Kerala",
                    "type": "located_in",
                    "valid_from": "2024-01-01T00:00:00+00:00",
                    "valid_until": "2024-02-01T00:00:00+00:00",
                }
            ],
        },
        format="turtle",
        include_temporal=True,
    )
    parsed = Graph().parse(data=turtle, format="turtle")

    assert (
        None,
        URIRef("https://semantica.dev/ns#source"),
        URIRef("https://semantica.dev/ns#Jane%20Doe"),
    ) in parsed
    assert (
        None,
        URIRef("https://semantica.dev/ns#target"),
        URIRef("https://semantica.dev/ns#Kochi%2C%20Kerala"),
    ) in parsed


def test_turtle_expands_context_prefixes_and_mints_relative_values():
    """Context prefixes expand while bare values use the fallback namespace."""
    turtle = RDFExporter().export_to_rdf(
        {
            "@context": {"ex": "https://example.org/"},
            "entities": [{"id": "ORG", "type": "ex:Person"}],
            "relationships": [],
        },
        format="turtle",
    )
    parsed = Graph().parse(data=turtle, format="turtle")

    assert (
        URIRef("https://semantica.dev/ns#ORG"),
        RDF.type,
        URIRef("https://example.org/Person"),
    ) in parsed


def test_rdfxml_normalizes_resource_iris():
    """RDF/XML resource attributes use the same safe absolute IRIs."""
    data = {
        "entities": [
            {"id": "Acme Corp", "type": "Person"},
            {"id": "mailto:foo", "type": "isbn:0451450523"},
        ],
        "relationships": [
            {"source": "Jane Doe", "target": "Acme Corp", "type": "knows"}
        ],
    }
    rdfxml = RDFExporter().export_to_rdf(data, format="rdfxml")
    parsed = Graph().parse(data=rdfxml, format="xml")

    assert URIRef("https://semantica.dev/ns#Acme%20Corp") in parsed.all_nodes()
    assert URIRef("mailto:foo") in parsed.all_nodes()


def test_ntriples_normalizes_resource_iris():
    """N-Triples resource IRIs reject neither spaces nor opaque schemes."""
    data = {
        "entities": [
            {"id": "Acme Corp", "type": "Person"},
            {"id": "mailto:foo", "type": "isbn:0451450523"},
        ],
        "relationships": [
            {"source": "Jane Doe", "target": "Acme Corp", "type": "knows"}
        ],
    }
    ntriples = RDFExporter().export_to_rdf(data, format="ntriples")
    parsed = Graph().parse(data=ntriples, format="nt")

    assert URIRef("https://semantica.dev/ns#Acme%20Corp") in parsed.all_nodes()
    assert URIRef("mailto:foo") in parsed.all_nodes()


def test_turtle_preserves_existing_valid_percent_escapes():
    """A pre-encoded absolute IRI keeps its escape, instead of %20 -> %2520."""
    turtle = RDFExporter().export_to_rdf(
        {
            "entities": [
                {
                    "id": "https://example.org/entities/path%20name",
                    "type": "PERSON",
                }
            ],
            "relationships": [],
        },
        format="turtle",
    )
    parsed = Graph().parse(data=turtle, format="turtle")

    assert (
        URIRef("https://example.org/entities/path%20name"),
        RDF.type,
        URIRef("https://semantica.dev/ns#PERSON"),
    ) in parsed
    assert "%2520" not in turtle


def test_ntriples_and_rdfxml_expand_builtin_prefixes_alongside_context():
    """A user @context must not shadow built-in prefixes like semantica:."""
    data = {
        "@context": {"ex": "https://example.org/"},
        "entities": [{"id": "ORG", "type": "semantica:Entity"}],
        "relationships": [],
    }

    ntriples = RDFExporter().export_to_rdf(data, format="ntriples")
    nt_parsed = Graph().parse(data=ntriples, format="nt")
    assert (
        URIRef("https://semantica.dev/ns#ORG"),
        RDF.type,
        URIRef("https://semantica.dev/ns#Entity"),
    ) in nt_parsed

    rdfxml = RDFExporter().export_to_rdf(data, format="rdfxml")
    xml_parsed = Graph().parse(data=rdfxml, format="xml")
    assert (
        URIRef("https://semantica.dev/ns#ORG"),
        RDF.type,
        URIRef("https://semantica.dev/ns#Entity"),
    ) in xml_parsed
