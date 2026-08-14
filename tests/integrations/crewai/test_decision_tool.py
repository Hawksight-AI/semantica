"""
Tests for SemanticaDecisionTool — decision intelligence CrewAI tool.

Runs with the crewai stubs installed by conftest, so ``CREWAI_AVAILABLE`` is
``True`` and the real Pydantic/BaseTool subclassing path is exercised.  A
MagicMock ``AgentContext`` is used so no vector store / faiss is required.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from integrations.crewai import SemanticaDecisionTool
from integrations.crewai.decision_tool import (
    CREWAI_AVAILABLE,
    SemanticaDecisionToolInput,
)


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.record_decision.return_value = "dec-test-001"
    ctx.find_precedents_advanced.return_value = [
        {
            "scenario": "past loan",
            "outcome": "approved",
            "confidence": 0.9,
            "category": "loan",
        }
    ]
    ctx.analyze_decision_influence.return_value = {"centrality": 0.75, "influenced": 3}
    ctx.knowledge_graph = MagicMock()
    ctx.knowledge_graph.trace_decision_causality = MagicMock(
        return_value=["step1", "step2"]
    )
    return ctx


class TestSemanticaDecisionToolInit(unittest.TestCase):

    def test_crewai_available_via_stub(self):
        self.assertTrue(CREWAI_AVAILABLE)

    def test_is_base_tool_subclass(self):
        from crewai.tools import BaseTool

        self.assertTrue(issubclass(SemanticaDecisionTool, BaseTool))

    def test_creates_with_explicit_context(self):
        ctx = _make_context()
        tool = SemanticaDecisionTool(context=ctx)
        self.assertIs(tool.context, ctx)

    def test_creates_context_when_none(self):
        tool = SemanticaDecisionTool()
        self.assertIsNotNone(tool.context)

    def test_default_metadata(self):
        tool = SemanticaDecisionTool(context=_make_context())
        self.assertEqual(tool.name, "semantica_decision")
        self.assertTrue(tool.description)
        self.assertEqual(tool.args_schema, SemanticaDecisionToolInput)

    def test_input_schema_validates(self):
        inp = SemanticaDecisionToolInput(action="record_decision", confidence=0.5)
        self.assertEqual(inp.confidence, 0.5)
        with self.assertRaises(Exception):
            SemanticaDecisionToolInput(action="bogus")

    def test_max_precedents_and_causal_depth_defaults(self):
        tool = SemanticaDecisionTool(context=_make_context())
        self.assertEqual(tool.max_precedents, 5)
        self.assertEqual(tool.causal_depth, 3)


class TestRecordDecision(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.tool = SemanticaDecisionTool(context=self.ctx)

    def test_returns_json_with_decision_id(self):
        result = json.loads(
            self.tool._run(
                action="record_decision",
                category="loan",
                scenario="Customer A loan application",
                reasoning="Good credit score 740",
                outcome="approved",
                confidence=0.95,
            )
        )
        self.assertEqual(result["decision_id"], "dec-test-001")
        self.assertEqual(result["status"], "recorded")

    def test_delegates_to_context(self):
        self.tool._run(
            action="record_decision",
            category="content",
            scenario="Moderation check",
            reasoning="No violations",
            outcome="allowed",
            confidence=0.88,
        )
        self.ctx.record_decision.assert_called_once()

    def test_parses_entities_string(self):
        self.tool._run(
            action="record_decision",
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
        result = json.loads(
            self.tool._run(
                action="record_decision",
                category="x",
                scenario="y",
                reasoning="z",
                outcome="failed",
            )
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("error", result)

    def test_default_confidence_used(self):
        self.tool._run(
            action="record_decision",
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
        self.tool = SemanticaDecisionTool(context=self.ctx)

    def test_returns_json_with_precedents(self):
        result = json.loads(
            self.tool._run(action="find_precedents", scenario="new loan application")
        )
        self.assertIn("precedents", result)
        self.assertIsInstance(result["precedents"], list)

    def test_count_in_result(self):
        result = json.loads(
            self.tool._run(action="find_precedents", scenario="test scenario")
        )
        self.assertEqual(result["count"], len(result["precedents"]))

    def test_category_filter_passed(self):
        self.tool._run(
            action="find_precedents", scenario="scenario", category="finance"
        )
        call_kwargs = self.ctx.find_precedents_advanced.call_args[1]
        self.assertEqual(call_kwargs.get("category"), "finance")

    def test_handles_exception_gracefully(self):
        self.ctx.find_precedents_advanced.side_effect = RuntimeError("fail")
        result = json.loads(self.tool._run(action="find_precedents", scenario="broken"))
        self.assertEqual(result["precedents"], [])
        self.assertIn("error", result)


class TestTraceCausalChain(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.tool = SemanticaDecisionTool(context=self.ctx)

    def test_returns_json_with_causal_chain(self):
        result = json.loads(
            self.tool._run(action="trace_causal_chain", decision_id="dec-001")
        )
        self.assertIn("causal_chain", result)
        self.assertEqual(result["decision_id"], "dec-001")

    def test_fallback_on_attribute_error(self):
        del self.ctx.knowledge_graph.trace_decision_causality
        self.ctx.knowledge_graph.find_precedents = MagicMock(return_value=[])
        result = json.loads(
            self.tool._run(action="trace_causal_chain", decision_id="dec-002")
        )
        self.assertIn("causal_chain", result)

    def test_depth_used(self):
        self.tool._run(action="trace_causal_chain", decision_id="dec-001", depth=5)
        self.ctx.knowledge_graph.trace_decision_causality.assert_called_once_with(
            "dec-001", depth=5
        )


class TestAnalyzeImpact(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.tool = SemanticaDecisionTool(context=self.ctx)

    def test_returns_json_with_decision_id(self):
        result = json.loads(
            self.tool._run(action="analyze_impact", decision_id="dec-001")
        )
        self.assertEqual(result["decision_id"], "dec-001")

    def test_includes_influence_metrics(self):
        result = json.loads(
            self.tool._run(action="analyze_impact", decision_id="dec-001")
        )
        self.assertIn("centrality", result)


class TestCheckPolicy(unittest.TestCase):

    def setUp(self):
        self.ctx = _make_context()
        self.tool = SemanticaDecisionTool(context=self.ctx)

    def test_returns_json_with_compliant_key(self):
        decision = json.dumps(
            {"category": "loan", "outcome": "approved", "confidence": 0.9}
        )
        result = json.loads(
            self.tool._run(action="check_policy", decision_data=decision)
        )
        self.assertIn("compliant", result)

    def test_invalid_json_returns_error(self):
        result = json.loads(
            self.tool._run(action="check_policy", decision_data="{not valid json}")
        )
        self.assertFalse(result["compliant"])
        self.assertGreater(len(result["violations"]), 0)

    def test_rule_violation_detected(self):
        decision = json.dumps({"confidence": 0.5})
        rules = json.dumps(["confidence >= 0.9"])
        result = json.loads(
            self.tool._run(
                action="check_policy", decision_data=decision, policy_rules=rules
            )
        )
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)

    def test_rule_missing_field_warns_not_silently_compliant(self):
        decision = json.dumps({"confidence": 0.95})
        rules = json.dumps(["minimum_score >= 0.9"])
        result = json.loads(
            self.tool._run(
                action="check_policy", decision_data=decision, policy_rules=rules
            )
        )
        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("minimum_score", result["warnings"][0])

    def test_decision_data_non_object_rejected(self):
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=json.dumps(["confidence", 0.95]),
                policy_rules=json.dumps(["confidence >= 0.9"]),
            )
        )
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)
        self.assertIn("JSON object", result["violations"][0])

    def test_unknown_action_returns_error(self):
        result = json.loads(self.tool._run(action="nope"))
        self.assertIn("error", result)

    def test_run_entrypoint(self):
        result = json.loads(
            self.tool.run(
                action="check_policy",
                decision_data=json.dumps({"confidence": 0.95}),
                policy_rules=json.dumps(["confidence >= 0.9"]),
            )
        )
        self.assertTrue(result["compliant"])


if __name__ == "__main__":
    unittest.main()
