"""
Coverage for ClusterBuilder, MergeStrategyManager, PropertyMergeRule,
EntityMerger.merge_duplicates, embedding similarity, and incremental detection.

Addresses issue #866.
"""

import unittest
from unittest.mock import patch

from semantica.deduplication.cluster_builder import Cluster, ClusterBuilder
from semantica.deduplication.duplicate_detector import (
    DuplicateDetector,
    DuplicateGroup,
)
from semantica.deduplication.entity_merger import EntityMerger
from semantica.deduplication.merge_strategy import (
    MergeStrategy,
    MergeStrategyManager,
    PropertyMergeRule,
)
from semantica.deduplication.methods import calculate_similarity
from semantica.deduplication.similarity_calculator import SimilarityCalculator
from semantica.utils.exceptions import ValidationError


class TestClusterBuilderCoverage(unittest.TestCase):
    """ClusterBuilder: union-find clustering and size filtering."""

    def setUp(self):
        self.entities = [
            {
                "id": "a1",
                "name": "Apple Inc.",
                "type": "Company",
                "properties": {"industry": "Technology"},
            },
            {
                "id": "a2",
                "name": "Apple",
                "type": "Company",
                "properties": {"industry": "Tech"},
            },
            {
                "id": "m1",
                "name": "Microsoft Corporation",
                "type": "Company",
                "properties": {"industry": "Software"},
            },
            {
                "id": "g1",
                "name": "Google LLC",
                "type": "Company",
                "properties": {"industry": "Internet"},
            },
        ]

    def test_known_duplicates_share_cluster_id(self):
        """Entities linked by high-similarity pairs land in the same cluster."""
        builder = ClusterBuilder(similarity_threshold=0.4, min_cluster_size=2)
        result = builder.build_clusters(self.entities)

        id_to_cluster = {}
        for cluster in result.clusters:
            for entity in cluster.entities:
                id_to_cluster[entity["id"]] = cluster.cluster_id

        self.assertIn("a1", id_to_cluster)
        self.assertIn("a2", id_to_cluster)
        self.assertEqual(id_to_cluster["a1"], id_to_cluster["a2"])

    def test_unrelated_entities_get_different_cluster_ids(self):
        """Unrelated brands must not share a cluster ID when they form clusters."""
        builder = ClusterBuilder(similarity_threshold=0.8, min_cluster_size=2)
        a1 = {"id": "a1", "name": "Apple Inc.", "type": "Company"}
        a2 = {"id": "a2", "name": "Apple", "type": "Company"}
        m1 = {"id": "m1", "name": "Microsoft Corporation", "type": "Company"}
        m2 = {"id": "m2", "name": "Microsoft Corp", "type": "Company"}
        # Deterministic pairs: intra-brand duplicates only — no Apple↔Microsoft edge
        pairs = [(a1, a2, 0.95), (m1, m2, 0.94)]

        with patch.object(
            builder.similarity_calculator,
            "batch_calculate_similarity",
            return_value=pairs,
        ):
            clusters = builder._graph_based_clustering(
                [a1, a2, m1, m2], threshold=0.8
            )

        id_to_cluster = {
            e["id"]: c.cluster_id for c in clusters for e in c.entities
        }
        self.assertEqual(set(id_to_cluster), {"a1", "a2", "m1", "m2"})
        self.assertEqual(id_to_cluster["a1"], id_to_cluster["a2"])
        self.assertEqual(id_to_cluster["m1"], id_to_cluster["m2"])
        self.assertNotEqual(id_to_cluster["a1"], id_to_cluster["m1"])

    def test_singleton_entities_are_unclustered(self):
        """Entities with no similar peers remain unclustered (min_cluster_size=2)."""
        builder = ClusterBuilder(similarity_threshold=0.9, min_cluster_size=2)
        result = builder.build_clusters(self.entities)
        unclustered_ids = {e["id"] for e in result.unclustered}
        # High threshold: Google and Microsoft should not form a pair cluster
        self.assertTrue(
            "g1" in unclustered_ids or "m1" in unclustered_ids,
            "Dissimilar entities should appear in unclustered",
        )

    def test_graph_clustering_from_similarity_pairs(self):
        """Union-find path merges transitively via mocked similarity pairs."""
        builder = ClusterBuilder(similarity_threshold=0.8, min_cluster_size=2)
        e1 = {"id": "1", "name": "A"}
        e2 = {"id": "2", "name": "B"}
        e3 = {"id": "3", "name": "C"}
        # 1~2 and 2~3 => all three in one cluster
        pairs = [(e1, e2, 0.95), (e2, e3, 0.92)]

        with patch.object(
            builder.similarity_calculator,
            "batch_calculate_similarity",
            return_value=pairs,
        ):
            clusters = builder._graph_based_clustering([e1, e2, e3], threshold=0.8)

        self.assertEqual(len(clusters), 1)
        self.assertEqual({e["id"] for e in clusters[0].entities}, {"1", "2", "3"})

    def test_unrelated_pairs_form_separate_clusters(self):
        """Two disjoint similarity pairs produce two cluster IDs."""
        builder = ClusterBuilder(similarity_threshold=0.8, min_cluster_size=2)
        a1, a2 = {"id": "a1", "name": "Apple"}, {"id": "a2", "name": "Apple Inc"}
        m1, m2 = {"id": "m1", "name": "MSFT"}, {"id": "m2", "name": "Microsoft"}
        pairs = [(a1, a2, 0.95), (m1, m2, 0.94)]

        with patch.object(
            builder.similarity_calculator,
            "batch_calculate_similarity",
            return_value=pairs,
        ):
            clusters = builder._graph_based_clustering([a1, a2, m1, m2], threshold=0.8)

        self.assertEqual(len(clusters), 2)
        cluster_ids = {c.cluster_id for c in clusters}
        self.assertEqual(len(cluster_ids), 2)

    def test_quality_metrics_populated(self):
        builder = ClusterBuilder(similarity_threshold=0.4, min_cluster_size=2)
        result = builder.build_clusters(self.entities[:2])
        self.assertIn("total_clusters", result.quality_metrics)
        self.assertIn("average_quality", result.quality_metrics)

    def test_update_clusters_adds_matching_entity(self):
        """Incremental update attaches a near-duplicate into an existing cluster."""
        builder = ClusterBuilder(similarity_threshold=0.8, min_cluster_size=2)
        a1 = {
            "id": "a1",
            "name": "Apple Inc.",
            "type": "Company",
            "properties": {"industry": "Technology"},
        }
        a2 = {
            "id": "a2",
            "name": "Apple",
            "type": "Company",
            "properties": {"industry": "Tech"},
        }
        existing = [Cluster(cluster_id="cluster_0", entities=[a1])]

        with patch.object(
            builder, "_entity_cluster_similarity", return_value=0.95
        ), patch.object(
            builder.similarity_calculator,
            "batch_calculate_similarity",
            return_value=[(a1, a2, 0.95)],
        ):
            result = builder.update_clusters(existing, [a2])

        self.assertEqual(len(result.clusters), 1)
        clustered_ids = {e["id"] for e in result.clusters[0].entities}
        self.assertEqual(clustered_ids, {"a1", "a2"})
        self.assertEqual(result.unclustered, [])


