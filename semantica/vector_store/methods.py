"""
Vector Store Methods Module

This module provides all vector store methods as simple, reusable functions for
storing vectors, searching, indexing, hybrid search, metadata management, and
namespace management. It supports multiple approaches and integrates with the
method registry for extensibility.

Supported Methods:

Vector Storage:
    - "default": Default vector storage using VectorStore
    - "batch": Batch vector storage
    - "normalized": Normalized vector storage

Vector Search:
    - "default": Default vector search
    - "cosine": Cosine similarity search
    - "l2": L2 distance search
    - "inner_product": Inner product search

Index Creation:
    - "default": Default index creation
    - "faiss_flat": FAISS flat index
    - "faiss_ivf": FAISS IVF index
    - "faiss_hnsw": FAISS HNSW index
    - "faiss_pq": FAISS product quantization index

Hybrid Search:
    - "default": Default hybrid search
    - "rrf": Reciprocal rank fusion
    - "weighted": Weighted average fusion

Metadata Management:
    - "default": Default metadata management
    - "indexed": Indexed metadata management
    - "filtered": Filtered metadata management

Namespace Management:
    - "default": Default namespace management
    - "isolated": Isolated namespace management

Algorithms Used:

Vector Storage:
    - ID Generation: Sequential or UUID-based ID generation
    - Vector Normalization: L2 normalization for cosine similarity
    - Batch Processing: Chunking algorithm for large datasets
    - Metadata Association: Vector-to-metadata mapping

Vector Search:
    - Cosine Similarity: Normalized dot product calculation
    - L2 Distance: Euclidean distance calculation
    - Inner Product: Dot product calculation
    - Top-k Selection: Argsort with descending order

Index Creation:
    - FAISS Index Types: Flat, IVF, HNSW, PQ index construction
    - Index Training: k-means clustering, codebook learning
    - Index Optimization: Parameter tuning, index rebuilding

Hybrid Search:
    - Result Fusion: RRF algorithm, weighted average fusion
    - Metadata Filtering: Field-based filtering with operators
    - Multi-Source Search: Cross-source result fusion

Key Features:
    - Multiple vector store operation methods
    - Vector storage with method dispatch
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - store_vectors: Vector storage wrapper
    - search_vectors: Vector search wrapper
    - update_vectors: Vector update wrapper
    - delete_vectors: Vector deletion wrapper
    - create_index: Index creation wrapper
    - hybrid_search: Hybrid search wrapper
    - filter_metadata: Metadata filtering wrapper
    - manage_namespace: Namespace management wrapper
    - get_vector_store_method: Get vector store method by task and name
    - list_available_methods: List registered methods

Example Usage:
    >>> from semantica.vector_store.methods import store_vectors, search_vectors, hybrid_search
    >>> vector_ids = store_vectors(vectors, metadata=metadata_list, method="default")
    >>> results = search_vectors(query_vector, vectors, vector_ids, k=10, method="default")
    >>> hybrid_results = hybrid_search(query_vector, vectors, metadata, vector_ids, filter=filter, method="default")
"""

from typing import Any, Dict, List, Optional, Union

import numpy as np

from .config import vector_store_config
from .hybrid_search import HybridSearch, MetadataFilter, SearchRanker
from .metadata_store import MetadataIndex, MetadataSchema, MetadataStore
from .namespace_manager import Namespace, NamespaceManager
from .registry import method_registry
from .vector_store import VectorIndexer, VectorManager, VectorRetriever, VectorStore

# Global manager instances
_global_store: Optional[VectorStore] = None
_global_hybrid_search: Optional[HybridSearch] = None
_global_metadata_store: Optional[MetadataStore] = None
_global_namespace_manager: Optional[NamespaceManager] = None


def _get_store() -> VectorStore:
    """Get or create global VectorStore instance."""
    global _global_store
    if _global_store is None:
        config = vector_store_config.get_all()
        backend = config.get("default_backend", "faiss")
        dimension = config.get("dimension", 768)
        _global_store = VectorStore(backend=backend, config=config, dimension=dimension)
    return _global_store


def _get_hybrid_search() -> HybridSearch:
    """Get or create global HybridSearch instance."""
    global _global_hybrid_search
    if _global_hybrid_search is None:
        config = vector_store_config.get_all()
        _global_hybrid_search = HybridSearch(**config)
    return _global_hybrid_search


