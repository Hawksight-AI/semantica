"""Evals result data models.

Defines the metric and result shapes produced by the evals module.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple


@dataclass(frozen=True)
class EvalMetric:
    """One evaluator's numeric score plus pass/fail verdict."""

    score: float
    passed: bool
    meta: Dict[str, Any] = field(default_factory=dict)


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
