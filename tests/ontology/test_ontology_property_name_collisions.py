import pytest

from semantica.ontology.class_inferrer import ClassInferrer
from semantica.ontology.property_generator import PropertyGenerator
from semantica.utils.exceptions import ValidationError


def test_same_kind_normalized_object_properties_are_merged():
    entities = [
        {"id": "p1", "type": "Person", "name": "Alice"},
        {"id": "o1", "type": "Organization", "name": "Acme"},
    ]
    classes = ClassInferrer(min_occurrences=1).infer_classes(entities)
    relationships = [
        {
            "source_type": "Person",
            "target_type": "Organization",
            "type": "works_for",
        },
        {
            "source_type": "Person",
            "target_type": "Organization",
            "type": "worksFor",
        },
    ]

    properties = PropertyGenerator().infer_properties(
        entities, relationships, classes, min_occurrences=1
    )

    works_for = [prop for prop in properties if prop["name"] == "worksFor"]
    assert len(works_for) == 1
    assert works_for[0]["domain"] == ["Person"]
    assert works_for[0]["range"] == ["Organization"]


def test_normalized_name_cannot_be_both_object_and_data_property():
    entities = [
        {"id": "p1", "type": "Person", "value": "Alice"},
        {"id": "p2", "type": "Person", "value": "Bob"},
    ]
    classes = ClassInferrer(min_occurrences=1).infer_classes(entities)
    relationships = [
        {"source_type": "Person", "target_type": "Person", "type": "value"},
        {"source_type": "Person", "target_type": "Person", "type": "value"},
    ]

    with pytest.raises(ValidationError, match="object and data"):
        PropertyGenerator().infer_properties(
            entities, relationships, classes, min_occurrences=1
        )
