"""
Regression test for the Semantica MCP `query_decisions` category filter bug.

Root cause (fixed): `record_decision` stores `category` as a node *property*
(via `add_node(category=...)`), so `find_nodes(node_type="decision")` surfaces it
under `metadata.category`, NOT as a top-level `category` key. The old
`_tool_query_decisions` filtered on the missing top-level key, so any category
filter returned an empty list. This test exercises the real MCP tool handlers
end-to-end (record -> query) against a fresh in-memory graph.
"""

import sys

import pytest

from semantica import mcp_server
from semantica.context import ContextGraph


@pytest.fixture
def fresh_graph(monkeypatch):
    """Provide a fresh ContextGraph and make `_get_graph()` return it."""
    graph = ContextGraph(advanced_analytics=True)
    monkeypatch.setattr(mcp_server, "_get_graph", lambda: graph)
    return graph


def _record(fresh_graph, category, idx=0):
    return mcp_server._tool_record_decision(
        {
            "category": category,
            "scenario": f"scenario {idx}",
            "reasoning": f"reasoning {idx}",
            "outcome": "approved",
            "confidence": 0.9,
        }
    )


def test_category_filter_matches_stored_decisions(fresh_graph):
    """Acceptance #1: filtered result is a subset of unfiltered."""
    _record(fresh_graph, "technology_selection", idx=1)
    _record(fresh_graph, "technology_selection", idx=2)
    _record(fresh_graph, "risk_assessment", idx=3)

    unfiltered = mcp_server._tool_query_decisions({"limit": 50})["decisions"]
    filtered = mcp_server._tool_query_decisions(
        {"category": "technology_selection", "limit": 50}
    )["decisions"]

    assert len(unfiltered) >= 3
    assert len(filtered) == 2

    # Every filtered decision must actually belong to the category.
    for d in filtered:
        cat = d.get("category") or (d.get("metadata") or {}).get("category")
        assert cat == "technology_selection"

    # Filtered must be a subset of unfiltered (by id).
    unfiltered_ids = {d["id"] for d in unfiltered}
    filtered_ids = {d["id"] for d in filtered}
    assert filtered_ids.issubset(unfiltered_ids)


def test_nonexistent_category_returns_empty(fresh_graph):
    """Acceptance #2: filtering an unknown category returns [] without error."""
    _record(fresh_graph, "technology_selection", idx=1)
    result = mcp_server._tool_query_decisions(
        {"category": "does_not_exist", "limit": 10}
    )
    assert result["decisions"] == []
    assert "error" not in result


def test_record_then_query_roundtrip(fresh_graph):
    """Acceptance #3: record -> query round trip returns the decision."""
    rec = _record(fresh_graph, "technology_selection", idx=7)
    assert "decision_id" in rec

    found = mcp_server._tool_query_decisions(
        {"category": "technology_selection", "limit": 10}
    )["decisions"]
    assert any(d["id"] == rec["decision_id"] for d in found)


if __name__ == "__main__":
    # Allow running directly without pytest (e.g. inside the MCP container).
    sys.exit(pytest.main([__file__, "-v"]))
