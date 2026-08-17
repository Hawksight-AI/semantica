"""
Graph Analytics Module

This module provides comprehensive graph analytics capabilities for knowledge graphs,
including centrality measures, community detection, connectivity analysis, and
graph metrics calculation.

Key Features:
    - Multiple centrality measures (degree, betweenness, closeness, eigenvector)
    - Community detection algorithms (Louvain, Leiden, etc.)
    - Connectivity analysis and path finding
    - Graph metrics and statistics
    - Temporal graph analysis (optional)

Example Usage:
    >>> from semantica.kg import GraphAnalyzer
    >>> analyzer = GraphAnalyzer()
    >>> analysis = analyzer.analyze_graph(graph)
    >>> centrality = analyzer.calculate_centrality(graph, centrality_type="degree")

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, Optional

from ..utils.progress_tracker import get_progress_tracker
from .centrality_calculator import CentralityCalculator
from .community_detector import CommunityDetector
from .connectivity_analyzer import ConnectivityAnalyzer


class GraphAnalyzer:
    """
    Comprehensive graph analytics handler.

    This class provides a unified interface for performing various graph analytics
    including centrality calculations, community detection, connectivity analysis,
    and graph metrics computation. It coordinates multiple specialized analyzers.

    Features:
        - Centrality measures (degree, betweenness, closeness, eigenvector)
        - Community detection (Louvain, Leiden, etc.)
        - Connectivity analysis and path finding
        - Graph metrics and statistics
        - Temporal graph analysis (optional)

    Example Usage:
        >>> analyzer = GraphAnalyzer()
        >>> # Comprehensive analysis
        >>> results = analyzer.analyze_graph(graph)
        >>> # Specific analysis
        >>> centrality = analyzer.calculate_centrality(graph, "betweenness")
        >>> communities = analyzer.detect_communities(graph, algorithm="louvain")
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        enable_temporal: bool = False,
        temporal_granularity: str = "day",
        **kwargs,
    ):
        """
        Initialize graph analyzer.

        Sets up all analysis components including centrality calculator,
        community detector, and connectivity analyzer.

        Args:
            config: Configuration dictionary for analyzers
            enable_temporal: Enable temporal graph analysis features (default: False)
            temporal_granularity: Time granularity for temporal analysis
                                 ("second", "minute", "hour", "day", etc., default: "day")
            **kwargs: Additional configuration options merged into config
        """
        from ..utils.logging import get_logger

        self.logger = get_logger("graph_analyzer")

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Merge configuration
        self.config = config or {}
        self.config.update(kwargs)

        # Temporal analysis settings
        self.enable_temporal = enable_temporal
        self.temporal_granularity = temporal_granularity

        # Initialize specialized analyzers
        self.centrality_calculator = CentralityCalculator(**self.config)
        self.community_detector = CommunityDetector(**self.config)
        self.connectivity_analyzer = ConnectivityAnalyzer(**self.config)

        self.logger.info(f"Graph analyzer initialized (temporal: {enable_temporal})")

    def analyze(self, graph: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Alias for analyze_graph.
        
        Args:
            graph: Knowledge graph dictionary
            **options: Analysis options
            
        Returns:
            Dict[str, Any]: Analysis results
        """
        return self.analyze_graph(graph, **options)

    def analyze_graph(self, graph: Dict[str, Any], **options) -> Dict[str, Any]:
        """
        Perform comprehensive graph analysis.

        This method runs all available graph analytics including centrality
        measures, community detection, connectivity analysis, and metrics
        computation. Returns a comprehensive analysis report.

        Args:
            graph: Knowledge graph to analyze (dict with "entities" and "relationships")
            **options: Analysis options passed to individual analyzers

        Returns:
            Dictionary containing:
                - centrality: Centrality measures for all nodes
                - communities: Detected community structures
                - connectivity: Connectivity analysis results
                - metrics: Graph metrics and statistics

        Example:
            >>> analysis = analyzer.analyze_graph(graph)
            >>> top_nodes = analysis["centrality"]["rankings"][:10]
            >>> num_communities = len(analysis["communities"])
        """
        self.logger.info("Performing comprehensive graph analysis")

        # Calculate centrality measures for all nodes
        self.logger.debug("Calculating centrality measures")
        centrality = self.calculate_centrality(graph, **options)

        # Detect community structures
        self.logger.debug("Detecting communities")
        communities = self.detect_communities(graph, **options)

        # Analyze graph connectivity
        self.logger.debug("Analyzing connectivity")
        connectivity = self.analyze_connectivity(graph, **options)

        # Compute overall graph metrics
        self.logger.debug("Computing graph metrics")
        metrics = self.compute_metrics(graph=graph, **options)

        # Compile comprehensive results
        results = {
            "centrality": centrality,
            "communities": communities,
            "connectivity": connectivity,
            "metrics": metrics,
        }

        self.logger.info("Graph analysis completed successfully")
        return results

    def calculate_centrality(self, graph, centrality_type="degree", **options):
        """
        Calculate centrality measures for graph nodes.

        • Apply centrality algorithms
        • Calculate centrality scores
        • Rank nodes by centrality
        • Handle different centrality types
        • Return centrality results
        """
        return self.centrality_calculator.calculate_all_centrality(
            graph, centrality_types=[centrality_type]
        )

    def detect_communities(self, graph, algorithm="louvain", **options):
        """
        Detect communities in graph.

        • Apply community detection algorithms
        • Identify community structures
        • Calculate community metrics
        • Handle overlapping communities
        • Return community detection results
        """
        return self.community_detector.detect_communities(
            graph, algorithm=algorithm, **options
        )

    def analyze_connectivity(self, graph, **options):
        """
        Analyze graph connectivity and structure.

        • Calculate connectivity metrics
        • Identify connected components
        • Analyze path lengths and distances
        • Detect bottlenecks and bridges
        • Return connectivity analysis
        """
        return self.connectivity_analyzer.analyze_connectivity(graph, **options)

    def compute_metrics(self, graph=None, at_time=None, time_range=None, **options):
        """
        Compute comprehensive graph metrics.

        • Calculate graph statistics
        • Compute structural metrics
        • Analyze graph properties
        • Support temporal metrics if temporal enabled
        • Return metrics dictionary

        Args:
            graph: Graph to analyze (if not provided, uses stored graph)
            at_time: Calculate metrics at specific time point (temporal graphs)
            time_range: Calculate metrics for time range (temporal graphs)
            **options: Additional metric calculation options

        Returns:
            Dictionary of graph metrics
        """
        if graph is None:
            return {}

        # Get connectivity metrics
        connectivity_metrics = (
            self.connectivity_analyzer.calculate_connectivity_metrics(graph)
        )

        # Get entities and relationships
        entities = graph.get("entities", []) if isinstance(graph, dict) else []
        relationships = (
            graph.get("relationships", []) if isinstance(graph, dict) else []
        )

        metrics = {
            "num_nodes": len(entities),
            "num_edges": len(relationships),
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            **connectivity_metrics,
        }

        return metrics

    def analyze_temporal_evolution(
        self,
        graph,
        start_time=None,
        end_time=None,
        metrics=None,
        interval=None,
        **options,
    ):
        """
        if metrics is None:
            metrics = ["node_count", "edge_count", "density", "communities"]
        Analyze temporal evolution of graph.

        Args:
            graph: Temporal knowledge graph
            start_time: Start of analysis period
            end_time: End of analysis period
            metrics: Metrics to track over time
            interval: Time interval for analysis snapshots
            **options: Additional analysis options

        Returns:
            Evolution analysis results with time series data
        """
        self.logger.info("Analyzing temporal evolution")

        from .temporal_query import TemporalGraphQuery

        temporal_query = TemporalGraphQuery(**self.config)

        # Analyze evolution
        evolution = temporal_query.analyze_evolution(
            graph, start_time=start_time, end_time=end_time, metrics=metrics, **options
        )

        return {
            "evolution": evolution,
            "time_range": {"start": start_time, "end": end_time},
            "metrics_tracked": metrics,
        }
