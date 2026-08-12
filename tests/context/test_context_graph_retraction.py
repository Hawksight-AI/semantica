"""Tests for ContextGraph retraction and purge (issue #955).

``ContextGraph`` had 56 public methods and none that removed anything: the only
option was ``clear()``, which discards the whole graph. Two operations are
added, with deliberately different contracts.

Retraction closes an entity's validity window. The entity stops being active
going forward, but ``state_at()`` before the retraction still returns it, so
decisions recorded against it remain explainable. Purge is destructive: the
entity is gone from history too, leaving only a tombstone recording that a
purge happened and why -- never the purged content.

The audit-trail assertions run against a real ``TemporalVersionManager`` rather
than a mock callback, since the behaviour under test is precisely that these
operations reach the existing mutation-recording path.
"""

import threading
import unittest

from semantica.change_management import TemporalVersionManager
from semantica.context import ContextGraph

BEFORE = "2025-06-01T00:00:00Z"
CUTOFF = "2026-01-01T00:00:00Z"
AFTER = "2026-06-01T00:00:00Z"


def _graph():
    """alice --works_at--> acme, plus an unrelated bob."""
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("alice", "person")
    graph.add_node("acme", "org")
    graph.add_node("bob", "person")
    graph.add_edge("alice", "acme", "works_at")
    return graph


def _ids_at(graph, when):
    return {node.get("id") for node in graph.state_at(when).get("nodes", [])}


def _index_totals(graph):
    return {
        "nodes": len(graph.nodes),
        "node_index": sum(len(v) for v in graph.node_type_index.values()),
        "edges": len(graph.edges),
        "edge_index": sum(len(v) for v in graph.edge_type_index.values()),
        "adjacency": sum(len(v) for v in graph._adjacency.values()),
    }


class TestRetractNode(unittest.TestCase):
    def test_retracted_node_leaves_the_active_view(self):
        graph = _graph()
        self.assertTrue(graph.retract_node("alice", at=CUTOFF))
        active = {node["id"] for node in graph.find_active_nodes()}
        self.assertNotIn("alice", active)
        self.assertIn("bob", active)

    def test_history_before_the_retraction_is_preserved(self):
        graph = _graph()
        graph.retract_node("alice", at=CUTOFF)
        self.assertIn("alice", _ids_at(graph, BEFORE))
        self.assertNotIn("alice", _ids_at(graph, AFTER))

    def test_retraction_record_captures_reason_and_time(self):
        graph = _graph()
        graph.retract_node("alice", reason="employment ended", at=CUTOFF)
        record = graph.get_retraction("alice")
        self.assertEqual(record["entity_id"], "alice")
        self.assertEqual(record["entity_kind"], "node")
        self.assertEqual(record["reason"], "employment ended")
        self.assertIn("2026-01-01", record["retracted_at"])

    def test_retracting_twice_is_a_no_op(self):
        graph = _graph()
        self.assertTrue(graph.retract_node("alice", reason="first", at=CUTOFF))
        self.assertFalse(graph.retract_node("alice", reason="second"))
        self.assertEqual(graph.get_retraction("alice")["reason"], "first")

    def test_retracting_an_unknown_node_returns_false(self):
        graph = _graph()
        self.assertFalse(graph.retract_node("nobody"))
        self.assertIsNone(graph.get_retraction("nobody"))

    def test_cascade_retracts_incident_edges_in_both_directions(self):
        graph = _graph()
        graph.add_edge("bob", "alice", "knows")  # inbound, not in _adjacency['alice']
        graph.retract_node("alice", at=CUTOFF)
        for edge in graph.edges:
            self.assertIsNotNone(
                graph.get_retraction(edge.edge_id),
                f"edge {edge.edge_type} touching alice was not retracted",
            )

    def test_cascade_can_be_disabled(self):
        graph = _graph()
        graph.retract_node("alice", at=CUTOFF, cascade=False)
        edge = graph.edges[0]
        self.assertIsNone(graph.get_retraction(edge.edge_id))

    def test_retraction_does_not_remove_the_record(self):
        """Retraction is a temporal change, not a deletion."""
        graph = _graph()
        graph.retract_node("alice", at=CUTOFF)
        self.assertTrue(graph.has_node("alice"))
        self.assertIsNotNone(graph.find_node("alice"))


class TestRetractEdge(unittest.TestCase):
    def test_edge_is_retracted_without_touching_endpoints(self):
        graph = _graph()
        edge_id = graph.edges[0].edge_id
        self.assertTrue(graph.retract_edge(edge_id, reason="wrong extraction"))
        self.assertIsNotNone(graph.get_retraction(edge_id))
        active = {node["id"] for node in graph.find_active_nodes()}
        self.assertIn("alice", active)
        self.assertIn("acme", active)

    def test_retracting_an_unknown_edge_returns_false(self):
        self.assertFalse(_graph().retract_edge("no-such-edge"))

    def test_retracting_an_edge_twice_is_a_no_op(self):
        graph = _graph()
        edge_id = graph.edges[0].edge_id
        self.assertTrue(graph.retract_edge(edge_id))
        self.assertFalse(graph.retract_edge(edge_id))


