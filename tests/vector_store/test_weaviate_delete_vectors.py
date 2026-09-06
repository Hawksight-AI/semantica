"""Tests for WeaviateStore.delete_vectors (#1374)."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from semantica.context.erasure import STATUS_ERASED, ErasureCoordinator
from semantica.utils.exceptions import ProcessingError
from semantica.vector_store import VectorStore
from semantica.vector_store.weaviate_store import WeaviateStore


class WeaviateStoreDeleteVectorsTest(TestCase):
    def setUp(self):
        self.patches = [
            patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def _store(self, error=None):
        """Return (store, data) where data records delete_by_id calls."""
        data = MagicMock()
        data.delete_by_id = MagicMock()
        coll = MagicMock()
        coll.data = data
        if error is not None:
            data.delete_by_id.side_effect = error
        store = WeaviateStore()
        store.collection = coll
        return store, data

    def test_delete_single_id_calls_delete_by_id(self):
        store, data = self._store()
        ret = store.delete_vectors(["abc"])
        data.delete_by_id.assert_called_once_with("abc")
        self.assertEqual(ret, {"delete_count": 1})

    def test_delete_many_ids_calls_each(self):
        store, data = self._store()
        ret = store.delete_vectors(["a", "b", "c"])
        self.assertEqual(data.delete_by_id.call_count, 3)
        self.assertEqual(ret, {"delete_count": 3})

    def test_delete_skips_ids_that_report_missing(self):
        store, data = self._store()

        def _fake(uuid):
            return uuid != "missing"

        data.delete_by_id.side_effect = _fake
        ret = store.delete_vectors(["present", "missing", "also-here"])
        self.assertEqual(data.delete_by_id.call_count, 3)
        self.assertEqual(ret, {"delete_count": 2})

    def test_delete_drops_empty_ids(self):
        store, data = self._store()
        store.delete_vectors(["", "abc"])
        data.delete_by_id.assert_called_once_with("abc")
        self.assertEqual(data.delete_by_id.call_count, 1)

    def test_delete_empty_ids_is_noop(self):
        store, data = self._store()
        ret = store.delete_vectors([])
        self.assertEqual(ret, {"delete_count": 0})
        data.delete_by_id.assert_not_called()

    def test_delete_without_collection_raises(self):
        store = WeaviateStore()
        with self.assertRaises(ProcessingError):
            store.delete_vectors(["a"])

    def test_delete_backend_error_raises_processing_error(self):
        store, _ = self._store(error=RuntimeError("connection reset"))
        with self.assertRaises(ProcessingError):
            store.delete_vectors(["a"])


class WeaviateErasureIntegrationTest(TestCase):
    """ErasureCoordinator reaches the real WeaviateStore.delete_vectors path."""

    def setUp(self):
        self._patch = patch(
            "semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def _bind_weaviate_as_vector_store(self):
        vs = VectorStore(backend="weaviate", config={"dimension": 3})
        weaviate = WeaviateStore()
        data = MagicMock()
        coll = MagicMock()
        coll.data = data
        weaviate.collection = coll
        vs._backend_store = weaviate
        return vs, data

    def test_erasure_reports_erased_when_delete_runs(self):
        vs, data = self._bind_weaviate_as_vector_store()
        coord = ErasureCoordinator(vector_store=vs)
        receipt = coord.erase_entity("customer-4471")
        data.delete_by_id.assert_called()
        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_ERASED)

    def test_erasure_reports_erased_when_nothing_was_found(self):
        """delete_by_id returns False (404) for an id that is not in the store.

        For erasure that still means the goal is met: nothing remains under
        that id. The receipt keeps the honest zero count in backend_result
        instead of raising a false failed status.
        """
        vs, data = self._bind_weaviate_as_vector_store()
        data.delete_by_id.return_value = False
        coord = ErasureCoordinator(vector_store=vs)
        receipt = coord.erase_entity("customer-4471")
        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_ERASED)
        self.assertEqual(
            receipt.stores["vectors"]["backend_result"], {"delete_count": 0}
        )

    def test_erasure_backend_name_is_weaviate(self):
        vs, _ = self._bind_weaviate_as_vector_store()
        coord = ErasureCoordinator(vector_store=vs)
        receipt = coord.erase_entity("customer-4471")
        self.assertEqual(receipt.stores["vectors"]["backend"], "weaviate")

    def test_facade_delete_vectors_forwards_to_weaviate(self):
        vs, data = self._bind_weaviate_as_vector_store()

        def _fake(uuid):
            return uuid != "missing"

        data.delete_by_id.side_effect = _fake
        ret = vs.delete_vectors(["present", "missing"])
        self.assertEqual(data.delete_by_id.call_count, 2)
        self.assertEqual(ret, {"delete_count": 1})
