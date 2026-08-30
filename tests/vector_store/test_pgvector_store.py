"""
PgVector Store Tests

This module provides comprehensive unit tests for the PgVectorStore implementation.
Tests are skipped if PostgreSQL with pgvector is not available.

To run these tests locally with Docker:
    docker run -d \
        --name pgvector-test \
        -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=test \
        -p 5432:5432 \
        ankane/pgvector:latest

    pytest tests/vector_store/test_pgvector_store.py -v

Author: Semantica Contributors
License: MIT
"""

import os
import uuid
from typing import Generator

import numpy as np
import pytest

# Check dependencies
psycopg_available = False
pgvector_available = False

try:
    import psycopg

    psycopg_available = True
except ImportError:
    try:
        import psycopg2

        psycopg_available = True
    except ImportError:
        pass

try:
    import pgvector

    pgvector_available = True
except ImportError:
    pass

# Skip all tests if dependencies not available
pytestmark = [
    pytest.mark.skipif(not psycopg_available, reason="psycopg not available"),
    pytest.mark.skipif(not pgvector_available, reason="pgvector not available"),
]

# Connection string from environment or default
TEST_CONNECTION_STRING = os.getenv(
    "TEST_PGVECTOR_URL",
    "postgresql://postgres:postgres@localhost:5432/test"
)


@pytest.fixture(scope="module")
def pg_available() -> bool:
    """Check if PostgreSQL with pgvector is available."""
    if not psycopg_available:
        return False

    try:
        if psycopg_available:
            try:
                import psycopg

                conn = psycopg.connect(TEST_CONNECTION_STRING, connect_timeout=5)
            except ImportError:
                import psycopg2

                conn = psycopg2.connect(TEST_CONNECTION_STRING, connect_timeout=5)

            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            return True
    except Exception:
        return False
    return False


@pytest.fixture
def unique_table_name() -> str:
    """Generate a unique table name for test isolation."""
    return f"test_vectors_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def store(pg_available, unique_table_name) -> Generator:
    """Create a PgVectorStore instance for testing."""
    if not pg_available:
        pytest.skip("PostgreSQL with pgvector not available")

    from semantica.vector_store.pgvector_store import PgVectorStore, psycopg_sql

    store = PgVectorStore(
        connection_string=TEST_CONNECTION_STRING,
        table_name=unique_table_name,
        dimension=128,
        distance_metric="cosine",
        pool_size=5,
    )

    yield store

    # Cleanup: Drop test table after test completes
    # Uses best-effort cleanup - failures are silently ignored since
    # this is teardown of optional test resources, not core functionality
    try:
        with store._get_connection() as conn:
            cur = conn.cursor()
            drop_sql = psycopg_sql.SQL("DROP TABLE IF EXISTS {}").format(
                psycopg_sql.Identifier(unique_table_name)
            )
            cur.execute(drop_sql)
            conn.commit()
            cur.close()
        store.close()
    except Exception:
        # Best-effort cleanup: PostgreSQL may be unavailable during teardown
        # This is expected when tests are skipped or connection is lost
        pass


class TestPgVectorStoreInit:
    """Test PgVectorStore initialization."""

    def test_init_success(self, store):
        """Test successful initialization."""
        assert store.dimension == 128
        assert store.distance_metric == "cosine"
        assert store.table_name.startswith("test_vectors_")

    def test_init_unsupported_metric(self, pg_available):
        """Test initialization with unsupported distance metric."""
        if not pg_available:
            pytest.skip("PostgreSQL not available")

        from semantica.vector_store.pgvector_store import PgVectorStore
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Unsupported distance metric"):
            PgVectorStore(
                connection_string=TEST_CONNECTION_STRING,
                table_name="test",
                dimension=128,
                distance_metric="invalid_metric",
            )

    def test_init_table_creation(self, store):
        """Test that table is created on initialization."""
        with store._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (store.table_name,))
            exists = cur.fetchone()[0]
            cur.close()
            assert exists is True


