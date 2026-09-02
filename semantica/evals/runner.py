"""Evaluation runner: orchestrates evaluators over a list of cases."""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .registry import get_evaluator
from .types import CaseResult, EvalMetric, EvalSummary

Case = Union[Dict[str, Any], Tuple[Any, Any]]


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

    for case in cases:
        case_id, expected, actual, case_config, per_fn = _extract(case, target_fn)
        resolver = per_fn or target_fn
        if actual is None and resolver is not None:
            try:
                actual = resolver(case)
            except Exception as exc:  # noqa: BLE001
                case_results.append(
                    CaseResult(case_id, "error", {}, {"target_fn": str(exc)})
                )
                continue
        merged = dict(default_config)
        merged.update(case_config)
        if expected is None:
            expected = merged.get("expected")
        metrics: Dict[str, EvalMetric] = {}
        details: Dict[str, Any] = {}
        failed, errored = False, False
        for name in evaluators:
            eval_config = merged.get(name) or {}
            try:
                metric = get_evaluator(name)(actual, expected, config=eval_config)
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
