---
title: "Quickstart"
description: "Build your first knowledge graph in 5 minutes. No configuration required."
icon: "rocket"
---

<Info>
  **v0.6.8**: cryptographically signed releases (SLSA provenance + Sigstore), real vector-store enumeration across FAISS/Qdrant/Weaviate/Milvus, and first-class Anthropic/Gemini/Ollama/DeepSeek/Novita LLM provider wrappers. <a href="https://github.com/semantica-agi/semantica/releases" style={{color:"#10B981",fontWeight:600,textDecoration:"none"}}>What's new →</a>
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
# 0.6.8
```


## Full Pipeline

<img src="/assets/img/diagrams/pipeline-flow.svg" alt="Semantica end-to-end pipeline: Ingest → Parse → Normalize → Extract → Build KG → QA → Store → Deliver" style={{ width: '100%', borderRadius: '10px', margin: '0 0 24px' }} />

<Steps>

<Step title="Ingest">

Load a document from a file or directory. The rest of this walkthrough follows
the file path; other sources are shown afterwards.

```python
from semantica.ingest import FileIngestor

ingestor = FileIngestor()
sources  = ingestor.ingest("data/report.pdf")
# Also accepts a directory, .docx, .html, .json, .csv, .xlsx, .pptx, .parquet, .xml
```

<Tip>
  **Other sources.** `WebIngestor().ingest_url(url)` returns a `WebContent` whose
  `.text` you can feed straight into the Extract step (no parsing needed).
  `ParquetIngestor().ingest(path)` and `XMLIngestor().ingest(path, schema_path=...)`
  return structured records rather than documents; build a graph from those with
  `GraphBuilder().build({"entities": [...], "relationships": [...]})` directly.
</Tip>

</Step>

<Step title="Parse">

Extract structured text and layout from raw documents.

```python
from semantica.parse import DocumentParser

parser = DocumentParser()
parsed = parser.parse(sources[0].path)   # parse() takes a path string

print(parsed["full_text"][:200])   # extracted text
print(parsed["metadata"])          # document properties (fields vary by format)
```

`parse()` returns a `dict`. `full_text` and `metadata` are present for every
format; other keys depend on the parser (`pages` for PDF, `tables` and
`paragraphs` for DOCX, `tables` for `DoclingParser`).

<Tip>
  For PDFs with tables, charts, or multi-column layouts, use `DoclingParser` (`pip install semantica[parse-docling]`): it applies advanced layout analysis and returns structured table data alongside text.
</Tip>

```python
from semantica.parse import DoclingParser

parser = DoclingParser()
parsed = parser.parse(sources[0].path)
print(parsed["tables"])   # structured table data
```

</Step>

<Step title="Extract Entities & Relationships">

Identify named entities and extract typed relationships between them.

<CodeGroup>

```python Pattern-based (fast, no API key)
from semantica.semantic_extract import NERExtractor, RelationExtractor

text = parsed["full_text"]

ner      = NERExtractor(method="pattern")
entities = ner.extract(text)
# Returns: [Entity(text="Apple Inc.", label="ORG", start_char=0, end_char=10, confidence=0.7), ...]

rel           = RelationExtractor(method="pattern")
relationships = rel.extract(text, entities=entities)
# Returns: [Relation(subject=Entity(...), predicate="founded_by", object=Entity(...), confidence=0.7), ...]
```

```python LLM-powered (higher accuracy)
from semantica.semantic_extract import NERExtractor, RelationExtractor

# Reads GROQ_API_KEY from the environment; provider/llm_model select the backend
text = parsed["full_text"]

ner           = NERExtractor(method="llm", provider="groq", llm_model="llama-3.3-70b-versatile")
entities      = ner.extract(text)

rel           = RelationExtractor(method="llm", provider="groq", llm_model="llama-3.3-70b-versatile")
relationships = rel.extract(text, entities=entities)
```

</CodeGroup>

</Step>

<Step title="Build the Knowledge Graph">

Assemble extracted entities and relationships into a queryable knowledge graph.

```python
from semantica.kg import GraphBuilder

builder = GraphBuilder(merge_entities=True)
graph   = builder.build({"entities": entities, "relationships": relationships})

print(f"Graph: {len(graph['entities'])} nodes, {len(graph['relationships'])} edges")
```

<Note>
  `merge_entities=True` automatically resolves duplicate entity references: "Apple", "Apple Inc.", "AAPL": using semantic similarity. No manual deduplication needed.
</Note>

</Step>

<Step title="Visualize">

Render an interactive, zoomable knowledge graph in the browser.

```python
from semantica.visualization import KGVisualizer

viz = KGVisualizer(
    layout="force",        # "force" | "hierarchical" | "circular"
)
viz.visualize_network(graph, output="html", file_path="graph.html", node_color_by="type")
```

Open `graph.html` in any browser: pan, zoom, click nodes for details, filter by entity type.

</Step>

<Step title="Export">

Export to any downstream format.

<CodeGroup>

```python RDF / Semantic Web
from semantica.export import RDFExporter

exporter = RDFExporter()
exporter.export(graph, file_path="graph.ttl",    format="turtle")
exporter.export(graph, file_path="graph.jsonld", format="json-ld")
exporter.export(graph, file_path="graph.nt",     format="nt")
```

```python Parquet / Analytics
from semantica.export import ParquetExporter

