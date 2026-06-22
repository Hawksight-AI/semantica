---
title: "Export & Serialization"
description: "Export knowledge graphs to RDF (Turtle, JSON-LD, N-Triples), GraphML, Cypher (Neo4j), ArangoDB AQL, CSV, Parquet, OWL, and more."
---

`export_rdf`, `export_graph`, `export_lpg`, and related functions serialize a `ContextGraph` to any of ten formats in a single call, preserving node types, edge weights, and metadata faithfully. Use them when downstream consumers — triple stores, graph databases, visualization tools, ML pipelines, or spreadsheet auditors — each expect a different format from the same in-memory graph.

<Info>
  All export functions take `graph.to_dict()` as their first argument — the same dict produced by `ContextGraph.to_dict()`. Build the graph once, export it to as many formats as you need without re-serializing.
</Info>

## Building the Graph to Export

Before the first export, populate a graph. Every example below starts from this shared setup:

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()
ctx   = AgentContext(vector_store=vs, knowledge_graph=graph, graph_expansion=True)

ctx.store(
    [
        "APT29 exploits CVE-2024-3400 in PAN-OS to target NATO defense contractors.",
        "CVE-2024-3400 is a critical remote code execution vulnerability in GlobalProtect.",
        "HAMMERTOSS is APT29's C2 backdoor using Twitter and GitHub as covert channels.",
    ],
    extract_entities=True,
    extract_relationships=True,
)

graph_data = graph.to_dict()   # single dict, reused across all exports below
```

## RDF Formats — For Triple Stores and Semantic Reasoners

When your consumers are triple stores (GraphDB, Stardog, Apache Jena) or OWL reasoners (HermiT, Pellet), you want RDF. Semantica exports to all five standard RDF serializations through a single `export_rdf` call.

```python
from semantica.export import export_rdf

# Turtle — the human-readable default; best for review and Git storage
export_rdf(graph_data, "threat_graph.ttl", format="turtle")

# N-Triples — one triple per line, no indentation; fastest bulk load into any triple store
export_rdf(graph_data, "threat_graph.nt", format="ntriples")

# JSON-LD — embeds @context; best when downstream consumers speak JSON natively
export_rdf(graph_data, "threat_graph.jsonld", format="jsonld")

# RDF/XML — maximum legacy interop; required by some older OWL tools
export_rdf(graph_data, "threat_graph.rdf", format="rdfxml")
```

The format to reach for depends on your consumer. Turtle is ideal for human review and committing to Git — it is compact and readable. N-Triples is the fastest choice for bulk-loading into a SPARQL endpoint because parsers can stream it line-by-line without buffering the whole file. JSON-LD is the right choice when downstream systems already speak JSON and you want the semantic context embedded in the same payload. RDF/XML exists for compatibility with older tools that predate the other formats.

## Graph Formats — For Gephi, Maltego, and Network Analysis

GraphML, GEXF, and DOT are the native formats of graph analysis and visualization tools. They preserve node attributes, edge weights, and type labels, so the graph you built in Semantica renders immediately in Gephi or NetworkX with full attribute data.

```python
from semantica.export import export_graph

# GraphML — widest tool support: Gephi, yEd, NetworkX, Maltego
export_graph(graph_data, "threat_graph.graphml", format="graphml")

# GEXF — richer attribute support in Gephi; better for large attributed graphs
export_graph(graph_data, "threat_graph.gexf", format="gexf")

# DOT (Graphviz) — automated layout and rendering for diagrams in reports
export_graph(graph_data, "threat_graph.dot", format="dot")
```

The GEXF format is worth knowing about if you use Gephi for analyst briefings — it carries dynamic attributes and temporal data that GraphML cannot express. DOT is the right choice when you need Graphviz to auto-layout a graph for embedding in a PDF report or documentation site.

## Neo4j Cypher — For Graph-Pattern Threat Hunting

When the SOC team wants to run Cypher queries against the graph — finding threat actors that share infrastructure, or tracing multi-hop attack paths — you export to Cypher and load the result into Neo4j Desktop or Memgraph with a single command.

```python
from semantica.export import export_lpg

export_lpg(graph_data, "threat_graph.cypher", method="cypher")
```

The output file contains ready-to-run `CREATE` and `MATCH` statements:

```text
CREATE (:ThreatActor {id: "apt29", name: "APT29", nation_state: "RU"})
CREATE (:Vulnerability {id: "cve-2024-3400", cvss_score: 10.0})
MATCH (a {id: "apt29"}), (b {id: "cve-2024-3400"}) CREATE (a)-[:EXPLOITS {confidence: 0.97}]->(b)
```

Load into Neo4j with `cypher-shell < threat_graph.cypher` or drag the file into Neo4j Desktop's import wizard. From that point, the SOC team can write Cypher queries without touching Python.

## ArangoDB AQL — For Multi-Model Queries

ArangoDB combines graph traversal with document queries and full-text search in a single query language. When your compliance team needs to join the graph against structured regulatory documents, ArangoDB is the right backend.

```python
from semantica.export import export_arango