class TestPgVectorStoreAdd:
    """Test vector addition operations."""

    def test_add_single_vector(self, store):
        """Test adding a single vector."""
        vector = np.random.rand(128).astype(np.float32)
        metadata = {"source": "test", "index": 0}

        ids = store.add([vector], [metadata], ids=["vec_0"])

        assert ids == ["vec_0"]

    def test_add_multiple_vectors(self, store):
        """Test adding multiple vectors."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(5)]
        metadata = [{"index": i} for i in range(5)]

        ids = store.add(vectors, metadata)

        assert len(ids) == 5
        assert all(id.startswith("vec_") for id in ids)

    def test_add_auto_generate_ids(self, store):
        """Test that IDs are auto-generated if not provided."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(3)]

        ids = store.add(vectors)

        assert len(ids) == 3
        assert len(set(ids)) == 3  # All unique

    def test_add_wrong_dimension(self, store):
        """Test adding vector with wrong dimension."""
        from semantica.utils.exceptions import ValidationError

        vector = np.random.rand(64).astype(np.float32)  # Wrong dimension

        with pytest.raises(ValidationError, match="dimension"):
            store.add([vector])

    def test_add_no_metadata(self, store):
        """Test adding vectors without metadata."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(2)]

        ids = store.add(vectors)

        assert len(ids) == 2

    def test_add_batch_with_numpy_array(self, store):
        """Test adding vectors as numpy array."""
        vectors = np.random.rand(5, 128).astype(np.float32)

        ids = store.add(vectors)

        assert len(ids) == 5


class TestPgVectorStoreSearch:
    """Test vector search operations."""

    @pytest.fixture(autouse=True)
    def setup_vectors(self, store):
        """Setup test vectors for search tests."""
        # Create vectors that are clearly different
        vectors = []
        for i in range(10):
            vec = np.zeros(128, dtype=np.float32)
            vec[i * 12] = 1.0  # Each vector has peak at different position
            vectors.append(vec)

        metadata = [{"category": "A" if i < 5 else "B", "index": i} for i in range(10)]
        store.add(vectors, metadata)

    def test_search_basic(self, store):
        """Test basic similarity search."""
        query = np.zeros(128, dtype=np.float32)
        query[0] = 1.0  # Should match first vector

        results = store.search(query, top_k=3)

        assert len(results) == 3
        assert all("id" in r for r in results)
        assert all("score" in r for r in results)
        assert all("metadata" in r for r in results)

    def test_search_top_k(self, store):
        """Test search with different top_k values."""
        query = np.random.rand(128).astype(np.float32)

        results_5 = store.search(query, top_k=5)
        results_10 = store.search(query, top_k=10)

        assert len(results_5) == 5
        assert len(results_10) == 10

    def test_search_with_filter(self, store):
        """Test search with metadata filter."""
        query = np.zeros(128, dtype=np.float32)
        query[0] = 1.0

        results = store.search(query, top_k=10, filter={"category": "A"})

        assert len(results) <= 5  # Only 5 vectors have category A
        assert all(r["metadata"].get("category") == "A" for r in results)

    def test_search_wrong_dimension(self, store):
        """Test search with wrong query dimension."""
        from semantica.utils.exceptions import ValidationError

        query = np.random.rand(64).astype(np.float32)

        with pytest.raises(ValidationError, match="dimension"):
            store.search(query, top_k=5)

    def test_search_empty_store(self, pg_available, unique_table_name):
        """Test search on empty store."""
        if not pg_available:
            pytest.skip("PostgreSQL not available")

        from semantica.vector_store.pgvector_store import PgVectorStore

        empty_store = PgVectorStore(
            connection_string=TEST_CONNECTION_STRING,
            table_name=unique_table_name,
            dimension=128,
            distance_metric="cosine",
        )

        query = np.random.rand(128).astype(np.float32)
        results = empty_store.search(query, top_k=5)

        assert len(results) == 0

        # Cleanup: Drop test table after test completes
        # Uses best-effort cleanup - failures are silently ignored since
        # this is teardown of optional test resources
        try:
            with empty_store._get_connection() as conn:
                cur = conn.cursor()
                from semantica.vector_store.pgvector_store import psycopg_sql
                drop_sql = psycopg_sql.SQL("DROP TABLE IF EXISTS {}").format(
                    psycopg_sql.Identifier(unique_table_name)
                )
                cur.execute(drop_sql)
                conn.commit()
                cur.close()
            empty_store.close()
        except Exception:
            # Best-effort cleanup: PostgreSQL may be unavailable during teardown
            # This is expected when tests are skipped or connection is lost
            pass


class TestPgVectorStoreGet:
    """Test vector retrieval operations."""

    def test_get_existing_vectors(self, store):
        """Test getting existing vectors."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(3)]
        metadata = [{"index": i} for i in range(3)]
        ids = store.add(vectors, metadata)

        results = store.get(ids)

        assert len(results) == 3
        result_ids = {r["id"] for r in results}
        assert result_ids == set(ids)
        assert all(r["vector"] is not None for r in results)
        # Don't assume ordering - check by id
        for r in results:
            assert r["metadata"]["index"] in [0, 1, 2]

    def test_get_nonexistent_ids(self, store):
        """Test getting non-existent vector IDs."""
        results = store.get(["nonexistent_1", "nonexistent_2"])

        assert len(results) == 0

    def test_get_empty_list(self, store):
        """Test getting with empty ID list."""
        results = store.get([])

        assert results == []

    def test_get_partial_ids(self, store):
        """Test getting mix of existing and non-existing IDs."""
        vectors = [np.random.rand(128).astype(np.float32)]
        ids = store.add(vectors, [{"test": True}])

        results = store.get(ids + ["nonexistent"])

        assert len(results) == 1
        assert results[0]["id"] == ids[0]


