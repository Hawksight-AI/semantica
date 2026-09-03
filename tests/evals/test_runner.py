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
        # direction-only minimize has no well-defined pass bar; must be rejected
        with pytest.raises(ValueError, match="'minimize' requires a 'threshold'"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "minimize"}}},
            )

    def test_minimize_with_explicit_none_threshold_raises(self):
        # explicit threshold=None is the same as omitting it; must also be rejected
        with pytest.raises(ValueError, match="'minimize' requires a 'threshold'"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "minimize", "threshold": None}}},
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

    def test_invalid_per_case_objective_fails_fast_before_target_fn(self):
        calls = []

        def side_effectful_target_fn(case):
            calls.append(case)
            return "line"

        with pytest.raises(ValueError):
            evaluate(
                [{"id": "c1"}, {"id": "c2", "config": {"levenshtein": {"objective": {"direction": "diagonal"}}}}],
                evaluators=["levenshtein"],
                target_fn=side_effectful_target_fn,
            )
        # validation must reject the run before any case is processed
        assert calls == []

    def test_case_config_keeps_global_objective(self):
        # global objective on the evaluator must survive a per-case override
        # that touches other settings for the same evaluator (deep merge)
        result = evaluate(
            [{"id": "c1", "expected": "abc", "actual": "abd",
              "config": {"levenshtein": {"ignore_case": False}}}],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.0}}},
        )
        # levenshtein("abc","abd") == 1 > 0 -> objective fails the case
        assert result.cases[0].status == "fail"


class TestMergeConfig:
    """Focused tests for _merge_config two-level deep-merge semantics."""

    def test_partial_per_case_objective_inherits_global_direction(self):
        # Per-case overrides only threshold; direction must come from global.
        result = evaluate(
            [{"id": "c1", "expected": "abc", "actual": "abd",
              "config": {"levenshtein": {"objective": {"threshold": 0.99}}}}],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.0}}},
        )
        # Effective objective: minimize, threshold=0.99.
        # levenshtein("abc","abd") similarity ~0.667; 0.667 <= 0.99 -> pass.
        assert result.cases[0].status == "pass"
        assert result.cases[0].metrics["levenshtein"].passed is True

    def test_partial_per_case_objective_inherits_global_threshold(self):
        # Per-case overrides only direction; threshold must come from global.
        result = evaluate(
            [{"id": "c1", "expected": "abc", "actual": "abd",
              "config": {"levenshtein": {"objective": {"direction": "maximize"}}}}],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.99}}},
        )
        # Effective objective: maximize, threshold=0.99.
        # levenshtein("abc","abd") similarity ~0.667; 0.667 >= 0.99 -> fail.
        assert result.cases[0].status == "fail"
        assert result.cases[0].metrics["levenshtein"].passed is False

    def test_per_case_threshold_overrides_global_threshold(self):
        # Global: minimize, threshold=0.0 (would fail for any positive score).
        # Per-case: threshold=0.99 (almost everything passes minimize).
        result = evaluate(
            [{"id": "c1", "expected": "abc", "actual": "abd",
              "config": {"levenshtein": {"objective": {"threshold": 0.99}}}}],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.0}}},
        )
        # Effective: minimize, threshold=0.99 -> ~0.667 <= 0.99 -> pass.
        assert result.cases[0].status == "pass"

    def test_per_case_direction_overrides_global_direction(self):
        # Global: maximize, threshold=0.99 (would fail for ~0.667).
        # Per-case: direction=minimize (with inherited threshold=0.99).
        result = evaluate(
            [{"id": "c1", "expected": "abc", "actual": "abd",
              "config": {"levenshtein": {"objective": {"direction": "minimize"}}}}],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.99}}},
        )
        # Effective: minimize, threshold=0.99 -> ~0.667 <= 0.99 -> pass.
        assert result.cases[0].status == "pass"

    def test_fully_specified_per_case_objective_replaces_global(self):
        # Both direction and threshold specified per-case; nothing from global.
        result = evaluate(
            [{"id": "c1", "expected": "abc", "actual": "abd",
              "config": {"levenshtein": {"objective": {"direction": "maximize", "threshold": 0.5}}}}],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.0}}},
        )
        # Effective: maximize, threshold=0.5 -> ~0.667 >= 0.5 -> pass.
        assert result.cases[0].status == "pass"

    def test_per_case_non_objective_keys_do_not_erase_global_objective(self):
        # Per-case touches only non-objective evaluator keys; global objective intact.
        result = evaluate(
            [{"id": "c1", "expected": "abc", "actual": "abd",
              "config": {"levenshtein": {"threshold": 0.5}}}],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.0}}},
        )
        # Effective: minimize, threshold=0.0 -> ~0.667 > 0.0 -> fail.
        assert result.cases[0].status == "fail"

    def test_no_objective_anywhere_unchanged(self):
        # No objectives anywhere; evaluator's own verdict stands throughout.
        result = evaluate(
            [{"id": "c1", "expected": "ok", "actual": "ok",
              "config": {"exact_match": {"some_key": "v"}}}],
            evaluators=["exact_match"],
            config={"exact_match": {"other_key": "w"}},
        )
        assert result.cases[0].status == "pass"

    def test_global_config_not_mutated(self):
        import copy
        global_config = {"levenshtein": {"objective": {"direction": "minimize", "threshold": 0.5}}}
        case_config = {"levenshtein": {"objective": {"threshold": 0.2}}}
        original_global = copy.deepcopy(global_config)
        original_case = copy.deepcopy(case_config)
        evaluate(
            [{"id": "c1", "expected": "abc", "actual": "abd", "config": case_config}],
            evaluators=["levenshtein"],
            config=global_config,
        )
        assert global_config == original_global
        assert case_config == original_case


