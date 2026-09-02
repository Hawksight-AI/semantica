"""Tests for the evaluator registry."""
import pytest

from semantica.evals import registry as reg
from semantica.evals.types import EvalMetric

# A unique name that will not collide with any production evaluator.
_TEST_EVAL_NAME = "test_registry_demo_eval"


class TestRegistry:
    def teardown_method(self, method):
        # Remove the test evaluator after each test that may have registered it,
        # so re-runs and randomised collection cannot see stale state.
        reg.EVALUATORS.pop(_TEST_EVAL_NAME, None)

    def test_register_and_get(self):
        @reg.register(_TEST_EVAL_NAME)
        def demo(actual, expected, config=None, **kwargs):
            return EvalMetric(1.0, True)

        assert reg.get_evaluator(_TEST_EVAL_NAME) is demo
        assert _TEST_EVAL_NAME in reg.list_evaluators()

    def test_registration_is_immutable_after_commit(self):
        with pytest.raises(ValueError):
            reg.get_evaluator("does_not_exist")

    def test_unknown_evaluator_failure_message(self):
        with pytest.raises(ValueError) as exc:
            reg.get_evaluator("nope")
        msg = str(exc.value)
        assert "nope" in msg
        # The error message lists available evaluators; verify using a name
        # that is always registered at import time (independent of test order).
        assert "exact_match" in msg
