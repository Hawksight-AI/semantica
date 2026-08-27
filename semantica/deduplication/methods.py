"""
Deduplication Methods Module

This module provides all deduplication methods as simple, reusable functions for
duplicate detection, entity merging, similarity calculation, and clustering. It supports
multiple deduplication approaches ranging from simple exact matching to advanced
semantic similarity and clustering algorithms.

Supported Methods:

Similarity Calculation:
    - "exact": Exact string matching
    - "levenshtein": Levenshtein distance-based similarity
    - "jaro_winkler": Jaro-Winkler similarity with prefix bonus
    - "cosine": Cosine similarity for embeddings
    - "property": Property value comparison
    - "relationship": Jaccard similarity of relationships
    - "embedding": Cosine similarity of vector embeddings
    - "multi_factor": Weighted aggregation of all components

Duplicate Detection:
    - "pairwise": O(n²) comparison of all entity pairs
    - "batch": Efficient batch similarity calculation
    - "incremental": O(n×m) comparison for new vs existing entities
    - "group": Union-find algorithm for duplicate group formation

Entity Merging:
    - "keep_first": Preserve first entity, merge others
    - "keep_last": Preserve last entity, merge others
    - "keep_most_complete": Preserve entity with most properties/relationships
    - "keep_highest_confidence": Preserve entity with highest confidence
    - "merge_all": Combine all properties and relationships
    - "custom": User-defined merge logic

Clustering:
    - "graph_based": Union-find algorithm for connected components
    - "hierarchical": Agglomerative clustering for large datasets

Algorithms Used:

Similarity Calculation:
    - Levenshtein Distance: Dynamic programming algorithm for edit distance
    - Jaro Similarity: Character-based similarity with match window
    - Jaro-Winkler Similarity: Jaro with prefix bonus (up to 4 characters)
    - Cosine Similarity: Vector dot product divided by magnitudes
    - Jaccard Similarity: Intersection over union for sets
    - Property Matching: Weighted comparison of property values
    - Multi-factor Aggregation: Weighted sum of similarity components

Duplicate Detection:
    - Pairwise Comparison: All-pairs similarity calculation
    - Batch Processing: Vectorized similarity calculations
    - Union-Find Algorithm: Disjoint set union for group formation
    - Confidence Scoring: Multi-factor confidence calculation
    - Incremental Processing: Efficient new vs existing comparison

Clustering:
    - Union-Find (Disjoint Set Union): Connected component detection
    - Hierarchical Clustering: Agglomerative bottom-up clustering
    - Similarity Graph: Graph construction from similarity scores
    - Cluster Quality Metrics: Cohesion and separation measures

Entity Merging:
    - Strategy Pattern: Multiple merge strategies
    - Conflict Resolution: Voting, credibility-weighted, temporal, confidence-based
    - Property Merging: Rule-based property combination
    - Relationship Preservation: Union of relationship sets
    - Provenance Tracking: Metadata preservation during merges

Key Features:
    - Multiple similarity calculation methods
    - Multiple duplicate detection methods
    - Multiple entity merging strategies
    - Clustering methods for batch processing
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - detect_duplicates: Duplicate detection wrapper
    - merge_entities: Entity merging wrapper
    - calculate_similarity: Similarity calculation wrapper
    - build_clusters: Cluster building wrapper
    - get_deduplication_method: Get deduplication method by name

Example Usage:
    >>> from semantica.deduplication.methods import detect_duplicates, calculate_similarity
    >>> duplicates = detect_duplicates(entities, method="pairwise", similarity_threshold=0.8)
    >>> similarity = calculate_similarity(entity1, entity2, method="levenshtein")
    >>> from semantica.deduplication.methods import get_deduplication_method
    >>> method = get_deduplication_method("similarity", "custom_method")

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Callable, Dict, List, Optional, Union, Tuple

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from .cluster_builder import Cluster, ClusterBuilder, ClusterResult
from .duplicate_detector import DuplicateCandidate, DuplicateDetector, DuplicateGroup
from .entity_merger import EntityMerger, MergeOperation
from .merge_strategy import MergeStrategy, MergeStrategyManager
from .registry import method_registry
from .similarity_calculator import SimilarityCalculator, SimilarityResult

logger = get_logger("deduplication_methods")


def calculate_similarity(
    entity1: Dict[str, Any],
    entity2: Dict[str, Any],
    method: str = "multi_factor",
    **kwargs,
) -> SimilarityResult:
    """
    Calculate similarity between two entities (convenience function).

    This is a user-friendly wrapper that calculates similarity using the specified method.

    Args:
        entity1: First entity dictionary
        entity2: Second entity dictionary
        method: Similarity calculation method (default: "multi_factor")
            - "exact": Exact string matching
            - "levenshtein": Levenshtein distance-based similarity
            - "jaro_winkler": Jaro-Winkler similarity
            - "cosine": Cosine similarity for embeddings
            - "property": Property value comparison
            - "relationship": Jaccard similarity of relationships
            - "embedding": Cosine similarity of vector embeddings
            - "multi_factor": Weighted aggregation of all components
        **kwargs: Additional options passed to SimilarityCalculator

    Returns:
        SimilarityResult object containing:
            - score: Similarity score (0.0 to 1.0)
            - method: Calculation method used
            - components: Dict of individual component scores
            - metadata: Additional metadata

    Examples:
        >>> from semantica.deduplication.methods import calculate_similarity
        >>> entity1 = {"name": "Apple Inc.", "type": "Company"}
        >>> entity2 = {"name": "Apple", "type": "Company"}
        >>> result = calculate_similarity(entity1, entity2, method="levenshtein")
        >>> print(f"Similarity: {result.score:.2f}")
    """
    # Check for custom method in registry, skip self-referential wrappers.
    # _multi_factor_similarity is registered under "multi_factor" and calls back
    # into calculate_similarity(method="multi_factor"), creating indirect
    # infinite recursion.  The identity guard short-circuits that loop.
    custom_method = method_registry.get("similarity", method)
    if custom_method and custom_method is not calculate_similarity:
        return custom_method(entity1, entity2, **kwargs)

    # Use default SimilarityCalculator
    calculator = SimilarityCalculator(**kwargs)

    # Map method to calculator method
    if method == "exact":
        name1 = entity1.get("name", "")
        name2 = entity2.get("name", "")
        score = 1.0 if name1.lower().strip() == name2.lower().strip() else 0.0
        return SimilarityResult(score=score, method="exact")
    elif method == "levenshtein":
        name1 = entity1.get("name", "")
        name2 = entity2.get("name", "")
        score = calculator.calculate_string_similarity(
            name1, name2, method="levenshtein"
        )
        return SimilarityResult(score=score, method="levenshtein")
    elif method == "jaro_winkler":
        name1 = entity1.get("name", "")
        name2 = entity2.get("name", "")
        score = calculator.calculate_string_similarity(
            name1, name2, method="jaro_winkler"
        )
        return SimilarityResult(score=score, method="jaro_winkler")
    elif method == "cosine":
        name1 = entity1.get("name", "")
        name2 = entity2.get("name", "")
        score = calculator.calculate_string_similarity(name1, name2, method="cosine")
        return SimilarityResult(score=score, method="cosine")
    elif method == "property":
        score = calculator.calculate_property_similarity(entity1, entity2)
        return SimilarityResult(score=score, method="property")
    elif method == "relationship":
        score = calculator.calculate_relationship_similarity(entity1, entity2)
        return SimilarityResult(score=score, method="relationship")
    elif method == "embedding":
        if "embedding" in entity1 and "embedding" in entity2:
            score = calculator.calculate_embedding_similarity(
                entity1["embedding"], entity2["embedding"]
            )
            return SimilarityResult(score=score, method="embedding")
        else:
            return SimilarityResult(score=0.0, method="embedding")
    else:  # multi_factor (default)
        return calculator.calculate_similarity(entity1, entity2, **kwargs)


def detect_duplicates(
    entities: List[Dict[str, Any]],
    method: str = "pairwise",
    similarity_threshold: float = 0.7,
    confidence_threshold: float = 0.6,
    **kwargs,
) -> List[Union[DuplicateCandidate, DuplicateGroup]]:
    """
    Detect duplicate entities (convenience function).

    This is a user-friendly wrapper that detects duplicates using the specified method.

    Args:
        entities: List of entity dictionaries to check for duplicates
        method: Detection method (default: "pairwise")
            - "pairwise": O(n²) comparison of all entity pairs
            - "batch": Efficient batch similarity calculation
            - "incremental": O(n×m) comparison for new vs existing entities
            - "group": Union-find algorithm for duplicate group formation
        similarity_threshold: Minimum similarity score to consider duplicates (default: 0.7)
        confidence_threshold: Minimum confidence score for duplicate candidates (default: 0.6)
        **kwargs: Additional options passed to DuplicateDetector

    Returns:
        List of DuplicateCandidate objects (for pairwise/batch/incremental) or
        List of DuplicateGroup objects (for group method)

    Examples:
        >>> from semantica.deduplication.methods import detect_duplicates
        >>> entities = [
        ...     {"id": "1", "name": "Apple Inc."},
        ...     {"id": "2", "name": "Apple"},
        ...     {"id": "3", "name": "Microsoft"}
        ... ]
        >>> duplicates = detect_duplicates(entities, method="pairwise", similarity_threshold=0.8)
        >>> print(f"Found {len(duplicates)} duplicate candidates")
    """
    # Check for custom method in registry, skip self-referential wrappers.
    # _pairwise_detection is registered under "pairwise" and calls back into
    # detect_duplicates(method="pairwise"), creating indirect infinite recursion.
    custom_method = method_registry.get("detection", method)
    if custom_method and custom_method is not detect_duplicates:
        return custom_method(
            entities, similarity_threshold=similarity_threshold, **kwargs
        )

    # Use default DuplicateDetector
    detector = DuplicateDetector(
        similarity_threshold=similarity_threshold,
        confidence_threshold=confidence_threshold,
        **kwargs,
    )

    # Map method to detector method
    if method == "group":
        return detector.detect_duplicate_groups(entities, **kwargs)
    elif method == "incremental":
        # For incremental, need to split entities
        existing = kwargs.pop("existing_entities", entities[: len(entities) // 2])
        new = kwargs.pop("new_entities", entities[len(entities) // 2 :])
        return detector.incremental_detect(new, existing, **kwargs)
    else:  # pairwise or batch (default)
        return detector.detect_duplicates(entities, **kwargs)


def dedup_triplets(
    relationships: List[Dict[str, Any]],
    mode: str = "semantic_v2",
    threshold: float = 0.85,
    **kwargs,
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Detect duplicate relationships/triplets (convenience function).

    Args:
        relationships: List of relationship dictionaries to check.
        mode: Dedup mode ("legacy" or "semantic_v2")
        threshold: Minimum similarity threshold for fuzzy matching.
        **kwargs: Additional options for Semantic mode:
            - predicate_synonym_map: Dict mapping synonyms to canonical predicates.
            - literal_normalization_enabled: Boolean to enable literal normalization.

    Returns:
        List of duplicate relationship piars (rel1, rel2).
    """

    # Check for custom method in registry (but not ourself — identity guard
    # consistent with the other dispatch functions in this module).
    custom_method = method_registry.get("detection", "triplets")
    if custom_method and custom_method is not dedup_triplets:
        return custom_method(relationships, mode=mode, threshold=threshold, **kwargs)

    detector = DuplicateDetector(**kwargs)
    options = {"threshold": threshold, "relationship_dedup_mode": mode, **kwargs}

    return detector.detect_relationship_duplicates(relationships, **options)


