from semantica.kg.graph_builder import GraphBuilder
from semantica.kg.graph_validator import GraphValidator


def test_entity_id_aliases_are_validated_across_graph_structure():
    """Entity aliases should work for schema and structural validation."""
    graph = GraphBuilder(
        merge_entities=True,
        entity_resolution_strategy="exact",
        resolve_conflicts=False,
    ).build(
        {
            "entities": [
                {"entity_id": "alice:1", "name": "Alice", "type": "Person"},
                {"entity_id": "alice:2", "name": " Alice ", "type": "Person"},
                {"entity_id": "org:1", "name": "Acme", "type": "Organization"},
            ],
            "relationships": [
                {
                    "source_id": "alice:2",
                    "target_id": "org:1",
                    "type": "WORKS_FOR",
                }
            ],
        }
    )

    result = GraphValidator().validate(graph)

    assert result.is_valid
    assert not any(
        issue.code in {"MISSING_FIELD", "DANGLING_EDGE", "ORPHAN_NODES"}
        for issue in result.issues
    )


def test_entity_id_and_relationship_aliases_validate_without_builder():
    """Validator endpoint fallbacks should be tested without normalization."""
    result = GraphValidator().validate(
        {
            "entities": [
                {"entity_id": "alice:1", "name": "Alice", "type": "Person"},
                {"entity_id": "org:1", "name": "Acme", "type": "Organization"},
            ],
            "relationships": [
                {
                    "source_id": "alice:1",
                    "target_id": "org:1",
                    "type": "WORKS_FOR",
                }
            ],
        }
    )

    assert result.is_valid
    assert not any(
        issue.code in {"MISSING_FIELD", "DANGLING_EDGE", "ORPHAN_NODES"}
        for issue in result.issues
    )


def test_unhashable_entity_id_returns_validation_issue():
    """Invalid unhashable IDs should produce an issue instead of crashing."""
    result = GraphValidator().validate(
        {
            "entities": [
                {"entity_id": ["alice:1"], "name": "Alice", "type": "Person"}
            ],
            "relationships": [],
        }
    )

    assert not result.is_valid
    assert any(issue.code == "INVALID_ID" for issue in result.issues)
