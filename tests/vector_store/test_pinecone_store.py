import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import sys
import os

# Ensure semantica is in path if running directly
if __name__ == "__main__":
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

try:
    from semantica.vector_store.pinecone_store import (
        PineconeStore,
        PineconeClient,
        PineconeIndex,
        PineconeSearch,
        PINECONE_AVAILABLE
    )
    from semantica.utils.exceptions import ProcessingError
except ImportError:
    # If we can't import, we can't run these tests
    # But we should not crash silently.
    # We will define dummy classes if needed or fail loudly.
    raise

class TestPineconeStore(unittest.TestCase):
    """Test Pinecone store functionality."""

    def setUp(self):
        self.mock_logger = MagicMock()
        self.mock_tracker = MagicMock()

        self.logger_patcher = patch('semantica.vector_store.pinecone_store.get_logger', return_value=self.mock_logger)
        self.tracker_patcher = patch('semantica.vector_store.pinecone_store.get_progress_tracker', return_value=self.mock_tracker)
        self.mock_logger_instance = self.logger_patcher.start()
        self.mock_tracker_instance = self.tracker_patcher.start()

    def tearDown(self):
        self.logger_patcher.stop()
        self.tracker_patcher.stop()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    @patch('semantica.vector_store.pinecone_store.PineconeClientLib')
    def test_connect(self, mock_pinecone_client):
        """Test connecting to Pinecone."""
        mock_client_instance = MagicMock()
        mock_pinecone_client.return_value = mock_client_instance

        store = PineconeStore(api_key="test-key")
        store.connect()

        self.assertIsNotNone(store.client)
        mock_pinecone_client.assert_called_once_with(api_key="test-key")

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', False)
    def test_connect_unavailable(self):
        """Test connecting when Pinecone is not available."""
        store = PineconeStore(api_key="test-key")
        with self.assertRaises(ProcessingError):
            store.connect()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    @patch('semantica.vector_store.pinecone_store.PineconeClientLib')
    def test_create_index(self, mock_pinecone_client):
        """Test creating an index."""
        mock_client_instance = MagicMock()
        mock_index_instance = MagicMock()
        mock_pinecone_client.return_value = mock_client_instance
        mock_client_instance.Index.return_value = mock_index_instance

        store = PineconeStore(api_key="test-key")
        store.connect()

        # Mock the client's create_index method
        store.client.create_index = MagicMock()
        store.client.get_index = MagicMock(return_value=mock_index_instance)

        result = store.create_index("test-index", dimension=768, metric="cosine")

        self.assertIsInstance(result, PineconeIndex)
        self.assertIsInstance(store.index, PineconeIndex)
        self.assertIsInstance(store.search_engine, PineconeSearch)
        store.client.create_index.assert_called_once()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    @patch('semantica.vector_store.pinecone_store.PineconeClientLib')
    def test_upsert_vectors(self, mock_pinecone_client):
        """Test upserting vectors to Pinecone index."""
        mock_client_instance = MagicMock()
        mock_index_instance = MagicMock()
        mock_pinecone_client.return_value = mock_client_instance

        store = PineconeStore(api_key="test-key")
        store.connect()

        # Set up index
        store.index = PineconeIndex(mock_index_instance)
        store.index.upsert_vectors = MagicMock(return_value={"upserted_count": 2})

        vectors = [np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])]
        ids = ["id1", "id2"]
        metadata = [{"key": "value1"}, {"key": "value2"}]

        result = store.upsert_vectors(vectors, ids, metadata)

        self.assertEqual(result["upserted_count"], 2)
        store.index.upsert_vectors.assert_called_once()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    @patch('semantica.vector_store.pinecone_store.PineconeClientLib')
    def test_search_vectors(self, mock_pinecone_client):
        """Test searching vectors in Pinecone index."""
        mock_client_instance = MagicMock()
        mock_index_instance = MagicMock()
        mock_pinecone_client.return_value = mock_client_instance

        store = PineconeStore(api_key="test-key")
        store.connect()

        # Set up search engine
        store.search_engine = PineconeSearch(PineconeIndex(mock_index_instance))
        store.search_engine.similarity_search = MagicMock(return_value=[
            {"id": "id1", "score": 0.9, "metadata": {"key": "value1"}}
        ])

        query_vector = np.array([0.1, 0.2, 0.3])
        results = store.search_vectors(query_vector, k=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "id1")
        store.search_engine.similarity_search.assert_called_once()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    @patch('semantica.vector_store.pinecone_store.PineconeClientLib')
    def test_delete_vectors(self, mock_pinecone_client):
        """Test deleting vectors from Pinecone index."""
        mock_client_instance = MagicMock()
        mock_index_instance = MagicMock()
        mock_pinecone_client.return_value = mock_client_instance

        store = PineconeStore(api_key="test-key")
        store.connect()

        # Set up index
        store.index = PineconeIndex(mock_index_instance)
        store.index.delete_vectors = MagicMock(return_value={"deleted": True})

        result = store.delete_vectors(["id1", "id2"])

        self.assertEqual(result["deleted"], True)
        # Fix: assert called without the empty dict
        store.index.delete_vectors.assert_called_once_with(["id1", "id2"], "")

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    @patch('semantica.vector_store.pinecone_store.PineconeClientLib')
    def test_fetch_vectors(self, mock_pinecone_client):
        """Test fetching vectors from Pinecone index."""
        mock_client_instance = MagicMock()
        mock_index_instance = MagicMock()
        mock_pinecone_client.return_value = mock_client_instance

        store = PineconeStore(api_key="test-key")
        store.connect()

        # Set up index
        store.index = PineconeIndex(mock_index_instance)
        store.index.fetch_vectors = MagicMock(return_value={
            "vectors": {
                "id1": {"values": [0.1, 0.2], "metadata": {"key": "value1"}}
            }
        })

        result = store.fetch_vectors(["id1"])

        self.assertIn("vectors", result)
        # Fix: assert called without the empty dict
        store.index.fetch_vectors.assert_called_once_with(["id1"], "")