class TestMergeStrategyManagerCoverage(unittest.TestCase):
    """MergeStrategyManager and PropertyMergeRule conflict resolution."""

    def setUp(self):
        self.entities = [
            {
                "id": "e1",
                "name": "Apple Inc.",
                "type": "Company",
                "properties": {
                    "industry": "Technology",
                    "description": "Short",
                    "hq": "Cupertino",
                },
                "relationships": [
                    {"subject": "e1", "predicate": "competitor", "object": "Microsoft"}
                ],
                "confidence": 0.7,
            },
            {
                "id": "e2",
                "name": "Apple",
                "type": "Company",
                "properties": {
                    "industry": "Tech",
                    "description": "A much longer company description",
                    "founded": "1976",
                },
                "relationships": [
                    {"subject": "e2", "predicate": "competitor", "object": "Google"}
                ],
                "confidence": 0.9,
            },
        ]

    def test_keep_first_strategy_selects_first_entity(self):
        manager = MergeStrategyManager(default_strategy="keep_first")
        result = manager.merge_entities(self.entities, strategy="keep_first")
        self.assertEqual(result.merged_entity["id"], "e1")
        self.assertEqual(result.metadata["strategy"], "keep_first")

    def test_keep_last_strategy_selects_last_entity(self):
        manager = MergeStrategyManager()
        result = manager.merge_entities(self.entities, strategy="keep_last")
        self.assertEqual(result.merged_entity["id"], "e2")

    def test_keep_most_complete_prefers_richer_entity(self):
        # e1 has 3 props + 1 rel; e2 has 3 props + 1 rel — tie goes to max() first max
        richer = [
            {
                "id": "sparse",
                "name": "Sparse",
                "type": "Company",
                "properties": {"a": 1},
                "relationships": [],
            },
            {
                "id": "rich",
                "name": "Rich Co",
                "type": "Company",
                "properties": {"a": 1, "b": 2, "c": 3},
                "relationships": [{"subject": "rich", "predicate": "owns", "object": "x"}],
            },
        ]
        manager = MergeStrategyManager(default_strategy="keep_most_complete")
        result = manager.merge_entities(richer)
        self.assertEqual(result.merged_entity["id"], "rich")

    def test_keep_highest_confidence_selects_confident_entity(self):
        manager = MergeStrategyManager()
        result = manager.merge_entities(
            self.entities, strategy=MergeStrategy.KEEP_HIGHEST_CONFIDENCE
        )
        self.assertEqual(result.merged_entity["id"], "e2")

    def test_conflicting_property_keep_first(self):
        manager = MergeStrategyManager(default_strategy="keep_first")
        result = manager.merge_entities(self.entities, strategy="keep_first")
        # Base is e1; conflicting industry keeps first value under keep_first
        self.assertEqual(result.merged_entity["properties"]["industry"], "Technology")
        # Non-conflicting property from e2 is still absorbed
        self.assertEqual(result.merged_entity["properties"]["founded"], "1976")

    def test_conflicting_property_keep_last(self):
        manager = MergeStrategyManager()
        manager.add_property_rule("industry", "keep_last")
        result = manager.merge_entities(self.entities, strategy="keep_first")
        self.assertEqual(result.merged_entity["properties"]["industry"], "Tech")

    def test_merge_all_combines_conflicting_values(self):
        manager = MergeStrategyManager()
        manager.add_property_rule("industry", "merge_all")
        result = manager.merge_entities(self.entities, strategy="keep_first")
        industry = result.merged_entity["properties"]["industry"]
        self.assertIsInstance(industry, list)
        self.assertIn("Technology", industry)
        self.assertIn("Tech", industry)

    def test_relationships_are_unioned(self):
        manager = MergeStrategyManager(default_strategy="keep_first")
        result = manager.merge_entities(self.entities)
        objects = {r.get("object") for r in result.merged_entity["relationships"]}
        self.assertIn("Microsoft", objects)
        self.assertIn("Google", objects)

    def test_empty_entities_raises_validation_error(self):
        manager = MergeStrategyManager()
        with self.assertRaises(ValidationError):
            manager.merge_entities([])

    def test_single_entity_returns_unchanged(self):
        manager = MergeStrategyManager()
        result = manager.merge_entities([self.entities[0]])
        self.assertEqual(result.merged_entity["id"], "e1")
        self.assertEqual(result.merged_entities, [self.entities[0]])

    def test_invalid_default_strategy_falls_back(self):
        manager = MergeStrategyManager(default_strategy="not_a_real_strategy")
        self.assertEqual(manager.default_strategy, MergeStrategy.KEEP_MOST_COMPLETE)

    def test_validate_merge_reports_missing_name(self):
        manager = MergeStrategyManager()
        result = manager.merge_entities(self.entities)
        result.merged_entity["name"] = None
        validation = manager.validate_merge(result)
        self.assertFalse(validation["valid"])
        self.assertTrue(any("name" in issue.lower() for issue in validation["issues"]))


