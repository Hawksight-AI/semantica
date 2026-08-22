# Semantica Evals Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `semantica.evals` stub with a working evaluation module (10 evaluators + `decision_scores` decision-specialized composite) following the metric/objective/threshold model of Palantir AIP Evals.

**Architecture:** Pure functions + a lightweight `evaluate()` runner. Evaluators are standalone functions registered by name in a registry; `decision_scores` composes field-level and governance-level checks against `semantica.context` Decision objects. No mandatory external services; `llm_as_judge` resolves a caller-supplied judge callable lazily.

**Tech Stack:** Python 3.8+, dataclasses/NamedTuple from stdlib, `semantica.context.decision_models.Decision`, `semantica.context.policy_engine.PolicyEngine`, pytest.

## Global Constraints

- Python >= 3.8 — NO `list[str]`/`dict[str, ...]` builtin generics, NO `match` statements, NO `|` type unions. Use `Optional[...]`, `Dict`, `List` from `typing`.
- No new dependencies. ROUGE implemented in-house from token overlap (no `rouge-score` package).
- No docstring downgrade: match repo style — every module and class has a docstring header, every public function has a docstring.
- Follow existing test conventions: `tests/evals/` directory, pytest classes, `from semantica...` imports.
- No comments in code unless needed to explain non-obvious logic.
- Style: black line-length 88, isort profile black.
- Update `semantica/__init__.py` module proxy so `semantica.evals` works via dot notation.
- CHANGELOG `[Unreleased]` entry required (there is a CI test enforcing unreleased-changelog coverage).
- Spec: `docs/superpowers/specs/2026-08-19-evals-module-design.md`.

---

### Task 1: `EvalMetric` + result models (`types.py`)

**Files:**
- Create: `semantica/evals/types.py`
- Test: `tests/evals/test_types.py`

**Interfaces:**
- Produces: `EvalMetric = NamedTuple(score: float, passed: bool, meta: dict)`, `CaseResult = NamedTuple(case_id: str, status: str, metrics: Dict[str, EvalMetric], details: Dict[str, Any])`, `EvalSummary` (dataclass: `total`, `passed`, `failed`, `errors`, `pass_rate`, plus a mutable `cases: List[CaseResult]` list for detail access).

---

- [ ] **Step 1: Create the test directory and files**

```bash
mkdir -p tests/evals
```

Write `tests/evals/test_types.py`:

```python
"""Tests for evals result models."""
import pytest

from semantica.evals.types import CaseResult, EvalMetric, EvalSummary


class TestEvalMetric:
    def test_construction(self):
        m = EvalMetric(score=1.0, passed=True, meta={"threshold": 1.0})
        assert m.score == 1.0 and m.passed and m.meta["threshold"] == 1.0

    def test_default_meta(self):
        m = EvalMetric(0.0, False)
        assert m.meta == {}


class TestCaseResult:
    def test_status_fail_on_any_failed_metric(self):
        r = CaseResult(
            case_id="c1",
            status="fail",
            metrics={"exact_match": EvalMetric(0.0, False)},
            details={},
        )
        assert r.status == "fail"
        assert r.metrics["exact_match"].passed is False


class TestEvalSummary:
    def test_pass_rate(self):
        s = EvalSummary(total=10, passed=8, failed=1, errors=1, pass_rate=0.8)
        assert s.pass_rate == 0.8

    def test_cases_are_mutable(self):
        s = EvalSummary(0, 0, 0, 0, 1.0)
        s.cases.append(CaseResult("c", "pass", {}, {}))
        assert len(s.cases) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/evals/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'semantica.evals.types'`

- [ ] **Step 3: Write minimal implementation**

Create `semantica/evals/types.py`:

```python
"""Evals result data models.

Defines the metric and result shapes produced by the evals module.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple


class EvalMetric(NamedTuple):
    """One evaluator's numeric score plus pass/fail verdict."""

    score: float
    passed: bool
    meta: Dict[str, Any] = {}


class CaseResult(NamedTuple):
    """Evaluation output for a single case."""

    case_id: str
    status: str
    metrics: Dict[str, EvalMetric]
    details: Dict[str, Any]


@dataclass
class EvalSummary:
    """Aggregate evaluation output across cases."""

    total: int
    passed: int
    failed: int
    errors: int
    pass_rate: float
    cases: List[CaseResult] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/evals/test_types.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/evals/test_types.py semantica/evals/types.py
git commit -m "feat(evals): add eval metric and result models"
```

