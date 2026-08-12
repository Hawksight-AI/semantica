import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from semantica.vector_store.faiss_store import FAISSStore
from semantica.vector_store.qdrant_store import QdrantStore
from semantica.vector_store.pinecone_store import PineconeStore
from semantica.vector_store.milvus_store import MilvusStore
from semantica.vector_store.pgvector_store import PgVectorStore
from semantica.vector_store.weaviate_store import WeaviateStore
from semantica.utils.exceptions import ProcessingError, ValidationError


class TestBackendMetadataFiltering(unittest.TestCase):

    def test_faiss_store_filter_by_metadata(self):
        store = FAISSStore(dimension=2)
        mock_index = MagicMock()
        mock_index.metadata = {
            "v1": {"category": "finance", "score": 10},
            "v2": {"category": "tech", "score": 20},
        }
        mock_index.get_vector.side_effect = lambda vid: np.array([1.0, 0.0]) if vid == "v1" else np.array([0.0, 1.0])
        store.index = mock_index

        results = store.filter_by_metadata({"category": "finance"}, limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "v1")
        self.assertEqual(results[0]["metadata"], {"category": "finance", "score": 10})

    @patch('semantica.vector_store.qdrant_store.FieldCondition', MagicMock())
    @patch('semantica.vector_store.qdrant_store.MatchValue', MagicMock())
    @patch('semantica.vector_store.qdrant_store.Filter', MagicMock())
    @patch('semantica.vector_store.qdrant_store.QDRANT_AVAILABLE', True)
    def test_qdrant_store_filter_by_metadata(self):
        store = QdrantStore()
        mock_collection = MagicMock()
        mock_collection.collection_name = "test_coll"
        store.collection = mock_collection
        mock_client = MagicMock()
        rec = MagicMock()
        rec.id = "q1"
        rec.payload = {"env": "prod"}
        rec.vector = [0.1, 0.2]
        mock_client.scroll.return_value = ([rec], None)
        store.client = mock_client

        results = store.filter_by_metadata({"env": "prod"}, limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "q1")
        self.assertEqual(results[0]["metadata"], {"env": "prod"})
        mock_client.scroll.assert_called_once()

    @patch('semantica.vector_store.qdrant_store.Range', MagicMock())
    @patch('semantica.vector_store.qdrant_store.FieldCondition', MagicMock())
    @patch('semantica.vector_store.qdrant_store.Filter', MagicMock())
    @patch('semantica.vector_store.qdrant_store.QDRANT_AVAILABLE', True)
    def test_qdrant_store_filter_by_metadata_range(self):
        """Range filters must construct Range objects and not raise NameError."""
        store = QdrantStore()
        mock_collection = MagicMock()
        mock_collection.collection_name = "test_coll"
        store.collection = mock_collection
        mock_client = MagicMock()
        rec = MagicMock()
        rec.id = "r1"
        rec.payload = {"score": 8}
        rec.vector = [0.3, 0.4]
        mock_client.scroll.return_value = ([rec], None)
        store.client = mock_client

        # min-only range
        results = store.filter_by_metadata({"score": {"min": 5}}, limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "r1")
        mock_client.scroll.assert_called()

        # Verify Range was actually called to build the condition (not skipped)
        import semantica.vector_store.qdrant_store as qs_mod
        qs_mod.Range.assert_called()

    @patch('semantica.vector_store.qdrant_store.Range', MagicMock())
    @patch('semantica.vector_store.qdrant_store.FieldCondition', MagicMock())
    @patch('semantica.vector_store.qdrant_store.Filter', MagicMock())
    @patch('semantica.vector_store.qdrant_store.QDRANT_AVAILABLE', True)
    def test_qdrant_store_filter_by_metadata_range_min_and_max(self):
        """Range filters with both min and max must construct Range with both gte and lte."""
        store = QdrantStore()
        mock_collection = MagicMock()
        mock_collection.collection_name = "test_coll"
        store.collection = mock_collection
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        store.client = mock_client

        store.filter_by_metadata({"score": {"min": 5, "max": 10}}, limit=10)

        import semantica.vector_store.qdrant_store as qs_mod
        # Range must have been called with gte and lte
        qs_mod.Range.assert_called_with(gte=5, lte=10)

    @patch('semantica.vector_store.qdrant_store.MatchAny', MagicMock())
    @patch('semantica.vector_store.qdrant_store.FieldCondition', MagicMock())
    @patch('semantica.vector_store.qdrant_store.Filter', MagicMock())
    @patch('semantica.vector_store.qdrant_store.QDRANT_AVAILABLE', True)
    def test_qdrant_store_filter_by_metadata_list(self):
        """List filters must construct MatchAny objects and not raise NameError."""
        store = QdrantStore()
        mock_collection = MagicMock()
        mock_collection.collection_name = "test_coll"
        store.collection = mock_collection
        mock_client = MagicMock()
        rec = MagicMock()
        rec.id = "l1"
        rec.payload = {"tags": "python"}
        rec.vector = [0.5, 0.6]
        mock_client.scroll.return_value = ([rec], None)
        store.client = mock_client

        results = store.filter_by_metadata({"tags": ["python", "ml"]}, limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "l1")
        mock_client.scroll.assert_called()

        # Verify MatchAny was actually called with the filter list
        import semantica.vector_store.qdrant_store as qs_mod
        qs_mod.MatchAny.assert_called_with(any=["python", "ml"])

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_pinecone_store_filter_by_metadata(self):
        store = PineconeStore(dimension=2)
        mock_index_wrapper = MagicMock()
        mock_inner_index = MagicMock()

        match_obj = MagicMock()
        match_obj.id = "p1"
        match_obj.metadata = {"status": "active"}
        match_obj.values = [0.1, 0.9]

        response = MagicMock()
        response.matches = [match_obj]
        mock_inner_index.query.return_value = response
        mock_index_wrapper.index = mock_inner_index
        store.index = mock_index_wrapper

        results = store.filter_by_metadata({"status": "active"}, limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "p1")
        self.assertEqual(results[0]["metadata"], {"status": "active"})
        # Assert query vector dimension matches store.dimension (2)
        mock_inner_index.query.assert_called_once()
        query_kw = mock_inner_index.query.call_args[1]
        self.assertEqual(len(query_kw["vector"]), 2)

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_pinecone_store_filter_by_metadata_unknown_dimension_raises(self):
        store = PineconeStore()
        mock_index_wrapper = MagicMock()
        mock_index_wrapper.describe_index_stats = MagicMock(return_value={})
        store.index = mock_index_wrapper
        with self.assertRaises(ProcessingError):
            store.filter_by_metadata({"status": "active"}, limit=5)

    @patch('semantica.vector_store.milvus_store.MILVUS_AVAILABLE', True)
    def test_milvus_store_filter_by_metadata(self):
        store = MilvusStore()
        mock_coll_wrapper = MagicMock()
        mock_inner_coll = MagicMock()
        mock_inner_coll.query.return_value = [
            {"id": "m1", "vector": [0.3, 0.4], "metadata": {"lang": "py"}}
        ]
        mock_coll_wrapper.collection = mock_inner_coll
        store.collection = mock_coll_wrapper

        results = store.filter_by_metadata({"lang": "py"}, limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "m1")
        self.assertEqual(results[0]["metadata"], {"lang": "py"})

    @patch('semantica.vector_store.milvus_store.MILVUS_AVAILABLE', True)
    def test_milvus_store_filter_by_metadata_escaping(self):
        store = MilvusStore()
        mock_coll_wrapper = MagicMock()
        mock_inner_coll = MagicMock()
        mock_inner_coll.query.return_value = []
        mock_coll_wrapper.collection = mock_inner_coll
        store.collection = mock_coll_wrapper

        store.filter_by_metadata(
            {
                "title": 'John "Jack" Doe',
                "active": True,
                "tags": ['python', 'c++ "v"'],
            },
            limit=5,
        )

        mock_inner_coll.query.assert_called_once()
        expr = mock_inner_coll.query.call_args[1]["expr"]
        self.assertIn('metadata["title"] == "John \\"Jack\\" Doe"', expr)
        self.assertIn('metadata["active"] == true', expr)
        self.assertIn('metadata["tags"] in ["python", "c++ \\"v\\""]', expr)

    @patch('semantica.vector_store.milvus_store.MILVUS_AVAILABLE', True)
    def test_milvus_store_filter_by_metadata_invalid_key_raises(self):
        store = MilvusStore()
        mock_coll_wrapper = MagicMock()
        store.collection = mock_coll_wrapper

        with self.assertRaises(ValidationError):
            store.filter_by_metadata({'dept" || 1==1 || "': "val"}, limit=5)

    @patch('semantica.vector_store.pgvector_store.PSYCOPG3_AVAILABLE', True)
    @patch('semantica.vector_store.pgvector_store.psycopg_sql')
    def test_pgvector_store_filter_by_metadata(self, mock_sql):
        store = object.__new__(PgVectorStore)
        store.table_name = "test_vectors"
        store._is_safe_identifier = lambda k: True

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("pg1", [0.1, 0.2], {"org": "acme"})
        ]
        mock_conn.cursor.return_value = mock_cur

        with patch.object(PgVectorStore, '_get_connection', return_value=MagicMock(__enter__=MagicMock(return_value=mock_conn), __exit__=MagicMock())):
            results = store.filter_by_metadata({"org": "acme"}, limit=10)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], "pg1")
            self.assertEqual(results[0]["metadata"], {"org": "acme"})

    @patch('semantica.vector_store.pgvector_store.PSYCOPG3_AVAILABLE', True)
    @patch('semantica.vector_store.pgvector_store.psycopg_sql')
    def test_pgvector_store_filter_by_metadata_bool_true(self, mock_sql):
        """Boolean True must become the string 'true' (lowercase) in the SQL parameter.

        PostgreSQL JSONB ->> returns 'true' for a JSON boolean true.
        str(True) == 'True' would never match; this test guards against regression.
        """
        store = object.__new__(PgVectorStore)
        store.table_name = "test_vectors"
        store._is_safe_identifier = lambda k: True

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("pg2", [0.3, 0.4], {"active": True})
        ]
        mock_conn.cursor.return_value = mock_cur

        with patch.object(
            PgVectorStore,
            '_get_connection',
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_conn),
                __exit__=MagicMock(),
            ),
        ):
            results = store.filter_by_metadata({"active": True}, limit=10)

        # Result is returned correctly
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "pg2")

        # The critical assertion: 'true' (not 'True') was passed to execute()
        execute_call_args = mock_cur.execute.call_args
        self.assertIsNotNone(execute_call_args, "cursor.execute was not called")
        params_passed = execute_call_args[0][1]  # positional arg 1 is the params list/tuple
        self.assertIn('true', params_passed,
                      "Expected lowercase 'true' in SQL params, got: {}".format(params_passed))
        self.assertNotIn('True', params_passed,
                         "str(True)='True' must NOT appear in SQL params")

    @patch('semantica.vector_store.pgvector_store.PSYCOPG3_AVAILABLE', True)
    @patch('semantica.vector_store.pgvector_store.psycopg_sql')
    def test_pgvector_store_filter_by_metadata_bool_false(self, mock_sql):
        """Boolean False must become the string 'false' (lowercase) in the SQL parameter.

        PostgreSQL JSONB ->> returns 'false' for a JSON boolean false.
        str(False) == 'False' would never match; this test guards against regression.
        """
        store = object.__new__(PgVectorStore)
        store.table_name = "test_vectors"
        store._is_safe_identifier = lambda k: True

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("pg3", [0.5, 0.6], {"active": False})
        ]
        mock_conn.cursor.return_value = mock_cur

        with patch.object(
            PgVectorStore,
            '_get_connection',
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_conn),
                __exit__=MagicMock(),
            ),
        ):
            results = store.filter_by_metadata({"active": False}, limit=10)

        # Result is returned correctly
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "pg3")

        # The critical assertion: 'false' (not 'False') was passed to execute()
        execute_call_args = mock_cur.execute.call_args
        self.assertIsNotNone(execute_call_args, "cursor.execute was not called")
        params_passed = execute_call_args[0][1]  # positional arg 1 is the params list/tuple
        self.assertIn('false', params_passed,
                      "Expected lowercase 'false' in SQL params, got: {}".format(params_passed))
        self.assertNotIn('False', params_passed,
                         "str(False)='False' must NOT appear in SQL params")

    @patch('semantica.vector_store.pgvector_store.PSYCOPG3_AVAILABLE', True)
    @patch('semantica.vector_store.pgvector_store.psycopg_sql')
    def test_pgvector_store_filter_by_metadata_bool_list(self, mock_sql):
        """List-valued boolean filters must use lowercase 'true'/'false', not
        str(True)/str(False), matching the scalar branch's handling.
        """
        store = object.__new__(PgVectorStore)
        store.table_name = "test_vectors"
        store._is_safe_identifier = lambda k: True

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("pg4", [0.7, 0.8], {"active": True})
        ]
        mock_conn.cursor.return_value = mock_cur

        with patch.object(
            PgVectorStore,
            '_get_connection',
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_conn),
                __exit__=MagicMock(),
            ),
        ):
            results = store.filter_by_metadata({"active": [True, False]}, limit=10)

        self.assertEqual(len(results), 1)
        execute_call_args = mock_cur.execute.call_args
        params_passed = execute_call_args[0][1]
        flat_params = [v for p in params_passed for v in (p if isinstance(p, list) else [p])]
        self.assertIn('true', flat_params)
        self.assertIn('false', flat_params)
        self.assertNotIn('True', flat_params)
        self.assertNotIn('False', flat_params)

    def test_faiss_store_filter_by_metadata_limit_zero(self):
        """limit=0 must return no results, not the first match."""
        store = FAISSStore(dimension=2)
        mock_index = MagicMock()
        mock_index.metadata = {
            "v1": {"category": "finance", "score": 10},
        }
        mock_index.get_vector.return_value = np.array([1.0, 0.0])
        store.index = mock_index

        results = store.filter_by_metadata({"category": "finance"}, limit=0)
        self.assertEqual(results, [])

    @patch('semantica.vector_store.milvus_store.MILVUS_AVAILABLE', True)
    def test_milvus_store_filter_by_metadata_nan_raises(self):
        """NaN/Infinity are not valid Milvus expression literals and must be
        rejected up front rather than silently producing an invalid expression
        that gets swallowed by the broad except around the query() call.
        """
        store = MilvusStore()
        mock_coll_wrapper = MagicMock()
        store.collection = mock_coll_wrapper

        with self.assertRaises(ValidationError):
            store.filter_by_metadata({"score": {"min": float("nan")}}, limit=5)

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_pinecone_store_get_index_sets_dimension_from_stats(self):
        """get_index() must read stats from the returned PineconeIndex wrapper
        (self.index), not from a nonexistent method on the store itself.
        """
        store = PineconeStore()
        mock_client = MagicMock()
        mock_pinecone_index = MagicMock()
        mock_client.get_index.return_value = mock_pinecone_index
        store.client = mock_client

        with patch(
            'semantica.vector_store.pinecone_store.PineconeIndex'
        ) as mock_index_cls:
            mock_index_instance = MagicMock()
            mock_index_instance.describe_index_stats.return_value = {"dimension": 42}
            mock_index_cls.return_value = mock_index_instance

            store.get_index("my-index")

        self.assertEqual(store.dimension, 42)

    def test_weaviate_store_filter_by_metadata(self):
        store = WeaviateStore()
        mock_coll = MagicMock()
        obj1 = MagicMock()
        obj1.uuid = "w-uuid-1"
        obj1.properties = {"dept": "eng"}
        obj1.vector = [0.5, 0.5]
        objs = MagicMock()
        objs.objects = [obj1]
        mock_coll.query.fetch_objects.return_value = objs
        store.collection = mock_coll

        with patch('semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE', True):
            results = store.filter_by_metadata({"dept": "eng"}, limit=5)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], "w-uuid-1")
            self.assertEqual(results[0]["metadata"], {"dept": "eng"})

    def test_weaviate_store_filter_by_metadata_pagination(self):
        """Test that WeaviateStore.filter_by_metadata paginates beyond page 1 to find matching items."""
        store = WeaviateStore()
        mock_coll = MagicMock()

        # Batch 1: 100 non-matching objects
        batch1_objs = []
        for i in range(100):
            obj = MagicMock()
            obj.uuid = f"batch1-uuid-{i}"
            obj.properties = {"dept": "hr"}
            obj.vector = [0.1, 0.1]
            batch1_objs.append(obj)

        res1 = MagicMock()
        res1.objects = batch1_objs

        # Batch 2: 2 matching objects
        obj_match1 = MagicMock()
        obj_match1.uuid = "match-uuid-1"
        obj_match1.properties = {"dept": "eng"}
        obj_match1.vector = [0.5, 0.5]

        obj_match2 = MagicMock()
        obj_match2.uuid = "match-uuid-2"
        obj_match2.properties = {"dept": "eng"}
        obj_match2.vector = [0.6, 0.6]

        res2 = MagicMock()
        res2.objects = [obj_match1, obj_match2]

        def side_effect(**kwargs):
            if kwargs.get("after") == "batch1-uuid-99":
                return res2
            return res1

        mock_coll.query.fetch_objects.side_effect = side_effect
        store.collection = mock_coll

        with patch('semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE', True):
            results = store.filter_by_metadata({"dept": "eng"}, limit=5)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["id"], "match-uuid-1")
            self.assertEqual(results[1]["id"], "match-uuid-2")

    def test_weaviate_store_filter_by_metadata_native_filter(self):
        """Test building native Weaviate filters for exact, range, and list criteria."""
        store = WeaviateStore()
        mock_filter_cls = MagicMock()
        mock_filter_prop = MagicMock()
        mock_filter_cls.by_property.return_value = mock_filter_prop

        mock_module = MagicMock()
        mock_module.classes.query.Filter = mock_filter_cls

        with patch('semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE', True), \
             patch('semantica.vector_store.weaviate_store.weaviate', mock_module):

            # Test exact match
            res = store._build_weaviate_filter({"dept": "eng"})
            mock_filter_cls.by_property.assert_called_with("dept")
            mock_filter_prop.equal.assert_called_with("eng")

            # Test range filter
            mock_filter_cls.reset_mock()
            mock_filter_prop.reset_mock()
            res = store._build_weaviate_filter({"age": {"min": 20, "max": 50}})
            mock_filter_cls.by_property.assert_called_with("age")
            mock_filter_prop.greater_or_equal.assert_called_with(20)
            mock_filter_prop.less_or_equal.assert_called_with(50)

            # Test list filter
            mock_filter_cls.reset_mock()
            mock_filter_prop.reset_mock()
            res = store._build_weaviate_filter({"tags": ["a", "b"]})
            mock_filter_cls.by_property.assert_called_with("tags")
            mock_filter_prop.contains_any.assert_called_with(["a", "b"])


if __name__ == "__main__":
    unittest.main()