class TestThresholdValidation:
    """Threshold coercion and validation: types, NaN, infinity."""

    # --- valid numeric thresholds ---

    def test_maximize_integer_threshold(self):
        # int is a valid threshold; coerced to float
        result = evaluate(
            [("apple", "apple")],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "maximize", "threshold": 1}}},
        )
        assert result.cases[0].status == "pass"
        assert result.cases[0].metrics["levenshtein"].passed is True

    def test_minimize_integer_threshold(self):
        result = evaluate(
            [("night", "nacht")],
            evaluators=["levenshtein"],
            config={"levenshtein": {"objective": {"direction": "minimize", "threshold": 1}}},
        )
        # similarity 0.6 <= 1 -> pass
        assert result.cases[0].status == "pass"

    # --- invalid threshold types ---

    def test_non_numeric_string_threshold_raises(self):
        with pytest.raises(ValueError, match="'threshold' must be a finite number"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "maximize", "threshold": "high"}}},
            )

    def test_list_threshold_raises_value_error(self):
        # Must be ValueError, not TypeError
        with pytest.raises(ValueError, match="'threshold' must be a finite number"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "maximize", "threshold": [0.5]}}},
            )

    def test_dict_threshold_raises_value_error(self):
        with pytest.raises(ValueError, match="'threshold' must be a finite number"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "maximize", "threshold": {"v": 1}}}},
            )

    # --- NaN and infinity ---

    def test_nan_threshold_raises(self):
        with pytest.raises(ValueError, match="'threshold' must be a finite number"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "maximize", "threshold": float("nan")}}},
            )

    def test_positive_infinity_threshold_raises(self):
        with pytest.raises(ValueError, match="'threshold' must be a finite number"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "maximize", "threshold": float("inf")}}},
            )

    def test_negative_infinity_threshold_raises(self):
        with pytest.raises(ValueError, match="'threshold' must be a finite number"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "maximize", "threshold": float("-inf")}}},
            )

    def test_nan_minimize_threshold_raises(self):
        with pytest.raises(ValueError, match="'threshold' must be a finite number"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "minimize", "threshold": float("nan")}}},
            )

    # --- preserved behaviors ---

    def test_maximize_without_threshold_still_noop(self):
        # maximize without threshold remains a no-op regardless of threshold validation
        result = evaluate(
            [("ok", "no")],
            evaluators=["exact_match"],
            config={"exact_match": {"objective": {"direction": "maximize"}}},
        )
        assert result.cases[0].status == "fail"

    def test_minimize_explicit_none_threshold_still_raises(self):
        # threshold=None for minimize hits the None check before coercion
        with pytest.raises(ValueError, match="'minimize' requires a 'threshold'"):
            evaluate(
                [("a", "b")],
                evaluators=["levenshtein"],
                config={"levenshtein": {"objective": {"direction": "minimize", "threshold": None}}},
            )

    def test_threshold_errors_are_fail_fast(self):
        # Invalid threshold on case 2 must reject the whole run before case 1 executes
        calls = []

        def recording_fn(case):
            calls.append(case)
            return "x"

        with pytest.raises(ValueError, match="'threshold' must be a finite number"):
            evaluate(
                [
                    {"id": "c1"},
                    {"id": "c2", "config": {"levenshtein": {"objective": {"direction": "maximize", "threshold": [0.5]}}}},
                ],
                evaluators=["levenshtein"],
                target_fn=recording_fn,
            )
        assert calls == []
