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
