"""
Decision Vector Methods Module

This module provides convenience functions for decision vector operations,
offering one-liner methods for common decision tracking tasks.

Key Features:
    - Quick decision recording with automatic embedding
    - Precedent search with configurable parameters
    - Decision explanation generation
    - Similar decision finding
    - Batch processing utilities

Algorithms Used:
    - Node2Vec: Structural embeddings from KG module for graph topology
    - PathFinder: Shortest path algorithms for multi-hop reasoning
    - CommunityDetector: Community detection for contextual relationships
    - CentralityCalculator: Centrality measures for entity importance weighting
    - SimilarityCalculator: Graph-based similarity calculations
    - ConnectivityAnalyzer: Graph connectivity analysis for embedding enhancement
    - HybridSimilarityCalculator: Combines semantic + structural embeddings
    - Cosine Similarity: Primary similarity metric for vector comparisons
    - Pearson Correlation: Alternative similarity metric
    - Euclidean Distance: Distance-based similarity calculation

Functions:
    - quick_decision: Record a decision with minimal parameters
    - find_precedents: Find similar decisions (precedents)
    - explain: Generate decision explanation
    - similar_to: Find decisions similar to a given scenario
    - batch_decisions: Process multiple decisions efficiently

Example Usage:
    >>> from semantica.vector_store.decision_vector_methods import quick_decision, find_precedents
    >>> decision_id = quick_decision("Credit limit increase", "approved")
    >>> precedents = find_precedents("Credit limit increase", limit=5)
"""

from typing import Any, Dict, List, Optional, Union
import numpy as np

# Global vector store instance for convenience functions
_global_vector_store: Optional[Any] = None


def set_global_vector_store(vector_store: Any) -> None:
    """Set the global vector store for convenience functions."""
    global _global_vector_store
    _global_vector_store = vector_store


def get_global_vector_store() -> Any:
    """Get the global vector store instance."""
    if _global_vector_store is None:
        raise RuntimeError("Global vector store not set. Call set_global_vector_store() first.")
    return _global_vector_store


def quick_decision(
    scenario: str,
    outcome: Optional[str] = None,
    reasoning: Optional[str] = None,
    confidence: Optional[float] = None,
    entities: Optional[List[str]] = None,
    category: Optional[str] = None,
    vector_store: Optional[Any] = None,
    **kwargs
) -> str:
    """
    Quick decision recording with automatic embedding generation.
    
    Args:
        scenario: Decision scenario description
        outcome: Decision outcome
        reasoning: Decision reasoning
        confidence: Decision confidence score
        entities: List of entities involved
        category: Decision category
        vector_store: Vector store instance (uses global if None)
        **kwargs: Additional metadata
        
    Returns:
        Decision vector ID
    """
    store = vector_store or get_global_vector_store()
    
    return store.store_decision(
        scenario=scenario,
        outcome=outcome,
        reasoning=reasoning,
        confidence=confidence,
        entities=entities,
        category=category,
        **kwargs
    )


