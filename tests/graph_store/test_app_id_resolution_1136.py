"""Regression tests for the application-id / internal-id mismatch (#1136).

`GraphStore.add_edges` reads application-level string ids from
``source_id``/``target_id`` while backends such as Neo4j match relationships
on their internal integer ids (``id(n)``). Every edge therefore failed with
"nodes not found" and a graph persisted with all nodes and zero
relationships.

The fix keeps the application-id -> internal-id map that ``add_nodes``
already receives from the backend (instead of discarding it) and resolves
known string ids in ``create_relationship``. These tests pin that contract
with a fake manager — no live database needed.
"""

import unittest
from typing import Any, Dict, List, Optional, Tuple

from semantica.graph_store.graph_store import GraphStore


class FakeNodeManager:
    """Mimics NodeManager against a backend that mints internal integer ids."""

    def __init__(self) -> None:
        self._next_internal_id = 100
        self.created: List[Dict[str, Any]] = []

    def create_batch(
        self, nodes: List[Dict[str, Any]], **options: Any
    ) -> List[Dict[str, Any]]:
        created: List[Dict[str, Any]] = []
        for node in nodes:
            internal_id = self._next_internal_id
            self._next_internal_id += 1
            record = {
                "id": internal_id,
                "labels": node.get("labels", []),
                "properties": dict(node.get("properties", {})),
            }
            created.append(record)
            self.created.append(record)
        return created

    def create(
        self, labels: List[str], properties: Dict[str, Any], **options: Any
    ) -> Dict[str, Any]:
        return self.create_batch(
            [{"labels": labels, "properties": properties}], **options
        )[0]


class FakeRelationshipManager:
    """Records the resolved ids create_relationship hands to the backend."""

    def __init__(self) -> None:
        self.calls: List[Tuple[Any, Any, str]] = []

    def create(
        self,
        start_node_id: Any,
        end_node_id: Any,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        **options: Any,
    ) -> Dict[str, Any]:
        self.calls.append((start_node_id, end_node_id, rel_type))
        return {"start": start_node_id, "end": end_node_id, "type": rel_type}


class FakeManager:
    def __init__(self) -> None:
        self.nodes = FakeNodeManager()
        self.relationships = FakeRelationshipManager()


def make_store() -> Tuple[GraphStore, FakeManager]:
    """Build a GraphStore around fakes, skipping backend initialization."""
    store = GraphStore.__new__(GraphStore)
    store.logger = None  # type: ignore[assignment]
    store.progress_tracker = None  # type: ignore[assignment]
    store.backend = "fake"
    store.config = {}
    store._app_node_id_map = {}
    manager = FakeManager()
    store._store_backend = None
    store._manager = manager  # type: ignore[assignment]
    return store, manager


class AppIdResolutionTests(unittest.TestCase):
    def test_add_edges_resolves_application_ids_to_internal_ids(self) -> None:
        store, manager = make_store()

        node_count = store.add_nodes(
            [
                {"id": "e1", "type": "Person", "properties": {}},
                {"id": "e2", "type": "Organization", "properties": {}},
            ]
        )
        self.assertEqual(node_count, 2)

        edge_count = store.add_edges(
            [{"source_id": "e1", "target_id": "e2", "type": "knows"}]
        )

        self.assertEqual(edge_count, 1)
        self.assertEqual(len(manager.relationships.calls), 1)
        start, end, rel_type = manager.relationships.calls[0]
        self.assertEqual(start, 100, "source app id must resolve to the internal id")
        self.assertEqual(end, 101, "target app id must resolve to the internal id")
        self.assertEqual(rel_type, "knows")

    def test_build_from_entities_and_relationships_creates_the_edge(self) -> None:
        """The exact shape of the #1136 reproduction, against fakes."""
        store, manager = make_store()

        stats = store.build_from_entities_and_relationships(
            [
                {"id": "e1", "type": "Person", "text": "Alice"},
                {"id": "e2", "type": "Organization", "text": "Acme"},
            ],
            [{"source_id": "e1", "target_id": "e2", "type": "knows"}],
        )

        self.assertEqual(stats["statistics"]["node_count"], 2)
        self.assertEqual(
            stats["statistics"]["edge_count"], 1, "the edge must be created, not dropped"
        )
        self.assertEqual(manager.relationships.calls, [(100, 101, "knows")])

    def test_unknown_ids_pass_through_unchanged(self) -> None:
        """Ids the map does not know keep the pre-fix pass-through behavior."""
        store, manager = make_store()

        store.create_relationship(7, 8, "RELATES_TO")

        self.assertEqual(manager.relationships.calls, [(7, 8, "RELATES_TO")])

    def test_create_node_also_populates_the_map(self) -> None:
        store, manager = make_store()

        store.create_node(["Person"], {"id": "app-1", "name": "Alice"})
        store.add_edges([{"source_id": "app-1", "target_id": 42, "type": "knows"}])

        self.assertEqual(manager.relationships.calls, [(100, 42, "knows")])

    def test_integer_application_ids_never_collide_with_internal_ids(self) -> None:
        # Qodo review: an int application id must not be recorded/resolved,
        # or a caller passing that same int as an internal id would be
        # silently remapped to a different node.
        store, manager = make_store()

        store.add_nodes(
            [
                {"id": 100, "type": "Person", "properties": {}},
                {"id": "str-app", "type": "Person", "properties": {}},
            ]
        )
        # Internal id 100 legitimately targets the FIRST node; the integer
        # app id of that same value must not redirect it to the second.
        store.create_relationship(100, 101, "RELATES_TO")

        self.assertEqual(manager.relationships.calls, [(100, 101, "RELATES_TO")])
        self.assertNotIn(100, store._app_node_id_map)

    def test_nodes_without_application_id_do_not_pollute_the_map(self) -> None:
        store, manager = make_store()

        store.add_nodes([{"labels": ["Person"], "properties": {"name": "Anon"}}])
        store.create_relationship("not-mapped", 5, "RELATES_TO")

        self.assertEqual(manager.relationships.calls, [("not-mapped", 5, "RELATES_TO")])


if __name__ == "__main__":
    unittest.main()
