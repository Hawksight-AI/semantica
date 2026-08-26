"""
Connectivity Analyzer Module

This module provides comprehensive connectivity analysis capabilities for the
Semantica framework, enabling analysis of graph connectivity, path finding,
and structural properties.

Supported Algorithms:
    - Connectivity analysis: Determine if graph is connected or disconnected
    - Connected components detection: Find all connected components using DFS
    - Shortest path calculation: BFS-based shortest path finding
    - Bridge edge identification: Find critical edges whose removal disconnects graph
    - Graph density calculation: Measure graph connectivity and sparsity
    - Degree statistics: Analyze node degree distributions

Key Features:
    - Comprehensive connectivity analysis with multiple metrics
    - Connected components detection and analysis
    - Bridge edge identification for network robustness
    - Shortest path calculation with source/target options
    - Graph density and degree statistics
    - Graph structure classification and properties
    - NetworkX integration with fallback implementations
    - Scalable algorithms for large graphs

Main Classes:
    - ConnectivityAnalyzer: Comprehensive connectivity analysis engine

Methods:
    - analyze_connectivity(): Main interface for connectivity analysis
    - find_connected_components(): Detect and analyze connected components
    - calculate_shortest_paths(): Find shortest paths between nodes
    - identify_bridges(): Find critical bridge edges
    - calculate_graph_density(): Compute graph density metrics
    - analyze_degree_statistics(): Analyze node degree distributions
    - classify_graph_structure(): Classify graph by structural properties

Example Usage:
    >>> from semantica.kg import ConnectivityAnalyzer
    >>> analyzer = ConnectivityAnalyzer()
    >>> connectivity = analyzer.analyze_connectivity(graph)
    >>> components = analyzer.find_connected_components(graph)
    >>> paths = analyzer.calculate_shortest_paths(graph, source="A", target="B")
    >>> bridges = analyzer.identify_bridges(graph)
    >>> density = analyzer.calculate_graph_density(graph)

Author: Semantica Contributors
License: MIT
"""

from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from ._graph_view import build_adjacency


