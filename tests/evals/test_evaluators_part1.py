"""Tests for generic evaluators: exact, regex, ranges, length."""
import pytest

from semantica.evals import registry as reg


class TestExactMatch:
    def test_exact_str(self):
        r = reg.get_evaluator("exact_match")("approved", "approved")
        assert r.passed and r.score == 1.0

    def test_exact_str_negative(self):
        r = reg.get_evaluator("exact_match")("approved", "denied")
        assert not r.passed and r.score == 0.0

    def test_exact_number(self):
        r = reg.get_evaluator("exact_match")(5, 5)
        assert r.passed

    def test_exact_array(self):
        r = reg.get_evaluator("exact_match")([1, 2], [1, 2])
        assert r.passed


class TestRegexMatch:
    def test_matching(self):
        r = reg.get_evaluator("regex_match")("abc123", r"^[a-z]+\d+$")
        assert r.passed

    def test_non_matching(self):
        r = reg.get_evaluator("regex_match")("ABC", r"^[a-z]+$")
        assert not r.passed
        assert "ABC" in r.meta.get("reason", "")

    def test_invalid_regex_is_error_metric(self):
        r = reg.get_evaluator("regex_match")("x", "[invalid")
        assert not r.passed
        assert r.meta.get("error")


class TestNumericRange:
    def test_inside(self):
        r = reg.get_evaluator("numeric_range")(0.9, config={"min": 0.8, "max": 1.0})
        assert r.passed and r.score == 1.0

    def test_outside(self):
        r = reg.get_evaluator("numeric_range")(0.5, config={"min": 0.8, "max": 1.0})
        assert not r.passed and r.score == 0.0

    def test_bounds_inclusive(self):
        assert reg.get_evaluator("numeric_range")(0.8, config={"min": 0.8, "max": 0.8}).passed


class TestTemporalRange:
    def test_inside_window(self):
        r = reg.get_evaluator("temporal_range")(
            "2026-01-15T10:00:00",
            config={"min": "2026-01-01T00:00:00", "max": "2026-02-01T00:00:00"},
        )
        assert r.passed

    def test_outside_window(self):
        r = reg.get_evaluator("temporal_range")(
            "2026-03-01T00:00:00",
            config={"min": "2026-01-01T00:00:00", "max": "2026-02-01T00:00:00"},
        )
        assert not r.passed


class TestLengthRange:
    def test_ok(self):
        r = reg.get_evaluator("length_range")("hello", config={"min": 3, "max": 5})
        assert r.passed

    def test_too_long(self):
        r = reg.get_evaluator("length_range")([1, 2, 3], config={"min": 1, "max": 2})
        assert not r.passed

    def test_min_not_given_defaults_zero(self):
        r = reg.get_evaluator("length_range")("abc", config={"max": 5})
        assert r.passed
