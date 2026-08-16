"""
Deterministic Explorer Rendering E2E Example.

Demonstrates building, serializing, and reloading a deterministic 4-node,
3-edge knowledge graph baseline for visual inspection in Semantica Explorer.

Graph topology:
    Alice (Person)       --WORKS_AT-->    Acme (Organization)
    Bob (Person)         --KNOWS-->       Alice (Person)
    Acme (Organization)  --LOCATED_IN-->  New York (Location)

Usage:
    python examples/explorer_deterministic_rendering_example.py
"""

from __future__ import annotations

import json
from pathlib import Path

from semantica.context.context_graph import ContextGraph
from semantica.explorer.session import GraphSession


def build_deterministic_graph() -> ContextGraph:
    """Build the exact 4-node, 3-edge graph specified in #1037."""
    graph = ContextGraph(advanced_analytics=False)

    # 1. Add exactly 4 nodes
    graph.add_node(
        "alice",
        node_type="Person",
        content="Alice",
        color="#63E6FF",
    )
    graph.add_node(
        "bob",
        node_type="Person",
        content="Bob",
        color="#63E6FF",
    )
    graph.add_node(
        "acme",
        node_type="Organization",
        content="Acme",
        color="#A78BFA",
    )
    graph.add_node(
        "new_york",
        node_type="Location",
        content="New York",
        color="#34D399",
    )

    # 2. Add exactly 3 directed edges
    graph.add_edge("alice", "acme", edge_type="WORKS_AT", weight=1.0)
    graph.add_edge("bob", "alice", edge_type="KNOWS", weight=1.0)
    graph.add_edge("acme", "new_york", edge_type="LOCATED_IN", weight=1.0)

    return graph


def main() -> None:
    print("1. Building deterministic ContextGraph...")
    graph = build_deterministic_graph()
    print(
        f"   ✓ Graph built with {len(graph.nodes)} nodes "
        f"and {len(graph.edges)} edges."
    )

    output_path = Path("explorer_e2e_test_graph.json").resolve()
    print(f"2. Persisting graph to '{output_path.name}'...")
    graph.save_to_file(str(output_path))
    print(f"   ✓ Graph saved to {output_path}")

    # Verify JSON format
    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data.get("nodes", [])) == 4
    assert len(data.get("edges", [])) == 3

    print("3. Verifying reload via GraphSession.from_file()...")
    session = GraphSession.from_file(str(output_path))
    stats = session.get_stats()
    nodes, total_nodes = session.get_nodes()
    edges, total_edges = session.get_edges()

    assert stats["node_count"] == 4
    assert stats["edge_count"] == 3
    assert total_nodes == 4
    assert total_edges == 3

    print(
        f"   ✓ Graph reloaded successfully without mutation "
        f"(nodes: {total_nodes}, edges: {total_edges}).\n"
    )

    print("=" * 70)
    print("Reproduction instructions to view in Semantica Explorer:")
    print("=" * 70)
    print("Option A (Explorer CLI server):")
    print(f"    python -m semantica.explorer --graph {output_path} " f"--port 8000\n")
    print("Option B (Frontend dev server + API backend):")
    print(
        f"    1. Backend:  python -m semantica.explorer --graph {output_path} "
        f"--port 8000 --no-browser"
    )
    print("    2. Frontend: cd explorer && npm run dev")
    print("    3. Open http://localhost:5173 to inspect the graph canvas.")
    print("=" * 70)


if __name__ == "__main__":
    main()
