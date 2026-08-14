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


class TestGraphBuilderExtractorReuse(unittest.TestCase):
    """Extractors must be built once per method, not once per text.

    `NERExtractor.__init__` loads its spaCy model eagerly, so with the `"ml"`
    default a per-text construction would reload the model for every source in
    a multi-document build.
    """

    def setUp(self):
        self.ner_patcher = patch(
            "semantica.semantic_extract.ner_extractor.NERExtractor"
        )
        self.NER = self.ner_patcher.start()
        self.addCleanup(self.ner_patcher.stop)
        self.NER.return_value.extract_entities.return_value = []

        self.builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

    def test_ner_extractor_built_once_across_texts(self):
        for i in range(5):
            self.builder._extract_from_text(f"Document {i}.", [], [])
        self.assertEqual(self.NER.call_count, 1)

    def test_distinct_methods_get_distinct_extractors(self):
        self.builder._extract_from_text("a", [], [])
        self.builder._extract_from_text("b", [], [], ner_method="pattern")
        self.builder._extract_from_text("c", [], [])
        self.assertEqual(self.NER.call_count, 2)


class TestGraphBuilderForwardsRelationsToTriplets(unittest.TestCase):
    """Relations extracted with relation_method must reach triplet extraction.

    `TripletExtractor` re-derives relations itself when `relations is None`,
    using a method derived from `triplet_method` — so not forwarding them both
    duplicates work and can produce triplets inconsistent with the relations
    already extracted.
    """

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
        self.Trip.return_value.extract_triplets.return_value = []

        self.builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

    def _triplet_kwargs(self):
        return self.Trip.return_value.extract_triplets.call_args.kwargs

    def test_extracted_relations_are_forwarded(self):
        sentinel = [object()]
        self.Rel.return_value.extract_relations.return_value = sentinel

        self.builder._extract_from_text("x", [], [], extract_relations=True)

        self.assertIs(self._triplet_kwargs()["relations"], sentinel)

    def test_relations_is_none_when_extraction_disabled(self):
        """Default path keeps TripletExtractor's own relation derivation."""
        self.builder._extract_from_text("x", [], [])

        self.assertIsNone(self._triplet_kwargs()["relations"])
        self.Rel.assert_not_called()

    def test_relations_is_none_when_extraction_fails(self):
        self.Rel.return_value.extract_relations.side_effect = RuntimeError("boom")

        self.builder._extract_from_text("x", [], [], extract_relations=True)

        self.assertIsNone(self._triplet_kwargs()["relations"])


class TestGraphBuilderFallbackMethodLists(unittest.TestCase):
    """All three extractors accept a list of methods for fallback ordering.

    The extractor cache must key on something hashable, or passing a list
    raises `TypeError: unhashable type: 'list'` before extraction even starts.
    """

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

    def test_list_method_does_not_raise(self):
        self.builder._extract_from_text(
            "x", [], [], ner_method=["pattern", "ml"], extract_triplets=False
        )
        self.assertEqual(self.NER.call_args.kwargs["method"], ["pattern", "ml"])

    def test_list_methods_accepted_for_every_extractor(self):
        self.builder._extract_from_text(
            "x",
            [],
            [],
            ner_method=["pattern", "ml"],
            relation_method=["pattern", "cooccurrence"],
            triplet_method=["pattern", "rules"],
            extract_relations=True,
        )
        self.assertEqual(self.NER.call_args.kwargs["method"], ["pattern", "ml"])
        self.assertEqual(
            self.Rel.call_args.kwargs["method"], ["pattern", "cooccurrence"]
        )
        self.assertEqual(self.Trip.call_args.kwargs["method"], ["pattern", "rules"])

    def test_equal_lists_reuse_one_extractor(self):
        for _ in range(3):
            self.builder._extract_from_text(
                "x", [], [], ner_method=["pattern", "ml"], extract_triplets=False
            )
        self.assertEqual(self.NER.call_count, 1)

    def test_different_lists_get_different_extractors(self):
        self.builder._extract_from_text(
            "x", [], [], ner_method=["pattern", "ml"], extract_triplets=False
        )
        self.builder._extract_from_text(
            "x", [], [], ner_method=["ml", "pattern"], extract_triplets=False
        )
        self.assertEqual(self.NER.call_count, 2)


class TestGraphBuilderDefaultsRunOffline(unittest.TestCase):
    """The default raw-text path must work with no provider and no network."""

    def test_default_build_needs_no_provider(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)
        entities, relationships = [], []

        # No mocks: this runs the real ml/pattern extractors end to end. If any
        # default resolved to "llm", this would attempt a provider call.
        with patch("semantica.semantic_extract.providers.create_provider") as provider:
            builder._extract_from_text(
                "Apple Inc. was founded by Steve Jobs in 1976.",
                entities,
                relationships,
            )

        provider.assert_not_called()
        self.assertIsInstance(entities, list)


if __name__ == "__main__":
    unittest.main()
