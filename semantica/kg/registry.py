"""
Method Registry Module for Knowledge Graph

This module provides a method registry system for registering custom knowledge graph methods,
enabling extensibility and community contributions to the knowledge graph toolkit.

Supported Registration Types:
    - Method Registry: Register custom KG methods for:
        * "build": Knowledge graph building methods
        * "analyze": Graph analysis methods
        * "resolve": Entity resolution methods
        * "validate": Graph validation methods
        * "centrality": Centrality calculation methods
        * "community": Community detection methods
        * "connectivity": Connectivity analysis methods
        * "temporal": Temporal query methods

Note: Conflict detection and deduplication have been moved to dedicated modules.
    Use semantica.conflicts for conflict detection and semantica.deduplication for deduplication.

Algorithms Used:
    - Registry Pattern: Dictionary-based registration and lookup
    - Dynamic Registration: Runtime function registration
    - Type Checking: Type validation for registered components
    - Lookup Algorithms: Hash-based O(1) lookup for methods
    - Task-based Organization: Hierarchical organization by task type

Key Features:
    - Method registry for custom KG methods
    - Task-based method organization (build, analyze, resolve, validate, centrality, community, connectivity, temporal)
    - Dynamic registration and unregistration
    - Easy discovery of available methods
    - Support for community-contributed extensions

Main Classes:
    - MethodRegistry: Registry for custom KG methods

Global Instances:
    - method_registry: Global method registry instance

Example Usage:
    >>> import method_registry
    >>> method_registry.register("build", "custom_method", custom_build_function)
    >>> available = method_registry.list_all("build")
"""

import copy
from typing import Any, Callable, Dict, List, Optional


class MethodRegistry:
    """Registry for custom knowledge graph methods."""

    _methods: Dict[str, Dict[str, Callable]] = {
        "build": {},
        "analyze": {},
        "resolve": {},
        "validate": {},
        "centrality": {},
        "community": {},
        "connectivity": {},
        "temporal": {},
    }

    @classmethod
    def register(cls, task: str, name: str, method_func: Callable):
        """
        Register a custom KG method.

        Args:
            task: Task type ("build", "analyze", "resolve", "validate", "centrality", "community", "connectivity", "temporal")
            name: Method name
            method_func: Method function
        """
        if task not in cls._methods:
            cls._methods[task] = {}
        cls._methods[task][name] = method_func

    @classmethod
    def get(cls, task: str, name: str) -> Optional[Callable]:
        """
        Get method by task and name.

        Args:
            task: Task type ("build", "analyze", "resolve", "validate", "centrality", "community", "connectivity", "temporal")
            name: Method name

        Returns:
            Method function or None
        """
        return cls._methods.get(task, {}).get(name)

    @classmethod
    def list_all(cls, task: Optional[str] = None) -> Dict[str, List[str]]:
        """
        List all registered methods.

        Args:
            task: Optional task type to filter by

        Returns:
            Dictionary mapping task types to method names
        """
        if task:
            return {task: list(cls._methods.get(task, {}).keys())}
        return {t: list(m.keys()) for t, m in cls._methods.items()}

    @classmethod
    def unregister(cls, task: str, name: str):
        """
        Unregister a method.

        Args:
            task: Task type ("build", "analyze", "resolve", "validate", "conflict", "centrality", "community", "connectivity", "deduplicate", "temporal")
            name: Method name
        """
        if task in cls._methods and name in cls._methods[task]:
            del cls._methods[task][name]

    @classmethod
    def clear(cls, task: Optional[str] = None):
        """
        Clear all registered methods for a task or all tasks.

        Args:
            task: Optional task type to clear (clears all if None)
        """
        if task:
            if task in cls._methods:
                cls._methods[task].clear()
        else:
            for task_dict in cls._methods.values():
                task_dict.clear()


# Global registry
method_registry = MethodRegistry()


