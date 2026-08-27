"""
Regression tests for #1103.

OWLExporter read `object_properties` / `data_properties` while OntologyGenerator
emits a single `properties` list, so every generated property was dropped. Class
IRIs arrived as None and were interpolated into `<>`, collapsing every class onto
the empty relative IRI, so an ontology of N classes serialised as one node
carrying N labels.

These tests drive the exporter with what the generator actually produces, and
assert on the parsed graph rather than on the serialised text.
"""

import pytest

rdflib = pytest.importorskip("rdflib")
from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal  # noqa: E402

from semantica.export.owl_exporter import OWLExporter  # noqa: E402
from semantica.ontology.ontology_generator import OntologyGenerator  # noqa: E402

XSD = "http://www.w3.org/2001/XMLSchema#"


@pytest.fixture(scope="module")
def generated_ontology():
    """A real OntologyGenerator run, not a hand-written stand-in."""
    data = {
        "entities": [
            {"type": "Person", "name": "John", "age": 30},
            {"type": "Person", "name": "Jane", "age": 25},
            {"type": "Organization", "name": "Acme"},
            {"type": "Organization", "name": "Globex"},
        ],
        "relationships": [
            {"source": "John", "target": "Acme", "type": "works_at"},
            {"source": "Jane", "target": "Globex", "type": "works_at"},
        ],
    }
    return OntologyGenerator().generate_ontology(data)


@pytest.fixture(scope="module")
def turtle_graph(generated_ontology):
    ttl = OWLExporter()._export_owl_turtle(generated_ontology)
    graph = Graph()
    graph.parse(data=ttl, format="turtle")
    return graph


@pytest.fixture(scope="module")
def xml_graph(generated_ontology):
    xml = OWLExporter()._export_owl_xml(generated_ontology)
    graph = Graph()
    graph.parse(data=xml, format="xml")
    return graph


def test_generator_mints_class_iris(generated_ontology):
    """The `uri` key is present with a None value, so a `not in` guard misses it."""
    classes = generated_ontology["classes"]
    assert classes, "fixture produced no classes"
    for cls in classes:
        assert cls.get("uri"), f"class {cls.get('name')!r} has no URI: {cls.get('uri')!r}"
        assert str(cls["uri"]).startswith("http"), cls["uri"]


def test_every_class_is_a_distinct_absolute_iri(turtle_graph, generated_ontology):
    subjects = set(turtle_graph.subjects(RDF.type, OWL.Class))
    assert len(subjects) == len(generated_ontology["classes"])
    for subject in subjects:
        assert isinstance(subject, URIRef)
        assert str(subject) != "", "class collapsed onto the empty relative IRI"
        assert str(subject).startswith("http"), subject


def test_class_labels_are_not_stacked_on_one_node(turtle_graph):
    """Two classes must not share a subject and pile up two rdfs:label values."""
    for subject in set(turtle_graph.subjects(RDF.type, OWL.Class)):
        labels = list(turtle_graph.objects(subject, RDFS.label))
        assert len(labels) == 1, f"{subject} carries {len(labels)} labels: {labels}"


def test_no_generated_property_is_dropped(turtle_graph, generated_ontology):
    declared = set(turtle_graph.subjects(RDF.type, OWL.ObjectProperty)) | set(
        turtle_graph.subjects(RDF.type, OWL.DatatypeProperty)
    )
    expected = {URIRef(p["uri"]) for p in generated_ontology["properties"]}
    assert expected, "fixture produced no properties"
    assert expected <= declared, f"dropped: {expected - declared}"


def test_properties_keep_their_owl_type(turtle_graph, generated_ontology):
    by_uri = {p["uri"]: p for p in generated_ontology["properties"]}
    for uri, prop in by_uri.items():
        expected = OWL.ObjectProperty if prop["type"] == "object" else OWL.DatatypeProperty
        assert (URIRef(uri), RDF.type, expected) in turtle_graph, (
            f"{prop['name']} ({prop['type']}) is not typed {expected}"
        )


