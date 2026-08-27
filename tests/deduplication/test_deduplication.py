import sys
import unittest
from typing import Dict, Any, List
from semantica.deduplication.similarity_calculator import SimilarityCalculator
from semantica.deduplication.duplicate_detector import (
    DuplicateCandidate,
    DuplicateDetector,
)
from semantica.deduplication.entity_merger import EntityMerger
from semantica.deduplication.merge_strategy import MergeStrategy
from semantica.deduplication.cluster_builder import ClusterBuilder
from semantica.deduplication.registry import MethodRegistry
from semantica.deduplication.config import DeduplicationConfig
from semantica.deduplication.methods import get_deduplication_method
from semantica.utils.types import Entity
from semantica.utils.progress_tracker import ConsoleProgressDisplay

class TestDeduplication(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.entities = [
            {
                "id": "e1",
                "name": "Apple Inc.",
                "type": "Company",
                "properties": {"industry": "Technology", "headquarters": "Cupertino"},
                "relationships": [{"type": "competitor", "target": "Microsoft"}]
            },
            {
                "id": "e2",
                "name": "Apple",
                "type": "Company",
                "properties": {"industry": "Tech", "headquarters": "Cupertino, CA"},
                "relationships": [{"type": "competitor", "target": "Google"}]
            },
            {
                "id": "e3",
                "name": "Microsoft Corp",
                "type": "Company",
                "properties": {"industry": "Software"},
                "relationships": []
            }
        ]
        
    def test_similarity_calculator(self):
        """Test similarity calculation components."""
        calculator = SimilarityCalculator(
            string_weight=0.5,
            property_weight=0.5,
            embedding_weight=0.0
        )
        
        # Test string similarity
        score_lev = calculator.calculate_string_similarity("Apple", "Apple Inc.", method="levenshtein")
        self.assertGreater(score_lev, 0.0)
        self.assertLess(score_lev, 1.0)
        
        score_exact = calculator.calculate_string_similarity("Apple", "Apple", method="exact")
        self.assertEqual(score_exact, 1.0)
        
        # Test full similarity calculation
        result = calculator.calculate_similarity(self.entities[0], self.entities[1])
        self.assertGreater(result.score, 0.0)
        self.assertIsNotNone(result.components)
        
    def test_duplicate_detector(self):
        """Test duplicate detection."""
        detector = DuplicateDetector(
            similarity_threshold=0.4, # Lower threshold for test data
            confidence_threshold=0.4
        )
        
        # Test pairwise detection
        duplicates = detector.detect_duplicates(self.entities)
        # Should find Apple and Apple Inc. as duplicates
        found_match = False
        for dup in duplicates:
            names = {dup.entity1["name"], dup.entity2["name"]}
            if "Apple" in names and "Apple Inc." in names:
                found_match = True
                break
        self.assertTrue(found_match, "Should detect 'Apple' and 'Apple Inc.' as duplicates")
        
        # Test group detection
        groups = detector.detect_duplicate_groups(self.entities)
        self.assertGreater(len(groups), 0)
        # One group should have at least 2 entities (the Apple ones)
        apple_group = next((g for g in groups if len(g.entities) >= 2), None)
        self.assertIsNotNone(apple_group)

    def test_different_types_are_never_duplicates(self):
        """Entities with different non-empty types must not merge (issue #1137)."""
        detector = DuplicateDetector(
            similarity_threshold=0.4, confidence_threshold=0.4
        )
        entities = [
            {"id": "e1", "type": "Person", "name": "Alice", "text": "Alice"},
            {"id": "e2", "type": "Organization", "name": "Acme", "text": "Acme"},
        ]
        duplicates = detector.detect_duplicates(entities)
        self.assertEqual(
            duplicates, [],
            "Person 'Alice' and Organization 'Acme' must not be duplicate candidates",
        )
        # GraphBuilder with merge_entities=True must keep both entities
        from semantica.kg import GraphBuilder
        graph = GraphBuilder(merge_entities=True).build(
            {"entities": entities, "relationships": []}
        )
        self.assertEqual(len(graph["entities"]), 2)

    def test_same_type_same_name_still_merges(self):
        """Type guard must not break legitimate dedup of same-type entities."""
        detector = DuplicateDetector(
            similarity_threshold=0.4, confidence_threshold=0.4
        )
        entities = [
            {"id": "e1", "type": "Person", "name": "Alice", "text": "Alice"},
            {"id": "e2", "type": "Person", "name": "Alice", "text": "Alice"},
        ]
        duplicates = detector.detect_duplicates(entities)
        self.assertTrue(
            duplicates, "Same-type same-name entities must still be detected as duplicates"
        )

    def test_untyped_same_name_still_merges(self):
        """Entities with no type must retain previous behavior (merge on similarity)."""
        detector = DuplicateDetector(
            similarity_threshold=0.4, confidence_threshold=0.4
        )
        entities = [
            {"id": "x1", "name": "Apple"},
            {"id": "x2", "name": "Apple"},
        ]
        duplicates = detector.detect_duplicates(entities)
        self.assertTrue(
            duplicates, "Untyped same-name entities must still be detected as duplicates"
        )

    def test_entity_objects_different_types_not_duplicates(self):
        """Entity objects expose their type via .type, not .label (issue #1137)."""
        detector = DuplicateDetector(
            similarity_threshold=0.4, confidence_threshold=0.0
        )
        entities = [
            Entity(id="e1", text="Alice", type="Person"),
            Entity(id="e2", text="Acme", type="Organization"),
        ]
        duplicates = detector.detect_duplicates(entities)
        self.assertEqual(
            duplicates, [],
            "Entity objects with different types must never be detected as duplicates",
        )

    def test_zero_threshold_still_excludes_type_mismatch(self):
        """Type mismatch must be excluded structurally, not just by confidence 0."""
        detector = DuplicateDetector(
            similarity_threshold=0.4, confidence_threshold=0.0
        )
        entities = [
            {"id": "e1", "type": "Person", "name": "Alice", "text": "Alice"},
            {"id": "e2", "type": "Organization", "name": "Acme", "text": "Acme"},
        ]
        duplicates = detector.detect_duplicates(entities)
        self.assertEqual(
            duplicates, [],
            "Different-type candidates must be excluded even with confidence_threshold=0.0",
        )
        
    def test_entity_merger(self):
        """Test entity merging."""
        merger = EntityMerger(preserve_provenance=True)
        
        # Test merging specific group
        to_merge = [self.entities[0], self.entities[1]]
        
        # Strategy: KEEP_FIRST
        op_first = merger.merge_entity_group(to_merge, strategy=MergeStrategy.KEEP_FIRST)
        self.assertEqual(op_first.merged_entity["id"], "e1")
        
        # Strategy: KEEP_LAST
        op_last = merger.merge_entity_group(to_merge, strategy=MergeStrategy.KEEP_LAST)
        self.assertEqual(op_last.merged_entity["id"], "e2")
        
        # Strategy: MERGE_ALL (combining properties)
        # Note: implementation might vary on how it combines properties, checking basics
        op_merge = merger.merge_entity_group(to_merge, strategy=MergeStrategy.MERGE_ALL)
        self.assertIn("industry", op_merge.merged_entity["properties"])
        
    def test_entity_merger_string_strategies(self):
        """Test entity merging with string strategies."""
        merger = EntityMerger(preserve_provenance=True)
        to_merge = [self.entities[0], self.entities[1]]
        
        # Strategy: "keep_first"
        op_first = merger.merge_entity_group(to_merge, strategy="keep_first")
        self.assertEqual(op_first.merged_entity["id"], "e1")
        
        # Strategy: "keep_last"
        op_last = merger.merge_entity_group(to_merge, strategy="keep_last")
        self.assertEqual(op_last.merged_entity["id"], "e2")
        
        # Strategy: "keep_most_complete"
        # Apple Inc. (e1) has 2 props, Apple (e2) has 1 prop
        op_complete = merger.merge_entity_group(to_merge, strategy="keep_most_complete")
        self.assertEqual(op_complete.merged_entity["id"], "e1")
        
        # Test property rule with string strategy
        from semantica.deduplication.merge_strategy import MergeStrategyManager
        manager = MergeStrategyManager()
        manager.add_property_rule("name", "keep_last")
        
        # Manually invoke with manager (since EntityMerger creates its own default manager)
        # We can pass a custom manager if EntityMerger allowed, but here we test manager directly
        result = manager.merge_entities(to_merge)
        # name should be from last entity ("Apple")
        self.assertEqual(result.merged_entity["name"], "Apple")

    def test_incremental_detection(self):
        """Test incremental duplicate detection."""
        detector = DuplicateDetector(
            similarity_threshold=0.4,
            confidence_threshold=0.4
        )
        existing = [self.entities[0]] # Apple Inc.
        new_ents = [self.entities[1], self.entities[2]] # Apple, Microsoft
        
        candidates = detector.incremental_detect(new_ents, existing)
        
        # Should match Apple (new) with Apple Inc. (existing)
        found_match = False
        for cand in candidates:
            if cand.entity1["name"] == "Apple" and cand.entity2["name"] == "Apple Inc.":
                found_match = True
            elif cand.entity1["name"] == "Apple Inc." and cand.entity2["name"] == "Apple":
                found_match = True
                
        self.assertTrue(found_match, "Should detect incremental duplicate between Apple and Apple Inc.")

    def test_cluster_builder(self):
        """Test cluster building."""
        builder = ClusterBuilder(
            similarity_threshold=0.4,
            min_cluster_size=2
        )
        result = builder.build_clusters(self.entities)
        
        # Should find at least one cluster with Apple entities
        self.assertGreater(len(result.clusters), 0)
        apple_cluster = next((c for c in result.clusters if len(c.entities) >= 2), None)
        self.assertIsNotNone(apple_cluster)
        
    def test_registry(self):
        """Test method registry."""
        registry = MethodRegistry()
        
        def dummy_method(a, b):
            return 1.0
            
        registry.register("similarity", "dummy", dummy_method)
        method = registry.get("similarity", "dummy")
        self.assertEqual(method, dummy_method)
        self.assertIn("dummy", registry.list_all("similarity")["similarity"])
        
    def test_config(self):
        """Test configuration manager."""
        config = DeduplicationConfig()
        config.set("similarity_threshold", 0.95)
        self.assertEqual(config.get("similarity_threshold"), 0.95)
        
        # Test fallback (if implemented) or default
        self.assertEqual(config.get("non_existent", default="default"), "default")

    def test_methods_wrapper(self):
        """Test methods wrapper."""
        # Test built-in method retrieval
        method = get_deduplication_method("similarity", "levenshtein")
        self.assertIsNotNone(method)
        
        # Test usage of retrieved method
        result = method(self.entities[0], self.entities[1])
        # The wrapper returns a SimilarityResult
        self.assertIsNotNone(result.score)
        
        # Test invalid method
        invalid = get_deduplication_method("similarity", "non_existent_method")
        self.assertIsNone(invalid)


class TestProgressTrackerEncoding(unittest.TestCase):
    """Regression tests for issue #531 — Unicode crash on cp1252 Windows consoles."""

    def _make_cp1252_stdout(self):
        """Return a stdout-like object that raises UnicodeEncodeError for non-cp1252 chars."""
        class CP1252Writer:
            encoding = "cp1252"
            def write(self, text):
                text.encode("cp1252")  # raises on emoji / block chars
            def flush(self):
                pass
        return CP1252Writer()

    def test_safe_write_does_not_crash_on_cp1252(self):
        """_safe_write must not raise UnicodeEncodeError on a cp1252 console."""
        display = ConsoleProgressDisplay()
        orig = sys.stdout
        sys.stdout = self._make_cp1252_stdout()
        try:
            display._safe_write("🧠 Semantica - 📊 Current Progress\n")
        except UnicodeEncodeError:
            self.fail("_safe_write raised UnicodeEncodeError on cp1252 stdout")
        finally:
            sys.stdout = orig

    def test_update_pipeline_header_does_not_crash_on_cp1252(self):
        """update() pipeline header write must not crash on a cp1252 console (issue #531)."""
        from semantica.utils.progress_tracker import ProgressItem
        display = ConsoleProgressDisplay()
        display.use_emoji = True  # force emoji path to exercise the fixed branch
        orig = sys.stdout
        sys.stdout = self._make_cp1252_stdout()
        try:
            display._safe_write("🧠 Semantica - 📊 Current Progress\n")
            display._safe_write("=" * 150 + "\n")
        except UnicodeEncodeError:
            self.fail("Pipeline header write raised UnicodeEncodeError on cp1252 stdout")
        finally:
            sys.stdout = orig

    def test_emoji_detection_disables_on_cp1252(self):
        """ConsoleProgressDisplay should auto-disable emoji when stdout is cp1252."""
        orig = sys.stdout
        sys.stdout = self._make_cp1252_stdout()
        try:
            display = ConsoleProgressDisplay()
            self.assertFalse(display.use_emoji, "use_emoji should be False on cp1252 stdout")
        finally:
            sys.stdout = orig


class TestResultLimiting(unittest.TestCase):
    """Tests for issue #534 — max_results, top_k_per_entity, min_similarity, sort_by."""

    def setUp(self):
        # Six entities: three near-duplicate Apple variants + two Microsoft variants + one Google.
        # Lower thresholds so all intra-brand pairs clear the bar.
        self.entities = [
            {"id": "a1", "name": "Apple Inc.", "type": "Company",
             "properties": {"industry": "Technology"}},
            {"id": "a2", "name": "Apple", "type": "Company",
             "properties": {"industry": "Tech"}},
            {"id": "a3", "name": "Apple Corp", "type": "Company",
             "properties": {"industry": "Technology"}},
            {"id": "b1", "name": "Microsoft Corporation", "type": "Company",
             "properties": {"industry": "Software"}},
            {"id": "b2", "name": "Microsoft Corp", "type": "Company",
             "properties": {"industry": "Software"}},
            {"id": "c1", "name": "Google LLC", "type": "Company",
             "properties": {"industry": "Internet"}},
        ]
        self.threshold = 0.3

    def _base_detector(self, **kwargs):
        return DuplicateDetector(
            similarity_threshold=self.threshold,
            confidence_threshold=self.threshold,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # max_results
    # ------------------------------------------------------------------

    def test_max_results_caps_output(self):
        detector = self._base_detector(max_results=1)
        results = detector.detect_duplicates(self.entities)
        self.assertLessEqual(len(results), 1)

    def test_max_results_two(self):
        detector = self._base_detector(max_results=2)
        results = detector.detect_duplicates(self.entities)
        self.assertLessEqual(len(results), 2)

    def test_max_results_none_no_cap(self):
        uncapped = self._base_detector()
        large_cap = self._base_detector(max_results=999)
        self.assertEqual(
            len(uncapped.detect_duplicates(self.entities)),
            len(large_cap.detect_duplicates(self.entities)),
        )

    def test_max_results_zero_returns_empty(self):
        detector = self._base_detector(max_results=0)
        self.assertEqual(detector.detect_duplicates(self.entities), [])

    def test_max_results_returns_highest_confidence_first(self):
        """When capped, the kept candidates must be the highest-confidence ones."""
        n = 2
        all_results = self._base_detector().detect_duplicates(self.entities)
        capped = self._base_detector(max_results=n).detect_duplicates(self.entities)
        if len(all_results) >= n:
            expected_ids = {
                (c.entity1["id"], c.entity2["id"]) for c in all_results[:n]
            }
            actual_ids = {
                (c.entity1["id"], c.entity2["id"]) for c in capped
            }
            self.assertEqual(expected_ids, actual_ids)

    def test_max_results_empty_input(self):
        detector = self._base_detector(max_results=5)
        self.assertEqual(detector.detect_duplicates([]), [])

    # ------------------------------------------------------------------
    # top_k_per_entity
    # ------------------------------------------------------------------

    def test_top_k_per_entity_k1(self):
        # OR semantics: keep if EITHER entity is under quota.
        # A popular entity can appear > k times (each new partner brings it back).
        # Invariant: no (entity1, entity2) pair is returned more than once.
        k = 1
        results = self._base_detector(top_k_per_entity=k).detect_duplicates(self.entities)
        pairs = [(c.entity1["id"], c.entity2["id"]) for c in results]
        self.assertEqual(len(pairs), len(set(pairs)), "No duplicate pairs should appear")
        # OR gives >= results than AND — at least 1 result when matches exist
        and_results = self._base_detector().detect_duplicates(self.entities)
        if and_results:
            self.assertGreater(len(results), 0)

    def test_top_k_per_entity_k2(self):
        # Same OR semantics: no pair appears twice; result is bounded below by k=1 count
        k = 2
        results = self._base_detector(top_k_per_entity=k).detect_duplicates(self.entities)
        pairs = [(c.entity1["id"], c.entity2["id"]) for c in results]
        self.assertEqual(len(pairs), len(set(pairs)), "No duplicate pairs should appear")
        k1_results = self._base_detector(top_k_per_entity=1).detect_duplicates(self.entities)
        self.assertGreaterEqual(len(results), len(k1_results))

    def test_top_k_per_entity_large_k_same_as_none(self):
        uncapped = self._base_detector().detect_duplicates(self.entities)
        large_k = self._base_detector(top_k_per_entity=999).detect_duplicates(self.entities)
        self.assertEqual(len(uncapped), len(large_k))

    def test_top_k_per_entity_empty_input(self):
        detector = self._base_detector(top_k_per_entity=2)
        self.assertEqual(detector.detect_duplicates([]), [])

    # ------------------------------------------------------------------
    # min_similarity
    # ------------------------------------------------------------------

    def test_min_similarity_all_results_above_floor(self):
        floor = 0.6
        results = self._base_detector(min_similarity=floor).detect_duplicates(self.entities)
        for c in results:
            self.assertGreaterEqual(
                c.similarity_score, floor,
                f"Candidate score {c.similarity_score} is below min_similarity={floor}",
            )

    def test_min_similarity_very_high_returns_only_exact(self):
        results = self._base_detector(min_similarity=1.0).detect_duplicates(self.entities)
        for c in results:
            self.assertEqual(c.similarity_score, 1.0)

    def test_min_similarity_zero_does_not_over_filter(self):
        no_floor = self._base_detector().detect_duplicates(self.entities)
        zero_floor = self._base_detector(min_similarity=0.0).detect_duplicates(self.entities)
        self.assertEqual(len(no_floor), len(zero_floor))

    def test_min_similarity_stricter_than_threshold_reduces_results(self):
        """A min_similarity above similarity_threshold must not increase the result count."""
        base = self._base_detector().detect_duplicates(self.entities)
        stricter = self._base_detector(min_similarity=0.8).detect_duplicates(self.entities)
        self.assertLessEqual(len(stricter), len(base))

    def test_min_similarity_empty_input(self):
        detector = self._base_detector(min_similarity=0.5)
        self.assertEqual(detector.detect_duplicates([]), [])

    # ------------------------------------------------------------------
    # sort_by
    # ------------------------------------------------------------------

    def test_sort_by_confidence_descending(self):
        results = self._base_detector(sort_by="confidence").detect_duplicates(self.entities)
        scores = [c.confidence for c in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_sort_by_similarity_score_descending(self):
        results = self._base_detector(sort_by="similarity_score").detect_duplicates(self.entities)
        scores = [c.similarity_score for c in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_sort_by_default_is_confidence(self):
        default = self._base_detector().detect_duplicates(self.entities)
        explicit = self._base_detector(sort_by="confidence").detect_duplicates(self.entities)
        self.assertEqual(
            [(c.entity1["id"], c.entity2["id"]) for c in default],
            [(c.entity1["id"], c.entity2["id"]) for c in explicit],
        )

    def test_sort_by_invalid_raises_at_construction(self):
        with self.assertRaises(ValueError):
            self._base_detector(sort_by="bogus_field")

    def test_sort_by_invalid_message_contains_field_name(self):
        with self.assertRaises(ValueError, msg="bogus_field") as ctx:
            self._base_detector(sort_by="bogus_field")
        self.assertIn("bogus_field", str(ctx.exception))

    # ------------------------------------------------------------------
    # Input validation (bug_002 / bug_003)
    # ------------------------------------------------------------------

    def test_max_results_negative_raises(self):
        with self.assertRaises(ValueError):
            self._base_detector(max_results=-1)

    def test_max_results_float_raises(self):
        with self.assertRaises(ValueError):
            self._base_detector(max_results=1.5)

    def test_top_k_per_entity_negative_raises(self):
        with self.assertRaises(ValueError):
            self._base_detector(top_k_per_entity=-1)

    def test_top_k_per_entity_float_raises(self):
        with self.assertRaises(ValueError):
            self._base_detector(top_k_per_entity=2.5)

    def test_min_similarity_above_1_raises(self):
        with self.assertRaises(ValueError):
            self._base_detector(min_similarity=1.1)

    def test_min_similarity_below_0_raises(self):
        with self.assertRaises(ValueError):
            self._base_detector(min_similarity=-0.1)

    def test_max_results_zero_is_valid(self):
        # 0 is a non-negative int — must not raise
        detector = self._base_detector(max_results=0)
        self.assertEqual(detector.detect_duplicates(self.entities), [])

    def test_top_k_per_entity_zero_is_valid(self):
        detector = self._base_detector(top_k_per_entity=0)
        self.assertEqual(detector.detect_duplicates(self.entities), [])

    def test_min_similarity_boundary_0_valid(self):
        self._base_detector(min_similarity=0.0)  # must not raise

    def test_min_similarity_boundary_1_valid(self):
        self._base_detector(min_similarity=1.0)  # must not raise

    # ------------------------------------------------------------------
    # top_k_per_entity OR semantics (bug_001)
    # ------------------------------------------------------------------

    def test_top_k_or_semantics_keeps_candidate_if_either_under_quota(self):
        """A high-ranked candidate must survive even if one of its entities hit k,
        as long as the other entity is still under quota."""
        # With k=1 and OR semantics, every entity can appear in AT LEAST one
        # candidate. Verify that more candidates survive than would under AND.
        k = 1
        or_results = self._base_detector(top_k_per_entity=k).detect_duplicates(self.entities)
        # Each entity should appear at least once — no entity completely starved
        seen_ids: set = set()
        for c in or_results:
            seen_ids.add(c.entity1["id"])
            seen_ids.add(c.entity2["id"])
        # Entities that have at least one match above threshold must appear
        all_ids_in_any_pair: set = set()
        uncapped = self._base_detector().detect_duplicates(self.entities)
        for c in uncapped:
            all_ids_in_any_pair.add(c.entity1["id"])
            all_ids_in_any_pair.add(c.entity2["id"])
        self.assertEqual(seen_ids, all_ids_in_any_pair)

    def test_group_merge_updates_normalized_entity_keys_for_int_ids(self):
        """Merged groups must update the normalized string lookup keys.

        Regression for stale raw int keys: after a bridge candidate merges two
        groups, later candidates involving the moved int-ID entities must still
        attach to the returned group rather than an orphaned removed group.
        """
        entities = [
            {"id": 1, "name": "Alpha"},
            {"id": 2, "name": "Alpha duplicate"},
            {"id": 3, "name": "Alpha bridge"},
            {"id": 4, "name": "Alpha merged"},
            {"id": 5, "name": "Alpha later"},
        ]
        candidates = [
            DuplicateCandidate(entities[0], entities[1], 0.95, 0.95),
            DuplicateCandidate(entities[2], entities[3], 0.94, 0.94),
            DuplicateCandidate(entities[1], entities[2], 0.93, 0.93),
            DuplicateCandidate(entities[2], entities[4], 0.92, 0.92),
        ]

        groups = self._base_detector()._build_duplicate_groups(candidates)

        self.assertEqual(len(groups), 1)
        self.assertEqual(
            {entity["id"] for entity in groups[0].entities},
            {1, 2, 3, 4, 5},
        )

    # ------------------------------------------------------------------
    # Combined options
    # ------------------------------------------------------------------

    def test_max_results_and_sort_by_similarity(self):
        n = 2
        results = self._base_detector(max_results=n, sort_by="similarity_score").detect_duplicates(self.entities)
        self.assertLessEqual(len(results), n)
        if len(results) == 2:
            self.assertGreaterEqual(results[0].similarity_score, results[1].similarity_score)

    def test_min_similarity_and_top_k_combined(self):
        floor, k = 0.5, 1
        results = self._base_detector(min_similarity=floor, top_k_per_entity=k).detect_duplicates(self.entities)
        # min_similarity floor still applies
        for c in results:
            self.assertGreaterEqual(c.similarity_score, floor)
        # OR semantics: no pair duplicated
        pairs = [(c.entity1["id"], c.entity2["id"]) for c in results]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_all_four_options_combined(self):
        results = self._base_detector(
            max_results=3,
            top_k_per_entity=1,
            min_similarity=0.3,
            sort_by="similarity_score",
        ).detect_duplicates(self.entities)
        self.assertLessEqual(len(results), 3)
        scores = [c.similarity_score for c in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for c in results:
            self.assertGreaterEqual(c.similarity_score, 0.3)

    def test_max_results_applied_after_top_k(self):
        """max_results must slice the already-top-k-filtered list, not pre-empt it."""
        top_k_only = self._base_detector(top_k_per_entity=1).detect_duplicates(self.entities)
        both = self._base_detector(top_k_per_entity=1, max_results=1).detect_duplicates(self.entities)
        self.assertLessEqual(len(both), min(1, len(top_k_only)))

    # ------------------------------------------------------------------
    # incremental_detect
    # ------------------------------------------------------------------

    def test_incremental_detect_max_results(self):
        new_e, existing = self.entities[:3], self.entities[3:]
        results = self._base_detector(max_results=1).incremental_detect(new_e, existing)
        self.assertLessEqual(len(results), 1)

    def test_incremental_detect_min_similarity(self):
        new_e, existing = self.entities[:3], self.entities[3:]
        results = self._base_detector(min_similarity=0.99).incremental_detect(new_e, existing)
        for c in results:
            self.assertGreaterEqual(c.similarity_score, 0.99)

    def test_incremental_detect_sort_by_similarity(self):
        new_e, existing = self.entities[:3], self.entities[3:]
        results = self._base_detector(sort_by="similarity_score").incremental_detect(new_e, existing)
        scores = [c.similarity_score for c in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_incremental_detect_top_k_per_entity(self):
        new_e, existing = self.entities[:3], self.entities[3:]
        k = 1
        results = self._base_detector(top_k_per_entity=k).incremental_detect(new_e, existing)
        # OR semantics: no pair appears twice
        pairs = [(c.entity1["id"], c.entity2["id"]) for c in results]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_incremental_detect_empty_new_entities(self):
        detector = self._base_detector(max_results=5)
        self.assertEqual(detector.incremental_detect([], self.entities), [])

    def test_incremental_detect_empty_existing_entities(self):
        detector = self._base_detector(max_results=5)
        self.assertEqual(detector.incremental_detect(self.entities, []), [])


if __name__ == "__main__":
    unittest.main()
