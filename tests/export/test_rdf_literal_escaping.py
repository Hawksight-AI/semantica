"""Regression tests for #1098: Turtle/N-Triples literal escaping."""
import pytest

from semantica.export.rdf_exporter import RDFSerializer


@pytest.fixture
def serializer():
    return RDFSerializer()


class TestTurtleLiteralEscaping:
    def test_quote_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": 'He said "hello"', "type": "ORG"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert '"He said \\"hello\\""' in turtle

    def test_backslash_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": r"path\to\file", "type": "ORG"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert r"path\\to\\file" in turtle

    def test_newline_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": "line1\nline2", "type": "ORG"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert "line1\\nline2" in turtle

    def test_tab_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": "a\tb", "type": "ORG"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert "a\\tb" in turtle

    def test_plain_text_unchanged(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": "Apple Inc.", "type": "ORG"}],
            "relationships": [],
        }
        turtle = serializer.serialize_to_turtle(kg)
        assert 'semantica:text "Apple Inc."' in turtle


class TestNTriplesLiteralEscaping:
    def test_quote_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": 'He said "hello"', "type": "ORG"}],
            "relationships": [],
        }
        ntriples = serializer.serialize_to_ntriples(kg)
        assert '\\"hello\\"' in ntriples

    def test_backslash_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": r"path\to\file", "type": "ORG"}],
            "relationships": [],
        }
        ntriples = serializer.serialize_to_ntriples(kg)
        assert r"path\\to\\file" in ntriples

    def test_newline_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": "line1\nline2", "type": "ORG"}],
            "relationships": [],
        }
        ntriples = serializer.serialize_to_ntriples(kg)
        assert "line1\\nline2" in ntriples

    def test_tab_in_text_is_escaped(self, serializer):
        kg = {
            "entities": [{"id": "e1", "text": "a\tb", "type": "ORG"}],
            "relationships": [],
        }
        ntriples = serializer.serialize_to_ntriples(kg)
        assert "a\\tb" in ntriples