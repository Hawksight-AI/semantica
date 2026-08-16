'''Regression tests for issue #997.

NERExtractor.__init__ must reuse the process-level spaCy model cache
(methods.load_spacy_model) instead of calling spacy.load() directly, so
constructing many extractors does not reload the same model from disk.
'''

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from semantica.semantic_extract import methods
from semantica.semantic_extract.ner_extractor import NERExtractor


@pytest.fixture(autouse=True)
def clear_cache():
    methods.clear_spacy_model_cache()
    yield
    methods.clear_spacy_model_cache()


def _fake_spacy(load):
    return SimpleNamespace(load=load, util=SimpleNamespace(is_package=lambda name: True))


def test_ner_extractor_loads_model_once_across_instances(monkeypatch):
    calls = []

    def fake_load(name, **kwargs):
        calls.append(name)
        return MagicMock()

    monkeypatch.setattr(methods, "spacy", _fake_spacy(fake_load))
    monkeypatch.setattr(methods, "SPACY_AVAILABLE", True)
    # NERExtractor reads SPACY_AVAILABLE from its own module namespace
    monkeypatch.setattr(
        "semantica.semantic_extract.ner_extractor.SPACY_AVAILABLE", True
    )

    NERExtractor(method="ml", model="en_core_web_sm")
    NERExtractor(method="ml", model="en_core_web_sm")
    NERExtractor(method="ml", model="en_core_web_sm")

    assert calls == ["en_core_web_sm"], "spacy.load should run once per model name"


def test_ner_extractor_distinct_models_cached_separately(monkeypatch):
    calls = []
    monkeypatch.setattr(
        methods,
        "spacy",
        _fake_spacy(lambda name, **kw: (calls.append(name), MagicMock())[1]),
    )
    monkeypatch.setattr(
        "semantica.semantic_extract.ner_extractor.SPACY_AVAILABLE", True
    )

    NERExtractor(method="ml", model="en_core_web_sm")
    NERExtractor(method="ml", model="en_core_web_lg")
    NERExtractor(method="ml", model="en_core_web_sm")

    assert calls == ["en_core_web_sm", "en_core_web_lg"]


def test_ner_extractor_reuses_model_loaded_by_methods(monkeypatch):
    '''A model loaded by extraction functions must be reused by NERExtractor.'''
    calls = []
    monkeypatch.setattr(methods, "spacy", _fake_spacy(lambda name, **kw: (calls.append(name), MagicMock())[1]))
    monkeypatch.setattr(
        "semantica.semantic_extract.ner_extractor.SPACY_AVAILABLE", True
    )

    methods.load_spacy_model("en_core_web_sm")
    NERExtractor(method="ml", model="en_core_web_sm")

    assert calls == ["en_core_web_sm"], "NERExtractor should reuse the cached model"


def test_ner_extractor_missing_model_still_falls_back(monkeypatch):
    '''OSError from the cache must still trigger the existing fallback path.'''
    def failing_load(name, **kwargs):
        raise OSError("Can't find model '" + name + "'")

    monkeypatch.setattr(methods, "spacy", _fake_spacy(failing_load))
    monkeypatch.setattr(
        "semantica.semantic_extract.ner_extractor.SPACY_AVAILABLE", True
    )

    extractor = NERExtractor(method="ml", model="en_core_web_missing")

    assert extractor.nlp is None
    assert extractor._ml_runtime_usable is True  # OSError is the soft fallback
