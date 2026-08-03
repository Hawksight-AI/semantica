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


if __name__ == "__main__":
    unittest.main()
