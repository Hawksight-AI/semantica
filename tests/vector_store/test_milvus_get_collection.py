"""Tests for MilvusStore.get_collection schema validation (#1331)."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from semantica.vector_store.milvus_store import MilvusStore
from semantica.utils.exceptions import ProcessingError


def _field(name, dtype_name, primary=False):
    f = MagicMock()
    f.name = name
    f.is_primary = primary
    f.dtype.name = dtype_name
    return f


class MilvusGetCollectionSchemaTest(TestCase):
    def setUp(self):
        self.patches = [
            patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True),
            patch("semantica.vector_store.milvus_store.utility"),
            patch("semantica.vector_store.milvus_store.Collection"),
        ]
        for p in self.patches:
            p.start()
        # utility.has_collection() must return truthy
        import semantica.vector_store.milvus_store as m

        m.utility.has_collection.return_value = True

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def _make_store(self, coll):
        store = MilvusStore()
        store.client = MagicMock()  # skip real connect
        import semantica.vector_store.milvus_store as m

        m.Collection.return_value = coll
        return store

    def _assert_rejected(self, store, expected_msg):
        with self.assertRaises(ProcessingError) as ctx:
            store.get_collection("c")
        self.assertIn(expected_msg, str(ctx.exception))
        self.assertIsNone(store.collection)

    def test_accepts_matching_schema(self):
        coll = MagicMock()
        coll.schema.fields = [
            _field("id", "VARCHAR", primary=True),
            _field("vector", "FLOAT_VECTOR"),
            _field("metadata", "JSON"),
        ]
        store = self._make_store(coll)
        result = store.get_collection("c")
        self.assertIsNotNone(result)
        self.assertIsNotNone(store.collection)
        self.assertIsNotNone(store.search_engine)
        self.assertEqual(store.collection.collection_name, "c")

    def test_rejects_non_varchar_primary_key(self):
        coll = MagicMock()
        coll.schema.fields = [
            _field("id", "INT64", primary=True),
            _field("vector", "FLOAT_VECTOR"),
            _field("metadata", "JSON"),
        ]
        store = self._make_store(coll)
        self._assert_rejected(store, "has an invalid primary key")

    def test_rejects_missing_primary_key(self):
        coll = MagicMock()
        coll.schema.fields = [
            _field("id", "VARCHAR"),
            _field("vector", "FLOAT_VECTOR"),
            _field("metadata", "JSON"),
        ]
        store = self._make_store(coll)
        self._assert_rejected(store, "has an invalid primary key")

    def test_rejects_wrongly_named_primary_key(self):
        coll = MagicMock()
        coll.schema.fields = [
            _field("pk", "VARCHAR", primary=True),
            _field("vector", "FLOAT_VECTOR"),
            _field("metadata", "JSON"),
        ]
        store = self._make_store(coll)
        self._assert_rejected(store, "has an invalid primary key")

    def test_rejects_missing_metadata_field(self):
        coll = MagicMock()
        coll.schema.fields = [
            _field("id", "VARCHAR", primary=True),
            _field("vector", "FLOAT_VECTOR"),
        ]
        store = self._make_store(coll)
        self._assert_rejected(store, "is missing required field 'metadata'")

    def test_rejects_missing_vector_field(self):
        coll = MagicMock()
        coll.schema.fields = [
            _field("id", "VARCHAR", primary=True),
            _field("metadata", "JSON"),
        ]
        store = self._make_store(coll)
        self._assert_rejected(store, "is missing required field 'vector'")

    def test_rejects_wrong_vector_dtype(self):
        coll = MagicMock()
        coll.schema.fields = [
            _field("id", "VARCHAR", primary=True),
            _field("vector", "BINARY_VECTOR"),
            _field("metadata", "JSON"),
        ]
        store = self._make_store(coll)
        self._assert_rejected(store, "has an invalid vector field")
