"""
Tests for AgnoKnowledgeGraph — relational Agno v2 ``Knowledge`` with GraphRAG.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock


from integrations.agno.knowledge_graph import AgnoKnowledgeGraph  # noqa: E402


class _FakeNER:
    def extract_entities(self, text):
        e = MagicMock()
        e.name = "FakeEntity"
        e.type = "ORG"
        e.confidence = 0.9
        return [e]


class _FakeRelExtractor:
    def extract_relations(self, text, entities=None):
        r = MagicMock()
        r.source = "FakeEntity"
        r.type = "RELATED_TO"
        r.target = "OtherEntity"
        r.confidence = 0.8
        return [r]


class _FakeGraphBuilder:
    def build(self, sources):
        return MagicMock()


class _FakeContextGraph:
    def find_nodes(self, label=None):
        node = MagicMock()
        node.label = label or "Node"
        node.node_type = "Entity"
        return [node]


def _make_kg(**kwargs) -> AgnoKnowledgeGraph:
    return AgnoKnowledgeGraph(
        graph_builder=_FakeGraphBuilder(),
        ner_extractor=_FakeNER(),
        relation_extractor=_FakeRelExtractor(),
        context_graph=_FakeContextGraph(),
        **kwargs,
    )


class TestAgnoKnowledgeGraphInit(unittest.TestCase):

    def test_creates_with_defaults(self):
        kg = AgnoKnowledgeGraph()
        self.assertIsNotNone(kg)

    def test_creates_with_custom_components(self):
        kg = _make_kg()
        self.assertIsNotNone(kg)

    def test_num_documents_default(self):
        kg = AgnoKnowledgeGraph(num_documents=10)
        self.assertEqual(kg.num_documents, 10)
        self.assertEqual(kg.max_results, 10)

    def test_custom_name(self):
        kg = _make_kg(name="regulatory_kb")
        self.assertEqual(kg.name, "regulatory_kb")


class TestAgnoKnowledgeGraphLoad(unittest.TestCase):

    def setUp(self):
        self.kg = _make_kg()

    def test_load_texts(self):
        self.kg.load(texts=["Alice works at Acme Corp.", "Bob is the CEO."])
        self.assertEqual(len(self.kg._docs), 2)

    def test_load_texts_multiple_calls_accumulate(self):
        self.kg.load(texts=["First batch"])
        self.kg.load(texts=["Second batch"])
        self.assertEqual(len(self.kg._docs), 2)

    def test_load_recreate_clears_docs(self):
        self.kg.load(texts=["Old doc"])
        self.kg.load(texts=["New doc"], recreate=True)
        self.assertEqual(len(self.kg._docs), 1)

    def test_load_documents(self):
        doc = MagicMock()
        doc.content = "Agno is a multi-agent framework."
        doc.name = "agno_intro"
        self.kg.load_documents([doc])
        self.assertEqual(len(self.kg._docs), 1)

    def test_ingest_stores_entities(self):
        self.kg._ingest_text("Tesla was founded by Elon Musk.", source="test")
        stored = self.kg._docs[-1]
        self.assertIn("entities", stored)
        self.assertTrue(len(stored["entities"]) > 0)


class TestAgnoKnowledgeGraphInsert(unittest.TestCase):
    """v2 Knowledge.insert() entry point."""

    def setUp(self):
        self.kg = _make_kg()

    def test_insert_text_content(self):
        self.kg.insert(text_content="Basel IV applies from 2026.", name="basel")
        self.assertEqual(len(self.kg._docs), 1)
        self.assertEqual(self.kg._docs[0]["source"], "basel")

    def test_insert_path_file(self):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Inserted from a file.")
            tmp_path = f.name
        try:
            self.kg.insert(path=tmp_path)
            self.assertEqual(len(self.kg._docs), 1)
        finally:
            os.unlink(tmp_path)

    def test_insert_path_directory_with_include(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            for fname in ("a.txt", "b.txt", "c.md"):
                with open(os.path.join(d, fname), "w") as f:
                    f.write(f"content of {fname}")
            self.kg.insert(path=d, include=["*.txt"])
            self.assertEqual(len(self.kg._docs), 2)

    def test_insert_url_disallowed_scheme_skipped(self):
        self.kg.insert(url="file:///etc/passwd")
        self.assertEqual(len(self.kg._docs), 0)


class TestAgnoKnowledgeGraphSearch(unittest.TestCase):

    def setUp(self):
        self.kg = _make_kg()
        self.kg.load(texts=[
            "Machine learning is a subset of artificial intelligence.",
            "Python is a popular programming language.",
            "Neural networks are inspired by the human brain.",
        ])

    def test_search_returns_list(self):
        results = self.kg.search("machine learning")
        self.assertIsInstance(results, list)

    def test_search_returns_agno_documents(self):
        results = self.kg.search("python", max_results=2)
        self.assertTrue(len(results) <= 2)
        for doc in results:
            self.assertTrue(hasattr(doc, "content"))

    def test_search_empty_kg_returns_empty(self):
        kg = _make_kg()
        results = kg.search("anything")
        self.assertEqual(results, [])

    def test_search_max_results_respected(self):
        results = self.kg.search("a", max_results=1)
        self.assertTrue(len(results) <= 1)

    def test_asearch_delegates_to_search(self):
        import asyncio

        results = asyncio.run(self.kg.asearch("python", max_results=2))
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) <= 2)

    def test_get_graph_context(self):
        ctx = self.kg.get_graph_context("FakeEntity")
        self.assertIsInstance(ctx, str)


class TestAgnoKnowledgeGraphPathLoading(unittest.TestCase):
    """Test path-based loading with a temporary file."""

    def test_load_missing_path_warns(self):
        kg = _make_kg()
        # Should not raise even for non-existent path
        kg.load(path="/nonexistent/path/xyz")
        self.assertEqual(len(kg._docs), 0)

    def test_load_file(self):
        import os
        import tempfile

        kg = _make_kg()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test document content for loading.")
            tmp_path = f.name

        try:
            kg.load(path=tmp_path)
            self.assertEqual(len(kg._docs), 1)
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
