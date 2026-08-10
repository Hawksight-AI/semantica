import unittest
from unittest.mock import MagicMock, patch, ANY
import numpy as np
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent.parent))

from semantica.vector_store.vector_store import VectorStore, VectorIndexer, VectorRetriever, VectorManager
from semantica.vector_store.registry import MethodRegistry, method_registry
from semantica.vector_store.faiss_store import FAISSStore, FAISSIndex, FAISSIndexBuilder, FAISSSearch
from semantica.vector_store.milvus_store import MilvusStore, MilvusClient, MilvusCollection, MilvusSearch
from semantica.vector_store.qdrant_store import QdrantStore
from semantica.vector_store.weaviate_store import WeaviateStore
from semantica.vector_store.hybrid_search import HybridSearch, MetadataFilter, SearchRanker

pytestmark = pytest.mark.integration

class TestVectorStoreDeepDive(unittest.TestCase):

    def setUp(self):
        self.vectors = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
        self.ids = ["vec_1", "vec_2"]
        self.metadata = [{"type": "a"}, {"type": "b"}]

    def test_vector_store_in_memory(self):
        """Test the default in-memory VectorStore implementation."""
        store = VectorStore(backend="inmemory", dimension=2)
        
        # Test storing vectors
        ids = store.store_vectors(self.vectors, self.metadata)
        self.assertEqual(len(ids), 2)
        self.assertEqual(store.vectors[ids[0]].tolist(), self.vectors[0].tolist())
        
        # Test searching vectors (exact match)
        results = store.search_vectors(np.array([1.0, 0.0]), k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], ids[0])
        # Score should be close to 1.0 (cosine similarity of identical vectors)
        self.assertAlmostEqual(results[0]["score"], 1.0)

        # Test searching vectors (orthogonal)
        results = store.search_vectors(np.array([0.0, 1.0]), k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], ids[1])

        # Test updating vectors
        new_vec = np.array([0.5, 0.5])
        store.update_vectors([ids[0]], [new_vec])
        self.assertTrue(np.array_equal(store.get_vector(ids[0]), new_vec))

        # Test deleting vectors
        store.delete_vectors([ids[0]])
        self.assertIsNone(store.get_vector(ids[0]))
        self.assertEqual(len(store.vectors), 1)

    def test_vector_indexer_retriever(self):
        """Test VectorIndexer and VectorRetriever directly."""
        indexer = VectorIndexer(backend="inmemory", dimension=2)
        index = indexer.create_index(self.vectors, self.ids)
        self.assertIsNotNone(index)
        self.assertEqual(len(index["vectors"]), 2)

        retriever = VectorRetriever(backend="inmemory")
        results = retriever.search_similar(
            np.array([1.0, 0.0]), 
            self.vectors, 
            self.ids, 
            k=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "vec_1")

        # Test hybrid search (metadata filter)
        results = retriever.search_hybrid(
            np.array([1.0, 0.0]),
            {"type": "b"}, # Filter for vec_2
            self.vectors,
            self.metadata,
            k=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["vector"].tolist(), self.vectors[1].tolist())

    def test_method_registry(self):
        """Test the MethodRegistry."""
        registry = MethodRegistry()
        
        def custom_store(): return "stored"
        
        # Register
        registry.register("store", "custom", custom_store, version="1.0")
        self.assertTrue(registry.has("store", "custom"))
        
        # Get
        func = registry.get("store", "custom")
        self.assertEqual(func(), "stored")
        
        # Metadata
        meta = registry.get_metadata("store", "custom")
        self.assertEqual(meta["version"], "1.0")
        
        # List
        all_methods = registry.list_all("store")
        self.assertEqual(all_methods["store"], ["custom"])
        
        # Unregister
        registry.unregister("store", "custom")
        self.assertFalse(registry.has("store", "custom"))

    @patch('semantica.vector_store.faiss_store.faiss')
    @patch('semantica.vector_store.faiss_store.FAISS_AVAILABLE', True)
    def test_faiss_store(self, mock_faiss):
        """Test FAISSStore with mocked faiss."""
        # Setup mock
        mock_index = MagicMock()
        mock_faiss.IndexFlatL2.return_value = mock_index
        mock_faiss.read_index.return_value = mock_index
        
        # Mock search return
        # distances, indices
        mock_index.search.return_value = (np.array([[0.0, 0.1]]), np.array([[0, 1]]))
        mock_index.ntotal = 2
        
        # Test Init
        store = FAISSStore(dimension=2)
        
        # Test Create Index
        store.create_index(index_type="flat")
        mock_faiss.IndexFlatL2.assert_called_with(2)
        
        # Test Add Vectors
        store.add_vectors(self.vectors, self.ids, self.metadata)
        mock_index.add.assert_called()
        self.assertEqual(len(store.index.vector_ids), 2)
        
        # Test Search
        results = store.search_similar(np.array([1.0, 0.0]), k=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], "vec_1")
        
        # Test Save
        store.save_index("test.index")
        mock_faiss.write_index.assert_called()
        
        # Test Load
        store.load_index("test.index")
        mock_faiss.read_index.assert_called()

    @patch('semantica.vector_store.milvus_store.connections')
    @patch('semantica.vector_store.milvus_store.Collection')
    @patch('semantica.vector_store.milvus_store.utility')
    @patch('semantica.vector_store.milvus_store.DataType')
    @patch('semantica.vector_store.milvus_store.FieldSchema')
    @patch('semantica.vector_store.milvus_store.CollectionSchema')
    @patch('semantica.vector_store.milvus_store.MILVUS_AVAILABLE', True)
    def test_milvus_store(self, mock_collection_schema, mock_field_schema, mock_data_type, mock_utility, mock_collection_cls, mock_connections):
        """Test MilvusStore with mocked pymilvus."""
        # Setup mocks
        mock_data_type.INT64 = 1
        mock_data_type.FLOAT_VECTOR = 2
        # Setup mocks
        mock_utility.has_collection.return_value = False
        mock_collection_instance = MagicMock()
        mock_collection_cls.return_value = mock_collection_instance
        
        # Mock search results
        mock_hit = MagicMock()
        mock_hit.id = 1
        mock_hit.distance = 0.1
        mock_collection_instance.search.return_value = [[mock_hit]]
        
        # Test Init
        store = MilvusStore(host="localhost")
        
        # Test Connect
        store.connect()
        mock_connections.connect.assert_called_with(
            alias="default", host="localhost", port=19530, user=None, password=None
        )
        
        # Test Create Collection
        store.create_collection("test_coll", dimension=2)
        mock_collection_cls.assert_called()
        mock_collection_instance.create_index.assert_called()
        
        # Test Insert
        store.insert_vectors(self.vectors)
        mock_collection_instance.insert.assert_called()
        
        # Test Search
        results = store.search_vectors(np.array([1.0, 0.0]), limit=1)
        mock_collection_instance.search.assert_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], 1)
        self.assertIn("metadata", results[0])
        self.assertIsInstance(results[0]["metadata"], dict)
        self.assertIn("vector", results[0])

    @patch('semantica.vector_store.qdrant_store.QdrantClientLib')
    @patch('semantica.vector_store.qdrant_store.VectorParams')
    @patch('semantica.vector_store.qdrant_store.Distance')
    @patch('semantica.vector_store.qdrant_store.PointStruct')
    @patch('semantica.vector_store.qdrant_store.QDRANT_AVAILABLE', True)
    def test_qdrant_store(self, mock_point_struct, mock_distance, mock_vector_params, mock_qdrant_cls):
        """Test QdrantStore with mocked qdrant_client."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        
        # Mock search response
        mock_hit = MagicMock()
        mock_hit.id = "vec_1"
        mock_hit.score = 0.9
        mock_hit.payload = {"type": "a"}
        mock_client.search.return_value = [mock_hit]
        
        store = QdrantStore(url="http://localhost:6333")
        
        # Connect
        store.connect()
        mock_qdrant_cls.assert_called()
        
        # Create Collection
        store.create_collection("test-collection", vector_size=2)
        mock_client.create_collection.assert_called()
        
        # Insert
        store.insert_vectors(self.vectors, self.ids, payloads=self.metadata)
        mock_client.upsert.assert_called()
        
        # Search
        results = store.search_vectors(np.array([1.0, 0.0]), limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "vec_1")

        self.assertIn("metadata", results[0])
        self.assertNotIn("payload", results[0])
        self.assertEqual(results[0]["metadata"], {"type": "a"})

        hybrid = HybridSearch()
        matched = hybrid.filter_by_metadata(
            results, MetadataFilter().eq("type", "a")
        )
        self.assertEqual(len(matched), 1)

    @patch('semantica.vector_store.weaviate_store.weaviate')
    @patch('semantica.vector_store.weaviate_store.MetadataQuery')
    @patch('semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE', True)
    def test_weaviate_store(self, mock_metadata_query, mock_weaviate):
        """Test WeaviateStore with mocked weaviate."""
        mock_client = MagicMock()
        mock_weaviate.connect_to_local.return_value = mock_client
        
        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection
        
        # Mock search response
        mock_obj = MagicMock()
        mock_obj.uuid = "uuid-1"
        mock_obj.properties = {"text": "hello"}
        mock_obj.metadata.distance = 0.1
        
        mock_query_response = MagicMock()
        mock_query_response.objects = [mock_obj]
        
        mock_collection.query.near_vector.return_value = mock_query_response
        
        store = WeaviateStore(url="http://localhost:8080")
        
        # Connect
        store.connect()
        mock_weaviate.connect_to_local.assert_called()
        
        # Create Schema
        store.create_schema("TestClass", properties=[])
        mock_client.collections.create.assert_called()
        
        # Add Objects
        # Need to mock batch context manager
        mock_batch = MagicMock()
        mock_collection.batch.dynamic.return_value.__enter__.return_value = mock_batch
        
        store.get_collection("TestClass")
        store.add_objects([{"text": "hello"}], vectors=self.vectors)
        mock_batch.add_object.assert_called()
        
        # Query
        results = store.query_vectors(np.array([1.0, 0.0]), limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "uuid-1")

    def test_hybrid_search(self):
        """Test HybridSearch, MetadataFilter and SearchRanker."""
        search = HybridSearch()
        
        # Test MetadataFilter
        meta_filter = MetadataFilter().eq("type", "a")
        self.assertTrue(meta_filter.matches({"type": "a"}))
        self.assertFalse(meta_filter.matches({"type": "b"}))
        
        meta_filter = MetadataFilter().gt("val", 10)
        self.assertTrue(meta_filter.matches({"val": 20}))
        self.assertFalse(meta_filter.matches({"val": 5}))
        
        # Test Search
        results = search.search(
            query=np.array([1.0, 0.0]),
            vectors=self.vectors,
            metadata=self.metadata,
            vector_ids=self.ids,
            k=2
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], "vec_1")
        
        # Test Filtered Search
        results = search.search(
            query=np.array([1.0, 0.0]),
            vectors=self.vectors,
            metadata=self.metadata,
            vector_ids=self.ids,
            k=2,
            metadata_filter=MetadataFilter().eq("type", "b")
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "vec_2")
        
        # Test Ranker
        ranker = SearchRanker(strategy="reciprocal_rank_fusion")
        res1 = [{"id": "1", "score": 0.9}, {"id": "2", "score": 0.8}]
        res2 = [{"id": "2", "score": 0.85}, {"id": "1", "score": 0.7}]
        
        fused = ranker.rank([res1, res2])
        self.assertEqual(len(fused), 2)
        # ID 2 should be top because it's high in both? Or ID 1?
        # RRF: 1/(k+1) + 1/(k+2) vs 1/(k+2) + 1/(k+1). They are equal rank-wise (1st and 2nd).
        
        # Multi-source search
        sources = [
            {"vectors": [self.vectors[0]], "metadata": [self.metadata[0]], "ids": ["vec_1"]},
            {"vectors": [self.vectors[1]], "metadata": [self.metadata[1]], "ids": ["vec_2"]}
        ]
        multi_res = search.multi_source_search(np.array([1.0, 0.0]), sources, k=2)
        self.assertEqual(len(multi_res), 2)

    def test_vector_manager(self):
        """Test VectorManager."""
        manager = VectorManager()
        store = VectorStore(backend="inmemory")
        store.store_vectors(self.vectors, self.metadata)
        
        # Test statistics
        stats = manager.collect_statistics(store)
        self.assertEqual(stats["total_vectors"], 2)
        self.assertEqual(stats["backend"], "inmemory")
        
        # Test maintenance
        health = manager.maintain_store(store)
        self.assertTrue(health["healthy"])
        
        # Test manage_store wrapper
        results = manager.manage_store(store, statistics=True, optimize=True)
        self.assertIn("statistics", results)
        self.assertIn("optimize", results)

    def test_config(self):
        """Test VectorStoreConfig."""
        from semantica.vector_store.config import vector_store_config
        
        # Test get default
        self.assertEqual(vector_store_config.get("default_backend"), "faiss")
        
        # Test set
        vector_store_config.set("test_key", "test_value")
        self.assertEqual(vector_store_config.get("test_key"), "test_value")
        
        # Test update
        vector_store_config.update({"test_key_2": "val2"})
        self.assertEqual(vector_store_config.get("test_key_2"), "val2")
        
        # Test method config
        vector_store_config.set_method_config("test_method", {"param": 1})
        self.assertEqual(vector_store_config.get_method_config("test_method")["param"], 1)

    def test_hybrid_search_backend_delegation(self):
        """Test HybridSearch delegation to non-inmemory backends."""
        mock_store = MagicMock()
        del mock_store.vectors  # Ensure hasattr(mock_store, "vectors") is False
        
        # Setup mock return value with mixed schema (some with metadata, some without/payload)
        mock_store.search_vectors.return_value = [
            {"id": "vec_1", "score": 0.9, "distance": 0.1, "metadata": {"type": "a", "val": 10}},
            {"id": "vec_2", "score": 0.8, "metadata": {"type": "b", "val": 20}},
            {"id": "vec_3", "score": 0.7, "distance": 0.3, "metadata": {"type": "a", "val": 30}},
            {"id": "vec_4", "score": 0.6, "payload": {"ignored": True}}
        ]
        
        search = HybridSearch(vector_store=mock_store)
        
        # 1. Basic delegation & normalization & list->ndarray conversion
        query_list = [1.0, 0.0]
        results = search.search(query=query_list, k=2)
        
        mock_store.search_vectors.assert_called_once()
        args, kwargs = mock_store.search_vectors.call_args
        self.assertIsInstance(kwargs.get("query_vector"), np.ndarray)
        self.assertEqual(kwargs.get("k"), 4)  # fetch_k = k * 2 = 4 (no filter)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], "vec_1")
        self.assertEqual(results[0]["distance"], 0.1)
        self.assertEqual(results[0]["metadata"], {"type": "a", "val": 10})
        
        self.assertEqual(results[1]["id"], "vec_2")
        self.assertIsNone(results[1]["distance"])
        self.assertEqual(results[1]["metadata"], {"type": "b", "val": 20})
        
        # 2. Metadata filtering
        mock_store.search_vectors.reset_mock()
        results = search.search(
            query=np.array([1.0, 0.0]), 
            k=2, 
            metadata_filter=MetadataFilter().eq("type", "a")
        )
        
        mock_store.search_vectors.assert_called_once()
        args, kwargs = mock_store.search_vectors.call_args
        self.assertEqual(kwargs.get("k"), 8)  # fetch_k = k * 4 = 8 (with filter)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], "vec_1")
        self.assertEqual(results[1]["id"], "vec_3")
        
        # 3. top_k handling
        mock_store.search_vectors.reset_mock()
        results = search.search(query=np.array([1.0, 0.0]), top_k=3)
        
        args, kwargs = mock_store.search_vectors.call_args
        self.assertEqual(kwargs.get("k"), 6)
        self.assertNotIn("top_k", kwargs)

if __name__ == '__main__':
    unittest.main()
