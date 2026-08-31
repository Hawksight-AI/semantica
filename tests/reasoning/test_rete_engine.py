"""Tests for the RETE engine pattern matching (issue #300).

These tests verify that ``AlphaNode._matches`` and ``BetaNode._can_join`` no
longer behave like the old always-``True`` stubs, and that the network as a
whole only fires rules whose conditions actually unify with the facts.
"""

import itertools
import re
import unittest
from unittest import mock

from semantica.reasoning import rete_engine
from semantica.reasoning.reasoner import Fact, Rule
from semantica.reasoning.rete_engine import (
    AlphaNode,
    BetaNode,
    ReteEngine,
    unify_condition,
)


class TestUnifyCondition(unittest.TestCase):
    def test_single_variable_binds(self):
        fact = Fact("f1", "Person", ["John"])
        bindings = unify_condition("Person(?x)", fact)
        self.assertEqual(bindings, {"x": "John"})

    def test_predicate_mismatch_returns_none(self):
        fact = Fact("f1", "Company", ["Google"])
        self.assertIsNone(unify_condition("Person(?x)", fact))

    def test_two_arguments_bind(self):
        fact = Fact("f2", "Parent", ["John", "Mary"])
        bindings = unify_condition("Parent(?x, ?y)", fact)
        self.assertEqual(bindings, {"x": "John", "y": "Mary"})

    def test_literal_argument_must_match(self):
        fact = Fact("f3", "Parent", ["John", "Mary"])
        self.assertIsNone(unify_condition("Parent(Bob, ?y)", fact))
        self.assertEqual(unify_condition("Parent(John, ?y)", fact), {"y": "Mary"})

    def test_repeated_variable_requires_equal_values(self):
        loves_self = Fact("f4", "Loves", ["John", "John"])
        loves_other = Fact("f5", "Loves", ["John", "Mary"])
        self.assertEqual(unify_condition("Loves(?x, ?x)", loves_self), {"x": "John"})
        self.assertIsNone(unify_condition("Loves(?x, ?x)", loves_other))

    def test_regex_error_logs_warning_and_returns_none(self):
        """A regex compilation error is logged with context and yields None."""
        fact = Fact("f6", "Person", ["John"])
        with mock.patch.object(
            rete_engine.re,
            "match",
            side_effect=re.error("bad pattern"),
        ), self.assertLogs("semantica.rete_engine", level="WARNING") as captured:
            result = unify_condition("Person(?x)", fact)
        self.assertIsNone(result)
        joined = "\n".join(captured.output)
        self.assertIn("Person(?x)", joined)
        self.assertIn("Person(John)", joined)
        self.assertIn("bad pattern", joined)

    def test_unexpected_error_logs_warning_and_returns_none(self):
        """An unexpected error is also logged and swallowed as None."""
        fact = Fact("f7", "Person", ["John"])
        with mock.patch.object(
            rete_engine.re,
            "match",
            side_effect=RuntimeError("boom"),
        ), self.assertLogs("semantica.rete_engine", level="WARNING") as captured:
            result = unify_condition("Person(?x)", fact)
        self.assertIsNone(result)
        self.assertIn("boom", "\n".join(captured.output))


class TestAlphaNode(unittest.TestCase):
    def test_matches_stores_bindings(self):
        node = AlphaNode("a1", "Person(?x)")
        fact = Fact("f1", "Person", ["John"])
        token = node.add_fact(fact)
        self.assertIsNotNone(token)
        assert token is not None  # narrow type for the checker
        self.assertEqual(token.facts, [fact])
        self.assertEqual(token.bindings, {"x": "John"})
        self.assertIn(token, node.tokens)

    def test_non_matching_fact_rejected(self):
        node = AlphaNode("a1", "Person(?x)")
        fact = Fact("f1", "Company", ["Google"])
        self.assertIsNone(node.add_fact(fact))
        self.assertEqual(node.tokens, [])

    def test_uses_precompiled_regex(self):
        """AlphaNode compiles its condition once and reuses it per fact."""
        node = AlphaNode("a1", "Person(?x)")
        self.assertIsNotNone(node._compiled)
        # Matching goes through the compiled matcher, not unify_condition.
        with mock.patch.object(rete_engine, "unify_condition") as unify:
            fact = Fact("f1", "Person", ["John"])
            token = node.add_fact(fact)
        unify.assert_not_called()
        self.assertIsNotNone(token)
        assert token is not None
        self.assertEqual(token.bindings, {"x": "John"})

    def test_bad_condition_never_matches_and_logs(self):
        """A condition that fails to compile logs a warning and never fires."""
        with mock.patch.object(
            rete_engine,
            "_build_condition_regex",
            return_value="(unbalanced",
        ), self.assertLogs("semantica.rete_engine", level="WARNING") as captured:
            node = AlphaNode("bad", "Person(?x)")
        self.assertIsNone(node._compiled)
        self.assertIn("failed to compile", "\n".join(captured.output))
        fact = Fact("f1", "Person", ["John"])
        self.assertIsNone(node.add_fact(fact))
        self.assertEqual(node.tokens, [])


