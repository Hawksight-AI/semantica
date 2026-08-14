"""
PgVector Store Module

This module provides PostgreSQL pgvector extension integration for vector storage and
similarity search in the Semantica framework, supporting various distance metrics,
index types (IVFFlat, HNSW), and efficient vector operations with JSONB metadata.

Key Features:
    - Distance metrics (Cosine, L2/Euclidean, Inner Product)
    - Index types (IVFFlat, HNSW)
    - Connection pooling with psycopg3/psycopg2
    - JSONB metadata storage and filtering
    - Batch vector operations
    - Idempotent index creation
    - Proper error handling and clean exceptions

Main Classes:
    - PgVectorStore: Main PgVector store for vector operations

Example Usage:
    >>> from semantica.vector_store import PgVectorStore
    >>> store = PgVectorStore(
    ...     connection_string="postgresql://user:pass@localhost/db",
    ...     table_name="vectors",
    ...     dimension=768,
    ...     distance_metric="cosine"
    ... )
    >>> store.add(vectors, metadata, ids)
    >>> results = store.search(query_vector, top_k=10)
    >>> store.create_index(index_type="hnsw", params={"m": 16, "ef_construction": 64})

Author: Semantica Contributors
License: MIT
"""

import json
import re
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger

# Optional psycopg imports - prefer psycopg3, fallback to psycopg2
try:
    import psycopg
    from psycopg import sql as psycopg_sql
    from psycopg_pool import ConnectionPool

    PSYCOPG3_AVAILABLE = True
    PSYCOPG2_AVAILABLE = False
except (ImportError, OSError):
    PSYCOPG3_AVAILABLE = False
    try:
        import psycopg2
        from psycopg2 import pool
        from psycopg2 import sql as psycopg_sql

        PSYCOPG2_AVAILABLE = True
    except (ImportError, OSError):
        PSYCOPG2_AVAILABLE = False
        psycopg2 = None
        psycopg_sql = None

# Optional pgvector import
try:
    import pgvector
    from pgvector.psycopg import register_vector

    PGVECTOR_AVAILABLE = True
except (ImportError, OSError):
    PGVECTOR_AVAILABLE = False
    pgvector = None
    register_vector = None


