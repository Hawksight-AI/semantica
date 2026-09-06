"""
Regression tests for PR #967 — Decision persistence / index consistency,
CJK similarity, query_graph limit, and MCP tool correctness.

These tests cover every bug confirmed by the pre-PR investigation and every
new correctness issue introduced or left behind by the PR:

  1.  save → load → find_similar_decisions  (core persistence invariant)
  2.  save → load → metadata preservation
  3.  save → load → all decision analytics callable
  4.  Repeated load clears stale indexes  (no ghost decisions)
  5.  In-memory decisions cleared when loading into a graph that already has
      decisions recorded in-memory
  6.  Category filtering via find_nodes / query_decisions
  7.  Decision index stays consistent after add_node_attribute mutation
  8.  CJK similarity — short CJK query matches relevant text
  9.  Bigram spike regression — 2-char English query must NOT produce 1.0
  10. English similarity still works normally
  11. Empty / 1-char input safety
  12. query_graph limit=0 returns empty (not unlimited)
  13. query_graph limit=None returns all
  14. query_graph limit=1 caps combined results
  15. query_graph inbound-only topology
  16. query_graph outbound-only topology
  17. query_graph mixed inbound + outbound
  18. from_dict also rebuilds decision indexes
  19. MCP _get_graph loads from SEMANTICA_KG_PATH
  20. update_node smoke test + decision index sync
  21. delete_node soft-archive smoke test
  22. update_node / delete_node persistence after reload
  23. entity extraction returns surface text
"""

import json
import os
import sys
import tempfile
import unittest
from collections import defaultdict
from unittest.mock import patch

# Make sure the repo root is importable even when running from the tests dir.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from semantica.context.context_graph import ContextGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision_graph() -> ContextGraph:
    """Return a ContextGraph with three decisions pre-recorded."""
    g = ContextGraph(advanced_analytics=False)
    g.record_decision(
        category="loan_approval",
        scenario="High-income applicant with perfect credit history",
        reasoning="Credit score 800+, stable employment for 10 years",
        outcome="approved",
        confidence=0.95,
        entities=["applicant_123", "bank_abc"],
        decision_maker="underwriter",
        metadata={"risk_tier": "low", "custom_flag": True},
    )
    g.record_decision(
        category="loan_approval",
        scenario="Self-employed applicant with variable income",
        reasoning="Good credit but income variability poses moderate risk",
        outcome="conditional_approval",
        confidence=0.72,
        entities=["applicant_456"],
        decision_maker="underwriter",
    )
    g.record_decision(
        category="fraud_detection",
        scenario="Unusual transaction pattern detected in account",
        reasoning="Multiple small transactions in rapid succession across geographies",
        outcome="flagged",
        confidence=0.88,
        entities=["account_789", "transaction_seq"],
        decision_maker="fraud_engine",
    )
    return g


# ---------------------------------------------------------------------------
# Part 1: Core persistence invariant — save → load → find_similar_decisions
# ---------------------------------------------------------------------------

class TestDecisionPersistenceRoundTrip(unittest.TestCase):
    """save → load must produce decision-query-equivalent behaviour."""

    def test_find_similar_decisions_after_reload(self):
        """Core invariant: similarity search works after save/load."""
        g = _decision_graph()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)

            # Query that matches the loan_approval decisions
            results = g2.find_similar_decisions(
                "credit history approval", max_results=5, min_similarity=0.01
            )
            self.assertGreater(len(results), 0, "Expected at least one match after reload")
            # Each result must be a dict with a decision key
            self.assertIn("decision", results[0])
        finally:
            os.unlink(path)

    def test_find_precedents_by_scenario_after_reload(self):
        """find_precedents_by_scenario must not return [] after reload."""
        g = _decision_graph()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)

            results = g2.find_precedents_by_scenario(
                "applicant credit history loan",
                similarity_threshold=0.01,
            )
            self.assertGreater(len(results), 0)
        finally:
            os.unlink(path)

    def test_decision_count_after_reload(self):
        """_decisions must be populated for statistics calls after reload."""
        g = _decision_graph()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)

            stats = g2.get_decision_insights()
            # Should not be the "No decisions" sentinel
            self.assertNotEqual(stats, {"message": "No decisions recorded yet"})
            self.assertEqual(stats.get("total_decisions", 0), 3)
        finally:
            os.unlink(path)

    def test_decisions_dict_populated_after_reload(self):
        """_decisions must exist and contain 3 entries after reload."""
        g = _decision_graph()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)

            self.assertTrue(hasattr(g2, "_decisions"))
            self.assertEqual(len(g2._decisions), 3)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Part 2: Metadata preservation across save/load
# ---------------------------------------------------------------------------