class TestBetaNode(unittest.TestCase):
    def test_join_consistent_bindings(self):
        left = AlphaNode("a1", "Parent(?x, ?y)")
        right = AlphaNode("a2", "Person(?x)")
        beta = BetaNode("b1", left, right)

        parent = Fact("f1", "Parent", ["John", "Mary"])
        person = Fact("f2", "Person", ["John"])
        left_token = left.add_fact(parent)
        right_token = right.add_fact(person)
        assert left_token is not None and right_token is not None

        merged = beta.join(left_token, right_token)
        self.assertIsNotNone(merged)
        assert merged is not None  # narrow type for the checker
        self.assertEqual(merged.bindings, {"x": "John", "y": "Mary"})
        # Facts are concatenated left-then-right in condition order.
        self.assertEqual(merged.facts, [parent, person])

    def test_join_conflicting_bindings_rejected(self):
        left = AlphaNode("a1", "Parent(?x, ?y)")
        right = AlphaNode("a2", "Person(?x)")
        beta = BetaNode("b1", left, right)

        parent = Fact("f1", "Parent", ["John", "Mary"])
        # ?x conflicts: John vs Alice
        person = Fact("f2", "Person", ["Alice"])
        left_token = left.add_fact(parent)
        right_token = right.add_fact(person)
        assert left_token is not None and right_token is not None

        self.assertIsNone(beta.join(left_token, right_token))


class TestReteEngineEndToEnd(unittest.TestCase):
    def test_only_matching_rule_fires(self):
        engine = ReteEngine()
        rule = Rule(
            rule_id="r1",
            name="person rule",
            conditions=["Person(?x)"],
            conclusion="Mortal(?x)",
        )
        engine.build_network([rule])

        engine.add_fact(Fact("f1", "Person", ["John"]))
        engine.add_fact(Fact("f2", "Company", ["Google"]))  # should NOT fire

        matches = engine.match_patterns()
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].bindings, {"x": "John"})

    def test_multi_condition_join(self):
        engine = ReteEngine()
        rule = Rule(
            rule_id="r1",
            name="child rule",
            conditions=["Person(?x)", "Parent(?x, ?y)"],
            conclusion="Child(?y, ?x)",
        )
        engine.build_network([rule])

        engine.add_fact(Fact("f1", "Person", ["John"]))
        engine.add_fact(Fact("f2", "Parent", ["John", "Mary"]))
        # Unrelated parent whose ?x does not match any Person -> no activation.
        engine.add_fact(Fact("f3", "Parent", ["Bob", "Sue"]))

        matches = engine.match_patterns()
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].bindings, {"x": "John", "y": "Mary"})

    def test_no_activation_when_join_inconsistent(self):
        engine = ReteEngine()
        rule = Rule(
            rule_id="r1",
            name="child rule",
            conditions=["Person(?x)", "Parent(?x, ?y)"],
            conclusion="Child(?y, ?x)",
        )
        engine.build_network([rule])

        engine.add_fact(Fact("f1", "Person", ["John"]))
        engine.add_fact(Fact("f2", "Parent", ["Alice", "Mary"]))  # ?x mismatch

        matches = engine.match_patterns()
        self.assertEqual(matches, [])


