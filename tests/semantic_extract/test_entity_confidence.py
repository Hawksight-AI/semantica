"""Regression tests for optional entity confidence (issue #1282).

Unavailable per-entity confidence must be represented explicitly (None)
instead of being fabricated as 1.0, and a genuine backend-provided score
of 1.0 must be distinguishable from "no score available".
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from semantica.semantic_extract.extraction_validator import ExtractionValidator
from semantica.semantic_extract.methods import (
    calculate_weighted_confidence,
    extract_entities_ml,
)
from semantica.semantic_extract.named_entity_recognizer import (
    EntityConfidenceScorer,
)
from semantica.semantic_extract.ner_extractor import NERExtractor
from semantica.semantic_extract.types import (
    CONFIDENCE_SOURCE_HEURISTIC,
    CONFIDENCE_SOURCE_KEY,
    CONFIDENCE_SOURCE_MODEL,
    CONFIDENCE_SOURCE_UNAVAILABLE,
    Entity,
    meets_confidence_threshold,
)


def _fake_span(text, label, start, end, **extra):
    return SimpleNamespace(
        text=text, label_=label, start_char=start, end_char=end, **extra
    )


def _fake_nlp(ents):
    return lambda text: SimpleNamespace(ents=ents)


class TestEntityModel(unittest.TestCase):
    def test_default_confidence_is_unknown(self):
        entity = Entity(text="Apple", label="ORG", start_char=0, end_char=5)
        self.assertIsNone(entity.confidence)

    def test_meets_confidence_threshold(self):
        self.assertTrue(meets_confidence_threshold(None, 0.9))
        self.assertTrue(meets_confidence_threshold(0.9, 0.5))
        self.assertFalse(meets_confidence_threshold(0.4, 0.5))


class TestSpacyAdapter(unittest.TestCase):
    def test_span_without_score_reports_unavailable(self):
        ents = [_fake_span("Apple Inc.", "ORG", 0, 10)]
        with patch(
            "semantica.semantic_extract.methods.SPACY_AVAILABLE", True
        ), patch(
            "semantica.semantic_extract.methods.load_spacy_model",
            return_value=_fake_nlp(ents),
        ):
            entities = extract_entities_ml("Apple Inc. was founded.")

        self.assertEqual(len(entities), 1)
        self.assertIsNone(entities[0].confidence)
        self.assertEqual(
            entities[0].metadata[CONFIDENCE_SOURCE_KEY],
            CONFIDENCE_SOURCE_UNAVAILABLE,
        )

    def test_backend_provided_score_is_preserved(self):
        ents = [
            _fake_span("Apple Inc.", "ORG", 0, 10, score=0.83),
            _fake_span("Steve Jobs", "PERSON", 26, 36, confidence=1.0),
        ]
        with patch(
            "semantica.semantic_extract.methods.SPACY_AVAILABLE", True
        ), patch(
            "semantica.semantic_extract.methods.load_spacy_model",
            return_value=_fake_nlp(ents),
        ):
            entities = extract_entities_ml(
                "Apple Inc. was founded by Steve Jobs."
            )

        self.assertEqual(entities[0].confidence, 0.83)
        self.assertEqual(
            entities[0].metadata[CONFIDENCE_SOURCE_KEY], CONFIDENCE_SOURCE_MODEL
        )
        # A genuine 1.0 stays 1.0 and is marked as a real measurement
        self.assertEqual(entities[1].confidence, 1.0)
        self.assertEqual(
            entities[1].metadata[CONFIDENCE_SOURCE_KEY], CONFIDENCE_SOURCE_MODEL
        )


class TestEntityConfidenceScorer(unittest.TestCase):
    def setUp(self):
        self.scorer = EntityConfidenceScorer()

    def test_unknown_confidence_gets_heuristic_score(self):
        entity = Entity(text="Apple", label="ORG", start_char=0, end_char=5)
        (scored,) = self.scorer.score_entities([entity])
        self.assertIsNotNone(scored.confidence)
        self.assertEqual(
            scored.metadata[CONFIDENCE_SOURCE_KEY], CONFIDENCE_SOURCE_HEURISTIC
        )

    def test_genuine_perfect_score_is_not_recalculated(self):
        # Lowercase ORG text would be penalized by the heuristic, so a
        # surviving 1.0 proves the backend score was preserved
        entity = Entity(
            text="apple",
            label="ORG",
            start_char=0,
            end_char=5,
            confidence=1.0,
            metadata={CONFIDENCE_SOURCE_KEY: CONFIDENCE_SOURCE_MODEL},
        )
        (scored,) = self.scorer.score_entities([entity])
        self.assertEqual(scored.confidence, 1.0)
        self.assertEqual(
            scored.metadata[CONFIDENCE_SOURCE_KEY], CONFIDENCE_SOURCE_MODEL
        )

    def test_backend_score_below_one_is_preserved(self):
        entity = Entity(
            text="Apple", label="ORG", start_char=0, end_char=5, confidence=0.6
        )
        (scored,) = self.scorer.score_entities([entity])
        self.assertEqual(scored.confidence, 0.6)


class TestConfidenceFiltering(unittest.TestCase):
    def _entities(self):
        return [
            Entity(text="Apple", label="ORG", start_char=0, end_char=5),
            Entity(
                text="Jobs",
                label="PERSON",
                start_char=6,
                end_char=10,
                confidence=0.9,
            ),
            Entity(
                text="maybe",
                label="ORG",
                start_char=11,
                end_char=16,
                confidence=0.2,
            ),
        ]

    def test_validator_filter_passes_unknown_confidence(self):
        validator = ExtractionValidator(min_confidence=0.5)
        filtered = validator.filter_by_confidence(self._entities())
        self.assertEqual([e.text for e in filtered], ["Apple", "Jobs"])

    def test_ner_extractor_filter_passes_unknown_confidence(self):
        extractor = NERExtractor(method="pattern")
        filtered = extractor.filter_by_confidence(self._entities(), 0.5)
        self.assertEqual([e.text for e in filtered], ["Apple", "Jobs"])

    def test_validator_metrics_count_unscored_separately(self):
        validator = ExtractionValidator(min_confidence=0.5)
        result = validator.validate_entities(self._entities())
        metrics = result.metrics
        self.assertEqual(metrics["unscored"], 1)
        self.assertEqual(metrics["high_confidence"], 1)
        self.assertEqual(metrics["low_confidence"], 1)
        self.assertAlmostEqual(metrics["average_confidence"], 0.55)

    def test_vote_averages_only_measured_scores(self):
        extractor = NERExtractor(method="pattern")
        known = Entity(
            text="Apple", label="ORG", start_char=0, end_char=5, confidence=0.8
        )
        unknown = Entity(text="Apple", label="ORG", start_char=0, end_char=5)
        voted = extractor._vote_entities([[known], [unknown]], threshold=0.5)
        self.assertEqual(len(voted), 1)
        # The fabricated 1.0 no longer inflates the average
        self.assertAlmostEqual(voted[0].confidence, 0.8)

    def test_vote_keeps_agreement_without_scores(self):
        extractor = NERExtractor(method="pattern")
        a = Entity(text="Apple", label="ORG", start_char=0, end_char=5)
        b = Entity(text="Apple", label="ORG", start_char=0, end_char=5)
        voted = extractor._vote_entities([[a], [b]], threshold=0.5)
        self.assertEqual(len(voted), 1)
        self.assertIsNone(voted[0].confidence)


class TestPipelineFillsUnknownConfidence(unittest.TestCase):
    def test_extract_emits_only_scored_entities(self):
        # The extract() pipeline scores unknown confidences before filtering,
        # so consumers of extract() never see None
        ents = [_fake_span("Apple Inc.", "ORG", 0, 10)]
        with patch(
            "semantica.semantic_extract.methods.SPACY_AVAILABLE", True
        ), patch(
            "semantica.semantic_extract.methods.load_spacy_model",
            return_value=_fake_nlp(ents),
        ):
            extractor = NERExtractor(method="ml")
            entities = extractor.extract("Apple Inc. was founded.")

        self.assertTrue(entities)
        for entity in entities:
            self.assertIsNotNone(entity.confidence)
        self.assertEqual(
            entities[0].metadata[CONFIDENCE_SOURCE_KEY],
            CONFIDENCE_SOURCE_HEURISTIC,
        )

    def test_extract_preserves_measured_scores(self):
        ents = [_fake_span("Apple Inc.", "ORG", 0, 10, score=0.83)]
        with patch(
            "semantica.semantic_extract.methods.SPACY_AVAILABLE", True
        ), patch(
            "semantica.semantic_extract.methods.load_spacy_model",
            return_value=_fake_nlp(ents),
        ):
            entities = NERExtractor(method="ml").extract(
                "Apple Inc. was founded."
            )

        self.assertEqual(entities[0].confidence, 0.83)
        self.assertEqual(
            entities[0].metadata[CONFIDENCE_SOURCE_KEY], CONFIDENCE_SOURCE_MODEL
        )


class TestWeightedConfidence(unittest.TestCase):
    def test_none_passthrough_without_valid_types(self):
        self.assertIsNone(
            calculate_weighted_confidence("ORG", None, valid_types=None)
        )

    def test_none_uses_similarity_alone(self):
        score = calculate_weighted_confidence(
            "PERSON", None, valid_types=["PERSON"], item_text="Steve Jobs"
        )
        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_none_stays_unknown_when_similarity_disabled(self):
        # Similarity explicitly disabled and no measured confidence:
        # the result must remain unknown, not a fabricated similarity score
        self.assertIsNone(
            calculate_weighted_confidence(
                "PERSON",
                None,
                valid_types=["PERSON"],
                item_text="Steve Jobs",
                weight_method=1.0,
                weight_similarity=0.0,
            )
        )
        self.assertIsNone(
            calculate_weighted_confidence(
                "PERSON",
                None,
                valid_types=["PERSON"],
                weight_method=0.0,
                weight_similarity=0.0,
            )
        )


if __name__ == "__main__":
    unittest.main()