def merge_entities(
    entities: List[Dict[str, Any]],
    method: str = "keep_most_complete",
    preserve_provenance: bool = True,
    **kwargs,
) -> List[MergeOperation]:
    """
    Merge duplicate entities (convenience function).

    This is a user-friendly wrapper that merges entities using the specified method.

    Args:
        entities: List of entity dictionaries to merge (should be duplicates)
        method: Merge strategy (default: "keep_most_complete")
            - "keep_first": Preserve first entity, merge others
            - "keep_last": Preserve last entity, merge others
            - "keep_most_complete": Preserve entity with most properties/relationships
            - "keep_highest_confidence": Preserve entity with highest confidence
            - "merge_all": Combine all properties and relationships
            - "custom": User-defined merge logic
        preserve_provenance: Whether to preserve provenance information (default: True)
        **kwargs: Additional options passed to EntityMerger

    Returns:
        List of MergeOperation objects containing merge results

    Examples:
        >>> from semantica.deduplication.methods import merge_entities
        >>> duplicate_entities = [
        ...     {"id": "1", "name": "Apple Inc.", "type": "Company"},
        ...     {"id": "2", "name": "Apple", "type": "Company"}
        ... ]
        >>> operations = merge_entities(duplicate_entities, method="keep_most_complete")
        >>> print(f"Performed {len(operations)} merge operations")
    """
    # Check for custom method in registry, skip self-referential registration.
    # merge_entities is now registered directly under its default method name;
    # the identity guard prevents a direct recursion loop.
    custom_method = method_registry.get("merging", method)
    if custom_method and custom_method is not merge_entities:
        return custom_method(
            entities, preserve_provenance=preserve_provenance, **kwargs
        )

    # Use default EntityMerger
    merger = EntityMerger(preserve_provenance=preserve_provenance, **kwargs)

    # Merge duplicates (EntityMerger handles string strategies directly)
    return merger.merge_duplicates(entities, strategy=method, **kwargs)


