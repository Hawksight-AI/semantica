"""
Test suite for Path Finder module.

This module tests the PathFinder class and its various path finding
algorithms for knowledge graphs.
"""

import pytest
import networkx as nx
from unittest.mock import Mock

from semantica.kg.path_finder import PathFinder


class TestPathFinder:
    """Test cases for PathFinder class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.finder = PathFinder()
        
        # Create test graphs
        self.simple_graph = nx.Graph()
        self.simple_graph.add_edges_from([
            ("A", "B"), ("B", "C"), ("C", "D"), ("A", "D")
        ])
        
        self.weighted_graph = nx.Graph()
        self.weighted_graph.add_weighted_edges_from([
            ("A", "B", 1), ("B", "C", 2), ("C", "D", 1), ("A", "D", 5)
        ])
        
        self.disconnected_graph = nx.Graph()
        self.disconnected_graph.add_edges_from([
            ("A", "B"), ("B", "C")
        ])
        self.disconnected_graph.add_node("D")  # Isolated node
        
        # Mock graph store
        self.mock_graph = Mock()
        self.mock_graph.nodes.return_value = ["A", "B", "C", "D"]
        self.mock_graph.has_node.return_value = True
        self.mock_graph.neighbors.return_value = []
        self.mock_graph.get_edge_data.return_value = {}
    
    def test_init_default(self):
        """Test PathFinder initialization with default parameters."""
        finder = PathFinder()
        assert finder.default_algorithm == "dijkstra"
    
    def test_init_custom_algorithm(self):
        """Test PathFinder initialization with custom algorithm."""
        finder = PathFinder(default_algorithm="astar")
        assert finder.default_algorithm == "astar"
    
    def test_init_invalid_algorithm(self):
        """Test PathFinder initialization with invalid algorithm."""
        with pytest.raises(ValueError, match="Unsupported default algorithm"):
            PathFinder(default_algorithm="invalid_algorithm")
    
    def test_dijkstra_shortest_path_simple(self):
        """Test Dijkstra's algorithm on simple graph."""
        path = self.finder.dijkstra_shortest_path(self.simple_graph, "A", "D")
        
        assert path in [["A", "D"], ["A", "B", "C", "D"]]
        assert path[0] == "A"
        assert path[-1] == "D"
    
    def test_dijkstra_shortest_path_weighted(self):
        """Test Dijkstra's algorithm on weighted graph."""
        path = self.finder.dijkstra_shortest_path(self.weighted_graph, "A", "D")
        
        # Should prefer path A-B-C-D (total weight 4) over A-D (weight 5)
        assert path == ["A", "B", "C", "D"]
    
    def test_dijkstra_shortest_path_no_path(self):
        """Test Dijkstra's algorithm with no path available."""
        path = self.finder.dijkstra_shortest_path(self.disconnected_graph, "A", "D")
        assert path == []
    
    def test_dijkstra_shortest_path_same_node(self):
        """Test Dijkstra's algorithm with same source and target."""
        path = self.finder.dijkstra_shortest_path(self.simple_graph, "A", "A")
        assert path == ["A"]
    
    def test_dijkstra_shortest_path_node_not_found(self):
        """Test Dijkstra's algorithm with non-existent node."""
        with pytest.raises(ValueError, match="Source node X not found"):
            self.finder.dijkstra_shortest_path(self.simple_graph, "X", "A")
        
        with pytest.raises(ValueError, match="Target node X not found"):
            self.finder.dijkstra_shortest_path(self.simple_graph, "A", "X")
    
    def test_dijkstra_shortest_path_custom_weights(self):
        """Test Dijkstra's algorithm with custom weight parameters."""
        path = self.finder.dijkstra_shortest_path(
            self.weighted_graph, 
            "A", "D",
            weight_attribute="weight",
            default_weight=2.0
        )
        assert path == ["A", "B", "C", "D"]
    
    def test_a_star_search_simple(self):
        """Test A* search on simple graph."""
        def heuristic(node1, node2):
            # Simple heuristic: 0 for all nodes (falls back to Dijkstra)
            return 0
        
        path = self.finder.a_star_search(self.simple_graph, "A", "D", heuristic)
        
        assert path in [["A", "D"], ["A", "B", "C", "D"]]
        assert path[0] == "A"
        assert path[-1] == "D"
    
    def test_a_star_search_weighted(self):
        """Test A* search on weighted graph."""
        def heuristic(node1, node2):
            # Simple heuristic based on node names (for testing)
            return 0
        
        path = self.finder.a_star_search(self.weighted_graph, "A", "D", heuristic)
        
        assert path == ["A", "B", "C", "D"]
    
    def test_a_star_search_no_path(self):
        """Test A* search with no path available."""
        def heuristic(node1, node2):
            return 0
        
        path = self.finder.a_star_search(self.disconnected_graph, "A", "D", heuristic)
        assert path == []
    
    def test_a_star_search_node_not_found(self):
        """Test A* search with non-existent node."""
        def heuristic(node1, node2):
            return 0
        
        with pytest.raises(ValueError, match="Source node X not found"):
            self.finder.a_star_search(self.simple_graph, "X", "A", heuristic)
    
    def test_bfs_shortest_path_unweighted(self):
        """Test BFS shortest path on unweighted graph."""
        path = self.finder.bfs_shortest_path(self.simple_graph, "A", "D")
        
        # BFS should find the direct edge A-D
        assert path == ["A", "D"]
    
    def test_bfs_shortest_path_no_path(self):
        """Test BFS shortest path with no path available."""
        path = self.finder.bfs_shortest_path(self.disconnected_graph, "A", "D")
        assert path == []
    
    def test_bfs_shortest_path_node_not_found(self):
        """Test BFS shortest path with non-existent node."""
        with pytest.raises(ValueError, match="Source node X not found"):
            self.finder.bfs_shortest_path(self.simple_graph, "X", "A")
    
    def test_all_shortest_paths(self):
        """Test finding all shortest paths from a source."""
        paths = self.finder.all_shortest_paths(self.simple_graph, "A")
        
        assert "B" in paths
        assert "C" in paths
        assert "D" in paths
        
        # Check that paths are valid
        for target, path_list in paths.items():
            for path in path_list:
                assert path[0] == "A"
                assert path[-1] == target
    
    def test_all_shortest_paths_weighted(self):
        """Test all shortest paths on weighted graph."""
        paths = self.finder.all_shortest_paths(self.weighted_graph, "A")
        
        assert "D" in paths
        # Should find the shortest path A-B-C-D
        assert ["A", "B", "C", "D"] in paths["D"]
    
    def test_all_shortest_paths_node_not_found(self):
        """Test all shortest paths with non-existent source."""
        with pytest.raises(ValueError, match="Source node X not found"):
            self.finder.all_shortest_paths(self.simple_graph, "X")
    
    def test_path_length(self):
        """Test path length calculation."""
        path = ["A", "B", "C", "D"]
        
        # Unweighted graph
        length = self.finder.path_length(self.simple_graph, path)
        assert length == 3.0  # 3 edges
        
        # Weighted graph
        length = self.finder.path_length(self.weighted_graph, path)
        assert length == 4.0  # 1 + 2 + 1
    
    def test_path_length_invalid_path(self):
        """Test path length calculation with invalid path."""
        path = ["A", "X", "D"]  # X doesn't exist
        
        with pytest.raises(ValueError, match="No edge found"):
            self.finder.path_length(self.simple_graph, path)
    
    def test_path_length_single_node(self):
        """Test path length calculation with single node."""
        path = ["A"]
        length = self.finder.path_length(self.simple_graph, path)
        assert length == 0.0
    
    def test_path_length_custom_weights(self):
        """Test path length calculation with custom weight parameters."""
        path = ["A", "B", "C", "D"]
        
        length = self.finder.path_length(
            self.weighted_graph, 
            path,
            weight_attribute="weight",
            default_weight=2.0
        )
        assert length == 4.0
    
    def test_find_k_shortest_paths(self):
        """Test finding k shortest paths."""
        # Create a graph with multiple paths
        multi_path_graph = nx.Graph()
        multi_path_graph.add_edges_from([
            ("A", "B"), ("B", "D"),  # Path 1
            ("A", "C"), ("C", "D"),  # Path 2
            ("A", "D")               # Direct path
        ])
        
        paths = self.finder.find_k_shortest_paths(multi_path_graph, "A", "D", k=3)
        
        assert len(paths) <= 3
        for path in paths:
            assert path[0] == "A"
            assert path[-1] == "D"
        
        # Paths should be ordered by length (shortest first)
        if len(paths) > 1:
            lengths = [self.finder.path_length(multi_path_graph, path) for path in paths]
            assert all(lengths[i] <= lengths[i+1] for i in range(len(lengths)-1))

    def test_find_k_shortest_paths_preserves_graph(self):
        """Test k-shortest path search does not mutate the input graph."""
        graph = nx.Graph()
        graph.add_edges_from([
            ("A", "X"), ("X", "Y"), ("Y", "E"),
            ("A", "B"), ("B", "C"), ("C", "E"),
        ])
        original_nodes = set(graph.nodes)
        original_edges = set(graph.edges)

        paths = self.finder.find_k_shortest_paths(graph, "A", "E", k=5)

        assert len(paths) == 2
        assert set(graph.nodes) == original_nodes
        assert set(graph.edges) == original_edges

    def test_find_k_shortest_paths_returns_loopless_paths(self):
        """Test k-shortest paths do not repeat nodes."""
        graph = nx.Graph()
        graph.add_edges_from([
            ("A", "D"), ("A", "E"), ("A", "C"),
            ("B", "D"), ("B", "C"),
        ])

        paths = self.finder.find_k_shortest_paths(graph, "A", "B", k=5)

        assert paths == [["A", "C", "B"], ["A", "D", "B"]]
        assert all(len(path) == len(set(path)) for path in paths)

    def test_dijkstra_exclusion_respects_undirected_traversal(self):
        """Test exclusions apply in both directions for undirected traversal."""
        graph = nx.DiGraph()
        graph.add_edge("A", "B")

        path = self.finder._dijkstra_shortest_path(
            graph,
            "B",
            "A",
            directed=False,
            excluded_edges={("A", "B")},
        )

        assert path == []

    def test_find_k_shortest_paths_no_path(self):
        """Test finding k shortest paths with no path available."""
        paths = self.finder.find_k_shortest_paths(self.disconnected_graph, "A", "D", k=3)
        assert paths == []
    
    def test_find_k_shortest_paths_invalid_k(self):
        """Test finding k shortest paths with invalid k."""
        with pytest.raises(ValueError, match="k must be positive"):
            self.finder.find_k_shortest_paths(self.simple_graph, "A", "D", k=0)
    
    def test_node_exists_networkx(self):
        """Test node existence check with NetworkX graph."""
        assert self.finder._node_exists(self.simple_graph, "A")
        assert not self.finder._node_exists(self.simple_graph, "X")
    
    def test_node_exists_mock_graph(self):
        """Test node existence check with mock graph."""
        self.mock_graph.has_node.return_value = True
        assert self.finder._node_exists(self.mock_graph, "A")
        
        self.mock_graph.has_node.return_value = False
        assert not self.finder._node_exists(self.mock_graph, "X")
    
    def test_get_neighbors_networkx(self):
        """Test getting neighbors with NetworkX graph."""
        neighbors = self.finder._get_neighbors(self.simple_graph, "A")
        neighbor_ids = [neighbor for neighbor, _ in neighbors]
        
        assert "B" in neighbor_ids
        assert "D" in neighbor_ids
    
    def test_get_neighbors_mock_graph(self):
        """Test getting neighbors with mock graph."""
        self.mock_graph.neighbors.return_value = ["B", "D"]
        self.mock_graph.get_edge_data.return_value = {}
        
        neighbors = self.finder._get_neighbors(self.mock_graph, "A")
        neighbor_ids = [neighbor for neighbor, _ in neighbors]
        
        assert "B" in neighbor_ids
        assert "D" in neighbor_ids
    
    def test_get_edge_data_networkx(self):
        """Test getting edge data with NetworkX graph."""
        edge_data = self.finder._get_edge_data(self.weighted_graph, "A", "B")
        assert edge_data == {"weight": 1}
    
    def test_get_edge_data_mock_graph(self):
        """Test getting edge data with mock graph."""
        self.mock_graph.get_edge_data.return_value = {"weight": 2}
        
        edge_data = self.finder._get_edge_data(self.mock_graph, "A", "B")
        assert edge_data == {"weight": 2}
    
    def test_get_edge_weight_dict(self):
        """Test getting edge weight from dictionary."""
        edge_data = {"weight": 5, "type": "related"}
        weight = self.finder._get_edge_weight(edge_data, "weight", 1.0)
        assert weight == 5
    
    def test_get_edge_weight_missing(self):
        """Test getting edge weight with missing attribute."""
        edge_data = {"type": "related"}
        weight = self.finder._get_edge_weight(edge_data, "weight", 1.0)
        assert weight == 1.0
    
    def test_get_edge_weight_non_dict(self):
        """Test getting edge weight from non-dictionary."""
        edge_data = None
        weight = self.finder._get_edge_weight(edge_data, "weight", 1.0)
        assert weight == 1.0


