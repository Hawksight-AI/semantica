# Objective Layer for semantica.evals Runner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-metric objective support (direction + threshold, or Boolean expectation) to the `evaluate()` runner, overriding evaluator default pass verdicts, backward-compatible when no objective is configured.

**Architecture:** The runner already iterates evaluators and computes per-case status. Objectives are read from `config["<name>"]["objective"]`, validated up front, and applied to each returned metric's `passed` field (and `details`) before aggregation. Error metrics always win over objectives.

**Tech Stack:** Python 3.8+, stdlib only (typing, dataclasses). pytest for tests.

## Global Constraints

- Python >= 3.8: use `typing.Dict/List/Optional/Union`, never builtin generics or `|`.
- Zero new dependencies.
- Do not change the `EvalMetric` shape, the `evaluate()` signature, or the evaluator function signature.
- Existing behavior with no `objective` configured must be byte-for-byte unchanged (all 62 existing tests keep passing).
- Error metrics (`meta` contains `"error"`) always classify the case as `error`, regardless of objective.
- Config errors are programmer errors: raise `ValueError` from `evaluate()` before any evaluator runs (fail-fast).
- Tests go in `tests/evals/`, pytest class style, no new files outside the listed paths.

---

### Task 1: Objective parsing, validation, and re-decision in the runner

**Files:**
- Modify: `semantica/evals/runner.py`
- Test: `tests/evals/test_runner.py`

**Interfaces:**
- Consumes: `EvalMetric` from `.types` (fields: `score`, `passed`, `meta`); `evaluate(cases, evaluators, config=None, target_fn=None)` existing signature.
- Produces: private helpers `_parse_objective(name, eval_config) -> Optional[Dict]` (returns `None` when no objective configured, raises `ValueError` on invalid config) and `_apply_objective(metric, objective) -> bool` (returns the re-decided `passed`). Public `evaluate()` behavior extended as specified.

- [ ] **Step 1: Write the failing tests**

Append a new test class to `tests/evals/test_runner.py`:

```python
class TestObjective:
    def test_maximize_with_threshold_pass(self):
        # levenshtein similarity 1.0 for identical, objective demands >= 0.5
        result = evaluate(
            [("apple", "apple")],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.5}}},
        )
        assert result.cases[0].status == "pass"
        assert result.cases[0].metrics["levenshtein"].passed is True

    def test_maximize_with_threshold_fail(self):
        result = evaluate(
            [("apple", "aple")],  # similarity < 1.0
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.99}}},
        )
        assert result.cases[0].status == "fail"
        assert result.cases[0].metrics["levenshtein"].passed is False
        assert "levenshtein" in result.cases[0].details

    def test_minimize_with_threshold_pass(self):
        # edit distance normalized ~0.2; objective: distance <= 0.5
        result = evaluate(
            [("night", "nacht")],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.5}}},
        )
        assert result.cases[0].status == "pass"
        assert result.cases[0].metrics["levenshtein"].passed is True

    def test_minimize_with_threshold_fail(self):
        result = evaluate(
            [("night", "nacht")],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.1}}},
        )
        assert result.cases[0].status == "fail"

    def test_expect_true_on_boolean_metric(self):
        result = evaluate(
            [("ok", "ok")],
            evaluators=["exact_match"],
            config={"exact_match": {"objective": {"expect": True}}},
        )
        assert result.cases[0].status == "pass"

    def test_expect_false_overrides_passing_metric(self):
        # exact_match passes (score 1.0) but expectation is false -> fail
        result = evaluate(
            [("ok", "ok")],
            evaluators=["exact_match"],
            config={"exact_match": {"objective": {"expect": False}}},
        )
        assert result.cases[0].status == "fail"
        assert result.cases[0].metrics["exact_match"].passed is False
        assert "exact_match" in result.cases[0].details

    def test_maximize_without_threshold_is_noop(self):
        # identical behavior to no objective: evaluator's own verdict stands
        result = evaluate(
            [("ok", "no")],
            evaluators=["exact_match"],
            config={"exact_match": {"objective": {"direction": "maximize"}}},
        )
        assert result.cases[0].status == "fail"

    def test_minimize_without_threshold_raises(self):
        import pytest as _pytest
        with _pytest.raises(ValueError):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "minimize"}}},
            )

    def test_bad_direction_raises(self):
        import pytest as _pytest
        with _pytest.raises(ValueError):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "sideways", "threshold": 0.5}}},
            )

    def test_expect_with_direction_raises(self):
        import pytest as _pytest
        with _pytest.raises(ValueError):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"expect": True, "direction": "maximize"}}},
            )

    def test_error_metric_wins_over_objective(self):
        result = evaluate(
            [("[invalid", "x")],
            evaluators=["regex_match"],
            config={"regex_match": {"objective": {"direction": "maximize", "threshold": 0.0}}},
        )
        assert result.cases[0].status == "error"
        assert result.errors == 1
        assert result.failed == 0

    def test_no_objective_unchanged(self):
        result = evaluate([("ok", "no")], evaluators=["exact_match"])
        assert result.cases[0].status == "fail"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/evals/test_runner.py -q`
Expected: the new `TestObjective` tests fail (objective config ignored → `exact_match` passes under `expect:false` etc.); the pre-existing tests in the file still pass.

- [ ] **Step 3: Implement objective parsing, validation, and re-decision**

In `semantica/evals/runner.py`, add two helpers before `evaluate` and wire them into the evaluator loop.

