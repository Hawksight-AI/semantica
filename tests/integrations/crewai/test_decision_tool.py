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


class TestSemanticaDecisionToolSerialization(unittest.TestCase):
    """CrewAI checkpoints serialise tools via ``model_dump(mode="json")`` — the
    live context must not break that (regression for PydanticSerializationError
    on arbitrary state objects)."""

    def test_model_dump_json_excludes_context(self):
        tool = SemanticaDecisionTool(context=_make_context())
        dumped = tool.model_dump(mode="json")
        self.assertNotIn("context", dumped)
        self.assertEqual(dumped["max_precedents"], 5)
        self.assertEqual(dumped["causal_depth"], 3)

    def test_model_validate_restores_defaults(self):
        tool = SemanticaDecisionTool(context=_make_context())
        restored = SemanticaDecisionTool.model_validate(tool.model_dump(mode="json"))
        self.assertIsNotNone(restored.context)
        self.assertEqual(restored.max_precedents, 5)
        self.assertEqual(restored.causal_depth, 3)

    def test_restore_flags_lost_live_state(self):
        """A tool restored from a checkpoint must signal that its live context
        was excluded and an empty one reconstructed (``reconstructed_state``)."""
        tool = SemanticaDecisionTool(context=_make_context())
        dumped = tool.model_dump(mode="json")
        self.assertTrue(dumped["had_live_state"])
        self.assertNotIn("reconstructed_state", dumped)
        restored = SemanticaDecisionTool.model_validate(dumped)
        self.assertTrue(restored.reconstructed_state)
        self.assertFalse(SemanticaDecisionTool().reconstructed_state)


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

    def test_malformed_confidence_returns_error_json(self):
        """A non-numeric confidence must not crash the tool — it is coerced
        inside ``_record_decision``'s error handling and reported as JSON."""
        for bad in ("high", None, "0.9"):
            result = json.loads(
                self.tool._run(
                    action="record_decision",
                    category="x",
                    scenario="y",
                    reasoning="z",
                    outcome="failed",
                    confidence=bad,
                )
            )
            if bad == "0.9":
                self.assertEqual(result["status"], "recorded")
            else:
                self.assertEqual(result["status"], "failed")
                self.assertIn("error", result)

    def test_missing_fields_get_sane_defaults(self):
        """record_decision must not hard-fail when the agent omits optional
        fields — category/reasoning/outcome get defaults."""
        result = json.loads(self.tool._run(action="record_decision"))
        self.assertEqual(result["status"], "recorded")
        call_kwargs = self.ctx.record_decision.call_args[1]
        self.assertEqual(call_kwargs["category"], "general")
        self.assertEqual(call_kwargs["scenario"], "decision recorded")
        self.assertEqual(call_kwargs["reasoning"], "agent decision")
        self.assertEqual(call_kwargs["outcome"], "recorded")


