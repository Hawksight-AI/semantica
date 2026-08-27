from semantica.ontology.class_inferrer import ClassInferrer
from semantica.ontology.ontology_generator import OntologyGenerator
from semantica.ontology.property_generator import PropertyGenerator


def _entities():
    return [
        {
            "id": "e1",
            "type": "software engineer",
            "name": "Alice",
            "email": "alice@example.org",
        },
        {
            "id": "e2",
            "type": "software engineer",
            "name": "Bob",
            "email": "bob@example.org",
        },
    ]


def test_property_generator_matches_normalized_class_names():
    entities = _entities()
    classes = ClassInferrer().infer_classes(entities)

    properties = PropertyGenerator().infer_properties(entities, [], classes)

    email = next(prop for prop in properties if prop["name"] == "email")
    assert email["domain"] == ["SoftwareEngineer"]
    assert email["range"] == "xsd:string"


def test_ontology_pipeline_emits_data_properties_for_normalized_types():
    ontology = OntologyGenerator().generate_ontology(
        {"entities": _entities(), "relationships": []}
    )

    email = next(prop for prop in ontology["properties"] if prop["name"] == "email")
    assert email["domain"] == ["SoftwareEngineer"]
    assert email["range"] == "xsd:string"