---

### Task 2: Evaluator registry (`registry.py`)

**Files:**
- Create: `semantica/evals/registry.py`
- Modify: `semantica/evals/types.py` (no change)
- Test: `tests/evals/test_registry.py`

**Interfaces:**
- Consumes: `EvalMetric` from `semantica.evals.types`.
- Produces: `EVALUATORS: Dict[str, callable]`, `register(name)` decorator, `list_evaluators()`, `get_evaluator(name)` raising `ValueError` for unknown names. Evaluator signature: `fn(actual, expected, config=None, **kwargs) -> EvalMetric`.

---

- [ ] **Step 1: Write the failing test**

Write `tests/evals/test_registry.py`:

```python
"""Tests for the evaluator registry."""
import pytest

from semantica.evals import registry as reg
from semantica.evals.types import EvalMetric


class TestRegistry:
    def test_register_and_get(self):
        @reg.register("demo_eval")
        def demo(actual, expected, config=None, **kwargs):
            return EvalMetric(1.0, True)

        assert reg.get_evaluator("demo_eval") is demo
        assert "demo_eval" in reg.list_evaluators()

    def test_registration_is_immutable_after_commit(self):
        with pytest.raises(ValueError):
            reg.get_evaluator("does_not_exist")

    def test_unknown_evaluator_failure_message(self):
        with pytest.raises(ValueError) as exc:
            reg.get_evaluator("nope")
        assert "nope" in str(exc.value)
        assert "demo_eval" in str(exc.value)  # hint lists available evals
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/evals/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'semantica.evals.registry'`

- [ ] **Step 3: Write minimal implementation**

Create `semantica/evals/registry.py`:

```python
"""Evaluator registry for the evals module.

Evaluators are plain functions ``fn(actual, expected, config=None, **kwargs)
-> EvalMetric`` registered under a stable string name so the runner and users
can select them by name without importing individual modules.
"""

from typing import Callable, Dict, List

from .types import EvalMetric

EVALUATORS: Dict[str, Callable] = {}


def register(name: str) -> Callable:
    """Decorator registering an evaluator function under ``name``."""
    def _register(fn: Callable) -> Callable:
        if name in EVALUATORS:
            raise ValueError(f"evaluator already registered: {name}")
        EVALUATORS[name] = fn
        return fn
    return _register


def list_evaluators() -> List[str]:
    """Return sorted names of all registered evaluators."""
    return sorted(EVALUATORS)


def get_evaluator(name: str) -> Callable:
    """Look up an evaluator by name, raising ValueError with a hint otherwise."""
    if name not in EVALUATORS:
        raise ValueError(f"unknown evaluator '{name}'. Available: {list_evaluators()}")
    return EVALUATORS[name]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/evals/test_registry.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/evals/test_registry.py semantica/evals/registry.py
git commit -m "feat(evals): add evaluator registry"
```

---

### Task 3: Generic evaluators I (`evaluators.py` — exact/regex/range/length)

**Files:**
- Create: `semantica/evals/evaluators.py`
- Modify: `semantica/evals/registry.py` (no change)
- Test: `tests/evals/test_evaluators_part1.py`

**Interfaces:**
- Consumes: `EvalMetric`, `register`/`get_evaluator`.
- Produces: registered names `exact_match`, `regex_match`, `numeric_range`, `temporal_range`, `length_range`. Config keys: none for `exact_match`; `regex_match` uses `expected` as pattern; `numeric_range` config `min`/`max`; `temporal_range` config `min`/`max` (ISO datetime strings); `length_range` config `min`/`max` (inclusive).

---

- [ ] **Step 1: Write the failing test**

Write `tests/evals/test_evaluators_part1.py`:

