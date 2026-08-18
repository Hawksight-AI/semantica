"""Tests for ContextGraph.to_kg_dict() — the official KG-shape adapter.

These tests lock in the contract that to_kg_dict() emits the
``{"entities", "relationships"}`` / ``source_id`` shape expected by
downstream consumers (RDFExporter, TemporalGraphQuery.query_time_range),
so users never need to hand-map field names.
"""

from semantica.context.context_graph import ContextEdge, ContextGraph, ContextNode


def _build_graph():
    g = ContextGraph()
    g._add_internal_node(ContextNode(node_id="e1", node_type="entity", content="Alice"))
    g._add_internal_node(ContextNode(node_id="e2", node_type="entity", content="Bob"))
    g._add_internal_node(
        ContextNode(node_id="c1", node_type="conversation", content="chat log")
    )
    g._add_internal_edge(
        ContextEdge(
            source_id="e1",
            target_id="e2",
            edge_type="knows",
            valid_from="2024-01-01",
            valid_until="2024-12-31",
        )
    )
    # Edge touching a non-entity node — used to test entities_only filtering.
    g._add_internal_edge(
        ContextEdge(source_id="c1", target_id="e1", edge_type="mentions")
    )
    return g


def test_basic_shape():
    kg = _build_graph().to_kg_dict()
    assert set(kg.keys()) == {"entities", "relationships", "statistics"}
    # Entity shape uses id/text/type (not id/content).
    entity = next(e for e in kg["entities"] if e["id"] == "e1")
    assert entity["text"] == "Alice"
    assert entity["type"] == "entity"


def test_relationship_uses_source_id_target_id():
    kg = _build_graph().to_kg_dict()
    rel = next(r for r in kg["relationships"] if r["type"] == "knows")
    assert rel["source_id"] == "e1"
    assert rel["target_id"] == "e2"
    # "source"/"target" (the internal names) must NOT leak through.
    assert "source" not in rel
    assert "target" not in rel


def test_temporal_fields_passthrough():
    kg = _build_graph().to_kg_dict()
    rel = next(r for r in kg["relationships"] if r["type"] == "knows")
    assert rel["valid_from"] == "2024-01-01"
    assert rel["valid_until"] == "2024-12-31"


def test_statistics_counts():
    kg = _build_graph().to_kg_dict()
    assert kg["statistics"]["entity_count"] == len(kg["entities"])
    assert kg["statistics"]["relationship_count"] == len(kg["relationships"])


def test_entities_only_filters_nodes():
    kg = _build_graph().to_kg_dict(entities_only=True)
    types = {e["type"] for e in kg["entities"]}
    assert types == {"entity"}
    assert len(kg["entities"]) == 2


def test_entities_only_drops_dangling_relationships():
    # The "mentions" edge points from a conversation node (filtered out under
    # entities_only) and must not appear as a dangling relationship.
    kg = _build_graph().to_kg_dict(entities_only=True)
    rel_types = {r["type"] for r in kg["relationships"]}
    assert "mentions" not in rel_types
    assert rel_types == {"knows"}


def test_returned_dicts_are_isolated_from_internal_state():
    g = _build_graph()
    kg = g.to_kg_dict()
    entity = next(e for e in kg["entities"] if e["id"] == "e1")
    # Mutating the returned dict must not corrupt internal node properties.
    entity["properties"]["injected"] = True
    assert "injected" not in g.nodes["e1"].properties
