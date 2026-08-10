"""
Vector Store Management Module

This module provides comprehensive vector storage and retrieval capabilities for the
Semantica framework, including support for multiple vector store backends (FAISS,
Weaviate, Qdrant, Pinecone, Milvus), hybrid search combining vector similarity and
metadata filtering, metadata management, and namespace isolation.

Algorithms Used:

Vector Storage Operations:
    - Vector Storage: ID generation (sequential or UUID-based), vector normalization (L2 normalization), batch storage (chunking algorithm), metadata association (vector-to-metadata mapping), vector validation (dimension checking, type validation)
    - Vector Indexing: Index construction (FAISS index types: Flat, IVF, HNSW, PQ), index training (k-means clustering for IVF, graph construction for HNSW), index optimization (index rebuilding, parameter tuning), incremental indexing (add vectors to existing index)
    - Vector Retrieval: Direct vector lookup by ID, batch retrieval, vector-to-metadata mapping
    - Vector Update: In-place vector update, index rebuilding after update, metadata update propagation
    - Vector Deletion: Vector removal, index rebuilding after deletion, metadata cleanup, orphaned metadata detection

Similarity Search Algorithms:
    - Cosine Similarity: Normalized dot product (dot(v1, v2) / (||v1|| * ||v2||)), similarity score calculation (0 to 1 range), top-k selection (argsort with descending order, slice top k)
    - L2 Distance: Euclidean distance calculation (sqrt(sum((v1 - v2)^2))), distance-to-similarity conversion (1 / (1 + distance)), top-k selection
    - Inner Product: Dot product calculation (dot(v1, v2)), unnormalized similarity, top-k selection
    - Approximate Nearest Neighbor (ANN): FAISS IVF (inverted file index with k-means clustering), FAISS HNSW (hierarchical navigable small world graph), FAISS PQ (product quantization for compression), approximate search with configurable accuracy/speed tradeoff
    - k-NN Search: Exact k-nearest neighbors (brute force with full distance calculation), approximate k-NN (using ANN indices), batch k-NN search

Index Construction:
    - FAISS Flat Index: Brute force exact search, no training required, O(n) search time, full vector storage
    - FAISS IVF Index: k-means clustering for cell assignment, inverted file structure, approximate search with configurable nprobe, training on sample vectors
    - FAISS HNSW Index: Hierarchical graph construction (multi-layer graph with connections), greedy search algorithm, approximate search with configurable ef_search, no training required
    - FAISS PQ Index: Product quantization (vector dimension splitting, codebook learning, vector compression), compressed storage, approximate search, training on sample vectors
    - Index Training: k-means clustering (for IVF), codebook learning (for PQ), parameter optimization, training data sampling
    - Index Optimization: Index rebuilding, parameter tuning (nlist for IVF, ef_construction for HNSW, m for PQ), memory optimization

Hybrid Search:
    - Vector Similarity + Metadata Filtering: Metadata filtering first (apply metadata filter conditions), then vector similarity search on filtered set, result combination
    - Result Fusion: Reciprocal Rank Fusion (RRF) algorithm (score = sum(1 / (k + rank)) for each result list, k typically 60), weighted average fusion (weighted sum of scores from multiple sources), result deduplication, top-k selection after fusion
    - Multi-Source Search: Search across multiple vector sources, result collection from each source, fusion using RRF or weighted average, unified result ranking
    - Ranking Strategies: RRF (reciprocal rank fusion with configurable k), weighted average (configurable weights per source), score normalization, result re-ranking

Metadata Management:
    - Metadata Indexing: Field-based indexing (inverted index per field), value-to-vector-ID mapping, list value handling (index each list item), fast lookup O(1) per field-value pair
    - Metadata Filtering: Equality filtering (eq operator), inequality filtering (ne, gt, gte, lt, lte operators), membership filtering (in operator for list values), contains filtering (string/list contains), AND/OR operator combination, condition chaining
    - Schema Management: Schema definition (field types, required fields, default values), schema validation (type checking, required field checking), schema enforcement, schema evolution
    - Metadata Querying: Field-value query (single condition), multi-field query (AND/OR operators), set intersection (AND) or union (OR) operations, result set construction

Namespace Management:
    - Namespace Isolation: Vector-to-namespace mapping (dictionary-based mapping), namespace-based vector organization, namespace-level access control, namespace metadata storage
    - Multi-Tenant Support: Tenant isolation via namespaces, per-namespace configuration, namespace-level statistics, namespace-level operations
    - Access Control: Permission-based access (read, write, delete permissions), entity-to-permission mapping (user/role to permissions), permission checking, access control enforcement
    - Namespace Operations: Namespace creation, namespace deletion, vector addition/removal, namespace metadata management, namespace statistics collection

Backend Pattern:
    - FAISS Store: Local vector storage, FAISS index management, index persistence (save/load), batch operations, multiple index types support
    - Weaviate Store: Schema-aware storage, GraphQL query support, object-oriented data model, batch operations, schema management
    - Qdrant Store: Point-based storage, payload filtering, collection management, optimized search, batch operations
    - Milvus Store: Scalable vector database, collection management, partitioning, complex querying, index building

Supported Backends:
    - FAISS: In-memory/local disk (Facebook AI Similarity Search)
    - Weaviate: Cloud/Self-hosted (Schema-aware vector database)
    - Qdrant: Cloud/Self-hosted (Vector database for the next generation of AI)
    - Pinecone: Cloud-managed (Managed vector database service)
    - Milvus: Cloud/Self-hosted (Highly scalable vector database)
    - InMemory: Simple list-based storage for testing/small datasets

Configuration:
    - Environment variables (SEMANTICA_VECTOR_STORE_*)
    - Configuration files (yaml/json)
    - Runtime configuration via VectorStoreConfig

Dependencies:
    - faiss-cpu (or faiss-gpu)
    - weaviate-client
    - qdrant-client
    - pymilvus

Key Features:
    - Multi-backend vector store support (FAISS, Weaviate, Qdrant, Pinecone, Milvus)
    - Vector indexing and similarity search
    - Metadata indexing and filtering
    - Hybrid search combining vector and metadata queries
    - Namespace isolation and multi-tenant support
    - Vector store management and optimization
    - Batch operations and performance optimization
    - Method registry for extensibility
    - Configuration management with environment variables and config files
    - Enhanced decision tracking with hybrid similarity search
    - Integration with KG algorithms for structural embeddings
    - Advanced context expansion using path finding, community detection, and centrality

Main Classes:
    - VectorStore: Main vector store interface
    - VectorIndexer: Vector indexing engine
    - VectorRetriever: Vector retrieval and similarity search
    - VectorManager: Vector store management and operations
    - FAISSStore: FAISS integration for local vector storage
    - WeaviateStore: Weaviate vector database integration
    - QdrantStore: Qdrant vector database integration
    - PineconeStore: Pinecone vector database integration
    - MilvusStore: Milvus vector database integration
    - HybridSearch: Hybrid vector and metadata search
    - MetadataStore: Metadata indexing and management
    - NamespaceManager: Namespace isolation and management

Convenience Functions:
    - store_vectors: Store vectors wrapper
    - search_vectors: Search vectors wrapper
    - update_vectors: Update vectors wrapper
    - delete_vectors: Delete vectors wrapper
    - create_index: Create index wrapper
    - hybrid_search: Hybrid search wrapper
    - filter_metadata: Metadata filtering wrapper
    - manage_namespace: Namespace management wrapper
    - get_vector_store_method: Get vector store method by task and name
    - list_available_methods: List registered vector store methods

Example Usage:
    >>> from semantica.vector_store import VectorStore, store_vectors, search_vectors, hybrid_search
    >>> # Using convenience functions
    >>> vector_ids = store_vectors(vectors, metadata=metadata_list, method="default")
    >>> results = search_vectors(query_vector, k=10, method="default")
    >>> hybrid_results = hybrid_search(query_vector, vectors, metadata, vector_ids, filter=filter, method="default")
    >>> # Using classes directly
    >>> store = VectorStore(backend="faiss", dimension=768)
    >>> vector_ids = store.store_vectors(vectors, metadata=metadata_list)
    >>> results = store.search_vectors(query_vector, k=10)
    >>> from semantica.vector_store import HybridSearch, MetadataFilter
    >>> search = HybridSearch()
    >>> filter = MetadataFilter().eq("category", "science")
    >>> results = search.search(query_vector, vectors, metadata, vector_ids, filter=filter)

Author: Semantica Contributors
License: MIT
"""

