import gc
import importlib
from unittest.mock import patch

import pytest

from semantica.semantic_extract.triplet_extractor import Triplet
from semantica.triplet_store import OxigraphStore, TripletStore
from semantica.utils.exceptions import ProcessingError, ValidationError

pytest.importorskip("pyoxigraph")


EX = "http://example.org/"


def _store(**config):
    return TripletStore(
        backend="oxigraph",
        enable_caching=False,
        enable_optimization=False,
        **config,
    )


def test_memory_store_crud_preserves_literal_metadata():
    store = _store()
    triplets = [
        Triplet(EX + "alice", EX + "knows", EX + "bob"),
        Triplet(
            EX + "alice",
            EX + "name",
            "Alice",
            metadata={"language": "en"},
        ),
        Triplet(
            EX + "alice",
            EX + "age",
            "42",
            metadata={"datatype": "xsd:integer"},
        ),
    ]

    result = store.add_triplets(triplets)

    assert result == {
        "success": True,
        "total": 3,
        "processed": 3,
        "failed": 0,
        "batches": 1,
    }
    saved = store.get_triplets(subject=EX + "alice")
    assert len(saved) == 3
    assert (
        next(t for t in saved if t.predicate == EX + "name").metadata["language"]
        == "en"
    )
    assert (
        next(t for t in saved if t.predicate == EX + "age").metadata["datatype"]
        == "http://www.w3.org/2001/XMLSchema#integer"
    )

    store.delete_triplet(triplets[0])

    assert store.get_triplets(predicate=EX + "knows") == []


def test_named_graphs_are_isolated_for_crud_and_queries():
    store = _store()
    default_triplet = Triplet(EX + "default", EX + "label", "default")
    named_triplet = Triplet(EX + "named", EX + "label", "named")
    graph = EX + "graphs/agents"

    store.add_triplet(default_triplet)
    store.add_triplet(named_triplet, graph=graph)

    assert [t.subject for t in store.get_triplets()] == [default_triplet.subject]
    assert [t.subject for t in store.get_triplets(graph=graph)] == [
        named_triplet.subject
    ]

    result = store.execute_query(
        "SELECT ?s WHERE { ?s <http://example.org/label> ?label }",
        graph=graph,
    )
    assert [row["s"]["value"] for row in result.bindings] == [named_triplet.subject]


def test_select_ask_and_construct_result_shapes():
    backend = OxigraphStore()
    backend.add_triplet(
        Triplet(
            EX + "alice",
            EX + "name",
            "Alice",
            metadata={"language": "en"},
        )
    )

    selected = backend.execute_sparql(
        "SELECT ?name WHERE { <http://example.org/alice> "
        "<http://example.org/name> ?name }"
    )
    assert selected["variables"] == ["name"]
    assert selected["bindings"] == [
        {"name": {"type": "literal", "value": "Alice", "xml:lang": "en"}}
    ]

    asked = backend.execute_sparql("ASK { ?s ?p ?o }")
    assert asked["metadata"]["boolean"] is True

    constructed = backend.execute_sparql("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")
    assert constructed["variables"] == []
    assert constructed["triples"] == [
        (EX + "alice", EX + "name", "Alice", {"language": "en"})
    ]


def test_on_disk_store_survives_reopen(tmp_path):
    path = tmp_path / "oxigraph"
    first = OxigraphStore(path=path)
    first.add_triplet(Triplet(EX + "alice", EX + "knows", EX + "bob"))
    first.flush()
    del first
    gc.collect()

    reopened = OxigraphStore(path=path)

    assert len(reopened.get_triplets()) == 1
    assert reopened.get_triplets()[0].object == EX + "bob"


def test_invalid_result_format_is_rejected():
    backend = OxigraphStore()

    with pytest.raises(ValidationError, match="Invalid result_format"):
        backend.execute_sparql("SELECT * WHERE { ?s ?p ?o }", result_format="csv")


def test_invalid_rdf_term_is_reported_as_processing_error():
    backend = OxigraphStore()

    with pytest.raises(ProcessingError, match="Oxigraph load failed"):
        backend.add_triplet(Triplet("not an iri", EX + "predicate", "value"))


