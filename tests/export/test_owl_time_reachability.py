"""
Regression test for #1106.

`include_temporal=True` emitted a well formed OWL-Time interval hanging off a
relationship IRI that appears nowhere else in the graph. The relationship
itself is written as a single triple, `<e1> <employs> <e2>`, so there is no
node to carry the time and no path from the edge to its validity interval.
The timestamps parsed, validated and meant nothing: no query could reach them
from the relationship they describe.

The JSON-LD path already reifies relationships as sem:Relationship with
sem:source, sem:target and sem:type, and the shipped vocabulary declares all
four terms. Turtle now emits the same shape when it has temporal data to
attach, so the interval hangs off a node the graph can actually reach.
"""

import pytest

rdflib = pytest.importorskip("rdflib")
from rdflib import Graph, RDF, URIRef  # noqa: E402

from semantica.export.rdf_exporter import RDFSerializer  # noqa: E402

NS = "https://semantica.dev/ns#"
TIME = "http://www.w3.org/2006/time#"

E1, E2 = NS + "e1", NS + "e2"
EMPLOYS = NS + "employs"

KG = {
    "entities": [
        {"id": E1, "text": "Acme", "type": NS + "ORG"},
        {"id": E2, "text": "Globex", "type": NS + "ORG"},
    ],
    "relationships": [
        {
            "source_id": E1,
            "target_id": E2,
            "type": EMPLOYS,
            "valid_from": "2024-01-01T00:00:00Z",
            "valid_until": "2025-01-01T00:00:00Z",
        }
    ],
}


def _graph(**options):
    turtle = RDFSerializer().serialize_to_turtle(
        {k: [dict(v) for v in vs] for k, vs in KG.items()}, **options
    )
    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    return graph


def test_the_interval_holder_is_reachable_from_the_graph():
    """The heart of #1106: the node carrying time had no inbound arc at all."""
    graph = _graph(include_temporal=True)
    holders = [s for s, p, _ in graph if str(p) == TIME + "hasTime"]
    assert holders, "no OWL-Time interval was emitted"

    for holder in holders:
        inbound = [(s, p) for s, p, o in graph if o == holder]
        outbound = [(p, o) for s, p, o in graph if s == holder and str(p) != TIME + "hasTime"]
        assert inbound or outbound, (
            f"{holder} carries an interval but nothing else in the graph mentions it"
        )


def test_the_relationship_is_reified_so_time_has_a_subject():
    graph = _graph(include_temporal=True)
    relationships = list(graph.subjects(RDF.type, URIRef(NS + "Relationship")))
    assert len(relationships) == 1, f"expected one reified relationship, got {relationships}"

    node = relationships[0]
    assert (node, URIRef(NS + "source"), URIRef(E1)) in graph
    assert (node, URIRef(NS + "target"), URIRef(E2)) in graph
    assert list(graph.objects(node, URIRef(TIME + "hasTime"))), (
        "the reified relationship does not carry the interval"
    )


def test_a_query_can_walk_from_the_edge_to_its_interval():
    """What the dangling node made impossible."""
    graph = _graph(include_temporal=True)
    rows = list(graph.query(
        """
        PREFIX sem:  <https://semantica.dev/ns#>
        PREFIX time: <http://www.w3.org/2006/time#>
        SELECT ?begin WHERE {
            ?s ?p ?o .
            ?rel sem:source ?s ;
                 sem:target ?o ;
                 time:hasTime/time:hasBeginning/time:inXSDDateTimeStamp ?begin .
        }
        """
    ))
    assert rows, "no path from the relationship to its validity interval"
    assert str(rows[0][0]) == "2024-01-01T00:00:00Z"


def test_the_direct_triple_is_still_written():
    """Reification is added alongside the edge, it does not replace it."""
    graph = _graph(include_temporal=True)
    assert (URIRef(E1), URIRef(EMPLOYS), URIRef(E2)) in graph


def test_default_output_is_unchanged():
    """Nothing is reified when there is no temporal data to attach."""
    graph = _graph()
    assert list(graph.subjects(RDF.type, URIRef(NS + "Relationship"))) == []
    assert (URIRef(E1), URIRef(EMPLOYS), URIRef(E2)) in graph


def test_a_relationship_without_temporal_data_is_not_reified():
    kg = {
        "entities": KG["entities"],
        "relationships": [
            {"source_id": E1, "target_id": E2, "type": EMPLOYS},
            dict(KG["relationships"][0]),
        ],
    }
    turtle = RDFSerializer().serialize_to_turtle(kg, include_temporal=True)
    graph = Graph()
    graph.parse(data=turtle, format="turtle")

    assert len(list(graph.subjects(RDF.type, URIRef(NS + "Relationship")))) == 1