class PgVectorStore:
    """
    PostgreSQL pgvector store for vector storage and similarity search.

    - Vector storage with pgvector extension
    - Similarity search with multiple distance metrics
    - JSONB metadata storage and filtering
    - Index creation (IVFFlat, HNSW)
    - Connection pooling
    - Batch operations support
    """

    SUPPORTED_METRICS = {"cosine", "l2", "inner_product"}
    SUPPORTED_INDEX_TYPES = {"ivfflat", "hnsw"}

    def __init__(
        self,
        connection_string: str,
        table_name: str,
        dimension: int,
        distance_metric: str = "cosine",
        **kwargs,
    ):
        """
        Initialize PgVectorStore.

        Args:
            connection_string: PostgreSQL connection string
            table_name: Name of the table to store vectors
            dimension: Vector dimension
            distance_metric: Distance metric (cosine, l2, inner_product)
            **kwargs: Additional options (pool_size, etc.)

        Raises:
            ValidationError: If distance_metric is not supported
            ProcessingError: If pgvector extension is not available
        """
        self.logger = get_logger("pgvector_store")

        # Validate dependencies
        if not PSYCOPG3_AVAILABLE and not PSYCOPG2_AVAILABLE:
            raise ProcessingError(
                "Neither psycopg3 nor psycopg2 is available. "
                "Install with: pip install psycopg[binary] or psycopg2-binary"
            )

        if not PGVECTOR_AVAILABLE:
            raise ProcessingError(
                "pgvector Python client is not available. "
                "Install with: pip install pgvector"
            )

        # Validate parameters
        if distance_metric.lower() not in self.SUPPORTED_METRICS:
            raise ValidationError(
                f"Unsupported distance metric: {distance_metric}. "
                f"Supported: {', '.join(self.SUPPORTED_METRICS)}"
            )

        self.connection_string = connection_string
        self.table_name = table_name
        self.dimension = dimension
        self.distance_metric = distance_metric.lower()
        self.config = kwargs

        # Connection pool settings
        self.pool_size = kwargs.get("pool_size", 10)
        self.max_overflow = kwargs.get("max_overflow", 10)

        # Initialize connection pool
        self._pool = None
        self._init_pool()

        # Verify pgvector extension is installed (do NOT auto-create)
        self._verify_pgvector_extension()

        # Ensure table exists
        self._ensure_table_exists()

        self.logger.info(
            f"Initialized PgVectorStore: table={table_name}, "
            f"dimension={dimension}, metric={distance_metric}"
        )

    def _init_pool(self):
        """Initialize connection pool."""
        try:
            if PSYCOPG3_AVAILABLE:
                self._pool = ConnectionPool(
                    self.connection_string,
                    min_size=1,
                    max_size=self.pool_size,
                )
            else:
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=self.pool_size,
                    dsn=self.connection_string,
                )
            self.logger.debug("Connection pool initialized")
        except Exception as e:
            raise ProcessingError("Failed to initialize database connection pool") from e

    @contextmanager
    def _get_connection(self):
        """Get a connection from the pool."""
        conn = None
        try:
            if PSYCOPG3_AVAILABLE:
                conn = self._pool.getconn()
            else:
                conn = self._pool.getconn()
            # Register pgvector adapters for this connection
            if register_vector:
                register_vector(conn)
            yield conn
        except (ValidationError, ProcessingError):
            # Re-raise framework exceptions without wrapping
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            raise ProcessingError("Database connection error") from e
        finally:
            if conn:
                if PSYCOPG3_AVAILABLE:
                    self._pool.putconn(conn)
                else:
                    self._pool.putconn(conn)

    def _verify_pgvector_extension(self):
        """Verify pgvector extension is installed. Fail clearly if not."""
        with self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                result = cur.fetchone()
                cur.close()

                if not result:
                    raise ProcessingError(
                        "pgvector extension is not installed in PostgreSQL. "
                        "Please install it first: https://github.com/pgvector/pgvector#installation"
                    )
                self.logger.debug("pgvector extension verified")
            except Exception as e:
                if "pgvector extension is not installed" in str(e):
                    raise
                raise ProcessingError("Failed to verify pgvector extension") from e

    def _ensure_table_exists(self):
        """Ensure the vector table exists."""
        # Use safe SQL composition with identifiers
        if PSYCOPG3_AVAILABLE:
            create_table_sql = psycopg_sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    id TEXT PRIMARY KEY,
                    vector VECTOR({}),
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """).format(
                psycopg_sql.Identifier(self.table_name),
                psycopg_sql.Literal(self.dimension)
            )
        else:
            # psycopg2 requires different approach - use %s for literals in composition
            create_table_sql = psycopg_sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    id TEXT PRIMARY KEY,
                    vector VECTOR(%s),
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """).format(psycopg_sql.Identifier(self.table_name))

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()
                if PSYCOPG3_AVAILABLE:
                    cur.execute(create_table_sql)
                else:
                    cur.execute(create_table_sql, (self.dimension,))
                conn.commit()
                cur.close()
                self.logger.debug(f"Table {self.table_name} ensured")
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to create table") from e

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
            ValidationError: If input dimensions don't match
            ProcessingError: If database operation fails
        """
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

        # Generate IDs if not provided - use UUID4 for collision safety
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(num_vectors)]

        # Prepare metadata
        if metadata is None:
            metadata = [{} for _ in range(num_vectors)]
        elif len(metadata) != num_vectors:
            raise ValidationError(
                f"Metadata length ({len(metadata)}) must match vectors length ({num_vectors})"
            )

        # Batch insert using safe SQL composition with executemany() for efficiency
        # Build data tuples for batch insert
        data_tuples = [
            (vec_id, vec.tolist() if isinstance(vec, np.ndarray) else list(vec), json.dumps(meta))
            for vec_id, vec, meta in zip(ids, vectors, metadata)
        ]

        insert_sql = psycopg_sql.SQL("""
            INSERT INTO {} (id, vector, metadata)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                vector = EXCLUDED.vector,
                metadata = EXCLUDED.metadata
        """).format(psycopg_sql.Identifier(self.table_name))

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()
                # Use executemany for batch insert optimization
                cur.executemany(insert_sql, data_tuples)
                conn.commit()
                cur.close()
                self.logger.info(f"Added {num_vectors} vectors")
                return ids
            except (ValidationError, ProcessingError):
                conn.rollback()
                raise
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to add vectors") from e

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
            List of results with id, score, and metadata

        Raises:
            ValidationError: If query vector dimension doesn't match
            ProcessingError: If database operation fails
        """
        if len(query_vector) != self.dimension:
            raise ValidationError(
                f"Query vector has dimension {len(query_vector)}, expected {self.dimension}"
            )

        # Determine operator based on distance metric
        operator_map = {
            "cosine": "<=>",  # cosine distance
            "l2": "<->",  # L2 distance
            "inner_product": "<#>",  # negative inner product (for ordering)
        }
        op = operator_map[self.distance_metric]

        # Build query
        query_list = query_vector.tolist() if isinstance(query_vector, np.ndarray) else list(query_vector)

        if filter:
            # Build metadata filter condition with safe key validation
            filter_conditions = []
            filter_values = []
            for key, value in filter.items():
                # Validate key is safe to prevent SQL injection
                if not self._is_safe_identifier(key):
                    raise ValidationError(
                        f"Invalid filter key: {key!r}. "
                        "Keys must be alphanumeric with underscores/hyphens only."
                    )
                filter_conditions.append(psycopg_sql.SQL("metadata->>{} = %s").format(
                    psycopg_sql.Literal(key)
                ))
                filter_values.append(str(value))

            where_clause = psycopg_sql.SQL(" AND ").join(filter_conditions)
            
            search_sql = psycopg_sql.SQL("""
                SELECT id, vector {op} %s::vector AS score, metadata
                FROM {table}
                WHERE {where}
                ORDER BY vector {op} %s::vector
                LIMIT %s
            """).format(
                op=psycopg_sql.SQL(op),
                table=psycopg_sql.Identifier(self.table_name),
                where=where_clause
            )
            params = [query_list] + filter_values + [query_list, top_k]
        else:
            search_sql = psycopg_sql.SQL("""
                SELECT id, vector {op} %s::vector AS score, metadata
                FROM {table}
                ORDER BY vector {op} %s::vector
                LIMIT %s
            """).format(
                op=psycopg_sql.SQL(op),
                table=psycopg_sql.Identifier(self.table_name)
            )
            params = [query_list, query_list, top_k]

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(search_sql, params)
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    vec_id, score, meta = row
                    # Convert distance to similarity score
                    if self.distance_metric in ("cosine", "l2"):
                        # Lower distance = higher similarity
                        similarity = 1.0 / (1.0 + float(score))
                    else:  # inner_product
                        # Negative because we used <#> operator
                        similarity = -float(score)

                    results.append({
                        "id": vec_id,
                        "score": similarity,
                        "metadata": meta if isinstance(meta, dict) else json.loads(meta),
                        "vector": None,
                        "distance": None,
                    })

                return results
            except (ValidationError, ProcessingError):
                raise
            except Exception as e:
                raise ProcessingError("Failed to search vectors") from e

    def _is_safe_identifier(self, key: str) -> bool:
        """
        Validate that a string is safe to use as a SQL/jsonb identifier.

        Only allows alphanumeric characters, underscores, and hyphens.
        Rejects any string that could be used for SQL injection.
        """
        if not isinstance(key, str):
            return False
        if not key:
            return False
        # Only allow: alphanumeric, underscore, hyphen
        # Must start with letter or underscore
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_-]*$', key))

    def delete(self, ids: List[str]) -> bool:
        """
        Delete vectors by ID.

        Args:
            ids: List of vector IDs to delete

        Returns:
            True if successful

        Raises:
            ProcessingError: If database operation fails
        """
        if not ids:
            return True

        # Use safe SQL composition for table name
        delete_sql = psycopg_sql.SQL("DELETE FROM {} WHERE id = ANY(%s)").format(
            psycopg_sql.Identifier(self.table_name)
        )

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(delete_sql, (ids,))
                conn.commit()
                deleted_count = cur.rowcount
                cur.close()
                self.logger.info(f"Deleted {deleted_count} vectors")
                return True
            except (ValidationError, ProcessingError):
                conn.rollback()
                raise
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
            ValidationError: If input dimensions don't match
            ProcessingError: If database operation fails
        """
        if not ids:
            return True

        if vectors is None and metadata is None:
            raise ValidationError("Either vectors or metadata must be provided for update")

        if vectors is not None:
            if isinstance(vectors, np.ndarray):
                vectors = [vectors[i] for i in range(len(vectors))]
            if len(vectors) != len(ids):
                raise ValidationError("Vectors length must match IDs length")

        if metadata is not None and len(metadata) != len(ids):
            raise ValidationError("Metadata length must match IDs length")

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()

                for i, vec_id in enumerate(ids):
                    updates = []
                    params = []

                    if vectors is not None:
                        vec = vectors[i]
                        if len(vec) != self.dimension:
                            raise ValidationError(
                                f"Vector at index {i} has dimension {len(vec)}, expected {self.dimension}"
                            )
                        vec_list = vec.tolist() if isinstance(vec, np.ndarray) else list(vec)
                        updates.append(psycopg_sql.SQL("vector = %s"))
                        params.append(vec_list)

                    if metadata is not None:
                        updates.append(psycopg_sql.SQL("metadata = %s"))
                        params.append(json.dumps(metadata[i]))

                    # Build safe UPDATE query
                    update_sql = psycopg_sql.SQL("""
                        UPDATE {}
                        SET {}
                        WHERE id = %s
                    """).format(
                        psycopg_sql.Identifier(self.table_name),
                        psycopg_sql.SQL(", ").join(updates)
                    )
                    params.append(vec_id)
                    cur.execute(update_sql, params)

                conn.commit()
                cur.close()
                self.logger.info(f"Updated {len(ids)} vectors")
                return True
            except (ValidationError, ProcessingError):
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

        # Use safe SQL composition for table name
        get_sql = psycopg_sql.SQL("""
            SELECT id, vector, metadata
            FROM {}
            WHERE id = ANY(%s)
        """).format(psycopg_sql.Identifier(self.table_name))

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(get_sql, (ids,))
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    vec_id, vec, meta = row
                    results.append({
                        "id": vec_id,
                        "vector": np.array(vec) if vec else None,
                        "metadata": meta if isinstance(meta, dict) else json.loads(meta) if meta else {},
                    })

                return results
            except (ValidationError, ProcessingError):
                raise
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
        Filter stored vectors by metadata using PostgreSQL JSONB queries.

        Args:
            filters: Dictionary of metadata filter conditions
            limit: Maximum number of results

        Returns:
            List of results containing id, metadata, and vector
        """
        if not PSYCOPG3_AVAILABLE and not PSYCOPG2_AVAILABLE:
            raise ProcessingError(
                "Neither psycopg3 nor psycopg2 is available. "
                "Install with: pip install psycopg[binary] or psycopg2-binary"
            )

        filter_conditions = []
        filter_values = []

        if filters:
            for key, value in filters.items():
                if not self._is_safe_identifier(key):
                    raise ValidationError(
                        f"Invalid filter key: {key!r}. "
                        "Keys must be alphanumeric with underscores/hyphens only."
                    )
                if isinstance(value, dict):
                    if "min" in value and value["min"] is not None:
                        filter_conditions.append(psycopg_sql.SQL("(metadata->>{})::numeric >= %s").format(
                            psycopg_sql.Literal(key)
                        ))
                        filter_values.append(value["min"])
                    if "max" in value and value["max"] is not None:
                        filter_conditions.append(psycopg_sql.SQL("(metadata->>{})::numeric <= %s").format(
                            psycopg_sql.Literal(key)
                        ))
                        filter_values.append(value["max"])
                elif isinstance(value, list):
                    # Same lowercase-bool rule as the scalar branch below: ->> renders
                    # JSON booleans as 'true'/'false', not str()'s 'True'/'False'.
                    str_values = [
                        ('true' if v else 'false') if isinstance(v, bool) else str(v)
                        for v in value
                    ]
                    # If the metadata value at this key is itself a JSON array, match on
                    # intersection (mirrors the in-memory backend's set-intersection
                    # semantics) via the jsonb `?|` "any array element matches" operator;
                    # otherwise fall back to plain scalar membership. `->>` renders an
                    # array as its whole text representation, so it cannot be reused for
                    # the array case.
                    filter_conditions.append(psycopg_sql.SQL(
                        "(CASE WHEN jsonb_typeof(metadata->{0}) = 'array' "
                        "THEN metadata->{0} ?| %s "
                        "ELSE metadata->>{0} = ANY(%s) END)"
                    ).format(psycopg_sql.Literal(key)))
                    filter_values.append(str_values)
                    filter_values.append(str_values)
                elif isinstance(value, bool):
                    # PostgreSQL JSONB ->> returns lowercase 'true'/'false' for JSON booleans.
                    # str(True)='True' and str(False)='False' would never match; use the
                    # correct lowercase text that ->> actually produces.
                    filter_conditions.append(psycopg_sql.SQL("metadata->>{} = %s").format(
                        psycopg_sql.Literal(key)
                    ))
                    filter_values.append('true' if value else 'false')
                else:
                    filter_conditions.append(psycopg_sql.SQL("metadata->>{} = %s").format(
                        psycopg_sql.Literal(key)
                    ))
                    filter_values.append(str(value))

        if filter_conditions:
            where_clause = psycopg_sql.SQL(" WHERE ") + psycopg_sql.SQL(" AND ").join(filter_conditions)
        else:
            where_clause = psycopg_sql.SQL("")

        query_sql = psycopg_sql.SQL("""
            SELECT id, vector, metadata
            FROM {table}
            {where}
            LIMIT %s
        """).format(
            table=psycopg_sql.Identifier(self.table_name),
            where=where_clause
        )
        params = filter_values + [limit]

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(query_sql, params)
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    vec_id, vector_data, meta = row
                    vec = np.array(vector_data) if vector_data is not None else None
                    results.append({
                        "id": vec_id,
                        "metadata": meta if isinstance(meta, dict) else json.loads(meta) if meta else {},
                        "vector": vec
                    })
                return results
            except Exception as e:
                raise ProcessingError(f"Failed to filter vectors by metadata: {str(e)}") from e

    def create_index(
        self,
        index_type: str = "hnsw",
        params: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create an index on the vector column. Idempotent - safe to call multiple times.

        Args:
            index_type: Index type (ivfflat, hnsw)
            params: Index-specific parameters
                For IVFFlat: {"lists": 100}
                For HNSW: {"m": 16, "ef_construction": 64}

        Returns:
            True if successful

        Raises:
            ValidationError: If index_type is not supported
            ProcessingError: If database operation fails
        """
        index_type = index_type.lower()
        if index_type not in self.SUPPORTED_INDEX_TYPES:
            raise ValidationError(
                f"Unsupported index type: {index_type}. "
                f"Supported: {', '.join(self.SUPPORTED_INDEX_TYPES)}"
            )

        params = params or {}
        # Use safe identifier for index name
        index_name = f"{self.table_name}_vector_{index_type}_idx"

        # Determine distance function
        distance_map = {
            "cosine": "vector_cosine_ops",
            "l2": "vector_l2_ops",
            "inner_product": "vector_ip_ops",
        }
        ops = distance_map[self.distance_metric]

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()

                # Check if index already exists
                cur.execute("""
                    SELECT indexname FROM pg_indexes
                    WHERE indexname = %s AND tablename = %s
                """, (index_name, self.table_name))

                if cur.fetchone():
                    self.logger.info(f"Index {index_name} already exists")
                    cur.close()
                    return True

                # Build index creation SQL with safe composition
                if index_type == "ivfflat":
                    lists = params.get("lists", 100)
                    # Validate lists is a positive integer
                    if not isinstance(lists, int) or lists <= 0:
                        raise ValidationError("lists must be a positive integer")
                    create_sql = psycopg_sql.SQL("""
                        CREATE INDEX {}
                        ON {}
                        USING ivfflat (vector {})
                        WITH (lists = {})
                    """).format(
                        psycopg_sql.Identifier(index_name),
                        psycopg_sql.Identifier(self.table_name),
                        psycopg_sql.SQL(ops),
                        psycopg_sql.Literal(lists)
                    )
                elif index_type == "hnsw":
                    m = params.get("m", 16)
                    ef_construction = params.get("ef_construction", 64)
                    # Validate params are positive integers
                    if not isinstance(m, int) or m <= 0:
                        raise ValidationError("m must be a positive integer")
                    if not isinstance(ef_construction, int) or ef_construction <= 0:
                        raise ValidationError("ef_construction must be a positive integer")
                    create_sql = psycopg_sql.SQL("""
                        CREATE INDEX {}
                        ON {}
                        USING hnsw (vector {})
                        WITH (m = {}, ef_construction = {})
                    """).format(
                        psycopg_sql.Identifier(index_name),
                        psycopg_sql.Identifier(self.table_name),
                        psycopg_sql.SQL(ops),
                        psycopg_sql.Literal(m),
                        psycopg_sql.Literal(ef_construction)
                    )

                if PSYCOPG3_AVAILABLE:
                    cur.execute(create_sql)
                else:
                    cur.execute(create_sql)
                conn.commit()
                cur.close()
                self.logger.info(f"Created {index_type} index: {index_name}")
                return True
            except (ValidationError, ProcessingError):
                conn.rollback()
                raise
            except Exception as e:
                conn.rollback()
                # If index already exists (race condition), consider it success
                if "already exists" in str(e).lower():
                    self.logger.info(f"Index {index_name} already exists (race condition)")
                    return True
                raise ProcessingError("Failed to create index") from e

    def drop_index(self, index_type: str = "hnsw") -> bool:
        """
        Drop a vector index.

        Args:
            index_type: Index type (ivfflat, hnsw)

        Returns:
            True if successful
        """
        # Use safe identifier for index name
        index_name = f"{self.table_name}_vector_{index_type}_idx"

        with self._get_connection() as conn:
            try:
                cur = conn.cursor()
                drop_sql = psycopg_sql.SQL("DROP INDEX IF EXISTS {}").format(
                    psycopg_sql.Identifier(index_name)
                )
                cur.execute(drop_sql)
                conn.commit()
                cur.close()
                self.logger.info(f"Dropped index: {index_name}")
                return True
            except (ValidationError, ProcessingError):
                conn.rollback()
                raise
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to drop index") from e

    def get_stats(self) -> Dict[str, Any]:
        """
        Get store statistics.

        Returns:
            Dictionary with statistics
        """
        with self._get_connection() as conn:
            try:
                cur = conn.cursor()

                # Get row count using safe SQL composition
                count_sql = psycopg_sql.SQL("SELECT COUNT(*) FROM {}").format(
                    psycopg_sql.Identifier(self.table_name)
                )
                cur.execute(count_sql)
                count = cur.fetchone()[0]

                # Get index info
                cur.execute("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = %s
                """, (self.table_name,))
                indexes = [{"name": row[0], "definition": row[1]} for row in cur.fetchall()]

                cur.close()

                return {
                    "table_name": self.table_name,
                    "dimension": self.dimension,
                    "distance_metric": self.distance_metric,
                    "vector_count": count,
                    "indexes": indexes,
                    "psycopg_version": "3" if PSYCOPG3_AVAILABLE else "2",
                }
            except (ValidationError, ProcessingError):
                raise
            except Exception as e:
                raise ProcessingError("Failed to get stats") from e

    def count(self) -> int:
        """Return the exact number of vectors stored in this PostgreSQL table.

        Executes ``SELECT COUNT(*) FROM <table>`` — always reflects the
        committed state of the table, including any deletes or updates.
        """
        stats = self.get_stats()
        return int(stats["vector_count"])

    def close(self):
        """Close the connection pool."""
        if self._pool:
            if PSYCOPG3_AVAILABLE:
                self._pool.close()
            else:
                self._pool.closeall()
            self.logger.info("Connection pool closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
