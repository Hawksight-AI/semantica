"""Tests for RDFExporter format alias resolution (issue #355)."""

import pytest

from semantica.export import RDFExporter

RDF_DATA = {
    "entities": [
        {"id": "e1", "text": "Apple Inc.", "type": "ORG", "confidence": 0.95},
        {"id": "e2", "text": "Steve Jobs", "type": "PERSON", "confidence": 0.97},
    ],
    "relationships": [
        {"source_id": "e2", "target_id": "e1", "type": "founded_by", "confidence": 0.91},
    ],
}


@pytest.fixture
def exporter():
    return RDFExporter()


def test_ttl_alias_produces_same_output_as_turtle(exporter):
    """format='ttl' must produce identical output to format='turtle'."""
    result_turtle = exporter.export_to_rdf(RDF_DATA, format="turtle")
    result_ttl = exporter.export_to_rdf(RDF_DATA, format="ttl")
    assert result_ttl == result_turtle


def test_nt_alias_produces_same_output_as_ntriples(exporter):
    result_canonical = exporter.export_to_rdf(RDF_DATA, format="ntriples")
    result_alias = exporter.export_to_rdf(RDF_DATA, format="nt")
    assert result_alias == result_canonical


def test_xml_alias_produces_same_output_as_rdfxml(exporter):
    result_canonical = exporter.export_to_rdf(RDF_DATA, format="rdfxml")
    result_alias = exporter.export_to_rdf(RDF_DATA, format="xml")
    assert result_alias == result_canonical


def test_rdf_alias_produces_same_output_as_rdfxml(exporter):
    result_canonical = exporter.export_to_rdf(RDF_DATA, format="rdfxml")
    result_alias = exporter.export_to_rdf(RDF_DATA, format="rdf")
    assert result_alias == result_canonical


def test_json_ld_alias_produces_same_output_as_jsonld(exporter):
    result_canonical = exporter.export_to_rdf(RDF_DATA, format="jsonld")
    result_alias = exporter.export_to_rdf(RDF_DATA, format="json-ld")
    assert result_alias == result_canonical


def test_canonical_formats_unaffected(exporter):
    """Existing canonical format names must continue to work."""
    # n3 is listed in supported_formats but has no serializer implementation yet
    for fmt in ("turtle", "rdfxml", "jsonld", "ntriples"):
        result = exporter.export_to_rdf(RDF_DATA, format=fmt)
        assert result is not None and len(result) > 0


def test_unsupported_format_raises(exporter):
    from semantica.utils.exceptions import ValidationError

    with pytest.raises(ValidationError):
        exporter.export_to_rdf(RDF_DATA, format="parquet")


def test_ttl_export_to_file(exporter, tmp_path):
    out = tmp_path / "output.ttl"
    exporter.export(RDF_DATA, str(out), format="ttl")
    assert out.exists()
    assert out.stat().st_size > 0


def test_non_string_format_raises_validation_error(exporter):
    """format=None or non-string must raise ValidationError, not AttributeError."""
    from semantica.utils.exceptions import ValidationError

    with pytest.raises(ValidationError):
        exporter.export_to_rdf(RDF_DATA, format=None)

    with pytest.raises(ValidationError):
        exporter.export_to_rdf(RDF_DATA, format=123)


def test_validate_rdf_returns_overall_valid_key(exporter):
    """validate_rdf() must return 'overall_valid' key (used in notebook example)."""
    result = exporter.validate_rdf(RDF_DATA)
    assert "overall_valid" in result
    assert isinstance(result["overall_valid"], bool)


# --- Regression tests for #1097 -------------------------------------------
# convert_kg_to_rdf() normalizes an entity's 'name' into 'label'/'text' but was
# never called from the export path, so GraphBuilder graphs (which emit 'name')
# exported with an empty semantica:text on every RDF format. These tests assert
# the human-readable label survives export on all four serializers.

NAME_ONLY_DATA = {
    "entities": [
        {
            "id": "https://example.org/acme",
            "name": "Acme Corp",
            "type": "https://example.org/Org",
            "confidence": 0.91,
        },
    ],
    "relationships": [],
}


@pytest.mark.parametrize("fmt", ["turtle", "ntriples", "rdfxml", "jsonld"])
def test_name_only_entity_exports_nonempty_label(exporter, fmt):
    """A GraphBuilder-style 'name'-only entity must export a non-empty label.

    Regression for #1097: previously every RDF path dropped the label because
    convert_kg_to_rdf() was never invoked from export_to_rdf().
    """
    result = exporter.export_to_rdf(NAME_ONLY_DATA, format=fmt)
    assert "Acme Corp" in result
    # The empty-text pattern that the bug produced must not appear.
    assert 'semantica:text ""' not in result


