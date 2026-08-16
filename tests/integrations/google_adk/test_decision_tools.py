import pytest


pytest.importorskip("google.adk")


from integrations.google_adk.decision_tools import (
    ADK_AVAILABLE,
    query_decisions,
    record_decision,
    semantica_decision_tools,
)


def test_adk_available():
    assert ADK_AVAILABLE is True


def test_record_decision_returns_dict():
    result = record_decision(
        category="testing",
        scenario="Google ADK integration test",
        reasoning="Testing decision recording through the ADK adapter.",
        outcome="Integration works",
        confidence=0.9,
        decision_maker="test-agent",
    )

    assert isinstance(result, dict)
    assert "decision_id" in result
    assert result["decision_id"]
    assert result["category"] == "testing"
    assert result["outcome"] == "Integration works"
    assert result["confidence"] == 0.9


def test_record_decision_clamps_confidence():
    result = record_decision(
        category="testing",
        scenario="Confidence test",
        reasoning="Testing confidence normalization.",
        outcome="Done",
        confidence=2.0,
    )

    assert result["confidence"] == 1.0


def test_record_decision_rejects_invalid_input_gracefully():
    result = record_decision(
        category=None,
        scenario="Invalid category test",
        reasoning="Testing error handling.",
        outcome="Done",
    )

    assert isinstance(result, dict)
    assert "decision_id" in result


def test_query_decisions_returns_dict():
    result = query_decisions("testing")

    assert isinstance(result, dict)
    assert "query" in result
    assert "decisions" in result
    assert "count" in result
    assert isinstance(result["decisions"], list)


def test_record_then_query_decision():
    result = record_decision(
        category="adk-integration",
        scenario="Shared graph test",
        reasoning="Verify that decisions can be queried after recording.",
        outcome="Shared graph works",
        confidence=0.95,
        decision_maker="test-agent",
    )

    assert result["decision_id"]

    query_result = query_decisions("Shared graph test")

    assert isinstance(query_result, dict)
    assert query_result["count"] >= 1

    decision_ids = {
        decision["decision_id"]
        for decision in query_result["decisions"]
    }

    assert result["decision_id"] in decision_ids


def test_semantica_decision_tools_returns_function_tools():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    tools = semantica_decision_tools(graph)

    assert isinstance(tools, list)
    assert len(tools) == 2

    for tool in tools:
        assert tool is not None


def test_semantica_decision_tools_names():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    tools = semantica_decision_tools(graph)

    names = {
        getattr(tool, "name", None)
        for tool in tools
    }

    assert "record_shared_decision" in names
    assert "query_shared_decisions" in names