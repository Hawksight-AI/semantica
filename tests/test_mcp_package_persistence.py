"""Regression tests for root mcp/ graph persistence (issue #1134).

Covers:
  1. get_graph() loads an existing JSON file via load_from_file(), not the
     nonexistent .load() method  (the original bug).
  2. get_graph() with a nonexistent / unset SEMANTICA_KG_PATH starts cleanly.
  3. handle_record_decision persists to SEMANTICA_KG_PATH and the mutation
     survives a fresh load_from_file() call.
  4. handle_add_entity persists to SEMANTICA_KG_PATH and survives reload.
  5. handle_add_relationship persists to SEMANTICA_KG_PATH and survives reload.
  6. All three mutation tools work correctly when SEMANTICA_KG_PATH is unset
     (no errors, no persistence attempt).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from semantica.context.context_graph import ContextGraph

import mcp.session as _session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_graph() -> ContextGraph:
    """Return a minimal ContextGraph ready for use in tests."""
    g = ContextGraph(advanced_analytics=False)
    g.add_node("seed_node", node_type="entity", label="Seed")
    return g


class _IsolatedSession:
    """Context manager that resets the mcp.session singleton before and after
    each test so tests are independent of process-level state."""

    def __enter__(self):
        _session.reset_graph()
        return self

    def __exit__(self, *_):
        _session.reset_graph()


# ---------------------------------------------------------------------------
# 1. get_graph() loading — regression against _graph.load()
# ---------------------------------------------------------------------------

class TestMCPSessionLoad(unittest.TestCase):
    """get_graph() must load an existing file using load_from_file(), not .load()."""

    def test_get_graph_loads_existing_kg_path(self):
        """When SEMANTICA_KG_PATH points to a valid JSON file the graph must
        contain the persisted nodes after get_graph() returns."""
        g = _fresh_graph()
        g.add_node("persistent_node", node_type="entity", label="Should survive")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)

            with _IsolatedSession():
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    loaded = _session.get_graph()

                self.assertTrue(
                    loaded.has_node("persistent_node"),
                    "Node saved before server start must be present after load",
                )
                self.assertTrue(
                    loaded.has_node("seed_node"),
                    "seed_node from the persisted graph must also be present",
                )
        finally:
            os.unlink(path)

    def test_get_graph_with_nonexistent_kg_path_starts_empty(self):
        """When SEMANTICA_KG_PATH does not exist the graph initialises empty
        (no error) — matching pre-existing behaviour."""
        with _IsolatedSession():
            with patch.dict(os.environ, {"SEMANTICA_KG_PATH": "/nonexistent/path.json"}):
                loaded = _session.get_graph()

        # An empty graph has no nodes; at minimum it must be a ContextGraph.
        self.assertIsNotNone(loaded)
        nodes = list(loaded.find_nodes())
        self.assertEqual(nodes, [], "Graph must be empty when KG_PATH does not exist")

    def test_get_graph_without_kg_path_starts_empty(self):
        """When SEMANTICA_KG_PATH is absent the graph initialises empty."""
        with _IsolatedSession():
            env = {k: v for k, v in os.environ.items() if k != "SEMANTICA_KG_PATH"}
            with patch.dict(os.environ, env, clear=True):
                loaded = _session.get_graph()

        self.assertIsNotNone(loaded)

    def test_get_graph_uses_load_from_file_not_load(self):
        """Regression: ContextGraph has no .load() method; get_graph() must
        call load_from_file() or the AttributeError is silently swallowed and
        the graph silently stays empty.  This test verifies the fix directly."""
        g = _fresh_graph()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            g.save_to_file(path)

            with _IsolatedSession():
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    # If the old _graph.load(path) bug were present the graph
                    # would be empty (exception swallowed).  With the fix the
                    # node must be present.
                    loaded = _session.get_graph()

                self.assertTrue(
                    loaded.has_node("seed_node"),
                    "load_from_file must have been called; if .load() was used "
                    "the AttributeError is swallowed and the graph stays empty",
                )
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 2–5. Mutation persistence
# ---------------------------------------------------------------------------

class TestMCPPackageMutationPersistence(unittest.TestCase):
    """Mutations via the root mcp/ tool handlers must persist to SEMANTICA_KG_PATH
    so the data survives a server restart (simulated by a fresh load_from_file)."""

    # ---- record_decision ------------------------------------------------

    def test_record_decision_persists_when_kg_path_set(self):
        """handle_record_decision must write to disk when SEMANTICA_KG_PATH is set."""
        from mcp.tools.decisions import handle_record_decision

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            with _IsolatedSession():
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    result = handle_record_decision({
                        "category": "test_persistence",
                        "scenario": "Verifying mcp/ decision persistence",
                        "reasoning": "KG_PATH must be written on mutation",
                        "outcome": "verified",
                        "confidence": 0.99,
                    })

            self.assertNotIn("error", result, result)
            self.assertIn("decision_id", result)

            # The file must have been written (or overwritten from empty).
            self.assertTrue(os.path.exists(path), "save_to_file must create the file")
            self.assertGreater(os.path.getsize(path), 0, "Persisted file must not be empty")

            # Simulate server restart: load into a fresh graph.
            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)
            decisions = list(g2.find_nodes(node_type="decision"))
            self.assertGreater(len(decisions), 0, "Decision must survive reload")
            cats = [d.get("category") or (d.get("metadata") or {}).get("category")
                    for d in decisions]
            self.assertIn("test_persistence", cats,
                          "Decision category must be present after reload")
        finally:
            os.unlink(path)

    def test_record_decision_works_without_kg_path(self):
        """handle_record_decision must succeed even when SEMANTICA_KG_PATH is unset."""
        from mcp.tools.decisions import handle_record_decision

        with _IsolatedSession():
            env = {k: v for k, v in os.environ.items() if k != "SEMANTICA_KG_PATH"}
            with patch.dict(os.environ, env, clear=True):
                result = handle_record_decision({
                    "category": "no_path",
                    "scenario": "No persistence path configured",
                    "reasoning": "Should still work in-memory",
                    "outcome": "ok",
                    "confidence": 0.5,
                })

        self.assertNotIn("error", result, result)
        self.assertIn("decision_id", result)

    # ---- add_entity -----------------------------------------------------

    def test_add_entity_persists_when_kg_path_set(self):
        """handle_add_entity must write to disk when SEMANTICA_KG_PATH is set."""
        from mcp.tools.graph import handle_add_entity

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            with _IsolatedSession():
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    result = handle_add_entity({
                        "id": "entity_persist_test",
                        "label": "Persistence Test Entity",
                        "type": "TestType",
                    })

            self.assertNotIn("error", result, result)
            self.assertEqual(result.get("status"), "added")

            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 0)

            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)
            self.assertTrue(
                g2.has_node("entity_persist_test"),
                "Entity must be present in the graph after reload",
            )
        finally:
            os.unlink(path)

    def test_add_entity_works_without_kg_path(self):
        """handle_add_entity must succeed when SEMANTICA_KG_PATH is unset."""
        from mcp.tools.graph import handle_add_entity

        with _IsolatedSession():
            env = {k: v for k, v in os.environ.items() if k != "SEMANTICA_KG_PATH"}
            with patch.dict(os.environ, env, clear=True):
                result = handle_add_entity({"id": "no_path_entity", "label": "ephemeral"})

        self.assertNotIn("error", result, result)
        self.assertEqual(result.get("status"), "added")

    # ---- add_relationship -----------------------------------------------

    def test_add_relationship_persists_when_kg_path_set(self):
        """handle_add_relationship must write to disk when SEMANTICA_KG_PATH is set."""
        from mcp.tools.graph import handle_add_relationship

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            with _IsolatedSession():
                with patch.dict(os.environ, {"SEMANTICA_KG_PATH": path}):
                    # Nodes must exist before an edge can be added.
                    from mcp.tools.graph import handle_add_entity
                    handle_add_entity({"id": "rel_src", "label": "Source"})
                    handle_add_entity({"id": "rel_tgt", "label": "Target"})
                    result = handle_add_relationship({
                        "source": "rel_src",
                        "target": "rel_tgt",
                        "type": "TESTED_BY",
                    })

            self.assertNotIn("error", result, result)
            self.assertEqual(result.get("status"), "added")

            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 0)

            g2 = ContextGraph(advanced_analytics=False)
            g2.load_from_file(path)
            edges = list(g2.find_edges())
            edge_types = [e.get("type") for e in edges]
            self.assertIn("TESTED_BY", edge_types,
                          "Relationship must be present after reload")
        finally:
            os.unlink(path)

    def test_add_relationship_works_without_kg_path(self):
        """handle_add_relationship must succeed when SEMANTICA_KG_PATH is unset."""
        from mcp.tools.graph import handle_add_entity, handle_add_relationship

        with _IsolatedSession():
            env = {k: v for k, v in os.environ.items() if k != "SEMANTICA_KG_PATH"}
            with patch.dict(os.environ, env, clear=True):
                handle_add_entity({"id": "src_no_path", "label": "S"})
                handle_add_entity({"id": "tgt_no_path", "label": "T"})
                result = handle_add_relationship({
                    "source": "src_no_path",
                    "target": "tgt_no_path",
                    "type": "RELATED_TO",
                })

        self.assertNotIn("error", result, result)
        self.assertEqual(result.get("status"), "added")


if __name__ == "__main__":
    unittest.main()
