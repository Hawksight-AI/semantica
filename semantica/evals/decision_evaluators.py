"""Decision-specialized evaluator.

``decision_scores`` validates a ``Decision`` (or dict) against field-level and
governance-level checks: expected outcome, confidence bounds, non-empty
required fields, provenance presence, and (when configured) policy compliance
via ``PolicyEngine.check_compliance``.
"""

from typing import Any, Dict, Optional

from .registry import register
from .types import EvalMetric


def _coerce_decision(actual: Any):
    """Return a Decision or None; never raise for dict inputs."""
    from semantica.context.decision_models import Decision

    if isinstance(actual, Decision):
        return actual
    if isinstance(actual, dict):
        try:
            return Decision(**actual)
        except (TypeError, ValueError, KeyError):
            return None
    return None


@register("decision_scores")
def decision_scores(actual, expected=None, config=None, **kwargs):
    """Composite evaluator over a Decision; see module docstring for sub-checks."""
    cfg = config or {}
    decision = _coerce_decision(actual)
    if decision is None:
        return EvalMetric(0.0, False, {"error": "input is not a valid Decision or dict"})

    checks: Dict[str, bool] = {}
    reasons: Dict[str, str] = {}

    checks["decision_outcome"] = decision.outcome == cfg.get("expected_outcome")
    if not checks["decision_outcome"]:
        reasons["decision_outcome"] = f"expected {cfg.get('expected_outcome')!r}, got {decision.outcome!r}"

    lo = cfg.get("min_confidence", 0.0)
    hi = cfg.get("max_confidence", 1.0)
    checks["decision_confidence"] = lo <= decision.confidence <= hi
    if not checks["decision_confidence"]:
        reasons["decision_confidence"] = f"{decision.confidence} not in [{lo}, {hi}]"

    for field in ("decision_maker", "reasoning", "scenario"):
        value = getattr(decision, field, None)
        checks[field] = isinstance(value, str) and bool(value.strip())
        if not checks[field]:
            reasons[field] = f"field {field!r} is empty"

    prov = (decision.metadata or {}).get(cfg.get("provenance_key", "provenance"))
    checks["provenance"] = bool(prov)
    if not checks["provenance"]:
        reasons["provenance"] = "no provenance record found in metadata"

    policy_engine = cfg.get("policy_engine")
    policy_id = cfg.get("policy_id")
    if policy_engine is not None and policy_id is not None:
        try:
            compliant = bool(policy_engine.check_compliance(decision, policy_id))
            checks["policy"] = compliant == cfg.get("expected_policy_compliant", True)
            if not checks["policy"]:
                reasons["policy"] = f"compliance={compliant}"
        except Exception as exc:  # noqa: BLE001
            checks["policy"] = False
            reasons["policy"] = str(exc)

    if cfg.get("causal_chain_exists"):
        raise NotImplementedError(
            "decision_scores causal_chain_exists is an interface slot reserved for V2"
        )

    passed_count = sum(checks.values())
    total = len(checks)
    passed = total > 0 and passed_count == total
    meta = dict(checks)
    meta["reasons"] = reasons
    return EvalMetric(
        score=passed_count / total if total else 0.0,
        passed=passed,
        meta=meta,
    )
