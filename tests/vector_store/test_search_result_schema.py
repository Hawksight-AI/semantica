"""
Test: Search Result Schema Compliance -- Issue #845

Every backend wrapper's search method must return a list of dicts that each
contain the four required canonical fields:

    id       : str | int
    score    : float
    metadata : dict  (always a dict, {} when none stored)
    vector   : any   (np.ndarray | None; None when backend doesn't return vectors)
    distance : float | None  (preserved from FAISS, Weaviate, Milvus; None elsewhere)
"""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_canonical_schema(test_case, results):
    """Assert every result satisfies the #845 canonical schema."""
    test_case.assertIsInstance(results, list)
    for r in results:
        test_case.assertIsInstance(r, dict, "result must be a dict")
        test_case.assertIn("id", r, "result must contain 'id'")
        test_case.assertTrue(isinstance(r["id"], (str, int)), "'id' must be a str or int")
        test_case.assertIn("score", r, "result must contain 'score'")
        test_case.assertIn("metadata", r, "result must contain 'metadata'")
        test_case.assertIn("vector", r, "result must contain 'vector'")
        test_case.assertIn("distance", r, "result must contain 'distance'")
        test_case.assertIsInstance(r["metadata"], dict, "'metadata' must be a dict")
        test_case.assertIsInstance(r["score"], float, "'score' must be a float")
        test_case.assertTrue(r["distance"] is None or isinstance(r["distance"], float), "'distance' must be float or None")


# ---------------------------------------------------------------------------
# In-memory backend (no mocking needed)
# ---------------------------------------------------------------------------

class TestInMemorySearchSchema(unittest.TestCase):

    def test_search_vectors_canonical_schema(self):
        """In-memory VectorStore.search_vectors() returns canonical schema."""
        from semantica.vector_store import VectorStore

        store = VectorStore(backend="inmemory", dimension=4)
        vectors = [np.array([0.1, 0.2, 0.3, 0.4]), np.array([0.5, 0.6, 0.7, 0.8])]
        metadata = [{"type": "a"}, {"type": "b"}]
        store.store_vectors(vectors, metadata)

        results = store.search_vectors(np.array([0.15, 0.25, 0.35, 0.45]), k=2)
        _assert_canonical_schema(self, results)
        self.assertEqual(results[0]["metadata"]["type"], "a")

    def test_search_vectors_no_metadata_gives_empty_dict(self):
        """In-memory results have metadata={} when no metadata was stored."""
        from semantica.vector_store import VectorStore

        store = VectorStore(backend="inmemory", dimension=4)
        store.store_vectors([np.array([0.1, 0.2, 0.3, 0.4])])

        results = store.search_vectors(np.array([0.1, 0.2, 0.3, 0.4]), k=1)
        _assert_canonical_schema(self, results)
        self.assertEqual(results[0]["metadata"], {})


# ---------------------------------------------------------------------------
# FAISS
# ---------------------------------------------------------------------------

class TestFAISSSearchSchema(unittest.TestCase):

    @patch("semantica.vector_store.faiss_store.FAISS_AVAILABLE", True)
    @patch("semantica.vector_store.faiss_store.faiss")
    def test_faiss_search_similar_canonical_schema(self, mock_faiss):
        from semantica.vector_store.faiss_store import FAISSIndex, FAISSSearch

        mock_index = MagicMock()
        mock_index.search.return_value = (
            np.array([[0.05, 0.2]], dtype=np.float32),
            np.array([[0, 1]]),
        )

        idx = FAISSIndex(mock_index, dimension=4)
        idx.vector_ids = ["vec_0", "vec_1"]
        idx.metadata = {"vec_0": {"k": "v"}, "vec_1": {}}

        searcher = FAISSSearch(idx)
        results = searcher.search_similar(np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), k=2)

        _assert_canonical_schema(self, results)
        self.assertIn("distance", results[0])
        self.assertIsNone(results[0]["vector"])


# ---------------------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------------------

class TestQdrantSearchSchema(unittest.TestCase):

    @patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
    def test_qdrant_search_points_canonical_schema(self):
        from semantica.vector_store.qdrant_store import QdrantCollection

        mock_client = MagicMock()
        mock_hit = MagicMock()
        mock_hit.id = "q_1"
        mock_hit.score = 0.88
        mock_hit.payload = {"category": "x"}
        mock_client.search.return_value = [mock_hit]

        coll = QdrantCollection(mock_client, "test_col")
        results = coll.search_points(np.array([0.1, 0.2]), limit=1)

        _assert_canonical_schema(self, results)
        self.assertIsNone(results[0]["vector"])
        self.assertEqual(results[0]["metadata"], {"category": "x"})

    @patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
    def test_qdrant_unbounded_dot_product_scores_preserve_ranking(self):
        """Qdrant's Dot distance metric is unbounded; normalized scores must
        stay strictly ordered instead of collapsing once raw score >= 1.0
        (regression for #845 follow-up)."""
        from semantica.vector_store.qdrant_store import QdrantCollection

        mock_client = MagicMock()
        mock_hit_high = MagicMock(id="q_hi", score=50.0, payload={})
        mock_hit_mid = MagicMock(id="q_mid", score=2.0, payload={})
        mock_hit_low = MagicMock(id="q_lo", score=1.0, payload={})
        mock_client.search.return_value = [mock_hit_high, mock_hit_mid, mock_hit_low]

        coll = QdrantCollection(mock_client, "test_col")
        results = coll.search_points(np.array([0.1, 0.2]), limit=3)

        _assert_canonical_schema(self, results)
        scores = [r["score"] for r in results]
        self.assertEqual(len(set(scores)), 3, "scores >= 1.0 must not collapse")
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])
        self.assertTrue(all(0.0 < s < 1.0 for s in scores))


