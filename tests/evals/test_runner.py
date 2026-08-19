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


class TestObjective:
    def test_maximize_with_threshold_pass(self):
        # levenshtein similarity 1.0 for identical, objective demands >= 0.5
        result = evaluate(
            [("apple", "apple")],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.5}}},
        )
        assert result.cases[0].status == "pass"
        assert result.cases[0].metrics["levenshtein"].passed is True

    def test_maximize_with_threshold_fail(self):
        result = evaluate(
            [("apple", "aple")],  # similarity < 1.0
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.99}}},
        )
        assert result.cases[0].status == "fail"
        assert result.cases[0].metrics["levenshtein"].passed is False
        assert "levenshtein" in result.cases[0].details

    def test_minimize_with_threshold_pass(self):
        # levenshtein similarity 0.6 for ("night", "nacht"); objective: similarity <= 0.7
        result = evaluate(
            [("night", "nacht")],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.7}}},
        )
        assert result.cases[0].status == "pass"
        assert result.cases[0].metrics["levenshtein"].passed is True

    def test_minimize_with_threshold_fail(self):
        result = evaluate(
            [("night", "nacht")],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.1}}},
        )
        assert result.cases[0].status == "fail"

    def test_expect_true_on_boolean_metric(self):
        result = evaluate(
            [("ok", "ok")],
            evaluators=["exact_match"],
            config={"exact_match": {"objective": {"expect": True}}},
        )
        assert result.cases[0].status == "pass"

    def test_expect_false_overrides_passing_metric(self):
        # exact_match passes (score 1.0) but expectation is false -> fail
        result = evaluate(
            [("ok", "ok")],
            evaluators=["exact_match"],
            config={"exact_match": {"objective": {"expect": False}}},
        )
        assert result.cases[0].status == "fail"
        assert result.cases[0].metrics["exact_match"].passed is False
        assert "exact_match" in result.cases[0].details

    def test_maximize_without_threshold_is_noop(self):
        # identical behavior to no objective: evaluator's own verdict stands
        result = evaluate(
            [("ok", "no")],
            evaluators=["exact_match"],
            config={"exact_match": {"objective": {"direction": "maximize"}}},
        )
        assert result.cases[0].status == "fail"

    def test_minimize_without_threshold_raises(self):
        with pytest.raises(ValueError):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "minimize"}}},
            )

    def test_bad_direction_raises(self):
        with pytest.raises(ValueError):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "sideways", "threshold": 0.5}}},
            )

    def test_expect_with_direction_raises(self):
        with pytest.raises(ValueError):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"expect": True, "direction": "maximize"}}},
            )

    def test_error_metric_wins_over_objective(self):
        result = evaluate(
            [("[invalid", "x")],
            evaluators=["regex_match"],
            config={"regex_match": {"objective": {"direction": "maximize", "threshold": 0.0}}},
        )
        assert result.cases[0].status == "error"
        assert result.errors == 1
        assert result.failed == 0

    def test_no_objective_unchanged(self):
        result = evaluate([("ok", "no")], evaluators=["exact_match"])
        assert result.cases[0].status == "fail"

    def test_non_dict_objective_raises(self):
        with pytest.raises(ValueError):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": "maximize"}},
            )

    def test_non_bool_expect_raises(self):
        with pytest.raises(ValueError):
            evaluate(
                [("a", "b")],
                evaluators=["exact_match"],
                config={"exact_match": {"objective": {"expect": "false"}}},
            )
