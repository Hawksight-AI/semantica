"""
Vector Store Module

This module provides comprehensive vector storage and retrieval capabilities with
support for multiple backends, decision tracking, and hybrid search functionality.

Key Features:
    - Multi-backend vector store support (FAISS, Weaviate, Qdrant, Pinecone, Milvus)
    - Vector indexing and similarity search
    - Metadata indexing and filtering
    - Hybrid search combining vector and metadata queries
    - Decision tracking with hybrid precedent search
    - Namespace isolation and multi-tenant support
    - Vector store management and optimization
    - Batch operations and performance optimization
    - Method registry for extensibility
    - Configuration management with environment variables and config files
    - Enhanced decision tracking with hybrid similarity search
    - Integration with KG algorithms for structural embeddings
    - Advanced context expansion using path finding, community detection, and centrality

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
    - Vector Indexing: FAISS, Qdrant, Weaviate, Pinecone, Milvus indexing
    - Metadata Filtering: Exact match, range, and list-based filtering
    - Batch Processing: Efficient batch operations for multiple vectors

Main Classes:
    - VectorStore: Main vector store interface with decision tracking
    - VectorIndexer: Vector indexing engine
    - VectorRetriever: Vector retrieval and similarity search
    - VectorManager: Vector store management and operations
    - FAISSStore: FAISS integration for local vector storage
    - WeaviateStore: Weaviate vector database integration
    - QdrantStore: Qdrant vector database integration
    - PineconeStore: Pinecone vector database integration
    - MilvusStore: Milvus vector database integration

Example Usage:
    >>> from semantica.vector_store import VectorStore
    >>> store = VectorStore(backend="faiss", dimension=384)
    >>> store.store_vectors([[0.1, 0.2, 0.3]], [{"type": "document"}])
    >>> results = store.search_vectors([0.1, 0.2, 0.3], k=5)
    >>> decision_id = store.store_decision("Credit approval", "approved")
    >>> precedents = store.search_decisions("Credit approval", limit=10)
    >>> store.update_vectors(vector_ids, new_vectors)
    >>> store.delete_vectors(vector_ids)
    >>> 
    >>> from semantica.vector_store import VectorIndexer, VectorRetriever
    >>> indexer = VectorIndexer(backend="faiss", dimension=768)
    >>> index = indexer.create_index(vectors, ids)
    >>> retriever = VectorRetriever(backend="faiss")
    >>> results = retriever.search_similar(query_vector, vectors, ids, k=10)

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union, cast
import concurrent.futures
import inspect

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from ..embeddings import EmbeddingGenerator
from .hybrid_similarity import HybridSimilarityCalculator
from .decision_embedding_pipeline import DecisionEmbeddingPipeline

class SearchResult(TypedDict):
    """Canonical schema returned by VectorStore.search_vectors().

    Required fields (always present):
        id       – string or integer identifier of the stored vector.
        score    – float similarity score, higher is better (normalised to 0.0–1.0 across all backends).
        metadata – dict of associated metadata; empty dict when none is stored.
        vector   – np.ndarray when the backend returns the raw vector, otherwise None.
        distance – raw native distance value preserved for backends that expose it
                   (FAISS L2, Weaviate cosine), otherwise None.
    """

    id: Union[str, int]
    score: float
    metadata: Dict[str, Any]
    vector: Optional[Any]          # np.ndarray | None
    distance: Optional[float]


class VectorStore:
    """
    Vector store interface and management.

    • Stores and manages vector embeddings
    • Provides similarity search capabilities
    • Handles vector indexing and retrieval
    • Manages vector metadata and provenance
    • Supports multiple vector store backends
    • Provides vector store operations
    """

    SUPPORTED_BACKENDS = {"faiss", "weaviate", "qdrant", "milvus", "pinecone", "pgvector", "inmemory", "sqlite"}

    def __init__(self, backend="faiss", config=None, max_workers: int = 6, **kwargs):
        """Initialize vector store."""
        if backend.lower() not in self.SUPPORTED_BACKENDS:
            raise ValueError(
                f"Unsupported backend: {backend}. "
                f"Supported backends are: {', '.join(sorted(self.SUPPORTED_BACKENDS))}"
            )

        self.logger = get_logger("vector_store")
        self.config = config or {}
        self.config.update(kwargs)
        self.max_workers = max_workers
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.backend = backend.lower()
        self.dimension = self.config.get("dimension", 768)

        # Initialize backend-specific store if not using generic in-memory implementation
        self._backend_store: Any = None
        self.embedder = None  # Always initialized; may be overridden in _init_backend_store
        if self.backend != "inmemory":
            self._init_backend_store()

        # For in-memory backend, initialize local storage
        if self.backend == "inmemory":
            self.vectors: Dict[str, np.ndarray] = {}
            self.metadata: Dict[str, Dict[str, Any]] = {}

            # Initialize backend-specific indexer
            # Avoid duplicate dimension argument
            indexer_config = self.config.copy()
            if "dimension" in indexer_config:
                del indexer_config["dimension"]

            self.indexer = VectorIndexer(
                backend=backend, dimension=self.dimension, **indexer_config
            )
            self.retriever = VectorRetriever(backend=backend, **self.config)

            # Initialize embedding and decision components for inmemory backend
            try:
                self.embedder = EmbeddingGenerator()
            except Exception as e:
                self.logger.warning(f"Could not initialize embedding generator: {e}")
                self.embedder = None
            self.hybrid_calculator = HybridSimilarityCalculator()
            self.decision_pipeline: Optional[DecisionEmbeddingPipeline] = None

    def _init_backend_store(self):
        """Initialize backend-specific store instance."""
        try:
            if self.backend == "pgvector":
                # Import PgVectorStore
                from .pgvector_store import PgVectorStore
                
                # Required parameters for PgVectorStore
                connection_string = self.config.get("connection_string")
                table_name = self.config.get("table_name", "vectors")
                dimension = self.config.get("dimension", 768)
                distance_metric = self.config.get("distance_metric", "cosine")
                
                if not connection_string:
                    raise ValueError(
                        "pgvector backend requires 'connection_string' in config. "
                        "Example: VectorStore(backend='pgvector', config={"
                        "'connection_string': 'postgresql://user:pass@localhost/db'})"
                    )
                
                # Initialize PgVectorStore
                self._backend_store = PgVectorStore(
                    connection_string=connection_string,
                    table_name=table_name,
                    dimension=dimension,
                    distance_metric=distance_metric,
                    **{k: v for k, v in self.config.items() 
                       if k not in ['connection_string', 'table_name', 'dimension', 'distance_metric']}
                )
                self.logger.info(f"Initialized PgVectorStore backend")
                
            elif self.backend == "faiss":
                from .faiss_store import FAISSStore
                self._backend_store = FAISSStore(
                    dimension=self.config.get("dimension", 768),
                    **{k: v for k, v in self.config.items() if k != 'dimension'}
                )
                self.logger.info(f"Initialized FAISSStore backend")
                
            elif self.backend == "weaviate":
                from .weaviate_store import WeaviateStore
                self._backend_store = WeaviateStore(
                    **self.config
                )
                self.logger.info(f"Initialized WeaviateStore backend")
                
            elif self.backend == "qdrant":
                from .qdrant_store import QdrantStore
                self._backend_store = QdrantStore(
                    **self.config
                )
                self.logger.info(f"Initialized QdrantStore backend")
                
            elif self.backend == "pinecone":
                from .pinecone_store import PineconeStore
                self._backend_store = PineconeStore(
                    **self.config
                )
                self.logger.info(f"Initialized PineconeStore backend")
                
            elif self.backend == "milvus":
                from .milvus_store import MilvusStore
                self._backend_store = MilvusStore(
                    **self.config
                )
                self.logger.info(f"Initialized MilvusStore backend")
                
            elif self.backend == "sqlite":
                from .sqlite_vec_store import SQLiteVecStore
                db_path = self.config.get("db_path") or self.config.get("sqlite_path")
                if not db_path:
                    raise ValueError(
                        "sqlite backend requires 'db_path' in config. "
                        "Example: VectorStore(backend='sqlite', config={'db_path': 'vectors.db'})"
                    )
                
                table_name = self.config.get("table_name", "vectors")
                dimension = self.config.get("dimension", 768)
                distance_metric = self.config.get("distance_metric", "cosine")
                read_only = self.config.get("read_only", False)
                
                self._backend_store = SQLiteVecStore(
                    db_path=db_path,
                    table_name=table_name,
                    dimension=dimension,
                    distance_metric=distance_metric,
                    read_only=read_only,
                    **{k: v for k, v in self.config.items() 
                       if k not in ['db_path', 'sqlite_path', 'table_name', 'dimension', 'distance_metric', 'read_only']}
                )
                self.logger.info(f"Initialized SQLite backend")
                
            else:
                # Fallback to in-memory for unknown backends
                self.logger.warning(f"Backend '{self.backend}' not implemented, using in-memory")
                self.backend = "inmemory"
                
        except ImportError as e:
            raise ImportError(f"Backend '{self.backend}' not available: {e}. Please install required dependencies.") from e
        except Exception as e:
            if "requires" in str(e) and ("connection_string" in str(e) or "db_path" in str(e)):
                # Re-raise validation errors for missing required parameters
                raise
            else:
                raise RuntimeError(f"Failed to initialize backend '{self.backend}': {e}") from e

        # Initialize embedding generator
        try:
            self.embedder = EmbeddingGenerator()
            # Set default model if not configured, or respect global config
            # For now, we try to ensure a model is loaded if possible
            if hasattr(self.embedder, "set_text_model"):
                # Use a lightweight default if none specified, or let EmbeddingGenerator handle defaults
                pass
        except Exception as e:
            self.logger.warning(f"Could not initialize embedding generator: {e}")
            self.embedder = None

        # Initialize decision-specific components
        self.hybrid_calculator = HybridSimilarityCalculator()
        self.decision_pipeline: Optional[DecisionEmbeddingPipeline] = None

    def embed(self, text: str) -> np.ndarray:
        """
        Generate embedding for text using the internal embedder.
        
        Args:
            text: Text to embed
            
        Returns:
            Numpy array of embedding
        """
        if self.embedder:
            try:
                return self.embedder.generate_embeddings(text)
            except Exception as e:
                self.logger.warning(f"Embedding generation failed: {e}")
        
        # Fallback or raise? AgentMemory expects None or valid embedding.
        # Returning random vector as fallback for now (matches DemoVectorStore behavior)
        # to prevent crashes, but logging warning.
        self.logger.warning("Using random fallback embedding")
        return np.random.rand(self.dimension).astype(np.float32)

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for a list of texts using the internal embedder.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of numpy arrays
        """
        if self.embedder:
            try:
                # generate_embeddings handles list input
                embeddings = self.embedder.generate_embeddings(texts)
                # Ensure it returns a list of arrays (it returns 2D array or list)
                if isinstance(embeddings, np.ndarray):
                    return list(embeddings)
                return embeddings
            except Exception as e:
                self.logger.warning(f"Batch embedding generation failed: {e}")
        
        # Fallback
        self.logger.warning("Using random fallback embeddings for batch")
        return [np.random.rand(self.dimension).astype(np.float32) for _ in texts]

    def add_documents(
        self,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        batch_size: int = 32,
        parallel: bool = True,
        **options,
    ) -> List[str]:
        """
        Add multiple documents to the store with parallel embedding generation.
        
        Args:
            documents: List of document texts
            metadata: List of metadata dictionaries
            batch_size: Number of documents to process in one batch
            parallel: Whether to use parallel processing for embeddings
            **options: Additional options
            
        Returns:
            List[str]: Vector IDs
        """
        if not documents:
            return []
            
        num_docs = len(documents)
        metadata = metadata or [{} for _ in range(num_docs)]
        
        if len(metadata) != num_docs:
            raise ValueError("Metadata list length must match documents length")
            
        all_vectors = [None] * num_docs
        
        # Helper for processing a batch
        def process_batch(start_idx: int, end_idx: int):
            batch_texts = documents[start_idx:end_idx]
            batch_embeddings = self.embed_batch(batch_texts)
            return start_idx, batch_embeddings

        # Calculate batches
        batches = []
        for i in range(0, num_docs, batch_size):
            batches.append((i, min(i + batch_size, num_docs)))
            
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="VectorStore",
            message=f"Processing {num_docs} documents (parallel={parallel})",
        )

        try:
            if parallel and self.max_workers > 1:
                self.progress_tracker.update_tracking(
                    tracking_id, message=f"Embedding with {self.max_workers} workers..."
                )
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = [
                        executor.submit(process_batch, start, end)
                        for start, end in batches
                    ]
                    
                    completed = 0
                    for future in concurrent.futures.as_completed(futures):
                        start_idx, embeddings = future.result()
                        # Place results in correct order
                        for i, emb in enumerate(embeddings):
                            all_vectors[start_idx + i] = emb
                        
                        completed += 1
                        if completed % 5 == 0:  # Update progress periodically
                            self.progress_tracker.update_tracking(
                                tracking_id, 
                                message=f"Embedded batch {completed}/{len(batches)}"
                            )
            else:
                # Sequential processing
                self.progress_tracker.update_tracking(
                    tracking_id, message="Embedding sequentially..."
                )
                for i, (start, end) in enumerate(batches):
                    _, embeddings = process_batch(start, end)
                    for j, emb in enumerate(embeddings):
                        all_vectors[start + j] = emb
                    
                    if i % 5 == 0:
                        self.progress_tracker.update_tracking(
                            tracking_id, 
                            message=f"Embedded batch {i+1}/{len(batches)}"
                        )
                        
            # Verify all embeddings generated
            if any(v is None for v in all_vectors):
                raise ProcessingError("Failed to generate all embeddings")
                
            # Store all vectors in one go
            self.progress_tracker.update_tracking(tracking_id, message="Storing vectors...")
            vector_ids = self.store_vectors(all_vectors, metadata=metadata, **options)
            
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Added {len(vector_ids)} documents",
            )
            return vector_ids
            
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def store(
        self,
        vectors: List[np.ndarray],
        documents: Optional[List[Any]] = None,
        metadata: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        **options,
    ) -> List[str]:
        """
        Convenience method to store vectors with documents/metadata.

        Args:
            vectors: List of embeddings
            documents: Optional list of source documents
            metadata: Optional metadata (dict for all, or list for each)
            **options: Additional options

        Returns:
            List[str]: Vector IDs
        """
        # Prepare metadata list
        num_vectors = len(vectors)
        final_metadata = []

        if isinstance(metadata, list):
            if len(metadata) != num_vectors:
                raise ValueError("Metadata list length must match vectors length")
            final_metadata = metadata
        elif isinstance(metadata, dict):
            # Apply same metadata to all, copy to avoid shared reference issues
            final_metadata = [metadata.copy() for _ in range(num_vectors)]
        else:
            final_metadata = [{} for _ in range(num_vectors)]

        # Merge document metadata if available
        if documents and len(documents) == num_vectors:
            for i, doc in enumerate(documents):
                doc_meta = {}
                if hasattr(doc, "metadata"):
                    doc_meta = doc.metadata
                elif isinstance(doc, dict):
                    doc_meta = doc.get("metadata", {})
                
                final_metadata[i].update(doc_meta)
        
        return self.store_vectors(vectors, metadata=final_metadata, **options)

    def store_vectors(
        self,
        vectors: List[np.ndarray],
        metadata: Optional[List[Dict[str, Any]]] = None,
        **options,
    ) -> List[str]:
        """
        Store vectors in vector store.

        Args:
            vectors: List of vector arrays
            metadata: List of metadata dictionaries
            **options: Storage options

        Returns:
            List of vector IDs
        """
        # Delegate to backend store if available
        if self._backend_store:
            # Handle different method names across backend stores
            if hasattr(self._backend_store, 'add'):
                return self._backend_store.add(vectors, metadata, **options)
            elif hasattr(self._backend_store, 'add_vectors'):
                # FAISSStore and others use add_vectors with different signature
                if hasattr(self._backend_store, 'store_vectors'):
                    # Some stores have store_vectors method
                    return self._backend_store.store_vectors(vectors, metadata=metadata, **options)
                else:
                    try:
                        add_vectors_params = inspect.signature(self._backend_store.add_vectors).parameters
                        supports_metadata = 'metadata' in add_vectors_params or any(
                            p.kind == inspect.Parameter.VAR_KEYWORD for p in add_vectors_params.values()
                        )
                    except (ValueError, TypeError):
                        supports_metadata = True
                    if supports_metadata:
                        return self._backend_store.add_vectors(vectors, metadata=metadata, **options)
                    return self._backend_store.add_vectors(vectors, **options)
            else:
                raise NotImplementedError(f"Backend store {type(self._backend_store).__name__} does not have add or add_vectors method")
        
        # Use in-memory implementation
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="VectorStore",
            message=f"Storing {len(vectors)} vectors",
        )

        try:
            vector_ids = []
            metadata = metadata or [{}] * len(vectors)

            self.progress_tracker.update_tracking(
                tracking_id, message="Storing vectors..."
            )
            start_idx = len(self.vectors)
            for i, (vector, meta) in enumerate(zip(vectors, metadata)):
                vector_id = f"vec_{start_idx + i}"
                self.vectors[vector_id] = vector
                self.metadata[vector_id] = meta
                vector_ids.append(vector_id)

            # Update index
            self.progress_tracker.update_tracking(
                tracking_id, message="Updating vector index..."
            )
            self.indexer.create_index(list(self.vectors.values()), vector_ids)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Stored {len(vector_ids)} vectors",
            )
            return vector_ids
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise
    def save(self, path: str) -> None:
        """
        Save vector store to disk.
        
        Args:
            path: Directory path to save to
        """
        import json
        import os
        
        os.makedirs(path, exist_ok=True)

        # Save metadata and vectors (generic fallback)
        # Ideally, backends like FAISS have their own save methods
        indexer = getattr(self, "indexer", None)
        if indexer is not None and hasattr(indexer, "save_index"):
            indexer.save_index(os.path.join(path, "index.bin"))
        elif self._backend_store is not None and hasattr(self._backend_store, "save_index"):
            self._backend_store.save_index(os.path.join(path, "index.bin"))

        # Save Python-level data using JSON (safe serialization).
        # pickle is intentionally avoided to prevent arbitrary code execution
        # if a malicious .pkl file is placed in the store directory.
        data = {
            "vectors": {k: v.tolist() if hasattr(v, "tolist") else list(v)
                    for k, v in getattr(self, "vectors", {}).items()},
            "metadata": getattr(self, "metadata", {}),
            "config": self.config,
            "backend": self.backend,
            "dimension": self.dimension
        }
        
        with open(os.path.join(path, "store_data.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
            
        self.logger.info(f"Saved vector store to {path}")

    def load(self, path: str) -> None:
        """
        Load vector store from disk.
        
        Args:
            path: Directory path to load from
            
        Raises:
            RuntimeError: If only a legacy pickle file is found (security risk).
        """
        import json
        import os
        
        json_path = os.path.join(path, "store_data.json")
        legacy_pkl_path = os.path.join(path, "store_data.pkl")
        
        if os.path.exists(json_path):
            data_path = json_path
        elif os.path.exists(legacy_pkl_path):
            # Refuse to load pickle files to prevent arbitrary code execution.
            # A crafted .pkl file can execute arbitrary Python when deserialized.
            raise RuntimeError(
                f"Legacy pickle file found at {legacy_pkl_path}. "
                "Pickle deserialization is disabled for security (arbitrary code "
                "execution risk). Please re-save the vector store to migrate "
                "to the safe JSON format: vs.save(path)"
            )
        else:
            self.logger.warning(f"Store data not found in: {path}")
            return
            
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.vectors = data.get("vectors", {})
        self.metadata = data.get("metadata", {})
        self.config = data.get("config", {})
        self.backend = data.get("backend", "faiss")
        self.dimension = data.get("dimension", 768)
        
        # Restore backend-specific index
        indexer = getattr(self, "indexer", None)
        index_path = os.path.join(path, "index.bin")
        if indexer is not None and hasattr(indexer, "load_index"):
            if os.path.exists(index_path):
                indexer.load_index(index_path)
            else:
                # Rebuild if index file missing but vectors present
                indexer.create_index(list(self.vectors.values()), list(self.vectors.keys()))
        elif (
            self._backend_store is not None
            and hasattr(self._backend_store, "load_index")
            and os.path.exists(index_path)
        ):
            self._backend_store.load_index(index_path)

        self.logger.info(f"Loaded vector store from {path}")

    def search(self, query: str, limit: int = 10, **options) -> List[Dict[str, Any]]:
        """
        Search for similar vectors by query string.

        Args:
            query: Query string
            limit: Number of results
            **options: Additional options

        Returns:
            List of results with scores
        """
        # Generate embedding for query
        query_vector = self.embed(query)

        # Search by vector
        return self.search_vectors(query_vector=query_vector, k=limit, **options)

    def search_vectors(
        self, query_vector: np.ndarray, k: int = 10, **options
    ) -> List[SearchResult]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query vector
            k: Number of results to return
            **options: Search options

        Returns:
            List of search results with scores
        """
        # Delegate to backend store if available
        if self._backend_store:
            # Handle different method names across backend stores
            if hasattr(self._backend_store, 'search'):
                return self._backend_store.search(query_vector, top_k=k, **options)
            elif hasattr(self._backend_store, 'search_similar'):
                return self._backend_store.search_similar(query_vector, k=k, **options)
            elif hasattr(self._backend_store, 'search_vectors'):
                # Some stores (QdrantStore, MilvusStore, PineconeStore) name
                # their count parameter differently (limit vs k), so bind it
                # positionally rather than guessing the keyword.
                return self._backend_store.search_vectors(query_vector, k, **options)
            else:
                raise NotImplementedError(f"Backend store {type(self._backend_store).__name__} does not have search, search_similar, or search_vectors method")
        
        # Use in-memory implementation
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="VectorStore",
            message=f"Searching for {k} similar vectors",
        )

        try:
            if not self.vectors:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="completed", message="No vectors to search"
                )
                return []

            # Use retriever for similarity search
            self.progress_tracker.update_tracking(
                tracking_id, message="Performing similarity search..."
            )
            results = self.retriever.search_similar(
                query_vector,
                list(self.vectors.values()),
                list(self.vectors.keys()),
                k=k,
                **options,
            )

            # Add metadata to results; guarantee the key always exists.
            for result in results:
                vector_id = result.get("id")
                if vector_id and vector_id in self.metadata:
                    result["metadata"] = self.metadata[vector_id]
                elif "metadata" not in result:
                    result["metadata"] = {}

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Found {len(results)} similar vectors",
            )
            return results
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def update_vectors(
        self, vector_ids: List[str], new_vectors: List[np.ndarray], metadata: Optional[List[Dict[str, Any]]] = None, **options
    ) -> bool:
        """Update existing vectors."""
        # Delegate to backend store if available
        if self._backend_store:
            if hasattr(self._backend_store, 'update'):
                return self._backend_store.update(ids=vector_ids, vectors=new_vectors, metadata=metadata, **options)
            elif hasattr(self._backend_store, 'update_vectors'):
                return self._backend_store.update_vectors(vector_ids, new_vectors, **options)
            else:
                raise NotImplementedError(f"Backend store {type(self._backend_store).__name__} does not have update or update_vectors method")

        for vec_id, new_vec in zip(vector_ids, new_vectors):
            if vec_id in self.vectors:
                self.vectors[vec_id] = new_vec

        if metadata:
            for vec_id, meta in zip(vector_ids, metadata):
                if vec_id in self.metadata:
                    self.metadata[vec_id] = meta

        # Rebuild index
        self.indexer.create_index(
            list(self.vectors.values()), list(self.vectors.keys())
        )

        return True

    def delete_vectors(self, vector_ids: List[str], **options) -> bool:
        """Delete vectors from store."""
        # Delegate to backend store if available
        if self._backend_store:
            if hasattr(self._backend_store, 'delete'):
                return self._backend_store.delete(ids=vector_ids, **options)
            elif hasattr(self._backend_store, 'delete_vectors'):
                return self._backend_store.delete_vectors(vector_ids, **options)
            else:
                raise NotImplementedError(f"Backend store {type(self._backend_store).__name__} does not have delete or delete_vectors method")

        for vec_id in vector_ids:
            self.vectors.pop(vec_id, None)
            self.metadata.pop(vec_id, None)

        # Rebuild index
        if self.vectors:
            self.indexer.create_index(
                list(self.vectors.values()), list(self.vectors.keys())
            )

        return True

    def get_vector(self, vector_id: str) -> Optional[np.ndarray]:
        """Get vector by ID."""
        if self.backend == "inmemory":
            return self.vectors.get(vector_id)
        elif self._backend_store and hasattr(self._backend_store, "get_vector"):
            return self._backend_store.get_vector(vector_id)
        else:
            raise NotImplementedError(f"Backend store {type(self._backend_store).__name__} does not implement get_vector")

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for vector."""
        if self.backend == "inmemory":
            return self.metadata.get(vector_id)
        elif self._backend_store and hasattr(self._backend_store, "get_metadata"):
            return self._backend_store.get_metadata(vector_id)
        else:
            raise NotImplementedError(f"Backend store {type(self._backend_store).__name__} does not implement get_metadata")

    def count(self) -> int:
        """Return the number of vectors in the store, backend-agnostic.

        The inmemory backend counts its local dict; persistent backends
        delegate to a ``count()`` on the wrapped store when available.
        Following the get_vector()/get_metadata() precedent (#843) and the
        NotImplementedError-on-unsupported-capability precedent of
        _filter_by_metadata() (#848), a persistent backend that cannot
        report a count raises NotImplementedError so callers can tell
        "no vectors" apart from "counting not supported" — including when
        the wrapped backend store is missing entirely (never silently
        report an uninitialized store as empty).
        """
        if self.backend == "inmemory":
            return len(self.vectors)
        elif self._backend_store is not None:
            count_attr = getattr(self._backend_store, "count", None)
            if callable(count_attr):
                return cast(int, count_attr())
            raise NotImplementedError(
                f"Backend store {type(self._backend_store).__name__} does not "
                "implement a count() method. Add a count() method to the "
                "backend store adapter to enable vector counting for this backend."
            )
        raise NotImplementedError(
            f"Backend store is not initialized; cannot count vectors for "
            f"backend {self.backend!r}."
        )

    def initialize_decision_pipeline(
        self,
        graph_store: Optional[Any] = None,
        **pipeline_kwargs
    ) -> None:
        """
        Initialize decision embedding pipeline.
        
        Args:
            graph_store: Graph store for structural embeddings
            **pipeline_kwargs: Additional pipeline configuration
        """
        self.decision_pipeline = DecisionEmbeddingPipeline(
            vector_store=self,
            graph_store=graph_store,
            **pipeline_kwargs
        )
        self.logger.info("Decision embedding pipeline initialized")

    def store_decision(
        self,
        scenario: str,
        reasoning: Optional[str] = None,
        outcome: Optional[str] = None,
        confidence: Optional[float] = None,
        entities: Optional[List[str]] = None,
        category: Optional[str] = None,
        **additional_metadata
    ) -> str:
        """
        Store a decision with automatic embedding generation.
        
        Args:
            scenario: Decision scenario description
            reasoning: Decision reasoning
            outcome: Decision outcome
            confidence: Decision confidence score
            entities: List of entities involved
            category: Decision category
            **additional_metadata: Additional metadata
            
        Returns:
            Decision vector ID
        """
        decision_data = {
            "scenario": scenario,
            "reasoning": reasoning or "",
            "outcome": outcome or "unknown",
            "confidence": confidence or 0.5,
            "entities": entities or [],
            "category": category or "general",
            **additional_metadata
        }
        
        if self.decision_pipeline:
            result = self.decision_pipeline.process_decision(decision_data)
            return result["vector_id"]
        else:
            # Fallback: simple semantic embedding
            text = f"{scenario} {reasoning or ''} {outcome or ''} {category or ''}"
            embedding = self.embed(text)
            vector_id = self.store_vectors([embedding], metadata=[decision_data])[0]
            return vector_id

    def process_decision_batch(
        self,
        decisions: List[Dict[str, Any]],
        batch_size: int = 32
    ) -> List[Dict[str, Any]]:
        """
        Process multiple decisions in batch.
        
        Args:
            decisions: List of decision data dictionaries
            batch_size: Batch size for processing
            
        Returns:
            List of processed decision results
        """
        if self.decision_pipeline:
            return self.decision_pipeline.process_decision_batch(
                decisions, batch_size=batch_size
            )

        # Fallback: process each decision individually using store_decision
        results = []
        for decision in decisions:
            try:
                vector_id = self.store_decision(**decision)
                results.append({"vector_id": vector_id, "status": "success"})
            except Exception as e:
                self.logger.warning(f"Failed to process decision: {e}")
                results.append({"vector_id": None, "status": "error", "error": str(e)})
        return results

    def search_decisions(
        self,
        query: str,
        semantic_weight: float = 0.7,
        structural_weight: float = 0.3,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        use_hybrid_search: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for similar decisions with hybrid similarity.
        
        Args:
            query: Search query
            semantic_weight: Weight for semantic similarity
            structural_weight: Weight for structural similarity
            filters: Metadata filters
            limit: Number of results
            use_hybrid_search: Whether to use hybrid search
            
        Returns:
            List of similar decisions with scores
        """
        if not self.decision_pipeline:
            # Fallback to semantic search only
            return self.search(query, limit=limit, **(filters or {}))
        
        # Create query decision
        query_decision = {
            "scenario": query,
            "reasoning": "",
            "outcome": "search_query",
            "category": "search"
        }
        
        return self.decision_pipeline.find_similar_decisions(
            query_decision=query_decision,
            limit=limit,
            use_hybrid_search=use_hybrid_search,
            semantic_weight=semantic_weight,
            structural_weight=structural_weight,
            filters=filters
        )

    def filter_decisions(
        self,
        query: Optional[str] = None,
        time_range: Optional[str] = None,
        confidence_min: Optional[float] = None,
        category: Optional[str] = None,
        outcome: Optional[str] = None,
        entities: Optional[List[str]] = None,
        limit: int = 50,
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
            entities: List of entities to filter by
            limit: Maximum number of results
            **kwargs: Additional metadata filters (e.g., loan_amount_min=100000)
            
        Returns:
            Filtered decisions
        """
        # Build filters
        filters = {}
        
        if confidence_min is not None:
            filters["confidence"] = {"min": confidence_min}
        
        if category is not None:
            filters["category"] = category
        
        if outcome is not None:
            filters["outcome"] = outcome
        
        if entities is not None:
            filters["entities"] = entities
        
        # Process additional kwargs as metadata filters
        for key, value in kwargs.items():
            if key.endswith('_min'):
                # Handle minimum range filters
                field_name = key[:-4]  # Remove '_min' suffix
                if field_name not in filters:
                    filters[field_name] = {}
                filters[field_name]["min"] = value
            elif key.endswith('_max'):
                # Handle maximum range filters
                field_name = key[:-4]  # Remove '_max' suffix
                if field_name not in filters:
                    filters[field_name] = {}
                filters[field_name]["max"] = value
            else:
                # Handle exact match filters
                filters[key] = value
        
        # Apply time range filter
        if time_range:
            filters = self._apply_time_range_filter(filters, time_range)
        
        # Search with query if provided
        if query:
            return self.search_decisions(
                query=query,
                filters=filters,
                limit=limit
            )
        else:
            # Filter only, no semantic search
            return self._filter_by_metadata(filters, limit)

    def build_decision_context(
        self,
        decision_id: str,
        depth: int = 2,
        include_entities: bool = True,
        include_policies: bool = True,
        max_hops: int = 3
    ) -> Dict[str, Any]:
        """
        Build decision context graph.

        Args:
            decision_id: Decision vector ID
            depth: Context depth
            include_entities: Whether to include entities
            include_policies: Whether to include policies
            max_hops: Maximum hops for context expansion

        Returns:
            Decision context graph dict with keys:
              - decision_id, decision_metadata, entities, policies,
                related_decisions, context_graph.
            If the backend cannot retrieve the raw vector for *decision_id*
            (e.g. a FAISS index built without ``make_direct_map``), similarity
            enrichment is skipped, a WARNING is emitted, and the key
            ``similarity_unavailable=True`` is added.  ``related_decisions``
            remains an empty list for schema stability.
        """
        # Get decision metadata
        decision_metadata = self.get_metadata(decision_id)
        if not decision_metadata:
            raise ValueError(f"Decision {decision_id} not found")
        
        context = {
            "decision_id": decision_id,
            "decision_metadata": decision_metadata,
            "entities": [],
            "policies": [],
            "related_decisions": [],
            "context_graph": {
                "nodes": [],
                "edges": []
            }
        }
        
        # Add entities
        if include_entities and "entities" in decision_metadata:
            context["entities"] = decision_metadata["entities"]
        
        # Add related decisions based on similarity
        query_vector = self.get_vector(decision_id)
        if query_vector is not None:
            similar_decisions = self.search_vectors(query_vector, k=depth * 5)
            
            for result in similar_decisions:
                if result["id"] != decision_id:
                    context["related_decisions"].append({
                        "id": result["id"],
                        "similarity": result["score"],
                        "metadata": result.get("metadata", {})
                    })
        else:
            self.logger.warning(
                "Backend cannot retrieve vector for decision '%s' — "
                "similarity enrichment skipped.",
                decision_id,
            )
            context["similarity_unavailable"] = True
        
        return context

    def explain_decision(
        self,
        decision_id: str,
        include_paths: bool = True,
        include_confidence: bool = True,
        include_weights: bool = True
    ) -> Dict[str, Any]:
        """
        Generate explanation for a decision.

        Args:
            decision_id: Decision vector ID
            include_paths: Whether to include reasoning paths
            include_confidence: Whether to include confidence scores
            include_weights: Whether to include similarity weights

        Returns:
            Decision explanation dict.  When *include_paths* is True and the
            backend can retrieve the raw vector, ``similar_decisions`` is
            populated.  If the backend cannot retrieve the vector (e.g. a FAISS
            index without ``make_direct_map``), a WARNING is emitted, the key
            ``similarity_unavailable=True`` is added, and ``similar_decisions``
            is set to ``[]`` for schema stability.
        """
        decision_metadata = self.get_metadata(decision_id)
        if not decision_metadata:
            raise ValueError(f"Decision {decision_id} not found")
        
        explanation = {
            "decision_id": decision_id,
            "scenario": decision_metadata.get("scenario", ""),
            "reasoning": decision_metadata.get("reasoning", ""),
            "outcome": decision_metadata.get("outcome", ""),
            "timestamp": decision_metadata.get("timestamp", "")
        }
        
        if include_confidence:
            explanation["confidence"] = decision_metadata.get("confidence", 0.5)
        
        if include_weights:
            explanation["semantic_weight"] = decision_metadata.get("semantic_weight", 0.7)
            explanation["structural_weight"] = decision_metadata.get("structural_weight", 0.3)
        
        if include_paths:
            # Find similar decisions for reasoning paths
            query_vector = self.get_vector(decision_id)
            if query_vector is not None:
                similar_decisions = self.search_vectors(query_vector, k=3)
                explanation["similar_decisions"] = similar_decisions
            else:
                self.logger.warning(
                    "Backend cannot retrieve vector for decision '%s' — "
                    "similarity enrichment skipped.",
                    decision_id,
                )
                explanation["similarity_unavailable"] = True
                explanation["similar_decisions"] = []
        
        return explanation

    def _apply_time_range_filter(
        self,
        filters: Dict[str, Any],
        time_range: str
    ) -> Dict[str, Any]:
        """Apply time range filter to filters."""
        # This is a simplified implementation
        # In practice, this would parse time_range strings and convert to timestamps
        if time_range == "last_30_days":
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=30)
            filters["timestamp"] = {"min": cutoff.isoformat()}
        elif time_range == "last_7_days":
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=7)
            filters["timestamp"] = {"min": cutoff.isoformat()}
        return filters

    def _filter_by_metadata(self, filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """Filter decisions by metadata only."""
        if self._backend_store is not None:
            if hasattr(self._backend_store, "filter_by_metadata"):
                return self._backend_store.filter_by_metadata(filters=filters, limit=limit)
            raise NotImplementedError(
                f"Backend store {type(self._backend_store).__name__} does not "
                "implement filter_by_metadata. Metadata-only filtering via "
                "filter_decisions(query=None, ...) is only supported for backends "
                "that implement filter_by_metadata. Pass a query string to use search_decisions() "
                "instead, which is supported by all backends."
            )

        results = []
        
        for vector_id, metadata in self.metadata.items():
            if _matches_filter(metadata, filters):
                results.append({
                    "id": vector_id,
                    "metadata": metadata,
                    "vector": self.vectors.get(vector_id)
                })
                
                if len(results) >= limit:
                    break
        
        return results


def _matches_filter(metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """Check if metadata dictionary matches filter criteria."""
    if not filters:
        return True
    if metadata is None:
        return False

    for key, value in filters.items():
        if key not in metadata:
            return False

        metadata_value = metadata[key]

        if isinstance(value, dict):
            # Handle range filters
            if "min" in value and value["min"] is not None:
                if metadata_value is None or metadata_value < value["min"]:
                    return False
            if "max" in value and value["max"] is not None:
                if metadata_value is None or metadata_value > value["max"]:
                    return False
        elif isinstance(value, list):
            # Handle list membership
            if isinstance(metadata_value, list):
                if not (set(metadata_value) & set(value)):
                    return False
            else:
                if metadata_value not in value:
                    return False
        else:
            # Handle exact match
            if metadata_value != value:
                return False

    return True


class VectorIndexer:
    """Vector indexing engine."""

    def __init__(self, backend: str = "faiss", dimension: int = 768, **config):
        """Initialize vector indexer."""
        self.logger = get_logger("vector_indexer")
        self.config = config
        self.backend = backend
        self.dimension = dimension
        self.index = None

    def create_index(self, vectors: List[np.ndarray], ids: Optional[List[str]] = None, **options) -> Any:
        """
        Create search index for vectors.
        
        Args:
            vectors: List of vectors to index
            ids: Optional vector IDs
            **options: Additional indexing options
            
        Returns:
            Index object
        """
        if not vectors:
            return None

        # Convert to numpy array with consistent dimensions
        if isinstance(vectors[0], list):
            vectors = [np.array(v) for v in vectors]
        
        # Ensure all vectors have same dimension
        if vectors:
            target_dim = len(vectors[0])
            vectors = [v if len(v) == target_dim else np.pad(v, (0, max(0, target_dim - len(v))))[:target_dim] for v in vectors]
        
        vectors = np.vstack(vectors)

        # Simple in-memory index (would use FAISS, etc. in production)
        self.index = {"vectors": vectors, "ids": ids or list(range(len(vectors)))}

        return self.index

    def update_index(self, index: Any, new_vectors: List[np.ndarray], **options) -> Any:
        """Update existing index."""
        # Simplified - rebuild index
        return self.create_index(
            list(index["vectors"]) + new_vectors,
            index["ids"] + [f"new_{i}" for i in range(len(new_vectors))],
        )

    def optimize_index(self, index: Any, **options) -> Any:
        """Optimize index for better performance."""
        # Simplified - return as-is
        return index


class VectorRetriever:
    """Vector retrieval engine."""

    def __init__(self, backend: str = "faiss", **config):
        """Initialize vector retriever."""
        self.logger = get_logger("vector_retriever")
        self.config = config
        self.backend = backend

    def search_similar(
        self,
        query_vector: np.ndarray,
        vectors: List[np.ndarray],
        ids: List[str],
        k: int = 10,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query vector
            vectors: List of vectors to search
            ids: Vector IDs
            k: Number of results

        Returns:
            List of results with scores
        """
        if not vectors:
            return []

        # Convert to numpy with consistent dimensions
        if isinstance(vectors[0], list):
            vectors = [np.array(v) for v in vectors]
        
        # Ensure all vectors have same dimension as query
        query_dim = len(query_vector) if isinstance(query_vector, (list, np.ndarray)) else 0
        if query_dim > 0:
            vectors = [v if len(v) == query_dim else np.pad(v, (0, max(0, query_dim - len(v))))[:query_dim] for v in vectors]
        
        vectors = np.vstack(vectors)

        if isinstance(query_vector, list):
            query_vector = np.array(query_vector)

        # Calculate cosine similarity with epsilon to avoid division by zero
        epsilon = 1e-10
        query_norm = np.linalg.norm(query_vector)
        vector_norms = np.linalg.norm(vectors, axis=1)

        similarities = np.dot(vectors, query_vector) / (
            (vector_norms * query_norm) + epsilon
        )

        # Get top k
        top_indices = np.argsort(similarities)[::-1][:k]

        results = []
        for idx in top_indices:
            results.append(
                {
                    "id": ids[idx],
                    "vector": vectors[idx],
                    "score": float(similarities[idx]),
                    "metadata": {},
                    "distance": None,
                }
            )

        return results

    def search_by_metadata(
        self,
        metadata_filters: Dict[str, Any],
        vectors: List[np.ndarray],
        metadata: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        """Search vectors by metadata."""
        results = []

        for vec, meta in zip(vectors, metadata):
            match = True
            for key, value in metadata_filters.items():
                if key not in meta or meta[key] != value:
                    match = False
                    break

            if match:
                results.append({"vector": vec, "metadata": meta})

        return results

    def search_hybrid(
        self,
        query_vector: np.ndarray,
        metadata_filters: Dict[str, Any],
        vectors: List[np.ndarray],
        metadata: List[Dict[str, Any]],
        **options,
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search."""
        # Filter by metadata first
        filtered = self.search_by_metadata(metadata_filters, vectors, metadata)

        if not filtered:
            return []

        # Then search by similarity
        filtered_vectors = [r["vector"] for r in filtered]
        filtered_ids = [i for i in range(len(filtered_vectors))]

        return self.search_similar(
            query_vector, filtered_vectors, filtered_ids, **options
        )


class VectorManager:
    """Vector store management engine."""

    def __init__(self, **config):
        """Initialize vector manager."""
        self.logger = get_logger("vector_manager")
        self.config = config

    def manage_store(
        self, store: VectorStore, **operations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Manage vector store operations."""
        results = {}

        for op_name, op_config in operations.items():
            if op_name == "optimize":
                results["optimize"] = self.maintain_store(store)
            elif op_name == "statistics":
                results["statistics"] = self.collect_statistics(store)

        return results

    def maintain_store(
        self, store: VectorStore, **options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Maintain vector store health.

        For the inmemory backend, both the vector count and the metadata
        count are independently tracked in separate dicts and are compared
        as an integrity check.

        For persistent backends that implement ``VectorStore.count()``,
        only the vector count is available.  Metadata is co-located with
        each vector in the underlying store (added/deleted atomically),
        so a separate metadata count cannot be meaningfully distinguished
        from the vector count.  The response omits ``metadata_count`` for
        such backends and reports ``healthy: True`` to indicate that the
        store is reachable and operational.

        If the backend does not implement ``count()``, the ``NotImplementedError``
        propagates to the caller — it is not silenced.
        """
        if store.backend == "inmemory":
            # Inmemory keeps vectors and metadata in separate dicts; compare
            # them to detect accidental divergence (#855).
            vector_count = len(store.vectors)
            metadata_count = len(store.metadata)
            return {
                "healthy": vector_count == metadata_count,
                "vector_count": vector_count,
                "metadata_count": metadata_count,
            }

        # Persistent backend: delegate to count().  Metadata and vectors are
        # stored together, so only one count is available.
        vector_count = store.count()
        return {
            "healthy": True,
            "vector_count": vector_count,
            "metadata_count": None,
        }

    def collect_statistics(self, store: VectorStore) -> Dict[str, Any]:
        """Collect vector store statistics."""
        return {
            "total_vectors": store.count(),
            "dimension": store.dimension,
            "backend": store.backend,
        }