class TestPgVectorStoreUpdate:
    """Test vector update operations."""

    def test_update_vectors(self, store):
        """Test updating vectors."""
        # Add initial vectors
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(2)]
        metadata = [{"version": 1} for _ in range(2)]
        ids = store.add(vectors, metadata)

        # Update with new vectors and metadata
        new_vectors = [np.random.rand(128).astype(np.float32) for _ in range(2)]
        new_metadata = [{"version": 2} for _ in range(2)]

        success = store.update(ids, new_vectors, new_metadata)

        assert success is True

        # Verify update
        results = store.get(ids)
        assert all(r["metadata"]["version"] == 2 for r in results)

    def test_update_metadata_only(self, store):
        """Test updating only metadata."""
        vectors = [np.random.rand(128).astype(np.float32)]
        ids = store.add(vectors, [{"tag": "original"}])

        success = store.update(ids, metadata=[{"tag": "updated"}])

        assert success is True

        results = store.get(ids)
        assert results[0]["metadata"]["tag"] == "updated"

    def test_update_vectors_only(self, store):
        """Test updating only vectors."""
        vectors = [np.random.rand(128).astype(np.float32)]
        ids = store.add(vectors, [{"tag": "keep"}])

        new_vectors = [np.random.rand(128).astype(np.float32)]
        success = store.update(ids, vectors=new_vectors)

        assert success is True

    def test_update_no_changes(self, store):
        """Test update with no changes specified."""
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="vectors or metadata"):
            store.update(["id_1"])

    def test_update_wrong_dimension(self, store):
        """Test updating with wrong vector dimension."""
        from semantica.utils.exceptions import ValidationError

        vectors = [np.random.rand(128).astype(np.float32)]
        ids = store.add(vectors)

        new_vectors = [np.random.rand(64).astype(np.float32)]  # Wrong dimension

        with pytest.raises(ValidationError, match="dimension"):
            store.update(ids, new_vectors)

    def test_update_wrong_length(self, store):
        """Test updating with mismatched IDs and vectors length."""
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="length"):
            store.update(["id_1", "id_2"], vectors=[np.random.rand(128)])