from .config import VectorStoreConfig, vector_store_config
from .faiss_store import FAISSStore, FAISSIndex, FAISSIndexBuilder, FAISSSearch
from .hybrid_search import HybridSearch, MetadataFilter, SearchRanker
from .hybrid_similarity import HybridSimilarityCalculator
from .decision_embedding_pipeline import DecisionEmbeddingPipeline
from .decision_vector_methods import (
    quick_decision,
    find_precedents,
    explain,
    similar_to,
    batch_decisions,
    filter_decisions,
    get_decision_context,
    search_by_entities,
    get_decision_statistics,
    update_similarity_weights,
    set_global_vector_store,
    get_global_vector_store,
    # Aliases
    record,
    precedents,
    explain_decision,
    similar,
    batch,
    filter,
    context,
    by_entities,
    stats,
    weights,
)
from .metadata_store import MetadataIndex, MetadataSchema, MetadataStore
from .methods import (
    create_index,
    delete_vectors,
    filter_metadata,
    get_vector_store_method,
    hybrid_search,
    list_available_methods,
    manage_namespace,
    search_vectors,
    store_vectors,
    update_vectors,
)
from .milvus_store import MilvusStore, MilvusClient, MilvusCollection, MilvusSearch
from .namespace_manager import Namespace, NamespaceManager
from .pgvector_store import PgVectorStore
from .pinecone_store import PineconeStore, PineconeClient, PineconeIndex, PineconeSearch
from .qdrant_store import QdrantStore, QdrantClient, QdrantCollection, QdrantSearch
from .registry import MethodRegistry, method_registry
from .sqlite_vec_store import SQLiteVecStore
from .vector_store import VectorIndexer, VectorManager, VectorRetriever, VectorStore, SearchResult
from .weaviate_store import (
    WeaviateStore,
    WeaviateClient,
    WeaviateQuery,
    WeaviateSchema,
)