class TestPineconeClient(unittest.TestCase):
    """Test PineconeClient wrapper."""

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    @patch('semantica.vector_store.pinecone_store.PineconeClientLib')
    def test_create_index(self, mock_pinecone_client):
        """Test creating an index via PineconeClient."""
        mock_client_instance = MagicMock()
        mock_pinecone_client.return_value = mock_client_instance

        client = PineconeClient(mock_client_instance)
        client.create_index("test-index", 768, "cosine")

        mock_client_instance.create_index.assert_called_once()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    @patch('semantica.vector_store.pinecone_store.PineconeClientLib')
    def test_list_indexes(self, mock_pinecone_client):
        """Test listing indexes via PineconeClient."""
        mock_client_instance = MagicMock()
        mock_index_obj = MagicMock()
        mock_index_obj.name = "test-index"
        mock_client_instance.list_indexes.return_value = [mock_index_obj]
        mock_pinecone_client.return_value = mock_client_instance

        client = PineconeClient(mock_client_instance)
        result = client.list_indexes()

        self.assertEqual(result, ["test-index"])


class TestPineconeIndex(unittest.TestCase):
    """Test PineconeIndex wrapper."""

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_upsert_vectors(self):
        """Test upserting vectors via PineconeIndex."""
        mock_index = MagicMock()
        mock_response = MagicMock()
        mock_response.upserted_count = 2
        mock_index.upsert.return_value = mock_response

        index = PineconeIndex(mock_index)
        result = index.upsert_vectors(
            [[0.1, 0.2], [0.3, 0.4]],
            ["id1", "id2"],
            [{"key": "value1"}]
        )

        self.assertEqual(result["upserted_count"], 2)
        mock_index.upsert.assert_called_once()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_search_vectors(self):
        """Test searching vectors via PineconeIndex."""
        mock_index = MagicMock()
        mock_match = MagicMock()
        mock_match.id = "id1"
        mock_match.score = 0.9
        mock_match.metadata = {"key": "value1"}
        mock_response = MagicMock()
        mock_response.matches = [mock_match]
        mock_index.query.return_value = mock_response

        index = PineconeIndex(mock_index)
        result = index.search_vectors([0.1, 0.2], k=5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "id1")
        mock_index.query.assert_called_once()