```python
def _parse_objective(name, eval_config):
    """Return the validated objective dict, or None when not configured.

    Raises ValueError for invalid configurations (programmer error).
    """
    objective = (eval_config or {}).get("objective")
    if objective is None:
        return None
    direction = objective.get("direction")
    threshold = objective.get("threshold")
    expect = objective.get("expect")

    if expect is not None:
        if direction is not None or threshold is not None:
            raise ValueError(
                f"objective for '{name}': 'expect' cannot be combined with "
                "'direction' or 'threshold'"
            )
        return {"expect": bool(expect)}
    if direction == "minimize":
        if threshold is None:
            raise ValueError(
                f"objective for '{name}': 'minimize' requires a 'threshold'"
            )
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
```

Then modify the evaluator loop in `evaluate()` so the parsed objective is computed once per case (outside the evaluator loop, since it only depends on merged config), and applied inside the loop:

```python
        objective_by_name = {
            name: _parse_objective(name, merged.get(name) or {})
            for name in evaluators
        }
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
```

Note: `objective_by_name` is computed once per case (it depends only on merged config), so invalid config raises `ValueError` at the first case — satisfying the fail-fast requirement. `EvalMetric` is a frozen dataclass, so the re-verdict constructs a new instance preserving score/meta.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/evals/test_runner.py -q`
Expected: all `TestObjective` tests pass; pre-existing tests still pass.

- [ ] **Step 5: Run the full evals suite**

Run: `python3 -m pytest tests/evals -q`
Expected: 62 existing + new tests all pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add semantica/evals/runner.py tests/evals/test_runner.py
git commit -m "feat(evals): add per-metric objective support to runner"
```

---

### Task 2: Documentation — usage.md and CHANGELOG

**Files:**
- Modify: `semantica/evals/usage.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: the objective config surface implemented in Task 1 (exact keys: `objective.direction`, `objective.threshold`, `objective.expect`; validation rules).
- Produces: docs only.

- [ ] **Step 1: Add objective section to usage.md**

Append a section after the existing "Run the runner over decision records" section:

```markdown
## Set per-evaluator objectives

By default each evaluator decides its own pass/fail. To override that
verdict at the run level, configure an **objective** per evaluator name:

```python
from semantica.evals import evaluate

# Require a minimum similarity (default direction is maximize):
evaluate(
    [("apple", "aple")],
    evaluators=["levenshtein"],
    config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.7}}},
)

# Lower is better — override the direction:
evaluate(
    [("night", "nacht")],
    evaluators=["levenshtein"],
    config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.5}}},
)

# Boolean expectation on a 0/1 metric:
evaluate(
    [("ok", "ok")],
    evaluators=["exact_match"],
    config={"exact_match": {"objective": {"expect": False}}},
)
```

Rules:

- `maximize` + `threshold`: pass iff `score >= threshold`. `maximize` without
  a threshold is a no-op (the evaluator's own verdict stands).
- `minimize` + `threshold`: pass iff `score <= threshold`. `minimize`
  **requires** a threshold — omitting it raises `ValueError`.
- `expect` (`true`/`false`): pass iff `bool(score)` matches; cannot be
  combined with `direction`/`threshold`.
- A metric whose `meta` contains `"error"` is always an error, never affected
  by an objective.
- Invalid objective config raises `ValueError` before any evaluator runs.
```

- [ ] **Step 2: Add CHANGELOG entry**

Under `## [Unreleased]` → `### Added`, insert a new bullet at the top (before the `semantica.evals` module entry), following existing style:

```markdown
- **`semantica.evals` runner gains per-metric objectives** (#1091)
  - `evaluate()` now accepts `config={"<evaluator>": {"objective": {"direction": "maximize"|"minimize", "threshold": X}}}` to override the evaluator's default pass verdict with a threshold; `{"objective": {"expect": bool}}` expresses a Boolean expectation
  - `minimize` requires a `threshold`; `maximize` without one is a no-op; `expect` cannot be combined with `direction`/`threshold`; invalid config raises `ValueError` before any evaluator runs
  - Error metrics are never affected by objectives (error wins over fail)
  - Backward compatible: no `objective` key → existing behavior unchanged
  - New tests in `tests/evals/test_runner.py::TestObjective`
```

- [ ] **Step 3: Verify docs examples run**

Run the three examples from Step 1 as a Python script (import `evaluate`, run each snippet) to confirm they don't raise unexpectedly. No test output assertion needed beyond "no exception" and sensible status values.

- [ ] **Step 4: Commit**

```bash
git add semantica/evals/usage.md CHANGELOG.md
git commit -m "docs(evals): document per-metric objectives"
```

---

## Self-Review Notes

- **Spec coverage:** §3.1 (config surface) → Task 1 helpers + Task 2 docs; §3.2 (semantics: maximize/minimize/expect) → Task 1 `_apply_objective`; §3.3 (error wins) → Task 1 error branch + `test_error_metric_wins_over_objective`; §3.4 rules 1-3 (validation) → Task 1 `_parse_objective` + 4 validation tests; §3.4 rule 4 → error branch; §3.5 (aggregation unchanged, details on final verdict) → Task 1 loop + `test_expect_false_overrides_passing_metric` asserts `details`; §4 (fail-fast ValueError) → `_parse_objective` at case top; §5 (tests) → Task 1 test class; §6 (compat) → `test_no_objective_unchanged` + full-suite green.
- **Type consistency:** `_parse_objective(name, eval_config) -> Optional[Dict]`, `_apply_objective(metric, objective) -> bool`; `EvalMetric(score, passed, meta)` positional construction preserved everywhere.
- **Backward compat:** objective parsed to `None` for absent config → loop behavior identical to before.