class TestPathFinderEdgeCases:
    """Edge case tests for PathFinder."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.finder = PathFinder()
    
    def test_empty_graph(self):
        """Test path finding on empty graph."""
        empty_graph = nx.Graph()
        
        with pytest.raises(ValueError, match="Source node A not found"):
            self.finder.dijkstra_shortest_path(empty_graph, "A", "B")
    
    def test_single_node_graph(self):
        """Test path finding on single node graph."""
        single_node_graph = nx.Graph()
        single_node_graph.add_node("A")
        
        # Same source and target
        path = self.finder.dijkstra_shortest_path(single_node_graph, "A", "A")
        assert path == ["A"]
        
        # Different nodes (target doesn't exist)
        with pytest.raises(ValueError, match="Target node B not found"):
            self.finder.dijkstra_shortest_path(single_node_graph, "A", "B")
    
    def test_cycle_graph(self):
        """Test path finding on cycle graph."""
        cycle_graph = nx.cycle_graph(4)  # 0-1-2-3-0
        # Convert to string nodes for consistency
        cycle_graph = nx.relabel_nodes(cycle_graph, {i: str(i) for i in range(4)})
        
        path = self.finder.dijkstra_shortest_path(cycle_graph, "0", "2")
        assert path in [["0", "1", "2"], ["0", "3", "2"]]
    
    def test_complete_graph(self):
        """Test path finding on complete graph."""
        complete_graph = nx.complete_graph(4)
        complete_graph = nx.relabel_nodes(complete_graph, {i: str(i) for i in range(4)})
        
        path = self.finder.dijkstra_shortest_path(complete_graph, "0", "3")
        assert path == ["0", "3"]  # Direct edge in complete graph
    
    def test_large_graph_performance(self):
        """Test path finding performance on larger graph."""
        # Create a larger graph for performance testing
        large_graph = nx.erdos_renyi_graph(100, 0.1)
        large_graph = nx.relabel_nodes(large_graph, {i: str(i) for i in range(100)})
        
        # Test that it completes without error
        path = self.finder.dijkstra_shortest_path(large_graph, "0", "99")
        assert isinstance(path, list)
    
    def test_graph_with_loops(self):
        """Test path finding on graph with self-loops."""
        loop_graph = nx.Graph()
        loop_graph.add_edges_from([("A", "B"), ("B", "C")])
        loop_graph.add_edge("A", "A")  # Self-loop
        
        path = self.finder.dijkstra_shortest_path(loop_graph, "A", "C")
        assert path == ["A", "B", "C"]
    
    def test_graph_with_multiple_edges(self):
        """Test path finding on multigraph."""
        multigraph = nx.MultiGraph()
        multigraph.add_edge("A", "B", weight=1)
        multigraph.add_edge("A", "B", weight=2)
        multigraph.add_edge("B", "C", weight=1)
        
        # PathFinder should handle multigraphs (use first edge)
        path = self.finder.dijkstra_shortest_path(multigraph, "A", "C")
        assert path == ["A", "B", "C"]


class TestPathFinderHeuristics:
    """Test heuristic functions for A* search."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.finder = PathFinder()
        self.graph = nx.Graph()
        self.graph.add_edges_from([
            ("A", "B", {"weight": 1}),
            ("B", "C", {"weight": 1}),
            ("C", "D", {"weight": 1}),
            ("A", "D", {"weight": 10})
        ])
    
    def test_zero_heuristic(self):
        """Test A* with zero heuristic (equivalent to Dijkstra)."""
        def zero_heuristic(node1, node2):
            return 0
        
        path = self.finder.a_star_search(self.graph, "A", "D", zero_heuristic)
        assert path == ["A", "B", "C", "D"]  # Should find shortest path
    
    def test_perfect_heuristic(self):
        """Test A* with perfect heuristic (should find optimal path)."""
        def perfect_heuristic(node1, node2):
            # Perfect heuristic: actual shortest distance
            if node1 == "A" and node2 == "D":
                return 3  # A-B-C-D distance
            return 0
        
        path = self.finder.a_star_search(self.graph, "A", "D", perfect_heuristic)
        assert path == ["A", "B", "C", "D"]
    
    def test_overestimating_heuristic(self):
        """Test A* with overestimating heuristic (still finds path but may be suboptimal)."""
        def overestimating_heuristic(node1, node2):
            return 100  # Overestimates all distances
        
        path = self.finder.a_star_search(self.graph, "A", "D", overestimating_heuristic)
        # Should still find a path, but not guaranteed to be optimal
        assert path[0] == "A"
        assert path[-1] == "D"


