"""
Regression tests for MCP/Explorer shared JSON persistence.

Covers the ContextGraph persistence extension that makes MCP writes durable:
- save_to_file round-trips the decision library (decisions + causal index),
  which previously was only held in memory and lost on restart.
- Decision records are materialized as graph nodes/edges and survive a
  save -> load cycle.
- Save is atomic (a valid JSON file always exists afterwards).
"""

import json
import sys

import pytest

from semantica.context import ContextGraph


@pytest.fixture
def fresh_graph():
    return ContextGraph(advanced_analytics=False)


def _save(g, path):
    g.save_to_file(str(path))


def _load(path):
    g = ContextGraph(advanced_analytics=False)
    g.load_from_file(str(path))
    return g


def test_decision_library_roundtrip(fresh_graph, tmp_path):
    """Decisions + causal index survive a save -> load cycle."""
    a = fresh_graph.record_decision(
        category="cat_a",
        scenario="Scenario A",
        reasoning="reasoning a",
        outcome="outcome_a",
        confidence=0.9,
        entities=["e1"],
        decision_maker="mcp_test",
    )
    b = fresh_graph.record_decision(
        category="cat_b",
        scenario="Scenario B",
        reasoning="reasoning b",
        outcome="outcome_b",
        confidence=0.8,
        entities=["e2"],
        causes=[a],
    )

    path = tmp_path / "kg.json"
    _save(fresh_graph, path)
    restored = _load(path)

    assert set(restored._decisions.keys()) == {a, b}
    # Causal index restored: b causes a -> a's upstream contains b.
    upstream = restored.get_causal_chain(a, direction="upstream", max_depth=5)
    assert any(n["decision_id"] == b for n in upstream)
    downstream = restored.get_causal_chain(b, direction="downstream", max_depth=5)
    assert any(n["decision_id"] == a for n in downstream)


def test_decision_nodes_materialized(fresh_graph, tmp_path):
    """Decision nodes/edges are persisted as ordinary graph elements."""
    decision_id = fresh_graph.record_decision(
        category="cat_x",
        scenario="Scenario X",
        reasoning="reasoning x",
        outcome="outcome_x",
        confidence=0.7,
        entities=["alice"],
    )
    path = tmp_path / "kg.json"
    _save(fresh_graph, path)
    restored = _load(path)

    node = restored.find_node(decision_id)
    assert node is not None
    assert node.get("type") == "decision"
    # Entity node + category node materialized too.
    assert restored.find_node("alice") is not None
    assert restored.find_node("category_cat_x") is not None


def test_save_is_atomic_and_parseable(fresh_graph, tmp_path):
    """The shared JSON file is always a valid, complete document."""
    fresh_graph.add_node("n1", "entity", content="node one")
    fresh_graph.add_edge("n1", "n1", edge_type="self_loop")
    fresh_graph.record_decision(
        category="cat", scenario="S", reasoning="R", outcome="O", confidence=1.0
    )
    path = tmp_path / "kg.json"
    _save(fresh_graph, path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["graph_id"] == fresh_graph.graph_id
    assert any(n["id"] == "n1" for n in data["nodes"])
    assert "decisions" in data
    # No stray temp files left behind.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "kg.json"]
    assert leftovers == []


def test_load_legacy_file_without_decisions(fresh_graph, tmp_path):
    """Files saved by older versions (no decisions key) still load fine."""
    fresh_graph.add_node("old", "entity", content="legacy node")
    path = tmp_path / "kg.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"graph_id": fresh_graph.graph_id, "nodes": fresh_graph.nodes["old"].to_dict(), "edges": []},
            f,
        )
    restored = _load(path)
    assert restored.find_node("old") is not None
    assert not getattr(restored, "_decisions", {})
    assert restored.get_causal_chain("whatever", direction="upstream") == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
