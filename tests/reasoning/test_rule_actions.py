"""Tests for rule-driven actions (production-rule behaviour) on the Reasoner.

Covers the L1 Action layer (Assert/Retract/Call/Emit), provenance logging of
fired actions (L2), and backward compatibility with the legacy Rule.handler
callback.
"""

import unittest
from collections import UserDict

from semantica.reasoning import (
    AssertAction,
    CallAction,
    EmitEventAction,
    Fact,
    Match,
    Reasoner,
    ReteEngine,
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

    def test_repeated_forward_chain_fires_same_activation_once(self):
        calls = []

        rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [
            CallAction(lambda bindings, reasoner: calls.append(dict(bindings)))
        ]
        self.reasoner.add_fact("Person(John)")

        self.reasoner.forward_chain()
        self.reasoner.forward_chain()

        self.assertEqual(calls, [{"x": "John"}])

    def test_repeated_forward_chain_records_provenance_once(self):
        reasoner = Reasoner(provenance=True)
        rule = reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [AssertAction("Verified(?x)")]
        reasoner.add_fact("Person(John)")

        reasoner.forward_chain()
        reasoner.forward_chain()

        self.assertEqual(len(reasoner.action_log), 1)

    def test_new_binding_creates_a_new_activation(self):
        calls = []
        rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [
            CallAction(lambda bindings, reasoner: calls.append(bindings["x"]))
        ]
        self.reasoner.add_fact("Person(John)")

        self.reasoner.forward_chain()
        self.reasoner.add_fact("Person(Jane)")
        self.reasoner.forward_chain()

        self.assertCountEqual(calls, ["John", "Jane"])

    def test_reset_action_history_allows_deliberate_replay(self):
        calls = []
        rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [CallAction(lambda bindings, reasoner: calls.append("called"))]
        self.reasoner.add_fact("Person(John)")

        self.reasoner.forward_chain()
        self.reasoner.reset_action_history()
        self.reasoner.forward_chain()

        self.assertEqual(calls, ["called", "called"])

    def test_clear_resets_action_history(self):
        calls = []
        rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [CallAction(lambda bindings, reasoner: calls.append("called"))]
        self.reasoner.add_fact("Person(John)")
        self.reasoner.forward_chain()

        self.reasoner.clear()
        rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [CallAction(lambda bindings, reasoner: calls.append("called"))]
        self.reasoner.add_fact("Person(John)")
        self.reasoner.forward_chain()

        self.assertEqual(calls, ["called", "called"])

    def test_failed_action_is_not_retried_without_explicit_reset(self):
        attempts = []

        def fail(bindings, reasoner):
            attempts.append(bindings["x"])
            raise RuntimeError("boom")

        rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [CallAction(fail)]
        self.reasoner.add_fact("Person(John)")

        self.reasoner.forward_chain()
        self.reasoner.forward_chain()
        self.assertEqual(attempts, ["John"])

        self.reasoner.reset_action_history()
        self.reasoner.forward_chain()
        self.assertEqual(attempts, ["John", "John"])

    def test_replacing_actions_in_place_requires_explicit_history_reset(self):
        calls = []
        rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [CallAction(lambda bindings, reasoner: calls.append("first"))]
        self.reasoner.add_fact("Person(John)")
        self.reasoner.forward_chain()

        rule.actions = [CallAction(lambda bindings, reasoner: calls.append("second"))]
        self.reasoner.forward_chain()
        self.assertEqual(calls, ["first"])

        self.reasoner.reset_action_history()
        self.reasoner.forward_chain()
        self.assertEqual(calls, ["first", "second"])

    def test_activation_is_recorded_before_reentrant_action_execution(self):
        calls = []

        def reenter(bindings, reasoner):
            calls.append(bindings["x"])
            if len(calls) == 1:
                reasoner.forward_chain()

        rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [CallAction(reenter)]
        self.reasoner.add_fact("Person(John)")

        self.reasoner.forward_chain()

        self.assertEqual(calls, ["John"])

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


class TestRuleActionRegressions(unittest.TestCase):
    """Regression coverage for the qodo-flagged bugs on PR #1096."""

    def test_variable_substitution_no_prefix_collision(self):
        # bug7: naive str.replace of "?x" would also corrupt "?xy". A
        # token-aware substitution must bind ?x and ?xy independently.
        reasoner = Reasoner()
        rule = reasoner.add_rule("IF Pair(?x, ?xy) THEN Linked(?x, ?xy)")
        rule.actions = [AssertAction("Tag(?x, ?xy)")]
        reasoner.add_fact("Pair(John, Johny)")

        reasoner.forward_chain()

        self.assertIn("Tag(John, Johny)", reasoner.facts)

    def test_assert_write_back_to_canonical_knowledge_graph(self):
        # bug1: a KG exposing only entities/relationships (no add_fact) must
        # still receive the asserted fact via canonical translation.
        from semantica.kg.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()
        reasoner = Reasoner(knowledge_graph=kg)
        rule = reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [AssertAction("Adult(?x)", write_back=True)]
        reasoner.add_fact("Person(John)")

        reasoner.forward_chain()

        # A single-argument fact lands as an entity node.
        self.assertTrue(any("John" in str(e) for e in kg.entities))

    def test_write_back_unsupported_target_raises(self):
        # bug1: an unsupported write-back target must fail loudly, not silently.
        from semantica.reasoning.reasoner import _write_fact_to_graph

        with self.assertRaises(ValueError):
            _write_fact_to_graph(object(), "Adult(John)")

    def test_provenance_entry_has_timestamp(self):
        # bug3: action_log entries must be structured with a timestamp.
        reasoner = Reasoner(provenance=True)
        rule = reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [AssertAction("Adult(?x)")]
        reasoner.add_fact("Person(John)")

        reasoner.forward_chain()

        entry = reasoner.action_log[0]
        self.assertIn("timestamp", entry)
        self.assertTrue(entry["timestamp"])

    def test_action_fires_even_when_conclusion_already_known(self):
        # bug4: previously an activation whose conclusion was already known
        # skipped firing its actions. Now it must still fire exactly once.
        reasoner = Reasoner()
        rule = reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [AssertAction("Verified(?x)")]
        reasoner.add_fact("Person(John)")
        # Conclusion already present before the pass runs.
        reasoner.add_fact("Adult(John)")

        reasoner.forward_chain()

        self.assertIn("Verified(John)", reasoner.facts)

    def test_retract_self_conclusion_terminates(self):
        # bug5: a RetractAction removing its own premise previously re-fired
        # every pass up to max_iterations. It must fire once and terminate.
        reasoner = Reasoner()
        rule = reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.actions = [RetractAction("Person(?x)")]
        reasoner.add_fact("Person(John)")

        # Should return promptly without exhausting iterations.
        reasoner.forward_chain()

        self.assertNotIn("Person(John)", reasoner.facts)

    def test_infer_with_results_preserves_confidence(self):
        # bug9: confidence must survive to the InferenceResult objects.
        reasoner = Reasoner()
        rule = reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        rule.confidence = 0.8

        results = reasoner.infer_with_results(["Person(John)"])

        self.assertTrue(results)
        self.assertTrue(all(0.0 <= r.confidence <= 1.0 for r in results))
        self.assertAlmostEqual(
            min(r.confidence for r in results), 0.8, places=6
        )


class TestReteActionExecution(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.reasoner = Reasoner()
        self.rule = self.reasoner.add_rule("IF Person(?x) THEN Adult(?x)")
        self.rule.actions = [
            CallAction(
                lambda bindings, reasoner: self.calls.append(dict(bindings))
            )
        ]
        self.match = Match(
            rule=self.rule,
            facts=[Fact("person-1", "Person", ["John"])],
            bindings={"x": "John"},
        )
        self.engine = ReteEngine(reasoner=self.reasoner)

    def test_rete_repeated_execute_matches_fires_activation_once(self):
        first_results = self.engine.execute_matches([self.match])
        second_results = self.engine.execute_matches([self.match])

        self.assertEqual(first_results, ["Adult(?x)"])
        self.assertEqual(second_results, ["Adult(?x)"])
        self.assertEqual(self.calls, [{"x": "John"}])

    def test_rete_duplicate_match_preserves_results_but_fires_once(self):
        results = self.engine.execute_matches([self.match, self.match])

        self.assertEqual(results, ["Adult(?x)", "Adult(?x)"])
        self.assertEqual(self.calls, [{"x": "John"}])

    def test_rete_distinct_fact_ids_create_distinct_activations(self):
        other_match = Match(
            rule=self.rule,
            facts=[Fact("person-2", "Person", ["John"])],
            bindings={"x": "John"},
        )

        self.engine.execute_matches([self.match])
        self.engine.execute_matches([other_match])

        self.assertEqual(self.calls, [{"x": "John"}, {"x": "John"}])

    def test_rete_equivalent_nested_bindings_share_an_activation(self):
        first_match = Match(
            rule=self.rule,
            facts=self.match.facts,
            bindings={"x": {"a": 1, "b": 2}},
        )
        reordered_match = Match(
            rule=self.rule,
            facts=self.match.facts,
            bindings={"x": {"b": 2, "a": 1}},
        )

        self.engine.execute_matches([first_match])
        self.engine.execute_matches([reordered_match])

        self.assertEqual(len(self.calls), 1)

    def test_rete_structured_fact_identity_avoids_separator_collisions(self):
        first_match = Match(
            rule=self.rule,
            facts=[Fact("a", "b:C", [])],
            bindings={"x": "John"},
        )
        colliding_text_match = Match(
            rule=self.rule,
            facts=[Fact("a:b", "C", [])],
            bindings={"x": "John"},
        )

        self.engine.execute_matches([first_match])
        self.engine.execute_matches([colliding_text_match])

        self.assertEqual(len(self.calls), 2)

    def test_rete_cyclic_binding_preserves_results_and_deduplicates_actions(self):
        cyclic_value = []
        cyclic_value.append(cyclic_value)
        cyclic_match = Match(
            rule=self.rule,
            facts=self.match.facts,
            bindings={"x": cyclic_value},
        )

        first_results = self.engine.execute_matches([cyclic_match])
        second_results = self.engine.execute_matches([cyclic_match])

        self.assertEqual(first_results, ["Adult(?x)"])
        self.assertEqual(second_results, ["Adult(?x)"])
        self.assertEqual(len(self.calls), 1)

    def test_rete_equivalent_mapping_implementations_share_an_activation(self):
        first_match = Match(
            rule=self.rule,
            facts=self.match.facts,
            bindings={"x": UserDict({"a": 1, "b": 2})},
        )
        reordered_match = Match(
            rule=self.rule,
            facts=self.match.facts,
            bindings={"x": UserDict({"b": 2, "a": 1})},
        )

        self.engine.execute_matches([first_match])
        self.engine.execute_matches([reordered_match])

        self.assertEqual(len(self.calls), 1)

    def test_rete_key_error_does_not_suppress_conclusion(self):
        class UnrepresentableValue:
            def __repr__(self):
                raise RuntimeError("cannot represent")

        invalid_match = Match(
            rule=self.rule,
            facts=self.match.facts,
            bindings={"x": UnrepresentableValue()},
        )

        results = self.engine.execute_matches([invalid_match])

        self.assertEqual(results, ["Adult(?x)"])
        self.assertEqual(self.calls, [])

    def test_rete_reset_action_history_allows_deliberate_replay(self):
        self.engine.execute_matches([self.match])

        self.engine.reset_action_history()
        self.engine.execute_matches([self.match])

        self.assertEqual(self.calls, [{"x": "John"}, {"x": "John"}])

    def test_rete_reset_allows_action_replay(self):
        self.engine.execute_matches([self.match])

        self.engine.reset()
        self.engine.execute_matches([self.match])

        self.assertEqual(self.calls, [{"x": "John"}, {"x": "John"}])

    def test_rete_build_network_allows_action_replay(self):
        self.engine.execute_matches([self.match])

        self.engine.build_network([self.rule])
        self.engine.execute_matches([self.match])

        self.assertEqual(self.calls, [{"x": "John"}, {"x": "John"}])


if __name__ == "__main__":
    unittest.main()