def test_missing_optional_dependency_has_install_hint():
    real_import_module = importlib.import_module

    def import_without_oxigraph(name, package=None):
        if name == "pyoxigraph":
            raise ModuleNotFoundError(name)
        return real_import_module(name, package)

    with patch(
        "semantica.triplet_store.oxigraph_store.importlib.import_module",
        side_effect=import_without_oxigraph,
    ):
        with pytest.raises(ImportError, match="tripletstore-oxigraph"):
            _store()


def test_on_disk_add_triplets_calls_flush(tmp_path):
    """add_triplets on a disk-backed store must flush once after the batch.

    The pyoxigraph background-thread flush "might lag a little bit"; an
    explicit flush after the batch closes that race without fsyncing on
    every individual write.  This test verifies the contract directly
    without relying on CPython destructor timing.
    """
    store = OxigraphStore(path=tmp_path / "oxigraph")
    with patch.object(store, "flush") as mock_flush:
        store.add_triplets([
            Triplet(EX + "alice", EX + "knows", EX + "bob"),
            Triplet(EX + "bob", EX + "knows", EX + "carol"),
        ])
    mock_flush.assert_called_once()


def test_on_disk_add_triplet_does_not_flush(tmp_path):
    """add_triplet (single write) must NOT flush on every call.

    Individual writes are committed to the store in memory; the caller is
    responsible for calling flush() when a hard durability boundary is
    needed.  Flushing on every add_triplet() call would fsync on every
    write, causing a severe throughput regression for workloads that write
    triplets one at a time.
    """
    store = OxigraphStore(path=tmp_path / "oxigraph")
    with patch.object(store, "flush") as mock_flush:
        store.add_triplet(Triplet(EX + "alice", EX + "knows", EX + "bob"))
    mock_flush.assert_not_called()


def test_in_memory_add_triplets_does_not_flush(tmp_path):
    """In-memory stores must not call flush() — there is nothing to flush."""
    store = OxigraphStore()  # no path → in-memory
    with patch.object(store, "flush") as mock_flush:
        store.add_triplet(Triplet(EX + "alice", EX + "knows", EX + "bob"))
        store.add_triplets([Triplet(EX + "bob", EX + "knows", EX + "carol")])
    mock_flush.assert_not_called()


def test_on_disk_add_triplets_is_durable_on_reopen(tmp_path):
    """End-to-end durability: a batch written via add_triplets and closed
    cleanly survives a reopen.

    This is an integration test for the full add_triplets → flush → close →
    reopen lifecycle.  The durability contract here is provided by the
    explicit ``store.flush()`` call before deletion; the internal flush
    inside add_triplets reduces (but does not eliminate) the crash-window
    race.  The authoritative unit test for the internal flush behaviour is
    ``test_on_disk_add_triplets_calls_flush``.
    """
    path = tmp_path / "oxigraph"
    store = OxigraphStore(path=path)
    store.add_triplets([
        Triplet(EX + "alice", EX + "knows", EX + "bob"),
        Triplet(EX + "bob", EX + "knows", EX + "carol"),
    ])
    store.flush()   # belt-and-suspenders: ensures close is clean
    del store
    gc.collect()

    reopened = OxigraphStore(path=path)
    assert len(reopened.get_triplets()) == 2


def test_storage_path_is_accepted_as_alias_for_path(tmp_path):
    """Regression: ``storage_path=...`` used to be silently swallowed by
    ``**config`` (the __init__ parameter is named ``path``), so the store
    silently degraded to in-memory with no warning. It must now be accepted
    as an alias consistent with other Semantica stores (e.g. ProvenanceManager)."""
    storage_path = tmp_path / "oxigraph"

    store = OxigraphStore(storage_path=str(storage_path))

    assert store.path == str(storage_path)
    # and it must actually persist (proves the alias wired through to the
    # on-disk path, not just set the attribute)
    store.add_triplet(Triplet(EX + "alice", EX + "knows", EX + "bob"))
    del store
    gc.collect()

    reopened = OxigraphStore(storage_path=str(storage_path))
    assert len(reopened.get_triplets()) == 1
