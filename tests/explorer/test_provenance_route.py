"""Unit tests for explorer provenance route helpers."""

from types import SimpleNamespace

import pytest

# fastapi ships in the optional `explorer` extra, not in `dev`, so this module
# must skip rather than fail collection when it is absent. The guard has to sit
# above the import below, which pulls fastapi in transitively.
pytest.importorskip("fastapi")

from semantica.explorer.routes.provenance import (  # noqa: E402
    _add_chain_edges,
    _build_provenance,
    _render_markdown,
)


def _make_session_with_chain() -> SimpleNamespace:
    """Build a minimal session-like object for Source -> Intermediate -> node_id."""
    nodes = {
        "Source": SimpleNamespace(node_type="entity", content="Source"),
        "Intermediate": SimpleNamespace(node_type="entity", content="Intermediate"),
        "node_id": SimpleNamespace(node_type="entity", content="Target"),
    }
    edges = [
        SimpleNamespace(source_id="Source", target_id="Intermediate", edge_type="related_to"),
        SimpleNamespace(source_id="Intermediate", target_id="node_id", edge_type="related_to"),
    ]
    graph = SimpleNamespace(nodes=nodes, edges=edges)
    return SimpleNamespace(graph=graph)


def test_build_provenance_direction_classification_chain():
    session = _make_session_with_chain()

    data = _build_provenance(session, "node_id")

    node_ids = {node["id"] for node in data["nodes"]}
    assert "Source" in node_ids
    assert "Intermediate" in node_ids

    edge_by_pair = {(edge["source"], edge["target"]): edge for edge in data["edges"]}

    assert edge_by_pair[("Intermediate", "node_id")]["direction"] == "upstream"
    assert edge_by_pair[("Source", "Intermediate")]["direction"] != "downstream"


def test_render_markdown_groups_edges_by_direction():
    report = {
        "node_id": "node_id",
        "label": "Target",
        "type": "entity",
        "properties": {},
        "lineage": {
            "nodes": [
                {"id": "Source", "prov_type": "Entity", "label": "Source"},
                {"id": "Intermediate", "prov_type": "Entity", "label": "Intermediate"},
                {"id": "node_id", "prov_type": "Entity", "label": "Target"},
            ],
            "edges": [
                {
                    "id": "Intermediate-node_id",
                    "source": "Intermediate",
                    "target": "node_id",
                    "label": "related_to",
                    "direction": "upstream",
                },
                {
                    "id": "Source-Intermediate",
                    "source": "Source",
                    "target": "Intermediate",
                    "label": "related_to",
                    "direction": "lateral",
                },
            ],
        },
    }

    markdown = _render_markdown(report)

    assert "## Upstream" in markdown
    assert "## Lateral" in markdown
    assert "`Intermediate` -[related_to]-> `node_id`" in markdown
    assert "`Source` -[related_to]-> `Intermediate`" in markdown


def test_add_chain_edges_ids_distinguish_direction():
    """Regression test: the same (src, target) pair appearing in both the
    ancestor and descendant chains (e.g. a cycle or overlap between them)
    must not collide on edge id — the id must carry the same uniqueness
    information as the seen_edges dedupe key, which already includes
    direction."""
    same_pair_chain = [
        {"entity_id": "b", "parent_entity_id": "a", "activity_id": "act"},
    ]

    edges: list = []
    seen_edges: set = set()
    _add_chain_edges(same_pair_chain, edges, seen_edges, "upstream")
    _add_chain_edges(same_pair_chain, edges, seen_edges, "downstream")

    assert len(edges) == 2
    ids = {edge["id"] for edge in edges}
    assert len(ids) == 2, f"edge ids collided across directions: {edges}"
    directions = {edge["id"]: edge["direction"] for edge in edges}
    assert directions == {"a-b-upstream": "upstream", "a-b-downstream": "downstream"}
