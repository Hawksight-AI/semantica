"""
SQLite Vector Store Module using sqlite-vec

This module provides SQLite integration using the sqlite-vec extension for vector storage and
similarity search in the Semantica framework, supporting L2 and Cosine distance metrics,
dynamic JSON metadata filtering, and disk-backed persistence.

Key Features:
    - Distance metrics (Cosine, L2/Euclidean)
    - Fully persistent or in-memory SQLite storage
    - Dynamic metadata filtering using SQLite's JSON extract functions
    - Thread-safe operations via a shared connection lock, with optional WAL mode
      (pass use_wal=True) for concurrent readers
    - Strict validation of vector dimensions and table names
    - Parity with PgVectorStore interface for seamless drop-in usage

Main Classes:
    - SQLiteVecStore: Main SQLite vector store using sqlite-vec virtual tables

Example Usage:
    >>> from semantica.vector_store import SQLiteVecStore
    >>> store = SQLiteVecStore(
    ...     db_path="vectors.db",
    ...     table_name="vectors",
    ...     dimension=768,
    ...     distance_metric="cosine"
    ... )
    >>> store.add(vectors, metadata, ids)
    >>> results = store.search(query_vector, top_k=10)
    >>> store.close()

Author: Semantica Contributors
License: MIT
"""

import importlib.util
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union
from urllib.request import pathname2url

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger

# Optional sqlite-vec import
# (Loaded lazily inside SQLiteVecStore.__init__ to prevent eager loading)
sqlite_vec = None

# Availability check only (via find_spec, not an actual import) so callers and
# tests can detect whether sqlite-vec is installed without paying the load cost.
SQLITE_VEC_AVAILABLE = importlib.util.find_spec("sqlite_vec") is not None


