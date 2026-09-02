"""Tests for the evals runner."""
import pytest

from semantica.evals.runner import evaluate


class TestEvaluate:
    def test_raw_tuple_cases(self):
        result = evaluate(
            [("approved", "approved"), ("approved", "denied")],
            evaluators=["exact_match"],
        )
        assert result.total == 2
        assert result.passed == 1
        assert result.failed == 1
        assert result.errors == 0
        assert result.pass_rate == 0.5

    def test_dict_cases_with_target_fn(self):
        def fn(case):
            return "ok" if case["id"] == "good" else "no"

        result = evaluate(
            [{"id": "good"}, {"id": "bad"}],
            evaluators=["exact_match"],
            target_fn=fn,
            config={"expected": "ok"},
        )
        assert result.passed == 1
        assert result.failed == 1

    def test_error_capture(self):
        result = evaluate([("x", "y")], evaluators=["does_not_exist"])
        assert result.errors == 1
        assert result.failed == 0
        assert result.pass_rate == 0.0

    def test_error_metric_classified_as_error(self):
        result = evaluate(
            [("[invalid", "x")],
            evaluators=["regex_match"],
        )
        assert result.errors == 1
        assert result.failed == 0
        assert result.cases[0].status == "error"

    def test_error_metric_and_fail_combine_as_error(self):
        result = evaluate(
            [("[invalid", "apple pie")],
            evaluators=["regex_match", "exact_match"],
        )
        assert result.errors == 1
        assert result.failed == 0
        assert result.cases[0].status == "error"

    def test_per_case_details(self):
        result = evaluate([("a", "b")], evaluators=["exact_match"])
        case = result.cases[0]
        assert case.status == "fail"
        assert "exact_match" in case.details

    def test_empty_cases(self):
        result = evaluate([], evaluators=["exact_match"])
        assert result.total == 0 and result.pass_rate == 1.0

    def test_multiple_evaluators(self):
        result = evaluate(
            [("apple pie", "apple pie")],
            evaluators=["exact_match", "keyword_check"],
            config={"keyword_check": {"required": ["apple"]}},
        )
        assert result.passed == 1
        assert "exact_match" in result.cases[0].metrics
        assert "keyword_check" in result.cases[0].metrics
