# Design: Objective layer for `semantica.evals` runner

**Date:** 2026-08-19
**Issue:** semantica-agi/semantica#1091 (assigned to pkupt)
**Base:** PR #1090 (`semantica.evals` module)

## 1. Problem

`semantica.evals` runs named evaluators and aggregates per-case pass/fail, but the pass judgement is hard-coded inside each evaluator — a higher score always means "better". There is no way to express an evaluation objective at the run level:

- apply a threshold the evaluator does not encode (e.g. "F1 must be ≥ 0.7");
- reverse the direction (e.g. "lower edit distance is better");
- express a Boolean expectation (e.g. "this metric should be `false`").

This blocks the domain-specific benchmark harnesses `docs/community-projects.md` says `semantica.evals` supports. Palantir AIP Evals models exactly this: each metric has an **objective** (Boolean expected value, or numeric `maximize`/`minimize` direction with an optional threshold), and a test case passes when **all** its metrics meet their objectives.

## 2. Scope

In scope:

- A per-metric objective configuration consumed by the `evaluate()` runner.
- Runner-level pass/fail re-decision for numeric scores and Boolean metrics.
- Backward-compatible behavior when no objective is configured.
- Tests and docs.

Out of scope:

- Changing the evaluator signature or the `EvalMetric` shape.
- Multi-iteration test cases (AIP Evals has them; Semantica's runner is single-iteration per case).
- Objective-aware aggregation beyond per-case `pass`/`fail` (existing `pass_rate` semantics are kept).

## 3. Design

### 3.1 Configuration surface

Objective is configured per evaluator inside the runner's `config`, under the evaluator name:

```python
config = {
    "<evaluator_name>": {
        "objective": {
            "direction": "maximize" | "minimize",
            "threshold": <float>,   # optional
        }
    }
}
```

Boolean-form objective (shorthand): for metrics whose score is Boolean-like (0.0/1.0) or for semantic clarity, `{"objective": {"expect": true}}` / `{"objective": {"expect": false}}` is also supported.

### 3.2 Evaluation semantics

For each metric produced by an evaluator during a case run, if an objective exists for that evaluator name, the runner recomputes the metric's pass verdict:

- **maximize** (default): pass iff `score >= threshold` when `threshold` is given; otherwise pass iff `score == metric.passed`'s default meaning is unchanged — i.e. no objective, no re-decision. (See "no threshold" rule below.)
- **minimize**: pass iff `score <= threshold` when `threshold` is given; otherwise pass iff `score` is the minimum possible for the metric (handled explicitly: `minimize` without `threshold` passes iff `score <= 0` for error/range metrics — **decision: require threshold for minimize to avoid ambiguity**, see 3.4).
- **expect**: pass iff `bool(score)` equals `expect` (for Boolean-style metrics).

When an objective is present, the runner **overrides** `metric.passed` with the objective verdict. When absent, `metric.passed` is used unchanged (existing behavior).

### 3.3 Interaction with errors

An `EvalMetric` whose `meta` contains `"error"` remains classified as an error regardless of objective (error wins over fail, per the existing contract). Objectives only affect non-error metrics.

### 3.4 Ambiguity rules (explicit decisions)

1. **`minimize` without `threshold`** is rejected at config-validation time with a clear error (`ValueError`), because "lowest is best" has no absolute pass bar without a threshold. (AIP Evals allows direction-only; we require threshold to keep pass/fail well-defined.) — *Chosen for determinism; revisit if a use case demands direction-only minimize.*
2. **`maximize` without `threshold`** behaves like no objective (pass iff evaluator's own `passed`), because the evaluator's default is already "higher is better".
3. **`expect` with a numeric `direction`/`threshold`** is a config error (`ValueError`): pick one form.
4. **Objective on a metric that errors** → the error wins (3.3), objective ignored.

### 3.5 Aggregation

Unchanged:

- Case `status`: `"error"` if any metric errored, else `"fail"` if any failed, else `"pass"`.
- `pass_rate` = passed / total (1.0 on empty).
- `metrics` dict holds the (possibly re-verdict'd) `EvalMetric`; the re-verdict is observable via `metric.passed`.

### 3.6 Files

- `semantica/evals/runner.py` — add objective parsing/validation and re-decision inside the evaluator loop.
- `tests/evals/test_runner.py` — new test class(es) for objective semantics.
- `semantica/evals/usage.md` — document the objective config and examples.
- `CHANGELOG.md` — `[Unreleased]` entry.

No new dependencies; Python ≥ 3.8 (stdlib `typing`).

## 4. Error handling

- Invalid objective config (`direction` not in {maximize, minimize}, both `expect` and `direction`, `minimize` without threshold, non-numeric threshold) → `ValueError` raised at runner config parse, before any evaluator runs. Deterministic, fail-fast.
- These are programmer errors, not per-case data errors — no per-case `error` status involved.

## 5. Testing

New tests in `tests/evals/test_runner.py`:

1. maximize + threshold: score ≥ threshold → pass; below → fail.
2. minimize + threshold: score ≤ threshold → pass; above → fail (e.g. levenshtein on a close pair).
3. minimize without threshold → `ValueError`.
4. expect=true / expect=false on a Boolean metric (exact_match) — pass/fail per expectation.
5. no objective → existing behavior unchanged (evaluator's own verdict).
6. objective + error metric → error wins (status=error, not fail).
7. config error (bad direction) → `ValueError` raised by `evaluate()`.
8. backward-compat: all existing 62 tests keep passing.

## 6. Compatibility

- Public API (`evaluate`, `list_evaluators`, `get_evaluator`, types) unchanged in signature.
- `EvalMetric` shape unchanged (score, passed, meta) — only `passed` may be recomputed by the runner.
- Existing configs (no `objective` key) behave identically.
