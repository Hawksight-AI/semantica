import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

from semantica.utils.exceptions import ProcessingError
from semantica.vector_store.faiss_store import (
    FAISSIndex,
    FAISSStore,
    _metadata_path,
)


def test_faiss_index_save_load_non_json_serializable_metadata(tmp_path):
    """Save/load roundtrip works with non-JSON-serializable metadata types."""
    faiss = pytest.importorskip("faiss")
    vectors = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        dtype=np.float32,
    )
    ids = ["vec_a", "vec_b"]
    now = datetime.now(timezone.utc)
    uid = uuid.uuid4()
    metadata = [
        {
            "timestamp": now,
            "uuid": uid,
            "numpy_int": np.int64(42),
            "numpy_float": np.float64(3.14),
            "a_set": {1, 2, 3},
        },
        {
            "timestamp": now,
            "uuid": uid,
            "numpy_int": np.int64(99),
            "numpy_float": np.float64(2.71),
            "a_set": {4, 5, 6},
        },
    ]

    index = FAISSIndex(faiss.IndexFlatL2(3), dimension=3)
    index.add_vectors(vectors, ids=ids)
    for vec_id, meta in zip(ids, metadata):
        index.metadata[vec_id] = meta

    index_path = tmp_path / "test_index.faiss"
    index.save(index_path)
    assert _metadata_path(index_path).exists()

    loaded_index = FAISSIndex.load(index_path, dimension=3)

    assert loaded_index.vector_ids == ids
    assert loaded_index.dimension == 3
    assert loaded_index.index_type == "flat"

    for i, vec_id in enumerate(ids):
        np.testing.assert_allclose(
            loaded_index.get_vector(vec_id), vectors[i], atol=1e-6
        )
        loaded_meta = loaded_index.get_metadata(vec_id)
        # Verify lossless restoration of all types
        assert loaded_meta["timestamp"] == now
        assert isinstance(loaded_meta["timestamp"], datetime)
        assert loaded_meta["uuid"] == uid
        assert isinstance(loaded_meta["uuid"], uuid.UUID)
        assert loaded_meta["numpy_int"] == metadata[i]["numpy_int"]
        assert isinstance(loaded_meta["numpy_int"], int)
        assert loaded_meta["numpy_float"] == float(metadata[i]["numpy_float"])
        assert isinstance(loaded_meta["numpy_float"], float)
        assert loaded_meta["a_set"] == metadata[i]["a_set"]
        assert isinstance(loaded_meta["a_set"], set)


def test_faiss_index_save_load_bytes_roundtrip(tmp_path):
    """Save/load roundtrip preserves bytes metadata via base64 encoding."""
    faiss = pytest.importorskip("faiss")
    vectors = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        dtype=np.float32,
    )
    ids = ["doc_1", "doc_2"]
    metadata = [
        {"blob": b"raw-embedding-hash"},
        {"blob": b"\x00\x01\x02\xff"},
    ]

    index = FAISSIndex(faiss.IndexFlatL2(3), dimension=3)
    index.add_vectors(vectors, ids=ids)
    for vec_id, meta in zip(ids, metadata):
        index.metadata[vec_id] = meta

    index_path = tmp_path / "test_index.faiss"
    index.save(index_path)

    loaded = FAISSIndex.load(index_path, dimension=3)
    assert loaded.metadata["doc_1"]["blob"] == b"raw-embedding-hash"
    assert isinstance(loaded.metadata["doc_1"]["blob"], bytes)
    assert loaded.metadata["doc_2"]["blob"] == b"\x00\x01\x02\xff"
    assert isinstance(loaded.metadata["doc_2"]["blob"], bytes)


def test_faiss_index_load_raises_on_vector_count_mismatch(tmp_path):
    """Loading an index with mismatched vector_ids count vs index.ntotal raises ProcessingError."""
    faiss = pytest.importorskip("faiss")
    vectors = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
        dtype=np.float32,
    )
    ids = ["vec_a", "vec_b", "vec_c"]

    index = FAISSIndex(faiss.IndexFlatL2(3), dimension=3)
    index.add_vectors(vectors, ids=ids)

    index_path = tmp_path / "test_index.faiss"
    index.save(index_path)

    # Corrupt the metadata: remove one vector_id but keep the FAISS index intact
    meta_path = _metadata_path(index_path)
    data = json.loads(meta_path.read_text())
    data["vector_ids"] = ["vec_a", "vec_b"]  # Only 2 IDs, but index has 3 vectors
    meta_path.write_text(json.dumps(data))

    with pytest.raises(ProcessingError, match="Sidecar metadata vector count.*does not match"):
        FAISSIndex.load(index_path, dimension=3)


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
    np.testing.assert_array_equal(
        page[0]["vector"], np.array([0.0, 0.0, 0.0], dtype=np.float32)
    )


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

    vectors = np.array(
        [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]], dtype=np.float32
    )
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

    store.add_vectors(
        np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32), ids=["a", "b"]
    )
    store.add_vectors(
        np.array([[1, 2, 3], [7, 8, 9]], dtype=np.float32), ids=["a", "c"]
    )

    assert store.index.vector_ids == ["a", "b", "c"]
    second_call_vectors = backend_index.add.call_args[0][0]
    assert second_call_vectors.shape[0] == 1
    np.testing.assert_array_equal(
        second_call_vectors[0], np.array([7, 8, 9], dtype=np.float32)
    )