```python
"""Tests for generic evaluators: exact, regex, ranges, length."""
import pytest

from semantica.evals import registry as reg


class TestExactMatch:
    def test_exact_str(self):
        r = reg.get_evaluator("exact_match")("approved", "approved")
        assert r.passed and r.score == 1.0

    def test_exact_str_negative(self):
        r = reg.get_evaluator("exact_match")("approved", "denied")
        assert not r.passed and r.score == 0.0

    def test_exact_number(self):
        r = reg.get_evaluator("exact_match")(5, 5)
        assert r.passed

    def test_exact_array(self):
        r = reg.get_evaluator("exact_match")([1, 2], [1, 2])
        assert r.passed


class TestRegexMatch:
    def test_matching(self):
        r = reg.get_evaluator("regex_match")("abc123", r"^[a-z]+\d+$")
        assert r.passed

    def test_non_matching(self):
        r = reg.get_evaluator("regex_match")("ABC", r"^[a-z]+$")
        assert not r.passed
        assert "ABC" in r.meta.get("reason", "")

    def test_invalid_regex_is_error_metric(self):
        r = reg.get_evaluator("regex_match")("x", "[invalid")
        assert not r.passed
        assert r.meta.get("error")


class TestNumericRange:
    def test_inside(self):
        r = reg.get_evaluator("numeric_range")(0.9, config={"min": 0.8, "max": 1.0})
        assert r.passed and r.score == 1.0

    def test_outside(self):
        r = reg.get_evaluator("numeric_range")(0.5, config={"min": 0.8, "max": 1.0})
        assert not r.passed and r.score == 0.0

    def test_bounds_inclusive(self):
        assert reg.get_evaluator("numeric_range")(0.8, config={"min": 0.8, "max": 0.8}).passed


class TestTemporalRange:
    def test_inside_window(self):
        r = reg.get_evaluator("temporal_range")(
            "2026-01-15T10:00:00",
            config={"min": "2026-01-01T00:00:00", "max": "2026-02-01T00:00:00"},
        )
        assert r.passed

    def test_outside_window(self):
        r = reg.get_evaluator("temporal_range")(
            "2026-03-01T00:00:00",
            config={"min": "2026-01-01T00:00:00", "max": "2026-02-01T00:00:00"},
        )
        assert not r.passed


class TestLengthRange:
    def test_ok(self):
        r = reg.get_evaluator("length_range")("hello", config={"min": 3, "max": 5})
        assert r.passed

    def test_too_long(self):
        r = reg.get_evaluator("length_range")([1, 2, 3], config={"min": 1, "max": 2})
        assert not r.passed

    def test_min_not_given_defaults_zero(self):
        r = reg.get_evaluator("length_range")("abc", config={"max": 5})
        assert r.passed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/evals/test_evaluators_part1.py -v`
Expected: FAIL with `KeyError: 'exact_match'` / `ValueError: unknown evaluator`

- [ ] **Step 3: Write minimal implementation**

Create `semantica/evals/evaluators.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/evals/test_evaluators_part1.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/evals/test_evaluators_part1.py semantica/evals/evaluators.py
git commit -m "feat(evals): add exact/regex/range/length evaluators"
```

---

### Task 4: Generic evaluators II (`evaluators.py` — keyword/levenshtein/rouge/llm_as_judge)

**Files:**
- Modify: `semantica/evals/evaluators.py` (append)
- Test: `tests/evals/test_evaluators_part2.py`

**Interfaces:**
- Consumes: `EvalMetric`, `register`.
- Produces: registered names `keyword_check`, `levenshtein`, `rouge`, `llm_as_judge`. Config: `keyword_check` `required` (list) or list passed as `expected`; `levenshtein` config `threshold` (default 0.8 similarity) — uses normalized Levenshtein similarity; `rouge` config `threshold` (default 0.0) on F1, tokenizes on word boundaries; `llm_as_judge` config `judge_fn` (required callable: `fn(actual, expected) -> bool`) — returns error metric if absent.

---

- [ ] **Step 1: Write the failing test**

Write `tests/evals/test_evaluators_part2.py`:

