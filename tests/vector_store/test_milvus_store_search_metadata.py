"""Tests for MilvusCollection.search() metadata fix (#1330).

The schema produced by create_collection() includes a JSON `metadata` field.
Before the fix, search() hardcoded ``"metadata": {}`` regardless of what was
stored.  After the fix it passes ``output_fields=["metadata"]`` to the Milvus
SDK and reads the actual value from ``hit.entity.get("metadata")``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers — minimal stubs so we never need a real Milvus server
# ---------------------------------------------------------------------------


def _make_hit(id_: str, distance: float, metadata: Optional[Dict[str, Any]]) -> MagicMock:
    """Return a mock Milvus search hit with a populated entity."""
    hit = MagicMock()
    hit.id = id_
    hit.distance = distance
    hit.entity.get = MagicMock(side_effect=lambda key, default=None: metadata if key == "metadata" else default)
    return hit


def _make_collection(hits_per_query: List[List[MagicMock]]) -> MagicMock:
    """Return a mock Milvus Collection whose search() yields *hits_per_query*."""
    collection = MagicMock()
    collection.search.return_value = hits_per_query
    return collection


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("milvus_available", [True])
def test_search_returns_stored_metadata(milvus_available: bool) -> None:
    """search() must return the metadata stored in the collection, not {}."""
    stored_meta = {"category": "science", "score": 0.95}
    hit = _make_hit("vec-1", 0.1, stored_meta)
    collection = _make_collection([[hit]])

    with patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", milvus_available):
        from semantica.vector_store.milvus_store import MilvusCollection

        mc = MilvusCollection.__new__(MilvusCollection)
        mc.collection = collection

        results = mc.search(
            vectors=[np.zeros(4)],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=5,
        )

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["id"] == "vec-1"
    assert results[0]["metadata"] == stored_meta, (
        "search() should return the stored metadata, not a hardcoded empty dict"
    )


def test_search_requests_metadata_output_field() -> None:
    """The underlying collection.search() call must include 'metadata' in output_fields."""
    hit = _make_hit("vec-2", 0.2, {"source": "test"})
    collection = _make_collection([[hit]])

    with patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True):
        from semantica.vector_store.milvus_store import MilvusCollection

        mc = MilvusCollection.__new__(MilvusCollection)
        mc.collection = collection

        mc.search(
            vectors=[np.zeros(4)],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=3,
        )

    call_kwargs = collection.search.call_args
    output_fields = call_kwargs.kwargs.get("output_fields") or call_kwargs[1].get("output_fields")
    assert output_fields is not None and "metadata" in output_fields, (
        "search() must pass output_fields=['metadata'] to the Milvus SDK"
    )


def test_search_falls_back_to_empty_dict_when_metadata_is_none() -> None:
    """If the entity has no metadata (e.g. legacy record), return {} not None."""
    hit = _make_hit("vec-3", 0.5, None)
    collection = _make_collection([[hit]])

    with patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True):
        from semantica.vector_store.milvus_store import MilvusCollection

        mc = MilvusCollection.__new__(MilvusCollection)
        mc.collection = collection

        results = mc.search(
            vectors=[np.zeros(4)],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=1,
        )

    assert results[0]["metadata"] == {}, "None metadata from entity should fall back to {}"


def test_search_score_calculation() -> None:
    """Verify score = 1/(1 + max(0, distance)) and distance is preserved."""
    distance = 0.4
    hit = _make_hit("vec-4", distance, {})
    collection = _make_collection([[hit]])

    with patch("semantica.vector_store.milvus_store.MILVUS_AVAILABLE", True):
        from semantica.vector_store.milvus_store import MilvusCollection

        mc = MilvusCollection.__new__(MilvusCollection)
        mc.collection = collection

        results = mc.search(
            vectors=[np.zeros(4)],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=1,
        )

    expected_score = 1.0 / (1.0 + distance)
    assert abs(results[0]["score"] - expected_score) < 1e-9
    assert results[0]["distance"] == distance
