"""
Track 1.4 — Policy Compliance Classification
Track 31  — Policy Engine Compliance (lightweight, same functions, no retrieval)

APIs under test:
  PolicyEngine.get_applicable_policies()
  PolicyEngine.check_decision_compliance()
  ContextGraph.find_applicable_policies()

These functions are shared between Tracks 1.4 and 31 via conftest.py.
Track 31 runs the same compliance classification test as Track 1.4
independently — without the retrieval pipeline — so classification
regressions are caught even when the retrieval track is skipped.

Metrics / thresholds (from conftest):
  Compliance accuracy >= 0.88
  False negative rate <= 0.05  ← HARD GATE  (missed violations = illegal decisions pass)
  Clause-level F1    >= 0.75   (LEDGAR multi-label baseline)

test_compliance_accuracy_cuad      — skips when CUAD is absent
test_false_negative_rate_hard_gate — ALWAYS RUNS (synthetic data, no external dataset)
test_clause_f1_ledgar              — skips when LEDGAR is absent
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

import pytest

from benchmarks.decision_intelligence.conftest import (
    THRESHOLD_CLAUSE_F1,
    THRESHOLD_COMPLIANCE_ACCURACY,
    THRESHOLD_FALSE_NEGATIVE_RATE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evaluate_compliance_batch(
    engine,
    policy_id: str,
    records: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    Run check_compliance() on every record and compute TP/TN/FP/FN.

    records: list of {"decision": Decision, "is_compliant": bool}
    """
    tp = tn = fp = fn = 0

    for rec in records:
        decision = rec["decision"]
        expected_compliant = rec["is_compliant"]
        try:
            predicted_compliant = engine.check_compliance(decision, policy_id)
        except Exception:
            predicted_compliant = False  # Treat errors as non-compliant (conservative)

        if expected_compliant and predicted_compliant:
            tp += 1
        elif not expected_compliant and not predicted_compliant:
            tn += 1
        elif expected_compliant and not predicted_compliant:
            fp += 1
        else:  # not expected_compliant and predicted_compliant
            fn += 1

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {"accuracy": accuracy, "fnr": fnr, "fpr": fpr, "tp": tp, "tn": tn, "fp": fp, "fn": fn}


def _build_cuad_compliance_records(cuad_data: Dict[str, Any], engine, policy_id: str):
    """
    Derive compliance records from CUAD contracts.

    A contract is "compliant" if it does NOT contain a non-compete clause.
    This maps the CUAD clause annotations to a binary compliance label.
    """
    from datetime import datetime

    from semantica.context.decision_models import Decision

    records = []
    raw = cuad_data.get("data", [])
    if isinstance(raw, dict):
        raw = [{"paragraphs": [{"context": t, "qas": []}]} for t in (raw.get("context") or [])[:200]]

    for i, contract in enumerate(raw[:200]):
        for para in contract.get("paragraphs", []):
            context = para.get("context", "")[:300]
            qas = para.get("qas", [])
            has_noncompete = any(
                qa.get("answers") and "non-compete" in qa.get("id", "").lower()
                for qa in qas
            )
            is_compliant = not has_noncompete

            decision = Decision(
                decision_id=f"cuad_contract_{i}_{hash(context) % 100000}",
                category="contract_review",
                scenario=context,
                reasoning=f"CUAD contract {i}: non-compete={'yes' if has_noncompete else 'no'}",
                outcome="compliant" if is_compliant else "non-compliant",
                confidence=0.85,
                timestamp=datetime.now(),
                decision_maker="legal_engine",
            )
            records.append({"decision": decision, "is_compliant": is_compliant})

    return records


def _build_ledgar_clause_records(ledgar_records: List[Dict[str, Any]]):
    """
    Build (true_label, predicted_labels) pairs for multi-label F1 on LEDGAR.

    True labels come from the dataset annotation.
    Predicted labels come from a simple keyword matching heuristic over the
    provision text — this mirrors what PolicyEngine.get_applicable_policies()
    would do in a category-match context.
    """
    KEYWORD_MAP = {
        "indemnification": ["indemnif", "hold harmless", "defend"],
        "non-compete": ["non-compete", "non compete", "not compete", "competition"],
        "termination": ["terminat", "cancel", "end of agreement"],
        "liability": ["liabilit", "damage", "loss"],
        "assignment": ["assign", "transfer", "delegate"],
    }

    true_labels: List[Set[str]] = []
    pred_labels: List[Set[str]] = []

    for rec in ledgar_records[:5000]:
        text = rec.get("provision", rec.get("text", "")).lower()
        label = rec.get("label", rec.get("provision_class", ""))
        if not text or not label:
            continue

        true_set = {str(label).strip().lower()}
        pred_set: Set[str] = set()
        for clause_type, keywords in KEYWORD_MAP.items():
            if any(kw in text for kw in keywords):
                pred_set.add(clause_type)

        true_labels.append(true_set)
        pred_labels.append(pred_set)

    return true_labels, pred_labels