export_arango(
    graph_data,
    "regulatory.aql",
    vertex_collection         = "regulatory_nodes",
    edge_collection           = "regulatory_edges",
    include_collection_creation = True,    # emits CREATE COLLECTION statements
    batch_size                = 200,       # INSERT statements batched to avoid memory spikes
)
```

The `include_collection_creation=True` flag means the AQL file is self-contained — it creates the collections before inserting data, so you can run it against a fresh ArangoDB instance without any prior setup.

## CSV — For Spreadsheet Audits and Statistical Analysis

The compliance team lives in Excel. The data science team lives in pandas. Both of them need CSV. `export_csv` writes the graph as flat rows — entities and relationships as separate files when you pass a base path.

```python
from semantica.export import export_csv

# Single CSV — nodes and edges interleaved with a "record_type" column
export_csv(graph_data, "threat_graph.csv")

# Split CSV — writes threat_graph_entities.csv and threat_graph_relationships.csv
export_csv(
    {"entities": graph_data.get("nodes", []),
     "relationships": graph_data.get("edges", [])},
    "threat_graph",
)
```

The split form is more useful for downstream tools: the entities CSV feeds a pivot table of entity types; the relationships CSV feeds a network analysis in pandas or R.

## Parquet — For Data Lakes and ML Pipelines

When the data science team runs feature engineering over graph attributes in DuckDB, Spark, or a lakehouse, Parquet is the format they want. It is columnar, compressed, and readable by every major ML framework.

```python
from semantica.export import export_parquet

export_parquet(graph_data, "threat_graph_entities.parquet")
```

Once in Parquet, the graph entities become a DataFrame that can be joined against telemetry, enriched with external features, and fed into classification models — without any custom serialization code on the data science side.

## OWL — For Ontology-Based Reasoning

When you have generated an OWL ontology from your graph using `OntologyGenerator`, you can export it for Protégé, HermiT reasoning, or regulatory submission.

```python
from semantica.export import export_owl
from semantica.ontology import OntologyGenerator

ontology = OntologyGenerator(base_uri="https://example.org/cti/") \
               .generate_from_graph(graph_data)

export_owl(ontology, "cti_ontology.owl", format="owl-xml")
```

## Domain Examples

<Tabs>

<Tab title="Defense — CTI/Threat">

A CTI team needs the same threat graph in four places simultaneously: a SPARQL endpoint for cross-team queries, Gephi for the analyst briefing, Neo4j for graph-pattern threat hunting, and a JSON-LD feed for the SIEM ingestion pipeline. Four exports, one graph dict.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.ingest import ingest_file
from semantica.export import export_rdf, export_graph, export_lpg
import os

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()
ctx   = AgentContext(vector_store=vs, knowledge_graph=graph, graph_expansion=True)

apt_report = ingest_file("apt29_2024_campaign.pdf", method="file")
ctx.store(apt_report.text, extract_entities=True, extract_relationships=True)

graph_data = graph.to_dict()
os.makedirs("./exports/", exist_ok=True)

# 1. Turtle → SPARQL endpoint (Apache Jena, Stardog, GraphDB)
export_rdf(graph_data, "./exports/threat_graph.ttl", format="turtle")

# 2. JSON-LD → SIEM ingestion (Splunk, Elastic) — JSON-native pipeline
export_rdf(graph_data, "./exports/threat_graph.jsonld", format="jsonld")

# 3. GraphML → Gephi for analyst briefing visualization
export_graph(graph_data, "./exports/threat_graph.graphml", format="graphml")

# 4. Cypher → Neo4j for graph-pattern threat hunting
export_lpg(graph_data, "./exports/threat_graph.cypher", method="cypher")

print("Threat graph exported to 4 formats.")
```

</Tab>

<Tab title="Security — SOC/Incident">

During an active incident the SOC needs the graph in Neo4j for hunting, in GEXF for the Gephi timeline visualization, and in GraphML for import into Maltego. All three from the same in-memory graph.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.export import export_lpg, export_graph
import os

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()
ctx   = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    decision_tracking=True,
)

incidents = [
    "Host ws-finance-03 (10.10.1.5): scheduled task created via wmiprvse.exe — T1053.005",
    "User jsmith logged in from anomalous IP 185.220.101.7 (Tor exit node)",
    "EDR alert on dc01: LSASS memory access by procdump.exe — T1003.001",
]
ctx.store(incidents, extract_entities=True, extract_relationships=True)

graph_data = graph.to_dict()
os.makedirs("./soc_exports/", exist_ok=True)

# Cypher → Neo4j for Cypher-based threat hunting
export_lpg(graph_data, "./soc_exports/incident_graph.cypher", method="cypher")