def build_clusters(
    entities: List[Dict[str, Any]],
    method: str = "graph_based",
    similarity_threshold: float = 0.7,
    **kwargs,
) -> ClusterResult:
    """
    Build clusters of similar entities (convenience function).

    This is a user-friendly wrapper that builds clusters using the specified method.

    Args:
        entities: List of entity dictionaries to cluster
        method: Clustering method (default: "graph_based")
            - "graph_based": Union-find algorithm for connected components
            - "hierarchical": Agglomerative clustering for large datasets
        similarity_threshold: Minimum similarity for entities in same cluster (default: 0.7)
        **kwargs: Additional options passed to ClusterBuilder

    Returns:
        ClusterResult object containing:
            - clusters: List of Cluster objects
            - unclustered: List of entities not in any cluster
            - quality_metrics: Cluster quality metrics
            - metadata: Additional metadata

    Examples:
        >>> from semantica.deduplication.methods import build_clusters
        >>> entities = [{"id": str(i), "name": f"Entity {i}"} for i in range(100)]
        >>> result = build_clusters(entities, method="graph_based", similarity_threshold=0.8)
        >>> print(f"Found {len(result.clusters)} clusters")
    """
    # Check for custom method in registry, skip self-referential wrappers.
    # _graph_based_clustering is registered under "graph_based" and calls back
    # into build_clusters(method="graph_based"), creating indirect infinite
    # recursion.
    custom_method = method_registry.get("clustering", method)
    if custom_method and custom_method is not build_clusters:
        return custom_method(
            entities, similarity_threshold=similarity_threshold, **kwargs
        )

    # Use default ClusterBuilder
    builder = ClusterBuilder(
        similarity_threshold=similarity_threshold,
        use_hierarchical=(method == "hierarchical"),
        **kwargs,
    )

    return builder.build_clusters(entities, **kwargs)