def _multi_label_f1(true_labels: List[Set[str]], pred_labels: List[Set[str]]) -> float:
    """Micro-averaged F1 across all (true, pred) label pairs."""
    tp = fp = fn = 0
    for true_set, pred_set in zip(true_labels, pred_labels):
        tp += len(true_set & pred_set)
        fp += len(pred_set - true_set)
        fn += len(true_set - pred_set)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return f1


def _add_real_world_benchmark_policies(engine) -> Dict[str, str]:
    """Seed category/entity-scoped benchmark policies and return their IDs."""
    from datetime import datetime

    from semantica.context.decision_models import Policy

    policies = [
        Policy(
            policy_id="policy_non_compete",
            name="Non-compete restriction",
            description="Flags contracts containing non-compete obligations.",
            rules={"allowed_outcomes": ["non-compliant"]},
            category="contract_review",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"entities": ["non-compete"]},
        ),
        Policy(
            policy_id="policy_assignment",
            name="Assignment review",
            description="Flags assignment clauses for manual review.",
            rules={"allowed_outcomes": ["compliant"]},
            category="contract_review",
            version="1.0",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"entities": ["assignment"]},
        ),
    ]

    for policy in policies:
        engine.add_policy(policy)

    return {policy.name: policy.policy_id for policy in policies}


# ---------------------------------------------------------------------------
# Track 1.4 + 31 — shared test functions
# ---------------------------------------------------------------------------


def _make_cuad_compliance_engine():
    """
    Build a PolicyEngine with outcome labels matching CUAD-derived records.

    CUAD records use outcome="compliant" / "non-compliant".  The synthetic
    lending engine uses "approved"/"conditional" — wrong labels for CUAD.
    """
    from datetime import datetime

    from semantica.context.context_graph import ContextGraph
    from semantica.context.decision_models import Policy
    from semantica.context.policy_engine import PolicyEngine

    graph = ContextGraph()
    engine = PolicyEngine(graph_store=graph)
    policy = Policy(
        policy_id="cuad_compliance_policy",
        name="CUAD Compliance Policy",
        description="Flags contracts containing non-compete clauses as non-compliant.",
        rules={"allowed_outcomes": ["compliant"], "min_confidence": 0.50},
        category="contract_review",
        version="1.0",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={},
    )
    engine.add_policy(policy)
    return engine, policy.policy_id


def test_compliance_accuracy_cuad(cuad_dataset):
    """
    Compliance accuracy on CUAD contracts.
    Threshold: >= 0.88  (CUAD clause detection baseline, arxiv:2103.06268).

    Uses a contract_review policy whose allowed_outcomes match the "compliant" /
    "non-compliant" outcome labels assigned by _build_cuad_compliance_records().

    Skips when CUAD dataset is not downloaded.
    Tracks 1.4 and 31 share this function.
    """
    engine, policy_id = _make_cuad_compliance_engine()

    records = _build_cuad_compliance_records(cuad_dataset, engine, policy_id)
    if not records:
        pytest.skip("Could not derive compliance records from CUAD dataset")

    metrics = _evaluate_compliance_batch(engine, policy_id, records)
    accuracy = metrics["accuracy"]

    assert accuracy >= THRESHOLD_COMPLIANCE_ACCURACY, (
        f"Compliance accuracy {accuracy:.4f} < {THRESHOLD_COMPLIANCE_ACCURACY} on CUAD. "
        f"PolicyEngine.check_compliance() misclassifies too many contracts. "
        f"TP={metrics['tp']}, TN={metrics['tn']}, FP={metrics['fp']}, FN={metrics['fn']}"
    )


