"""Tests for ErasureCoordinator (issue #1018).

``ContextGraph.purge_node()`` is graph-scope by design: it removes the node and
writes a tombstone attesting the content is gone, while the same content can
survive verbatim as an ``AgentMemory`` item and as an embedding. The
coordinator drives the cascade across every bound store and returns a receipt
saying what was reached -- and, just as importantly, what was not.

These tests run against real ``ContextGraph`` and ``AgentMemory`` instances
rather than mocks. The bug this feature exists to prevent lives in the
interaction between them (``find_by_entity`` truncating the sweep the caller
uses to decide the erasure is done), so mocking that interaction away would
test nothing. The vector stores *are* fakes, because the point of those tests
is backend shape -- ``delete_vectors`` vs ``delete`` vs neither -- and three of
the real backends cannot delete at all.
"""

import json
import unittest

import numpy as np

from semantica.context import AgentMemory, ContextGraph
from semantica.context.erasure import (
    STATUS_ERASED,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
    STATUS_NOT_FOUND,
    STATUS_UNSUPPORTED,
    ErasureCoordinator,
    ErasureReceipt,
)
from semantica.vector_store import VectorStore


def _graph():
    """customer --purchased--> order, plus an unrelated supplier."""
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("customer-4471", "person")
    graph.add_node("order-9", "order")
    graph.add_node("supplier-1", "org")
    graph.add_edge("customer-4471", "order-9", "purchased")
    return graph


def _memory_with(entity_id, count, extra_entity=None):
    """A memory holding ``count`` items that reference ``entity_id``."""
    memory = AgentMemory()
    for index in range(count):
        memory.store(
            f"note {index} about {entity_id}",
            entities=[{"id": entity_id, "name": entity_id}],
            skip_graph=True,
        )
    if extra_entity:
        memory.store(
            f"unrelated note about {extra_entity}",
            entities=[{"id": extra_entity, "name": extra_entity}],
            skip_graph=True,
        )
    return memory


class _DeleteVectorsStore:
    """Backend shaped like qdrant/pinecone: exposes ``delete_vectors``."""

    backend = "qdrant"

    def __init__(self, result=True):
        self._result = result
        self.deleted = []

    def delete_vectors(self, vector_ids, **options):
        self.deleted.append(list(vector_ids))
        return self._result


class _DeleteStore:
    """Backend shaped like pgvector/sqlite-vec: exposes ``delete``."""

    backend = "pgvector"

    def __init__(self):
        self.deleted = []

    def delete(self, ids):
        self.deleted.append(list(ids))
        return True


class _NoDeleteStore:
    """Backend shaped like FAISS/Milvus/Weaviate: no delete surface at all."""

    backend = "faiss"


class _RaisingStore:
    backend = "qdrant"

    def delete_vectors(self, vector_ids, **options):
        raise RuntimeError("connection reset")


class _FacadeOverNoDeleteBackend:
    """The ``VectorStore`` facade shape: declares delete_vectors for every
    backend and only fails on the call, so the backend must be probed."""

    backend = "faiss"

    def __init__(self):
        self._backend_store = _NoDeleteStore()

    def delete_vectors(self, vector_ids, **options):
        raise NotImplementedError("Backend store _NoDeleteStore has no delete")


class _MemoryVectorStore(_DeleteVectorsStore):
    """Delete-capable store that AgentMemory can also write embeddings to."""

    def store_vectors(self, vectors, metadata=None, **options):
        return [f"vec-{len(self.deleted)}-{index}" for index in range(len(vectors))]


