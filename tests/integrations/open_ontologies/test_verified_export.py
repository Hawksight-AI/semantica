"""Verified RDF export: an independent engine reads the file back.

The case that matters is the first one. Semantica's GraphBuilder defaults an
entity's id to its surface text, so the documented path emits `<Acme Corp> a
<ORG>`, and a space is not allowed in an IRI. rdflib parses it anyway by
resolving against the working directory; Oxigraph refuses it. A pipeline that
writes a file which parses nowhere has not succeeded, and this is the check
that says so before anything downstream reads it.

These tests are also the regression guard for #1108: until #1127, the registry
caught every exception from a custom method and fell back to the default, so a
gate that rejected the export and deleted the file was followed by the default
writing it straight back. Test one asserts the file is gone.
"""

import pytest

pytest.importorskip("open_ontologies_lite")

from integrations.open_ontologies import (  # noqa: E402
    VerificationError,
    register,
    verified_export_rdf,
    verify_rdf,
)

# The shape GraphBuilder actually produces: id defaults to the surface text,
# type to the extractor's label.
UNSOUND = {
    "entities": [{"id": "Acme Corp", "text": "Acme Corp", "type": "ORG"}],
    "relationships": [],
}

SOUND = {
    "entities": [
        {
            "id": "https://example.org/acme",
            "text": "Acme Corp",
            "type": "https://example.org/Org",
        }
    ],
    "relationships": [],
}

VOCAB = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix ex:   <https://example.org/> .
ex:Org a owl:Class .
"""

# Targets a namespace the data never uses, which is the defect that makes a
# validator report a pass having examined nothing.
SHAPES_THAT_MATCH_NOTHING = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/shapes/> .
ex:PersonShape a sh:NodeShape ;
    sh:targetClass ex:Person ;
    sh:property [ sh:path ex:name ; sh:minCount 1 ] .
"""


def test_an_unsound_export_raises_and_leaves_no_file(tmp_path):
    path = tmp_path / "graph.ttl"
    with pytest.raises(VerificationError) as excinfo:
        verified_export_rdf(UNSOUND, str(path))
    assert "Invalid IRI" in str(excinfo.value) or "not valid RDF" in str(excinfo.value)
    assert not path.exists(), "a failed run must not leave an artifact behind"


def test_the_same_export_succeeds_without_verification(tmp_path):
    """The bytes are unchanged; only the verdict on them is new."""
    from semantica.export.rdf_exporter import RDFExporter

    path = tmp_path / "graph.ttl"
    RDFExporter().export(UNSOUND, path, format="turtle")
    assert path.exists() and path.stat().st_size > 0


def test_a_sound_export_keeps_its_file_and_reports(tmp_path):
    path = tmp_path / "graph.ttl"
    report = verified_export_rdf(SOUND, str(path))
    assert report.ok
    assert report.triples > 0
    assert path.exists()


def test_raise_on_failure_false_keeps_the_file_and_still_reports(tmp_path):
    path = tmp_path / "graph.ttl"
    report = verified_export_rdf(UNSOUND, str(path), raise_on_failure=False)
    assert not report.ok
    assert not report.parses
    assert path.exists(), "surveying a corpus needs the file kept"


def test_a_term_declared_nowhere_is_reported(tmp_path):
    rdf = """
    @prefix ex: <https://example.org/> .
    ex:acme a ex:Org ; ex:hasInventedProperty "x" .
    """
    report = verify_rdf(rdf, ontology=VOCAB, policed_namespaces=["https://example.org/"])
    assert "https://example.org/hasInventedProperty" in report.undeclared_terms
    assert not report.ok


def test_shapes_that_match_nothing_do_not_report_a_pass():
    rdf = """
    @prefix ex: <https://example.org/> .
    ex:acme a ex:Org .
    """
    report = verify_rdf(rdf, shapes=SHAPES_THAT_MATCH_NOTHING)
    assert report.conforms is None, "a vacuous run is not a pass"
    assert report.focus_nodes == 0
    assert report.unmatched_shapes
    assert not report.ok


def test_registration_routes_export_rdf_through_the_gate(tmp_path):
    """The whole point of #1127: a registered method can refuse."""
    from semantica.export.methods import export_rdf

    register()
    path = tmp_path / "graph.ttl"
    with pytest.raises(VerificationError):
        export_rdf(UNSOUND, str(path), method="verified")
    assert not path.exists()


def test_registration_leaves_the_default_method_alone(tmp_path):
    from semantica.export.methods import export_rdf

    register()
    path = tmp_path / "graph.ttl"
    export_rdf(UNSOUND, str(path))
    assert path.exists(), "an existing pipeline must behave exactly as before"