def test_object_property_domain_and_range_are_class_iris(turtle_graph, generated_ontology):
    """The generator emits bare class names; they must resolve, not stay relative."""
    class_iris = {URIRef(c["uri"]) for c in generated_ontology["classes"]}
    obj_props = [p for p in generated_ontology["properties"] if p["type"] == "object"]
    assert obj_props, "fixture produced no object properties"
    for prop in obj_props:
        subject = URIRef(prop["uri"])
        for predicate in (RDFS.domain, RDFS.range):
            values = list(turtle_graph.objects(subject, predicate))
            assert values, f"{prop['name']} has no {predicate}"
            for value in values:
                assert value in class_iris, f"{prop['name']} {predicate} = {value!r}"


def test_data_property_range_is_a_single_well_formed_xsd_iri(turtle_graph, generated_ontology):
    """`rdfs:range xsd:{range}` doubled the prefix when range was already 'xsd:string'."""
    data_props = [p for p in generated_ontology["properties"] if p["type"] != "object"]
    assert data_props, "fixture produced no data properties"
    for prop in data_props:
        ranges = list(turtle_graph.objects(URIRef(prop["uri"]), RDFS.range))
        assert ranges, f"{prop['name']} has no range"
        for value in ranges:
            assert str(value).startswith(XSD), f"{prop['name']} range = {value!r}"
            assert "xsd:" not in str(value), f"doubled prefix: {value!r}"


def test_xml_and_turtle_describe_the_same_ontology(turtle_graph, xml_graph):
    """The two serialisations of one ontology must not be different graphs."""
    def summary(graph):
        return {
            "classes": set(graph.subjects(RDF.type, OWL.Class)),
            "object_properties": set(graph.subjects(RDF.type, OWL.ObjectProperty)),
            "data_properties": set(graph.subjects(RDF.type, OWL.DatatypeProperty)),
        }

    assert summary(turtle_graph) == summary(xml_graph)


def test_explicit_object_and_data_property_keys_still_work():
    """The pre-existing hand-authored shape must keep working."""
    ontology = {
        "uri": "https://example.org/onto/",
        "name": "Hand",
        "classes": [{"uri": "https://example.org/onto/Person", "name": "Person"}],
        "object_properties": [
            {
                "uri": "https://example.org/onto/knows",
                "name": "knows",
                "domain": "https://example.org/onto/Person",
                "range": "https://example.org/onto/Person",
            }
        ],
        "data_properties": [
            {"uri": "https://example.org/onto/age", "name": "age", "range": "integer"}
        ],
    }
    graph = Graph()
    graph.parse(data=OWLExporter()._export_owl_turtle(ontology), format="turtle")

    assert (URIRef("https://example.org/onto/knows"), RDF.type, OWL.ObjectProperty) in graph
    assert (URIRef("https://example.org/onto/age"), RDF.type, OWL.DatatypeProperty) in graph
    assert (
        URIRef("https://example.org/onto/age"),
        RDFS.range,
        URIRef(XSD + "integer"),
    ) in graph


def test_a_class_without_any_identifier_is_skipped_not_emitted_as_empty():
    """An unusable class must not become `<>` and swallow the document IRI."""
    ontology = {
        "uri": "https://example.org/onto/",
        "name": "Partial",
        "classes": [{"comment": "no name, no uri, no id"}],
    }
    graph = Graph()
    graph.parse(data=OWLExporter()._export_owl_turtle(ontology), format="turtle")

    assert set(graph.subjects(RDF.type, OWL.Class)) == set()
    assert (URIRef("https://example.org/onto/"), RDF.type, OWL.Ontology) in graph


# ── Review findings on the first revision of this fix ────────────────────────