def _get_metadata_store() -> MetadataStore:
    """Get or create global MetadataStore instance."""
    global _global_metadata_store
    if _global_metadata_store is None:
        config = vector_store_config.get_all()
        _global_metadata_store = MetadataStore(**config)
    return _global_metadata_store


def _get_namespace_manager() -> NamespaceManager:
    """Get or create global NamespaceManager instance."""
    global _global_namespace_manager
    if _global_namespace_manager is None:
        config = vector_store_config.get_all()
        _global_namespace_manager = NamespaceManager(**config)
    return _global_namespace_manager


def store_vectors(
    vectors: List[np.ndarray],
    metadata: Optional[List[Dict[str, Any]]] = None,
    method: str = "default",
    **options,
) -> List[str]:
    """
    Store vectors in vector store.

    Args:
        vectors: List of vector arrays
        metadata: List of metadata dictionaries
        method: Storage method name (default: "default")
        **options: Additional options

    Returns:
        List of vector IDs
    """
    # Check registry for custom method
    custom_method = method_registry.get("store", method)
    if custom_method:
        return custom_method(vectors, metadata=metadata, **options)

    # Default implementation
    store = _get_store()
    return store.store_vectors(vectors, metadata=metadata, **options)


def search_vectors(
    query_vector: np.ndarray,
    vectors: Optional[List[np.ndarray]] = None,
    vector_ids: Optional[List[str]] = None,
    k: int = 10,
    method: str = "default",
    **options,
) -> List[Dict[str, Any]]:
    """
    Search for similar vectors.

    Args:
        query_vector: Query vector
        vectors: Optional list of vectors to search (uses store vectors if not provided)
        vector_ids: Optional list of vector IDs
        k: Number of results to return
        method: Search method name (default: "default")
        **options: Additional options

    Returns:
        List of search results with scores
    """
    # Check registry for custom method
    custom_method = method_registry.get("search", method)
    if custom_method:
        return custom_method(
            query_vector, vectors=vectors, vector_ids=vector_ids, k=k, **options
        )

    # Default implementation
    store = _get_store()
    if vectors is None:
        # Use store's vectors
        return store.search_vectors(query_vector, k=k, **options)
    else:
        # Use provided vectors
        retriever = VectorRetriever(backend=store.backend, **store.config)
        return retriever.search_similar(
            query_vector,
            vectors,
            vector_ids or list(range(len(vectors))),
            k=k,
            **options,
        )


def update_vectors(
    vector_ids: List[str],
    new_vectors: List[np.ndarray],
    method: str = "default",
    **options,
) -> bool:
    """
    Update existing vectors.

    Args:
        vector_ids: List of vector IDs to update
        new_vectors: List of new vectors
        method: Update method name (default: "default")
        **options: Additional options

    Returns:
        True if successful
    """
    # Check registry for custom method
    custom_method = method_registry.get("store", method)
    if custom_method:
        return custom_method(vector_ids, new_vectors, **options)

    # Default implementation
    store = _get_store()
    return store.update_vectors(vector_ids, new_vectors, **options)


def delete_vectors(vector_ids: List[str], method: str = "default", **options) -> bool:
    """
    Delete vectors from store.

    Args:
        vector_ids: List of vector IDs to delete
        method: Deletion method name (default: "default")
        **options: Additional options

    Returns:
        True if successful
    """
    # Check registry for custom method
    custom_method = method_registry.get("store", method)
    if custom_method:
        return custom_method(vector_ids, **options)

    # Default implementation
    store = _get_store()
    return store.delete_vectors(vector_ids, **options)


def create_index(
    vectors: List[np.ndarray],
    ids: Optional[List[str]] = None,
    method: str = "default",
    **options,
) -> Any:
    """
    Create vector index.

    Args:
        vectors: List of vectors
        ids: Vector IDs
        method: Index creation method name (default: "default")
        **options: Additional options

    Returns:
        Index object
    """
    # Check registry for custom method
    custom_method = method_registry.get("index", method)
    if custom_method:
        return custom_method(vectors, ids=ids, **options)

    # Default implementation
    config = vector_store_config.get_all()
    backend = config.get("default_backend", "faiss")
    dimension = config.get("dimension", 768)
    # backend/dimension are already passed explicitly; drop them from the
    # forwarded config so VectorIndexer(..., **remaining_config) doesn't
    # receive duplicate keyword arguments.
    remaining_config = {k: v for k, v in config.items() if k not in ("default_backend", "dimension")}
    indexer = VectorIndexer(backend=backend, dimension=dimension, **remaining_config)
    return indexer.create_index(vectors, ids, **options)


