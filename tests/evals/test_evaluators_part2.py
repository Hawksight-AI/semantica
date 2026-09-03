"""Tests for generic evaluators: keyword, levenshtein, rouge, llm-as-judge."""
import pytest

from semantica.evals import registry as reg


class TestKeywordCheck:
    def test_all_required_present(self):
        r = reg.get_evaluator("keyword_check")(
            "the loan was approved", expected=["loan", "approved"]
        )
        assert r.passed

    def test_missing_keyword(self):
        r = reg.get_evaluator("keyword_check")(
            "the loan was approved", expected=["loan", "denied"]
        )
        assert not r.passed
        assert "denied" in r.meta.get("missing", [])

    def test_short_words_ignored(self):
        r = reg.get_evaluator("keyword_check")("x and y", expected=["and"])
        assert r.passed


class TestLevenshtein:
    def test_identical(self):
        r = reg.get_evaluator("levenshtein")("credit approved", "credit approved")
        assert r.passed

    def test_close_above_threshold(self):
        r = reg.get_evaluator("levenshtein")(
            "credit approved", "credit denied", config={"threshold": 0.8}
        )
        assert not r.passed

    def test_default_threshold(self):
        assert reg.get_evaluator("levenshtein")("a", "a").passed


class TestRouge:
    def test_identical(self):
        r = reg.get_evaluator("rouge")("loan approved by committee", "loan approved by committee")
        assert r.passed
        assert r.meta["f1"] == pytest.approx(1.0)

    def test_no_overlap(self):
        r = reg.get_evaluator("rouge")("one two three", "four five six")
        assert not r.passed

    def test_partial_sets_meta(self):
        r = reg.get_evaluator("rouge")("a b c", "a b d", config={"threshold": 0.5})
        assert "precision" in r.meta and "recall" in r.meta


class TestLlmAsJudge:
    def test_uses_supplied_judge(self):
        judge = lambda actual, expected: actual == expected  # noqa: E731
        r = reg.get_evaluator("llm_as_judge")(
            "x", "x", config={"judge_fn": judge}
        )
        assert r.passed

    def test_missing_judge_is_error(self):
        r = reg.get_evaluator("llm_as_judge")("x", "y", config={})
        assert not r.passed
        assert r.meta.get("error")
