"""Regression tests for RDF literal export (issues #1097, #1098).

- #1097: convert_kg_to_rdf() was never called, so entities carrying `name`
  (as GraphBuilder emits) exported as semantica:text "".
- #1098: literal values were interpolated unescaped, so a quote or newline in
  entity text produced syntactically invalid Turtle.
"""
import pytest

from semantica.export.rdf_exporter import RDFSerializer


@pytest.fixture
def serializer():
    return RDFSerializer()


class TestNameToTextMapping:
    def test_entity_with_name_exports_text(self, serializer):
        kg = {
            "entities": [{"id": "e1", "name": "Alice", "type": "Person"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert 'semantica:text "Alice"' in turtle

    def test_entity_with_name_uses_label_fallback(self, serializer):
        kg = {
            "entities": [{"id": "e1", "name": "Alice", "label": "A. L.", "type": "Person"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert 'semantica:text "A. L."' in turtle


class TestLiteralEscaping:
    def test_quote_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": 'say "hi"', "type": "Person"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert 'semantica:text "say \\"hi\\""' in turtle

    def test_newline_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": "line one\nline two", "type": "Person"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert 'semantica:text "line one\\nline two"' in turtle

    def test_backslash_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": "C:\\path", "type": "Person"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert 'semantica:text "C:\\\\path"' in turtle

    def test_plain_text_unchanged(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": "Apple Inc.", "type": "ORG"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert 'semantica:text "Apple Inc."' in turtle


class TestNameMappingAcrossFormats:
    def test_rdfxml_entity_with_name_exports_text(self, serializer):
        kg = {
            "entities": [{"id": "e1", "name": "Alice", "type": "Person"}],
            "relationships": [],
        }
        rdfxml = serializer.serialize_to_rdfxml(kg)
        assert "<semantica:text>Alice</semantica:text>" in rdfxml

    def test_ntriples_entity_with_name_exports_text(self, serializer):
        kg = {
            "entities": [{"id": "e1", "name": "Alice", "type": "Person"}],
            "relationships": [],
        }
        ntriples = serializer.serialize_to_ntriples(kg)
        assert '<https://semantica.dev/ns#text> "Alice"' in ntriples

    def test_jsonld_entity_with_name_exports_text(self, serializer):
        kg = {
            "entities": [{"id": "e1", "name": "Alice", "type": "Person"}],
            "relationships": [],
        }
        jsonld = serializer.serialize_to_jsonld(kg)
        assert '"semantica:text": "Alice"' in jsonld
