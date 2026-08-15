"""Regression tests for KG analytics node scope handling."""

import networkx as nx

from semantica.kg.centrality_calculator import CentralityCalculator
from semantica.kg.community_detector import CommunityDetector
from semantica.kg.connectivity_analyzer import ConnectivityAnalyzer


def _graph_with_isolated_node():
    return {
        "entities": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "relationships": [{"source": "A", "target": "B"}],
    }


def test_centrality_keeps_declared_isolated_nodes():
    result = CentralityCalculator().calculate_degree_centrality(
        _graph_with_isolated_node()
    )

    assert result["total_nodes"] == 3
    assert result["centrality"]["C"] == 0.0


def test_connectivity_reports_declared_isolated_nodes():
    result = ConnectivityAnalyzer().analyze_connectivity(
        _graph_with_isolated_node()
    )

    assert result["num_nodes"] == 3
    assert result["num_components"] == 2
    assert ["C"] in result["components"]
    assert result["is_connected"] is False


def test_community_detection_keeps_declared_isolated_nodes():
    detector = CommunityDetector()
    result = detector.detect_communities(_graph_with_isolated_node())

    assert set(result["node_assignments"]) == {"A", "B", "C"}
    metrics = detector.calculate_community_metrics(
        _graph_with_isolated_node(), result
    )
    assert metrics["num_communities"] == 2
    structure = detector.analyze_community_structure(
        _graph_with_isolated_node(), result
    )
    assert structure["num_communities"] == 2


def test_community_detection_returns_singletons_for_edgeless_graph():
    graph = {"entities": [{"id": "A"}, {"id": "B"}], "relationships": []}

    result = CommunityDetector().detect_communities(graph)

    assert {frozenset(community) for community in result["communities"]} == {
        frozenset({"A"}),
        frozenset({"B"}),
    }


def test_networkx_graph_keeps_isolated_nodes_for_analytics():
    graph = nx.Graph()
    graph.add_nodes_from(["A", "B", "C"])
    graph.add_edge("A", "B")

    centrality = CentralityCalculator().calculate_degree_centrality(graph)
    connectivity = ConnectivityAnalyzer().analyze_connectivity(graph)

    assert centrality["total_nodes"] == 3
    assert centrality["centrality"]["C"] == 0.0
    assert connectivity["num_nodes"] == 3
    assert connectivity["num_components"] == 2


def test_nodes_edges_payload_keeps_declared_isolated_nodes():
    graph = {
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "edges": [("A", "B")],
    }

    result = CentralityCalculator().calculate_degree_centrality(graph)

    assert result["total_nodes"] == 3
    assert result["centrality"]["C"] == 0.0


def test_name_and_text_nodes_are_kept_when_ids_are_missing():
    graph = {
        "entities": [{"name": "Alice"}, {"text": "Bob"}],
        "relationships": [],
    }

    result = CentralityCalculator().calculate_degree_centrality(graph)

    assert result["total_nodes"] == 2
    assert set(result["centrality"]) == {"Alice", "Bob"}


def test_community_metrics_accepts_communities_payload():
    detector = CommunityDetector()
    graph = {
        "entities": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "relationships": [{"source": "A", "target": "B"}],
    }
    result = {"communities": [["A", "B"], ["C"]]}

    metrics = detector.calculate_community_metrics(graph, result)

    assert metrics["num_communities"] == 2
    assert metrics["community_sizes"] == {0: 2, 1: 1}
