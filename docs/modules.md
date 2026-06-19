---
title: "Modules"
description: "Every Semantica module works independently: use only what you need."
icon: "puzzle-piece"
---

<Info>
  Looking for a quick reference? Jump to the [Module Index](#module-index) at the bottom.
</Info>

<Tip>
  Not sure which module to use? The [Choose the Right Module](choose-your-module) guide maps 35+ developer goals to modules with code examples — start there if you're orienting for the first time.
</Tip>

Semantica is organized into **27 modules** across six logical layers. Each module is independently importable: you never pay for what you don't use.

## Architecture Overview

- **Input Layer** — Data ingestion and preparation. Modules: `ingest`, `parse`, `split`, `normalize`
- **Core Processing** — Intelligence and understanding. Modules: `semantic_extract`, `kg`, `ontology`, `reasoning`
- **Storage** — Persistent data storage. Modules: `embeddings`, `vector_store`, `graph_store`, `triplet_store`
- **Quality Assurance** — Data quality and consistency. Modules: `deduplication`, `conflicts`
- **Context & Memory** — Agent memory and decision tracking. Modules: `context`, `provenance`, `change_management`
- **Output & Orchestration** — Export, visualization, and workflows. Modules: `export`, `visualization`, `pipeline`, `explorer`


## Input Layer

### Ingest

Loads data from files, web, databases, and streams into a unified `SourceDocument` format.

```python
from semantica.ingest import FileIngestor, WebIngestor, ParquetIngestor, XMLIngestor

# Files: PDF, DOCX, CSV, Excel, PPTX, JSON, HTML, archives
ingestor = FileIngestor()
documents = ingestor.ingest_directory("data/")

# Web crawl
web_ingestor = WebIngestor()
pages = web_ingestor.ingest_urls(["https://example.com"])

# Parquet: single file, partitioned directory, Hive-style (v0.5.0)
parquet = ParquetIngestor()
sources = parquet.ingest("data/events.parquet")

# XML with XSD/DTD validation, namespace handling (v0.5.0)
xml = XMLIngestor(validate_xsd="schema.xsd")
sources = xml.ingest("data/records/")
```

**Available ingestors:** `FileIngestor`, `WebIngestor`, `ParquetIngestor`, `XMLIngestor`, `RESTIngestor`, `PublicAPIIngestor`, `DBIngestor`, `DuckDBIngestor`, `ElasticIngestor`, `EmailIngestor`, `FeedIngestor`, `GDriveIngestor`, `HuggingFaceIngestor`, `MCPIngestor`, `MongoIngestor`, `OntologyIngestor`, `PandasIngestor`, `RepoIngestor`, `SnowflakeIngestor`, `StreamIngestor`

### Parse

Extracts structured text and layout metadata from raw documents.

```python
from semantica.parse import DocumentParser, DoclingParser

# Standard parser: all common formats
parser = DocumentParser()
parsed = parser.parse_document("document.pdf")

# Advanced parser: multi-column PDFs, merged-cell tables, OCR
parser = DoclingParser(extract_tables=True, extract_images=True, output_format="markdown")
parsed = parser.parse("data/annual_report.pdf")
```

**Available parsers:** `DocumentParser`, `DoclingParser`, `CodeParser`, `CSVParser`, `DocxParser`, `EmailParser`, `ExcelParser`, `HTMLParser`, `ImageParser`, `JSONParser`, `MCPParser`, `MediaParser`, `PDFParser`, `PPTXParser`, `StructuredDataParser`, `WebParser`, `XMLParser`

### Split

Chunks text for embedding and RAG pipelines with awareness of semantic boundaries.

```python
from semantica.split import TextSplitter

splitter = TextSplitter(method="semantic_transformer")
chunks = splitter.split(text, chunk_size=1000, chunk_overlap=200)
```

**Chunking strategies:** `recursive`, `semantic_transformer`, `entity_aware`, `relation_aware`, `sliding_window`, `structural`

### Normalize

Cleans and standardizes text before semantic processing.

```python
from semantica.normalize import TextNormalizer, normalize_text, normalize_date

normalizer = TextNormalizer()
clean_text        = normalizer.normalize_text(text)
standardized_date = normalize_date("Jan 1st, 2020")
```

**Normalizers available:** text cleaning, entity canonicalization, date normalization, number normalization, encoding handling, language detection


## Core Processing

### Semantic Extract

Named entity recognition, relation extraction, and triplet generation.

```python
from semantica.semantic_extract import NERExtractor, RelationExtractor, TripletExtractor

ner = NERExtractor(method="llm", llm_provider=llm)
entities = ner.extract("Apple Inc. was founded by Steve Jobs.")

rel = RelationExtractor(method="llm", llm_provider=llm)
relationships = rel.extract(text, entities=entities)

trip = TripletExtractor(method="llm", llm_provider=llm)
triplets = trip.extract(text)
```

**Extraction methods:** `"pattern"` (no API key), `"ml"` (local model), `"llm"` (any of the 8 supported providers)

**Additional extractors:** `CoreferenceResolver`, `EventDetector`, `SemanticAnalyzer`, `SemanticNetworkExtractor`

### Knowledge Graph

Graph construction, graph algorithms, temporal model, and distance intelligence.

```python
from semantica.kg import GraphBuilder, GraphAnalyzer, TemporalGraphQuery, SimilarityCalculator
from datetime import datetime

# Build
builder = GraphBuilder(merge_entities=True)
kg = builder.build(entities=entities, relationships=relationships)

# Temporal graphs (v0.4.0)
query_engine = TemporalGraphQuery(enable_temporal_reasoning=True)
snapshot = query_engine.query_at_time(kg, query="", at_time=datetime(2021, 6, 15))

# Semantic similarity (v0.5.0)
calc = SimilarityCalculator()
scores = calc.calculate_similarity(entity_a, entity_b)
```

**Graph algorithms available:** centrality calculation, community detection, connectivity analysis, entity resolution, link prediction, path finding, similarity calculation

### Ontology

Schema management including SHACL, SKOS, alignments, diff/migration, auto-generation, and the visual Ontology Hub (v0.5.0).

```python
from semantica.ontology import OntologyGenerator, SHACLGenerator

generator = OntologyGenerator()
ontology  = generator.generate_from_graph(kg)

shacl  = SHACLGenerator()
shapes = shacl.generate(ontology)
```

**Components:** `OntologyGenerator`, `SHACLGenerator`, `OntologyValidator`, `OntologyEvaluator`, `LLMOntologyGenerator`, `OWLGenerator`, `PropertyGenerator`, `DomainOntologies`, `NamespaceManager`

### Reasoning

Derives new facts from existing knowledge using multiple inference strategies.

```python
from semantica.reasoning import Reasoner, DatalogReasoner

# Rule-based reasoning
engine = Reasoner()
engine.apply_transitivity("located_in")
engine.apply_symmetry("knows")
result = engine.infer()

# Datalog: recursive Horn clause rules (v0.4.0)
datalog = DatalogEngine()
datalog.add_rule("ancestor(X, Z) :- parent(X, Y), ancestor(Y, Z).")
results = datalog.query("ancestor(alice, ?)")
```

**Engines:** forward chaining, Rete network, deductive, abductive, SPARQL, Datalog: all produce explainable inference paths


## Storage

### Embeddings

Generates and manages vector embeddings for semantic similarity.

```python
from semantica.embeddings import EmbeddingGenerator

generator  = EmbeddingGenerator(model="sentence-transformers")
embeddings = generator.generate(["text1", "text2"])
similarity = generator.similarity(embeddings[0], embeddings[1])
```

**Supported models:** Sentence-Transformers, FastEmbed, OpenAI, BGE

**Components:** `EmbeddingGenerator`, `TextEmbedder`, `VectorEmbeddingManager`, `GraphEmbeddingManager`, `PoolingStrategies`

### Vector Store

Multi-backend vector database with hybrid search support.

```python
from semantica.vector_store import VectorStore

store   = VectorStore(backend="faiss", dimension=768)
store.add_vectors(embeddings, ids)
results = store.search(query_vector, top_k=10)
```

**Backends:** FAISS, Pinecone, Weaviate, Qdrant, Milvus, PgVector, in-memory

**Search modes:** semantic top-k, hybrid (vector + keyword), metadata-filtered

### Graph Store

Connects to graph databases for persistent, query-able storage.

```python
from semantica.graph_store import GraphStore

store = GraphStore(backend="neo4j")
store.add_nodes(entities)
store.add_edges(relationships)
results = store.query("MATCH (n)-[r]->(m) RETURN n, r, m")
```

**Backends:** Neo4j, FalkorDB, Apache AGE, Amazon Neptune

### Triplet Store

RDF triple-based storage with SPARQL query support.

```python
from semantica.triplet_store import TripletStore

store = TripletStore(backend="blazegraph")
store.add_triplets(subject, predicate, obj)
results = store.sparql("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")
```

**Backends:** Blazegraph, Apache Jena, RDF4J


## Quality Assurance

### Deduplication

Detects, scores, and merges duplicate entities across sources.

```python
from semantica.deduplication import EntityResolver

resolver = EntityResolver()
merged   = resolver.resolve(entities, strategy="semantic_v2")
```

**v2 strategies** (`blocking_v2`, `hybrid_v2`, `semantic_v2`) are up to 7x faster than v1.

**Components:** `EntityResolver`, `DuplicateDetector`, `EntityMerger`, `SimilarityCalculator`, `ClusterBuilder`

**`DuplicateDetector` options:** `max_results`, `top_k_per_entity`, `min_similarity`, `sort_by`

### Conflicts

Detects and resolves fact conflicts across overlapping knowledge sources.

```python
from semantica.conflicts import ConflictDetector

detector  = ConflictDetector()
conflicts = detector.detect_conflicts(kg)
resolved  = detector.resolve(conflicts, strategy="most_recent")
```

**Detection types:** value conflicts, type conflicts, temporal conflicts, logical conflicts

**Resolution strategies:** prefer most recent, prefer most reliable source, majority vote, flag for manual review


## Context & Memory

### Context

Agent context graphs, decision tracking, causal chains, and precedent search.

```python
from semantica.context import AgentContext, ContextGraph

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    decision_tracking=True,
)

context.store("GPT-4 outperforms GPT-3.5 on reasoning benchmarks by 40%")

decision_id = context.record_decision(
    category="model_selection",
    scenario="...",
    reasoning="...",
    outcome="...",
    confidence=0.9,
)

precedents = context.find_precedents("model selection", limit=5)
```

**Components:** `AgentContext`, `ContextGraph`, `AgentMemory`, `DecisionRecorder`, `CausalAnalyzer`, `EntityLinker`, `PolicyEngine`

### Provenance

W3C PROV-O compliant lineage tracking across all modules.

```python
from semantica.provenance import ProvenanceManager

manager = ProvenanceManager()
manager.track_entity("entity_1", "document.pdf", "person")
lineage = manager.get_lineage("entity_1")
```

**Components:** `ProvenanceManager`, `IntegrityChecker`, `BridgeAxiom`, `ProvenanceStorage`

### Change Management

Version control with SHA-256 checksums, diffs, and rollback.

```python
from semantica.change_management import TemporalVersionManager

manager  = TemporalVersionManager(storage_path="versions.db")
snapshot = manager.create_snapshot(kg, "v1.0", "user@example.com", "Initial version")
diff     = manager.diff("v1.0", "v1.1")
```

**Components:** `TemporalVersionManager`, `ChangeLog`, `OntologyVersionManager`, `VersionStorage`


## Output & Orchestration

### Export

Serializes graphs to downstream formats for analytics, semantic web, or graph databases.

```python
from semantica.export import RDFExporter, ParquetExporter, ArangoDBExporter

# RDF formats
RDFExporter().export_to_rdf(graph, format="turtle", output="graph.ttl")

# Analytics
ParquetExporter().export(graph, output_dir="output/")

# ArangoDB
aql = ArangoDBExporter().export(graph)
```

**Export formats:** RDF (Turtle, JSON-LD, N-Triples, XML), Parquet, ArangoDB AQL, CSV, OWL, Arrow, LPG, YAML, distance matrices

### Visualization

Renders interactive and static knowledge graph visualizations.

```python
from semantica.visualization import GraphVisualizer

viz = GraphVisualizer()
viz.visualize(graph, output="graph.html")
```

**Visualizers:** `GraphVisualizer`, `OntologyVisualizer`, `EmbeddingVisualizer`, `SemanticNetworkVisualizer`, `TemporalVisualizer`, `AnalyticsVisualizer`

**Layout algorithms:** force-directed, hierarchical, circular

### Pipeline

Pipeline DSL with parallel workers, retry policies, and failure handling.

```python
from semantica.pipeline import Pipeline

pipeline = Pipeline()
pipeline.add_step("ingest",   FileIngestor())
pipeline.add_step("extract",  NERExtractor())
pipeline.add_step("build",    GraphBuilder())
result = pipeline.run("data/")
```

**Components:** `Pipeline`, `PipelineBuilder`, `ExecutionEngine`, `FailureHandler`, `PipelineValidator`, `ParallelismManager`, `ResourceScheduler`

### Explorer

FastAPI Knowledge Explorer with Ontology Hub, WebSocket progress, bidirectional path finding, and indexed search (0.004ms on 118k nodes).

```bash
semantica-explorer --graph my_graph.json
```

**Routes:** graph, ontology, provenance, decisions, analytics, SPARQL, temporal, annotations, export/import, vocabulary


## Utilities

### LLM Providers

Unified interface to all supported LLM providers.

```python
from semantica.llms import Groq, OpenAI, LiteLLM
import os

llm = Groq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))
llm = OpenAI(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY"))
# Anthropic, Gemini, Ollama, DeepSeek via LiteLLM:
llm = LiteLLM(model="anthropic/claude-opus-4-7", api_key=os.getenv("ANTHROPIC_API_KEY"))
```

**Supported providers:** OpenAI, Anthropic, Google Gemini, Groq, Ollama, DeepSeek, Novita AI, LiteLLM (20+ models via one interface)

### MCP Server

Exposes Semantica as an MCP stdio server for IDE and agent integrations.

```bash
python -m semantica.mcp_server
```

**Integrations:** Claude Desktop, VS Code, Cursor, Windsurf, Cline: 12 MCP tools exposed

### Seed

Bootstrap knowledge graphs from verified structured sources: fixed-point reference data, controlled vocabularies, and domain anchors.

```python
from semantica.seed import SeedManager

seed = SeedManager()
seed.populate(kg, dataset="companies", count=100)

# Load domain seeds from file or built-in datasets
seed.load_from_file("seed_data/industries.json")
seed.inject(kg)   # merges seed nodes without duplicating existing entities
```

**Use cases:** anchoring extraction with known entities, pre-populating ontology classes, deterministic test graph generation.

### Evals

Evaluation framework for measuring KG quality, extraction accuracy, and pipeline performance.

```python
from semantica.evals import KGEvaluator, ExtractionEvaluator, PipelineEvaluator, RegressionTracker

# KG quality
report = KGEvaluator().evaluate(kg, ontology=ontology)
print(f"Completeness: {report.completeness:.2%}  Consistency: {report.consistency:.2%}")

# Extraction accuracy
report = ExtractionEvaluator().evaluate_ner(predictions=extracted, gold_standard=annotated)
print(f"Precision: {report.precision:.3f}  Recall: {report.recall:.3f}  F1: {report.f1:.3f}")

# Pipeline throughput and latency
metrics = PipelineEvaluator().benchmark(pipeline, data="data/", bench_runs=5)
print(f"Throughput: {metrics.docs_per_second:.1f} docs/sec")

# Regression tracking across runs
tracker = RegressionTracker(db_path="eval_history.db")
run_id  = tracker.record_run(pipeline_version="v1.2.0", metrics=metrics)
diff    = tracker.compare(run_id, baseline_run_id="run_abc123")
```

**Components:** `KGEvaluator`, `ExtractionEvaluator`, `PipelineEvaluator`, `RegressionTracker`

### Core

Base classes, shared data models, and the plugin registry used across all modules.

```python
from semantica.core import Semantica, PluginRegistry, ConfigManager

# Top-level orchestrator
sem = Semantica(config_path="config.yaml")
sem.initialize()

# Plugin registry: register custom components
registry = PluginRegistry()
registry.register("my_ingestor", MyCustomIngestor)

# Config management
config  = ConfigManager(config_path="config.yaml")
batch   = config.get("processing.batch_size", default=32)
```

**Components:** `Semantica`, `PluginRegistry`, `ConfigManager`, `LifecycleManager`, `HealthMonitor`, `Config`

### Utils

Shared utilities for ID generation, date parsing, validation, and logging.

```python
from semantica.utils import helpers, validators, logging
```

**Components:** `helpers`, `validators`, `constants`, `types`, `exceptions`, `logging`, `ProgressTracker`


## Common Module Chains

<Tabs>
  <Tab title="Document → KG">
    Load documents from any source and turn them into a queryable knowledge graph.

    **Pipeline:** `Ingest` → `Parse` → `Normalize` → `Semantic Extract` → `GraphBuilder` → `KG`

```python
from semantica.ingest import FileIngestor
from semantica.parse import DocumentParser
from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.kg import GraphBuilder

sources       = FileIngestor().ingest("data/")
parsed        = DocumentParser().parse(sources[0])
entities      = NERExtractor(method="llm", llm_provider=llm).extract(parsed)
relationships = RelationExtractor(method="llm", llm_provider=llm).extract(parsed, entities=entities)
graph         = GraphBuilder(merge_entities=True).build(
                    entities=entities, relationships=relationships
                )
```

    **Best for:** research pipelines, enterprise data extraction, document intelligence
  </Tab>

  <Tab title="GraphRAG">
    Ground every LLM response in a knowledge graph: structured retrieval with source attribution.

    **Pipeline:** `KG` + `VectorStore` → `AgentContext` → GraphRAG query → grounded answer

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
)
context.load_graph("company_kg.json")

