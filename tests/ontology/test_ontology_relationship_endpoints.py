from semantica.ontology.ontology_generator import OntologyGenerator


def _object_property(ontology, name):
    return next(prop for prop in ontology["properties"] if prop["name"] == name)


def test_id_based_relationship_endpoints_infer_domain_and_range():
    entities = [
        {"id": "p1", "type": "Person", "name": "Alice"},
        {"id": "p2", "type": "Person", "name": "Bob"},
        {"id": "o1", "type": "Organization", "name": "Acme"},
        {"id": "o2", "type": "Organization", "name": "Beta"},
    ]
    relationships = [
        {"source_id": "p1", "target_id": "o1", "type": "works_for"},
        {"source_id": "p2", "target_id": "o2", "type": "works_for"},
    ]

    ontology = OntologyGenerator().generate_ontology(
        {"entities": entities, "relationships": relationships}
    )

    works_for = _object_property(ontology, "worksFor")
    assert works_for["domain"] == ["Person"]
    assert works_for["range"] == ["Organization"]


def test_source_and_target_aliases_resolve_without_matching_missing_fields():
    entities = [
        {"id": "p1", "type": "Person", "name": "Alice"},
        {"id": "p2", "type": "Person", "name": "Bob"},
        {"id": "o1", "type": "Organization", "name": "Acme"},
        {"id": "o2", "type": "Organization", "name": "Beta"},
    ]
    relationships = [
        {"source": "p1", "target": "o1", "type": "works_for"},
        {"source": "p2", "target": "o2", "type": "works_for"},
    ]

    ontology = OntologyGenerator().generate_ontology(
        {"entities": entities, "relationships": relationships}
    )

    works_for = _object_property(ontology, "worksFor")
    assert works_for["domain"] == ["Person"]
    assert works_for["range"] == ["Organization"]


def test_explicit_relationship_endpoint_types_are_preserved():
    entities = [
        {"id": "p1", "type": "Person", "name": "Alice"},
        {"id": "o1", "type": "Organization", "name": "Acme"},
    ]
    relationships = [
        {
            "source_id": "p1",
            "target_id": "o1",
            "type": "works_for",
            "source_type": "Employee",
            "target_type": "Company",
        }
    ]

    ontology = OntologyGenerator(min_occurrences=1).generate_ontology(
        {"entities": entities, "relationships": relationships}
    )

    works_for = _object_property(ontology, "worksFor")
    assert works_for["domain"] == ["Employee"]
    assert works_for["range"] == ["Company"]


def test_nested_endpoint_alias_skips_empty_id_and_uses_name():
    entities = [
        {"id": "p1", "type": "Person", "name": "Alice"},
        {"id": "o1", "type": "Organization", "name": "Acme"},
    ]
    relationships = [
        {
            "source": {"id": "", "name": "Alice"},
            "target": {"id": "", "name": "Acme"},
            "type": "works_for",
        },
        {
            "source": {"id": "", "name": "Alice"},
            "target": {"id": "", "name": "Acme"},
            "type": "works_for",
        },
    ]

    ontology = OntologyGenerator().generate_ontology(
        {"entities": entities, "relationships": relationships}
    )

    works_for = _object_property(ontology, "worksFor")
    assert works_for["domain"] == ["Person"]
    assert works_for["range"] == ["Organization"]
