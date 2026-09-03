"""Framework/control entity keys must not be inferred as datatype properties.

The _CONTROL_FIELDS skip set mirrors exactly what the framework writes to a
merged entity's top level (see MergeStrategyManager._merge_entities): no extra
guesses, so business attributes that merely share a common name (e.g. source)
keep getting inferred.
"""

from semantica.deduplication.merge_strategy import MergeStrategyManager
from semantica.ontology.property_generator import PropertyGenerator


def _merged_entity():
    """Run a real merge so the entity carries the framework's actual top-level keys."""
    manager = MergeStrategyManager(default_strategy="keep_most_complete")
    result = manager.merge_entities(
        [
            {"id": "b1", "name": "Hangzhou Branch", "type": "ORG", "employee_count": 120},
            {"id": "b2", "name": "Hangzhou Branch", "type": "ORG"},
        ]
    )
    return result.merged_entity


def test_framework_fields_not_inferred_as_data_properties():
    entity = _merged_entity()
    classes = [{"name": "Organization", "metadata": {"inferred_from": "ORG"}}]

    properties = PropertyGenerator().infer_properties([entity], [], classes)

    names = {p["name"] for p in properties}
    for framed in (
        "properties",
        "relationships",
        "metadata",
        "merged_from",
        "merge_strategy",
    ):
        assert framed not in names, f"framework field {framed} leaked as a property"


def test_business_attributes_still_inferred():
    entity = _merged_entity()
    classes = [{"name": "Organization", "metadata": {"inferred_from": "ORG"}}]

    properties = PropertyGenerator().infer_properties([entity], [], classes)

    names = {p["name"] for p in properties}
    assert "name" in names
    assert "metadata" not in names


def test_source_field_still_inferred_as_business_attribute():
    """A top-level 'source' is a business attribute, not a framework field."""
    entity = {
        "id": "b1",
        "name": "Hangzhou Branch",
        "type": "ORG",
        "source": "doc-42",
    }
    classes = [{"name": "Organization", "metadata": {"inferred_from": "ORG"}}]

    properties = PropertyGenerator().infer_properties([entity], [], classes)

    names = {p["name"] for p in properties}
    assert "source" in names