class TestRealAutoCreatedContext(unittest.TestCase):
    """The no-context path builds a real AgentContext with a knowledge graph so
    decision tracking is actually enabled (regression for the live
    'Decision tracking is not enabled' failure)."""

    def setUp(self):
        self.tool = SemanticaDecisionTool()

    def test_context_is_real_agent_context(self):
        from semantica.context import AgentContext

        self.assertIsInstance(self.tool.context, AgentContext)
        self.assertIsNotNone(self.tool.context.knowledge_graph)

    def test_record_decision_actually_records(self):
        result = json.loads(
            self.tool.run(
                action="record_decision",
                scenario="ship v2",
                reasoning="user demand",
                confidence=0.9,
            )
        )
        self.assertEqual(result["status"], "recorded")
        self.assertTrue(result["decision_id"])

    def test_find_precedents_runs_against_real_context(self):
        result = json.loads(self.tool.run(action="find_precedents", scenario="ship v2"))
        self.assertIn("precedents", result)

    def test_trace_causal_chain_runs_against_real_context(self):
        """Regression: trace_decision_causality takes ``max_depth``, not
        ``depth`` — must not raise against a real ContextGraph."""
        rec = json.loads(
            self.tool.run(
                action="record_decision",
                scenario="ship v2",
                reasoning="user demand",
                confidence=0.9,
            )
        )
        trace = json.loads(
            self.tool.run(action="trace_causal_chain", decision_id=rec["decision_id"])
        )
        self.assertIn("causal_chain", trace)
        self.assertEqual(trace["decision_id"], rec["decision_id"])


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

    def test_limit_propagated_to_backend(self):
        self.tool.max_precedents = 20
        self.tool._run(action="find_precedents", scenario="scenario")
        call_kwargs = self.ctx.find_precedents_advanced.call_args[1]
        self.assertEqual(call_kwargs.get("limit"), 20)

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

    def test_honest_error_when_causal_trace_unavailable(self):
        """When the graph cannot trace causality, the tool must say so — it
        must NOT substitute similarity-based precedents as a causal chain."""
        del self.ctx.knowledge_graph.trace_decision_causality
        result = json.loads(
            self.tool._run(action="trace_causal_chain", decision_id="dec-002")
        )
        self.assertEqual(result["causal_chain"], [])
        self.assertIn("error", result)
        self.ctx.knowledge_graph.find_precedents.assert_not_called()

    def test_missing_decision_id_reports_error(self):
        result = json.loads(self.tool._run(action="trace_causal_chain"))
        self.assertIn("error", result)
        self.assertEqual(result["causal_chain"], [])

    def test_depth_used(self):
        self.tool._run(action="trace_causal_chain", decision_id="dec-001", depth=5)
        self.ctx.knowledge_graph.trace_decision_causality.assert_called_once_with(
            "dec-001", max_depth=5
        )

    def test_graceful_error_when_context_has_no_knowledge_graph(self):
        """Regression: an unguarded ``self.context.knowledge_graph`` read raised
        AttributeError out of ``_run`` and could hard-fail a crew task. It must
        return honest error JSON instead."""
        del self.ctx.knowledge_graph
        result = json.loads(
            self.tool._run(action="trace_causal_chain", decision_id="dec-003")
        )
        self.assertEqual(result["causal_chain"], [])
        self.assertIn("error", result)


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

    def test_bool_false_rule_is_compliant(self):
        """Regression: ``enabled == false`` with ``enabled: false`` must be
        compliant — bool("false") is truthy, so the old coercion inverted it."""
        decision = json.dumps({"enabled": False, "confidence": 0.95})
        rules = json.dumps(["enabled == false"])
        result = json.loads(
            self.tool._run(
                action="check_policy", decision_data=decision, policy_rules=rules
            )
        )
        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])

    def test_bool_true_rule_is_compliant(self):
        decision = json.dumps({"enabled": True})
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=decision,
                policy_rules=json.dumps(["enabled == true"]),
            )
        )
        self.assertTrue(result["compliant"])

    def test_whitespace_padded_strings_are_trimmed(self):
        """Regression: ``_coerce_value`` must return the *stripped* string for
        non-numeric literals, or padded decision_data fields never match."""
        decision = json.dumps({"status": "  approved  "})
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=decision,
                policy_rules=json.dumps(["status == approved"]),
            )
        )
        self.assertTrue(result["compliant"])
        self.assertEqual(result["violations"], [])

    def test_bool_false_rule_violated_when_true(self):
        decision = json.dumps({"enabled": True})
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=decision,
                policy_rules=json.dumps(["enabled == false"]),
            )
        )
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["violations"]), 1)

    def test_zero_one_flag_parsed_as_bool(self):
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=json.dumps({"flag": 1}),
                policy_rules=json.dumps(["flag != 0"]),
            )
        )
        self.assertTrue(result["compliant"])
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=json.dumps({"flag": 0}),
                policy_rules=json.dumps(["flag != 0"]),
            )
        )
        self.assertFalse(result["compliant"])

    def test_numeric_string_value_compared_numerically(self):
        """Regression: a string datum like "0.90" must compare numerically to
        rule literal 0.9, not lexicographically."""
        decision = json.dumps({"score": "0.90"})
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=decision,
                policy_rules=json.dumps(["score == 0.9"]),
            )
        )
        self.assertTrue(result["compliant"])

    def test_numeric_string_ordering(self):
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=json.dumps({"pct": "0.95"}),
                policy_rules=json.dumps(["pct >= 0.9"]),
            )
        )
        self.assertTrue(result["compliant"])
        result = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=json.dumps({"pct": "0.85"}),
                policy_rules=json.dumps(["pct >= 0.9"]),
            )
        )
        self.assertFalse(result["compliant"])

    def test_field_names_with_hyphens_dots_spaces(self):
        """Rule field names are not limited to ``\\w+`` — hyphenated/dotted
        (and space-containing) JSON keys must be addressable."""
        decision = json.dumps({"risk-score": 0.95, "max.risk": 0.2, "min score": 0.4})
        compliant = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=decision,
                policy_rules=json.dumps(
                    ["risk-score >= 0.9", "max.risk <= 0.5", "min score >= 0.3"]
                ),
            )
        )
        self.assertTrue(compliant["compliant"])
        self.assertEqual(compliant["violations"], [])
        violated = json.loads(
            self.tool._run(
                action="check_policy",
                decision_data=decision,
                policy_rules=json.dumps(["max.risk >= 0.5"]),
            )
        )
        self.assertFalse(violated["compliant"])
        self.assertEqual(len(violated["violations"]), 1)

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
