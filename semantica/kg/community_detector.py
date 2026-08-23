"""
Community Detection Module

This module provides comprehensive community detection capabilities for the
Semantica framework, enabling identification of communities (clusters) in
knowledge graphs using various algorithms.

Supported Algorithms:
    - Louvain community detection: Modularity optimization with hierarchical clustering
    - Leiden community detection: Improved version of Louvain with guaranteed connectivity
    - Label propagation: Fast, semi-supervised community detection
    - K-clique communities: Overlapping community detection based on clique percolation

Key Features:
    - Multiple community detection algorithms with different theoretical foundations
    - Community quality metrics (modularity, size distribution, coverage)
    - Community structure analysis and visualization support
    - Overlapping and non-overlapping community detection
    - Scalable implementations for large graphs
    - NetworkX integration with fallback implementations
    - Configurable parameters and resolution settings

Main Classes:
    - CommunityDetector: Comprehensive community detection engine

Methods:
    - detect_communities(): Main interface for community detection
    - detect_communities_louvain(): Louvain modularity optimization
    - detect_communities_leiden(): Leiden algorithm with refinement
    - detect_communities_label_propagation(): Fast label propagation method
    - calculate_community_metrics(): Community quality assessment
    - analyze_community_structure(): Detailed community analysis
    - get_community_statistics(): Statistical summary of communities

Example Usage:
    >>> from semantica.kg import CommunityDetector
    >>> detector = CommunityDetector()
    >>> communities = detector.detect_communities(graph, algorithm="louvain")
    >>> metrics = detector.calculate_community_metrics(graph, communities)
    >>> leiden_communities = detector.detect_communities_leiden(graph, resolution=1.2)
    >>> label_communities = detector.detect_communities_label_propagation(graph)

Author: Semantica Contributors
License: MIT
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from ._graph_view import build_adjacency, build_graph_view


def _is_hashable(value: Any) -> bool:
    """Return whether a community identifier can be used in a set."""
    try:
        hash(value)
    except TypeError:
        return False
    return True


class CommunityDetector:
    """
    Community detection engine.

    This class provides community detection capabilities for knowledge graphs,
    supporting multiple algorithms including Louvain, Leiden, and overlapping
    community detection. Uses NetworkX when available, with fallback to basic
    implementations.

    Features:
        - Louvain algorithm for modularity optimization
        - Leiden algorithm with refinement step
        - Overlapping community detection (k-clique)
        - Community quality metrics calculation
        - Community structure analysis

    Example Usage:
        >>> detector = CommunityDetector()
        >>> communities = detector.detect_communities(graph, algorithm="louvain")
        >>> metrics = detector.calculate_community_metrics(graph, communities)
        >>> structure = detector.analyze_community_structure(graph, communities)
    """

    def __init__(self, **config):
        """
        Initialize community detector.

        Sets up the detector with configuration and checks for optional
        dependencies (NetworkX). Falls back to basic implementations if
        NetworkX is not available.

        Args:
            **config: Configuration options:
                - detection_config: Detection algorithm configuration (optional)
        """
        self.logger = get_logger("community_detector")
        self.supported_algorithms = [
            "louvain",
            "leiden",
            "overlapping",
            "label_propagation",
        ]
        self.detection_config = config.get("detection_config", {})
        self.config = config

        # Try to use networkx if available (optional dependency)
        try:
            import networkx as nx

            self.nx = nx
            self.use_networkx = True
            self.logger.debug("NetworkX available, using optimized implementations")
        except (ImportError, OSError):
            self.nx = None
            self.use_networkx = False
            self.logger.warning("NetworkX not available, using basic implementations")

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def detect_communities_louvain(
        self, graph: Any, resolution: float = 1.0, max_iter: int = 10, **options
    ) -> Dict[str, Any]:
        """
        Detect communities using Louvain algorithm.

        This method applies the Louvain algorithm for community detection,
        which optimizes modularity through iterative greedy optimization.
        Uses NetworkX implementation when available, with fallback to basic
        greedy modularity approach.

        Args:
            graph: Input graph for community detection (dict, object with
                  relationships, or NetworkX graph)
            resolution: Resolution parameter for modularity optimization
                       (default: 1.0, higher values favor smaller communities)
            max_iter: Maximum iterations for basic implementation (default: 10)
            **options: Additional detection options (unused)

        Returns:
            dict: Community detection results containing:
                - communities: List of community lists (each list contains node IDs)
                - node_assignments: Dictionary mapping node IDs to community IDs
                - modularity: Calculated modularity score
                - algorithm: Algorithm name ("louvain")
        """
        # Track community detection
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="kg",
            submodule="CommunityDetector",
            message="Detecting communities using Louvain algorithm",
        )

        try:
            self.logger.info("Detecting communities using Louvain algorithm")

            if self.use_networkx:
                try:
                    import networkx.algorithms.community as nx_comm

                    nx_graph = self._to_networkx(graph)
                    
                    # An empty graph has no communities. A graph with nodes but
                    # no edges still has singleton communities.
                    num_nodes = nx_graph.number_of_nodes()
                    num_edges = nx_graph.number_of_edges()
                    self.logger.debug(f"Graph stats: nodes={num_nodes}, edges={num_edges}")

                    if num_nodes == 0:
                        self.logger.warning("Graph is empty, returning 0 communities")
                        self.progress_tracker.stop_tracking(
                            tracking_id,
                            status="completed",
                            message="Detected 0 communities (empty graph)",
                        )
                        return {
                            "communities": [],
                            "node_assignments": {},
                            "modularity": 0.0,
                            "algorithm": "louvain",
                        }

                    resolution = options.get("resolution", 1.0)

                    self.progress_tracker.update_tracking(
                        tracking_id, message="Detecting communities with NetworkX..."
                    )
                    # Use greedy modularity communities (Louvain-like)
                    communities = nx_comm.greedy_modularity_communities(
                        nx_graph, resolution=resolution
                    )

                    # Convert to node assignments
                    node_communities = {}
                    for i, community in enumerate(communities):
                        for node in community:
                            node_communities[node] = i

                    modularity = nx_comm.modularity(nx_graph, communities)

                    result = {
                        "communities": list(communities),
                        "node_assignments": node_communities,
                        "modularity": modularity,
                        "algorithm": "louvain",
                    }
                    self.progress_tracker.stop_tracking(
                        tracking_id,
                        status="completed",
                        message=f"Detected {len(communities)} communities",
                    )
                    return result
                except Exception as e:
                    import traceback
                    self.logger.warning(
                        f"NetworkX Louvain failed: {e}, using basic implementation. Traceback: {traceback.format_exc()}"
                    )

            self.progress_tracker.update_tracking(
                tracking_id, message="Using basic community detection..."
            )
            # Basic greedy modularity implementation
            adjacency = self._build_adjacency(graph)
            result = self._basic_community_detection(
                adjacency, algorithm="louvain", **options
            )
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Detected {len(result.get('communities', []))} communities",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def detect_communities_leiden(
        self, graph: Any, resolution: float = 1.0, max_iter: int = 10, **options
    ) -> Dict[str, Any]:
        """
        Detect communities using Leiden algorithm.

        This method applies the Leiden algorithm for community detection,
        which is similar to Louvain but includes a refinement step for better
        quality. Currently uses Louvain implementation as Leiden refinement
        requires additional libraries.

        Args:
            graph: Input graph for community detection
            resolution: Resolution parameter for modularity optimization
                       (default: 1.0)
            max_iter: Maximum iterations (default: 10)
            **options: Additional detection options

        Returns:
            dict: Community detection results (same format as Louvain)
        """
        self.logger.info("Detecting communities using Leiden algorithm")

        # Leiden is similar to Louvain but with refinement
        # For now, use Louvain-like approach (full Leiden requires igraph)
        result = self.detect_communities_louvain(
            graph, resolution=resolution, max_iter=max_iter, **options
        )
        result["algorithm"] = "leiden"
        return result

    def detect_overlapping_communities(
        self, graph: Any, k: int = 3, min_size: int = 3, **options
    ) -> Dict[str, Any]:
        """
        Detect overlapping communities.

        This method detects communities where nodes can belong to multiple
        communities simultaneously. Uses k-clique communities when NetworkX
        is available, with fallback to basic dense subgraph detection.

        Args:
            graph: Input graph for community detection
            k: Minimum clique size for k-clique communities (default: 3)
            min_size: Minimum community size for basic detection (default: 3)
            **options: Additional detection options

        Returns:
            dict: Overlapping community detection results containing:
                - communities: List of community lists
                - node_assignments: Dictionary mapping node IDs to list of
                                  community IDs (nodes can belong to multiple)
                - algorithm: Algorithm name ("overlapping")
                - overlap_count: Number of nodes belonging to multiple communities
        """
        self.logger.info("Detecting overlapping communities")

        if self.use_networkx:
            try:
                import networkx.algorithms.community as nx_comm

                nx_graph = self._to_networkx(graph)

                # Use k-clique communities for overlapping detection
                k = options.get("k", 3)
                communities = list(nx_comm.k_clique_communities(nx_graph, k))

                # Build node to communities mapping
                node_communities = defaultdict(list)
                for i, community in enumerate(communities):
                    for node in community:
                        node_communities[node].append(i)

                return {
                    "communities": [list(c) for c in communities],
                    "node_assignments": dict(node_communities),
                    "algorithm": "overlapping",
                    "overlap_count": len(
                        [n for n, comms in node_communities.items() if len(comms) > 1]
                    ),
                }
            except Exception as e:
                self.logger.warning(
                    f"NetworkX overlapping detection failed: {e}, using basic implementation"
                )

        # Basic overlapping detection
        adjacency = self._build_adjacency(graph)
        return self._basic_overlapping_detection(adjacency, **options)

    def calculate_community_metrics(
        self, graph: Any, communities: Any
    ) -> Dict[str, Any]:
        """
        Calculate community quality metrics.

        This method calculates various quality metrics for detected communities,
        including modularity, community size distribution, and basic statistics.

        Args:
            graph: Input graph for community analysis
            communities: Community assignments (can be dict with "node_assignments",
                        dict mapping nodes to community IDs, or list of community lists)

        Returns:
            dict: Community quality metrics containing:
                - num_communities: Total number of communities
                - community_sizes: Dictionary mapping community ID to size
                - avg_community_size: Average community size
                - max_community_size: Largest community size
                - min_community_size: Smallest community size
                - modularity: Calculated modularity score
        """
        self.logger.info("Calculating community quality metrics")

        adjacency = self._build_adjacency(graph)

        node_communities = self._to_node_assignments(communities)

        # Calculate metrics
        num_communities = len(set(node_communities.values()))
        community_sizes = defaultdict(int)
        for comm_id in node_communities.values():
            community_sizes[comm_id] += 1

        # Calculate modularity (simplified)
        modularity = self._calculate_modularity(adjacency, node_communities)

        # Calculate statistics
        sizes = list(community_sizes.values())

        return {
            "num_communities": num_communities,
            "community_sizes": dict(community_sizes),
            "avg_community_size": sum(sizes) / len(sizes) if sizes else 0,
            "max_community_size": max(sizes) if sizes else 0,
            "min_community_size": min(sizes) if sizes else 0,
            "modularity": modularity,
        }

    def analyze_community_structure(
        self, graph: Any, communities: Any
    ) -> Dict[str, Any]:
        """
        Analyze community structure and properties.

        This method performs comprehensive analysis of community structure,
        including connectivity metrics (intra-community vs inter-community edges)
        and community quality metrics.

        Args:
            graph: Input graph for community analysis
            communities: Community assignments to analyze

        Returns:
            dict: Community structure analysis containing all metrics from
                  calculate_community_metrics plus:
                - intra_community_edges: Number of edges within communities
                - inter_community_edges: Number of edges between communities
                - edge_ratio: Ratio of intra- to inter-community edges
        """
        self.logger.info("Analyzing community structure")

        metrics = self.calculate_community_metrics(graph, communities)

        node_communities = self._to_node_assignments(communities)

        # Analyze connectivity between communities
        adjacency = self._build_adjacency(graph)
        inter_community_edges = 0
        intra_community_edges = 0

        for source, targets in adjacency.items():
            source_comm = node_communities.get(source)
            for target in targets:
                target_comm = node_communities.get(target)
                if source_comm == target_comm:
                    intra_community_edges += 1
                else:
                    inter_community_edges += 1

        return {
            **metrics,
            "intra_community_edges": intra_community_edges,
            "inter_community_edges": inter_community_edges,
            "edge_ratio": intra_community_edges / (inter_community_edges + 1),
        }

    @staticmethod
    def _to_node_assignments(communities: Any) -> Dict[Any, Any]:
        """Normalize community results to a node-to-community mapping."""
        if isinstance(communities, dict):
            assignments = communities.get("node_assignments")
            if isinstance(assignments, dict):
                return assignments

            detected_communities = communities.get("communities")
            if isinstance(detected_communities, (list, tuple)):
                communities = detected_communities
            elif "communities" in communities:
                raise ValueError("Community results must contain a list of communities")
            elif not all(_is_hashable(value) for value in communities.values()):
                raise ValueError(
                    "Community assignments must map nodes to hashable community IDs"
                )
            else:
                return communities

        node_assignments: Dict[Any, Any] = {}
        for community_id, community in enumerate(communities or []):
            for node in community:
                node_assignments[node] = community_id
        return node_assignments

    def detect_communities(
        self, graph: Any, algorithm: str = "louvain", method: str = None, **options
    ) -> Dict[str, Any]:
        """
        Detect communities using specified algorithm.

        This is a convenience method that routes to the appropriate algorithm
        based on the specified algorithm name.

        Args:
            graph: Input graph for community detection
            algorithm: Community detection algorithm to use
                      (supported: "louvain", "leiden", "overlapping")
            **options: Additional detection options (passed to algorithm-specific method)

        Returns:
            dict: Community detection results and analysis

        Raises:
            ValueError: If algorithm is not supported
        """
        # 'method' is an alias for 'algorithm'
        if method is not None:
            algorithm = method if method in ("louvain", "leiden", "overlapping") else "louvain"

        self.logger.info(f"Detecting communities using {algorithm} algorithm")

        if algorithm == "louvain":
            return self.detect_communities_louvain(graph, **options)
        elif algorithm == "leiden":
            return self.detect_communities_leiden(graph, **options)
        elif algorithm == "overlapping":
            return self.detect_overlapping_communities(graph, **options)
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

    def _build_adjacency(self, graph) -> Dict[str, List[str]]:
        """Build adjacency list from graph."""
        return build_adjacency(graph)

    def _to_networkx(self, graph):
        """Convert graph to NetworkX format."""
        # If already a NetworkX graph, return directly
        if hasattr(graph, 'nodes') and hasattr(graph, 'edges') and hasattr(graph, 'number_of_nodes'):
            return graph

        view = build_graph_view(graph)
        nx_graph = self.nx.Graph()

        nx_graph.add_nodes_from(view.nodes)
        nx_graph.add_edges_from(view.edges)

        return nx_graph

    def _basic_community_detection(
        self, adjacency: Dict[str, List[str]], algorithm="louvain", **options
    ):
        """Basic community detection implementation."""
        # Simple greedy approach
        nodes = list(adjacency.keys())
        node_communities = {node: i for i, node in enumerate(nodes)}

        # Simple merge step
        changed = True
        iterations = 0
        max_iter = options.get("max_iter", 10)
        best_modularity = 0.0

        while changed and iterations < max_iter:
            changed = False
            iterations += 1

            for node in nodes:
                # Find best community for this node
                best_community = node_communities[node]
                best_modularity = self._calculate_modularity(
                    adjacency, node_communities
                )

                # Try moving to neighbor communities
                for neighbor in adjacency.get(node, []):
                    neighbor_comm = node_communities.get(neighbor)
                    if neighbor_comm != node_communities[node]:
                        # Try moving
                        old_comm = node_communities[node]
                        node_communities[node] = neighbor_comm
                        new_modularity = self._calculate_modularity(
                            adjacency, node_communities
                        )

                        if new_modularity > best_modularity:
                            best_modularity = new_modularity
                            best_community = neighbor_comm
                            changed = True
                        else:
                            node_communities[node] = old_comm

        # Build communities
        communities = defaultdict(list)
        for node, comm_id in node_communities.items():
            communities[comm_id].append(node)

        return {
            "communities": list(communities.values()),
            "node_assignments": node_communities,
            "modularity": best_modularity,
            "algorithm": algorithm,
        }

    def _basic_overlapping_detection(self, adjacency: Dict[str, List[str]], **options):
        """Basic overlapping community detection."""
        # Simple approach: find dense subgraphs
        communities = []
        nodes = list(adjacency.keys())
        visited = set()

        for node in nodes:
            if node in visited:
                continue

            # Find neighbors
            neighbors = set(adjacency.get(node, []))
            neighbors.add(node)

            # Check if this forms a community (min size)
            min_size = options.get("min_size", 3)
            if len(neighbors) >= min_size:
                communities.append(list(neighbors))
                visited.update(neighbors)

        # Build node to communities mapping
        node_communities = defaultdict(list)
        for i, community in enumerate(communities):
            for node in community:
                node_communities[node].append(i)

        return {
            "communities": communities,
            "node_assignments": dict(node_communities),
            "algorithm": "overlapping",
        }

    def _calculate_modularity(
        self, adjacency: Dict[str, List[str]], node_communities: Dict[str, int]
    ) -> float:
        """Calculate modularity."""
        # Simplified modularity calculation
        total_edges = sum(len(neighbors) for neighbors in adjacency.values()) // 2

        if total_edges == 0:
            return 0.0

        modularity = 0.0
        nodes = list(adjacency.keys())

        for node in nodes:
            node_comm = node_communities.get(node)
            degree = len(adjacency.get(node, []))

            for neighbor in adjacency.get(node, []):
                neighbor_comm = node_communities.get(neighbor)

                if node_comm == neighbor_comm:
                    # Same community
                    modularity += 1.0 - (degree * len(adjacency.get(neighbor, []))) / (
                        2 * total_edges
                    )

        return modularity / (2 * total_edges) if total_edges > 0 else 0.0

    def detect_communities_label_propagation(
        self,
        graph: Any,
        node_labels: Optional[List[str]] = None,
        relationship_types: Optional[List[str]] = None,
        max_iterations: int = 100,
        random_seed: Optional[int] = None,
        chunk_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Detect communities using Label Propagation algorithm.
        
        Label Propagation is a fast and simple community detection algorithm
        where nodes adopt labels from their neighbors iteratively. It's particularly
        effective for large graphs and provides good quality results.
        
        Args:
            graph: Graph object (NetworkX or similar)
            node_labels: List of node labels to include (None for all)
            relationship_types: List of relationship types to consider (None for all)
            max_iterations: Maximum number of iterations for convergence
            random_seed: Random seed for reproducible results
            chunk_size: Process nodes in chunks for memory efficiency
            
        Returns:
            Dictionary containing:
            - communities: List of communities (each as list of node IDs)
            - node_assignments: Dictionary mapping node IDs to community IDs
            - algorithm: Algorithm name used
            - iterations: Number of iterations until convergence
            
        Raises:
            ValueError: If graph is empty or parameters are invalid
            RuntimeError: If community detection fails
        """
        try:
            self.logger.info("Detecting communities using Label Propagation algorithm")
            
            # Set random seed if provided
            if random_seed is not None:
                import random
                random.seed(random_seed)
            
            # Filter nodes by labels if specified
            nodes = self._filter_nodes_by_labels(graph, node_labels)
            if not nodes:
                raise ValueError("No nodes found matching the specified criteria")
            
            # For very large graphs, use chunked processing
            if len(nodes) > chunk_size:
                return self._detect_communities_label_propagation_chunked(
                    graph, nodes, relationship_types, max_iterations, random_seed, chunk_size
                )
            
            # Build adjacency list for filtered nodes
            adjacency = self._build_filtered_adjacency(graph, nodes, relationship_types)
            
            # Initialize labels - each node starts with its own unique label
            labels = {node: i for i, node in enumerate(nodes)}
            
            # Label propagation iterations
            for iteration in range(max_iterations):
                labels_changed = False
                nodes_copy = nodes.copy()
                
                # Random order for asynchronous updates
                import random
                random.shuffle(nodes_copy)
                
                for node in nodes_copy:
                    # Get neighbor labels
                    neighbor_labels = []
                    neighbors = adjacency.get(node, [])
                    
                    for neighbor in neighbors:
                        if neighbor in labels:
                            neighbor_labels.append(labels[neighbor])
                    
                    if neighbor_labels:
                        # Find most frequent label
                        label_counts = defaultdict(int)
                        for label in neighbor_labels:
                            label_counts[label] += 1
                        
                        # Get label with highest count (break ties randomly)
                        max_count = max(label_counts.values())
                        best_labels = [label for label, count in label_counts.items() if count == max_count]
                        new_label = random.choice(best_labels)
                        
                        if labels[node] != new_label:
                            labels[node] = new_label
                            labels_changed = True
                
                # Check for convergence
                if not labels_changed:
                    self.logger.info(f"Label Propagation converged after {iteration + 1} iterations")
                    break
            else:
                self.logger.warning(f"Label Propagation did not converge after {max_iterations} iterations")
            
            # Group nodes by their final labels
            label_to_nodes = defaultdict(list)
            for node, label in labels.items():
                label_to_nodes[label].append(node)
            
            # Convert to communities list
            communities = list(label_to_nodes.values())
            
            # Create node assignments mapping
            node_assignments = {node: i for i, community in enumerate(communities) for node in community}
            
            result = {
                "communities": communities,
                "node_assignments": node_assignments,
                "algorithm": "label_propagation",
                "iterations": iteration + 1 if 'iteration' in locals() else max_iterations
            }
            
            self.logger.info(f"Detected {len(communities)} communities using Label Propagation")
            return result
            
        except Exception as e:
            self.logger.error(f"Label Propagation community detection failed: {str(e)}")
            raise RuntimeError(f"Community detection failed: {str(e)}")
    
    def _detect_communities_label_propagation_chunked(
        self,
        graph: Any,
        nodes: List[str],
        relationship_types: Optional[List[str]],
        max_iterations: int,
        random_seed: Optional[int],
        chunk_size: int
    ) -> Dict[str, Any]:
        """
        Chunked Label Propagation for very large graphs.
        
        Processes the graph in chunks to manage memory usage while maintaining
        algorithm effectiveness through iterative refinement.
        """
        self.logger.info(f"Using chunked Label Propagation for {len(nodes)} nodes")
        
        # Initialize labels for all nodes
        labels = {node: i for i, node in enumerate(nodes)}
        
        # Build adjacency in chunks
        adjacency = {}
        for i in range(0, len(nodes), chunk_size):
            chunk_nodes = nodes[i:i + chunk_size]
            chunk_adjacency = self._build_filtered_adjacency(graph, chunk_nodes, relationship_types)
            adjacency.update(chunk_adjacency)
        
        # Run label propagation with memory-efficient updates
        for iteration in range(max_iterations):
            labels_changed = False
            
            # Process nodes in chunks
            for i in range(0, len(nodes), chunk_size):
                chunk_nodes = nodes[i:i + chunk_size]
                
                # Random order within chunk
                import random
                random.shuffle(chunk_nodes)
                
                for node in chunk_nodes:
                    # Get neighbor labels
                    neighbor_labels = []
                    neighbors = adjacency.get(node, [])
                    
                    for neighbor in neighbors:
                        if neighbor in labels:
                            neighbor_labels.append(labels[neighbor])
                    
                    if neighbor_labels:
                        # Find most frequent label
                        label_counts = defaultdict(int)
                        for label in neighbor_labels:
                            label_counts[label] += 1
                        
                        # Get label with highest count (break ties randomly)
                        max_count = max(label_counts.values())
                        best_labels = [label for label, count in label_counts.items() if count == max_count]
                        new_label = random.choice(best_labels)
                        
                        if labels[node] != new_label:
                            labels[node] = new_label
                            labels_changed = True
            
            # Check for convergence
            if not labels_changed:
                self.logger.info(f"Chunked Label Propagation converged after {iteration + 1} iterations")
                break
        
        # Group nodes by their final labels
        label_to_nodes = defaultdict(list)
        for node, label in labels.items():
            label_to_nodes[label].append(node)
        
        # Convert to communities list
        communities = list(label_to_nodes.values())
        
        # Create node assignments mapping
        node_assignments = {node: i for i, community in enumerate(communities) for node in community}
        
        result = {
            "communities": communities,
            "node_assignments": node_assignments,
            "algorithm": "label_propagation_chunked",
            "iterations": iteration + 1 if 'iteration' in locals() else max_iterations
        }
        
        self.logger.info(f"Detected {len(communities)} communities using chunked Label Propagation")
        return result
    
    def _filter_nodes_by_labels(self, graph: Any, node_labels: Optional[List[str]]) -> List[str]:
        """Filter nodes by specified labels."""
        if node_labels is None:
            return list(graph.nodes()) if hasattr(graph, 'nodes') else []
        
        filtered_nodes = []
        for node in graph.nodes():
            if hasattr(graph, 'nodes'):
                node_data = graph.nodes[node]
                if isinstance(node_data, dict):
                    node_label = node_data.get('label') or node_data.get('type')
                    if node_label in node_labels:
                        filtered_nodes.append(node)
                else:
                    # Fallback - include all nodes if no label information
                    filtered_nodes.append(node)
        
        return filtered_nodes
    
    def _build_filtered_adjacency(
        self, 
        graph: Any, 
        nodes: List[str], 
        relationship_types: Optional[List[str]]
    ) -> Dict[str, List[str]]:
        """Build adjacency list filtered by nodes and relationship types."""
        adjacency = {}
        
        for node in nodes:
            neighbors = []
            
            if hasattr(graph, 'neighbors'):
                all_neighbors = list(graph.neighbors(node))
            elif hasattr(graph, 'get_neighbors'):
                all_neighbors = graph.get_neighbors(node)
            else:
                all_neighbors = []

            if all_neighbors and isinstance(all_neighbors[0], dict):
                all_neighbors = [
                    n.get("id") for n in all_neighbors
                    if isinstance(n, dict) and n.get("id")
                ]
            
            # Filter by relationship types if specified
            if relationship_types is not None and hasattr(graph, 'get_edge_data'):
                for neighbor in all_neighbors:
                    if neighbor in nodes:  # Only include filtered nodes
                        edge_data = graph.get_edge_data(node, neighbor)
                        if edge_data and isinstance(edge_data, dict):
                            edge_type = edge_data.get('type') or edge_data.get('relationship')
                            if edge_type in relationship_types:
                                neighbors.append(neighbor)
            else:
                # Include all neighbors that are in the filtered node set
                neighbors = [neighbor for neighbor in all_neighbors if neighbor in nodes]
            
            adjacency[node] = neighbors
        
        return adjacency