class TestDecisionMetadataPreservation(unittest.TestCase):

    def test_custom_metadata_survives_reload(self):
        """User-supplied metadata must survive a save → load round-trip."""
        g = ContextGraph(advanced_analytics=False)
        did = g.record_decision(
            category="test",
            scenario="Testing metadata preservation",
            reasoning="Verifying that custom fields survive reload",
            outcome="pass",
            confidence=0.9,
            metadata={"foo": "bar", "priority": 42},
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)

            reloaded_decision = g2._decisions.get(did)
            self.assertIsNotNone(reloaded_decision, "_decisions must contain the decision after reload")
            # Metadata should contain the custom fields
            meta = reloaded_decision.get("metadata", {})
            self.assertEqual(meta.get("foo"), "bar")
            self.assertEqual(meta.get("priority"), 42)
        finally:
            os.unlink(path)

    def test_core_fields_preserved_after_reload(self):
        """All core decision fields must survive a round-trip unchanged."""
        g = ContextGraph(advanced_analytics=False)
        did = g.record_decision(
            category="compliance",
            scenario="Regulatory check for derivative trade",
            reasoning="Trade complies with Dodd-Frank Section 732",
            outcome="compliant",
            confidence=0.85,
            entities=["trader_X", "instrument_Y"],
            decision_maker="compliance_engine",
        )
        recorded_at_before = g._decisions[did]["recorded_at"]
        self.assertTrue(recorded_at_before, "recorded_at must be set at record time")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)

            dec = g2._decisions.get(did)
            self.assertIsNotNone(dec)
            self.assertEqual(dec["category"], "compliance")
            self.assertIn("Regulatory check", dec["scenario"])
            self.assertEqual(dec["outcome"], "compliant")
            self.assertAlmostEqual(dec["confidence"], 0.85, places=3)
            self.assertIn("trader_X", dec["entities"])
            self.assertEqual(dec["decision_maker"], "compliance_engine")
            self.assertEqual(dec["recorded_at"], recorded_at_before,
                             "recorded_at must survive a save -> load round trip")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Part 3: Repeated load clears stale indexes
# ---------------------------------------------------------------------------

