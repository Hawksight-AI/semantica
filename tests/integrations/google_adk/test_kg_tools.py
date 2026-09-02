import pytest
import sys
import importlib
from unittest.mock import patch

@pytest.fixture(autouse=True)
def require_adk(request):
    """Skip tests if ADK is missing, unless testing missing dependency behavior."""
    if "missing_adk" not in request.node.name:
        pytest.importorskip("google.adk")

from integrations.google_adk.kg_tools import (
    ADK_AVAILABLE,
    extract_entities,
    extract_relations,
    semantica_kg_tools,
)


def test_adk_available():
    assert ADK_AVAILABLE is True


def test_extract_entities_returns_dict():
    result = extract_entities(
        "Google was founded by Larry Page and Sergey Brin."
    )

    assert isinstance(result, dict)
    assert "entities" in result
    assert "count" in result
    assert isinstance(result["entities"], list)


def test_extract_relations_returns_dict():
    result=extract_relations('Alice works at Acme Corp. Bob founded Acme Corp. ')

    assert isinstance(result, dict)
    assert "relations" in result
    assert "count" in result
    assert isinstance(result["relations"], list)
    assert "error" not in result,f"Extraction failed with the error: {result.get('error')}"
    assert result["count"]>0, " We Expected  at least one relation to be extracted"
    assert len(result["relations"]) > 0, "Relation list should not ne empty"


def test_semantica_kg_tools_returns_function_tools():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    tools = semantica_kg_tools(graph)

    assert isinstance(tools, list)
    assert len(tools) == 4

    for tool in tools:
        assert tool is not None


def test_semantica_kg_tools_share_graph():
    from semantica.context import ContextGraph

    graph = ContextGraph()

    tools = semantica_kg_tools(graph)

    assert len(tools) == 4

    # FunctionTool should wrap our closures/functions.
    names = {
        getattr(tool, "name", None)
        for tool in tools
    }

    assert "extract_entities" in names
    assert "extract_relations" in names
    assert "add_to_shared_graph" in names
    assert "query_shared_graph" in names


def test_extract_entities_invalid_input():
    result = extract_entities(None)

    assert isinstance(result, dict)
    assert result["entities"] == []
    assert result["count"] == 0
    assert "error" in result


def test_missing_adk_graceful_failure(monkeypatch):
    import pytest
    import integrations.google_adk.kg_tools as kg_module

    # Safely mock the flag to False just for this test
    monkeypatch.setattr(kg_module, "ADK_AVAILABLE", False)

    assert kg_module.ADK_AVAILABLE is False
    with pytest.raises(ImportError, match="Google ADK is required"):
        kg_module.semantica_kg_tools(None)