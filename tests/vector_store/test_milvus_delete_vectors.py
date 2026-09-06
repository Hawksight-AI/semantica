"""Tests for MilvusStore.delete_vectors (#1374)."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from semantica.context.erasure import STATUS_ERASED, ErasureCoordinator
from semantica.utils.exceptions import ProcessingError
from semantica.vector_store import VectorStore
from semantica.vector_store.milvus_store import MilvusStore


class MilvusStoreDeleteVectorsTest(TestCase):
    def setUp(self):
        self.patches = [
            patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def _store(self, result=None, error=None):
        """Return (store, exprs) where delete() records exprs, returns result."""
        exprs = []
        coll = MagicMock()

        def _delete(expr, **kwargs):
            exprs.append(expr)
            if error is not None:
                raise error
            if result is None:
                return MagicMock(delete_count=0)
            return result

        coll.collection.delete.side_effect = _delete
        store = MilvusStore()
        store.collection = coll
        return store, exprs

    def test_delete_single_id_uses_equality_expr(self):
        store, exprs = self._store(result=MagicMock(delete_count=1))
        ret = store.delete_vectors(["abc"])
        self.assertEqual(exprs, ['id == "abc"'])
        self.assertEqual(ret, {"delete_count": 1})

    def test_delete_many_ids_uses_in_expr(self):
        store, exprs = self._store(result=MagicMock(delete_count=2))
        ret = store.delete_vectors(["a", "b"])
        self.assertEqual(exprs, ['id in ["a", "b"]'])
        self.assertEqual(ret, {"delete_count": 2})

    def test_delete_escapes_quote_and_backslash_in_id(self):
        store, exprs = self._store()
        store.delete_vectors(['he said "hi"', "a\\b"])
        self.assertEqual(exprs, ['id in ["he said \\"hi\\"", "a\\\\b"]'])

    def test_delete_empty_ids_is_noop(self):
        store, _ = self._store()
        ret = store.delete_vectors([])
        self.assertEqual(ret, {"delete_count": 0})
        store.collection.collection.delete.assert_not_called()

    def test_delete_without_collection_raises(self):
        store = MilvusStore()
        with self.assertRaises(ProcessingError):
            store.delete_vectors(["a"])

    def test_delete_backend_error_raises_processing_error(self):
        store, _ = self._store(error=RuntimeError("connection reset"))
        with self.assertRaises(ProcessingError):
            store.delete_vectors(["a"])

    def test_delete_string_delete_count_is_parsed(self):
        store, _ = self._store(result=MagicMock(delete_count="3"))
        ret = store.delete_vectors(["a", "b", "c"])
        self.assertEqual(ret, {"delete_count": 3})

    def test_delete_none_delete_count_defaults_zero(self):
        store, _ = self._store(result=MagicMock(delete_count=None))
        ret = store.delete_vectors(["a"])
        self.assertEqual(ret, {"delete_count": 0})


class MilvusErasureIntegrationTest(TestCase):
    """ErasureCoordinator reaches the real MilvusStore.delete_vectors path."""

    def _bind_milvus_as_vector_store(self):
        vs = VectorStore(backend="milvus", config={"dimension": 3})
        milvus = MilvusStore()
        coll = MagicMock()
        coll.collection.delete.return_value = MagicMock(delete_count=0)
        milvus.collection = coll
        vs._backend_store = milvus
        return vs, coll

    def test_erasure_reports_erased_when_delete_runs(self):
        vs, coll = self._bind_milvus_as_vector_store()
        coord = ErasureCoordinator(vector_store=vs)
        receipt = coord.erase_entity("customer-4471")
        coll.collection.delete.assert_called()
        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_ERASED)

    def test_erasure_backend_name_is_milvus(self):
        vs, _ = self._bind_milvus_as_vector_store()
        coord = ErasureCoordinator(vector_store=vs)
        receipt = coord.erase_entity("customer-4471")
        self.assertEqual(receipt.stores["vectors"]["backend"], "milvus")