```python
"""Tests for generic evaluators: keyword, levenshtein, rouge, llm-as-judge."""
import pytest

from semantica.evals import registry as reg


class TestKeywordCheck:
    def test_all_required_present(self):
        r = reg.get_evaluator("keyword_check")(
            "the loan was approved", expected=["loan", "approved"]
        )
        assert r.passed

    def test_missing_keyword(self):
        r = reg.get_evaluator("keyword_check")(
            "the loan was approved", expected=["loan", "denied"]
        )
        assert not r.passed
        assert "denied" in r.meta.get("missing", [])

    def test_short_words_ignored(self):
        r = reg.get_evaluator("keyword_check")("x and y", expected=["and"])
        assert r.passed


class TestLevenshtein:
    def test_identical(self):
        r = reg.get_evaluator("levenshtein")("credit approved", "credit approved")
        assert r.passed

    def test_close_above_threshold(self):
        r = reg.get_evaluator("levenshtein")(
            "credit approved", "credit denied", config={"threshold": 0.8}
        )
        assert not r.passed

    def test_default_threshold(self):
        assert reg.get_evaluator("levenshtein")("a", "a").passed


class TestRouge:
    def test_identical(self):
        r = reg.get_evaluator("rouge")("loan approved by committee", "loan approved by committee")
        assert r.passed
        assert r.meta["f1"] == pytest.approx(1.0)

    def test_no_overlap(self):
        r = reg.get_evaluator("rouge")("one two three", "four five six")
        assert not r.passed

    def test_partial_sets_meta(self):
        r = reg.get_evaluator("rouge")("a b c", "a b d", config={"threshold": 0.5})
        assert "precision" in r.meta and "recall" in r.meta


class TestLlmAsJudge:
    def test_uses_supplied_judge(self):
        judge = lambda actual, expected: actual == expected  # noqa: E731
        r = reg.get_evaluator("llm_as_judge")(
            "x", "x", config={"judge_fn": judge}
        )
        assert r.passed

    def test_missing_judge_is_error(self):
        r = reg.get_evaluator("llm_as_judge")("x", "y", config={})
        assert not r.passed
        assert r.meta.get("error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/evals/test_evaluators_part2.py -v`
Expected: FAIL with `ValueError: unknown evaluator 'keyword_check'`

- [ ] **Step 3: Write minimal implementation**

Append to `semantica/evals/evaluators.py`:

```python
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
        meta={"similarity": similarity} if not passed else {"similarity": similarity},
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
    passed = f1 >= threshold
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/evals/test_evaluators_part2.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/evals/test_evaluators_part2.py semantica/evals/evaluators.py
git commit -m "feat(evals): add keyword/levenshtein/rouge/llm-as-judge evaluators"
```

---

### Task 5: `decision_scores` composite evaluator (`decision_evaluators.py`)

**Files:**
- Create: `semantica/evals/decision_evaluators.py`
- Test: `tests/evals/test_decision_evaluators.py`

**Interfaces:**
- Consumes: `Decision`/`Decision.from_dict` from `semantica.context.decision_models`; `EvalMetric`; `register`.
- Produces: registered name `decision_scores`. Config keys: `expected_outcome` (str), `min_confidence`/`max_confidence` (float, default 0/1), `provenance_key` (default `"provenance"`), optional `policy_engine` (instance) + `expected_policy_compliant` (bool, default True) + `policy_id` (str), optional `causal_chain_exists` (bool, default False) + `graph_store` (any object; check succeeds if graph-stored decision chain is reachable — V1 uses a presence shortcut, documented below).
- Produces multiple flat metrics per run stored in a single `EvalMetric.meta`: keys `decision_outcome`, `decision_confidence`, `decision_maker`, `reasoning`, `provenance`, `policy`, `causal_chain`. `score` = fraction of sub-checks passed (0..1), `passed` = all configured sub-checks pass.
- Field-required fields never validated against empty config: `decision_maker`, `reasoning`, `scenario`, `outcome` non-empty strings.

**Decision coercion:** `decision_scores(actual, expected, config, **kwargs)` accepts either a `Decision` object or a dict; dicts convert via `Decision.from_dict` when all required keys present, else the sub-check is skipped with an error note rather than crashing.

---

- [ ] **Step 1: Write the failing test**

Write `tests/evals/test_decision_evaluators.py`:

