"""Tests for MilvusStore.iter_all() query-iterator enumeration.

pymilvus is not installed in this environment, so these drive the real
MilvusStore against MagicMocks, following the pattern already used for milvus
in test_backend_metadata_filtering.py.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from semantica.utils.exceptions import ProcessingError
from semantica.vector_store.milvus_store import MilvusStore


def _store_with_batches(*batches):
    """MilvusStore whose query_iterator yields the given batches then stops.

    The attribute path is doubled here: the pymilvus Collection sits at
    wrapper.collection.
    """
    store = MilvusStore()
    wrapper = MagicMock()
    inner = MagicMock()
    iterator = MagicMock()
    iterator.next.side_effect = list(batches)
    inner.query_iterator.return_value = iterator
    wrapper.collection = inner
    store.collection = wrapper
    return store, wrapper, inner, iterator


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_yields_batches_until_exhausted():
    """Exhaustion is an empty list, not StopIteration."""
    store, _, _, iterator = _store_with_batches(
        [{"id": 1, "vector": [0.1], "metadata": {}}],
        [{"id": 2, "vector": [0.2], "metadata": {}}],
        [],
    )

    result = list(store.iter_all(batch_size=1))

    assert [item["id"] for item in result] == ["1", "2"]
    assert iterator.next.call_count == 3


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_requests_the_fields_needed_for_the_result_shape():
    store, _, inner, _ = _store_with_batches([])

    list(store.iter_all(batch_size=64))

    kwargs = inner.query_iterator.call_args[1]
    assert kwargs["batch_size"] == 64
    assert kwargs["output_fields"] == ["id", "vector", "metadata"]
    # Milvus rejects an empty expression, so a match-all form is required.
    assert kwargs["expr"] == "id != ''"


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_loads_the_collection_before_querying():
    """Milvus requires a loaded collection for query operations."""
    store, wrapper, _, _ = _store_with_batches([])

    list(store.iter_all())

    assert wrapper.load.called


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_closes_the_iterator_on_exhaustion():
    store, _, _, iterator = _store_with_batches([])

    list(store.iter_all())

    assert iterator.close.called


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_closes_the_iterator_when_consumer_stops_early():
    """Abandoning the generator early must still release the iterator."""
    store, _, _, iterator = _store_with_batches(
        [{"id": 1, "vector": [0.1], "metadata": {}}],
        [{"id": 2, "vector": [0.2], "metadata": {}}],
        [],
    )

    generator = store.iter_all(batch_size=1)
    next(generator)
    assert not iterator.close.called
    generator.close()

    assert iterator.close.called


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_converts_entities_to_the_shared_result_shape():
    store, _, _, _ = _store_with_batches(
        [{"id": 7, "vector": [0.1, 0.2, 0.3], "metadata": {"tag": "x"}}], []
    )

    item = list(store.iter_all())[0]

    assert item["id"] == "7"
    assert item["metadata"] == {"tag": "x"}
    np.testing.assert_allclose(item["vector"], np.array([0.1, 0.2, 0.3]))


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_handles_missing_vector_and_metadata():
    store, _, _, _ = _store_with_batches([{"id": 1, "vector": None, "metadata": None}], [])

    item = list(store.iter_all())[0]

    assert item["metadata"] == {}
    assert item["vector"] is None


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_empty_collection_yields_nothing():
    store, _, _, _ = _store_with_batches([])

    assert list(store.iter_all()) == []


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_raises_when_query_iterator_is_unavailable():
    """Older pymilvus lacks query_iterator; falling back to query(offset=...)
    would truncate at the 16384 window."""
    store = MilvusStore()
    wrapper = MagicMock()
    wrapper.collection = MagicMock(spec=["query"])
    store.collection = wrapper

    with pytest.raises(ProcessingError, match="query_iterator"):
        list(store.iter_all())


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_raises_when_collection_not_initialized():
    """Must fail loudly: an empty scan reads the same as an empty source."""
    store = MilvusStore()

    with pytest.raises(ProcessingError, match="Collection not initialized"):
        list(store.iter_all())


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", False)
def test_iter_all_raises_when_milvus_unavailable():
    store = MilvusStore()
    store.collection = MagicMock()

    with pytest.raises(ProcessingError):
        list(store.iter_all())


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_propagates_iterator_errors():
    store, _, _, iterator = _store_with_batches()
    iterator.next.side_effect = RuntimeError("connection reset")

    with pytest.raises(RuntimeError, match="connection reset"):
        list(store.iter_all())


@patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True)
def test_iter_all_closes_the_iterator_when_a_batch_fails():
    store, _, _, iterator = _store_with_batches()
    iterator.next.side_effect = RuntimeError("connection reset")

    with pytest.raises(RuntimeError):
        list(store.iter_all())

    assert iterator.close.called