class AlgorithmRegistry:
    """
    Algorithm Registry for Enhanced Graph Algorithms.
    
    This class provides a registry system for enhanced graph algorithms,
    enabling algorithm discovery, method dispatch, and extensibility for
    the new graph analysis capabilities.
    
    Supported Algorithm Categories:
        - "embeddings": Node embedding algorithms (node2vec, etc.)
        - "similarity": Similarity calculation methods (cosine, euclidean, etc.)
        - "path_finding": Path finding algorithms (dijkstra, astar, bfs, etc.)
        - "link_prediction": Link prediction methods (preferential_attachment, etc.)
        - "centrality": Enhanced centrality measures (pagerank, etc.)
        - "community_detection": Enhanced community detection (label_propagation, etc.)
    
    Features:
        - Algorithm registration and discovery
        - Method dispatch for algorithm selection
        - Extensibility for new algorithms
        - Algorithm metadata and capabilities
        - Integration with convenience functions
    
    Example Usage:
        >>> from semantica.kg.registry import algorithm_registry
        >>> # Register custom algorithm
        >>> algorithm_registry.register("embeddings", "custom_algo", CustomEmbedder)
        >>> # Get algorithm class
        >>> embedder_class = algorithm_registry.get("embeddings", "node2vec")
        >>> # List available algorithms
        >>> embeddings = algorithm_registry.list_category("embeddings")
    """
    
    def __init__(self):
        """Initialize the algorithm registry.

        Instances start by sharing the module-level built-in catalog built
        once at import (#1177): the maps are bound by reference, and the
        first mutation copies them (copy-on-write), so constructing a
        registry no longer replays the 14 built-in ``register`` calls.
        """
        self._algorithms = _BUILTIN_ALGORITHMS
        self._metadata = _BUILTIN_METADATA
        self._capabilities = _BUILTIN_CAPABILITIES

    def _ensure_owned_maps(self) -> None:
        """Copy-on-write: leave the shared built-in catalog before mutating."""
        # globals().get: the catalog is built once at import time by a
        # throwaway builder instance whose register() calls arrive here
        # before the module-level constants exist.
        if (
            self._algorithms is globals().get("_BUILTIN_ALGORITHMS")
            or self._metadata is globals().get("_BUILTIN_METADATA")
            or self._capabilities is globals().get("_BUILTIN_CAPABILITIES")
        ):
            self._algorithms = {
                category: dict(algorithms)
                for category, algorithms in self._algorithms.items()
            }
            self._metadata = dict(self._metadata)
            self._capabilities = dict(self._capabilities)
    
    def register(
        self,
        category: str,
        name: str,
        algorithm_class: type,
        metadata: Optional[Dict[str, Any]] = None,
        capabilities: Optional[List[str]] = None
    ) -> None:
        """
        Register an algorithm.
        
        Args:
            category: Algorithm category
            name: Algorithm name
            algorithm_class: Algorithm class
            metadata: Algorithm metadata (description, parameters, etc.)
            capabilities: List of algorithm capabilities
            
        Raises:
            ValueError: If category is not supported or name already exists
        """
        if category not in self._algorithms:
            raise ValueError(f"Unsupported algorithm category: {category}")
        
        if name in self._algorithms[category]:
            raise ValueError(f"Algorithm {name} already registered in category {category}")
        
        # Register algorithm (copy-on-write away from the shared built-in catalog)
        self._ensure_owned_maps()
        self._algorithms[category][name] = algorithm_class
        
        # Store metadata
        if metadata:
            self._metadata[(category, name)] = metadata
        
        # Store capabilities
        if capabilities:
            self._capabilities[(category, name)] = capabilities
    
    def get(self, category: str, name: str) -> Optional[type]:
        """
        Get algorithm class by category and name.
        
        Args:
            category: Algorithm category
            name: Algorithm name
            
        Returns:
            Algorithm class or None if not found
        """
        return self._algorithms.get(category, {}).get(name)
    
    def create_instance(self, category: str, name: str, **kwargs) -> Any:
        """
        Create an instance of an algorithm.
        
        Args:
            category: Algorithm category
            name: Algorithm name
            **kwargs: Arguments for algorithm initialization
            
        Returns:
            Algorithm instance
            
        Raises:
            ValueError: If algorithm not found
        """
        if name not in self._algorithms.get(category, {}):
            raise ValueError(f"Algorithm {name} not found in category {category}")
        algorithm_class = self._algorithms[category][name]
        if algorithm_class is None:
            raise TypeError(f"Algorithm {name} has no implementation class registered")
        
        return algorithm_class(**kwargs)
    
    def list_category(self, category: str) -> List[str]:
        """
        List all algorithms in a category.
        
        Args:
            category: Algorithm category
            
        Returns:
            List of algorithm names
        """
        return list(self._algorithms.get(category, {}).keys())
    
    def list_all(self) -> Dict[str, List[str]]:
        """
        List all algorithms by category.
        
        Returns:
            Dictionary mapping categories to algorithm lists
        """
        return {category: list(algorithms.keys()) 
                for category, algorithms in self._algorithms.items()}
    
    def get_metadata(self, category: str, name: str) -> Optional[Dict[str, Any]]:
        """
        Get algorithm metadata.
        
        Args:
            category: Algorithm category
            name: Algorithm name
            
        Returns:
            Metadata dictionary or None if not found
        """
        metadata = self._metadata.get((category, name))
        return copy.deepcopy(metadata) if metadata is not None else None
    
    def get_capabilities(self, category: str, name: str) -> Optional[List[str]]:
        """
        Get algorithm capabilities.
        
        Args:
            category: Algorithm category
            name: Algorithm name
            
        Returns:
            List of capabilities or None if not found
        """
        capabilities = self._capabilities.get((category, name))
        return copy.deepcopy(capabilities) if capabilities is not None else None
    
    def unregister(self, category: str, name: str) -> None:
        """
        Unregister an algorithm.
        
        Args:
            category: Algorithm category
            name: Algorithm name
        """
        if category in self._algorithms and name in self._algorithms[category]:
            self._ensure_owned_maps()
            del self._algorithms[category][name]
            
            # Clean up metadata and capabilities
            metadata_key = (category, name)
            self._metadata.pop(metadata_key, None)
            self._capabilities.pop(metadata_key, None)
    
    def clear_category(self, category: str) -> None:
        """
        Clear all algorithms in a category.
        
        Args:
            category: Algorithm category
        """
        if category in self._algorithms:
            self._ensure_owned_maps()
            self._algorithms[category].clear()
            
            # Clean up metadata and capabilities
            keys_to_remove = [key for key in self._metadata.keys() if key[0] == category]
            for key in keys_to_remove:
                self._metadata.pop(key, None)
                self._capabilities.pop(key, None)
    
    def clear_all(self) -> None:
        """Clear all registered algorithms.

        Rebinds to fresh empty owned maps rather than mutating in place, so
        neither the shared built-in catalog nor other instances are affected.
        """
        self._algorithms = {
            category: {}
            for category in self._algorithms
        }
        self._metadata = {}
        self._capabilities = {}
    
    def _register_builtin_algorithms(self) -> None:
        """Rebind to the shared built-in catalog.

        The catalog itself is built once at import (see
        ``_build_builtin_algorithm_catalog``); the shared maps are never
        mutated in place — every mutating method copies first — so restoring
        the built-ins is a plain pointer rebind, used e.g. after ``clear_all``.
        """
        self._algorithms = _BUILTIN_ALGORITHMS
        self._metadata = _BUILTIN_METADATA
        self._capabilities = _BUILTIN_CAPABILITIES


