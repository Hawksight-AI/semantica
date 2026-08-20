# Semantica Evals — Usage

The evals module measures decision intelligence outputs: decision records,
audit trails, and reasoning output — with deterministic and model-backed
evaluators plus a small runner.

## Import

```python
import semantica.evals as evals          # through the root lazy proxy
from semantica.evals import evaluate, list_evaluators
```

## Discover evaluators

```python
>>> evals.list_evaluators()
['decision_scores', 'exact_match', 'keyword_check', 'length_range',
 'levenshtein', 'llm_as_judge', 'numeric_range', 'regex_match', 'rouge',
 'temporal_range']
```

`list_evaluators` returns every name registered by importing the package —
the import wiring runs each evaluator module's `register()` side effects.

## Run the runner over decision records

`evaluate(cases, evaluators, config=None)` accepts a list of cases; each case is
a dict with `expected`, `actual`, optional `config`, and optional `id`. The
`actual` can be a finished `Decision` object or its dict form.

```python
from datetime import datetime
from semantica.context.decision_models import Decision
from semantica.evals import evaluate

decision = Decision(
    decision_id="d-1",
    category="loan",
    scenario="loan-request",
    reasoning="vetted by policy",
    outcome="approve",
    confidence=0.87,
    timestamp=datetime.now(),
    decision_maker="approver-a",
    metadata={"provenance": "workflow:loan/v3"},
)

cases = [
    {
        "id": "loan-001",
        "actual": decision,
        "config": {
            "decision_scores": {
                "expected_outcome": "approve",
                "min_confidence": 0.7,
            }
        },
    },
    {
        "id": "loan-002",
        "actual": {
            "decision_id": "d-2",
            "category": "loan",
            "scenario": "loan-request",
            "reasoning": "auto",
            "outcome": "reject",
            "confidence": 0.9,
            "timestamp": datetime.now().isoformat(),
            "decision_maker": "system",
            "metadata": {},
        },
        "config": {
            "decision_scores": {
                "expected_outcome": "approve",
                "min_confidence": 0.7,
            }
        },
    },
]

summary = evaluate(cases, ["decision_scores"])
```

`evaluate` also runs high-level names like `exact_match`, `keyword_check`, or
`llm_as_judge`; per-case or top-level `config` may carry per-evaluator settings
(e.g. `config={"exact_match": {...}}`).

## Set per-evaluator objectives

By default each evaluator decides its own pass/fail. To override that
verdict at the run level, configure an **objective** per evaluator name:

```python
from semantica.evals import evaluate

# Require a minimum similarity (levenshtein's default bar is >= 0.8; here we set 0.7):
evaluate(
    [("apple", "aple")],
    evaluators=["levenshtein"],
    config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.7}}},
)

# Lower is better — override the direction:
evaluate(
    [("night", "nacht")],
    evaluators=["levenshtein"],
    config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.7}}},
)

# Boolean expectation — the metric matches (score 1), but we expect it not to:
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
  without a threshold is a no-op (the evaluator's own verdict stands).
- `expect` (`true`/`false`): pass iff `bool(score)` matches; cannot be
  combined with `direction`/`threshold`. `expect` must be a real boolean
  (a string like `"false"` is rejected).
- A metric whose `meta` contains `"error"` is always an error, never affected
  by an objective.
- Invalid objective config (non-dict objective, bad `direction`, non-bool
  `expect`) raises `ValueError` before any evaluator runs.

## Interpret the summary

```python
>>> summary.total, summary.passed, summary.failed, summary.errors
(2, 1, 1, 0)
>>> summary.pass_rate
0.5

>>> for case in summary.cases:
...     print(case.case_id, case.status)
...     for name, metric in case.metrics.items():
...         print("  ", name, metric.score, metric.passed)
...         print("    ", metric.meta.get("reasons"))
loan-001 pass
   decision_scores 1.0 True
    {}
loan-002 fail
   decision_scores 0.667 False
    {'decision_outcome': "expected 'approve', got 'reject'",
     'provenance': 'no provenance record found in metadata'}
```

`EvalSummary` fields:

- `total` / `passed` / `failed` / `errors` — case counts by status.
- `pass_rate` — `passed / total` (1.0 on an empty case list).
- `cases` — one `CaseResult` per input case: `case_id`, `status`
  (`pass` | `fail` | `error`), `metrics` (name → `EvalMetric` with `score`,
  `passed`, `meta`), and `details`.

Evaluator failures do not crash the run; they surface as `status="error"` on
the affected case with the exception text captured in the metric meta.

## Notes

- **`llm_as_judge` needs `config["judge_fn"]`**: a callable
  `judge_fn(actual, expected) -> bool` supplied by the caller. Without it the
  evaluator fails with `config['judge_fn'] required`.
- **`decision_scores` governance checks are opt-in**: policy compliance is only
  evaluated when both `config["policy_engine"]` and `config["policy_id"]` are
  provided; otherwise those checks are skipped. The reserved
  `causal_chain_exists` slot is not yet implemented.