def test_a_name_with_a_space_still_mints_a_valid_iri():
    """The name fallback pasted free text onto a base, producing `<... ...>`."""
    import pyoxigraph

    ontology = {
        "uri": "https://example.org/onto/",
        "name": "Spaces",
        "classes": [{"name": "Customer Account"}],
    }
    turtle = OWLExporter()._export_owl_turtle(ontology)

    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    subjects = [str(s) for s in graph.subjects(RDF.type, OWL.Class)]
    assert subjects, "the class was dropped entirely"
    assert " " not in subjects[0], subjects[0]

    # rdflib only warns about a space in an IRI; a strict parser refuses it.
    pyoxigraph.Store().load(
        turtle.encode(), format=pyoxigraph.RdfFormat.TURTLE, base_iri=None
    )


def test_owl_thing_expands_instead_of_becoming_its_own_scheme():
    """`owl:Thing` matches the generic scheme grammar but is a prefixed name."""
    ontology = {
        "uri": "https://example.org/onto/",
        "name": "Thing",
        "classes": [{"name": "Person", "uri": "https://example.org/onto/Person"}],
        "object_properties": [
            {
                "name": "relatedTo",
                "uri": "https://example.org/onto/relatedTo",
                "domain": ["owl:Thing"],
                "range": ["owl:Thing"],
            }
        ],
    }
    graph = Graph()
    graph.parse(data=OWLExporter()._export_owl_turtle(ontology), format="turtle")

    subject = URIRef("https://example.org/onto/relatedTo")
    for predicate in (RDFS.domain, RDFS.range):
        values = [str(v) for v in graph.objects(subject, predicate)]
        assert values == ["http://www.w3.org/2002/07/owl#Thing"], values


def test_the_generators_owl_thing_fallback_round_trips():
    """stage 4 assigns domain/range of ["owl:Thing"], so this is the live path."""
    ontology = {
        "uri": "https://example.org/onto/",
        "name": "Generated",
        "classes": [{"name": "Person", "uri": "https://example.org/onto/Person"}],
        "properties": [
            {"name": "linkedTo", "type": "object", "uri": "https://example.org/onto/linkedTo",
             "domain": ["owl:Thing"], "range": ["owl:Thing"], "@type": "owl:ObjectProperty"}
        ],
    }
    graph = Graph()
    graph.parse(data=OWLExporter()._export_owl_turtle(ontology), format="turtle")

    assert (
        URIRef("https://example.org/onto/linkedTo"),
        RDFS.domain,
        URIRef("http://www.w3.org/2002/07/owl#Thing"),
    ) in graph


def test_optimizing_a_class_without_a_uri_does_not_raise():
    """improve_coherence lives on OntologyOptimizer, which owns no namespace manager."""
    from semantica.ontology.ontology_generator import OntologyOptimizer

    result = OntologyOptimizer().improve_coherence(
        {"uri": "https://example.org/onto/", "classes": [{"name": "Person"}], "properties": []}
    )
    minted = result["classes"][0]["uri"]
    assert minted.startswith("https://example.org/onto/"), minted
    assert " " not in minted


def test_optimizing_falls_back_to_a_base_when_the_ontology_has_no_uri():
    from semantica.ontology.ontology_generator import OntologyOptimizer

    result = OntologyOptimizer().improve_coherence(
        {"classes": [{"name": "Customer Account"}], "properties": []}
    )
    minted = result["classes"][0]["uri"]
    assert minted.startswith("http"), minted
    assert " " not in minted, minted


def test_unusable_property_entries_are_reported_not_silently_dropped(caplog):
    import logging

    ontology = {
        "uri": "https://example.org/onto/",
        "name": "Malformed",
        "classes": [],
        "properties": ["not a dict", {"name": "untyped", "uri": "https://example.org/onto/untyped"}],
    }
    with caplog.at_level(logging.WARNING):
        OWLExporter()._export_owl_turtle(ontology)

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "not dictionaries" in messages or "not\ndictionaries" in messages or "dictionaries" in messages
    assert "untyped" in messages