def test_faiss_index_save_load_roundtrip_with_metadata(tmp_path):
    """vector_ids and metadata persist across a FAISSIndex save/load round-trip."""
    faiss = pytest.importorskip("faiss")
    vectors = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
        dtype=np.float32,
    )
    ids = ["vec_a", "vec_b", "vec_c"]
    metadata = [
        {"tag": "alpha", "value": 1},
        {"tag": "beta", "value": 2},
        {"tag": "gamma", "value": 3},
    ]

    index = FAISSIndex(faiss.IndexFlatL2(3), dimension=3)
    index.add_vectors(vectors, ids=ids)
    for vec_id, meta in zip(ids, metadata):
        index.metadata[vec_id] = meta

    index_path = tmp_path / "test_index.faiss"
    index.save(index_path)
    assert _metadata_path(index_path).exists()

    loaded_index = FAISSIndex.load(index_path, dimension=3)

    assert loaded_index.vector_ids == ids
    assert loaded_index.metadata == dict(zip(ids, metadata))
    assert loaded_index.dimension == 3
    assert loaded_index.index_type == "flat"

    for i, vec_id in enumerate(ids):
        np.testing.assert_allclose(
            loaded_index.get_vector(vec_id), vectors[i], atol=1e-6
        )
        assert loaded_index.get_metadata(vec_id) == metadata[i]


def test_faiss_index_load_writes_companion_json_file(tmp_path):
    """save() writes a companion .meta.json file alongside the index."""
    faiss = pytest.importorskip("faiss")
    index = FAISSIndex(faiss.IndexFlatL2(3), dimension=3)
    index.add_vectors(np.array([[1, 2, 3]], dtype=np.float32), ids=["x"])
    index.metadata["x"] = {"source": "doc"}

    index_path = tmp_path / "sub" / "dir" / "index.faiss"
    index.save(index_path)

    meta_path = _metadata_path(index_path)
    assert meta_path.exists()
    payload = json.loads(meta_path.read_text())
    assert payload["vector_ids"] == ["x"]
    assert payload["metadata"] == {"x": {"source": "doc"}}
    assert payload["dimension"] == 3
    assert payload["index_type"] == "flat"


def test_faiss_store_save_load_roundtrip_with_metadata(tmp_path):
    """FAISSStore save_index/load_index round-trip preserves IDs and metadata."""
    _ = pytest.importorskip("faiss")
    store = FAISSStore(dimension=3)
    vectors = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        dtype=np.float32,
    )
    ids = ["store_vec_1", "store_vec_2"]
    metadata = [{"source": "doc1"}, {"source": "doc2"}]

    store.add_vectors(vectors, ids=ids, metadata=metadata)

    index_path = tmp_path / "store_index.faiss"
    store.save_index(index_path)

    new_store = FAISSStore(dimension=3)
    new_store.load_index(index_path)

    assert new_store.index.vector_ids == ids
    assert new_store.index.metadata == dict(zip(ids, metadata))
    assert new_store.count() == 2

    for i, vec_id in enumerate(ids):
        np.testing.assert_allclose(new_store.get_vector(vec_id), vectors[i], atol=1e-6)
        assert new_store.get_metadata(vec_id) == metadata[i]

    results = new_store.search_similar(vectors[0], k=2)
    assert len(results) == 2
    assert results[0]["id"] == ids[0]
    assert results[0]["metadata"] == metadata[0]


def test_roundtrip_load_respects_persisted_dimension_and_index_type(tmp_path):
    """load() uses persisted dimension/index_type over caller-supplied values."""
    faiss = pytest.importorskip("faiss")
    vectors = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
    index = FAISSIndex(faiss.IndexFlatL2(3), dimension=3, index_type="flat")
    index.add_vectors(vectors, ids=["a", "b"])

    index_path = tmp_path / "index.faiss"
    index.save(index_path)

    loaded_index = FAISSIndex.load(index_path, dimension=999, index_type="hnsw")

    assert loaded_index.dimension == 3
    assert loaded_index.index_type == "flat"
    assert loaded_index.vector_ids == ["a", "b"]