class TestPgVectorStoreDelete:
    """Test vector deletion operations."""

    def test_delete_vectors(self, store):
        """Test deleting vectors."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(3)]
        ids = store.add(vectors)

        success = store.delete(ids[:2])

        assert success is True

        # Verify deletion
        remaining = store.get(ids)
        assert len(remaining) == 1
        assert remaining[0]["id"] == ids[2]

    def test_delete_nonexistent(self, store):
        """Test deleting non-existent IDs."""
        success = store.delete(["nonexistent_id"])

        assert success is True  # Should not error

    def test_delete_empty_list(self, store):
        """Test deleting empty list."""
        success = store.delete([])

        assert success is True


class TestPgVectorStoreScan:
    """Test scan_vectors pagination."""

    def test_scan_returns_all_vectors_across_pages(self, store):
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(5)]
        ids = store.add(vectors, [{"index": i} for i in range(5)])

        seen_ids = []
        offset = 0
        while True:
            page = store.scan_vectors(offset=offset, limit=2)
            if not page:
                break
            seen_ids.extend(p["id"] for p in page)
            offset += len(page)

        assert set(seen_ids) == set(ids)
        assert len(seen_ids) == 5

    def test_scan_page_includes_vector_and_metadata(self, store):
        vectors = [np.random.rand(128).astype(np.float32)]
        ids = store.add(vectors, [{"tag": "only"}])

        page = store.scan_vectors(offset=0, limit=10)

        assert len(page) == 1
        assert page[0]["id"] == ids[0]
        assert page[0]["metadata"] == {"tag": "only"}
        assert page[0]["vector"] is not None

    def test_scan_empty_store_returns_empty_list(self, store):
        assert store.scan_vectors(offset=0, limit=10) == []

    def test_scan_zero_limit_returns_empty_list(self, store):
        store.add([np.random.rand(128).astype(np.float32)])
        assert store.scan_vectors(offset=0, limit=0) == []

    def test_scan_offset_past_end_returns_empty_list(self, store):
        store.add([np.random.rand(128).astype(np.float32)])
        assert store.scan_vectors(offset=100, limit=10) == []


class TestPgVectorStoreIndex:
    """Test index creation operations."""

    def test_create_hnsw_index(self, store):
        """Test creating HNSW index."""
        # Add some vectors first
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(100)]
        store.add(vectors)

        success = store.create_index(index_type="hnsw", params={"m": 16, "ef_construction": 64})

        assert success is True

    def test_create_ivfflat_index(self, store):
        """Test creating IVFFlat index."""
        # Add some vectors first (IVF needs at least as many vectors as lists)
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(100)]
        store.add(vectors)

        success = store.create_index(index_type="ivfflat", params={"lists": 10})

        assert success is True

    def test_create_index_idempotent(self, store):
        """Test that creating same index twice is idempotent."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(100)]
        store.add(vectors)

        store.create_index(index_type="hnsw")
        success = store.create_index(index_type="hnsw")  # Should not fail

        assert success is True

    def test_create_unsupported_index(self, store):
        """Test creating unsupported index type."""
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Unsupported index type"):
            store.create_index(index_type="invalid")

    def test_drop_index(self, store):
        """Test dropping an index."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(100)]
        store.add(vectors)
        store.create_index(index_type="hnsw")

        success = store.drop_index(index_type="hnsw")

        assert success is True


class TestPgVectorStoreStats:
    """Test statistics operations."""

    def test_get_stats(self, store):
        """Test getting store statistics."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(5)]
        store.add(vectors)

        stats = store.get_stats()

        assert stats["table_name"] == store.table_name
        assert stats["dimension"] == 128
        assert stats["distance_metric"] == "cosine"
        assert stats["vector_count"] == 5
        assert "psycopg_version" in stats
        assert "indexes" in stats

    def test_get_stats_empty(self, store):
        """Test stats for empty store."""
        stats = store.get_stats()

        assert stats["vector_count"] == 0


class TestPgVectorStoreContextManager:
    """Test context manager support."""

    def test_context_manager(self, pg_available, unique_table_name):
        """Test using store as context manager."""
        if not pg_available:
            pytest.skip("PostgreSQL not available")

        from semantica.vector_store.pgvector_store import PgVectorStore

        with PgVectorStore(
            connection_string=TEST_CONNECTION_STRING,
            table_name=unique_table_name,
            dimension=64,
            distance_metric="l2",
        ) as store:
            vectors = [np.random.rand(64).astype(np.float32)]
            ids = store.add(vectors)
            assert len(ids) == 1


class TestPgVectorStoreDistanceMetrics:
    """Test different distance metrics."""

    @pytest.fixture
    def l2_store(self, pg_available, unique_table_name):
        """Create a store with L2 distance metric."""
        if not pg_available:
            pytest.skip("PostgreSQL not available")

        from semantica.vector_store.pgvector_store import PgVectorStore, psycopg_sql

        store = PgVectorStore(
            connection_string=TEST_CONNECTION_STRING,
            table_name=f"{unique_table_name}_l2",
            dimension=64,
            distance_metric="l2",
            pool_size=5,
        )

        yield store

        # Cleanup: Drop test table after test completes
        # Uses best-effort cleanup - failures are silently ignored since
        # this is teardown of optional test resources, not core functionality
        try:
            with store._get_connection() as conn:
                cur = conn.cursor()
                drop_sql = psycopg_sql.SQL("DROP TABLE IF EXISTS {}").format(
                    psycopg_sql.Identifier(store.table_name)
                )
                cur.execute(drop_sql)
                conn.commit()
                cur.close()
            store.close()
        except Exception:
            # Best-effort cleanup: PostgreSQL may be unavailable during teardown
            # This is expected when tests are skipped or connection is lost
            pass

    def test_l2_distance_search(self, l2_store):
        """Test search with L2 distance."""
        # Create vectors with known distances
        vec1 = np.zeros(64, dtype=np.float32)
        vec1[0] = 1.0
        vec2 = np.zeros(64, dtype=np.float32)
        vec2[0] = 2.0  # L2 distance = 1.0

        l2_store.add([vec1, vec2], [{"name": "vec1"}, {"name": "vec2"}])

        query = np.zeros(64, dtype=np.float32)
        query[0] = 0.0  # Should be closest to vec1

        results = l2_store.search(query, top_k=2)

        assert len(results) == 2
        # Higher score = closer (we convert distance to similarity)
        assert results[0]["score"] > results[1]["score"]