def test_the_reified_terms_are_declared_in_the_shipped_vocabulary():
    """A reification nobody declared would just move the problem."""
    from semantica.ontology.vocabulary import vocabulary_turtle

    vocabulary = Graph()
    vocabulary.parse(data=vocabulary_turtle(), format="turtle")
    declared = {str(s) for s in vocabulary.subjects()}

    graph = _graph(include_temporal=True)
    node = next(iter(graph.subjects(RDF.type, URIRef(NS + "Relationship"))))
    emitted = {str(p) for p in graph.predicates(node, None)} | {NS + "Relationship"}

    undeclared = {t for t in emitted if t.startswith(NS) and t not in declared}
    assert not undeclared, f"emitted but not declared in the vocabulary: {undeclared}"


# ── Review finding on the first revision of this fix ─────────────────────────

def test_the_reified_type_keeps_the_full_predicate():
    """
    Truncating to the local name made two predicates from different namespaces
    indistinguishable, and disagreed with the direct triple beside it.
    """
    from rdflib import Literal

    def reified_type(rel_type):
        kg = {
            "entities": KG["entities"],
            "relationships": [
                {
                    "source_id": E1,
                    "target_id": E2,
                    "type": rel_type,
                    "valid_from": "2024-01-01T00:00:00Z",
                }
            ],
        }
        graph = Graph()
        graph.parse(
            data=RDFSerializer().serialize_to_turtle(kg, include_temporal=True),
            format="turtle",
        )
        node = next(iter(graph.subjects(RDF.type, URIRef(NS + "Relationship"))))
        return set(graph.objects(node, URIRef(NS + "type")))

    a = reified_type("https://a.example/ns#employs")
    b = reified_type("https://b.example/ns#employs")

    assert a == {Literal("https://a.example/ns#employs")}, a
    assert a != b, "two distinct predicates produced the same reified type"


def test_the_reified_type_matches_the_direct_triples_predicate():
    from rdflib import Literal

    graph = _graph(include_temporal=True)
    node = next(iter(graph.subjects(RDF.type, URIRef(NS + "Relationship"))))

    assert set(graph.objects(node, URIRef(NS + "type"))) == {Literal(EMPLOYS)}
    assert (URIRef(E1), URIRef(EMPLOYS), URIRef(E2)) in graph


# ── Qodo review: temporal bounds are str-only at the escape helper ─────────

def test_datetime_bounds_do_not_crash_the_turtle_export():
    """_escape_literal is str-only; datetime bounds must be stringified, not
    run through .replace(). Regression for Qodo high-priority finding #2 on
    PR #1221.

    Also asserts the lexical form: xsd:dateTimeStamp requires an ISO 8601 "T"
    separator (e.g. 2024-01-01T00:00:00+00:00). plain str() emits a space
    ("2024-01-01 00:00:00+00:00"), which is format-invalid; isoformat() fixes
    it. Regression for the maintainer review on PR #1221."""
    from datetime import datetime, timezone

    kg = {
        "entities": [dict(e) for e in KG["entities"]],
        "relationships": [
            {
                "source_id": E1,
                "target_id": E2,
                "type": EMPLOYS,
                "valid_from": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2025, 1, 1, tzinfo=timezone.utc),
            }
        ],
    }
    turtle = RDFSerializer().serialize_to_turtle(kg, include_temporal=True)
    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    stamps = {
        str(o) for o in graph.objects(None, URIRef(TIME + "inXSDDateTimeStamp"))
    }
    assert len(stamps) == 2, stamps
    assert "2024-01-01T00:00:00+00:00" in stamps, stamps
    assert "2025-01-01T00:00:00+00:00" in stamps, stamps


def test_end_only_interval_does_not_crash_the_turtle_export():
    """A valid_until bound with no valid_from passes None as from_val; it must
    not be handed to the str-only escaper. Regression for Qodo finding #2."""
    kg = {
        "entities": [dict(e) for e in KG["entities"]],
        "relationships": [
            {
                "source_id": E1,
                "target_id": E2,
                "type": EMPLOYS,
                "valid_until": "2025-01-01T00:00:00Z",
            }
        ],
    }
    turtle = RDFSerializer().serialize_to_turtle(kg, include_temporal=True)
    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    assert list(graph.subjects(RDF.type, URIRef(TIME + "Instant")))
