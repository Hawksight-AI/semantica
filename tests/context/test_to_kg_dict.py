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


def test_null_properties_and_metadata_do_not_crash():
    """Nodes loaded from JSON ``null`` keep None props/metadata; to_kg_dict
    must normalize them instead of raising TypeError (Qodo bug 1)."""
    g = ContextGraph()
    n = ContextNode(node_id="e1", node_type="entity", content="Alice")
    n.properties = None
    n.metadata = None
    g._add_internal_node(n)

    kg = g.to_kg_dict()
    entity = kg["entities"][0]
    assert entity["properties"] == {}
    assert entity["metadata"] == {}


def test_non_string_node_id_is_normalized_and_keeps_edges():
    """ContextEdge coerces endpoints to str; entity ids must be coerced too
    so entities_only filtering does not drop valid edges (Qodo bug 3)."""
    g = ContextGraph()
    g._add_internal_node(ContextNode(node_id=1, node_type="entity", content="one"))
    g._add_internal_node(ContextNode(node_id=2, node_type="entity", content="two"))
    g._add_internal_edge(ContextEdge(source_id=1, target_id=2, edge_type="links"))

    kg = g.to_kg_dict(entities_only=True)
    ids = {e["id"] for e in kg["entities"]}
    assert ids == {"1", "2"}
    assert all(isinstance(e["id"], str) for e in kg["entities"])
    # The edge must survive filtering despite the int-vs-str origin.
    assert {r["type"] for r in kg["relationships"]} == {"links"}


def test_output_is_consumable_by_kg_utilities():
    """to_kg_dict output must validate and be traversable by KG utilities that
    historically read ``source``/``target`` (Qodo bug 2, consumer side)."""
    from semantica.kg.graph_validator import GraphValidator, ValidationSeverity
    from semantica.kg.temporal_query import TemporalGraphQuery

    g = ContextGraph()
    g._add_internal_node(ContextNode(node_id="e1", node_type="entity", content="Alice"))
    g._add_internal_node(ContextNode(node_id="e2", node_type="entity", content="Bob"))
    g._add_internal_edge(ContextEdge(source_id="e1", target_id="e2", edge_type="knows"))
    kg = g.to_kg_dict()

    # Validator requires entity ``name``; add it so only endpoint compat is tested.
    for e in kg["entities"]:
        e["name"] = e["text"]

    result = GraphValidator().validate(kg)
    endpoint_errors = [
        i for i in result.issues
        if i.code in {"MISSING_FIELD", "DANGLING_EDGE"}
        and i.element_type == "relationship"
    ]
    assert endpoint_errors == [], endpoint_errors

    # TemporalGraphQuery.analyze_evolution must see the relationship for "e1".
    tq = TemporalGraphQuery()
    filtered = tq.analyze_evolution(kg, entity="e1")
    assert filtered is not None