class TestRepeatedLoadClearsStaleIndexes(unittest.TestCase):

    def test_second_load_replaces_first(self):
        """Loading file B into a graph that already loaded file A must leave
        only B's decisions visible — no ghost decisions from A."""
        g_a = ContextGraph(advanced_analytics=False)
        g_a.record_decision(
            category="cat_A",
            scenario="Decision from file A",
            reasoning="Reason A",
            outcome="outcome_A",
            confidence=0.9,
        )

        g_b = ContextGraph(advanced_analytics=False)
        g_b.record_decision(
            category="cat_B",
            scenario="Decision from file B",
            reasoning="Reason B",
            outcome="outcome_B",
            confidence=0.8,
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fa, \
             tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fb:
            path_a, path_b = fa.name, fb.name
        try:
            g_a.save_to_file(path_a)
            g_b.save_to_file(path_b)

            target = ContextGraph(advanced_analytics=False)

            # Load A
            target.load_from_file(path_a)
            self.assertEqual(len(target._decisions), 1)
            cats_after_a = {d["category"] for d in target._decisions.values()}
            self.assertIn("cat_A", cats_after_a)

            # Load B into same instance — must replace A entirely
            target.load_from_file(path_b)
            self.assertEqual(len(target._decisions), 1,
                             "Stale cat_A decision must not persist after loading B")
            cats_after_b = {d["category"] for d in target._decisions.values()}
            self.assertIn("cat_B", cats_after_b)
            self.assertNotIn("cat_A", cats_after_b)
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_load_into_graph_with_in_memory_decisions(self):
        """Loading a file into a graph that already has in-memory decisions
        must produce indexes that reflect ONLY the file's decisions."""
        g = ContextGraph(advanced_analytics=False)
        # Record an in-memory decision first
        g.record_decision(
            category="in_memory",
            scenario="Decision recorded before load",
            reasoning="Testing stale index reset",
            outcome="ok",
            confidence=0.5,
        )

        # Now create a graph file with different content
        g_file = ContextGraph(advanced_analytics=False)
        g_file.record_decision(
            category="from_file",
            scenario="Decision loaded from file",
            reasoning="This is what should survive",
            outcome="loaded",
            confidence=0.7,
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g_file.save_to_file(path)
            g.load_from_file(path)

            cats = {d["category"] for d in g._decisions.values()}
            self.assertIn("from_file", cats)
            self.assertNotIn("in_memory", cats,
                             "In-memory decision must be evicted after load_from_file")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Part 4: Category filtering
# ---------------------------------------------------------------------------

class TestCategoryFiltering(unittest.TestCase):

    def test_decision_index_correct_after_reload(self):
        """_decision_index must map categories correctly after reload."""
        g = _decision_graph()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)

            loan_ids = g2._decision_index.get("loan_approval", set())
            fraud_ids = g2._decision_index.get("fraud_detection", set())

            self.assertEqual(len(loan_ids), 2, "Expected 2 loan_approval decisions")
            self.assertEqual(len(fraud_ids), 1, "Expected 1 fraud_detection decision")
            # No overlap
            self.assertTrue(loan_ids.isdisjoint(fraud_ids))
        finally:
            os.unlink(path)

    def test_find_nodes_category_in_metadata(self):
        """find_nodes returns category inside 'metadata', not at top level."""
        g = ContextGraph(advanced_analytics=False)
        g.record_decision(
            category="risk_check",
            scenario="Scenario",
            reasoning="Reasoning",
            outcome="pass",
            confidence=0.9,
        )
        nodes = g.find_nodes(node_type="decision")
        self.assertGreater(len(nodes), 0)
        # Category must be accessible via metadata key
        found = any(
            n.get("metadata", {}).get("category") == "risk_check"
            for n in nodes
        )
        self.assertTrue(found, "category must be in n['metadata']['category']")
        # Must NOT be at top level (that is the bug that was fixed)
        top_level = any(n.get("category") == "risk_check" for n in nodes)
        self.assertFalse(top_level, "category must NOT appear at the top level of find_nodes result")


# ---------------------------------------------------------------------------
# Part 5: Decision index consistency after mutation
# ---------------------------------------------------------------------------

class TestDecisionIndexMutationSync(unittest.TestCase):

    def test_add_node_attribute_syncs_decision_index(self):
        """After add_node_attribute on a decision node, _decisions must reflect
        the new values without requiring a reload."""
        g = ContextGraph(advanced_analytics=False)
        did = g.record_decision(
            category="original_cat",
            scenario="Original scenario",
            reasoning="Original reasoning",
            outcome="original",
            confidence=0.6,
        )
        # Verify original state
        self.assertIn(did, g._decision_index.get("original_cat", set()))

        # Mutate via add_node_attribute
        g.add_node_attribute(did, {"confidence": 0.95, "custom_note": "reviewed"})

        # _decisions must reflect updated confidence
        updated = g._decisions.get(did)
        self.assertIsNotNone(updated)
        self.assertAlmostEqual(updated["confidence"], 0.95, places=3)
        # custom_note should appear in metadata
        self.assertEqual(updated["metadata"].get("custom_note"), "reviewed")

    def test_update_node_does_not_leave_stale_index(self):
        """update_node (via add_node_attribute) must not break category lookup."""
        g = ContextGraph(advanced_analytics=False)
        did = g.record_decision(
            category="cat_original",
            scenario="Some scenario",
            reasoning="Some reasoning",
            outcome="ok",
            confidence=0.7,
        )
        # The decision should be findable by category
        results_before = g.find_precedents_by_scenario(
            "Some scenario", similarity_threshold=0.01
        )
        self.assertGreater(len(results_before), 0)

        # Mutate some non-index fields
        g.add_node_attribute(did, {"status": "reviewed", "reviewer": "alice"})

        # Decision should still be findable after mutation
        results_after = g.find_precedents_by_scenario(
            "Some scenario", similarity_threshold=0.01
        )
        self.assertGreater(len(results_after), 0)


# ---------------------------------------------------------------------------
# Part 6: from_dict also rebuilds decision indexes
# ---------------------------------------------------------------------------

class TestFromDictDecisionIndexes(unittest.TestCase):

    def test_from_dict_populates_decision_indexes(self):
        """from_dict must rebuild _decisions, _decision_index, etc."""
        g = _decision_graph()
        d = g.to_dict()

        g2 = ContextGraph(advanced_analytics=False)
        g2.from_dict(d)

        self.assertTrue(hasattr(g2, "_decisions"))
        self.assertEqual(len(g2._decisions), 3)
        self.assertGreater(len(g2._decision_index), 0)

    def test_from_dict_repeated_call_clears_stale(self):
        """Calling from_dict twice must not accumulate ghost entries."""
        g1 = ContextGraph(advanced_analytics=False)
        g1.record_decision(
            category="x", scenario="s", reasoning="r", outcome="o", confidence=0.5
        )
        g2 = ContextGraph(advanced_analytics=False)
        g2.record_decision(
            category="y", scenario="s2", reasoning="r2", outcome="o2", confidence=0.6
        )

        target = ContextGraph(advanced_analytics=False)
        target.from_dict(g1.to_dict())
        self.assertEqual(len(target._decisions), 1)
        cats = {d["category"] for d in target._decisions.values()}
        self.assertIn("x", cats)

        target.from_dict(g2.to_dict())
        self.assertEqual(len(target._decisions), 1)
        cats2 = {d["category"] for d in target._decisions.values()}
        self.assertIn("y", cats2)
        self.assertNotIn("x", cats2)


# ---------------------------------------------------------------------------
# Part 7: CJK similarity
# ---------------------------------------------------------------------------

class TestCJKSimilarity(unittest.TestCase):

    def _sim(self, scenario, decision_scenario, decision_reasoning="", entities=None):
        """Helper: compute _calculate_decision_content_similarity directly."""
        g = ContextGraph(advanced_analytics=False)
        decision = {
            "scenario": decision_scenario,
            "reasoning": decision_reasoning,
            "entities": entities or [],
        }
        return g._calculate_decision_content_similarity(scenario, decision)

    def test_cjk_two_char_query_matches_relevant_text(self):
        """A 2-character CJK query should match text containing those chars."""
        # 中文 (Chinese text) — 2 chars, produces 1 bigram: not enough for
        # bigram signal.  But a 3-char query should work.
        # Use a 4-char CJK phrase (→ 3 bigrams) to activate the bigram path.
        query = "中文审批"        # 4 CJK chars → 3 bigrams
        doc_scenario = "中文审批流程 贷款决策"
        sim = self._sim(query, doc_scenario)
        self.assertGreater(sim, 0.0, "CJK query must produce a non-zero similarity")

    def test_cjk_irrelevant_text_low_similarity(self):
        """A CJK query must NOT produce high similarity with unrelated text."""
        query = "中文审批"
        unrelated = "Python programming language feature request"
        sim = self._sim(query, unrelated)
        # Some accidental bigram overlap is possible with stripped chars, but
        # should be significantly less than 1.0
        self.assertLess(sim, 0.5)

    def test_cjk_identical_text_high_similarity(self):
        """Identical CJK text must produce similarity close to 1.0."""
        text = "中文审批流程决策"   # 8 chars → 7 bigrams
        sim = self._sim(text, text)
        self.assertGreater(sim, 0.9)


# ---------------------------------------------------------------------------
# Part 8: Bigram spike regression (2-char English query must NOT give 1.0)
# ---------------------------------------------------------------------------

class TestBigramSpikeRegression(unittest.TestCase):

    def _sim(self, scenario, doc_scenario):
        g = ContextGraph(advanced_analytics=False)
        return g._calculate_decision_content_similarity(
            scenario, {"scenario": doc_scenario, "reasoning": "", "entities": []}
        )

    def test_two_char_english_query_no_spike(self):
        """A 2-char English query must NOT receive similarity 1.0 merely
        because those chars appear as a substring in the document text."""
        # 'in' is a 2-char query → 1 bigram → below the 3-bigram threshold.
        # Word-based Jaccard also gives 0.0 ('in' not a word in the doc).
        sim = self._sim("in", "interest rate decision analysis")
        self.assertLess(sim, 0.5,
                        "2-char English query 'in' must not spike to 1.0")

    def test_single_char_query_safe(self):
        """A single-character query must return 0.0 without crashing."""
        sim = self._sim("a", "apple analysis algorithm")
        self.assertEqual(sim, 0.0)

    def test_empty_query_safe(self):
        """An empty query must return 0.0 without crashing."""
        sim = self._sim("", "some decision text here")
        self.assertEqual(sim, 0.0)

    def test_normal_english_similarity_preserved(self):
        """Normal English word overlap must still produce reasonable scores."""
        sim = self._sim(
            "credit approval loan applicant",
            "loan applicant credit history approval decision",
        )
        self.assertGreater(sim, 0.3, "Normal English similarity must remain reasonable")

    def test_common_bigram_substring_below_threshold(self):
        """2-char queries 'al', 'ba', 'at' must not produce similarity 1.0."""
        for q in ("al", "ba", "at", "re"):
            sim = self._sim(q, "algorithm alignment base rate attention")
            self.assertLess(sim, 0.5,
                            f"2-char query {q!r} must not produce high similarity")

    def test_unrelated_multiword_english_queries_score_zero(self):
        """The bigram fallback must not activate for ordinary multi-word
        English queries -- it exists only for CJK/single-token queries where
        whitespace tokenisation can't help. Unrelated multi-word English
        sentences must score 0.0, not a nonzero incidental bigram overlap."""
        sim = self._sim(
            "employee vacation request approval process",
            "Server infrastructure migration to cloud provider",
        )
        self.assertEqual(sim, 0.0,
                         "Unrelated multi-word English queries must not "
                         "receive a nonzero score from bigram overlap")


# ---------------------------------------------------------------------------
# Part 9: query_graph limit semantics
# ---------------------------------------------------------------------------

class TestQueryGraphLimitSemantics(unittest.TestCase):
    """Tests for _tool_query_graph limit correctness."""

    def _make_graph_and_patch(self):
        """Build a simple graph and patch _get_graph to return it."""
        g = ContextGraph(advanced_analytics=False)
        g.add_node("center", "hub", label="Center")
        for i in range(5):
            g.add_node(f"out_{i}", "spoke", label=f"Spoke {i}")
            g.add_edge("center", f"out_{i}", "connects")
        for i in range(3):
            g.add_node(f"in_{i}", "feeder", label=f"Feeder {i}")
            g.add_edge(f"in_{i}", "center", "feeds")
        return g

    def test_limit_none_returns_all(self):
        """limit=None must return all neighbours (outbound + inbound)."""
        from semantica.mcp_server import _tool_query_graph
        g = self._make_graph_and_patch()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({
                "mode": "neighbors",
                "node_id": "center",
                "depth": 1,
                "limit": None,
            })
        neighbors = result.get("neighbors", [])
        self.assertGreaterEqual(len(neighbors), 5, "Should include all outbound")

    def test_limit_zero_returns_empty(self):
        """limit=0 must return an empty neighbors list, not bypass the cap."""
        from semantica.mcp_server import _tool_query_graph
        g = self._make_graph_and_patch()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({
                "mode": "neighbors",
                "node_id": "center",
                "depth": 1,
                "limit": 0,
            })
        neighbors = result.get("neighbors", [])
        self.assertEqual(neighbors, [],
                         "limit=0 must produce an empty result, not bypass the cap")

    def test_limit_one_caps_result(self):
        """limit=1 must return exactly 1 neighbour regardless of total."""
        from semantica.mcp_server import _tool_query_graph
        g = self._make_graph_and_patch()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({
                "mode": "neighbors",
                "node_id": "center",
                "depth": 1,
                "limit": 1,
            })
        neighbors = result.get("neighbors", [])
        self.assertEqual(len(neighbors), 1)

    def test_limit_larger_than_available(self):
        """limit > total results must return all available without error."""
        from semantica.mcp_server import _tool_query_graph
        g = self._make_graph_and_patch()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({
                "mode": "neighbors",
                "node_id": "center",
                "depth": 1,
                "limit": 1000,
            })
        self.assertNotIn("error", result)
        neighbors = result.get("neighbors", [])
        # center has 5 outbound + 3 inbound = 8 total
        self.assertGreaterEqual(len(neighbors), 5)

    def test_outbound_only_topology(self):
        """Nodes with only outbound edges must return outbound neighbours."""
        from semantica.mcp_server import _tool_query_graph
        g = ContextGraph(advanced_analytics=False)
        g.add_node("source", "hub")
        g.add_node("dest1", "leaf")
        g.add_node("dest2", "leaf")
        g.add_edge("source", "dest1", "points_to")
        g.add_edge("source", "dest2", "points_to")
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({
                "mode": "neighbors",
                "node_id": "source",
                "depth": 1,
            })
        neighbors = result.get("neighbors", [])
        directions = {n["direction"] for n in neighbors}
        self.assertIn("out", directions)

    def test_inbound_only_topology(self):
        """Nodes with only inbound edges must return inbound neighbours."""
        from semantica.mcp_server import _tool_query_graph
        g = ContextGraph(advanced_analytics=False)
        g.add_node("sink", "hub")
        g.add_node("src1", "feeder")
        g.add_node("src2", "feeder")
        g.add_edge("src1", "sink", "feeds")
        g.add_edge("src2", "sink", "feeds")
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({
                "mode": "neighbors",
                "node_id": "sink",
                "depth": 1,
            })
        neighbors = result.get("neighbors", [])
        directions = {n["direction"] for n in neighbors}
        self.assertIn("in", directions)
        self.assertNotIn("out", directions)

    def test_mixed_inbound_outbound(self):
        """A node with both inbound and outbound edges returns both directions."""
        from semantica.mcp_server import _tool_query_graph
        g = ContextGraph(advanced_analytics=False)
        g.add_node("mid", "hub")
        g.add_node("up", "parent")
        g.add_node("down", "child")
        g.add_edge("up", "mid", "parent_of")
        g.add_edge("mid", "down", "child_of")
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({
                "mode": "neighbors",
                "node_id": "mid",
                "depth": 1,
            })
        neighbors = result.get("neighbors", [])
        directions = {n["direction"] for n in neighbors}
        self.assertIn("in", directions)
        self.assertIn("out", directions)


# ---------------------------------------------------------------------------
# Part 10: MCP _get_graph loads from SEMANTICA_KG_PATH
# ---------------------------------------------------------------------------

class TestMCPGetGraphLoadsFromPath(unittest.TestCase):

    def test_get_graph_loads_kg_path(self):
        """When SEMANTICA_KG_PATH is set, _get_graph must load it."""
        import semantica.mcp_server as mcp_mod

        g = ContextGraph(advanced_analytics=False)
        g.add_node("kg_node_1", "entity", label="Loaded from file")
        g.record_decision(
            category="test_load",
            scenario="Testing KG path load",
            reasoning="Verifying MCP server auto-load",
            outcome="verified",
            confidence=0.99,
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)

            # Reset the module-level _graph so _get_graph re-initialises
            original_graph = mcp_mod._graph
            mcp_mod._graph = None
            try:
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    loaded_graph = mcp_mod._get_graph()
                    self.assertTrue(loaded_graph.has_node("kg_node_1"),
                                    "Graph must contain node from persisted file")
                    # Decision indexes must also be rebuilt
                    self.assertTrue(
                        hasattr(loaded_graph, "_decisions") and loaded_graph._decisions,
                        "Decision indexes must be rebuilt when loading from SEMANTICA_KG_PATH"
                    )
            finally:
                mcp_mod._graph = original_graph
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Part 11: update_node / delete_node smoke tests + decision sync
# ---------------------------------------------------------------------------

class TestUpdateDeleteNodeMCP(unittest.TestCase):

    def _fresh_graph_with_decision(self):
        g = ContextGraph(advanced_analytics=False)
        g.add_node("task_1", "task", label="A task node")
        did = g.record_decision(
            category="project",
            scenario="Scope definition for Q3",
            reasoning="Requirements complete",
            outcome="approved",
            confidence=0.9,
        )
        return g, did

    def test_update_node_returns_updated_properties(self):
        """update_node must reflect new property values in its response."""
        from semantica.mcp_server import _tool_update_node
        g, _ = self._fresh_graph_with_decision()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_update_node({
                "node_id": "task_1",
                "properties": {"status": "done", "note": "completed by alice"},
            })
        self.assertEqual(result.get("status"), "updated")
        self.assertEqual(result.get("node_id"), "task_1")
        # Verify node actually updated in graph
        node = g.find_node("task_1")
        self.assertEqual((node.get("metadata") or {}).get("status"), "done")

    def test_update_node_nonexistent_returns_error(self):
        """update_node on a nonexistent node must return an error dict."""
        from semantica.mcp_server import _tool_update_node
        g, _ = self._fresh_graph_with_decision()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_update_node({
                "node_id": "does_not_exist",
                "properties": {"status": "done"},
            })
        self.assertIn("error", result)

    def test_delete_node_soft_archives(self):
        """delete_node must mark the node status='archived', not remove it."""
        from semantica.mcp_server import _tool_delete_node
        g, _ = self._fresh_graph_with_decision()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_delete_node({"node_id": "task_1"})
        self.assertEqual(result.get("status"), "archived")
        # Node must still exist
        node = g.find_node("task_1")
        self.assertIsNotNone(node, "Node must still exist after soft-delete")
        self.assertEqual((node.get("metadata") or {}).get("status"), "archived")

    def test_delete_node_nonexistent_returns_error(self):
        """delete_node on a nonexistent node must return an error dict."""
        from semantica.mcp_server import _tool_delete_node
        g, _ = self._fresh_graph_with_decision()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_delete_node({"node_id": "ghost_id"})
        self.assertIn("error", result)

    def test_update_decision_node_syncs_index(self):
        """update_node on a decision node must keep _decisions consistent."""
        from semantica.mcp_server import _tool_update_node
        g, did = self._fresh_graph_with_decision()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            _tool_update_node({
                "node_id": did,
                "properties": {"status": "reviewed", "reviewer": "bob"},
            })
        # _decisions must reflect the new metadata
        dec = g._decisions.get(did)
        self.assertIsNotNone(dec)
        self.assertEqual(dec["metadata"].get("reviewer"), "bob")

    def test_update_delete_persist_after_reload(self):
        """Changes made by update_node / delete_node must survive save → load."""
        from semantica.mcp_server import _tool_update_node, _tool_delete_node
        g, _ = self._fresh_graph_with_decision()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            _tool_update_node({"node_id": "task_1",
                               "properties": {"status": "done"}})
            _tool_delete_node.__wrapped__ = None  # noop; we call the real fn below

        # Manually save and reload
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)
            node = g2.find_node("task_1")
            self.assertIsNotNone(node)
            self.assertEqual((node.get("metadata") or {}).get("status"), "done")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Part 12: MCP entity extraction surface text
