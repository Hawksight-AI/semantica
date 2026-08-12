"""
SQLite Vector Store Tests

This module provides comprehensive unit tests for the SQLiteVecStore implementation using sqlite-vec.
Tests are skipped if sqlite-vec is not available.

pytest tests/vector_store/test_sqlite_vec_store.py -v
"""

import os
import uuid
import numpy as np
import pytest
from typing import Generator

# Check dependencies
try:
    from semantica.vector_store.sqlite_vec_store import SQLITE_VEC_AVAILABLE
except ImportError:
    SQLITE_VEC_AVAILABLE = False

# Skip all tests in this file if sqlite-vec is not available
pytestmark = pytest.mark.skipif(
    not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available"
)


@pytest.fixture
def unique_table_name() -> str:
    """Generate a unique table name for test isolation."""
    return f"test_vectors_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def db_file(tmp_path) -> str:
    """Create a temporary database file path."""
    return str(tmp_path / "test_vectors.db")


@pytest.fixture
def store(db_file, unique_table_name) -> Generator:
    """Create a SQLiteVecStore instance for testing."""
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore

    store = SQLiteVecStore(
        db_path=db_file,
        table_name=unique_table_name,
        dimension=128,
        distance_metric="cosine",
    )

    yield store

    # Teardown
    store.close()


class TestSQLiteVecStoreInit:
    """Test SQLiteVecStore initialization."""

    def test_init_success(self, store, db_file):
        """Test successful initialization."""
        assert store.dimension == 128
        assert store.distance_metric == "cosine"
        assert store.table_name.startswith("test_vectors_")
        assert os.path.exists(db_file) or store.db_path == ":memory:"

    def test_init_unsupported_metric(self, db_file):
        """Test initialization with unsupported distance metric."""
        from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Unsupported distance metric"):
            SQLiteVecStore(
                db_path=db_file,
                table_name="test",
                dimension=128,
                distance_metric="invalid_metric",
            )

    def test_init_table_creation(self, store):
        """Test that table is created on initialization."""
        with store._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (store.table_name,),
            )
            row = cur.fetchone()
            cur.close()
            assert row is not None
            assert row[0] == store.table_name


class TestSQLiteVecStoreAdd:
    """Test vector addition operations."""

    def test_add_single_vector(self, store):
        """Test adding a single vector."""
        vector = np.random.rand(128).astype(np.float32)
        metadata = {"source": "test", "index": 0}

        ids = store.add([vector], [metadata], ids=["vec_0"])

        assert ids == ["vec_0"]

        # Retrieve and verify
        res = store.get(["vec_0"])
        assert len(res) == 1
        assert res[0]["id"] == "vec_0"
        assert np.allclose(res[0]["vector"], vector)
        assert res[0]["metadata"] == metadata

    def test_add_multiple_vectors(self, store):
        """Test adding multiple vectors."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(5)]
        metadata = [{"index": i} for i in range(5)]

        ids = store.add(vectors, metadata)

        assert len(ids) == 5
        assert all(isinstance(id_str, str) for id_str in ids)

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
        res = store.get(ids)
        assert all(r["metadata"] == {} for r in res)

    def test_add_batch_with_numpy_array(self, store):
        """Test adding vectors as numpy array."""
        vectors = np.random.rand(5, 128).astype(np.float32)

        ids = store.add(vectors)

        assert len(ids) == 5


class TestSQLiteVecStoreSearch:
    """Test vector search operations."""

    @pytest.fixture(autouse=True)
    def setup_vectors(self, store):
        """Setup test vectors for search tests."""
        vectors = []
        for i in range(10):
            vec = np.zeros(128, dtype=np.float32)
            vec[i] = 1.0  # Each vector has peak at different position
            vectors.append(vec)

        metadata = [{"category": "A" if i < 5 else "B", "index": i} for i in range(10)]
        store.add(vectors, metadata)

    def test_search_basic(self, store):
        """Test basic similarity search."""
        query = np.zeros(128, dtype=np.float32)
        query[0] = 1.0  # Should match first vector perfectly

        results = store.search(query, top_k=3)

        assert len(results) == 3
        assert all("id" in r for r in results)
        assert all("score" in r for r in results)
        assert all("metadata" in r for r in results)
        assert results[0]["score"] == pytest.approx(1.0)

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

    def test_search_empty_store(self, db_file, unique_table_name):
        """Test search on empty store."""
        from semantica.vector_store.sqlite_vec_store import SQLiteVecStore

        empty_store = SQLiteVecStore(
            db_path=db_file,
            table_name=unique_table_name + "_empty",
            dimension=128,
            distance_metric="cosine",
        )

        query = np.random.rand(128).astype(np.float32)
        results = empty_store.search(query, top_k=5)

        assert len(results) == 0
        empty_store.close()


class TestSQLiteVecStoreGet:
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


class TestSQLiteVecStoreUpdate:
    """Test vector update operations."""

    def test_update_vectors(self, store):
        """Test updating vectors."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(2)]
        metadata = [{"version": 1} for _ in range(2)]
        ids = store.add(vectors, metadata)

        new_vectors = [np.random.rand(128).astype(np.float32) for _ in range(2)]
        new_metadata = [{"version": 2} for _ in range(2)]

        success = store.update(ids, new_vectors, new_metadata)

        assert success is True

        results = store.get(ids)
        assert len(results) == 2
        assert all(r["metadata"]["version"] == 2 for r in results)
        # Compare by id rather than dict/ndarray equality
        results_by_id = {r["id"]: r for r in results}
        for vec_id, new_v in zip(ids, new_vectors):
            assert np.allclose(results_by_id[vec_id]["vector"], new_v)

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

        new_vector = np.random.rand(128).astype(np.float32)
        success = store.update(ids, vectors=[new_vector])

        assert success is True

        results = store.get(ids)
        assert np.allclose(results[0]["vector"], new_vector)
        assert results[0]["metadata"]["tag"] == "keep"


