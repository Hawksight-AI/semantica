"""Tests for evals result models."""
import pytest

from semantica.evals.types import CaseResult, EvalMetric, EvalSummary


class TestEvalMetric:
    def test_construction(self):
        m = EvalMetric(score=1.0, passed=True, meta={"threshold": 1.0})
        assert m.score == 1.0 and m.passed and m.meta["threshold"] == 1.0

    def test_default_meta(self):
        m = EvalMetric(0.0, False)
        assert m.meta == {}

    def test_default_meta_is_not_shared(self):
        m1 = EvalMetric(0.0, False)
        m2 = EvalMetric(0.0, False)
        m1.meta["mutated"] = True
        assert "mutated" not in m2.meta


class TestCaseResult:
    def test_status_fail_on_any_failed_metric(self):
        r = CaseResult(
            case_id="c1",
            status="fail",
            metrics={"exact_match": EvalMetric(0.0, False)},
            details={},
        )
        assert r.status == "fail"
        assert r.metrics["exact_match"].passed is False


class TestEvalSummary:
    def test_pass_rate(self):
        s = EvalSummary(total=10, passed=8, failed=1, errors=1, pass_rate=0.8)
        assert s.pass_rate == 0.8

    def test_cases_are_mutable(self):
        s = EvalSummary(0, 0, 0, 0, 1.0)
        s.cases.append(CaseResult("c", "pass", {}, {}))
        assert len(s.cases) == 1