class TestPathFinderEdgeCases:
    """Edge case tests for PathFinder."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.finder = PathFinder()
    
    def test_empty_graph_all_algorithms(self):
        """Test all path finding algorithms on empty graph."""
        empty_graph = nx.Graph()
        
        # Dijkstra
        with pytest.raises(ValueError, match="Source node A not found"):
            self.finder.dijkstra_shortest_path(empty_graph, "A", "B")
        
        # A*
        def heuristic(node1, node2):
            return 0
        
        with pytest.raises(ValueError, match="Source node A not found"):
            self.finder.a_star_search(empty_graph, "A", "B", heuristic)
        
        # BFS
        with pytest.raises(ValueError, match="Source node A not found"):
            self.finder.bfs_shortest_path(empty_graph, "A", "B")
    
    def test_single_node_graph_all_algorithms(self):
        """Test all path finding algorithms on single node graph."""
        single_node_graph = nx.Graph()
        single_node_graph.add_node("A")
        
        # Same source and target
        dijkstra_path = self.finder.dijkstra_shortest_path(single_node_graph, "A", "A")
        assert dijkstra_path == ["A"]
        
        def heuristic(node1, node2):
            return 0
        
        astar_path = self.finder.a_star_search(single_node_graph, "A", "A", heuristic)
        assert astar_path == ["A"]
        
        bfs_path = self.finder.bfs_shortest_path(single_node_graph, "A", "A")
        assert bfs_path == ["A"]
        
        # Different nodes (target doesn't exist)
        with pytest.raises(ValueError, match="Target node B not found"):
            self.finder.dijkstra_shortest_path(single_node_graph, "A", "B")
    
    def test_disconnected_graph_all_algorithms(self):
        """Test all path finding algorithms on disconnected graph."""
        disconnected_graph = nx.Graph()
        disconnected_graph.add_edges_from([("A", "B"), ("B", "C")])  # Component 1
        disconnected_graph.add_edges_from([("X", "Y"), ("Y", "Z")])  # Component 2
        
        # Path within same component
        path = self.finder.dijkstra_shortest_path(disconnected_graph, "A", "C")
        assert path == ["A", "B", "C"]
        
        # Path between different components
        path = self.finder.dijkstra_shortest_path(disconnected_graph, "A", "X")
        assert path == []  # No path exists
        
        # Test A* with disconnected components
        def heuristic(node1, node2):
            return 0
        
        path = self.finder.a_star_search(disconnected_graph, "A", "X", heuristic)
        assert path == []
        
        # Test BFS with disconnected components
        path = self.finder.bfs_shortest_path(disconnected_graph, "A", "X")
        assert path == []
    
    def test_complete_graph_all_algorithms(self):
        """Test all path finding algorithms on complete graph."""
        complete_graph = nx.complete_graph(4)
        complete_graph = nx.relabel_nodes(complete_graph, {i: str(i) for i in range(4)})
        
        # Should find direct edges for all pairs
        for source in complete_graph.nodes():
            for target in complete_graph.nodes():
                if source != target:
                    dijkstra_path = self.finder.dijkstra_shortest_path(complete_graph, source, target)
                    assert dijkstra_path == [source, target]  # Direct edge
                    
                    def heuristic(node1, node2):
                        return 0
                    
                    astar_path = self.finder.a_star_search(complete_graph, source, target, heuristic)
                    assert astar_path == [source, target]
                    
                    bfs_path = self.finder.bfs_shortest_path(complete_graph, source, target)
                    assert bfs_path == [source, target]
    
    def test_cycle_graph_all_algorithms(self):
        """Test all path finding algorithms on cycle graph."""
        cycle_graph = nx.cycle_graph(6)  # 0-1-2-3-4-5-0
        cycle_graph = nx.relabel_nodes(cycle_graph, {i: str(i) for i in range(6)})
        
        # Test paths at different distances
        # Adjacent nodes
        path = self.finder.dijkstra_shortest_path(cycle_graph, "0", "1")
        assert path in [["0", "1"], ["0", "5", "4", "3", "2", "1"]]
        
        # Opposite nodes
        path = self.finder.dijkstra_shortest_path(cycle_graph, "0", "3")
        assert len(path) == 4  # Should be shortest path
        
        # Test A* with cycle
        def heuristic(node1, node2):
            # Simple heuristic based on node numbers
            return abs(int(node1) - int(node2))
        
        path = self.finder.a_star_search(cycle_graph, "0", "3", heuristic)
        assert len(path) == 4
        
        # Test BFS with cycle
        path = self.finder.bfs_shortest_path(cycle_graph, "0", "3")
        assert len(path) == 4
    
    def test_star_graph_all_algorithms(self):
        """Test all path finding algorithms on star graph."""
        star_graph = nx.star_graph(5)  # Central node 0, leaves 1-5
        star_graph = nx.relabel_nodes(star_graph, {i: str(i) for i in range(6)})
        
        # Path from center to leaf
        path = self.finder.dijkstra_shortest_path(star_graph, "0", "3")
        assert path == ["0", "3"]
        
        # Path between leaves (must go through center)
        path = self.finder.dijkstra_shortest_path(star_graph, "1", "4")
        assert path == ["1", "0", "4"]
        
        # Test A* with star
        def heuristic(node1, node2):
            return 0
        
        path = self.finder.a_star_search(star_graph, "1", "4", heuristic)
        assert path == ["1", "0", "4"]
        
        # Test BFS with star
        path = self.finder.bfs_shortest_path(star_graph, "1", "4")
        assert path == ["1", "0", "4"]
    
    def test_graph_with_self_loops(self):
        """Test path finding with self-loops."""
        loop_graph = nx.Graph()
        loop_graph.add_edges_from([("A", "B"), ("B", "C")])
        loop_graph.add_edge("A", "A")  # Self-loop
        loop_graph.add_edge("B", "B")  # Self-loop
        
        # Should ignore self-loops for path finding
        path = self.finder.dijkstra_shortest_path(loop_graph, "A", "C")
        assert path == ["A", "B", "C"]
        
        def heuristic(node1, node2):
            return 0
        
        path = self.finder.a_star_search(loop_graph, "A", "C", heuristic)
        assert path == ["A", "B", "C"]
        
        path = self.finder.bfs_shortest_path(loop_graph, "A", "C")
        assert path == ["A", "B", "C"]
    
    def test_multigraph_all_algorithms(self):
        """Test path finding on multigraph."""
        multigraph = nx.MultiGraph()
        multigraph.add_edge("A", "B", weight=1)
        multigraph.add_edge("A", "B", weight=2)  # Multiple edges
        multigraph.add_edge("B", "C", weight=1)
        
        # Should handle multigraph (use first edge weight)
        path = self.finder.dijkstra_shortest_path(multigraph, "A", "C")
        assert path == ["A", "B", "C"]
        
        # Test path length with multigraph
        length = self.finder.path_length(multigraph, path)
        assert length == 2.0  # Should use first edge weights (1 + 1)
        
        def heuristic(node1, node2):
            return 0
        
        path = self.finder.a_star_search(multigraph, "A", "C", heuristic)
        assert path == ["A", "B", "C"]
        
        path = self.finder.bfs_shortest_path(multigraph, "A", "C")
        assert path == ["A", "B", "C"]
    
    def test_weighted_graph_edge_cases(self):
        """Test path finding with extreme weights."""
        weighted_graph = nx.Graph()
        
        # Add edges with various weights
        weighted_graph.add_edge("A", "B", weight=0.001)  # Very small weight
        weighted_graph.add_edge("B", "C", weight=1000.0)  # Very large weight
        weighted_graph.add_edge("A", "C", weight=1.0)  # Normal weight
        
        # Should prefer path with smaller total weight
        path = self.finder.dijkstra_shortest_path(weighted_graph, "A", "C")
        assert path == ["A", "C"]  # Direct path weight 1.0 vs A-B-C weight 1000.001
        
        # Test path length calculation
        length = self.finder.path_length(weighted_graph, ["A", "C"])
        assert length == 1.0
        
        length = self.finder.path_length(weighted_graph, ["A", "B", "C"])
        assert length == 1000.001
    
    def test_negative_weights(self):
        """Test path finding with negative weights."""
        negative_graph = nx.Graph()
        negative_graph.add_edge("A", "B", weight=-1.0)
        negative_graph.add_edge("B", "C", weight=2.0)
        negative_graph.add_edge("A", "C", weight=1.0)
        
        # Dijkstra should handle negative weights (though not optimal for negative cycles)
        path = self.finder.dijkstra_shortest_path(negative_graph, "A", "C")
        # Should still find a path, though may not be optimal with negative weights
        assert path in [["A", "C"], ["A", "B", "C"]]
    
    def test_zero_weight_edges(self):
        """Test path finding with zero weight edges."""
        zero_weight_graph = nx.Graph()
        zero_weight_graph.add_edge("A", "B", weight=0.0)
        zero_weight_graph.add_edge("B", "C", weight=1.0)
        zero_weight_graph.add_edge("A", "C", weight=2.0)
        
        # Should prefer zero-weight path
        path = self.finder.dijkstra_shortest_path(zero_weight_graph, "A", "C")
        assert path == ["A", "B", "C"]  # Total weight 0.0 vs direct 2.0
        
        length = self.finder.path_length(zero_weight_graph, ["A", "B", "C"])
        assert length == 1.0  # 0.0 + 1.0
    
    def test_astar_heuristic_edge_cases(self):
        """Test A* with various heuristic edge cases."""
        graph = nx.Graph()
        graph.add_edges_from([("A", "B"), ("B", "C"), ("C", "D")])
        
        # Zero heuristic (equivalent to Dijkstra)
        def zero_heuristic(node1, node2):
            return 0
        
        path = self.finder.a_star_search(graph, "A", "D", zero_heuristic)
        assert path == ["A", "B", "C", "D"]
        
        # Perfect heuristic
        def perfect_heuristic(node1, node2):
            distances = {"A": 0, "B": 1, "C": 2, "D": 3}
            return abs(distances[node1] - distances[node2])
        
        path = self.finder.a_star_search(graph, "A", "D", perfect_heuristic)
        assert path == ["A", "B", "C", "D"]
        
        # Overestimating heuristic
        def overestimating_heuristic(node1, node2):
            return 100  # Always overestimates
        
        path = self.finder.a_star_search(graph, "A", "D", overestimating_heuristic)
        # Should still find a path, though may not be optimal
        assert path[0] == "A" and path[-1] == "D"
        
        # Negative heuristic (should still work)
        def negative_heuristic(node1, node2):
            return -10
        
        path = self.finder.a_star_search(graph, "A", "D", negative_heuristic)
        assert path == ["A", "B", "C", "D"]
    
    def test_very_large_graph_performance(self):
        """Test path finding performance on large graph."""
        # Create a large sparse graph
        large_graph = nx.erdos_renyi_graph(1000, 0.01)  # 1000 nodes, sparse
        large_graph = nx.relabel_nodes(large_graph, {i: str(i) for i in range(1000)})
        
        # Test that algorithms complete without error
        source = "0"
        target = "999"
        
        # Only test if path exists
        if nx.has_path(large_graph, source, target):
            dijkstra_path = self.finder.dijkstra_shortest_path(large_graph, source, target)
            assert isinstance(dijkstra_path, list)
            assert dijkstra_path[0] == source
            if dijkstra_path:  # If path is not empty
                assert dijkstra_path[-1] == target
            
            def heuristic(node1, node2):
                return 0
            
            astar_path = self.finder.a_star_search(large_graph, source, target, heuristic)
            assert isinstance(astar_path, list)
            
            bfs_path = self.finder.bfs_shortest_path(large_graph, source, target)
            assert isinstance(bfs_path, list)
    
    def test_k_shortest_paths_edge_cases(self):
        """Test k-shortest paths with edge cases."""
        # Simple graph with limited paths
        simple_graph = nx.Graph()
        simple_graph.add_edges_from([("A", "B"), ("B", "C")])
        
        # Ask for more paths than exist
        paths = self.finder.find_k_shortest_paths(simple_graph, "A", "C", k=10)
        assert len(paths) <= 1  # Only 1 path exists
        
        # Graph with multiple paths
        multi_path_graph = nx.Graph()
        multi_path_graph.add_edges_from([
            ("A", "B"), ("B", "D"),  # Path 1
            ("A", "C"), ("C", "D"),  # Path 2
            ("A", "D")               # Direct path
        ])
        
        # Find multiple paths
        paths = self.finder.find_k_shortest_paths(multi_path_graph, "A", "D", k=5)
        assert len(paths) >= 2  # Should find at least 2 paths
        assert len(paths) <= 3  # Maximum 3 paths exist
        
        # All paths should be valid
        for path in paths:
            assert path[0] == "A"
            assert path[-1] == "D"
        
        # Should be ordered by length (shortest first)
        if len(paths) > 1:
            lengths = [self.finder.path_length(multi_path_graph, path) for path in paths]
            assert all(lengths[i] <= lengths[i+1] for i in range(len(lengths)-1))
    
    def test_path_length_edge_cases(self):
        """Test path length calculation edge cases."""
        graph = nx.Graph()
        graph.add_edge("A", "B", weight=1.5)
        graph.add_edge("B", "C", weight=2.5)
        
        # Path with non-existent edge
        invalid_path = ["A", "X", "C"]  # X doesn't exist
        with pytest.raises(ValueError, match="No edge found"):
            self.finder.path_length(graph, invalid_path)
        
        # Path with disconnected nodes
        disconnected_path = ["A", "D"]  # D doesn't exist in graph
        with pytest.raises(ValueError, match="No edge found"):
            self.finder.path_length(graph, disconnected_path)
        
        # Empty path
        empty_path = []
        length = self.finder.path_length(graph, empty_path)
        assert length == 0.0
        
        # Path with missing weights
        graph_no_weights = nx.Graph()
        graph_no_weights.add_edge("A", "B")
        graph_no_weights.add_edge("B", "C")
        
        length = self.finder.path_length(graph_no_weights, ["A", "B", "C"])
        assert length == 2.0  # Default weight of 1.0 per edge
    
    def test_all_shortest_paths_edge_cases(self):
        """Test all shortest paths with edge cases."""
        # Graph with multiple shortest paths
        multi_shortest_graph = nx.Graph()
        multi_shortest_graph.add_edges_from([
            ("A", "B"), ("B", "D"),  # Path 1: A-B-D
            ("A", "C"), ("C", "D"),  # Path 2: A-C-D
            ("A", "E"), ("E", "D")   # Path 3: A-E-D
        ])
        
        paths = self.finder.all_shortest_paths(multi_shortest_graph, "A")
        
        # Should find multiple shortest paths to D
        assert "D" in paths
        assert len(paths["D"]) >= 2  # At least 2 shortest paths of length 2
        
        # All paths should be valid
        for target, path_list in paths.items():
            for path in path_list:
                assert path[0] == "A"
                assert path[-1] == target
                assert len(path) >= 1
        
        # Single node graph
        single_node_graph = nx.Graph()
        single_node_graph.add_node("A")
        
        paths = self.finder.all_shortest_paths(single_node_graph, "A")
        assert len(paths) == 0  # No paths to other nodes


class TestBidirectionalPathFinding:
    """Tests for the directed=False undirected-traversal mode (issue #469)."""

    def setup_method(self):
        self.finder = PathFinder()
        # Single directed edge A → B.  Reverse query B → A has no directed path.
        self.digraph = nx.DiGraph()
        self.digraph.add_edge("A", "B")

    # --- directed=True (default) preserves existing behaviour ---

    def test_bfs_directed_true_reverse_returns_empty(self):
        """B→A should find nothing when directed=True (default)."""
        path = self.finder.bfs_shortest_path(self.digraph, "B", "A", directed=True)
        assert path == []

    def test_dijkstra_directed_true_reverse_returns_empty(self):
        """B→A should find nothing when directed=True (default)."""
        path = self.finder.dijkstra_shortest_path(self.digraph, "B", "A", directed=True)
        assert path == []

    def test_bfs_directed_true_default_arg(self):
        """Omitting directed= should behave the same as directed=True."""
        path = self.finder.bfs_shortest_path(self.digraph, "B", "A")
        assert path == []

    def test_dijkstra_directed_true_default_arg(self):
        path = self.finder.dijkstra_shortest_path(self.digraph, "B", "A")
        assert path == []

    # --- directed=False finds path against edge orientation ---

    def test_bfs_directed_false_reverse_single_edge(self):
        """directed=False must find B→A even though only A→B exists."""
        path = self.finder.bfs_shortest_path(self.digraph, "B", "A", directed=False)
        assert path == ["B", "A"]

    def test_dijkstra_directed_false_reverse_single_edge(self):
        path = self.finder.dijkstra_shortest_path(self.digraph, "B", "A", directed=False)
        assert path == ["B", "A"]

    def test_bfs_directed_false_forward_still_works(self):
        """directed=False should not break the forward direction."""
        path = self.finder.bfs_shortest_path(self.digraph, "A", "B", directed=False)
        assert path == ["A", "B"]

    def test_dijkstra_directed_false_forward_still_works(self):
        path = self.finder.dijkstra_shortest_path(self.digraph, "A", "B", directed=False)
        assert path == ["A", "B"]

    # --- multi-hop path where one edge is against the query direction ---

    def test_bfs_directed_false_multihop(self):
        """A→B, C→B graph: directed=False lets us find A→B→C (i.e. A→C via B)."""
        g = nx.DiGraph()
        g.add_edge("A", "B")
        g.add_edge("C", "B")  # oriented towards B, not away from it
        # undirected view: A-B-C, so A→C path exists
        path = self.finder.bfs_shortest_path(g, "A", "C", directed=False)
        assert path[0] == "A" and path[-1] == "C"
        assert "B" in path

    def test_dijkstra_directed_false_multihop(self):
        g = nx.DiGraph()
        g.add_edge("A", "B")
        g.add_edge("C", "B")
        path = self.finder.dijkstra_shortest_path(g, "A", "C", directed=False)
        assert path[0] == "A" and path[-1] == "C"
        assert "B" in path

    # --- PathResponse.directed field ---

    def test_path_response_directed_field_exists(self):
        """PathResponse must carry a directed field."""
        from semantica.explorer.schemas import PathResponse
        r = PathResponse(source="A", target="B", algorithm="bfs", path=["A", "B"], directed=False)
        assert r.directed is False

    def test_path_response_directed_field_defaults_true(self):
        from semantica.explorer.schemas import PathResponse
        r = PathResponse(source="A", target="B", algorithm="bfs", path=["A", "B"])
        assert r.directed is True
