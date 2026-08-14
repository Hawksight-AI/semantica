"""Regression tests for explicit causal edges in decision tracing (issue #975).

``trace_decision_causality()`` used to infer causes purely from shared NER
entities plus timestamps, so relationships recorded through
``add_causal_relationship()`` had no effect on the trace. When entity
extraction found nothing, the chain came back empty even though an explicit
``CAUSED`` edge was stored in the graph.
"""

from semantica.context import ContextGraph
from semantica.context.context_graph import ContextEdge


CAUSAL_EDGE_TYPES = ("CAUSED", "INFLUENCED", "PRECEDENT_FOR")


def _graph_with_linked_decisions(category_a="hardware", category_b="failover"):
    """Two decisions joined by an explicit CAUSED edge."""
    graph = ContextGraph(advanced_analytics=True)
    cause = graph.record_decision(
        category=category_a,
        scenario="Server Alpha fails",
        reasoning="PSU defect on server Alpha",
        outcome="flagged",
        confidence=0.9,
    )
    effect = graph.record_decision(
        category=category_b,
        scenario="Failover to server Beta",
        reasoning="Failover triggered because of server Alpha outage",
        outcome="approved",
        confidence=0.9,
    )
    graph.add_causal_relationship(cause, effect, relationship_type="CAUSED")
    return graph, cause, effect


def test_trace_uses_explicit_edge_when_no_entities_extracted():
    """The issue's reproduction: explicit edge must drive the trace on its own."""
    graph, cause, effect = _graph_with_linked_decisions()

    # Precondition: the bug is only visible when NER finds nothing to overlap on.
    assert graph._decisions[cause]["entities"] == []
    assert graph._decisions[effect]["entities"] == []

    chains = graph.trace_decision_chain(effect)

    assert chains, "explicit CAUSED edge must produce a causal chain"
    hops = [hop for chain in chains for hop in chain["hops"]]
    assert any(
        hop["from"] == cause and hop["to"] == effect and hop["type"] == "CAUSED"
        for hop in hops
    )


def test_trace_reports_relationship_type_of_each_explicit_edge():
    for relationship_type in CAUSAL_EDGE_TYPES:
        graph = ContextGraph(advanced_analytics=True)
        cause = graph.record_decision(
            category="a", scenario="upstream", reasoning="r",
            outcome="approved", confidence=0.9,
        )
        effect = graph.record_decision(
            category="b", scenario="downstream", reasoning="r",
            outcome="approved", confidence=0.9,
        )
        graph.add_causal_relationship(cause, effect, relationship_type=relationship_type)

        hops = [hop for chain in graph.trace_decision_chain(effect) for hop in chain["hops"]]
        assert [hop["type"] for hop in hops] == [relationship_type]


def test_trace_follows_multi_hop_explicit_chain():
    graph = ContextGraph(advanced_analytics=True)
    first = graph.record_decision(
        category="a", scenario="root cause", reasoning="r",
        outcome="flagged", confidence=0.9,
    )
    second = graph.record_decision(
        category="b", scenario="mitigation", reasoning="r",
        outcome="approved", confidence=0.9,
    )
    third = graph.record_decision(
        category="c", scenario="follow-up", reasoning="r",
        outcome="approved", confidence=0.9,
    )
    graph.add_causal_relationship(first, second, relationship_type="CAUSED")
    graph.add_causal_relationship(second, third, relationship_type="CAUSED")

    chains = graph.trace_decision_chain(third)
    traced = {(hop["from"], hop["to"]) for chain in chains for hop in chain["hops"]}

    assert (second, third) in traced
    assert (first, second) in traced


def test_trace_survives_edge_referencing_unrecorded_decision():
    """Edges can outlive ``_decisions`` (e.g. a graph restored via from_dict).

    Such an edge must be skipped rather than aborting the whole trace.
    """
    graph, cause, effect = _graph_with_linked_decisions()

    graph.add_node("ghost", "decision", content="never recorded via record_decision")
    graph._add_internal_edge(
        ContextEdge(
            source_id="ghost",
            target_id=effect,
            edge_type="CAUSED",
            weight=1.0,
            metadata={},
        )
    )

    chains = graph.trace_decision_chain(effect)

    assert not any("error" in chain for chain in chains)
    hops = [hop for chain in chains for hop in chain["hops"]]
    assert any(hop["from"] == cause for hop in hops), "valid chain must survive"
    assert not any(hop["from"] == "ghost" for hop in hops)


def test_explicitly_linked_decision_counts_as_direct_influence():
    """Differing categories, so the category-match shortcut cannot mask the bug."""
    graph, cause, effect = _graph_with_linked_decisions(
        category_a="hardware", category_b="failover"
    )

    impact = graph.analyze_decision_impact(cause)
    direct_ids = {entry["decision_id"] for entry in impact["direct_influence"]}
    indirect_ids = {entry["decision_id"] for entry in impact["indirect_influence"]}

    assert effect in direct_ids
    assert effect not in indirect_ids


def test_influence_is_not_double_counted_as_direct_and_indirect():
    graph, cause, effect = _graph_with_linked_decisions(
        category_a="shared", category_b="shared"
    )

    impact = graph.analyze_decision_impact(cause)
    direct_ids = {entry["decision_id"] for entry in impact["direct_influence"]}
    indirect_ids = {entry["decision_id"] for entry in impact["indirect_influence"]}

    assert not direct_ids & indirect_ids


def test_entity_based_inference_still_applies_without_explicit_edges():
    """The entity heuristic remains as a fallback; it must not be regressed."""
    graph = ContextGraph(advanced_analytics=True)
    earlier = graph.record_decision(
        category="ops", scenario="first", reasoning="r",
        outcome="approved", confidence=0.9,
    )
    later = graph.record_decision(
        category="ops", scenario="second", reasoning="r",
        outcome="approved", confidence=0.9,
    )

    # Simulate NER having produced a shared entity between the two decisions.
    shared_entity = "server_alpha"
    for decision_id in (earlier, later):
        graph._decisions[decision_id]["entities"] = [shared_entity]
    graph._entity_index.setdefault(shared_entity, set()).update({earlier, later})
    graph._decisions[earlier]["timestamp"] = graph._decisions[later]["timestamp"] - 60

    hops = [hop for chain in graph.trace_decision_chain(later) for hop in chain["hops"]]

    assert any(
        hop["from"] == earlier and hop["to"] == later and hop["type"] == "influences"
        for hop in hops
    )
