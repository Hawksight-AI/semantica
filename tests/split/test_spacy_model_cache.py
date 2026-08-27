from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from semantica.semantic_extract import methods as se_methods
from semantica.split import methods as split_methods
from semantica.split import semantic_chunker
from semantica.semantic_extract import ner_extractor as ner_extractor_module
from semantica.semantic_extract.ner_extractor import NERExtractor


@pytest.fixture(autouse=True)
def clear_cache():
    se_methods.clear_spacy_model_cache()
    yield
    se_methods.clear_spacy_model_cache()


@pytest.fixture(autouse=True)
def force_spacy_available(monkeypatch):
    # split.methods, split.semantic_chunker, and ner_extractor each compute
    # their own SPACY_AVAILABLE flag from the real environment at import time;
    # force all true so these tests exercise the spaCy branch regardless of
    # whether spaCy is actually installed where they run.
    monkeypatch.setattr(split_methods, "SPACY_AVAILABLE", True)
    monkeypatch.setattr(semantic_chunker, "SPACY_AVAILABLE", True)
    monkeypatch.setattr(ner_extractor_module, "SPACY_AVAILABLE", True)


def _fake_spacy(load):
    return SimpleNamespace(
        load=load,
        util=SimpleNamespace(is_package=lambda _name: True),
    )


def _nlp_mock(sentences=("Hello world.",)):
    """A stand-in spaCy Language object: callable, returns a doc with .sents."""
    nlp = MagicMock()
    nlp.return_value = SimpleNamespace(
        sents=[SimpleNamespace(text=s) for s in sentences]
    )
    return nlp


class TestSpacyModelCache:
    """split.methods and split.semantic_chunker must share the cached model
    defined in semantic_extract.methods instead of each calling spacy.load()
    independently.
    """

    def test_split_by_sentences_reuses_cached_model(self, monkeypatch):
        calls = []

        def fake_load(name, **kwargs):
            calls.append((name, kwargs))
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        split_methods.split_by_sentences("Hello world. Bye world.")
        split_methods.split_by_sentences("Another sentence here.")
        split_methods.split_by_sentences("A third call.")

        assert len(calls) == 1, "spacy.load should run once, not once per call"
        assert calls[0][0] == "en_core_web_sm"

    def test_semantic_chunker_reuses_cached_model_across_instances(self, monkeypatch):
        calls = []

        def fake_load(name, **kwargs):
            calls.append((name, kwargs))
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        chunker1 = semantic_chunker.SemanticChunker()
        chunker2 = semantic_chunker.SemanticChunker()

        assert len(calls) == 1, "each new SemanticChunker should not reload the model"
        assert chunker1.nlp is chunker2.nlp

    def test_split_methods_and_semantic_chunker_share_the_cache(self, monkeypatch):
        calls = []

        def fake_load(name, **kwargs):
            calls.append((name, kwargs))
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        split_methods.split_by_sentences("Test sentence for split.methods.")
        semantic_chunker.SemanticChunker()

        assert len(calls) == 1, (
            "split.methods and split.semantic_chunker must share one cached "
            "model instead of each loading their own"
        )

    def test_distinct_model_names_load_separately(self, monkeypatch):
        calls = []

        def fake_load(name, **kwargs):
            calls.append((name, kwargs))
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        sm_chunker = semantic_chunker.SemanticChunker(model="en_core_web_sm")
        lg_chunker = semantic_chunker.SemanticChunker(model="en_core_web_lg")
        sm_chunker_again = semantic_chunker.SemanticChunker(model="en_core_web_sm")

        assert [name for name, _ in calls] == ["en_core_web_sm", "en_core_web_lg"]
        assert sm_chunker.nlp is sm_chunker_again.nlp
        assert sm_chunker.nlp is not lg_chunker.nlp

    def test_no_disable_kwarg_requested(self, monkeypatch):
        """split.methods and split.semantic_chunker both want the full
        pipeline (they need .sents, which requires the parser/senter). If
        either one later starts requesting a trimmed pipeline (e.g.
        disable=["ner"]), the name-only cache key in load_spacy_model would
        silently hand back a cached model built for a different config --
        this test should catch that the moment it happens.
        """
        calls = []

        def fake_load(_name, **kwargs):
            calls.append(kwargs)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        split_methods.split_by_sentences("Hello world.")
        se_methods.clear_spacy_model_cache()
        semantic_chunker.SemanticChunker()

        assert len(calls) == 2
        assert all(kwargs == {} for kwargs in calls), (
            "neither caller should pass any pipeline-configuration kwargs; "
            "the name-only cache key in load_spacy_model cannot distinguish "
            "models loaded with different component configs"
        )

    def test_missing_model_falls_back_without_poisoning_cache(self, monkeypatch):
        attempts = []

        def failing_load(name, **_kwargs):
            attempts.append(name)
            raise OSError(f"Can't find model '{name}'")

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(failing_load))

        # split_by_sentences should fall back to regex splitting, not raise
        chunks = split_methods.split_by_sentences("Hello world. Bye world.")
        assert chunks, "fallback splitting should still produce chunks"

        # SemanticChunker should leave .nlp as None rather than propagate
        chunker = semantic_chunker.SemanticChunker()
        assert chunker.nlp is None

        assert len(attempts) == 2, "a failed load must not be cached"

        # Once the model is available, both callers should now get it, and
        # share a single successful load.
        def working_load(name, **_kwargs):
            attempts.append(name)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(working_load))

        chunker2 = semantic_chunker.SemanticChunker()
        split_methods.split_by_sentences("One more sentence.")

        assert len(attempts) == 3, (
            "the model should load once after it becomes available"
        )
        assert chunker2.nlp is not None

    def test_semantic_chunker_falls_back_when_spacy_runtime_is_broken(
        self, monkeypatch
    ):
        """A spaCy model that is installed but unusable at runtime (e.g. a
        config incompatible with the installed spaCy version) must degrade
        SemanticChunker to fallback chunking, not crash __init__ -- mirrors
        TestNERExtractorSpacyModelCache's equivalent broken-runtime test.
        """

        def broken_load(name, **_kwargs):
            raise RuntimeError("ConfigSchemaNlp is not fully defined")

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(broken_load))

        chunker = semantic_chunker.SemanticChunker()

        assert chunker.nlp is None