def hybrid_search(
    query_vector: np.ndarray,
    vectors: List[np.ndarray],
    metadata: List[Dict[str, Any]],
    vector_ids: List[str],
    k: int = 10,
    metadata_filter: Optional[MetadataFilter] = None,
    method: str = "default",
    **options,
) -> List[Dict[str, Any]]:
    """
    Perform hybrid search combining vector similarity and metadata filtering.

    Args:
        query_vector: Query vector
        vectors: List of vectors to search
        metadata: List of metadata dictionaries
        vector_ids: Vector IDs
        k: Number of results
        metadata_filter: Optional metadata filter
        method: Hybrid search method name (default: "default")
        **options: Additional options

    Returns:
        List of search results
    """
    # Check registry for custom method
    custom_method = method_registry.get("hybrid_search", method)
    if custom_method:
        return custom_method(
            query_vector,
            vectors,
            metadata,
            vector_ids,
            k=k,
            metadata_filter=metadata_filter,
            **options,
        )

    # Default implementation
    search = _get_hybrid_search()
    return search.search(
        query_vector,
        vectors,
        metadata,
        vector_ids,
        k=k,
        metadata_filter=metadata_filter,
        **options,
    )


def filter_metadata(
    metadata: List[Dict[str, Any]],
    filter_conditions: Dict[str, Any],
    operator: str = "AND",
    method: str = "default",
    **options,
) -> List[Dict[str, Any]]:
    """
    Filter metadata by conditions.

    Args:
        metadata: List of metadata dictionaries
        filter_conditions: Filter conditions dictionary
        operator: "AND" or "OR" operator
        method: Filtering method name (default: "default")
        **options: Additional options

    Returns:
        Filtered metadata list
    """
    # Check registry for custom method
    custom_method = method_registry.get("metadata", method)
    if custom_method:
        return custom_method(metadata, filter_conditions, operator=operator, **options)

    # Default implementation
    metadata_store = _get_metadata_store()
    # Create filter from conditions
    metadata_filter = MetadataFilter()
    for field, value in filter_conditions.items():
        metadata_filter.eq(field, value)

    # Filter metadata
    filtered = []
    for meta in metadata:
        if metadata_filter.matches(meta):
            filtered.append(meta)

    return filtered


def manage_namespace(namespace_name: str, operation: str, **options) -> Any:
    """
    Manage namespace operations.

    Args:
        namespace_name: Namespace name
        operation: Operation type ("create", "delete", "add_vector", "remove_vector", "get_vectors")
        **options: Additional options

    Returns:
        Operation result
    """
    # Check registry for custom method
    custom_method = method_registry.get("namespace", operation)
    if custom_method:
        return custom_method(namespace_name, **options)

    # Default implementation
    manager = _get_namespace_manager()

    if operation == "create":
        return manager.create_namespace(namespace_name, **options)
    elif operation == "delete":
        return manager.delete_namespace(namespace_name, **options)
    elif operation == "add_vector":
        vector_id = options.get("vector_id")
        return manager.add_vector_to_namespace(vector_id, namespace_name, **options)
    elif operation == "remove_vector":
        vector_id = options.get("vector_id")
        return manager.remove_vector_from_namespace(
            vector_id, namespace_name, **options
        )
    elif operation == "get_vectors":
        return manager.get_namespace_vectors(namespace_name, **options)
    else:
        raise ValueError(f"Unknown operation: {operation}")


def get_vector_store_method(task: str, method_name: str) -> Optional[Any]:
    """
    Get vector store method by task and name.

    Args:
        task: Task type (store, search, index, hybrid_search, metadata, namespace)
        method_name: Method name

    Returns:
        Method function or None if not found
    """
    return method_registry.get(task, method_name)


def list_available_methods(task: Optional[str] = None) -> Dict[str, List[str]]:
    """
    List all available vector store methods.

    Args:
        task: Optional task type to filter by

    Returns:
        Dictionary mapping task types to lists of method names
    """
    return method_registry.list_all(task)
