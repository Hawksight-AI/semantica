"""
Deterministic Explorer Rendering E2E Example.

Demonstrates building, serializing, and reloading a deterministic 4-node,
3-edge knowledge graph baseline for visual inspection in Semantica Explorer (#1037).

Graph topology:
    Alice (Person, #63E6FF)       --WORKS_AT-->    Acme (Organization, #A78BFA)
    Bob (Person, #63E6FF)         --KNOWS-->       Alice (Person, #63E6FF)
    Acme (Organization, #A78BFA)  --LOCATED_IN-->  New York (Location, #34D399)

Clean Checkout Prerequisites:
    1. Python backend dependencies:
       pip install -e ".[explorer]"
    2. Frontend workspace dependencies:
       cd explorer && npm install && cd ..

Usage:
    # 1. Generate the deterministic graph baseline:
    python examples/explorer_deterministic_rendering_example.py

    # 2. Launch Explorer with local dev authentication (Option A - Dev mode):
    # Terminal 1 (Backend API):
    SEMANTICA_ALLOW_ANONYMOUS=true python -m semantica.explorer --graph explorer_e2e_test_graph.json --port 8000 --no-browser
    # Terminal 2 (Frontend UI):
    cd explorer && npm run dev
    # Open http://localhost:5173

    # 2. Launch Explorer (Option B - Standalone CLI server):
    SEMANTICA_ALLOW_ANONYMOUS=true python -m semantica.explorer --graph explorer_e2e_test_graph.json --port 8000
    # Open http://localhost:8000

    # Secure authentication alternative:
    export SEMANTICA_API_KEY="your-secret-api-key"
    python -m semantica.explorer --graph explorer_e2e_test_graph.json --port 8000
    # Send HTTP header: X-API-Key: your-secret-api-key

Verification Checklist:
    - Exactly 4 nodes visible on canvas:
        * Alice (Person, #63E6FF)
        * Bob (Person, #63E6FF)
        * Acme (Organization, #A78BFA)
        * New York (Location, #34D399)
    - Exactly 3 directed edges with canonical relationship labels:
        * Alice -> Acme  (WORKS_AT)
        * Bob -> Alice   (KNOWS)
        * Acme -> New York (LOCATED_IN)
    - Zoom behavior:
        * Zoom in to Inspection tier (ratio <= 0.5): directional arrows and node labels scale clearly.
        * Zoom out to Overview tier (ratio > 1.2): layout remains stable and non-colliding.
    - Hover & Selection interactions:
        * Hover over 'Alice': node halo triggers; incident edges (WORKS_AT, KNOWS) highlight in local context.
        * Click an edge: Inspector panel confirms edgeType ('WORKS_AT', 'KNOWS', or 'LOCATED_IN').
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
    print("=" * 75)
    print("Semantica Explorer Deterministic Graph Generator (#1037)")
    print("=" * 75)

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

    print("=" * 75)
    print("Clean Checkout Prerequisites:")
    print("=" * 75)
    print("    pip install -e '.[explorer]'")
    print("    cd explorer && npm install && cd ..\n")

    print("=" * 75)
    print("Reproduction instructions to view in Semantica Explorer:")
    print("=" * 75)
    print("Option A (Frontend dev server + API backend — recommended for development):")
    print(
        f"    1. Backend:  SEMANTICA_ALLOW_ANONYMOUS=true python -m semantica.explorer "
        f"--graph {output_path} --port 8000 --no-browser"
    )
    print("    2. Frontend: cd explorer && npm run dev")
    print("    3. Open http://localhost:5173 to inspect the graph canvas.\n")

    print("Option B (Standalone Explorer CLI server):")
    print(
        f"    SEMANTICA_ALLOW_ANONYMOUS=true python -m semantica.explorer "
        f"--graph {output_path} --port 8000"
    )
    print("    Open http://localhost:8000\n")

    print("Secure Authentication Alternative:")
    print("    export SEMANTICA_API_KEY='your-secret-api-key'")
    print(
        f"    python -m semantica.explorer --graph {output_path} --port 8000"
    )
    print("    Send header: 'X-API-Key: your-secret-api-key'\n")

    print("=" * 75)
    print("Verification Checklist:")
    print("=" * 75)
    print("    1. Nodes (4 total):")
    print("       - Alice (Person, #63E6FF)")
    print("       - Bob (Person, #63E6FF)")
    print("       - Acme (Organization, #A78BFA)")
    print("       - New York (Location, #34D399)")
    print("    2. Directed Edges & Canonical Labels (3 total):")
    print("       - Alice -> Acme     [WORKS_AT]")
    print("       - Bob   -> Alice    [KNOWS]")
    print("       - Acme  -> New York [LOCATED_IN]")
    print("    3. Zoom Interactions:")
    print("       - Inspection tier (zoom in): directional arrows & labels remain legible.")
    print("       - Overview tier (zoom out): nodes and edges maintain layout integrity.")
    print("    4. Hover & Selection Interactions:")
    print("       - Hover Alice: node halo triggers and incident edges (WORKS_AT, KNOWS) highlight.")
    print("       - Click edge: Inspector panel displays edgeType label ('WORKS_AT', 'KNOWS', 'LOCATED_IN').")
    print("=" * 75)


if __name__ == "__main__":
    main()
