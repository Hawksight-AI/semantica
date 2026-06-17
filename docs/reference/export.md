---
title: "Export Module"
description: "Export knowledge graphs to RDF, Parquet, LPG, ArangoDB AQL, CSV, GraphML, OWL, JSON-LD, Arrow, and vector formats."
icon: "file-export"
---

**`semantica.export`** serializes knowledge graphs to **every downstream format**:

- RDF: Turtle, JSON-LD, N-Triples, RDF/XML: with optional W3C PROV-O provenance inline
- Analytics: Apache Parquet and Arrow for Spark, BigQuery, Databricks
- Graph databases: Cypher `CREATE` statements for Neo4j; AQL `INSERT` for ArangoDB
- Standard formats: GraphML, GEXF, Graphviz DOT, CSV, OWL 2.0
- Vector export: NumPy `.npz`, FAISS index, binary for embedding pipelines


## Exported Classes

| Class | Output formats | Notes |
| :--- | :--- | :--- |
| `RDFExporter` | Turtle, JSON-LD, N-Triples, RDF/XML | `export_to_rdf()` → string; `export()` → file |
| `ParquetExporter` | `.parquet` | Requires `pyarrow`; explicit typed schema |
| `LPGExporter` | Cypher `CREATE` | Neo4j and Memgraph compatible |
| `ArangoAQLExporter` | AQL `INSERT` | Vertex and edge collections |
| `GraphExporter` | GraphML, GEXF, Graphviz DOT | Standard graph interchange formats |
| `OWLExporter` | OWL 2.0 in Turtle/XML | Ontology serialization |
| `CSVExporter` | `.csv` | `export_entities()` and `export_relationships()` |
| `VectorExporter` | JSON, NumPy `.npz`, FAISS index, binary | Embedding vector export |
| `ArrowExporter` | Apache Arrow IPC | Requires `pyarrow`; zero-copy transfer |
| `DistanceExporter` | CSV, JSONL | Pairwise distance metrics; takes a `graph` arg |
| `ReportGenerator` | HTML, Markdown, JSON, plain text | Analytics reports |
| `NamespaceManager` |: | RDF namespace extraction and declaration generation |

## Getting Started

```python
from semantica.export import RDFExporter

# Export a knowledge graph dict to Turtle
exporter = RDFExporter()
rdf_str = exporter.export_to_rdf(graph, format="turtle")
with open("output.ttl", "w") as f:
    f.write(rdf_str)
```

Or use the one-liner convenience functions:

```python
from semantica.export import export_rdf, export_csv, export_lpg

export_rdf(graph,  "output.ttl",    format="turtle")
export_csv(graph,  "output_base")   # writes entities and relationships as CSV
export_lpg(graph,  "import.cypher", method="cypher")
```

## Quick Export

<Steps>
  <Step title="Export to RDF string">
    ```python
    from semantica.export import RDFExporter

    exporter = RDFExporter()
    rdf_str = exporter.export_to_rdf(graph, format="turtle")
    ```
  </Step>
  <Step title="Write RDF directly to file">
    ```python
    exporter.export(graph, "output.ttl", format="turtle")
    ```
  </Step>
  <Step title="Columnar export for analytics">
    ```python
    from semantica.export import ParquetExporter

    exporter = ParquetExporter(compression="snappy")
    exporter.export_entities(entities, "nodes.parquet")
    exporter.export_relationships(relationships, "edges.parquet")
    ```
  </Step>
  <Step title="Graph database import">
    ```python
    from semantica.export import LPGExporter

    exporter = LPGExporter()
    exporter.export(graph, "import.cypher")   # Cypher CREATE statements
    ```
  </Step>
</Steps>

## Exporters