# ---------------------------------------------------------------------------
# Pinecone
# ---------------------------------------------------------------------------

class TestPineconeSearchSchema(unittest.TestCase):

    @patch("semantica.vector_store.pinecone_store.PINECONE_AVAILABLE", True)
    def test_pinecone_search_vectors_canonical_schema(self):
        from semantica.vector_store.pinecone_store import PineconeIndex

        mock_index = MagicMock()
        mock_match = MagicMock()
        mock_match.id = "p_1"
        mock_match.score = 0.95
        mock_match.metadata = {"source": "web"}
        mock_index.query.return_value = MagicMock(matches=[mock_match])

        pi = PineconeIndex(mock_index)
        results = pi.search_vectors([0.1, 0.2], k=1)

        _assert_canonical_schema(self, results)
        self.assertIsNone(results[0]["vector"])
        self.assertEqual(results[0]["metadata"], {"source": "web"})

    @patch("semantica.vector_store.pinecone_store.PINECONE_AVAILABLE", True)
    def test_pinecone_none_metadata_becomes_empty_dict(self):
        from semantica.vector_store.pinecone_store import PineconeIndex

        mock_index = MagicMock()
        mock_match = MagicMock()
        mock_match.id = "p_2"
        mock_match.score = 0.7
        mock_match.metadata = None
        mock_index.query.return_value = MagicMock(matches=[mock_match])

        pi = PineconeIndex(mock_index)
        results = pi.search_vectors([0.1, 0.2], k=1)

        _assert_canonical_schema(self, results)
        self.assertEqual(results[0]["metadata"], {})

    @patch("semantica.vector_store.pinecone_store.PINECONE_AVAILABLE", True)
    def test_pinecone_unbounded_dotproduct_scores_preserve_ranking(self):
        """Pinecone's dotproduct metric is unbounded; normalized scores must
        stay strictly ordered instead of collapsing once raw score >= 1.0
        (regression for #845 follow-up)."""
        from semantica.vector_store.pinecone_store import PineconeIndex

        mock_index = MagicMock()
        mock_match_high = MagicMock(id="p_hi", score=50.0, metadata={})
        mock_match_mid = MagicMock(id="p_mid", score=2.0, metadata={})
        mock_match_low = MagicMock(id="p_lo", score=1.0, metadata={})
        mock_index.query.return_value = MagicMock(
            matches=[mock_match_high, mock_match_mid, mock_match_low]
        )

        pi = PineconeIndex(mock_index)
        results = pi.search_vectors([0.1, 0.2], k=3)

        _assert_canonical_schema(self, results)
        scores = [r["score"] for r in results]
        self.assertEqual(len(set(scores)), 3, "scores >= 1.0 must not collapse")
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])
        self.assertTrue(all(0.0 < s < 1.0 for s in scores))


# ---------------------------------------------------------------------------
# Milvus
# ---------------------------------------------------------------------------

class TestMilvusSearchSchema(unittest.TestCase):

    @patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
    def test_milvus_search_canonical_schema(self):
        from semantica.vector_store.milvus_store import MilvusCollection

        mock_collection = MagicMock()
        mock_hit = MagicMock()
        mock_hit.id = 42
        mock_hit.distance = 0.15

        mock_collection.search.return_value = [[mock_hit]]

        mc = MilvusCollection.__new__(MilvusCollection)
        mc.collection = mock_collection
        mc.logger = MagicMock()

        results = mc.search(
            vectors=[np.array([0.1, 0.2])],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=1,
        )

        _assert_canonical_schema(self, results)
        self.assertEqual(results[0]["metadata"], {})
        self.assertIsNone(results[0]["vector"])
        self.assertIn("distance", results[0])


# ---------------------------------------------------------------------------
# Weaviate (direct WeaviateQuery)
# ---------------------------------------------------------------------------

class TestWeaviateSearchSchema(unittest.TestCase):

    @patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
    @patch("semantica.vector_store.weaviate_store.MetadataQuery")
    def test_weaviate_similarity_search_canonical_schema(self, mock_mq):
        from semantica.vector_store.weaviate_store import WeaviateQuery

        mock_obj = MagicMock()
        mock_obj.uuid = "weaviate-uuid-1"
        mock_obj.properties = {"text": "hello", "category": "docs"}
        mock_obj.metadata.distance = 0.12

        mock_collection = MagicMock()
        mock_collection.query.near_vector.return_value = MagicMock(objects=[mock_obj])

        wq = WeaviateQuery(mock_collection)
        results = wq.similarity_search(np.array([0.1, 0.2]), limit=1)

        _assert_canonical_schema(self, results)
        self.assertNotIn("properties", results[0])
        self.assertEqual(results[0]["metadata"]["text"], "hello")
        self.assertIsNone(results[0]["vector"])
        self.assertIn("distance", results[0])
        self.assertAlmostEqual(results[0]["distance"], 0.12)


# ---------------------------------------------------------------------------
# SearchResult TypedDict is importable
# ---------------------------------------------------------------------------

class TestSearchResultTypeImport(unittest.TestCase):

    def test_search_result_importable_from_package(self):
        from semantica.vector_store import SearchResult
        self.assertTrue(callable(SearchResult))

    def test_search_result_importable_from_module(self):
        from semantica.vector_store.vector_store import SearchResult
        self.assertTrue(callable(SearchResult))


if __name__ == "__main__":
    unittest.main()
