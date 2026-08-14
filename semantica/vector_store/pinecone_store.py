"""
Pinecone Store Module

This module provides Pinecone vector database integration for vector storage and
similarity search in the Semantica framework, supporting managed vector database
service with serverless and pod-based indexes, namespace isolation, and efficient
vector operations with metadata filtering.

Key Features:
 - Serverless and Pod-based index management
 - Namespace isolation for multi-tenant support
 - Metadata filtering during search
 - Batch operations for efficient data loading
 - Index creation, deletion, and listing
 - Optional dependency handling

Main Classes:
 - PineconeStore: Main Pinecone store for vector operations
 - PineconeClient: Pinecone client wrapper
 - PineconeIndex: Index wrapper with operations
 - PineconeSearch: Search operations and filtering

Example Usage:
 >>> from semantica.vector_store import PineconeStore
 >>> store = PineconeStore(api_key="your-api-key")
 >>> store.connect()
 >>> store.create_index("my-index", dimension=768)
 >>> store.upsert_vectors(vectors, ids, metadata=metadata)
 >>> results = store.search_vectors(query_vector, k=10, filter={"category": "science"})
 >>> stats = store.get_stats()

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Union

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Optional Pinecone import
try:
    from pinecone import Pinecone as PineconeClientLib, ServerlessSpec, PodSpec

    PINECONE_AVAILABLE = True
except (ImportError, OSError):
    PINECONE_AVAILABLE = False
    PineconeClientLib = None
    ServerlessSpec = None
    PodSpec = None


class PineconeClient:
    """Pinecone client wrapper."""

    def __init__(self, client: Any):
        """Initialize Pinecone client wrapper."""
        self.client = client
        self.logger = get_logger("pinecone_client")

    def create_index(
        self,
        index_name: str,
        dimension: int,
        metric: str = "cosine",
        spec: Optional[Dict[str, Any]] = None,
        **options,
    ) -> bool:
        """Create an index in Pinecone."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            # Default to serverless spec if not provided
            if spec is None and ServerlessSpec is not None:
                spec = ServerlessSpec(cloud="aws", region="us-east-1")

            # Map metric names
            metric_map = {
                "cosine": "cosine",
                "euclidean": "euclidean_distance",
                "dot": "dotproduct",
            }
            pinecone_metric = metric_map.get(metric.lower(), "cosine")

            self.client.create_index(
                name=index_name,
                dimension=dimension,
                metric=pinecone_metric,
                spec=spec,
                **options,
            )
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to create index: {str(e)}")

    def delete_index(self, index_name: str) -> bool:
        """Delete an index from Pinecone."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            self.client.delete_index(index_name)
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to delete index: {str(e)}")

    def list_indexes(self) -> List[str]:
        """List available indexes."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            indexes = self.client.list_indexes()
            return [index.name for index in indexes]
        except Exception as e:
            raise ProcessingError(f"Failed to list indexes: {str(e)}")

    def get_index(self, index_name: str) -> Any:
        """Get index object."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            return self.client.Index(index_name)
        except Exception as e:
            raise ProcessingError(f"Failed to get index: {str(e)}")


class PineconeIndex:
    """Pinecone index wrapper."""

    def __init__(self, index: Any):
        """Initialize Pinecone index wrapper."""
        self.index = index
        self.logger = get_logger("pinecone_index")

    def upsert_vectors(
        self,
        vectors: List[List[float]],
        ids: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        namespace: str = "",
        **options,
    ) -> Dict[str, Any]:
        """Upsert vectors to index."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            # Prepare vectors for upsert
            upsert_data = []
            for i, (vector, vector_id) in enumerate(zip(vectors, ids)):
                vector_dict = {"id": vector_id, "values": vector}
                if metadata and i < len(metadata):
                    vector_dict["metadata"] = metadata[i]
                upsert_data.append(vector_dict)

            response = self.index.upsert(
                vectors=upsert_data, namespace=namespace, **options
            )
            return {"upserted_count": response.upserted_count}
        except Exception as e:
            raise ProcessingError(f"Failed to upsert vectors: {str(e)}")

    def search_vectors(
        self,
        query_vector: List[float],
        k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        namespace: str = "",
        **options,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            response = self.index.query(
                vector=query_vector,
                top_k=k,
                filter=filter,
                namespace=namespace,
                include_metadata=True,
                include_values=False,
                **options,
            )

            results = []
            for match in response.matches:
                results.append(
                    {
                        "id": match.id,
                        # Pinecone's native score is already "higher is better" but its
                        # range depends on the configured metric (bounded for cosine,
                        # unbounded for dotproduct). Squash with x/(1+|x|) instead of
                        # clamping distance-to-zero, since the latter collapses every
                        # score >= 1.0 to an identical 1.0 and destroys ranking order
                        # for dotproduct/unnormalized-vector indexes.
                        "score": (
                            float(match.score) / (1.0 + abs(float(match.score))) + 1.0
                        )
                        / 2.0,
                        "metadata": match.metadata or {},
                        "vector": None,
                        "distance": None,
                    }
                )

            return results
        except Exception as e:
            raise ProcessingError(f"Failed to search vectors: {str(e)}")

    def delete_vectors(
        self, vector_ids: List[str], namespace: str = "", **options
    ) -> Dict[str, Any]:
        """Delete vectors from index."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            response = self.index.delete(ids=vector_ids, namespace=namespace, **options)
            return {"deleted": True}
        except Exception as e:
            raise ProcessingError(f"Failed to delete vectors: {str(e)}")

    def fetch_vectors(
        self, vector_ids: List[str], namespace: str = "", **options
    ) -> Dict[str, Any]:
        """Fetch vectors by ID."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            response = self.index.fetch(ids=vector_ids, namespace=namespace, **options)
            return {
                "vectors": {
                    vector_id: {
                        "values": vector.values,
                        "metadata": vector.metadata or {},
                    }
                    for vector_id, vector in response.vectors.items()
                }
            }
        except Exception as e:
            raise ProcessingError(f"Failed to fetch vectors: {str(e)}")

    def describe_index_stats(self, **options) -> Dict[str, Any]:
        """Get index statistics."""
        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            stats = self.index.describe_index_stats(**options)
            return {
                "dimension": stats.dimension,
                "index_fullness": stats.index_fullness,
                "total_vector_count": stats.total_vector_count,
                "namespaces": stats.namespaces,
            }
        except Exception as e:
            raise ProcessingError(f"Failed to get index stats: {str(e)}")


class PineconeSearch:
    """Pinecone search operations."""

    def __init__(self, index: PineconeIndex):
        """Initialize Pinecone search."""
        self.index = index
        self.logger = get_logger("pinecone_search")

    def similarity_search(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        namespace: str = "",
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search.

        Args:
            query_vector: Query vector
            limit: Number of results
            filter: Metadata filter
            namespace: Namespace to search in
            **options: Additional options

        Returns:
            List of search results
        """
        return self.index.search_vectors(
            query_vector.tolist(), limit, filter, namespace, **options
        )


class PineconeStore:
    """
    Pinecone store for vector storage and similarity search.

    • Pinecone connection and authentication
    • Index and namespace management
    • Vector storage and retrieval
    • Similarity search and filtering
    • Performance optimization
    • Error handling and recovery
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        environment: Optional[str] = None,
        **config,
    ):
        """Initialize Pinecone store."""
        self.logger = get_logger("pinecone_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.api_key = api_key or config.get("api_key")
        self.environment = environment or config.get("environment")
        self.dimension: Optional[int] = config.get("dimension")

        self.client: Optional[PineconeClient] = None
        self.index: Optional[PineconeIndex] = None
        self.search_engine: Optional[PineconeSearch] = None

        # Check Pinecone availability
        if not PINECONE_AVAILABLE:
            self.logger.warning(
                "Pinecone not available. Install with: pip install pinecone-client"
            )

    def connect(self, **kwargs) -> bool:
        """
        Connect to Pinecone service.

        Args:
            **kwargs: Connection options

        Returns:
            True if connected successfully
        """
        if not PINECONE_AVAILABLE:
            raise ProcessingError(
                "Pinecone is not available. Install it with: pip install pinecone-client"
            )

        api_key = kwargs.get("api_key") or self.api_key
        if not api_key:
            raise ValidationError("Pinecone API key is required")

        try:
            pinecone_client = PineconeClientLib(api_key=api_key, **kwargs)
            self.client = PineconeClient(pinecone_client)

            self.logger.info("Connected to Pinecone")
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to connect to Pinecone: {str(e)}")

    def create_index(
        self,
        index_name: str,
        dimension: int,
        metric: str = "cosine",
        spec: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Create a Pinecone index.

        Args:
            index_name: Name of the index
            dimension: Vector dimension
            metric: Distance metric ("cosine", "euclidean", "dot")
            spec: Index specification (ServerlessSpec or PodSpec)
            **kwargs: Additional options

        Returns:
            PineconeIndex instance
        """
        if self.client is None:
            self.connect()

        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            # Create index spec if not provided
            if spec is None and ServerlessSpec is not None:
                spec = ServerlessSpec(cloud="aws", region="us-east-1")

            self.client.create_index(index_name, dimension, metric, spec, **kwargs)

            # Get the index
            pinecone_index = self.client.get_index(index_name)
            self.index = PineconeIndex(pinecone_index)
            self.search_engine = PineconeSearch(self.index)
            self.dimension = dimension

            self.logger.info(f"Created Pinecone index: {index_name}")
            return self.index

        except Exception as e:
            raise ProcessingError(f"Failed to create index: {str(e)}")

    def get_index(self, index_name: str) -> PineconeIndex:
        """
        Get existing index.

        Args:
            index_name: Name of the index

        Returns:
            PineconeIndex instance
        """
        if self.client is None:
            self.connect()

        if not PINECONE_AVAILABLE:
            raise ProcessingError("Pinecone not available")

        try:
            pinecone_index = self.client.get_index(index_name)
            self.index = PineconeIndex(pinecone_index)
            self.search_engine = PineconeSearch(self.index)
            if self.dimension is None:
                try:
                    stats = self.index.describe_index_stats()
                    if stats and isinstance(stats, dict) and stats.get("dimension"):
                        self.dimension = int(stats["dimension"])
                except Exception as e:
                    self.logger.warning(f"Could not determine index dimension for '{index_name}': {e}")
            return self.index
        except Exception as e:
            raise ProcessingError(f"Failed to get index: {str(e)}")

    def delete_index(self, index_name: str) -> bool:
        """
        Delete an index.

        Args:
            index_name: Name of the index to delete

        Returns:
            True if deleted successfully
        """
        if self.client is None:
            self.connect()

        return self.client.delete_index(index_name)

    def list_indexes(self) -> List[str]:
        """
        List available indexes.

        Returns:
            List of index names
        """
        if self.client is None:
            self.connect()

        return self.client.list_indexes()

    def upsert_vectors(
        self,
        vectors: List[Any],
        ids: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        namespace: str = "",
        **options,
    ) -> Dict[str, Any]:
        """
        Upsert vectors to index.

        Args:
            vectors: List of vectors
            ids: Vector IDs
            metadata: Optional metadata for each vector
            namespace: Namespace to upsert into
            **options: Additional options

        Returns:
            Upsert response
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="PineconeStore",
            message=f"Upserting {len(vectors)} vectors to Pinecone index",
        )

        try:
            if self.index is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Index not initialized"
                )
                raise ProcessingError(
                    "Index not initialized. Call create_index() or get_index() first."
                )

            if not PINECONE_AVAILABLE:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Pinecone not available"
                )
                raise ProcessingError("Pinecone not available")

            self.progress_tracker.update_tracking(
                tracking_id, message="Preparing vectors..."
            )

            # Convert vectors to list format
            vector_list = []
            for vector in vectors:
                if isinstance(vector, np.ndarray):
                    vector_list.append(vector.tolist())
                else:
                    vector_list.append(list(vector))

            if self.dimension is None and vector_list:
                self.dimension = len(vector_list[0])

            self.progress_tracker.update_tracking(
                tracking_id, message="Upserting vectors to index..."
            )
            result = self.index.upsert_vectors(
                vector_list, ids, metadata, namespace, **options
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Upserted {len(vectors)} vectors",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to upsert vectors: {str(e)}")

    def search_vectors(
        self,
        query_vector: Any,
        k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        namespace: str = "",
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Search vectors in index.

        Args:
            query_vector: Query vector
            k: Number of results
            filter: Metadata filter
            namespace: Namespace to search in
            **options: Additional options

        Returns:
            List of search results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="PineconeStore",
            message=f"Searching for {k} similar vectors in Pinecone",
        )

        try:
            if self.search_engine is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Index not initialized"
                )
                raise ProcessingError(
                    "Index not initialized. Call create_index() or get_index() first."
                )

            self.progress_tracker.update_tracking(
                tracking_id, message="Performing similarity search..."
            )

            # Convert query vector to list
            if isinstance(query_vector, np.ndarray):
                query_vector = query_vector.tolist()
            else:
                query_vector = list(query_vector)

            if self.dimension is None and query_vector:
                self.dimension = len(query_vector)

            results = self.search_engine.similarity_search(
                np.array(query_vector), k, filter, namespace, **options
            )

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

    def delete_vectors(
        self, vector_ids: List[str], namespace: str = "", **options
    ) -> Dict[str, Any]:
        """
        Delete vectors from index.

        Args:
            vector_ids: Vector IDs to delete
            namespace: Namespace to delete from
            **options: Additional options

        Returns:
            Delete response
        """
        if self.index is None:
            raise ProcessingError(
                "Index not initialized. Call create_index() or get_index() first."
            )

        return self.index.delete_vectors(vector_ids, namespace, **options)

    def get_vector(self, vector_id: str) -> Optional[np.ndarray]:
        """Get vector by ID."""
        try:
            res = self.fetch_vectors([vector_id])
            if "vectors" in res and vector_id in res["vectors"]:
                return np.array(res["vectors"][vector_id]["values"])
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get vector {vector_id}: {e}")
            return None

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata by ID."""
        try:
            res = self.fetch_vectors([vector_id])
            if "vectors" in res and vector_id in res["vectors"]:
                return res["vectors"][vector_id].get("metadata", {})
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get metadata for {vector_id}: {e}")
            return None

    def filter_by_metadata(
        self, filters: Dict[str, Any], limit: int = 10, namespace: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Filter vectors by metadata using Pinecone metadata filters.

        Args:
            filters: Metadata filter criteria
            limit: Maximum number of results
            namespace: Namespace to search in

        Returns:
            List of matching result dicts with 'id', 'metadata', and 'vector'
        """
        if self.index is None or not PINECONE_AVAILABLE:
            return []

        dimension = self.dimension
        if dimension is None:
            try:
                stats = self.index.describe_index_stats()
                if stats and isinstance(stats, dict) and stats.get("dimension"):
                    dimension = int(stats["dimension"])
                    self.dimension = dimension
            except Exception:
                pass

        if not dimension:
            raise ProcessingError(
                "Index dimension is unknown. Please specify 'dimension' when initializing PineconeStore "
                "or call create_index()/get_index() first."
            )

        pinecone_filter = {}
        if filters:
            for key, value in filters.items():
                if isinstance(value, dict):
                    cond = {}
                    if "min" in value and value["min"] is not None:
                        cond["$gte"] = value["min"]
                    if "max" in value and value["max"] is not None:
                        cond["$lte"] = value["max"]
                    if cond:
                        pinecone_filter[key] = cond
                elif isinstance(value, list):
                    pinecone_filter[key] = {"$in": value}
                else:
                    pinecone_filter[key] = value

        # A literal zero vector is rejected by Pinecone for cosine-metric indexes
        # ("Query vector must not be the zero vector"). Use a unit vector instead so
        # this works regardless of the index's distance metric; since this call only
        # cares about which vectors match `filter`, not similarity ranking, any
        # fixed non-zero query vector is an equally valid probe.
        dummy_vector = [1.0 / (dimension ** 0.5)] * dimension

        try:
            response = self.index.index.query(
                vector=dummy_vector,
                top_k=limit,
                filter=pinecone_filter if pinecone_filter else None,
                namespace=namespace,
                include_metadata=True,
                include_values=True,
            )
            results = []
            for match in response.matches:
                results.append(
                    {
                        "id": match.id,
                        "metadata": match.metadata or {},
                        "vector": np.array(match.values) if match.values else None,
                    }
                )
            return results
        except Exception as e:
            self.logger.warning(f"Failed to filter Pinecone vectors by metadata: {e}")
            return []

    def fetch_vectors(
        self, vector_ids: List[str], namespace: str = "", **options
    ) -> Dict[str, Any]:
        """
        Fetch vectors by ID.

        Args:
            vector_ids: Vector IDs to fetch
            namespace: Namespace to fetch from
            **options: Additional options

        Returns:
            Fetch response
        """
        if self.index is None:
            raise ProcessingError(
                "Index not initialized. Call create_index() or get_index() first."
            )

        return self.index.fetch_vectors(vector_ids, namespace, **options)

    def get_stats(self, **options) -> Dict[str, Any]:
        """Get index statistics."""
        if self.index is None:
            raise ProcessingError(
                "Index not initialized. Call create_index() or get_index() first."
            )

        return self.index.describe_index_stats(**options)
