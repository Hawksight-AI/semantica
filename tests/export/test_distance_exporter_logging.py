"""Tests for DistanceExporter error logging.

Verifies that the four metric helper methods log debug messages (rather
than silently swallowing exceptions) when the underlying computation
raises an error.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from semantica.export.distance_exporter import DistanceExporter


@pytest.fixture
def mock_graph():
    """Minimal graph mock with two nodes."""
    graph = MagicMock()
    node_a = MagicMock(node_id="a", node_type="entity", content="A", properties={})
    node_b = MagicMock(node_id="b", node_type="entity", content="B", properties={})
    graph.nodes = {"a": node_a, "b": node_b}
    graph.edges = []
    return graph


@pytest.fixture
def exporter_with_mocked_kg(mock_graph):
    """DistanceExporter with mocked KG components (regardless of install)."""
    exporter = DistanceExporter(mock_graph)
    # Force KG components to be present (mocked)
    exporter._path_finder = MagicMock()
    exporter._similarity = MagicMock()
    exporter._centrality = MagicMock()
    return exporter


class TestDistanceExporterErrorLogging:
    """Verify that silent exception swallowing is replaced with debug logging."""

    def test_hop_distance_logs_on_failure(self, exporter_with_mocked_kg, caplog):
        """_hop_distance should log when bfs_shortest_path raises."""
        exporter = exporter_with_mocked_kg
        exporter._path_finder.bfs_shortest_path = MagicMock(
            side_effect=RuntimeError("graph corrupted")
        )
        graph_dict = exporter._build_graph_dict()

        with caplog.at_level(logging.DEBUG):
            result = exporter._hop_distance(graph_dict, "a", "b")

        assert result is None
        assert "hop_distance(a, b) failed" in caplog.text
        assert "graph corrupted" in caplog.text

    def test_weighted_distance_logs_on_failure(self, exporter_with_mocked_kg, caplog):
        """_weighted_distance should log when dijkstra_shortest_path raises."""
        exporter = exporter_with_mocked_kg
        exporter._path_finder.dijkstra_shortest_path = MagicMock(
            side_effect=ValueError("negative weight")
        )
        graph_dict = exporter._build_graph_dict()

        with caplog.at_level(logging.DEBUG):
            result = exporter._weighted_distance(graph_dict, "a", "b")

        assert result is None
        assert "weighted_distance(a, b) failed" in caplog.text
        assert "negative weight" in caplog.text

    def test_semantic_similarity_logs_on_failure(self, exporter_with_mocked_kg, caplog):
        """_semantic_similarity should log when cosine_similarity raises."""
        exporter = exporter_with_mocked_kg
        exporter._similarity.cosine_similarity = MagicMock(
            side_effect=TypeError("embedding not found")
        )
        graph_dict = exporter._build_graph_dict()

        with caplog.at_level(logging.DEBUG):
            result = exporter._semantic_similarity(graph_dict, "a", "b")

        assert result is None
        assert "semantic_similarity(a, b) failed" in caplog.text
        assert "embedding not found" in caplog.text

    def test_betweenness_logs_on_failure(self, exporter_with_mocked_kg, caplog):
        """_betweenness should log when calculate_betweenness_centrality raises."""
        exporter = exporter_with_mocked_kg
        exporter._centrality.calculate_betweenness_centrality = MagicMock(
            side_effect=RuntimeError("unsupported graph structure")
        )
        graph_dict = exporter._build_graph_dict()

        with caplog.at_level(logging.DEBUG):
            result = exporter._betweenness(graph_dict)

        assert result == {}
        assert "betweenness_centrality failed" in caplog.text
        assert "unsupported graph structure" in caplog.text

    def test_compute_pairs_still_produces_rows_on_metric_failure(
        self, exporter_with_mocked_kg, caplog
    ):
        """compute_pairs should still produce rows even when all metrics fail."""
        exporter = exporter_with_mocked_kg
        exporter._path_finder.bfs_shortest_path = MagicMock(
            side_effect=RuntimeError("fail")
        )
        exporter._path_finder.dijkstra_shortest_path = MagicMock(
            side_effect=RuntimeError("fail")
        )
        exporter._similarity.cosine_similarity = MagicMock(
            side_effect=RuntimeError("fail")
        )
        exporter._centrality.calculate_betweenness_centrality = MagicMock(
            side_effect=RuntimeError("fail")
        )

        with caplog.at_level(logging.DEBUG):
            rows = exporter.compute_pairs()

        # 2 nodes → 2 directed pairs (a→b and b→a)
        assert len(rows) == 2
        assert rows[0]["hop_count"] is None
        assert rows[0]["weighted_distance"] is None
        assert rows[0]["semantic_similarity"] is None
        # Verify errors were logged
        assert "failed" in caplog.text
