---
title: "Evals Module"
description: "Score decision records, audit trails, and reasoning output with deterministic and model-backed evaluators plus a small run harness."
icon: "chart-line"
---

`semantica.evals` measures the quality of decision intelligence outputs. It takes
the decisions, audit trails, and reasoning text your pipeline produces and scores
them against expectations you define, returning a structured summary you can log,
assert on in tests, or track across runs.

- A registry of named evaluators, from exact string matching to ROUGE overlap and
  LLM-as-judge
- `decision_scores`, a composite evaluator for `Decision` objects that checks
  outcome, confidence bounds, required fields, provenance, and (optionally)
  policy compliance
- A `evaluate()` runner that applies several evaluators to a list of cases and
  aggregates pass / fail / error counts
- Per-evaluator **objectives** that let you override an evaluator's built-in
  verdict at the run level

<Note>
  The module is versioned separately from the package: `semantica.evals.__version__`
  is `"0.1.0"`. The public surface described here is stable, but expect additive
  changes (new evaluators, new objective options) before it reaches 1.0.
</Note>

## Public API

| Name | Kind | Role |
| :--- | :--- | :--- |
| `evaluate(cases, evaluators, config=None, target_fn=None)` | function | Run named evaluators over each case, return an `EvalSummary` |
| `list_evaluators()` | function | Sorted names of every registered evaluator |
| `get_evaluator(name)` | function | Look up a single evaluator function by name |
| `EvalMetric` | dataclass (frozen) | One evaluator's result: `score`, `passed`, `meta` |
| `CaseResult` | namedtuple | One case's result: `case_id`, `status`, `metrics`, `details` |
| `EvalSummary` | dataclass | Aggregate across cases: `total`, `passed`, `failed`, `errors`, `pass_rate`, `cases` |

```python
import semantica.evals as evals
from semantica.evals import evaluate, list_evaluators, get_evaluator
```

## Built-in evaluators

Every evaluator is a plain function `fn(actual, expected, config=None) -> EvalMetric`
registered under a stable name. `list_evaluators()` returns the current set:

```python
>>> list_evaluators()
['decision_scores', 'exact_match', 'keyword_check', 'length_range',
 'levenshtein', 'llm_as_judge', 'numeric_range', 'regex_match', 'rouge',
 'temporal_range']
```

| Name | Passes when | Relevant `config` keys |
| :--- | :--- | :--- |
| `exact_match` | `actual == expected` | none |
| `regex_match` | `re.search(expected, actual)` matches | none |
| `keyword_check` | every required term appears in `actual` (word-boundary) | `required` (falls back to `expected`) |
| `numeric_range` | `min <= actual <= max` | `min`, `max` (both required) |
| `temporal_range` | ISO datetime `actual` falls in `[min, max]` | `min`, `max` as ISO strings (both required) |
| `length_range` | `min <= len(actual) <= max` | `min` (default 0), `max` (required) |
| `levenshtein` | normalized similarity `>= threshold` | `threshold` (default 0.8) |
| `rouge` | ROUGE-1 F1 `> 0` and `>= threshold` | `threshold` (default 0.0) |
| `llm_as_judge` | caller-supplied `judge_fn(actual, expected)` returns truthy | `judge_fn` (required callable) |
| `decision_scores` | all configured sub-checks on a `Decision` pass | see below |

An evaluator that cannot run (bad regex, unparseable datetime, no `judge_fn`) returns an
`EvalMetric` with an `"error"` key in `meta` rather than raising. Evaluators that
require numeric bounds (`numeric_range`, `length_range`) instead return a failing
metric with a `"reason"` key when the bound is missing — they do not raise and do
not set `"error"`.

### `decision_scores`

`decision_scores` accepts a `Decision` (from `semantica.context.decision_models`)
or its dict form and runs a set of field-level and governance checks. The score is
the fraction of checks that passed; `passed` is `True` only when all of them did.

| Sub-check | Controlled by |
| :--- | :--- |
| Outcome matches | `expected_outcome` in config, or the case's `expected`; **skipped** when neither is set |
| Confidence in range | `min_confidence` (default 0.0), `max_confidence` (default 1.0); always run |
| `decision_maker`, `reasoning`, `scenario` non-empty | always run |
| Provenance present in metadata | `provenance_key` (default `"provenance"`); always run |
| Policy compliance | `policy_engine` and `policy_id` both set; skipped otherwise |

