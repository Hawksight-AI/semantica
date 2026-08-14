"""
Tests for SemanticaKnowledgeSource — CrewAI knowledge source backed by a
Semantica ContextGraph.

Runs with the crewai stubs installed by conftest, so ``CREWAI_AVAILABLE`` is
``True`` and the real Pydantic/BaseKnowledgeSource subclassing path (including
the current ``validate_content`` / ``add`` / ``aadd`` contract) is exercised.
"""

from __future__ import annotations

import asyncio
import unittest

from integrations.crewai import SemanticaKnowledgeSource
from integrations.crewai.knowledge_source import CREWAI_AVAILABLE, _chunk_text_manual
from semantica.context import ContextGraph


class _FakeStorage:
    def __init__(self):
        self.saved_chunks: list = []

    def save(self, chunks: list) -> None:
        self.saved_chunks.extend(chunks)

    async def asave(self, chunks: list) -> None:
        self.saved_chunks.extend(chunks)


class _RaisingStorage(_FakeStorage):
    """Mirrors real crewai: storage is wired but ``save`` raises ``ValueError``
    (e.g. the embedder has no credentials configured)."""

    def save(self, chunks: list) -> None:
        raise ValueError("The OPENAI_API_KEY environment variable is not set.")

    async def asave(self, chunks: list) -> None:
        raise ValueError("The OPENAI_API_KEY environment variable is not set.")


def _build_graph() -> ContextGraph:
    graph = ContextGraph()
    graph.add_node(node_id="privacy", node_type="policy", content="privacy policy doc")
    graph.add_node(node_id="fraud", node_type="risk", content="fraud detection rules")
    graph.add_edge(source_id="privacy", target_id="fraud", edge_type="constrains")
    return graph


class TestSemanticaKnowledgeSourceInit(unittest.TestCase):

    def test_crewai_available_via_stub(self):
        self.assertTrue(CREWAI_AVAILABLE)

    def test_is_base_knowledge_source_subclass(self):
        from crewai.knowledge.source import BaseKnowledgeSource

        self.assertTrue(issubclass(SemanticaKnowledgeSource, BaseKnowledgeSource))

    def test_creates_with_explicit_graph(self):
        graph = _build_graph()
        src = SemanticaKnowledgeSource(graph=graph)
        self.assertIs(src.graph, graph)

    def test_creates_fresh_graph_when_none(self):
        src = SemanticaKnowledgeSource()
        self.assertIsNotNone(src.graph)
        self.assertIsInstance(src.graph, ContextGraph)

    def test_default_metadata(self):
        src = SemanticaKnowledgeSource(graph=_build_graph())
        self.assertEqual(src.name, "semantica_knowledge_graph")
        self.assertEqual(src.chunk_size, 4000)
        self.assertEqual(src.chunk_overlap, 200)

    def test_custom_chunking_params(self):
        src = SemanticaKnowledgeSource(
            graph=_build_graph(), chunk_size=50, chunk_overlap=10
        )
        self.assertEqual(src.chunk_size, 50)
        self.assertEqual(src.chunk_overlap, 10)


class TestLoadContent(unittest.TestCase):

    def setUp(self):
        self.graph = _build_graph()
        self.src = SemanticaKnowledgeSource(graph=self.graph)

    def test_nodes_serialized(self):
        content = self.src.load_content()
        text = "\n".join(content.values())
        self.assertIn("privacy", text)
        self.assertIn("fraud", text)
        self.assertIn("policy", text)

    def test_edges_serialized(self):
        content = self.src.load_content()
        text = "\n".join(content.values())
        self.assertIn("-[" + "constrains" + "]->", text)

    def test_empty_graph_returns_empty(self):
        src = SemanticaKnowledgeSource(graph=ContextGraph())
        self.assertEqual(src.load_content(), {})

    def test_validate_content_passes(self):
        self.assertTrue(self.src.validate_content())

    def test_validate_content_raises_without_graph(self):
        self.src.graph = None
        with self.assertRaises(ValueError):
            self.src.validate_content()


