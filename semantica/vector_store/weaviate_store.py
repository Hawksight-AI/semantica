"""
Weaviate Store Module

This module provides Weaviate vector database integration for vector storage and
similarity search in the Semantica framework, supporting GraphQL queries, schema
management, and object-oriented vector storage with rich metadata support.

Key Features:
    - GraphQL-based query interface
    - Schema and class management
    - Object-oriented vector storage
    - Rich metadata and property support
    - Similarity search with filtering
    - Batch operations for efficient data loading
    - Optional dependency handling

Main Classes:
    - WeaviateStore: Main Weaviate store for vector operations
    - WeaviateClient: Weaviate client wrapper
    - WeaviateSchema: Schema builder and validator
    - WeaviateQuery: Query builder and executor

Example Usage:
    >>> from semantica.vector_store import WeaviateStore
    >>> store = WeaviateStore(url="http://localhost:8080")
    >>> store.connect()
    >>> store.create_schema("Document", properties=[{"name": "text", "dataType": "text"}])
    >>> collection = store.get_collection("Document")
    >>> object_ids = store.add_objects(objects, vectors=vectors)
    >>> results = store.query_vectors(query_vector, limit=10, where={"category": "science"})
    >>> results = store.graphql_query("{Get {Document {text}}}")

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Union

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Optional Weaviate import
try:
    import weaviate
    from weaviate.classes.query import MetadataQuery, QueryReturn

    WEAVIATE_AVAILABLE = True
except (ImportError, OSError):
    WEAVIATE_AVAILABLE = False
    weaviate = None
    MetadataQuery = None
    QueryReturn = None


class WeaviateClient:
    """Weaviate client wrapper."""

    def __init__(self, client: Any):
        """Initialize Weaviate client wrapper."""
        self.client = client
        self.logger = get_logger("weaviate_client")

    def create_class(self, class_name: str, schema: Dict[str, Any], **options) -> bool:
        """Create a class (collection) in Weaviate."""
        if not WEAVIATE_AVAILABLE:
            raise ProcessingError("Weaviate not available")

        try:
            # Convert schema to Weaviate format
            class_obj = self.client.collections.create(
                name=class_name,
                vectorizer_config=weaviate.classes.config.Configure.vectorizer.none(),
                **schema,
                **options,
            )
            return True
        except Exception as e:
            raise ProcessingError(f"Failed to create class: {str(e)}")

    def get_collection(self, class_name: str) -> Any:
        """Get collection by class name."""
        if not WEAVIATE_AVAILABLE:
            raise ProcessingError("Weaviate not available")

        try:
            return self.client.collections.get(class_name)
        except Exception as e:
            raise ProcessingError(f"Failed to get collection: {str(e)}")

    def query_graphql(self, query: str, **options) -> Dict[str, Any]:
        """Execute GraphQL query."""
        if not WEAVIATE_AVAILABLE:
            raise ProcessingError("Weaviate not available")

        try:
            result = self.client.query.raw(query)
            return result
        except Exception as e:
            raise ProcessingError(f"Failed to execute GraphQL query: {str(e)}")


class WeaviateSchema:
    """Weaviate schema builder."""

    @staticmethod
    def build_schema(
        class_name: str,
        properties: List[Dict[str, Any]],
        vectorizer: Optional[str] = None,
        **options,
    ) -> Dict[str, Any]:
        """Build Weaviate schema."""
        schema = {"class": class_name, "properties": properties}

        if vectorizer:
            schema["vectorizer"] = vectorizer

        return schema

    @staticmethod
    def build_property(
        name: str, data_type: str = "text", description: Optional[str] = None, **options
    ) -> Dict[str, Any]:
        """Build property definition."""
        prop = {"name": name, "dataType": [data_type]}

        if description:
            prop["description"] = description

        return {**prop, **options}


class WeaviateQuery:
    """Weaviate query builder."""

    def __init__(self, collection: Any):
        """Initialize Weaviate query builder."""
        self.collection = collection
        self.logger = get_logger("weaviate_query")

    def similarity_search(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        where: Optional[Dict[str, Any]] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search.

        Args:
            query_vector: Query vector
            limit: Number of results
            where: Filter conditions
            **options: Additional options

        Returns:
            List of search results
        """
        if not WEAVIATE_AVAILABLE:
            raise ProcessingError("Weaviate not available")

        try:
            response = self.collection.query.near_vector(
                near_vector=query_vector.tolist(),
                limit=limit,
                where=where,
                return_metadata=MetadataQuery(distance=True),
                **options,
            )

            results = []
            for obj in response.objects:
                results.append(
                    {
                        "id": str(obj.uuid),
                        "metadata": obj.properties if obj.properties is not None else {},
                        "distance": obj.metadata.distance if obj.metadata else None,
                        "score": 1.0 / (1.0 + max(0.0, obj.metadata.distance))
                        if obj.metadata and obj.metadata.distance is not None
                        else 1.0,
                        "vector": None,
                    }
                )

            return results

        except Exception as e:
            raise ProcessingError(f"Failed to execute similarity search: {str(e)}")

    def get_all(self, limit: int = 100, **options) -> List[Dict[str, Any]]:
        """Get all objects from collection."""
        if not WEAVIATE_AVAILABLE:
            raise ProcessingError("Weaviate not available")

        try:
            response = self.collection.query.fetch_objects(limit=limit, **options)

            results = []
            for obj in response.objects:
                results.append({"id": str(obj.uuid), "properties": obj.properties})

            return results
        except Exception as e:
            raise ProcessingError(f"Failed to get objects: {str(e)}")


