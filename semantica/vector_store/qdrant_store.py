"""
Qdrant Store Module

This module provides Qdrant vector database integration for vector storage and
similarity search in the Semantica framework, supporting collection management,
payload filtering, and efficient vector operations with distance metrics.

Key Features:
    - Collection-based vector organization
    - Distance metrics (Cosine, Euclidean, Dot Product)
    - Payload (metadata) filtering and querying
    - Point-based vector operations
    - Batch insert and search operations
    - Collection statistics and monitoring
    - Optional dependency handling

Main Classes:
    - QdrantStore: Main Qdrant store for vector operations
    - QdrantClient: Qdrant client wrapper
    - QdrantCollection: Collection wrapper with operations
    - QdrantSearch: Search operations and filtering

Example Usage:
    >>> from semantica.vector_store import QdrantStore
    >>> store = QdrantStore(url="http://localhost:6333")
    >>> store.connect()
    >>> collection = store.create_collection("my-collection", vector_size=768, distance="Cosine")
    >>> store.insert_vectors(vectors, ids, payloads=metadata)
    >>> results = store.search_vectors(query_vector, limit=10, filter={"category": "science"})
    >>> stats = store.get_stats()

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Union

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Optional Qdrant import
try:
    from qdrant_client import QdrantClient as QdrantClientLib
    from qdrant_client.models import (
        CollectionStatus,
        Distance,
        FieldCondition,
        Filter,
        MatchAny,
        MatchValue,
        PointStruct,
        Range,
        VectorParams,
    )

    QDRANT_AVAILABLE = True
except (ImportError, OSError):
    QDRANT_AVAILABLE = False
    QdrantClientLib = None
    Distance = None
    VectorParams = None
    PointStruct = None
    Filter = None
    FieldCondition = None
    MatchAny = None
    MatchValue = None
    Range = None
    CollectionStatus = None


class QdrantClient:
    """Qdrant client wrapper."""

    def __init__(self, client: Any):
        """Initialize Qdrant client wrapper."""
        self.client = client
        self.logger = get_logger("qdrant_client")

    def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: str = "Cosine",
        **options,
    ) -> bool:
        """Create a collection in Qdrant."""
        if not QDRANT_AVAILABLE:
            raise ProcessingError("Qdrant not available")

        try:
            distance_map = {
                "Cosine": Distance.COSINE,
                "Euclidean": Distance.EUCLID,
                "Dot": Distance.DOT,
            }

            distance_enum = distance_map.get(distance, Distance.COSINE)

            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance_enum),
                **options,
            )
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to create collection: {str(e)}")

    def get_collection(self, collection_name: str) -> Any:
        """Get collection info."""
        if not QDRANT_AVAILABLE:
            raise ProcessingError("Qdrant not available")

        try:
            return self.client.get_collection(collection_name)
        except Exception as e:
            raise ProcessingError(f"Failed to get collection: {str(e)}")


class QdrantCollection:
    """Qdrant collection wrapper."""

    def __init__(self, client: Any, collection_name: str):
        """Initialize Qdrant collection wrapper."""
        self.client = client
        self.collection_name = collection_name
        self.logger = get_logger("qdrant_collection")

    def upsert_points(self, points: List[PointStruct], **options) -> Dict[str, Any]:
        """Upsert points to collection."""
        if not QDRANT_AVAILABLE:
            raise ProcessingError("Qdrant not available")

        try:
            response = self.client.upsert(
                collection_name=self.collection_name, points=points, **options
            )
            return {"status": response.status}
        except Exception as e:
            raise ProcessingError(f"Failed to upsert points: {str(e)}")

    def search_points(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        query_filter: Optional[Filter] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """Search for similar points."""
        if not QDRANT_AVAILABLE:
            raise ProcessingError("Qdrant not available")

        try:
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector.tolist(),
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
                with_vectors=False,
                **options,
            )

            results = []
            for result in search_results:
                results.append(
                    {
                        "id": result.id,
                        # See pinecone_store.py PineconeIndex.search_vectors for why
                        # this uses x/(1+|x|) rather than clamping distance-to-zero:
                        # Qdrant's Dot distance metric is unbounded, and the old
                        # clamped formula collapsed every score >= 1.0 to 1.0.
                        "score": (
                            float(result.score) / (1.0 + abs(float(result.score))) + 1.0
                        )
                        / 2.0,
                        "metadata": result.payload or {},
                        "vector": None,
                        "distance": None,
                    }
                )

            return results
        except Exception as e:
            raise ProcessingError(f"Failed to search points: {str(e)}")

    def delete_points(
        self, point_ids: List[Union[str, int]], **options
    ) -> Dict[str, Any]:
        """Delete points from collection."""
        if not QDRANT_AVAILABLE:
            raise ProcessingError("Qdrant not available")

        try:
            response = self.client.delete(
                collection_name=self.collection_name,
                points_selector=point_ids,
                **options,
            )
            return {"status": response.status}
        except Exception as e:
            raise ProcessingError(f"Failed to delete points: {str(e)}")


class QdrantSearch:
    """Qdrant search operations."""

    def __init__(self, collection: QdrantCollection):
        """Initialize Qdrant search."""
        self.collection = collection
        self.logger = get_logger("qdrant_search")

    def similarity_search(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search.

        Args:
            query_vector: Query vector
            limit: Number of results
            filter: Metadata filter
            **options: Additional options

        Returns:
            List of search results
        """
        query_filter = None
        if filter and QDRANT_AVAILABLE:
            # Build Qdrant filter from dict
            conditions = []
            for key, value in filter.items():
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )
            if conditions:
                query_filter = Filter(must=conditions)

        return self.collection.search_points(
            query_vector, limit, query_filter, **options
        )


