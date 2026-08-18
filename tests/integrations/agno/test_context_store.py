"""
Tests for AgnoContextStore — graph-backed Agno v2 ``BaseDb``.

All tests run with or without a real Agno installation (conftest installs a
v2 stub when agno is absent) and use in-memory Semantica components only.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock


from integrations.agno.context_store import AgnoContextStore, UserMemory  # noqa: E402


def _make_memory(text: str, uid: str = "u1", **kwargs) -> UserMemory:
    return UserMemory(memory=text, user_id=uid, **kwargs)


class TestAgnoContextStoreInit(unittest.TestCase):
    """Construction and basic attribute checks."""

    def _make_store(self, **kwargs) -> AgnoContextStore:
        return AgnoContextStore(decision_tracking=True, graph_expansion=True, **kwargs)

    def test_creates_without_args(self):
        store = self._make_store()
        self.assertIsNotNone(store)

    def test_session_id_generated(self):
        store = self._make_store()
        self.assertIsInstance(store.session_id, str)
        self.assertTrue(len(store.session_id) > 0)

    def test_explicit_session_id(self):
        store = AgnoContextStore(session_id="abc-123")
        self.assertEqual(store.session_id, "abc-123")

    def test_decision_tracking_flag(self):
        store = AgnoContextStore(decision_tracking=False)
        self.assertFalse(store.decision_tracking)

    def test_context_property(self):
        store = self._make_store()
        self.assertIsNotNone(store.context)


class TestAgnoContextStoreUserMemoryGroup(unittest.TestCase):
    """BaseDb UserMemory-group protocol methods."""

    def setUp(self):
        self.store = AgnoContextStore(decision_tracking=False)

    def test_table_exists(self):
        self.assertTrue(self.store.table_exists("user_memories"))

    def test_upsert_and_read(self):
        self.store.upsert_user_memory(_make_memory("Hello world"))
        memories = self.store.get_user_memories()
        self.assertEqual(len(memories), 1)

    def test_upsert_sets_memory_id(self):
        mem = _make_memory("Test memory")
        self.store.upsert_user_memory(mem)
        self.assertIsNotNone(mem.memory_id)

    def test_upsert_sets_timestamps(self):
        mem = _make_memory("Timestamped")
        self.store.upsert_user_memory(mem)
        self.assertIsNotNone(mem.created_at)
        self.assertIsNotNone(mem.updated_at)

    def test_get_user_memory_by_id(self):
        mem = _make_memory("Fetch me")
        self.store.upsert_user_memory(mem)
        fetched = self.store.get_user_memory(mem.memory_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.memory, "Fetch me")

    def test_get_user_memory_missing_returns_none(self):
        self.assertIsNone(self.store.get_user_memory("no-such-id"))

    def test_get_user_memory_deserialize_false_returns_dict(self):
        mem = _make_memory("As dict")
        self.store.upsert_user_memory(mem)
        raw = self.store.get_user_memory(mem.memory_id, deserialize=False)
        self.assertIsInstance(raw, dict)
        self.assertEqual(raw["memory"], "As dict")

    def test_get_user_memory_user_id_mismatch(self):
        mem = _make_memory("Owned by alice", uid="alice")
        self.store.upsert_user_memory(mem)
        self.assertIsNone(self.store.get_user_memory(mem.memory_id, user_id="bob"))

    def test_delete_user_memory(self):
        mem = _make_memory("To delete")
        self.store.upsert_user_memory(mem)
        self.store.delete_user_memory(mem.memory_id)
        self.assertIsNone(self.store.get_user_memory(mem.memory_id))

    def test_delete_user_memory_wrong_user_keeps_memory(self):
        mem = _make_memory("Owned", uid="alice")
        self.store.upsert_user_memory(mem)
        self.store.delete_user_memory(mem.memory_id, user_id="bob")
        self.assertIsNotNone(self.store.get_user_memory(mem.memory_id))

    def test_delete_user_memories_bulk(self):
        ids = []
        for i in range(3):
            mem = _make_memory(f"Bulk {i}")
            self.store.upsert_user_memory(mem)
            ids.append(mem.memory_id)
        self.store.delete_user_memories(ids)
        self.assertEqual(len(self.store.get_user_memories()), 0)

    def test_get_user_memories_user_filter(self):
        self.store.upsert_user_memory(_make_memory("User A memory", uid="alice"))
        self.store.upsert_user_memory(_make_memory("User B memory", uid="bob"))

        alice_rows = self.store.get_user_memories(user_id="alice")
        self.assertEqual(len(alice_rows), 1)
        self.assertEqual(alice_rows[0].user_id, "alice")

    def test_get_user_memories_search_content(self):
        self.store.upsert_user_memory(_make_memory("Basel IV applies from 2026"))
        self.store.upsert_user_memory(_make_memory("Unrelated note"))
        rows = self.store.get_user_memories(search_content="basel")
        self.assertEqual(len(rows), 1)

    def test_get_user_memories_topics_filter(self):
        self.store.upsert_user_memory(_make_memory("Finance fact", topics=["finance"]))
        self.store.upsert_user_memory(_make_memory("Sports fact", topics=["sports"]))
        rows = self.store.get_user_memories(topics=["finance"])
        self.assertEqual(len(rows), 1)

    def test_get_user_memories_limit(self):
        for i in range(5):
            self.store.upsert_user_memory(_make_memory(f"Memory {i}"))
        rows = self.store.get_user_memories(limit=3)
        self.assertEqual(len(rows), 3)

    def test_get_user_memories_deserialize_false_returns_tuple(self):
        for i in range(4):
            self.store.upsert_user_memory(_make_memory(f"M{i}"))
        rows, total = self.store.get_user_memories(limit=2, deserialize=False)
        self.assertEqual(total, 4)
        self.assertEqual(len(rows), 2)
        self.assertIsInstance(rows[0], dict)

    def test_get_all_memory_topics(self):
        self.store.upsert_user_memory(_make_memory("A", topics=["x", "y"]))
        self.store.upsert_user_memory(_make_memory("B", topics=["y", "z"]))
        self.assertEqual(self.store.get_all_memory_topics(), ["x", "y", "z"])

    def test_get_user_memory_stats(self):
        self.store.upsert_user_memory(_make_memory("A", uid="alice", topics=["t1"]))
        self.store.upsert_user_memory(_make_memory("B", uid="alice"))
        self.store.upsert_user_memory(_make_memory("C", uid="bob"))
        rows, total = self.store.get_user_memory_stats()
        self.assertEqual(total, 2)
        alice = next(r for r in rows if r["user_id"] == "alice")
        self.assertEqual(alice["total_memories"], 2)
        self.assertEqual(alice["topics"], ["t1"])

    def test_upsert_memories_bulk(self):
        mems = [_make_memory(f"Bulk {i}") for i in range(3)]
        results = self.store.upsert_memories(mems)
        self.assertEqual(len(results), 3)
        self.assertEqual(len(self.store.get_user_memories()), 3)

    def test_upsert_memories_deserialize_false(self):
        results = self.store.upsert_memories([_make_memory("x")], deserialize=False)
        self.assertIsInstance(results[0], dict)

    def test_clear_memories(self):
        for i in range(3):
            self.store.upsert_user_memory(_make_memory(f"M{i}"))
        self.store.clear_memories()
        self.assertEqual(len(self.store.get_user_memories()), 0)


class TestAgnoContextStoreUnsupportedGroups(unittest.TestCase):
    """Non-memory BaseDb groups raise NotImplementedError (documented degradation)."""

    def setUp(self):
        self.store = AgnoContextStore(decision_tracking=False)

    def test_session_group_unsupported(self):
        with self.assertRaises(NotImplementedError):
            self.store.get_session(session_id="s1")
        with self.assertRaises(NotImplementedError):
            self.store.upsert_session(session=MagicMock())
        with self.assertRaises(NotImplementedError):
            self.store.delete_session(session_id="s1")

    def test_metrics_group_unsupported(self):
        with self.assertRaises(NotImplementedError):
            self.store.get_metrics()
        with self.assertRaises(NotImplementedError):
            self.store.calculate_metrics()

    def test_knowledge_group_unsupported(self):
        with self.assertRaises(NotImplementedError):
            self.store.get_knowledge_content(id="k1")

    def test_eval_group_unsupported(self):
        with self.assertRaises(NotImplementedError):
            self.store.get_eval_runs()

    def test_traces_group_unsupported(self):
        with self.assertRaises(NotImplementedError):
            self.store.get_traces()


class TestAgnoContextStoreExtendedAPI(unittest.TestCase):
    """Extended Semantica-specific methods."""

    def setUp(self):
        self.store = AgnoContextStore(decision_tracking=True)
        # Patch the internal AgentContext to avoid real LLM/vector calls
        self.store._context = MagicMock()
        self.store._context.record_decision.return_value = "dec-001"
        self.store._context.find_precedents_advanced.return_value = []
        self.store._context.retrieve.return_value = []

    def test_record_decision_returns_id(self):
        did = self.store.record_decision(
            category="test",
            scenario="Unit test scenario",
            reasoning="Testing",
            outcome="pass",
            confidence=0.9,
        )
        self.assertEqual(did, "dec-001")
        self.store._context.record_decision.assert_called_once()

    def test_find_precedents_returns_list(self):
        result = self.store.find_precedents("some scenario")
        self.assertIsInstance(result, list)

    def test_retrieve_returns_list(self):
        result = self.store.retrieve("query text")
        self.assertIsInstance(result, list)

    def test_record_decision_passes_entities(self):
        self.store.record_decision(
            category="finance",
            scenario="Loan",
            reasoning="Good credit",
            outcome="approved",
            confidence=0.95,
            entities=["applicant", "loan"],
        )
        call_kwargs = self.store._context.record_decision.call_args[1]
        self.assertEqual(call_kwargs["entities"], ["applicant", "loan"])

    def test_upsert_with_decision_tracking(self):
        self.store.upsert_user_memory(_make_memory("Important fact"))
        # decision should have been recorded
        self.store._context.record_decision.assert_called()


if __name__ == "__main__":
    unittest.main()
