"""Regression tests for spaCy pipeline caching in semantic_extract.methods.

Before this cache, extract_entities_ml, extract_relations_similarity and
extract_relations_dependency each called spacy.load() on every invocation,
costing ~120 ms per call on work that takes ~2 ms.
"""

import unittest
from unittest.mock import MagicMock, patch

from semantica.semantic_extract import methods


def _fake_spacy():
    """A spacy stand-in whose loaded pipeline yields a document with no entities."""
    fake = MagicMock()
    fake.load.return_value = MagicMock(**{"return_value.ents": []})
    return fake


class TestSpacyModelCache(unittest.TestCase):

    def setUp(self):
        methods.load_spacy_model.cache_clear()
        self.addCleanup(methods.load_spacy_model.cache_clear)

    def test_repeated_extraction_loads_model_once(self):
        """extract_entities_ml must not reload the pipeline on every call."""
        fake = _fake_spacy()
        with patch.object(methods, "spacy", fake), patch.object(
            methods, "SPACY_AVAILABLE", True
        ):
            for _ in range(5):
                methods.extract_entities_ml("Apple Inc. was founded in 1976.")

        self.assertEqual(fake.load.call_count, 1)

    def test_returns_the_same_pipeline_instance(self):
        fake = _fake_spacy()
        with patch.object(methods, "spacy", fake):
            first = methods.load_spacy_model("en_core_web_sm")
            second = methods.load_spacy_model("en_core_web_sm")

        self.assertIs(first, second)

    def test_distinct_models_are_cached_separately(self):
        fake = _fake_spacy()
        with patch.object(methods, "spacy", fake):
            methods.load_spacy_model("en_core_web_sm")
            methods.load_spacy_model("en_core_web_lg")
            methods.load_spacy_model("en_core_web_sm")

        self.assertEqual(fake.load.call_count, 2)

    def test_dependency_extraction_shares_the_cache(self):
        """extract_relations_dependency reuses a pipeline loaded elsewhere."""
        fake = _fake_spacy()
        with patch.object(methods, "spacy", fake), patch.object(
            methods, "SPACY_AVAILABLE", True
        ):
            methods.extract_entities_ml("Apple Inc. was founded in 1976.")
            methods.extract_relations_dependency("Apple Inc. was founded in 1976.", [])

        self.assertEqual(fake.load.call_count, 1)

    def test_missing_model_is_not_cached(self):
        """A failed load must retry, not serve a cached failure, and still fall back."""
        fake = MagicMock()
        fake.load.side_effect = OSError("model not found")
        with patch.object(methods, "spacy", fake), patch.object(
            methods, "SPACY_AVAILABLE", True
        ):
            first = methods.extract_entities_ml("Apple Inc. was founded in 1976.")
            second = methods.extract_entities_ml("Apple Inc. was founded in 1976.")

        # Two attempts per call: the requested model, then the en_core_web_sm fallback.
        self.assertEqual(fake.load.call_count, 4)
        # And the pattern-based fallback still produced results.
        self.assertEqual([e.text for e in first], [e.text for e in second])


if __name__ == "__main__":
    unittest.main()