result = context.query(
    "What companies did Apple alumni found?",
    mode="graphrag",
    reasoning=True,
)
for claim in result.claims:
    print(f"{claim.text}  →  {claim.source_node}")
```

    **Best for:** question-answering systems, RAG with source attribution, research assistants
  </Tab>

  <Tab title="AI Agent">
    Give your agent persistent memory, decision tracking, and policy enforcement.

    **Pipeline:** `AgentContext` → decision recording → precedent search → policy check → causal analysis

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    decision_tracking=True,
)
context.store("GPT-4 outperforms GPT-3.5 on reasoning by 40%")

decision_id = context.record_decision(
    category="model_selection",
    scenario="Choose LLM for production",
    reasoning="Benchmark advantage justifies cost",
    outcome="selected_gpt4",
    confidence=0.91,
)
precedents = context.find_precedents("model selection", limit=5)
```

    **Best for:** autonomous agents, AI copilots, decision-support systems
  </Tab>

  <Tab title="Compliance Pipeline">
    Full provenance from raw data to final inference: W3C PROV-O, SHA-256 checksums, audit trail.

    **Pipeline:** `Ingest` → `Parse` → `Extract` → `KG` → `Provenance` → `ChangeManagement` → `Export`

```python
from semantica.ingest import FileIngestor
from semantica.semantic_extract import NERExtractor
from semantica.kg import GraphBuilder
from semantica.provenance import ProvenanceManager
from semantica.export import RDFExporter

sources  = FileIngestor().ingest("records/")
entities = NERExtractor(method="llm", llm_provider=llm).extract(sources)
graph    = GraphBuilder(merge_entities=True).build(entities=entities, relationships=[])
prov     = ProvenanceManager()
lineage  = prov.get_entity_lineage("entity_id")

RDFExporter(include_provenance=True).export_to_rdf(graph, format="turtle", output="audit.ttl")
```

    **Best for:** HIPAA, SOX, GDPR, FDA 21 CFR Part 11 deployments
  </Tab>

  <Tab title="Web Scraping → Graph">
    Crawl websites, normalize text, and extract knowledge directly from the web.

    **Pipeline:** `WebIngestor` → `Normalize` → `Semantic Extract` → `GraphStore`

