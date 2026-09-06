"""Tests for QdrantStore.iter_all() cursor enumeration.

Qdrant is not installed in this environment, so these drive the real
QdrantStore against a MagicMock standing in for the qdrant_client, following
the pattern already used for qdrant in test_backend_metadata_filtering.py.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from semantica.utils.exceptions import ProcessingError
from semantica.vector_store.qdrant_store import QdrantStore


def _record(point_id, payload=None, vector=None):
    """Build a stand-in for a qdrant_client Record."""
    rec = MagicMock()
    rec.id = point_id
    rec.payload = payload
    rec.vector = vector
    return rec


def _store_with_scroll(*pages):
    """QdrantStore whose client.scroll() returns the given (records, cursor) pages."""
    store = QdrantStore()
    store.client = MagicMock()
    store.client.scroll.side_effect = list(pages)
    store.collection = MagicMock()
    store.collection.collection_name = "test_collection"
    return store


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_threads_cursor_across_pages():
    """The next call continues from the previous page's cursor."""
    store = _store_with_scroll(
        ([_record(1), _record(2)], "cursor-1"),
        ([_record(3)], None),
    )

    result = list(store.iter_all(batch_size=2))

    assert [item["id"] for item in result] == ["1", "2", "3"]
    calls = store.client.scroll.call_args_list
    assert len(calls) == 2
    assert calls[0][1]["offset"] is None
    assert calls[0][1]["limit"] == 2
    assert calls[1][1]["offset"] == "cursor-1"


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_yields_final_page_that_reports_no_next_cursor():
    """Records and a null cursor can arrive together; those records must still
    be yielded or every scan loses its tail."""
    store = _store_with_scroll(([_record(1), _record(2)], None))

    result = list(store.iter_all(batch_size=10))

    assert [item["id"] for item in result] == ["1", "2"]
    assert store.client.scroll.call_count == 1


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_converts_records_to_the_shared_result_shape():
    store = _store_with_scroll(
        ([_record(7, payload={"tag": "x"}, vector=[0.1, 0.2, 0.3])], None),
    )

    item = list(store.iter_all())[0]

    assert item["id"] == "7"
    assert item["metadata"] == {"tag": "x"}
    np.testing.assert_allclose(item["vector"], np.array([0.1, 0.2, 0.3]))


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_handles_missing_payload_and_vector():
    store = _store_with_scroll(([_record(1, payload=None, vector=None)], None))

    item = list(store.iter_all())[0]

    assert item["metadata"] == {}
    assert item["vector"] is None


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_empty_collection_yields_nothing():
    store = _store_with_scroll(([], None))

    assert list(store.iter_all()) == []


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_continues_past_empty_page_with_advancing_cursor():
    store = _store_with_scroll(
        ([], "cursor-1"),
        ([_record(1)], None),
    )

    result = list(store.iter_all())

    assert [item["id"] for item in result] == ["1"]
    assert store.client.scroll.call_count == 2


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_raises_when_cursor_stops_advancing():
    store = _store_with_scroll(
        ([], "stuck-cursor"),
        ([], "stuck-cursor"),
    )

    with pytest.raises(ProcessingError, match="stopped advancing"):
        list(store.iter_all())


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_raises_when_collection_not_initialized():
    """Must fail loudly: an empty scan reads the same as an empty source."""
    store = QdrantStore()

    with pytest.raises(ProcessingError, match="Collection not initialized"):
        list(store.iter_all())


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", False)
def test_iter_all_raises_when_qdrant_unavailable():
    store = QdrantStore()
    store.client = MagicMock()
    store.collection = MagicMock()

    with pytest.raises(ProcessingError):
        list(store.iter_all())


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_propagates_scroll_errors():
    store = QdrantStore()
    store.client = MagicMock()
    store.client.scroll.side_effect = RuntimeError("connection reset")
    store.collection = MagicMock()
    store.collection.collection_name = "test_collection"

    with pytest.raises(RuntimeError, match="connection reset"):
        list(store.iter_all())


@patch("semantica.vector_store.qdrant_store.QDRANT_AVAILABLE", True)
def test_iter_all_requests_payload_and_vectors():
    store = _store_with_scroll(([], None))

    list(store.iter_all())

    kwargs = store.client.scroll.call_args[1]
    assert kwargs["with_payload"] is True
    assert kwargs["with_vectors"] is True
    assert kwargs["collection_name"] == "test_collection"