class TestPropertyMergeRuleCoverage(unittest.TestCase):
    """PropertyMergeRule: custom per-property conflict resolution."""

    def test_custom_rule_takes_longer_description(self):
        manager = MergeStrategyManager(default_strategy="keep_first")

        def longer_string(v1, v2):
            return v1 if len(str(v1)) >= len(str(v2)) else v2

        manager.add_property_rule(
            "description",
            "custom",
            conflict_resolution=longer_string,
            priority=10,
        )
        entities = [
            {
                "id": "e1",
                "name": "Alpha",
                "type": "Org",
                "properties": {"description": "Short"},
            },
            {
                "id": "e2",
                "name": "Alpha Inc",
                "type": "Org",
                "properties": {
                    "description": "This is a much longer description of the entity"
                },
            },
        ]
        result = manager.merge_entities(entities, strategy="keep_first")
        self.assertEqual(
            result.merged_entity["properties"]["description"],
            "This is a much longer description of the entity",
        )

    def test_property_merge_rule_dataclass_fields(self):
        rule = PropertyMergeRule(
            property_name="description",
            strategy=MergeStrategy.CUSTOM,
            conflict_resolution=lambda a, b: a,
            priority=5,
        )
        self.assertEqual(rule.property_name, "description")
        self.assertEqual(rule.strategy, MergeStrategy.CUSTOM)
        self.assertEqual(rule.priority, 5)
        self.assertIsNotNone(rule.conflict_resolution)

    def test_top_level_name_rule_overrides_base(self):
        manager = MergeStrategyManager(default_strategy="keep_first")
        manager.add_property_rule("name", "keep_last")
        entities = [
            {"id": "e1", "name": "First Name", "type": "Org", "properties": {}},
            {"id": "e2", "name": "Second Name", "type": "Org", "properties": {}},
        ]
        result = manager.merge_entities(entities)
        self.assertEqual(result.merged_entity["name"], "Second Name")

    def test_invalid_property_strategy_defaults(self):
        manager = MergeStrategyManager()
        manager.add_property_rule("industry", "bogus_strategy")
        self.assertEqual(
            manager.property_rules["industry"].strategy,
            MergeStrategy.KEEP_MOST_COMPLETE,
        )


