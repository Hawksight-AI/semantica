"""Regression tests for #855 / #914: VectorManager persistent-backend crash.

VectorManager.maintain_store() and collect_statistics() used to reach
into VectorStore internals (``.vectors`` / ``.metadata``), which only
exist for the inmemory backend — any persistent backend (FAISS, Qdrant,
Pinecone, Milvus, SQLite, PgVector, Weaviate) crashed with AttributeError.
Both methods now go through the public backend-agnostic
``VectorStore.count()`` accessor.

Phase 1 (PR #855): dispatch fix + NotImplementedError instead of
AttributeError for backends that don't implement count().

Phase 2 (PR #914): count() added to FAISSStore, SQLiteVecStore, and
PgVectorStore — the three backends whose storage contracts guarantee a
reliable, synchronous count.  maintain_store() revised so the
persistent-backend path no longer manufactures a vacuous
``metadata_count == vector_count`` tautology; instead it returns
``metadata_count=None`` and delegates healthiness to whether the store is
reachable.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from semantica.vector_store.vector_store import VectorStore, VectorManager


# ---------------------------------------------------------------------------
# Minimal fake backend stores for dispatch-level unit tests
# ---------------------------------------------------------------------------

class _CountingBackendStore:
    """Fake persistent backend store that supports count()."""

    def __init__(self, n: int):
        self._n = n

    def count(self) -> int:
        return self._n


class _NonCountingBackendStore:
    """Fake persistent backend store without any count capability."""


class _MisShapedBackendStore:
    """Backend store whose ``count`` attribute is not callable."""

    count = 42  # plain attribute, not a method


# ---------------------------------------------------------------------------
# VectorStore.count() dispatch tests
# ---------------------------------------------------------------------------

class VectorStoreCountTests(unittest.TestCase):
    """VectorStore.count() backend-agnostic accessor — dispatch logic."""

    def setUp(self):
        self.vectors = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
        self.metadata = [{"type": "a"}, {"type": "b"}]

    def test_count_inmemory(self):
        store = VectorStore(backend="inmemory", dimension=2)
        store.store_vectors(self.vectors, self.metadata)
        self.assertEqual(store.count(), 2)

    def test_count_empty_inmemory(self):
        store = VectorStore(backend="inmemory", dimension=2)
        self.assertEqual(store.count(), 0)

    def test_count_delegates_to_backend_store(self):
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = "faiss"
        store._backend_store = _CountingBackendStore(7)
        self.assertEqual(store.count(), 7)

    def test_count_raises_not_implemented_without_backend_support(self):
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = "faiss"
        store._backend_store = _NonCountingBackendStore()
        with self.assertRaises(NotImplementedError):
            store.count()

    def test_count_raises_when_persistent_backend_not_initialized(self):
        # A persistent backend with no wrapped store must not silently
        # report 0 — that masks a missing initialization as an empty,
        # healthy store.  Follow the get_vector()/get_metadata() precedent.
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = "faiss"
        store._backend_store = None
        with self.assertRaises(NotImplementedError):
            store.count()

    def test_count_raises_when_backend_count_not_callable(self):
        # A mis-shaped adapter exposing a non-callable ``count`` attribute
        # must surface a clean NotImplementedError, not a TypeError.
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = "faiss"
        store._backend_store = _MisShapedBackendStore()
        with self.assertRaises(NotImplementedError):
            store.count()

    def test_count_not_implemented_message_describes_requirement(self):
        """Error message should explain *how* to fix it, not claim only
        inmemory works (the old misleading message)."""
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = "qdrant"
        store._backend_store = _NonCountingBackendStore()
        with self.assertRaises(NotImplementedError) as ctx:
            store.count()
        msg = str(ctx.exception)
        # Must not claim inmemory is the only backend that works
        self.assertNotIn("only supported for the inmemory", msg)
        # Must point at what to implement
        self.assertIn("count()", msg)


# ---------------------------------------------------------------------------
# VectorManager tests — inmemory backend
# ---------------------------------------------------------------------------

class VectorManagerInmemoryTests(unittest.TestCase):
    """VectorManager with the inmemory backend — full integrity semantics."""

    def setUp(self):
        self.vectors = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
        self.metadata = [{"type": "a"}, {"type": "b"}]
        self.manager = VectorManager()

    def _store(self):
        store = VectorStore(backend="inmemory", dimension=2)
        store.store_vectors(self.vectors, self.metadata)
        return store

    def test_collect_statistics_inmemory(self):
        stats = self.manager.collect_statistics(self._store())
        self.assertEqual(stats["total_vectors"], 2)
        self.assertEqual(stats["dimension"], 2)
        self.assertEqual(stats["backend"], "inmemory")

    def test_collect_statistics_empty_inmemory(self):
        store = VectorStore(backend="inmemory", dimension=2)
        stats = self.manager.collect_statistics(store)
        self.assertEqual(stats["total_vectors"], 0)

    def test_maintain_store_inmemory_healthy(self):
        health = self.manager.maintain_store(self._store())
        self.assertTrue(health["healthy"])
        self.assertEqual(health["vector_count"], 2)
        self.assertEqual(health["metadata_count"], 2)

    def test_maintain_store_inmemory_empty(self):
        store = VectorStore(backend="inmemory", dimension=2)
        health = self.manager.maintain_store(store)
        self.assertTrue(health["healthy"])
        self.assertEqual(health["vector_count"], 0)
        self.assertEqual(health["metadata_count"], 0)

    def test_maintain_store_inmemory_detects_divergence(self):
        """Artificially diverge vectors and metadata — must report unhealthy."""
        store = VectorStore(backend="inmemory", dimension=2)
        store.store_vectors(self.vectors, self.metadata)
        # Inject an extra metadata entry with no matching vector
        store.metadata["orphan"] = {"type": "orphan"}
        health = self.manager.maintain_store(store)
        self.assertFalse(health["healthy"])
        self.assertEqual(health["vector_count"], 2)
        self.assertEqual(health["metadata_count"], 3)


# ---------------------------------------------------------------------------
# VectorManager tests — persistent backends (dispatch level)
# ---------------------------------------------------------------------------

class VectorManagerPersistentDispatchTests(unittest.TestCase):
    """VectorManager with fake persistent backends — dispatch/contract tests."""

    def setUp(self):
        self.vectors = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
        self.metadata = [{"type": "a"}, {"type": "b"}]
        self.manager = VectorManager()

    def _persistent_store(self, backend_store, backend_name="faiss"):
        """Create a VectorStore instance whose backend is swapped to a fake."""
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = backend_name
        store._backend_store = backend_store
        return store

    # -- collect_statistics --------------------------------------------------

    def test_collect_statistics_persistent_with_count(self):
        store = self._persistent_store(_CountingBackendStore(5))
        stats = self.manager.collect_statistics(store)
        self.assertEqual(stats["total_vectors"], 5)
        self.assertEqual(stats["dimension"], 2)
        self.assertEqual(stats["backend"], "faiss")

    def test_collect_statistics_persistent_without_count_raises(self):
        """Must raise NotImplementedError, not AttributeError (#855)."""
        store = self._persistent_store(_NonCountingBackendStore())
        with self.assertRaises(NotImplementedError):
            self.manager.collect_statistics(store)

    # -- maintain_store ------------------------------------------------------

    def test_maintain_store_persistent_with_count(self):
        store = self._persistent_store(_CountingBackendStore(5))
        health = self.manager.maintain_store(store)
        self.assertTrue(health["healthy"])
        self.assertEqual(health["vector_count"], 5)
        # Persistent backends cannot independently verify metadata count.
        self.assertIsNone(health["metadata_count"])

    def test_maintain_store_persistent_metadata_count_is_none_not_vacuous(self):
        """Regression for Qodo review #914: maintain_store must not
        manufacture metadata_count = vector_count to force healthy=True.
        The only way to confirm metadata integrity for a persistent backend
        is through the backend itself, so metadata_count must be None.
        """
        store = self._persistent_store(_CountingBackendStore(3))
        health = self.manager.maintain_store(store)
        # metadata_count must be None — never equal to vector_count because
        # we didn't actually verify it; we simply don't have the information.
        self.assertIsNone(health["metadata_count"])
        # vector_count comes from the real count() call, not fabricated.
        self.assertEqual(health["vector_count"], 3)

    def test_maintain_store_persistent_without_count_raises(self):
        """Must raise NotImplementedError, not AttributeError (#855)."""
        store = self._persistent_store(_NonCountingBackendStore())
        with self.assertRaises(NotImplementedError):
            self.manager.maintain_store(store)

    def test_maintain_store_persistent_not_initialized_raises(self):
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = "qdrant"
        store._backend_store = None
        with self.assertRaises(NotImplementedError):
            self.manager.maintain_store(store)

    def test_maintain_store_zero_count_not_confused_with_unhealthy(self):
        """An empty but reachable persistent store is healthy (count=0)."""
        store = self._persistent_store(_CountingBackendStore(0))
        health = self.manager.maintain_store(store)
        self.assertTrue(health["healthy"])
        self.assertEqual(health["vector_count"], 0)
        self.assertIsNone(health["metadata_count"])


# ---------------------------------------------------------------------------
# FAISSStore.count() — unit tests with mocked faiss
# ---------------------------------------------------------------------------

class FAISSStoreCountTests(unittest.TestCase):
    """FAISSStore.count() returns len(index.vector_ids)."""

    @patch("semantica.vector_store.faiss_store.faiss")
    @patch("semantica.vector_store.faiss_store.FAISS_AVAILABLE", True)
    def test_count_after_add(self, mock_faiss):
        from semantica.vector_store.faiss_store import FAISSStore

        mock_index = MagicMock()
        mock_faiss.IndexFlatL2.return_value = mock_index

        store = FAISSStore(dimension=2)
        store.create_index()

        vecs = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
        store.add_vectors(vecs)
        self.assertEqual(store.count(), 2)

    @patch("semantica.vector_store.faiss_store.faiss")
    @patch("semantica.vector_store.faiss_store.FAISS_AVAILABLE", True)
    def test_count_empty_no_index(self, mock_faiss):
        from semantica.vector_store.faiss_store import FAISSStore

        store = FAISSStore(dimension=2)
        # No index created yet — count() must return 0, not raise.
        self.assertEqual(store.count(), 0)

    @patch("semantica.vector_store.faiss_store.faiss")
    @patch("semantica.vector_store.faiss_store.FAISS_AVAILABLE", True)
    def test_count_via_vectorstore_faiss_backend(self, mock_faiss):
        """VectorStore.count() delegates to FAISSStore.count()."""
        from semantica.vector_store.faiss_store import FAISSStore

        mock_index = MagicMock()
        mock_faiss.IndexFlatL2.return_value = mock_index

        faiss_store = FAISSStore(dimension=2)
        faiss_store.create_index()
        faiss_store.add_vectors([np.array([1.0, 0.0])])

        vs = VectorStore(backend="inmemory", dimension=2)
        vs.backend = "faiss"
        vs._backend_store = faiss_store

        self.assertEqual(vs.count(), 1)


# ---------------------------------------------------------------------------
# SQLiteVecStore.count() — unit tests with a real in-memory SQLite DB
# ---------------------------------------------------------------------------

try:
    from semantica.vector_store.sqlite_vec_store import SQLITE_VEC_AVAILABLE
except ImportError:
    SQLITE_VEC_AVAILABLE = False


@unittest.skipUnless(SQLITE_VEC_AVAILABLE, "sqlite-vec not installed")
class SQLiteVecStoreCountTests(unittest.TestCase):
    """SQLiteVecStore.count() executes SELECT COUNT(*) against the db."""

    def _make_store(self, dimension: int = 2):
        """Return a SQLiteVecStore backed by an in-memory SQLite database."""
        from semantica.vector_store.sqlite_vec_store import SQLiteVecStore

        # Use ":memory:" for isolation; each test gets a fresh store.
        store = SQLiteVecStore(
            db_path=":memory:",
            table_name="vecs",
            dimension=dimension,
            distance_metric="cosine",
        )
        return store

    def test_count_empty_store(self):
        store = self._make_store()
        self.assertEqual(store.count(), 0)

    def test_count_after_add(self):
        store = self._make_store()
        vecs = [np.array([1.0, 0.0], dtype=np.float32),
                np.array([0.0, 1.0], dtype=np.float32)]
        meta = [{"k": "a"}, {"k": "b"}]
        store.add(vecs, meta)
        self.assertEqual(store.count(), 2)

    def test_count_after_delete(self):
        store = self._make_store()
        vecs = [np.array([1.0, 0.0], dtype=np.float32),
                np.array([0.0, 1.0], dtype=np.float32)]
        meta = [{"k": "a"}, {"k": "b"}]
        ids = store.add(vecs, meta)
        store.delete([ids[0]])
        self.assertEqual(store.count(), 1)

    def test_count_matches_get_stats(self):
        store = self._make_store()
        vecs = [np.array([1.0, 0.0], dtype=np.float32)]
        store.add(vecs, [{"k": "x"}])
        stats = store.get_stats()
        self.assertEqual(store.count(), stats["vector_count"])

    def test_vectorstore_count_with_sqlite_backend(self):
        """VectorStore.count() delegates to SQLiteVecStore.count()."""
        store = self._make_store()
        vecs = [np.array([1.0, 0.0], dtype=np.float32),
                np.array([0.0, 1.0], dtype=np.float32)]
        store.add(vecs, [{}, {}])

        vs = VectorStore(backend="inmemory", dimension=2)
        vs.backend = "sqlite"
        vs._backend_store = store
        self.assertEqual(vs.count(), 2)

    def test_maintain_store_sqlite_via_vectorstore(self):
        """maintain_store() works end-to-end with a real SQLiteVecStore."""
        store = self._make_store()
        vecs = [np.array([1.0, 0.0], dtype=np.float32)]
        store.add(vecs, [{}])

        vs = VectorStore(backend="inmemory", dimension=2)
        vs.backend = "sqlite"
        vs._backend_store = store

        manager = VectorManager()
        health = manager.maintain_store(vs)
        self.assertTrue(health["healthy"])
        self.assertEqual(health["vector_count"], 1)
        self.assertIsNone(health["metadata_count"])


# ---------------------------------------------------------------------------
# PgVectorStore.count() — unit tests with mocked psycopg connection
# ---------------------------------------------------------------------------

class PgVectorStoreCountTests(unittest.TestCase):
    """PgVectorStore.count() runs SELECT COUNT(*) via get_stats()."""

    def _make_mock_store(self, row_count: int):
        """Return a PgVectorStore with its connection pool mocked out."""
        try:
            from semantica.vector_store.pgvector_store import PgVectorStore
        except ImportError:
            self.skipTest("psycopg not installed")

        store = PgVectorStore.__new__(PgVectorStore)
        store.logger = MagicMock()
        store.table_name = "vectors"
        store.dimension = 2
        store.distance_metric = "cosine"
        store._pool = None

        # Build a mock connection context that returns row_count for COUNT(*)
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (row_count,)
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        store._get_connection = MagicMock(return_value=mock_conn)

        # Stub out psycopg_sql.SQL so the parameterised query builds without
        # a real psycopg installation.
        from semantica.vector_store import pgvector_store as pgmod
        if not hasattr(pgmod, "psycopg_sql") or pgmod.psycopg_sql is None:
            self.skipTest("psycopg_sql not available in pgvector_store module")

        return store

    def test_count_returns_db_value(self):
        try:
            store = self._make_mock_store(9)
        except Exception:
            self.skipTest("Could not construct mocked PgVectorStore")
        self.assertEqual(store.count(), 9)

    def test_count_zero(self):
        try:
            store = self._make_mock_store(0)
        except Exception:
            self.skipTest("Could not construct mocked PgVectorStore")
        self.assertEqual(store.count(), 0)

    def test_vectorstore_count_delegates_to_pgvector(self):
        try:
            store = self._make_mock_store(4)
        except Exception:
            self.skipTest("Could not construct mocked PgVectorStore")

        vs = VectorStore(backend="inmemory", dimension=2)
        vs.backend = "pgvector"
        vs._backend_store = store
        self.assertEqual(vs.count(), 4)


if __name__ == "__main__":
    unittest.main()