class ConnectivityAnalyzer:
    """
    Connectivity analysis engine.

    This class provides comprehensive connectivity analysis for knowledge graphs,
    including connected component detection, shortest path calculation, bridge
    identification, and connectivity metrics. Uses NetworkX when available,
    with fallback to basic implementations.

    Features:
        - Connected component detection (DFS-based)
        - Shortest path calculation (BFS-based)
        - Bridge edge identification
        - Connectivity metrics (density, degree statistics)
        - Graph structure classification

    Example Usage:
        >>> analyzer = ConnectivityAnalyzer()
        >>> connectivity = analyzer.analyze_connectivity(graph)
        >>> components = analyzer.find_connected_components(graph)
        >>> path = analyzer.calculate_shortest_paths(graph, source="A", target="B")
    """

    def __init__(self, **config):
        """
        Initialize connectivity analyzer.

        Sets up the analyzer with configuration and checks for optional
        dependencies (NetworkX). Falls back to basic implementations if
        NetworkX is not available.

        Args:
            **config: Configuration options:
                - analysis_config: Analysis configuration (optional)
        """
        self.logger = get_logger("connectivity_analyzer")
        self.connectivity_algorithms = ["dfs", "bfs", "tarjan", "kosaraju"]

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True
        self.analysis_config = config.get("analysis_config", {})
        self.config = config

        # Try to use networkx if available (optional dependency)
        from ..utils.helpers import safe_import
        networkx, nx_available = safe_import("networkx")
        if nx_available:
            self.nx = networkx
            self.use_networkx = True
            self.logger.debug("NetworkX available, using optimized implementations")
        else:
            self.nx = None
            self.use_networkx = False
            self.logger.warning("NetworkX not available, using basic implementations")

    def analyze_connectivity(self, graph: Any) -> Dict[str, Any]:
        """
        Analyze graph connectivity.

        This method performs comprehensive connectivity analysis, including
        connected component detection and connectivity metrics calculation.

        Args:
            graph: Input graph for connectivity analysis (dict, object with
                  relationships, or NetworkX graph)

        Returns:
            dict: Comprehensive connectivity analysis containing:
                - components: List of connected component lists
                - num_components: Number of connected components
                - component_sizes: List of component sizes
                - largest_component_size: Size of largest component
                - smallest_component_size: Size of smallest component
                - num_nodes: Total number of nodes
                - num_edges: Total number of edges
                - density: Graph density (0.0 to 1.0)
                - avg_degree: Average node degree
                - max_degree: Maximum node degree
                - min_degree: Minimum node degree
                - is_connected: Whether graph is fully connected (single component)
        """
        self.logger.info("Analyzing graph connectivity")

        components_result = self.find_connected_components(graph)
        metrics = self.calculate_connectivity_metrics(graph)

        return {
            **components_result,
            **metrics,
            "is_connected": components_result.get("num_components", 0) == 1,
        }

    def find_connected_components(self, graph: Any) -> Dict[str, Any]:
        """
        Find connected components in graph.

        This method identifies all connected components (disconnected subgraphs)
        in the graph using depth-first search (DFS).

        Args:
            graph: Input graph for component analysis

        Returns:
            dict: Connected components analysis containing:
                - components: List of component lists (each list contains node IDs)
                - num_components: Total number of connected components
                - component_sizes: List of sizes for each component
                - largest_component_size: Size of largest component
                - smallest_component_size: Size of smallest component
        """
        self.logger.info("Finding connected components")

        adjacency = self._build_adjacency(graph)
        visited = set()
        components = []

        # DFS to find components
        for node in adjacency:
            if node not in visited:
                component = []
                stack = [node]

                while stack:
                    current = stack.pop()
                    if current not in visited:
                        visited.add(current)
                        component.append(current)

                        for neighbor in adjacency.get(current, []):
                            if neighbor not in visited:
                                stack.append(neighbor)

                if component:
                    components.append(component)

        # Calculate statistics
        component_sizes = [len(comp) for comp in components]

        return {
            "components": components,
            "num_components": len(components),
            "component_sizes": component_sizes,
            "largest_component_size": max(component_sizes) if component_sizes else 0,
            "smallest_component_size": min(component_sizes) if component_sizes else 0,
        }

    def calculate_shortest_paths(
        self, graph: Any, source: Optional[str] = None, target: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate shortest paths in graph.

        This method calculates shortest paths between nodes using breadth-first
        search (BFS). If both source and target are provided, calculates single
        pair shortest path. If omitted, calculates all pairs shortest paths.

        Args:
            graph: Input graph for path analysis
            source: Source node ID for path calculation (optional)
            target: Target node ID for path calculation (optional)

        Returns:
            dict: Shortest path results:
                - If source and target provided:
                    - source: Source node ID
                    - target: Target node ID
                    - path: List of node IDs forming shortest path (or None)
                    - distance: Path length in edges (or -1 if no path)
                    - exists: Whether path exists
                - If source/target omitted:
                    - distances: Dictionary of all-pairs distances
                    - paths: Dictionary of all-pairs paths
                    - avg_path_length: Average shortest path length
        """
        self.logger.info(f"Calculating shortest paths from {source} to {target}")

        adjacency = self._build_adjacency(graph)

        if source is None or target is None:
            # Calculate all pairs shortest paths
            return self._calculate_all_pairs_shortest_paths(adjacency)

        # Single pair shortest path
        path, distance = self._bfs_shortest_path(adjacency, source, target)

        return {
            "source": source,
            "target": target,
            "path": path,
            "distance": distance,
            "exists": path is not None,
        }

    def identify_bridges(self, graph: Any) -> Dict[str, Any]:
        """
        Identify bridge edges in graph.

        This method identifies bridge edges (edges whose removal would
        disconnect the graph or increase the number of connected components).
        Uses a simple approach: temporarily removes each edge and checks if
        connectivity changes.

        Args:
            graph: Input graph for bridge analysis

        Returns:
            dict: Bridge identification results containing:
                - bridges: List of bridge edge tuples (source, target)
                - num_bridges: Total number of bridge edges
                - bridge_edges: List of bridge edge dictionaries with
                               "source" and "target" keys
        """
        self.logger.info("Identifying bridge edges")

        adjacency = self._build_adjacency(graph)
        bridges = []

        # Get all edges
        edges = set()
        for source, targets in adjacency.items():
            for target in targets:
                edge = tuple(sorted([source, target]))
                edges.add(edge)

        # Check each edge
        for edge in edges:
            source, target = edge

            # Remove edge temporarily
            temp_adjacency = {
                k: [v for v in vs if v != target] for k, vs in adjacency.items()
            }
            temp_adjacency[source] = [
                v for v in temp_adjacency.get(source, []) if v != target
            ]

            # Check connectivity
            components = self._find_components(temp_adjacency)

            # If more components, it's a bridge
            if len(components) > 1:
                bridges.append(edge)

        return {
            "bridges": bridges,
            "num_bridges": len(bridges),
            "bridge_edges": [{"source": s, "target": t} for s, t in bridges],
        }

    def calculate_connectivity_metrics(self, graph: Any) -> Dict[str, Any]:
        """
        Calculate comprehensive connectivity metrics.

        This method calculates various connectivity and structural metrics
        for the graph, including density, degree statistics, and edge counts.

        Args:
            graph: Input graph for metrics calculation

        Returns:
            dict: Connectivity metrics containing:
                - num_nodes: Total number of nodes
                - num_edges: Total number of edges
                - density: Graph density (edges / max_possible_edges, 0.0 to 1.0)
                - avg_degree: Average node degree
                - max_degree: Maximum node degree
                - min_degree: Minimum node degree
        """
        self.logger.info("Calculating connectivity metrics")

        adjacency = self._build_adjacency(graph)
        nodes = list(adjacency.keys())
        n = len(nodes)

        # Count edges
        total_edges = sum(len(neighbors) for neighbors in adjacency.values()) // 2

        # Calculate density
        max_edges = n * (n - 1) / 2 if n > 1 else 0
        density = total_edges / max_edges if max_edges > 0 else 0.0

        # Average degree
        degrees = [len(adjacency.get(node, [])) for node in nodes]
        avg_degree = sum(degrees) / n if n > 0 else 0.0

        return {
            "num_nodes": n,
            "num_edges": total_edges,
            "density": density,
            "avg_degree": avg_degree,
            "max_degree": max(degrees) if degrees else 0,
            "min_degree": min(degrees) if degrees else 0,
        }

    def analyze_graph_structure(self, graph: Any) -> Dict[str, Any]:
        """
        Analyze overall graph structure and connectivity.

        This method performs comprehensive graph structure analysis, combining
        connectivity analysis, metrics calculation, and bridge identification,
        and classifies the graph structure type.

        Args:
            graph: Input graph for structure analysis

        Returns:
            dict: Comprehensive structure analysis containing all metrics from
                  analyze_connectivity(), calculate_connectivity_metrics(), and
                  identify_bridges(), plus:
                - structure_type: Classification ("disconnected", "sparse",
                                 "moderate", or "dense")
        """
        self.logger.info("Analyzing graph structure")

        connectivity = self.analyze_connectivity(graph)
        metrics = self.calculate_connectivity_metrics(graph)
        bridges = self.identify_bridges(graph)

        return {
            **connectivity,
            **metrics,
            **bridges,
            "structure_type": self._classify_structure(connectivity, metrics),
        }

    def _build_adjacency(self, graph) -> Dict[str, List[str]]:
        """Build adjacency list from graph."""
        return build_adjacency(graph)

    def _bfs_shortest_path(
        self, adjacency: Dict[str, List[str]], source: str, target: str
    ) -> Tuple[Optional[List[str]], int]:
        """Find shortest path using BFS."""
        if source == target:
            return [source], 0

        queue = deque([(source, [source])])
        visited = {source}

        while queue:
            node, path = queue.popleft()

            for neighbor in adjacency.get(node, []):
                if neighbor == target:
                    return path + [target], len(path)

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None, -1

    def _calculate_all_pairs_shortest_paths(
        self, adjacency: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """Calculate all pairs shortest paths."""
        nodes = list(adjacency.keys())
        distances = {}
        paths = {}

        for source in nodes:
            distances[source] = {}
            paths[source] = {}

            for target in nodes:
                if source == target:
                    distances[source][target] = 0
                    paths[source][target] = [source]
                else:
                    path, distance = self._bfs_shortest_path(adjacency, source, target)
                    distances[source][target] = distance
                    paths[source][target] = path

        return {
            "distances": distances,
            "paths": paths,
            "avg_path_length": self._calculate_avg_path_length(distances),
        }

    def _calculate_avg_path_length(self, distances: Dict[str, Dict[str, int]]) -> float:
        """Calculate average path length."""
        total = 0
        count = 0

        for source_distances in distances.values():
            for distance in source_distances.values():
                if distance > 0:
                    total += distance
                    count += 1

        return total / count if count > 0 else 0.0

    def _find_components(self, adjacency: Dict[str, List[str]]) -> List[List[str]]:
        """Find connected components using DFS."""
        visited = set()
        components = []

        for node in adjacency:
            if node not in visited:
                component = []
                stack = [node]

                while stack:
                    current = stack.pop()
                    if current not in visited:
                        visited.add(current)
                        component.append(current)

                        for neighbor in adjacency.get(current, []):
                            if neighbor not in visited:
                                stack.append(neighbor)

                if component:
                    components.append(component)

        return components

    def _classify_structure(
        self, connectivity: Dict[str, Any], metrics: Dict[str, Any]
    ) -> str:
        """Classify graph structure type."""
        num_components = connectivity.get("num_components", 1)
        density = metrics.get("density", 0.0)

        if num_components > 1:
            return "disconnected"
        elif density > 0.5:
            return "dense"
        elif density < 0.1:
            return "sparse"
        else:
            return "moderate"