class TestEntityMergerMergeDuplicates(unittest.TestCase):
    """EntityMerger.merge_duplicates end-to-end with DuplicateGroup path."""

    def setUp(self):
        self.entities = [
            {
                "id": "a1",
                "name": "Apple Inc.",
                "type": "Company",
                "properties": {"industry": "Technology", "hq": "Cupertino"},
                "relationships": [],
            },
            {
                "id": "a2",
                "name": "Apple",
                "type": "Company",
                "properties": {"industry": "Tech"},
                "relationships": [],
            },
            {
                "id": "m1",
                "name": "Microsoft Corp",
                "type": "Company",
                "properties": {"industry": "Software"},
                "relationships": [],
            },
        ]

    def test_merge_duplicates_returns_operations_for_groups(self):
        merger = EntityMerger(
            preserve_provenance=True,
            detector={
                "similarity_threshold": 0.4,
                "confidence_threshold": 0.4,
            },
        )
        operations = merger.merge_duplicates(self.entities, strategy="keep_first")
        self.assertGreater(len(operations), 0)
        op = operations[0]
        self.assertGreaterEqual(len(op.source_entities), 2)
        self.assertIn("id", op.merged_entity)
        self.assertIn("group_confidence", op.metadata)
        # Provenance preserved (written by EntityMerger._add_provenance()).
        provenance = op.merged_entity.get("metadata", {}).get("provenance", {})
        self.assertIn("merged_from", provenance)
        self.assertIn("merge_count", provenance)
        self.assertEqual(provenance["merge_count"], len(op.source_entities))

    def test_merge_duplicates_provenance_absent_when_disabled(self):
        merger = EntityMerger(
            preserve_provenance=False,
            detector={
                "similarity_threshold": 0.4,
                "confidence_threshold": 0.4,
            },
        )
        operations = merger.merge_duplicates(self.entities, strategy="keep_first")
        self.assertGreater(len(operations), 0)
        op = operations[0]

        provenance = op.merged_entity.get("metadata", {}).get("provenance")
        self.assertTrue(
            provenance is None or provenance == {},
            "metadata.provenance should be absent when preserve_provenance=False",
        )

    def test_merge_duplicates_with_explicit_duplicate_group(self):
        """merge_entity_group path used when a DuplicateGroup is already known."""
        group = DuplicateGroup(
            entities=[self.entities[0], self.entities[1]],
            similarity_scores={("a1", "a2"): 0.85},
            confidence=0.9,
        )
        merger = EntityMerger(preserve_provenance=True)
        op = merger.merge_entity_group(group.entities, strategy="keep_most_complete")
        self.assertEqual(len(op.source_entities), 2)
        self.assertEqual(
            {e["id"] for e in op.source_entities},
            {"a1", "a2"},
        )
        self.assertIn(op.merged_entity["id"], {"a1", "a2"})

    def test_merge_duplicates_recorded_in_history(self):
        merger = EntityMerger(
            detector={"similarity_threshold": 0.4, "confidence_threshold": 0.4}
        )
        ops = merger.merge_duplicates(self.entities)
        self.assertEqual(len(merger.get_merge_history()), len(ops))


