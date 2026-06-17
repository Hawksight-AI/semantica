---
title: "Quickstart"
description: "Build your first knowledge graph in 5 minutes. No configuration required."
icon: "rocket"
---

<Info>
  **v0.5.0** — Ontology Hub, Distance Intelligence, Parquet & XML ingestion, 12 security fixes. <a href="index#whats-new" style={{color:"#10B981",fontWeight:600,textDecoration:"none"}}>What's new →</a>
</Info>

This guide walks you through the end-to-end pipeline for building your first knowledge graph. Start here after installation. An LLM API key is optional: pattern-based extraction works out of the box.


## Install

<CodeGroup>

```bash pip (recommended)
pip install semantica
```

```bash With all extras
pip install semantica[all]
```

```bash From source
git clone https://github.com/semantica-agi/semantica.git
cd semantica
pip install -e ".[dev]"
```

</CodeGroup>

Verify:

```bash
python -c "import semantica; print(semantica.__version__)"
# 0.5.0
```


## Full Pipeline

<img src="/assets/img/diagrams/pipeline-flow.svg" alt="Semantica end-to-end pipeline: Ingest → Parse → Normalize → Extract → Build KG → QA → Store → Deliver" style={{ width: '100%', borderRadius: '10px', margin: '0 0 24px' }} />

<Steps>

<Step title="Ingest">

Load a document from a file, directory, URL, or database.

<CodeGroup>

```python File
from semantica.ingest import FileIngestor

ingestor = FileIngestor()
sources  = ingestor.ingest("data/report.pdf")
# Also accepts: .docx, .html, .json, .csv, .xlsx, .pptx, .parquet, .xml
```

```python Web
from semantica.ingest import WebIngestor

ingestor = WebIngestor(max_depth=2)
sources  = ingestor.ingest("https://example.com/article")
```

```python Parquet / XML (v0.5.0)
from semantica.ingest import ParquetIngestor, XMLIngestor

# Single file or Hive-partitioned directory
sources = ParquetIngestor().ingest("data/events.parquet")

# XML with XSD schema validation
sources = XMLIngestor(validate_xsd="schema.xsd").ingest("data/records/")
```

</CodeGroup>

</Step>

<Step title="Parse">

Extract structured text and layout from raw documents.

```python
from semantica.parse import DocumentParser

parser = DocumentParser()
parsed = parser.parse(sources[0])

print(parsed.text[:200])  # extracted text
print(parsed.metadata)    # title, author, date, source
```

<Tip>
  For PDFs with tables, charts, or multi-column layouts, use `DoclingParser`: it applies advanced layout analysis and returns structured table data alongside text.
</Tip>

```python
from semantica.parse import DoclingParser

parser = DoclingParser()
parsed = parser.parse(sources[0])
print(parsed.tables)  # structured table objects
```

</Step>

<Step title="Extract Entities & Relationships">

Identify named entities and extract typed relationships between them.

<CodeGroup>

```python Pattern-based (fast, no API key)
from semantica.semantic_extract import NERExtractor, RelationExtractor

ner      = NERExtractor(method="pattern")
entities = ner.extract(parsed)
# Returns: [{"text": "Apple Inc.", "type": "ORGANIZATION", "confidence": 0.98}, ...]

rel           = RelationExtractor(method="rule")
relationships = rel.extract(parsed, entities=entities)
# Returns: [{"subject": "Steve Jobs", "predicate": "founded", "object": "Apple Inc."}, ...]
```

```python LLM-powered (higher accuracy)
from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.llms import Groq

llm = Groq(model="llama-3.3-70b-versatile")

ner           = NERExtractor(method="llm", llm_provider=llm)
entities      = ner.extract(parsed)

rel           = RelationExtractor(method="llm", llm_provider=llm)
relationships = rel.extract(parsed, entities=entities)
```

</CodeGroup>

</Step>

<Step title="Build the Knowledge Graph">

Assemble extracted entities and relationships into a queryable knowledge graph.

```python
from semantica.kg import GraphBuilder

builder = GraphBuilder(merge_entities=True)
graph   = builder.build(entities=entities, relationships=relationships)

print(f"Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

# Query the graph
apple    = graph.get_node("Apple Inc.")
founders = graph.get_neighbors("Apple Inc.", predicate="founded_by")
```

<Note>
  `merge_entities=True` automatically resolves duplicate entity references: "Apple", "Apple Inc.", "AAPL": using semantic similarity. No manual deduplication needed.
</Note>

</Step>

<Step title="Visualize">

Render an interactive, zoomable knowledge graph in the browser.

```python
from semantica.visualization import GraphVisualizer

viz = GraphVisualizer(
    layout="force",        # "force" | "hierarchical" | "circular"
    node_color_by="type",  # color nodes by entity type
    show_confidence=True,
)
viz.visualize(graph, output="graph.html")
```

Open `graph.html` in any browser: pan, zoom, click nodes for details, filter by entity type.

</Step>

<Step title="Export">

Export to any downstream format.

<CodeGroup>

```python RDF / Semantic Web
from semantica.export import RDFExporter

exporter = RDFExporter()
exporter.export_to_rdf(graph, format="turtle",  output="graph.ttl")
exporter.export_to_rdf(graph, format="json-ld", output="graph.jsonld")
exporter.export_to_rdf(graph, format="nt",      output="graph.nt")
```