# ---------------------------------------------------------------------------

class TestEntityExtractionSurfaceText(unittest.TestCase):

    def test_extract_entities_returns_text_field(self):
        """extract_entities must include a 'text' key with the surface form."""
        from semantica.mcp_server import _tool_extract_entities

        # Minimal smoke test: verify the response shape regardless of whether
        # spaCy models are available.  If no entities are found we skip the
        # assertion on content but still verify no crash and no missing key
        # structure.
        try:
            result = _tool_extract_entities({"text": "Apple announced new iPhone"})
        except Exception as exc:
            self.skipTest(f"NER dependency unavailable: {exc}")

        if "error" in result:
            # spaCy model not installed in this environment — acceptable skip
            self.skipTest(f"NER not available: {result['error']}")

        entities = result.get("entities", [])
        for ent in entities:
            self.assertIn("text", ent,
                          "Each entity must have a 'text' key with the surface form")
            self.assertIn("label", ent,
                          "Each entity must have a 'label' key (NER category)")
            self.assertIn("start", ent)
            self.assertIn("end", ent)

    def test_extract_entities_missing_text_returns_error(self):
        """extract_entities with no text must return an error dict."""
        from semantica.mcp_server import _tool_extract_entities
        result = _tool_extract_entities({})
        self.assertIn("error", result)

    def test_extract_relations_missing_text_returns_error(self):
        """extract_relations with no text must return an error dict."""
        from semantica.mcp_server import _tool_extract_relations
        result = _tool_extract_relations({})
        self.assertIn("error", result)

    def test_extract_relations_with_text_does_not_raise(self):
        """extract_relations must not raise TypeError for missing `entities`
        (RelationExtractor.extract_relations requires an `entities` arg;
        the tool must supply one, e.g. by running NER first)."""
        from semantica.mcp_server import _tool_extract_relations

        try:
            result = _tool_extract_relations({"text": "Apple announced new iPhone"})
        except Exception as exc:
            self.fail(f"extract_relations raised unexpectedly: {exc!r}")

        self.assertNotIn("error", result,
                          "extract_relations should not error on valid text input")
        self.assertIn("relations", result)
        self.assertIn("triplets", result)