class SQLiteVecStore:
    """
    SQLite vector store using the sqlite-vec extension for similarity search.

    - Vector storage with vec0 virtual table
    - Similarity search with L2 and Cosine metrics
    - Thread-safe query and insertion execution
    - Dynamic metadata extraction and filtering
    """

    SUPPORTED_METRICS = {"cosine", "l2"}

    def __init__(
        self,
        db_path: str,
        table_name: str,
        dimension: int,
        distance_metric: str = "cosine",
        read_only: bool = False,
        **kwargs,
    ):
        """
        Initialize SQLiteVecStore.

        Args:
            db_path: Path to SQLite database file, or ':memory:'
            table_name: Name of the virtual table to store vectors
            dimension: Vector dimension
            distance_metric: Distance metric (cosine, l2)
            read_only: Open database in read-only mode (requires existing database)
            **kwargs: Additional option parameters
                use_wal: If True, enable WAL journal mode and NORMAL synchronous
                    durability for improved write concurrency (default: False)

        Raises:
            ValidationError: If parameters are invalid
            ProcessingError: If sqlite-vec or connection load extension fails
        """
        self.logger = get_logger("sqlite_vec_store")

        # Validate dependencies and lazy load
        global sqlite_vec
        if sqlite_vec is None:
            try:
                import sqlite_vec
            except (ImportError, OSError):
                raise ProcessingError(
                    "sqlite-vec Python package is not available. "
                    "Install with: pip install sqlite-vec"
                )

        # Validate parameters
        if distance_metric.lower() not in self.SUPPORTED_METRICS:
            raise ValidationError(
                f"Unsupported distance metric: {distance_metric}. "
                f"Supported: {', '.join(self.SUPPORTED_METRICS)}"
            )

        if not self._is_safe_identifier(table_name):
            raise ValidationError(
                f"Invalid table name: {table_name!r}. "
                "Table names must start with a letter or underscore and contain "
                "only alphanumeric characters and underscores."
            )

        if not isinstance(dimension, int) or dimension <= 0:
            raise ValidationError(
                f"Dimension must be a positive integer, got: {dimension}"
            )

        self.db_path = db_path
        self.table_name = table_name
        self.dimension = dimension
        self.distance_metric = distance_metric.lower()
        self.read_only = read_only
        self.config = kwargs
        self.use_wal = kwargs.get("use_wal", False)

        # Lock to ensure thread safety when sharing a single SQLite connection
        self._lock = threading.Lock()
        self._conn = None

        # Connect to database
        self._init_connection()

        # Ensure table exists (if not read-only)
        if not self.read_only:
            self._ensure_table_exists()

        self.logger.info(
            f"Initialized SQLiteVecStore: db_path={db_path}, table={table_name}, "
            f"dimension={dimension}, metric={distance_metric}, read_only={read_only}"
        )

    def _init_connection(self):
        """Initialize database connection and load sqlite-vec extension."""
        try:
            if self.read_only:
                if self.db_path == ":memory:":
                    self._conn = sqlite3.connect(":memory:", check_same_thread=False)
                else:
                    if not os.path.exists(self.db_path):
                        raise ProcessingError(
                            f"Database file does not exist for read-only mode: {self.db_path}"
                        )
                    abs_path = os.path.abspath(self.db_path)
                    url_path = pathname2url(abs_path)
                    self._conn = sqlite3.connect(
                        f"file:{url_path}?mode=ro", uri=True, check_same_thread=False
                    )
            else:
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)

            # Enable and load extension
            try:
                self._conn.enable_load_extension(True)
                sqlite_vec.load(self._conn)
                self._conn.enable_load_extension(False)
            except AttributeError as ae:
                raise ProcessingError(
                    "SQLite load extension attribute is not available in this Python build. "
                    "Make sure you are using a Python build compiled with loadable extension support."
                ) from ae
            except Exception as e:
                raise ProcessingError(
                    f"Failed to load sqlite-vec extension: {e}"
                ) from e

            # Set WAL journal mode + NORMAL synchronous for performance and
            # concurrent readers, if configured via use_wal=True
            if self.use_wal and not self.read_only and self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")

        except (ValidationError, ProcessingError):
            if self._conn:
                self._conn.close()
            raise
        except Exception as e:
            if self._conn:
                self._conn.close()
            raise ProcessingError(f"Failed to establish SQLite connection: {e}") from e

    @contextmanager
    def _get_connection(self):
        """Get the active connection."""
        if not self._conn:
            raise ProcessingError("Database connection is closed.")
        try:
            yield self._conn
        except (ValidationError, ProcessingError):
            raise
        except Exception as e:
            raise ProcessingError("Database operation failed") from e

    def _is_safe_identifier(self, key: str) -> bool:
        """
        Validate that a string is safe to use as a SQL identifier.

        Only allows alphanumeric characters and underscores.
        """
        if not isinstance(key, str):
            return False
        if not key:
            return False
        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key))

    def _ensure_table_exists(self):
        """Ensure the vector table exists."""
        # Define vec0 virtual table
        create_table_sql = f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name} USING vec0(
                id TEXT PRIMARY KEY,
                embedding float[{self.dimension}] distance_metric={self.distance_metric},
                +metadata TEXT
            )
        """
        with self._lock, self._get_connection() as conn:
            try:
                conn.execute(create_table_sql)
                conn.commit()
                self.logger.debug(f"Virtual table {self.table_name} ensured")
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to create vec0 virtual table") from e

    def add(
        self,
        vectors: Union[List[np.ndarray], np.ndarray],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Add vectors to the store.

        Args:
            vectors: List of vectors or numpy array
            metadata: List of metadata dictionaries (one per vector)
            ids: Optional list of IDs (auto-generated if not provided)

        Returns:
            List of vector IDs

        Raises:
            ValidationError: If input dimensions or lengths don't match
            ProcessingError: If read-only mode is active or database operation fails
        """
        if self.read_only:
            raise ProcessingError("Cannot add vectors in read-only mode")

        # Convert to list if numpy array
        if isinstance(vectors, np.ndarray):
            vectors = [vectors[i] for i in range(len(vectors))]

        num_vectors = len(vectors)

        # Validate dimensions
        for i, vec in enumerate(vectors):
            if len(vec) != self.dimension:
                raise ValidationError(
                    f"Vector at index {i} has dimension {len(vec)}, "
                    f"expected {self.dimension}"
                )

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(num_vectors)]
        elif len(ids) != num_vectors:
            raise ValidationError(
                f"IDs length ({len(ids)}) must match vectors length ({num_vectors})"
            )

        # Prepare metadata
        if metadata is None:
            metadata = [{} for _ in range(num_vectors)]
        elif len(metadata) != num_vectors:
            raise ValidationError(
                f"Metadata length ({len(metadata)}) must match vectors length ({num_vectors})"
            )

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                # Run deletes first to emulate INSERT OR REPLACE / UPSERT behavior
                # Use batched deletes to avoid a massive performance bottleneck
                if ids:
                    batch_size = 1000
                    for i in range(0, len(ids), batch_size):
                        batch_ids = ids[i : i + batch_size]
                        placeholders = ",".join(["?"] * len(batch_ids))
                        cur.execute(
                            f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",
                            batch_ids,
                        )

                # Build data tuples for insert
                data_tuples = [
                    (
                        vec_id,
                        sqlite_vec.serialize_float32(vec),
                        json.dumps(meta),
                    )
                    for vec_id, vec, meta in zip(ids, vectors, metadata)
                ]

                # Bulk insert
                cur.executemany(
                    f"INSERT INTO {self.table_name} (id, embedding, metadata) VALUES (?, ?, ?)",
                    data_tuples,
                )
                conn.commit()
                cur.close()
                self.logger.info(f"Added {num_vectors} vectors")
                return ids
            except (ValidationError, ProcessingError):
                conn.rollback()
                raise
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to add vectors to database") from e

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query vector
            top_k: Number of results to return
            filter: Optional metadata filter (dict of key-value pairs)

        Returns:
            List of results with id, score (similarity), and metadata

        Raises:
            ValidationError: If query vector dimension doesn't match
            ProcessingError: If database operation fails
        """
        if len(query_vector) != self.dimension:
            raise ValidationError(
                f"Query vector has dimension {len(query_vector)}, expected {self.dimension}"
            )

        # Serialize query vector
        query_serialized = sqlite_vec.serialize_float32(query_vector)

        # Build query
        filter_conditions = []
        filter_params = []
        if filter:
            for key, value in filter.items():
                if not self._is_safe_identifier(key):
                    raise ValidationError(
                        f"Invalid filter key: {key!r}. "
                        "Keys must start with a letter or underscore and contain "
                        "only alphanumeric characters and underscores."
                    )
                filter_conditions.append(f"json_extract(metadata, '$.{key}') = ?")
                if isinstance(value, bool):
                    filter_params.append(1 if value else 0)
                else:
                    filter_params.append(value)

        where_clause = ""
        if filter_conditions:
            where_clause = " AND " + " AND ".join(filter_conditions)

        search_sql = f"""
            SELECT id, distance, metadata
            FROM {self.table_name}
            WHERE embedding MATCH ? AND k = ?{where_clause}
        """
        params = [query_serialized, top_k] + filter_params

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(search_sql, params)
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    vec_id, distance, meta_json = row
                    # Convert distance to similarity score
                    similarity = 1.0 / (1.0 + float(distance))

                    results.append(
                        {
                            "id": vec_id,
                            "score": similarity,
                            "metadata": json.loads(meta_json) if meta_json else {},
                            "vector": None,
                            "distance": None,
                        }
                    )

                return results
            except (ValidationError, ProcessingError):
                raise
            except Exception as e:
                raise ProcessingError("Failed to search vectors") from e

    def delete(self, ids: List[str]) -> bool:
        """
        Delete vectors by ID.

        Args:
            ids: List of vector IDs to delete

        Returns:
            True if successful

        Raises:
            ProcessingError: If read-only mode is active or database operation fails
        """
        if not ids:
            return True

        if self.read_only:
            raise ProcessingError("Cannot delete vectors in read-only mode")

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                batch_size = 1000
                for i in range(0, len(ids), batch_size):
                    batch_ids = ids[i : i + batch_size]
                    placeholders = ",".join(["?"] * len(batch_ids))
                    cur.execute(
                        f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",
                        batch_ids,
                    )
                conn.commit()
                cur.close()
                self.logger.info(f"Deleted vectors: {len(ids)}")
                return True
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to delete vectors") from e

    def update(
        self,
        ids: List[str],
        vectors: Optional[Union[List[np.ndarray], np.ndarray]] = None,
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Update existing vectors.

        Args:
            ids: List of vector IDs to update
            vectors: Optional new vectors
            metadata: Optional new metadata

        Returns:
            True if successful

        Raises:
            ValidationError: If input dimensions or lengths don't match
            ProcessingError: If read-only mode is active or database operation fails
        """
        if not ids:
            return True

        if self.read_only:
            raise ProcessingError("Cannot update vectors in read-only mode")

        if vectors is None and metadata is None:
            raise ValidationError(
                "Either vectors or metadata must be provided for update"
            )

        if vectors is not None:
            if isinstance(vectors, np.ndarray):
                vectors = [vectors[i] for i in range(len(vectors))]
            if len(vectors) != len(ids):
                raise ValidationError("Vectors length must match IDs length")
            for i, vec in enumerate(vectors):
                if len(vec) != self.dimension:
                    raise ValidationError(
                        f"Vector at index {i} has dimension {len(vec)}, expected {self.dimension}"
                    )

        if metadata is not None and len(metadata) != len(ids):
            raise ValidationError("Metadata length must match IDs length")

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()

                # Same columns are updated for every row, so build one
                # statement and batch it via executemany for efficiency.
                if vectors is not None and metadata is not None:
                    update_sql = f"UPDATE {self.table_name} SET embedding = ?, metadata = ? WHERE id = ?"
                    data_tuples = [
                        (sqlite_vec.serialize_float32(vectors[i]), json.dumps(metadata[i]), vec_id)
                        for i, vec_id in enumerate(ids)
                    ]
                elif vectors is not None:
                    update_sql = f"UPDATE {self.table_name} SET embedding = ? WHERE id = ?"
                    data_tuples = [
                        (sqlite_vec.serialize_float32(vectors[i]), vec_id)
                        for i, vec_id in enumerate(ids)
                    ]
                else:
                    update_sql = f"UPDATE {self.table_name} SET metadata = ? WHERE id = ?"
                    data_tuples = [
                        (json.dumps(metadata[i]), vec_id) for i, vec_id in enumerate(ids)
                    ]

                cur.executemany(update_sql, data_tuples)
                conn.commit()
                cur.close()
                self.logger.info(f"Updated {len(ids)} vectors")
                return True
            except ValidationError:
                conn.rollback()
                raise
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to update vectors") from e

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get vectors by ID.

        Args:
            ids: List of vector IDs

        Returns:
            List of dictionaries with id, vector, and metadata

        Raises:
            ProcessingError: If database operation fails
        """
        if not ids:
            return []

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                results = []
                batch_size = 1000
                for i in range(0, len(ids), batch_size):
                    batch_ids = ids[i : i + batch_size]
                    placeholders = ",".join(["?"] * len(batch_ids))
                    cur.execute(
                        f"SELECT id, embedding, metadata FROM {self.table_name} "
                        f"WHERE id IN ({placeholders})",
                        batch_ids,
                    )
                    for row in cur.fetchall():
                        vid, embedding_blob, metadata_json = row
                        vec = (
                            np.frombuffer(embedding_blob, dtype=np.float32).copy()
                            if embedding_blob
                            else None
                        )
                        meta = json.loads(metadata_json) if metadata_json else {}
                        results.append(
                            {
                                "id": vid,
                                "vector": vec,
                                "metadata": meta,
                            }
                        )
                cur.close()
                return results
            except Exception as e:
                raise ProcessingError("Failed to get vectors") from e

    def get_vector(self, vector_id: str) -> Optional[np.ndarray]:
        """Get vector by ID."""
        try:
            results = self.get([vector_id])
            if results and len(results) > 0:
                return results[0].get("vector")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get vector {vector_id}: {e}")
            return None

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata by ID."""
        try:
            results = self.get([vector_id])
            if results and len(results) > 0:
                return results[0].get("metadata")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get metadata for {vector_id}: {e}")
            return None

    def filter_by_metadata(
        self, filters: Dict[str, Any], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Filter stored vectors by metadata using SQLite JSON functions.

        Args:
            filters: Dictionary of metadata filter conditions
            limit: Maximum number of results

        Returns:
            List of results containing id, metadata, and vector
        """
        filter_conditions = []
        filter_params = []

        if filters:
            for key, value in filters.items():
                if not self._is_safe_identifier(key):
                    raise ValidationError(
                        f"Invalid filter key: {key!r}. "
                        "Keys must start with a letter or underscore and contain "
                        "only alphanumeric characters and underscores."
                    )
                if isinstance(value, dict):
                    if "min" in value and value["min"] is not None:
                        filter_conditions.append(f"CAST(json_extract(metadata, '$.{key}') AS NUMERIC) >= ?")
                        filter_params.append(value["min"])
                    if "max" in value and value["max"] is not None:
                        filter_conditions.append(f"CAST(json_extract(metadata, '$.{key}') AS NUMERIC) <= ?")
                        filter_params.append(value["max"])
                elif isinstance(value, list):
                    # If the metadata value at this key is itself a JSON array, match on
                    # intersection (mirrors the in-memory backend's set-intersection
                    # semantics); otherwise fall back to plain scalar membership. Both
                    # cases are handled uniformly via json_each: a non-array value is
                    # wrapped in a one-element array first so json_each always sees a
                    # valid JSON array to iterate.
                    placeholders = ", ".join(["?"] * len(value))
                    filter_conditions.append(
                        f"EXISTS (SELECT 1 FROM json_each("
                        f"  CASE WHEN json_type(metadata, '$.{key}') = 'array'"
                        f"       THEN json_extract(metadata, '$.{key}')"
                        f"       ELSE json_array(json_extract(metadata, '$.{key}'))"
                        f"  END"
                        f") je WHERE je.value IN ({placeholders}))"
                    )
                    filter_params.extend([str(v) if not isinstance(v, (int, float, bool)) else v for v in value])
                else:
                    filter_conditions.append(f"json_extract(metadata, '$.{key}') = ?")
                    if isinstance(value, bool):
                        filter_params.append(1 if value else 0)
                    else:
                        filter_params.append(value)

        where_clause = ""
        if filter_conditions:
            where_clause = " WHERE " + " AND ".join(filter_conditions)

        query_sql = f"""
            SELECT id, embedding, metadata
            FROM {self.table_name}
            {where_clause}
            LIMIT ?
        """
        params = filter_params + [limit]

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(query_sql, params)
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    vec_id, embedding_blob, meta_json = row
                    vec = None
                    if embedding_blob:
                        vec = np.frombuffer(embedding_blob, dtype=np.float32).copy()

                    results.append({
                        "id": vec_id,
                        "metadata": json.loads(meta_json) if meta_json else {},
                        "vector": vec
                    })
                return results
            except Exception as e:
                raise ProcessingError(f"Failed to filter by metadata: {str(e)}") from e

    def create_index(
        self,
        index_type: str = "hnsw",
        params: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create an index on the vector column.
        For SQLiteVecStore, vec0 virtual tables automatically index vectors,
        so this is a no-op that always returns True for interface parity.
        """
        self.logger.debug("create_index is a no-op for SQLiteVecStore")
        return True

    def get_stats(self) -> Dict[str, Any]:
        """
        Get store statistics.

        Returns:
            Dictionary with vector_count, dimension, and distance_metric
        """
        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                count = cur.fetchone()[0]
                cur.close()
                return {
                    "vector_count": count,
                    "dimension": self.dimension,
                    "distance_metric": self.distance_metric,
                }
            except Exception as e:
                raise ProcessingError("Failed to get store statistics") from e

    def count(self) -> int:
        """Return the exact number of vectors stored in this SQLite table.

        Executes ``SELECT COUNT(*) FROM <table>`` under the store's lock to
        guarantee a consistent, transaction-aware result.
        """
        stats = self.get_stats()
        return int(stats["vector_count"])

    def close(self):
        """Close the database connection."""
        if hasattr(self, "_lock") and self._lock:
            with self._lock:
                if hasattr(self, "_conn") and self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
        else:
            if hasattr(self, "_conn") and self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()
