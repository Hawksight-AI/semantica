"""
Tests for AgnoSharedContext — multi-agent shared ContextGraph coordinator.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stub agno (MemoryDb needed by AgnoContextStore base)
# ---------------------------------------------------------------------------
def _stub_agno() -> None:
    if "agno" in sys.modules:
        return

    agno = types.ModuleType("agno")

    memory_pkg = types.ModuleType("agno.memory")
    memory_db_pkg = types.ModuleType("agno.memory.db")
    memory_db_base = types.ModuleType("agno.memory.db.base")
    memory_db_row = types.ModuleType("agno.memory.db.row")

    class MemoryDb:
        def __init__(self, *a, **kw): ...  # noqa: E704

    class MemoryRow:
        def __init__(self, memory, id=None, user_id=None, **kw):
            self.memory = memory
            self.id = id
            self.user_id = user_id
            self.last_updated = 0.0
            self.topics = kw.get("topics", [])

    memory_db_base.MemoryDb = MemoryDb  # type: ignore
    memory_db_row.MemoryRow = MemoryRow  # type: ignore
    memory_db_pkg.base = memory_db_base
    memory_db_pkg.row = memory_db_row
    memory_pkg.db = memory_db_pkg
    agno.memory = memory_pkg  # type: ignore

    for name, mod in [
        ("agno", agno),
        ("agno.memory", memory_pkg),
        ("agno.memory.db", memory_db_pkg),
        ("agno.memory.db.base", memory_db_base),
        ("agno.memory.db.row", memory_db_row),
    ]:
        sys.modules.setdefault(name, mod)


_stub_agno()

from integrations.agno.shared_context import AgnoSharedContext  # noqa: E402


def _make_shared(**kwargs) -> AgnoSharedContext:
    shared = AgnoSharedContext(**kwargs)
    # Replace internal AgentContext with a mock to avoid real side-effects
    mock_ctx = MagicMock()
    mock_ctx.record_decision.return_value = "shared-dec-001"
    mock_ctx.find_precedents_advanced.return_value = []
    mock_ctx.get_context_insights.return_value = {"total": 0}
    shared._context = mock_ctx
    return shared


class TestAgnoSharedContextInit(unittest.TestCase):

    def test_creates_without_args(self):
        shared = _make_shared()
        self.assertIsNotNone(shared)

    def test_session_id_auto_generated(self):
        shared = _make_shared()
        self.assertIsInstance(shared.session_id, str)
        self.assertTrue(len(shared.session_id) > 0)

    def test_explicit_session_id(self):
        shared = _make_shared(session_id="team-session-xyz")
        self.assertEqual(shared.session_id, "team-session-xyz")

    def test_decision_tracking_flag(self):
        shared = _make_shared(decision_tracking=False)
        self.assertFalse(shared.decision_tracking)

    def test_knowledge_graph_property(self):
        shared = _make_shared()
        self.assertIsNotNone(shared.knowledge_graph)

    def test_bound_roles_initially_empty(self):
        shared = _make_shared()
        self.assertEqual(shared.bound_roles, [])


class TestBindAgent(unittest.TestCase):

    def setUp(self):
        self.shared = _make_shared()

    def test_bind_returns_store(self):
        store = self.shared.bind_agent("researcher")
        self.assertIsNotNone(store)

    def test_bind_idempotent(self):
        store1 = self.shared.bind_agent("analyst")
        store2 = self.shared.bind_agent("analyst")
        self.assertIs(store1, store2)

    def test_bind_tracks_roles(self):
        self.shared.bind_agent("researcher")
        self.shared.bind_agent("analyst")
        self.assertIn("researcher", self.shared.bound_roles)
        self.assertIn("analyst", self.shared.bound_roles)

    def test_scoped_session_id(self):
        store = self.shared.bind_agent("writer")
        self.assertIn("writer", store.session_id)
        self.assertIn(self.shared.session_id, store.session_id)

    def test_different_roles_different_stores(self):
        s1 = self.shared.bind_agent("role_a")
        s2 = self.shared.bind_agent("role_b")
        self.assertIsNot(s1, s2)


class TestSharedMemoryPool(unittest.TestCase):
    """Memories written by one agent are visible to all others."""

    def setUp(self):
        self.shared = _make_shared()
        self.researcher = self.shared.bind_agent("researcher")
        self.analyst = self.shared.bind_agent("analyst")

    def _make_row(self, text: str):
        row = MagicMock()
        row.memory = text
        row.id = None
        row.user_id = "u1"
        row.last_updated = 0.0
        row.topics = []
        return row

    def test_researcher_memory_visible_to_analyst(self):
        row = self._make_row("New regulation: Basel IV applies from 2026")
        self.researcher.upsert_memory(row)

        analyst_memories = self.analyst.read_memories()
        texts = [getattr(m, "memory", "") for m in analyst_memories]
        self.assertIn("New regulation: Basel IV applies from 2026", texts)

    def test_analyst_memory_visible_to_researcher(self):
        row = self._make_row("Market share: Competitor X grew by 12%")
        self.analyst.upsert_memory(row)

        researcher_memories = self.researcher.read_memories()
        texts = [getattr(m, "memory", "") for m in researcher_memories]
        self.assertIn("Market share: Competitor X grew by 12%", texts)

    def test_both_memories_in_pool(self):
        self.researcher.upsert_memory(self._make_row("Research insight A"))
        self.analyst.upsert_memory(self._make_row("Analysis finding B"))

        # Either agent should see both
        researcher_memories = self.researcher.read_memories()
        self.assertTrue(len(researcher_memories) >= 2)

    def test_limit_respected_in_read(self):
        for i in range(5):
            self.researcher.upsert_memory(self._make_row(f"Fact {i}"))
        memories = self.analyst.read_memories(limit=2)
        self.assertTrue(len(memories) <= 2)

    def test_upsert_memory_store_failure_logs_warning(self):
        self.shared._context.store.side_effect = RuntimeError("store error")
        with self.assertLogs("semantica.integrations.agno.shared_context", level="WARNING") as cm:
            mem = self.researcher.upsert_memory(self._make_row("Test store fail"))
        self.assertIsNotNone(mem)
        self.assertIn(mem.id, self.researcher._memories)
        self.assertTrue(any("store failed:" in msg and "store error" in msg for msg in cm.output))
        self.shared._context.store.side_effect = None

    def test_upsert_memory_record_decision_failure_logs_warning(self):
        self.shared._context.record_decision.side_effect = RuntimeError("decision error")
        with self.assertLogs("semantica.integrations.agno.shared_context", level="WARNING") as cm:
            mem = self.researcher.upsert_memory(self._make_row("Test decision fail"))
        self.assertIsNotNone(mem)
        self.assertIn(mem.id, self.researcher._memories)
        self.assertTrue(any("record_decision failed:" in msg and "decision error" in msg for msg in cm.output))
        self.shared._context.record_decision.side_effect = None


class TestSharedContextDecisions(unittest.TestCase):

    def setUp(self):
        self.shared = _make_shared()

    def test_record_decision_returns_id(self):
        did = self.shared.record_decision(
            category="strategy",
            scenario="Expand to EU market",
            reasoning="Strong demand signals",
            outcome="approved",
            confidence=0.87,
        )
        self.assertEqual(did, "shared-dec-001")

    def test_agent_role_tags_category(self):
        self.shared.record_decision(
            category="finance",
            scenario="Budget allocation",
            reasoning="Q1 performance",
            outcome="increase",
            confidence=0.9,
            agent_role="cfo",
        )
        call_kwargs = self.shared._context.record_decision.call_args[1]
        self.assertIn("cfo", call_kwargs["category"])

    def test_find_precedents_returns_list(self):
        result = self.shared.find_precedents("expansion strategy")
        self.assertIsInstance(result, list)

    def test_get_shared_insights_returns_dict(self):
        result = self.shared.get_shared_insights()
        self.assertIsInstance(result, dict)


class TestSharedContextThreadSafety(unittest.TestCase):
    """Concurrent bind_agent calls should return the same store."""

    def test_concurrent_bind_same_role(self):
        import threading

        shared = _make_shared()
        results = []

        def bind():
            results.append(shared.bind_agent("concurrent_role"))

        threads = [threading.Thread(target=bind) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same store instance
        self.assertEqual(len(set(id(s) for s in results)), 1)


if __name__ == "__main__":
    unittest.main()
