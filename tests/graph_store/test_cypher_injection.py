"""Regression tests for GHSA-482h-hw99-h62p: unvalidated node labels and
property keys allowed arbitrary Cypher injection in the Neptune, Neo4j, and
FalkorDB graph stores (labels/keys can't be bound as query parameters, so
an unvalidated value reaching the query string is a direct injection
point).

Mirrors the advisory's own PoC shape: a label/key crafted to close the
current Cypher token early and append a destructive statement
(`DETACH DELETE victim`). Before the fix, these reached `_run_query` /
`session.run` / `graph.query` verbatim. After the fix, `sanitize_identifier`
(graph_store/query_sanitize.py) rejects them with ValidationError before
any query is built, matching the existing age_store.py `_sanitize_label`
behavior used as the reference implementation.
"""

import pytest
import unittest
from unittest.mock import MagicMock

from semantica.graph_store.query_sanitize import sanitize_identifier
from semantica.utils.exceptions import ProcessingError, ValidationError

# AmazonNeptuneStore/Neo4jStore/FalkorDBStore.create_node() wrap their whole
# body in `except Exception: raise ProcessingError(...)` (pre-existing,
# unrelated to this fix), so the ValidationError sanitize_identifier raises
# surfaces to callers as ProcessingError. Either way the malicious query is
# never built or sent — these tests assert exactly that via the query-capture
# stubs, and check the wrapped message to confirm it's the sanitizer firing.

EVIL_LABEL = "N}) MATCH (victim) DETACH DELETE victim //"
EVIL_KEY = "k1`: 1}) MATCH (victim) DETACH DELETE victim //"


def _wire(store):
    store.logger = MagicMock()
    store.progress_tracker = MagicMock()
    store.progress_tracker.start_tracking.return_value = "tid"
    store.config = {}
    return store


class TestSanitizeIdentifier(unittest.TestCase):
    def test_valid_identifiers_pass_through_unchanged(self):
        self.assertEqual(sanitize_identifier("Person"), "Person")
        self.assertEqual(sanitize_identifier("_hidden"), "_hidden")
        self.assertEqual(sanitize_identifier("Rel_Type2"), "Rel_Type2")

    def test_injection_payload_is_rejected(self):
        with self.assertRaises(ValidationError):
            sanitize_identifier(EVIL_LABEL)

    def test_property_key_injection_payload_is_rejected(self):
        with self.assertRaises(ValidationError):
            sanitize_identifier(EVIL_KEY)

    def test_rejects_non_string(self):
        with self.assertRaises(ValidationError):
            sanitize_identifier(123)  # type: ignore[arg-type]

    def test_rejects_spaces_and_dashes(self):
        with self.assertRaises(ValidationError):
            sanitize_identifier("no spaces")
        with self.assertRaises(ValidationError):
            sanitize_identifier("no-dashes")


class TestAmazonNeptuneCypherInjection(unittest.TestCase):
    def _make_store(self):
        from semantica.graph_store.amazon_neptune import AmazonNeptuneStore

        store = _wire(AmazonNeptuneStore.__new__(AmazonNeptuneStore))
        store._connected = True
        store._ensure_connected = lambda: None
        store._generate_id = lambda: "generated-id"
        store._run_query = MagicMock(return_value=[])
        store._parse_results = lambda r: []
        return store

    def test_create_node_rejects_malicious_label_before_querying(self):
        store = self._make_store()
        with self.assertRaises(ProcessingError) as ctx:
            store.create_node(labels=[EVIL_LABEL], properties={"name": "x"})
        self.assertIn("Invalid label", str(ctx.exception))
        store._run_query.assert_not_called()

    def test_create_node_rejects_malicious_property_key_before_querying(self):
        store = self._make_store()
        with self.assertRaises(ProcessingError) as ctx:
            store.create_node(labels=["Person"], properties={"name": "x", EVIL_KEY: 1})
        self.assertIn("Invalid property key", str(ctx.exception))
        store._run_query.assert_not_called()

    def test_create_node_with_legitimate_labels_still_works(self):
        store = self._make_store()
        store.create_node(labels=["Person", "Employee"], properties={"name": "Alice"})
        query = store._run_query.call_args[0][0]
        self.assertIn("Person:Employee", query)
        self.assertNotIn("DETACH DELETE", query)


class TestNeo4jCypherInjection(unittest.TestCase):
    def _make_store(self):
        from semantica.graph_store import neo4j_store as m

        store = _wire(m.Neo4jStore.__new__(m.Neo4jStore))
        captured = {}

        class Session:
            def run(self, q, params=None):
                captured["query"] = q
                rec = {"n": {"name": "x"}, "id": 1}
                return type("R", (), {"single": lambda self: rec})()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        store.get_session = lambda: Session()
        store._captured = captured
        return store

    def test_create_node_rejects_malicious_label_before_querying(self):
        store = self._make_store()
        with self.assertRaises(ProcessingError) as ctx:
            store.create_node(labels=["Person", EVIL_LABEL], properties={"name": "x"})
        self.assertIn("Invalid label", str(ctx.exception))
        self.assertNotIn("query", store._captured)

    def test_create_relationship_rejects_malicious_rel_type(self):
        store = self._make_store()
        with self.assertRaises(ProcessingError) as ctx:
            store.create_relationship(start_node_id=1, end_node_id=2, rel_type=EVIL_LABEL)
        self.assertIn("Invalid relationship type", str(ctx.exception))
        self.assertNotIn("query", store._captured)


