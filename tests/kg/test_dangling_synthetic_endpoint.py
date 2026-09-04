"""Tests for reconciling synthetic relation endpoints into the graph.

Relation extraction synthesizes ``UNKNOWN`` entities for endpoints that are
absent from the NER entity list, but ``GraphBuilder._process_item`` kept only
the endpoint string. The resulting graph then failed ``GraphValidator`` with
``DANGLING_EDGE``. See issue #1463.
"""

from semantica.kg import GraphBuilder, GraphValidator
from semantica.semantic_extract import Entity, Relation, Triplet


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


def test_merge_entities_true_no_dangling_edge():
    # With entity merging explicitly enabled (and conflict resolution on, the
    # default), a promoted synthetic endpoint still must not leave a dangling
    # edge and must not duplicate the existing entity.
    graph = GraphBuilder(merge_entities=True).build(
        [_known(), _rel(_known(), "related_to", _synthetic("Synthetic Entity"))],
        extract=False,
    )

    assert not [i for i in _issues(graph) if i.get("code") == "DANGLING_EDGE"]
    synthetic = [e for e in graph["entities"] if e["id"] == "Synthetic Entity"]
    assert len(synthetic) == 1


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


def test_reject_policy_via_nested_config():
    # The orchestrator constructs GraphBuilder(config=self.config.get("kg", {})),
    # which lands as a nested "config" keyword. The policy lookup must read
    # through that nesting so the reject option works end to end.
    builder = GraphBuilder(
        resolve_conflicts=False,
        config={"unknown_relation_endpoint": "reject"},
    )
    graph = builder.build(
        [_rel(_known(), "related_to", _synthetic("Synthetic Entity"))],
        extract=False,
    )

    assert graph["relationships"] == []
    assert "Synthetic Entity" not in {e["id"] for e in graph["entities"]}


def test_real_entity_wins_over_prior_synthetic():
    # A synthetic endpoint promoted early must yield to a real entity with the
    # same id that arrives later (e.g. relation data precedes NER entity data).
    graph = GraphBuilder(resolve_conflicts=False).build(
        [_rel(_synthetic("Shared"), "related_to", _known("Other"))],
        extract=False,
    )
    # Force a real "Shared" entity to coexist with the promoted synthetic one and
    # confirm only the real one survives.
    real_graph = GraphBuilder(resolve_conflicts=False).build(
        [
            _synthetic("Shared"),
            _known("Shared"),
            _rel(_synthetic("Shared"), "related_to", _known("Other")),
        ],
        extract=False,
    )

    shared = [e for e in real_graph["entities"] if e["id"] == "Shared"]
    assert len(shared) == 1
    assert shared[0]["metadata"].get("synthetic") is not True


def test_triplet_with_synthetic_endpoint_promoted():
    # The LLM triplet path tags endpoint texts it could not match, and the
    # GraphBuilder promotes them as synthetic entities (issue #1463).
    triplet = Triplet(
        subject="Missing Subj",
        predicate="related_to",
        object="Known Target",
    )
    triplet.metadata = {"synthetic_endpoints": ["Missing Subj"]}
    graph = GraphBuilder(resolve_conflicts=False).build(
        [_known("Known Target"), triplet],
        extract=False,
    )

    entity_ids = {e["id"] for e in graph["entities"]}
    assert "Missing Subj" in entity_ids
    assert not [i for i in _issues(graph) if i.get("code") == "DANGLING_EDGE"]


def test_synthetic_endpoint_deduped_against_entity_id():
    # A dict entity may carry its canonical id under "entity_id". A synthetic
    # endpoint promoted with the same id must not create a duplicate node.
    graph = GraphBuilder(resolve_conflicts=False).build(
        [
            {"entity_id": "Shared", "name": "Shared"},
            _rel(_synthetic("Shared"), "related_to", _known("Other")),
        ],
        extract=False,
    )

    ids = [
        e.get("id")
        for e in graph["entities"]
        if e.get("id") == "Shared" or e.get("entity_id") == "Shared"
    ]
    assert len(ids) == 1


def test_dict_relationship_unknown_endpoint_untouched_by_design():
    # Dictionary-form relationships stay out of the synthetic reconcile path by
    # design; they have no synthetic marker so no entity is invented on their
    # behalf.
    graph = GraphBuilder(resolve_conflicts=False).build(
        {
            "entities": [{"id": "Known"}],
            "relationships": [
                {"source": "Known", "target": "Absent", "type": "related_to"}
            ],
        },
        extract=False,
    )

    ids = {e["id"] for e in graph["entities"]}
    assert "Known" in ids
    assert "Absent" not in ids