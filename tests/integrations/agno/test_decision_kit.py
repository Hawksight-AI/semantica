"""
Tests for AgnoDecisionKit — decision intelligence Agno Toolkit.
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stub agno Toolkit
# ---------------------------------------------------------------------------
def _stub_agno() -> None:
    if "agno" in sys.modules:
        return

    agno = types.ModuleType("agno")

    tools_pkg = types.ModuleType("agno.tools")
    tools_toolkit = types.ModuleType("agno.tools.toolkit")

    class Toolkit:
        def __init__(self, name="toolkit", **kw):
            self.name = name
            self._tools = []

        def register(self, fn):
            self._tools.append(fn)

    tools_toolkit.Toolkit = Toolkit  # type: ignore
    tools_pkg.toolkit = tools_toolkit
    agno.tools = tools_pkg  # type: ignore

    for name, mod in [
        ("agno", agno),
        ("agno.tools", tools_pkg),
        ("agno.tools.toolkit", tools_toolkit),
    ]:
        sys.modules.setdefault(name, mod)


_stub_agno()

from integrations.agno.decision_kit import AgnoDecisionKit  # noqa: E402


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.record_decision.return_value = "dec-test-001"
    ctx.find_precedents_advanced.return_value = [
        {"scenario": "past loan", "outcome": "approved", "confidence": 0.9, "category": "loan"}
    ]
    ctx.analyze_decision_influence.return_value = {"centrality": 0.75, "influenced": 3}
    ctx.get_context_insights.return_value = {"total_decisions": 5, "categories": ["loan"]}
    ctx.knowledge_graph = MagicMock()
    ctx.knowledge_graph.trace_decision_causality = MagicMock(return_value=["step1", "step2"])
    return ctx


class TestAgnoDecisionKitInit(unittest.TestCase):

    def test_creates_with_context(self):
        kit = AgnoDecisionKit(context=_make_context())
        self.assertIsNotNone(kit)

    def test_creates_without_context(self):
        # Should auto-create an AgentContext
        kit = AgnoDecisionKit()
        self.assertIsNotNone(kit)

    def test_tools_registered(self):
        kit = AgnoDecisionKit(context=_make_context())
        # Tools should be registered (Toolkit.register was called)
        self.assertEqual(len(kit._tools), 6)
        self.assertEqual(len(kit._tools), len(set(kit._tools)))

    def test_registration_invoked(self):
        with patch.object(AgnoDecisionKit, "register") as mock_register:
            AgnoDecisionKit(context=_make_context())
            self.assertEqual(mock_register.call_count, 6)

    def test_registration_failure_propagates(self):
        with patch.object(AgnoDecisionKit, "register", side_effect=RuntimeError("Registration failed")):
            with self.assertRaises(RuntimeError):
                AgnoDecisionKit(context=_make_context())

    def test_graceful_degradation_when_agno_unavailable(self):
        with patch("integrations.agno.decision_kit.AGNO_AVAILABLE", False):
            with patch.object(AgnoDecisionKit, "register") as mock_register:
                kit = AgnoDecisionKit(context=_make_context())
                mock_register.assert_not_called()
                self.assertEqual(len(kit._tools), 6)
                self.assertEqual(len(kit._tools), len(set(kit._tools)))

    def test_no_duplicate_tools(self):
        kit = AgnoDecisionKit(context=_make_context())
        self.assertEqual(len(kit._tools), len(set(kit._tools)))
        self.assertEqual(len(kit._tools), 6)

    def test_policy_tool_can_be_disabled(self):
        kit = AgnoDecisionKit(context=_make_context(), enable_policy_check=False)
        tool_names = [fn.__name__ for fn in kit._tools]
        self.assertNotIn("check_policy", tool_names)


class TestRecordDecision(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.kit = AgnoDecisionKit(context=self.ctx)

    def test_returns_json_with_decision_id(self):
        result = json.loads(self.kit.record_decision(
            category="loan",
            scenario="Customer A loan application",
            reasoning="Good credit score 740",
            outcome="approved",
            confidence=0.95,
        ))
        self.assertIn("decision_id", result)
        self.assertEqual(result["status"], "recorded")

    def test_delegates_to_context(self):
        self.kit.record_decision(
            category="content",
            scenario="Moderation check",
            reasoning="No violations",
            outcome="allowed",
            confidence=0.88,
        )
        self.ctx.record_decision.assert_called_once()

    def test_parses_entities_string(self):
        self.kit.record_decision(
            category="hr",
            scenario="Hire decision",
            reasoning="Qualified",
            outcome="hired",
            confidence=0.9,
            entities="Alice, ACME Corp, Senior Engineer",
        )
        call_kwargs = self.ctx.record_decision.call_args[1]
        self.assertIsInstance(call_kwargs["entities"], list)
        self.assertEqual(len(call_kwargs["entities"]), 3)

    def test_returns_error_json_on_failure(self):
        self.ctx.record_decision.side_effect = RuntimeError("DB unavailable")
        result = json.loads(self.kit.record_decision(
            category="x", scenario="y", reasoning="z", outcome="failed",
        ))
        self.assertEqual(result["status"], "failed")
        self.assertIn("error", result)

    def test_default_confidence_used(self):
        self.kit.record_decision(
            category="test",
            scenario="Default confidence test",
            reasoning="N/A",
            outcome="pass",
        )
        call_kwargs = self.ctx.record_decision.call_args[1]
        self.assertEqual(call_kwargs["confidence"], 0.8)


class TestFindPrecedents(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.kit = AgnoDecisionKit(context=self.ctx)

    def test_returns_json_with_precedents(self):
        result = json.loads(self.kit.find_precedents("new loan application"))
        self.assertIn("precedents", result)
        self.assertIsInstance(result["precedents"], list)

    def test_count_in_result(self):
        result = json.loads(self.kit.find_precedents("test scenario"))
        self.assertIn("count", result)
        self.assertEqual(result["count"], len(result["precedents"]))

    def test_category_filter_passed(self):
        self.kit.find_precedents("scenario", category="finance")
        call_kwargs = self.ctx.find_precedents_advanced.call_args[1]
        self.assertEqual(call_kwargs.get("category"), "finance")

    def test_limit_applied(self):
        self.ctx.find_precedents_advanced.return_value = [
            {"scenario": f"s{i}", "outcome": "o", "confidence": 0.5, "category": "c"}
            for i in range(10)
        ]
        result = json.loads(self.kit.find_precedents("s", limit=3))
        self.assertTrue(result["count"] <= 3)

    def test_handles_exception_gracefully(self):
        self.ctx.find_precedents_advanced.side_effect = RuntimeError("fail")
        result = json.loads(self.kit.find_precedents("broken"))
        self.assertEqual(result["precedents"], [])
        self.assertIn("error", result)


class TestTraceCausalChain(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.kit = AgnoDecisionKit(context=self.ctx)

    def test_returns_json_with_causal_chain(self):
        result = json.loads(self.kit.trace_causal_chain("dec-001"))
        self.assertIn("causal_chain", result)
        self.assertEqual(result["decision_id"], "dec-001")

    def test_fallback_on_attribute_error(self):
        del self.ctx.knowledge_graph.trace_decision_causality
        self.ctx.knowledge_graph.find_precedents = MagicMock(return_value=[])
        result = json.loads(self.kit.trace_causal_chain("dec-002"))
        self.assertIn("causal_chain", result)

    def test_depth_passed(self):
        self.kit.trace_causal_chain("dec-001", depth=5)
        # Should not raise


class TestAnalyzeImpact(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.kit = AgnoDecisionKit(context=self.ctx)

    def test_returns_json_with_decision_id(self):
        result = json.loads(self.kit.analyze_impact("dec-001"))
        self.assertEqual(result["decision_id"], "dec-001")

    def test_includes_influence_metrics(self):
        result = json.loads(self.kit.analyze_impact("dec-001"))
        self.assertIn("centrality", result)


class TestCheckPolicy(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.kit = AgnoDecisionKit(context=self.ctx)

    def test_returns_json_with_compliant_key(self):
        decision = json.dumps({"category": "loan", "outcome": "approved", "confidence": 0.9})
        result = json.loads(self.kit.check_policy(decision))
        self.assertIn("compliant", result)

    def test_invalid_json_returns_error(self):
        result = json.loads(self.kit.check_policy("{not valid json}"))
        # Implementation returns {"compliant": False, "violations": [...], "warnings": [...]}
        self.assertFalse(result["compliant"])
        violations = result.get("violations", [])
        self.assertGreater(len(violations), 0)

    def test_decision_data_list_rejected_with_clear_violation(self):
        # decision_data decoding to a list previously passed the isinstance
        # check silently, then `field not in data` did list-membership
        # (not key) testing and `data[field]` raised a raw, confusing
        # TypeError deep inside _eval_rule. Must now be rejected upfront.
        result = json.loads(self.kit.check_policy(
            json.dumps(["confidence", 0.95]),
            json.dumps(["confidence >= 0.9"]),
        ))
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertIn("JSON object", result["violations"][0])
        self.assertEqual(result["warnings"], [])

    def test_decision_data_number_rejected_with_clear_violation(self):
        result = json.loads(self.kit.check_policy(
            json.dumps(42),
            json.dumps(["confidence >= 0.9"]),
        ))
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertIn("JSON object", result["violations"][0])

    def test_decision_data_string_rejected_with_clear_violation(self):
        result = json.loads(self.kit.check_policy(
            json.dumps("confidence"),
            json.dumps(["confidence >= 0.9"]),
        ))
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertIn("JSON object", result["violations"][0])

    def test_decision_data_bool_rejected_with_clear_violation(self):
        result = json.loads(self.kit.check_policy(
            json.dumps(True),
            json.dumps(["confidence >= 0.9"]),
        ))
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertIn("JSON object", result["violations"][0])

    def test_decision_data_null_rejected_with_clear_violation(self):
        result = json.loads(self.kit.check_policy(
            json.dumps(None),
            json.dumps(["confidence >= 0.9"]),
        ))
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertIn("JSON object", result["violations"][0])

    def test_rule_referencing_missing_field_warns_not_silently_compliant(self):
        # Issue #778 traced example: rule references a field absent from the
        # decision payload. This must NOT be silently treated as compliant
        # with no signal — it should surface in `warnings`.
        decision = json.dumps({"confidence": 0.95})
        rules = json.dumps(["minimum_score >= 0.9"])
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("minimum_score", result["warnings"][0])
        self.assertIn("minimum_score >= 0.9", result["warnings"][0])

    def test_malformed_rule_string_warns_not_silently_compliant(self):
        # A rule that doesn't match `<field> <op> <value>` must also warn
        # instead of silently passing through as compliant.
        decision = json.dumps({"confidence": 0.95})
        rules = json.dumps(["not a valid rule!!!"])
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("not a valid rule!!!", result["warnings"][0])

    def test_valid_rule_against_present_field_still_evaluates_normally(self):
        # Sanity check: a rule referencing a field that IS present is
        # unaffected by the missing-field fix and evaluates as before.
        decision = json.dumps({"confidence": 0.95})
        rules = json.dumps(["confidence >= 0.9"])
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["warnings"], [])

    def test_valid_rule_violation_against_present_field(self):
        decision = json.dumps({"confidence": 0.5})
        rules = json.dumps(["confidence >= 0.9"])
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertEqual(result["warnings"], [])

    def test_bare_json_string_policy_rules_treated_as_single_rule(self):
        # policy_rules='"confidence >= 0.9"' decodes to a plain str via
        # json.loads. Must be treated as ONE rule, not iterated character
        # by character (which previously produced one warning per char).
        decision = json.dumps({"confidence": 0.95})
        rules = json.dumps("confidence >= 0.9")  # -> '"confidence >= 0.9"'
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["warnings"], [])

    def test_bare_json_string_policy_rules_missing_field_warns_once(self):
        decision = json.dumps({"confidence": 0.95})
        rules = json.dumps("minimum_score >= 0.9")
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("minimum_score", result["warnings"][0])

    def test_non_list_non_string_policy_rules_produces_single_warning(self):
        # policy_rules is valid JSON but decodes to a number/object, not a
        # list of rule strings. Must produce exactly one warning, not crash
        # or silently no-op.
        decision = json.dumps({"confidence": 0.95})
        rules = json.dumps(42)
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("policy_rules", result["warnings"][0])

    def test_non_string_list_elements_warn_and_are_skipped(self):
        # A list containing a non-string entry should warn about that entry
        # specifically and continue evaluating the valid string entries.
        decision = json.dumps({"confidence": 0.5})
        rules = json.dumps(["confidence >= 0.9", 123, None])
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertEqual(len(result["warnings"]), 2)

    def test_missing_key_and_null_value_produce_distinct_warnings(self):
        # dict.get(field) can't distinguish an absent key from a key present
        # with JSON null. `minimum_score` is truly absent; `flagged_reason`
        # is present but explicitly null. Both are unevaluable, but the
        # warning text must say something different for each so the
        # diagnosis is accurate rather than always claiming "undefined".
        decision = json.dumps({"confidence": 0.95, "flagged_reason": None})
        rules = json.dumps(["minimum_score >= 0.9", "flagged_reason != none"])
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(len(result["warnings"]), 2)

        missing_warning = next(w for w in result["warnings"] if "minimum_score" in w)
        null_warning = next(w for w in result["warnings"] if "flagged_reason" in w)

        self.assertIn("undefined field", missing_warning)
        self.assertNotIn("undefined field", null_warning)
        self.assertIn("null", null_warning)

    def test_field_present_with_null_value_alone(self):
        decision = json.dumps({"score": None})
        rules = json.dumps(["score >= 0.9"])
        result = json.loads(self.kit.check_policy(decision, policy_rules=rules))

        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("null", result["warnings"][0])
        self.assertNotIn("undefined field", result["warnings"][0])


class TestGetDecisionSummary(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.kit = AgnoDecisionKit(context=self.ctx)

    def test_returns_json(self):
        result_str = self.kit.get_decision_summary()
        result = json.loads(result_str)
        self.assertIsInstance(result, dict)

    def test_category_filter_stored(self):
        result = json.loads(self.kit.get_decision_summary(category="finance"))
        self.assertEqual(result.get("category_filter"), "finance")

    def test_handles_exception_gracefully(self):
        self.ctx.get_context_insights.side_effect = RuntimeError("insight fail")
        result = json.loads(self.kit.get_decision_summary())
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
