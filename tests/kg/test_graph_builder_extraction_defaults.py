"""Pins GraphBuilder's raw-text extraction defaults to the documented values.

Regression guard for #930: `_extract_from_text` defaulted to LLM extraction for
all three methods and ran relation extraction unconditionally, both of which
contradicted the `build()` docstring and silently required a provider and API
key for any raw-text build.
"""

import unittest
from unittest.mock import patch

from semantica.kg.graph_builder import GraphBuilder


class TestGraphBuilderExtractionDefaults(unittest.TestCase):

    def setUp(self):
        self.ner_patcher = patch(
            "semantica.semantic_extract.ner_extractor.NERExtractor"
        )
        self.rel_patcher = patch(
            "semantica.semantic_extract.relation_extractor.RelationExtractor"
        )
        self.trip_patcher = patch(
            "semantica.semantic_extract.triplet_extractor.TripletExtractor"
        )
        self.NER = self.ner_patcher.start()
        self.Rel = self.rel_patcher.start()
        self.Trip = self.trip_patcher.start()
        self.addCleanup(self.ner_patcher.stop)
        self.addCleanup(self.rel_patcher.stop)
        self.addCleanup(self.trip_patcher.stop)

        self.NER.return_value.extract_entities.return_value = []
        self.Rel.return_value.extract_relations.return_value = []
        self.Trip.return_value.extract_triplets.return_value = []

        self.builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

    def _extract(self, **options):
        self.builder._extract_from_text(
            "Apple Inc. was founded in 1976.", [], [], **options
        )

    def test_ner_method_defaults_to_ml(self):
        self._extract()
        self.assertEqual(self.NER.call_args.kwargs["method"], "ml")

    def test_triplet_method_defaults_to_pattern(self):
        self._extract()
        self.assertEqual(self.Trip.call_args.kwargs["method"], "pattern")

    def test_relation_extraction_is_off_by_default(self):
        self._extract()
        self.Rel.assert_not_called()

    def test_relation_method_defaults_to_pattern_when_enabled(self):
        self._extract(extract_relations=True)
        self.assertEqual(self.Rel.call_args.kwargs["method"], "pattern")

    def test_no_extractor_defaults_to_llm(self):
        """No raw-text default may require a provider or API key."""
        self._extract(extract_relations=True)
        extractors = (
            ("ner", self.NER),
            ("relation", self.Rel),
            ("triplet", self.Trip),
        )
        for name, mock_cls in extractors:
            with self.subTest(extractor=name):
                self.assertNotEqual(mock_cls.call_args.kwargs["method"], "llm")

    def test_llm_extraction_is_still_available_explicitly(self):
        self._extract(
            ner_method="llm",
            relation_method="llm",
            triplet_method="llm",
            extract_relations=True,
        )
        self.assertEqual(self.NER.call_args.kwargs["method"], "llm")
        self.assertEqual(self.Rel.call_args.kwargs["method"], "llm")
        self.assertEqual(self.Trip.call_args.kwargs["method"], "llm")


if __name__ == "__main__":
    unittest.main()