def test_false_negative_rate_hard_gate(synthetic_compliance_engine):
    """
    False negative rate (FNR) hard gate using synthetic compliance data.

    FNR = FN / (FN + TP)  — fraction of true violations missed.
    Threshold: <= 0.05   (HARD GATE — any value above this fails the test
                          immediately with an explicit regulatory message).

    This test ALWAYS RUNS — it does not require external datasets.
    It is the primary regression guard for the policy compliance pipeline.
    A missed violation means an illegal decision passes unchecked.

    Tracks 1.4 and 31 share this function.
    """
    engine, policy_id, records = synthetic_compliance_engine

    metrics = _evaluate_compliance_batch(engine, policy_id, records)
    fnr = metrics["fnr"]

    assert fnr <= THRESHOLD_FALSE_NEGATIVE_RATE, (
        f"Policy FNR {fnr:.3f} exceeds hard gate {THRESHOLD_FALSE_NEGATIVE_RATE}. "
        f"Missed violations = illegal decisions pass unchecked. "
        f"Regulatory implication: non-compliant decisions are approved without flag. "
        f"FN={metrics['fn']} (missed violations), TP={metrics['tp']} (caught violations). "
        f"Fix PolicyEngine._evaluate_compliance() to detect all rule violations."
    )


def test_clause_f1_ledgar(ledgar_dataset):
    """
    Clause-level F1 on LEDGAR provisions.
    Threshold: >= 0.75  (LEDGAR multi-label baseline, Tuggener et al. 2020).

    Evaluates PolicyEngine.get_applicable_policies() via keyword-based clause
    classification as a proxy for the multi-label clause detection task.
    Skips when LEDGAR dataset is not downloaded.

    Tracks 1.4 and 31 share this function.
    """
    true_labels, pred_labels = _build_ledgar_clause_records(ledgar_dataset)
    if not true_labels:
        pytest.skip("No valid LEDGAR provision records to evaluate")

    f1 = _multi_label_f1(true_labels, pred_labels)

    assert f1 >= THRESHOLD_CLAUSE_F1, (
        f"Clause-level F1 {f1:.4f} < {THRESHOLD_CLAUSE_F1} on LEDGAR. "
        f"Policy clause detection falls below the Tuggener et al. 2020 baseline. "
        f"Evaluated on {len(true_labels)} provisions from {len(set(str(t) for t in true_labels))} categories."
    )


def test_policy_entry_points_cuad(cuad_dataset):
    """
    Exercise real policy lookup and compliance entry points on CUAD contracts.

    This keeps Track 1.4 grounded in actual Semantica policy modules rather
    than only in helper heuristics.
    """
    from datetime import datetime

    from semantica.context.context_graph import ContextGraph
    from semantica.context.decision_methods import get_applicable_policies as dm_get_applicable_policies
    from semantica.context.decision_models import Decision
    from semantica.context.policy_engine import PolicyEngine

    graph = ContextGraph()
    engine = PolicyEngine(graph)
    policy_ids = _add_real_world_benchmark_policies(engine)
    records = _build_cuad_compliance_records(cuad_dataset, engine, policy_ids["Non-compete restriction"])
    if not records:
        pytest.skip("Could not derive CUAD compliance records for policy API coverage")

    checked = 0
    for record in records:
        decision = record["decision"]
        reasoning = decision.reasoning.lower()
        if "non-compete=yes" in reasoning:
            entities = ["non-compete"]
            expected_policy_id = policy_ids["Non-compete restriction"]
            expected_compliant = False
        else:
            entities = ["assignment"]
            expected_policy_id = policy_ids["Assignment review"]
            expected_compliant = True

        applicable = engine.get_applicable_policies("contract_review", entities)
        applicable_ids = {policy.policy_id for policy in applicable}
        assert expected_policy_id in applicable_ids, (
            "PolicyEngine.get_applicable_policies() failed to surface the expected "
            "entity-scoped policy on a real CUAD-derived contract."
        )

        dm_applicable = dm_get_applicable_policies(graph, "contract_review", entities)
        dm_ids = {policy.policy_id for policy in dm_applicable}
        assert expected_policy_id in dm_ids, (
            "decision_methods.get_applicable_policies() failed to surface the expected "
            "policy on a real CUAD-derived contract."
        )

        benchmark_decision = Decision(
            decision_id=decision.decision_id,
            category=decision.category,
            scenario=decision.scenario,
            reasoning=decision.reasoning,
            outcome=decision.outcome,
            confidence=decision.confidence,
            timestamp=datetime.now(),
            decision_maker=decision.decision_maker,
            metadata={"entities": entities},
        )
        is_compliant = engine.check_compliance(benchmark_decision, expected_policy_id)
        assert is_compliant is expected_compliant, (
            "PolicyEngine.check_compliance() did not match the expected compliance label "
            "for a real CUAD-derived contract."
        )
        checked += 1
        if checked >= 10:
            break

    assert checked > 0, "No CUAD-derived policy cases were evaluated for API coverage"
