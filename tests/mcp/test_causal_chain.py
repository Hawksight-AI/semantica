"""
Regression test for the Semantica MCP causal-chain feature.

Background: `get_causal_chain` used to return an empty chain because
`record_decision` never wrote causal edges, and the traversal only followed
knowledge-graph `CAUSED` edges that were never created. This test exercises the
real MCP tool handlers end-to-end (record with causes/caused_by -> query chain)
against a fresh in-memory graph.

Chain layout under test (arrows = "causes"):
    A -> B -> C      (so C was caused_by B, B was caused_by A)
"""

import sys

import pytest

from semantica import mcp_server
from semantica.context import ContextGraph


@pytest.fixture
def fresh_graph(monkeypatch):
    graph = ContextGraph(advanced_analytics=True)
    monkeypatch.setattr(mcp_server, "_get_graph", lambda: graph)
    return graph


def _record(cat, idx, **extra):
    return mcp_server._tool_record_decision(
        {
            "category": cat,
            "scenario": f"scenario {idx}",
            "reasoning": f"reasoning {idx}",
            "outcome": f"outcome_{idx}",
            "confidence": 0.9,
            **extra,
        }
    )


def _chain(decision_id, direction, max_depth=5):
    res = mcp_server._tool_get_causal_chain(
        {"decision_id": decision_id, "direction": direction, "max_depth": max_depth}
    )
    return res["chain"]


def _build_chain(fresh_graph):
    a = _record("cat", 1)["decision_id"]
    b = _record("cat", 2, caused_by=[a])["decision_id"]
    c = _record("cat", 3, caused_by=[b])["decision_id"]
    return a, b, c


def test_one_hop_causal_links(fresh_graph):
    """Acceptance #1: B upstream contains A; A downstream contains B."""
    a, b, _ = _build_chain(fresh_graph)

    upstream_b = _chain(b, "upstream")
    assert any(n["decision_id"] == a for n in upstream_b)

    downstream_a = _chain(a, "downstream")
    assert any(n["decision_id"] == b for n in downstream_a)


def test_two_hop_chain_ordered(fresh_graph):
    """Acceptance #2: get_causal_chain(C, upstream, max_depth=2) -> [B, A]."""
    a, b, c = _build_chain(fresh_graph)

    upstream_c = _chain(c, "upstream", max_depth=2)
    ids = [n["decision_id"] for n in upstream_c]
    assert ids == [b, a], f"expected [B, A] got {ids}"

    # max_depth=1 must stop at the immediate cause only.
    assert [n["decision_id"] for n in _chain(c, "upstream", max_depth=1)] == [b]


def test_chain_node_shape(fresh_graph):
    """Each chain node exposes decision_id, outcome, summary."""
    a, b, _ = _build_chain(fresh_graph)
    upstream_b = _chain(b, "upstream")
    node = next(n for n in upstream_b if n["decision_id"] == a)
    assert set(node.keys()) == {"decision_id", "outcome", "summary"}
    assert node["decision_id"] == a
    assert node["outcome"] == "outcome_1"
    assert node["summary"] == "scenario 1"


def test_unknown_decision_id_returns_empty(fresh_graph):
    """Acceptance #3: unknown id -> empty chain (no exception)."""
    _build_chain(fresh_graph)
    chain = _chain("decision_does_not_exist", "upstream")
    assert chain == []


def test_causes_direction(fresh_graph):
    """`causes=[x]` on y means y -> x: y's downstream has x, x's upstream has y."""
    x = _record("cat", 10)["decision_id"]
    y = _record("cat", 11, causes=[x])["decision_id"]
    assert any(n["decision_id"] == x for n in _chain(y, "downstream"))
    assert any(n["decision_id"] == y for n in _chain(x, "upstream"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