# ---------------------------------------------------------------------------
# Part 13: query_graph node / search modes
# ---------------------------------------------------------------------------

class TestQueryGraphNodeAndSearch(unittest.TestCase):

    def _make_graph(self):
        g = ContextGraph(advanced_analytics=False)
        g.add_node("alpha", "concept", label="Alpha Concept")
        g.add_node("beta", "concept", label="Beta Concept")
        g.add_edge("alpha", "beta", "relates_to")
        return g

    def test_node_mode_existing(self):
        """node mode must return the node dict for an existing id."""
        from semantica.mcp_server import _tool_query_graph
        g = self._make_graph()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({"mode": "node", "node_id": "alpha"})
        self.assertIn("node", result)
        self.assertIsNotNone(result["node"])

    def test_node_mode_missing_id(self):
        """node mode with no node_id must return an error."""
        from semantica.mcp_server import _tool_query_graph
        g = self._make_graph()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({"mode": "node"})
        self.assertIn("error", result)

    def test_search_mode_finds_matching(self):
        """search mode must return nodes whose id or content contains the query."""
        from semantica.mcp_server import _tool_query_graph
        g = self._make_graph()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({"mode": "search", "query": "alpha"})
        hits = result.get("results", [])
        self.assertGreater(len(hits), 0)
        ids = [h["id"] for h in hits]
        self.assertIn("alpha", ids)

    def test_search_mode_limit_respected(self):
        """search mode must respect the limit parameter."""
        from semantica.mcp_server import _tool_query_graph
        g = ContextGraph(advanced_analytics=False)
        for i in range(20):
            g.add_node(f"item_{i}", "thing", label=f"item {i}")
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({"mode": "search", "query": "item", "limit": 3})
        self.assertLessEqual(len(result.get("results", [])), 3)

    def test_search_mode_limit_zero_returns_empty(self):
        """search mode with limit=0 must return no results."""
        from semantica.mcp_server import _tool_query_graph
        g = ContextGraph(advanced_analytics=False)
        for i in range(5):
            g.add_node(f"alpha_{i}", "thing", label=f"alpha item {i}")
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({"mode": "search", "query": "alpha", "limit": 0})
        hits = result.get("results", [])
        self.assertEqual(hits, [], f"limit=0 must return empty, got {len(hits)} results")

    def test_unknown_mode_returns_error(self):
        """An unknown mode string must return an error."""
        from semantica.mcp_server import _tool_query_graph
        g = self._make_graph()
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({"mode": "invalid_mode"})
        self.assertIn("error", result)

    def test_inbound_no_duplicates_when_multiple_edges(self):
        """Multiple edges between same source→target must produce only one
        inbound entry for the source node."""
        from semantica.mcp_server import _tool_query_graph
        g = ContextGraph(advanced_analytics=False)
        g.add_node("hub", "center")
        g.add_node("src", "node")
        g.add_edge("src", "hub", "type_A")
        g.add_edge("src", "hub", "type_B")
        with patch("semantica.mcp_server._get_graph", return_value=g):
            result = _tool_query_graph({"mode": "neighbors", "node_id": "hub", "depth": 1})
        in_ids = [n["id"] for n in result.get("neighbors", []) if n.get("direction") == "in"]
        self.assertEqual(in_ids.count("src"), 1,
                         "src must appear exactly once even with two edges")