def find_precedents(
    query: str,
    limit: int = 10,
    semantic_weight: float = 0.7,
    structural_weight: float = 0.3,
    category: Optional[str] = None,
    outcome: Optional[str] = None,
    confidence_min: Optional[float] = None,
    filters: Optional[Dict[str, Any]] = None,
    vector_store: Optional[Any] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Find similar decisions (precedents) for a given query.

    Args:
        query: Search query
        limit: Number of results
        semantic_weight: Weight for semantic similarity
        structural_weight: Weight for structural similarity
        category: Filter by decision category
        outcome: Filter by decision outcome
        confidence_min: Minimum confidence threshold
        filters: Additional metadata filters
        vector_store: Vector store instance (uses global if None)
        **kwargs: Additional search parameters

    Returns:
        List of similar decisions with scores
    """
    store = vector_store or get_global_vector_store()

    # Build filters, merging with any provided filters dict
    merged_filters = dict(filters) if filters else {}
    if category is not None:
        merged_filters["category"] = category
    if outcome is not None:
        merged_filters["outcome"] = outcome
    if confidence_min is not None:
        merged_filters["confidence"] = {"min": confidence_min}

    return store.search_decisions(
        query=query,
        semantic_weight=semantic_weight,
        structural_weight=structural_weight,
        filters=merged_filters,
        limit=limit,
        **kwargs
    )


def explain(
    decision_id: str,
    include_paths: bool = True,
    include_confidence: bool = True,
    include_weights: bool = True,
    vector_store: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Generate explanation for a decision.
    
    Args:
        decision_id: Decision vector ID
        include_paths: Whether to include reasoning paths
        include_confidence: Whether to include confidence scores
        include_weights: Whether to include similarity weights
        vector_store: Vector store instance (uses global if None)
        
    Returns:
        Decision explanation
    """
    store = vector_store or get_global_vector_store()
    
    return store.explain_decision(
        decision_id=decision_id,
        include_paths=include_paths,
        include_confidence=include_confidence,
        include_weights=include_weights
    )


def similar_to(
    scenario: str,
    limit: int = 10,
    use_hybrid_search: bool = True,
    category: Optional[str] = None,
    outcome: Optional[str] = None,
    vector_store: Optional[Any] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Find decisions similar to a given scenario.
    
    Args:
        scenario: Scenario to find similar decisions for
        limit: Number of results
        use_hybrid_search: Whether to use hybrid similarity
        category: Filter by decision category
        outcome: Filter by decision outcome
        vector_store: Vector store instance (uses global if None)
        **kwargs: Additional search parameters
        
    Returns:
        List of similar decisions
    """
    store = vector_store or get_global_vector_store()
    
    # Build filters
    filters = {}
    if category is not None:
        filters["category"] = category
    if outcome is not None:
        filters["outcome"] = outcome
    
    return store.search_decisions(
        query=scenario,
        filters=filters,
        limit=limit,
        use_hybrid_search=use_hybrid_search,
        **kwargs
    )


def batch_decisions(
    decisions: List[Dict[str, Any]],
    batch_size: int = 32,
    vector_store: Optional[Any] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Process multiple decisions efficiently in batch.
    
    Args:
        decisions: List of decision data dictionaries
        batch_size: Batch size for processing
        vector_store: Vector store instance (uses global if None)
        **kwargs: Additional processing parameters
        
    Returns:
        List of processed decision results
    """
    store = vector_store or get_global_vector_store()
    
    return store.process_decision_batch(
        decisions=decisions,
        batch_size=batch_size,
        **kwargs
    )


def filter_decisions(
    query: Optional[str] = None,
    time_range: Optional[str] = None,
    confidence_min: Optional[float] = None,
    category: Optional[str] = None,
    outcome: Optional[str] = None,
    entities: Optional[List[str]] = None,
    limit: int = 50,
    vector_store: Optional[Any] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Filter decisions with natural language queries.
    
    Args:
        query: Natural language query
        time_range: Time range filter (e.g., "last_30_days")
        confidence_min: Minimum confidence threshold
        category: Decision category filter
        outcome: Decision outcome filter
        entities: Entities to filter by
        limit: Maximum number of results
        vector_store: Vector store instance (uses global if None)
        **kwargs: Additional filter parameters
        
    Returns:
        List of filtered decisions
    """
    store = vector_store or get_global_vector_store()
    
    return store.filter_decisions(
        query=query,
        time_range=time_range,
        confidence_min=confidence_min,
        category=category,
        outcome=outcome,
        entities=entities,
        limit=limit,
        **kwargs
    )


def get_decision_context(
    decision_id: str,
    depth: int = 2,
    include_entities: bool = True,
    include_policies: bool = True,
    max_hops: int = 3,
    vector_store: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Get decision context graph.
    
    Args:
        decision_id: Decision vector ID
        depth: Context depth
        include_entities: Whether to include entities
        include_policies: Whether to include policies
        max_hops: Maximum hops for context expansion
        vector_store: Vector store instance (uses global if None)
        
    Returns:
        Decision context graph
    """
    store = vector_store or get_global_vector_store()
    
    return store.build_decision_context(
        decision_id=decision_id,
        depth=depth,
        include_entities=include_entities,
        include_policies=include_policies,
        max_hops=max_hops
    )


def search_by_entities(
    entities: List[str],
    limit: int = 10,
    vector_store: Optional[Any] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Search decisions by entities.
    
    Args:
        entities: List of entities to search for
        limit: Number of results
        vector_store: Vector store instance (uses global if None)
        **kwargs: Additional search parameters
        
    Returns:
        List of decisions containing the specified entities
    """
    return filter_decisions(
        entities=entities,
        limit=limit,
        vector_store=vector_store,
        **kwargs
    )


def get_decision_statistics(
    vector_store: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Get decision statistics from the vector store.
    
    Args:
        vector_store: Vector store instance (uses global if None)
        
    Returns:
        Decision statistics
    """
    store = vector_store or get_global_vector_store()
    
    # Count decisions by category
    category_counts = {}
    outcome_counts = {}
    confidence_values = []
    
    # Not all backends expose internal metadata dictionaries (e.g. FAISS).
    if not hasattr(store, "metadata"):
        return {
            "total_decisions": 0,
            "categories": {},
            "outcomes": {},
            "average_confidence": 0.0,
            "min_confidence": 0.0,
            "max_confidence": 0.0,
            "has_structural_embeddings": False,
            "warning": "Statistics not supported for persistent backends without full metadata access."
        }
    
    for metadata in store.metadata.values():
        # Count by category
        category = metadata.get("category", "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        
        # Count by outcome
        outcome = metadata.get("outcome", "unknown")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        
        # Collect confidence values
        confidence = metadata.get("confidence", 0.5)
        confidence_values.append(confidence)
    
    # Calculate statistics
    stats = {
        "total_decisions": len(store.metadata),
        "categories": category_counts,
        "outcomes": outcome_counts,
        "average_confidence": np.mean(confidence_values) if confidence_values else 0.0,
        "min_confidence": np.min(confidence_values) if confidence_values else 0.0,
        "max_confidence": np.max(confidence_values) if confidence_values else 0.0,
        "has_structural_embeddings": any(
            "structural_embedding" in metadata 
            for metadata in store.metadata.values()
        )
    }
    
    return stats


def update_similarity_weights(
    semantic_weight: float,
    structural_weight: float,
    vector_store: Optional[Any] = None
) -> None:
    """
    Update similarity weights for the vector store.
    
    Args:
        semantic_weight: Weight for semantic similarity
        structural_weight: Weight for structural similarity
        vector_store: Vector store instance (uses global if None)
    """
    store = vector_store or get_global_vector_store()
    
    if store.decision_pipeline:
        store.decision_pipeline.update_weights(semantic_weight, structural_weight)
    
    if store.hybrid_calculator:
        store.hybrid_calculator.update_weights(semantic_weight, structural_weight)


# Convenience aliases for common operations
record = quick_decision
precedents = find_precedents
explain_decision = explain
similar = similar_to
batch = batch_decisions
filter = filter_decisions
context = get_decision_context
by_entities = search_by_entities
stats = get_decision_statistics
weights = update_similarity_weights