class TestFalkorDBCypherInjection(unittest.TestCase):
    def _make_store(self):
        from semantica.graph_store import falkordb_store as m

        store = _wire(m.FalkorDBStore.__new__(m.FalkorDBStore))
        captured = {}

        class Graph:
            def query(self, q, params=None):
                captured["query"] = q
                return type("R", (), {"result_set": []})()

        store._ensure_graph = lambda: Graph()
        store._captured = captured
        return store

    def test_create_node_rejects_malicious_label_and_key(self):
        store = self._make_store()
        with self.assertRaises(ProcessingError) as ctx:
            store.create_node(labels=[EVIL_LABEL], properties={"name": "x", EVIL_KEY: 1})
        self.assertIn("Invalid label", str(ctx.exception))
        self.assertNotIn("query", store._captured)

    def test_create_node_with_legitimate_input_still_works(self):
        store = self._make_store()
        store.create_node(labels=["Person"], properties={"name": "Alice"})
        query = store._captured["query"]
        self.assertIn("Person", query)
        self.assertNotIn("DETACH DELETE", query)


# ---------------------------------------------------------------------------
# BLOCKER 1 regression: Neo4jStore.get_neighbors / shortest_path depth coercion
# ---------------------------------------------------------------------------
# Payload representative of the confirmed injection (review BLOCKER 1):
# supplying a string as `depth` / `max_depth` previously reached the Cypher
# f-string verbatim because Neo4jStore did not call int() like Neptune/FalkorDB.
#
# After the fix `depth = int(depth)` / `max_depth = int(max_depth)` are added
# at the top of each method's try-block.  A malicious string raises ValueError
# (wrapped in ProcessingError), and the session.run / _run_query mock must
# never be called.

EVIL_DEPTH = "1]->(x) DETACH DELETE x //"


class TestNeo4jDepthInjection(unittest.TestCase):
    """Regression tests for BLOCKER 1: Neo4jStore depth/max_depth coercion."""

    def _make_store(self):
        """Build a Neo4jStore with a session that records every query string sent to it."""
        from semantica.graph_store import neo4j_store as m

        store = _wire(m.Neo4jStore.__new__(m.Neo4jStore))
        captured = {}

        class IterSession:
            """Returns an empty iterator so get_neighbors' for-loop completes cleanly."""
            def run(self, q, params=None):
                captured["query"] = q
                return iter([])

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class SingleSession:
            """Returns a FakeResult whose .single() yields None (shortest_path)."""
            def run(self, q, params=None):
                captured["query"] = q
                return type("R", (), {"single": lambda self: None})()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        store._captured = captured
        store._iter_session = IterSession
        store._single_session = SingleSession
        return store

    # -- get_neighbors --------------------------------------------------------

    def test_get_neighbors_malicious_depth_raises_before_query(self):
        """Malicious string depth must never reach session.run."""
        store = self._make_store()
        store.get_session = lambda: store._iter_session()
        with self.assertRaises(ProcessingError):
            store.get_neighbors(node_id=1, depth=EVIL_DEPTH)
        self.assertNotIn("query", store._captured,
                         "session.run was called — injected query reached the database layer")

    def test_get_neighbors_malicious_depth_does_not_contain_payload(self):
        """Double-check: if somehow a query were built, it must not contain the payload."""
        store = self._make_store()
        store.get_session = lambda: store._iter_session()
        with pytest.raises(ProcessingError):
            store.get_neighbors(node_id=1, depth=EVIL_DEPTH)
        query = store._captured.get("query", "")
        self.assertNotIn("DETACH DELETE", query,
                         f"Injection payload found in query: {query!r}")

    def test_get_neighbors_legitimate_depth_works(self):
        """Valid integer depth must still produce a correct traversal pattern."""
        store = self._make_store()
        store.get_session = lambda: store._iter_session()
        result = store.get_neighbors(node_id=1, depth=2)
        self.assertIsInstance(result, list)
        self.assertIn("query", store._captured)
        self.assertIn("*1..2", store._captured["query"])
        self.assertNotIn("DETACH DELETE", store._captured["query"])

    def test_get_neighbors_depth_string_int_is_coerced(self):
        """A string representation of a valid integer must be coerced and work."""
        store = self._make_store()
        store.get_session = lambda: store._iter_session()
        result = store.get_neighbors(node_id=1, depth="3")
        self.assertIsInstance(result, list)
        self.assertIn("*1..3", store._captured["query"])

    # -- shortest_path --------------------------------------------------------

    def test_shortest_path_malicious_max_depth_raises_before_query(self):
        """Malicious string max_depth must never reach session.run."""
        store = self._make_store()
        store.get_session = lambda: store._single_session()
        with self.assertRaises(ProcessingError):
            store.shortest_path(start_node_id=1, end_node_id=2, max_depth=EVIL_DEPTH)
        self.assertNotIn("query", store._captured,
                         "session.run was called — injected query reached the database layer")

    def test_shortest_path_malicious_max_depth_does_not_contain_payload(self):
        store = self._make_store()
        store.get_session = lambda: store._single_session()
        with pytest.raises(ProcessingError):
            store.shortest_path(start_node_id=1, end_node_id=2, max_depth=EVIL_DEPTH)
        query = store._captured.get("query", "")
        self.assertNotIn("DETACH DELETE", query,
                         f"Injection payload found in query: {query!r}")

    def test_shortest_path_legitimate_max_depth_works(self):
        """Valid integer max_depth must produce a correct shortestPath pattern."""
        store = self._make_store()
        store.get_session = lambda: store._single_session()
        result = store.shortest_path(start_node_id=1, end_node_id=2, max_depth=5)
        self.assertIsNone(result)          # single() returns None → correct
        self.assertIn("query", store._captured)
        self.assertIn("*..5", store._captured["query"])
        self.assertNotIn("DETACH DELETE", store._captured["query"])

    def test_shortest_path_max_depth_string_int_is_coerced(self):
        store = self._make_store()
        store.get_session = lambda: store._single_session()
        store.shortest_path(start_node_id=1, end_node_id=2, max_depth="7")
        self.assertIn("*..7", store._captured["query"])


