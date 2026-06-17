---
title: "Evals Module"
description: "Evaluation framework for measuring Knowledge Graph quality, extraction accuracy, and pipeline performance: coming soon."
icon: "chart-line"
---

**`semantica.evals`** is planned as a comprehensive evaluation framework for measuring **extraction accuracy, graph quality, and pipeline performance**.

<Warning>
  **`semantica.evals` is not yet implemented.** The module is a placeholder with `__all__ = []`. No classes or functions are available for import. This page describes the planned API only.
</Warning>

## Planned Features

When released, `semantica.evals` will provide:

| Planned Class | Role |
| :--- | :--- |
| `KGEvaluator` | Completeness, consistency, schema compliance, coverage, and orphan node detection |
| `ExtractionEvaluator` | NER precision / recall / F1 and relation extraction metrics against gold datasets |
| `PipelineBenchmark` | Throughput (docs/sec), per-step latency, peak memory, and error rate |
| `RegressionTracker` | Record runs and compare metrics across commits or config changes |
| `EvalReport` | Structured report: `{scores, regressions, recommendations}` |
| `DeduplicationEvaluator` | Merge precision, false positive / false negative rates |
| `ReasoningEvaluator` | Inference accuracy, rule coverage, and derivation depth |

## Current Workaround

Until `semantica.evals` ships, use `semantica.ontology.OntologyEvaluator` for ontology quality metrics:

```python
from semantica.ontology import OntologyEvaluator

evaluator = OntologyEvaluator()

# evaluate_ontology takes the ontology dict only
result = evaluator.evaluate_ontology(ontology)

print("Coverage:    ", result.coverage_score)
print("Completeness:", result.completeness_score)
print("Gaps:        ", result.gaps)
print("Suggestions: ", result.suggestions)

# Full report with class granularity and relation completeness
report = evaluator.generate_report(ontology)
print("Coverage score:    ", report["evaluation"]["coverage_score"])
print("Completeness score:", report["evaluation"]["completeness_score"])
print("Relation coverage: ", report["relation_completeness"]["relation_coverage"])
```

`EvaluationResult` fields returned by `evaluate_ontology()`:

| Field | Type | Description |
| :----- | :---- | :----------- |
| `coverage_score` | `float` | Fraction of competency questions answerable by the ontology |
| `completeness_score` | `float` | Average of class and property completeness scores |
| `gaps` | `List[str]` | Identified gaps in coverage |
| `suggestions` | `List[str]` | Improvement suggestions |
| `metrics` | `dict` | Detailed sub-metrics |

<CardGroup cols={2}>
  <Card title="Semantic Extract" icon="magnifying-glass" href="semantic_extract">
    Extraction module.
  </Card>
  <Card title="Knowledge Graph" icon="diagram-project" href="kg">
    Graph quality assessment.
  </Card>
  <Card title="Pipeline" icon="gear" href="pipeline">
    Pipeline performance metrics.
  </Card>
  <Card title="Ontology Evaluator" icon="sitemap" href="ontology">
    Available now for ontology quality metrics.
  </Card>
</CardGroup>