```python Parquet / Analytics
from semantica.export import ParquetExporter

exporter = ParquetExporter()
exporter.export(graph, output_dir="output/")
# Writes nodes.parquet + edges.parquet: ready for Spark, BigQuery, Databricks
```

```python ArangoDB
from semantica.export import ArangoDBExporter

exporter = ArangoDBExporter()
aql      = exporter.export(graph)
# Returns ready-to-run AQL INSERT statements
```

</CodeGroup>

</Step>

</Steps>


## Add Decision Intelligence

Track every agent decision with full causal chains and provenance: one extra import:

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    decision_tracking=True,
)

# Store a fact with provenance
context.store("GPT-4 outperforms GPT-3.5 on reasoning benchmarks by 40%")

# Record a decision
decision_id = context.record_decision(
    category="model_selection",
    scenario="Choose LLM for production reasoning pipeline",
    reasoning="GPT-4 benchmark advantage justifies 3x cost increase",
    outcome="selected_gpt4",
    confidence=0.91,
)

# Retrieve similar past decisions: prevents inconsistent choices
precedents = context.find_precedents("model selection reasoning", limit=5)
influence  = context.analyze_decision_influence(decision_id)
```


## Common Patterns

<AccordionGroup>

<Accordion title="Process raw text directly: no file needed" icon="text">

```python
from semantica.semantic_extract import NERExtractor, RelationExtractor

text = "Apple Inc. was founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976 in Cupertino, California."

ner           = NERExtractor()
entities      = ner.extract(text)

rel           = RelationExtractor()
relationships = rel.extract(text, entities=entities)
```

</Accordion>

<Accordion title="Multi-source incremental graph build" icon="layer-group">

```python
from semantica.kg import GraphBuilder

builder     = GraphBuilder(merge_entities=True)
all_entities, all_rels = [], []

for doc in parsed_docs:
    entities = ner.extract(doc)
    rels     = rel.extract(doc, entities=entities)
    all_entities.extend(entities)
    all_rels.extend(rels)

graph = builder.build(entities=all_entities, relationships=all_rels)
```

</Accordion>

<Accordion title="Temporal knowledge graph with point-in-time queries" icon="clock">

```python
from semantica.kg import TemporalKnowledgeGraph
from datetime import datetime

tkg = TemporalKnowledgeGraph()

tkg.add_node("Tim Cook",   role="CEO", valid_from=datetime(2011, 8, 24))
tkg.add_node("Steve Jobs", role="CEO", valid_from=datetime(1997, 9, 16),
             valid_until=datetime(2011, 8, 24))

# What did the graph look like on Jan 1, 2005?
snapshot = tkg.at(datetime(2005, 1, 1))
print(snapshot.get_node("Steve Jobs"))  # role: CEO
```

</Accordion>

<Accordion title="Persistent graph store: Neo4j, FalkorDB, Apache AGE" icon="database">

```python
from semantica.graph_store import Neo4jStore
from semantica.kg import GraphBuilder

store = Neo4jStore(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password",
)

builder = GraphBuilder(merge_entities=True, graph_store=store)
graph   = builder.build(entities=entities, relationships=relationships)
# Graph persisted to Neo4j: survives process restarts
```

</Accordion>

<Accordion title="Full provenance pipeline: W3C PROV-O" icon="link">

```python
from semantica.provenance import ProvenanceTracker
from semantica.kg import GraphBuilder

tracker = ProvenanceTracker()
builder = GraphBuilder(merge_entities=True, provenance=tracker)
graph   = builder.build(entities=entities, relationships=relationships)

# Every node and edge has full lineage
node = graph.get_node("Apple Inc.")
print(node.provenance)
# {
#   "source_document": "data/report.pdf",
#   "extraction_method": "NERExtractor:llm",
#   "extracted_at": "2026-05-22T10:30:00Z",
#   "confidence": 0.98
# }
```

</Accordion>

</AccordionGroup>


## Troubleshooting

<AccordionGroup>

<Accordion title="No entities extracted" icon="magnifying-glass">

The document likely contains scanned images rather than machine-readable text. Enable OCR:

```python
from semantica.parse import DocumentParser

parser = DocumentParser(ocr=True)  # enables Tesseract OCR
parsed = parser.parse(sources[0])
```

</Accordion>

<Accordion title="Slow processing on large corpora" icon="gauge">

Enable parallel processing and GPU acceleration:

```bash
pip install semantica[gpu]
```

```python
from semantica.pipeline import Pipeline

pipeline = Pipeline(workers=8, batch_size=32)
pipeline.run(sources)
```

</Accordion>

<Accordion title="Memory errors on large graphs" icon="memory">

Switch from in-memory NetworkX to a persistent backend:

```python
from semantica.graph_store import FalkorDBStore

store   = FalkorDBStore(host="localhost", port=6379)
builder = GraphBuilder(merge_entities=True, graph_store=store)
```

</Accordion>

<Accordion title="NER falls back to pattern mode on enterprise gateway" icon="triangle-exclamation">

Fixed in **v0.5.0**. Upgrade:

```bash
pip install --upgrade semantica
```

</Accordion>

</AccordionGroup>


## Next Steps

- [Core Concepts](concepts) — Knowledge graphs, ontologies, reasoning engines: the mental model behind Semantica.
- [Module Reference](modules) — Every module explained with key classes and common chains.
- [API Reference](reference/context) — Complete documentation for every module, class, and parameter.
- [Cookbook](cookbook) — 40+ interactive Jupyter notebooks with real-world datasets.