class TestPineconeIterAll(unittest.TestCase):
    """PineconeStore.iter_all() list-then-fetch enumeration."""

    def _page(self, ids, next_token):
        """Stand-in for a list_paginated() response."""
        response = MagicMock()
        response.vectors = [MagicMock(id=vector_id) for vector_id in ids]
        response.pagination = MagicMock(next=next_token)
        return response

    def _store(self, pages, fetch_results):
        store = PineconeStore()
        wrapper = MagicMock()
        raw_index = MagicMock()
        raw_index.list_paginated.side_effect = list(pages)
        wrapper.index = raw_index
        wrapper.fetch_vectors.side_effect = list(fetch_results)
        store.index = wrapper
        return store, wrapper, raw_index

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_threads_pagination_token_across_pages(self):
        store, _, raw_index = self._store(
            [self._page(["a", "b"], "token-1"), self._page(["c"], None)],
            [
                {"vectors": {"a": {"values": [0.1], "metadata": {}},
                             "b": {"values": [0.2], "metadata": {}}}},
                {"vectors": {"c": {"values": [0.3], "metadata": {}}}},
            ],
        )

        result = list(store.iter_all(batch_size=2))

        self.assertEqual([item["id"] for item in result], ["a", "b", "c"])
        calls = raw_index.list_paginated.call_args_list
        self.assertNotIn("pagination_token", calls[0][1])
        self.assertEqual(calls[1][1]["pagination_token"], "token-1")

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_hydrates_listed_ids_with_a_fetch(self):
        """Listing returns ids only, so each page needs a fetch()."""
        store, wrapper, _ = self._store(
            [self._page(["a"], None)],
            [{"vectors": {"a": {"values": [0.1, 0.2], "metadata": {"tag": "x"}}}}],
        )

        item = list(store.iter_all())[0]

        self.assertEqual(item["id"], "a")
        self.assertEqual(item["metadata"], {"tag": "x"})
        np.testing.assert_allclose(item["vector"], np.array([0.1, 0.2]))
        wrapper.fetch_vectors.assert_called_once_with(["a"], namespace="")

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_list_and_fetch_use_the_same_namespace(self):
        store, wrapper, raw_index = self._store(
            [self._page(["a"], None)],
            [{"vectors": {"a": {"values": [0.1], "metadata": {}}}}],
        )

        list(store.iter_all(namespace="prod"))

        self.assertEqual(raw_index.list_paginated.call_args[1]["namespace"], "prod")
        wrapper.fetch_vectors.assert_called_once_with(["a"], namespace="prod")

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_skips_ids_deleted_between_list_and_fetch(self):
        """fetch() omits ids it cannot find rather than returning blanks."""
        store, _, _ = self._store(
            [self._page(["a", "gone"], None)],
            [{"vectors": {"a": {"values": [0.1], "metadata": {}}}}],
        )

        result = list(store.iter_all())

        self.assertEqual([item["id"] for item in result], ["a"])

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_raises_when_pagination_token_repeats(self):
        """A stalled token must not loop forever, nor quietly return a partial
        scan that reads as a complete one."""
        store, _, raw_index = self._store(
            [self._page(["a"], "same"), self._page(["b"], "same")],
            [
                {"vectors": {"a": {"values": [0.1], "metadata": {}}}},
                {"vectors": {"b": {"values": [0.2], "metadata": {}}}},
            ],
        )

        with self.assertRaises(ProcessingError):
            list(store.iter_all())

        self.assertEqual(raw_index.list_paginated.call_count, 2)

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_empty_listing_yields_nothing_without_fetching(self):
        store, wrapper, _ = self._store([self._page([], None)], [])

        self.assertEqual(list(store.iter_all()), [])
        wrapper.fetch_vectors.assert_not_called()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_continues_past_an_empty_page_with_a_live_token(self):
        """An empty page is not necessarily the end: Pinecone can legitimately
        list zero ids for a page while pagination.next is still set (sparse
        or filtered namespaces, eventual-consistency windows on serverless
        indexes). Only the absence of a next token means exhaustion."""
        store, wrapper, raw_index = self._store(
            [
                self._page(["a"], "token-1"),
                self._page([], "token-2"),  # empty page, but the token still advances
                self._page(["b"], None),
            ],
            [
                {"vectors": {"a": {"values": [0.1], "metadata": {}}}},
                {"vectors": {"b": {"values": [0.2], "metadata": {}}}},
            ],
        )

        result = list(store.iter_all(batch_size=1))

        self.assertEqual([item["id"] for item in result], ["a", "b"])
        self.assertEqual(raw_index.list_paginated.call_count, 3)
        # Nothing to hydrate on the empty page, so only two fetches happen.
        self.assertEqual(wrapper.fetch_vectors.call_count, 2)

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_accepts_plain_string_ids_from_listing(self):
        """SDK generations differ on what listing yields."""
        store, _, _ = self._store(
            [self._page([], None)],
            [{"vectors": {"a": {"values": [0.1], "metadata": {}}}}],
        )
        response = MagicMock()
        response.vectors = ["a"]
        response.pagination = MagicMock(next=None)
        store.index.index.list_paginated.side_effect = [response]

        self.assertEqual([item["id"] for item in store.iter_all()], ["a"])

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_handles_missing_values_and_metadata(self):
        store, _, _ = self._store(
            [self._page(["a"], None)],
            [{"vectors": {"a": {"values": None, "metadata": None}}}],
        )

        item = list(store.iter_all())[0]

        self.assertIsNone(item["vector"])
        self.assertEqual(item["metadata"], {})

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_raises_when_list_paginated_unavailable(self):
        store = PineconeStore()
        wrapper = MagicMock()
        wrapper.index = MagicMock(spec=["query", "fetch"])
        store.index = wrapper

        with self.assertRaises(ProcessingError):
            list(store.iter_all())

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_raises_when_index_not_initialized(self):
        """Must fail loudly: an empty scan reads the same as an empty source."""
        with self.assertRaises(ProcessingError):
            list(PineconeStore().iter_all())

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', False)
    def test_raises_when_pinecone_unavailable(self):
        store = PineconeStore()
        store.index = MagicMock()

        with self.assertRaises(ProcessingError):
            list(store.iter_all())

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_propagates_listing_errors(self):
        store, _, raw_index = self._store([], [])
        raw_index.list_paginated.side_effect = RuntimeError("connection reset")

        with self.assertRaises(RuntimeError):
            list(store.iter_all())


if __name__ == '__main__':
    print("DEBUG: Starting unittest.main()")
    unittest.main()
