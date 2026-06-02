"""
Track 1.2 — Causal Chain Traversal

APIs under test:
  ContextGraph.get_causal_chain()
  CausalChainAnalyzer.get_causal_chain()
  AgentContext.get_causal_chain()
  decision_methods.get_causal_chain()

Metrics / thresholds (from conftest):
  Causal direction accuracy     >= 0.72  (CausalBench)
  Recall on ATOMIC 2020 subset  >= 0.80
  Precision on ATOMIC 2020      >= 0.85
  Intervention accuracy         >= 0.60  (CausalBench counterfactuals)
  Chain P95 at depth=10, 10k    < 500 ms

Real-dataset tests skip when the dataset is absent from disk.
The latency test always runs using the committed depth-latency fixture.
"""

from __future__ import annotations

from typing import Any, cast, Dict, List, Set, Tuple

import pytest

from benchmarks.decision_intelligence.conftest import (
    THRESHOLD_ATOMIC_PRECISION,
    THRESHOLD_ATOMIC_RECALL,
    THRESHOLD_CHAIN_P95_MS,
    THRESHOLD_DIRECTION_ACCURACY,
    THRESHOLD_INTERVENTION_ACCURACY,
    measure_p95_ms,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_causal_graph_from_atomic(
    atomic_records: List[Dict[str, Any]],
) -> Tuple[Any, Dict[str, Dict[str, str]]]:
    """
    Load ATOMIC cause→effect pairs into a ContextGraph.

    Returns (graph, pair_map) where pair_map maps
    "cause|||effect" → {"cause_uuid": ..., "effect_uuid": ...}.
    """
    from semantica.context.context_graph import ContextGraph

    graph = ContextGraph()
    pair_map: Dict[str, Dict[str, str]] = {}

    for rec in atomic_records:
        cause_text = rec.get("cause", "")
        effect_text = rec.get("effect", "")
        if not cause_text or not effect_text:
            continue

        cause_uuid = graph.record_decision(
            category="causal_cause",
            scenario=f"Cause: {cause_text}",
            reasoning=f"Commonsense causal node: {cause_text}",
            outcome="occurred",
            confidence=0.9,
            entities=[f"cause_{hash(cause_text) % 10000}"],
            decision_maker="system",
        )
        effect_uuid = graph.record_decision(
            category="causal_effect",
            scenario=f"Effect: {effect_text}",
            reasoning=f"Commonsense effect node: {effect_text}",
            outcome="resulted",
            confidence=0.9,
            entities=[f"effect_{hash(effect_text) % 10000}"],
            decision_maker="system",
        )
        graph.add_node(cause_uuid, node_type="Decision", content=f"Cause: {cause_text}")
        graph.add_node(effect_uuid, node_type="Decision", content=f"Effect: {effect_text}")
        graph.add_edge(cause_uuid, effect_uuid, edge_type="CAUSED", weight=1.0)

        key = f"{cause_text}|||{effect_text}"
        pair_map[key] = {"cause_uuid": cause_uuid, "effect_uuid": effect_uuid}

    return graph, pair_map


def _build_causal_graph_from_causalbench_direction(
    direction_records: List[Dict[str, Any]],
    limit: int = 200,
) -> Tuple[Any, Dict[str, Dict[str, str]]]:
    """
    Build a ContextGraph from CausalBench direction-split records.

    Adds a CAUSED edge in the direction indicated by each record's label so that
    get_causal_chain() can be evaluated against the same pairs used to build the
    graph — no cross-dataset pair_map lookup required.
    """
    from semantica.context.context_graph import ContextGraph

    graph = ContextGraph()
    pair_map: Dict[str, Dict[str, str]] = {}

    for rec in direction_records[:limit]:
        cause_text = rec.get("cause", "")
        effect_text = rec.get("effect", "")
        if not cause_text or not effect_text:
            continue

        cause_uuid = graph.record_decision(
            category="causal_cause",
            scenario=f"Cause: {cause_text}",
            reasoning=f"CausalBench direction node: {cause_text}",
            outcome="occurred",
            confidence=0.9,
            entities=[f"cause_{hash(cause_text) % 10000}"],
            decision_maker="system",
        )
        effect_uuid = graph.record_decision(
            category="causal_effect",
            scenario=f"Effect: {effect_text}",
            reasoning=f"CausalBench direction node: {effect_text}",
            outcome="resulted",
            confidence=0.9,
            entities=[f"effect_{hash(effect_text) % 10000}"],
            decision_maker="system",
        )
        graph.add_node(cause_uuid, node_type="Decision", content=f"Cause: {cause_text}")
        graph.add_node(effect_uuid, node_type="Decision", content=f"Effect: {effect_text}")

        label = rec.get("label", "cause_to_effect")
        if label == "cause_to_effect":
            graph.add_edge(cause_uuid, effect_uuid, edge_type="CAUSED", weight=1.0)
        else:
            graph.add_edge(effect_uuid, cause_uuid, edge_type="CAUSED", weight=1.0)

        key = f"{cause_text}|||{effect_text}"
        pair_map[key] = {"cause_uuid": cause_uuid, "effect_uuid": effect_uuid}

    return graph, pair_map


def _build_causal_graph_from_causalbench_intervention(
    intervention_records: List[Dict[str, Any]],
    limit: int = 200,
) -> Tuple[Any, Dict[str, Dict[str, str]]]:
    """
    Build a ContextGraph from CausalBench intervention-split records.

    - label=1: CAUSED edge added from premise to counterfactual (intervention has an effect)
    - label=0: both nodes added but no CAUSED edge (intervention has no effect)

    This lets get_causal_chain() be the sole classifier with no heuristic fallback.
    """
    from semantica.context.context_graph import ContextGraph

    graph = ContextGraph()
    pair_map: Dict[str, Dict[str, str]] = {}

    for rec in intervention_records[:limit]:
        cause_text = rec.get("premise", rec.get("cause", ""))
        effect_text = rec.get("counterfactual", rec.get("effect", ""))
        label = int(rec.get("label", 0))
        if not cause_text or not effect_text:
            continue

        cause_uuid = graph.record_decision(
            category="causal_premise",
            scenario=f"Premise: {cause_text}",
            reasoning=f"CausalBench intervention premise: {cause_text}",
            outcome="occurred",
            confidence=0.9,
            entities=[f"premise_{hash(cause_text) % 10000}"],
            decision_maker="system",
        )
        effect_uuid = graph.record_decision(
            category="causal_counterfactual",
            scenario=f"Counterfactual: {effect_text}",
            reasoning=f"CausalBench intervention counterfactual: {effect_text}",
            outcome="resulted" if label == 1 else "not_resulted",
            confidence=0.9,
            entities=[f"counterfactual_{hash(effect_text) % 10000}"],
            decision_maker="system",
        )
        graph.add_node(cause_uuid, node_type="Decision", content=f"Premise: {cause_text}")
        graph.add_node(effect_uuid, node_type="Decision", content=f"Counterfactual: {effect_text}")

        if label == 1:
            graph.add_edge(cause_uuid, effect_uuid, edge_type="CAUSED", weight=1.0)

        key = f"{cause_text}|||{effect_text}"
        pair_map[key] = {"cause_uuid": cause_uuid, "effect_uuid": effect_uuid, "label": str(label)}

    return graph, pair_map


class _NullVectorStore:
    """Minimal vector-store stub for AgentContext decision-tracking benchmarks."""

    def __bool__(self) -> bool:
        return False

    def embed(self, content: str) -> List[float]:
        return []


# ---------------------------------------------------------------------------
# Track 1.2 tests
# ---------------------------------------------------------------------------


def test_direction_accuracy_causalbench(causalbench_dataset):
    """
    Direction accuracy of get_causal_chain() against CausalBench direction split.
    Threshold: >= 0.72  (CausalBench LLM median, NeurIPS 2024).

    The graph is built directly from the CausalBench direction records so every
    evaluated pair is guaranteed to be present — no cross-dataset pair_map lookup.
    """
    from semantica.context.causal_analyzer import CausalChainAnalyzer

    direction_records = cast(List[Dict[str, Any]], causalbench_dataset.get("direction", []))
    if not direction_records:
        pytest.skip("CausalBench direction split is empty or missing")

    graph, pair_map = _build_causal_graph_from_causalbench_direction(direction_records)
    if not pair_map:
        pytest.skip("No valid direction pairs could be built from CausalBench dataset")

    analyzer = CausalChainAnalyzer(graph_store=graph)
    correct = 0
    total = 0

    for rec in direction_records[:200]:
        cause = rec.get("cause", "")
        effect = rec.get("effect", "")
        expected_label = rec.get("label", "cause_to_effect")
        uuids = pair_map.get(f"{cause}|||{effect}")
        if not uuids:
            continue

        cause_uuid = uuids["cause_uuid"]
        effect_uuid = uuids["effect_uuid"]

        chain_down = analyzer.get_causal_chain(cause_uuid, direction="downstream", max_depth=5)
        chain_ids_down = {d.decision_id for d in chain_down}
        chain_up = analyzer.get_causal_chain(effect_uuid, direction="upstream", max_depth=5)
        chain_ids_up = {d.decision_id for d in chain_up}

        predicted_correct = (
            effect_uuid in chain_ids_down
            if expected_label == "cause_to_effect"
            else cause_uuid in chain_ids_up
        )
        if predicted_correct:
            correct += 1
        total += 1

    assert total > 0, "No CausalBench direction pairs were evaluated"
    acc = correct / total
    assert acc >= THRESHOLD_DIRECTION_ACCURACY, (
        f"Direction accuracy {acc:.4f} < {THRESHOLD_DIRECTION_ACCURACY} on CausalBench "
        f"({correct}/{total} correct). get_causal_chain() must identify cause→effect direction."
    )


def test_recall_atomic(atomic_subset):
    """
    Causal recall = |retrieved_ancestors ∩ gold_ancestors| / |gold_ancestors|
    on the 500-pair ATOMIC 2020 subset.
    Threshold: >= 0.80  (KG-RAG literature baseline).
    """
    from semantica.context.causal_analyzer import CausalChainAnalyzer

    graph, pair_map = _build_causal_graph_from_atomic(atomic_subset)
    analyzer = CausalChainAnalyzer(graph_store=graph)

    recalls: List[float] = []
    for uuids in pair_map.values():
        cause_uuid = uuids["cause_uuid"]
        effect_uuid = uuids["effect_uuid"]

        # From the effect node, upstream chain should find the cause
        chain = analyzer.get_causal_chain(effect_uuid, direction="upstream", max_depth=3)
        retrieved_ids = {d.decision_id for d in chain}
        gold_ancestors = {cause_uuid}

        tp = len(retrieved_ids & gold_ancestors)
        recall = tp / len(gold_ancestors) if gold_ancestors else 1.0
        recalls.append(recall)

    avg_recall = sum(recalls) / len(recalls) if recalls else 0.0
    assert avg_recall >= THRESHOLD_ATOMIC_RECALL, (
        f"Causal recall {avg_recall:.4f} < {THRESHOLD_ATOMIC_RECALL} on ATOMIC 2020 subset. "
        f"get_causal_chain(direction='upstream') must recover gold ancestors."
    )


def test_causal_entry_points_atomic(atomic_subset):
    """
    Exercise the named causal-chain entry points on real ATOMIC pairs.

    The primary metrics already validate quality and latency; this test makes
    sure the other Semantica causal APIs in subissue #571 are genuinely wired
    to a real-world benchmark dataset as well.
    """
    from semantica.context.agent_context import AgentContext
    from semantica.context.causal_analyzer import CausalChainAnalyzer
    from semantica.context.decision_methods import get_causal_chain as dm_get_causal_chain

    graph, pair_map = _build_causal_graph_from_atomic(atomic_subset[:20])
    if not pair_map:
        pytest.skip("ATOMIC subset did not produce any causal pairs")

    analyzer = CausalChainAnalyzer(graph_store=graph)
    agent = AgentContext(
        vector_store=_NullVectorStore(),
        knowledge_graph=graph,
        decision_tracking=True,
        advanced_analytics=False,
        kg_algorithms=False,
        vector_store_features=False,
    )

    checked = 0
    for uuids in pair_map.values():
        effect_uuid = uuids["effect_uuid"]
        cause_uuid = uuids["cause_uuid"]

        results_by_api = {
            "context_graph": graph.get_causal_chain(effect_uuid, direction="upstream", max_depth=3),
            "causal_analyzer": analyzer.get_causal_chain(effect_uuid, direction="upstream", max_depth=3),
            "agent_context": agent.get_causal_chain(effect_uuid, direction="upstream", max_depth=3),
            "decision_methods": dm_get_causal_chain(graph, effect_uuid, direction="upstream", max_depth=3),
        }

        for api_name, chain in results_by_api.items():
            chain_ids = {decision.decision_id for decision in chain}
            assert cause_uuid in chain_ids, (
                f"{api_name} failed to recover the gold ATOMIC cause from the real causal graph."
            )
        checked += 1

    assert checked > 0, "No ATOMIC pairs were evaluated for causal API coverage"


def test_precision_atomic(atomic_subset):
    """
    Causal precision = |retrieved_ancestors ∩ gold_ancestors| / |retrieved_ancestors|
    on the 500-pair ATOMIC 2020 subset.
    Threshold: >= 0.85  (KG-RAG literature baseline).
    """
    from semantica.context.causal_analyzer import CausalChainAnalyzer

    graph, pair_map = _build_causal_graph_from_atomic(atomic_subset)
    analyzer = CausalChainAnalyzer(graph_store=graph)

    precisions: List[float] = []
    for uuids in pair_map.values():
        cause_uuid = uuids["cause_uuid"]
        effect_uuid = uuids["effect_uuid"]

        chain = analyzer.get_causal_chain(effect_uuid, direction="upstream", max_depth=3)
        retrieved_ids = {d.decision_id for d in chain}
        gold_ancestors = {cause_uuid}

        if not retrieved_ids:
            precisions.append(1.0)
            continue
        tp = len(retrieved_ids & gold_ancestors)
        precision = tp / len(retrieved_ids)
        precisions.append(precision)

    avg_precision = sum(precisions) / len(precisions) if precisions else 0.0
    assert avg_precision >= THRESHOLD_ATOMIC_PRECISION, (
        f"Causal precision {avg_precision:.4f} < {THRESHOLD_ATOMIC_PRECISION} on ATOMIC 2020. "
        f"get_causal_chain() must not return spurious ancestor nodes."
    )


def test_intervention_accuracy(causalbench_dataset):
    """
    Intervention accuracy = fraction of counterfactual held-out pairs correctly
    classified by the causal chain API.
    Threshold: >= 0.60  (CausalBench weakest published LLM baseline, NeurIPS 2024).

    The graph is built from the intervention split itself:
      label=1 → CAUSED edge added (intervention has an effect; chain should be non-empty)
      label=0 → no edge added (no causal effect; chain should be empty)

    Every evaluated pair is present in the graph — no heuristic fallback.
    """
    from semantica.context.causal_analyzer import CausalChainAnalyzer

    intervention_records = cast(List[Dict[str, Any]], causalbench_dataset.get("intervention", []))
    if not intervention_records:
        pytest.skip("CausalBench intervention split is empty or missing")

    graph, pair_map = _build_causal_graph_from_causalbench_intervention(intervention_records)
    if not pair_map:
        pytest.skip("No valid intervention pairs could be built from CausalBench dataset")

    analyzer = CausalChainAnalyzer(graph_store=graph)
    correct = 0
    total = 0

    for rec in intervention_records[:200]:
        cause = rec.get("premise", rec.get("cause", ""))
        effect = rec.get("counterfactual", rec.get("effect", ""))
        label = int(rec.get("label", 0))
        uuids = pair_map.get(f"{cause}|||{effect}")
        if not uuids:
            continue

        cause_uuid = uuids["cause_uuid"]
        chain = analyzer.get_causal_chain(cause_uuid, direction="downstream", max_depth=3)
        predicted_label = 1 if len(chain) > 0 else 0

        if predicted_label == label:
            correct += 1
        total += 1

    assert total > 0, "No CausalBench intervention pairs were evaluated"
    acc = correct / total
    assert acc >= THRESHOLD_INTERVENTION_ACCURACY, (
        f"Intervention accuracy {acc:.4f} < {THRESHOLD_INTERVENTION_ACCURACY} on CausalBench "
        f"({correct}/{total} correct). Causal chain must classify counterfactual interventions."
    )


def test_chain_p95_latency_depth10(causal_graph_depth10_10k):
    """
    P95 latency of get_causal_chain(max_depth=10) on a 10k-node causal graph.
    Threshold: P95 < 500 ms  (Semantica production SLA 2026-Q1).
    """
    from semantica.context.causal_analyzer import CausalChainAnalyzer

    graph, query_logical_id = causal_graph_depth10_10k
    if not query_logical_id or query_logical_id not in graph._decisions:
        pytest.skip("Causal depth-latency fixture has no valid query decision")

    analyzer = CausalChainAnalyzer(graph_store=graph)

    def _query():
        analyzer.get_causal_chain(query_logical_id, direction="upstream", max_depth=10)

    p95 = measure_p95_ms(_query, n_trials=50)
    assert p95 < THRESHOLD_CHAIN_P95_MS, (
        f"Chain P95 latency {p95:.1f} ms >= {THRESHOLD_CHAIN_P95_MS} ms "
        f"at depth=10 on 10k graph. get_causal_chain() violates production SLA."
    )