class TestSQLiteVecStoreDelete:
    """Test vector deletion operations."""

    def test_delete_vectors(self, store):
        """Test deleting vectors."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(3)]
        ids = store.add(vectors)

        # Delete two of them
        success = store.delete(ids[:2])
        assert success is True

        # Check only the third one remains
        res = store.get(ids)
        assert len(res) == 1
        assert res[0]["id"] == ids[2]

    def test_delete_empty(self, store):
        """Test deleting empty list of IDs."""
        assert store.delete([]) is True


class TestSQLiteVecStoreReadOnly:
    """Test read-only mode behavior."""

    def test_read_only_mode(self, db_file, unique_table_name):
        """Test that read-only mode restricts writes but allows reads."""
        from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
        from semantica.utils.exceptions import ProcessingError

        # 1. Create and populate database first
        store_write = SQLiteVecStore(
            db_path=db_file,
            table_name=unique_table_name,
            dimension=4,
        )
        vec = np.array([1, 2, 3, 4], dtype=np.float32)
        store_write.add([vec], ids=["v1"])
        store_write.close()

        # 2. Open in read-only mode
        store_ro = SQLiteVecStore(
            db_path=db_file,
            table_name=unique_table_name,
            dimension=4,
            read_only=True,
        )

        # Read should succeed
        results = store_ro.get(["v1"])
        assert len(results) == 1
        assert results[0]["id"] == "v1"

        # Search should succeed
        search_res = store_ro.search(np.array([1, 2, 3, 4], dtype=np.float32), top_k=1)
        assert len(search_res) == 1

        # Write should fail
        with pytest.raises(ProcessingError, match="read-only"):
            store_ro.add([vec], ids=["v2"])

        # Update should fail
        with pytest.raises(ProcessingError, match="read-only"):
            store_ro.update(["v1"], vectors=[vec])

        # Delete should fail
        with pytest.raises(ProcessingError, match="read-only"):
            store_ro.delete(["v1"])

        store_ro.close()


class TestSQLiteVecStoreStats:
    """Test store statistics retrieval."""

    def test_get_stats(self, store):
        """Test getting stats from store."""
        stats = store.get_stats()
        assert stats["vector_count"] == 0
        assert stats["dimension"] == 128
        assert stats["distance_metric"] == "cosine"

        # Add vectors and check again
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(4)]
        store.add(vectors)

        stats = store.get_stats()
        assert stats["vector_count"] == 4


class TestSQLiteVecStoreFilterByMetadata:
    """Test filter_by_metadata, including list-valued metadata handling."""

    def test_filter_exact_match(self, store):
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(2)]
        metadata = [{"category": "finance"}, {"category": "tech"}]
        ids = store.add(vectors, metadata, ids=["v1", "v2"])

        results = store.filter_by_metadata({"category": "finance"}, limit=10)

        assert [r["id"] for r in results] == ["v1"]

    def test_filter_scalar_field_against_list_filter(self, store):
        """A scalar metadata value should match via plain IN-list membership."""
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(2)]
        metadata = [{"category": "finance"}, {"category": "tech"}]
        store.add(vectors, metadata, ids=["v1", "v2"])

        results = store.filter_by_metadata({"category": ["finance", "ops"]}, limit=10)

        assert [r["id"] for r in results] == ["v1"]

    def test_filter_array_field_intersects_list_filter(self, store):
        """A list-valued metadata field must match on set intersection with the
        filter list, mirroring the in-memory backend's semantics -- not on a
        literal comparison of the whole array's JSON text against each candidate.
        """
        vectors = [np.random.rand(128).astype(np.float32) for _ in range(3)]
        metadata = [
            {"tags": ["python", "js"]},
            {"tags": ["go"]},
            {"tags": ["python", "ml"]},
        ]
        store.add(vectors, metadata, ids=["v1", "v2", "v3"])

        results = store.filter_by_metadata({"tags": ["python", "ml"]}, limit=10)

        assert {r["id"] for r in results} == {"v1", "v3"}

    def test_filter_limit_zero_returns_empty(self, store):
        vectors = [np.random.rand(128).astype(np.float32)]
        store.add(vectors, [{"category": "finance"}], ids=["v1"])

        results = store.filter_by_metadata({"category": "finance"}, limit=0)

        assert results == []
