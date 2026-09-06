"""Facade-level contract tests for the cloud vector store backends.

Other tests here either mock a backend's internals or inject a fake into
``VectorStore._backend_store``. Both skip ``_init_backend_store``, which is
where the qdrant/pinecone/milvus/weaviate adapters are built, and that is how
#1316 shipped green while a qdrant-backed store could neither read nor write.

Gaps are recorded as strict xfail so they turn into XPASS once the wiring
lands, failing the suite until the stale marker is removed.

Related: #1265, #1019.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from semantica.vector_store import VectorStore

# Availability flag per backend, plus every symbol its connect/select path
# calls. The clients must be patched too: without the real SDK installed they
# are None, so a fixed _init_backend_store would still fail and these could
# never reach XPASS. Extend these if the wiring touches more symbols.
_AVAILABILITY_FLAG = {
    "qdrant": "semantica.vector_store.qdrant_store.QDRANT_AVAILABLE",
    "pinecone": "semantica.vector_store.pinecone_store.PINECONE_AVAILABLE",
    "milvus": "semantica.vector_store.milvus_store.MILVUS_AVAILABLE",
    "weaviate": "semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE",
}

_CLIENT_SYMBOLS = {
    "qdrant": ("semantica.vector_store.qdrant_store.QdrantClientLib",),
    "pinecone": ("semantica.vector_store.pinecone_store.PineconeClientLib",),
    "milvus": (
        "semantica.vector_store.milvus_store.connections",
        "semantica.vector_store.milvus_store.Collection",
        "semantica.vector_store.milvus_store.utility",
    ),
    "weaviate": ("semantica.vector_store.weaviate_store.weaviate",),
}

# Pinecone refuses to connect without a key, so supply a dummy one rather than
# letting a missing credential masquerade as the wiring gap.
_EXTRA_CONFIG = {"pinecone": {"api_key": "test-key"}}

CLOUD_BACKENDS = sorted(_AVAILABILITY_FLAG)

# Backends that store locally and need no connection step.
_LOCAL_BACKENDS = {"inmemory", "faiss", "sqlite", "pgvector"}

# The facade dispatches store_vectors() to `add` or `add_vectors`. Milvus
# exposes add_vectors so it already resolves; the other three name their write
# method differently and fall through to NotImplementedError.
_NO_WRITE_DISPATCH = {"qdrant", "pinecone", "weaviate"}


def _construct(backend):
    """Build a VectorStore through the real _init_backend_store path."""
    config = {"dimension": 3, **_EXTRA_CONFIG.get(backend, {})}
    with ExitStack() as stack:
        stack.enter_context(patch(_AVAILABILITY_FLAG[backend], True))
        for symbol in _CLIENT_SYMBOLS[backend]:
            stack.enter_context(patch(symbol, MagicMock()))
        return VectorStore(backend=backend, config=config)


def _live_handle(backend_store):
    """The attribute each adapter holds its connected resource in.

    Reaching into the adapter rather than asserting through the facade is
    deliberate: the facade's read methods are exactly what is broken, so there
    is no public call that distinguishes "not connected" from the other gaps.
    """
    for name in ("collection", "index"):
        if hasattr(backend_store, name):
            return getattr(backend_store, name)
    return None


def _param(backend, broken_for, reason):
    marks = [pytest.mark.xfail(strict=True, reason=reason)] if backend in broken_for else []
    return pytest.param(backend, marks=marks)


def test_roster_covers_every_supported_backend():
    """A new backend must be classified here rather than silently uncovered."""
    assert set(CLOUD_BACKENDS) | _LOCAL_BACKENDS == VectorStore.SUPPORTED_BACKENDS


@pytest.mark.parametrize("backend", CLOUD_BACKENDS)
def test_facade_constructs_an_adapter(backend):
    store = _construct(backend)

    assert store._backend_store is not None
    assert store.backend == backend


@pytest.mark.parametrize(
    "backend",
    [
        _param(b, CLOUD_BACKENDS, "_init_backend_store never connects or selects a collection")
        for b in CLOUD_BACKENDS
    ],
)
def test_backend_is_connected_after_construction(backend):
    """A constructed store should be usable without the caller reaching past
    the facade to call connect() and get_collection() itself."""
    store = _construct(backend)

    assert _live_handle(store._backend_store) is not None


@pytest.mark.parametrize(
    "backend",
    [
        _param(b, _NO_WRITE_DISPATCH, "facade dispatches only to add/add_vectors")
        for b in CLOUD_BACKENDS
    ],
)
def test_store_vectors_dispatch_resolves(backend):
    """store_vectors() should reach the backend's write method."""
    store = _construct(backend)

    try:
        store.store_vectors([np.zeros(3)], [{}], ids=["a"])
    except NotImplementedError as exc:
        pytest.fail(f"no write dispatch for {backend}: {exc}")
    except Exception:
        # Any other error means the facade found a write method and the failure
        # came from below it, which is the connection gap the test above pins.
        # Whether the write succeeds needs a live server, not this test.
        pass


def test_milvus_write_dispatch_already_resolves():
    """Control for _NO_WRITE_DISPATCH: if milvus changes, the xfail list is
    wrong rather than the feature being broken."""
    store = _construct("milvus")

    assert hasattr(store._backend_store, "add_vectors")
