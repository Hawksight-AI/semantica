"""Tests for the process-level spaCy model cache in semantic_extract.methods.

Before this cache existed, extract_entities_ml(), extract_relations_similarity()
and extract_relations_dependency() called spacy.load() on every invocation, so a
short sentence cost ~120 ms of model loading on top of ~2 ms of actual work.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from semantica.semantic_extract import methods


@pytest.fixture(autouse=True)
def clear_cache():
    methods.clear_spacy_model_cache()
    yield
    methods.clear_spacy_model_cache()


def _fake_spacy(load):
    return SimpleNamespace(load=load, util=SimpleNamespace(is_package=lambda name: True))


def test_model_loaded_once_across_calls(monkeypatch):
    calls = []

    def fake_load(name, **kwargs):
        calls.append(name)
        return MagicMock()

    monkeypatch.setattr(methods, "spacy", _fake_spacy(fake_load))

    methods.load_spacy_model("en_core_web_sm")
    methods.load_spacy_model("en_core_web_sm")
    methods.load_spacy_model("en_core_web_sm")

    assert calls == ["en_core_web_sm"], "spacy.load should run once per model name"


def test_same_object_returned(monkeypatch):
    sentinel = MagicMock()
    monkeypatch.setattr(methods, "spacy", _fake_spacy(lambda name, **kw: sentinel))

    assert methods.load_spacy_model("en_core_web_sm") is sentinel
    assert methods.load_spacy_model("en_core_web_sm") is sentinel


def test_distinct_models_cached_separately(monkeypatch):
    calls = []
    monkeypatch.setattr(
        methods,
        "spacy",
        _fake_spacy(lambda name, **kw: (calls.append(name), MagicMock())[1]),
    )

    methods.load_spacy_model("en_core_web_sm")
    methods.load_spacy_model("en_core_web_lg")
    methods.load_spacy_model("en_core_web_sm")

    assert calls == ["en_core_web_sm", "en_core_web_lg"]


def test_load_errors_propagate_and_are_not_cached(monkeypatch):
    """Callers rely on OSError to trigger their fallback path."""
    attempts = []

    def failing_load(name, **kwargs):
        attempts.append(name)
        raise OSError(f"Can't find model '{name}'")

    monkeypatch.setattr(methods, "spacy", _fake_spacy(failing_load))

    with pytest.raises(OSError):
        methods.load_spacy_model("en_core_web_missing")
    with pytest.raises(OSError):
        methods.load_spacy_model("en_core_web_missing")

    assert len(attempts) == 2, "a failed load must not populate the cache"


def test_cache_ignores_entries_from_a_replaced_spacy_module(monkeypatch):
    """Patching methods.spacy must not hand back a model from the old module.

    Existing tests patch this attribute with a mock and assert on load calls, so
    a cache keyed on model name alone would leak objects across those tests.
    """
    first = MagicMock()
    monkeypatch.setattr(methods, "spacy", _fake_spacy(lambda name, **kw: first))
    assert methods.load_spacy_model("en_core_web_sm") is first

    second = MagicMock()
    monkeypatch.setattr(methods, "spacy", _fake_spacy(lambda name, **kw: second))
    assert methods.load_spacy_model("en_core_web_sm") is second


def test_extract_entities_ml_reuses_the_cached_model(monkeypatch):
    calls = []

    def fake_load(name, **kwargs):
        calls.append(name)
        nlp = MagicMock()
        nlp.return_value = SimpleNamespace(ents=[])
        return nlp

    monkeypatch.setattr(methods, "spacy", _fake_spacy(fake_load))
    monkeypatch.setattr(methods, "SPACY_AVAILABLE", True)

    methods.extract_entities_ml("Alice works at Acme Corp.")
    methods.extract_entities_ml("Bob works at Globex.")

    assert len(calls) == 1, "the model should be loaded once, not once per call"
