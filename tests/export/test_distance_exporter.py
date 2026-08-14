"""Tests for DistanceExporter's silent-exception handling (issue #874).

Each of the four private metric helpers (_betweenness, _hop_distance,
_weighted_distance, _semantic_similarity) wraps its computation in a bare
except Exception and returns None/{} with no signal, so a raised exception is
indistinguishable in the exported data from a legitimate "no path" result.
"""

import logging

import pytest

from semantica.export.distance_exporter import DistanceExporter


class _Node:
    def __init__(self, node_id):
        self.node_id = node_id
        self.node_type = "t"
        self.content = ""
        self.properties = {}


class _Graph:
    def __init__(self):
        self.nodes = {"a": _Node("a"), "b": _Node("b")}
        self.edges = []


class _RaisingPathFinder:
    def bfs_shortest_path(self, graph_dict, src, tgt):
        raise RuntimeError("bfs boom")

    def dijkstra_shortest_path(self, graph_dict, src, tgt):
        raise RuntimeError("dijkstra boom")


class _RaisingSimilarity:
    def cosine_similarity(self, graph_dict, src, tgt):
        raise RuntimeError("cosine boom")


class _RaisingCentrality:
    def calculate_betweenness_centrality(self, graph_dict):
        raise RuntimeError("betweenness boom")


@pytest.fixture
def exporter():
    exp = DistanceExporter(_Graph())
    exp._path_finder = _RaisingPathFinder()
    exp._similarity = _RaisingSimilarity()
    exp._centrality = _RaisingCentrality()
    return exp


def test_hop_distance_logs_warning_on_exception(exporter, caplog):
    with caplog.at_level(logging.WARNING, logger="semantica.export.distance_exporter"):
        result = exporter._hop_distance({}, "a", "b")
    value, error = result
    assert value is None
    assert error == "hop_count"
    assert any("Hop distance" in rec.message for rec in caplog.records)


def test_weighted_distance_logs_warning_on_exception(exporter, caplog):
    with caplog.at_level(logging.WARNING, logger="semantica.export.distance_exporter"):
        result = exporter._weighted_distance({}, "a", "b")
    value, error = result
    assert value is None
    assert error == "weighted_distance"
    assert any("Weighted distance" in rec.message for rec in caplog.records)


def test_semantic_similarity_logs_warning_on_exception(exporter, caplog):
    with caplog.at_level(logging.WARNING, logger="semantica.export.distance_exporter"):
        result = exporter._semantic_similarity({}, "a", "b")
    value, error = result
    assert value is None
    assert error == "semantic_similarity"
    assert any("Semantic similarity" in rec.message for rec in caplog.records)


def test_betweenness_logs_warning_on_exception(exporter, caplog):
    with caplog.at_level(logging.WARNING, logger="semantica.export.distance_exporter"):
        result = exporter._betweenness({})
    value, error = result
    assert value == {}
    assert error == "betweenness"
    assert any("Betweenness" in rec.message for rec in caplog.records)


def test_compute_pairs_still_produces_none_sentinels_when_metrics_raise(exporter, caplog):
    """The exported row shape is unchanged: a raised exception still yields
    None/"distant", it is just no longer silent."""
    with caplog.at_level(logging.WARNING, logger="semantica.export.distance_exporter"):
        rows = exporter.compute_pairs()
    assert len(rows) == 2
    for row in rows:
        assert row["hop_count"] is None
        assert row["weighted_distance"] is None
        assert row["semantic_similarity"] is None
        assert row["distance_band"] == "distant"
    assert len(caplog.records) >= 4


def test_hop_distance_no_warning_when_kg_unavailable(caplog):
    """A legitimate 'no KG backend' None (the pre-existing early-return path)
    must not be confused with an exception; nothing to log there."""
    exp = DistanceExporter(_Graph())
    exp._path_finder = None
    with caplog.at_level(logging.WARNING, logger="semantica.export.distance_exporter"):
        result = exp._hop_distance({}, "a", "b")
    value, error = result
    assert value is None
    assert error is None
    assert len(caplog.records) == 0
