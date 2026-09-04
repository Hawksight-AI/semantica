"""Tests for reconciling synthetic relation endpoints into the graph.

Relation extraction synthesizes ``UNKNOWN`` entities for endpoints that are
absent from the NER entity list, but ``GraphBuilder._process_item`` kept only
the endpoint string. The resulting graph then failed ``GraphValidator`` with
``DANGLING_EDGE``. See issue #1463.
"""

from semantica.kg import GraphBuilder, GraphValidator
from semantica.semantic_extract import Entity, Relation


def _known(text="Known Entity", label="CONCEPT"):
    return Entity(text=text, label=label, start_char=0, end_char=len(text))


def _synthetic(text):
    return Entity(
        text=text,
        label="UNKNOWN",
        start_char=0,
        end_char=len(text),
        confidence=0.8,
        metadata={"synthetic": True},
    )


def _rel(subject, predicate, object_):
    return Relation(subject=subject, predicate=predicate, object=object_)


def _issues(graph):
    return GraphValidator().validate(graph).to_dict()["issues"]


def test_single_missing_endpoint_promoted():
    graph = GraphBuilder(resolve_conflicts=False).build(
        [_known(), _rel(_known(), "related_to", _synthetic("Synthetic Entity"))],
        extract=False,
    )

    entity_ids = {e["id"] for e in graph["entities"]}
    assert "Synthetic Entity" in entity_ids
    assert not [i for i in _issues(graph) if i.get("code") == "DANGLING_EDGE"]


def test_two_missing_endpoints_promoted():
    graph = GraphBuilder(resolve_conflicts=False).build(
        [_rel(_synthetic("Org A"), "related_to", _synthetic("Org B"))],
        extract=False,
    )

    entity_ids = {e["id"] for e in graph["entities"]}
    assert {"Org A", "Org B"} <= entity_ids


def test_promoted_default_confidence_is_0_8():
    graph = GraphBuilder(resolve_conflicts=False).build(
        [_rel(_known(), "related_to", _synthetic("Synthetic Entity"))],
        extract=False,
    )

    synthetic = next(e for e in graph["entities"] if e["id"] == "Synthetic Entity")
    assert synthetic["confidence"] == 0.8
    assert synthetic["metadata"].get("synthetic") is True
    assert synthetic["type"] == "UNKNOWN"
    assert synthetic["name"] == "Synthetic Entity"


def test_no_duplicate_when_endpoint_already_present():
    # A synthetic endpoint sharing an id with an existing entity must not
    # create a duplicate node.
    known = _known("Shared", label="CONCEPT")
    graph = GraphBuilder(resolve_conflicts=False).build(
        [known, _rel(known, "related_to", _synthetic("Shared"))],
        extract=False,
    )

    ids = [e["id"] for e in graph["entities"] if e["id"] == "Shared"]
    assert len(ids) == 1


def test_default_settings_no_dangling_edge():
    # merge_entities=True, conflict resolution enabled (the default).
    graph = GraphBuilder().build(
        [_known(), _rel(_known(), "related_to", _synthetic("Synthetic Entity"))],
        extract=False,
    )

    assert not [i for i in _issues(graph) if i.get("code") == "DANGLING_EDGE"]


def test_reject_policy_drops_dangling_relationship():
    builder = GraphBuilder(
        resolve_conflicts=False,
        unknown_relation_endpoint="reject",
    )
    graph = builder.build(
        [_rel(_known(), "related_to", _synthetic("Synthetic Entity"))],
        extract=False,
    )

    assert graph["relationships"] == []
    assert "Synthetic Entity" not in {e["id"] for e in graph["entities"]}


def test_reject_policy_requires_config_to_promote():
    # Same input as test_reject_policy but policies must be explicit; only
    # "reject" disables promotion, the default remains permissive.
    default_builder = GraphBuilder(resolve_conflicts=False)
    graph = default_builder.build(
        [_rel(_known(), "related_to", _synthetic("Synthetic Entity"))],
        extract=False,
    )
    assert "Synthetic Entity" in {e["id"] for e in graph["entities"]}


def test_dict_source_relationship_with_all_endpoints_present():
    # Non-synthetic dict relationships with a legitimate entity set are left
    # untouched; endpoints already resolve so no dangling edge appears.
    graph = GraphBuilder(resolve_conflicts=False).build(
        {
            "entities": [{"id": "Known Entity", "name": "Known Entity"}],
            "relationships": [
                {
                    "source": "Known Entity",
                    "target": "Known Entity",
                    "type": "related_to",
                }
            ],
        },
        extract=False,
    )

    assert "Known Entity" in {e["id"] for e in graph["entities"]}
    assert not [i for i in _issues(graph) if i.get("code") == "DANGLING_EDGE"]