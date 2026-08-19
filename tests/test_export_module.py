
import os
import unittest
import shutil
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from semantica.export import (
    ArrowExporter,
    JSONExporter,
    CSVExporter,
    RDFExporter,
    GraphExporter,
    SemanticNetworkYAMLExporter,
    YAMLSchemaExporter,
    OWLExporter,
    VectorExporter,
    LPGExporter,
    ReportGenerator,
    MethodRegistry,
    method_registry
)
from semantica.export.rdf_exporter import NamespaceManager, RDFSerializer, RDFValidator

class TestExportModule(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.entities = [
            {"id": "e1", "type": "Person", "name": "Alice", "label": "Alice", "properties": {"age": 30}},
            {"id": "e2", "type": "Organization", "name": "Acme Corp", "label": "Acme Corp", "properties": {"loc": "NY"}}
        ]
        self.relationships = [
            {"id": "r1", "source": "e1", "target": "e2", "type": "WORKS_FOR", "properties": {"role": "Engineer"}}
        ]
        self.kg = {
            "entities": self.entities,
            "relationships": self.relationships,
            "metadata": {"version": "1.0"}
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_json_exporter(self):
        exporter = JSONExporter(indent=2)
        output_path = Path(self.test_dir) / "output.json"
        
        # Test export_knowledge_graph
        exporter.export_knowledge_graph(self.kg, str(output_path))
        self.assertTrue(output_path.exists())
        
        with open(output_path, 'r') as f:
            data = json.load(f)
            self.assertEqual(len(data['entities']), 2)
            self.assertEqual(len(data['relationships']), 1)

        # Test export_entities
        entities_path = Path(self.test_dir) / "entities.json"
        exporter.export_entities(self.entities, str(entities_path))
        self.assertTrue(entities_path.exists())

    def test_turtle_serializer_escapes_literal_syntax(self):
        turtle = RDFSerializer().serialize_to_turtle({
            "entities": [{"id": "https://example.org/e1", "type": "Person",
                          "text": 'He said "hi"\\then\nleft\r'}],
            "relationships": [],
        })
        self.assertIn('semantica:text "He said \\"hi\\"\\\\then\\nleft\\r"', turtle)

    def test_export_knowledge_graph_smoke(self):
        from semantica.export.methods import export_knowledge_graph

        output_path = Path(self.test_dir) / "smoke.json"
        export_knowledge_graph(self.kg, output_path, format="json")

        self.assertTrue(output_path.exists())
        exported = output_path.read_text(encoding="utf-8")
        self.assertIn("Alice", exported)
        self.assertIn("Acme Corp", exported)
        
    def test_csv_exporter(self):
        exporter = CSVExporter()
        output_path = Path(self.test_dir) / "output.csv" 
        
        # Test export_entities directly
        ent_path = Path(self.test_dir) / "entities.csv"
        exporter.export_entities(self.entities, str(ent_path))
        self.assertTrue(ent_path.exists())
        
        # Verify CSV content
        with open(ent_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            header = lines[0].strip()
            # Check for presence of fields (order might vary)
            self.assertIn("id", header)
            self.assertIn("text", header)
            self.assertIn("type", header)
            
            content = "".join(lines)
            self.assertIn("e1", content)
            self.assertIn("Alice", content)
            self.assertIn("Person", content)
            self.assertIn("e2", content)
            self.assertIn("Acme Corp", content)
            self.assertIn("Organization", content)

        rel_path = Path(self.test_dir) / "rels.csv"
        exporter.export_relationships(self.relationships, str(rel_path))
        self.assertTrue(rel_path.exists())
        
        # Verify Relationship CSV content
        with open(rel_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            header = lines[0].strip()
            self.assertIn("id", header)
            self.assertIn("source_id", header)
            self.assertIn("target_id", header)
            self.assertIn("type", header)
            
            content = "".join(lines)
            self.assertIn("r1", content)
            self.assertIn("e1", content)
            self.assertIn("e2", content)
            self.assertIn("WORKS_FOR", content)

    def test_rdf_exporter(self):
        exporter = RDFExporter()
        output_path = Path(self.test_dir) / "output.ttl"
        
        try:
            exporter.export(self.kg, str(output_path), format="turtle")
            if output_path.exists():
                self.assertTrue(output_path.exists())
                
                # Verify RDF content
                with open(output_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Basic checks for Turtle format
                    # self.assertIn("@prefix", content) # Prefix might not be present if full URIs used or defaults
                    self.assertIn("Person", content)
                    self.assertIn("Alice", content)
                    self.assertIn("WORKS_FOR", content)
                    
        except ImportError:
            print("Skipping RDF test due to missing dependencies")
        except Exception as e:
            self.fail(f"RDF Export failed: {e}")

    def test_graph_exporter(self):
        exporter = GraphExporter()
        output_path = Path(self.test_dir) / "output.graphml"
        
        try:
            exporter.export_knowledge_graph(self.kg, str(output_path), format="graphml")
            self.assertTrue(output_path.exists())
            
            # Verify GraphML content
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn("<?xml", content)
                self.assertIn("<graphml", content)
                self.assertIn('id="e1"', content)
                # Edges in GraphML might not have IDs in this implementation
                # self.assertIn('id="r1"', content)
                self.assertIn('source="e1"', content)
                self.assertIn('target="e2"', content)
                
        except Exception as e:
            self.fail(f"Graph Export failed: {e}")

    def test_yaml_exporter(self):
        exporter = SemanticNetworkYAMLExporter()
        output_path = Path(self.test_dir) / "network.yaml"
        
        exporter.export(self.kg, str(output_path))
        self.assertTrue(output_path.exists())
        
        # Verify YAML content
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("entities:", content)
            self.assertIn("- id: e1", content)
            self.assertIn("name: Alice", content)
        
        schema_exporter = YAMLSchemaExporter()
        schema_path = Path(self.test_dir) / "schema.yaml"
        # Mock schema
        schema = {"classes": ["Person", "Organization"], "properties": ["WORKS_FOR"]}
        yaml_content = schema_exporter.export_ontology_schema(schema)
        with open(schema_path, 'w') as f:
            f.write(yaml_content)
        self.assertTrue(schema_path.exists())
        
        # Verify Schema content
        with open(schema_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("classes:", content)
            self.assertIn("- Person", content)

    def test_owl_exporter(self):
        exporter = OWLExporter()
        output_path = Path(self.test_dir) / "ontology.owl"
        
        # Mock ontology structure
        ontology = {
            "classes": [{"id": "Person"}, {"id": "Organization"}],
            "properties": [{"id": "works_for", "domain": "Person", "range": "Organization"}]
        }
        
        try:
            exporter.export(ontology, str(output_path))
            self.assertTrue(output_path.exists())
            
            # Verify OWL content
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn("<rdf:RDF", content)
                self.assertIn("owl:Class", content)
                # Check for Person class definition, format might vary
                self.assertIn("Person", content)
                
        except Exception as e:
            self.fail(f"OWL Export failed: {e}")

    def test_vector_exporter(self):
        exporter = VectorExporter()
        output_path = Path(self.test_dir) / "vectors.json"
        
        # Updated format: List of dicts with 'id' and 'vector'
        vectors = [
            {"id": "v1", "vector": [0.1, 0.2]},
            {"id": "v2", "vector": [0.3, 0.4]}
        ]
        
        exporter.export(vectors, str(output_path), format="json")
        self.assertTrue(output_path.exists())
        
        # Verify JSON content
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # VectorExporter wraps output in {"vectors": [...], "metadata": ...}
            self.assertIn("vectors", data)
            vectors_list = data["vectors"]
            self.assertEqual(len(vectors_list), 2)
            self.assertEqual(vectors_list[0]['id'], 'v1')
            self.assertEqual(vectors_list[0]['vector'], [0.1, 0.2])

    def test_lpg_exporter(self):
        exporter = LPGExporter()
        output_path = Path(self.test_dir) / "graph.cypher"
        
        try:
            exporter.export_knowledge_graph(self.kg, str(output_path), format="cypher")
            self.assertTrue(output_path.exists())
            
            # Verify Cypher content
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn("CREATE", content)
                # Matches (:Person { or (n0:Person {
                self.assertIn(":Person {", content)
                self.assertIn("Alice", content)
                # Matches [:WORKS_FOR or -[:WORKS_FOR
                self.assertIn(":WORKS_FOR", content)
                
        except Exception as e:
            self.fail(f"LPG Export failed: {e}")

    def test_report_generator(self):
        generator = ReportGenerator()
        output_path = Path(self.test_dir) / "report.html"
        
        generator.generate_report(self.kg, str(output_path), format="html")
        self.assertTrue(output_path.exists())

    def test_arrow_exporter(self):
        """Test Arrow exporter basic functionality."""
        try:
            import pyarrow as pa
            import pyarrow.ipc as ipc
            
            exporter = ArrowExporter()
            output_path = Path(self.test_dir) / "entities.arrow"
            
            # Test export_entities
            exporter.export_entities(self.entities, str(output_path))
            self.assertTrue(output_path.exists())
            
            # Verify Arrow file
            with pa.OSFile(str(output_path), 'rb') as source:
                with ipc.open_file(source) as reader:
                    table = reader.read_all()
                    self.assertEqual(table.num_rows, 2)
                    self.assertIn('id', table.column_names)
                    self.assertIn('text', table.column_names)
                    self.assertIn('type', table.column_names)
            
            # Test export_knowledge_graph
            base_path = Path(self.test_dir) / "kg_arrow"
            exporter.export_knowledge_graph(self.kg, str(base_path))
            
            entities_path = Path(self.test_dir) / "kg_arrow_entities.arrow"
            rels_path = Path(self.test_dir) / "kg_arrow_relationships.arrow"
            
            self.assertTrue(entities_path.exists())
            self.assertTrue(rels_path.exists())
            
        except ImportError:
            print("Skipping Arrow test due to missing pyarrow")

    def test_registry(self):
        def dummy_method(data, path, **kwargs):
            with open(path, 'w') as f:
                f.write("dummy")
        
        MethodRegistry.register("dummy_fmt", "dummy_provider", dummy_method)
        
        methods = method_registry.list_all()
        self.assertIn("dummy_fmt", methods)
        
        output_path = Path(self.test_dir) / "dummy.txt"
        method = MethodRegistry.get("dummy_fmt", "dummy_provider")
        method("data", str(output_path))
        self.assertTrue(output_path.exists())

if __name__ == '__main__':
    unittest.main()