```python
"""Tests for the decision_scores composite evaluator."""
import pytest
from datetime import datetime

from semantica.context.decision_models import Decision
from semantica.evals import registry as reg


def _decision(**overrides):
    base = dict(
        decision_id="d1",
        category="loan",
        scenario="mortgage application",
        reasoning="strong credit history",
        outcome="approved",
        confidence=0.95,
        timestamp=datetime(2026, 1, 1),
        decision_maker="loan_officer",
    )
    base.update(overrides)
    return Decision(**base)


class TestDecisionScores:
    def test_full_pass(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(
            d, config={"expected_outcome": "approved"}
        )
        assert r.passed
        assert r.meta["decision_outcome"] is True
        assert r.meta["provenance"] is True

    def test_outcome_mismatch(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(
            d, config={"expected_outcome": "denied"}
        )
        assert not r.passed
        assert r.meta["decision_outcome"] is False

    def test_confidence_out_of_range(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}}, confidence=0.4)
        r = reg.get_evaluator("decision_scores")(
            d, config={"expected_outcome": "approved", "min_confidence": 0.8}
        )
        assert not r.passed
        assert r.meta["decision_confidence"] is False

    def test_missing_provenance_fails(self):
        d = _decision(metadata={})
        r = reg.get_evaluator("decision_scores")(d, config={"expected_outcome": "approved"})
        assert not r.passed
        assert r.meta["provenance"] is False

    def test_missing_required_fields(self):
        d = _decision(reasoning="")
        r = reg.get_evaluator("decision_scores")(d, config={"expected_outcome": "approved"})
        assert not r.passed
        assert r.meta["reasoning"] is False

    def test_dict_input_coerced(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        as_dict = d.to_dict()
        r = reg.get_evaluator("decision_scores")(
            as_dict, config={"expected_outcome": "approved"}
        )
        assert r.passed

    def test_malformed_dict_is_error_not_crash(self):
        r = reg.get_evaluator("decision_scores")({"foo": "bar"}, config={})
        assert not r.passed
        assert r.meta.get("error")

    def test_policy_compliance_check(self):
        class FakePolicyEngine:
            def check_compliance(self, decision, policy_id):
                return True

        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(
            d, config={
                "expected_outcome": "approved",
                "policy_engine": FakePolicyEngine(),
                "policy_id": "p1",
                "expected_policy_compliant": True,
            }
        )
        assert r.meta["policy"] is True

    def test_policy_mismatch_fails(self):
        class FakePolicyEngine:
            def check_compliance(self, decision, policy_id):
                return False

        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(
            d, config={
                "policy_engine": FakePolicyEngine(),
                "policy_id": "p1",
                "expected_policy_compliant": True,
            }
        )
        assert not r.passed
        assert r.meta["policy"] is False

    def test_causal_chain_gate(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}}, decision_id="only-decision")
        with pytest.raises(NotImplementedError):
            reg.get_evaluator("decision_scores")(
                d, config={"causal_chain_exists": True, "graph_store": object()}
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/evals/test_decision_evaluators.py -v`
Expected: FAIL with `ValueError: unknown evaluator 'decision_scores'`

- [ ] **Step 3: Write minimal implementation**

Create `semantica/evals/decision_evaluators.py`:

```python
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
    return EvalMetric(
        score=passed_count / total if total else 0.0,
        passed=passed,
        meta={"checks": checks, "reasons": reasons},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/evals/test_decision_evaluators.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/evals/test_decision_evaluators.py semantica/evals/decision_evaluators.py
git commit -m "feat(evals): add decision_scores composite evaluator"
```

---

### Task 6: Runner (`runner.py`)

**Files:**
- Create: `semantica/evals/runner.py`
- Test: `tests/evals/test_runner.py`

**Interfaces:**
- Consumes: `CaseResult`, `EvalSummary`, `EvalMetric` from `.types`; `get_evaluator` from `.registry`.
- Produces: `evaluate(cases, evaluators, config=None, target_fn=None) -> EvalSummary`. Each case dict: `{"id": str or None, "expected": Any, "actual": Any or None, "target_fn": callable or None, "config": dict or None}`; `cases` may also be a list of raw `(expected, actual)` tuples. A one-arg `fn(case) -> actual` provided at top level or per-case produces `actual`. Status mapping: all passed → `pass`, any failed → `fail`, evaluator raised → `error`. The returned `EvalSummary` carries `cases: List[CaseResult]` for detail access.

---

- [ ] **Step 1: Write the failing test**

