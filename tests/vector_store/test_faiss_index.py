from unittest.mock import MagicMock

import numpy as np
import pytest

from semantica.vector_store.faiss_store import FAISSIndex


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


@pytest.mark.parametrize("error", [NotImplementedError(), RuntimeError()])
def test_get_vector_returns_none_when_reconstruction_is_unsupported(error):
    backend_index = MagicMock()
    backend_index.reconstruct.side_effect = error
    index = FAISSIndex(backend_index, dimension=3)
    index.vector_ids = ["vec_known"]

    assert index.get_vector("vec_known") is None