__all__ = [
    # Core vector store
    "VectorStore",
    "VectorIndexer",
    "VectorRetriever",
    "VectorManager",
    "SearchResult",
    # FAISS
    "FAISSStore",
    "FAISSIndex",
    "FAISSSearch",
    "FAISSIndexBuilder",
    # Weaviate
    "WeaviateStore",
    "WeaviateClient",
    "WeaviateSchema",
    "WeaviateQuery",
    # Qdrant
    "QdrantStore",
    "QdrantClient",
    "QdrantCollection",
    "QdrantSearch",
    # Milvus
    "MilvusStore",
    "MilvusClient",
    "MilvusCollection",
    "MilvusSearch",
    # Pinecone
    "PineconeStore",
    "PineconeClient",
    "PineconeIndex",
    "PineconeSearch",
    # PgVector
    "PgVectorStore",
    # SQLite
    "SQLiteVecStore",
    # Hybrid search
    "HybridSearch",
    "MetadataFilter",
    "SearchRanker",
    # Enhanced decision features
    "HybridSimilarityCalculator",
    "DecisionEmbeddingPipeline",
    # Decision convenience functions
    "quick_decision",
    "find_precedents",
    "explain",
    "similar_to",
    "batch_decisions",
    "filter_decisions",
    "get_decision_context",
    "search_by_entities",
    "get_decision_statistics",
    "update_similarity_weights",
    "set_global_vector_store",
    "get_global_vector_store",
    # Aliases for convenience
    "record",
    "precedents",
    "explain_decision",
    "similar",
    "batch",
    "filter",
    "context",
    "by_entities",
    "stats",
    "weights",
    # Metadata store
    "MetadataStore",
    "MetadataIndex",
    "MetadataSchema",
    # Namespace manager
    "NamespaceManager",
    "Namespace",
    # Convenience functions
    "store_vectors",
    "search_vectors",
    "update_vectors",
    "delete_vectors",
    "create_index",
    "hybrid_search",
    "filter_metadata",
    "manage_namespace",
    "get_vector_store_method",
    "list_available_methods",
    # Configuration and registry
    "VectorStoreConfig",
    "vector_store_config",
    "MethodRegistry",
    "method_registry",
]
