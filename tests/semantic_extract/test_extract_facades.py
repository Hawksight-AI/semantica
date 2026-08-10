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


def test_extract_relations_reuses_provided_entities(monkeypatch):
    """Regression for Qodo review on #894: when the caller (e.g. the explorer
    /api/enrich/extract route) already extracted entities, the facade must
    forward them instead of re-running NER on the same text."""
    from semantica.semantic_extract import methods
    from semantica.semantic_extract.types import Entity

    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "extract_entities must not be called when entities are provided"
        )

    monkeypatch.setattr(methods, "extract_entities", fail_if_called)

    captured = {}

    class FakeExtractor:
        def __init__(self, confidence_threshold=0.6, **kwargs):
            pass

        def extract_relations(self, text, entities=None, **kwargs):
            captured["text"] = text
            captured["entities"] = entities
            return []

    monkeypatch.setattr(methods, "RelationExtractor", FakeExtractor)

    entities = [Entity(text="Apple", label="ORG", start_char=0, end_char=5, confidence=1.0)]
    methods.extract_relations("Apple", entities=entities)

    assert captured["text"] == "Apple"
    assert captured["entities"] is entities
