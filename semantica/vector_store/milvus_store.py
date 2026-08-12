"""
Milvus Store Module

This module provides Milvus vector database integration for vector storage and
similarity search in the Semantica framework, supporting collection management,
partitioning, and efficient vector operations with various distance metrics.

Key Features:
    - Collection and partition management
    - Distance metrics (L2, Inner Product, Cosine)
    - Index types (IVF_FLAT, HNSW, etc.)
    - Expression-based filtering
    - Collection loading and release
    - Batch insert and search operations
    - Collection statistics and monitoring
    - Optional dependency handling

Main Classes:
    - MilvusStore: Main Milvus store for vector operations
    - MilvusClient: Milvus client wrapper
    - MilvusCollection: Collection wrapper with operations
    - MilvusSearch: Search operations and filtering

Example Usage:
    >>> from semantica.vector_store import MilvusStore
    >>> store = MilvusStore(host="localhost", port=19530)
    >>> store.connect()
    >>> collection = store.create_collection("my-collection", dimension=768, metric_type="L2")
    >>> store.insert_vectors(vectors)
    >>> collection.load()
    >>> results = store.search_vectors(query_vector, limit=10, expr="category == 'science'")
    >>> stats = store.get_stats()

Author: Semantica Contributors
License: MIT
"""

import math
import re
from typing import Any, Dict, List, Optional, Union

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


def _validate_milvus_key(key: str) -> str:
    """Validate and escape a metadata filter key for Milvus queries."""
    if not key or not isinstance(key, str) or not re.match(r"^[a-zA-Z0-9_.-]+$", key):
        raise ValidationError(f"Invalid metadata filter key: '{key}'")
    return key.replace("\\", "\\\\").replace('"', '\\"')


