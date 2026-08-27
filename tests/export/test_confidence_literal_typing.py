"""
Regression tests for #1100 and #1102.

#1100: the four RDF serializers rendered the same confidence value four
different ways. Turtle wrote it bare, which the Turtle grammar reads as
xsd:decimal. N-Triples typed it xsd:float. RDF/XML wrote a plain literal with
no datatype at all. JSON-LD emitted a native JSON number, which becomes
xsd:double. Those are four distinct RDF terms, so a FILTER matches at most one
of them and merging two exports of one graph yields two confidence values for
the same entity.

#1102: the Turtle path interpolated the value with no type check, so a
non-numeric confidence produced `semantica:confidence high .`, which is not
parseable Turtle. One bad field made the whole export unreadable.
"""

import json

import pytest

rdflib = pytest.importorskip("rdflib")
from rdflib import Graph, URIRef  # noqa: E402
from rdflib.compare import isomorphic  # noqa: E402

from semantica.export.rdf_exporter import RDFSerializer  # noqa: E402

NS = "https://semantica.dev/ns#"
CONFIDENCE = URIRef(NS + "confidence")
XSD_DECIMAL = URIRef("http://www.w3.org/2001/XMLSchema#decimal")


def _kg(confidence):
    entity = {"id": NS + "e1", "text": "Acme", "type": NS + "ORG"}
    if confidence is not _ABSENT:
        entity["confidence"] = confidence
    return {"entities": [entity], "relationships": []}


_ABSENT = object()


def _graphs(kg):
    """Parse every serialization of one KG into a graph, keyed by format."""
    serializer = RDFSerializer()
    out = {}

    out["turtle"] = Graph()
    out["turtle"].parse(data=serializer.serialize_to_turtle(json.loads(json.dumps(kg))),
                        format="turtle")

    out["ntriples"] = Graph()
    out["ntriples"].parse(data=serializer.serialize_to_ntriples(json.loads(json.dumps(kg))),
                          format="nt")

    out["rdfxml"] = Graph()
    out["rdfxml"].parse(data=serializer.serialize_to_rdfxml(json.loads(json.dumps(kg))),
                        format="xml")

    jsonld = serializer.serialize_to_jsonld(json.loads(json.dumps(kg)))
    out["jsonld"] = Graph()
    out["jsonld"].parse(
        data=jsonld if isinstance(jsonld, str) else json.dumps(jsonld), format="json-ld"
    )
    return out


def _confidence_terms(graph):
    return [o for _, p, o in graph if p == CONFIDENCE]


def test_every_serializer_agrees_on_the_confidence_term():
    """The heart of #1100. One value, one RDF term, whatever the format."""
    terms = {}
    for name, graph in _graphs(_kg(0.9)).items():
        values = _confidence_terms(graph)
        assert len(values) == 1, f"{name} emitted {len(values)} confidence triples"
        terms[name] = values[0]

    distinct = set(terms.values())
    assert len(distinct) == 1, (
        "the same confidence serialised as different RDF terms: "
        + ", ".join(f"{k}={v!r} ({v.datatype})" for k, v in terms.items())
    )


def test_the_agreed_term_is_a_typed_decimal():
    for name, graph in _graphs(_kg(0.9)).items():
        term = _confidence_terms(graph)[0]
        assert term.datatype == XSD_DECIMAL, f"{name} typed it {term.datatype}"
        assert str(term) == "0.9", f"{name} wrote the lexical form {str(term)!r}"


def test_turtle_and_ntriples_are_the_same_graph():
    """#1100 as filed: two serializations of one KG must not be two graphs."""
    graphs = _graphs(_kg(0.9))
    assert isomorphic(graphs["turtle"], graphs["ntriples"]), (
        "Turtle only:\n"
        + "\n".join(str(t) for t in set(graphs["turtle"]) - set(graphs["ntriples"]))
        + "\nN-Triples only:\n"
        + "\n".join(str(t) for t in set(graphs["ntriples"]) - set(graphs["turtle"]))
    )


def test_a_numeric_string_is_accepted():
    for name, graph in _graphs(_kg("0.85")).items():
        terms = _confidence_terms(graph)
        assert terms, f"{name} dropped a usable numeric string"
        assert terms[0].datatype == XSD_DECIMAL
        assert str(terms[0]) == "0.85"