class TestThreeConditionChain(unittest.TestCase):
    """Chained beta joins across three or more conditions (issue #300).

    These exercise the Token model: a token must accumulate the ordered
    facts and the consistent bindings of every condition, so that deep
    chains neither drop bindings nor duplicate facts, and a conflict on the
    third condition correctly suppresses activation.
    """

    def _three_condition_rule(self):
        return Rule(
            rule_id="r1",
            name="location chain",
            conditions=[
                "Person(?x)",
                "Parent(?x, ?y)",
                "Located(?y, ?z)",
            ],
            conclusion="LivesNear(?x, ?z)",
        )

    def test_three_condition_valid_match(self):
        engine = ReteEngine()
        engine.build_network([self._three_condition_rule()])

        engine.add_fact(Fact("f1", "Person", ["John"]))
        engine.add_fact(Fact("f2", "Parent", ["John", "Mary"]))
        engine.add_fact(Fact("f3", "Located", ["Mary", "Paris"]))

        matches = engine.match_patterns()
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0].bindings,
            {"x": "John", "y": "Mary", "z": "Paris"},
        )

    def test_three_condition_third_level_conflict(self):
        engine = ReteEngine()
        engine.build_network([self._three_condition_rule()])

        engine.add_fact(Fact("f1", "Person", ["John"]))
        engine.add_fact(Fact("f2", "Parent", ["John", "Mary"]))
        # ?y is bound to Mary, so a Located fact about Bob must not join.
        engine.add_fact(Fact("f3", "Located", ["Bob", "Paris"]))

        matches = engine.match_patterns()
        self.assertEqual(matches, [])

    def test_fact_insertion_order_independent(self):
        # Whatever order facts arrive, the same single match must result.
        base_facts = [
            Fact("f1", "Person", ["John"]),
            Fact("f2", "Parent", ["John", "Mary"]),
            Fact("f3", "Located", ["Mary", "Paris"]),
        ]
        expected = {"x": "John", "y": "Mary", "z": "Paris"}

        for order in itertools.permutations(base_facts):
            engine = ReteEngine()
            engine.build_network([self._three_condition_rule()])
            for fact in order:
                engine.add_fact(fact)
            matches = engine.match_patterns()
            self.assertEqual(len(matches), 1, f"order={order}")
            self.assertEqual(matches[0].bindings, expected)

    def test_match_facts_complete_in_condition_order(self):
        engine = ReteEngine()
        engine.build_network([self._three_condition_rule()])

        person = Fact("f1", "Person", ["John"])
        parent = Fact("f2", "Parent", ["John", "Mary"])
        located = Fact("f3", "Located", ["Mary", "Paris"])
        engine.add_fact(person)
        engine.add_fact(parent)
        engine.add_fact(located)

        matches = engine.match_patterns()
        self.assertEqual(len(matches), 1)
        # All three facts preserved, in condition order, no duplicates.
        self.assertEqual(matches[0].facts, [person, parent, located])

    def test_multiple_left_tokens_join_one_right_fact(self):
        # Two Person/Parent chains sharing the same Located(?y, ?z) fact.
        engine = ReteEngine()
        engine.build_network([self._three_condition_rule()])

        engine.add_fact(Fact("f1", "Person", ["John"]))
        engine.add_fact(Fact("f2", "Parent", ["John", "Mary"]))
        engine.add_fact(Fact("f3", "Person", ["Alice"]))
        engine.add_fact(Fact("f4", "Parent", ["Alice", "Mary"]))
        # One right fact should join with both accumulated left tokens.
        engine.add_fact(Fact("f5", "Located", ["Mary", "Paris"]))

        matches = engine.match_patterns()
        self.assertEqual(len(matches), 2)
        result = {m.bindings["x"]: m.bindings["z"] for m in matches}
        self.assertEqual(result, {"John": "Paris", "Alice": "Paris"})

    def test_matches_reasoner_match_rule(self):
        from semantica.reasoning.reasoner import Reasoner

        rule = self._three_condition_rule()
        facts = [
            Fact("f1", "Person", ["John"]),
            Fact("f2", "Parent", ["John", "Mary"]),
            Fact("f3", "Located", ["Mary", "Paris"]),
        ]

        # Reasoner works over stringified facts and returns
        # (conclusion, matched_facts, bindings) tuples from self.facts.
        reasoner = Reasoner()
        for fact in facts:
            reasoner.add_fact(str(fact))
        reasoner_matches = reasoner._match_rule(rule)

        engine = ReteEngine()
        engine.build_network([rule])
        for fact in facts:
            engine.add_fact(fact)
        rete_matches = engine.match_patterns()

        # Both engines must agree on the number of activations.
        self.assertEqual(len(rete_matches), len(reasoner_matches))
        self.assertEqual(len(rete_matches), 1)
        self.assertEqual(
            rete_matches[0].bindings,
            {"x": "John", "y": "Mary", "z": "Paris"},
        )
        # The RETE match must carry the instantiated conclusion facts too.
        conclusion, _, _ = reasoner_matches[0]
        self.assertEqual(conclusion, "LivesNear(John, Paris)")

    def test_reset_clears_all_token_memory(self):
        engine = ReteEngine()
        engine.build_network([self._three_condition_rule()])

        engine.add_fact(Fact("f1", "Person", ["John"]))
        engine.add_fact(Fact("f2", "Parent", ["John", "Mary"]))
        engine.add_fact(Fact("f3", "Located", ["Mary", "Paris"]))
        self.assertEqual(len(engine.match_patterns()), 1)

        engine.reset()

        # No stale facts, tokens or activations remain anywhere.
        self.assertEqual(engine.facts, [])
        for node in engine.network.values():
            if isinstance(node, AlphaNode):
                self.assertEqual(node.tokens, [])
            elif isinstance(node, BetaNode):
                self.assertEqual(node.left_tokens, [])
                self.assertEqual(node.right_tokens, [])
        self.assertEqual(engine.match_patterns(), [])


if __name__ == "__main__":
    unittest.main()
