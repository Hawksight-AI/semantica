import unittest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List, Optional
from semantica.graph_store.graph_store import GraphStore

class MockGraphStore:
    def __init__(self, **config):
        self.config = config
        self.nodes = {}
        self.relationships = {}
        self.node_counter = 0
        self.rel_counter = 0
        self.connected = False

    def connect(self, **options):
        self.connected = True
        return True

    def close(self):
        self.connected = False

    def create_node(self, labels: List[str], properties: Dict[str, Any], **options) -> Dict[str, Any]:
        self.node_counter += 1
        node_id = self.node_counter
        node = {
            "id": node_id,
            "labels": labels,
            "properties": properties
        }
        self.nodes[node_id] = node
        return node

    def create_nodes(self, nodes: List[Dict[str, Any]], **options) -> List[Dict[str, Any]]:
        created = []
        for node_data in nodes:
            created.append(self.create_node(node_data.get("labels", []), node_data.get("properties", {})))
        return created

    def get_node(self, node_id: int, **options) -> Optional[Dict[str, Any]]:
        return self.nodes.get(node_id)

    def get_nodes(self, labels: Optional[List[str]] = None, properties: Optional[Dict[str, Any]] = None, limit: int = 100, **options) -> List[Dict[str, Any]]:
        result = []
        for node in self.nodes.values():
            if labels:
                if not any(label in node["labels"] for label in labels):
                    continue
            if properties:
                match = True
                for k, v in properties.items():
                    if node["properties"].get(k) != v:
                        match = False
                        break
                if not match:
                    continue
            result.append(node)
            if len(result) >= limit:
                break
        return result

    def update_node(self, node_id: int, properties: Dict[str, Any], merge: bool = True, **options) -> Dict[str, Any]:
        if node_id not in self.nodes:
            raise Exception(f"Node {node_id} not found")
        
        if merge:
            self.nodes[node_id]["properties"].update(properties)
        else:
            self.nodes[node_id]["properties"] = properties
        return self.nodes[node_id]

    def delete_node(self, node_id: int, detach: bool = True, **options) -> bool:
        if node_id in self.nodes:
            del self.nodes[node_id]
            # Handle detach (delete relationships) if needed
            if detach:
                to_delete = []
                for rel_id, rel in self.relationships.items():
                    if rel["start_node_id"] == node_id or rel["end_node_id"] == node_id:
                        to_delete.append(rel_id)
                for rel_id in to_delete:
                    del self.relationships[rel_id]
            return True
        return False

    def create_relationship(self, start_node_id: int, end_node_id: int, rel_type: str, properties: Optional[Dict[str, Any]] = None, **options) -> Dict[str, Any]:
        if start_node_id not in self.nodes or end_node_id not in self.nodes:
            raise Exception("Nodes not found")
        
        self.rel_counter += 1
        rel_id = self.rel_counter
        rel = {
            "id": rel_id,
            "start_node_id": start_node_id,
            "end_node_id": end_node_id,
            "type": rel_type,
            "properties": properties or {}
        }
        self.relationships[rel_id] = rel
        return rel

    def get_relationships(self, node_id: Optional[int] = None, rel_type: Optional[str] = None, direction: str = "both", limit: int = 100, **options) -> List[Dict[str, Any]]:
        result = []
        for rel in self.relationships.values():
            if node_id is not None:
                if direction == "out" and rel["start_node_id"] != node_id:
                    continue
                elif direction == "in" and rel["end_node_id"] != node_id:
                    continue
                elif direction == "both" and rel["start_node_id"] != node_id and rel["end_node_id"] != node_id:
                    continue
            
            if rel_type and rel["type"] != rel_type:
                continue
                
            result.append(rel)
            if len(result) >= limit:
                break
        return result

    def delete_relationship(self, rel_id: int, **options) -> bool:
        if rel_id in self.relationships:
            del self.relationships[rel_id]
            return True
        return False

    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None, **options) -> Dict[str, Any]:
        return {"records": [], "summary": "Mock query executed"}

    def get_stats(self) -> Dict[str, Any]:
        return {"nodes": len(self.nodes), "relationships": len(self.relationships)}
        
    def create_index(self, label: str, property_name: str, index_type: str = "btree", **options) -> bool:
        return True

    def shortest_path(self, start_node_id: int, end_node_id: int, rel_type: Optional[str] = None, max_depth: int = 10, **options) -> Optional[Dict[str, Any]]:
        return None # Simplified

    def get_neighbors(self, node_id: int, rel_type: Optional[str] = None, direction: str = "both", depth: int = 1, **options) -> List[Dict[str, Any]]:
        return [] # Simplified