def get_deduplication_method(task: str, name: str) -> Optional[Callable]:
    """
    Get deduplication method by task and name.

    This function retrieves a registered deduplication method from the registry
    or returns a built-in method if available.

    Args:
        task: Task type ("detection", "merging", "similarity", "clustering")
        name: Method name

    Returns:
        Method function or None if not found

    Examples:
        >>> from semantica.deduplication.methods import get_deduplication_method
        >>> method = get_deduplication_method("similarity", "custom_method")
        >>> if method:
        ...     result = method(entity1, entity2)
    """
    # First check registry
    method = method_registry.get(task, name)
    if method:
        return method

    # Check built-in methods
    builtin_methods = {
        "similarity": {
            "exact": lambda e1, e2, **kw: calculate_similarity(
                e1, e2, method="exact", **kw
            ),
            "levenshtein": lambda e1, e2, **kw: calculate_similarity(
                e1, e2, method="levenshtein", **kw
            ),
            "jaro_winkler": lambda e1, e2, **kw: calculate_similarity(
                e1, e2, method="jaro_winkler", **kw
            ),
            "cosine": lambda e1, e2, **kw: calculate_similarity(
                e1, e2, method="cosine", **kw
            ),
            "property": lambda e1, e2, **kw: calculate_similarity(
                e1, e2, method="property", **kw
            ),
            "relationship": lambda e1, e2, **kw: calculate_similarity(
                e1, e2, method="relationship", **kw
            ),
            "embedding": lambda e1, e2, **kw: calculate_similarity(
                e1, e2, method="embedding", **kw
            ),
            "multi_factor": lambda e1, e2, **kw: calculate_similarity(
                e1, e2, method="multi_factor", **kw
            ),
        },
        "detection": {
            "pairwise": lambda entities, **kw: detect_duplicates(
                entities, method="pairwise", **kw
            ),
            "batch": lambda entities, **kw: detect_duplicates(
                entities, method="batch", **kw
            ),
            "incremental": lambda entities, **kw: detect_duplicates(
                entities, method="incremental", **kw
            ),
            "group": lambda entities, **kw: detect_duplicates(
                entities, method="group", **kw
            ),
        },
        "merging": {
            "keep_first": lambda entities, **kw: merge_entities(
                entities, method="keep_first", **kw
            ),
            "keep_last": lambda entities, **kw: merge_entities(
                entities, method="keep_last", **kw
            ),
            "keep_most_complete": lambda entities, **kw: merge_entities(
                entities, method="keep_most_complete", **kw
            ),
            "keep_highest_confidence": lambda entities, **kw: merge_entities(
                entities, method="keep_highest_confidence", **kw
            ),
            "merge_all": lambda entities, **kw: merge_entities(
                entities, method="merge_all", **kw
            ),
        },
        "clustering": {
            "graph_based": lambda entities, **kw: build_clusters(
                entities, method="graph_based", **kw
            ),
            "hierarchical": lambda entities, **kw: build_clusters(
                entities, method="hierarchical", **kw
            ),
        },
    }

    if task in builtin_methods and name in builtin_methods[task]:
        return builtin_methods[task][name]

    return None