class TestNERExtractorSpacyModelCache:
    """NERExtractor(method="ml") must reuse the centralized cache in
    semantic_extract.methods, not call spacy.load() on every construction.

    These tests mirror TestSpacyModelCache but focus on the NERExtractor path,
    confirming that all three callers (split_by_sentences, SemanticChunker, and
    NERExtractor) draw from the same process-level cache.
    """

    def test_ner_extractor_reuses_cached_model_across_instances(self, monkeypatch):
        """Two NERExtractor(method='ml') constructions with the same model name
        must cause exactly one underlying spacy.load() call."""
        calls = []

        def fake_load(name, **kwargs):
            calls.append(name)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        e1 = NERExtractor(method="ml")
        e2 = NERExtractor(method="ml")
        e3 = NERExtractor(method="ml", model="en_core_web_sm")

        assert len(calls) == 1, (
            "repeated NERExtractor constructions should not reload the model"
        )
        assert e1.nlp is e2.nlp is e3.nlp

    def test_ner_extractor_and_split_callers_share_one_cached_model(self, monkeypatch):
        """NERExtractor, SemanticChunker, and split_by_sentences must all use
        the same cached Language object for the same model name."""
        calls = []

        def fake_load(name, **kwargs):
            calls.append(name)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        split_methods.split_by_sentences("First sentence.")
        semantic_chunker.SemanticChunker()
        NERExtractor(method="ml")

        assert len(calls) == 1, (
            "split_by_sentences, SemanticChunker, and NERExtractor must share "
            "one cached model instead of each loading their own"
        )

    def test_ner_extractor_distinct_model_names_load_separately(self, monkeypatch):
        """Different model names must produce separate cache entries."""
        calls = []

        def fake_load(name, **kwargs):
            calls.append(name)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        sm = NERExtractor(method="ml", model="en_core_web_sm")
        lg = NERExtractor(method="ml", model="en_core_web_lg")
        sm_again = NERExtractor(method="ml", model="en_core_web_sm")

        assert calls == ["en_core_web_sm", "en_core_web_lg"]
        assert sm.nlp is sm_again.nlp
        assert sm.nlp is not lg.nlp

    def test_ner_extractor_failed_load_not_cached_and_retried(self, monkeypatch):
        """A missing model must not poison the cache.  A subsequent construction
        after the model becomes available must succeed and share the loaded model."""
        attempts = []

        def failing_load(name, **_kwargs):
            attempts.append(name)
            raise OSError(f"Can't find model '{name}'")

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(failing_load))

        # Construction with missing model: nlp must remain None, no crash
        extractor1 = NERExtractor(method="ml")
        assert extractor1.nlp is None
        assert len(attempts) == 1, "one load attempt expected for the missing model"

        # Second construction: must retry (cache must not hold the failure)
        extractor2 = NERExtractor(method="ml")
        assert extractor2.nlp is None
        assert len(attempts) == 2, "a failed load must not be cached"

        # Now install a working model and verify recovery
        def working_load(name, **_kwargs):
            attempts.append(name)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(working_load))

        extractor3 = NERExtractor(method="ml")
        extractor4 = NERExtractor(method="ml")

        assert extractor3.nlp is not None
        assert extractor3.nlp is extractor4.nlp
        assert len(attempts) == 3, (
            "exactly one successful load expected after the model becomes available"
        )

    def test_ner_extractor_non_ml_method_does_not_load_model(self, monkeypatch):
        """NERExtractor with a non-ml method must not touch the spaCy cache."""
        calls = []

        def fake_load(name, **kwargs):
            calls.append(name)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        NERExtractor(method="pattern")
        NERExtractor(method="llm")
        NERExtractor(method="regex")

        assert calls == [], "non-ml methods must not trigger any spacy.load()"


if __name__ == "__main__":
    pytest.main([__file__])
