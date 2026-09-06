import os
import shutil
import tempfile
import pytest
from pathlib import Path
from semantica.ingest import OntologyIngestor, ingest, ingest_ontology, OntologyData

class TestOntologyIngestor:
    @pytest.fixture
    def sample_ttl_content(self):
        return """
        @prefix : <http://example.org/ontology/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

        <http://example.org/ontology/> rdf:type owl:Ontology ;
            rdfs:label "Test Ontology" .

        :Person rdf:type owl:Class ;
            rdfs:label "Person" .

        :hasName rdf:type owl:DatatypeProperty ;
            rdfs:domain :Person ;
            rdfs:range xsd:string .
        """

    def test_ingest_single_file(self, sample_ttl_content):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttl", mode="w") as tmp:
            tmp.write(sample_ttl_content)
            tmp_path = tmp.name

        try:
            ingestor = OntologyIngestor()
            result = ingestor.ingest_ontology(tmp_path)
            
            assert isinstance(result, OntologyData)
            assert result.data["name"] == "Test Ontology" or result.data["name"] == os.path.basename(tmp_path)
            assert any(cls["name"] == "Person" for cls in result.data["classes"])
            assert any(prop["name"] == "hasName" for prop in result.data["properties"])
            assert result.metadata["format"] == "ttl" or result.metadata["format"] == "turtle"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_ingest_preserves_multiple_property_domains_and_ranges(self):
        ttl_content = """
        @prefix : <http://example.org/ontology/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

        <http://example.org/ontology/> a owl:Ontology .
        :Person a owl:Class .
        :Place a owl:Class .
        :name a owl:DatatypeProperty ;
            rdfs:domain :Person, :Place ;
            rdfs:range xsd:normalizedString, xsd:string .
        :label a owl:DatatypeProperty ;
            rdfs:domain :Person, :Place ;
            rdfs:range xsd:string .
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttl", mode="w") as tmp:
            tmp.write(ttl_content)
            tmp_path = tmp.name

        try:
            result = OntologyIngestor().ingest_ontology(tmp_path)
            name_property = next(
                prop for prop in result.data["properties"] if prop["name"] == "name"
            )
            assert name_property["domain"] == [
                "http://example.org/ontology/Person",
                "http://example.org/ontology/Place",
            ]
            assert name_property["range"] == [
                "http://www.w3.org/2001/XMLSchema#normalizedString",
                "http://www.w3.org/2001/XMLSchema#string",
            ]
            label_property = next(
                prop for prop in result.data["properties"] if prop["name"] == "label"
            )
            assert label_property["domain"] == [
                "http://example.org/ontology/Person",
                "http://example.org/ontology/Place",
            ]
            assert label_property["range"] == (
                "http://www.w3.org/2001/XMLSchema#string"
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_ingest_directory(self, sample_ttl_content):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create two ontology files
            file1 = os.path.join(tmp_dir, "ont1.ttl")
            file2 = os.path.join(tmp_dir, "ont2.rdf")
            
            with open(file1, "w") as f:
                f.write(sample_ttl_content)
            
            # Simple RDF/XML content for the second file
            rdf_content = """
            <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                     xmlns:owl="http://www.w3.org/2002/07/owl#">
              <owl:Ontology rdf:about="http://example.org/ont2"/>
              <owl:Class rdf:about="http://example.org/ont2/Animal"/>
            </rdf:RDF>
            """
            with open(file2, "w") as f:
                f.write(rdf_content)
            
            ingestor = OntologyIngestor()
            results = ingestor.ingest_directory(tmp_dir)
            
            assert len(results) == 2
            assert all(isinstance(r, OntologyData) for r in results)
            
            # Verify results contain expected classes
            classes = [cls["name"] for res in results for cls in res.data["classes"]]
            assert "Person" in classes
            assert "Animal" in classes

    def test_unified_ingest_function(self, sample_ttl_content):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttl", mode="w") as tmp:
            tmp.write(sample_ttl_content)
            tmp_path = tmp.name
            
        try:
            # Test auto-detection via unified ingest
            result = ingest(tmp_path)
            assert "ontology" in result
            assert isinstance(result["ontology"], OntologyData)
            assert len(result["ontology"].data["classes"]) > 0
            
            # Test explicit source type
            result_explicit = ingest(tmp_path, source_type="ontology")
            assert "ontology" in result_explicit
            assert result_explicit["ontology"].metadata["source_path"] == tmp_path
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_convenience_function(self, sample_ttl_content):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".n3", mode="w") as tmp:
            tmp.write(sample_ttl_content)
            tmp_path = tmp.name
            
        try:
            result = ingest_ontology(tmp_path)
            assert isinstance(result, OntologyData)
            assert len(result.data["classes"]) > 0
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_ingest_formats(self):
        """Test ingestion of all supported formats."""
        ingestor = OntologyIngestor()
        
        # 1. JSON-LD
        jsonld_content = """
        {
          "@context": {
            "owl": "http://www.w3.org/2002/07/owl#",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
          },
          "@id": "http://example.org/jsonld",
          "@type": "owl:Ontology",
          "rdfs:label": "JSON-LD Ontology",
          "owl:versionInfo": "1.0"
        }
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonld", mode="w") as tmp:
            tmp.write(jsonld_content)
            tmp_path = tmp.name
        try:
            result = ingestor.ingest_ontology(tmp_path)
            assert result.data["name"] == "JSON-LD Ontology"
            assert result.metadata["format"] == "json-ld"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # 2. N-Triples
        nt_content = '<http://example.org/nt/Class> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2002/07/owl#Class> .\n'
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nt", mode="w") as tmp:
            tmp.write(nt_content)
            tmp_path = tmp.name
        try:
            result = ingestor.ingest_ontology(tmp_path)
            # N-Triples often doesn't have ontology metadata, so name might default to basename
            assert result.data["name"] == os.path.basename(tmp_path)
            assert any(cls["uri"] == "http://example.org/nt/Class" for cls in result.data["classes"])
            assert result.metadata["format"] == "nt"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # 3. Notation3
        n3_content = """
        @prefix : <http://example.org/n3/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        :N3Class a owl:Class .
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=".n3", mode="w") as tmp:
            tmp.write(n3_content)
            tmp_path = tmp.name
        try:
            result = ingestor.ingest_ontology(tmp_path)
            assert any(cls["uri"] == "http://example.org/n3/N3Class" for cls in result.data["classes"])
            # format might be 'n3' or 'turtle' depending on rdflib detection as they are similar
            assert result.metadata["format"] in ["n3", "turtle"] 
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # 4. RDF/XML (.owl)
        owl_content = """
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:owl="http://www.w3.org/2002/07/owl#"
                 xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
          <owl:Ontology rdf:about="http://example.org/owl"/>
          <owl:Class rdf:about="http://example.org/owl/OwlClass">
            <rdfs:label>OwlClass</rdfs:label>
          </owl:Class>
        </rdf:RDF>
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=".owl", mode="w") as tmp:
            tmp.write(owl_content)
            tmp_path = tmp.name
        try:
            result = ingestor.ingest_ontology(tmp_path)
            assert any(cls["name"] == "OwlClass" for cls in result.data["classes"])
            assert result.metadata["format"] in ["xml", "rdf", "owl"]
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_error_handling(self):
        ingestor = OntologyIngestor()
        with pytest.raises(Exception): # Specific exception type depends on implementation, likely ValidationError or FileNotFoundError
            ingestor.ingest_ontology("non_existent_file.ttl")

    def test_invalid_content(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttl", mode="w") as tmp:
            tmp.write("This is not valid turtle content")
            tmp_path = tmp.name
            
        try:
            ingestor = OntologyIngestor()
            # Depending on implementation, this might raise an exception or return partial/empty result with error in metadata
            # Given current implementation uses g.parse(), it likely raises an exception which is caught or propagated
            # If propagated:
            with pytest.raises(Exception):
                ingestor.ingest_ontology(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