```python
from semantica.ingest import WebIngestor
from semantica.normalize import TextNormalizer
from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.graph_store import Neo4jStore

pages      = WebIngestor(max_depth=2).ingest("https://example.com")
normalizer = TextNormalizer()
store      = Neo4jStore(uri="bolt://localhost:7687", user="neo4j", password="password")

for page in pages:
    text          = normalizer.normalize_text(page.text)
    entities      = NERExtractor().extract(text)
    relationships = RelationExtractor().extract(text, entities=entities)
    store.add_nodes(entities)
    store.add_edges(relationships)
```

    **Best for:** competitive intelligence, news monitoring, research aggregation
  </Tab>

  <Tab title="Temporal Analysis">
    Track how facts change over time: point-in-time queries, snapshots, and versioning.

    **Pipeline:** `KG (Temporal)` → `TemporalGraphQuery` → `VersionManager` → `ChangeManagement`

```python
from semantica.kg import GraphBuilder, TemporalGraphQuery, TemporalVersionManager

builder = GraphBuilder()
kg      = builder.build(sources=[{
    "entities": [{"id": "alice", "type": "Person"}],
    "relationships": [{"source": "alice", "target": "acme", "type": "ceo_of",
                       "valid_from": "2020-01-01", "valid_until": "2023-06-01"}]
}])

query         = TemporalGraphQuery()
snapshot_2021 = query.reconstruct_at_time(kg, "2021-06-15")

versioner = TemporalVersionManager()
versioner.create_snapshot(kg, "2024-Q1", author="user@example.com", description="Q1 snapshot")
```

    **Best for:** financial history, regulatory timelines, organizational change tracking
  </Tab>
