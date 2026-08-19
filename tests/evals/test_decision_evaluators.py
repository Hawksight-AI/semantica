"""Tests for the decision_scores composite evaluator."""
import pytest
from datetime import datetime

from semantica.context.decision_models import Decision
from semantica.evals import registry as reg


def _decision(**overrides):
    base = dict(
        decision_id="d1",
        category="loan",
        scenario="mortgage application",
        reasoning="strong credit history",
        outcome="approved",
        confidence=0.95,
        timestamp=datetime(2026, 1, 1),
        decision_maker="loan_officer",
    )
    base.update(overrides)
    return Decision(**base)


class TestDecisionScores:
    def test_full_pass(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(
            d, config={"expected_outcome": "approved"}
        )
        assert r.passed
        assert r.meta["decision_outcome"] is True
        assert r.meta["provenance"] is True

    def test_outcome_mismatch(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(
            d, config={"expected_outcome": "denied"}
        )
        assert not r.passed
        assert r.meta["decision_outcome"] is False

    def test_outcome_from_expected_argument(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(d, expected="approved")
        assert r.passed
        assert r.meta["decision_outcome"] is True

    def test_outcome_mismatch_via_expected_argument(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(d, expected="denied")
        assert not r.passed
        assert r.meta["decision_outcome"] is False
        assert "decision_outcome" in r.meta["reasons"]

    def test_outcome_check_skipped_when_no_expected(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(d)
        assert "decision_outcome" not in r.meta

    def test_confidence_out_of_range(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}}, confidence=0.4)
        r = reg.get_evaluator("decision_scores")(
            d, config={"expected_outcome": "approved", "min_confidence": 0.8}
        )
        assert not r.passed
        assert r.meta["decision_confidence"] is False

    def test_missing_provenance_fails(self):
        d = _decision(metadata={})
        r = reg.get_evaluator("decision_scores")(d, config={"expected_outcome": "approved"})
        assert not r.passed
        assert r.meta["provenance"] is False

    def test_missing_required_fields(self):
        d = _decision(reasoning="")
        r = reg.get_evaluator("decision_scores")(d, config={"expected_outcome": "approved"})
        assert not r.passed
        assert r.meta["reasoning"] is False

    def test_dict_input_coerced(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        as_dict = d.to_dict()
        r = reg.get_evaluator("decision_scores")(
            as_dict, config={"expected_outcome": "approved"}
        )
        assert r.passed

    def test_malformed_dict_is_error_not_crash(self):
        r = reg.get_evaluator("decision_scores")({"foo": "bar"}, config={})
        assert not r.passed
        assert r.meta.get("error")

    def test_policy_compliance_check(self):
        class FakePolicyEngine:
            def check_compliance(self, decision, policy_id):
                return True

        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(
            d, config={
                "expected_outcome": "approved",
                "policy_engine": FakePolicyEngine(),
                "policy_id": "p1",
                "expected_policy_compliant": True,
            }
        )
        assert r.meta["policy"] is True

    def test_policy_mismatch_fails(self):
        class FakePolicyEngine:
            def check_compliance(self, decision, policy_id):
                return False

        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}})
        r = reg.get_evaluator("decision_scores")(
            d, config={
                "policy_engine": FakePolicyEngine(),
                "policy_id": "p1",
                "expected_policy_compliant": True,
            }
        )
        assert not r.passed
        assert r.meta["policy"] is False

    def test_causal_chain_gate(self):
        d = _decision(metadata={"provenance": {"prov_record": "rid-1"}}, decision_id="only-decision")
        with pytest.raises(NotImplementedError):
            reg.get_evaluator("decision_scores")(
                d, config={"causal_chain_exists": True, "graph_store": object()}
            )