class TestErasureAcrossStores(unittest.TestCase):
    def test_erases_graph_and_memory_and_reports_both(self):
        graph, memory = _graph(), _memory_with("customer-4471", 3, "supplier-1")
        receipt = ErasureCoordinator(graph=graph, memory=memory).erase_entity(
            "customer-4471", reason="GDPR Art. 17 request #882"
        )

        self.assertTrue(receipt.complete)
        self.assertEqual(receipt.stores["graph"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["graph"]["edges"], 1)
        self.assertEqual(receipt.stores["memory"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["memory"]["items"], 3)

        self.assertFalse(graph.has_node("customer-4471"))
        self.assertEqual(memory.find_by_entity("customer-4471", limit=500), [])

    def test_leaves_other_entities_alone(self):
        graph, memory = _graph(), _memory_with("customer-4471", 2, "supplier-1")
        ErasureCoordinator(graph=graph, memory=memory).erase_entity("customer-4471")

        self.assertTrue(graph.has_node("supplier-1"))
        self.assertEqual(len(memory.find_by_entity("supplier-1", limit=500)), 1)

    def test_graph_purge_records_the_reason_in_its_tombstone(self):
        graph = _graph()
        ErasureCoordinator(graph=graph).erase_entity(
            "customer-4471", reason="GDPR Art. 17 request #882"
        )

        tombstone = graph.get_tombstone("customer-4471", "node")
        self.assertIsNotNone(tombstone)
        self.assertEqual(tombstone["reason"], "GDPR Art. 17 request #882")

    def test_erase_entities_returns_one_receipt_per_id_in_order(self):
        graph = _graph()
        receipts = ErasureCoordinator(graph=graph).erase_entities(
            ["customer-4471", "supplier-1", "never-existed"], reason="offboarding"
        )

        self.assertEqual(
            [receipt.entity_id for receipt in receipts],
            ["customer-4471", "supplier-1", "never-existed"],
        )
        self.assertEqual(receipts[0].stores["graph"]["status"], STATUS_ERASED)
        self.assertEqual(receipts[1].stores["graph"]["status"], STATUS_ERASED)
        self.assertEqual(receipts[2].stores["graph"]["status"], STATUS_NOT_FOUND)


class TestMemorySweepIsNotTruncated(unittest.TestCase):
    """The regression this feature exists to prevent.

    ``find_by_entity`` has historically defaulted to ``limit=10`` and truncated
    silently, so the obvious hand-rolled cascade erases the first ten items and
    reports success. 25 items is more than any such default, and a coordinator
    that calls ``find_by_entity`` once with the default fails this test.
    """

    def test_erases_far_more_items_than_the_default_limit(self):
        memory = _memory_with("customer-4471", 25)
        receipt = ErasureCoordinator(memory=memory).erase_entity("customer-4471")

        self.assertEqual(receipt.stores["memory"]["items"], 25)
        self.assertEqual(memory.find_by_entity("customer-4471", limit=500), [])
        self.assertTrue(receipt.complete)

    def test_residual_items_are_reported_as_failed_not_erased(self):
        class _UndeletableMemory:
            """Deletes nothing, as a backend refusing the write would."""

            def __init__(self):
                self.items = [{"memory_id": f"m{i}"} for i in range(3)]

            def find_by_entity(self, entity_id, limit=10):
                return list(self.items)[:limit]

            def batch_delete(self, memory_ids):
                return 0

        receipt = ErasureCoordinator(memory=_UndeletableMemory()).erase_entity("e1")

        self.assertEqual(receipt.stores["memory"]["status"], STATUS_FAILED)
        self.assertEqual(receipt.stores["memory"]["residual"], 3)
        self.assertFalse(receipt.complete)

    def test_memory_items_without_an_identifier_fail_rather_than_look_erased(self):
        class _AnonymousMemory:
            def find_by_entity(self, entity_id, limit=10):
                return [{"content": "no id here"}]

            def batch_delete(self, memory_ids):  # pragma: no cover - never reached
                raise AssertionError("should not delete items it cannot identify")

        receipt = ErasureCoordinator(memory=_AnonymousMemory()).erase_entity("e1")

        self.assertEqual(receipt.stores["memory"]["status"], STATUS_FAILED)
        self.assertFalse(receipt.complete)


class TestVectorBackendShapes(unittest.TestCase):
    def test_delete_vectors_backend_is_erased(self):
        store = _DeleteVectorsStore()
        receipt = ErasureCoordinator(vector_store=store).erase_entity("customer-4471")

        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["vectors"]["via"], "delete_vectors")
        self.assertEqual(store.deleted, [["customer-4471"]])

    def test_delete_backend_is_erased(self):
        store = _DeleteStore()
        receipt = ErasureCoordinator(vector_store=store).erase_entity("customer-4471")

        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["vectors"]["via"], "delete")
        self.assertEqual(store.deleted, [["customer-4471"]])

    def test_backend_without_delete_is_unsupported_not_erased(self):
        receipt = ErasureCoordinator(vector_store=_NoDeleteStore()).erase_entity("e1")

        vectors = receipt.stores["vectors"]
        self.assertEqual(vectors["status"], STATUS_UNSUPPORTED)
        self.assertEqual(vectors["backend"], "faiss")
        self.assertIn("no delete", vectors["detail"])
        self.assertFalse(receipt.complete)

    def test_facade_declaring_delete_over_a_delete_less_backend_is_unsupported(self):
        receipt = ErasureCoordinator(
            vector_store=_FacadeOverNoDeleteBackend()
        ).erase_entity("e1")

        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_UNSUPPORTED)
        self.assertFalse(receipt.complete)

    def test_store_reporting_no_deletion_is_failed(self):
        store = _DeleteVectorsStore(result=False)
        receipt = ErasureCoordinator(vector_store=store).erase_entity("e1")

        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_FAILED)
        self.assertFalse(receipt.complete)

    def test_explicit_vector_ids_override_the_entity_id(self):
        store = _DeleteVectorsStore()
        ErasureCoordinator(vector_store=store).erase_entity(
            "customer-4471", vector_ids=["vec-a", "vec-b"]
        )

        self.assertEqual(store.deleted, [["vec-a", "vec-b"]])

    def test_vector_store_defaults_to_the_one_memory_holds(self):
        store = _MemoryVectorStore()
        memory = AgentMemory(vector_store=store)

        self.assertIs(ErasureCoordinator(memory=memory).vector_store, store)

    def test_memory_bound_vector_store_can_be_overridden(self):
        owned, external = _MemoryVectorStore(), _DeleteVectorsStore()
        memory = AgentMemory(vector_store=owned)

        coordinator = ErasureCoordinator(memory=memory, vector_store=external)

        self.assertIs(coordinator.vector_store, external)

    def test_vector_leg_can_be_disabled_for_a_memory_bound_store(self):
        memory = AgentMemory(vector_store=_MemoryVectorStore())
        coordinator = ErasureCoordinator(memory=memory, vector_store=False)

        receipt = coordinator.erase_entity("customer-4471")

        self.assertIsNone(coordinator.vector_store)
        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_NOT_CONFIGURED)


