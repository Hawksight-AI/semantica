import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from semantica.conflicts.conflict_analyzer import ConflictAnalyzer
from semantica.conflicts.conflict_detector import (
    Conflict,
    ConflictDetector,
    ConflictType,
)
from semantica.conflicts.conflict_resolver import ConflictResolver
from semantica.conflicts.investigation_guide import InvestigationGuideGenerator
from semantica.conflicts.source_tracker import SourceReference, SourceTracker


class TestConflictsModule(unittest.TestCase):
    def setUp(self):
        # Mock progress tracker
        self.mock_tracker_patcher = patch(
            "semantica.utils.progress_tracker.get_progress_tracker"
        )
        self.mock_get_tracker = self.mock_tracker_patcher.start()
        self.mock_tracker = MagicMock()
        self.mock_get_tracker.return_value = self.mock_tracker

        self.setUp_data()

    def tearDown(self):
        self.mock_tracker_patcher.stop()

    def setUp_data(self):
        # Setup common data for tests
        self.entities = [
            {
                "id": "e1",
                "type": "Person",
                "name": "John Doe",
                "properties": {"age": 30, "location": "New York"},
                "source": "source1",
                "page": 1,
                "confidence": 0.9,
                "metadata": {"timestamp": "2023-01-01T10:00:00"},
            },
            {
                "id": "e1",
                "type": "Person",
                "name": "John Doe",
                "properties": {"age": 32, "location": "Boston"},
                "source": "source2",
                "page": 5,
                "confidence": 0.8,
                "metadata": {"timestamp": "2023-06-01T10:00:00"},
            },
        ]

        self.source1 = SourceReference(
            document="doc1", page=1, confidence=0.9, timestamp=datetime(2023, 1, 1)
        )
        self.source2 = SourceReference(
            document="doc2", page=2, confidence=0.8, timestamp=datetime(2023, 6, 1)
        )

    def test_source_tracker(self):
        tracker = SourceTracker()

        # Test tracking property source
        tracker.track_property_source("e1", "age", 30, self.source1)
        tracker.track_property_source("e1", "age", 32, self.source2)

        # Test getting property sources
        prop_source = tracker.get_property_sources("e1", "age")
        self.assertIsNotNone(prop_source)
        self.assertEqual(len(prop_source.sources), 2)
        self.assertEqual(prop_source.value, 32)  # Should store latest value

        # Test finding disagreements
        disagreements = tracker.find_source_disagreements("e1", "age")
        # Since we tracked different sources for the same property, there might be
        # disagreements based on how find_source_disagreements works.
        self.assertTrue(len(disagreements) > 0)

        # Test tracking entity source
        tracker.track_entity_source("e1", self.source1)
        sources = tracker.get_entity_sources("e1")
        self.assertTrue(len(sources) >= 1)

    def test_track_sources_batch_failure_not_counted(self):
        """Test that track_sources_batch does not increment stats when tracking fails (#783)."""
        tracker = SourceTracker()
        source_data = [
            {
                "type": "property",
                "entity_id": "e1",
                "property_name": "age",
                "value": 30,
                "source": self.source1,
            },
            {
                "type": "property",
                "entity_id": "e2",
                "property_name": "age",
                "value": 25,
                "source": self.source2,
            },
        ]
        with patch.object(tracker, "track_property_source", return_value=False):
            stats = tracker.track_sources_batch(source_data)
            self.assertEqual(stats["properties_tracked"], 0)
            self.assertEqual(stats["total_tracked"], 0)

    def test_conflict_detector(self):
        detector = ConflictDetector()

        # We need to flatten the entities structure for detect_value_conflicts since it
        # expects properties at top-level (value = entity[property_name]).

        flat_entities = [
            {"id": "e1", "age": 30, "source": "source1", "confidence": 0.9},
            {"id": "e1", "age": 32, "source": "source2", "confidence": 0.8},
        ]

        conflicts = detector.detect_value_conflicts(flat_entities, "age")

        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertEqual(conflict.entity_id, "e1")
        self.assertEqual(conflict.property_name, "age")
        self.assertEqual(conflict.conflict_type, ConflictType.VALUE_CONFLICT)
        self.assertEqual(len(conflict.conflicting_values), 2)
        self.assertIn(30, conflict.conflicting_values)
        self.assertIn(32, conflict.conflicting_values)

        # Test type conflicts
        type_entities = [
            {"id": "e2", "type": "Person", "source": "s1"},
            {"id": "e2", "type": "Organization", "source": "s2"},
        ]
        type_conflicts = detector.detect_type_conflicts(type_entities)
        self.assertEqual(len(type_conflicts), 1)
        self.assertEqual(type_conflicts[0].conflict_type, ConflictType.TYPE_CONFLICT)

    def test_conflict_resolver(self):
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_id="c1",
            conflict_type=ConflictType.VALUE_CONFLICT,
            entity_id="e1",
            property_name="age",
            conflicting_values=[30, 30, 32],
            sources=[
                {
                    "document": "doc1",
                    "confidence": 0.9,
                    "metadata": {"timestamp": datetime(2023, 1, 1)},
                },
                {
                    "document": "doc3",
                    "confidence": 0.9,
                    "metadata": {"timestamp": datetime(2023, 1, 2)},
                },
                {
                    "document": "doc2",
                    "confidence": 0.8,
                    "metadata": {"timestamp": datetime(2023, 6, 1)},
                },
            ],
        )

        # Test Voting
        result_voting = resolver.resolve_conflict(conflict, strategy="voting")
        self.assertTrue(result_voting.resolved)
        self.assertEqual(result_voting.resolved_value, 30)  # 30 appears twice

        # Test Most Recent
        result_recent = resolver.resolve_conflict(conflict, strategy="most_recent")
        self.assertTrue(result_recent.resolved)
        self.assertEqual(result_recent.resolved_value, 32)  # doc2 is most recent (June)

        # Test Highest Confidence
        # doc1 and doc3 have 0.9, doc2 has 0.8. Should pick 30 (first max confidence)
        result_conf = resolver.resolve_conflict(conflict, strategy="highest_confidence")
        self.assertTrue(result_conf.resolved)
        self.assertEqual(result_conf.resolved_value, 30)

    def test_conflict_analyzer(self):
        analyzer = ConflictAnalyzer()

        conflicts = [
            Conflict(
                conflict_id="c1",
                conflict_type=ConflictType.VALUE_CONFLICT,
                entity_id="e1",
                property_name="age",
                conflicting_values=[30, 32],
                sources=[{"document": "doc1"}, {"document": "doc2"}],
                severity="medium",
            ),
            Conflict(
                conflict_id="c2",
                conflict_type=ConflictType.TYPE_CONFLICT,
                entity_id="e2",
                property_name="type",
                conflicting_values=["Person", "Org"],
                sources=[{"document": "doc1"}, {"document": "doc3"}],
                severity="critical",
            ),
        ]

        analysis = analyzer.analyze_conflicts(conflicts)

        self.assertEqual(analysis["total_conflicts"], 2)
        self.assertEqual(analysis["by_severity"]["counts"]["critical"], 1)
        self.assertEqual(analysis["by_severity"]["counts"]["medium"], 1)
        self.assertIn("recommendations", analysis)

    def test_investigation_guide(self):
        generator = InvestigationGuideGenerator()

        conflict = Conflict(
            conflict_id="c1",
            conflict_type=ConflictType.VALUE_CONFLICT,
            entity_id="e1",
            property_name="age",
            conflicting_values=[30, 32],
            sources=[{"document": "doc1"}, {"document": "doc2"}],
            severity="medium",
        )

        guide = generator.generate_guide(conflict)

        self.assertEqual(guide.conflict_id, "c1")
        self.assertEqual(guide.severity, "medium")
        self.assertTrue(len(guide.investigation_steps) > 0)
        self.assertTrue(len(guide.recommended_actions) > 0)

        # Test checklist export
        checklist = generator.export_investigation_checklist(guide, format="text")
        self.assertIn("INVESTIGATION GUIDE: c1", checklist)

    def test_conflict_resolver_credibility_weighted(self):
        """Test credibility-weighted resolution strategy (#865)."""
        resolver = ConflictResolver()

        # Boost the credibility of "doc_trusted" so its value should win
        # even though it only has one vote, vs. two lower-credibility votes.
        # Use the validated setter rather than mutating the internal dict
        # directly, so the test stays coupled to the public API surface.
        resolver.source_tracker.set_source_credibility("doc_trusted", 1.0)
        resolver.source_tracker.set_source_credibility("doc_flaky", 0.1)

        conflict = Conflict(
            conflict_id="c_cred",
            conflict_type=ConflictType.VALUE_CONFLICT,
            entity_id="e1",
            property_name="age",
            conflicting_values=[30, 30, 40],
            sources=[
                {"document": "doc_flaky", "confidence": 0.9},
                {"document": "doc_flaky", "confidence": 0.9},
                {"document": "doc_trusted", "confidence": 0.9},
            ],
        )

        result = resolver.resolve_conflict(conflict, strategy="credibility_weighted")
        self.assertTrue(result.resolved)
        self.assertEqual(result.resolved_value, 40)
        self.assertEqual(result.resolution_strategy, "credibility_weighted")
        self.assertGreater(result.confidence, 0.0)

    def test_conflict_resolver_first_seen(self):
        """Test first-seen resolution strategy (#865)."""
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_id="c_first",
            conflict_type=ConflictType.VALUE_CONFLICT,
            entity_id="e1",
            property_name="age",
            conflicting_values=[30, 32],
            sources=[
                {"document": "doc1", "confidence": 0.9},
                {"document": "doc2", "confidence": 0.9},
            ],
        )

        result = resolver.resolve_conflict(conflict, strategy="first_seen")
        self.assertTrue(result.resolved)
        self.assertEqual(result.resolved_value, 30)  # first value in the list
        self.assertEqual(result.resolution_strategy, "first_seen")
        self.assertEqual(result.sources_used, ["doc1"])

    def test_conflict_resolver_manual_review(self):
        """Test manual-review resolution strategy flags without resolving (#865)."""
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_id="c_manual",
            conflict_type=ConflictType.VALUE_CONFLICT,
            entity_id="e1",
            property_name="age",
            conflicting_values=[30, 32],
            sources=[{"document": "doc1"}, {"document": "doc2"}],
            severity="high",
        )

        result = resolver.resolve_conflict(conflict, strategy="manual_review")
        self.assertFalse(result.resolved)
        self.assertEqual(result.resolution_strategy, "manual_review")
        self.assertTrue(result.metadata.get("requires_manual_review"))
        self.assertEqual(result.metadata.get("severity"), "high")

    def test_conflict_resolver_expert_review(self):
        """Test expert-review resolution strategy flags without resolving (#865)."""
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_id="c_expert",
            conflict_type=ConflictType.VALUE_CONFLICT,
            entity_id="e1",
            property_name="age",
            conflicting_values=[30, 32],
            sources=[{"document": "doc1"}, {"document": "doc2"}],
            severity="critical",
        )

        result = resolver.resolve_conflict(conflict, strategy="expert_review")
        self.assertFalse(result.resolved)
        self.assertEqual(result.resolution_strategy, "expert_review")
        self.assertTrue(result.metadata.get("requires_expert_review"))
        self.assertEqual(result.metadata.get("severity"), "critical")

    def test_conflict_detector_relationship_conflicts(self):
        """Test relationship conflict detection (#865)."""
        detector = ConflictDetector()

        relationships = [
            {
                "id": "r1",
                "source_id": "e1",
                "target_id": "e2",
                "type": "works_at",
                "source": "doc1",
            },
            {
                "id": "r1",
                "source_id": "e1",
                "target_id": "e2",
                "type": "founded",
                "source": "doc2",
            },
        ]

        conflicts = detector.detect_relationship_conflicts(relationships)
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertEqual(conflict.conflict_type, ConflictType.RELATIONSHIP_CONFLICT)
        self.assertEqual(conflict.relationship_id, "r1")
        self.assertEqual(conflict.property_name, "type")
        self.assertIn("works_at", conflict.conflicting_values)
        self.assertIn("founded", conflict.conflicting_values)

    def test_conflict_detector_relationship_conflicts_no_conflict(self):
        """Relationships with a single occurrence should not raise conflicts (#865)."""
        detector = ConflictDetector()

        relationships = [
            {"id": "r1", "source_id": "e1", "target_id": "e2", "type": "works_at"},
        ]

        conflicts = detector.detect_relationship_conflicts(relationships)
        self.assertEqual(len(conflicts), 0)

    def test_conflict_detector_temporal_conflicts(self):
        """Test temporal conflict detection (#865)."""
        detector = ConflictDetector()

        entities = [
            {"id": "e1", "founded": "1998", "source": "doc1", "confidence": 0.9},
            {"id": "e1", "founded": "2004", "source": "doc2", "confidence": 0.8},
        ]

        conflicts = detector.detect_temporal_conflicts(entities)
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertEqual(conflict.conflict_type, ConflictType.TEMPORAL_CONFLICT)
        self.assertEqual(conflict.entity_id, "e1")
        self.assertEqual(conflict.property_name, "founded")
        self.assertIn("1998", conflict.conflicting_values)
        self.assertIn("2004", conflict.conflicting_values)

    def test_conflict_detector_temporal_conflicts_no_conflict(self):
        """Matching temporal values across sources should not raise conflicts (#865)."""
        detector = ConflictDetector()

        entities = [
            {"id": "e1", "founded": "1998", "source": "doc1"},
            {"id": "e1", "founded": "1998", "source": "doc2"},
        ]

        conflicts = detector.detect_temporal_conflicts(entities)
        self.assertEqual(len(conflicts), 0)

    def test_conflict_detector_logical_conflicts(self):
        """Test logical conflict detection for incompatible entity types (#865)."""
        detector = ConflictDetector()

        entities = [
            {"id": "e1", "type": "Person", "source": "doc1"},
            {"id": "e1", "type": "Organization", "source": "doc2"},
        ]

        conflicts = detector.detect_logical_conflicts(entities)
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertEqual(conflict.conflict_type, ConflictType.LOGICAL_CONFLICT)
        self.assertEqual(conflict.entity_id, "e1")
        self.assertEqual(conflict.severity, "critical")
        self.assertIn("Person", conflict.conflicting_values)
        self.assertIn("Organization", conflict.conflicting_values)

    def test_conflict_detector_logical_conflicts_compatible_types(self):
        """Compatible/unrelated types should not raise logical conflicts (#865)."""
        detector = ConflictDetector()

        entities = [
            {"id": "e1", "type": "Person", "source": "doc1"},
            {"id": "e1", "type": "Employee", "source": "doc2"},
        ]

        conflicts = detector.detect_logical_conflicts(entities)
        self.assertEqual(len(conflicts), 0)

    def test_conflict_analyzer_by_source_breakdown(self):
        """Test the by_source breakdown of analyze_conflicts (#902)."""
        analyzer = ConflictAnalyzer()

        conflicts = [
            Conflict(
                conflict_id="c1",
                conflict_type=ConflictType.VALUE_CONFLICT,
                entity_id="e1",
                property_name="age",
                conflicting_values=[30, 32],
                sources=[{"document": "doc1"}, {"document": "doc2"}],
                severity="medium",
            ),
            Conflict(
                conflict_id="c2",
                conflict_type=ConflictType.TYPE_CONFLICT,
                entity_id="e2",
                property_name="type",
                conflicting_values=["Person", "Org"],
                sources=[{"document": "doc1"}, {"document": "doc3"}],
                severity="critical",
            ),
        ]

        analysis = analyzer.analyze_conflicts(conflicts)

        self.assertIn("by_source", analysis)
        by_source = analysis["by_source"]

        # doc1 appears in both conflicts, doc2 and doc3 in one each.
        self.assertEqual(by_source["counts"]["doc1"], 2)
        self.assertEqual(by_source["counts"]["doc2"], 1)
        self.assertEqual(by_source["counts"]["doc3"], 1)

        top_sources = {
            s["source"]: s["conflict_count"] for s in by_source["top_sources"]
        }
        self.assertEqual(top_sources["doc1"], 2)

        self.assertIn("doc1", by_source["details"])
        doc1_entries = by_source["details"]["doc1"]
        self.assertEqual(len(doc1_entries), 2)
        self.assertEqual({e["conflict_id"] for e in doc1_entries}, {"c1", "c2"})

    def test_conflict_analyzer_analyze_trends(self):
        """Test analyze_trends over deterministic, time-ordered data (#902)."""
        analyzer = ConflictAnalyzer()

        def make_conflict(conflict_id, timestamp):
            return Conflict(
                conflict_id=conflict_id,
                conflict_type=ConflictType.VALUE_CONFLICT,
                entity_id="e1",
                property_name="age",
                conflicting_values=[30, 32],
                sources=[{"document": "doc1", "metadata": {"timestamp": timestamp}}],
            )

        # January: 1 conflict. February: 3 conflicts (>10% increase -> "increasing").
        conflicts = [
            make_conflict("c1", "2023-01-05T00:00:00"),
            make_conflict("c2", "2023-02-01T00:00:00"),
            make_conflict("c3", "2023-02-10T00:00:00"),
            make_conflict("c4", "2023-02-20T00:00:00"),
        ]

        trends = analyzer.analyze_trends(conflicts)

        self.assertEqual(len(trends), 2)
        self.assertEqual(trends[0]["period"], "2023-01")
        self.assertEqual(trends[0]["conflict_count"], 1)
        self.assertEqual(trends[1]["period"], "2023-02")
        self.assertEqual(trends[1]["conflict_count"], 3)
        self.assertEqual(trends[1]["trend"], "increasing")
        self.assertEqual(trends[1]["trend_direction"], "up")

    def test_conflict_analyzer_analyze_trends_insufficient_data(self):
        """Single-period data should report insufficient_data, not crash (#902)."""
        analyzer = ConflictAnalyzer()

        conflict = Conflict(
            conflict_id="c1",
            conflict_type=ConflictType.VALUE_CONFLICT,
            entity_id="e1",
            property_name="age",
            conflicting_values=[30, 32],
            sources=[
                {"document": "doc1", "metadata": {"timestamp": "2023-01-05T00:00:00"}}
            ],
        )

        trends = analyzer.analyze_trends([conflict])

        self.assertEqual(len(trends), 1)
        self.assertEqual(trends[0]["trend"], "insufficient_data")
        self.assertEqual(trends[0]["conflict_count"], 1)


if __name__ == "__main__":
    unittest.main()