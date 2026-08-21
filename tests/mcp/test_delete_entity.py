"""
Regression test for the Semantica MCP `delete_entity` tool and the underlying
`ContextGraph.delete_node` method.

Background: the user reported that the MCP surface had no way to remove a node.
`ContextGraph.delete_node` (cascade / non-cascade) and the MCP tool
`_tool_delete_entity` were added. These tests exercise both layers end-to-end
against a fresh in-memory graph:

  * delete_node removes the node and (by default) its incident edges;
  * non-cascade delete keeps the edge collection untouched (edges_removed == 0);
  * deleting a missing / empty-id node is a safe no-op (node_found is False);
  * the MCP handler returns a clear error for a missing node and for an empty id.
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


# ── ContextGraph.delete_node (core layer) ────────────────────────────────────

def test_delete_node_removes_node_and_cascades_edges(fresh_graph):
    fresh_graph.add_node(node_id="A", node_type="Entity")
    fresh_graph.add_node(node_id="B", node_type="Entity")
    fresh_graph.add_edge(source_id="A", target_id="B", edge_type="RELATED_TO")

    result = fresh_graph.delete_node(node_id="A", cascade_edges=True)
    assert result["deleted"] is True
    assert result["node_found"] is True
    assert result["edges_removed"] == 1

    # Node A is gone; node B remains.
    assert "A" not in fresh_graph.nodes
    assert "B" in fresh_graph.nodes
    # The only edge (A->B) was cascaded away.
    remaining = [e for e in fresh_graph.edges if e.source_id == "A" or e.target_id == "A"]
    assert remaining == []


def test_delete_node_non_cascade_keeps_edges(fresh_graph):
    fresh_graph.add_node(node_id="A", node_type="Entity")
    fresh_graph.add_node(node_id="B", node_type="Entity")
    fresh_graph.add_edge(source_id="A", target_id="B", edge_type="RELATED_TO")

    result = fresh_graph.delete_node(node_id="A", cascade_edges=False)
    assert result["deleted"] is True
    assert result["node_found"] is True
    assert result["edges_removed"] == 0  # edges intentionally untouched

    assert "A" not in fresh_graph.nodes


def test_delete_node_missing_is_safe_noop(fresh_graph):
    result = fresh_graph.delete_node(node_id="ghost")
    assert result["deleted"] is False
    assert result["node_found"] is False
    assert result["edges_removed"] == 0


def test_delete_node_empty_id_is_safe(fresh_graph):
    result = fresh_graph.delete_node(node_id="")
    assert result["deleted"] is False
    assert result["node_found"] is False


# ── MCP layer: _tool_delete_entity ───────────────────────────────────────────

def test_mcp_delete_entity_roundtrip(fresh_graph):
    add = mcp_server._tool_add_entity({"id": "X", "type": "Person", "label": "X"})
    assert add.get("status") == "added"

    res = mcp_server._tool_delete_entity({"id": "X"})
    assert res.get("deleted") is True
    assert res.get("node_found") is True
    assert "X" not in fresh_graph.nodes


def test_mcp_delete_entity_cascades_edge(fresh_graph):
    mcp_server._tool_add_entity({"id": "P", "type": "Person"})
    mcp_server._tool_add_entity({"id": "Q", "type": "Person"})
    mcp_server._tool_add_relationship({"source": "P", "target": "Q", "type": "KNOWS"})

    res = mcp_server._tool_delete_entity({"id": "P"})  # cascade default True
    assert res.get("deleted") is True
    assert res.get("edges_removed") == 1
    remaining = [e for e in fresh_graph.edges if e.source_id == "P" or e.target_id == "P"]
    assert remaining == []


def test_mcp_delete_entity_not_found(fresh_graph):
    res = mcp_server._tool_delete_entity({"id": "nope"})
    assert res.get("deleted") is False
    assert "error" in res
    assert "node not found" in res["error"].lower()


def test_mcp_delete_entity_empty_id(fresh_graph):
    res = mcp_server._tool_delete_entity({"id": ""})
    assert "error" in res
    assert res["error"] == "id is required"


if __name__ == "__main__":
    # Allow running directly without pytest (e.g. inside the MCP container).
    sys.exit(pytest.main([__file__, "-v"]))