<Tabs>
  <Tab title="RDF">
    Export to W3C RDF formats: Turtle, JSON-LD, N-Triples, and RDF/XML.

    **`export_to_rdf()` returns a string; `export()` writes to a file:**

    ```python
    from semantica.export import RDFExporter

    exporter = RDFExporter()

    # Returns RDF string
    turtle_str  = exporter.export_to_rdf(graph, format="turtle")   # Turtle
    jsonld_str  = exporter.export_to_rdf(graph, format="jsonld")   # JSON-LD
    nt_str      = exporter.export_to_rdf(graph, format="ntriples") # N-Triples
    xml_str     = exporter.export_to_rdf(graph, format="rdfxml")   # RDF/XML

    # Accepted format aliases: "ttl" -> turtle, "nt" -> ntriples, "xml" -> rdfxml,
    # "json-ld" -> jsonld, "rdf" -> rdfxml

    # Write directly to file
    exporter.export(graph, "output.ttl", format="turtle")

    # Also available
    exporter.export_knowledge_graph(graph, "output.ttl", format="turtle")
    ```

    <Warning>
      **`export_to_rdf()` returns a string: it does not write a file.** Call `export()` or `export_knowledge_graph()` to write directly to disk.
    </Warning>

    <Tip>
      **Use `export_to_rdf()` + string for inspection, `export()` for production.** In notebooks or debug sessions, `export_to_rdf()` is handy for quick inspection. For CI pipelines and pipelines writing files, `export()` is a single call.
    </Tip>

    <Tip>
      **Use `turtle` for human readability, `ntriples` for streaming.** Turtle is compact and readable for debugging and sharing. N-Triples (`.nt`) is line-oriented: one triple per line: making it safe to stream, concatenate, and process with standard Unix tools.
    </Tip>

    **Namespace management:**

    ```python
    from semantica.export import NamespaceManager, RDFExporter

    ns_manager = NamespaceManager()
    # ns_manager.namespaces contains the built-in prefix dict (rdf, rdfs, owl, xsd, semantica)
    # Add custom namespaces by updating the dict directly
    ns_manager.namespaces["ex"]     = "http://example.org/"
    ns_manager.namespaces["schema"] = "https://schema.org/"

    # Generate Turtle prefix declarations
    decls = ns_manager.generate_namespace_declarations(
        ns_manager.namespaces, format="turtle"
    )
    print(decls)   # @prefix ex: <http://example.org/> .   etc.
    ```

    **Temporal export (OWL-Time):**

    ```python
    # Pass include_temporal=True to embed OWL-Time interval triples
    turtle_str = exporter.export_to_rdf(
        graph,
        format="turtle",
        include_temporal=True,
        time_axis="valid",  # "valid" | "transaction" | "both"
    )
    ```
  </Tab>
  <Tab title="Columnar & Analytics">
    ```python
    from semantica.export import ParquetExporter

    exporter = ParquetExporter(compression="snappy")
    # compression: snappy | gzip | brotli | zstd | lz4 | none

    # Export entities and relationships as separate Parquet files
    exporter.export_entities(entities,           "nodes.parquet")
    exporter.export_relationships(relationships, "edges.parquet")

    # Export full knowledge graph (writes entities.parquet and relationships.parquet)
    exporter.export_knowledge_graph(graph, "output_base")
    # → output_base_entities.parquet, output_base_relationships.parquet

    # Generic export from list or dict
    exporter.export(entities, "entities.parquet")
    exporter.export(graph,    "output_base")
    ```

    <Warning>
      **`ParquetExporter` and `ArrowExporter` require `pyarrow`.** Both fall back to a no-op stub class if `pyarrow` is not installed. Install with `pip install pyarrow` before using these exporters.
    </Warning>

    <Tip>
      **Use `ParquetExporter` for downstream analytics.** Parquet preserves column types (int, float, datetime) that CSV loses and is natively supported by Spark, BigQuery, Databricks, and Snowflake. Use `compression="snappy"` for a good balance of speed and compression.
    </Tip>

    Requires `pyarrow`: `pip install pyarrow`. Schema is explicitly typed.

    ```python
    from semantica.export import CSVExporter

    exporter = CSVExporter(delimiter=",")
    exporter.export_entities(entities,           "nodes.csv")
    exporter.export_relationships(relationships, "edges.csv")
    exporter.export_knowledge_graph(graph,       "output_base")
    ```

    ```python
    from semantica.export import SemanticNetworkYAMLExporter

    exporter = SemanticNetworkYAMLExporter()
    exporter.export(graph, "graph.yaml")
    ```
  </Tab>
  <Tab title="Graph DB Import">
    **LPGExporter** writes Cypher `CREATE` statements for Neo4j and Memgraph:

    ```python
    from semantica.export import LPGExporter

    exporter = LPGExporter()

    # Write Cypher CREATE statements to file
    exporter.export(graph, "import.cypher")

    # Also available
    exporter.export_knowledge_graph(graph, "import.cypher")
    ```

    **ArangoAQLExporter** writes `INSERT` statements for ArangoDB:

    ```python
    from semantica.export import ArangoAQLExporter

    exporter = ArangoAQLExporter(
        vertex_collection="entities",
        edge_collection="relationships"
    )

    # Write AQL INSERT statements to file
    exporter.export(graph, "import.aql")
    exporter.export_knowledge_graph(graph, "import.aql")
    ```

    Both exporters write to a file and return `None`.

    <Warning>
      **`ArangoAQLExporter.export()` and `LPGExporter.export()` write to a file and return `None`.** They do not return the AQL/Cypher string. Write to a file and read it back if you need the string.
    </Warning>
  </Tab>
  <Tab title="Visualization & OWL">
    ```python
    from semantica.export import GraphExporter

    exporter = GraphExporter()
    exporter.export(graph, "graph.graphml", format="graphml")  # Gephi, yEd
    exporter.export(graph, "graph.gexf",    format="gexf")     # Gephi streaming
    exporter.export(graph, "graph.dot",     format="dot")      # Graphviz
    ```

    ```python
    from semantica.export import OWLExporter

    exporter = OWLExporter()
    exporter.export(ontology, path="ontology.owl", format="owl-xml")
    exporter.export(ontology, path="ontology.ttl", format="turtle")
    ```
  </Tab>
  <Tab title="Vectors, Arrow & Reports">
    **VectorExporter**: takes `(vectors, file_path, format=)`:

    ```python
    from semantica.export import VectorExporter

    exporter = VectorExporter()
    # vectors: list of dicts with 'id', 'vector', 'text', 'metadata' keys
    exporter.export(vectors, "vectors.json",  format="json")
    exporter.export(vectors, "vectors.npz",   format="numpy")   # NumPy .npz
    exporter.export(vectors, "vectors.bin",   format="binary")
    exporter.export(vectors, "vectors.faiss", format="faiss")
    ```

    **ArrowExporter**: requires `pyarrow`:

    ```python
    from semantica.export import ArrowExporter

    exporter = ArrowExporter()
    exporter.export(graph, "graph.arrow")
    ```

    **DistanceExporter**: takes a `graph` argument at construction:

    ```python
    from semantica.export import DistanceExporter

    exporter = DistanceExporter(graph)   # graph is required

    # Compute all pairwise distances and write to file
    exporter.to_csv("distances.csv")
    exporter.to_jsonl("distances.jsonl")

    # Compute with column selection and optional node subset
    exporter.to_csv(
        "distances.csv",
        include=["source_id", "target_id", "hop_count", "distance_band"],
        node_subset=["node_a", "node_b", "node_c"],
    )

    # Return as pandas DataFrame (requires pandas)
    df = exporter.to_dataframe(include=["hop_count", "semantic_similarity"])

    # Return as string (for API responses)
    csv_str  = exporter.to_csv_string(node_subset=["node_a", "node_b"])
    jsonl_str = exporter.to_jsonl_string()
    ```

    Available `include` columns: `source_id`, `source_type`, `target_id`, `target_type`, `hop_count`, `weighted_distance`, `semantic_similarity`, `distance_band`, `source_betweenness`, `target_betweenness`.

    <Warning>
      **`DistanceExporter` requires a graph at construction.** Instantiate as `DistanceExporter(graph)`, not `DistanceExporter()`. Semantic similarity columns (`semantic_similarity`) require the graph nodes to have embeddings in their properties.
    </Warning>

    **ReportGenerator:**

    ```python
    from semantica.export import ReportGenerator

    generator = ReportGenerator()
    generator.generate_report(data, "report.html",  format="html")
    generator.generate_report(data, "report.md",    format="markdown")
    generator.generate_report(data, "report.json",  format="json")
    generator.generate_report(data, "report.txt",   format="text")
    ```
  </Tab>
