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


if __name__ == "__main__":
    unittest.main()
