# Semantica Evals Module — Design

**Date:** 2026-08-19
**Status:** Approved (brainstorming)
**Scope:** Replace `semantica.evals` stub with a working evaluation module — evaluator library + Decision integration.

---

## 1. Goal

`semantica/evals/__init__.py` is currently a stub (`__status__ = "coming_soon"`, `__all__ = []`).
This PR makes it real: a **testable evaluation layer** for Semantica's decision-intelligence outputs,
modeled on Palantir's AIP Evals (`metric + objective + threshold`), so audit trails, reasoning
chains, and decision records become measurable regression targets.

No external services required at runtime. `llm_as_judge` is lazy-loaded behind an optional LLM backend.

## 2. API Surface

Style: pure functions + one lightweight runner — follows the repo's existing `methods.py` facade pattern.

### 2.1 Entry point

```python
from semantica.evals import evaluate

result = evaluate(
    cases=[{"id": "c1", "expected": {...}, "actual": {...}, "target_fn": <callable or None>}],
    evaluators=["exact_match", "decision_scores", ...],
    config={"confidence_range": [0.8, 1.0]},
)
```

- If `target_fn` present, `actual` is produced by calling it per case; otherwise `actual` is taken from the case dict.
- Evaluators are referenced by registered name; registry follows `semantica/core/registry.py` pattern.

### 2.2 Evaluators (V1, 10 built-ins)

| Name | Purpose | Decision type |
|---|---|---|
| `exact_match` | bool/str/num/array exact equality | generic |
| `regex_match` | template/format validation | generic |
| `numeric_range` | value within `[min,max]` | generic |
| `temporal_range` | datetime within window | generic |
| `length_range` | string/sequence length within bounds | generic |
| `keyword_check` | required terms present | generic |
| `levenshtein` | fuzzy text similarity >= threshold | generic |
| `rouge` | summarization overlap (R/F scores) | generic |
| `decision_scores` | **decision-specific composite** (see §3) | decision |
| `llm_as_judge` | LLM verdict (optional backend, lazy) | generic |

Each evaluator is a standalone function:

```python
def exact_match(actual, expected, config=None) -> EvalMetric:
    # EvalMetric = NamedTuple(score: float, passed: bool, meta: dict)
```

`decision_scores` is the differentiator of this PR and the only composite evaluator.

### 2.3 Result contract

Per case:

```json
{
  "case_id": "c1",
  "status": "pass" | "fail" | "error",
  "metrics": {
    "exact_match": {"value": 0.0, "passed": false, "threshold": 1.0},
    "decision_scores": {"value": 0.75, "passed": true, "threshold": 0.7}
  },
  "details": {"exact_match": {"reason": "expected 'approved' got 'denied'"}}
}
```

Aggregate:

```json
{
  "total": 10, "passed": 8, "failed": 1, "errors": 1, "pass_rate": 0.8,
  "cases": [...]
}
```

- Status semantics: `pass` all metrics passed, `fail` any metric failed, `error` evaluator raised.
- Bool evaluators score 0/1; range evaluators pass inside bounds; scored evaluators have configurable `threshold`.
- Top-level `pass_rate` is the CI gate surface.

## 3. `decision_scores` — decision-specific composite

Evaluates a `Decision` (from `semantica.context.decision_models.Decision`) or its dict form across two groups. Group ③ is interface-only (not implemented in V1).

### ① Field-level
- `outcome` equals expected value (e.g. `approved` vs `denied`)
- `confidence` within `[min, max]` (default [0,1])
- `decision_maker` non-empty, `reasoning` non-empty, `scenario` non-empty

### ② Governance-level (deterministic, no external deps)
- **Provenance present**: `decision.metadata`/`provenance` carries a non-empty audit reference; verified via `semantica.provenance` record when provided
- **Policy compliance**: if config provides both a live `PolicyEngine` instance and a `policy_id`, call `policy_engine.check_compliance(decision, policy_id)`; metric passes iff result matches expected boolean (`config["expected_policy_compliant"]`, default True). If the pair is not provided, the sub-check is skipped (not counted), never failed.
- **Causal chain reachable**: if `causal_analyzer`/graph provided, assert a causal ancestor/successor exists via `trace_decision_chain`

### ③ Interface slot (V1 documented, not implemented)
- `decision_embedding_similarity` — semantic distance against precedent using vector store. Reserved for V2; raises `NotImplementedError` with a clear message if requested.

Scoring rule: V1 reports each sub-check as its own metric (`decision_outcome`, `decision_confidence`, `decision_provenance`, `decision_policy`, `decision_maker`, ...). No weighted composite number in V1 — flat pass criteria, simple to reason about.

## 4. Module layout

```
semantica/evals/
├── __init__.py          # public API: evaluate(), list_evaluators(), __version__
├── registry.py          # evaluator name → function registration
├── runner.py            # evaluate() implementation, per-case + aggregate
├── evaluators.py        # 8 generic evaluators
├── decision_evaluators.py  # decision_scores composite
└── usage.md             # README-style module doc
```

`semantica/__init__.py` gains the `evals` proxy in `_SemanticaModules` (currently absent) — module access via `semantica.evals`.

## 5. Error handling

- Unknown evaluator name → `ValueError` with `list_evaluators()` hint.
- Evaluator raising → case status `error`, captured in `details`, never aborts the run.
- `llm_as_judge` without a configured backend → clear error directing to `semantica.llms` docs; resolver stays lazy.
- `decision_scores` receiving a non-Decision dict → coerced via `Decision.from_dict`; missing required fields → `error`, not crash.

## 6. Testing

New `tests/evals/` mirroring the `tests/` convention with `test_evals_*.py` files. Targets:

- All 9 evaluators: pass/fail/edge/error cases (table-driven)
- Registry: unknown-name error, registration decorator
- Runner: target_fn invocation, per-case status semantics, aggregation math, empty/partial case lists
- `decision_scores`: full Decision golden paths, provenance/policy/causal failure paths, non-Decision coercion
- Backward-compat: `import semantica.evals` still works; `coming_soon` flag removed, `__all__` populated

Run locally: `python -m pytest tests/evals -q`.

## 7. Docs & changelog

- `CHANGELOG.md` `[Unreleased]` entry following the existing detailed style (feature + tests + review notes)
- Module `usage.md` with minimal worked examples
- No CLI / MCP wiring in this PR (deferred to follow-up)

## 8. Out of scope (follow-up PRs)

- CLI subcommand, MCP eval tool
- Ontology simulation / sandbox for decision writes
- Grid/iteration experiments (AIP Experiment analog)
- `decision_embedding_similarity` (③)
- Action-log evaluation (lands with the Action PR)