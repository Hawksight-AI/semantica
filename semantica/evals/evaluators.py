"""Generic (non-decision) evaluators for the evals module.

Each evaluator takes ``(actual, expected, config=None, **kwargs)`` and returns
an ``EvalMetric``. Config uses ``min``/``max`` bounds where relevant.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from .registry import register
from .types import EvalMetric


def _default_config(config):
    return config or {}


@register("exact_match")
def exact_match(actual, expected, config=None, **kwargs):
    """Score 1.0 if ``actual`` equals ``expected`` (scalar or list)."""
    matched = actual == expected
    return EvalMetric(
        score=1.0 if matched else 0.0,
        passed=matched,
        meta={} if matched else {"reason": f"expected {expected!r}, got {actual!r}"},
    )


@register("regex_match")
def regex_match(actual, expected, config=None, **kwargs):
    """Score 1.0 if string ``actual`` matches regex ``expected``."""
    import re
    try:
        matched = re.search(expected, actual) is not None
        return EvalMetric(
            score=1.0 if matched else 0.0,
            passed=matched,
            meta={} if matched else {"reason": f"'{actual}' does not match {expected}"},
        )
    except re.error as exc:
        return EvalMetric(0.0, False, {"error": str(exc)})


@register("numeric_range")
def numeric_range(actual, expected=None, config=None, **kwargs):
    """Score 1.0 if number ``actual`` is within inclusive ``[min, max]``."""
    cfg = _default_config(config)
    lo, hi = cfg.get("min"), cfg.get("max")
    passed = lo is not None and hi is not None and lo <= actual <= hi
    return EvalMetric(
        score=1.0 if passed else 0.0,
        passed=passed,
        meta={} if passed else {"reason": f"{actual} not in [{lo}, {hi}]"},
    )


@register("temporal_range")
def temporal_range(actual, expected=None, config=None, **kwargs):
    """Score 1.0 if datetime ``actual`` is within inclusive ISO-datetime window."""
    cfg = _default_config(config)
    try:
        stamp = datetime.fromisoformat(actual)
        lo = datetime.fromisoformat(cfg["min"])
        hi = datetime.fromisoformat(cfg["max"])
        passed = lo <= stamp <= hi
        return EvalMetric(
            score=1.0 if passed else 0.0,
            passed=passed,
            meta={} if passed else {"reason": f"{actual} not in [{cfg['min']}, {cfg['max']}]"},
        )
    except (KeyError, TypeError, ValueError) as exc:
        return EvalMetric(0.0, False, {"error": str(exc)})


@register("length_range")
def length_range(actual, expected=None, config=None, **kwargs):
    """Score 1.0 if length of ``actual`` is within inclusive ``[min, max]``."""
    cfg = _default_config(config)
    size = len(actual)
    lo = cfg.get("min", 0)
    hi = cfg.get("max")
    passed = hi is not None and lo <= size <= hi
    return EvalMetric(
        score=1.0 if passed else 0.0,
        passed=passed,
        meta={} if passed else {"reason": f"length {size} not in [{lo}, {hi}]"},
    )