</Tabs>

## Convenience Functions

```python
from semantica.export import (
    export_rdf, export_json, export_parquet, export_csv,
    export_lpg, export_arango, export_graph, export_owl,
    export_vector, export_arrow, export_yaml, generate_report,
)

export_rdf(graph,     "output.ttl",    format="turtle")
export_rdf(graph,     "output.nt",     format="ntriples")
export_json(graph,    "output.json",   format="json")
export_parquet(graph, "output_base",   compression="snappy")
export_csv(graph,     "output_base")   # uses CSVExporter.export()
export_lpg(graph,     "import.cypher", method="cypher")
export_arango(graph,  "import.aql")
export_graph(graph,   "graph.graphml", format="graphml")
export_owl(ontology,  "ontology.owl",  format="owl-xml")
export_vector(vectors,"vectors.json",  format="json")
export_arrow(graph,   "graph.arrow")
export_yaml(graph,    "graph.yaml",    method="semantic_network")
generate_report(data, "report.html",   format="html")
```

The `export_csv` convenience function delegates to `CSVExporter.export()`. For per-type exports use the class directly (`exporter.export_entities()`, `exporter.export_relationships()`).

## Format Reference

| Format string | Canonical name | Exporter | File ext | Best for |
| :--- | :--- | :--- | :--- | :--- |
| `"turtle"` / `"ttl"` | `turtle` | `RDFExporter` | `.ttl` | Readable RDF, ontology sharing |
| `"jsonld"` / `"json-ld"` | `jsonld` | `RDFExporter` | `.jsonld` | APIs, Linked Data, JSON pipelines |
| `"ntriples"` / `"nt"` | `ntriples` | `RDFExporter` | `.nt` | Streaming RDF, line-by-line processing |
| `"rdfxml"` / `"xml"` / `"rdf"` | `rdfxml` | `RDFExporter` | `.rdf` | W3C RDF/XML, broadest compatibility |
| `"parquet"` | `parquet` | `ParquetExporter` | `.parquet` | Spark, BigQuery, Databricks, Snowflake |
| `"cypher"` | `cypher` | `LPGExporter` | `.cypher` | Neo4j, Memgraph import |
| `"aql"` | `aql` | `ArangoAQLExporter` | `.aql` | ArangoDB vertex + edge collections |
| `"graphml"` | `graphml` | `GraphExporter` | `.graphml` | Gephi, yEd visualization |
| `"gexf"` | `gexf` | `GraphExporter` | `.gexf` | Gephi streaming format |
| `"dot"` | `dot` | `GraphExporter` | `.dot` | Graphviz rendering |
| `"owl-xml"` | `owl-xml` | `OWLExporter` | `.owl` | OWL 2.0 ontology distribution |
| `"csv"` | `csv` | `CSVExporter` | `.csv` | Spreadsheets, simple pipelines |
| `"yaml"` | `yaml` | `SemanticNetworkYAMLExporter` | `.yaml` | Human-readable config-driven use |
| `"arrow"` | `arrow` | `ArrowExporter` | `.arrow` | Zero-copy inter-process transfer |
| `"json"` | `json` | `VectorExporter` | `.json` | Vector embeddings |
| `"numpy"` | `numpy` | `VectorExporter` | `.npz` | NumPy arrays from embeddings |
| `"binary"` | `binary` | `VectorExporter` | `.bin` | Raw float32 binary |
| `"faiss"` | `faiss` | `VectorExporter` | `.faiss` | Direct FAISS index files |
| `"html"` / `"markdown"` / `"json"` / `"text"` |: | `ReportGenerator` | `.html` / `.md` / `.json` / `.txt` | Analytics reports |

<Tip>
  **Match your export format to your consumer.** Neo4j → `cypher`; ArangoDB → `aql`; Gephi/yEd → `graphml` or `gexf`; semantic web tools → `turtle` or `json-ld`; analytics pipelines → `parquet`; zero-copy IPC → `arrow`.
</Tip>

- [Triplet Store](triplet_store) — Store RDF exports in a SPARQL-queryable backend.
- [Ontology](ontology) — Export OWL ontologies.
- [Provenance](provenance) — Include provenance metadata in RDF exports.
- [Pipeline](pipeline) — Add export as a final pipeline step.