class QdrantStore:
    """
    Qdrant store for vector storage and similarity search.

    • Qdrant connection and authentication
    • Collection and point management
    • Vector storage and retrieval
    • Similarity search and filtering
    • Performance optimization
    • Error handling and recovery
    """

    def __init__(
        self, url: Optional[str] = None, api_key: Optional[str] = None, **config
    ):
        """Initialize Qdrant store."""
        self.logger = get_logger("qdrant_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True
        self.url = url or config.get("url", "http://localhost:6333")
        self.api_key = api_key or config.get("api_key")

        self.client: Optional[Any] = None
        self.collection: Optional[QdrantCollection] = None
        self.search_engine: Optional[QdrantSearch] = None

        # Check Qdrant availability
        if not QDRANT_AVAILABLE:
            self.logger.warning(
                "Qdrant not available. Install with: pip install qdrant-client"
            )

    def connect(
        self, url: Optional[str] = None, api_key: Optional[str] = None, **options
    ) -> bool:
        """
        Connect to Qdrant service.

        Args:
            url: Qdrant URL
            api_key: API key for authentication
            **options: Connection options

        Returns:
            True if connected successfully
        """
        if not QDRANT_AVAILABLE:
            raise ProcessingError(
                "Qdrant is not available. Install it with: pip install qdrant-client"
            )

        url = url or self.url
        api_key = api_key or self.api_key

        try:
            if api_key:
                self.client = QdrantClientLib(url=url, api_key=api_key, **options)
            else:
                self.client = QdrantClientLib(url=url, **options)

            self.logger.info(f"Connected to Qdrant at {url}")
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to connect to Qdrant: {str(e)}")

    def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: str = "Cosine",
        **options,
    ) -> QdrantCollection:
        """
        Create Qdrant collection.

        Args:
            collection_name: Name of the collection
            vector_size: Vector dimension
            distance: Distance metric ("Cosine", "Euclidean", "Dot")
            **options: Additional options

        Returns:
            QdrantCollection instance
        """
        if self.client is None:
            self.connect()

        if not QDRANT_AVAILABLE:
            raise ProcessingError("Qdrant not available")

        try:
            client_wrapper = QdrantClient(self.client)
            client_wrapper.create_collection(
                collection_name, vector_size, distance, **options
            )

            self.collection = QdrantCollection(self.client, collection_name)
            self.search_engine = QdrantSearch(self.collection)

            self.logger.info(f"Created Qdrant collection: {collection_name}")
            return self.collection

        except Exception as e:
            raise ProcessingError(f"Failed to create collection: {str(e)}")

    def get_collection(self, collection_name: str) -> QdrantCollection:
        """
        Get existing collection.

        Args:
            collection_name: Name of the collection

        Returns:
            QdrantCollection instance
        """
        if self.client is None:
            self.connect()

        if not QDRANT_AVAILABLE:
            raise ProcessingError("Qdrant not available")

        try:
            client_wrapper = QdrantClient(self.client)
            client_wrapper.get_collection(collection_name)

            self.collection = QdrantCollection(self.client, collection_name)
            self.search_engine = QdrantSearch(self.collection)
            return self.collection
        except Exception as e:
            raise ProcessingError(f"Failed to get collection: {str(e)}")

    def insert_vectors(
        self,
        vectors: List[Union[np.ndarray, List[float]]],
        ids: List[Union[str, int]],
        payloads: Optional[List[Dict[str, Any]]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Insert vectors into collection.

        Args:
            vectors: List of vectors
            ids: Point IDs
            payloads: Optional metadata payloads
            **options: Additional options

        Returns:
            Insert response
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="QdrantStore",
            message=f"Inserting {len(vectors)} vectors into Qdrant collection",
        )

        try:
            if self.collection is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Collection not initialized"
                )
                raise ProcessingError(
                    "Collection not initialized. Call create_collection() or get_collection() first."
                )

            if not QDRANT_AVAILABLE:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Qdrant not available"
                )
                raise ProcessingError("Qdrant not available")

            self.progress_tracker.update_tracking(
                tracking_id, message="Preparing points..."
            )
            points = []
            for i, (vector, point_id) in enumerate(zip(vectors, ids)):
                if isinstance(vector, np.ndarray):
                    vector = vector.tolist()

                payload = payloads[i] if payloads and i < len(payloads) else {}

                points.append(PointStruct(id=point_id, vector=vector, payload=payload))

            self.progress_tracker.update_tracking(
                tracking_id, message="Upserting points to collection..."
            )
            result = self.collection.upsert_points(points, **options)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Inserted {len(vectors)} vectors",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to insert vectors: {str(e)}")

    def search_vectors(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Search vectors in collection.

        Args:
            query_vector: Query vector
            limit: Number of results
            filter: Metadata filter
            **options: Additional options

        Returns:
            List of search results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="QdrantStore",
            message=f"Searching for {limit} similar vectors in Qdrant",
        )

        try:
            if self.search_engine is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Collection not initialized"
                )
                raise ProcessingError(
                    "Collection not initialized. Call create_collection() or get_collection() first."
                )

            self.progress_tracker.update_tracking(
                tracking_id, message="Performing similarity search..."
            )
            results = self.search_engine.similarity_search(
                query_vector, limit, filter, **options
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

    def get_vector(self, vector_id: str) -> Optional[np.ndarray]:
        """Get vector by ID."""
        if self.collection is None or not QDRANT_AVAILABLE:
            return None
        
        try:
            results = self.client.retrieve(
                collection_name=self.collection.collection_name,
                ids=[vector_id],
                with_vectors=True,
                with_payload=False
            )
            if results and results[0].vector:
                return np.array(results[0].vector)
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get vector {vector_id}: {e}")
            return None

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata by ID."""
        if self.collection is None or not QDRANT_AVAILABLE:
            return None
            
        try:
            results = self.client.retrieve(
                collection_name=self.collection.collection_name,
                ids=[vector_id],
                with_vectors=False,
                with_payload=True
            )
            if results and results[0].payload is not None:
                return results[0].payload
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get metadata for {vector_id}: {e}")
            return None

    def filter_by_metadata(
        self, filters: Dict[str, Any], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Filter vectors by metadata using Qdrant payload filtering.

        Args:
            filters: Metadata filter criteria
            limit: Maximum number of results

        Returns:
            List of matching result dicts with 'id', 'metadata', and 'vector'
        """
        if self.collection is None or self.client is None or not QDRANT_AVAILABLE:
            return []

        conditions = []
        if filters:
            for key, value in filters.items():
                if isinstance(value, dict):
                    cond_kwargs = {}
                    if "min" in value and value["min"] is not None:
                        cond_kwargs["gte"] = value["min"]
                    if "max" in value and value["max"] is not None:
                        cond_kwargs["lte"] = value["max"]
                    if cond_kwargs:
                        conditions.append(
                            FieldCondition(key=key, range=Range(**cond_kwargs))
                        )
                elif isinstance(value, list):
                    conditions.append(
                        FieldCondition(key=key, match=MatchAny(any=value))
                    )
                else:
                    conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )

        query_filter = Filter(must=conditions) if conditions else None

        try:
            records, _ = self.client.scroll(
                collection_name=self.collection.collection_name,
                scroll_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=True,
            )
            results = []
            for rec in records:
                results.append(
                    {
                        "id": str(rec.id),
                        "metadata": rec.payload or {},
                        "vector": np.array(rec.vector) if rec.vector is not None else None,
                    }
                )
            return results
        except Exception as e:
            self.logger.warning(f"Failed to scroll Qdrant points by metadata filter: {e}")
            return []

    def delete_vectors(
        self, point_ids: List[Union[str, int]], **options
    ) -> Dict[str, Any]:
        """
        Delete vectors from collection.

        Args:
            point_ids: Point IDs to delete
            **options: Additional options

        Returns:
            Delete response
        """
        if self.collection is None:
            raise ProcessingError(
                "Collection not initialized. Call create_collection() or get_collection() first."
            )

        return self.collection.delete_points(point_ids, **options)

    def get_stats(self, collection_name: Optional[str] = None) -> Dict[str, Any]:
        """Get collection statistics."""
        if self.collection is None and collection_name:
            self.get_collection(collection_name)

        if self.collection is None:
            raise ProcessingError(
                "Collection not initialized. Call create_collection() or get_collection() first."
            )

        try:
            collection_info = self.client.get_collection(
                self.collection.collection_name
            )
            return {
                "points_count": collection_info.points_count,
                "vectors_count": collection_info.vectors_count,
                "status": str(collection_info.status)
                if hasattr(collection_info, "status")
                else "unknown",
            }
        except Exception as e:
            self.logger.warning(f"Failed to get stats: {str(e)}")
            return {"status": "unknown"}
