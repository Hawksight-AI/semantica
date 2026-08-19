"""Generic (non-decision) evaluators for the evals module.

Each evaluator takes ``(actual, expected, config=None, **kwargs)`` and returns
an ``EvalMetric``. Config uses ``min``/``max`` bounds where relevant.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

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


@register("keyword_check")
def keyword_check(actual, expected=None, config=None, **kwargs):
    """Score 1.0 if all required terms appear in ``actual`` (word-boundary matching)."""
    cfg = _default_config(config)
    required = cfg.get("required") or (expected or [])
    import re
    tokens = set(re.findall(r"\w+", str(actual).lower()))
    missing = [term for term in required if str(term).lower() not in tokens]
    passed = not missing
    return EvalMetric(
        score=1.0 if passed else 0.0,
        passed=passed,
        meta={} if passed else {"missing": missing},
    )


def _levenshtein(a: str, b: str) -> int:
    """Classic Levenshtein edit distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@register("levenshtein")
def levenshtein(actual, expected, config=None, **kwargs):
    """Score normalized similarity (1 - distance/max_len) vs ``threshold`` (default 0.8)."""
    cfg = _default_config(config)
    threshold = cfg.get("threshold", 0.8)
    a, b = str(actual), str(expected)
    max_len = max(len(a), len(b))
    similarity = 1.0 if max_len == 0 else 1.0 - _levenshtein(a, b) / max_len
    passed = similarity >= threshold
    return EvalMetric(
        score=similarity,
        passed=passed,
        meta={"similarity": similarity},
    )


def _tokenize(text: str) -> List[str]:
    import re
    return re.findall(r"\w+", str(text).lower())


@register("rouge")
def rouge(actual, expected, config=None, **kwargs):
    """ROUGE-1 precision/recall/F1 over tokens; pass on F1 >= ``threshold`` (default 0.0)."""
    cfg = _default_config(config)
    threshold = cfg.get("threshold", 0.0)
    hyp, ref = _tokenize(actual), _tokenize(expected)
    from collections import Counter
    hyp_c, ref_c = Counter(hyp), Counter(ref)
    overlap = sum((hyp_c & ref_c).values())
    precision = overlap / len(hyp) if hyp else 0.0
    recall = overlap / len(ref) if ref else 0.0
    f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    passed = f1 > 0 and f1 >= threshold
    return EvalMetric(
        score=f1,
        passed=passed,
        meta={"precision": precision, "recall": recall, "f1": f1},
    )


@register("llm_as_judge")
def llm_as_judge(actual, expected, config=None, **kwargs):
    """Score 1.0 when a caller-supplied ``judge_fn(actual, expected) -> bool`` passes.

    The judge resolver stays lazy: no LLM backend is imported unless the caller
    provides one in config.
    """
    cfg = _default_config(config)
    judge_fn = cfg.get("judge_fn")
    if judge_fn is None:
        return EvalMetric(
            0.0, False, {"error": "config['judge_fn'] required (callable(actual, expected) -> bool)"}
        )
    try:
        verdict = bool(judge_fn(actual, expected))
        return EvalMetric(score=1.0 if verdict else 0.0, passed=verdict)
    except Exception as exc:  # noqa: BLE001
        return EvalMetric(0.0, False, {"error": str(exc)})