def _format_milvus_value(val: Any) -> str:
    """Format and escape a filter value for Milvus expression syntax."""
    if isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, (int, float)):
        if isinstance(val, float) and not math.isfinite(val):
            raise ValidationError(
                f"Invalid metadata filter value: {val!r}. NaN/Infinity are not "
                "valid Milvus expression literals."
            )
        return str(val)
    elif isinstance(val, str):
        escaped = (
            val.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        return f'"{escaped}"'
    elif val is None:
        return "null"
    else:
        escaped = (
            str(val)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        return f'"{escaped}"'

# Optional Milvus import
try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        MilvusException,
        connections,
        utility,
    )

    MILVUS_AVAILABLE = True
except (ImportError, OSError):
    MILVUS_AVAILABLE = False
    connections = None
    Collection = None
    FieldSchema = None
    CollectionSchema = None
    DataType = None
    utility = None
    MilvusException = None


class MilvusClient:
    """Milvus client wrapper."""

    def __init__(self, alias: str = "default"):
        """Initialize Milvus client wrapper."""
        self.alias = alias
        self.logger = get_logger("milvus_client")

    def connect(
        self,
        host: str = "localhost",
        port: int = 19530,
        user: Optional[str] = None,
        password: Optional[str] = None,
        **options,
    ) -> bool:
        """Connect to Milvus server."""
        if not MILVUS_AVAILABLE:
            raise ProcessingError("Milvus not available")

        try:
            connections.connect(
                alias=self.alias,
                host=host,
                port=port,
                user=user,
                password=password,
                **options,
            )
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to connect to Milvus: {str(e)}")

    def disconnect(self):
        """Disconnect from Milvus server."""
        if not MILVUS_AVAILABLE:
            return

        try:
            connections.disconnect(self.alias)
        except Exception as e:
            self.logger.warning(f"Failed to disconnect: {str(e)}")


class MilvusCollection:
    """Milvus collection wrapper."""

    def __init__(self, collection: Any, collection_name: str):
        """Initialize Milvus collection wrapper."""
        self.collection = collection
        self.collection_name = collection_name
        self.logger = get_logger("milvus_collection")

    def insert(self, data: List[List[Any]], **options) -> Any:
        """Insert data into collection."""
        if not MILVUS_AVAILABLE:
            raise ProcessingError("Milvus not available")

        try:
            insert_result = self.collection.insert(data, **options)
            return insert_result
        except Exception as e:
            raise ProcessingError(f"Failed to insert data: {str(e)}")

    def search(
        self,
        vectors: List[np.ndarray],
        anns_field: str,
        param: Dict[str, Any],
        limit: int = 10,
        expr: Optional[str] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """Search vectors in collection."""
        if not MILVUS_AVAILABLE:
            raise ProcessingError("Milvus not available")

        try:
            search_results = self.collection.search(
                data=[v.tolist() for v in vectors],
                anns_field=anns_field,
                param=param,
                limit=limit,
                expr=expr,
                **options,
            )

            results = []
            for hits in search_results:
                batch_results = []
                for hit in hits:
                    batch_results.append(
                        {
                            "id": hit.id,
                            "distance": hit.distance,
                            "score": 1.0 / (1.0 + max(0.0, hit.distance)),
                            # Milvus collection schema stores only id+vector; no
                            # metadata field is defined in create_collection().
                            # Return empty dict — a future schema migration that
                            # adds a metadata JSON field is tracked separately.
                            "metadata": {},
                            "vector": None,
                        }
                    )
                results.append(batch_results)

            return results[0] if len(results) == 1 else results
        except Exception as e:
            raise ProcessingError(f"Failed to search: {str(e)}")

    def load(self, **options) -> bool:
        """Load collection into memory."""
        if not MILVUS_AVAILABLE:
            raise ProcessingError("Milvus not available")

        try:
            self.collection.load(**options)
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to load collection: {str(e)}")

    def release(self) -> bool:
        """Release collection from memory."""
        if not MILVUS_AVAILABLE:
            raise ProcessingError("Milvus not available")

        try:
            self.collection.release()
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to release collection: {str(e)}")


class MilvusSearch:
    """Milvus search operations."""

    def __init__(self, collection: MilvusCollection):
        """Initialize Milvus search."""
        self.collection = collection
        self.logger = get_logger("milvus_search")

    def similarity_search(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        metric_type: str = "L2",
        expr: Optional[str] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search.

        Args:
            query_vector: Query vector
            limit: Number of results
            metric_type: Distance metric ("L2", "IP", "COSINE")
            expr: Filter expression
            **options: Additional options

        Returns:
            List of search results
        """
        search_params = {
            "metric_type": metric_type,
            "params": options.get("params", {"nprobe": 10}),
        }

        return self.collection.search(
            vectors=[query_vector],
            anns_field="vector",
            param=search_params,
            limit=limit,
            expr=expr,
            **options,
        )


class MilvusStore:
    """
    Milvus store for vector storage and similarity search.

    • Milvus connection and authentication
    • Collection and partition management
    • Vector storage and retrieval
    • Similarity search and filtering
    • Performance optimization
    • Error handling and recovery
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        user: Optional[str] = None,
        password: Optional[str] = None,
        **config,
    ):
        """Initialize Milvus store."""
        self.logger = get_logger("milvus_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True
        self.host = host or config.get("host", "localhost")
        self.port = port or config.get("port", 19530)
        self.user = user or config.get("user")
        self.password = password or config.get("password")

        self.client: Optional[MilvusClient] = None
        self.collection: Optional[MilvusCollection] = None
        self.search_engine: Optional[MilvusSearch] = None

        # Check Milvus availability
        if not MILVUS_AVAILABLE:
            self.logger.warning(
                "Milvus not available. Install with: pip install pymilvus"
            )

    def connect(self, **options) -> bool:
        """
        Connect to Milvus service.

        Args:
            **options: Connection options

        Returns:
            True if connected successfully
        """
        if not MILVUS_AVAILABLE:
            raise ProcessingError(
                "Milvus is not available. Install it with: pip install pymilvus"
            )

        try:
            self.client = MilvusClient()
            self.client.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                **options,
            )

            self.logger.info(f"Connected to Milvus at {self.host}:{self.port}")
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to connect to Milvus: {str(e)}")

    def create_collection(
        self, collection_name: str, dimension: int, metric_type: str = "L2", **options
    ) -> MilvusCollection:
        """
        Create Milvus collection.

        Args:
            collection_name: Name of the collection
            dimension: Vector dimension
            metric_type: Distance metric ("L2", "IP", "COSINE")
            **options: Additional options

        Returns:
            MilvusCollection instance
        """
        if self.client is None:
            self.connect()

        if not MILVUS_AVAILABLE:
            raise ProcessingError("Milvus not available")

        try:
            # Check if collection exists
            if utility.has_collection(collection_name):
                self.logger.info(f"Collection {collection_name} already exists")
                return self.get_collection(collection_name)

            # Define schema
            fields = [
                FieldSchema(
                    name="id", dtype=DataType.VARCHAR, is_primary=True, auto_id=False, max_length=65535
                ),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dimension),
                FieldSchema(name="metadata", dtype=DataType.JSON),
            ]

            schema = CollectionSchema(
                fields=fields, description=f"Vector collection for {collection_name}"
            )

            # Create collection
            collection = Collection(name=collection_name, schema=schema)

            # Create index
            index_params = {
                "metric_type": metric_type,
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024},
            }
            collection.create_index(field_name="vector", index_params=index_params)

            self.collection = MilvusCollection(collection, collection_name)
            self.search_engine = MilvusSearch(self.collection)

            self.logger.info(f"Created Milvus collection: {collection_name}")
            return self.collection

        except Exception as e:
            raise ProcessingError(f"Failed to create collection: {str(e)}")

    def get_collection(self, collection_name: str) -> MilvusCollection:
        """
        Get existing collection.

        Args:
            collection_name: Name of the collection

        Returns:
            MilvusCollection instance
        """
        if self.client is None:
            self.connect()

        if not MILVUS_AVAILABLE:
            raise ProcessingError("Milvus not available")

        try:
            if not utility.has_collection(collection_name):
                raise ProcessingError(f"Collection {collection_name} does not exist")

            collection = Collection(collection_name)
            self.collection = MilvusCollection(collection, collection_name)
            self.search_engine = MilvusSearch(self.collection)
            return self.collection
        except Exception as e:
            raise ProcessingError(f"Failed to get collection: {str(e)}")

    def insert_vectors(self, vectors: List[Union[np.ndarray, List[float]]], **options) -> Any:
        """Backward compatibility alias for add_vectors."""
        return self.add_vectors(vectors, **options)

    def add_vectors(
        self, 
        vectors: List[Union[np.ndarray, List[float]]], 
        ids: Optional[List[str]] = None,
        metadata: Optional[List[Dict[str, Any]]] = None,
        **options
    ) -> List[str]:
        """
        Add vectors to collection.

        Args:
            vectors: List of vectors
            ids: Optional list of vector IDs
            metadata: Optional list of metadata dictionaries
            **options: Additional options

        Returns:
            List of vector IDs
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="MilvusStore",
            message=f"Inserting {len(vectors)} vectors into Milvus collection",
        )

        try:
            if self.collection is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Collection not initialized"
                )
                raise ProcessingError(
                    "Collection not initialized. Call create_collection() or get_collection() first."
                )

            if not MILVUS_AVAILABLE:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Milvus not available"
                )
                raise ProcessingError("Milvus not available")

            # Convert vectors to list format
            self.progress_tracker.update_tracking(
                tracking_id, message="Converting vectors to list format..."
            )
            vector_data = []
            for vector in vectors:
                if isinstance(vector, np.ndarray):
                    vector = vector.tolist()
                vector_data.append(vector)

            import uuid
            if ids is None:
                ids = [str(uuid.uuid4()) for _ in range(len(vectors))]
                
            if metadata is None:
                metadata = [{} for _ in range(len(vectors))]

            data = [ids, vector_data, metadata]
            
            self.progress_tracker.update_tracking(
                tracking_id, message="Inserting vectors into collection..."
            )
            result = self.collection.insert(data, **options)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Inserted {len(vectors)} vectors",
            )
            return ids

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to insert vectors: {str(e)}")

    def search_vectors(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        metric_type: str = "L2",
        expr: Optional[str] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Search vectors in collection.

        Args:
            query_vector: Query vector
            limit: Number of results
            metric_type: Distance metric
            expr: Filter expression
            **options: Additional options

        Returns:
            List of search results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="MilvusStore",
            message=f"Searching for {limit} similar vectors in Milvus",
        )

        try:
            if self.search_engine is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Collection not initialized"
                )
                raise ProcessingError(
                    "Collection not initialized. Call create_collection() or get_collection() first."
                )

            # Load collection if not loaded
            if not self.collection.collection.has_index():
                self.progress_tracker.update_tracking(
                    tracking_id, message="Loading collection..."
                )
                self.collection.load()

            self.progress_tracker.update_tracking(
                tracking_id, message="Performing similarity search..."
            )
            results = self.search_engine.similarity_search(
                query_vector, limit, metric_type, expr, **options
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
        if not MILVUS_AVAILABLE or not self.collection:
            return None

        try:
            safe_id = vector_id.replace("\\", "\\\\").replace('"', '\\"')
            res = self.collection.collection.query(
                expr=f'id == "{safe_id}"',
                output_fields=["vector"]
            )
            if res and len(res) > 0:
                return np.array(res[0]["vector"])
            return None
        except Exception:
            return None

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata by ID."""
        if not MILVUS_AVAILABLE or not self.collection:
            return None

        try:
            safe_id = vector_id.replace("\\", "\\\\").replace('"', '\\"')
            res = self.collection.collection.query(
                expr=f'id == "{safe_id}"',
                output_fields=["metadata"]
            )
            if res and len(res) > 0:
                return res[0].get("metadata", {})
            return None
        except Exception:
            return None

    def filter_by_metadata(
        self, filters: Dict[str, Any], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Filter vectors by metadata using Milvus expression filtering.

        Args:
            filters: Metadata filter criteria
            limit: Maximum number of results

        Returns:
            List of matching result dicts with 'id', 'metadata', and 'vector'
        """
        if self.collection is None or not MILVUS_AVAILABLE:
            return []

        expr_parts = []
        if filters:
            for key, value in filters.items():
                safe_key = _validate_milvus_key(key)
                if isinstance(value, dict):
                    if "min" in value and value["min"] is not None:
                        min_val = _format_milvus_value(value["min"])
                        expr_parts.append(f'metadata["{safe_key}"] >= {min_val}')
                    if "max" in value and value["max"] is not None:
                        max_val = _format_milvus_value(value["max"])
                        expr_parts.append(f'metadata["{safe_key}"] <= {max_val}')
                elif isinstance(value, list):
                    formatted_vals = [_format_milvus_value(v) for v in value]
                    expr_parts.append(
                        f'metadata["{safe_key}"] in [{", ".join(formatted_vals)}]'
                    )
                else:
                    formatted_val = _format_milvus_value(value)
                    expr_parts.append(f'metadata["{safe_key}"] == {formatted_val}')

        expr = " and ".join(expr_parts) if expr_parts else "id != ''"

        try:
            query_results = self.collection.collection.query(
                expr=expr,
                limit=limit,
                output_fields=["id", "vector", "metadata"],
            )
            results = []
            for item in query_results:
                vec = item.get("vector")
                results.append(
                    {
                        "id": str(item.get("id")),
                        "metadata": item.get("metadata") or {},
                        "vector": np.array(vec) if vec is not None else None,
                    }
                )
            return results
        except Exception as e:
            self.logger.warning(f"Failed to query Milvus vectors by metadata expression: {e}")
            return []

    def get_stats(self, collection_name: Optional[str] = None) -> Dict[str, Any]:
        """Get collection statistics."""
        if self.collection is None and collection_name:
            self.get_collection(collection_name)

        if self.collection is None:
            raise ProcessingError(
                "Collection not initialized. Call create_collection() or get_collection() first."
            )

        try:
            stats = self.collection.collection.num_entities
            return {
                "entity_count": stats,
                "collection_name": self.collection.collection_name,
            }
        except Exception as e:
            self.logger.warning(f"Failed to get stats: {str(e)}")
            return {"status": "unknown"}