class WeaviateStore:
    """
    Weaviate store for vector storage and similarity search.

    • Weaviate connection and authentication
    • Schema and class management
    • Vector storage and retrieval
    • GraphQL query support
    • Performance optimization
    • Error handling and recovery
    """

    def __init__(
        self, url: Optional[str] = None, api_key: Optional[str] = None, **config
    ):
        """Initialize Weaviate store."""
        self.logger = get_logger("weaviate_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True
        self.url = url or config.get("url", "http://localhost:8080")
        self.api_key = api_key or config.get("api_key")

        self.client: Optional[Any] = None
        self.collection: Optional[Any] = None
        self.query_builder: Optional[WeaviateQuery] = None

        # Check Weaviate availability
        if not WEAVIATE_AVAILABLE:
            self.logger.warning(
                "Weaviate not available. Install with: pip install weaviate-client"
            )

    def connect(
        self, url: Optional[str] = None, api_key: Optional[str] = None, **options
    ) -> bool:
        """
        Connect to Weaviate service.

        Args:
            url: Weaviate URL
            api_key: API key for authentication
            **options: Connection options

        Returns:
            True if connected successfully
        """
        if not WEAVIATE_AVAILABLE:
            raise ProcessingError(
                "Weaviate is not available. Install it with: pip install weaviate-client"
            )

        url = url or self.url
        api_key = api_key or self.api_key

        try:
            auth_config = None
            if api_key:
                auth_config = weaviate.auth.AuthApiKey(api_key=api_key)

            self.client = weaviate.connect_to_local(
                host=url.replace("http://", "").replace("https://", ""),
                auth_credentials=auth_config,
                **options,
            )

            self.logger.info(f"Connected to Weaviate at {url}")
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to connect to Weaviate: {str(e)}")

    def create_schema(
        self,
        class_name: str,
        properties: List[Dict[str, Any]],
        vectorizer: Optional[str] = None,
        **options,
    ) -> bool:
        """
        Create Weaviate schema.

        Args:
            class_name: Name of the class
            properties: List of property definitions
            vectorizer: Vectorizer configuration
            **options: Additional options

        Returns:
            True if successful
        """
        if self.client is None:
            self.connect()

        if not WEAVIATE_AVAILABLE:
            raise ProcessingError("Weaviate not available")

        try:
            client_wrapper = WeaviateClient(self.client)
            schema = WeaviateSchema.build_schema(
                class_name, properties, vectorizer, **options
            )
            client_wrapper.create_class(class_name, schema, **options)

            self.logger.info(f"Created Weaviate schema for class: {class_name}")
            return True

        except Exception as e:
            raise ProcessingError(f"Failed to create schema: {str(e)}")

    def get_collection(self, class_name: str) -> Any:
        """
        Get collection by class name.

        Args:
            class_name: Name of the class

        Returns:
            Collection instance
        """
        if self.client is None:
            self.connect()

        if not WEAVIATE_AVAILABLE:
            raise ProcessingError("Weaviate not available")

        try:
            self.collection = self.client.collections.get(class_name)
            self.query_builder = WeaviateQuery(self.collection)
            return self.collection
        except Exception as e:
            raise ProcessingError(f"Failed to get collection: {str(e)}")

    def add_objects(
        self,
        objects: List[Dict[str, Any]],
        vectors: Optional[List[np.ndarray]] = None,
        class_name: Optional[str] = None,
        **options,
    ) -> List[str]:
        """
        Add objects to Weaviate.

        Args:
            objects: List of objects with properties
            vectors: Optional list of vectors
            class_name: Class name (if not using default collection)
            **options: Additional options

        Returns:
            List of object IDs
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="WeaviateStore",
            message=f"Adding {len(objects)} objects to Weaviate",
        )

        try:
            if self.collection is None and class_name:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Getting collection..."
                )
                self.get_collection(class_name)

            if self.collection is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Collection not initialized"
                )
                raise ProcessingError(
                    "Collection not initialized. Call get_collection() first."
                )

            if not WEAVIATE_AVAILABLE:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Weaviate not available"
                )
                raise ProcessingError("Weaviate not available")

            self.progress_tracker.update_tracking(
                tracking_id, message="Adding objects in batch..."
            )
            object_ids = []

            with self.collection.batch.dynamic() as batch:
                for i, obj in enumerate(objects):
                    vector = (
                        vectors[i].tolist() if vectors and i < len(vectors) else None
                    )
                    uuid = batch.add_object(properties=obj, vector=vector, **options)
                    object_ids.append(str(uuid))

            self.logger.info(f"Added {len(objects)} objects to Weaviate")
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Added {len(objects)} objects to Weaviate",
            )
            return object_ids

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise ProcessingError(f"Failed to add objects: {str(e)}")

    def get_vector(self, vector_id: str) -> Optional[np.ndarray]:
        """Get vector by ID."""
        if self.collection is None or not WEAVIATE_AVAILABLE:
            return None
        
        try:
            # Weaviate expects a valid UUID string
            obj = self.collection.query.fetch_object_by_id(vector_id, include_vector=True)
            if obj and obj.vector:
                return np.array(obj.vector)
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get vector {vector_id}: {e}")
            return None

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata by ID."""
        if self.collection is None or not WEAVIATE_AVAILABLE:
            return None
        
        try:
            obj = self.collection.query.fetch_object_by_id(vector_id)
            if obj and obj.properties:
                return obj.properties
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get metadata for {vector_id}: {e}")
            return None

    def _build_weaviate_filter(self, filters: Dict[str, Any]) -> Any:
        """Build native Weaviate Filter object from metadata filter dictionary."""
        if not filters or not WEAVIATE_AVAILABLE:
            return None

        Filter = None
        try:
            from weaviate.classes.query import Filter
        except (ImportError, AttributeError):
            try:
                if weaviate and hasattr(weaviate, "classes") and hasattr(weaviate.classes, "query"):
                    Filter = getattr(weaviate.classes.query, "Filter", None)
            except AttributeError:
                Filter = None

        if Filter is None:
            return None

        try:
            conditions = []
            for key, value in filters.items():
                if isinstance(value, dict):
                    if "min" in value and value["min"] is not None:
                        conditions.append(Filter.by_property(key).greater_or_equal(value["min"]))
                    if "max" in value and value["max"] is not None:
                        conditions.append(Filter.by_property(key).less_or_equal(value["max"]))
                elif isinstance(value, list):
                    conditions.append(Filter.by_property(key).contains_any(value))
                else:
                    conditions.append(Filter.by_property(key).equal(value))

            if not conditions:
                return None

            weaviate_filter = conditions[0]
            for cond in conditions[1:]:
                weaviate_filter = weaviate_filter & cond

            return weaviate_filter
        except Exception as e:
            self.logger.debug(f"Could not build native Weaviate filter: {e}")
            return None

    def filter_by_metadata(
        self, filters: Dict[str, Any], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Filter stored objects by metadata in Weaviate.

        Args:
            filters: Metadata filter criteria
            limit: Maximum number of results

        Returns:
            List of matching result dicts with 'id', 'metadata', and 'vector'
        """
        if self.collection is None or not WEAVIATE_AVAILABLE:
            return []

        from .vector_store import _matches_filter

        native_filter = self._build_weaviate_filter(filters) if filters else None

        results = []
        seen_ids = set()
        after_cursor = None
        scanned_count = 0
        page_size = max(limit, 100)
        use_native_filter = native_filter is not None

        try:
            while len(results) < limit:
                kwargs = {"limit": page_size, "include_vector": True}
                if use_native_filter and native_filter is not None:
                    kwargs["filters"] = native_filter
                if after_cursor is not None:
                    kwargs["after"] = after_cursor

                try:
                    objs = self.collection.query.fetch_objects(**kwargs)
                except TypeError as te:
                    # Handle kwargs incompatibility (e.g. mock or client version without filters/after)
                    if "filters" in kwargs:
                        use_native_filter = False
                        kwargs.pop("filters", None)
                        try:
                            objs = self.collection.query.fetch_objects(**kwargs)
                        except TypeError:
                            if "after" in kwargs:
                                kwargs.pop("after", None)
                                kwargs["offset"] = scanned_count
                                try:
                                    objs = self.collection.query.fetch_objects(**kwargs)
                                except TypeError:
                                    kwargs.pop("offset", None)
                                    objs = self.collection.query.fetch_objects(**kwargs)
                    elif "after" in kwargs:
                        kwargs.pop("after", None)
                        kwargs["offset"] = scanned_count
                        try:
                            objs = self.collection.query.fetch_objects(**kwargs)
                        except TypeError:
                            kwargs.pop("offset", None)
                            objs = self.collection.query.fetch_objects(**kwargs)
                    else:
                        raise te
                except Exception as fe:
                    if use_native_filter:
                        self.logger.warning(
                            f"Native Weaviate filter query failed, falling back to paginated fetch: {fe}"
                        )
                        use_native_filter = False
                        kwargs.pop("filters", None)
                        objs = self.collection.query.fetch_objects(**kwargs)
                    else:
                        raise fe

                if not objs or not getattr(objs, "objects", None):
                    break

                batch_objects = objs.objects
                if not batch_objects:
                    break

                new_objects_found = False
                for obj in batch_objects:
                    obj_id = str(obj.uuid) if hasattr(obj, "uuid") and obj.uuid is not None else None
                    if obj_id:
                        if obj_id in seen_ids:
                            continue
                        seen_ids.add(obj_id)
                        new_objects_found = True

                    properties = getattr(obj, "properties", None) or {}
                    if _matches_filter(properties, filters):
                        vector = None
                        if hasattr(obj, "vector") and obj.vector:
                            vector = np.array(obj.vector)
                        results.append(
                            {
                                "id": obj_id,
                                "metadata": properties,
                                "vector": vector,
                            }
                        )
                        if len(results) >= limit:
                            break

                if not new_objects_found:
                    break

                scanned_count += len(batch_objects)
                if len(batch_objects) < page_size:
                    break

                last_obj = batch_objects[-1]
                if hasattr(last_obj, "uuid") and last_obj.uuid is not None:
                    after_cursor = str(last_obj.uuid)
                else:
                    break

            return results
        except Exception as e:
            self.logger.warning(f"Failed to fetch Weaviate objects by metadata filter: {e}")
            return results if results else []


    def query_vectors(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        where: Optional[Dict[str, Any]] = None,
        class_name: Optional[str] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Query similar vectors.

        Args:
            query_vector: Query vector
            limit: Number of results
            where: Filter conditions
            class_name: Class name (if not using default collection)
            **options: Additional options

        Returns:
            List of search results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="WeaviateStore",
            message=f"Querying {limit} similar vectors from Weaviate",
        )

        try:
            if self.collection is None and class_name:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Getting collection..."
                )
                self.get_collection(class_name)

            if self.query_builder is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Collection not initialized"
                )
                raise ProcessingError(
                    "Collection not initialized. Call get_collection() first."
                )

            self.progress_tracker.update_tracking(
                tracking_id, message="Performing similarity search..."
            )
            results = self.query_builder.similarity_search(
                query_vector, limit, where, **options
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Query completed: {len(results)} results",
            )
            return results
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def graphql_query(self, query: str, **options) -> Dict[str, Any]:
        """
        Execute GraphQL query.

        Args:
            query: GraphQL query string
            **options: Additional options

        Returns:
            Query results
        """
        if self.client is None:
            self.connect()

        if not WEAVIATE_AVAILABLE:
            raise ProcessingError("Weaviate not available")

        client_wrapper = WeaviateClient(self.client)
        return client_wrapper.query_graphql(query, **options)

    def get_stats(self, class_name: Optional[str] = None) -> Dict[str, Any]:
        """Get collection statistics."""
        if self.collection is None and class_name:
            self.get_collection(class_name)

        if self.collection is None:
            raise ProcessingError(
                "Collection not initialized. Call get_collection() first."
            )

        try:
            # Get approximate count
            count = len(self.query_builder.get_all(limit=10000))
            return {"object_count": count, "class_name": class_name or "default"}
        except Exception as e:
            self.logger.warning(f"Failed to get stats: {str(e)}")
            return {"status": "unknown"}
