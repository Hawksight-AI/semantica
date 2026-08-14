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


def test_explicit_edge_weight_of_zero_is_preserved():
    """``add_edge()`` is public and can create causal edges with any weight.

    A stored 0.0 must not be coerced to the 1.0 default, which would inflate
    ``confidence_decay`` in the causal-chain report.
    """
    graph = ContextGraph(advanced_analytics=True)
    cause = graph.record_decision(
        category="a", scenario="upstream", reasoning="r",
        outcome="approved", confidence=0.9,
    )
    effect = graph.record_decision(
        category="b", scenario="downstream", reasoning="r",
        outcome="approved", confidence=0.9,
    )
    graph.add_edge(cause, effect, "CAUSED", weight=0.0)

    chains = graph.trace_decision_chain(effect)

    assert [hop["edge_weight"] for chain in chains for hop in chain["hops"]] == [0.0]
    assert [chain["confidence_decay"] for chain in chains] == [0.0]


def test_parallel_causal_edges_are_all_traced():
    """Multiple causal edges between the same pair must not overwrite each other."""
    graph = ContextGraph(advanced_analytics=True)
    cause = graph.record_decision(
        category="a", scenario="upstream", reasoning="r",
        outcome="approved", confidence=0.9,
    )
    effect = graph.record_decision(
        category="b", scenario="downstream", reasoning="r",
        outcome="approved", confidence=0.9,
    )
    graph.add_edge(cause, effect, "CAUSED", weight=0.8)
    graph.add_edge(cause, effect, "INFLUENCED", weight=0.3)

    hops = [hop for chain in graph.trace_decision_chain(effect) for hop in chain["hops"]]

    assert sorted(hop["type"] for hop in hops) == ["CAUSED", "INFLUENCED"]
    assert sorted(hop["edge_weight"] for hop in hops) == [0.3, 0.8]


def test_branching_graph_does_not_drop_alternative_chains():
    """Diamond graph: both routes through the shared ancestor must be reported.

    Cycle detection is per-path, so visiting ``S`` via one branch must not
    prevent reaching it again through the other.
    """
    graph = ContextGraph(advanced_analytics=True)
    ids = {
        name: graph.record_decision(
            category="ops", scenario=name, reasoning="r",
            outcome="approved", confidence=0.9,
        )
        for name in ("R", "S", "A", "B", "D")
    }
    names = {decision_id: name for name, decision_id in ids.items()}
    for source, target in [("R", "S"), ("S", "A"), ("S", "B"), ("A", "D"), ("B", "D")]:
        graph.add_causal_relationship(ids[source], ids[target], relationship_type="CAUSED")

    chains = graph.trace_decision_chain(ids["D"], max_steps=10)
    paths = {
        " -> ".join(
            [names[hop["from"]] for hop in chain["hops"]]
            + [names[chain["hops"][-1]["to"]]]
        )
        for chain in chains
    }

    assert "R -> S -> A -> D" in paths
    assert "R -> S -> B -> D" in paths


def test_cyclic_causal_edges_terminate():
    """A causal cycle must not recurse forever once cycle detection is per-path."""
    graph = ContextGraph(advanced_analytics=True)
    first = graph.record_decision(
        category="a", scenario="A", reasoning="r", outcome="approved", confidence=0.9,
    )
    second = graph.record_decision(
        category="b", scenario="B", reasoning="r", outcome="approved", confidence=0.9,
    )
    third = graph.record_decision(
        category="c", scenario="C", reasoning="r", outcome="approved", confidence=0.9,
    )
    graph.add_causal_relationship(first, second, relationship_type="CAUSED")
    graph.add_causal_relationship(second, third, relationship_type="CAUSED")
    graph.add_causal_relationship(third, first, relationship_type="CAUSED")

    chains = graph.trace_decision_chain(first, max_steps=5)

    assert chains
    assert not any("error" in chain for chain in chains)


def _dense_causal_graph(levels, width):
    """Layered DAG where every decision in a layer causes every one in the next."""
    graph = ContextGraph(advanced_analytics=True)
    layers = []
    for level in range(levels):
        layers.append([
            graph.record_decision(
                category="ops", scenario=f"L{level}n{index}", reasoning="r",
                outcome="approved", confidence=0.9,
            )
            for index in range(width)
        ])
    for level in range(levels - 1):
        for source in layers[level]:
            for target in layers[level + 1]:
                graph.add_causal_relationship(source, target, relationship_type="CAUSED")
    return graph, layers[-1][0]


def test_dense_graph_is_bounded_and_reports_truncation():
    """Per-path traversal is combinatorial, so the result must stay bounded.

    Truncation is reported rather than silently dropping chains, which is the
    very failure this module exists to prevent.
    """
    graph, sink = _dense_causal_graph(levels=9, width=5)

    chains = graph.trace_decision_chain(sink, max_steps=9, max_chains=500)

    markers = [chain for chain in chains if chain.get("truncated")]
    assert len(markers) == 1, "truncation must be reported exactly once"
    assert markers[0]["max_chains"] == 500
    assert len(chains) == 501, "500 chains plus the marker"


def test_small_graph_reports_no_truncation():
    """The cap must not alter results for graphs that fit within it."""
    graph, sink = _dense_causal_graph(levels=5, width=2)

    chains = graph.trace_decision_chain(sink)

    assert chains
    assert not any(chain.get("truncated") for chain in chains)


def test_max_chains_none_disables_the_cap():
    graph, sink = _dense_causal_graph(levels=5, width=5)

    capped = graph.trace_decision_chain(sink, max_chains=100)
    uncapped = graph.trace_decision_chain(sink, max_chains=None)

    assert len(capped) == 101
    assert not any(chain.get("truncated") for chain in uncapped)
    assert len(uncapped) > len(capped)


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