</Tabs>


## Module Index

| Module | Purpose | Key Classes |
| :------ | :------- | :----------- |
| [ingest](reference/ingest) | Data ingestion | `FileIngestor`, `WebIngestor`, `ParquetIngestor`, `XMLIngestor` |
| [parse](reference/parse) | Document parsing | `DocumentParser`, `DoclingParser` |
| [split](reference/split) | Text chunking | `TextSplitter` |
| [normalize](reference/normalize) | Data cleaning | `TextNormalizer`, `EntityNormalizer`, `LanguageDetector` |
| [semantic_extract](reference/semantic_extract) | NER & relation extraction | `NERExtractor`, `RelationExtractor`, `TripletExtractor`, `SemanticAnalyzer`, `SemanticNetworkExtractor`, `ExtractionValidator` |
| [kg](reference/kg) | Graph construction | `GraphBuilder`, `TemporalGraphQuery`, `SimilarityCalculator` |
| [ontology](reference/ontology) | Schema management | `OntologyGenerator`, `SHACLGenerator` |
| [reasoning](reference/reasoning) | Logical inference | `Reasoner`, `DatalogReasoner` |
| [embeddings](reference/embeddings) | Vector embeddings | `EmbeddingGenerator` |
| [vector_store](reference/vector_store) | Vector database | `VectorStore` |
| [graph_store](reference/graph_store) | Graph database | `GraphStore` |
| [triplet_store](reference/triplet_store) | RDF triple store | `TripletStore` |
| [deduplication](reference/deduplication) | Entity resolution | `EntityResolver`, `DuplicateDetector`, `ClusterBuilder`, `MergeStrategyManager` |
| [conflicts](reference/conflicts) | Conflict resolution | `ConflictDetector` |
| [context](reference/context) | Agent context & decisions | `AgentContext`, `ContextGraph` |
| [provenance](reference/provenance) | W3C PROV-O lineage | `ProvenanceManager` |
| [change_management](reference/change_management) | Version control | `TemporalVersionManager` |
| [export](reference/export) | Data export | `RDFExporter`, `ParquetExporter` |
| [visualization](reference/visualization) | Graph visualization | `GraphVisualizer` |
| [pipeline](reference/pipeline) | Workflow orchestration | `Pipeline`, `PipelineBuilder` |
| [explorer](reference/explorer) | Knowledge Explorer UI | `semantica-explorer --graph <file>` |
| [llms](reference/llms) | LLM providers | `Groq`, `OpenAI`, `create_provider` |
| [mcp_server](reference/mcp_server) | MCP stdio server | `python -m semantica.mcp_server` |
| [seed](reference/seed) | KG bootstrapping from structured sources | `SeedManager` |
| [evals](reference/evals) | Quality evaluation | `KGEvaluator`, `ExtractionEvaluator`, `PipelineEvaluator`, `RegressionTracker` |
| [core](reference/core) | Base classes & registry | `Semantica`, `ConfigManager`, `PluginRegistry`, `LifecycleManager` |
| [utils](reference/utils) | Shared utilities | `helpers`, `validators` |

- [Getting Started](getting-started) — Your first knowledge graph in 5 minutes.
- [Cookbook](cookbook) — 40+ domain notebooks with real-world examples.
- [API Reference](reference/context) — Full technical documentation.
