"""Evaluation runner: orchestrates evaluators over a list of cases."""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .registry import get_evaluator
from .types import CaseResult, EvalMetric, EvalSummary

Case = Union[Dict[str, Any], Tuple[Any, Any]]


def _parse_objective(name, eval_config):
    """Return the validated objective dict, or None when not configured.

    Raises ValueError for invalid configurations (programmer error).
    """
    objective = (eval_config or {}).get("objective")
    if objective is None:
        return None
    if not isinstance(objective, dict):
        raise ValueError(
            f"objective for '{name}': expected a dict, got {type(objective).__name__}"
        )
    direction = objective.get("direction")
    threshold = objective.get("threshold")
    expect = objective.get("expect")

    if expect is not None:
        if not isinstance(expect, bool):
            raise ValueError(
                f"objective for '{name}': 'expect' must be a bool (got {expect!r})"
            )
        if direction is not None or threshold is not None:
            raise ValueError(
                f"objective for '{name}': 'expect' cannot be combined with "
                "'direction' or 'threshold'"
            )
        return {"expect": expect}
    if direction == "minimize":
        if threshold is None:
            # no bar to re-decide against; treat as absent (evaluator default stands)
            return None
        return {"direction": "minimize", "threshold": float(threshold)}
    if direction == "maximize":
        if threshold is None:
            # no bar to re-decide against; treat as absent (evaluator default stands)
            return None
        return {"direction": "maximize", "threshold": float(threshold)}
    raise ValueError(
        f"objective for '{name}': 'direction' must be 'maximize' or 'minimize' "
        f"(got {direction!r})"
    )


def _apply_objective(metric, objective):
    """Return the objective-adjusted pass verdict for a non-error metric."""
    if "expect" in objective:
        return bool(metric.score) == objective["expect"]
    if objective["direction"] == "minimize":
        return metric.score <= objective["threshold"]
    return metric.score >= objective["threshold"]


def _extract(case: Case, target_fn: Optional[Callable]):
    """Return (case_id, expected, actual, config, per_case_target_fn)."""
    if isinstance(case, tuple):
        expected, actual = case[0], (case[1] if len(case) > 1 else None)
        return str(id(case)), expected, actual, {}, None
    case_id = case.get("id") or f"case-{id(case)}"
    expected = case.get("expected")
    actual = case.get("actual")
    config = case.get("config") or {}
    per_fn = case.get("target_fn")
    return case_id, expected, actual, config, per_fn


def _merge_config(default_config: Dict[str, Any], case_config: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge per-case config over the global config.

    Top-level keys are merged key-by-key, so a per-case override of one
    evaluator's settings keeps the global objective for that evaluator
    (rather than replacing the whole top-level entry).
    """
    merged = dict(default_config)
    for key, value in (case_config or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            current = dict(merged[key])
            current.update(value)
            merged[key] = current
        else:
            merged[key] = value
    return merged


def evaluate(
    cases: List[Case],
    evaluators: List[str],
    config: Optional[Dict[str, Any]] = None,
    target_fn: Optional[Callable] = None,
) -> EvalSummary:
    """Run named evaluators over each case and aggregate metrics.

    A per-case or top-level ``target_fn`` produces ``actual`` when the case
    does not already carry one. Evaluator failures become ``error`` results.
    """
    default_config = config or {}
    case_results: List[CaseResult] = []

    # Validate objective config for every case up front so an invalid objective
    # rejects the run before any target_fn or evaluator executes (fail-fast),
    # regardless of which case carries it.
    pre_resolved = []
    for case in cases:
        _, _, _, case_config, _ = _extract(case, target_fn)
        merged = _merge_config(default_config, case_config)
        pre_resolved.append(
            {
                name: _parse_objective(name, merged.get(name) or {})
                for name in evaluators
            }
        )

    for case, objective_by_name in zip(cases, pre_resolved):
        case_id, expected, actual, case_config, per_fn = _extract(case, target_fn)
        merged = _merge_config(default_config, case_config)
        if expected is None:
            expected = merged.get("expected")
        resolver = per_fn or target_fn
        if actual is None and resolver is not None:
            try:
                actual = resolver(case)
            except Exception as exc:  # noqa: BLE001
                case_results.append(
                    CaseResult(case_id, "error", {}, {"target_fn": str(exc)})
                )
                continue
        metrics: Dict[str, EvalMetric] = {}
        details: Dict[str, Any] = {}
        failed, errored = False, False
        for name in evaluators:
            eval_config = merged.get(name) or {}
            try:
                metric = get_evaluator(name)(actual, expected, config=eval_config)
                objective = objective_by_name.get(name)
                if objective is not None and "error" not in metric.meta:
                    metric = EvalMetric(metric.score, _apply_objective(metric, objective), metric.meta)
                metrics[name] = metric
                if "error" in metric.meta:
                    errored = True
                    details[name] = metric.meta
                elif not metric.passed:
                    failed = True
                    details[name] = metric.meta
            except Exception as exc:  # noqa: BLE001
                errored = True
                metrics[name] = EvalMetric(0.0, False, {"error": str(exc)})
                details[name] = {"error": str(exc)}
        status = "error" if errored else ("fail" if failed else "pass")
        case_results.append(CaseResult(case_id, status, metrics, details))

    total = len(case_results)
    passed = sum(1 for c in case_results if c.status == "pass")
    failed = sum(1 for c in case_results if c.status == "fail")
    errors = sum(1 for c in case_results if c.status == "error")
    pass_rate = (passed / total) if total else 1.0
    return EvalSummary(
        total, passed, failed, errors, pass_rate,
        cases=case_results,
    )
