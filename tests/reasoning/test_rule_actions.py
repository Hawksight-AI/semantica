"""Tests for rule-driven actions (production-rule behaviour) on the Reasoner.

Covers the L1 Action layer (Assert/Retract/Call/Emit), provenance logging of
fired actions (L2), and backward compatibility with the legacy Rule.handler
callback.
"""

import unittest

from semantica.reasoning import (
    AssertAction,
    CallAction,
    EmitEventAction,
    Reasoner,
    RetractAction,
)


class TestRuleActions(unittest.TestCase):
    def setUp(self):
        self.reasoner = Reasoner()

    def _add_person_parent_facts(self):
        self.reasoner.add_fact("Person(John)")
        self.reasoner.add_fact("Parent(John, Jane)")

    def test_assert_action_fires_and_substitutes_bindings(self):
        rule = self.reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.actions = [AssertAction("Adult(?x)")]
        self._add_person_parent_facts()

        self.reasoner.forward_chain()

        # Action-asserted fact uses the match bindings (?x -> John).
        self.assertIn("Adult(John)", self.reasoner.facts)

    def test_retract_action_removes_fact(self):
        rule = self.reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.actions = [RetractAction("Person(?x)")]
        self._add_person_parent_facts()

        self.reasoner.forward_chain()

        self.assertNotIn("Person(John)", self.reasoner.facts)

    def test_call_action_invoked_with_bindings(self):
        seen = {}

        def record(bindings, reasoner):
            seen.update(bindings)

        rule = self.reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.actions = [CallAction(record, name="record")]
        self._add_person_parent_facts()

        self.reasoner.forward_chain()

        self.assertEqual(seen.get("x"), "John")
        self.assertEqual(seen.get("y"), "Jane")

    def test_emit_event_action_delivers_to_sink(self):
        events = []
        self.reasoner.on_event(lambda name, payload: events.append((name, payload)))

        rule = self.reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.actions = [EmitEventAction("child_derived:?y")]
        self._add_person_parent_facts()

        self.reasoner.forward_chain()

        self.assertEqual(len(events), 1)
        name, payload = events[0]
        self.assertEqual(name, "child_derived:Jane")
        self.assertEqual(payload["bindings"]["x"], "John")

    def test_assert_action_write_back_to_knowledge_graph(self):
        class FakeKG:
            def __init__(self):
                self.added = []

            def add_fact(self, fact):
                self.added.append(fact)

        kg = FakeKG()
        reasoner = Reasoner(knowledge_graph=kg)
        rule = reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.actions = [AssertAction("Adult(?x)", write_back=True)]
        reasoner.add_fact("Person(John)")
        reasoner.add_fact("Parent(John, Jane)")

        reasoner.forward_chain()

        self.assertIn("Adult(John)", kg.added)

    def test_provenance_logs_fired_actions(self):
        reasoner = Reasoner(provenance=True)
        rule = reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.actions = [AssertAction("Adult(?x)")]
        reasoner.add_fact("Person(John)")
        reasoner.add_fact("Parent(John, Jane)")

        reasoner.forward_chain()

        self.assertEqual(len(reasoner.action_log), 1)
        entry = reasoner.action_log[0]
        self.assertEqual(entry["action"], "AssertAction")
        self.assertEqual(entry["rule_id"], rule.rule_id)
        self.assertEqual(entry["bindings"]["x"], "John")
        self.assertIn("Adult(John)", entry["description"])

    def test_no_provenance_log_when_disabled(self):
        rule = self.reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.actions = [AssertAction("Adult(?x)")]
        self._add_person_parent_facts()

        self.reasoner.forward_chain()

        self.assertEqual(self.reasoner.action_log, [])

    def test_legacy_handler_still_invoked(self):
        calls = []

        rule = self.reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.handler = lambda bindings, reasoner: calls.append(bindings)
        self._add_person_parent_facts()

        self.reasoner.forward_chain()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["x"], "John")

    def test_action_error_does_not_break_chain(self):
        def boom(bindings, reasoner):
            raise RuntimeError("boom")

        rule = self.reasoner.add_rule(
            "IF Person(?x) AND Parent(?x, ?y) THEN Child(?y, ?x)"
        )
        rule.actions = [CallAction(boom, name="boom"), AssertAction("Adult(?x)")]
        self._add_person_parent_facts()

        # A failing action is logged but must not abort the pass; the later
        # action still runs and the conclusion is still derived.
        self.reasoner.forward_chain()

        self.assertIn("Adult(John)", self.reasoner.facts)
        self.assertIn("Child(Jane, John)", self.reasoner.facts)


if __name__ == "__main__":
    unittest.main()