# GEXF → Gephi for timeline visualization
export_graph(graph_data, "./soc_exports/incident_graph.gexf", format="gexf")

# GraphML → Maltego for link analysis
export_graph(graph_data, "./soc_exports/incident_graph.graphml", format="graphml")

print("SOC graph exported — load incident_graph.cypher into Neo4j Desktop.")
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

Clinical trial data needs to reach a SPARQL endpoint for cross-trial federated queries, a CSV for statistical analysis in R, and a Turtle file for regulatory submission. The graph encodes compound-target-disease relationships extracted from trial protocols.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.ingest import DBIngestor
from semantica.export import export_rdf, export_csv

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph(advanced_analytics=True)
ctx   = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    retention_days=None,
)

db = DBIngestor()
trial_rows = db.execute_query(
    "postgresql://readonly@clindb:5432/trials",
    "SELECT compound, target_protein, disease, mechanism FROM trial_protocols",
)
trial_texts = [
    "{} targets {} in {} via {}.".format(
        r["compound"], r["target_protein"], r["disease"], r["mechanism"]
    )
    for r in trial_rows
]
ctx.store(trial_texts, extract_entities=True, extract_relationships=True)

graph_data = graph.to_dict()

# N-Triples for fast bulk load into GraphDB or Stardog
export_rdf(graph_data, "./exports/clinical_graph.nt",  format="ntriples")

# Turtle for human review and regulatory dossier attachment
export_rdf(graph_data, "./exports/clinical_graph.ttl", format="turtle")

# Split CSV for statistical analysis in R / SAS
export_csv(
    {"entities": graph_data.get("nodes", []),
     "relationships": graph_data.get("edges", [])},
    "./exports/clinical_graph",
)

print("Clinical graph exported — ready for SPARQL endpoint and statistical review.")
```

</Tab>

<Tab title="Banking — Risk/Compliance">

A regulatory knowledge graph must reach ArangoDB for multi-model compliance queries, RDF/XML for the long-term regulatory archive, and JSON-LD for the compliance dashboard API. Basel III regulations, risk parameters, and their relationships are all captured as graph nodes.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.ingest import ingest_file
from semantica.export import export_arango, export_rdf
import os

vs    = VectorStore(backend="faiss", dimension=768)
graph = ContextGraph()
ctx   = AgentContext(
    vector_store=vs,
    knowledge_graph=graph,
    graph_expansion=True,
    retention_days=2555,    # 7-year regulatory retention
)

regs = [
    ingest_file("basel3_cre20.pdf",       method="file"),
    ingest_file("sr_11_7_model_risk.pdf", method="file"),
    ingest_file("bcbs239.pdf",            method="file"),
]
ctx.store(
    [r.text for r in regs],
    extract_entities=True,
    extract_relationships=True,
)

graph_data = graph.to_dict()
os.makedirs("./compliance_exports/", exist_ok=True)

# ArangoDB AQL for multi-model regulatory queries (graph + document joins)
export_arango(
    graph_data,
    "./compliance_exports/regulatory.aql",
    vertex_collection           = "regulatory_nodes",
    edge_collection             = "regulatory_edges",
    include_collection_creation = True,
    batch_size                  = 200,
)

# RDF/XML for long-term regulatory archive (maximum legacy interop)
export_rdf(graph_data, "./compliance_exports/regulatory_audit.rdf", format="rdfxml")

# JSON-LD for compliance dashboard REST API
export_rdf(graph_data, "./compliance_exports/regulatory.jsonld", format="jsonld")

print("Compliance graph exported in 3 formats.")
```

</Tab>

</Tabs>

## Choosing the Right Format

The format decision usually comes down to who is consuming the output and what tools they already use.

If your consumer speaks SPARQL or uses a triple store, reach for Turtle (human review), N-Triples (bulk load), or JSON-LD (JSON-native pipelines). If they use a property graph database, Cypher goes to Neo4j or Memgraph; AQL goes to ArangoDB when they also need document and search queries in the same system. If they use a graph visualization tool, GraphML is the safest default with the widest tool support, GEXF gives richer attribute handling in Gephi specifically, and DOT is right when you need Graphviz to auto-render a static diagram. If they live in spreadsheets or statistical tools, CSV is the path of least resistance. If they run ML pipelines in DuckDB, Spark, or a lakehouse, Parquet is what they want.

For semantic reasoning and ontology work, OWL/XML is the format — it is the only output that preserves the full class hierarchy for Protégé and HermiT.

## Related Guides

- [Context Graphs](context-graphs) — the `ContextGraph` object whose `to_dict()` feeds all exports
- [Ontology Management](ontology) — export OWL ontologies generated from your graph
- [Reasoning & Rules](reasoning) — reasoning results can be exported as RDF triples
- [Change Management](change-management) — snapshot a graph before exporting to prove the export was made from a verified state
- [Pipeline](pipeline) — chain ingest, extract, and export in a single `PipelineBuilder`