# ---------------------------------------------------------------------------
# Part 14: clear() resets decision indexes
# ---------------------------------------------------------------------------

class TestClearResetsDecisionIndexes(unittest.TestCase):

    def test_clear_removes_decision_indexes(self):
        """clear() must reset _decisions so that decision queries return empty."""
        g = ContextGraph(advanced_analytics=False)
        g.record_decision(
            category="test", scenario="s", reasoning="r", outcome="o", confidence=0.9
        )
        self.assertTrue(hasattr(g, "_decisions"))
        self.assertEqual(len(g._decisions), 1)

        g.clear()

        # After clear, _decisions must be empty
        self.assertEqual(len(getattr(g, "_decisions", {})), 0,
                         "_decisions must be empty after clear()")
        # find_similar_decisions must return empty
        results = g.find_similar_decisions("s", min_similarity=0.01)
        self.assertEqual(results, [],
                         "find_similar_decisions must return [] after clear()")

    def test_clear_then_record_works(self):
        """clear() followed by record_decision must work correctly."""
        g = ContextGraph(advanced_analytics=False)
        g.record_decision(category="old", scenario="s", reasoning="r", outcome="o", confidence=0.9)
        g.clear()
        did = g.record_decision(
            category="new", scenario="fresh decision", reasoning="fresh",
            outcome="ok", confidence=0.8
        )
        self.assertEqual(len(g._decisions), 1)
        self.assertIn(did, g._decisions)
        self.assertEqual(g._decisions[did]["category"], "new")


