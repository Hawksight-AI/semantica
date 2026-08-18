
import pytest
from semantica.kg.graph_builder import GraphBuilder
from semantica.kg.entity_resolver import EntityResolver
from semantica.kg.graph_analyzer import GraphAnalyzer
from semantica.utils.entity_ids import get_entity_id
from semantica.utils.types import Entity

def test_full_entity_pipeline():
    """
    Tests the full pipeline using Entity objects:
    Builder -> Resolver -> Analyzer
    This specifically verifies the fix for 'unhashable type: Entity'
    and the robustness of ID extraction.
    """
    # 1. Create Entity objects
    e1 = Entity(id="ent1", text="Entity 1", type="PERSON")
    e2 = Entity(id="ent2", text="Entity 2", type="ORG")
    e3 = Entity(id="ent3", text="Entity 3", type="LOCATION")

    # 2. Define relationships using Entity objects
    relationships = [
        {"source": e1, "target": e2, "type": "WORKS_AT"},
        {"source": e2, "target": e3, "type": "LOCATED_IN"},
        {"source": e1, "target": e3, "type": "LIVES_IN"}
    ]

    # 3. Build the graph
    builder = GraphBuilder()
    # Provide both entities and relationships
    sources = {
        "entities": [e1, e2, e3],
        "relationships": relationships
    }
    graph_data = builder.build(sources=sources)
    
    # DEBUG: Print graph_data keys and entities count
    print(f"DEBUG: graph_data keys: {list(graph_data.keys())}")
    print(f"DEBUG: Entities count: {len(graph_data.get('entities', []))}")
    print(f"DEBUG: Relationships count: {len(graph_data.get('relationships', []))}")
    if graph_data.get('entities'):
        print(f"DEBUG: First entity: {graph_data['entities'][0]}")

    # Verify graph data contains the entities and normalized relationships
    assert len(graph_data["entities"]) >= 3
    assert len(graph_data["relationships"]) == 3
    
    # 4. Resolve entities
    resolver = EntityResolver()
    resolved_entities = resolver.resolve_entities(graph_data["entities"])
    resolved_graph = {
        "entities": resolved_entities,
        "relationships": graph_data["relationships"]
    }
    
    # 5. Analyze the graph
    # This is where the 'unhashable type: Entity' usually occurred
    analyzer = GraphAnalyzer()
    analysis_results = analyzer.analyze(resolved_graph)
    
    # Verify analysis results
    assert "centrality" in analysis_results
    assert "communities" in analysis_results
    assert "connectivity" in analysis_results
    
    # Verify specific metrics are present
    centrality = analysis_results["centrality"]
    assert "centrality_measures" in centrality
    # It seems by default it might only calculate degree
    assert "degree" in centrality["centrality_measures"]
    
    # Verify connectivity
    connectivity = analysis_results["connectivity"]
    assert "is_connected" in connectivity
    assert connectivity["is_connected"] is True
    assert connectivity["num_components"] == 1
    
    print("Full pipeline test passed successfully!")

def test_direct_entity_objects_in_analyzer():
    """
    Specifically tests the fix for 'unhashable type: Entity' when
    Entity objects are directly passed in the relationships to GraphAnalyzer.
    This simulates the scenario reported by users where the graph 
    contains Entity objects instead of IDs.
    """
    # 1. Create Entity objects
    e1 = Entity(id="ent1", text="Entity 1", type="PERSON")
    e2 = Entity(id="ent2", text="Entity 2", type="ORG")
    
    # 2. Define relationships directly using Entity objects
    # In some scenarios, the user might pass objects instead of strings
    graph = {
        "entities": [e1, e2],
        "relationships": [
            {"source": e1, "target": e2, "type": "CONNECTED_TO"}
        ]
    }
    
    # 3. Analyze the graph
    analyzer = GraphAnalyzer()
    
    # This should not raise TypeError: unhashable type: 'Entity'
    analysis_results = analyzer.analyze(graph)
    
    assert "centrality" in analysis_results
    assert "metrics" in analysis_results
    
    print("Direct Entity objects test passed successfully!")


def test_entity_id_only_merge_remaps_relationship_endpoints():
    """Entity aliases must survive merging and relationship remapping."""
    builder = GraphBuilder(
        merge_entities=True,
        entity_resolution_strategy="exact",
        resolve_conflicts=False,
    )

    graph = builder.build(
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

    merged_alice = next(
        entity for entity in graph["entities"] if entity["name"] == "Alice"
    )
    relationship = graph["relationships"][0]
    entity_ids = {
        entity.get("id") or entity.get("entity_id") for entity in graph["entities"]
    }

    assert merged_alice["id"] == "alice:1"
    assert set(merged_alice["merged_from"]) == {"alice:1", "alice:2"}
    assert {
        item["id"] for item in merged_alice["metadata"]["provenance"]["merged_from"]
    } == {"alice:1", "alice:2"}
    assert relationship["source"] == "alice:1"
    assert relationship["target"] == "org:1"
    assert {relationship["source"], relationship["target"]} <= entity_ids


def test_entity_id_helper_ignores_falsy_identifiers():
    """ID extraction must match the KG pipeline's falsy-ID contract."""
    assert get_entity_id({"id": "", "entity_id": "alias:1"}) == "alias:1"
    assert get_entity_id({"id": 0, "entity_id": "alias:2"}) == "alias:2"
    assert (
        get_entity_id({"id": "primary:1", "entity_id": "alias:3"})
        == "primary:1"
    )
    assert get_entity_id({"id": "", "entity_id": 0}) is None

if __name__ == "__main__":
    test_full_entity_pipeline()
    test_direct_entity_objects_in_analyzer()
