"""Regression tests for #855: VectorManager persistent-backend crash.

VectorManager.maintain_store() and collect_statistics() used to reach
into VectorStore internals (``.vectors`` / ``.metadata``), which only
exist for the inmemory backend — any persistent backend (FAISS, Qdrant,
Pinecone, Milvus, ...) crashed with AttributeError. Both methods now go
through the public backend-agnostic ``VectorStore.count()`` accessor.

The persistent paths are exercised by swapping the backend on an
inmemory-backed instance, the same trick used across the earlier fixes
in this cluster (#839/#843/#845/#848).
"""

import unittest

import numpy as np

from semantica.vector_store.vector_store import VectorStore, VectorManager


class _CountingBackendStore:
    """Fake persistent backend store that supports count()."""

    def __init__(self, n):
        self._n = n

    def count(self):
        return self._n


class _NonCountingBackendStore:
    """Fake persistent backend store without any count capability."""


class _MisShapedBackendStore:
    """Fake persistent backend store whose ``count`` attribute is not callable."""

    count = 42  # not a method — a plain attribute


class VectorStoreCountTests(unittest.TestCase):
    """VectorStore.count() backend-agnostic accessor."""

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
        # Regression (Qodo review #914): a persistent backend with no
        # wrapped store must not silently report 0 — that masks a missing
        # initialization as an empty, healthy store. Follow the
        # get_vector()/get_metadata() precedent and raise.
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = "faiss"
        store._backend_store = None
        with self.assertRaises(NotImplementedError):
            store.count()

    def test_count_raises_when_backend_count_not_callable(self):
        # Regression (Qodo review #914): a mis-shaped adapter exposing a
        # non-callable ``count`` attribute must surface a clean
        # NotImplementedError, not a TypeError.
        store = VectorStore(backend="inmemory", dimension=2)
        store.backend = "faiss"
        store._backend_store = _MisShapedBackendStore()
        with self.assertRaises(NotImplementedError):
            store.count()


class VectorManagerPersistentTests(unittest.TestCase):
    """VectorManager works on persistent-style stores via count() (#855)."""

    def setUp(self):
        self.vectors = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
        self.metadata = [{"type": "a"}, {"type": "b"}]
        self.manager = VectorManager()

    def _inmemory_store(self):
        store = VectorStore(backend="inmemory", dimension=2)
        store.store_vectors(self.vectors, self.metadata)
        return store

    def _persistent_store(self, backend_store):
        store = self._inmemory_store()
        store.backend = "faiss"
        store._backend_store = backend_store
        return store

    def test_collect_statistics_inmemory(self):
        stats = self.manager.collect_statistics(self._inmemory_store())
        self.assertEqual(stats["total_vectors"], 2)
        self.assertEqual(stats["dimension"], 2)
        self.assertEqual(stats["backend"], "inmemory")

    def test_collect_statistics_persistent_with_count(self):
        store = self._persistent_store(_CountingBackendStore(5))
        stats = self.manager.collect_statistics(store)
        self.assertEqual(stats["total_vectors"], 5)
        self.assertEqual(stats["dimension"], 2)
        self.assertEqual(stats["backend"], "faiss")

    def test_collect_statistics_persistent_without_count_raises(self):
        store = self._persistent_store(_NonCountingBackendStore())
        # Regression: must raise NotImplementedError (capability missing),
        # not AttributeError (internal attribute poking).
        with self.assertRaises(NotImplementedError):
            self.manager.collect_statistics(store)

    def test_maintain_store_inmemory(self):
        health = self.manager.maintain_store(self._inmemory_store())
        self.assertTrue(health["healthy"])
        self.assertEqual(health["vector_count"], 2)
        self.assertEqual(health["metadata_count"], 2)

    def test_maintain_store_persistent_with_count(self):
        store = self._persistent_store(_CountingBackendStore(5))
        health = self.manager.maintain_store(store)
        self.assertTrue(health["healthy"])
        self.assertEqual(health["vector_count"], 5)
        self.assertEqual(health["metadata_count"], 5)

    def test_maintain_store_persistent_without_count_raises(self):
        store = self._persistent_store(_NonCountingBackendStore())
        with self.assertRaises(NotImplementedError):
            self.manager.maintain_store(store)


if __name__ == "__main__":
    unittest.main()