class TestPartialFailureIsAResultNotAnException(unittest.TestCase):
    def test_a_raising_vector_store_does_not_stop_the_remaining_legs(self):
        graph, memory = _graph(), _memory_with("customer-4471", 4)
        receipt = ErasureCoordinator(
            graph=graph, memory=memory, vector_store=_RaisingStore()
        ).erase_entity("customer-4471")

        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_FAILED)
        self.assertIn("RuntimeError", receipt.stores["vectors"]["detail"])
        # The legs after the failure still ran.
        self.assertEqual(receipt.stores["memory"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["graph"]["status"], STATUS_ERASED)
        self.assertFalse(graph.has_node("customer-4471"))
        self.assertFalse(receipt.complete)
        self.assertEqual(receipt.incomplete_stores, ["vectors"])

    def test_a_raising_graph_is_reported_after_memory_was_erased(self):
        class _RaisingGraph:
            def find_edges(self):
                return []

            def purge_node(self, node_id, reason=None, at=None):
                raise RuntimeError("graph store unavailable")

        memory = _memory_with("customer-4471", 2)
        receipt = ErasureCoordinator(graph=_RaisingGraph(), memory=memory).erase_entity(
            "customer-4471"
        )

        self.assertEqual(receipt.stores["memory"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["graph"]["status"], STATUS_FAILED)
        self.assertFalse(receipt.complete)


class TestReceipt(unittest.TestCase):
    def test_unconfigured_stores_are_reported_and_still_count_as_complete(self):
        receipt = ErasureCoordinator(graph=_graph()).erase_entity("customer-4471")

        self.assertEqual(receipt.stores["memory"]["status"], STATUS_NOT_CONFIGURED)
        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_NOT_CONFIGURED)
        self.assertTrue(receipt.complete)

    def test_erasing_a_second_time_reports_nothing_left_rather_than_raising(self):
        graph, memory = _graph(), _memory_with("customer-4471", 3)
        coordinator = ErasureCoordinator(graph=graph, memory=memory)
        coordinator.erase_entity("customer-4471")

        second = coordinator.erase_entity("customer-4471")

        self.assertEqual(second.stores["graph"]["status"], STATUS_NOT_FOUND)
        self.assertEqual(second.stores["memory"]["status"], STATUS_NOT_FOUND)
        self.assertTrue(second.complete)

    def test_to_dict_round_trips_the_reported_shape(self):
        graph = _graph()
        receipt = ErasureCoordinator(graph=graph).erase_entity(
            "customer-4471",
            reason="GDPR Art. 17 request #882",
            at="2026-08-16T00:00:00Z",
        )
        payload = receipt.to_dict()

        self.assertEqual(payload["entity_id"], "customer-4471")
        self.assertEqual(payload["reason"], "GDPR Art. 17 request #882")
        self.assertEqual(payload["erased_at"], "2026-08-16T00:00:00")
        self.assertTrue(payload["complete"])
        self.assertEqual(set(payload["stores"]), {"graph", "memory", "vectors"})

    def test_to_dict_copies_the_store_results(self):
        receipt = ErasureCoordinator(graph=_graph()).erase_entity("customer-4471")

        payload = receipt.to_dict()
        payload["stores"]["graph"]["status"] = "tampered"

        self.assertEqual(receipt.stores["graph"]["status"], STATUS_ERASED)

    def test_receipt_and_tombstone_agree_on_when_the_erasure_happened(self):
        graph = _graph()
        receipt = ErasureCoordinator(graph=graph).erase_entity(
            "customer-4471", at="2026-08-16T00:00:00Z"
        )

        tombstone = graph.get_tombstone("customer-4471", "node")
        self.assertEqual(tombstone["purged_at"], "2026-08-16T00:00:00")
        self.assertEqual(receipt.erased_at, tombstone["purged_at"])

    def test_receipt_and_tombstone_agree_when_no_at_is_given(self):
        """The default path, where the drift actually happens.

        With `at=None` the coordinator and `purge_node()` would each take their
        own `now()`, so the receipt attested to a different instant than the
        tombstone it points at. Passing an explicit `at` hides this, which is
        why the test above passed while the common case was wrong.
        """
        graph = _graph()
        receipt = ErasureCoordinator(graph=graph).erase_entity("customer-4471")

        tombstone = graph.get_tombstone("customer-4471", "node")
        self.assertEqual(receipt.erased_at, tombstone["purged_at"])

    def test_epoch_seconds_are_accepted_like_the_graph_accepts_them(self):
        graph = _graph()
        receipt = ErasureCoordinator(graph=graph).erase_entity(
            "customer-4471", at=1755302400
        )

        tombstone = graph.get_tombstone("customer-4471", "node")
        self.assertEqual(receipt.erased_at, tombstone["purged_at"])
        self.assertTrue(receipt.erased_at.startswith("2025-"))

    def test_an_unparseable_at_is_rejected_before_any_store_is_touched(self):
        graph, memory = _graph(), _memory_with("customer-4471", 2)

        with self.assertRaises(ValueError):
            ErasureCoordinator(graph=graph, memory=memory).erase_entity(
                "customer-4471", at="not-a-timestamp"
            )

        self.assertTrue(graph.has_node("customer-4471"))
        self.assertEqual(len(memory.find_by_entity("customer-4471", limit=500)), 2)

    def test_incomplete_stores_names_every_store_still_holding_data(self):
        receipt = ErasureReceipt(
            entity_id="e1",
            stores={
                "vectors": {"status": STATUS_UNSUPPORTED},
                "memory": {"status": STATUS_FAILED},
                "graph": {"status": STATUS_ERASED},
            },
        )

        self.assertEqual(sorted(receipt.incomplete_stores), ["memory", "vectors"])
        self.assertFalse(receipt.complete)


class TestRealVectorStoreBackend(unittest.TestCase):
    """The fakes above assert the shapes the coordinator expects; these assert
    that a real backend actually has one of them.

    This repo's recurring failure is a change verified only against the default
    that reaches for internals and breaks on every other backend, so the fake
    stores are worth exactly as much as the assumption that a real store looks
    like them. ``VectorStore(backend="inmemory")`` is the one backend that runs
    without external services, so it is the one that can hold that assumption
    to account here.
    """

    def _store(self):
        return VectorStore(backend="inmemory", dimension=8)

    def test_real_backend_erases_the_vector_ids_it_is_given(self):
        store = self._store()
        vector_ids = store.store_vectors(
            vectors=[np.ones(8), np.zeros(8)], metadata=[{}, {}]
        )
        self.assertEqual(store.count(), 2)

        receipt = ErasureCoordinator(vector_store=store).erase_entity(
            "customer-4471", vector_ids=vector_ids
        )

        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["vectors"]["backend"], "inmemory")
        self.assertEqual(store.count(), 0)

    def test_the_full_cascade_removes_a_real_memory_bound_embedding(self):
        """The end-to-end case the receipt actually attests to.

        Real ``ContextGraph``, real ``AgentMemory``, real ``VectorStore`` --
        the embedding is written by ``AgentMemory.store()`` and has to be gone
        afterwards, which exercises the memory leg's own ``delete_memory()``
        vector cascade rather than the coordinator's model of it.
        """
        store, graph = self._store(), _graph()
        memory = AgentMemory(vector_store=store)
        memory.store(
            "note about customer-4471",
            entities=[{"id": "customer-4471", "name": "customer-4471"}],
            skip_graph=True,
        )
        self.assertEqual(store.count(), 1)

        receipt = ErasureCoordinator(graph=graph, memory=memory).erase_entity(
            "customer-4471", reason="GDPR Art. 17 request #882"
        )

        self.assertTrue(receipt.complete)
        self.assertEqual(receipt.stores["memory"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["graph"]["status"], STATUS_ERASED)
        self.assertEqual(store.count(), 0)
        self.assertFalse(graph.has_node("customer-4471"))
        self.assertEqual(memory.find_by_entity("customer-4471", limit=500), [])

    def test_erased_means_the_store_accepted_the_delete_not_that_data_existed(self):
        """Pins a limit of the receipt worth knowing before trusting it.

        The in-memory backend pops the ids and returns ``True`` whether or not
        they were there, and no backend offers a portable "did this id exist"
        check, so the vectors leg reports how many ids the store accepted --
        not how many embeddings were really removed. ``erased`` on this leg is
        therefore weaker than on the memory leg, which re-queries to confirm.
        """
        store = self._store()

        receipt = ErasureCoordinator(vector_store=store).erase_entity("never-embedded")

        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_ERASED)
        self.assertEqual(receipt.stores["vectors"]["vector_ids"], 1)
        self.assertEqual(store.count(), 0)