# ---------------------------------------------------------------------------
# BLOCKER 2 regression: GraphStore.get_neighbors hops forwarding
# ---------------------------------------------------------------------------
# Before the fix, GraphStore.get_neighbors() set:
#   actual_depth = options.get("hops", depth)
# and forwarded the raw value to Neo4jStore.get_neighbors(depth=actual_depth).
# Because Neo4jStore did not coerce depth, an attacker-controlled hops string
# reached Cypher verbatim.
#
# The fix adds int() at the GraphStore facade:
#   actual_depth = int(options.get("hops", depth))
# This closes the path regardless of which backend is wired up.

class TestGraphStoreHopsForwarding(unittest.TestCase):
    """Regression tests for BLOCKER 2: GraphStore hops→depth forwarding."""

    def _make_graph_store_with_neo4j(self):
        """
        Wire a GraphStore whose backend is a Neo4j store stub that records every
        query passed to session.run.  Returns (graph_store, captured_dict).
        """
        from semantica.graph_store import neo4j_store as m
        from semantica.graph_store.graph_store import (
            GraphAnalytics,
            GraphManager,
            GraphStore,
        )

        captured = {}

        class IterSession:
            def run(self, q, params=None):
                captured["query"] = q
                return iter([])

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        neo4j_stub = _wire(m.Neo4jStore.__new__(m.Neo4jStore))
        neo4j_stub.get_session = lambda: IterSession()

        gs = GraphStore.__new__(GraphStore)
        gs.logger = MagicMock()
        gs.progress_tracker = MagicMock()
        gs._store_backend = neo4j_stub
        gs._manager = GraphManager(neo4j_stub)

        return gs, captured

    # -- hops injection -------------------------------------------------------

    def test_hops_malicious_string_raises_before_query(self):
        """Malicious hops string must be rejected before session.run is reached."""
        gs, captured = self._make_graph_store_with_neo4j()
        with self.assertRaises(Exception):
            gs.get_neighbors(node_id=1, hops=EVIL_DEPTH)
        self.assertNotIn("query", captured,
                         "session.run was called — injected hops reached the database layer")

    def test_hops_malicious_string_payload_not_in_any_query(self):
        """Belt-and-suspenders: payload text must not appear in any built query."""
        gs, captured = self._make_graph_store_with_neo4j()
        with pytest.raises(ValueError):
            gs.get_neighbors(node_id=1, hops=EVIL_DEPTH)
        query = captured.get("query", "")
        self.assertNotIn("DETACH DELETE", query,
                         f"Injection payload found in forwarded query: {query!r}")

    def test_hops_legitimate_integer_works(self):
        """Valid integer hops value must produce a correct query."""
        gs, captured = self._make_graph_store_with_neo4j()
        result = gs.get_neighbors(node_id=1, hops=2)
        self.assertIsInstance(result, list)
        self.assertIn("query", captured)
        self.assertIn("*1..2", captured["query"])
        self.assertNotIn("DETACH DELETE", captured["query"])

    def test_hops_string_int_is_coerced_and_works(self):
        """String '3' forwarded as hops must be coerced to int and produce *1..3."""
        gs, captured = self._make_graph_store_with_neo4j()
        result = gs.get_neighbors(node_id=1, hops="3")
        self.assertIsInstance(result, list)
        self.assertIn("*1..3", captured["query"])

    def test_depth_param_still_works_without_hops(self):
        """depth positional arg (no hops kwarg) must still be coerced and forwarded."""
        gs, captured = self._make_graph_store_with_neo4j()
        result = gs.get_neighbors(node_id=1, depth=4)
        self.assertIsInstance(result, list)
        self.assertIn("*1..4", captured["query"])


if __name__ == "__main__":
    unittest.main()