def test_an_integer_confidence_is_accepted():
    for name, graph in _graphs(_kg(1)).items():
        terms = _confidence_terms(graph)
        assert terms, f"{name} dropped an integer confidence"
        assert terms[0].datatype == XSD_DECIMAL


def test_a_small_value_is_not_written_in_exponent_notation():
    """1e-05 is a valid Python repr and an invalid xsd:decimal lexical form."""
    for name, graph in _graphs(_kg(0.00001)).items():
        term = _confidence_terms(graph)[0]
        assert "e" not in str(term).lower(), f"{name} wrote {str(term)!r}"
        assert term.value is not None, f"{name} produced an ill-typed literal"


# ── #1102 ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "bad", ["high", "", "not a number", None, True, False, [0.9], {"v": 0.9},
            float("nan"), float("inf")],
)
def test_an_unusable_confidence_never_breaks_the_export(bad):
    """`semantica:confidence high .` made the whole Turtle document unparseable."""
    serializer = RDFSerializer()
    kg = _kg(bad)

    turtle = serializer.serialize_to_turtle(json.loads(json.dumps(kg, default=str)))
    graph = Graph()
    graph.parse(data=turtle, format="turtle")  # must not raise

    assert _confidence_terms(graph) == [], (
        f"{bad!r} was emitted as a confidence value: {_confidence_terms(graph)}"
    )
    # The rest of the entity must survive.
    assert (URIRef(NS + "e1"), URIRef(NS + "text"), rdflib.Literal("Acme")) in graph


def test_an_unusable_confidence_is_dropped_consistently_everywhere():
    for name, graph in _graphs(_kg("high")).items():
        assert _confidence_terms(graph) == [], f"{name} still emitted it"


def test_all_serializers_stay_parseable_with_an_unusable_confidence():
    graphs = _graphs(_kg("high"))  # each parse would raise on malformed output
    assert isomorphic(graphs["turtle"], graphs["ntriples"])


def test_the_emitted_datatype_matches_the_shipped_vocabulary():
    """
    Drift guard. The vocabulary shipped with no rdfs:range on sem:confidence
    precisely because the serializers disagreed. Now that they agree, the range
    is declared, and the two must not drift apart again.
    """
    from rdflib import RDFS

    from semantica.export.rdf_exporter import CONFIDENCE_DATATYPE
    from semantica.ontology.vocabulary import vocabulary_turtle

    vocabulary = Graph()
    vocabulary.parse(data=vocabulary_turtle(), format="turtle")

    declared = list(vocabulary.objects(URIRef(NS + "confidence"), RDFS.range))
    assert declared, "sem:confidence declares no rdfs:range"
    assert str(declared[0]) == CONFIDENCE_DATATYPE, (
        f"vocabulary says {declared[0]}, serializers write {CONFIDENCE_DATATYPE}"
    )


# ── Review findings on the first revision of this fix ────────────────────────

@pytest.mark.parametrize("huge", ["1e100000000", "1E1000000", "-1e999999", 10**400])
def test_an_absurd_magnitude_is_rejected_not_expanded(huge):
    """
    xsd:decimal has no exponent notation, so the value has to be written out.
    "1e100000000" is eleven characters that expand to a hundred million digits,
    and the export path continues past validation errors.
    """
    from semantica.export.rdf_exporter import normalize_confidence

    assert normalize_confidence(huge) is None


def test_a_legitimately_small_confidence_is_still_accepted():
    from semantica.export.rdf_exporter import normalize_confidence

    assert normalize_confidence(1e-9) == "0.000000001"


def test_signed_zero_is_normalized():
    """0.0 and -0.0 would otherwise be two distinct RDF terms."""
    from semantica.export.rdf_exporter import normalize_confidence

    assert normalize_confidence(0.0) == normalize_confidence(-0.0) == "0"


def test_signed_zero_gives_one_term_across_serializers():
    positive = {n: _confidence_terms(g)[0] for n, g in _graphs(_kg(0.0)).items()}
    negative = {n: _confidence_terms(g)[0] for n, g in _graphs(_kg(-0.0)).items()}

    assert set(positive.values()) | set(negative.values()) == set(positive.values())
    assert len(set(positive.values())) == 1