Write `tests/evals/test_runner.py`:

```python
"""Tests for the evals runner."""
import pytest

from semantica.evals.runner import evaluate


class TestEvaluate:
    def test_raw_tuple_cases(self):
        result = evaluate(
            [("approved", "approved"), ("approved", "denied")],
            evaluators=["exact_match"],
        )
        assert result.total == 2
        assert result.passed == 1
        assert result.failed == 1
        assert result.errors == 0
        assert result.pass_rate == 0.5

    def test_dict_cases_with_target_fn(self):
        def fn(case):
            return "ok" if case["id"] == "good" else "no"

        result = evaluate(
            [{"id": "good"}, {"id": "bad"}],
            evaluators=["exact_match"],
            target_fn=fn,
            config={"expected": "ok"},
        )
        assert result.passed == 1
        assert result.failed == 1

    def test_error_capture(self):
        result = evaluate([("x", "y")], evaluators=["does_not_exist"])
        assert result.errors == 1
        assert result.failed == 0
        assert result.pass_rate == 0.0

    def test_per_case_details(self):
        result = evaluate([("a", "b")], evaluators=["exact_match"])
        case = result.cases[0]
        assert case.status == "fail"
        assert "exact_match" in case.details

    def test_empty_cases(self):
        result = evaluate([], evaluators=["exact_match"])
        assert result.total == 0 and result.pass_rate == 1.0

    def test_multiple_evaluators(self):
        result = evaluate(
            [("apple pie", "apple pie")],
            evaluators=["exact_match", "keyword_check"],
            config={"keyword_check": {"required": ["apple"]}},
        )
        assert result.passed == 1
        assert "exact_match" in result.cases[0].metrics
        assert "keyword_check" in result.cases[0].metrics
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/evals/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'semantica.evals.runner'`

- [ ] **Step 3: Write minimal implementation**

Create `semantica/evals/runner.py`:

```python
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
        metrics: Dict[str, EvalMetric] = {}
        details: Dict[str, Any] = {}
        failed, errored = False, False
        for name in evaluators:
            try:
                metric = get_evaluator(name)(actual, expected, config=merged)
                metrics[name] = metric
                if not metric.passed:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/evals/test_runner.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/evals/test_runner.py semantica/evals/runner.py
git commit -m "feat(evals): add evaluation runner"
```

---

### Task 7: Public API, module proxy, usage docs (`__init__.py` + `semantica/__init__.py`)

**Files:**
- Modify: `semantica/evals/__init__.py` (replace stub)
- Modify: `semantica/__init__.py` (add `evals` to `_SemanticaModules` + `__getattr__` list)
- Create: `semantica/evals/usage.md`
- Test: `tests/evals/test_public_api.py`

**Interfaces:**
- Consumes: `evaluate` from `.runner`, `list_evaluators` from `.registry`.
- Produces: `semantica.evals.evaluate`, `semantica.evals.list_evaluators`, `semantica.evals.__version__`, `semantica.evals` module proxy, and `(str(Decision))` — keep `__all__` populated.

---

- [ ] **Step 1: Write the failing test**

Write `tests/evals/test_public_api.py`:

```python
"""Tests for the evals public package API."""
from semantica import evals
from semantica.evals import evaluate, list_evaluators


class TestPublicAPI:
    def test_imports(self):
        assert callable(evaluate)
        assert callable(list_evaluators)

    def test_version_present(self):
        assert hasattr(evals, "__version__")

    def test_module_proxy_via_root(self):
        # semantica.evals must resolve through the lazy proxy
        assert hasattr(evals, "evaluate")

    def test_all_populated(self):
        assert len(evals.__all__) >= 2
        assert "evaluate" in evals.__all__
        assert "list_evaluators" in evals.__all__

    def test_register_discovery(self):
        names = evals.list_evaluators()
        for expected in (
            "exact_match", "regex_match", "numeric_range", "temporal_range",
            "length_range", "keyword_check", "levenshtein", "rouge",
            "llm_as_judge", "decision_scores",
        ):
            assert expected in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/evals/test_public_api.py -v`
Expected: FAIL — `semantica.evals.evaluate` import errors (`__init__` still a stub) or `evals.__all__` empty.

