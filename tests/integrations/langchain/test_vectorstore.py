"""
Unit tests for SemanticaVectorStore.
"""

from __future__ import annotations

import pytest

# Skip tests if langchain_core is not installed
pytest.importorskip("langchain_core")

import unittest
from unittest.mock import MagicMock
import numpy as np
from integrations.langchain import SemanticaVectorStore
from semantica.vector_store import VectorStore


class _MockEmbedding:
    """Mock LangChain Embeddings class."""

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class TestSemanticaVectorStore(unittest.TestCase):

    def test_vectorstore_initialisation(self) -> None:
        store = SemanticaVectorStore(backend="inmemory", dimension=3)
        self.assertIsNotNone(store)
        self.assertIsNotNone(store.vector_store)

    def test_custom_embedding(self) -> None:
        emb = _MockEmbedding()
        store = SemanticaVectorStore(backend="inmemory", dimension=3, embedding=emb)
        self.assertEqual(store.vector_store.embed("test"), [0.1, 0.2, 0.3])
        self.assertEqual(store.vector_store.embed_batch(["test"]), [[0.1, 0.2, 0.3]])

    def test_add_and_search(self) -> None:
        emb = _MockEmbedding()
        store = SemanticaVectorStore(backend="inmemory", dimension=3, embedding=emb)

        # Add texts
        ids = store.add_texts(
            texts=["First document content", "Second document content"],
            metadatas=[{"doc_id": 101}, {"doc_id": 102}],
        )
        self.assertEqual(len(ids), 2)

        # Similarity search
        results = store.similarity_search("query text", k=2)
        self.assertEqual(len(results), 2)

        contents = [doc.page_content for doc in results]
        self.assertIn("First document content", contents)
        self.assertIn("Second document content", contents)

        metadatas = [doc.metadata for doc in results]
        self.assertIn(101, [m.get("doc_id") for m in metadatas])
        self.assertIn(102, [m.get("doc_id") for m in metadatas])

    def test_from_texts(self) -> None:
        emb = _MockEmbedding()
        store = SemanticaVectorStore.from_texts(
            texts=["Sample text"],
            embedding=emb,
            backend="inmemory",
            dimension=3,
        )
        self.assertIsNotNone(store)

        results = store.similarity_search_with_score("query", k=1)
        self.assertEqual(len(results), 1)
        doc, score = results[0]
        self.assertEqual(doc.page_content, "Sample text")
        self.assertIsInstance(score, float)


if __name__ == "__main__":
    unittest.main()