class TestAdd(unittest.TestCase):

    def setUp(self):
        self.graph = _build_graph()
        self.src = SemanticaKnowledgeSource(
            graph=self.graph, chunk_size=40, chunk_overlap=5
        )

    def test_add_saves_chunks_to_storage(self):
        storage = _FakeStorage()
        self.src.storage = storage
        self.src.add()
        self.assertGreater(len(storage.saved_chunks), 0)
        self.assertTrue(all(isinstance(c, str) and c for c in storage.saved_chunks))

    def test_add_without_storage_keeps_chunks_in_memory(self):
        self.src.add()
        self.assertGreater(len(self.src.chunks), 0)
        self.assertGreater(len(self.src._chunks), 0)

    def test_add_wired_storage_failure_logs_error_not_debug(self):
        """Regression: real crewai raises ``ValueError`` for a missing embedder
        even though storage IS wired. That used to fall into the "storage not
        wired" DEBUG branch, silently hiding the failure — it must log an
        actionable ERROR instead."""
        self.src.storage = _RaisingStorage()
        with self.assertLogs(
            f"semantica.{SemanticaKnowledgeSource.__module__}", level="ERROR"
        ) as caught:
            self.src.add()
        joined = "\n".join(caught.output)
        self.assertIn("storage save FAILED", joined)
        self.assertIn("OPENAI_API_KEY", joined)
        self.assertGreater(len(self.src.chunks), 0)

    def test_add_empty_graph_no_chunks(self):
        src = SemanticaKnowledgeSource(
            graph=ContextGraph(), chunk_size=40, chunk_overlap=5
        )
        src.add()
        self.assertEqual(src.chunks, [])

    def test_aadd_async(self):
        storage = _FakeStorage()
        self.src.storage = storage
        asyncio.run(self.src.aadd())
        self.assertGreater(len(storage.saved_chunks), 0)

    def test_content_summary(self):
        summary = self.src.get_content_summary()
        self.assertEqual(summary["name"], "semantica_knowledge_graph")
        self.assertGreater(summary["source_count"], 0)
        self.assertTrue(summary["crewai_available"])


class TestSemanticaKnowledgeSourceSerialization(unittest.TestCase):
    """CrewAI checkpoints serialise their models via ``model_dump(mode="json")``
    — the live graph must not break that (regression for
    PydanticSerializationError on arbitrary state objects)."""

    def test_model_dump_json_excludes_graph(self):
        src = SemanticaKnowledgeSource(graph=_build_graph())
        dumped = src.model_dump(mode="json")
        self.assertNotIn("graph", dumped)
        self.assertEqual(dumped["name"], "semantica_knowledge_graph")

    def test_model_validate_restores_graph(self):
        src = SemanticaKnowledgeSource(graph=_build_graph())
        restored = SemanticaKnowledgeSource.model_validate(src.model_dump(mode="json"))
        self.assertIsInstance(restored.graph, ContextGraph)

    def test_restored_source_still_loads_content(self):
        """A checkpoint-restored source gets a fresh graph (the live graph is
        excluded from serialisation); once a graph is attached it works."""
        src = SemanticaKnowledgeSource(graph=_build_graph())
        restored = SemanticaKnowledgeSource.model_validate(src.model_dump(mode="json"))
        restored.graph = _build_graph()
        self.assertNotEqual(restored.load_content(), {})

    def test_restore_flags_lost_live_state(self):
        """A source restored from a checkpoint must signal that its live graph
        was excluded and an empty one reconstructed (``reconstructed_state``).
        Regression: an eager graph build in ``__init__`` used to hide this."""
        src = SemanticaKnowledgeSource(graph=_build_graph())
        dumped = src.model_dump(mode="json")
        self.assertTrue(dumped["had_live_state"])
        self.assertNotIn("reconstructed_state", dumped)
        restored = SemanticaKnowledgeSource.model_validate(dumped)
        self.assertTrue(restored.reconstructed_state)
        self.assertFalse(SemanticaKnowledgeSource().reconstructed_state)
        self.assertIsInstance(SemanticaKnowledgeSource().graph, ContextGraph)


class TestManualChunker(unittest.TestCase):

    def test_short_text_single_chunk(self):
        self.assertEqual(_chunk_text_manual("hello", 40, 5), ["hello"])

    def test_empty_text(self):
        self.assertEqual(_chunk_text_manual("", 40, 5), [])

    def test_long_text_overlaps(self):
        chunks = _chunk_text_manual("a" * 100, 40, 10)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 40 for c in chunks))
        # Overlap means consecutive chunks share tail/head content
        self.assertIn("a" * 10, chunks[0][-10:] + chunks[1][:10])

    def test_zero_chunk_size_guarded(self):
        self.assertEqual(_chunk_text_manual("hello world", 0, 5), ["hello world"])


if __name__ == "__main__":
    unittest.main()