def _register_builtin_algorithms_on(builder: "AlgorithmRegistry") -> None:
    """Populate ``builder`` with the built-in algorithm catalog.

    The catalog never changes, so this replay runs exactly once at import
    (see ``_build_builtin_algorithm_catalog``); ``AlgorithmRegistry.__init__``
    binds the result instead of re-running it (#1177).
    """

    # Node embeddings
    builder.register(
        "embeddings",
        "node2vec",
        None,  # Will be imported when needed
        metadata={
            "description": "Node2Vec algorithm for node embeddings",
            "parameters": ["embedding_dimension", "walk_length", "num_walks", "p", "q"],
            "complexity": "O(V * (L * W + E))",
            "quality": "High",
            "use_case": "Structural similarity analysis"
        },
        capabilities=["biased_random_walks", "word2vec_training", "embedding_storage"]
    )
    
    # Similarity metrics
    similarity_metrics = ["cosine", "euclidean", "manhattan", "correlation"]
    for metric in similarity_metrics:
        builder.register(
            "similarity",
            metric,
            None,
            metadata={
                "description": f"{metric.title()} similarity for embeddings",
                "parameters": ["normalization"],
                "complexity": "O(d)" if metric != "correlation" else "O(d)",
                "quality": "Standard",
                "use_case": "Embedding comparison"
            },
            capabilities=["vector_similarity", "batch_computation"]
        )
    
    # Path finding
    path_algorithms = {
        "dijkstra": {
            "description": "Dijkstra's algorithm for shortest paths",
            "parameters": ["weight_attribute", "default_weight"],
            "complexity": "O(E + V log V)",
            "quality": "Optimal",
            "use_case": "Weighted shortest path"
        },
        "astar": {
            "description": "A* search with heuristic guidance",
            "parameters": ["heuristic", "weight_attribute"],
            "complexity": "O(E) (with good heuristic)",
            "quality": "Optimal",
            "use_case": "Guided path finding"
        },
        "bfs": {
            "description": "Breadth-first search for unweighted paths",
            "parameters": [],
            "complexity": "O(V + E)",
            "quality": "Optimal (unweighted)",
            "use_case": "Unweighted shortest path"
        }
    }
    
    for name, meta in path_algorithms.items():
        builder.register(
            "path_finding",
            name,
            None,
            metadata=meta,
            capabilities=["shortest_path", "path_reconstruction"]
        )
    
    # Link prediction
    link_methods = {
        "preferential_attachment": {
            "description": "Preferential attachment link prediction",
            "parameters": [],
            "complexity": "O(1)",
            "quality": "Good for scale-free networks",
            "use_case": "Fast link prediction"
        },
        "common_neighbors": {
            "description": "Common neighbors link prediction",
            "parameters": [],
            "complexity": "O(min(deg(u), deg(v)))",
            "quality": "Good for dense networks",
            "use_case": "Simple similarity-based prediction"
        },
        "jaccard_coefficient": {
            "description": "Jaccard coefficient link prediction",
            "parameters": [],
            "complexity": "O(min(deg(u), deg(v)))",
            "quality": "Normalized similarity",
            "use_case": "Normalized link prediction"
        },
        "adamic_adar": {
            "description": "Adamic-Adar index link prediction",
            "parameters": [],
            "complexity": "O(min(deg(u), deg(v)))",
            "quality": "Degree-weighted similarity",
            "use_case": "Sophisticated link prediction"
        }
    }
    
    for name, meta in link_methods.items():
        builder.register(
            "link_prediction",
            name,
            None,
            metadata=meta,
            capabilities=["neighbor_analysis", "similarity_scoring"]
        )
    
    # Enhanced centrality
    builder.register(
        "centrality",
        "pagerank",
        None,
        metadata={
            "description": "PageRank centrality calculation",
            "parameters": ["max_iterations", "damping_factor", "tolerance"],
            "complexity": "O(E * iterations)",
            "quality": "Industry standard",
            "use_case": "Importance ranking"
        },
        capabilities=["iterative_computation", "convergence_detection"]
    )
    
    # Enhanced community detection
    builder.register(
        "community_detection",
        "label_propagation",
        None,
        metadata={
            "description": "Label propagation community detection",
            "parameters": ["max_iterations", "random_seed"],
            "complexity": "O(E * iterations)",
            "quality": "Good for large graphs",
            "use_case": "Fast community detection"
        },
        capabilities=["iterative_labeling", "convergence_detection"]
    )


def _build_builtin_algorithm_catalog():
    """Build the shared built-in algorithm/metadata/capability maps once.

    Returns three structures that instances bind by reference until their
    first mutation (copy-on-write), so the shared catalog is effectively
    immutable.
    """
    builder = AlgorithmRegistry.__new__(AlgorithmRegistry)
    builder._algorithms = {
        category: {}
        for category in (
            "embeddings",
            "similarity",
            "path_finding",
            "link_prediction",
            "centrality",
            "community_detection",
        )
    }
    builder._metadata = {}
    builder._capabilities = {}
    _register_builtin_algorithms_on(builder)
    return builder._algorithms, builder._metadata, builder._capabilities


_BUILTIN_ALGORITHMS, _BUILTIN_METADATA, _BUILTIN_CAPABILITIES = (
    _build_builtin_algorithm_catalog()
)


# Global algorithm registry
algorithm_registry = AlgorithmRegistry()
