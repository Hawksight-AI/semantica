"""
Tests for integrations/langchain.

Adapter behavior is always exercised (hit parsing, seed/fallback, tool JSON).
LangChain-present paths use pytest.importorskip; degradation without
langchain-core is covered in test_degradation.py via a subprocess so it still
runs when langchain-core is installed in this env.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from integrations.langchain import (
    LANGCHAIN_AVAILABLE,
    SemanticaDecisionTool,
    SemanticaKGTool,
    SemanticaRetriever,
    SemanticaVectorStore,
)
from integrations.langchain.retriever import _hit_content, _hit_id, _hit_type
from integrations.langchain.tools import QueryDecisionsInput, QueryGraphInput

# HybridSearch.search() returns {id, score, distance, metadata} — content lives
# inside metadata, and id is a vector id, not a graph node id.
_HYBRID_HIT = {
    "id": "vec_0",
    "score": 0.91,
    "distance": 0.09,
    "metadata": {
        "node_id": "alice",
        "content": "Alice is a developer",
        "node_type": "person",
        "source": "graph",
    },
}


def test_exports_exist():
    assert callable(SemanticaRetriever)
    assert callable(SemanticaVectorStore)
    assert callable(SemanticaKGTool)
    assert callable(SemanticaDecisionTool)


def test_version():
    from integrations.langchain import __version__

    assert __version__ == "0.1.0"


# ---------------------------------------------------------------------------
# Hit parsing (the Qodo high-severity finding)
# ---------------------------------------------------------------------------
def test_hit_id_prefers_metadata_node_id_over_vector_id():
    assert _hit_id(_HYBRID_HIT) == "alice"
    assert _hit_id({"node_id": "n1"}) == "n1"
    assert _hit_id({"id": "n2"}) == "n2"


def test_hit_id_unwraps_context_graph_query_shape():
    hit = {
        "node": {
            "id": "alice",
            "type": "person",
            "properties": {"content": "Alice"},
        },
        "score": 1.0,
        "content": "Alice is a developer",
    }
    assert _hit_id(hit) == "alice"
    assert _hit_content(hit) == "Alice is a developer"
    assert _hit_type(hit) == "person"


def test_hit_content_and_type_read_nested_metadata():
    assert _hit_content(_HYBRID_HIT) == "Alice is a developer"
    assert _hit_type(_HYBRID_HIT) == "person"
    assert _hit_content({"id": "x"}) == ""


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------
def test_empty_seed_returns_empty():
    graph = MagicMock()
    graph.query.return_value = []
    retriever = SemanticaRetriever(graph=graph, top_k=5)
    assert retriever._seed_results("query") == []
    assert retriever.hops == 2


def test_seed_uses_hybrid_when_provided():
    graph = MagicMock()
    hybrid = MagicMock()
    hybrid.search.return_value = [_HYBRID_HIT]
    retriever = SemanticaRetriever(graph=graph, hybrid=hybrid)
    results = retriever._seed_results("query")
    assert len(results) == 1
    hybrid.search.assert_called_once_with("query", k=10)


def test_graph_fallback_when_hybrid_fails():
    graph = MagicMock()
    graph.query.return_value = [{"node_id": "n1", "content": "c1"}]
    hybrid = MagicMock()
    hybrid.search.side_effect = RuntimeError("down")
    retriever = SemanticaRetriever(graph=graph, hybrid=hybrid)
    results = retriever._seed_results("query")
    assert len(results) == 1
    graph.query.assert_called_once()


def test_retriever_reads_hybrid_metadata_and_expands_by_node_id():
    pytest.importorskip("langchain_core")
    graph = MagicMock()
    graph.get_neighbors.return_value = [
        {
            "id": "bob",
            "type": "person",
            "content": "Bob reports to Alice",
            "weight": 0.8,
        }
    ]
    hybrid = MagicMock()
    hybrid.search.return_value = [_HYBRID_HIT]
    retriever = SemanticaRetriever(graph=graph, hybrid=hybrid)
    docs = retriever._get_relevant_documents("Alice")
    assert docs[0].page_content == "Alice is a developer"
    assert docs[0].metadata["node_id"] == "alice"
    assert docs[0].metadata["source"] == "graph"
    graph.get_neighbors.assert_called_once_with("alice", hops=2)
    assert [d.metadata["node_id"] for d in docs] == ["alice", "bob"]


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------
def test_add_texts_delegates_to_vector_store():
    vs = MagicMock()
    vs.add_documents.return_value = ["id1"]
    store = SemanticaVectorStore(hybrid=MagicMock(), vector_store=vs)
    assert store.add_texts(["hello"]) == ["id1"]
    vs.add_documents.assert_called_once()


def test_add_texts_raises_without_vector_store():
    store = SemanticaVectorStore(hybrid=SimpleNamespace(vector_store=None))
    with pytest.raises(ValueError):
        store.add_texts(["hello"])


def test_from_texts_requires_hybrid_kwarg():
    with pytest.raises(ValueError):
        SemanticaVectorStore.from_texts(["hello"], embedding=None)


def test_vectorstore_reads_hybrid_metadata():
    pytest.importorskip("langchain_core")
    hybrid = MagicMock()
    hybrid.search.return_value = [_HYBRID_HIT]
    store = SemanticaVectorStore(hybrid=hybrid)
    docs = store.similarity_search("Alice", k=1)
    assert docs[0].page_content == "Alice is a developer"
    assert docs[0].metadata["node_id"] == "alice"
    assert docs[0].metadata["source"] == "graph"
    pairs = store.similarity_search_with_score("Alice", k=1)
    assert pairs[0][0].page_content == "Alice is a developer"
    assert pairs[0][1] == pytest.approx(0.91)


# ---------------------------------------------------------------------------
# Tools — JSON payload + BaseTool contract
# ---------------------------------------------------------------------------
def test_kg_tool_returns_full_valid_json():
    graph = MagicMock()
    graph.query.return_value = [{"content": "x" * 5000, "id": i} for i in range(3)]
    raw = SemanticaKGTool(graph)._run("q", limit=3)
    parsed = json.loads(raw)
    assert len(parsed) == 3
    assert len(parsed[0]["content"]) == 5000
    graph.query.assert_called_once_with("q", limit=3)


def test_tool_errors_are_json():
    graph = MagicMock()
    graph.query.side_effect = RuntimeError("boom")
    assert json.loads(SemanticaKGTool(graph)._run("q")) == {"error": "boom"}
    assert json.loads(SemanticaDecisionTool(graph)._run("q")) == {"error": "boom"}


def test_decision_tool_empty_category_uses_insights():
    graph = MagicMock()
    graph.get_decision_insights.return_value = {"n": 0}
    assert json.loads(SemanticaDecisionTool(graph)._run("")) == {"n": 0}


def test_tools_are_base_tools_with_args_schema():
    pytest.importorskip("langchain_core")
    from langchain_core.tools import BaseTool

    graph = MagicMock()
    graph.query.return_value = [{"hit": True}]
    kg = SemanticaKGTool(graph)
    dec = SemanticaDecisionTool(graph)
    assert isinstance(kg, BaseTool)
    assert isinstance(dec, BaseTool)
    assert kg.args_schema is QueryGraphInput
    assert dec.args_schema is QueryDecisionsInput
    assert kg.build() is kg
    parsed = json.loads(kg.invoke({"query": "Alice", "limit": 5}))
    assert parsed == [{"hit": True}]


@pytest.mark.skipif(not LANGCHAIN_AVAILABLE, reason="langchain-core not installed")
def test_kg_tool_invoke_with_context_graph():
    pytest.importorskip("langchain_core")
    try:
        from semantica.context import ContextGraph
    except ImportError:
        pytest.skip("ContextGraph import requires optional core deps")

    graph = ContextGraph()
    graph.add_node(node_id="alice", node_type="person", content="Alice is a developer")
    result = SemanticaKGTool(graph).invoke({"query": "Alice", "limit": 5})
    assert "Alice" in result
    json.loads(result)