def test_roundtrip_filter_by_metadata_after_reload(tmp_path):
    """filter_by_metadata works correctly on a reloaded store."""
    _ = pytest.importorskip("faiss")
    store = FAISSStore(dimension=3)
    vectors = np.array(
        [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ],
        dtype=np.float32,
    )
    ids = ["d1", "d2", "d3"]
    metadata = [
        {"source": "alpha", "tier": 1},
        {"source": "beta", "tier": 2},
        {"source": "alpha", "tier": 3},
    ]
    store.add_vectors(vectors, ids=ids, metadata=metadata)

    index_path = tmp_path / "index.faiss"
    store.save_index(index_path)

    new_store = FAISSStore(dimension=3)
    new_store.load_index(index_path)

    alpha = new_store.filter_by_metadata({"source": "alpha"})
    assert {r["id"] for r in alpha} == {"d1", "d3"}
    for r in alpha:
        assert r["metadata"]["source"] == "alpha"
        np.testing.assert_allclose(r["vector"], store.get_vector(r["id"]), atol=1e-6)

    tier = new_store.filter_by_metadata({"tier": {"min": 2}})
    assert {r["id"] for r in tier} == {"d2", "d3"}

    none_match = new_store.filter_by_metadata({"source": "gamma"})
    assert none_match == []


def test_roundtrip_scan_vectors_on_loaded_store(tmp_path):
    """scan_vectors returns restored ids and metadata on a loaded store."""
    _ = pytest.importorskip("faiss")
    store = FAISSStore(dimension=3)
    vectors = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
        dtype=np.float32,
    )
    ids = ["a", "b", "c"]
    metadata = [{"i": 0}, {"i": 1}, {"i": 2}]
    store.add_vectors(vectors, ids=ids, metadata=metadata)

    index_path = tmp_path / "index.faiss"
    store.save_index(index_path)

    new_store = FAISSStore(dimension=3)
    new_store.load_index(index_path)

    page = new_store.scan_vectors(offset=0, limit=10)
    assert [p["id"] for p in page] == ids
    for p, v, meta in zip(page, vectors, metadata):
        np.testing.assert_allclose(p["vector"], v, atol=1e-6)
        assert p["metadata"] == meta

    assert [p["id"] for p in new_store.scan_vectors(offset=1, limit=2)] == ["b", "c"]


def test_roundtrip_duplicate_check_on_loaded_store(tmp_path):
    """Re-adding existing ids on a loaded store does not duplicate vectors."""
    _ = pytest.importorskip("faiss")
    store = FAISSStore(dimension=3)
    vectors = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
    ids = ["a", "b"]
    store.add_vectors(vectors, ids=ids, metadata=[{"i": 0}, {"i": 1}])

    index_path = tmp_path / "index.faiss"
    store.save_index(index_path)

    new_store = FAISSStore(dimension=3)
    new_store.load_index(index_path)
    assert new_store.count() == 2

    new_store.add_vectors(vectors, ids=ids, metadata=[{"i": 0}, {"i": 1}])

    assert new_store.count() == 2
    assert new_store.index.vector_ids == ids
    assert new_store.index.metadata == dict(zip(ids, [{"i": 0}, {"i": 1}]))
    assert new_store.index.index.ntotal == 2


def test_faiss_store_save_load_scan_vectors_end_to_end(tmp_path):
    """End-to-end: save/load a store, then scan_vectors returns original ids and metadata."""
    _ = pytest.importorskip("faiss")
    store = FAISSStore(dimension=3)
    vectors = np.array(
        [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ],
        dtype=np.float32,
    )
    ids = ["doc_a", "doc_b", "doc_c"]
    metadata = [
        {"source": "alpha", "page": 1},
        {"source": "beta", "page": 2},
        {"source": "alpha", "page": 3},
    ]
    store.add_vectors(vectors, ids=ids, metadata=metadata)

    index_path = tmp_path / "index.faiss"
    store.save_index(index_path)

    new_store = FAISSStore(dimension=3)
    new_store.load_index(index_path)

    page = new_store.scan_vectors(offset=0, limit=10)
    assert [p["id"] for p in page] == ids
    for p, v, meta in zip(page, vectors, metadata):
        np.testing.assert_allclose(p["vector"], v, atol=1e-6)
        assert p["metadata"] == meta


def test_loading_index_without_meta_json_warns(tmp_path):
    """Loading an index with no companion .meta.json emits an explicit warning."""
    faiss = pytest.importorskip("faiss")
    index = FAISSIndex(faiss.IndexFlatL2(3), dimension=3)
    index.add_vectors(np.array([[1, 2, 3]], dtype=np.float32), ids=["x"])

    index_path = tmp_path / "index.faiss"
    index.save(index_path)
    _metadata_path(index_path).unlink()

    with pytest.warns(RuntimeWarning, match="without ID mappings"):
        loaded = FAISSIndex.load(index_path, dimension=3)

    assert loaded.vector_ids == []
    assert loaded.metadata == {}