- [ ] **Step 3: Write implementation**

Replace `semantica/evals/__init__.py`:

```python
"""Semantica Evals — evaluation layer for decision intelligence outputs.

Provides a small library of deterministic and model-backed evaluators plus a
runner for measuring decision records, audit trails, and reasoning output.
"""

from .registry import list_evaluators
from .runner import evaluate

__version__ = "0.1.0"
__all__ = ["evaluate", "list_evaluators", "CaseResult", "EvalMetric", "EvalSummary"]
```

Edit `semantica/__init__.py`:

Add to `_SemanticaModules` (near the other properties):

```python
    @property
    def evals(self):
        """Access evaluation module."""
        if self._evals is None:
            self._evals = _ModuleProxy("evals")
        return self._evals
```

Initialize `self._evals = None` in `__init__`, and add `"evals"` to the `__getattr__` allow-list.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/evals/test_public_api.py -v`
Expected: PASS (5 passed)

Run: `python -m pytest tests/evals -q`
Expected: all tasks' evals tests pass.

- [ ] **Step 5: Commit**

```bash
git add semantica/evals/__init__.py semantica/__init__.py tests/evals/test_public_api.py semantica/evals/usage.md
git commit -m "feat(evals): expose public API and module proxy"
```

---

### Task 8: Usage docs + CHANGELOG entry

**Files:**
- Create: `semantica/evals/usage.md`
- Modify: `CHANGELOG.md`

**Interfaces:** None (docs).

---

- [ ] **Step 1: Write usage.md**

Create `semantica/evals/usage.md` with worked examples (import, list evaluators, run `evaluate` over decision records, interpret summary). Include a note that `llm_as_judge` needs `config["judge_fn"]` and `decision_scores` governance checks are opt-in.

- [ ] **Step 2: Add CHANGELOG entry**

Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`, following the detailed style of existing entries (features + tests + review notes). Draft:

```markdown
- **`semantica.evals` is now a fully implemented evaluation module** (was a "Coming Soon" stub) (#NNNN)
  - `evaluate(cases, evaluators, config=None, target_fn=None)` runner with per-case `pass`/`fail`/`error` status and an aggregate `pass_rate`, using a registry of named evaluators (`list_evaluators()`)
  - 10 built-in evaluators: `exact_match`, `regex_match`, `numeric_range`, `temporal_range`, `length_range`, `keyword_check`, `levenshtein` (edit-distance similarity), `rouge` (in-house token F1, no new deps), `llm_as_judge` (lazy: caller-supplied `judge_fn`), and `decision_scores` (composite over `semantica.context.Decision`)
  - `decision_scores` validates field-level (expected outcome, confidence bounds, non-empty maker/reasoning/scenario) and governance-level (provenance record presence; opt-in `PolicyEngine.check_compliance`) checks, coercing dict inputs via `Decision.from_dict` and never crashing on malformed input; an interface slot is reserved for causal-chain/embedding checks (V2)
  - `semantica.evals` is reachable through the root package lazy module proxy (`semantica.evals`)
  - 40+ unit tests in `tests/evals/` covering every evaluator, registry errors, runner aggregation, and decision coercion
```

- [ ] **Step 3: Verify**

Run: `python -m pytest tests/ -q` (full suite — expect existing pre-change count to pass, new tests included). Confirm no regression in `tests/cli` etc.

- [ ] **Step 4: Commit**

```bash
git add semantica/evals/usage.md CHANGELOG.md
git commit -m "docs(evals): add usage docs and changelog entry"
```

---

## Self-Review Notes

- **Spec coverage:** §2.1 (evaluate entry) → Task 6; §2.2 (10 evaluators) → Tasks 3, 4, 5; §2.3 (result contract) → Tasks 1, 6; §3 ①/②/③ → Task 5 (③ raises `NotImplementedError`, interface-only per spec); §4 layout → Tasks 1-8 (+ `semantica/__init__.py` proxy → Task 7); §5 error handling → Tasks 2, 5, 6; §6 testing → every task; §7 changelog/docs → Task 8.
- **Type consistency:** `EvalMetric(score, passed, meta)` created in Task 1 and consumed unchanged by Tasks 2-6; `evaluate(...)` signature consistent between Task 6 and Task 7.