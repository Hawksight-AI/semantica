"""Semantica Evals — evaluation layer for decision intelligence outputs.

Provides a small library of deterministic and model-backed evaluators plus a
runner for measuring decision records, audit trails, and reasoning output.
"""

from . import decision_evaluators  # noqa: F401 (registers decision_scores)
from . import evaluators  # noqa: F401 (registers the generic evaluators)
from .registry import list_evaluators
from .runner import evaluate
from .types import CaseResult, EvalMetric, EvalSummary

__version__ = "0.1.0"
__all__ = ["evaluate", "list_evaluators", "CaseResult", "EvalMetric", "EvalSummary"]