class TestEmbeddingSimilarityCoverage(unittest.TestCase):
    """SimilarityCalculator / methods embedding path (vectors, no external model)."""

    def test_calculate_similarity_method_embedding(self):
        e1 = {
            "id": "1",
            "name": "Alpha",
            "embedding": [1.0, 0.0, 0.0],
        }
        e2 = {
            "id": "2",
            "name": "Beta",
            "embedding": [1.0, 0.0, 0.0],
        }
        result = calculate_similarity(e1, e2, method="embedding")
        self.assertEqual(result.method, "embedding")
        self.assertAlmostEqual(result.score, 1.0)

    def test_calculate_similarity_method_embedding_missing_vectors(self):
        result = calculate_similarity(
            {"id": "1", "name": "A"},
            {"id": "2", "name": "B"},
            method="embedding",
        )
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.method, "embedding")

    def test_calculate_similarity_method_embedding_orthogonal(self):
        e1 = {"embedding": [1.0, 0.0]}
        e2 = {"embedding": [0.0, 1.0]}
        result = calculate_similarity(e1, e2, method="embedding")
        # Cosine of orthogonal vectors is 0; normalized to (0+1)/2 = 0.5
        self.assertAlmostEqual(result.score, 0.5)

    def test_similarity_calculator_includes_embedding_component(self):
        calculator = SimilarityCalculator(
            string_weight=0.2,
            property_weight=0.2,
            relationship_weight=0.0,
            embedding_weight=0.6,
            prefilter_enabled=False,
        )
        e1 = {
            "id": "1",
            "name": "Apple Inc.",
            "properties": {},
            "embedding": [0.9, 0.1, 0.0],
        }
        e2 = {
            "id": "2",
            "name": "Apple",
            "properties": {},
            "embedding": [0.85, 0.15, 0.0],
        }
        result = calculator.calculate_similarity(e1, e2, track=False)
        self.assertIn("embedding", result.components)
        self.assertGreater(result.components["embedding"], 0.5)
        self.assertGreater(result.score, 0.0)

    def test_embedding_similarity_mismatched_dimensions(self):
        calculator = SimilarityCalculator()
        score = calculator.calculate_embedding_similarity([1.0, 0.0], [1.0, 0.0, 0.0])
        self.assertEqual(score, 0.0)


class TestIncrementalDetectionCoverage(unittest.TestCase):
    """Incremental O(n×m) detection: new entities vs existing set."""

    def setUp(self):
        self.existing = [
            {
                "id": "a1",
                "name": "Apple Inc.",
                "type": "Company",
                "properties": {"industry": "Technology"},
            },
            {
                "id": "m1",
                "name": "Microsoft Corp",
                "type": "Company",
                "properties": {"industry": "Software"},
            },
        ]
        self.new = [
            {
                "id": "a2",
                "name": "Apple",
                "type": "Company",
                "properties": {"industry": "Tech"},
            },
            {
                "id": "g1",
                "name": "Google LLC",
                "type": "Company",
                "properties": {"industry": "Internet"},
            },
        ]

    def test_incremental_detect_finds_new_vs_existing_duplicate(self):
        detector = DuplicateDetector(
            similarity_threshold=0.4,
            confidence_threshold=0.4,
        )
        candidates = detector.incremental_detect(self.new, self.existing)
        names = {(c.entity1["name"], c.entity2["name"]) for c in candidates}
        found = any(
            ("Apple" in pair and "Apple Inc." in pair) for pair in names
        )
        self.assertTrue(found, f"Expected Apple/Apple Inc. match, got {names}")

    def test_incremental_detect_does_not_compare_within_new_set(self):
        """Incremental path only compares new×existing, not new×new."""
        detector = DuplicateDetector(
            similarity_threshold=0.3,
            confidence_threshold=0.3,
        )
        # Two near-identical new entities; existing is unrelated
        new = [
            {"id": "n1", "name": "Acme Corp", "type": "Company", "properties": {}},
            {"id": "n2", "name": "Acme Corporation", "type": "Company", "properties": {}},
        ]
        existing = [
            {"id": "z1", "name": "Zebra Industries", "type": "Company", "properties": {}}
        ]
        candidates = detector.incremental_detect(new, existing)
        pair_ids = {
            frozenset((c.entity1["id"], c.entity2["id"])) for c in candidates
        }
        self.assertNotIn(frozenset({"n1", "n2"}), pair_ids)

    def test_methods_incremental_detect_duplicates(self):
        from semantica.deduplication.duplicate_detector import DuplicateCandidate
        from semantica.deduplication.methods import detect_duplicates

        results = detect_duplicates(
            self.new + self.existing,
            method="incremental",
            similarity_threshold=0.4,
            confidence_threshold=0.4,
            new_entities=self.new,
            existing_entities=self.existing,
        )
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        for candidate in results:
            self.assertIsInstance(candidate, DuplicateCandidate)
            self.assertGreaterEqual(candidate.similarity_score, 0.4)
            # Wrapper must route new×existing only: one id from each set
            ids = {candidate.entity1["id"], candidate.entity2["id"]}
            self.assertTrue(ids & {"a2", "g1"})
            self.assertTrue(ids & {"a1", "m1"})

        names = {
            frozenset((c.entity1["name"], c.entity2["name"])) for c in results
        }
        self.assertIn(frozenset({"Apple", "Apple Inc."}), names)


if __name__ == "__main__":
    unittest.main()
