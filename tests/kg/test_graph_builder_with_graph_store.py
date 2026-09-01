"""
Test for GraphBuilder with GraphStore backend (Issue #1135).

This test verifies that GraphBuilder correctly works with the GraphStore
facade interface, not with raw backend stores like Neo4jStore.
"""
import unittest
from unittest.mock import MagicMock, patch


class TestGraphBuilderWithGraphStore(unittest.TestCase):
    """Test GraphBuilder integration with GraphStore facade."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock progress tracker
        self.mock_tracker_patcher = patch("semantica.utils.progress_tracker.get_progress_tracker")
        self.mock_get_tracker = self.mock_tracker_patcher.start()
        self.mock_tracker = MagicMock()
        self.mock_get_tracker.return_value = self.mock_tracker

    def tearDown(self):
        """Clean up after tests."""
        self.mock_tracker_patcher.stop()

    def test_graph_builder_with_graph_store_facade(self):
        """Test that GraphBuilder works with GraphStore facade (Issue #1135)."""
        from semantica.kg.graph_builder import GraphBuilder
        from semantica.graph_store import GraphStore

        # Create a mock GraphStore facade
        mock_store = MagicMock(spec=GraphStore)
        mock_store.add_nodes.return_value = 2
        mock_store.add_edges.return_value = 1

        # Create GraphBuilder with the GraphStore facade
        builder = GraphBuilder(
            merge_entities=False,
            resolve_conflicts=False,
            graph_store=mock_store
        )

        # Build a simple graph
        entities = [
            {"id": "alice", "type": "Person"},
            {"id": "bob", "type": "Person"},
        ]
        relationships = [
            {"source": "alice", "target": "bob", "type": "knows"},
        ]

        graph = builder.build({
            "entities": entities,
            "relationships": relationships
        })

        # Verify the graph was built
        self.assertEqual(len(graph["entities"]), 2)
        self.assertEqual(len(graph["relationships"]), 1)

        # Verify that add_nodes and add_edges were called on the GraphStore
        mock_store.add_nodes.assert_called_once()
        mock_store.add_edges.assert_called_once()

    def test_graph_builder_without_graph_store_still_works(self):
        """Test that GraphBuilder still works without a graph_store parameter."""
        from semantica.kg.graph_builder import GraphBuilder

        # Create GraphBuilder without graph_store
        builder = GraphBuilder(
            merge_entities=False,
            resolve_conflicts=False
        )

        # Build a simple graph
        entities = [
            {"id": "alice", "type": "Person"},
            {"id": "bob", "type": "Person"},
        ]
        relationships = [
            {"source": "alice", "target": "bob", "type": "knows"},
        ]

        graph = builder.build({
            "entities": entities,
            "relationships": relationships
        })

        # Verify the graph was built
        self.assertEqual(len(graph["entities"]), 2)
        self.assertEqual(len(graph["relationships"]), 1)
        self.assertEqual(graph["metadata"]["num_entities"], 2)
        self.assertEqual(graph["metadata"]["num_relationships"], 1)


if __name__ == "__main__":
    unittest.main()