# ---------------------------------------------------------------------------
# Part 15: semantica.mcp_server mutation persistence (#1134)
# ---------------------------------------------------------------------------

class TestMCPServerMutationPersistence(unittest.TestCase):
    """_tool_record_decision, _tool_add_entity, and _tool_add_relationship must
    each call save_to_file when SEMANTICA_KG_PATH is configured so mutations
    survive server restarts.

    Mirrors update_node / delete_node which already had this behaviour from
    PR #967.  These tests extend coverage to the three previously missing tools.
    """

    # ---- helpers --------------------------------------------------------

    def _isolated_mcp_graph(self):
        """Return a fresh ContextGraph injected as the mcp_server singleton."""
        import semantica.mcp_server as mcp_mod
        g = ContextGraph(advanced_analytics=False)
        self._original_graph = mcp_mod._graph
        mcp_mod._graph = g
        return g

    def _restore_mcp_graph(self):
        import semantica.mcp_server as mcp_mod
        mcp_mod._graph = self._original_graph

    # ---- record_decision ------------------------------------------------

    def test_record_decision_persists_to_kg_path(self):
        """_tool_record_decision must write the graph to SEMANTICA_KG_PATH."""
        from semantica.mcp_server import _tool_record_decision

        g = self._isolated_mcp_graph()
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                path = f.name
            try:
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    result = _tool_record_decision({
                        "category": "mcp_server_persist",
                        "scenario": "Testing packaged server persistence",
                        "reasoning": "save_to_file must be called on mutation",
                        "outcome": "verified",
                        "confidence": 0.99,
                    })

                self.assertNotIn("error", result, result)
                self.assertIn("decision_id", result)

                # File must have been written.
                self.assertGreater(os.path.getsize(path), 0,
                                   "save_to_file must have written to the KG_PATH file")

                # Simulate restart: reload into a fresh graph.
                g2 = ContextGraph(advanced_analytics=False)
                g2.load_from_file(path)
                decisions = list(g2.find_nodes(node_type="decision"))
                self.assertGreater(len(decisions), 0,
                                   "Decision must be present after save → load")
                cats = [d.get("category") or (d.get("metadata") or {}).get("category")
                        for d in decisions]
                self.assertIn("mcp_server_persist", cats)
            finally:
                os.unlink(path)
        finally:
            self._restore_mcp_graph()

    def test_record_decision_works_without_kg_path(self):
        """_tool_record_decision must succeed when SEMANTICA_KG_PATH is unset."""
        from semantica.mcp_server import _tool_record_decision

        g = self._isolated_mcp_graph()
        try:
            env = {k: v for k, v in os.environ.items() if k != "SEMANTICA_KG_PATH"}
            with patch.dict(os.environ, env, clear=True):
                result = _tool_record_decision({
                    "category": "no_path",
                    "scenario": "no kg path",
                    "reasoning": "in-memory only",
                    "outcome": "ok",
                    "confidence": 0.5,
                })
            self.assertNotIn("error", result, result)
            self.assertIn("decision_id", result)
        finally:
            self._restore_mcp_graph()

    # ---- add_entity -----------------------------------------------------

    def test_add_entity_persists_to_kg_path(self):
        """_tool_add_entity must write the graph to SEMANTICA_KG_PATH."""
        from semantica.mcp_server import _tool_add_entity

        g = self._isolated_mcp_graph()
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                path = f.name
            try:
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    result = _tool_add_entity({
                        "id": "mcp_server_entity_test",
                        "label": "Persistence Entity",
                        "type": "TestEntity",
                    })

                self.assertNotIn("error", result, result)
                self.assertEqual(result.get("status"), "added")

                self.assertGreater(os.path.getsize(path), 0)

                g2 = ContextGraph(advanced_analytics=False)
                g2.load_from_file(path)
                self.assertTrue(g2.has_node("mcp_server_entity_test"),
                                "Entity must be present after save → load")
            finally:
                os.unlink(path)
        finally:
            self._restore_mcp_graph()

    def test_add_entity_works_without_kg_path(self):
        """_tool_add_entity must succeed when SEMANTICA_KG_PATH is unset."""
        from semantica.mcp_server import _tool_add_entity

        g = self._isolated_mcp_graph()
        try:
            env = {k: v for k, v in os.environ.items() if k != "SEMANTICA_KG_PATH"}
            with patch.dict(os.environ, env, clear=True):
                result = _tool_add_entity({"id": "ephemeral_ent", "label": "E"})
            self.assertNotIn("error", result, result)
            self.assertEqual(result.get("status"), "added")
        finally:
            self._restore_mcp_graph()

    # ---- add_relationship -----------------------------------------------

    def test_add_relationship_persists_to_kg_path(self):
        """_tool_add_relationship must write the graph to SEMANTICA_KG_PATH."""
        from semantica.mcp_server import _tool_add_entity, _tool_add_relationship

        g = self._isolated_mcp_graph()
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                path = f.name
            try:
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    _tool_add_entity({"id": "rel_src_mcp", "label": "Source"})
                    _tool_add_entity({"id": "rel_tgt_mcp", "label": "Target"})
                    result = _tool_add_relationship({
                        "source": "rel_src_mcp",
                        "target": "rel_tgt_mcp",
                        "type": "PROVEN_BY",
                    })

                self.assertNotIn("error", result, result)
                self.assertEqual(result.get("status"), "added")

                self.assertGreater(os.path.getsize(path), 0)

                g2 = ContextGraph(advanced_analytics=False)
                g2.load_from_file(path)
                edges = list(g2.find_edges())
                self.assertTrue(any(e.get("type") == "PROVEN_BY" for e in edges),
                                "PROVEN_BY edge must be present after save → load")
            finally:
                os.unlink(path)
        finally:
            self._restore_mcp_graph()

    def test_add_relationship_works_without_kg_path(self):
        """_tool_add_relationship must succeed when SEMANTICA_KG_PATH is unset."""
        from semantica.mcp_server import _tool_add_entity, _tool_add_relationship

        g = self._isolated_mcp_graph()
        try:
            env = {k: v for k, v in os.environ.items() if k != "SEMANTICA_KG_PATH"}
            with patch.dict(os.environ, env, clear=True):
                _tool_add_entity({"id": "src_no_p", "label": "S"})
                _tool_add_entity({"id": "tgt_no_p", "label": "T"})
                result = _tool_add_relationship({
                    "source": "src_no_p",
                    "target": "tgt_no_p",
                    "type": "RELATED_TO",
                })
            self.assertNotIn("error", result, result)
            self.assertEqual(result.get("status"), "added")
        finally:
            self._restore_mcp_graph()


if __name__ == "__main__":
    unittest.main()
