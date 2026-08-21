"""Timestamps that leave the process must carry a timezone (issue #1114).

Every timestamp an exporter wrote was naive: ``datetime.now().isoformat()``
reads the local clock, ``datetime.utcnow().isoformat()`` reads UTC, and the two
serialize identically, so nothing downstream can tell which zone a value belongs
to. In RDF the consequence is not a parse error but a silent one: under XSD 1.1
a value with no timezone compared against one with a timezone is indeterminate
whenever they fall inside the +/-14 hour window, SPARQL turns that into an error,
and FILTER discards errors as non-matches. A timezone-qualified query therefore
returns an answer with every Semantica-written record quietly missing from it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from semantica.export.json_exporter import JSONExporter
from semantica.export.report_generator import ReportGenerator
from semantica.export.yaml_exporter import SemanticNetworkYAMLExporter
from semantica.utils.helpers import utc_now, utc_now_iso

KG = {
    "entities": [{"id": "https://example.org/e1", "text": "Bob"}],
    "relationships": [],
}


def assert_offset_aware(value):
    """An ISO 8601 string is only an instant if it says which zone it is in."""
    assert isinstance(value, str), value
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"timezone-naive timestamp: {value!r}"
    assert parsed.utcoffset() is not None


def test_utc_now_iso_is_offset_aware():
    assert_offset_aware(utc_now_iso())
    assert utc_now().tzinfo is not None


def test_jsonld_export_timestamp_is_offset_aware():
    document = JSONExporter()._convert_kg_to_jsonld(KG)
    assert_offset_aware(document["semantica:exportedAt"])


def test_json_export_metadata_timestamp_is_offset_aware(tmp_path):
    import json

    exporter = JSONExporter()
    exporter.export_entities(KG["entities"], tmp_path / "entities.json")
    exporter.export_relationships([], tmp_path / "relationships.json")

    for name in ("entities.json", "relationships.json"):
        payload = json.loads((tmp_path / name).read_text())
        assert_offset_aware(payload["metadata"]["exported_at"])


def test_yaml_export_timestamp_is_offset_aware():
    yaml = pytest.importorskip("yaml")

    document = SemanticNetworkYAMLExporter().export_entities(KG["entities"])
    payload = yaml.safe_load(document)
    assert_offset_aware(payload["metadata"]["exported_at"])


def test_report_timestamp_is_offset_aware():
    import json

    report = json.loads(
        ReportGenerator().generate_quality_report({"score": 0.9}, format="json")
    )
    assert_offset_aware(report["generated_at"])


def test_exported_timestamp_compares_against_a_timezone_aware_instant():
    """The naive form raised TypeError here, or compared as if it were UTC."""
    exported = datetime.fromisoformat(
        JSONExporter()._convert_kg_to_jsonld(KG)["semantica:exportedAt"]
    )
    assert exported <= utc_now()
    assert exported > datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_exported_timestamp_survives_a_timezone_qualified_sparql_filter():
    """The regression in #1114: a strict engine dropped the naive value."""
    pyoxigraph = pytest.importorskip("pyoxigraph")

    exported = JSONExporter()._convert_kg_to_jsonld(KG)["semantica:exportedAt"]
    store = pyoxigraph.Store()
    store.load(
        (
            '<https://example.org/export> '
            '<https://semantica.dev/ns#exportedAt> '
            f'"{exported}"^^<http://www.w3.org/2001/XMLSchema#dateTime> .'
        ).encode(),
        format=pyoxigraph.RdfFormat.N_TRIPLES,
    )
    # The bound has to sit inside the +/-14 hour window that makes an
    # untimezoned comparison indeterminate. A bound years away is determinate
    # even for a naive value, and the test would pass without the fix.
    bound = (utc_now() + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    rows = list(store.query(
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> "
        "SELECT ?e WHERE { ?e <https://semantica.dev/ns#exportedAt> ?t . "
        f'FILTER (?t < "{bound}"^^xsd:dateTime) }}'
    ))
    assert len(rows) == 1, "the export was dropped by a timezone-qualified filter"


def test_document_iri_carrying_an_offset_is_a_valid_iri():
    """The offset puts '+' and ':' in the @id; both are legal in a path."""
    rdflib = pytest.importorskip("rdflib")

    document_iri = JSONExporter()._convert_kg_to_jsonld(KG)["@id"]
    assert "+00:00" in document_iri
    assert rdflib.term._is_valid_uri(document_iri)

    graph = rdflib.Graph()
    graph.add((
        rdflib.URIRef(document_iri),
        rdflib.RDF.type,
        rdflib.URIRef("https://semantica.dev/ns#KnowledgeGraph"),
    ))
    reparsed = rdflib.Graph().parse(data=graph.serialize(format="nt"), format="nt")
    assert document_iri in {str(s) for s in reparsed.subjects()}


def test_vocabulary_range_matches_what_the_exporter_writes():
    """The declared range says the offset is required; the export must carry it."""
    rdflib = pytest.importorskip("rdflib")
    from rdflib.namespace import RDFS, XSD

    from semantica.ontology.vocabulary import NAMESPACE, vocabulary_turtle

    graph = rdflib.Graph()
    graph.parse(data=vocabulary_turtle(), format="turtle")
    declared = graph.value(rdflib.URIRef(f"{NAMESPACE}exportedAt"), RDFS.range)
    assert declared == XSD.dateTimeStamp

    exported = JSONExporter()._convert_kg_to_jsonld(KG)["semantica:exportedAt"]
    assert datetime.fromisoformat(exported).utcoffset() is not None
