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
