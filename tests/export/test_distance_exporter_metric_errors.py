"""Tests for DistanceExporter metric_errors column.

Verifies that when ``include=["metric_errors"]`` is passed to
``compute_pairs()``, the exported rows contain a ``metric_errors`` field
that distinguishes computation failures from legitimate None results.
"""

import logging
from unittest.mock import MagicMock

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
def exporter(mock_graph):
    """DistanceExporter with mocked KG components."""
    exp = DistanceExporter(mock_graph)
    exp._path_finder = MagicMock()
    exp._similarity = MagicMock()
    exp._centrality = MagicMock()
    return exp


class TestMetricErrorsColumn:
    """Tests for the opt-in metric_errors export column."""

    def test_metric_errors_empty_on_success(self, exporter):
        """When all metrics succeed, metric_errors is an empty string."""
        exporter._path_finder.bfs_shortest_path.return_value = {"path": ["a", "x", "b"]}
        exporter._path_finder.dijkstra_shortest_path.return_value = {"total_weight": 2.5, "path": ["a", "b"]}
        exporter._similarity.cosine_similarity.return_value = 0.87

        rows = exporter.compute_pairs(include=["hop_count", "weighted_distance", "semantic_similarity", "metric_errors"])

        assert len(rows) == 2  # a->b and b->a
        for row in rows:
            assert "metric_errors" in row
            assert row["metric_errors"] == ""

    def test_metric_errors_records_single_failure(self, exporter):
        """When one metric fails, its name appears in metric_errors."""
        exporter._path_finder.bfs_shortest_path.return_value = {"path": ["a", "b"]}
        exporter._path_finder.dijkstra_shortest_path.side_effect = RuntimeError("negative cycle")
        exporter._similarity.cosine_similarity.return_value = 0.5

        rows = exporter.compute_pairs(include=["hop_count", "weighted_distance", "semantic_similarity", "metric_errors"])

        for row in rows:
            assert row["metric_errors"] == "weighted_distance"
            assert row["hop_count"] == 1  # still computed
            assert row["weighted_distance"] is None  # failed
            assert row["semantic_similarity"] == 0.5  # still computed

    def test_metric_errors_records_multiple_failures(self, exporter):
        """When multiple metrics fail, all names appear comma-separated."""
        exporter._path_finder.bfs_shortest_path.side_effect = RuntimeError("fail")
        exporter._path_finder.dijkstra_shortest_path.side_effect = RuntimeError("fail")
        exporter._similarity.cosine_similarity.side_effect = TypeError("fail")
        exporter._centrality.calculate_betweenness_centrality.side_effect = RuntimeError("fail")

        rows = exporter.compute_pairs(include=[
            "hop_count", "weighted_distance", "semantic_similarity",
            "source_betweenness", "metric_errors",
        ])

        for row in rows:
            errors = row["metric_errors"].split(",")
            assert "hop_count" in errors
            assert "weighted_distance" in errors
            assert "semantic_similarity" in errors
            assert "betweenness" in errors
            assert row["hop_count"] is None
            assert row["weighted_distance"] is None
            assert row["semantic_similarity"] is None

    def test_metric_errors_absent_when_not_requested(self, exporter):
        """When metric_errors is not in include, it doesn't appear in rows."""
        exporter._path_finder.bfs_shortest_path.side_effect = RuntimeError("fail")
        exporter._path_finder.dijkstra_shortest_path.return_value = {"total_weight": 1.0, "path": ["a", "b"]}
        exporter._similarity.cosine_similarity.return_value = 0.9

        rows = exporter.compute_pairs(include=["hop_count", "weighted_distance", "semantic_similarity"])

        for row in rows:
            assert "metric_errors" not in row

    def test_metric_errors_distinguishes_no_path_from_error(self, exporter):
        """Core distinction: None from 'no path' has empty error; None from exception has the metric name."""
        # bfs returns empty path (legitimate "no path") — NOT an error
        exporter._path_finder.bfs_shortest_path.return_value = {"path": []}
        # dijkstra raises (computation error)
        exporter._path_finder.dijkstra_shortest_path.side_effect = ValueError("bad weight")
        exporter._similarity.cosine_similarity.return_value = 0.3

        rows = exporter.compute_pairs(include=["hop_count", "weighted_distance", "semantic_similarity", "metric_errors"])

        for row in rows:
            # Both are None, but only weighted_distance is an error
            assert row["hop_count"] is None
            assert row["weighted_distance"] is None
            assert row["metric_errors"] == "weighted_distance"

    def test_default_columns_unchanged_without_metric_errors(self, exporter):
        """Default column set (no metric_errors) produces the same schema as before."""
        exporter._path_finder.bfs_shortest_path.return_value = {"path": ["a", "b"]}
        exporter._path_finder.dijkstra_shortest_path.return_value = {"total_weight": 1.0, "path": ["a", "b"]}
        exporter._similarity.cosine_similarity.return_value = 0.5
        exporter._centrality.calculate_betweenness_centrality.return_value = {"betweenness": {"a": 0.5, "b": 0.3}}

        rows = exporter.compute_pairs()

        assert len(rows) == 2
        expected_keys = {
            "source_id", "source_type", "target_id", "target_type",
            "hop_count", "weighted_distance", "semantic_similarity",
            "distance_band", "source_betweenness", "target_betweenness",
        }
        assert set(rows[0].keys()) == expected_keys
        assert "metric_errors" not in rows[0]