class TestPurge(unittest.TestCase):
    def test_purged_node_is_absent_from_history(self):
        graph = _graph()
        self.assertTrue(graph.purge_node("alice", reason="erasure request #1"))
        self.assertNotIn("alice", _ids_at(graph, BEFORE))
        self.assertFalse(graph.has_node("alice"))

    def test_tombstone_records_the_purge_without_the_content(self):
        graph = ContextGraph(advanced_analytics=False)
        graph.add_node("alice", "person", email="alice@example.com")
        graph.purge_node("alice", reason="erasure request #1")

        tombstone = graph.get_tombstone("alice")
        self.assertEqual(tombstone["entity_id"], "alice")
        self.assertEqual(tombstone["reason"], "erasure request #1")
        self.assertIn("purged_at", tombstone)
        self.assertNotIn(
            "alice@example.com",
            str(tombstone),
            "tombstone retained purged content, defeating the purpose of a purge",
        )

    def test_purge_cascades_to_incident_edges(self):
        graph = _graph()
        graph.add_edge("bob", "alice", "knows")
        graph.purge_node("alice")
        remaining = {(e.source_id, e.target_id) for e in graph.edges}
        self.assertEqual(remaining, set())

    def test_purge_keeps_every_index_consistent(self):
        """The invariant clear() already upholds must hold here too."""
        graph = ContextGraph(advanced_analytics=False)
        for i in range(5):
            graph.add_node(f"n{i}", f"t{i % 2}")
        graph.add_edge("n0", "n1", "a")
        graph.add_edge("n1", "n2", "b")
        graph.add_edge("n2", "n0", "a")
        graph.add_edge("n3", "n0", "b")

        graph.purge_node("n0")

        totals = _index_totals(graph)
        self.assertEqual(totals["node_index"], totals["nodes"])
        self.assertEqual(totals["edge_index"], totals["edges"])
        self.assertEqual(totals["adjacency"], totals["edges"])
        self.assertEqual(totals["edges"], 1)  # only n1->n2 survives

    def test_purge_edge_leaves_endpoints_in_place(self):
        graph = _graph()
        edge_id = graph.edges[0].edge_id
        self.assertTrue(graph.purge_edge(edge_id))
        self.assertEqual(len(graph.edges), 0)
        self.assertTrue(graph.has_node("alice"))
        self.assertTrue(graph.has_node("acme"))
        totals = _index_totals(graph)
        self.assertEqual(totals["edge_index"], 0)
        self.assertEqual(totals["adjacency"], 0)

    def test_purging_unknown_entities_returns_false(self):
        graph = _graph()
        self.assertFalse(graph.purge_node("nobody"))
        self.assertFalse(graph.purge_edge("no-such-edge"))

    def test_purge_supersedes_an_earlier_retraction(self):
        graph = _graph()
        graph.retract_node("alice", reason="left", at=CUTOFF)
        graph.purge_node("alice", reason="erasure request #2")
        self.assertIsNone(graph.get_retraction("alice"))
        self.assertIsNotNone(graph.get_tombstone("alice"))


class TestClearResetsRecords(unittest.TestCase):
    def test_clear_drops_retractions_and_tombstones(self):
        graph = _graph()
        graph.retract_node("alice", at=CUTOFF)
        graph.purge_node("bob")
        graph.clear()
        self.assertEqual(graph.list_retractions(), [])
        self.assertEqual(graph.list_tombstones(), [])


class TestAuditTrailIntegration(unittest.TestCase):
    """Against the real TemporalVersionManager, not a mock callback."""

    def _attached(self):
        manager = TemporalVersionManager()
        graph = _graph()
        manager.attach_to_graph(graph)
        return manager, graph

    def _ops(self, manager, entity_id):
        history = manager.storage.get_entity_history(entity_id) or []
        return [entry.get("operation") for entry in history]

    def test_retraction_is_recorded_as_an_update(self):
        manager, graph = self._attached()
        graph.retract_node("alice", reason="left", at=CUTOFF)
        self.assertIn("UPDATE_NODE", self._ops(manager, "alice"))

    def test_purge_is_recorded_as_a_removal(self):
        manager, graph = self._attached()
        graph.purge_node("acme", reason="erasure request #3")
        self.assertIn("REMOVE_NODE", self._ops(manager, "acme"))

    def test_operations_use_the_documented_mutation_vocabulary(self):
        """MutationRecord documents ADD/UPDATE/REMOVE for nodes and edges."""
        manager, graph = self._attached()
        graph.retract_node("alice", at=CUTOFF)
        graph.purge_node("bob")
        allowed = {
            "ADD_NODE",
            "UPDATE_NODE",
            "REMOVE_NODE",
            "ADD_EDGE",
            "UPDATE_EDGE",
            "REMOVE_EDGE",
        }
        seen = set()
        for entity_id in ("alice", "acme", "bob"):
            seen.update(self._ops(manager, entity_id))
        self.assertTrue(seen)
        self.assertTrue(
            seen <= allowed, f"undocumented mutation operation(s): {seen - allowed}"
        )


class TestConcurrency(unittest.TestCase):
    def test_concurrent_purges_keep_indexes_consistent(self):
        """Post-condition, not timing: threads must finish and indexes agree."""
        graph = ContextGraph(advanced_analytics=False)
        for i in range(60):
            graph.add_node(f"n{i}", "t")
        for i in range(59):
            graph.add_edge(f"n{i}", f"n{i + 1}", "rel")

        errors = []

        def purge(start):
            try:
                for i in range(start, 60, 4):
                    graph.purge_node(f"n{i}")
            except Exception as exc:  # surfaced below, never swallowed
                errors.append(f"{type(exc).__name__}: {exc}")

        threads = [
            threading.Thread(target=purge, args=(offset,)) for offset in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual([t.name for t in threads if t.is_alive()], [])
        self.assertEqual(errors, [])
        self.assertEqual(len(graph.nodes), 0)
        totals = _index_totals(graph)
        self.assertEqual(totals["node_index"], 0)
        self.assertEqual(totals["edge_index"], 0)
        self.assertEqual(totals["adjacency"], 0)
        self.assertEqual(totals["edges"], 0)


if __name__ == "__main__":
    unittest.main()