class TestGraphStore(unittest.TestCase):
    def setUp(self):
        # Patch Neo4jStore to return our MockGraphStore
        self.patcher = patch('semantica.graph_store.neo4j_store.Neo4jStore', side_effect=MockGraphStore)
        self.mock_store_class = self.patcher.start()
        
        # Initialize GraphStore with 'neo4j' backend (which will use our mock)
        self.store = GraphStore(backend="neo4j")
        self.store.connect()

    def tearDown(self):
        self.store.close()
        self.patcher.stop()

    def test_node_operations(self):
        # Create
        node = self.store.create_node(labels=["Person"], properties={"name": "Alice", "age": 30})
        self.assertIsNotNone(node)
        self.assertEqual(node["properties"]["name"], "Alice")
        node_id = node["id"]

        # Get
        fetched_node = self.store.get_node(node_id)
        self.assertEqual(fetched_node["id"], node_id)
        self.assertEqual(fetched_node["properties"]["name"], "Alice")

        # Get with filters
        nodes = self.store.get_nodes(labels=["Person"], properties={"name": "Alice"})
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["id"], node_id)

        # Update
        updated_node = self.store.update_node(node_id, properties={"age": 31})
        self.assertEqual(updated_node["properties"]["age"], 31)
        self.assertEqual(updated_node["properties"]["name"], "Alice") # Merge behavior

        # Delete
        result = self.store.delete_node(node_id)
        self.assertTrue(result)
        self.assertIsNone(self.store.get_node(node_id))

    def test_relationship_operations(self):
        node1 = self.store.create_node(["Person"], {"name": "Alice"})
        node2 = self.store.create_node(["Person"], {"name": "Bob"})
        
        # Create
        rel = self.store.create_relationship(node1["id"], node2["id"], "KNOWS", {"since": 2023})
        self.assertIsNotNone(rel)
        self.assertEqual(rel["type"], "KNOWS")
        rel_id = rel["id"]

        # Get
        rels = self.store.get_relationships(node_id=node1["id"], direction="out")
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["id"], rel_id)

        # Delete
        result = self.store.delete_relationship(rel_id)
        self.assertTrue(result)
        rels = self.store.get_relationships(node_id=node1["id"])
        self.assertEqual(len(rels), 0)

    def test_batch_node_creation(self):
        nodes_data = [
            {"labels": ["Person"], "properties": {"name": "User1"}},
            {"labels": ["Person"], "properties": {"name": "User2"}}
        ]
        created_nodes = self.store.create_nodes(nodes_data)
        self.assertEqual(len(created_nodes), 2)
        self.assertEqual(created_nodes[0]["properties"]["name"], "User1")
        self.assertEqual(created_nodes[1]["properties"]["name"], "User2")

    def test_query_execution(self):
        # Since MockGraphStore returns a fixed response
        result = self.store.execute_query("MATCH (n) RETURN n")
        self.assertEqual(result["summary"], "Mock query executed")

    def test_degree_centrality_rejects_malicious_label(self):
        """Regression test for GHSA-482h-hw99-h62p: degree_centrality()
        interpolates labels/rel_type directly into a Cypher MATCH clause
        (graph_store.py's own query builder, not delegated to the backend),
        so an unvalidated label was a direct injection point."""
        from semantica.utils.exceptions import ValidationError
        evil_label = "N}) MATCH (victim) DETACH DELETE victim //"
        with self.assertRaises(ValidationError):
            self.store._manager.analytics.degree_centrality(labels=[evil_label])

    def test_degree_centrality_rejects_malicious_rel_type(self):
        from semantica.utils.exceptions import ValidationError
        evil_rel_type = "R]-() DETACH DELETE n //"
        with self.assertRaises(ValidationError):
            self.store._manager.analytics.degree_centrality(rel_type=evil_rel_type)

    def test_degree_centrality_with_legitimate_input_still_works(self):
        result = self.store._manager.analytics.degree_centrality(labels=["Person"])
        self.assertEqual(result, [])  # MockGraphStore.execute_query returns no records

class TestGraphStoreInitialization(unittest.TestCase):
    def test_falkordb_initialization(self):
        with patch('semantica.graph_store.falkordb_store.FalkorDBStore', side_effect=MockGraphStore) as mock_falkor:
            store = GraphStore(backend="falkordb")
            self.assertIsInstance(store._store_backend, MockGraphStore)
            mock_falkor.assert_called_once()

    def test_invalid_backend(self):
        from semantica.utils.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            GraphStore(backend="invalid_backend")

if __name__ == '__main__':
    unittest.main()
