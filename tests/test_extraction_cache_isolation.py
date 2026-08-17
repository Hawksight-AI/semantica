"""ExtractionCache hands out caller-owned values (found by source audit).

get() used to return the stored list by reference, and CacheItem kept the
very list the caller passed to set(). Every extraction result is
post-processed in place by its callers — weighted-confidence reblending in
NERExtractor, boundary correction, ensemble merges — so the cached entities
themselves were rewritten, and each later cache hit returned
already-mutated objects. calculate_weighted_confidence is not idempotent
(each application blends the blended value again: 0.6 -> 0.775 -> 0.8625 ->
0.90625 ...), so the corruption compounded per hit.

The contract pinned here: values cross the cache boundary only as deep
copies, in both directions.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantica.semantic_extract.cache import ExtractionCache
from semantica.semantic_extract.types import Entity
from semantica.semantic_extract import methods
from semantica.semantic_extract.schemas import EntitiesResponse, EntityOut


def make_entity(text="Apple Inc.", confidence=0.6):
    return Entity(text=text, label="ORG", start_char=0, end_char=10,
                  confidence=confidence, metadata={})


class TestCacheBoundaryIsolation(unittest.TestCase):
    def setUp(self):
        self.cache = ExtractionCache(max_size=10, ttl=3600)

    def test_mutating_a_get_result_never_reaches_the_next_get(self):
        original = make_entity()
        self.cache.set("entities", "text", [original], provider="p")

        handed_out = self.cache.get("entities", "text", provider="p")
        handed_out[0].confidence = 0.123
        handed_out.append(make_entity(text="EVIL"))

        again = self.cache.get("entities", "text", provider="p")
        self.assertEqual(len(again), 1, "a rogue append must not persist")
        self.assertNotEqual(again[0].confidence, 0.123, "an in-place rewrite must not persist")
        self.assertEqual(again[0].confidence, 0.6)

    def test_mutating_the_set_input_after_storing_never_reaches_the_cache(self):
        fresh = [make_entity()]
        self.cache.set("entities", "text", fresh, provider="p")

        fresh[0].confidence = 0.123
        fresh.append(make_entity(text="EVIL"))

        stored = self.cache.get("entities", "text", provider="p")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].confidence, 0.6)

    def test_two_consecutive_gets_are_independent_objects(self):
        self.cache.set("entities", "text", [make_entity()], provider="p")
        first = self.cache.get("entities", "text", provider="p")
        second = self.cache.get("entities", "text", provider="p")
        self.assertIsNot(first[0], second[0])


class TestExtractionResultsAreNotSharedWithTheCache(unittest.TestCase):
    """End to end: what extract_entities_llm() returns is caller-owned."""

    def test_reblending_a_returned_entity_does_not_poison_the_next_call(self):
        methods._result_cache.clear()
        text = "Apple Inc. was founded by Steve Jobs."

        def run():
            with patch("semantica.semantic_extract.methods.create_provider") as mock_create:
                provider = MagicMock()
                provider.is_available.return_value = True
                provider.generate_typed.return_value = EntitiesResponse(entities=[
                    EntityOut(text="Apple Inc.", label="ORG", start=0, end=10,
                              confidence=0.6),
                ])
                mock_create.return_value = provider
                return methods.extract_entities_llm(text, provider="openai", silent_fail=False)

        first = run()
        first_confidence = first[0].confidence
        # Simulate any in-place post-processing a caller applies.
        first[0].confidence = 0.42
        first[0].start_char = 999

        second = run()  # cache hit
        self.assertEqual(second[0].confidence, first_confidence,
                         "a cache hit must return the pristine extraction, not the "
                         "previous caller's mutations")
        self.assertNotEqual(second[0].start_char, 999)


if __name__ == "__main__":
    unittest.main()