Passing `causal_chain_exists` in config raises `NotImplementedError`. That key is a
reserved slot for a future release.

## Running an evaluation

`evaluate()` takes a list of cases and a list of evaluator names. A case is either
a `(expected, actual)` tuple or a dict:

```python
{
    "id": "loan-001",          # optional, generated if absent
    "expected": ...,           # optional; some evaluators read it, some don't
    "actual": ...,             # the value under test
    "config": {...},           # optional, per-evaluator settings for this case
    "target_fn": callable,     # optional, called with the case to produce `actual`
}
```

If `actual` is missing, the runner calls the case's `target_fn` (or the
`target_fn` passed to `evaluate()`) to produce it. Per-case `config` is deep-merged
over the top-level `config`, so a case can override one evaluator's settings
without discarding the rest.

```python
from datetime import datetime

from semantica.context.decision_models import Decision
from semantica.evals import evaluate

decision = Decision(
    decision_id="d-1",
    category="loan",
    scenario="loan-request",
    reasoning="vetted against lending policy v3",
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
]

summary = evaluate(cases, ["decision_scores"])
print(summary.pass_rate)   # 1.0
```

Evaluators run independently per case. If one raises, that case's `status` becomes
`"error"` and the exception text is captured in the metric's `meta`; the rest of
the run continues.

## Objectives

By default each evaluator decides its own pass / fail. An **objective** overrides
that verdict at the run level, keyed by evaluator name under `config`:

```python
# Raise levenshtein's bar from its default 0.8 to 0.9
evaluate(
    [("apple", "aple")],
    evaluators=["levenshtein"],
    config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.9}}},
)

# Lower is better
evaluate(
    [("night", "nacht")],
    evaluators=["levenshtein"],
    config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.5}}},
)

# Expect the metric NOT to match
evaluate(
    [("ok", "ok")],
    evaluators=["exact_match"],
    config={"exact_match": {"objective": {"expect": False}}},
)
```

Rules:

- `maximize` with `threshold`: pass iff `score >= threshold`. `maximize` with no
  threshold is a no-op and the evaluator's own verdict stands.
- `minimize` with `threshold`: pass iff `score <= threshold`. `minimize`
  **requires** a threshold; omitting it raises `ValueError`.
- `expect` (`True` / `False`): pass iff `bool(score)` equals it. Cannot be combined
  with `direction` or `threshold`, and must be a real boolean.
- A metric that already carries an `"error"` in its `meta` is unaffected by any
  objective.
- Invalid objective config is validated for every case before any evaluator runs,
  so a bad objective fails the whole run up front rather than partway through.

## Reading the summary

```python
summary = evaluate(cases, ["decision_scores"])

summary.total, summary.passed, summary.failed, summary.errors
summary.pass_rate    # passed / total, or 1.0 for an empty case list

for case in summary.cases:
    print(case.case_id, case.status)          # status: "pass" | "fail" | "error"
    for name, metric in case.metrics.items():
        print(name, metric.score, metric.passed)
        print(metric.meta.get("reasons", {}))  # per-sub-check failure reasons
```

`EvalMetric` is frozen (`score: float`, `passed: bool`, `meta: dict`). `CaseResult`
is a namedtuple, and `EvalSummary` is a plain dataclass, so all three are
straightforward to serialize for logging or regression tracking.

## Notes

- `llm_as_judge` needs `config["judge_fn"]`, a callable
  `judge_fn(actual, expected) -> bool` you supply. No LLM backend is imported
  unless you pass one in.
- `decision_scores` governance checks are opt-in: policy compliance is only
  evaluated when both `policy_engine` and `policy_id` are present.

## See also

- [Decision Intelligence](/guides/decision-intelligence) — producing the `Decision` records this module scores
- [Reasoning](/reference/reasoning) — inference output that reasoning-text evaluators can measure
- [Policy Engine](/guides/policy-engine) — the `policy_engine` used by `decision_scores`
- [Ontology Evaluator](/reference/ontology) — separate tooling for ontology quality metrics