exporter = ParquetExporter()
exporter.export(graph, file_path="output/graph")
# Dict input writes one file per key: output/graph_entities.parquet and
# output/graph_relationships.parquet: ready for Spark, BigQuery, Databricks
```

```python ArangoDB
from semantica.export import ArangoAQLExporter

exporter = ArangoAQLExporter()
exporter.export(graph, file_path="graph.aql")
# Writes ready-to-run AQL INSERT statements to graph.aql
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
from semantica.ingest import FileIngestor
from semantica.parse import DocumentParser
from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.kg import GraphBuilder

parser  = DocumentParser()
ner     = NERExtractor(method="pattern")
rel     = RelationExtractor(method="pattern")
builder = GraphBuilder(merge_entities=True)

all_entities, all_rels = [], []
for source in FileIngestor().ingest("data/reports/"):
    text     = parser.parse(source.path)["full_text"]
    entities = ner.extract(text)
    rels     = rel.extract(text, entities=entities)
    all_entities.extend(entities)
    all_rels.extend(rels)

graph = builder.build({"entities": all_entities, "relationships": all_rels})
```

</Accordion>

<Accordion title="Temporal knowledge graph with point-in-time queries" icon="clock">

```python
from semantica.kg import GraphBuilder, TemporalGraphQuery

builder = GraphBuilder()
kg = builder.build({
    "entities": [
        {"id": "alice",     "type": "Person"},
        {"id": "acme_corp", "type": "Organization"},
        {"id": "beta_ltd",  "type": "Organization"},
    ],
    "relationships": [
        {
            "source": "alice", "target": "acme_corp", "type": "ceo_of",
            "valid_from": "2018-01-01", "valid_until": "2022-06-01",
        },
        {
            "source": "alice", "target": "beta_ltd", "type": "ceo_of",
            "valid_from": "2022-06-01",
        },
    ],
})

tq = TemporalGraphQuery(temporal_granularity="day")

result_2020 = tq.query_at_time(kg, query="",  # query reserved for future use
                               at_time="2020-06-15")
result_2023 = tq.query_at_time(kg, query="", at_time="2023-01-01")

print(f"Relationships active in 2020: {result_2020['num_relationships']}")
print(f"Relationships active in 2023: {result_2023['num_relationships']}")
```

</Accordion>

<Accordion title="Persistent graph store: Neo4j, FalkorDB, Apache AGE" icon="database">

```python
from semantica.graph_store import GraphStore
from semantica.kg import GraphBuilder

store = GraphStore(
    backend="neo4j",
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password",
)

builder = GraphBuilder(merge_entities=True, graph_store=store)
graph   = builder.build({"entities": entities, "relationships": relationships})
# Graph persisted to Neo4j: survives process restarts
```

</Accordion>

<Accordion title="Full provenance pipeline: W3C PROV-O" icon="link">

```python
from semantica.provenance import ProvenanceManager
from semantica.kg import GraphBuilder

prov    = ProvenanceManager()
prov.track_entity("Apple Inc.", "data/report.pdf", metadata={"confidence": 0.98})

builder = GraphBuilder(merge_entities=True)
graph   = builder.build({"entities": entities, "relationships": relationships})

# Retrieve full lineage for any entity
sources = prov.get_all_sources("Apple Inc.")
print(sources[0])
# {"source": "data/report.pdf", "location": None, "timestamp": "...",
#  "confidence": 1.0, "metadata": {"confidence": 0.98}}
```

</Accordion>

</AccordionGroup>


## Troubleshooting

<AccordionGroup>

<Accordion title="No entities extracted" icon="magnifying-glass">

The document likely contains scanned images rather than machine-readable text. `DocumentParser` warns when a PDF has no text layer; switch to `DoclingParser` with OCR enabled:

```python
from semantica.parse import DoclingParser   # pip install semantica[parse-docling]

parser = DoclingParser(enable_ocr=True)
parsed = parser.parse(sources[0].path)
```

</Accordion>

<Accordion title="Slow processing on large corpora" icon="gauge">

Install the GPU extras so embedding and ML inference run on CUDA:

```bash
pip install semantica[gpu]
```

Scan the directory for paths first (no file contents are read), then handle one
document at a time and write to a persistent graph backend instead of the
in-memory graph:

```python
from semantica.ingest import FileIngestor
from semantica.parse import DocumentParser
from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.graph_store import GraphStore
from semantica.kg import GraphBuilder

ingestor = FileIngestor()
parser   = DocumentParser()
ner      = NERExtractor(method="pattern")
rel      = RelationExtractor(method="pattern")
store    = GraphStore(backend="neo4j", uri="bolt://localhost:7687",
                      user="neo4j", password="password")
builder  = GraphBuilder(merge_entities=True, graph_store=store)

for info in ingestor.scan_directory("data/reports/", recursive=True):
    text     = parser.parse(info["path"])["full_text"]   # one document loaded at a time
    entities = ner.extract(text)
    rels     = rel.extract(text, entities=entities)
    builder.build({"entities": entities, "relationships": rels})
```

For multi-step orchestration with configurable parallelism, see the
[Pipeline guide](/guides/pipeline).

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

- [Core Concepts](/concepts): knowledge graphs, ontologies, and reasoning engines (the mental model behind Semantica).
- [Module Reference](/modules): every module explained with key classes and common chains.
- [API Reference](/reference/context): complete documentation for every module, class, and parameter.
- [Cookbook](/cookbook): 40+ interactive Jupyter notebooks with real-world datasets.