def list_available_methods(task: Optional[str] = None) -> Dict[str, List[str]]:
    """
    List all available deduplication methods.

    Args:
        task: Optional task type to filter by

    Returns:
        Dictionary mapping task types to method names

    Examples:
        >>> from semantica.deduplication.methods import list_available_methods
        >>> all_methods = list_available_methods()
        >>> similarity_methods = list_available_methods("similarity")
    """
    # Get registered methods
    registered = method_registry.list_all(task=task)

    # Add built-in methods
    builtin_methods = {
        "similarity": [
            "exact",
            "levenshtein",
            "jaro_winkler",
            "cosine",
            "property",
            "relationship",
            "embedding",
            "multi_factor",
        ],
        "detection": ["pairwise", "batch", "incremental", "group"],
        "merging": [
            "keep_first",
            "keep_last",
            "keep_most_complete",
            "keep_highest_confidence",
            "merge_all",
        ],
        "clustering": ["graph_based", "hierarchical"],
    }

    if task:
        # Merge for specific task
        result = {
            task: list(set(registered.get(task, []) + builtin_methods.get(task, [])))
        }
    else:
        # Merge for all tasks
        result = {}
        for t in set(list(registered.keys()) + list(builtin_methods.keys())):
            result[t] = list(set(registered.get(t, []) + builtin_methods.get(t, [])))

    return result


# Register default methods with registry.
# The public dispatch functions are registered directly so the identity guard
# in each function short-circuits the self-reference rather than going through
# an intermediate wrapper that re-enters the same dispatch path.
method_registry.register("similarity", "multi_factor", calculate_similarity)
method_registry.register("detection", "pairwise", detect_duplicates)
method_registry.register("merging", "keep_most_complete", merge_entities)
method_registry.register("clustering", "graph_based", build_clusters)
method_registry.register("detection", "triplets", dedup_triplets)
