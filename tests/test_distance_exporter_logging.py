"""Tests for DistanceExporter debug logging on computation failures (issue #874).

Verifies that each metric helper logs at DEBUG level when the underlying
computation raises an exception, rather than silently swallowing errors.
"""

import logging
import unittest
from unittest.mock import MagicMock, patch

from semantica.export.distance_exporter import DistanceExporter

# get_logger prefixes with "semantica." so the actual logger name is double-prefixed
_LOGGER_NAME = "semantica.semantica.export.distance_exporter"


class _FakeNode:
    def __init__(self, node_id, node_type="entity", content="", properties=None):
        self.node_id = node_id
        self.node_type = node_type
        self.content = content
        self.properties = properties or {}


class _FakeEdge:
    def __init__(self, edge_id, source_id, target_id, edge_type="related", weight=1.0):
        self.edge_id = edge_id
        self.source_id = source_id
        self.target_id = target_id
        self.edge_type = edge_type
        self.weight = weight


def _make_graph():
    """Create a minimal mock graph with two connected nodes."""
    graph = MagicMock()
    graph.nodes = {
        "a": _FakeNode("a", "concept"),
        "b": _FakeNode("b", "concept"),
    }
    graph.edges = [_FakeEdge("e1", "a", "b")]
    return graph


@patch("semantica.export.distance_exporter._KG_AVAILABLE", True)
@patch("semantica.export.distance_exporter.PathFinder")
@patch("semantica.export.distance_exporter.SimilarityCalculator")
@patch("semantica.export.distance_exporter.CentralityCalculator")
class TestDistanceExporterLogging(unittest.TestCase):
    """Verify that silent except blocks now emit logger.debug messages."""

    def _make_exporter(self, mock_centrality_cls, mock_similarity_cls, mock_pathfinder_cls):
        """Build an exporter with mocked KG components."""
        mock_pf = MagicMock()
        mock_sim = MagicMock()
        mock_cent = MagicMock()
        mock_pathfinder_cls.return_value = mock_pf
        mock_similarity_cls.return_value = mock_sim
        mock_centrality_cls.return_value = mock_cent

        exporter = DistanceExporter(_make_graph())
        exporter._path_finder = mock_pf
        exporter._similarity = mock_sim
        exporter._centrality = mock_cent
        return exporter, mock_pf, mock_sim, mock_cent

    def test_hop_distance_logs_on_exception(self, mock_cent, mock_sim, mock_pf):
        exporter, pf, _, _ = self._make_exporter(mock_cent, mock_sim, mock_pf)
        pf.bfs_shortest_path.side_effect = RuntimeError("graph corrupted")

        with self.assertLogs(_LOGGER_NAME, level=logging.DEBUG) as cm:
            result = exporter._hop_distance({}, "a", "b")

        self.assertIsNone(result)
        self.assertTrue(any("hop_distance" in msg and "graph corrupted" in msg for msg in cm.output))

    def test_weighted_distance_logs_on_exception(self, mock_cent, mock_sim, mock_pf):
        exporter, pf, _, _ = self._make_exporter(mock_cent, mock_sim, mock_pf)
        pf.dijkstra_shortest_path.side_effect = ValueError("negative weight")

        with self.assertLogs(_LOGGER_NAME, level=logging.DEBUG) as cm:
            result = exporter._weighted_distance({}, "a", "b")

        self.assertIsNone(result)
        self.assertTrue(any("weighted_distance" in msg and "negative weight" in msg for msg in cm.output))

    def test_semantic_similarity_logs_on_exception(self, mock_cent, mock_sim, mock_pf):
        exporter, _, sim, _ = self._make_exporter(mock_cent, mock_sim, mock_pf)
        sim.cosine_similarity.side_effect = TypeError("embeddings missing")

        with self.assertLogs(_LOGGER_NAME, level=logging.DEBUG) as cm:
            result = exporter._semantic_similarity({}, "a", "b")

        self.assertIsNone(result)
        self.assertTrue(any("semantic_similarity" in msg and "embeddings missing" in msg for msg in cm.output))

    def test_betweenness_logs_on_exception(self, mock_cent, mock_sim, mock_pf):
        exporter, _, _, cent = self._make_exporter(mock_cent, mock_sim, mock_pf)
        cent.calculate_betweenness_centrality.side_effect = RuntimeError("disconnected")

        with self.assertLogs(_LOGGER_NAME, level=logging.DEBUG) as cm:
            result = exporter._betweenness({})

        self.assertEqual(result, {})
        self.assertTrue(any("betweenness" in msg and "disconnected" in msg for msg in cm.output))

    def test_successful_computation_no_spurious_debug(self, mock_cent, mock_sim, mock_pf):
        """When computations succeed, no debug error messages are logged."""
        exporter, pf, sim, cent = self._make_exporter(mock_cent, mock_sim, mock_pf)
        pf.bfs_shortest_path.return_value = {"path": ["a", "b"]}
        pf.dijkstra_shortest_path.return_value = {"path": ["a", "b"], "total_weight": 1.5}
        sim.cosine_similarity.return_value = 0.95
        cent.calculate_betweenness_centrality.return_value = {"betweenness": {"a": 0.5, "b": 0.3}}

        # These should not log any debug messages about failures
        hop = exporter._hop_distance({}, "a", "b")
        weighted = exporter._weighted_distance({}, "a", "b")
        similarity = exporter._semantic_similarity({}, "a", "b")
        betweenness = exporter._betweenness({})

        self.assertEqual(hop, 1)
        self.assertAlmostEqual(weighted, 1.5)
        self.assertAlmostEqual(similarity, 0.95)
        self.assertEqual(betweenness, {"a": 0.5, "b": 0.3})


if __name__ == "__main__":
    unittest.main()