class TestConstruction(unittest.TestCase):
    def test_a_coordinator_with_no_stores_is_rejected(self):
        with self.assertRaises(ValueError):
            ErasureCoordinator()

    def test_a_single_store_is_enough(self):
        self.assertIsNotNone(ErasureCoordinator(graph=_graph()))
        self.assertIsNotNone(ErasureCoordinator(memory=AgentMemory()))
        self.assertIsNotNone(ErasureCoordinator(vector_store=_DeleteStore()))

    def test_a_falsey_vector_store_is_still_a_store(self):
        """An empty store defining __len__ is falsey but perfectly valid."""

        class _EmptyButReal(_DeleteVectorsStore):
            def __len__(self):
                return 0

        store = _EmptyButReal()
        coordinator = ErasureCoordinator(vector_store=store)

        self.assertIs(coordinator.vector_store, store)
        receipt = coordinator.erase_entity("customer-4471")
        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_ERASED)


class TestBackendDeleteResults(unittest.TestCase):
    """Backends report deletes as dicts, not bools.

    Qdrant returns ``{"status": <UpdateStatus>}`` and Pinecone
    ``{"deleted": True}``, so a bare ``result is False`` check calls every dict
    a success and throws away the only account of the delete the caller gets.
    """

    def _store_returning(self, value):
        store = _DeleteVectorsStore(result=value)
        return store, ErasureCoordinator(vector_store=store)

    def test_qdrant_shaped_success_dict_is_erased_and_kept(self):
        _, coordinator = self._store_returning({"status": "completed"})

        vectors = coordinator.erase_entity("e1").stores["vectors"]

        self.assertEqual(vectors["status"], STATUS_ERASED)
        self.assertEqual(vectors["backend_result"], {"status": "completed"})

    def test_pinecone_shaped_success_dict_is_erased(self):
        _, coordinator = self._store_returning({"deleted": True})

        self.assertEqual(
            coordinator.erase_entity("e1").stores["vectors"]["status"], STATUS_ERASED
        )

    def test_explicit_failure_marker_in_a_dict_is_failed(self):
        for payload in ({"deleted": False}, {"success": False}, {"status": "failed"}):
            with self.subTest(payload=payload):
                _, coordinator = self._store_returning(payload)

                receipt = coordinator.erase_entity("e1")

                self.assertEqual(receipt.stores["vectors"]["status"], STATUS_FAILED)
                self.assertFalse(receipt.complete)

    def test_an_enum_like_failure_status_is_not_read_as_success(self):
        class _UpdateStatus:
            def __str__(self):
                return "UpdateStatus.FAILED"

        _, coordinator = self._store_returning({"status": _UpdateStatus()})

        receipt = coordinator.erase_entity("e1")

        self.assertEqual(receipt.stores["vectors"]["status"], STATUS_FAILED)
        # Rendered as a string so the receipt stays serializable as an audit record.
        self.assertEqual(
            receipt.stores["vectors"]["backend_result"],
            {"status": "UpdateStatus.FAILED"},
        )
        json.dumps(receipt.to_dict())

    def test_a_zero_count_return_is_not_mistaken_for_False(self):
        """`0 == False` in Python; a store reporting "0 rows" is not a failure."""
        _, coordinator = self._store_returning({"deleted": 0})

        self.assertEqual(
            coordinator.erase_entity("e1").stores["vectors"]["status"], STATUS_ERASED
        )

    def test_a_void_delete_returning_None_is_accepted(self):
        """Reporting `failed` for a void method would be a false alarm."""
        _, coordinator = self._store_returning(None)

        self.assertEqual(
            coordinator.erase_entity("e1").stores["vectors"]["status"], STATUS_ERASED
        )


if __name__ == "__main__":
    unittest.main()
