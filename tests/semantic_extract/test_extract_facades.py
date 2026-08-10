"""Tests for the generic extract_entities / extract_relations facades."""

import pytest

from semantica.semantic_extract.methods import extract_entities, extract_relations


def test_facades_are_exported():
    """Regression for #883: the explorer /api/enrich/extract route imports
    these names directly and previously crashed with a misleading 503."""
    assert callable(extract_entities)
    assert callable(extract_relations)


def test_extract_entities_returns_entities():
    pytest.importorskip("spacy")
    result = extract_entities("Apple CEO Tim Cook announced record earnings.")
    assert isinstance(result, list)
    assert len(result) >= 1


def test_extract_relations_auto_extracts_entities():
    pytest.importorskip("spacy")
    result = extract_relations("Apple CEO Tim Cook announced record earnings.")
    assert isinstance(result, list)
