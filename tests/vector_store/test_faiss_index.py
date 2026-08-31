from unittest.mock import MagicMock

import numpy as np
import pytest

from semantica.vector_store.faiss_store import FAISSIndex, FAISSStore


def test_get_vector_reconstructs_from_flat_l2_index():
    faiss = pytest.importorskip("faiss")
    vectors = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        dtype=np.float32,
    )
    index = FAISSIndex(faiss.IndexFlatL2(3), dimension=3)
    index.add_vectors(vectors, ids=["vec_first", "vec_target"])

    result = index.get_vector("vec_target")

    np.testing.assert_array_equal(result, vectors[1])


def test_get_vector_reconstructs_vector_at_matching_id_position():
    backend_index = MagicMock()
    backend_index.reconstruct.return_value = [0.25, 0.5, 0.75]
    index = FAISSIndex(backend_index, dimension=3)
    index.vector_ids = ["vec_first", "vec_target"]

    result = index.get_vector("vec_target")

    backend_index.reconstruct.assert_called_once_with(1)
    np.testing.assert_array_equal(result, np.array([0.25, 0.5, 0.75], dtype=np.float32))


def test_get_vector_returns_none_for_unknown_id_without_reconstructing():
    backend_index = MagicMock()
    index = FAISSIndex(backend_index, dimension=3)
    index.vector_ids = ["vec_known"]

    assert index.get_vector("vec_missing") is None
    backend_index.reconstruct.assert_not_called()


def test_get_vector_returns_none_when_index_has_no_reconstruct_method():
    index = FAISSIndex(object(), dimension=3)
    index.vector_ids = ["vec_known"]

    assert index.get_vector("vec_known") is None


@pytest.mark.parametrize(
    "error",
    [
        NotImplementedError(),
        RuntimeError("reconstruct not implemented for this type of index"),
        RuntimeError("reconstruct_from_offset not implemented"),
    ],
)
def test_get_vector_returns_none_when_reconstruction_is_unsupported(error):
    backend_index = MagicMock()
    backend_index.reconstruct.side_effect = error
    index = FAISSIndex(backend_index, dimension=3)
    index.vector_ids = ["vec_known"]

    assert index.get_vector("vec_known") is None


def test_get_vector_propagates_unexpected_runtime_errors():
    backend_index = MagicMock()
    runtime_error = RuntimeError("index is not trained")
    backend_index.reconstruct.side_effect = runtime_error
    index = FAISSIndex(backend_index, dimension=3)
    index.vector_ids = ["vec_known"]

    with pytest.raises(RuntimeError) as exc_info:
        index.get_vector("vec_known")

    assert exc_info.value is runtime_error


def test_get_vector_builds_direct_map_and_retries_when_not_initialized():
    backend_index = MagicMock()
    backend_index.reconstruct.side_effect = [
        RuntimeError("direct map not initialized"),
        [0.25, 0.5, 0.75],
    ]
    index = FAISSIndex(backend_index, dimension=3)
    index.vector_ids = ["vec_known"]

    result = index.get_vector("vec_known")

    backend_index.make_direct_map.assert_called_once_with()
    assert backend_index.reconstruct.call_count == 2
    np.testing.assert_array_equal(result, np.array([0.25, 0.5, 0.75], dtype=np.float32))


def test_get_vector_returns_none_when_direct_map_unavailable_and_not_initialized():
    backend_index = MagicMock(spec=["reconstruct"])
    backend_index.reconstruct.side_effect = RuntimeError("direct map not initialized")
    index = FAISSIndex(backend_index, dimension=3)
    index.vector_ids = ["vec_known"]

    assert index.get_vector("vec_known") is None


def test_get_vector_reconstructs_from_real_ivfflat_index_without_prior_direct_map():
    faiss = pytest.importorskip("faiss")
    dimension = 3
    vectors = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9], [1.0, 1.1, 1.2]],
        dtype=np.float32,
    )
    quantizer = faiss.IndexFlatL2(dimension)
    backend_index = faiss.IndexIVFFlat(quantizer, dimension, 2)
    backend_index.train(vectors)

    index = FAISSIndex(backend_index, dimension=dimension)
    index.add_vectors(vectors, ids=["vec_0", "vec_1", "vec_2", "vec_target"])

    result = index.get_vector("vec_target")

    np.testing.assert_allclose(result, vectors[3], atol=1e-6)


def _store_with_fake_index(ids, metadata_by_id=None):
    backend_index = MagicMock()
    backend_index.reconstruct.side_effect = lambda idx: [float(idx)] * 3
    index = FAISSIndex(backend_index, dimension=3)
    index.vector_ids = list(ids)
    index.metadata = dict(metadata_by_id or {})

    store = FAISSStore(dimension=3)
    store.index = index
    return store


def test_scan_vectors_returns_all_across_pages():
    store = _store_with_fake_index(["a", "b", "c", "d", "e"])

    seen_ids = []
    offset = 0
    while True:
        page = store.scan_vectors(offset=offset, limit=2)
        if not page:
            break
        seen_ids.extend(p["id"] for p in page)
        offset += len(page)

    assert seen_ids == ["a", "b", "c", "d", "e"]


def test_scan_vectors_includes_vector_and_metadata():
    store = _store_with_fake_index(["a"], {"a": {"tag": "only"}})

    page = store.scan_vectors(offset=0, limit=10)

    assert len(page) == 1
    assert page[0]["id"] == "a"
    assert page[0]["metadata"] == {"tag": "only"}
    np.testing.assert_array_equal(page[0]["vector"], np.array([0.0, 0.0, 0.0], dtype=np.float32))


def test_scan_vectors_no_index_returns_empty_list():
    store = FAISSStore(dimension=3)
    assert store.scan_vectors(offset=0, limit=10) == []


def test_scan_vectors_zero_limit_returns_empty_list():
    store = _store_with_fake_index(["a"])
    assert store.scan_vectors(offset=0, limit=0) == []


def test_scan_vectors_offset_past_end_returns_empty_list():
    store = _store_with_fake_index(["a"])
    assert store.scan_vectors(offset=100, limit=10) == []


def test_add_vectors_retry_with_same_ids_does_not_duplicate():
    """Re-running add_vectors with ids already in the index (e.g. retrying
    an interrupted migration) must not create a second physical vector
    under the same id."""
    backend_index = MagicMock()
    store = FAISSStore(dimension=3)
    store.index = FAISSIndex(backend_index, dimension=3)

    vectors = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]], dtype=np.float32)
    ids = ["a", "b", "c", "d"]

    store.add_vectors(vectors, ids=ids, metadata=[{"i": i} for i in range(4)])
    assert store.count() == 4

    store.add_vectors(vectors, ids=ids, metadata=[{"i": i} for i in range(4)])

    assert store.count() == 4
    assert store.index.vector_ids == ids


def test_add_vectors_retry_with_partial_overlap_only_adds_new_ids():
    backend_index = MagicMock()
    store = FAISSStore(dimension=3)
    store.index = FAISSIndex(backend_index, dimension=3)

    store.add_vectors(np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32), ids=["a", "b"])
    store.add_vectors(np.array([[1, 2, 3], [7, 8, 9]], dtype=np.float32), ids=["a", "c"])

    assert store.index.vector_ids == ["a", "b", "c"]
    second_call_vectors = backend_index.add.call_args[0][0]
    assert second_call_vectors.shape[0] == 1
    np.testing.assert_array_equal(second_call_vectors[0], np.array([7, 8, 9], dtype=np.float32))