def test_name_only_export_to_file_contains_label(exporter, tmp_path):
    """The file-writing entry point must also normalize name -> label (#1097)."""
    out = tmp_path / "acme.ttl"
    exporter.export(NAME_ONLY_DATA, str(out), format="turtle")
    content = out.read_text()
    assert "Acme Corp" in content
    assert 'semantica:text ""' not in content


def test_existing_text_not_overwritten_by_name(exporter):
    """An entity that already has 'text' must keep it, not be clobbered by 'name' (#1097)."""
    data = {
        "entities": [
            {
                "id": "https://example.org/acme",
                "name": "Acme Corp",
                "text": "Explicit Text",
                "type": "https://example.org/Org",
            }
        ],
        "relationships": [],
    }
    result = exporter.export_to_rdf(data, format="turtle")
    assert "Explicit Text" in result
    assert "Acme Corp" not in result


def test_id_fallback_label_when_no_name(exporter):
    """With neither 'name' nor 'text', the id local-name is used as label (#1097)."""
    data = {
        "entities": [
            {"id": "https://example.org/acme", "type": "https://example.org/Org"}
        ],
        "relationships": [],
    }
    result = exporter.export_to_rdf(data, format="turtle")
    assert 'semantica:text ""' not in result
    # The label must be the URI local name 'acme', not '//example.org/acme'.
    assert 'semantica:text "acme"' in result


@pytest.mark.parametrize(
    "identifier,expected",
    [
        ("https://example.org/acme", "acme"),
        ("https://example.org/path/acme", "acme"),
        ("https://example.org/onto#acme", "acme"),
        ("https://example.org/acme/", "acme"),
        ("urn:example:acme", "acme"),
        ("semantica:acme", "acme"),
        ("acme", "acme"),
    ],
)
def test_id_fallback_local_name_extraction(exporter, identifier, expected):
    """The id fallback must extract a URI-aware local name, not a colon split (#1113)."""
    data = {
        "entities": [{"id": identifier, "type": "https://example.org/Org"}],
        "relationships": [],
    }
    result = exporter.export_to_rdf(data, format="turtle")
    assert f'semantica:text "{expected}"' in result


def _export(exporter, name, fmt):
    data = {
        "entities": [
            {"id": "https://example.org/e1", "name": name, "type": "ORG"}
        ],
        "relationships": [],
    }
    return exporter.export_to_rdf(data, format=fmt)


def test_turtle_escapes_quotes_and_control_chars(exporter):
    """Turtle literals must escape quotes/backslashes/newlines (#1113 security)."""
    result = _export(exporter, 'Acme "Best" \\ Corp\nLine2\tTab\rCR', "turtle")
    # The raw closing-quote breakout must not appear inside the literal.
    assert '"Acme "Best"' not in result
    assert '\\"Best\\"' in result
    assert "\\\\ Corp" in result
    assert "\\n" in result and "\\t" in result and "\\r" in result
    # No unescaped newline leaked into the literal value.
    assert "Line2" in result and "\nLine2" not in result.split("semantica:text")[1]


def test_ntriples_escapes_quotes_and_control_chars(exporter):
    """N-Triples literals must escape backslash first, then quotes/controls (#1113)."""
    result = _export(exporter, 'Quote " Back \\ New\nTab\t', "ntriples")
    assert '\\"' in result
    assert "\\\\" in result
    assert "\\n" in result and "\\t" in result
    # Each triple must be a single physical line: the literal value carrying the
    # escaped text must not have leaked a bare newline that splits it in two.
    text_lines = [ln for ln in result.splitlines() if "Quote" in ln]
    assert len(text_lines) == 1
    assert text_lines[0].rstrip().endswith(" .")


def test_rdfxml_escapes_markup(exporter):
    """RDF/XML character data must escape &, <, > so names cannot inject markup (#1113)."""
    result = _export(exporter, 'Acme <script>&"x"', "rdfxml")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "&amp;" in result
    # The document must still parse as well-formed XML.
    import xml.dom.minidom

    xml.dom.minidom.parseString(result)


def test_turtle_output_is_parseable_with_special_name(exporter):
    """A name full of metacharacters must still yield parseable Turtle (#1113)."""
    rdflib = pytest.importorskip("rdflib")
    result = _export(exporter, 'Tricky "quote" \\ and <angle> & amp', "turtle")
    graph = rdflib.Graph()
    # Should not raise a parser error.
    graph.parse(data=result, format="turtle")
